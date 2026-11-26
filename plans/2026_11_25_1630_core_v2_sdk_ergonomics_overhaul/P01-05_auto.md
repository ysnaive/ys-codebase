# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：Core 2.0 下游模組 SDK 門面雙層收斂與開發人體工學重構  
> 建立日期：2026-11-25  
> 所屬主計畫：無（獨立 Full Track 計畫，為 Wave 1.3 `dev 2.0` 與 Wave 2 下游模組移植之前置門面鎖定）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (XHigh)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **SDK 雙層門面分流 (`sdk` vs `sdk.advanced`)** | 將 `core.surface.sdk` 收斂為以 `knowledge-db` / `agents-workflow` 等業務模組高頻必用為準線之精確 **52 符號**主入口；新建子套件 `core.surface.sdk.advanced`（`sdk/advanced/__init__.py`）承接外部客戶端、低階轉接器、細部儲存/VFS/剖析與值物件之精確 **38 符號**（與主入口零重複）；自 SDK 清退 4 組 `Space*Input`（移至 `bootstrap/system_module.py` 服務系統任務與 CLI）及 2 組 `SPACE_*_EVENT_ID_STR`（全倉清退，改用 `SPACE_*_EVENT` / `SPACE_*_EVENT_ID`）；同步更新內部 `cli`/`bootstrap`（含 `_TIER1_FORMAT_SNIPPET`）匯入；兩層 `__all__` 皆納入 `Gate 0` 1:1 活規格檢核（`surface/sdk.md` 與 `surface/sdk_advanced.md`）。 | P0 | [P00:DR-01] |
| **FR-02** | **一等空間門面 `ctx.spaces: SpaceClient` 與強型別系統事件** | 於 Domain 5 實作 `SpaceClient` 並掛載為 `TaskContext.spaces`，提供 `list_spaces`、`status`、`list_files`、`diff`（預設 `consumer=ctx.module_id.value`）、`scan`、`ack_cursor(batch, consumer=None)`、`set_dynamic(name, spec)`（自動綁定 `owner=ctx.module_id`）、`clear_dynamic(name=None)`，底層透過 4 支新增無鎖併發讀 `TaskExposure.SDK_ONLY` 系統任務 `core.space.{list,status,files,diff}` 與 4 支既有寫入/掃描任務 `core.space.{scan,ack_cursor,set_dynamic,clear_dynamic}` 執行，Tier 0/1 100% 對稱；將 `Empty`、3 組系統事件 Payload DTO、2 組新 `SPACE_*_EVENT_ID` 與 6 組強型別 `EventMetadata` 常數（含 `MODULE_REMOVING_EVENT` 為 `EventOrdering.ORDERED`）下沉為 Domain 5 單一真理。 | P0 | [P00:DR-01] |
| **FR-03** | **VFS 路徑橋接、`glob` 與受管子行程 `ctx.run_process`** | 於 Domain 1 `ManagedProcessTree` 新增 `capture_output: bool = False`、`stdout_pipe`/`stderr_pipe` 與 `close_pipes()`；於 `ScopedVfs` 新增 `resolve_caller_uri(raw_path, caller_cwd) -> SemanticUri` 與 `glob(uri_dir, pattern) -> tuple[SemanticUri, ...]`；於 `TaskContext` 新增 `resolve_uri(raw_path)` 與 `run_process(argv, *, cwd=None, env=None, timeout_sec=60.0, max_output_bytes=1048576) -> ProcessResult`（復用 `ManagedProcessTree(capture_output=True)`、`build_isolated_python_env()` + `sanitize_caller_env(ctx.caller_env)` 隔離環境、`ctx.cancel_token` 整棵進程樹終止、Windows `CREATE_NO_WINDOW` 與雙讀執行緒有界排空）。 | P0 | [P00:DR-03] |
| **FR-04** | **統一跨模組強型別呼叫 (`TaskRef` + `TaskContext.call` + `YscbClient.call`)** | 於 Domain 5 新增不可變三欄契約 `TaskRef[TIn, TOut](task_id, input_type, output_type)`；於 `TaskContext` 以統一重載之 `ctx.call(...)` 徹底取代 `invoke_task` 與 `invoke_typed`（底層 `RuntimeDispatcher` 不動），並於 `YscbClient.call(...)` 同步支援 `TaskRef` 重載；將 `errors.py` 修復提示與全倉測試呼叫點同步遷移。 | P0 | [P00:DR-04] |
| **FR-05** | **模組撰寫零樣板與強型別人體工學** | (1) `ProtectedModuleLoader.load_module_artifact` 於 `create_module` 缺席時自動偵測 `module_entry.py` 自身定義之唯一具象非抽象 `YscbModuleConvertible`/`YscbModule` 子類並自動建構（保留 `create_module()` 最高優先權，嚴格排除 `ABC in cls.__bases__` 與 `inspect.isabstract(cls)`）；(2) `TaskGroup[TModule_co]` 協變泛型化並提供 `parent_module -> Optional[TModule_co]` 與非空 `module -> TModule_co`；(3) `TaskContext.module_id` 屬性；(4) `@task(..., equivalence_fn=...)` 支援自訂 `COALESCE` 等價鍵；(5) `@on_event` 維持 `(self, ctx)` 或顯式 `mapper=`（無 `EventBatch`）並強化錯誤指引；維持強制 Request DTO 唯一真理（零通用 Bags）與 `ctx.load_config(MyCfg)`。 | P1 | [P00:DR-02], [P00:DR-05], [P00:DR-06] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `resolve_caller_uri` / `ctx.resolve_uri` 傳入越界路徑（`../../etc/passwd`）、半限定磁碟機路徑、符號連結（含 `symlink/../safe` 未折疊前）、空字串/控制字元、或指涉未掛載/核心專屬協議（`yscb://`、`module://`、`project://ys_codebase/.modules/...`）或他模組私有 `storage.local://other/` | 純型別錯誤/空字串/控制字元/半限定路徑拋 `ValueError`；建構 `HostPath` 前即對未折疊與折疊後原始路徑檢驗 `has_symlink_raw_path` 與 `is_symlink_or_reparse`，命中即拋 `YscbError(ErrorCode.SECURITY_GATED)`；先對**全部覆蓋掛載**取最深層級，最深層含非共掛核心專屬協議（或他模組讀隔離區、或未掛載區域）即拋 `YscbError(ErrorCode.ACCESS_DENIED)`，杜絕降級命中 `project://` 外洩 `.yscb/`。 |
| **EC-02** | `ctx.run_process(...)` 遇到 `ctx.cancel_token` 取消、逾時 `timeout_sec`、孫行程殘留、輸出超過 `max_output_bytes`、非法 `env` 鍵（如 `_YSCB_*`）或 `cwd` 指向虛擬 URI／越界路徑 | 取消時終止整棵進程樹、回收讀取執行緒與管道並拋 `TaskCancelledException`；逾時時終止進程樹並回傳 `ProcessResult(returncode=-1, ..., timed_out=True)`；雙讀執行緒有界緩衝且持續讀乾管道防死鎖，超長標記 `truncated=True` 並以 UTF-8 `errors="replace"` 解碼；`cwd` 指向無實體路徑之虛擬 URI 或越界路徑拋 `YscbError(ErrorCode.ACCESS_DENIED)`；無效參數或私密環境鍵拋 `ValueError`。 |
| **EC-03** | `ctx.spaces.*` 底層系統任務失敗（`SPACE_NOT_FOUND`、`ACCESS_DENIED`、`CONFIG_INVALID`、`TASK_TIMEOUT`）或於 Tier 1 子行程跨進程呼叫時 | `SpaceClient` 遇 `TaskOutcome(ok=False)` 呼叫 `error.raise_as_exception()` 還原具精確 `ErrorCode` 之 `YscbError`；`set_dynamic(name, spec)` 若 `spec.space_id` 與 `(ctx.module_id, name)` 不符由 `core.space.set_dynamic` 拋 `CONFIG_INVALID`；Tier 1 呼叫經由既有 `WorkerCallbackKind.INVOKE_TASK` 回呼宿主，與 Tier 0 100% 對稱。 |
| **EC-04** | `ProtectedModuleLoader.load_module_artifact` 載入無 `create_module` 之 `module_entry.py` 時，檔內有 0 個或 >=2 個具象模組子類、或含 `class Base(Module, ABC)` / 匯入他檔之子類 | 嚴格限定 `cls.__module__ == entry_mod_name`、非 `ABC in cls.__bases__` 且非 `inspect.isabstract(cls)`（並依物件身分去重）；數量 `!= 1` 時拋出 `YscbError(ErrorCode.MODULE_DEGRADED)` 並回收暫存 `sys.modules` 套件鍵；若檔內有 `create_module` 但不可呼叫亦維持拋 `MODULE_DEGRADED`。 |
| **EC-05** | `TaskRef` 傳入含巢狀 `typing.Any`、無效型別標註、或呼叫 `ctx.call(ref, wrong_type_obj)` / 缺少必填 `req` / 傳入衝突 `output_type` | `TaskRef.__init__` 遞迴檢查 `Any` 與 `is_valid_type_annotation`，非法即拋 `ValueError`；`ctx.call` 遇到輸入不符 `ref.input_type`、非 `Empty` 卻省略 `input_obj`、或衝突 `output_type` 時回傳 `TaskOutcome(ok=False, error=ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, ...))`。 |
| **EC-06** | `TaskGroup.module` 在尚未綁定 `Module` 時被讀取、`@task(equivalence_fn=...)` 傳入非可呼叫物件、或 `ScopedVfs.glob` 傳入非法 pattern（空字串、前導 `/`、含 `\` 或 `..`） | `TaskGroup.module` 拋 `RuntimeError`（`parent_module` 維持回傳 `None`）；非可呼叫 `equivalence_fn` 或非法 glob pattern 即刻拋 `ValueError`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **架構與依賴純淨** | 100% Python 3.11+ 標準庫、零 `Any`、零 `# type: ignore`、零 `print`/`getattr`、零可變模組全域、6 域 DAG 零反向匯入（`execution` 嚴禁匯入 `surface`）且 10 階段 `unplug` 物理拔除全綠。 |
| **NFR-02** | **活規格 1:1 雙向對齊** | `core.surface.sdk`（52 符號）與 `core.surface.sdk.advanced`（38 符號）兩層 `__all__` 及受影響之 6 份 Active Living Specs（`foundation.md`、`vfs.md`、`runtime.md`、`sdk.md`、`sdk_advanced.md`、`composition_and_bootstrap.md`）100% 通過 `Gate 0` 雙向校驗。 |
| **NFR-03** | **跨平台穩定與潔淨室邊界** | Linux 標準/`-O` 雙模全 9 套件與 Windows 11 實機驗證 `0 ResourceWarning`；`ys_codebase/source/*` 與 `.vscode/settings.json` 零異動。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` Gate 0 不可變全域與反射白名單**：`_IMMUTABLE_GLOBAL_CALLS` 須加入 `"EventMetadata"`；`ProtectedModuleLoader` 之 `py_mod.__dict__` 掃描須保留在已登錄白名單之 `load_module_artifact` 內，類成員探測採 `inspect.getmembers_static`。
- **`[!NOTE]` Gate 0 `sdk.advanced` 子套件與註冊順序**：以 `core/surface/sdk/advanced/__init__.py` 建為子套件（天然符合 `_assert_no_unused_top_imports` 轉匯規則），並於 `test_gate0.py` 的 `_PUBLIC_DOMAIN_ROOTS`、`pairs`（對應 `surface/sdk_advanced.md`）及 `_verify_cross_package_public_exports`（**必須排在 `core.surface.sdk` 之前**以防前綴誤判）完整註冊。
- **`[!NOTE]` 內部子行程腳本與環境基底**：`bootstrap/factory.py` 內嵌 `_TIER1_FORMAT_SNIPPET` 必須同步改由 `core.surface.sdk.advanced` 匯入 `format_output`；`ctx.run_process` 必須以 `build_isolated_python_env()` 為基底再疊加 `sanitize_caller_env(ctx.caller_env)` 與使用者 `env`，避免剝除 `PATH`/`SYSTEMROOT`。
- **`[!NOTE]` CLI `yscb fs ack-cursor` 向下相容**：既有 `core.space.ack_cursor` 同時服務 CLI 並回傳 `SystemResultView(..., {"acked": bool})`；`SpaceClient.ack_cursor()` 統一相容 `bool` 與 `{"data": {"acked": bool}}`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Downstream Business Module: kdb / aw / ast / vsc / gdrive]
   │  (high-frequency primary imports)
   ▼
core.surface.sdk (52 符號主入口)            core.surface.sdk.advanced (38 符號進階子套件)
   │  re-export only                          │  re-export only
   ▼                                          ▼
Domain 5: core.execution.runtime (contracts / module_slot / __init__)
   ├─ TaskRef[TIn, TOut] & TaskContext.call(...) ──► RuntimeDispatcher / WorkerCallback
   ├─ TaskContext.spaces (SpaceClient) ──► ctx.call("core.space.{list,status,files,diff,scan,ack_cursor,set_dynamic,clear_dynamic}")
   ├─ TaskContext.resolve_uri(raw) ──► ScopedVfs.resolve_caller_uri(raw, caller_cwd)
   ├─ TaskContext.run_process(...) ──► ManagedProcessTree(capture_output=True) + build_isolated_python_env()
   ├─ Typed System Events (6 組 EventMetadata + 3 組 Payload DTO + Empty + 6 組 *_EVENT_ID)
   └─ ProtectedModuleLoader.load_module_artifact (create_module() 優先, 否則唯一具象模組子類)
   │
   ▼
Domain 2: core.filesystem.vfs.ScopedVfs (resolve_caller_uri, glob)
   │
   ▼
Domain 1: core.foundation.proc.ManagedProcessTree (capture_output, stdout_pipe, stderr_pipe, close_pipes)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `core_v2/source/core/core/foundation/proc.py` | Modify | 為 `ManagedProcessTree` 新增 `capture_output: bool = False`、`stdout_pipe`/`stderr_pipe` 與 `close_pipes()`（含 Win32 Job 失敗與 `__exit__` 管道確定關閉） |
| `core_v2/source/core/core/foundation/errors.py` | Modify | 更新 `CallCycleError` 預設修復提示由 `ctx.invoke_task()` 改為 `ctx.call()` |
| `core_v2/source/core/core/filesystem/vfs/scoped.py` | Modify | 新增 `ScopedVfs.glob(uri_dir, pattern)` 與 `ScopedVfs.resolve_caller_uri(raw_path, caller_cwd)`（先檢 raw symlink、先全覆蓋算最深掛載防 `.yscb/` 降級外洩） |
| `core_v2/source/core/core/execution/runtime/contracts.py` | Modify | 新增 `Empty`、`TaskRef[TIn, TOut]`、`ProcessResult`、`SpaceClient`、`YscbModuleConvertible`、3 組系統事件 Payload DTO、2 組 `SPACE_*_EVENT_ID` 與 6 組強型別 `EventMetadata` 常數；於 `TaskContext` 新增 `module_id`/`spaces`/`resolve_uri`/`run_process` 並以 `call(...)` 取代 `invoke_task`/`invoke_typed` |
| `core_v2/source/core/core/execution/runtime/module_slot.py` | Modify | 實作 `_StepTaskContext.{module_id,call}` 取代 `invoke_task`；擴充 `ProtectedModuleLoader.load_module_artifact` 支援無 `create_module()` 之唯一具象非抽象模組子類自動載入 |
| `core_v2/source/core/core/execution/runtime/__init__.py` | Modify | 匯出所有新增之 Domain 5 公開契約 |
| `core_v2/source/core/core/surface/sdk/declarative.py` | Modify | 復用 Domain 5 `Empty`；協變泛型化 `TaskGroup[TModule_co]` 並新增 `module -> TModule_co`；為 `@task` 新增 `equivalence_fn`；強化 `@on_event` 無 `mapper` 錯誤指引；移除 4 組舊 `Space*Input` 與 2 組 `SPACE_*_EVENT_ID_STR` |
| `core_v2/source/core/core/surface/sdk/client.py` | Modify | 為 `YscbClient.call(...)` 新增 `TaskRef[TIn, TOut]` 重載與型別校驗，與 `TaskContext.call` 100% 對稱 |
| `core_v2/source/core/core/surface/sdk/advanced/__init__.py` | New | 建立進階／客戶端／底層轉接器二層子套件入口（精確 38 符號 `__all__`） |
| `core_v2/source/core/core/surface/sdk/__init__.py` | Modify | 收斂主入口 `__all__` 為精確 52 符號業務模組核心集 |
| `core_v2/source/core/core/surface/cli/entrypoint.py` | Modify | 將 `format_output` 匯入遷移至 `core.surface.sdk.advanced` |
| `core_v2/source/core/core/surface/bootstrap/factory.py` | Modify | 將 `InMemoryModule` 與 `format_output`（含 `_TIER1_FORMAT_SNIPPET`）匯入遷移至 `core.surface.sdk.advanced` |
| `core_v2/source/core/core/surface/bootstrap/system_module.py` | Modify | 承接 4 組 `Space*Input` DTO；復用 Domain 5 事件 Payload 與 6 組 `EventMetadata`（清退 `SPACE_*_EVENT_ID_STR`）；新增 4 支無鎖併發讀 `SDK_ONLY` 任務 `core.space.{list,status,files,diff}` 及對應 4 組輸入 DTO |
| `core_v2/source/core/core/surface/bootstrap/__init__.py` | Modify | 匯出新增 4 組 `Space{List,Status,Files,Diff}Input`、保留 4 組舊 `Space*Input` 與事件 Payload，清退 `SPACE_*_EVENT_ID_STR` |
| `core_v2/sub_module_design/{foundation/foundation,filesystem/vfs,execution/runtime,surface/sdk,surface/sdk_advanced,surface/composition_and_bootstrap}.md` | Modify / New | 1:1 同步 5 份既有活規格並新建 `surface/sdk_advanced.md` |
| `core_v2/tests/{_harness,test_gate0,test_foundation,test_vfs_storage_space,test_runtime_daemon,test_rc_e2e,test_surface_sdk,test_surface_cli_e2e}.py` | Modify | 遷移全倉測試之 `ctx.call` / `sdk.advanced` 匯入；更新 `Gate 0` 雙層校驗、`_PUBLIC_DOMAIN_ROOTS`、跨包白名單順序與 `_IMMUTABLE_GLOBAL_CALLS`；補齊 `FR-01`~`FR-05` 與 `EC-01`~`EC-06` 測項 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] Domain 5 單一真理歸屬**：`Empty`、`TaskRef`、`ProcessResult`、`SpaceClient`、`YscbModuleConvertible`、3 組事件 Payload、6 組 `*_EVENT_ID` 與 6 組強型別 `EventMetadata` 定義於 `core.execution.runtime.contracts`，由 `sdk`/`sdk.advanced`/`bootstrap` 單向 Re-export，維持 6 域 DAG 零反向依賴與 10 階段 `unplug` 全綠。
- **[P02:DR-02] `SpaceClient` 讀寫分流與零重複鎖**：`SpaceClient` 全數透過 `TaskContext.call(...)` 調用 `core.space.*` 系統任務（享 Tier 0/1 對稱與效能樹追蹤）；其中 4 支純讀取任務 `core.space.{list,status,files,diff}` 採無鎖 `ConcurrencyMode.PARALLEL` 保留 SQLite WAL 併發讀吞吐，4 支變更/掃描任務 `core.space.{scan,ack_cursor,set_dynamic,clear_dynamic}` 維持單點 `core:space_state` 互斥鎖。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# core/foundation/proc.py
class ManagedProcessTree:
    def __init__(self, argv: Sequence[str], *, cwd: HostPath, env: Optional[Mapping[str, str]] = None, inherit_tty: bool = False, capture_output: bool = False) -> None: ...
    @property
    def stdout_pipe(self) -> Optional[BinaryIO]: ...
    @property
    def stderr_pipe(self) -> Optional[BinaryIO]: ...
    def close_pipes(self) -> None: ...

# core/filesystem/vfs/scoped.py
class ScopedVfs:
    def glob(self, uri_dir: SemanticUri | str, pattern: str) -> tuple[SemanticUri, ...]: ...
    def resolve_caller_uri(self, raw_path: str, caller_cwd: HostPath) -> SemanticUri: ...

# core/execution/runtime/contracts.py
SPACE_UPDATED_EVENT_ID: EventId = EventId("core.space_updated")
SPACE_REGISTRY_CHANGED_EVENT_ID: EventId = EventId("core.space_registry_changed")

@dataclass(frozen=True, slots=True)
class Empty: ...

@dataclass(frozen=True, slots=True)
class ModuleLifecycleEventPayload:
    modules: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class ConfigChangedEventPayload:
    changed_paths: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class SpaceUpdatedEventPayload:
    spaces: tuple[str, ...] = ()

SPACE_UPDATED_EVENT: EventMetadata[SpaceUpdatedEventPayload]          # EventOrdering.UNORDERED
SPACE_REGISTRY_CHANGED_EVENT: EventMetadata[SpaceUpdatedEventPayload] # EventOrdering.UNORDERED
CONFIG_CHANGED_EVENT: EventMetadata[ConfigChangedEventPayload]        # EventOrdering.UNORDERED
MODULE_INSTALLED_EVENT: EventMetadata[ModuleLifecycleEventPayload]    # EventOrdering.UNORDERED
MODULE_REMOVING_EVENT: EventMetadata[ModuleLifecycleEventPayload]     # EventOrdering.ORDERED
WORKSPACE_RELOADED_EVENT: EventMetadata[Empty]                        # EventOrdering.UNORDERED

@dataclass(frozen=True, slots=True, init=False)
class TaskRef(Generic[TIn, TOut]):
    task_id: TaskId
    input_type: type[TIn]
    output_type: type[TOut]
    def __init__(self, task_id: TaskId | str, input_type: type[TIn], output_type: type[TOut]) -> None: ...

@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int           # -1 when timed_out=True
    stdout: str               # UTF-8 errors="replace"
    stderr: str               # UTF-8 errors="replace"
    duration_ms: float
    timed_out: bool = False
    truncated: bool = False
    @property
    def ok(self) -> bool: ... # (not self.timed_out) and self.returncode == 0

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

class TaskContext(ABC):
    @property
    @abstractmethod
    def module_id(self) -> ModuleId: ...
    @property
    def spaces(self) -> SpaceClient: ...                              # concrete default
    def resolve_uri(self, raw_path: str) -> SemanticUri: ...          # concrete default
    def run_process(
        self, argv: Sequence[str], *, cwd: Optional[SemanticUri | HostPath | str] = None,
        env: Optional[Mapping[str, str]] = None, timeout_sec: float = 60.0, max_output_bytes: int = 1048576,
    ) -> ProcessResult: ...                                           # concrete default
    @overload
    def call(self, target: TaskRef[Empty, TOut], input_obj: Optional[Empty] = None, *, target_workspace: Optional[HostPath] = None, routing_policy: Optional[ClientRoutingPolicy] = None) -> TaskOutcome[TOut]: ...
    @overload
    def call(self, target: TaskRef[TIn, TOut], input_obj: TIn, *, target_workspace: Optional[HostPath] = None, routing_policy: Optional[ClientRoutingPolicy] = None) -> TaskOutcome[TOut]: ...
    @overload
    def call(self, target: TaskId | str, input_obj: object = None, *, output_type: type[TOut], target_workspace: Optional[HostPath] = None, routing_policy: Optional[ClientRoutingPolicy] = None) -> TaskOutcome[TOut]: ...
    @overload
    def call(self, target: TaskId | str, input_obj: object = None, *, output_type: None = None, target_workspace: Optional[HostPath] = None, routing_policy: Optional[ClientRoutingPolicy] = None) -> TaskOutcome[JsonValue]: ...
    @abstractmethod
    def call(self, target: TaskRef[TIn, TOut] | TaskId | str, input_obj: object = None, *, output_type: Optional[type[TOut]] = None, target_workspace: Optional[HostPath] = None, routing_policy: Optional[ClientRoutingPolicy] = None) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]: ...

# core/surface/sdk/declarative.py & client.py
TModule_co = TypeVar("TModule_co", bound="Module", covariant=True)
class TaskGroup(Generic[TModule_co], metaclass=_DeclarativeMeta):
    @property
    def parent_module(self) -> Optional[TModule_co]: ...
    @property
    def module(self) -> TModule_co: ...
class Module(metaclass=_DeclarativeMeta):
    groups: ClassVar[tuple[type[TaskGroup[Module]], ...]] = ()
def task(..., equivalence_fn: Optional[Callable[[TIn], str]] = None) -> Callable[[_TFn], _TFn]: ...
# YscbClient.call(...) adds matching TaskRef[Empty, TOut] and TaskRef[TIn, TOut] overloads.

# core/surface/bootstrap/system_module.py (4 new SDK_ONLY lock-free PARALLEL tasks on CoreSystemModule)
@dataclass(frozen=True, slots=True) class SpaceListInput: owner: Optional[str] = None
@dataclass(frozen=True, slots=True) class SpaceStatusInput: space_id: str
@dataclass(frozen=True, slots=True) class SpaceFilesInput: space_id: str; pattern: Optional[str] = None
@dataclass(frozen=True, slots=True) class SpaceDiffInput: space_id: str; consumer: str
# CoreSystemModule: core.space.list -> tuple[SpaceSpec, ...], core.space.status -> SpaceStatusSnapshot,
# core.space.files -> tuple[SpaceFileEntry, ...], core.space.diff -> SpaceDiffBatch (all HYBRID, SAFE, PARALLEL)
```

