"""Strongly typed frozen wire DTOs for Master <-> Tier 1 Worker and Client <-> Daemon IPC."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional

from core.execution.event import CausalLineage, RawEventRecord
from core.execution.runtime.contracts import (
    validate_host_task_pairs,
    CallPropagationContext,
    CallerSurface,
    ClientRoutingPolicy,
    ExecutionPriority,
    ModuleDescriptor,
)
from core.foundation.errors import ErrorDetail, safe_exception_summary
from core.foundation.primitives import MAX_USER_JSON_DEPTH, EventId, HostPath, JsonObject, JsonValue, ModuleId, TaskId, require_pure_bool, require_pure_str, require_typed_tuple, validate_wire_json_object



class WorkerCommandKind(Enum):
    WARMUP = "warmup"
    UNLOAD_MODULES = "unload_modules"
    COMPUTE_EQUIV = "compute_equiv"
    MAP_BATCH = "map_batch"
    RUN_STEP = "run_step"


class WorkerCallbackKind(Enum):
    EMIT_IMM = "emit_imm"
    INVOKE_TASK = "invoke_task"


class WorkerControlAction(Enum):
    MODULE_INITIALIZED = "module_initialized"
    ELEVATE_STEP = "elevate_step"


@dataclass(frozen=True, slots=True)
class WorkerModInitControl:
    action: WorkerControlAction
    module_id: ModuleId


@dataclass(frozen=True, slots=True)
class WorkerElevateControl:
    action: WorkerControlAction
    step_run_id: str


@dataclass(frozen=True, slots=True)
class WorkerStopControl:
    grace_ms: int = 1000


@dataclass(frozen=True, slots=True)
class WorkerStopAck:
    ok: bool = True
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()


@dataclass(frozen=True, slots=True)
class EmittedEventHop:
    """Scoped event hop paired with the exact emitting task for cross-workspace causal cycle attribution."""

    workspace_scope: str
    event_id: EventId
    source_task: Optional[str] = None

    def __post_init__(self) -> None:
        require_pure_str(self.workspace_scope, "EmittedEventHop.workspace_scope")
        if not isinstance(self.event_id, EventId):
            raise ValueError(f"EmittedEventHop.event_id must be EventId, got {self.event_id!r}")
        if self.source_task is not None:
            require_pure_str(self.source_task, "EmittedEventHop.source_task", non_empty=True)


@dataclass(frozen=True, slots=True)
class WorkerBootstrapConfig:
    """Compact startup payload passed to a Tier 1 .venv subprocess (auth_token travels via popped env var)."""

    host: str
    port: int
    boot_id: str
    workspace_root: HostPath
    modules: tuple[ModuleDescriptor, ...]
    is_hot_container: bool = True


@dataclass(frozen=True, slots=True)
class WorkerCallbackContext:
    """Propagated turn & security context carried across Tier 1 reverse callbacks."""

    propagation: CallPropagationContext
    caller_cwd: HostPath
    caller_env: Mapping[str, str]
    parent_routing_policy: ClientRoutingPolicy = ClientRoutingPolicy.AUTO_SPAWN
    step_run_id: str = ""


@dataclass(frozen=True, slots=True)
class WorkerCommandEnvelope:
    """Typed Master -> Tier 1 Worker command envelope."""

    action: WorkerCommandKind
    modules: tuple[ModuleId, ...] = ()
    step_run_id: str = ""
    task_id: Optional[TaskId] = None
    event_id: Optional[EventId] = None
    raw_input: JsonObject = field(default_factory=dict)
    event_payloads: tuple[JsonObject, ...] = ()
    caller_cwd: Optional[HostPath] = None
    caller_env: Mapping[str, str] = field(default_factory=dict)
    lineage: CausalLineage = field(default_factory=CausalLineage)
    priority: ExecutionPriority = ExecutionPriority.FOREGROUND
    interactive_tty: bool = False
    callback_context: Optional[WorkerCallbackContext] = None


@dataclass(frozen=True, slots=True)
class WorkerWarmupReply:
    ok: bool
    degraded: Mapping[str, ErrorDetail] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkerUnloadReply:
    ok: bool
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkerEquivReply:
    ok: bool
    equiv_key: str = ""
    error: Optional[ErrorDetail] = None


@dataclass(frozen=True, slots=True)
class WorkerMapBatchReply:
    ok: bool
    skip: bool = False
    mapped_input: JsonObject = field(default_factory=dict)
    error: Optional[ErrorDetail] = None


@dataclass(frozen=True, slots=True)
class WorkerStepReply:
    """Typed step result returned both by LocalModuleSlotRegistry and Tier 1 Worker IPC."""

    ok: bool
    raw_output: JsonValue = None
    committed_events: tuple[RawEventRecord, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    preempted: bool = False
    fatal_abort_turn: bool = False
    error: Optional[ErrorDetail] = None


@dataclass(frozen=True, slots=True)
class WorkerCallbackEnvelope:
    """Typed Tier 1 Worker -> Master reverse callback envelope."""

    callback: WorkerCallbackKind
    context_meta: WorkerCallbackContext
    event_id: Optional[EventId] = None
    raw_payload: JsonObject = field(default_factory=dict)
    strict: bool = False
    task_id: Optional[TaskId] = None
    raw_input: JsonObject = field(default_factory=dict)
    target_workspace: Optional[HostPath] = None
    routing_policy: Optional[ClientRoutingPolicy] = None
    lineage: CausalLineage = field(default_factory=CausalLineage)


@dataclass(frozen=True, slots=True)
class WorkerCallbackReply:
    ok: bool
    raw_value: JsonValue = None
    error: Optional[ErrorDetail] = None
    event_diagnostics: tuple[ErrorDetail, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    coalesced: bool = False
    executed_hot: bool = False
    fatal_abort_turn: bool = False


@dataclass(frozen=True, slots=True)
class DaemonRpcInvokeEnvelope:
    """Typed Client -> WorkspaceDaemon RPC invocation request composing CallPropagationContext."""

    task_id: TaskId
    raw_input: JsonObject
    workspace_root: HostPath
    caller_cwd: HostPath
    caller_env: Mapping[str, str] = field(default_factory=dict)
    caller_surface: CallerSurface = CallerSurface.SDK
    priority: ExecutionPriority = ExecutionPriority.FOREGROUND
    approval_scope: frozenset[TaskId] = frozenset()
    allow_conditional: bool = True
    timeout_ms: Optional[int] = None
    propagation: CallPropagationContext = field(default_factory=CallPropagationContext)


@dataclass(frozen=True, slots=True)
class DaemonRpcInvokeReply:
    """Typed WorkspaceDaemon -> Client RPC invocation reply carrying transitive invoked_tasks and emitted_hops."""

    ok: bool
    raw_value: JsonValue = None
    error: Optional[ErrorDetail] = None
    event_diagnostics: tuple[ErrorDetail, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    invoked_tasks: tuple[tuple[HostPath, TaskId], ...] = ()
    emitted_hops: tuple[EmittedEventHop, ...] = ()
    coalesced: bool = False

    def __post_init__(self) -> None:
        require_pure_bool(self.ok, "DaemonRpcInvokeReply.ok")
        require_pure_bool(self.coalesced, "DaemonRpcInvokeReply.coalesced")
        if self.error is not None and not isinstance(self.error, ErrorDetail):
            raise ValueError("DaemonRpcInvokeReply.error must be ErrorDetail or None.")
        try:
            validate_wire_json_object(
                {"v": self.raw_value},
                max_depth=MAX_USER_JSON_DEPTH + 1,
                label="DaemonRpcInvokeReply.raw_value",
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(safe_exception_summary(exc)) from exc
        object.__setattr__(self, "event_diagnostics", require_typed_tuple(self.event_diagnostics, ErrorDetail, "event_diagnostics"))
        object.__setattr__(self, "teardown_diagnostics", require_typed_tuple(self.teardown_diagnostics, ErrorDetail, "teardown_diagnostics"))
        object.__setattr__(self, "invoked_tasks", validate_host_task_pairs(self.invoked_tasks, "DaemonRpcInvokeReply.invoked_tasks"))
        object.__setattr__(self, "emitted_hops", require_typed_tuple(self.emitted_hops, EmittedEventHop, "emitted_hops"))
