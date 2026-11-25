# Core 2.0 跨對話與遠端異步開發交接快照 (`core_v2/handoff.md`)

> **最後更新**：`2026-11-25`
> **當前狀態**：**Wave 1.1 + Wave 1.2 全內核 6 大功能域 + 止血收斂 + 內核可觀測性/ImTK 效能剖析器與 3+1 JSONL 日誌體系 + `core_v2/yscb.py` + 17 份正式活規格已 100% 實作完封，並通過 Linux 雙模與 Windows 11 實機全 9 套件驗收及 Phase 7 Pillar 3 唯讀盲審（`Completed`），就緒推進 Wave 1.3 (`dev 2.0`) / Wave 2**
> **關聯總路線圖**：[ROADMAP.md](./ROADMAP.md)
> **關聯結案計畫**：[2026_11_25_1157_core_v2_observability_profiler](../plans/2026_11_25_1157_core_v2_observability_profiler/P07_walkthrough.md)（承接 [2026_11_25_0706_core_v2_wave12_stabilization](../plans/2026_11_25_0706_core_v2_wave12_stabilization/P07_walkthrough.md)）
> **封存完整版基線 Tag**：`archive/core-v2-maximalist`（`9847b1a`）

---

## 1. 目前已完成基線（Wave 1.1 + Wave 1.2 微內核與原生可觀測性）

* **內核與啟動器規模**：
  - `core_v2/source/core/core/` 共 **93 支 `.py`、`65,954 LOC`**（100% Python 3.11+ 標準庫、零第三方依賴、零 `Any`、零 `# type: ignore`），另含 `core_v2/source/core/{manifest.json,configurable/config.project.json.tmpl,.yscbignore}` 真實元資料：
    - **Domain 1 `foundation/`**（7 檔，`7,582 LOC`）：`primitives`（含值物件、`PUBLIC_ENV_ALLOWLIST` + `YSCB_PROFILE_MEM` + `_YSCB_*`、`FORCE_FLIGHT_LOGS_ENV_KEY` 與跨平台 `safe_realpath`）、`errors`（33 碼）、`codec`（`DataclassCodec` + `SchemaExporter`）、`observability`（`StructuredLogger`、跨進程 `fcntl.flock`/Win32 `LockFileEx` 側車鎖 `LogRotator`、關聯鍵擴充 `LogRecord`、`LocaleCatalog`）、`profiler`（ImTK 風格 `Profiler`/`ProfilerSession`/`ProfilerNodeSnapshot`/`NullProfiler`、`MemoryTrackingGuard`、`ProfilerRingBuffer`、`FlightLogRouter`、脫敏器、`render_profiler_tree`、`read_process_rss_kb`）、`proc`（Job Object / Session+PGID、`read_flight_log_env`）。
    - **Domain 2 `filesystem/`**（21 檔，`11,105 LOC`）：`fs`（`safe_realpath` 全覆蓋 + Windows `st_reparse_tag` + Watcher 剪枝）、`vfs`（15 協議、雙層 `ReadonlyPolicy`、`VfsEchoGuard`、`ScopedVfs.open_read()`）、`storage`（SQLite WAL MVCC + 選配 `profiler` 埋點 + `BlobVault`）、`space`（SQLite WAL `state.db` `SpaceRegistry`、`SpaceScanner` 選配 `profiler` 埋點、`GitignoreMaterializer`）。
    - **Domain 3 `metadata/`**（14 檔，`7,869 LOC`）：`config`（`ModuleManifest` 2.0、2×2 `ConfigStore`、`DeepInfiller`、`SnapshotVault`）、`contributes`（`@dataclass` SSOT、`_schema.json`、5 大合併策略、`ProvenanceGraph`、`ContributesAggregator`）。
    - **Domain 4 `packaging/`**（14 檔，`9,090 LOC`）：`env`（不可變雜湊 `.venv` 池、`safe_realpath`、共享租約與節流 GC）、`installer`（純離線 `OfflinePackageEngine`、`safe_realpath`、RFC 8089 Windows `file://` 校驗、三級 `PurgeLevel`、`UpdateChecker`）。
    - **Domain 5 `execution/`**（22 檔，`17,095 LOC`）：`event`、`lifecycle`、`rpc`、`runtime`（5 段管線、單寫入者 3+1 日誌主權矩陣、`CLI → Daemon → Tier 1 Worker` 三進程 `profiler_tree` 合併、`modules/<mod>.jsonl` 關聯鍵與 `WARN/ERROR` `ALERT` 冒泡、`invoke_daemon_rpc` 於 `daily/[IN]` 後起算 `DeadlineGuard`）、`daemon`（Stream 1 `daemon/daemon_*.jsonl`、`DaemonStatusSnapshot.profiler_summary`、20ms Racy-Clean `.cache/daemon/core_sig_cache.json` `11.5x` 啟動掃描加速）。
    - **Domain 6 `surface/`**（14 檔，`13,210 LOC`）：`sdk`（**80 符號**零反射門面 + `TaskContext.profiler`/`ModuleEnv.profiler` + `TaskGroup.parent_module` + `YscbClient` 單寫入者）、`cli`（零匯入 `tasks.index.json` 路由、`--profile`/`--profile-mem` 旗標且 `--json` `stdout` 100% 純淨、5 層 `CallerMode`）、`bootstrap`（`WorkspaceKernelFactory` + `_LazyCliKernelSession`/`_LazyCliDispatcherProxy` 單次建核快啟與 Stage-1 守門完整對齊 + `CoreSystemModule`）。
  - `core_v2/yscb.py`（**`3,386 LOC`**）：100% 純標準庫單檔超薄自舉啟動器（紀錄 `boot_start_ns` 銜接 `Bootstrap/Launcher` 耗時、非人類環境覆寫守門與確定性 `.modules/core` 還原）。
