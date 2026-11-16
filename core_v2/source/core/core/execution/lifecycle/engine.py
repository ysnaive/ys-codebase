"""TurnEngine, ColdTurnRunner, WorkerContainerLifecycle, and LifoResourceStack."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import threading
import uuid
from typing import Callable, Generic, Mapping, Optional, Protocol, Sequence, TypeVar

from core.execution.event import DoubleBufferedEventQueue, EventBatchEnvelope, RawEventRecord
from core.foundation.errors import ErrorCode, ErrorDetail, YscbError, safe_exception_summary
from core.foundation.observability import MAX_TIMEOUT_MS, CancellationToken, ms_to_safe_sec
from core.foundation.primitives import JsonValue, ModuleId, invoke_observer_safely, require_pure_int, require_pure_str, require_typed_frozenset, require_typed_tuple

TOut_co = TypeVar("TOut_co", covariant=True)
TReq = TypeVar("TReq")
TReqContra = TypeVar("TReqContra", contravariant=True)


class TurnKind(Enum):
    COLD = "cold"
    HOT_FOREGROUND = "hot_fg"
    HOT_BACKGROUND = "hot_bg"


class ContainerState(Enum):
    UNINITIALIZED = "uninitialized"
    BOOTING = "booting"
    WARMING = "warming"
    READY = "ready"
    QUIESCED = "quiesced"
    DRAINING = "draining"
    STOPPED = "stopped"


def _wrap_void_closer(close_fn: Callable[[], None]) -> Callable[[], Sequence[ErrorDetail]]:
    def _run() -> Sequence[ErrorDetail]:
        close_fn()
        return ()

    return _run


class LifoResourceStack:
    """Thread-safe LIFO teardown stack isolating individual close() failures and preserving LIFO diagnostics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[tuple[str, Callable[[], Sequence[ErrorDetail]]]] = []

    def push_closeable(self, owner: str, close_fn: Callable[[], None]) -> None:
        require_pure_str(owner, "LifoResourceStack.owner", non_empty=True)
        if not callable(close_fn):
            raise ValueError("LifoResourceStack.close_fn must be callable.")
        with self._lock:
            self._entries.append((owner, _wrap_void_closer(close_fn)))

    def push_diagnostic_closeable(
        self,
        owner: str,
        close_fn: Callable[[], Sequence[ErrorDetail]],
    ) -> None:
        require_pure_str(owner, "LifoResourceStack.owner", non_empty=True)
        if not callable(close_fn):
            raise ValueError("LifoResourceStack.close_fn must be callable.")
        with self._lock:
            self._entries.append((owner, close_fn))

    def pop_tagged_by_prefixes(
        self,
        prefixes: frozenset[str],
    ) -> tuple[tuple[str, Callable[[], Sequence[ErrorDetail]]], ...]:
        if not prefixes:
            return ()
        matched: list[tuple[str, Callable[[], Sequence[ErrorDetail]]]] = []
        remaining: list[tuple[str, Callable[[], Sequence[ErrorDetail]]]] = []
        dot_prefixes = tuple(f"{p}." for p in prefixes)
        with self._lock:
            for owner, fn in self._entries:
                if owner in prefixes or owner.startswith(dot_prefixes):
                    matched.append((owner, fn))
                else:
                    remaining.append((owner, fn))
            self._entries = remaining
        matched.reverse()
        return tuple(matched)

    @staticmethod
    def run_void_closer(owner: str, close_fn: Callable[[], None]) -> tuple[ErrorDetail, ...]:
        require_pure_str(owner, "LifoResourceStack.owner", non_empty=True)
        if not callable(close_fn):
            raise ValueError("LifoResourceStack.close_fn must be callable.")
        return LifoResourceStack.run_closers(((owner, _wrap_void_closer(close_fn)),))

    @staticmethod
    def run_closers(
        entries: Sequence[tuple[str, Callable[[], Sequence[ErrorDetail]]]],
    ) -> tuple[ErrorDetail, ...]:
        if isinstance(entries, (str, bytes, bytearray, memoryview)) or not isinstance(entries, Sequence):
            raise ValueError("LifoResourceStack.run_closers requires a Sequence of (owner, close_fn) pairs.")
        errors: list[ErrorDetail] = []
        deferred_base: Optional[BaseException] = None
        for owner, close_fn in entries:
            safe_owner = owner if type(owner) is str else repr(owner)
            try:
                sub_diags = close_fn()
                if sub_diags:
                    errors.extend(require_typed_tuple(sub_diags, ErrorDetail, "close_fn diagnostics"))
            except (Exception, SystemExit, GeneratorExit) as exc:
                errors.append(
                    ErrorDetail(
                        code=ErrorCode.TEARDOWN_ERROR,
                        message=f"Teardown close() failed for '{safe_owner}': {safe_exception_summary(exc)}",
                        source_task=safe_owner,
                    )
                )
            except BaseException as base_exc:
                if deferred_base is None:
                    deferred_base = base_exc
        if deferred_base is not None:
            raise deferred_base
        return tuple(errors)

    def close_all_lifo(self) -> tuple[ErrorDetail, ...]:
        with self._lock:
            items = list(reversed(self._entries))
            self._entries.clear()
        return LifoResourceStack.run_closers(items)


