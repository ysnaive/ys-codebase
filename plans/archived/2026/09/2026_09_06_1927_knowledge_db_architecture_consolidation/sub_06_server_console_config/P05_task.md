# 實作任務清單 (Task Breakdown)

> 功能名稱：server_console_config  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Passed  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：新增 `source/server/server/config.py`，實作 `ServerConfig` 資料類別與 `core.config` 對接 (FR-01, EC-02)
- [x] **TASK-02**：修改 `source/server/scripts/cli.py`，重構 `_handle_start` 參數解析為互斥群組並加入 `_resolve_enable_console` (FR-02, FR-03, EC-01)
- [x] **TASK-03**：新增 `source/server/tests/test_server_config.py`，編寫 FT-01 ~ FT-05 單元測試 (FT-01~05)
- [x] **TASK-04**：執行 `server` 單元測試與靜態合規性檢驗 (FT-06, FT-07)
- [x] **TASK-05**：文檔同步交付 (`docs/server/DESIGN_NOTES.md`, `source/server/contributes.format.md`)

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
