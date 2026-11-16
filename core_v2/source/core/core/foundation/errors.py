"""Structured error hierarchy and machine-actionable remediation codes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, NoReturn, Optional


class ErrorCode(Enum):
    """Canonical error codes across runtime, transport, security, and lifecycle."""

    TASK_NOT_FOUND = "task_not_found"
    EXPOSURE_DENIED = "exposure_denied"
    SECURITY_GATED = "security_gated"
    TTY_REQUIRED = "tty_required"
    COLD_DISPATCH_FORBIDDEN = "cold_dispatch_forbidden"
    DAEMON_UNAVAILABLE = "daemon_unavailable"
    HOT_MUTATION_FORBIDDEN = "hot_mutation_forbidden"
    CALL_CYCLE_DETECTED = "call_cycle_detected"
    EVENT_CYCLE_DETECTED = "event_cycle_detected"
    ILLEGAL_LOCK_REENTRANCY = "illegal_lock_reentrancy"
    TASK_CANCELLED = "task_cancelled"
    TASK_PREEMPTED = "task_preempted"
    TASK_TIMEOUT = "task_timeout"
    TRANSPORT_LOST = "transport_lost"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    CODEC_VALIDATION_FAILED = "codec_validation_failed"
    WORKER_CRASHED = "worker_crashed"
    MODULE_DEGRADED = "module_degraded"
    TEARDOWN_ERROR = "teardown_error"
    BUSINESS_FAILURE = "business_failure"


def sanitize_utf8_text(text: str) -> str:
    """Escape lone UTF-16 surrogates (e.g. POSIX os.fsdecode bytes) so diagnostics remain valid UTF-8 JSON."""
    if type(text) is not str:
        raise ValueError(f"Expected plain str text, got {text!r}")
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


def safe_exception_summary(exc: BaseException) -> str:
    """Format ``TypeName: message`` safely even when ``exc.__str__()`` raises or emits lone surrogates."""
    cls_name = type(exc).__name__
    try:
        detail = sanitize_utf8_text(str(exc))
    except BaseException:
        return f"{cls_name}: <unprintable exception>"
    return f"{cls_name}: {detail}" if detail else cls_name


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    """Serializable structured error diagnostic with optional remediation hint."""

    code: ErrorCode
    message: str
    remediation: Optional[str] = None
    source_task: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ErrorCode):
            raise ValueError(f"ErrorDetail.code must be ErrorCode, got {self.code!r}")
        object.__setattr__(self, "message", sanitize_utf8_text(self.message))
        if self.remediation is not None:
            object.__setattr__(self, "remediation", sanitize_utf8_text(self.remediation))
        if self.source_task is not None:
            object.__setattr__(self, "source_task", sanitize_utf8_text(self.source_task))

    def with_fallback_task(self, task_id: str) -> ErrorDetail:
        """Return this ErrorDetail with source_task populated when currently unset."""
        if self.source_task is not None:
            return self
        return ErrorDetail(
            code=self.code,
            message=self.message,
            remediation=self.remediation,
            source_task=task_id,
        )

    def raise_as_exception(self) -> NoReturn:
        """Raise the canonical YscbError subclass corresponding to this ErrorDetail."""
        if self.code == ErrorCode.EVENT_CYCLE_DETECTED:
            raise EventCycleError(self.message, remediation=self.remediation, source_task=self.source_task)
        if self.code == ErrorCode.CALL_CYCLE_DETECTED:
            raise CallCycleError(self.message, remediation=self.remediation, source_task=self.source_task)
        if self.code in (ErrorCode.TASK_CANCELLED, ErrorCode.TASK_PREEMPTED):
            raise TaskCancelledException(
                self.message,
                preempted=(self.code == ErrorCode.TASK_PREEMPTED),
                remediation=self.remediation,
                source_task=self.source_task,
            )
        raise YscbError(self.code, self.message, remediation=self.remediation, source_task=self.source_task)


class YscbError(Exception):
    """Base exception carrying an immutable ErrorDetail."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        remediation: Optional[str] = None,
        source_task: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.detail = ErrorDetail(
            code=code,
            message=message,
            remediation=remediation,
            source_task=source_task,
        )


FATAL_TURN_ERROR_CODES: Final[frozenset[ErrorCode]] = frozenset(
    {
        ErrorCode.EVENT_CYCLE_DETECTED,
        ErrorCode.CALL_CYCLE_DETECTED,
        ErrorCode.ILLEGAL_LOCK_REENTRANCY,
    }
)


def is_fatal_error_code(code: ErrorCode) -> bool:
    """Return True if an ErrorCode mandates immediate turn/cascade abortion."""
    return code in FATAL_TURN_ERROR_CODES


class EventCycleError(YscbError):
    """Raised immediately when CausalLineage detects a closed event loop."""

    def __init__(
        self,
        message: str,
        *,
        remediation: Optional[str] = None,
        source_task: Optional[str] = None,
    ) -> None:
        eff_rem = (
            remediation
            if remediation is not None
            else "Break the cyclic event subscription chain in TaskMetadata.subscriptions."
        )
        super().__init__(
            ErrorCode.EVENT_CYCLE_DETECTED,
            message,
            remediation=eff_rem,
            source_task=source_task,
        )


class CallCycleError(YscbError):
    """Raised when synchronous CallStack[(workspace_root, task_id)] forms a cycle."""

    def __init__(
        self,
        message: str,
        *,
        remediation: Optional[str] = None,
        source_task: Optional[str] = None,
    ) -> None:
        eff_rem = (
            remediation
            if remediation is not None
            else "Remove recursive synchronous ctx.invoke_task() calls within the same workspace."
        )
        super().__init__(
            ErrorCode.CALL_CYCLE_DETECTED,
            message,
            remediation=eff_rem,
            source_task=source_task,
        )


class TaskCancelledException(YscbError):
    """Raised cooperatively when a CancellationToken is triggered."""

    def __init__(
        self,
        message: str = "Task execution cancelled.",
        *,
        preempted: bool = False,
        remediation: Optional[str] = None,
        source_task: Optional[str] = None,
    ) -> None:
        super().__init__(
            ErrorCode.TASK_PREEMPTED if preempted else ErrorCode.TASK_CANCELLED,
            message,
            remediation=remediation,
            source_task=source_task,
        )
