# 實作任務清單 (Task Breakdown)

> 功能名稱：optional_manifest_and_daemon_cleanup  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Passed  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：修改 `source/core/core/installer.py`，新增 `_check_optional_dependencies` 與單元測試 (FT-01, FT-02)
- [x] **TASK-02**：修改 `source/dev/dev/checker.py`，擴充 `optional` 欄位靜態結構檢核與單元測試 (FT-03, FT-04)
- [x] **TASK-03**：刪除 `source/knowledge-db/knowledge_db/daemon.py` 與 `source/knowledge-db/scripts/hook.core.py` (FR-04, FR-05)
- [x] **TASK-04**：修改 `source/knowledge-db/scripts/cli.py`，清理對 `daemon.py` 的引用與提示 (FR-05)
- [x] **TASK-05**：修改 `source/knowledge-db/manifest.json`，將 `server` 移至 `optional` (FR-06, FT-06)
- [x] **TASK-06**：執行 `knowledge-db` 與全生態系回歸驗證 (FT-05, FT-07)
- [x] **TASK-07**：文檔同步交付 (`docs/knowledge-db/DESIGN_NOTES.md`, `CHANGELOG.md`)

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
