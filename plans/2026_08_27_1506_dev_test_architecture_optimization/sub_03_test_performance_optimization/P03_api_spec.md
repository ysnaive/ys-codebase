# API 與介面規格說明書 (API Specification)

> 功能名稱：測試分類體系重構、效能深水區與沙盒型別安全防固 (Test Taxonomy, Performance & Sandbox Type Safety)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.2  

---

## 1. 介面定義清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案 | 變更類型 | 核心職責說明 |
| :--- | :--- | :---: | :--- |
| `Requirement(Flag)` | `source/dev/dev/testing/requirement.py` | Modify | 重構四層測試分類枚舉與正交沙盒標籤。 |
| `filter_suite()` | `source/dev/dev/testing/runner.py` | Modify | 支援預設過濾遮罩、多分類篩選與 `--target` 精準解析。 |
| `TestDiscovery` | `source/dev/dev/testing/runner.py` | Modify | 動態守門：加載時執行 `isinstance(test, YSCBTestCase)` 斷言。 |
| `YSCBTestCase.setUp()` | `source/dev/dev/testing/case.py` | Modify | 入口守門：檢測非沙盒宿主裸跑直接拋出 `SecurityError` 阻斷。 |
| `Checker._check_tests()` | `source/dev/dev/checker.py` | Modify | 靜態守門：AST 語法樹檢查禁止原生 `unittest.TestCase`。 |
| `Tester._run_test()` | `source/dev/dev/tester.py` | Modify | 解析 `--target`, `--logical`, `--env`, `--workflow`, `--perf`, `--all-types`。 |

---

## 2. API 詳細簽名與行為規格 (Detailed Signatures)

### 2.1 `Requirement` (四層分類列舉)
```python
from enum import Flag, auto

class Requirement(Flag):
    """Test execution requirement and classification flags."""
    NONE = 0
    LOGIC = auto()            # 純邏輯（預設執行）
    ENV = auto()              # 環境/跨模組/依賴注入（預設執行）
    WORKFLOW = auto()         # 工作流/E2E（預設略過）
    PERF = auto()             # 效能/壓力（預設略過）
    ISOLATED_SANDBOX = auto() # 正交獨立沙盒標籤

    # 組合別名
    ALL_DEFAULT = LOGIC | ENV
    ALL = LOGIC | ENV | WORKFLOW | PERF
```

### 2.2 `filter_suite` (過濾與目標定位引擎)
```python
def filter_suite(
    suite: unittest.TestSuite,
    pattern: Optional[str] = None,
    target: Optional[str] = None,
    active_types: Optional[Set[str]] = None
) -> unittest.TestSuite:
    """
    Filters test suite by pattern, target selector, and active requirement types.

    Args:
        suite: unittest.TestSuite to filter.
        pattern: Optional name substring filter (-k).
        target: Optional target selector (e.g. 'core:test_uri' or 'core:TestCoreURI.test_resolve').
        active_types: Set of active category strings ('logic', 'env', 'workflow', 'perf').
                      Defaults to {'logic', 'env'}.

    Returns:
        Filtered unittest.TestSuite.
    """
```

### 2.3 `YSCBTestCase.setUp` (入口守門阻斷)
```python
class SecurityError(RuntimeError):
    """Raised when tests are executed in an insecure or forbidden host environment."""
    pass

class YSCBTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # Check if running within authenticated sandbox environment
        is_sandbox_env = os.environ.get("YSCB_TEST_SANDBOX") == "1"
        if not is_sandbox_env:
            raise SecurityError(
                "[dev:test] Security Guard Blocked: Running tests directly on the host workspace is strictly forbidden. "
                "Please use 'python yscb.py dev test <module>' or execute within an authenticated YSCB virtual sandbox."
            )
```

---

## 3. 異常與錯誤碼規格 (Error Handling & Exceptions)

| 異常類型 | 觸發情境 | 拋出層級 | 錯誤訊息範例 |
| :--- | :--- | :--- | :--- |
| `TypeError` | 測試類別繼承原生 `unittest.TestCase` | `TestDiscovery` | `[dev:test] Test 'X' must inherit from 'dev.testing.case.YSCBTestCase'` |
| `SecurityError` | 在宿主環境裸跑 `python -m unittest` | `YSCBTestCase.setUp` | `[dev:test] Security Guard Blocked: Running tests directly on host workspace is forbidden` |
| `ValueError` | 指定了無效的 `--type` 或 `--target` 語法 | `Tester` | `[dev:test] Invalid target selector 'xyz'. Expected format 'module:case[.method]'` |
