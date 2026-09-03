# Phase 7: 成果展示與結案審查 (P07 Walkthrough Guide)

本手冊定義 Phase 7 成果展示、三層文檔 1:1 交付驗收、全域發布日誌追加與結案交付規範。

---

## 🎯 1. 核心定位與職責

- **產出結案報告**：建立 `P07_walkthrough.md`，全面總結變更成果、測試數據與推薦 Commit 訊息。
- **三層文檔 1:1 交付對齊 (Documentation Delivery Audit)**：逐項核驗宏觀、中觀與微觀文檔交付完整度。
- **發布日誌追加**：於專案全域 `CHANGELOG.md` 追加高階變更條目。

---

## 📚 2. 三層文檔 1:1 交付驗收對齊鐵律

在 `P07_walkthrough.md` 中必須建立文檔交付驗收表格，進行剛性核對：

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀發布日誌** | `CHANGELOG.md` | ✅ 已交付 | 已追加本次計畫名稱與高階架構變更摘要 |
| **中觀模組手冊** | `docs/<Category>/README.md` | ✅ 已交付 | Public API 變更或新增功能已同步反映 |
| **中觀專題手冊** | `docs/<Category>/[topic].md` | ✅ 已交付 | 複雜跨類別機制或資料管線已獨立成冊 |
| **中觀設計決策** | `docs/<Category>/DESIGN_NOTES.md` | ✅ 已交付 | 反直覺設計已登記 `DN-XX` 並標註 `[!CAUTION]` |
| **微觀代碼註解** | 程式碼本體 | ✅ 已交付 | Docstrings 結構完整，Why-Driven 動機註解清晰 |

> 🚨 **交付阻斷**：上述文檔若有任何一項涉及更動但未交付，**嚴禁宣告結案**。核驗或編輯文檔前，應調用文檔規範技能。

---

## 📦 3. 計畫目錄歸檔與 Commit 紀律

- **計畫目錄歸檔紀律**：
  - 開發計畫目錄預設留存於 `plans/` 原位，**嚴禁 Agent 自行執行 `plan archive` 或主動搬移目錄**（除非開發者明確下達歸檔指令）。
- **推薦 Commit 訊息**：
  - 結案報告尾部提供符合 Conventional Commits 規範之推薦 Commit 訊息，供開發者直接採用。

---

`__@{PHASE07_AGENTS_GUILD}__`

---

## 🛑 4. Phase 7 結束 Checkpoint

- `P07_walkthrough.md` 建立完成，狀態標記為 `Completed`。
- 全域 `CHANGELOG.md` 追加完成。
- 計畫微觀日誌 `changelog.md` 記錄 Phase 7 結案。
- 向開發者呈報完整結案報告，計畫正式圓滿結案！
