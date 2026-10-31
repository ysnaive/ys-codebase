# 技術調研報告：`knowledge-db` 模組五維度靜態診斷與 Mode A 無損重構處方 (R01_code_optimization_audit.md)

> 調研主題：sub_04_knowledge_db_code_optimization (`knowledge-db` 模組五維度靜態診斷與 Mode A 無損重構處方)  
> 建立日期：2026-10-30  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  1. **巨型單體管線與跨層重複編排（`D1` / `D3`）**：`ys_codebase/source/knowledge-db/knowledge_db/pipeline.py`（1,412 LOC）同時承擔「多空間索引建置、增量熱修補 (`_hot_patch_unified_index_locked` 212 LOC)、混合檢索 (`search` 303 LOC)、調用圖查詢 (`callers`/`callees`/`impact` ~350 LOC)、狀態盤點與常駐背景服務」6 大職責；`formatter.py`（1,057 LOC）與 `scripts/cli.py`（928 LOC）則各自針對 `callers`、`callees`、`impact` 重複實作三套高度同構的 CLI 參數驗證與終端樹狀渲染邏輯。
  2. **雙軌檢索迴圈分叉引發演算法一致性漂移（`D3` — `P0/P1`）**：`retrieval.py:BM25Engine` 的 `search`（`L648-774`）與 `search_aggregated`（`L776-940`）複製貼上了 ~95 行相同的 IDF 預計算、Posting 走訪與 BM25F 打分迴圈，導致後續在 `search` 加入的「長複合字（$\ge 3$ sub-tokens）50% 覆蓋率門檻過濾」未同步至 `search_aggregated`（`L840-868`），造成檔案聚合搜尋與一般符號搜尋的召回過濾行為不一致。
  3. **多層相容別名、門面薄代理與雙軌序列化負債（`D2` / `D5`）**：殘留 `CodeTokenizer = MultilingualTokenizer`、`LanguageRegistry = ParserRegistry`、5 個空白的 `TreeSitterDriver` 空殼子類別、`KnowledgeEngine` 16 個單行代理屬性/方法、`act_callers`/`act_callees`/`act_impact` 雙套命名、`UnifiedSymbol` 的 `children`/`members` 與 `space`/`spaces` 雙重 JSON 讀寫、`AggregatedFileResult` 6 個偽裝為 `SearchResult` 的相容屬性、`HotPatchResult(int)` 繼承 `int` 的雙重語意，以及舊版 `*.index.json` / `fingerprints.json` 遷移死分支。
  4. **非原子檔案寫入與雙套圖譜引擎維護（`D3` / `D4`）**：`embedding.py:VectorIndex.save_binary`（`L581-594`）與 `download_model`（`L220-225`）直接開啟目標路徑寫入而未採用 `.tmp + os.replace` 原子替換；`graph.py:CallGraphIndex` 在 `manifest.json` 已強制依賴 `networkx>=3.0` 的前提下，仍同時維護 `nx.DiGraph` 與純 Python `_out_edges`/`_in_edges` 雙套圖走訪與 BFS 邏輯。
- **調研目標**：
  - 鎖定 **範圍 = 單一模組（`ys_codebase/source/knowledge-db/`，含 `knowledge_db/` 28 檔與 `scripts/` 2 檔，共 30 檔 / 11,535 LOC）** 與 **生命週期 = `Mode A：新功能收斂期（Convergence Mode / 可破壞性變更）`**。
  - 融合雙子代理（Auditor A / Auditor B）獨立盲測共識，產出完整基線盤點、`Mode A` 破壞性清除清冊（12 大群組共 23 項）、`D1~D5` 分級問題單（`P0/P1/P2`）與 `S1~S6` 無損重構處方。

### 1.1 `knowledge-db` 模組基線盤點表 (30 檔 / 11,535 LOC)

