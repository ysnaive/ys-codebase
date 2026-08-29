# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_01_three_tier_weighted_expansion  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `WeightedToken` | `knowledge_db/schema.py` | Public | 表示具備權重與類型標記之查詢 Token |
| `ThesaurusConfig` | `knowledge_db/schema.py` | Public | 結構化同義詞 (thesaurus)、別名 (aliases) 與關聯詞 (related) 之組態資料模型 |
| `ThesaurusEngine` | `knowledge_db/thesaurus.py` | Public | 雙層三階加權語意擴展引擎 |
| `SpaceManager.load_thesaurus_config` | `knowledge_db/space.py` | Public | 聚合載入所有來源之結構化詞庫組態 |
| `BM25Engine.search` | `knowledge_db/retrieval.py` | Public | 支援 Token 權重衰減計算之多欄位 BM25 檢索引擎 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `WeightedToken` & `ThesaurusConfig` (`schema.py`)
```python
@dataclass
class WeightedToken:
    """查詢 Token 資料結構 (含權重與語意類別)"""
    term: str
    weight: float = 1.0
    kind: str = "original"  # "original" | "synonym" | "alias" | "related"

@dataclass
class ThesaurusConfig:
    """詞庫與關聯詞組態模型"""
    thesaurus: List[List[str]] = field(default_factory=list)
    aliases: Dict[str, List[str]] = field(default_factory=dict)
    related: List[List[str]] = field(default_factory=list)
    origin: str = "project"

    def to_dict(self) -> Dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: Any, origin: str = "project") -> "ThesaurusConfig": ...
```

### 2.2 `ThesaurusEngine` (`thesaurus.py`)
```python
class ThesaurusEngine:
    """雙層三階同義詞與關聯詞擴展引擎"""

    def __init__(
        self,
        custom_groups: Optional[List[List[str]]] = None,
        custom_aliases: Optional[Dict[str, List[str]]] = None,
        custom_related: Optional[List[List[str]]] = None,
    ):
        """
        :param custom_groups: 自訂雙向同義詞群組 (Tier 2, 0.6)
        :param custom_aliases: 自訂單向別名字典 source => [targets] (Tier 2, 0.6)
        :param custom_related: 自訂領域關聯詞群組 (Tier 3, 0.25)
        """

    def add_group(self, group: List[str]) -> None:
        """動態加入雙向等價同義詞群組"""

    def add_alias(self, source: str, targets: List[str]) -> None:
        """動態加入單向別名映射 (source => targets)"""

    def add_related_group(self, group: List[str]) -> None:
        """動態加入領域關聯詞群組"""

    def expand_query_weighted(
        self,
        tokens: List[str],
        max_expanded: int = 50,
        include_related: bool = True,
    ) -> List[WeightedToken]:
        """
        對輸入之 Token 清單進行三階加權展開與去重 (保留最高權重)。
        Tier 1 (Original, 1.0) -> Tier 2 (Synonym/Alias, 0.6) -> Tier 3 (Related, 0.25)
        """

    def expand_query(self, tokens: List[str], max_expanded: int = 50) -> List[str]:
        """向後相容介面：回傳展開後純字串 Token 清單"""
```

### 2.3 `BM25Engine.search` (`retrieval.py`)
```python
class BM25Engine:
    def search(
        self,
        query: str,
        index: InvertedIndex,
        filter_cfg: Optional[QueryFilter] = None,
    ) -> List[SearchResult]:
        """
        執行多欄位加權 BM25 語意檢索。
        計分公式：term_score = idf * field_scores_sum * token.weight
        """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
┌────────────────────────────────────────────────────────┐
│ Step 1: schema.py (WeightedToken, ThesaurusConfig)    │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Step 2: thesaurus.py (ThesaurusEngine Weighted Engine) │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Step 3: space.py (SpaceManager Thesaurus Config Load)  │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Step 4: retrieval.py (BM25Engine Weighted Search)      │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Step 5: tests/test_thesaurus_weighted.py (Unit Tests)  │
└────────────────────────────────────────────────────────┘
```
