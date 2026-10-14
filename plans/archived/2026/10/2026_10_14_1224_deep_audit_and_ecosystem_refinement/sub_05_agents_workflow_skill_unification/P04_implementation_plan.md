# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_05_agents_workflow_skill_unification  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 覆蓋 Schema 純化、資產遷移、Contributes 更新、發布清理與測試對齊
- [x] **零遺留承諾**：專案中不再殘留任何 `.agents/workflows/` 舊檔案
- [x] **向後相容**：歷史 `type: "workflow"` 宣告由編譯器無損自動轉譯為 `type: "skill"`

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 登記 `[DN-AW-14]` 純 Skill 架構統一設計決策 |
| **微觀日誌** | `plans/.../changelog.md` | Modify | 記錄子計畫完成與結案紀錄 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若下游專案仍存在歷史 `.agents/workflows/` 舊檔案，是否會導致 Agent 混淆？  
> [*] **防護解法**：`publisher.py` 在發布交易中自動檢測並主動安全清理 `.agents/workflows/` 目錄，確保工作區零歷史殭屍檔案。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [x] **TASK-01 (Schema DSL 純化與編譯器轉譯)**：修改 `_format.json` 純化 `ExportAssetDef.type`；於 `compiler.py` 實作 `workflow` 到 `skill` 之相容轉譯。
- [x] **TASK-02 (內建 8 大工作流實體遷移為 Skills)**：將 `assets/workflows/` 下之 8 個檔案重構建立為 `assets/skills/<name>/SKILL.md`，並移除 `assets/workflows/`。
- [x] **TASK-03 (Contributes 與 Release Targets 投影更新)**：修改 `agents-workflow.json`，將 8 大工作流改為 `type: "skill"` 導出，並移除各 target 之 `workflow` 投影。
- [x] **TASK-04 (專案級 BumpRevision 遷移)**：將 `config/agents-workflow/workflows/BumpRevision.md` 遷移為 `skills/bump-revision/SKILL.md`，更新 `contribute.json`。
- [x] **TASK-05 (Publisher 歷史殘留自動清理)**：修改 `publisher.py`，於發布交易時自動探測並清理 `.agents/workflows/` 目錄與舊檔案。
- [x] **TASK-06 (規範文檔與超連結全面校準)**：修改 `AgentsStandards.md`、`DevelopmentStandards.md` 等，校準所有工作流超連結至 Skills 目錄。
- [x] **TASK-07 (單元測試全面適配與全生態系驗證)**：修改 `test_compiler.py`、`test_publisher.py` 等測試，執行全生態系 550 測試驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 零雙軌妥協**：
  徹底終結 `workflow` 類型，全系統統一且唯一採用 `skill`，徹底簡化 Agent 開發認知模型。


