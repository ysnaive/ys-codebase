---
name: auto
description: 針對已確認需求之計畫自動連續執行規格產出、代碼實作與測試驗證。僅於顯式輸入 /auto 或明確指示自動連續推進計畫時觸發。
---

# 自動連續推進工作流 (Auto)

本工作流用於 Full Track 或 Umbrella 子計畫處於 Phase 00 (Confirmed) 或 Phase 01 ~ 05 時，跳過中間 Checkpoint 連續推進至 Phase 6 手動/UX 驗證守門點。執行規範遵循 [development-sop](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)。

---

## 適用情境與觸發時機

- **適用情境**：進行中之 Full Track 計畫或 Umbrella 活躍子計畫。
- **觸發時機**：處於 Phase 00 (Confirmed) 或 Phase 01 ~ Phase 05 時輸入 `/auto`（或 `/Auto`），或明確指示自動連續推進。
- **排除情境（負向邊界）**：
  - **Phase 0 未確認**：`P00_discuss.md` 處於 Draft / Discussing 時需求邊界必須先由開發者確認定稿 (`Confirmed`) 方可觸發 `/auto`。
  - **Fast Track**：流程極簡（3-Step），無多階段等待需求，請直接依 `fast_track_plan.md` 推進。
  - **僅需恢復中斷現場**：若僅要讀取 `handoff.md` 查看上次進度而非連續跑完 Phase 01~05，請改用 [continue](`__#{module://agents-workflow/assets/skills/continue/SKILL.md}__`)。

---

## [!] 核心原則與熔斷機制

執行連續推進時強制遵守以下熔斷機制，一旦觸發立即暫停：
1. **零臆測熔斷**：需求語意不明或規格存在歧義時，因為自行假設會造成後續階段連鎖返工，禁止自行腦補，立即暫停釐清。
2. **偏差熔斷**：產生 Major/Critical 架構或 API 偏差時，立即轉入 [/discuss](`__#{module://agents-workflow/assets/skills/discuss/SKILL.md}__`)。
3. **P06 手動/UX 驗證阻斷**：抵達 Phase 6 且自動化測試通過後，嚴禁自行標記 `Completed` 或進入 Phase 7，強制停步等待開發者驗收。
4. **文件保真與技能調用**：各 Phase 文件與 `changelog.md` 仍須完整生成；執行具體動作時遵循專案準則調用專屬技能與階段作業手冊。

---

## 執行步驟

開始執行時，請複製以下檢核表追蹤連續推進狀態：

```markdown
/Auto 連續推進檢核表：
- [ ] 步驟 1：掃描 `__${project://plans}__` 確認目標計畫處於 P00 (Confirmed) 或 P01~P05
- [ ] 步驟 2：依序連續產出並定稿 Phase 01 -> Phase 05 產物與代碼實作
- [ ] 步驟 3：執行 Phase 06 自動化測試並回填 P06_test_plan.md 直至 100% 通過
- [ ] 步驟 4：輸出極簡 P06 驗證 Checkpoint 狀態卡並立即 End Turn 等待驗收
```

### 步驟 1：掃描計畫與狀態判定
1. 檢視 `__${project://plans}__` 定位進行中之計畫。
2. 檢查當前階段（若處於 Phase 0 未 Confirmed 或 Fast Track，提示不適用並中斷；若 P00 處於 Confirmed 則直接自 Phase 1 啟動連續推進）。

### 步驟 2：連續推進閉環 (Phase 01 -> 05)
從當前斷點依序連續產出並定稿各階段產物，跳過中間等待點：
- **Phase 1**：[`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`)
- **Phase 2**：[`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`)
- **Phase 3**：[`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`)
- **Phase 4**：[`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`)、一次建立並定稿 [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`) (Confirmed)
- **Phase 5**：[`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`)，編碼實作與單元測試
- 階段推進同步記錄至 [`changelog.md`](`__#{module://agents-workflow/assets/templates/changelog.md}__`)。

### 步驟 3：Phase 6 自動化測試
1. 執行專案定義之自動化測試指令。
2. 測試結果回填至 [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`)。若遇連續失敗觸發偏差熔斷轉入 [/discuss](`__#{module://agents-workflow/assets/skills/discuss/SKILL.md}__`)。

### 步驟 4：抵達 P06 手動/UX 驗證 Checkpoint（強制等待）
1. 自動化測試 100% 通過。
2. **極精簡 Session 回覆格式**：對話 Session **嚴禁全文重複、代碼傾倒或日誌傾倒**，強制僅呈遞以下極簡卡片：
   ```markdown
   ### 🚦 /Auto 連續推進完成 (抵達 P06 驗證 Checkpoint)
   - **產出文件**：[P06_test_plan.md](`__${project://plans}__`/{plan_name}/P06_test_plan.md) (Passed / 待驗收)
   - **推進摘要**：Phase 01 ~ Phase 05 已連續產出並定稿；自動化測試 100% 通過
   - **手動/UX 驗收項目**：[若有 UX 項目，條列項目與操作預期；若無填「無」]
   - **待確認事項**：[若有 UX 項目請確認驗收結果為 [測試通過] 或是 [跳過/免測]；確認完成後將進入 Phase 7 (P07 成果展示與 SOP Review 結案)]
   ```
3. **[!] 立即 End Turn 等待開發者回覆**：絕對禁止自行將 P06 標記為 `Completed` 或擅自推進至 Phase 7。
4. **接續推進與表層修訂分流硬性約束**：
   - 開發者確認 UX 驗證結果（無論為 `[測試通過]` 或是 `[跳過/免測]`）後，**唯一法定下一步為進入 [Phase 7 (P07 結案與 SOP 審查)](`__#{module://agents-workflow/assets/skills/development-sop/references/phase_07_walkthrough.md}__`)**。
   - 若開發者在 P06 期間不再反饋邏輯 Bug 或錯誤行為，轉而開始要求微調 UI/UX/DX、參數或文檔，Agent 應主動提問確認業務核心是否已無問題，並建議先進入 P07 結案審查後再建立 [`revision_log.md`](`__#{module://agents-workflow/assets/templates/revision_log.md}__`) 進行修訂。
   - P07 內化三層文檔對齊、測試完整性與 `plan verify` 合規檢核，確認 100% Passed 後方可結案。

---

## 常見踩坑指南 (Gotchas)

- **切勿因為自動推進而省略中間產物檔案**：`/auto` 跳過的是「階段間的人工確認等待」，而非跳過 `P01`~`P05` 的實體 Markdown 文件生成。漏產文件會導致 `Phase 07` 的 `plan verify` 合規檢核失敗。
- **切勿跳過 Phase 06 手動/UX 驗收守門直接寫出 `P07_walkthrough.md`**：抵達 `P06` 後必須強制 End Turn 將控制權交還開發者。
