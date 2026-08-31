# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge_db_call_graph_and_reference_index  
> 建立日期：2026-08-31  
> 所屬主計畫：無 (獨立主計畫)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `SymbolCallSite` | `knowledge_db/schema.py` | Public | 不可變 Value Object，記錄單一調用點位置、被調用名稱與作用域 |
| `CallGraphNode` | `knowledge_db/schema.py` | Public | 調用圖譜節點模型，持雙向關聯清單與調用點集合 |
| `BaseParser` (擴充) | `knowledge_db/parsers/base.py` | Public | 擴充 `extract_call_sites()` 與 `extract_imports()` 抽象介面 |
| `PythonParser` (擴充) | `knowledge_db/parsers/python_parser.py` | Public | 實作 Python AST 調用點萃取與作用域棧 (`ScopeStack`) 走訪 |
| `TopologyLinker` | `knowledge_db/linker.py` | Public | 跨檔案四階消歧鏈接器，將調用點與目標 `UnifiedSymbol` 綁定 |
| `CallGraphIndex` | `knowledge_db/graph.py` | Public | 雙向稀疏鄰接表、整數池化、Gzip 二進位快取與多階影響面分析引擎 |
| `KnowledgeEngine` (擴充) | `knowledge_db/engine.py` | Public | 頂層中樞 Facade，提供 `act_callers`、`act_callees`、`act_impact` 與 JIT 增量同步 |
| `cli_callers/callees/impact` | `knowledge_db/cli.py` | Public | CLI 指令封裝與 RFC 8089 可點擊 Markdown 標籤格式化輸出 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `schema.py` 調用點與節點資料結構
```python
@dataclass(frozen=True)
class SymbolCallSite:
    """符號調用點不可變模型 (Value Object)"""
    callee_name: str             # 被調用之識別碼名稱 (如 'build_index' 或 'load_binary')
    line_number: int             # 調用所在行號 (1-based)
    caller_symbol_id: str = ""   # 調用者所屬頂層 UnifiedSymbol ID
    caller_member_name: str = "" # 若在類別/方法內，記錄方法名 (如 'KnowledgeEngine.act_search')
    context_prefix: str = ""     # 調用前綴 (如 'self.', 'InvertedIndex.', 'uri.')
    file_path: str = ""          # 相對於專案根目錄之正規化檔案路徑
    space: str = ""              # 所屬語意空間

@dataclass
class CallGraphNode:
    """調用圖譜節點"""
    symbol_id: str
    callers: Set[str] = field(default_factory=set)      # 上游調用者 symbol_id 清單
    callees: Set[str] = field(default_factory=set)      # 下游被調用者 symbol_id 清單
    call_sites: List[SymbolCallSite] = field(default_factory=list)
```

### 2.2 `parsers/base.py` 與 `python_parser.py` 解析器介面
```python
class BaseParser(ABC):
    def extract_call_sites(self, file_path: str, content: str, space: str) -> List[SymbolCallSite]:
        """提取文字內容中的符號調用點清單 (預設回傳空清單)"""
        return []

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        """提取文字內容中的檔頭 import 映射表 {'alias': 'full.module.path'} (預設回傳空字典)"""
        return {}
```

### 2.3 `linker.py` 四階消歧拓撲鏈接器
```python
class TopologyLinker:
    """跨檔案四階消歧鏈接器"""
    def __init__(
        self,
        symbols_map: Dict[str, UnifiedSymbol],
        thesaurus: Optional[ThesaurusEngine] = None,
        tokenizer: Optional[CodeTokenizer] = None,
    ):
        ...

    def link_call_sites(
        self,
        call_sites: List[SymbolCallSite],
        imports_map: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> List[Tuple[str, str, SymbolCallSite]]:
        """
        將調用點清單解析並消歧為 (caller_symbol_id, callee_symbol_id, call_site) 三元組。
        :param call_sites: 提取出之調用點清單
        :param imports_map: {file_path: {local_name: full_import_path}}
        :return: 成功解析之調用邊清單
        """
```

