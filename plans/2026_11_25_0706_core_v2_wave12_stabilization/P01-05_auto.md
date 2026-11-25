# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：Core 2.0 Wave 1.2 止血收斂與下游契約補齊計畫  
> 建立日期：2026-11-25  
> 所屬主計畫：無（獨立 Full Track 計畫）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (XHigh)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `manifest.json` 2.0 統一解析與 `ReleaseMeta` 對齊 (`P0-1`) | 於 `metadata.config.manifest` 提供單一權威 `parse_manifest_dict(raw)`，使 `ReleaseMeta` 接受規格鍵 `"type"`（與 `release_type` 相容），`installer/models.py`、`workspace_builtins.py` 與 `system_module.py:758` 統一委派；含 `"release": {"type": ...}` 之已裝模組可被 `discover_installed_manifests_map` 100% 正常辨識。 | P0 | [P00:DR-01] |
| **FR-02** | Domain 2 檔案／空間／儲存四大止血 (`P0-2`~`P0-5`) | ① `space/rules.py` 保留 POSIX 絕對路徑前導 `/` 使 `project://plans/*.md` 等非 `/**` URI 規則正確匹配；② `vfs/mount.py` + `vfs/scoped.py` 檢查所有覆蓋實體路徑之掛載並取最嚴格能力（封堵同址 `project://yscb.py` 覆寫與唯讀別名穿透）；③ 於 `foundation/primitives.py` 定義 `is_disallowed_reparse_tag` 供 `foundation/observability.py` 與 `fs/atomic.py` 共用（同步修正 `yscb.py:311`），於 Windows 僅攔截 `SYMLINK`/`MOUNT_POINT` 放行 OneDrive/WOF；④ `storage/database.py` 依既有 33 碼細分 `SQLITE_BUSY`/`SQLITE_LOCKED` -> `TASK_TIMEOUT`、`IntegrityError`/`ProgrammingError` -> `BUSINESS_FAILURE`（並保持 `SCHEMA_MIGRATION_ERROR` 包裝）與真實磁碟損毀 `STORAGE_CORRUPT`。 | P0 | [P00:DR-01] |
| **FR-03** | Domain 5 並發死鎖與輪詢風暴止血 (`P0-6`~`P0-8`) | ① `runtime/coordinator.py` 佇列中 `COALESCE` Leader 等待晉升及取 OS 鎖時使用 `holder.cancel_token` 與動態 `flight.effective_deadline()`，Leader 取消不波及存活 Follower；② `runtime/{dispatcher,gates}.py` 將 `StepFlight` Step 5 納入 `LifecycleReloadGate` 重入排空豁免並傳動態 deadline，根除 `QUIESCE`↔Step 5 AB-BA 死鎖；③ `daemon/service.py` + `fs/{atomic,watcher}.py` 解除 100ms 輪詢硬上限並預設剪枝 `.git`、`node_modules`、`.venv`、`.cache`、`build`、`dist`、`target`。 | P0 | [P00:DR-01] |
| **FR-04** | Tier 1 `.venv` GC 寬限期與 POSIX 活體保護 (`P0-9`) | `packaging/env/{pool,gc}.py` 提供非破壞性節流更新 `touch_env_last_used(env_dir)` 與共享讀鎖 `acquire_env_shared_lease(pool, env_hash)`；於 `execution/runtime/contracts.py` 定義 DI 回呼 Port（嚴守 `runtime` 禁匯 `packaging`）並由 Domain 6 `bootstrap/factory.py` 注入至 `worker_pool.py`（`HotWorkerPool` 與 `OneShotVenvHost`），確保執行期間持有共享鎖並節流刷新 `last_used_epoch_sec`。 | P0 | [P00:DR-01] |
| **FR-05** | 安全邊界全面鎖緊 (`P0-10` + `CallerMode` + `ScopedVfs`) | ① `core_v2/yscb.py` 為 `init --fix` / `self-update` 補輕量環境守門（阻擋非互動 `AGENT`/`CI`/`NON_TTY` 未授權覆寫，須 `--allow-bootstrap-mutation` 或互動人類 TTY）；② `cli/caller_mode.py` 令顯式 AI Agent 優先於 `CI`（保留 `YSCB_CALLER_MODE=ci` 強制覆寫）、封鎖有 Agent 環境時 `YSCB_CALLER_MODE=human` 降級、收窄過寬前綴避免誤判人類終端，並修正 `test_surface_cli_e2e.py` 清除 `CI*`；③ `vfs/scoped.py` 鎖死非核心模組對 `config.local://` 與 `storage.local://` 之跨模組讀取隔離（僅可讀寫自身 `@/`，保留 `try_get_physical_path(storage.local://)` 空相對路徑供 `ModuleDatabase` 驗界）。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-06** | `core` 自身真實打包元資料落地 | 於 `core_v2/source/core/` 建立符合 2.0 規格之 `manifest.json`、`configurable/config.project.json.tmpl` 與 `.yscbignore`（並確保 `Gate 0` 與現有測試 100% 通過）。 | P1 | [P00:DR-03] |
| **FR-07** | 下游 I/O 與游標契約補齊 | ① `CoreSystemModule` 新增 `core.space.ack_cursor` 系統任務（接受完整 6 欄 CAS 參數 `SpaceAckCursorInput` 薄封裝 `SpaceScanner.ack_cursor()`）；② `ScopedVfs` 公開 `open_read(uri) -> BinaryIO`（復用 `VfsProvider.open_read()` 並受同樣路徑/讀取隔離守門）。 | P1 | [P00:DR-04] |
| **FR-08** | `core.surface.sdk` 契約補齊與 `Module -> TaskGroup` 狀態共享 | ① `core.surface.sdk.__all__` 補齊 `TaskMetadata`、`ClientRoutingPolicy`、`ExecutionPriority`、`JsonValue`，並下沉標準核心事件 ID 與常用系統 DTO 至 `sdk`（由 `bootstrap` 反向重匯出以嚴守 `sdk` 禁匯 `bootstrap` 與 0 重名）；② `TaskGroup.parent_module` 透過 `declarative.py` 內部 WeakKeyDictionary 綁定父 `Module`（0 跨類別私有屬性存取），使 `CoreSystemModule` 拔除 `_ActiveKernelTls`/`_ActiveKernelScope` TLS 繞道（保留 `_SystemKernelRegistry` 供 `factory.py:909` 跨倉查找）。 | P1 | [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `manifest.json` 同時包含 `"type"` 與 `"release_type"`，或含未知鍵 | 拒絕非法鍵（拋 `CONFIG_INVALID`）；接受單一 `"type"` 或 `"release_type"` 並統一轉為 `ReleaseMeta.release_type`。 |
| **EC-02** | 同址工作區下以 `project://yscb.py` 或基礎協議穿透唯讀別名寫入，或第三方模組嘗試讀取 `config.local://gdrive-support/token.json` | 檢驗所有覆蓋實體掛載與跨模組私有命名空間守衛，一律拋出 `READONLY_VIOLATION` / `ACCESS_DENIED`。 |
| **EC-03** | Windows 路徑位於 OneDrive Cloud Files（`0x9000001A`）或 WOF（`0x80000017`）vs 真實 Junction（`0xA0000003`）或 Symlink（`0xA000000C`） | 放行 OneDrive/WOF 重解析點，嚴格攔截 Symlink 與 Mount Point/Junction。 |
| **EC-04** | SQLite 遭遇 `database is locked` (`SQLITE_BUSY`)、`UNIQUE constraint failed` (`IntegrityError`) vs 磁碟檔頭損毀 (`database disk image is malformed`) | `SQLITE_BUSY`/`SQLITE_LOCKED` 對應 `ErrorCode.TASK_TIMEOUT`；`IntegrityError`/`ProgrammingError`/`SQLITE_FULL` 對應 `ErrorCode.BUSINESS_FAILURE`（遷移期間仍包裝為 `SCHEMA_MIGRATION_ERROR`）；僅真實損毀映射為 `ErrorCode.STORAGE_CORRUPT`。 |
| **EC-05** | `COALESCE` 佇列中 Leader 取消而 Follower 仍存活；或全體參與者取消後 `QUIESCE` 抵達 | 存活 Follower 正常完成並取回結果；Step 5 排空在 `QUIESCE` draining 期間正常豁免放行且追蹤動態 deadline，零死鎖。 |
| **EC-06** | `EnvGarbageCollector.collect()` 與運行中 Tier 1 Worker 並發執行 | Worker 持有 `env_<hash>.lock` 共享鎖，GC 非阻塞嘗試獨占鎖失敗後將該環境計入 `skipped_locked` 跳過，零誤刪。 |
| **EC-07** | 容器同時存在 `CI=true` + `ANTIGRAVITY_AGENT=1`，或 Agent 在 PTY 下注入 `YSCB_CALLER_MODE=human`，或人類終端設 `CLAUDE_CODE_USE_VERTEX=1` | 容器 Agent 判為 `AGENT`（保留方言與 `--approve`）；PTY 內 Agent 注入 `human` 遭忽略仍判為 `AGENT`；人類設非 Session 組態鍵不誤判為 `AGENT`。 |
| **EC-08** | 模組無自訂 `TaskGroup` 狀態或使用舊式無參 `TaskGroup`；第三方模組呼叫 `core.space.ack_cursor` 傳入非法 consumer/gen | 舊式無參 `TaskGroup` 100% 向後相容；`ack_cursor` 驗證參數並精準推進單一 consumer 游標。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴與靜態紀律 | 100% Python 3.11+ 標準庫、0 `Any`（`core/`）、Gate 0 17 份活規格 1:1 雙向校驗與 10 階段物理拔除 100% 通過。 |
| **NFR-02** | 雙模與零洩漏 | 標準模式與 `-O` 模式執行 `verify_execution_live.py --suite all`（含本容器 `CI=true` 環境原樣執行）100% 通過且 `0 ResourceWarning`。 |
| **NFR-03** | 潔淨室隔離 | `ys_codebase/source/*` 與根目錄 `.vscode/settings.json` 零異動；不觸及波段 B/C 排除範疇。 |
| **NFR-04** | 跨平台可驗性 | Windows `st_reparse_tag` 邏輯拆分純函式並具完整 Linux 單元模擬測試，確保於本機 Windows 11 實測零語法/邏輯盲區。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` Gate 0 活規格 1:1 剛性約束**：任何修改 `core/` 公開符號、`__all__`、類別方法簽名或預設值，必須同步更新 `core_v2/sub_module_design/` 對應活規格，否則 `test_gate0.py` 立即失敗。
- **`[!NOTE]` 10 階段物理拔除 DAG 約束**：`foundation` 不可匯入 `filesystem`、`filesystem` 不可匯入 `metadata`、`packaging` 不可匯入 `execution`、`execution` 不可匯入 `surface`、`sdk` 不可匯入 `bootstrap`/`cli`。
- **`[!NOTE]` 單次寫檔 150 行上限**：所有編修與測試更新均分段精準套用，避免大塊覆寫。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
Domain 1-2 (底層止血與 I/O 契約)
  foundation/primitives.py        : IO_REPARSE_TAG_SYMLINK/MOUNT_POINT + is_disallowed_reparse_tag(tag)
  foundation/observability.py & fs/atomic.py : 共用 foundation.is_disallowed_reparse_tag 精準放行 OneDrive/WOF
  vfs/mount.py & scoped.py        : iter_covering_mounts() 最嚴格權限 + config.local/storage.local 跨模組讀隔離 + open_read() -> BinaryIO
  storage/database.py             : _stg_translate_db_error 細分 TASK_TIMEOUT / BUSINESS_FAILURE / STORAGE_CORRUPT
  space/rules.py                  : _compile_glob_regex(..., preserve_leading_slash=True) 修正 POSIX URI glob

Domain 3-4 (元資料統一與 Tier 1 環境鎖)
  metadata/config/manifest.py     : 單一 parse_manifest_dict()（ReleaseMeta 支援 type / release_type）
    ├── packaging/installer/models.py 委派復用
    ├── metadata/contributes/workspace_builtins.py 委派復用
    └── surface/bootstrap/system_module.py 委派復用
  packaging/env/{pool,gc}.py      : touch_env_last_used() 節流更新 + acquire_env_shared_lease() 共享讀鎖
  core_v2/source/core/            : manifest.json + configurable/config.project.json.tmpl + .yscbignore

Domain 5 (並發死鎖、輪詢治理與 DI Port)
  runtime/contracts.py & dispatcher.py : contracts.py 定義 EnvLeaseAcquireFn / EnvTouchUsedFn；dispatcher.py 之 DispatcherHostOptions 新增可選 DI 回呼（0 packaging 匯入）
  runtime/coordinator.py          : 佇列 COALESCE Leader 改用 holder.cancel_token & flight.effective_deadline()
  runtime/{dispatcher,gates}.py   : StepFlight Step 5 註冊 draining 重入豁免 + 動態 deadline
  runtime/{worker_pool,turn_session}.py : HotWorkerPool & OneShotVenvHost 透過注入回呼持共享 env 鎖並節流 touch
  daemon/service.py & fs/watcher  : 解除 100ms 輪詢硬上限 + 預設剪枝 .git/node_modules/.venv/.cache/build/dist/target

Domain 6 & yscb.py (安全守門、SDK 狀態共享與下游契約)
  surface/cli/caller_mode.py      : AGENT > CI（YSCB_CALLER_MODE=ci 例外）、禁 Agent 降級 human、精準識別鍵
  surface/sdk/{declarative,__init__}.py : TaskGroup.parent_module (WeakKeyDict) + 下沉系統 DTO/事件常數 + 補齊 4 型別
  surface/bootstrap/{factory,system_module}.py : 注入 packaging.env 回呼至 runtime；拔除 _ActiveKernelScope TLS；新增 core.space.ack_cursor
  core_v2/yscb.py                 : init --fix / self-update 輕量環境守門 (--allow-bootstrap-mutation) + Windows st_reparse_tag
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `core_v2/source/core/core/foundation/{primitives,observability,__init__}.py` | Modify | 下沉 `IO_REPARSE_TAG_SYMLINK`/`IO_REPARSE_TAG_MOUNT_POINT`/`is_disallowed_reparse_tag` 至 `primitives` 並套用於 `observability.py` (`P0-4`) |
| `core_v2/source/core/core/filesystem/fs/{atomic,watcher,__init__}.py` | Modify | `atomic.py` 改用 `foundation.is_disallowed_reparse_tag` (`P0-4`)；`PollingDirectoryWatcher` 補預設忽略目錄 (`P0-8`) |
| `core_v2/source/core/core/filesystem/vfs/{mount,scoped,__init__}.py` | Modify | 新增覆蓋掛載全檢（最嚴格權限贏、`P0-3`）、`config.local://`/`storage.local://` 跨模組讀隔離（保留 `storage.local://` 根目錄 `try_get_physical_path`）與 `ScopedVfs.open_read() -> BinaryIO` (`FR-05`, `FR-07`) |
| `core_v2/source/core/core/filesystem/storage/database.py` | Modify | `_stg_translate_db_error` 與全檔 9 處 `except` 改攔截 `sqlite3.Error`（含 `InterfaceError`），依既有 `ErrorCode` 細分 `TASK_TIMEOUT`/`BUSINESS_FAILURE`/`STORAGE_CORRUPT`，並維持 `_stg_bootstrap_and_migrate` 之 `SCHEMA_MIGRATION_ERROR` 包裝 (`P0-5`) |
| `core_v2/source/core/core/filesystem/space/rules.py` | Modify | URI 座標萬用字元編譯保留 POSIX 前導 `/` (`P0-2`) |
| `core_v2/source/core/core/metadata/config/{manifest,__init__}.py` | Modify | 公開單一 `parse_manifest_dict()` 並使 `ReleaseMeta` 支援 `"type"` 與 `"release_type"` (`P0-1`) |
| `core_v2/source/core/core/metadata/contributes/workspace_builtins.py` | Modify | `discover_installed_manifests_map` 改調用 `parse_manifest_dict()` (`P0-1`) |
| `core_v2/source/core/core/packaging/installer/{models,provider}.py` | Modify | `ins_parse_manifest_dict` 委派 `parse_manifest_dict()` 消除漂移 (`P0-1`)；`provider.py` 補齊 Windows `file://` URI 磁碟機與 UNC 嚴格校驗防止 `nturl2path` 截斷繞過 |
| `core_v2/source/core/core/packaging/env/{pool,gc,__init__}.py` | Modify | 新增 `touch_env_last_used()`、`acquire_env_shared_lease()` 與 `acquire_env_lease_for_python()` (`P0-9`) |
| `core_v2/source/core/core/execution/runtime/{contracts,coordinator,dispatcher,gates,turn_session,worker_pool,__init__}.py` | Modify | `contracts.py` 定義 DI 回呼型別、`dispatcher.py` `DispatcherHostOptions` 接收回呼；修正佇列 `COALESCE` Leader 取消 (`P0-6`)、`QUIESCE`↔Step 5 死鎖 (`P0-7`)，`worker_pool.py` 與 `turn_session.py` 掛載共享 env 鎖與節流 touch (`P0-9`) |
| `core_v2/source/core/core/execution/daemon/service.py` | Modify | 解除 100ms 輪詢硬上限，依設定傳遞合理輪詢間隔與排除集 (`P0-8`) |
| `core_v2/source/core/core/surface/cli/caller_mode.py` | Modify | `AGENT > CI`（`YSCB_CALLER_MODE=ci` 優先）、封鎖 Agent 環境降級 `human`、收窄過寬前綴 (`FR-05`) |
| `core_v2/source/core/core/surface/sdk/{declarative,__init__}.py` | Modify | `TaskGroup.parent_module` 弱引用綁定父 `Module`；匯出 `TaskMetadata`/`ClientRoutingPolicy`/`ExecutionPriority`/`JsonValue` + 系統事件常數與 4 個系統 DTO (`FR-08`) |
| `core_v2/source/core/core/surface/bootstrap/{system_module,factory,__init__}.py` | Modify | `factory.py` 注入 `packaging.env` 租約回呼至 `DispatcherHostOptions`；`system_module.py` 改走 `parse_manifest_dict()`、從 `sdk` 重匯出系統 DTO/事件常數、拔除 `_ActiveKernelScope` TLS（保留 `_SystemKernelRegistry` 供 `factory.py:909`）、新增 `core.space.ack_cursor` (`P0-1`, `P0-9`, `FR-07`, `FR-08`) |
| `core_v2/yscb.py` | Modify | `init --fix` / `self-update` 補齊輕量環境守門（`--allow-bootstrap-mutation`、`P0-10`）與 Windows `st_reparse_tag` 修正 (`P0-4`) |
| `core_v2/source/core/{manifest.json,configurable/config.project.json.tmpl,.yscbignore}` | New | 補齊 `core` 2.0 真實打包元資料 (`FR-06`) |
| `core_v2/sub_module_design/**/*.md` | Modify | 同步所有異動之公開簽名與 `__all__` 至對應 Active Living Specs (`NFR-01`) |
| `core_v2/tests/{_harness,test_foundation_fs,test_vfs_storage_space,test_metadata_packaging,test_runtime_daemon,test_rc_e2e,test_surface_sdk,test_surface_cli_e2e}.py` | Modify | 歸戶補齊 10 項 P0、安全守門、`ack_cursor`、`open_read`、SDK 狀態共享測試、沙盒清除 `CI*` 與 Windows 實測確定性修補 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `Module -> TaskGroup` 狀態共享保持 100% 向後相容且符合 Gate 0**：於 `declarative.py` 內部 `_SdkStateRegistry` 以 `WeakKeyDictionary[TaskGroup, Module]` 綁定每個 `TaskGroup` 實例之父 `Module`，並於 `TaskGroup` 提供唯讀屬性 `parent_module -> Optional[Module]`（0 跨類別私有屬性存取、無參 `TaskGroup()` 零破壞）。`CoreSystemModule` 拔除 `_ActiveKernelTls` / `_ActiveKernelScope` TLS 繞道，改於各 `TaskGroup` 透過 `self.parent_module` 存取 `kernel`（保留 `_SystemKernelRegistry` + `lookup_active_system_kernel` 供 `factory.py:909` 跨倉查找）。
- **[P02:DR-02] `ScopedVfs` 跨模組讀取隔離不破壞 `ModuleDatabase` 驗界**：僅針對 `config.local://` 與 `storage.local://`（含別名終點）強制非核心模組讀寫限定於自身 `@/`（`<module_id>/`）前綴；特例保留 `try_get_physical_path(SemanticUri("storage.local", ""))`（空相對路徑）供 `storage/database.py:128` 計算物理根邊界。
- **[P02:DR-03] `yscb.py` 自舉原語守門統一使用 `--allow-bootstrap-mutation`**：`yscb init --fix` 與 `yscb self-update` 採內嵌輕量偵測（辨識 `AGENT`/`CI`/`NON_TTY`）：非人類互動 TTY 呼叫時預設拒絕並回傳 `security_gated` (`exit 4`)，除非顯式傳入 `--allow-bootstrap-mutation`（非 `--fix` 之空工作區全新 `yscb init` 免攔截）。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# Domain 1: foundation/primitives.py (re-exported in core.foundation.__all__)
IO_REPARSE_TAG_SYMLINK: Final[int] = 0xA000000C
IO_REPARSE_TAG_MOUNT_POINT: Final[int] = 0xA0000003
def is_disallowed_reparse_tag(reparse_tag: int) -> bool: ...

# Domain 2: filesystem/vfs/mount.py & scoped.py
class UriMountTable:
    def iter_covering_mounts(self, host_path: HostPath) -> tuple[tuple[str, SemanticUri], ...]: ...

class ScopedVfs:
    def open_read(self, uri: SemanticUri | str) -> BinaryIO: ...

# Domain 3: metadata/config/manifest.py (re-exported in core.metadata.config.__all__)
def parse_manifest_dict(
    raw: Mapping[str, object],
    *,
    expected_id: Optional[ModuleId] = None,
) -> ModuleManifest: ...

# Domain 4: packaging/env/pool.py (re-exported in core.packaging.env.__all__)
def touch_env_last_used(env_dir: HostPath, *, min_interval_sec: float = 3600.0) -> bool: ...
def acquire_env_shared_lease(pool: ImmutableVenvPool, env_hash: EnvHash) -> Optional[FileLock]: ...
def acquire_env_lease_for_python(pool: ImmutableVenvPool, venv_python: HostPath) -> Optional[FileLock]: ...

# Domain 5: execution/runtime/contracts.py (DI callbacks, 0 packaging imports)
EnvLeaseAcquireFn = Callable[[HostPath], Optional[Callable[[], None]]]
EnvTouchUsedFn = Callable[[HostPath], None]

# Domain 6: surface/sdk (re-exported in core.surface.sdk.__all__ & bootstrap.__all__)
# Added to core.surface.sdk.__all__ (14 symbols):
#   ClientRoutingPolicy, ExecutionPriority, JsonValue, TaskMetadata,
#   WORKSPACE_RELOADED_EVENT_ID, MODULE_INSTALLED_EVENT_ID,
#   MODULE_REMOVING_EVENT_ID, CONFIG_CHANGED_EVENT_ID,
#   SPACE_UPDATED_EVENT_ID_STR, SPACE_REGISTRY_CHANGED_EVENT_ID_STR,
#   SetDynamicSpaceInput, ClearDynamicSpaceInput, SpaceScanInput, SpaceAckCursorInput
class TaskGroup:
    @property
    def parent_module(self) -> Optional[Module]: ...

@dataclass(frozen=True, slots=True)
class SpaceAckCursorInput:
    space: str
    consumer: str
    from_gen: int
    to_gen: int
    config_hash: str
    merkle_root: str
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `storage/database.py`：沿用既有 33 碼，不增新碼：`SQLITE_BUSY`/`SQLITE_LOCKED` $\to$ `ErrorCode.TASK_TIMEOUT`；`IntegrityError`/`ProgrammingError`/`DataError`/`NotSupportedError`/`InterfaceError` 與 `SQLITE_FULL` $\to$ `ErrorCode.BUSINESS_FAILURE`（遷移步驟內仍由 `_stg_bootstrap_and_migrate` 包裝為 `ErrorCode.SCHEMA_MIGRATION_ERROR`）；僅真實檔頭／頁面／磁碟 I/O 損毀 $\to$ `ErrorCode.STORAGE_CORRUPT`。
  - `vfs/scoped.py`：跨掛載覆寫受保護根或唯讀別名拋 `READONLY_VIOLATION`；非核心模組越界讀取他模組 `config.local://` / `storage.local://` 拋 `ACCESS_DENIED`。
  - `yscb.py`：非互動 `AGENT`/`CI`/`NON_TTY` 呼叫 `init --fix` 或 `self-update` 未帶 `--allow-bootstrap-mutation` 時回傳 `security_gated` (`exit 4`)。
- **階段決策紀錄**：`[P03:DR-01]` 所有新增公開符號均嚴守六域單向 DAG 並同步更新對應 Active Living Specs；`sdk` 系統 DTO 與事件常數單點定義於 `sdk`，由 `bootstrap` 重匯出，確保 Gate 0 零重名與 1:1 雙向對齊。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-08 皆已於介面簽名與實作清單完整對齊 `[P00:DR-01]`~`[P00:DR-05]`
- [x] **邊界防護**：EC-01 ~ EC-08 皆具備具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 6 域單向 DAG 與 NFR-01 ~ NFR-04 約束
- **靈魂拷問與防護解法**：
  - *既有測試是否呼叫 `yscb init --fix` 或 `yscb self-update` 於非 TTY 子進程？* 必須核查 `test_surface_cli_e2e.py` 既有呼叫端，對合法自測顯式傳遞授權旗標，並新增負向測試證明預設遭 `AGENT`/`CI` 攔截。
  - *`ScopedVfs` 鎖定 `config.local://` / `storage.local://` 跨模組讀隔離後，會否破壞既有測試？* 必須檢視 `test_vfs_storage_space.py` 與 `test_surface_cli_e2e.py`，確保模組自身 `@/` 讀寫與 `KernelVfs` 全域管理完全通過，並新增跨模組讀取遭拒負向測試。
  - *`PollingDirectoryWatcher` 預設剪枝 `.git` 等目錄會否影響測試將沙盒建於特殊目錄？* 剪枝僅比對**監聽根以下之相對子目錄名**（不誤殺監聽根以上的祖先目錄）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **活規格 (Meso)** | `core_v2/sub_module_design/{foundation,filesystem,metadata,packaging,execution,surface}/*.md` | Modify | 同步新增/調整之公開簽名、`__all__`、安全規則與行為契約 |
| **交接與路線圖** | `core_v2/handoff.md`、`core_v2/ROADMAP.md` | Modify | Phase 7 結案時更新止血收斂成果與 Windows 實測指引 |
| **1.x 知識庫** | `docs/<Category>/*.md` | N/A | 潔淨室邊界不更動 1.x 文檔 |
| **微觀註解** | 受異動之 `core_v2/source/core/core/**/*.py` | Modify | 同步更新新增函式與類別之精準 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | Phase 7 結案時記錄 Wave 1.2 止血收斂摘要 |

- **決策定稿**：**[P04:DR-01]** 嚴格分 4 路正交實作（Domain 1–2、Domain 3–4 + `core` 元資料、Domain 5、Domain 6 + `yscb.py`），每路完成即跑對應分域靶向套件驗證，最後統一通過 `gate0` 與標準/`-O` 雙模 9 套件全量驗收。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：Domain 1–2 止血與契約補齊（`P0-2` POSIX URI glob、`P0-3` VFS 全覆蓋最嚴格掛載、`P0-4` Windows `st_reparse_tag`、`P0-5` SQLite 錯誤細分、`P0-8` Watcher 預設剪枝、`ScopedVfs.open_read()` 與 `config.local://`/`storage.local://` 跨模組讀取隔離）及 `foundation_fs` / `vfs_storage_space` 測試
- [x] **TASK-02**：Domain 3–4 止血與 `core` 真實元資料落地（`P0-1` 統一 `parse_manifest_dict` + `ReleaseMeta` `type` 相容、`P0-9` `touch_env_last_used` 與 `acquire_env_shared_lease`、`core_v2/source/core/` 真實 `manifest.json`/`configurable/`/`.yscbignore`）及 `metadata_packaging` 測試
- [x] **TASK-03**：Domain 5 並發與輪詢止血（`P0-6` 佇列 `COALESCE` Leader 取消、`P0-7` `QUIESCE`↔Step 5 AB-BA 死鎖、`P0-8` Daemon 解除 100ms 硬上限、`P0-9` Tier 1 Worker/OneShot 共享 env 鎖與節流 touch）及 `runtime_daemon` / `rc_e2e` 測試
- [x] **TASK-04**：Domain 6 & `yscb.py` 安全鎖緊與 SDK/系統契約補齊（`P0-10` `yscb.py` 輕量守門、`CallerMode` `AGENT > CI` + 禁降級 + 精準鍵、`core.space.ack_cursor`、SDK 匯出 4 型別/事件 ID/系統 DTO、`Module -> TaskGroup` 狀態共享並拔除 `CoreSystemModule` TLS 繞道）及 `surface_sdk` / `surface_cli_e2e`（清 `CI*`）測試
- [x] **TASK-DOC**：同步更新所有受影響之 `core_v2/sub_module_design/` 活規格與源碼 Docstrings，確保 `gate0`、`unplug` 與標準/`-O` 雙模全 9 套件 100% 通過

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01** | Minor | 併發 4 進程首次開啟全新 `state.db` 時，SQLite `PRAGMA journal_mode = WAL` 會忽略 `busy_timeout` 立即觸發 `SQLITE_BUSY`；另 Pre-UX 盲審補獲 `surface/sdk/client.py:114` 殘留裸 `FILE_ATTRIBUTE_REPARSE_POINT`。 | 於 `storage/database.py:_stg_open_sqlite_conn` 加入先查 `journal_mode` 與 `busy_timeout_ms` 上限內退避重試，並於 `sdk/client.py` 統一套用 `is_disallowed_reparse_tag`。 |
| **TASK-03** | Minor | `LocalModuleSlotRegistry` 與 `HotWorkerPool` 原接收含 `draining` 的 `is_call_gated_for_quiesce`，導致已准入排空中的 Step 5 二波訂閱者在真正卸載前遭 `module_slot.py:945` 拒絶。 | 於 `gates.py` 新增 `is_module_slot_quiesced`（僅於 `quiesced`/`resuming` 回傳 `True`）並同步更新 `dispatcher.py` 與 `runtime.md`。 |
| **TASK-04** | Minor | Pre-UX 盲審發現已初始化工作區呼叫 `yscb init --provider/--yscb-root/--ignore-sha256`（不帶 `--fix`）可繞過自舉守門；另 `core` `manifest.json` 之 `pip_dependencies` 依實碼型別採 `{}`、`entry` 採 `core/__init__.py`。 | 於 `yscb.py:2214` 補齊已初始化覆寫旗標守門與對應負向測試（空工作區全新 `init` 與無參冪等 `init` 維持放行）。 |
| **UX-WIN** | Minor | 本機 Windows 11 實測（`UX-01`）揭露 4 項 Win32 產品瑕疵（`nturl2path.url2pathname` 靜默截斷 `file:///bad:path`、`CreateProcess` 錯誤省略 `venv_python` 路徑、`-B` 無 `.pyc` 下背景 Daemon 冷啟動逾 `3.0s`、動態空間通知 RPC `2000ms` 與 NTFS 耗時碰撞）及 5 項測試跨平台競態（Racy-Clean 20ms 未釘 `mtime`、`os.kill(..., SIGTERM)` 於 Windows 等同 `SIGKILL`、`YscbClient` 首次冷核心初始化逾 `1.5s`、RC-04 `30ms` 盲等、RC-08 `60ms` 鎖排隊逾時）。 | 於 `provider.py`/`yscb.py` 補 RFC 8089 Windows `file://` 校驗、`worker_pool.py` 顯式帶入 `venv_python`、`factory.py` 調整 Windows Daemon 啟動視窗（`10.0s`/`5.0s`）與通知 RPC 逾時（`5000ms`），並於 `test_{vfs_storage_space,surface_cli_e2e,rc_e2e}.py` 與 `_harness.py` 改為確定性斷言；全 9 組套件於 Windows 11 與 Linux 均 100% 通過。 |
| **P07-REV** | Minor | Phase 7 唯讀盲審檢出 `core.space.ack_cursor` 跨模組游標所有權邊界未鎖定，以及 `worker_pool.py:_infer_env_host_dialect` 仍使用寬鬆前綴且未對齊 `YSCB_CALLER_MODE=ci/non_tty` 抑制規則。 | 於 `system_module.py:_verify_fs_ack_cursor_access` 強制非核心模組僅可推進自身 `consumer` 命名空間（越權拋 `ACCESS_DENIED`），於 `worker_pool.py` 改為與 `caller_mode.py` 1:1 對齊之精準鍵與不可變 `MappingProxyType` 排序表，補齊對應正負向測試並獲盲審 `REVIEW_STATUS: PASSED` 及雙模覆驗全綠。 |
