# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_05_pipeline_engine_refactor_and_dogfooding  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `UniversalRedundancyFilter` | `knowledge_db/formatter.py` | Public | 全域切片去重器：過濾 Docstring 註解、Markdown 標頭、版權樣板與空行，保留真實邏輯 |
| `ResultFormatter` | `knowledge_db/formatter.py` | Public | 呈現層格式化器：管理 8,000 字元動態預算、路徑與 Markdown 鏈接、4 大查詢輸出格式化 |
| `IndexingPipeline` | `knowledge_db/pipeline.py` | Public | 流水線引擎：多空間倒排/向量索引建置、JIT 增量指紋嗅探、熱補丁修復與 Gzip 快取持久化 |
| `KnowledgeEngine` | `knowledge_db/engine.py` | Public | 頂層 SDK 門面 (Facade)：高內聚中樞，委派呈現與流水線，維持 100% 既有 Public API |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 UniversalRedundancyFilter API

```python
class UniversalRedundancyFilter:
    """通用切片去重與資訊純化器"""

    def purify_lines(
        self,
        lines: List[Tuple[int, str]],
        symbol_name: str = "",
        signature: str = "",
        docstring_summary: str = "",
        language: str = "",
    ) -> List[Tuple[int, str]]:
        """
        純化切片代碼行清單 [(line_num, text), ...]:
        1. 剔除與 docstring_summary 重疊之多行引號 (''' 或 \"\"\") 或區塊註解 (/* ... */)
        2. 剔除 Markdown 切片中與 symbol_name / signature 重疊之 #+ Heading 開頭行
        3. 剔除版權宣告 (SPDX, Copyright, License) 樣板
        4. 收斂 2 行以上之連續空白行至單一行
        5. 保證原行號 line_num 100% 精確保留；若過濾後為空，保底回傳原始首行 (EC-05)
        """
```

### 2.2 ResultFormatter API (8,000 字元上限)

```python
AUTO_BUDGET_CHARS: int = 8000
AUTO_DECAY_START_CHARS: int = 3500
AUTO_DECAY_MIN_CHARS: int = 6000
AUTO_NO_SNIPPET_CHARS: int = 7000
AUTO_MAX_SNIPPET_LINES: int = 30
AUTO_MIN_SNIPPET_LINES: int = 10
AUTO_MIN_RENDERED_ITEMS: int = 5

def compute_dynamic_snippet_lines(
    current_chars: int,
    budget_limit: int = AUTO_BUDGET_CHARS,
    start_decay: int = AUTO_DECAY_START_CHARS,
    min_decay: int = AUTO_DECAY_MIN_CHARS,
    no_snippet_threshold: int = AUTO_NO_SNIPPET_CHARS,
    max_lines: int = AUTO_MAX_SNIPPET_LINES,
    min_lines: int = AUTO_MIN_SNIPPET_LINES,
) -> int:
    """計算 auto 模式下的 8000 字元動態切片行數預算"""

class ResultFormatter:
    """呈現層格式化中樞"""

    def __init__(
        self,
        space_manager: Optional[Any] = None,
        workspace_root: Optional[Path] = None,
        redundancy_filter: Optional[UniversalRedundancyFilter] = None,
    ): ...

    def format_file_link(self, file_path: Union[str, Path], line: Optional[int] = None, end_line: Optional[int] = None, use_basename: bool = True) -> str: ...
    def to_file_uri(self, file_path: Union[str, Path], line: Optional[int] = None) -> str: ...
    def normalize_workspace_path(self, file_path: Union[str, Path]) -> str: ...
    def format_search_output(self, results: List[AggregatedFileResult], query: str = "", detail_mode: str = "auto", snippet: bool = False, format_type: str = "text", limit_mode: Union[int, str] = "auto") -> str: ...
    def format_callers_output(self, callers_data: List[SymbolCallSite], symbol_name: str, detail_mode: str = "auto", snippet: bool = False, format_type: str = "text") -> str: ...
    def format_callees_output(self, callees_data: List[SymbolCallSite], symbol_name: str, detail_mode: str = "auto", snippet: bool = False, format_type: str = "text") -> str: ...
    def format_impact_output(self, impact_data: Dict[str, Any], symbol_name: str, detail_mode: str = "auto", format_type: str = "text") -> str: ...
```

### 2.3 IndexingPipeline API

```python
class IndexingPipeline:
    """多空間索引建置、JIT 增量熱補丁與持久化流水線"""

    def __init__(
        self,
        space_manager: SpaceManager,
        bundler: SemanticBundler,
        scanner: FingerprintScanner,
        bm25_engine: BM25Engine,
        embedding_service: EmbeddingService,
        hybrid_engine: HybridSearchEngine,
    ): ...

    @property
    def indices_dir(self) -> Path: ...
    def build_unified_index(self, force: bool = False, quiet: bool = True) -> InvertedIndex: ...
    def hot_patch_unified_index(self, index: InvertedIndex) -> InvertedIndex: ...
    def build_index(self, space: str, force: bool = False, quiet: bool = True) -> InvertedIndex: ...
    def clean(self, space: Optional[str] = None) -> Dict[str, Any]: ...
```

### 2.4 KnowledgeEngine Facade 委派轉發契約

```python
class KnowledgeEngine:
    """瘦身後的頂層統一 Facade SDK (<= 450 行)"""

    def __init__(self, ...):
        # 實例化各子系統 + self.pipeline + self.formatter
        ...

    # 維持完全相容之公開 API 轉發
    def build_unified_index(self, force: bool = False, quiet: bool = True) -> InvertedIndex:
        return self.pipeline.build_unified_index(force=force, quiet=quiet)

    def search(self, query: str, space: Optional[str] = None, ...) -> Union[List[SearchResult], List[AggregatedFileResult]]:
        # 檢索編排 (委派 hybrid_engine 與 pipeline)
        ...

    def format_search_output(self, *args, **kwargs) -> str:
        return self.formatter.format_search_output(*args, **kwargs)

    def act_callers(self, *args, **kwargs) -> List[SymbolCallSite]: ...
    def act_callees(self, *args, **kwargs) -> List[SymbolCallSite]: ...
    def act_impact(self, *args, **kwargs) -> Dict[str, Any]: ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: 實作 formatter.py (含 UniversalRedundancyFilter 與 8000 字元預算衰減器)
Step 2: 實作 pipeline.py (含 IndexingPipeline 獨立索引與熱補丁邏輯)
Step 3: 重構 engine.py (精簡為輕量 Facade，注入 pipeline 與 formatter，維持全對外契約)
Step 4: 單元測試與回歸驗證 (test_engine.py 擴充，121 測試 100% 綠燈)
```
