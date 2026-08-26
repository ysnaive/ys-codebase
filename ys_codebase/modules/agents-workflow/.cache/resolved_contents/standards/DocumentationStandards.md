# 專案知識庫架構與維護規範 (Documentation Standards)

本文件定義專案知識庫（`docs://`）的抽象知識維度、判定決策樹、中觀專題手冊 (Topic Docs) 概念與全生命週期 1:1 交付對齊機制。

---

## 🎯 核心定位：兩套系統的職責劃分

| 系統 | 語意定位 | 職責 | 內容性質與生命週期 |
| :--- | :--- | :--- | :--- |
| **開發過程紀錄** | `plans://` / `archive://` | 記錄「我們當時是怎麼探索、爭辯與實作出來的」 | 過程導向、DR 決策、任務清單；結案後永久凍結 |
| **系統知識庫** | `docs://` | 記錄「這個系統現在長什麼樣子、有什麼邊界與坑點」 | 狀態導向、現狀事實、邊界合約；隨程式碼演進持續更新 |

> [!IMPORTANT]
> **知識庫只陳述客觀現狀與坑點，不記錄歷史爭辯過程。**  
> 「為什麼這樣設計」的辯論與替代方案留在 `plans://` 的 Decision Records。  
> `docs://` 只回答「現在是什麼架構與機制」以及「你需要知道的邊界條件與不變量」。

---

## 🌐 1. 軟體工程 7 大抽象知識維度

任何軟體系統的知識皆可嚴格投射在以下 7 個互相正交的維度中：

| 維度 (Dimension) | 核心概念與範疇 | 剛性宿主 (Carrier) | 說明 |
| :--- | :--- | :--- | :--- |
| **① 領域概念模型 (Domain Model)** | 領域通用語言 (Ubiquitous Language)、核心實體與名詞定義 | `docs/_project/ARCHITECTURE.md`<br>`docs/<Module>/README.md` | 跨檔案/模組的全局認知基礎 |
| **② 靜態邊界與拓撲 (Topology)** | 模組職責邊界（做什麼、絕不做什麼）、依賴方向 | `docs/_project/ARCHITECTURE.md`<br>`docs/<Module>/README.md` | 防止職責蔓延與循環依賴 |
| **③ 中觀動態機制 (Dynamic Mechanics)** | 跨類別協同之資料流、控制流、狀態空間 (FSM)、協議與生命週期 | `docs/<Module>/[topic].md`<br>*(獨立專題手冊)* | **核心中觀架構，嚴禁塞在註解或撐爆 README** |
| **④ 介面合約與承諾 (Contracts)** | 前置/後置條件、執行緒安全保證、錯誤型態、輸入輸出 Schema | 程式碼 Docstrings / Public Headers / Topic 規格書 | 呼叫方與實作方之剛性約定 |
| **⑤ 工程妥協與防坑 (Compromises)** | 為了效能/硬體/平台限制而採取的反直覺設計 (Non-obvious) | `docs/<Module>/DESIGN_NOTES.md`<br>*(DN-XX + `[!CAUTION]`)* | 防止後人不知情「修正」有意為之的設計 |
| **⑥ 人因操作引導 (Ergonomics)** | 快速上手、配置矩陣、典型使用案例 (Cookbook)、故障排查 | `docs/<Module>/README.md`<br>`docs/_project/CLI_SPECIFICATION.md` | 面向使用者與開發者的操作指南 |
| **⑦ 架構演進歷史 (Evolution)** | 重大架構重構歷史（舊架構痛點 ➔ 新架構改變 ➔ 參照 Plan） | `docs/<Module>/CHANGELOG.md` | 僅記錄架構級變更，不記日常功能碎屑 |

---

## 🌳 2. 文檔歸屬第一性原理判定樹 (Decision Tree)

當面對任何程式碼、機制或設計時，依序透過以下決策樹判定歸屬：

