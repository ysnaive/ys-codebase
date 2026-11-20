# 子模組架構設計規格：`core.execution.event`（強型別雙緩衝事件佇列與工作區範圍因果環路偵測引擎）

> **所屬功能域**：`Domain 5 — 執行與常駐調度域 (execution/)`
> **模組路徑**：`core_v2/source/core/core/execution/event/`（`engine.py`、`__init__.py`）
> **依賴上限（Allowed Imports）**：`foundation.{primitives, errors, codec}`
> **禁止反向依賴（Forbidden Imports）**：`filesystem/*`、`execution.{lifecycle, runtime, rpc, daemon}`、`surface/*`
> **狀態**：`Active Living Spec — Clean-Sheet Simplified & Orthogonal Benchmark Aligned`

## 1. 模組定位與核心邊界 (Positioning & Clean Separation)

在 `Core 2.0` 中，`core.execution.event` 執行徹底的職責減法與純化：
1. **三類舊機制徹底移除**：廢除 `on_pre / post_cli_dispatch` 攔截器、廢除 `on_register_*` 可變 Callback Hook、廢除 `scripts/hook.*.py` 檔案動態掃描。
2. **零業務執行權與零跨環境匯入（Pure Buffer & Topology Resolver）**：`event` **不載入任何業務模組、不持有跨 `.venv` Python 函式指標、不開執行緒跑業務邏輯**。它專職管理強型別 `EventMetadata` 契約、雙緩衝暫存佇列（`DoubleBufferedEventQueue`）、`ORDERED / UNORDERED` 批次折疊規則、靜態前置過濾條件（`EventBatchEnvelope.filter_for_subscription`）以及工作區範圍因果鏈環路偵測（`CausalLineage` / `ScopedHop`）；產出的待調用目標 `TaskId` 一律交由上層 `lifecycle` / `runtime` 統一派發。
3. **安全閘門訂閱禁令**：凡宣告 `SecurityTier.GATED` 之高危破壞性任務，靜態與執行期一律禁止掛載 `EventSubscriptionSpec`（事件絕不可暗中觸發高危破壞動作）。

## 2. 核心架構設計 (Core Mechanisms)

### 2.1 強型別 `EventMetadata[TPayload]` 與 `ORDERED / UNORDERED` 批次封套折疊

所有跨模組事件皆須定義不可變的 `@dataclass(frozen=True, slots=True)` 負載與顯式 `EventMetadata`。為確保 Tier 0 主控端在不匯入任何 Tier 1 `.venv` 代碼的前提下完成折疊，統一採用**「純資料批次封套（`EventBatchEnvelope`）」**設計：

| `EventOrdering` | 語意定位 | 雙緩衝凍結（`freeze_and_swap`）處置行為 | 典型場景 |
| :--- | :--- | :--- | :--- |
| **`UNORDERED`**<br>（預設：無序狀態通知） | 訂閱者僅關心「狀態已變更」或「變更範圍聯集」，不關心單輪重複觸發次數。 | **純資料打包折疊，單輪僅觸發訂閱者 1 次**：同一暫存批次內若出現 $N$ 顆同 `EventId` 事件，主控端以該 `EventId` 於批次中**首次出現之槽位**為錨點，將其 `raw_payload` 與逐筆 `record_lineages` 保序打包折疊為單一 `EventBatchEnvelope(payloads=(p_1, ..., p_N))`，**對每個匹配的訂閱 `Task` 僅派發唯一一次**（經 `filter_for_subscription` 僅合併實際命中靜態過濾之因果鏈），交由訂閱端 Worker 內的 `BoundEventSubscription.decode_and_map()` 執行 `batch_mapper` 轉型。 | `core.space_updated`<br>`ast.graph_updated`<br>`core.workspace_reloaded`<br>`core.config_changed` |
| **`ORDERED`**<br>（有序操作序列） | 每次發生的先後次序與獨立次數皆具業務意義，不可去重或合併。 | **嚴格 FIFO 逐顆派發**：每顆事件各自封裝為單元素 `EventBatchEnvelope(payloads=(p_i,))` 嚴格保持 `emit` 時間順序（與同批其他 `ORDERED` 事件及各 `UNORDERED` 事件首次出現之錨點槽位維持相對順序；後續同 `EventId` 之 `UNORDERED` 事件仍依前項規則折疊回首次出現槽位，以維持單輪僅觸發 1 次之不變量），$N$ 顆事件即依序產出 $N$ 次訂閱 `Task` 調用。 | 嚴格時序狀態遷移、模組移除前置清理序列 |

