# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：CLI 觸發鍊與 Server/Worker 防卡死韌性加固  
> 建立日期：2026-11-10  
> 所屬主計畫：2026_11_10_1425_cli_worker_resilience_and_incremental_index_fix  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `YSCB_IN_SERVER_WORKER=1` 與 `YSCB_NO_HOT_DISPATCH=1` 強制繞過 HTTP 熱派發直走本地執行 | FR-01 | `python3 yscb.py dev test core --no-build` |
| **FT-02** | 整合測試 | 驗證 Worker 子進程專用 IPC FD 不被孫進程繼承、裸寫 `fd 1` 不破壞 `task_finish` 且 `sys.stdin` 讀取立即返回 EOF | FR-02, EC-01, EC-03 | `python3 yscb.py dev test server --no-build` |
| **FT-03** | 整合測試 | 驗證 Master 送出 `heartbeat` 保活，且 Client 斷線逾寬限期後自動強殺卡死 Worker 並恢復後續派發 | FR-03, EC-02 | `python3 yscb.py dev test server --no-build` |
| **FT-04** | 單元測試 | 驗證 `stop()` 後 `restart_worker()` 不會復活孤兒進程，且前景執行中模組異動改走延遲重載不腰斬任務 | FR-04 | `python3 yscb.py dev test server --no-build` |
| **FT-05** | 單元測試 | 驗證 `GDriveSync` 無變更輪詢不觸發 `touch_activity`、前景活躍時禮讓且自身拉取不自我喚醒，以及 `SpaceWatcher` 最大防抖上限與 I/O 逾時參數 | FR-05, NFR-01 | `python3 yscb.py dev test gdrive-support --no-build` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `core` 303/303 (100.0%, `0 ResourceWarning`)：重入旁路、`--json` 跳過更新探測與超時邊界驗證通過 | 2026-11-10 |
| **FT-02** | `Passed` | `server` 71/71 (100.0%, `0 ResourceWarning`)：不可繼承專用 IPC FD、孫進程句柄隔離、`sys.stdin` EOF 與 `owned_ipc_in` 執行緒交接關閉驗證通過 | 2026-11-10 |
| **FT-03** | `Passed` | `server` 71/71 (100.0%, `0 ResourceWarning`)：15s `heartbeat`、斷線寬限強殺、自動熱重建 Worker 並同步更新 `daemon.json` 驗證通過 | 2026-11-10 |
| **FT-04** | `Passed` | `server` 71/71 (100.0%, `0 ResourceWarning`)：停機防孤兒復活、Idle TTL 無存活 Worker 防無限續命、延遲重載與 `_snapshot_gen` 防覆寫驗證通過 | 2026-11-10 |
| **FT-05** | `Passed` | `gdrive-support` 39/39、`knowledge-db` 124/124 (`0 ResourceWarning`)：Idle TTL 保全、前景禮讓喚醒保留與零忙等、延後刷盤、`SpaceWatcher` 5.0s 上限與外部 I/O 逾時驗證通過 | 2026-11-10 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於本地執行 `python yscb.py gdrive pull` 後啟動 `server start -d`，測試連續 CLI 派發與 `Ctrl+C` 中斷後下一條指令秒回無卡頓 | `[跳過/免測]` | 雲端 VM 已完成自動化與新環境模擬驗證，交由本地發布前例行驗收 |
