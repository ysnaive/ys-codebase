# Phase 6: 測試驗證與品質驗收 (P06 Test Guide)

本手冊定義 Phase 6 測試執行、回填規範、UX 驗收 Checkpoint 守門與盲目修補阻斷鐵律。

---

## 🎯 1. 核心定位與職責

- **實機跑測與回填**：100% 依據 `P06_test_plan.md` 執行自動化測試與回歸測試，客觀回填測試日誌。
- **人工 / UX 驗收守門**：若包含人機介面、CLI 輸出或終端交互變更，強制等待開發者驗收確認。
- **阻斷盲目修補**：測試失敗時遵守排查階層與 5-Whys 根因溯源。

---

## 🧪 2. 測試執行與回填鐵律

1. **隔離沙盒跑測**：
   - 執行 `python yscb.py dev test <module> --quiet`（單元/邊界測試）與 `python yscb.py dev test --all --quiet`（全量回歸）。
2. **測試紀錄客觀回填**：
   - 在 `P06_test_plan.md` 之「測試執行紀錄表」如實填寫執行狀態（`Passed` / `Failed`）、執行時間與關鍵日誌摘要。
3. **部署後免重複測試鐵律**：
   - 通過沙盒測試並完成 `@build` 或正式安裝後，**嚴禁重複調用 `dev test` 跑測**；物化完成即結案交付。

---

## 🚨 3. 人工 / UX 驗證 Checkpoint 守門

- 若測試計畫中定義了 `UX-{XX}` 人工驗證項目：
  - **嚴禁 Agent 自行勾選為 Passed**。
  - Agent 必須呈遞驗證方法與預期效果，明確詢問開發者並 **立即 End Turn 等待回饋**。
  - 唯有在開發者明確回覆「驗收通過」或「指示免測」後，方可標記為完成並推進至 Phase 7。

---

## 🛡️ 4. 除錯排查與防淺層修復 (Anti-Blind Patching)

- **本體優先階層**：排查錯誤優先排查當前組件內部邏輯與傳參，未排除自身問題前禁止深入下游外部模組。
- **連續失敗阻斷**：同一問題連續 2 次修復失敗或破壞 API 簽名時，**強制停手發起 [/Discuss](`__#{module://agents-workflow/assets/workflows/Discuss.md}__`) 進行 5-Whys 根因分析**。

---

`__@{PHASE06_AGENTS_GUILD}__`

---

## 🛑 5. Phase 6 結束 Checkpoint

- 自動化測試 100% Passed，全系統回歸 100% Passed。
- `P06_test_plan.md` 狀態更新為 **`Completed`**（或等待 UX 確認中）並更新 `changelog.md`。
- **極精簡 Session 回覆格式**：對話中**嚴禁全文重複、日誌傾倒或冗長轉述**，強制僅呈遞以下極簡卡片：
  ```markdown
  ### 📄 P06 測試驗證回報
  - **產出文件**：[P06_test_plan.md](__${project://plans/}__/{plan_name}/P06_test_plan.md) (Completed / 待驗收)
  - **測試摘要**：[單元/邊界測試 N 項 100% 通過 / 全量回歸 100% 通過]
  - **待手動驗證項**：[若有 UX/實機測試，極簡條列操作指令與預期效果；若無填「無」]
  - **待確認事項**：[若有待驗項請開發者操作驗證；若無則詢問是否推進至 Phase 7？]
  ```
- **立即 End Turn 等待確認**：嚴禁跨階段連續產出。
