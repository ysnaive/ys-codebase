# 子模組架構設計規格：`core.runtime`（指令分派與受管業務執行引擎）

> **所屬分層**：`Layer 4`（動態調度與執行層）
> **模組路徑**：`core_v2/source/core/core/runtime/`
> **依賴上限（Allowed Imports）**：`L0 (primitives, errors)`、`L1 (codec, platform, observability)`、`L2 (config, vfs, space, storage)`、`L3 (contributes, env)`、`L4 (core.event)`
> **禁止反向依賴（Forbidden Imports）**：`core.cli`、`core.rpc`、`core.daemon`、`core.lifecycle`

## 1. 模組定位與職責邊界 (Positioning & Boundaries)

在 `1.x` 架構中，指令分派器同時混雜了命令列解析、`--help` 文字渲染、Localhost HTTP 熱派發連線、自動拉起守護進程、動態篡改全域 `sys.argv` / `sys.path`、弱型別 `CmdBags` 字典傳遞與全域 `pre_cli_dispatch` 攔截器，導致冷啟動與常駐 `WarmWorker` 行為分歧且狀態極易互相污染。

在 `Core 2.0` 中，**`core.runtime` 是全系統業務資料平面的唯一執行心臟**。它不感知終端機 `sys.argv`，也不感知網路 Socket，專職負責將標準化的**強型別調用封套（`InvocationEnvelope`）**或**領域事件（`DomainEvent`）**，在嚴格隔離的受管沙盒內分派至目標業務模組，並回傳確定性的**強型別執行結果（`ExecutionOutcome[TResp]`）**。

### 1.1 跨子模組職責切分矩陣

| 關注點 | 負責子模組 | 邊界說明 |
| :--- | :--- | :--- |
| 命令列字串切詞、`--help` 排版、終端雙軌列印 | `core.cli` (L5) | 將 `argv` 轉為 `InvocationEnvelope`；拿到 `ExecutionOutcome` 後負責渲染 Human / `--json` 輸出與返回 Exit Code。 |
| 探測本機 Daemon 在線狀態、跨進程 Socket 通訊 | `core.rpc` (L4) | 決定走遠端 Daemon 或本地直跑；保證「請求一旦被遠端接受（`accepted=True`）絕不自動降級重跑」以防雙重執行。 |
| 套件安裝、升級、重載、卸載與環境重建 | `core.lifecycle` (L4) | 處理變更 `.modules/` 與 `.venv/` 的系統級原子交易；需要觸發模組安裝/升級 Hook 時，委派 `core.runtime` 執行。 |
| 常駐進程保活、Idle TTL、Tier 1 常駐子進程池 | `core.daemon` (L4) | 維護預熱好的 Tier 0 主進程與 Tier 1 `.venv/<group>_<hash>/` 常駐子進程池；每個子進程內部皆運行同一個 `core.runtime`。 |
| **路由綁定、快照閘門、DI 組裝、強型別轉型、執行沙盒** | **`core.runtime` (L4)** | **本模組核心範疇**：確保同一個業務模組在「冷啟動直跑、Daemon Tier 0、Tier 1 隔離開箱子進程」三種環境下具備 100% 完全一致的執行語意。 |

## 2. 核心架構不變量 (Core Invariants)

1. **零全域狀態與零環境篡改（Zero Global Mutation）**：
   - 徹底廢除全域單例 `get_runtime_context()`、禁止在執行期修改 `sys.argv`、禁止呼叫 `os.chdir()`。
   - 呼叫端工作目錄（`caller_cwd: HostPath`）、取消信號（`CancellationToken`）與進度回報器（`ProgressReporter`）一律封裝於不可變 `CommandContext` 顯式傳入業務方法。
2. **運行端空間剛性守門（`.modules/` Only Guardrail）**：
   - `ProtectedModuleLoader` 嚴格限制僅允許載入已物化部署之 `module://<mod>/`（`.modules/<mod>/`）空間代碼，**絕對禁止讀取或 fallback 至 `source/` 開發源碼目錄**。
3. **前景讀路徑 100% 零寫入（Snapshot-First Consistency）**：
   - 徹底廢除 `on_pre_cli_dispatch` 全域攔截器與讀路徑上的懶同步寫入（JIT Index Write）。
   - 凡標記為 `CommandSemantics.READ_SNAPSHOT` 的查詢指令，預設（`SyncMode.SNAPSHOT_FAST`）直接綁定 `core.storage` 最新已提交世代 `SnapshotGen` 毫秒級零鎖執行，並在回傳封套自動附帶 `SyncStatusMeta`（提示背景是否正在追平）；僅在顯式指定 `SyncMode.WAIT_SYNC`（`--sync`）時，才先等待 `core.event` 單寫者管線排空並提交新世代後，再以唯讀快照執行查詢。
