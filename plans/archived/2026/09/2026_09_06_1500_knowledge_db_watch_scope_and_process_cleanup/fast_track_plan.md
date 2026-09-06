# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：knowledge_db_watch_scope_and_process_cleanup  
> 建立日期：2026-09-06  
> 所屬主計畫：無 (獨立 Fast Track)  
> 狀態：Completed  

> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  1. **收斂監聽過濾範疇**：收斂 `HotReloadServer.is_path_watched` 兜底邏輯，移除 `workspace_root` 過度寬鬆放行機制，嚴格限定監聽檔案必須明確隸屬於 Space 所定義之 `include` 實體根目錄（且符合 include/exclude 模式），杜絕 Space 範圍外的無關檔案（如 `.vscode/`, `.cache/`, `node_modules/`, `dist/`）觸發幽靈防抖與「無變更」空轉日誌循環。
  2. **四層剛性進程防護機制 (Four-Tier Process Safeguard)**：
     - **Tier 1 (父進程即時預註冊)**：父進程在 `subprocess.Popen` 返回瞬間 (<10ms) 立即將 `proc.pid` 預先註冊至 `daemon.pid`（標記 `status="starting"`），徹底消滅子進程啟動載入 Python 函式庫期間（2~3 秒）導致外界誤判未運行的空白真空期。
     - **Tier 2 (跨進程排他檔案鎖 `daemon.lock`)**：在 `ensure_running()` 引入跨進程排他鎖，防止連續或並行 CLI 呼叫競態拉起多個進程。
     - **Tier 3 (超時剛性熔斷強殺)**：若因極端高峰或死鎖導致進程超過探測上限（8.0 秒）仍未進入 Ready 狀態，立即發動 `taskkill /F /T /PID` 整棵進程樹強行處決，絕不放生孤兒殭屍進程，清理 PID 檔並安全降級。
     - **Tier 4 (啟動前孤兒進程掃蕩)**：在啟動新進程前，若系統中存在殘留的同專案 `knowledge-db daemon run-foreground` 進程，先以 `taskkill` 清場再啟動，確保絕對單例。
     - **進程樹強殺 (`taskkill /F /T`)**：在 `HotReloadServer.stop()` 中優先使用 `taskkill /F /T /PID` 徹底終止目標進程及其完整子進程樹。
  3. **可觀測性改善**：在防抖日誌中輸出觸發之 dirty 檔案名稱，避免盲盒除錯。
- **影響範圍**：
  - `ys_codebase/source/knowledge-db/knowledge_db/daemon.py`
  - `ys_codebase/source/knowledge-db/tests/test_hot_reload_server.py`

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：收斂 `daemon.py:is_path_watched`，移除 Space 外全域 `workspace_root` 兜底；完善防抖日誌輸出 dirty 檔案名稱。
- [x] **TASK-02**：於 `daemon.py` 實作四層剛性進程防護（Tier 1 父進程預註冊、Tier 2 `daemon.lock` 跨進程鎖、Tier 3 超時熔斷處決、Tier 4 啟動前清場）以及 `stop()` 進程樹強殺。
- [x] **TASK-03**：於 `test_hot_reload_server.py` 新增/更新單元測試，驗證非 Space 根目錄檔案不被監聽，連續 `ensure_running` 呼叫保證單例（Singleton），以及 Windows 進程樹終止邏輯。
- **測試案例**：
  - `FT-01`：驗證不在 Space include 範圍的檔案（如 `.vscode/settings.json`, `.cache/foo.json`）在 `is_path_watched` 中嚴格回傳 `False`。
  - `FT-02`：驗證連續/快速執行兩次 `ensure_running()` 僅存在單一運行實例，不洩漏多個進程。
  - `FT-03`：驗證 `HotReloadServer.stop()` 成功執行進程樹終止呼叫並清理 PID 鎖。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  1. `is_path_watched` 收斂：刪除原 696-714 行對 `workspace_root` 任意檔案的兜底放行機制，嚴格限定變更檔案必須隸屬至少一個解析之 Space `include` 根目錄，並具備防禦性型態檢查防止 Mock 空間結構異常；於防抖日誌輸出觸發之 dirty 檔案名稱列表。
  2. 四層剛性進程防護：
     - **Tier 1 (父進程即時預註冊)**：在 `subprocess.Popen` 返回瞬間立即寫入 `daemon.pid`（`status="starting"`），徹底消除 2~3 秒啟動真空期。
     - **Tier 2 (跨進程互斥鎖 `daemon.lock`)**：實作 `DaemonLock`（Windows `msvcrt.locking` / POSIX `fcntl.flock`），確保同一工作區同一時間僅有一進程調度啟動。
     - **Tier 3 (超時剛性熔斷強殺)**：探測等待上限放寬至 8.0 秒（80 * 0.1s），超時未 ready 即由 `kill_process_tree` 強行處決進程樹並清理 PID 檔。
     - **Tier 4 (進程樹強殺 `kill_process_tree`)**：在 Windows 使用 `taskkill /F /T /PID` 終止整個子進程樹。
  3. 全平台高辨識度進程命名：
     - **Windows**：建立 `cache://knowledge-db/bin/yscb-knowledge-db-daemon.exe` 執行檔，使 Windows 工作管理員直接顯示 `yscb-knowledge-db-daemon`，並透過 `SetThreadDescription` 與 `SetConsoleTitleW` 設定標題。
     - **Linux**：建立 `yscb-knowledge-db-daemon` 執行檔並透過 `libc.prctl(PR_SET_NAME)` 修改 `/proc/self/comm`，使 `ps` / `top` / `htop` / `pgrep` 精準識別 `yscb-kdb-daemon`。
     - **macOS**：建立 `yscb-knowledge-db-daemon` 執行檔並透過 `pthread_setname_np` 設置活動監視器 (Activity Monitor) 名稱。
     - **通用支援**：環境若安裝 `setproctitle` 則優先連動。
- **實機測試日誌**：
  - `python yscb.py dev test knowledge-db`：156 Total, 156 Passed, 0 Failed (19.747s) 100% PASS。
  - `test_ensure_running_four_tier_safeguards`：單元驗證 Tier 1 預註冊、Tier 2 鎖、單例防重複 Popen (1.67s PASS)。
  - `test_ensure_running_timeout_hard_kill`：單元驗證超時強殺處決 (1.51s PASS)。
  - `test_stop_invokes_kill_process_tree`：單元驗證進程樹終止與清理 (1.63s PASS)。
  - `test_get_daemon_executable_high_recognizability`：單元驗證專用高辨識度可執行檔生成 (1.16s PASS)。
  - `test_set_process_title_cross_platform`：單元驗證跨平台標題平滑設置無例外 (1.01s PASS)。
  - `test_contributes_driven_extensions_and_path_filter`：情境 F 驗證非 Space 根目錄檔案嚴格過濾 (1.69s PASS)。
  - `scratch/test_leak_repro.py`：實機測試連續快速兩次 `ensure_running`，第 1 次 2.67s 建立，第 2 次 0.19s 即時復用，系統中精確僅存 1 個守護進程，徹底杜絕多進程洩漏。

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `project://CHANGELOG.md` 發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed。
- **結案狀態**：`Completed`


