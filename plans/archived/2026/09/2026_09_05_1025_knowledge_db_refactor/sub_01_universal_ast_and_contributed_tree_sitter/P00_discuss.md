# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_universal_ast_and_contributed_tree_sitter  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「將當前計畫歸檔，開啟新主計畫: knowledge db refactor，主目標為利用新的 pip 相依性，捨棄原手刻函式，並優化現有功能」
  - 「我考慮將 AST 部分打造成未來 Agents 程式碼搜尋的主軸，甚至是唯一工具，所以想支援所有語法，能設計成通用語義，或是讓類型可擴充嗎? 例如用 contributes 註冊 format / type 等等?」
  - 「沒問題，關於現有 phaser 的遷移，不要直接內建，而是於自身的 contributes 進行自貢獻」
- **核心目標**：
  1. **建立階層化通用語意 AST 抽象模型 (Universal Semantic Schema)**：
     - 將扁平/閹割的 `UnifiedSymbol` + `MemberInfo` 重塑為支援任意巢狀層級（`parent_id`/`children`）的統一符號節點。
     - 引入全限定名稱 (FQN，如 `pkg.module.Class.method`) 與精準作用域鏈 (Scope Path)，根除短名碰撞與圖譜幽靈關聯。
     - 支援結構化簽名與型別標註（`parameters: List[ParamInfo]`, `return_type`）。
     - 內建精煉檢索語意區塊 (`search_payload`)，供後續 BM25 與向量檢索直接秒級消費。
     - 嚴格維持現有 Public API / CLI 屬性與 JSON 序列化向後相容。
  2. **設計 YSCB `contributes.knowledge_db` 外掛註冊協議**：
     - 讓任何生態系模組均可透過 `contribute.json` 宣告式註冊支援之語言 (`languages`)、副檔名 (`extensions`)、S-Expression 查詢檔 (`.scm`) 與領域特化符號類型 (`custom_kinds`)。
     - 支援主流語言（宣告式 Tree-sitter）與特化 DSL（如 SPICE 編程化 Custom Parser）雙軌架構。
  3. **引入 `tree-sitter` 驅動器並徹底汰換手刻正則**：
     - 於 `source/knowledge-db/manifest.json` 宣告 `pip_dependencies` (`tree-sitter` 等相依性)，由 `yscb.venv` 微環境統一治理。
     - 實作宣告式 Tree-sitter 查詢驅動器，以 `.scm` S-Expression 規則取代手刻解析代碼。
     - 優先遷移現行支援之主流語言（Python, C/C++, JS/TS, C# 等）至 Tree-sitter 驅動，並保留特化 DSL 擴充介面。
     - 徹底廢除 `parsers/` 下脆弱的 2,000 行手刻正則狀態機。
  4. **零特權自貢獻 (Zero-Privilege Dogfooding)**：
     - `knowledge-db` 核心不 hardcode 任何語言解析特權；所有內建支援之語言（Python, C/C++, JS/TS, C#, Markdown, SPICE）全數透過 `knowledge-db` 自身的 `contribute.json` 宣告自貢獻，以真實情境驗證擴充架構。
- **邊界排除 (Explicitly Excluded)**：
  - 本階段 (sub_01) 專注於 AST 模型、Tree-sitter 解析器、Contributes 註冊協議與 Parser 汰換；分詞器重塑與向量檢索 (sub_02)、Call Graph 拓撲 (sub_03) 及 Engine 門面解耦 (sub_04) 留待後續子計畫獨立推進。
  - 不更動對外 CLI 命令列參數與既有 JSON 返回欄位契約。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Universal Recursive AST Model**：
  - 廢除 `MemberInfo` 次等地位，所有符號節點（Class, Method, Function, Namespace 等）統一為 `UnifiedSymbol`，具備 `parent_id` 與 `children`。
  - 對外保持相容性屬性（如 `members` 屬性動態適配 `children`），現有上游 Agent 與既有測試無痛向下相容。

- **[P00:DR-02] FQN 與 Search Payload 內聚**：
  - AST 符號生成時即計算 FQN 與 `search_payload`（Name + Signature + Docstring + 核心代碼切片），節省後續檢索時的重複字串拼接與硬碟隨機 I/O。

- **[P00:DR-03] Contributes.knowledge_db 宣告式外掛協議**：
  - 建立通用協議規格，各模組可獨立宣告語言、副檔名與 `.scm` 查詢路徑，實現「零代碼擴充新語言支援」。

- **[P00:DR-04] Tree-sitter 雙軌解析體系**：
  - 軌道 A：主流語言透過 Tree-sitter + S-Expression (`.scm`) 宣告式解析。
  - 軌道 B：特化 DSL 透過宣告 `custom_parser` 實現擴充，確保 100% 語法覆蓋彈性。

- **[P00:DR-05] 淘汰手刻正則狀態機**：
  - 廢除 `parsers/` 中的 regex-based parsers，降低維護成本與邊界缺陷。

- **[P00:DR-06] 內建語言全面採 contributes 自貢獻 (Zero-Privilege Dogfooding)**：
  - 核心引擎不 hardcode 任何內建語言註冊；所有現有語言（Python, C/C++, JS/TS, C#, Markdown, SPICE 等）均於模組自身之 `contributes/knowledge-db.json` 或 `contribute.json` 自行聲明，驗證動態加載管線之完整性。

---

## 3. 開放議題與確認紀錄

- [ ] 確認首發 Tree-sitter 內建支援之語言清單（Python, C/C++, JavaScript, TypeScript, C#, Markdown）。
- [ ] 確認 `tree-sitter` Python 綁定版本與 grammar 套件在 `pip_dependencies` 中的相依宣告清單。
