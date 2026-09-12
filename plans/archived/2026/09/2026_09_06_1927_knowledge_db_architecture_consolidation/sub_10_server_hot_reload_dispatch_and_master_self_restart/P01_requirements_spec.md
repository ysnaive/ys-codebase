# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_10_server_hot_reload_dispatch_and_master_self_restart  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 變更路徑模組歸屬感知 | `ModulesWatcher` 比對快照時，除偵測變更外，需識別受影響的模組清單 (`affected_modules`)，解析變更檔案相對 `.modules/` 的頂層目錄名稱。 | P0 | [P00:DR-01] |
| **FR-02** | 雙軌重載決策分流 | 依 `affected_modules` 分流：<br/>1. 包含 `server` 或 `core` ➔ 觸發 `restart_server()`。<br/>2. 僅包含其他領域模組 (如 `knowledge-db`, `dev`, `agents-workflow`) ➔ 觸發 `restart_worker()`。 | P0 | [P00:DR-02] |
| **FR-03** | Master 優雅自重啟機制 | `MasterSupervisor` 實作 `restart_server()`：以原參數拉起新 Master 進程，並安全釋放鎖與關閉舊 Master 進程資源，達成平滑自重啟。 | P0 | [P00:DR-03] |
| **FR-04** | 變更感知防抖 (Debounce) | 為避免模組解壓或覆蓋多檔案時連續高頻觸發多次重啟，`ModulesWatcher` 引入變更防抖 (如 500ms)，聚合批量變更後一次性判定分流。 | P1 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 安裝中途暫存檔案或檔案突然刪除 | 走訪 `.modules/` 計算 mtime 時捕獲 `FileNotFoundError` / `PermissionError`，安全略過不拋出例外中斷 watcher 線程。 |
| **EC-02** | 變更檔案不屬於任何已知模組 (例如根目錄臨時檔) | 歸類為非關鍵變更或預設僅重啟 Worker，不盲目觸發 Master 重啟。 |
| **EC-03** | Master 自重啟進程鎖爭碰 | 新 Master 啟動時需確保舊 Master 能在超時前關閉 HTTP 與釋放檔案鎖，或由舊 Master 發起脫鉤拉起後主動釋放鎖。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 資源 | Worker 重啟延遲 $\le 500\text{ms}$；Watcher 每秒輪詢資源開銷 CPU $< 0.1\%$。 |
| **NFR-02** | 相容性 | 保持既有 CLI `python yscb.py server reload` 與 HTTP `/api/reload` API 契約向下相容。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：Windows/Linux 跨平台拉起 detached 進程需統一依賴 `core.platform.spawn_detached`，避免僵屍進程或控制台窗口跳出。
