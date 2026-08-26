# 調研報告：uitk.net 測試框架架構深度剖析與 YS-Codebase 測試引擎借鑑方案

> 主題名稱：uitk.net 測試框架架構調研與 YS-Codebase 借鑑方案  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)\n> 所屬子計畫：sub_05_dev_testing_workflow  
> 狀態：Completed  
> 擴充項目：none  
> 模板版本：v1.2  

---

## 1. 調研背景與目標

在 YS-Codebase 即將啟動 `sub_05_dev_testing_workflow` 之際，為了避免設計出過於簡陋或難以支撐大型多模組生態的測試工具，我們對具備高成熟度測試架構的跨平台框架 **`uitk.net`**（本機路徑：`H:\UseFolder\CodeRepo\uitk.net\tests\UIToolkit.Tests`）進行了全面的源碼級架構調研。

本調研旨在提煉 `uitk.net` 在**測試夾具 (Fixture) 生命週期管理、環境能力動態探測與優雅跳過 (`RequireAttribute`)、契約測試 (Contract Tests)、VFS 測試隔離以及 FT/ET/PT 剛性可追溯命名**上的設計模式，並給出 YS-Codebase 在 Python 3.8+ 標準庫約束下的 Pythonic 移植與落地藍圖。

---

## 2. `uitk.net` 測試架構 5 大核心亮點深度剖析

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                             uitk.net 測試體系架構全貌                                    │
└────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                             │
      ┌──────────────────────────────────────┼──────────────────────────────────────┐
      ▼                                      ▼                                      ▼
【1. 基礎夾具層 Fixture】             【2. 條件探測層 Requirement】       【3. 測試金字塔層 Taxonomy】
- UIToolkitTestFixture                 - TestRequirement (位元旗標)         - Contracts (契約測試)
- Hook Factory Pattern (Platform,      - RequireAttribute (BeforeTest)       - Core/Asset (VFS 原子寫入)
  GraphicsBackend)                     - 自動識別 Headless / CI / Display    - UI/E2E (端到端全流程)
- SetUp/TearDown 嚴格狀態歸零          - 未滿足自動 Assert.Ignore            - Benchmarks (記憶體/效能)
```

### 2.1 亮點一：雙層夾具基類與 Hook 工廠模式 (`UIToolkitTestFixture`)
- **生命週期重置鐵律**：在 `[SetUp]` 中強制清空日誌 Sinks (`Log.clearSinks()`) 並執行 `Application.ResetForTesting()`；在 `[TearDown]` 強制退出並歸零所有成員引用，保證**測試案例間 100% 物理隔離、零狀態殘留**。
- **Hook Factory 模式**：
  ```csharp
  protected virtual IPlatform CreatePlatform() => new HeadlessPlatform();
  protected virtual IGraphicsBackend CreateGraphicsBackend() => new HeadlessGraphicsBackend();
  ```
  基類預設提供 Headless 虛擬實作，同時提供泛型基類 `UIToolkitTestFixture<TPlatform, TGraphics>`，允許特定測試派生自定義平台與後端，兼具極簡預設值與超高擴展性。

---

### 2.2 亮點二：環境能力動態探測與優雅條件跳過 (`RequireAttribute` + `TestRequirement`)
- **問題痛點**：許多整合/E2E 測試需要特定的硬體（如 GPU、音效卡、真實 Display）或特定環境變數。在無顯卡的 CI 或沙盒環境執行時，傳統測試會直接報錯 Crash，造成「假性失敗 (False Positive)」。
- **`uitk.net` 解法**：
  1. 定義能力位元旗標 `TestRequirement`：
     ```csharp
     [Flags]
     public enum TestRequirement {
         None = 0,
         Platform = 1 << 0,
         GraphicBackend = 1 << 1,
         FullHost = Platform | GraphicBackend
     }
     ```
  2. 透過 `[Require(TestRequirement.Platform)]` 宣告測試需求。
  3. `BeforeTest` 自動探測環境（例如 `CI != null && DISPLAY == null`）；若條件不符，自動調用 **`Assert.Ignore("[Auto-Skipped] ...")`** 優雅跳過，不破壞 CI 綠燈。

---

### 2.3 亮點三：契約測試體系 (Contract Testing Pattern)
- 在 `tests/UIToolkit.Tests/Contracts/` 中建立了 `GraphicsBackendContractTests.cs` 與 `PlatformContractTests.cs`。
- **核心價值**：契約測試只針對「介面規範與行為準則」編寫。未來無論新增任何新的後端（如 Headless、SDL、DirectX、Vulkan），只需讓該後端的測試套件繼承契約測試基類，即可**自動繼承數十項標準合規性驗證**，杜絕實作偏離標準。

---

### 2.4 亮點四：VFS 虛擬檔案系統深度測試矩陣 (`VFSTests.cs`)
- 測試覆蓋了 `VFS_Sync_TextAndBinary_ReadWrite`、`VFS_AtomicWrite_PreventsCorruption` 等核心操作。
- 專門針對**「原子寫入 (Atomic Write) 防止併發損壞」**與**「跨協議路徑解析」**建立了斷言標準，這與 YS-Codebase 的 `core.uri` 一級 VFS 完全同構。

---

### 2.5 亮點五：FT / ET / PT / UX 剛性可追溯命名法
- 測試方法嚴格命名：
  - `FT01_...`（Functional Test，對應功能需求 FR）
  - `ET01_...`（Edge-case Test，對應邊界防護 EC）
  - `PT01_...`（Performance Test，對應非功能效能 NFR，例如斷言 Setup/TearDown 耗時 < 10ms）
- 每個測試方法內部嚴格落實 **`Arrange / Act / Assert / Cleanup`** 四段式結構，代碼極度工整。

---

## 3. 橫向對比評估矩陣 (Candidate Comparison Matrix)

| 維度 | YS-Codebase 原初草案 | uitk.net 成熟架構 | YS-Codebase 吸收升級方案 (sub_05) |
| :--- | :--- | :--- | :--- |
| **底層基底** | 純 `unittest` 簡易封裝 | NUnit 3 擴展 | 基於 Python 標準庫 `unittest` + 自研 Pythonic 擴展 |
| **環境能力探測** | 無（硬跑，依賴手動過濾） | `RequireAttribute` + `TestRequirement` | **`@require(Requirement.Sandbox | Network)`** 裝飾器 + `skipTest` |
| **沙盒隔離機制** | 手動建立 temp 目錄 | `UIToolkitTestFixture` 嚴格生命週期 | **`YSCBTestCase`** 內建自動沙盒 + 失敗自動保留路徑 |
| **契約測試能力** | 無 | `Contracts/` 介面契約測試基類 | 建立 **`ModuleContractTestCase`** 標準模組契約測試 |
| **測試可追溯性** | 測試清單散落 | 嚴格 `FT/ET/PT` 命名法 | 剛性要求所有測試方法遵循 **`test_ftXX_*` / `test_etXX_*`** 命名 |
| **效能與記憶體** | 無監控 | `Benchmarks/` 耗時與 GC 測試 | 提供 **`assertExecutionTime`** 與 GC 引用檢查輔助 |

---

## 4. YS-Codebase 測試框架 (`dev test`) 移植落地設計

結合 Python 3.8+ 標準庫零外部相依原則，我們將 `uitk.net` 的精髓轉譯為以下 Pythonic 實作架構：

### 4.1 測試基礎類別：`dev.testing.YSCBTestCase`
```python
import os
import sys
import unittest
import tempfile
import shutil
from typing import List, Optional
from core import uri

