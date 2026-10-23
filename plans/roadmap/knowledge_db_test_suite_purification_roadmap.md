# 技術路線圖：Knowledge-DB 測試集純化、跨檔去重與複合檢索／熱修補圖譜補盲 (`knowledge_db_test_suite_purification_roadmap`) (Roadmap)

> 主題：Knowledge-DB 測試集純化、跨檔去重與複合檢索／熱修補圖譜補盲 (`knowledge_db_test_suite_purification_roadmap`)  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
對 `ys-codebase / module:knowledge-db`（`v1.1.0.6`）下的 `tests/` 目錄（共 **14 個測試檔案、5,879 行程式碼、128 個 `test_*` 測試方法**）執行六維度測試體檢後，發現現有測試集存在 **5 大類結構性病灶（`KT-01` ～ `KT-05`）**，這也是為何 `K-01`（冷啟動向量索引永不載入）與 `K-02`（熱修補後跨檔 `callers` 入度邊 100% 遺失）在 128 個測試全綠下潛伏未覺的根本原因：

1. **`KT-01` 虛假測驗、自寫自驗與寬容放行（Vacuous, Self-Simulated & Lenient-Pass Tests，共 5 處）**：
   - **`test_space.py::TestKnowledgeDBProviders.test_ft_01_get_knowledge_db_spaces_output_format`（L228–252）**：在測試內建立局部變數 `mgr = SpaceManager(contributes_data=mock_contributes)`（含 `alpha_space`, `beta_space`），卻從未將 `mgr` 注入或 Mock 進 `get_knowledge_db_spaces()`；實際呼叫 `get_knowledge_db_spaces()` 時讀到空空間並回傳 `*(目前無已註冊空間)*`，而測試僅斷言表頭字串存在，導致 `providers.py` 空間列舉迴圈（L39–50）實際為 **0% 覆蓋**。
   - **`test_space.py::TestKnowledgeDBProviders.test_ft_02_get_knowledge_db_spaces_empty_fallback`（L254–260）**：Docstring 宣稱「驗證無任何空間時之安全降級輸出」，但測試內**完全未呼叫 `get_knowledge_db_spaces()`**，僅呼叫了 `mgr.load_spaces()`。
   - **`test_cli.py::test_cli_search_modes`（L190–271）＆ `test_cli_callers_callees_impact_modes`（L290–313）**：在未配置任何有效空間與符號的空環境下呼叫 `process(["search", "PIDController", ...])`，每次皆回傳 `未找到符合的結果（total=0）`；測試內多達 **5 處核心斷言被包在 `if "#01" in out:` 與 `if data["total"] > 0:` 條件塊內**（L199, L208, L220, L253, L267），因查無結果而 **100% 靜默跳過放行**。
   - **`test_retrieval.py::test_embedding_last_error_capture`（L646–662）**：宣稱驗證 FastEmbed 載入失敗時 `last_error` 結構化捕獲，實際卻是在測試裡**自己手動賦值 `failing_svc.last_error = {"error_type": "ImportError", ...}`** 再斷言該屬性等於 `"ImportError"`（自寫自驗）。
   - **`test_retrieval.py::DummyIndex`（L43–52）與 `TestHybridSearchEngine`（L732–803）**：使用虛構的 `DummyIndex.search()` 方法測試 `HybridSearchEngine`，但真實的 `InvertedIndex` 並無 `.search()` 方法（真實管線走 `elif self.bm25_engine is not None:` 分支），導致 `HybridSearchEngine` 與真實 `InvertedIndex` + `BM25Engine` 的對接分支在單元測試中從未執行。
