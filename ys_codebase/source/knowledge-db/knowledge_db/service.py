"""
KnowledgeDBServiceWorker: Background two-stage incremental indexing,
automatic vector model download, micro-batched vector self-healing,
and elapsed busy millisecond probe (`is_worker_busy() -> int`).

File system monitoring (`watchdog`) is delegated 100% to `module:file-space` (`file-space-watcher`).
"""

import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, Optional, Union

logger = logging.getLogger("knowledge-db.service")

try:
    from server.service import BaseServiceWorker
except ImportError:

    class BaseServiceWorker:  # type: ignore[no-redef]
        """Fallback base worker when server module is not installed."""

        @property
        def name(self) -> str:
            return "knowledge-db-worker"

        def start(self, context: Dict[str, Any]) -> None:
            pass

        def stop(self) -> None:
            pass

        def health_check(self) -> bool:
            return False

        def touch_activity(self) -> bool:
            return False


WORKER_STATE_FILENAME = ".kdb_worker_state.json"

_WORKER_LOCK = threading.Lock()
_ACTIVE_WORKER: Optional["KnowledgeDBServiceWorker"] = None
_IN_PROCESS_BUSY_START_TS: float = 0.0
_IN_PROCESS_PHASE: str = "idle"
_IN_PROCESS_PROGRESS: str = ""
_IDLE_EVENT = threading.Event()
_IDLE_EVENT.set()


def _check_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        from core.platform import is_process_alive
        return bool(is_process_alive(pid))
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def get_active_worker() -> Optional["KnowledgeDBServiceWorker"]:
    """Return the active in-process KnowledgeDBServiceWorker instance if running."""
    with _WORKER_LOCK:
        if _ACTIVE_WORKER is not None and _ACTIVE_WORKER.is_alive():
            return _ACTIVE_WORKER
        return None


def is_worker_running(indices_dir: Optional[Union[str, Path]] = None) -> bool:
    """Return True if a KnowledgeDBServiceWorker is active in-process or in the server daemon."""
    if get_active_worker() is not None:
        return True
    if indices_dir is not None:
        st = read_worker_state(indices_dir)
        pid = int(st.get("pid", 0) or 0)
        if st.get("worker_running") and _check_pid_alive(pid):
            return True
    return False


def get_worker_state_path(indices_dir: Union[str, Path]) -> Path:
    return Path(indices_dir) / WORKER_STATE_FILENAME


def write_worker_state(
    indices_dir: Union[str, Path],
    *,
    busy: bool,
    start_ts: float = 0.0,
    phase: str = "idle",
    progress: str = "",
    worker_running: bool = True,
) -> None:
    """Atomically persist worker state to `indices/.kdb_worker_state.json` and update in-process state."""
    global _IN_PROCESS_BUSY_START_TS, _IN_PROCESS_PHASE, _IN_PROCESS_PROGRESS
    now = time.time()
    with _WORKER_LOCK:
        if busy:
            if start_ts <= 0.0:
                start_ts = _IN_PROCESS_BUSY_START_TS if _IN_PROCESS_BUSY_START_TS > 0.0 else now
            _IN_PROCESS_BUSY_START_TS = start_ts
            _IN_PROCESS_PHASE = phase
            _IN_PROCESS_PROGRESS = progress
            _IDLE_EVENT.clear()
        else:
            _IN_PROCESS_BUSY_START_TS = 0.0
            _IN_PROCESS_PHASE = "idle"
            _IN_PROCESS_PROGRESS = ""
            _IDLE_EVENT.set()

    p = get_worker_state_path(indices_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "worker_running": bool(worker_running),
            "busy": bool(busy),
            "start_ts": float(start_ts if busy else 0.0),
            "updated_ts": now,
            "pid": os.getpid(),
            "phase": phase if busy else "idle",
            "progress": progress if busy else "",
        }
        tmp_path = p.with_name(f"{WORKER_STATE_FILENAME}.tmp.{os.getpid()}.{threading.get_ident()}")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp_path), str(p))
    except Exception as exc:
        logger.debug("Failed writing worker state file %s: %s", p, exc)


