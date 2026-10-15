---
target: "Knowledge-DB/Retrieval"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb://source/knowledge-db/knowledge_db/retrieval.py"
  - "yscb://source/knowledge-db/knowledge_db/hybrid.py"
  - "yscb://source/knowledge-db/knowledge_db/embedding.py"
  - "yscb://source/knowledge-db/knowledge_db/formatter.py"
related_docs:
  - "./README.md"
  - "./architecture.md"
  - "./tokenizer.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-10-15"
---

# knowledge-db 倒排索引與 BM25/向量雙軌複合檢索引擎指南 (Retrieval Guide)

> 模組名稱：`knowledge-db`  
> 核心模組：`knowledge_db.retrieval`、`knowledge_db.hybrid`、`knowledge_db.embedding`、`knowledge_db.formatter`  
> 演算法：多欄位加權 Okapi BM25 + 預先過濾下推 + FastEmbed ONNX 向量 RRF 融合 + 8,000 字元動態預算衰減  

---

## 📌 1. 檢索引擎架構

`knowledge-db` 檢索引擎透過建立多欄位全域聯集倒排索引 (`InvertedIndex`) 與稠密特徵向量索引 (`VectorIndex`)，將代碼與文檔符號提取為結構化檢索表，並由 `HybridSearchEngine` 協同 `BM25Engine` 與 `EmbeddingService` 進行候選池預先過濾下推、多欄位加權評分與倒數排名融合 (RRF)。

---

## 📐 2. BM25 多欄位加權評分公式

### 2.1 欄位加權權重
| 欄位名稱 | 權重 | 說明 |
| :--- | :---: | :--- |
| **`name`** | **3.5** | 類別/函式/巨集名稱或文檔標題 (最高優先級) |
| **`signature`** | **2.0** | 函式或類別宣告簽名 (含參數與型別) |
| **`members`** | **2.0** | 類別內部公開/保護方法與成員欄位 |
| **`docstring`** | **1.5** | 文檔說明、段落內文或註解說明 |

### 2.2 詞條加權與衰減計分 (Term Weight Decay)
檢索引擎結合三階展開權重進行詞條得分計算：
$$\text{Score}(d, q) = \sum_{t \in \text{Expanded}(q)} \text{IDF}(t) \cdot \left(\sum_{f \in \text{Fields}} W_f \cdot \text{TF}_{\text{norm}}(t, d, f)\right) \cdot \text{Weight}(t)$$

其中 $\text{Weight}(t)$ 依展開來源指派：
- 原始查詢詞 (Original)：`1.0`
- 雙向同義詞 (Synonym) / 單向別名 (Alias)：`0.6`
- 領域關聯詞 (Related)：`0.25`

### 2.3 平滑 IDF 公式
為防止高頻詞出現負分數，IDF 計算採用平滑截斷：
$$\text{IDF}(q) = \ln\left(1 + \max\left(0, \frac{N - n(q) + 0.5}{n(q) + 0.5}\right)\right)$$

### 2.4 Exact Match 2.0x 置頂加權
當使用者輸入之查詢字串與符號之 `name` 完全精確一致時，加權總分額外乘上 **2.0x 置頂係數**，確保精準查詢時目標符號絕對置頂。

---

## 🛠️ 3. CLI 語意檢索指令

```bash
# 1. 全空間聯集檢索
python yscb.py knowledge-db search PIDController

# 2. 限定空間檢索
python yscb.py knowledge-db search "狀態機更新" --space=source

# 3. 複合空間與檔案類型篩選 (帶 AST 切片預覽)
python yscb.py knowledge-db search "README" --space=docs --ftype=md --json -s

# 4. 限定符號類型或程式語言
python yscb.py knowledge-db search "Controller" --kind=class --lang=cpp --limit=5
```

---

## 💻 4. Python SDK 檢索呼叫

