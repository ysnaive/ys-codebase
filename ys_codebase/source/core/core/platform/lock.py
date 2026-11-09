"""
Core Platform - Cross-Platform Inter-Process Lock.

Provides a robust, reentrant-safe, non-blocking file-based mutex across
Linux/POSIX (fcntl.flock) and Windows (msvcrt.locking), plus centralized
transaction lock probing (`is_transaction_locked`).
"""

import errno
import os
from pathlib import Path
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple, Union

from core.context import get_runtime_context

_EEXIST_RETRIES: int = 3
_STALE_PLAIN_LOCK_TTL_SEC: float = 30.0


def _norm_lock_key(lock_file: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.realpath(os.path.abspath(lock_file))))


def _get_held_locks_state() -> Tuple[threading.RLock, Dict[str, Tuple[int, int, int]]]:
    ctx = get_runtime_context()
    return ctx.interprocess_locks_lock, ctx.held_interprocess_locks


class LockAcquisitionError(Exception):
    """Raised when an inter-process lock cannot be acquired."""
    pass


class InterProcessLock:
    """
    Cross-platform inter-process file lock.

    Guarantees mutual exclusion between separate processes on both POSIX
    (via fcntl.flock) and Windows (via msvcrt.locking), and supports
    same-thread cross-instance reentrancy (`reentrant=True` or via `with` context manager)
    coordinated via `RuntimeContext.held_interprocess_locks`.
    """

    def __init__(
        self,
        lock_file: str,
        timeout: float = 0.0,
        reentrant: Optional[bool] = None,
    ) -> None:
        self.lock_file = os.path.abspath(lock_file)
        self.timeout = float(timeout)
        self.reentrant = reentrant
        self._fd: Optional[int] = None
        self._is_locked: bool = False
        self._shared_reentrant: bool = False
        self._locked_key: Optional[str] = None

    @property
    def is_locked(self) -> bool:
        return self._is_locked

    def _try_acquire_same_thread_reentrant(self, norm_key: str, allow_reentrant: bool) -> Optional[bool]:
        """
        Checks `RuntimeContext.held_interprocess_locks` for in-process lock ownership.
        Returns:
          - `True` if `allow_reentrant` is True and the current thread already holds `norm_key` (increments ref_count).
          - `False` if `norm_key` is currently held in-process and cannot be re-entered (`not allow_reentrant` or different thread).
          - `None` if `norm_key` is not currently held in-process (caller should proceed with OS lock acquisition).
        """
        table_lock, held_map = _get_held_locks_state()
        my_tid = threading.get_ident()
        with table_lock:
            entry = held_map.get(norm_key)
            if entry is None:
                return None
            owner_tid, ref_count, owner_fd = entry
            if allow_reentrant and owner_tid == my_tid:
                held_map[norm_key] = (owner_tid, ref_count + 1, owner_fd)
                self._is_locked = True
                self._shared_reentrant = True
                self._locked_key = norm_key
                return True
            return False

    def acquire(
        self,
        blocking: bool = False,
        timeout_sec: float = 0.0,
        reentrant: Optional[bool] = None,
    ) -> bool:
        """
        Attempts to acquire the lock.

        Args:
            blocking: If True, waits until the lock is acquired or timeout expires.
            timeout_sec: Maximum seconds to wait when blocking is True (0 = wait indefinitely).
            reentrant: Optional override for same-thread cross-instance reentrancy.

        Returns:
            bool: True if lock was acquired, False otherwise.
        """
        if self._is_locked:
            return True

        allow_reentrant = bool(self.reentrant) if reentrant is None else bool(reentrant)
        parent_dir = os.path.dirname(self.lock_file)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        norm_key = _norm_lock_key(self.lock_file)
        in_proc = self._try_acquire_same_thread_reentrant(norm_key, allow_reentrant)
        if in_proc is True:
            return True
        if in_proc is False and not blocking:
            return False

        fd = self._open_lock_fd()
        acquired = False
        try:
            start_time = time.time()
            while True:
                in_proc = self._try_acquire_same_thread_reentrant(norm_key, allow_reentrant)
                if in_proc is True:
                    return True
                if in_proc is None and self._try_lock_fd(fd):
                    if sys.platform != "win32":
                        try:
                            st_fd = os.fstat(fd)
                            st_path = os.stat(self.lock_file)
                            if (st_fd.st_dev, st_fd.st_ino) != (st_path.st_dev, st_path.st_ino):
                                self._unlock_fd(fd)
                                os.close(fd)
                                fd = self._open_lock_fd()
                                continue
                        except FileNotFoundError:
                            self._unlock_fd(fd)
                            os.close(fd)
                            fd = self._open_lock_fd()
                            continue
                    table_lock, held_map = _get_held_locks_state()
                    with table_lock:
                        if norm_key in held_map:
                            self._unlock_fd(fd)
                        else:
                            held_map[norm_key] = (threading.get_ident(), 1, fd)
                            self._fd = fd
                            self._is_locked = True
                            self._shared_reentrant = False
                            self._locked_key = norm_key
                            acquired = True
                            return True

                if not blocking:
                    return False

                if timeout_sec > 0 and (time.time() - start_time) >= timeout_sec:
                    return False

                time.sleep(0.05)
        finally:
            if not acquired:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def _open_lock_fd(self) -> int:
        """
        Opens (creating if needed) the lock file descriptor.

        Some filesystems (e.g. shared/9p mounts) transiently raise ``FileExistsError``
        for ``O_CREAT`` when another process races on creating the same file. Retries
        up to ``_EEXIST_RETRIES`` times (50ms apart) re-opening without ``O_CREAT``;
        re-raises the original ``FileExistsError`` if all retries fail. Other errors propagate.
        """
        try:
            fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR)
            os.set_inheritable(fd, False)
            return fd
        except FileExistsError as first_err:
            original = first_err
        for _ in range(_EEXIST_RETRIES):
            time.sleep(0.05)
            try:
                fd = os.open(self.lock_file, os.O_RDWR)
                os.set_inheritable(fd, False)
                return fd
            except FileExistsError:
                continue
        raise original

    def release(self) -> None:
        """Releases the lock and closes the underlying file descriptor when the reference count reaches zero."""
        if not self._is_locked:
            return

        norm_key = self._locked_key or _norm_lock_key(self.lock_file)
        table_lock, held_map = _get_held_locks_state()
        fd_to_close: Optional[int] = None
        with table_lock:
            entry = held_map.get(norm_key)
            if entry is not None:
                owner_tid, ref_count, owner_fd = entry
                if ref_count > 1:
                    held_map[norm_key] = (owner_tid, ref_count - 1, owner_fd)
                    self._fd = None
                    self._is_locked = False
                    self._shared_reentrant = False
                    self._locked_key = None
                    return
                held_map.pop(norm_key, None)
                fd_to_close = self._fd if self._fd is not None else owner_fd
            else:
                fd_to_close = self._fd

        self._fd = None
        self._is_locked = False
        self._shared_reentrant = False
        self._locked_key = None

        if fd_to_close is not None:
            try:
                self._unlock_fd(fd_to_close)
            finally:
                try:
                    os.close(fd_to_close)
                except OSError:
                    pass

    def _try_lock_fd(self, fd: int) -> bool:
        fatal_errnos = (
            getattr(errno, "ENOTSUP", -1),
            getattr(errno, "EOPNOTSUPP", -1),
            getattr(errno, "ENOSYS", -1),
            errno.EBADF,
            errno.EINVAL,
        )
        if sys.platform == "win32":
            try:
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return True
            except (IOError, OSError) as e:
                if e.errno in fatal_errnos:
                    raise
                win_err = getattr(e, "winerror", None)
                if e.errno in (errno.EACCES, errno.EAGAIN, getattr(errno, "EDEADLK", 36)) or win_err == 33:
                    return False
                if e.errno is not None:
                    raise
                return False
        else:
            posix_contention = {
                errno.EACCES,
                errno.EAGAIN,
                getattr(errno, "EWOULDBLOCK", errno.EAGAIN),
            }
            try:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (IOError, OSError) as e:
                if e.errno in fatal_errnos:
                    raise
                if e.errno in posix_contention:
                    return False
                raise

    def _unlock_fd(self, fd: int) -> None:
        if sys.platform == "win32":
            try:
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except (IOError, OSError):
                pass
        else:
            try:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
            except (IOError, OSError):
                pass

    def __enter__(self) -> "InterProcessLock":
        eff_reentrant = True if self.reentrant is None else bool(self.reentrant)
        if not self.acquire(blocking=True, timeout_sec=self.timeout, reentrant=eff_reentrant):
            raise LockAcquisitionError(f"Could not acquire inter-process lock on {self.lock_file}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass


def _probe_single_lock_file(lock_cand: Path, allow_plain_recent_file: bool = False) -> bool:
    """
    Probes whether `lock_cand` is actively held via `InterProcessLock` or (when
    `allow_plain_recent_file=True` for legacy test touch markers at `project_root/.yscb.lock`)
    was recently touched within `_STALE_PLAIN_LOCK_TTL_SEC`.
    """
    if not lock_cand.exists():
        return False
    norm_key = _norm_lock_key(str(lock_cand))
    table_lock, held_map = _get_held_locks_state()
    with table_lock:
        if norm_key in held_map:
            return True

    probe = InterProcessLock(str(lock_cand), reentrant=False)
    try:
        if not probe.acquire(blocking=False, reentrant=False):
            return True
    except Exception:
        return True
    finally:
        probe.release()

    if allow_plain_recent_file:
        try:
            mtime = lock_cand.stat().st_mtime
            if (time.time() - mtime) < _STALE_PLAIN_LOCK_TTL_SEC:
                return True
        except OSError:
            pass
    return False


def is_transaction_locked(
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    explicit_lock: Optional[Union[str, Path]] = None,
) -> bool:
    """
    Centralized check for whether a global `.yscb.lock` transaction lock is currently active
    across `explicit_lock`, `project_root/.yscb.lock`, `yscb_dir/.yscb.lock`, or `cache://.yscb.lock`.
    Deterministically releases all probe file descriptors in `finally` blocks.
    """
    if explicit_lock:
        exp_p = Path(str(explicit_lock))
        if _probe_single_lock_file(exp_p, allow_plain_recent_file=False):
            return True

    if project_root:
        p_root = Path(str(project_root))
        if _probe_single_lock_file(p_root / ".yscb.lock", allow_plain_recent_file=True):
            return True

    lock_candidates: List[Path] = []
    if yscb_dir:
        y_dir = Path(str(yscb_dir))
        lock_candidates.append(y_dir / ".yscb.lock")
        lock_candidates.append(y_dir / ".cache" / ".yscb.lock")

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
        if _probe_single_lock_file(lock_cand, allow_plain_recent_file=False):
            return True

    return False
