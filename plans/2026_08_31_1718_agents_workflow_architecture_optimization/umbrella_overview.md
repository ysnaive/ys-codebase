# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：agents_workflow_architecture_optimization  
> 建立日期：2026-08-31  
> 計畫狀態：Completed  
> Umbrella 模式：Incremental (增量演進型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  - 針對 `agents-workflow` 模組展開一系列核心架構演進與規範治理優化。
  - 改善資產注入、編譯與發布管線，解決規範過度集中注入全域 `AGENTS.md` 導致 Token 膨脹之問題。
  - 建立「剛性守門 Rules ➔ 隨選領域 Skills ➔ 宏觀流程 Workflows」之三層完整資產治理體系，提升全生態系可擴充性與執行效能。
- **架構邊界**：
  - `source/agents-workflow/`：編譯器 (`ArtifactCompiler`)、發布引擎 (`ReleasePublisher`)、目標管理 (`ReleaseTargetManager`)、宣告規範 (`contributes.format.md`)。
  - 生態系模組規範下沉：`knowledge-db` 等模組的 `contributes` 注入宣告重構與 Skills 封裝。
  - 專案根目錄 `AGENTS.md` 守門化與瘦身。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_existing_injection_mode_optimization` | Full Track | `Completed` | 現有注入模式優化 (`release_target.agents_md` 宣告式規範投影、淘汰全域 `enable_agents_md`) |
| **sub_02** | `sub_02_skills_architecture` | Full Track | `Completed` | Skills 體系引入與投影管線架構實作 (支援 `export.type="skill"` 與 Target `projections.skill`) |
| **sub_03** | `sub_03_content_optimization_and_agents_md_slimming` | Full Track | `Cancelled` | 轉入增量修訂計畫模式 (Revision Plan)，免開實體目錄保護 Token |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1**：完成子計畫 01（現有注入模式優化），確立純淨且具擴充彈性的注入架構與規範投影。
- [x] **里程碑 2**：完成子計畫 02（Skills 基礎架構支援），具備 `export.type="skill"` 編譯、投影與發布能力，落地首個 `documentation` Skill。
- [x] **里程碑 3**：核心基礎建設與投影管線完備，Umbrella 主計畫順利收斂結案；後續內容優化無縫轉入短循環修訂計畫模式。
