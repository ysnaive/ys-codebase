# 實作任務清單 (Task Breakdown)

> 功能名稱：跨模組組態體檢教練 (/how-to-config-yscb)、互動式上手領航教練 (/how-to-yscb) 與專案角色邊界錨點建設 (Onboarding & Config Coaching Skills)  
> 建立日期：2026-10-24  
> 所屬主計畫：[2026_10_23_1314_agents_workflow_aci_and_delegation_evolution](../umbrella_overview.md)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：修正 `compiler.py:_resolve_source_path()` 跨模組 sibling fallback 與 `scripts/cli.py:tokens()` 雙欄位 (`value`/`name`) 相容顯示（對應 `FR-05`）。
- [x] **TASK-02**：於 `AgentsStandards.md` 增設 `PROJECT_ROLE_AND_BOUNDARIES` 錨點、更新 `context-init/SKILL.md` 熱啟動提取與引導提示，並建立 `how-to-config-yscb/SKILL.md`、`how-to-yscb/SKILL.md` 與註冊 `agents-workflow/contributes/agents-workflow.json`（對應 `FR-01`、`FR-02`、`FR-03`）。
- [x] **TASK-03**：於 `core`、`dev`、`server`、`knowledge-db` 四大模組建立 `assets/config_guide.md` 與 `assets/usage_guide.md`（各 15~25 行，含單反引號包覆之隨包手冊連結）並更新各模組 `contributes/agents-workflow.json` 與 `_manifest.md`（對應 `FR-04`、`NFR-01`）。
- [x] **TASK-04**：於 `test_plans_model_record.py` 與 `test_compiler.py` 增補單元與邊界測試（驗證雙星技能契約、三要素指南結構、`PROJECT_ROLE_AND_BOUNDARIES` 注入與跨模組 sibling fallback；本倉 `project_role.md` 與 `testing_guide.md` 交由 `/how-to-config-yscb` 實機探勘代寫）（對應 `FR-01` ~ `FR-05`、`EC-01` ~ `EC-04`）。
- [x] **TASK-DOC**：同步更新 `ys_codebase/source/agents-workflow/README.md`、`docs/agents-workflow/README.md`、`docs/agents-workflow/user_guide.md` 與 `docs/agents-workflow/DESIGN_NOTES.md`（`[DN-AW-13]`）。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

