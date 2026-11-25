"""Cooperative cancellation, deadline guards, structured logging, cross-process rotation, and locale catalog."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
import errno
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import threading
import time
from types import MappingProxyType
from typing import (
    BinaryIO,
    Callable,
    ClassVar,
    Final,
    Iterable,
    Iterator,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    TextIO,
)

from core.foundation.errors import ErrorCode, TaskCancelledException, YscbError, sanitize_utf8_text
from core.foundation.primitives import (
    INT64_MAX,
    INT64_MIN,
    IS_WINDOWS,
    MAX_SAFE_WAIT_SEC,
    HostPath,
    JsonObject,
    ModuleId,
    MutableJsonObject,
    clamp_wait_sec,
    clone_strict_json_object,
    is_disallowed_reparse_tag,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    require_typed_tuple,
    safe_real_to_float,
    strict_parse_json_object,
    validate_min_sec,
)

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    import msvcrt

    _OBS_K32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _ObsOverlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    _OBS_LOCKFILE_EXCLUSIVE_LOCK: Final[int] = 0x00000002
    _OBS_WIN_LOCK_EX = _OBS_K32.LockFileEx
    _OBS_WIN_LOCK_EX.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_ObsOverlapped),
    ]
    _OBS_WIN_LOCK_EX.restype = wintypes.BOOL
    _OBS_WIN_UNLOCK_EX = _OBS_K32.UnlockFileEx
    _OBS_WIN_UNLOCK_EX.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_ObsOverlapped),
    ]
    _OBS_WIN_UNLOCK_EX.restype = wintypes.BOOL
else:
    import fcntl

MAX_LOCALE_INTERPOLATION_DEPTH: Final[int] = 5
_LOCALE_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\{\{|\}\}|\{([a-zA-Z0-9_.:-]+)\}")
_ROT_TMP_INFIX: Final[str] = ".rot_tmp_"


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Structured progress frame payload."""

    phase: str
    completed: int
    total: int
    message: str = ""

    def __post_init__(self) -> None:
        require_pure_str(self.phase, "ProgressEvent.phase")
        require_pure_str(self.message, "ProgressEvent.message")
        require_pure_int(self.completed, "ProgressEvent.completed", min_val=INT64_MIN, max_val=INT64_MAX)
        require_pure_int(self.total, "ProgressEvent.total", min_val=INT64_MIN, max_val=INT64_MAX)


