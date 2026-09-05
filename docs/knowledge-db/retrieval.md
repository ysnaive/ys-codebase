# knowledge-db 倒排索引與 BM25 語意檢索引擎指南 (Retrieval Guide)

> 模組名稱：`knowledge-db`  
> 核心模組：`knowledge_db.retrieval`  
> 演算法：多欄位加權 Okapi BM25 + 平滑 IDF + Exact Match Boost  

---

## 📌 1. 檢索引擎架構

`knowledge-db` 檢索引擎透過建立多欄位倒排索引 (`InvertedIndex`)，將代碼與文檔符號提取為結構化倒排表，並透過 `BM25Engine` 進行多欄位加權評分與條件過濾。

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

```powershell
# 1. 全空間聯集檢索
python yscb.py knowledge-db search PIDController

# 2. 限定空間檢索
python yscb.py knowledge-db search "狀態機更新" --space=project_main

# 3. 限定符號類型或程式語言
python yscb.py knowledge-db search "Controller" --kind=class --lang=cpp --limit=5
```

---

## 💻 4. Python SDK 檢索呼叫

```python
from knowledge_db.retrieval import InvertedIndex, BM25Engine, QueryFilter
from knowledge_db.tokenizer import CodeTokenizer
from knowledge_db.thesaurus import ThesaurusEngine

# 1. 建立倒排索引
tokenizer = CodeTokenizer()
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
   - 使用 **原生 Pickle (Protocol 5) + Gzip (Level 1/6)** 壓縮快取，讀取載入耗時 < 20 ms。

```python
# 1. 保存二進位壓縮快取 (體積縮減 99.5%)
index.save_binary("path/to/space.index.bin.gz")

# 2. 極速載入二進位快取 (載入耗時 < 20 ms，具備舊快取自省升級)
restored_index = InvertedIndex.load_binary("path/to/space.index.bin.gz")
```

---

## 🔍 6. 代碼片段延遲提取器 (`SnippetExtractor`)

為消滅 Agent 在檢索後的二次檔案讀取（Double-Look 耗時），`SnippetExtractor` 支援延遲切片讀取與安全截斷：

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

## ⚡ 7. 全域聯集單一索引與 JIT 智能變更感知熱自愈機制 (Unified Index & JIT Hot Healing)

`knowledge-db@1.0.2.0` (sub_01) 引入了「全域聯集單一倒排索引 (`unified.index.bin.gz`)」與「JIT 查詢時智能變更感知與熱自愈 (Just-In-Time Smart Healing)」架構：

1. **全專案空間聯集去重 (Union Scope De-duplication)**：
   - 掃描器將所有空間之 `include`/`exclude` 規則計算為去重的實體檔案集合，每個檔案 **100% 僅解析 1 次**。
   - 單一全域倒排索引使 BM25 的 IDF 與 $avgdl$ 指標全局正規化，消除空間重疊引起的重複符號與 BM25 評分失真。
   - 符號與 Posting 自動記錄命中的多空間標籤 (`spaces: List[str]`)，支援 `--space <name>` 進行 $O(1)$ 高速空間篩選。
2. **原生二進位極速快照 (`unified.meta.bin`)**：
   - 採用 Magic `YFP1` + 原生 `struct` 封裝，反序列化延遲 $< 0.1\text{ ms}$。
   - JIT 變更嗅探只透過 `os.scandir` 取得 `(mtime, size)`，千檔規模下偵測耗時僅 $2\sim 3\text{ ms}$。
3. **無縫非侵入式熱自愈 (Non-Intrusive Hot Healing)**：
   - 查詢時若感知來源檔案新增、修改或刪除，自動於背景執行熱重建並向 `stderr` 輸出提示（不污染 `--json` 結構化輸出）。
   - CLI 支援 `--no-auto-rebuild` / `-n` 旗標以手動停用自動熱自愈。

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

## 🚀 9. FastEmbed 向量嵌入與 RRF 雙軌複合檢索引擎 (HybridSearchEngine & RRF Fusion)

`knowledge-db@1.0.3.0` (sub_02) 全面升級至 BM25 + 向量語意雙軌倒數排名融合 (RRF) 複合檢索：

1. **多語言分詞 (`MultilingualTokenizer`)**：
   - 支援中英混雜、CJK 1/2-gram 滑動窗口與駝峰/蛇形標識符拆解。
   - 解決中英無空格黏連、小數點標識符切分與停用詞過濾。
2. **FastEmbed ONNX 向量嵌入服務 (`EmbeddingService` & `VectorIndex`)**：
   - 基於 `BAAI/bge-small-zh-v1.5` 模型 (384 維度)，透過 ONNX Runtime 純 CPU 離線推論。
   - 向量特徵二進位快取：使用 Pickle Protocol 5 + Gzip 持久化至 `unified.vectors.bin.gz`。
   - 支援增量熱自愈修補 (`VectorIndex.patch_incremental`)：檔案修改或刪除時差量拔除舊特徵、追加新特徵。
3. **倒數排名融合演算法 (Reciprocal Rank Fusion, RRF)**：
   - 融合公式：
     $$\text{Score}_{\text{RRF}}(d) = \frac{w_{\text{lex}}}{k + \text{rank}_{\text{lex}}(d)} + \frac{w_{\text{vec}}}{k + \text{rank}_{\text{vec}}(d)}$$
     其中預設 $k=60$，$w_{\text{lex}}=0.5$，$w_{\text{vec}}=0.5$。
4. **雙重防呆與雜訊過濾守門**：
   - **純語意門檻守門 (`min_vector_similarity = 0.70`)**：若候選項目無任何 BM25 關鍵字命中，必須達到餘弦相似度門檻始納入召回，徹底防止小型程式碼庫因向量近鄰誤召無關程式碼。
   - **複合查詢子詞覆蓋率門檻 (`coverage >= 0.50`)**：針對長標識符未完全命中時，防範單一通用子詞誤召喚。
5. **100% 剛性平滑降級守門**：
   - 若 `fastembed` 套件未安裝或模型加載失敗，系統無死鎖平滑退化為純 BM25 檢索。
   - CLI 與 SDK 支援 `--lexical-only` / `lexical_only=True` 參數，允許手動強制作為純關鍵字倒排檢索。