2. **`KT-02` 歷史合併直接拼貼導致的雙胞胎重複測試與任務碎片檔（Duplicate Tests & Fragment Files，共 2 個碎片檔 ＋ 8 組重複測試）**：
   - **2 個任務導向碎片檔（Plan-Named Fragment Files）**：
     - `test_benchmark_perf_and_memory.py`（239 行，7 個測試）：過往單次效能瘦身任務留下的碎片檔，內容全數與 `test_retrieval.py`（Tokenizer、Posting `__slots__`、`InvertedIndex.doc_lengths`、Legacy 快取遷移、BM25 評分）及 `test_bundler.py`（`_parse_file_task_worker`）重疊。
     - `test_cli_ux.py`（356 行，9 個測試）：過往單次 CLI UX 任務留下的碎片檔，其中 `test_vector_index_model_mismatch_invalidation` 與 `test_retrieval.py::test_vector_index_dimension_compatibility` 重複、`test_embedding_model_config_and_fallback` 與 `test_retrieval.py::test_model_name_normalization` 重複，其餘應整併入 `test_cli.py` 與 `test_space.py`（Config）。
   - **`test_graph.py` 內部兩大 Class 上下直貼重複（3 組）**：
     - `test_add_and_query_edges`（L52）與 `test_ft_04_call_graph_index_bidirectional`（L420）**100% 逐行重複**。
     - `test_query_impact_layers`（L73）+ `test_cyclic_graph_resilience`（L100）與 `test_ft_05_call_graph_impact_and_cycle_protection`（L443）重複。
     - `test_serialization_roundtrip`（L215）與 `test_ft_06_call_graph_binary_cache_and_incremental_patch`（L462）前半段重複。
   - **`test_hot_reload.py` 內部兩大 Class 上下直貼重複（3 組）**：
     - `test_jit_invalidation_and_hot_healing`（L131）與 `test_ft_04_incremental_hot_reload_search`（L405）**100% 邏輯重複**。
     - `test_edge_case_deleted_file`（L219）與 `test_et_01_file_deletion_handling`（L439）**100% 邏輯重複**。
     - `test_edge_cases_missing_and_corrupted_snapshot`（L192）與 `test_et_03_corrupted_snapshot_fallback`（L499）**100% 邏輯重複**。
   - **`test_engine.py` 內部重複（1 組）**：
     - `test_compute_dynamic_snippet_lines_curve`（L144）與 `test_8000_char_budget_decay`（L293）在同一個 Class 內重複測試 `compute_dynamic_snippet_lines()`。
3. **`KT-03` 過時同義詞測試、死代碼測試與歷史墓碑斷言（Obsolete, Dead-Code & Tombstone Tests，共 10 處）**：
   - **已純化移除之 `thesaurus` 遺留測試（4 檔）**：配合 `K-05` 純化移除同義詞庫，需同步清理 `test_schema.py`（`ThesaurusConfig`）、`test_space.py`（`load_thesaurus`）、`test_bundler.py`（`bundle.thesaurus`）與 `test_engine.py`（`thesaurus` 注入）中的過時斷言。
   - **死代碼測試（2 處）**：`knowledge_db/protocol.py`（`LanguageTopologyProtocol`, `TreeSitterTopologyAdapter`, `TopologyProtocolRegistry`）與 `knowledge_db/schema.py:CallGraphNode` 在生產環境中 **0 次被呼叫**，僅在 `test_graph.py`（L188, L278）被測試（建議連同死代碼一併清理）。
   - **歷史墓碑測試（4 處）**：`test_cli.py::test_removed_commands`（L74，測已刪除之 `scan`/`bundle`）、`test_service_worker.py::test_cli_no_daemon`（L95，測已刪除之 `daemon`）、`test_space.py::test_ft_02_knowledgedb_config_purity`（L206，測 `hasattr(cfg, "enable_hot_reload_server")` 為 `False`）、`test_retrieval.py::test_dynamic_dimension_without_constant`（L637，測 `hasattr(emb_mod, "DEFAULT_EMBEDDING_DIM")` 為 `False`）。
