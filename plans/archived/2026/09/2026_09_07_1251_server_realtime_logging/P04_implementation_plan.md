# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：server_realtime_logging  
> 建立日期：2026-09-07  
> 所屬主計畫：無 (獨立 Full Track)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書中均有明確之類別方法與職責分配（`ServerLogger` 與 `MasterSupervisor`）。
- [x] **邊界防護**：EC-01 ~ EC-06（首行損毀退化 mtime、同名衝突序號遞增、正則保護非相關快取檔案、Worker 崩潰捕獲等）皆具備具體防禦邏輯。
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-03 指標約束，無外部 logging 套件，flush 與滾動開銷極小。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/server/README.md` | Modify | 補充即時 Flush 日誌、歷史滾動機制與排查日誌路徑說明 |
| **專題手冊** | `docs/server/realtime_logging.md` | New | 詳細記載 ServerLogger 架構、異常自癒規則、日誌格式與 IPC 匯流設計 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 記錄 DN-08 即時 Flush 與啟動異常自癒之架構考量 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 Phase 7 結案時的變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：Server 若遭受 `kill -9` 或斷電等未受控強殺，日誌是否會丟失？下次重啟如何恢復？  
> 💡 **防護解法**：`ServerLogger` 每次寫入均執行 `file.flush()`，強制將應用層緩衝刷入作業系統 Page Cache，杜絕非正常退出時的丟失。下次新 Server 啟動時，`recover_and_open()` 會在建立新日誌前優先檢查殘留之舊 `log`，讀取首行啟動時間標誌將其歸檔為歷史檔，並保持 $\le 5$ 份滾動，確保歷史鏈路連續完整。

> ❓ **尖銳問題 2**：滾動清理時，如果日誌目錄下同時存在 `daemon.json`、`daemon.lock` 等其他 server 快取檔案，會不會被誤刪？  
> 💡 **防護解法**：`clean_rolling_history()` 嚴格以正規表示式 `^\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2}_log$` 進行完整匹配（`re.match` 且排除目錄），任何不完全符合該格式的檔案均直接跳過，絕不誤傷系統快取。

> ❓ **尖銳問題 3**：Worker 任務輸出可能非常巨大（如數千行代碼掃描結果），會不會導致 Server 日誌暴增？  
> 💡 **防護解法**：遵循 P00 邊界排除原則，Worker 執行任務時的 stdout/stderr 串流全文由現有 ndjson chunk 專門回傳呼叫端，ServerLogger 僅記錄任務啟動（module/cmd/args）與任務結束摘要（exit_code/duration），維持日誌精簡乾淨。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：建立 `source/server/server/logger.py`，實作 `ServerLogger`（即時 flush、首行格式、異常自癒、歷史檔案滾動與首行時間解析）。
- [ ] **TASK-02**：更新 `source/server/server/master.py`，於 `MasterSupervisor` 整合 `ServerLogger`，涵蓋啟動自癒、生命週期記錄、HTTP 請求攔截與停機優雅歸檔。
- [ ] **TASK-03**：更新 `source/server/server/worker.py` 與 `master.py`，新增 Worker 關鍵事件 IPC 日誌封包發送與 Master 端攔截匯流。
- [ ] **TASK-04**：建立 `source/server/tests/test_server_logging.py`，編寫 FT-01 ~ FT-08 自動化測試套件。
- [ ] **TASK-05**：執行測試套件與全量回歸（FT-01~08 與 RT-01 全數綠燈通過）。
- [ ] **TASK-DOC**：補齊文檔與 Docstrings（更新 `docs/server/` 與代碼註解）。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性鎖定歷史正則與保留上限**：正則為 `^\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2}_log$`，嚴格保留最新 5 份歷史檔案。
- **[P04:DR-02] 首行時間戳優先退化 mtime 策略**：啟動自癒時優先以 `^server start at time "(\d{4}_\d{2}_\d{2}_\d{2}\.\d{2}\.\d{2})"` 提取歷史時間戳；失敗時以檔案 `mtime` 退化，確保 100% 不阻斷啟動。
