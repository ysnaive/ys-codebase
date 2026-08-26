# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：擴充 Dev 模組對 Agents-Workflow 注入之工程規範與指令防呆 (Dev Injection Expansion & Command Abuse Guardrails)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0143_dev_agents_workflow_injection_expansion  
> 狀態：Passed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | **單元測試** | 驗證 `core.providers.get_agents_cli_guild`：有定義 pros/cons 之指令正確格式化為 Markdown 表格，pros/cons 皆空之指令自動排除。 | FR-01, FR-02 | `python yscb.py dev test core` |
| **FT-02** | **主機 CLI 測試** | 驗證 `yscb.py` 之 `_get_installed_module_commands` 僅讀取 `contributes.core.commands` 並正確提取 `description` 輸出 CLI Help。 | FR-03 | `python yscb.py --help` |
| **FT-03** | **編譯與導出測試** | 驗證 `agents-workflow` 編譯發布時，`AgentsCliGuild.md` 正確解析 `__@{AGENTS_CLI_GUILD}__` 並物化至發布目標。 | FR-04 | `python yscb.py dev test agents-workflow` |
| **FT-04** | **標準文檔測試** | 驗證 `AgentsStandards.md` 包含 CLI 比對與未列情境強制向開發者確認之剛性守門文字。 | FR-05 | 靜態斷言檢驗 |
| **FT-05** | **超連結轉譯測試** | 驗證 `ContextInit.md` 中之 `__#{module://...}__` 原文件指針在編譯後正確轉譯為各 Target 相對超連結。 | FR-06 | `python yscb.py dev test agents-workflow` |
| **FT-06** | **Manifest 合規測試** | 驗證 `core`, `agents-workflow`, `dev` 三大模組之 `manifest.json` 均具備標準 `contributes.core.commands` 且無舊版頂層殘留。 | FR-07~09 | `python yscb.py dev check core dev agents-workflow` |
| **ET-01** | **邊界防禦測試** | 驗證 `case_pros` / `case_cons` 為字串而非陣列時自動相容轉換；空值模組安全跳過。 | EC-01~03 | `python yscb.py dev test core` |
| **ET-02** | **廢除頂層阻斷測試** | 驗證殘留頂層 `contributes.commands` 不會被 `yscb.py` 或 `core` 解析。 | EC-04 | `python yscb.py dev test core` |
| **RT-01** | **全系統回歸測試** | 全系統沙盒回歸測試 100% 通過（維持 23/23 + E2E 綠燈）。 | NFR-02 | `python test/run_regression.py` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `python yscb.py dev test core` 通過 69/69 測試 (含 `test_cli_guild.py`)。 | 2026-08-27 02:40 |
| **FT-02** | `Passed` | `python yscb.py --help` 成功讀取 `contributes.core.commands` 並渲染 CLI Help。 | 2026-08-27 02:35 |
| **FT-03** | `Passed` | `python yscb.py dev test agents-workflow` 通過 23/23 測試，`AgentsCliGuild.md` 成功物化。 | 2026-08-27 02:40 |
| **FT-04** | `Passed` | 靜態檢驗 `AgentsStandards.md` 包含 CLI 查表比對與 Default-Deny 守門鐵律。 | 2026-08-27 02:36 |
| **FT-05** | `Passed` | `ContextInit.md` 使用 `__#{module://...}__` 指針轉譯為 Target 相對超連結。 | 2026-08-27 02:36 |
| **FT-06** | `Passed` | `python yscb.py dev check --all` 掃描三大模組全數 PASSED。 | 2026-08-27 02:39 |
| **ET-01** | `Passed` | `test_cli_guild.py` 驗證單一字串型別防禦轉換與空值模組略過。 | 2026-08-27 02:35 |
| **ET-02** | `Passed` | `test_cli_guild.py` 驗證無 pros/cons 指令安全過濾排除。 | 2026-08-27 02:35 |
| **RT-01** | `Passed` | `python yscb.py dev test --all` 沙盒跑測 122/122 Passed (100% Ready)。 | 2026-08-27 02:39 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01 (CLI Help 人工檢驗)**：實機執行 `python yscb.py --help`，確認三大模組指令說明排版清晰無瑕疵。
- [x] **UX-02 (工作流熱啟動驗證)**：執行 `/ContextInit`，確認超連結點擊 100% 有效導航至 `DevelopmentStandards.md` 與 `AgentsCliGuild.md`。
- [x] **UX-03 (CLI 防呆指南閱讀體感)**：檢視物化後之 `AgentsCliGuild.md`，確認 6 大情境防呆與三大模組命令一目了然。

---

