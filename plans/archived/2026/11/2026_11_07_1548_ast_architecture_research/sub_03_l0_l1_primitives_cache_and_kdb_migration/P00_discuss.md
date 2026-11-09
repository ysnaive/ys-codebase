# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：AST 單次掃描 FileSymbolGraph 快取、L0/L1 六大操作原語、CLI 升級與 KDB 下游對接遷移  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_07_1548_ast_architecture_research  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：依主計畫 `R03_graph_primitives_incremental_cache_and_kdb_contract.md` 定案結論，啟動第三個子計畫 `sub_03_l0_l1_primitives_cache_and_kdb_migration`，落地基於不可變 `FileSymbolGraph` 之單次掃描（Single-Pass）二進位快取與 $O(|\text{Dirty}|)$ 零污染增量熱修補（拔除重複 Tree-sitter 解析與 `_own_members` 髒狀態原地還原）；實作 L0 無狀態單檔原語（`parse_file`、`outline`、`slice_part`）與 L1 全倉圖譜原語（`resolve`、`select_nodes`、`traverse_edges` 及 CLI 對齊）；並完成下游 `knowledge-db` 與全倉測試無縫對接遷移。
- **核心目標**：
  1. **單次掃描 `FileSymbolGraph` 快取與零污染增量熱修補（Single-Pass Cache & $O(|\text{Dirty}|)$ Hot-Patch）**：
     - 在 `SemanticBundler` 與 `ASTEngine` 管線中建立基於單次 `ParserRegistry.extract_file_graph(...)` 的 `FileSymbolGraph` 快取字典 `file_graphs_by_path: Dict[str, FileSymbolGraph]`（以 `core.space` 對齊之 `content_hash` 校驗有效性）與持久化（於 `ASTSnapshot` 擴充保存 `file_graphs` 與於 `unified.graph.bin.gz` / `ASTEngine._workspace_graph` 保存 `WorkspaceSymbolGraph`），徹底消除建置索引時同檔三次重複解析（`parse_file` + `extract_call_sites` + `extract_imports`）。
     - `hot_patch_index` 收到 `ScanDiffDetail` 時，僅重新呼叫 `extract_file_graph` 解析 `added | modified` 髒檔案、淘汰 `deleted` 檔案之 `FileSymbolGraph`，其餘無變更檔案 100% 沿用記憶體/磁碟中之不可變 `FileSymbolGraph` 並直接重跑 `WorkspaceGraphLinker.link_workspace(...)`，拔除脆弱之 `_own_members` 原地變異與還原步驟，並同步衍生相容之 `ASTSnapshot` 與 `CallGraphIndex`。
  2. **L0 無狀態單檔原語（Zero-Index / Stateless Single-File Primitives）**：
     - `ASTEngine.parse_file(file_or_uri, *, content=None) -> FileSymbolGraph`：純記憶體無狀態單檔解析，支援直接傳入未落盤之 `content: str | bytes`，絕不觸發全倉 `ensure_jit_synced()` 或讀寫磁碟快取。
     - `ASTEngine.outline(file_or_uri, ...)`：底層基於 `FileSymbolGraph`（或當 `merged=True` / 含 `partial` 時結合 `WorkspaceSymbolGraph` 之 `merges_with` 同體群組）投影大綱樹並保持既有 `OutlineResult.to_dict()` 回傳契約與三維正交過濾相容。
     - `ASTEngine.slice_part(symbol_or_id, part="outer", *, file_bytes=None) -> str`：利用 `SymbolNode.parts[part]`（`"name"`, `"signature"`, `"parameters"`, `"return_type"`, `"doc"`, `"body"`）或 `node.span`（`"outer"`）執行 $O(1)$ 無損位元組切片（`raw_bytes[span.start_byte : span.end_byte].decode("utf-8")`），絕不重跑 Tree-sitter 或以正則截斷源碼。
  3. **L1 全倉語意圖譜原語（Workspace Graph Primitives）与 CLI 對齊**：
     - `ASTEngine.get_workspace_graph(auto_sync=True) -> WorkspaceSymbolGraph`：取得當前 JIT 同步後之全倉不可變 `WorkspaceSymbolGraph`。
     - `ASTEngine.resolve(selector_expr, *, spaces=None, kinds=None, ftypes=None) -> SymbolResolutionResult`：橫跨程式碼、Markdown 文檔與 `contributes` 宣告符號之確定性選擇器解析原語。
     - `ASTEngine.select_nodes(*, spaces=None, kinds=None, visibility=None, facets=None, ftypes=None) -> Tuple[SymbolNode, ...]`：批次條件篩選全倉 `SymbolNode`（支援 `kinds` 交集、`visibility`、`spaces` 與 `facets` 鍵值匹配）。
     - `ASTEngine.traverse_edges(seed_ids, *, edge_kinds=None, direction="out", depth=1, status_filter=None) -> Dict[str, Any]`：通用有向圖 BFS 遍歷原語，支援任意 `edge_kinds`（`calls`, `inherits`, `implements`, `imports`, `references`, `documents`, `merges_with`, `declares`）、方向（`"out"` / `"in"` / `"both"`）、深度與 `resolution_status` 過濾（預設排除 `"unresolved"`），並讓 `callers`、`callees`、`impact` 作為對齊其上之領域視圖且完整保留 `ambiguous` 結構化回報。
     - 於 `ys_codebase/source/ast/contributes/core.json` 與 `scripts/cli.py` 擴充支援 `slice`（`slice_part`）與 `traverse`（`traverse_edges`）子命令（或選用旗標），並維持既有 `outline`、`callers`、`callees`、`impact`、`status`、`clean` 100% 向下相容。
  4. **下游 `knowledge-db` 對接與零回歸驗證**：
     - 確保 `knowledge-db` 之 `IndexingPipeline`（`_sync_ast_snapshot`、`_collect_all_dirty_files`、`_align_index_symbols_with_ast_snapshot`）與 `ASTEngine` 單次掃描快取管線無縫協同，並支援從 `ASTEngine` 直接透過 `select_nodes`、`traverse_edges` 與 `slice_part` 消費全倉符號與文檔雙向邊，通過 `ast` 與 `knowledge-db` 全量測試守門。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `sub_01` 已落地之 `Span`、`SymbolNode`、`RelationEdge`、`FileSymbolGraph` 與 `ParserRegistry.extract_file_graph`。
  - 復用 `sub_02` 已落地之 `WorkspaceSymbolGraph` 與 `WorkspaceGraphLinker.link_workspace`。
  - 復用 `core.space` 之 `consume_diff(consumer_id="ast")` 與檔案指紋雜湊機制。
