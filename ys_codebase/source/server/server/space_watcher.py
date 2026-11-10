"""
CoreSpaceWatcherServiceWorker: Background file system watcher hosted in `module:server`
for `core.space`, providing 500ms debouncing, `.yscb.lock` transaction deference,
incremental `patch_files` updates, composite/short-name union snapshot synchronization,
and `on_file_space_changed` (`emit_module="core"`) event broadcasting.
"""

from __future__ import annotations

import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple, Union

from core.context import is_foreground_active
from core.log import log_error, log_warn
from core.space.registry import SpaceConfig, SpaceRegistry, get_default_registry
from core.space.scanner import ScanDiffResult, SpaceScanner, get_default_scanner
from core.space.watcher import (
    broadcast_file_space_changed,
    get_active_watcher,
    is_watcher_active,
    notify_subscribers,
    register_active_watcher,
    remove_watcher_state,
    resolve_watcher_state_path,
    subscribe,
    write_watcher_state,
)

from .service import BaseServiceWorker
from .watcher import _is_lock_file_active

_FAST_IGNORED_SEGMENTS: FrozenSet[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        ".cache",
        ".storage.local",
        ".modules",
        ".build",
        ".mirror",
        ".snapshots",
        ".temp",
        ".pytest_cache",
        "node_modules",
    }
)

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    FileSystemEvent = Any  # type: ignore[assignment,misc]
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = None  # type: ignore[assignment]


def _install_inotify_safe_watch_patch() -> None:
    """
    Guard `watchdog.observers.inotify_c.Inotify._add_watch` against transient `FileNotFoundError` (`ENOENT`)
    or `PermissionError` (`EACCES`) on individual subdirectories (e.g., concurrently deleted `.staging_*`/`.old_*`
    directories or virtiofs ghost dentries) during recursive `Observer.schedule()`, so watching the root
    directory never aborts as a whole.
    """
    try:
        from watchdog.observers.inotify_c import Inotify
        import errno as _errno

        orig_add_watch = getattr(Inotify, "_add_watch", None)
        if orig_add_watch is None or getattr(orig_add_watch, "_yscb_enoent_safe", False):
            return

        def _safe_add_watch(self: Any, path: bytes, mask: int) -> Any:
            try:
                return orig_add_watch(self, path, mask)
            except OSError as exc:
                if exc.errno in (_errno.ENOENT, _errno.EACCES, _errno.ENOTDIR):
                    return -1
                raise

        setattr(_safe_add_watch, "_yscb_enoent_safe", True)
        setattr(Inotify, "_add_watch", _safe_add_watch)
    except Exception:
        pass


if HAS_WATCHDOG:
    _install_inotify_safe_watch_patch()


class _CoreSpaceWatchdogHandler(FileSystemEventHandler):
    """Watchdog event handler routing file system events to CoreSpaceWatcherServiceWorker."""

    def __init__(self, worker: "CoreSpaceWatcherServiceWorker") -> None:
        super().__init__()
        self.worker = worker

    def on_any_event(self, event: FileSystemEvent) -> None:
        is_dir = bool(getattr(event, "is_directory", False))
        ev_type = str(getattr(event, "event_type", "modified"))
        if is_dir:
            if ev_type in ("created", "moved", "deleted"):
                with self.worker.bind_worker_context():
                    try:
                        setattr(event, "_yscb_handled", True)
                    except Exception:
                        pass
                    self._forward_dir_event(event, ev_type)
            return

        if ev_type not in ("created", "modified", "moved", "deleted"):
            return

        with self.worker.bind_worker_context():
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

    def on_created(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False) and not getattr(
            event, "_yscb_handled", False
        ):
            with self.worker.bind_worker_context():
                self._forward_dir_event(event, "created")

    def on_moved(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False) and not getattr(
            event, "_yscb_handled", False
        ):
            with self.worker.bind_worker_context():
                self._forward_dir_event(event, "moved")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False) and not getattr(
            event, "_yscb_handled", False
        ):
            with self.worker.bind_worker_context():
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


def _strip_macos_private_prefix(path_posix: str) -> str:
    """Normalizes macOS `/private/var/...` and `/private/tmp/...` paths by stripping leading `/private`."""
    if path_posix.startswith("/private/"):
        return path_posix[len("/private") :]
    return path_posix


def _canonical_dir_path(p: Union[str, Path]) -> Path:
    """Returns canonical realpath with platform case normalization for symlink-safe directory matching."""
    try:
        return Path(os.path.normcase(os.path.realpath(str(p))))
    except OSError:
        return Path(os.path.normcase(os.path.abspath(str(p))))