@dataclass(slots=True)
class TurnScope:
    """Master-owned per-Turn state isolating queued events and scoped teardown resources."""

    turn_id: str
    kind: TurnKind
    cancel_token: CancellationToken
    event_queue: DoubleBufferedEventQueue = field(default_factory=DoubleBufferedEventQueue)
    scoped_stack: LifoResourceStack = field(default_factory=LifoResourceStack)
    on_diagnostic: Optional[Callable[[ErrorDetail], None]] = None
    _diag_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False, compare=False)
    _event_diagnostics: list[ErrorDetail] = field(default_factory=list, init=False, repr=False, compare=False)
    _teardown_diagnostics: list[ErrorDetail] = field(default_factory=list, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        require_pure_str(self.turn_id, "TurnScope.turn_id", non_empty=True)
        if not isinstance(self.kind, TurnKind):
            raise ValueError(f"TurnScope.kind must be TurnKind, got {self.kind!r}")
        if not isinstance(self.cancel_token, CancellationToken):
            raise ValueError(f"TurnScope.cancel_token must be CancellationToken, got {self.cancel_token!r}")
        if not isinstance(self.event_queue, DoubleBufferedEventQueue):
            raise ValueError("TurnScope.event_queue must be DoubleBufferedEventQueue.")
        if not isinstance(self.scoped_stack, LifoResourceStack):
            raise ValueError("TurnScope.scoped_stack must be LifoResourceStack.")
        if self.on_diagnostic is not None and not callable(self.on_diagnostic):
            raise ValueError("TurnScope.on_diagnostic must be callable or None.")

    def record_event_diagnostic(self, detail: ErrorDetail) -> None:
        with self._diag_lock:
            self._event_diagnostics.append(detail)
        cb = self.on_diagnostic
        if cb is not None:
            invoke_observer_safely(lambda: cb(detail))

    def snapshot_event_diagnostics(self) -> tuple[ErrorDetail, ...]:
        with self._diag_lock:
            return tuple(self._event_diagnostics)

    def close_scoped_stack_recorded(self) -> tuple[ErrorDetail, ...]:
        errs = self.scoped_stack.close_all_lifo()
        with self._diag_lock:
            if errs:
                self._teardown_diagnostics.extend(errs)
            return tuple(self._teardown_diagnostics)


@dataclass(frozen=True, slots=True)
class StepExecutionResult(Generic[TOut_co]):
    """Outcome of a single primary or event-subscriber task step."""

    ok: bool
    outcome: Optional[TOut_co] = None
    error: Optional[ErrorDetail] = None
    preempted: bool = False
    coalesced: bool = False
    fatal_abort_turn: bool = False
    committed_events: tuple[RawEventRecord, ...] = ()

    def __post_init__(self) -> None:
        for flag, label in (
            (self.ok, "ok"),
            (self.preempted, "preempted"),
            (self.coalesced, "coalesced"),
            (self.fatal_abort_turn, "fatal_abort_turn"),
        ):
            if not isinstance(flag, bool):
                raise ValueError(f"StepExecutionResult.{label} must be a bool.")
        if self.error is not None and not isinstance(self.error, ErrorDetail):
            raise ValueError("StepExecutionResult.error must be ErrorDetail or None.")
        object.__setattr__(
            self, "committed_events", require_typed_tuple(self.committed_events, RawEventRecord, "committed_events")
        )


@dataclass(frozen=True, slots=True)
class TurnExecutionReport:
    """Complete result of primary dispatch, double-buffered event cascade draining, and LIFO teardown."""

    turn_id: str
    primary_result: StepExecutionResult[JsonValue]
    event_diagnostics: tuple[ErrorDetail, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    fatal_event_error: Optional[ErrorDetail] = None

    def __post_init__(self) -> None:
        require_pure_str(self.turn_id, "TurnExecutionReport.turn_id", non_empty=True)
        if not isinstance(self.primary_result, StepExecutionResult):
            raise ValueError("TurnExecutionReport.primary_result must be StepExecutionResult.")
        if self.fatal_event_error is not None and not isinstance(self.fatal_event_error, ErrorDetail):
            raise ValueError("TurnExecutionReport.fatal_event_error must be ErrorDetail or None.")
        object.__setattr__(
            self, "event_diagnostics", require_typed_tuple(self.event_diagnostics, ErrorDetail, "event_diagnostics")
        )
        object.__setattr__(
            self, "teardown_diagnostics", require_typed_tuple(self.teardown_diagnostics, ErrorDetail, "teardown_diagnostics")
        )


class TaskStepExecutor(Protocol, Generic[TReqContra]):
    """Injected by execution.runtime so lifecycle never reverse-imports runtime."""

    def run_primary_step(self, request: TReqContra, turn: TurnScope) -> StepExecutionResult[JsonValue]: ...
    def run_event_step(self, batch: EventBatchEnvelope, turn: TurnScope) -> Sequence[StepExecutionResult[JsonValue]]: ...
    def finalize_turn_events(self, turn: TurnScope, *, abort_only: bool = False) -> Optional[ErrorDetail]: ...


class TurnEngine(Generic[TReq]):
    """Drives primary task dispatch and double-buffered BFS event draining with LIFO teardown."""

    def __init__(self, executor: TaskStepExecutor[TReq]) -> None:
        self._executor = executor

    def execute_turn(
        self,
        request: TReq,
        kind: TurnKind,
        *,
        cancel_token: Optional[CancellationToken] = None,
        turn_id: Optional[str] = None,
        scope: Optional[TurnScope] = None,
    ) -> TurnExecutionReport:
        if scope is not None and not isinstance(scope, TurnScope):
            raise ValueError(f"scope must be TurnScope or None, got {scope!r}")
        if turn_id is not None:
            require_pure_str(turn_id, "turn_id", non_empty=True)
        scope = scope or TurnScope(
            turn_id=turn_id or uuid.uuid4().hex,
            kind=kind,
            cancel_token=cancel_token or CancellationToken(),
        )
        fatal_event_error: Optional[ErrorDetail] = None
        try:
            primary_res = self._executor.run_primary_step(request, scope)
            if primary_res.committed_events and not primary_res.fatal_abort_turn:
                scope.event_queue.append_committed(primary_res.committed_events)

            if primary_res.fatal_abort_turn:
                scope.event_queue.clear()
                self._executor.finalize_turn_events(scope, abort_only=True)
                is_ev_cyc = primary_res.error is not None and primary_res.error.code == ErrorCode.EVENT_CYCLE_DETECTED
                fatal_event_error = primary_res.error if is_ev_cyc else None
            else:
                fatal_event_error = self.drain_turn_scope(scope)
                cas_err = self._executor.finalize_turn_events(scope, abort_only=(fatal_event_error is not None))
                if fatal_event_error is None and cas_err is not None:
                    primary_res, fatal_event_error = _apply_cascade_finalize_error(primary_res, cas_err)
                if primary_res.ok and fatal_event_error is None and scope.cancel_token.is_cancelled:
                    primary_res = _cancelled_turn_result(scope.cancel_token, primary_res.coalesced)
        except KeyboardInterrupt:
            try:
                self._executor.finalize_turn_events(scope, abort_only=True)
            finally:
                sig_rep = _abort_scope_on_sigint(scope)
            return sig_rep
        except BaseException:
            try:
                self._executor.finalize_turn_events(scope, abort_only=True)
            finally:
                scope.close_scoped_stack_recorded()
            raise

        teardown_errs = scope.close_scoped_stack_recorded()
        return TurnExecutionReport(
            turn_id=scope.turn_id,
            primary_result=primary_res,
            event_diagnostics=scope.snapshot_event_diagnostics(),
            teardown_diagnostics=teardown_errs,
            fatal_event_error=fatal_event_error,
        )

    def execute_event_turn(
        self,
        scope: TurnScope,
        seed_records: Sequence[RawEventRecord],
        *,
        on_events_staged: Optional[Callable[[Sequence[RawEventRecord]], None]] = None,
    ) -> TurnExecutionReport:
        """Drain an event-seeded TurnScope through the exact same BFS + LIFO pipeline."""
        if not isinstance(scope, TurnScope):
            raise ValueError(f"scope must be TurnScope, got {scope!r}")
        primary_res: StepExecutionResult[JsonValue] = StepExecutionResult(ok=True)
        fatal_err: Optional[ErrorDetail] = None
        try:
            if seed_records and not scope.cancel_token.is_cancelled:
                if on_events_staged is not None:
                    on_events_staged(seed_records)
                scope.event_queue.append_committed(seed_records)
            fatal_err = self.drain_turn_scope(scope, on_events_staged=on_events_staged)
            cas_err = self._executor.finalize_turn_events(scope, abort_only=(fatal_err is not None))
            if fatal_err is not None:
                primary_res = StepExecutionResult(ok=False, error=fatal_err)
            elif cas_err is not None:
                primary_res, fatal_err = _apply_cascade_finalize_error(primary_res, cas_err)
            if primary_res.ok and fatal_err is None and scope.cancel_token.is_cancelled:
                primary_res = _cancelled_turn_result(scope.cancel_token, False)
        except KeyboardInterrupt:
            try:
                self._executor.finalize_turn_events(scope, abort_only=True)
            finally:
                sig_rep = _abort_scope_on_sigint(scope)
            return sig_rep
        except BaseException:
            try:
                self._executor.finalize_turn_events(scope, abort_only=True)
            finally:
                scope.close_scoped_stack_recorded()
            raise

        teardown_errs = scope.close_scoped_stack_recorded()
        return TurnExecutionReport(
            turn_id=scope.turn_id,
            primary_result=primary_res,
            event_diagnostics=scope.snapshot_event_diagnostics(),
            teardown_diagnostics=teardown_errs,
            fatal_event_error=fatal_err,
        )

    def drain_turn_scope(
        self,
        scope: TurnScope,
        *,
        on_events_staged: Optional[Callable[[Sequence[RawEventRecord]], None]] = None,
    ) -> Optional[ErrorDetail]:
        while scope.event_queue.has_pending:
            if scope.cancel_token.is_cancelled:
                scope.event_queue.clear()
                return None
            for batch in scope.event_queue.freeze_and_swap():
                fatal_err = self._drain_single_batch(batch, scope, on_events_staged=on_events_staged)
                if fatal_err is not None:
                    scope.event_queue.clear()
                    return fatal_err
                if scope.cancel_token.is_cancelled:
                    scope.event_queue.clear()
                    return None
        return None

    def _drain_single_batch(
        self,
        batch: EventBatchEnvelope,
        scope: TurnScope,
        *,
        on_events_staged: Optional[Callable[[Sequence[RawEventRecord]], None]],
    ) -> Optional[ErrorDetail]:
        if scope.cancel_token.is_cancelled:
            return None
        for sub_res in self._executor.run_event_step(batch, scope):
            if sub_res.fatal_abort_turn:
                scope.event_queue.clear()
                return sub_res.error or ErrorDetail(ErrorCode.BUSINESS_FAILURE, "Fatal subscriber abort")
            if sub_res.committed_events:
                if on_events_staged is not None:
                    on_events_staged(sub_res.committed_events)
                if scope.cancel_token.is_cancelled:
                    scope.event_queue.clear()
                    return None
                scope.event_queue.append_committed(sub_res.committed_events)
            if (
                not sub_res.ok
                and not sub_res.preempted
                and sub_res.error is not None
                and not (scope.cancel_token.is_cancelled and sub_res.error.code == ErrorCode.TASK_CANCELLED)
            ):
                scope.record_event_diagnostic(sub_res.error)
        return None


def _apply_cascade_finalize_error(
    primary_res: StepExecutionResult[JsonValue],
    cas_err: ErrorDetail,
) -> tuple[StepExecutionResult[JsonValue], Optional[ErrorDetail]]:
    if cas_err.code in (ErrorCode.TASK_CANCELLED, ErrorCode.TASK_PREEMPTED, ErrorCode.TASK_TIMEOUT):
        if not primary_res.ok:
            return (primary_res, None)
        return (
            StepExecutionResult(
                ok=False,
                error=cas_err,
                preempted=(cas_err.code == ErrorCode.TASK_PREEMPTED),
                coalesced=primary_res.coalesced,
            ),
            None,
        )
    return (primary_res, cas_err)


def _cancelled_turn_result(tok: CancellationToken, coalesced: bool) -> StepExecutionResult[JsonValue]:
    code = ErrorCode.TASK_PREEMPTED if tok.is_preempted else ErrorCode.TASK_CANCELLED
    return StepExecutionResult(
        ok=False,
        preempted=tok.is_preempted,
        coalesced=coalesced,
        error=ErrorDetail(code=code, message=tok.reason or "Turn cancelled during event drain"),
    )


def _abort_scope_on_sigint(scope: TurnScope) -> TurnExecutionReport:
    scope.cancel_token.cancel(reason="Interrupted by SIGINT")
    scope.event_queue.clear()
    teardown_errs = scope.close_scoped_stack_recorded()
    return TurnExecutionReport(
        turn_id=scope.turn_id,
        primary_result=StepExecutionResult(
            ok=False,
            error=ErrorDetail(code=ErrorCode.TASK_CANCELLED, message="Interrupted by SIGINT"),
        ),
        event_diagnostics=scope.snapshot_event_diagnostics(),
        teardown_diagnostics=teardown_errs,
    )


def _build_failed_cold_report(
    scope: Optional[TurnScope],
    eff_tid: str,
    session_stack: LifoResourceStack,
    err: ErrorDetail,
) -> TurnExecutionReport:
    ev_diags = scope.snapshot_event_diagnostics() if scope is not None else ()
    sc_td: tuple[ErrorDetail, ...] = ()
    try:
        if scope is not None:
            sc_td = scope.close_scoped_stack_recorded()
    finally:
        sess_td = session_stack.close_all_lifo()
    return TurnExecutionReport(
        turn_id=eff_tid,
        primary_result=StepExecutionResult(ok=False, error=err),
        event_diagnostics=ev_diags,
        teardown_diagnostics=(*sc_td, *sess_td),
    )


class ColdTurnRunner(Generic[TReq]):
    """Drives ColdTurnLifecycle LIFO bootstrap/teardown and exception convergence under leased installer locks."""

    def __init__(
        self,
        turn_engine: TurnEngine[TReq],
        *,
        on_bootstrap_check: Optional[Callable[[LifoResourceStack], None]] = None,
    ) -> None:
        self._turn_engine = turn_engine
        self._on_bootstrap_check = on_bootstrap_check

    def execute_leased_turn(
        self,
        request: TReq,
        *,
        cancel_token: Optional[CancellationToken] = None,
        turn_id: Optional[str] = None,
        scope: Optional[TurnScope] = None,
        fallback_task: Optional[str] = None,
    ) -> TurnExecutionReport:
        if scope is not None and not isinstance(scope, TurnScope):
            raise ValueError(f"scope must be TurnScope or None, got {scope!r}")
        if turn_id is not None:
            require_pure_str(turn_id, "turn_id", non_empty=True)
        if fallback_task is not None:
            require_pure_str(fallback_task, "fallback_task", non_empty=True)
        if cancel_token is not None and not isinstance(cancel_token, CancellationToken):
            raise ValueError(f"cancel_token must be CancellationToken or None, got {cancel_token!r}")
        session_stack = LifoResourceStack()
        token = scope.cancel_token if scope is not None else (cancel_token or CancellationToken())
        eff_tid = scope.turn_id if scope is not None else (turn_id or uuid.uuid4().hex)
        eff_scope = scope or TurnScope(turn_id=eff_tid, kind=TurnKind.COLD, cancel_token=token)
        try:
            if self._on_bootstrap_check is not None:
                self._on_bootstrap_check(session_stack)
            report = self._turn_engine.execute_turn(
                request,
                TurnKind.COLD,
                cancel_token=token,
                turn_id=eff_tid,
                scope=eff_scope,
            )
        except YscbError as exc:
            det = exc.detail.with_fallback_task(fallback_task) if fallback_task else exc.detail
            return _build_failed_cold_report(eff_scope, eff_tid, session_stack, det)
        except KeyboardInterrupt:
            token.cancel(reason="Interrupted by SIGINT")
            det_int = ErrorDetail(code=ErrorCode.TASK_CANCELLED, message="Interrupted by SIGINT")
            return _build_failed_cold_report(eff_scope, eff_tid, session_stack, det_int)
        except (Exception, SystemExit, GeneratorExit) as exc:
            det_exc = ErrorDetail(code=ErrorCode.BUSINESS_FAILURE, message=safe_exception_summary(exc), source_task=fallback_task)
            return _build_failed_cold_report(eff_scope, eff_tid, session_stack, det_exc)
        except BaseException:
            try:
                eff_scope.close_scoped_stack_recorded()
            finally:
                session_stack.close_all_lifo()
            raise

        teardown_diags = session_stack.close_all_lifo()
        return TurnExecutionReport(
            turn_id=report.turn_id,
            primary_result=report.primary_result,
            event_diagnostics=report.event_diagnostics,
            teardown_diagnostics=(*report.teardown_diagnostics, *teardown_diags),
            fatal_event_error=report.fatal_event_error,
        )


def _validate_warmup_hooks_map(
    warmup_hooks: Optional[Mapping[ModuleId, Callable[[], None]]],
) -> tuple[tuple[ModuleId, Callable[[], None]], ...]:
    if warmup_hooks is None:
        return ()
    if not isinstance(warmup_hooks, Mapping):
        raise ValueError("warmup_hooks must be a Mapping[ModuleId, Callable[[], None]].")
    items = tuple(warmup_hooks.items())
    for mod_id, hook_fn in items:
        if not isinstance(mod_id, ModuleId) or not callable(hook_fn):
            raise ValueError(f"Invalid warmup_hooks entry: {(mod_id, hook_fn)!r}")
    return items


class WorkerContainerLifecycle:
    """Single source of truth for persistent container state and module degradation."""

    def __init__(self, *, quiesce_probe: Optional[Callable[[], bool]] = None) -> None:
        if quiesce_probe is not None and not callable(quiesce_probe):
            raise ValueError("quiesce_probe must be callable or None.")
        self._lock = threading.RLock()
        self._stop_done = threading.Event()
        self._draining_tid: Optional[int] = None
        self._state = ContainerState.UNINITIALIZED
        self._quiesced_flag = False
        self._quiesce_probe = quiesce_probe
        self._container_stack = LifoResourceStack()
        self._degraded: dict[ModuleId, ErrorDetail] = {}
        self._index_degraded: dict[ModuleId, ErrorDetail] = {}

    @property
    def state(self) -> ContainerState:
        with self._lock:
            base = self._state
            manual_q = self._quiesced_flag
        if base in (ContainerState.DRAINING, ContainerState.STOPPED):
            return base
        if manual_q or (self._quiesce_probe is not None and bool(self._quiesce_probe())):
            return ContainerState.QUIESCED
        return base

    @property
    def degraded_modules(self) -> Mapping[ModuleId, ErrorDetail]:
        with self._lock:
            return {**self._index_degraded, **self._degraded}

    def get_degraded(self, module_id: ModuleId) -> Optional[ErrorDetail]:
        if not isinstance(module_id, ModuleId):
            raise ValueError(f"module_id must be ModuleId, got {module_id!r}")
        with self._lock:
            return self._degraded.get(module_id) or self._index_degraded.get(module_id)

    def get_runtime_degraded(self, module_id: ModuleId) -> Optional[ErrorDetail]:
        if not isinstance(module_id, ModuleId):
            raise ValueError(f"module_id must be ModuleId, got {module_id!r}")
        with self._lock:
            return self._degraded.get(module_id)

    def has_index_degraded(self, module_id: ModuleId) -> bool:
        if not isinstance(module_id, ModuleId):
            raise ValueError(f"module_id must be ModuleId, got {module_id!r}")
        with self._lock:
            return module_id in self._index_degraded

    def snapshot_index_degraded(self) -> dict[ModuleId, ErrorDetail]:
        with self._lock:
            return dict(self._index_degraded)

    @property
    def resource_stack(self) -> LifoResourceStack:
        return self._container_stack

    def record_degraded(self, module_id: ModuleId, detail: ErrorDetail) -> None:
        if not isinstance(module_id, ModuleId) or not isinstance(detail, ErrorDetail):
            raise ValueError("record_degraded requires (ModuleId, ErrorDetail).")
        with self._lock:
            self._degraded[module_id] = detail

    def sync_index_degraded(self, index_errors: Mapping[ModuleId, ErrorDetail]) -> None:
        if not isinstance(index_errors, Mapping):
            raise ValueError("sync_index_degraded requires Mapping[ModuleId, ErrorDetail].")
        validated: dict[ModuleId, ErrorDetail] = {}
        for mid, det in index_errors.items():
            if not isinstance(mid, ModuleId) or not isinstance(det, ErrorDetail):
                raise ValueError("sync_index_degraded entries must be (ModuleId, ErrorDetail).")
            validated[mid] = det
        with self._lock:
            self._index_degraded = validated

    def clear_degraded(self, modules: Optional[frozenset[ModuleId]] = None) -> None:
        checked_mods = require_typed_frozenset(modules, ModuleId, "modules") if modules is not None else None
        with self._lock:
            if checked_mods is None:
                self._degraded.clear()
                self._index_degraded.clear()
            else:
                for m in checked_mods:
                    self._degraded.pop(m, None)
                    self._index_degraded.pop(m, None)

    def warmup(
        self,
        warmup_hooks: Optional[Mapping[ModuleId, Callable[[], None]]] = None,
    ) -> None:
        hook_items = _validate_warmup_hooks_map(warmup_hooks)
        prev_state: Optional[ContainerState] = None
        with self._lock:
            if self._state in (ContainerState.DRAINING, ContainerState.STOPPED):
                return
            if self._state in (ContainerState.UNINITIALIZED, ContainerState.BOOTING):
                prev_state = self._state
                self._state = ContainerState.WARMING

        try:
            for mod_id, hook_fn in hook_items:
                if self._is_stopping():
                    break
                self._run_single_warmup_hook(mod_id, hook_fn)
        except BaseException:
            with self._lock:
                if self._state == ContainerState.WARMING and prev_state is not None:
                    self._state = prev_state
            raise
        with self._lock:
            if self._state == ContainerState.WARMING:
                self._state = ContainerState.READY

    def _is_stopping(self) -> bool:
        with self._lock:
            return self._state in (ContainerState.DRAINING, ContainerState.STOPPED)

    def _run_single_warmup_hook(
        self,
        mod_id: ModuleId,
        hook_fn: Callable[[], None],
    ) -> None:
        try:
            hook_fn()
            with self._lock:
                if self._state not in (ContainerState.DRAINING, ContainerState.STOPPED):
                    self._degraded.pop(mod_id, None)
        except YscbError as exc:
            with self._lock:
                self._degraded[mod_id] = exc.detail
        except (Exception, SystemExit, GeneratorExit) as exc:
            with self._lock:
                self._degraded[mod_id] = ErrorDetail(
                    code=ErrorCode.MODULE_DEGRADED,
                    message=f"Module '{mod_id}' warmup failed: {safe_exception_summary(exc)}",
                    source_task=None,
                )

    def begin_hot_turn(
        self,
        kind: TurnKind,
        *,
        cancel_token: Optional[CancellationToken] = None,
        turn_id: Optional[str] = None,
    ) -> Optional[TurnScope]:
        if turn_id is not None:
            require_pure_str(turn_id, "turn_id", non_empty=True)
        if not isinstance(kind, TurnKind):
            raise ValueError(f"kind must be TurnKind, got {kind!r}")
        if cancel_token is not None and not isinstance(cancel_token, CancellationToken):
            raise ValueError(f"cancel_token must be CancellationToken or None, got {cancel_token!r}")
        with self._lock:
            if self._state in (ContainerState.DRAINING, ContainerState.STOPPED):
                return None
        return TurnScope(
            turn_id=turn_id or uuid.uuid4().hex,
            kind=kind,
            cancel_token=cancel_token or CancellationToken(),
        )

    def quiesce(self) -> None:
        with self._lock:
            if self._state not in (ContainerState.DRAINING, ContainerState.STOPPED):
                self._quiesced_flag = True

    def resume(self) -> None:
        with self._lock:
            self._quiesced_flag = False

    def reload_modules(self, modules: Optional[frozenset[ModuleId]] = None) -> None:
        self.clear_degraded(modules)
        with self._lock:
            if self._state in (ContainerState.UNINITIALIZED, ContainerState.BOOTING):
                self._state = ContainerState.READY

    def drain_and_stop(
        self,
        grace_period_ms: int = 3000,
        *,
        on_drain: Optional[Callable[[int], None]] = None,
    ) -> tuple[ErrorDetail, ...]:
        require_pure_int(grace_period_ms, "grace_period_ms", min_val=0, max_val=None)
        safe_grace_ms = min(max(0, grace_period_ms), MAX_TIMEOUT_MS)
        cur_tid = threading.get_ident()
        wait_existing = False
        with self._lock:
            if self._state == ContainerState.STOPPED:
                return ()
            if self._state == ContainerState.DRAINING:
                if self._draining_tid == cur_tid:
                    return ()
                wait_existing = True
            else:
                self._state = ContainerState.DRAINING
                self._draining_tid = cur_tid
        if wait_existing:
            self._stop_done.wait(timeout=ms_to_safe_sec(safe_grace_ms, min_sec=0.05) + 5.0)
            return ()
        drain_err: Optional[ErrorDetail] = None
        stack_diags: tuple[ErrorDetail, ...] = ()
        try:
            if on_drain is not None:
                on_drain(safe_grace_ms)
        except (Exception, SystemExit, GeneratorExit) as exc:
            drain_err = ErrorDetail(ErrorCode.TEARDOWN_ERROR, f"Container drain hook failed: {safe_exception_summary(exc)}")
        finally:
            try:
                stack_diags = self._container_stack.close_all_lifo()
            finally:
                with self._lock:
                    self._state = ContainerState.STOPPED
                    self._draining_tid = None
                self._stop_done.set()
        return (drain_err, *stack_diags) if drain_err is not None else stack_diags
