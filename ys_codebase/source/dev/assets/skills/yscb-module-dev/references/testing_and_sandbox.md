# 生態系模組測試工程實踐與沙盒機制 (Testing Engineering & Sandbox Guild)

本手冊定義 YSCB 模組單元/整合測試工程規範、`YSCBTestCase` 基類特徵、拋棄式沙盒隔離機制、生命週期鉤子與高效跑測技巧。

---

## 🏛️ 1. 隔離沙盒機制 (Testing Engine Sandbox)

為確保模組測試的純淨性與確定性，`dev test` 採用**拋棄式虛擬沙盒**機制：

```mermaid
graph LR
    classDef s1 fill:#1e3a8a,stroke:#3b82f6,stroke-width:2px,color:#fff;
    classDef s2 fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#fff;
    classDef s3 fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fff;
    classDef s4 fill:#4c1d95,stroke:#8b5cf6,stroke-width:2px,color:#fff;

    A["前置 Build (產出 .build 包)"]:::s1 --> B["建立臨時拋棄式沙盒<br/>(cache://dev/sandbox/{id})"]:::s2
    B --> C["物化模組依賴與代碼"]:::s2
    C --> D["調用 scripts/hook.dev.py<br/>(on_test_setup)"]:::s3
    D --> E["執行 unittest 測試套件"]:::s3
    E --> F["調用 hook.dev.py<br/>(on_test_teardown)"]:::s3
    F --> G["自動抹除與清理沙盒環境"]:::s4
```

### 沙盒隔離的核心保證
1. **防止環境污染**：測試產生的暫存檔、快取與假資料侷限於沙盒目錄，結束時自動清理，不汙染正式 `project://.modules/`。
2. **依賴隔離驗證**：在近乎空白的獨立環境中載入模組，能即時暴露遺漏宣告的依賴或隱式本機路徑依賴。
3. **無鎖並發跑測**：每個測試進程擁有獨立的沙盒目錄與虛擬根目錄，支援多進程平行測試而無檔案鎖衝突。

---

## 🧪 2. 測試案例撰寫與 `YSCBTestCase` 基類

所有模組測試案例**必須**繼承 `dev.testing.YSCBTestCase`（`dev check` 會剛性攔截直接繼承 `unittest.TestCase` 之測試）。

### 2.1 剛性追溯鏈命名守則
測試方法命名必須與專案追溯鏈 1:1 強綁定：

| 測試類型 | 方法命名規範 | 追溯標籤 | 說明與適用情境 |
| :--- | :--- | :--- | :--- |
| **功能需求測試** | `def test_ft_XX_<desc>(self)` | `FT-XX` (對應 FR-XX) | 驗證主要業務邏輯與成功路徑 |
| **邊界與異常測試** | `def test_et_XX_<desc>(self)` | `ET-XX` (對應 EC-XX) | 驗證非法輸入、邊界條件與防禦性例外 |
| **全系統回歸測試** | `def test_rt_XX_<desc>(self)` | `RT-XX` | 驗證修復或重構未破壞現有既有功能 |
| **效能基準測試** | `def test_pt_XX_<desc>(self)` | `PT-XX` (對應 NFR-XX) | 驗證冷啟動導入時間或執行吞吐量門檻 |

### 2.2 核心狀態約定：`self.mark_passed()` 契約
> [!IMPORTANT]
> `YSCBTestCase` 實作了三態分類機制（`PASSED` / `FAILED` / `UNKNOWN`）：
> - 測試方法拋出未捕獲例外時，歸類為 `FAILED`。
> - 測試執行完畢且**顯式呼叫 `self.mark_passed()`** 時，歸類為 `PASSED`。
> - **若測試既未拋錯、又未呼叫 `self.mark_passed()`**，將被分類為 **`UNKNOWN`**（測試結果統計顯示 `Unknown: X`，無法完成驗收）！
> 
> 編寫測試方法時，成功路徑末尾必須顯式調用 `self.mark_passed()`。

