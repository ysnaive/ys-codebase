"""
Tests for Knowledge-DB Service Worker, Eager Preload, and mtime Cache Synchronization (sub_04).
"""

import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import MagicMock, patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require

from knowledge_db.service import KnowledgeDBServiceWorker, resolve_watch_extensions
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.pipeline import IndexingPipeline, _GLOBAL_INDEX_CACHE
from knowledge_db.retrieval import InvertedIndex
from scripts.cli import process, get_engine


class TestServiceWorker(YSCBTestCase):
    """sub_04 驗證：ServiceWorker 納管、預熱、mtime 快取自愈與 CLI 重構 (FT-01 ~ FT-06)"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_lifecycle(self):
        """FT-01: 驗證 KnowledgeDBServiceWorker 生命週期 (name, start, health_check, stop)"""
        worker = KnowledgeDBServiceWorker(self.root_path)
        self.assertEqual(worker.name, "knowledge-db-watcher")
        self.assertFalse(worker.health_check())

        # 啟動
        worker.start({"yscb_root": str(self.root_path)})
        self.assertTrue(worker.health_check())

        # 重複啟動無副作用
        worker.start({"yscb_root": str(self.root_path)})
        self.assertTrue(worker.health_check())

        # 停止
        worker.stop()
        self.assertFalse(worker.health_check())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_debounce_patch(self):
        """FT-02: 驗證 500ms 防抖計時器聚合檔案變更並安全觸發增量熱修補"""
        worker = KnowledgeDBServiceWorker(self.root_path)
        worker.start({"yscb_root": str(self.root_path)})

        mock_pipeline = MagicMock()
        mock_pipeline.get_indices_dir.return_value = self.root_path
        mock_pipeline.scanner.check_invalidation.return_value = (
            False, 1, "test", {}, MagicMock(has_changes=True)
        )
        mock_pipeline.hot_patch_unified_index.return_value = (True, False, None)
        worker._pipeline = mock_pipeline

        # 觸發檔案變更
        test_file = str(self.root_path / "test.py")
        worker.on_file_changed(test_file)
        self.assertIsNotNone(worker._debounce_timer)

        # 立即手動呼叫防抖修補
        worker._execute_debounced_patch()
        self.assertTrue(mock_pipeline.scanner.check_invalidation.called)
        self.assertTrue(mock_pipeline.hot_patch_unified_index.called)

        worker.stop()
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_no_daemon(self):
        """FT-03: 驗證 scripts/cli.py 徹底移除 daemon 子命令且 --help 中無殘留"""
        import io
        from contextlib import redirect_stdout, redirect_stderr

        # 1. 測試 --help
        f_out = io.StringIO()
        with redirect_stdout(f_out):
            ret = process(["--help"])
        self.assertEqual(ret, 0)
        out_text = f_out.getvalue()
        self.assertNotIn("knowledge-db daemon", out_text)

        # 2. 測試調用已移除的 daemon 指令（應被未知指令攔截或返回異常碼）
        f_err = io.StringIO()
        with redirect_stderr(f_err):
            try:
                ret2 = process(["daemon", "status"])
            except Exception:
                ret2 = 1
        # daemon 已不是合法 subcmd，不會返回 0
        self.assertNotEqual(ret2, 0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_pre_warm_eager_load(self):
        """FT-04: 驗證 KnowledgeEngine.pre_warm 支援提前加載索引快取與 FastEmbed 模型"""
        with patch.object(IndexingPipeline, "_ensure_indices_loaded") as mock_load:
            KnowledgeEngine.pre_warm(workspace_root=self.root_path)
            self.assertTrue(mock_load.called)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_mtime_cache_invalidation(self):
        """FT-05: 驗證 _GLOBAL_INDEX_CACHE 與 _ensure_indices_loaded 透過微秒級 mtime 比對熱刷新"""
        indices_dir = self.root_path / "indices"
        indices_dir.mkdir(parents=True, exist_ok=True)
        bin_file = indices_dir / "unified.index.bin.gz"

        # 寫入初始空索引快照
        idx = InvertedIndex()
        idx.save_binary(bin_file)
        mtime1 = bin_file.stat().st_mtime

        # 透過 pipeline 載入
        sm = MagicMock()
        sm.storage_dir = self.root_path
        pipeline = IndexingPipeline(
            space_manager=sm,
            bundler=MagicMock(),
            scanner=MagicMock(),
            tokenizer=MagicMock(),
            bm25_engine=MagicMock(),
            embedding_service=MagicMock(),
            hybrid_engine=MagicMock(),
        )

        pipeline._ensure_indices_loaded(load_graph=False, load_vectors=False)
        self.assertIsNotNone(pipeline.unified_index)
        self.assertEqual(_GLOBAL_INDEX_CACHE["unified_mtime"], mtime1)

        # 模擬檔案被修改（更新 mtime）
        time.sleep(0.01)
        idx2 = InvertedIndex()
        idx2.doc_count = 42
        idx2.save_binary(bin_file)
        mtime2 = bin_file.stat().st_mtime
        self.assertGreater(mtime2, mtime1)

        # 再次呼叫 _ensure_indices_loaded，驗證快取自動原地熱重載
        pipeline._ensure_indices_loaded(load_graph=False, load_vectors=False)
        self.assertEqual(pipeline.unified_index.doc_count, 42)
        self.assertEqual(_GLOBAL_INDEX_CACHE["unified_mtime"], mtime2)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_primitives_integration(self):
        """FT-06: 驗證微內核原語整合 (core.vfs.write_bytes 原子覆蓋與 core.platform.lock 互斥鎖)"""
        from core.vfs import exists, read_bytes
        from core.platform.lock import InterProcessLock
        from knowledge_db.scanner import BinarySnapshotManager

        meta_file = self.root_path / "unified.meta.bin"
        files_map = {str(self.root_path / "a.py"): (time.time(), 100)}

        BinarySnapshotManager.save(meta_file, files_map)
        self.assertTrue(exists(meta_file))
        raw = read_bytes(meta_file)
        self.assertTrue(raw.startswith(b"YFP1"))

        # 驗證 InterProcessLock 能正常保護快照
        lock_file = self.root_path / "snapshot.lock"
        with InterProcessLock(str(lock_file)) as lock:
            self.assertTrue(lock.is_locked)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_singleton_engine(self):
        """FT-02: 驗證 KnowledgeEngine 單例化：get_engine() 多次調用返回同一實例物件"""
        e1 = get_engine()
        e2 = get_engine()
        self.assertIs(e1, e2)
        self.assertIsInstance(e1, KnowledgeEngine)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_watcher_dirty_flag_stat_bypass(self):
        """FT-04: 驗證 Watcher Dirty Flag：未標記 dirty 時，pipeline.search() 0ms 跳過 stat 走訪"""
        indices_dir = self.root_path / "indices"
        indices_dir.mkdir(parents=True, exist_ok=True)
        bin_file = indices_dir / "unified.index.bin.gz"

        idx = InvertedIndex()
        idx.save_binary(bin_file)

        sm = MagicMock()
        sm.storage_dir = self.root_path
        pipeline = IndexingPipeline(
            space_manager=sm,
            bundler=MagicMock(),
            scanner=MagicMock(),
            tokenizer=MagicMock(),
            bm25_engine=MagicMock(),
            embedding_service=MagicMock(),
            hybrid_engine=MagicMock(),
        )
        pipeline._unified_index = idx

        # 模擬 Watcher 活躍且 dirty flag 不存在
        active_file = indices_dir / ".watcher_active"
        import json
        with open(active_file, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "start_time": time.time()}, f)

        dirty_file = indices_dir / ".watcher_dirty"
        if dirty_file.exists():
            dirty_file.unlink()

        # 呼叫 search，驗證 scanner.check_invalidation 未被調用（直接跳過 stat 走訪）
        pipeline.search(query="test_query", auto_rebuild=True)
        self.assertFalse(pipeline.scanner.check_invalidation.called)

        # 模擬檔案發生未防抖變更，寫入 dirty flag；Watcher 活躍期間前台搜尋依然保持 0ms 非阻塞
        with open(dirty_file, "w", encoding="utf-8") as f:
            f.write("dirty")

        pipeline.search(query="test_query", auto_rebuild=True)
        self.assertFalse(pipeline.scanner.check_invalidation.called)

        # 模擬 Watcher 停止運行（無背景服務），前台 search 恢復同步執行 check_invalidation
        active_file.unlink()
        pipeline.scanner.check_invalidation.return_value = (False, 0, "no changes", {}, MagicMock(has_changes=False))
        pipeline.search(query="test_query", auto_rebuild=True)
        self.assertTrue(pipeline.scanner.check_invalidation.called)
        self.mark_passed()