### 3.2 雙層門面精確 `__all__` 清冊與行為細則

- **`core.surface.sdk.__all__`（精確 52 符號，主入口）**：
  `Arg`, `BlobVault`, `CONFIG_CHANGED_EVENT`, `CancellationToken`, `ConcurrencyMode`, `ConfigChangedEventPayload`, `ContribField`, `DispatchMode`, `Empty`, `ErrorCode`, `EventMetadata`, `ExitCodeProvider`, `ExtensionPointSpec`, `HostPath`, `HumanRenderable`, `MODULE_INSTALLED_EVENT`, `MODULE_REMOVING_EVENT`, `MergeStrategy`, `MigrationRequest`, `Module`, `ModuleDatabase`, `ModuleEnv`, `ModuleLifecycleEventPayload`, `Option`, `ProcessResult`, `ProgressEvent`, `SPACE_REGISTRY_CHANGED_EVENT`, `SPACE_UPDATED_EVENT`, `SchemaMigration`, `ScopedVfs`, `SecurityTier`, `SemanticUri`, `SpaceClient`, `SpaceDiffBatch`, `SpaceFileEntry`, `SpaceId`, `SpacePath`, `SpaceSpec`, `SpaceStatusSnapshot`, `SpaceUpdatedEventPayload`, `TaskCancelledException`, `TaskContext`, `TaskGroup`, `TaskOutcome`, `TaskRef`, `WORKSPACE_RELOADED_EVENT`, `YscbError`, `define_event`, `on_event`, `on_migrate`, `periodic`, `task`。