4. **Tier 0 / Tier 1 環境嚴格物理隔離（Zero `sys.path` Cross-Pollution）**：
   - Tier 0 內核進程永不將 Tier 1 模組的 `.venv/<group>_<hash>/site-packages` 塞入自身 `sys.path`。
   - 當在無 Daemon 的冷啟動模式下呼叫 Tier 1 模組指令時，`core.runtime` 自動透過 `OneShotVenvHost` 以目標 `.venv/<group>_<hash>/python` 啟動單次受管子進程執行該 `InvocationEnvelope`（子進程內部啟動標準 `InProcessRuntimeHost` 執行完畢即退出，0 `.pyd` 常駐句柄殘留）。
5. **單執行緒無鎖業務沙盒與輸出流鐵壁保護（Stream & Concurrency Sandbox）**：
   - 業務模組實例不持有跨請求可變快取，且單次業務調用預設於受管執行緒內無鎖運行。
   - 業務 Handler 只回傳強型別資料物件 `TResp`，嚴禁直接 `print()`；`TaskSandbox` 透過 `StreamGuard` 攔截底層套件意外寫入 `stdout` 的雜訊並導向診斷日誌，確保 `--json` 與 RPC 串流 100% 純淨。

## 3. 七階段確定性指令分派流水線 (7-Stage Dispatch Pipeline)

```text
InvocationEnvelope
   │
   ▼
[Stage 1: Route & Contract Binding] ──(未知模組/指令)──> UnknownCommandError (附 Did-you-mean 建議, Exit 2)
   │ 產出 BoundCommandSpec (含 Tier 0/1、READ/MUTATE 語意、SecurityTier、TReq/TResp 型別)
   ▼
[Stage 2: Security & Capability Gate] ──(未獲 GATED/CONDITIONAL 授權)──> PermissionDeniedError (Exit 126)
   │
   ▼
[Stage 3: Execution Host Selection]
   ├── 若目標為 Tier 1 且當前進程 EnvHash != 目標 EnvHash：
   │      └─> 委派 IsolatedVenvHost（常駐模式下由 Daemon 路由至預熱 Worker；冷啟動下啟動單次 .venv 子進程）
   ▼ (當前進程環境已匹配目標模組：Tier 0 於主進程，或已身處目標 Tier 1 Worker 進程內)
[Stage 4: Consistency & Sync Barrier]
   ├── READ_SNAPSHOT + SNAPSHOT_FAST (預設)：O(1) 取得當前 committed_gen 與背景待處理數，0 等待放行
   ├── READ_SNAPSHOT + WAIT_SYNC (--sync)  ：等待 core.event 排空目標空間變更並提交最新世代後，綁定新快照
   └── MUTATE_STATE                        ：配置受管寫入能力（或單寫者序列化憑證）
   │
   ▼
[Stage 5: Protected Load & Explicit DI] ──(載入異常)──> 原子回滾 sys.modules，回傳 ModuleLoadError (Exit 1)
   │ 透過 ModuleContainer 取得/實例化目標 YscbModule（建構子注入 ScopedVfs / Storage / Config / Contributes）
   ▼
[Stage 6: Typed Request Codec] ──(欄位/型別/URI 不合法)──> SchemaValidationError (附欄位糾錯, Exit 2)
   │ 由 DataclassCodec 將 raw_payload 轉為不可變強型別 req: TReq
   ▼
[Stage 7: TaskSandbox Execution & Outcome Normalization]
   │ 建立顯式 CommandContext (CancellationToken, ProgressReporter, SnapshotReadView, caller_cwd)
   │ 啟動 StreamGuard 隔離 stdout -> 呼叫 handler.execute(req, ctx) -> 收集 StageMetrics
   ▼
ExecutionOutcome[TResp] (含強型別 payload / 結構化錯誤、SnapshotGen、SyncStatusMeta、StageMetrics)
```

## 4. 核心 OOP 類別體系與強型別契約規格 (OOP Architecture & Contracts)

### 4.1 調用與結果值物件（`core/runtime/contracts.py`）

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Mapping, Optional, TypeVar
from core.primitives import EnvHash, HostPath, ModuleId, SnapshotGen, TaskId
from core.errors import ErrorDetail

