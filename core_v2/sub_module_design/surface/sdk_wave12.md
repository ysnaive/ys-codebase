# 子模組架構設計規格：`core.surface.sdk`（Wave 1.2 統一對外公開契約擴充設計書）

> **所屬功能域**：`Domain 6 — 對外門面域 (surface/)`
> **模組路徑**：`core_v2/source/core/core/surface/sdk/`（擴充既有 `declarative.py`、`client.py`、`__init__.py`）
> **依賴上限（Allowed Imports）**：`Domain 1 ~ 5`（`foundation/*`、`filesystem/{vfs, space, storage}`、`metadata/{config, contributes}`、`execution.{event, lifecycle, rpc, runtime}`）
> **禁止反向依賴（Forbidden Imports）**：`execution.daemon`、`packaging/*`（且所有下層域嚴禁反向匯入 `surface/*`）
> **狀態**：`Draft — Design Frozen for Wave 1.2 Implementation`（實作完成並接入 Gate 0 後併入 Active Living Spec [sdk.md](./sdk.md)）

> [!IMPORTANT]
> **全內核唯一強制統一之對外契約（Mandatory External SDK Contract）**：
> Wave 1.2 其餘內部域（`filesystem`、`metadata`、`packaging`、`cli`）允許遠端實作端依實務微調內部 API；但本文件與 [sdk.md](./sdk.md) 定義之 **`core.surface.sdk` 對外符號名稱、簽名語意、裝飾器契約、`ModuleEnv` 與 `TaskContext` 注入介面**屬全生態系（Wave 2 / Wave 3 全部業務模組）唯一匯入邊界，**必須嚴格統一不可擅改**。

---

## 1. 擴充定位與向後相容保證

1. **100% 保留 Wave 1.1 既有 25 符號**：[sdk.md](./sdk.md) 已落地之 25 個公開符號名稱、參數與行為維持完全相容；既有 `InMemoryModule` 單元測試在不提供完整宿主 VFS/Config 服務時自動以安全預設（`MemoryVfsProvider` + 無副作用 Logger + 空 Locale）運作，零破壞既有測試。
2. **單一匯入入口原則**：Wave 2 / Wave 3 業務模組僅需 `from core.surface.sdk import ...` 即可取得一切合法內核契約（同時保留直接匯入 `core.foundation.{primitives, errors}` 之合法性）。
3. **資源自動 LIFO 防洩漏**：模組透過 `ModuleEnv.open_database(...)` 與 `ModuleEnv.open_blob_vault(...)` 開啟持久化儲存時，SDK 強制將落點限定於 `storage.local://@/` 並自動註冊 `db.close` 至 `env.register_closer(...)`，確保重載與停機階段嚴格逆序釋放、零 `ResourceWarning`、零 Windows 檔案句柄鎖死。

---

## 2. `Module` 宣告擴充、`@on_migrate` 與 `SecurityTier.CRITICAL`

### 2.1 `Module` 類別宣告與裝飾器擴充
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, ClassVar, Optional, Sequence, TypeVar

from core.execution.runtime import ConcurrencyMode, DispatchMode, SecurityTier, TaskContext
from core.filesystem.storage import BlobVault, ModuleDatabase, SchemaMigration, StorageOpenOptions
from core.filesystem.vfs import ScopedVfs
from core.foundation.observability import LocaleCatalog, StructuredLogger
from core.foundation.primitives import HostPath, ModuleId, SemVer4
from core.metadata.contributes import AggregatedContributes, ExtensionPointSpec

TConfig = TypeVar("TConfig")
_TFn = TypeVar("_TFn", bound=Callable[..., object])


@dataclass(frozen=True, slots=True)
class Option:
    """Wave 1.2 擴充：新增 group 供 1.x 正交互斥選項分組與 HelpRenderer 分區渲染。"""
    short: Optional[str] = None
    summary: str = ""
    long_name: Optional[str] = None
    group: Optional[str] = None  # 同 group 之選項於 CLI 層互斥並於 -h 分組呈現


@dataclass(frozen=True, slots=True)
class MigrationRequest:
    """模組跨版本資料遷移任務輸入 DTO（由上層 install/update 系統 Task 派發）。"""
    old_version: SemVer4
    new_version: SemVer4


def task(
    cli: Optional[str | tuple[str, ...]] = None,
    *,
    name: Optional[str] = None,
    summary: str = "",
    aliases: tuple[str, ...] = (),
    usage_pros: tuple[str, ...] = (),  # 1.x RECOMMENDED USAGE (Pros) 承襲
    usage_cons: tuple[str, ...] = (),  # 1.x RESTRICTIONS & GATES (Cons) 承襲
    dispatch_mode: DispatchMode = DispatchMode.HYBRID,
    interactive_tty: bool = False,
    security: SecurityTier = SecurityTier.SAFE,
    lock: Optional[str] = None,
    concurrency: Optional[ConcurrencyMode] = None,
    timeout_ms: Optional[int] = None,
) -> Callable[[_TFn], _TFn]: ...


