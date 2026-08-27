# API 與介面規格書 (API & Interface Specification)

> 功能名稱：測試框架 Session 層級共用沙盒與效能優化 (Test Session-Level Shared Sandbox Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `YSCBTestCase` | `source/dev/dev/testing/case.py` | Public | 提供 Session-Level 共用沙盒與 Per-Method 獨立沙盒之生命週期管理。 |
| `TestRunner` | `source/dev/dev/testing/runner.py` | Public | 執行 TestSuite 並在 finally 區塊調度 Session 沙盒清理。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
class YSCBTestCase(unittest.TestCase):
    """
    YS-Codebase Core Test Fixture (Full-Fidelity Virtual Sandbox on cache://dev/sandbox/<uuid>).
    Supports shared session-level sandbox by default and per-method isolated sandbox via @require(Requirement.ISOLATED_SANDBOX).
    """
    _shared_sandbox_ctx: Optional[SandboxContext] = None
    _is_isolated_sandbox: bool = False
    _test_passed: bool
    _orig_sys_path: List[str]
    _orig_env: Dict[str, str]

    @classmethod
    def cleanup_shared_sandbox(cls) -> None:
        """
        Session-level teardown: cleanup shared sandbox when test suite execution completes.
        Safe against multiple invocations and respects YSCB_TEST_KEEP_SANDBOX.
        """
        ...

    @classmethod
    def tearDownClass(cls) -> None:
        """Class-level teardown: defensive fallback."""
        ...

    def setUp(self) -> None:
        """
        Test setup:
        1. Validates YSCB_TEST_SANDBOX security guard.
        2. Backups sys.path and os.environ.
        3. If @require(Requirement.ISOLATED_SANDBOX): provisions dedicated sandbox.
        4. Else: assigns/reuses YSCBTestCase._shared_sandbox_ctx (Session-Level).
        """
        ...

    def tearDown(self) -> None:
        """
        Test teardown:
        1. Restores sys.path and os.environ.
        2. If self._is_isolated_sandbox: tears down dedicated sandbox immediately.
        3. Else: keeps shared sandbox intact for subsequent tests in session.
        """
        ...
```

```python
class TestRunner:
    def run_suite(self, suite: unittest.TestSuite) -> Tuple[unittest.TestResult, str]:
        """
        Executes TestSuite inside sandbox environment.
        Guarantees YSCBTestCase.cleanup_shared_sandbox() is invoked in finally block.
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1] source/dev/dev/testing/case.py (升級 _shared_sandbox_ctx 與 cleanup_shared_sandbox)
   │
   ▼
[Step 2] source/dev/dev/testing/runner.py (在 run_suite 加入 finally 釋放調度)
   │
   ▼
[Step 3] 標註寫入型測試：
   ├─ source/core/tests/test_installer.py
   ├─ source/core/tests/test_engine.py
   ├─ source/core/tests/test_remote_zip_bootstrap.py
   └─ source/agents-workflow/tests/test_targets.py
   │
   ▼
[Step 4] source/dev/tests/test_case.py (更新沙盒單元測試)
```
