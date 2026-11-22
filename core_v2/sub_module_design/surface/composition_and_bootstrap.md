# 子模組架構設計規格：頂層組裝根、內建系統管理 `Task`、`core_v2/yscb.py` 與遠端異步開發交接指引

> **所屬功能域**：`Domain 6 — 對外門面域 (surface/)` + 宿主入口 `core_v2/yscb.py`
> **模組路徑**：`core_v2/source/core/core/surface/bootstrap/`、`core_v2/source/core/core/surface/system_tasks/`、`core_v2/yscb.py`
> **依賴上限（Allowed Imports）**：組裝根與系統 `Task` 允許依賴 `Domain 1 ~ 6`（為全系統唯一跨六域轉接點）；`core_v2/yscb.py` **嚴格僅限 100% Python 3.11+ 標準庫**
> **狀態**：`Draft — Design Frozen for Wave 1.2 Implementation`

> [!NOTE]
> **實作彈性邊界**：本文件鎖定跨六域 Port 轉接拓撲、內建系統管理 `Task` 指令與編排時序、`yscb.py` 雙原語自舉邊界與遠端實作驗收閘門；內部檔案拆分與輔助類別名稱可由實作端微調。

---

## 1. 頂層組裝根（Composition Root — `core.surface.bootstrap`）

依據 [ROADMAP.md](../../ROADMAP.md) §3「消費端定義 Port、組裝根負責轉接」鐵律，底層 5 大功能域彼此嚴格遵守單向 DAG 且零反向匯入，全系統對象組裝唯一收斂於 `core.surface.bootstrap.WorkspaceKernelFactory`：

```text
[host_dir, yscb_root]
   │
   ├── 1. metadata.config.ConfigStore + SnapshotVault  (實作 ConfigViewPort!)
   ├── 2. metadata.contributes.ContributesAggregator   (聚合 uri_schemes / spaces / locales)
   ├── 3. filesystem.vfs: UriMountTable + ReadonlyPolicy + VfsEchoGuard + VfsHub
   │        (VfsEchoGuard 實作 VfsEchoGuardPort!)
   ├── 4. filesystem.storage.ModuleDatabase("storage.local://core/space/state.db")
   ├── 5. filesystem.space: SpaceRegistry + SpaceScanner + GitignoreMaterializer
   │        (將編譯後 /readonly 匹配器回綁至 ReadonlyPolicy!)
   ├── 6. packaging.env.ImmutableVenvPool + packaging.installer.OfflinePackageEngine
   ├── 7. ModuleProviderAdapter (轉接 manifests + EnvPool + tasks.index.json -> ModuleProviderPort!)
   ├── 8. ModuleRuntimeServicesFactory (為各模組生成 ScopedVfs / Logger / Locale / Config / Contributes)
   ├── 9. execution.runtime.RuntimeDispatcher (載入 CoreSystemModule + 已安裝模組)
   └── 10. (Daemon 模式) execution.daemon.WorkspaceDaemon
            (注入 echo_guard, space_watch_roots=SpaceRegistry.collect_watch_roots(),
             config_watch_roots=(config/, .config.local/, yscb.config.json),
             on_space_changed_task=TaskId("core.watcher"),
             on_config_changed_task=TaskId("core.config.on_changed"))
```

### 1.1 四大消費端 Port 轉接契約核對
| Port 介面（定義於 `execution.runtime`） | 具體實作來源 | 組裝根轉接職責 |
| :--- | :--- | :--- |
| **`ConfigViewPort`** | `metadata.config.ConfigStore` | 直接結構滿足（`get_module_value`、`fingerprint`、`reload`），零轉接樣板 |
| **`VfsEchoGuardPort`** | `filesystem.vfs.VfsEchoGuard` | 直接結構滿足（`is_suppressed`），並作為 `DaemonWatcherConfig.echo_guard` 注入 |
| **`ModuleProviderPort`** | `ModuleProviderAdapter`（組裝根薄類別） | 讀取 `ConfigStore` 已安裝模組之 `ModuleManifest`、`ImmutableVenvPool.get_python_executable` 與 `tasks.index.json`，合成 `ModuleDescriptor` 清單（並固定將 `CoreSystemModule` 註冊為內建 Tier 0 模組） |
| **`DaemonSpawner`** | `execution.daemon.SingleFlightDaemonSpawner` | 以 `[sys.executable, str(yscb_py_path), "daemon", "start", "--console"]` 或內核子進程參數建構拉起命令 |

