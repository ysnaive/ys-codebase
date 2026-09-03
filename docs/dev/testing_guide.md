# Dev 測試框架與沙盒指南 (Testing Framework & Sandbox Guide)

> 本手冊為維度 3 中觀專題手冊，定義 YS-Codebase 測試體系、三階 CLI 指令架構、完全對標微型虛擬環境 (`SandboxProvisioner`)、`scripts/hook.dev.py` 測試自治 Hook 與 `YSCBTestCase` 測試基類。

---

## 1. 三階 CLI 指令架構 (3-Tier Testing CLI Architecture)

為根除傳統測試命令「同時負責建沙盒又負責跑測試」所引發的遞迴語意陷阱，Dev 測試框架解耦為高階門面與底層原子指令：

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 高階開發者指令 (User-Facing Facade)                                    │
│   • python yscb.py dev test [mod | --all] [options]                    │
│     ➔ 完整端到端：自動執行 Hermetic dev build ➔ 調用 op-mksb 建立沙盒 │
│        ➔ 沙盒內透過標準三層鏈解析與安裝 ➔ 原地執行 op-test ➔ 銷毀      │
├────────────────────────────────────────────────────────────────────────┤
│ 底層原子操作 (Atomic Primitives)                                       │
│   1. python yscb.py dev op-mksb [--dir=<path>]                         │
│      ➔ 【純環境工廠】建立微型虛擬環境、複製 .modules/ 與 source/、廣播 Hook│
│                                                                        │
│   2. python yscb.py dev op-test [mod | --all] [options]                │
│      ➔ 【純執行引擎】在當前環境原地執行 TestDiscovery + TestRunner      │
│         100% 零沙盒建立、零遞迴                                       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 完全對標微型虛擬環境拓撲 (Virtual Sandbox Topology)

由 `SandboxProvisioner` (或 `dev op-mksb`) 建立之沙盒位於 `cache://dev/sandbox/sandbox_{timestamp}/` (`.cache/dev/sandbox/`)，嚴格劃分三大空間：

```text
.cache/dev/sandbox/sandbox_20260826_184739_990974/
  ├── mock_downstream_project/          # 【專案空間 project://】被管理之下游業務專案
  ├── host_env/                         # 【宿主空間 host_dir】
  │     ├── yscb.py                     # 宿主派發腳本（嚴格僅調用 .modules/）
  │     ├── yscb.config.json            # 宿主設定檔 (yscb_root="./engine", installed_modules)
  │     └── engine/                     # 【工具庫空間 yscb://】
  │           ├── .modules/             # 繼承父層已安裝模組 (core, dev 等，動態讀取 manifest 版本)
  │           ├── source/               # 複製待測最新源碼
  │           ├── config/               # 模組設定檔 (config/core/config.project.json)
  │           └── .cache/               # 沙盒內部快取暫存檔案
  └── mock_provider/                    # 【套件來源庫】提供 file:/// 協議之 Mock 套件
```

---

## 3. 模組測試自治 Hook 體系 (`scripts/hook.dev.py`)

為解決第三方模組初始化相依問題（如 `core` 模組需指定 `project_root` 以免拋出 `!undefined`），模組可在其根目錄提供自治測試 Hook：

### 3.1 標準 Hook 介面規範
```python
# scripts/hook.dev.py
from typing import Any

def on_test_setup(context: Any) -> None:
    """當 SandboxProvisioner 建立沙盒時調用，用於配置沙盒內模組專屬設定。"""
    pass

def on_test_teardown(context: Any) -> None:
    """沙盒銷毀前調用 (選填)。"""
    pass
```

### 3.2 Core 模組具體實作
```python
# source/core/scripts/hook.dev.py
from typing import Any

def on_test_setup(context: Any) -> None:
    # 自動為沙盒配置 core 的 project_root 指向 mock_downstream_project
    context.set_module_config("core", "config.project.json", {
        "project_root": "../mock_downstream_project"
    })
```
> **發布保證**：`dev build` 在打包模組發布產物時，會自動排除 `tests/` 但**完整保留 `scripts/hook.dev.py`**，使第三方在發布包環境下依然具備 100% 自治測試能力！

---

## 4. 核心測試基類：`YSCBTestCase`

