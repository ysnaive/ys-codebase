# 成果展示與結案報告 (Walkthrough)

> 功能名稱：擴充 Dev 模組對 Agents-Workflow 注入之工程規範與指令防呆 (Dev Injection Expansion & Command Abuse Guardrails)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0143_dev_agents_workflow_injection_expansion  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

本計畫徹底解決了 Agent 在開發過程中對 CLI 指令的過度濫用與誤用痛點，並優化了專案規範與工作流熱啟動體驗：

1. **職責解耦與 Contributes 規範統一**：
   - 徹底廢除頂層特例 `contributes.commands`，統一收斂至由 `core` 模組治理的 `contributes.core.commands` 標準結構。
   - 支援富語意 Schema：`{"description": "...", "case_pros": ["..."], "case_cons": ["..."]}`。
   - `yscb.py` 宿主起手腳本全面適配僅自 `contributes.core.commands` 讀取並渲染標準 CLI Help。
2. **動態 CLI 指南與防呆守門機制 (`AGENTS_CLI_GUILD`)**：
   - 由 `core.providers.get_agents_cli_guild` 自動遍歷掃描全系統模組之指令宣告，過濾無防呆情境項目，格式化為乾淨的 Markdown 語意對照表。
   - `agents-workflow` 新增標準資產 `AgentsCliGuild.md` 並透過 `__@{AGENTS_CLI_GUILD}__` 自動物化。
   - 在 `AgentsStandards.md` 注入剛性「查表比對」與「Default-Deny 未列情境向開發者確認」之強制守門鐵律。
3. **現有三大模組指令清冊補齊**：
   - `core`（8 大指令）、`dev`（10 大子指令）、`agents-workflow`（7 大子指令）全面補齊 `contributes.core.commands` 與詳細防呆情境。
4. **工作流導航指針修復與編譯器轉譯增強**：
   - 修復 `ContextInit.md` 步驟 2 導引讀取 `DevelopmentStandards.md` 與 `AgentsCliGuild.md`。
   - 強化 `compiler.py` 之 `URI_REF_REGEX`，支援在 Markdown 超連結括號內直接使用 `__#{module://...}__` 並精確轉譯為各發布目標的相對路徑。
5. **測試隔離性修復**：
   - 修復 `test_robustness.py` 中缺少 `_get_yscb_root` mock 的沙盒外溢漏洞，達成 100% 虛擬目錄拘束隔離。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| [`source/core/core/providers.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/providers.py) | **NEW** | 實作 `get_agents_cli_guild` 動態 Token Provider |
| [`source/core/tests/test_cli_guild.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_cli_guild.py) | **NEW** | `get_agents_cli_guild` 單元測試（過濾、字串防禦轉換、空備援） |
| [`source/core/tests/test_robustness.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_robustness.py) | **MODIFY** | 補齊 `_get_yscb_root` mock，根絕測試時對實體 `config.project.json` 的外溢寫入 |
| [`source/core/manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/manifest.json) | **MODIFY** | 宣告 8 大指令 `contributes.core.commands` 與 `AGENTS_CLI_GUILD` computed token |
| [`yscb.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/yscb.py) | **MODIFY** | 修正 `_get_installed_module_commands` 僅自 `contributes.core.commands` 讀取並提取 description |
| [`source/dev/manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/manifest.json) | **MODIFY** | 遷移至 `contributes.core.commands` 並補齊 10 大指令與防呆推薦/禁止情境 |
| [`source/agents-workflow/assets/standards/AgentsCliGuild.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/assets/standards/AgentsCliGuild.md) | **NEW** | 建立 CLI 指令防呆對照指南資產 |
| [`source/agents-workflow/assets/standards/AgentsStandards.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md) | **MODIFY** | 注入 CLI 查表比對與 Default-Deny 守門鐵律 |
| [`source/agents-workflow/assets/workflows/ContextInit.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/assets/workflows/ContextInit.md) | **MODIFY** | 步驟 2 導航補齊指針轉譯，步驟 4 修正為純淨 URI 檢驗 |
| [`source/agents-workflow/manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/manifest.json) | **MODIFY** | 遷移 commands、export 新增 `AgentsCliGuild.md`、宣告 `AGENTS_CLI_GUILD` token |
| [`source/agents-workflow/agents_workflow/compiler.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/agents_workflow/compiler.py) | **MODIFY** | 支援 Markdown 超連結內無反引號之 `__#{uri}__` 標籤正規化轉譯 |
| [`source/agents-workflow/contributes.format.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/contributes.format.md) | **MODIFY** | 登載 Section 2.5 `contributes.core.commands` 規範 |
| [`docs/agents-workflow/user_guide.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/agents-workflow/user_guide.md) | **MODIFY** | 登載 `AgentsCliGuild.md` 與 CLI 守門機制 |
| [`docs/dev/user_guide.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/user_guide.md) | **MODIFY** | 登載 `dev` 模組 6 大指令防呆規範對照表 |
| [`.agents/.yscb/standards/AgentsCliGuild.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/.agents/.yscb/standards/AgentsCliGuild.md) | **NEW** | 編譯物化產物（含三大模組防呆矩陣） |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `core` 模組單元測試：69/69 Passed (100%)
  - `agents-workflow` 模組測試：23/23 Passed (100%)
  - `dev` 模組測試：30/30 Passed (100%)
  - **全模組沙盒回歸測試 (`python yscb.py dev test --all`)**：**122/122 Passed (100% Ready)**
- **實機 UX / 人工驗證**：
  - `python yscb.py --help` 輸出排版清晰，三大模組子指令完美渲染。
  - `/ContextInit` 超連結 100% 有效導航至相對路徑 `DevelopmentStandards.md` 與 `AgentsCliGuild.md`。
  - `AgentsCliGuild.md` 內容完整呈現推薦與禁止情境，閱讀體感良好。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :---: | :--- | :---: | :--- |
| **模組規範** | [`source/agents-workflow/contributes.format.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/contributes.format.md) | ✅ 已交付 | 登載 Section 2.5 `contributes.core.commands` 規格與 `AGENTS_CLI_GUILD` |
| **工作流手冊** | [`docs/agents-workflow/user_guide.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/agents-workflow/user_guide.md) | ✅ 已交付 | 登載 `AgentsCliGuild.md` 查表與守門機制 |
| **開發手冊** | [`docs/dev/user_guide.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/user_guide.md) | ✅ 已交付 | 登載 `dev` 模組 6 大指令防呆推薦與禁止情境對照表 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(dev,core,agents-workflow): expand dev-agents-workflow injection and implement cli abuse guardrails

- unify contributes schema to contributes.core.commands with case_pros/case_cons
- implement AGENTS_CLI_GUILD computed provider in core and AgentsCliGuild.md in agents-workflow
- enforce lookup matching and default-deny gate in AgentsStandards.md
- enhance compiler URI_REF_REGEX to resolve markdown hyperlinks without backticks
- fix test_robustness sandbox leak by patching _get_yscb_root
- update ContextInit.md navigation and populate commands for core, dev, and agents-workflow
```
