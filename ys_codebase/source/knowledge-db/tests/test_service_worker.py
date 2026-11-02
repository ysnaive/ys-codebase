"""
Tests for Knowledge-DB Space Event Hook (`scripts/hook.file-space.py`), Server Pre-warm Hook,
and mtime Cache Synchronization.
"""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.pipeline import HotPatchResult, IndexingPipeline, _GLOBAL_INDEX_CACHE
from knowledge_db.retrieval import InvertedIndex
from knowledge_db.schema import SymbolKind, UnifiedSymbol
from knowledge_db.tokenizer import MultilingualTokenizer
from scripts.cli import get_engine
from file_space import FileSpaceConfig


def process(args: list) -> int:
    from core.commands.dispatcher import dispatch
    return dispatch(["knowledge-db"] + list(args))


def _load_hook_module(script_name: str):
    hook_path = Path(_pkg_root) / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(script_name.replace(".", "_"), hook_path)
    hook_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook_mod)
    return hook_mod


class TestSpaceEventHookAndCacheSync(YSCBTestCase):
    """驗證 hook.file-space.py + consume_diff 事件熱修補、Server 預熱與 mtime 快取自愈"""

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
    def test_hook_file_space_on_file_space_changed_end_to_end(self):
        """驗證 scripts/hook.file-space.py 接收 on_file_space_changed 事件時透過 consume_diff 觸發熱修補與游標推進"""
        hook_file_space = _load_hook_module("hook.file-space.py")

        src_dir = self.root_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        storage_dir = self.root_path / "storage"

        f1 = src_dir / "alpha.py"
        f1.write_text("class AlphaComponent:\n    def execute(self): pass\n", encoding="utf-8")

        sp = FileSpaceConfig(name="main", include=[str(src_dir)])
        engine = KnowledgeEngine(
            storage_dir=storage_dir,
            contributes_data={"spaces": {"main": sp.to_dict()}},
            embedding_mock_mode=True,
        )

        # 1. 當基礎索引尚未建立時，收到 on_file_space_changed 自動觸發初次建置並對齊游標
        res_init = hook_file_space.on_file_space_changed({"engine": engine, "space_name": "main"})
        self.assertIn(res_init["status"], ("rebuilt", "patched"))
        self.assertEqual(len(engine.search("AlphaComponent", auto_rebuild=False)), 1)

        # 2. 無變更時再次觸發 on_file_space_changed -> noop
        res_noop = hook_file_space.on_file_space_changed({"engine": engine, "space_name": "main"})
        self.assertEqual(res_noop["status"], "noop")
        self.assertEqual(res_noop["patched_count"], 0)

        # 3. 修改檔案並新增符號後，觸發 on_file_space_changed -> 執行 4 階段增量熱修補
        time.sleep(0.05)
        f1.write_text(
            "class AlphaComponent:\n    def execute(self): pass\n"
            "class BetaHotPatched:\n    def run_hot(self): pass\n",
            encoding="utf-8",
        )
        res_patch = hook_file_space.on_file_space_changed({"engine": engine, "space_name": "main"})
        self.assertEqual(res_patch["status"], "patched")
        self.assertGreaterEqual(res_patch["patched_count"], 1)

        # 驗證無須再次掃描，記憶體與磁碟索引皆已包含新符號
        hits = engine.search("BetaHotPatched", auto_rebuild=False)
        self.assertEqual(len(hits), 1)
        sym_names = [it.symbol.name for it in hits[0].items]
        self.assertIn("BetaHotPatched", sym_names)

        # 4. 驗證游標已於 with consume_diff 區塊結束後自動 ack，再次呼叫為 noop
        res_after = hook_file_space.on_file_space_changed({"engine": engine, "space_name": "main"})
        self.assertEqual(res_after["status"], "noop")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hook_file_space_fallback_to_rebuild_when_hot_patch_fails(self):
        """驗證當 hot_patch_unified_index 返回失敗時，hook.file-space.py 安全退回 build_unified_index(allow_parallel=False)"""
        hook_file_space = _load_hook_module("hook.file-space.py")

        src_dir = self.root_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        storage_dir = self.root_path / "storage"

        f1 = src_dir / "service.py"
        f1.write_text("class BaseService:\n    pass\n", encoding="utf-8")

        sp = FileSpaceConfig(name="main", include=[str(src_dir)])
        engine = KnowledgeEngine(
            storage_dir=storage_dir,
            contributes_data={"spaces": {"main": sp.to_dict()}},
            embedding_mock_mode=True,
        )
        engine.build_unified_index(force=True)

        time.sleep(0.05)
        f1.write_text("class BaseService:\n    pass\nclass FallbackRebuiltService:\n    pass\n", encoding="utf-8")

        with patch.object(
            engine.pipeline,
            "hot_patch_unified_index",
            return_value=HotPatchResult(success=False, patched_count=0),
        ), patch.object(
            engine.pipeline,
            "build_unified_index",
            wraps=engine.pipeline.build_unified_index,
        ) as spy_rebuild:
            res = hook_file_space.on_file_space_changed({"engine": engine, "space_name": "main"})
            self.assertEqual(res["status"], "rebuilt")
            spy_rebuild.assert_called_once_with(force=True, allow_parallel=False)

        self.assertEqual(len(engine.search("FallbackRebuiltService", auto_rebuild=False)), 1)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_no_daemon(self):
        """驗證 scripts/cli.py 無 daemon 子命令且 --help 中無殘留"""
        import io
        from contextlib import redirect_stderr, redirect_stdout

        f_out = io.StringIO()
        with redirect_stdout(f_out):
            ret = process(["--help"])
        self.assertEqual(ret, 0)
        out_text = f_out.getvalue()
        self.assertNotIn("knowledge-db daemon", out_text)

        f_err = io.StringIO()
        with redirect_stderr(f_err):
            try:
                ret2 = process(["daemon", "status"])
            except Exception:
                ret2 = 1
        self.assertNotEqual(ret2, 0)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_pre_warm_eager_load(self):
        """驗證 KnowledgeEngine.pre_warm 支援提前加載索引快取與 FastEmbed 模型"""
        with patch.object(IndexingPipeline, "_ensure_indices_loaded") as mock_load:
            KnowledgeEngine.pre_warm(workspace_root=self.root_path)
            self.assertTrue(mock_load.called)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_mtime_cache_invalidation(self):
        """驗證 _GLOBAL_INDEX_CACHE 與 _ensure_indices_loaded 透過微秒級 mtime 比對熱刷新"""
        indices_dir = self.root_path / "indices"
        indices_dir.mkdir(parents=True, exist_ok=True)
        bin_file = indices_dir / "unified.index.bin.gz"

        idx = InvertedIndex()
        idx.save_binary(bin_file)
        mtime1 = bin_file.stat().st_mtime

        sm = MagicMock()
        pipeline = IndexingPipeline(
            space_manager=sm,
            bundler=MagicMock(),
            scanner=MagicMock(),
            tokenizer=MagicMock(),
            bm25_engine=MagicMock(),
            embedding_service=MagicMock(),
            hybrid_engine=MagicMock(),
            storage_dir=self.root_path,
        )

        pipeline._ensure_indices_loaded(load_graph=False, load_vectors=False)
        self.assertIsNotNone(pipeline.unified_index)
        self.assertEqual(_GLOBAL_INDEX_CACHE["unified_mtime"], mtime1)

        time.sleep(0.01)
        idx2 = InvertedIndex()
        idx2.doc_count = 42
        idx2.save_binary(bin_file)
        mtime2 = bin_file.stat().st_mtime
        self.assertGreater(mtime2, mtime1)

        pipeline._ensure_indices_loaded(load_graph=False, load_vectors=False)
        self.assertEqual(pipeline.unified_index.doc_count, 42)
        self.assertEqual(_GLOBAL_INDEX_CACHE["unified_mtime"], mtime2)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_singleton_engine(self):
        """驗證 KnowledgeEngine 單例化：get_engine() 多次調用返回同一實例物件"""
        e1 = get_engine()
        e2 = get_engine()
        self.assertIs(e1, e2)
        self.assertIsInstance(e1, KnowledgeEngine)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hook_server_no_duplicate_watcher(self):
        """驗證 scripts/hook.server.py 僅執行 pre_warm，不啟動私有 watcher 實例，且支援 on_server_worker_warming"""
        hook_mod = _load_hook_module("hook.server.py")
        self.assertFalse(hasattr(hook_mod, "_watcher_instance"))
        ret = hook_mod.on_worker_warming({"workspace_root": str(self.root_path)})
        self.assertEqual(ret, "warming_started")
        ret2 = hook_mod.on_server_worker_warming({"workspace_root": str(self.root_path)})
        self.assertEqual(ret2, "warming_started")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_wait_until_worker_idle_cross_process_does_not_busy_spin(self):
        """FR-04, EC-05, NFR-01 (AUD-10): Verify wait_until_worker_idle sleeps instead of busy-spinning when _IDLE_EVENT is set locally."""
        from knowledge_db import service as svc_mod

        indices_dir = self.root_path / "indices_spin_test"
        indices_dir.mkdir(parents=True, exist_ok=True)
        svc_mod._IDLE_EVENT.set()

        call_count = {"n": 0}

        def _fake_busy_ms(_dir):
            call_count["n"] += 1
            return 50

        with patch.object(svc_mod, "get_worker_busy_ms", side_effect=_fake_busy_ms):
            res = svc_mod.wait_until_worker_idle(indices_dir, timeout_ms=60)
            self.assertFalse(res)
            self.assertLessEqual(call_count["n"], 10)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_concurrent_serialization_safety(self):
        """驗證多執行緒同時執行 InvertedIndex.to_dict() 與並發變異之安全性"""
        idx = InvertedIndex()
        tok = MultilingualTokenizer()
        for i in range(50):
            sym = UnifiedSymbol(
                id=f"test.py::func_{i}",
                name=f"func_{i}",
                kind=SymbolKind.FUNCTION,
                language="python",
                file_path="test.py",
                line_number=i + 1,
                end_line=i + 2,
                signature=f"def func_{i}():",
                docstring="doc",
                metadata={"spaces": ["default"]},
            )
            idx.add_symbol(sym, tok)

        errors = []
        stop_evt = threading.Event()

        def mutate_loop():
            counter = 100
            while not stop_evt.is_set():
                try:
                    s = UnifiedSymbol(
                        id=f"test.py::dyn_{counter}",
                        name=f"dyn_{counter}",
                        kind=SymbolKind.FUNCTION,
                        language="python",
                        file_path="test.py",
                        line_number=1,
                        end_line=2,
                        signature="def dyn():",
                        docstring="",
                        metadata={"spaces": ["default"]},
                    )
                    idx.symbols[s.id] = s
                    idx.index[f"term_{counter}"] = []
                    if counter > 110:
                        idx.symbols.pop(f"test.py::dyn_{counter - 10}", None)
                        idx.index.pop(f"term_{counter - 10}", None)
                    counter += 1
                except Exception as e:
                    errors.append(e)

        t_mut = threading.Thread(target=mutate_loop, daemon=True)
        t_mut.start()
        try:
            for _ in range(30):
                d = idx.to_dict()
                self.assertIn("symbols", d)
        except Exception as e:
            errors.append(e)
        finally:
            stop_evt.set()
            t_mut.join(timeout=1.0)

        self.assertEqual(errors, [], f"Concurrent to_dict raised: {errors}")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_is_worker_busy_probe_and_dynamic_tolerance_degradation(self):
        """驗證 is_worker_busy() -> int (已運行 ms) 探針、>= timeout_ms 0ms 瞬時降級、< timeout_ms 剩餘時間等待與陳舊 PID 清理"""
        import contextlib
        import io
        from knowledge_db.service import (
            clear_worker_state,
            get_worker_busy_ms,
            write_worker_state,
        )

        src_dir = self.root_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        storage_dir = self.root_path / "storage"
        (src_dir / "core_mod.py").write_text(
            "class VectorTargetNode:\n    '''核心向量測試節點'''\n    def compute(self): pass\n",
            encoding="utf-8",
        )
        sp = FileSpaceConfig(name="main", include=[str(src_dir)])
        engine = KnowledgeEngine(
            storage_dir=storage_dir,
            local_config={"knowledge-db": {"jit_vector_timeout_ms": 500, "enable_vector_search": True}},
            contributes_data={"spaces": {"main": sp.to_dict()}},
            embedding_mock_mode=True,
        )
        engine.build_unified_index(force=True)
        indices_dir = engine.pipeline.get_indices_dir()

        # 1. 空閒時 is_worker_busy() == 0
        clear_worker_state(indices_dir, worker_running=True)
        self.assertEqual(engine.is_worker_busy(), 0)

        # 2. 當已運行時間 >= jit_vector_timeout_ms (例如已忙碌 1200ms >= 500ms)，前台等待 0ms 瞬時降級純 BM25 並印出提示
        write_worker_state(
            indices_dir,
            busy=True,
            start_ts=time.time() - 1.2,
            phase="downloading_model",
            progress="下載中",
            worker_running=True,
        )
        self.assertGreaterEqual(engine.is_worker_busy(), 1000)

        err_buf = io.StringIO()
        t0 = time.perf_counter()
        with contextlib.redirect_stderr(err_buf):
            hits = engine.search("VectorTargetNode", auto_rebuild=False)
        elapsed_wait_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(len(hits), 1)
        self.assertLess(elapsed_wait_ms, 150.0, "Should degrade immediately without waiting full timeout")
        self.assertIn("[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]", err_buf.getvalue())

        # 3. 當 0 < elapsed_ms < timeout_ms 且後台在剩餘時間內完成，前台等待至完成後不降級
        write_worker_state(
            indices_dir,
            busy=True,
            start_ts=time.time() - 0.1,
            phase="stage2_vector_microbatch",
            progress="1/2",
            worker_running=True,
        )

        def _finish_soon():
            time.sleep(0.08)
            clear_worker_state(indices_dir, worker_running=True)

        threading.Thread(target=_finish_soon, daemon=True).start()
        err_buf2 = io.StringIO()
        with contextlib.redirect_stderr(err_buf2):
            hits2 = engine.search("VectorTargetNode", auto_rebuild=False)
        self.assertEqual(len(hits2), 1)
        self.assertNotIn("[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]", err_buf2.getvalue())
        self.assertEqual(engine.is_worker_busy(), 0)

        # 4. EC-01: 若狀態檔內 PID 已不存在 (死進程殘留)，自動視為空閒 0ms 並清理
        state_file = indices_dir / ".kdb_worker_state.json"
        import json
        state_file.write_text(
            json.dumps({
                "worker_running": True,
                "busy": True,
                "start_ts": time.time() - 0.1,
                "pid": 99999999,
                "phase": "stage2",
            }),
            encoding="utf-8",
        )
        self.assertEqual(get_worker_busy_ms(indices_dir), 0)
        self.assertFalse(state_file.exists())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_knowledge_db_service_worker_two_stage_and_auto_model_download(self):
        """驗證 KnowledgeDBServiceWorker 兩階段背景管線 (Stage 1 快篩 + Stage 2 微批次向量差集補齊) 與背景自動下載模型"""
        import contextlib
        import io
        from knowledge_db.service import KnowledgeDBServiceWorker

        src_dir = self.root_path / "src_worker"
        src_dir.mkdir(parents=True, exist_ok=True)
        storage_dir = self.root_path / "storage_worker"

        for i in range(6):
            (src_dir / f"mod_{i}.py").write_text(
                f"class WorkerSymbol{i}:\n    '''符號 {i}'''\n    def run_{i}(self): return {i}\n",
                encoding="utf-8",
            )

        sp = FileSpaceConfig(name="w_space", include=[str(src_dir)])
        engine = KnowledgeEngine(
            storage_dir=storage_dir,
            local_config={"knowledge-db": {"enable_vector_search": True, "vector_batch_size": 4, "jit_vector_timeout_ms": 2000}},
            contributes_data={"spaces": {"w_space": sp.to_dict()}},
            embedding_mock_mode=True,
        )

        # 先建立不含向量的基礎索引 (模擬首次僅完成 Stage 1 或向量遺失)
        engine.pipeline.build_unified_index(force=True, skip_vectors=True)
        deficit_before = engine.pipeline.get_vector_deficit_info()
        self.assertGreater(deficit_before["missing_count"], 0)
        self.assertEqual(deficit_before["embedded_count"], 0)

        # 啟動 KnowledgeDBServiceWorker 自動在背景分批補齊向量
        worker = KnowledgeDBServiceWorker(engine=engine)
        worker.start()
        try:
            deadline = time.time() + 5.0
            while time.time() < deadline:
                info = engine.pipeline.get_vector_deficit_info()
                if info["missing_count"] == 0 and info["embedded_count"] > 0 and engine.is_worker_busy() == 0:
                    break
                time.sleep(0.05)

            deficit_after = engine.pipeline.get_vector_deficit_info()
            self.assertEqual(deficit_after["missing_count"], 0)
            self.assertEqual(deficit_after["coverage_pct"], 100.0)
            self.assertGreaterEqual(worker.get_custom_metrics()["vector_batches_processed"], 2)

            # 驗證若運行中途刪除 unified.vectors.bin.gz，_ensure_indices_loaded 與 get_vector_deficit_info 能即時感知並清空舊記憶體向量
            worker.stop()
            vec_file = engine.pipeline.get_indices_dir() / "unified.vectors.bin.gz"
            self.assertTrue(vec_file.exists())
            vec_file.unlink()
            deficit_deleted = engine.pipeline.get_vector_deficit_info()
            self.assertEqual(deficit_deleted["embedded_count"], 0)
            self.assertGreater(deficit_deleted["missing_count"], 0)

            # 驗證背景自動模型下載 (當 mock_mode=False 且 is_model_downloaded()=False 時由 Worker 自動呼叫 download_model 且不印 [GUARD])
            worker._stop_event.clear()
            engine.embedding_service.mock_mode = False
            dl_flag = {"downloaded": False}

            def _fake_is_downloaded():
                return dl_flag["downloaded"]

            def _fake_download(force: bool = False):
                dl_flag["downloaded"] = True
                engine.embedding_service.mock_mode = True
                return True

            with patch.object(engine.embedding_service, "is_model_downloaded", side_effect=_fake_is_downloaded), patch.object(
                engine.embedding_service, "download_model", side_effect=_fake_download
            ) as mock_dl:
                err_buf = io.StringIO()
                with contextlib.redirect_stderr(err_buf):
                    worker._last_download_attempt_ts = 0.0
                    worker._run_sync_cycle(engine, engine.pipeline.get_indices_dir())
                self.assertTrue(mock_dl.called)
                self.assertNotIn("[GUARD]", err_buf.getvalue())
        finally:
            engine.embedding_service.mock_mode = True
            worker.stop()

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
