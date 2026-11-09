"""
GDriveSyncServiceWorker: Optional background service worker gated by auto_sync (default False).

Invariants:
- When config.auto_sync is False (default), enters standby_mode=True without starting a polling
  thread or registering core.space subscriptions, while health_check() returns True so
  'yscb server status' reports healthy standby rather than a dead worker.
- When config.auto_sync is True, subscribes to core.space.subscribe and deterministically
  invokes _unsubscribe() upon stop().
"""
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

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

from .config import GDriveConfig, load_gdrive_config
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
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.standby_mode: bool = True
        self._started: bool = False
        self._sync_runs: int = 0
        self._last_error: str = ""
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
        cfg = self._explicit_config or load_gdrive_config()
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
        self._wake_event.set()

    def _run_loop(self) -> None:
        assert self._config is not None
        interval = max(1.0, float(self._config.poll_interval_sec))
        self.set_state(self.STATE_READY)
        while not self._stop_event.is_set():
            self._wake_event.wait(timeout=interval)
            if self._stop_event.is_set():
                break
            self._wake_event.clear()
            self.run_once()

    def run_once(self) -> Optional[Dict[str, Any]]:
        """Execute a single non-blocking background sync cycle."""
        if self.standby_mode or self._coordinator is None:
            return None
        self.set_state(self.STATE_UPDATING)
        try:
            try:
                self.touch_activity()
            except Exception:
                pass
            report = self._coordinator.run_sync(
                mode="sync",
                non_blocking_lock=True,
                background_worker=True,
                abort_check=self._stop_event.is_set,
            )
            self._sync_runs += 1
            self._last_error = ""
            if not self._stop_event.is_set():
                self.set_state(self.STATE_READY)
            return report.to_dict()
        except Exception as exc:
            self._last_error = str(exc)
            if not self._stop_event.is_set():
                self.set_state(self.STATE_DEGRADED_OFFLINE)
            log_debug(f"Background gdrive sync deferred/failed: {exc}")
            return None

    def stop(self) -> None:
        """Gracefully stop background thread and deterministically unsubscribe from core.space."""
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