| 檔案路徑 (`ys_codebase/source/knowledge-db/...`) | 行數 (LOC) | 核心職責與主要類別/函式 | 入向耦合 (`kdb` 內 / 跨模組) | 診斷熱點等級 |
| :--- | :---: | :--- | :--- | :---: |
| `knowledge_db/pipeline.py` | 1,412 | `KnowledgePipeline`、`KnowledgeDBService`：統一索引建置、熱修補、混合檢索与拓撲查詢 | `engine`、`cli`、`hook.server`、`tests/` | **P0 / P1** |
| `knowledge_db/formatter.py` | 1,057 | `ResultFormatter`：搜尋結果、AST 展開切片、Callers/Callees/Impact 與 Status 渲染 | `cli`、`tests/` | **P0 / P1** |
| `knowledge_db/retrieval.py` | 941 | `InvertedIndex`、`BM25Engine`、`HybridRanker`：BM25F 倒排檢索與 RRF 混合排序 | `pipeline`、`bundler`、`tests/` | **P0 / P1** |
| `scripts/cli.py` | 928 | `knowledge-db` CLI 路由入口（`search`/`callers`/`callees`/`impact`/`index`/`status`/`bundle`） | `core.dispatcher`、`tests/` | **P0 / P1** |
| `knowledge_db/embedding.py` | 636 | `ONNXEmbeddingModel`、`VectorIndex`：ONNX 向量推論、分塊池化與 Gzip+Pickle 索引 | `pipeline`、`bundler`、`tests/` | **P0 / P1** |
| `knowledge_db/graph.py` | 629 | `TopologyLinker`、`CallGraphIndex`：兩階段跨檔符號連結與 NetworkX 有向圖分析 | `pipeline`、`bundler`、`tests/` | **P1** |
| `knowledge_db/parsers/treesitter.py` | 624 | `TreeSitterDriver`：基於 `.scm` 查詢之多語言通用 AST 與調用點提取引擎 | `registry`、`tests/` | **P1** |
| `knowledge_db/schema.py` | 482 | `UnifiedSymbol`、`SearchResult`、`AggregatedFileResult`：核心資料模型 | 全模組共用 | **P1** |
| `knowledge_db/engine.py` | 453 | `KnowledgeEngine`：高階門面與執行期資源監控 (`RuntimeMonitor`) | `cli`、`hook.server`、`tests/` | **P1** |
| `knowledge_db/bundler.py` | 433 | `KnowledgeBundler`：預編譯知識包匯出/匯入與壓縮序列化 | `pipeline`、`cli`、`tests/` | **P1** |
| `knowledge_db/parsers/markdown.py` | 380 | `CustomMarkdownParser`：標題階層樹、Frontmatter 與圍欄代碼塊解析 | `registry`、`tests/` | **P2** |
| `knowledge_db/parsers/spice.py` | 341 | `SpiceParser`：SPICE 電路網表 `.subckt`、元件實例與參數解析 | `registry`、`tests/` | **P1 / P2** |
| `knowledge_db/parsers/registry.py` | 296 | `ParserRegistry`：副檔名與語言解析器映射表及 5 個空殼子類別 | `pipeline`、`scanner`、`tests/` | **P1** |
| `knowledge_db/scanner.py` | 288 | `FingerprintScanner`：兩階段 (`mtime_ns + size` $\to$ `xxh64`) 增量指紋掃描 | `pipeline`、`tests/` | **P1** |
| `knowledge_db/parsers/structured_text.py` | 254 | `JsonParser`、`YamlParser`、`TomlParser`、`XmlParser`、`IniParser` | `registry`、`tests/` | **P2** |
| `knowledge_db/parsers/web_markup.py` | 246 | `HtmlParser`、`CssParser`：HTML DOM 與 CSS 規則集解析 | `registry`、`tests/` | **P1 / P2** |
| `knowledge_db/parsers/devops.py` | 238 | `DockerfileParser`、`MakefileParser`、`CMakeParser`、`ProtoParser`、`GraphQLParser`、`SqlParser` | `registry`、`tests/` | **P2** |
| `knowledge_db/parsers/godot.py` | 229 | `GdScriptParser`、`GdShaderParser`、`GodotResourceParser` | `registry`、`tests/` | **P2** |
| `knowledge_db/parsers/shell_batch.py` | 209 | `ShellParser`、`PowerShellParser`、`BatchParser` | `registry`、`tests/` | **P2** |
| `knowledge_db/parsers/hardware_eda.py` | 208 | `VerilogParser`、`VhdlParser`、`TclSdcParser` | `registry`、`tests/` | **P2** |
| `knowledge_db/parsers/systems_emerging.py` | 192 | `GoParser`、`RustParser`、`JavaParser`、`KotlinParser`、`SwiftParser`、`ZigParser` | `registry`、`tests/` | **P2** |
| `knowledge_db/parsers/scripting_data.py` | 191 | `RubyParser`、`PhpParser`、`LuaParser`、`RParser`、`JuliaParser`、`PerlParser` | `registry`、`tests/` | **P2** |
| `knowledge_db/space.py` | 175 | `SpaceManager`：邏輯知識空間配置解析與路徑過濾 | `pipeline`、`scanner`、`tests/` | **P1** |
| `knowledge_db/tokenizer.py` | 174 | `MultilingualTokenizer`：Camel/Snake 拆解、CJK N-gram 與權重標記 | `retrieval`、`pipeline`、`tests/` | **P1** |
| `knowledge_db/config.py` | 162 | `KnowledgeDBConfig`：模組組態載入与硬體執行緒自适应計算 | `pipeline`、`engine`、`cli`、`tests/` | **P1** |
| `knowledge_db/parsers/base.py` | 131 | `LanguageParser`、`RegexBlockParser`：解析器抽象基類与正則區塊提取器 | `parsers/*` | **P2** |
| `knowledge_db/parsers/PlainText.py` | 97 | `PlainTextParser`、`CsvTsvParser`、`LogParser` | `registry`、`tests/` | **P2** |
| `knowledge_db/parsers/query_loader.py` | 65 | `load_scm_query`：Tree-sitter `.scm` 查詢檔快取載入器 | `treesitter` | Clean |
| `scripts/hook.server.py` | 34 | Server Worker 預熱與常駐服務生命週期 Hook | `server.worker` | **P1** |
| `knowledge_db/__init__.py` & `parsers/__init__.py` | 30 | 套件頂層匯出門面 | `tests/` | **P2** |

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：`Mode A` 全面破壞性收斂 + 拓撲/檢索/格式化三層去重**<br/>*(Recommended — Full Track)* | 徹底清除 23 項歷史別名、`KnowledgeEngine` 薄代理、空白 Parser 子類別與雙軌序列化分支；從 `pipeline.py` 剝離獨立之 `TopologyQueryService`；合併 `BM25Engine.search` 與 `search_aggregated` 打分核心（同步修復複合字過濾缺口）；合併 `formatter.py` 與 `scripts/cli.py` 三套拓撲查詢樣板；移除 `CallGraphIndex` 純 Python 備援圖並補齊 `VectorIndex` 原子寫入。 | 預計淨減 **900~1,200 LOC**，消除 `BM25Engine` 打分漂移與非原子寫入風險，`pipeline.py` 行數由 1,412 LOC 壓降至 ~850 LOC。 | 需同步更新 `knowledge-db/tests/` 中引用舊別名（如 `CodeTokenizer`、`LanguageRegistry`、`PythonParser`、`engine.act_callers`）的測試案例。 | ⭐⭐⭐⭐⭐ **(推薦)** |
| **方案 B：僅拆分 `pipeline.py` 內部私有方法（保留雙軌別名與舊代理）** | 不動 `KnowledgeEngine`、`schema.py`、`registry.py` 與 `BM25Engine` 雙迴圈。 | 測試修改量少。 | 雙軌序列化、16 個薄代理與 `BM25Engine` 邏輯分叉持續存在，違背 `Mode A`。 | ⭐⭐ |