def _match_prefix_rel(raw_str: str, prefix: str) -> Optional[str]:
    clean_prefix = prefix.rstrip("/") + "/"
    if raw_str.startswith(clean_prefix):
        return raw_str[len(clean_prefix) :]
    if os.name == "nt" and raw_str.lower().startswith(clean_prefix.lower()):
        return raw_str[len(clean_prefix) :]
    norm_raw = _strip_macos_private_prefix(raw_str)
    norm_prefix = _strip_macos_private_prefix(clean_prefix)
    if norm_raw.startswith(norm_prefix):
        return norm_raw[len(norm_prefix) :]
    try:
        canon_raw = os.path.normcase(os.path.realpath(raw_str)).replace("\\", "/")
        canon_pref = os.path.normcase(os.path.realpath(prefix.rstrip("/"))).replace("\\", "/") + "/"
        if canon_raw.startswith(canon_pref):
            return canon_raw[len(canon_pref) :]
    except OSError:
        pass
    return None


def _is_lock_path_active(lock_cand: Path) -> bool:
    """
    Probes whether `lock_cand` is actively held via `InterProcessLock` or contains a
    non-empty `'locked'` sentinel marker. Stale unlocked `.yscb.lock` files return False.
    """
    return _is_lock_file_active(lock_cand)