4. **`KT-04` 全域單例快取與真實路徑狀態污染（Global Cache & Watcher Pollution，共 3 處）**：
   - `test_service_worker.py::test_mtime_cache_invalidation`（L128）修改全域 `_GLOBAL_INDEX_CACHE["unified_index"]`（設為 `doc_count = 42`）卻未在 `tearDown` 清理，污染同進程後續測試。
   - `test_service_worker.py::test_lifecycle`（L54）在未替換 `_pipeline` 與 `_space_manager` 的情況下直接呼叫 `worker.start()`，導致在真實工作區 `cache://knowledge-db/indices/` 寫入 `.watcher_active` 並對真實工作區啟動 Watchdog 執行緒。
   - `test_cli.py` 與 `test_cli_ux.py` 呼叫 `get_engine()` 單例執行測試，未在 `setUp`/`tearDown` 隔離 `_GLOBAL_ENGINE_INSTANCE` 與 `_GLOBAL_INDEX_CACHE`。
5. **`KT-05` 高風險真實路徑漏測（Critical Coverage Gaps，共 4 大區塊，對應 `K-01` ～ `K-08`）**：
   - **跨進程冷啟動向量檢索漏測（`K-01`）**：從未測試「建置索引寫盤後，清空記憶體快取並以全新 `KnowledgeEngine` 實例執行 `search()` 時，是否成功載入 `unified.vectors.bin.gz` 並走 `hybrid_rrf`」。
   - **熱修補後跨檔案 `callers / impact` 入度邊保真漏測（`K-02`）**：`test_hot_reload.py` 僅測試熱修補後的 `search()`，從未測試修改被調用檔案後執行 `act_callers()` 與 `act_impact()` 是否保留跨檔案上游調用者。
   - **複合檢索多副檔名 `--ftype=c,cpp,py` 與拓撲查詢 `--ftype` 目標消歧漏測（`K-04`）**。
   - **CLI 有結果實境下之 `-d --json` 全欄位驗證與 `contributes/` Schema 合規驗證漏測（`K-06`、`K-08`）**。

### 1.2 現況與影響範圍評估
- **架構定調：裁撤 2 個歷史任務碎片檔，將 `knowledge-db/tests/` 由 14 檔收斂為 12 個子系統 1:1 對齊的高內聚測試檔，消除 8 組重複測試並補齊 `K-01` ～ `K-08` 回歸防線**：
  1. **一子系統一測試檔（14 檔 $\rightarrow$ 12 檔）**：將 `test_benchmark_perf_and_memory.py` 與 `test_cli_ux.py` 無損拆併入對應子系統主測試檔並刪除碎片檔。
  2. **消滅歷史直貼雙胞胎（-650 行冗餘代碼）**：整併 `test_graph.py`、`test_hot_reload.py`、`test_engine.py` 內部的雙重 Class 重複測試，省去多餘的 `time.sleep` 與重複建索引開銷。
  3. **100% 實質斷言與跨進程狀態模擬**：所有 CLI 與 Engine 檢索測試皆在配備真實測試空間與符號的隔離沙盒中運行，徹底廢除 `if "#01" in out:` 條件式放行。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：僅刪除 `thesaurus` 斷言，維持 14 檔結構** | 配合 `K-05` 刪改同義詞斷言，不動碎片檔與重複測試 | 改動最小 | `test_graph.py` 與 `test_hot_reload.py` 的雙胞胎測試、`test_cli.py` 的空索引條件放行與 `test_space.py` 的空殼 Provider 測試依舊留存 | ⭐️⭐️ |