### 3.1 `Mode A` 公開入口收斂、薄轉發層、相容別名與死代碼清除清冊 (`S5`)

| 編號 | 檔案與行號座標 | 冗餘轉發 / 相容別名 / 死代碼 | 調用方盤點（`kdb` 內部 / 跨模組 / `tests/`） | `Mode A` 物理清除與收斂處方 (`S5`) |
| :---: | :--- | :--- | :--- | :--- |
| **M-01** | `knowledge_db/tokenizer.py:97-112, 173` | `CodeTokenizer = MultilingualTokenizer` 類別別名；`is_cjk(self, char)` 與 `split_identifier(self, text)` 0 調用實例包裝方法 | 生產代碼 **0 callers**；僅 `tests/test_tokenizer_retrieval.py` 引用 `CodeTokenizer` | 物理刪除 `CodeTokenizer` 別名與 `is_cjk`/`split_identifier` 包裝方法；測試統一改用 `MultilingualTokenizer`。 |
| **M-02** | `knowledge_db/parsers/registry.py:20-133, 219-225, 295`<br/>`parsers/__init__.py` | `LanguageRegistry = ParserRegistry` 別名；5 個僅覆寫 `_default_lang` 的空白子類別（`PythonParser`, `MarkdownParser`, `CppParser`, `CSharpParser`, `JsTsParser`）；0 調用之 `get_language_configs()` 與 `is_supported_file()` | 生產代碼 **0 callers**；僅 `tests/test_parsers.py` 實例化舊子類別 | 物理刪除 `LanguageRegistry`、5 個空殼子類別與 2 個 0 調用方法；`ParserRegistry` 直接以 `TreeSitterDriver(lang=...)` 註冊，測試改透過 `ParserRegistry().get_parser_for_file()` 取用。 |
| **M-03** | `knowledge_db/space.py:170-174` | `SpaceManager.get_union_spaces` 與 `list_spaces` 完全等價之單行轉發 | `pipeline.py`、`scanner.py`、`bundler.py` | 收斂為單一正統方法 `list_spaces()`，物理刪除 `get_union_spaces()` 並更新內部調用點。 |
| **M-04** | `knowledge_db/scanner.py:228-253` | 標註 `Deprecated` 之 `save_fingerprints` 與 `load_fingerprints` 舊版單檔指紋讀寫方法 | 生產代碼已被 `save_space_fingerprints` / `load_space_fingerprints` 取代 | 物理刪除 `save_fingerprints` 與 `load_fingerprints`，更新 `test_space_scanner.py` 測試正統空間級 API。 |
| **M-05** | `knowledge_db/config.py:35, 46, 81, 131-133, 155-161` | `KnowledgeDBConfig.load(workspace_root=None)` 未使用參數、`self.root_path` 死屬性、`_find_workspace_root()` 死方法、`resolve_jit_vector_timeout()` 1 行轉發，以及 `L81` 引用舊別名 `core.config.Config` | `pipeline.py`、`engine.py`、`cli.py`、`tests/` | 物理刪除 `workspace_root` 參數、`root_path`、`_find_workspace_root` 與 `resolve_jit_vector_timeout`；`L81` 改用正統 `ConfigManager`。 |
| **M-06** | `knowledge_db/retrieval.py:36, 333-340, 400-423, 471-475` | `InvertedIndex.symbols_map` 雙向別名 property、`build_unified` 薄轉發方法，以及 `Posting.__init__(field_lengths=...)` 與 `from_dict` 舊版 JSON 字典相容分支 | `pipeline.py:678`、`tests/` | 物理刪除 `symbols_map` property（統一用 `.symbols`）、刪除 `build_unified`（統一用 `.build`）、移除 `Posting` 舊版 `field_lengths` 處理。 |
| **M-07** | `knowledge_db/schema.py:150-291, 331-376, 444-455` | `UnifiedSymbol` 雙重欄位序列化（同時寫入 `"children"` 與 `"members"`、同時讀寫 `"space"` 與 `"spaces"`）；`AggregatedFileResult` 偽裝為 `SearchResult` 的 6 個相容 property（`symbol`/`score`/`space`/`matched_terms`/`snippet`/`code_snippet`）；0 調用之 `WeightedToken` | 全模組序列化與 `formatter.py` | `UnifiedSymbol.to_dict/from_dict` 僅保留正統 `"children"` 與 `"spaces"`；刪除 `AggregatedFileResult` 6 個相容 property 與 `WeightedToken`。 |
| **M-08** | `knowledge_db/engine.py:125-191, 211-221, 283-286, 332, 379-445`<br/>`knowledge_db/pipeline.py:1260-1265` | `KnowledgeEngine` 16 個單行代理 property/method（`space_manager`/`scanner`/`registry` 等）、`act_callers`/`act_callees`/`act_impact` 雙重方法、回傳字典重複鍵 `"caller_symbol"`、`get_status()` 重複鍵 `fingerprint_cached_files`/`index_cached`、未使用參數 `bundle(pretty=...)` 與 `status(space_name=...)` | `scripts/cli.py`、`tests/` | 物理刪除 16 個內部組件代理、刪除 `act_*` 重複命名（統一保留 `callers`/`callees`/`impact`）、移除重複字典鍵與未使用參數。 |
| **M-09** | `knowledge_db/pipeline.py:48-74, 643-653, 671-676, 685` | `HotPatchResult(int)` 繼承 `int` 與 `.patched` 別名 property；`_load_persisted_index_if_valid` 內清理舊版 `*.index.json` / `fingerprints.json` 與 `version not in ("2.0", "2.1")` 之歷史遷移分支 | `pipeline.py`、`tests/` | 將 `HotPatchResult` 改為標準 `@dataclass`（僅保留 `.patched_count`），物理刪除舊版檔案清理與 `"2.0"` 版本分支。 |
| **M-10** | `knowledge_db/graph.py:245, 250`<br/>`parsers/treesitter.py:150`<br/>`embedding.py:109-115, 456-472, 483, 497`<br/>`bundler.py:123-125, 419-432`<br/>`scripts/hook.server.py:14-33` | `graph.patch_incremental` 未使用參數 `dirty_file_paths`/`dirty_prefix`；`treesitter._extract_preceding_comment` 未使用參數 `content_lines`；`embedding` 0 調用之 `list_supported_models`/`compute_similarity`/`_doc_id_to_idx`；`bundler` 0 調用之 `clear_symbols_cache` 與重複包裝 `import_bundle`；`hook.server.py` 舊版 `on_worker_warming` 包裝 | **0 callers**（或僅測試舊入口） | 物理刪除上述所有未使用參數、死屬性与 0 調用包裝函式。 |

