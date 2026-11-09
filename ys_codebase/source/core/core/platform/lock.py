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
import time
from typing import List, Optional, Union

_EEXIST_RETRIES: int = 3
_STALE_PLAIN_LOCK_TTL_SEC: float = 30.0


class LockAcquisitionError(Exception):
    """Raised when an inter-process lock cannot be acquired."""
    pass


class InterProcessLock:
    """
    Cross-platform inter-process file lock.

    Guarantees mutual exclusion between separate processes on both POSIX
    (via fcntl.flock) and Windows (via msvcrt.locking).
    """

    def __init__(self, lock_file: str, timeout: float = 0.0) -> None:
        self.lock_file = os.path.abspath(lock_file)
        self.timeout = float(timeout)
        self._fd: Optional[int] = None
        self._is_locked: bool = False

    @property
    def is_locked(self) -> bool:
        return self._is_locked

    def acquire(self, blocking: bool = False, timeout_sec: float = 0.0) -> bool:
        """
        Attempts to acquire the lock.

        Args:
            blocking: If True, waits until the lock is acquired or timeout expires.
            timeout_sec: Maximum seconds to wait when blocking is True (0 = wait indefinitely).

        Returns:
            bool: True if lock was acquired, False otherwise.
        """
        if self._is_locked:
            return True

        parent_dir = os.path.dirname(self.lock_file)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        fd = self._open_lock_fd()
        acquired = False
        try:
            start_time = time.time()
            while True:
                if self._try_lock_fd(fd):
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
                    self._fd = fd
                    self._is_locked = True
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
        """Releases the lock and closes the underlying file descriptor."""
        if not self._is_locked or self._fd is None:
            return

        fd_to_close = self._fd
        try:
            self._unlock_fd(fd_to_close)
        finally:
            try:
                os.close(fd_to_close)
            except OSError:
                pass
            self._fd = None
            self._is_locked = False

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
        if not self.acquire(blocking=True, timeout_sec=self.timeout):
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
    probe = InterProcessLock(str(lock_cand))
    try:
        if not probe.acquire(blocking=False):
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
