# 專案知識庫架構與維護規範 (Documentation Standards)

本文件定義專案知識庫（`docs://`）的抽象知識維度、判定決策樹、中觀專題手冊 (Topic Docs) 概念與全生命週期 1:1 交付對齊機制。

---

## 🎯 核心定位：兩套系統的職責劃分

| 系統 | 語意定位 | 職責與生命週期 | 內容性質 |
| :--- | :--- | :--- | :--- |
| **開發過程紀錄** | `plans://` / `archive://` | 記錄探索、爭辯、任務與決策過程；結案後永久凍結 | 過程導向、DR 決策、任務清單 |
| **系統知識庫** | `docs://` | 記錄現況事實、架構拓撲與防坑邊界；隨代碼持續演進 | 狀態導向、現狀事實、邊界合約 |

> [!IMPORTANT]
> **知識庫只陳述客觀現狀與坑點，不記錄歷史爭辯過程。** 爭辯與替代方案留於 `plans://`，`docs://` 專注於回答「現在是什麼架構」與「邊界條件/不變量」。

---

## 🌐 1. 軟體工程 7 大抽象知識維度

| 維度 (Dimension) | 核心範疇 | 剛性宿主 (Carrier) | 說明 |
| :--- | :--- | :--- | :--- |
| **① 領域概念模型** | 領域通用語言 (Ubiquitous Language)、實體與名詞定義 | `docs/_project/ARCHITECTURE.md`<br>`docs/<Module>/README.md` | 全局認知基礎 |
| **② 靜態邊界與拓撲** | 模組職責邊界（做什麼、不做什麼）、依賴方向 | `docs/_project/ARCHITECTURE.md`<br>`docs/<Module>/README.md` | 防止職責蔓延與循環依賴 |
| **③ 中觀動態機制** | 跨類別協同、資料流、狀態機 (FSM)、協議與生命週期 | `docs/<Module>/[topic].md`<br>*(獨立專題手冊)* | **核心中觀架構，嚴禁塞入註解或撐爆 README** |
| **④ 介面合約與承諾** | 前置/後置條件、錯誤型態、輸入輸出 Schema | 程式碼 Docstrings / Public Headers | 呼叫方與實作方之剛性約定 |
| **⑤ 工程妥協與防坑** | 為效能/平台限制而採取的反直覺設計 (Non-obvious) | `docs/<Module>/DESIGN_NOTES.md`<br>*(DN-XX + `[!CAUTION]`)* | 防止後人誤改有意為之的設計 |
| **⑥ 人因操作引導** | 快速上手、配置矩陣、典型範例 (Cookbook)、故障排查 | `docs/<Module>/README.md`<br>`docs/_project/CLI_SPECIFICATION.md` | 面向使用者之操作指南 |
| **⑦ 架構演進歷史** | 重大架構重構歷史（痛點 ➔ 改變 ➔ 參照 Plan） | `docs/<Module>/CHANGELOG.md` | 僅記錄架構級重大變更 |

---

## 🌳 2. 文檔歸屬判定樹 (Decision Tree)

```text
Q1: 這是「歷史探索過程」還是「當前系統事實」？
    ├─ 探索/任務/爭辯 ➔ 【workflow.plans://】(結案後凍結)
    └─ 當前系統事實 ➔ 進入 Q2

Q2: 這是屬於「全域宏觀拓撲」還是「特定模組內部」？
    ├─ 全域宏觀 ➔ 【workflow.docs://_project/*.md】
    └─ 特定模組 ➔ 進入 Q3

Q3: 這是「單一函式微觀簽名」還是「多實體協同/流向/機制」？
    ├─ 單一函式簽名 ➔ 【程式碼 Docstrings】
    └─ 跨實體協同/資料流/狀態 ➔ 進入 Q4

Q4: 內部機制是否涉及「狀態轉換 / 深度資料管線 / 超過 1 頁」？
    ├─ 否 (極簡介面/單純轉發) ➔ 【docs/<Module>/README.md】
    └─ 是 (存在中觀動態機制) ➔ 【docs/<Module>/[topic].md】(強制獨立專題手冊！)

Q5: 是否包含「反直覺妥協 / Workaround / 效能硬體限制」？
    └─ 是 ➔ 【docs/<Module>/DESIGN_NOTES.md】(強制登記 DN-XX + CAUTION！)
```

