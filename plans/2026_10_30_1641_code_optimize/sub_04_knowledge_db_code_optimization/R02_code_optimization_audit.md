# 技術調研報告：knowledge-db 模組五維度業務代碼靜態診斷與重構處方 (R02_code_optimization_audit.md)

> 調研主題：knowledge-db 模組業務代碼五維度靜態診斷與無損重構處方  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  `ys_codebase/source/knowledge-db/` 作為 YS-Codebase 的知識庫與語意檢索核心模組（共 27 個業務 Python 檔案、約 6,830 行業務代碼，不含 `tests/`），承載多語言 Tree-sitter / Custom AST 符號提取、二進位增量指紋掃描（`YFP1`）、BM25 + FastEmbed ONNX 混合 RRF 檢索、NetworkX 雙向調用圖譜消歧與 CLI / Watcher 守護服務。隨著功能演進，模組內浮現多處結構性技術債：
  1. **巨型與高耦合檔案（God Files / Classes）**：[`pipeline.py`](../../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py)（1,101 行）、[`formatter.py`](../../../ys_codebase/source/knowledge-db/knowledge_db/formatter.py)（930 行）、[`retrieval.py`](../../../ys_codebase/source/knowledge-db/knowledge_db/retrieval.py)（759 行）、[`cli.py`](../../../ys_codebase/source/knowledge-db/scripts/cli.py)（735 行）及 [`treesitter.py`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/treesitter.py)（690 行）行數龐大，單一檔案混雜多條正交職責軸線。
  2. **跨層次與跨檔案重複邏輯（DRY Violations）**：執行緒預算解析與模型正規化在 `config.py` 與 `embedding.py` 重複定義；`contributes` 雙軌加載與 URI 路徑解算在 `space.py`、`parsers/registry.py`、`formatter.py`、`retrieval.py` 與 `bundler.py` 各自實作；路徑正規化比對與副檔名清洗散落於 4 個以上模組；`HybridSearchEngine` 與 `IndexingPipeline` 存在完全無調用之分支與雙重過濾；`CssParser` 與 `HtmlParser` 重複定義 `_make_symbol` 與多行註解累積狀態機。
  3. **Mode A 過渡期相容別名與死代碼殘留**：存在多處薄轉發包裝函式（Pass-through Wrappers）、未使用的參數與欄位（如 `context_lines`、`MODEL_SPECS`、廢棄 `staging_dir` 殘留變數），以及 `KnowledgeDBConfig.resolve_threads()` 將實例方法誤當類別方法呼叫的潛在契約缺陷。
- **調研目標**：
  遵循 [`code-optimizer`](../../../.agents/skills/code-optimizer/SKILL.md) 規範，在 **檢視範圍：`Module Scope`（`ys_codebase/source/knowledge-db/`，排除 `tests/`）** 與 **生命週期模式：`Mode A`（收斂期 / 允許破壞性清理）** 定錨基準下，執行 `D1~D5` 五維度微觀與中觀靜態診斷，盤點單一正統入口收斂清單與調用點座標，並制定 `S1~S6` 行為無損重構處方箋。

### 1.1 定錨基準與範圍摘要 (Anchoring Baseline & Scope Summary)

| 定錨維度 | 設定值 | 說明与約束邊界 |
| :--- | :--- | :--- |
| **檢視範圍 (Scope)** | `Module Scope` | `ys_codebase/source/knowledge-db/` 全部非測試業務代碼（`knowledge_db/*.py`、`knowledge_db/parsers/*.py`、`scripts/*.py`，共 27 檔 / 約 6,830 LOC）。 |
| **生命週期模式 (Lifecycle)** | `Mode A：收斂期 (Convergence Mode)` | 強制單一正統入口（Single Canonical Entry），零容忍物理刪除相容別名、薄轉發層、過渡分支與死代碼，並同步更新所有內部/測試調用點。 |
| **對外契約與插件註冊點** | `contributes/*.json` & `manifest.json` | 1. CLI 路由：`scripts/cli.py`（`status`, `index`, `search`, `callers`, `callees`, `impact`, `clean`, `model`）<br>2. Server 服務與 Hook：`knowledge_db.service:KnowledgeDBServiceWorker`、`scripts/hook.server.py:on_worker_warming`<br>3. Dev Hook：`scripts/hook.dev.py:on_test_setup / on_test_teardown`<br>4. Workflow Computed Token：`knowledge_db.providers:get_knowledge_db_spaces`<br>5. 語言解析插件：`knowledge_db.parsers.{spice_parser:SpiceParser, html_parser:HtmlParser, css_parser:CssParser}`<br>6. 模組門面與公開匯出：`knowledge_db/__init__.py`、`knowledge_db.engine:KnowledgeEngine / get_engine` |
| **既有測試套件保護網** | `tests/test_*.py` (12 檔) | `test_bundler.py`, `test_cli.py`, `test_engine.py`, `test_graph.py`, `test_hot_reload.py`, `test_parsers.py`, `test_retrieval.py`, `test_scanner.py`, `test_schema.py`, `test_selector.py`, `test_service_worker.py`, `test_space.py`（驗收命令：`python yscb.py dev test knowledge-db`）。 |

---

## 2. 候選方案分析與對比 (Candidate Evaluation)

針對 `knowledge-db` 模組在 `Mode A` 下的結構收斂與重構深度，評估以下三種候選方案：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：僅執行表層死代碼與別名清理 (`S2` 局部 + `Mode A` 別名移除)** | 僅刪除未使用的相容別名、死常數與冗餘參數，不拆解 `formatter.py`、`cli.py`、`treesitter.py` 等長方法，亦不拆離大檔案。 | 修改行數極少（`< 150` 行），風險最低。 | 無法解決 `format_search_output`（290 行 6 分支重複）、`cli.py:search`（213 行）、`pipeline.py`（1,101 行）等核心結構腐化與高認知複雜度問題。 | ⭐⭐ |
| **方案 B：全模組 `S1~S6` 外科手術式無損重構（推薦）** | 1. 依 `Mode A` 物理拔除所有轉發別名與死分支，收斂為單一正統入口。<br>2. 對 `formatter.py`、`cli.py`、`treesitter.py`、`linker.py`、`embedding.py` 執行 `S1` 業務階段拆解、`S2` 無狀態純函式剝離、`S3` 同構樣板聚合、`S4` 衛語句與表驅動分派、`S5` 資料團塊封裝。<br>3. 對 `pipeline.py` 與 `retrieval.py` 執行適度 `S6` 職責解耦（或提取共用路徑/過濾基礎設施），維持 `knowledge_db/__init__.py` 正統匯出。 | 徹底消除 `P0/P1/P2` 病灶，大幅降低單檔與單函式行數及圈複雜度，修復 `resolve_threads` 靜態調用 Bug，且不引入過度設計的抽象階層。 | 變更規模約 500~800 行，涵蓋模組內十餘個業務檔案，需升級為 **Full Track** 計畫嚴密驗證。 | ⭐⭐⭐⭐⭐ |
| **方案 C：激進重寫與設計模式教條化（Abstract Factory / Visitor 重塑）** | 將所有 Parser、Formatter 與 Indexer 全面改寫為多層 Abstract Factory、Strategy Pattern 與 Visitor 類別階層，並將每個檔案細拆為 20+ 個微型檔案。 | 形式上符合極端物件導向教條。 | 嚴重違反 `code-optimizer` 防過度設計紅線 ②（禁止教條式套用設計模式）與紅線 ③（禁止碎紙機式過度拆分），大幅增加跨檔跳轉成本與序列化相容風險。 | ⭐ |

