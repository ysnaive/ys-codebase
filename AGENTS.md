# Agent 專案行為準則與工作流指南 (AGENTS.template.md)

<!-- YSCB_AGENTS_BEGIN -->
# Agent 專案行為準則與防呆紀律規範 (Agents Standards)

本文件定義 Agent 在專案內執行任務時**必須強制遵守**的通用硬性核心原則、防呆紀律與工程規範。

---

## 1. 核心原則與防呆紀律 (Core Principles & Guardrails)

Agent 必須始終遵守以下三大原則：
1. **零臆測 (Zero Speculation)**：任何不確定的技術細節，都必須與開發者釐清後才能推進。禁止自行假設需求、猜測 API 行為或臆測解法。
2. **可追溯 (Traceability)**：從需求到程式碼的每一步決策，都必須有文件記錄可回溯（`P00 語意` ➔ `FR/EC` ➔ `[{Phase}:DR-XX]` ➔ `API 簽名` ➔ `程式碼` ➔ `測試`）。
3. **分級管控 (Graduated Control)**：完整 Phase 0 語意化討論後，依三大分流層級矩陣選擇 Level 0 (Fast Track)、Level 1 (Full Track) 或 Level 2 (Umbrella 分類型主計畫模式)。

### 🚨 執行紀律（絕對禁止條款）
- **嚴禁連發**：一次回應 (Turn) **最多只能執行一個 Phase**。產出階段文件後，必須以明確文字詢問開發者並**立即 End Turn** 等待回覆。
- **Checkpoint 強制等待**：產出 Phase 文件後，必須等待開發者明確給予對該階段的「確認/同意/推進」指示，絕對禁止 Agent 自行假設通過並推進下一個 Phase。
- **「問答 $\neq$ 推進」防呆條款 (Clarification $\neq$ Advancement Disambiguation)**：
  - **回覆意圖二分法**：Agent 必須嚴格區分開發者的回覆類型：
    - **類型 A：局部解答 / 意見回饋**（例：解答 Agent 提問、提供特定參數、修改某欄位）➔ Agent **僅可更新當前 Phase 文件**，呈遞更新摘要與變更處，並明確詢問「已為您更新 [項目]，請問本階段內容是否確認無誤，可指示推進至下一階段？」並**立即 End Turn 等待**，**絕對禁止直接跨入下一 Phase**！
    - **類型 B：推進 / 定稿指令**（例：「確認」、「通過」、「進入 Phase X」、「沒有其他問題了」）➔ 只有接收到此類明確信號，Agent 才能將當前 Phase 標記為 `Confirmed` / `Passed` 並推進。
  - **嚴禁複合推論**：絕對禁止 Agent 自行假設「因為開發者解答了疑問 ➔ 代表整份文件無其他問題 ➔ 自動推進」。
  - **更新後二次確認 (Update & Re-confirm Loop)**：文件修訂後必須重新呈遞修改摘要，並重新等待開發者明確給出類型 B 指令。
- **嚴禁空降實作**：未經 Phase 1~4（或 FT-1）規劃並獲得開發者確認前，**絕對禁止直接編寫或修改原始碼**。
- **除錯排查與範疇保護鐵律 (Scope-Bound Debugging & Anti-Drift Guardrail)**：
  - **「由近及遠、本體優先」排查階層 (Local-First Hierarchy)**：遇到錯誤、異常或視覺/邏輯不符預期時，Agent **必須優先徹底排查當前組件本體內部邏輯與呼叫端傳參配置**。在未 100% 排除自身問題前，**絕對禁止直接跨模組深入下游/外部模組進行修改**。
  - **修改範疇越界阻斷 (Out-of-Scope Modification Gate)**：若排查發現問題似乎位於超出本次 Dev Plan 承諾範圍的外部模組，**Agent 絕對禁止擅自修改外部代碼**！必須立即發起 Discuss 向開發者呈遞調用證據，由開發者判定。
  - **阻斷盲目淺層修補 (Anti-Trial-and-Error Loop)**：同一問題**連續 2 次修復失敗**，或修復將破壞既有架構/API 簽名時，必須強制停手發起 Discuss 進行 5-Whys 根因分析。