### 2.2 `emit` vs. `emit_imm` 雙發射原語與同單步多發基準因果鏈（禁止全域 `flush`）

為維持執行期 Turn 的全域可預測性，**嚴禁提供強制提前排空佇列中他人暫存事件的全域 `flush_events()` 指令**，統一採用經典雙原語：

1. **`ctx.emit(event_meta, payload)`（預設延遲入列 — Post-Success Sub-Buffer + 入站基準分支推進）**：
   - 每個單步執行器初始化 `TaskLocalOutbox(emitter_task, base_lineage, workspace_scope=...)` 時，固定綁定該步入站之不可變基準祖先鏈 `base_lineage` 與當前正規化工作區識別碼 `workspace_scope`。
   - **同單步多發防假自環保證（`SIBLING_MULTI_EMIT`）**：當同一 `Task` 單步內連續呼叫多次 `ctx.emit()` 時，`TaskLocalOutbox.stage()` **每次皆基於該步固定之 `self._base_lineage.advance(event_id, workspace_scope=...)` 計算平行子鏈，絕不在單步內原地覆寫累進 `self._base_lineage`**，確保同單步連發多顆同 `EventId` 事件完全合法不誤報自環，而下游訂閱者若在同一工作區再次發射回祖先 `EventId` 則立即精確攔截（跨不同子工作區的相同 `EventId` 則因 `workspace_scope` 互異而合法放行）。
   - **單步成功即提交**：唯有當該 `Task` 單步正常返回時，局部暫存區的事件紀錄才會經 `drain_committed()` 移交至宿主 `TurnScope` 的 `DoubleBufferedEventQueue.append_committed()`（或對稱 `FlightCascade`）；若該單步拋錯或被取消，呼叫 `discard()` 直接銷毀局部暫存區。
2. **`ctx.emit_imm(event_meta, payload, *, strict: bool = False)`（單顆立即同步派發）**：
   - **絕不觸碰或提前沖刷 `staging_list` 中任何其他待處理事件**。
   - 透過 `TaskLocalOutbox.compute_immediate_lineage(event_id)` 基於當前單步入站 `base_lineage` 產生子因果鏈（不污染後續平行 `emit` 之基準鏈），攜帶當前 `CallPropagationContext` 立即同步請求 `runtime` 依序執行該事件的訂閱 `Task`（若身處對稱 `COALESCE` 中性單飛內且所有存活參與者皆與該立即因果鏈衝突，派發前立即拋出 `EventCycleError`），完成後返回呼叫端下一行。

### 2.3 宣告式前置過濾器（防「未過濾先搶占」與因果污染）

為防止無關事件在進入 Worker 執行 `batch_mapper` 返回 `None` 之前，就先在主控端 `ResourceCoordinator` 觸發 `PREEMPT` 誤殺正在執行的正常任務，或將未命中過濾條件的因果鏈污染至無關訂閱者：
- `EventSubscriptionSpec` 與靜態路由 `SubscriptionRouteSpec` 支援宣告純資料 `payload_filter: Optional[Mapping[str, tuple[JsonPrimitive, ...]]]`。
- 主控端在派發前先透過 `EventBatchEnvelope.filter_for_subscription()` 比對靜態過濾條件並僅合併命中紀錄之 `CausalLineage`；未命中的事件直接略過，絕不請求 `resource_key` 鎖或觸發 `PREEMPT`。

### 2.4 工作區範圍因果環路偵測（`ScopedHop` & `CausalLineage`）與致命異常傳播

