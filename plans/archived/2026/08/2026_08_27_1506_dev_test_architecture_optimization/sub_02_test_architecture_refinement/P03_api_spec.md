# API 與介面規格書 (API & Interface Specification)

> 功能名稱：測試架構完善 (Test Architecture Refinement)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `Requirement.ISOLATED_SANDBOX` | `source/dev/dev/testing/requirement.py` | Public | 標記測試案例需使用專屬 Per-Method 獨立沙盒之 Flag。 |
| `YSCBTestCase` | `source/dev/dev/testing/case.py` | Public | 基底測試類別，實作 Class-level 共用沙盒與 Per-Method 獨立沙盒分流，並管理 `YSCB_TEST_SANDBOX` 環境變數。 |
| `reconcile_undefined_uri` | `source/core/core/uri.py` | Public | 協議未定義路徑之 JIT 互動解析器，檢測 `YSCB_TEST_SANDBOX=1` 時靜默拋出 `UndefinedURIError`。 |
| `TestRunner` | `source/dev/dev/testing/runner.py` | Public | 測試套件執行器，執行期間確保 `YSCB_TEST_SANDBOX=1`。 |
| `Tester._run_test` | `source/dev/dev/tester.py` | Internal | 高階測試調度器，執行期間確保 `YSCB_TEST_SANDBOX=1`。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `Requirement.ISOLATED_SANDBOX` 列舉宣告
```python
# source/dev/dev/testing/requirement.py
from enum import Flag, auto

class Requirement(Flag):
    NONE = 0
    LOGIC = auto()            # Pure in-memory / unit logic test
    HOST_CLI = auto()         # Subprocess invocation required
    NETWORK = auto()          # Active network connection required
    ISOLATED_SANDBOX = auto() # Dedicated per-test isolated sandbox required
```

### 2.2 `YSCBTestCase` 智慧沙盒分流與環境透傳
```python
# source/dev/dev/testing/case.py
class YSCBTestCase(unittest.TestCase):
    ctx: SandboxContext
    sandbox_id: str
    sandbox_uri: str
    sandbox_dir: str
    sandbox_host_dir: str
    sandbox_project_dir: str
    sandbox_provider_dir: str
    
    _class_sandbox_ctx: Optional[SandboxContext] = None
    _is_isolated_sandbox: bool = False
    _test_passed: bool
    _orig_sys_path: List[str]
    _orig_env: Dict[str, str]

    @classmethod
    def tearDownClass(cls) -> None:
        """類別測試全數結束後，統一銷毀共用沙盒實例。"""
        if cls._class_sandbox_ctx is not None:
            keep_all = os.environ.get("YSCB_TEST_KEEP_SANDBOX", "0") == "1"
            if not keep_all:
                SandboxProvisioner.cleanup_sandbox(cls._class_sandbox_ctx.sandbox_dir, force=True)
            cls._class_sandbox_ctx = None

    def setUp(self) -> None:
        """
        1. 設置 os.environ["YSCB_TEST_SANDBOX"] = "1"
        2. 備份 sys.path 與 os.environ
        3. 檢查當前測試方法是否標記 Requirement.ISOLATED_SANDBOX：
           - 若有：建立專屬 self.ctx，標記 _is_isolated_sandbox = True
           - 若無：延遲初始化 / 複用 cls._class_sandbox_ctx，標記 _is_isolated_sandbox = False
        4. 填充 self.sandbox_* 屬性
        """
        ...

    def tearDown(self) -> None:
        """
        1. 還原 sys.path 與 os.environ
        2. 若為 _is_isolated_sandbox：
           - 通過且未要求 keep：即時銷毀專屬沙盒
           - 失敗：印出保留路徑並依保留上限滾動管理
        """
        ...

    def run_cli(
        self,
        args: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
    ) -> Tuple[int, str, str]:
        """
        於沙盒子行程執行 CLI，自動將 YSCB_TEST_SANDBOX="1" 併入子行程環境變數。
        """
        ...
```

### 2.3 `core.uri.reconcile_undefined_uri` 非互動環境防護
```python
# source/core/core/uri.py
def reconcile_undefined_uri(
    scheme_token: str,
    raw_target: str,
    provider: Optional[str] = None,
    config_binding: Optional[str] = None,
    description: Optional[str] = None,
    interactive: bool = True
) -> str:
    """
    非互動判斷規則：
    is_test_env = os.environ.get("YSCB_TEST_SANDBOX") == "1"
    is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
    if is_test_env or not interactive or not is_tty:
        raise UndefinedURIError(scheme=scheme_token, provider=provider_name, binding=binding_key)
    ...
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Core 協議層]
  source/core/core/uri.py (reconcile_undefined_uri 加入 YSCB_TEST_SANDBOX 判定)
       |
       v
[Step 2: Core 測試層]
  source/core/tests/test_uri.py (測試 YSCB_TEST_SANDBOX=1 時靜默拋出例外)
       |
       v
[Step 3: Dev 需求層]
  source/dev/dev/testing/requirement.py (加入 Requirement.ISOLATED_SANDBOX)
       |
       v
[Step 4: Dev TestCase 層]
  source/dev/dev/testing/case.py (實作智慧沙盒分流、tearDownClass 與 run_cli 透傳)
       |
       v
[Step 5: Dev 執行器與調度層]
  source/dev/dev/testing/runner.py & source/dev/dev/tester.py (注入 YSCB_TEST_SANDBOX)
       |
       v
[Step 6: Dev 測試層]
  source/dev/tests/test_requirement.py & source/dev/tests/test_case.py (新增單元測試)
```