def on_migrate() -> Callable[[_TFn], _TFn]:
    """標註模組跨版資料遷移處理方法 (self, req: MigrationRequest, ctx: TaskContext) -> None。
    由 _DeclarativeMeta 編譯為 TaskExposure.INTERNAL_TRIGGER 內部任務（每模組最多 1 支）。"""
    ...


class Module:
    """Wave 1.2 擴充後之宣告式模組基類。"""
    id: ClassVar[str] = ""
    aliases: ClassVar[tuple[str, ...]] = ()
    description: ClassVar[str] = ""
    groups: ClassVar[tuple[type[TaskGroup], ...]] = ()
    config_type: ClassVar[Optional[type[object]]] = None
    extension_points: ClassVar[tuple[ExtensionPointSpec[object], ...]] = ()

    def on_init(self, env: ModuleEnv) -> None: ...
    def on_warmup(self, env: ModuleEnv) -> None: ...
    def on_close(self) -> None: ...
    def to_yscb_module(self) -> YscbModule: ...
```

### 2.2 類別定義期靜態校驗追加規則（`_DeclarativeMeta`）
1. `config_type` 若非 `None`，必須為 `@dataclass(frozen=True, slots=True)` 且所有欄位通過 `DataclassCodec` 嚴格無 `Any` 檢核。
2. `extension_points` 內所有 `ExtensionPointSpec.name` 必須互異且各自 `payload_type` 為合法不可變型別。
3. 同一 `Module` 最多宣告 1 個 `@on_migrate` 方法；其輸入註解必須精準為 `MigrationRequest`、回傳為 `None`（正規化為 `Empty`），禁止疊加 `@task` / `@on_event` / `@periodic`。
4. `SecurityTier.CRITICAL` 與 `SecurityTier.GATED` 同享事件／排程禁止規則（嚴禁綁定 `@on_event` 或 `@periodic`）。
5. 靜態任務分級鐵律：**1 Task = 1 固定 `SecurityTier`**，不支援單一選項動態改變安全等級。


---

## 3. 能力注入接縫：`ModuleEnv` 與 `TaskContext`（Wave 1.2 統一契約）

```python
class ModuleEnv:
    """傳入 Module / TaskGroup 之 on_init(env) 與 on_warmup(env) 的模組生命週期環境。"""
    @property
    def module_id(self) -> ModuleId: ...
    @property
    def workspace_root(self) -> HostPath: ...
    @property
    def vfs(self) -> ScopedVfs: ...
    @property
    def logger(self) -> StructuredLogger: ...
    @property
    def locale(self) -> LocaleCatalog: ...

    def register_closer(self, fn: Callable[[], None]) -> None: ...
    def load_config(self, config_cls: type[TConfig]) -> TConfig: ...
    def load_contributes(self) -> AggregatedContributes: ...
    def open_database(
        self,
        name: str,
        *,
        migrations: Sequence[SchemaMigration] = (),
        options: StorageOpenOptions = StorageOpenOptions(),
    ) -> ModuleDatabase: ...
    def open_blob_vault(self, name: str) -> BlobVault: ...
```

### `TaskContext` Wave 1.2 追加唯讀能力存取（加於 `execution.runtime.TaskContext` 並由 `surface.sdk` Re-export）
在既有 10 項方法／屬性（`workspace_root`, `caller_cwd`, `caller_env`, `cancel_token`, `effective_priority`, `emit`, `emit_imm`, `invoke_task`, `invoke_typed`, `report_progress`）基礎上，追加 5 項受管服務入口：

```python
class TaskContext(ABC):
    # ... 保留 Wave 1.1 既有 10 項抽象方法與屬性 100% 不變 ...
    @property
    @abstractmethod
    def vfs(self) -> ScopedVfs: ...
    @property
    @abstractmethod
    def logger(self) -> StructuredLogger: ...
    @property
    @abstractmethod
    def locale(self) -> LocaleCatalog: ...
    @abstractmethod
    def load_config(self, config_cls: type[TConfig]) -> TConfig: ...
    @abstractmethod
    def load_contributes(self) -> AggregatedContributes: ...
```

### 跨 Tier 能力行為與 `space` 互動規則
1. **Tier 0 與 Tier 1 行為 100% 同構**：`ScopedVfs`、`ModuleDatabase`（SQLite WAL）、`BlobVault`、`StructuredLogger`、`LocaleCatalog`、`load_config`、`load_contributes` 皆為純標準庫實作，Tier 1 Worker 子進程內直接可用；`open_database(name)` 強制映射為 `storage.local://@/<name>.db` 並自動 `register_closer(db.close)`。
2. **空間異動統一走系統 `Task`**：下游模組若需註冊／清除動態空間（如 `agents-workflow/gitignore`、`agents-workflow/readonly`）或主動觸發掃描，一律經 `ctx.invoke_typed` 呼叫內核系統任務（`core.space.set_dynamic`、`core.space.clear_dynamic`、`core.space.scan`），確保單點 `resource_key` 互斥、事件廣播與 Daemon 監視同步。
3. **Wave 1.1 `InMemoryModule` 測試相容**：未注入完整宿主 `ModuleRuntimeServices` 時，預設提供基於 `MemoryVfsProvider` 之隔離 `ScopedVfs`、無副作用 `NullLogger` 與空 `LocaleCatalog`。

