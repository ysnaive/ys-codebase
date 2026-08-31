# Phase 2: 架構設計 (P02 Architecture Plan Guide)

本手冊定義 Phase 2 架構設計階段之拓撲設計、時序圖規範與 Test-First 測試初始化要求。

---

## 🎯 1. 核心定位與職責

- **模組邊界與職責劃分**：定義組件職責，確立依賴單向性，杜絕循環依賴。
- **動態流程設計**：以循序圖或資料管線流向圖清晰表達跨物件協同機制。
- **Test-First 測試預先映射**：在架構確立的同時，同步預先規劃測試案例。

---

## 📐 2. 架構設計與圖表規範

- **圖表排版優先級**：
  $$\text{Markdown 表格} \succ \text{垂直 Mermaid (TD / TB)} \succ \text{橫向 Mermaid (LR)} \succ \text{純文字 ASCII 表格}$$
- **Mermaid 防呆**：節點標籤若含括號或特殊符號，強制使用引號包覆（例 `id["Label (Info)"]`）。
- **關鍵決策標註 ([P02:DR-XX])**：記錄選型、狀態空間定義與快取一致性等關鍵決策。

---

## 🧪 3. `P06_test_plan.md` (Draft) 同步初始化鐵律

在 Phase 2 完成時，**必須同步建立並初始化 `P06_test_plan.md`（狀態：`Draft`）**：
- 將 `P01` 定義之 `FR-XX` 映射至 `FT-XX`（功能測試）。
- 將 `P01` 定義之 `EC-XX` 映射至 `ET-XX`（邊界測試）。
- 規劃系統全量回歸測試 `RT-01`。

---

`__@{PHASE02_AGENTS_GUILD}__`

---

## 🛑 4. Phase 2 結束 Checkpoint

- 產出 `P02_architecture_plan.md` 與 `P06_test_plan.md` (Draft)，更新 `changelog.md`。
- 向開發者呈遞架構拓撲圖與測試預排清單。
- 詢問：「請問是否同意架構設計並推進至 Phase 3（API 規格）？」
- **立即 End Turn 等待確認**。

