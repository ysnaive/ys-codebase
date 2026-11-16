"""Pure-standard-library debounced directory watcher with echo-suppression filtering and scandir efficiency."""

from __future__ import annotations

import os
from dataclasses import dataclass
import stat
import threading
import time
from typing import Callable, Optional, Sequence

from core.filesystem.fs.atomic import is_atomic_staging_filename, is_contained_nonsymlink_path, is_symlink_or_reparse, walk_nonsymlink_dir_tree
from core.foundation.observability import MAX_SAFE_WAIT_SEC, validate_non_negative_sec
from core.foundation.primitives import HostPath, require_typed_tuple

_IGNORED_DIR_PREFIXES = (".tmp_", ".staging_", "__pycache__")
EchoSuppressionHook = Callable[[HostPath, int, int, int], bool]


@dataclass(frozen=True, slots=True)
class _FileStatStamp:
    mtime_ns: int
    size: int
    ino: int


def _record_regular_watch_entry(entry: os.DirEntry[str], out_state: dict[HostPath, _FileStatStamp]) -> None:
    if entry.is_symlink() or is_symlink_or_reparse(entry.path) or is_atomic_staging_filename(entry.name):
        return
    try:
        if not entry.is_dir(follow_symlinks=False):
            st = entry.stat(follow_symlinks=False)
            if stat.S_ISREG(st.st_mode):
                out_state[HostPath(entry.path)] = _FileStatStamp(st.st_mtime_ns, st.st_size, st.st_ino)
    except (OSError, ValueError):
        return


def _scan_dir_tree(root_dir: str, out_state: dict[HostPath, _FileStatStamp]) -> None:
    for _cur_dir, entries in walk_nonsymlink_dir_tree(root_dir, ignored_dir_prefixes=_IGNORED_DIR_PREFIXES):
        for entry in entries:
            _record_regular_watch_entry(entry, out_state)


def _normalize_prefix_pair(hp: HostPath) -> tuple[str, str]:
    base = hp.comparison_key.rstrip("/\\")
    return (base, f"{base}{os.sep}")


def _is_under_any_prefix(hp: HostPath, prefixes: tuple[tuple[str, str], ...]) -> bool:
    norm_cand = hp.comparison_key.rstrip("/\\")
    return any(norm_cand == exact or norm_cand.startswith(with_sep) for exact, with_sep in prefixes)


def _diff_stat_snapshots(
    prev_map: dict[HostPath, _FileStatStamp],
    new_map: dict[HostPath, _FileStatStamp],
) -> list[tuple[HostPath, _FileStatStamp]]:
    cands = [(hp, sig) for hp, sig in new_map.items() if prev_map.get(hp) != sig]
    removed_stamp = _FileStatStamp(-1, -1, -1)
    cands.extend((old_hp, removed_stamp) for old_hp in set(prev_map.keys()) - set(new_map.keys()))
    return cands


def _stat_watchable_file(hp: HostPath, roots: Sequence[HostPath]) -> Optional[_FileStatStamp]:
    if is_atomic_staging_filename(hp.path.name) or not any(
        is_contained_nonsymlink_path(root, hp, allow_equal=True, is_dir=False, ignored_dir_prefixes=_IGNORED_DIR_PREFIXES)
        for root in roots
    ):
        return None
    try:
        st = os.lstat(str(hp))
    except OSError:
        return None
    return _FileStatStamp(st.st_mtime_ns, st.st_size, st.st_ino) if stat.S_ISREG(st.st_mode) else None


def _scan_resync_candidates(
    under_roots: Sequence[HostPath],
    roots: Sequence[HostPath],
    root_prefixes: tuple[tuple[str, str], ...],
) -> dict[HostPath, _FileStatStamp]:
    raw_partial: dict[HostPath, _FileStatStamp] = {}
    for hp in under_roots:
        if not _is_under_any_prefix(hp, root_prefixes):
            continue
        raw_r = str(hp)
        try:
            mode = os.lstat(raw_r).st_mode
        except OSError:
            continue
        if stat.S_ISREG(mode):
            stamp = _stat_watchable_file(hp, roots)
            if stamp is not None:
                raw_partial[hp] = stamp
        elif stat.S_ISDIR(mode) and any(is_contained_nonsymlink_path(root, hp, allow_equal=True, is_dir=True, ignored_dir_prefixes=_IGNORED_DIR_PREFIXES) for root in roots):
            _scan_dir_tree(raw_r, raw_partial)
    return {k: v for k, v in raw_partial.items() if _is_under_any_prefix(k, root_prefixes)}


