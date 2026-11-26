# 子模組架構設計規格：`core.surface.sdk`（零反射方案 B 宣告式門面與程式化客戶端）

> **所屬功能域**：`Domain 6 — 對外門面域 (surface/)`
> **模組路徑**：`core_v2/source/core/core/surface/sdk/`（`declarative.py`、`client.py`、`__init__.py`）
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.{vfs, space, storage}`、`metadata.{config, contributes}`、`execution.{event, lifecycle, rpc, runtime}`
> **禁止反向依賴（Forbidden Imports）**：`execution.daemon`、`packaging/*`、`surface.{cli, bootstrap}`（所有下層域亦嚴禁反向匯入 `surface/*`）
> **狀態**：`Active Living Spec — Two-Tier Primary 52-Symbol Zero-Reflection SDK Facade`

## 1. 模組定位與架構邊界 (Positioning & Layering Overview)

`core.surface.sdk` 為下游業務模組（如 `knowledge-db`、`agents-workflow`、`ast`、`vscode-support`、`gdrive-support`）提供**精簡高信噪比之主公開入口（精準鎖定 52 個高頻核心符號）**；外部客戶端（`YscbClient`）、記憶體治具（`InMemoryModule`）、CLI 呈現輔助（`format_output`）、底層剖析與儲存轉接契約則分流至二層子套件 [`core.surface.sdk.advanced`](./sdk_advanced.md)（38 個符號，兩層交集為空）：

- **宣告式 DSL (`declarative.py`)**：透過內部零反射 Metaclass（`_DeclarativeMeta(ABCMeta)`）於類別定義期掃描 `Module`（含 `aliases`、`description`、`config_type`、`extension_points`）與協變泛型 `TaskGroup[TModule_co]`（公開 `parent_module -> Optional[TModule_co]` 與非空 `module -> TModule_co`）內之 `@task`（含 `equivalence_fn`）、`@on_event`、`@periodic`、`@on_migrate` 方法並編譯為強型別 `TaskMetadata` 與 `YscbModule` 轉接器；`ProtectedModuleLoader` 於未宣告 `create_module()` 時亦支援自動偵測 `module_entry.py` 內唯一具象 `Module` 子類。
- **零反射疊加描述符與一等業務能力**：裝飾器疊加封裝於不可變描述符（`_DecoratedMethod`）；結合 Domain 5 匯出之 `SpaceClient`（`ctx.spaces`）、`TaskRef[TIn, TOut]`（`ctx.call(ref, req)`）、`ProcessResult`（`ctx.run_process(...)`）與 6 組強型別系統事件常數，免除下游模組重複造輪。
- **跨 Tier 同構能力注入與 LIFO 資源自動關閉 (`ModuleEnv` / `TaskContext`)**：將 `Module` 與靜態掛載 `TaskGroup` 的 `on_init` / `on_warmup` / `on_close`、`env.register_closer(...)`、`env.open_database(...)` 與 `env.open_blob_vault(...)` 橋接至 `LifoResourceStack`，確保重載與停機階段嚴格逆序（LIFO）釋放、零 `ResourceWarning` 與零 Windows 檔案句柄鎖死。

## 2. 公開契約與門面簽名（1:1 Parity）

```python
from dataclasses import dataclass
from typing import Callable, ClassVar, Generic, Mapping, Optional, Protocol, Sequence, TypeVar, runtime_checkable
from core.execution.event import EventMetadata
from core.execution.runtime import (
    CONFIG_CHANGED_EVENT,
    MODULE_INSTALLED_EVENT,
    MODULE_REMOVING_EVENT,
    SPACE_REGISTRY_CHANGED_EVENT,
    SPACE_UPDATED_EVENT,
    WORKSPACE_RELOADED_EVENT,
    ConcurrencyMode,
    ConfigChangedEventPayload,
    DispatchMode,
    Empty,
    ModuleLifecycleEventPayload,
    ProcessResult,
    SecurityTier,
    SpaceClient,
    SpaceUpdatedEventPayload,
    TaskContext,
    TaskOutcome,
    TaskRef,
    YscbModule,
)
from core.filesystem.space import SpaceDiffBatch, SpaceFileEntry, SpaceSpec, SpaceStatusSnapshot
from core.filesystem.storage import BlobVault, ModuleDatabase, SchemaMigration, StorageOpenOptions
from core.filesystem.vfs import ScopedVfs
from core.foundation import (
    CancellationToken,
    ErrorCode,
    EventId,
    HostPath,
    JsonPrimitive,
    LocaleCatalog,
    ModuleId,
    Profiler,
    ProgressEvent,
    SemVer4,
    SemanticUri,
    SpaceId,
    SpacePath,
    StructuredLogger,
    TaskCancelledException,
    YscbError,
)
from core.metadata.contributes import AggregatedContributes, ContribField, ExtensionPointSpec, MergeStrategy

TIn = TypeVar("TIn")
TPayload = TypeVar("TPayload")
TConfig = TypeVar("TConfig")
TModule_co = TypeVar("TModule_co", bound="Module", covariant=True)
_TFn = TypeVar("_TFn", bound=Callable[..., object])


@dataclass(frozen=True, slots=True)
class Arg:
    summary: str = ""
    name: Optional[str] = None


@dataclass(frozen=True, slots=True)
class Option:
    short: Optional[str] = None
    summary: str = ""
    long_name: Optional[str] = None
    group: Optional[str] = None


@dataclass(frozen=True, slots=True)
class MigrationRequest:
    old_version: SemVer4
    new_version: SemVer4


@runtime_checkable
class HumanRenderable(Protocol):
    def render_text(self) -> str: ...


@runtime_checkable
class ExitCodeProvider(Protocol):
    def exit_code(self) -> int: ...


class ModuleEnv:
    def __init__(self, workspace_root: HostPath) -> None: ...
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
    @property
    def profiler(self) -> Profiler: ...
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


def define_event(
    event_id: str,
    payload_type: type[TPayload] = Empty,
    *,
    ordered: bool = False,
    description: str = "",
) -> EventMetadata[TPayload]: ...


class TaskGroup(Generic[TModule_co]):
    @property
    def parent_module(self) -> Optional[TModule_co]: ...
    @property
    def module(self) -> TModule_co: ...
    def on_init(self, env: ModuleEnv) -> None: ...
    def on_warmup(self, env: ModuleEnv) -> None: ...
    def on_close(self) -> None: ...


class Module:
    id: ClassVar[str] = ""
    aliases: ClassVar[tuple[str, ...]] = ()
    description: ClassVar[str] = ""
    groups: ClassVar[tuple[type[TaskGroup[Module]], ...]] = ()
    config_type: ClassVar[Optional[type[object]]] = None
    extension_points: ClassVar[tuple[ExtensionPointSpec[object], ...]] = ()

    def on_init(self, env: ModuleEnv) -> None: ...
    def on_warmup(self, env: ModuleEnv) -> None: ...
    def on_close(self) -> None: ...
    def to_yscb_module(self) -> YscbModule: ...


def task(
    cli: Optional[str | tuple[str, ...]] = None,
    *,
    name: Optional[str] = None,
    summary: str = "",
    aliases: tuple[str, ...] = (),
    usage_pros: tuple[str, ...] = (),
    usage_cons: tuple[str, ...] = (),
    dispatch_mode: DispatchMode = DispatchMode.HYBRID,
    interactive_tty: bool = False,
    security: SecurityTier = SecurityTier.SAFE,
    lock: Optional[str] = None,
    concurrency: Optional[ConcurrencyMode] = None,
    equivalence_fn: Optional[Callable[[TIn], str]] = None,
    timeout_ms: Optional[int] = None,
) -> Callable[[_TFn], _TFn]: ...


def on_migrate() -> Callable[[_TFn], _TFn]: ...


def on_event(
    event: EventMetadata[TPayload] | EventId | str,
    *,
    payload_filter: Optional[Mapping[str, Sequence[JsonPrimitive]]] = None,
    mapper: Optional[Callable[[Sequence[TPayload]], Optional[TIn]]] = None,
) -> Callable[[_TFn], _TFn]: ...


def periodic(
    interval_sec: float,
    *,
    enabled_config_key: Optional[str] = None,
    interval_config_key: Optional[str] = None,
) -> Callable[[_TFn], _TFn]: ...


__all__: tuple[str, ...] = (
    "Arg",
    "BlobVault",
    "CONFIG_CHANGED_EVENT",
    "CancellationToken",
    "ConcurrencyMode",
    "ConfigChangedEventPayload",
    "ContribField",
    "DispatchMode",
    "Empty",
    "ErrorCode",
    "EventMetadata",
    "ExitCodeProvider",
    "ExtensionPointSpec",
    "HostPath",
    "HumanRenderable",
    "MODULE_INSTALLED_EVENT",
    "MODULE_REMOVING_EVENT",
    "MergeStrategy",
    "MigrationRequest",
    "Module",
    "ModuleDatabase",
    "ModuleEnv",
    "ModuleLifecycleEventPayload",
    "Option",
    "ProcessResult",
    "ProgressEvent",
    "SPACE_REGISTRY_CHANGED_EVENT",
    "SPACE_UPDATED_EVENT",
    "SchemaMigration",
    "ScopedVfs",
    "SecurityTier",
    "SemanticUri",
    "SpaceClient",
    "SpaceDiffBatch",
    "SpaceFileEntry",
    "SpaceId",
    "SpacePath",
    "SpaceSpec",
    "SpaceStatusSnapshot",
    "SpaceUpdatedEventPayload",
    "TaskCancelledException",
    "TaskContext",
    "TaskGroup",
    "TaskOutcome",
    "TaskRef",
    "WORKSPACE_RELOADED_EVENT",
    "YscbError",
    "define_event",
    "on_event",
    "on_migrate",
    "periodic",
    "task",
)
```

## 3. 宣告式編譯與生命週期規則

1. **類別定義期驗證（`ABCMeta.__new__`）**：
   - 具體 `Module` 子類必須宣告非空且合法之 `ModuleId`（`id`）；`Module` 本身與抽象 `ABC` 中間基類可省略 `id`。
   - `Module.groups` 必須皆為互異之具體 `TaskGroup` 子類（禁止重複或抽象基類）；`config_type` 若非 `None` 必須為 `@dataclass(frozen=True, slots=True)` 且無 `Any`；`extension_points` 必須通過 `compile_extension_points` 不可變型別檢核。
   - 同一 `Module` 最多宣告 1 個 `@on_migrate` 方法，簽名必須為 `(self, req: MigrationRequest, ctx: TaskContext) -> None`，編譯為 `TaskId(f"{id}.yscb_on_migrate")`（`TaskExposure.INTERNAL_TRIGGER`），禁止疊加 `@task`/`@on_event`/`@periodic`。
   - `SecurityTier.GATED`、`SecurityTier.CRITICAL` 與 `DispatchMode.COLD_ONLY` 任務嚴禁綁定 `@on_event` 或 `@periodic`。
2. **LIFO 資源卸載隔離**：
   - `ModuleEnv.open_database(name)` 強制落點於 `storage.local://@/<name>.db` 並自動 `register_closer(db.close)`；卸載時嚴格逆序（LIFO）執行 `env.register_closer(...)`、`group.on_close()` 與 `module.on_close()`。


## 4. 主入口 52 符號分組總表（進階 38 符號見 `sdk_advanced.md`）

| 分組 | 匯出符號（共 52 個） |
| :--- | :--- |
| **宣告式 DSL 與 CLI（14 個）** | `Arg`, `Empty`, `ExitCodeProvider`, `HumanRenderable`, `MigrationRequest`, `Module`, `ModuleEnv`, `Option`, `TaskGroup`, `define_event`, `on_event`, `on_migrate`, `periodic`, `task` |
| **執行、跨模組與受管子行程（10 個）** | `CancellationToken`, `ConcurrencyMode`, `DispatchMode`, `EventMetadata`, `ProcessResult`, `SecurityTier`, `SpaceClient`, `TaskContext`, `TaskOutcome`, `TaskRef` |
| **強型別系統事件與 Payload（9 個）** | `CONFIG_CHANGED_EVENT`, `MODULE_INSTALLED_EVENT`, `MODULE_REMOVING_EVENT`, `SPACE_REGISTRY_CHANGED_EVENT`, `SPACE_UPDATED_EVENT`, `WORKSPACE_RELOADED_EVENT`, `ConfigChangedEventPayload`, `ModuleLifecycleEventPayload`, `SpaceUpdatedEventPayload` |
| **VFS、儲存與邏輯空間模型（10 個）** | `BlobVault`, `ModuleDatabase`, `SchemaMigration`, `ScopedVfs`, `SpaceDiffBatch`, `SpaceFileEntry`, `SpaceId`, `SpacePath`, `SpaceSpec`, `SpaceStatusSnapshot` |
| **錯誤、進度、擴充與路徑（9 個）** | `ContribField`, `ErrorCode`, `ExtensionPointSpec`, `HostPath`, `MergeStrategy`, `ProgressEvent`, `SemanticUri`, `TaskCancelledException`, `YscbError` |
