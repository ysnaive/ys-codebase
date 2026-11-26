"""Strongly typed contracts, TaskMetadata, TaskRouteSpec, BoundTask, TaskContext, YscbModule, and Ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
import dataclasses
from dataclasses import dataclass, field
from enum import Enum
import json
import math
import re
import threading
import time
from types import MappingProxyType
from typing import (
    BinaryIO,
    Callable,
    Generic,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    TypeVar,
    cast,
    get_args,
    get_origin,
    overload,
    runtime_checkable,
)

from core.execution.event import (
    BoundEventSubscription,
    CausalLineage,
    EventMetadata,
    EventOrdering,
    normalize_payload_filter,
)
from core.filesystem.space import SpaceDiffBatch, SpaceFileEntry, SpaceSpec, SpaceStatusSnapshot
from core.filesystem.vfs import ScopedVfs
from core.foundation.codec import DataclassCodec
from core.foundation.errors import ErrorCode, ErrorDetail, TaskCancelledException, YscbError, safe_exception_summary
from core.foundation.observability import CancellationToken, LocaleCatalog, ProgressEvent, StructuredLogger
from core.foundation.proc import ManagedProcessTree, build_isolated_python_env
from core.foundation.profiler import NullProfiler, Profiler
from core.foundation.primitives import (
    INT64_MAX,
    IS_WINDOWS,
    MAX_PARSE_JSON_DEPTH,
    PRIVATE_ENV_PREFIX,
    PYTHON_LAUNCHER_HIJACK_ENV_KEYS,
    TOOLCHAIN_ENV_ALLOWLIST,
    TREE_ID_ENV_KEY,
    EnvHash,
    EventId,
    HostPath,
    JsonObject,
    JsonPrimitive,
    JsonValue,
    ModuleId,
    SemVer4,
    SemanticUri,
    SnapshotGen,
    SpaceId,
    SpacePath,
    TaskId,
    VersionConstraint,
    clone_strict_json_object,
    is_valid_type_annotation,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    require_typed_frozenset,
    require_typed_tuple,
    safe_real_to_float,
)
from core.metadata.contributes import AggregatedContributes

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")
TOut_co = TypeVar("TOut_co", covariant=True)
TPayload = TypeVar("TPayload")
TConfig = TypeVar("TConfig")

EnvLeaseAcquireFn = Callable[[HostPath], Optional[Callable[[], None]]]
EnvTouchUsedFn = Callable[[HostPath], None]

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
WORKER_AUTH_ENV_KEY: str = "_YSCB_WORKER_AUTH_TOKEN"
LOCKS_SUBDIR: str = "locks"
INSTALLER_LOCK_STEM: str = "installer"
INSTALLER_LOCK_FILENAME: str = "installer.lock"
MODULES_DIRNAME: str = ".modules"
DEFAULT_CACHE_DIRNAME: str = ".cache"
CORE_MODULE_ID: ModuleId = ModuleId("core")
WATCHER_TASK_ID: TaskId = TaskId("core.watcher")
CONFIG_CHANGED_EVENT_ID: EventId = EventId("core.config_changed")
WORKSPACE_RELOADED_EVENT_ID: EventId = EventId("core.workspace_reloaded")
MODULE_INSTALLED_EVENT_ID: EventId = EventId("core.module_installed")
MODULE_REMOVING_EVENT_ID: EventId = EventId("core.module_removing")
SPACE_UPDATED_EVENT_ID: EventId = EventId("core.space_updated")
SPACE_REGISTRY_CHANGED_EVENT_ID: EventId = EventId("core.space_registry_changed")


@dataclass(frozen=True, slots=True)
class Empty:
    """Empty payload or output DTO for parameterless or void tasks and events."""


@dataclass(frozen=True, slots=True)
class ModuleLifecycleEventPayload:
    """Event payload emitted on core.module_removing and core.module_installed."""

    modules: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConfigChangedEventPayload:
    """Event payload emitted on core.config_changed."""

    changed_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SpaceUpdatedEventPayload:
    """Event payload emitted on core.space_updated and core.space_registry_changed."""

    spaces: tuple[str, ...] = ()


SPACE_UPDATED_EVENT: EventMetadata[SpaceUpdatedEventPayload] = EventMetadata(
    event_id=SPACE_UPDATED_EVENT_ID,
    payload_type=SpaceUpdatedEventPayload,
    ordering=EventOrdering.UNORDERED,
    description="Emitted when one or more logical spaces detect file deltas.",
)
SPACE_REGISTRY_CHANGED_EVENT: EventMetadata[SpaceUpdatedEventPayload] = EventMetadata(
    event_id=SPACE_REGISTRY_CHANGED_EVENT_ID,
    payload_type=SpaceUpdatedEventPayload,
    ordering=EventOrdering.UNORDERED,
    description="Emitted when dynamic logical space registrations change.",
)
CONFIG_CHANGED_EVENT: EventMetadata[ConfigChangedEventPayload] = EventMetadata(
    event_id=CONFIG_CHANGED_EVENT_ID,
    payload_type=ConfigChangedEventPayload,
    ordering=EventOrdering.UNORDERED,
    description="Emitted when workspace configuration files change.",
)
MODULE_INSTALLED_EVENT: EventMetadata[ModuleLifecycleEventPayload] = EventMetadata(
    event_id=MODULE_INSTALLED_EVENT_ID,
    payload_type=ModuleLifecycleEventPayload,
    ordering=EventOrdering.UNORDERED,
    description="Emitted after one or more modules are installed or updated.",
)
MODULE_REMOVING_EVENT: EventMetadata[ModuleLifecycleEventPayload] = EventMetadata(
    event_id=MODULE_REMOVING_EVENT_ID,
    payload_type=ModuleLifecycleEventPayload,
    ordering=EventOrdering.ORDERED,
    description="Ordered pre-removal hook emitted before uninstalling modules.",
)
WORKSPACE_RELOADED_EVENT: EventMetadata[Empty] = EventMetadata(
    event_id=WORKSPACE_RELOADED_EVENT_ID,
    payload_type=Empty,
    ordering=EventOrdering.UNORDERED,
    description="Emitted after workspace metadata and modules reload.",
)


def _contains_any_type_contract(tp: object) -> bool:
    if repr(tp) == "typing.Any":
        return True
    origin = get_origin(tp)
    if origin is None:
        return False
    if repr(origin) == "typing.Any":
        return True
    return any(_contains_any_type_contract(a) for a in get_args(tp))


@dataclass(frozen=True, slots=True, init=False)
class TaskRef(Generic[TIn, TOut]):
    """Lightweight immutable typed cross-module task reference binding task_id, input_type, and output_type."""

    task_id: TaskId
    input_type: type[TIn]
    output_type: type[TOut]

    def __init__(self, task_id: TaskId | str, input_type: type[TIn], output_type: type[TOut]) -> None:
        tid = task_id if isinstance(task_id, TaskId) else TaskId(require_pure_str(task_id, "TaskRef.task_id", non_empty=True))
        for tp_val, label in ((input_type, "input_type"), (output_type, "output_type")):
            if tp_val is type(None) or _contains_any_type_contract(tp_val) or not is_valid_type_annotation(tp_val):
                raise ValueError(f"TaskRef.{label} must be a valid strict non-Any type annotation, got {tp_val!r}")
        object.__setattr__(self, "task_id", tid)
        object.__setattr__(self, "input_type", input_type)
        object.__setattr__(self, "output_type", output_type)


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Immutable captured outcome from TaskContext.run_process()."""

    returncode: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    truncated: bool = False
    stdout_bytes: bytes = b""
    stderr_bytes: bytes = b""

    def __post_init__(self) -> None:
        require_pure_int(self.returncode, "ProcessResult.returncode", min_val=None, max_val=None)
        require_pure_str(self.stdout, "ProcessResult.stdout")
        require_pure_str(self.stderr, "ProcessResult.stderr")
        dur_f = safe_real_to_float(self.duration_ms, label="ProcessResult.duration_ms")
        if not math.isfinite(dur_f) or dur_f < 0.0:
            raise ValueError(f"ProcessResult.duration_ms must be finite and >= 0, got {self.duration_ms!r}")
        object.__setattr__(self, "duration_ms", dur_f)
        require_pure_bool(self.timed_out, "ProcessResult.timed_out")
        require_pure_bool(self.truncated, "ProcessResult.truncated")
        if type(self.stdout_bytes) is not bytes:
            raise ValueError(f"ProcessResult.stdout_bytes must be bytes, got {type(self.stdout_bytes).__name__}")
        if type(self.stderr_bytes) is not bytes:
            raise ValueError(f"ProcessResult.stderr_bytes must be bytes, got {type(self.stderr_bytes).__name__}")

    @property
    def ok(self) -> bool:
        """Return True iff the subprocess exited cleanly with returncode 0 and did not time out."""
        return (not self.timed_out) and self.returncode == 0


