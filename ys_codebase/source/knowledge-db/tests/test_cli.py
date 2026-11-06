"""
Unit Tests for knowledge-db CLI Router, Development Hooks, and Version Migration.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
import knowledge_db.engine as kdb_engine
import knowledge_db.pipeline as kdb_pipeline
from knowledge_db.embedding import EmbeddingService
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.retrieval import CodeSnippet
from knowledge_db.schema import AggregatedFileResult, AggregatedItem, UnifiedSymbol
from tests import load_script_module, process


class TestCLI(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.proj_dir = Path(self.temp_dir.name)
        src_dir = self.proj_dir / "src"
        docs_dir = self.proj_dir / "docs"
        src_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.mkdir(parents=True, exist_ok=True)

        (src_dir / "pid_a.py").write_text(
            "class PIDController:\n"
            '    """PID 控制器實作"""\n'
            "    def compute_pid(self):\n"
            "        return 1\n\n"
            "def compute_pid_step(error: float) -> float:\n"
            '    """計算單步 PIDController 修正量"""\n'
            "    return error * 0.5\n",
            encoding="utf-8",
        )
        (src_dir / "pid_b.py").write_text(
            "class PIDFilterNode:\n"
            '    """PIDController 訊號濾波節點"""\n'
            "    def apply_pid_filter(self):\n"
            "        return 2\n",
            encoding="utf-8",
        )
        (src_dir / "pid_c.py").write_text(
            "class PIDActuatorDriver:\n"
            '    """PIDController 致動器驅動模組"""\n'
            "    def drive_pid_output(self):\n"
            "        return 3\n",
            encoding="utf-8",
        )
        (docs_dir / "pid_guide.md").write_text(
            "# PIDController 架構指南\n\n說明 PIDController 控制器調校與穩定度分析。\n",
            encoding="utf-8",
        )

        self.engine = KnowledgeEngine(
            project_root=self.proj_dir,
            storage_dir=self.proj_dir / "storage",
            contributes_data={
                "spaces": {
                    "core": {"include": [str(src_dir)]},
                    "docs": {"include": [str(docs_dir)]},
                },
                "space_weights": {"core": 1.0, "docs": 1.2},
            },
            embedding_mock_mode=True,
        )
        self.engine.build_unified_index(force=True)

        self._old_global_engine = kdb_engine._GLOBAL_ENGINE_INSTANCE
        self._old_global_cache = dict(kdb_pipeline._GLOBAL_INDEX_CACHE)
        kdb_engine._GLOBAL_ENGINE_INSTANCE = self.engine

    def tearDown(self):
        kdb_engine._GLOBAL_ENGINE_INSTANCE = self._old_global_engine
        with kdb_pipeline._CACHE_LOCK:
            kdb_pipeline._GLOBAL_INDEX_CACHE.clear()
            kdb_pipeline._GLOBAL_INDEX_CACHE.update(self._old_global_cache)
        self.temp_dir.cleanup()
        super().tearDown()

    def _run_cli(self, args: list) -> tuple:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            code = process(args)
        return code, out_buf.getvalue(), err_buf.getvalue()

    @require(Requirement.LOGIC)
    def test_cli_all_commands(self):
        """驗證 CLI 5 大子指令路由、輸出內容與索引清除重建副作用"""
        code, out_help, _ = self._run_cli([])
        self.assertEqual(code, 0)
        self.assertIn("knowledge-db", out_help)

        code_h, out_h, _ = self._run_cli(["--help"])
        self.assertEqual(code_h, 0)
        self.assertIn("search", out_h)

        code_st, out_st, _ = self._run_cli(["status"])
        self.assertEqual(code_st, 0)
        self.assertIn("系統狀態摘要", out_st)

        code_s, out_s, _ = self._run_cli(["search", "PIDController"])
        self.assertEqual(code_s, 0)
        self.assertIn("PIDController", out_s)

        code_empty, _, _ = self._run_cli(["search"])
        self.assertEqual(code_empty, 1)

        code_m, out_m, _ = self._run_cli(["model", "status"])
        self.assertEqual(code_m, 0)
        self.assertIn("向量推論模型狀態", out_m)

        # 驗證 clean --all 確實刪除磁碟上的 unified.index.bin.gz
        bin_path = self.engine.pipeline.get_indices_dir() / "unified.index.bin.gz"
        self.assertTrue(bin_path.exists())
        code_c, _, _ = self._run_cli(["clean", "--all"])
        self.assertEqual(code_c, 0)
        self.assertFalse(bin_path.exists())

        # 驗證 index --all 重建索引且 doc_count >= 4
        code_idx, _, _ = self._run_cli(["index", "--all"])
        self.assertEqual(code_idx, 0)
        self.assertTrue(bin_path.exists())
        self.assertGreaterEqual(self.engine.pipeline.unified_index.doc_count, 4)

        code_unk, _, _ = self._run_cli(["unknown_cmd_xyz"])
        self.assertNotEqual(code_unk, 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_removed_commands(self):
        """驗證舊指令 (scan, bundle, callers, callees, impact) 已徹底移除，調用時返回非 0 退出碼"""
        for cmd_args in (
            ["scan", "--all"],
            ["bundle", "--all"],
            ["callers", "PIDController"],
            ["callees", "PIDController"],
            ["impact", "PIDController"],
        ):
            code, _, _ = self._run_cli(cmd_args)
            self.assertNotEqual(code, 0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_status_json_output(self):
        """驗證 status 與 status --json 正常輸出空間資訊、權重與索引統計"""
        ret, out_text, _ = self._run_cli(["status"])
        self.assertEqual(ret, 0)
        self.assertIn("系統狀態摘要", out_text)

        ret_j, out_json, _ = self._run_cli(["status", "--json"])
        self.assertEqual(ret_j, 0)
        st_data = json.loads(out_json)
        self.assertEqual(st_data["total_spaces"], 2)
        self.assertIn("core", st_data["spaces"])
        self.assertIn("docs", st_data["spaces"])
        self.assertIn("storage_dir", st_data)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_index_pipeline_and_export(self):
        """驗證 index 一鍵全管線建置，以及 index --export <path> 導出 Bundle"""
        ret, _, _ = self._run_cli(["index", "--all"])
        self.assertEqual(ret, 0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            export_file = Path(tmp_dir) / "nested" / "bundle_export.json"
            ret_exp, _, _ = self._run_cli(["index", "--export", str(export_file)])
            self.assertEqual(ret_exp, 0)
            self.assertTrue(export_file.exists())
            with open(export_file, "r", encoding="utf-8") as f:
                bundle_data = json.load(f)
            self.assertIn("symbols", bundle_data)
            self.assertGreaterEqual(len(bundle_data["symbols"]), 4)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_model_subcommands(self):
        """驗證 model status 與 model download 正常運作，權重資訊輸出精確"""
        ret, out_text, _ = self._run_cli(["model", "status"])
        self.assertEqual(ret, 0)
        self.assertIn("向量推論模型狀態", out_text)
        self.assertIn("模型名稱", out_text)
        self.assertIn("快取目錄", out_text)

        ret_j, out_json, _ = self._run_cli(["model", "status", "--json"])
        self.assertEqual(ret_j, 0)
        st_data = json.loads(out_json)
        self.assertIn("model_name", st_data)
        self.assertIn("cache_dir", st_data)
        self.assertIn("is_downloaded", st_data)
        self.assertIn("dimension", st_data)

        with patch(
            "knowledge_db.embedding.EmbeddingService.download_model", return_value=True
        ):
            ret_dl, _, _ = self._run_cli(["model", "download"])
            self.assertEqual(ret_dl, 0)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_search_smooth_fallback(self):
        """驗證本地無模型時 search 不連網發請求，平滑且靜默退回 BM25"""
        with tempfile.TemporaryDirectory() as empty_cache:
            svc = EmbeddingService(
                cache_dir=empty_cache, mock_mode=False, enable_vector_search=False
            )
            self.assertFalse(svc.is_model_downloaded())
            self.assertFalse(svc.is_available)
            self.assertIsNotNone(svc.last_error)
            self.assertEqual(svc.last_error["error_type"], "ModelNotFoundLocally")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_guard_directive_output(self):
        """驗證當 enable_vector_search: true 但無模型時，stderr 輸出 [GUARD] 提示"""
        with tempfile.TemporaryDirectory() as empty_cache:
            err_buf = io.StringIO()
            with contextlib.redirect_stderr(err_buf):
                svc = EmbeddingService(
                    cache_dir=empty_cache, mock_mode=False, enable_vector_search=True
                )
                _ = svc.is_available
            err_out = err_buf.getvalue()
            expected_guard = "[GUARD] 如果你是 AI Agent，必須立即暫停當前作業，並向開發者提問：要執行 model download 或是於 config 中關閉向量檢索？"
            self.assertIn(expected_guard, err_out)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_offline_zero_crash(self):
        """驗證離線模式下模型缺失探針秒級生效，檢索無逾時、無卡頓與無例外崩潰"""
        import time

        with tempfile.TemporaryDirectory() as empty_cache:
            t0 = time.perf_counter()
            svc = EmbeddingService(
                cache_dir=empty_cache, mock_mode=False, enable_vector_search=True
            )
            with contextlib.redirect_stderr(io.StringIO()):
                _ = svc.is_available
            elapsed = time.perf_counter() - t0
            self.assertLess(
                elapsed, 0.5, "Probe should complete sub-second without network timeout"
            )
            self.assertFalse(svc.is_available)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_search_modes(self):
        """驗證 search 模式 (simple, detail, auto, md, json, limit=auto/N) 與輸出數量約束"""
        # 1. 預設 auto 模式
        ret, out, _ = self._run_cli(["search", "PIDController"])
        self.assertEqual(ret, 0)
        self.assertIn("檢索查詢", out)
        self.assertIn("#01", out)
        self.assertNotIn("](file:///", out)
        self.assertNotIn("清單模式", out)

        # 1b. 顯式 --file-uri 旗標開啟 file:/// 超連結
        ret_u, out_uri, _ = self._run_cli(["search", "PIDController", "--file-uri"])
        self.assertEqual(ret_u, 0)
        self.assertIn("](file:///", out_uri)

        # 2. 清單模式 (--simple)
        ret_s, out_simple, _ = self._run_cli(["search", "PIDController", "--simple"])
        self.assertEqual(ret_s, 0)
        self.assertIn("#01", out_simple)
        self.assertIn("清單模式", out_simple)
        self.assertNotIn("命中詞:", out_simple)
        self.assertNotIn("](file:///", out_simple)

        # 3. 詳細模式 (--detail, -d, --verbose)
        for flag in ["--detail", "-d", "--verbose"]:
            ret_d, out_detail, _ = self._run_cli(["search", "PIDController", flag])
            self.assertEqual(ret_d, 0)
            self.assertIn("#01", out_detail)
            self.assertIn("詳細模式", out_detail)
            self.assertNotIn("](file:///", out_detail)

        # 4. Markdown 模式 (--md, --markdown 預設保留完整連結)
        for flag in ["--md", "--markdown"]:
            ret_m, out_md, _ = self._run_cli(["search", "PIDController", flag])
            self.assertEqual(ret_m, 0)
            self.assertIn("知識庫檢索", out_md)
            self.assertIn("](file:///", out_md)

        # 5. Limit 參數 (--limit=2 僅輸出 #01, #02 且不含 #03；--limit=auto 包含 #01~#03)
        ret_lim, out_lim, _ = self._run_cli(["search", "PIDController", "--limit=2"])
        self.assertEqual(ret_lim, 0)
        self.assertIn("#01", out_lim)
        self.assertIn("#02", out_lim)
        self.assertNotIn("#03", out_lim)

        ret_auto, out_auto, _ = self._run_cli(
            ["search", "PIDController", "--limit=auto"]
        )
        self.assertEqual(ret_auto, 0)
        self.assertIn("#01", out_auto)
        self.assertIn("#02", out_auto)
        self.assertIn("#03", out_auto)

        # 6. JSON 模式
        ret_j, out_json, _ = self._run_cli(["search", "PIDController", "--json"])
        self.assertEqual(ret_j, 0)
        data = json.loads(out_json)
        self.assertEqual(data["query"], "PIDController")
        self.assertGreater(data["total"], 0)
        item = data["results"][0]
        self.assertNotIn("file_uri", item)
        self.assertIn("total_score", item)

        ret_ju, out_juri, _ = self._run_cli(
            ["search", "PIDController", "--json", "--file-uri"]
        )
        self.assertEqual(ret_ju, 0)
        data_uri = json.loads(out_juri)
        self.assertGreater(data_uri["total"], 0)
        item_uri = data_uri["results"][0]
        self.assertIn("file_uri", item_uri)
        self.assertTrue(item_uri["file_uri"].startswith("file:///"))

        # 7. Snippet 模式 (--snippet, -s, --preview)
        for flag in ["--snippet", "-s", "--preview"]:
            ret_sn, out_snip, _ = self._run_cli(["search", "PIDController", flag])
            self.assertEqual(ret_sn, 0)
            self.assertIn("檢索查詢", out_snip)
            self.assertIn("#01", out_snip)
            self.assertIn("預覽模式", out_snip)
            self.assertIn("檔案:", out_snip)
            self.assertNotIn("](file:///", out_snip)

        # 8. 0 筆結果情境
        ret_emp, out_emp, _ = self._run_cli(["search", "NonExistentTermXYZ_123456"])
        self.assertEqual(ret_emp, 0)
        self.assertIn("未找到符合的結果", out_emp)

        ret_ej, out_ej, _ = self._run_cli(
            ["search", "NonExistentTermXYZ_123456", "--json"]
        )
        self.assertEqual(ret_ej, 0)
        data_empty = json.loads(out_ej)
        self.assertEqual(data_empty["total"], 0)
        self.assertEqual(data_empty["results"], [])

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hook_lifecycle(self):
        """驗證 hook.dev.py 測試前置與後置鉤子建立 4 個目錄、支援物件型態 context 並還原環境變數"""
        hook_dev = load_script_module("hook.dev.py")
        prev_mock = os.environ.get("KNOWLEDGE_DB_MOCK_EMBEDDING")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                sb_path = Path(temp_dir)
                # 1. 字串路徑 context
                hook_dev.on_test_setup(temp_dir)
                self.assertEqual(os.environ.get("KNOWLEDGE_DB_MOCK_EMBEDDING"), "1")
                storage_dir = sb_path / ".storage.local" / "knowledge-db"
                self.assertTrue((storage_dir / "indices").is_dir())
                self.assertTrue((storage_dir / "bundles").is_dir())
                self.assertTrue((storage_dir / "models").is_dir())
                self.assertTrue((sb_path / ".cache" / "knowledge-db").is_dir())

                hook_dev.on_test_teardown(temp_dir)
                self.assertNotIn("KNOWLEDGE_DB_MOCK_EMBEDDING", os.environ)

                # 2. SimpleNamespace(sandbox_dir=...) 物件型態 context
                sb_obj_dir = sb_path / "obj_sandbox"
                ctx_obj = SimpleNamespace(sandbox_dir=str(sb_obj_dir))
                hook_dev.on_test_setup(ctx_obj)
                self.assertEqual(os.environ.get("KNOWLEDGE_DB_MOCK_EMBEDDING"), "1")
                obj_storage = sb_obj_dir / ".storage.local" / "knowledge-db"
                self.assertTrue((obj_storage / "indices").is_dir())
                self.assertTrue((obj_storage / "bundles").is_dir())
                self.assertTrue((obj_storage / "models").is_dir())
                self.assertTrue((sb_obj_dir / ".cache" / "knowledge-db").is_dir())

                hook_dev.on_test_teardown(ctx_obj)
                self.assertNotIn("KNOWLEDGE_DB_MOCK_EMBEDDING", os.environ)
        finally:
            if prev_mock is None:
                os.environ.pop("KNOWLEDGE_DB_MOCK_EMBEDDING", None)
            else:
                os.environ["KNOWLEDGE_DB_MOCK_EMBEDDING"] = prev_mock

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_options_extraction_and_orthogonal_filter(self):
        """驗證 CLI options 正確提取純字串值，且 --space / --ftype / --kind / --lang 正交篩選結果精確"""
        # 1. 驗證 --space core --ftype py：僅回傳 core 空間內的 .py 檔，排除 docs 空間的 pid_guide.md
        ret, out_core_py, _ = self._run_cli(
            [
                "search",
                "PIDController",
                "--space",
                "core",
                "--ftype",
                "py",
                "--lexical-only",
                "--detail",
                "--json",
            ]
        )
        self.assertEqual(ret, 0)
        core_py_data = json.loads(out_core_py)
        self.assertGreaterEqual(len(core_py_data["results"]), 1)
        for f_res in core_py_data["results"]:
            self.assertTrue(f_res["file_path"].endswith(".py"))
            self.assertNotIn("pid_guide.md", f_res["file_path"])
            if "spaces" in f_res:
                self.assertIn("core", f_res["spaces"])

        # 2. 驗證 --kind class --lang python --limit 3：僅保留 class 符號，排除 compute_pid_step (function)
        ret_cls, out_cls, _ = self._run_cli(
            [
                "search",
                "PIDController",
                "--kind",
                "class",
                "--lang",
                "python",
                "--limit",
                "3",
                "--json",
            ]
        )
        self.assertEqual(ret_cls, 0)
        data_cls = json.loads(out_cls)
        self.assertGreaterEqual(len(data_cls["results"]), 1)
        self.assertLessEqual(len(data_cls["results"]), 3)
        for f_res in data_cls["results"]:
            self.assertTrue(f_res["file_path"].endswith(".py"))
            for sym_item in f_res["items"]:
                self.assertEqual(sym_item["kind"], "class")

        # 3. 驗證 search -s --json 截斷提示透過 core.locale 與 agent_tool.file_read_range 動態替換
        mock_target = UnifiedSymbol(
            id="t1",
            name="Panel.UpdateLayout",
            kind="method",
            file_path="src/Panel.cs",
            line_number=10,
            end_line=20,
            language="c_sharp",
            signature="void UpdateLayout()",
        )
        long_cs = CodeSnippet(
            start_line=10,
            end_line=25,
            target_line=10,
            lines=[(i, f"line_{i} = {i}") for i in range(10, 26)],
        )
        mock_search_res = [
            AggregatedFileResult(
                file_path="src/Panel.cs",
                total_score=99.0,
                language="c_sharp",
                spaces=["source"],
                items=[
                    AggregatedItem(
                        symbol=mock_target,
                        score=99.0,
                        matched_terms=["UpdateLayout"],
                        code_snippet=long_cs,
                    )
                ],
            )
        ]
        old_yscb_loc = os.environ.get("YSCB_LOCALE")
        try:
            os.environ["YSCB_LOCALE"] = "nouns-claude,zh"
            with patch(
                "knowledge_db.engine.KnowledgeEngine.search",
                return_value=mock_search_res,
            ):
                ret_tr, out_tr, _ = self._run_cli(
                    [
                        "search",
                        "Panel.UpdateLayout",
                        "-s",
                        "--max-snippet-lines",
                        "5",
                        "--json",
                    ]
                )
            self.assertEqual(ret_tr, 0)
            trunc_payload = json.loads(out_tr)
            all_codes = [
                itm.get("code", "")
                for r in trunc_payload.get("results", [])
                for itm in r.get("items", [])
                if itm.get("truncated")
            ]
            self.assertEqual(len(all_codes), 1)
            self.assertIn("use Read (offset/limit) to view", all_codes[0])

            # 4. 驗證未安裝 agents-workflow 時，隱藏 AI Agent 專用導引提示與 [GUARD] 警告
            with patch(
                "knowledge_db.config.is_agents_workflow_installed", return_value=False
            ), patch(
                "knowledge_db.engine.KnowledgeEngine.search",
                return_value=mock_search_res,
            ):
                ret_no_aw, out_no_aw, _ = self._run_cli(
                    [
                        "search",
                        "Panel.UpdateLayout",
                        "-s",
                        "--max-snippet-lines",
                        "5",
                        "--json",
                    ]
                )
                self.assertEqual(ret_no_aw, 0)
                no_aw_payload = json.loads(out_no_aw)
                no_aw_codes = [
                    itm.get("code", "")
                    for r in no_aw_payload.get("results", [])
                    for itm in r.get("items", [])
                    if itm.get("truncated")
                ]
                self.assertEqual(len(no_aw_codes), 1)
                self.assertIn("truncated", no_aw_codes[0])
                self.assertNotIn("use ", no_aw_codes[0])
                self.assertNotIn("to view", no_aw_codes[0])

            with tempfile.TemporaryDirectory() as empty_model_dir:
                with patch(
                    "knowledge_db.embedding.is_agents_workflow_installed",
                    return_value=False,
                ):
                    err_buf = io.StringIO()
                    with contextlib.redirect_stderr(err_buf):
                        svc_no_aw = EmbeddingService(
                            cache_dir=Path(empty_model_dir),
                            mock_mode=False,
                            enable_vector_search=True,
                        )
                        svc_no_aw._init_model()
                    self.assertNotIn("[GUARD]", err_buf.getvalue())
        finally:
            if old_yscb_loc is None:
                os.environ.pop("YSCB_LOCALE", None)
            else:
                os.environ["YSCB_LOCALE"] = old_yscb_loc

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_migration_1_2_1_x(self):
        """驗證 scripts/migrations/1.2.1.x.py 搬移非 .lock 檔、保留 .lock 檔、衝突覆寫與冪等性"""
        mig_mod = load_script_module("migrations/1.2.1.x.py")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_cache = root / ".cache" / "knowledge-db"
            storage_local = root / ".storage.local" / "knowledge-db"

            (legacy_cache / "models" / "sub").mkdir(parents=True)
            (legacy_cache / "indices").mkdir(parents=True)
            (legacy_cache / "bundles").mkdir(parents=True)

            # 1. 非 .lock 檔案 (含子目錄) 與 .lock 鎖檔
            (legacy_cache / "models" / "sub" / "model.onnx").write_bytes(b"onnx_data")
            (legacy_cache / "indices" / "unified.index.bin.gz").write_bytes(b"idx_data")
            (legacy_cache / "indices" / ".kdb_index.lock").write_text(
                "locked", encoding="utf-8"
            )
            (legacy_cache / "bundles" / "conflict.json").write_text(
                "old_bundle", encoding="utf-8"
            )

            # 2. 預先在目標區建立同名衝突檔
            (storage_local / "bundles").mkdir(parents=True)
            (storage_local / "bundles" / "conflict.json").write_text(
                "new_bundle", encoding="utf-8"
            )

            ok = mig_mod.migrate(
                {"yscb_dir": str(root), "storage_local_dir": str(storage_local)}
            )
            self.assertTrue(ok)

            # 非 .lock 檔已搬移至 storage_local
            self.assertTrue(
                (storage_local / "models" / "sub" / "model.onnx").is_file()
            )
            self.assertTrue(
                (storage_local / "indices" / "unified.index.bin.gz").is_file()
            )

            # 同名衝突保留目標區新檔，且刪除舊檔、清空空目錄 bundles
            self.assertEqual(
                (storage_local / "bundles" / "conflict.json").read_text(
                    encoding="utf-8"
                ),
                "new_bundle",
            )
            self.assertFalse((legacy_cache / "bundles").exists())

            # .lock 檔案保留於原處
            self.assertTrue((legacy_cache / "indices" / ".kdb_index.lock").is_file())

            # 再次執行驗證冪等性
            self.assertTrue(
                mig_mod.migrate(
                    {"yscb_dir": str(root), "storage_local_dir": str(storage_local)}
                )
            )

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