| **方案 2：將所有測試壓縮為 3 個大檔** | 強行將 12 個子系統合併為 3 個超過 1,500 行的巨型測試檔 | 檔案數最少 | 單檔過大（> 1,800 行），且當單一元件（如 `selector` 或 `scanner`）故障時難以快速定點跑測 | ⭐️⭐️⭐️ |
| **方案 3：子系統 1:1 對齊收斂（14 檔 $\rightarrow$ 12 檔）＋ 去重純化 ＋ 冷啟動／熱修補圖譜補盲（推薦採納）** | 1. 裁撤 `test_benchmark_perf_and_memory.py` 與 `test_cli_ux.py` 2 個任務碎片檔，歸戶至 12 個標準子系統測試檔。<br/>2. 消除 8 組重複測試、4 處墓碑測試與死代碼測試（同步清理未使用的 `protocol.py` 與 `CallGraphNode`）。<br/>3. 修復 5 處虛假／寬容放行測試並補齊 `K-01`～`K-08` 實機回歸測試。 | 1. 檔案與 `knowledge_db/*.py` 模組職責 1:1 清晰對應<br/>2. 削減約 20% 重複執行時間與 ~650 行冗餘代碼<br/>3. 100% 攔截冷啟動向量漏載與熱修補掉邊 | 需重構整併測試檔並同步清理 `knowledge_db/protocol.py` 死代碼 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1：僅刪同義詞斷言 | 方案 2：極端壓縮為 3 巨檔 | 方案 3：12 檔子系統對齊 ＋ 去重純化 ＋ 補盲（採納） |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 高 | **極高**（與 `testing-sop` 六大鐵律 100% 對齊） |
| **後續維護難度 (Maintenance)** | 高（碎片檔與雙胞胎測試混淆） | 高（單檔破千行難檢索） | **極低**（每個子系統皆有唯一主測試檔，單檔控制在 150～650 行） |
| **缺陷攔截可靠性 (Reliability)** | 低（`if "#01" in out:` 空跑） | 中 | **極高**（強制斷言非空結果、模擬跨進程冷啟動與跨檔熱修補） |
| **落地難度 (Implementation)** | 極低 | 中 | **低**（可與 `knowledge-db` 功能路線圖 Stage 1~3 同步落地） |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

### 4.1 測試集檔案結構收斂映射表（14 檔 $\rightarrow$ 12 檔）

