# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`module:knowledge-db` 轉型為 Layer 3 純混合檢索消費者與三階單向 DAG 快照對接  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_1009_ast_topology_engine_modularization](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將 `module:knowledge-db` 重構轉型為 `file-space (Layer 1) -> ast (Layer 2) -> knowledge-db (Layer 3)` 三階單向無環圖（Strict 3-Tier DAG）中的純混合檢索消費者，落實 Single-Parse Symbol Sharing（單次解析符號共享）與 Pull-Based JIT 連鎖同步，並徹底移除 `knowledge-db` 內部重複的 AST 解析器、分部聚合器、呼叫圖譜建構器與 `callers/callees/impact` CLI。
- **核心目標**：
  1. **零 Parser 與零拓撲殘留（`[P00:DR-02]`, `[P00:DR-03]`）**：物理移除 `ys_codebase/source/knowledge-db/` 內的 `knowledge_db/parsers/`、`assets/queries/`、`knowledge_db/{bundler,linker,graph,topology_query}.py` 與 `contributes/knowledge-db.json`；於 `manifest.json` 新增 `"ast": ">=1.0.0"` 依賴並移除 `tree-sitter*` 與 `networkx` 套件依賴（僅保留 `"fastembed": ">=0.3.0"`）。
  2. **Single-Parse Symbol Sharing（單次解析符號共享）**：`KnowledgeEngine` 與 `IndexingPipeline` 直接委派並消費 `ast_engine.ASTEngine` 產出的 `ASTSnapshot`（含已跨檔聚合之 `UnifiedSymbol` 與 `_own_members` 物理成員隔離），零重複執行 Tree-sitter / Python AST / Markdown 解析，建立 `InvertedIndex`（BM25 多欄位倒排索引）與 `VectorIndex`（ONNX 語意向量索引）。
  3. **三階 Pull-Based JIT 水位線與事件驅動熱修補（`uitk.net` 邊界 ④）**：
     - CLI 查詢與 `knowledge-db search` 時，透過 `self.ast_engine.ensure_jit_synced()` 取得最新 `ASTSnapshot`，比對 `acked_ast_generation` 與檔案差量，自動觸發增量熱修補（`hot_patch_unified_index`）或全量重建，維持「0 手動 index、隨改隨查」的 JIT 自癒體驗。
     - 常駐 Server 與 Hook 路徑（`scripts/hook.file-space.py`）同步透過 `ASTEngine` 快照驅動 `InvertedIndex` 與 `VectorIndex` 熱修補。
  4. **CLI 與 `contributes` 契約純化**：`knowledge-db` CLI 僅保留 `status`、`index`、`search`、`clean`、`model` 五大檢索與索引治理子命令；`contributes/_format.json` 僅保留 `space_weights` 權重擴充點。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 直接復用 `sub_01` 已落成之 `ast_engine`（`ASTEngine`, `ASTSnapshot`, `UnifiedSymbol`, `MemberInfo`, `SymbolKind`, `LanguageType`, `SemanticBundle`, `aggregate_partial_symbols`, `restore_unaggregated_partial_symbol`）。
  - 保留並精簡 `knowledge_db/{retrieval,tokenizer,embedding,formatter,service,providers}.py` 既有之多欄位 BM25、ONNX 向量檢索、RRF 混合排序與 10-symbol 向量探針自癒能力。
- **邊界排除 (Explicitly Excluded)**：
  - 不在 `knowledge-db` 保留任何 AST/文檔 Parser、呼叫圖譜（`unified.graph.bin.gz`）或 `callers/callees/impact` CLI 轉發殼層。
  - `agents-workflow` 技能手冊與 `docs/` 架構文檔更新歸屬後續 `sub_03_agents_workflow_ast_routing` 處置。