```python
from knowledge_db.retrieval import InvertedIndex, BM25Engine, QueryFilter
from knowledge_db.tokenizer import MultilingualTokenizer
from knowledge_db.thesaurus import ThesaurusEngine

# 1. 建立倒排索引
tokenizer = MultilingualTokenizer()
index = InvertedIndex(space_name="main")
index.build(symbols, tokenizer=tokenizer)

# 2. 執行檢索
engine = BM25Engine(tokenizer=tokenizer, thesaurus=ThesaurusEngine())
flt = QueryFilter(languages=["python", "cpp"], limit=10)

results = engine.search("馬達驅動", index=index, filter_cfg=flt)
for r in results:
    print(f"[{r.score:.2f}] {r.symbol.name} ({r.symbol.file_path}:{r.symbol.line_number})")
```

---

## ⚡ 5. 符號池去重、Slots 瘦身與二進位 Gzip 快取持久化 (`.index.bin.gz`)

`knowledge-db` 倒排索引採用 **符號池解耦 (Symbol Pool Normalization)**、**`Posting` `__slots__` 節點瘦身** 與 **頂層 `doc_lengths` 共享池** 架構：

1. **`Posting` 節點輕量化**：
   - 節點配置 `__slots__ = ('doc_id', 'field_freqs', 'space', 'spaces')`，徹底消滅 Python 動態字典 `__dict__` 開銷。
   - 欄位長度字典抽離至頂層 `InvertedIndex.doc_lengths: Dict[str, Dict[str, int]]` 共享池，消除數十萬個重複字典物件（記憶體瘦身 40%+）。
2. **Schema 自省相容升級**：
   - `InvertedIndex.from_dict` 具備自動遷移能力，載入舊版二進位快取時自動將 `Posting` 內部之 `field_lengths` 提取至頂層共享池。
3. **二進位快取持久化**：
   - 使用 **原生 Pickle (Protocol 5) + Gzip (Level 1/6)** 壓縮快取，讀取載入耗時 $< 20\text{ ms}$。

```python
# 1. 保存二進位壓縮快取 (體積縮減 99.5%)
index.save_binary("path/to/unified.index.bin.gz")

# 2. 極速載入二進位快取 (載入耗時 < 20 ms，具備舊快取自省升級)
restored_index = InvertedIndex.load_binary("path/to/unified.index.bin.gz")
```

---

## 🔍 6. 代碼片段延遲提取 (`SnippetExtractor`)、8,000 字元預算衰減與全域切片去重 (`UniversalRedundancyFilter`)

為消滅 Agent 在檢索後的二次檔案讀取（Double-Look 耗時）並最大化 LLM Context 資訊密度，檢索輸出管線結合了 `SnippetExtractor`、`ResultFormatter` 動態預算衰減與 `UniversalRedundancyFilter`：

### 6.1 8,000 字元動態預算階梯衰減曲線 (Dynamic Budget Decay)
`ResultFormatter` 將單次檢索輸出總預算控制在 **8,000 字元** 上限，並依當前累計輸出字元數動態調整後續項目的切片行數上限：

| 當前累計輸出字元數 | 單一項目最大切片行數 (`max_lines`) | 階梯策略說明 |
| :--- | :---: | :--- |
| **$< 3,500$ 字元** | **30 行** | 首屏高排名命中項目保留完整 AST 邏輯上下文 |
| **$3,500 \sim 6,000$ 字元** | **$30 \to 10$ 行** | 按比例平滑線性衰減切片行數 |
| **$6,000 \sim 7,000$ 字元** | **10 行** | 維持緊湊核心定義預覽 |
| **$\ge 7,000$ 字元** | **0 行 (僅元資料)** | 關閉切片提取，僅輸出符號簽名與行號位址（嚴格保底呈現至少前 5 個命中項目） |

### 6.2 `UniversalRedundancyFilter` 全域切片去重規則
由於符號的 `signature` 與 `docstring` 已在搜尋結果標頭獨立呈現，代碼/文檔切片 (`code_snippet`) 會經由 `UniversalRedundancyFilter` 執行無損去重純化：
1. **程式碼 Docstring 剝除**：自動剔除切片內已於摘要呈現之多行文檔註解（如 Python `"""..."""`、C/C++/JS/C# `/** ... */`）。
2. **Markdown 重疊標題剔除**：針對 Markdown 切片，自動剔除與符號名稱 (`name`) 或簽名重疊之首行 `# Heading` 標題行。
3. **版權與 License 樣板過濾**：自動略過檔頭常見之 SPDX、Copyright、Apache/MIT 等制式授權聲明區塊。
4. **空白行緊湊壓縮**：將連續 2 行以上之空白行自動折疊壓縮為單一空行。
5. **目標行絕對保底**：無論過濾規則如何作用，強制保底保留符號定義起始行 (`target_line`)，絕不產生空切片。