- **Phase 0 討論模式鐵律**：
  - **知識顧問模式 (Zero Speculation in Discussion)**：在 Phase 0 討論階段，Agent 僅作為知識顧問，針對開發者陳述提出釐清問題。除非開發者明確要求，否則嚴禁主動提出設計方案、功能清單或架構建議。
  - **討論結束由開發者明確宣告**：Agent 絕對禁止自行判定討論已完整並推進。必須等待開發者明確表示後，才可將 `P00_semantic_requirements.md` 標記為 `Confirmed`。
  - **先 P00 後分流**：P00 確認後，在同一輪呈遞三大分流層級建議，由開發者最終決定 Track。
- **Test-First 測試前置定稿條款**：`P06_test_plan.md` 必須於 Phase 2 隨設計同步初始化草擬 (Draft)，並於 Phase 4 Review 階段與 `P04_implementation_plan.md` 一併剛性定稿 (Confirmed)，嚴禁延至 Phase 6 才開始憑空設計測試項目。
- **Phase 6 UX / 手動測試 Checkpoint 強制等待關卡**：即使 CLI 自動化測試 100% Passed，Agent **絕對禁止**自行將 P06 標記為 `Passed` 或擅自進入 Phase 7！必須呈遞測試結果，並明確詢問開發者進行實際互動/視覺/UX 驗證。必須等待開發者明確回覆「UX 驗證通過/指示免測」後，方可將 P06 標記為 `Passed` 並推進至 Phase 7。
- **Phase 6 驗證防呆鐵律 (無 Log 即未驗證)**：若 CLI 編譯/測試命令執行受阻，Agent **絕對禁止**在 `P06_test_plan.md` 與對話中標記 `Passed`。必須明確標記 `[未實機編譯/僅靜態檢查]`，並呈遞精確命令請開發者於控制台執行回填。
- **雙星伴隨初始化鐵律**：開立計畫目錄時，`P00_semantic_requirements.md` 必須與 `changelog.md` 剛性伴隨同時建立，立即寫入第 1 筆紀錄。
- **目錄歸檔紀律與 CLI 調度優先**：所有計畫預設留存原位（`plans://`），嚴禁 Agent 主動歸檔，僅在開發者明確下達歸檔指令時才執行歸檔工具。
- **CLI 指令防呆比對與 Default-Deny 守門鐵律**：
  - **查表比對**：Agent 在欲調用 `python yscb.py` 宿主或子模組指令前，必須先比對 `AgentsCliGuild.md`。僅在當前情境 100% 符合 `✅ 推薦/適用情境` 時方可執行。
  - **Default-Deny 閉環**：若欲執行之指令或參數組合未列於表、無對應推薦欄位、或命中 `🚨 絕對禁止/不適用情境`（例：跑測前手動 build、未授權 bump 版本、日常跑 test --all、調用內部 op-test 等），**絕對禁止擅自執行**！必須向開發者確認意圖與預期指令，獲明確授權後方可執行。
- **巢狀層級硬性約束**：專案嚴格限制子計畫目錄最多**兩層結構**（主計畫 ➔ 子計畫），**絕對禁止在子計畫下再開子計畫**！

---

# Agent 專案行為準則與防呆紀律規範 (Agents Standards)

本文件定義 Agent 在專案內執行任務時**必須強制遵守**的通用硬性核心原則、防呆紀律與工程規範。

---

## 1. 核心原則與防呆紀律 (Core Principles & Guardrails)

Agent 必須始終遵守以下三大原則：
1. **零臆測 (Zero Speculation)**：任何不確定的技術細節，都必須與開發者釐清後才能推進。禁止自行假設需求、猜測 API 行為或臆測解法。
2. **可追溯 (Traceability)**：從需求到程式碼的每一步決策，都必須有文件記錄可回溯（`P00 語意` ➔ `FR/EC` ➔ `[{Phase}:DR-XX]` ➔ `API 簽名` ➔ `程式碼` ➔ `測試`）。
3. **分級管控 (Graduated Control)**：完整 Phase 0 語意化討論後，依三大分流層級矩陣選擇 Level 0 (Fast Track)、Level 1 (Full Track) 或 Level 2 (Umbrella 分類型主計畫模式)。

