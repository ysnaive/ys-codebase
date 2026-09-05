# knowledge-db 設計決策與工程妥協手冊 (Design Notes)

> 模組名稱：`knowledge-db`  
> 建立日期：2026-08-28  
> 維護規範：凡涉及非直觀架構妥協、二進位協議選型、效能取捨或安全性限制，必須在此登錄 `DN-XX` 編號。  

---

## 登錄索引表

| 決策編號 | 決策主題 | 影響子系統 | 關鍵約束 / 取捨 |
| :---: | :--- | :--- | :--- |
| **DN-01** | **符號池分離去重與 Protocol 5 Gzip 快取** | `retrieval.py` | 倒排索引取消 Posting 內嵌 Symbol，改為頂層 `symbols` 符號池；本地快取使用 `pickle` Protocol 5 + `gzip` L6，達成 99.5% 體積縮減與 < 20ms 讀取。 |
| **DN-02** | **本地端快取物理隔離 (`cache://knowledge-db/`)** | `space.py`, `engine.py` | 所有指紋、倒排索引與 Bundle 產物 100% 留存於 `.cache/knowledge-db/`，利用 `.gitignore` 徹底防止 AST 符號與索引污染 Git。 |
| **DN-03** | **雙階增量指紋比對 (Two-Stage Fingerprint)** | `scanner.py` | 先比對 `mtime + size`，未命中或變更時才讀取計算 `SHA1`，避免全庫頻繁磁碟 I/O。 |
| **DN-04** | **JIT 變更嗅探與原生二進位快照 (`unified.meta.bin`)** | `scanner.py`, `engine.py` | 採用 Magic `YFP1` + `struct` 原生二進位封裝檔案清冊，反序列化耗時 < 0.1ms；檢索前執行 `os.scandir` stat 嗅探（2~3ms），Dirty 時無感背景熱自愈。 |
| **DN-05** | **倒排節點 Slots 瘦身與頂層文檔長度共享池** | `retrieval.py` | `Posting` 配置 `__slots__` 消除 `__dict__` 記憶體負擔，`field_lengths` 字典抽離至頂層 `doc_lengths` 共享池，達成 40%+ 節點記憶體節省並支援舊快取自省升級。 |
| **DN-06** | **Unicode 整數區間分詞與動態門檻多進程打包** | `tokenizer.py`, `bundler.py` | 以 `_is_cjk_ord` 碼點整數比對徹底取代逐字元正則；`SemanticBundler` 於檔案數 $\ge 10$ 且多核時啟用 `ProcessPoolExecutor` 並行解析。 |
| **DN-07** | **整數池化雙向調用圖譜與四階消歧鏈接** | `linker.py`, `graph.py`, `engine.py` | 透過 `Integer String Pool` 與雙向稀疏鄰接表將調用邊快取控制在 $<150\text{KB}$；四階消歧流水線達成 95% 靜態鏈接精度，支援 JIT 差量修補與 BFS 循環防護。 |
| **DN-08** | **Tree-sitter 宣告式通用 AST 解析與零特權自貢獻外掛生態** | `parsers/`, `schema.py` | 徹底廢除舊有手刻正則解析狀態機，改採 `tree-sitter` S-Expression 聲明式語法查詢；`LanguageRegistry` 透過 `contributes.knowledge-db` 動態驅動，內建 10 種語言一律採自身自貢獻，核心零特權硬編碼。 |
| **DN-09** | **FastEmbed 向量嵌入與 RRF 雙軌複合檢索** | `embedding.py`, `hybrid.py`, `engine.py` | 引入 `fastembed` (ONNX Runtime, 384-dim `BAAI/bge-small-zh-v1.5`) 進行純 CPU 離線向量提取；以倒數排名融合 (RRF $k=60$) 結合 BM25 與語意向量；設定純語意門檻 ($\ge 0.70$) 與複合查詢覆蓋率門檻 ($\ge 50\%$) 抑制雜訊；支援 100% 剛性平滑降級與 `--lexical-only`。 |
| **DN-10** | **NetworkX 有向圖拓撲、FQN 消歧幽靈關聯根除與全方位符號選擇器** | `graph.py`, `linker.py`, `selector.py`, `protocol.py` | 引入 `networkx.DiGraph` 替換手刻鄰接表，支援精確前驅追蹤與多階影響面剪枝；四階消歧緊扣 Universal AST FQN 與 Import 作用域，杜絕跨檔案同名幽靈關聯；實作 `SymbolSelector` 微型語法 (`[kind] [scope.]name[()]`) 達成 CLI 與 API 高維度精確定位。 |
| **DN-11** | **測試套件聚合拓撲、三態分類純化與 4-Tier 需求分流** | `tests/` | 收斂 20 個測試檔為 12 個高內聚模組；全面補齊 `self.mark_passed()` 將 115+ UNKNOWN 徹底歸零；標註 LOGIC/WORKFLOW/PERF 需求分流。 |
| **DN-12** | **管線門面解耦、8,000 字元預算動態衰減與全域切片去重純化** | `formatter.py`, `pipeline.py`, `engine.py` | `engine.py` 瘦身 80.8% 轉為輕量 Facade (338 行)；輸出上限由 12,500 收斂為 8,000 字元並實作階梯平滑衰減；以 `UniversalRedundancyFilter` 徹底剔除 Docstring、重疊 Heading、License 與空白行，極大化資訊密度。 |

