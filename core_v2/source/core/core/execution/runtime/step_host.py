"""Isolated Tier 0 and Tier 1 step execution, equivalence key evaluation, and outcome translation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import threading
from typing import Callable, Optional, Sequence, TypeVar
import uuid

from core.execution.lifecycle import (
    StepExecutionResult,
    TurnExecutionReport,
    TurnKind,
    TurnScope,
    WorkerContainerLifecycle,
)
from core.execution.rpc import InboundCallHandler, RemoteCallOutcome
from core.execution.runtime.contracts import (
    ClientRoutingPolicy,
    InvokeRequest,
    ModuleDescriptor,
    TaskOutcome,
    TaskRouteSpec,
)
from core.execution.runtime.coordinator import PriorityHandle
from core.execution.runtime.gates import LifecycleReloadGate, compute_coalesce_context_suffix
from core.execution.runtime.module_slot import (
    LocalStepExecutionSpec,
    StepContextCallbacks,
)
from core.execution.runtime.route_index import RouteIndexRegistry
from core.execution.runtime.turn_session import ActiveStepBinding, TurnSessionRegistry, merge_deadlines
from core.execution.runtime.wire import (
    DaemonRpcInvokeReply,
    EmittedEventHop,
    WorkerCallbackContext,
    WorkerCallbackEnvelope,
    WorkerCallbackReply,
    WorkerCommandEnvelope,
    WorkerCommandKind,
    WorkerEquivReply,
    WorkerMapBatchReply,
    WorkerStepReply,
)
from core.execution.runtime.worker_pool import HotWorkerPool, WorkerCallSpec
from core.foundation.codec import DataclassCodec
from core.foundation.errors import ErrorCode, ErrorDetail, TaskCancelledException, YscbError, safe_exception_summary
from core.foundation.observability import MAX_SAFE_WAIT_SEC, CancellationToken, DeadlineGuard, ms_to_safe_sec
from core.foundation.primitives import EventId, HostPath, JsonObject, JsonValue, TaskId, invoke_observer_safely, require_non_none

_TIER0_CANCEL_GRACE_SEC = 0.20
_TRes = TypeVar("_TRes")


@dataclass(frozen=True, slots=True)
class RawInvokeResult:
    outcome: TaskOutcome[JsonValue]
    invoked_tasks: tuple[tuple[HostPath, TaskId], ...] = ()
    emitted_hops: tuple[EmittedEventHop, ...] = ()


@dataclass(frozen=True, slots=True)
class StepExecutionEnv:
    desc: ModuleDescriptor
    spec: TaskRouteSpec
    step_req: InvokeRequest
    turn: TurnScope
    step_cancel: CancellationToken
    on_progress: Optional[Callable[[JsonObject], None]]
    step_guard: DeadlineGuard = field(default_factory=DeadlineGuard)
    dynamic_deadline_fn: Optional[Callable[[], Optional[float]]] = None
    reload_epoch: int = 0

    def current_guard(self) -> DeadlineGuard:
        dl = merge_deadlines(
            self.step_guard.deadline,
            self.dynamic_deadline_fn() if self.dynamic_deadline_fn is not None else None,
        )
        return DeadlineGuard(cancel_token=self.step_cancel, deadline=dl)


@dataclass(frozen=True, slots=True)
class EquivCallContext:
    turn: Optional[TurnScope] = None
    call_tree_id: str = ""
    is_nested: bool = False
    cancel_token: Optional[CancellationToken] = None
    bypass_reload: bool = False
    guard: DeadlineGuard = field(default_factory=DeadlineGuard)


class WorkerCallbackBridge(InboundCallHandler):
    """Private reverse-callback handler isolating Tier 1 worker IPC from public RuntimeDispatcher surface."""

    def __init__(
        self,
        dispatch_fn: Callable[[WorkerCallbackEnvelope, CancellationToken], WorkerCallbackReply],
    ) -> None:
        self._dispatch_fn = dispatch_fn

    def on_call(
        self,
        stream_id: int,
        payload: JsonObject,
        ack_accepted: Callable[[], bool],
        emit_progress: Callable[[JsonObject], None],
        peer_cancel_token: CancellationToken,
    ) -> tuple[bool, JsonObject]:
        _ = (stream_id, emit_progress)
        try:
            env = DataclassCodec.decode_envelope(WorkerCallbackEnvelope, payload)
        except YscbError as exc:
            return (False, DataclassCodec.encode_envelope(WorkerCallbackReply(ok=False, error=exc.detail)))
        if not ack_accepted():
            return (False, {"ok": False})
        reply = self._dispatch_fn(env, peer_cancel_token)
        return (True, DataclassCodec.encode_envelope(reply))



class Tier0HostExitCoordinator:
    """Ensures exit_host_step and release_turn_session fire strictly once after lingering yscb-t0 finishes."""

    def __init__(self, cleanup_fn: Callable[[], object]) -> None:
        self._cleanup_fn = cleanup_fn
        self._lock = threading.Lock()
        self._spawned = False
        self._worker_done = False
        self._caller_detached = False

    def mark_worker_spawned(self) -> None:
        with self._lock:
            self._spawned = True

    def rollback_unspawned(self) -> None:
        with self._lock:
            self._spawned = False

    def worker_exit(self) -> None:
        with self._lock:
            self._worker_done = True
            run_now = self._caller_detached
        if run_now:
            self._cleanup_fn()

    def caller_exit(self) -> None:
        with self._lock:
            if self._spawned and not self._worker_done:
                self._caller_detached = True
                return
        self._cleanup_fn()


def cancelled_task_outcome(token: CancellationToken, source_task: Optional[str]) -> TaskOutcome[JsonValue]:
    c_code = ErrorCode.TASK_PREEMPTED if token.is_preempted else ErrorCode.TASK_CANCELLED
    return TaskOutcome(
        ok=False,
        error=ErrorDetail(code=c_code, message=token.reason or "Task cancelled", source_task=source_task),
    )


def safe_invoke_progress(cb: Optional[Callable[[JsonObject], None]], payload: JsonObject) -> None:
    if cb is not None:
        invoke_observer_safely(lambda: cb(payload))


def default_nested_routing_policy(is_cross_ws: bool, parent_policy: ClientRoutingPolicy) -> ClientRoutingPolicy:
    if is_cross_ws:
        return ClientRoutingPolicy.AUTO_NO_SPAWN
    if parent_policy == ClientRoutingPolicy.FORCE_COLD:
        return ClientRoutingPolicy.FORCE_COLD
    return ClientRoutingPolicy.AUTO_SPAWN


def decode_tier1_mapper_outcome(
    out: RemoteCallOutcome,
    eff_cancel: CancellationToken,
    task_id: TaskId,
) -> WorkerMapBatchReply:
    if eff_cancel.is_cancelled and out.result_payload is None:
        c_code = ErrorCode.TASK_PREEMPTED if eff_cancel.is_preempted else ErrorCode.TASK_CANCELLED
        return WorkerMapBatchReply(
            ok=False, error=ErrorDetail(c_code, eff_cancel.reason or c_code.value, source_task=str(task_id))
        )
    if out.transport_lost:
        return WorkerMapBatchReply(
            ok=False, error=ErrorDetail(ErrorCode.WORKER_CRASHED, f"Mapper worker crashed for {task_id}", source_task=str(task_id))
        )
    if out.error_code is not None:
        return WorkerMapBatchReply(
            ok=False, error=ErrorDetail(out.error_code, out.error_message or out.error_code.value, source_task=str(task_id))
        )
    if out.result_payload is None:
        return WorkerMapBatchReply(
            ok=False, error=ErrorDetail(ErrorCode.WORKER_CRASHED, f"Mapper worker failed for {task_id}", source_task=str(task_id))
        )
    try:
        reply = DataclassCodec.decode_envelope(WorkerMapBatchReply, out.result_payload)
    except YscbError as exc:
        return WorkerMapBatchReply(ok=False, error=exc.detail.with_fallback_task(str(task_id)))
    if not reply.ok:
        err = (reply.error or ErrorDetail(ErrorCode.BUSINESS_FAILURE, "Mapper error")).with_fallback_task(str(task_id))
        return WorkerMapBatchReply(ok=False, error=err)
    return reply


def _map_unaccepted_daemon_rpc_outcome(
    outcome: RemoteCallOutcome,
    cancel_token: CancellationToken,
    fallback_task: str,
) -> Optional[TaskOutcome[JsonValue]]:
    if cancel_token.is_cancelled:
        return cancelled_task_outcome(cancel_token, fallback_task)
    if outcome.error_code in (
        ErrorCode.CODEC_VALIDATION_FAILED,
        ErrorCode.PAYLOAD_TOO_LARGE,
        ErrorCode.TASK_CANCELLED,
        ErrorCode.TASK_PREEMPTED,
        ErrorCode.TASK_TIMEOUT,
    ):
        return TaskOutcome(
            ok=False,
            error=ErrorDetail(
                code=outcome.error_code,
                message=outcome.error_message or outcome.error_code.value,
                source_task=fallback_task,
            ),
        )
    return None


def translate_remote_daemon_outcome(
    outcome: Optional[RemoteCallOutcome],
    cancel_token: CancellationToken,
    fallback_task: str,
) -> Optional[RawInvokeResult]:
    if outcome is None:
        return RawInvokeResult(cancelled_task_outcome(cancel_token, fallback_task)) if cancel_token.is_cancelled else None
    if not outcome.was_accepted:
        unacc = _map_unaccepted_daemon_rpc_outcome(outcome, cancel_token, fallback_task)
        return RawInvokeResult(unacc) if unacc is not None else None
    if outcome.transport_lost:
        return RawInvokeResult(
            TaskOutcome(
                ok=False,
                error=ErrorDetail(
                    code=ErrorCode.TRANSPORT_LOST,
                    message=outcome.error_message
                    or "Daemon connection lost after CALL_ACCEPTED; refusing automatic re-run.",
                    source_task=fallback_task,
                ),
                executed_hot=True,
            )
        )
    if outcome.error_code is not None:
        return RawInvokeResult(
            TaskOutcome(
                ok=False,
                error=ErrorDetail(
                    code=outcome.error_code,
                    message=outcome.error_message or outcome.error_code.value,
                    source_task=fallback_task,
                ),
                executed_hot=True,
            )
        )
    if outcome.result_payload is None:
        return None
    try:
        reply = DataclassCodec.decode_envelope(DaemonRpcInvokeReply, outcome.result_payload)
    except YscbError as exc:
        return RawInvokeResult(TaskOutcome(ok=False, error=exc.detail.with_fallback_task(fallback_task), executed_hot=True))
    err = reply.error.with_fallback_task(fallback_task) if reply.error is not None else None
    return RawInvokeResult(
        TaskOutcome(
            ok=reply.ok,
            value=reply.raw_value,
            error=err,
            event_diagnostics=reply.event_diagnostics,
            teardown_diagnostics=reply.teardown_diagnostics,
            coalesced=reply.coalesced,
            executed_hot=True,
        ),
        reply.invoked_tasks,
        reply.emitted_hops,
    )


def _step_reply_to_result(task_id: TaskId, reply: WorkerStepReply) -> StepExecutionResult[JsonValue]:
    if reply.ok:
        return StepExecutionResult(ok=True, outcome=reply.raw_output, committed_events=reply.committed_events)
    err = (reply.error or ErrorDetail(ErrorCode.BUSINESS_FAILURE, f"Step {task_id} failed")).with_fallback_task(
        str(task_id)
    )
    return StepExecutionResult(
        ok=False,
        error=err,
        preempted=reply.preempted,
        fatal_abort_turn=reply.fatal_abort_turn,
        committed_events=reply.committed_events,
    )


def map_tier1_remote_outcome(
    task_id: TaskId,
    out: RemoteCallOutcome,
    step_cancel: CancellationToken,
) -> tuple[StepExecutionResult[JsonValue], tuple[ErrorDetail, ...]]:
    decoded_reply: Optional[WorkerStepReply] = None
    if out.error_code is None and not out.transport_lost and out.result_payload is not None:
        try:
            decoded_reply = DataclassCodec.decode_envelope(WorkerStepReply, out.result_payload)
        except YscbError as exc:
            return (StepExecutionResult(ok=False, error=exc.detail.with_fallback_task(str(task_id))), ())
        if decoded_reply.fatal_abort_turn:
            return (_step_reply_to_result(task_id, decoded_reply), decoded_reply.teardown_diagnostics)
    if step_cancel.is_cancelled and out.error_code not in (ErrorCode.TASK_TIMEOUT, ErrorCode.PAYLOAD_TOO_LARGE):
        code = ErrorCode.TASK_PREEMPTED if step_cancel.is_preempted else ErrorCode.TASK_CANCELLED
        td = decoded_reply.teardown_diagnostics if decoded_reply is not None else ()
        return (
            StepExecutionResult(
                ok=False,
                preempted=step_cancel.is_preempted,
                error=ErrorDetail(code=code, message=step_cancel.reason or "Step cancelled", source_task=str(task_id)),
            ),
            td,
        )
    if out.error_code is not None:
        return (
            StepExecutionResult(
                ok=False,
                preempted=(out.error_code == ErrorCode.TASK_PREEMPTED),
                error=ErrorDetail(
                    code=out.error_code,
                    message=out.error_message or out.error_code.value,
                    source_task=str(task_id),
                ),
            ),
            (),
        )
    if decoded_reply is None:
        code = ErrorCode.TRANSPORT_LOST if out.was_accepted else ErrorCode.WORKER_CRASHED
        return (
            StepExecutionResult(
                ok=False,
                error=ErrorDetail(code=code, message="Tier 1 worker connection lost", source_task=str(task_id)),
            ),
            (),
        )
    return (_step_reply_to_result(task_id, decoded_reply), decoded_reply.teardown_diagnostics)


def report_to_outcome(
    report: TurnExecutionReport,
    *,
    is_hot: bool,
    fallback_task: str,
) -> TaskOutcome[JsonValue]:
    if report.fatal_event_error is not None:
        ferr = (
            report.fatal_event_error.with_fallback_task(fallback_task)
            if fallback_task
            else report.fatal_event_error
        )
        return TaskOutcome(
            ok=False,
            error=ferr,
            event_diagnostics=report.event_diagnostics,
            teardown_diagnostics=report.teardown_diagnostics,
            coalesced=report.primary_result.coalesced,
            executed_hot=is_hot,
        )
    prim = report.primary_result
    if not prim.ok:
        perr = prim.error.with_fallback_task(fallback_task) if (prim.error is not None and fallback_task) else prim.error
        return TaskOutcome(
            ok=False,
            error=perr,
            event_diagnostics=report.event_diagnostics,
            teardown_diagnostics=report.teardown_diagnostics,
            coalesced=prim.coalesced,
            executed_hot=is_hot,
        )
    return TaskOutcome(
        ok=True,
        value=prim.outcome,
        event_diagnostics=report.event_diagnostics,
        teardown_diagnostics=report.teardown_diagnostics,
        coalesced=prim.coalesced,
        executed_hot=is_hot,
    )


def _wait_tier0_done_or_cancel(
    done_ev: threading.Event,
    wake_ev: threading.Event,
    step_cancel: CancellationToken,
    timeout_sec: Optional[float],
) -> bool:
    safe_tmo = min(MAX_SAFE_WAIT_SEC, max(0.0, timeout_sec)) if timeout_sec is not None else None
    unreg = step_cancel.register_callback(lambda _p, _r: wake_ev.set())
    try:
        if not done_ev.is_set() and not step_cancel.is_cancelled:
            wake_ev.wait(timeout=safe_tmo)
        if done_ev.is_set():
            return True
        if step_cancel.is_cancelled:
            rem_g = (
                _TIER0_CANCEL_GRACE_SEC
                if timeout_sec is None
                else min(_TIER0_CANCEL_GRACE_SEC, max(0.01, timeout_sec))
            )
            done_ev.wait(timeout=rem_g)
        return done_ev.is_set()
    finally:
        unreg()


def _run_tier0_bounded(
    fn: Callable[[], _TRes],
    guard: DeadlineGuard,
    cancel_token: CancellationToken,
    default_timeout_ms: int,
    task_id: TaskId,
    label: str,
) -> _TRes:
    tmo_ms = guard.remaining_ms(default_timeout_ms, expired_message=f"{label} timed out for '{task_id}'")
    done_ev = threading.Event()
    wake_ev = threading.Event()
    outcome_box: list[_TRes] = []
    err_box: list[BaseException] = []

    def _worker() -> None:
        try:
            outcome_box.append(fn())
        except BaseException as exc:
            err_box.append(exc)
        finally:
            done_ev.set()
            wake_ev.set()

    threading.Thread(target=_worker, name=f"yscb-t0-{label}-{task_id}", daemon=True).start()
    finished = _wait_tier0_done_or_cancel(done_ev, wake_ev, cancel_token, ms_to_safe_sec(tmo_ms))
    if not finished:
        if cancel_token.is_cancelled:
            code = ErrorCode.TASK_PREEMPTED if cancel_token.is_preempted else ErrorCode.TASK_CANCELLED
            raise TaskCancelledException(
                ErrorDetail(code, cancel_token.reason or f"{label} cancelled", source_task=str(task_id))
            )
        raise YscbError(
            ErrorCode.TASK_TIMEOUT,
            f"{label} timed out after {tmo_ms}ms for '{task_id}'",
            source_task=str(task_id),
        )
    if err_box:
        raise err_box[0]
    return outcome_box[0]


def _handle_unfinished_tier0_step(
    spec: TaskRouteSpec,
    turn: TurnScope,
    done_ev: threading.Event,
    step_cancel: CancellationToken,
) -> tuple[StepExecutionResult[JsonValue], Optional[threading.Event]]:
    was_cancelled = step_cancel.is_cancelled
    if not was_cancelled:
        step_cancel.cancel(reason=f"Timed out after {spec.timeout_ms}ms")
        done_ev.wait(timeout=0.03)
    if not done_ev.is_set() and turn.kind == TurnKind.COLD:
        turn.scoped_stack.push_closeable(f"t0_join.{spec.task_id}", lambda: (done_ev.wait(timeout=3.0), None)[1])
    if was_cancelled:
        code = ErrorCode.TASK_PREEMPTED if step_cancel.is_preempted else ErrorCode.TASK_CANCELLED
        return (
            StepExecutionResult(
                ok=False,
                preempted=step_cancel.is_preempted,
                error=ErrorDetail(code, step_cancel.reason or "Step cancelled", source_task=str(spec.task_id)),
            ),
            None if done_ev.is_set() else done_ev,
        )
    return (
        StepExecutionResult(
            ok=False,
            error=ErrorDetail(
                ErrorCode.TASK_TIMEOUT,
                f"Task '{spec.task_id}' timed out after {spec.timeout_ms}ms",
                source_task=str(spec.task_id),
            ),
        ),
        None if done_ev.is_set() else done_ev,
    )


def _finalize_tier0_reply(
    task_id: TaskId,
    reply: WorkerStepReply,
    step_cancel: CancellationToken,
) -> StepExecutionResult[JsonValue]:
    if reply.fatal_abort_turn:
        return _step_reply_to_result(task_id, reply)
    if step_cancel.is_cancelled:
        code = ErrorCode.TASK_PREEMPTED if step_cancel.is_preempted else ErrorCode.TASK_CANCELLED
        return StepExecutionResult(
            ok=False,
            preempted=step_cancel.is_preempted,
            error=ErrorDetail(code=code, message=step_cancel.reason or "Step cancelled", source_task=str(task_id)),
        )
    return _step_reply_to_result(task_id, reply)


class StepHostRunner:
    """Executes isolated Tier 0/1 steps, equivalence evaluations, and event batch mappings."""

    def __init__(
        self,
        *,
        is_daemon_host: bool,
        tier1_pool: HotWorkerPool,
        container: WorkerContainerLifecycle,
        gates: LifecycleReloadGate,
        routes: RouteIndexRegistry,
        sessions: TurnSessionRegistry,
    ) -> None:
        self._is_daemon_host = is_daemon_host
        self._tier1_pool = tier1_pool
        self._container = container
        self._gates = gates
        self._routes = routes
        self._sessions = sessions

    def dispatch_to_host(
        self,
        env: StepExecutionEnv,
        priority_getter: PriorityHandle,
        effective_cancel: CancellationToken,
        callbacks_factory: Callable[[StepExecutionEnv, PriorityHandle], StepContextCallbacks],
        *,
        forbid_retiring_wait: bool = False,
    ) -> tuple[StepExecutionResult[JsonValue], Optional[threading.Event]]:
        attempt_cancel, detach_attempt = CancellationToken.combine(effective_cancel)
        active_env = replace(
            env,
            step_cancel=attempt_cancel,
            step_guard=DeadlineGuard(cancel_token=attempt_cancel, deadline=env.step_guard.deadline),
        )
        tid = active_env.turn.turn_id
        ctree = active_env.step_req.propagation.call_tree_id or tid
        mod_id = active_env.desc.module_id
        self._sessions.get_or_bind_turn_session(active_env.turn, retain=True)
        self._gates.enter_host_step(mod_id, tid, ctree)

        def _on_host_step_exit() -> None:
            self._gates.exit_host_step(mod_id, tid, ctree)
            self._sessions.release_turn_session(tid)

        exit_coord = Tier0HostExitCoordinator(_on_host_step_exit)
        host_ok = False
        try:
            if active_env.desc.venv_python is None:
                res, gev = self._run_tier0_step(active_env, priority_getter, exit_coord, callbacks_factory)
            else:
                res, gev = self._run_tier1_step(
                    active_env, priority_getter, forbid_retiring_wait=forbid_retiring_wait
                )
            host_ok = res.ok
            return (res, gev)
        finally:
            detach_attempt()
            if not host_ok and not attempt_cancel.is_cancelled:
                attempt_cancel.cancel(reason="Host step terminated")
            exit_coord.caller_exit()

    def is_reentrant_retiring(self, req: InvokeRequest) -> bool:
        prop = req.propagation
        return self._routes.is_reentrant_retiring_for_module(
            req.task_id,
            self._tier1_pool.has_reentrant_retiring_turn,
            prop.turn_id or "",
            prop.call_tree_id or "",
            tuple((c.turn_id, c.call_tree_id) for c in prop.coalesce_callers),
        )

    def _run_tier0_step(
        self,
        env: StepExecutionEnv,
        priority_getter: PriorityHandle,
        exit_coord: Tier0HostExitCoordinator,
        callbacks_factory: Callable[[StepExecutionEnv, PriorityHandle], StepContextCallbacks],
    ) -> tuple[StepExecutionResult[JsonValue], Optional[threading.Event]]:
        spec, step_req, turn, step_cancel = env.spec, env.step_req, env.turn, env.step_cancel
        if spec.timeout_ms is not None and spec.timeout_ms <= 0:
            return (StepExecutionResult(ok=False, error=ErrorDetail(ErrorCode.TASK_TIMEOUT, "Step timed out immediately")), None)
        local_spec = LocalStepExecutionSpec(
            task_id=spec.task_id,
            raw_input=step_req.raw_input,
            caller_cwd=step_req.caller_cwd,
            caller_env=step_req.caller_env,
            base_lineage=step_req.propagation.lineage,
            cancel_token=step_cancel,
            priority_getter=priority_getter,
            callbacks=callbacks_factory(env, priority_getter),
            interactive_tty=spec.interactive_tty,
        )
        slots = self._sessions.slots_for_turn(turn)
        try:
            eff_tmo = env.step_guard.remaining_ms(spec.timeout_ms)
        except YscbError as exc:
            return (StepExecutionResult(ok=False, error=exc.detail.with_fallback_task(str(spec.task_id))), None)
        if eff_tmo is not None and eff_tmo <= 0:
            return (
                StepExecutionResult(
                    ok=False,
                    error=ErrorDetail(ErrorCode.TASK_TIMEOUT, "Step timed out immediately", source_task=str(spec.task_id)),
                ),
                None,
            )

        holder: list[WorkerStepReply] = []
        escaped_base: list[BaseException] = []
        done_ev = threading.Event()
        wake_ev = threading.Event()

        def _worker_main() -> None:
            try:
                rep_w = slots.execute_step_locally(local_spec)
                holder.append(rep_w)
                self._sessions.record_step_teardown_diags(turn, rep_w.teardown_diagnostics)
            except BaseException as base_exc:
                escaped_base.append(base_exc)
            finally:
                done_ev.set()
                wake_ev.set()
                exit_coord.worker_exit()

        exit_coord.mark_worker_spawned()
        try:
            threading.Thread(target=_worker_main, name=f"yscb-t0-{spec.task_id}", daemon=True).start()
        except BaseException:
            exit_coord.rollback_unspawned()
            raise
        tmo_sec = ms_to_safe_sec(eff_tmo) if eff_tmo is not None else None
        if not _wait_tier0_done_or_cancel(done_ev, wake_ev, step_cancel, tmo_sec):
            return _handle_unfinished_tier0_step(replace(spec, timeout_ms=eff_tmo), turn, done_ev, step_cancel)
        if not holder:
            msg = safe_exception_summary(escaped_base[0]) if escaped_base else "Tier 0 worker exited without reply"
            err = ErrorDetail(ErrorCode.BUSINESS_FAILURE, msg, source_task=str(spec.task_id))
            return (StepExecutionResult(ok=False, error=err), None)
        return (_finalize_tier0_reply(spec.task_id, holder[0], step_cancel), None)

    def _run_tier1_step(
        self,
        env: StepExecutionEnv,
        priority_getter: PriorityHandle,
        *,
        forbid_retiring_wait: bool,
    ) -> tuple[StepExecutionResult[JsonValue], Optional[threading.Event]]:
        desc, spec, step_req, turn, step_cancel = env.desc, env.spec, env.step_req, env.turn, env.step_cancel
        try:
            eff_tmo = env.step_guard.remaining_ms(spec.timeout_ms)
        except YscbError as exc:
            return (StepExecutionResult(ok=False, error=exc.detail.with_fallback_task(str(spec.task_id))), None)
        prop = step_req.propagation
        srid = uuid.uuid4().hex
        ctree = prop.call_tree_id or turn.turn_id
        cb_ctx = WorkerCallbackContext(
            propagation=replace(prop, turn_id=turn.turn_id, call_tree_id=ctree),
            caller_cwd=step_req.caller_cwd,
            caller_env=step_req.caller_env,
            parent_routing_policy=step_req.routing_policy,
            step_run_id=srid,
        )
        cmd = WorkerCommandEnvelope(
            action=WorkerCommandKind.RUN_STEP,
            step_run_id=srid,
            task_id=spec.task_id,
            raw_input=step_req.raw_input,
            caller_cwd=step_req.caller_cwd,
            caller_env=step_req.caller_env,
            lineage=prop.lineage,
            priority=priority_getter(),
            interactive_tty=spec.interactive_tty,
            callback_context=cb_ctx,
        )
        parent_req = replace(step_req, propagation=replace(prop, call_stack=prop.call_stack[:-1]))
        call_spec = WorkerCallSpec(
            group_descriptors=self._routes.collect_group_descriptors(desc),
            command=cmd,
            on_progress=env.on_progress,
            cancel_token=step_cancel,
            priority_handle=priority_getter,
            timeout_ms=eff_tmo,
            inherit_tty=(spec.interactive_tty and turn.kind == TurnKind.COLD),
            turn_id=turn.turn_id,
            call_tree_id=ctree,
            forbid_retiring_wait=forbid_retiring_wait,
            bypass_reload_gate=self._gates.is_request_reload_exempt(parent_req, self.is_reentrant_retiring),
        )
        step_bind = ActiveStepBinding(
            cancel_token=step_cancel,
            prio_handle=priority_getter,
            approval_scope=step_req.approval_scope,
            allow_conditional=step_req.allow_conditional,
            deadline_fn=lambda: env.current_guard().deadline,
        )
        self._sessions.bind_active_step(srid, step_bind)
        try:
            out, release_guard = (
                self._sessions.cold_venv_for_turn(turn).run_once_with_guard(call_spec, turn.scoped_stack)
                if turn.kind == TurnKind.COLD
                else self._tier1_pool.call_worker_with_guard(call_spec)
            )
        finally:
            self._sessions.unbind_active_step(srid)
        step_res, td_diags = map_tier1_remote_outcome(spec.task_id, out, step_cancel)
        if step_res.error is not None and step_res.error.code == ErrorCode.MODULE_DEGRADED and turn.kind != TurnKind.COLD:
            self._container.record_degraded(desc.module_id, step_res.error)
        self._sessions.record_step_teardown_diags(turn, td_diags)
        return (step_res, release_guard)

    def map_event_batch(
        self,
        desc: ModuleDescriptor,
        task_id: TaskId,
        event_id: EventId,
        filtered_payloads: Sequence[JsonObject],
        ctx: EquivCallContext,
    ) -> WorkerMapBatchReply:
        turn = require_non_none(ctx.turn)
        eff_ctree = ctx.call_tree_id or turn.turn_id
        with self._gates.host_step_scope(desc.module_id, turn.turn_id, eff_ctree):
            eff_cancel = ctx.cancel_token or turn.cancel_token
            if desc.venv_python is None:
                try:
                    return _run_tier0_bounded(
                        lambda: self._sessions.slots_for_turn(turn).map_batch_locally(task_id, event_id, filtered_payloads),
                        ctx.guard,
                        eff_cancel,
                        10000,
                        task_id,
                        "Event mapper",
                    )
                except TaskCancelledException as exc:
                    if turn.cancel_token.is_cancelled:
                        raise
                    return WorkerMapBatchReply(ok=False, error=exc.detail.with_fallback_task(str(task_id)))
                except YscbError as exc:
                    return WorkerMapBatchReply(ok=False, error=exc.detail.with_fallback_task(str(task_id)))
            cmd = WorkerCommandEnvelope(
                action=WorkerCommandKind.MAP_BATCH,
                task_id=task_id,
                event_id=event_id,
                event_payloads=tuple(filtered_payloads),
            )
            bypass_rel = self._gates.has_turn_or_tree_exempt(turn.turn_id, eff_ctree)
            try:
                map_tmo = ctx.guard.remaining_ms(10000)
            except YscbError as exc:
                return WorkerMapBatchReply(ok=False, error=exc.detail.with_fallback_task(str(task_id)))
            call_spec = WorkerCallSpec(
                group_descriptors=self._routes.collect_group_descriptors(desc),
                command=cmd,
                cancel_token=eff_cancel,
                timeout_ms=map_tmo,
                turn_id=turn.turn_id,
                call_tree_id=eff_ctree,
                bypass_reload_gate=bypass_rel,
            )
            return self._invoke_tier1_mapper(desc, task_id, turn, eff_cancel, call_spec)


    def _invoke_tier1_mapper(
        self,
        desc: ModuleDescriptor,
        task_id: TaskId,
        turn: TurnScope,
        eff_cancel: CancellationToken,
        call_spec: WorkerCallSpec,
    ) -> WorkerMapBatchReply:
        try:
            out = (
                self._sessions.cold_venv_for_turn(turn).run_once_with_guard(call_spec, turn.scoped_stack)[0]
                if turn.kind == TurnKind.COLD
                else self._tier1_pool.call_worker_with_guard(call_spec)[0]
            )
            res_map = decode_tier1_mapper_outcome(out, eff_cancel, task_id)
            if res_map.error is not None and res_map.error.code == ErrorCode.MODULE_DEGRADED and turn.kind != TurnKind.COLD:
                self._container.record_degraded(desc.module_id, res_map.error)
            return res_map
        except TaskCancelledException as exc:
            if turn.cancel_token.is_cancelled:
                raise
            return WorkerMapBatchReply(ok=False, error=exc.detail.with_fallback_task(str(task_id)))
        except YscbError as exc:
            return WorkerMapBatchReply(ok=False, error=exc.detail.with_fallback_task(str(task_id)))
        except (Exception, SystemExit, GeneratorExit) as exc:
            err = ErrorDetail(
                ErrorCode.BUSINESS_FAILURE,
                f"Event mapper failed for {task_id}: {safe_exception_summary(exc)}",
                source_task=str(task_id),
            )
            return WorkerMapBatchReply(ok=False, error=err)

    def compute_isolated_equiv_key(
        self,
        req: InvokeRequest,
        ctx: EquivCallContext,
    ) -> str:
        entry = self._routes.lookup(req.task_id)
        if entry is None:
            base_key = f"{req.task_id}:{DataclassCodec.canonical_hash(req.raw_input)}"
        elif entry[0].venv_python is None:
            base_key = self._compute_tier0_equiv_key(entry[0], req, ctx)
        else:
            base_key = self._compute_tier1_equiv_key(entry[0], req, ctx)
        ctx_suf = compute_coalesce_context_suffix(
            req.caller_cwd, req.caller_env, req.approval_scope, req.allow_conditional
        )
        return f"{base_key}|ctx:{ctx_suf}"

    def _compute_tier0_equiv_key(
        self,
        desc: ModuleDescriptor,
        req: InvokeRequest,
        ctx: EquivCallContext,
    ) -> str:
        turn = ctx.turn
        tid = turn.turn_id if turn is not None else ""
        ctree = ctx.call_tree_id or tid
        eff_tok = ctx.cancel_token or (turn.cancel_token if turn is not None else CancellationToken())
        if self._is_daemon_host and not ctx.bypass_reload and not ctx.is_nested:
            self._gates.wait_if_module_reloading(
                req,
                eff_tok,
                self.is_reentrant_retiring,
                timeout_ms=ctx.guard.remaining_ms(3000),
            )
        with self._gates.host_step_scope(desc.module_id, tid, ctree):
            rep = _run_tier0_bounded(
                lambda: self._sessions.slots_for_turn(turn).compute_equiv_locally(req.task_id, req.raw_input),
                ctx.guard,
                eff_tok,
                3000,
                req.task_id,
                "Equivalence key",
            )
            if not rep.ok or not rep.equiv_key:
                err = rep.error or ErrorDetail(ErrorCode.BUSINESS_FAILURE, f"Equivalence failed for '{req.task_id}'", source_task=str(req.task_id))
                err.raise_as_exception()
            return rep.equiv_key

    def _compute_tier1_equiv_key(
        self,
        desc: ModuleDescriptor,
        req: InvokeRequest,
        ctx: EquivCallContext,
    ) -> str:
        task_id = req.task_id
        out = self._call_hot_tier1_equiv_gated(desc, req, ctx)
        if out.error_code is not None:
            raise YscbError(out.error_code, out.error_message or out.error_code.value, source_task=str(task_id))
        if out.transport_lost or out.result_payload is None:
            raise YscbError(ErrorCode.WORKER_CRASHED, f"Equivalence worker lost for '{task_id}'", source_task=str(task_id))
        rep = DataclassCodec.decode_envelope(WorkerEquivReply, out.result_payload)
        if not rep.ok or not rep.equiv_key:
            err = rep.error or ErrorDetail(ErrorCode.BUSINESS_FAILURE, f"Equivalence failed for '{task_id}'")
            if err.code == ErrorCode.MODULE_DEGRADED and (ctx.turn is None or ctx.turn.kind != TurnKind.COLD):
                self._container.record_degraded(desc.module_id, err)
            raise YscbError(err.code, err.message, remediation=err.remediation, source_task=err.source_task or str(task_id))
        return rep.equiv_key

    def _call_hot_tier1_equiv_gated(
        self,
        desc: ModuleDescriptor,
        req: InvokeRequest,
        ctx: EquivCallContext,
    ) -> RemoteCallOutcome:
        turn = ctx.turn
        tid = turn.turn_id if turn is not None else ""
        ctree = ctx.call_tree_id or tid
        eff_tok = ctx.cancel_token or (turn.cancel_token if turn is not None else None)
        bypass_rel = ctx.bypass_reload or ctx.is_nested or not self._is_daemon_host
        if not bypass_rel:
            self._gates.wait_if_module_reloading(
                req,
                eff_tok or CancellationToken(),
                self.is_reentrant_retiring,
                timeout_ms=ctx.guard.remaining_ms(3000),
            )
            found = self._routes.lookup(req.task_id)
            desc = found[0] if found is not None else desc
        eff_tmo = ctx.guard.remaining_ms(3000)
        with self._gates.host_step_scope(desc.module_id, tid, ctree):
            call_spec = WorkerCallSpec(
                group_descriptors=self._routes.collect_group_descriptors(desc),
                command=WorkerCommandEnvelope(
                    action=WorkerCommandKind.COMPUTE_EQUIV, task_id=req.task_id, raw_input=req.raw_input
                ),
                cancel_token=eff_tok,
                timeout_ms=eff_tmo,
                turn_id=tid,
                call_tree_id=ctree,
                bypass_reload_gate=bypass_rel,
            )
            return self._tier1_pool.call_worker_with_guard(call_spec)[0]