```text
Q1: 這是「歷史探索過程」還是「當前系統事實」？
    ├─ 探索/爭辯/任務過程 ➔ 【plans://】(Phase 結案後封存)
    └─ 當前系統事實 ➔ 進入 Q2

Q2: 這是屬於「全域宏觀拓撲/規範」還是「特定模組內部」？
    ├─ 全域宏觀 ➔ 【docs/_project/*.md】
    └─ 特定模組 ➔ 進入 Q3

Q3: 這是「單一函式的微觀簽名」還是「多實體協同/機制/流向」？
    ├─ 單一函式簽名/單行微觀邏輯 ➔ 【程式碼 Docstrings / 行內註解】
    └─ 跨實體協同/流向/狀態/協議 ➔ 進入 Q4

Q4: 這個內部機制的描述是否需要「超過 1 頁 / 涉及狀態轉換 / 資料管線」？
    ├─ 否 (極簡介面/單純轉發) ➔ 【docs/<Module>/README.md】
    └─ 是 (存在中觀動態機制) ➔ 【docs/<Module>/[topic].md】(強制獨立專題！)

Q5: 這段實作是否包含「反直覺妥協 / 繞道 Workaround / 效能硬體限制」？
    └─ 是 ➔ 【docs/<Module>/DESIGN_NOTES.md】(強制登記 DN-XX + CAUTION！)
```

---

## 🔬 3. 中觀專題手冊核心概念與典型範例 (Topic Docs Archetypes)

### 3.1 核心理念與定位
中觀專題手冊 (`docs/<Module>/[topic].md`) 旨在解決**「微觀 Docstrings 放不下，宏觀 README 裝不下」**的架構知識斷層。當某個機制的內部複雜度已涉及多物件協作、深度資料流或非直觀狀態流轉時，強制建立獨立專題手冊，維持模組概覽 (`README.md`) 的輕量與高階聚焦。

### 3.2 典型抽象情境與啟發性範例 (Illustrative Examples)

| 抽象機制概念 (Archetype) | 本質特徵 | 啟發性應用範例 (Examples) | 專題手冊建議涵蓋重點 |
| :--- | :--- | :--- | :--- |
| **① 多物件協同與時序協調<br/>(Multi-Entity Orchestration)** | 跨多個類別/實體協同完成之複雜控制流與呼叫鏈。 | • 編譯器多階段解算狀態機<br>• 外掛生命週期 Hook 註冊與調度<br>• 使用者認證與權限校驗流程 | • 協同實體職責清冊<br>• 垂直 Mermaid 循序圖 (Sequence Diagram)<br>• 失敗與例外傳遞路徑 |
| **② 複雜狀態空間與轉換<br/>(State Space & Transitions)** | 包含 3 個以上非顯而易見的狀態轉移、超時或回滾防禦。 | • 任務排程器狀態機 (Pending/Running/Retry)<br>• 連線生命週期與優雅停機 (Graceful Shutdown) | • 狀態轉移矩陣 (State Matrix)<br>• 狀態圖 (Mermaid stateDiagram)<br>• 邊界防禦與不變量 (Invariants) |
| **③ 資料處理管線與轉換<br/>(Data Pipeline & Transforms)** | 多階段過濾、加工、轉換、物化或原子寫入的流水線。 | • AST 語法樹解析與代碼生成管線<br>• 檔案格式解析與自注入物化流程<br>• 批次事件流過濾與聚合 | • 管線階段流向圖 (Pipeline Flow)<br>• 各 Stage 輸入輸出合約<br>• 記憶體/效能極值防禦與限制 |
| **④ 協議與通訊契約<br/>(Protocols & Wire/IPC Contracts)** | 自定義資料封裝、跨處理程序 IPC、RPC 或文字通訊協議。 | • 自定義 CLI 參數與通訊序列化協議<br>• LSP 語言伺服器協議封裝<br>• 跨進程記憶體映射通訊協議 | • 封包/訊息 Header 與 Payload Schema<br>• 握手 (Handshake) 與心跳機制<br>• 版本向前/向後相容性保證 |
| **⑤ 並發、非同步與資源治理<br/>(Concurrency & Resource Governance)** | 涉及多執行緒/非同步協同、資源池化、快取淘汰與鎖模型。 | • 快取淘汰策略與執行緒安全保證<br>• 連線池/Worker 池排隊與復用機制<br>• 非同步事件緩衝區與背壓 (Backpressure) | • 鎖粒度與競爭防範模型<br>• 快取一致性保證<br>• 資源上限、洩漏防範與清理生命週期 |