@runtime_checkable
class HumanRenderable(Protocol):
    """Optional output protocol rendering human-readable CLI output without altering SDK return values."""

    def render_text(self) -> str: ...


@runtime_checkable
class ExitCodeProvider(Protocol):
    """Optional output protocol supplying semantic CLI process exit codes."""

    def exit_code(self) -> int: ...


def format_output(output: object) -> tuple[str, int]:
    """Extract (rendered_text, exit_code) uniformly from any SDK task return object."""
    code = (
        require_pure_int(output.exit_code(), "ExitCodeProvider.exit_code()", min_val=None, max_val=None)
        if isinstance(output, ExitCodeProvider)
        else 0
    )
    if isinstance(output, HumanRenderable):
        return (require_pure_str(output.render_text(), "HumanRenderable.render_text()"), code)
    if isinstance(output, Enum) and not isinstance(output, type):
        output = output.value
    if output is None or isinstance(output, Empty):
        return ("", code)
    if type(output) is str:
        return (output, code)
    if isinstance(
        output,
        (
            bool,
            int,
            float,
            ModuleId,
            TaskId,
            EventId,
            HostPath,
            SemVer4,
            VersionConstraint,
            SemanticUri,
            SpaceId,
            SpacePath,
            SnapshotGen,
            EnvHash,
        ),
    ):
        return (str(output), code)
    if (dataclasses.is_dataclass(output) and not isinstance(output, type)) or isinstance(
        output, (Mapping, list, tuple, frozenset)
    ):
        return (json.dumps(DataclassCodec.encode(output), indent=2, ensure_ascii=False), code)
    return (str(output), code)


