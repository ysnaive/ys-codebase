# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：server_module_daemon_supervisor  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Passed  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `core.platform.process`：測試 `spawn_detached` 能在背景拉起脫鉤進程，`is_process_alive` 能精確識別存活與已死 PID | FR-01 | `python yscb.py dev test --modules=core --filter=platform` |
| **FT-02** | 單元測試 | `core.platform.process`：測試 `kill_process_tree` 能完整收割父進程及其派生之子進程，不留殭屍進程 | FR-01 | `python yscb.py dev test --modules=core --filter=platform` |
| **FT-03** | 單元測試 | `core.platform.lock`：測試 `InterProcessLock` 互斥鎖有效性，同一鎖檔不可被雙重 acquire，支援 Context Manager | FR-01 | `python yscb.py dev test --modules=core --filter=platform` |
| **FT-04** | 靜態檢驗 | `server` 模組 CLI 入口靜態合規性（含 `process(args)`、首行 `guard_dispatch("server")`、無 `main`、無頂層裸語句） | FR-02 | `python yscb.py dev check server` |
| **FT-05** | 單元測試 | `DebouncedIOStreamer`：驗證輸出捕獲、500ms 防抖緩衝閥值、手動 flush 與 `terminal_stream` / `task_finish` NDJSON 協議 | FR-06 | `python yscb.py dev test --target=server:TestServerModule.test_debounced_streamer` |
| **FT-06** | 單元測試 | `WarmWorker`：驗證預熱時發布 `server_worker_warming` 與 `server_worker_ready` 事件，且按需延遲加載（調用 A 絕不載入 B） | FR-05<br/>FR-09 | `python yscb.py dev test --target=server:TestServerModule.test_warm_worker_pre_warm_events` |
| **FT-07** | 單元測試 | `WarmWorker`：驗證模組拋出 `SystemExit` 時能安全攔截並轉為 exit code，Worker 進程持續常駐不崩潰 | FR-05 | `python yscb.py dev test --target=server:TestServerModule.test_warm_worker_system_exit_interception` |
| **FT-08** | 單元測試 | `BaseServiceWorker`：驗證 Service 伴隨 Master 啟動與停止，跟隨 Server 共享生命週期（有 TTL 則一同自毀，無 TTL 則一同常駐） | FR-10 | `python yscb.py dev test --target=server:TestServerModule.test_service_manager_lifecycle` |
| **FT-09** | 整合測試 | `MasterSupervisor`：驗證 127.0.0.1:0 動態隨機 Port、Token 403 阻擋、`/api/status`、`/api/dispatch` 任務排隊與串流回傳 | FR-03<br/>FR-04 | `python yscb.py dev test --target=server:TestServerModule.test_master_supervisor_http_and_lifecycle` |
| **FT-10** | 整合測試 | `ModulesWatcher`：驗證 `.modules/` 變更時，Master 自動終止舊 Worker 並重啟全新 Worker，代碼記憶體完全刷新 | FR-08 | `python yscb.py dev test --target=server:TestServerModule.test_modules_watcher_detection` |
| **FT-11** | 整合測試 | Server 生命週期配置：驗證開啟 15 分鐘 TTL 時空閒自毀，關閉 TTL 時可常駐運行，PID 鎖檔乾淨釋放 | FR-08 | `python yscb.py dev test --target=server:TestServerModule.test_master_supervisor_http_and_lifecycle` |
| **FT-12** | 系統測試 | `yscb.py` 雙軌調度客戶端：驗證軟依賴探測、自循環旁路 (`server` 指令走冷分發)、按需非同步拉起與 Server 未運行時透明冷降級 | FR-07 | `python yscb.py dev test --target=server` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `core:TestCorePlatform.test_spawn_and_liveness_and_kill` 通過 (0.15s) | 2026-09-06 23:50 |
| **FT-02** | `Passed` | `core:TestCorePlatform.test_spawn_and_liveness_and_kill` 通過，完整收割進程樹 | 2026-09-06 23:50 |
| **FT-03** | `Passed` | `core:TestCorePlatform.test_inter_process_lock_*` 通過互斥驗證 | 2026-09-06 23:50 |
| **FT-04** | `Passed` | `dev check server` 靜態檢驗合規通過 | 2026-09-06 23:52 |
| **FT-05** | `Passed` | `server:TestServerModule.test_debounced_streamer` 通過 (0.01s) | 2026-09-06 23:55 |
| **FT-06** | `Passed` | `server:TestServerModule.test_warm_worker_pre_warm_events` 通過 (0.02s) | 2026-09-06 23:56 |
| **FT-07** | `Passed` | `server:TestServerModule.test_warm_worker_system_exit_interception` 通過 (0.01s) | 2026-09-06 23:56 |
| **FT-08** | `Passed` | `server:TestServerModule.test_service_manager_lifecycle` 通過 (0.01s) | 2026-09-06 23:56 |
| **FT-09** | `Passed` | `server:TestServerModule.test_master_supervisor_http_and_lifecycle` 通過 (0.62s) | 2026-09-06 23:57 |
| **FT-10** | `Passed` | `server:TestServerModule.test_modules_watcher_detection` 通過 (0.51s) | 2026-09-06 23:56 |
| **FT-11** | `Passed` | `server:TestServerModule.test_master_supervisor_http_and_lifecycle` 通過 | 2026-09-06 23:57 |
| **FT-12** | `Passed` | `server` 全套 9/9 測試 100% 通過 (1.17s) | 2026-09-06 23:57 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py server status`，能正確呈現 Master、Worker PID、動態 Port 與 Idle TTL 倒數 | `[跳過/免測]` | 開發者指示免測 |
| **UX-02** | 執行業務命令（如 `python yscb.py dev test`），觀察終端是否具備 <30ms 熱派發瞬發感且串流輸出無撕裂 | `[跳過/免測]` | 開發者指示免測 |
