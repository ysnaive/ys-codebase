"""Tier 1 .venv subprocess RPC command router and entrypoint."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import os
import signal
import sys
import threading
from typing import Callable, Literal, Optional, Sequence

from core.execution.event import CausalLineage
from core.execution.lifecycle import WorkerContainerLifecycle
from core.execution.rpc import (
    FrameKind,
    InboundCallHandler,
    MultiplexedChannel,
    RemoteCallOutcome,
    RpcEndpointInfo,
    connect_and_handshake,
)
from core.execution.runtime.contracts import ClientRoutingPolicy, ExecutionPriority, ModuleDescriptor, TaskOutcome
from core.execution.runtime.module_slot import LocalModuleSlotRegistry, LocalStepExecutionSpec, StepContextCallbacks
from core.execution.runtime.wire import (
    WORKER_AUTH_ENV_KEY,
    WorkerBootstrapConfig,
    WorkerCallbackContext,
    WorkerCallbackEnvelope,
    WorkerCallbackKind,
    WorkerCallbackReply,
    WorkerCommandEnvelope,
    WorkerCommandKind,
    WorkerEquivReply,
    WorkerMapBatchReply,
    WorkerUnloadReply,
    WorkerWarmupReply,
)
from core.foundation.codec import DataclassCodec
from core.foundation.errors import ErrorCode, ErrorDetail, TaskCancelledException, YscbError, safe_exception_summary
from core.foundation.observability import CancellationToken, ms_to_safe_sec
from core.foundation.proc import SignalWakeupGuard
from core.foundation.primitives import (
    IS_WINDOWS,
    EventId,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    TaskId,
    strict_parse_json_object,
)


def _unwrap_emit_imm_callback(cb_out: RemoteCallOutcome, parent_tid: TaskId) -> None:
    if cb_out.error_code in (ErrorCode.TASK_CANCELLED, ErrorCode.TASK_PREEMPTED):
        raise TaskCancelledException(
            cb_out.error_message or "emit_imm cancelled.",
            preempted=(cb_out.error_code == ErrorCode.TASK_PREEMPTED),
            source_task=str(parent_tid),
        )
    if cb_out.error_code is not None:
        ErrorDetail(code=cb_out.error_code, message=cb_out.error_message or cb_out.error_code.value, remediation=cb_out.error_remediation, source_task=cb_out.error_source_task or str(parent_tid)).raise_as_exception()
    if cb_out.transport_lost or cb_out.result_payload is None:
        raise YscbError(ErrorCode.TRANSPORT_LOST, "Master callback channel lost during emit_imm.", source_task=str(parent_tid))
    try:
        rep = DataclassCodec.decode_envelope(WorkerCallbackReply, cb_out.result_payload)
    except YscbError as exc:
        raise YscbError(exc.detail.code, exc.detail.message, source_task=str(parent_tid)) from exc
    if not rep.ok and rep.error is not None:
        rep.error.with_fallback_task(str(parent_tid)).raise_as_exception()


def _unwrap_invoke_task_callback(cb_out: RemoteCallOutcome, child_tid: TaskId) -> TaskOutcome[JsonValue]:
    if cb_out.error_code is not None:
        err_det = ErrorDetail(
            code=cb_out.error_code,
            message=cb_out.error_message or cb_out.error_code.value,
            remediation=cb_out.error_remediation,
            source_task=cb_out.error_source_task or str(child_tid),
        )
        if cb_out.error_code == ErrorCode.CALL_CYCLE_DETECTED:
            err_det.raise_as_exception()
        return TaskOutcome(ok=False, error=err_det)
    if cb_out.transport_lost or cb_out.result_payload is None:
        return TaskOutcome(
            ok=False,
            error=ErrorDetail(ErrorCode.TRANSPORT_LOST, "Master callback channel lost.", source_task=str(child_tid)),
        )
    try:
        rep = DataclassCodec.decode_envelope(WorkerCallbackReply, cb_out.result_payload)
    except YscbError as exc:
        return TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(child_tid)))
    if rep.fatal_abort_turn and rep.error is not None:
        rep.error.raise_as_exception()
    return TaskOutcome(
        ok=rep.ok,
        value=rep.raw_value,
        error=rep.error,
        event_diagnostics=rep.event_diagnostics,
        teardown_diagnostics=rep.teardown_diagnostics,
        coalesced=rep.coalesced,
        executed_hot=rep.executed_hot,
    )


class WorkerSubprocessHandler(InboundCallHandler):
    """Runs inside a Tier 1 .venv Python subprocess with table-driven typed command dispatch."""

    def __init__(
        self,
        workspace_root: HostPath,
        descriptors: Sequence[ModuleDescriptor],
        *,
        is_hot_container: bool = True,
        expect_channel: bool = False,
    ) -> None:
        self._expect_channel = expect_channel
        self._container = WorkerContainerLifecycle()
        self._slots = LocalModuleSlotRegistry(
            workspace_root,
            self._container.resource_stack,
            container=self._container,
            require_eager_start=is_hot_container,
            on_module_initialized=self._notify_runtime_module_initialized,
        )
        self._slots.register_descriptors(descriptors)
        self.channel: Optional[MultiplexedChannel] = None
        self._channel_ready = threading.Event()
        self._prio_lock = threading.Lock()
        self._active_step_priorities: dict[str, ExecutionPriority] = {}
        self._pre_elevated_steps: OrderedDict[str, None] = OrderedDict()
        self._simple_commands: dict[
            WorkerCommandKind,
            Callable[[WorkerCommandEnvelope, Callable[[], bool]], tuple[bool, JsonObject]],
        ] = {
            WorkerCommandKind.WARMUP: self._handle_warmup,
            WorkerCommandKind.UNLOAD_MODULES: self._handle_unload_modules,
            WorkerCommandKind.COMPUTE_EQUIV: self._handle_compute_equiv,
            WorkerCommandKind.MAP_BATCH: self._handle_map_batch,
        }

    def bind_channel(self, ch: MultiplexedChannel) -> None:
        self.channel = ch
        self._channel_ready.set()

    def _require_channel(self) -> MultiplexedChannel:
        if not self._channel_ready.wait(timeout=5.0) or self.channel is None:
            raise YscbError(ErrorCode.TRANSPORT_LOST, "Master callback channel not bound.")
        return self.channel

    def _notify_runtime_module_initialized(self, mod_id: ModuleId) -> None:
        if self._expect_channel and not self._channel_ready.is_set():
            self._channel_ready.wait(timeout=5.0)
        ch = self.channel
        if not self._channel_ready.is_set() or ch is None or ch.is_closed:
            return
        ch.send_control(
            FrameKind.CONTROL_REQUEST,
            {"action": "module_initialized", "module_id": str(mod_id)},
            timeout_ms=2000,
        )

    def close(self, *, grace_ms: int = 1000) -> tuple[ErrorDetail, ...]:
        slot_diags: list[ErrorDetail] = []
        cont_diags = self._container.drain_and_stop(
            grace_period_ms=grace_ms,
            on_drain=lambda rem_ms: slot_diags.extend(
                self._slots.unload_all_modules(grace_sec=ms_to_safe_sec(rem_ms, min_sec=0.05))
            ),
        )
        return (*slot_diags, *cont_diags)

    def on_call(
        self,
        stream_id: int,
        payload: JsonObject,
        ack_accepted: Callable[[], bool],
        emit_progress: Callable[[JsonObject], None],
        peer_cancel_token: CancellationToken,
    ) -> tuple[bool, JsonObject]:
        _ = stream_id
        try:
            cmd = DataclassCodec.decode_envelope(WorkerCommandEnvelope, payload)
        except YscbError:
            ack_accepted()
            raise
        if cmd.action == WorkerCommandKind.RUN_STEP:
            return self._handle_run_step(cmd, ack_accepted, emit_progress, peer_cancel_token)
        simple_fn = self._simple_commands.get(cmd.action)
        if simple_fn is None:
            return (False, {"ok": False})
        return simple_fn(cmd, ack_accepted)

    def _handle_warmup(
        self,
        cmd: WorkerCommandEnvelope,
        ack_accepted: Callable[[], bool],
    ) -> tuple[bool, JsonObject]:
        ack_accepted()
        only_mods = frozenset(cmd.modules) if cmd.modules else None
        hooks = self._slots.warmup_modules(only_mods)
        self._container.warmup(hooks)
        deg_map = self._container.degraded_modules
        reported = {
            str(m): det
            for m, det in deg_map.items()
            if only_mods is None or m in only_mods
        }
        return (True, DataclassCodec.encode_envelope(WorkerWarmupReply(ok=True, degraded=reported)))

    def _handle_unload_modules(
        self,
        cmd: WorkerCommandEnvelope,
        ack_accepted: Callable[[], bool],
    ) -> tuple[bool, JsonObject]:
        ack_accepted()
        fb_mod = str(cmd.modules[0]) if cmd.modules else None
        try:
            diags = self._slots.unload_modules(frozenset(cmd.modules), drain_in_flight=False)
        except (Exception, SystemExit, GeneratorExit) as exc:
            diags = (ErrorDetail(code=ErrorCode.TEARDOWN_ERROR, message=safe_exception_summary(exc), source_task=fb_mod),)
        return (True, DataclassCodec.encode_envelope(WorkerUnloadReply(ok=True, teardown_diagnostics=diags)))

    def _handle_compute_equiv(
        self,
        cmd: WorkerCommandEnvelope,
        ack_accepted: Callable[[], bool],
    ) -> tuple[bool, JsonObject]:
        ack_accepted()
        if cmd.task_id is None:
            err = ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, "COMPUTE_EQUIV requires task_id.")
            return (True, DataclassCodec.encode_envelope(WorkerEquivReply(ok=False, error=err)))
        return (True, DataclassCodec.encode_envelope(self._slots.compute_equiv_locally(cmd.task_id, cmd.raw_input)))

    def _handle_map_batch(
        self,
        cmd: WorkerCommandEnvelope,
        ack_accepted: Callable[[], bool],
    ) -> tuple[bool, JsonObject]:
        ack_accepted()
        if cmd.task_id is None or cmd.event_id is None:
            err = ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, "MAP_BATCH requires task_id and event_id.")
            return (True, DataclassCodec.encode_envelope(WorkerMapBatchReply(ok=False, error=err)))
        rep = self._slots.map_batch_locally(cmd.task_id, cmd.event_id, cmd.event_payloads)
        return (True, DataclassCodec.encode_envelope(rep))

    def _handle_run_step(
        self,
        cmd: WorkerCommandEnvelope,
        ack_accepted: Callable[[], bool],
        emit_progress: Callable[[JsonObject], None],
        peer_cancel_token: CancellationToken,
    ) -> tuple[bool, JsonObject]:
        if cmd.task_id is None or cmd.caller_cwd is None or cmd.callback_context is None:
            ack_accepted()
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                "RUN_STEP requires task_id, caller_cwd, and callback_context.",
            )
        if not ack_accepted():
            return (False, {"ok": False})
        step_run_id = cmd.step_run_id
        if step_run_id:
            with self._prio_lock:
                was_pre_elevated = self._pre_elevated_steps.pop(step_run_id, None) is not None
                self._active_step_priorities[step_run_id] = (
                    ExecutionPriority.FOREGROUND if was_pre_elevated else cmd.priority
                )

        def _live_prio() -> ExecutionPriority:
            if cmd.priority == ExecutionPriority.FOREGROUND or not step_run_id:
                return cmd.priority
            with self._prio_lock:
                return self._active_step_priorities.get(step_run_id, cmd.priority)

        callbacks = self._build_reverse_callbacks(
            cmd.task_id, cmd.callback_context, cmd.lineage, emit_progress, peer_cancel_token
        )
        step_spec = LocalStepExecutionSpec(
            task_id=cmd.task_id,
            raw_input=cmd.raw_input,
            caller_cwd=cmd.caller_cwd,
            caller_env=cmd.caller_env,
            base_lineage=cmd.lineage,
            cancel_token=peer_cancel_token,
            priority_getter=_live_prio,
            callbacks=callbacks,
            interactive_tty=cmd.interactive_tty,
        )
        try:
            reply = self._slots.execute_step_locally(step_spec)
            return (True, DataclassCodec.encode_envelope(reply))
        finally:
            if step_run_id:
                with self._prio_lock:
                    self._active_step_priorities.pop(step_run_id, None)

    def _build_reverse_callbacks(
        self,
        parent_tid: TaskId,
        cb_ctx: WorkerCallbackContext,
        base_lineage: CausalLineage,
        emit_progress: Callable[[JsonObject], None],
        peer_cancel: CancellationToken,
    ) -> StepContextCallbacks:
        def _on_emit_imm(eid: EventId, ev_raw: JsonObject, imm_lin: CausalLineage, strict: bool) -> None:
            ch = self._require_channel()
            env = WorkerCallbackEnvelope(
                callback=WorkerCallbackKind.EMIT_IMM,
                context_meta=cb_ctx,
                event_id=eid,
                raw_payload=ev_raw,
                strict=strict,
                lineage=imm_lin,
            )
            cb_out = ch.call(DataclassCodec.encode_envelope(env), cancel_token=peer_cancel, cancel_grace_ms=500)
            _unwrap_emit_imm_callback(cb_out, parent_tid)

        def _on_invoke_task(
            child_tid: TaskId,
            encoded_in: JsonObject,
            target_ws: Optional[HostPath],
            r_pol: Optional[ClientRoutingPolicy],
        ) -> TaskOutcome[JsonValue]:
            ch = self._require_channel()
            env = WorkerCallbackEnvelope(
                callback=WorkerCallbackKind.INVOKE_TASK,
                context_meta=cb_ctx,
                task_id=child_tid,
                raw_input=encoded_in,
                target_workspace=target_ws,
                routing_policy=r_pol,
                lineage=base_lineage,
            )
            try:
                enc_env = DataclassCodec.encode_envelope(env)
            except YscbError as exc:
                return TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(child_tid)))
            cb_out = ch.call(enc_env, cancel_token=peer_cancel, cancel_grace_ms=500)
            return _unwrap_invoke_task_callback(cb_out, child_tid)

        return StepContextCallbacks(
            on_emit_imm=_on_emit_imm,
            on_invoke_task=_on_invoke_task,
            on_progress=emit_progress,
        )

    def _elevate_step_if_active(self, step_run_id: str) -> None:
        if not step_run_id:
            return
        with self._prio_lock:
            if step_run_id in self._active_step_priorities:
                self._active_step_priorities[step_run_id] = ExecutionPriority.FOREGROUND
                return
            self._pre_elevated_steps[step_run_id] = None
            while len(self._pre_elevated_steps) > 256:
                self._pre_elevated_steps.popitem(last=False)

    def on_control(self, kind: FrameKind, payload: JsonObject) -> JsonObject:
        try:
            if kind == FrameKind.CONTROL_STOP:
                stop_ctrl = DataclassCodec.decode(_WorkerStopControl, payload)
                if stop_ctrl.grace_ms < 0:
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "grace_ms must be >= 0.")
                td_diags = self.close(grace_ms=stop_ctrl.grace_ms)
                self._channel_ready.wait(timeout=2.0)
                if self.channel is not None:
                    self.channel.close_when_idle()
                return {"ok": True, "teardown_diagnostics": [DataclassCodec.encode_object(d) for d in td_diags]}
            if kind == FrameKind.CONTROL_REQUEST:
                ctrl = DataclassCodec.decode(_WorkerElevateControl, payload)
                if not ctrl.step_run_id.strip():
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "step_run_id must be a non-empty string.")
                self._elevate_step_if_active(ctrl.step_run_id)
                return {"ok": True}
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported worker control frame: {kind.value}")
        except YscbError as exc:
            return {"ok": False, "error": exc.detail.code.value, "message": exc.detail.message}


@dataclass(frozen=True, slots=True)
class _WorkerStopControl:
    grace_ms: int = 1000


@dataclass(frozen=True, slots=True)
class _WorkerElevateControl:
    action: Literal["elevate_step"]
    step_run_id: str


def worker_main() -> int:
    """Subprocess entrypoint consuming auth token from popped environment variable."""
    auth_token = os.environ.pop(WORKER_AUTH_ENV_KEY, "")
    if not auth_token:
        return 1
    if len(sys.argv) < 2 or not sys.argv[1]:
        return 2
    try:
        raw_cfg = strict_parse_json_object(sys.argv[1])
        cfg = DataclassCodec.decode(WorkerBootstrapConfig, raw_cfg)
    except (ValueError, YscbError, KeyError, TypeError, RecursionError):
        return 2
    descriptors = cfg.modules
    handler = WorkerSubprocessHandler(
        cfg.workspace_root,
        descriptors,
        is_hot_container=cfg.is_hot_container,
        expect_channel=True,
    )
    ep = RpcEndpointInfo(
        pid=os.getpid(),
        host=cfg.host,
        port=cfg.port,
        boot_id=cfg.boot_id,
        auth_token=auth_token,
        workspace_root=cfg.workspace_root,
    )
    ch = connect_and_handshake(ep, handler=handler, connect_timeout_sec=5.0)
    if ch is None:
        return 1
    handler.bind_channel(ch)
    stop_sigs = (int(signal.SIGTERM), int(signal.SIGBREAK)) if IS_WINDOWS else (int(signal.SIGTERM),)
    with SignalWakeupGuard(stop_sigs, ch.close):
        try:
            ch.wait_until_closed()
        finally:
            handler.close()
            ch.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(worker_main())