@dataclass(frozen=True, slots=True)
class EncodedStepOutput:
    """Typed encoded task step output with optional in-process presentation text and semantic exit code."""

    raw_output: JsonValue
    rendered_text: Optional[str] = None
    exit_code: Optional[int] = None

    def __post_init__(self) -> None:
        if self.rendered_text is not None and type(self.rendered_text) is not str:
            raise ValueError("EncodedStepOutput.rendered_text must be str or None.")
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise ValueError("EncodedStepOutput.exit_code must be int or None.")


class YscbModuleConvertible(Protocol):
    """Structural protocol for declarative Module instances convertible into runtime YscbModule."""

    def to_yscb_module(self) -> YscbModule: ...

_ALLOWED_ENV_PREFIXES: tuple[str, ...] = ("LC_", "YSCB_")
_FORBIDDEN_ENV_UPPER: frozenset[str] = frozenset(
    {
        WORKER_AUTH_ENV_KEY.upper(),
        TREE_ID_ENV_KEY.upper(),
        *(k.upper() for k in PYTHON_LAUNCHER_HIJACK_ENV_KEYS),
    }
)


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
    seen_yscb_upper: dict[str, str] = {}
    for k, v in raw_env.items():
        if type(k) is not str or type(v) is not str or not k:
            continue
        k_up = k.upper()
        if (
            not k_up.startswith(PRIVATE_ENV_PREFIX)
            and k_up not in _FORBIDDEN_ENV_UPPER
            and (k in _ALLOWED_ENV_EXACT or k.startswith(_ALLOWED_ENV_PREFIXES))
            and _is_valid_env_str(k, forbid_eq=True)
            and _is_valid_env_str(v)
        ):
            if k_up.startswith("YSCB_"):
                prev_k = seen_yscb_upper.get(k_up)
                if prev_k is not None and prev_k != k:
                    cleaned.pop(prev_k, None)
                seen_yscb_upper[k_up] = k
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
    CRITICAL = "critical"


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
    usage_pros: tuple[str, ...] = ()
    usage_cons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        cp_tup = require_typed_tuple(self.command_path, str, "CliBindingSpec.command_path")
        al_tup = require_typed_tuple(self.aliases, str, "CliBindingSpec.aliases")
        pros_tup = require_typed_tuple(self.usage_pros, str, "CliBindingSpec.usage_pros")
        cons_tup = require_typed_tuple(self.usage_cons, str, "CliBindingSpec.usage_cons")
        require_pure_str(self.summary, "CliBindingSpec.summary", non_empty=True)
        object.__setattr__(self, "command_path", cp_tup)
        object.__setattr__(self, "aliases", al_tup)
        object.__setattr__(self, "usage_pros", pros_tup)
        object.__setattr__(self, "usage_cons", cons_tup)
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
        for note_seq, note_label in ((self.usage_pros, "usage_pros"), (self.usage_cons, "usage_cons")):
            if any((not line.strip() or not _is_valid_env_str(line)) for line in note_seq):
                raise ValueError(f"CliBindingSpec {note_label} entries must be non-empty valid UTF-8 strings.")


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
    if spec.interactive_tty and spec.exposure == TaskExposure.SDK_ONLY:
        raise ValueError(f"SDK_ONLY Task '{spec.task_id}' cannot declare interactive_tty=True.")
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
    if spec.security_tier in (SecurityTier.GATED, SecurityTier.CRITICAL):
        if spec.exposure == TaskExposure.INTERNAL_TRIGGER or spec.subscriptions or spec.periodic is not None:
            raise ValueError(f"{spec.security_tier.name} Task '{spec.task_id}' cannot bind INTERNAL_TRIGGER, events, or periodic timers.")
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


@dataclass(frozen=True, slots=True)
class CallPropagationContext:
    """Immutable cross-hop call tree, causal lineage, profiling flag, and container reentrancy state."""

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
    profile_mem: bool = False

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
            (self.profile_mem, "profile_mem"),
        ):
            require_pure_bool(flag, f"CallPropagationContext.{label}")
        object.__setattr__(self, "call_stack", validate_host_task_pairs(self.call_stack, "call_stack"))
        object.__setattr__(self, "hot_workspaces", require_typed_frozenset(self.hot_workspaces, HostPath, "hot_workspaces"))
        object.__setattr__(
            self,
            "cold_shared_workspaces",
            require_typed_frozenset(self.cold_shared_workspaces, HostPath, "cold_shared_workspaces"),
        )