TReq = TypeVar("TReq")
TResp = TypeVar("TResp")


class ExecutionTier(Enum):
    TIER_0_STDLIB = "tier_0"       # 純標準庫模組，可直跑於內核主進程
    TIER_1_ISOLATED = "tier_1"     # 具 pip_dependencies 之隔離環境模組


class CommandSemantics(Enum):
    READ_SNAPSHOT = "read_snapshot"  # 純讀取查詢：預設零鎖秒回快照，支援 --sync
    MUTATE_STATE = "mutate_state"    # 狀態變更或外部副作用操作


class SecurityTier(Enum):
    SAFE = "safe"                    # 唯讀或無破壞性，Agent 可自主呼叫
    CONDITIONAL = "conditional"      # 受條件約束之變更操作
    GATED = "gated"                  # 高風險/發布/刪除操作，需明確授權憑證


class SyncMode(Enum):
    SNAPSHOT_FAST = "snapshot_fast"  # 預設：毫秒級秒回上一版已提交快照
    WAIT_SYNC = "wait_sync"          # --sync：等待背景單寫者追平後再讀取


class OutputMode(Enum):
    HUMAN = "human"
    JSON = "json"


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    sync_mode: SyncMode = SyncMode.SNAPSHOT_FAST
    output_mode: OutputMode = OutputMode.HUMAN
    timeout_ms: Optional[int] = None
    allow_gated: bool = False
    verbose: bool = False


@dataclass(frozen=True, slots=True)
class InvocationEnvelope:
    """跨 CLI、RPC 與子進程完全通用的標準指令調用封套。"""
    task_id: TaskId
    target_module: ModuleId
    command_path: tuple[str, ...]
    raw_payload: Mapping[str, Any]
    caller_cwd: HostPath
    policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)


@dataclass(frozen=True, slots=True)
class SyncStatusMeta:
    """附帶於每次查詢結果的一致性狀態元數據（落實 DR-03 秒回提示）。"""
    committed_gen: SnapshotGen
    is_background_syncing: bool
    pending_diff_count: int = 0
    hint: Optional[str] = None


@dataclass(frozen=True, slots=True)
class StageMetrics:
    """細粒度階段耗時遙測（取代舊版全域 cell_span）。"""
    route_ms: float = 0.0
    sync_wait_ms: float = 0.0
    load_di_ms: float = 0.0
    codec_ms: float = 0.0
    exec_ms: float = 0.0

    @property
    def total_ms(self) -> float:
        return self.route_ms + self.sync_wait_ms + self.load_di_ms + self.codec_ms + self.exec_ms


@dataclass(frozen=True, slots=True)
class ExecutionOutcome(Generic[TResp]):
    """core.runtime 對外回傳之唯一確定性結果封套（永不向調用端拋出未封裝業務異常）。"""
    task_id: TaskId
    ok: bool
    exit_code: int
    data: Optional[TResp] = None
    error: Optional[ErrorDetail] = None
    sync_status: Optional[SyncStatusMeta] = None
    metrics: StageMetrics = field(default_factory=StageMetrics)
```

### 4.2 顯式請求上下文、取消令牌與進度流（`core/runtime/context.py`）

```python
from dataclasses import dataclass
from typing import Protocol
from core.primitives import HostPath, TaskId
from core.storage import SnapshotReadView, WriteUnitOfWork


class CancellationToken(Protocol):
    """唯讀協作式取消令牌：傳遞至業務迴圈、I/O 與資料庫查詢邊界。"""
    @property
    def is_cancelled(self) -> bool: ...
    @property
    def reason(self) -> str: ...
    def throw_if_cancelled(self) -> None: ...  # 若已取消立即拋出 TaskCancelledError


class ProgressReporter(Protocol):
    """結構化進度回報介面：自動轉發至 RPC 串流或終端 stderr 進度列，絕不污染 stdout。"""
    def report(self, phase: str, current: int, total: Optional[int] = None, message: str = "") -> None: ...


@dataclass(frozen=True, slots=True)
class CommandContext:
    """單次請求專屬之顯式不可變上下文（取代全域 RuntimeContext）。"""
    task_id: TaskId
    caller_cwd: HostPath
    cancellation: CancellationToken
    progress: ProgressReporter
    snapshot: SnapshotReadView  # 當前綁定之唯讀一致性快照視圖
