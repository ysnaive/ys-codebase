# Phase 6: 測試計畫與驗證報告 (P06 Test Plan)

> 功能名稱：sub_06_downstream_cli_ux_and_server_feedback  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `server start` 輸出結構化啟動橫幅（包含 PID、Port、TTL 等參數） | FR-01 | `python yscb.py dev test server -k test_server_cli` |
| **FT-02** | 單元測試 | 驗證 `server stop` 輸出結構化停機總結報告（包含 Uptime、Tasks、歸檔路徑） | FR-03 | `python yscb.py dev test server -k test_server_cli` |
| **FT-03** | 單元測試 | 驗證 `server status` 增強欄位（Uptime、Log File）正確呈現 | FR-04 | `python yscb.py dev test server -k test_server_cli` |
| **RT-01** | 模組回歸 | 驗證 `server` 模組全量單元測試 100% 通過 | NFR-02 | `python yscb.py dev test server` |
| **RT-02** | 全量回歸 | 驗證全生態系 550 項單元測試 100% 通過 | NFR-02 | `python yscb.py dev test --all --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** ~ **FT-03** | `Passed` | `test_format_startup_banner_and_shutdown_summary` 與 `test_status_and_shutdown_api_payloads` 100% 斷言通過 | 2026-10-14 14:23 |
| **RT-01** | `Passed` | `server` 模組全量 36 項單元測試 100% 通過（含 3 契約測試與 33 自訂測試） | 2026-10-14 14:24 |
| **RT-02** | `Passed` | 全生態系 5 大模組 552 項單元測試 100% 通過（0 Fail, 0 Skip） | 2026-10-14 14:25 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python yscb.py server start`，終端清晰輸出包含 PID、Port、TTL、Watcher、Services、Log 之 ASCII 啟動橫幅 | `Passed` | 實機輸出完整對齊橫幅，包含 Master/Worker PID、Port、Log 路徑等 |
| **UX-02** | 實機執行 `python yscb.py server stop`，終端清晰輸出包含 Uptime、累計任務數、停機原因、歸檔日誌路徑之停機報告 | `Passed` | 實機輸出 Total Uptime: 14.3s、Tasks Handled、Archived Log 路徑 |

