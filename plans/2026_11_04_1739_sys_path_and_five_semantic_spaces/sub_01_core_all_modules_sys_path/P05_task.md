# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_01_core_all_modules_sys_path  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：`core.platform` 權威路徑原語實作與匯出（`core/platform/venv.py`、`core/platform/__init__.py`，含 `list_module_search_roots`）
- [x] **TASK-02**：`core` 三大派發入口收斂（`dispatcher.py`、`events.py`、`symbols.py`）與 `core` 單元測試（`test_config.py`、`test_platform.py`）
- [x] **TASK-03**：`server`、`ast`、`file-space`、`knowledge-db`、`agents-workflow`、`vscode-support` 散落補丁拔除、`core.platform` 委派與 `vscode-support` `extraPaths` 模組/源碼自動投影 (`TODO-22`)
- [x] **TASK-04**：`dev` 內部收斂（`runner.py`、`case.py`）與 `Checker` 零豁免靜態 AST 守門實作及單元測試（`checker.py`、`test_checker.py`）
- [x] **TASK-05**：全模組 `@build` 熱部署、回歸測試與三層文檔同步（`docs/core/`、`docs/dev/`、`docs/vscode-support/`）

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
