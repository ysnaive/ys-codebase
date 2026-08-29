# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_01_jit_invalidation_and_hot_healing  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1049_knowledge_db_algorithm_optimization`  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `BinarySnapshotManager` | `knowledge_db/scanner.py` | Internal / Public | 封裝 `unified.meta.bin`（Magic `YFP1`）原生二進位快照讀寫與極速 `(mtime, size)` 比對 |
| `FingerprintScanner.check_invalidation` | `knowledge_db/scanner.py` | Public | 執行全專案空間聯集之 JIT 變更嗅探，於 < 3ms 內判定 Dirty 或 Clean |
| `SemanticBundler.bundle_union` | `knowledge_db/bundler.py` | Public | 全域聯集去重 AST 解析，為符號注入命中的多空間標籤清單 (`spaces: List[str]`) |
| `InvertedIndex` (Unified) | `knowledge_db/retrieval.py` | Public | 單一全域倒排索引，維護正規化全域 BM25 統計指標與多空間標籤 Posting |
| `BM25Engine.search` | `knowledge_db/retrieval.py` | Public | 支援基於 `spaces` 標籤的 O(1) 空間過濾檢索 |
| `KnowledgeEngine.search` | `knowledge_db/engine.py` | Public | 頂層查詢門面，整合 JIT 嗅探、stderr 回饋熱自愈與檢索輸出 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 二進位快照管理器 (`BinarySnapshotManager`)
```python
class BinarySnapshotManager:
    """極致緊湊原生二進位快照管理器 (Magic: YFP1)"""
    MAGIC: bytes = b"YFP1"
    VERSION: int = 1

    @classmethod
    def save(cls, snapshot_path: Union[str, Path], files_map: Dict[str, Tuple[float, int]]) -> None:
        """
        原子寫入二進位快照至磁碟。
        :param snapshot_path: 目標 .meta.bin 路徑
        :param files_map: {正規化檔案相對路徑: (mtime, size)}
        """
        ...

    @classmethod
    def load(cls, snapshot_path: Union[str, Path]) -> Optional[Dict[str, Tuple[float, int]]]:
        """
        極速載入二進位快照（耗時 < 0.1ms）。
        :return: {檔案路徑: (mtime, size)}，若檔案不存在或損毀則回傳 None
        """
        ...
```

### 2.2 空間聯集去重打包 (`SemanticBundler.bundle_union`)
```python
class SemanticBundler:
    def bundle_union(
        self,
        spaces: Optional[List[SpaceConfig]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> SemanticBundle:
        """
        掃描全專案空間聯集，以實體檔案絕對路徑為唯一鍵執行去重，
        所有檔案僅讀取與 AST 解析 1 次；於各 UnifiedSymbol.metadata["spaces"] 注入命中的空間名稱清單。
        """
        ...
```

### 2.3 單一全域倒排索引與空間標籤過濾 (`InvertedIndex` & `Posting`)
```python
@dataclass
class Posting:
    doc_id: str
    field_freqs: Dict[str, int]
    field_lengths: Dict[str, int]
    spaces: List[str] = field(default_factory=list)  # 支援多空間標籤

class InvertedIndex:
    UNIFIED_INDEX_NAME: str = "unified"
    UNIFIED_BIN_FILENAME: str = "unified.index.bin.gz"
    UNIFIED_SNAPSHOT_FILENAME: str = "unified.meta.bin"

    def build_unified(
        self,
        symbols: List[UnifiedSymbol],
        tokenizer: Optional[CodeTokenizer] = None,
    ) -> None:
        """批次建立單一全域倒排索引並正規化 avgdl/IDF 基準指標"""
        ...
```

### 2.4 頂層檢索門面與 JIT 整合 (`KnowledgeEngine.search`)
```python
class KnowledgeEngine:
    def search(
        self,
        query: str,
        space: Optional[Union[str, List[str]]] = None,
        languages: Optional[List[str]] = None,
        kinds: Optional[List[str]] = None,
        min_score: float = 0.01,
        limit: int = 20,
        snippet: bool = False,
        context_lines: int = 2,
        auto_rebuild: bool = True,
        verbose: bool = True,
    ) -> List[SearchResult]:
        """
        執行語意代碼與文檔檢索。
        :param auto_rebuild: 若為 True (預設)，在查詢前執行 JIT 變更嗅探並自動背景熱自愈
        :param verbose: 若為 True，觸發熱自愈時向 sys.stderr 輸出提示
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

依據無環依賴原則，Phase 5 實作嚴格遵循以下拓撲順序：

```text
[Step 1: Scanner]  scanner.py ➔ BinarySnapshotManager 實作與 check_invalidation JIT 嗅探
       │
       ▼
[Step 2: Schema]   schema.py / retrieval.py ➔ Posting / UnifiedSymbol 多空間標籤化 (spaces: List[str])
       │
       ▼
[Step 3: Bundler]  bundler.py ➔ bundle_union() 全域聯集實體檔案去重掃描與符號空間標籤注入
       │
       ▼
[Step 4: Index]    retrieval.py ➔ InvertedIndex 單一全域索引 build_unified() 與 BM25 空間標籤過濾
       │
       ▼
[Step 5: Engine]   engine.py ➔ KnowledgeEngine 串聯 JIT 快篩、熱自愈、stderr 提示與 search 輸出
       │
       ▼
[Step 6: CLI]      cli.py ➔ 增加 --no-auto-rebuild / -n 旗標控制
       │
       ▼
[Step 7: Tests]    tests/test_jit_hot_healing.py ➔ 全量單元、邊界、效能與回歸測試套件
```
