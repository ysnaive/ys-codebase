<!-- YSCB_AGENTS_BEGIN -->
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
  - **查表比對**：Agent 在欲調用 `python yscb.py` 宿主或子模組指令前，必須先比對 `AgentsCliGuild.md`。僅在當前情境 100% 符合 `✅ 推薦/適用情境` 時方可執行。
  - **Default-Deny 閉環**：若欲執行之指令或參數組合未列於表、無對應推薦欄位、或命中 `🚨 絕對禁止/不適用情境`（例：跑測前手動 build、未授權 bump 版本、日常跑 test --all、調用內部 op-test 等），**絕對禁止擅自執行**！必須向開發者確認意圖與預期指令，獲明確授權後方可執行。
- **目錄歸檔紀律與 CLI 調度優先**：所有計畫預設留存原位（plans），**嚴禁 Agent 主動歸檔**，僅在開發者明確下達歸檔指令時才執行歸檔工具。

---


### 🏛️ 模組開發與 Dogfooding 自引用空間閉環鐵律 (Module Dev & Dogfooding Axiom)

本模組提供本地擴充模組開發與測試設施。凡安裝 `dev` 模組之專案，Agent 進行生態系模組開發時**必須強制遵守**以下三大空間隔離與四步標準閉環流水線：

#### 1. 三層空間權限矩陣
- **空間 ① 源碼開發空間 (`source/<module>/`)**：【唯一源碼來源 (SSOT)】所有代碼、腳本、工作流修改 **100% 必須在此空間進行**。
- **空間 ② 測試驗證空間 (`cache://dev/sandbox/`)**：【品質守門閘門】所有自動化測試在獨立隔離沙盒中執行（`python yscb.py dev test <module>` 或 `python yscb.py dev test --all`），未 100% 通過前嚴禁放行更新自引用產物。
- **空間 ③ 自引用運行消費空間 (`modules/<module>/` 與 `.mirror/`)**：【部署運行產物】視為編譯產物，**嚴禁手動直接修改**，一律由 CLI 同步物化。

#### 2. 標準四步開發閉環流水線 (The Canonical 4-Stage Pipeline)
1. `Step 1 (Source)`：編輯 `source/<module>/...` (唯一 SSOT)。
2. `Step 2 (Build/Check)`：`python yscb.py dev check <module>` 靜態稽核，或 `python yscb.py dev build <module>` 產出本機開發包。
3. `Step 3 (Regression)`：實機執行 `python yscb.py dev test <module>` (或全量 `python yscb.py dev test --all`) 100% Passed。
4. `Step 4 (Dogfooding Sync)`：
   - 透過 `@build` 直裝通道部署至 `modules/`：`python yscb.py install <module>@build --force` (🚨 嚴禁未獲指示使用 `dev release` 正式發布)。
   - 工作流系統自動完成資產物化與 `AGENTS.md` 軟合併無損。

#### 3. 🚨 發布、安裝與部署免測防呆鐵律 (Release & Install Guardrails)
- **嚴禁未獲授權主動發布**：未獲開發者明確指示前，**絕對禁止**主動執行 `python yscb.py dev release` 正式打包，或對當前本機宿主環境進行 `python yscb.py install` 覆蓋安裝。
- **部署後免重複測試鐵律 (No Redundant Test Post-Deployment)**：在通過沙盒測試並完成 **`@build` 本地部署 (`python yscb.py install <module>@build --force`)** 後，**不需要且嚴禁重複調用 `dev test` 跑測**！安裝部署僅為產物物化與環境同步操作，部署完成後直接結案交付。

#### 4. 📦 語意 URI 與源碼解耦鐵律 (VFS & Decoupling Governance)
- **嚴禁硬編碼相對路徑**：模組內部跨空間檔案存取**嚴禁使用硬編碼之宿主相對路徑**，必須 100% 使用語意空間協議（`storage://`、`cache://`、`config://`、`module.source://`、`module.build://`、`module.release://`）。
<!-- YSCB_AGENTS_END -->

## 4. 專案特化工程規範 (Project Specific Standards)
*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*