def _validate_profiler_contract(prof: Profiler, label: str) -> None:
    try:
        m_scope = prof.scope
        m_rel = prof.scope_relative
        m_merge = prof.merge_subtree
        m_snap = prof.snapshot
        m_span = prof.current_span_path
    except AttributeError as exc:
        raise ValueError(f"Invalid Profiler on {label}: {prof!r}") from exc
    if not (
        callable(m_scope)
        and callable(m_rel)
        and callable(m_merge)
        and callable(m_snap)
        and callable(m_span)
    ):
        raise ValueError(f"Invalid Profiler methods on {label}: {prof!r}")


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
        if not _is_valid_env_str(k, forbid_eq=True) or not _is_valid_env_str(v):
            raise ValueError("InvokeRequest.caller_env keys forbid '=' and keys/values forbid NUL and lone surrogates.")
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
    profile_mem: bool = False
    external_flight_owner: bool = False
    active_profiler: Optional[Profiler] = None
    include_presentation: bool = False
    skip_module_init: bool = False

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
        require_pure_bool(self.profile_mem, "InvokeRequest.profile_mem")
        require_pure_bool(self.external_flight_owner, "InvokeRequest.external_flight_owner")
        require_pure_bool(self.include_presentation, "InvokeRequest.include_presentation")
        require_pure_bool(self.skip_module_init, "InvokeRequest.skip_module_init")
        if not isinstance(self.propagation, CallPropagationContext):
            raise ValueError("InvokeRequest.propagation must be CallPropagationContext.")
        if self.active_profiler is not None:
            _validate_profiler_contract(self.active_profiler, "InvokeRequest.active_profiler")
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
    rendered_text: Optional[str] = None
    exit_code: Optional[int] = None

    def __post_init__(self) -> None:
        for flag, label in ((self.ok, "ok"), (self.coalesced, "coalesced"), (self.executed_hot, "executed_hot")):
            require_pure_bool(flag, f"TaskOutcome.{label}")
        if self.error is not None and not isinstance(self.error, ErrorDetail):
            raise ValueError("TaskOutcome.error must be ErrorDetail or None.")
        if self.rendered_text is not None and type(self.rendered_text) is not str:
            raise ValueError("TaskOutcome.rendered_text must be str or None.")
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise ValueError("TaskOutcome.exit_code must be int or None.")
        for diag_seq, attr_nm in (
            (self.event_diagnostics, "event_diagnostics"),
            (self.teardown_diagnostics, "teardown_diagnostics"),
        ):
            object.__setattr__(self, attr_nm, require_typed_tuple(diag_seq, ErrorDetail, f"TaskOutcome.{attr_nm}"))


@dataclass(frozen=True, slots=True)
class ModuleRuntimeServices:
    """Managed module runtime service bundle symmetrically injected across Tier 0 and Tier 1."""

    module_id: ModuleId
    workspace_root: HostPath
    vfs: ScopedVfs
    logger: StructuredLogger
    locale: LocaleCatalog
    config_loader: Callable[[type[object]], object]
    contributes_loader: Callable[[], AggregatedContributes]
    profiler: Profiler = field(default_factory=NullProfiler)

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, ModuleId):
            raise ValueError(f"ModuleRuntimeServices.module_id must be ModuleId, got {self.module_id!r}")
        if not isinstance(self.workspace_root, HostPath):
            raise ValueError(f"ModuleRuntimeServices.workspace_root must be HostPath, got {self.workspace_root!r}")
        if not isinstance(self.vfs, ScopedVfs):
            raise ValueError(f"ModuleRuntimeServices.vfs must be ScopedVfs, got {self.vfs!r}")
        if not isinstance(self.locale, LocaleCatalog):
            raise ValueError(f"ModuleRuntimeServices.locale must be LocaleCatalog, got {self.locale!r}")
        try:
            log_m = self.logger.log
        except AttributeError as exc:
            raise ValueError(f"Invalid StructuredLogger on ModuleRuntimeServices: {self.logger!r}") from exc
        if not callable(log_m):
            raise ValueError(f"Invalid StructuredLogger.log on ModuleRuntimeServices: {self.logger!r}")
        if not callable(self.config_loader) or not callable(self.contributes_loader):
            raise ValueError("ModuleRuntimeServices config_loader and contributes_loader must be callable.")
        _validate_profiler_contract(self.profiler, "ModuleRuntimeServices")


def _unwrap_space_outcome(outcome: TaskOutcome[TOut]) -> TOut:
    if not outcome.ok:
        if outcome.error is not None:
            outcome.error.raise_as_exception()
        raise YscbError(ErrorCode.BUSINESS_FAILURE, "Space operation failed without error detail.")
    return cast(TOut, outcome.value)


