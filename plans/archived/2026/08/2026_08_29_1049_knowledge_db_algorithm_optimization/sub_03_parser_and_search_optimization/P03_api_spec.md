# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge_db_parser_and_search_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_1049_knowledge_db_algorithm_optimization  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `UnifiedSymbol` | `knowledge_db/schema.py` | Public | 擴充支援 `end_line` 物理端線與 `parent_scope` 作用域元資料。 |
| `AggregatedItem` | `knowledge_db/schema.py` | Public | 結構化檔案內部單一命中 Item（含符號、單項得分、命中詞與切片）。 |
| `AggregatedFileResult` | `knowledge_db/schema.py` | Public | 聚合檔案節點資料模型（含檔案路徑、聚合總分、子項目清單、空間標籤等）。 |
| `QueryFilter` | `knowledge_db/retrieval.py` | Public | 擴充 `ftypes: Optional[List[str]]` 支援來源副檔名過濾。 |
| `BM25Engine.search_aggregated` | `knowledge_db/retrieval.py` | Public | 執行 BM25 計分、`--ftype` 篩選、Top-N 動態聚合與回填管線。 |
| `PythonParser.parse` | `knowledge_db/parsers/python_parser.py` | Public | AST 提取類別方法、函式為一級 Symbol，標記精確 `end_lineno`。 |
| `CppParser.parse` | `knowledge_db/parsers/cpp_parser.py` | Public | 跨行累積狀態機、Namespace 堆疊與 Class 作用域成員提取。 |
| `CSharpParser.parse` | `knowledge_db/parsers/csharp_parser.py` | Public | 提取 Class/Method/Property 並標記 `end_line` 邊界。 |
| `MarkdownParser.parse` | `knowledge_db/parsers/markdown_parser.py` | Public | 標題、表格、段落精確計算並寫入 `end_line`。 |
| `KnowledgeDBEngine.search` | `knowledge_db/engine.py` | Public | 頂層檢索入口，支援 `ftypes`、延遲切片提取與 JIT 自愈。 |
| `format_aggregated_tree` | `scripts/cli.py` | Internal | 將聚合檢索結果渲染為 ASCII 樹狀階層文本。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 資料模型擴充 (`schema.py`)

```python
@dataclass(frozen=True)
class UnifiedSymbol:
    id: str
    name: str
    kind: str
    file_path: str
    line_number: int
    language: str
    docstring: str = ""
    signature: str = ""
    end_line: int = 0                  # [NEW] 符號實體結束行號 (預設 0 代表單行或未知)
    members: List[MemberInfo] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化時輸出 end_line 與 metadata"""
        ...

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedSymbol":
        """反序列化時若無 end_line 則預設為 line_number，保證向後相容"""
        ...

@dataclass(frozen=True)
class AggregatedItem:
    """單一檔案節點內部的命中項目"""
    symbol: UnifiedSymbol
    score: float
    matched_terms: List[str]
    snippet: str = ""
    code_snippet: Optional[CodeSnippet] = None

    def to_dict(self) -> Dict[str, Any]:
        ...

@dataclass(frozen=True)
class AggregatedFileResult:
    """檔案層級聚合節點 (Top-N 返回之主實體)"""
    file_path: str
    total_score: float
    items: List[AggregatedItem]        # 內部依 Item 分數降序，最多保留 Top-3
    spaces: List[str]
    language: str

    def to_dict(self) -> Dict[str, Any]:
        ...
```

### 2.2 檢索引擎與過濾器 (`retrieval.py`)

```python
@dataclass(frozen=True)
class QueryFilter:
    spaces: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    kinds: Optional[List[str]] = None
    ftypes: Optional[List[str]] = None     # [NEW] 副檔名清單 (如 ["py"], ["c", "cpp", "h"])
    min_score: float = 0.01
    limit: int = 10

class BM25Engine:
    def search_aggregated(
        self,
        query: str,
        index: InvertedIndex,
        filter_cfg: Optional[QueryFilter] = None,
        alpha: float = 0.2,
        top_k_items_per_file: int = 3,
    ) -> List[AggregatedFileResult]:
        """
        執行多欄位加權 BM25 檢索並透過 Top-N 動態回填管線聚合為檔案節點清單。
        
        評分公式：
          Score(File) = max(S_i) + alpha * sum(S_j for j != i)
        
        回填閉環：
          從候選池依分數降序逐筆處理，同檔案合併，新檔案開立節點，直到累積滿 limit 個檔案節點或候選池耗盡。
          最後依 total_score 二次降序排序輸出。
        """
        ...
```

### 2.3 核心引擎與 CLI 格式化 (`engine.py` & `cli.py`)

```python
class KnowledgeDBEngine:
    def search(
        self,
        query: str,
        space: Optional[Union[str, List[str]]] = None,
        kinds: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        ftypes: Optional[Union[str, List[str]]] = None,  # [NEW]
        min_score: float = 0.01,
        limit: int = 10,
        snippet: bool = False,
        context_lines: int = 3,
        auto_rebuild: bool = True,
        verbose: bool = True,
    ) -> List[AggregatedFileResult]:
        ...

# cli.py
def format_tree_output(
    results: List[AggregatedFileResult],
    query_str: str,
    is_detail: bool = False,
    is_snippet: bool = False,
    normalize_fn: Optional[Callable[[str], str]] = None,
) -> str:
    """
    依據模式將 AggregatedFileResult 清單渲染為 ASCII 樹狀分支：
      file_path (Score: XX.XX, N items)
      ├── #01 [XX.XX] KIND: name (lines L1~L2)
      └── #02 [XX.XX] KIND: name (lines L3~L4)
    """
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Layer 0: 資料模型與介面契約]
  └─ 1. schema.py: UnifiedSymbol (end_line) + AggregatedItem + AggregatedFileResult

[Layer 1: 解析器原子 Item 化與深度強化]
  ├─ 2. parsers/python_parser.py (Method/Function 物化 + end_lineno)
  ├─ 3. parsers/cpp_parser.py (跨行累積狀態機 + Namespace 堆疊 + Class 作用域)
  ├─ 4. parsers/csharp_parser.py (Method/Property end_line 座標)
  └─ 5. parsers/markdown_parser.py (Section/Table end_line 座標)

[Layer 2: 檢索引擎與動態聚合演算法]
  └─ 6. retrieval.py: QueryFilter.ftypes + BM25Engine.search_aggregated (Top-N Refill)

[Layer 3: 核心引擎對接與延遲切片]
  └─ 7. engine.py: search() 支援 ftypes 與聚合切片對接

[Layer 4: CLI 參數與樹狀輸出渲染]
  └─ 8. scripts/cli.py: --ftype 參數解析 + format_tree_output 樹狀分支渲染

[Layer 5: 單元測試、整合測試與 Dogfooding 閉環]
  ├─ 9. tests/test_parsers_deep.py (解析器深度測試)
  ├─ 10. tests/test_search_aggregation.py (檢索、聚合與樹狀渲染測試)
  └─ 11. Dogfooding Pipeline (Build ➔ Regression ➔ Sync)
```

