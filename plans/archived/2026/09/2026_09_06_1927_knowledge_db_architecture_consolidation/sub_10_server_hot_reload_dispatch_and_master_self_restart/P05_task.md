# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_10_server_hot_reload_dispatch_and_master_self_restart  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Passed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：修改 `source/server/server/watcher.py`，新增 `_extract_affected_modules`、回調簽名向下相容與防抖機制。
- [x] **TASK-02**：修改 `source/server/server/master.py`，新增 `on_modules_changed` 分流與 `restart_server()` 自重啟邏輯。
- [x] **TASK-03**：修改 `source/server/tests/test_server.py`，編寫 FT-01 ~ FT-03 測試案例並運行驗證。
- [x] **TASK-DOC**：更新 `docs/server/DESIGN_NOTES.md` (DN-08) 與 `docs/server/README.md`。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 尚無偏差 | - |