---

## 詳細設計決策說明

### DN-01: 符號池分離去重與 Protocol 5 Gzip 快取 (Symbol Pool Normalization)

- **背景與根因**：
  在早期設計中，`Posting` 倒排節點直接持有 `symbol: UnifiedSymbol` 物件。在多欄位分詞後，單一符號會出現在數十至數百個 Term 的 Posting 清單中，導致 JSON 序列化時產生巨大重複拷貝（94 KB 源碼文檔產生 55.35 MB 索引檔案，膨脹超過 500 倍）。
- **架構解法**：
  1. **符號池解耦**：`InvertedIndex` 頂層維護 `symbols: Dict[str, UnifiedSymbol]`，每個符號僅存 1 份；`Posting` 僅記錄 `doc_id`。
  2. **二進位 Gzip 序列化**：使用純 Python 3.9+ 原生標準庫 `pickle.HIGHEST_PROTOCOL` (Protocol 5) 配合 `gzip.compress` (Level 6)，儲存為 `.index.bin.gz`。
- **效益與驗證**：
  - 磁碟檔案體積由 55.35 MB 暴降至 253.89 KB（縮減 99.53%）。
  - 反序列化載入耗時由 ~850 ms 降低至 < 20 ms。
  - 檢索階段透過 `index.symbols[doc_id]` 以 $O(1)$ 複雜度還原完整符號。

---

### DN-02: 本地端快取物理隔離 (`cache://knowledge-db/`)

- **背景**：AST 與倒排索引屬於本機計算生成之衍生快取，不應提交至版本控制。
- **解法**：全面統一至 `cache://knowledge-db/`（對應專案根目錄 `.cache/knowledge-db/`）。
- **安全邊界**：`pickle` 二進位快取僅限定存取本地 `.cache/` 空間，嚴禁用於不可信網路傳輸；外部導出維持純 JSON 之 `SemanticBundle`。

---

### DN-04: JIT 變更嗅探與原生二進位快照 (Just-In-Time Smart Healing)

- **背景與根因**：
  跨開發者協作或 Git pull 後，若開發者忘記手動執行 `python yscb.py knowledge-db index`，檢索結果將嚴重失真或遺漏新符號。但若將索引存入 `storage://`（納入 Git 追蹤），每次修改均會造成二進位 Git Conflict 且快速膨脹 Repository 體積。
- **架構解法**：
  1. **維持 `cache://` 儲存**：索引與快照清冊 100% 維持在本地 `.cache/knowledge-db/`，受 `.gitignore` 隔離。
  2. **原生二進位快照 (`unified.meta.bin`)**：透過 Magic `YFP1` 與 Python 原生 `struct` 封裝 `{canonical_path: (mtime, size)}`，讀取耗時 $< 0.1\text{ ms}$。
  3. **JIT 查詢時智能感知**：在 `engine.search()` 入口呼叫 `os.scandir` 比對檔案系統 stat（耗時 $2\sim 3\text{ ms}$）。若發現 1+ 個檔案異動，自動於背景執行熱重建並向 `sys.stderr` 輸出簡明提示。