```

### 4.3 模組依賴注入容器與受保護載入器（`core/runtime/container.py` & `loader.py`）

1. **`ProtectedModuleLoader`**：
   - 僅接受來自 `UriMountTable` 解析出的 `.modules/<module_id>/` 實體路徑，將模組掛載於受保護的獨立命名空間（`_yscb_v2_mod.<module_id>`），不向全域 `sys.path` 傾倒所有模組目錄，從根源阻斷跨模組私自 `import` 內部實作（強制跨模組互動走 `core.storage`、`core.event` 或 `core.contributes`）。
   - 記錄檔案 `(mtime_ns, size)` 指紋；若 `exec_module` 拋出異常，立即透過交易快照還原 `sys.modules`，防止殘留半初始化模組。
2. **`ModuleDeps[TConfig, TContrib]` 與 `ModuleContainer`**：
   - 每個業務模組定義一個繼承自 `YscbModule` 的聚合根類別，於首次調用時由 `ModuleContainer` 建構並顯式注入該模組專屬的受限能力物件（`ScopedVfs`、`ScopedModuleStorage`、`TypedConfigView[TConfig]`、`TypedContributesView[TContrib]`、`ScopedEventPublisher`、`StructuredLogger`）。
   - `ModuleContainer` 實作標準 Context Manager，於 Worker 重載或關閉時反向依序呼叫各模組的 `close()` 確定性釋放資源（確保 `0 ResourceWarning`）。

### 4.4 指令契約與執行宿主抽象（`core/runtime/engine.py` & `hosts.py`）

```python
from abc import ABC, abstractmethod
from typing import Generic, Protocol, Type
from core.primitives import EnvHash, ModuleId


class CommandHandler(ABC, Generic[TReq, TResp]):
    """下游業務模組實作單一指令之強型別基類。"""
    request_type: Type[TReq]
    response_type: Type[TResp]
    semantics: CommandSemantics = CommandSemantics.READ_SNAPSHOT
    security_tier: SecurityTier = SecurityTier.SAFE

    @abstractmethod
    def execute(self, req: TReq, ctx: CommandContext) -> TResp:
        """純業務執行入口：無須解析字串參數、無須管鎖、無須手動印出 JSON。"""
        raise NotImplementedError


class ExecutionHost(Protocol):
    """屏蔽本進程直跑與跨 .venv 子進程執行的統一宿主介面。"""
    def execute(self, envelope: InvocationEnvelope, cancel: CancellationToken) -> ExecutionOutcome[Any]: ...


class InProcessRuntimeHost:
    """於當前進程內執行 Stage 4 ~ Stage 7（供 Tier 0 主進程與已啟動之 Tier 1 Worker 子進程使用）。"""
    ...


class OneShotVenvHost:
    """供無 Daemon 冷啟動時呼叫 Tier 1 模組使用：以 .venv/<group>_<hash>/python 單次執行後乾淨回收。"""
    ...


class RuntimeEngine:
    """
    core.runtime 頂層編排門面：
    串聯 CommandRouter -> SecurityGate -> ExecutionHost (InProcess / IsolatedVenv) -> ExecutionOutcome。
    """
    def dispatch(
        self,
        envelope: InvocationEnvelope,
        cancellation: Optional[CancellationToken] = None,
    ) -> ExecutionOutcome[Any]: ...
```

## 5. 下游業務模組開發體驗對照 (`1.x` vs. `2.0`)

在 `Core 2.0` 的 `core.runtime` 託管下，下游模組撰寫一個查詢指令不再需要觸碰任何基礎設施細節：

```python
# 2.0 下游模組指令實作示意（100% 強型別業務邏輯，0 鎖、0 路徑字串切割、0 JSON print）
from dataclasses import dataclass
from typing import Optional
from core.primitives import SpaceId
from core.sdk import CommandContext, CommandHandler, CommandSemantics, SecurityTier


@dataclass(frozen=True, slots=True)
class SearchQueryReq:
    query: str
    space: Optional[SpaceId] = None
    limit: int = 20


@dataclass(frozen=True, slots=True)
class SearchHit:
    symbol_fqn: str
    score: float


@dataclass(frozen=True, slots=True)
class SearchQueryResp:
    hits: tuple[SearchHit, ...]
    total_matched: int


class SearchCommandHandler(CommandHandler[SearchQueryReq, SearchQueryResp]):
    request_type = SearchQueryReq
    response_type = SearchQueryResp
    semantics = CommandSemantics.READ_SNAPSHOT
    security_tier = SecurityTier.SAFE

    def __init__(self, search_service: "KnowledgeSearchService") -> None:
        self._service = search_service  # 由模組聚合根建構子顯式 DI 注入

    def execute(self, req: SearchQueryReq, ctx: CommandContext) -> SearchQueryResp:
        # ctx.snapshot 已由 core.runtime 按預設秒回或 --sync 綁定好唯讀一致性世代！
        return self._service.search(
            snapshot=ctx.snapshot,
            query=req.query,
            space=req.space,
            limit=req.limit,
            cancel=ctx.cancellation,
        )
