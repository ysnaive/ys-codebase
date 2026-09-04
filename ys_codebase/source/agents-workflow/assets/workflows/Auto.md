# 自動連續推進工作流 (Auto)

本工作流用於 Full Track 或 Umbrella 子計畫處於 Phase 01 ~ 05 時，跳過中間 Checkpoint 連續推進至 Phase 6 手動/UX 驗證守門點。執行規範遵循 [NewPlan](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`)。

---

## 🎯 適用情境與觸發時機

- **適用情境**：進行中之 Full Track 計畫或 Umbrella 活躍子計畫。
- **觸發時機**：處於 Phase 01 ~ Phase 05 時輸入 `/Auto`。
- **排除情境**：
  - **Phase 0**：需求邊界必須由開發者確認定稿。
  - **Fast Track**：流程極簡，無多階段等待需求。

---

## 🚨 核心原則與熔斷機制

執行連續推進時強制遵守以下熔斷機制，一旦觸發立即暫停：
1. **零臆測熔斷**：需求語意不明或規格存在歧義時，禁止自行假設，立即暫停釐清。
2. **偏差熔斷**：產生 Major/Critical 架構或 API 偏差時，立即轉入 [/Discuss](`__#{module://agents-workflow/assets/workflows/Discuss.md}__`)。
3. **P06 手動/UX 驗證阻斷**：抵達 Phase 6 且自動化測試通過後，嚴禁自行標記 Passed 或進入 Phase 7，強制停步等待開發者驗收。
4. **文件保真與技能調用**：各 Phase 文件與 `changelog.md` 仍須完整生成；執行具體動作時遵循專案準則調用專屬技能。

---

## 🚀 執行步驟

### 步驟 1：掃描計畫與狀態判定
1. 檢視 `__${project://plans/}__` 定位進行中之計畫。
2. 檢查當前階段（若處於 Phase 0 或 Fast Track，提示不適用並中斷）。

### 步驟 2：連續推進閉環 (Phase 01 ➔ 05)
從當前斷點依序連續產出並定稿各階段產物，跳過中間等待點：
- **Phase 1**：[`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`)
- **Phase 2**：[`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`)、初始化 [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`) (Draft)
- **Phase 3**：[`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`)
- **Phase 4**：[`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`)、定稿 [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`) (Confirmed)
- **Phase 5**：[`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`)，編碼實作與單元測試
- 階段推進同步記錄至 [`changelog.md`](`__#{module://agents-workflow/assets/templates/changelog.md}__`)。

### 步驟 3：Phase 6 自動化測試
1. 執行專案定義之自動化測試指令。
2. 測試結果回填至 [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`)。若遇連續失敗觸發偏差熔斷轉入 [/Discuss](`__#{module://agents-workflow/assets/workflows/Discuss.md}__`)。

### 步驟 4：抵達 P06 手動/UX 驗證 Checkpoint（強制等待）
1. 自動化測試 100% 通過。
2. **極精簡 Session 回覆格式**：對話 Session **嚴禁全文重複、代碼傾倒或日誌傾倒**，強制僅呈遞以下極簡卡片：
   ```markdown
   ### 📄 /Auto 連續推進完成 (抵達 P06 驗證 Checkpoint)
   - **產出文件**：[P06_test_plan.md](__${project://plans/}__/{plan_name}/P06_test_plan.md) (Completed / 待驗收)
   - **推進摘要**：Phase 01 ~ Phase 05 已連續產出並定稿；自動化測試 100% 通過
   - **手動/UX 驗收項目**：[若有 UX 項目，條列項目與操作預期；若無填「無」]
   - **待確認事項**：[若有 UX 項目請確認驗收結果為 [測試通過] 或是 [跳過/免測]；確認完成後將強制進入 SOP Review 審查步驟]
   ```
3. **🚨 立即 End Turn 等待開發者回覆**：絕對禁止自行將 P06 標記為 Passed 或擅自推進。
4. **接續推進硬性約束 (SOP Review Gate)**：
   - 開發者確認 UX 驗證結果（無論為 `[測試通過]` 或是 `[跳過/免測]`）後，**唯一法定下一步為強制觸發 SOP [Review Gate](`__#{module://agents-workflow/assets/skills/development-sop/references/review_gate.md}__`)**。
   - **🚨 守門禁令**：**嚴禁跳過 SOP Review 步驟直接產出 `P07_walkthrough.md` 或宣稱結案**；必須執行三層文檔對齊與合規檢核並產出 `Review Verdict Card` 後，方可推進至 Phase 7。

---

`__@{WORKFLOW_AUTO}__`