1. **單點推進精確閉環攔截與空範圍全域萬用語意**：每顆事件封套及跨任務 `CallPropagationContext` 全程傳遞 `CausalLineage`（`UNORDERED` 批次折疊與菱形匯流 `FANOUT_DIAMOND_DAG` 時透過 `CausalLineage.merge()` 取保序去重聯集）。一旦 `hop_conflicts()` 發現目標 `(workspace_scope, EventId)` 已存在於當前祖先鏈中，**第 1 次閉環瞬間立即拋出致命 `EventCycleError` 並中止整個 Turn**。其中 `workspace_scope=""`（空字串）為顯式**全域萬用範圍（Wildcard Scope）**，於 `hop_conflicts()` 與任何具名工作區範圍皆視為衝突，且在 `CausalLineage.merge()` 合併同 `EventId` 跳點時自動將具名範圍收斂升級為全域萬用跳點；跨子工作區隔離派發時由 `runtime` 一律傳入正規化 `workspace_root.comparison_key`。
2. **一般訂閱者故障隔離**：非環路之一般業務異常僅作廢該失敗訂閱者自身的局部事件並記錄於 `TurnScope.record_event_diagnostic()`（對稱 `StepFlight` / `FlightCascade` 等待者亦同步收到對應診斷），不中斷同輪其他獨立訂閱者。

## 3. 核心 OOP 類別與強型別契約規格 (`core/execution/event/engine.py`)

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Generic, Mapping, Optional, Protocol, Sequence, TypeVar
from core.foundation.primitives import EventId, JsonObject, JsonPrimitive, TaskId

TPayload = TypeVar("TPayload")
TIn = TypeVar("TIn")
TIn_co = TypeVar("TIn_co", covariant=True)
ScopedHop = tuple[str, EventId]


class EventOrdering(Enum):
    UNORDERED = "unordered"  # 同輪自動打包折疊，每個訂閱 Task 僅觸發一次
    ORDERED = "ordered"      # 嚴格維持 FIFO 順序，逐顆獨立觸發


@dataclass(frozen=True, slots=True)
class EventMetadata(Generic[TPayload]):
    event_id: EventId
    payload_type: type[TPayload]
    ordering: EventOrdering = EventOrdering.UNORDERED
    description: str = ""


def hop_conflicts(existing: ScopedHop, cand_scope: str, cand_id: EventId) -> bool: ...
def normalize_payload_filter(
    payload_filter: Optional[Mapping[str, Sequence[JsonPrimitive]]],
) -> Optional[Mapping[str, tuple[JsonPrimitive, ...]]]: ...


@dataclass(frozen=True, slots=True)
class CausalLineage:
    """全程隨 Event 與 CallPropagationContext 傳遞之不可變因果祖先鏈。"""
    chain: tuple[EventId, ...] = ()
    scopes: tuple[str, ...] = ()

    def scoped_hops(self) -> tuple[ScopedHop, ...]: ...
    def advance(
        self,
        next_event_id: EventId,
        *,
        source_task: Optional[str] = None,
        workspace_scope: str = "",
    ) -> "CausalLineage": ...

    @staticmethod
    def merge(lineages: Sequence["CausalLineage"]) -> "CausalLineage": ...


@dataclass(frozen=True, slots=True)
class RawEventRecord:
    """已完成 advance 校驗之單筆事件序列化紀錄。"""
    event_id: EventId
    emitter_task: TaskId
    raw_payload: JsonObject
    ordering: EventOrdering
    lineage: CausalLineage = field(default_factory=CausalLineage)


@dataclass(frozen=True, slots=True)
class EventBatchEnvelope:
    """freeze_and_swap() 折疊後交付單步派發之純資料批次封套（Tier 0 零業務匯入）。"""
    event_id: EventId
    ordering: EventOrdering
    payloads: tuple[JsonObject, ...]
    merged_lineage: CausalLineage
    record_lineages: tuple[CausalLineage, ...] = ()

    def filter_for_subscription(
        self,
        payload_filter: Optional[Mapping[str, tuple[JsonPrimitive, ...]]],
    ) -> tuple[tuple[JsonObject, ...], CausalLineage]: ...


