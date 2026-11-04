"""
GDriveSyncServiceWorker: Optional background service worker gated by auto_sync (default False).

Invariants:
- When config.auto_sync is False (default), enters standby_mode=True without starting a polling
  thread or registering file-space subscriptions, while health_check() returns True so
  'yscb server status' reports healthy standby rather than a dead worker.
- When config.auto_sync is True, subscribes to file_space.service.subscribe and deterministically
  invokes _unsubscribe() upon stop().
"""
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from .config import GDriveConfig, load_gdrive_config
from .coordinator import SyncCoordinator
from .transport import create_transport

logger = logging.getLogger("gdrive_support.service")

try:
    from server.service import BaseServiceWorker
except ImportError:

    class BaseServiceWorker:  # type: ignore[no-redef]
        """Fallback base worker when server module is not installed."""

        @property
        def name(self) -> str:
            return "gdrive-sync"

        def start(self, context: Dict[str, Any]) -> None:
            pass

        def stop(self) -> None:
            pass

        def health_check(self) -> bool:
            return True


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

    @property
    def name(self) -> str:
        return "gdrive-sync"

    def start(self, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Start the service worker. If auto_sync is False (default), stays in standby_mode=True.
        """
        self._stop_event.clear()
        self._wake_event.clear()
        cfg = self._explicit_config or load_gdrive_config()
        self._config = cfg
        self._started = True

        if not cfg.auto_sync:
            self.standby_mode = True
            return

        if not cfg.root_folder_id and not cfg.sandbox_dir:
            self.standby_mode = True
            return

        self.standby_mode = False
        if self._coordinator is None:
            transport = create_transport(cfg)
            self._coordinator = SyncCoordinator(config=cfg, transport=transport)

        sub_fn = self._subscribe_fn
        if sub_fn is None:
            try:
                from file_space.service import subscribe as fs_subscribe

                sub_fn = fs_subscribe
            except Exception:
                sub_fn = None

        if sub_fn is not None and self._unsubscribe is None:
            watched_spaces = [sp.space for sp in cfg.sync_spaces] or None
            self._unsubscribe = sub_fn(
                self._on_file_space_changed, spaces=watched_spaces
            )

        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run_loop, name="Worker-gdrive-sync", daemon=True
            )
            self._thread.start()

    def _on_file_space_changed(self, space_name: str, _diff: Any = None) -> None:
        self._wake_event.set()

    def _run_loop(self) -> None:
        assert self._config is not None
        interval = max(1.0, float(self._config.poll_interval_sec))
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
        try:
            report = self._coordinator.run_sync(
                mode="sync", non_blocking_lock=True
            )
            self._sync_runs += 1
            self._last_error = ""
            return report.to_dict()
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("Background gdrive sync deferred/failed: %s", exc)
            return None

    def stop(self) -> None:
        """Gracefully stop background thread and deterministically unsubscribe from file-space."""
        self._stop_event.set()
        self._wake_event.set()
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            finally:
                self._unsubscribe = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        self._started = False

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
            "mode": "standby" if self.standby_mode else "active",
            "healthy": self.health_check(),
            "subscribed": self._unsubscribe is not None,
            "sync_runs": self._sync_runs,
            "last_error": self._last_error,
        }

