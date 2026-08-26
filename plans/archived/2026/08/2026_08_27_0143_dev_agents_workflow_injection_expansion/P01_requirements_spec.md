# 需求規格說明書 (Requirements Specification)

> 功能名稱：擴充 Dev 模組對 Agents-Workflow 注入之工程規範與指令防呆 (Dev Injection Expansion & Command Abuse Guardrails)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0143_dev_agents_workflow_injection_expansion  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 調研報告：[R01_problem_summary_and_synthesis.md](./R01_problem_summary_and_synthesis.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 / 決策 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **Core `commands` Schema 升級與頂層廢除** | 廢除歷史頂層 `contributes.commands` 特例格式。統一規範於 `contributes["core"]["commands"]` 下，支援 `<cmd>: { description, case_pros?, case_cons? }` 物件結構。 | P0 | [P00:DR-04] |
| **FR-02** | **Core 提供 `AGENTS_CLI_GUILD` 動態 Token 與過濾** | `core` 模組實作動態 Token Provider，收集所有模組宣告之 `contributes.core.commands`。若 `case_pros` 與 `case_cons` 兩者皆無或為空，則**自動排除於生成清單**；有定義者則格式化為標準 Markdown 防呆對照表。向 `agents-workflow` 註冊該 Token。 | P0 | [P00:DR-04] |
| **FR-03** | **`yscb.py` 宿主起手腳本適配** | 修改 `yscb.py` 之 `_get_installed_module_commands`，僅讀取 `contributes.get("core", {}).get("commands", {})`，並支援自物件中提取 `description` 欄位以渲染標準 CLI Help。 | P0 | [P00:DR-04] |
| **FR-04** | **Agents-Workflow 新增 `AgentsCliGuild.md` 標準資產** | 在 `source/agents-workflow/assets/standards/AgentsCliGuild.md` 建立標準文檔資產，內嵌 `__@{AGENTS_CLI_GUILD}__` 錨點；於 `manifest.json` 宣告 `export`（type: `standard`）。 | P0 | [P00:DR-05] |
| **FR-05** | **`AgentsStandards.md` 注入 CLI 強制確認守門** | 在 `AgentsStandards.md` 注入剛性鐵律：Agent 調用 `yscb` CLI 前必須比對 `AgentsCliGuild.md`；若無對應欄位或屬於未明確定義情境，嚴禁擅自執行，必須向開發者確認意圖與預期指令，獲允許後方可執行。 | P0 | [P00:DR-05] |
| **FR-06** | **`ContextInit.md` 模板修復與原文件指針轉譯** | 修正 `ContextInit.md` 步驟 2，指向 `[DevelopmentStandards.md](__#{module://agents-workflow/assets/standards/DevelopmentStandards.md}__)` 與 `[AgentsCliGuild.md](__#{module://agents-workflow/assets/standards/AgentsCliGuild.md}__)`（由編譯器自動轉譯 Target 超連結）；步驟 4 修正為直接檢查 `workflow.plans://` 與 `workflow.archived://`。 | P0 | [P00:DR-06] |
| **FR-07** | **`dev` 模組 `contributes.core.commands` 內容補齊** | 更新 `source/dev/manifest.json` 之 `contributes.core.commands`，為 `create`, `check`, `build`, `test`, `release`, `bump-*` 填入完整的 `description`, `case_pros`, `case_cons`（涵蓋 R01 歸納之 6 大真實情境防呆）。 | P0 | [P00:DR-03], [P00:DR-04] |
| **FR-08** | **`agents-workflow` 模組 `contributes.core.commands` 遷移與內容補齊** | 將 `source/agents-workflow/manifest.json` 頂層宣告遷移至 `contributes.core.commands`，為 `init`, `plan`, `release`, `release-target`, `compile`, `tokens`, `list` 等指令補齊標準 `description`, `case_pros`, `case_cons`。 | P0 | [P00:DR-04] |
| **FR-09** | **`core` 模組 `contributes.core.commands` 宣告與內容補齊** | 在 `source/core/manifest.json` 宣告 `contributes.core.commands`，為 `uri`, `install`, `update`, `remove`, `list`, `status`, `reload`, `rollback`, `init` 等核心指令補齊標準 `description`, `case_pros`, `case_cons`。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **模組無宣告 `commands` 或宣告為空** | `AGENTS_CLI_GUILD` Provider 自動略過該模組；`yscb.py --help` 降級顯示預設 `run: <mod_desc>`，不引發異常。 |
| **EC-02** | **指令僅有 `description`，`case_pros` 與 `case_cons` 均為空或未提供** | 依過濾規則，該指令自動自 `AGENTS_CLI_GUILD` 生成清單中排除，不產生無防呆語意之空表格；`yscb.py --help` 依然正常顯示其 `description`。 |
| **EC-03** | **`case_pros` 或 `case_cons` 給定為單一字串而非陣列** | Provider 具備防禦性型別相容轉換，自動將字串封裝為單元素陣列 `[val]` 處理，防止型別不匹配引發迭代崩潰。 |
| **EC-04** | **模組仍殘留舊版頂層 `contributes.commands`** | `yscb.py` 與 `core` 徹底忽略頂層宣告，嚴格要求並推動所有模組遷移至 `contributes.core.commands`。 |
| **EC-05** | **`ContextInit.md` 原文件指針轉譯邊界** | 編譯器解析 `__#{module://...}__` 時若在發布目標清冊找不到對應 Projection，降級輸出原始 URI 並提出警告，不阻斷整體發布。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **純淨語意與零硬編碼** | 所有模組間資源引用嚴格遵循標準語意 URI（`project://`, `module://`, `cache://`, `storage://`, `workflow.*://`），嚴禁硬編碼宿主路徑。 |
| **NFR-02** | **Dogfooding 閉環回歸** | 執行全系統回歸測試 `python test/run_regression.py`，保持 100% Passed (維持 23/23 + E2E 通過)。 |
| **NFR-03** | **Token 經濟性與純 ASCII 渲染** | `AGENTS_CLI_GUILD` 動態生成之 Markdown 表格嚴格過濾無效指令，格式採用簡潔純 ASCII 表格，最大程度節省 Agent Prompt Token。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- > [!IMPORTANT]
  > **編譯器原文件超連結轉譯規則**：模板與工作流中的文件超連結，必須一律使用 `__#{module://<mod>/...}__` 原文件協議格式，由 `agents-workflow` 編譯器在執行 `release` 依各 Target 投射目錄自動轉譯為相對路徑。嚴禁在源碼模板中硬編碼特定 Target 的產物路徑（如 `project://.agents/...`）。

- > [!WARNING]
  > **頂層 `contributes.commands` 徹底廢除**：本次重構將全面清理所有模組（`core`, `dev`, `agents-workflow`）的 `manifest.json`，全數對齊為 `contributes.core.commands`，確保 SSOT 規範一致。

---
