# 實作任務清單 (Task Breakdown)

> 功能名稱：專案特化技能建置與 Layer 2 宣告式擴充引導工作流 (sub_05_skill_creator_extension_workflow)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Medium)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：於 `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` 與 `_manifest.md` 註冊 `skill-creator` 技能匯出（內建技能共 17 個）與 `SKILL_CREATOR_STANDARDS` Token（本模組共 21 個、全系統共 22 個）。
- [x] **TASK-02**：於 `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` 支援 `LITERAL_FENCED_BLOCK_REGEX` (`<!-- yscb:literal -->`) 字面量教學區塊保護，並建立單層擴充參考手冊 `ys_codebase/source/agents-workflow/assets/skills/skill-creator/references/extension-guide.md`，頂部配置 `## 目錄 (Contents)`，收錄全系統 22 個 Stage 1 Token 錨點地圖、Stage 2 語意 URI 轉換與單反引號封裝規則，以及軌跡 ①/②/③ `contribute.json` 最小增量範本。
- [x] **TASK-03**：建立 `ys_codebase/source/agents-workflow/assets/skills/skill-creator/SKILL.md`（114 行，$\le 180$ 行），實作主動指令型 Frontmatter、四步進度檢核表、三軌擴充判定矩陣、擴充藍圖確認卡、雙軌路徑分流、三步編譯驗證守門與 `SKILL_CREATOR_STANDARDS` 錨點；並同步更新 `development-sop/SKILL.md` 與 `skill-optimizer/SKILL.md` 雙向互指導流。
- [x] **TASK-04**：於 `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py` 更新 `test_ft_08`（納入 `skill-creator` 共 17 個技能）並新增 `test_ft_11_sub05_skill_creator_extension_workflow`。
- [x] **TASK-DOC**：同步更新 `ys_codebase/source/agents-workflow/README.md` 與 `docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}`（登錄 `[DN-AW-14]`）。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

