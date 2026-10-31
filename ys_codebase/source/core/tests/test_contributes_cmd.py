"""
Integration tests for contributes CLI and SDK functions.
Covers FT-06 ~ FT-07.
"""
from dev.testing import YSCBTestCase, require, Requirement
from core import contributes
from core.commands import contributes_cmd
from core.commands.bags import CmdBags


class TestContributesCmdAndSDK(YSCBTestCase):
    @require(Requirement.ENV)
    def test_sdk_get_format_and_list_points(self):
        """FT-06: SDK get_format 與 list_points 正確讀取"""
        core_fmt = contributes.get_format("core")
        self.assertIsNotNone(core_fmt, "core _format.json should be readable")
        self.assertIn("commands", core_fmt)
        self.assertIn("uri_schemes", core_fmt)
        self.assertIn("events", core_fmt)

        points = contributes.list_points("core")
        self.assertTrue(len(points) >= 3)
        pts = [p["point"] for p in points]
        self.assertIn("commands", pts)
        self.assertIn("uri_schemes", pts)
        self.assertIn("events", pts)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_contributes_cli_list(self):
        """FT-06: CLI contributes list 執行"""
        ret = contributes_cmd.list_contributes("core")
        self.assertEqual(ret, 0)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_contributes_cli_check_self(self):
        """FT-06: CLI contributes check 執行檢驗 core.json"""
        ret = contributes_cmd.check_contributes("core")
        self.assertEqual(ret, 0)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_contributes_cli_format_check(self):
        """FT-06: CLI contributes check --format 執行"""
        ret = contributes_cmd.check_contributes("core", is_format_check=True)
        self.assertEqual(ret, 0)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_contributes_aggregator_ignores_special_files(self):
        """FT-07: Aggregator 聚合時排除 _ 開頭特殊檔案"""
        aggregator = contributes.ContributesAggregator()
        merged = aggregator.scan_and_inject()
        # _format 不應作為 target 模組存在於聚合根鍵中
        self.assertNotIn("_format", merged)
        self.assertNotIn("_manifest", merged)
        self.assertIn("core", merged)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_contributes_cli_dispatcher(self):
        """FT-08: 驗證 core scripts.cli:contributes() 分發器與未知子指令防呆 (ISSUE-02)"""
        import io
        import os
        import importlib.util
        import contextlib

        test_dir = os.path.dirname(os.path.abspath(__file__))
        cli_path = os.path.join(os.path.dirname(test_dir), "scripts", "cli.py")
        if not os.path.isfile(cli_path):
            from core import uri
            cli_path = os.path.join(uri.resolve_yscb_root(), ".modules", "core", "scripts", "cli.py")
        spec = importlib.util.spec_from_file_location("core_cli", cli_path)
        core_cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core_cli)
        cli_contributes = core_cli.contributes

        # 1. 預設無參數分發 -> list
        ret = cli_contributes(CmdBags(args=[]))
        self.assertEqual(ret, 0)

        # 2. list 帶 module 參數
        ret = cli_contributes(CmdBags(args=["list", "core"]))
        self.assertEqual(ret, 0)

        # 3. check 帶 module 參數
        ret = cli_contributes(CmdBags(args=["check", "core"]))
        self.assertEqual(ret, 0)

        # 4. 未知子指令防呆 (ISSUE-02: 確保不拋出 NameError 或 AttributeError，且輸出可用提示)
        err_buf = io.StringIO()
        with contextlib.redirect_stderr(err_buf):
            ret = cli_contributes(CmdBags(args=["get", "knowledge-db", "spaces"]))
        self.assertEqual(ret, 1)
        err_msg = err_buf.getvalue()
        self.assertIn("Unknown subcommand 'get'", err_msg)
        self.assertIn("Available: list, check", err_msg)

        # 5. list 帶 --module 選項參數 (FR-02)
        from core.commands.bags import CmdOption
        ret = cli_contributes(CmdBags(args=["list"], options={"module": CmdOption(name="module", params="core")}))
        self.assertEqual(ret, 0)

        self.mark_passed()

    @require(Requirement.ENV)
    def test_contributes_check_invalid_payload_returns_error(self):
        """T-06 補盲: 驗證傳入含未知擴充點與型別錯誤的貢獻檔至 check_contributes 時回傳 1 且輸出包含 [FAIL]。"""
        import io
        import os
        import json
        import tempfile
        from contextlib import redirect_stdout
        from core.commands import contributes_cmd

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

        # EC-02: 指定不存在的檔案或模組名稱時回傳 1
        self.assertEqual(contributes_cmd.check_contributes("nonexistent_module_xyz_999"), 1)
        self.assertEqual(contributes_cmd.check_contributes("config://nonexistent_mod/contribute.json"), 1)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_contributes_check_project_override_file(self):
        """T-06 補盲 & FT-02 & EC-01: 驗證 check_contributes 支援 config://core/contribute.json (含包裹與未包裹兩種格式) 與模組級掃描。"""
        import os
        import json
        from core import uri, vfs
        from core.commands import contributes_cmd

        cfg_core_dir = uri.resolve("config://core")
        vfs.makedirs("config://core", exist_ok=True)
        cfg_path = os.path.join(cfg_core_dir, "contribute.json")
        try:
            # 1. 包裹於 {"core": ...} 頂層鍵之標準格式
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

            # 驗證 URI 形式與實體路徑形式皆正確推導 target_mod="core" 並通過 (0)
            self.assertEqual(contributes_cmd.check_contributes("config://core/contribute.json"), 0)
            self.assertEqual(contributes_cmd.check_contributes(cfg_path), 0)
            # 驗證模組級掃描亦納管 config://core/contribute.json
            self.assertEqual(contributes_cmd.check_contributes("core"), 0)

            # 2. EC-01: 未包裹頂層 "core" 鍵（直接為擴充點 dict）亦正常校驗通過
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

            # 3. 寫入非法型別 Payload 時單檔與模組級掃描皆返回 1
            invalid_cfg = {"core": {"commands": "invalid_type"}}
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(invalid_cfg, f, indent=2)
            self.assertEqual(contributes_cmd.check_contributes("config://core/contribute.json"), 1)
            self.assertEqual(contributes_cmd.check_contributes("core"), 1)
        finally:
            if os.path.isfile(cfg_path):
                os.remove(cfg_path)

        self.mark_passed()



