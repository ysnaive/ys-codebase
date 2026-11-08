"""
Tests for Knowledge-DB Space Event Hook (`scripts/hook.core.py`), Server Pre-warm Hook,
and mtime Cache Synchronization.
"""

import contextlib
import io
import json
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

from core.space import SpaceConfig
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
import knowledge_db.engine as kdb_engine
import knowledge_db.pipeline as kdb_pipeline
from knowledge_db import service as svc_mod
from knowledge_db.embedding import EmbeddingService
from knowledge_db.engine import KnowledgeEngine, get_engine
from knowledge_db.pipeline import HotPatchResult, IndexingPipeline, _GLOBAL_INDEX_CACHE
from knowledge_db.retrieval import InvertedIndex
from knowledge_db.schema import SymbolKind, UnifiedSymbol
from knowledge_db.service import (
    KnowledgeDBServiceWorker,
    clear_worker_state,
    get_worker_busy_ms,
    read_worker_state,
    write_worker_state,
)
from knowledge_db.tokenizer import MultilingualTokenizer
from tests import advance_mtime, load_script_module, process, write_text_and_advance_mtime


class TestSpaceEventHookAndCacheSync(YSCBTestCase):
    """驗證 hook.core.py + consume_diff 事件熱修補、Server 預熱與 mtime 快取自愈"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self._old_global_engine = kdb_engine._GLOBAL_ENGINE_INSTANCE
        self._old_global_cache = dict(kdb_pipeline._GLOBAL_INDEX_CACHE)

    def tearDown(self):
        svc_mod._IDLE_EVENT.set()
        kdb_engine._GLOBAL_ENGINE_INSTANCE = self._old_global_engine
        with kdb_pipeline._CACHE_LOCK:
            kdb_pipeline._GLOBAL_INDEX_CACHE.clear()
            kdb_pipeline._GLOBAL_INDEX_CACHE.update(self._old_global_cache)
        self.temp_dir.cleanup()
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_hook_file_space_on_file_space_changed_end_to_end(self):
        """驗證 scripts/hook.core.py 接收 on_file_space_changed 事件時透過 consume_diff 觸發熱修補與游標推進"""
        hook_file_space = load_script_module("hook.core.py")

        src_dir = self.root_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        storage_dir = self.root_path / "storage"

        f1 = src_dir / "alpha.py"
        f1.write_text(
            "class AlphaComponent:\n    def execute(self): pass\n", encoding="utf-8"
        )

        sp = SpaceConfig(
            qualified_name="project/main",
            owner="project",
            short_name="main",
            entries=(str(src_dir),),
        )
        engine = KnowledgeEngine(
            storage_dir=storage_dir,
            contributes_data={"spaces": {"main": sp}},
            embedding_mock_mode=True,
        )

        # 1. 當基礎索引尚未建立時，收到 on_file_space_changed 自動觸發初次建置並對齊游標
        res_init = hook_file_space.on_file_space_changed(
            {"engine": engine, "space_name": "main"}
        )
        self.assertIn(res_init["status"], ("rebuilt", "patched"))
        self.assertEqual(len(engine.search("AlphaComponent", auto_rebuild=False)), 1)

        # 2. 無變更時再次觸發 on_file_space_changed -> noop
        res_noop = hook_file_space.on_file_space_changed(
            {"engine": engine, "space_name": "main"}
        )
        self.assertEqual(res_noop["status"], "noop")
        self.assertEqual(res_noop["patched_count"], 0)

        # 3. 修改檔案並新增符號後，觸發 on_file_space_changed -> 執行 4 階段增量熱修補
        write_text_and_advance_mtime(
            f1,
            "class AlphaComponent:\n    def execute(self): pass\n"
            "class BetaHotPatched:\n    def run_hot(self): pass\n",
        )
        res_patch = hook_file_space.on_file_space_changed(
            {"engine": engine, "space_name": "main"}
        )
        self.assertEqual(res_patch["status"], "patched")
        self.assertGreaterEqual(res_patch["patched_count"], 1)

        # 驗證無須再次掃描，記憶體與磁碟索引皆已包含新符號
        hits = engine.search("BetaHotPatched", auto_rebuild=False)
        self.assertEqual(len(hits), 1)
        sym_names = [it.symbol.name for it in hits[0].items]
        self.assertIn("BetaHotPatched", sym_names)

        # 4. 驗證游標已於 with consume_diff 區塊結束後自動 ack，再次呼叫為 noop
        res_after = hook_file_space.on_file_space_changed(
            {"engine": engine, "space_name": "main"}
        )
        self.assertEqual(res_after["status"], "noop")
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hook_file_space_fallback_to_rebuild_when_hot_patch_fails(self):
        """驗證當 hot_patch_unified_index 返回失敗時，hook.core.py 安全退回 build_unified_index(allow_parallel=False)"""
        hook_file_space = load_script_module("hook.core.py")

        src_dir = self.root_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        storage_dir = self.root_path / "storage"

        f1 = src_dir / "service.py"
        f1.write_text("class BaseService:\n    pass\n", encoding="utf-8")

        sp = SpaceConfig(
            qualified_name="project/main",
            owner="project",
            short_name="main",
            entries=(str(src_dir),),
        )
        engine = KnowledgeEngine(
            storage_dir=storage_dir,
            contributes_data={"spaces": {"main": sp}},
            embedding_mock_mode=True,
        )
        engine.build_unified_index(force=True)

        write_text_and_advance_mtime(
            f1,
            "class BaseService:\n    pass\nclass FallbackRebuiltService:\n    pass\n",
        )

        with patch.object(
            engine.pipeline,
            "hot_patch_unified_index",
            return_value=HotPatchResult(success=False, patched_count=0),
        ), patch.object(
            engine.pipeline,
            "build_unified_index",
            wraps=engine.pipeline.build_unified_index,
        ) as spy_rebuild:
            res = hook_file_space.on_file_space_changed(
                {"engine": engine, "space_name": "main"}
            )
            self.assertEqual(res["status"], "rebuilt")
            spy_rebuild.assert_called_once_with(force=True, allow_parallel=False)

        self.assertEqual(
            len(engine.search("FallbackRebuiltService", auto_rebuild=False)), 1
        )
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hook_file_space_queued_to_active_worker_and_diff_summary(self):
        """驗證常駐 Worker 存活時 O(1) 轉發 queued_to_worker，以及傳入 diff_summary 時傳遞 auto_refresh=False"""
        hook_file_space = load_script_module("hook.core.py")

        fake_worker = MagicMock()
        fake_worker.name = "knowledge-db-worker"
        fake_worker.is_alive.return_value = True

        with patch.object(hook_file_space, "get_active_worker", return_value=fake_worker):
            res_q = hook_file_space.on_file_space_changed(
                {"space_name": "main"}, spaces=["main"]
            )
        self.assertEqual(res_q["status"], "queued_to_worker")
        self.assertEqual(res_q["worker"], "knowledge-db-worker")
        fake_worker.notify_space_changed.assert_called_once()

        # 驗證傳入 diff_summary 時，scanner.consume_diff 收到 auto_refresh=False
        src_dir = self.root_path / "src_diff_sum"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "item.py").write_text("class DiffSumNode: pass\n", encoding="utf-8")
        sp = SpaceConfig(
            qualified_name="project/main",
            owner="project",
            short_name="main",
            entries=(str(src_dir),),
        )
        engine = KnowledgeEngine(
            storage_dir=self.root_path / "storage_diff_sum",
            contributes_data={"spaces": {"main": sp}},
            embedding_mock_mode=True,
        )
        engine.build_unified_index(force=True)

        with patch.object(
            engine.scanner, "consume_diff", wraps=engine.scanner.consume_diff
        ) as spy_consume:
            res_ds = hook_file_space.on_file_space_changed(
                {"engine": engine, "space_name": "main"},
                diff_summary={"main": 0},
            )
        self.assertEqual(res_ds["status"], "noop")
        spy_consume.assert_called_once_with(
            "main", consumer_id="knowledge-db", auto_refresh=False
        )
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_cli_no_daemon(self):
        """驗證 scripts/cli.py 無 daemon 子命令且 --help 中無殘留"""
        f_out = io.StringIO()
        with contextlib.redirect_stdout(f_out):
            ret = process(["--help"])
        self.assertEqual(ret, 0)
        out_text = f_out.getvalue()
        self.assertNotIn("knowledge-db daemon", out_text)

        f_err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            f_err
        ):
            ret2 = process(["daemon", "status"])
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

        pipeline._ensure_indices_loaded(load_vectors=False)
        self.assertIsNotNone(pipeline.unified_index)
        self.assertEqual(_GLOBAL_INDEX_CACHE["unified_mtime"], mtime1)

        old_ns = bin_file.stat().st_mtime_ns
        idx2 = InvertedIndex()
        idx2.doc_count = 42
        idx2.save_binary(bin_file)
        advance_mtime(bin_file, old_mtime_ns=old_ns)
        mtime2 = bin_file.stat().st_mtime
        self.assertGreater(mtime2, mtime1)

        pipeline._ensure_indices_loaded(load_vectors=False)
        self.assertEqual(pipeline.unified_index.doc_count, 42)
        self.assertEqual(_GLOBAL_INDEX_CACHE["unified_mtime"], mtime2)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_singleton_engine(self):
        """驗證 KnowledgeEngine 單例化：get_engine() 多次調用返回同一實例物件"""
        kdb_engine._GLOBAL_ENGINE_INSTANCE = None
        e1 = get_engine()
        e2 = get_engine()
        self.assertIs(e1, e2)
        self.assertIsInstance(e1, KnowledgeEngine)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_hook_server_no_duplicate_watcher(self):
        """驗證 scripts/hook.server.py 野執行緒已移除，背景預熱與增量索引統一由受管 KnowledgeDBServiceWorker 承擔"""
        hook_server_path = Path(_pkg_root) / "scripts" / "hook.server.py"
        self.assertFalse(
            hook_server_path.exists(),
            "scripts/hook.server.py must be removed to prevent unmanaged prewarm threads",
        )
        fs_hook_server_path = Path(_pkg_root).parent / "file-space" / "scripts" / "hook.server.py"
        self.assertFalse(
            fs_hook_server_path.exists(),
            "file-space/scripts/hook.server.py must be removed to prevent unmanaged prewarm threads",
        )

        # Verify model download CLI is marked server_compatible: false
        core_json_path = Path(_pkg_root) / "contributes" / "core.json"
        core_data = json.loads(core_json_path.read_text(encoding="utf-8"))
        dl_spec = core_data["commands"]["cmd"]["model"]["cmd"]["download"]
        self.assertIs(dl_spec.get("server_compatible"), False)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_wait_until_worker_idle_cross_process_does_not_busy_spin(self):
        """驗證 wait_until_worker_idle 於跨進程忙碌且本地 _IDLE_EVENT 已 set 時不會 busy-spin"""
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
        src_dir = self.root_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        storage_dir = self.root_path / "storage"
        (src_dir / "core_mod.py").write_text(
            "class VectorTargetNode:\n    '''核心向量測試節點'''\n    def compute(self): pass\n",
            encoding="utf-8",
        )
        sp = SpaceConfig(
            qualified_name="project/main",
            owner="project",
            short_name="main",
            entries=(str(src_dir),),
        )
        engine = KnowledgeEngine(
            storage_dir=storage_dir,
            local_config={
                "knowledge-db": {
                    "jit_vector_timeout_ms": 500,
                    "enable_vector_search": True,
                }
            },
            contributes_data={"spaces": {"main": sp}},
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
        self.assertLess(
            elapsed_wait_ms,
            150.0,
            "Should degrade immediately without waiting full timeout",
        )
        self.assertIn(
            "[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]", err_buf.getvalue()
        )

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
        self.assertNotIn(
            "[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]", err_buf2.getvalue()
        )
        self.assertEqual(engine.is_worker_busy(), 0)

        # 4. 若狀態檔內 PID 已不存在 (死進程殘留)，自動視為空閒 0ms 並清理
        state_file = indices_dir / ".kdb_worker_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "worker_running": True,
                    "busy": True,
                    "start_ts": time.time() - 0.1,
                    "pid": 99999999,
                    "phase": "stage2",
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(get_worker_busy_ms(indices_dir), 0)
        self.assertFalse(state_file.exists())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_knowledge_db_service_worker_two_stage_and_auto_model_download(self):
        """驗證 KnowledgeDBServiceWorker 兩階段背景管線 (Stage 1 快篩 + Stage 2 微批次向量差集補齊) 與背景自動下載模型"""
        src_dir = self.root_path / "src_worker"
        src_dir.mkdir(parents=True, exist_ok=True)
        storage_dir = self.root_path / "storage_worker"

        for i in range(6):
            (src_dir / f"mod_{i}.py").write_text(
                f"class WorkerSymbol{i}:\n    '''符號 {i}'''\n    def run_{i}(self): return {i}\n",
                encoding="utf-8",
            )

        sp = SpaceConfig(
            qualified_name="project/w_space",
            owner="project",
            short_name="w_space",
            entries=(str(src_dir),),
        )
        engine = KnowledgeEngine(
            storage_dir=storage_dir,
            local_config={
                "knowledge-db": {
                    "enable_vector_search": True,
                    "vector_batch_size": 4,
                    "jit_vector_timeout_ms": 2000,
                }
            },
            contributes_data={"spaces": {"w_space": sp}},
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
                if (
                    info["missing_count"] == 0
                    and info["embedded_count"] > 0
                    and engine.is_worker_busy() == 0
                ):
                    break
                time.sleep(0.05)

            deficit_after = engine.pipeline.get_vector_deficit_info()
            self.assertEqual(deficit_after["missing_count"], 0)
            self.assertEqual(deficit_after["coverage_pct"], 100.0)
            self.assertGreaterEqual(
                worker.get_custom_metrics()["vector_batches_processed"], 2
            )

            # 驗證若運行中途刪除 unified.vectors.bin.gz，_ensure_indices_loaded 與 get_vector_deficit_info 能即時感知並清空舊記憶體向量
            worker.stop()
            vec_file = engine.pipeline.get_indices_dir() / "unified.vectors.bin.gz"
            self.assertTrue(vec_file.exists())
            vec_file.unlink()
            deficit_deleted = engine.pipeline.get_vector_deficit_info()
            self.assertEqual(deficit_deleted["embedded_count"], 0)
            self.assertGreater(deficit_deleted["missing_count"], 0)

            # 驗證背景自動模型下載 (當 mock_mode=False 且 has_local_model()=False 時由 Worker 自動呼叫 download_model 且不印 [GUARD])
            worker._stop_event.clear()
            engine.embedding_service.mock_mode = False
            dl_flag = {"downloaded": False}

            def _fake_has_local():
                return dl_flag["downloaded"]

            def _fake_download(force: bool = False):
                dl_flag["downloaded"] = True
                engine.embedding_service.mock_mode = True
                return True

            with patch.object(
                engine.embedding_service,
                "has_local_model",
                side_effect=_fake_has_local,
            ), patch.object(
                engine.embedding_service, "download_model", side_effect=_fake_download
            ) as mock_dl:
                err_buf = io.StringIO()
                with contextlib.redirect_stderr(err_buf):
                    worker._last_download_attempt_ts = 0.0
                    worker._run_sync_cycle(engine, engine.pipeline.get_indices_dir())
                self.assertTrue(mock_dl.called)
                self.assertNotIn("[GUARD]", err_buf.getvalue())
                self.assertEqual(worker.state, worker.STATE_READY)

            # 驗證離線下載失敗時進入 DEGRADED_OFFLINE 狀態，且前景 search 不阻塞於 _index_lock (< 1ms 純 BM25)
            engine.embedding_service.mock_mode = False
            with patch.object(
                engine.embedding_service, "has_local_model", return_value=False
            ), patch.object(
                engine.embedding_service,
                "download_model",
                side_effect=RuntimeError("Offline network unreachable"),
            ):
                worker._last_download_attempt_ts = 0.0
                worker._run_sync_cycle(engine, engine.pipeline.get_indices_dir())
                self.assertEqual(worker.state, worker.STATE_DEGRADED_OFFLINE)
                self.assertEqual(
                    worker.get_custom_metrics()["phase"], "degraded_offline"
                )
        finally:
            engine.embedding_service.mock_mode = True
            worker.stop()

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_vector_deficit_step_lock_splitting_persist_throttling_and_removed_terms(
        self,
    ):
        """驗證 sync_vector_deficit_step 於 embed_texts 期間釋放 _index_lock、重入過濾已刪符號、支援 persist=False + flush_vector_index 與 removed_terms 精確清理"""
        src_dir = self.root_path / "src_lock_test"
        src_dir.mkdir(parents=True, exist_ok=True)
        storage_dir = self.root_path / "storage_lock_test"

        for i in range(4):
            (src_dir / f"item_{i}.py").write_text(
                f"class ItemNode{i}:\n    '''獨特測試節點 {i} unique_token_{i}'''\n    pass\n",
                encoding="utf-8",
            )

        sp = SpaceConfig(
            qualified_name="project/l_space",
            owner="project",
            short_name="l_space",
            entries=(str(src_dir),),
        )
        engine = KnowledgeEngine(
            storage_dir=storage_dir,
            local_config={
                "knowledge-db": {"enable_vector_search": True, "vector_batch_size": 2}
            },
            contributes_data={"spaces": {"l_space": sp}},
            embedding_mock_mode=True,
        )
        engine.pipeline.build_unified_index(force=True, skip_vectors=True)
        vec_file = engine.pipeline.get_indices_dir() / "unified.vectors.bin.gz"
        self.assertFalse(vec_file.exists())

        # 1. persist=False updates in-memory vector_index without writing unified.vectors.bin.gz
        res1 = engine.pipeline.sync_vector_deficit_step(batch_size=2, persist=False)
        self.assertEqual(res1["embedded_in_step"], 2)
        self.assertEqual(res1["remaining"], 2)
        self.assertTrue(engine.pipeline._vector_index_dirty)
        self.assertFalse(vec_file.exists())

        # Explicit flush_vector_index() persists to disk and clears dirty flag
        self.assertTrue(engine.pipeline.flush_vector_index())
        self.assertFalse(engine.pipeline._vector_index_dirty)
        self.assertTrue(vec_file.exists())

        # 2. Verify _index_lock is released during embed_texts and deleted symbols are filtered on re-entry
        orig_embed = engine.embedding_service.embed_texts
        lock_acquired_in_other_thread = {"ok": False}
        evicted_sid_holder = {"sid": None}

        def _hooked_embed_texts(texts, batch_size=32):
            def _probe_lock_and_evict():
                acquired = engine.pipeline._index_lock.acquire(blocking=False)
                if acquired:
                    try:
                        lock_acquired_in_other_thread["ok"] = True
                        vec_ids = set(engine.hybrid_engine.vector_index.doc_ids)
                        remaining_sids = [
                            sid
                            for sid in engine.pipeline.unified_index.symbols
                            if sid not in vec_ids
                        ]
                        if remaining_sids:
                            victim = remaining_sids[0]
                            evicted_sid_holder["sid"] = victim
                            engine.pipeline.unified_index.symbols.pop(victim, None)
                    finally:
                        engine.pipeline._index_lock.release()

            t = threading.Thread(target=_probe_lock_and_evict)
            t.start()
            t.join(timeout=1.0)
            return orig_embed(texts, batch_size=batch_size)

        with patch.object(
            engine.embedding_service, "embed_texts", side_effect=_hooked_embed_texts
        ):
            res2 = engine.pipeline.sync_vector_deficit_step(batch_size=2, persist=True)

        self.assertTrue(
            lock_acquired_in_other_thread["ok"],
            "_index_lock must not be held during embed_texts()",
        )
        self.assertIsNotNone(evicted_sid_holder["sid"])
        self.assertNotIn(
            evicted_sid_holder["sid"], engine.hybrid_engine.vector_index.doc_ids
        )
        self.assertEqual(res2["embedded_in_step"], 1)
        self.assertEqual(res2["remaining"], 0)

        # 3. Verify InvertedIndex.patch_incremental accurately prunes postings via removed_terms
        idx = engine.pipeline.unified_index
        self.assertIn("uniquetoken0", idx.index)
        idx.patch_incremental(
            dirty_file_paths={str((src_dir / "item_0.py").resolve())},
            new_symbols=[],
            tokenizer=engine.tokenizer,
            pre_aggregated=True,
        )
        self.assertNotIn("uniquetoken0", idx.index)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_has_local_model_is_fast_and_strict(self):
        """驗證 EmbeddingService.has_local_model() < 1ms 純本地嚴格檢查，且不將鬆散空目錄誤判為已下載"""
        cache_dir = self.root_path / "emb_cache_strict"
        cache_dir.mkdir(parents=True, exist_ok=True)
        svc = EmbeddingService(
            model_name="BAAI/bge-small-zh-v1.5",
            cache_dir=cache_dir,
            mock_mode=False,
        )

        t0 = time.perf_counter()
        has_before = svc.has_local_model()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.assertFalse(has_before)
        self.assertLess(elapsed_ms, 5.0)

        # 建立僅含 2 個無關檔案的子目錄（無 .onnx 權重），驗證嚴格返回 False
        fake_sub = cache_dir / "models--BAAI--bge-small-zh-v1.5"
        fake_sub.mkdir(parents=True, exist_ok=True)
        (fake_sub / "README.md").write_text("placeholder", encoding="utf-8")
        self.assertFalse(svc.has_local_model())
        self.assertFalse(svc.is_model_downloaded())

        # 建立真實結構與大於 1024 bytes 的 .onnx 檔案後應返回 True
        snap_dir = fake_sub / "snapshots" / "main"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "model_optimized.onnx").write_bytes(b"X" * 2048)
        self.assertTrue(svc.has_local_model())
        self.assertTrue(svc.is_model_downloaded())
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_stage2_auto_download_and_degraded_offline_state(self):
        """驗證 KnowledgeDBServiceWorker Stage 2 自動下載模型保留，且離線失敗時轉為 DEGRADED_OFFLINE 狀態"""
        src_dir = self.root_path / "src_offline_deg"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "mod.py").write_text("class OfflineNode:\n    pass\n", encoding="utf-8")
        storage_dir = self.root_path / "storage_offline_deg"

        sp = SpaceConfig(
            qualified_name="project/off_space",
            owner="project",
            short_name="off_space",
            entries=(str(src_dir),),
        )
        engine = KnowledgeEngine(
            storage_dir=storage_dir,
            local_config={"knowledge-db": {"enable_vector_search": True}},
            contributes_data={"spaces": {"off_space": sp}},
            embedding_mock_mode=False,
        )

        worker = KnowledgeDBServiceWorker(engine=engine)

        with patch.object(engine.embedding_service, "has_local_model", return_value=False), patch.object(
            engine.embedding_service, "download_model", return_value=False
        ) as mock_dl:
            worker._run_sync_cycle(engine, engine.pipeline.get_indices_dir())
            mock_dl.assert_called_once_with(force=False)
            self.assertEqual(worker.state, KnowledgeDBServiceWorker.STATE_DEGRADED_OFFLINE)
            st = read_worker_state(engine.pipeline.get_indices_dir())
            self.assertEqual(st.get("phase"), "degraded_offline")
            self.assertEqual(worker.get_custom_metrics().get("state"), KnowledgeDBServiceWorker.STATE_DEGRADED_OFFLINE)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_foreground_search_fast_path_skips_lock_when_worker_busy(self):
        """驗證當 unified.index.bin.gz 存在且背景 Worker 運行中或持有 _index_lock 時，前台 _ensure_jit_index_ready 走非阻塞快速路徑"""
        src_dir = self.root_path / "src_fast_path"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "fast.py").write_text("class FastPathTarget:\n    pass\n", encoding="utf-8")
        storage_dir = self.root_path / "storage_fast_path"

        sp = SpaceConfig(
            qualified_name="project/fp_space",
            owner="project",
            short_name="fp_space",
            entries=(str(src_dir),),
        )
        engine = KnowledgeEngine(
            storage_dir=storage_dir,
            contributes_data={"spaces": {"fp_space": sp}},
            embedding_mock_mode=True,
        )
        engine.build_unified_index(force=True)
        indices_dir = engine.pipeline.get_indices_dir()

        # 情境 A：Worker 處於 running (例如 degraded_offline idle)，前台不應搶 _consume_space_diff
        clear_worker_state(indices_dir, worker_running=True, phase="degraded_offline")
        with patch.object(engine.pipeline, "_consume_space_diff") as spy_consume:
            idx = engine.pipeline._ensure_jit_index_ready(require_vectors=False)
            self.assertIsNotNone(idx)
            spy_consume.assert_not_called()

        # 情境 B：背景執行緒持有 _index_lock 時，前台併發呼叫 _ensure_jit_index_ready 不阻塞等待鎖
        clear_worker_state(indices_dir, worker_running=False, phase="idle")
        lock_held = threading.Event()
        release_lock = threading.Event()

        def _hold_lock():
            with engine.pipeline._index_lock:
                lock_held.set()
                release_lock.wait(timeout=3.0)

        t = threading.Thread(target=_hold_lock)
        t.start()
        self.assertTrue(lock_held.wait(timeout=1.0))
        try:
            t0 = time.perf_counter()
            idx2 = engine.pipeline._ensure_jit_index_ready(require_vectors=False)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            self.assertIsNotNone(idx2)
            self.assertLess(dt_ms, 100.0)
        finally:
            release_lock.set()
            t.join(timeout=1.0)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