| 序號 | 檔案名稱 | 處置動作與職責定位 |
| :---: | :--- | :--- |
| **1** | `test_benchmark_perf_and_memory.py` | **【裁撤併入】** 將 Tokenizer 測試併入 `test_retrieval.py::TestTokenizer`；將 Posting `__slots__`、`doc_lengths`、Legacy 遷移與 BM25 評分併入 `test_retrieval.py::TestRetrieval`；將 `_parse_file_task_worker` 併入 `test_bundler.py`。 |
| **2** | `test_cli_ux.py` | **【裁撤併入】** 將 `KnowledgeDBConfig` 測試併入 `test_space.py`；將 JIT 10 符號動態探針熔斷與 5 階段進度回呼併入 `test_hot_reload.py`；將 `TerminalStyler` 併入 `test_engine.py`；將 CLI `--help` / `status` / `--json` 純淨度併入 `test_cli.py`；刪除與 `test_retrieval.py` 重複的 `VectorIndex` / `normalize_model_name` 測試。 |
| **3** | `test_schema.py` | **【純化保留】** 驗證 `UnifiedSymbol`、`MemberInfo`、`SpaceConfig`、`LanguageConfig`；移除已廢棄的 `ThesaurusConfig` 與死代碼 `CallGraphNode` 測試。 |
| **4** | `test_space.py` | **【純化＋修復虛假測試】** 統管 `SpaceManager`、`KnowledgeDBConfig`（含 `core.config` 優先級驗證）與 `providers.py`；移除 `thesaurus` 斷言與墓碑測試 `test_ft_02_knowledgedb_config_purity`；**重寫 `TestKnowledgeDBProviders` 真實測試 `get_knowledge_db_spaces()` 非空表格與空空間降級輸出**。 |
| **5** | `test_scanner.py` | **【純化保留】** 統管 `BinarySnapshotManager` 與 `FingerprintScanner` 增量比對及損毀自癒。 |
| **6** | `test_parsers.py` | **【純化保留】** 統管 `ParserRegistry` 與 10 大語言 AST 解析器（Python, C/C++, C#, JS/TS, Markdown, SPICE, HTML, CSS），並補齊 `code.class://` 與語意 URI `query_file` 解析測試。 |
| **7** | `test_bundler.py` | **【純化＋擴充】** 統管 `SemanticBundle`、`SemanticBundler` 與 `_parse_file_task_worker`；移除 `bundle.thesaurus` 斷言。 |
| **8** | `test_selector.py` | **【純化保留】** 統管 `SymbolSelector` 語法解析與範疇／型別匹配。 |
| **9** | `test_retrieval.py` | **【去重＋修復虛假測試】** 統管 `MultilingualTokenizer`、`InvertedIndex`、`BM25Engine`、`SnippetExtractor`、`EmbeddingService`、`VectorIndex` 與 `HybridSearchEngine`；移除 `DummyIndex`，改用真實 `InvertedIndex` + `BM25Engine` 測試 `HybridSearchEngine`；重寫 `test_embedding_last_error_capture` 真實觸發 `_init_model()` 異常捕獲；移除 `DEFAULT_EMBEDDING_DIM` 墓碑斷言。 |
| **10** | `test_graph.py` | **【合併雙胞胎＋補齊熱修補保真】** 合併 `TestNetworkXCallGraphAndLinker` 與 `TestCallGraphAndReferenceIndex` 為單一類別，刪除 3 組完全重複的圖譜測試与 `protocol.py` 死代碼測試（同步刪除未使用的 `knowledge_db/protocol.py`）；新增跨檔案熱修補入度邊（`Callers`）保真測試（`K-02`）與 `--ftype` 目標消歧測試（`K-04`）。 |
| **11** | `test_hot_reload.py` | **【合併雙胞胎＋補齊冷啟動向量載入】** 合併 `TestJITHotHealing` 與 `TestIncrementalHotReload`，刪除 3 組重複的新增／刪除／損毀快照測試；併入 JIT 10 符號探針熔斷測試；新增「跨進程冷啟動自動載入 `unified.vectors.bin.gz` 執行 Hybrid RRF 檢索」測試（`K-01`）。 |
| **12** | `test_engine.py` | **【去重＋補齊 SDK 別名】** 統管 `KnowledgeEngine` 門面與 `ResultFormatter`（含 `UniversalRedundancyFilter`、`TerminalStyler`、8,000 字元預算）；刪除重複的 `test_compute_dynamic_snippet_lines_curve`；新增 `engine.callers() / callees() / impact()` SDK 別名測試（`K-08`）。 |
| **13** | `test_service_worker.py` | **【加固隔離＋清理墓碑】** 統管 `KnowledgeDBServiceWorker`、`hook.server.py` 與 `_GLOBAL_INDEX_CACHE` mtime 熱刷新；刪除墓碑測試 `test_cli_no_daemon`；於 `setUp`/`tearDown` 強制隔離 `_pipeline`、`_space_manager` 與還原 `_GLOBAL_INDEX_CACHE`，杜絕污染真實工作區；新增驗證 `hook.server.py` 僅呼叫 `pre_warm()` 不私自啟動第二個 Watcher（`K-03`）。 |
| **14** | `test_cli.py` | **【修復空索引寬容放行＋補齊 Schema 驗證】** 於 `setUp` 建立含真實 Python/Markdown 原始碼與調用關係的沙盒空間並注入 `_GLOBAL_ENGINE_INSTANCE`；徹底移除 `if "#01" in out:` 條件式放行，強制斷言 `search / callers / callees / impact` 在 `simple / snippet (-s) / detail (-d)` 與 `--json` 下的完整輸出結構（含 `search -d --json` 的 `id`, `matched_terms`, `spaces`, `code`）；刪除墓碑測試 `test_removed_commands`；新增 `ContributesValidator` 驗證 `contributes/*.json` 合規性。 |

