# 子模組架構設計規格：`core.execution.lifecycle`（三大執行期生命週期與雙緩衝 Turn 狀態機）

> **所屬功能域**：`Domain 5 — 執行與常駐調度域 (execution/)`
> **模組路徑**：`core_v2/source/core/core/execution/lifecycle/`（`engine.py`、`__init__.py`）
> **依賴上限（Allowed Imports）**：`foundation/*`、`execution.event`
> **禁止反向依賴（Forbidden Imports）**：`execution.{runtime, rpc, daemon}`、`surface/*`
> **狀態**：`Active Living Spec — Clean-Sheet Simplified & Orthogonal Benchmark Aligned`

## 1. 模組定位與單向解耦邊界 (Positioning & Acyclic Seam)

**`core.execution.lifecycle` 專職定義並驅動全系統「業務代碼執行期（Execution Lifecycle）」的確定性狀態機**。

### 1.1 主控唯一持有 `TurnScope` 原則
- **Turn 狀態機集中於主控端**：無論單次 Turn 內部跨派多少個 Tier 1 `.venv` 子進程（常駐 Worker 或冷啟動 `OneShotVenvHost`），**完整 Turn 狀態機（Steps 2～5 的 `TurnScope` 與雙緩衝佇列）永遠由發起該 Turn 的主控協調端唯一持有**；子進程僅執行單步 `Step` 並回傳 `RawEventRecord` 清單。
- **零反向匯入介面**：定義泛型 `TaskStepExecutor(Protocol, Generic[TReqContra])` 由上層 `execution.runtime` 實作注入，嚴守 `runtime -> lifecycle -> event` 單向無環依賴（零 `Any`）。

## 2. 三大執行期生命週期體系 (Three Execution Lifecycle Profiles)

### 2.1 體系一：冷派發完整生命週期（`ColdTurnRunner`：Steps 1 ～ 6）
適用於無常駐 Daemon 時的 CLI / SDK 本地執行與 `COLD_ONLY` 任務：

```text
[Step 1: 環境與底座按需初始化 (Bootstrap, Shared/Exclusive Deployment Guard & Hook)]
   │ 1. 非安裝類冷執行先獲取 .cache/locks/installer.lock 共享讀鎖（安裝突變任務則獲取獨佔寫鎖）
   │ 2. 觸發 on_bootstrap_check 校驗磁碟組態與模組描述子指紋，建立 LifoResourceStack 與本 Turn 專屬 DoubleBufferedEventQueue
   │ 3. 業務模組採 Lazy Init：僅在 Step 2/5 實際被觸碰時呼叫 on_init 並壓入 LifoResourceStack
   ▼
[Step 2: 主任務派發 (Primary Task Execution)]
   │ 透過 TaskStepExecutor.run_primary_step 執行目標 Task（若成功提交事件則匯入 committed_events）
   ▼
[Step 3~5: 雙緩衝事件排空迴圈 (Double-Buffered Event Drain Loop)]
   │ while event_queue.has_pending:
   │     frozen_batches = event_queue.freeze_and_swap()
   │     for batch_envelope in frozen_batches:
   │         executor.run_event_step(batch_envelope, turn_scope)  # 若遇 fatal_abort_turn (如 EventCycleError) 立即中止迴圈！
   ▼ (當 staging_list 為空時自然跳出迴圈)
[Step 6: 收尾與 LIFO 環境卸載 (Deterministic Fault-Isolated Teardown)]
   │ 於最外層 finally 依「後初始化者先關閉（LIFO）」反向呼叫所有已載入模組、單次子進程與檔案鎖之 close()（單一 close() 異常隔離為 ErrorCode.TEARDOWN_ERROR 並記錄於 teardown_diagnostics，保證底層資源 100% 釋放）
   ▼
返回結構化 TurnExecutionReport（確保 0 ResourceWarning）
```

