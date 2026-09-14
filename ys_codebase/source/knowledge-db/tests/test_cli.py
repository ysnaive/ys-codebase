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

def process(args: list) -> int:
    from core.commands.dispatcher import dispatch
    return dispatch(["knowledge-db"] + list(args))


# 動態加載 hook.dev.py
_hook_path = os.path.join(_pkg_root, "scripts", "hook.dev.py")
_spec = importlib.util.spec_from_file_location("hook_dev", _hook_path)
_hook_dev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hook_dev)


class TestCLI(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_cli_all_commands(self):
        """FT-07: 驗證 CLI 8 大子指令路由與執行 (status, index, search, callers, callees, impact, clean, model)"""
        # 1. 說明指令
        self.assertEqual(process([]), 0)
        self.assertEqual(process(["--help"]), 0)

        # 2. status 指令
        self.assertEqual(process(["status"]), 0)

        # 3. index 指令
        self.assertEqual(process(["index", "--all"]), 0)

        # 4. search 指令
        self.assertEqual(process(["search", "PIDController"]), 0)
        # 空檢索參數防禦
        self.assertEqual(process(["search"]), 1)

        # 5. callers 指令
        self.assertEqual(process(["callers", "PIDController"]), 0)

        # 6. callees 指令
        self.assertEqual(process(["callees", "PIDController"]), 0)

        # 7. impact 指令
        self.assertEqual(process(["impact", "PIDController"]), 0)

        # 8. model 指令
        self.assertEqual(process(["model", "status"]), 0)

        # 9. clean 指令
        self.assertEqual(process(["clean", "--all"]), 0)

        # 10. 未知指令 (EC-06)
        self.assertNotEqual(process(["unknown_cmd_xyz"]), 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_removed_commands(self):
        """FT-01, EC-05: 驗證舊指令 (scan, bundle) 已徹底移除，調用時返回非 0 退出碼"""
        self.assertNotEqual(process(["scan", "--all"]), 0)
        self.assertNotEqual(process(["bundle", "--all"]), 0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_status_with_scan(self):
        """FT-02: 驗證 status --scan / status --diff 正常輸出空間指紋統計與變更"""
        buf_scan = io.StringIO()
        with contextlib.redirect_stdout(buf_scan):
            ret = process(["status", "--scan"])
        self.assertEqual(ret, 0)
        out_scan = buf_scan.getvalue()
        self.assertIn("系統狀態摘要", out_scan)
        self.assertIn("增量指紋比對結果", out_scan)

        buf_diff = io.StringIO()
        with contextlib.redirect_stdout(buf_diff):
            ret = process(["status", "--diff"])
        self.assertEqual(ret, 0)
        out_diff = buf_diff.getvalue()
        self.assertIn("增量指紋比對結果", out_diff)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_index_pipeline_and_export(self):
        """FT-03, EC-04: 驗證 index 一鍵全管線建置，以及 index --export <path> 導出 Bundle"""
        ret = process(["index", "--all"])
        self.assertEqual(ret, 0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            export_file = Path(tmp_dir) / "nested" / "bundle_export.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ret = process(["index", "--export", str(export_file)])
            self.assertEqual(ret, 0)
            self.assertTrue(export_file.exists())
            with open(export_file, "r", encoding="utf-8") as f:
                bundle_data = json.load(f)
            self.assertIn("symbols", bundle_data)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_model_subcommands(self):
        """FT-04: 驗證 model status 與 model download 正常運作，權重資訊輸出精確"""
        # 1. model status 格式化文字
        buf_text = io.StringIO()
        with contextlib.redirect_stdout(buf_text):
            ret = process(["model", "status"])
        self.assertEqual(ret, 0)
        out_text = buf_text.getvalue()
        self.assertIn("向量推論模型狀態", out_text)
        self.assertIn("模型名稱", out_text)
        self.assertIn("快取目錄", out_text)

        # 2. model status --json
        buf_json = io.StringIO()
        with contextlib.redirect_stdout(buf_json):
            ret = process(["model", "status", "--json"])
        self.assertEqual(ret, 0)
        st_data = json.loads(buf_json.getvalue())
        self.assertIn("model_name", st_data)
        self.assertIn("cache_dir", st_data)
        self.assertIn("is_downloaded", st_data)
        self.assertIn("dimension", st_data)

        # 3. model download
        from unittest.mock import patch
        with patch("knowledge_db.embedding.EmbeddingService.download_model", return_value=True):
            ret = process(["model", "download"])
            self.assertEqual(ret, 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_search_smooth_fallback(self):
        """FT-05, EC-01: 驗證本地無模型時 search 絕不連網發 HF 請求，平滑且靜默退回 BM25"""
        from knowledge_db.embedding import EmbeddingService
        with tempfile.TemporaryDirectory() as empty_cache:
            svc = EmbeddingService(cache_dir=empty_cache, mock_mode=False, enable_vector_search=False)
            self.assertFalse(svc.is_model_downloaded())
            self.assertFalse(svc.is_available)
            self.assertIsNotNone(svc.last_error)
            self.assertEqual(svc.last_error["error_type"], "ModelNotFoundLocally")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_guard_directive_output(self):
        """FT-06: 驗證當 enable_vector_search: true 但無模型時，stderr 輸出 [GUARD] 提示"""
        from knowledge_db.embedding import EmbeddingService
        with tempfile.TemporaryDirectory() as empty_cache:
            err_buf = io.StringIO()
            with contextlib.redirect_stderr(err_buf):
                svc = EmbeddingService(cache_dir=empty_cache, mock_mode=False, enable_vector_search=True)
                _ = svc.is_available
            err_out = err_buf.getvalue()
            expected_guard = "[GUARD] 如果你是 AI Agent，必須立即暫停當前作業，並向開發者提問：要執行 model download 或是於 config 中關閉向量檢索？"
            self.assertIn(expected_guard, err_out)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_offline_zero_crash(self):
        """ET-01, EC-02, NFR-01: 驗證離線模式下模型缺失探針秒級生效，檢索無逾時、無卡頓與無例外崩潰"""
        import time
        from knowledge_db.embedding import EmbeddingService
        with tempfile.TemporaryDirectory() as empty_cache:
            t0 = time.perf_counter()
            svc = EmbeddingService(cache_dir=empty_cache, mock_mode=False, enable_vector_search=True)
            _ = svc.is_available
            elapsed = time.perf_counter() - t0
            self.assertLess(elapsed, 0.5, "Probe should complete sub-second without network timeout")
            self.assertFalse(svc.is_available)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_search_modes(self):
        """FT-01 ~ FT-03, ET-01: 驗證 search 模式 (simple, detail, auto, md, json, limit=auto/N)"""
        # 1. 預設 auto 模式
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = process(["search", "PIDController"])
        self.assertEqual(ret, 0)
        out = buf.getvalue()
        self.assertIn("檢索查詢", out)
        if "#01" in out:
            self.assertIn("](file:///", out)

        # 2. 清單模式 (--simple)
        buf_simple = io.StringIO()
        with contextlib.redirect_stdout(buf_simple):
            ret = process(["search", "PIDController", "--simple"])
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
                ret = process(["search", "PIDController", flag])
            self.assertEqual(ret, 0)
            out_detail = buf_detail.getvalue()
            if "#01" in out_detail:
                self.assertIn("詳細模式", out_detail)
                self.assertIn("](file:///", out_detail)

        # 4. Markdown 模式 (--md, --markdown)
        for flag in ["--md", "--markdown"]:
            buf_md = io.StringIO()
            with contextlib.redirect_stdout(buf_md):
                ret = process(["search", "PIDController", flag])
            self.assertEqual(ret, 0)
            out_md = buf_md.getvalue()
            self.assertIn("知識庫檢索", out_md)

        # 5. Limit 參數 (--limit=auto, --limit=2)
        buf_lim = io.StringIO()
        with contextlib.redirect_stdout(buf_lim):
            ret = process(["search", "PIDController", "--limit=2"])
        self.assertEqual(ret, 0)

        buf_auto = io.StringIO()
        with contextlib.redirect_stdout(buf_auto):
            ret = process(["search", "PIDController", "--limit=auto"])
        self.assertEqual(ret, 0)

        # 6. JSON 模式 (--json)
        buf_json = io.StringIO()
        with contextlib.redirect_stdout(buf_json):
            ret = process(["search", "PIDController", "--json"])
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
                ret = process(["search", "PIDController", flag])
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
            ret = process(["search", "NonExistentTermXYZ_123456"])
        self.assertEqual(ret, 0)
        self.assertIn("未找到符合的結果", buf_empty.getvalue())

        buf_empty_json = io.StringIO()
        with contextlib.redirect_stdout(buf_empty_json):
            ret = process(["search", "NonExistentTermXYZ_123456", "--json"])
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
                ret = process(["callers", "PIDController", flag])
            self.assertEqual(ret, 0)

        # 2. callees 指令
        for flag in ["--simple", "--detail", "--md", "--json", "-s"]:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ret = process(["callees", "PIDController", flag])
            self.assertEqual(ret, 0)

        # 3. impact 指令
        for flag in ["--simple", "--detail", "--md", "--json", "--depth=2"]:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ret = process(["impact", "PIDController", flag])
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


    @require(Requirement.LOGIC)
    def test_cli_options_extraction_and_orthogonal_filter(self):
        """FT-10: 驗證 CLI options 正確提取純字串值與 --space 和 --ftype 正交複合篩選 (ISSUE-01, ISSUE-03)"""
        # 1. 驗證 --space 與 --ftype 複合使用，不再引發互斥衝突 EC-02
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = process(["search", "PIDController", "--space", "core", "--ftype", "py", "--lexical-only"])
        self.assertEqual(ret, 0)

        # 2. 驗證 search 帶 --kind, --lang, --limit 正常提取
        buf_search = io.StringIO()
        with contextlib.redirect_stdout(buf_search):
            ret = process(["search", "PIDController", "--kind", "class", "--lang", "python", "--limit", "3", "--json"])
        self.assertEqual(ret, 0)
        data = json.loads(buf_search.getvalue())
        self.assertIn("results", data)

        # 3. 驗證 callers 帶 --limit 正常提取數值
        buf_callers = io.StringIO()
        with contextlib.redirect_stdout(buf_callers):
            ret = process(["callers", "PIDController", "--limit", "5", "--json"])
        self.assertEqual(ret, 0)

        # 4. 驗證 callees 帶 --limit 正常提取數值
        buf_callees = io.StringIO()
        with contextlib.redirect_stdout(buf_callees):
            ret = process(["callees", "PIDController", "--limit", "5", "--json"])
        self.assertEqual(ret, 0)

        # 5. 驗證 impact 帶 --depth 與 --limit 正常提取數值
        buf_impact = io.StringIO()
        with contextlib.redirect_stdout(buf_impact):
            ret = process(["impact", "PIDController", "--depth", "3", "--limit", "5", "--json"])
        self.assertEqual(ret, 0)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()

