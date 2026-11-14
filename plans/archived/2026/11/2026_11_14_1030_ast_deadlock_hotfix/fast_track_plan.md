# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：AST 指令跨執行緒與跨消費端防死鎖過渡止血修復  
> 建立日期：2026-11-14  
> 所屬主計畫：獨立計畫 (Standalone)  
> 狀態：Completed  
> 模型：Unknown  

> 計畫類型：Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)

### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)
- [x] **修改行數守門**：過渡期手術式鎖序解耦與防堵（初始預估 $\le 100$ 行；含 `[FP-02:DR-01]` 納入 `server/worker.py` `stderr` FD 隔離後，實測 10 個生產檔案忽略空白 `git diff -w --stat` 為 +187/-30 行，維持零架構重寫與零 Public API 異動）。
- [x] **API 契約守門**：Public API 簽名契約 0 變更（無破壞性與新增導出）。
- [x] **依賴邊界守門**：零跨模組新依賴引入。
- [x] **既有測試守門**：受影響核心功能與新增並發回歸測試 100% 通過；既有跨範疇 Windows 測試基建問題依方案 A（`[FP-02:DR-01]`）轉入 `TODO-26`、`TODO-27`。

### 1.2 核心需求與邊界
- **需求描述**：針對 Core 2.0 上線前之過渡期間，緊急消除 `ast callers` / `ast outline` / `knowledge-db` 並發或背景同步期間可能發生之 AB-BA 鎖死鎖、無鎖 C `TreeSitter` 節點競態、Windows `ProcessPoolExecutor` 冷啟動卡死、背景持久化執行緒自旋及 `WarmWorker` 假性心跳無限掛起問題，並進行多執行緒壓力測試驗證。
- **影響範圍**：`ys_codebase/source/{core,knowledge-db,server,ast}/`、`docs/{ast,server}/DESIGN_NOTES.md`、`CHANGELOG.md`（嚴禁變更 `.modules/` 黑盒或新增公開介面）。

### 1.3 實作任務與測試規劃
- [x] **TASK-01**：`core`（`scanner.py`）將 `CursorStore._rlock` 降為葉鎖並拆分為依 `consumer_id` 獨立的 `RLock`，且 `_prune_expired_tombstones` 不再於 `SpaceScanner._rlock` 內阻塞等待他處消費端鎖。
- [x] **TASK-02**：`knowledge-db`（`pipeline.py`, `scripts/hook.core.py`）在取得 `knowledge-db` 游標批次鎖前先行呼叫 `ensure_jit_synced`，並禁止 Worker 環境空檔回落事件執行緒同步索引。
- [x] **TASK-03**：`server`（`space_watcher.py`, `master.py`, `worker.py`）將事件廣播移出 `watcher._flush_lock`，補齊 `worker_main` `stderr` FD 隔離與 Windows 讀取執行緒先收斂後關管順序，並為 `MasterSupervisor` 增設真實 Worker 靜默逾時斷路與自動回收機制（`YSCB_WORKER_STALL_TIMEOUT_SEC`）。
- [x] **TASK-04**：`ast`（`scripts/hook.core.py`, `engine.py`, `bundler.py`, `parsers/treesitter.py`）禁止 Worker 廣播同步搶鎖、收斂 `.ast_index.lock` 至純磁碟讀寫、修正 `_run_bg_persist_loop` 空轉、Windows 停用 `ProcessPoolExecutor`，並以 `_cache_lock` 保護 `TreeSitterDriver` 節點走訪與 `tree` 生命週期。
- **測試案例清冊**：
  - [x] **FT-01**：`core` 驗證 `batch_cursor_updates("knowledge-db")`、`batch_cursor_updates("ast")` 與 `patch_files` 過期墓碑清理並發無死鎖。
  - [x] **FT-02**：`ast` 驗證並發 `callers` + `outline` + Worker 廣播鉤子無死鎖與無競爭異常。
  - [x] **FT-03**：`knowledge-db` 驗證 `sync_incremental_changes` 與 `ensure_jit_synced` 交叉並發無 AB-BA 死鎖。
  - [x] **FT-04**：`server` 驗證 `SpaceWatcher` 鎖外廣播重入安全性與 `MasterSupervisor` 卡死 Worker 斷路自動回收。
  - [x] **FT-05**：四模組 `@build` 熱部署後執行多執行緒 CLI（`ast outline/callers/callees/slice/traverse/status` + `knowledge-db search`）高並發壓力測試，達成零逾時、零死鎖。
  - [x] **RT-01**：`dev check` 4/4 與 `ast` 58/58、`knowledge-db` 125/125、`server` 靶向套件 64/64、`core` 靶向回歸全數通過（Windows 嵌套沙盒 `MAX_PATH` 與 `TestVFS` 既有基建議題依 `[FP-02:DR-01]` 轉入 `TODO-26` / `TODO-27`）。

