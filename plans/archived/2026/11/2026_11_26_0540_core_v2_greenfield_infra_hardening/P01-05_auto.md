# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：Core 2.0 下游基建高優先回補（遷移回滾、熱 Worker 呈現、憑證防護、子行程 I/O 與空間反解）  
> 建立日期：2026-11-26  
> 所屬主計畫：無（獨立 Full Track 計畫，於 Wave 1.3 `dev 2.0` 與 Wave 2 模組移植前堵死盲眼審計檢出之 5 項高優先內核缺漏）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (XHigh)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **`@on_migrate` 跳過新版 `on_init()` 與 `.storage.local/<mod>/` 交易回滾 (`1A`)** | (1) `InvokeRequest`/`LocalStepExecutionSpec`/`WorkerCommandEnvelope` 新增 `skip_module_init: bool = False`（僅限 `is_internal_trigger=True` 且目標任務為 `<mod>.yscb_on_migrate` 之冷派發使用）；`LocalModuleSlotRegistry` 與 Tier 1 Worker 在 `skip_module_init=True` 時直接載入新版模組執行 `@on_migrate` 而跳過 `on_init()`，完成後立即關閉資源並卸載模組包，確保零殘留 SQLite 檔案句柄；(2) `OfflinePackageEngine.migration_rollback_scope()` 回傳向下相容可呼叫句柄 `MigrationRollbackHandle`（保留 `restore()` 與 `__call__()`），新增 `snapshot_module_storage_local(module_id)`；`CoreSystemModule` 僅於 `trans.is_upgrade` 且 `_module_declares_on_migrate` 為真時，在執行遷移前即刻備份該模組 `.storage.local/<mod>/`（含 `.db`/`.db-wal`/`.db-shm`）至 `0o700` `.temp/`，失敗時原子還原（含刪除遷移前不存在之新建目錄），成功或結束時清理暫存；常態 `SnapshotVault` 維持排除 `.storage.local/`。 | P0 | [P00:DR-01] |
| **FR-02** | **Tier 0/1 `HumanRenderable` / `ExitCodeProvider` 熱 Worker 化與消滅 CI 假綠** | (1) 將 `HumanRenderable`、`ExitCodeProvider` 與 `format_output` 下沉至 Domain 5 `core.execution.runtime.contracts`（由 `core.surface.sdk` 與 `core.surface.sdk.advanced` 單向 Re-export，維持 6 域 DAG 與 `unplug` 全綠）；(2) `InvokeRequest`/`LocalStepExecutionSpec`/`WorkerCommandEnvelope`/`DaemonRpcInvokeEnvelope` 新增 `include_presentation: bool = False`，`WorkerStepReply`/`StepExecutionResult`/`DaemonRpcInvokeReply`/`TaskOutcome` 新增 `rendered_text: Optional[str] = None` 與 `exit_code: Optional[int] = None`；(3) CLI 呼叫設 `include_presentation=True`，由執行該步之同進程 Slot 或溫熱 Tier 1 Worker 直接於原始強型別物件呼叫 `format_output` 回填 `(rendered_text, exit_code)`，刪除 `factory.py` `_resolve_tier1_disk_presentation` 冷子行程與 `_TIER1_FORMAT_SNIPPET`；若 `render_text()` 或 `exit_code()` 拋例外則以 `ErrorCode.BUSINESS_FAILURE` 明確失敗回報，杜絕退出碼靜默回落 `0`。 | P0 | [P00:DR-02] |
| **FR-03** | **Secret 憑證安全閉環 (`2A`，無 `--reveal`)** | (1) 於 `foundation/codec.py` 新增 `SECRET_FIELD_METADATA_KEY = "yscb_secret"` 與 `secret_field(...)`（回傳標準 `dataclasses.field(..., metadata={"yscb_secret": True})`），`SchemaExporter` 辨識後於 JSON Schema 寫入 `"writeOnly": true` 與 `"x-yscb-secret": true`；於 `core.surface.sdk` 匯出 `secret_field`（主入口升至精確 **53 符號**）；(2) 於 `foundation/profiler.py` 公開共用 `is_sensitive_key(key: str) -> bool`；(3) `ConfigStore` 寫入 `.config.local/<mod>/config.local.json` 強制傳入 `file_mode=0o600`（POSIX 並收斂 `.config.local` 目錄權限 `0o700`，Windows 走既有 owner-only DACL）；`SnapshotVault._CFG_BACKUP_AREAS` 移除 `.config.local`；(4) `core.config.{list,get,inspect}` 對所有源自 `config.local.json` 的鍵、Schema/dataclass 標記 `yscb_secret`/`writeOnly` 的鍵及命中 `is_sensitive_key` 的鍵一律脫敏為 `"[REDACTED]"`，且不提供 `--reveal`；模組內部 `ctx.load_config(MyCfg)` 維持讀取強型別原值。 | P0 | [P00:DR-03] |
| **FR-04** | **`ManagedProcessTree` / `run_process` 補齊 `stdin`、`bytes` 輸出與工具鏈環境白名單 (`3B`)** | (1) 於 `foundation/primitives.py` 新增不可變 `TOOLCHAIN_ENV_ALLOWLIST` 與 `extract_toolchain_env(raw_env)`（大小寫不敏感比對，排除 `_YSCB_*` 與 Python 劫持鍵），不改動 `manifest.json`；(2) `ManagedProcessTree` 新增 `pipe_stdin: bool = False`、`stdin_pipe` 並納入 `close_pipes()` 與 Win32 失敗清理；(3) `ProcessResult` 新增 `stdout_bytes: bytes = b""` 與 `stderr_bytes: bytes = b""`；(4) `TaskContext.run_process` 新增 `input: Optional[str | bytes] = None`（背景寫入執行緒分塊寫入並 `close()` 通知 EOF，防大 payload 管道互鎖）與 `inherit_toolchain_env: bool = True`（疊加宿主安全工具鏈變數，使用者 `env` 優先覆寫），回傳同時具備無損原始 `bytes` 與 UTF-8 文字輸出之 `ProcessResult`。 | P0 | [P00:DR-04] |
| **FR-05** | **`SpaceClient` 無鎖路徑反解與空間匹配 (`4A`)** | 於 `CoreSystemModule` 新增 2 支 `ConcurrencyMode.PARALLEL`、`TaskExposure.SDK_ONLY` 系統任務：`core.space.resolve_uri`（`SpaceRegistry.resolve_file_path` $\to$ 經呼叫模組 `ScopedVfs` 轉為已通過讀隔離驗證之 `SemanticUri`）與 `core.space.match_spaces`（先經呼叫模組 `ScopedVfs` 驗證 `target` 讀權限轉 `HostPath` $\to$ 逐空間 `match_path` 回傳排序去重之 `tuple[SpaceId, ...]`）；於 `SpaceClient` 新增對應 `resolve_uri(space_id, rel_path)` 與 `match_spaces(target)`，Tier 0/1 100% 對稱。 | P1 | [P00:DR-05] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 非法調用 `skip_module_init=True`（非 `is_internal_trigger`、非 `*.yscb_on_migrate` 或熱派發），或 `@on_migrate` 在升級模組中途失敗（含模組 A 成功、模組 B 失敗，或先前無 `.storage.local/<mod>` 目錄） | 非法傳入 `skip_module_init=True` 即刻回傳 `ErrorCode.ACCESS_DENIED`；失敗回滾時於冷 Worker/Slot 徹底釋放後原子還原全部已快照模組之 `.storage.local/<mod>/`（含刪除遷移前原本不存在之新建目錄與 `.db-wal`/`.db-shm`），驗證 v1 模組重啟零 `SCHEMA_MIGRATION_ERROR`。 |
| **EC-02** | `HumanRenderable.render_text()` 或 `ExitCodeProvider.exit_code()` 在 Tier 0/1 Worker 內拋出例外、回傳非 `str`/非純 `int`（如 `bool`）、或 `COALESCE` 跟單者為 CLI 而 Leader 未要求呈現 | 呈現/退出碼求值例外或型別違規直接回報 `WorkerStepReply(ok=False, error=ErrorDetail(ErrorCode.BUSINESS_FAILURE, ...))`，絕不吞成退出碼 `0`；`COALESCE` 合併若任務宣告 `custom_render`/`custom_exit_code` 或跟單者需要呈現，Leader 統一附帶呈現結果（若缺席則 Tier 1 絕不靜默降級回傳 `0`）。 |
| **EC-03** | 專案 `config.json` 與本機 `config.local.json` 同時存在巢狀物件鍵、陣列、標記 `secret_field` 之欄位（即使寫於 `config.json`）、敏感鍵名（如 `api_token`）、或非敏感 `config.local` 鍵 | `core.config.{list,get,inspect}` 遞迴比對 local 覆寫路徑、Schema `writeOnly`/`x-yscb-secret` 路徑與 `is_sensitive_key()` 鍵名，任一命中皆脫敏為 `"[REDACTED]"`；`config.local.json` 於 POSIX 為 `0o600`（父目錄 `0o700`）、Windows 具 owner-only ACL，且 `SnapshotVault.create_snapshot()` 產出之 `.snapshots/` 零 `.config.local` 檔案。 |
| **EC-04** | `ctx.run_process` 傳入超過 OS 管道緩衝區（如 `256 KiB`）之 `input`、子行程提早退出關閉 stdin（`BrokenPipeError`）、非法型別 `input`（如 `int`）、非 UTF-8 二進位輸出（如 `b"\x80\xff\x00OK"`）、取消或逾時 | 背景寫入執行緒分塊寫入並安全吞掉 `BrokenPipeError`/`OSError` 且於 `finally` 強制關閉 `stdin_pipe`；非 `str`/`bytes`/`None` 拋 `ValueError`；`stdout_bytes`/`stderr_bytes` 無損保留原始位元組（受 `max_output_bytes` 截斷上限保護），`stdout`/`stderr` 以 UTF-8 `errors="replace"` 解碼；取消或逾時皆中斷寫入執行緒、終止整棵進程樹並關閉全部 3 條管道（`0 ResourceWarning`）。 |
| **EC-05** | `ctx.spaces.resolve_uri` 解析到呼叫模組無權讀取之核心專屬區或他模組私密區，或 `ctx.spaces.match_spaces` 傳入越界路徑／未折疊符號連結／無實體路徑之虛擬 URI | `resolve_uri` 經呼叫模組 `ScopedVfs.resolve_caller_uri` 攔截越權（拋 `ACCESS_DENIED` 或 `SECURITY_GATED`）；`match_spaces` 先經 `ScopedVfs.resolve_caller_uri` + `try_get_physical_path` 驗證讀權限與實體存在，越界拋 `ACCESS_DENIED`/`SECURITY_GATED`，無匹配空間回傳空元組 `()`。 |
| **EC-06** | `secret_field()` 與既有 `default` / `default_factory` 同時傳入或傳入不合法 `metadata` 衝突 | 依 `dataclasses.field` 標準驗證互斥性；若傳入自訂 `metadata` 則安全合併保留 `"yscb_secret": True` 不覆寫使用者其他中繼鍵。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **架構與依賴純淨** | 100% Python 3.11+ 標準庫、零 `Any`、零 `# type: ignore`、零 `print`/`getattr`、6 域 DAG 零反向匯入（`execution` 嚴禁匯入 `surface`）且 10 階段 `unplug` 物理拔除全綠。 |
| **NFR-02** | **活規格 1:1 雙向對齊** | `core.surface.sdk`（精確 **53 符號**）與 `core.surface.sdk.advanced`（精確 **38 符號**）及所有受異動 Active Living Specs 100% 通過 `Gate 0` 雙向校驗。 |
| **NFR-03** | **跨平台穩定與潔淨室邊界** | Linux 標準/`-O` 雙模全 9 套件與 Windows 11 實機驗證 `0 ResourceWarning`；Tier 1 熱 CLI 呼叫不再 spawn `_TIER1_FORMAT_SNIPPET` 冷子行程；`ys_codebase/source/*` 與 `.vscode/settings.json` 零異動。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` `atomic_write_bytes` 既有權限原語**：`filesystem/fs/atomic.py` 已內建 `file_mode: Optional[int]`（POSIX `os.fchmod` + Windows `_open_windows_owner_only_temp_fd` DACL），`ConfigStore` 直接傳 `file_mode=0o600` 即可，無需另造輪子。
- **`[!NOTE]` `SnapshotVault` 既有測試對齊**：將 `.config.local` 移出 `SnapshotVault._CFG_BACKUP_AREAS` 後，需同步檢視並更新 `test_metadata_packaging.py` 中關於 `.snapshots/` 備份範圍之斷言，改為驗證 `.config.local` 被嚴格排除。
- **`[!NOTE]` `StepExecutionResult` 位於 `execution/lifecycle/engine.py`**：為 `StepExecutionResult` 新增 `rendered_text`/`exit_code` 須同步更新 `execution/lifecycle.md` 與 `execution/runtime.md` 活規格簽名。
- **`[!NOTE]` Windows SQLite WAL 檔案鎖與回滾順序**：`invoke_internal_migration` 使用 `FORCE_COLD` 且必須在 Cold Turn 結束、Slot 與 Tier 1 單次子行程完全退出後，外層 `except` 才執行 `restore_pre_tx()` 覆寫 `.storage.local/<mod>/`，避免 Windows `PermissionError`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[1. Migration & Rollback (FR-01)]
CoreSystemModule install/update
  └─ with package_engine.migration_rollback_scope() as tx_scope:
       ├─ operation_fn()  # deploy new files + mirror
       └─ for upgraded mod declaring @on_migrate:
            ├─ tx_scope.snapshot_module_storage_local(mod_id)   # .storage.local/<mod> -> 0o700 .temp/
            ├─ kernel.invoke_internal_migration(..., skip_module_init=True)
            │    └─ Cold Turn -> LocalModuleSlotRegistry / Tier1 Worker (skip on_init(), run @on_migrate, close immediately)
            └─ on exception -> tx_scope.restore()               # atomic restore config + storage + .storage.local/<mod>

[2. Warm Worker Presentation & Exit Code (FR-02)]
CLI entrypoint (include_presentation=True)
  └─ Dispatcher -> Daemon RPC / Local Slot / Warm Tier 1 Worker
       └─ BoundTask executes -> format_output(typed_obj) in-process -> (rendered_text, exit_code)
            └─ WorkerStepReply -> StepExecutionResult -> DaemonRpcInvokeReply -> TaskOutcome -> CLI (zero cold format subprocess!)

[3. Secret Hygiene (FR-03)]   [4. Process Stdin/Bytes/Toolchain (FR-04)]   [5. SpaceClient (FR-05)]
sdk.secret_field -> SchemaExporter (writeOnly + x-yscb-secret)   ManagedProcessTree(pipe_stdin, capture_output, bufsize=0)
ConfigStore (0o600 local, redacted view)                         TaskContext.run_process(input, inherit_toolchain_env) -> ProcessResult(+bytes)
SnapshotVault (excludes .config.local)                           SpaceClient.{resolve_uri,match_spaces} -> core.space.{resolve_uri,match_spaces}
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `core_v2/source/core/core/foundation/{primitives,codec,proc,profiler,__init__}.py` | Modify | 新增 `TOOLCHAIN_ENV_ALLOWLIST` / `extract_toolchain_env`、`build_isolated_python_env(..., include_toolchain_env=False)`（滿足 `_ALLOWED_KERNEL_ENVIRON_FILES`）、`SECRET_FIELD_METADATA_KEY` / `secret_field`（`SchemaExporter` 輸出 `writeOnly` + `x-yscb-secret`）、`is_sensitive_key`、`ManagedProcessTree(pipe_stdin=...)` / `stdin_pipe` |
| `core_v2/source/core/core/metadata/config/{matrix,snapshot,__init__}.py` | Modify | `ConfigStore` 寫入/刪除 `config.local.json` 均套用 `file_mode=0o600`（目錄 `0o700`）並新增 `get_module_local_dict` / `get_module_redacted_dict`（同時讀取磁碟 `config.schema.json` `writeOnly`/`x-yscb-secret`）；`SnapshotVault._CFG_BACKUP_AREAS` 移除 `.config.local` |
| `core_v2/source/core/core/packaging/installer/{engine,__init__}.py` | Modify | `OfflinePackageEngine.migration_rollback_scope()` 回傳相容可呼叫 `MigrationRollbackHandle`（支援 `snapshot_module_storage_local(module_id)` 與 `restore()`），`.temp/` 交易目錄採 `0o700` 且還原 `.config.local` 維持 `0o600` |
| `core_v2/source/core/core/execution/lifecycle/{engine,__init__}.py` | Modify | `StepExecutionResult` 新增 `rendered_text: Optional[str] = None`、`exit_code: Optional[int] = None` |
| `core_v2/source/core/core/execution/runtime/{contracts,wire,gates,module_slot,step_host,worker_entry,dispatcher,__init__}.py` | Modify | 下沉 `HumanRenderable`/`ExitCodeProvider`/`format_output`；新增 `EncodedStepOutput` 與 `BoundTask.execute_encoded_with_presentation`；擴充 `ProcessResult(+stdout_bytes, stderr_bytes)`、`TaskContext.run_process(+input, inherit_toolchain_env)`、`SpaceClient.{resolve_uri,match_spaces}`；於 `gates.py` 納入 `include_presentation` coalesce key 並貫通 `skip_module_init` 與呈現欄位 |
| `core_v2/source/core/core/surface/sdk/{declarative,__init__,advanced/__init__}.py` | Modify | Re-export Domain 5 `HumanRenderable`/`ExitCodeProvider`/`format_output` 與 Domain 1 `secret_field`（主入口 `core.surface.sdk` 升級為精確 53 符號，`sdk.advanced` 維持 38 符號） |
| `core_v2/source/core/core/surface/cli/entrypoint.py` | Modify | CLI 派發設 `include_presentation=True`，優先消費 `TaskOutcome.{rendered_text,exit_code}`，`--json` 嚴格保持輸出純淨不洩漏 `rendered_text`，對宣告 `custom_exit_code` 卻遺失退出碼時拒絕靜默回落 `0` |
| `core_v2/source/core/core/surface/bootstrap/{factory,system_module,__init__}.py` | Modify | 移除 `_resolve_tier1_disk_presentation` 冷子行程與 `_TIER1_FORMAT_SNIPPET`；於 `SystemKernelPort`/`WorkspaceKernel`/`_LazySdkKernelPort` 新增 `scoped_vfs_for_module`；補齊 `_CustomizedBoundTask` 呈現與 `factory.py:3336` fast foreground start；`invoke_internal_migration` 啟用 `skip_module_init=True` 與 `snapshot_module_storage_local`；`core.config.{list,get,inspect,set}` 全面脫敏；新增無鎖 `core.space.{resolve_uri,match_spaces}` |
| `core_v2/sub_module_design/{foundation/foundation,metadata/config,packaging/installer,execution/lifecycle,execution/runtime,surface/sdk,surface/sdk_advanced,surface/composition_and_bootstrap}.md` | Modify | 1:1 同步全部受影響之 8 份 Active Living Specs |
| `core_v2/tests/{test_gate0,test_foundation_fs,test_metadata_packaging,test_runtime_daemon,test_surface_sdk,test_surface_cli_e2e}.py` | Modify | 更新 `test_surface_sdk.py` 53 符號斷言與 `SnapshotVault` 排除 `.config.local` 斷言；補齊 `FR-01`~`FR-05` 與 `EC-01`~`EC-06` 全量測項 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `secret_field` 置於 `foundation/codec.py`、`HumanRenderable`/`format_output` 下沉至 `execution/runtime/contracts.py`**：維持 6 域 DAG 絕對單向性（Domain 1 `SchemaExporter` 直接讀取 `SECRET_FIELD_METADATA_KEY`、Domain 5 `LocalModuleSlotRegistry` 與 `worker_entry` 直接呼叫 `format_output`，完全零反向匯入 Domain 6）。
- **[P02:DR-02] `MigrationRollbackHandle` 向下相容設計**：令 `migration_rollback_scope()` 產出之 `MigrationRollbackHandle` 同時支援 `handle()`（相容既有 `restore_pre_tx()` 呼叫點）與 `handle.snapshot_module_storage_local(mod_id)`，零破壞既有契約。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# core/foundation/primitives.py
TOOLCHAIN_ENV_ALLOWLIST: Final[frozenset[str]]
def extract_toolchain_env(raw_env: Mapping[str, str]) -> dict[str, str]: ...

# core/foundation/codec.py
SECRET_FIELD_METADATA_KEY: Final[str] = "yscb_secret"
def secret_field(
    *,
    default: object = ...,
    default_factory: object = ...,
    init: bool = True,
    repr: bool = False,
    compare: bool = True,
    metadata: Optional[Mapping[str, object]] = None,
) -> object: ...

# core/foundation/profiler.py
def is_sensitive_key(key: str) -> bool: ...

# core/foundation/proc.py
def build_isolated_python_env(*, include_toolchain_env: bool = False) -> dict[str, str]: ...
class ManagedProcessTree:
    def __init__(
        self, argv: Sequence[str], *, cwd: HostPath, env: Optional[Mapping[str, str]] = None,
        inherit_tty: bool = False, capture_output: bool = False, pipe_stdin: bool = False,
    ) -> None: ...
    @property
    def stdin_pipe(self) -> Optional[BinaryIO]: ...

# core/metadata/config/matrix.py
class ConfigStore:
    def get_module_local_dict(self, module_id: ModuleId) -> JsonObject: ...
    def get_module_redacted_dict(
        self, module_id: ModuleId, *, schema_cls: Optional[type[object]] = None,
    ) -> JsonObject: ...

# core/packaging/installer/engine.py
class MigrationRollbackHandle:
    def snapshot_module_storage_local(self, module_id: ModuleId) -> None: ...
    def restore(self) -> None: ...
    def __call__(self) -> None: ...

# core/execution/lifecycle/engine.py
@dataclass(frozen=True, slots=True)
class StepExecutionResult(Generic[TOut_co]):
    ok: bool; outcome: Optional[TOut_co] = None; error: Optional[ErrorDetail] = None
    preempted: bool = False; coalesced: bool = False; fatal_abort_turn: bool = False
    committed_events: tuple[RawEventRecord, ...] = ()
    rendered_text: Optional[str] = None; exit_code: Optional[int] = None

# core/execution/runtime/contracts.py & wire.py
@runtime_checkable
class HumanRenderable(Protocol):
    def render_text(self) -> str: ...
@runtime_checkable
class ExitCodeProvider(Protocol):
    def exit_code(self) -> int: ...
def format_output(output: object) -> tuple[str, int]: ...

@dataclass(frozen=True, slots=True)
class EncodedStepOutput:
    raw_output: JsonValue
    rendered_text: Optional[str] = None
    exit_code: Optional[int] = None

@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int; stdout: str; stderr: str; duration_ms: float
    timed_out: bool = False; truncated: bool = False
    stdout_bytes: bytes = b""; stderr_bytes: bytes = b""

# BoundTask.execute_encoded_with_presentation(raw_input, ctx, *, include_presentation=False) -> EncodedStepOutput
# InvokeRequest / LocalStepExecutionSpec / WorkerCommandEnvelope: + include_presentation: bool = False, skip_module_init: bool = False
# DaemonRpcInvokeEnvelope: + include_presentation: bool = False
# WorkerStepReply / DaemonRpcInvokeReply / TaskOutcome: + rendered_text: Optional[str] = None, exit_code: Optional[int] = None
# SystemKernelPort / WorkspaceKernel / _LazySdkKernelPort: + scoped_vfs_for_module(module_id: Optional[ModuleId]) -> ScopedVfs

class SpaceClient:
    def resolve_uri(self, space_id: SpaceId | str, rel_path: SpacePath | str) -> SemanticUri: ...
    def match_spaces(self, target: SemanticUri | HostPath | str) -> tuple[SpaceId, ...]: ...

class TaskContext(ABC):
    def run_process(
        self, argv: Sequence[str], *, cwd: Optional[SemanticUri | HostPath | str] = None,
        env: Optional[Mapping[str, str]] = None, input: Optional[str | bytes] = None,
        inherit_toolchain_env: bool = True, timeout_sec: float = 60.0, max_output_bytes: int = 1048576,
    ) -> ProcessResult: ...

# core/surface/bootstrap/system_module.py
@dataclass(frozen=True, slots=True) class SpaceResolveUriInput: space_id: str; rel_path: str
@dataclass(frozen=True, slots=True) class SpaceMatchSpacesInput: target: str
# CoreSystemModule: core.space.resolve_uri -> SemanticUri, core.space.match_spaces -> tuple[SpaceId, ...] (HYBRID, SAFE, PARALLEL, SDK_ONLY)
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 非授權呼叫 `skip_module_init=True` 拋／回傳 `ErrorCode.ACCESS_DENIED`；`format_output` 於 Worker 內拋例外或回傳非法型別轉為 `ErrorCode.BUSINESS_FAILURE` 絕不靜默吞成退出碼 `0`；`run_process` 非法 `input`／`inherit_toolchain_env` 拋 `ValueError`；`SpaceClient.resolve_uri` / `match_spaces` 越界拋 `ACCESS_DENIED` / `SECURITY_GATED`、無效空間拋 `SPACE_NOT_FOUND`。
- **階段決策紀錄**：`[P03:DR-01]` `secret_field` 預設 `repr=False` 防止 Secret 隨 dataclass `repr()` 誤入除錯日誌；`ProcessResult` 保留既有欄位順序並將 `stdout_bytes`/`stderr_bytes` 置於尾端預設 `b""` 維持 100% 位置引數向下相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 與 `[P00:DR-01]` ~ `[P00:DR-05]` 100% 映射覆蓋，無遺漏且嚴格排除 `TODO-35`/`TODO-36`/`TODO-37`。
- [x] **邊界防護**：EC-01 ~ EC-06 涵蓋非法 `skip_module_init`、Windows SQLite 回滾無殘留鎖、大 stdin 防死鎖、非 UTF-8 位元組保留、呈現失敗防 CI 假綠與空間越權攔截。
- [x] **依賴純淨**：全數變更維持 6 域嚴格單向 DAG、零 `Any`、零 `# type: ignore` 與 10 階段 `unplug` 全綠。
- **靈魂拷問與防護解法**：
  1. *若 `secret_field` 回傳型別標註為何才能兼顧 Gate 0 零 `Any` 與 dataclass 靜態檢查？* -> 回傳型別標註為 `object`（或泛型 `_T` 多載），與 `ContribField` / 標準函式零 `Any` 規範一致，並在 `SchemaExporter` 與 `DataclassCodec` 測試驗證零 `Any` 違規。
  2. *Tier 1 冷遷移執行 `@on_migrate` 後若失敗，如何保證 Windows 上 `.storage.local/<mod>/sbom.db` 不會因冷 Worker 尚未退出而 `PermissionError`？* -> `invoke_internal_migration` 走 `FORCE_COLD` 且 `ColdTurnRunner` 於 `finally` 同步等待 `OneShotVenvHost` 回收與 `lifo.close_all()` 完畢後才返回 `TaskOutcome`；外層捕獲例外呼叫 `restore_pre_tx()` 時所有子行程與 FD 均已關閉。
  3. *`COALESCE` 合併中，若背景或 SDK Leader 未設 `include_presentation=True` 而 CLI 跟單者需要呈現怎麼辦？* -> 在 `RuntimeDispatcher` 派發時，凡 `caller_surface == CallerSurface.CLI` 或 `include_presentation=True` 皆附帶計算；且對 CLI 端若 `outcome.exit_code is None` 且 `task_entry.custom_exit_code` 為真，Tier 0 走既有記憶體回退，Tier 1 則明確報錯而非回落退出碼 `0`（熱 Worker 對 `custom_exit_code`/`custom_render` 任務亦可在 `include_presentation=True` 命中，或於 `StepFlight` 允許 `include_presentation` 與 `custom_exit_code` 觸發呈現求值）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **活規格 (Meso)** | `core_v2/sub_module_design/{foundation/foundation,metadata/config,packaging/installer,execution/lifecycle,execution/runtime,surface/sdk,surface/composition_and_bootstrap}.md` | Modify | 1:1 同步 7 份 Active Living Specs 簽名與行為契約 |
