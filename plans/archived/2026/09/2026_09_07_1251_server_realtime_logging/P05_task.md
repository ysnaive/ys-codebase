# 實作任務清單 (Task Breakdown)

> 功能名稱：server_realtime_logging  
> 建立日期：2026-09-07  
> 所屬主計畫：無 (獨立 Full Track)  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：建立 `source/server/server/logger.py`，實作 `ServerLogger`（即時 flush、首行格式、異常自癒、歷史檔案滾動與首行時間解析）。
- [x] **TASK-02**：更新 `source/server/server/master.py`，於 `MasterSupervisor` 整合 `ServerLogger`，涵蓋啟動自癒、生命週期記錄、HTTP 請求攔截與停機優雅歸檔。
- [x] **TASK-03**：更新 `source/server/server/worker.py` 與 `master.py`，新增 Worker 關鍵事件 IPC 日誌封包發送與 Master 端攔截匯流。
- [x] **TASK-04**：建立 `source/server/tests/test_server_logging.py`，編寫 FT-01 ~ FT-08 自動化測試套件。
- [x] **TASK-05**：執行測試套件與全量回歸（FT-01~08 與 RT-01 全數綠燈通過）。
- [x] **TASK-DOC**：補齊文檔與 Docstrings（更新 `docs/server/` 與代碼註解）。
- [x] **TASK-06**：偏差修復：修復 `core:update` 忽略 `@build` 版本之缺陷（`Installer.cmd_update` 略過已安裝 `@build` 模組，且候選版本過濾 `.build`）。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-06** | `Major` | 開發者實機驗收期間發現 `python yscb.py update` 誤將開發中之 `@build` 模組降級覆蓋為歷史 release 包，經開發者指示併入本計畫偏差修復。 | 於 `source/core/core/installer.py` 中增加 `@build` 跳過邏輯與候選版本過濾，並編寫單元測試驗證。 |
