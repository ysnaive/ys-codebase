# Phase 7: 成果展示與結案報告 (P07 Walkthrough Guide)

本手冊定義 Phase 7 成果展示、開發歷程總結、全域發布日誌追加與結案交付規範。

---

## 🎯 1. 核心定位與前置條件

- **🚨 前置守門條件**：進入 Phase 7 前，**必須已通過 SOP [Review Gate](./review_gate.md) 步驟並產出 Review Verdict 審查卡**。嚴禁未經審查直接建立結案報告！
- **產出結案報告**：建立 `P07_walkthrough.md`，全面總結變更成果、測試數據、SOP Review 審查結論與推薦 Commit 訊息。
- **發布日誌追加**：於專案全域 [`__${project://CHANGELOG.md}__`](`__${project://CHANGELOG.md}__`) 追加高階變更條目。

---

## 🔍 2. 開發歷程覆盤與審查結論回填

結案報告撰寫時執行歷程覆盤並回填 Review 審查結論：
1. **需求與實作對齊 (Requirement Alignment)**：核對 `P00` 原始需求與最終交付成果是否 100% 對齊。
2. **偏差紀錄閉環 (Deviation Closure)**：檢視 `P05` 實作偏差紀錄表，確認所有 Minor/Major 偏差均已妥善解決並閉環。
3. **Review 審查結論回填**：將 SOP Review 步驟中核驗之三層文檔對齊清冊、測試通過率（含手動 UX 二元標定項目）如實回填於 `P07_walkthrough.md`。

---

## 📦 3. 發布邊界與 Commit 紀律

- **生態系模組發布邊界鐵律**：
  - Phase 7 結案時，模組物化**一律僅能維持軌道 A（`@build` 直裝）**。
  - **🚨 嚴禁自主升版發布**：嚴禁 Agent 在結案階段擅自調用 `dev bump` 或 `dev release`（此為 🔴 授權守門級別，必須獲開發者顯式指示方可執行）。
- **計畫目錄歸檔紀律**：
  - 開發計畫目錄預設留存於 `__${project://plans/}__` 原位，**嚴禁 Agent 自行執行 `plan archive` 或主動搬移目錄**（除非開發者明確下達歸檔指令）。
- **推薦 Commit 訊息**：
  - 結案報告尾部提供符合 Conventional Commits 規範之推薦 Commit 訊息，供開發者直接採用。

---

`__@{PHASE07_AGENTS_GUILD}__`

---

## 🛑 4. Phase 7 結束 Checkpoint

- `P07_walkthrough.md` 建立完成（狀態 `Completed`），全域 [`__${project://CHANGELOG.md}__`](`__${project://CHANGELOG.md}__`) 追加完成，`changelog.md` 記錄結案。
- **極精簡 Session 回覆格式**：對話中**嚴禁全文重複、傾倒完整結案報告或大篇幅轉述**，強制僅呈遞以下極簡卡片：
  ```markdown
  ### 📄 P07 開發成果已結案
  - **產出文件**：[P07_walkthrough.md](__${project://plans/}__/{plan_name}/P07_walkthrough.md)、[changelog.md](__${project://plans/}__/{plan_name}/changelog.md)、[CHANGELOG.md](__${project://CHANGELOG.md}__)
  - **結案摘要**：[1~2 行高階成果 / 通過 SOP Review 審查與合規檢核]
  - **推薦 Commit**：`[type(scope): brief message]`
  - **後續動作**：[計畫已圓滿結案，可依需求執行 commit、plan archive 或依指示進行對話歷程評測]
  ```
- **立即 End Turn 等待指示**。
