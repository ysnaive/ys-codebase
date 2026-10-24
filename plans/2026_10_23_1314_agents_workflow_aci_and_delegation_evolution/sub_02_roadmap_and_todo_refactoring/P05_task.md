# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_02_roadmap_and_todo_refactoring  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：新增 `assets/templates/todo.md` 模板並升級 `assets/templates/roadmap.md` 標頭欄位 (`> 目標範疇：`、`> 前置解鎖條件：`)
- [x] **TASK-02**：於 `agents_workflow/roadmap.py` 實作 `TodoItem`/`TodoManager` (`add_todo`, `list_todos`, `promote_todos`) 與 `RoadmapManager.promote_roadmap` 及 `--status` 過濾
- [x] **TASK-03**：於 `agents_workflow/plans/{status.py,scanner.py,verifier.py}` 實作 `ORIGIN_SEED_FILES` (`roadmap.md` / `todo.md`) 前置資產白名單與 `Seeded` 狀態領航
- [x] **TASK-04**：更新 `scripts/cli.py`、`contributes/{core,agents-workflow}.json`，新增 `assets/skills/todo/SKILL.md` 並更新 `roadmap`、`new-plan`、`development-sop`、`discuss`、`research`、`yscb-cli-guide` 技能手冊
- [x] **TASK-05**：於 `tests/test_plans_toolchain.py` 編寫完整單元與邊界測試 (`FT-01`~`FT-06`, `ET-01`~`ET-06`, `RT-01`~`RT-02`)，通過 `dev check` / `dev test` 並執行 `@build` 熱部署與 `release`
- [x] **TASK-DOC**：同步更新 `docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}` (`[DN-AW-11]`) 與公開 API Docstring

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
