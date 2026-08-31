# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge-db 全棧運算提速、並發 AST 打包與倒排索引記憶體瘦身  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_0533_knowledge_db_performance_and_memory_optimization  
> 狀態：Confirmed  

> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `_is_cjk_ord` | `knowledge_db/tokenizer.py` | Internal | 依據 Unicode 整數值 (`ord`) 極速判斷是否為 CJK 字元。 |
| `_split_identifier_cached` | `knowledge_db/tokenizer.py` | Internal | 具備 `@lru_cache(maxsize=8192)` 之識別碼 CamelCase/snake_case 拆解函式。 |
| `CodeTokenizer` | `knowledge_db/tokenizer.py` | Public | 代碼與文字分詞器，負責 Token 流切分與正規化。 |
| `Posting` | `knowledge_db/schema.py` | Public | 倒排索引節點資料結構，配置 `__slots__` 與緊湊欄位。 |
| `InvertedIndex` | `knowledge_db/retrieval.py` | Public | BM25 倒排索引引擎，管理頂層 `doc_lengths` 與 Max-Score 剪枝搜尋。 |
| `ThesaurusEngine` | `knowledge_db/thesaurus.py` | Public | 同義詞引擎，支援基於 Tuple 簽章的加權展開 LRU 快取。 |
| `_parse_file_task` | `knowledge_db/bundler.py` | Internal | 頂層可 Pickle 之單檔 AST 解析工作者函式。 |
| `SemanticBundler` | `knowledge_db/bundler.py` | Public | 語意空間打包器，支援動態門檻多進程並發解析。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `CodeTokenizer` (`knowledge_db/tokenizer.py`)

```python
def _is_cjk_ord(code: int) -> bool:
    """判斷 Unicode 整數 code 是否落入 CJK 與相關東亞字元區間 (零正則開銷)。"""
    return (
        (0x4E00 <= code <= 0x9FFF) or   # CJK Unified Ideographs
        (0x3400 <= code <= 0x4DBF) or   # CJK Unified Ideographs Extension A
        (0x20000 <= code <= 0x2A6DF) or # CJK Extension B
        (0xF900 <= code <= 0xFAFF) or   # CJK Compatibility Ideographs
        (0x3040 <= code <= 0x309F) or   # Hiragana
        (0x30A0 <= code <= 0x30FF) or   # Katakana
        (0xAC00 <= code <= 0xD7AF)      # Hangul Syllables
    )

@functools.lru_cache(maxsize=8192)
def _split_identifier_cached(identifier: str) -> tuple[str, ...]:
    """拆解 CamelCase 與 snake_case 識別碼為單詞元組 (LRU 快取防重複運算)。"""
    ...

class CodeTokenizer:
    @staticmethod
    def is_cjk(char: str) -> bool:
        """向後相容字元判定 (內部委任 _is_cjk_ord(ord(char)))。"""
        ...

    def split_identifier(self, identifier: str) -> list[str]:
        """拆分識別碼為單詞清單 (內部調用快取元組轉為 list)。"""
        ...

    def tokenize(self, text: str) -> list[Token]:
        """極速走訪並切分 Token 流。"""
        ...
```

---

### 2.2 `Posting` (`knowledge_db/schema.py`)

```python
class Posting:
    __slots__ = ('doc_id', 'tf', 'positions', 'field_tfs')
    
    def __init__(
        self,
        doc_id: str,
        tf: int = 1,
        positions: list[int] = None,
        field_tfs: dict[str, int] = None,
    ):
        self.doc_id: str = doc_id
        self.tf: int = tf
        self.positions: list[int] = positions or []
        self.field_tfs: dict[str, int] = field_tfs or {}
```

---

### 2.3 `InvertedIndex` (`knowledge_db/retrieval.py`)

```python
class InvertedIndex:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1: float = k1
        self.b: float = b
        self.postings: dict[str, list[Posting]] = defaultdict(list)
        self.doc_lengths: dict[str, dict[str, int]] = {} # 頂層文檔欄位長度池
        self.doc_count: int = 0
        self.field_avgdl: dict[str, float] = {}

    def search(
        self,
        query_tokens: Union[list[str], list[WeightedToken]],
        limit: int = 20,
        field_weights: Optional[dict[str, float]] = None,
    ) -> list[SearchResult]:
        """BM25 搜尋，實作 Max-Score 評分上限預估與 Top-K 早停剪枝。"""
        ...

    def patch_incremental(
        self,
        added_docs: list[tuple[str, dict[str, str], dict[str, Any]]],
        deleted_doc_ids: set[str],
    ) -> None:
        """增量打補丁更新倒排表，並同步維護頂層 self.doc_lengths。"""
        ...

    def save(self, file_path: str) -> None: ...
    
    @classmethod
    def load(cls, file_path: str) -> 'InvertedIndex':
        """載入二進位快取，具備 Schema 自省相容舊版結構能力。"""
        ...
```

---

### 2.4 `ThesaurusEngine` (`knowledge_db/thesaurus.py`)

```python
class ThesaurusEngine:
    def expand_query_weighted(self, tokens: list[str]) -> list[WeightedToken]:
        """加權展開查詢詞 (內部委任以 tuple(tokens) 為鍵之 LRU 快取)。"""
        ...
```

---

### 2.5 `SemanticBundler` (`knowledge_db/bundler.py`)

```python
def _parse_file_task(
    file_path: str,
    language_val: str,
    mod_time: float,
) -> Optional[tuple[str, list[dict[str, Any]], float]]:
    """頂層可序列化工作者函式，返回純資料 AST 符號結構。"""
    ...

class SemanticBundler:
    CONCURRENCY_THRESHOLD: int = 10 # 檔案數 >= 10 且 CPU > 1 啟用多進程
    
    def bundle_space(self, space_name: str, space_path: str, ...) -> SemanticBundle:
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Layer 1: 基礎資料結構與分詞]
  1.1 ys_codebase/source/knowledge-db/knowledge_db/tokenizer.py (_is_cjk_ord, _split_identifier_cached, CodeTokenizer)
  1.2 ys_codebase/source/knowledge-db/knowledge_db/schema.py (Posting __slots__)
        │
        ▼
[Layer 2: 核心檢索引擎與同義詞]
  2.1 ys_codebase/source/knowledge-db/knowledge_db/thesaurus.py (LRU expand_query_weighted)
  2.2 ys_codebase/source/knowledge-db/knowledge_db/retrieval.py (InvertedIndex doc_lengths, Max-Score pruning, Schema migration)
        │
        ▼
[Layer 3: 語意打包並行化]
  3.1 ys_codebase/source/knowledge-db/knowledge_db/bundler.py (_parse_file_task, dynamic threshold ProcessPool)
        │
        ▼
[Layer 4: 基準測試與品質驗收]
  4.1 ys_codebase/source/knowledge-db/tests/test_benchmark_perf_and_memory.py
```
