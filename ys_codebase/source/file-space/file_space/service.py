"""
FileSpaceWatcherServiceWorker: Background file system watcher, 500ms debouncer,
transaction lock deference, YFP2 snapshot updater, and on_file_space_changed broadcaster.
"""
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple, Union

from .manager import FileSpaceManager
from .scanner import (
    FingerprintScanner,
    _adjust_active_watcher_count,
    _atomic_write_bytes,
    is_watcher_active,
)
from .schema import FileSpaceConfig, ScanDiffResult

logger = logging.getLogger("file_space.service")

_FAST_IGNORED_SEGMENTS: FrozenSet[str] = frozenset(
    {
        ".git",
        "__pycache__",
        ".cache",
        ".storage.local",
        ".modules",
        ".pytest_cache",
        "node_modules",
    }
)

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

        def touch_activity(self) -> bool:
            return False

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
        is_dir = bool(getattr(event, "is_directory", False))
        ev_type = str(getattr(event, "event_type", "modified"))
        if is_dir:
            if ev_type in ("moved", "deleted"):
                try:
                    setattr(event, "_yscb_handled", True)
                except Exception:
                    pass
                self._forward_dir_event(event, ev_type)
            return

        src_path = getattr(event, "src_path", None)
        if src_path:
            self.worker.notify_file_event(
                str(src_path), is_directory=False, event_type=ev_type
            )
        dest_path = getattr(event, "dest_path", None)
        if dest_path:
            self.worker.notify_file_event(
                str(dest_path), is_directory=False, event_type=ev_type
            )

    def on_moved(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False) and not getattr(
            event, "_yscb_handled", False
        ):
            self._forward_dir_event(event, "moved")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False) and not getattr(
            event, "_yscb_handled", False
        ):
            self._forward_dir_event(event, "deleted")

    def _forward_dir_event(self, event: FileSystemEvent, ev_type: str) -> None:
        src_path = getattr(event, "src_path", None)
        if src_path:
            self.worker.notify_file_event(
                str(src_path), is_directory=True, event_type=ev_type
            )
        dest_path = getattr(event, "dest_path", None)
        if dest_path:
            self.worker.notify_file_event(
                str(dest_path), is_directory=True, event_type=ev_type
            )


