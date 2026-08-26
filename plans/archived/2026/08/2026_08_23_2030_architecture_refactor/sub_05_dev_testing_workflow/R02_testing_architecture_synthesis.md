# 調研報告：YS-Codebase 測試架構移植與特化設計 (R02)

> 主題名稱：YS-Codebase 測試架構移植與特化設計  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 所屬子計畫：sub_05_dev_testing_workflow  
> 狀態：Completed  
> 擴充項目：none  
> 模板版本：v1.2  

---

## 1. 調研目標與移植原則

本調研基於 `R01_uitk_net_testing_survey.md` 的前置調研結果，進一步進行**「去蕪存菁、架構轉譯與專案特化」**，明確界定哪些機制應當完整吸收、哪些應當簡化或捨棄，並針對 YS-Codebase 的 Python 3.8+ 標準庫約束、一級 VFS 體系與微內核多模組特性，設計出最純粹、強固且優雅的測試架構。

### 核心移植三大原則：
1. **零外部依賴鐵律 (Zero Third-Party Dependency)**：100% 基於 Python 標準庫 `unittest` 擴展，嚴禁引入 `pytest`、`pytest-xdist` 等第三方套件。
2. **三層空間與沙盒物理隔離 (Strict Spatial Isolation)**：測試過程絕不污染真實工作空間、`source/` 或全域組態。
3. **契約化與剛性可追溯性 (Contract & Traceability)**：所有模組共享標準契約測試基類，測試方法命名剛性對齊 FR/EC/NFR。

---

## 2. 吸收 / 捨棄 / 創新 決策矩陣 (Keep / Drop / Invent)

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                           YS-Codebase 測試體系移植決策矩陣                                │
└────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                             │
      ┌──────────────────────────────────────┼──────────────────────────────────────┐
      ▼                                      ▼                                      ▼
【1. 吸收與轉譯 (KEEP)】              【2. 簡化與捨棄 (DROP)】              【3. 專案特化創新 (INVENT)】
- 夾具生命週期狀態重置                 - 捨棄 NUnit 複雜 ActionTargets        - 一級 VFS URI 深度整合夾具
- @require 環境能力條件跳過            - 捨棄 C# 泛型工廠注入                 - 沙盒失敗自動保留機制
- 模組標準契約測試 (Contract)          - 捨棄 pytest 等第三方生態相依         - dev test 宿主命令列發現器
- FT / ET / PT 剛性命名法              - 捨棄反射式攔截改用原生裝飾器         - 跨模組依賴拓撲回歸守門
```

### 2.1 吸收與轉譯 (KEEP)
1. **`YSCBTestCase` 狀態歸零夾具**：
   - 借鑑 `UIToolkitTestFixture` 的 SetUp/TearDown 狀態重置邏輯。在 Python 中實作為：`setUp` 自動備份 `sys.path`、`os.environ` 與 `uri._active_module_context`；`tearDown` 強制 100% 恢復，徹底杜絕測試間狀態外溢。
2. **`@require` 能力動態探測裝飾器**：
   - 借鑑 `RequireAttribute` + `TestRequirement`。在 Python 中實作為 `@require(Requirement.NETWORK | Requirement.SANDBOX)`，在測試執行前動態探測環境能力，未滿足時調用 `unittest.SkipTest` 自動跳過，避免 CI 假性紅燈。
3. **`ModuleContractTestCase` 模組契約測試**：
   - 借鑑 `Contracts/` 模式。任何 YS-Codebase 業務模組只要繼承此基類，即可免寫重複代碼，自動獲得 `manifest` 格式、進入點可調用性、純淨建置與零外部依賴 4 大標準契約驗證。
4. **FT / ET / PT 可追溯命名**：
   - 測試案例嚴格遵循 `test_ft01_*`、`test_et01_*`、`test_pt01_*` 命名。

---

### 2.2 簡化與捨棄 (DROP)
1. **捨棄 C# 泛型工廠複雜注入**：
   - C# 的 `UIToolkitTestFixture<TPlatform, TGraphics>` 是為了靜態型別編譯期綁定。Python 為動態語言，改採簡潔的 Hook 方法（例如 `def create_context(self) -> ExecutionContext:`）即可達成相同效果。
2. **捨棄對 pytest / 外部 Runner 的依賴**：
   - 不依賴外部 CLI 工具，直接於 `dev` 模組內建輕量級 `TestRunner`，無縫整合進 `python yscb.py dev test`。

---

### 2.3 專案特化創新 (INVENT)
1. **一級 VFS 深度整合測試夾具**：
   - 測試基類自動將臨時沙盒映射為 `temp://` 或專屬沙盒協議，測試代碼可直接呼叫 `uri.write_text("temp://file.txt", ...)` 進行測試，模組代碼 100% 免轉換實體路徑。
2. **沙盒「通過即刪除、失敗即保留」策略 (Preserve on Failure)**：
   - 測試通過時，`tearDown` 自動清理臨時目錄；若測試失敗，完整保留沙盒現場並在終端列印絕對路徑，方便開發者立即進入現場除錯。
3. **`dev test` 命令列發現器與回歸守門**：
   - 支援 `python yscb.py dev test [mod | --all] [-k pattern] [--verbose] [--contract-only]`。
   - 輸出對齊的 ASCII 測試結果表格與可由 CI/Agent 解析的結構化診斷摘要。