- **架構影響範圍**：
  - `ys_codebase/source/knowledge-db/manifest.json`
  - `ys_codebase/source/knowledge-db/contributes/{_format.json,_manifest.md,core.json,knowledge-db.json}`
  - `ys_codebase/source/knowledge-db/knowledge_db/{__init__,schema,engine,pipeline,retrieval,formatter,service}.py`
  - `ys_codebase/source/knowledge-db/scripts/{cli.py,hook.file-space.py}`
  - `ys_codebase/source/knowledge-db/tests/test_*.py`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `knowledge_db.schema` 與 `ast_engine.schema` 型別同一性與無損重匯出**：
  - `knowledge_db/schema.py` 直接從 `ast_engine` 匯入並重匯出 `UnifiedSymbol`、`MemberInfo`、`SymbolKind`、`LanguageType`、`SemanticBundle`、`aggregate_partial_symbols`、`restore_unaggregated_partial_symbol`，同時保留 `knowledge-db` 專屬之 `SearchQuery` 與 `SearchResult` 契約，確保 `ASTSnapshot.symbols` 進入 `InvertedIndex` 與 `HybridSearchEngine` 時具備 100% 類別同一性（零轉型拷貝開銷），且相容既有匯入路徑。
- **[P00:DR-02] 零 Parser 殘留與 `ASTSnapshot` 單次解析消費機制**：
  - `IndexingPipeline.build_unified_index()` 不再呼叫 `SemanticBundler.bundle_all()`，而是呼叫 `self.ast_engine.ensure_jit_synced(force=force)` 取得 `ASTSnapshot`，直接將 `list(snapshot.symbols.values())` 餵入 `InvertedIndex.add_symbols_batch()` 與 `VectorIndex`。
  - 由於 `ASTSnapshot.symbols` 已由 `module:ast` 完成 `aggregate_partial_symbols()` 並保留單檔物理 `_own_members`，`InvertedIndex._extract_symbol_members_text()` 直接讀取 `_own_members` 建立分部成員倒排索引，100% 杜絕 `partial class` 跨檔重複膨脹（$N^2$ Bloat）。
- **[P00:DR-03] 三階 Pull-Based JIT 游標水位線與增量熱修補（`acked_ast_generation`）**：
  - `IndexingPipeline` 於 `unified.index.bin.gz` 內持久化 `acked_ast_generation: int`（對應建置或修補當下之 `ASTSnapshot.ast_generation`）。
  - 當 `KnowledgeEngine._ensure_jit_index_ready()` 觸發時：
    1. 先讀取 `file-space` 對 `consumer_id="knowledge-db"` 的差量 `diff_detail = self.space_manager.get_unconsumed_diff("knowledge-db")`。
    2. 呼叫 `self.ast_engine.ensure_jit_synced()` 確保 Layer 2 `ASTSnapshot` 已同步至最新 `file-space` 狀態。
    3. 若 `diff_detail` 存在變更檔案（或 `acked_ast_generation != snapshot.ast_generation`），則從 `snapshot.symbols` 提取髒檔案對應之最新 `UnifiedSymbol` 集合，對 `InvertedIndex` 與 `VectorIndex` 執行毫秒級 `hot_patch_unified_index()`，並推進 `acked_ast_generation` 與 `space_manager.ack_consumed("knowledge-db", head_gen)`。
- **[P00:DR-04] CLI、`contributes` 與測試集純化**：
  - 從 `contributes/core.json` 與 `scripts/cli.py` 移除 `callers`、`callees`、`impact` 子命令；從 `contributes/_format.json` 移除 `languages` 欄位並刪除 `contributes/knowledge-db.json`。
  - 刪除已遷移至 `ys_codebase/source/ast/tests/` 之 `tests/{test_parsers,test_bundler,test_graph}.py`，並更新 `tests/{test_cli,test_engine,test_file_space,test_schema,test_hot_reload,test_self_healing,test_service_worker}.py` 以驗證三階 DAG 單次解析共享與 JIT 自癒。

---

## 3. 開放議題與確認紀錄

- 所有決策均已於主計畫 [`P00_discuss.md`](../P00_discuss.md) 由開發者確認定案，本子計畫直接以 `/auto` 推進至 Phase 06。