- **`core.surface.sdk.advanced.__all__`（精確 38 符號，進階子套件，與主入口交集為空）**：
  `AggregatedContributes`, `CONFIG_CHANGED_EVENT_ID`, `ClientRoutingPolicy`, `ConsumerCursor`, `ErrorDetail`, `EventId`, `ExecutionPriority`, `HashPolicy`, `InMemoryModule`, `JsonValue`, `LocaleCatalog`, `LogLevel`, `MODULE_INSTALLED_EVENT_ID`, `MODULE_REMOVING_EVENT_ID`, `ModuleId`, `NullProfiler`, `Profiler`, `ProfilerNodeSnapshot`, `ProfilerSession`, `ProvenanceGraph`, `SPACE_REGISTRY_CHANGED_EVENT_ID`, `SPACE_UPDATED_EVENT_ID`, `SemVer4`, `SnapshotGen`, `SnapshotReader`, `StorageOpenOptions`, `StructuredLogger`, `TaskId`, `TaskMetadata`, `VersionConstraint`, `VfsCapabilities`, `VfsStat`, `WORKSPACE_RELOADED_EVENT_ID`, `WriteTransaction`, `YscbClient`, `YscbModule`, `format_output`, `render_profiler_tree`。
- **清退 6 符號**：`ClearDynamicSpaceInput`、`SetDynamicSpaceInput`、`SpaceAckCursorInput`、`SpaceScanInput` 移至 `core.surface.bootstrap.system_module`（保留於 `bootstrap.__all__` 服務系統任務與 CLI）；`SPACE_UPDATED_EVENT_ID_STR`、`SPACE_REGISTRY_CHANGED_EVENT_ID_STR` 全倉清退。
- **關鍵行為契約細則**：
  - `ScopedVfs.glob(uri_dir, pattern)`：僅回傳符合相對 POSIX 規則（`*` 不跨 `/`、`?` 單字元、`**` 跨 0..N 層目錄）之**檔案** `SemanticUri`，依字串字典序排序；目錄不存在或非目錄回傳 `()`；空字串、前導 `/`、含 `\`、控制字元或 `..` 區段拋 `ValueError`。
  - `ScopedVfs.resolve_caller_uri(raw_path, caller_cwd)`：含 `://` 則走語意 URI 解析 + 讀隔離 + 非共掛最深核心掛載阻斷 + 物理路徑 symlink 檢查；否則以原始字串驗證非半限定路徑與未折疊/折疊後 symlink（命中拋 `SECURITY_GATED`）後建構 `HostPath`，取全覆蓋最深層掛載（同深優先 `project://` > 非別名基底掛載 > 別名掛載；最深層含非共掛核心專屬協議或讀隔離外模組區拋 `ACCESS_DENIED`）。
  - `TaskContext.run_process(...)`：`cwd=None` 預設為 `self.caller_cwd`；顯式 `cwd`（`str`/`SemanticUri`/`HostPath`）強制經 VFS 讀邊界校驗並解析實體路徑（虛擬 URI 或越界拋 `ACCESS_DENIED`，目錄不存在拋 `FileNotFoundError`）；環境採 `build_isolated_python_env()` + `sanitize_caller_env(self.caller_env)` + 經校驗之使用者 `env`（拒絕 `_YSCB_*` 與劫持鍵）；取消拋 `TaskCancelledException`，逾時回傳 `ProcessResult(returncode=-1, ..., timed_out=True)`。
