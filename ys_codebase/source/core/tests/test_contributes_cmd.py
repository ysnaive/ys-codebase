"""
Integration tests for contributes CLI and SDK functions.
"""
import contextlib
import io
import json
import os
import tempfile
from contextlib import redirect_stdout

from dev.testing import YSCBTestCase, require, Requirement
from core import contributes, uri, vfs
from core.commands import contributes_cmd
from core.commands.bags import CmdBags, CmdOption
from tests import load_core_cli_module


@require(Requirement.ENV)
class TestContributesCmdAndSDK(YSCBTestCase):
    def test_sdk_get_format_and_list_points(self):
        """驗證 SDK get_format 與 list_points 正確讀取。"""
        core_fmt = contributes.get_format("core")
        self.assertIsNotNone(core_fmt, "core _format.json should be readable")
        self.assertIn("commands", core_fmt)
        self.assertIn("uri_schemes", core_fmt)
        self.assertIn("events", core_fmt)

        points = contributes.list_points("core")
        self.assertGreaterEqual(len(points), 3)
        pts = [p["point"] for p in points]
        self.assertIn("commands", pts)
        self.assertIn("uri_schemes", pts)
        self.assertIn("events", pts)
        self.mark_passed()

    def test_contributes_cli_list(self):
        """驗證 CLI contributes list 執行。"""
        ret = contributes_cmd.list_contributes("core")
        self.assertEqual(ret, 0)
        self.mark_passed()

    def test_contributes_cli_check_self(self):
        """驗證 CLI contributes check 執行檢驗 core.json。"""
        ret = contributes_cmd.check_contributes("core")
        self.assertEqual(ret, 0)
        self.mark_passed()

    def test_contributes_cli_format_check(self):
        """驗證 CLI contributes check --format 執行。"""
        ret = contributes_cmd.check_contributes("core", is_format_check=True)
        self.assertEqual(ret, 0)
        self.mark_passed()

    def test_contributes_aggregator_ignores_special_files(self):
        """驗證 Aggregator 聚合時排除 _ 開頭特殊檔案。"""
        aggregator = contributes.ContributesAggregator()
        merged = aggregator.scan_and_inject()
        self.assertNotIn("_format", merged)
        self.assertNotIn("_manifest", merged)
        self.assertIn("core", merged)
        self.mark_passed()

    def test_contributes_cli_dispatcher(self):
        """驗證 core scripts.cli:contributes() 分發器與未知子指令防呆。"""
        core_cli = load_core_cli_module("_test_core_cli_contributes")
        cli_contributes = core_cli.contributes

        ret = cli_contributes(CmdBags(args=[]))
        self.assertEqual(ret, 0)

        ret = cli_contributes(CmdBags(args=["list", "core"]))
        self.assertEqual(ret, 0)

        ret = cli_contributes(CmdBags(args=["check", "core"]))
        self.assertEqual(ret, 0)

        err_buf = io.StringIO()
        with contextlib.redirect_stderr(err_buf):
            ret = cli_contributes(CmdBags(args=["get", "knowledge-db", "spaces"]))
        self.assertEqual(ret, 1)
        err_msg = err_buf.getvalue()
        self.assertIn("Unknown subcommand 'get'", err_msg)
        self.assertIn("Available: list, check", err_msg)

        ret = cli_contributes(CmdBags(args=["list"], options={"module": CmdOption(name="module", params="core")}))
        self.assertEqual(ret, 0)

        self.mark_passed()

    def test_contributes_check_invalid_payload_returns_error(self):
        """驗證傳入含未知擴充點與型別錯誤的貢獻檔至 check_contributes 時回傳 1 且輸出包含 [FAIL]。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_core_json = os.path.join(tmp_dir, "core.json")
            with open(bad_core_json, "w", encoding="utf-8") as f:
                json.dump({
                    "unknown_point_xyz": {"foo": "bar"},
                    "commands": "invalid_string_instead_of_dict"
                }, f)

            buf = io.StringIO()
            with redirect_stdout(buf):
                ret = contributes_cmd.check_contributes(bad_core_json)
            self.assertEqual(ret, 1)
            self.assertIn("[FAIL]", buf.getvalue())

        self.assertEqual(contributes_cmd.check_contributes("nonexistent_module_xyz_999"), 1)
        self.assertEqual(contributes_cmd.check_contributes("config://nonexistent_mod/contribute.json"), 1)
        self.mark_passed()

    def test_contributes_check_project_override_file(self):
        """驗證 check_contributes 支援 config://core/contribute.json (含包裹與未包裹兩種格式) 與模組級掃描。"""
        cfg_core_dir = uri.resolve("config://core")
        vfs.makedirs("config://core", exist_ok=True)
        cfg_path = os.path.join(cfg_core_dir, "contribute.json")
        try:
            wrapped_cfg = {
                "core": {
                    "commands": {
                        "cmd": {
                            "custom_cmd": {
                                "description": "Custom project command",
                                "tier": "safe"
                            }
                        }
                    }
                }
            }
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(wrapped_cfg, f, indent=2)

            self.assertEqual(contributes_cmd.check_contributes("config://core/contribute.json"), 0)
            self.assertEqual(contributes_cmd.check_contributes(cfg_path), 0)
            self.assertEqual(contributes_cmd.check_contributes("core"), 0)

            unwrapped_cfg = {
                "commands": {
                    "cmd": {
                        "custom_cmd_unwrapped": {
                            "description": "Unwrapped project command",
                            "tier": "safe"
                        }
                    }
                }
            }
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(unwrapped_cfg, f, indent=2)
            self.assertEqual(contributes_cmd.check_contributes("config://core/contribute.json"), 0)

            invalid_cfg = {"core": {"commands": "invalid_type"}}
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(invalid_cfg, f, indent=2)
            self.assertEqual(contributes_cmd.check_contributes("config://core/contribute.json"), 1)
            self.assertEqual(contributes_cmd.check_contributes("core"), 1)
        finally:
            if os.path.isfile(cfg_path):
                os.remove(cfg_path)

        self.mark_passed()

    def test_contributes_check_corrupted_single_file_and_format_file(self):
        """驗證單檔模式傳入損毀 JSON、損毀 _format.json 及分片路徑 donor_mod 語系連動校驗時優雅回傳 1。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            corrupt_core = os.path.join(tmp_dir, "core.json")
            with open(corrupt_core, "w", encoding="utf-8") as f:
                f.write("{corrupted json syntax")

            buf_c1 = io.StringIO()
            with redirect_stdout(buf_c1):
                ret_c1 = contributes_cmd.check_contributes(corrupt_core)
            self.assertEqual(ret_c1, 1)
            self.assertIn("[FAIL]", buf_c1.getvalue())

            corrupt_fmt = os.path.join(tmp_dir, "_format.json")
            with open(corrupt_fmt, "w", encoding="utf-8") as f:
                f.write("{corrupted format json")

            buf_c2 = io.StringIO()
            with redirect_stdout(buf_c2):
                ret_c2 = contributes_cmd.check_contributes(corrupt_fmt)
            self.assertEqual(ret_c2, 1)
            self.assertIn("[FAIL]", buf_c2.getvalue())

            valid_fmt = uri.resolve("module://core/contributes/_format.json")
            buf_v = io.StringIO()
            with redirect_stdout(buf_v):
                self.assertEqual(contributes_cmd.check_contributes(valid_fmt), 0)

        # Verify shard path <donor>/contributes/core.json derives donor_mod and checks locale contract
        donor_name = "mock_donor_loc_err"
        donor_contrib_dir = uri.resolve(f"module://{donor_name}/contributes")
        os.makedirs(donor_contrib_dir, exist_ok=True)
        shard_file = os.path.join(donor_contrib_dir, "core.json")
        try:
            with open(shard_file, "w", encoding="utf-8") as f:
                json.dump({"locales": {"definition": "locales/missing_def.json"}}, f)
            buf_loc = io.StringIO()
            with redirect_stdout(buf_loc):
                ret_loc = contributes_cmd.check_contributes(shard_file)
            self.assertEqual(ret_loc, 1)
            self.assertIn("[FAIL]", buf_loc.getvalue())
        finally:
            if vfs.exists(f"module://{donor_name}"):
                vfs.rmtree(f"module://{donor_name}", ignore_errors=True)

        self.mark_passed()