class YSCBTestCase(unittest.TestCase):
    """
    YS-Codebase 標準測試夾具基類 (借鑑 uitk.net UIToolkitTestFixture)。
    """
    def setUp(self):
        # 1. 建立該測試案例專屬的隔離沙盒目錄
        self._test_passed = False
        self.sandbox_dir = tempfile.mkdtemp(prefix="yscb_test_")
        self.sandbox_uri = uri.to_uri(self.sandbox_dir) if hasattr(uri, 'to_uri') else self.sandbox_dir
        
        # 2. 備份全域環境變數與 sys.path
        self._orig_sys_path = list(sys.path)
        self._orig_env = dict(os.environ)

    def tearDown(self):
        # 3. 恢復全域環境
        sys.path[:] = self._orig_sys_path
        os.environ.clear()
        os.environ.update(self._orig_env)
        
        # 4. 沙盒清理策略：通過自動刪除，失敗保留
        if self._test_passed:
            if os.path.exists(self.sandbox_dir):
                shutil.rmtree(self.sandbox_dir, ignore_errors=True)
        else:
            print(f"\n[Test Failed] Sandbox preserved at: {self.sandbox_dir}")

    # 自訂斷言介面
    def assertSuccess(self, returncode: int, msg: str = ""):
        self.assertEqual(returncode, 0, msg or f"Command failed with exit code {returncode}")

    def assertInOutput(self, expected: str, actual: str, msg: str = ""):
        self.assertIn(expected, actual, msg or f"Expected '{expected}' in output.")

    def run_cli(self, args: List[str], cwd: Optional[str] = None) -> int:
        """封裝宿主或模組 CLI 調用"""
        ...
```

---

### 4.2 能力需求條件探測裝飾器：`@require`
```python
from enum import Flag, auto
import functools

class Requirement(Flag):
    NONE = 0
    NETWORK = auto()     # 需要真實網路連線
    SANDBOX = auto()     # 需要沙盒隔離權限
    FULL_BUILD = auto()  # 需要 build 產物完備

def require(requirement: Requirement):
    """
    借鑑 uitk.net RequireAttribute：測試前動態探測環境，未滿足時自動呼叫 skipTest。
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if Requirement.NETWORK in requirement and not _is_network_available():
                raise unittest.SkipTest("[Auto-Skipped] Test requires active Network connection.")
            return func(self, *args, **kwargs)
        return wrapper
    return decorator
```

---

### 4.3 模組標準契約測試：`dev.testing.ModuleContractTestCase`
```python
class ModuleContractTestCase(YSCBTestCase):
    """
    模組標準契約測試基類 (借鑑 uitk.net Contract Testing)。
    任何新模組只需繼承此類，即可自動執行標準規範檢驗：
    - test_contract_manifest_schema
    - test_contract_entrypoint_exists
    - test_contract_clean_build
    """
    module_name: str = ""

    def test_contract_manifest_schema(self):
        self.assertTrue(self.module_name, "module_name must be defined in subclass.")
        ...
```

---

## 5. 調研結論與後續執行指引

1. **結論**：`uitk.net` 的測試架構非常嚴謹成熟，其「**雙層 Fixture 生命週期、Require 動態能力探測、契約測試、VFS 原子測試與 FT/ET/PT 規範**」完全可以直接轉譯為 YS-Codebase 的測試核心架構。
2. **對 `sub_05` 的具體指引**：
   - 在 `sub_05` 中實作 `dev.testing` 套件（包含 `YSCBTestCase`, `@require`, `Requirement`, `ModuleContractTestCase`）。
   - 在 `source/dev/dev/tester.py` 中實作支援標籤過濾、發現、彩色 ASCII 報告與失敗保留沙盒的 `TestRunner`。
   - 為現有的 `core` 與 `dev` 模組建立標準的 `tests/test_basic.py` 與 `tests/test_contract.py`，作為全專案回歸測試示範。
