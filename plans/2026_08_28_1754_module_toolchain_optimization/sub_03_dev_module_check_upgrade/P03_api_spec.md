# API 與介面規格說明書 (API Specification)

> 功能名稱：Dev 模組狀態檢核工具升級 (Dev Module Check & Diagnostics Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_03)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 核心檢查器介面規格 (`dev.checker.Checker`)

模組路徑：`source/dev/dev/checker.py`

### 1.1 資料結構與公開 API

```python
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple, Any

class CheckSeverity(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"

@dataclass
class CheckIssue:
    severity: CheckSeverity
    category: str        # "MANIFEST", "CONTRIBUTES", "PROBING", "STRUCTURE", "ANTIPATTERN", "SYNTAX"
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典格式 (供 --json 輸出使用)。"""

@dataclass
class CheckReport:
    module: str
    status: CheckSeverity
    issues: List[CheckIssue]

    @property
    def has_fails(self) -> bool:
        return any(i.severity == CheckSeverity.FAIL for i in self.issues)

    @property
    def has_warns(self) -> bool:
        return any(i.severity == CheckSeverity.WARN for i in self.issues)

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典格式。"""


class Checker:
    """模組靜態合規與架構守門檢查器。"""

    def check_module(self, name: str) -> CheckReport:
        """
        執行單一模組之 5 步流水線完整檢核。
        :param name: 模組名稱 (如 "agents-workflow", "knowledge-db", "core")
        :return: 結構化檢核報告 CheckReport
        """

    def check_all(self) -> Dict[str, CheckReport]:
        """
        掃描並檢核 module.source:// 下所有可用模組。
        :return: 模組名稱至 CheckReport 之對應字典
        """
```

---

## 2. 發布守門閘門介面升級 (`dev.releaser.Releaser`)

模組路徑：`source/dev/dev/releaser.py`

```python
class Releaser:
    def __init__(self):
        self.checker = Checker()

    def build_release_package(self, module_name: str, force: bool = False) -> Tuple[bool, str, List[str]]:
        """
        建置正式發布包。在打包前自動執行 Checker.check_module(module_name)。
        若 check_module 報告中 has_fails 為 True，剛性中斷打包並回傳 (False, "", errors)。
        """
```

---

## 3. CLI 指令與輸出規格 (`dev.scripts.cli`)

進入點：`source/dev/scripts/cli.py`

### 3.1 指令語法與參數

| 指令 | 參數 | 說明 |
| :--- | :--- | :--- |
| `dev check` | `<module_name>` | 檢核指定單一模組 |
| `dev check` | `--all` / `-a` | 檢核全生態系所有源碼模組 |
| `dev check` | `--json` | 以 JSON 格式輸出完整診斷結果 |

### 3.2 終端輸出格式範例

```text
======================================================================
YS-Codebase Module Compliance Diagnostic Report
======================================================================
[*] Module: agents-workflow                                     [PASS]
[*] Module: knowledge-db                                        [WARN]
    |-- [WARN] [CONTRIBUTES] Module lacks 'contributes.format.md' documentation.
[*] Module: invalid-mod                                         [FAIL]
    |-- [FAIL] [MANIFEST] 'dependencies' must include 'core' module.
    |-- [FAIL] [ANTIPATTERN] Direct access to 'config.project.json' detected at invalid_mod/foo.py:24.
----------------------------------------------------------------------
Summary : 3 Modules, 1 Passed, 1 Warnings, 1 Failed
Status  : FAILED (Release Blocked)
======================================================================
```

---

## 4. 拓撲實作順序 (Implementation Topology)

```text
[TASK-01] 升級 source/dev/dev/checker.py (實作 CheckIssue, CheckReport 與 5 步檢核流水線)
    │
    ▼
[TASK-02] 升級 source/dev/dev/releaser.py (在 release 流程整合 has_fails 守門阻斷)
    │
    ▼
[TASK-03] 升級 source/dev/scripts/cli.py (實作 cmd_check 彩色輸出與 --json 格式化)
    │
    ▼
[TASK-04] 編寫單元測試 source/dev/tests/test_checker.py 並進行全模組回歸驗證
```
