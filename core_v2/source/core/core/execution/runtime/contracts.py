"""Strongly typed contracts, TaskMetadata, TaskRouteSpec, BoundTask, TaskContext, YscbModule, and Ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
import dataclasses
from dataclasses import dataclass, field
from enum import Enum
import re
from types import MappingProxyType
import math
from typing import Callable, Generic, Mapping, Optional, Protocol, Sequence, TypeVar, get_origin, overload

from core.execution.event import (
    BoundEventSubscription,
    CausalLineage,
    EventMetadata,
    ScopedHop,
    normalize_payload_filter,
)
from core.foundation.codec import DataclassCodec
from core.foundation.errors import ErrorCode, ErrorDetail, YscbError, safe_exception_summary
from core.foundation.observability import CancellationToken, ProgressEvent, safe_real_to_float
from core.foundation.primitives import (
    clone_strict_json_object,
    is_valid_type_annotation,
    EventId,
    HostPath,
    JsonObject,
    JsonPrimitive,
    JsonValue,
    ModuleId,
    TaskId,
    INT64_MAX,
    MAX_PARSE_JSON_DEPTH,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    require_typed_frozenset,
    require_typed_tuple,
)

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")
TOut_co = TypeVar("TOut_co", covariant=True)
TPayload = TypeVar("TPayload")

_ALLOWED_ENV_EXACT: frozenset[str] = frozenset(
    {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "all_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "LANG",
        "TZ",
        "TERM",
        "COLORTERM",
        "FORCE_COLOR",
        "NO_COLOR",
    }
)
_ALLOWED_ENV_PREFIXES: tuple[str, ...] = ("LC_", "YSCB_")
_FORBIDDEN_ENV_EXACT: frozenset[str] = frozenset({"YSCB_WORKER_AUTH_TOKEN"})


def _is_valid_env_str(val: str, *, forbid_eq: bool = False) -> bool:
    if "\x00" in val or (forbid_eq and "=" in val):
        return False
    try:
        val.encode("utf-8", errors="strict")
        return True
    except UnicodeEncodeError:
        return False


def sanitize_caller_env(raw_env: Mapping[str, str]) -> dict[str, str]:
    """Filter transient caller environment variables against the explicit runtime allowlist and UTF-8/OS safety."""
    cleaned: dict[str, str] = {}
    for k, v in raw_env.items():
        if type(k) is not str or type(v) is not str:
            continue
        if (
            k not in _FORBIDDEN_ENV_EXACT
            and (k in _ALLOWED_ENV_EXACT or k.startswith(_ALLOWED_ENV_PREFIXES))
            and _is_valid_env_str(k, forbid_eq=True)
            and _is_valid_env_str(v)
        ):
            cleaned[k] = v
    return cleaned


class CallerSurface(Enum):
    SDK = "sdk"
    CLI = "cli"


class TaskExposure(Enum):
    CLI_AND_SDK = "cli_and_sdk"
    SDK_ONLY = "sdk_only"
    INTERNAL_TRIGGER = "internal_trigger"


class DispatchMode(Enum):
    HYBRID = "hybrid"
    COLD_ONLY = "cold_only"
    DAEMON_ONLY = "daemon_only"


class SelfMutationScope(Enum):
    NONE = "none"
    MUTATES_MODULES = "mutates_modules"
    MUTATES_CORE = "mutates_core"


class SecurityTier(Enum):
    SAFE = "safe"
    CONDITIONAL = "conditional"
    GATED = "gated"


class ConcurrencyMode(Enum):
    PARALLEL = "parallel"
    SERIALIZE = "serialize"
    COALESCE = "coalesce"
    PREEMPT = "preempt"


class ExecutionPriority(Enum):
    FOREGROUND = "foreground"
    BACKGROUND = "background"


class ClientRoutingPolicy(Enum):
    AUTO_SPAWN = "auto_spawn"
    AUTO_NO_SPAWN = "auto_no_spawn"
    FORCE_COLD = "force_cold"
    STRICT_HOT = "strict_hot"


@dataclass(frozen=True, slots=True)
class PeriodicScheduleSpec:
    """Declarative periodic background trigger specification supporting config-gated activation."""

    default_interval_sec: float
    enabled_config_key: Optional[str] = None
    interval_config_key: Optional[str] = None

    def __post_init__(self) -> None:
        f_iv = safe_real_to_float(self.default_interval_sec, label="default_interval_sec")
        if not math.isfinite(f_iv) or f_iv <= 0.0:
            raise ValueError(
                f"PeriodicScheduleSpec default_interval_sec must be finite and > 0, got {self.default_interval_sec!r}"
            )
        object.__setattr__(self, "default_interval_sec", f_iv)
        for key_val, label in (
            (self.enabled_config_key, "enabled_config_key"),
            (self.interval_config_key, "interval_config_key"),
        ):
            if key_val is not None:
                require_pure_str(key_val, f"PeriodicScheduleSpec.{label}", non_empty=True)
                if not _is_valid_env_str(key_val):
                    raise ValueError(f"PeriodicScheduleSpec {label} must be a non-empty plain UTF-8 str.")


@dataclass(frozen=True, slots=True)
class CliBindingSpec:
    command_path: tuple[str, ...]
    summary: str
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        cp_tup = require_typed_tuple(self.command_path, str, "CliBindingSpec.command_path")
        al_tup = require_typed_tuple(self.aliases, str, "CliBindingSpec.aliases")
        require_pure_str(self.summary, "CliBindingSpec.summary", non_empty=True)
        object.__setattr__(self, "command_path", cp_tup)
        object.__setattr__(self, "aliases", al_tup)
        if not self.command_path or any(
            (not seg.strip() or any(ch.isspace() for ch in seg) or not _is_valid_env_str(seg))
            for seg in self.command_path
        ):
            raise ValueError("CliBindingSpec command_path must contain non-empty valid UTF-8 whitespace-free segments.")
        if not self.summary or not self.summary.strip() or not _is_valid_env_str(self.summary):
            raise ValueError("CliBindingSpec summary must be non-empty valid UTF-8.")
        if any((not alias.strip() or any(ch.isspace() for ch in alias) or not _is_valid_env_str(alias)) for alias in self.aliases):
            raise ValueError("CliBindingSpec aliases must contain non-empty valid UTF-8 whitespace-free entries.")
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError("CliBindingSpec aliases must not contain duplicates.")
        if any(seg.startswith("-") for seg in self.command_path) or any(a.startswith("-") for a in self.aliases):
            raise ValueError("CliBindingSpec command_path segments and aliases must not start with '-'.")
        if len(self.command_path) == 1 and self.command_path[0] in self.aliases:
            raise ValueError("CliBindingSpec single-segment command_path must not duplicate an alias.")


@dataclass(frozen=True, slots=True)
class SubscriptionRouteSpec:
    """Pure-data static subscription entry compiled into tasks.index.json (zero Tier 1 import)."""

    event_id: EventId
    payload_filter: Optional[Mapping[str, tuple[JsonPrimitive, ...]]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, EventId):
            raise ValueError(f"SubscriptionRouteSpec.event_id must be EventId, got {self.event_id!r}")
        object.__setattr__(self, "payload_filter", normalize_payload_filter(self.payload_filter))


def _normalize_resource_key(raw_key: Optional[str]) -> Optional[str]:
    if raw_key is None:
        return None
    require_pure_str(raw_key, "resource_key")
    stripped = raw_key.strip()
    if stripped and not _is_valid_env_str(stripped):
        raise ValueError("resource_key must be valid UTF-8 without NUL or lone surrogates.")
    return stripped if stripped else None


def _validate_route_invariants(spec: TaskRouteSpec) -> None:
    if spec.concurrency_mode != ConcurrencyMode.PARALLEL and not spec.resource_key:
        raise ValueError(f"Task '{spec.task_id}' with mode={spec.concurrency_mode} requires non-empty resource_key.")
    if spec.interactive_tty and spec.dispatch_mode != DispatchMode.COLD_ONLY:
        raise ValueError(f"Task '{spec.task_id}' with interactive_tty=True must declare COLD_ONLY.")
    if spec.mutation_scope != SelfMutationScope.NONE and spec.dispatch_mode != DispatchMode.COLD_ONLY:
        raise ValueError(f"Task '{spec.task_id}' with mutation_scope={spec.mutation_scope} must declare COLD_ONLY.")
    if spec.exposure == TaskExposure.INTERNAL_TRIGGER and (
        spec.interactive_tty or spec.mutation_scope != SelfMutationScope.NONE
    ):
        raise ValueError(f"INTERNAL_TRIGGER Task '{spec.task_id}' cannot declare interactive_tty or mutation_scope.")
    if (spec.interactive_tty or spec.mutation_scope != SelfMutationScope.NONE) and (
        spec.subscriptions or spec.periodic is not None
    ):
        raise ValueError(f"Task '{spec.task_id}' with TTY or mutation scope cannot bind background triggers.")
    if spec.timeout_ms is not None:
        require_pure_int(spec.timeout_ms, f"Task '{spec.task_id}' timeout_ms", min_val=1, max_val=INT64_MAX)
    if spec.dispatch_mode == DispatchMode.COLD_ONLY and (spec.periodic is not None or spec.subscriptions):
        raise ValueError(f"COLD_ONLY Task '{spec.task_id}' cannot bind daemon periodic timer or event subscriptions.")
    if spec.security_tier == SecurityTier.GATED:
        if spec.exposure == TaskExposure.INTERNAL_TRIGGER or spec.subscriptions or spec.periodic is not None:
            raise ValueError(f"GATED Task '{spec.task_id}' cannot bind INTERNAL_TRIGGER, events, or periodic timers.")
    if spec.cli is not None and spec.exposure != TaskExposure.CLI_AND_SDK:
        raise ValueError(f"Task '{spec.task_id}' with exposure={spec.exposure} cannot bind a CLI command.")
    if len({s.event_id for s in spec.subscriptions}) != len(spec.subscriptions):
        raise ValueError(f"Task '{spec.task_id}' cannot subscribe multiple times to the same EventId.")


@dataclass(frozen=True, slots=True)
class TaskRouteSpec:
    """Pure-data static routing & scheduling descriptor usable by Tier 0 Master without importing Tier 1."""

    task_id: TaskId
    exposure: TaskExposure = TaskExposure.CLI_AND_SDK
    cli: Optional[CliBindingSpec] = None
    dispatch_mode: DispatchMode = DispatchMode.HYBRID
    mutation_scope: SelfMutationScope = SelfMutationScope.NONE
    interactive_tty: bool = False
    security_tier: SecurityTier = SecurityTier.SAFE
    resource_key: Optional[str] = None
    concurrency_mode: ConcurrencyMode = ConcurrencyMode.PARALLEL
    timeout_ms: Optional[int] = None
    subscriptions: tuple[SubscriptionRouteSpec, ...] = ()
    periodic: Optional[PeriodicScheduleSpec] = None

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, TaskId):
            raise ValueError(f"TaskRouteSpec.task_id must be TaskId, got {self.task_id!r}")
        for enum_val, enum_cls, label in (
            (self.exposure, TaskExposure, "exposure"),
            (self.dispatch_mode, DispatchMode, "dispatch_mode"),
            (self.mutation_scope, SelfMutationScope, "mutation_scope"),
            (self.security_tier, SecurityTier, "security_tier"),
            (self.concurrency_mode, ConcurrencyMode, "concurrency_mode"),
        ):
            if not isinstance(enum_val, enum_cls):
                raise ValueError(f"TaskRouteSpec.{label} must be {enum_cls.__name__}, got {enum_val!r}")
        require_pure_bool(self.interactive_tty, "TaskRouteSpec.interactive_tty")
        subs_tup = require_typed_tuple(self.subscriptions, SubscriptionRouteSpec, "TaskRouteSpec.subscriptions")
        if self.cli is not None and not isinstance(self.cli, CliBindingSpec):
            raise ValueError("TaskRouteSpec.cli must be CliBindingSpec or None.")
        if self.periodic is not None and not isinstance(self.periodic, PeriodicScheduleSpec):
            raise ValueError("TaskRouteSpec.periodic must be PeriodicScheduleSpec or None.")
        object.__setattr__(self, "subscriptions", subs_tup)
        object.__setattr__(self, "resource_key", _normalize_resource_key(self.resource_key))
        _validate_route_invariants(self)


def _validate_bound_subscription_item(sub: BoundEventSubscription[object]) -> None:
    try:
        eid = sub.event_id
        dm = sub.decode_and_map
    except AttributeError as exc:
        raise ValueError(f"Invalid BoundEventSubscription: {sub!r}") from exc
    if not isinstance(eid, EventId) or not callable(dm):
        raise ValueError(f"Invalid BoundEventSubscription contract on {sub!r}")


def validate_host_task_pairs(raw: object, label: str) -> tuple[tuple[HostPath, TaskId], ...]:
    if isinstance(raw, (str, bytes, bytearray, memoryview)) or not isinstance(raw, Sequence):
        raise ValueError(f"{label} must be a Sequence of (HostPath, TaskId).")
    out: list[tuple[HostPath, TaskId]] = []
    for item in raw:
        if isinstance(item, (str, bytes, bytearray, memoryview)) or not isinstance(item, Sequence) or len(item) != 2:
            raise ValueError(f"{label} entry must be a 2-element (HostPath, TaskId) pair.")
        hp, tid = item[0], item[1]
        if not isinstance(hp, HostPath) or not isinstance(tid, TaskId):
            raise ValueError(f"{label} entry requires (HostPath, TaskId), got {item!r}")
        out.append((hp, tid))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class TaskMetadata(Generic[TIn, TOut]):
    """Complete static declaration governing routing, locking, security, and triggers for a Task."""

    task_id: TaskId
    input_type: type[TIn]
    output_type: type[TOut]
    exposure: TaskExposure = TaskExposure.CLI_AND_SDK
    cli: Optional[CliBindingSpec] = None
    dispatch_mode: DispatchMode = DispatchMode.HYBRID
    mutation_scope: SelfMutationScope = SelfMutationScope.NONE
    interactive_tty: bool = False
    security_tier: SecurityTier = SecurityTier.SAFE
    resource_key: Optional[str] = None
    concurrency_mode: ConcurrencyMode = ConcurrencyMode.PARALLEL
    equivalence_fn: Optional[Callable[[TIn], str]] = None
    timeout_ms: Optional[int] = None
    subscriptions: tuple[BoundEventSubscription[TIn], ...] = ()
    periodic: Optional[PeriodicScheduleSpec] = None

    def to_route_spec(self) -> TaskRouteSpec:
        return TaskRouteSpec(
            task_id=self.task_id,
            exposure=self.exposure,
            cli=self.cli,
            dispatch_mode=self.dispatch_mode,
            mutation_scope=self.mutation_scope,
            interactive_tty=self.interactive_tty,
            security_tier=self.security_tier,
            resource_key=self.resource_key,
            concurrency_mode=self.concurrency_mode,
            timeout_ms=self.timeout_ms,
            subscriptions=tuple(
                SubscriptionRouteSpec(event_id=s.event_id, payload_filter=s.payload_filter)
                for s in self.subscriptions
            ),
            periodic=self.periodic,
        )

    def __post_init__(self) -> None:
        for tp_val, label in ((self.input_type, "input_type"), (self.output_type, "output_type")):
            if not is_valid_type_annotation(tp_val):
                raise ValueError(f"TaskMetadata.{label} must be a valid type or generic alias, got {tp_val!r}")
        if self.equivalence_fn is not None and not callable(self.equivalence_fn):
            raise ValueError("TaskMetadata.equivalence_fn must be callable or None.")
        if isinstance(self.subscriptions, (str, bytes)) or not isinstance(self.subscriptions, Sequence):
            raise ValueError("TaskMetadata.subscriptions must be a non-string Sequence.")
        sub_tup = tuple(self.subscriptions)
        for sub in sub_tup:
            _validate_bound_subscription_item(sub)
        object.__setattr__(self, "subscriptions", sub_tup)
        object.__setattr__(self, "resource_key", _normalize_resource_key(self.resource_key))
        _ = self.to_route_spec()


def _validate_scoped_hops_tuple(raw: object) -> tuple[ScopedHop, ...]:
    if isinstance(raw, (str, bytes, bytearray, memoryview)) or not isinstance(raw, Sequence):
        raise ValueError("CoalesceCallerView.caller_hops must be a Sequence of (str, EventId).")
    out: list[ScopedHop] = []
    for item in raw:
        if isinstance(item, (str, bytes, bytearray, memoryview)) or not isinstance(item, Sequence) or len(item) != 2:
            raise ValueError("caller_hops entry must be a (str, EventId) pair.")
        sc, eid = item[0], item[1]
        require_pure_str(sc, "caller_hops scope")
        if not isinstance(eid, EventId):
            raise ValueError("caller_hops entry requires (str, EventId).")
        out.append((sc, eid))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class CoalesceCallerView:
    """Propagated snapshot of a live StepFlight caller for cross-step and cross-process reentrancy/cycle checks."""

    turn_id: str
    call_tree_id: str
    call_stack: tuple[tuple[HostPath, TaskId], ...] = ()
    caller_hops: tuple[ScopedHop, ...] = ()
    flight_ids: tuple[str, ...] = ()
    in_event_chain: bool = False

    def __post_init__(self) -> None:
        require_pure_str(self.turn_id, "CoalesceCallerView.turn_id")
        require_pure_str(self.call_tree_id, "CoalesceCallerView.call_tree_id")
        require_pure_bool(self.in_event_chain, "CoalesceCallerView.in_event_chain")
        object.__setattr__(self, "call_stack", validate_host_task_pairs(self.call_stack, "call_stack"))
        object.__setattr__(self, "caller_hops", _validate_scoped_hops_tuple(self.caller_hops))
        object.__setattr__(self, "flight_ids", require_typed_tuple(self.flight_ids, str, "flight_ids"))


@dataclass(frozen=True, slots=True)
class CallPropagationContext:
    """Immutable cross-hop call tree, causal lineage, and container reentrancy state."""

    turn_id: Optional[str] = None
    call_tree_id: Optional[str] = None
    call_stack: tuple[tuple[HostPath, TaskId], ...] = ()
    lineage: CausalLineage = field(default_factory=CausalLineage)
    is_internal_trigger: bool = False
    is_nested_call: bool = False
    in_event_chain: bool = False
    from_hot_container: bool = False
    hot_workspaces: frozenset[HostPath] = frozenset()
    cold_shared_workspaces: frozenset[HostPath] = frozenset()
    coalesce_callers: tuple[CoalesceCallerView, ...] = ()
    coalesce_flights: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for opt_txt, label in ((self.turn_id, "turn_id"), (self.call_tree_id, "call_tree_id")):
            if opt_txt is not None:
                require_pure_str(opt_txt, f"CallPropagationContext.{label}")
        if not isinstance(self.lineage, CausalLineage):
            raise ValueError("CallPropagationContext.lineage must be CausalLineage.")
        for flag, label in (
            (self.is_internal_trigger, "is_internal_trigger"),
            (self.is_nested_call, "is_nested_call"),
            (self.in_event_chain, "in_event_chain"),
            (self.from_hot_container, "from_hot_container"),
        ):
            require_pure_bool(flag, f"CallPropagationContext.{label}")
        object.__setattr__(self, "call_stack", validate_host_task_pairs(self.call_stack, "call_stack"))
        object.__setattr__(self, "hot_workspaces", require_typed_frozenset(self.hot_workspaces, HostPath, "hot_workspaces"))
        object.__setattr__(
            self,
            "cold_shared_workspaces",
            require_typed_frozenset(self.cold_shared_workspaces, HostPath, "cold_shared_workspaces"),
        )
        if isinstance(self.coalesce_callers, (str, bytes)) or not isinstance(self.coalesce_callers, Sequence):
            raise ValueError("CallPropagationContext.coalesce_callers must be a Sequence of CoalesceCallerView.")
        cc_tup = tuple(self.coalesce_callers)
        if any(not isinstance(c, CoalesceCallerView) for c in cc_tup):
            raise ValueError("CallPropagationContext.coalesce_callers elements must be CoalesceCallerView.")
        object.__setattr__(self, "coalesce_callers", cc_tup)
        object.__setattr__(
            self, "coalesce_flights", require_typed_tuple(self.coalesce_flights, str, "coalesce_flights")
        )


def _freeze_raw_input_value(val: object, depth: int = 0) -> object:
    if depth > MAX_PARSE_JSON_DEPTH:
        raise ValueError("InvokeRequest.raw_input exceeded maximum nesting depth.")
    if isinstance(val, Mapping):
        return MappingProxyType({k: _freeze_raw_input_value(v, depth + 1) for k, v in val.items()})
    if isinstance(val, (list, tuple)):
        return tuple(_freeze_raw_input_value(item, depth + 1) for item in val)
    if isinstance(val, (set, frozenset)):
        return frozenset(_freeze_raw_input_value(item, depth + 1) for item in val)
    if isinstance(val, (bytes, bytearray, memoryview)):
        return bytes(val)
    if not isinstance(val, (type(None), bool, int, float, str, Enum)):
        raise ValueError(f"InvokeRequest.raw_input contains unsupported value type {type(val).__name__}.")
    return val


def _validate_caller_env_map(raw: object) -> Mapping[str, str]:
    if not isinstance(raw, Mapping):
        raise ValueError("InvokeRequest.caller_env must be a Mapping[str, str].")
    frozen_env: dict[str, str] = {}
    for k, v in raw.items():
        require_pure_str(k, "InvokeRequest.caller_env key", non_empty=True)
        require_pure_str(v, "InvokeRequest.caller_env value")
        if not _is_valid_env_str(k) or not _is_valid_env_str(v):
            raise ValueError("InvokeRequest.caller_env keys and values forbid NUL and lone surrogates.")
        frozen_env[k] = v
    return MappingProxyType(frozen_env)


@dataclass(frozen=True, slots=True)
class InvokeRequest:
    """Invocation envelope validating structural fields and caller_env at construction while freezing raw_input containers and deferring JSON value-domain checks to RuntimeDispatcher.invoke()."""

    task_id: TaskId
    raw_input: JsonObject
    workspace_root: HostPath
    caller_cwd: HostPath
    caller_env: Mapping[str, str] = field(default_factory=dict)
    caller_surface: CallerSurface = CallerSurface.SDK
    routing_policy: ClientRoutingPolicy = ClientRoutingPolicy.AUTO_SPAWN
    priority: ExecutionPriority = ExecutionPriority.FOREGROUND
    approval_scope: frozenset[TaskId] = frozenset()
    allow_conditional: bool = True
    propagation: CallPropagationContext = field(default_factory=CallPropagationContext)

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, TaskId):
            raise ValueError(f"InvokeRequest.task_id must be TaskId, got {self.task_id!r}")
        if not isinstance(self.raw_input, Mapping):
            raise ValueError(f"InvokeRequest.raw_input must be a Mapping, got {self.raw_input!r}")
        if not isinstance(self.workspace_root, HostPath) or not isinstance(self.caller_cwd, HostPath):
            raise ValueError("InvokeRequest workspace_root and caller_cwd must be HostPath.")
        object.__setattr__(self, "raw_input", _freeze_raw_input_value(self.raw_input))
        object.__setattr__(self, "caller_env", _validate_caller_env_map(self.caller_env))
        if not isinstance(self.caller_surface, CallerSurface):
            raise ValueError(f"InvokeRequest.caller_surface must be CallerSurface, got {self.caller_surface!r}")
        if not isinstance(self.routing_policy, ClientRoutingPolicy):
            raise ValueError(f"InvokeRequest.routing_policy must be ClientRoutingPolicy, got {self.routing_policy!r}")
        if not isinstance(self.priority, ExecutionPriority):
            raise ValueError(f"InvokeRequest.priority must be ExecutionPriority, got {self.priority!r}")
        require_pure_bool(self.allow_conditional, "InvokeRequest.allow_conditional")
        if not isinstance(self.propagation, CallPropagationContext):
            raise ValueError("InvokeRequest.propagation must be CallPropagationContext.")
        object.__setattr__(self, "approval_scope", require_typed_frozenset(self.approval_scope, TaskId, "InvokeRequest.approval_scope"))


@dataclass(frozen=True, slots=True)
class TaskOutcome(Generic[TOut_co]):
    """Strongly typed result returned to any CLI, SDK, nested, or background caller."""

    ok: bool
    value: Optional[TOut_co] = None
    error: Optional[ErrorDetail] = None
    event_diagnostics: tuple[ErrorDetail, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    coalesced: bool = False
    executed_hot: bool = False

    def __post_init__(self) -> None:
        for flag, label in ((self.ok, "ok"), (self.coalesced, "coalesced"), (self.executed_hot, "executed_hot")):
            require_pure_bool(flag, f"TaskOutcome.{label}")
        if self.error is not None and not isinstance(self.error, ErrorDetail):
            raise ValueError("TaskOutcome.error must be ErrorDetail or None.")
        for diag_seq, attr_nm in (
            (self.event_diagnostics, "event_diagnostics"),
            (self.teardown_diagnostics, "teardown_diagnostics"),
        ):
            object.__setattr__(self, attr_nm, require_typed_tuple(diag_seq, ErrorDetail, f"TaskOutcome.{attr_nm}"))


class TaskContext(ABC):
    """Explicit execution context passed into Task.run(req, ctx) with zero global singletons."""

    @property
    @abstractmethod
    def workspace_root(self) -> HostPath: ...

    @property
    @abstractmethod
    def caller_cwd(self) -> HostPath: ...

    @property
    @abstractmethod
    def caller_env(self) -> Mapping[str, str]: ...

    @property
    @abstractmethod
    def cancel_token(self) -> CancellationToken: ...

    @property
    @abstractmethod
    def effective_priority(self) -> ExecutionPriority: ...

    @abstractmethod
    def emit(self, event_meta: EventMetadata[TPayload], payload: TPayload) -> None: ...

    @abstractmethod
    def emit_imm(self, event_meta: EventMetadata[TPayload], payload: TPayload, *, strict: bool = False) -> None: ...

    @overload
    def invoke_task(
        self,
        task_id: TaskId | str,
        input_obj: object,
        *,
        output_type: type[TOut],
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def invoke_task(
        self,
        task_id: TaskId | str,
        input_obj: object,
        *,
        output_type: None = None,
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[JsonValue]: ...

    @abstractmethod
    def invoke_task(
        self,
        task_id: TaskId | str,
        input_obj: object,
        *,
        output_type: Optional[type[TOut]] = None,
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]: ...

    def invoke_typed(
        self,
        task_meta: TaskMetadata[TIn, TOut],
        req: TIn,
        *,
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut]:
        """End-to-end compile-time typed nested invocation checking both TIn and TOut."""
        if not isinstance(task_meta, TaskMetadata):
            return TaskOutcome(
                ok=False,
                error=ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected TaskMetadata, got {task_meta!r}"),
            )
        try:
            encoded_req = DataclassCodec.encode_object(req, expected_type=task_meta.input_type)
        except YscbError as exc:
            return TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(task_meta.task_id)))
        return self.invoke_task(
            task_meta.task_id,
            encoded_req,
            output_type=task_meta.output_type,
            target_workspace=target_workspace,
            routing_policy=routing_policy,
        )

    @abstractmethod
    def report_progress(self, progress: ProgressEvent) -> None: ...


class BoundTask(ABC):
    """Variance-safe typed adapter implemented automatically by generic Task[TIn, TOut]."""

    @property
    @abstractmethod
    def task_id(self) -> TaskId: ...

    @property
    @abstractmethod
    def route_spec(self) -> TaskRouteSpec: ...

    @property
    @abstractmethod
    def interactive_tty(self) -> bool: ...

    @abstractmethod
    def compute_normalized_equivalence(self, raw_input: JsonObject) -> str: ...

    @abstractmethod
    def map_subscription_batch(
        self,
        event_id: EventId,
        raw_payloads: Sequence[JsonObject],
    ) -> tuple[bool, JsonObject]: ...

    @abstractmethod
    def execute_encoded(self, raw_input: JsonObject, ctx: TaskContext) -> JsonValue: ...


class Task(BoundTask, Generic[TIn, TOut]):
    """Universal strongly typed base class for every public or triggered capability in Core 2.0."""

    @property
    @abstractmethod
    def metadata(self) -> TaskMetadata[TIn, TOut]: ...

    @abstractmethod
    def run(self, req: TIn, ctx: TaskContext) -> TOut: ...

    @property
    def task_id(self) -> TaskId:
        return self.metadata.task_id

    @property
    def route_spec(self) -> TaskRouteSpec:
        return self.metadata.to_route_spec()

    @property
    def interactive_tty(self) -> bool:
        return self.metadata.interactive_tty

    def compute_normalized_equivalence(self, raw_input: JsonObject) -> str:
        typed_in = DataclassCodec.decode(self.metadata.input_type, raw_input)
        eq_fn = self.metadata.equivalence_fn
        if eq_fn is not None:
            raw_eq = eq_fn(typed_in)
            try:
                clean_eq = require_pure_str(raw_eq, "equivalence_fn return value")
            except ValueError as exc:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, safe_exception_summary(exc), source_task=str(self.task_id)) from exc
            return f"{self.task_id}:custom:{clean_eq}"
        enc_norm = DataclassCodec.encode_typed(self.metadata.input_type, typed_in)
        return f"{self.task_id}:norm:{DataclassCodec.canonical_hash(enc_norm)}"

    def map_subscription_batch(
        self,
        event_id: EventId,
        raw_payloads: Sequence[JsonObject],
    ) -> tuple[bool, JsonObject]:
        sub = next((s for s in self.metadata.subscriptions if s.event_id == event_id), None)
        if sub is None:
            return (True, {})
        mapped = sub.decode_and_map(raw_payloads)
        if mapped is None:
            return (True, {})
        in_tp = self.metadata.input_type
        in_orig = get_origin(in_tp)
        is_dc_in = (
            (isinstance(in_tp, type) and in_tp not in (ModuleId, TaskId, EventId, HostPath) and dataclasses.is_dataclass(in_tp))
            or (isinstance(in_orig, type) and dataclasses.is_dataclass(in_orig))
        )
        if isinstance(mapped, Mapping) and is_dc_in:
            try:
                raw_obj = clone_strict_json_object(mapped, label="batch_mapper output")
            except (TypeError, ValueError) as exc:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, safe_exception_summary(exc), source_task=str(self.task_id)) from exc
            _ = DataclassCodec.decode(in_tp, raw_obj)
            return (False, raw_obj)
        return (False, DataclassCodec.encode_object(mapped, expected_type=in_tp))

    def execute_encoded(self, raw_input: JsonObject, ctx: TaskContext) -> JsonValue:
        typed_in = DataclassCodec.decode(self.metadata.input_type, raw_input)
        typed_out = self.run(typed_in, ctx)
        return DataclassCodec.encode_typed(self.metadata.output_type, typed_out)


class YscbModule(ABC):
    """Managed module container base class instantiated via explicit DI (zero global singletons)."""

    @property
    @abstractmethod
    def module_id(self) -> ModuleId: ...

    @abstractmethod
    def tasks(self) -> Sequence[BoundTask]: ...

    def on_init(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        _ = workspace_root
        return None

    def on_start(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        _ = workspace_root
        return None


@dataclass(frozen=True, slots=True)
class ModuleDescriptor:
    """Pure value descriptor describing an installed module strictly inside .modules/<id>."""

    module_id: ModuleId
    module_dir: HostPath
    entry_file: str = "module_entry.py"
    venv_group: Optional[str] = None
    venv_python: Optional[HostPath] = None
    eager_warmup: bool = False
    declared_tasks: tuple[TaskRouteSpec, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, ModuleId) or not isinstance(self.module_dir, HostPath):
            raise ValueError("ModuleDescriptor requires ModuleId and HostPath.")
        require_pure_str(self.entry_file, "ModuleDescriptor.entry_file", non_empty=True)
        if not _is_valid_env_str(self.entry_file):
            raise ValueError("ModuleDescriptor.entry_file contains NUL or lone surrogates.")
        if self.venv_group is not None:
            require_pure_str(self.venv_group, "ModuleDescriptor.venv_group", non_empty=True)
            if not re.fullmatch(r"[A-Za-z0-9_-]+", self.venv_group) or self.venv_group.startswith("mod_"):
                raise ValueError(
                    f"ModuleDescriptor.venv_group must match [A-Za-z0-9_-]+ and not start with 'mod_', got {self.venv_group!r}"
                )
        if self.venv_python is not None and not isinstance(self.venv_python, HostPath):
            raise ValueError("ModuleDescriptor.venv_python must be HostPath or None.")
        require_pure_bool(self.eager_warmup, "ModuleDescriptor.eager_warmup")
        if isinstance(self.declared_tasks, (str, bytes)) or not isinstance(self.declared_tasks, Sequence):
            raise ValueError("ModuleDescriptor.declared_tasks must be a Sequence of TaskRouteSpec.")
        dt_tup = tuple(self.declared_tasks)
        seen_tids: set[TaskId] = set()
        for t in dt_tup:
            if not isinstance(t, TaskRouteSpec):
                raise ValueError("ModuleDescriptor.declared_tasks elements must be TaskRouteSpec.")
            if t.task_id.module_id != self.module_id:
                raise ValueError(
                    f"ModuleDescriptor '{self.module_id}' cannot declare foreign task '{t.task_id}'."
                )
            if t.task_id in seen_tids:
                raise ValueError(f"Duplicate task_id '{t.task_id}' in ModuleDescriptor.declared_tasks.")
            seen_tids.add(t.task_id)
        object.__setattr__(self, "declared_tasks", dt_tup)


class ModuleProviderPort(Protocol):
    """Port abstracting packaging/metadata discovery so runtime stays decoupled from Domain 3/4 internals."""

    def list_modules(self) -> Sequence[ModuleDescriptor]: ...
    def get_module(self, module_id: ModuleId) -> Optional[ModuleDescriptor]: ...
    def reload(self) -> None: ...


class ConfigViewPort(Protocol):
    """Port providing read-only typed module config values for dynamic scheduling and runtime policy."""

    def get_module_value(self, module_id: ModuleId, key: str, default: JsonValue = None) -> JsonValue: ...
    def fingerprint(self) -> str: ...
    def reload(self) -> None: ...


class VfsEchoGuardPort(Protocol):
    """Port tracking self-inflicted VFS writes so file watchers suppress echo loops."""

    def is_suppressed(self, path: HostPath, mtime_ns: int, size: int, ino: int) -> bool: ...


class DaemonSpawner(Protocol):
    """Injected background daemon spawner guarding .cache/daemon/spawn.lock."""

    def can_spawn_in_environment(self) -> bool: ...
    def try_spawn_background(self, workspace_root: HostPath) -> bool: ...


@dataclass(frozen=True, slots=True)
class WorkerProcessSnapshot:
    """Typed status snapshot of an active Tier 1 .venv worker process."""

    group: str
    pid: int
    alive: bool

    def __post_init__(self) -> None:
        require_pure_str(self.group, "WorkerProcessSnapshot.group", non_empty=True)
        require_pure_int(self.pid, "WorkerProcessSnapshot.pid", min_val=1)
        require_pure_bool(self.alive, "WorkerProcessSnapshot.alive")


class CoordinatorPort(Protocol):
    """Read-only and control-plane management port over ResourceCoordinator."""

    def coalesce_participant_count(self, resource_key: str) -> int: ...
    def handle_remote_flight_control(self, payload: JsonObject) -> JsonObject: ...


class Tier1WorkerPool(Protocol):
    """Management port over warm Tier 1 .venv subprocess groups."""

    def active_worker_snapshots(self) -> tuple[WorkerProcessSnapshot, ...]: ...
    def warmup_group(
        self,
        group_descriptors: Sequence[ModuleDescriptor],
        only_modules: Optional[frozenset[ModuleId]] = None,
    ) -> None: ...
    def stop_groups_for_modules(
        self,
        modules: frozenset[ModuleId],
        all_descriptors: Sequence[ModuleDescriptor],
        *,
        grace_ms: int = 1000,
        drain_in_flight: bool = False,
    ) -> tuple[ErrorDetail, ...]: ...


def decode_outcome_as(
    outcome: TaskOutcome[JsonValue],
    output_type: type[TOut],
    *,
    source_task: Optional[str] = None,
) -> TaskOutcome[TOut]:
    """Decode a JsonValue TaskOutcome into a strongly typed TaskOutcome[TOut]."""
    if not outcome.ok:
        return TaskOutcome(
            ok=False,
            value=None,
            error=outcome.error,
            event_diagnostics=outcome.event_diagnostics,
            teardown_diagnostics=outcome.teardown_diagnostics,
            coalesced=outcome.coalesced,
            executed_hot=outcome.executed_hot,
        )
    try:
        typed_val = DataclassCodec.decode(output_type, outcome.value)
        return TaskOutcome(
            ok=True,
            value=typed_val,
            error=None,
            event_diagnostics=outcome.event_diagnostics,
            teardown_diagnostics=outcome.teardown_diagnostics,
            coalesced=outcome.coalesced,
            executed_hot=outcome.executed_hot,
        )
    except YscbError as exc:
        return TaskOutcome(
            ok=False,
            value=None,
            error=exc.detail.with_fallback_task(source_task) if source_task else exc.detail,
            event_diagnostics=outcome.event_diagnostics,
            teardown_diagnostics=outcome.teardown_diagnostics,
            coalesced=outcome.coalesced,
            executed_hot=outcome.executed_hot,
        )