class CancellationToken:
    """Thread-safe cooperative cancellation token supporting detachable callbacks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._preempted = False
        self._reason = ""
        self._callbacks: dict[int, Callable[[bool, str], None]] = {}
        self._next_id = 0

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def is_preempted(self) -> bool:
        with self._lock:
            return self._preempted

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    def cancel_deferred(
        self,
        *,
        preempted: bool = False,
        reason: str = "cancelled",
    ) -> tuple[Callable[[], None], ...]:
        require_pure_bool(preempted, "CancellationToken.preempted")
        require_pure_str(reason, "CancellationToken.reason")
        with self._lock:
            if self._event.is_set():
                return ()
            self._preempted = preempted
            self._reason = reason
            self._event.set()
            callbacks = tuple(self._callbacks.values())
            self._callbacks.clear()
        return tuple((lambda fn=cb: fn(preempted, reason)) for cb in callbacks)

    @staticmethod
    def run_callbacks(thunks: Sequence[Callable[[], None]]) -> None:
        """Execute deferred cancellation callbacks isolating Exception/SystemExit/GeneratorExit."""
        deferred_base: Optional[BaseException] = None
        for thunk in thunks:
            try:
                thunk()
            except (Exception, SystemExit, GeneratorExit):
                pass
            except BaseException as base_exc:
                if deferred_base is None:
                    deferred_base = base_exc
        if deferred_base is not None:
            raise deferred_base

    def cancel(self, *, preempted: bool = False, reason: str = "cancelled") -> None:
        CancellationToken.run_callbacks(self.cancel_deferred(preempted=preempted, reason=reason))

    def register_callback(self, fn: Callable[[bool, str], None]) -> Callable[[], None]:
        call_now = False
        preempted = False
        reason = ""
        cb_id = -1
        with self._lock:
            if self._event.is_set():
                call_now = True
                preempted = self._preempted
                reason = self._reason
            else:
                cb_id = self._next_id
                self._next_id += 1
                self._callbacks[cb_id] = fn
        if call_now:
            try:
                fn(preempted, reason)
            except (Exception, SystemExit, GeneratorExit):
                pass
            return lambda: None

        def _unregister() -> None:
            with self._lock:
                self._callbacks.pop(cb_id, None)

        return _unregister

    def wait(self, timeout_sec: Optional[float] = None) -> bool:
        return self._event.wait(clamp_wait_sec(timeout_sec))

    @staticmethod
    def combine(*tokens: Optional[CancellationToken]) -> tuple[CancellationToken, Callable[[], None]]:
        merged = CancellationToken()
        active = [t for t in tokens if t is not None]
        if not active:
            return (merged, lambda: None)
        unregs = [
            tok.register_callback(lambda p, r, m=merged: m.cancel(preempted=p, reason=r))
            for tok in active
        ]

        def _detach_all() -> None:
            for u in unregs:
                u()

        return (merged, _detach_all)

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            with self._lock:
                preempted = self._preempted
                reason = self._reason
            raise TaskCancelledException(reason or "Task cancelled", preempted=preempted)


MAX_TIMEOUT_MS: Final[int] = int(MAX_SAFE_WAIT_SEC * 1000.0)


def validate_non_negative_sec(timeout_sec: Optional[float], *, label: str = "timeout_sec") -> Optional[float]:
    """Validate finite non-negative seconds (rejecting bool, NaN, inf, and < 0) clamped to MAX_SAFE_WAIT_SEC."""
    if timeout_sec is None:
        return None
    f_val = safe_real_to_float(timeout_sec, label=label)
    if not math.isfinite(f_val) or f_val < 0.0:
        raise ValueError(f"{label} must be finite and >= 0, got {timeout_sec!r}")
    return min(MAX_SAFE_WAIT_SEC, f_val)


def clamp_positive_sec(
    val: object,
    *,
    min_sec: float,
    max_sec: float,
    default_sec: Optional[float] = None,
    label: str = "seconds",
) -> float:
    """Validate or fallback a positive seconds value and clamp within [min_sec, max_sec]."""
    f_min = safe_real_to_float(min_sec, label="min_sec")
    f_max = safe_real_to_float(max_sec, label="max_sec")
    if not math.isfinite(f_min) or f_min <= 0.0:
        raise ValueError(f"min_sec must be finite and > 0, got {min_sec!r}")
    if not math.isfinite(f_max) or f_max < f_min:
        raise ValueError(f"max_sec must be finite and >= min_sec ({f_min}), got {max_sec!r}")
    eff_min = min(MAX_SAFE_WAIT_SEC, f_min)
    eff_max = min(MAX_SAFE_WAIT_SEC, f_max)
    f_default: Optional[float] = None
    if default_sec is not None:
        raw_def = safe_real_to_float(default_sec, label="default_sec")
        if not math.isfinite(raw_def) or raw_def <= 0.0:
            raise ValueError(f"default_sec must be finite and > 0, got {default_sec!r}")
        f_default = min(eff_max, max(eff_min, raw_def))
    if f_default is not None:
        try:
            f_val = safe_real_to_float(val, label=label)
        except ValueError:
            return f_default
        if math.isnan(f_val) or f_val <= 0.0:
            return f_default
        return min(eff_max, max(eff_min, f_val))
    f_strict = safe_real_to_float(val, label=label)
    if math.isnan(f_strict) or f_strict <= 0.0:
        raise ValueError(f"{label} must be > 0 (not bool or NaN), got {val!r}")
    return min(eff_max, max(eff_min, f_strict))


def ms_to_safe_sec(ms: int, *, min_sec: float = 0.0) -> float:
    """Convert integer milliseconds to safe monotonic seconds clamped within [min_sec, MAX_SAFE_WAIT_SEC]."""
    safe_min = validate_min_sec(min_sec)
    if type(ms) is not int:
        raise ValueError(f"Duration in ms must be an int (not bool), got {ms!r}")
    clamped_ms = min(max(0, ms), MAX_TIMEOUT_MS)
    return min(MAX_SAFE_WAIT_SEC, max(safe_min, clamped_ms / 1000.0))


@dataclass(frozen=True, slots=True)
class DeadlineGuard:
    """Monotonic deadline and cancellation budget shared across gates, locks, and RPC calls."""

    cancel_token: Optional[CancellationToken] = None
    deadline: Optional[float] = None

    def __post_init__(self) -> None:
        if self.deadline is not None:
            f_dl = safe_real_to_float(self.deadline, label="deadline")
            if math.isnan(f_dl):
                raise ValueError(f"Deadline must not be bool or NaN: {self.deadline!r}")
            max_dl = time.monotonic() + MAX_SAFE_WAIT_SEC
            object.__setattr__(self, "deadline", min(f_dl, max_dl))

    @staticmethod
    def from_timeout_ms(
        timeout_ms: Optional[int],
        cancel_token: Optional[CancellationToken] = None,
    ) -> DeadlineGuard:
        if timeout_ms is None:
            return DeadlineGuard(cancel_token=cancel_token, deadline=None)
        if type(timeout_ms) is not int or timeout_ms < 0:
            raise ValueError(f"timeout_ms must be a non-negative int, got {timeout_ms!r}")
        return DeadlineGuard(
            cancel_token=cancel_token,
            deadline=time.monotonic() + ms_to_safe_sec(timeout_ms),
        )

    def remaining_ms(
        self,
        default_ms: Optional[int] = None,
        *,
        expired_message: str = "Operation timed out.",
    ) -> Optional[int]:
        if default_ms is not None:
            if type(default_ms) is not int or default_ms < 0:
                raise ValueError(f"default_ms must be a non-negative int, got {default_ms!r}")
            if default_ms == 0:
                raise YscbError(ErrorCode.TASK_TIMEOUT, expired_message)
        safe_default = min(default_ms, MAX_TIMEOUT_MS) if default_ms is not None else None
        if self.deadline is None:
            return safe_default
        rem_sec = self.deadline - time.monotonic()
        if rem_sec <= 0:
            raise YscbError(ErrorCode.TASK_TIMEOUT, expired_message)
        computed = min(MAX_TIMEOUT_MS, max(1, int(rem_sec * 1000)))
        return min(safe_default, computed) if safe_default is not None else computed


class _CaptureBufferStackLocal(threading.local):
    """Strongly typed thread-local capture buffer stack (None marks TTY pass-through)."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[Optional[io.StringIO]] = []


