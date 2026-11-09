# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：AST 四階段確定性跨檔連結流水線 (4-Pass Linker)、四階作用域查找與全倉圖譜組裝  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_07_1548_ast_architecture_research  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：依主計畫 `R02_cross_file_linking_and_workspace_graph.md` 定案結論，啟動第二個子計畫 `sub_02_deterministic_linker_and_workspace_graph`，落地 `WorkspaceSymbolGraph` 與四階段確定性跨檔連結流水線（Pass 1 全域符號索引與跨檔同體折疊 $\to$ Pass 2 `FileImportTable` 匯入邊解析 $\to$ Pass 3 型別繼承與實作 DAG 建構 $\to$ Pass 4 四階確定性作用域查找消歧）；廢除啟發式模糊打分，確立 `resolved` / `overload_group` / `ambiguous` / `external` 四種確定性完成態與平權 `ModulePathResolver` / `receiver_aliases` / `EdgeRefiner` 注入契約。
- **核心目標**：
  1. 在 `ast_engine/schema.py` 擴充定義不可變之 `FileImportBinding`、`FileImportTable` 與全倉語意圖譜容器 `WorkspaceSymbolGraph`（全數 `@dataclass(frozen=True)`），支援從多份 `FileSymbolGraph` 組裝全倉節點、已解析邊（含正向 `outgoing_edges_by_source` 與反向 `incoming_edges_by_target` 索引）、跨檔同體群組與無環型別繼承 DAG。
  2. 擴充 `ys_codebase/source/ast/contributes/_format.json`、`LanguageConfig` 與 `ParserRegistry` / `DialectAdapter`，支援平權宣告式注入 `receiver_aliases`（`self_aliases` 與 `super_aliases`）、`symbol_folding`（跨檔同體宣告折疊規則，如 `partial` 與 `.h`/`.cpp` 配對）、`module_resolver: str?`（`ModulePathResolver` 入口）與 `edge_refiners: list[str]?`（`EdgeRefiner` 入口清單）。
  3. 實作內核 `WorkspaceGraphLinker` 四階段依序連結流水線（4-Pass Deterministic Linking Pipeline）：
     - **Pass 1（Global Indexing & Symbol Folding）**：建立全倉 `SymbolNode` 索引表，並依同體折疊規則建立對稱 `merges_with` / `declares` 雙向關係邊（絕不竄改單檔 `FileSymbolGraph` 內部節點）。
     - **Pass 2（Import Edge Resolution & `FileImportTable` Construction）**：搭配各語言 `ModulePathResolver` 解析 `edge_kind="imports"`（含相對路徑匯入、別名匯入、萬用匯入 `*` 與 `__all__` / `export` 重導出），產出每個檔案確定性的 `FileImportTable` 並標記 `resolved` 或 `external`。
     - **Pass 3（Inheritance & Type Graph Construction）**：利用 Pass 2 的 `FileImportTable` 與詞法作用域精確解析 `edge_kind in ("inherits", "implements")` 邊，綁定至目標 `SymbolNode.id`（徹底根除 `short_name` 跨模組同名基底誤連），建立無環型別繼承 DAG（`type_bases_by_id` / `type_derived_by_id`）與欄位型別映射（`field_types_by_class_id`）。
     - **Pass 4（4-Tier Deterministic Scope Cascade & Edge Refinement）**：嚴格依序透過 ① **詞法封閉作用域（Lexical Enclosing Scope）** $\to$ ② **所屬型別與 Pass 3 繼承鏈 DAG（Class & Base DAG，含 `receiver_aliases` 與欄位型別派發）** $\to$ ③ **Pass 2 檔案匯入綁定表（`FileImportTable`）** $\to$ ④ **同模組/全倉唯一 FQN 精確匹配** 解析所有 `calls`、`references`、`documents` 邊；隨後執行選填之平權 `EdgeRefiner`，寫入最終 `resolution_status`（`resolved` / `overload_group` / `ambiguous` / `external` / `unresolved`）、`resolved_target_ids` 與 `ProvenanceStep`，**100% 廢除啟發式子字串模糊打分**。
  4. 在 `sub_02` 過渡期間保留 `TopologyLinker`、`expand_contract_symbol_ids` 與 `DeterministicSymbolResolver` 既有公開簽名相容門面（並讓 `expand_contract_symbol_ids` 同時支援 `WorkspaceSymbolGraph` 與舊 `Dict[str, UnifiedSymbol]`），且同步升級 `TreeSitterDriver` 與 `MarkdownParser` 確保單檔 `extract_file_graph` 產出具備精確 alias 元資訊之 `imports`、`inherits`/`implements` 與 `documents` 邊。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `sub_01` 已落地之 `Span`、`ProvenanceStep`、`SymbolNode`、`RelationEdge`、`FileSymbolGraph` 與 `SymbolProcessor`（`ast_engine/schema.py`、`ast_engine/parsers/base.py`）。
  - 復用 `core.loader.load_module_from_path` 載入動態配置之 `ModulePathResolver` 與 `EdgeRefiner` 類別。
  - 復用並升級 `ast_engine/dialects/*` 各語言既有匯入正則與接收者正規化邏輯，將其抽離封裝為預設的 `ModulePathResolver` 與 `receiver_aliases` 配置。