### 6.3 `SnippetExtractor` SDK 呼叫範例
```python
from knowledge_db.retrieval import SnippetExtractor

extractor = SnippetExtractor(workspace_root="/path/to/workspace", max_lines=12)

# 安全切片提取目標符號之代碼上下文
snippet = extractor.extract(
    file_path="src/pid.cpp",
    line_number=45,
    context_before=2,
    context_after=4,
    docstring="PID 計算函式",
)

print(snippet.format_text())
# 輸出：
#    >  45 | float PIDController::Calculate(float target, float current) {
#       46 |     float error = target - current;
#       47 |     return kp * error;
#       48 | }
```

---

## ⚡ 7. 全域聯集單一索引與 JIT 智能變更感知熱自癒機制 (Unified Index & JIT Hot Healing)

`knowledge-db` 採用「全域聯集單一倒排索引 (`unified.index.bin.gz`)」與「JIT 查詢時智能變更感知與熱自癒 (Just-In-Time Smart Healing)」架構：

1. **全專案空間聯集去重 (Union Scope De-duplication)**：
   - 掃描器將所有空間之 `include`/`exclude` 規則計算為去重的實體檔案集合，每個檔案 **100% 僅解析 1 次**。
   - 單一全域倒排索引使 BM25 的 IDF 與 $avgdl$ 指標全局正規化，消除空間重疊引起的重複符號與 BM25 評分失真。
   - 符號與 Posting 自動記錄命中的多空間標籤 (`spaces: List[str]`)，支援 `--space <name>` 進行 $O(1)$ 高速空間篩選。
2. **原生二進位極速快照 (`unified.meta.bin`)**：
   - 採用 Magic `YFP1` + 原生 `struct` 封裝，反序列化延遲 $< 0.1\text{ ms}$。
   - JIT 變更嗅探只透過 `os.scandir` 取得 `(mtime, size)`，千檔規模下偵測耗時僅 $2\sim 3\text{ ms}$。
3. **無縫非侵入式熱自癒 (Non-Intrusive Hot Healing)**：
   - 查詢時若感知來源檔案新增、修改或刪除，自動執行增量差量修補 (`hot_patch_unified_index`) 並向 `stderr` 輸出提示（不污染 `--json` 結構化輸出）。
   - 當背景 `KnowledgeDBServiceWorker` 運行且 `.watcher_active` 存在（無 `.watcher_dirty`）時，前台 0ms 直接略過同步掃描，透過微秒級 `mtime` 比對熱刷新 `_GLOBAL_INDEX_CACHE`。
   - CLI 支援 `--no-auto-rebuild` / `-n` 旗標以手動停用自動熱自癒。

---

## 🔗 8. IDE 相容 Markdown 超連結與零 Fallback 快取隔離 (IDE Clickable Links & Zero Fallback)

1. **RFC 8089 IDE 超連結 (`to_file_uri`)**：
   - `knowledge-db search` 全面輸出 `[relative/path.py:L10-20](file:///absolute/path.py#L10)` 之 Markdown 格式。
   - 支援人類開發者於 VS Code / Cursor / 終端機中透過 `Ctrl + Click` 直達精確程式碼行位址。
   - 為 Agent 自動化提供 100% 確定之實體路徑，消除路徑拼接猜測。
   - `--json` 模式於每筆搜尋項目注入 `file_uri` 欄位。
2. **快取根目錄零 Fallback 守門 (Zero Fallback Guardrail)**：
   - `SpaceManager._get_storage_root()` 嚴格遵循語意協議 `cache://knowledge-db/`，禁止任何隱式退化至 CWD 之相對路徑，杜絕在專案宿主根目錄意外產生 `.cache/` 殘留目錄。

---

## 🚀 9. FastEmbed 向量嵌入與 RRF 雙軌複合檢索引擎 (`HybridSearchEngine` & RRF Fusion)