---

## 🔬 3. 中觀專題手冊 5 大抽象情境 (Topic Docs)

中觀專題手冊（`docs/<Module>/[topic].md`）解決**「Docstrings 放不下，README 裝不下」**的架構斷層：

| 抽象機制 (Archetype) | 本質特徵與典型範例 | 專題手冊涵蓋重點 |
| :--- | :--- | :--- |
| **① 多物件協同與時序** | 跨類別協同控制流（例：編譯器多階段解算、Hook 調度管線） | 實體職責清冊、垂直 Mermaid 循序圖、例外傳遞路徑 |
| **② 複雜狀態空間與轉換** | $\ge 3$ 個狀態轉移、超時或回滾（例：任務排程器 FSM、連線生命週期） | 狀態轉移矩陣、Mermaid 狀態圖、邊界防禦不變量 |
| **③ 資料處理管線與轉換** | 多階段過濾、加工、物化流程（例：AST 解析管線、自注入編譯流水線） | 管線階段流向圖、各 Stage I/O 契約、極值防禦限制 |
| **④ 協議與通訊契約** | 跨程序 IPC、RPC 或通訊協議（例：自定義 CLI 協議、LSP 封裝） | 封包 Header/Payload Schema、握手心跳、版本相容保證 |
| **⑤ 並發與資源治理** | 多執行緒、資源池化、快取淘汰（例：連線池排隊、快取一致性模型） | 鎖粒度模型、快取策略、資源清理生命週期 |

---

## 🧭 4. 三維錨點投影與交付驗收

- **Phase 4 預先盤點 (Impact Plan)**：在 `P04` 定稿前，依據 P03 (API)、P05 (Tasks)、P06 (Tests) 投影並輸出 `docs/` 需更新清單。
- **Phase 7 結案驗收 (Delivery Audit)**：在 `P07_walkthrough.md` 中 1:1 交叉對齊盤點清單，任一項未交付則阻斷結案。

---

## 📐 5. 文檔撰寫實作規範

### 5.1 超連結規範：Markdown 可點擊性優先 (Clickability First)
- 文檔正文超連結**一律使用相對於當前檔案的標準相對路徑**（例：`[全域架構](../_project/ARCHITECTURE.md)`），確保 IDE 原生點擊跳轉。
- **指令與引導型連結顯示文字規範**：引導讀取實體檔案時，源碼模板顯示文字應使用專案相對佔位符（例：[`__${module://agents-workflow/assets/standards/AgentsCliGuild.md}__`](`__#{module://agents-workflow/assets/standards/AgentsCliGuild.md}__`)），編譯時依 Target 部署地圖自動解算，嚴禁硬編碼特定目錄。

### 5.2 圖表排版優先級
$$\text{Markdown 表格} \succ \text{垂直排版 Mermaid (TD / TB)} \succ \text{橫向 Mermaid (LR)} \succ \text{純文字 ASCII 表格}$$
> 僅在終端輸出中禁止 Mermaid；在 `.md` 文檔本體中鼓勵使用垂直排版 Mermaid (TD)。

### 5.3 YAML Frontmatter 標準 Schema
```yaml
---
target: "[模組名稱或 Namespace，例：Core/Config]"
doc_type: "readme | topic | design_notes | changelog | overview"
status: "draft | active | deprecated | archived"
source_paths:
  - "yscb://source/core/yscb_core/config.py"
related_docs:
  - "../_project/STANDARDS.md"
last_updated: "YYYY-MM-DD"
---
```

---

## 6. 知識點提煉與 Alert 等級

| Alert 等級 | 使用場景 |
| :--- | :--- |
| `[!CAUTION]` | 可能導致重大 Bug、崩潰、記憶體洩漏、資料損壞或安全漏洞的關鍵坑點 |
| `[!WARNING]` | 常見誤用模式，影響系統穩定度、相容性或效能的注意事項 |
| `[!NOTE]` | 非顯而易見但重要的設計細節（解釋 Why） |
| `[!TIP]` | 推薦的最佳實踐與調用技巧 |

---

`__@{WORKFLOW_DOCS_STANDARDS}__`
