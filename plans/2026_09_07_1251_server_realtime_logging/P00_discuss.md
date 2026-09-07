# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：server_realtime_logging  
> 建立日期：2026-09-07  
> 所屬主計畫：無 (獨立 Full Track)  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  於 server module 添加即時 flush 的 log 檔案，預計於 `cache://` 儲存成：
  - `log` - 當前運行中的 server 及時 log 檔案
  - `{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}_log` - 歷史運行檔案，符合該命名格式的，滾動保留 5 份 (儲存新的後，確認 <= 5 份)
  - 須注意為避免 server 是異常中斷，新 server 啟動時須先處理舊有 log，未儲存成歷史的話，要先處理 (server 啟動需先 log server start at time `"{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}"`)
  - 需額外詳細討論預計 log 的資訊量
- **核心目標**：
  1. **及時落檔與防崩潰丟失 (Immediate Flush)**：日誌寫入時具備即時 flush 行為，確保即使進程被非正常終止，日誌依然完整保留。
  2. **歷史檔案滾動 (Rolling History)**：歷史檔案遵循 `{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}_log` 命名規則，嚴格保留最新 5 份，超過時自動清理最舊者。
  3. **異常中斷自癒轉存 (Crash Recovery & Archival)**：新 Server 啟動時主動偵測上一任殘留之 `log`，先完成歷史歸檔與輪轉清理，再建立全新 `log`。
  4. **啟動標誌錨點 (Server Start Banner)**：全新 `log` 建立後，首行寫入 `server start at time "{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}"`。
  5. **標準平衡級資訊量 (Balanced Observability)**：覆蓋伺服器生命週期、HTTP 請求端點、任務派發摘要、模組熱重載感知與異常堆疊。
  6. **集中式多進程匯流 (Centralized IPC Logging)**：由 Master Supervisor 集中管理檔案 Handle 與即時 Flush，Worker 透過 IPC 串流回傳日誌，避免跨進程檔案鎖衝突與交錯寫入。
- **邊界排除 (Explicitly Excluded)**：
  - **排除任務輸出傾倒**：不在 Server Log 中無節制傾倒個別 CLI 任務產生的完整 stdout/stderr 串流全文（該串流由現有 ndjson chunk 專門回傳呼叫端）。
  - **排除外部重型套件**：嚴禁引進額外日誌依賴，100% 採用 Python 標準庫與微內核 VFS 原語。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 時間戳與歷史檔名格式**：
  - 確定採日時分秒點分隔格式：`{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}`。
  - 範例歷史檔名：`2026_09_07_12.51.30_log`。
  - 首行啟動格式：`server start at time "2026_09_07_12.51.30"`。
- **[P00:DR-02] Log 資訊量層級定義 (標準平衡級 Standard)**：
  - **Lifecycle**：Master 啟動/停止、Port 綁定、Idle TTL 狀態、自我重啟、Worker 進程拉起與退出。
  - **HTTP API**：HTTP 請求方法、路徑、回應狀態碼、處理耗時（ms）。
  - **Task Dispatch**：任務派發模組名稱、指令名稱、參數摘要、結束狀態碼（exit_code）、執行耗時（ms）。
  - **Subsystems**：Worker 預熱完成廣播、Watcher 模組變更感知事件（affected modules）、Service Workers 註冊與狀態。
  - **Exceptions**：捕獲之異常型別、訊息與完整 Stacktrace。
- **[P00:DR-03] 異常中斷舊 Log 歷史檔名時間戳判定**：
  - 新 Server 啟動時若發現未封存之 `log`，優先讀取該舊 `log` 第一行嘗試解析其記錄之啟動時間字串。
  - 若舊 Log 首行不合規範或損毀，自動退化採用該舊 Log 檔案之最後修改時間 (`os.path.getmtime`)。
- **[P00:DR-04] 多進程日誌寫入架構**：
  - 由 Master Supervisor 掌管 `cache://server/log` 的檔案 Handle，封裝即時 flush 邏輯。
  - Worker 子進程若有需記錄之事件，透過 stdout ndjson 協議發送 `{"type": "log", "level": "...", "msg": "..."}` 由 Master 集中寫入，根絕多進程競爭。
- **[P00:DR-05] 滾動清理與保留策略**：
  - 歷史檔案匹配正則：`^\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2}_log$`。
  - 每次新增歷史日誌後，列舉目錄下所有匹配檔案依時間排序，若總數 > 5 份，刪除最舊的檔案，嚴格確保歷史檔案數量 $\le 5$。

---

## 3. 開放議題與確認紀錄

- [x] 時間戳格式敲定為 `{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}`。
- [x] 資訊量層級敲定為「標準平衡級」。
- [x] 舊 Log 異常自癒轉存之時間戳判定規則敲定。
- [x] 多進程 Master 集中寫入架構敲定。
