"""
FileSpaceWatcherServiceWorker: Background file system watcher, 500ms debouncer,
transaction lock deference, YFP2 snapshot updater, and on_file_space_changed broadcaster.
"""
import logging
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .manager import FileSpaceManager
from .scanner import (
    FingerprintScanner,
    _adjust_active_watcher_count,
    is_watcher_active,
)
from .schema import ScanDiffResult

logger = logging.getLogger("file_space.service")

try:
    from server.service import BaseServiceWorker
except ImportError:

    class BaseServiceWorker:  # type: ignore[no-redef]
        """Fallback base worker when server module is not installed."""

        def __init__(self, name: str = "file-space-watcher", context: Optional[Dict[str, Any]] = None) -> None:
            self._name = name
            self.context = context or {}
            self._stop_event = threading.Event()
            self._thread: Optional[threading.Thread] = None

        @property
        def name(self) -> str:
            return self._name

        def start(self, context: Optional[Dict[str, Any]] = None) -> None:
            if context is not None:
                self.context = context
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self.run, name=f"Worker-{self.name}", daemon=True
            )
            self._thread.start()

        def stop(self, timeout: float = 5.0) -> None:
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=timeout)

        def is_alive(self) -> bool:
            return bool(self._thread and self._thread.is_alive())

        def health_check(self) -> bool:
            return self.is_alive()

        def get_custom_metrics(self) -> Dict[str, Any]:
            return {}

        def run(self) -> None:
            raise NotImplementedError


try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    FileSystemEvent = Any  # type: ignore[assignment,misc]
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = None  # type: ignore[assignment]


_SUBSCRIBER_LOCK = threading.Lock()
_SUBSCRIBERS: List[Tuple[Callable[[str, ScanDiffResult], Any], Optional[Set[str]]]] = []


def subscribe(
    callback: Callable[[str, ScanDiffResult], Any],
    *,
    spaces: Optional[List[str]] = None,
) -> Callable[[], None]:
    """
    Register an in-process callback invoked whenever a watched space snapshot changes.
    Returns an unsubscribe function.
    """
    space_filter = set(spaces) if spaces is not None else None
    entry = (callback, space_filter)
    with _SUBSCRIBER_LOCK:
        _SUBSCRIBERS.append(entry)

    def _unsubscribe() -> None:
        with _SUBSCRIBER_LOCK:
            if entry in _SUBSCRIBERS:
                _SUBSCRIBERS.remove(entry)

    return _unsubscribe


def clear_subscribers() -> None:
    """Remove all registered in-process space change subscribers."""
    with _SUBSCRIBER_LOCK:
        _SUBSCRIBERS.clear()


def _notify_subscribers(space_name: str, diff_result: ScanDiffResult) -> None:
    with _SUBSCRIBER_LOCK:
        current = list(_SUBSCRIBERS)
    for callback, space_filter in current:
        if space_filter is not None and space_name not in space_filter:
            continue
        try:
            callback(space_name, diff_result)
        except Exception as exc:
            logger.warning(
                "Subscriber callback failed for space '%s': %s", space_name, exc
            )


def _broadcast_file_space_changed(
    space_name: str, diff_result: ScanDiffResult
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "space_name": space_name,
        "spaces": [space_name],
        "from_generation": diff_result.from_generation,
        "to_generation": diff_result.to_generation,
        "merkle_root": diff_result.merkle_root,
        "added": diff_result.added,
        "modified": diff_result.modified,
        "deleted": diff_result.deleted,
        "added_count": diff_result.added_count,
        "modified_count": diff_result.modified_count,
        "deleted_count": diff_result.deleted_count,
    }
    try:
        from core import events as core_events

        res = core_events.broadcast(
            "on_file_space_changed", payload, emit_module="file-space"
        )
        logger.info(
            "[file-space-watcher] Space '%s' updated (gen %d -> %d, +%d ~%d -%d) | hooks: %s",
            space_name,
            diff_result.from_generation,
            diff_result.to_generation,
            diff_result.added_count,
            diff_result.modified_count,
            diff_result.deleted_count,
            res,
        )
    except Exception as exc:
        logger.debug("Event broadcast skipped or failed: %s", exc)
    return payload


