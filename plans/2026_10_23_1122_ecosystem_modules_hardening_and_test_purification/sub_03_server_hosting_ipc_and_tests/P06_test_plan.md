# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_03_server_hosting_ipc_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Passed  
> 模型：Gemini 3.8 Flash (Medium)  

> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 單元測試 | 驗證 `ServiceManager.load_from_contributes` 透過 SDK 載入連字號模組且不拋 `NameError`，`auto_start` 正常作用 | FR-01 | `test_server.py::test_service_manager_load_from_contributes_and_auto_start` |
| **FT-02** | 整合測試 | 驗證 `worker_main` 私有 `_ipc_stdout` 隔離，背景 `print` 雜訊導向 stderr 不污染 IPC，且 `exit` 觸發 `stop_all` | FR-02 | `test_server.py::test_worker_main_ipc_isolation_and_exit_handshake` |
| **FT-03** | 單元測試 | 驗證 `MasterSupervisor._write_state()` 傳入 `self._start_time`，Worker 重啟後 `start_time` 不重置 | FR-03 | `test_server.py::test_master_supervisor_start_time_persistence` |
| **FT-04** | 靜態檢核 | 驗證 Worker 與 Master 啟動時零 `source/` 路徑注入，嚴守 `.modules/` 運行時隔離 | FR-04 | `test_server.py::test_worker_and_master_zero_source_path_injection` |
| **FT-05** | 單元測試 | 驗證 `contributes/core.json` 聲明 events，`restart_worker()` 同步刷新 `ServerConfig.idle_timeout_sec` | FR-05 | `test_server_config.py::test_server_reload_syncs_config_and_events_declared` |
| **FT-06** | 整合測試 | 驗證 `test_basic.py` 移除後測試集收斂為 3 檔，重寫之 IPC Log 攔截與 Watcher 狀態測試 100% 呼叫真實方法 | FR-06 | `test_server_logging.py::test_worker_ipc_logging_stream` |
| **FT-07** | 整合測試 | 驗證 `MasterSupervisor` 之 `POST /api/dispatch`、`/api/reload`、`/api/shutdown` 全端點及 CLI 四大 `CmdBags` 指令 | FR-07 | `test_server.py::test_master_supervisor_http_and_lifecycle` |
| **ET-01** | 邊界測試 | 服務宣告使用 `code.class://knowledge-db/...` 連字號路徑，成功動態解析並注入 `.modules/knowledge-db` | EC-01 | `test_server.py::test_service_manager_load_from_contributes_and_auto_start` |
| **ET-02** | 邊界測試 | 服務宣告設定 `"auto_start": false`，`start_all()` 略過啟動該服務，`alive` 保持 `False` | EC-02 | `test_server.py::test_service_manager_load_from_contributes_and_auto_start` |
| **ET-03** | 邊界測試 | 背景執行緒隨機寫入非結構化字串，NDJSON 管道無交錯或損毀，Master 不拋 `JSONDecodeError` | EC-03 | `test_server.py::test_worker_main_ipc_isolation_and_exit_handshake` |
| **ET-04** | 邊界測試 | Worker 收到 `exit` 逾時未退出時，Master 兩階段停機降級為 `kill_process_tree` 強制收割 | EC-04 | `test_server.py::test_master_two_stage_kill_fallback` |
| **ET-05** | 邊界測試 | `POST /api/dispatch` 傳入不相符 `yscb_root` 回傳 HTTP `400`；CLI `start` 傳入負數 TTL 阻斷退出 | EC-05 | `test_server_config.py::test_cli_and_http_bad_request_guard` |
| **RT-01** | 全量回歸 | 執行 `python yscb.py dev check server` 與 `python yscb.py dev test server -q` 100% 通過且零殘留 | NFR-01, NFR-02 | `dev check server` && `dev test server -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-07** | `Passed` | 包含 `test_server.py`, `test_server_config.py`, `test_server_logging.py` 單元與整合測試全量綠燈通過 (40/40) | 2026-10-24 11:50 |
| **ET-01 ~ ET-05** | `Passed` | 包含 hyphen 模組解析、auto_start、IPC 隔離雜訊測試、兩階段強制收割與負數 TTL 阻斷等邊界測試通過 | 2026-10-24 11:50 |
| **RT-01** | `Passed` | `dev check server` 通過，`dev test server --sync` 通過 (40/40)，全量回歸 `dev test -q` 通過 (193/193) | 2026-10-24 11:50 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py server status`，驗證各項輸出（Uptime、Port、Background Svcs）顯示正常且無報錯。 | `Passed` | 實機輸出 State: READY, Worker PID Alive, Background Svcs: knowledge-db-watcher RUNNING |
| **UX-02** | 執行 `python yscb.py server reload`，驗證輸出 Worker 重啟橫幅且 Uptime 不被重置。 | `Passed` | 實機驗證熱重啟成功，新 PID 正常接手且 Master Uptime (2.9s -> 7.8s) 持續累加未被重置 |