- **階段決策紀錄**：`[P03:DR-01]` `TaskRef` 採 `@dataclass(frozen=True, slots=True, init=False)` 顯式 `__init__` 與遞迴非 `Any` 檢查；`TaskContext.call` 預設參數採公開 `None` 以符合 Gate 0 活規格求值對齊；`core.space.{list,status,files,diff}` 屬 `TaskExposure.SDK_ONLY` + `ConcurrencyMode.PARALLEL` 無鎖併發讀，與寫入/掃描任務之 `core:space_state` 單點互斥鎖正交分離。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05、P00 DR-01 ~ DR-06 與 Pre-Code Analyze Gate 全部 5 項 BLOCKER 與 6 項 ADVISORY 已 100% 閉環落盤。
- [x] **邊界防護**：EC-01 ~ EC-06 涵蓋未折疊 symlink 防繞過、最深掛載防 `.yscb/` 降級外洩、受管進程樹取消與雙執行緒排空、Tier 1 空間回呼、無樣板模組抽象/歧義防護與型別衝突。
- [x] **依賴與 Gate 0 純淨**：Domain 5 零反向匯入 Domain 6、`sdk.advanced` 建為子套件、`test_gate0.py` 註冊順序防跨包前綴衝突、`_IMMUTABLE_GLOBAL_CALLS` 納入 `"EventMetadata"`、`load_module_artifact` 嚴守反射白名單。
- **靈魂拷問與防護解法**：
  1. *若 `core.surface.sdk` 移出 `format_output` 與 `InMemoryModule`，是否會導致 Tier 1 CLI 渲染或測試崩潰？* -> 同步遷移 `cli/entrypoint.py`、`bootstrap/factory.py`（含 `_TIER1_FORMAT_SNIPPET`）及全倉測試至 `core.surface.sdk.advanced`，並於雙模全 9 套件實測 Tier 1 CLI 輸出渲染。
  2. *`ctx.run_process()` 讀取子行程 stdout/stderr 會否死鎖或遺留管道句柄？* -> `ManagedProcessTree(capture_output=True)` 於 Win32 Job 失敗與 `__exit__` 確定呼叫 `close_pipes()`；`run_process` 以雙 daemon 讀執行緒有界緩衝且讀乾管道，結束/取消/逾時皆 `terminate_tree()` + `join()` + `close_pipes()`，確保零死鎖與 `0 ResourceWarning`。
  3. *`resolve_caller_uri` 遇 `<repo>/ys_codebase/.modules/foo` 會否降級命中 `project://`？* -> 先對全部覆蓋掛載算 `max_root_len`，最深層命中 `_KERNEL_ONLY_SCHEMES`（排除與 `project` 共掛之 `yscb.host`）直接拋 `ACCESS_DENIED`，絕不降級。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **活規格 (Meso)** | `core_v2/sub_module_design/{foundation/foundation,filesystem/vfs,execution/runtime,surface/sdk,surface/composition_and_bootstrap}.md` | Modify | 1:1 同步 `ManagedProcessTree`、`ScopedVfs`、`TaskContext`/`TaskRef`/`ProcessResult`/`SpaceClient`/系統事件、`sdk`（52 符號）與 `bootstrap` 4 支新 `core.space.*` 任務及清退項 |
