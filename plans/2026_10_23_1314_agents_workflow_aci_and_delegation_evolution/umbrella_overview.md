# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 建立日期：2026-10-23  
> 計畫狀態：In Progress  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：全面推進 `agents-workflow` 下世代工程體驗、品質守門與認知負荷治理——透過 Python 工具鏈 (ACI) 強化狀態機領航與免讀盲寫、建立雙層儲備體系（`/todo` 輕量待辦帳本 + `/roadmap` 立項物理遷入 `Consume-on-Promote`）、建立與 `documentation` 對偶之環境型測試規範技能 `testing-sop` 並內化三支柱門檻觸發式 Subagent 任務級上下文隔離協定、補齊下游接入與賦能三劍客（`/how-to-config-yscb` 專案角色邊界與設定體檢代寫、`/how-to-yscb` 互動式教學引導、`/skill-creator` 三軌宣告式擴充），並於最終階段完成跨子計畫二次驗收、測試集子系統歸戶純化與整體功能打磨。
- **架構邊界**：
  - 聚焦於 `ys_codebase/source/agents-workflow/`（Python 工具鏈 `plans/`、`roadmap.py`、CLI 指令宣告 `contributes/core.json` 與擴充錨點 `contributes/agents-workflow.json`，以及內建 `assets/skills/`、`assets/templates/`、`assets/standards/` 與 `tests/`）、核心模組跨模組片段注入（`core`、`dev`、`knowledge-db`）及對應系統知識庫文檔 `docs/agents-workflow/` 與本倉組態 `config/agents-workflow/`。
  - 嚴格遵守「主體規格檔單次原生寫入」、「Single-Writer 計畫檔保護」、「第一層 `config://agents-workflow/{skills,snippets}/` 扁平存放慣例」與「100% Python 標準庫零外部依賴」原則。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_python_aci_toolchain` | Full Track | `Completed` | 落實 [roadmap.md](./sub_01_python_aci_toolchain/roadmap.md)：`plan status --resume` 確定性狀態領航與 `handoff.md` 原子閱後即焚、`plan verify --phase` 左移檢核與 `P01<->P06` 追溯鏈集合差集比對、伴隨檔自癒與 `--log` 免讀盲寫追加 `changelog.md`。 |
| **sub_02** | `sub_02_roadmap_and_todo_refactoring` | Full Track | `Completed` | 落實 [roadmap.md](./sub_02_roadmap_and_todo_refactoring/roadmap.md)：拆分 `/todo` (`TODO.md` 單調遞增編號、單行免讀盲寫 `todo add`) 與 `/roadmap` 雙層體系、實作 `todo promote` (支援多筆批次與 `--slug` 校驗) / `roadmap promote` 立項物理遷入 (`Consume-on-Promote`)、`Seeded` 前置源頭資產白名單與 `new-plan` 復用防呆。 |
| **sub_03** | `sub_03_testing_sop_and_subagent_isolation` | Full Track | `Completed` | **核心 SOP 品質與隔離深度合流** — 落實 [roadmap.md](./sub_03_testing_sop_and_subagent_isolation/roadmap.md)：建立與 `documentation` 對偶之環境型技能 `testing-sop`（六大測試鐵律、`TESTING_SOP_STANDARDS` 錨點、存量體檢純化指南），並於 `AgentsStandards.md`、`research`、`discuss`、`auto`、`phase_04`~`phase_07`、`plan_modes.md` 一次性植入 `testing-sop` 連鎖守門與「三支柱門檻觸發式 Subagent 委派協定」（探索隔離、Phase 05 實作隔離綁定 `testing-sop` 與二振熔斷、Phase 07 Fresh-Eyes 冷眼審查納入測試反模式契約）。 |
| **sub_04** | `sub_04_onboarding_and_config_coaching` | Full Track | `Pending` | **下游接入與教學賦能雙星合流** — 落實 [how_to_config_yscb_and_project_role_roadmap.md](../roadmap/how_to_config_yscb_and_project_role_roadmap.md) 與 [how_to_yscb_interactive_coaching_roadmap.md](../roadmap/how_to_yscb_interactive_coaching_roadmap.md)：於 `AgentsStandards.md` 增設 `PROJECT_ROLE_AND_BOUNDARIES` 錨點（Turn 0 界定本體業務空間 vs. 外部工具包黑盒）；建立 `/how-to-config-yscb`（含自動探勘代寫 `config://agents-workflow/snippets/project_role.md` 與 `testing_guide.md` 嫁接至 `TESTING_SOP_STANDARDS` 及三步熱更新驗證）與 `/how-to-yscb`（互動式引導教練與新開實戰 Session 隔離），並完成四大核心模組之設定體檢卡與黃金配方片段注入。 |
| **sub_05** | `sub_05_skill_creator_extension_workflow` | Full Track | `Pending` | **Layer 2 擴充造血閉環** — 落實 [skill_creator_and_layer2_extension_roadmap.md](../roadmap/skill_creator_and_layer2_extension_roadmap.md)：在 `sub_03` / `sub_04` 所有新增錨點定型後，建立主動指令型技能 `/skill-creator` 與完整錨點／語意 URI 擴充參考手冊（`references/extension-guide.md`），落實「三軌擴充智能分流（純錨點注入 vs. 環境攔截型 vs. 功能特化型）」、「擴充藍圖確認卡」與第一層 `config://agents-workflow/{skills,snippets}/` 宣告式註冊及三步編譯驗證守門。 |
| **sub_06** | `sub_06_final_acceptance_and_suite_purification` | Full Track | `Pending` | **全主計畫二次驗收與 Dogfooding 實戰收斂**：針對 `sub_01` ~ `sub_05` 落地成果執行端到端二次驗收、跨功能協同整合驗證（含將本主計畫所消費之 6 份 Roadmap 儲備透過新機制閉環遷移）、依 `testing-sop` 規範對 `agents-workflow/tests/` 執行子系統 1:1 歸戶與純化收斂，以及最終三層文檔對齊與打磨結案。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

