# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Core 2.0 下游模組 SDK 門面雙層收斂與開發人體工學重構  
> 建立日期：2026-11-25  
> 所屬主計畫：無（獨立 Full Track 計畫，為 Wave 1.3 `dev 2.0` 與 Wave 2 下游模組移植之前置門面鎖定）  
> 狀態：Confirmed  
> 模型：Gemini 4 Neon (XHigh)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對 Core 2.0 下游模組實際看到的開發門面進行檢視，確認「現在實作模組是否真正無心智負擔」；將本地單元測試工作台留待 `dev 2.0` 處理，其餘 6 大門面斷層與心智負擔項目全部優先於 Core 2.0 收斂完封。
- **核心目標**：在尚未開始移植任何外部業務模組（零歷史包袱）前，讓 `ast`、`knowledge-db`、`agents-workflow`、`vscode-support`、`gdrive-support` 等下游模組在撰寫時達到真正的低心智負擔與強型別零魔術字串體驗：
  1. 雙層 SDK 分流：`core.surface.sdk` 僅保留業務模組（以 `kdb`/`aw` 實際需求為準線）高頻核心符號；進階／客戶端／底層轉接器（如 `dev` 或外部客戶端所需）收斂至 `core.surface.sdk.advanced`，並清退被 `ctx.spaces` 取代的裸 RPC Input DTO 與字串常數。
  2. 一等強型別空間門面 `ctx.spaces: SpaceClient`（Tier 0/1 透明對稱，底層走單點系統 Task + `core:space_state` 鎖）與強型別系統事件契約（`SPACE_UPDATED_EVENT` 等 6 組 `EventMetadata` + Payload DTO）。
  3. VFS 呼叫者路徑安全橋接 `ctx.resolve_uri(raw_path)`、`ctx.vfs.glob(uri_dir, pattern)`，以及自動綁定 `ctx.cancel_token` 與 Windows `CREATE_NO_WINDOW` 之受管子行程介面 `ctx.run_process(...) -> ProcessResult`。
  4. 跨模組強型別呼叫契約 `TaskRef[TIn, TOut]` 與 `TaskContext` 唯一呼叫入口 `ctx.call(...)`（徹底取代 `invoke_task` / `invoke_typed` 兩套同義詞）。
  5. 模組零樣板與強型別人體工學：`ProtectedModuleLoader` 自動偵測 `module_entry.py` 唯一具象 `Module` 子類（免手寫 `create_module()`，向下相容）、泛型 `TaskGroup[TModule]`、`ctx.module_id` 與 `@task(..., equivalence_fn=...)`。
- **既有組件復用與查重 (Reuse Discovery)**：
  - `SpaceClient` 復用既有 `core.space.{scan,ack_cursor,set_dynamic,clear_dynamic}` 系統任務與 `SpaceScanner`/`SpaceRegistry`，僅補齊 4 支純結構化 SDK-only 系統任務（`core.space.{list,status,files,diff}`）避免剝洋蔥 `SystemResultView`。
  - `ctx.run_process(...)` 直接封裝復用 `core.foundation.proc.ManagedProcessTree`、`sanitize_caller_env` 與 `ctx.cancel_token` 取消回呼，零重造進程樹管理。
  - `ctx.resolve_uri(...)` 直接復用 `ScopedVfs` + `UriMountTable.iter_covering_mounts` 與 `HostPath.resolve_caller_relative`，確保 Tier 0 與 Tier 1 Worker 共用同一套越界/符號連結守門。
  - `ctx.vfs.glob(...)` 直接復用 `ScopedVfs.iter_entries(..., recursive=True)`（自動承接讀隔離與符號連結過濾）。
- **邊界排除 (Explicitly Excluded)**：
  - **本地模組單元測試工作台（TestBench / `MemoryVfsProvider` 封裝）**：明確留待 Wave 1.3 `dev 2.0` 處理。
  - **非 DTO 方法簽名直寫參數 / 通用語意 Request DTO Bags**：明確排除（維持強制 Request DTO 唯一真理，僅保留 `Empty`）。
  - **`@on_event` 新增 `EventBatch` 語法糖**：明確排除（維持無參數 `(self, ctx)` 或顯式 `mapper=`，僅強化報錯指引）。
  - **`ctx.config` 未定型屬性**：明確排除（嚴格型別下無法推導具體配置類型，維持 `ctx.load_config(MyCfg) -> MyCfg`）。
  - **觀測與啟動瘦身待辦（`TODO-32` `yscb diag`、`TODO-33` Daemon 活體檢視、`TODO-34` CLI 熱轉發瘦身）**：獨立排程，不混入本計畫。
  - **`ys_codebase/source/*`（1.x 主線）與 `.vscode/settings.json`**：潔淨室隔離，100% 零異動。