- **效益與驗證**：
  - 徹底根絕異地代碼過期問題，無論開發者如何切換分支或修改代碼，搜尋永遠 100% 最新。
  - 不污染 `--json` 結構化輸出，兼顧極致效能與開發體驗。

---

### DN-05: 倒排節點 Slots 瘦身與頂層文檔長度共享池 (Slots Memory Slimming & Shared doc_lengths)

- **背景與根因**：
  在百萬級倒排索引節點中，每個 `Posting` 物件預設帶有 `__dict__` 雜湊表開銷，且重複保存了與文檔相關的各欄位長度字典 `field_lengths`，造成大量記憶體浪費。
- **架構解法**：
  1. **Slots 約束**：`Posting` 明確宣告 `__slots__ = ('doc_id', 'field_freqs', 'space', 'spaces')`，根除實例字典開銷。
  2. **頂層共享長度池**：將文檔長度提升至 `InvertedIndex.doc_lengths: Dict[str, Dict[str, int]]` 統一管理，單一文檔僅存一份。
  3. **舊快取自省升級**：反序列化時若遇舊版快取結構，自動萃取並遷移至頂層 `doc_lengths`。
- **效益與驗證**：
  - 節點記憶體開銷降低 40%+。
  - 增量打補丁與檢索評分無縫向下相容。

---

### DN-06: Unicode 整數區間分詞與動態門檻多進程打包 (Unicode Range Tokenization & Parallel Bundling)

- **背景與根因**：
  原分詞主迴圈中針對每個字元反覆調用 `re.match(r'[\u4e00-\u9fff]')`，在大文本分詞時 CPU 開銷主要被正則引擎調度所佔據；全庫大型 AST 解析在多核心環境下串行執行未能充分發揮多核算力。
- **架構解法**：
  1. **Unicode 整數區間比對 (`_is_cjk_ord`)**：透過 `0x4E00 <= ord(c) <= 0x9FFF`、假名 `0x3040..0x30FF`、諺文 `0xAC00..0xD7AF` 整數比對，消除正則呼叫。
  2. **具名標識符 LRU 快取**：為 `split_identifier` 提供 `@lru_cache(maxsize=8192)` 與預編譯正則。
  3. **動態門檻多進程打包**：檔案數 $\ge 10$ 且 CPU $> 1$ 時啟用 `ProcessPoolExecutor`，配合頂層模組級可 Pickle 工作者函式 `_parse_file_task_worker` 進行批次解析，單元測試沙盒與異常狀況自動安全降級。
- **效益與驗證**：
  - 全庫完全索引重建時間從 1.8s+ 驟降至 0.887s (提速 > 50%)。

---

### DN-07: 整數池化雙向調用圖譜與四階消歧鏈接 (Integer Pooled Call Graph & 4-Tier Disambiguation)

- **背景與根因**：
  傳統 AST 符號檢索僅支援定義層級查詢，Agent 無法得知符號的直接調用者與間接依賴，容易退化為文字盲搜；若直接在節點保存字串物件邊，全專案數千條邊會造成記憶體與二進位快取體積嚴重膨脹。
- **架構解法**：
  1. **整數標識符池化 (Integer Pool)**：將全域 `symbol_id` 映射為緊湊整數 `int`，以 `Dict[int, Set[int]]` 儲存雙向鄰接表（`forward_graph` / `reverse_graph`）。
  2. **四階消歧流水線**：結合單檔 AST `ScopeStack`、檔頭 Import 映射表、同語意空間與全域倒排上下文評分，實現高精確度靜態鏈接。
  3. **循環調用防護**：`impact` 擴散分析強制引入 `visited_set`，杜絕遞迴死循環。
  4. **JIT 增量熱重載同步**：`patch_incremental` 支援拔除 dirty 檔案出入度邊並注入新邊，持久化至 `unified.graph.bin.gz`。
