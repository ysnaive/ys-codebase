# 實作任務清單 (Task Breakdown)

> 功能名稱：工作流流程架構與提示詞設計調研與優化 (Workflow Process Architecture & Prompt Refinement)  
> 建立日期：2026-10-18  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新 `ys_codebase/source/agents-workflow/assets/templates/` 下 9 份標準模板（`P00_discuss.md`、`P01_requirements_spec.md`、`P03_api_spec.md`、`P04_implementation_plan.md`、`P07_walkthrough.md`、`fast_track_plan.md`、`revision_log.md`、`roadmap.md`、`changelog.md`），落實 `FR-04`、`FR-05`、`FR-07`、`FR-08` 與 `EC-01` ~ `EC-04`。
- [x] **TASK-02**：更新 L0/L1 全域治理與入口技能資產（`assets/standards/AgentsStandards.md`、`assets/skills/context-init/SKILL.md`、`assets/skills/yscb-cli-guild/SKILL.md`、`assets/skills/new-plan/SKILL.md`、`assets/skills/research/SKILL.md`、`assets/skills/roadmap/SKILL.md`），落實 `FR-01`、`FR-04`、`FR-08`。
- [x] **TASK-03**：更新 L2/L3 核心 SOP 與流程控制技能資產（`assets/skills/development-sop/SKILL.md`、`references/plan_modes.md`、`references/phase_00_discuss.md`、`references/phase_01_requirements.md`、`references/phase_03_api_spec.md`、`references/phase_07_walkthrough.md`、`assets/skills/pause/SKILL.md`、`assets/skills/continue/SKILL.md`、`assets/skills/discuss/SKILL.md`、`assets/skills/auto/SKILL.md`、`assets/skills/session-analysis/SKILL.md`），落實 `FR-02`、`FR-03`、`FR-04`、`FR-05`、`FR-06`、`FR-08`。
- [x] **TASK-04**：於 `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py` 新增單元測試（`FT-04` ~ `FT-06`）覆蓋 `FR-01` ~ `FR-08`，並檢視確認 `author_guide_and_checklist.md` 已符合三層文檔架構。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| TASK-04 | Minor | `P04 §2` 原列 `docs/agents-workflow/author_guide_and_checklist.md`，實查該專題手冊位於 `ys_codebase/source/agents-workflow/assets/skills/documentation/references/author_guide_and_checklist.md` 且其 §1 與 §3 已完整採用 `<Category>` 與宏觀/中觀/微觀三層定義 | 檢視確認已 100% 對齊，無需額外改動 |

