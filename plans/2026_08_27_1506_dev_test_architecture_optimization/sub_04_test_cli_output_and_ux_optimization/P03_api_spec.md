# API 與介面規格說明書 (API Specification)

> 功能名稱：dev test CLI 輸出結構與資訊優化 (Dev Test CLI Output & UX Optimization)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.3  

---

## 1. 介面與型別定義 (Interface & Type Definitions)

### 1.1 `dev.testing.runner.OutputCapturer`
```python
import io
import sys
from typing import Optional

class OutputCapturer:
    """Context manager for buffering stdout and stderr during test execution."""
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._stdout_buf = io.StringIO()
        self._stderr_buf = io.StringIO()
        self._orig_stdout: Optional[Any] = None
        self._orig_stderr: Optional[Any] = None

    def __enter__(self) -> "OutputCapturer":
        if self.enabled:
            self._orig_stdout = sys.stdout
            self._orig_stderr = sys.stderr
            sys.stdout = self._stdout_buf
            sys.stderr = self._stderr_buf
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.enabled:
            if self._orig_stdout is not None:
                sys.stdout = self._orig_stdout
            if self._orig_stderr is not None:
                sys.stderr = self._orig_stderr

    def get_output(self) -> str:
        return self._stdout_buf.getvalue() + self._stderr_buf.getvalue()
```

### 1.2 `dev.testing.runner.ModuleTestMetrics`
```python
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class ModuleTestMetrics:
    module_name: str
    status: str  # "PASS" | "FAIL"
    duration: float = 0.0
    contract_passed: int = 0
    contract_total: int = 0
    custom_passed: int = 0
    custom_total: int = 0
    logic_passed: int = 0
    env_passed: int = 0
    workflow_passed: int = 0
    perf_passed: int = 0
    failures: List[Dict[str, Any]] = field(default_factory=list)
```

### 1.3 `dev.testing.runner.ASCIIReportFormatter`
```python
class ASCIIReportFormatter:
    @staticmethod
    def format_report(
        metrics_list: List[ModuleTestMetrics],
        filter_types: List[str],
        target_selector: Optional[str] = None,
        no_build: bool = False,
        total_duration: float = 0.0,
    ) -> str:
        """Render complete structured diagnostic report with metadata and failure guides."""
        ...
```

---

## 2. CLI 介面簽名更新 (`dev.tester.Tester`)

```python
class Tester:
    def run_test(
        self,
        target_module: Optional[str] = None,
        test_type: Optional[str] = None,
        all_modules: bool = False,
        contract_only: bool = False,
        keep_sandbox: bool = False,
        pattern: Optional[str] = None,
        no_build: bool = False,
        logical: bool = False,
        env: bool = False,
        workflow: bool = False,
        perf: bool = False,
        all_types: bool = False,
        target: Optional[str] = None,
        verbose: bool = False,
    ) -> int: ...
```