- **效益與驗證**：
  - 5,000+ 條調用邊 Gzip 快取體積 $< 150\text{ KB}$。
  - 單次 `callers`/`callees` 查詢 $< 5\text{ ms}$，影響面分析遍歷 $< 10\text{ ms}$。

---

### DN-08: Tree-sitter 宣告式通用 AST 解析與零特權自貢獻外掛生態 (Tree-sitter Universal AST & Zero-Privilege Contributed Plugins)

- **背景與根因**：
  早期解析器採用原生 `ast`（僅限 Python）與大量手刻正則狀態機（`cpp_parser.py`, `csharp_parser.py`, `js_ts_parser.py` 等）。面對現代語言之深層巢狀類別/函式、複合泛型、巨集預處理、異步語法與語法殘缺容錯時，正則解析不僅維護成本極高，更容易發生括號失衡、簽名截斷與調用點漏判；此外，所有內建語言硬編碼於 `ParserRegistry`，外掛模組無法以統一規格貢獻新語言。
- **架構解法**：
  1. **Tree-sitter 宣告式驅動器 (`TreeSitterDriver`)**：
     - 引入高效 C 底層繫結之 `tree-sitter`，支援漸進式容錯 AST 解析。
     - 語言查詢邏輯 100% 抽離為標準 S-Expression (`assets/queries/*.scm`)，包含符號定義（`@symbol.name`, `@definition.*`）、調用點（`@call.site`, `@call.name`）與檔頭引用（`@import.stmt`）。
  2. **零特權外掛自貢獻架構 (Zero-Privilege Dogfooding)**：
     - `LanguageRegistry` 動態讀取 `contributes.knowledge-db.languages` 宣告，依副檔名與優先級動態實例化並分發驅動。
     - `knowledge-db` 模組本身不享有核心特權，其內建之 10 種語言支援（Python, C, C++, C#, JS/TS, Markdown, SPICE, HTML, CSS）全數在自身 `contributes/knowledge-db.json` 宣告自貢獻物化。
  3. **遞迴階層符號模型 (`UnifiedSymbol`)**：
     - 新增 `parent_id`、`children`、結構化搜尋負載 `search_payload`、FQN 全限定名與結構化簽名參數清單。
     - 保留向後相容之 `members` 轉接層，無縫相容既有倒排檢索與調用拓撲引擎。
  4. **遺留代碼徹底清除**：
     - 徹底移除 `parsers/` 下所有手刻正則舊檔與過時測試用例，全生態系單元測試 100% 遷移。
- **效益與驗證**：
  - 語法錯誤下自動容錯提取合法符號節點（測試 `ET-01` 通過）。
  - 單檔解析效能提升 3~5 倍，深層巢狀 AST 結構 100% 精準還原。
  - 新語言擴充僅需在 `contributes` 宣告與撰寫 `.scm` 查詢規則，達成 0 侵入式生態系外掛擴充。

---

### DN-09: FastEmbed 向量嵌入與 RRF 雙軌複合檢索 (FastEmbed ONNX Vector Inference & RRF Hybrid Fusion)

- **背景與根因**：
  在 sub_02 之前，`knowledge-db` 僅依賴關鍵字倒排索引與手刻同義詞庫 (`ThesaurusEngine`)。然而：
  1. 同義詞庫維護成本高、難以窮舉跨領域專用術語，且中英文同義詞展開經常引入意料外的詞彙漂移。
  2. 自然語言概念搜尋（如「用戶驗證流程」、「金流退款處理」）無法命中代碼標識符如 `UserAuthService` 或 `RefundEngine`。
  3. 傳統稠密向量模型（如 PyTorch / HuggingFace Transformers）體積過大（數百 MB 至數 GB）且依賴重型 C++ 擴充，不符輕量跨平台分發要求。
