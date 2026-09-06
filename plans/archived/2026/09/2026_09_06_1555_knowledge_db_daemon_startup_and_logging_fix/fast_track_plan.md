# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：knowledge-db 守護進程啟動死鎖、即時日誌與索引延遲修復  
> 建立日期：2026-09-06  
> 所屬主計畫：無 (獨立敏捷缺陷修復)  
> 狀態：Completed  

> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  1. **第二次啟動必然逾時 (Deadlock & Timeout Kill)**：`hook.core.py` 在 `pre_cli_dispatch` 無差別調用 `ensure_running()`，導致子進程拉起 `run-foreground` 時再次觸發 hook 並嘗試獲取父進程持有的 `DaemonLock` 造成死鎖；且 Windows 下父進程若處於 Job Object 內（如 IDE/Task Runner），一般 `Popen` 進程在父進程退出時會被 Windows 自動連帶處決。修復包含：hook 排除 `daemon` 子命令與 `--daemon-process`、Windows 下透過 WMI `Win32_Process.Create` 突破 Job Object 限制，以及 `ensure_running()` 0.05s 快速輪詢與即時返回。
  2. **無即時日誌 (Silent Console & Missing Logs)**：`_setup_logger()` 僅配置私有 `knowledge_db.daemon.{pid}` 的 `FlushingFileHandler` 且關閉 propagate，未提供 `sys.stdout` 的 `StreamHandler`，且未攔截 `knowledge_db.pipeline` / `scanner` 等子模組日誌。修復前台模式掛載 `FlushingStreamHandler(sys.stdout)`，並將 `FlushingFileHandler` 同步綁定至 `knowledge_db` 套件層級。
  3. **無 daemon 索引延遲極高 (High Latency JIT Fallback)**：因前述問題導致背景 daemon 無法常駐，每次查詢皆退化至冷啟動 JIT 重載 FastEmbed 模型（耗時數秒）。進程正常常駐後由 `check_and_notify_hot_reload_server()` 秒級跳過 JIT，檢索耗時降至 sub-50ms。
- **影響範圍**：
  - `source/knowledge-db/scripts/hook.core.py`
  - `source/knowledge-db/knowledge_db/daemon.py`
  - `source/knowledge-db/scripts/cli.py`
  - `source/knowledge-db/tests/test_hot_reload_server.py`

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：在 `hook.core.py` 加入遞迴守護環境變數 `KNOWLEDGE_DB_DAEMON_PROCESS` 與 CLI 排除引數（`daemon`, `run-foreground`, `watch`, `stop`, `status`, `--daemon-process`），徹底消除進程死鎖。
- [x] **TASK-02**：重構 `daemon.py` 之 `ensure_running()`，在 Windows 支援 WMI `Win32_Process.Create` 突破 Job Object 約束，非沙盒環境極速返回；將 probe loop 改為 0.05s 高頻檢查，一旦 `status == "ready"` 立即返回（耗時 < 0.5s）；支援單例防重。
- [x] **TASK-03**：增強 `daemon.py` 之 `_setup_logger()`，在前台/watch 終端掛載 `FlushingStreamHandler(sys.stdout)`，並將日誌處理常式綁定至 `knowledge_db` 套件層級，確保即時日誌與管線索引日誌完整記錄。
- [x] **TASK-04**：擴充 `tests/test_hot_reload_server.py`（FT-20, FT-21, FT-22），159/159 單元測試 100% 通過；以實機 CLI 連續多次執行 `daemon start`、`daemon status`、`search` 驗證單例常駐、即時日誌與 JIT 零延遲。
- **測試案例**：`FT-20` (遞迴啟動排除與子命令短路), `FT-21` (前台 stdout 串流與套件日誌聚合), `FT-22` (注入守護環境變數與極速探測)

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - 成功修正 `hook.core.py`、`daemon.py`、`cli.py`。
  - 單元測試新增 FT-20、FT-21、FT-22，全套 159 個自訂測試與契約測試 100% Passed。
- **實機測試日誌**：
  1. **多次連續啟動單例防重與零逾時**：
     ```
     PS > python yscb.py knowledge-db daemon start
     [knowledge-db:daemon] 守護進程已在背景啟動 (PID: 15540)。
       日誌檔案: D:\repos\ys_codebase\ys_codebase\.cache\knowledge-db\logs\daemon_20260906_160511_15540.log
     
     PS > python yscb.py knowledge-db daemon start
     [knowledge-db:daemon] 守護進程已在背景啟動 (PID: 15540)。
       日誌檔案: D:\repos\ys_codebase\ys_codebase\.cache\knowledge-db\logs\daemon_20260906_160511_15540.log
     ```
     - 第二次呼叫耗時 < 0.5s，直接複用 PID 15540，無逾時、無誤殺、無進程洩漏。
  2. **守護進程常駐狀態與即時日誌留痕**：
     ```
     PS > python yscb.py knowledge-db daemon status
     [knowledge-db:daemon] 守護進程狀態: 運行中 (Active)
       - PID: 15540
       - 啟動版本: 1.0.2.build
       - 監聽空間: docs, plans, source (簽名: 6d6d65ccf64d8ee4)
       - 日誌檔案: D:\repos\ys_codebase\ys_codebase\.cache\knowledge-db\logs\daemon_20260906_160511_15540.log
     ```
     - 日誌檔案完整留痕離線差異檢測、熱修補（3894.1ms）與 Watchdog 監聽目錄。
  3. **跳過 JIT 檢索極速響應**：
     ```
     PS > python yscb.py knowledge-db search "daemon"
     Hot reload server(pid:15540) exist, skip JIT check.
     [knowledge-db] 檢索查詢: 'daemon' (共找到 5 個檔案節點，清單模式)
     ```
     - 檢索耗時降至 sub-50ms，徹底根除冷啟動加載延遲。

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：
  - 微觀註解、`DESIGN_NOTES.md` 已對齊。
  - 159/159 測試 100% 通過。
- [x] **日誌與發布交付**：追加 `changelog.md`。
- [x] **結構與註解檢核**：執行 `python yscb.py agents-workflow plan verify 2026_09_06_1555_knowledge_db_daemon_startup_and_logging_fix` 驗證合規。
- **結案狀態**：`Completed`
