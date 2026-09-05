# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_03_networkx_call_graph_and_impact_analysis  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `SymbolSelector` | `knowledge_db/selector.py` | Public | 解析微型查詢語法並回傳結構化選擇器物件。 |
| `ParsedSelector` | `knowledge_db/selector.py` | Public | 結構化選擇器容器，提供對 `UnifiedSymbol` 的精確比對。 |
| `LanguageTopologyProtocol` | `knowledge_db/protocol.py` | Public | 跨語言調用點與匯入提取之抽象基礎協議。 |
| `CallGraphIndex` | `knowledge_db/graph.py` | Public | NetworkX 驅動之符號調用拓撲圖索引與多階影響面分析。 |
| `TopologyLinker` | `knowledge_db/linker.py` | Public | 基於 FQN 與 Import 映射的跨檔案調用消歧鏈接器。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# =============================================================================
# 1. 符號選擇器 (knowledge_db/selector.py)
# =============================================================================

@dataclass(frozen=True)
class ParsedSelector:
    raw_query: str
    identifier: str
    scope: Optional[str] = None
    target_kinds: Optional[Set[SymbolKind]] = None
    is_callable: bool = False

    def matches(self, sym: UnifiedSymbol) -> bool:
        """驗證 UnifiedSymbol 是否精確符合選擇器約束條件"""
        ...

class SymbolSelector:
    @classmethod
    def parse(cls, expr: str) -> ParsedSelector:
        """
        解析 [<kind-prefix>\s+][<scope>.]<identifier>[()] 微型語法
        範例：'class Foo', 'struct Point.x', 'foo.bar()', 'fn init()'
        """
        ...

    @classmethod
    def find_matches(
        cls,
        expr: str,
        symbols_pool: Iterable[UnifiedSymbol],
    ) -> List[UnifiedSymbol]:
        """由符號池中過濾出所有符合選擇器之候選符號"""
        ...


# =============================================================================
# 2. 多語言調用拓撲協議 (knowledge_db/protocol.py)
# =============================================================================

class LanguageTopologyProtocol(ABC):
    """跨語言調用拓撲與檔頭匯入提取協議"""

    @abstractmethod
    def extract_call_sites(self, ast: Any, source_bytes: bytes, file_path: str) -> List[SymbolCallSite]:
        """自語法樹提取具備 caller_member_name 與 context_prefix 之調用點"""
        ...

    @abstractmethod
    def extract_imports(self, ast: Any, source_bytes: bytes, file_path: str) -> Dict[str, str]:
        """提取模組或別名與完整目標路徑之映射表 (e.g. {'np': 'numpy'})"""
        ...


# =============================================================================
# 3. NetworkX 調用圖譜索引 (knowledge_db/graph.py)
# =============================================================================

class CallGraphIndex:
    """以 networkx.DiGraph 驅動的調用圖譜索引"""

    def __init__(self, graph: Optional[nx.DiGraph] = None):
        self._graph: nx.DiGraph = graph if graph is not None else nx.DiGraph()

    def add_edge(
        self,
        caller_symbol_id: str,
        callee_symbol_id: str,
        call_site: Optional[SymbolCallSite] = None,
    ) -> None:
        """新增調用邊，節點保存 symbol_id，邊保存 call_sites 列表"""
        ...

    def get_callers(self, symbol_id: str) -> List[str]:
        """回傳所有直接調用該符號的上游 caller_symbol_id (基於 G.pred)"""
        ...

    def get_callees(self, symbol_id: str) -> List[str]:
        """回傳該符號直接調用的所有下游 callee_symbol_id (基於 G.succ)"""
        ...

    def get_call_sites(self, caller_id: str, callee_id: Optional[str] = None) -> List[SymbolCallSite]:
        """取得指定兩點間或 caller 上的調用點資訊"""
        ...

    def query_impact(self, target_symbol_id: str, max_depth: int = 2) -> Dict[str, Any]:
        """
        利用 NetworkX 逆向走訪計算多階影響層級 (layers) 與呼叫鏈 (call_chains)，
        天然規避遞迴循環。
        """
        ...

    def remove_symbol_edges(self, symbol_ids: Set[str]) -> None:
        """自圖中移除指定節點及其所有關聯邊"""
        ...

    def patch_incremental(
        self,
        dirty_file_paths: Set[str],
        new_edges: List[Tuple[str, str, SymbolCallSite]],
        old_symbol_ids: Set[str],
    ) -> None:
        """差量修補調用圖譜"""
        ...

    def to_dict(self) -> Dict[str, Any]:
        """序列化圖資料為向後相容字典"""
        ...

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CallGraphIndex":
        """由字典還原 CallGraphIndex"""
        ...

    def save_binary(self, path: Union[str, Path], compresslevel: int = 1) -> None:
        """原子持久化二進位 Gzip 快取 (Protocol 5)"""
        ...

    @classmethod
    def load_binary(cls, path: Union[str, Path]) -> "CallGraphIndex":
        """自二進位 Gzip 快取載入"""
        ...


# =============================================================================
# 4. 跨檔案消歧鏈接器 (knowledge_db/linker.py)
# =============================================================================

class TopologyLinker:
    """結合 FQN、階層父子作用域與 Import 映射執行精準四階消歧"""

    def __init__(
        self,
        symbols_map: Dict[str, UnifiedSymbol],
        thesaurus: Optional[Any] = None,
        tokenizer: Optional[CodeTokenizer] = None,
    ):
        ...

    def resolve_call_site(
        self,
        site: SymbolCallSite,
        file_imports: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """四階消歧定位唯一 callee_symbol_id；無法確定者回傳 None (杜絕幽靈邊)"""
        ...

    def link_call_sites(
        self,
        call_sites: List[SymbolCallSite],
        imports_map: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> List[Tuple[str, str, SymbolCallSite]]:
        """批次消歧並建立調用邊清單"""
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[manifest.json: networkx]
          │
          ▼
[knowledge_db/selector.py] ──┐
                             │
[knowledge_db/protocol.py] ──┼──► [knowledge_db/linker.py] ──► [knowledge_db/graph.py]
                             │                                           │
                             │                                           ▼
                             └─────────────────────────────────► [scripts/cli.py]
```