### 1.2 `Core` 內建系統重載聯動（`core.config.on_changed` / `core.watcher`）
- **`core.watcher`（`INTERNAL_TRIGGER`）**：收到 `WorkspaceDaemon` 傳入之 `dirty_paths` 或 `startup_catchup=True` $\to$ 呼叫 `SpaceScanner.patch_paths()`（或 `scan()`） $\to$ 若 `batch.has_changes` 則發射 `core.space_updated` 事件（`UNORDERED`），由 `ast` / `knowledge-db` 訂閱追平。
- **`core.config.on_changed`（`INTERNAL_TRIGGER`）**：組態或模組變更時依序重載 `ConfigStore` $\to$ `ContributesAggregator` $\to$ `UriMountTable` $\to$ `SpaceRegistry` $\to$ 回綁 `ReadonlyPolicy` 匹配器與 `GitignoreMaterializer.sync()` $\to$ 同步更新 `LocaleCatalog`。

---

## 2. 內建系統管理 `Task` 清冊（`CoreSystemModule`）

全數實作為 `core` 模組之宣告式 `Module` + `TaskGroup`，100% 經 `RuntimeDispatcher` 派發；`1 Task = 1 固定 SecurityTier`：

| 指令群 | 子指令 | `SecurityTier` | `DispatchMode` | `SelfMutationScope` | 關鍵編排說明 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`daemon`** | `daemon status` | `SAFE` | `COLD_ONLY` | `NONE` | 透過 `query_daemon_control(CONTROL_STATUS)` 查詢，不續命 TTL |
| | `daemon start [--console\|-d]` | `CONDITIONAL` | `COLD_ONLY` | `NONE` | 單實例鎖啟動 `WorkspaceDaemon`（`-d` 走 `SingleFlightDaemonSpawner`） |
| | `daemon stop [--force]` | `CONDITIONAL` | `COLD_ONLY` | `NONE` | 發送 `CONTROL_STOP` 並回報 `teardown_diagnostics` |
| | `daemon reload [modules...]` | `CONDITIONAL` | `COLD_ONLY` | `NONE` | 發送 `CONTROL_RELOAD` 觸發熱重載或 `core` 交棒 |
| **套件管理** | `list [--remote]` / `status` | `SAFE` | `HYBRID` | `NONE` | 檢視已安裝模組、版本、Tier 與 `.venv` 狀態 |
| | `reload` | `CONDITIONAL` | `COLD_ONLY` | `MUTATES_MODULES` | 依 `QUIESCE -> reload_from_mirror -> RESUME` 重物化與同步 |
| | `install <mod[@ver]...>` | `GATED` | `COLD_ONLY` | `MUTATES_MODULES` / `MUTATES_CORE` | 完整編排見 §2.1（支援 `--provider`/`--force`/`--offline`/`--ignore-sha256`） |
| | `update [mods...]` | `GATED` | `COLD_ONLY` | `MUTATES_MODULES` / `MUTATES_CORE` | 同 Major 鎖定升級 + `core` 先行 + 相依交集自癒 |
| | `restore` | `GATED` | `COLD_ONLY` | `MUTATES_MODULES` | 依 `yscb.config.json` 還原全模組（含 `pruned` 同三元組補位） |
| | `remove <mods...> [--clean]` | `GATED` | `COLD_ONLY` | `MUTATES_MODULES` | 卸載模組（保留 `config://` & `storage://`），自動清動態空間與 `.gitignore` |
| | `purge <mods...>` | **`CRITICAL`** | `COLD_ONLY` | `MUTATES_MODULES` | **獨立高危任務**：卸載並永久清除五大資料空間（限人類互動終端確認） |
| | `rollback [snap_id]` | **`CRITICAL`** | `COLD_ONLY` | `MUTATES_CORE` | **獨立高危任務**：還原 `SnapshotVault` 並由不可變鏡像重物化（限人類終端） |
| **組態擴充** | `config list\|get\|inspect` | `SAFE` | `HYBRID` | `NONE` | 讀取 2×2 組態矩陣與型別 Schema 說明 |
| | `config set\|unset\|reload` | `CONDITIONAL` | `HYBRID` | `NONE` | 寫前 Schema 驗證、單檔原子寫入並發射 `core.config_changed` |
| | `contributes list\|check\|inspect` | `SAFE` | `HYBRID` | `NONE` | 零匯入自省、`Strict Egress` 校驗與 `--provenance` 溯源檢視 |
| **URI／唯讀** | `uri list\|resolve\|to-uri\|check` | `SAFE` | `HYBRID` | `NONE` | 檢視 Scheme B 15 協議與模組自訂協議健康狀態 |
| | `file-lock status` | `SAFE` | `HYBRID` | `NONE` | 診斷 `/readonly` 空間與單檔 OS 唯讀鎖狀態 |
| | `file-lock sync\|lock` | `CONDITIONAL` | `HYBRID` | `NONE` | 同步施加 OS 唯讀屬性 |
| | `file-lock unlock` | `GATED` | `HYBRID` | `NONE` | 緊急維護解除受管唯讀鎖 |
| **空間／忽略** | `fs spaces\|match\|ls\|hash\|status\|diff` | `SAFE` | `HYBRID` | `NONE` | SQLite WAL 唯讀快照查詢與規則來源診斷 |
| | `fs scan\|clean` / `gitignore sync` | `CONDITIONAL` | `HYBRID` | `NONE` | 執行增量掃描、清游標或手動同步 `project://.gitignore` |
| | `gitignore status` | `SAFE` | `HYBRID` | `NONE` | 檢視各模組 `# [<owner>]` 分組忽略規則 |
| **虛擬環境** | `env list\|check [--deep]` | `SAFE` | `HYBRID` | `NONE` | 檢視 `.venv` 池狀態、快檢或子進程深檢 |
| | `env repair\|gc [--all]` | `CONDITIONAL` | `COLD_ONLY` | `NONE` | 修復損毀環境或執行孤兒環境回收 |


