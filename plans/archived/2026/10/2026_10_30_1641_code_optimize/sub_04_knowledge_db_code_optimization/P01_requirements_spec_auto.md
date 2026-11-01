# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_04_knowledge_db_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `Mode A` 基礎分詞、解析註冊與空間掃描別名物理清除 (`M-01~M-05`) | 1. 物理刪除 `tokenizer.py` 之 `CodeTokenizer` 別名與 `is_cjk`、`split_identifier` 0 調用實例包裝方法。<br/>2. 物理刪除 `parsers/registry.py` 之 `LanguageRegistry` 別名、5 個空殼子類別 (`PythonParser`, `MarkdownParser`, `CppParser`, `CSharpParser`, `JsTsParser`) 及 `get_language_configs()`、`is_supported_file()`，直接以 `TreeSitterDriver(lang=...)` 註冊。<br/>3. 物理刪除 `space.py` 之 `get_union_spaces`（統一使用 `list_spaces`）與 `scanner.py` 之 `save_fingerprints`、`load_fingerprints`。<br/>4. 物理刪除 `config.py` 之 `load(workspace_root=None)` 未使用參數、`self.root_path`、`_find_workspace_root()`、`resolve_jit_vector_timeout()`，並將 `L81` `Config` 改為正統 `ConfigManager`。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | `Mode A` 檢索、資料模型、門面薄代理與歷史分支清除 (`M-06~M-10`) | 1. 物理刪除 `retrieval.py` 之 `InvertedIndex.symbols_map`、`build_unified` 及 `Posting` 舊版 `field_lengths` 相容分支。<br/>2. `schema.py` 之 `UnifiedSymbol.to_dict/from_dict` 僅保留正統 `"children"` 與 `"spaces"`，物理刪除 `AggregatedFileResult` 6 個相容 property 與 `WeightedToken`。<br/>3. 物理刪除 `engine.py` 16 個內部組件單行代理、`act_callers`/`act_callees`/`act_impact` 重複方法、`caller_symbol`/`fingerprint_cached_files`/`index_cached` 重複字典鍵及 `bundle(pretty=...)`、`status(space_name=...)` 未使用參數。<br/>4. 將 `pipeline.py` 之 `HotPatchResult` 改為標準 `@dataclass`（僅保留 `.patched_count`），刪除舊版 `*.index.json`/`fingerprints.json` 清理與 `"2.0"` 版本分支。<br/>5. 物理刪除 `M-10` 所列 `graph.patch_incremental`、`treesitter._extract_preceding_comment` 未使用參數、`embedding` 0 調用方法/屬性、`bundler` 死方法與 `hook.server.py` 舊版 `on_worker_warming` 包裝。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | `TopologyQueryService` 職責剝離與 `pipeline.py` 階段拆解 (`F-01`) | 1. 將 `pipeline.py` 內調用圖拓撲查詢邏輯（`_resolve_target_symbols`、`callers`、`callees`、`impact` 與 BFS 風險分級）完整剝離至獨立模組 `knowledge_db/topology_query.py` (`TopologyQueryService`)。<br/>2. 將 `_hot_patch_unified_index_locked` 拆解為 `_collect_all_dirty_files`、`_evict_dirty_file_artifacts`、`_reparse_and_relink_dirty_files`、`_persist_patched_indices` 四階段。<br/>3. 將 `search` 拆解為 `_prepare_search_context_and_filters`、`_execute_lexical_and_vector_retrieval`、`_enrich_snippets_and_expand_ast` 三階段，並剝離無狀態純函式。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-04** | `BM25Engine` 雙軌打分核心合一與複合字過濾修復 (`F-02`) | 抽取 `BM25Engine._score_candidate_documents` 共用核心，統一執行 IDF 預計算、Posting 走訪、欄位加權與「$\ge 3$ sub-tokens 複合字 50% 覆蓋率門檻過濾」，使 `search` 與 `search_aggregated` 共用同一打分基準並修復聚合搜尋噪音召回缺口。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-05** | CLI 與 Formatter 拓撲查詢三倍重複收斂 (`F-03`) | 1. 於 `formatter.py` 抽取通用樹狀拓撲渲染器 `_format_topology_tree`，收斂 `format_callers`、`format_callees`、`format_impact` 重複邏輯。<br/>2. 於 `scripts/cli.py` 抽取 `_run_topology_cli_command`，收斂 `cmd_callers`、`cmd_callees`、`cmd_impact` 重複樣板。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-06** | 原子寫入原語、Gzip+Pickle 共用 I/O 與圖譜/設定純化 (`F-04, F-06~F-08`) | 1. 新建 `knowledge_db/io_utils.py` 提供 `atomic_save_gzip_pickle` 與 `load_gzip_pickle`，供 `retrieval.py`、`graph.py`、`embedding.py`、`bundler.py` 共用，並為 `embedding.download_model` 補齊 `.tmp + os.replace` 原子替換。<br/>2. 移除 `graph.py:CallGraphIndex` 之 `_HAS_NX` 分支與純 Python `_out_edges`/`_in_edges` 備援結構，100% 採用 `nx.DiGraph`。<br/>3. 統一以 `config.py` 為執行緒數計算與模型預設值之單一真理來源。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-07** | 目錄掃描生成器收斂與解析器/連結器長方法拆解 (`F-05, F-09`) | 1. 於 `scanner.py` 抽取 `_iter_eligible_files` 生成器，供 `scan_directory`、`scan_spaces`、`get_dirty_files` 共用。<br/>2. 拆解 `treesitter.py:extract_symbols`、`spice.py:extract_symbols` 與 `graph.py:TopologyLinker.resolve_call_site` 深層巢狀控制流。 | P1 | [P00:DR-01], [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 複合字（$\ge 3$ sub-tokens）查詢於 `search_aggregated` 模式下僅匹配單一通用子詞（覆蓋率 $< 50\%$） | 由共用 `_score_candidate_documents` 強制過濾覆蓋率未達 $\lceil N \times 0.5 \rceil$ 的候選符號，防止單一高頻子詞撐高檔案聚合分數。 |
| **EC-02** | `VectorIndex.save_binary` 或 `download_model` 寫入中途發生 I/O 例外或程序中斷 | 統一寫入 `.tmp` 暫存檔並在 `except` 區塊安全清理殘留 `.tmp` 檔，確保原索引或模型檔不被半成品覆蓋損毀。 |
| **EC-03** | 拓撲查詢（`callers`/`callees`/`impact`）輸入空符號、未命中符號或命中多個同名符號（Disambiguation） | `TopologyQueryService` 與通用 CLI/Formatter 保持一致的空查詢攔截、空結果結構與同名候選清單渲染契約。 |
| **EC-04** | 反序列化損毀或版本不相容（非 `"2.1"`）之持久化索引檔 | `load_gzip_pickle` 與 `_load_persisted_index_if_valid` 捕獲例外或版本不符時安全回退至重新建置，不拋出未處理崩潰。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 代碼精簡與職責純化 | 100% 物理清除 `M-01~M-10` 共 23 項歷史別名與死代碼；`pipeline.py` 行數由 1,412 LOC 壓降至 $\le 900$ LOC，全模組淨減 $\ge 800$ LOC。 |
| **NFR-02** | 並行邊界與相依隔離 | 嚴格限制修改範圍於 `ys_codebase/source/knowledge-db/` 與本子計畫目錄，零跨模組副作用，並確保所有修改檔案 100% 通過 `py_compile` 語法檢核與測試同步更新。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** **[P01:DR-01] `Mode A` 測試同步遷移原則**：移除 `CodeTokenizer`、`LanguageRegistry`、5 個空白 Parser 子類別、`KnowledgeEngine` 薄代理與 `HotPatchResult(int)` 後，`ys_codebase/source/knowledge-db/tests/` 內直接引用舊別名或內部組件代理之測試案例必須同步切換至正統 API（如 `MultilingualTokenizer`、`ParserRegistry().get_parser_for_file()`、`engine.pipeline.*`、`result.patched_count`）。