def require_non_negative_sec(timeout_sec: float, *, label: str = "timeout_sec") -> float:
    """Validate a required non-negative finite timeout in seconds."""
    if timeout_sec is None:
        raise ValueError(f"{label} must not be None")
    validated = validate_non_negative_sec(timeout_sec, label=label)
    if validated is None:
        raise ValueError(f"{label} must not be None")
    return validated


def _unwrap_proxy_chain(stream: Optional[TextIO]) -> Optional[TextIO]:
    cur = stream
    while isinstance(cur, _ThreadLocalStdoutProxy):
        cur = cur.fallback_stream
    return cur


@dataclass(slots=True)
class _StdoutProxyState:
    _INSTANCE: ClassVar[Optional[_StdoutProxyState]] = None
    _INIT_LOCK: ClassVar[threading.Lock] = threading.Lock()

    install_lock: threading.RLock
    capture_local: _CaptureBufferStackLocal
    total_active_guards: int = 0

    @classmethod
    def instance(cls) -> _StdoutProxyState:
        inst = cls._INSTANCE
        if inst is not None:
            return inst
        with cls._INIT_LOCK:
            if cls._INSTANCE is None:
                cls._INSTANCE = cls(threading.RLock(), _CaptureBufferStackLocal(), 0)
            return cls._INSTANCE


class _ThreadLocalStdoutProxy(io.TextIOBase):
    """TextIOBase-compliant thread-local stdout proxy isolating active task threads."""

    def __init__(self, fallback: Optional[TextIO]) -> None:
        super().__init__()
        self._fallback: Optional[TextIO] = fallback
        self._fallback_encoding = (
            fallback.encoding if (fallback is not None and isinstance(fallback.encoding, str)) else "utf-8"
        )

    @property
    def fallback_stream(self) -> Optional[TextIO]:
        return self._fallback

    def _fallback_detached(self) -> Optional[TextIO]:
        st = _StdoutProxyState.instance()
        if st.total_active_guards == 0 and isinstance(sys.stdout, _ThreadLocalStdoutProxy):
            with st.install_lock:
                if st.total_active_guards == 0 and isinstance(sys.stdout, _ThreadLocalStdoutProxy):
                    sys.stdout = _unwrap_proxy_chain(sys.stdout)
        return self._fallback

    def _target(self) -> Optional[TextIO | io.StringIO]:
        fb = self._fallback_detached()
        st = _StdoutProxyState.instance()
        if st.total_active_guards == 0:
            return fb
        cap = st.capture_local.stack[-1] if st.capture_local.stack else None
        return cap if cap is not None else fb

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    @property
    def closed(self) -> bool:
        target = self._target()
        return bool(target.closed) if target is not None else False

    @property
    def errors(self) -> Optional[str]:
        fb = self._fallback_detached()
        return fb.errors if fb is not None else "strict"

    def write(self, s: str) -> int:
        target = self._target()
        if target is not None:
            return target.write(s)
        if not isinstance(s, str):
            raise TypeError(f"write() argument must be str, not {type(s).__name__}")
        return len(s)

    def writelines(self, lines: Iterable[str]) -> None:
        target = self._target()
        if target is not None:
            target.writelines(lines)
            return
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        target = self._target()
        if target is not None:
            target.flush()

    def isatty(self) -> bool:
        fb = self._fallback_detached()
        cap = (
            _StdoutProxyState.instance().capture_local.stack[-1]
            if (
                _StdoutProxyState.instance().total_active_guards > 0
                and _StdoutProxyState.instance().capture_local.stack
            )
            else None
        )
        return bool(fb.isatty()) if (cap is None and fb is not None) else False

    def fileno(self) -> int:
        fb = self._fallback_detached()
        cap = (
            _StdoutProxyState.instance().capture_local.stack[-1]
            if (
                _StdoutProxyState.instance().total_active_guards > 0
                and _StdoutProxyState.instance().capture_local.stack
            )
            else None
        )
        if cap is not None or fb is None:
            raise io.UnsupportedOperation("Captured task stdout does not expose raw OS fileno")
        return fb.fileno()

    @property
    def buffer(self) -> BinaryIO:
        fb = self._fallback_detached()
        cap = (
            _StdoutProxyState.instance().capture_local.stack[-1]
            if (
                _StdoutProxyState.instance().total_active_guards > 0
                and _StdoutProxyState.instance().capture_local.stack
            )
            else None
        )
        if cap is not None or fb is None:
            raise io.UnsupportedOperation("Captured task stdout does not expose binary buffer")
        return fb.buffer

    @property
    def encoding(self) -> str:
        _ = self._fallback_detached()
        return self._fallback_encoding

    @classmethod
    def enter_guard(cls, frame_buf: Optional[io.StringIO]) -> Optional[_ThreadLocalStdoutProxy]:
        st = _StdoutProxyState.instance()
        with st.install_lock:
            cur = sys.stdout
            if frame_buf is None and not isinstance(cur, _ThreadLocalStdoutProxy):
                return None
            if isinstance(cur, _ThreadLocalStdoutProxy) and st.total_active_guards > 0:
                proxy = cur
            else:
                proxy = cls(_unwrap_proxy_chain(cur))
                sys.stdout = proxy
            st.total_active_guards += 1
            st.capture_local.stack.append(frame_buf)
            return proxy

    @staticmethod
    def leave_guard() -> None:
        st = _StdoutProxyState.instance()
        with st.install_lock:
            if st.capture_local.stack:
                st.capture_local.stack.pop()
            st.total_active_guards = max(0, st.total_active_guards - 1)
            if st.total_active_guards == 0 and isinstance(sys.stdout, _ThreadLocalStdoutProxy):
                sys.stdout = _unwrap_proxy_chain(sys.stdout)