> **[GLOBAL PRIORITY] 跨主計畫 4 階段 10 步全局落地順序（最高優先級執行軌道）**：
> - **Stage 1（研發憲法與儲備工具鏈先行 — 本主計畫核心層）**：`1. AW/sub_02` (`/todo` 與 `roadmap promote`) $\to$ `2. AW/sub_03` (`testing-sop` 六大鐵律 + Subagent 三支柱隔離)
> - **Stage 2（微內核與開發工具鏈加固 — `2026_10_23_1122` 地基層）**：`3. ECO/sub_01` (`core` 微內核與測試純化) $\to$ `4. ECO/sub_02` (`dev` 沙盒檢查與測試純化)
> - **Stage 3（常駐服務與檢索管線加固 — `2026_10_23_1122` 運行層與結案）**：`5. ECO/sub_03` (`server` 託管與測試純化) $\to$ `6. ECO/sub_04` (`knowledge-db` 管線與測試純化) $\to$ `7. ECO/sub_05` (四模組聯合驗收與 8 份 Roadmap `promote` 閉環結案)
> - **Stage 4（下游賦能與擴充造血收官 — 本主計畫擴充層與結案）**：`8. AW/sub_04` (`PROJECT_ROLE` + `/how-to-config-yscb` + `/how-to-yscb`) $\to$ `9. AW/sub_05` (`/skill-creator` 三軌擴充) $\to$ `10. AW/sub_06` (`agents-workflow/tests/` 純化與 6 份 Roadmap `promote` 閉環結案)

- [x] **里程碑 1 (`sub_01`)**：完成 `agents-workflow` Python 工具鏈 (ACI) 強化（`plan status --resume`、`plan verify --phase` 追溯差集比對與 `--log` 免讀盲寫追加）並通過單元測試。
- [x] **里程碑 2 (`sub_02`) [Global Step 1 - Completed]**：完成 `/todo` 與 `/roadmap` 雙層儲備體系重構（`todo add/list/promote`、`roadmap promote` 物理遷入與 `Seeded` 白名單）並通過單元測試。
- [x] **里程碑 3 (`sub_03`) [Global Step 2 - Completed]**：完成環境型技能 `testing-sop` 與三支柱門檻觸發式 Subagent 委派協定深度合流植入，通過合規測試。
- [ ] **里程碑 4 (`sub_04`) [Global Step 8]**：完成 `PROJECT_ROLE_AND_BOUNDARIES` 空間邊界錨點、`/how-to-config-yscb`（含 `testing_guide.md` 嫁接）與 `/how-to-yscb` 雙星技能建置及跨模組片段注入。
- [ ] **里程碑 5 (`sub_05`) [Global Step 9]**：完成 `/skill-creator` 三軌擴充引導工作流與全系統錨點／URI 擴充手冊建置。
- [ ] **里程碑 6 (`sub_06`) [Global Step 10]**：完成 `sub_01` ~ `sub_05` 二次驗收、6 份 Roadmap 儲備閉環遷移、`agents-workflow/tests/` 測試集子系統歸戶純化、三層文檔對齊與最終打磨結案。

