# 子模組架構設計規格：`core.surface.sdk`（零反射方案 B 宣告式門面與程式化客戶端）

> **所屬功能域**：`Domain 6 — 對外門面域 (surface/)`
> **模組路徑**：`core_v2/source/core/core/surface/sdk/`（`declarative.py`、`client.py`、`__init__.py`）
> **依賴上限（Allowed Imports）**：`foundation/*`、`execution.{event, lifecycle, rpc, runtime}`
> **禁止反向依賴（Forbidden Imports）**：`execution.daemon`、`filesystem/*`（`execution` 層亦嚴禁反向匯入 `surface/*`）
> **狀態**：`Active Living Spec — Scheme B 25-Symbol Zero-Reflection SDK Facade`

## 1. 模組定位與架構邊界 (Positioning & Layering Overview)

`core.surface.sdk` 為下游業務模組與程式化調用端提供**唯一公開匯入門面（精準鎖定 25 個完全自洽核心符號）**，在零全域單例與零執行期反射的前提下封裝執行內核（`core.execution.{event, lifecycle, runtime, rpc}`）：

- **宣告式 DSL (`declarative.py`)**：透過內部零反射 Metaclass（`_DeclarativeMeta(ABCMeta)`）於類別定義期掃描 `Module` 與靜態 `TaskGroup` 內之 `@task`、`@on_event`、`@periodic` 疊加方法並編譯為強型別 `TaskMetadata` 與 `YscbModule` 轉接器；凡遇非法型別註解、重複 CLI 路徑或 `GATED`/`COLD_ONLY` 綁定事件/排程等違規，於類別定義期即確定性拋出 `ValueError`。
- **零反射疊加描述符**：裝飾器疊加封裝於不可變可呼叫描述符（`_DecoratedMethod`），全程零 `.__dict__` / `setattr` / `hasattr` / `getattr`，保持實體與未綁定方法直接可呼叫且與裝飾器上下疊加順序無關。
- **雙層生命週期橋接 (`ModuleEnv`)**：將 `Module` 與靜態掛載 `TaskGroup` 的 `on_init` / `on_warmup` / `on_close` 與 `env.register_closer(...)` 自動橋接至 `YscbModule.on_init` / `on_start` 與 `LifoResourceStack`，確保嚴格逆序（LIFO）清理與單點異常隔離（`TEARDOWN_ERROR` / `MODULE_DEGRADED`）。
- **測試治具 (`InMemoryModule`)**：提供流暢式 `add_task(...)` / `to_yscb_module()` 記憶體模組組裝器，專供單元與整合測試隔離使用，無須在磁碟建立 `.modules/`；生產模組嚴禁執行期動態註冊任務或訂閱。
- **程式化客戶端 (`client.py`)**：`YscbClient` 將傳入之 `Module | InMemoryModule` 轉接為 `YscbModule` 並注入 `DispatcherHostOptions(in_memory_modules=...)`，經 `RuntimeDispatcher`（`CallerSurface.SDK`）完成嚴格 JSON / Dataclass 編解碼（`DataclassCodec`）、`ProgressEvent` 進度串流、`CancellationToken` 傳遞與冪等 LIFO 關閉。

```text
@task / @on_event / @periodic -> Module / TaskGroup（類別定義期靜態驗證）
                              -> Module.to_yscb_module() / InMemoryModule.to_yscb_module()
                              -> YscbClient.local(ws, *modules) / YscbClient.connect(ws)
                              -> DispatcherHostOptions(in_memory_modules=...) -> RuntimeDispatcher.invoke()
```

### 公開匯出清冊（`core.surface.sdk.__all__`，共 25 個符號）

```text
Re-exports (10): CancellationToken, ConcurrencyMode, DispatchMode, EventMetadata, HostPath,
                 ProgressEvent, SecurityTier, TaskContext, TaskOutcome, YscbModule
SDK Symbols (15): Arg, Empty, ExitCodeProvider, HumanRenderable, InMemoryModule, Module,
                  ModuleEnv, Option, TaskGroup, YscbClient, define_event, format_output,
                  on_event, periodic, task
```

## 2. 公開契約與門面簽名（1:1 Parity）