### 2.3 標準測試撰寫範式
```python
import unittest
from dev.testing import YSCBTestCase
from dev.testing.requirement import require, Requirement
from core import uri

class TestMyModuleCore(YSCBTestCase):
    """模組核心業務測試案例。"""

    def setUp(self):
        super().setUp()
        # 準備測試暫存資源 (使用沙盒提供之 self.sandbox_dir 或 temp://)
        self.test_data = {"key": "value"}

    def tearDown(self):
        # 清理測試資源
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_ft_01_successful_transformation(self):
        """FT-01: 驗證正常輸入下轉換成功且輸出完整。"""
        result = self.my_transform(self.test_data)
        self.assertIn("key", result)
        self.mark_passed()  # 🚨 必須顯式標記通過！

    @require(Requirement.LOGIC)
    def test_et_01_none_input_raises_value_error(self):
        """ET-01: 驗證傳入 None 時能拋出防禦性例外。"""
        with self.assertRaises(ValueError):
            self.my_transform(None)
        self.mark_passed()  # 🚨 異常路徑驗證完成後亦須標記通過！
```

### 2.4 `YSCBTestCase` 專屬斷言與輔助工具庫

| 方法 / 屬性 | 簽名 / 類型 | 說明與適用情境 |
| :--- | :--- | :--- |
| `self.mark_passed()` | `() -> None` | 標記當前測試方法已順利執行完成，分類為 `PASSED` |
| `self.assertSuccess()` | `(returncode: int, msg: str = "") -> None` | 斷言 CLI 或進程退出代碼為 0 |
| `self.assertFailed()` | `(returncode: int, msg: str = "") -> None` | 斷言 CLI 或進程退出代碼為非 0 |
| `self.assertInOutput()` | `(expected: str, actual: str, msg: str = "") -> None` | 斷言終端文字輸出包含預期字串 |
| `self.assertFileExists()` | `(path_or_uri: str, msg: str = "") -> None` | 斷言實體路徑或語意 URI 存在 |
| `self.assertJsonEquals()` | `(expected: dict, path_or_uri: str, msg: str = "") -> None` | 讀取 JSON 檔案/URI 並斷言內容完全相等 |
| `self.assertExecutionTime()` | `(max_seconds: float)` (上下文管理器) | `with self.assertExecutionTime(0.5):` 斷言區塊執行時間不逾限 |
| `self.run_cli()` | `(args: List[str], cwd=None, env=None) -> (rc, stdout, stderr)` | 在沙盒內以子進程執行 Host CLI (`yscb.py`) 進行端到端命令驗證 |
| `self.create_mock_package()` | `(name, version, deps, desc) -> str` | 在沙盒 `mock_provider` 動態生成虛擬安裝包 |
| `self.create_mock_source_module()` | `(name, version, deps, files) -> str` | 在沙盒 `source/` 目錄動態建立完整源碼模組骨架 |
| `self.sandbox_dir` | `str` | 當前測試沙盒之絕對路徑 |
| `self.sandbox_uri` | `str` | 當前測試沙盒之語意 URI (`cache://dev/sandbox/<id>`) |

---

## 🏷️ 3. 4-Tier 測試分類與沙盒隔離機制

透過 `@require(Requirement.XXX)` 裝飾器可對測試類別或測試方法進行分級標註：

```python
from dev.testing.requirement import require, Requirement

# 1. 純邏輯單元測試 (預設包含，共享沙盒)
@require(Requirement.LOGIC)
def test_ft_logic(self): ...

# 2. 跨模組 / VFS 環境測試 (預設包含，共享沙盒)
@require(Requirement.ENV)
def test_ft_env(self): ...

# 3. 需網路連線測試 (離線環境自動 SkipTest，不阻斷離線跑測)
@require(Requirement.NETWORK)
def test_ft_remote_download(self): ...

# 4. 多步驟複合工作流 / 端到端測試 (預設排除，需顯式指定 --type=workflow)
@require(Requirement.WORKFLOW)
def test_ft_e2e_pipeline(self): ...

# 5. 效能與壓力測試 (預設排除，需顯式指定 --type=perf)
@require(Requirement.PERF)
def test_pt_stress(self): ...

# 6. 正交隔離沙盒標籤 (強制當前方法建立專屬獨立拋棄式沙盒，結束即銷毀)
@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)
def test_ft_destructive_cleanup(self): ...
```