### 2.2 體系二：熱派發請求生命週期（`TurnEngine`：僅 Steps 2 ～ 5）
適用於已啟動常駐容器承接單次請求或同工作區頂層 `StepFlight` 單飛排空：
- **省略 Step 1 與全域 Step 6**：複用常駐底座與預熱模組實例，結束時僅釋放單次 `TurnScope.scoped_stack` 暫態資源；事件觸發型背景 Turn 與頂層單飛 `StepFlight` 衍生鏈共用 `execute_event_turn()` 走同一條 BFS + LIFO 管線。
- **Turn 級別佇列隔離與頂層 `COALESCE` 衍生收斂**：每個前景 `HOT_FOREGROUND`、背景 `HOT_BACKGROUND` 與頂層同工作區 `StepFlight` 各自擁有獨立 `TurnScope` 與 `DoubleBufferedEventQueue`；多方合併（`COALESCE`）時，衍生鏈於 `StepFlight` 單次排空並將 `event_diagnostics`、`teardown_diagnostics` 與 `fatal_error` 精確傳播予所有存活等待者（巢狀與事件鏈呼叫自動降級為 `SERIALIZE`）。

### 2.3 體系三：後台常駐容器生命週期（`WorkerContainerLifecycle`：統一狀態機與預熱故障隔離）
適用於常駐守護進程（`DaemonRunState = ContainerState` 共用同一狀態列舉）與長駐容器主控：

```text
UNINITIALIZED / BOOTING ──(warmup 掛載底座)──> WARMING ──(on_start 逐模組故障隔離預熱)──> READY
                                                                                            │  ▲
                                                                           (quiesce 讓位釋鎖) │  │ (resume 重載組態與擴充回就緒)
                                                                                            ▼  │
STOPPED <──(LIFO close_all_lifo)── DRAINING <──(drain_and_stop)──────────────────────── QUIESCED
```

- **預熱階段局部故障隔離（`P1_INIT_OR_WARMUP` Guard）**：容器於 `WARMING` 階段逐一呼叫各模組預熱閉包時，單一擴充模組若拋出異常，容器僅將該模組記錄於 `degraded_modules` 結構化診斷表，**正常推進容器進入 `READY` 服務其餘健康模組**。

## 3. 異常、取消與搶占在生命週期中的確定性規則

| 執行情境 / 中斷時機 | `core.execution.lifecycle` 確定性狀態跳轉與處置行為 |
| :--- | :--- |
| **Step 1（底座鎖定或 `on_bootstrap_check`）被取消或拋錯** | 立即中止當次請求後續步驟，跳入 **Step 6** 將先前已壓入 `LifoResourceStack` 的元件按 LIFO 反向關閉。 |
| **`WARMING` 階段單一擴充模組預熱失敗** | 捕獲並寫入 `degraded_modules`，隔離該故障模組，主容器繼續進入 `READY`。 |
| **Step 2（主任務）自身拋錯或被取消** | 丟棄主任務自身未提交之局部事件；**若 Step 2 期間曾呼叫子任務且子任務已提交事件（且非呼叫端主動取消），仍排空該已提交子事件以維持下游一致**，隨後清理收尾。 |
| **Step 3～5 單一訂閱者拋出一般業務異常** | 丟棄該失敗訂閱者自身的局部事件並透過 `record_event_diagnostic()` 記錄，**繼續執行同輪其餘獨立訂閱者**。 |
| **Step 3～5 單一訂閱者遭他輪 `PREEMPT` 搶占取消** | 僅標記 `preempted=True` 中止該單一訂閱步，**不寫入錯誤診斷且不中斷同輪 `frozen_batches` 中其他無關訂閱者**。 |
| **Step 3～5 發生致命錯誤（`fatal_abort_turn=True`，如 `EventCycleError`）或 `turn.cancel_token` 被取消** | 立即清空未派發佇列並中止整個事件排空迴圈，寫入 `fatal_event_error` 或回傳取消結果，安全進入 `scoped_stack.close_all_lifo()`。 |
| **Step 6（LIFO `close()`）單一資源釋放拋出異常** | `LifoResourceStack` 捕獲並轉為 `ErrorDetail(ErrorCode.TEARDOWN_ERROR, ...)`，**強制繼續反向執行剩餘所有底層資源與檔案鎖之 `close()`**。 |

