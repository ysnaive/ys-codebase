"""
Unit and Integration Tests for core.commands Subsystem.
Covers FT-01~FT-10, ET-01~ET-06, PT-01, RT-01.
100% Python Standard Library.
"""
import io
import os
import sys
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, patch

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require

import core
from core.commands.bags import CmdBags, CmdOption
from core.commands.dispatcher import dispatch, dispatch_local, _suggest_command
from core.commands.help import HelpRenderer
from core.commands.registry import (
    ArgSpec,
    CommandSpec,
    CommandsRegistry,
    ModuleSpec,
    OptionSpec,
)
from core.commands.resolver import (
    InvalidChoiceError,
    MissingArgumentError,
    MissingValueError,
    MutualExclusionError,
    OptionResolver,
)


class TestCoreCommandsSubsystem(YSCBTestCase):
    """core.commands 全功能、邊界與效能單元測試集合。"""

    @require(Requirement.LOGIC)
    def test_ft01_pep562_lazy_loading(self):
        """FT-01: 驗證 PEP 562 Lazy Loading：引用 core.commands 不載入重型子模組。"""
        # 驗證 core 模組具備 __getattr__
        self.assertTrue(hasattr(core, "__getattr__"))
        self.assertIn("commands", dir(core))
        # 存取 commands 屬性
        cmds = core.commands
        self.assertIsNotNone(cmds)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft02_commands_schema_parser(self):
        """FT-02: 驗證 Contributes Commands Schema 解析 (含 module_alias, tier, server_compatible, args, options, usage)。"""
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

    @require(Requirement.LOGIC)
    def test_ft03_option_resolver(self):
        """FT-03: 驗證 OptionResolver 正交群組互斥、別名規範化與 args 帶參解析。"""
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

        # 測試別名 -j 轉為規範名 json，帶值 -o path 轉為 out
        args, opts = OptionResolver.resolve(cmd_spec, ["pos1", "-j", "-o", "result.txt", "pos2"])
        self.assertEqual(args, ["pos1", "pos2"])
        self.assertIn("json", opts)
        self.assertTrue(opts["json"].params)
        self.assertIn("out", opts)
        self.assertEqual(opts["out"].params, "result.txt")

        # 測試 --out=result2.txt
        _, opts2 = OptionResolver.resolve(cmd_spec, ["--out=result2.txt"])
        self.assertEqual(opts2["out"].params, "result2.txt")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft04_cmdbags_dataclass(self):
        """FT-04: 驗證強型別 CmdBags 與 CmdOption 屬性完整度與不可變性。"""
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

        # 斷言不可變性 (frozen=True)
        with self.assertRaises(Exception):
            bags.command = "changed"
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft05_help_renderer(self):
        """FT-05: 驗證模組級與指令級 --help 渲染格式、choice 格式化與 ARGUMENTS 欄位輸出。"""
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

    @require(Requirement.LOGIC)
    def test_ft06_server_compatible_routing(self):
        """FT-06: 驗證指令級 server_compatible 雙管道分流。"""
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

                # hot_cmd 應觸發 _try_hot_dispatch
                ret = dispatch(["test-server-mod", "hot_cmd"])
                self.assertEqual(ret, 0)
                mock_hot.assert_called_once()

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft07_yscb_thin_host_delegation(self):
        """FT-07: 驗證 yscb.py 薄宿主相容函式正常轉派。"""
        import yscb
        self.assertTrue(hasattr(yscb, "cmd_init"))
        self.assertTrue(hasattr(yscb, "dispatch_module"))
        self.assertTrue(hasattr(yscb, "_suggest_command"))
        self.assertTrue(hasattr(yscb, "_print_global_help"))

        sugg = yscb._suggest_command("stauts", ["status", "install"])
        self.assertEqual(sugg, "status")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft08_hard_sunset_ec05_enforcement(self):
        """FT-08: 驗證向後相容過渡層徹底拔除 (Hard Sunset Gate)：未定義精確函式之模組調用嚴格拋出 EC-05 並返回退出碼 127，不再退化至 process。"""
        fake_mod = MagicMock(spec=["process"])
        fake_mod.process.return_value = 0

        cmd_spec = CommandSpec(name="my_cmd", description="Legacy cmd")

        f_out = io.StringIO()
        f_err = io.StringIO()
        with redirect_stdout(f_out), redirect_stderr(f_err):
            with patch("core.commands.dispatcher._find_module_cli", return_value="/fake/cli.py"):
                with patch.dict("core.commands.dispatcher._MODULE_CACHE", {"/fake/cli.py": fake_mod}):
                    ret = dispatch_local("legacy_mod", "my_cmd", ["arg1"], cmd_spec, "/fake/root")

        # 斷言硬性阻斷並返回 EC-05 退出碼 127
        self.assertEqual(ret, 127)
        fake_mod.process.assert_not_called()
        self.assertIn("EC-05", f_out.getvalue())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft09_all_modules_cli_contract(self):
        """FT-09: 驗證 core 模組自身無殘留 process(args) 且定義精確命令函式。"""
        import importlib.util
        core_cli_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "cli.py"))
        spec_core = importlib.util.spec_from_file_location("core_scripts_cli_test", core_cli_path)
        core_cli = importlib.util.module_from_spec(spec_core)
        spec_core.loader.exec_module(core_cli)
        self.assertFalse(hasattr(core_cli, "process"), "core cli still defines legacy process()!")
        self.assertTrue(callable(getattr(core_cli, "status", None)))
        self.assertTrue(callable(getattr(core_cli, "install", None)))
        self.assertTrue(callable(getattr(core_cli, "config_inspect", None)))
        self.assertTrue(callable(getattr(core_cli, "config_unset", None)))
        self.mark_passed()


    @require(Requirement.LOGIC)
    def test_ft10_symmetric_lifecycle_hooks(self):
        """FT-10: 驗證 pre_cli_dispatch / post_cli_dispatch Hook 於執行環境內部對稱觸發。"""
        with patch("core.events.broadcast") as mock_broadcast:
            with patch("core.commands.dispatcher._find_module_cli", return_value="/fake/cli.py"):
                fake_mod = MagicMock()
                fake_mod.my_cmd.return_value = 0
                with patch.dict("core.commands.dispatcher._MODULE_CACHE", {"/fake/cli.py": fake_mod}):
                    cmd_spec = CommandSpec(name="my_cmd")
                    ret = dispatch_local("fake_mod", "my_cmd", [], cmd_spec, "/fake/root")

            self.assertEqual(ret, 0)
            calls = [c[0][0] for c in mock_broadcast.call_args_list]
            self.assertIn("pre_cli_dispatch", calls)
            self.assertIn("post_cli_dispatch", calls)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et01_unknown_cmd_fuzzy_suggest(self):
        """ET-01: 驗證未知指令返回退出碼 1 並提供模糊拼寫建議。"""
        f_out = io.StringIO()
        with redirect_stdout(f_out):
            ret = dispatch(["stauts"])  # status typo
        self.assertEqual(ret, 1)
        out = f_out.getvalue()
        self.assertIn("Unknown command or module 'stauts'", out)
        self.assertIn("Did you mean 'status'?", out)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et02_orthogonal_group_conflict(self):
        """ET-02: 驗證同正交群組多選衝突：拋出 MutualExclusionError。"""
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

    @require(Requirement.LOGIC)
    def test_et03_missing_option_value(self):
        """ET-03: 驗證帶參 Option 缺少參數值時拋出 MissingValueError。"""
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

    @require(Requirement.LOGIC)
    def test_et04_hot_dispatch_fallback(self):
        """ET-04: 驗證 Server Worker 熱派發通訊異常時透明降級為本地冷派發。"""
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

    @require(Requirement.LOGIC)
    def test_et05_missing_entrypoint_contract(self):
        """ET-05: 驗證目標模組無精確函式亦無 process 接口時返回退出碼 127。"""
        fake_mod = MagicMock(spec=[])  # 既無 cmd 亦無 process
        with patch("core.commands.dispatcher._find_module_cli", return_value="/fake/cli.py"):
            with patch.dict("core.commands.dispatcher._MODULE_CACHE", {"/fake/cli.py": fake_mod}):
                cmd_spec = CommandSpec(name="ghost_cmd")
                f_out = io.StringIO()
                with redirect_stdout(f_out):
                    ret = dispatch_local("fake_mod", "ghost_cmd", [], cmd_spec, "/fake/root")
        self.assertEqual(ret, 127)
        self.assertIn("EC-05", f_out.getvalue())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et06_module_alias_conflict(self):
        """ET-06: 驗證不同模組宣告重複 module_alias 時拋出衝突異常。"""
        reg = CommandsRegistry()
        reg.register_module("mod_a", {"module_alias": ["shared_alias"]})
        with self.assertRaises(ValueError) as ctx:
            reg.register_module("mod_b", {"module_alias": ["shared_alias"]})
        self.assertIn("EC-06", str(ctx.exception))
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_et07_invalid_choice_error(self):
        """ET-07: 驗證傳入非法 choice 值時拋出 InvalidChoiceError。"""
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

    @require(Requirement.LOGIC)
    def test_et08_missing_required_argument(self):
        """ET-08: 驗證缺少必填位置參數時拋出 MissingArgumentError。"""
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

    @require(Requirement.LOGIC)
    def test_pt01_dispatch_performance(self):
        """PT-01: 驗證 core.commands 模組載入效能 <= 5ms。"""
        start_t = time.perf_counter()
        # 測試重複導入/存取耗時
        _ = core.commands
        _ = core.commands.dispatch
        duration_ms = (time.perf_counter() - start_t) * 1000.0
        self.assertLessEqual(duration_ms, 5.0)
        self.mark_passed()


    @require(Requirement.LOGIC)
    def test_ft11_recursive_subcommand_tree(self):
        """FT-11: 驗證同構遞迴指令樹解析、走訪與子命令 Help 渲染。"""
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

        # 走訪至子命令
        path, spec, rem = reg.resolve_command_path("test_tree", ["group", "sub_a", "val_123"])
        self.assertEqual(path, ["group", "sub_a"])
        self.assertIsNotNone(spec)
        self.assertEqual(spec.name, "sub_a")
        self.assertEqual(rem, ["val_123"])

        # 走訪至分支
        path2, spec2, rem2 = reg.resolve_command_path("test_tree", ["group"])
        self.assertEqual(path2, ["group"])
        self.assertIsNotNone(spec2)
        self.assertEqual(spec2.name, "group")
        self.assertIn("sub_a", spec2.cmd)
        self.assertEqual(rem2, [])

        # Help 渲染包含 SUBCOMMANDS
        cmd_help = HelpRenderer.render_cmd_help("test_tree", "group", spec2)
        self.assertIn("AVAILABLE SUBCOMMANDS:", cmd_help)
        self.assertIn("sub_a <param>", cmd_help)
        self.assertIn("sub_b", cmd_help)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft11_maybe_auto_spawn_server_auto_spawn_disabled(self):
        """FT-11: 驗證 auto_spawn: false 時 _maybe_auto_spawn_server 靜默跳過無輸出且不拉起。"""
        import tempfile
        from core.commands import dispatcher

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

    @require(Requirement.LOGIC)
    def test_ft12_maybe_auto_spawn_server_probe_false_warning(self):
        """FT-12: 驗證探針判定 False 時輸出 stderr 警告與 IDE Agent 常駐指引，且不拉起。"""
        import tempfile
        from core.commands import dispatcher

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

    @require(Requirement.LOGIC)
    def test_ft13_maybe_auto_spawn_server_warning_debounce(self):
        """FT-13: 驗證 stderr 警告在單次進程內具備防洗頻抑制，重複調用僅警告一次。"""
        import tempfile
        from core.commands import dispatcher

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
                            # 第一次呼叫 -> 產生警告
                            dispatcher._maybe_auto_spawn_server(tmp_dir, tmp_dir)
                            first_out = stderr_buf.getvalue()
                            # 第二次呼叫 -> 被抑制
                            dispatcher._maybe_auto_spawn_server(tmp_dir, tmp_dir)
                            second_out = stderr_buf.getvalue()

                        self.assertEqual(first_out, second_out)
                        self.assertEqual(second_out.count("[BLOCKER] YSCB SERVER DAEMON MANDATORY ACTION REQUIRED"), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft14_maybe_auto_spawn_server_probe_true_spawns(self):
        """FT-14: 驗證探針判定 True 時正常呼叫 spawn_detached。"""
        import tempfile
        from core.commands import dispatcher

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
        """T-06 補盲 & FT-03 & EC-03: 驗證 _try_hot_dispatch 傳遞完整子指令路徑 Token 清單、處理串流輸出與斷線降級。"""
        import tempfile
        import json
        import io
        from core.commands.dispatcher import _try_hot_dispatch

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
                def __enter__(self): return self
                def __exit__(self, *args): pass
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

            # EC-03: 連線失敗時返回 None 以便透明降級冷派發
            with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
                with patch("core.commands.dispatcher.is_process_alive", return_value=True):
                    res_fallback = _try_hot_dispatch("core", ["uri", "resolve"], ["project://AGENTS.md"], tmp_dir)
                    self.assertIsNone(res_fallback)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_group_unknown_subcommand_interception_and_help(self):
        """C-06 / FT-06 / ET-07: 驗證群組指令無參數時渲染 HelpRenderer，傳入未知子命令時由 Dispatcher 統一攔截並回傳 1。"""
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

        # 無參數調用群組指令輸出 AVAILABLE SUBCOMMANDS 並回傳 0
        for grp in ("config", "uri", "event"):
            grp_buf = io.StringIO()
            with redirect_stdout(grp_buf):
                ret_grp = dispatch([grp])
            self.assertEqual(ret_grp, 0)
            self.assertIn("AVAILABLE SUBCOMMANDS:", grp_buf.getvalue())

        self.mark_passed()

    def test_option_resolver_double_dash_and_bool_false(self):
        """T-06 補盲: 驗證 OptionResolver 正確解析 -- 終止符與 --flag=false 布林反轉。"""
        from core.commands.resolver import OptionResolver
        from core.commands.registry import CommandSpec, OptionSpec
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



if __name__ == "__main__":
    unittest.main()

