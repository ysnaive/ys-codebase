"""
KnowledgeDBServiceWorker: Background two-stage incremental indexing,
automatic vector model download, micro-batched vector self-healing,
and elapsed busy millisecond probe (`is_worker_busy() -> int`).

File system monitoring (`watchdog`) is delegated 100% to `core.space` (`space-watcher`).
"""

import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, Optional, Tuple, Union

from core.context import (
    get_or_compute_cell_state,
    get_runtime_context,
    invalidate_cell_state,
)
from core.log import bind_log_context, log_debug, log_warn

try:
    from server.service import BaseServiceWorker
except ImportError:

    class BaseServiceWorker:  # type: ignore[no-redef]
        STATE_STARTING: str = "STARTING"
        STATE_UPDATING: str = "UPDATING"
        STATE_READY: str = "READY"
        STATE_DEGRADED_OFFLINE: str = "DEGRADED_OFFLINE"
        STATE_STOPPED: str = "STOPPED"
        _state: str = STATE_STOPPED
        _log_sink: Optional[Any] = None

        @property
        def state(self) -> str:
            return getattr(self, "_state", self.STATE_STOPPED)

        def set_state(self, new_state: str) -> None:
            self._state = str(new_state)

        def touch_activity(self) -> bool:
            return False

        def start_managed_thread(
            self,
            target: Any,
            *,
            context: Optional[Dict[str, Any]] = None,
            thread_name: Optional[str] = None,
        ) -> Any:
            from concurrent.futures import ThreadPoolExecutor

            sink = context.get("log_sink") if isinstance(context, dict) else None
            comp = getattr(self, "name", "worker")

            def _wrapped() -> None:
                with bind_log_context(
                    background_sink=sink,
                    component=comp,
                    isolated_error_scope=True,
                ):
                    target()

            pool = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix=thread_name or f"Worker-{comp}",
            )
            fut = pool.submit(_wrapped)

            class _ManagedHandle:
                def __init__(self, f: Any, p: Any) -> None:
                    self._f = f
                    self._p = p

                def is_alive(self) -> bool:
                    return not self._f.done()

                def join(self, timeout: Optional[float] = None) -> None:
                    try:
                        self._f.result(timeout=timeout)
                    except Exception:
                        pass
                    self._p.shutdown(wait=False)

            return _ManagedHandle(fut, pool)

        def stop_managed_thread(
            self,
            thread: Any,
            stop_event: Optional[threading.Event] = None,
            *,
            wake_event: Optional[threading.Event] = None,
            timeout: float = 2.0,
        ) -> None:
            if stop_event is not None:
                stop_event.set()
            if wake_event is not None:
                wake_event.set()
            if thread is not None and hasattr(thread, "join"):
                thread.join(timeout=timeout)
            self.set_state(self.STATE_STOPPED)


WORKER_STATE_FILENAME = ".kdb_worker_state.json"
WORKER_CELL_STATE_KEY = "kdb.worker_state"

_WORKER_LOCK = threading.RLock()
_IDLE_EVENT = threading.Event()
_IDLE_EVENT.set()


def _norm_indices_dir(indices_dir: Optional[Union[str, Path]]) -> str:
    if indices_dir is None:
        return ""
    try:
        return os.path.normcase(os.path.realpath(str(indices_dir)))
    except OSError:
        return os.path.normcase(os.path.abspath(str(indices_dir)))


def _invalidate_worker_cell_state() -> None:
    invalidate_cell_state(WORKER_CELL_STATE_KEY)
    invalidate_cell_state("kdb.worker_state_raw")


def _get_worker_mem_state() -> Dict[str, Any]:
    ctx = get_runtime_context()
    st = ctx.get_module_state("knowledge_db.service.mem_state")
    if not isinstance(st, dict):
        st = {
            "active_worker": None,
            "indices_dir": "",
            "busy_start_ts": 0.0,
            "phase": "idle",
            "progress": "",
        }
        ctx.set_module_state("knowledge_db.service.mem_state", st)
    return st


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
        w = _get_worker_mem_state().get("active_worker")
        if w is not None and w.is_alive():
            return w
        return None