### 2.4 `graph.py` 雙向調用圖譜索引
```python
class CallGraphIndex:
    """雙向調用圖譜索引 (整數池化 + Gzip 二進位快取)"""
    def __init__(self):
        self.id_to_int: Dict[str, int] = {}
        self.int_to_id: List[str] = []
        self.forward_graph: Dict[int, Set[int]] = defaultdict(set)   # caller -> callees
        self.reverse_graph: Dict[int, Set[int]] = defaultdict(set)   # callee -> callers
        self.call_sites_map: Dict[Tuple[int, int], List[SymbolCallSite]] = defaultdict(list)

    def add_edge(self, caller_symbol_id: str, callee_symbol_id: str, call_site: Optional[SymbolCallSite] = None) -> None:
        """建立 caller ➔ callee 雙向關聯邊"""

    def remove_symbol_edges(self, symbol_ids: Set[str]) -> None:
        """移除指定 symbol_ids 所屬之所有出入度邊"""

    def get_callers(self, symbol_id: str) -> List[str]:
        """取得上游調用者 symbol_id 清單"""

    def get_callees(self, symbol_id: str) -> List[str]:
        """取得下游被調用者 symbol_id 清單"""

    def query_impact(self, target_symbol_id: str, max_depth: int = 2) -> Dict[str, Any]:
        """
        以 BFS 走訪 reverse_graph 計算多階擴散影響面 (防循環 visited_set 剪枝)
        :return: {
            "target_id": str,
            "max_depth": int,
            "layers": {1: [caller_id, ...], 2: [caller_id, ...]},
            "total_impacted_symbols": int,
            "total_impacted_files": int
        }
        """

    def patch_incremental(
        self,
        dirty_file_paths: Set[str],
        new_edges: List[Tuple[str, str, SymbolCallSite]],
        old_symbol_ids: Set[str],
    ) -> None:
        """差量修補調用圖譜 (拔除 dirty 檔案舊邊並注入 new_edges)"""

    def save_binary(self, path: Union[str, Path], compresslevel: int = 1) -> None:
        """原子持久化二進位 Gzip 快取 (Protocol 5)"""

    @classmethod
    def load_binary(cls, path: Union[str, Path]) -> "CallGraphIndex":
        """自二進位 Gzip 快取反序列化 CallGraphIndex"""
```

### 2.5 `engine.py` 頂層 Facade SDK
```python
class KnowledgeEngine:
    def act_callers(self, target_query: str, space: Optional[str] = None, snippet: bool = True) -> Dict[str, Any]:
        """查詢 target_query 的直接上游調用者"""

    def act_callees(self, target_query: str, space: Optional[str] = None, snippet: bool = True) -> Dict[str, Any]:
        """查詢 target_query 內部調用的下游符號清單"""

    def act_impact(self, target_query: str, depth: int = 2, space: Optional[str] = None) -> Dict[str, Any]:
        """計算 target_query 的重構影響面擴散拓撲樹"""
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Schema 模型]
  └── schema.py (SymbolCallSite, CallGraphNode)
       │
       v
[Step 2: AST 解析器擴充]
  └── parsers/base.py ➔ parsers/python_parser.py (CallSiteVisitor, ScopeStack)
       │
       v
[Step 3: 拓撲消歧鏈接器]
  └── linker.py (TopologyLinker, 4-Tier Cascade)
       │
       v
[Step 4: 雙向圖索引引擎]
  └── graph.py (CallGraphIndex, Integer Pool, Gzip Binary, patch_incremental)
       │
       v
[Step 5: 門面整合與 JIT 熱自愈]
  └── engine.py (act_callers, act_callees, act_impact, _hot_patch_unified_index)
       │
       v
[Step 6: CLI 指令與 RFC 8089 輸出]
  └── cli.py (callers, callees, impact)
       │
       v
[Step 7: 測試驗證套件]
  └── tests/test_call_graph.py (FT-01~07, ET-01~02, PT-01, RT-01)
```