---

## 🧭 4. P03 / P05 / P06 三維錨點投影與驗收機制

### 4.1 Phase 4 預先盤點 (Documentation Impact Plan)
在 `P04_implementation_plan.md` 定稿前，依據 P03 (API)、P05 (Tasks)、P06 (Tests) 投影並輸出盤點清單：

| 判定依據 (P03/P05/P06) | 知識維度 | 預計更新/新建的文檔路徑 | 具體涵蓋內容 |
| :--- | :--- | :--- | :--- |
| `P03: API 變更` | 維度 2 (邊界與使用) | `docs/<Module>/README.md` | 補齊公開介面簽名與快速上手範例 |
| `P05: Task X (管線實作)` | 維度 3 (中觀機制) | `docs/<Module>/pipeline_flow.md` | [NEW] 垂直 TD 流程圖與各 Stage 規格 |
| `P06: ST-01~03 (狀態測試)` | 維度 3 (中觀機制) | `docs/<Module>/lifecycle_fsm.md` | [NEW] 狀態轉移矩陣與邊界例外處理 |
| `P05: Task Y (Workaround)` | 維度 5 (工程妥協) | `docs/<Module>/DESIGN_NOTES.md` | 登記 `DN-XX` 與 `[!CAUTION]` 坑點防護 |

### 4.2 Phase 7 結案 1:1 交叉對齊驗收 (Documentation Delivery Audit)
在 `P07_walkthrough.md` 中，逐項比對實際產出物，任一項未落實則阻斷結案。

---

## 📐 5. 文檔撰寫實作規範

### 5.1 超連結規範：Markdown 可點擊性優先 (Clickability First)
- 在 `.md` 文檔正文中的超連結，**一律使用相對於當前檔案的標準相對路徑**（例：`[全域架構](../_project/ARCHITECTURE.md)`、`[專題手冊](./protocol_spec.md)`），確保 IDE 與 GitHub 原生點擊跳轉。
- 語意 URI（`docs://`、`plans://`）用於文字說明、Frontmatter `source_paths` 與 CLI 調度。

### 5.2 圖表排版優先級 (Priority Chain)
文檔檔案（`.md`）內部之圖表選型順序如下：
$$\text{Markdown 表格} \succ \text{垂直排版 Mermaid (TD / TB)} \succ \text{橫向 Mermaid (LR)} \succ \text{純文字 ASCII 表格}$$
> **注意**：僅在 **對話視窗與 CLI 終端輸出** 中禁止 Mermaid（因終端不支援渲染），在 `.md` 文檔本體中鼓勵使用垂直排版 Mermaid (TD)。

### 5.3 YAML Frontmatter 標準 Schema
所有 `docs/` 下的 Markdown 文件必須包含以下 Frontmatter：

```yaml
---
# ── 識別資訊 ─────────────────────────────────────────
target: "[模組名稱或 Namespace，例：Core/Config]"
doc_type: "readme | topic | design_notes | changelog | overview"

# ── 狀態 ─────────────────────────────────────────────
status: "draft | active | deprecated | archived"

# ── 來源連結 ──────────────────────────────────────────
source_paths:
  - "yscb://source/core/yscb_core/config.py"
related_docs:
  - "../_project/STANDARDS.md"

# ── 維護資訊 ──────────────────────────────────────────
last_updated: "YYYY-MM-DD"
---
```

---

## 6. 知識點提煉與 Alert 等級

| Alert 等級 | 使用場景 |
| :--- | :--- |
| `[!CAUTION]` | 可能導致重大 Bug、系統崩潰、記憶體洩漏、資料損壞或安全漏洞的關鍵坑點 |
| `[!WARNING]` | 常見誤用模式，影響系統穩定度、相容性或效能的注意事項 |
| `[!NOTE]` | 非顯而易見但重要的設計細節（解釋 Why） |
| `[!TIP]` | 推薦的最佳實踐與調用技巧 |

---