class BoundEventSubscription(Protocol, Generic[TIn_co]):
    """共變安全訂閱協定，使單一 TaskMetadata[TIn, TOut] 可同時訂閱多種異質事件負載。"""
    @property
    def event_id(self) -> EventId: ...
    @property
    def payload_filter(self) -> Optional[Mapping[str, tuple[JsonPrimitive, ...]]]: ...
    def decode_and_map(self, raw_payloads: Sequence[JsonObject]) -> Optional[TIn_co]: ...


@dataclass(frozen=True, slots=True)
class EventSubscriptionSpec(Generic[TPayload, TIn]):
    """綁定於目標 TaskMetadata 之強型別事件訂閱規格（禁止掛載於 SecurityTier.GATED 任務）。"""
    event: EventMetadata[TPayload] | EventId
    batch_mapper: Callable[[Sequence[TPayload]], Optional[TIn]]
    payload_filter: Optional[Mapping[str, tuple[JsonPrimitive, ...]]] = None
    payload_type: Optional[type[TPayload]] = None

    @property
    def event_id(self) -> EventId: ...
    def decode_and_map(self, raw_payloads: Sequence[JsonObject]) -> Optional[TIn]: ...


class TaskLocalOutbox:
    """單步執行局部暫存區：固定基於入站 base_lineage 分支呼叫 advance()，支援同單步多發同型事件且單步成功後移交佇列。"""
    def __init__(
        self,
        emitter_task: TaskId,
        base_lineage: CausalLineage,
        *,
        workspace_scope: str = "",
    ) -> None: ...
    @property
    def base_lineage(self) -> CausalLineage: ...
    def compute_immediate_lineage(self, event_id: EventId) -> CausalLineage: ...
    def stage(
        self,
        event_id: EventId,
        raw_payload: JsonObject,
        ordering: EventOrdering = EventOrdering.UNORDERED,
    ) -> RawEventRecord: ...
    def discard(self) -> None: ...
    def drain_committed(self) -> tuple[RawEventRecord, ...]: ...


class DoubleBufferedEventQueue:
    """執行緒安全雙緩衝佇列：append_committed 入列已校驗紀錄；freeze_and_swap 原子交換並折疊 UNORDERED 批次。"""
    def __init__(self) -> None: ...
    @property
    def has_pending(self) -> bool: ...
    def append_committed(self, records: Sequence[RawEventRecord]) -> None: ...
    def clear(self) -> None: ...
    def freeze_and_swap(self) -> tuple[EventBatchEnvelope, ...]: ...
```

## 4. 必測驗收門檻 (Verification Gate — 對標 `verify_execution_live.py` `RC-02, RC-06, RC-08`)

1. **同單步多發同型事件（`SIBLING_MULTI_EMIT`）與 `UNORDERED` 折疊測試**：驗證同一單步連發多顆同 `EventId` 事件不誤報假自環，且於下輪折疊為單一 `EventBatchEnvelope` 僅觸發訂閱者 1 次。
2. **靜態前置過濾防誤搶占與逐筆因果隔離測試**：驗證未命中 `payload_filter` 之事件直接於主控端略過，不觸發 `PREEMPT` 亦不將過濾排除紀錄之因果鏈混入命中訂閱者。
3. **菱形匯流合法放行、跨子工作區同事件名放行與同工作區因果閉環攔截測試**：驗證 `FANOUT_DIAMOND_DAG` 正常合流，而同工作區真實因果閉環（含跨 `COALESCE` 對稱 `FlightCascade` 合流與嵌套 `emit_imm`）瞬間拋出 `EventCycleError` 立即中止全 Turn。
4. **訂閱故障隔離與對稱 `COALESCE` 錯誤傳播測試**：驗證一般業務異常不中斷同輪獨立訂閱者，且錯誤診斷正確傳播予所有關聯 `COALESCE` 等待者。