---

## 4. `core.surface.sdk.__all__` 完整對外公開清冊（單一匯入邊界）

| 分組 | 匯出符號（必須 100% 統一對齊） |
| :--- | :--- |
| **既有 Wave 1.1 宣告與執行契約（25 個）** | `Arg`, `CancellationToken`, `ConcurrencyMode`, `DispatchMode`, `Empty`, `EventMetadata`, `ExitCodeProvider`, `HostPath`, `HumanRenderable`, `InMemoryModule`, `Module`, `ModuleEnv`, `Option`, `ProgressEvent`, `SecurityTier`, `TaskContext`, `TaskGroup`, `TaskOutcome`, `YscbClient`, `YscbModule`, `define_event`, `format_output`, `on_event`, `periodic`, `task` |
| **Foundation 值物件、錯誤與可觀測（16 個）** | `ModuleId`, `TaskId`, `EventId`, `SemVer4`, `VersionConstraint`, `SemanticUri`, `SpaceId`, `SpacePath`, `SnapshotGen`, `YscbError`, `ErrorCode`, `ErrorDetail`, `TaskCancelledException`, `LogLevel`, `StructuredLogger`, `LocaleCatalog` |
| **VFS 與持久化儲存（9 個）** | `ScopedVfs`, `VfsCapabilities`, `VfsStat`, `ModuleDatabase`, `SnapshotReader`, `WriteTransaction`, `SchemaMigration`, `StorageOpenOptions`, `BlobVault` |
| **邏輯空間、擴充與遷移（11 個）** | `SpaceSpec`, `HashPolicy`, `SpaceFileEntry`, `SpaceDiffBatch`, `MergeStrategy`, `ContribField`, `ExtensionPointSpec`, `AggregatedContributes`, `ProvenanceGraph`, `MigrationRequest`, `on_migrate` |

---

## 5. 對既有 Wave 1.1 `execution.runtime` 的最小增量改動（Runtime Delta）

為銜接 Wave 1.2，既有已穩定的 `execution/runtime` 僅需 **4 處精準微幅增量**（不更動任何 5 階段管線與 `COALESCE`/`QUIESCE` 核心模型）：
1. `contracts.py`：`WORKER_AUTH_ENV_KEY` 更名為 `"_YSCB_WORKER_AUTH_TOKEN"`；`SecurityTier` 新增 `CRITICAL = "critical"`；`CliBindingSpec` 補上 `usage_pros` / `usage_cons`。
2. `gates.py`：`check_exposure_and_security_gates` 對 `SecurityTier.CRITICAL` 除要求 `approval_scope` 外，額外阻斷任何非頂層前景或背景／事件鏈呼叫（與 `surface.cli` 4×3 矩陣雙層設防）。
3. `module_slot.py` & `dispatcher.py`：`DispatcherHostOptions` 增設選配 `module_services_factory`（與 Worker 端對稱初始化），將模組專屬 `vfs`/`logger`/`locale`/`config`/`contributes` 注入 `ModuleEnv` 與 `TaskContext`。
4. `test_gate0.py`：待 Wave 1.2 實作完成時，將 `core.surface.sdk` 之允許依賴調整為對齊 [ROADMAP.md](../../ROADMAP.md) §3.1（放行 `filesystem/{vfs,space,storage}` 與 `metadata`，維持禁止 `execution.daemon` 與 `packaging`）。

---

## 6. 必測驗收門檻 (Verification Gate)

1. **Wave 1.1 零回歸**：既有 `test_surface_sdk.py` 與 `RC-01 ~ RC-08` 全數不改測試即 100% 通過。
2. **LIFO 自動關閉保證**：模組於 `on_init` 透過 `env.open_database("test")` 開庫後未手動 `close()`，於模組卸載／`YscbClient.close()` 後驗證連線已關閉、Windows 可立即刪除目錄且 `0 ResourceWarning`。
3. **跨 Tier 服務一致性**：Tier 0 與 Tier 1 模組在 `@task` 內調用 `ctx.vfs`、`ctx.load_config`、`ctx.load_contributes`、`ctx.logger`、`ctx.locale` 及 `@on_migrate` 皆行為完全等價。
4. **單一匯入邊界驗證**：Gate 0 / `dev check` 驗證下游範例模組僅透過 `from core.surface.sdk import ...` 即可完整開發，無須匯入任何內部子模組。
