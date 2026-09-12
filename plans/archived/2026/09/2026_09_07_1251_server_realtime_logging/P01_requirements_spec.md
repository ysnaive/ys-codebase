# 需求規格說明書 (Requirements Specification)

> 功能名稱：server_realtime_logging  
> 建立日期：2026-09-07  
> 所屬主計畫：無 (獨立 Full Track)  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 即時 Flush 日誌引擎 | 實作 `ServerLogger`，日誌檔案固定存放於 `cache://server/log`，所有寫入必須即時執行 `flush()`，杜絕進程非正常終止時緩衝區丟失 | P0 | [P00:DR-01], [P00:DR-04] |
| **FR-02** | 啟動起始標誌寫入 | 新 Server 啟動建立新 `log` 時，首行固定寫入 `server start at time "{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}"`，作為時間基準與有效性錨點 | P0 | [P00:DR-01] |
| **FR-03** | 異常中斷偵測與自癒歸檔 | 新 Server 啟動若偵測到已存在 `log`（未正常歸檔之舊日誌），優先解析首行啟動時間轉存為 `{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}_log`；解析失敗自動退化以 mtime 命名 | P0 | [P00:DR-03] |
| **FR-04** | 歷史日誌 5 份滾動保留 | 歷史日誌檔案遵循 `{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}_log`，每次產生新歷史檔後自動掃描目錄，保留最新 5 份，超過者自動清理，維持總數 $\le 5$ | P0 | [P00:DR-05] |
| **FR-05** | 標準平衡級資訊量記錄 | 涵蓋 Server 生命週期（啟停/PID/Port/TTL/Reload）、HTTP 請求（路徑/狀態碼/耗時）、任務派發摘要（module/cmd/args/exit_code/耗時）、Watcher 感知與異常堆疊 | P0 | [P00:DR-02] |
| **FR-06** | Master 集中管理與 Worker IPC 匯流 | Master 獨佔日誌檔案寫入 Handle，Worker 透過 IPC ndjson 封包回傳日誌事件，由 Master 集中寫入並 flush，避免跨進程競爭 | P0 | [P00:DR-04] |
| **FR-07** | 正常停機主動歷史歸檔 | Server 優雅停機（Graceful Shutdown）時，寫入停機時間戳，關閉檔案 Handle 並自動將當前 `log` 歸檔為歷史檔案，連動執行 5 份滾動清理 | P0 | [P00:DR-01], [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 舊 `log` 檔案為空或首行損毀/無啟動標誌 | 啟動偵測時使用正則解析首行，若無匹配則安全退化採用該檔案之最後修改時間 (`mtime`) 格式化為歷史檔名，不拋出例外阻斷啟動 |
| **EC-02** | 歷史檔名發生同名衝突 | 轉存歷史時若目標檔名已存在，自動於秒數後附加序號（如 `_01_log`）避免覆蓋舊有歷史日誌 |
| **EC-03** | 目錄存在不符合命名格式之無關檔案 | 滾動清理時嚴格以正則 `^\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2}_log$` 過濾，嚴禁誤刪 `daemon.json`、`daemon.lock` 等系統檔 |
| **EC-04** | 歷史日誌總數不足 5 份 | 滾動清理演算法在 `len(history_files) <= 5` 時不觸發刪除，安全返回 |
| **EC-05** | Worker 子進程異常崩潰中斷連線 | Master 在 `dispatch_task` 中捕獲 stdout EOF 或 JSON 異常，立即向 `ServerLogger` 記錄 Worker 崩潰事件與錯誤堆疊 |
| **EC-06** | 日誌寫入並發線程安全 | `ServerLogger` 內部採用 `threading.Lock()` 保護檔案寫入與 flush 操作，確保多線程並發調用無交錯字元 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴 | 100% 使用 Python 標準庫 (`logging`, `datetime`, `re`, `threading`) 與微內核 `core.vfs` 原語，不引入第三方 logging 庫 |
| **NFR-02** | 寫入效能 | 單次日誌寫入與 `flush()` 耗時 $< 1.0\text{ms}$，不顯著拖慢 HTTP 請求與 CLI 派發 |
| **NFR-03** | 滾動開銷 | 歷史檔案輪轉掃描與清理耗時 $< 10\text{ms}$，於啟動與停機時同步執行 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!IMPORTANT]` Windows 檔案佔用與 Renaming**：Windows 平台下若檔案處於被開啟狀態無法直接 rename，在執行歷史轉存前必須確認前置 handle 已關閉或為全新進程接管。
- **`[!NOTE]` 空間協議對齊**：日誌目錄路徑透過 `core.uri.resolve("cache://server")` 或 `os.path.join(yscb_root, ".cache", "server")` 取得，嚴禁寫入硬編碼相對路徑。
