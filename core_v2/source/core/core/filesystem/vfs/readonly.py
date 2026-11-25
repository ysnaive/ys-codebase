"""Dual-layer VFS and OS readonly file protection policy keyed by canonical HostPath."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
import stat
import threading
import time
from typing import Callable, Iterator, Optional, Sequence

from core.filesystem.fs import has_symlink_raw_path
from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary
from core.foundation.primitives import IS_WINDOWS, HostPath, require_pure_int, require_typed_tuple


def _validate_failed_path_pairs(raw: Sequence[tuple[HostPath, str]]) -> tuple[tuple[HostPath, str], ...]:
    if isinstance(raw, (str, bytes, bytearray, memoryview)) or not isinstance(raw, Sequence):
        raise ValueError("ReadonlySyncResult.failed_paths must be a Sequence of (HostPath, str) pairs.")
    cleaned: list[tuple[HostPath, str]] = []
    for item in raw:
        if isinstance(item, (str, bytes, bytearray, memoryview)) or not isinstance(item, Sequence) or len(item) != 2:
            raise ValueError("ReadonlySyncResult.failed_paths entry must be a (HostPath, str) pair.")
        hp, reason = item[0], item[1]
        if not isinstance(hp, HostPath) or type(reason) is not str:
            raise ValueError(f"ReadonlySyncResult.failed_paths requires (HostPath, str), got {item!r}")
        reason.encode("utf-8")
        cleaned.append((hp, reason))
    return tuple(cleaned)


def _is_stat_os_readonly(st: os.stat_result) -> bool:
    if not stat.S_ISREG(st.st_mode):
        return False
    if IS_WINDOWS:
        return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_READONLY) or ((st.st_mode & stat.S_IWRITE) == 0)
    return (stat.S_IMODE(st.st_mode) & 0o222) == 0


def _chmod_with_nt_retry(raw_path: str, mode: int) -> None:
    max_attempts = 6 if IS_WINDOWS else 1
    for attempt in range(max_attempts):
        try:
            os.chmod(raw_path, mode)
            return
        except PermissionError:
            if attempt + 1 >= max_attempts:
                raise
            time.sleep(0.01 * (attempt + 1))


@dataclass(frozen=True, slots=True)
class ReadonlySyncResult:
    """Summary of synchronizing OS readonly attributes across a set of protected HostPaths."""

    locked_count: int
    already_locked_count: int
    unlocked_count: int
    failed_paths: tuple[tuple[HostPath, str], ...] = ()

    def __post_init__(self) -> None:
        require_pure_int(self.locked_count, "ReadonlySyncResult.locked_count", min_val=0)
        require_pure_int(self.already_locked_count, "ReadonlySyncResult.already_locked_count", min_val=0)
        require_pure_int(self.unlocked_count, "ReadonlySyncResult.unlocked_count", min_val=0)
        object.__setattr__(self, "failed_paths", _validate_failed_path_pairs(self.failed_paths))


class ReadonlyPolicy:
    """Dual-layer readonly guard combining VFS path matching with OS readonly mode enforcement."""

    def __init__(self, matcher: Optional[Callable[[HostPath], bool]] = None) -> None:
        if matcher is not None and not callable(matcher):
            raise ValueError("ReadonlyPolicy matcher must be callable or None.")
        self._lock = threading.RLock()
        self._matcher: Optional[Callable[[HostPath], bool]] = matcher
        self._synced_protected: frozenset[HostPath] = frozenset()
        self._managed_locked: set[HostPath] = set()

    def update_matcher(self, matcher: Callable[[HostPath], bool]) -> None:
        if not callable(matcher):
            raise ValueError("ReadonlyPolicy.update_matcher requires a callable matcher.")
        with self._lock:
            self._matcher = matcher

    def is_protected(self, path: HostPath) -> bool:
        if not isinstance(path, HostPath):
            raise ValueError(f"ReadonlyPolicy.is_protected requires HostPath, got {path!r}")
        with self._lock:
            matcher = self._matcher
            synced = self._synced_protected
        if matcher is not None:
            return bool(matcher(path))
        return path in synced

    def is_os_readonly(self, path: HostPath) -> bool:
        if not isinstance(path, HostPath):
            raise ValueError(f"ReadonlyPolicy.is_os_readonly requires HostPath, got {path!r}")
        raw_p = str(path)
        if self._lock is None or has_symlink_raw_path(raw_p):
            return False
        try:
            st = os.lstat(raw_p)
        except OSError:
            return False
        return _is_stat_os_readonly(st)

    def lock_file(self, path: HostPath) -> bool:
        if not isinstance(path, HostPath):
            raise ValueError(f"ReadonlyPolicy.lock_file requires HostPath, got {path!r}")
        raw_p = str(path)
        if has_symlink_raw_path(raw_p):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing readonly lock across symlink path: {raw_p}")
        with self._lock:
            try:
                st = os.lstat(raw_p)
            except FileNotFoundError:
                return False
            if not stat.S_ISREG(st.st_mode):
                return False
            target_mode = stat.S_IREAD if IS_WINDOWS else 0o444
            _chmod_with_nt_retry(raw_p, target_mode)
            self._managed_locked.add(path)
            return True

    def unlock_file(self, path: HostPath) -> bool:
        if not isinstance(path, HostPath):
            raise ValueError(f"ReadonlyPolicy.unlock_file requires HostPath, got {path!r}")
        raw_p = str(path)
        if has_symlink_raw_path(raw_p):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing readonly unlock across symlink path: {raw_p}")
        with self._lock:
            try:
                st = os.lstat(raw_p)
            except FileNotFoundError:
                self._managed_locked.discard(path)
                return False
            if not stat.S_ISREG(st.st_mode):
                return False
            target_mode = (stat.S_IREAD | stat.S_IWRITE) if IS_WINDOWS else 0o644
            _chmod_with_nt_retry(raw_p, target_mode)
            self._managed_locked.discard(path)
            return True

    def sync_files(self, protected_paths: Sequence[HostPath]) -> ReadonlySyncResult:
        validated = require_typed_tuple(protected_paths, HostPath, "protected_paths")
        desired_order: list[HostPath] = []
        desired_set: set[HostPath] = set()
        for hp in validated:
            if hp not in desired_set:
                desired_set.add(hp)
                desired_order.append(hp)
        locked_count = 0
        already_locked_count = 0
        unlocked_count = 0
        failed: list[tuple[HostPath, str]] = []
        with self._lock:
            stale_paths = sorted(
                self._managed_locked - desired_set,
                key=lambda item: item.comparison_key,
            )
            self._synced_protected = frozenset(desired_set)
            for old_hp in stale_paths:
                try:
                    was_ro = self.is_os_readonly(old_hp)
                    if was_ro and self.unlock_file(old_hp):
                        unlocked_count += 1
                    else:
                        self._managed_locked.discard(old_hp)
                except (OSError, YscbError) as exc:
                    failed.append((old_hp, safe_exception_summary(exc)))
            for hp in desired_order:
                raw_p = str(hp)
                try:
                    if has_symlink_raw_path(raw_p):
                        raise YscbError(ErrorCode.ACCESS_DENIED, f"Symlink path rejected in sync_files: {raw_p}")
                    st = os.lstat(raw_p)
                    if not stat.S_ISREG(st.st_mode):
                        failed.append((hp, "Target path is not a regular file."))
                        continue
                    if _is_stat_os_readonly(st):
                        already_locked_count += 1
                        self._managed_locked.add(hp)
                    elif self.lock_file(hp):
                        locked_count += 1
                except (OSError, YscbError) as exc:
                    failed.append((hp, safe_exception_summary(exc)))
        return ReadonlySyncResult(
            locked_count=locked_count,
            already_locked_count=already_locked_count,
            unlocked_count=unlocked_count,
            failed_paths=tuple(failed),
        )

    @contextmanager
    def authorized_write_tunnel(self, path: HostPath) -> Iterator[None]:
        if not isinstance(path, HostPath):
            raise ValueError(f"authorized_write_tunnel requires HostPath, got {path!r}")
        raw_p = str(path)
        if has_symlink_raw_path(raw_p):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"Refusing write tunnel across symlink path: {raw_p}")
        with self._lock:
            was_os_ro = self.is_os_readonly(path)
            should_relock = was_os_ro or self.is_protected(path)
            if was_os_ro:
                self.unlock_file(path)
            try:
                yield
            finally:
                if should_relock and not has_symlink_raw_path(raw_p) and os.path.lexists(raw_p):
                    try:
                        self.lock_file(path)
                    except OSError:
                        if os.path.isfile(raw_p):
                            raise
