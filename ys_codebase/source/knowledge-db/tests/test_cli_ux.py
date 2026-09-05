"""
Unit Tests for knowledge-db CLI UX, Flow Refactoring, Dynamic Probe, and Configurations (FT-01 ~ FT-09).
"""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock, patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_ENABLE_VECTOR_SEARCH,
    DEFAULT_JIT_VECTOR_TIMEOUT_SECONDS,
    DEFAULT_MAX_THREADS,
    KnowledgeDBConfig,
)
from knowledge_db.embedding import EmbeddingService, VectorIndex
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.formatter import TerminalStyler
from knowledge_db.pipeline import HotPatchResult, IndexingPipeline
from knowledge_db.scanner import ScanDiffDetail
from knowledge_db.schema import UnifiedSymbol
from scripts.cli import main


class TestCLIOptimizationAndUX(YSCBTestCase):
    """測試 CLI UX 與流程重構及優化 (FT-01 ~ FT-09)"""

    @require(Requirement.LOGIC)
    def test_enable_vector_search_config(self):
        """FT-01: 驗證 Local/Project Config 向量開關 (enable_vector_search=false) 正確跳過 FastEmbed 且以純 BM25 檢索"""
        # 1. 測試預設值為 True
        cfg_default = KnowledgeDBConfig()
        self.assertTrue(cfg_default.enable_vector_search)

        # 2. 測試 local_config 顯式傳入 False
        cfg_disabled = KnowledgeDBConfig.load(
            local_config={"knowledge-db": {"enable_vector_search": False}}
        )
        self.assertFalse(cfg_disabled.enable_vector_search)

        # 3. 測試字串 "false", "off", "0" 防呆解析
        for val in ["false", "0", "no", "off", "False"]:
            cfg_str = KnowledgeDBConfig.load(local_config={"knowledge-db": {"enable_vector_search": val}})
            self.assertFalse(cfg_str.enable_vector_search)

        # 4. 驗證 Engine 注入與 Pipeline 向量跳過
        engine = KnowledgeEngine(
            embedding_mock_mode=True,
            local_config={"knowledge-db": {"enable_vector_search": False}},
        )
        self.assertFalse(engine.config.enable_vector_search)
        self.assertFalse(engine.pipeline.config.enable_vector_search)

        # 5. 驗證 build_unified_index 在 enable_vector_search=False 時跳過向量建立
        stages_called = []
        def reporter(stg, name, elapsed):
            stages_called.append((stg, name))

        engine.build_unified_index(force=True, progress_callback=reporter)
        # Stage 4 應標記為略過
        stage4 = [name for stg, name in stages_called if stg == 4]
        self.assertTrue(len(stage4) > 0)
        self.assertIn("略過", stage4[0])

    @require(Requirement.LOGIC)
    def test_embedding_model_config_and_fallback(self):
        """FT-02: 驗證模型自訂配置 (embedding_model) 載入與白名單預檢，非法名稱平滑降級"""
        # 1. 自訂合法模型載入
        custom_model = "BAAI/bge-small-zh-v1.5"
        cfg = KnowledgeDBConfig.load(
            local_config={"knowledge-db": {"embedding_model": custom_model}}
        )
        self.assertEqual(cfg.embedding_model, custom_model)

        # 2. 非法或不存在之模型平滑處理 (EC-01)
        srv = EmbeddingService(model_name="nonexistent/fake-model-xyz", mock_mode=True)
        self.assertIsNotNone(srv)
        self.assertEqual(srv.model_name, "nonexistent/fake-model-xyz")

        # 3. 驗證支援清單查詢介面存在且不拋錯
        models = EmbeddingService.list_supported_models()
        self.assertIsInstance(models, list)
        self.assertTrue(len(models) > 0)

    @require(Requirement.LOGIC)
    def test_vector_index_model_mismatch_invalidation(self):
        """FT-03: 驗證模型切換時向量快取維度/名稱不符自動標記失效並降級 (EC-02)"""
        # 1. 建立具有檔頭元資料之 VectorIndex
        import numpy as np
        vec_idx = VectorIndex(model_name="BAAI/bge-small-zh-v1.5", dim=384)
        doc_ids = ["sym_1", "sym_2"]
        vecs = np.random.randn(2, 384).astype(np.float32)
        vec_idx.build(doc_ids, vecs)

        # 2. 相容性校驗：相同模型與維度
        self.assertTrue(vec_idx.is_compatible_with("BAAI/bge-small-zh-v1.5", 384))

        # 3. 不相容校驗：維度不符
        self.assertFalse(vec_idx.is_compatible_with("BAAI/bge-small-zh-v1.5", 512))

        # 4. 不相容校驗：模型名稱不符
        self.assertFalse(vec_idx.is_compatible_with("other/model-name", 384))

        # 5. 持久化與反序列化檔頭檢驗
        with tempfile.TemporaryDirectory() as tmpdir:
            f_path = Path(tmpdir) / "test_vec.bin.gz"
            vec_idx.save_binary(f_path)
            loaded_idx = VectorIndex.load_binary(f_path)
            self.assertEqual(loaded_idx.model_name, "BAAI/bge-small-zh-v1.5")
            self.assertEqual(loaded_idx.dim, 384)
            self.assertEqual(len(loaded_idx.doc_ids), 2)

    @require(Requirement.LOGIC)
    def test_jit_dynamic_probe_and_fuse(self):
        """FT-04: 驗證 JIT 10 符號動態探針推估與熔斷降級邏輯 (FR-03, EC-03)"""
        # 1. 測試 HotPatchResult 資料結構契約
        res_ok = HotPatchResult(True, False, None)
        self.assertTrue(res_ok)
        self.assertTrue(res_ok.success)
        self.assertFalse(res_ok.vector_degraded)
        self.assertIsNone(res_ok.degrade_notice)

        # 解構支援
        success, degraded, notice = res_ok
        self.assertTrue(success)
        self.assertFalse(degraded)

        # 2. 測試動態探針函式
        srv = EmbeddingService(mock_mode=True)
        texts = [f"symbol_{i} test signature" for i in range(15)]
        probe_vecs, est_total = srv.embed_texts_probe(texts[:10], total_count=15)
        self.assertIsNotNone(probe_vecs)
        self.assertEqual(len(probe_vecs), 10)
        self.assertGreater(est_total, 0.0)

        # 3. 測試熔斷情境：超時臨界值設定為極小 (0.00001s)
        engine = KnowledgeEngine(embedding_mock_mode=True)
        engine.build_unified_index(force=True)

        # 模擬建立待更新 diff
        diff = ScanDiffDetail(
            added={"test_diff.py"},
            modified=set(),
            deleted=set(),
        )
        # 模擬 20 個符號
        mock_symbols = [
            UnifiedSymbol(
                id=f"test_diff.py:sym_{i}",
                name=f"sym_{i}",
                kind="function",
                file_path="test_diff.py",
                line_number=i + 1,
                signature=f"def sym_{i}()",
                docstring="Doc",
                language="python",
                metadata={"spaces": ["core"]},
            )
            for i in range(20)
        ]

        with patch.object(engine.pipeline.bundler, "bundle_dirty_files", return_value=({"test_diff.py": mock_symbols}, ["test_diff.py"])):
            # 設定 timeout_seconds 為 0.000001 強制觸發熔斷
            res = engine.pipeline.hot_patch_unified_index(
                diff_detail=diff,
                full_files_map={"test_diff.py": (100.0, 500)},
                timeout_seconds=0.000001,
            )
            self.assertTrue(res.success)
            self.assertTrue(res.vector_degraded)
            self.assertIsNotNone(res.degrade_notice)
            self.assertIn("熔斷降級", res.degrade_notice)
            self.assertIn("knowledge-db:notice", res.degrade_notice)

    @require(Requirement.LOGIC)
    def test_dual_track_progress_reporter(self):
        """FT-05: 驗證手動 index 雙軌進度呈現與各階段耗時回呼 (FR-04)"""
        engine = KnowledgeEngine(embedding_mock_mode=True)
        stages = []

        def on_progress(stage, name, elapsed):
            stages.append((stage, name, elapsed))

        # 執行 5 階段 build_unified_index
        stderr_buf = io.StringIO()
        with contextlib.redirect_stderr(stderr_buf):
            engine.build_unified_index(force=True, interactive=True, progress_callback=on_progress)

        # 驗證 5 大階段均被回呼
        stage_nums = [s[0] for s in stages]
        self.assertEqual(stage_nums, [1, 2, 3, 4, 5])

        # 驗證 stderr 包含進度輸出
        output = stderr_buf.getvalue()
        self.assertIn("[1/5] AST 符號解析與全域打包", output)
        self.assertIn("[2/5] BM25 倒排索引建置", output)
        self.assertIn("[3/5] 雙向調用圖譜建置", output)
        self.assertIn("[4/5] 向量特徵嵌入", output)
        self.assertIn("[5/5] 二進位索引與快照原子持久化", output)
        self.assertIn("總耗時", output)

    @require(Requirement.LOGIC)
    def test_help_and_status_recognition(self):
        """FT-06: 驗證 knowledge-db --help 包含 index 說明，且 status 能正確識別 unified.index.bin.gz (FR-05)"""
        # 1. 驗證 --help 說明文字
        stdout_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf):
            self.assertEqual(main(["--help"]), 0)
        help_out = stdout_buf.getvalue()
        self.assertIn("python yscb.py knowledge-db index", help_out)
        self.assertIn("status", help_out)

        # 2. 建置全域索引並驗證 status
        engine = KnowledgeEngine(embedding_mock_mode=True)
        engine.build_unified_index(force=True)
        st = engine.status()

        self.assertTrue(st.get("has_unified_index"))
        for sp_name, sp in st["spaces"].items():
            self.assertTrue(sp["has_index"])

        # 3. 驗證 status 指令輸出
        status_buf = io.StringIO()
        with contextlib.redirect_stdout(status_buf):
            self.assertEqual(main(["status"]), 0)
        status_out = status_buf.getvalue()
        self.assertIn("已建立", status_out)
        self.assertIn("全域倒排索引: 已建立", status_out)

    @require(Requirement.LOGIC)
    def test_json_stdout_purity_and_hf_warning_suppression(self):
        """FT-07: 驗證 HF Hub 警告屏蔽生效，且 --json 輸出時 stdout 為純淨 JSON (FR-06, EC-06)"""
        # 1. 驗證 HF 警告抑制環境變數生效
        srv = EmbeddingService(mock_mode=True)
        self.assertEqual(os.environ.get("HF_HUB_DISABLE_IMPLICIT_TOKEN"), "1")
        self.assertEqual(os.environ.get("HF_HUB_ENABLE_HF_TRANSFER"), "0")

        # 2. 驗證 search --json 時 stdout 純淨度
        engine = KnowledgeEngine(embedding_mock_mode=True)
        engine.build_unified_index(force=True)

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            ret = main(["search", "test", "--json", "--limit=3"])
            self.assertEqual(ret, 0)

        raw_stdout = stdout_buf.getvalue().strip()
        self.assertTrue(len(raw_stdout) > 0)

        # 斷言 stdout 為 100% 合法 JSON，無任何非 JSON 前綴雜訊
        parsed = json.loads(raw_stdout)
        self.assertIn("query", parsed)
        self.assertIn("results", parsed)

    @require(Requirement.LOGIC)
    def test_terminal_styler_no_color(self):
        """FT-08: 驗證 ANSI 終端著色與 NO_COLOR / 非 TTY 自動去色機制 (FR-07, EC-05)"""
        # 1. 模擬 TTY 啟用且 NO_COLOR 未設定
        fake_tty = MagicMock()
        fake_tty.isatty.return_value = True

        with patch.dict(os.environ, {}, clear=True):
            styler_color = TerminalStyler(stream=fake_tty)
            self.assertTrue(styler_color.enabled)
            self.assertIn("\033[94m", styler_color.path("test.py"))
            self.assertIn("\033[92m", styler_color.symbol("my_func"))
            self.assertIn("\033[93m", styler_color.kind("FUNCTION"))
            self.assertIn("\033[96m", styler_color.line("Line 10"))
            self.assertIn("\033[1;93m", styler_color.warn("warning"))
            self.assertIn("\033[1;91m", styler_color.err("error"))

        # 2. 模擬設定 NO_COLOR=1 自動去色
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            styler_no_color = TerminalStyler(stream=fake_tty)
            self.assertFalse(styler_no_color.enabled)
            self.assertEqual(styler_no_color.path("test.py"), "test.py")
            self.assertEqual(styler_no_color.symbol("my_func"), "my_func")
            self.assertEqual(styler_no_color.kind("FUNCTION"), "FUNCTION")
            self.assertEqual(styler_no_color.line("Line 10"), "Line 10")
            self.assertEqual(styler_no_color.warn("warning"), "warning")
            self.assertEqual(styler_no_color.err("error"), "error")

        # 3. 模擬非 TTY (例如導向 pipe 或檔案)
        fake_pipe = MagicMock()
        fake_pipe.isatty.return_value = False
        styler_pipe = TerminalStyler(stream=fake_pipe)
        self.assertFalse(styler_pipe.enabled)
        self.assertEqual(styler_pipe.path("test.py"), "test.py")

    @require(Requirement.LOGIC)
    def test_cpu_max_threads_adaptation(self):
        """FT-09: 驗證 CPU 調用保護配置 (max_threads auto=cpu//2 及手動數值截斷) (FR-08, EC-07)"""
        cpu_cnt = os.cpu_count() or 1
        expected_auto = max(1, cpu_cnt // 2)

        # 1. 預設 auto 解析為 cpu_count // 2
        cfg_auto = KnowledgeDBConfig(max_threads="auto")
        self.assertEqual(cfg_auto.resolve_threads(), expected_auto)

        # 2. 超過實體 CPU 數截斷至 cpu_count
        cfg_over = KnowledgeDBConfig(max_threads=99999)
        self.assertEqual(cfg_over.resolve_threads(), cpu_cnt)

        # 3. 負數或 0 回退為 auto
        cfg_zero = KnowledgeDBConfig(max_threads=0)
        self.assertEqual(cfg_zero.resolve_threads(), expected_auto)

        cfg_neg = KnowledgeDBConfig(max_threads=-4)
        self.assertEqual(cfg_neg.resolve_threads(), expected_auto)

        # 4. 非法字串回退為 auto
        cfg_bad = KnowledgeDBConfig(max_threads="invalid_number")
        self.assertEqual(cfg_bad.resolve_threads(), expected_auto)

        # 5. 合法整數指定 (例如 1)
        cfg_one = KnowledgeDBConfig(max_threads=1)
        self.assertEqual(cfg_one.resolve_threads(), 1)
