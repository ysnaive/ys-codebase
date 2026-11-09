"""
Core Service Contract - Canonical Lightweight Base Contract for Domain Background Workers.
100% Python Standard Library, Zero Third-Party Dependencies.

Provides `BaseServiceWorkerContract` (and alias `BaseServiceWorker`) plus `touch_activity`
so `server`, `knowledge-db`, and `gdrive-support` share a single canonical lifecycle,
managed daemon thread, and log/context isolation contract in `module:core`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
import contextvars
import json
import os
import threading
import time
import urllib.request
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

from core.context import bind_runtime_context, get_env, get_runtime_context, get_virtual_cwd
from core.log import bind_log_context

STATE_STARTING: str = "STARTING"
STATE_UPDATING: str = "UPDATING"
STATE_READY: str = "READY"
STATE_DEGRADED_OFFLINE: str = "DEGRADED_OFFLINE"
STATE_STOPPED: str = "STOPPED"

_TOUCH_MIN_INTERVAL_SEC: float = 1.0
_ORIGINAL_URLOPEN = urllib.request.urlopen
_LOCAL_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _open_local_no_proxy(req: urllib.request.Request, timeout: float) -> Any:
    """Opens a localhost request bypassing system HTTP proxy unless `urllib.request.urlopen` is patched."""
    if urllib.request.urlopen is not _ORIGINAL_URLOPEN:
        return urllib.request.urlopen(req, timeout=timeout)
    return _LOCAL_NO_PROXY_OPENER.open(req, timeout=timeout)


def _resolve_service_root(yscb_root: Optional[str]) -> str:
    """Resolves the active YSCB root directory for daemon state lookup."""
    if yscb_root:
        return yscb_root
    try:
        from core import uri

        resolved_root = uri.resolve("yscb://", interactive=False)
        if resolved_root:
            return resolved_root
    except Exception:
        pass
    cand = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.isdir(os.path.join(cand, ".cache")):
        return cand
    return get_env("YSCB_HOST_DIR") or get_virtual_cwd()


def _get_touch_state() -> Tuple[threading.RLock, Dict[str, float], Dict[str, Tuple[int, int, str]]]:
    """Returns `(server_touch_lock, server_last_touch_by_root, server_touch_daemon_cache)` bound to RuntimeContext."""
    ctx = get_runtime_context()
    lock = getattr(ctx, "server_touch_lock", None)
    if lock is None:
        lock = threading.RLock()
        setattr(ctx, "server_touch_lock", lock)
    touch_map = getattr(ctx, "server_last_touch_by_root", None)
    if touch_map is None:
        touch_map = {}
        setattr(ctx, "server_last_touch_by_root", touch_map)
    daemon_cache = getattr(ctx, "server_touch_daemon_cache", None)
    if daemon_cache is None:
        daemon_cache = {}
        setattr(ctx, "server_touch_daemon_cache", daemon_cache)
    return lock, touch_map, daemon_cache


def touch_activity(
    yscb_root: Optional[str] = None,
    *,
    source: str = "sdk",
    force: bool = False,
) -> bool:
    """
    Refresh the running Server daemon's idle timeout timer (non-CLI keepalive probe SDK).

    Reads `.cache/server/daemon.json` (with `(mtime_ns, port, token)` caching) and sends an
    authenticated `POST /api/touch` (debounced to at most once per 1.0s unless `force=True`)
    via a direct no-proxy localhost opener to the MasterSupervisor so background workers and
    external SDK callers keep the server alive without corrupting the worker stdout pipe.

    Returns True if the activity timestamp was refreshed (or throttled within 1s), False if no
    active daemon was reachable.
    """
    now = time.monotonic()
    resolved_root = _resolve_service_root(yscb_root)
    root_key = os.path.normcase(os.path.abspath(resolved_root))
    touch_lock, touch_map, daemon_cache = _get_touch_state()
    if not force:
        with touch_lock:
            last_ts = touch_map.get(root_key, 0.0)
            if last_ts > 0.0 and (now - last_ts) < _TOUCH_MIN_INTERVAL_SEC:
                return True

    state_file = os.path.join(resolved_root, ".cache", "server", "daemon.json")
    try:
        st = os.stat(state_file)
        mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
    except OSError:
        with touch_lock:
            daemon_cache.pop(root_key, None)
        return False

    try:
        port = 0
        token = ""
        with touch_lock:
            cached_ep = daemon_cache.get(root_key)
            if cached_ep is not None and cached_ep[0] == mtime_ns:
                _, port, token = cached_ep
        if port <= 0 or not token:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                return False
            port = int(state.get("port", 0) or 0)
            token = str(state.get("token", "") or "")
            if port <= 0 or not token:
                return False
            with touch_lock:
                daemon_cache[root_key] = (mtime_ns, port, token)

        url = f"http://127.0.0.1:{port}/api/touch"
        body = json.dumps({"source": source}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with _open_local_no_proxy(req, timeout=1.5) as resp:
            if resp.status != 200:
                return False
        with touch_lock:
            touch_map[root_key] = now
        return True
    except Exception:
        return False


class BaseServiceWorkerContract(ABC):
    """
    Canonical lightweight base contract for domain background service workers.

    Lifecycle & Managed Thread Contract:
    1. Standardized worker state machine:
       `STARTING` -> `UPDATING` -> `READY` -> `DEGRADED_OFFLINE` -> `STOPPED`.
    2. Each active service worker runs inside a dedicated managed daemon thread
       (`start_managed_thread` / `stop_managed_thread`) with `bind_worker_context`
       stream and runtime scope isolation so background logs never pollute foreground CLI streams.
    """

    STATE_STARTING: str = STATE_STARTING
    STATE_UPDATING: str = STATE_UPDATING
    STATE_READY: str = STATE_READY
    STATE_DEGRADED_OFFLINE: str = STATE_DEGRADED_OFFLINE
    STATE_STOPPED: str = STATE_STOPPED

    _state: str = STATE_STOPPED
    _log_sink: Optional[Any] = None
    _status_notify_fn: Optional[Callable[[str, str, bool], None]] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique service worker identifier (e.g. 'knowledge-db-worker')."""
        pass

    @property
    def state(self) -> str:
        """Returns the current worker lifecycle state."""
        raw_st = getattr(self, "_state", None)
        if raw_st and raw_st != self.STATE_STOPPED:
            if getattr(self, "_thread", None) is not None:
                try:
                    if not self.health_check():
                        return self.STATE_STOPPED
                except Exception:
                    return self.STATE_STOPPED
            return str(raw_st)
        try:
            if self.health_check():
                return self.STATE_READY
        except Exception:
            pass
        return self.STATE_STOPPED

    def set_state(self, new_state: str) -> None:
        """Updates the worker's lifecycle state and notifies the supervisor if changed."""
        prev_state = getattr(self, "_state", None)
        target_state = str(new_state)
        self._state = target_state
        if prev_state == target_state:
            return
        alive = target_state != self.STATE_STOPPED
        busy = target_state in (self.STATE_STARTING, self.STATE_UPDATING)
        notify_fn = getattr(self, "_status_notify_fn", None)
        if callable(notify_fn):
            try:
                notify_fn(self.name, target_state, alive)
                return
            except Exception:
                pass
        sink = getattr(self, "_log_sink", None)
        emit_fn = getattr(sink, "emit_packet_fn", None) if sink is not None else None
        if callable(emit_fn):
            try:
                emit_fn({
                    "type": "service_status",
                    "name": self.name,
                    "state": target_state,
                    "alive": alive,
                    "busy": busy,
                })
            except Exception:
                pass

    def _resolve_worker_runtime_dirs(
        self, context: Optional[Dict[str, Any]] = None
    ) -> tuple[Optional[str], Optional[str]]:
        if isinstance(context, dict) and context:
            if not isinstance(getattr(self, "context", None), dict):
                self.context = dict(context)
            else:
                self.context.update(context)
        ctx_dict = context if isinstance(context, dict) else getattr(self, "context", None)
        yscb_dir: Optional[str] = None
        host_dir: Optional[str] = None
        if isinstance(ctx_dict, dict):
            raw_yscb = ctx_dict.get("yscb_root") or ctx_dict.get("yscb_dir")
            if raw_yscb:
                yscb_dir = os.path.abspath(str(raw_yscb))
            raw_host = (
                ctx_dict.get("workspace_root")
                or ctx_dict.get("project_root")
                or ctx_dict.get("host_dir")
            )
            if raw_host:
                host_dir = os.path.abspath(str(raw_host))
        return host_dir, yscb_dir

    def bind_worker_log_context(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Returns a `bind_log_context` context manager isolating background worker output
        to `background_sink` (if configured on the worker or in `context`).
        """
        sink = getattr(self, "_log_sink", None)
        if sink is None and isinstance(context, dict):
            sink = context.get("log_sink")
            if sink is not None:
                self._log_sink = sink
        return bind_log_context(
            background_sink=sink,
            component=self.name,
            isolated_error_scope=True,
        )

    @contextmanager
    def bind_worker_context(self, context: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
        """
        Context manager binding both `RuntimeScope` (`bind_runtime_context`) and
        `LogExecutionScope` (`bind_worker_log_context`) for background worker threads and callbacks.
        """
        host_dir, yscb_dir = self._resolve_worker_runtime_dirs(context)
        ctx_dict = context if isinstance(context, dict) else getattr(self, "context", None)
        explicit_vcwd: Optional[str] = None
        if isinstance(ctx_dict, dict):
            raw_vcwd = ctx_dict.get("virtual_cwd") or ctx_dict.get("cwd")
            if raw_vcwd:
                explicit_vcwd = os.path.abspath(str(raw_vcwd))
        vcwd = explicit_vcwd or host_dir or yscb_dir
        env_overrides: Optional[Dict[str, Optional[str]]] = None
        if host_dir or yscb_dir:
            env_overrides = {}
            if yscb_dir:
                env_overrides["YSCB_ROOT_DIR"] = yscb_dir
            if host_dir:
                env_overrides["YSCB_HOST_DIR"] = host_dir
        with bind_runtime_context(
            virtual_cwd=vcwd,
            env=env_overrides,
            host_dir=host_dir,
            yscb_dir=yscb_dir,
        ) as runtime_scope, self.bind_worker_log_context(context):
            yield runtime_scope

    def start_managed_thread(
        self,
        target: Callable[[], None],
        *,
        context: Optional[Dict[str, Any]] = None,
        thread_name: Optional[str] = None,
    ) -> threading.Thread:
        """
        Spawns and starts a managed daemon `threading.Thread` copying parent `contextvars`
        and wrapping execution in `bind_worker_context` (`bind_runtime_context` + `bind_worker_log_context`)
        so all `core.uri` and `core.log` calls on the worker thread remain isolated.
        """
        if isinstance(context, dict) and context:
            if not isinstance(getattr(self, "context", None), dict):
                self.context = dict(context)
            else:
                self.context.update(context)
            if context.get("log_sink") is not None:
                self._log_sink = context.get("log_sink")

        ctx = contextvars.copy_context()

        def _wrapped_entry() -> None:
            with self.bind_worker_context(context):
                target()

        t_name = thread_name or f"Worker-{self.name}"
        from core.log import create_managed_thread

        t = create_managed_thread(target=lambda: ctx.run(_wrapped_entry), name=t_name, daemon=True)
        t.start()
        return t

    def stop_managed_thread(
        self,
        thread: Optional[threading.Thread],
        stop_event: Optional[threading.Event] = None,
        *,
        wake_event: Optional[threading.Event] = None,
        timeout: float = 2.0,
    ) -> None:
        """Signals `stop_event` (and optional `wake_event`), joins `thread`, and transitions state to `STOPPED`."""
        if stop_event is not None:
            stop_event.set()
        if wake_event is not None:
            wake_event.set()
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        self.set_state(self.STATE_STOPPED)

    @abstractmethod
    def start(self, context: Dict[str, Any]) -> None:
        """Starts background work in a managed daemon thread."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Gracefully shuts down the service worker and releases resources."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Probes whether the background service is running healthy."""
        pass

    def touch_activity(self) -> bool:
        """Notify the server supervisor that this background worker is actively processing work."""
        sink = getattr(self, "_log_sink", None)
        emit_fn = getattr(sink, "emit_packet_fn", None) if sink is not None else None
        if callable(emit_fn):
            try:
                emit_fn({"type": "touch_activity", "source": self.name})
                return True
            except Exception:
                pass
        _, yscb_dir = self._resolve_worker_runtime_dirs()
        return touch_activity(yscb_root=yscb_dir, source=self.name)

    def is_busy(self) -> bool:
        """Returns True if this service worker is actively starting or updating state."""
        try:
            st = self.state
            if st in (self.STATE_STARTING, self.STATE_UPDATING):
                return True
            get_metrics = getattr(self, "get_custom_metrics", None)
            if callable(get_metrics):
                m = get_metrics()
                if isinstance(m, dict) and bool(m.get("busy")):
                    return True
        except Exception:
            pass
        return False


BaseServiceWorker = BaseServiceWorkerContract

__all__ = (
    "STATE_STARTING",
    "STATE_UPDATING",
    "STATE_READY",
    "STATE_DEGRADED_OFFLINE",
    "STATE_STOPPED",
    "BaseServiceWorkerContract",
    "BaseServiceWorker",
    "touch_activity",
)