---

### 3.2 五維度靜態診斷問題單 (`D1~D5` × `P0/P1/P2`)

| 編號 | 維度 | 嚴重度 | 座標 (`file:line`) | 病徵描述與根因剖析 | 對應重構策略 |
| :---: | :---: | :---: | :--- | :--- | :---: |
| **F-01** | **D1 / D2** | **P0** | `knowledge_db/pipeline.py:1-1412` | **`pipeline.py` (1,412 LOC) 六職責耦合上帝類別**：單一檔案混雜索引建置、增量熱修補（`_hot_patch_unified_index_locked` 212 LOC，巢狀 7 層）、混合檢索（`search` 303 LOC）、調用圖拓撲分析（`callers`/`callees`/`impact` ~350 LOC）、狀態統計與背景服務。 | **S1 + S2**（剝離 `topology_query.py` 並拆解長方法） |
| **F-02** | **D3** | **P0** | `knowledge_db/retrieval.py:648-940` | **`BM25Engine.search` 與 `search_aggregated` ~95 行打分迴圈分叉導致過濾不一致**：兩方法重複實作查詢分詞、IDF 計算、Posting 走訪與欄位加權；`search` (`L715-727`) 實作了「$\ge 3$ sub-tokens 複合字 50% 覆蓋率門檻」，但 `search_aggregated` (`L840-868`) 漏掉了該檢查，造成聚合模式出現噪音召回。 | **S1 + S3**（抽取共用 `_score_matching_documents` 核心） |
| **F-03** | **D3** | **P0** | `knowledge_db/formatter.py:553-982`<br/>`scripts/cli.py:349-652` | **`callers` / `callees` / `impact` 在 CLI 層與 Formatter 層雙重三倍複製**：`scripts/cli.py` 的 `cmd_callers`/`cmd_callees`/`cmd_impact`（~300 LOC）重複實作參數解析、空查詢報錯與格式分派；`formatter.py` 的 `format_callers`/`format_callees`/`format_impact`（~430 LOC）重複實作候選消歧提示、節點標題與遞迴樹繪製。 | **S1 + S3**（合併為參數化通用拓撲命令與樹狀渲染器） |
| **F-04** | **D4** | **P0** | `knowledge_db/embedding.py:220-225, 581-594` | **向量索引與 ONNX 模型下載缺乏原子寫入保護 (`Scoped Resource Lifecycle`)**：`VectorIndex.save_binary` 直接 `gzip.open(index_path, "wb")` 寫入目標檔，`download_model` 直接 `urllib.request.urlretrieve` 寫入目標路徑；若中途斷電或中斷將留下損毀的半成品檔案（而 `retrieval.py` 與 `graph.py` 均有使用 `.tmp + os.replace`）。 | **S4**（統一抽取 `atomic_write_gzip_pickle` 與下載 `.tmp + os.replace`） |
| **F-05** | **D3** | **P1** | `knowledge_db/scanner.py:85-226` | **`FingerprintScanner` 三套重複的目錄走訪迴圈**：`scan_directory`、`scan_spaces` 與 `get_dirty_files` 各自手寫 `os.walk`、忽略目錄過濾、副檔名檢查与 `os.stat` 異常處理。 | **S2 + S3**（抽取 `_iter_eligible_files` 生成器） |
| **F-06** | **D2 / D3** | **P1** | `knowledge_db/graph.py:350-629` | **`CallGraphIndex` 冗餘維護雙套有向圖結構 (`nx.DiGraph` + 純 Python 字典)**：`manifest.json` 已強制依賴 `networkx>=3.0`，但 `CallGraphIndex` 仍維持 `_HAS_NX` 分支並同步寫入 `_out_edges`/`_in_edges` 與手寫 BFS。 | **S5**（移除純 Python 備援圖，100% 採用 `nx.DiGraph`） |
| **F-07** | **D3** | **P1** | `retrieval.py:425-498`、`graph.py:552-628`、`embedding.py:581-635`、`bundler.py:258-340` | **4 處重複實作 Gzip+Pickle 二進制序列化與反序列化樣板**：4 個模組各自實作 `gzip.open`、`pickle.dump/load` 與 `.tmp` 替換。 | **S3**（抽取共用 `io_utils.py` 原語） |
| **F-08** | **D2 / D3** | **P1** | `knowledge_db/config.py:135-153`<br/>`knowledge_db/embedding.py:55-98, 229-260` | **執行緒數計算與模型預設值在 `config.py` 與 `embedding.py` 重複定義**：`resolve_worker_threads` 在兩檔各自讀取 `os.cpu_count()` 與環境變數；模型預設名稱與 Repo 映射亦分散於兩處。 | **S3 + S5**（統一以 `config.py` 為單一真理來源） |
| **F-09** | **D1 / D3** | **P1** | `parsers/treesitter.py:194-414`、`parsers/spice.py:83-298`、`parsers/web_markup.py:25-245`、`graph.py:98-219` | **解析器與符號連結器單體長函式**：`TreeSitterDriver.extract_symbols` (220 LOC)、`SpiceParser.extract_symbols` (215 LOC)、`TopologyLinker.resolve_call_site` (122 LOC) 控制流深層巢狀。 | **S1 + S2**（詳見 §3.3） |