## 4. 核心 OOP 類別與強型別契約規格 (`core/execution/lifecycle/engine.py`)

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Generic, Mapping, Optional, Protocol, Sequence, TypeVar
from core.execution.event import DoubleBufferedEventQueue, EventBatchEnvelope, RawEventRecord
from core.foundation.errors import ErrorDetail
from core.foundation.observability import CancellationToken
from core.foundation.primitives import JsonValue, ModuleId

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


class LifoResourceStack:
    """嚴格執行緒安全 LIFO 反向釋放堆疊，單一 close() 異常隔離為 TEARDOWN_ERROR 並確保底層資源 100% 釋放。"""
    def __init__(self) -> None: ...
    def push_closeable(self, owner: str, close_fn: Callable[[], None]) -> None: ...
    def push_diagnostic_closeable(self, owner: str, close_fn: Callable[[], Sequence[ErrorDetail]]) -> None: ...
    def pop_tagged_by_prefixes(
        self,
        prefixes: frozenset[str],
    ) -> tuple[tuple[str, Callable[[], Sequence[ErrorDetail]]], ...]: ...
    @staticmethod
    def run_void_closer(owner: str, close_fn: Callable[[], None]) -> tuple[ErrorDetail, ...]: ...
    @staticmethod
    def run_closers(
        entries: Sequence[tuple[str, Callable[[], Sequence[ErrorDetail]]]],
    ) -> tuple[ErrorDetail, ...]: ...
    def close_all_lifo(self) -> tuple[ErrorDetail, ...]: ...


@dataclass(slots=True)
class TurnScope:
    """單次 Turn (Steps 2~5) 的主控端隔離作用域。"""
    turn_id: str
    kind: TurnKind
    cancel_token: CancellationToken
    event_queue: DoubleBufferedEventQueue = field(default_factory=DoubleBufferedEventQueue)
    scoped_stack: LifoResourceStack = field(default_factory=LifoResourceStack)
    on_diagnostic: Optional[Callable[[ErrorDetail], None]] = None

    def record_event_diagnostic(self, detail: ErrorDetail) -> None: ...
    def snapshot_event_diagnostics(self) -> tuple[ErrorDetail, ...]: ...
    def close_scoped_stack_recorded(self) -> tuple[ErrorDetail, ...]: ...