- **邊界排除 (Explicitly Excluded)**：
  - **`ASTEngine` 二進位快取全面替換、L0/L1 六大公開原語（`slice_part`、`select_nodes`、`traverse_edges`）與 `knowledge-db` 下游消費端遷移**：歸屬 `sub_03_l0_l1_primitives_cache_and_kdb_migration`，不在 `sub_02` 提前越界修改 `knowledge-db`。
- **架構影響範圍**：
  - `ys_codebase/source/ast/contributes/_format.json`
  - `ys_codebase/source/ast/ast_engine/schema.py`
  - `ys_codebase/source/ast/ast_engine/linker.py`
  - `ys_codebase/source/ast/ast_engine/parsers/{base.py,registry.py,treesitter.py,markdown.py}`
  - `ys_codebase/source/ast/ast_engine/dialects/{base.py,python.py,csharp.py,cpp.py,javascript.py,typescript.py,markdown.py}`
  - `ys_codebase/source/ast/tests/`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 軸一（既有組件復用與過渡期雙軌相容）**：
  - 於 `ast_engine/linker.py` 實作全新的四階段確定性連結器 `WorkspaceGraphLinker`（及平權擴充介面 `ModulePathResolver`、`EdgeRefiner`），同時保留既有 `TopologyLinker` 與 `expand_contract_symbol_ids` 相容介面，並讓 `expand_contract_symbol_ids` 原生支援傳入 `WorkspaceSymbolGraph`，確保 `sub_02` 獨立驗收時既有 `engine.py`、`bundler.py` 與 `knowledge-db` 100% 無縫運作。
- **[P00:DR-02] 軸二（預設值與零幽靈邊消歧防呆）**：
  - `WorkspaceGraphLinker` 完全廢除舊版 `_score_candidates` 的 `+15.0 / +10.0 / +8.0` 子字串模糊打分；當四階確定性查找命中唯一符號時設為 `resolved`（`len(resolved_target_ids) == 1`）；命中同一父型別下多個同名重載方法（且無法依呼叫端參數數量唯一收斂）時設為 `overload_group`；跨不同型別匹配多個候選（如鴨子型別方法呼叫 `obj.run()`）時設為 `ambiguous` 並依字典序穩定保留全部候選 ID 於 `resolved_target_ids`；命中非工作區內之匯入模組前綴時設為 `external`；查無任何匹配時維持 `unresolved`。
- **[P00:DR-03] 軸三（生命週期、不可變結構與異常逆向隔離）**：
  - `FileImportBinding`、`FileImportTable` 與 `WorkspaceSymbolGraph` 100% 採用 `@dataclass(frozen=True)`，內部集合與字典一律轉為 `tuple`、`frozenset` 與 `MappingProxyType`（符合 `dev check` `C8`/`C9` 規範）；Pass 3 建構型別繼承圖時內建 DFS 環路偵測與斷路保護（防止惡意或語法錯誤之循環繼承 `class A(B): ... class B(A): ...` 造成無限迴圈）；外部注入之 `ModulePathResolver` 或 `EdgeRefiner` 若拋出異常，記錄 `log_warn(..., stream="stderr")` 並回退至內核預設行為，不中斷整體圖譜連結。
- **[P00:DR-04] 軸四（全局座標、跨檔同體不變量與來源追蹤）**：
  - 跨檔同體折疊（Pass 1，如 C# `partial class` 與 C/C++ `.h` 宣告 / `.cpp` 實作）僅在 `WorkspaceSymbolGraph` 層級產生 `edge_kind="merges_with"` 或 `edge_kind="declares"` 之關係邊與同體折疊群組映射，**嚴禁修改輸入之單檔 `FileSymbolGraph` 實例**；每條經 Pass 1~4 或 `EdgeRefiner` 解析之 `RelationEdge` 均追加對應的 `ProvenanceStep(provider_id=..., action="link"|"refine", rule_or_hook=...)` 並維持字典序穩定排序。
- **[P00:DR-05] 軸五（顯式排除與階段邊界鎖定）**：
  - `sub_02` 專注於 `WorkspaceSymbolGraph`、4-Pass 確定性連結流水線、四階作用域查找與 `ModulePathResolver` / `EdgeRefiner` 平權擴充契約；`ASTEngine` 快取結構切換、L0/L1 六大公開原語與 `knowledge-db` 下游遷移嚴格留待 `sub_03`。

---

## 3. 開放議題與確認紀錄

- **[已確認] 議題 1**：`R02` 四階段確定性跨檔連結流水線規格與五維度邊界均已收斂確認，無開放未決問題。