---

### 3.3 `S1` 業務階段邏輯聚合與 `S2` 無狀態邏輯剝離藍圖（7 大核心檔案）

#### 1. `knowledge_db/pipeline.py` (1,412 LOC $\to$ 預估 ~820 LOC) + 新模組 `knowledge_db/topology_query.py` (~320 LOC)
* **`S2` 職責剝離 (`TopologyQueryService`)**：
  - 將 `pipeline.py` 尾部 ~350 行之調用圖查詢邏輯（`_resolve_target_symbols`、`callers`、`callees`、`impact`、BFS 風險分級與內部/外部影響邊界統計）完整剝離至獨立模組 `knowledge_db/topology_query.py`。
* **`S1` 業務階段拆解**：
  - `_hot_patch_unified_index_locked`（原 `L419-630`，212 LOC）$\to$ 拆為 `_collect_all_dirty_files`、`_evict_dirty_file_artifacts`、`_reparse_and_relink_dirty_files`、`_persist_patched_indices` 四階段。
  - `search`（原 `L765-1067`，303 LOC）$\to$ 拆為 `_prepare_search_context_and_filters`、`_execute_lexical_and_vector_retrieval`、`_enrich_snippets_and_expand_ast` 三階段，並將 `_infer_symbol_role`、`_symbol_matches_filters`、`_expand_symbol_code` 剝離為無狀態純函式。