* **17 份正式活規格（Active Living Specs）**：
  - 全數 17 份活規格與實碼維持 1:1 雙向對齊並通過 `Gate 0` 靜態／執行期校驗與圍欄衛生檢查；僅 [dev/dev.md](./sub_module_design/dev/dev.md) 維持 `Draft — Prototype Design`。
* **雙平台驗證體系與盲審收斂**：
  - [verify_execution_live.py](./verify_execution_live.py) + `core_v2/tests/`（共 13 檔、`26,779 LOC`），涵蓋全部 9 大套件（`gate0`、`foundation_fs`、`vfs_storage_space`、`metadata_packaging`、`surface_sdk`、`surface_cli_e2e`、`unplug`、`runtime_daemon`、`rc_e2e`）。
  - **Linux 雙模與 Pillar 3 複驗全綠**：全 9 套件標準（`255.31s`）與 `-O`（`289.72s`）全通過；Pillar 3 修復後覆驗 `gate0`、`foundation_fs`、`vfs_storage_space`、`metadata_packaging`、`surface_cli_e2e`、`unplug` 全綠（`0 ResourceWarning`）；Pre-UX 與 Phase 7 Pillar 3 唯讀盲審雙雙獲 `REVIEW_STATUS: PASSED`。
  - **Windows 11 實機全綠（`UX-01` 已簽核）**：全 9 大套件（含 `surface_cli_e2e` `572.16s` 較前次快 `65.75s`、`rc_e2e` `105.56s`、`unplug` `7.55s`）於 Windows 11 原生環境 100% 通過（`0 ResourceWarning`），且 `--profile`/`--profile-mem` 瀑布樹與 3+1 JSONL 實機樣本經開發者審閱簽核。`TODO-31` 已完封，`yscb diag` CLI UX 已延後登錄 `TODO-32`。
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

1. **推進 Wave 1.3：`dev 2.0` 工具鏈設計定案與實作（主線首選）**：以 [dev/dev.md](./sub_module_design/dev/dev.md) §4 開放議題為起點，拍板 `dev build`、`dev check 2.0` 與跨平台模組測試沙盒，落地 `core_v2/source/dev/`。
2. **推進 Wave 2：Tier 0 輕模組移植（`vscode-support` / `agents-workflow` / `gdrive-support`）**：基於已鎖定的 80 符號 `core.surface.sdk` 公開門面與內建 `ctx.profiler` / 3+1 日誌體系，將三大 Tier 0 模組純 `Task` 化遷移至 `core_v2/source/`。
3. **排程跟進技術債與歸檔（選配）**：視需要推進 `TODO-32`（`yscb diag <perf|logs|inspect|bundle>` 診斷 UX）、`TODO-30` 或封存已結案之 `core_v2` 歷史計畫。