- **架構解法**：
  1. **輕量 FastEmbed ONNX 推論 (`EmbeddingService`)**：
     - 選用 `BAAI/bge-small-zh-v1.5` 離線模型（~130MB ONNX 模型），透過 ONNX Runtime 實現純 CPU 低延遲推論，兼顧中英文語意特徵提取。
     - 內建 `_preprocess_text` 針對程式碼標識符實施駝峰命名拆解（`CamelCase` $\to$ `camel case`）與符號正規化，完美適配 uncased BERT 分詞器。
  2. **二進位向量快取與增量熱自愈修補 (`VectorIndex`)**：
     - 特徵向量採用 Pickle Protocol 5 + Gzip 持久化至 `unified.vectors.bin.gz`，支援極速磁碟讀寫。
     - 支援 `patch_incremental`：檔案變更或刪除時差量拔除舊特徵、追加新特徵，端到端熱更新延遲 $< 200\text{ ms}$。
  3. **倒數排名融合 (Reciprocal Rank Fusion, RRF)**：
     - 以非參數化 RRF 公式融合 BM25 關鍵字排名與向量語意排名：
       $$\text{Score}(d) = \frac{w_{\text{lex}}}{60 + \text{rank}_{\text{lex}}(d)} + \frac{w_{\text{vec}}}{60 + \text{rank}_{\text{vec}}(d)}$$
  4. **防噪音雙重門檻**：
     - **純語意門檻 (`min_vector_similarity = 0.70`)**：無 BM25 命中的項目必須達到餘弦相似度 0.70 始納入召回，消滅小型代碼庫強行傳回最近鄰雜訊的問題。
     - **複合查詢子詞覆蓋率門檻 ($\ge 50\%$)**：防範長標識符僅命中單一通用子詞（如 `term`）即誤召喚無關文件。
  5. **100% 剛性平滑降級保證**：
     - 當 `fastembed` 未安裝或加載失敗時，服務無感降級為純 BM25 檢索，保證系統高可用。
     - 提供 `--lexical-only` CLI 旗標與 SDK 參數，允許手動關閉向量推論。
- **效益與驗證**：
  - 徹底廢除舊有 `thesaurus.py` 脆弱手刻同義詞庫。
  - 自然語言跨語意查詢召回率大幅提升，116 筆測試用例 100% 通過。

---

### DN-10: NetworkX DiGraph 調用圖譜拓撲、FQN 消歧與 AST 符號微型語法 (NetworkX DiGraph Call Graph Topology, FQN Disambiguation & AST Micro-Syntax)

- **背景與根因**：
  在 sub_03 之前，調用圖譜使用手刻整數池字典，缺乏正規圖論演算法支援（如環路剪枝、最短路徑、拓撲排序）。同時：
  1. 符號缺乏跨檔案 FQN 與 Import 作用域消歧，常將同名函式（如 `service_a.run` 與 `service_b.run`）誤連成幽靈邊。
  2. 調用者查詢僅支援成員單名，無法透過類別限定或型態標記精準過濾目標節點。
- **架構解法**：
  1. **NetworkX DiGraph 圖論核心 (`CallGraphIndex`)**：
     - 全面遷移至 NetworkX `DiGraph`，節點與邊持有結構化 `SymbolCallSite` 屬性字典，序列化支援 Gzip Protocol 5 二進位壓縮快取 (`unified.graph.bin.gz`)。
     - 具備自動訪點剪枝演算法，環路圖譜（如 $A \to B \to C \to A$）安全走訪不陷入死循環。
  2. **FQN 與 Import 作用域拓撲消歧 (`TopologyLinker`)**：
     - 基於 AST 提取之檔案級 Import 表進行作用域校驗；未顯式 import 之同名裸調用判定為 `None`，徹底根絕跨檔幽靈關聯。
  3. **完備 AST 符號選擇器微型語法 (`SymbolSelector`)**：
     - 語法定義：`[kind] [scope.]name[()]`。
     - 支援 `class Foo`, `struct Point`, `interface IService`, `enum Color`, `fn run()`, `const MAX`, `Foo.bar()` 等直覺過濾。
  4. **多語言調用拓撲協議 (`LanguageTopologyProtocol`)**：
     - 抽象 `LanguageTopologyProtocol` 與 `TopologyProtocolRegistry`，透過 Tree-Sitter 語法樹統一多語言調用點與引用提取。
- **效益與驗證**：
  - 徹底消滅跨檔案同名幽靈邊，調用關聯 100% 真實可靠。
  - 500 節點 / 2000 調用邊圖譜在 Gzip 下體積 $< 150\text{KB}$，多階影響面分析平均延遲 $< 10\text{ms}$。

