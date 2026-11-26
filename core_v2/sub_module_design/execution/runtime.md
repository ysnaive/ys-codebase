# 子模組架構設計規格：`core.execution.runtime`（全系統唯一 Task 派發、對稱單飛合併與隔離執行協調中樞）

> **所屬功能域**：`Domain 5 — 執行與常駐調度域 (execution/)`
> **模組路徑**：`core_v2/source/core/core/execution/runtime/`
> **內部模組職責切分**：`contracts.py`、`coordinator.py`、`gates.py`、`module_slot.py`、`route_index.py`、`services.py`、`turn_session.py`、`step_host.py`、`worker_entry.py`、`worker_pool.py`、`wire.py`、`dispatcher.py`
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.{fs, vfs, storage, space}`、`metadata.{config, contributes}`、`execution.{rpc, lifecycle, event}`
> **禁止反向依賴（Forbidden Imports）**：`execution.daemon`、`packaging/*`、`surface/*`
> **狀態**：`Active Living Spec — Single-Flight Top-Level Coalesce, Global Quiesce Barrier & Symmetric Module Services`

## 1. 核心公理與單點封閉使命 (Core Axiom & Single-Point Mission)

`core.execution.runtime` 的最高準則為：**將全系統所有功能派發、冷熱路由、環境隔離執行與資源並發協調問題 100% 封閉鎖死在本模組單點維護，且以根因正交模型取代過渡補丁**。

### 1.1 萬物皆 `Task`、顯式傳播組合與零逆向依賴邊界
1. **唯一公開執行單元**：全生態系所有可被 CLI、SDK、跨模組調用、事件、定時排程或升級遷移觸發的能力，**100% 實作為 `Task[TIn, TOut]` 並附帶強型別 `TaskMetadata`**。支援磁碟 `.modules/` 與無磁碟 `DispatcherHostOptions.in_memory_modules` 雙軌註冊；即便兩模組共置於同一 `venv_group` 子進程，跨模組呼叫 `ctx.call()` **仍必須經由主控端 `RuntimeDispatcher` 協調**。
2. **顯式 11 欄位傳播上下文（`CallPropagationContext`）與跨 Tier 服務注入（`ModuleRuntimeServices`）**：將跨單步/跨進程傳遞之呼叫狀態（含 `profile_mem`）收斂為 11 欄位不可變值物件；透過 `DispatcherHostOptions.module_services_factory` 與 `WorkerBootstrapConfig.host_dir` 對稱注入 `ScopedVfs`、`StructuredLogger`（寫入 `.cache/logs/modules/<module>.jsonl` 並關聯 `trace_id`/`span_id`）、`LocaleCatalog`、`ConfigStore`、`ContributesAggregator` 與 `Profiler`。
3. **頂層單工作區單飛合併（`StepFlight`）與全域 `QUIESCE` 單屏障（`LifecycleReloadGate`）**：
   - **頂層同工作區 `StepFlight`**：`COALESCE` 僅於非事件鏈之頂層同工作區熱呼叫啟用對稱單飛合併；任何巢狀呼叫與事件鏈呼叫自動降級為 `SERIALIZE`。
   - **全域單一 `QUIESCE` 屏障**：`LifecycleReloadGate` 以全域 `quiesce_epoch` 與單一租約門檻統一控管停止/重載與租約續期／逾時自癒恢復。
4. **純淨 `sys.meta_path` 隔離套件與零樣板模組載入（`module_slot.py`）**：透過 `_ScopedModuleFinder` 與直接呼叫幀限定之 `importlib.import_module` 轉發，零全域 `sys.path` / `sys.modules` 頂層污染；`ProtectedModuleLoader.load_module_artifact` 優先呼叫 `create_module()`，若缺席則自動偵測入口檔自身定義之唯一具象非抽象模組子類（排除 `ABC` 與 `Protocol`）。
5. **一等空間門面、受管子行程與強型別系統事件（`contracts.py`）**：`TaskContext` 提供 `module_id`、`spaces: SpaceClient`（透明路由至 `core.space.*`）、`resolve_uri`、`run_process`（復用 `ManagedProcessTree(capture_output=True)` 與隔離環境、保留 `TASK_PREEMPTED` 搶佔語意）及重載統一之 `call(TaskRef | TaskId | str, ...)`，並統一承載 `Empty`、3 組事件 Payload 與 6 組強型別系統 `EventMetadata`（其中 `MODULE_REMOVING_EVENT` 為 `ORDERED`）。
6. **與 `execution.daemon` 零逆向耦合**：`runtime` 透過 `execution.rpc` 唯讀探測線上 Daemon，並透過外層注入的 `DaemonSpawner(Protocol)` 按需背景拉起 Daemon，**`runtime` 內部 0 行匯入 `execution.daemon`**。
7. **消費端擁有之 `ModuleProviderPort` 契約**：`ModuleProviderPort` 及 `ModuleDescriptor` / `TaskRouteSpec` 由 `execution.runtime` 定義並擁有。
8. **跨進程 `SERIALIZE` 單跳 `.pin` 免死鎖重入與 4 階安全分級守門**：`SecurityTier.CRITICAL` 與 `SecurityTier.GATED` 強制要求 `approval_scope`，且 `CRITICAL` 額外阻斷任何非頂層前景呼叫。

## 2. 核心契約規格 (`contracts.py` & `services.py` 公開快照)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Generic, Mapping, Optional, Protocol, Sequence, TypeVar, overload
from core.execution.event import BoundEventSubscription, CausalLineage, EventMetadata, EventOrdering
from core.filesystem.space import SpaceDiffBatch, SpaceFileEntry, SpaceSpec, SpaceStatusSnapshot
from core.filesystem.vfs import ScopedVfs, VfsHub
from core.foundation.errors import ErrorDetail
from core.foundation.observability import CancellationToken, LocaleCatalog, ProgressEvent, StructuredLogger
from core.foundation.primitives import EventId, HostPath, JsonObject, JsonPrimitive, JsonValue, ModuleId, SemanticUri, SpaceId, TaskId
from core.foundation.profiler import NullProfiler, Profiler
from core.metadata.config import ConfigStore
from core.metadata.contributes import AggregatedContributes, ContributesAggregator

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")
TOut_co = TypeVar("TOut_co", covariant=True)
TPayload = TypeVar("TPayload")
TConfig = TypeVar("TConfig")

EnvLeaseAcquireFn = Callable[[HostPath], Optional[Callable[[], None]]]
EnvTouchUsedFn = Callable[[HostPath], None]


WORKER_AUTH_ENV_KEY: str = "_YSCB_WORKER_AUTH_TOKEN"
LOCKS_SUBDIR: str = "locks"
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
    pass


@dataclass(frozen=True, slots=True)
class ModuleLifecycleEventPayload:
    modules: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConfigChangedEventPayload:
    changed_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SpaceUpdatedEventPayload:
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


@dataclass(frozen=True, slots=True, init=False)
class TaskRef(Generic[TIn, TOut]):
    task_id: TaskId
    input_type: type[TIn]
    output_type: type[TOut]
    def __init__(self, task_id: TaskId | str, input_type: type[TIn], output_type: type[TOut]) -> None: ...


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    truncated: bool = False
    @property
    def ok(self) -> bool: ...


class YscbModuleConvertible(Protocol):
    def to_yscb_module(self) -> YscbModule: ...


class SpaceClient:
    def __init__(self, ctx: TaskContext) -> None: ...
    def list_spaces(self, *, owner: Optional[str] = None) -> tuple[SpaceSpec, ...]: ...
    def status(self, space_id: SpaceId | str) -> SpaceStatusSnapshot: ...
    def list_files(self, space_id: SpaceId | str, *, pattern: Optional[str] = None) -> tuple[SpaceFileEntry, ...]: ...
    def diff(self, space_id: SpaceId | str, *, consumer: Optional[str] = None) -> SpaceDiffBatch: ...
    def scan(self, space_id: Optional[SpaceId | str] = None, *, force: bool = False) -> tuple[SpaceDiffBatch, ...]: ...
    def ack_cursor(self, batch: SpaceDiffBatch, *, consumer: Optional[str] = None) -> bool: ...
    def set_dynamic(self, name: str, spec: SpaceSpec) -> bool: ...
    def clear_dynamic(self, name: Optional[str] = None) -> int: ...


def sanitize_caller_env(raw_env: Mapping[str, str]) -> dict[str, str]: ...


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
    default_interval_sec: float
    enabled_config_key: Optional[str] = None
    interval_config_key: Optional[str] = None


@dataclass(frozen=True, slots=True)
class CliBindingSpec:
    command_path: tuple[str, ...]
    summary: str
    aliases: tuple[str, ...] = ()
    usage_pros: tuple[str, ...] = ()
    usage_cons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SubscriptionRouteSpec:
    event_id: EventId
    payload_filter: Optional[Mapping[str, tuple[JsonPrimitive, ...]]] = None


@dataclass(frozen=True, slots=True)
class TaskRouteSpec:
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


@dataclass(frozen=True, slots=True)
class TaskMetadata(Generic[TIn, TOut]):
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

    def to_route_spec(self) -> TaskRouteSpec: ...


@dataclass(frozen=True, slots=True)
class CallPropagationContext:
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


@dataclass(frozen=True, slots=True)
class InvokeRequest:
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


@dataclass(frozen=True, slots=True)
class TaskOutcome(Generic[TOut_co]):
    ok: bool
    value: Optional[TOut_co] = None
    error: Optional[ErrorDetail] = None
    event_diagnostics: tuple[ErrorDetail, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    coalesced: bool = False
    executed_hot: bool = False


@dataclass(frozen=True, slots=True)
class ModuleRuntimeServices:
    module_id: ModuleId
    workspace_root: HostPath
    vfs: ScopedVfs
    logger: StructuredLogger
    locale: LocaleCatalog
    config_loader: Callable[[type[object]], object]
    contributes_loader: Callable[[], AggregatedContributes]
    profiler: Profiler = field(default_factory=NullProfiler)


def build_default_module_services(workspace_root: HostPath, module_id: ModuleId) -> ModuleRuntimeServices: ...


def build_workspace_module_services_factory(
    host_dir: HostPath,
    yscb_root: HostPath,
    *,
    config_store: Optional[ConfigStore] = None,
    contributes_aggregator: Optional[ContributesAggregator] = None,
    vfs_hub: Optional[VfsHub] = None,
    locale_getter: Optional[Callable[[], LocaleCatalog]] = None,
) -> Callable[[ModuleId], ModuleRuntimeServices]: ...


def resolve_active_module_services(workspace_root: HostPath, module_id: ModuleId) -> ModuleRuntimeServices: ...


def resolve_active_caller_module() -> Optional[ModuleId]: ...


def resolve_active_call_tree_id() -> Optional[str]: ...


class TaskContext(ABC):
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
    def profiler(self) -> Profiler: ...
    @abstractmethod
    def load_config(self, config_cls: type[TConfig]) -> TConfig: ...
    @abstractmethod
    def load_contributes(self) -> AggregatedContributes: ...
    @abstractmethod
    def emit(self, event_meta: EventMetadata[TPayload], payload: TPayload) -> None: ...
    @abstractmethod
    def emit_imm(self, event_meta: EventMetadata[TPayload], payload: TPayload, *, strict: bool = False) -> None: ...
    @property
    def spaces(self) -> SpaceClient: ...
    def resolve_uri(self, raw_path: str) -> SemanticUri: ...
    def run_process(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[SemanticUri | HostPath | str] = None,
        env: Optional[Mapping[str, str]] = None,
        timeout_sec: float = 60.0,
        max_output_bytes: int = 1048576,
    ) -> ProcessResult: ...
    @overload
    def call(
        self, target: TaskRef[Empty, TOut], input_obj: Optional[Empty] = None, *,
        target_workspace: Optional[HostPath] = None, routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut]: ...
    @overload
    def call(
        self, target: TaskRef[TIn, TOut], input_obj: TIn, *,
        target_workspace: Optional[HostPath] = None, routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut]: ...
    @overload
    def call(
        self, target: TaskId | str, input_obj: object = None, *, output_type: type[TOut],
        target_workspace: Optional[HostPath] = None, routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut]: ...
    @overload
    def call(
        self, target: TaskId | str, input_obj: object = None, *, output_type: None = None,
        target_workspace: Optional[HostPath] = None, routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[JsonValue]: ...
    @abstractmethod
    def call(
        self, target: TaskRef[TIn, TOut] | TaskId | str, input_obj: object = None, *, output_type: Optional[type[TOut]] = None,
        target_workspace: Optional[HostPath] = None, routing_policy: Optional[ClientRoutingPolicy] = None,
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]: ...
    @abstractmethod
    def report_progress(self, progress: ProgressEvent) -> None: ...


class BoundTask(ABC):
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
    def map_subscription_batch(self, event_id: EventId, raw_payloads: Sequence[JsonObject]) -> tuple[bool, JsonObject]: ...
    @abstractmethod
    def execute_encoded(self, raw_input: JsonObject, ctx: TaskContext) -> JsonValue: ...


class Task(BoundTask, Generic[TIn, TOut]):
    @property
    @abstractmethod
    def metadata(self) -> TaskMetadata[TIn, TOut]: ...
    @abstractmethod
    def run(self, req: TIn, ctx: TaskContext) -> TOut: ...
    @property
    def task_id(self) -> TaskId: ...
    @property
    def route_spec(self) -> TaskRouteSpec: ...
    @property
    def interactive_tty(self) -> bool: ...
    def compute_normalized_equivalence(self, raw_input: JsonObject) -> str: ...
    def map_subscription_batch(self, event_id: EventId, raw_payloads: Sequence[JsonObject]) -> tuple[bool, JsonObject]: ...
    def execute_encoded(self, raw_input: JsonObject, ctx: TaskContext) -> JsonValue: ...


class YscbModule(ABC):
    @property
    @abstractmethod
    def module_id(self) -> ModuleId: ...
    @abstractmethod
    def tasks(self) -> Sequence[BoundTask]: ...
    def on_init(self, workspace_root: HostPath) -> Optional[Callable[[], None]]: ...
    def on_start(self, workspace_root: HostPath) -> Optional[Callable[[], None]]: ...


@dataclass(frozen=True, slots=True)
class ModuleDescriptor:
    module_id: ModuleId
    module_dir: HostPath
    entry_file: str = "module_entry.py"
    venv_group: Optional[str] = None
    venv_python: Optional[HostPath] = None
    eager_warmup: bool = False
    declared_tasks: tuple[TaskRouteSpec, ...] = ()


class ModuleProviderPort(Protocol):
    def list_modules(self) -> Sequence[ModuleDescriptor]: ...
    def get_module(self, module_id: ModuleId) -> Optional[ModuleDescriptor]: ...
    def reload(self) -> None: ...


class ConfigViewPort(Protocol):
    def get_module_value(self, module_id: ModuleId, key: str, default: JsonValue = None) -> JsonValue: ...
    def fingerprint(self) -> str: ...
    def reload(self) -> None: ...


class VfsEchoGuardPort(Protocol):
    def is_suppressed(self, path: HostPath, mtime_ns: int, size: int, ino: int) -> bool: ...


class DaemonSpawner(Protocol):
    def can_spawn_in_environment(self) -> bool: ...
    def try_spawn_background(self, workspace_root: HostPath) -> bool: ...


@dataclass(frozen=True, slots=True)
class WorkerProcessSnapshot:
    group: str
    pid: int
    alive: bool


def decode_outcome_as(
    outcome: TaskOutcome[JsonValue], output_type: type[TOut], *, source_task: Optional[str] = None,
) -> TaskOutcome[TOut]: ...
```

## 3. 對上層暴露之 `RuntimeDispatcher` 管理介面 (`dispatcher.py` / `gates.py`)

```python
from contextlib import contextmanager
from dataclasses import dataclass
import threading
from typing import Callable, Iterator, Optional, Protocol, Sequence, overload
from core.execution.event import EventBatchEnvelope, EventOrdering
from core.execution.lifecycle import (
    StepExecutionResult, TaskStepExecutor, TurnExecutionReport, TurnScope, WorkerContainerLifecycle,
)
from core.execution.rpc import DaemonConnectionConfig, PersistentRpcSession
from core.foundation.profiler import FlightLogRouter, ProfilerRingBuffer


@dataclass(frozen=True, slots=True)
class DaemonRpcInvokeReply:
    ok: bool
    raw_value: JsonValue = None
    error: Optional[ErrorDetail] = None
    event_diagnostics: tuple[ErrorDetail, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    invoked_tasks: tuple[tuple[HostPath, TaskId], ...] = ()
    coalesced: bool = False
    profiler_tree: Optional[JsonValue] = None


@dataclass(frozen=True, slots=True)
class QuiesceResumeResult:
    started: bool
    need_handoff: bool


class CoordinatorPort(Protocol):
    def coalesce_participant_count(self, resource_key: str) -> int: ...


class Tier1WorkerPool(Protocol):
    def active_worker_snapshots(self) -> tuple[WorkerProcessSnapshot, ...]: ...
    def warmup_group(self, group_descriptors: Sequence[ModuleDescriptor], only_modules: Optional[frozenset[ModuleId]] = None) -> None: ...
    def stop_groups_for_modules(
        self, modules: frozenset[ModuleId], all_descriptors: Sequence[ModuleDescriptor],
        *, grace_ms: int = 1000, drain_in_flight: bool = False,
    ) -> tuple[ErrorDetail, ...]: ...


class LifecycleReloadGate:
    def __init__(self, workspace_root: HostPath) -> None: ...
    @property
    def quiesce_epoch(self) -> int: ...
    @property
    def transition_seq(self) -> int: ...
    def lifecycle_scope(self) -> threading.RLock: ...
    @contextmanager
    def try_lifecycle_scope(self, timeout_sec: Optional[float] = None) -> Iterator[bool]: ...
    def has_any_active_work(self) -> bool: ...
    def has_any_quiesced(self) -> bool: ...
    def register_gate_listener(self, listener: Callable[[], None]) -> None: ...
    def is_globally_quiesced(self) -> bool: ...
    def is_globally_gated(self) -> bool: ...
    def is_call_gated_for_quiesce(self, target_mod: Optional[ModuleId]) -> bool: ...
    def is_module_slot_quiesced(self, target_mod: Optional[ModuleId]) -> bool: ...
    def is_rpc_call_gated(self, target_mod: Optional[ModuleId], prop: Optional[CallPropagationContext] = None) -> bool: ...
    def has_admitted_rpc_turn(self, call_id: str) -> bool: ...
    def enter_rpc_call(self, mod_id: ModuleId, call_id: str, prop: Optional[CallPropagationContext] = None) -> bool: ...
    def exit_rpc_call(self, mod_id: ModuleId, call_id: str) -> None: ...
    def enter_host_step(self, mod_id: ModuleId, turn_id: str, call_tree_id: str = "") -> None: ...
    def exit_host_step(self, mod_id: ModuleId, turn_id: str, call_tree_id: str = "") -> None: ...
    @contextmanager
    def host_step_scope(self, mod_id: ModuleId, turn_id: str, call_tree_id: str = "") -> Iterator[None]: ...
    @contextmanager
    def register_draining_exempt_turn(self, turn_id: str) -> Iterator[None]: ...
    def try_begin_global_quiesce(
        self, drain_deadline: Optional[float] = None, *, leased: bool = False, pre_accepted_ids: frozenset[str] = frozenset(),
    ) -> bool: ...
    def record_quiesce_lease(self, lease_sec: float) -> None: ...
    def next_quiesce_wakeup(self) -> Optional[float]: ...
    def due_quiesce_epoch(self) -> Optional[int]: ...
    def postpone_due_lease(self, epoch: int, delay_sec: float) -> None: ...
    def schedule_deferred_resume(self, expected_epoch: Optional[int]) -> None: ...
    def run_global_resume_guarded(self, expected_epoch: Optional[int], body_fn: Callable[[], bool]) -> QuiesceResumeResult: ...
    @contextmanager
    def resume_reload_scope(self) -> Iterator[None]: ...
    @contextmanager
    def module_reload_scope(self, reload_all: bool, initial_gated: frozenset[ModuleId]) -> Iterator[None]: ...
    def bump_reload_epochs(self, mods: frozenset[ModuleId]) -> None: ...
    def any_descriptor_reloading(self, descriptors: Sequence[ModuleDescriptor]) -> bool: ...
    def has_leased_pre_quiesce(self, turn_id: str, call_tree_id: str) -> bool: ...
    def is_quiesced_blocked(self, request: InvokeRequest, target_mod: ModuleId, is_daemon_host: bool) -> bool: ...
    def current_epoch(self, mod_id: ModuleId) -> int: ...
    def has_turn_or_tree_exempt(self, turn_id: str, call_tree_id: str) -> bool: ...
    def is_request_reload_exempt(self, request: InvokeRequest, is_reentrant_retiring: Callable[[InvokeRequest], bool]) -> bool: ...
    def is_step_blocked_by_reload(self, parent_req: InvokeRequest, is_reentrant_retiring: Callable[[InvokeRequest], bool]) -> bool: ...
    def wait_for_unquiesced(
        self, request: InvokeRequest, token: CancellationToken, is_reentrant_retiring: Callable[[InvokeRequest], bool],
        *, timeout_ms: Optional[int] = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class DispatcherHostOptions:
    config_view: Optional[ConfigViewPort] = None
    daemon_spawner: Optional[DaemonSpawner] = None
    connection_config: DaemonConnectionConfig = DaemonConnectionConfig()
    is_daemon_host: bool = False
    persistent_rpc_session: Optional[PersistentRpcSession] = None
    child_dispatcher_factory: Optional[Callable[[HostPath], RuntimeDispatcher]] = None
    peer_cache_dir_resolver: Optional[Callable[[HostPath], HostPath]] = None
    owns_child_dispatchers: bool = True
    in_memory_modules: tuple[YscbModule, ...] = ()
    module_services_factory: Optional[Callable[[ModuleId], ModuleRuntimeServices]] = None
    worker_host_dir: Optional[HostPath] = None
    env_lease_acquire: Optional[EnvLeaseAcquireFn] = None
    env_touch_used: Optional[EnvTouchUsedFn] = None
    flight_log_router: Optional[FlightLogRouter] = None
    daemon_boot_id: str = ""
    profiler_ring_buffer: Optional[ProfilerRingBuffer] = None


class RuntimeDispatcher(TaskStepExecutor[InvokeRequest]):
    def __init__(
        self, *, workspace_root: HostPath, cache_dir: HostPath, module_provider: ModuleProviderPort,
        options: DispatcherHostOptions = DispatcherHostOptions(),
    ) -> None: ...
    @property
    def is_daemon_host(self) -> bool: ...
    @property
    def cache_dir(self) -> HostPath: ...
    @property
    def container_lifecycle(self) -> WorkerContainerLifecycle: ...
    @property
    def tier1_pool(self) -> Tier1WorkerPool: ...
    @property
    def reload_gate(self) -> LifecycleReloadGate: ...
    @property
    def coordinator(self) -> CoordinatorPort: ...
    @property
    def module_provider(self) -> ModuleProviderPort: ...
    @property
    def active_turn_count(self) -> int: ...
    @property
    def flight_log_router(self) -> Optional[FlightLogRouter]: ...
    @property
    def profiler_ring_buffer(self) -> Optional[ProfilerRingBuffer]: ...
    def bind_daemon_observability(
        self, *, daemon_boot_id: str = "", flight_log_router: Optional[FlightLogRouter] = None,
        profiler_ring_buffer: Optional[ProfilerRingBuffer] = None,
    ) -> None: ...
    def drain_teardown_diagnostics(self) -> tuple[ErrorDetail, ...]: ...
    def list_route_specs(self) -> tuple[TaskRouteSpec, ...]: ...
    def subscribed_modules(self, event_id: EventId) -> frozenset[ModuleId]: ...
    def warmup_daemon_container(self, only_modules: Optional[frozenset[ModuleId]] = None) -> None: ...
    @overload
    def invoke(
        self, request: InvokeRequest, *, output_type: type[TOut], cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[TOut]: ...
    @overload
    def invoke(
        self, request: InvokeRequest, *, output_type: None = None, cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[JsonValue]: ...
    def invoke(
        self, request: InvokeRequest, *, output_type: Optional[type[TOut]] = None,
        cancel_token: Optional[CancellationToken] = None, on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]: ...
    def invoke_daemon_rpc(
        self, payload: JsonObject, cancel_token: CancellationToken, on_progress: Callable[[JsonObject], None],
        *, pre_turn_id: str = "",
    ) -> DaemonRpcInvokeReply: ...
    def invoke_typed(
        self, task_meta: TaskMetadata[TIn, TOut], req: TIn, *, caller_cwd: Optional[HostPath] = None,
        routing_policy: ClientRoutingPolicy = ClientRoutingPolicy.AUTO_SPAWN,
        approval_scope: frozenset[TaskId] = frozenset(), cancel_token: Optional[CancellationToken] = None,
    ) -> TaskOutcome[TOut]: ...
    def try_quiesce_global(self, *, drain_deadline: Optional[float] = None, leased: bool = False) -> bool: ...
    def quiesce_global(self, grace_ms: int = 3000) -> None: ...
    def execute_daemon_quiesce_resume(
        self, *, expected_epoch: Optional[int], check_core_mutated: Callable[[], bool],
        on_before_warmup: Callable[[], None],
    ) -> QuiesceResumeResult: ...
    def resume_from_quiesce(self, *, on_before_warmup: Optional[Callable[[], None]] = None) -> None: ...
    def reload_config_and_contributes(self, *, changed_paths: Sequence[str] = (), emit_event: bool = True) -> bool: ...
    def reload_affected_modules(self, modules: frozenset[ModuleId], grace_ms: int = 2000) -> None: ...
    def emit_background_event(
        self, event_id: EventId, raw_payload: JsonObject, *, ordering: EventOrdering = EventOrdering.UNORDERED,
    ) -> TurnExecutionReport: ...
    def cancel_all_active_turns(self, reason: str = "Forced shutdown") -> None: ...
    def shutdown(self, grace_ms: int = 3000) -> tuple[ErrorDetail, ...]: ...
    def run_primary_step(self, request: InvokeRequest, turn: TurnScope) -> StepExecutionResult[JsonValue]: ...
    def run_event_step(self, batch: EventBatchEnvelope, turn: TurnScope) -> Sequence[StepExecutionResult[JsonValue]]: ...
    def finalize_turn_events(self, turn: TurnScope, *, abort_only: bool = False) -> Optional[ErrorDetail]: ...
```

## 3.1 協調引擎與隔離模組槽契約 (`coordinator.py` / `module_slot.py` / `wire.py`)

```python
from dataclasses import dataclass, field
import threading
from typing import Callable, Generic, Mapping, MutableMapping, Optional, Sequence, TypeVar
from core.execution.event import CausalLineage, RawEventRecord
from core.execution.lifecycle import LifoResourceStack, WorkerContainerLifecycle

TVal = TypeVar("TVal")
TResult = TypeVar("TResult")


@dataclass(frozen=True, slots=True)
class CoordinatedExecution(Generic[TResult]):
    is_follower: bool
    caller_slot_id: int
    outcome: Optional[TResult]


@dataclass(frozen=True, slots=True)
class FlightCallerRegistration:
    caller_turn_id: str
    call_tree_id: str
    caller_stack: tuple[tuple[HostPath, TaskId], ...]
    step_cancel: CancellationToken
    turn_cancel: CancellationToken
    in_event_chain: bool = False
    deadline: Optional[float] = None


@dataclass(frozen=True, slots=True)
class HolderIdentity:
    turn_id: str
    tree_id: str
    stack: tuple[tuple[HostPath, TaskId], ...] = ()


@dataclass(slots=True)
class LoadedModuleArtifact:
    instance: YscbModule
    package_key: str
    in_flight: int = 0


class LocalModuleSlotRegistry:
    def __init__(
        self, workspace_root: HostPath, lifo_stack: LifoResourceStack, *,
        container: Optional[WorkerContainerLifecycle] = None, is_module_quiesced: Optional[Callable[[ModuleId], bool]] = None,
        require_eager_start: bool = False, on_module_initialized: Optional[Callable[[ModuleId], None]] = None,
        in_memory_modules: Mapping[ModuleId, YscbModule] = ...,
        module_services_factory: Optional[Callable[[ModuleId], ModuleRuntimeServices]] = None,
    ) -> None: ...
    @property
    def workspace_root(self) -> HostPath: ...
    def drain_pending_teardown_diagnostics(self) -> tuple[ErrorDetail, ...]: ...
    def register_descriptors(self, descriptors: Sequence[ModuleDescriptor]) -> None: ...
    def ensure_module_artifact_loaded(self, module_id: ModuleId, *, record_runtime_degraded: bool = True) -> YscbModule: ...
    def introspect_bound_route_specs(self, module_id: ModuleId) -> tuple[TaskRouteSpec, ...]: ...
    def ensure_module_loaded_and_initialized(self, module_id: ModuleId) -> YscbModule: ...
    def warmup_modules(self, only_modules: Optional[frozenset[ModuleId]] = None) -> Mapping[ModuleId, Callable[[], None]]: ...
    def lookup_task(self, task_id: TaskId, *, require_initialized: bool = True) -> BoundTask: ...
    def compute_equiv_locally(self, task_id: TaskId, raw_input: JsonObject) -> WorkerEquivReply: ...
    def map_batch_locally(self, task_id: TaskId, event_id: EventId, event_payloads: Sequence[JsonObject]) -> WorkerMapBatchReply: ...
    def unload_all_modules(self, *, grace_sec: float = 0.2) -> tuple[ErrorDetail, ...]: ...
    def unload_modules(
        self, modules: frozenset[ModuleId], *, drain_in_flight: bool = False, grace_sec: float = 2.0, force_retire: bool = False,
    ) -> tuple[ErrorDetail, ...]: ...
    def execute_step_locally(self, spec: LocalStepExecutionSpec) -> WorkerStepReply: ...


@dataclass(frozen=True, slots=True)
class LocalStepExecutionSpec:
    task_id: TaskId
    raw_input: JsonObject
    caller_cwd: HostPath
    caller_env: Mapping[str, str]
    base_lineage: CausalLineage
    cancel_token: CancellationToken
    priority_getter: Callable[[], ExecutionPriority]
    callbacks: StepContextCallbacks
    interactive_tty: bool = False


class PriorityHandle:
    def __init__(self, initial: ExecutionPriority) -> None: ...
    @property
    def current(self) -> ExecutionPriority: ...
    def __call__(self) -> ExecutionPriority: ...
    def elevate_to_foreground(self) -> bool: ...
    def register_listener(self, cb: Callable[[ExecutionPriority], None]) -> Callable[[], None]: ...


class ProtectedModuleLoader:
    def __init__(self, workspace_root: HostPath) -> None: ...
    @classmethod
    def cleanup_package(cls, pkg_or_entry: str) -> None: ...
    def load_module_artifact(self, descriptor: ModuleDescriptor) -> LoadedModuleArtifact: ...


@dataclass(frozen=True, slots=True)
class ResourceAcquireSpec:
    resource_key: Optional[str]
    mode: ConcurrencyMode
    equiv_key: str
    priority: ExecutionPriority
    turn_id: str
    call_stack: tuple[tuple[HostPath, TaskId], ...]
    cancel_token: CancellationToken
    turn_cancel_token: Optional[CancellationToken] = None
    timeout_ms: Optional[int] = None
    external_priority_handle: Optional[PriorityHandle] = None
    allow_step_coalesce: bool = True
    call_tree_id: str = ""
    in_event_chain: bool = False
    on_progress: Optional[Callable[[JsonObject], None]] = None


class ResourceCoordinator:
    def __init__(
        self, *, cache_dir: Optional[HostPath] = None, workspace_root: Optional[HostPath] = None,
        resolve_cache_dir: Optional[Callable[[HostPath], Optional[HostPath]]] = None, is_daemon_host: bool = False,
    ) -> None: ...
    @property
    def is_daemon_host(self) -> bool: ...
    def coalesce_participant_count(self, resource_key: str) -> int: ...
    def execute(
        self, spec: ResourceAcquireSpec,
        leader_fn: Callable[[PriorityHandle, CancellationToken, Optional[StepFlight[TResult]]], TResult],
        *, extract_release_guard: Optional[Callable[[TResult], Optional[threading.Event]]] = None,
    ) -> CoordinatedExecution[TResult]: ...


class SharedCancelGroup:
    def __init__(self) -> None: ...
    def add_participants(self, caller_tokens: Sequence[CancellationToken]) -> tuple[Optional[Callable[[], None]], ...]: ...
    def try_add_participant(self, caller_token: CancellationToken) -> Optional[Callable[[], None]]: ...
    @property
    def active_count(self) -> int: ...
    def close_all(self) -> None: ...


@dataclass(frozen=True, slots=True)
class StepContextCallbacks:
    on_emit_imm: Callable[[EventId, JsonObject, CausalLineage, bool], None]
    on_invoke_task: Callable[[TaskId, JsonObject, Optional[HostPath], Optional[ClientRoutingPolicy]], TaskOutcome[JsonValue]]
    on_progress: Callable[[JsonObject], None]


class StepFlight(Generic[TVal]):
    def __init__(self, priority_handle: PriorityHandle) -> None: ...
    def slot_wake_event(self, slot_id: int) -> threading.Event: ...
    def seal(self) -> None: ...
    def active_caller_count(self) -> int: ...
    def effective_deadline(self) -> Optional[float]: ...
    def effective_post_step_deadline(self) -> Optional[float]: ...
    def add_caller(self, reg: FlightCallerRegistration, on_progress: Optional[Callable[[JsonObject], None]]) -> tuple[int, Optional[Callable[[], None]]]: ...
    def detach_post_step(self, slot_id: int) -> None: ...
    def broadcast_progress(self, payload: JsonObject) -> None: ...
    def complete(self, *, outcome: Optional[TVal] = None, raised_exc: Optional[BaseException] = None) -> None: ...
    def run_or_await_post_step(
        self, slot_id: int, turn_cancel: CancellationToken, timeout_sec: Optional[float],
        drain_fn: Callable[[CancellationToken, Callable[[], Optional[float]]], object],
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class WorkerBootstrapConfig:
    host: str
    port: int
    boot_id: str
    workspace_root: HostPath
    modules: tuple[ModuleDescriptor, ...]
    is_hot_container: bool = True
    host_dir: Optional[HostPath] = None
    daemon_boot_id: str = ""
    flight_log_config: Optional[JsonObject] = None


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
    ok: bool
    raw_output: JsonValue = None
    committed_events: tuple[RawEventRecord, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    preempted: bool = False
    fatal_abort_turn: bool = False
    error: Optional[ErrorDetail] = None
    profiler_tree: Optional[JsonValue] = None


def worker_main(argv: Optional[Sequence[str]] = None, env: Optional[MutableMapping[str, str]] = None) -> int: ...
```
