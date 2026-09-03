# Phase 4: 實作計畫定稿與審查 (P04 Implementation Plan Guide)

本手冊定義 Phase 4 實作計畫定稿階段之文檔衝擊盤點、架構質詢與測試計畫定稿規範。

---

## 🎯 1. 核心定位與職責

- **實作全面預排**：將 P02 架構與 P03 API 轉化為具體的檔案變更矩陣。
- **7 維度文檔衝擊盤點 (Documentation Impact Audit)**：主動盤點本次開發將衝擊的宏觀、中觀與微觀文檔。
- **剛性品質雙定稿**：同時將 `P04_implementation_plan.md` 與 `P06_test_plan.md` 剛性定稿 (`Status: Confirmed`)。

---

## 📚 2. 文檔衝擊預先盤點清冊

在 `P04` 中必須顯式建立文檔衝擊清冊：
- **宏觀層**：[`__${project://CHANGELOG.md}__`](`__${project://CHANGELOG.md}__`) 變更摘要。
- **中觀層**：
  - 是否新增/修改模組手冊 (`__${project://docs/}__`<Category>/README.md)？
  - 是否需獨立中觀專題手冊 (`__${project://docs/}__`<Category>/[topic].md)？
  - 是否涉及反直覺妥協需登記設計決策 (`__${project://docs/}__`<Category>/DESIGN_NOTES.md + `[!CAUTION]`)？
- **微觀層**：原始碼 Public API 介面註解與 Why-Driven 動機註解。

---

## 🔒 3. `P06_test_plan.md` 剛性定稿鐵律

- 審查 Phase 2 預排之 `P06` 測試案例，補齊執行指令、測試檔案與斷言條件。
- 將 `P06_test_plan.md` 狀態由 `Draft` 修改為 **`Confirmed`**。
- 嚴格守門：測試計畫未 Confirmed 前，**絕對禁止進入 Phase 5 寫任何一行程式碼**。

---

`__@{PHASE04_AGENTS_GUILD}__`

---

## 🛑 4. Phase 4 結束 Checkpoint

- **極精簡 Session 回覆格式**：產出 `P04_implementation_plan.md` 與定稿 `P06_test_plan.md` 並更新 `changelog.md` 後，對話中**嚴禁全文重複、代碼傾倒或冗長轉述**，強制僅呈遞以下極簡卡片：
  ```markdown
  ### 📄 P04 實作計畫定稿已落檔
  - **產出文件**：[P04_implementation_plan.md](__${project://plans/}__/{plan_name}/P04_implementation_plan.md)、[P06_test_plan.md](__${project://plans/}__/{plan_name}/P06_test_plan.md) (Confirmed)
  - **計畫摘要**：[預計變更檔案計 N 個 / 文檔衝擊 N 項 / 核心決策 [P04:DR-XX]]
  - **待確認事項**：請問是否同意實作計畫定稿並授權進入 Phase 5（任務實作）？
  ```
- **立即 End Turn 等待確認**：嚴禁跨階段連續產出。