`knowledge-db` 透過 `HybridSearchEngine` 實現 BM25 關鍵字倒排與 FastEmbed ONNX 稠密向量語意雙軌倒數排名融合 (RRF) 複合檢索：

1. **多語言分詞與識別碼前處理 (`MultilingualTokenizer` & `_preprocess_text`)**：
   - `MultilingualTokenizer` 支援中英混雜無空格切分、CJK 1/2-gram 滑動窗口與駝峰/底線標識符拆解。
   - `EmbeddingService._preprocess_text` 在送入 ONNX 模型前，針對程式碼標識符自動執行駝峰與底線拆解（例如將 `CamelCase` / `snake_case` 正規化為空格分隔之小寫詞序列 `camel case` / `snake case`），完美適配 uncased BERT 分詞器，避免長標識符退化為 `[UNK]` token。
2. **FastEmbed ONNX 動態維度向量嵌入 (`EmbeddingService` & `VectorIndex`)**：
   - 預設採用 `BAAI/bge-small-zh-v1.5` 模型，透過 ONNX Runtime 進行純 CPU 離線推論；模型維度採**動態維度解析 (`model.embedding_size`)**，預設為 **512 維**（徹底廢除早期硬編碼 384 維度假設）。
   - 向量特徵二進位快取：使用 Pickle Protocol 5 + Gzip (`compresslevel=1` 低壓縮高速寫盤) 持久化至 `unified.vectors.bin.gz`。
   - 支援增量熱自癒修補 (`VectorIndex.patch_incremental`)：檔案修改或刪除時差量拔除舊特徵、追加新特徵，且模型異常時嚴格回傳 `(0, dim)` 空矩陣，**絕不生成偽造隨機向量**。
3. **BM25 候選池預先過濾下推 (Filter Push-Down)**：
   - `HybridSearchEngine.search` 將空間 (`spaces`)、符號類型 (`kinds`) 與程式語言 (`languages`) 等篩選條件，**在 RRF 融合前直接下推 (Push-Down) 至底層 `BM25Engine.search_unified` 與向量相似度計算階段**。
   - 從源頭確保候選池 100% 皆為符合目標範圍之有效符號，徹底消除後置過濾 (Post-filtering) 導致非目標空間符號擠壓 Top-K 候選名額與浪費向量運算的問題。
4. **倒數排名融合演算法 (Reciprocal Rank Fusion, RRF)**：
   - 融合公式：
     $$\text{Score}_{\text{RRF}}(d) = \frac{w_{\text{lex}}}{k + \text{rank}_{\text{lex}}(d)} + \frac{w_{\text{vec}}}{k + \text{rank}_{\text{vec}}(d)}$$
     其中預設 $k=60$，$w_{\text{lex}}=0.5$，$w_{\text{vec}}=0.5$。
5. **雙重防呆與雜訊過濾守門**：
   - **純語意門檻守門 (`min_vector_similarity = 0.70`)**：若候選項目無任何 BM25 關鍵字命中，必須達到餘弦相似度 $\ge 0.70$ 始納入召回，徹底防止小型程式碼庫因向量近鄰誤召無關程式碼。
   - **複合查詢子詞覆蓋率門檻 (`coverage >= 0.50`)**：針對長標識符未完全命中時，防範單一通用子詞誤召喚。
6. **100% 剛性平滑降級守門與 Agent 剛性防呆引導**：
   - **本地探針先行 (Probe First)**：`EmbeddingService` 於推論前先以純本機路徑檢查 `.onnx` 權重檔案，未就緒時絕不發起 Hugging Face Hub 未認證網路請求，立即平滑退回純 BM25 檢索。
   - **Agent 剛性防呆引導 (`[GUARD]`)**：當檢索降級且組態設定 `enable_vector_search: true` 時，強制於 `sys.stderr` 輸出引導：
     `[GUARD] 如果你是 AI Agent，必須立即暫停當前作業，並向開發者提問：要執行 model download 或是於 config 中關閉向量檢索？`
   - **顯式模型管理 (`model` CLI)**：提供 `model status` 查詢模型檔案與維度，`model download` 顯式下載預載權重。
   - CLI 與 SDK 支援 `--lexical-only` / `lexical_only=True` 參數，允許手動強制使用純關鍵字倒排檢索。




