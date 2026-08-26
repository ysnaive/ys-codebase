# 詳細介面規範書 (API Specification)

> 功能名稱：開發者測試框架與全自動契約回歸工作流 (Dev Testing Framework & Regression Workflow)
> 建立日期：2026-08-24
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)
> 狀態：Draft
> 擴充項目：none
> 模板版本：v1.2

---

## 1. 型別與列舉宣告 (Types & Enumerations)

### 1.1 `dev.testing.require.Requirement`
```python
from enum import Flag, auto

class Requirement(Flag):
    """
    測試環境能力需求位元旗標 (借鑑 uitk.net TestRequirement)。
    """
    NONE = 0                 # 純邏輯運算，無任何環境需求 (Level 1)
    SANDBOX = auto()         # 需要檔案系統臨時沙盒讀寫 (Level 2)
    HOST_CLI = auto()        # 需要宿主子進程與 Python CLI 執行環境 (Level 3)
    NETWORK = auto()         # 需要真實對外網路連線 (Level 4)
```

---

## 2. 核心介面與類別定義 (Core Interfaces)

### 2.1 條件探測裝飾器：`dev.testing.require.require`
```python
from typing import Callable, Any
import functools
import unittest
import urllib.request

def is_network_available(timeout: float = 2.0) -> bool:
    """探測對外網路是否可用"""
    try:
        urllib.request.urlopen("https://raw.githubusercontent.com", timeout=timeout)
        return True
    except Exception:
        return False

def require(requirement: Requirement) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    環境能力探測裝飾器。若當前環境未滿足 requirement，自動觸發 unittest.SkipTest 優雅跳過。
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            if Requirement.NETWORK in requirement and not is_network_available():
                raise unittest.SkipTest("[Auto-Skipped] Test requires active Network connection.")
            return func(self, *args, **kwargs)
        return wrapper
    return decorator
```

---

### 2.2 測試基礎類別：`dev.testing.case.YSCBTestCase`
```python
import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
import unittest
from contextlib import contextmanager
from typing import List, Optional, Dict, Any, Tuple, Iterator
from core import uri

class YSCBTestCase(unittest.TestCase):
    """
    YS-Codebase 核心測試夾具基類 (借鑑 uitk.net UIToolkitTestFixture)。
    """
    sandbox_dir: str
    _test_passed: bool
    _orig_sys_path: List[str]
    _orig_env: Dict[str, str]

    def setUp(self) -> None:
        """測試前置：建立獨立專案沙盒，備份環境變數與 sys.path。"""
        self._test_passed = False
        self.sandbox_dir = tempfile.mkdtemp(prefix="yscb_test_")
        self._orig_sys_path = list(sys.path)
        self._orig_env = dict(os.environ)

    def tearDown(self) -> None:
        """測試後置：強制恢復環境；若通過則清空沙盒，失敗則保留沙盒現場供除錯。"""
        sys.path[:] = self._orig_sys_path
        os.environ.clear()
        os.environ.update(self._orig_env)
        
        # 失敗保留策略 (Preserve on Failure)
        if self._test_passed:
            if os.path.exists(self.sandbox_dir):
                shutil.rmtree(self.sandbox_dir, ignore_errors=True)
        else:
            print(f"\n[Test Failed] Sandbox preserved at: {self.sandbox_dir}")

    def mark_passed(self) -> None:
        """標記本測試案例已通過。"""
        self._test_passed = True

    # 專屬斷言庫
    def assertSuccess(self, returncode: int, msg: str = "") -> None:
        """斷言 Exit Code 為 0。"""
        self.assertEqual(returncode, 0, msg or f"Expected exit code 0, got {returncode}")

    def assertFailed(self, returncode: int, msg: str = "") -> None:
        """斷言 Exit Code 非 0。"""
        self.assertNotEqual(returncode, 0, msg or "Expected non-zero exit code, got 0")

    def assertInOutput(self, expected: str, actual: str, msg: str = "") -> None:
        """斷言終端輸出包含指定字串。"""
        self.assertIn(expected, actual, msg or f"Expected '{expected}' in output: {actual}")

    def assertFileExists(self, path_or_uri: str, msg: str = "") -> None:
        """斷言實體路徑或語意 URI 存在。"""
        real_path = uri.resolve(path_or_uri) if uri.is_uri(path_or_uri) else path_or_uri
        self.assertTrue(os.path.exists(real_path), msg or f"File not found: {path_or_uri}")

    def assertJsonEquals(self, expected: Dict[str, Any], path_or_uri: str, msg: str = "") -> None:
        """讀取指定路徑的 JSON 檔案並斷言內容一致。"""
        self.assertFileExists(path_or_uri, msg)
        real_path = uri.resolve(path_or_uri) if uri.is_uri(path_or_uri) else path_or_uri
        with open(real_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data, expected, msg or f"JSON mismatch at {path_or_uri}")

    @contextmanager
    def assertExecutionTime(self, max_seconds: float) -> Iterator[None]:
        """斷言程式碼區塊執行耗時小於 max_seconds。"""
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        self.assertLessEqual(elapsed, max_seconds, f"Execution took {elapsed:.4f}s > {max_seconds:.4f}s")

    def run_cli(self, args: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
        """於指定目錄執行 yscb 宿主子進程命令。"""
        work_dir = cwd or self.sandbox_dir
        yscb_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "yscb.py"))
        if not os.path.isfile(yscb_script):
            yscb_script = os.path.abspath("yscb.py")
        
        cmd = [sys.executable, yscb_script] + args
        p_env = dict(os.environ)
        if env:
            p_env.update(env)
        res = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True, env=p_env)
        return res.returncode, res.stdout, res.stderr
```

