# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_03_testing_sop_and_subagent_isolation  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash (High)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：修改 `agents_workflow/roadmap.py` 補強 `RoadmapManager.promote_roadmap()`，支援目標目錄已存在 `roadmap.md` 時無損追加合併與移除原來源檔，並於 `tests/test_roadmap.py` 擴充單元測試 (`FR-07`, `ET-05`)
- [x] **TASK-02**：建立 `assets/skills/testing-sop/SKILL.md`（六大測試鐵律 + 自檢清單 + 錨點）與 `references/test_suite_audit_and_purification.md`（`T-01`~`T-06` 體檢模型與純化工作流）(`FR-01`, `FR-02`)
- [x] **TASK-03**：於 `contributes/agents-workflow.json` 註冊 `testing-sop` 技能匯出與 `TESTING_SOP_STANDARDS` Token (`FR-01`)
- [x] **TASK-04**：更新 `assets/standards/AgentsStandards.md` 條件式技能路由表，並於 `phase_04_plan.md`、`phase_05_task.md`、`phase_06_test.md`（雙重守門）及 `plan_modes.md` 植入 `testing-sop` 強制連鎖引用 (`FR-03`)
- [x] **TASK-05**：於 `research/SKILL.md`、`discuss/SKILL.md`（支柱一：唯讀廣域探索）及 `auto/SKILL.md`、`phase_05_task.md`、`phase_06_test.md`（支柱二：序列實作、二振熔斷與 Single-Writer）內化委派協定 (`FR-04`, `FR-05`)
- [x] **TASK-06**：於 `phase_07_walkthrough.md` Step 1 內化支柱三 Fresh-Eyes Review、Untracked 新檔防護與三類硬性審查契約 (`FR-06`)
- [x] **TASK-DOC**：同步更新 `docs/agents-workflow/` 模組手冊、用戶指南與 `DESIGN_NOTES.md`，並更新 `test_plans_model_record.py` 技能預期清冊 (`FR-01`, `NFR-02`)

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