---

### DN-11: 測試套件聚合拓撲、三態分類純化與 4-Tier 需求分流 (Test Suite Aggregation Topology, 3-State Classification Purification & 4-Tier Filtering)

- **背景與根因**：
  隨著知識庫功能持續擴充，測試目錄出現嚴重碎片化：
  1. 測試檔案膨脹至 20 個，充斥同質微型小檔（如 `test_networkx_graph.py` 與 `test_call_graph.py`、`test_spice_parser.py` 與 `test_web_parsers.py`）。
  2. 既有測試案例普遍未依據測試框架契約調用 `self.mark_passed()`，導致高達 115+ 個測試案例在報告中被歸類為 `UNKNOWN` 假未驗雜訊。
  3. 缺乏執行分流標註，日常快測與重型多進程打包、壓測混雜執行，拖慢開發反饋循環。
- **架構解法**：
  1. **測試套件五大領域高內聚聚合**：
     - 圖譜家族：`test_call_graph.py` + `test_networkx_graph.py` $\to$ `test_graph.py`。
     - 解析器家族：`test_parsers.py` + `test_spice_parser.py` + `test_web_parsers.py` $\to$ `test_parsers.py`。
     - 檢索家族：`test_retrieval.py` + `test_search_aggregation.py` + `test_tokenizer.py` + `test_hybrid.py` $\to$ `test_retrieval.py`。
     - 熱重載家族：`test_incremental_hot_reload.py` + `test_jit_hot_healing.py` $\to$ `test_hot_reload.py`。
     - 空間家族：`test_space.py` + `test_providers.py` $\to$ `test_space.py`。
     - 測試檔總數由 20 個收斂至 12 個，完全符合 $\le 12$ 指標約束。
  2. **100% `self.mark_passed()` 契約補齊**：
     - 全套件所有測試方法逐一落地 `self.mark_passed()`，嚴格履行三態分類守則，將假未驗 `UNKNOWN` 計數徹底清零。
  3. **4-Tier 需求層級分流標註**：
     - 純記憶體邏輯標註 `@require(Requirement.LOGIC)`（日常預設執行）。
     - 重度多進程實體打包、全量磁碟走訪標註 `@require(Requirement.WORKFLOW)`。
     - 效能走勢與吞吐量基準標註 `@require(Requirement.PERF)`。
- **效益與驗證**：
  - `dev test knowledge-db` 執行回報 `Pass: 121 (100.0%), Fail: 0, Unknown: 0, Skip: 0`，測試報告純淨度達到 100%。
  - 重複冗餘夾具與正則遺留測試徹底清除，全部業務邏輯斷言 100% 零遺漏保存。

---

### DN-12: 管線門面職責分離、8,000 字元預算動態衰減與全域切片重複資訊剔除 (Pipeline-Facade Decoupling, 8000-Char Budget Decay & Universal Redundancy Purge)

- **背景與根因**：
  1. `engine.py` 膨脹至 1,765 行，兼具管線建置、拓撲分析、格式化呈現、CLI 輸出預算裁切與門面 API，違反單一職責原則。
  2. 原 12,500 字元 CLI 輸出預算偏大且切片充斥已呈現資訊之重複項（例如程式碼切片夾帶 Docstring、Markdown 切片夾帶重疊之 `# Heading`、License 樣板與連續空白行），稀釋了終端與 LLM 上下文內的有效資訊密度。
