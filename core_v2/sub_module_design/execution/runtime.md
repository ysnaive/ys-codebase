# 子模組架構設計規格：`core.execution.runtime`（全系統唯一 Task 派發、對稱單飛合併與隔離執行協調中樞）

> **所屬功能域**：`Domain 5 — 執行與常駐調度域 (execution/)`
> **模組路徑**：`core_v2/source/core/core/execution/runtime/`
> **內部模組職責切分**：`contracts.py`、`coordinator.py`、`lineage_join.py`、`gates.py`、`module_slot.py`、`route_index.py`、`turn_session.py`、`step_host.py`、`worker_entry.py`、`worker_pool.py`、`wire.py`、`dispatcher.py`
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.fs`、`execution.{rpc, lifecycle, event}`
> **禁止反向依賴（Forbidden Imports）**：`execution.daemon`、`surface/*`
> **狀態**：`Active Living Spec — Clean-Sheet Simplified & Orthogonal Benchmark Aligned`

## 1. 核心公理與單點封閉使命 (Core Axiom & Single-Point Mission)

`core.execution.runtime` 的最高準則為：**將全系統所有功能派發、冷熱路由、環境隔離執行與資源並發協調問題 100% 封閉鎖死在本模組單點維護，且以根因正交模型取代過渡補丁**。

### 1.1 萬物皆 `Task`、顯式傳播組合與零逆向依賴邊界
1. **唯一公開執行單元**：全生態系所有可被 CLI、SDK、跨模組調用、事件、定時排程或升級遷移觸發的能力，**100% 實作為 `Task[TIn, TOut]` 並附帶強型別 `TaskMetadata`**。即便兩個模組共置於同一 `venv_group` 子進程，跨模組呼叫 `ctx.invoke_task()` / `ctx.invoke_typed()` **仍必須經由主控端 `RuntimeDispatcher` 協調（嚴禁私下直呼繞過鎖、權限與事件收集）**。
2. **顯式傳播上下文組合（`CallPropagationContext`）**：將跨單步/跨進程傳遞之呼叫棧、對稱單飛存活呼叫端視圖（`CoalesceCallerView`）、因果鏈、工作區共享視圖與觸發標記收斂為單一不可變值物件 `CallPropagationContext`，由 `InvokeRequest.propagation`、`DaemonRpcInvokeEnvelope.propagation` 與 `WorkerCallbackContext.propagation` 統一組合持有，且公開套件表面（`core.execution.runtime.__all__`）明確匯出業務契約與宿主協調門面（`RuntimeDispatcher`、`DispatcherHostOptions`，以及由 `RuntimeDispatcher` 內部建構持有、對外透過唯讀屬性提供管理門面之 `LifecycleReloadGate`、`CoordinatorPort`、`Tier1WorkerPool`，連同 `DueQuiesceResume`、`QuiesceResumeResult`、`ResumeConsumePlan`、`DaemonRpcInvokeReply`、`EmittedEventHop`、`WorkerProcessSnapshot`；內部子進程回呼橋接完全私有封裝）。
3. **中性對稱單飛合併與原子共享事件排空（`StepFlight` + `FlightCascade`）**：
   - **對稱中性單步單飛（`StepFlight`）**：同一 `(resource_key, task_id, equivalence_key)` 的所有並發參與者地位完全對稱；入站前預檢跨進程與多跳單飛重入（若僅部分合併呼叫端觸發非法重入則精確逐槽剔除違規呼叫端而不連坐無辜參與者），單步本體以**完全獨立之中性 `TurnScope`、中性 `call_stack = ((ws, task_id),)`、空白 `CausalLineage()` 與動態存活截止預算 `effective_deadline()`** 執行唯一 1 次，並以 `.pin` 共享/獨佔 OS 檔案鎖釘住跨進程重入子鎖與延遲收尾生命週期；任一參與者取消僅分離自身槽位，唯有**全體參與者皆已取消**時才取消底層單步；任一前景參與者加入立即透過 `PriorityHandle` 加速底層單步。
   - **原子封口（`StepFlight.seal_and_finalize`）與共享 `FlightCascade`**：單步完成時先於 `_lock` 內封口停止收客並快照存活槽位，隨即於鎖外展開嵌套呼叫端視圖並掛載 `FlightCascade`（傳遞完整嵌套 `ChildCascadeJoin` `EmittedEventHop` 因果鏈與存活呼叫端視圖 `snapshot_live_caller_views`），最後於 `_lock` 內原子綁定 `abort_hook` 並重播封口視窗期間之中止槽位，消除跨鎖順序反轉；若全體參與者皆已取消則不建立孤兒 `FlightCascade`；若單一存活參與者且無子級合流則走內聯因果重算快徑；多人或嵌套合流則透過對稱 `FlightCascade` 單次排空並依各呼叫端自身因果鏈精確歸責環路來源。
4. **純淨 `sys.meta_path` 隔離套件與子模組載入（`module_slot.py`）**：透過 `_ScopedModuleFinder` 與直接呼叫幀（Direct-Frame）限定之 `importlib.import_module` 轉發，將每個模組掛載為獨立合成套件 `_yscb_v2_mod_<id>_<hex>` 及其入口子模組 `.__entry__`，完整支援相對匯入、不遮蔽 Python 標準庫之絕對兄弟匯入、`importlib.import_module()` 動態匯入與 PEP 420 命名空間子目錄，零全域 `sys.path` / `sys.modules` 頂層污染。
5. **與 `execution.daemon` 零逆向耦合**：`runtime` 透過 `execution.rpc` 唯讀探測線上 Daemon，並透過外層注入的 `DaemonSpawner(Protocol)` 按需背景拉起 Daemon，**`runtime` 內部 0 行匯入 `execution.daemon`**。
6. **消費端擁有之 `ModuleProviderPort` 契約與 `surface` 組裝轉接縫（Dependency Inversion Seam）**：`ModuleProviderPort` 及 `ModuleDescriptor` / `TaskRouteSpec` 由消費端 `execution.runtime` 定義並擁有；下游 `Domain 3 (metadata)` 與 `Domain 4 (packaging)` 維持 100% 執行引擎無涉（零匯入 `execution`），由頂層組裝根 `Domain 6 (surface)` 實作超薄轉接器將 `(metadata + packaging)` 靜態產物映射為 `ModuleDescriptor` 注入 `RuntimeDispatcher`。
7. **跨進程 `SERIALIZE` 合法後代 `.pin` 免排隊直通與全回合逾時語意**：當外部進程已持有 `resource_key` 之 `SERIALIZE` 檔案鎖並透過 RPC 巢狀回呼常駐 Daemon 時，合法後代透過 `.pin` 共享鎖驗證擁有者身分後直接重入執行，絕不排在正等待該外部鎖之無關競爭者後方造成循環等待；`TaskMetadata.timeout_ms` 定義為涵蓋主任務單步與同一 Turn 延遲事件訂閱鏈排空之整體時間預算；`approval_scope` 與 `allow_conditional` 則作為同使用者信任域內防止破壞性任務遭未確認或背景/事件鏈誤觸發之顯式安全護欄。

## 2. 核心契約規格 (`contracts.py` & `wire.py` 公開快照)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Generic, Mapping, Optional, Protocol, Sequence, TypeVar, overload
from core.execution.event import BoundEventSubscription, CausalLineage, EventMetadata, ScopedHop
from core.foundation.errors import ErrorDetail
from core.foundation.observability import CancellationToken, ProgressEvent
from core.foundation.primitives import EventId, HostPath, JsonObject, JsonPrimitive, JsonValue, ModuleId, TaskId

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")
TOut_co = TypeVar("TOut_co", covariant=True)
TPayload = TypeVar("TPayload")


WORKER_AUTH_ENV_KEY: str = "YSCB_WORKER_AUTH_TOKEN"
LOCKS_SUBDIR: str = "locks"
INSTALLER_LOCK_FILENAME: str = "installer.lock"
MODULES_DIRNAME: str = ".modules"
DEFAULT_CACHE_DIRNAME: str = ".cache"
CORE_MODULE_ID: ModuleId = ModuleId("core")
WATCHER_TASK_ID: TaskId = TaskId("core.watcher")
CONFIG_CHANGED_EVENT_ID: EventId = EventId("core.config_changed")


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
class CoalesceCallerView:
    turn_id: str
    call_tree_id: str
    call_stack: tuple[tuple[HostPath, TaskId], ...] = ()
    caller_hops: tuple[ScopedHop, ...] = ()
    flight_ids: tuple[str, ...] = ()
    in_event_chain: bool = False


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
    coalesce_callers: tuple[CoalesceCallerView, ...] = ()
    coalesce_flights: tuple[str, ...] = ()


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


@dataclass(frozen=True, slots=True)
class TaskOutcome(Generic[TOut_co]):
    ok: bool
    value: Optional[TOut_co] = None
    error: Optional[ErrorDetail] = None
    event_diagnostics: tuple[ErrorDetail, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    coalesced: bool = False
    executed_hot: bool = False


class TaskContext(ABC):
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
    ) -> TaskOutcome[TOut]: ...
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
    def map_subscription_batch(
        self,
        event_id: EventId,
        raw_payloads: Sequence[JsonObject],
    ) -> tuple[bool, JsonObject]: ...
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
    def map_subscription_batch(
        self,
        event_id: EventId,
        raw_payloads: Sequence[JsonObject],
    ) -> tuple[bool, JsonObject]: ...
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
    outcome: TaskOutcome[JsonValue],
    output_type: type[TOut],
    *,
    source_task: Optional[str] = None,
) -> TaskOutcome[TOut]: ...
```

## 3. 全統一派發與執行協調流水線 (Unified Dispatch Pipeline)

```text
InvokeRequest (攜帶 caller_cwd、caller_env、approval_scope 與顯式組合之 CallPropagationContext)
   │
   ▼
[Stage 1: Metadata Lookup, Security/Mutation Invariant Gate & CallStack Check (gates.py)]
   │ 1. 驗證靜默/降級狀態（LifecycleReloadGate / WorkerContainerLifecycle）、TaskId、Exposure、--cold 相容性
   │ 2. 核驗 SecurityTier.GATED / CONDITIONAL（事件鏈與跨工作區自動收緊授權）
   │ 3. 驗證物理互斥：interactive_tty 僅限頂層前景冷呼叫（不可為 SDK_ONLY）；mutation_scope != NONE 僅允許前景冷 Turn（零 hot_workspaces、非事件鏈），嚴禁任何觸及常駐熱容器呼叫樹之同步呼叫
   │ 4. 事件觸發先於 Tier 0 主控端執行 filter_for_subscription（未命中直接短路，絕不進 Stage 3 誤觸 PREEMPT 或污染因果鏈）
   │ 5. 以 (workspace_root, task_id) 與對稱單飛 coalesce_callers 檢查任務呼叫環路（跨子工作區同 task_id 合法放行）
   ▼
[Stage 2: Master Location & Cold/Hot Turn Routing (dispatcher.py)]
   ├── 外部呼叫 HYBRID / DAEMON_ONLY（routing_policy != FORCE_COLD）：
   │      ├── PersistentRpcSession / call_ephemeral_daemon_rpc 連入線上 Daemon：
   │      │     • was_accepted=True  -> 正常回傳結果；若 transport_lost=True 回報 TRANSPORT_LOST（嚴禁自動重跑！）
   │      │     • was_accepted=False -> 配合 wait_for_handoff_daemon_endpoint 透明等待交棒或安全轉入本地 ColdTurn
   │      └── Daemon 離線 -> STRICT_HOT/DAEMON_ONLY 報錯；HYBRID 本地跑 ColdTurn（AUTO_SPAWN 單飛拉起 Daemon）
   └── FORCE_COLD / COLD_ONLY：壓制 auto_spawn，於 ColdInstallerLockManager 保護下直連 TurnEngine 執行
   │
   ▼
[Stage 3: Symmetric Resource Coordinator & FlightCascade (coordinator.py + lineage_join.py)]
   │ • 同棧與跨多跳單飛祖先重入判定：僅有效 SERIALIZE 允許同棧或 COALESCE 參與者祖先重入繼承持鎖；部分參與者非法重入僅逐槽剔除違規者！
   │ • COALESCE 中性對稱單飛：獨立 flight TurnScope 隔離執行，StepFlight.seal_and_finalize 原子掛載 FlightCascade 或單人內聯重算快徑
   │ • 物理層統一持有 .cache/locks/res_<prefix>_<sha256>.lock/.owner.json/.pin/.turn.lock/.turn.json 屏障，確保同進程與跨進程冷熱混合多執行緒 SERIALIZE 重入 100% 嚴格互斥且巢狀子呼叫免死鎖讓位
   ▼
[Stage 4 & 5: Isolated Step Execution Host (module_slot.py / worker_pool.py / worker_entry.py)]
   ├── Tier 0 模組：LocalModuleSlotRegistry + _ScopedModuleFinder 合成套件隔離直跑單步 + guard_standard_streams 守護
   └── Tier 1 模組：Daemon 模式經 Tier1WorkerPool 常駐複用（逐模組 LIFO 卸載診斷對齊、中毒行程實際退出後才釋鎖）；
                    冷啟動模式經 OneShotVenvHost 執行單步並支援完整雙向回呼重入與逐模組 LIFO 釋放診斷收集
   ▼
TaskOutcome[TOut]
```

## 4. 對上層暴露之 `RuntimeDispatcher` 管理介面 (`dispatcher.py`)

```python
from contextlib import contextmanager
from dataclasses import dataclass
import threading
from typing import Callable, Iterator, Optional, Protocol, Sequence, overload
from core.execution.event import EventBatchEnvelope, EventOrdering
from core.execution.lifecycle import (
    StepExecutionResult,
    TaskStepExecutor,
    TurnExecutionReport,
    TurnScope,
    WorkerContainerLifecycle,
)
from core.execution.rpc import DaemonConnectionConfig, PersistentRpcSession


@dataclass(frozen=True, slots=True)
class EmittedEventHop:
    workspace_scope: str
    event_id: EventId
    source_task: Optional[str] = None


@dataclass(frozen=True, slots=True)
class DaemonRpcInvokeReply:
    ok: bool
    raw_value: JsonValue = None
    error: Optional[ErrorDetail] = None
    event_diagnostics: tuple[ErrorDetail, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    invoked_tasks: tuple[tuple[HostPath, TaskId], ...] = ()
    emitted_hops: tuple[EmittedEventHop, ...] = ()
    coalesced: bool = False


@dataclass(frozen=True, slots=True)
class QuiesceResumeResult:
    started: bool
    need_handoff: bool
    still_quiesced: bool


@dataclass(frozen=True, slots=True)
class ResumeConsumePlan:
    re_warm: frozenset[ModuleId]
    touched_all: frozenset[ModuleId]
    was_all: bool


@dataclass(frozen=True, slots=True)
class DueQuiesceResume:
    epoch: int
    modules: Optional[frozenset[ModuleId]] = None
    preserve_modules: frozenset[ModuleId] = frozenset()


class CoordinatorPort(Protocol):
    def coalesce_participant_count(self, resource_key: str) -> int: ...
    def handle_remote_flight_control(self, payload: JsonObject) -> JsonObject: ...


class Tier1WorkerPool(Protocol):
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


class LifecycleReloadGate:
    def __init__(self, workspace_root: HostPath) -> None: ...
    @property
    def quiesce_epoch(self) -> int: ...
    @property
    def transition_seq(self) -> int: ...
    def lifecycle_scope(self) -> threading.RLock: ...
    @contextmanager
    def try_lifecycle_scope(self, timeout_sec: Optional[float] = None) -> Iterator[bool]: ...
    def register_gate_listener(self, listener: Callable[[], None]) -> None: ...
    def has_any_active_work(self) -> bool: ...
    def has_admitted_rpc_turn(self, call_id: str) -> bool: ...
    def has_any_quiesced(self) -> bool: ...
    def is_globally_quiesced(self) -> bool: ...
    def is_globally_gated(self) -> bool: ...
    def active_quiesced_modules(self) -> frozenset[ModuleId]: ...
    def is_module_quiesced(self, target_mod: ModuleId) -> bool: ...
    def is_call_gated_for_quiesce(self, target_mod: Optional[ModuleId]) -> bool: ...
    def is_rpc_call_gated(
        self,
        target_mod: Optional[ModuleId],
        prop: Optional[CallPropagationContext] = None,
    ) -> bool: ...
    def enter_rpc_call(
        self,
        mod_id: ModuleId,
        call_id: str,
        prop: Optional[CallPropagationContext] = None,
    ) -> bool: ...
    def exit_rpc_call(self, mod_id: ModuleId, call_id: str) -> None: ...
    def record_quiesce_lease(
        self,
        eff_global: bool,
        expanded_mods: frozenset[ModuleId],
        lease_sec: float,
    ) -> int: ...
    def due_quiesce_resume(self, now: float) -> Optional[DueQuiesceResume]: ...
    def next_quiesce_wakeup(self, now: float) -> Optional[float]: ...
    def postpone_due_lease(
        self,
        epoch: int,
        due_mods: Optional[frozenset[ModuleId]],
        retry_after_sec: float,
    ) -> None: ...
    def schedule_deferred_resume(
        self,
        expected_epoch: Optional[int],
        eff_mods: Optional[frozenset[ModuleId]],
    ) -> None: ...
    def run_quiesce_resume_guarded(
        self,
        expected_epoch: Optional[int],
        eff_mods: Optional[frozenset[ModuleId]],
        expanded_cands: frozenset[ModuleId],
        body_fn: Callable[[], bool],
        *,
        force_global: bool = False,
    ) -> QuiesceResumeResult: ...
    @contextmanager
    def resume_reload_scope(
        self,
        fresh_descs: Sequence[ModuleDescriptor],
        target_modules: Optional[frozenset[ModuleId]] = None,
        *,
        preserve_modules: frozenset[ModuleId] = frozenset(),
        deferred_boot: bool = False,
    ) -> Iterator[ResumeConsumePlan]: ...
    @contextmanager
    def module_reload_scope(
        self,
        reload_all: bool,
        initial_gated: frozenset[ModuleId],
    ) -> Iterator[Callable[[frozenset[ModuleId], bool], None]]: ...
    def any_descriptor_reloading(self, descriptors: Sequence[ModuleDescriptor]) -> bool: ...
    def has_leased_pre_quiesce(self, turn_id: str, call_tree_id: str) -> bool: ...
    def enter_host_step(self, mod_id: ModuleId, turn_id: str, call_tree_id: str) -> None: ...
    def exit_host_step(self, mod_id: ModuleId, turn_id: str, call_tree_id: str) -> None: ...
    @contextmanager
    def host_step_scope(self, mod_id: ModuleId, turn_id: str, call_tree_id: str) -> Iterator[None]: ...
    def sync_colocated_quiesce_siblings(
        self,
        fresh_descs: Sequence[ModuleDescriptor],
    ) -> frozenset[ModuleId]: ...
    def try_begin_quiesce(
        self,
        modules: frozenset[ModuleId],
        all_descs: Sequence[ModuleDescriptor],
        *,
        drain_deadline: Optional[float] = None,
        leased: bool = False,
        pre_accepted_ids: frozenset[str] = frozenset(),
    ) -> Optional[frozenset[ModuleId]]: ...
    def is_quiesced_blocked(self, request: InvokeRequest, target_mod: ModuleId, is_daemon_host: bool) -> bool: ...
    def current_epoch(self, mod_id: ModuleId) -> int: ...
    def has_turn_or_tree_exempt(self, turn_id: str, call_tree_id: str) -> bool: ...
    def is_request_reload_exempt(
        self,
        request: InvokeRequest,
        is_reentrant_retiring: Callable[[InvokeRequest], bool],
    ) -> bool: ...
    def is_step_blocked_by_reload(
        self,
        parent_req: InvokeRequest,
        is_reentrant_retiring: Callable[[InvokeRequest], bool],
    ) -> bool: ...
    def wait_if_module_reloading(
        self,
        request: InvokeRequest,
        token: CancellationToken,
        is_reentrant_retiring: Callable[[InvokeRequest], bool],
        *,
        timeout_ms: Optional[int] = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class DispatcherHostOptions:
    config_view: Optional[ConfigViewPort] = None
    daemon_spawner: Optional[DaemonSpawner] = None
    connection_config: DaemonConnectionConfig = DaemonConnectionConfig()
    is_daemon_host: bool = False
    persistent_rpc_session: Optional[PersistentRpcSession] = None
    child_dispatcher_factory: Optional[Callable[[HostPath], "RuntimeDispatcher"]] = None
    peer_cache_dir_resolver: Optional[Callable[[HostPath], HostPath]] = None
    owns_child_dispatchers: bool = True


class RuntimeDispatcher(TaskStepExecutor[InvokeRequest]):
    def __init__(
        self,
        *,
        workspace_root: HostPath,
        cache_dir: HostPath,
        module_provider: ModuleProviderPort,
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
    def list_route_specs(self) -> tuple[TaskRouteSpec, ...]: ...
    def subscribed_modules(self, event_id: EventId) -> frozenset[ModuleId]: ...
    def expand_quiesce_targets(self, modules: frozenset[ModuleId]) -> frozenset[ModuleId]: ...
    def warmup_daemon_container(self, only_modules: Optional[frozenset[ModuleId]] = None) -> None: ...
    @overload
    def invoke(
        self,
        request: InvokeRequest,
        *,
        output_type: type[TOut],
        cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[TOut]: ...
    @overload
    def invoke(
        self,
        request: InvokeRequest,
        *,
        output_type: None = None,
        cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[JsonValue]: ...
    def invoke(
        self,
        request: InvokeRequest,
        *,
        output_type: Optional[type[TOut]] = None,
        cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]: ...
    def invoke_daemon_rpc(
        self,
        payload: JsonObject,
        cancel_token: CancellationToken,
        on_progress: Callable[[JsonObject], None],
        *,
        pre_turn_id: str = "",
    ) -> DaemonRpcInvokeReply: ...
    def invoke_typed(
        self,
        task_meta: TaskMetadata[TIn, TOut],
        req: TIn,
        *,
        caller_cwd: Optional[HostPath] = None,
        routing_policy: ClientRoutingPolicy = ClientRoutingPolicy.AUTO_SPAWN,
        approval_scope: frozenset[TaskId] = frozenset(),
        cancel_token: Optional[CancellationToken] = None,
    ) -> TaskOutcome[TOut]: ...
    def emit_background_event(
        self,
        event_id: EventId,
        raw_payload: JsonObject,
        *,
        ordering: EventOrdering = EventOrdering.UNORDERED,
    ) -> TurnExecutionReport: ...
    def try_quiesce_modules(
        self,
        modules: frozenset[ModuleId],
        *,
        drain_deadline: Optional[float] = None,
        leased: bool = False,
    ) -> bool: ...
    def quiesce_modules(self, modules: frozenset[ModuleId], grace_ms: int = 3000) -> None: ...
    def execute_daemon_quiesce_resume(
        self,
        *,
        expected_epoch: Optional[int],
        modules: Optional[frozenset[ModuleId]],
        preserve_modules: frozenset[ModuleId] = frozenset(),
        deferred_boot: bool = False,
        check_core_mutated: Callable[[], bool],
        on_before_warmup: Callable[[frozenset[ModuleId], bool], None],
    ) -> QuiesceResumeResult: ...
    def resume_from_quiesce(
        self,
        *,
        modules: Optional[frozenset[ModuleId]] = None,
        preserve_modules: frozenset[ModuleId] = frozenset(),
        on_before_warmup: Optional[Callable[[frozenset[ModuleId], bool], None]] = None,
    ) -> tuple[frozenset[ModuleId], bool]: ...
    def reload_config_and_contributes(self, *, changed_paths: Sequence[str] = (), emit_event: bool = True) -> bool: ...
    def reload_affected_modules(self, modules: frozenset[ModuleId], grace_ms: int = 2000) -> None: ...
    def drain_teardown_diagnostics(self) -> tuple[ErrorDetail, ...]: ...
    def cancel_all_active_turns(self, reason: str = "Forced shutdown") -> None: ...
    def shutdown(self, grace_ms: int = 3000) -> tuple[ErrorDetail, ...]: ...
    def run_primary_step(self, request: InvokeRequest, turn: TurnScope) -> StepExecutionResult[JsonValue]: ...
    def run_event_step(self, batch: EventBatchEnvelope, turn: TurnScope) -> Sequence[StepExecutionResult[JsonValue]]: ...
    def finalize_turn_events(self, turn: TurnScope, *, abort_only: bool = False) -> Optional[ErrorDetail]: ...
```

## 4.1 協調引擎、級聯排空與隔離模組槽契約 (`coordinator.py` / `lineage_join.py` / `module_slot.py`)

```python
import contextlib
from dataclasses import dataclass, field
import threading
from typing import Callable, Generic, Iterator, Mapping, MutableMapping, Optional, Sequence, TypeVar
import weakref
from core.execution.event import CausalLineage, RawEventRecord, ScopedHop
from core.execution.lifecycle import LifoResourceStack, TurnExecutionReport, WorkerContainerLifecycle

TVal = TypeVar("TVal")
TResult = TypeVar("TResult")
TBundle = TypeVar("TBundle")

@dataclass(frozen=True, slots=True)
class CascadeOutcome:
    event_diagnostics: tuple[ErrorDetail, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    fatal_error: Optional[ErrorDetail] = None

@dataclass(frozen=True, slots=True)
class ChildCascadeJoin:
    rel_hops: tuple[EmittedEventHop, ...]
    cascade: FlightCascade
    slot_id: int = -1

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
    caller_hops: tuple[ScopedHop, ...]
    step_cancel: CancellationToken
    turn_cancel: CancellationToken
    enclosing_flights: tuple[StepFlight[object], ...] = ()
    inherited_views: tuple[CoalesceCallerView, ...] = ()
    coalesce_flights: tuple[str, ...] = ()
    turn_entry_stack: tuple[tuple[HostPath, TaskId], ...] = ()
    in_event_chain: bool = False
    deadline: Optional[float] = None

class FlightCascade:

    def __init__(self, *, seed_events: Sequence[RawEventRecord]=(), imm_hops: Sequence[EmittedEventHop]=(), imm_diagnostics: Sequence[ErrorDetail]=(), seed_teardown_diagnostics: Sequence[ErrorDetail]=(), initial_priority: ExecutionPriority=ExecutionPriority.BACKGROUND, graph_cond: Optional[threading.Condition]=None) -> None:
        ...

    def assert_acyclic(self, base_lineage: CausalLineage) -> None:
        ...

    def snapshot_emitted_hops(self) -> tuple[EmittedEventHop, ...]:
        ...

    def snapshot_live_caller_views(self) -> tuple[CoalesceCallerView, ...]:
        ...

    def add_cleanup(self, unreg: Callable[[], None]) -> None:
        ...

    def register_caller_slots(self, callers: Sequence[LiveFlightParticipant], priority: ExecutionPriority) -> None:
        ...

    def detach_caller_slot(self, slot_id: int) -> None:
        ...

    def bind_parent_cascade(self, parent: FlightCascade, transfer_slot_id: int=-1) -> bool:
        ...

    def record_emitted_hops(self, hops: Sequence[EmittedEventHop]) -> None:
        ...

    def record_live_diagnostic(self, detail: ErrorDetail) -> None:
        ...

    def add_child_join(self, call_rel_hops: Sequence[EmittedEventHop | ScopedHop], child: FlightCascade, transfer_slot_id: int=-1) -> None:
        ...

    def mark_own_completed(self, *, event_diagnostics: Sequence[ErrorDetail]=(), teardown_diagnostics: Sequence[ErrorDetail]=(), fatal_error: Optional[ErrorDetail]=None) -> None:
        ...

    def activate_and_await(self, slot_id: int, base_lineage: CausalLineage, caller_cancel: CancellationToken, deadline: Optional[float], drain_fn: Optional[Callable[[FlightCascade], TurnExecutionReport]]) -> CascadeOutcome:
        ...

    def collect_outcomes(self, slot_id: int, base_lineage: CausalLineage) -> CascadeOutcome:
        ...

@dataclass(frozen=True, slots=True)
class HolderIdentity:
    turn_id: str = ''
    tree_id: str = ''
    flight_id: str = ''
    stack: tuple[tuple[HostPath, TaskId], ...] = ()
    alt_owners: tuple[HolderIdentity, ...] = ()

@dataclass(frozen=True, slots=True)
class LiveFlightParticipant:
    slot_id: int
    turn_cancel: CancellationToken
    caller_hops: tuple[ScopedHop, ...] = ()
    caller_views: tuple[CoalesceCallerView, ...] = ()

@dataclass(slots=True)
class LoadedModuleArtifact:
    instance: YscbModule
    package_key: str
    in_flight: int = 0

class LocalModuleSlotRegistry:

    def __init__(self, workspace_root: HostPath, lifo_stack: LifoResourceStack, *, container: Optional[WorkerContainerLifecycle]=None, is_module_quiesced: Optional[Callable[[ModuleId], bool]]=None, require_eager_start: bool=False, on_module_initialized: Optional[Callable[[ModuleId], None]]=None) -> None:
        ...

    @property
    def workspace_root(self) -> HostPath:
        ...

    def drain_pending_teardown_diagnostics(self) -> tuple[ErrorDetail, ...]:
        ...

    def register_descriptors(self, descriptors: Sequence[ModuleDescriptor]) -> None:
        ...

    def ensure_module_artifact_loaded(self, module_id: ModuleId, *, record_runtime_degraded: bool=True) -> YscbModule:
        ...

    def introspect_bound_route_specs(self, module_id: ModuleId) -> tuple[TaskRouteSpec, ...]:
        ...

    def ensure_module_loaded_and_initialized(self, module_id: ModuleId) -> YscbModule:
        ...

    def warmup_modules(self, only_modules: Optional[frozenset[ModuleId]]=None) -> Mapping[ModuleId, Callable[[], None]]:
        ...

    def lookup_task(self, task_id: TaskId, *, require_initialized: bool=True) -> BoundTask:
        ...

    def compute_equiv_locally(self, task_id: TaskId, raw_input: JsonObject) -> WorkerEquivReply:
        ...

    def map_batch_locally(self, task_id: TaskId, event_id: EventId, event_payloads: Sequence[JsonObject]) -> WorkerMapBatchReply:
        ...

    def unload_all_modules(self, *, grace_sec: float=0.2) -> tuple[ErrorDetail, ...]:
        ...

    def unload_modules(self, modules: frozenset[ModuleId], *, drain_in_flight: bool=False, grace_sec: float=2.0, force_retire: bool=False) -> tuple[ErrorDetail, ...]:
        ...

    def execute_step_locally(self, spec: LocalStepExecutionSpec) -> WorkerStepReply:
        ...

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

    def __init__(self, initial: ExecutionPriority) -> None:
        ...

    @property
    def current(self) -> ExecutionPriority:
        ...

    def __call__(self) -> ExecutionPriority:
        ...

    def elevate_to_foreground(self) -> None:
        ...

    def register_listener(self, cb: Callable[[ExecutionPriority], None]) -> Callable[[], None]:
        ...

class ProtectedModuleLoader:

    def __init__(self, workspace_root: HostPath) -> None:
        ...

    @classmethod
    def cleanup_package(cls, pkg_or_entry: str) -> None:
        ...

    def load_module_artifact(self, descriptor: ModuleDescriptor) -> LoadedModuleArtifact:
        ...

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
    call_tree_id: str = ''
    caller_hops: tuple[ScopedHop, ...] = ()
    enclosing_flights: tuple[StepFlight[object], ...] = ()
    coalesce_callers: tuple[CoalesceCallerView, ...] = ()
    coalesce_flights: tuple[str, ...] = ()
    turn_entry_stack: tuple[tuple[HostPath, TaskId], ...] = ()
    in_event_chain: bool = False
    on_progress: Optional[Callable[[JsonObject], None]] = None

class ResourceCoordinator:

    def __init__(self, locks_dir: Optional[HostPath]=None, *, cache_dir: Optional[HostPath]=None, workspace_root: Optional[HostPath]=None, resolve_cache_dir: Optional[Callable[[HostPath], HostPath]]=None, is_daemon_host: bool=False) -> None:
        ...

    @property
    def is_daemon_host(self) -> bool:
        ...

    def drain_local_borrowed_locks(self, spec: ResourceAcquireSpec, deadline: float) -> None:
        ...

    def remove_remote_flight(self, flight_id: str) -> None:
        ...

    def evict_local_flight_ident(self, flight_id: str, ident: HolderIdentity, detail: ErrorDetail) -> bool:
        ...

    def handle_remote_flight_control(self, payload: JsonObject) -> JsonObject:
        ...

    def register_remote_flight_join(self, flight_id: str, views: Sequence[CoalesceCallerView], *, origin_ws: Optional[HostPath]=None) -> Optional[tuple[HolderIdentity, ErrorDetail]]:
        ...

    def coalesce_participant_count(self, resource_key: str) -> int:
        ...

    @contextlib.contextmanager
    def pin_inbound_flights(self, flight_ids: Sequence[str]) -> Iterator[None]:
        ...

    def bind_shared_peers(self, peers: weakref.WeakValueDictionary[str, ResourceCoordinator], cache_dirs: dict[str, HostPath], guard: threading.RLock) -> None:
        ...

    def execute(self, spec: ResourceAcquireSpec, leader_fn: Callable[[PriorityHandle, CancellationToken, Optional[StepFlight[TResult]]], TResult], *, extract_release_guard: Optional[Callable[[TResult], Optional[threading.Event]]]=None) -> CoordinatedExecution[TResult]:
        ...

class SharedCancelGroup:

    def __init__(self) -> None:
        ...

    def add_participants(self, caller_tokens: Sequence[CancellationToken]) -> tuple[Optional[Callable[[], None]], ...]:
        ...

    def try_add_participant(self, caller_token: CancellationToken) -> Optional[Callable[[], None]]:
        ...

    @property
    def active_count(self) -> int:
        ...

    def close_all(self) -> None:
        ...

@dataclass(frozen=True, slots=True)
class StepContextCallbacks:
    on_emit_imm: Callable[[EventId, JsonObject, CausalLineage, bool], None]
    on_invoke_task: Callable[[TaskId, JsonObject, Optional[HostPath], Optional[ClientRoutingPolicy]], TaskOutcome[JsonValue]]
    on_progress: Callable[[JsonObject], None]

class StepFlight(Generic[TVal]):

    def __init__(self, priority_handle: PriorityHandle) -> None:
        ...

    def record_notified_workspace(self, ws: HostPath, *, send_tcp: bool) -> bool:
        ...

    def drain_notified_workspaces(self) -> tuple[tuple[HostPath, bool], ...]:
        ...

    def slot_wake_event(self, slot_id: int) -> threading.Event:
        ...

    def seal(self) -> None:
        ...

    def get_slot_error(self, slot_id: int) -> Optional[BaseException]:
        ...

    def effective_deadline(self) -> Optional[float]:
        ...

    def add_caller(self, reg: FlightCallerRegistration, on_progress: Optional[Callable[[JsonObject], None]]) -> tuple[int, Optional[Callable[[], None]]]:
        ...

    def evict_callers_where(self, reg_pred: Callable[[FlightCallerRegistration], bool], view_pred: Callable[[CoalesceCallerView, tuple[str, ...]], bool], exc_factory: Callable[[Sequence[CoalesceCallerView]], BaseException]) -> tuple[bool, bool]:
        ...

    def evict_callers_matching_holder(self, ident: HolderIdentity, leaf_frame: Optional[tuple[HostPath, TaskId]], exc: BaseException) -> tuple[bool, bool]:
        ...

    def seal_and_finalize(self, builder: Callable[[list[LiveFlightParticipant], int], tuple[TBundle, Optional[Callable[[int], None]]]]) -> TBundle:
        ...

    def notify_waiter_aborted(self, slot_id: int) -> None:
        ...

    def broadcast_progress(self, payload: JsonObject) -> None:
        ...

    def snapshot_caller_views(self, visited: Optional[set[int]]=None, *, post_step: bool=False) -> tuple[CoalesceCallerView, ...]:
        ...

    def find_common_conflicting_hop(self, cand_hops: Sequence[ScopedHop]) -> Optional[ScopedHop]:
        ...

    def all_active_callers_have_frame(self, frame: tuple[HostPath, TaskId]) -> bool:
        ...

    def depends_on_flight_ids(self, target_fids: frozenset[str], seen: Optional[set[int]]=None) -> bool:
        ...

    def has_reentrant_caller(self, ident: HolderIdentity, leaf_frame: Optional[tuple[HostPath, TaskId]]=None) -> bool:
        ...

    def complete(self, *, outcome: Optional[TVal]=None, raised_exc: Optional[BaseException]=None) -> None:
        ...

@dataclass(frozen=True, slots=True)
class WorkerBootstrapConfig:
    host: str
    port: int
    boot_id: str
    workspace_root: HostPath
    modules: tuple[ModuleDescriptor, ...]
    is_hot_container: bool = True

@dataclass(frozen=True, slots=True)
class WorkerEquivReply:
    ok: bool
    equiv_key: str = ''
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

def worker_main(argv: Optional[Sequence[str]] = None, env: Optional[MutableMapping[str, str]] = None) -> int:
    ...
```

## 5. 必測封閉性驗收門檻 (Verification Gate — 對標 `verify_execution_live.py` `RC-01 ～ RC-08`)

1. **零逆向匯入、顯式六域匯入白名單、業務階段聚合與零跨協作者私有穿透檢查，以及共置 Worker 強制主控路由檢查**。
2. **帶參 `COALESCE` 中性對稱 `StepFlight` / `FlightCascade` 合併、多跳跨鎖重入（含跨常駐 Daemon 彈跳與 `.pin` 保護）、逐呼叫方非法重入剔除與環路隔離、動態截止預算、優先級傳遞與部分取消不誤殺測試**。
3. **`_ScopedModuleFinder` 合成套件世代熱重載隔離、不遮蔽標準庫匯入、直接幀限定 `importlib.import_module` 並發動態匯入與 PEP 420 命名空間子套件測試**。
4. **`caller_cwd` / `caller_env` 跨熱派發傳遞、`GATED` 巢狀防提權、Worker 收單前後崩潰分流、逐模組跨層級 LIFO 釋放診斷與中毒子進程實際退出後釋鎖測試**。
