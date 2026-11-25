# 子模組架構設計規格：`core.surface.sdk`（零反射方案 B 宣告式門面與程式化客戶端）

> **所屬功能域**：`Domain 6 — 對外門面域 (surface/)`
> **模組路徑**：`core_v2/source/core/core/surface/sdk/`（`declarative.py`、`client.py`、`__init__.py`）
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.{vfs, space, storage}`、`metadata.{config, contributes}`、`execution.{event, lifecycle, rpc, runtime}`
> **禁止反向依賴（Forbidden Imports）**：`execution.daemon`、`packaging/*`、`surface.{cli, bootstrap}`（所有下層域亦嚴禁反向匯入 `surface/*`）
> **狀態**：`Active Living Spec — Scheme B 75-Symbol Zero-Reflection Unified SDK Facade`

## 1. 模組定位與架構邊界 (Positioning & Layering Overview)

`core.surface.sdk` 為下游業務模組與程式化調用端提供**全生態系唯一公開匯入門面（精準鎖定 75 個完全自洽核心符號）**，在零全域單例與零執行期反射的前提下統一封裝 `Domain 1 ~ 5` 能力（`foundation`、`filesystem.{vfs, storage, space}`、`metadata.{config, contributes}`、`execution.{event, lifecycle, runtime, rpc}`）：

- **宣告式 DSL (`declarative.py`)**：透過內部零反射 Metaclass（`_DeclarativeMeta(ABCMeta)`）於類別定義期掃描 `Module`（含 `aliases`、`description`、`config_type`、`extension_points`）與靜態 `TaskGroup` 內之 `@task`、`@on_event`、`@periodic`、`@on_migrate` 方法並編譯為強型別 `TaskMetadata` 與 `YscbModule` 轉接器；`Module.to_yscb_module()` 透過內部 `WeakKeyDictionary` 將每個 `TaskGroup` 實例綁定至父 `Module` 並公開 `TaskGroup.parent_module` 唯讀屬性以供狀態共享；凡遇非法型別註解、非 `@dataclass(frozen=True, slots=True)` 組態類別、重複擴充點或 CLI 路徑、或 `GATED`/`CRITICAL`/`COLD_ONLY` 綁定事件/排程等違規，於類別定義期即確定性拋出 `ValueError`。
- **零反射疊加描述符**：裝飾器疊加封裝於不可變可呼叫描述符（`_DecoratedMethod`），全程零 `.__dict__` / `setattr` / `hasattr` / `getattr`，保持實體與未綁定方法直接可呼叫且與裝飾器上下疊加順序無關。
- **跨 Tier 同構能力注入與 LIFO 資源自動關閉 (`ModuleEnv` / `TaskContext`)**：將 `Module` 與靜態掛載 `TaskGroup` 的 `on_init` / `on_warmup` / `on_close`、`env.register_closer(...)`、`env.open_database(...)`（強制落點 `storage.local://@/<name>.db` 並自動註冊 `db.close`）與 `env.open_blob_vault(...)` 橋接至 `LifoResourceStack`，確保重載與停機階段嚴格逆序（LIFO）釋放、零 `ResourceWarning` 與零 Windows 檔案句柄鎖死。
- **測試治具 (`InMemoryModule`) 與程式化客戶端 (`YscbClient`)**：未注入完整宿主服務時自動回退至基於 `MemoryVfsProvider` 之無副作用預設服務，100% 相容既有單測。

## 2. 公開契約與門面簽名（1:1 Parity）

```python
from dataclasses import dataclass
from typing import Callable, ClassVar, Final, Mapping, Optional, Protocol, Sequence, TypeVar, overload, runtime_checkable
from core.execution.event import EventMetadata
from core.execution.runtime import (
    CONFIG_CHANGED_EVENT_ID,
    MODULE_INSTALLED_EVENT_ID,
    MODULE_REMOVING_EVENT_ID,
    WORKSPACE_RELOADED_EVENT_ID,
    ClientRoutingPolicy,
    ConcurrencyMode,
    DispatchMode,
    ExecutionPriority,
    SecurityTier,
    TaskContext,
    TaskMetadata,
    TaskOutcome,
    YscbModule,
)
from core.filesystem.space import HashPolicy, SpaceDiffBatch, SpaceFileEntry, SpaceSpec
from core.filesystem.storage import (
    BlobVault,
    ModuleDatabase,
    SchemaMigration,
    SnapshotReader,
    StorageOpenOptions,
    WriteTransaction,
)
from core.filesystem.vfs import ScopedVfs, VfsCapabilities, VfsStat
from core.foundation import (
    CancellationToken,
    ErrorCode,
    ErrorDetail,
    EventId,
    HostPath,
    JsonPrimitive,
    JsonValue,
    LocaleCatalog,
    LogLevel,
    ModuleId,
    ProgressEvent,
    SemVer4,
    SemanticUri,
    SnapshotGen,
    SpaceId,
    SpacePath,
    StructuredLogger,
    TaskCancelledException,
    TaskId,
    VersionConstraint,
    YscbError,
)
from core.metadata.contributes import (
    AggregatedContributes,
    ContribField,
    ExtensionPointSpec,
    MergeStrategy,
    ProvenanceGraph,
)

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")
TPayload = TypeVar("TPayload")
TConfig = TypeVar("TConfig")
_TFn = TypeVar("_TFn", bound=Callable[..., object])

SPACE_UPDATED_EVENT_ID_STR: Final[str] = "core.space_updated"
SPACE_REGISTRY_CHANGED_EVENT_ID_STR: Final[str] = "core.space_registry_changed"


@dataclass(frozen=True, slots=True)
class Empty:
    pass


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


@dataclass(frozen=True, slots=True)
class SetDynamicSpaceInput:
    owner: ModuleId
    name: str
    spec: SpaceSpec


@dataclass(frozen=True, slots=True)
class ClearDynamicSpaceInput:
    owner: ModuleId
    name: Optional[str] = None


@dataclass(frozen=True, slots=True)
class SpaceScanInput:
    space_id: Optional[str] = None
    force: bool = False


@dataclass(frozen=True, slots=True)
class SpaceAckCursorInput:
    space: str
    consumer: str
    from_gen: int
    to_gen: int
    config_hash: str
    merkle_root: str


@runtime_checkable
class HumanRenderable(Protocol):
    def render_text(self) -> str: ...


@runtime_checkable
class ExitCodeProvider(Protocol):
    def exit_code(self) -> int: ...


def format_output(output: object) -> tuple[str, int]: ...


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


class TaskGroup:
    @property
    def parent_module(self) -> Optional[Module]: ...
    def on_init(self, env: ModuleEnv) -> None: ...
    def on_warmup(self, env: ModuleEnv) -> None: ...
    def on_close(self) -> None: ...


class Module:
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


class InMemoryModule:
    def __init__(self, module_id: str) -> None: ...
    def add_task(
        self,
        name: str,
        handler: Callable[..., object],
        *,
        summary: str = "",
        security: SecurityTier = SecurityTier.SAFE,
        lock: Optional[str] = None,
        concurrency: Optional[ConcurrencyMode] = None,
    ) -> "InMemoryModule": ...
    def to_yscb_module(self) -> YscbModule: ...


class YscbClient:
    def __init__(
        self,
        workspace_root: HostPath,
        *,
        modules: Sequence[Module | InMemoryModule] = (),
    ) -> None: ...

    @classmethod
    def local(
        cls,
        workspace_root: HostPath,
        *modules: Module | InMemoryModule,
    ) -> "YscbClient": ...

    @classmethod
    def connect(cls, workspace_root: HostPath) -> "YscbClient": ...

    @overload
    def call(
        self,
        task_id: TaskId | str,
        req: object = None,
        *,
        output_type: type[TOut],
        cwd: Optional[HostPath] = None,
        env: Optional[Mapping[str, str]] = None,
        force_cold: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        approval_scope: frozenset[TaskId] = frozenset(),
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def call(
        self,
        task_id: TaskId | str,
        req: object = None,
        *,
        output_type: None = None,
        cwd: Optional[HostPath] = None,
        env: Optional[Mapping[str, str]] = None,
        force_cold: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        approval_scope: frozenset[TaskId] = frozenset(),
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> TaskOutcome[JsonValue]: ...

    def call(
        self,
        task_id: TaskId | str,
        req: object = None,
        *,
        output_type: Optional[type[TOut]] = None,
        cwd: Optional[HostPath] = None,
        env: Optional[Mapping[str, str]] = None,
        force_cold: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        approval_scope: frozenset[TaskId] = frozenset(),
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]: ...

    def close(self) -> None: ...
    def __enter__(self) -> "YscbClient": ...
    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None: ...


__all__: tuple[str, ...] = (
    "AggregatedContributes",
    "Arg",
    "BlobVault",
    "CONFIG_CHANGED_EVENT_ID",
    "CancellationToken",
    "ClearDynamicSpaceInput",
    "ClientRoutingPolicy",
    "ConcurrencyMode",
    "ContribField",
    "DispatchMode",
    "Empty",
    "ErrorCode",
    "ErrorDetail",
    "EventId",
    "EventMetadata",
    "ExecutionPriority",
    "ExitCodeProvider",
    "ExtensionPointSpec",
    "HashPolicy",
    "HostPath",
    "HumanRenderable",
    "InMemoryModule",
    "JsonValue",
    "LocaleCatalog",
    "LogLevel",
    "MODULE_INSTALLED_EVENT_ID",
    "MODULE_REMOVING_EVENT_ID",
    "MergeStrategy",
    "MigrationRequest",
    "Module",
    "ModuleDatabase",
    "ModuleEnv",
    "ModuleId",
    "Option",
    "ProgressEvent",
    "ProvenanceGraph",
    "SPACE_REGISTRY_CHANGED_EVENT_ID_STR",
    "SPACE_UPDATED_EVENT_ID_STR",
    "SchemaMigration",
    "ScopedVfs",
    "SecurityTier",
    "SemVer4",
    "SemanticUri",
    "SetDynamicSpaceInput",
    "SnapshotGen",
    "SnapshotReader",
    "SpaceAckCursorInput",
    "SpaceDiffBatch",
    "SpaceFileEntry",
    "SpaceId",
    "SpacePath",
    "SpaceScanInput",
    "SpaceSpec",
    "StorageOpenOptions",
    "StructuredLogger",
    "TaskCancelledException",
    "TaskContext",
    "TaskGroup",
    "TaskId",
    "TaskMetadata",
    "TaskOutcome",
    "VersionConstraint",
    "VfsCapabilities",
    "VfsStat",
    "WORKSPACE_RELOADED_EVENT_ID",
    "WriteTransaction",
    "YscbClient",
    "YscbError",
    "YscbModule",
    "define_event",
    "format_output",
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


## 4. 對外公開 75 符號分組總表（單一匯入邊界）

| 分組 | 匯出符號（共 75 個） |
| :--- | :--- |
| **宣告與執行契約（28 個）** | `Arg`, `CancellationToken`, `ClientRoutingPolicy`, `ConcurrencyMode`, `DispatchMode`, `Empty`, `EventMetadata`, `ExecutionPriority`, `ExitCodeProvider`, `HostPath`, `HumanRenderable`, `InMemoryModule`, `Module`, `ModuleEnv`, `Option`, `ProgressEvent`, `SecurityTier`, `TaskContext`, `TaskGroup`, `TaskMetadata`, `TaskOutcome`, `YscbClient`, `YscbModule`, `define_event`, `format_output`, `on_event`, `periodic`, `task` |
| **Foundation 值物件、錯誤與可觀測（17 個）** | `JsonValue`, `ModuleId`, `TaskId`, `EventId`, `SemVer4`, `VersionConstraint`, `SemanticUri`, `SpaceId`, `SpacePath`, `SnapshotGen`, `YscbError`, `ErrorCode`, `ErrorDetail`, `TaskCancelledException`, `LogLevel`, `StructuredLogger`, `LocaleCatalog` |
| **VFS 與持久化儲存（9 個）** | `ScopedVfs`, `VfsCapabilities`, `VfsStat`, `ModuleDatabase`, `SnapshotReader`, `WriteTransaction`, `SchemaMigration`, `StorageOpenOptions`, `BlobVault` |
| **邏輯空間、系統事件、擴充與遷移（21 個）** | `SpaceSpec`, `HashPolicy`, `SpaceFileEntry`, `SpaceDiffBatch`, `SetDynamicSpaceInput`, `ClearDynamicSpaceInput`, `SpaceScanInput`, `SpaceAckCursorInput`, `SPACE_UPDATED_EVENT_ID_STR`, `SPACE_REGISTRY_CHANGED_EVENT_ID_STR`, `WORKSPACE_RELOADED_EVENT_ID`, `MODULE_INSTALLED_EVENT_ID`, `MODULE_REMOVING_EVENT_ID`, `CONFIG_CHANGED_EVENT_ID`, `MergeStrategy`, `ContribField`, `ExtensionPointSpec`, `AggregatedContributes`, `ProvenanceGraph`, `MigrationRequest`, `on_migrate` |
