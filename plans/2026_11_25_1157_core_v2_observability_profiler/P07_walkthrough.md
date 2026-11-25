# 成果展示與結案報告 (Walkthrough)

> 功能名稱：Core 2.0 內核可觀測性、ImTK 風格效能剖析器與 3+1 全 JSONL 日誌體系  
> 建立日期：2026-11-25  
> 所屬主計畫：無（獨立 Full Track 計畫，承接 `TODO-31`）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (XHigh)  

> 模板版本：v1.4

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  - **ImTK 風格零全域階層剖析器 (`core/foundation/profiler.py`)**：參考 `ImTKProfiler.cs` 以 100% 純標準庫落地實例級 `Profiler` / `ProfilerSession` / `ProfilerNodeSnapshot` / `NullProfiler`（`scope`、`scope_relative`、Self/Total 拆帳、`merge_subtree`、首次 Caller 快取，30 層計時開銷實測 **`0.1678ms`** `< 0.5ms`）、`MemoryTrackingGuard`（`tracemalloc` 冪等還原）、跨平台 `read_process_rss_kb`（含 Win32 `K32GetProcessMemoryInfo`）、限深/限節點 fail-open `decode_profiler_snapshot` 與脫敏器 `redact_sensitive_value`/`redact_cli_args`。
  - **3+1 全 JSONL 運行日誌體系與跨進程合併**：淘汰 `SessionTelemetryRecord`/`SessionTelemetryWriter`，於 `.cache/logs/` 落地 4 路統一關聯（`trace_id` + `daemon_boot_id`）日誌：Stream 1 `daemon/daemon_<ts>_<pid>_<boot8>.jsonl`、Stream 2 `daily/YYYY-MM-DD.jsonl`（冷熱合一 `[IN]`/`[OUT]`/`ALERT`）、Stream 3 `perf/YYYY-MM-DD.jsonl`（任務分派、完整 ImTK 效能樹、RSS 與失敗/超慢上下文 + Daemon `ProfilerRingBuffer`）、Per-Module `modules/<mod>.jsonl`（完整中間態自動戳記關聯鍵並將 `WARN/ERROR` 冒泡至 `daily/`）；貫通 `CLI → Daemon → Tier 1 Worker` 三進程 `profiler_tree` 合併與單寫入者主權矩陣，並為 `LogRotator` 補齊 POSIX `fcntl.flock` / Win32 `LockFileEx` 跨進程側車鎖。
  - **SDK 80 符號門面、極簡 `--profile`/`--profile-mem` 與 `TODO-31` 實戰優化**：擴充 `core.surface.sdk` 至 **80 符號**（匯出 `Profiler` 契約與 `ctx.profiler`/`env.profiler`）；新增全域 `--profile`（`stderr` 輸出 ImTK 瀑布樹且 `--json` `stdout` 100% 純淨）與 `--profile-mem`/`YSCB_PROFILE_MEM=1`；落地 `_LazyCliKernelSession`/`_LazyCliDispatcherProxy`（完整對齊 Stage-1 守門）將 `daemon start --supervisor` 建核次數由 **2 次降為 1 次**，並以 20ms Racy-Clean `.cache/daemon/core_sig_cache.json` 將 `_scan_core_module_tree` 由 **`62.83ms` 加速至 `5.48ms`（11.5x）**、Windows 11 `surface_cli_e2e` 縮短 **`65.75s`**；同步根治 Windows 並發 `ntpath.realpath()` 殘留 `\\?\` 前綴競態（全核心統一採用 `safe_realpath`）及 Daemon RPC 逾時起點偏差。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `core_v2/source/core/core/foundation/profiler.py` | New | ImTK 階層剖析器、`MemoryTrackingGuard`、3+1 JSONL `FlightLogRouter`、`ProfilerRingBuffer`、脫敏器、RSS 讀取與瀑布樹渲染器 |
| `core_v2/source/core/core/foundation/{observability,primitives,proc,__init__}.py` | Modify | 擴充 `LogRecord` 與 `LogRotator` 跨進程側車鎖、淘汰 `SessionTelemetry*`、新增 `safe_realpath()` / `read_flight_log_env()` / `YSCB_PROFILE_MEM` 並匯出（105 符號） |
| `core_v2/source/core/core/filesystem/{fs/atomic,vfs/provider,space/scanner,storage/database}.py` | Modify | 全域收斂 `safe_realpath()`；於 `ModuleDatabase` 與 `SpaceScanner` 加入選配 `profiler` 埋點 |
| `core_v2/source/core/core/packaging/{env/pool,installer/provider}.py` | Modify | 收斂剩餘裸 `os.path.realpath` 為 `safe_realpath()` 確保跨模組 Windows 路徑一致 |
| `core_v2/source/core/core/execution/runtime/{contracts,wire,services,module_slot,coordinator,turn_session,step_host,worker_entry,worker_pool,dispatcher}.py` | Modify | `TaskContext.profiler`、關聯上下文與模組日誌 `ALERT` 冒泡、三進程 `profiler_tree` 合併、單寫入者主權矩陣與 `invoke_daemon_rpc` 逾時計時起點修復 |
| `core_v2/source/core/core/execution/daemon/service.py` | Modify | Stream 1 `daemon/` 生命週期日誌、統一 `boot_id`、`profiler_summary` 與 20ms Racy-Clean `core_sig_cache.json` |
| `core_v2/source/core/core/surface/{sdk,cli,bootstrap}/*.py`、`core_v2/yscb.py`、`config.project.json.tmpl` | Modify | SDK 80 符號門面、`--profile`/`--profile-mem` 旗標、`boot_start_ns` 銜接、`_LazyCliKernelSession`/`_LazyCliDispatcherProxy` 單次建核快啟與 `observability` 組態範本 |
| `core_v2/sub_module_design/{foundation/foundation,filesystem/space,filesystem/storage,execution/runtime,execution/daemon,surface/sdk,surface/cli,surface/composition_and_bootstrap}.md` | Modify | 1:1 同步全部 8 份受影響之 Active Living Specs（通過 Gate 0 雙向對齊） |
| `core_v2/tests/{_harness,test_gate0,test_foundation_fs,test_vfs_storage_space,test_runtime_daemon,test_rc_e2e,test_surface_sdk,test_surface_cli_e2e}.py` | Modify | 補齊 3+1 日誌、ImTK 剖析器、三進程合併、並發輪替鎖、`safe_realpath`、5 組獨立未物化懶代理守門與 Windows 多進程同步加固 |
| `CHANGELOG.md`、`core_v2/ROADMAP.md`、`core_v2/handoff.md`、`plans/roadmap/TODO.md` | Modify | 更新全域發布日誌、Core 2.0 路線圖與交接快照（93 檔 / `65,954 LOC`、80 符號 SDK），並延後登錄 `TODO-32` (`yscb diag`) |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：**100% 通過（`0 ResourceWarning`）**
  - **Linux 標準 / `-O` 雙模全 9 套件**：`255.31s` / `289.72s` 全綠；Windows 修復與 Pillar 3 複修後覆驗 `gate0` (`13.63s`)、`foundation_fs` (`0.98s`)、`vfs_storage_space` (`3.50s`)、`metadata_packaging` (`12.70s`)、`runtime_daemon` (`14.48s`)、`rc_e2e` (`62.27s`)、`surface_cli_e2e` (`157.81s`)、`unplug` 10 階段 (`2.65s`) 全綠。
  - **效能基準 (`PT-01`)**：30 層 Scope 開銷 `0.1678ms`（`< 0.5ms`）；`daemon start --supervisor` 僅建核 1 次；`_scan_core_module_tree` `62.83ms → 5.48ms`（`11.5x`）。
  - **雙重唯讀盲審**：Pre-Code Analyze Gate (`PASSED`)、Pre-UX 唯讀盲審 (`REVIEW_STATUS: PASSED`) 與 Phase 7 Pillar 3 跨模組冷眼盲審 (`REVIEW_STATUS: PASSED`) 全數閉環。
- **實機 UX / 人工驗證 (`UX-01`)**：**`[測試通過]`** — 開發者於 Windows 11 實機驗證全 9 套件全綠（`gate0` `19.80s`、`foundation_fs` `2.84s`、`vfs_storage_space` `78.36s`、`metadata_packaging` `71.94s`、`surface_sdk` `12.22s`、`surface_cli_e2e` `572.16s` 較前次快 `65.75s`、`runtime_daemon` `23.80s`、`rc_e2e` `105.56s`、`unplug` `7.55s`，`0 ResourceWarning`），並審閱實機 `stderr` 3 進程 `--profile`/`--profile-mem` ImTK 瀑布樹與 4 路 JSONL 樣本後簽核通過。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md`、`core_v2/ROADMAP.md`、`core_v2/handoff.md` | 已交付 | 追加本計畫發布摘要並更新 Core 2.0 模組清冊、LOC 規模與 80 符號 SDK 狀態 |
| **中觀 (Meso)** | `core_v2/sub_module_design/{foundation/foundation,filesystem/space,filesystem/storage,execution/runtime,execution/daemon,surface/sdk,surface/cli,surface/composition_and_bootstrap}.md` | 已交付 | 8 份 Active Living Specs 1:1 雙向對齊並通過 Gate 0 校驗 |
| **中觀 (Meso)** | `docs/<Category>/{README,[topic]}.md` | 免更 | 1.x 主線知識庫維持潔淨室邊界零異動 |
| **中觀 (Meso)** | `docs/<Category>/DESIGN_NOTES.md` | 免更 | 本計畫屬 Core 2.0 潔淨室實作，平台/架構不變量已完整紀錄於對應 Active Living Specs |
| **微觀 (Micro)** | `core_v2/source/core/core/**/*.py` Public API Docstrings | 已交付 | 全新增公開類別、函式與契約具完整 Docstring 且零工單標籤、`0 Any` |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack（`ys_codebase/source/*` 與 `.vscode/settings.json` 零異動）。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(core_v2): add ImTK-style profiler, 3+1 JSONL flight logs, and TODO-31 fast daemon boot
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_25_1157_core_v2_observability_profiler` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