def is_worker_running(indices_dir: Optional[Union[str, Path]] = None) -> bool:
    """Return True if a KnowledgeDBServiceWorker is active in-process or in the server daemon."""
    w = get_active_worker()
    if w is not None:
        if indices_dir is None:
            return True
        mem_dir = str(_get_worker_mem_state().get("indices_dir") or "")
        if not mem_dir or mem_dir == _norm_indices_dir(indices_dir):
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
    now = time.time()
    eff_phase = phase if (busy or phase not in ("", "idle")) else "idle"
    eff_progress = progress if (busy or phase not in ("", "idle")) else ""
    norm_dir = _norm_indices_dir(indices_dir)
    mem_st = _get_worker_mem_state()
    with _WORKER_LOCK:
        mem_st["indices_dir"] = norm_dir
        if busy:
            prev_ts = float(mem_st.get("busy_start_ts", 0.0) or 0.0)
            if start_ts <= 0.0:
                start_ts = prev_ts if prev_ts > 0.0 else now
            mem_st["busy_start_ts"] = start_ts
            mem_st["phase"] = eff_phase
            mem_st["progress"] = eff_progress
            _IDLE_EVENT.clear()
        else:
            mem_st["busy_start_ts"] = 0.0
            mem_st["phase"] = eff_phase
            mem_st["progress"] = eff_progress
            _IDLE_EVENT.set()

    p = get_worker_state_path(indices_dir)
    _invalidate_worker_cell_state()
    try:
        from core import vfs

        payload = {
            "worker_running": bool(worker_running),
            "busy": bool(busy),
            "start_ts": float(start_ts if busy else 0.0),
            "updated_ts": now,
            "pid": os.getpid(),
            "phase": eff_phase,
            "progress": eff_progress,
        }
        vfs.write_json(str(p), payload, indent=None, atomic=True)
    except Exception as exc:
        log_debug(f"Failed writing worker state file {p}: {exc}")
    finally:
        _invalidate_worker_cell_state()


def clear_worker_state(
    indices_dir: Union[str, Path],
    *,
    worker_running: bool = False,
    phase: str = "idle",
    progress: str = "",
) -> None:
    """Reset busy state to idle (or degraded_offline / yielded_to_foreground) or clear state when worker stops."""
    write_worker_state(
        indices_dir,
        busy=False,
        start_ts=0.0,
        phase=phase,
        progress=progress,
        worker_running=worker_running,
    )


