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

    @require(Requirement.LOGIC)
    def test_cli_search_modes(self):
        """FT-01 ~ FT-03, ET-01: 驗證 search 簡易模式、詳細模式與 JSON 結構化輸出"""
        # 1. 簡易模式 (預設)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = main(["search", "PIDController"])
        self.assertEqual(ret, 0)
        out = buf.getvalue()
        self.assertIn("檢索查詢", out)
        if "#01" in out:
            # 簡易模式每行應為 #01 file_path:line
            self.assertNotIn("命中詞:", out)
            self.assertNotIn("簽名:", out)

        # 2. 詳細模式 (--detail, -d, --verbose)
        for flag in ["--detail", "-d", "--verbose"]:
            buf_detail = io.StringIO()
            with contextlib.redirect_stdout(buf_detail):
                ret = main(["search", "PIDController", flag])
            self.assertEqual(ret, 0)
            out_detail = buf_detail.getvalue()
            if "#01" in out_detail:
                self.assertIn("命中詞:", out_detail)

        # 3. JSON 模式 (--json)
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
            self.assertIn("rank", item)
            self.assertIn("score", item)
            self.assertIn("symbol", item)
            self.assertIn("file_path", item["symbol"])

        # 4. Snippet 模式 (--snippet, -s, --preview)
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

        # 5. JSON + Snippet 模式
        buf_json_snip = io.StringIO()
        with contextlib.redirect_stdout(buf_json_snip):
            ret = main(["search", "PIDController", "-s", "--json"])
        self.assertEqual(ret, 0)
        data_snip = json.loads(buf_json_snip.getvalue())
        self.assertIn("results", data_snip)
        if data_snip["total"] > 0:
            item = data_snip["results"][0]
            self.assertIn("code_snippet", item)

        # 6. 0 筆結果情境 (ET-01)
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

    @require(Requirement.LOGIC)
    def test_hook_lifecycle(self):
        """FT-08: 驗證 hook.dev.py 測試前置與後置鉤子正常執行"""
        with tempfile.TemporaryDirectory() as temp_dir:
            _hook_dev.on_test_setup(temp_dir)
            indices_dir = Path(temp_dir) / ".cache" / "knowledge-db" / "indices"
            self.assertTrue(indices_dir.exists())

            _hook_dev.on_test_teardown(temp_dir)