#### 2. `knowledge_db/retrieval.py` (`BM25Engine`, 941 LOC $\to$ 預估 ~740 LOC)
* **`S1 + S3` 打分核心合一**：
  - 抽取 `_score_candidate_documents(self, query_tokens, space_filter, file_type_filter, role_filter) -> Tuple[Dict[str, float], Dict[str, Set[str]], List[str]]`：統一執行 IDF 預計算、Posting 走訪、欄位加權與「$\ge 3$ sub-tokens 50% 覆蓋率門檻過濾」。
  - `search` 與 `search_aggregated` 均調用 `_score_candidate_documents` 取得候選分數表，再分別執行單一符號排序或依 `file_path` 聚合，徹底消除 ~95 行重複迴圈並修復聚合模式過濾缺口。

#### 3. `knowledge_db/formatter.py` (1,057 LOC $\to$ 預估 ~680 LOC) & `scripts/cli.py` (928 LOC $\to$ 預估 ~640 LOC)
* **`S1 + S3` 拓撲查詢與渲染去重**：
  - `formatter.py`：抽取通用樹狀拓撲渲染器 `_format_topology_tree(result, direction, ...)`，將 `format_callers`、`format_callees`、`format_impact` 的 430 行重複代碼收斂為參數化分派。
  - `scripts/cli.py`：抽取通用 `_run_topology_cli_command(args_or_bags, mode: Literal["callers", "callees", "impact"])`，消除 `cmd_callers`、`cmd_callees`、`cmd_impact` 三處 ~300 行重複樣板。

