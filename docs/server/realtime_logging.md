---
target: "Server/RealtimeLogging"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb://source/server/server/logger.py"
  - "yscb://source/server/server/master.py"
  - "yscb://source/server/server/worker.py"
related_docs:
  - "./README.md"
  - "./daemon_architecture.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-10-15"
---

# Server 即時 Flush 日誌與歷史滾動自癒指南 (Realtime Logging & Crash Recovery)

> 適用模組：`server` (`v1.0.0+`)  
> 核心類別：`server.logger.ServerLogger`、`server.master.MasterSupervisor`

---

## 1. 架構概述 (Architecture Overview)

Server 模組內建集中式即時 flush 日誌、Console 雙向 Tee 回顯與啟動歷史自癒機制，以滿足背景守護進程與前台除錯模式的運維可觀測性與極限中斷下的日誌完整性：

1. **即時 Flush (Zero-Buffered Disk Write)**：
   - 當前運行中日誌固定存放於語意路徑 `cache://server/log`（實體路徑為 `.cache/server/log`）。
   - 所有日誌行在寫入時強制調用 `file.flush()`，直接將用戶空間緩衝刷入作業系統 Page Cache，杜絕 `kill -9`、進程崩潰或斷電時的日誌丟失。
2. **Console 雙向 Tee 實時回顯 (`echo_console`)**：
   - `ServerLogger` 支援 `echo_console: bool = False` 參數。
   - 當透過 `python yscb.py server start --console`（或設定檔 `enable_console: true`）以前台控制台模式啟動時，`echo_console` 設為 `True`：每一筆日誌除強制寫入並 `flush()` 至 `.cache/server/log` 磁碟檔案外，**同步 Tee 輸出至 `sys.stdout` 並立即 flush**，實現終端機即時串流觀測與持久化留痕雙軌兼顧。
3. **啟動歷史自癒 (Crash Recovery Archival)**：
   - 新 Server 啟動時，若偵測到目錄下遺留未正常歸檔之舊 `log` 檔案，在建立新日誌前會優先將其歸檔為歷史日誌 `{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}_log`（若同秒內發生多次重啟衝突，自動附加 `_{NN}` 兩位數序號後綴如 `_01_log`）。
   - 時間戳判定優先解析舊日誌首行的啟動標誌；若首行損毀或無標誌則安全退化為該檔案之最後修改時間 (`mtime`)。
4. **歷史檔案 5 份滾動保留與同秒序號後綴防呆 (`HIST_REGEX`)**：
   - `ServerLogger` 歷史檔案匹配正則 `HIST_REGEX` 定義為 `^\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2}(?:_\d{2})?_log$`，**完整支援 `_01` 等同秒碰撞序號後綴**。
   - 每次產生新歷史檔案（無論優雅關閉或高頻異常重啟自癒）後，所有符合 `HIST_REGEX` 之歷史檔案均納入排序，自動保留最新 5 份並刪除超額之最舊檔案，杜絕異常重啟產生的序號後綴檔案逃逸滾動清理。
5. **單一寫入權威與 IPC 匯流 (Master-Only Handle & Worker IPC)**：
   - 僅由 Master Supervisor 掌管檔案寫入 Handle。
   - Warm Worker 子進程與任務若有需記錄之日誌，透過 stdout 串流發送 `{"type": "log", "level": "...", "msg": "..."}` 封包，由 Master 集中攔截並寫入，徹底根絕跨進程競爭與 Windows 檔案佔用鎖死問題。

---

## 2. 日誌格式規範 (Log Format Specification)

### 2.1 啟動起始標誌 (Start Banner)
新日誌建立後，首行固定寫入時間基準錨點：
```text
server start at time "{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}"
```
*範例：`server start at time "2026_09_07_12.55.30"`*

### 2.2 標準平衡級日誌行 (Standard Balanced Log Line)
```text
[{YYYY}-{MM}-{DD} {HH}:{MM}:{SS}.{fff}] [{PID}] [{LEVEL}] [{COMPONENT}] {MESSAGE}
```
*範例：*
```text
[2026-09-07 12:55:30.145] [53891] [INFO] [master] Starting MasterSupervisor (PID: 53891, Root: /workspace/ys-codebase, Idle TTL: 900.0s)
[2026-09-07 12:55:30.160] [53891] [INFO] [master] HTTP Server listening on dynamic port 127.0.0.1:41923
[2026-09-07 12:55:30.185] [53891] [INFO] [worker] Warm worker pre_warm completed in 12.3ms (PID: 53902)
[2026-09-07 12:55:35.210] [53891] [INFO] [master] Task dispatch requested: module='knowledge-db', args=['search', 'core']
[2026-09-07 12:55:35.245] [53891] [INFO] [master] Task dispatch finished: module='knowledge-db', exit_code=0, duration=34.8ms
[2026-09-07 12:55:35.246] [53891] [INFO] [master] HTTP POST /api/dispatch -> 200 (36.1ms)
```

### 2.3 優雅停機標誌 (Shutdown Banner)
```text
[2026-09-07 13:10:30.500] [53891] [INFO] [master] Server stopped gracefully at time "2026_09_07_13.10.30"
```

---

## 3. 生命週期與自癒循序圖 (Lifecycle & Self-Healing Sequence)

```mermaid
sequenceDiagram
    autonumber
    participant CLI as yscb.py CLI
    participant Master as MasterSupervisor
    participant Logger as ServerLogger
    participant Worker as WarmWorker

    Note over Master, Logger: 步驟 1: 啟動檢查與異常自癒
    Master->>Logger: recover_and_open(echo_console=...)
    alt 發現舊 log 檔案存在 (前次異常中斷)
        Logger->>Logger: 讀取首行解析 start at time
        alt 解析成功
            Logger->>Logger: target = {parsed_time}[_NN]_log
        else 解析失敗 (檔案損毀/無標誌)
            Logger->>Logger: target = {mtime}[_NN]_log
        end
        Logger->>Logger: rename log -> target
        Logger->>Logger: clean_rolling_history() (依 HIST_REGEX 保持 <= 5 份)
    end
    Logger->>Logger: 開啟新 log 檔案並寫入首行標誌 (立即 flush)

    Note over Master, Worker: 步驟 2: 運作期間、IPC 匯流與 Console Tee
    Master->>Logger: log Master 事件 (PID, Port, Watcher, TTL)
    Worker-->>Master: stdout {"type": "log", "msg": "pre_warm done"}
    Master->>Logger: 集中寫入 Worker 日誌 (立即 flush 至磁碟；若 echo_console=True 同步 Tee 至 stdout)

    Note over Master, Logger: 步驟 3: 優雅停機與歷史歸檔
    Master->>Logger: archive_and_close()
    Logger->>Logger: 寫入關閉日誌行並關閉 Handle
    Logger->>Logger: rename 當前 log -> {start_time}[_NN]_log
    Logger->>Logger: clean_rolling_history() (依 HIST_REGEX 保持 <= 5 份)
```