class FileSpaceWatcherServiceWorker(BaseServiceWorker):
    """
    Daemon service worker that watches registered spaces (`watch=True`),
    debounces rapid file changes (500ms default), yields to `.yscb.lock`
    transactions, updates YFP2 snapshots, and broadcasts `on_file_space_changed`.
    """

    DEFAULT_DEBOUNCE_SECONDS = 0.5
    MAX_PATCH_PATHS_THRESHOLD = 200

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
        self._dirty_paths_by_space: Dict[str, Set[Path]] = {}
        self._pending_paths_by_space: Dict[str, Set[Path]] = {}
        self._full_rescan_spaces: Set[str] = set()
        self._last_event_time: float = 0.0
        self._refresh_count: int = 0
        self._events_received: int = 0
        self._deferred_by_lock_count: int = 0
        self._last_refresh_at: Optional[float] = None
        self._observer: Optional[Any] = None
        self._state_file_path: Optional[Path] = None

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
        self._remove_watcher_state_file()
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
        if "lock_file" in self.context and self.context["lock_file"]:
            explicit_lock = Path(self.context["lock_file"])
            if explicit_lock.exists():
                try:
                    from core.platform.lock import InterProcessLock
                    probe = InterProcessLock(str(explicit_lock))
                    if probe.acquire(blocking=False):
                        probe.release()
                    else:
                        return True
                except Exception:
                    return True

        for legacy_cand in (p_root / ".yscb.lock", p_root / "ys_codebase" / ".yscb.lock"):
            if legacy_cand.exists():
                return True

        cache_lock_candidates = [
            p_root / "ys_codebase" / ".cache" / ".yscb.lock",
            p_root / ".cache" / ".yscb.lock",
        ]
        try:
            from core import uri
            resolved_lock = uri.resolve("cache://.yscb.lock", interactive=False)
            if resolved_lock and not str(resolved_lock).startswith("!undefined"):
                cache_lock_candidates.insert(0, Path(str(resolved_lock)))
        except Exception:
            pass

        for lock_cand in cache_lock_candidates:
            if lock_cand.exists():
                try:
                    from core.platform.lock import InterProcessLock
                    probe = InterProcessLock(str(lock_cand))
                    if probe.acquire(blocking=False):
                        probe.release()
                    else:
                        return True
                except Exception:
                    pass
        return False

    def _dir_belongs_to_space(self, dir_path: Path, cfg: FileSpaceConfig) -> bool:
        candidate = dir_path
        if not candidate.is_absolute():
            candidate = (self.space_manager.project_root / candidate).resolve()
        elif cfg.follow_symlinks:
            candidate = candidate.resolve()

        for inc_root in cfg.resolved_include_paths:
            try:
                rel = candidate.relative_to(inc_root).as_posix()
            except ValueError:
                try:
                    rel = candidate.resolve().relative_to(inc_root.resolve()).as_posix()
                except ValueError:
                    continue
            if rel == ".":
                return True
            if not cfg.is_dir_excluded(candidate.name, rel):
                return True
        return False

    def notify_file_event(
        self,
        file_path: Union[str, Path],
        is_directory: bool = False,
        event_type: str = "modified",
    ) -> List[str]:
        """
        Record a raw file system event and mark matching watched spaces as dirty.
        Performs fast string-segment filtering prior to path resolution, tracks per-space
        dirty file paths, and escalates directory move/delete events to full space rescan.
        Returns the list of matched workspace names.
        """
        raw_str = (
            file_path.as_posix()
            if isinstance(file_path, Path)
            else str(file_path).replace("\\", "/")
        )
        if not raw_str:
            return []

        base_name = raw_str.rsplit("/", 1)[-1]
        if (
            not base_name
            or base_name == ".yscb.lock"
            or base_name.endswith(".tmp")
            or base_name in _FAST_IGNORED_SEGMENTS
        ):
            return []

        proj_prefix = self.space_manager.project_root.as_posix().rstrip("/") + "/"
        rel_check = (
            raw_str[len(proj_prefix) :]
            if raw_str.startswith(proj_prefix)
            else raw_str
        )
        if any(
            seg in _FAST_IGNORED_SEGMENTS
            for seg in rel_check.split("/")
            if seg
        ):
            return []

        matched: List[str] = []
        p = Path(file_path)
        abs_p = (
            p
            if p.is_absolute()
            else (self.space_manager.project_root / p).resolve()
        )

        if is_directory:
            if event_type not in ("moved", "deleted"):
                return matched
            for s_name, cfg in self.space_manager.get_all_spaces().items():
                if not cfg.watch:
                    continue
                if self._dir_belongs_to_space(abs_p, cfg):
                    matched.append(s_name)
            if matched:
                with self._lock:
                    self._events_received += 1
                    self._dirty_spaces.update(matched)
                    self._full_rescan_spaces.update(matched)
                    self._last_event_time = time.monotonic()
                self.scanner.mark_watcher_dirty(True)
            return matched

        for s_name, cfg in self.space_manager.get_all_spaces().items():
            if not cfg.watch:
                continue
            if self.space_manager.file_belongs_to_space(abs_p, cfg):
                matched.append(s_name)

        if matched:
            with self._lock:
                self._events_received += 1
                self._dirty_spaces.update(matched)
                for s_name in matched:
                    self._dirty_paths_by_space.setdefault(s_name, set()).add(
                        abs_p
                    )
                self._last_event_time = time.monotonic()
            self.scanner.mark_watcher_dirty(True)

        return matched

    def _refresh_or_patch_space(
        self,
        s_name: str,
        dirty_paths: Set[Path],
        pending_paths: Set[Path],
        full_rescan: bool,
    ) -> Tuple[ScanDiffResult, Set[Path]]:
        paths_to_patch = dirty_paths | pending_paths
        snap_path = self.scanner.get_snapshot_path(s_name)
        use_patch = (
            not full_rescan
            and 0 < len(paths_to_patch) <= self.MAX_PATCH_PATHS_THRESHOLD
            and snap_path.exists()
        )
        if use_patch:
            state = self.scanner.patch_space_files(
                s_name, paths_to_patch, background=True
            )
            diff_res = state.last_diff
            if diff_res is None:
                state, diff_res = self.scanner.scan_space(
                    s_name, background=True
                )
                self.scanner.snapshot_mgr.save_state(state, snap_path)
        else:
            state, diff_res = self.scanner.scan_space(s_name, background=True)
            self.scanner.snapshot_mgr.save_state(state, snap_path)

        still_pending: Set[Path] = set()
        for fp in state.entries.values():
            if fp.pending_stabilization and not fp.is_deleted:
                src_root = (
                    Path(fp.source_root)
                    if fp.source_root
                    else self.space_manager.project_root
                )
                still_pending.add(src_root / fp.path)

        if diff_res.has_changes:
            self._refresh_count += 1
            self._last_refresh_at = time.time()
            try:
                self.touch_activity()
            except Exception:
                pass
            _notify_subscribers(s_name, diff_res)
            _broadcast_file_space_changed(s_name, diff_res)

        return diff_res, still_pending

    def flush_space_now(self, space_name: str) -> Optional[Dict[str, Any]]:
        """
        Synchronously flush pending dirty or lazy-stabilization paths for a single space
        without waiting for the debounce window. Returns serialized ScanDiffResult dict
        if a flush occurred, or None if the space was clean or transaction-locked.
        """
        if self.is_transaction_locked():
            with self._lock:
                if space_name in self._dirty_spaces:
                    self._deferred_by_lock_count += 1
            return None

        with self._lock:
            is_dirty = space_name in self._dirty_spaces
            dirty_paths = set(self._dirty_paths_by_space.pop(space_name, set()))
            pending_paths = set(
                self._pending_paths_by_space.pop(space_name, set())
            )
            full_rescan = space_name in self._full_rescan_spaces
            self._full_rescan_spaces.discard(space_name)
            self._dirty_spaces.discard(space_name)

        if not is_dirty and not dirty_paths and not pending_paths and not full_rescan:
            return None

        try:
            diff_res, still_pending = self._refresh_or_patch_space(
                space_name, dirty_paths, pending_paths, full_rescan
            )
            if still_pending:
                with self._lock:
                    self._pending_paths_by_space.setdefault(
                        space_name, set()
                    ).update(still_pending)
                    self._dirty_spaces.add(space_name)
                    if self._last_event_time == 0.0:
                        self._last_event_time = time.monotonic()
                self.scanner.mark_watcher_dirty(True)
            else:
                with self._lock:
                    has_remaining = bool(self._dirty_spaces)
                if not has_remaining:
                    self.scanner.mark_watcher_dirty(False)
            return diff_res.to_dict()
        except Exception as exc:
            logger.error(
                "Error flushing space '%s' immediately: %s", space_name, exc
            )
            return None

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
            dirty_batch: Dict[str, Set[Path]] = {
                s: set(self._dirty_paths_by_space.pop(s, set()))
                for s in target_spaces
            }
            pending_batch: Dict[str, Set[Path]] = {
                s: set(self._pending_paths_by_space.pop(s, set()))
                for s in target_spaces
            }
            full_rescan_batch: Set[str] = set(self._full_rescan_spaces)
            self._full_rescan_spaces.difference_update(target_spaces)

        results: Dict[str, ScanDiffResult] = {}
        still_pending_by_space: Dict[str, Set[Path]] = {}

        for s_name in target_spaces:
            try:
                diff_res, still_pending = self._refresh_or_patch_space(
                    s_name,
                    dirty_batch.get(s_name, set()),
                    pending_batch.get(s_name, set()),
                    s_name in full_rescan_batch,
                )
                results[s_name] = diff_res
                if still_pending:
                    still_pending_by_space[s_name] = still_pending
            except Exception as exc:
                logger.error(
                    "Error refreshing dirty space '%s': %s", s_name, exc
                )

        if still_pending_by_space:
            with self._lock:
                for s_name, p_set in still_pending_by_space.items():
                    self._pending_paths_by_space.setdefault(
                        s_name, set()
                    ).update(p_set)
                    self._dirty_spaces.add(s_name)
                if self._last_event_time == 0.0:
                    self._last_event_time = time.monotonic()
            self.scanner.mark_watcher_dirty(True)
        else:
            with self._lock:
                has_remaining = bool(self._dirty_spaces)
            if not has_remaining:
                self.scanner.mark_watcher_dirty(False)

        return results

    def _resolve_watcher_state_path(self) -> Path:
        if self._state_file_path is not None:
            return self._state_file_path
        p_root = self.space_manager.project_root
        if (p_root / "ys_codebase").is_dir():
            self._state_file_path = (
                p_root / "ys_codebase" / ".cache" / "file-space" / "watcher_state.json"
            )
        else:
            self._state_file_path = (
                p_root / ".cache" / "file-space" / "watcher_state.json"
            )
        return self._state_file_path

    def _write_watcher_state_file(self) -> None:
        try:
            target = self._resolve_watcher_state_path()
            payload = {
                "pid": os.getpid(),
                "watchdog_running": self._observer is not None,
                "watched_spaces": [
                    s
                    for s, cfg in self.space_manager.get_all_spaces().items()
                    if cfg.watch
                ],
                "updated_at": time.time(),
            }
            _atomic_write_bytes(
                target, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            )
        except Exception as exc:
            logger.debug("Failed to write watcher_state.json: %s", exc)

    def _remove_watcher_state_file(self) -> None:
        self.scanner.mark_watcher_dirty(False)
        if self._state_file_path is not None and self._state_file_path.exists():
            try:
                self._state_file_path.unlink()
            except OSError:
                pass

    def _start_watchdog_observer(self) -> None:
        if not HAS_WATCHDOG or Observer is None:
            return
        observer = Observer()
        handler = _FileSpaceWatchdogHandler(self)
        watched_dirs: Set[str] = set()

        for s_name, cfg in self.space_manager.get_all_spaces().items():
            if not cfg.watch:
                continue
            for inc_path in self.space_manager.resolve_space_include(s_name):
                inc_dir = inc_path.parent if inc_path.is_file() else inc_path
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
        _adjust_active_watcher_count(1, worker=self)
        try:
            for s_name, cfg in self.space_manager.get_all_spaces().items():
                if cfg.watch and not self.scanner.get_snapshot_path(s_name).exists():
                    self.scanner.refresh(s_name, background=True)
        except Exception as exc:
            logger.warning("Initial space snapshot warm-up failed: %s", exc)

        self._start_watchdog_observer()
        self._write_watcher_state_file()
        poll_interval = min(0.1, max(0.02, self.debounce_seconds / 4.0))

        try:
            while not self._stop_event.is_set():
                self.flush_dirty_spaces(force=False)
                self._stop_event.wait(timeout=poll_interval)
        finally:
            _adjust_active_watcher_count(-1, worker=self)
            self._stop_watchdog_observer()
            self._remove_watcher_state_file()

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