### 🚨 執行紀律（絕對禁止條款）
- **嚴禁連發**：一次回應 (Turn) **最多只能執行一個 Phase**。產出階段文件後，必須以明確文字詢問開發者並**立即 End Turn** 等待回覆。
- **Checkpoint 強制等待**：產出 Phase 文件後，必須等待開發者明確給予對該階段的「確認/同意/推進」指示，絕對禁止 Agent 自行假設通過並推進下一個 Phase。
- **「問答 $\neq$ 推進」防呆條款 (Clarification $\neq$ Advancement Disambiguation)**：
  - **回覆意圖二分法**：Agent 必須嚴格區分開發者的回覆類型：
    - **類型 A：局部解答 / 意見回饋**（例：解答 Agent 提問、提供特定參數、修改某欄位）➔ Agent **僅可更新當前 Phase 文件**，呈遞更新摘要與變更處，並明確詢問「已為您更新 [項目]，請問本階段內容是否確認無誤，可指示推進至下一階段？」並**立即 End Turn 等待**，**絕對禁止直接跨入下一 Phase**！
    - **類型 B：推進 / 定稿指令**（例：「確認」、「通過」、「進入 Phase X」、「沒有其他問題了」）➔ 只有接收到此類明確信號，Agent 才能將當前 Phase 標記為 `Confirmed` / `Passed` 並推進。
  - **嚴禁複合推論**：絕對禁止 Agent 自行假設「因為開發者解答了疑問 ➔ 代表整份文件無其他問題 ➔ 自動推進」。
  - **更新後二次確認 (Update & Re-confirm Loop)**：文件修訂後必須重新呈遞修改摘要，並重新等待開發者明確給出類型 B 指令。
- **嚴禁空降實作**：未經 Phase 1~4（或 FT-1）規劃並獲得開發者確認前，**絕對禁止直接編寫或修改原始碼**。
- **除錯排查與範疇保護鐵律 (Scope-Bound Debugging & Anti-Drift Guardrail)**：
  - **「由近及遠、本體優先」排查階層 (Local-First Hierarchy)**：遇到錯誤、異常或視覺/邏輯不符預期時，Agent **必須優先徹底排查當前組件本體內部邏輯與呼叫端傳參配置**。在未 100% 排除自身問題前，**絕對禁止直接跨模組深入下游/外部模組進行修改**。
  - **修改範疇越界阻斷 (Out-of-Scope Modification Gate)**：若排查發現問題似乎位於超出本次 Dev Plan 承諾範圍的外部模組，**Agent 絕對禁止擅自修改外部代碼**！必須立即發起 Discuss 向開發者呈遞調用證據，由開發者判定。
  - **阻斷盲目淺層修補 (Anti-Trial-and-Error Loop)**：同一問題**連續 2 次修復失敗**，或修復將破壞既有架構/API 簽名時，必須強制停手發起 Discuss 進行 5-Whys 根因分析。
- **Phase 0 討論模式鐵律**：
  - **知識顧問模式 (Zero Speculation in Discussion)**：在 Phase 0 討論階段，Agent 僅作為知識顧問，針對開發者陳述提出釐清問題。除非開發者明確要求，否則嚴禁主動提出設計方案、功能清單或架構建議。
  - **討論結束由開發者明確宣告**：Agent 絕對禁止自行判定討論已完整並推進。必須等待開發者明確表示後，才可將 `P00_semantic_requirements.md` 標記為 `Confirmed`。
  - **先 P00 後分流**：P00 確認後，在同一輪呈遞三大分流層級建議，由開發者最終決定 Track。
