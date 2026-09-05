"""
Unit Tests for knowledge-db CLI Router and Development Hooks.
"""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from scripts.cli import main

# 動態加載 hook.dev.py
_hook_path = os.path.join(_pkg_root, "scripts", "hook.dev.py")
_spec = importlib.util.spec_from_file_location("hook_dev", _hook_path)
_hook_dev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hook_dev)


class TestCLI(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_cli_all_commands(self):
        """FT-07: 驗證 CLI 6 大子指令路由與執行 (status, scan, bundle, index, search, clean)"""
        # 1. 說明指令
        self.assertEqual(main([]), 0)
        self.assertEqual(main(["--help"]), 0)

        # 2. status 指令
        self.assertEqual(main(["status"]), 0)

        # 3. scan 指令
        self.assertEqual(main(["scan", "--all"]), 0)

        # 4. bundle 指令
        self.assertEqual(main(["bundle", "--all"]), 0)

        # 5. index 指令
        self.assertEqual(main(["index", "--all"]), 0)

        # 6. search 指令
        self.assertEqual(main(["search", "PIDController"]), 0)
        # 空檢索參數防禦
        self.assertEqual(main(["search"]), 1)

        # 7. clean 指令
        self.assertEqual(main(["clean", "--all"]), 0)

        # 8. 未知指令 (EC-06)
        self.assertEqual(main(["unknown_cmd_xyz"]), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_search_modes(self):
        """FT-01 ~ FT-03, ET-01: 驗證 search 模式 (simple, detail, auto, md, json, limit=auto/N)"""
        # 1. 預設 auto 模式
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["search", "PIDController"])
        self.assertEqual(ret, 0)
        out = buf.getvalue()
        self.assertIn("檢索查詢", out)
        if "#01" in out:
            self.assertIn("](file:///", out)

        # 2. 清單模式 (--simple)
        buf_simple = io.StringIO()
        with contextlib.redirect_stdout(buf_simple):
            ret = main(["search", "PIDController", "--simple"])
        self.assertEqual(ret, 0)
        out_simple = buf_simple.getvalue()
        if "#01" in out_simple:
            self.assertIn("清單模式", out_simple)
            self.assertNotIn("命中詞:", out_simple)
            self.assertIn("](file:///", out_simple)

        # 3. 詳細模式 (--detail, -d, --verbose)
        for flag in ["--detail", "-d", "--verbose"]:
            buf_detail = io.StringIO()
            with contextlib.redirect_stdout(buf_detail):
                ret = main(["search", "PIDController", flag])
            self.assertEqual(ret, 0)
            out_detail = buf_detail.getvalue()
            if "#01" in out_detail:
                self.assertIn("詳細模式", out_detail)
                self.assertIn("](file:///", out_detail)

        # 4. Markdown 模式 (--md, --markdown)
        for flag in ["--md", "--markdown"]:
            buf_md = io.StringIO()
            with contextlib.redirect_stdout(buf_md):
                ret = main(["search", "PIDController", flag])
            self.assertEqual(ret, 0)
            out_md = buf_md.getvalue()
            self.assertIn("知識庫檢索", out_md)

        # 5. Limit 參數 (--limit=auto, --limit=2)
        buf_lim = io.StringIO()
        with contextlib.redirect_stdout(buf_lim):
            ret = main(["search", "PIDController", "--limit=2"])
        self.assertEqual(ret, 0)

        buf_auto = io.StringIO()
        with contextlib.redirect_stdout(buf_auto):
            ret = main(["search", "PIDController", "--limit=auto"])
        self.assertEqual(ret, 0)

        # 6. JSON 模式 (--json)
        buf_json = io.StringIO()
        with contextlib.redirect_stdout(buf_json):
            ret = main(["search", "PIDController", "--json"])
        self.assertEqual(ret, 0)
        data = json.loads(buf_json.getvalue())
        self.assertEqual(data["query"], "PIDController")
        self.assertIn("total", data)
        self.assertIn("results", data)
        if data["total"] > 0:
            item = data["results"][0]
            self.assertIn("file_uri", item)
            self.assertTrue(item["file_uri"].startswith("file:///"))
            self.assertIn("total_score", item)

        # 7. Snippet 模式 (--snippet, -s, --preview)
        for flag in ["--snippet", "-s", "--preview"]:
            buf_snip = io.StringIO()
            with contextlib.redirect_stdout(buf_snip):
                ret = main(["search", "PIDController", flag])
            self.assertEqual(ret, 0)
            out_snip = buf_snip.getvalue()
            self.assertIn("檢索查詢", out_snip)
            if "#01" in out_snip:
                self.assertIn("預覽模式", out_snip)
                self.assertIn("檔案:", out_snip)
                self.assertIn("](file:///", out_snip)

        # 8. 0 筆結果情境 (ET-01)
        buf_empty = io.StringIO()
        with contextlib.redirect_stdout(buf_empty):
            ret = main(["search", "NonExistentTermXYZ_123456"])
        self.assertEqual(ret, 0)
        self.assertIn("未找到符合的結果", buf_empty.getvalue())

        buf_empty_json = io.StringIO()
        with contextlib.redirect_stdout(buf_empty_json):
            ret = main(["search", "NonExistentTermXYZ_123456", "--json"])
        self.assertEqual(ret, 0)
        data_empty = json.loads(buf_empty_json.getvalue())
        self.assertEqual(data_empty["total"], 0)
        self.assertEqual(data_empty["results"], [])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_callers_callees_impact_modes(self):
        """FT-09: 驗證 callers, callees, impact 子命令之 simple, detail, md, json 模式與參數解析"""
        # 1. callers 指令
        for flag in ["--simple", "--detail", "--md", "--json", "-s"]:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ret = main(["callers", "PIDController", flag])
            self.assertEqual(ret, 0)

        # 2. callees 指令
        for flag in ["--simple", "--detail", "--md", "--json", "-s"]:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ret = main(["callees", "PIDController", flag])
            self.assertEqual(ret, 0)

        # 3. impact 指令
        for flag in ["--simple", "--detail", "--md", "--json", "--depth=2"]:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ret = main(["impact", "PIDController", flag])
            self.assertEqual(ret, 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hook_lifecycle(self):
        """FT-08: 驗證 hook.dev.py 測試前置與後置鉤子正常執行"""
        with tempfile.TemporaryDirectory() as temp_dir:
            _hook_dev.on_test_setup(temp_dir)
            indices_dir = Path(temp_dir) / ".cache" / "knowledge-db" / "indices"
            self.assertTrue(indices_dir.exists())

            _hook_dev.on_test_teardown(temp_dir)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