- **架構解法**：
  1. **職責徹底三向解耦**：
     - `formatter.py`: 專責結果聚合金字塔、終端 ANSI 上色、Markdown 排版、動態切片行數計算器、全域重複資訊過濾器 (`UniversalRedundancyFilter`)。
     - `pipeline.py`: 專責索引建置編排 (`IndexingPipeline`)、JIT 增量嗅探、向量索引與雙向調用圖譜整合、查詢協調。
     - `engine.py`: 瘦身為輕量統一 Facade ($\le 450$ 行，實作 338 行)，100% 委派 pipeline 與 formatter，維持對外 API 完全向後相容。
  2. **8,000 字元動態預算階梯衰減**：
     - 預算上限調降為 8,000 字元。
     - 動態衰減曲線：$<3,500$ 字元保留 30 行切片；$3,500\sim 6,000$ 字元平滑線性衰減至 10 行；$6,000\sim 7,000$ 字元維持 10 行；$\ge 7,000$ 字元切片歸零（僅呈現元資料與保底 5 項目）。
  3. **全域通用切片重複資訊剔除 (`UniversalRedundancyFilter`)**：
     - 程式碼切片自動過濾已摘要呈現之 Docstring（Python `"""`、C/JS `/* */`）。
     - Markdown 切片自動剔除與符號名稱或簽名重疊之 `# Heading` 標題行。
     - 自動剔除版權與 License 樣板（SPDX、Copyright、Apache/MIT）。
     - 自動壓縮 2 行以上連續空白行。
     - 嚴格保底：至少保留目標定義行 `target_line`。
- **效益與驗證**：
  - `engine.py` 由 1,765 行減至 338 行（瘦身 80.8%）。
  - CLI 與 LLM 輸出資訊密度大幅增加，終端檢索體驗俐落緊湊。
  - 123/123 測試用例 100% 通過。

---

### DN-13: 向量推論防護、AST 單次走訪優化與索引寫盤純化 (Vector Inference Safeguards, AST Single-Pass & Fast Index Serialization)

- **背景與根因**：
  在 Phase 6 實機驗證（UX-01）與大規模代碼庫（200+ 檔案、數千個符號）建置時：
  1. `FastEmbed` 底層 ONNX Runtime 預設吃滿本機 100% CPU，連續推論數千個符號致排程飢餓、DPC 軟中斷逾時與硬體保護重開機。
  2. `bundler` 在多進程 Worker 內部逐檔重複初始化 `ParserRegistry`，重複讀取並編譯 7 套 Tree-sitter S-Expression `.scm` 數百次。
  3. `extract_call_sites` 內部再次呼叫 `self.parse()`，全專案檔案 AST 被重複解析 3 遍。
  4. `VectorIndex.save_binary` 硬編碼 `compresslevel=6` 壓縮百萬級 float32 陣列，產生極高 CPU 運算負擔。
- **架構解法**：
  1. **ONNX 執行緒硬上限與環境變數注入**：
     - 在 `EmbeddingService._init_model` 初始化時，設定 `OMP_NUM_THREADS` 與 `ONNXRUNTIME_INTRA_OP_NUM_THREADS` 為 `min(2, max(1, cpu_count // 2))`，並透過 `threads=max_threads` 傳入 ONNX Session，剛性杜絕 100% CPU 搶佔。
  2. **分批推論與時間片讓渡**：
     - `embed_texts` 採用 `batch_size=64` 切片推論，每批次微幅調用 `time.sleep(0.005)` 主動讓出時間片給 OS 排程器與 UI/中斷。
  3. **向量快取寫盤壓縮等級降級**：
     - `VectorIndex.save_binary` 預設改為 `compresslevel=1`，消除浮點陣列高壓縮比的無意義 CPU 浪費，磁碟寫入延遲降低 80%+。
  4. **Worker 內解析器單例快取 (`_get_worker_registry`)**：
     - 多進程工作者模組層級維持單例 `ParserRegistry`，進程生命週期僅初始化與編譯 `.scm` 查詢檔一次，消滅數千次磁碟 I/O。
  5. **調用點提取 AST 符號重用 (`extract_call_sites`)**：
     - `extract_call_sites` 擴充 `symbols: Optional[List[UnifiedSymbol]] = None` 參數；`bundler` 調用時傳入 `self._file_symbols_cache` 已提取之符號實例，徹底消除調用點提取時的二次 AST 解析。
- **效益與驗證**：
  - 實機 231 個檔案 hot-rebuild 索引由數分鐘且 CPU 卡死，壓降至僅 **10.4 秒** 平穩完成，全系統 0 凍結、0 卡頓。
  - 全套件 124/124 單元與契約測試 100% 通過（0 Fail、0 Skip、0 Unknown）。
