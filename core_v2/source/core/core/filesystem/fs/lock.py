"""Cross-process advisory FileLock and shared .lock/.owner.json/.pin lease primitives."""

from __future__ import annotations

from dataclasses import dataclass
import errno
from enum import Enum
import os
import stat
import threading
import time
import uuid
from typing import Callable, Optional

from core.filesystem.fs.atomic import (
    is_symlink_or_reparse,
    assert_no_symlink_raw_path,
    atomic_write_json,
    has_symlink_raw_path,
    read_json_dict,
    resolve_contained_subpath,
    silent_unlink,
)
from core.foundation.errors import ErrorCode, TaskCancelledException, YscbError, safe_exception_summary
from core.foundation.observability import (
    CancellationToken,
    require_non_negative_sec,
    validate_non_negative_sec,
)
from core.foundation.primitives import IS_WINDOWS, HostPath, JsonObject, require_non_none, require_pure_bool, require_pure_str
from core.foundation.proc import get_process_start_tag, is_process_alive

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    import msvcrt

    _K32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    _LOCKFILE_EXCLUSIVE_LOCK = 0x00000002
    _LOCKFILE_FAIL_IMMEDIATELY = 0x00000001
    _WIN_LOCK_EX = _K32.LockFileEx
    _WIN_LOCK_EX.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_Overlapped),
    ]
    _WIN_LOCK_EX.restype = wintypes.BOOL
    _WIN_UNLOCK_EX = _K32.UnlockFileEx
    _WIN_UNLOCK_EX.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_Overlapped),
    ]
    _WIN_UNLOCK_EX.restype = wintypes.BOOL
else:
    import fcntl

_LOCK_OPEN_FLAGS = os.O_CREAT | os.O_RDWR | (0 if IS_WINDOWS else os.O_NOFOLLOW)


def _map_lock_os_error(raw_path: str, exc: OSError) -> YscbError:
    if exc.errno == errno.ELOOP or is_symlink_or_reparse(raw_path):
        return YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink lock file: {raw_path}")
    return YscbError(
        ErrorCode.DAEMON_UNAVAILABLE,
        f"Filesystem lock I/O error on '{raw_path}': {safe_exception_summary(exc)}",
    )


def _open_nofollow_lock_fd(raw_path: str) -> int:
    assert_no_symlink_raw_path(raw_path)
    try:
        fd = os.open(raw_path, _LOCK_OPEN_FLAGS, 0o666)
    except OSError as exc:
        raise _map_lock_os_error(raw_path, exc) from exc
    try:
        f_st = os.fstat(fd)
        if not stat.S_ISREG(f_st.st_mode) or has_symlink_raw_path(raw_path):
            raise YscbError(
                ErrorCode.SECURITY_GATED if has_symlink_raw_path(raw_path) else ErrorCode.DAEMON_UNAVAILABLE,
                f"Lock target is not a regular non-symlink file: {raw_path}",
            )
        return fd
    except BaseException:
        _safe_close_fd(fd)
        raise


def _ensure_lock_parent_dir(lock_path: HostPath) -> None:
    raw_lock = str(lock_path)
    assert_no_symlink_raw_path(raw_lock)
    try:
        os.makedirs(str(lock_path.path.parent), exist_ok=True)
    except OSError as exc:
        raise _map_lock_os_error(raw_lock, exc) from exc
    assert_no_symlink_raw_path(raw_lock)


class _LockPhase(Enum):
    IDLE = "idle"
    ACQUIRING = "acquiring"
    HELD = "held"
    TRANSITIONING = "transitioning"
    RELEASING = "releasing"


def _try_os_lock(fd: int, *, shared: bool) -> bool:
    if IS_WINDOWS:
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(fd))
        flags = _LOCKFILE_FAIL_IMMEDIATELY | (0 if shared else _LOCKFILE_EXCLUSIVE_LOCK)
        ov = _Overlapped()
        return bool(_WIN_LOCK_EX(handle, flags, 0, 1, 0, ctypes.byref(ov)))
    mode = (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB
    try:
        fcntl.flock(fd, mode)
        return True
    except (BlockingIOError, PermissionError, OSError):
        return False


def _os_unlock(fd: int) -> None:
    if IS_WINDOWS:
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(fd))
        ov = _Overlapped()
        _WIN_UNLOCK_EX(handle, 0, 1, 0, ctypes.byref(ov))
    else:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