```python
from dataclasses import dataclass
from typing import Callable, ClassVar, Mapping, Optional, Protocol, Sequence, TypeVar, overload, runtime_checkable
from core.execution.event import EventMetadata
from core.execution.runtime import (
    ConcurrencyMode,
    DispatchMode,
    SecurityTier,
    TaskContext,
    TaskOutcome,
    YscbModule,
)
from core.foundation import CancellationToken, EventId, HostPath, JsonPrimitive, JsonValue, ProgressEvent, TaskId

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")
TPayload = TypeVar("TPayload")
_TFn = TypeVar("_TFn", bound=Callable[..., object])


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


@runtime_checkable
class HumanRenderable(Protocol):
    def render_text(self) -> str: ...


@runtime_checkable
class ExitCodeProvider(Protocol):
    def exit_code(self) -> int: ...


def format_output(output: object) -> tuple[str, int]: ...


class ModuleEnv:
    workspace_root: HostPath

    def __init__(self, workspace_root: HostPath) -> None: ...
    def register_closer(self, fn: Callable[[], None]) -> None: ...


def define_event(
    event_id: str,
    payload_type: type[TPayload] = Empty,
    *,
    ordered: bool = False,
    description: str = "",
) -> EventMetadata[TPayload]: ...


class TaskGroup:
    def on_init(self, env: ModuleEnv) -> None: ...
    def on_warmup(self, env: ModuleEnv) -> None: ...
    def on_close(self) -> None: ...


class Module:
    id: ClassVar[str] = ""
    groups: ClassVar[tuple[type[TaskGroup], ...]] = ()

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
    dispatch_mode: DispatchMode = DispatchMode.HYBRID,
    interactive_tty: bool = False,
    security: SecurityTier = SecurityTier.SAFE,
    lock: Optional[str] = None,
    concurrency: Optional[ConcurrencyMode] = None,
    timeout_ms: Optional[int] = None,
) -> Callable[[_TFn], _TFn]: ...


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
    "Arg",
    "CancellationToken",
    "ConcurrencyMode",
    "DispatchMode",
    "Empty",
    "EventMetadata",
    "ExitCodeProvider",
    "HostPath",
    "HumanRenderable",
    "InMemoryModule",
    "Module",
    "ModuleEnv",
    "Option",
    "ProgressEvent",
    "SecurityTier",
    "TaskContext",
    "TaskGroup",
    "TaskOutcome",
    "YscbClient",
    "YscbModule",
    "define_event",
    "format_output",
    "on_event",
    "periodic",
    "task",
)
```

## 3. 宣告式編譯與生命週期規則

1. **類別定義期驗證（`ABCMeta.__new__`）**：
   - 具體 `Module` 子類必須宣告非空且合法之 `ModuleId`（`id`）；`Module` 本身與抽象 `ABC` 中間基類可省略 `id`。
   - `Module.groups` 必須皆為互異之具體 `TaskGroup` 子類（禁止重複或抽象基類）。
   - 任務方法必須宣告為 `(self, ctx)`、`(self, req, ctx)` 或 `(self, ctx, req)`（其中 `ctx: TaskContext`），並具嚴格非 `Any` 型別註解與顯式回傳型別（`-> None` 映射為 `output_type = Empty` 並將 `None` 回傳正規化為 `Empty()`）；`InMemoryModule.add_task` 支援 `(ctx)`、`(req, ctx)` 或 `(ctx, req)` 處理函式。
   - `SecurityTier.GATED` 與 `DispatchMode.COLD_ONLY` 任務嚴禁綁定 `@on_event` 或 `@periodic`。
   - `@on_event` 在 `mapper=None` 時僅允許無請求參數之 `(self, ctx)` 方法（自動綁定回傳 `Empty()` 之預設觸發工廠）。
   - `cli` 非空且 `summary` 為空字串時，自動取方法 Docstring 首行或以 `f"Execute {task_id}"` 補齊。
   - `lock` 非空且 `concurrency=None` 時，自動預設為 `ConcurrencyMode.SERIALIZE`。
   - 重複 `task_id`、重複 CLI `command_path` 或同父層別名碰撞皆於類別定義期直接拋出 `ValueError`。
2. **LIFO 資源卸載隔離**：
   - `Module.to_yscb_module()` 實體化所有 `groups` 並轉接掛載至 `YscbModule.on_init` / `on_start`。
   - `on_init` 關閉回呼嚴格依逆序（LIFO）執行 `env.register_closer(...)`、`group.on_close()` 與 `module.on_close()`，單點異常隔離轉為 `YscbError(ErrorCode.TEARDOWN_ERROR, ...)` 而不中斷底層資源釋放。
