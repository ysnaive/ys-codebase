# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Core 2.0 內核可觀測性、ImTK 風格效能剖析器與 3+1 全 JSONL 日誌體系  
> 建立日期：2026-11-25  
> 所屬主計畫：無（獨立 Full Track 計畫，承接 `TODO-31`）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (XHigh)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元 / 並發測試 | `ProfilerSession`（`scope`/`scope_relative`/分組名、Self/Total 拆帳、`merge_subtree` 去重、首次 Caller 快取、未進入 `_ScopeGuard` 不洩漏堆疊）、`MemoryTrackingGuard` 例外冪等還原、`read_process_rss_kb`、`decode_profiler_snapshot` 畸形/超深降級 `None`、`redact_sensitive_value`/`redact_cli_args` 脫敏不篡改原值、`FlightLogRouter` 3+1 JSONL 落盤/淘汰/沙盒抑制/fail-open、`ProfilerRingBuffer`、`LogRotator` 3 進程並發輪替鎖。 | FR-01, FR-02, EC-02, EC-03, EC-04, EC-05, EC-06, NFR-02 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite foundation_fs` |
| **FT-02** | 整合測試 | `ModuleDatabase`（`Storage/Open`/`Migrate`/`WriteTx`/`ReadSnap`/`Checkpoint`）與 `SpaceScanner`（`Space/Scan`/`WalkFiles`/`HashFiles`/`Commit`/`Diff`/`AckCursor`/`PatchPaths`）選配 `profiler` 埋點與跨元件共用樹巢狀記錄，及預設 `profiler=None` / `NullProfiler` 行為完全一致。 | FR-01, FR-03 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite vfs_storage_space` |
| **FT-03** | 跨進程 / 常駐測試 | 模組日誌遷入 `modules/<mod>.jsonl` 自動注入 `trace_id`/`span_id`/`task_id`/`exec_mode`/`daemon_boot_id` + 脫敏 + `WARN/ERROR` 冒泡 `daily/` `ALERT`；單寫入者主權矩陣（直呼 1 組 `[IN]`/`[OUT]`/`perf/`、`external_flight_owner=True` 0 重複、失敗/超慢附 `error_detail` 與 `runtime_snapshot`）；Tier 1 Worker `profiler_tree` 合併、`profile_mem` 透傳與畸形 `profiler_tree` fail-open 降級；Daemon Stream 1（`daemon/daemon_*.jsonl`）生命週期事件與 `DaemonStatusSnapshot.profiler_summary`。 | FR-02, FR-03, EC-01, EC-04, EC-06, NFR-02 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite runtime_daemon` 與 `--suite rc_e2e` |
| **FT-04** | SDK / CLI 端對端測試 | `core.surface.sdk` 80 符號門面與 `ctx.profiler`/`env.profiler`；冷 `--help` 與未初始化工作區 0 寫盤；`--profile`/`--profile-mem`/`YSCB_PROFILE_MEM=1` 於 `stderr` 渲染 ImTK 樹且 `--json` `stdout` 100% 純淨；前置解析／安全失敗脫敏落盤；CLI → 熱 Daemon → Tier 1 Worker 與 `YscbClient` → 熱 Daemon 完整單寫入者 3 進程合併驗證；巢狀 RPC 不雙計時；`_LazyCliDispatcherProxy` 維持 `allow_conditional`/`DaemonStartInput` 守門；`YSCB_TEST_SANDBOX=1` 抑制與 `_YSCB_FORCE_FLIGHT_LOGS=1` 覆寫。 | FR-02, FR-03, FR-04, EC-01, EC-02, EC-04, EC-05 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite surface_sdk` 與 `--suite surface_cli_e2e` |
| **PT-01** | 效能與 `TODO-31` 基準驗證 | 30 層巢狀 Scope 純計時開銷 `< 0.5ms`；`daemon start --supervisor --json` 僅建置 1 次 `WorkspaceKernel.__init__`（`[True]`，0 次冷核浪費）；`.cache/daemon/core_sig_cache.json` 持久化快取（20ms Racy-Clean 窗口，同時通過 `os.utime()` 不誤觸與同大小改寫必觸交接）加速 `_scan_core_module_tree` 並縮短 `daemon.boot` 耗時。 | FR-05, NFR-01 | `foundation_fs` + `runtime_daemon` + `surface_cli_e2e` 實測基準 |
| **RT-01** | 架構守門與雙模全量回歸 | `Gate 0`（6 域 DAG 含 `core.foundation.profiler` 正負向檢核、全部 17 份 Active Living Specs 1:1 雙向對齊、0 `Any`/`print`/`getattr`/可變全域/工單標籤）、10 階段物理拔除（`unplug`）、Linux 標準與 `-O` 雙模全 9 套件驗證、Pre-UX 唯讀盲審 `REVIEW_STATUS: PASSED` 及 `ys_codebase/source/*` 零異動。 | NFR-02, NFR-03 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all` 與 `-O` 雙模 |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `foundation_fs` 全通過（Linux `0.98s` / `-O` `1.05s`，Windows 11 `2.84s`，`0 ResourceWarning`）；含 ImTK Profiler、未進入 Guard 防漏、脫敏、3+1 路由器、3 進程並發 `LogRotator` 輪替與 `safe_realpath` drive/UNC/Volume 單測。 | 2026-11-25 15:38 |
| **FT-02** | `Passed` | `vfs_storage_space` 全通過（Linux `3.50s` / `-O` `2.73s`，Windows 11 `78.36s`，`0 ResourceWarning`）；驗證 `ModuleDatabase`、`SpaceScanner` 獨立與共用樹埋點、`safe_realpath` 對齊及 `profiler=None` 零回歸。 | 2026-11-25 15:38 |
| **FT-03** | `Passed` | `runtime_daemon`（Linux `14.48s` / `-O` `16.46s`，Windows 11 `23.80s`）與 `rc_e2e` `RC-01~RC-08`（Linux `62.27s` / `-O` `73.48s`，Windows 11 `105.56s`）全通過，`0 ResourceWarning`；驗證 RPC 逾時起點對齊與 3+1 日誌。 | 2026-11-25 15:10 |
| **FT-04** | `Passed` | `surface_sdk`（Linux `1.73s` / `-O` `2.15s`，Windows 11 `12.22s`）與 `surface_cli_e2e`（Linux `157.81s` / `-O` `145.34s`，Windows 11 `572.16s` 較前次 `637.91s` 快 `65.75s`）全通過，`0 ResourceWarning`；驗證 3 進程合併、5 組獨立未物化 `_LazyCliDispatcherProxy` 守門與沙盒覆寫。 | 2026-11-25 15:38 |
| **PT-01** | `Passed` | 30 層巢狀 Scope 計時開銷實測 **`0.1678ms`**（`< 0.5ms`）；`daemon start --supervisor` 僅建置 **1 次** `WorkspaceKernel`（由 2 次降至 1 次）；`core_sig_cache.json` 使 `_scan_core_module_tree` 由 **`62.83ms` 降至 `5.48ms`（11.5x 加速）**、Linux `daemon start --supervisor` 就緒由 **`271.58ms` 降至 `206.58ms`（`-65.0ms`）**、Windows 11 `surface_cli_e2e` 由 `637.91s` 降至 `572.16s`（`-65.75s`）。 | 2026-11-25 15:10 |
| **RT-01** | `Passed` | Linux 標準/`-O` 雙模全 9 套件（`255.31s`/`289.72s`）與 Windows 11 全 9 套件（`gate0` `19.80s`、`foundation_fs` `2.84s`、`vfs_storage_space` `78.36s`、`metadata_packaging` `71.94s`、`surface_sdk` `12.22s`、`surface_cli_e2e` `572.16s`、`runtime_daemon` `23.80s`、`rc_e2e` `105.56s`、`unplug` `7.55s`）全綠（`0 ResourceWarning`）；Pillar 3 修復後 Linux `gate0` `13.63s` + 受影響 5 套件全綠，Pre-UX 與 Phase 7 Pillar 3 唯讀盲審雙雙獲 `REVIEW_STATUS: PASSED`；`ys_codebase/source/*` 零異動。 | 2026-11-25 15:41 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 開發者於本機 Windows 11 主機拉取同步後：(1) 執行 `python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all` 驗證 Win32 `LockFileEx` 輪替鎖、`K32GetProcessMemoryInfo` RSS 讀取、`core_sig_cache.json` 與全 9 套件零回歸；(2) 實機試跑 `python core_v2/yscb.py status --profile` / `--profile-mem` 檢視 `stderr` ImTK 階層耗時樹與 `.cache/logs/{daemon,daily,perf,modules}/*.jsonl` 結構符合直覺預期。 | `[測試通過]` | 開發者於 Windows 11 完成全 9 套件實機驗證（`0 ResourceWarning`），並審閱本機實機產出之 3 進程 `--profile` / `--profile-mem` `stderr` ImTK 瀑布樹與 4 路 JSONL 樣本後簽核「通過」。 |