def _normalize_space_id_str(space_id: SpaceId | str, label: str = "space_id") -> str:
    if isinstance(space_id, SpaceId):
        return str(space_id)
    return str(SpaceId.parse(require_pure_str(space_id, label, non_empty=True)))


class SpaceClient:
    """First-class module facade over Core 2.0 logical spaces backed transparently by core.space.* system tasks."""

    __slots__ = ("_ctx",)

    def __init__(self, ctx: TaskContext) -> None:
        if not isinstance(ctx, TaskContext):
            raise ValueError(f"SpaceClient requires TaskContext, got {ctx!r}")
        self._ctx = ctx

    def list_spaces(self, *, owner: Optional[str] = None) -> tuple[SpaceSpec, ...]:
        """List registered logical spaces, optionally filtered by owner module ID."""
        if owner is not None:
            require_pure_str(owner, "owner", non_empty=True)
        out = self._ctx.call("core.space.list", {"owner": owner}, output_type=tuple[SpaceSpec, ...])
        return _unwrap_space_outcome(out)

    def status(self, space_id: SpaceId | str) -> SpaceStatusSnapshot:
        """Return SQLite WAL generation, Merkle root, and consumer cursors for a logical space."""
        sid = _normalize_space_id_str(space_id)
        out = self._ctx.call("core.space.status", {"space_id": sid}, output_type=SpaceStatusSnapshot)
        return _unwrap_space_outcome(out)

    def list_files(self, space_id: SpaceId | str, *, pattern: Optional[str] = None) -> tuple[SpaceFileEntry, ...]:
        """Enumerate matched files inside a logical space with optional glob pattern filtering."""
        sid = _normalize_space_id_str(space_id)
        if pattern is not None:
            require_pure_str(pattern, "pattern", non_empty=True)
        out = self._ctx.call(
            "core.space.files",
            {"space_id": sid, "pattern": pattern},
            output_type=tuple[SpaceFileEntry, ...],
        )
        return _unwrap_space_outcome(out)

    def diff(self, space_id: SpaceId | str, *, consumer: Optional[str] = None) -> SpaceDiffBatch:
        """Read unacknowledged incremental file deltas for a consumer cursor (defaulting to current module_id)."""
        sid = _normalize_space_id_str(space_id)
        eff_consumer = self._ctx.module_id.value if consumer is None else require_pure_str(consumer, "consumer", non_empty=True)
        out = self._ctx.call(
            "core.space.diff",
            {"space_id": sid, "consumer": eff_consumer},
            output_type=SpaceDiffBatch,
        )
        return _unwrap_space_outcome(out)

    def scan(self, space_id: Optional[SpaceId | str] = None, *, force: bool = False) -> tuple[SpaceDiffBatch, ...]:
        """Trigger an incremental two-stage SQLite WAL scan across one or all logical spaces."""
        sid = None if space_id is None else _normalize_space_id_str(space_id)
        require_pure_bool(force, "force")
        out = self._ctx.call(
            "core.space.scan",
            {"space_id": sid, "force": force},
            output_type=tuple[SpaceDiffBatch, ...],
        )
        return _unwrap_space_outcome(out)

    def ack_cursor(self, batch: SpaceDiffBatch, *, consumer: Optional[str] = None) -> bool:
        """Advance a consumer cursor using compare-and-swap verification against a SpaceDiffBatch."""
        if not isinstance(batch, SpaceDiffBatch):
            raise ValueError(f"SpaceClient.ack_cursor requires SpaceDiffBatch, got {batch!r}")
        eff_consumer = self._ctx.module_id.value if consumer is None else require_pure_str(consumer, "consumer", non_empty=True)
        raw_out = self._ctx.call(
            "core.space.ack_cursor",
            {
                "space": str(batch.space_id),
                "consumer": eff_consumer,
                "from_gen": batch.from_gen.value,
                "to_gen": batch.to_gen.value,
                "config_hash": batch.config_hash,
                "merkle_root": batch.merkle_root,
            },
        )
        val = _unwrap_space_outcome(raw_out)
        if type(val) is bool:
            return val
        if isinstance(val, Mapping):
            payload = val.get("data") if "data" in val else val
            if isinstance(payload, Mapping) and type(payload.get("acked")) is bool:
                return cast(bool, payload["acked"])
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unexpected core.space.ack_cursor response: {val!r}")

    def set_dynamic(self, name: str, spec: SpaceSpec) -> bool:
        """Register or update a dynamic logical space owned by the calling module."""
        require_pure_str(name, "name", non_empty=True)
        if not isinstance(spec, SpaceSpec):
            raise ValueError(f"SpaceClient.set_dynamic requires SpaceSpec, got {spec!r}")
        out = self._ctx.call(
            "core.space.set_dynamic",
            {
                "owner": self._ctx.module_id.value,
                "name": name,
                "spec": DataclassCodec.encode_object(spec),
            },
            output_type=bool,
        )
        return _unwrap_space_outcome(out)

    def clear_dynamic(self, name: Optional[str] = None) -> int:
        """Remove one or all dynamic logical spaces owned by the calling module."""
        if name is not None:
            require_pure_str(name, "name", non_empty=True)
        out = self._ctx.call(
            "core.space.clear_dynamic",
            {"owner": self._ctx.module_id.value, "name": name},
            output_type=int,
        )
        return _unwrap_space_outcome(out)

    def resolve_uri(self, space_id: SpaceId | str, rel_path: SpacePath | str) -> SemanticUri:
        """Resolve a space-relative SpacePath into a caller-validated SemanticUri usable with ctx.vfs."""
        sid = _normalize_space_id_str(space_id)
        sp = rel_path if isinstance(rel_path, SpacePath) else SpacePath.parse(require_pure_str(rel_path, "rel_path", non_empty=True))
        out = self._ctx.call(
            "core.space.resolve_uri",
            {"space_id": sid, "rel_path": str(sp)},
            output_type=SemanticUri,
        )
        return _unwrap_space_outcome(out)

    def match_spaces(self, target: SemanticUri | HostPath | str) -> tuple[SpaceId, ...]:
        """Return all logical SpaceIds whose compiled rules match the caller-readable target URI or path."""
        if isinstance(target, (SemanticUri, HostPath)):
            raw_target = str(target)
        elif type(target) is str:
            raw_target = require_pure_str(target, "target", non_empty=True)
        else:
            raise ValueError(f"SpaceClient.match_spaces requires SemanticUri, HostPath, or str, got {target!r}")
        out = self._ctx.call(
            "core.space.match_spaces",
            {"target": raw_target},
            output_type=tuple[SpaceId, ...],
        )
        return _unwrap_space_outcome(out)