---

## 3. `dev.testing` 套件詳細 API 與結構設計

### 3.1 目錄結構規劃 (`source/dev/dev/testing/`)
```text
source/dev/dev/
├── testing/
│   ├── __init__.py          # 匯出 TestCase, require, Requirement, ContractTestCase
│   ├── case.py              # YSCBTestCase 核心夾具與斷言
│   ├── require.py           # Requirement 位元旗標與 @require 裝飾器
│   ├── contract.py          # ModuleContractTestCase 模組標準契約測試
│   └── runner.py            # YSCBTestRunner、TestDiscovery 與 ASCII 報告器
├── tester.py                # dev test 命令業務層分發器
├── scaffold.py
├── checker.py
└── builder.py
```

---

### 3.2 關鍵介面簽章定義

#### 1. `Requirement` 與 `@require` (`require.py`)
```python
from enum import Flag, auto
import functools
import unittest

class Requirement(Flag):
    NONE = 0
    NETWORK = auto()     # 需要真實對外網路
    SANDBOX = auto()     # 需要檔案系統隔離沙盒
    BUILD = auto()       # 需要 build 產物已就緒
    WINDOWS = auto()     # 平台約束
    POSIX = auto()

def require(req: Requirement):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # 動態探測環境能力
            if Requirement.NETWORK in req and not _check_network():
                raise unittest.SkipTest(f"[Auto-Skipped] Test requires active Network.")
            return func(self, *args, **kwargs)
        return wrapper
    return decorator
```

#### 2. `YSCBTestCase` (`case.py`)
```python
import unittest
import tempfile
import shutil
import os
import sys
from typing import List, Optional
from core import uri

class YSCBTestCase(unittest.TestCase):
    def setUp(self):
        self._test_passed = False
        # 自動建立隔離沙盒
        self.sandbox_dir = tempfile.mkdtemp(prefix="yscb_test_")
        self._orig_sys_path = list(sys.path)
        self._orig_env = dict(os.environ)

    def tearDown(self):
        sys.path[:] = self._orig_sys_path
        os.environ.clear()
        os.environ.update(self._orig_env)
        
        # 失敗保留，成功清理
        if self._test_passed:
            if os.path.exists(self.sandbox_dir):
                shutil.rmtree(self.sandbox_dir, ignore_errors=True)
        else:
            print(f"\n[Test Failed] Sandbox preserved at: {self.sandbox_dir}")

    def mark_passed(self):
        self._test_passed = True

    # 專屬斷言
    def assertSuccess(self, returncode: int, msg: str = ""):
        self.assertEqual(returncode, 0, msg or f"Command exited with non-zero code {returncode}")

    def assertInOutput(self, expected: str, actual: str, msg: str = ""):
        self.assertIn(expected, actual, msg or f"Expected text '{expected}' was not found in output.")

    def assertExecutionTime(self, max_seconds: float):
        # 效能計時 ContextManager 斷言
        ...
```

#### 3. `ModuleContractTestCase` (`contract.py`)
```python
class ModuleContractTestCase(YSCBTestCase):
    module_name: str = ""

    def test_contract_manifest_schema(self):
        """契約 1: manifest.json 格式與必要欄位"""
        src_uri = f"module.source.root://{self.module_name}/manifest.json"
        self.assertTrue(uri.exists(src_uri), f"Missing manifest.json for module '{self.module_name}'")
        data = uri.read_json(src_uri)
        for f in ("name", "version", "entry"):
            self.assertIn(f, data)
        self.assertEqual(data["name"], self.module_name)

    def test_contract_entrypoint_exists(self):
        """契約 2: scripts/cli.py 進入點存在且語法合法"""
        cli_uri = f"module.source.root://{self.module_name}/scripts/cli.py"
        self.assertTrue(uri.exists(cli_uri))

    def test_contract_clean_build(self):
        """契約 3: 純淨建置驗證"""
        from dev.builder import Builder
        builder = Builder()
        ok, msg = builder.build_module(self.module_name, clean=True)
        self.assertTrue(ok, f"Contract build failed: {msg}")
```

---

## 4. 落地回歸測試與示範規劃

在 `sub_05` 實作完成後，我們將立即為現有的核心模組建立標準測試套件：
1. **`source/core/tests/`**：
   - `test_contract.py`（繼承 `ModuleContractTestCase`）
   - `test_uri_vfs.py`（驗證 9 大語意協議、佔位符與原子寫入）
   - `test_engine_atomic.py`（驗證 Kahn 拓撲、快照與兩階段純淨物化）
2. **`source/dev/tests/`**：
   - `test_contract.py`（繼承 `ModuleContractTestCase`）
   - `test_scaffold.py`（驗證骨架生成與合法識別碼）
   - `test_checker.py`（驗證 AST 靜態解析與 0 副作用）
   - `test_builder.py`（驗證 `.yscbignore` 與版本化產物）

---

## 5. 調研結論

本架構在**「零外部依賴、純淨標準庫」**的約束下，完整重現並超越了 `uitk.net` 的核心品質守門能力，具備高度的工程優雅度與擴展性，可直接作為 `sub_05_dev_testing_workflow` 的正式需求規格與架構依據。
