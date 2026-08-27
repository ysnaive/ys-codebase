# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Dev 模組測試效能瓶頸優化、Mock 模組建置隔離與 Windows Unicode/cp950 編碼異常修復  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `safe_print` | `dev/tester.py` | Internal | 封裝控制台輸出，針對 Windows 編碼自動以 `errors="replace"` 或安全字符降級。 |
| `create_mock_source_module` | `dev/testing/case.py` | Internal/Test | 於沙盒 `source/<name>` 建立純淨 Mock 模組骨架與 Manifest，供 Builder/Release 測試。 |
| `TestDevBuilder` | `tests/test_builder.py` | Test Suite | 使用 Mock 模組測試 `Builder` 之建置、發布與修剪邏輯。 |
| `TestReleasePipeline` | `tests/test_release_pipeline.py` | Test Suite | 使用 Mock 模組測試發布流水線與三道閘門。 |
| `TestDevTester` | `tests/test_tester.py` | Test Suite | 包含 Mock 隔離之沙盒清理驗證與 CLI 契約測試。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. 控制台安全輸出輔助
def safe_print(text: str, file=None, end: str = "\n", flush: bool = False) -> None:
    """
    Safely output text to standard streams on Windows systems where encoding
    (e.g., cp950) might throw UnicodeEncodeError on certain special characters.
    """
    target = file or sys.stdout
    try:
        target.write(text + end)
        if flush:
            target.flush()
    except UnicodeEncodeError:
        enc = getattr(target, "encoding", "utf-8") or "utf-8"
        safe_text = (text + end).encode(enc, errors="replace").decode(enc)
        target.write(safe_text)
        if flush:
            target.flush()

# 2. YSCBTestCase Mock 模組源碼建立器
class YSCBTestCase(unittest.TestCase):
    def create_mock_source_module(
        self,
        name: str = "mock_source_pkg",
        version: str = "1.0.0.0",
        files: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Creates a valid mock module in the sandbox's source/<name> directory
        with standard manifest.json and boilerplate entry points.
        Returns the resolved source directory path.
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: dev.tester & dev.testing.runner] ──▶ safe_print 導入與 subprocess.run 編碼安全化
                    │
                    ▼
[Step 2: dev.testing.case] ──────────────▶ create_mock_source_module 輔助方法擴充
                    │
                    ▼
[Step 3: tests/test_builder.py] ─────────▶ 全面遷移至 Mock Module (零打包真實代碼)
                    │
                    ▼
[Step 4: tests/test_release_pipeline.py] ─▶ 全面遷移至 Mock Module (零依賴真實代碼)
                    │
                    ▼
[Step 5: tests/test_tester.py] ──────────▶ test_run_test_all 改採 Mock 隔離去子進程化
                    │
                    ▼
[Step 6: tests/test_sandbox.py] ─────────▶ test_dev_test_high_level 標記為 WORKFLOW
```