def _try_acquire_under_xchg_fd(fd: int, xchg_fd: Optional[int], *, shared: bool) -> bool:
    if xchg_fd is None:
        return _try_os_lock(fd, shared=shared)
    if not _try_os_lock(xchg_fd, shared=True):
        return False
    try:
        return _try_os_lock(fd, shared=shared)
    finally:
        _os_unlock(xchg_fd)


def _safe_close_fd(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


class _ExternalLockDisplacedError(Exception):
    """Raised when an external non-framework process displaces a shared flock during upgrade."""


class FileLock:
    """Process-safe advisory file lock supporting shared/exclusive modes, atomic transitions, and synchronous release."""

    def __init__(self, lock_path: HostPath, *, allow_transitions: bool = True) -> None:
        require_pure_bool(allow_transitions, "FileLock allow_transitions")
        self._lock_path = lock_path
        self._allow_transitions = allow_transitions
        self._guard = threading.Condition(threading.RLock())
        self._fd: Optional[int] = None
        self._held_shared: Optional[bool] = None
        self._phase: _LockPhase = _LockPhase.IDLE
        self._owner_tid: Optional[int] = None
        self._acquire_gen: int = 0
        self._release_cancel = CancellationToken()

    @property
    def lock_path(self) -> HostPath:
        return self._lock_path

    @property
    def is_acquired(self) -> bool:
        with self._guard:
            return self._fd is not None and self._phase in (_LockPhase.HELD, _LockPhase.TRANSITIONING)

    @property
    def is_shared(self) -> bool:
        with self._guard:
            return bool(self._fd is not None and self._held_shared is True)

    def _fd_matches_lock_inode(self, fd: int) -> bool:
        if IS_WINDOWS:
            return True
        try:
            f_st = os.fstat(fd)
            p_st = os.lstat(str(self._lock_path))
            return stat.S_ISREG(p_st.st_mode) and (f_st.st_dev, f_st.st_ino) == (p_st.st_dev, p_st.st_ino)
        except OSError:
            return False

    def _commit_acquired_fd(self, fd: int, *, shared: bool) -> None:
        aborted = False
        with self._guard:
            if self._phase == _LockPhase.RELEASING:
                aborted = True
            else:
                self._fd = fd
                self._held_shared = shared
                self._phase = _LockPhase.HELD
                self._owner_tid = None
                self._guard.notify_all()
        if aborted:
            _os_unlock(fd)
            raise TaskCancelledException(f"FileLock released during acquire: {self._lock_path}")

    def _wait_poll_slice(
        self,
        max_slice: float,
        deadline: Optional[float],
        cancel_token: Optional[CancellationToken] = None,
    ) -> None:
        rem = max_slice if deadline is None else min(max_slice, max(0.001, deadline - time.monotonic()))

        def _notify(_p: bool, _r: str) -> None:
            with self._guard:
                self._guard.notify_all()

        unreg = cancel_token.register_callback(_notify) if cancel_token is not None else None
        try:
            with self._guard:
                if self._phase == _LockPhase.RELEASING or (cancel_token is not None and cancel_token.is_cancelled):
                    return
                self._guard.wait(timeout=rem)
        finally:
            if unreg is not None:
                unreg()

    def acquire(
        self,
        *,
        shared: bool = False,
        blocking: bool = True,
        timeout_sec: Optional[float] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> bool:
        require_pure_bool(shared, "FileLock.acquire shared")
        require_pure_bool(blocking, "FileLock.acquire blocking")
        safe_timeout = validate_non_negative_sec(timeout_sec, label="FileLock timeout_sec")
        with self._guard:
            if self._phase != _LockPhase.IDLE or self._fd is not None:
                raise RuntimeError(f"FileLock already acquired or busy on this instance: {self._lock_path}")
            self._acquire_gen += 1
            self._phase = _LockPhase.ACQUIRING
            self._owner_tid = threading.get_ident()
            self._release_cancel = CancellationToken()

        fd: Optional[int] = None
        xchg_fd: Optional[int] = None
        try:
            _ensure_lock_parent_dir(self._lock_path)
            raw_path = str(self._lock_path)
            fd = _open_nofollow_lock_fd(raw_path)
            if self._allow_transitions and not raw_path.endswith((".xchg", ".upg")):
                xchg_fd = _open_nofollow_lock_fd(f"{raw_path}.xchg")
            deadline = (time.monotonic() + safe_timeout) if safe_timeout is not None else None
            while True:
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                with self._guard:
                    if self._phase == _LockPhase.RELEASING:
                        raise TaskCancelledException(f"FileLock aborted during acquire: {self._lock_path}")
                if _try_acquire_under_xchg_fd(fd, xchg_fd, shared=shared):
                    self._commit_acquired_fd(fd, shared=shared)
                    return True
                if not blocking:
                    _safe_close_fd(fd)
                    fd = None
                    with self._guard:
                        self._held_shared = None
                        self._phase = _LockPhase.IDLE
                        self._owner_tid = None
                        self._guard.notify_all()
                    return False
                if deadline is not None and time.monotonic() >= deadline:
                    raise YscbError(ErrorCode.TASK_TIMEOUT, f"Timed out waiting for file lock: {self._lock_path}")
                self._wait_poll_slice(0.01, deadline, cancel_token)
        except BaseException:
            if fd is not None:
                _safe_close_fd(fd)
            with self._guard:
                self._fd = None
                self._held_shared = None
                self._phase = _LockPhase.IDLE
                self._owner_tid = None
                self._guard.notify_all()
            raise
        finally:
            if xchg_fd is not None:
                _safe_close_fd(xchg_fd)

    def release(self) -> None:
        cur_tid = threading.get_ident()
        fd_to_close: Optional[int] = None
        rel_tok: Optional[CancellationToken] = None
        seen_gen = 0
        with self._guard:
            if self._phase == _LockPhase.IDLE:
                return
            seen_gen = self._acquire_gen
            if self._phase in (_LockPhase.ACQUIRING, _LockPhase.TRANSITIONING, _LockPhase.RELEASING):
                self._phase = _LockPhase.RELEASING
                rel_tok = self._release_cancel
                self._guard.notify_all()
            else:
                fd_to_close = self._fd
                self._fd = None
                self._held_shared = None
                self._phase = _LockPhase.RELEASING
                self._owner_tid = cur_tid
                self._guard.notify_all()
        if rel_tok is not None:
            rel_tok.cancel(reason=f"FileLock released: {self._lock_path}")
            with self._guard:
                while (
                    self._acquire_gen == seen_gen
                    and self._owner_tid != cur_tid
                    and self._phase != _LockPhase.IDLE
                ):
                    self._guard.wait(timeout=0.02)
            return
        try:
            if fd_to_close is not None:
                try:
                    _os_unlock(fd_to_close)
                finally:
                    _safe_close_fd(fd_to_close)
        finally:
            with self._guard:
                self._phase = _LockPhase.IDLE
                self._owner_tid = None
                self._guard.notify_all()

    def _begin_transition(self) -> Optional[int]:
        if not self._allow_transitions:
            raise RuntimeError(f"Lock transitions disabled on FileLock: {self._lock_path}")
        with self._guard:
            if self._phase != _LockPhase.HELD or self._fd is None:
                return None
            self._phase = _LockPhase.TRANSITIONING
            self._owner_tid = threading.get_ident()
            return self._fd

    def _poll_lock_mode(
        self,
        fd: int,
        *,
        shared: bool,
        deadline: Optional[float],
        cancel_token: Optional[CancellationToken],
        timeout_code: ErrorCode,
        timeout_msg: str,
    ) -> None:
        while True:
            with self._guard:
                if self._phase == _LockPhase.RELEASING:
                    raise TaskCancelledException(f"FileLock released during transition: {self._lock_path}")
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            if _try_os_lock(fd, shared=shared):
                return
            if deadline is not None and time.monotonic() >= deadline:
                raise YscbError(timeout_code, timeout_msg)
            self._wait_poll_slice(0.005, deadline, cancel_token)

    def _end_transition(self, fd: int, *, close_now: bool, raising: bool) -> None:
        was_released = False
        with self._guard:
            was_released = self._phase == _LockPhase.RELEASING
            if not (close_now or was_released):
                self._phase = _LockPhase.HELD
                self._owner_tid = None
                self._guard.notify_all()
                return
            self._fd = None
            self._held_shared = None
            self._phase = _LockPhase.RELEASING
        try:
            try:
                _os_unlock(fd)
            finally:
                _safe_close_fd(fd)
        finally:
            with self._guard:
                self._phase = _LockPhase.IDLE
                self._owner_tid = None
                self._guard.notify_all()
        if was_released and not raising:
            raise TaskCancelledException(f"FileLock released during transition: {self._lock_path}")

    def _try_restore_shared_after_failed_upgrade(
        self,
        fd: int,
        timeout_sec: Optional[float],
    ) -> bool:
        with self._guard:
            if self._phase == _LockPhase.RELEASING:
                return False
        if _try_os_lock(fd, shared=True):
            return True
        eff_tmo = 2.0 if timeout_sec is None else min(2.0, max(0.5, timeout_sec))
        try:
            restore_dl = time.monotonic() + eff_tmo
            self._poll_lock_mode(
                fd,
                shared=True,
                deadline=restore_dl,
                cancel_token=self._release_cancel,
                timeout_code=ErrorCode.TASK_TIMEOUT,
                timeout_msg="Timed out restoring shared file lock after failed upgrade.",
            )
            return True
        except Exception:
            return False

    def _acquire_transition_gate(
        self,
        timeout_sec: Optional[float],
        cancel_token: Optional[CancellationToken],
        timeout_code: ErrorCode,
    ) -> FileLock:
        xchg_raw = f"{self._lock_path}.xchg"
        if has_symlink_raw_path(xchg_raw) or has_symlink_raw_path(str(self._lock_path)):
            raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink lock transition gate: {xchg_raw}")
        merged_tok, detach_merged = CancellationToken.combine(self._release_cancel, cancel_token)
        gate = FileLock(HostPath(xchg_raw), allow_transitions=False)
        try:
            gate.acquire(shared=False, blocking=True, timeout_sec=timeout_sec, cancel_token=merged_tok)
        except TaskCancelledException as exc:
            if self._release_cancel.is_cancelled and (cancel_token is None or not cancel_token.is_cancelled):
                raise TaskCancelledException(f"FileLock released during transition: {self._lock_path}") from exc
            raise
        except YscbError as exc:
            if exc.detail.code == ErrorCode.TASK_TIMEOUT and timeout_code != ErrorCode.TASK_TIMEOUT:
                raise YscbError(
                    timeout_code,
                    f"Timed out waiting on lock transition gate: {self._lock_path}",
                ) from exc
            raise
        finally:
            detach_merged()
        return gate

    def _acquire_upgrade_reservation_gate(self) -> FileLock:
        upg_raw = f"{self._lock_path}.upg"
        if has_symlink_raw_path(upg_raw) or has_symlink_raw_path(str(self._lock_path)):
            raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink lock upgrade reservation: {upg_raw}")
        upg_gate = FileLock(HostPath(upg_raw), allow_transitions=False)
        if not upg_gate.acquire(shared=False, blocking=False):
            raise YscbError(
                ErrorCode.ILLEGAL_LOCK_REENTRANCY,
                f"Concurrent shared-to-exclusive lock upgrade deadlock detected on: {self._lock_path}",
            )
        return upg_gate

    def _poll_posix_upgrade_preserving_shared(
        self,
        fd: int,
        deadline: Optional[float],
        cancel_token: Optional[CancellationToken],
        shared_at_risk: list[bool],
    ) -> None:
        while True:
            with self._guard:
                if self._phase == _LockPhase.RELEASING:
                    raise TaskCancelledException(f"FileLock released during transition: {self._lock_path}")
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            shared_at_risk[0] = True
            if _try_os_lock(fd, shared=False):
                shared_at_risk[0] = False
                return
            if not _try_os_lock(fd, shared=True):
                raise _ExternalLockDisplacedError()
            shared_at_risk[0] = False
            if deadline is not None and time.monotonic() >= deadline:
                raise YscbError(
                    ErrorCode.TASK_TIMEOUT,
                    f"Timed out upgrading shared lock to exclusive: {self._lock_path}",
                )
            self._wait_poll_slice(0.005, deadline, cancel_token)

    def upgrade_to_exclusive(
        self,
        *,
        timeout_sec: Optional[float] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> None:
        safe_timeout = validate_non_negative_sec(timeout_sec, label="FileLock transition timeout_sec")
        fd = self._begin_transition()
        if fd is None:
            raise RuntimeError(f"FileLock not currently held for upgrade: {self._lock_path}")
        deadline = (time.monotonic() + safe_timeout) if safe_timeout is not None else None
        failed_unrestored = False
        unlocked_win32 = False
        posix_shared_at_risk = [False]
        raising = False
        upg_gate: Optional[FileLock] = None
        xchg_gate: Optional[FileLock] = None
        try:
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            if self._held_shared is False:
                return
            upg_gate = self._acquire_upgrade_reservation_gate()
            rem_gate = None if deadline is None else max(0.0, deadline - time.monotonic())
            xchg_gate = self._acquire_transition_gate(rem_gate, cancel_token, ErrorCode.TASK_TIMEOUT)
            if IS_WINDOWS:
                _os_unlock(fd)
                unlocked_win32 = True
                self._poll_lock_mode(
                    fd,
                    shared=False,
                    deadline=deadline,
                    cancel_token=cancel_token,
                    timeout_code=ErrorCode.TASK_TIMEOUT,
                    timeout_msg=f"Timed out upgrading shared lock to exclusive: {self._lock_path}",
                )
            else:
                self._poll_posix_upgrade_preserving_shared(fd, deadline, cancel_token, posix_shared_at_risk)
            with self._guard:
                self._held_shared = False
        except _ExternalLockDisplacedError as exc:
            raising = True
            failed_unrestored = True
            raise YscbError(
                ErrorCode.DAEMON_UNAVAILABLE,
                f"Shared lock displaced by external exclusive writer during upgrade: {self._lock_path}",
            ) from exc
        except BaseException:
            raising = True
            if unlocked_win32 or posix_shared_at_risk[0]:
                failed_unrestored = not self._try_restore_shared_after_failed_upgrade(fd, safe_timeout)
            else:
                failed_unrestored = not self._fd_matches_lock_inode(fd)
            raise
        finally:
            if xchg_gate is not None:
                xchg_gate.release()
            if upg_gate is not None:
                upg_gate.release()
            self._end_transition(fd, close_now=failed_unrestored, raising=raising)

    def downgrade_to_shared(
        self,
        *,
        timeout_sec: float = 10.0,
        cancel_token: Optional[CancellationToken] = None,
    ) -> None:
        assert_t = require_non_negative_sec(timeout_sec, label="FileLock downgrade timeout_sec")
        fd = self._begin_transition()
        if fd is None:
            raise RuntimeError(f"FileLock not currently held for downgrade: {self._lock_path}")
        deadline = time.monotonic() + assert_t
        failed_close = False
        unlocked_for_downgrade = False
        raising = False
        xchg_gate: Optional[FileLock] = None
        try:
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            if self._held_shared is True:
                return
            acquired_fast = False
            if IS_WINDOWS:
                rem_gate = max(0.0, deadline - time.monotonic())
                xchg_gate = self._acquire_transition_gate(rem_gate, cancel_token, ErrorCode.TASK_TIMEOUT)
                _os_unlock(fd)
                unlocked_for_downgrade = True
                if _try_os_lock(fd, shared=True):
                    unlocked_for_downgrade = False
                    acquired_fast = True
            if not acquired_fast:
                self._poll_lock_mode(
                    fd,
                    shared=True,
                    deadline=deadline,
                    cancel_token=cancel_token,
                    timeout_code=ErrorCode.TASK_TIMEOUT,
                    timeout_msg=f"Timed out downgrading exclusive lock to shared: {self._lock_path}",
                )
                unlocked_for_downgrade = False
            with self._guard:
                self._held_shared = True
        except BaseException:
            raising = True
            failed_close = unlocked_for_downgrade or not self._fd_matches_lock_inode(fd)
            raise
        finally:
            if xchg_gate is not None:
                xchg_gate.release()
            self._end_transition(fd, close_now=failed_close, raising=raising)

    def __enter__(self) -> FileLock:
        self.acquire(blocking=True)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _ = (exc_type, exc, tb)
        self.release()


@dataclass(frozen=True, slots=True)
class CrossProcessLockPaths:
    """Uniform (<stem>.lock, <stem>.owner.json, <stem>.pin) bundle under a contained locks directory."""

    lock_file: FileLock
    owner_path: HostPath
    pin_path: HostPath

    @classmethod
    def for_stem(
        cls,
        locks_dir: HostPath,
        stem: str,
        *,
        allow_transitions: bool = True,
    ) -> CrossProcessLockPaths:
        require_pure_str(stem, "lock stem", non_empty=True)
        return cls(
            lock_file=FileLock(
                resolve_contained_subpath(locks_dir, f"{stem}.lock"),
                allow_transitions=allow_transitions,
            ),
            owner_path=resolve_contained_subpath(locks_dir, f"{stem}.owner.json"),
            pin_path=resolve_contained_subpath(locks_dir, f"{stem}.pin"),
        )


def read_live_owner_dict(owner_path: HostPath) -> Optional[JsonObject]:
    """Read cross-process lock owner metadata returning None when absent, malformed, dead, or PID-reused."""
    doc = read_json_dict(owner_path)
    if doc is None:
        return None
    pid_raw = doc.get("pid")
    if type(pid_raw) is not int or pid_raw <= 0 or not is_process_alive(pid_raw):
        return None
    rec_tag = doc.get("start_tag")
    if type(rec_tag) is str and rec_tag:
        live_tag = get_process_start_tag(pid_raw)
        if live_tag is not None and live_tag != rec_tag:
            return None
    return doc


def write_cross_proc_owner_json(owner_path: HostPath, payload: JsonObject) -> None:
    """Atomically publish cross-process owner metadata (enriched with PID start_tag and unique lease_nonce)."""
    enriched = dict(payload)
    enriched.setdefault("lease_nonce", uuid.uuid4().hex)
    pid_raw = enriched.get("pid")
    if type(pid_raw) is int and pid_raw > 0 and "start_tag" not in enriched:
        st_tag = get_process_start_tag(pid_raw)
        if st_tag is not None:
            enriched["start_tag"] = st_tag
    try:
        atomic_write_json(owner_path, enriched)
    except OSError as exc:
        raise _map_lock_os_error(str(owner_path), exc) from exc


def acquire_verified_cross_proc_pin(
    owner_path: HostPath,
    pin_path: HostPath,
    owner_pred: Callable[[HostPath], bool],
    *,
    timeout_sec: float,
    cancel_token: CancellationToken,
) -> Optional[FileLock]:
    """Double-check ``owner_pred`` before and after pinning ``pin_path`` with a shared FileLock."""
    if not owner_pred(owner_path):
        return None
    pin_lk = FileLock(pin_path, allow_transitions=False)
    pin_lk.acquire(shared=True, blocking=True, timeout_sec=timeout_sec, cancel_token=cancel_token)
    try:
        if owner_pred(owner_path):
            return pin_lk
    except BaseException:
        pin_lk.release()
        raise
    pin_lk.release()
    return None


def _spawn_deferred_owner_unlink(owner_path: HostPath, pin_path: HostPath, expected_doc: JsonObject) -> None:
    def _reap_when_unpinned() -> None:
        reap_gate = FileLock(pin_path, allow_transitions=False)
        acquired = False
        try:
            acquired = reap_gate.acquire(shared=False, blocking=True, timeout_sec=30.0)
            if acquired and read_json_dict(owner_path) == expected_doc:
                silent_unlink(owner_path)
        except YscbError:
            return
        finally:
            if acquired:
                reap_gate.release()

    try:
        threading.Thread(target=_reap_when_unpinned, name="yscb-owner-pin-reap", daemon=True).start()
    except RuntimeError:
        return


def unlink_owner_under_pin(
    owner_path: HostPath,
    pin_path: HostPath,
    after_unlink: Callable[[], None],
    *,
    grace_timeout_sec: float = 5.0,
) -> None:
    """Acquire exclusive ``pin_path`` within ``grace_timeout_sec``, unlink ``owner_path`` safely, then release."""
    safe_grace = max(0.05, require_non_none(validate_non_negative_sec(grace_timeout_sec, label="grace_timeout_sec")))
    pin_gate = FileLock(pin_path, allow_transitions=False)
    pin_acquired = False
    try:
        try:
            pin_acquired = pin_gate.acquire(shared=False, blocking=True, timeout_sec=safe_grace)
        except YscbError:
            pin_acquired = False
        if pin_acquired:
            silent_unlink(owner_path)
        else:
            snap_doc = read_json_dict(owner_path)
            if snap_doc is not None:
                _spawn_deferred_owner_unlink(owner_path, pin_path, snap_doc)
    finally:
        try:
            after_unlink()
        finally:
            if pin_acquired:
                pin_gate.release()


def try_acquire_contained_lock(
    root: HostPath,
    *parts: str,
    shared: bool = True,
    timeout_sec: Optional[float] = None,
    cancel_token: Optional[CancellationToken] = None,
) -> Optional[FileLock]:
    """Resolve ``root/parts`` without symlinks and attempt to acquire a ``FileLock``, returning ``None`` on contention or error."""
    try:
        lock = FileLock(resolve_contained_subpath(root, *parts))
        acquired = (
            lock.acquire(shared=shared, blocking=False)
            if timeout_sec is None
            else lock.acquire(shared=shared, blocking=True, timeout_sec=timeout_sec, cancel_token=cancel_token)
        )
        return lock if acquired else None
    except (OSError, ValueError, TaskCancelledException, YscbError):
        return None