def clear_worker_state(indices_dir: Union[str, Path], *, worker_running: bool = False) -> None:
    """Reset busy state to idle (or remove state file when worker stops)."""
    write_worker_state(
        indices_dir,
        busy=False,
        start_ts=0.0,
        phase="idle",
        progress="",
        worker_running=worker_running,
    )


def read_worker_state(indices_dir: Union[str, Path]) -> Dict[str, Any]:
    """
    Read worker state from in-process memory or `indices/.kdb_worker_state.json`.
    Automatically cleans up stale state if the owning PID is no longer alive.
    """
    p = get_worker_state_path(indices_dir)
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                pid = int(raw.get("pid", 0) or 0)
                if pid > 0 and not _check_pid_alive(pid):
                    try:
                        p.unlink()
                    except OSError:
                        pass
                    return {
                        "worker_running": False,
                        "busy": False,
                        "start_ts": 0.0,
                        "elapsed_ms": 0,
                        "phase": "idle",
                        "progress": "",
                        "pid": 0,
                    }
                busy = bool(raw.get("busy", False))
                start_ts = float(raw.get("start_ts", 0.0) or 0.0)
                elapsed_ms = max(1, int((time.time() - start_ts) * 1000)) if (busy and start_ts > 0.0) else 0
                return {
                    "worker_running": bool(raw.get("worker_running", True)),
                    "busy": busy,
                    "start_ts": start_ts,
                    "elapsed_ms": elapsed_ms,
                    "phase": str(raw.get("phase", "idle") or "idle"),
                    "progress": str(raw.get("progress", "") or ""),
                    "pid": pid,
                }
        except Exception:
            pass

    with _WORKER_LOCK:
        active = _ACTIVE_WORKER is not None and _ACTIVE_WORKER.is_alive()
        if _IN_PROCESS_BUSY_START_TS > 0.0:
            elapsed_ms = max(1, int((time.time() - _IN_PROCESS_BUSY_START_TS) * 1000))
            return {
                "worker_running": active,
                "busy": True,
                "start_ts": _IN_PROCESS_BUSY_START_TS,
                "elapsed_ms": elapsed_ms,
                "phase": _IN_PROCESS_PHASE,
                "progress": _IN_PROCESS_PROGRESS,
                "pid": os.getpid(),
            }
        return {
            "worker_running": active,
            "busy": False,
            "start_ts": 0.0,
            "elapsed_ms": 0,
            "phase": "idle",
            "progress": "",
            "pid": os.getpid() if active else 0,
        }


def get_worker_busy_ms(indices_dir: Union[str, Path]) -> int:
    """
    Return the elapsed milliseconds (`int`) that the background worker has been
    continuously busy on its current task (`0` means idle).
    """
    st = read_worker_state(indices_dir)
    if not st.get("busy"):
        return 0
    return max(1, int(st.get("elapsed_ms", 0)))


def wait_until_worker_idle(indices_dir: Union[str, Path], timeout_ms: int) -> bool:
    """
    Wait up to `timeout_ms` milliseconds for the worker to become idle (`get_worker_busy_ms() == 0`).
    Returns True if worker became idle within the window, False if still busy on timeout.
    """
    if get_worker_busy_ms(indices_dir) == 0:
        return True
    if timeout_ms <= 0:
        return False

    deadline = time.perf_counter() + (timeout_ms / 1000.0)
    while time.perf_counter() < deadline:
        if get_worker_busy_ms(indices_dir) == 0:
            return True
        remain = deadline - time.perf_counter()
        if remain <= 0:
            break
        wait_slice = min(0.025, remain)
        if not _IDLE_EVENT.is_set():
            if _IDLE_EVENT.wait(timeout=wait_slice):
                if get_worker_busy_ms(indices_dir) == 0:
                    return True
        else:
            time.sleep(wait_slice)
    return get_worker_busy_ms(indices_dir) == 0


