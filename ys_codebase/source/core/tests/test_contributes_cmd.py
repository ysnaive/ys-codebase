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
            cli_path = os.path.join(uri._get_yscb_root(), ".modules", "core", "scripts", "cli.py")
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

        self.mark_passed()