class CoreSpaceWatcherServiceWorker(BaseServiceWorker):
    """
    Daemon service worker hosted in `module:server` that monitors all `core.space` spaces
    with `watch=True` (including runtime ephemeral spaces and `compose` child entries),
    debounces rapid file changes (500ms default), yields to `.yscb.lock` transactions,
    incrementally patches `YFP2` snapshots, and broadcasts `on_file_space_changed` (`emit_module="core"`).
    """

    DEFAULT_DEBOUNCE_SECONDS = 0.5
    MAX_PATCH_PATHS_THRESHOLD = 200
    MAX_FOREGROUND_DEFER_SECONDS: float = 5.0
    HAS_WATCHDOG = HAS_WATCHDOG

    def __init__(
        self,
        name: str = "core-space-watcher",
        context: Optional[Dict[str, Any]] = None,
        *,
        registry: Optional[SpaceRegistry] = None,
        scanner: Optional[SpaceScanner] = None,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
        max_debounce_seconds: float = 5.0,
    ) -> None:
        super().__init__()
        self._name = name
        self.context: Dict[str, Any] = dict(context) if isinstance(context, dict) else {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        project_root = self.context.get("project_root") or self.context.get(
            "workspace_root"
        )
        yscb_dir = self.context.get("yscb_root") or self.context.get("yscb_dir")
        storage_root = self.context.get("storage_root")

        self.registry: SpaceRegistry = registry or get_default_registry(
            project_root=project_root,
            yscb_dir=yscb_dir,
        )
        self.scanner: SpaceScanner = scanner or get_default_scanner(
            registry=registry,
            project_root=self.registry.project_root,
            yscb_dir=self.registry.yscb_dir,
            storage_root=storage_root,
        )
        self.debounce_seconds = float(
            self.context.get("debounce_seconds", debounce_seconds)
        )
        self.max_debounce_seconds = float(
            self.context.get("max_debounce_seconds", max_debounce_seconds)
        )

        self._lock = threading.RLock()
        self._flush_lock = threading.RLock()
        self._dirty_spaces: Set[str] = set()
        self._dirty_paths_by_space: Dict[str, Set[Path]] = {}
        self._full_rescan_spaces: Set[str] = set()
        self._last_event_time: float = 0.0
        self._dirty_since_mono: Optional[float] = None
        self._refresh_count: int = 0
        self._events_received: int = 0
        self._deferred_by_lock_count: int = 0
        self._deferred_by_foreground_count: int = 0
        self._last_refresh_at: Optional[float] = None
        self._observer: Optional[Any] = None
        self._scheduled_dirs: Set[str] = set()
        self._scheduled_watches: Dict[str, Any] = {}
        self._state_file_path: Optional[Path] = None

    @property
    def name(self) -> str:
        """Unique service worker identifier."""
        return self._name

    @property
    def project_root(self) -> Path:
        """Workspace project root managed by this watcher."""
        return self.registry.project_root

    def _rebind_context_if_needed(self, context: Dict[str, Any]) -> None:
        self.context.update(context)
        if "debounce_seconds" in context:
            self.debounce_seconds = float(context["debounce_seconds"])
        if "max_debounce_seconds" in context:
            self.max_debounce_seconds = float(context["max_debounce_seconds"])
        project_root = self.context.get("project_root") or self.context.get(
            "workspace_root"
        )
        yscb_dir = self.context.get("yscb_root") or self.context.get("yscb_dir")
        storage_root = self.context.get("storage_root")
        if project_root or yscb_dir:
            self.registry = get_default_registry(
                project_root=project_root, yscb_dir=yscb_dir
            )
            self.scanner = get_default_scanner(
                project_root=self.registry.project_root,
                yscb_dir=self.registry.yscb_dir,
                storage_root=storage_root,
            )

    def start(self, context: Optional[Dict[str, Any]] = None) -> None:
        """Start background watcher thread."""
        if context is not None and isinstance(context, dict):
            self._rebind_context_if_needed(context)
        if self._thread and self._thread.is_alive():
            return
        prev_watcher = get_active_watcher()
        if prev_watcher is not None and prev_watcher is not self:
            try:
                stop_fn = getattr(prev_watcher, "stop", None)
                if callable(stop_fn):
                    stop_fn(timeout=0.5)
            except Exception:
                pass
        self._stop_event.clear()
        self.set_state(self.STATE_STARTING)
        register_active_watcher(self)
        self._thread = self.start_managed_thread(
            self.run,
            context=self.context,
            thread_name=f"Worker-{self.name}",
        )

    def stop(self, timeout: float = 1.0) -> None:
        """Stop background watcher thread and release watchdog observer."""
        self._stop_event.set()
        if get_active_watcher() is self:
            register_active_watcher(None)
        self._stop_watchdog_observer()
        self._remove_watcher_state_file()
        self.stop_managed_thread(
            self._thread,
            self._stop_event,
            timeout=timeout,
        )
        self._thread = None

    def is_alive(self) -> bool:
        """Return whether the background thread is alive (race-free during startup)."""
        if self._stop_event.is_set():
            return False
        th = self._thread
        if th is not None and th.is_alive():
            return True
        return getattr(self, "_state", self.STATE_STOPPED) in (
            self.STATE_STARTING,
            self.STATE_READY,
            self.STATE_UPDATING,
        )

    def health_check(self) -> bool:
        """Probe whether the background watcher service is healthy."""
        return self.is_alive()

    def _watched_space_configs(self) -> List[SpaceConfig]:
        return [
            s
            for s in self.registry.list_spaces()
            if s.watch
            and s.owner != ""
            and bool(self.registry.collect_all_entry_paths(s.qualified_name))
        ]

    def _watched_space_names(self) -> List[str]:
        return [s.qualified_name for s in self._watched_space_configs()]

    def is_transaction_locked(self) -> bool:
        """
        Check whether a global `.yscb.lock` transaction lock is currently active
        in `project_root`, `yscb_dir`, or `yscb_dir/.cache/.yscb.lock` using non-blocking
        `InterProcessLock` probing so stale unlocked `.yscb.lock` files never freeze watching.
        """
        p_root = self.registry.project_root
        y_dir = self.registry.yscb_dir

        lock_candidates: List[Path] = []
        if "lock_file" in self.context and self.context["lock_file"]:
            lock_candidates.append(Path(str(self.context["lock_file"])))

        for cand in (
            p_root / ".yscb.lock",
            y_dir / ".yscb.lock",
            y_dir / ".cache" / ".yscb.lock",
        ):
            if cand not in lock_candidates:
                lock_candidates.append(cand)

        try:
            from core import uri

            resolved_lock = uri.resolve("cache://.yscb.lock", interactive=False)
            if resolved_lock and not str(resolved_lock).startswith("!undefined"):
                cand_p = Path(str(resolved_lock))
                if cand_p not in lock_candidates:
                    lock_candidates.append(cand_p)
        except Exception:
            pass

        for lock_cand in lock_candidates:
            if _is_lock_path_active(lock_cand):
                return True
        return False

    def _extract_rel_for_fast_ignore(self, raw_str: str) -> str:
        rel_check = _match_prefix_rel(raw_str, self.registry.project_root.as_posix())
        if rel_check is not None:
            return rel_check
        for s_cfg in self._watched_space_configs():
            for entry_p in self.registry.collect_all_entry_paths(s_cfg.qualified_name):
                rel_inc = _match_prefix_rel(raw_str, entry_p.as_posix())
                if rel_inc is not None:
                    return rel_inc
        return raw_str.rsplit("/", 1)[-1]

    def _dir_belongs_to_space(self, dir_abs: Path, s_cfg: SpaceConfig) -> bool:
        canon_dir = _canonical_dir_path(dir_abs)
        all_entries = self.registry.collect_all_entry_paths(s_cfg.qualified_name)
        for entry_p in all_entries:
            if entry_p.is_file():
                continue
            canon_entry = _canonical_dir_path(entry_p)
            if canon_dir == canon_entry:
                return True
            try:
                rel = canon_dir.relative_to(canon_entry)
                if str(rel) != "." and not str(rel).startswith(".."):
                    try:
                        real_dir = Path(os.path.realpath(str(dir_abs)))
                        real_entry = Path(os.path.realpath(str(entry_p)))
                        aligned_dir = entry_p / real_dir.relative_to(real_entry)
                    except (OSError, ValueError):
                        aligned_dir = dir_abs
                    if not s_cfg.is_dir_excluded_fast(
                        aligned_dir, entry_p, self.registry.project_root
                    ):
                        return True
            except ValueError:
                try:
                    rel_rev = canon_entry.relative_to(canon_dir)
                    if not str(rel_rev).startswith(".."):
                        return True
                except ValueError:
                    continue
        return False

    def _normalize_event_path(self, file_path: Union[str, Path]) -> Path:
        """
        Normalizes an incoming file system event path and aligns symlinked aliases
        (such as macOS `/private/var` -> `/var`) back onto `self.registry.project_root`.
        """
        p = Path(str(file_path))
        raw_abs = (
            Path(os.path.normpath(str(p)))
            if p.is_absolute()
            else Path(os.path.normpath(str(self.registry.project_root / p)))
        )
        proj_root = self.registry.project_root
        try:
            canon_target = _canonical_dir_path(raw_abs)
            canon_proj = _canonical_dir_path(proj_root)
            if canon_target == canon_proj:
                return proj_root
            rel_to_proj = canon_target.relative_to(canon_proj)
            if str(rel_to_proj) != "." and not str(rel_to_proj).startswith(".."):
                raw_norm = os.path.normcase(str(raw_abs))
                proj_norm = os.path.normcase(str(proj_root))
                if not raw_norm.startswith(proj_norm + os.sep):
                    real_target = Path(os.path.realpath(str(raw_abs)))
                    real_proj = Path(os.path.realpath(str(proj_root)))
                    return Path(os.path.normpath(str(proj_root / real_target.relative_to(real_proj))))
        except (OSError, ValueError):
            pass
        try:
            norm_raw_posix = _strip_macos_private_prefix(raw_abs.as_posix())
            norm_proj_posix = _strip_macos_private_prefix(proj_root.as_posix()).rstrip("/") + "/"
            if norm_raw_posix.startswith(norm_proj_posix):
                rel_tail = norm_raw_posix[len(norm_proj_posix) :]
                return Path(os.path.normpath(str(proj_root / rel_tail)))
        except Exception:
            pass
        return raw_abs

    def notify_file_event(
        self,
        file_path: Union[str, Path],
        is_directory: bool = False,
        event_type: str = "modified",
    ) -> List[str]:
        """
        Record a raw file system event and mark matching watched spaces (`watch=True`) as dirty.
        Performs fast string-segment filtering prior to path resolution, tracks per-space
        dirty file paths, and escalates directory create/move/delete events to full space rescan.
        Returns the list of matched `<owner>/<space>` qualified names.
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

        rel_check = self._extract_rel_for_fast_ignore(raw_str)
        if any(
            seg in _FAST_IGNORED_SEGMENTS
            for seg in rel_check.split("/")
            if seg
        ):
            return []

        abs_p = self._normalize_event_path(file_path)

        matched: List[str] = []
        watched_spaces = self._watched_space_configs()

        if is_directory:
            if event_type not in ("created", "moved", "deleted"):
                return matched
            for s_cfg in watched_spaces:
                if self._dir_belongs_to_space(abs_p, s_cfg):
                    matched.append(s_cfg.qualified_name)
            if matched:
                with self._lock:
                    now_m = time.monotonic()
                    self._events_received += 1
                    self._dirty_spaces.update(matched)
                    self._full_rescan_spaces.update(matched)
                    self._last_event_time = now_m
                    if self._dirty_since_mono is None:
                        self._dirty_since_mono = now_m
                    self.scanner.mark_watcher_dirty(True)
            return matched

        for s_cfg in watched_spaces:
            q_name = s_cfg.qualified_name
            try:
                if hasattr(self.registry, "is_path_matched_fast"):
                    is_matched = self.registry.is_path_matched_fast(
                        abs_p, q_name, is_dir=False
                    )
                else:
                    try:
                        match_res = self.registry.match_path(abs_p, space=q_name)
                    except TypeError:
                        match_res = self.registry.match_path(abs_p, space_query=q_name)
                    is_matched = match_res.matched
                if is_matched:
                    matched.append(q_name)
            except Exception:
                continue

        if matched:
            with self._lock:
                now_m = time.monotonic()
                self._events_received += 1
                self._dirty_spaces.update(matched)
                for q_name in matched:
                    self._dirty_paths_by_space.setdefault(q_name, set()).add(abs_p)
                self._last_event_time = now_m
                if self._dirty_since_mono is None:
                    self._dirty_since_mono = now_m
                self.scanner.mark_watcher_dirty(True)

        return matched

    def _refresh_or_patch_space(
        self,
        q_name: str,
        dirty_paths: Set[Path],
        full_rescan: bool,
        *,
        batch_qnames: Optional[Set[str]] = None,
        sync_dependents: bool = True,
    ) -> Tuple[ScanDiffResult, bool]:
        has_snap = self.scanner._has_existing_snapshot(q_name)
        use_patch = (
            not full_rescan
            and 0 < len(dirty_paths) <= self.MAX_PATCH_PATHS_THRESHOLD
            and has_snap
        )
        if use_patch:
            state = self.scanner.patch_files(q_name, dirty_paths)
            diff_res = state.last_diff
            if diff_res is None:
                diff_res = self.scanner._scan_single_query(q_name)
                use_patch = False
        else:
            diff_res = self.scanner._scan_single_query(q_name)

        if diff_res.has_changes:
            with self._lock:
                self._refresh_count += 1
                self._last_refresh_at = time.time()
            if sync_dependents:
                self.scanner.sync_dependent_snapshots(
                    q_name,
                    dirty_paths if use_patch else None,
                    exclude_keys=batch_qnames,
                )
                try:
                    self.touch_activity()
                except Exception:
                    pass
                notify_subscribers(q_name, diff_res)
                broadcast_file_space_changed(q_name, diff_res)

        return diff_res, use_patch

    def _rollback_space_batch(
        self,
        q_name: str,
        dirty_paths: Set[Path],
        full_rescan: bool,
    ) -> None:
        with self._lock:
            now_m = time.monotonic()
            self._dirty_spaces.add(q_name)
            if dirty_paths:
                self._dirty_paths_by_space.setdefault(q_name, set()).update(
                    dirty_paths
                )
            if full_rescan:
                self._full_rescan_spaces.add(q_name)
            if self._last_event_time == 0.0:
                self._last_event_time = now_m
            if self._dirty_since_mono is None:
                self._dirty_since_mono = now_m
            self.scanner.mark_watcher_dirty(True)

    def _finalize_dirty_marker(self) -> None:
        with self._lock:
            has_remaining = bool(self._dirty_spaces)
            if not has_remaining:
                self._dirty_since_mono = None
            self.scanner.mark_watcher_dirty(has_remaining)

    def _expand_query_to_dirty_qnames(
        self, space_query: Optional[Union[str, Iterable[str]]]
    ) -> List[str]:
        if space_query is None:
            with self._lock:
                return sorted(self._dirty_spaces)
        if not isinstance(space_query, str) and isinstance(space_query, Iterable):
            combined_cands: List[str] = []
            for item in space_query:
                q_item = str(item or "").strip()
                if not q_item or q_item == "*":
                    with self._lock:
                        return sorted(self._dirty_spaces)
                try:
                    participating = self.registry._collect_participating_spaces(q_item)
                    for s in participating:
                        if s.qualified_name not in combined_cands:
                            combined_cands.append(s.qualified_name)
                except Exception:
                    pass
                if q_item not in combined_cands:
                    combined_cands.append(q_item)
            with self._lock:
                return [name for name in combined_cands if name in self._dirty_spaces]
        if str(space_query).strip() in ("", "*"):
            with self._lock:
                return sorted(self._dirty_spaces)
        q = str(space_query).strip()
        try:
            participating = self.registry._collect_participating_spaces(q)
            cand_qnames = [s.qualified_name for s in participating]
            if q not in cand_qnames:
                cand_qnames.append(q)
        except Exception:
            cand_qnames = [q]
        with self._lock:
            return [name for name in cand_qnames if name in self._dirty_spaces]

    def _execute_space_flush_batch(
        self,
        target_spaces: List[str],
        dirty_batch: Dict[str, Set[Path]],
        full_rescan_batch: Set[str],
        *,
        error_verb: str = "refreshing dirty space",
    ) -> Dict[str, ScanDiffResult]:
        """
        Shared batch execution helper for `flush_space_now` and `flush_dirty_spaces`.
        Updates all target spaces, synchronizes dependent snapshots (synthetic short-name unions,
        composite spaces, and `__all__`), and only afterwards notifies subscribers and broadcasts
        `on_file_space_changed`.
        """
        batch_set = set(target_spaces)
        results: Dict[str, ScanDiffResult] = {}
        changed_diffs: List[Tuple[str, ScanDiffResult]] = []
        combined_patch_paths: Set[Path] = set()
        all_patchable = True
        self.set_state(self.STATE_UPDATING)
        try:
            for q_name in target_spaces:
                s_dirty = dirty_batch.get(q_name, set())
                s_full = q_name in full_rescan_batch
                try:
                    diff_res, used_patch = self._refresh_or_patch_space(
                        q_name,
                        s_dirty,
                        s_full,
                        batch_qnames=batch_set,
                        sync_dependents=False,
                    )
                    results[q_name] = diff_res
                    if diff_res.has_changes:
                        changed_diffs.append((q_name, diff_res))
                        if used_patch:
                            combined_patch_paths.update(s_dirty)
                        else:
                            all_patchable = False
                except Exception as exc:
                    self._rollback_space_batch(q_name, s_dirty, s_full)
                    log_error(f"Error {error_verb} '{q_name}': {exc}")

            if changed_diffs:
                changed_qnames = [q_name for q_name, _ in changed_diffs]
                dep_dirty = (
                    combined_patch_paths
                    if (
                        all_patchable
                        and 0 < len(combined_patch_paths) <= self.MAX_PATCH_PATHS_THRESHOLD
                    )
                    else None
                )
                self.scanner.sync_dependent_snapshots_batch(
                    changed_qnames,
                    dep_dirty,
                    exclude_keys=batch_set,
                )
                try:
                    self.touch_activity()
                except Exception:
                    pass
                for q_name, diff_res in changed_diffs:
                    notify_subscribers(q_name, diff_res)
                    broadcast_file_space_changed(q_name, diff_res)
        finally:
            if not self._stop_event.is_set():
                self.set_state(self.STATE_READY)

        self._finalize_dirty_marker()
        return results

    def flush_space_now(
        self, space_query: Optional[Union[str, Iterable[str]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Synchronously flush pending dirty paths for `space_query` (supports `<owner>/<space>`,
        `<space>` short-name union, `compose` spaces, an iterable of queries, or `None` for all dirty spaces)
        without waiting for the debounce window.
        """
        with self._flush_lock:
            target_qnames = self._expand_query_to_dirty_qnames(space_query)
            if not target_qnames:
                return None

            if self.is_transaction_locked():
                with self._lock:
                    if self._dirty_spaces:
                        self._deferred_by_lock_count += 1
                return None

            active_qnames: List[str] = []
            dirty_batch: Dict[str, Set[Path]] = {}
            full_rescan_batch: Set[str] = set()
            with self._lock:
                for q_name in target_qnames:
                    is_dirty = q_name in self._dirty_spaces
                    dirty_paths = set(self._dirty_paths_by_space.pop(q_name, set()))
                    full_rescan = q_name in self._full_rescan_spaces
                    self._full_rescan_spaces.discard(q_name)
                    self._dirty_spaces.discard(q_name)
                    if not is_dirty and not dirty_paths and not full_rescan:
                        continue
                    active_qnames.append(q_name)
                    dirty_batch[q_name] = dirty_paths
                    if full_rescan:
                        full_rescan_batch.add(q_name)

            if not active_qnames:
                return None

            results = self._execute_space_flush_batch(
                active_qnames,
                dirty_batch,
                full_rescan_batch,
                error_verb="flushing space immediately",
            )
            last_dict: Optional[Dict[str, Any]] = None
            for q_name in active_qnames:
                if q_name in results:
                    last_dict = results[q_name].to_dict()
            return last_dict

    def flush_dirty_spaces(self, *, force: bool = False) -> Dict[str, ScanDiffResult]:
        """
        If debounce window has elapsed and no `.yscb.lock` is active (or `force=True`),
        refresh all dirty spaces, invoke subscribers, and broadcast `on_file_space_changed`.
        """
        now_mono = time.monotonic()
        max_debounce_sec = float(getattr(self, "max_debounce_seconds", 5.0))
        with self._lock:
            if not self._dirty_spaces:
                return {}
            dirty_age_pre = (
                (now_mono - self._dirty_since_mono)
                if self._dirty_since_mono is not None
                else 0.0
            )
            if (
                not force
                and (now_mono - self._last_event_time) < self.debounce_seconds
                and dirty_age_pre < max_debounce_sec
            ):
                return {}

        max_defer_sec = float(getattr(self, "MAX_FOREGROUND_DEFER_SECONDS", 5.0))
        if not force and is_foreground_active():
            with self._lock:
                if self._dirty_spaces:
                    dirty_age = (
                        (now_mono - self._dirty_since_mono)
                        if self._dirty_since_mono is not None
                        else 0.0
                    )
                    if dirty_age < max_defer_sec:
                        self._deferred_by_foreground_count += 1
                        return {}

        if self.is_transaction_locked():
            with self._lock:
                if self._dirty_spaces:
                    self._deferred_by_lock_count += 1
            return {}

        with self._flush_lock:
            with self._lock:
                if not self._dirty_spaces:
                    return {}
                now_recheck = time.monotonic()
                dirty_age_post = (
                    (now_recheck - self._dirty_since_mono)
                    if self._dirty_since_mono is not None
                    else 0.0
                )
                if (
                    not force
                    and (now_recheck - self._last_event_time) < self.debounce_seconds
                    and dirty_age_post < max_debounce_sec
                ):
                    return {}
                target_spaces = sorted(self._dirty_spaces)
                self._dirty_spaces.clear()
                self._dirty_since_mono = None
                dirty_batch: Dict[str, Set[Path]] = {
                    s: set(self._dirty_paths_by_space.pop(s, set()))
                    for s in target_spaces
                }
                full_rescan_batch: Set[str] = set(self._full_rescan_spaces)
                self._full_rescan_spaces.difference_update(target_spaces)

            return self._execute_space_flush_batch(
                target_spaces,
                dirty_batch,
                full_rescan_batch,
                error_verb="refreshing dirty space",
            )

    def _resolve_watcher_state_path(self) -> Path:
        if self._state_file_path is not None:
            return self._state_file_path
        if "state_file" in self.context and self.context["state_file"]:
            self._state_file_path = Path(
                os.path.abspath(str(self.context["state_file"]))
            )
            return self._state_file_path
        self._state_file_path = resolve_watcher_state_path(
            self.registry.project_root, self.registry.yscb_dir
        )
        return self._state_file_path

    def _write_watcher_state_file(self) -> None:
        target = self._resolve_watcher_state_path()
        write_watcher_state(
            watched_spaces=self._watched_space_names(),
            watchdog_running=bool(self._observer is not None or (not HAS_WATCHDOG and self.is_alive())),
            project_root=self.registry.project_root,
            yscb_dir=self.registry.yscb_dir,
            state_file=target,
        )

    def _remove_watcher_state_file(self) -> None:
        with self._lock:
            if not self._dirty_spaces:
                self.scanner.mark_watcher_dirty(False)
        target = self._resolve_watcher_state_path()
        remove_watcher_state(
            project_root=self.registry.project_root,
            yscb_dir=self.registry.yscb_dir,
            state_file=target,
        )

    def sync_watched_directories(self) -> List[str]:
        """
        Synchronize `watchdog` Observer schedules across all spaces with `watch=True`
        (including composed child entries and newly defined runtime ephemeral spaces),
        and unschedule any removed directories to release OS directory handles.
        """
        desired_dirs: List[Path] = []
        seen_norm: Set[str] = set()
        for s_cfg in self._watched_space_configs():
            for entry_p in self.registry.collect_all_entry_paths(s_cfg.qualified_name):
                watch_dir = entry_p.parent if entry_p.is_file() else entry_p
                if not watch_dir.is_dir():
                    continue
                norm_k = os.path.normcase(str(watch_dir))
                if norm_k not in seen_norm:
                    seen_norm.add(norm_k)
                    desired_dirs.append(watch_dir)

        if ((HAS_WATCHDOG and Observer is not None) or self._observer is not None) and not self._stop_event.is_set():
            with self._lock:
                if self._observer is None and desired_dirs:
                    try:
                        obs = Observer()
                        obs.start()
                        self._observer = obs
                    except Exception as exc:
                        log_warn(f"Failed to start watchdog observer: {exc}")
                        self._observer = None

                if self._observer is not None:
                    stale_keys = [k for k in self._scheduled_dirs if k not in seen_norm]
                    for stale_k in stale_keys:
                        self._scheduled_dirs.discard(stale_k)
                        watch_obj = self._scheduled_watches.pop(stale_k, None)
                        if watch_obj is not None:
                            try:
                                unsched_fn = getattr(self._observer, "unschedule", None)
                                if callable(unsched_fn):
                                    unsched_fn(watch_obj)
                            except Exception:
                                pass

                    handler = _CoreSpaceWatchdogHandler(self)
                    for w_dir in desired_dirs:
                        norm_k = os.path.normcase(str(w_dir))
                        if norm_k not in self._scheduled_dirs:
                            scheduled_ok = False
                            for attempt in range(2):
                                try:
                                    watch_obj = self._observer.schedule(
                                        handler, str(w_dir), recursive=True
                                    )
                                    self._scheduled_dirs.add(norm_k)
                                    self._scheduled_watches[norm_k] = watch_obj
                                    scheduled_ok = True
                                    break
                                except FileNotFoundError as fnf_exc:
                                    if attempt == 0 and w_dir.is_dir():
                                        continue
                                    log_warn(
                                        f"Failed to schedule watchdog on '{w_dir}': {fnf_exc}"
                                    )
                                except Exception as exc:
                                    log_warn(
                                        f"Failed to schedule watchdog on '{w_dir}': {exc}"
                                    )
                                    break

        if self.is_alive() or self._observer is not None:
            self._write_watcher_state_file()

        return [d.as_posix() for d in desired_dirs]

    def _stop_watchdog_observer(self) -> None:
        with self._lock:
            obs = self._observer
            self._observer = None
            self._scheduled_dirs.clear()
            self._scheduled_watches.clear()
        if obs is not None:
            try:
                obs.stop()
                obs.join(timeout=0.5)
            except Exception:
                pass

    def run(self) -> None:
        """Main background loop for CoreSpaceWatcherServiceWorker."""
        self.set_state(self.STATE_STARTING)
        register_active_watcher(self)
        if not self._stop_event.is_set():
            self.sync_watched_directories()
            self._write_watcher_state_file()

        try:
            watched_cfgs = self._watched_space_configs()
            missing_any = any(
                not self.scanner._has_existing_snapshot(s_cfg.qualified_name)
                for s_cfg in watched_cfgs
            )
            missing_unified = not self.scanner._has_existing_snapshot(
                self.scanner.UNIFIED_KEY
            )
            if not self._stop_event.is_set():
                if missing_any and missing_unified:
                    self.scanner.scan(None)
                else:
                    for s_cfg in watched_cfgs:
                        if self._stop_event.is_set():
                            break
                        if is_foreground_active():
                            self._stop_event.wait(timeout=0.05)
                            if self._stop_event.is_set():
                                break
                        q_name = s_cfg.qualified_name
                        if not self.scanner._has_existing_snapshot(q_name):
                            self.scanner.scan(q_name)
                    if not self._stop_event.is_set() and missing_unified:
                        self.scanner._scan_single_query(None)
        except Exception as exc:
            log_warn(f"Initial core.space snapshot warm-up failed: {exc}")

        if not self._stop_event.is_set():
            self.set_state(self.STATE_READY)

        poll_interval = min(0.1, max(0.02, self.debounce_seconds / 4.0))
        try:
            while not self._stop_event.is_set():
                self.flush_dirty_spaces(force=False)
                self._stop_event.wait(timeout=poll_interval)
        finally:
            self.set_state(self.STATE_STOPPED)
            if get_active_watcher() is self:
                register_active_watcher(None)
            self._stop_watchdog_observer()
            self._remove_watcher_state_file()

    def get_custom_metrics(self) -> Dict[str, Any]:
        """Expose runtime telemetry for `yscb server status`."""
        with self._lock:
            pending_count = len(self._dirty_spaces)
            events_received = self._events_received
            refresh_count = self._refresh_count
            deferred_count = self._deferred_by_lock_count
            deferred_fg_count = self._deferred_by_foreground_count
            last_refresh_at = self._last_refresh_at
            scheduled_count = len(self._scheduled_dirs)
        return {
            "watched_spaces": self._watched_space_names(),
            "scheduled_dir_count": scheduled_count,
            "events_received": events_received,
            "refresh_count": refresh_count,
            "pending_dirty_spaces": pending_count,
            "deferred_by_lock_count": deferred_count,
            "deferred_by_foreground_count": deferred_fg_count,
            "last_refresh_at": last_refresh_at,
            "watchdog_active": self._observer is not None,
        }


__all__ = (
    "CoreSpaceWatcherServiceWorker",
    "HAS_WATCHDOG",
    "is_watcher_active",
    "subscribe",
)