def read_worker_state(indices_dir: Union[str, Path]) -> Dict[str, Any]:
    """
    Read worker state from in-process memory (when an active worker matches `indices_dir`)
    or from `indices/.kdb_worker_state.json`.
    Automatically cleans up stale state if the owning PID is no longer alive, and never
    leaks in-process memory state across unrelated `indices_dir` paths.
    """
    target_dir_norm = _norm_indices_dir(indices_dir)
    with _WORKER_LOCK:
        mem_st = _get_worker_mem_state()
        w = mem_st.get("active_worker")
        active = w is not None and w.is_alive()
        mem_dir_norm = str(mem_st.get("indices_dir") or "")
        if active and not mem_dir_norm and getattr(w, "_engine", None) is not None:
            try:
                mem_dir_norm = _norm_indices_dir(w._engine.pipeline.get_indices_dir())
                mem_st["indices_dir"] = mem_dir_norm
            except Exception:
                pass
        if active and mem_dir_norm and mem_dir_norm == target_dir_norm:
            busy_ts = float(mem_st.get("busy_start_ts", 0.0) or 0.0)
            phase_str = str(mem_st.get("phase") or "idle")
            prog_str = str(mem_st.get("progress") or "")
            if busy_ts > 0.0:
                elapsed_ms = max(1, int((time.time() - busy_ts) * 1000))
                return {
                    "worker_running": True,
                    "busy": True,
                    "start_ts": busy_ts,
                    "elapsed_ms": elapsed_ms,
                    "phase": phase_str,
                    "progress": prog_str,
                    "pid": os.getpid(),
                }
            return {
                "worker_running": True,
                "busy": False,
                "start_ts": 0.0,
                "elapsed_ms": 0,
                "phase": phase_str,
                "progress": prog_str,
                "pid": os.getpid(),
            }

    p = get_worker_state_path(indices_dir)
    if p.exists():
        try:
            st = p.stat()
            file_fp = (int(st.st_mtime_ns), int(st.st_size))

            def _read_disk_raw() -> Optional[Dict[str, Any]]:
                from core import vfs

                raw_obj = vfs.read_json(str(p))
                return raw_obj if isinstance(raw_obj, dict) else None

            raw = get_or_compute_cell_state(
                (WORKER_CELL_STATE_KEY, os.path.normcase(str(p)), file_fp),
                _read_disk_raw,
            )
            if isinstance(raw, dict):
                pid = int(raw.get("pid", 0) or 0)
                if pid > 0 and not _check_pid_alive(pid):
                    try:
                        from core import vfs

                        vfs.remove(str(p), missing_ok=True)
                    except OSError:
                        pass
                else:
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
        mem_st = _get_worker_mem_state()
        w = mem_st.get("active_worker")
        active = w is not None and w.is_alive()
        mem_dir_norm = str(mem_st.get("indices_dir") or "")
        if not mem_dir_norm or mem_dir_norm != target_dir_norm:
            return {
                "worker_running": False,
                "busy": False,
                "start_ts": 0.0,
                "elapsed_ms": 0,
                "phase": "idle",
                "progress": "",
                "pid": 0,
            }
        busy_ts = float(mem_st.get("busy_start_ts", 0.0) or 0.0)
        phase_str = str(mem_st.get("phase") or "idle")
        prog_str = str(mem_st.get("progress") or "")
        if busy_ts > 0.0:
            elapsed_ms = max(1, int((time.time() - busy_ts) * 1000))
            return {
                "worker_running": active,
                "busy": True,
                "start_ts": busy_ts,
                "elapsed_ms": elapsed_ms,
                "phase": phase_str,
                "progress": prog_str,
                "pid": os.getpid(),
            }
        return {
            "worker_running": active,
            "busy": False,
            "start_ts": 0.0,
            "elapsed_ms": 0,
            "phase": phase_str,
            "progress": prog_str,
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
        _invalidate_worker_cell_state()
        if get_worker_busy_ms(indices_dir) == 0:
            return True
        remain = deadline - time.perf_counter()
        if remain <= 0:
            break
        wait_slice = min(0.025, remain)
        if not _IDLE_EVENT.is_set():
            if _IDLE_EVENT.wait(timeout=wait_slice):
                _invalidate_worker_cell_state()
                if get_worker_busy_ms(indices_dir) == 0:
                    return True
        else:
            time.sleep(wait_slice)
    _invalidate_worker_cell_state()
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
        self._space_dirty_flag: bool = True
        self._idle_verified_state: Optional[Tuple[int, int, int, bool, bool]] = None
        self.set_state(self.STATE_STOPPED)

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
        """Non-blocking O(1) wakeup signal when `space-watcher` broadcasts `on_file_space_changed`."""
        self._space_dirty_flag = True
        self._idle_verified_state = None
        self._wake_event.set()

    def start(self, context: Optional[Dict[str, Any]] = None) -> None:
        mem_st = _get_worker_mem_state()
        with _WORKER_LOCK:
            if isinstance(context, dict):
                self.context.update(context)
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._space_dirty_flag = True
            self._idle_verified_state = None
            self._wake_event.set()
            self.set_state(self.STATE_STARTING)
            mem_st["active_worker"] = self
            if self._engine is not None and hasattr(self._engine, "pipeline"):
                try:
                    mem_st["indices_dir"] = _norm_indices_dir(self._engine.pipeline.get_indices_dir())
                except Exception:
                    pass
            self._thread = self.start_managed_thread(
                self.run,
                context=self.context,
                thread_name=f"Worker-{self.name}",
            )

    def stop(self, timeout: float = 5.0) -> None:
        mem_st = _get_worker_mem_state()
        self._stop_event.set()
        self._wake_event.set()
        self.stop_managed_thread(
            self._thread,
            self._stop_event,
            wake_event=self._wake_event,
            timeout=timeout,
        )
        self._thread = None
        with _WORKER_LOCK:
            if mem_st.get("active_worker") is self:
                mem_st["active_worker"] = None
        try:
            engine = self._get_engine()
            clear_worker_state(engine.pipeline.get_indices_dir(), worker_running=False)
        except Exception:
            pass
        self.set_state(self.STATE_STOPPED)

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def health_check(self) -> bool:
        return self.is_alive()

    def run(self) -> None:
        """Main background loop executing Stage 1 (Fast AST/BM25/Graph) and Stage 2 (Micro-batched Vector Sync)."""
        self.set_state(self.STATE_STARTING)
        try:
            engine = self._get_engine()
            indices_dir = engine.pipeline.get_indices_dir()
            clear_worker_state(indices_dir, worker_running=True)
        except Exception as exc:
            self.set_state(self.STATE_STOPPED)
            log_warn(f"[knowledge-db-worker] Failed to initialize engine in worker: {exc}", stream="stderr")
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
            self.set_state(self.STATE_STOPPED)
            try:
                clear_worker_state(indices_dir, worker_running=False)
            except Exception:
                pass

    def _run_sync_cycle(self, engine: Any, indices_dir: Path) -> None:
        """Execute a full background synchronization cycle (Stage 1 + Auto Model Download + Stage 2)."""
        busy_start_ts: float = 0.0
        final_state: str = self.STATE_READY
        final_phase: str = "idle"
        final_progress: str = ""
        did_sync_work: bool = False

        def _current_index_signature() -> Optional[Tuple[int, int, int, bool, bool]]:
            try:
                bin_file = indices_dir / "unified.index.bin.gz"
                vec_file = indices_dir / "unified.vectors.bin.gz"
                if not bin_file.exists():
                    return None
                u_mtime = int(bin_file.stat().st_mtime_ns)
                v_mtime = int(vec_file.stat().st_mtime_ns) if vec_file.exists() else 0
                idx = getattr(engine.pipeline, "unified_index", None)
                ast_gen = int(getattr(idx, "acked_ast_generation", 0) or 0) if idx is not None else 0
                emb = getattr(engine, "embedding_service", None)
                mock_flag = bool(getattr(emb, "mock_mode", False)) if emb is not None else False
                has_local = (
                    bool(emb.has_local_model() if hasattr(emb, "has_local_model") else emb.is_model_downloaded())
                    if (emb is not None and not mock_flag)
                    else True
                )
                return (ast_gen, u_mtime, v_mtime, mock_flag, has_local)
            except OSError:
                return None

        def _mark_busy(phase: str, progress: str = "") -> None:
            nonlocal busy_start_ts
            if busy_start_ts <= 0.0:
                busy_start_ts = time.time()
            self.set_state(self.STATE_UPDATING)
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
            # Fast O(1) idle short-circuit when no space dirty notification arrived and index files are unchanged
            if not self._space_dirty_flag and self._idle_verified_state is not None:
                cur_sig = _current_index_signature()
                if cur_sig is not None and cur_sig == self._idle_verified_state:
                    return

            # Stage 1: Check and consume any pending space diffs (AST + BM25 + CallGraph only)
            if self._has_pending_space_work(engine, indices_dir):
                _mark_busy("stage1_ast_bm25_graph", "同步 AST 符號、BM25 倒排與呼叫圖譜")
                self._sync_stage1_lexical_and_graph(engine, indices_dir)
                self._space_diffs_processed += 1
                self._last_sync_at = time.time()
                self._idle_verified_state = None
                did_sync_work = True
            self._space_dirty_flag = False

            if self._stop_event.is_set():
                return

            # Stage 2: Vector model auto-download & micro-batched vector self-healing
            enable_vec = getattr(engine.config, "enable_vector_search", True)
            if not enable_vec:
                self._idle_verified_state = _current_index_signature()
                return

            emb_svc = getattr(engine, "embedding_service", None)
            if emb_svc is None:
                self._idle_verified_state = _current_index_signature()
                return

            # Check if there is any vector deficit before downloading/loading model
            deficit_info = engine.pipeline.get_vector_deficit_info()
            needs_vectors = (
                deficit_info["missing_count"] > 0
                or deficit_info["stale_count"] > 0
                or not deficit_info["compatible"]
            )

            has_model = emb_svc.has_local_model() if hasattr(emb_svc, "has_local_model") else emb_svc.is_model_downloaded()
            if not emb_svc.mock_mode and not has_model:
                now = time.time()
                if (now - self._last_download_attempt_ts) >= self.MODEL_DOWNLOAD_RETRY_COOLDOWN_SEC:
                    self._last_download_attempt_ts = now
                    _mark_busy("downloading_model", f"背景自動下載向量模型 {emb_svc.model_name}")
                    try:
                        dl_ok = emb_svc.download_model(force=False)
                        if not dl_ok:
                            raise RuntimeError(f"download_model returned False for {emb_svc.model_name}")
                        needs_vectors = True
                        did_sync_work = True
                    except Exception as dl_err:
                        final_state = self.STATE_DEGRADED_OFFLINE
                        final_phase = "degraded_offline"
                        final_progress = f"向量模型下載失敗或離線降級: {dl_err}"
                        log_warn(f"[knowledge-db-worker] Background model download failed: {dl_err}", stream="stderr")
                        return
                else:
                    final_state = self.STATE_DEGRADED_OFFLINE
                    final_phase = "degraded_offline"
                    final_progress = f"等待向量模型重試冷卻 ({emb_svc.model_name})"
                    return

            if not emb_svc.is_available:
                final_state = self.STATE_DEGRADED_OFFLINE
                final_phase = "degraded_offline"
                final_progress = f"向量模型不可用 ({emb_svc.model_name})"
                return

            if not needs_vectors:
                self._idle_verified_state = _current_index_signature()
                return

            batch_size = max(1, int(getattr(engine.config, "vector_batch_size", 32) or 32))
            batches_since_persist = 0
            last_persist_ts = time.monotonic()
            step_info = deficit_info
            while not self._stop_event.is_set():
                # Yield immediately to foreground CLI tasks in WarmWorker while persisting partial progress
                # and marking phase="yielded_to_foreground" so foreground search never overwrites in-memory vectors
                try:
                    if bool(get_runtime_context().get_module_state("server.worker.foreground_active", lambda: False)):
                        if getattr(engine.pipeline, "_vector_index_dirty", False):
                            engine.pipeline.flush_vector_index()
                            batches_since_persist = 0
                            last_persist_ts = time.monotonic()
                        if busy_start_ts > 0.0:
                            tot_s = int(step_info.get("total_symbols", 0))
                            rem_s = int(step_info.get("missing_count", 0))
                            clear_worker_state(
                                indices_dir,
                                worker_running=True,
                                phase="yielded_to_foreground",
                                progress=f"禮讓前景查詢 ({max(0, tot_s - rem_s)}/{tot_s})",
                            )
                            busy_start_ts = 0.0
                        self._wake_event.wait(timeout=0.05)
                        continue
                except Exception:
                    pass

                # If new code changes arrived during Stage 2, immediately prioritize Stage 1!
                if self._wake_event.is_set() and self._has_pending_space_work(engine, indices_dir):
                    self._wake_event.clear()
                    self._space_dirty_flag = False
                    if getattr(engine.pipeline, "_vector_index_dirty", False):
                        engine.pipeline.flush_vector_index()
                        batches_since_persist = 0
                        last_persist_ts = time.monotonic()
                    _mark_busy("stage1_ast_bm25_graph", "插隊同步最新變更之 AST / BM25 / 圖譜")
                    self._sync_stage1_lexical_and_graph(engine, indices_dir)
                    self._space_diffs_processed += 1
                    did_sync_work = True
                    step_info = engine.pipeline.get_vector_deficit_info()

                total_syms = int(step_info.get("total_symbols", 0))
                missing_cnt = int(step_info.get("missing_count", 0))
                stale_cnt = int(step_info.get("stale_count", 0))
                is_compat = bool(step_info.get("compatible", True))
                if missing_cnt == 0 and stale_cnt == 0 and is_compat:
                    self._idle_verified_state = _current_index_signature()
                    break

                embedded_before = max(0, total_syms - missing_cnt)
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
                remaining_after = int(res.get("remaining", 0))
                total_after = int(res.get("total_symbols", total_syms))
                if embedded_step > 0 or removed_step > 0:
                    self._vector_batches_processed += 1
                    self._last_sync_at = time.time()
                    batches_since_persist += 1
                    did_sync_work = True
                if should_persist or remaining_after <= 0:
                    batches_since_persist = 0
                    last_persist_ts = time.monotonic()
                if remaining_after <= 0:
                    self._idle_verified_state = _current_index_signature()
                    break
                if embedded_step == 0 and removed_step == 0:
                    break
                step_info = {
                    "total_symbols": total_after,
                    "missing_count": remaining_after,
                    "stale_count": 0,
                    "compatible": True,
                }
                # Brief yield between micro-batches
                time.sleep(0.005)
        except Exception as exc:
            log_warn(f"[knowledge-db-worker] Sync cycle warning: {exc}", stream="stderr")
        finally:
            try:
                if getattr(engine.pipeline, "_vector_index_dirty", False):
                    engine.pipeline.flush_vector_index()
                    self._idle_verified_state = _current_index_signature()
            except Exception as flush_err:
                log_warn(f"[knowledge-db-worker] Flush vector index on exit warning: {flush_err}", stream="stderr")
            if did_sync_work and not self._stop_event.is_set():
                try:
                    from core.platform import trim_process_memory

                    trim_process_memory()
                except Exception:
                    pass
            if not self._stop_event.is_set():
                self.set_state(final_state)
            if busy_start_ts > 0.0 or final_phase != "idle":
                clear_worker_state(
                    indices_dir,
                    worker_running=not self._stop_event.is_set(),
                    phase=final_phase if not self._stop_event.is_set() else "idle",
                    progress=final_progress if not self._stop_event.is_set() else "",
                )

    def _has_pending_space_work(self, engine: Any, indices_dir: Path) -> bool:
        bin_file = indices_dir / "unified.index.bin.gz"
        if not bin_file.exists():
            return True
        try:
            scanner = getattr(engine, "scanner", None)
            if scanner is not None and hasattr(scanner, "diff"):
                indexed_spaces = (
                    list(engine.get_indexed_spaces().values())
                    if hasattr(engine, "get_indexed_spaces")
                    else []
                )
                if indexed_spaces:
                    for sp in indexed_spaces:
                        q_name = getattr(sp, "qualified_name", None) or getattr(sp, "short_name", None)
                        if q_name and scanner.diff(q_name, consumer_id="knowledge-db", auto_refresh=False).has_changes:
                            return True
                elif scanner.diff(consumer_id="knowledge-db", auto_refresh=False).has_changes:
                    return True
            if hasattr(engine.pipeline, "_ensure_indices_loaded"):
                engine.pipeline._ensure_indices_loaded(load_vectors=False)
            idx = getattr(engine.pipeline, "unified_index", None)
            if idx is not None and hasattr(engine.pipeline, "get_current_ast_generation"):
                ast_gen = engine.pipeline.get_current_ast_generation()
                if ast_gen is not None and int(getattr(idx, "acked_ast_generation", 0) or 0) != ast_gen:
                    return True
        except Exception:
            pass
        return False

    def _sync_stage1_lexical_and_graph(self, engine: Any, indices_dir: Path) -> None:
        """Stage 1 Fast Path: Update AST and BM25 inverted index via the unified pipeline sync helper."""
        indexed_spaces = (
            list(engine.get_indexed_spaces().values())
            if hasattr(engine, "get_indexed_spaces")
            else []
        )
        target_qnames = [
            getattr(sp, "qualified_name", None) or getattr(sp, "short_name", None)
            for sp in indexed_spaces
            if (getattr(sp, "qualified_name", None) or getattr(sp, "short_name", None))
        ]
        engine.pipeline.sync_incremental_changes(
            target_spaces=target_qnames if target_qnames else None,
            skip_vectors=True,
            allow_parallel=False,
        )

    def get_custom_metrics(self) -> Dict[str, Any]:
        try:
            engine = self._get_engine()
            indices_dir = engine.pipeline.get_indices_dir()
            st = read_worker_state(indices_dir)
        except Exception:
            st = {"busy": False, "elapsed_ms": 0, "phase": "idle", "progress": ""}
        return {
            "state": self.state,
            "busy": st.get("busy", False),
            "busy_elapsed_ms": st.get("elapsed_ms", 0),
            "phase": st.get("phase", "idle"),
            "progress": st.get("progress", ""),
            "space_diffs_processed": self._space_diffs_processed,
            "vector_batches_processed": self._vector_batches_processed,
            "last_sync_at": self._last_sync_at,
        }
