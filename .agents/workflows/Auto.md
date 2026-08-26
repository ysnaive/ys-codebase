---
description: 自動連續推進工作流 (Auto) — 支援 Phase 01~05 跳過中間 Checkpoint 連續執行直至 P06 手動驗證
---

# 自動連續推進工作流 (Auto)

本 Workflow 用於在進行中之 **Full Track (Level 1)** 開發計畫或 **Umbrella (Level 2)** 活躍子計畫處於 **Phase 01 ~ Phase 05** 之間時，授權 Agent 在無未確定技術疑問與無爭議的前提下，跳過中間強制 Checkpoint 連續推進，直至 **Phase 6 手動/UX 驗證 Checkpoint** 前強制停步。所有階段的具體標準請嚴格遵循 [標準開發作業流程 (NewPlan)](`./NewPlan.md`)。

---

## 🎯 適用情境與觸發時機 (Scope & Triggers)

- **適用情境**：
  - **Full Track (Level 1)** 進行中計畫。
  - **Umbrella (Level 2)** 主計畫下處於進行中狀態之 Full Track 子計畫 (`sub_XX`)。
- **觸發時機**：
  - 開發者於 **Phase 01 ~ Phase 05** 之間的任何時點輸入 `/Auto` 或下達連續推進指令。
- **不適用情境 (Explicit Exclusions)**：
  - **Phase 0 討論階段**：需求收斂必須由開發者確認定稿，嚴禁於 Phase 0 跳過討論。
  - **Fast Track (Level 0)**：流程極簡且無多階段等待需求，不適用 `/Auto`。

---

## 🚨 核心原則與三大熔斷機制 (Circuit Breakers)

在執行自動連續推進時，Agent 必須強制遵守以下三大熔斷防線，一旦觸發必須立即中斷自動流程：

1. **零臆測熔斷 (Zero Speculation Gate)**：
   - 遭遇任何需求語意不明、API 行為未定、或規格存在歧義之技術疑問時，**絕對禁止自行猜測**，必須立即暫停並向開發者提問釐清。
2. **偏差熔斷 (Deviation Gate)**：
   - 實作過程若發現需要修改外部模組、破壞既有 Public API、或產生 Major/Critical 架構偏差時，必須立即停止實作並轉入 [深度歸因與防淺層修復 (Discuss)](`./Discuss.md`)。
3. **P06 手動/UX 驗證絕對阻斷 (Mandatory UX Gate)**：
   - 推進至 Phase 6 且 CLI 自動化測試 100% 通過後，**絕對禁止** Agent 自行將 P06 標記為 `Passed` 或擅自進入 Phase 7 結案！必須強制停步呈遞測試報告，等待開發者明確回覆「UX 驗證通過/指示免測」。
4. **規範與文件 100% 保真**：
   - 連續推進期間，所有對應 Phase 文件（[`P01_requirements_spec.md`](`../.yscb/templates/P01_requirements_spec.md`)、[`P02_architecture_plan.md`](`../.yscb/templates/P02_architecture_plan.md`)、[`P03_api_spec.md`](`../.yscb/templates/P03_api_spec.md`)、[`P04_implementation_plan.md`](`../.yscb/templates/P04_implementation_plan.md`)、[`P05_task.md`](`../.yscb/templates/P05_task.md`)、[`P06_test_plan.md`](`../.yscb/templates/P06_test_plan.md`) 與計畫內部 [`changelog.md`](`../.yscb/templates/changelog.md`)）仍必須 100% 嚴格鏡像標準模板完整生成與記錄，不可略過或縮減產物。

---

## 🚀 執行步驟 (4-Step Execution Pipeline)

### 步驟 1：掃描目標計畫與斷點狀態 (Plan & State Detection)

1. 檢視 `workflow.plans://` 定位當前進行中之 Full Track 計畫（或 Umbrella 活躍子計畫 `sub_XX`）。
2. 檢查當前處於 Phase 01 ~ Phase 05 之哪一階段。
3. **邊界狀態防禦**：
   - **若處於 Phase 0**：提示開發者：「Phase 0 語意討論必須由開發者確認定稿，P00 標記為 `Confirmed` 後方可啟用 `/Auto`」，中斷執行。
   - **若處於 Fast Track**：提示開發者：「Fast Track (Level 0) 無多階段等待需求，不適用 `/Auto`」，中斷執行。
   - **若處於 Umbrella 主計畫**：自動定位至當前處於 `進行中` / `In Progress` 的目標子計畫目錄 `sub_XX/`。

---

### 步驟 2：連續推進閉環 (Continuous Advancement Loop)

從當前斷點 Phase 開始，依序連續執行以下階段（跳過中間 Checkpoint 等待）：

1. **Phase 1 (需求規格轉譯)**：
   - 產出 [`P01_requirements_spec.md`](`../.yscb/templates/P01_requirements_spec.md`)，確認與 P00 1:1 映射後標記為 `Confirmed`。
2. **Phase 2 (架構設計與模組拆解)**：
   - 產出 [`P02_architecture_plan.md`](`../.yscb/templates/P02_architecture_plan.md`)，同步 Test-First 初始化 [`P06_test_plan.md`](`../.yscb/templates/P06_test_plan.md`) (Draft)，標記 P02 為 `Confirmed`。
3. **Phase 3 (API 與介面規格定義)**：
   - 產出 [`P03_api_spec.md`](`../.yscb/templates/P03_api_spec.md`)，標記為 `Confirmed`。
4. **Phase 4 (實作計畫定稿與靈魂拷問)**：
   - 產出 [`P04_implementation_plan.md`](`../.yscb/templates/P04_implementation_plan.md`) (Confirmed)，並同步剛性定稿 [`P06_test_plan.md`](`../.yscb/templates/P06_test_plan.md`) (Confirmed)。
5. **Phase 5 (依序程式碼實作)**：
   - 建立 [`P05_task.md`](`../.yscb/templates/P05_task.md`)，依 P04 拓撲順序編寫程式碼與單元測試。
- 📝 **日誌同步**：每一個 Phase 推進均同步寫入計畫內部 [`changelog.md`](`../.yscb/templates/changelog.md`)。

---

### 步驟 3：Phase 6 自動化測試與日誌登載 (Automated Verification)

1. 實機執行 CLI 自動化測試（如 `python yscb.py dev test <module>`）。
2. 將實機測試日誌摘要回填至 [`P06_test_plan.md`](`../.yscb/templates/P06_test_plan.md`)。
3. 若測試失敗，遵循除錯排查範疇保護鐵律進行修復；若連續 2 次修復失敗或涉及架構變更，立即觸發偏差熔斷轉入 `/Discuss`。

---

### 步驟 4：抵達 P06 UX/手動驗證 Checkpoint（強制等待）

1. CLI 自動化測試 100% Passed 後，向開發者呈遞測試結果摘要與執行日誌。
2. 明確詢問開發者進行實際互動/視覺/UX 驗證。
3. **🚨 立即 End Turn 等待開發者回覆**：絕對禁止自行將 P06 標記為 `Passed` 或擅自進入 Phase 7！必須等待開發者明確給出「UX 驗證通過/指示免測」指令後，方可推進至 Phase 7 交付結案。

---