def _resolve_run_process_cwd(ctx: TaskContext, cwd: Optional[SemanticUri | HostPath | str]) -> HostPath:
    if cwd is None:
        cwd_hp = ctx.caller_cwd
    elif isinstance(cwd, (SemanticUri, HostPath)) or type(cwd) is str:
        raw_target = str(cwd) if isinstance(cwd, (SemanticUri, HostPath)) else cwd
        resolved_uri = ctx.resolve_uri(raw_target)
        phys = ctx.vfs.try_get_physical_path(resolved_uri)
        if phys is None:
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Cannot run subprocess in virtual URI without physical path: '{cwd}'.",
            )
        cwd_hp = phys
    else:
        raise ValueError(f"run_process cwd must be SemanticUri, HostPath, str, or None, got {cwd!r}")
    if not cwd_hp.path.is_dir():
        raise FileNotFoundError(f"Subprocess working directory does not exist: '{cwd_hp}'")
    return cwd_hp


def _set_case_normalized_env(env_map: dict[str, str], key: str, value: str) -> None:
    if IS_WINDOWS:
        k_up = key.upper()
        for existing_k in [ek for ek in env_map if ek != key and ek.upper() == k_up]:
            env_map.pop(existing_k, None)
    env_map[key] = value


def _build_run_process_env(
    ctx: TaskContext,
    env: Optional[Mapping[str, str]],
    *,
    inherit_toolchain_env: bool = True,
) -> dict[str, str]:
    merged = build_isolated_python_env(include_toolchain_env=inherit_toolchain_env)
    stripped_tc_upper = (TOOLCHAIN_ENV_ALLOWLIST | frozenset({"ALL_PROXY"})) if not inherit_toolchain_env else frozenset()
    if stripped_tc_upper:
        for existing_k in [ek for ek in merged if ek.upper() in stripped_tc_upper]:
            merged.pop(existing_k, None)
    for ck, cv in sanitize_caller_env(ctx.caller_env).items():
        if stripped_tc_upper and ck.upper() in stripped_tc_upper:
            continue
        _set_case_normalized_env(merged, ck, cv)
    if env is None:
        return merged
    if not isinstance(env, Mapping):
        raise ValueError(f"run_process env must be Mapping[str, str] or None, got {type(env).__name__}")
    for k, v in env.items():
        require_pure_str(k, "run_process env key", non_empty=True)
        require_pure_str(v, "run_process env value")
        if not _is_valid_env_str(k, forbid_eq=True) or not _is_valid_env_str(v):
            raise ValueError("run_process env keys forbid '=' and keys/values forbid NUL and lone surrogates.")
        k_up = k.upper()
        if k_up.startswith(PRIVATE_ENV_PREFIX) or k_up in _FORBIDDEN_ENV_UPPER:
            raise ValueError(f"run_process env key {k!r} is reserved or forbidden.")
        _set_case_normalized_env(merged, k, v)
    return merged


