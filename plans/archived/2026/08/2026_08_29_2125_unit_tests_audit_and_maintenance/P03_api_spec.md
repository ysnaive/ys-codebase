# API 與介面規格書 (API & Interface Specification)

> 功能名稱：`unit_tests_audit_and_maintenance`  
> 建立日期：2026-08-29  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `SemVerCoreTest` | `source/core/tests/test_semver.py` | Internal (Test) | 測試標準 4 段式與 3 段式 SemVer 解析、比較、`bump_version` 與約束求解。 |
| `TestTester` | `source/dev/tests/test_tester.py` | Internal (Test) | 測試測試調度器、單元測試執行與沙盒生命週期整合。 |
| `TestParsers` | `source/knowledge-db/tests/test_parsers.py` | Internal (Test) | 測試多語言 (Python/C/C++/Markdown) AST 符號解析與深度邊界容錯。 |
| `TestTokenizer` | `source/knowledge-db/tests/test_tokenizer.py` | Internal (Test) | 測試 CamelCase/snake_case 分詞與雙向軟工同義詞庫擴展。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `core`: `SemVerCoreTest`
```python
class SemVerCoreTest(YSCBTestCase):
    def test_parse_valid_semver(self) -> None:
        """驗證 4 段式 (1.2.3.4) 與 3 段式 (1.2.3) 正規化解析。"""
        ...

    def test_parse_semver_build_tag(self) -> None:
        """驗證 .build 標籤解析與 is_build 屬性。"""
        ...

    def test_parse_malformed_semver_raises_value_error(self) -> None:
        """驗證非法版本字串防禦 (EC-01)。"""
        ...

    def test_numerical_ordering_and_comparison(self) -> None:
        """驗證數值優先級比較 (1.10.0 > 1.9.0, major 優先, revision 數值比較)。"""
        ...

    def test_bump_version(self) -> None:
        """驗證 major, minor, patch, revision 四維度版本號遞增。"""
        ...

    def test_constraint_matching_and_find_best(self) -> None:
        """驗證 >=, >, <, <= 等約束條件求解與 find_best_version。"""
        ...
```

### 2.2 `knowledge-db`: `TestParsers` & `TestTokenizer`
```python
class TestParsers(YSCBTestCase):
    def test_python_parser_symbols_and_docstrings(self) -> None:
        """驗證 Python class, method, function 與 docstring 提取。"""
        ...

    def test_cpp_parser_classes_and_macros(self) -> None:
        """驗證 C/C++ class, struct, enum, macro 與多行簽名解析。"""
        ...

    def test_markdown_and_json_parsers(self) -> None:
        """驗證 Markdown 標題/表格與 JSON 結構提取。"""
        ...

    def test_parser_syntax_error_resilience(self) -> None:
        """驗證語法毀損檔案之容錯與防禦處理。"""
        ...

class TestTokenizer(YSCBTestCase):
    def test_code_tokenizer_subwords(self) -> None:
        """驗證 CamelCase 與 snake_case 子詞切分。"""
        ...

    def test_thesaurus_expansion(self) -> None:
        """驗證軟工同義詞庫雙向擴展與去重。"""
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Core 測試整併] 
  source/core/tests/test_semver.py (更新) ➔ 刪除 source/core/tests/test_semver_v4.py
      │
      ▼
[Step 2: Dev 測試純化]
  source/dev/tests/test_tester.py (精簡重複斷言) ➔ 驗證 source/dev/tests/test_sandbox.py
      │
      ▼
[Step 3: Agents-Workflow 測試精簡]
  刪除 source/agents-workflow/tests/test_basic.py ➔ 驗證 test_compiler.py 與 test_targets.py
      │
      ▼
[Step 4: Knowledge-DB 測試整併]
  source/knowledge-db/tests/test_parsers.py (更新) ➔ 刪除 test_parsers_deep.py
  source/knowledge-db/tests/test_tokenizer.py (更新) ➔ 刪除 test_thesaurus.py
      │
      ▼
[Step 5: 全生態系 4 大模組全量回歸驗證]
  python yscb.py dev test --all
```
