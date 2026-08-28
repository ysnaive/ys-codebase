# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge-db 子計畫 05: 符號池去重與二進位 Gzip 倒排索引快取優化 (Symbol Pool Normalization & Binary Gzip Inverted Index Cache Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 類別 / 方法名稱 | 所屬模組檔案 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| **`Posting`** | `knowledge_db/retrieval.py` | Public | 輕量倒排節點（僅持有 `doc_id` 引用，不內嵌 symbol） |
| **`InvertedIndex`** | `knowledge_db/retrieval.py` | Public | 符號池與倒排索引核心資料結構 |
| **`InvertedIndex.save_binary`** | `knowledge_db/retrieval.py` | Public | 原子序列化寫入 `.index.bin.gz` |
| **`InvertedIndex.load_binary`** | `knowledge_db/retrieval.py` | Public | 二進位解壓縮並載入 `InvertedIndex` |
| **`BM25Engine.search`** | `knowledge_db/retrieval.py` | Public | BM25 多欄位加權評分（透過 `doc_id` 自符號池解析符號） |
| **`KnowledgeEngine._get_or_build_index`** | `knowledge_db/engine.py` | Internal | 自動讀取 `.index.bin.gz` 快取或透明懶建置 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `Posting` 輕量化模型 (`knowledge_db/retrieval.py`)

```python
@dataclass
class Posting:
    """輕量倒排索引節點 (消滅 Symbol 深拷貝冗餘)"""
    doc_id: str
    field_freqs: Dict[str, int] = field(default_factory=dict)
    field_lengths: Dict[str, int] = field(default_factory=dict)
    space: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "field_freqs": self.field_freqs,
            "field_lengths": self.field_lengths,
            "space": self.space,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Posting":
        return cls(
            doc_id=data["doc_id"],
            field_freqs=data.get("field_freqs", {}),
            field_lengths=data.get("field_lengths", {}),
            space=data.get("space", "default"),
        )
```

---

### 2.2 `InvertedIndex` 符號池與二進位 I/O API (`knowledge_db/retrieval.py`)

```python
class InvertedIndex:
    """多欄位加權倒排索引與符號池中心"""

    def __init__(self, space_name: str = "default"):
        self.space_name: str = space_name
        self.doc_count: int = 0
        self.field_avgdl: Dict[str, float] = {"name": 0.0, "signature": 0.0, "members": 0.0, "docstring": 0.0}
        self.field_total_lengths: Dict[str, int] = {"name": 0, "signature": 0, "members": 0, "docstring": 0}
        self.symbols: Dict[str, UnifiedSymbol] = {}
        self.index: Dict[str, List[Posting]] = {}

    def add_symbol(self, symbol: UnifiedSymbol, space: str = "default") -> None:
        """索引單一符號，自動登錄符號池與建立倒排 Postings"""

    def get_symbol(self, doc_id: str) -> Optional[UnifiedSymbol]:
        """自符號池中以 O(1) 複雜度獲取完整符號物件"""
        return self.symbols.get(doc_id)

    def save_binary(self, path: Union[str, Path]) -> None:
        """使用 pickle(Protocol 5) + gzip(L6) 原子寫入 .index.bin.gz"""

    @classmethod
    def load_binary(cls, path: Union[str, Path]) -> "InvertedIndex":
        """自 .index.bin.gz 二進位檔案解壓縮並反序列化 InvertedIndex"""
```

---

## 3. 依賴拓撲與實作順序 (Topological Implementation Order)

```text
┌────────────────────────────────────────────────────────┐
│ Level 1: 倒排索引核心重構 (knowledge_db/retrieval.py)  │
│ - Posting (移除 symbol 屬性，保留 doc_id)              │
│ - InvertedIndex (新增 symbols 符號池、save/load_binary) │
│ - BM25Engine.search (改自 index.symbols 取得符號)       │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 2: 門面 SDK 與快取連動 (knowledge_db/engine.py)  │
│ - 快取檔案路徑改為 <space>.index.bin.gz                │
│ - status / clean 升級支援 .index.bin.gz                │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 3: 單元與效能測試驗證 (test_retrieval, test_engine)│
└────────────────────────────────────────────────────────┘
```
