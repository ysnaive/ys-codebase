# API 與介面規格書 (API & Interface Specification)

> 功能名稱：core_dev_test_case_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `TestDevTester` | `source/dev/tests/test_tester.py` | Internal / Test | 驗證合約自動合成、測試套件建置與 safe_print 安全編碼防護 |
| `TestDevTesterSync` | `source/dev/tests/test_tester.py` | Internal / Test | 驗證測試完成後之自動本地物化同步流程 (`--sync`) |
| `TestDevTesterThrottle` | `source/dev/tests/test_tester.py` | Internal / Test | 驗證 `--quiet` 節流模式報表生成、零輸出與錯誤詳情展示 |
| `TestCLIRouterAndGuild` | `source/core/tests/test_cli_router.py` | Internal / Test | 驗證 yscb.py 主入口 CLI 說明看板、拼寫建議演算法與 Guild 權限規範 |
| `TestCoreContributes` | `source/core/tests/test_contributes.py` | Internal / Test | 驗證貢獻清冊聚合、Provider 標記與 JIT 快取髒檢查自癒 |
| `TestPipManagerSDK` | `source/core/tests/test_pip_manager_sdk.py` | Internal / Test | 驗證 PipManager SDK 導出、相依性宣告解析與空白/極值邊界防護 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 Dev 測試整合簽名 (`source/dev/tests/test_tester.py`)

```python
class TestDevTesterSync(YSCBTestCase):
    """整合自原 test_tester_sync.py，驗證 --sync 後置安裝調度。"""
    def test_handle_post_test_sync_flow(self) -> None:
        """合併驗證 prompt-only 與 --sync 旗標自動觸發 install 之雙軌行為。"""
        ...

class TestDevTesterThrottle(YSCBTestCase):
    """整合自原 test_tester_throttle.py，驗證節流格式化與靜默調度。"""
    def test_format_throttled_comprehensive(self) -> None:
        """合併驗證全通、全跳過、空案例與帶有失敗/worker 錯誤之格式化輸出。"""
        ...
```

### 2.2 Core CLI 路由整合簽名 (`source/core/tests/test_cli_router.py`)

```python
class TestCLIRouterAndGuild(YSCBTestCase):
    """整合自原 test_cli_help.py 與 test_cli_guild.py。"""
    def test_cli_help_and_spelling_suggestion(self) -> None:
        """驗證全域說明結構、difflib 拼寫建議與未知指令自動推薦提示。"""
        ...
    def test_cli_guild_compliance_and_table_generation(self) -> None:
        """驗證 CLI Guild Markdown 表格生成與自主安全/階段條件/授權守門矩陣。"""
        ...
```

### 2.3 WORKFLOW 重型沙盒測試標註範式

```python
from dev.testing import YSCBTestCase, require, Requirement

# 凡實質建立沙盒實體或調度子行程跑測之重型案例，必須明確裝飾：
@require(Requirement.WORKFLOW)
def test_heavy_sandbox_e2e_flow(self):
    ctx = SandboxProvisioner.create_sandbox()
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: 【Dev 模組收斂】
  ├── 更新 source/dev/tests/test_tester.py (注入 TestDevTesterSync, TestDevTesterThrottle)
  ├── 刪除 source/dev/tests/test_tester_sync.py
  ├── 刪除 source/dev/tests/test_tester_throttle.py
  └── 標註 source/dev/tests/test_sandbox.py 之重型案例為 @require(Requirement.WORKFLOW)

Step 2: 【Core 模組收斂】
  ├── 建立 source/core/tests/test_cli_router.py (整合 help + guild)
  ├── 刪除 source/core/tests/test_cli_help.py
  ├── 刪除 source/core/tests/test_cli_guild.py
  ├── 更新 source/core/tests/test_contributes.py (整合 JIT 自癒案例)
  ├── 刪除 source/core/tests/test_contributes_jit.py
  ├── 緊湊化 source/core/tests/test_pip_manager_sdk.py
  └── 標註 source/core/tests/test_engine.py 之重型快照/鎖案例為 @require(Requirement.WORKFLOW)

Step 3: 【回歸與基線驗證】
  ├── 執行 dev test dev --quiet (確認預設模式速度與通過率)
  ├── 執行 dev test core --quiet (確認預設模式速度與通過率)
  └── 執行 --all-types 完整驗證 0 回歸
```
