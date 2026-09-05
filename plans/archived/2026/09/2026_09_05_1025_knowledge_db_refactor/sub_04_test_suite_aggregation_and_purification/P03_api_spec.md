# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_04_test_suite_aggregation_and_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `TestNetworkXGraph` & `TestCallGraph` | `ys_codebase/source/knowledge-db/tests/test_graph.py` | Internal | 整併圖譜操作、NetworkX 拓撲演算法、AST 調用解析與 Gzip 序列化測試 |
| `TestMultiLanguageParsers` | `ys_codebase/source/knowledge-db/tests/test_parsers.py` | Internal | 整併 Python、JS/TS、Spice、Web AST 解析器與節點走訪測試 |
| `TestRetrievalAndAggregation` | `ys_codebase/source/knowledge-db/tests/test_retrieval.py` | Internal | 整併倒排檢索、BM25 評分與多條件聚合搜尋過濾測試 |
| `TestIncrementalAndHealing` | `ys_codebase/source/knowledge-db/tests/test_hot_reload.py` | Internal | 整併檔案系統增量監聽、AST 差異更新與 JIT 熱修復測試 |
| `YSCBTestCase.mark_passed()` | 全測試案例方法 | Public | 測試斷言成功之標定契約，通知測試框架分類為 PASS，消除 UNKNOWN |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
from yscb_test import YSCBTestCase, require, Requirement

class TestGraphSuite(YSCBTestCase):
    """整併後之統一圖譜測試套件 (涵蓋 NetworkX DiGraph 與 Call Graph 調用圖譜)"""

    @require(Requirement.LOGIC)
    def test_digraph_lifecycle_and_serialization(self) -> None:
        """驗證 NetworkX DiGraph 之節點邊操作與 Gzip Protocol 5 序列化/反序列化"""
        ...
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ast_caller_callee_resolution(self) -> None:
        """驗證基於 AST 作用域解析之調用者/被調用者圖譜邊建立"""
        ...
        self.mark_passed()


class TestParsersSuite(YSCBTestCase):
    """整併後之多語言 AST 解析器測試套件 (Python, TS/JS, Spice, Web)"""

    @require(Requirement.LOGIC)
    def test_universal_ast_and_spice_parsing(self) -> None:
        """驗證通用 AST 節點映射與 Spice/Netlist 電路語法解析"""
        ...
        self.mark_passed()


class TestWorkflowSuite(YSCBTestCase):
    """重度多進程與磁碟 I/O 測試套件 (標註為 WORKFLOW 分流)"""

    @require(Requirement.WORKFLOW)
    def test_multiprocess_bundler_packaging(self) -> None:
        """多進程實體打包與解包測試 (日常快測略過)"""
        ...
        self.mark_passed()
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Phase 1: 圖譜與檢索整併]
├── 1. test_graph.py (合併 test_networkx_graph.py + test_call_graph.py) ──> 刪除舊檔
└── 2. test_retrieval.py (合併 test_search_aggregation.py) ───────────────> 刪除舊檔

[Phase 2: 解析器與熱重載整併]
├── 3. test_parsers.py (合併 test_spice_parser.py + test_web_parsers.py) ──> 刪除舊檔
└── 4. test_hot_reload.py (合併 test_incremental_hot_reload.py + test_jit_hot_healing.py) ──> 刪除舊檔

[Phase 3: 4-Tier 標註與 全量 mark_passed 補齊]
├── 5. 獨立套件 (test_selector, test_hybrid, test_tokenizer, test_schema, test_space, test_providers, test_cli) 補齊 mark_passed
└── 6. 重型套件 (test_engine, test_scanner, test_bundler) 標註 WORKFLOW，test_benchmark 標註 PERF

[Phase 4: 全量回歸驗證與快取清理]
└── 7. 刪除殘留 __pycache__，執行 dev test 達成 0 Fail, 0 Unknown, Pass 100%
```
