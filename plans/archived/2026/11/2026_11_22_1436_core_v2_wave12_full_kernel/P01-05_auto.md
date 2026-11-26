# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：Core 2.0 Wave 1.2 全內核子模組實作、雙盲語境裁決閉環與活規格轉正  
> 建立日期：2026-11-22  
> 所屬主計畫：無（獨立 Full Track 實作計畫）  
> 狀態：Completed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **Wave 1.2a：Domain 1 底座補完與環境變數更名** | 1. 依 `foundation_wave12.md` 擴充 `SemVer4`、`VersionConstraint`、`SemanticUri`、`SpaceId`、`SpacePath`、`SnapshotGen`、`EnvHash` 不可變值物件並接入 `DataclassCodec` 雙向編解碼。<br>2. 於 `ErrorCode` 新增 13 個標準枚舉值；建立 `PUBLIC_ENV_ALLOWLIST` 與 `PRIVATE_ENV_PREFIX = "_YSCB_"`，將 `WORKER_AUTH_ENV_KEY` 統一更名為 `"_YSCB_WORKER_AUTH_TOKEN"` 並確保 `sanitize_caller_env` 依前綴整批剔除。<br>3. 實作純標準庫 JSON Schema Draft 2020-12 導出器 `SchemaExporter`，以及顯式注入之 `LogLevel`、`LogRecord`、`LogRotator`、`StructuredLogger`、`LocaleCatalog`（顯式語系鏈與有界深度 5 插值）與 `SessionTelemetryWriter`。 | P0 | `[P00:DR-01]`<br>`[P00:DR-02]`<br>`[P00:DR-06]` |
| **FR-02** | **Wave 1.2a：Domain 2 檔案、儲存與空間引擎（`vfs` / `storage` / `space`）** | 1. 依 `vfs.md` 實作 `VfsCapabilities(Flag)`、Scheme B 15 組標準協議、`PhysicalDirectoryProvider`、`MemoryVfsProvider`、`UriMountTable`（禁回退 `os.getcwd()`）、雙層 `ReadonlyPolicy`（VFS + OS 唯讀穿隧）、`VfsEchoGuard`（結構滿足 `VfsEchoGuardPort`）、`VfsHub`、`ScopedVfs`（跨模組 `@/` 隔離）與 `KernelVfs`。<br>2. 依 `storage.md` 實作基於 `sqlite3` WAL MVCC 之 `ModuleDatabase`（`SnapshotReader` 零鎖讀 + `WriteTransaction` `BEGIN IMMEDIATE` 序列化寫與取消回滾 + 單向 `SchemaMigration`）與分片內容定址 `BlobVault`，建構期剛性驗證僅放行 `storage.local://`。<br>3. 依 `space.md` 以單一 `state.db` 取代 1.x `YFP2`，實作 `SpaceRegistry`（三源兩趟編譯、`DN-20` 正反向規則對稱、安全子樹剪枝、`compose` 純檔案集差集與持久化動態空間）、`SpaceScanner`（雙階段掃描、多消費者獨立游標與無變動短路）與 `GitignoreMaterializer`（確定性排序與 Zero-Touch）。 | P0 | `[P00:DR-01]`<br>`[P00:DR-02]`<br>`[P00:DR-06]` |
| **FR-03** | **Wave 1.2b：Domain 3 組態擴充域（`config` / `contributes`）** | 1. 依 `config.md` 實作 `ModuleManifest`（`manifest.json` 2.0 十二欄）、2x2 強型別組態矩陣 `ConfigStore`（結構滿足 `ConfigViewPort`、100% 解耦 `project://` 且零向上爬樹）、遞迴缺失鍵補齊 `DeepInfiller` 與智能 `SnapshotVault`（指紋去重、60s 連點折疊保留起點快照、3 份/7 天淘汰，嚴禁納入 `.storage.local/` 與 `.cache/`）。<br>2. 依 `contributes.md` 實作 Python `@dataclass` + `ContribField` 單一真理 `ExtensionPointSpec`、`compile_extension_points`（產出 `_schema.json`）、離帶溯源 `ProvenanceGraph`、五大合併策略（`MERGE`/`EXTEND`/`REPLACE`/`UNIQUE`/`BUCKET_BY_DONOR`，`raw_merged` 零魔術鍵）、同構 `config://<target>/contribute.json` 覆寫、`validate_locale_bundle` 與純記憶體 `ContributesAggregator`。 | P0 | `[P00:DR-01]`<br>`[P00:DR-02]`<br>`[P00:DR-06]` |
| **FR-04** | **Wave 1.2b：Domain 4 純離線套件環境域（`env` / `installer`）** | 1. 依 `env.md` 實作方案 B 不可變雜湊虛擬環境池 `ImmutableVenvPool`（`.venv/<group>_<py_tag>_<hash16>/`、`venv_group` 合取共置、原子 `.staging_*` + `.yscb_env_meta.json`、`--only-binary=:all:`、`_can_symlink()` 降級）、`EnvHealthProbe` 與回滾友善 `EnvGarbageCollector`（7 天 / 每組保留 1 份歷史環境 + 鎖檔跳過容忍）。<br>2. 依 `installer.md` 實作零匯入 `execution` 之純離線引擎 `OfflinePackageEngine`（組合 `ProviderClient` 20MiB/CRC/SHA-256/ZipSlip 防線、`MirrorStore`、`DependencySolver` 同 Major 鎖定與 `index.json` 依賴覆寫、`AtomicPackageDeployer` `configurable/*.tmpl` 整目錄無條件剝離與三階段句柄探針、三級 `PurgeLevel`、`UpdateChecker` 與回報 `UpgradeTransition`）。 | P0 | `[P00:DR-01]`<br>`[P00:DR-02]`<br>`[P00:DR-06]` |
| **FR-05** | **Wave 1.2c：Domain 5 微調、Domain 6 門面組裝與 `core_v2/yscb.py` 自舉** | 1. 依 `sdk_wave12.md` 擴充 `core.surface.sdk` 至 61 個公開符號（保留 Wave 1.1 既有 25 符號零回歸），支援 `Option(group=...)`、`@task(usage_pros, usage_cons)`、`Module.config_type` / `extension_points` / 單一 `@on_migrate`、`ModuleEnv.open_database/open_blob_vault` 自動 LIFO 關閉與 `TaskContext` 5 項注入服務，並完成 `execution/runtime` 四處最小增量接縫（含 `SecurityTier.CRITICAL`）。<br>2. 依 `cli.md` 實作 `compile_tasks_index`、零匯入業務源碼之靜態命令列解析器、1.x 風格 `HelpRenderer`、5 層 `CallerMode`（防 PTY Agent 誤判）、4x3 安全矩陣與兩段式單次確認碼 `ApprovalTokenStore`（綁定 `(task_id, args_hash)` 用過即焚）。<br>3. 依 `composition_and_bootstrap.md` 實作頂層組裝根 `WorkspaceKernelFactory`、全套內建系統管理任務 `CoreSystemModule`（含 `install`/`update`/`remove`/`purge`/`rollback`/`daemon`/`config`/`contributes`/`uri`/`file-lock`/`fs`/`gitignore`/`env` 與套件異動防撕裂閉環）及 100% 純標準庫超薄啟動器 `core_v2/yscb.py`（唯二冷自舉 `init`/`self-update` 與確定性 `core` 還原）。 | P0 | `[P00:DR-01]`<br>`[P00:DR-02]`<br>`[P00:DR-06]` |
| **FR-06** | **Wave 1.2d：逐域拔除驗證、活規格轉正與雙盲語境裁決閉環** | 1. 執行由頂向下逐域拔除測試（Unplug Test），驗證移除上層域時下層功能域單測 100% 獨立通過。<br>2. 將 `foundation_wave12.md` 併入 `foundation.md`、`sdk_wave12.md` 併入 `sdk.md`，並將 `vfs.md`、`storage.md`、`space.md`、`config.md`、`contributes.md`、`env.md`、`installer.md`、`cli.md`、`composition_and_bootstrap.md` 同步轉正為 Active Living Specs 移出 `_DRAFT_SPECS`（僅保留 `dev/dev.md` 於 `_DRAFT_SPECS`），全數接入 `test_gate0.py` 1:1 校驗。<br>3. 每子波次與全域終審執行「雙軌冷眼盲審 -> 輕量語境校準裁決 -> 確定性根因修復」直至 `ACCEPT_FIX == 0` 收斂。 | P0 | `[P00:DR-03]`<br>`[P00:DR-04]`<br>`[P00:DR-05]` |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `project://` 未配置（`!undefined`）、`MountRule` 循環引用、同前綴兄弟目錄（如 `.cache_hack`）或對 `cache://` / `storage://` 開啟 `ModuleDatabase` | 未配置協議確定性拋出帶 `remediation` 之 `URI_UNDEFINED`（絕不回退 `os.getcwd()`）；循環掛載拋 `URI_CYCLE`；成對 `realpath` + `+ os.sep` 攔截越界拋 `ACCESS_DENIED`；非 `storage.local://` 建庫或建 `BlobVault` 立即拋 `ACCESS_DENIED`。 |
| **EC-02** | SQLite WAL 並發讀寫期間遭遇 `cancel_token` 取消、長開讀快照或以舊程式開啟高版本資料庫 | `WriteTransaction` 以 `BEGIN IMMEDIATE` 起事務，取消或異常必 `ROLLBACK` 且不推進世代；`SnapshotReader` 於 `finally` 執行 `ROLLBACK` 釋放讀快照；`db_ver > target_ver` 硬拋 `SCHEMA_MIGRATION_ERROR`。 |
| **EC-03** | 模組包損毀、Zip Slip 路徑穿越、相依版本無交集、離線缺 `.whl` 或跨版 `@on_migrate` 拋出異常 | `ProviderClient` / `MirrorStore` 攔截損毀或越界拋 `PACKAGE_INTEGRITY_ERROR`；無交集拋 `DEPENDENCY_CONFLICT`；離線缺預編譯 Wheel 拋 `ENV_BUILD_FAILED`；任一步（含 `@on_migrate`）失敗立即由 `SnapshotVault.restore_snapshot()` 與鏡像重物化回滾，並於 `finally` 送出 `CONTROL_RESUME` 絕不卡死線上 Daemon。 |
| **EC-04** | AI Agent 運行於 PTY（`isatty() == True`）呼叫 `GATED` 或 `CRITICAL` 任務，或重放／篡改 `--approve=<token>` | 5 層 `CallerMode` 優先識別 Agent 環境變數判為 `AGENT`，絕不阻塞呼叫 `input()`；`GATED` 簽發綁定 `(task_id, args_hash)` 之 300s 單次權杖且驗證通過即焚（重放或改參數必拒）；`CRITICAL` 於非人類終端與非頂層前景呼叫雙層硬阻斷。 |
| **EC-05** | Windows 唯讀位元（`WinError 5`）、開啟中檔案句柄鎖（`WinError 32`）或跨磁碟區暫存替換（`EXDEV`） | `ReadonlyPolicy.authorized_write_tunnel` 於 `finally` 保證重鎖；`ModuleDatabase.close()` 與 `ModuleEnv` LIFO 完整釋放讀寫連線；所有 `.tmp_*` 與 `.staging_*` 強制建於目標同父目錄內。 |
| **EC-06** | 雙軌盲審回報偏離 Core 2.0 減法設計語境之過度防禦建議或內部命名挑剔 | 經輕量語境校準裁決子代理核對 SSOT 標記為 `[REJECT_NITPICK]` 或 `[REJECT_OUT_OF_DESIGN]` 予以駁回，防止無謂代碼膨脹與跨輪修改震盪。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴純淨與單向 DAG | `core 2.0` 全數 6 大功能域與 `core_v2/yscb.py` 100% 僅依賴 Python 3.11+ 標準庫；嚴格通過 `test_gate0.py` 單向匯入白名單與跨套件 `__all__` 邊界檢核。 |
| **NFR-02** | 靜態品質與語意內聚 | 全核心與測試檔 `0 Any`、`0 print`、`0` 未授權反射、`0` 工單噪訊註解；函式與類別依語意聚焦度（SLAP/SRP/CCP）組織，零奈米傳聲筒與零轉發殼。 |
| **NFR-03** | 資源安全與冷自省效能 | 全套 `verify_execution_live.py` 於 `-W error::ResourceWarning` 下 100% 通過（`0 ResourceWarning`）；`surface.cli` 冷啟動 `--help` 與參數解析零匯入業務模組源碼。 |
| **NFR-04** | 活規格 1:1 對齊 | 完成後 `sub_module_design/` 全部正式子模組規格書 100% 通過 `Gate 0` AST 與 Runtime 公開簽名、`__all__`、欄位與常數 1:1 校驗。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` `Gate 0` 全域唯一命名與寬元組規範**：`test_gate0.py` `_build_kernel_ast_index` 對全內核非 `__init__.py` 頂層公開定義執行碰撞檢查，且禁止公開函式簽名出現匿名 3+ 元組（如 `tuple[str, bool, str]`），內部健康檢查等結構應封裝為具名 `@dataclass(frozen=True, slots=True)` 並同步反映於活規格。
- **`[!NOTE]` 離線沙盒環境測試治具**：雲端 VM 無對外網路，測試 `ImmutableVenvPool` 與 `OfflinePackageEngine` 時須以標準庫 `zipfile` 動態合成合法 `.whl` 與模組 `.zip` 於本地 Provider / Wheel Cache 進行真實離線部署驗證。
- **`[!NOTE]` 潔淨室隔離紅線**：全程僅異動 `core_v2/`、`plans/2026_11_22_1436_core_v2_wave12_full_kernel/` 與結案時之 `CHANGELOG.md`，嚴禁觸碰 `ys_codebase/source/*` 與 `.vscode/settings.json`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
core_v2/yscb.py (純 stdlib 薄啟動器: init / self-update / 確定性還原 core -> core.surface.cli.main)
   │
   ▼  Domain 6: surface/ (cli 零匯入 tasks.index.json + 5 層 CallerMode + 4x3 安全守門 | sdk 61 符號門面 | bootstrap WorkspaceKernelFactory + CoreSystemModule)
   │
   ├──► Domain 5: execution/ (runtime 5 段管線 + CRITICAL 守門 + ModuleRuntimeServices 注入 | daemon | rpc | lifecycle | event)
   ├──► Domain 4: packaging/ (installer 純離線套件引擎 + *.tmpl 剝離 -> env 不可變雜湊 .venv 池 + E3-A GC)
   ├──► Domain 3: metadata/  (contributes Python @dataclass SSOT + ProvenanceGraph -> config manifest 2.0 + 2x2 矩陣 + SnapshotVault)
   ├──► Domain 2: filesystem/ (space SQLite WAL 空間與 .gitignore -> storage WAL MVCC + BlobVault -> vfs 15 協議與雙層唯讀 -> fs)
   └──► Domain 1: foundation/ (primitives 含 SemVer4/SemanticUri/SpaceId | errors | codec + SchemaExporter | observability + Logger/Locale/Telemetry | proc)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `core_v2/source/core/core/foundation/{primitives,errors,codec,observability,schema,logging_io,__init__}.py` | Modify / New | 補齊 Wave 1.2 值物件、13 個 `ErrorCode`、環境變數憲法、`SchemaExporter`、`LogRotator`、`StructuredLogger`、`LocaleCatalog` 與 `SessionTelemetryWriter` |
| `core_v2/source/core/core/filesystem/vfs/{capabilities,provider,mount,readonly,echo,scoped,__init__}.py` | New | Scheme B 15 協議、能力遮罩、實體與記憶體 Provider、雙層唯讀守衛、免回音抑制與 `ScopedVfs` / `KernelVfs` |
| `core_v2/source/core/core/filesystem/storage/{database,blob_vault,__init__}.py` | New | SQLite WAL MVCC `ModuleDatabase`（`SnapshotReader`/`WriteTransaction`/`SchemaMigration`）與 `BlobVault`（限 `storage.local://`） |
| `core_v2/source/core/core/filesystem/space/{rules,registry,scanner,gitignore,__init__}.py` | New | 三源兩趟空間編譯、`DN-20` 對稱規則與剪枝、持久化動態空間、WAL 增量掃描游標與 `GitignoreMaterializer` |
| `core_v2/source/core/core/metadata/config/{manifest,matrix,infill,snapshot,__init__}.py` | New | `manifest.json` 2.0、2x2 `ConfigStore`、`DeepInfiller` 與智能 `SnapshotVault` |
| `core_v2/source/core/core/metadata/contributes/{spec,compiler,validator,provenance,aggregator,__init__}.py` | New | `Contributes 2.0` 強型別擴充編譯、離帶 `ProvenanceGraph`、五大合併策略與純記憶體聚合器 |
| `core_v2/source/core/core/packaging/env/{spec,pool,probe,gc,__init__}.py` | New | 方案 B 不可變雜湊 `.venv` 池、健康探針與 E3-A 回滾友善 GC |
| `core_v2/source/core/core/packaging/installer/{models,provider,mirror,solver,deployer,update_checker,engine,__init__}.py` | New | 純離線套件部署引擎、依賴求解、`*.tmpl` 整目錄剝離、三級清理與 12h 更新探測 |
| `core_v2/source/core/core/execution/runtime/{contracts,gates,module_slot,dispatcher,worker_entry,__init__}.py` | Modify | `_YSCB_WORKER_AUTH_TOKEN` 更名、`SecurityTier.CRITICAL`、`CliBindingSpec` `usage_pros/cons` 與模組執行期服務注入接縫 |
| `core_v2/source/core/core/surface/sdk/{declarative,client,__init__}.py` | Modify | 擴充 61 符號對外門面、`@on_migrate`、`Option.group`、`ModuleEnv.open_database` LIFO 與預設記憶體服務回退 |
| `core_v2/source/core/core/surface/cli/{index,caller_mode,approval,parser,help_renderer,entrypoint,__init__}.py` | New | `tasks.index.json` 編譯與零匯入路由、`CallerMode`、兩段式 `--approve` 與 1.x 風格 `HelpRenderer` |
| `core_v2/source/core/core/surface/bootstrap/{factory,system_module,__init__}.py` | New | `WorkspaceKernelFactory` 六域組裝根、Port 轉接與 `CoreSystemModule` 全套系統管理任務 |
| `core_v2/yscb.py` | New | 100% 純標準庫超薄自舉啟動器（`init` / `self-update` / 確定性還原與委派 `core.surface.cli`） |
| `core_v2/tests/{test_gate0,test_foundation_fs,test_vfs_storage_space,test_metadata_packaging,test_surface_sdk,test_surface_cli_e2e,test_runtime_daemon}.py` & `core_v2/verify_execution_live.py` | Modify / New | 新增三大分域測試集、Unplug 拔除驗證與升級全內核 DAG / 活規格 `Gate 0` 守門 |
| `core_v2/sub_module_design/**/*.md`, `core_v2/{ROADMAP,handoff}.md`, `CHANGELOG.md` | Modify / Delete | 合併 `foundation_wave12.md` 與 `sdk_wave12.md`，將全部已實作設計書轉正為 Active Living Specs 並更新變更紀錄 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 頂層組裝根單點跨界轉接**：嚴守 `filesystem` 零匯入 `metadata`、`packaging` 零匯入 `execution`、`execution` 零匯入 `surface`，所有跨功能域協作（如 `Contributes -> UriMountTable / SpaceRegistry`、`SpaceRegistry(/readonly) -> ReadonlyPolicy`、`OfflinePackageEngine -> @on_migrate Task`）唯一收斂於 `core.surface.bootstrap`。
- **[P02:DR-02] 離線測試合成治具策略**：於測試輔助層內建純標準庫最小合法 `.whl`（含 `.dist-info/{METADATA,WHEEL,RECORD}`）與模組 `.zip` 產生器，在不觸發外網請求下 100% 實機跑通 `pip install --no-index --find-links --only-binary=:all:` 與 `yscb.py init / install / update / rollback`。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

各子模組完整公開類別、方法型別簽名與常數定義以 `core_v2/sub_module_design/` 下 11 份凍結設計書為準（不於本節重複貼入程式碼）：
- **Domain 1 (`core.foundation`)**：見 `core_v2/sub_module_design/foundation/foundation.md` + `foundation_wave12.md` §2~§4。
- **Domain 2 (`core.filesystem.{vfs,storage,space}`)**：見 `core_v2/sub_module_design/filesystem/{vfs,storage,space}.md` §3（其中 `UriMountTable.check_health` 回傳元素型別封裝為不可變 `@dataclass(frozen=True, slots=True) class MountHealthEntry(scheme: str, healthy: bool, detail: str)` 以符合 `Gate 0` 禁匿名 3 元組規範）。
- **Domain 3 (`core.metadata.{config,contributes}`)**：見 `core_v2/sub_module_design/metadata/{config,contributes}.md` §3。
- **Domain 4 (`core.packaging.{env,installer}`)**：見 `core_v2/sub_module_design/packaging/{env,installer}.md` §2~§3。
- **Domain 5 & 6 (`core.execution.runtime` 增量 & `core.surface.{sdk,cli,bootstrap}` & `core_v2/yscb.py`)**：見 `core_v2/sub_module_design/surface/{sdk_wave12,cli,composition_and_bootstrap}.md`。

- **錯誤與例外契約 (Error & Exception Contracts)**：所有預期領域失敗統一拋出攜帶結構化 `ErrorDetail(code, message, remediation, source_task)` 之 `YscbError`（含既有 20 碼與 Wave 1.2 新增 13 碼），建構期純值物件格式非法拋出 `ValueError`，協作取消拋出 `TaskCancelledException`。
- **階段決策紀錄**：`[P03:DR-01]` 鎖定 `core.surface.sdk.__all__` 61 個公開符號與磁碟 JSON 格式零偏差，內部返回結構對齊 `Gate 0` 具名不可變 `@dataclass` 規範。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-06 皆已於 11 份設計書與四階段任務清單完整對齊。
- [x] **邊界防護**：EC-01 ~ EC-06 皆具備明確錯誤碼、原子 Staging 與 `finally` 回滾釋放策略。
- [x] **依賴純淨**：100% 符合 NFR-01 ~ NFR-04 純標準庫、單向 DAG 與 `0 ResourceWarning` 約束。
- **靈魂拷問與防護解法**：
  1. *若 `@on_migrate` 拋出異常或進程被取消，是否會導致線上 Daemon 卡在 `QUIESCE` 或留下半升級組態？* -> `CoreSystemModule` 套件異動以 `try...finally` 保證必然發送 `CONTROL_RESUME`，且遷移失敗立即觸發 `SnapshotVault.restore_snapshot()` 與 `OfflinePackageEngine.reload_from_mirror()` 全量回滾。
  2. *不限輪數盲審如何避免過度防禦膨脹？* -> 強制經由輕量語境校準裁決子代理核對 Core 2.0 減法語境，駁回 `[REJECT_NITPICK]` 與 `[REJECT_OUT_OF_DESIGN]`。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | N/A | 1.x 主線文檔維持不變；2.0 架構集中維護於 `core_v2/` |
| **專題手冊** | `core_v2/sub_module_design/**/*.md` & `core_v2/{ROADMAP,handoff}.md` | Modify | 將 Wave 1.2 全部已實作設計書轉正為 Active Living Specs 並更新路線圖與交接狀態 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | N/A | 潔淨室階段不異動 1.x 知識庫，設計不變量均固化於 `core_v2/sub_module_design/` |
| **微觀註解** | `core_v2/source/core/core/**/*.py` & `core_v2/yscb.py` | Modify / New | 補齊無工單噪訊之清晰模組與公開契約 Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 07 結案時記錄 Core 2.0 Wave 1.2 全內核完成摘要 |

- **決策定稿**：**[P04:DR-01]** 規格通過動刀前 `Pre-Code Analyze Gate`，正式依序執行 `TASK-01` ~ `TASK-05`。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01（Wave 1.2a）**：完成 `core.foundation` Wave 1.2 擴充、`_YSCB_WORKER_AUTH_TOKEN` 更名與 `core.filesystem.{vfs,storage,space}` 實作，補齊 `test_vfs_storage_space.py` 並通過實測與雙盲語境裁決閉環。
- [x] **TASK-02（Wave 1.2b）**：完成 `core.metadata.{config,contributes}` 與 `core.packaging.{env,installer}` 實作，補齊 `test_metadata_packaging.py` 並通過實測與雙盲語境裁決閉環。
- [x] **TASK-03（Wave 1.2c）**：完成 `execution.runtime` 四處接縫微調、`core.surface.{sdk,cli,bootstrap}` 與純標準庫 `core_v2/yscb.py` 實作，補齊 `test_surface_cli_e2e.py` 並通過實測與雙盲語境裁決閉環。
- [x] **TASK-04（Wave 1.2d）**：完成跨領域逐層拔除測試（Unplug Test）、合併與轉正 11 份設計書為 Active Living Specs（接入 `test_gate0.py` 1:1 校驗），並通過全內核雙軌終審與全量 `verify_execution_live.py` 回歸。
- [x] **TASK-DOC**：同步更新 `core_v2/ROADMAP.md`、`core_v2/handoff.md`、`CHANGELOG.md` 與產出 `P07_walkthrough.md`，完成雲端受控 CoW 全量同步。

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
## 階段檢查點紀錄（Wave 1.2a ~ Wave 1.2d 全波段收斂完封）
- **TASK-01 (`Wave 1.2a`)**：完成 Domain 1 補完、`_YSCB_WORKER_AUTH_TOKEN` 對齊及 Domain 2 `core.filesystem.{vfs,storage,space}` 全量實作與 `test_vfs_storage_space.py`，通過雙軌盲審與語境裁決閉環（`0/0/0/0 PASSED`）。
- **TASK-02 (`Wave 1.2b`)**：完成 Domain 3 `core.metadata.{config,contributes}` 與 Domain 4 `core.packaging.{env,installer}` 全量實作與 `test_metadata_packaging.py`，通過雙軌盲審與語境裁決閉環（`0/0/0/0 PASSED`）。
- **TASK-03 (`Wave 1.2c`)**：完成 Domain 5 執行服務接縫、Domain 6 `core.surface.{sdk(61 符號),cli,bootstrap}`、`CoreSystemModule`、純標準庫 `core_v2/yscb.py` 與 `test_surface_cli_e2e.py`，通過雙軌盲審與語境裁決閉環（`0/0/0/0 PASSED`）。
- **TASK-04 (`Wave 1.2d`) & TASK-DOC**：完成 10 階段物理拔除驗證 `test_unplug.py`、合併轉正全部 17 份 Active Living Specs 接入 `Gate 0` 雙向校驗與圍欄檢查、通過全域雙軌終審（`0/0/0/0 PASSED`）及標準/`-O` 全量 9 大套件實測（`209.16s` / `232.87s`, `0 ResourceWarning`），並完成 `ROADMAP.md`、`handoff.md`、`CHANGELOG.md` 與 `P07_walkthrough.md` 結案。