---

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 契約邊界與 `Mode A` 單一正統入口收斂查驗表 (Contract & Entry Convergence Table)

依據 `Mode A（收斂期 / 允許破壞性清理）` 規則，以下盤點模組內所有重複定義、相容別名、薄轉發包裝器、孤兒死代碼與廢棄參數，並列出需同步改寫之調用方座標（`Callers to Update`）：

| 類別 | 目標符號与檔案座標 | 現況病徵與冗餘原因 | `Mode A` 單一正統入口處置方案 | 需同步改寫之生產代碼調用方座標 (`Callers to Update`) |
| :---: | :--- | :--- | :--- | :--- |
| **Bug + 重複入口** | [`config.py:L40-L64`](../../../ys_codebase/source/knowledge-db/knowledge_db/config.py#L40-L64) `resolve_threads()`<br>[`config.py:L83-L109`](../../../ys_codebase/source/knowledge-db/knowledge_db/config.py#L83-L109) `KnowledgeDBConfig.resolve_threads()` / `resolve_max_threads()`<br>[`embedding.py:L30-L32`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L30-L32) `resolve_max_threads()` | 1. **實例方法誤作類別方法調用 Bug**：`embedding.py:L32` 執行 `KnowledgeDBConfig.resolve_threads(max_threads)`（未實例化），導致 `max_threads` 被綁定為 `self`，進而在 `config.py:L85` 存取 `self.max_threads` 時若 `explicit_threads` 為 `None` 會拋出 `AttributeError: 'NoneType' object has no attribute 'max_threads'` 或將字串當成 `self`！<br>2. 同一執行緒計算邏輯在 `config.py:L40-L64` 與 `config.py:L83-L105` 重複實作兩遍，且存在 `resolve_threads`、`resolve_max_threads` 等 4 個入口。 | 1. 將 `config.py:resolve_threads(explicit_threads=None)` 定為**唯一正統純函式**。<br>2. `KnowledgeDBConfig.resolve_threads(self, explicit_threads=None)` 內部直接委派 `resolve_threads(explicit_threads if explicit_threads is not None else self.max_threads)`。<br>3. **物理刪除** `KnowledgeDBConfig.resolve_max_threads()` 與 `embedding.py:resolve_max_threads()`。 | • [`embedding.py:L149`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L149)<br>• [`embedding.py:L235`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L235)<br>*(改為直接調用 `config.resolve_threads(self.max_threads)`)* |
| **薄轉發別名** | [`config.py:L79-L81`](../../../ys_codebase/source/knowledge-db/knowledge_db/config.py#L79-L81) `KnowledgeDBConfig.normalize_model_name()`<br>[`embedding.py:L45-L47`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L45-L47) `EmbeddingService.normalize_model_name()` | `config.py:L32` 已有模組級純函式 `normalize_model_name(name)`，但 `KnowledgeDBConfig` 與 `EmbeddingService` 又各自封裝一層 `@staticmethod` / `@classmethod` 薄轉發別名。 | 保留 [`config.py:L32`](../../../ys_codebase/source/knowledge-db/knowledge_db/config.py#L32) `normalize_model_name()` 為唯一正統純函式，**物理刪除** `KnowledgeDBConfig.normalize_model_name` 與 `EmbeddingService.normalize_model_name`（或僅保留 `config.normalize_model_name`）。 | • [`embedding.py:L57`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L57)<br>• [`embedding.py:L157`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L157)<br>• [`embedding.py:L216`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L216) |
| **薄轉發別名** | [`parsers/registry.py:L138-L140`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/registry.py#L138-L140) `ParserRegistry.get_parser_for_file()` | 100% 純轉發 `return self.get_parser(file_path)`，全生產代碼 `0` 調用。 | **物理刪除** `get_parser_for_file()`，統一使用 `ParserRegistry.get_parser()`。 | 生產代碼 `0` 調用（若有測試調用則同步更新至 `get_parser`）。 |
| **薄轉發別名** | [`pipeline.py:L1068-L1074`](../../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py#L1068-L1074) `IndexingPipeline.find_target_symbol()` | 100% 純轉發至 `self.topology_query.find_target_symbol()`，且 `KnowledgeEngine` 並未暴露此方法，生產代碼 `0` 調用。 | **物理刪除** `IndexingPipeline.find_target_symbol()`，直接以 `pipeline.topology_query.find_target_symbol()` 為單一正統入口。 | 生產代碼 `0` 調用（同步檢查並更新測試調用點）。 |
| **死分支 (Unreachable Branch)** | [`hybrid.py:L115-L140`](../../../ys_codebase/source/knowledge-db/knowledge_db/hybrid.py#L115-L140) `if hasattr(self.inverted_index, "search"):` | `InvertedIndex` 類別根本**沒有** `search()` 方法（檢索由 `BM25Engine.search()` 執行）！此處 `L115-L140` 共 26 行屬於歷史遺留的死代碼分支，每次執行都只會走 `L141` 的 `elif self.bm25_engine is not None:`。 | **物理刪除** `hybrid.py:L115-L140` 死分支，統一由 `self.bm25_engine.search()` 執行詞彙檢索。 | 內部無損收斂，外部 `0` 影響。 |
| **孤兒死代碼 / 常數** | [`config.py:L16-L23`](../../../ys_codebase/source/knowledge-db/knowledge_db/config.py#L16-L23) `MODEL_SPECS`<br>[`embedding.py:L27`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L27) `DEFAULT_MODEL_NAME`<br>[`embedding.py:L154, L183-L184`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L154) `staging_dir` | 1. `config.py:MODEL_SPECS` 定義後全模組 `0` 引用（`EmbeddingService._resolve_dimension_mock` 卻在 `L95-L104` 用字串硬編碼 `if "large" in name: 1024...`）。<br>2. `DEFAULT_MODEL_NAME` 為 `DEFAULT_EMBEDDING_MODEL` 的無意義別名。<br>3. `embedding.py:L154` 宣告 `staging_dir` 卻從未傳給 `TextEmbedding`（直接傳了 `self.cache_dir`），僅在 `except` 中 `rmtree(staging_dir)`，屬半成品殘留死代碼。 | 1. 於 `_resolve_dimension_mock` 實際對接 `MODEL_SPECS`（或刪除冗餘硬編碼分支）。<br>2. 刪除 `DEFAULT_MODEL_NAME` 別名，統一使用 `DEFAULT_EMBEDDING_MODEL`。<br>3. 清理未使用的 `staging_dir` 死變數。 | [`embedding.py:L27, L49, L154, L183-L184, L231`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L27) |
| **未使用之死參數 / 屬性** | [`engine.py:L295`](../../../ys_codebase/source/knowledge-db/knowledge_db/engine.py#L295) & [`pipeline.py:L1023`](../../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py#L1023) `context_lines: int = 3`<br>[`engine.py:L348`](../../../ys_codebase/source/knowledge-db/knowledge_db/engine.py#L348) `pre_warm(cls, workspace_root=None)`<br>[`linker.py:L27, L30`](../../../ys_codebase/source/knowledge-db/knowledge_db/linker.py#L27-L30) `tokenizer` | 1. `engine.search()` 與 `pipeline.search()` 接收 `context_lines: int = 3`，但在 `pipeline.py:L1033-L1059` 中**完全未使用**（`_enrich_snippets_and_expand_ast` 硬編碼 `context_before=2, context_after=8`）。<br>2. `KnowledgeEngine.pre_warm(cls, workspace_root=None)` 接收 `workspace_root` 卻完全忽略。<br>3. `TopologyLinker.__init__` 接收並實例化 `self.tokenizer = tokenizer or MultilingualTokenizer()`，但全類別 `456` 行中**從未讀取 `self.tokenizer`**。 | 1. `Mode A` 下移除未使用的 `TopologyLinker.tokenizer` 參數與實例化（消除無謂物件建立開銷）。<br>2. 針對 `search(..., context_lines)`：將 `context_lines` 實際傳遞至 `_enrich_snippets_and_expand_ast`（或依 `Mode A` 移除死參數）。<br>3. 移除 `pre_warm` 未使用之 `workspace_root` 參數。 | • [`pipeline.py:L274-L277, L429-L432`](../../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py#L274-L277)<br>• [`engine.py:L295, L309, L348`](../../../ys_codebase/source/knowledge-db/knowledge_db/engine.py#L295) |
| **向後相容過渡殘留** | [`schema.py:L154-L163`](../../../ys_codebase/source/knowledge-db/knowledge_db/schema.py#L154-L163) `UnifiedSymbol.members` vs `children`<br>[`schema.py:L183-L186, L264-L267`](../../../ys_codebase/source/knowledge-db/knowledge_db/schema.py#L183-L186) `metadata["space"]` 單數相容轉換 | 1. `UnifiedSymbol` 同時存在 `children: Tuple[Any, ...]` 與 `members: Tuple[Any, ...]` 兩個完全鏡像的欄位，並靠 `__post_init__` 執行 `object.__setattr__` 雙向同步，造成每個符號物件雙倍 Tuple 參照。<br>2. `SpiceParser` 仍在 `metadata` 寫入舊版單數 `"space": space`（`spice_parser.py:L242, L325, L358, L379, L399, L445, L476`），迫使 `UnifiedSymbol.to_dict/from_dict` 保留 `metadata.pop("space")` 過渡轉換。 | 1. 清理 `SpiceParser` 中所有 `"space": space` 冗餘鍵，統一只寫 `"spaces": [space]`。<br>2. 收斂 `UnifiedSymbol` 的 `children` / `members`（或將 `members` 改為唯讀 `@property def members(self): return self.children`，徹底消滅雙重欄位儲存與 `__post_init__` 反射開銷）。 | • [`spice_parser.py:L242, L325, L358, L379, L399, L445, L476`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/spice_parser.py#L242)<br>• [`treesitter.py:L391, L395, L455-L456`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/treesitter.py#L391) |

---

### 3.2 `D1 ~ D5` 五維度分級診斷矩陣 (Five-Dimension Diagnostic Matrix)

以下依 [`diagnostic-matrix.md`](../../../.agents/skills/code-optimizer/references/diagnostic-matrix.md) 判準，逐維度列出 `ys_codebase/source/knowledge-db/` 全模組之結構病灶座標與嚴重度分級（共計 **P0：3 項**、**P1：12 項**、**P2：5 項**）：

#### 維度 `D1`：職責內聚與抽象層級 (Cohesion & Abstraction Levels)

| 編號 | 檔案路徑與行號座標 | 嚴重度 | 具體結構病徵描述 | 建議策略 |
| :---: | :--- | :---: | :--- | :---: |
| **D1-01** | [`knowledge_db/pipeline.py:L1-L1101`](../../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py#L1-L1101) | **P0** | **巨型檔案與多重正交職責混雜 (God File / Class, 1,101 LOC)**：`IndexingPipeline` 同時承擔：① 全域進程級快取與 mtime 同步（`_GLOBAL_INDEX_CACHE`, `_ensure_indices_loaded`）、② 全量索引與向量建置（`_build_unified_index_locked`）、③ 4 階段增量熱修補與 10 符號動態探針熔斷（`L354-L633`）、④ Watcher 進程存活探測（`_is_watcher_active`）、⑤ 3 階段混合檢索與聚合編排（`L812-L1060`）。且 `L860-L942` 的混合檢索聚合邏輯與 `BM25Engine.search_aggregated`（`retrieval.py:L689-L759`）高度重疊。 | `S1`, `S2`, `S6` |
| **D1-02** | [`knowledge_db/formatter.py:L316-L607`](../../../ys_codebase/source/knowledge-db/knowledge_db/formatter.py#L316-L607) | **P0** | **呈現層巨型檔案與單一方法嚴重違反 SLAP (930 LOC / 單方法 292 LOC)**：`ResultFormatter.format_search_output` 單一函式長達 292 行，內部將「自適應分數斷層過濾」、「8,000 字元動態預算控制」、「`UniversalRedundancyFilter` 切片純化」與「`is_md (True/False) × mode (simple/detail/auto)` 共 6 種格式化字串拼接分支」全部塞在同一迴圈內；且 `_get_workspace_root`、`normalize_workspace_path`、`to_file_uri` 屬於路徑基礎設施，卻綁定在呈現層類別上。 | `S1`, `S2`, `S3`, `S4` |
| **D1-03** | [`scripts/cli.py:L234-L445`](../../../ys_codebase/source/knowledge-db/scripts/cli.py#L234-L445) & [`L516-L682`](../../../ys_codebase/source/knowledge-db/scripts/cli.py#L516-L682) | **P1** | **CLI 控制器混雜業務轉換、JSON Schema 組裝與重複例外守門 (735 LOC)**：`search()` 長達 212 行，內嵌 `_cap_json_snippet` 巢狀函式（`L292-L326`）、手動解析 `tier/limit/json/md`（`L253-L283`，卻未複用下方 `L448` 已抽出的 `_parse_common_display_options`！），並以 75 行巢狀 Dict Comprehension 組裝 3 種 Tier 的 JSON；`_run_topology_cli_command()` 亦長達 167 行。此外，`status`、`index`、`model_status`、`model_download`、`search`、`_run_topology_cli_command`、`clean` 共 **7 個頂層函式重複編寫完全相同的 `guard_dispatch` + `_setup_stream_encodings` + `try...except (SpaceNotFoundError, KnowledgeDBError, Exception)` 樣板**。 | `S1`, `S3` |
| **D1-04** | [`knowledge_db/retrieval.py:L1-L759`](../../../ys_codebase/source/knowledge-db/knowledge_db/retrieval.py#L1-L759) | **P1** | **單檔塞入 3 個正交領域模型 (759 LOC)**：`retrieval.py` 同時塞入：① 原始碼實體檔案切片讀取器（`CodeSnippet` + `SnippetExtractor`，`L70-L279`，依賴 VFS 與 `space_manager`）、② 倒排索引資料結構與增量修補器（`Posting` + `InvertedIndex`，`L22-L56`, `L310-L516`）、③ BM25 評分與檔案聚合演算法（`BM25Engine`，`L518-L759`）。 | `S2`, `S6` |
| **D1-05** | [`knowledge_db/parsers/treesitter.py:L144-L690`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/treesitter.py#L144-L690) | **P1** | **通用 AST 驅動混雜大量無狀態正則解析與語言特判 (690 LOC)**：`TreeSitterDriver` 內部包含大量完全不讀寫 `self._parser / self._query` 的無狀態純運算方法：`_extract_base_types`（`L161`）、`_fallback_markdown`（`L431`）、`extract_call_sites` 中的 Markdown 正則解析分支（`L474-L510`）與 `extract_imports`（`L591-L690`，100 行純 Regex 分派，涵蓋 `markdown`, `python`, `js/ts`, `c/cpp`, `c_sharp`，完全未使用 Tree-sitter！）。 | `S1`, `S2`, `S4` |
| **D1-06** | [`knowledge_db/linker.py:L170-L413`](../../../ys_codebase/source/knowledge-db/knowledge_db/linker.py#L170-L413) & [`knowledge_db/topology_query.py:L68-L126`](../../../ys_codebase/source/knowledge-db/knowledge_db/topology_query.py#L68-L126) | **P1** | **假性實例方法與類別繼承圖邏輯重複**：`TopologyLinker._pick_best_by_import_path`（`L357`）與 `_score_candidates`（`L368`）完全不讀取 `self`，屬於純無狀態評分函式；此外 `TopologyQueryService.expand_contract_symbol_ids`（`topology_query.py:L86-L113`）在每次查詢 `callers/impact` 時全表掃描 `idx.symbols` 重建 `class_bases` 與 BFS 繼承鏈，與 `TopologyLinker._reindex` / `_get_ancestor_classes`（`linker.py:L69-L74, L128-L141`）邏輯重複。 | `S1`, `S2`, `S3` |

#### 維度 `D2`：調用耦合與拓撲健康度 (Coupling & Topology Hygiene)

| 編號 | 檔案路徑與行號座標 | 嚴重度 | 具體結構病徵描述 | 建議策略 |
| :---: | :--- | :---: | :--- | :---: |
| **D2-01** | [`knowledge_db/embedding.py:L30-L32`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L30-L32) $\to$ [`knowledge_db/config.py:L83-L105`](../../../ys_codebase/source/knowledge-db/knowledge_db/config.py#L83-L105) | **P0** | **跨檔錯誤調用契約與重複轉發層**：`embedding.py:L32` 的 `resolve_max_threads(max_threads)` 執行 `return KnowledgeDBConfig.resolve_threads(max_threads)`，但 `KnowledgeDBConfig.resolve_threads(self, explicit_threads=None)` 是**實例方法（非 `@staticmethod` / `@classmethod`）**！當呼叫 `resolve_max_threads("auto")` 時，`"auto"` 被當作 `self` 傳入，`explicit_threads` 為 `None`，隨即在 `config.py:L85` 執行 `self.max_threads` 觸發 `AttributeError: 'str' object has no attribute 'max_threads'`（此處在 `download_model` 與 `_init_model` 中必現崩潰或退化！）。同時 `config.py:L40` 已存在模組級 `resolve_threads()` 卻未被 `embedding.py` 調用。 | `S2`, `S3` |
| **D2-02** | [`knowledge_db/engine.py:L93`](../../../ys_codebase/source/knowledge-db/knowledge_db/engine.py#L93) $\to$ [`knowledge_db/formatter.py:L238`](../../../ys_codebase/source/knowledge-db/knowledge_db/formatter.py#L238) | **P1** | **跨物件私有方法耦合與基礎設施倒置**：`KnowledgeEngine.__init__` 為了初始化检索層的 `SnippetExtractor`，竟然跨層呼叫呈現層 `self.formatter._get_workspace_root()` 私有方法（`engine.py:L93`），導致資料檢索層反向依賴 UI 格式化器來獲取 Workspace 根目錄。 | `S2`, `S6` |
| **D2-03** | [`knowledge_db/hybrid.py:L115-L140`](../../../ys_codebase/source/knowledge-db/knowledge_db/hybrid.py#L115-L140)、[`parsers/registry.py:L138`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/registry.py#L138)、[`pipeline.py:L1068`](../../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py#L1068)、[`config.py:L16, L79, L106`](../../../ys_codebase/source/knowledge-db/knowledge_db/config.py#L16) | **P1** | **Mode A 死代碼與冗餘別名殘留**：如 §3.1 契約查驗表所列，`HybridSearchEngine.search` 內含 26 行對不存在之 `InvertedIndex.search` 的死分支；`ParserRegistry.get_parser_for_file`、`IndexingPipeline.find_target_symbol`、`KnowledgeDBConfig.resolve_max_threads`、`EmbeddingService.normalize_model_name` 均為多餘轉發層；`TopologyLinker.tokenizer` 與 `staging_dir` 為無效死狀態。 | `S2` |

#### 維度 `D3`：控制流與認知複雜度 (Control Flow & Cognitive Complexity)

| 編號 | 檔案路徑與行號座標 | 嚴重度 | 具體結構病徵描述 | 建議策略 |
| :---: | :--- | :---: | :--- | :---: |
| **D3-01** | [`knowledge_db/formatter.py:L394-L590`](../../../ys_codebase/source/knowledge-db/knowledge_db/formatter.py#L394-L590) & [`L682-L760`](../../../ys_codebase/source/knowledge-db/knowledge_db/formatter.py#L682-L760) | **P1** | **6 路對稱分支重複與 6 層深層巢狀 (Arrow Anti-pattern)**：在 `format_search_output` 中，`is_md`（Markdown vs Text）× `mode`（`simple` / `detail` / `auto`）展開為 6 個龐大分支，每個分支內部都重複執行完全相同的 `self.redundancy_filter.purify_lines(...)`、行號範圍計算 `line_range` 與代碼區塊行號格式化迴圈，最大縮排深度達 **6~7 層**；`_format_topology_tree`（`L682-L760`）亦有同樣的 4 路重複渲染骨架。 | `S1`, `S3`, `S4` |
| **D3-02** | [`knowledge_db/linker.py:L245-L333`](../../../ys_codebase/source/knowledge-db/knowledge_db/linker.py#L245-L333) | **P1** | **Tier 3 與 Tier 4 消歧邏輯高度鏡像重複與 6 層巢狀**：`_resolve_same_file_or_global_call`（89 行）中，針對 `space_name` 空間內匹配（`L256-L298`）與全域 `self._by_name` 匹配（`L302-L332`）重複編寫了幾乎完全相同的「`prefix.callee` 匹配 $\to$ `prefix_tail.callee` 退回 $\to$ `imports` 交集過濾 $\to$ 單一候選直接返回 / 多候選 `_score_candidates`」控制流，縮排深度達 **6 層**。 | `S1`, `S3`, `S4` |
| **D3-03** | [`knowledge_db/parsers/css_parser.py:L65-L218`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/css_parser.py#L65-L218) & [`html_parser.py:L83-L205`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/html_parser.py#L83-L205) | **P1** | **跨解析器同構迴圈與重複 `_make_symbol` 工廠**：`CssParser` 與 `HtmlParser` 各自複製了一份 31 行完全相同的 `_make_symbol(...)` 輔助函式；且兩者的 `parse()` 均採用「多行註解狀態機（`/*...*/` / `<!--...-->`）$\to$ 4~6 個線性 Regex `if match: symbols.append(_make_symbol(...)); comments = []; continue`」的冗長 `if` 鏈，極易收斂為共用基礎輔助與表驅動規則分派。 | `S3`, `S4` |
| **D3-04** | [`knowledge_db/bundler.py:L228-L262`](../../../ys_codebase/source/knowledge-db/knowledge_db/bundler.py#L228-L262)、[`L375-L450`](../../../ys_codebase/source/knowledge-db/knowledge_db/bundler.py#L375-L450) | **P1** | **並行/串行結果收集迴圈與全量/增量調用點提取重複**：1. `bundle_union` 中 `use_parallel`（`L234-L244`）與 `not use_parallel`（`L250-L261`）的結果消費、進度回呼、錯誤日誌與 `UnifiedSymbol.from_dict` 迴圈 100% 重複。<br>2. `extract_all_call_sites_and_imports`（`L375-L404`）與 `extract_dirty_call_sites_and_imports`（`L406-L450`）除了一個 `dirty_keys_norm` 過濾條件外，其餘 30 行讀檔與調用 `parser_registry.extract_call_sites / extract_imports` 邏輯完全重複。 | `S3` |
| **D3-05** | [`knowledge_db/scanner.py:L452-L469`](../../../ys_codebase/source/knowledge-db/knowledge_db/retrieval.py#L452-L469)、[`pipeline.py:L386-L400`](../../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py#L386-L400)、[`bundler.py:L420-L431`](../../../ys_codebase/source/knowledge-db/knowledge_db/bundler.py#L420-L431) | **P1** | **跨 3 檔重複實作「變更檔案路徑模糊匹配」與「副檔名正規化」**：1. `InvertedIndex.patch_incremental`（`retrieval.py:L452-L468`）、`IndexingPipeline._evict_dirty_file_artifacts`（`pipeline.py:L386-L400`）與 `SemanticBundler.extract_dirty_call_sites_and_imports`（`bundler.py:L420-L431`）三處重複手寫 `sym_path_norm == p or p.endswith("/" + sym_path_norm) or sym_path_norm.endswith("/" + p)` 路徑比對。<br>2. 副檔名正規化邏輯在 `TopologyQueryService.normalize_ftypes`（`topology_query.py:L33`）、`BM25Engine._normalize_ftypes`（`retrieval.py:L546`）與 `HybridSearchEngine.search`（`hybrid.py:L99-L110`）重複實作三遍。 | `S2`, `S3` |

#### 維度 `D4`：介面契約與資源生命週期 (Contracts & Resource Lifecycle)

| 編號 | 檔案路徑與行號座標 | 嚴重度 | 具體結構病徵描述 | 建議策略 |
| :---: | :--- | :---: | :--- | :---: |
| **D4-01** | [`knowledge_db/embedding.py:L370-L395`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L370-L395) | **P1** | **回傳型別隨參數變異之不一致契約 (`embed_texts_probe -> Any`)**：`EmbeddingService.embed_texts_probe` 若傳入 `total_count` 回傳二元組 `(probe_vectors, est_total)`，若未傳入則回傳三元組 `(probe_vectors, elapsed, unit_sec)`，導致型別標註被迫退化為 `Any`，違反穩定介面契約原則。檢查全空間僅 `pipeline.py:L532` 一處調用（且必傳 `total_count=num_symbols`）。 | `S5` |
| **D4-02** | [`knowledge_db/parsers/treesitter.py:L183-L400`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/treesitter.py#L183-L400) | **P1** | **跨階段傳遞無型別約束之鬆散裸字典 (`List[Dict[str, Any]]`)**：`TreeSitterDriver` 的三階段管線（`_extract_raw_definition_items` $\to$ `_build_symbol_hierarchy` $\to$ `_materialize_unified_symbols`）以包含 14 個鍵值（`short_name`, `kind`, `start_byte`, `end_byte`, `node`, `scope_path`, `children_items` 等）的可變裸 `dict` 跨方法傳遞並原地變異狀態，缺乏結構化型別保護。 | `S5` |
| **D4-03** | [`knowledge_db/pipeline.py:L112-L124, L846-L905`](../../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py#L846-L905) | **P2** | **長參數列與跨物件狀態臨時改寫**：`_prepare_search_context_and_filters` 與 `_execute_lexical_and_vector_retrieval` 參數多達 10 個；且在每次 `search()` 時動態篡改 `self.hybrid_engine.inverted_index = unified_index`（`L862, L891`），以及在 `IndexingPipeline` 上以可變旗標 `self._vector_degraded` 傳遞單次熱修補狀態。 | `S5` |

#### 維度 `D5`：架構邊界與專案慣例 (Architectural Idioms)

| 編號 | 檔案路徑與行號座標 | 嚴重度 | 具體結構病徵描述 | 建議策略 |
| :---: | :--- | :---: | :--- | :---: |
| **D5-01** | [`knowledge_db/bundler.py:L344-L360`](../../../ys_codebase/source/knowledge-db/knowledge_db/bundler.py#L344-L360) & [`knowledge_db/scanner.py:L78-L93`](../../../ys_codebase/source/knowledge-db/knowledge_db/scanner.py#L78-L93) | **P1** | **原子檔案寫入重複造輪子且未統一走 `io_utils` / `core.vfs`**：`SemanticBundler.export_bundle`（`bundler.py:L344-L360`）完全手寫 `tempfile.mkstemp` + `os.fdopen` + `os.replace` 並未優先調用 `core.vfs`；`BinarySnapshotManager.save`（`scanner.py:L78-L93`）亦手寫了一套 `mkstemp` fallback，而 `io_utils.py` 則是直接調用 `core.vfs.write_bytes`。應統一收斂原子寫入基礎設施於 `io_utils.py`。 | `S3`, `S5` |
| **D5-02** | [`knowledge_db/space.py:L90-L131`](../../../ys_codebase/source/knowledge-db/knowledge_db/space.py#L90-L131) & [`knowledge_db/parsers/registry.py:L36-L68`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/registry.py#L36-L68) | **P2** | **Contributes 雙軌降級載入樣板重複**：`SpaceManager._load_contributes` 與 `ParserRegistry._load_from_contributes` 各自重複實作了「① 優先使用 `contributes_data` 參數 $\to$ ② `from core import contributes; contributes.get('knowledge-db')` $\to$ ③ 降級讀取 `Path(__file__).../contributes/knowledge-db.json`」的三階載入邏輯。 | `S3` |
| **D5-03** | [`knowledge_db/config.py:L165-L200`](../../../ys_codebase/source/knowledge-db/knowledge_db/config.py#L165-L200)、[`space.py:L16-L28`](../../../ys_codebase/source/knowledge-db/knowledge_db/space.py#L16-L28)、[`formatter.py:L238-L256`](../../../ys_codebase/source/knowledge-db/knowledge_db/formatter.py#L238-L256)、[`retrieval.py:L168-L203`](../../../ys_codebase/source/knowledge-db/knowledge_db/retrieval.py#L168-L203)、[`bundler.py:L120-L141`](../../../ys_codebase/source/knowledge-db/knowledge_db/bundler.py#L120-L141) | **P2** | **Core URI 解算與 Workspace Root 探測散落 5 處且調用不一致**：`config.py:L194` 呼叫 `from core.uri import resolve_uri`（而 `core.uri` 標準 API 為 `resolve`，導致 `config.py` 的 `_resolve_config_uri` 永遠走 `except` 靜默失敗！）；同時 `space.py`、`formatter.py`、`retrieval.py`、`bundler.py` 各自手寫 `try: from core import uri; uri.resolve("project://") ...` 的安全包裝。 | `S2`, `S3` |
| **D5-04** | [`knowledge_db/pipeline.py:L895, L913, L928`](../../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py#L895) & [`retrieval.py:L675, L711`](../../../ys_codebase/source/knowledge-db/knowledge_db/retrieval.py#L675) | **P2** | **散落之魔術常數 (Magic Literals)**：摘要截斷長度 `120`、每檔聚合上限 `3`、聚合衰減係數 `alpha = 0.2`、候選放大倍率 `max(limit * 3, 30)`、向量探針數量 `10` 等常數散落於 `pipeline.py`、`retrieval.py` 與 `hybrid.py` 迴圈內部，未提取為模組頂層具名常數。 | `S5` |

---

### 3.3 `S1 ~ S6` 外科手術重構處方箋 (Refactoring Blueprint)

針對上述 `D1~D5` 病灶，遵循四大防過度設計紅線（100% 行為與錯誤語意等價、禁止設計模式狂熱、禁止奈米函式、自我解釋命名），制定以下六大重構處方：

#### 處方 1：修復跨檔靜態調用缺陷並徹底執行 `Mode A` 單一入口清理 (`D2-01`, `D2-03`, `D4-01`)
1. **`config.py` & `embedding.py` 執行緒與模型名稱單一正統入口（`S2` + `S3`）**：
   - 於 [`config.py`](../../../ys_codebase/source/knowledge-db/knowledge_db/config.py) 將 `resolve_threads(explicit_threads, fallback_threads)` 定為唯一純函式實作；`KnowledgeDBConfig.resolve_threads(self, explicit_threads=None)` 僅用 1 行委派該純函式。
   - **物理刪除** `KnowledgeDBConfig.resolve_max_threads()`、`KnowledgeDBConfig.normalize_model_name()`、`EmbeddingService.normalize_model_name()`、`embedding.py:resolve_max_threads()` 與 `DEFAULT_MODEL_NAME`。
   - 修復 `config.py:L194` `_resolve_config_uri` 誤用 `from core.uri import resolve_uri` 之 Bug，改為正統 `from core.uri import resolve`。
   - 將 `EmbeddingService._resolve_dimension_mock` 對接 `config.MODEL_SPECS`，消除重複硬編碼；清理 `download_model` 中未使用的 `staging_dir` 變數；將 `embed_texts_probe` 簽名固定回傳 `Tuple[np.ndarray, float]`（移除未使用的無 `total_count` 三元組分支）。
   - 於 [`EmbeddingService._init_model`](../../../ys_codebase/source/knowledge-db/knowledge_db/embedding.py#L193-L276) 執行 `S1` 拆解：抽離 `_record_unavailable_and_notify(error_type, message)` 與 `_resolve_supported_model_name(TextEmbedding)`，消除模型未找到與加載失敗兩處重複的 `last_error` 組裝與 `[GUARD]` stderr 通知。
2. **拔除全模組冗餘轉發層與死分支（`Mode A`）**：
   - **物理刪除** [`hybrid.py:L115-L140`](../../../ys_codebase/source/knowledge-db/knowledge_db/hybrid.py#L115-L140) 針對 `hasattr(self.inverted_index, "search")` 的 26 行死分支，直接透過 `self.bm25_engine.search()` 取回詞彙候選。
   - **物理刪除** [`parsers/registry.py:L138`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/registry.py#L138) `get_parser_for_file()` 與 [`pipeline.py:L1068`](../../../ys_codebase/source/knowledge-db/knowledge_db/pipeline.py#L1068) `find_target_symbol()`。
   - 移除 [`linker.py:L27`](../../../ys_codebase/source/knowledge-db/knowledge_db/linker.py#L27) `TopologyLinker.__init__` 未使用的 `tokenizer` 參數與屬性。
   - 將 [`schema.py`](../../../ys_codebase/source/knowledge-db/knowledge_db/schema.py) 與 [`spice_parser.py`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/spice_parser.py) 中舊版單數 `metadata["space"]` 全面收斂為 `metadata["spaces"]`。

#### 處方 2：收斂底層路徑、URI、副檔名與原子 I/O 基礎設施 (`D2-02`, `D3-05`, `D5-01`, `D5-02`, `D5-03`)
於 [`io_utils.py`](../../../ys_codebase/source/knowledge-db/knowledge_db/io_utils.py)（或擴充為模組內部共用基礎工具）集中收斂 5 項跨檔重複的純函式與 I/O 原語（`S2` + `S3`）：
1. **`safe_resolve_uri(uri_str: str) -> Optional[Path]` 與 `get_workspace_root(explicit_root: Optional[Path] = None) -> Path`**：
   - 取代 `space.py:_safe_resolve_uri`、`config.py:_resolve_config_uri`、`formatter.py:_get_workspace_root`、`retrieval.py:SnippetExtractor.resolve_file_path` 與 `bundler.py:_get_project_relpath` 中重複的 `core.uri` try-except 區塊。
   - 解除 `engine.py:L93` 對 `self.formatter._get_workspace_root()` 的跨層私有調用耦合。
2. **`atomic_write_bytes(target_path: Path, data: bytes)` 與 `atomic_write_json(target_path: Path, payload: Any)`**：
   - 優先使用 `core.vfs.write_bytes(..., atomic=True)`，失敗時統一退回 `tempfile.mkstemp` + `os.replace`，供 `io_utils.atomic_save_gzip_pickle`、`scanner.BinarySnapshotManager.save` 與 `bundler.SemanticBundler.export_bundle` 共用，消除 3 處重複的暫存檔清理樣板。
3. **`normalize_ftypes(ftypes: Optional[Union[str, Iterable[str]]]) -> Optional[List[str]]` 與 `matches_dirty_path(sym_file_path: str, dirty_paths_norm: Set[str]) -> bool`**：
   - 統一提供副檔名正規化（供 `TopologyQueryService`、`BM25Engine`、`HybridSearchEngine` 共用）與變更檔案路徑匹配（供 `InvertedIndex.patch_incremental`、`IndexingPipeline._evict_dirty_file_artifacts`、`SemanticBundler.extract_dirty_call_sites_and_imports` 共用）。
4. **`load_module_contributes(section_key: str, custom_data: Optional[Dict], config_override_file: Optional[Path] = None) -> Dict[str, Any]`**：
   - 統一處理 `custom_data` $\to$ `core.contributes.get("knowledge-db")` $\to$ `contributes/knowledge-db.json` 三階安全載入，供 `SpaceManager` 與 `ParserRegistry` 共用。

#### 處方 3：`formatter.py` 呈現層階段拆解与 6 路重複渲染收斂 (`D1-02`, `D3-01`)
針對 [`formatter.py`](../../../ys_codebase/source/knowledge-db/knowledge_db/formatter.py)（930 行）執行 `S1` + `S3` + `S4` 重構（預計縮減 35%+ 行數）：
1. **提取自適應分數斷層過濾純函式 `_filter_results_by_score_cliff(results, limit_mode)`（`S1` / `S2`）**：將 `format_search_output` 前段 `L335-L353` 的分數斷層計算獨立為無狀態純函式。
2. **提取共用切片純化與格式化輔助方法 `_prepare_purified_snippet_lines(itm, language, max_snip_lines)` 與 `_render_snippet_block(...)`（`S3`）**：
   - 將原本在 `format_search_output` 的 6 個分支（`md/text` × `simple/detail/auto`）中重複呼叫 6 次的 `self.redundancy_filter.purify_lines(...)` 與行號寬度對齊迴圈，收斂為單一內部方法。
3. **拆解單一檔案節點渲染器 `_render_search_file_node_md(...)` 與 `_render_search_file_node_text(...)`（`S1`）**：
   - 將 `simple`、`detail`、`auto` 三種模式的共通欄位（標題行、簽名、摘要、命中詞、代碼切片）以參數化控制旗標（如 `show_score`, `show_meta`, `show_terms`）合併渲染，彻底消除 200 行的複製貼上分支，使 `format_search_output` 主幹退化為 40 行內的清晰編排器。
4. **收斂 `_format_topology_tree`（`L609-L776`）**：提取 `_render_topology_item_md` 與 `_render_topology_item_text`，將縮排深度壓回 $\le 3$ 層。

#### 處方 4：`scripts/cli.py` 命令守門裝飾器與序列化邏輯解耦 (`D1-03`)
針對 [`scripts/cli.py`](../../../ys_codebase/source/knowledge-db/scripts/cli.py)（735 行）執行 `S1` + `S3` 重構：
1. **提取統一 CLI 執行守門包裹器 `_execute_cli_action(cmd_name, cmd_bags, handler_fn)`（`S3`）**：
   - 集中處理 `guard_dispatch("knowledge-db")`、`_setup_stream_encodings()`、`_normalize_bags(cmd_bags, cmd_name)` 以及 `try ... except (SpaceNotFoundError, KnowledgeDBError, Exception)` 標準錯誤輸出與返回碼 `1`，消除 7 個 CLI 入口函式重複的樣板代碼。
2. **重構 `search()` 與 `_run_topology_cli_command()`（`S1` + `S2`）**：
   - 讓 `search()` 直接複用 `_parse_common_display_options(bags)`，消除 `L253-L283` 的重複選項解析。
   - 將內嵌於 `search()` 的 `_cap_json_snippet` 與 3 種 Tier（`detail` / `preview` / `simple`）的 JSON Payload 建構邏輯，抽離為模組級純函式 `_serialize_search_json(engine, results, query_str, tier, max_snippet_lines)` 與 `_serialize_topology_json(...)`，使 `search()` 與 `_run_topology_cli_command()` 各縮減至 45 行以內。

#### 處方 5：`pipeline.py`、`retrieval.py` 與 `hybrid.py` 檢索與聚合管線收斂 (`D1-01`, `D1-04`, `D4-03`, `D5-04`)
1. **統一檔案層級聚合演算法（消除 `pipeline.py` 與 `retrieval.py` 雙軌重複 — `S3`）**：
   - `BM25Engine.search_aggregated`（`retrieval.py:L689-L759`）與 `IndexingPipeline._execute_lexical_and_vector_retrieval`（`pipeline.py:L902-L942`）實作了兩套相同的 `Score(File) = max(S_i) + alpha * sum(S_j)` 檔案聚合邏輯。
   - 提取通用純函式 `aggregate_symbol_hits_by_file(hits, limit, alpha=0.2, top_k_per_file=3) -> List[AggregatedFileResult]` 於 `retrieval.py`，統一供純 BM25 與 Hybrid RRF 檢索結果調用，一舉刪除 `pipeline.py` 中 45 行的重複聚合迴圈。
2. **簡化 `HybridSearchEngine` 與 `IndexingPipeline` 的過濾契約（`S1` + `S5`）**：
   - 將檢索過濾條件統一封裝於既有 `QueryFilter`（`retrieval.py:L58`），避免在 `_prepare_search_context_and_filters` 與 `_execute_lexical_and_vector_retrieval` 之間重複傳遞 10 個散裝參數，並消除 `pipeline.py:L876, L909` 對 `HybridSearchEngine.search` 已過濾結果的二次冗餘 `_symbol_matches_filters` 檢查。
   - 實際連接 `search(..., context_lines)` 參數至 `_enrich_snippets_and_expand_ast`。
3. **拆解 `SemanticBundler` 重複迴圈（`D3-04` — `S3`）**：
   - 於 [`bundler.py`](../../../ys_codebase/source/knowledge-db/knowledge_db/bundler.py) 提取 `_consume_parse_results(results_iter, unique_files, total_files, progress_callback)` 統一處理並行與串行 AST 解析結果；將 `extract_all_call_sites_and_imports` 與 `extract_dirty_call_sites_and_imports` 合併為共用 `_extract_call_sites_and_imports_from_files(target_files_iter)`。

#### 處方 6：解析器群組 (`treesitter.py`, `css_parser.py`, `html_parser.py`) 與 `linker.py` 結構純化 (`D1-05`, `D1-06`, `D3-02`, `D3-03`, `D4-02`)
1. **共用自訂解析器基礎設施（`css_parser.py` & `html_parser.py` — `S3` + `S4`）**：
   - 將 `CssParser` 與 `HtmlParser` 重複的 `_make_symbol` 提升至 [`parsers/base.py`](../../../ys_codebase/source/knowledge-db/knowledge_db/parsers/base.py)（作為 `BaseParser.make_symbol` 靜態/輔助方法），並將 `CssParser` 的 6 種選擇器/變數匹配規則改為表驅動分派（Table-Driven Rules），消除重複的 `symbols.append(...); css_comments = []; continue` 樣板。
2. **`TreeSitterDriver` 內部階段結構化與無狀態 Import 提取器剝離（`D1-05`, `D4-02` — `S2` + `S5`）**：
   - 以輕量 `@dataclass class _RawSymbolNode` 取代 `treesitter.py` 內部跨階段傳遞的 14 鍵裸字典（`D4-02`）。
   - 將 `extract_imports` 中各語言的 Regex 提取規則抽離為模組級純函式與語言分派映射表 `_IMPORT_EXTRACTORS: Dict[str, Callable[[str], Dict[str, str]]]`（`S2` + `S4`），大幅降低 `TreeSitterDriver` 類別複雜度。
3. **`TopologyLinker` 與 `TopologyQueryService` 候選消歧收斂（`D1-06`, `D3-02` — `S2` + `S3`）**：
   - 將 `linker.py` 中 `_pick_best_by_import_path` 與 `_score_candidates` 剝離為無狀態純函式（`S2`）。
   - 提取 `_resolve_in_lookup_table(lookup_dict, prefix, prefix_tail, callee, imports, caller_class, norm_path)` 輔助方法（`S3`），合併 `_resolve_same_file_or_global_call` 中 Tier 3（空間字典）與 Tier 4（全域字典）重複的 80 行鏡像分支。

---

### 3.4 模組重構前後結構預估量化對照 (Projected Quantitative Delta)

| 量化指標 (Metric) | 重構前現況 (Before) | 預計重構後 (After) | 預估變化幅度 (Delta) | 結構改善說明 |
| :--- | :---: | :---: | :---: | :--- |
| **業務代碼總行數 (Total Module LOC)** | `~6,830 行` | `~6,150 行` | `~ -10.0% (-680 行)` | 消除 `formatter.py` 6 路重複、`cli.py` 7 處守門樣板、`pipeline/retrieval` 重複聚合、`hybrid.py` 死分支與跨檔重複工具 |
| **最大單一函式行數 (Max Function LOC)** | `292 行` (`format_search_output`)<br>`212 行` (`cli.search`) | `≤ 65 行` | `-77.7%` | 全面落實 `S1` 業務階段拆解與 `S3` 樣板抽離，頂層方法退化為清晰編排器 |
| **最大控制流縮排深度 (Max Nesting Depth)** | `6 ~ 7 層` (`formatter.py`, `linker.py`) | `≤ 3 層` | `-3 ~ -4 層` | 透過 `S4` 衛語句反轉與表驅動分派拉平箭頭型深層巢狀 |
| **清除之死代碼 / 轉發別名 / 潛在缺陷數** | `0` | `14 項` | `+14 項清理` | 修復 `resolve_threads` 靜態呼叫 Bug 與 `resolve_uri` 錯誤匯入，拔除全部 `Mode A` 冗餘別名與死分支 |
| **既有測試套件相容性 (12 Test Suites)** | `100% Passed` | `100% Passed` | `100% 行為無損` | 嚴守公開契約與錯誤語意 100% 等價 |

---

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **推薦落地策略**：
  採納 **方案 B（全模組 `S1~S6` 外科手術式無損重構）**，於 `Mode A（收斂期 / 允許破壞性清理）` 下分三批次有序推進：
  1. **Batch 1（底層基礎設施收斂與 `Mode A` 單一入口清理）**：優先修復 `config.py` / `embedding.py` 的 `resolve_threads` 靜態調用缺陷與 `resolve_uri` 匯入 Bug，拔除 `hybrid.py`、`registry.py`、`pipeline.py`、`linker.py`、`schema.py` 的死分支与轉發別名，並於 `io_utils.py` 收斂 URI 解算、原子寫入、副檔名正規化與髒路徑匹配純函式。
  2. **Batch 2（核心檢索、拓撲與解析引擎重構）**：執行 `pipeline.py` 與 `retrieval.py` 的檔案聚合邏輯合一（`S3`）、`bundler.py` 並行/串行與全量/增量提取收斂（`S3`）、`linker.py` Tier 3/4 消歧去重（`S3`/`S4`），以及 `treesitter.py`、`css_parser.py`、`html_parser.py` 的無狀態邏輯剝離與表驅動分派（`S2`/`S4`/`S5`）。
  3. **Batch 3（呈現層 `formatter.py` 與控制器 `scripts/cli.py` 瘦身）**：抽離 `formatter.py` 的 6 路重複渲染與切片純化迴圈（`S1`/`S3`），並以統一守門包裹器與 JSON 序列化純函式收斂 `scripts/cli.py`（`S1`/`S3`），最後執行 `python yscb.py dev check knowledge-db` 與 `python yscb.py dev test knowledge-db` 完成全量回歸驗證。
- **後續行動與流轉出口建議**：
  - **出口 ① 立即原地升級實作（強烈推薦）**：由於本子計畫涵蓋 `knowledge-db` 模組內超過 10 個業務檔案之深度結構收斂且變更行數 `> 100` 行，建議將本報告標記為 `Concluded`，並於子計畫目錄推進 **Full Track（`P01`~`P07`）** 執行無損重構與量化驗收。
  - **出口 ② 轉入技術儲備**：若當前排程優先處理其他模組，可將 `D1~D5` 病灶清冊轉入 `/roadmap` 或 `/todo` 分階段消化。
  - **出口 ③ 維持現狀結案**：不建議（因存在 `D2-01` `resolve_max_threads` 誤將實例方法作靜態呼叫及 `D5-03` `resolve_uri` 錯誤名稱匯入等實質缺陷）。