class KnowledgeDBServiceWorker(BaseServiceWorker):
    """
    Persistent background worker for `module:knowledge-db`:
    - Stage 1 (Fast Path): Consumes `space` diffs (`consume_diff("knowledge-db")`) and hot-patches
      AST snapshot (`ast_engine`) and BM25 (`unified.index.bin.gz`).
    - Auto Model Download: When `enable_vector_search=True` and model weights are missing in `.storage.local/`,
      automatically downloads the FastEmbed ONNX model in the background without `[GUARD]` prompts.
    - Stage 2 (Slow Path): Compares `unified_index.symbols` vs `vector_index.doc_ids` and incrementally
      computes missing symbol embeddings in small micro-batches (`vector_batch_size`, default 32).
    """

    MODEL_DOWNLOAD_RETRY_COOLDOWN_SEC = 60.0

    def __init__(
        self,
        name: str = "knowledge-db-worker",
        context: Optional[Dict[str, Any]] = None,
        *,
        engine: Optional[Any] = None,
    ) -> None:
        self._name = name
        self.context: Dict[str, Any] = dict(context) if isinstance(context, dict) else {}
        self._engine = engine
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_download_attempt_ts: float = 0.0
        self._space_diffs_processed: int = 0
        self._vector_batches_processed: int = 0
        self._last_sync_at: Optional[float] = None

    @property
    def name(self) -> str:
        return self._name

    def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        from .engine import get_engine
        self._engine = get_engine()
        return self._engine

    def notify_space_changed(self) -> None:
        """Non-blocking O(1) wakeup signal when `file-space-watcher` broadcasts `on_file_space_changed`."""
        self._wake_event.set()

    def start(self, context: Optional[Dict[str, Any]] = None) -> None:
        global _ACTIVE_WORKER
        if isinstance(context, dict):
            self.context.update(context)
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._wake_event.set()
        with _WORKER_LOCK:
            _ACTIVE_WORKER = self
        self._thread = threading.Thread(
            target=self.run,
            name=f"Worker-{self.name}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        global _ACTIVE_WORKER
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        with _WORKER_LOCK:
            if _ACTIVE_WORKER is self:
                _ACTIVE_WORKER = None
        try:
            engine = self._get_engine()
            clear_worker_state(engine.pipeline.get_indices_dir(), worker_running=False)
        except Exception:
            pass

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def health_check(self) -> bool:
        return self.is_alive()

    def run(self) -> None:
        """Main background loop executing Stage 1 (Fast AST/BM25/Graph) and Stage 2 (Micro-batched Vector Sync)."""
        try:
            engine = self._get_engine()
            indices_dir = engine.pipeline.get_indices_dir()
            clear_worker_state(indices_dir, worker_running=True)
            if hasattr(engine, "embedding_service") and engine.embedding_service is not None:
                engine.embedding_service.suppress_guard_prompt = True
        except Exception as exc:
            logger.warning("[knowledge-db-worker] Failed to initialize engine in worker: %s", exc)
            return

        try:
            while not self._stop_event.is_set():
                self._wake_event.clear()
                self._run_sync_cycle(engine, indices_dir)
                if self._stop_event.is_set():
                    break
                # Wait for next `on_file_space_changed` wakeup or periodic self-check
                self._wake_event.wait(timeout=2.0)
        finally:
            try:
                clear_worker_state(indices_dir, worker_running=False)
            except Exception:
                pass

    def _run_sync_cycle(self, engine: Any, indices_dir: Path) -> None:
        """Execute a full background synchronization cycle (Stage 1 + Auto Model Download + Stage 2)."""
        busy_start_ts: float = 0.0

        def _mark_busy(phase: str, progress: str = "") -> None:
            nonlocal busy_start_ts
            if busy_start_ts <= 0.0:
                busy_start_ts = time.time()
            try:
                self.touch_activity()
            except Exception:
                pass
            write_worker_state(
                indices_dir,
                busy=True,
                start_ts=busy_start_ts,
                phase=phase,
                progress=progress,
                worker_running=True,
            )

        try:
            # Stage 1: Check and consume any pending space diffs (AST + BM25 + CallGraph only)
            if self._has_pending_space_work(engine, indices_dir):
                _mark_busy("stage1_ast_bm25_graph", "同步 AST 符號、BM25 倒排與呼叫圖譜")
                self._sync_stage1_lexical_and_graph(engine, indices_dir)
                self._space_diffs_processed += 1
                self._last_sync_at = time.time()

            if self._stop_event.is_set():
                return

            # Stage 2: Vector model auto-download & micro-batched vector self-healing
            enable_vec = getattr(engine.config, "enable_vector_search", True)
            if not enable_vec:
                return

            emb_svc = getattr(engine, "embedding_service", None)
            if emb_svc is None:
                return
            emb_svc.suppress_guard_prompt = True

            # Check if there is any vector deficit before downloading/loading model
            deficit_info = engine.pipeline.get_vector_deficit_info()
            needs_vectors = deficit_info["missing_count"] > 0 or deficit_info["stale_count"] > 0 or not deficit_info["compatible"]

            if not emb_svc.mock_mode and not emb_svc.is_model_downloaded():
                now = time.time()
                if (now - self._last_download_attempt_ts) >= self.MODEL_DOWNLOAD_RETRY_COOLDOWN_SEC:
                    self._last_download_attempt_ts = now
                    _mark_busy("downloading_model", f"背景自動下載向量模型 {emb_svc.model_name}")
                    try:
                        emb_svc.download_model(force=False)
                        needs_vectors = True
                    except Exception as dl_err:
                        logger.warning("[knowledge-db-worker] Background model download failed: %s", dl_err)
                        return
                else:
                    return

            if not emb_svc.is_available:
                return

            if not needs_vectors:
                return

            batch_size = max(1, int(getattr(engine.config, "vector_batch_size", 32) or 32))
            batches_since_persist = 0
            last_persist_ts = time.monotonic()
            while not self._stop_event.is_set():
                # If new code changes arrived during Stage 2, immediately prioritize Stage 1!
                if self._wake_event.is_set() and self._has_pending_space_work(engine, indices_dir):
                    self._wake_event.clear()
                    if getattr(engine.pipeline, "_vector_index_dirty", False):
                        engine.pipeline.flush_vector_index()
                        batches_since_persist = 0
                        last_persist_ts = time.monotonic()
                    _mark_busy("stage1_ast_bm25_graph", "插隊同步最新變更之 AST / BM25 / 圖譜")
                    self._sync_stage1_lexical_and_graph(engine, indices_dir)
                    self._space_diffs_processed += 1

                step_info = engine.pipeline.get_vector_deficit_info()
                total_syms = step_info["total_symbols"]
                embedded_before = max(0, total_syms - step_info["missing_count"])
                if step_info["missing_count"] == 0 and step_info["stale_count"] == 0 and step_info["compatible"]:
                    break

                _mark_busy(
                    "stage2_vector_microbatch",
                    f"向量增量嵌入 ({embedded_before}/{total_syms})",
                )
                should_persist = (
                    (batches_since_persist + 1) >= 8
                    or (time.monotonic() - last_persist_ts) >= 2.0
                )
                res = engine.pipeline.sync_vector_deficit_step(
                    batch_size=batch_size,
                    persist=should_persist,
                )
                embedded_step = int(res.get("embedded_in_step", 0))
                removed_step = int(res.get("removed_stale", 0))
                if embedded_step > 0 or removed_step > 0:
                    self._vector_batches_processed += 1
                    self._last_sync_at = time.time()
                    batches_since_persist += 1
                if should_persist or res.get("remaining", 0) <= 0:
                    batches_since_persist = 0
                    last_persist_ts = time.monotonic()
                if res.get("remaining", 0) <= 0 or (embedded_step == 0 and removed_step == 0):
                    break
                # Brief yield between micro-batches
                time.sleep(0.005)
        except Exception as exc:
            logger.warning("[knowledge-db-worker] Sync cycle warning: %s", exc)
        finally:
            try:
                if getattr(engine.pipeline, "_vector_index_dirty", False):
                    engine.pipeline.flush_vector_index()
            except Exception as flush_err:
                logger.warning("[knowledge-db-worker] Flush vector index on exit warning: %s", flush_err)
            if busy_start_ts > 0.0:
                clear_worker_state(indices_dir, worker_running=not self._stop_event.is_set())

    def _has_pending_space_work(self, engine: Any, indices_dir: Path) -> bool:
        bin_file = indices_dir / "unified.index.bin.gz"
        if not bin_file.exists():
            return True
        try:
            scanner = getattr(engine, "scanner", None)
            if scanner is not None and hasattr(scanner, "diff"):
                diff_res = scanner.diff(consumer_id="knowledge-db", auto_refresh=False)
                if diff_res.has_changes:
                    return True
            ast_eng = getattr(engine, "ast_engine", None)
            idx = getattr(engine.pipeline, "unified_index", None)
            if ast_eng is not None and idx is not None and ast_eng._ensure_loaded_from_disk():
                snap = ast_eng._snapshot
                if snap is not None and int(getattr(idx, "acked_ast_generation", 0) or 0) != int(snap.ast_generation):
                    return True
        except Exception:
            pass
        return False

    def _sync_stage1_lexical_and_graph(self, engine: Any, indices_dir: Path) -> None:
        """Stage 1 Fast Path: Update AST and BM25 inverted index without blocking on vectors."""
        bin_file = indices_dir / "unified.index.bin.gz"
        with engine.pipeline._consume_space_diff(consumer_id="knowledge-db") as diff_res:
            if not bin_file.exists() and engine.pipeline.unified_index is None:
                engine.pipeline.build_unified_index(
                    force=True,
                    allow_parallel=False,
                    skip_vectors=True,
                )
                return
            if not diff_res.has_changes:
                ast_eng = getattr(engine, "ast_engine", None)
                idx = getattr(engine.pipeline, "unified_index", None)
                if ast_eng is not None and idx is not None and ast_eng._ensure_loaded_from_disk():
                    snap = ast_eng._snapshot
                    if snap is not None and int(getattr(idx, "acked_ast_generation", 0) or 0) != int(snap.ast_generation):
                        engine.pipeline.build_unified_index(
                            force=True,
                            allow_parallel=False,
                            skip_vectors=True,
                        )
                return
            patch_res = engine.pipeline.hot_patch_unified_index(
                diff_res.detail,
                skip_vectors=True,
            )
            if not patch_res.success:
                engine.pipeline.build_unified_index(
                    force=True,
                    allow_parallel=False,
                    skip_vectors=True,
                )

    def get_custom_metrics(self) -> Dict[str, Any]:
        try:
            engine = self._get_engine()
            indices_dir = engine.pipeline.get_indices_dir()
            st = read_worker_state(indices_dir)
        except Exception:
            st = {"busy": False, "elapsed_ms": 0, "phase": "idle", "progress": ""}
        return {
            "busy": st.get("busy", False),
            "busy_elapsed_ms": st.get("elapsed_ms", 0),
            "phase": st.get("phase", "idle"),
            "progress": st.get("progress", ""),
            "space_diffs_processed": self._space_diffs_processed,
            "vector_batches_processed": self._vector_batches_processed,
            "last_sync_at": self._last_sync_at,
        }

