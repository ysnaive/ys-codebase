# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_02_skills_architecture  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新 `source/agents-workflow/contributes/agents-workflow.json` 與 `contributes.format.md`，為 `antigravity`、`claude`、`codex` 加入 `projections.skill` 宣告，並對齊 `codex` 專案路徑至 `project://.agents/`。
- [x] **TASK-02**：擴充 `source/agents-workflow/agents_workflow/compiler.py`，實作 `_scan_directory_files`，支援目錄級 export 掃描與保留 `rel_path` 的 Stage 1 快取。
- [x] **TASK-03**：擴充 `source/agents-workflow/agents_workflow/publisher.py`，支援 `projections.skill`、目錄巨集插值、多檔案 Stage 2 解析與 Gitignore 精確忽略。
- [x] **TASK-04**：更新單元測試套件 `source/agents-workflow/tests/test_compiler.py`、`test_publisher.py`、`test_targets.py`，覆蓋 FT-01~07、ET-01~03。
- [x] **TASK-DOC**：同步更新 `docs/agents-workflow/README.md` 與 `user_guide.md`。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
