# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_04_knowledge_db_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `atomic_save_gzip_pickle` / `load_gzip_pickle` | `knowledge_db/io_utils.py` | Public | 原子寫入與安全讀取 Gzip+Pickle 二進制檔案 (`FR-06`) |
| `TopologyQueryService` | `knowledge_db/topology_query.py` | Public | 執行符號消歧、`callers`、`callees` 與 `impact` 圖譜查詢 (`FR-03`) |
| `HotPatchResult` | `knowledge_db/pipeline.py` | Public | 熱修補結果純資料類別（移除 `int` 繼承與 `.patched` 別名） (`FR-02`) |
| `KnowledgePipeline` | `knowledge_db/pipeline.py` | Public | 階段化索引熱修補、混合檢索與拓撲查詢委派 (`FR-03`) |
| `BM25Engine` | `knowledge_db/retrieval.py` | Public | 基於 `_score_candidate_documents` 共用核心之 BM25F 檢索器 (`FR-04`) |
| `ResultFormatter` | `knowledge_db/formatter.py` | Public | 搜尋結果與參數化通用拓撲樹 `_format_topology_tree` 渲染器 (`FR-05`) |
| `FingerprintScanner` | `knowledge_db/scanner.py` | Public | 基於 `_iter_eligible_files` 生成器之多空間檔案指紋掃描器 (`FR-07`) |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# knowledge_db/io_utils.py
from pathlib import Path
from typing import Any

def atomic_save_gzip_pickle(target_path: Path, payload: Any) -> None: ...
def load_gzip_pickle(target_path: Path) -> Any: ...

# knowledge_db/topology_query.py
from typing import Any, Dict, List, Optional, Tuple
from .graph import CallGraphIndex
from .retrieval import InvertedIndex
from .schema import UnifiedSymbol
from .space import SpaceManager

class TopologyQueryService:
    def resolve_target_symbols(
        self,
        inverted_index: InvertedIndex,
        symbol_query: str,
        space: Optional[str] = None,
        space_manager: Optional[SpaceManager] = None,
    ) -> Tuple[List[UnifiedSymbol], bool]: ...

    def query_callers(
        self,
        inverted_index: InvertedIndex,
        call_graph: CallGraphIndex,
        space_manager: SpaceManager,
        symbol_query: str,
        depth: int = 1,
        space: Optional[str] = None,
    ) -> Dict[str, Any]: ...

    def query_callees(
        self,
        inverted_index: InvertedIndex,
        call_graph: CallGraphIndex,
        space_manager: SpaceManager,
        symbol_query: str,
        depth: int = 1,
        space: Optional[str] = None,
    ) -> Dict[str, Any]: ...

    def query_impact(
        self,
        inverted_index: InvertedIndex,
        call_graph: CallGraphIndex,
        space_manager: SpaceManager,
        symbol_query: str,
        max_depth: int = 3,
        space: Optional[str] = None,
    ) -> Dict[str, Any]: ...

# knowledge_db/pipeline.py
from dataclasses import dataclass

@dataclass
class HotPatchResult:
    patched_count: int = 0
    evicted_symbols: int = 0
    added_symbols: int = 0
    elapsed_ms: float = 0.0

# knowledge_db/retrieval.py
from typing import Callable, Dict, List, Optional, Set, Tuple
from .tokenizer import Token

class BM25Engine:
    def _score_candidate_documents(
        self,
        query_tokens: List[Token],
        space_filter: Optional[Set[str]] = None,
        file_type_filter: Optional[Set[str]] = None,
        role_filter: Optional[Set[str]] = None,
        symbol_predicate: Optional[Callable[[UnifiedSymbol], bool]] = None,
    ) -> Tuple[Dict[str, float], Dict[str, Set[str]], List[str]]: ...

# knowledge_db/scanner.py
from typing import Iterator, Set, Tuple

class FingerprintScanner:
    def _iter_eligible_files(
        self,
        root_dir: Path,
        supported_exts: Optional[Set[str]] = None,
        extra_ignore_dirs: Optional[Set[str]] = None,
    ) -> Iterator[Tuple[Path, str, os.stat_result]]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `atomic_save_gzip_pickle`：寫入 `.tmp` 失敗時必須確保刪除殘留暫存檔並向上拋出 `OSError` (`EC-02`)。
  - `load_gzip_pickle`：當檔案不存在或 Gzip/Pickle 損毀時向上拋出 `(OSError, EOFError, pickle.UnpicklingError)`，由呼叫端捕獲並觸發索引重建 (`EC-04`)。
  - `TopologyQueryService`：當 `symbol_query` 為空白字串時回傳包含空結果與明確提示之結構，當命中多個同名符號時回傳 `disambiguation_needed=True` 與 `candidates` 列表 (`EC-03`)。
- **階段決策紀錄**：`[P03:DR-01]` `HotPatchResult` 移除 `int` 子類別化，僅保留標準 `@dataclass` 欄位 `patched_count`、`evicted_symbols`、`added_symbols`、`elapsed_ms`；`BM25Engine._score_candidate_documents` 支援選配 `symbol_predicate` 以同時滿足一般檢索與聚合檢索之過濾需求。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: 基礎工具與資料模型層 (io_utils.py, config.py, schema.py, tokenizer.py, space.py)
  │
  ▼
Step 2: 掃描與解析器層 (scanner.py, parsers/registry.py, parsers/__init__.py, parsers/treesitter.py, parsers/spice.py)
  │
  ▼
Step 3: 索引、檢索與圖譜引擎層 (retrieval.py, graph.py, embedding.py, bundler.py)
  │
  ▼
Step 4: 拓撲查詢、管線與門面層 (topology_query.py, pipeline.py, engine.py)
  │
  ▼
Step 5: 格式化、CLI 入口與測試同步層 (formatter.py, scripts/cli.py, scripts/hook.server.py, tests/*.py)
```
