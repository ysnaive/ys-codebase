"""Cooperative cancellation tokens, monotonic deadline guards, progress reporting, and stdout purity."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import io
import math
import sys
import threading
import time
from typing import BinaryIO, Callable, ClassVar, Final, Iterable, Iterator, Optional, Sequence, TextIO

from core.foundation.errors import ErrorCode, TaskCancelledException, YscbError
from core.foundation.primitives import INT64_MAX, INT64_MIN, require_pure_bool, require_pure_int, require_pure_str


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


MAX_SAFE_WAIT_SEC: Final[float] = min(86400.0 * 7.0, float(threading.TIMEOUT_MAX) * 0.5)
MAX_TIMEOUT_MS: Final[int] = int(MAX_SAFE_WAIT_SEC * 1000.0)


def safe_real_to_float(val: object, *, label: str = "value") -> float:
    """Convert exact int/float (excluding bool/Enum/subclasses) to pure float, clamping huge ints within [-1e18, 1e18]."""
    if type(val) not in (int, float):
        raise ValueError(f"{label} must be an exact int or float, got {val!r}")
    if type(val) is int:
        return float(min(10**18, max(-(10**18), val)))
    return val


def _validate_min_sec(min_sec: float) -> float:
    f_min = safe_real_to_float(min_sec, label="min_sec")
    if not math.isfinite(f_min) or f_min < 0.0:
        raise ValueError(f"min_sec must be finite and >= 0, got {min_sec!r}")
    return min(MAX_SAFE_WAIT_SEC, f_min)


def clamp_wait_sec(timeout_sec: Optional[float], *, min_sec: float = 0.0) -> Optional[float]:
    """Validate optional wait seconds (rejecting bool and NaN) and clamp within [min_sec, MAX_SAFE_WAIT_SEC]."""
    safe_min = _validate_min_sec(min_sec)
    if timeout_sec is None:
        return None
    f_val = safe_real_to_float(timeout_sec, label="timeout_sec")
    if math.isnan(f_val):
        raise ValueError(f"timeout_sec must not be bool or NaN, got {timeout_sec!r}")
    return min(MAX_SAFE_WAIT_SEC, max(safe_min, f_val))


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
    eff_max = min(MAX_SAFE_WAIT_SEC, max_sec)
    if default_sec is not None:
        try:
            f_val = safe_real_to_float(val, label=label)
        except ValueError:
            return default_sec
        if not math.isfinite(f_val) or f_val <= 0.0:
            return default_sec
        return min(eff_max, max(min_sec, f_val))
    f_strict = safe_real_to_float(val, label=label)
    if math.isnan(f_strict) or f_strict <= 0.0:
        raise ValueError(f"{label} must be > 0 (not bool or NaN), got {val!r}")
    return min(eff_max, max(min_sec, f_strict))


def ms_to_safe_sec(ms: int, *, min_sec: float = 0.0) -> float:
    """Convert integer milliseconds to safe monotonic seconds clamped within [min_sec, MAX_SAFE_WAIT_SEC]."""
    safe_min = _validate_min_sec(min_sec)
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


class _ThreadLocalStdoutProxy(io.TextIOBase):
    """TextIOBase-compliant thread-local stdout proxy isolating active task threads."""

    _INSTALL_LOCK: ClassVar[threading.RLock] = threading.RLock()
    _CAPTURE_LOCAL: ClassVar[_CaptureBufferStackLocal] = _CaptureBufferStackLocal()
    _TOTAL_ACTIVE_GUARDS: ClassVar[int] = 0

    def __init__(self, fallback: Optional[TextIO]) -> None:
        super().__init__()
        self._fallback: Optional[TextIO] = fallback
        self._fallback_encoding = (
            fallback.encoding if (fallback is not None and isinstance(fallback.encoding, str)) else "utf-8"
        )

    @classmethod
    def _unwrap_proxy_chain(cls, stream: Optional[TextIO]) -> Optional[TextIO]:
        cur = stream
        while isinstance(cur, _ThreadLocalStdoutProxy):
            cur = cur._fallback
        return cur

    def _fallback_detached(self) -> Optional[TextIO]:
        if self._TOTAL_ACTIVE_GUARDS == 0 and isinstance(sys.stdout, _ThreadLocalStdoutProxy):
            with self._INSTALL_LOCK:
                if self._TOTAL_ACTIVE_GUARDS == 0 and isinstance(sys.stdout, _ThreadLocalStdoutProxy):
                    sys.stdout = self._unwrap_proxy_chain(sys.stdout)
        return self._fallback

    def _target(self) -> Optional[TextIO | io.StringIO]:
        fb = self._fallback_detached()
        if self._TOTAL_ACTIVE_GUARDS == 0:
            return fb
        cap = self._CAPTURE_LOCAL.stack[-1] if self._CAPTURE_LOCAL.stack else None
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
        cap = self._CAPTURE_LOCAL.stack[-1] if (self._TOTAL_ACTIVE_GUARDS > 0 and self._CAPTURE_LOCAL.stack) else None
        return bool(fb.isatty()) if (cap is None and fb is not None) else False

    def fileno(self) -> int:
        fb = self._fallback_detached()
        cap = self._CAPTURE_LOCAL.stack[-1] if (self._TOTAL_ACTIVE_GUARDS > 0 and self._CAPTURE_LOCAL.stack) else None
        if cap is not None or fb is None:
            raise io.UnsupportedOperation("Captured task stdout does not expose raw OS fileno")
        return fb.fileno()

    @property
    def buffer(self) -> BinaryIO:
        fb = self._fallback_detached()
        cap = self._CAPTURE_LOCAL.stack[-1] if (self._TOTAL_ACTIVE_GUARDS > 0 and self._CAPTURE_LOCAL.stack) else None
        if cap is not None or fb is None:
            raise io.UnsupportedOperation("Captured task stdout does not expose binary buffer")
        return fb.buffer

    @property
    def encoding(self) -> str:
        _ = self._fallback_detached()
        return self._fallback_encoding

    @classmethod
    def enter_guard(cls, frame_buf: Optional[io.StringIO]) -> Optional[_ThreadLocalStdoutProxy]:
        with cls._INSTALL_LOCK:
            cur = sys.stdout
            if frame_buf is None and not isinstance(cur, _ThreadLocalStdoutProxy):
                return None
            if isinstance(cur, _ThreadLocalStdoutProxy) and cls._TOTAL_ACTIVE_GUARDS > 0:
                proxy = cur
            else:
                proxy = cls(cls._unwrap_proxy_chain(cur))
                sys.stdout = proxy
            cls._TOTAL_ACTIVE_GUARDS += 1
            cls._CAPTURE_LOCAL.stack.append(frame_buf)
            return proxy

    def exit_guard(self) -> None:
        with self._INSTALL_LOCK:
            if self._CAPTURE_LOCAL.stack:
                self._CAPTURE_LOCAL.stack.pop()
            type(self)._TOTAL_ACTIVE_GUARDS = max(0, type(self)._TOTAL_ACTIVE_GUARDS - 1)
            if type(self)._TOTAL_ACTIVE_GUARDS == 0 and isinstance(sys.stdout, _ThreadLocalStdoutProxy):
                sys.stdout = self._unwrap_proxy_chain(sys.stdout)


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
            proxy.exit_guard()
