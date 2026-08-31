# 專案文檔撰寫與作者指引 (Documentation - Author's Guide & Checklist)

本手冊專為文檔作者（撰寫、修改或更新文檔之開發者與 Agent）設計，提供文檔歸屬決策樹、中觀專題手冊定義、三層交付模型、排版規範與自我核對清單。

---

## 🌳 1. 文檔歸屬判定樹 (Decision Tree)

```text
Q1: 這是「歷史探索過程」還是「當前系統事實」？
    ├─ 探索/任務/爭辯 ➔ 【`__${workflow.plans://}__`】(結案後凍結)
    └─ 當前系統事實 ➔ 進入 Q2

Q2: 這是屬於「全域宏觀拓撲」還是「特定分類 (<Category>)」？
    ├─ 全域宏觀 ➔ 【`__${workflow.docs://_project/}__`*.md】
    └─ 特定分類/領域路徑 (<Category>，如 core 或 Render/Layout/FlexEngine) ➔ 進入 Q3

Q3: 這是「單一函式微觀簽名」還是「多實體協同/流向/機制」？
    ├─ 單一函式簽名 ➔ 【程式碼 Docstrings】
    └─ 跨實體協同/資料流/狀態 ➔ 進入 Q4

Q4: 內部機制是否涉及「狀態轉換 / 深度資料管線 / 超過 1 頁」？
    ├─ 否 (極簡介面/單純轉發) ➔ 【`__${workflow.docs://}__/<Category>/README.md`】
    └─ 是 (存在中觀動態機制) ➔ 【`__${workflow.docs://}__/<Category>/[topic].md`】(強制獨立專題手冊！)

Q5: 是否包含「反直覺妥協 / Workaround / 效能硬體限制」？
    └─ 是 ➔ 【`__${workflow.docs://}__/<Category>/DESIGN_NOTES.md`】(強制登記 DN-XX + CAUTION！)
```

---

## 🔬 2. 中觀專題手冊 5 大抽象情境 (Topic Docs Archetypes)

中觀專題手冊（`__${workflow.docs://}__/<Category>/[topic].md`）解決**「Docstrings 放不下，README 裝不下」**的架構斷層，適用於各層級模組與子系統：

| 抽象機制 (Archetype) | 本質特徵與典型範例 | 專題手冊涵蓋重點 |
| :--- | :--- | :--- |
| **① 多物件協同與時序** | 跨類別協同控制流（例：編譯器多階段解算、Hook 調度管線） | 實體職責清冊、垂直 Mermaid 循序圖、例外傳遞路徑 |
| **② 複雜狀態空間與轉換** | $\ge 3$ 個狀態轉移、超時或回滾（例：任務排程器 FSM、連線生命週期） | 狀態轉移矩陣、Mermaid 狀態圖、邊界防禦不變量 |
| **③ 資料處理管線與轉換** | 多階段過濾、加工、物化流程（例：AST 解析管線、自注入編譯流水線） | 管線階段流向圖、各 Stage I/O 契約、極值防禦限制 |
| **④ 協議與通訊契約** | 跨程序 IPC、RPC 或通訊協議（例：自定義 CLI 協議、LSP 封裝） | 封包 Header/Payload Schema、握手心跳、版本相容保證 |
| **⑤ 並發與資源治理** | 多執行緒、資源池化、快取淘汰（例：連線池排隊、快取一致性模型） | 鎖粒度模型、快取策略、資源清理生命週期 |

---

## 🧭 3. 三層文檔交付架構與三維錨點驗收 (Three-Tier Delivery & Anchors)

- **三層文檔交付模型 (Three-Tier Delivery Model)**：
  - **宏觀層 (Macro)**：專案全域發布日誌（`__${workflow.docs://CHANGELOG.md}__`），記錄高階發布與架構演進。
  - **中觀層 (Meso)**：分類/領域手冊 (`__${workflow.docs://}__/<Category>/README.md`)、專題手冊 (`__${workflow.docs://}__/<Category>/[topic].md`) 與設計決策 (`__${workflow.docs://}__/<Category>/DESIGN_NOTES.md`)。
  - **微觀層 (Micro)**：原始碼內部 Public API Docstring、型別契約與複雜演算法 Why-Driven 行內動機註解。
- **Phase 4 預先盤點 (Impact Plan)**：在 `P04` 定稿前，主動盤點宏觀日誌、中觀手冊與微觀契約，輸出文檔衝擊清單。
- **Phase 5 實作落實 (Implementation)**：代碼編寫時將微觀註解與中觀手冊視為一等公民任務同步交付。
- **Phase 7 結案驗收 (Delivery Audit)**：在 `P07_walkthrough.md` 中 1:1 交叉對齊三層文檔清單，任一項未交付則阻斷結案。

---

## 📐 4. 文檔撰寫實作規範

### 4.1 超連結規範：Markdown 可點擊性優先 (Clickability First)
- 文檔正文超連結**一律使用相對於當前檔案的標準相對路徑**（例：`[全域架構](../_project/ARCHITECTURE.md)`、`[核心機制](./pipeline.md)`），確保 IDE 原生點擊跳轉。
- **嚴禁硬編碼主機絕對路徑**：文檔內部嚴禁使用主機或系統絕對路徑（如 `/workspace/...` 或 `C:\...`），確保文檔在任何環境下皆具備可移植性與點擊跳轉有效性。

### 4.2 圖表排版優先級
$$\text{Markdown 表格} \succ \text{垂直排版 Mermaid (TD / TB)} \succ \text{橫向 Mermaid (LR)} \succ \text{純文字 ASCII 表格}$$
> 僅在終端輸出中禁止 Mermaid；在 `.md` 文檔本體中鼓勵使用垂直排版 Mermaid (TD)。

### 4.3 YAML Frontmatter 標準 Schema
```yaml
---
target: "[分類路徑或 Namespace，例：Core/Config 或 Render/Layout/FlexEngine]"
doc_type: "readme | topic | design_notes | changelog | overview"
status: "draft | active | deprecated | archived"
source_paths:
  - "yscb://source/core/yscb_core/config.py"
related_docs:
  - "../_project/STANDARDS.md"
last_updated: "YYYY-MM-DD"
---
```

### 4.4 知識點提煉與 Alert 等級
| Alert 等級 | 使用場景 |
| :--- | :--- |
| `[!CAUTION]` | 可能導致重大 Bug、崩潰、記憶體洩漏、資料損壞或安全漏洞的關鍵坑點 |
| `[!WARNING]` | 常見誤用模式，影響系統穩定度、相容性或效能的注意事項 |
| `[!NOTE]` | 非顯而易見但重要的設計細節（解釋 Why） |
| `[!TIP]` | 推薦的最佳實踐與調用技巧 |

---

## ✅ 5. 文檔更新與添加自我核對清單 (Documentation Checklist)

在每次撰寫、修改或結案提交文檔前，請逐一自檢以下項目：

- [ ] **1. 系統事實確認 (Truth vs. Process)**：內容純粹陳述當前客觀系統架構與程式碼合約，無歷史爭辯或過期過渡期敘述。
- [ ] **2. 抽象維度歸屬 (Dimension Alignment)**：明確符合 7 大維度之一，`<Category>` README 保持概覽與上手，中觀複雜機制已抽出至獨立專題手冊 (`__${workflow.docs://}__/<Category>/[topic].md`)。
- [ ] **3. 可點擊性與路徑有效性 (Clickability)**：所有 Markdown 連結均使用有效相對路徑，無死鏈或硬編碼主機絕對路徑。
- [ ] **4. 防坑邊界留痕 (DN-XX & CAUTION)**：若實作涉及反直覺妥協、硬體/平台繞道或特定常數，已在 `__${workflow.docs://}__/<Category>/DESIGN_NOTES.md` 登記條目並標註 `[!CAUTION]`。
- [ ] **5. 三層文檔交付對齊 (3-Tier Delivery)**：
  - [ ] 宏觀：涉及版本重大變更時已於全域 `__${workflow.docs://CHANGELOG.md}__` 登記。
  - [ ] 中觀：涉及 Public API 或資料流轉向時已同步更新 `__${workflow.docs://}__/<Category>/`。
  - [ ] 微觀：程式碼 Public API 介面註解 (Docstrings) 與型別契約 100% 完整。

---
