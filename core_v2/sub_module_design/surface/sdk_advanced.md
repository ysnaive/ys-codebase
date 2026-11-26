# 子模組架構設計規格：`core.surface.sdk.advanced`（進階客戶端、低階轉接器與效能剖析子門面）

> **所屬功能域**：`Domain 6 — 對外門面域 (surface/)`
> **模組路徑**：`core_v2/source/core/core/surface/sdk/advanced/__init__.py`（實作位於 `core/surface/sdk/{client,declarative}.py` 與下層域）
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.{vfs, space, storage}`、`metadata.{config, contributes}`、`execution.{event, lifecycle, rpc, runtime}`、`surface.sdk.{client, declarative}`
> **禁止反向依賴（Forbidden Imports）**：`execution.daemon`、`packaging/*`、`surface.{cli, bootstrap}`
> **狀態**：`Active Living Spec — 38-Symbol Advanced SDK Subpackage`

## 1. 模組定位與分層邊界

`core.surface.sdk.advanced` 承接外部程式化宿主客戶端（`YscbClient`）、無磁碟記憶體模組治具（`InMemoryModule`）、CLI 呈現輔助（`format_output`）、ImTK 階層式效能剖析與渲染工具（`Profiler` / `ProfilerSession` / `ProfilerNodeSnapshot` / `NullProfiler` / `render_profiler_tree`）、細部儲存與 VFS 契約（`SnapshotReader` / `WriteTransaction` / `StorageOpenOptions` / `VfsCapabilities` / `VfsStat` / `HashPolicy` / `ConsumerCursor`）、低階值物件與系統事件 ID，讓主入口 [`core.surface.sdk`](./sdk.md) 保持高信噪比（52 個高頻業務模組核心符號），兩層 `__all__` 交集嚴格為空。

## 2. 公開契約與門面簽名（1:1 Parity）

```python
from typing import Callable, Mapping, Optional, Sequence, TypeVar, overload
from core.execution.runtime import (
    CONFIG_CHANGED_EVENT_ID,
    MODULE_INSTALLED_EVENT_ID,
    MODULE_REMOVING_EVENT_ID,
    SPACE_REGISTRY_CHANGED_EVENT_ID,
    SPACE_UPDATED_EVENT_ID,
    WORKSPACE_RELOADED_EVENT_ID,
    ClientRoutingPolicy,
    ConcurrencyMode,
    Empty,
    ExecutionPriority,
    SecurityTier,
    TaskMetadata,
    TaskOutcome,
    TaskRef,
    YscbModule,
)
from core.filesystem.space import ConsumerCursor, HashPolicy
from core.filesystem.storage import SnapshotReader, StorageOpenOptions, WriteTransaction
from core.filesystem.vfs import VfsCapabilities, VfsStat
from core.foundation import (
    CancellationToken,
    ErrorDetail,
    EventId,
    HostPath,
    JsonValue,
    LocaleCatalog,
    LogLevel,
    ModuleId,
    NullProfiler,
    Profiler,
    ProfilerNodeSnapshot,
    ProfilerSession,
    ProgressEvent,
    SemVer4,
    SnapshotGen,
    StructuredLogger,
    TaskId,
    VersionConstraint,
    render_profiler_tree,
)
from core.metadata.contributes import AggregatedContributes, ProvenanceGraph
from core.surface.sdk import Module

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


def format_output(output: object) -> tuple[str, int]: ...


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
        task_id: TaskRef[Empty, TOut],
        req: Optional[Empty] = None,
        *,
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
        task_id: TaskRef[TIn, TOut],
        req: TIn,
        *,
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
        task_id: TaskRef[TIn, TOut] | TaskId | str,
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
    "CONFIG_CHANGED_EVENT_ID",
    "ClientRoutingPolicy",
    "ConsumerCursor",
    "ErrorDetail",
    "EventId",
    "ExecutionPriority",
    "HashPolicy",
    "InMemoryModule",
    "JsonValue",
    "LocaleCatalog",
    "LogLevel",
    "MODULE_INSTALLED_EVENT_ID",
    "MODULE_REMOVING_EVENT_ID",
    "ModuleId",
    "NullProfiler",
    "Profiler",
    "ProfilerNodeSnapshot",
    "ProfilerSession",
    "ProvenanceGraph",
    "SPACE_REGISTRY_CHANGED_EVENT_ID",
    "SPACE_UPDATED_EVENT_ID",
    "SemVer4",
    "SnapshotGen",
    "SnapshotReader",
    "StorageOpenOptions",
    "StructuredLogger",
    "TaskId",
    "TaskMetadata",
    "VersionConstraint",
    "VfsCapabilities",
    "VfsStat",
    "WORKSPACE_RELOADED_EVENT_ID",
    "WriteTransaction",
    "YscbClient",
    "YscbModule",
    "format_output",
    "render_profiler_tree",
)
```