@dataclass(frozen=True, slots=True)
class StepExecutionResult(Generic[TOut_co]):
    ok: bool
    outcome: Optional[TOut_co] = None
    error: Optional[ErrorDetail] = None
    preempted: bool = False
    coalesced: bool = False
    fatal_abort_turn: bool = False
    committed_events: tuple[RawEventRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class TurnExecutionReport:
    turn_id: str
    primary_result: StepExecutionResult[JsonValue]
    event_diagnostics: tuple[ErrorDetail, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    fatal_event_error: Optional[ErrorDetail] = None


class TaskStepExecutor(Protocol, Generic[TReqContra]):
    """由上層 execution.runtime 實作注入之單步執行協定。"""
    def run_primary_step(self, request: TReqContra, turn: TurnScope) -> StepExecutionResult[JsonValue]: ...
    def run_event_step(self, batch: EventBatchEnvelope, turn: TurnScope) -> Sequence[StepExecutionResult[JsonValue]]: ...
    def finalize_turn_events(self, turn: TurnScope, *, abort_only: bool = False) -> Optional[ErrorDetail]: ...


class TurnEngine(Generic[TReq]):
    """執行核心 Steps 2 ~ 5（主任務 + 雙緩衝凍結 Swap 事件排空迴圈 + LIFO 暫態資源回收）。"""
    def __init__(self, executor: TaskStepExecutor[TReq]) -> None: ...
    def execute_turn(
        self,
        request: TReq,
        kind: TurnKind,
        *,
        cancel_token: Optional[CancellationToken] = None,
        turn_id: Optional[str] = None,
        scope: Optional[TurnScope] = None,
    ) -> TurnExecutionReport: ...
    def execute_event_turn(
        self,
        scope: TurnScope,
        seed_records: Sequence[RawEventRecord],
        *,
        on_events_staged: Optional[Callable[[Sequence[RawEventRecord]], None]] = None,
    ) -> TurnExecutionReport: ...
    def drain_turn_scope(
        self,
        scope: TurnScope,
        *,
        on_events_staged: Optional[Callable[[Sequence[RawEventRecord]], None]] = None,
    ) -> Optional[ErrorDetail]: ...


class ColdTurnRunner(Generic[TReq]):
    """驅動體系一（於上層 ColdInstallerLockManager 租約保護下執行完整冷回合 LIFO 掛載與異常收斂）。"""
    def __init__(
        self,
        turn_engine: TurnEngine[TReq],
        *,
        on_bootstrap_check: Optional[Callable[[LifoResourceStack], None]] = None,
    ) -> None: ...

    def execute_leased_turn(
        self,
        request: TReq,
        *,
        cancel_token: Optional[CancellationToken] = None,
        turn_id: Optional[str] = None,
        scope: Optional[TurnScope] = None,
        fallback_task: Optional[str] = None,
    ) -> TurnExecutionReport: ...


class WorkerContainerLifecycle:
    """驅動體系三（常駐容器狀態機與模組降級單一權威來源）：支援啟動階段推進、預熱故障隔離、quiesce 讓位、resume 恢復與 LIFO 停機。"""
    def __init__(self, *, quiesce_probe: Optional[Callable[[], bool]] = None) -> None: ...
    @property
    def base_state(self) -> ContainerState: ...
    @property
    def state(self) -> ContainerState: ...
    def transition_boot_phase(self, target: ContainerState) -> None: ...
    @property
    def degraded_modules(self) -> Mapping[ModuleId, ErrorDetail]: ...
    @property
    def resource_stack(self) -> LifoResourceStack: ...
    def get_degraded(self, module_id: ModuleId) -> Optional[ErrorDetail]: ...
    def get_runtime_degraded(self, module_id: ModuleId) -> Optional[ErrorDetail]: ...
    def has_index_degraded(self, module_id: ModuleId) -> bool: ...
    def snapshot_index_degraded(self) -> dict[ModuleId, ErrorDetail]: ...
    def record_degraded(self, module_id: ModuleId, detail: ErrorDetail) -> None: ...
    def sync_index_degraded(self, index_errors: Mapping[ModuleId, ErrorDetail]) -> None: ...
    def clear_degraded(self, modules: Optional[frozenset[ModuleId]] = None) -> None: ...
    def warmup(self, warmup_hooks: Optional[Mapping[ModuleId, Callable[[], None]]] = None) -> None: ...
    def begin_hot_turn(
        self,
        kind: TurnKind,
        *,
        cancel_token: Optional[CancellationToken] = None,
        turn_id: Optional[str] = None,
    ) -> Optional[TurnScope]: ...
    def quiesce(self) -> None: ...
    def resume(self) -> None: ...
    def reload_modules(self, modules: Optional[frozenset[ModuleId]] = None) -> None: ...
    def drain_and_stop(
        self,
        grace_period_ms: int = 3000,
        *,
        on_drain: Optional[Callable[[int], None]] = None,
    ) -> tuple[ErrorDetail, ...]: ...
```

## 5. 必測驗收門檻 (Verification Gate — 對標 `verify_execution_live.py` `RC-02, RC-03, RC-06, RC-07`)

1. **冷派發共享部署鎖、組態指紋校驗與 LIFO 異常隔離測試**：驗證外部安裝器持獨佔鎖期間冷啟動安全等待，且單一 `close()` 拋錯記錄 `TEARDOWN_ERROR` 不影響底層句柄釋放與 `0 ResourceWarning`。
2. **`WARMING` 單模組預熱失敗隔離測試**：模擬單一擴充模組 `on_start` 拋錯，驗證容器正常進入 `READY` 且其餘模組正常服務。
3. **對稱 `COALESCE` Step 5 崩潰與診斷傳播測試**：模擬共享衍生鏈在事件排空階段發生錯誤或環路，驗證所有存活搭便車等待者精確收到對應診斷或致命錯誤而不誤拿乾淨成功。
4. **`QUIESCED <-> READY` 完整往返與 `EventCycleError` 立即中止測試**。
