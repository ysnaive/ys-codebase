# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：AST 模組正交化重構與全倉符號 SSOT 架構深度調研  
> 建立日期：2026-11-07  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模型：Gemini 3.1 Pro  
> 計畫類型：Umbrella  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：在規劃 `knowledge-db`（KDB）專精於「萬物皆符號化 SSOT」之多視角文檔生成管線（對外 SDK 文檔、對內超集技術文檔、下游教學文檔）前，需先重新審視 `module:ast` 是否如同重構前的 `file-space` 模組一般，僅包含早期從 KDB 抽離出來的檢索切片設計而缺乏通用性與正交性。將 AST 架構拆解為三大核心議題逐項調研：
  1. **第一大項（R01 已完成）**：產出的原子符號定義、Tree-sitter 解析流程對齊、官方 `queries/tags.scm` 標準直連相容，以及「內核原始碼（Kernel）」與「`contributes` 宣告式注入設定 + 符號處理器（Symbol Processor）」之職責邊界。
  2. **第二大項（R02 已完成）**：單檔語法規則與符號樹（File AST）如何透過跨檔名稱解析與連結器（Scope-Import Linker / Deterministic Resolver）組裝為全倉語意圖譜（Workspace Symbol Graph）。
  3. **第三大項（R03 已完成）**：AST 全倉圖譜與 `core.space` 之正交協同、快取持久化、無損源碼部位切片原語（`slice_part`）與提供給下游（KDB 文檔管線、Compiler/Checker）之通用圖譜查詢介面。
- **核心目標**：釐清 `module:ast` 的正交分層架構，消除現有 KDB 檢索導向的耦合病症，確立可支撐「全倉一切皆符號 SSOT」與跨語言/跨領域擴充的底層基石。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 盤點既有 `ys_codebase/source/ast/ast_engine/`（`schema.py`、`engine.py`、`bundler.py`、`linker.py`、`resolver.py`、`parsers/registry.py`、`parsers/treesitter.py`、`parsers/markdown.py`、`dialects/`）與 `docs/ast/DESIGN_NOTES.md`。
  - 直接復用 `2026_11_06_1020_core_file_space_architecture` 之 `core.space` 空間尋址與 `match_path` 原語，不在 `ast` 中重複定義 `include`/`exclude` 過濾器。
  - 原生相容 Tree-sitter 官方與 GitHub Code Navigation 之 `queries/tags.scm` 標準規範（`@definition.<kind>`、`@reference.<kind>`、`@name`、`@doc`）。
- **邊界排除 (Explicitly Excluded)**：
  - 本調研計畫階段聚焦架構剖析與三份專題調研報告（`R01`、`R02`、`R03`）收斂，不直接修改 `ys_codebase/source/ast/` 業務源碼。
- **架構影響範圍**：
  - `ys_codebase/source/ast/`（資料結構 `schema.py`、Tree-sitter 通用驅動器 `parsers/treesitter.py`、語言與規則註冊表 `parsers/registry.py`、跨檔連結器 `linker.py`、解析器 `resolver.py`、引擎 `engine.py` 與 `contributes/_format.json` 契約）。
  - 下游消費模組：`ys_codebase/source/knowledge-db/`（符號圖譜消費與文檔管線）、`ys_codebase/source/core/`（`core.space` 協同與框架級領域符號注入）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] AST 三大核心議題分階段調研路線**：
  - 確立從第一性原理對齊 AST 的三個組成階段：① **原子符號定義與提取契約（R01）** $\to$ ② **跨檔語意連結與全倉圖譜組裝（R02）** $\to$ ③ **圖譜操作原語、`core.space` 協同與下游消費管線（R03）**。
- **[P00:DR-02] 第一大項（原子定義與內核 vs. `contributes` 邊界）定案結論（詳見 `R01`）**：
  - **單一遞迴同構 `SymbolNode` + 多部位無損座標 `parts: Dict[str, Span]` + 通用有向邊 `RelationEdge` + 來源追蹤 `provenance`**。
  - **全平權一等公民與交換律合流（Commutative Merge）**：`SymbolNode.kinds: FrozenSet[str]` 無主從之分；多 `.scm` 以 `@name` 物理座標為錨點執行交換律聯集，徹底免疫 `core.contributes` 底層合併順序。
  - **原生相容 Tree-sitter 官方 `queries/tags.scm` 標準**，並支援**於規則註冊時透過 `spaces?: list[str]` 直接引用 `core.space` 定義（預設不給即 `project://` 全掃描，不在 `ast.json` 自搞 `include`/`exclude`）**。
- **[P00:DR-03] 第二大項（跨檔語意連結與全倉圖譜組裝）定案結論（詳見 `R02`）**：
  - **四階段依序連結流水線（4-Pass Linking Pipeline）**：Pass 1 全域索引與跨檔同體折疊 $\to$ Pass 2 匯入邊解析與 `FileImportTable` 建構 $\to$ Pass 3 型別繼承與實作 DAG 建構 $\to$ Pass 4 呼叫與文檔引用四階確定性消歧。
  - **廢除啟發式模糊打分，確立四種確定性消歧狀態**：`resolved`、`overload_group`、`ambiguous`（保留全數候選 ID 元組 `resolved_target_ids`）、`external`。
- **[P00:DR-04] 第三大項（圖譜原語、單檔子圖增量快取與下游消費契約）定案結論（詳見 `R03`）**：
  - **單次掃描不可變 `FileSymbolGraph` 快取**：消除同檔三次重複解析與 `_own_members` 髒狀態還原。
  - **L0 無狀態單檔原語（`parse_file`、`outline`、`slice_part`）+ L1 全倉圖譜查詢原語（`resolve`、`select_nodes`、`traverse_edges`）**：直接支撐 KDB 對外 SDK、對內超集技術文檔與教學文檔/腐敗檢測三大管線。

---

## 3. 開放議題與確認紀錄

- **[已完成] 議題 1**：第一大項已定案並收斂於 `R01_atomic_symbol_definition_and_contributes_boundary.md`（狀態 `Concluded`）。
- **[已完成] 議題 2**：第二大項已定案並收斂於 `R02_cross_file_linking_and_workspace_graph.md`（狀態 `Concluded`）。
- **[已完成] 議題 3**：第三大項已定案並收斂於 `R03_graph_primitives_incremental_cache_and_kdb_contract.md`（狀態 `Concluded`）。
