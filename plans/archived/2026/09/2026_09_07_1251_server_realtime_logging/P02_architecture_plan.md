# 架構設計說明書 (Architecture Design)

> 功能名稱：server_realtime_logging  
> 建立日期：2026-09-07  
> 所屬主計畫：無 (獨立 Full Track)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 模組架構分層與職責邊界 (Layered Architecture)

```text
+-------------------------------------------------------------------------+
|                           Master Supervisor                             |
|  - 持有 ServerLogger 實例 (單一寫入權威)                                  |
|  - 啟動前守門：recover_and_open() (舊日誌解析自癒 -> 輪轉 -> 開啟新日誌)      |
|  - 生命週期記錄：start / reload / shutdown / idle TTL / watcher 變更       |
+-------------------+---------------------------------+-------------------+
                    |                                 |
                    v                                 v
+-----------------------------+     +-------------------------------------+
|    DispatcherHTTPHandler    |     |             Warm Worker             |
| - 攔截 do_GET / do_POST     |     | - pre_warm / task 執行生命週期       |
| - 記錄 API 路徑、狀態碼與耗時 |     | - IPC stdout: {"type":"log",...}    |
+-----------------------------+     +------------------+------------------+
                                                       |
                                    (stdout ndjson)    v
                                    +-------------------------------------+
                                    | Master Worker Stream Interceptor    |
                                    | - 攔截 packet.type == 'log'         |
                                    | - 轉發至 ServerLogger.log()         |
                                    +------------------+------------------+
                                                       |
                                                       v
+-------------------------------------------------------------------------+
|                        ServerLogger (即時 Flush)                         |
|  - 檔案位址：cache://server/log                                         |
|  - 線程安全：threading.Lock() 保護寫入與 flush                            |
|  - 歷史輪轉：{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}_log (嚴格保留最新 5 份)       |
+-------------------------------------------------------------------------+
```

---

## 2. 核心資料流與循序圖 (Data Flow & Sequence Diagram)

```mermaid
sequenceDiagram
    autonumber
    participant CLI as yscb.py / CLI
    participant Master as MasterSupervisor
    participant Logger as ServerLogger
    participant Worker as WarmWorker

    Note over Master, Logger: Phase A: 伺服器啟動與歷史自癒
    Master->>Logger: recover_and_open()
    alt 發現未歸檔舊 log
        Logger->>Logger: 讀取首行解析 start at time
        alt 解析失敗
            Logger->>Logger: 退化使用 mtime 格式化時間戳
        end
        Logger->>Logger: rename 舊 log ➔ {timestamp}_log
        Logger->>Logger: 執行 5 份歷史檔案滾動清理
    end
    Logger->>Logger: 建立全新 cache://server/log
    Logger->>Logger: 寫入首行: server start at time "..." (flush)
    Master->>Logger: log(INFO, "MasterSupervisor started PID: ...")

    Note over Master, Worker: Phase B: Worker 啟動與 IPC 日誌匯流
    Master->>Worker: spawn_worker()
    Worker-->>Master: stdout {"type": "log", "msg": "Worker pre_warm completed"}
    Master->>Logger: log(INFO, "Worker pre_warm completed") (flush)

    Note over CLI, Worker: Phase C: 任務派發與請求記錄
    CLI->>Master: POST /api/dispatch
    Master->>Logger: log(INFO, "Dispatch task: module=knowledge-db, cmd=search")
    Master->>Worker: send request stdin
    Worker-->>Master: stdout {"type": "log", "msg": "Loaded module cache"}
    Master->>Logger: log(INFO, "Loaded module cache") (flush)
    Worker-->>Master: stdout {"type": "task_finish", "exit_code": 0}
    Master-->>CLI: HTTP 200 chunked finish
    Master->>Logger: log(INFO, "Task finished: exit=0, duration=12.5ms") (flush)

    Note over Master, Logger: Phase D: 優雅停機與歷史歸檔
    Master->>Logger: log(INFO, "Server stopping gracefully...")
    Master->>Logger: archive_and_close()
    Logger->>Logger: 關閉檔案 Handle
    Logger->>Logger: rename 當前 log ➔ {start_timestamp}_log
    Logger->>Logger: 執行 5 份歷史檔案滾動清理
```

---

## 3. 受影響檔案與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `source/server/server/logger.py` | New | 實作 `ServerLogger`，封裝及時 flush、自癒解析、5 份滾動與格式化器 |
| `source/server/server/master.py` | Modify | 整合 `ServerLogger`，於啟停、HTTP 處理、Worker 串流攔截處記錄日誌 |
| `source/server/server/worker.py` | Modify | 於 `WarmWorker` 預熱與任務關鍵節點發送 `{"type": "log"}` 封包 |
| `source/server/tests/test_server_logging.py` | New | 編寫單元測試、滾動測試、異常中斷自癒測試與多進程 IPC 匯流測試 |

---

## 4. 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 權威單一寫入原則**：僅由 Master 擁有日誌檔案之寫入 Handle，子進程（Worker）嚴禁直接打開同一個 log 檔案進行 append。所有子進程日誌皆透過 IPC 協議送至 Master 集中落檔，消除 OS 等級的跨進程鎖開銷與交錯寫入風險。
- **[P02:DR-02] 雙重歷史歸檔防禦 (Graceful + Crash-Safe Recovery)**：
  - 常態模式：`stop()` 時呼叫 `archive_and_close()`，將當前 log 轉為歷史檔並保持 $\le 5$ 份。
  - 異常中斷自癒：若上次是非正常退出（如 SIGKILL、斷電），`start()` 前呼叫 `recover_and_open()`，主動檢查殘留 log 並完成歸檔輪轉。
- **[P02:DR-03] 正則約束與孤兒保護**：歷史檔名正則固定為 `^\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2}_log$`。非符合該格式之檔案絕對不予觸動，保障其他快取資產安全。