---

## 2. 實作與驗證成果 (FP-02 Execution & Test Log)

- **實作結果**（10 個生產檔案，忽略空白 `git diff -w --stat` 計 `+187 / -30` 行；零 Public API 變更、零跨模組新依賴）：
  - [scanner.py](../../ys_codebase/source/core/core/space/scanner.py)：`CursorStore._rlock` 僅保護元數據映射不跨 `yield`/I/O，新增 `_consumer_locks` / `_get_consumer_lock` 隔離 `knowledge-db` 與 `ast` 游標鎖。
  - [pipeline.py](../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py)、[hook.core.py](../../ys_codebase/source/knowledge-db/scripts/hook.core.py)：`sync_incremental_changes` 於取得 `_write_serial_lock` 前先執行 `ensure_jit_synced(allow_parallel=False)`；`YSCB_IN_SERVER_WORKER=1` 且無活躍 KDB Worker 時事件鉤子直接回傳 `"noop"`。
  - [hook.core.py](../../ys_codebase/source/ast/scripts/hook.core.py)、[engine.py](../../ys_codebase/source/ast/ast_engine/engine.py)、[bundler.py](../../ys_codebase/source/ast/ast_engine/bundler.py)、[treesitter.py](../../ys_codebase/source/ast/ast_engine/parsers/treesitter.py)：`ast` 事件鉤子於 `YSCB_IN_SERVER_WORKER=1` 無 KDB Worker 時回傳 `"noop"`；`hot_patch_index` 移除外層 `InterProcessLock`；`_run_bg_persist_loop` 先檢查 `_bg_persist_pending is None` 再判斷 `is_foreground_active()` 並於 `_bg_persist_lock` 內更新時間戳；`bundle_union` 於 Windows 停用 `ProcessPoolExecutor`；`TreeSitterDriver` 快取保留 `"tree"` 並以 `self._cache_lock` 序列化走訪。
  - [space_watcher.py](../../ys_codebase/source/server/server/space_watcher.py)、[worker.py](../../ys_codebase/source/server/server/worker.py)、[master.py](../../ys_codebase/source/server/server/master.py)：`SpaceWatcher` 釋放 `_flush_lock` 後再執行 `_emit_changed_diffs`；`worker_main` 補齊 `stderr` FD 不可繼承複製與 `fd 2` `devnull` 重導向；`_kill_worker_locked` 先 `join` `_yscb_io_threads` 再關讀管；`_stream_task_over_worker_pipe` 增設 `YSCB_WORKER_STALL_TIMEOUT_SEC`（預設 `120.0s`）真實封包靜默斷路器。
  - **範疇裁定 `[FP-02:DR-01]`**：採納方案 A，不變更 `dev/` 與 `test_vfs.py`，已透過 `todo add` 登記 `TODO-26`（Windows 嵌套 `ISOLATED_SANDBOX` 260 字元 `MAX_PATH` `WinError 3`）與 `TODO-27`（`TestVFS` Windows `os.readlink` 長路徑前綴比對）。
