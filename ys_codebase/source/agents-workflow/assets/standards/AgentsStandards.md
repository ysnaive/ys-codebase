# Agent 專案行為準則與防呆紀律規範 (Agents Standards)

本文件定義 Agent 在專案內執行任務時**必須強制遵守**的通用硬性核心原則、防呆紀律與工程規範。

---

## 1. 核心原則與防呆紀律 (Core Principles & Guardrails)

### 📌 核心三大原則 (Core Axioms)
1. **零臆測 (Zero Speculation)**：任何不確定的技術細節，必須與開發者釐清後才能推進。嚴禁自行假設需求、猜測 API 行為或臆測解法。
2. **剛性追溯 (Traceability)**：從需求到程式碼的每一步決策，必須 100% 具備文件記錄可回溯（`P00 語意` ➔ `FR/EC` ➔ `[{Phase}:DR-XX]` ➔ `API 簽名` ➔ `程式碼` ➔ `測試`）。
3. **分級管控 (Graduated Control)**：依三大分流層級選擇 Level 0 (Fast Track)、Level 1 (Full Track) 或 Level 2 (Umbrella 主計畫模式)。

### 🚨 執行與推進紀律（絕對禁止條款）
- **嚴禁連發**：一次回應 (Turn) **最多只能執行一個 Phase 或一個獨立動作**。產出階段文件後，必須以明確文字詢問開發者並**立即 End Turn** 等待回覆。
- **Checkpoint 強制等待**：產出 Phase 文件後，必須等待開發者明確給予推進指示，絕對禁止 Agent 自行假設通過並推進下一個 Phase。
- **「問答 $\neq$ 推進」防呆條款 (Clarification $\neq$ Advancement Disambiguation)**：
  - **回覆意圖二分法**：Agent 必須嚴格區分開發者的回覆類型：
    - **類型 A：局部解答 / 意見回饋**（例：解答提問、提供特定參數、修改某欄位）➔ Agent **僅可更新當前 Phase 文件**，呈遞更新摘要與變更處，並明確詢問「已為您更新 [項目]，請問本階段內容是否確認無誤，可指示推進至下一階段？」並**立即 End Turn 等待**，**絕對禁止直接跨入下一 Phase**！
    - **類型 B：推進 / 定稿指令**（例：「確認」、「通過」、「進入 Phase X」、「沒有其他問題了」）➔ 只有接收到此類明確信號，Agent 才能標記當前 Phase 為 `Confirmed` / `Passed` 並推進。
  - **嚴禁複合推論**：絕對禁止 Agent 自行假設「因為開發者解答了疑問 ➔ 代表整份文件無其他問題 ➔ 自動推進」。
  - **更新後二次確認 (Update & Re-confirm Loop)**：文件修訂後必須重新呈遞修改摘要，並重新等待開發者明確給出類型 B 指令。
- **嚴禁空降實作**：未經規劃定稿並獲得開發者確認前，**絕對禁止直接編寫或修改原始碼**。
- **確定性文檔讀取失效阻斷鐵律 (Deterministic Document Read & Anti-Fuzzy Fallback Guardrail)**：
  - **確定性內容定義**：指 SOP 工作流、規範手冊、註冊協議或指引中**顯式指定之實體文檔或標準檔案路徑**（例：`AGENTS.md`、`AgentsCliGuild.md`、`CHANGELOG.md`、`STANDARDS.md`、指定 Phase 模板等）。
  - **🚨 絕對禁止同義詞搜尋與模糊探勘**：當讀取指定文檔發生失敗或無法定位時（如 404 FileNotFound / 路徑解析錯誤），**絕對禁止** Agent 自主發起 `knowledge-db search`、同義詞搜尋、全專案模糊搜尋或遍歷目錄來「擅自隱藏缺陷並猜測替代檔案」！
  - **即時呈報與阻斷**：必須立即停止動作，向開發者明確呈遞：「指定文檔路徑 `[檔案路徑]` 讀取失敗，無法定位」，直接暴露底層路徑缺陷與真實報錯，等待開發者指示或修正。

### 🛡️ 除錯排查與範疇保護鐵律 (Scope-Bound Debugging & Anti-Drift Guardrails)
- **「由近及遠、本體優先」排查階層 (Local-First Hierarchy)**：遇到錯誤或異常時，Agent **必須優先徹底排查當前組件本體內部邏輯與呼叫端傳參配置**。在未 100% 排除自身問題前，**絕對禁止直接跨模組深入下游/外部模組進行修改**。
- **修改範疇越界阻斷 (Out-of-Scope Modification Gate)**：若排查發現問題似乎位於超出本次 Dev Plan 承諾範圍的外部模組，**Agent 絕對禁止擅自修改外部代碼**！必須立即發起 `/Discuss` 向開發者呈遞調用證據，由開發者判定。
- **阻斷盲目淺層修補 (Anti-Trial-and-Error Loop)**：同一問題**連續 2 次修復失敗**，或修復將破壞既有架構/API 簽名時，必須強制停手發起 `/Discuss` 進行 5-Whys 根因分析。

### ⚙️ 工具調度與 CLI 守門鐵律 (Tool Execution & Safety Guardrails)
- **CLI 指令 Default-Deny 守門**：
  - **查表比對**：Agent 在欲調用 `python __${yscb.host://yscb.py}__` 宿主或子模組指令前，必須先比對 `AgentsCliGuild.md`。僅在當前情境 100% 符合 `✅ 推薦/適用情境` 時方可執行。
  - **Default-Deny 閉環**：若欲執行之指令或參數組合未列於表、無對應推薦欄位、或命中 `🚨 絕對禁止/不適用情境`（例：跑測前手動 build、未授權 bump 版本、日常跑 test --all、調用內部 op-test 等），**絕對禁止擅自執行**！必須向開發者確認意圖與預期指令，獲明確授權後方可執行。
- **目錄歸檔紀律與 CLI 調度優先**：所有計畫預設留存原位（`__${workflow.plans://}__`），**嚴禁 Agent 主動歸檔**，僅在開發者明確下達歸檔指令時才執行歸檔工具。

---

`__@{AGENTS_STANDARDS}__`