### 4.2 5 處虛假／寬容放行測試 (`KT-01`) 重寫規格
1. **重寫 `test_space.py::TestKnowledgeDBProviders`**：
   - 使用 `patch("knowledge_db.providers.SpaceManager")` 回傳掛載了 `alpha_space` 與 `beta_space` 的 `SpaceManager` 實例，呼叫 `output = get_knowledge_db_spaces()`，明確斷言 `"**`alpha_space`**"`、"`module://alpha/docs`"、`"**`beta_space`**"` 皆存在於輸出表格中。
   - 另以空空間實例呼叫 `get_knowledge_db_spaces()`，明確斷言輸出包含 `"*(目前無已註冊空間)*"`。
2. **重寫 `test_cli.py::test_cli_search_modes` 與 `test_cli_callers_callees_impact_modes`**：
   - 在 `TestCLI.setUp()` 中建立暫存目錄（含 `controller.py` 定義 `PIDController.calculate` 與 `app.py` 定義 `MainApp.run` 調用 `PIDController.calculate`），配置為預設 `KnowledgeEngine` 單例並完成索引。
   - 移除所有 `if "#01" in out:` 與 `if data["total"] > 0:`，直接剛性斷言 `self.assertGreater(data["total"], 0)`、斷言 `-s` 與 `-d` 模式皆輸出代碼切片 `code`，且 `-d --json` 包含 40 碼 `id`、`matched_terms` 與 `spaces`。
3. **重寫 `test_retrieval.py::test_embedding_last_error_capture`**：
   - 建立本地假 `.onnx` 檔案使 `is_model_downloaded()` 為 `True`，並以 `patch("fastembed.TextEmbedding", side_effect=ImportError("WinError 1114 DLL init failed"))` 真實觸發 `failing_svc.is_available` $\to$ `_init_model()` 異常捕獲分支，斷言 `failing_svc.is_available` 為 `False` 且 `failing_svc.last_error["error_type"] == "ImportError"`。
4. **移除 `test_retrieval.py::DummyIndex`**：
   - 在 `TestHybridSearchEngine` 中直接使用真實 `InvertedIndex` 與 `BM25Engine` 搭配 `EmbeddingService(mock_mode=True)` 進行 RRF 融合、多副檔名 `--ftype=c,cpp,py` 過濾與降級測試。

### 4.3 4 大高風險漏測路徑 (`KT-05`) 補盲規格
1. **補齊「冷啟動跨進程向量索引自動載入與 RRF 檢索」測試（於 `test_hot_reload.py`，對應 `K-01`）**：
   - 實例 `eng1` 執行 `build_unified_index(force=True)` 產出 `unified.index.bin.gz` 與 `unified.vectors.bin.gz`。
   - 清空 `_GLOBAL_INDEX_CACHE`，建立全新 `eng2 = KnowledgeEngine(...)`（此時 `eng2.hybrid_engine.vector_index.doc_ids` 為空），直接呼叫 `eng2.search("query")`。
   - 斷言 `eng2.hybrid_engine.is_vector_available` 為 `True`、`len(eng2.hybrid_engine.vector_index.doc_ids) > 0`，證明冷啟動 `search()` 成功載入向量索引而非退化為純 BM25。
2. **補齊「修改被調用檔案後增量熱修補保留跨檔案上游 `Callers`（含類別方法與無前綴裸函式調用）」測試（於 `test_graph.py`，對應 `K-02`）**：
   - 建立 `service.py`（同時定義類別方法 `AuthService.verify` 與頂層函式 `verify_token`）與 `handler.py`（同時以 `AuthService.verify()` 前綴調用與 `from service import verify_token; verify_token()` 無前綴裸調用呼叫），建置初始索引並確認兩者之 `act_callers(...)["total_callers"] == 1`。
   - 修改 `service.py`（在檔頭新增註解與新函式使 `AuthService.verify` 與 `verify_token` 行號下移、SHA-1 ID 改變，但 `handler.py` 不變），觸發 JIT 熱修補後再次對 `AuthService.verify` 與 `verify_token` 呼叫 `act_callers()` 與 `act_impact()`。
   - 斷言兩者的 `total_callers == 1` 且調用者仍為 `handler.py` 的函式，實證第一階 `Identity Remap` 與第二階 `TopologyLinker` 能 100% 阻斷熱修補掉邊回歸。