class PollingDirectoryWatcher:
    """Watches target directories using lightweight scandir stat snapshots and non-blocking coalesced dispatch."""

    def __init__(
        self,
        roots: Sequence[HostPath],
        on_changed: Callable[[frozenset[HostPath]], None],
        *,
        debounce_sec: float = 0.2,
        poll_interval_sec: float = 0.05,
        is_suppressed: Optional[EchoSuppressionHook] = None,
    ) -> None:
        safe_deb = validate_non_negative_sec(debounce_sec, label="debounce_sec")
        safe_poll = validate_non_negative_sec(poll_interval_sec, label="poll_interval_sec")
        if safe_deb is None or safe_poll is None or safe_poll <= 0.0:
            raise ValueError("Watcher debounce_sec (>= 0) and poll_interval_sec (> 0) must be finite numbers.")
        self._roots = require_typed_tuple(roots, HostPath, "roots")
        self._on_changed = on_changed
        self._debounce_sec = max(0.02, safe_deb)
        self._poll_interval_sec = max(0.02, safe_poll)
        self._is_suppressed = is_suppressed
        self._state_lock = threading.Lock()
        self._scan_lock = threading.Lock()
        self._callback_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._dispatch_wake = threading.Event()
        self._pending_paths: set[HostPath] = set()
        self._last_change_ts: Optional[float] = None
        self._first_change_ts: Optional[float] = None
        self._dispatch_pending: set[HostPath] = set()
        self._poll_thread: Optional[threading.Thread] = None
        self._dispatch_thread: Optional[threading.Thread] = None
        self._snapshot: dict[HostPath, _FileStatStamp] = {}

    @property
    def tracked_paths(self) -> frozenset[HostPath]:
        """Return the current set of tracked file paths without exposing internal snapshot state."""
        with self._state_lock:
            return frozenset(self._snapshot.keys())

    def start(self) -> None:
        with self._state_lock:
            if (self._poll_thread is not None and self._poll_thread.is_alive()) or (
                self._dispatch_thread is not None and self._dispatch_thread.is_alive()
            ):
                return
            self._stop_event.clear()
            self._dispatch_wake.clear()
            self._pending_paths.clear()
            self._last_change_ts = None
            self._first_change_ts = None
            self._dispatch_pending.clear()
            self._snapshot = self._scan_all()
            pt = threading.Thread(target=self._run_loop, name="yscb-fs-watcher", daemon=True)
            dt = threading.Thread(
                target=self._dispatch_loop,
                name="yscb-fs-watcher-dispatch",
                daemon=True,
            )
            try:
                pt.start()
                dt.start()
            except BaseException:
                self._stop_event.set()
                self._dispatch_wake.set()
                if pt.is_alive():
                    pt.join(timeout=1.0)
                self._poll_thread = None
                self._dispatch_thread = None
                raise
            self._poll_thread = pt
            self._dispatch_thread = dt

    def stop(self) -> None:
        with self._state_lock:
            self._stop_event.set()
            self._dispatch_wake.set()
            pt = self._poll_thread
            dt = self._dispatch_thread
        join_tmo = min(MAX_SAFE_WAIT_SEC, max(2.0, self._poll_interval_sec * 2.0))
        if pt is not None and pt.is_alive() and pt is not threading.current_thread():
            pt.join(timeout=join_tmo)
        if dt is not None and dt.is_alive() and dt is not threading.current_thread():
            dt.join(timeout=join_tmo)
        with self._state_lock:
            if self._poll_thread is pt and (pt is None or not pt.is_alive()):
                self._poll_thread = None
            if self._dispatch_thread is dt and (dt is None or not dt.is_alive()):
                self._dispatch_thread = None

    def _scan_all(self) -> dict[HostPath, _FileStatStamp]:
        root_prefixes = tuple(_normalize_prefix_pair(r) for r in self._roots)
        if not root_prefixes:
            return {}
        state: dict[HostPath, _FileStatStamp] = {}
        for root in self._roots:
            raw_root = str(root)
            if is_symlink_or_reparse(raw_root):
                continue
            try:
                mode = os.lstat(raw_root).st_mode
            except OSError:
                continue
            if stat.S_ISREG(mode):
                stamp = _stat_watchable_file(root, self._roots)
                if stamp is not None:
                    state[root] = stamp
            elif stat.S_ISDIR(mode):
                _scan_dir_tree(raw_root, state)
        return {k: v for k, v in state.items() if _is_under_any_prefix(k, root_prefixes)}

    def resync_paths(self, under_roots: Sequence[HostPath]) -> frozenset[HostPath]:
        under_roots = require_typed_tuple(under_roots, HostPath, "under_roots")
        prefixes = tuple(_normalize_prefix_pair(r) for r in under_roots)
        root_prefixes = tuple(_normalize_prefix_pair(r) for r in self._roots)
        if not prefixes or not root_prefixes:
            return frozenset()
        if threading.current_thread() is self._dispatch_thread:
            return self._apply_resync_under_callback_lock(under_roots, prefixes, root_prefixes)
        with self._callback_lock:
            return self._apply_resync_under_callback_lock(under_roots, prefixes, root_prefixes)

    def _apply_resync_under_callback_lock(
        self,
        under_roots: Sequence[HostPath],
        prefixes: tuple[tuple[str, str], ...],
        root_prefixes: tuple[tuple[str, str], ...],
    ) -> frozenset[HostPath]:
        with self._scan_lock:
            partial = _scan_resync_candidates(under_roots, self._roots, root_prefixes)
            with self._state_lock:
                prev_under = {k: v for k, v in self._snapshot.items() if _is_under_any_prefix(k, prefixes)}
            unsuppressed = self._filter_unsuppressed_unlocked(_diff_stat_snapshots(prev_under, partial))
            with self._state_lock:
                flushed = {p for p in self._pending_paths if _is_under_any_prefix(p, prefixes)} | {
                    p for p in self._dispatch_pending if _is_under_any_prefix(p, prefixes)
                }
                kept_snap = {k: v for k, v in self._snapshot.items() if not _is_under_any_prefix(k, prefixes)}
                kept_snap.update(partial)
                self._snapshot = kept_snap
                self._pending_paths = {p for p in self._pending_paths if not _is_under_any_prefix(p, prefixes)}
                self._dispatch_pending = {p for p in self._dispatch_pending if not _is_under_any_prefix(p, prefixes)}
                if not self._pending_paths:
                    self._last_change_ts = None
                    self._first_change_ts = None
            return frozenset(flushed | unsuppressed)

    def _check_suppressed_safely(self, hp: HostPath, st: _FileStatStamp) -> bool:
        if self._is_suppressed is None:
            return False
        try:
            return bool(self._is_suppressed(hp, st.mtime_ns, st.size, st.ino))
        except (Exception, SystemExit, GeneratorExit):
            return False

    def _filter_unsuppressed_unlocked(
        self,
        raw_cands: list[tuple[HostPath, _FileStatStamp]],
    ) -> set[HostPath]:
        if self._is_suppressed is None or not raw_cands:
            return {hp for hp, _st in raw_cands}
        return {hp for hp, st in raw_cands if not self._check_suppressed_safely(hp, st)}

    def _commit_poll_diff_locked(
        self,
        new_snap: dict[HostPath, _FileStatStamp],
        diff_paths: set[HostPath],
        now: float,
        max_defer_sec: float,
    ) -> bool:
        self._snapshot = new_snap
        if diff_paths:
            self._pending_paths.update(diff_paths)
            self._last_change_ts = now
            if self._first_change_ts is None:
                self._first_change_ts = now
        if (
            self._pending_paths
            and self._last_change_ts is not None
            and self._first_change_ts is not None
            and ((now - self._last_change_ts) >= self._debounce_sec or (now - self._first_change_ts) >= max_defer_sec)
        ):
            self._dispatch_pending.update(self._pending_paths)
            self._pending_paths.clear()
            self._last_change_ts = None
            self._first_change_ts = None
            return True
        return False

    def _poll_once(self, max_defer_sec: float) -> bool:
        with self._scan_lock:
            new_snap = self._scan_all()
            with self._state_lock:
                raw_cands = _diff_stat_snapshots(self._snapshot, new_snap)
            diff_paths = self._filter_unsuppressed_unlocked(raw_cands)
            now = time.monotonic()
            with self._state_lock:
                return self._commit_poll_diff_locked(new_snap, diff_paths, now, max_defer_sec)

    def _run_loop(self) -> None:
        max_defer_sec = max(self._debounce_sec * 6.0, 2.0)
        while not self._stop_event.wait(self._poll_interval_sec):
            try:
                should_wake = self._poll_once(max_defer_sec)
            except (Exception, SystemExit, GeneratorExit):
                continue
            if should_wake:
                self._dispatch_wake.set()

    def _dispatch_loop(self) -> None:
        while not self._stop_event.is_set():
            self._dispatch_wake.wait()
            self._dispatch_wake.clear()
            while not self._stop_event.is_set() and self._dispatch_single_batch():
                pass

    def _requeue_failed_batch(self, batch: frozenset[HostPath]) -> None:
        now = time.monotonic()
        with self._state_lock:
            if self._stop_event.is_set():
                return
            self._pending_paths.update(batch)
            self._last_change_ts = now
            if self._first_change_ts is None:
                self._first_change_ts = now

    def _dispatch_single_batch(self) -> bool:
        with self._callback_lock:
            with self._state_lock:
                if not self._dispatch_pending:
                    return False
                batch = frozenset(self._dispatch_pending)
                self._dispatch_pending.clear()
            try:
                self._on_changed(batch)
            except (Exception, SystemExit, GeneratorExit):
                self._requeue_failed_batch(batch)
                return False
        return True
