# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：工作流優化 (Workflow Optimization)  
> 建立日期：2026-10-17  
> 計畫狀態：Completed  
> Umbrella 模式：Incremental (增量演進型)  
> 模型：Claude Opus 5.5  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：以 2026-10-17 `agents-workflow` 通用工作流獨立審計結果為起點，逐步消除規格跨檔矛盾、工具鏈（scanner / verifier / archiver）與規格的落差，以及生命週期缺口，讓工作流可被 Agent 無歧義地執行。
- **架構邊界**：
  - 範疇：`agents-workflow` 模組原始碼（`assets/standards`、`assets/skills`、`assets/templates`、`agents_workflow/plans/`、`contributes/`）。
  - 排除：已物化之 `.agents/*` 產物不得手動修改，一律由 release 流程同步；不追溯修改已封存計畫與既有 `CHANGELOG.md` 歷史內容。
- **審計已裁定事項**（作為各子計畫前提）：
  1. 附掛 `revision_log.md` 未結案時，**僅於 `plan archive` 攔截**，`plan verify` 不強制。
  2. `plan status` **不標示**附掛修訂之狀態。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_workflow_audit_remediation` | Full Track | `Completed` | 以 [R01 審計報告](./sub_01_workflow_audit_remediation/R01_workflow_audit_research.md) 為依據，一併修復全部發現：plans 工具鏈共用狀態解析、Research / Revision / Fast Track 生命週期對齊、`FP-01/02/03` 更名、Standards 模板指針改向 development-sop、佔位符自動推導、41 檔全資產自檢純化、元數據與死代碼清理 |
| **sub_02** | `sub_02_workflow_architecture_and_prompt_refinement` | Full Track | `Completed` | 從業務流程分析師與提示詞架構師角度，拆解 `assets/` 37 份原始文件之流程架構與提示詞設計，經獨立驗證 `GAP-01` ~ `GAP-12`（見 [R01 調研報告](./sub_02_workflow_architecture_and_prompt_refinement/R01_workflow_process_and_prompt_analysis.md)）後原地升級 Full Track 完成架構與提示詞優化 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1**：sub_01 完成——審計全部發現修復，工作流規格、模板與 plans 工具鏈一致。
- [x] **里程碑 2**：sub_02 完成——完成 `assets/` 原始文件之業務流程架構閉環與提示詞優化。