- **邊界排除 (Explicitly Excluded)**：
  - **KDB 多視角文檔生成器本體（SDK Doc / Superset Tech Doc / Tutorial Generator）**：本子計畫聚焦於 `module:ast` 側之單次掃描快取、L0/L1 六大原語落地及與 `knowledge-db` 現有檢索/索引管線之無縫對接；KDB 全新多視角文檔生成業務邏輯屬於後續獨立之 KDB 專題計畫。
- **架構影響範圍**：
  - `ys_codebase/source/ast/ast_engine/{schema.py,bundler.py,engine.py,graph.py,linker.py,resolver.py,formatter.py,__init__.py}`
  - `ys_codebase/source/ast/contributes/core.json`
  - `ys_codebase/source/ast/scripts/cli.py`
  - `ys_codebase/source/ast/tests/`
  - `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 軸一（既有組件復用與雙視圖無損橋接）**：
  - `ASTEngine.build_index` 與 `hot_patch_index` 底層全面改以 `ParserRegistry.extract_file_graph` 產出之不可變 `FileSymbolGraph` 與 `WorkspaceGraphLinker.link_workspace` 產出之 `WorkspaceSymbolGraph` 為唯一真實來源（SSOT）；並由 `FileSymbolGraph` / `WorkspaceSymbolGraph` 確定性投影衍生 `ASTSnapshot`（含聚合後之 `UnifiedSymbol` 字典與 `file_graphs: Dict[str, FileSymbolGraph]`）與 `CallGraphIndex`（附掛 `workspace_graph: Optional[WorkspaceSymbolGraph]`），使既有 `get_snapshot()`、`get_call_graph()` 與 `knowledge-db` 100% 零斷裂運作，同時徹底消滅建置/熱修補時對同一檔案的三次重複 Tree-sitter 解析。
- **[P00:DR-02] 軸二（L0/L1 原語預設值與邊界防呆）**：
  - `slice_part(symbol_or_id, part="outer", *, file_bytes=None)`：當 `part="outer"` 時切取 `SymbolNode.span`；當 `part` 為 `"name"`、`"signature"`、`"parameters"`、`"return_type"`、`"doc"`、`"body"` 時切取 `SymbolNode.parts.get(part)`，若該節點無對應部位（例如欄位無 `"body"` 或無 docstring）則安全回傳空字串 `""`；若傳入未知的 `part` 名稱則拋出明確之 `ASTError` / `ValueError`。
  - `traverse_edges(seed_ids, *, edge_kinds=None, direction="out", depth=1, status_filter=None)`：`direction` 預設為 `"out"`，`depth` 預設為 `1`（若 `depth <= 0` 則回傳空層級），`status_filter` 預設為 `frozenset({"resolved", "overload_group", "ambiguous"})`（自動過濾 `"unresolved"` 與 `"external"`，亦可顯式指定包含 `"external"`）。
- **[P00:DR-03] 軸三（增量熱修補生命週期與零髒狀態污染）**：
  - 增量熱修補 `hot_patch_index` 僅針對 `detail.added | detail.modified` 重新提取 `FileSymbolGraph`、從 `self._file_graphs` 移除 `detail.deleted`，隨後將全倉存活之不可變 `FileSymbolGraph` 集合交由 `WorkspaceGraphLinker.link_workspace` 執行快速記憶體內 4-Pass 連結（10 檔 5,000+ 邊僅需 ~0.2s，全倉記憶體連結無任何磁碟 I/O 與 Tree-sitter 解析開銷），徹底廢除舊版 `_evict_dirty_and_reaggregate_partials` 中脆弱的 `_own_members` 還原與外部入邊手動重連邏輯。
- **[P00:DR-04] 軸四（位元組座標一致性與跨平台編碼對齊）**：
  - `slice_part` 讀取目標檔案時必須以原始位元組 `Path.read_bytes()`（或將傳入之 `str` 以 UTF-8 編碼為 `bytes`）直接依 `Span.start_byte:Span.end_byte` 切片後再 `.decode("utf-8", errors="replace")`，保證與 Tree-sitter UTF-8 byte offset 100% 對齊，不受多語系非 ASCII 字元影響。
- **[P00:DR-05] 軸五（顯式排除與階段邊界鎖定）**：
  - `sub_03` 聚焦於完成 `R03` 定義之單次掃描 `FileSymbolGraph` 快取、L0/L1 六大原語、CLI 擴充（`slice`、`traverse`）與 `knowledge-db` 對接驗證；完成本子計畫後，`2026_11_07_1548_ast_architecture_research` 主計畫之三大里程碑即全數達成。

---

## 3. 開放議題與確認紀錄

- **[已確認] 議題 1**：`R03` 單次掃描 `FileSymbolGraph` 快取、L0/L1 六大操作原語與 `knowledge-db` 對接規格均已收斂確認，無開放未決問題。