> [!WARNING]
> **反模式警示**：純記憶體單元測試（`LOGIC`）嚴禁同時標註 `ISOLATED_SANDBOX`！`dev check` 會發出反模式警告，避免無謂消耗沙盒建置開銷。

---

## 🪝 4. 虛擬沙盒生命週期鉤子 (`scripts/hook.dev.py`)

當模組在沙盒中跑測需要客製化準備（如預設快取目錄、注入 Mock 環境變數、初始化模擬 DB 或種子資料）時，可在模組內宣告 `scripts/hook.dev.py`：

```python
"""
scripts/hook.dev.py: 沙盒測試生命週期擴充鉤子
"""
import os
from pathlib import Path
from typing import Any

def on_test_setup(context: Any) -> None:
    """
    在沙盒目錄建置完成、測試套件執行前觸發。
    context 包含 sandbox_dir 屬性。
    """
    os.environ["MY_MODULE_MOCK_MODE"] = "1"
    sb_dir = Path(getattr(context, "sandbox_dir", str(context)))
    cache_dir = sb_dir / ".cache" / "my_module"
    cache_dir.mkdir(parents=True, exist_ok=True)

def on_test_teardown(context: Any) -> None:
    """
    在測試套件執行完畢、沙盒清理前觸發。
    """
    os.environ.pop("MY_MODULE_MOCK_MODE", None)
```

- **打包保留**：`dev build` 打包時會自動將 `scripts/hook.dev.py` 保留於 `.build.zip` 中。
- **剛性防線**：`hook.dev.py` 頂層**嚴禁**散落可執行語句（僅能宣告 import、class 與 function），否則會被 `dev check` 攔截。

---

## ⚡ 5. 高效跑測與 Token 節流技巧

在 Agent 開發情境下，高效跑測與減少終端輸出至關重要：

### 5.1 靜音節流模式 (`-q` / `--quiet`)
```bash
python yscb.py dev test <mod_name> -q
```
- **效果**：隱藏冗長的前置打包與沙盒建置日誌，全數通過時僅輸出單行：
  ```
  Pass: 42(100.0%), Fail: 0, Unknown: 0, Skip: 0
  ```
- **節流**：節省 95% 以上 Token I/O，僅於測試失敗時輸出詳細 Traceback。

### 5.2 略過前置打包直接跑測 (`--no-build`)
```bash
python yscb.py dev test <mod_name> --no-build
```
- **效果**：當僅微調代碼且結構、依賴未發生變化時，直接重用上一輪沙盒環境進行快速熱除錯，測試反饋時間減半。

### 5.3 局部單案精準聚焦 (`-k <pattern>` 與 `--target`)
```bash
# 1. 樣式模糊聚焦
python yscb.py dev test <mod_name> -k test_ft_01

# 2. 精準目標選擇器 (可直接穿透非預設分類)
python yscb.py dev test <mod_name> --target=TestMyModuleCore.test_ft_01
```

### 5.4 依分類執行測試 (`--type`)
```bash
# 執行所有測試 (含 logic, env, workflow, perf, network)
python yscb.py dev test <mod_name> --type=all

# 僅執行工作流測試
python yscb.py dev test <mod_name> --type=workflow
```

### 5.5 組合高效跑測命令
```bash
# 日常微調最推薦的高效命令：
python yscb.py dev test <mod_name> -q --no-build -k test_ft_01
```

---

## 🚫 6. 測試防呆鐵律與調用禁忌

1. **嚴禁無端執行 `--all`**：
   日常單一模組開發中，**絕對禁止**濫用 `python yscb.py dev test --all`。全量測試僅限於結案前跨模組回歸驗證或開發者明確指示時使用。
2. **嚴禁調用內部原子操作**：
   `dev op-test` 與 `dev op-mksb` 為測試引擎底層原子操作，**嚴禁 Agent 手動直接調用**。一律使用封裝完備的 `dev test`。
3. **部署後免重複測試**：
   通過沙盒測試並完成 `@build` 直裝或正式發布後，**嚴禁重複執行 `dev test`**；物化完成即視為驗收通過。
4. **Contributes 閉環聯動**：
   若測試涉及擴充點註冊變更，跑測前建議先透過 `python yscb.py contributes check <mod>` 確認 Ingress/Egress 契約合法（詳見 [contributes_guide.md](./contributes_guide.md)）。
