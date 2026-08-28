# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge-db 子計畫 03: 分詞、同義詞與 BM25 語意檢索引擎 (Tokenizer, Thesaurus & BM25 Retrieval)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| **`CodeTokenizer`** | `knowledge_db/tokenizer.py` | Public | 代碼標識符與 CJK 中文 1-gram/2-gram 混合分詞器 |
| **`ThesaurusEngine`** | `knowledge_db/thesaurus.py` | Public | 雙層同義詞合併與查詢端雙向擴展器 |
| **`InvertedIndex`** | `knowledge_db/retrieval.py` | Public | 多欄位倒排索引儲存、詞頻統計與 IDF 預計算 |
| **`QueryFilter`** | `knowledge_db/retrieval.py` | Public | 空間、語言、類型、分數門檻複合過濾器 (@dataclass) |
| **`SearchResult`** | `knowledge_db/retrieval.py` | Public | 結構化語意檢索結果模型 (@dataclass) |
| **`BM25Engine`** | `knowledge_db/retrieval.py` | Public | 多欄位加權 BM25 評分與置頂檢索引擎 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 代碼與中文混合分詞器 (`knowledge_db/tokenizer.py`)

```python
class CodeTokenizer:
    """程式碼標識符與 CJK 中文混合分詞器 (Zero External Dependency)"""

    def __init__(self, stopwords: Optional[Set[str]] = None):
        """
        初始化分詞器。
        :param stopwords: 自訂停用詞集合 (若為 None 則使用內建中英文停用詞)
        """

    @classmethod
    def split_identifier(cls, identifier: str) -> List[str]:
        """
        拆解程式碼標識符 (camelCase, PascalCase, snake_case, ALL_CAPS)。
        回傳包含拆解後的子單字以及原始小寫單字。
        """

    def tokenize(self, text: str) -> List[str]:
        """
        對輸入文字進行混合分詞：
        1. 程式碼標識符提取與駝峰拆解。
        2. CJK 中文字元 1-gram 與 2-gram 窗口滑動。
        3. 停用詞過濾與小寫標準化。
        :param text: 輸入字串
        :return: 分詞後的 Token 清單
        """
```

---

### 2.2 雙層同義詞擴展引擎 (`knowledge_db/thesaurus.py`)

```python
class ThesaurusEngine:
    """雙層同義詞擴展引擎"""

    def __init__(self, custom_groups: Optional[List[List[str]]] = None):
        """
        初始化同義詞引擎。自動載入內建軟體工程詞庫，並合併 custom_groups。
        """

    def add_group(self, group: List[str]) -> None:
        """
        動態加入一組同義詞。
        :param group: 同義詞字串清單 (如 ["建立", "create", "init", "construct"])
        """

    def expand_query(self, tokens: List[str]) -> List[str]:
        """
        對輸入的查詢 Token 清單進行雙向同義詞擴展。
        :param tokens: 原始查詢 Token 清單
        :return: 包含原始詞與同義詞之去重擴展清單 (Set-based, EC-05)
        """
```

---

### 2.3 倒排索引與 BM25 檢索引擎 (`knowledge_db/retrieval.py`)

```python
@dataclass
class Posting:
    doc_id: str                                      # UnifiedSymbol.id
    symbol: UnifiedSymbol                            # 原始符號物件
    field_freqs: Dict[str, int]                      # 各欄位詞頻 {"name": 2, "signature": 1, ...}
    field_lengths: Dict[str, int]                    # 各欄位總長度 {"name": 3, "signature": 10, ...}


@dataclass(frozen=True)
class QueryFilter:
    spaces: Optional[List[str]] = None               # 限定空間清單 (None 為不限)
    languages: Optional[List[str]] = None            # 限定語言清單 (如 ["python", "cpp"])
    kinds: Optional[List[str]] = None                # 限定類型清單 (如 ["class", "function"])
    min_score: float = 0.1                           # 最低 BM25 分數門檻
    limit: int = 20                                  # 回傳數量上限


@dataclass(frozen=True)
class SearchResult:
    symbol: UnifiedSymbol
    score: float
    matched_terms: List[str]
    space: str
    snippet: str = ""


class InvertedIndex:
    """多欄位倒排索引結構"""

    def __init__(self, space_name: str = ""):
        self.space_name = space_name
        self.doc_count: int = 0
        self.index: Dict[str, List[Posting]] = {}    # Term ➔ List[Posting]
        self.symbols_map: Dict[str, UnifiedSymbol] = {}
        self.field_avgdl: Dict[str, float] = {}      # 各欄位平均長度

    def add_symbol(self, symbol: UnifiedSymbol, tokenizer: CodeTokenizer) -> None:
        """將單一 UnifiedSymbol 提取欄位加入倒排索引"""

    def build(self, symbols: List[UnifiedSymbol], tokenizer: Optional[CodeTokenizer] = None) -> None:
        """批次建立倒排索引並計算 avgdl"""

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvertedIndex": ...


class BM25Engine:
    """多欄位加權 BM25 檢索引擎"""

    DEFAULT_WEIGHTS = {
        "name": 3.5,
        "signature": 2.0,
        "members": 2.0,
        "docstring": 1.5,
    }

    def __init__(
        self,
        tokenizer: Optional[CodeTokenizer] = None,
        thesaurus: Optional[ThesaurusEngine] = None,
        field_weights: Optional[Dict[str, float]] = None,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        ...

    def search(
        self,
        query: str,
        index: InvertedIndex,
        filter_cfg: Optional[QueryFilter] = None,
    ) -> List[SearchResult]:
        """
        執行語意檢索：
        1. Query 分詞與同義詞擴展。
        2. 多欄位 BM25 評分累加。
        3. Exact Match 2.0x 置頂 Boost。
        4. 條件過濾與分數截斷排序。
        :return: 排序後之 SearchResult 清單
        """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
┌────────────────────────────────────────────────────────┐
│ Level 1: 混合分詞器 (knowledge_db/tokenizer.py)        │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 2: 雙層同義詞擴展 (knowledge_db/thesaurus.py)    │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 3: 倒排索引與 BM25 (knowledge_db/retrieval.py)   │
│ - InvertedIndex, BM25Engine, QueryFilter, SearchResult │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 4: CLI 指令擴充與模組導出                        │
│ - scripts/cli.py (search 指令)                         │
│ - manifest.json (命令宣告)                             │
│ - knowledge_db/__init__.py                             │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 5: 完整單元測試套件                              │
│ - tests/test_tokenizer.py (FT-01~02)                   │
│ - tests/test_thesaurus.py (FT-03)                      │
│ - tests/test_retrieval.py (FT-04~07, ET-01)            │
└────────────────────────────────────────────────────────┘
```