class _FileSpaceWatchdogHandler(FileSystemEventHandler):
    """Watchdog event handler routing file system events to FileSpaceWatcherServiceWorker."""

    def __init__(self, worker: "FileSpaceWatcherServiceWorker") -> None:
        super().__init__()
        self.worker = worker

    def on_any_event(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False):
            return
        src_path = getattr(event, "src_path", None)
        if src_path:
            self.worker.notify_file_event(str(src_path))
        dest_path = getattr(event, "dest_path", None)
        if dest_path:
            self.worker.notify_file_event(str(dest_path))


class FileSpaceWatcherServiceWorker(BaseServiceWorker):
    """
    Daemon service worker that watches registered spaces (`watch=True`),
    debounces rapid file changes (500ms default), yields to `.yscb.lock`
    transactions, updates YFP2 snapshots, and broadcasts `on_file_space_changed`.
    """

    DEFAULT_DEBOUNCE_SECONDS = 0.5

    def __init__(
        self,
        name: str = "file-space-watcher",
        context: Optional[Dict[str, Any]] = None,
        *,
        space_manager: Optional[FileSpaceManager] = None,
        scanner: Optional[FingerprintScanner] = None,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
    ) -> None:
        ctx = context or {}
        self._name = name
        self.context = ctx
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        project_root = ctx.get("project_root") or ctx.get("workspace_root")
        storage_root = ctx.get("storage_root")

        self.space_manager = space_manager or FileSpaceManager(
            project_root=Path(project_root) if project_root else None,
            storage_root=Path(storage_root) if storage_root else None,
        )
        self.scanner = scanner or FingerprintScanner(
            space_manager=self.space_manager,
            storage_root=self.space_manager.storage_root,
        )
        self.debounce_seconds = float(
            ctx.get("debounce_seconds", debounce_seconds)
        )

        self._lock = threading.Lock()
        self._dirty_spaces: Set[str] = set()
        self._last_event_time: float = 0.0
        self._refresh_count: int = 0
        self._events_received: int = 0
        self._deferred_by_lock_count: int = 0
        self._last_refresh_at: Optional[float] = None
        self._observer: Optional[Any] = None

    @property
    def name(self) -> str:
        """Unique service worker identifier."""
        return self._name

    def start(self, context: Optional[Dict[str, Any]] = None) -> None:
        """Start background watcher thread."""
        if context is not None and isinstance(context, dict):
            self.context.update(context)
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self.run, name=f"Worker-{self.name}", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop background watcher thread and release watchdog observer."""
        self._stop_event.set()
        self._stop_watchdog_observer()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        """Return whether the background thread is alive."""
        return bool(self._thread and self._thread.is_alive())

    def health_check(self) -> bool:
        """Probe whether the background watcher service is healthy."""
        return self.is_alive()

    def is_transaction_locked(self) -> bool:
        """
        Check whether a global `.yscb.lock` transaction lock is currently active
        in the project root or ys_codebase runtime directory.
        """
        p_root = self.space_manager.project_root
        candidates = [
            p_root / ".yscb.lock",
            p_root / "ys_codebase" / ".yscb.lock",
        ]
        if "lock_file" in self.context and self.context["lock_file"]:
            candidates.append(Path(self.context["lock_file"]))
        return any(c.exists() for c in candidates)

    def notify_file_event(self, file_path: str) -> List[str]:
        """
        Record a raw file system event and mark matching watched spaces as dirty.
        Returns the list of matched workspace names.
        """
        matched: List[str] = []
        p = Path(file_path)
        if p.name == ".yscb.lock" or p.name.endswith(".tmp"):
            return matched

        for s_name, cfg in self.space_manager.get_all_spaces().items():
            if not cfg.watch:
                continue
            if self.space_manager.file_belongs_to_space(p, cfg):
                matched.append(s_name)

        if matched:
            with self._lock:
                self._events_received += 1
                self._dirty_spaces.update(matched)
                self._last_event_time = time.monotonic()

        return matched

    def flush_dirty_spaces(self, *, force: bool = False) -> Dict[str, ScanDiffResult]:
        """
        If debounce window has elapsed and no `.yscb.lock` is active (or `force=True`),
        refresh all dirty spaces (and any spaces with pending lazy stabilization),
        invoke subscribers, and broadcast `on_file_space_changed`.
        """
        if self.is_transaction_locked():
            with self._lock:
                if self._dirty_spaces:
                    self._deferred_by_lock_count += 1
            return {}

        now_mono = time.monotonic()
        with self._lock:
            if not self._dirty_spaces:
                return {}
            if (
                not force
                and (now_mono - self._last_event_time) < self.debounce_seconds
            ):
                return {}
            target_spaces = sorted(self._dirty_spaces)
            self._dirty_spaces.clear()

        results: Dict[str, ScanDiffResult] = {}
        still_pending_spaces: Set[str] = set()

        for s_name in target_spaces:
            try:
                state, diff_res = self.scanner.scan_space(
                    s_name, background=True
                )
                self.scanner.snapshot_mgr.save_state(
                    state, self.scanner.get_snapshot_path(s_name)
                )
                results[s_name] = diff_res

                if any(
                    fp.pending_stabilization and not fp.is_deleted
                    for fp in state.entries.values()
                ):
                    still_pending_spaces.add(s_name)

                if diff_res.has_changes:
                    self._refresh_count += 1
                    self._last_refresh_at = time.time()
                    _notify_subscribers(s_name, diff_res)
                    _broadcast_file_space_changed(s_name, diff_res)
            except Exception as exc:
                logger.error(
                    "Error refreshing dirty space '%s': %s", s_name, exc
                )

        if still_pending_spaces:
            with self._lock:
                self._dirty_spaces.update(still_pending_spaces)
                if self._last_event_time == 0.0:
                    self._last_event_time = time.monotonic()

        return results

    def _start_watchdog_observer(self) -> None:
        if not HAS_WATCHDOG or Observer is None:
            return
        observer = Observer()
        handler = _FileSpaceWatchdogHandler(self)
        watched_dirs: Set[str] = set()

        for s_name, cfg in self.space_manager.get_all_spaces().items():
            if not cfg.watch:
                continue
            for inc_dir in self.space_manager.resolve_space_include(s_name):
                key = inc_dir.as_posix()
                if key not in watched_dirs:
                    watched_dirs.add(key)
                    try:
                        observer.schedule(handler, str(inc_dir), recursive=True)
                    except Exception as exc:
                        logger.warning(
                            "Failed to schedule watchdog on '%s': %s",
                            inc_dir,
                            exc,
                        )

        if watched_dirs:
            try:
                observer.start()
                self._observer = observer
            except Exception as exc:
                logger.warning("Failed to start watchdog observer: %s", exc)
                self._observer = None

    def _stop_watchdog_observer(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:
                pass
            self._observer = None

    def run(self) -> None:
        """Main background loop for FileSpaceWatcherServiceWorker."""
        _adjust_active_watcher_count(1)
        try:
            for s_name, cfg in self.space_manager.get_all_spaces().items():
                if cfg.watch and not self.scanner.get_snapshot_path(s_name).exists():
                    self.scanner.refresh(s_name, background=True)
        except Exception as exc:
            logger.warning("Initial space snapshot warm-up failed: %s", exc)

        self._start_watchdog_observer()
        poll_interval = min(0.1, max(0.02, self.debounce_seconds / 4.0))

        try:
            while not self._stop_event.is_set():
                self.flush_dirty_spaces(force=False)
                self._stop_event.wait(timeout=poll_interval)
        finally:
            _adjust_active_watcher_count(-1)
            self._stop_watchdog_observer()

    def get_custom_metrics(self) -> Dict[str, Any]:
        """Expose runtime telemetry for `yscb server status`."""
        with self._lock:
            pending_count = len(self._dirty_spaces)
        return {
            "watched_spaces": [
                s
                for s, cfg in self.space_manager.get_all_spaces().items()
                if cfg.watch
            ],
            "events_received": self._events_received,
            "refresh_count": self._refresh_count,
            "pending_dirty_spaces": pending_count,
            "deferred_by_lock_count": self._deferred_by_lock_count,
            "last_refresh_at": self._last_refresh_at,
            "watchdog_active": self._observer is not None,
        }
