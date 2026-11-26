# Core 2.0 跨對話與遠端異步開發交接快照 (`core_v2/handoff.md`)

> **最後更新**：`2026-11-26`
> **當前狀態**：**Wave 1.1 + Wave 1.2 全內核 6 大功能域 + 止血收斂 + 原生可觀測性/效能剖析 + 下游 SDK 雙層門面（52+38）與人體工學重構 + `core_v2/yscb.py` + 18 份正式活規格已 100% 實作完封，並通過 Linux 雙模與 Windows 11 實機全 9 套件驗收（`Completed`），就緒推進 Wave 1.3 (`dev 2.0`) / Wave 2**
> **關聯總路線圖**：[ROADMAP.md](./ROADMAP.md)
> **關聯結案計畫**：[2026_11_25_1630_core_v2_sdk_ergonomics_overhaul](../plans/2026_11_25_1630_core_v2_sdk_ergonomics_overhaul/P07_walkthrough.md)（承接 [2026_11_25_1157_core_v2_observability_profiler](../plans/2026_11_25_1157_core_v2_observability_profiler/P07_walkthrough.md)）
> **封存完整版基線 Tag**：`archive/core-v2-maximalist`（`9847b1a`）

---

## 1. 目前已完成基線（Wave 1.1 + Wave 1.2 微內核、可觀測性與雙層 SDK 門面）

* **內核與啟動器規模**：
  - `core_v2/source/core/core/` 共 **94 支 `.py`、`66,952 LOC`**（100% Python 3.11+ 標準庫、零第三方依賴、零 `Any`、零 `# type: ignore`），另含 `core_v2/source/core/{manifest.json,configurable/config.project.json.tmpl,.yscbignore}` 真實元資料：
    - **Domain 1 `foundation/`**（7 檔，`7,629 LOC`）：`primitives`（值物件、環境白名單、`safe_realpath`）、`errors`（33 碼、`CallCycleError` 指向 `ctx.call()`）、`codec`（`DataclassCodec` + `SchemaExporter`）、`observability`（`StructuredLogger`、跨進程側車鎖 `LogRotator`、`LocaleCatalog`）、`profiler`（ImTK 風格 `Profiler`/`ProfilerSession`/`NullProfiler`/`FlightLogRouter`/`ProfilerRingBuffer`）、`proc`（Job Object / Session+PGID、`ManagedProcessTree(capture_output=True, bufsize=0)` 雙管道與 `close_pipes()`、`read_flight_log_env`）。
    - **Domain 2 `filesystem/`**（21 檔，`11,329 LOC`）：`fs`（`safe_realpath` + Windows `st_reparse_tag` + Watcher 剪枝）、`vfs`（15 協議、雙層 `ReadonlyPolicy`、`VfsEchoGuard`、`ScopedVfs.{open_read,glob,resolve_caller_uri}` 防未折疊符號連結與最深核心掛載外洩）、`storage`（SQLite WAL MVCC + 選配 `profiler` + `BlobVault`）、`space`（SQLite WAL `state.db` `SpaceRegistry`、`SpaceScanner` 選配 `profiler`、`GitignoreMaterializer`）。
    - **Domain 3 `metadata/`**（14 檔，`7,869 LOC`）：`config`（`ModuleManifest` 2.0、2×2 `ConfigStore`、`DeepInfiller`、`SnapshotVault`）、`contributes`（`@dataclass` SSOT、`_schema.json`、5 大合併策略、`ProvenanceGraph`、`ContributesAggregator`）。
    - **Domain 4 `packaging/`**（14 檔，`9,090 LOC`）：`env`（不可變雜湊 `.venv` 池、共享租約與節流 GC）、`installer`（純離線 `OfflinePackageEngine`、RFC 8089 Windows `file://` 校驗、三級 `PurgeLevel`、`UpdateChecker`）。
    - **Domain 5 `execution/`**（22 檔，`17,689 LOC`）：`event`、`lifecycle`、`rpc`、`runtime`（5 段管線、3+1 日誌主權矩陣、三進程 `profiler_tree` 合併、`Empty`/`TaskRef[TIn, TOut]`/`ProcessResult`/`SpaceClient`/6 組強型別系統 `EventMetadata`、`TaskContext.{module_id,spaces,call,resolve_uri,run_process}`、`ProtectedModuleLoader` 唯一具象子類零樣板自動載入）、`daemon`（Stream 1 `daemon/daemon_*.jsonl`、`DaemonStatusSnapshot.profiler_summary`、20ms 雙條件 Racy-Clean `.cache/daemon/core_sig_cache.json` 含 `cache_mtime_ns` 與 `_boot_core_snapshot_ns`）。
    - **Domain 6 `surface/`**（15 檔，`13,343 LOC`）：雙層零反射 SDK 門面——主入口 `core.surface.sdk`（精確 **52 符號**，含協變 `TaskGroup[TModule_co]`/`.module`、`@task(..., equivalence_fn=...)`）與進階子套件 `core.surface.sdk.advanced`（精確 **38 符號**，零交集，含 `YscbClient.call(TaskRef)`、`InMemoryModule`、`format_output`、`Profiler`）；`cli`（零匯入 `tasks.index.json` 路由、`--profile`/`--profile-mem`）；`bootstrap`（`WorkspaceKernelFactory` + `_LazyCliKernelSession` + `CoreSystemModule` 含 4 支無鎖併發讀 `SDK_ONLY` `core.space.{list,status,files,diff}` 與 4 支寫入/掃描任務）。
  - `core_v2/yscb.py`（**`3,386 LOC`**）：100% 純標準庫單檔超薄自舉啟動器。
