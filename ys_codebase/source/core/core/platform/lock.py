"""
Core Platform - Cross-Platform Inter-Process Lock.

Provides a robust, reentrant-safe, non-blocking file-based mutex across
Linux/POSIX (fcntl.flock) and Windows (msvcrt.locking).
"""

import os
import sys
import time
from typing import Optional


class LockAcquisitionError(Exception):
    """Raised when an inter-process lock cannot be acquired."""
    pass


class InterProcessLock:
    """
    Cross-platform inter-process file lock.

    Guarantees mutual exclusion between separate processes on both POSIX
    (via fcntl.flock) and Windows (via msvcrt.locking).
    """

    def __init__(self, lock_file: str) -> None:
        self.lock_file = os.path.abspath(lock_file)
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

        fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR)

        start_time = time.time()
        while True:
            if self._try_lock_fd(fd):
                self._fd = fd
                self._is_locked = True
                return True

            if not blocking:
                os.close(fd)
                return False

            if timeout_sec > 0 and (time.time() - start_time) >= timeout_sec:
                os.close(fd)
                return False

            time.sleep(0.05)

    def release(self) -> None:
        """Releases the lock and closes the underlying file descriptor."""
        if not self._is_locked or self._fd is None:
            return

        try:
            self._unlock_fd(self._fd)
        finally:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            self._is_locked = False

    def _try_lock_fd(self, fd: int) -> bool:
        if sys.platform == "win32":
            try:
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return True
            except (IOError, OSError):
                return False
        else:
            try:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (IOError, OSError):
                return False

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
        if not self.acquire(blocking=True):
            raise LockAcquisitionError(f"Could not acquire inter-process lock on {self.lock_file}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
