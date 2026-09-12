# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：server_realtime_logging  
> 建立日期：2026-09-07  
> 所屬主計畫：無 (獨立 Full Track)  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `ServerLogger` 寫入格式、首行 `server start at time "..."` 與即時 `flush()` 落檔 | FR-01, FR-02 | `pytest source/server/tests/test_server_logging.py -k test_logger_write_and_flush` |
| **FT-02** | 單元測試 | 驗證歷史檔名格式匹配與 $\le 5$ 份滾動保留清理，驗證非相關檔案不被誤刪 | FR-04, EC-03, EC-04 | `pytest source/server/tests/test_server_logging.py -k test_rolling_retention` |
| **FT-03** | 功能測試 | 異常中斷自癒測試：模擬遺留未歸檔之舊 log，驗證啟動時解析首行時間戳並成功轉存歷史 | FR-03 | `pytest source/server/tests/test_server_logging.py -k test_crash_recovery_with_header` |
| **FT-04** | 邊界測試 | 舊 log 檔案為空或首行損毀無啟動標誌時，驗證安全退化採用 mtime 格式化轉存 | FR-03, EC-01 | `pytest source/server/tests/test_server_logging.py -k test_crash_recovery_corrupted_header` |
| **FT-05** | 邊界測試 | 歷史檔名同名衝突時，驗證自動附加後綴序號避免覆蓋既有歷史日誌 | EC-02 | `pytest source/server/tests/test_server_logging.py -k test_archive_collision_handling` |
| **FT-06** | 功能測試 | 優雅停機（Graceful Shutdown）測試：驗證停機時自動歸檔當前 log 為歷史檔並清理滾動 | FR-07 | `pytest source/server/tests/test_server_logging.py -k test_graceful_stop_archival` |
| **FT-07** | 整合測試 | MasterSupervisor 整合測試：驗證啟動、HTTP 請求處理與 dispatch 任務完成時各記錄完整度 | FR-05 | `pytest source/server/tests/test_server_logging.py -k test_master_logging_integration` |
| **FT-08** | 整合測試 | Worker IPC 串流日誌匯流測試：驗證 Worker 送出 log 封包被 Master 捕獲並統一落檔 | FR-06 | `pytest source/server/tests/test_server_logging.py -k test_worker_ipc_logging_stream` |
| **RT-01** | 回歸測試 | Server 模組既有全部 23 項測試 100% 綠燈回歸 | 全局相容性 | `pytest source/server/tests/` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 驗證 ServerLogger 首行標誌、即時 flush 與標準格式化成功 | 2026-09-07 |
| **FT-02** | `Passed` | 驗證歷史檔案 5 份滾動保留，非相關快取檔案完整保護 | 2026-09-07 |
| **FT-03** | `Passed` | 驗證啟動時成功偵測未歸檔舊日誌並以首行時間戳轉存歷史 | 2026-09-07 |
| **FT-04** | `Passed` | 驗證首行損毀/無標誌時安全退化以檔案 mtime 格式化轉存 | 2026-09-07 |
| **FT-05** | `Passed` | 驗證歷史檔名衝突時自動附加序號後綴防覆蓋 | 2026-09-07 |
| **FT-06** | `Passed` | 驗證優雅停機時主動歸檔當前日誌為歷史檔並滾動清理 | 2026-09-07 |
| **FT-07** | `Passed` | 驗證 MasterSupervisor 生命週期整合與日誌記錄完整度 | 2026-09-07 |
| **FT-08** | `Passed` | 驗證 Worker IPC 日誌封包匯流由 Master 集中落檔不外洩至任務串流 | 2026-09-07 |
| **RT-01** | `Passed` | Server 模組既有 23 項測試 100% 綠燈回歸 (總計 31/31 案例通過) | 2026-09-07 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 啟動 server 前台模式或背景模式，檢視 `cache://server/log` 檔案即時產生、首行格式 `server start at time "..."` 及各事件即時 flush | `[測試通過]` | 開發者實機驗收通過 (2026-09-07) |
