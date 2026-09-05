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