#### 4. `knowledge_db/embedding.py` (636 LOC) & `knowledge_db/graph.py` (629 LOC)
* **`S3 + S4 + S5` 原子 I/O 與圖譜純化**：
  - 抽取 `atomic_save_gzip_pickle(path, payload)` 與 `load_gzip_pickle(path)` 共用原語，修復 `VectorIndex.save_binary` 非原子寫入，`download_model` 改為寫入 `.onnx.tmp` 後 `os.replace`。
  - `graph.py:CallGraphIndex` 移除 `_HAS_NX` 備援分支與 `_out_edges`/`_in_edges` 字典，統一使用 `nx.DiGraph`；`TopologyLinker.resolve_call_site` (122 LOC) 拆為 `_resolve_self_or_cls_call`、`_resolve_imported_module_call`、`_resolve_same_file_or_global_call`。

#### 5. `knowledge_db/scanner.py` (288 LOC) & `knowledge_db/parsers/*`
* **`S1 + S2 + S3` 走訪與解析器拆解**：
  - `scanner.py`：抽取 `_iter_eligible_files(root_dir, include_exts, exclude_dirs)` 生成器，讓 `scan_directory`、`scan_spaces`、`get_dirty_files` 共用單一目錄走訪邏輯。
  - `treesitter.py:extract_symbols` (220 LOC) 拆為 `_run_definition_captures`、`_build_symbol_nodes_from_captures`、`_assemble_parent_child_hierarchy`；`spice.py:extract_symbols` (215 LOC) 將行續接預處理與 `.subckt`/元件狀態機拆分為獨立輔助函式。

---

## 3. 結論 (Conclusion)

- **推薦落地策略**：
  - 採納 **方案 A（`Mode A` 全面破壞性收斂 + 拓撲/檢索/格式化三層去重）**，於後續啟動實作時將本子計畫 `sub_04_knowledge_db_code_optimization` 原地升級為 **標準開發計畫 (`Full Track`, `P01~P07`)**。
  - **預估量化收益**：
    1. 物理清除 **23 項歷史別名、空白 Parser 子類別、`KnowledgeEngine` 16 個薄代理、雙重 JSON 欄位與舊版遷移分支**，並消除 `BM25Engine`、`formatter.py`、`scripts/cli.py`、`scanner.py` 與 `CallGraphIndex` 的重複實作，預計淨減 **950~1,200 LOC**。
    2. 修復 `BM25Engine.search_aggregated` 缺失複合字 50% 覆蓋率過濾之演算法漂移，以及 `VectorIndex.save_binary` / `download_model` 非原子寫入風險。
    3. 將 `pipeline.py` 由 **1,412 LOC** 壓降至 **~820 LOC**，建立職責清晰的 `TopologyQueryService`。
- **後續行動與 P00 銜接（Step 3 三大流轉出口）**：
  1. **出口 ① 立即/後續升級實作（推薦）**：將 `R01_code_optimization_audit.md` 標記為 `Concluded`，並於 `sub_04_knowledge_db_code_optimization` 原地追加 `P01~P07` 升級為 `Full Track` 實作計畫。
  2. **出口 ② 轉入長期技術儲備**：轉入 `/roadmap` 或 `/todo` 分批排程。
  3. **出口 ③ 結案存檔**：僅保留調研診斷報告備查。