### 2.1 套件異動標準編排時序（`install` / `update` / `restore` / `remove` / `purge` / `rollback`）
所有改變 `.modules/` 或組態矩陣之內建系統 `Task` 統一執行以下防撕裂閉環：
1. **前置守門**：確認為頂層前景冷呼叫（`COLD_ONLY` + `SelfMutationScope`），取得跨進程 `.cache/locks/installer.lock` 排他鎖。
2. **通知線上 Daemon 全域靜默**：若探測到線上 Daemon，發送 `CONTROL_QUIESCE(lease_sec=...)` 排空非核心在途任務（`finally` 中必然發送 `CONTROL_RESUME`，若更新了 `core` 則觸發 Daemon 自重啟交棒）。
3. **移除前置事件（僅 `remove` / `purge`）**：先向將卸載之模組發射 `MODULE_REMOVING_EVENT_ID`（`ORDERED`），並呼叫 `SpaceRegistry.clear_dynamic_spaces(mod)` 清除其動態空間。
4. **純離線套件引擎執行**：委派 `packaging.installer.OfflinePackageEngine` 完成 `SnapshotVault` 保護快照 $\to$ 依賴求解 $\to$ 下載校驗 $\to$ Tier 1 `.venv` 建置 $\to$ Staging 物化與 `*.tmpl` 整目錄剝離 $\to$ 原子目錄替換。
5. **跨版資料遷移 `Task` 派發**：依 `DeploymentReport.transitions` 中 `is_upgrade == True` 且目標模組宣告 `@on_migrate` 者，經 `RuntimeDispatcher` 派發內部遷移任務（帶 `MigrationRequest(old_version, new_version)`）；**任一遷移失敗立即觸發 `SnapshotVault.restore_snapshot()` 與鏡像重物化回滾**。
6. **收尾同步與通知**：重建 `.cache/tasks.index.json`、重載 `ContributesAggregator` / `SpaceRegistry`、執行 `GitignoreMaterializer.sync()` 與 `ReadonlyPolicy.sync_files()`、執行 `EnvGarbageCollector.collect()`、發射 `MODULE_INSTALLED_EVENT_ID` / `WORKSPACE_RELOADED_EVENT_ID`，最後釋放 `installer.lock` 並 `CONTROL_RESUME` 喚醒 Daemon。

### 2.2 供下游模組呼叫之內核空間寫入系統 `Task`（`SDK_ONLY`）
- `core.space.set_dynamic(owner, name, spec)` / `core.space.clear_dynamic(owner, name=None)`：檢核呼叫來源模組僅能修改自身 `owner`，寫入 `storage.local://core/space/state.db` 後立即觸發 `.gitignore` / `/readonly` 同步並發射 `core.space_registry_changed`。

---

## 3. `core_v2/yscb.py` 超薄自舉啟動器規格

延續 1.x Thin Host 紀律（`DN-12`, `DN-14`），`core_v2/yscb.py` 維持 100% Python 3.11+ 純標準庫單檔腳本（目標精簡於 400–600 行），嚴禁堆疊任何業務邏輯：

1. **唯二無依賴冷自舉原語**：
   - `yscb init [--provider=<url_or_path>] [--yscb-root=<rel>] [--fix]`：建立或修復 `yscb.config.json`，向 Provider 探測並下載驗證 `core` 套件（SHA-256 + CRC + Zip Slip），原子物化至 `.modules/core/`。
   - `yscb self-update [--url=<url>] [--sha256=<hex>] [--ignore-sha256]`：使用與 `DEFAULT_PROVIDER_URL` 物理獨立之 `DEFAULT_SELF_UPDATE_URL`（指向 `releases` 孤兒分支），驗證伴隨 `.sha256` 與 AST 結構完整性後原子替換自身 `yscb.py`。
