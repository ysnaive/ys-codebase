# Phase 7: 成果展示與結案審查 (P07 Walkthrough Guide)

本手冊定義 Phase 7 成果展示、開發歷程回顧、聯動 [/Review 工作流](`__#{module://agents-workflow/assets/workflows/Review.md}__`) 結案驗收、全域發布日誌追加與結案交付規範。

---

## 🎯 1. 核心定位與職責

- **產出結案報告**：建立 `P07_walkthrough.md`，全面總結變更成果、測試數據與推薦 Commit 訊息。
- **開發歷程覆盤與 `/Review` 工作流聯動**：回顧 P00~P06 完整歷程，強制聯動 [/Review 工作流](`__#{module://agents-workflow/assets/workflows/Review.md}__`) 進行五維度品質驗收（含三層文檔 1:1 交付審查）。
- **發布日誌追加**：於專案全域 [`__${project://CHANGELOG.md}__`](`__${project://CHANGELOG.md}__`) 追加高階變更條目。

---

## 🔍 2. 開發歷程覆盤與 `/Review` 工作流結案驗收

結案前必須執行開發歷程覆盤並連動 [/Review 工作流](`__#{module://agents-workflow/assets/workflows/Review.md}__`)：
1. **開發歷程覆盤 (Development Lifecycle Audit)**：
   - 核對 `P00` 原始需求與最終交付成果是否 100% 對齊。
   - 檢視 `P05` 實作偏差紀錄表，確認所有 Minor/Major 偏差均已妥善解決並閉環。
2. **連動 `/Review` 工作流 (Five Quality Pillars)**：
   - 主動觸發或依循 [/Review 工作流](`__#{module://agents-workflow/assets/workflows/Review.md}__`)，執行五維度品質矩陣驗收（程式碼品質、日誌安全性、**三層文檔 1:1 交付**、測試覆蓋、Commit 規範）。
   - 發現任何瑕疵或文檔缺漏立即修復閉環，並將審查結論記錄於 `P07_walkthrough.md`。

---

## 📦 3. 計畫目錄歸檔與 Commit 紀律

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
  - **結案摘要**：[1~2 行高階成果 / 通過 /Review 五維審查（含文檔對齊）]
  - **推薦 Commit**：`[type(scope): brief message]`
  - **後續動作**：[計畫已圓滿結案，可依需求執行 commit、plan archive 或調用 [/SessionAnalysis](__#{module://agents-workflow/assets/workflows/SessionAnalysis.md}__) 進行歷程評測]
  ```
- **立即 End Turn 等待指示**。