---

### 2.3 全自動模組標準契約測試：`dev.testing.contract`
```python
import unittest
from typing import Type
from core import uri
from dev.testing.case import YSCBTestCase

class BaseModuleContractTestCase(YSCBTestCase):
    """
    標準模組規格契約測試基類 (借鑑 uitk.net Contract Testing)。
    由測試引擎自動合成實例化，開發者無需在 tests/ 手寫任何樣板程式碼。
    """
    module_name: str = ""

    def test_contract_manifest_schema(self) -> None:
        """契約 1: 檢查 manifest.json 必要欄位 (name, version, entry) 與 SemVer 格式。"""
        src_uri = f"module.source.root://{self.module_name}/manifest.json"
        self.assertTrue(uri.exists(src_uri), f"Missing manifest.json for module '{self.module_name}'")
        data = uri.read_json(src_uri)
        for field in ("name", "version", "entry"):
            self.assertIn(field, data, f"Missing field '{field}' in manifest.json")
        self.assertEqual(data["name"], self.module_name, "Module name mismatch in manifest.json")
        self.mark_passed()

    def test_contract_entrypoint_valid(self) -> None:
        """契約 2: 檢查 scripts/cli.py 進入點存在、可導入且具備 main(argv) 簽名。"""
        from dev.checker import Checker
        checker = Checker()
        passed, errors = checker.check_module(self.module_name)
        self.assertTrue(passed, f"Contract entrypoint check failed: {errors}")
        self.mark_passed()

    def test_contract_clean_build(self) -> None:
        """契約 3: 檢查 dev build 能純淨打包至版本化目錄 build/<mod>/<ver>/。"""
        from dev.builder import Builder
        builder = Builder()
        passed, msg = builder.build_module(self.module_name, clean=True)
        self.assertTrue(passed, f"Contract clean build failed: {msg}")
        self.mark_passed()


def make_contract_suite(module_name: str) -> unittest.TestSuite:
    """
    全自動契約測試工廠函式 (Auto-Contract Suite Factory)：
    為指定模組動態合成專屬 Contract 測試類別並封裝為 TestSuite。
    """
    class_name = f"{module_name.capitalize()}AutoContractTestCase"
    dynamic_case_cls = type(
        class_name,
        (BaseModuleContractTestCase,),
        {"module_name": module_name}
    )
    loader = unittest.TestLoader()
    return loader.loadTestsFromTestCase(dynamic_case_cls)
```

---

### 2.4 測試發現與執行引擎：`dev.testing.runner.TestRunner`
```python
class TestDiscovery:
    """測試套件發現器"""
    @staticmethod
    def discover_modules(target: Optional[str] = None) -> List[str]:
        """發現 source/ 下的目標模組清單。"""
        ...

    @staticmethod
    def build_suite_for_module(
        module_name: str, 
        test_type: Optional[str] = None,
        pattern: Optional[str] = None,
        contract_only: bool = False
    ) -> unittest.TestSuite:
        """
        兩階段動態測試套件組裝：
        - 階段 1：動態生成 SynthesizedContractSuite(module_name)
        - 階段 2：若非 contract_only 且 tests/ 存在，加載自訂測試案例
        """
        ...

class TestRunner:
    """測試執行與報告彙總器"""
    def __init__(self, verbose: bool = False, keep_sandbox: bool = False):
        self.verbose = verbose
        self.keep_sandbox = keep_sandbox

    def run(self, suite: unittest.TestSuite) -> Tuple[bool, Dict[str, Any]]:
        """執行測試並返回 (passed, summary_dict)。"""
        ...

class ASCIIReportFormatter:
    """ASCII 結構化報告格式化器"""
    @staticmethod
    def format_summary(summary_data: Dict[str, Any]) -> str:
        """產生對齊之終端 ASCII 統計表。"""
        ...
```

---

### 2.5 `dev test` 命令業務派發器：`dev.tester.Tester`
```python
class Tester:
    def __init__(self):
        self.runner = TestRunner()

    def run(self, argv: List[str]) -> int:
        """
        解析 argv 參數並執行測試：
        - python yscb.py dev test [mod | --all]
        - 支援 --type=logic|sandbox|host|network
        - 支援 -k pattern, --verbose, --keep-sandbox, --contract-only
        """
        ...
```

---

## 3. CLI 語法規範 (CLI Syntax Spec)

```powershell
python yscb.py dev test [module_name | --all] [options]

選項說明：
  --all              掃描並執行 source/ 下所有模組的測試
  --type=<type>      過濾運行類型 (logic | sandbox | host | network)
  -k <pattern>       僅執行方法名稱符合 pattern 的測試案例
  --contract-only    僅執行全自動標準規格契約守門測試
  --verbose, -v      顯示每個案例的詳細執行過程與 Traceback
  --keep-sandbox     強制保留所有沙盒目錄（無論測試成功或失敗）
```
