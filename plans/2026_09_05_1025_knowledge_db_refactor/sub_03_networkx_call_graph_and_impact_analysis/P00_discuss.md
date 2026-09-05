# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_03_networkx_call_graph_and_impact_analysis  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 承接 Umbrella 主計畫 `2026_09_05_1025_knowledge_db_refactor` 里程碑 3。
  - 「基於 NetworkX 的符號拓撲分析：引入 networkx；利用 FQN 與 Import 作用域重構 linker.py（消除幽靈關聯）；重構 graph.py 提升 callers/callees 與多階 impact分析精度。」
  - 開發者確認啟動 `sub_03` 之需求討論與執行。
- **核心目標**：
  1. **工業級圖論引擎引入 (`networkx`)**：引入 `networkx` 替換現有手刻整數池、雙向稀疏鄰接表與手刻 BFS，提供高維度有向圖 (`DiGraph`) 拓撲建模。
  2. **消除幽靈關聯 (Ghost Edges Elimination)**：利用 Universal AST 所產出的標準階層 FQN、模組命名空間與檔頭 Import 映射，重構 `TopologyLinker` 的消歧策略，杜絕跨檔案同名函式/方法的誤連。
  3. **高精度多階影響面分析 (`query_impact`)**：基於 NetworkX 的有向圖前驅走訪與路徑演算法，精確產出多階影響層級與完整調用鏈路，並天然免疫圖中循環依賴 (Cyclic Dependencies)。
  4. **多語言調用拓撲協議 (Language Topology Protocol)**：以宣告式/外掛 Protocol 形式擴容支援任何程式語言（如 Python, JS/TS, C/C++, C# 等），使各語言能透過統一協議提供 AST 調用點 (`SymbolCallSite`) 與 Import 映射。
  5. **全方位增強型 AST 符號定位語法 (Comprehensive Symbol Selector)**：升級 CLI 與查詢介面，調用者除單純 member 名稱外，可提供全方位結構化資訊精確定位：
     - **類型前綴 (Kind Prefix)**：`class foo`, `struct foo`, `interface foo`, `enum foo`, `fn foo` / `def foo` / `func foo`, `type foo`, `const foo`, `var foo`, `macro foo` 等。
     - **範疇層次 (Hierarchical Scope / FQN)**：`foo.a`（在 `foo` 範疇/類別/模組中名為 `a` 的節點）、`pkg.foo.a`。
     - **可調用尾碼 (Callable Suffix)**：`foo.a()` 或 `a()`（限定為可調用之函式或方法）。
     - **複合組合 (Combined Syntax)**：例如 `class Foo.bar()`, `struct Point.x`, `interface IService.start()`。
  6. **高精度多階影響面分析 (`query_impact`)**：基於 NetworkX 的有向圖前驅走訪與路徑演算法，精確產出多階影響層級與完整調用鏈路，並天然免疫圖中循環依賴 (Cyclic Dependencies)。
  7. **對外契約 100% 相容**：嚴格維持 `CallGraphIndex` 與 `TopologyLinker` 的 Public API 門面契約（`add_edge`, `get_callers`, `get_callees`, `get_call_sites`, `query_impact`, `patch_incremental`, `save_binary`, `load_binary`）以及 CLI 輸出契約（`knowledge-db callers/callees/impact`），既有調用端與測試案例零破壞。
  8. **平滑降級與微環境適配**：將 `networkx` 列入 `pip_dependencies`（`>=3.0`），並在程式碼層面提供乾淨的模組匯入防護，確保微環境無障礙運行。
- **邊界排除 (Explicitly Excluded)**：
  - 不拆解 `engine.py` 之流水線架構（保留至 sub_04 集中處理）。
  - 不更動 Tree-sitter S-Expression AST 解析核心與查詢規則（sub_01 已定稿）。
  - 不更動 Tokenizer 與 BM25 + 向量複合檢索管線（sub_02 已定稿）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 圖論引擎選型 (NetworkX)**：選用 `networkx`（純 Python、Zero-C 擴展、輕量穩定），以 `networkx.DiGraph` 作為核心拓撲資料結構，圖節點記錄符號 ID 與元數據，有向邊記錄調用關係與 `SymbolCallSite` 列表。
- **[P00:DR-02] 外部相依宣告與相容性方針**：在 `source/knowledge-db/manifest.json` 之 `pip_dependencies` 宣告 `"networkx": ">=3.0"`；在 `graph.py` 中進行安全載入，確保微環境構建與沙盒測試自動物化依賴。
- **[P00:DR-03] 基於 FQN 與 Import 作用域之消歧鏈接重構**：
  - 充分利用 Universal AST 階層模型中的 `fqn` 與 `parent_id`。
  - 重構 Tier 1~4 消歧梯隊：Tier 1 (類別/檔內作用域)、Tier 2 (精確 Import 映射與相對匯入解析)、Tier 3 (同語意空間與同模組路徑優先)、Tier 4 (全庫消歧施加嚴格上下文模組相似度門檻)。
  - 針對無法確認歸屬的同名裸調用，嚴格標記為未鏈接邊，杜絕幽靈關聯。
- **[P00:DR-04] 圖持久化與快取相容性**：
  - 延續 Protocol 5 Pickle + Gzip 二進位壓縮格式 (`unified.graph.bin.gz`)，內部儲存 NetworkX 圖結構與屬性。
  - 維持 `to_dict` / `from_dict` 格式相容，確保現有單元測試與增量快取機制無縫運作。
- **[P00:DR-05] 影響面分析演算法升級**：
  - `query_impact` 改由 NetworkX 有向圖之逆向走訪（predecessors / reverse view），精準分層（Layer 1..N）並還原調用鏈路，天然規避遞迴循環。
- **[P00:DR-06] 多語言調用拓撲協議 (Topology Protocol)**：制定抽象 `LanguageTopologyProtocol`，定義 `extract_call_sites(ast, source_bytes)` 與 `extract_imports(ast, source_bytes)` 介面，各語言（Python、JS/TS、C/C++、C# 等）皆可實現適配器外掛接入。
- **[P00:DR-07] 全方位 AST 符號結構化選擇器語法 (Comprehensive Symbol Selector)**：設計完備微型語法解析器，支援類型前綴（`class`, `struct`, `interface`, `enum`, `fn`/`def`/`func`, `type`, `const`, `var`, `macro`）、階層範疇（`foo.a`）、可調用標記（`()`）與任意正交組合，一次性完備 CLI 精確定位契約。

---

## 3. 開放議題與確認紀錄

- [x] **NetworkX 依賴形式**：確認作為 `knowledge-db` 之標準 `pip_dependencies` 宣告，由 YSCB 微環境工具鏈自動物化。
- [x] **對外 API 門面契約**：確認 `CallGraphIndex` 門面方法簽名維持不變，內部實作全面改用 NetworkX。
- [x] **消除幽靈關聯策略**：確認提高 Tier 4 消歧門檻，寧可不鏈接也不建立錯誤跨模組幽靈邊。
- [x] **多語言與符號選擇器擴容**：確認以 Protocol 協議解耦跨語言萃取，並在 CLI 深度整合階層符號選擇器語法。