| **活規格 (Meso)** | `core_v2/sub_module_design/surface/sdk_advanced.md` | New | 新建 `core.surface.sdk.advanced`（38 符號）Active Living Spec 並接入 Gate 0 1:1 校驗 |
| **交接與路線圖** | `core_v2/ROADMAP.md`、`core_v2/handoff.md` | Modify | Phase 7 結案時更新雙層 SDK 與人體工學重構成果 |
| **1.x 知識庫** | `docs/<Category>/*.md` | N/A | 潔淨室邊界不異動 1.x 文檔 |
| **微觀註解** | 受異動之 `core_v2/source/core/core/**/*.py` | Modify | 補齊全部新增公開介面、參數與例外契約 Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | Phase 7 結案時追加本計畫高階變更摘要 |

- **決策定稿**：**[P04:DR-01]** 採分層順序推進（Domain 1 `proc`/`errors` + Domain 2 `scoped` + Domain 5 `contracts`/`module_slot`/`__init__` -> Domain 6 `sdk`/`sdk.advanced`/`client`/`cli`/`bootstrap` -> 6 份活規格與全倉測試遷移/擴充），動刀前先經盲眼 `Pre-Code Analyze Gate` 複審取得 `ANALYZE_GATE: PASSED`，完成後通過雙模全 9 套件與 Pre-UX 盲審。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 Domain 1 `ManagedProcessTree(capture_output=...)` 與 `CallCycleError` 提示（`foundation/{proc,errors}.py`）、Domain 2 `ScopedVfs.{glob,resolve_caller_uri}`（`filesystem/vfs/scoped.py`）與 Domain 5 `Empty`/`TaskRef`/`ProcessResult`/`SpaceClient`/`YscbModuleConvertible`/6 組強型別系統事件契約、`TaskContext.{module_id,spaces,call,resolve_uri,run_process}`（`execution/runtime/{contracts,module_slot,__init__}.py`）及 `ProtectedModuleLoader.load_module_artifact` 無樣板自動載入
- [x] **TASK-02**：實作 Domain 6 雙層 SDK（`surface/sdk/{__init__,declarative,client}.py`、`surface/sdk/advanced/__init__.py`，含協變 `TaskGroup[TModule_co]`、`module` 屬性、`@task(..., equivalence_fn=...)`、`YscbClient.call(TaskRef)`）、遷移內部 `cli/entrypoint.py` 與 `bootstrap/factory.py`（含 `_TIER1_FORMAT_SNIPPET`），並於 `bootstrap/{system_module,__init__}.py` 承接 4 組舊 `Space*Input` 與新增 4 支無鎖併發讀 `core.space.{list,status,files,diff}` SDK-only 系統任務
- [x] **TASK-03**：同步更新全部 6 份 Active Living Specs（含新建 `surface/sdk_advanced.md`）、遷移全倉測試之 `ctx.call` / `sdk.advanced` 匯入、更新 `Gate 0`（`_IMMUTABLE_GLOBAL_CALLS`、`_PUBLIC_DOMAIN_ROOTS`、`pairs`、`_verify_cross_package_public_exports` 順序），並補齊 `FR-01`~`FR-05` 與 `EC-01`~`EC-06` 之單元、跨進程 Tier 1 與 E2E 測試，驗證 Linux 標準/`-O` 雙模全 9 套件 100% 通過

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01** | Minor | Pre-UX 盲審指出 `capture_output=True` 採用預設 `BufferedReader` 於 `KeyboardInterrupt` 或異常中斷時恐觸發 C 鎖死鎖，且 Windows 環境鍵需大小寫去重；`ManagedProcessTree` 改以 `bufsize=0`（無緩衝 `FileIO`）搭配 `finally` 優先終止進程樹並補齊 `TASK_PREEMPTED` 保留與 `Protocol` 排除。 | 已實作並通過 Pre-UX 盲審複驗（`REVIEW_STATUS: PASSED`）與雙模全 9 套件驗證 |
| **TASK-03** | Minor | `-O` 雙模回歸捕獲既存 `_verify_single_kernel_fast_daemon_boot` 於 `WARMING -> READY` 過渡視窗提早發送 `CONTROL_STOP` 之測試競態；改於確認就緒輸出（`sup_out` 非空）後再發送停止指令。 | 已修復並通過標準與 `-O` 雙模全 9 套件 100% 綠燈 |
| **UX-01** | Minor | Windows 11 `-O` 實機驗證捕獲既有 `core_sig_cache` 測項 `+50ms` 視窗遭 NTFS `fsync` 擊穿，並連帶識別 `core/execution/daemon/service.py` 缺少 `cache_mtime_ns` 跨重啟 Racy-Clean 守衛；經開發者授權同步補強生產端雙條件 Racy-Clean（含 `_boot_core_snapshot_ns` 與 `daemon.md` 同步）及擴充測試視窗與跨重啟驗證。 | 已實作並完成 Linux 雙模回歸與 GDrive 推送待 Windows 11 複測 |