- **實機測試與壓測日誌**：
  - **合規檢核 (`dev check`)**：`core`、`ast`、`knowledge-db`、`server` 共 4/4 **PASSED**。
  - **單元與並發回歸**：
    - `ast`：`dev test ast -q` -> **58/58 PASSED**（含 `test_concurrent_callers_outline_and_worker_hook_no_deadlock` `1/1` in `1.54s`）。
    - `knowledge-db`：`dev test knowledge-db -q` -> **125/125 PASSED**（含 `test_concurrent_kdb_sync_and_ast_jit_sync_no_abba_deadlock` `1/1` in `2.45s`）。
    - `server` 靶向全綠：`TestServerModule` **46/46 PASSED**（21.34s，涵蓋 stall 斷路器、Windows `stderr` /孫進程回收及日誌鎖釋放修復）、`TestServerConfig` **9/9 PASSED**（0.86s）、`TestServerLogging` **9/9 PASSED**（0.36s）；註：事前全量 `dev test server -q` 中 `TestCoreSpaceWatcherService` 5 項因嵌套 `ISOLATED_SANDBOX` 觸及 Windows `MAX_PATH` 失敗，已納入 `TODO-26`。
    - `core` 靶向全綠：`test_cursor_store_isolated_consumer_locks_and_tombstone_prune_concurrency` **1/1 PASSED**（1.20s）、`TestEventsPipeline` **12/12 PASSED**（0.73s）；註：事前全量 `dev test core -q` 為 208 Pass / 95 Fail / 1 Skip，94 項為嵌套 `ISOLATED_SANDBOX` `WinError 3`（`TODO-26`），1 項為 `TestVFS` 宿主路徑/前綴問題（`TODO-27`）。
  - **`@build` 熱部署與實機多執行緒壓測**：
    - 完成 `core@1.2.10.build`、`ast@1.1.1.build`、`knowledge-db@1.2.3.build`、`server@1.0.7.build` 安裝與 `server reload`（Master PID `40700`、Worker PID `72140` `READY`）。
    - 壓測 Phase 1（8 執行緒、64 次 `ast outline/callers/callees/slice/traverse/status` + `knowledge-db search`）：**64/64 PASSED**（0 Fail、0 Timeout，`wall_sec=7.15s`，`p50=618.1ms`，`p95=2405.3ms`，`max=2617.3ms`）。
    - 壓測 Phase 2（6 查詢執行緒 + 背景執行緒 12 次寫入 `_stress_probe_tmp.py`、36 次混合圖譜查詢）：**36/36 PASSED**（0 Fail、0 Timeout，`wall_sec=4.02s`，`p50=497.3ms`，`p95=1148.5ms`，`max=1615.3ms`）。
    - 壓測收斂後 `reconcile_ast_ok=true`、`reconcile_kdb_ok=true`，`server status` 維持 `READY`（`Tasks Handled: 129`、`Auto-Recycles: 0`）。

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（[docs/ast/DESIGN_NOTES.md](../../docs/ast/DESIGN_NOTES.md) `DN-AST-11`、[docs/server/DESIGN_NOTES.md](../../docs/server/DESIGN_NOTES.md) `DN-14`、[CHANGELOG.md](../../CHANGELOG.md)、微觀註解）與受影響測試/實機壓測 100% 通過（跨範疇測試基建登錄 `TODO-26`/`TODO-27`）。
- [x] **日誌與發布交付**：已追加 `CHANGELOG.md` 結案摘要並登載 `[FP-02:DR-01]` 至 `changelog.md`。
- [x] **標頭狀態更新**：已將頂部標頭 `> 狀態：` 更新為 `Completed` 且維持 `> 模型：Unknown`。
- [x] **結構與註解檢核（最終守門）**：實機執行 `python yscb.py agents-workflow plan verify 2026_11_14_1030_ast_deadlock_hotfix` 通過。
