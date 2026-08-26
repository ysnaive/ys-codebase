# 實作任務清單 (Task Breakdown)

> 功能名稱：擴充 Dev 模組對 Agents-Workflow 注入之工程規範與指令防呆 (Dev Injection Expansion & Command Abuse Guardrails)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0143_dev_agents_workflow_injection_expansion  
> 狀態：Completed  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (Core 模組規格升級與 Provider 實作)**：
  - 在 `source/core/core/providers.py` 實作 `get_agents_cli_guild` 函式（過濾 pros/cons 皆空指令、支援型別防禦轉換、格式化為 Markdown 表格）。
  - 更新 `source/core/manifest.json` 宣告 `contributes.core.commands` 並宣告提供 `AGENTS_CLI_GUILD` computed token。
  - 建立 `source/core/tests/test_cli_guild.py` 單元測試並實機驗證。
- [x] **TASK-02 (yscb.py 宿主起手腳本適配)**：
  - 修改 `yscb.py` 之 `_get_installed_module_commands`，僅自 `contributes.get("core", {}).get("commands", {})` 讀取並提取 `description`。
  - 實機檢驗 `python yscb.py --help`。
- [x] **TASK-03 (Dev 模組 6 大子指令防呆宣告)**：
  - 更新 `source/dev/manifest.json` 之 `contributes.core.commands`，填寫 6 大指令完整 `description`, `case_pros`, `case_cons`。
  - 精簡 `source/dev/assets/standards/DevEngineeringStandards.md`。
- [x] **TASK-04 (Agents-Workflow 資產、守門與工作流修復)**：
  - 新增 `source/agents-workflow/assets/standards/AgentsCliGuild.md` 資產，內嵌 `__@{AGENTS_CLI_GUILD}__` 錨點。
  - 更新 `source/agents-workflow/manifest.json` 遷移 commands 並宣告 export `AgentsCliGuild.md`。
  - 在 `source/agents-workflow/assets/standards/AgentsStandards.md` 注入 CLI 比對與強制確認守門。
  - 修正 `source/agents-workflow/assets/workflows/ContextInit.md` 步驟 2 原文件指針轉譯與步驟 4 清理過時設定。
- [x] **TASK-05 (知識庫 1:1 文檔交付與全系統回歸)**：
  - 更新 `docs/agents-workflow/contributes.format.md`、`docs/agents-workflow/user_guide.md` 與 `docs/dev/user_guide.md`。
  - 執行全模組回歸測試 `python yscb.py dev test --all` 達成 122/122 Passed (100%)。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

---