@contextmanager
def guard_standard_streams(*, allow_interactive_tty: bool = False) -> Iterator[io.StringIO]:
    """Intercept stray stdout writes on the current thread only, restoring sys.stdout when idle."""
    require_pure_bool(allow_interactive_tty, "allow_interactive_tty")
    captured = io.StringIO()
    proxy = _ThreadLocalStdoutProxy.enter_guard(None if allow_interactive_tty else captured)
    try:
        yield captured
    finally:
        if proxy is not None:
            _ThreadLocalStdoutProxy.leave_guard()


class LogLevel(Enum):
    """Canonical structured log severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LogRecord:
    """Immutable structured log record with optional distributed correlation fields."""

    ts_utc: str
    level: LogLevel
    logger_name: str
    message: str
    fields: JsonObject = field(default_factory=dict)
    trace_id: str = ""
    span_id: str = ""
    task_id: str = ""
    exec_mode: str = ""
    daemon_boot_id: str = ""
    pid: int = 0

    def __post_init__(self) -> None:
        require_pure_str(self.ts_utc, "LogRecord.ts_utc", non_empty=True)
        if not isinstance(self.level, LogLevel):
            raise ValueError(f"LogRecord.level must be LogLevel, got {self.level!r}")
        require_pure_str(self.logger_name, "LogRecord.logger_name", non_empty=True)
        require_pure_str(self.message, "LogRecord.message")
        cloned_fields = clone_strict_json_object(self.fields, label="LogRecord.fields")
        object.__setattr__(self, "fields", MappingProxyType(cloned_fields))
        require_pure_str(self.trace_id, "LogRecord.trace_id")
        require_pure_str(self.span_id, "LogRecord.span_id")
        require_pure_str(self.task_id, "LogRecord.task_id")
        require_pure_str(self.exec_mode, "LogRecord.exec_mode")
        require_pure_str(self.daemon_boot_id, "LogRecord.daemon_boot_id")
        require_pure_int(self.pid, "LogRecord.pid", min_val=0, max_val=INT64_MAX)


def _write_all_fd(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    written = 0
    total = len(view)
    while written < total:
        n_bytes = os.write(fd, view[written:])
        if n_bytes <= 0:
            raise OSError("Short or zero write on log file descriptor.")
        written += n_bytes


_OBS_POSIX_SYS_ROOT_LINKS: Final[frozenset[str]] = frozenset({"tmp", "var", "etc", "run"})


def _obs_is_allowed_posix_root_link(anc: Path, st: os.stat_result) -> bool:
    if IS_WINDOWS or anc.parent != Path("/") or anc.name not in _OBS_POSIX_SYS_ROOT_LINKS:
        return False
    if st.st_uid != 0:
        return False
    try:
        resolved_st = os.stat(anc)
    except OSError:
        return False
    return stat.S_ISDIR(resolved_st.st_mode)


def _obs_is_reparse_stat(st: os.stat_result) -> bool:
    if stat.S_ISLNK(st.st_mode):
        return True
    if IS_WINDOWS:
        return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT) and is_disallowed_reparse_tag(
            st.st_reparse_tag
        )
    return False


def _obs_verify_or_create_ancestors(parent_dir: Path, *, create_missing: bool) -> None:
    chain = (*reversed(parent_dir.parents[:-1]), parent_dir) if parent_dir.parents else ()
    for anc in chain:
        try:
            a_st = os.lstat(anc)
        except FileNotFoundError:
            if not create_missing:
                continue
            try:
                os.mkdir(anc, 0o700)
            except FileExistsError:
                pass
            a_st = os.lstat(anc)
        if _obs_is_reparse_stat(a_st):
            if _obs_is_allowed_posix_root_link(anc, a_st):
                continue
            raise YscbError(ErrorCode.ACCESS_DENIED, f"LogRotator refuses symlinked ancestor directory: {anc}")
        if not stat.S_ISDIR(a_st.st_mode):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"LogRotator ancestor is not a directory: {anc}")


def _obs_verify_regular_or_missing(target: Path) -> Optional[os.stat_result]:
    _obs_verify_or_create_ancestors(target.parent, create_missing=False)
    try:
        st = os.lstat(target)
    except FileNotFoundError:
        return None
    if _obs_is_reparse_stat(st) or not stat.S_ISREG(st.st_mode):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"LogRotator refuses symlink or non-regular file: {target}")
    return st


def _open_non_inheritable_fd(target: Path, flags: int, mode: int = 0o600) -> int:
    try:
        fd = os.open(str(target), flags, mode)
    except OSError as exc:
        if not IS_WINDOWS and exc.errno in (errno.ELOOP, errno.ENXIO, errno.EOPNOTSUPP, errno.EMLINK):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"LogRotator refuses symlink or special file: {target}") from exc
        raise
    try:
        f_st = os.fstat(fd)
        if not stat.S_ISREG(f_st.st_mode):
            raise YscbError(ErrorCode.ACCESS_DENIED, f"LogRotator requires regular file descriptor: {target}")
        if not IS_WINDOWS and (flags & os.O_NONBLOCK):
            os.set_blocking(fd, True)
        os.set_inheritable(fd, False)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    return fd


def _read_lf_lines_strict(target: Path) -> list[str]:
    if _obs_verify_regular_or_missing(target) is None:
        return []
    read_flags = os.O_RDONLY | (os.O_BINARY if IS_WINDOWS else (os.O_NOFOLLOW | os.O_NONBLOCK))
    try:
        fd = _open_non_inheritable_fd(target, read_flags)
    except FileNotFoundError:
        return []
    chunks: list[bytes] = []
    try:
        while True:
            buf = os.read(fd, 65536)
            if not buf:
                break
            chunks.append(buf)
    finally:
        os.close(fd)
    if not chunks:
        return []
    raw_text = b"".join(chunks).decode("utf-8", errors="replace")
    parts = raw_text.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    return [ln[:-1] if ln.endswith("\r") else ln for ln in parts]


def _replace_with_retry(src_path: Path, dst_path: Path) -> None:
    _obs_verify_regular_or_missing(dst_path)
    last_exc: Optional[OSError] = None
    for attempt in range(5):
        try:
            os.replace(str(src_path), str(dst_path))
            return
        except PermissionError as exc:
            last_exc = exc
            if attempt < 4:
                time.sleep(0.01 * (attempt + 1))
    if last_exc is not None:
        raise last_exc


def _atomic_rewrite_lines(target_path: Path, lines: Sequence[str], *, seq_num: int) -> None:
    parent_dir = target_path.parent
    _obs_verify_or_create_ancestors(parent_dir, create_missing=True)
    _obs_verify_regular_or_missing(target_path)
    rand_hex = secrets.token_hex(6)
    tmp_name = f".{target_path.name}{_ROT_TMP_INFIX}{os.getpid()}_{seq_num}_{rand_hex}"
    tmp_path = parent_dir / tmp_name
    encoded = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    tmp_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | (
        os.O_BINARY if IS_WINDOWS else (os.O_NOFOLLOW | os.O_NONBLOCK)
    )
    fd = _open_non_inheritable_fd(tmp_path, tmp_flags, 0o600)
    try:
        _write_all_fd(fd, encoded)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        _replace_with_retry(tmp_path, target_path)
    finally:
        if os.path.lexists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


_STALE_ROT_TMP_MAX_AGE_SEC: Final[float] = 60.0
_HEX12_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{12}$")


def _cleanup_stale_rotation_temps(log_file: Path) -> None:
    parent_dir = log_file.parent
    try:
        _obs_verify_or_create_ancestors(parent_dir, create_missing=False)
    except (YscbError, OSError):
        return
    if not parent_dir.is_dir() or parent_dir.is_symlink():
        return
    prefix = f".{log_file.name}{_ROT_TMP_INFIX}"
    cur_pid = os.getpid()
    now_sec = time.time()
    try:
        with os.scandir(parent_dir) as it:
            for entry in it:
                if not entry.name.startswith(prefix) or entry.is_symlink():
                    continue
                tail = entry.name[len(prefix) :]
                parts = tail.split("_")
                if (
                    len(parts) == 3
                    and parts[0].isdigit()
                    and parts[1].isdigit()
                    and _HEX12_RE.fullmatch(parts[2]) is not None
                ):
                    if int(parts[0]) == cur_pid:
                        continue
                    try:
                        st = entry.stat(follow_symlinks=False)
                        if (now_sec - st.st_mtime) < _STALE_ROT_TMP_MAX_AGE_SEC:
                            continue
                    except OSError:
                        continue
                try:
                    os.unlink(entry.path)
                except OSError:
                    pass
    except OSError:
        pass


def _file_needs_newline_repair(log_file: Path) -> tuple[int, bool]:
    if _obs_verify_regular_or_missing(log_file) is None:
        return (0, False)
    read_flags = os.O_RDONLY | (os.O_BINARY if IS_WINDOWS else (os.O_NOFOLLOW | os.O_NONBLOCK))
    try:
        fd = _open_non_inheritable_fd(log_file, read_flags)
    except FileNotFoundError:
        return (0, False)
    try:
        end_pos = os.lseek(fd, 0, os.SEEK_END)
        if end_pos <= 0:
            return (0, False)
        os.lseek(fd, end_pos - 1, os.SEEK_SET)
        tail_byte = os.read(fd, 1)
        return (end_pos, tail_byte != b"\n")
    finally:
        os.close(fd)


def _acquire_os_advisory_lock(fd: int, *, exclusive: bool) -> None:
    if IS_WINDOWS:
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(fd))
        flags = _OBS_LOCKFILE_EXCLUSIVE_LOCK if exclusive else 0
        ov = _ObsOverlapped()
        if not _OBS_WIN_LOCK_EX(handle, flags, 0, 1, 0, ctypes.byref(ov)):
            err_code = ctypes.get_last_error()
            raise OSError(err_code, f"LockFileEx failed with winerror={err_code}")
        return
    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    while True:
        try:
            fcntl.flock(fd, mode)
            return
        except InterruptedError:
            continue


def _release_os_advisory_lock(fd: int) -> None:
    if IS_WINDOWS:
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(fd))
        ov = _ObsOverlapped()
        _OBS_WIN_UNLOCK_EX(handle, 0, 1, 0, ctypes.byref(ov))
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def _cross_process_log_lock(lock_path: Path, *, create: bool, exclusive: bool) -> Iterator[None]:
    if not create and not os.path.lexists(lock_path):
        yield
        return
    _obs_verify_regular_or_missing(lock_path)
    if create:
        open_flags = os.O_RDWR | os.O_CREAT | (
            os.O_BINARY if IS_WINDOWS else (os.O_NOFOLLOW | os.O_NONBLOCK)
        )
    else:
        open_flags = os.O_RDONLY | (
            os.O_BINARY if IS_WINDOWS else (os.O_NOFOLLOW | os.O_NONBLOCK)
        )
    try:
        fd = _open_non_inheritable_fd(lock_path, open_flags, 0o600)
    except FileNotFoundError:
        if not create:
            yield
            return
        raise
    locked = False
    try:
        _acquire_os_advisory_lock(fd, exclusive=exclusive)
        locked = True
        yield
    finally:
        if locked:
            _release_os_advisory_lock(fd)
        try:
            os.close(fd)
        except OSError:
            pass


class LogRotator:
    """Pure-stdlib rolling file recorder supporting byte/line atomic rotation, crash recovery, and non-inheritable FDs."""

    def __init__(
        self,
        log_path: HostPath,
        *,
        max_bytes: int = 524288,
        max_lines: Optional[int] = None,
        keep_lines: Optional[int] = None,
        max_history_files: int = 5,
    ) -> None:
        if not isinstance(log_path, HostPath):
            raise ValueError(f"LogRotator.log_path must be HostPath, got {log_path!r}")
        require_pure_int(max_bytes, "LogRotator.max_bytes", min_val=1, max_val=INT64_MAX)
        if max_lines is not None:
            require_pure_int(max_lines, "LogRotator.max_lines", min_val=1, max_val=INT64_MAX)
        if keep_lines is not None:
            require_pure_int(keep_lines, "LogRotator.keep_lines", min_val=1, max_val=INT64_MAX)
            if max_lines is not None and keep_lines > max_lines:
                raise ValueError(f"LogRotator.keep_lines ({keep_lines}) cannot exceed max_lines ({max_lines}).")
        require_pure_int(max_history_files, "LogRotator.max_history_files", min_val=0, max_val=1000)
        self._log_path = log_path
        self._max_bytes = max_bytes
        self._max_lines = max_lines
        self._keep_lines = keep_lines
        self._max_history_files = max_history_files
        self._lock = threading.RLock()
        self._rot_seq = 0
        self._closed = False
        _cleanup_stale_rotation_temps(self._log_path.path)

    def _history_path(self, index: int) -> Path:
        base = self._log_path.path
        return base.parent / f"{base.name}.{index}"

    def _lock_file_path(self) -> Path:
        base = self._log_path.path
        return base.parent / f".{base.name}.lock"

    def _rotate_history_files_locked(self) -> None:
        base = self._log_path.path
        if _obs_verify_regular_or_missing(base) is None:
            return
        parent_dir = base.parent
        hist_prefix = f"{base.name}."
        try:
            with os.scandir(parent_dir) as it:
                for entry in it:
                    if entry.name.startswith(hist_prefix):
                        suffix = entry.name[len(hist_prefix) :]
                        if suffix.isdigit() and int(suffix) >= self._max_history_files:
                            try:
                                os.unlink(entry.path)
                            except OSError:
                                pass
        except OSError:
            pass
        if self._max_history_files <= 0:
            self._rot_seq += 1
            _atomic_rewrite_lines(base, (), seq_num=self._rot_seq)
            return
        for idx in range(self._max_history_files - 1, 0, -1):
            src_h = self._history_path(idx)
            if _obs_verify_regular_or_missing(src_h) is not None:
                _replace_with_retry(src_h, self._history_path(idx + 1))
        _replace_with_retry(base, self._history_path(1))

    def _compact_tail_lines_locked(self, target_keep: int, *, jsonl_mode: bool) -> None:
        raw_lines = _read_lf_lines_strict(self._log_path.path)
        if jsonl_mode:
            valid_lines: list[str] = []
            for ln in raw_lines:
                if not ln.strip(" \t\r"):
                    continue
                try:
                    strict_parse_json_object(ln)
                    valid_lines.append(ln)
                except ValueError:
                    continue
            kept = list(valid_lines[-target_keep:])
        else:
            kept = list(raw_lines[-target_keep:])

        if len(kept) > 1:
            line_sizes = [len(ln.encode("utf-8")) + 1 for ln in kept]
            total_bytes = sum(line_sizes)
            drop_idx = 0
            while (len(kept) - drop_idx) > 1 and total_bytes > self._max_bytes:
                total_bytes -= line_sizes[drop_idx]
                drop_idx += 1
            if drop_idx > 0:
                kept = kept[drop_idx:]

        if len(kept) == 1 and len(raw_lines) == 1 and kept[0] == raw_lines[0]:
            return

        self._rot_seq += 1
        _atomic_rewrite_lines(self._log_path.path, kept, seq_num=self._rot_seq)

    def _append_internal(self, clean_line: str, *, jsonl_mode: bool) -> None:
        encoded_line = f"{clean_line}\n".encode("utf-8")
        with self._lock:
            if self._closed:
                raise YscbError(ErrorCode.TEARDOWN_ERROR, "LogRotator is already closed.")
            target = self._log_path.path
            _obs_verify_or_create_ancestors(target.parent, create_missing=True)
            _obs_verify_regular_or_missing(target)
            with _cross_process_log_lock(self._lock_file_path(), create=True, exclusive=True):
                in_place_keep: Optional[int] = self._keep_lines
                if in_place_keep is None and self._max_lines is not None and self._max_history_files == 0:
                    in_place_keep = self._max_lines

                cur_size, needs_nl = _file_needs_newline_repair(target)
                if in_place_keep is None and cur_size > 0:
                    exceeds_bytes = (cur_size + (1 if needs_nl else 0) + len(encoded_line)) > self._max_bytes
                    exceeds_lines = (
                        self._max_lines is not None and len(_read_lf_lines_strict(target)) >= self._max_lines
                    )
                    if exceeds_bytes or exceeds_lines:
                        self._rotate_history_files_locked()
                        cur_size, needs_nl = (0, False)

                _obs_verify_regular_or_missing(target)
                write_bytes = (b"\n" + encoded_line) if needs_nl else encoded_line
                append_flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | (
                    os.O_BINARY if IS_WINDOWS else (os.O_NOFOLLOW | os.O_NONBLOCK)
                )
                fd = _open_non_inheritable_fd(target, append_flags, 0o600)
                try:
                    _write_all_fd(fd, write_bytes)
                    new_size = os.fstat(fd).st_size
                finally:
                    os.close(fd)

                if in_place_keep is not None:
                    need_compact = new_size > self._max_bytes
                    if not need_compact and self._max_lines is not None:
                        need_compact = len(_read_lf_lines_strict(target)) > self._max_lines
                    if need_compact:
                        self._compact_tail_lines_locked(in_place_keep, jsonl_mode=jsonl_mode)

    def append_line(self, line: str) -> None:
        require_pure_str(line, "LogRotator.append_line line")
        stripped = line[:-1] if line.endswith("\n") else line
        if stripped.endswith("\r"):
            stripped = stripped[:-1]
        if "\n" in stripped or "\r" in stripped:
            raise ValueError("LogRotator.append_line forbids embedded CR/LF newline characters.")
        self._append_internal(stripped, jsonl_mode=False)

    def append_jsonl(self, payload: JsonObject) -> None:
        validated = clone_strict_json_object(payload, label="LogRotator.append_jsonl payload")
        serialized = json.dumps(validated, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        self._append_internal(serialized, jsonl_mode=True)

    def _collect_chronological_lines_locked(self) -> list[str]:
        with _cross_process_log_lock(self._lock_file_path(), create=False, exclusive=False):
            if self._keep_lines is None and self._max_history_files > 0:
                merged: list[str] = []
                for idx in range(self._max_history_files, 0, -1):
                    hist_p = self._history_path(idx)
                    merged.extend(_read_lf_lines_strict(hist_p))
                merged.extend(_read_lf_lines_strict(self._log_path.path))
                return merged
            return _read_lf_lines_strict(self._log_path.path)

    def read_tail_lines(self, limit: int = 100) -> tuple[str, ...]:
        require_pure_int(limit, "LogRotator.read_tail_lines limit", min_val=0, max_val=INT64_MAX)
        if limit == 0:
            return ()
        with self._lock:
            all_lines = self._collect_chronological_lines_locked()
            return tuple(all_lines[-limit:])

    def read_jsonl(self, *, limit: Optional[int] = None) -> tuple[MutableJsonObject, ...]:
        if limit is not None:
            require_pure_int(limit, "LogRotator.read_jsonl limit", min_val=0, max_val=INT64_MAX)
            if limit == 0:
                return ()
        with self._lock:
            raw_lines = self._collect_chronological_lines_locked()
        if limit is not None:
            collected_rev: list[MutableJsonObject] = []
            for ln in reversed(raw_lines):
                if not ln.strip(" \t\r"):
                    continue
                try:
                    collected_rev.append(strict_parse_json_object(ln))
                except ValueError:
                    continue
                if len(collected_rev) >= limit:
                    break
            collected_rev.reverse()
            return tuple(collected_rev)
        parsed_all: list[MutableJsonObject] = []
        for ln in raw_lines:
            if not ln.strip(" \t\r"):
                continue
            try:
                parsed_all.append(strict_parse_json_object(ln))
            except ValueError:
                continue
        return tuple(parsed_all)

    def close(self) -> None:
        with self._lock:
            self._closed = True


class StructuredLogger(Protocol):
    """Explicitly injected structured logger protocol consumed via TaskContext and ModuleEnv."""

    def log(self, level: LogLevel, message: str, *, fields: Optional[JsonObject] = None) -> None: ...
    def debug(self, message: str, *, fields: Optional[JsonObject] = None) -> None: ...
    def info(self, message: str, *, fields: Optional[JsonObject] = None) -> None: ...
    def warning(self, message: str, *, fields: Optional[JsonObject] = None) -> None: ...
    def error(self, message: str, *, fields: Optional[JsonObject] = None) -> None: ...


def _normalize_explicit_locale_chain(chain: Sequence[str], *, label: str) -> tuple[str, ...]:
    raw_tup = require_typed_tuple(chain, str, label)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in raw_tup:
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return tuple(ordered)


class LocaleCatalog:
    """Pure-in-memory multi-locale and host proper-noun lookup engine with bounded recursive interpolation."""

    def __init__(
        self,
        dictionaries_by_module: Mapping[ModuleId, Mapping[str, Mapping[str, str]]],
        *,
        default_chain: Sequence[str] = ("zh",),
    ) -> None:
        if not isinstance(dictionaries_by_module, Mapping):
            raise ValueError("LocaleCatalog.dictionaries_by_module must be a Mapping.")
        frozen_mods: dict[ModuleId, Mapping[str, Mapping[str, str]]] = {}
        for mod_id, lang_table in dictionaries_by_module.items():
            if not isinstance(mod_id, ModuleId):
                raise ValueError(f"LocaleCatalog module key must be ModuleId, got {mod_id!r}")
            if not isinstance(lang_table, Mapping):
                raise ValueError(f"LocaleCatalog language table for '{mod_id}' must be a Mapping.")
            frozen_langs: dict[str, Mapping[str, str]] = {}
            for lang_id, kv_map in lang_table.items():
                clean_lang = require_pure_str(lang_id, "LocaleCatalog lang_id", non_empty=True).strip()
                if not isinstance(kv_map, Mapping):
                    raise ValueError(f"LocaleCatalog entries for '{mod_id}:{clean_lang}' must be a Mapping.")
                frozen_kv: dict[str, str] = {}
                for k, v in kv_map.items():
                    clean_k = require_pure_str(k, "LocaleCatalog entry key", non_empty=True).strip()
                    clean_v = require_pure_str(v, "LocaleCatalog entry value")
                    frozen_kv[clean_k] = clean_v
                frozen_langs[clean_lang] = MappingProxyType(frozen_kv)
            frozen_mods[mod_id] = MappingProxyType(frozen_langs)
        self._dicts: Mapping[ModuleId, Mapping[str, Mapping[str, str]]] = MappingProxyType(frozen_mods)
        self._sorted_modules: tuple[ModuleId, ...] = tuple(sorted(frozen_mods.keys(), key=lambda m: m.value))
        self._default_chain: tuple[str, ...] = _normalize_explicit_locale_chain(
            default_chain, label="LocaleCatalog.default_chain"
        )

    def _candidate_modules(self, primary: Optional[ModuleId]) -> tuple[ModuleId, ...]:
        if primary is None or primary not in self._dicts:
            return self._sorted_modules
        return (primary, *(m for m in self._sorted_modules if m != primary))

    def _lookup_entry(
        self,
        raw_key: str,
        *,
        caller_module: Optional[ModuleId],
        active_chain: tuple[str, ...],
    ) -> Optional[tuple[ModuleId, str, str]]:
        stripped = raw_key.strip()
        if not stripped:
            return None
        if ":" in stripped:
            mod_str, sub_key = stripped.split(":", 1)
            mod_clean, key_clean = mod_str.strip(), sub_key.strip()
            if not mod_clean or not key_clean:
                return None
            try:
                explicit_mod = ModuleId(mod_clean)
            except ValueError:
                return None
            mod_table = self._dicts.get(explicit_mod)
            if mod_table is None:
                return None
            for lang_id in active_chain:
                lang_kv = mod_table.get(lang_id)
                if lang_kv is not None and key_clean in lang_kv:
                    return (explicit_mod, key_clean, lang_kv[key_clean])
            return None

        for cand_mod in self._candidate_modules(caller_module):
            mod_table = self._dicts[cand_mod]
            for lang_id in active_chain:
                lang_kv = mod_table.get(lang_id)
                if lang_kv is not None and stripped in lang_kv:
                    return (cand_mod, stripped, lang_kv[stripped])
        return None

    def _interpolate(
        self,
        template: str,
        *,
        current_mod: Optional[ModuleId],
        active_chain: tuple[str, ...],
        params: Optional[Mapping[str, object]],
        visited: frozenset[tuple[ModuleId, str]],
        depth: int,
    ) -> str:
        if "{" not in template and "}" not in template:
            return template

        def _replace_tok(match: re.Match[str]) -> str:
            whole = match.group(0)
            if whole == "{{":
                return "{"
            if whole == "}}":
                return "}"
            token = match.group(1)
            if params is not None and token in params and params[token] is not None:
                return sanitize_utf8_text(str(params[token]))
            if depth >= MAX_LOCALE_INTERPOLATION_DEPTH:
                return whole
            hit = self._lookup_entry(token, caller_module=current_mod, active_chain=active_chain)
            if hit is None:
                return whole
            resolved_mod, resolved_key, sub_tpl = hit
            visit_tag = (resolved_mod, resolved_key)
            if visit_tag in visited:
                return whole
            return self._interpolate(
                sub_tpl,
                current_mod=resolved_mod,
                active_chain=active_chain,
                params=params,
                visited=visited | {visit_tag},
                depth=depth + 1,
            )

        return _LOCALE_TOKEN_RE.sub(_replace_tok, template)

    def translate(
        self,
        key: str,
        *,
        caller_module: Optional[ModuleId] = None,
        chain: Optional[Sequence[str]] = None,
        params: Optional[Mapping[str, object]] = None,
    ) -> str:
        require_pure_str(key, "LocaleCatalog.translate key")
        if caller_module is not None and not isinstance(caller_module, ModuleId):
            raise ValueError(f"LocaleCatalog.translate caller_module must be ModuleId or None, got {caller_module!r}")
        if params is not None:
            if not isinstance(params, Mapping):
                raise ValueError("LocaleCatalog.translate params must be a Mapping or None.")
            for pk in params:
                require_pure_str(pk, "LocaleCatalog.translate param key")
        active_chain = (
            _normalize_explicit_locale_chain(chain, label="LocaleCatalog.translate chain")
            if chain is not None
            else self._default_chain
        )
        hit = self._lookup_entry(key, caller_module=caller_module, active_chain=active_chain)
        if hit is None:
            return self._interpolate(
                key,
                current_mod=caller_module,
                active_chain=active_chain,
                params=params,
                visited=frozenset(),
                depth=0,
            )
        resolved_mod, resolved_key, raw_tpl = hit
        return self._interpolate(
            raw_tpl,
            current_mod=resolved_mod,
            active_chain=active_chain,
            params=params,
            visited=frozenset({(resolved_mod, resolved_key)}),
            depth=0,
        )