| **交接與路線圖** | `core_v2/{ROADMAP,handoff}.md` | Modify | Phase 7 結案時更新 53+38 SDK 與 5 項基建加固成果 |
| **1.x 知識庫** | `docs/<Category>/*.md` | N/A | 嚴守潔淨室邊界不異動 1.x 文檔 |
| **微觀註解** | 受異動之 `core_v2/source/core/core/**/*.py` | Modify | 補齊新增公開契約與安全不變量 Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | Phase 7 結案時追加本計畫高階摘要 |

- **決策定稿**：**[P04:DR-01]** 動刀前派發盲眼 `Pre-Code Analyze Gate` 核對 `[P00:DR-01]`~`[P00:DR-05]`、DAG 邊界與 Gate 0 紅線；通過後分四批次（Domain 1-4 -> Domain 5 -> Domain 6 -> 活規格與測試）實作並執行雙模全 9 套件與 Pre-UX 盲審。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01（Domain 1~4）**：實作 `TOOLCHAIN_ENV_ALLOWLIST` / `extract_toolchain_env`、`build_isolated_python_env(..., include_toolchain_env=False)`、`secret_field` + `SchemaExporter` `writeOnly`/`x-yscb-secret`、`is_sensitive_key`、`redact_cli_args`（涵蓋 `config set --local`）、`ManagedProcessTree(pipe_stdin=...)`；`ConfigStore` `0o600`/`0o700` 與遞迴脫敏查詢（含同型別兄弟巢狀、陣列、動態 Map 與磁碟 `config.schema.json`）、`SnapshotVault` 排除 `.config.local`；`OfflinePackageEngine.migration_rollback_scope()` `MigrationRollbackHandle` 與 `.storage.local/<mod>/` 按需交易快照還原（含 Windows/POSIX 私密檔權限保留與 `0o700` `.temp/`）
- [x] **TASK-02（Domain 5）**：下沉 `HumanRenderable`/`ExitCodeProvider`/`format_output` 至 `execution/runtime/contracts.py`；新增 `EncodedStepOutput` 與 `BoundTask.execute_encoded_with_presentation`；擴充 `ProcessResult(+stdout_bytes, stderr_bytes)`、`TaskContext.run_process(+input, inherit_toolchain_env)`、`SpaceClient.{resolve_uri,match_spaces}`；貫通 `skip_module_init`（冷遷移跳過 `on_init()` 並攔截熱容器／巢狀呼叫）與 `include_presentation`/`rendered_text`/`exit_code`（涵蓋 `StepExecutionResult`、`WorkerStepReply`、`DaemonRpcInvokeReply`、`TaskOutcome`、`LocalModuleSlotRegistry`、`worker_entry`、`step_host`、`dispatcher`，並對非 `HumanRenderable` 避免 RPC 雙倍序列化且保留 `exit_code=0` 區分求值成功與呈現缺席）
- [x] **TASK-03（Domain 6）**：更新 `core.surface.sdk` 匯出 `secret_field`（精確 53 符號）與單向 Re-export；升級 `cli/entrypoint.py` 直接消費 `TaskOutcome.{rendered_text,exit_code}`、`--json` 嚴格剔除呈現鍵並禁止 `custom_exit_code` 缺席靜默回落 `0`；移除 `bootstrap/factory.py` `_resolve_tier1_disk_presentation` 冷子行程與 `_TIER1_FORMAT_SNIPPET`；新增 `scoped_vfs_for_module`（外部預設採保留非模組命名空間 `ModuleId("project")`）；更新 `bootstrap/system_module.py` 遷移快照回滾、`core.config.{list,get,inspect,set}` 全量脫敏（含頂層原義含點鍵相容、無 `--reveal`）與新增無鎖容錯 `core.space.{resolve_uri,match_spaces}`
- [x] **TASK-04（活規格、`Gate 0` 與測試驗證）**：1:1 同步 8 份 Active Living Specs、更新 `test_surface_sdk.py` 53 符號校驗與既有 `SnapshotVault` 測項、補齊 `FR-01`~`FR-05` 與 `EC-01`~`EC-06` 全量測試；經 3 輪零錨定盲眼審查收斂至 `REVIEW_STATUS: PASSED (0 BLOCKER)` 並修復所有 ADVISORY，通過 Linux 標準/`-O` 雙模全 9 套件（`0 ResourceWarning`）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| TASK-01 / 03 | Minor | 同步涵蓋磁碟 `config.schema.json`、`list`/`Mapping`/同型別兄弟巢狀 dataclass 脫敏、`config set --local` 飛行日誌遮罩與 `build_daemon()` 預建 `.config.local/` `0o700` 權限 | 已落實於 `matrix.py`/`profiler.py`/`factory.py` 並補齊回歸測試 |
| TASK-02 | Minor | 以強型別 `EncodedStepOutput` 取代 3 元組滿足 `Gate 0` 規範；非 `HumanRenderable` 僅回填 `exit_code=0` 與 `rendered_text=None` 消除大負載 RPC 雙倍序列化，並兼顧 `Optional[ExitCodeProvider]` 回傳 `None` | 已同步寫入 `execution/runtime.md` 並補測 Tier 1 `Optional[WarmOut]` |
| TASK-03 | Minor | `scoped_vfs_for_module(None)` 改用系統保留非模組 ID `ModuleId("project")` 取代 `"external"`，避免與外部模組碰撞 | 已落實於 `factory.py` |