* **18 份正式活規格（Active Living Specs）**：
  - 全數 18 份活規格（含新建 [surface/sdk_advanced.md](./sub_module_design/surface/sdk_advanced.md)）與實碼維持 1:1 雙向對齊並通過 `Gate 0` 雙向校驗與跨包邊界檢查；僅 [dev/dev.md](./sub_module_design/dev/dev.md) 維持 `Draft — Prototype Design`。
* **雙平台驗證體系與盲審收斂**：
  - [verify_execution_live.py](./verify_execution_live.py) + `core_v2/tests/`（共 12 檔、`27,490 LOC`），涵蓋全部 9 大套件。
  - **Linux 雙模全綠**：全 9 套件標準（`248.35s`）與 `-O`（`278.37s`）全通過（`0 ResourceWarning`）；UX-01 補強 `core_sig_cache` 雙條件 Racy-Clean 後覆驗雙模 `gate0`/`runtime_daemon`/`unplug`/`rc_e2e` 全綠；Pre-Code Analyze Gate 與 Pre-UX 盲眼靜態審查均獲 `PASSED`。
  - **Windows 11 實機全綠（`UX-01` 已簽核 `[測試通過]`）**：Windows 11 `-O` 全 9 大套件 100% 通過（`0 ResourceWarning`），實證覆蓋 Win32 Job Object + `bufsize=0` `ctx.run_process`、大小寫不敏感環境變數、`ScopedVfs.{glob,resolve_caller_uri}`、Tier 0/1 `ctx.spaces.*` 跨進程 E2E 與雙條件 `core_sig_cache` Racy-Clean。
  - 潔淨室隔離護欄：`ys_codebase/source/*`（1.x 主線）與 `.vscode/settings.json` 全程零異動。

---

## 2. 本機拉取驗收指令（Local Acceptance Commands）

1. 拉取雲端同步倉變更：
   ```bash
   python yscb.py gdrive pull
   ```
2. 執行全內核 9 大套件實機驗證（標準模式與 `-O` 模式）：
   ```bash
   python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all
   python -O -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all
   ```

---

## 3. 下次對話建議入口（Pick Next）

1. **推進 Wave 1.3：`dev 2.0` 工具鏈設計定案與實作（主線首選）**：以 [dev/dev.md](./sub_module_design/dev/dev.md) §4 開放議題為起點，拍板 `dev build`、`dev check 2.0` 與跨平台模組測試沙盒（含模組本地單元測試工作台 `TestBench`），落地 `core_v2/source/dev/`。
2. **推進 Wave 2：Tier 0 輕模組移植（`vscode-support` / `agents-workflow` / `gdrive-support`）**：基於已鎖定的 **52+38 雙層 SDK 門面**（`ctx.spaces`、`ctx.call(TaskRef)`、`ctx.resolve_uri`、`ctx.run_process`、零樣板自動載入），將三大 Tier 0 模組純 `Task` 化遷移至 `core_v2/source/`。
3. **排程跟進技術債與歸檔（選配）**：視需要推進 `TODO-32`（`yscb diag`）、`TODO-33`（Daemon 活體現場檢視）、`TODO-34`（CLI 熱轉發 `Bootstrap`/`Launcher` 瘦身）或封存已結案歷史計畫。