- **Test-First 測試前置定稿條款**：`P06_test_plan.md` 必須於 Phase 2 隨設計同步初始化草擬 (Draft)，並於 Phase 4 Review 階段與 `P04_implementation_plan.md` 一併剛性定稿 (Confirmed)，嚴禁延至 Phase 6 才開始憑空設計測試項目。
- **Phase 6 UX / 手動測試 Checkpoint 強制等待關卡**：即使 CLI 自動化測試 100% Passed，Agent **絕對禁止**自行將 P06 標記為 `Passed` 或擅自進入 Phase 7！必須呈遞測試結果，並明確詢問開發者進行實際互動/視覺/UX 驗證。必須等待開發者明確回覆「UX 驗證通過/指示免測」後，方可將 P06 標記為 `Passed` 並推進至 Phase 7。
- **Phase 6 驗證防呆鐵律 (無 Log 即未驗證)**：若 CLI 編譯/測試命令執行受阻，Agent **絕對禁止**在 `P06_test_plan.md` 與對話中標記 `Passed`。必須明確標記 `[未實機編譯/僅靜態檢查]`，並呈遞精確命令請開發者於控制台執行回填。
- **雙星伴隨初始化鐵律**：開立計畫目錄時，`P00_semantic_requirements.md` 必須與 `changelog.md` 剛性伴隨同時建立，立即寫入第 1 筆紀錄。
- **目錄歸檔紀律與 CLI 調度優先**：所有計畫預設留存原位（`plans://`），嚴禁 Agent 主動歸檔，僅在開發者明確下達歸檔指令時才執行歸檔工具。
- **CLI 指令防呆比對與 Default-Deny 守門鐵律**：
  - **查表比對**：Agent 在欲調用 `python yscb.py` 宿主或子模組指令前，必須先比對 `AgentsCliGuild.md`。僅在當前情境 100% 符合 `✅ 推薦/適用情境` 時方可執行。
  - **Default-Deny 閉環**：若欲執行之指令或參數組合未列於表、無對應推薦欄位、或命中 `🚨 絕對禁止/不適用情境`（例：跑測前手動 build、未授權 bump 版本、日常跑 test --all、調用內部 op-test 等），**絕對禁止擅自執行**！必須向開發者確認意圖與預期指令，獲明確授權後方可執行。
- **巢狀層級硬性約束**：專案嚴格限制子計畫目錄最多**兩層結構**（主計畫 ➔ 子計畫），**絕對禁止在子計畫下再開子計畫**！

---


### 🧠 知識庫檢索與註解防護規範 (Knowledge-DB Standards)

- **知識檢索優先紀律 (Knowledge-First Axiom)**：
  - Agent 在探索專案架構、查找類別/函式或尋找既有實現時，**必須優先調用 `python yscb.py knowledge-db search <query>` 或查閱 `workflow.docs://` 知識庫**。
  - **絕對禁止**在未經定向索引前，盲目發起大範圍檔案正則遍歷、暴力 grep 或逐檔全文讀取。
- **Docstring 與符號結構防護鐵律 (Docstring Integrity Guardrail)**：
  - Agent 在編寫或重構 Public API 時，**嚴禁刪除或破壞已有的標準 Docstring 註解結構**，必須確保符號能被 `knowledge-db` AST 解析器無損提取。
<!-- YSCB_AGENTS_END -->

## 4. 專案特化工程規範 (Project Specific Standards)
*(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*

### 🚨 Dogfooding 自引用代碼庫三層空間邊界與防呆鐵律 (Dogfooding Axiom)
本專案呈現「自引用 (Dogfooding)」狀態，Agent 必須強制遵守以下三大空間隔離與四步標準閉環流水線：

#### 1. 三層空間權限矩陣
- **空間 ① 源碼開發空間 (`:/ys_codebase/`)**：【唯一源碼來源 (SSOT)】包含 `ys_codebase/source/`、`ys_codebase/yscb_*.py`。所有代碼、腳本、SOP 工作流修改 **100% 必須在此空間進行**。
- **空間 ② 測試驗證空間 (`:/test/`)**：【品質守門閘門】執行 `python test/run_regression.py`。未 100% 通過前嚴禁放行更新自引用產物。
- **空間 ③ 自引用消費空間 (`:/` 專案根目錄)**：【發布運行產物】包含 `modules/`、`.agents/`、根目錄 `yscb_*.py`。**視為編譯產物，嚴禁手動直接修改**，必須透過 CLI 指令自動同步。

#### 2. 標準四步閉環流水線 (The Canonical 4-Stage Pipeline)
1. `Stage 1 (Source)`: 編輯 `ys_codebase/source/...` 或 `ys_codebase/yscb_*.py`。
2. `Stage 2 (Build)`: `python yscb_cli.py installer build <module>` (或 `build --all`)。
3. `Stage 3 (Regression)`: 實機執行 `python test/run_regression.py` (維持 23/23 + E2E 100% Passed)。
4. `Stage 4 (Dogfooding Sync)`:
   - 覆蓋同步根目錄起手腳本 (`yscb_installer.py` / `yscb_cli.py`)。
   - `python yscb_cli.py installer install <module> --force` 部署至 `modules/`。
   - `python yscb_cli.py agents-workflow --ide-antigravity` 重新生成 `.agents/workflows/`。
   - 檢查 `AGENTS.md` 軟合併無損。