2. **新環境缺失 `.modules/core` 確定性自舉還原（`DN-12`, `DN-14`）**：
   - 當 `yscb.config.json` 存在但 `.modules/core` 缺失（或版本不健康）時，嚴格依組態中的確定性 `provider` 與 `installed_modules["core"]["version"]`（支援 `pruned` 同三元組最高 `active` 補位並同步更新 `yscb.config.json`）拉取還原 `core`。
   - **零盲猜紅線**：探測或來源失敗時明確印出修復指引並退出，**嚴禁硬編碼預設版本號或私自 fallback 至官方遠端 URL**。
3. **100% 委派微內核**：
   - 其餘所有指令（包含 `yscb --help`、`daemon`、`install` 與全部業務模組指令），僅將 `{yscb_root}/.modules/core` 置於 `sys.path` 首位（絕不注入任何業務模組或 `.venv` 至宿主進程），傳入顯式 `(argv, host_dir, yscb_root)` 呼叫 `core.surface.cli.main(...)` 並原樣透傳退出碼。

---

## 4. 遠端異步實作交接指引與分波出場閘門（Wave 1.2 Implementation Guide）

> [!IMPORTANT]
> **給遠端異步開發者／代理的總綱**：
> 1. **強制統一邊界**：`core.surface.sdk`（[sdk.md](./sdk.md) + [sdk_wave12.md](./sdk_wave12.md)）、磁碟與 JSON 檔案格式（`manifest.json` 2.0、`tasks.index.json`、`contributes/_schema.json`、`config.schema.json`、`*.tmpl`、`yscb.config.json`）、六域單向 DAG 與環境變數憲法必須嚴格遵循。
> 2. **內部調整彈性**：各子模組內部檔案切分、私有輔助類別與非 SDK 內部方法簽名可依實際開發情況適度微調，無須機械拘泥草案中每一條內部 helper 簽名。
> 3. **潔淨室與零回歸紅線**：全程僅修改 `core_v2/` 內檔案，**嚴禁修改 `ys_codebase/source/*` 1.x 主線或 `.vscode/settings.json`**；每個子波段結束必須跑通既有 `python -B -W error::ResourceWarning core_v2/verify_execution_live.py`（`0 ResourceWarning`、`0 Any`）。

### 建議分波實作順序（嚴格沿單向 DAG 由底向上）
| 子波段 | 實作範圍與對應設計書 | 本波段出場驗收門檻 |
| :---: | :--- | :--- |
| **Wave 1.2a** | **Domain 1 補完 + Domain 2 剩餘**<br/>• [foundation_wave12.md](../foundation/foundation_wave12.md)<br/>• [vfs.md](../filesystem/vfs.md)、[storage.md](../filesystem/storage.md)、[space.md](../filesystem/space.md) | • 補齊 `core_v2/tests/test_vfs_storage_space.py` 並接入 `verify_execution_live.py --suite`<br/>• 驗證 `storage.local://` 能力守門、WAL 並發零鎖讀寫、動態空間與 `.gitignore`、`_YSCB_WORKER_AUTH_TOKEN` 更名 |
| **Wave 1.2b** | **Domain 3 (`metadata`) + Domain 4 (`packaging`)**<br/>• [config.md](../metadata/config.md)、[contributes.md](../metadata/contributes.md)<br/>• [env.md](../packaging/env.md)、[installer.md](../packaging/installer.md) | • 補齊 `core_v2/tests/test_metadata_packaging.py`<br/>• 驗證 `Contributes 2.0` Python SSOT 與 `_schema.json` 等價、3 份／7 天／60s 智能 `SnapshotVault`、`*.tmpl` 零殘留剝離、`ImmutableVenvPool` 與 E3-A 回滾友善 GC |
| **Wave 1.2c** | **Domain 5 微調 + Domain 6 (`sdk`/`cli`/`bootstrap`) + `core_v2/yscb.py`**<br/>• [sdk_wave12.md](./sdk_wave12.md)、[cli.md](./cli.md)、本文件 | • 補齊 `core_v2/tests/test_surface_cli_e2e.py`<br/>• 驗證 `yscb.py init` $\to$ `install` $\to$ `daemon` $\to$ `@on_migrate` $\to$ `rollback` 端到端閉環、`CallerMode` PTY 偵測、4×3 安全矩陣與兩段式 `--approve=<tok>` |
| **Wave 1.2d** | **逐域拔除測試（Unplug Test）與 Gate 0 活規格轉正** | • 依序驗證各上層域可獨立拔除且底層單測全綠<br/>• 將各 `Draft` 規格依最終實作同步為 `Active Living Spec`（`foundation_wave12.md` 併入 `foundation.md`、`sdk_wave12.md` 併入 `sdk.md`）並由 `_DRAFT_SPECS` 移入 `test_gate0.py` `pairs` 1:1 校驗，全量套件全綠通過 |
