# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 建立日期：2026-10-23  
> 計畫狀態：In Progress  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：全面推進 `agents-workflow` 下世代工程體驗與認知負荷治理——透過 Python 工具鏈 (ACI) 強化狀態機領航與免讀盲寫、建立雙層儲備體系（`/todo` 輕量待辦帳本 + `/roadmap` 立項物理遷入 `Consume-on-Promote`）、內化三支柱門檻觸發式 Subagent 任務級上下文隔離協定，並於最終階段完成跨子計畫二次驗收與整體功能打磨。
- **架構邊界**：
  - 聚焦於 `ys_codebase/source/agents-workflow/`（Python 工具鏈 `plans/`、`roadmap.py`、CLI 指令宣告 `contributes/core.json` 與擴充錨點 `contributes/agents-workflow.json`，以及內建 `assets/skills/`、`assets/templates/` 與 `tests/`）及對應系統知識庫文檔 `docs/agents-workflow/`。
  - 嚴格遵守「主體規格檔單次原生寫入」、「Single-Writer 計畫檔保護」與「100% Python 標準庫零外部依賴」原則。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_python_aci_toolchain` | Full Track | `Completed` | 落實 [python_aci_toolchain_roadmap.md](../roadmap/python_aci_toolchain_roadmap.md)：`plan status --resume` 確定性狀態領航與 `handoff.md` 原子閱後即焚、`plan verify --phase` 左移檢核與 `P01<->P06` 追溯鏈集合差集比對、伴隨檔自癒與 `--log` 免讀盲寫追加 `changelog.md`。 |
| **sub_02** | `sub_02_roadmap_and_todo_refactoring` | Full Track | `Pending` | 落實 [roadmap_and_todo_refactoring.md](../roadmap/roadmap_and_todo_refactoring.md)：拆分 `/todo` (`TODO.md` 單調遞增編號、單行免讀盲寫 `todo add`) 與 `/roadmap` 雙層體系、實作 `todo promote` / `roadmap promote` 立項物理遷入 (`Consume-on-Promote`) 及 `Seeded` 前置源頭資產白名單。 |
| **sub_03** | `sub_03_subagent_task_isolation` | Full Track | `Pending` | 落實 [subagent_task_isolation_evaluation.md](../roadmap/subagent_task_isolation_evaluation.md)：於 `research`、`discuss`、`auto`、`phase_05`、`phase_06`、`phase_07` 內化「三支柱門檻觸發式 Subagent 委派協定」（探索隔離、序列實作隔離與二振熔斷、Fresh-Eyes 冷眼審查）與檔案路徑傳址 / Single-Writer 護欄。 |
| **sub_04** | `sub_04_final_acceptance_and_polish` | Full Track | `Pending` | 針對 `sub_01` ~ `sub_03` 落地成果執行端到端二次驗收、跨功能協同整合驗證（含將本計畫所消費之 3 份 Roadmap 儲備透過新機制閉環遷移）與最終 UX/DX 功能打磨。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (`sub_01`)**：完成 `agents-workflow` Python 工具鏈 (ACI) 強化（`plan status --resume`、`plan verify --phase` 追溯差集比對與 `--log` 免讀盲寫追加）並通過單元測試。
- [ ] **里程碑 2 (`sub_02`)**：完成 `/todo` 與 `/roadmap` 雙層儲備體系重構（`todo add/list/promote`、`roadmap promote` 物理遷入與 `Seeded` 白名單）並通過單元測試。
- [ ] **里程碑 3 (`sub_03`)**：完成三支柱門檻觸發式 Subagent 委派協定與八大安全收斂護欄植入，通過合規測試。
- [ ] **里程碑 4 (`sub_04`)**：完成 `sub_01` ~ `sub_03` 二次驗收、全模組整合回歸測試、三層文檔對齊與最終打磨結案。

