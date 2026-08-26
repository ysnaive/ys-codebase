# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：擴充 Dev 模組對 Agents-Workflow 注入之工程規範與指令防呆 (Dev Injection Expansion & Command Abuse Guardrails)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0143_dev_agents_workflow_injection_expansion  
> 狀態：Confirmed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 依據 P03：[P03_api_spec.md](./P03_api_spec.md)  
> 測試計畫：[P06_test_plan.md](./P06_test_plan.md)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求完整對齊**：FR-01 ~ FR-09 在 P02 架構與 P03 API 規格書中均有具體承接模組與函數簽名。
- [x] **邊界防護覆蓋**：EC-01 ~ EC-05 在 `get_agents_cli_guild` 與 `yscb.py` 實作中有明確防禦轉譯策略。
- [x] **依賴純淨約束**：符合 NFR-01 ~ NFR-03，無硬編碼物理路徑，維持 100% 純淨語意 URI 與 Token 經濟性。
- [x] **Test-First 定稿**：P06 測試案例清單（FT-01~FT-06, ET-01~ET-02, RT-01）已嚴格對齊需求並同步定稿。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

依據知識庫 7 大抽象維度，預排本次交付必須新建或同步更新的文檔清單（Phase 7 將 1:1 核對交付）：

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1 (規格書)** | `docs/agents-workflow/contributes.format.md` | `MODIFY` | 更新 `contributes.core.commands` Schema 欄位定義 (`description`, `case_pros`, `case_cons`) 與 `AGENTS_CLI_GUILD` Token 用法。 |
| **維度 2 (使用手冊)** | `docs/agents-workflow/user_guide.md` | `MODIFY` | 登載 `AgentsCliGuild.md` 標準指南與 CLI 強制比對/確認守門機制說明。 |
| **維度 3 (架構筆記)** | `docs/dev/user_guide.md` | `MODIFY` | 登載 `dev` 6 大子指令防呆情境與標準調用流水線。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1 (第三方外部模組無宣告 `commands` 或宣告舊版頂層)**：  
> 若使用者安裝了未宣告 `case_pros`/`case_cons` 的第三方外掛模組，是否會破壞 `AgentsCliGuild.md` 或造成渲染崩潰？  
> 💡 **防護解法**：`get_agents_cli_guild` 實作嚴格防禦過濾機制：若模組無 `contributes.core.commands` 或其子指令 pros/cons 均為空，自動排除該指令；頂層舊格式徹底忽略；若全系統皆無防呆宣告，安全輸出提示區塊，絕不拋出未捕獲例外。

> ❓ **尖銳問題 2 (`ContextInit.md` 在多 Target 環境發布時的超連結有效性)**：  
> 在非 Antigravity 的其他 IDE Target（若 target 產物目錄結構不同），原文件轉譯指針是否能保證超連結不會 404？  
> 💡 **防護解法**：編譯器在執行 `release` 時，依據當前 Target 之 `projections` 動態計算相對路徑（例如 `../.yscb/standards/DevelopmentStandards.md`）。若目標 Projection 存在則轉譯，若不存在則降級輸出原始 URI 並記錄警告，保證路徑動態自適應。

> ❓ **尖銳問題 3 (Agent 嘗試繞過 `AgentsCliGuild` 自行組裝命令)**：  
> 如果 Agent 試圖發明 `dev build && dev test --all` 等未列在對照表的情境與命令，如何確保被攔截？  
> 💡 **防護解法**：在 `AgentsStandards.md` 注入剛性鐵律，明確宣告「Default-Deny 閉環」與「未列情境強制向開發者發起 Discuss 確認，獲允許後方可執行」，從最高優先級規則層級切斷 LLM 擅自拼裝命令的自由度。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (Core 模組規格升級與 Provider 實作)**：
  - 在 `source/core/core/providers.py` 實作 `get_agents_cli_guild` 函式（過濾 pros/cons 皆空指令、支援型別防禦轉換、格式化為 Markdown 表格）。
  - 更新 `source/core/manifest.json` 宣告 `contributes.core.commands` 並宣告提供 `AGENTS_CLI_GUILD` computed token。
  - 建立 `source/core/tests/test_cli_guild.py` 單元測試並實機驗證。
- [ ] **TASK-02 (yscb.py 宿主起手腳本適配)**：
  - 修改 `yscb.py` 之 `_get_installed_module_commands`，僅自 `contributes.get("core", {}).get("commands", {})` 讀取並提取 `description`。
  - 實機檢驗 `python yscb.py --help`。
- [ ] **TASK-03 (Dev 模組 6 大子指令防呆宣告)**：
  - 更新 `source/dev/manifest.json` 之 `contributes.core.commands`，填寫 6 大指令完整 `description`, `case_pros`, `case_cons`。
  - 精簡 `source/dev/assets/standards/DevEngineeringStandards.md`。
- [ ] **TASK-04 (Agents-Workflow 資產、守門與工作流修復)**：
  - 新增 `source/agents-workflow/assets/standards/AgentsCliGuild.md` 資產，內嵌 `__@{AGENTS_CLI_GUILD}__` 錨點。
  - 更新 `source/agents-workflow/manifest.json` 遷移 commands 並宣告 export `AgentsCliGuild.md`。
  - 在 `source/agents-workflow/assets/standards/AgentsStandards.md` 注入 CLI 比對與強制確認守門。
  - 修正 `source/agents-workflow/assets/workflows/ContextInit.md` 步驟 2 原文件指針轉譯與步驟 4 清理過時設定。
- [ ] **TASK-05 (知識庫 1:1 文檔交付與全系統回歸)**：
  - 更新 `docs/agents-workflow/contributes.format.md`、`docs/agents-workflow/user_guide.md` 與 `docs/dev/user_guide.md`。
  - 執行 `python test/run_regression.py` 達成 100% Passed。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** Core 宣告式 `contributes.core.commands` Schema 與 `AGENTS_CLI_GUILD` Provider 動態過濾定稿。
- **[P04:DR-02]** `yscb.py` 廢除頂層 `contributes.commands`，僅讀取 core 宣告之指令與 description 定稿。
- **[P04:DR-03]** `agents-workflow` 新增 `AgentsCliGuild.md` 標準資產與 `AgentsStandards.md` 強制確認守門定稿。
- **[P04:DR-04]** `ContextInit.md` 修正原文件超連結轉譯指針 (`__#{module://...}__`) 與清理過時設定定稿。
- **[P04:DR-05]** `dev`, `agents-workflow`, `core` 三大模組 `commands` 完整宣告補齊定稿。
- **[P04:DR-06]** P06 測試計畫（9 項測試案例）審查通過，剛性定稿為 `Confirmed`。

---
