"""
Unit and Integration Tests for core.commands Subsystem.
"""
import io
import json
import os
import socket
import sys
import tempfile
import time
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, patch

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require

import core
from core.commands import dispatcher
from core.commands.bags import CmdBags, CmdOption
from core.commands.dispatcher import dispatch, dispatch_local, _try_hot_dispatch
from core.commands.help import HelpRenderer
from core.commands.registry import (
    ArgSpec,
    CommandSpec,
    CommandsRegistry,
    OptionSpec,
)
from core.commands.resolver import (
    InvalidChoiceError,
    MissingArgumentError,
    MissingValueError,
    MutualExclusionError,
    OptionResolver,
)
from core.platform import daemon_probe
from tests import load_core_cli_module
import yscb


@require(Requirement.LOGIC)
class TestCoreCommandsSubsystem(YSCBTestCase):
    """core.commands 全功能、邊界與效能單元測試集合。"""

    def setUp(self):
        super().setUp()
        self._orig_auto_spawn_warned = dispatcher._AUTO_SPAWN_WARNED
        self._orig_last_error_hint = dispatcher._LAST_DISPATCH_ERROR_HINT

    def tearDown(self):
        dispatcher._AUTO_SPAWN_WARNED = False
        dispatcher._LAST_DISPATCH_ERROR_HINT = ""
        dispatcher.clear_cache()
        super().tearDown()

    def test_pep562_lazy_loading(self):
        """驗證 PEP 562 Lazy Loading：引用 core.commands 不載入重型子模組。"""
        self.assertTrue(hasattr(core, "__getattr__"))
        self.assertIn("commands", dir(core))
        cmds = core.commands
        self.assertIsNotNone(cmds)
        self.mark_passed()

    def test_commands_schema_parser(self):
        """驗證 Contributes Commands Schema 解析 (含 module_alias, tier, server_compatible, args, options, usage)。"""
        raw_schema = {
            "module_alias": ["testmod", "tm"],
            "description": "Test module description",
            "cmd": {
                "run": {
                    "description": "Run task",
                    "tier": "safe",
                    "server_compatible": True,
                    "args": {
                        "mode": {
                            "description": "Execution mode",
                            "required": True,
                            "choice": ["auto", "safe", "force"]
                        }
                    },
                    "options": {
                        "mode": {
                            "fast": {"description": "Fast run", "alias": ["f"]},
                            "slow": {"description": "Slow run", "alias": ["s"]},
                        },
                        "output": {
                            "file": {
                                "description": "Output path",
                                "alias": ["o"],
                                "args": {
                                    "path": {"description": "File path"}
                                }
                            },
                        }
                    },
                    "usage": {
                        "pros": ["快速執行單元測試"],
                        "cons": ["[!] 嚴禁未編譯直接執行"]
                    }
                }
            }
        }
        reg = CommandsRegistry()
        mod_spec = reg.register_module("my-module", raw_schema)

        self.assertEqual(mod_spec.module_name, "my-module")
        self.assertEqual(mod_spec.module_alias, ["testmod", "tm"])
        self.assertEqual(reg.resolve_module_name("tm"), "my-module")
        self.assertEqual(reg.resolve_module_name("testmod"), "my-module")

        cmd = reg.get_command("my-module", "run")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.tier, "safe")
        self.assertTrue(cmd.server_compatible)
        self.assertIn("mode", cmd.args)
        self.assertTrue(cmd.args["mode"].required)
        self.assertEqual(cmd.args["mode"].choice, ["auto", "safe", "force"])
        self.assertIn("mode", cmd.groups)
        self.assertIn("file", cmd.canonical_options)
        self.assertTrue(cmd.canonical_options["file"].takes_value)
        self.assertFalse(cmd.canonical_options["fast"].takes_value)
        self.assertEqual(cmd.canonical_options["file"].alias, ["o"])
        self.assertIn("快速執行單元測試", cmd.usage_pros)
        self.assertIn("[!] 嚴禁未編譯直接執行", cmd.usage_cons)
        self.mark_passed()

    def test_option_resolver(self):
        """驗證 OptionResolver 正交群組互斥、別名規範化與 args 帶參解析。"""
        cmd_spec = CommandSpec(
            name="test",
            description="Test cmd",
            groups={"output_format": ["json", "table"]},
            options={
                "json": OptionSpec(canonical_name="json", alias=["j"], group_name="output_format"),
                "j": OptionSpec(canonical_name="json", alias=["j"], group_name="output_format"),
                "table": OptionSpec(canonical_name="table", alias=["t"], group_name="output_format"),
                "t": OptionSpec(canonical_name="table", alias=["t"], group_name="output_format"),
                "out": OptionSpec(canonical_name="out", alias=["o"], args={"dest": ArgSpec(name="dest")}, group_name="default"),
                "o": OptionSpec(canonical_name="out", alias=["o"], args={"dest": ArgSpec(name="dest")}, group_name="default"),
            },
            canonical_options={
                "json": OptionSpec(canonical_name="json", alias=["j"], group_name="output_format"),
                "table": OptionSpec(canonical_name="table", alias=["t"], group_name="output_format"),
                "out": OptionSpec(canonical_name="out", alias=["o"], args={"dest": ArgSpec(name="dest")}, group_name="default"),
            }
        )

        args, opts = OptionResolver.resolve(cmd_spec, ["pos1", "-j", "-o", "result.txt", "pos2"])
        self.assertEqual(args, ["pos1", "pos2"])
        self.assertIn("json", opts)
        self.assertTrue(opts["json"].params)
        self.assertIn("out", opts)
        self.assertEqual(opts["out"].params, "result.txt")

        _, opts2 = OptionResolver.resolve(cmd_spec, ["--out=result2.txt"])
        self.assertEqual(opts2["out"].params, "result2.txt")
        self.mark_passed()

    def test_cmdbags_dataclass(self):
        """驗證強型別 CmdBags 與 CmdOption 屬性完整度與不可變性。"""
        opt = CmdOption(name="json", params=True)
        bags = CmdBags(
            raw_cmd="status --json",
            command="status",
            args=["target_mod"],
            options={"json": opt}
        )
        self.assertEqual(bags.command, "status")
        self.assertEqual(bags.args, ["target_mod"])
        self.assertTrue(bags.has_option("json"))
        self.assertFalse(bags.has_option("table"))
        self.assertEqual(bags.get_option_value("json"), True)
        self.assertEqual(bags.get_option_value("missing", "default_val"), "default_val")

        with self.assertRaises(Exception):
            bags.command = "changed"
        self.mark_passed()

    def test_help_renderer(self):
        """驗證模組級與指令級 --help 渲染格式、choice 格式化與 ARGUMENTS 欄位輸出。"""
        reg = CommandsRegistry()
        reg.register_module("my-mod", {
            "module_alias": ["mm"],
            "description": "My sample module",
            "cmd": {
                "check": {
                    "description": "Pre-flight check",
                    "tier": "safe",
                    "server_compatible": True,
                    "args": {
                        "mode": {
                            "description": "Check mode",
                            "required": True,
                            "choice": ["auto", "safe"]
                        }
                    },
                    "options": {
                        "mode": {
                            "strict": {"description": "Strict check", "alias": ["s"]}
                        }
                    },
                    "usage": {
                        "pros": ["靜態檢查代碼"],
                        "cons": ["嚴禁跳過預檢"]
                    }
                }
            }
        })

        mod_spec = reg.get_module("my-mod")
        mod_help = HelpRenderer.render_module_help("my-mod", mod_spec)
        self.assertIn("YS-Codebase Module: my-mod", mod_help)
        self.assertIn("My sample module", mod_help)
        self.assertIn("Aliases    : mm", mod_help)
        self.assertIn("check <mode=[auto | safe]>", mod_help)

        cmd_spec = reg.get_command("my-mod", "check")
        cmd_help = HelpRenderer.render_cmd_help("my-mod", "check", cmd_spec)
        self.assertIn("Command: python yscb.py my-mod check", cmd_help)
        self.assertIn("USAGE:\n  python yscb.py my-mod check <mode=[auto | safe]> [options]", cmd_help)
        self.assertIn("ARGUMENTS:", cmd_help)
        self.assertIn("<mode=[auto | safe]>", cmd_help)
        self.assertIn("Check mode (choices: auto, safe) [required]", cmd_help)
        self.assertIn("[SAFE] 自主安全", cmd_help)
        self.assertIn("Hot IPC Compatible", cmd_help)
        self.assertIn("--strict", cmd_help)
        self.assertIn("靜態檢查代碼", cmd_help)
        self.assertIn("嚴禁跳過預檢", cmd_help)
        self.mark_passed()

    def test_server_compatible_routing(self):
        """驗證指令級 server_compatible 雙管道分流。"""
        with patch("core.commands.dispatcher._try_hot_dispatch", return_value=0) as mock_hot:
            with patch("core.commands.dispatcher._load_registry") as mock_reg_loader:
                reg = CommandsRegistry()
                reg.register_module("test-server-mod", {
                    "cmd": {
                        "hot_cmd": {
                            "description": "Hot task",
                            "server_compatible": True,
                        },
                        "cold_cmd": {
                            "description": "Cold task",
                            "server_compatible": False,
                        }
                    }
                })
                mock_reg_loader.return_value = reg

                ret = dispatch(["test-server-mod", "hot_cmd"])
                self.assertEqual(ret, 0)
                mock_hot.assert_called_once()

        self.mark_passed()

    def test_yscb_thin_host_delegation(self):
        """驗證 yscb.py 薄宿主對外公開介面與 core.commands.dispatcher 轉派。"""
        self.assertTrue(hasattr(yscb, "cmd_init"))
        self.assertTrue(hasattr(yscb, "cmd_self_update"))
        self.assertTrue(hasattr(yscb, "cmd_restore"))
        self.assertTrue(hasattr(yscb, "dispatch_module"))
        self.mark_passed()

    def test_hard_sunset_missing_command_function(self):
        """驗證向後相容過渡層徹底拔除：未定義精確函式之模組調用嚴格輸出 EC-05 並返回退出碼 127，不再退化至 process。"""
        fake_mod = MagicMock(spec=["process"])
        fake_mod.process.return_value = 0

        cmd_spec = CommandSpec(name="my_cmd", description="Legacy cmd")

        f_out = io.StringIO()
        f_err = io.StringIO()
        with redirect_stdout(f_out), redirect_stderr(f_err):
            with patch("core.commands.dispatcher._find_module_cli", return_value="/fake/cli.py"):
                with patch.dict("core.commands.dispatcher._MODULE_CACHE", {"/fake/cli.py": fake_mod}):
                    ret = dispatch_local("legacy_mod", "my_cmd", ["arg1"], cmd_spec, "/fake/root")

        self.assertEqual(ret, 127)
        fake_mod.process.assert_not_called()
        self.assertIn("EC-05", f_out.getvalue())
        self.mark_passed()

    def test_all_modules_cli_contract(self):
        """驗證 core 模組自身無殘留 process(args) 且定義精確命令函式。"""
        core_cli = load_core_cli_module("_test_core_cli_contract")
        self.assertFalse(hasattr(core_cli, "process"), "core cli still defines legacy process()!")
        self.assertTrue(callable(getattr(core_cli, "status", None)))
        self.assertTrue(callable(getattr(core_cli, "install", None)))
        self.assertTrue(callable(getattr(core_cli, "config_inspect", None)))
        self.assertTrue(callable(getattr(core_cli, "config_unset", None)))
        self.mark_passed()

    def test_symmetric_lifecycle_hooks(self):
        """驗證 pre_cli_dispatch / post_cli_dispatch Hook 於正常與各種提前返回/異常路徑下皆對稱觸發。"""
        # 1. Normal execution
        with patch("core.events.broadcast") as mock_broadcast:
            with patch("core.commands.dispatcher._find_module_cli", return_value="/fake/cli.py"):
                fake_mod = MagicMock()
                fake_mod.my_cmd.return_value = 0
                with patch.dict("core.commands.dispatcher._MODULE_CACHE", {"/fake/cli.py": fake_mod}):
                    cmd_spec = CommandSpec(name="my_cmd")
                    ret = dispatch_local("fake_mod", "my_cmd", [], cmd_spec, "/fake/root")

            self.assertEqual(ret, 0)
            calls = [c[0][0] for c in mock_broadcast.call_args_list]
            self.assertEqual(calls, ["pre_cli_dispatch", "post_cli_dispatch"])

        # 2. OptionResolutionError early return
        req_spec = CommandSpec(
            name="my_cmd",
            args={"target": ArgSpec(name="target", required=True)},
        )
        with patch("core.events.broadcast") as mock_bc_opt, redirect_stdout(io.StringIO()):
            ret_opt = dispatch_local("fake_mod", "my_cmd", [], req_spec, "/fake/root")
        self.assertEqual(ret_opt, 1)
        self.assertEqual([c[0][0] for c in mock_bc_opt.call_args_list], ["pre_cli_dispatch", "post_cli_dispatch"])

        # 3. Missing scripts/cli.py early return
        with patch("core.events.broadcast") as mock_bc_missing, \
             patch("core.commands.dispatcher._find_module_cli", return_value=None), \
             redirect_stdout(io.StringIO()):
            ret_missing = dispatch_local("fake_mod", "my_cmd", [], CommandSpec(name="my_cmd"), "/fake/root")
        self.assertEqual(ret_missing, 1)
        self.assertEqual([c[0][0] for c in mock_bc_missing.call_args_list], ["pre_cli_dispatch", "post_cli_dispatch"])

        # 4. SyntaxError during module load
        with tempfile.TemporaryDirectory() as tmp_dir:
            cli_dir = os.path.join(tmp_dir, ".modules", "sym-broken", "scripts")
            os.makedirs(cli_dir, exist_ok=True)
            with open(os.path.join(cli_dir, "cli.py"), "w", encoding="utf-8") as f:
                f.write("def broken(:\n")
            with patch("core.events.broadcast") as mock_bc_syn, redirect_stdout(io.StringIO()):
                ret_syn = dispatch_local("sym-broken", "run", [], CommandSpec(name="run"), tmp_dir)
            self.assertEqual(ret_syn, 1)
            self.assertEqual([c[0][0] for c in mock_bc_syn.call_args_list], ["pre_cli_dispatch", "post_cli_dispatch"])

        # 5. RuntimeError or SystemExit raised by handler
        for exc_to_raise, expected_rc in ((RuntimeError("boom"), 1), (SystemExit(3), 3)):
            with patch("core.events.broadcast") as mock_bc_exc, \
                 patch("core.commands.dispatcher._find_module_cli", return_value="/fake/exc_cli.py"), \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exc_mod = MagicMock()
                exc_mod.my_cmd.side_effect = exc_to_raise
                with patch.dict("core.commands.dispatcher._MODULE_CACHE", {"/fake/exc_cli.py": exc_mod}):
                    rc_exc = dispatch_local("fake_mod", "my_cmd", [], CommandSpec(name="my_cmd"), "/fake/root")
            self.assertEqual(rc_exc, expected_rc)
            self.assertEqual([c[0][0] for c in mock_bc_exc.call_args_list], ["pre_cli_dispatch", "post_cli_dispatch"])

        self.mark_passed()

    def test_unknown_cmd_fuzzy_suggest(self):
        """驗證未知指令返回退出碼 1 並提供模糊拼寫建議。"""
        f_out = io.StringIO()
        with redirect_stdout(f_out):
            ret = dispatch(["stauts"])
        self.assertEqual(ret, 1)
        out = f_out.getvalue()
        self.assertIn("Unknown command or module 'stauts'", out)
        self.assertIn("Did you mean 'status'?", out)
        self.mark_passed()

    def test_orthogonal_group_conflict(self):
        """驗證同正交群組多選衝突：拋出 MutualExclusionError。"""
        cmd_spec = CommandSpec(
            name="build",
            groups={"mode": ["fast", "slow"]},
            canonical_options={
                "fast": OptionSpec(canonical_name="fast", group_name="mode"),
                "slow": OptionSpec(canonical_name="slow", group_name="mode"),
            },
            options={
                "fast": OptionSpec(canonical_name="fast", group_name="mode"),
                "slow": OptionSpec(canonical_name="slow", group_name="mode"),
            }
        )
        with self.assertRaises(MutualExclusionError) as ctx:
            OptionResolver.resolve(cmd_spec, ["--fast", "--slow"])
        self.assertIn("EC-02", str(ctx.exception))
        self.mark_passed()

    def test_missing_option_value(self):
        """驗證帶參 Option 缺少參數值時拋出 MissingValueError。"""
        cmd_spec = CommandSpec(
            name="get",
            canonical_options={
                "provider": OptionSpec(canonical_name="provider", args={"url": ArgSpec(name="url")}),
            },
            options={
                "provider": OptionSpec(canonical_name="provider", args={"url": ArgSpec(name="url")}),
            }
        )
        with self.assertRaises(MissingValueError) as ctx:
            OptionResolver.resolve(cmd_spec, ["--provider"])
        self.assertIn("EC-03", str(ctx.exception))
        self.mark_passed()

    def test_hot_dispatch_fallback(self):
        """驗證 Server Worker 熱派發通訊異常時透明降級為本地冷派發。"""
        with patch("core.commands.dispatcher._try_hot_dispatch", return_value=None):
            with patch("core.commands.dispatcher.dispatch_local", return_value=42) as mock_local:
                with patch("core.commands.dispatcher._load_registry") as mock_reg_loader:
                    reg = CommandsRegistry()
                    reg.register_module("test-mod", {
                        "cmd": {
                            "run": {"server_compatible": True}
                        }
                    })
                    mock_reg_loader.return_value = reg
                    ret = dispatch(["test-mod", "run"])
                    self.assertEqual(ret, 42)
                    mock_local.assert_called_once()
        self.mark_passed()

    def test_missing_entrypoint_contract(self):
        """驗證目標模組無精確函式亦無 process 接口時返回退出碼 127。"""
        fake_mod = MagicMock(spec=[])
        with patch("core.commands.dispatcher._find_module_cli", return_value="/fake/cli.py"):
            with patch.dict("core.commands.dispatcher._MODULE_CACHE", {"/fake/cli.py": fake_mod}):
                cmd_spec = CommandSpec(name="ghost_cmd")
                f_out = io.StringIO()
                with redirect_stdout(f_out):
                    ret = dispatch_local("fake_mod", "ghost_cmd", [], cmd_spec, "/fake/root")
        self.assertEqual(ret, 127)
        self.assertIn("EC-05", f_out.getvalue())
        self.mark_passed()

    def test_module_alias_conflict(self):
        """驗證不同模組宣告重複 module_alias 時拋出衝突異常。"""
        reg = CommandsRegistry()
        reg.register_module("mod_a", {"module_alias": ["shared_alias"]})
        with self.assertRaises(ValueError) as ctx:
            reg.register_module("mod_b", {"module_alias": ["shared_alias"]})
        self.assertIn("EC-06", str(ctx.exception))
        self.mark_passed()

    def test_invalid_choice_error(self):
        """驗證傳入非法 choice 值時拋出 InvalidChoiceError。"""
        cmd_spec = CommandSpec(
            name="deploy",
            args={
                "env": ArgSpec(name="env", required=True, choice=["dev", "prod"])
            }
        )
        with self.assertRaises(InvalidChoiceError) as ctx:
            OptionResolver.resolve(cmd_spec, ["staging"])
        self.assertIn("EC-07", str(ctx.exception))
        self.assertIn("dev | prod", str(ctx.exception))
        self.mark_passed()

    def test_missing_required_argument(self):
        """驗證缺少必填位置參數時拋出 MissingArgumentError。"""
        cmd_spec = CommandSpec(
            name="install",
            args={
                "module": ArgSpec(name="module", required=True)
            }
        )
        with self.assertRaises(MissingArgumentError) as ctx:
            OptionResolver.resolve(cmd_spec, [])
        self.assertIn("EC-08", str(ctx.exception))
        self.assertIn("module", str(ctx.exception))
        self.mark_passed()

    def test_dispatch_performance(self):
        """驗證 core.commands 模組載入效能 <= 5ms。"""
        start_t = time.perf_counter()
        _ = core.commands
        _ = core.commands.dispatch
        duration_ms = (time.perf_counter() - start_t) * 1000.0
        self.assertLessEqual(duration_ms, 5.0)
        self.mark_passed()

    def test_recursive_subcommand_tree(self):
        """驗證同構遞迴指令樹解析、走訪與子命令 Help 渲染。"""
        raw_schema = {
            "cmd": {
                "group": {
                    "description": "Group command",
                    "tier": "safe",
                    "cmd": {
                        "sub_a": {
                            "description": "Sub A command",
                            "tier": "safe",
                            "args": {
                                "param": {"description": "Param", "required": True}
                            }
                        },
                        "sub_b": {
                            "description": "Sub B command",
                            "tier": "safe"
                        }
                    }
                }
            }
        }
        reg = CommandsRegistry()
        reg.register_module("test_tree", raw_schema)

        path, spec, rem = reg.resolve_command_path("test_tree", ["group", "sub_a", "val_123"])
        self.assertEqual(path, ["group", "sub_a"])
        self.assertIsNotNone(spec)
        self.assertEqual(spec.name, "sub_a")
        self.assertEqual(rem, ["val_123"])

        path2, spec2, rem2 = reg.resolve_command_path("test_tree", ["group"])
        self.assertEqual(path2, ["group"])
        self.assertIsNotNone(spec2)
        self.assertEqual(spec2.name, "group")
        self.assertIn("sub_a", spec2.cmd)
        self.assertEqual(rem2, [])

        cmd_help = HelpRenderer.render_cmd_help("test_tree", "group", spec2)
        self.assertIn("AVAILABLE SUBCOMMANDS:", cmd_help)
        self.assertIn("sub_a <param>", cmd_help)
        self.assertIn("sub_b", cmd_help)
        self.mark_passed()

    def test_maybe_auto_spawn_server_auto_spawn_disabled(self):
        """驗證 auto_spawn: false 時 _maybe_auto_spawn_server 靜默跳過無輸出且不拉起。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            server_mod = os.path.join(tmp_dir, ".modules", "server")
            os.makedirs(server_mod, exist_ok=True)
            cfg_dir = os.path.join(tmp_dir, "config", "server")
            os.makedirs(cfg_dir, exist_ok=True)
            cfg_file = os.path.join(cfg_dir, "config.project.json")
            with open(cfg_file, "w", encoding="utf-8") as f:
                f.write('{"enable": true, "auto_spawn": false}')

            clean_env = {k: v for k, v in os.environ.items() if k not in ("YSCB_TESTING", "YSCB_TEST_SANDBOX")}
            stderr_buf = io.StringIO()
            with patch.dict(os.environ, clean_env, clear=True):
                with patch("core.commands.dispatcher.spawn_detached") as mock_spawn:
                    with patch("core.commands.dispatcher.can_spawn_background_daemon") as mock_probe:
                        with redirect_stderr(stderr_buf):
                            dispatcher._maybe_auto_spawn_server(tmp_dir, tmp_dir)
                        mock_probe.assert_not_called()
                        mock_spawn.assert_not_called()
                        self.assertEqual(stderr_buf.getvalue(), "")

        self.mark_passed()

    def test_maybe_auto_spawn_server_probe_false_warning(self):
        """驗證探針判定 False 時輸出 stderr 警告與 IDE Agent 常駐指引，且不拉起。"""
        dispatcher._AUTO_SPAWN_WARNED = False
        with tempfile.TemporaryDirectory() as tmp_dir:
            server_mod = os.path.join(tmp_dir, ".modules", "server")
            os.makedirs(server_mod, exist_ok=True)
            cfg_dir = os.path.join(tmp_dir, "config", "server")
            os.makedirs(cfg_dir, exist_ok=True)
            cfg_file = os.path.join(cfg_dir, "config.project.json")
            with open(cfg_file, "w", encoding="utf-8") as f:
                f.write('{"enable": true, "auto_spawn": true}')

            clean_env = {k: v for k, v in os.environ.items() if k not in ("YSCB_TESTING", "YSCB_TEST_SANDBOX")}
            stderr_buf = io.StringIO()
            with patch.dict(os.environ, clean_env, clear=True):
                with patch("core.commands.dispatcher.spawn_detached") as mock_spawn:
                    with patch("core.commands.dispatcher.can_spawn_background_daemon", return_value=False):
                        with redirect_stderr(stderr_buf):
                            dispatcher._maybe_auto_spawn_server(tmp_dir, tmp_dir)
                        mock_spawn.assert_not_called()
                        out = stderr_buf.getvalue()
                        self.assertIn("[BLOCKER] YSCB SERVER DAEMON MANDATORY ACTION REQUIRED", out)
                        self.assertIn("auto_spawn", out)
                        self.assertIn("AGENT", out)
                        self.assertIn("server start --console", out)
                        self.assertIn("方案 A", out)
                        self.assertIn("方案 B", out)
                        self.assertIn("方案 C", out)
                        self.assertIn("(不推薦)", out)

        self.mark_passed()

    def test_maybe_auto_spawn_server_warning_debounce(self):
        """驗證 stderr 警告在單次進程內具備防洗頻抑制，重複調用僅警告一次。"""
        dispatcher._AUTO_SPAWN_WARNED = False
        with tempfile.TemporaryDirectory() as tmp_dir:
            server_mod = os.path.join(tmp_dir, ".modules", "server")
            os.makedirs(server_mod, exist_ok=True)

            clean_env = {k: v for k, v in os.environ.items() if k not in ("YSCB_TESTING", "YSCB_TEST_SANDBOX")}
            stderr_buf = io.StringIO()
            with patch.dict(os.environ, clean_env, clear=True):
                with patch("core.commands.dispatcher.spawn_detached"):
                    with patch("core.commands.dispatcher.can_spawn_background_daemon", return_value=False):
                        with redirect_stderr(stderr_buf):
                            dispatcher._maybe_auto_spawn_server(tmp_dir, tmp_dir)
                            first_out = stderr_buf.getvalue()
                            dispatcher._maybe_auto_spawn_server(tmp_dir, tmp_dir)
                            second_out = stderr_buf.getvalue()

                        self.assertEqual(first_out, second_out)
                        self.assertEqual(second_out.count("[BLOCKER] YSCB SERVER DAEMON MANDATORY ACTION REQUIRED"), 1)

        self.mark_passed()

    def test_maybe_auto_spawn_server_probe_true_spawns(self):
        """驗證探針判定 True 時正常呼叫 spawn_detached。"""
        dispatcher._AUTO_SPAWN_WARNED = False
        with tempfile.TemporaryDirectory() as tmp_dir:
            server_mod = os.path.join(tmp_dir, ".modules", "server")
            os.makedirs(server_mod, exist_ok=True)

            clean_env = {k: v for k, v in os.environ.items() if k not in ("YSCB_TESTING", "YSCB_TEST_SANDBOX")}
            with patch.dict(os.environ, clean_env, clear=True):
                with patch("core.commands.dispatcher.spawn_detached") as mock_spawn:
                    with patch("core.commands.dispatcher.can_spawn_background_daemon", return_value=True):
                        dispatcher._maybe_auto_spawn_server(tmp_dir, tmp_dir)
                        mock_spawn.assert_called_once()

        self.mark_passed()

    def test_hot_dispatch_subcommand_payload_and_stream(self):
        """驗證 _try_hot_dispatch 傳遞完整子指令路徑 Token 清單、處理串流輸出與斷線降級。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_srv = os.path.join(tmp_dir, ".cache", "server")
            os.makedirs(cache_srv, exist_ok=True)
            with open(os.path.join(cache_srv, "daemon.json"), "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "port": 59999, "token": "test_token", "root": tmp_dir}, f)

            captured_payload = {}
            stream_lines = (
                json.dumps({"type": "terminal_stream", "stream": "stdout", "text": "hot_out_ok\n"}) + "\n" +
                json.dumps({"type": "terminal_stream", "stream": "stderr", "text": "hot_err_warn\n"}) + "\n" +
                json.dumps({"type": "task_finish", "exit_code": 7}) + "\n"
            ).encode("utf-8")

            class DummyResp:
                def __init__(self, data: bytes):
                    self._buf = io.BytesIO(data)

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self, n=1024):
                    return self._buf.read(n)

            def fake_urlopen(req, timeout=120.0):
                nonlocal captured_payload
                captured_payload = json.loads(req.data.decode("utf-8"))
                return DummyResp(stream_lines)

            out_buf = io.StringIO()
            err_buf = io.StringIO()
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with patch("core.commands.dispatcher.is_process_alive", return_value=True):
                    with redirect_stdout(out_buf), redirect_stderr(err_buf):
                        res = _try_hot_dispatch("core", ["uri", "resolve"], ["project://AGENTS.md"], tmp_dir)
                    self.assertEqual(res, 7)
                    self.assertEqual(captured_payload.get("module"), "core")
                    self.assertEqual(captured_payload.get("args"), ["uri", "resolve", "project://AGENTS.md"])
                    self.assertIn("hot_out_ok", out_buf.getvalue())
                    self.assertIn("hot_err_warn", err_buf.getvalue())

            with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
                with patch("core.commands.dispatcher.is_process_alive", return_value=True):
                    res_fallback = _try_hot_dispatch("core", ["uri", "resolve"], ["project://AGENTS.md"], tmp_dir)
                    self.assertIsNone(res_fallback)

        self.mark_passed()

    def test_group_unknown_subcommand_interception_and_help(self):
        """驗證群組指令無參數時渲染 HelpRenderer，傳入未知子命令時由 Dispatcher 統一攔截並回傳 1。"""
        out_buf = io.StringIO()
        with redirect_stdout(out_buf):
            ret_typo = dispatch(["uri", "reslove"])
        self.assertEqual(ret_typo, 1)
        out_str = out_buf.getvalue()
        self.assertIn("Unknown subcommand 'reslove' for command 'uri'", out_str)
        self.assertIn("Did you mean 'resolve'?", out_str)

        out_cfg_typo = io.StringIO()
        with redirect_stdout(out_cfg_typo):
            ret_cfg_typo = dispatch(["config", "lits"])
        self.assertEqual(ret_cfg_typo, 1)
        self.assertIn("Unknown subcommand 'lits' for command 'config'", out_cfg_typo.getvalue())
        self.assertIn("Did you mean 'list'?", out_cfg_typo.getvalue())

        for grp in ("config", "uri", "event"):
            grp_buf = io.StringIO()
            with redirect_stdout(grp_buf):
                ret_grp = dispatch([grp])
            self.assertEqual(ret_grp, 0)
            self.assertIn("AVAILABLE SUBCOMMANDS:", grp_buf.getvalue())

        self.mark_passed()

    def test_option_resolver_double_dash_and_bool_false(self):
        """驗證 OptionResolver 正確解析 -- 終止符與 --flag=false 布林反轉。"""
        cmd_spec = CommandSpec(
            name="dummy",
            options={
                "flag": OptionSpec(canonical_name="flag"),
                "verbose": OptionSpec(canonical_name="verbose"),
            }
        )
        raw_tokens = ["--flag=false", "--verbose", "--", "--not-an-option", "pos_arg"]
        pos_args, resolved_opts = OptionResolver.resolve(cmd_spec, raw_tokens)

        self.assertFalse(resolved_opts["flag"].params)
        self.assertTrue(resolved_opts["verbose"].params)
        self.assertEqual(pos_args, ["--not-an-option", "pos_arg"])
        self.mark_passed()

    def test_cli_lifecycle_batch_forwarding(self):
        """驗證 scripts/cli.py 之 install、update、remove、list、status、reload、rollback、restore、event 參數解析與轉發。"""
        core_cli = load_core_cli_module("_test_core_cli_batch")

        with patch.object(core_cli, "Installer") as mock_inst_cls:
            mock_inst = MagicMock()
            mock_inst.cmd_install.return_value = 0
            mock_inst.cmd_update.return_value = 0
            mock_inst.cmd_remove.return_value = 0
            mock_inst.cmd_list.return_value = 0
            mock_inst.cmd_status.return_value = 0
            mock_inst.cmd_reload.return_value = 0
            mock_inst.cmd_rollback.return_value = 0
            mock_inst.cmd_restore.return_value = 0
            mock_inst_cls.return_value = mock_inst

            # Empty install args returns 1
            with redirect_stdout(io.StringIO()):
                self.assertEqual(core_cli.install(CmdBags(command="install", args=[], options={})), 1)

            b_inst_single = CmdBags(command="install", args=["dev@1.2.0.0"], options={"force": CmdOption("force", True)})
            self.assertEqual(core_cli.install(b_inst_single), 0)
            mock_inst.cmd_install.assert_called_with(
                "dev", version="1.2.0.0", provider=None, force=True, ignore_sha256=False
            )

            b_inst_batch = CmdBags(
                command="install",
                args=["dev@build", "agents-workflow@build"],
                options={"force": CmdOption("force", True), "ignore-sha256": CmdOption("ignore-sha256", True)},
            )
            self.assertEqual(core_cli.install(b_inst_batch), 0)
            mock_inst.cmd_install.assert_called_with(
                ["dev@build", "agents-workflow@build"], version=None, provider=None, force=True, ignore_sha256=True
            )

            b_up_all = CmdBags(command="update", args=[], options={})
            self.assertEqual(core_cli.update(b_up_all), 0)
            mock_inst.cmd_update.assert_called_with(None, provider=None, ignore_sha256=False)

            b_up_batch = CmdBags(
                command="update",
                args=["dev", "server"],
                options={"ignore-sha256": CmdOption("ignore-sha256", True)},
            )
            self.assertEqual(core_cli.update(b_up_batch), 0)
            mock_inst.cmd_update.assert_called_with(["dev", "server"], provider=None, ignore_sha256=True)

            b_rm_batch = CmdBags(
                command="remove",
                args=["dev", "server"],
                options={"purge": CmdOption("purge", True)},
            )
            self.assertEqual(core_cli.remove(b_rm_batch), 0)
            mock_inst.cmd_remove.assert_called_with(["dev", "server"], clean=False, purge=True, force=False)

            # Verify list, status, reload, rollback, restore, event forwarding
            self.assertEqual(core_cli.list(CmdBags(command="list", args=[], options={"remote": CmdOption("remote", True)})), 0)
            mock_inst.cmd_list.assert_called_once_with(remote=True, provider=None)

            self.assertEqual(core_cli.status(CmdBags(command="status", args=[], options={})), 0)
            mock_inst.cmd_status.assert_called_once()

            self.assertEqual(core_cli.reload(CmdBags(command="reload", args=[], options={})), 0)
            mock_inst.cmd_reload.assert_called_once()

            self.assertEqual(core_cli.rollback(CmdBags(command="rollback", args=["snap_1"], options={})), 0)
            mock_inst.cmd_rollback.assert_called_once_with("snap_1")

            self.assertEqual(
                core_cli.restore(CmdBags(command="restore", args=[], options={"force": CmdOption("force", True)})),
                0,
            )
            mock_inst.cmd_restore.assert_called_once_with(force=True, provider=None, ignore_sha256=False)

            with redirect_stdout(io.StringIO()):
                self.assertEqual(core_cli.event(CmdBags(command="event", args=["unknown_sub"], options={})), 1)

        self.mark_passed()

    def test_read_server_spawn_config_strict_layering(self):
        """驗證 _read_server_spawn_config 預設 strict=False，local 覆寫 project，舊組態缺鍵可載入。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            default_cfg = dispatcher._read_server_spawn_config(tmp_dir)
            self.assertEqual(default_cfg, dispatcher._ServerSpawnConfig(enabled=True, auto_spawn=True, strict_hot_dispatch=False))

            cfg_dir = os.path.join(tmp_dir, "config", "server")
            cfg_local_dir = os.path.join(tmp_dir, ".config.local", "server")
            os.makedirs(cfg_dir, exist_ok=True)
            os.makedirs(cfg_local_dir, exist_ok=True)
            with open(os.path.join(cfg_dir, "config.project.json"), "w", encoding="utf-8") as f:
                f.write('{"enable": true, "auto_spawn": true}')
            self.assertFalse(dispatcher._read_server_spawn_config(tmp_dir).strict_hot_dispatch)

            with open(os.path.join(cfg_local_dir, "config.local.json"), "w", encoding="utf-8") as f:
                f.write('{"strict_hot_dispatch": true, "auto_spawn": false}')
            layered = dispatcher._read_server_spawn_config(tmp_dir)
            self.assertTrue(layered.strict_hot_dispatch)
            self.assertFalse(layered.auto_spawn)
            self.assertTrue(layered.enabled)
        self.mark_passed()

    def test_blocker_advisory_vs_strict_wording(self):
        """驗證 advisory 文案宣告冷派發兜底；strict 文案宣告已阻斷且不含兜底字樣。"""
        adv_buf, strict_buf = io.StringIO(), io.StringIO()
        with redirect_stderr(adv_buf):
            dispatcher._print_agent_daemon_blocker()
        with redirect_stderr(strict_buf):
            dispatcher._print_agent_daemon_blocker(strict=True)
        adv, strict = adv_buf.getvalue(), strict_buf.getvalue()
        for out in (adv, strict):
            self.assertIn("[BLOCKER] YSCB SERVER DAEMON MANDATORY ACTION REQUIRED", out)
            self.assertIn("YSCB_FORCE_DAEMON=1", out)
        self.assertIn("冷派發兜底完成", adv)
        self.assertNotIn("已阻斷執行", adv)
        self.assertIn("strict_hot_dispatch=true", strict)
        self.assertIn("已阻斷執行 (exit 1)", strict)
        self.assertNotIn("冷派發兜底完成", strict)
        self.mark_passed()

    def test_strict_mode_blocks_cold_dispatch(self):
        """驗證 strict 模式下熱派發失敗回傳 1 且不冷派發；server_compatible=false 指令與 enable=false 照常冷派發。"""
        strict_cfg = dispatcher._ServerSpawnConfig(enabled=True, auto_spawn=True, strict_hot_dispatch=True)
        disabled_cfg = dispatcher._ServerSpawnConfig(enabled=False, auto_spawn=True, strict_hot_dispatch=True)
        reg = CommandsRegistry()
        reg.register_module("test-mod", {"cmd": {"run": {"server_compatible": True}, "cold": {"server_compatible": False}}})
        dispatcher._AUTO_SPAWN_WARNED = False
        with patch("core.commands.dispatcher._load_registry", return_value=reg), \
             patch("core.commands.dispatcher._hot_dispatch_attempt", return_value=dispatcher._HotDispatchResult(None, False)), \
             patch("core.commands.dispatcher.can_spawn_background_daemon", return_value=False), \
             patch("core.commands.dispatcher.dispatch_local", return_value=42) as mock_local:
            err_buf = io.StringIO()
            with patch("core.commands.dispatcher._read_server_spawn_config", return_value=strict_cfg), redirect_stderr(err_buf):
                ret_strict = dispatch(["test-mod", "run"])
                ret_cold = dispatch(["test-mod", "cold"])
            self.assertEqual(ret_strict, 1)
            self.assertIn("已阻斷執行 (exit 1)", err_buf.getvalue())
            self.assertEqual(ret_cold, 42)
            self.assertEqual(mock_local.call_count, 1)

            with patch("core.commands.dispatcher._read_server_spawn_config", return_value=disabled_cfg):
                ret_disabled = dispatch(["test-mod", "run"])
            self.assertEqual(ret_disabled, 42)
            self.assertEqual(mock_local.call_count, 2)
        self.mark_passed()

    def test_strict_mode_auto_spawn_then_retry_hot(self):
        """驗證 strict 模式可常駐時 auto-spawn、記錄 spawn 探針，待 daemon 活躍後重試熱派發一次成功。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.makedirs(os.path.join(tmp_dir, ".modules", "server"), exist_ok=True)
            state_dir = os.path.join(tmp_dir, ".cache", "server")
            cfg = dispatcher._ServerSpawnConfig(enabled=True, auto_spawn=True, strict_hot_dispatch=True)

            def fake_spawn(cmd, cwd=None):
                os.makedirs(state_dir, exist_ok=True)
                with open(os.path.join(state_dir, "daemon.json"), "w", encoding="utf-8") as f:
                    f.write("{}")
                return 4242

            with patch("core.commands.dispatcher._read_server_spawn_config", return_value=cfg), \
                 patch("core.commands.dispatcher.can_spawn_background_daemon", return_value=True), \
                 patch("core.commands.dispatcher._is_server_daemon_active_or_locked", return_value=False), \
                 patch("core.commands.dispatcher.spawn_detached", side_effect=fake_spawn) as mock_spawn, \
                 patch("core.commands.dispatcher.daemon_probe.record_spawn") as mock_record, \
                 patch("core.commands.dispatcher.time.sleep"), \
                 patch("core.commands.dispatcher._hot_dispatch_attempt", side_effect=[dispatcher._HotDispatchResult(None, False), dispatcher._HotDispatchResult(0, True)]) as mock_hot:
                ret = dispatcher._strict_hot_dispatch_or_block("test-mod", ["run"], [], tmp_dir, tmp_dir)
            self.assertEqual(ret, 0)
            mock_spawn.assert_called_once()
            mock_record.assert_called_once_with(tmp_dir, 4242)
            self.assertEqual(mock_hot.call_count, 2)

            err_buf = io.StringIO()
            with patch("core.commands.dispatcher._read_server_spawn_config", return_value=cfg), \
                 patch("core.commands.dispatcher._STRICT_SPAWN_WAIT_SEC", 0.05), \
                 patch("core.commands.dispatcher.time.sleep"), \
                 patch("core.commands.dispatcher.can_spawn_background_daemon", return_value=True), \
                 patch("core.commands.dispatcher._is_server_daemon_active_or_locked", return_value=True), \
                 patch("core.commands.dispatcher.spawn_detached") as mock_spawn2, \
                 patch("core.commands.dispatcher._hot_dispatch_attempt", return_value=dispatcher._HotDispatchResult(None, False)), \
                 redirect_stderr(err_buf):
                ret_fail = dispatcher._strict_hot_dispatch_or_block("test-mod", ["run"], [], tmp_dir, tmp_dir)
            self.assertEqual(ret_fail, 1)
            mock_spawn2.assert_not_called()
            self.assertIn("strict_hot_dispatch=true", err_buf.getvalue())
        self.mark_passed()

    def test_auto_spawn_records_probe_and_passes_root(self):
        """驗證 auto-spawn 以 yscb_root 呼叫能力判定並將 spawn PID 寫入 spawn_probe.json。"""
        dispatcher._AUTO_SPAWN_WARNED = False
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.makedirs(os.path.join(tmp_dir, ".modules", "server"), exist_ok=True)
            clean_env = {k: v for k, v in os.environ.items() if k not in ("YSCB_TESTING", "YSCB_TEST_SANDBOX")}
            with patch.dict(os.environ, clean_env, clear=True):
                with patch("core.commands.dispatcher.spawn_detached", return_value=31337), \
                     patch("core.commands.dispatcher.can_spawn_background_daemon", return_value=True) as mock_can:
                    dispatcher._maybe_auto_spawn_server(tmp_dir, tmp_dir)
            mock_can.assert_called_once_with(yscb_root=tmp_dir)
            with open(os.path.join(tmp_dir, daemon_probe.PROBE_REL_PATH), "r", encoding="utf-8") as f:
                data = json.load(f)
            entry = data[daemon_probe.env_fingerprint()]
            self.assertEqual(entry["pid"], 31337)
            self.assertFalse(entry["clean_exit"])
        self.mark_passed()

    def test_exec_module_failure_is_reported(self):
        """驗證 CLI 載入期 SyntaxError 回傳 1、印出錯誤類型並移除半初始化模組，不寫入快取。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cli_dir = os.path.join(tmp_dir, ".modules", "broken-mod", "scripts")
            os.makedirs(cli_dir, exist_ok=True)
            cli_path = os.path.join(cli_dir, "cli.py")
            with open(cli_path, "w", encoding="utf-8") as f:
                f.write("def run(cmd_bags):\n    return 0\ndef broken(:\n")
            out_buf = io.StringIO()
            orig_path = list(sys.path)
            try:
                with redirect_stdout(out_buf):
                    ret = dispatch_local("broken-mod", "run", [], CommandSpec(name="run"), tmp_dir)
            finally:
                sys.path[:] = orig_path
            self.assertEqual(ret, 1)
            self.assertIn("[yscb] Error loading CLI for 'broken-mod': SyntaxError:", out_buf.getvalue())
            self.assertNotIn("yscb_mod_broken_mod_cli", sys.modules)
            self.assertNotIn(os.path.normpath(cli_path), dispatcher._MODULE_CACHE)
        self.mark_passed()

    def test_strict_failed_after_send_never_retries(self):
        """驗證 strict 模式請求已送達後失敗（逾時/重置/搶占）回傳 1、不重試、不 spawn、不冷派發，防重複執行。"""
        cfg = dispatcher._ServerSpawnConfig(enabled=True, auto_spawn=True, strict_hot_dispatch=True)
        err_buf = io.StringIO()
        with patch("core.commands.dispatcher._read_server_spawn_config", return_value=cfg), \
             patch("core.commands.dispatcher.can_spawn_background_daemon", return_value=True), \
             patch("core.commands.dispatcher.spawn_detached") as mock_spawn, \
             patch("core.commands.dispatcher.dispatch_local") as mock_local, \
             patch("core.commands.dispatcher._hot_dispatch_attempt", return_value=dispatcher._HotDispatchResult(None, True)) as mock_hot, \
             redirect_stderr(err_buf):
            ret = dispatcher._strict_hot_dispatch_or_block("test-mod", ["run"], [], "/fake", "/fake")
        self.assertEqual(ret, 1)
        self.assertEqual(mock_hot.call_count, 1)
        mock_spawn.assert_not_called()
        mock_local.assert_not_called()
        self.assertIn("Not retried to avoid double execution", err_buf.getvalue())
        self.assertNotIn("[BLOCKER]", err_buf.getvalue())

        with tempfile.TemporaryDirectory() as tmp_dir:
            os.makedirs(os.path.join(tmp_dir, ".modules", "server"), exist_ok=True)
            os.makedirs(os.path.join(tmp_dir, ".cache", "server"), exist_ok=True)
            with open(os.path.join(tmp_dir, ".cache", "server", "daemon.json"), "w", encoding="utf-8") as f:
                f.write("{}")
            with patch("core.commands.dispatcher._read_server_spawn_config", return_value=cfg), \
                 patch("core.commands.dispatcher.can_spawn_background_daemon", return_value=True), \
                 patch("core.commands.dispatcher._is_server_daemon_active_or_locked", return_value=True), \
                 patch("core.commands.dispatcher._hot_dispatch_attempt", side_effect=[dispatcher._HotDispatchResult(None, False), dispatcher._HotDispatchResult(None, True)]) as mock_hot2, \
                 redirect_stderr(io.StringIO()):
                ret2 = dispatcher._strict_hot_dispatch_or_block("test-mod", ["run"], [], tmp_dir, tmp_dir)
        self.assertEqual(ret2, 1)
        self.assertEqual(mock_hot2.call_count, 2)
        self.mark_passed()

    def test_hot_dispatch_attempt_classifies_unreachable_vs_accepted(self):
        """驗證無 state/連線拒絕/HTTP 錯誤判為未送達；串流中途失敗或無 task_finish 判為已送達且 _try_hot_dispatch 回傳 1 不降級冷派發。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.assertEqual(dispatcher._hot_dispatch_attempt("m", ["c"], [], tmp_dir), dispatcher._HotDispatchResult(None, False))
            state_dir = os.path.join(tmp_dir, ".cache", "server")
            os.makedirs(state_dir, exist_ok=True)
            with open(os.path.join(state_dir, "daemon.json"), "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "port": 1, "token": "t", "root": tmp_dir}, f)

            refused = urllib.error.URLError(ConnectionRefusedError(111, "refused"))
            http_err = urllib.error.HTTPError("http://x", 403, "Forbidden", {}, None)
            timeout_err = urllib.error.URLError(TimeoutError("timed out"))
            cases = [(refused, False), (http_err, False), (timeout_err, True), (ConnectionResetError(), True)]
            for exc, accepted in cases:
                with patch("core.commands.dispatcher.urllib.request.urlopen", side_effect=exc):
                    res = dispatcher._hot_dispatch_attempt("m", ["c"], [], tmp_dir)
                self.assertIsNone(res.exit_code)
                self.assertEqual(res.accepted, accepted, repr(exc))

            class _Resp(io.BytesIO):
                def __enter__(self):
                    return self

            mid_stream = MagicMock()
            mid_stream.__enter__.return_value = mid_stream
            mid_stream.read.side_effect = ConnectionResetError()
            with patch("core.commands.dispatcher.urllib.request.urlopen", return_value=mid_stream):
                self.assertEqual(dispatcher._hot_dispatch_attempt("m", ["c"], [], tmp_dir), dispatcher._HotDispatchResult(None, True))
                self.assertEqual(dispatcher._try_hot_dispatch("m", ["c"], [], tmp_dir), 1)

            no_finish = _Resp(b'{"type": "terminal_stream", "text": "x", "stream": "stdout"}\n')
            with patch("core.commands.dispatcher.urllib.request.urlopen", return_value=no_finish), redirect_stdout(io.StringIO()):
                self.assertEqual(dispatcher._hot_dispatch_attempt("m", ["c"], [], tmp_dir), dispatcher._HotDispatchResult(None, True))

            ok = _Resp(b'{"type": "task_finish", "exit_code": 3}\n')
            with patch("core.commands.dispatcher.urllib.request.urlopen", return_value=ok):
                self.assertEqual(dispatcher._hot_dispatch_attempt("m", ["c"], [], tmp_dir), dispatcher._HotDispatchResult(3, True))
        self.mark_passed()

    def test_try_hot_dispatch_accepted_never_falls_back_to_cold(self):
        """驗證 _try_hot_dispatch 於 accepted=True (含 exit_code=1 或中途 socket.timeout) 時直接回傳退出碼/1，僅於 accepted=False 時回傳 None。"""
        with patch(
            "core.commands.dispatcher._hot_dispatch_attempt",
            return_value=dispatcher._HotDispatchResult(exit_code=1, accepted=True),
        ):
            self.assertEqual(dispatcher._try_hot_dispatch("m", ["c"], [], "/fake"), 1)

        with patch(
            "core.commands.dispatcher._hot_dispatch_attempt",
            return_value=dispatcher._HotDispatchResult(exit_code=None, accepted=True),
        ):
            self.assertEqual(dispatcher._try_hot_dispatch("m", ["c"], [], "/fake"), 1)

        with patch(
            "core.commands.dispatcher._hot_dispatch_attempt",
            return_value=dispatcher._HotDispatchResult(exit_code=None, accepted=False),
        ):
            self.assertIsNone(dispatcher._try_hot_dispatch("m", ["c"], [], "/fake"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = os.path.join(tmp_dir, ".cache", "server")
            os.makedirs(state_dir, exist_ok=True)
            with open(os.path.join(state_dir, "daemon.json"), "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "port": 1, "token": "t", "root": tmp_dir}, f)
            with patch("core.commands.dispatcher.urllib.request.urlopen", side_effect=socket.timeout("timed out")):
                self.assertEqual(dispatcher._try_hot_dispatch("m", ["c"], [], tmp_dir), 1)
        self.mark_passed()

    def test_hot_dispatch_surfaces_task_finish_error(self):
        """驗證 task_finish 非零且帶 error 時輸出 '[yscb] Error: <error>' 至 stderr 並納入 error hint；成功時不輸出。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = os.path.join(tmp_dir, ".cache", "server")
            os.makedirs(state_dir, exist_ok=True)
            with open(os.path.join(state_dir, "daemon.json"), "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "port": 1, "token": "t", "root": tmp_dir}, f)

            fail = io.BytesIO(b'{"type": "task_finish", "exit_code": 1, "error": "Worker terminated by restart/stop"}\n')
            err_buf = io.StringIO()
            with patch("core.commands.dispatcher.urllib.request.urlopen", return_value=fail), redirect_stderr(err_buf):
                res = dispatcher._hot_dispatch_attempt("m", ["c"], [], tmp_dir)
            self.assertEqual(res, dispatcher._HotDispatchResult(1, True))
            self.assertIn("[yscb] Error: Worker terminated by restart/stop", err_buf.getvalue())
            self.assertIn("Worker terminated by restart/stop", dispatcher._LAST_DISPATCH_ERROR_HINT)

            ok = io.BytesIO(b'{"type": "task_finish", "exit_code": 0, "error": "ignored"}\n')
            ok_buf = io.StringIO()
            with patch("core.commands.dispatcher.urllib.request.urlopen", return_value=ok), redirect_stderr(ok_buf):
                self.assertEqual(dispatcher._hot_dispatch_attempt("m", ["c"], [], tmp_dir).exit_code, 0)
            self.assertEqual(ok_buf.getvalue(), "")
        self.mark_passed()

    def test_negative_number_arguments_and_proxy_bypass(self):
        """驗證 OptionResolver 負數參數支援，以及 _hot_dispatch_attempt 對 URLError 斷線異常之 accepted 判定。"""
        spec = CommandSpec(
            name="calc",
            description="calc test",
            args={"x": ArgSpec(name="x", description="x", required=True)},
            options={
                "offset": OptionSpec(
                    canonical_name="offset",
                    group_name="default",
                    description="offset",
                    args={"val": ArgSpec(name="val", description="val", required=True)},
                )
            },
        )
        pos, opts = OptionResolver.resolve(spec, ["--offset", "-5", "-3.14"])
        self.assertEqual(pos, ["-3.14"])
        self.assertEqual(opts["offset"].params, "-5")

        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = os.path.join(tmp_dir, ".cache", "server")
            os.makedirs(state_dir, exist_ok=True)
            with open(os.path.join(state_dir, "daemon.json"), "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "port": 1, "token": "t", "root": tmp_dir}, f)

            for err_reason in (ConnectionResetError("reset"), BrokenPipeError("broken")):
                with patch(
                    "core.commands.dispatcher._open_localhost_no_proxy",
                    side_effect=urllib.error.URLError(err_reason),
                ):
                    res = dispatcher._hot_dispatch_attempt("m", ["c"], [], tmp_dir)
                    self.assertTrue(res.accepted)
                    self.assertIsNone(res.exit_code)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