- **架構影響範圍**：
  - Domain 2 `filesystem/vfs/scoped.py`（`glob`、`resolve_caller_uri` 輔助）與 `vfs.md`。
  - Domain 5 `execution/runtime/{contracts,services,module_slot,dispatcher,worker_entry,__init__}.py`（`TaskRef`、`ProcessResult`、`SpaceClient`、`TaskContext.{call,spaces,module_id,resolve_uri,run_process}`、強型別系統事件契約、`ProtectedModuleLoader` 自動偵測 `Module` 子類）與 `runtime.md`。
  - Domain 6 `surface/sdk/{__init__,advanced,declarative,client}.py`（雙層 SDK 拆分、泛型 `TaskGroup[TModule]`、`@task(..., equivalence_fn=...)`）、`surface/bootstrap/system_module.py`（4 支結構化 `core.space.{list,status,files,diff}` SDK-only 系統任務與事件 Payload 復用）與 `{sdk,composition_and_bootstrap}.md`。
  - `core_v2/tests/*`（同步遷移 `ctx.call` 與雙層 SDK 匯入、補齊 Gate 0 雙層活規格校驗與全功能契約/E2E 測試）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] SDK 雙層分流準線（`core.surface.sdk` vs `core.surface.sdk.advanced`）**：以「`knowledge-db` / `agents-workflow` 等下游業務模組日常開發實際需要」為準線留在 `core.surface.sdk` 主入口（含 `Module`, `TaskGroup`, `task`, `on_event`, `periodic`, `on_migrate`, `Arg`, `Option`, `Empty`, `MigrationRequest`, `HumanRenderable`, `ExitCodeProvider`, `TaskContext`, `ModuleEnv`, `TaskRef`, `TaskOutcome`, `ProcessResult`, `SpaceClient`, `define_event`, `EventMetadata`, 6 組強型別系統事件與 3 組 Payload DTO、`ModuleDatabase`, `SchemaMigration`, `BlobVault`, `ScopedVfs`, `SemanticUri`, `HostPath`, `SpaceSpec`, `SpaceDiffBatch`, `SpaceFileEntry`, `SpaceStatusSnapshot`, `SpaceId`, `SpacePath`, `ExtensionPointSpec`, `ContribField`, `MergeStrategy`, `YscbError`, `ErrorCode`, `TaskCancelledException`, `CancellationToken`, `ProgressEvent`, `SecurityTier`, `DispatchMode`, `ConcurrencyMode`）；進階／客戶端／底層轉接器（如 `dev` 工具鏈或外部程式化客戶端所需：`YscbClient`, `InMemoryModule`, `YscbModule`, `TaskMetadata`, `format_output`, `ClientRoutingPolicy`, `ExecutionPriority`, `Profiler*`, `render_profiler_tree`, `SnapshotReader`, `WriteTransaction`, `StorageOpenOptions`, `VfsCapabilities`, `VfsStat`, `HashPolicy`, `SnapshotGen`, `AggregatedContributes`, `ProvenanceGraph`, `StructuredLogger`, `LocaleCatalog`, `LogLevel`, `ErrorDetail`, `JsonValue`, `ModuleId`, `TaskId`, `EventId`, `SemVer4`, `VersionConstraint`, `*_EVENT_ID`）統一拆入 `core.surface.sdk.advanced`；同時清退被 `ctx.spaces` 取代的裸 RPC Input DTO 與舊事件字串常數。
- **[P00:DR-02] 強制 Request DTO 唯一真理、零通用語意 Bags**：拒絕放寬方法參數直寫 CLI 旗標，亦不預置 `ForceInput`/`DryRunInput` 等通用 Bag（僅留 `Empty`），杜絕 1.x 參數發散與半吊子共用 DTO 包袱。
- **[P00:DR-03] 受管子行程高階封裝 (`ctx.run_process`)**：採高階 `ctx.run_process(...) -> ProcessResult` 封裝 `ManagedProcessTree`（自動綁定 `ctx.cancel_token` 取消即整棵終止、Windows `CREATE_NO_WINDOW`、隔離 `env`、強制有界 `timeout_sec` 與輸出截斷上限），不向主 SDK 暴露裸進程句柄，確保生命週期拆卸零洩漏。
- **[P00:DR-04] 統一跨模組呼叫入口 (`TaskContext.call` + `TaskRef`)**：於 `TaskContext` 以 `ctx.call(ref, req)`（亦重載支援 `ctx.call(task_id, input_obj, *, output_type=...)`）徹底取代 `invoke_task` / `invoke_typed`（底層 `RuntimeDispatcher` 簽名維持不動）；`TaskRef[TIn, TOut]` 僅攜帶 `(task_id, input_type, output_type)` 三欄純契約，歸屬 Domain 5 並由 `core.surface.sdk` 單向 Re-export，維持 10 階段 `unplug` 零反向耦合。
- **[P00:DR-05] `@on_event` 維持嚴格批次映射與型別清晰原則**：不新增 `EventBatch` 語法糖，維持無參數 `(self, ctx)` 或顯式 `mapper=`，並強化錯誤訊息明確指引簽名與批次折疊契約；維持 `ctx.load_config(MyCfg) -> MyCfg` 不引入未定型 `ctx.config`。
- **[P00:DR-06] `ProtectedModuleLoader` 無樣板載入安全守門**：載入 `module_entry.py` 時優先呼叫 `create_module()`（100% 向下相容）；若未定義 `create_module`，則僅掃描定義於該入口模組自身（`cls.__module__ == py_mod.__name__`）之具象非抽象 `Module` 子類（且具 `to_yscb_module`），嚴格要求恰好 1 個（0 個或 $\ge 2$ 個皆明確報 `MODULE_DEGRADED`），杜絕掃到外部匯入基類或歧義實例化。

---

## 3. 開放議題與確認紀錄

- [x] **雙層 SDK 分流準線（`kdb`/`aw` 主用留 `sdk`，更深入與 `dev` 歸 `sdk.advanced`）**：已確認（`[P00:DR-01]`）。
- [x] **強制 Request DTO 唯一真理且不預置通用語意 Bags**：已確認（`[P00:DR-02]`）。
- [x] **高階受管子行程 `ctx.run_process(...) -> ProcessResult`**：已確認（`[P00:DR-03]`）。
- [x] **`ctx.call(...)` + `TaskRef` 徹底取代 `invoke_task`/`invoke_typed`、`@on_event` 維持現狀、維持 `ctx.load_config(MyCfg)`**：已確認（`[P00:DR-04]`、`[P00:DR-05]`）。
- [x] **本地單元測試工作台留待 `dev 2.0`**：已確認納入邊界排除。