所有單元與整合測試均應繼承 `dev.testing.YSCBTestCase`：

```python
from dev.testing import YSCBTestCase, require, Requirement
from core import uri

class TestMyFeature(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_mock_package_installation(self):
        # 1. 快速在沙盒 mock_provider 中動態合成 Mock 套件
        pkg_dir = self.create_mock_package("mock_lib", "1.0.0")
        
        # 2. 於沙盒 host_env 執行 CLI 指令
        ret, stdout, stderr = self.run_cli(["core", "install", "mock_lib"])
        self.assertSuccess(ret)
        self.assertInOutput("Successfully installed", stdout)
        
        # 3. 標記測試成功以觸發 tearDown 安全銷毀
        self.mark_passed()
```

### 4.1 需求條件裝飾器 (`@require`)
```python
from dev.testing import require, Requirement

class Requirement(Flag):
    NONE = 0
    LOGIC = auto()     # 純內部單元邏輯
    HOST_CLI = auto()  # 需呼叫 yscb.py 子程序
    NETWORK = auto()   # 需對外聯網連線（無網路時自動 Skip）
```

---

## 5. 兩階段測試探索 (Two-Phase TestDiscovery)

當執行 `dev op-test` 時，測試探索引擎會自動組裝兩階段測試：
1. **Phase 1: Auto-Contract 自動契約測試**：
   - 契約 1 (`Manifest` 必填欄位與 SemVer 合規)。
   - 契約 2 (`scripts/cli.py` 存在且具備 `main(argv)` 進入點)。
   - 契約 3 (`Builder` 純淨打包驗證)。
2. **Phase 2: 自訂業務測試 (Custom Tests)**：
   - 載入 `source/<module>/tests/test_*.py`。
   - 支援 `--type=<logic|host_cli|network>` 與 `-k <pattern>` 遞迴深度篩選。

---

## 6. 精確報表與失敗案例清單 (Accurate Diagnostics & Failure Reports)

測試執行器 (`TestRunner`) 採用嚴格分離的分類統計算法：
- **分類精準計數**：依據 TestCase 類型將通過數與失敗數分別歸屬於 `[Contract]` 與 `[Custom]`，杜絕交叉誤扣。
- **獨立失敗案例清單**：若有任何測試失敗或拋出例外，於報表底部輸出獨立清單區塊：

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Module: core                                                   [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (32/32)
[*] Module: dev                                                    [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (21/21)
----------------------------------------------------------------------
Summary : 59 Total, 59 Passed, 0 Failed, 0 Skipped (5.077s)
Status  : PASSED (100% Ready)
======================================================================
```

---

## 7. 節流輸出模式 (Throttled Output Mode - `--quiet` / `-q`)

為因應日常頻繁代碼更動後的高頻回歸測試需求，避免長篇 ASCII 診斷報表造成大量 Token I/O 浪費，Dev 測試框架提供專屬節流輸出模式：

- **觸發參數**：`--quiet` 或 `-q`（例如 `python yscb.py dev test --quiet`、`python yscb.py dev test <module> -q`、`python yscb.py dev test --all -q`）。
- **深度靜默**：徹底抑制前置沙盒構建、進度與清理日誌（`[dev:test] Pre-building...`、`Create sandbox...`、`Cleaned up sandbox...`）與通過後提示資訊。
- **全通單行極致壓縮**：若目標測試全數通過，僅輸出單行：
  ```text
  Pass: 312(100.0%), Fail: 0, Skip: 0
  ```
- **精準失敗細節保留**：若存在失敗案例，第一行輸出統計總計，緊隨輸出 `FAILED / ERROR TEST CASES LIST:` 詳情區塊（包含錯誤訊息、檔案行號、捕獲輸出與快速重測指令 Quick Re-run）。
- **跨進程環境變數穿透**：自動透過 `YSCB_TEST_QUIET="1"` 跨進程沙盒內部調度器穿透，確保多模組並行與單模組沙盒一致靜默。
- **AI 調用規範**：生態系面向 Agent 之技能手冊（`yscb-module-dev`）、工作流（`Auto.md`）與標準 SOP 手冊全面強制對齊 `--quiet`，使日常開發 Token 吞吐量縮減 95% 以上。