```
> **對人類終端機輸出怎麼辦？** 每個模組可選配為 `SearchQueryResp` 註冊純無狀態的 `HumanPresenter(resp) -> str`（或使用內核預設表格/卡片渲染器）；當呼叫端指定 `--json` 或走 RPC 呼叫時，`core.cli / core.rpc` 直接透過 `DataclassCodec` 序列化 `SearchQueryResp`（連同 `SyncStatusMeta`），從架構根源保證雙軌輸出 100% 對齊且絕無雜訊混入。

## 6. 異常隔離與標準退出碼映射矩陣 (Fault Isolation & Exit Codes)

`RuntimeEngine.dispatch()` 捕獲所有執行期異常並正規化為 `ExecutionOutcome`，確保常駐 Worker 永不因單一指令錯誤而崩潰：

| 異常類別 / 情境 | `ErrorCode` | 標準 Exit Code | 處置行為與回傳保證 |
| :--- | :--- | :---: | :--- |
| 正常完成 | - | `0` | `ok=True`，攜帶強型別 `data: TResp` 與 `SyncStatusMeta`。 |
| 未知模組、未知子指令、參數 Schema 校驗失敗 | `INVALID_ARGUMENT` / `UNKNOWN_COMMAND` | `2` | 附帶 `Did-you-mean` 拼寫建議與用法指引（不觸發模組載入）。 |
| 未綁定 URI、唯讀空間違規、已知業務規則阻斷 | `DOMAIN_RULE_VIOLATION` / `URI_UNBOUND` | `1` | 保留結構化 `remediation` 自癒建議指令。 |
| 安全位階不足（未授權執行 `GATED` 指令） | `PERMISSION_DENIED` | `126` | 於 Stage 2 直接阻斷，保證零業務副作用。 |
| 模組宣告了指令但缺失對應 `CommandHandler` 綁定 | `HANDLER_NOT_FOUND` | `127` | 同時也會在靜態期被 `dev check 2.0` 對稱性檢查提前攔截。 |
| 使用者 `Ctrl+C`、RPC 斷線取消或超過 `timeout_ms` | `TASK_CANCELLED` / `DEADLINE_EXCEEDED` | `130` | `CancellationSource` 觸發信號，安全釋放快照讀取器後立即返回。 |
| 下游模組未捕獲之程式崩潰（`Exception`） | `UNHANDLED_MODULE_ERROR` | `1` | 記錄隔離 Traceback 至結構化日誌，保護常駐進程不退出。 |

## 7. Wave 1 實作驗收測試矩陣 (Verification Gate)

1. **三態執行同構測試**：同一組測試模組指令分別透過 `InProcessRuntimeHost`（冷啟動 Tier 0）、`OneShotVenvHost`（冷啟動 Tier 1）與常駐 Worker 執行，斷言輸出的 `ExecutionOutcome` 100% 結構與語意等價。
2. **`SNAPSHOT_FAST` vs `WAIT_SYNC` 並發測試**：模擬背景單寫者正在慢速寫入新世代時，驗證預設查詢 `<5ms` 零阻塞秒回上一版世代且 `is_background_syncing=True`；帶 `WAIT_SYNC` 時精確等待新世代提交後讀出新資料。
3. **Stdout 污染鐵壁測試**：在業務模組內故意呼叫底層 `print("noise")` 或 C 擴充輸出，驗證 `StreamGuard` 完整攔截，最終 `--json` 輸出仍可 100% 通過 `json.loads()`。
4. **半初始化崩潰回滾測試**：模擬模組頂層匯入拋出異常，驗證 `ProtectedModuleLoader` 將 `sys.modules` 100% 還原無殘留。
5. **跨模組私自 `import` 物理阻斷測試**：驗證模組 A 未經允許直接 `import module_b` 時立即拋出 `ModuleNotFoundError`，強制遵守解耦邊界。
6. **取消信號即時穿透測試**：模擬長耗時處理中途觸發 `CancellationSource.cancel()` 與 Timeout，驗證業務沙盒於毫秒內拋出 `TaskCancelledError` 並回傳 Exit Code `130` 且 `0 ResourceWarning`。
