"""
GDriveSyncServiceWorker: Optional background service worker gated by auto_sync (default False).

Invariants:
- When config.auto_sync is False (default), enters standby_mode=True without starting a polling
  thread or registering core.space subscriptions, while health_check() returns True so
  'yscb server status' reports healthy standby rather than a dead worker.
- When config.auto_sync is True, subscribes to core.space.subscribe and deterministically
  invokes _unsubscribe() upon stop().
"""
from dataclasses import replace
import threading
from typing import Any, Callable, Dict, Optional

import time

from core import vfs
from core.context import is_foreground_active
from core.log import bind_log_context, log_debug
from core.platform import ensure_installed_modules_path

try:
    from server.service import BaseServiceWorker
except ImportError:
    ensure_installed_modules_path()
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
                comp = getattr(self, "name", "gdrive-sync")

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

from .config import GDriveConfig, load_gdrive_config, normalize_remote_rel_path
from .coordinator import SyncCoordinator
from .transport import create_transport


class GDriveSyncServiceWorker(BaseServiceWorker):
    """
    Background synchronization service worker for module:gdrive-support.
    """

    def __init__(
        self,
        config: Optional[GDriveConfig] = None,
        coordinator: Optional[SyncCoordinator] = None,
        subscribe_fn: Optional[Callable[..., Callable[[], None]]] = None,
    ) -> None:
        self._explicit_config = config
        self._explicit_coordinator = coordinator
        self._subscribe_fn = subscribe_fn
        self._config: Optional[GDriveConfig] = config
        self._coordinator: Optional[SyncCoordinator] = coordinator
        self._owned_transport: Optional[Any] = None
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.standby_mode: bool = True
        self._started: bool = False
        self._sync_runs: int = 0
        self._last_error: str = ""
        self._in_sync_run: bool = False
        self._ignore_space_events_until: float = 0.0
        self._recent_synced_paths: set[str] = set()
        self._last_run_yielded: bool = False
        self.set_state(self.STATE_STOPPED)

    @property
    def name(self) -> str:
        return "gdrive-sync"

    def start(self, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Start the service worker. If auto_sync is False (default), stays in standby_mode=True.
        """
        self._stop_event.clear()
        self._wake_event.clear()
        self.set_state(self.STATE_STARTING)
        if self._explicit_config is not None:
            cfg = self._explicit_config
        else:
            try:
                cfg = load_gdrive_config()
            except Exception as exc:
                self._last_error = str(exc)
                self.standby_mode = True
                self._started = True
                self.set_state(self.STATE_READY)
                return
        self._config = cfg
        self._started = True

        if not cfg.auto_sync:
            self.standby_mode = True
            self.set_state(self.STATE_READY)
            return

        if not cfg.root_folder_id and not cfg.sandbox_dir:
            self.standby_mode = True
            self.set_state(self.STATE_READY)
            return

        self.standby_mode = False
        if self._coordinator is None:
            transport = create_transport(cfg)
            self._owned_transport = transport
            self._coordinator = SyncCoordinator(config=cfg, transport=transport)

        sub_fn = self._subscribe_fn
        if sub_fn is None:
            try:
                from core.space import subscribe as fs_subscribe

                sub_fn = fs_subscribe
            except Exception:
                sub_fn = None

        if sub_fn is not None and self._unsubscribe is None:
            watched_spaces = [sp.space for sp in cfg.sync_spaces] or None
            self._unsubscribe = sub_fn(
                self._on_file_space_changed, spaces=watched_spaces
            )

        if self._thread is None or not self._thread.is_alive():
            self.set_state(self.STATE_STARTING)
            self._thread = self.start_managed_thread(
                self._run_loop,
                context=context,
                thread_name="Worker-gdrive-sync",
            )

    def _on_file_space_changed(self, space_name: str, _diff: Any = None) -> None:
        now_m = time.monotonic()
        detail = getattr(_diff, "detail", _diff) if _diff is not None else None
        changed_paths: set[str] = set()
        if detail is not None:
            for attr in ("added", "modified", "deleted"):
                vals = getattr(detail, attr, None)
                if vals:
                    for p in vals:
                        norm_p = str(p).replace("\\", "/").strip("/")
                        if norm_p:
                            changed_paths.add(norm_p)
                            changed_paths.add(norm_p.rsplit("/", 1)[-1])
        if changed_paths:
            if now_m < self._ignore_space_events_until and self._recent_synced_paths:
                if changed_paths.issubset(self._recent_synced_paths):
                    return
            self._wake_event.set()
            return
        if self._in_sync_run or now_m < self._ignore_space_events_until:
            return
        self._wake_event.set()

    def _refresh_active_branch(self) -> None:
        """
        Dynamically refresh configuration and active_branch on each sync cycle without calling
        _load_local_state() before acquiring sync.lock (preventing lockless WAL journal replay/deletion
        and stale sync_state.json branch overrides in non-sandbox mode).
        """
        if self._coordinator is None:
            return
        if self._explicit_config is None:
            try:
                latest_cfg = load_gdrive_config()
                self._coordinator.config = latest_cfg
                self._config = latest_cfg
            except Exception:
                pass

        if self._coordinator.config.sandbox_dir and self._coordinator.state_path.is_file():
            try:
                raw_state = vfs.read_json(self._coordinator.state_path)
                if isinstance(raw_state, dict):
                    state_branch = normalize_remote_rel_path(
                        str(raw_state.get("active_branch") or "")
                    )
                    if (
                        state_branch
                        and "/" not in state_branch
                        and state_branch != self._coordinator.config.active_branch
                    ):
                        updated_cfg = replace(
                            self._coordinator.config, active_branch=state_branch
                        )
                        self._coordinator.config = updated_cfg
                        self._config = updated_cfg
            except Exception:
                pass

    def _run_loop(self) -> None:
        assert self._config is not None
        interval = max(1.0, float(self._config.poll_interval_sec))
        self.set_state(self.STATE_READY)
        while not self._stop_event.is_set():
            self._wake_event.wait(timeout=interval)
            if self._stop_event.is_set():
                break
            if is_foreground_active():
                self._stop_event.wait(timeout=0.1)
                continue
            was_woken = self._wake_event.is_set()
            self._wake_event.clear()
            rep = self.run_once(yield_to_foreground=True)
            if (was_woken and self._last_run_yielded) or (
                isinstance(rep, dict) and rep.get("yielded")
            ):
                self._wake_event.set()
                self._stop_event.wait(timeout=0.1)

    def run_once(self, *, yield_to_foreground: bool = False) -> Optional[Dict[str, Any]]:
        """Execute a single non-blocking background sync cycle without resetting Idle TTL on no-op polls."""
        self._last_run_yielded = False
        if self.standby_mode or self._coordinator is None:
            return None
        if yield_to_foreground and is_foreground_active():
            self._last_run_yielded = True
            return None

        entered_updating = False

        def _mark_active_transfer() -> None:
            nonlocal entered_updating
            if not entered_updating and not self._stop_event.is_set():
                entered_updating = True
                self.set_state(self.STATE_UPDATING)
                try:
                    self.touch_activity()
                except Exception:
                    pass

        def _abort_check() -> bool:
            if self._stop_event.is_set():
                return True
            return bool(yield_to_foreground and is_foreground_active())

        self._in_sync_run = True
        try:
            self._refresh_active_branch()
            try:
                report = self._coordinator.run_sync(
                    mode="sync",
                    non_blocking_lock=True,
                    background_worker=True,
                    abort_check=_abort_check,
                    on_active_transfer=_mark_active_transfer,
                )
            except TypeError:
                report = self._coordinator.run_sync(
                    mode="sync",
                    non_blocking_lock=True,
                    background_worker=True,
                    abort_check=_abort_check,
                )
            rep_dict = report.to_dict()
            did_mutate = bool(
                rep_dict.get("pushed")
                or rep_dict.get("pulled")
                or rep_dict.get("deleted_local")
                or rep_dict.get("deleted_remote")
                or rep_dict.get("moved_to_history")
                or rep_dict.get("gc_history_to_trash")
            )
            if did_mutate and not entered_updating:
                _mark_active_transfer()
            if rep_dict.get("yielded"):
                self._wake_event.set()
            pulled_or_del = list(rep_dict.get("pulled") or []) + list(rep_dict.get("deleted_local") or [])
            if pulled_or_del:
                synced_set: set[str] = set()
                for sp_path in pulled_or_del:
                    np_str = str(sp_path).replace("\\", "/").strip("/")
                    if np_str:
                        synced_set.add(np_str)
                        synced_set.add(np_str.rsplit("/", 1)[-1])
                self._recent_synced_paths = synced_set
                self._ignore_space_events_until = time.monotonic() + 1.5
            self._sync_runs += 1
            self._last_error = ""
            if not self._stop_event.is_set() and (entered_updating or self.state != self.STATE_READY):
                self.set_state(self.STATE_READY)
            return rep_dict
        except Exception as exc:
            self._last_error = str(exc)
            if not self._stop_event.is_set():
                self.set_state(self.STATE_DEGRADED_OFFLINE)
            log_debug(f"Background gdrive sync deferred/failed: {exc}")
            return None
        finally:
            self._in_sync_run = False

    def stop(self) -> None:
        """Gracefully stop background thread, unsubscribe from core.space, and close owned transport."""
        self._stop_event.set()
        self._wake_event.set()
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            finally:
                self._unsubscribe = None
        self.stop_managed_thread(
            self._thread,
            self._stop_event,
            wake_event=self._wake_event,
            timeout=5.0,
        )
        self._thread = None
        if self._owned_transport is not None:
            try:
                self._owned_transport.close()
            except Exception:
                pass
            self._owned_transport = None
        self._coordinator = self._explicit_coordinator
        self._started = False
        self.set_state(self.STATE_STOPPED)

    def health_check(self) -> bool:
        """
        Return True when standing by (auto_sync=False) or when active background thread is alive.
        """
        if not self._started:
            return False
        if self.standby_mode:
            return True
        return bool(self._thread and self._thread.is_alive())

    def get_service_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "started": self._started,
            "state": self.state,
            "mode": "standby" if self.standby_mode else "active",
            "healthy": self.health_check(),
            "subscribed": self._unsubscribe is not None,
            "sync_runs": self._sync_runs,
            "last_error": self._last_error,
        }