def _write_stdin_bytes(pipe: Optional[BinaryIO], data: bytes, stop_event: threading.Event) -> None:
    if pipe is None:
        return
    try:
        view = memoryview(data)
        total = len(view)
        offset = 0
        while offset < total and not stop_event.is_set():
            written = pipe.write(view[offset : offset + 16384])
            if written is None or written <= 0:
                break
            offset += written
    except (BrokenPipeError, OSError, ValueError):
        pass
    finally:
        try:
            pipe.close()
        except OSError:
            pass


def _drain_pipe_bounded(pipe: Optional[BinaryIO], max_bytes: int, sink: list[bytes], trunc_flag: list[bool]) -> None:
    if pipe is None:
        return
    collected = 0
    while True:
        try:
            chunk = pipe.read(8192)
        except (OSError, ValueError):
            break
        if not chunk:
            break
        if collected < max_bytes:
            rem = max_bytes - collected
            if len(chunk) <= rem:
                sink.append(chunk)
                collected += len(chunk)
            else:
                sink.append(chunk[:rem])
                collected = max_bytes
                trunc_flag[0] = True
        else:
            trunc_flag[0] = True


class TaskContext(ABC):
    """Explicit execution context passed into Task.run(req, ctx) with zero global singletons."""

    @property
    @abstractmethod
    def module_id(self) -> ModuleId: ...

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

    @property
    @abstractmethod
    def vfs(self) -> ScopedVfs: ...

    @property
    @abstractmethod
    def logger(self) -> StructuredLogger: ...

    @property
    @abstractmethod
    def locale(self) -> LocaleCatalog: ...

    @property
    def profiler(self) -> Profiler:
        return NullProfiler()

    @abstractmethod
    def load_config(self, config_cls: type[TConfig]) -> TConfig: ...

    @abstractmethod
    def load_contributes(self) -> AggregatedContributes: ...

    @abstractmethod
    def emit(self, event_meta: EventMetadata[TPayload], payload: TPayload) -> None: ...

    @abstractmethod
    def emit_imm(self, event_meta: EventMetadata[TPayload], payload: TPayload, *, strict: bool = False) -> None: ...

    @property
    def spaces(self) -> SpaceClient:
        """Return a first-class SpaceClient bound to this TaskContext."""
        return SpaceClient(self)

    def resolve_uri(self, raw_path: str) -> SemanticUri:
        """Resolve a caller-supplied URI or local path relative to caller_cwd into a validated SemanticUri."""
        return self.vfs.resolve_caller_uri(raw_path, self.caller_cwd)

    def run_process(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[SemanticUri | HostPath | str] = None,
        env: Optional[Mapping[str, str]] = None,
        input: Optional[str | bytes] = None,
        inherit_toolchain_env: bool = True,
        timeout_sec: float = 60.0,
        max_output_bytes: int = 1048576,
    ) -> ProcessResult:
        """Run a managed child process tree with optional stdin, raw bytes output, cancel_token teardown, and isolated env."""
        clean_argv = require_typed_tuple(argv, str, "run_process argv")
        if not clean_argv or any((not seg and idx == 0) or not _is_valid_env_str(seg) for idx, seg in enumerate(clean_argv)):
            raise ValueError("run_process argv must be a non-empty UTF-8 NUL-free Sequence[str] with non-empty program.")
        require_pure_bool(inherit_toolchain_env, "run_process inherit_toolchain_env")
        stdin_bytes: Optional[bytes]
        if input is None:
            stdin_bytes = None
        elif type(input) is bytes:
            stdin_bytes = input
        elif type(input) is str:
            try:
                stdin_bytes = input.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("run_process input str must be valid UTF-8 without lone surrogates.") from exc
        else:
            raise ValueError(f"run_process input must be str, bytes, or None, got {type(input).__name__}")
        timeout_f = safe_real_to_float(timeout_sec, label="run_process timeout_sec")
        if not math.isfinite(timeout_f) or timeout_f <= 0.0:
            raise ValueError(f"run_process timeout_sec must be finite and > 0, got {timeout_sec!r}")
        max_bytes = require_pure_int(max_output_bytes, "run_process max_output_bytes", min_val=0, max_val=INT64_MAX)
        cwd_hp = _resolve_run_process_cwd(self, cwd)
        merged_env = _build_run_process_env(self, env, inherit_toolchain_env=inherit_toolchain_env)
        self.cancel_token.raise_if_cancelled()
        t0 = time.monotonic()
        deadline = t0 + timeout_f
        out_chunks: list[bytes] = []
        err_chunks: list[bytes] = []
        out_trunc: list[bool] = [False]
        err_trunc: list[bool] = [False]
        timed_out = False
        cancelled = False
        rc: Optional[int] = None
        with self.profiler.scope_relative("Proc/Run"):
            with ManagedProcessTree(
                clean_argv,
                cwd=cwd_hp,
                env=merged_env,
                capture_output=True,
                pipe_stdin=(stdin_bytes is not None),
            ) as tree:
                started_threads: list[threading.Thread] = []
                stdin_stop = threading.Event()
                step = 0.002
                try:
                    for pipe_obj, sink_buf, trunc_ref in (
                        (tree.stdout_pipe, out_chunks, out_trunc),
                        (tree.stderr_pipe, err_chunks, err_trunc),
                    ):
                        reader = threading.Thread(
                            target=_drain_pipe_bounded,
                            args=(pipe_obj, max_bytes, sink_buf, trunc_ref),
                            daemon=True,
                        )
                        reader.start()
                        started_threads.append(reader)
                    if stdin_bytes is not None:
                        writer = threading.Thread(
                            target=_write_stdin_bytes,
                            args=(tree.stdin_pipe, stdin_bytes, stdin_stop),
                            daemon=True,
                        )
                        writer.start()
                        started_threads.append(writer)
                    while True:
                        rc = tree.poll()
                        if rc is not None:
                            break
                        if self.cancel_token.is_cancelled:
                            cancelled = True
                            stdin_stop.set()
                            tree.terminate_tree()
                            break
                        now = time.monotonic()
                        if now >= deadline:
                            timed_out = True
                            stdin_stop.set()
                            tree.terminate_tree()
                            break
                        time.sleep(min(step, max(0.001, deadline - now)))
                        step = min(0.015, step * 1.5)
                finally:
                    stdin_stop.set()
                    if rc is None:
                        tree.terminate_tree()
                    for io_thread in started_threads:
                        io_thread.join(timeout=2.0)
                    tree.close_pipes()
        if cancelled:
            self.cancel_token.raise_if_cancelled()
            raise TaskCancelledException(f"Subprocess '{clean_argv[0]}' cancelled.")
        duration_ms = max(0.0, round((time.monotonic() - t0) * 1000.0, 3))
        raw_out_bytes = b"".join(out_chunks)
        raw_err_bytes = b"".join(err_chunks)
        return ProcessResult(
            returncode=-1 if timed_out else (rc if rc is not None else -1),
            stdout=raw_out_bytes.decode("utf-8", errors="replace"),
            stderr=raw_err_bytes.decode("utf-8", errors="replace"),
            duration_ms=duration_ms,
            timed_out=timed_out,
            truncated=out_trunc[0] or err_trunc[0],
            stdout_bytes=raw_out_bytes,
            stderr_bytes=raw_err_bytes,
        )

    @overload
    def call(
        self,
        target: TaskRef[Empty, TOut],
        input_obj: Optional[Empty] = None,
        *,
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def call(
        self,
        target: TaskRef[TIn, TOut],
        input_obj: TIn,
        *,
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def call(
        self,
        target: TaskId | str,
        input_obj: object = None,
        *,
        output_type: type[TOut],
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def call(
        self,
        target: TaskId | str,
        input_obj: object = None,
        *,
        output_type: None = None,
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[JsonValue]: ...

    @abstractmethod
    def call(
        self,
        target: TaskRef[TIn, TOut] | TaskId | str,
        input_obj: object = None,
        *,
        output_type: Optional[type[TOut]] = None,
        target_workspace: Optional[HostPath] = None,
        routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]: ...

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

    def execute_encoded_with_presentation(
        self,
        raw_input: JsonObject,
        ctx: TaskContext,
        *,
        include_presentation: bool = False,
    ) -> EncodedStepOutput:
        raw_out = self.execute_encoded(raw_input, ctx)
        if not include_presentation:
            return EncodedStepOutput(raw_output=raw_out)
        rendered, code = format_output(raw_out)
        return EncodedStepOutput(raw_output=raw_out, rendered_text=rendered, exit_code=code)


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

    def execute_encoded_with_presentation(
        self,
        raw_input: JsonObject,
        ctx: TaskContext,
        *,
        include_presentation: bool = False,
    ) -> EncodedStepOutput:
        typed_in = DataclassCodec.decode(self.metadata.input_type, raw_input)
        typed_out = self.run(typed_in, ctx)
        raw_out = DataclassCodec.encode_typed(self.metadata.output_type, typed_out)
        if not include_presentation:
            return EncodedStepOutput(raw_output=raw_out)
        is_human = isinstance(typed_out, HumanRenderable)
        is_exit = isinstance(typed_out, ExitCodeProvider)
        if not is_human and not is_exit:
            return EncodedStepOutput(
                raw_output=raw_out,
                rendered_text="" if isinstance(typed_out, Empty) else None,
                exit_code=0,
            )
        rendered: Optional[str] = None
        code: Optional[int] = None
        if is_human:
            rendered, code = format_output(typed_out)
        elif is_exit:
            code = require_pure_int(typed_out.exit_code(), "ExitCodeProvider.exit_code()", min_val=None, max_val=None)
        return EncodedStepOutput(raw_output=raw_out, rendered_text=rendered, exit_code=code)


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
            rendered_text=outcome.rendered_text,
            exit_code=outcome.exit_code,
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
