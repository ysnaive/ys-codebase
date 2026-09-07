# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_10_server_hot_reload_dispatch_and_master_self_restart  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書中有對應介面 (`_extract_affected_modules`, `on_modules_changed`, `restart_server`)
- [x] **邊界防護**：EC-01 ~ EC-03 有具體錯誤處理策略 (路徑解析異常略過、無參回調相容、優雅釋放鎖)
- [x] **依賴純淨**：符合 NFR-01/02 指標約束，嚴格使用標準庫與 `core.platform`

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 登記 DN-08: 雙軌重載分流 (Worker vs Master 自重啟) 與路徑模組感知規範 |
| **模組手冊** | `docs/server/README.md` | Modify | 更新模組熱重載機制說明：領域模組單重啟 Worker，server/core 自動重啟整機 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當舊 Master 自重啟拉起新 Master 時，是否會因 InterProcessLock 或埠位被舊進程占用而導致新 Master 啟動失敗？  
> 💡 **防護解法**：舊 Master 在觸發 `restart_server()` 時，先依序執行 `self.stop()`（停止 watcher、結束 service workers、關閉 HTTP socket 並移除 `.cache/server/daemon.json` 與 lock），隨後透過 `core.platform.spawn_detached` 啟動新進程，最後由舊進程乾淨退出 (`sys.exit(0)`)，100% 杜絕鎖與通訊埠競爭。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：修改 `source/server/server/watcher.py`，新增模組路徑解析 `_extract_affected_modules`、回調簽名向下相容與防抖機制。
- [ ] **TASK-02**：修改 `source/server/server/master.py`，新增 `on_modules_changed` 分流與 `restart_server()` 自重啟邏輯。
- [ ] **TASK-03**：修改 `source/server/tests/test_server.py`，新增 FT-01 ~ FT-03 測試案例並實跑驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 變更分流白名單與兜底原則**：
  - 核心/守護模組清單：`{"server", "core"}` 變更時強制觸發 `restart_server()`。
  - 其餘模組或未知路徑變更：僅觸發 `restart_worker()`，杜絕非必要的全機重啟。
