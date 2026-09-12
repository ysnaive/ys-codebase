# 實作任務清單 (Task Breakdown)

> 功能名稱：cli_dispatch_and_core_guard_sdk  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實裝 Core 守門 SDK (`core.guard.guard_dispatch`) 並於 `core` 模組導出，編寫 `test_guard.py`
- [x] **TASK-02**：升級 `dev.scaffold.Scaffolder`，生成合規宣告 `process(args)` 之 `scripts/cli.py` 範本
- [x] **TASK-03**：升級 `dev.checker.Checker`，實裝 AST 靜態語法檢核（must process, no main, no top-level stmts），編寫 `test_cli_compliance.py`
- [x] **TASK-04**：改造 `yscb.py` 宿主分發層，注入 Dispatch Token 並改以 `process(args)` 調用
- [x] **TASK-05**：生態系既有模組全量遷移對齊（`core`、`dev`、`agents-workflow`、`knowledge-db` 之 `scripts/cli.py`）
- [x] **TASK-06**：全生態系模組單元測試與回歸驗收
- [x] **TASK-DOC**：同步更新 docs 模組手冊與代碼 Docstrings

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 嚴格依據 P01~P04 規格推進 |