3. **補齊「`--ftype=c,cpp,py` 逗號多副檔名複合檢索與拓撲目標消歧」測試（於 `test_retrieval.py` 與 `test_graph.py`，對應 `K-04`）**：
   - 在開啟向量檢索（`mock_mode=True`）下，呼叫 `engine.search("...", ftypes="c,cpp,py")`，斷言 `.py` 與 `.cpp` 的向量與詞彙命中皆正常保留。
   - 在同時存在 `worker.py:run` 與 `worker.ts:run` 的空間中，呼叫 `engine.act_callers("run", ftypes="ts")`，斷言 `target_symbol.language == "typescript"`。
4. **補齊 `contributes/` 全檔案 Schema 合規檢驗（於 `test_cli.py`，對應 `K-06`、`K-08`）**：
   - 使用 `core.validator.ContributesValidator` 逐一檢驗 `knowledge-db/contributes/_format.json`、`core.json`、`server.json`、`knowledge-db.json` 與 `agents-workflow.json`，確保 0 Schema 錯誤。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- **雙路線圖強制綁定／合併立項建議**：由於本測試純化路線圖之 `KT-03`（移除 `thesaurus` 測試與 `protocol.py` / `CallGraphNode` 死代碼測試）與 `KT-05`（補測 `K-01` 冷啟動向量載入、`K-02` 熱修補入度邊保真、`K-04` 多副檔名過濾與 `K-06` CLI `-d` 結構）與 `knowledge_db_retrieval_pipeline_and_purity_roadmap.md` 100% 共生，**立項時應將兩份 `knowledge-db` 路線圖合併為單一 `knowledge-db` 升級計畫（Full Track）同步交付**。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1：裁撤 2 個任務碎片檔、合併 8 組重複測試與清理死代碼／同義詞遺留（`KT-02`、`KT-03`）**
   - 將 `test_benchmark_perf_and_memory.py` 與 `test_cli_ux.py` 拆併入 `test_retrieval.py`、`test_bundler.py`、`test_hot_reload.py`、`test_engine.py`、`test_space.py` 與 `test_cli.py` 後刪除。
   - 合併 `test_graph.py`、`test_hot_reload.py`、`test_engine.py` 內部的重複測試，刪除墓碑測試、同義詞測試與未使用的 `knowledge_db/protocol.py` 及 `CallGraphNode`。
2. **Stage 2：修復 5 處虛假／寬容放行測試與加固全域單例隔離（`KT-01`、`KT-04`）**
   - 重寫 `test_space.py::TestKnowledgeDBProviders`、`test_cli.py` 實境沙盒檢索斷言、`test_retrieval.py::test_embedding_last_error_capture` 與真實 `InvertedIndex` 複合檢索測試。
   - 於 `test_service_worker.py` 與 `test_cli.py` 補齊 `tearDown` 對 `_GLOBAL_INDEX_CACHE` 與 `_GLOBAL_ENGINE_INSTANCE` 的狀態還原。
3. **Stage 3：補齊 `K-01` ～ `K-08` 四大高風險回歸測試並全量驗收（`KT-05`）**
   - 新增冷啟動向量索引載入測試、熱修補跨檔 `callers` 入度邊保真測試、`--ftype` 多副檔名與拓撲消歧測試、以及 `contributes` Schema 合規測試，執行 `python yscb.py dev test knowledge-db` 確保 12 個測試檔 100% 綠燈通過且環境零殘留。
