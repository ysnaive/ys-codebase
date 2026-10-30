# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_10_30_1641_code_optimize  
> 建立日期：2026-10-30  
> 計畫狀態：In Progress  
> Umbrella 模式：Incremental (增量演進型)  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：運用 `/code-optimizer` 技能對 YS-Codebase 核心生態系模組（`core`、`dev`、`server`、`knowledge-db`、`agents-workflow`）分階段執行五維度靜態診斷（`D1~D5`）、業務階段邏輯聚合（`S1`）、無狀態邏輯剝離（`S2`）與行為無損重構（`S3~S6`），消除歷史轉發層、相容別名、循環耦合與巨型檔案/長函式，全面提升代碼內聚度與可維護性。
- **架構邊界**：
  - 採增量演進型（`Incremental`）推進，每個子計畫先以 `Research Plan (R01)` 完成五維度靜態診斷與重構處方盤點，待開發者拍板出口後原地升級為實作計畫或分階段落地。
  - 首發子計畫 `sub_01_core_code_optimization` 聚焦於 `ys_codebase/source/core/`（`Module Scope` × `Mode A：新功能收斂期 / 可破壞性變更`），並同步盤點跨模組 `uri.<io> -> vfs.<io>` 調用遷移邊界。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_core_code_optimization` | Research Plan (`R01`) | `In Progress` | 針對 `ys_codebase/source/core/`（21 檔 / 7,611 LOC）執行 `Mode A` 五維度靜態診斷（`D1~D5`）、公開入口與死代碼收斂盤點，以及 9 大核心模組之 `S1` 業務階段拆解與 `S2` 無狀態邏輯剝離處方（`R01`） |
| **sub_02** | `sub_02_dev_code_optimization` | Research Plan (`R01`) | `In Progress` | 針對 `ys_codebase/source/dev/`（13 檔 / 4,813 LOC）執行 `Mode A` 雙子代理獨立盲測並合併收斂為單一正統 `R01_code_optimization_audit.md`（12 項 `Mode A` 清除清冊、`D1~D5` 問題單與 `S1~S6` 拆解處方） |
| **sub_03** | `sub_03_server_code_optimization` | Research Plan (`R01`) | `In Progress` | 針對 `ys_codebase/source/server/`（9 檔 / 2,263 LOC）執行 `Mode A` 雙子代理獨立盲測並合併收斂為單一正統 `R01_code_optimization_audit.md`（11 項 `Mode A` 清除清冊、`logger.py` 隱藏 `NameError` 修復與 `S1~S6` 拆解處方） |
| **sub_04** | `sub_04_knowledge_db_code_optimization` | Research Plan (`R01`) | `In Progress` | 針對 `ys_codebase/source/knowledge-db/`（30 檔 / 11,535 LOC）執行 `Mode A` 雙子代理獨立盲測並合併收斂為單一正統 `R01_code_optimization_audit.md`（23 項 `Mode A` 清除清冊、`TopologyQueryService` 剝離、BM25 打分核心合一與 `S1~S6` 處方） |
| **sub_05** | `sub_05_agents_workflow_code_optimization` | Research Plan (`R01`) | `In Progress` | 針對 `ys_codebase/source/agents-workflow/`（16 檔 / 8,847 LOC）執行 `Mode A` 雙子代理獨立盲測並合併收斂為單一正統 `R01_code_optimization_audit.md`（19 項 `Mode A` 清除清冊、`session_trace`/`verifier` 模組拆解與循環依賴破除處方） |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [ ] **里程碑 1 (`sub_01`)**：完成 `core` 模組 `R01` 五維度靜態診斷報告與後續重構實作閉環
- [ ] **里程碑 2 (`sub_02`)**：完成 `dev` 模組 `R01` 五維度靜態診斷報告與後續重構實作閉環
- [ ] **里程碑 3 (`sub_03`)**：完成 `server` 模組 `R01` 五維度靜態診斷報告與後續重構實作閉環
- [ ] **里程碑 4 (`sub_04`)**：完成 `knowledge-db` 模組 `R01` 五維度靜態診斷報告與後續重構實作閉環
- [ ] **里程碑 5 (`sub_05`)**：完成 `agents-workflow` 模組 `R01` 五維度靜態診斷報告與後續重構實作閉環

