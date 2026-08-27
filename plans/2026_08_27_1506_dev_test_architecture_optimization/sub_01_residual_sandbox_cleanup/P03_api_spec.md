# API 與介面規格書 (API & Interface Specification)

> 功能名稱：殘留 sandbox 清理機制 (Residual Sandbox Cleanup)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `SandboxProvisioner.prune_sandboxes` | `source/dev/dev/testing/sandbox.py` | Internal (Static) | 掃描 `cache://dev/sandbox/`，若 `sandbox_*` 目錄數超過 `max_keep`，刪除最舊的沙盒，返回被刪除數量。 |
| `SandboxProvisioner.cleanup_all_sandboxes` | `source/dev/dev/testing/sandbox.py` | Internal (Static) | 清空 `cache://dev/sandbox/` 下的所有 `sandbox_*` 目錄，返回被刪除數量。 |
| `Tester._run_test` | `source/dev/dev/tester.py` | Internal (Method) | 於測試執行結束時，依據回傳碼與 `--all` 旗標決定呼叫 `cleanup_all_sandboxes` 或 `cleanup_sandbox`。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
class SandboxProvisioner:
    @staticmethod
    def prune_sandboxes(max_keep: int = 3) -> int:
        """
        Scans cache://dev/sandbox/ and deletes the oldest sandbox_* directories
        if total count exceeds max_keep.
        
        Args:
            max_keep: Maximum number of sandboxes to retain (default: 3).
            
        Returns:
            int: Number of deleted sandboxes.
        """
        ...

    @staticmethod
    def cleanup_all_sandboxes() -> int:
        """
        Removes all sandbox_* directories under cache://dev/sandbox/.
        
        Returns:
            int: Number of deleted sandboxes.
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 底層修剪核心]
   └─ SandboxProvisioner.prune_sandboxes & cleanup_all_sandboxes in sandbox.py
           │
           ▼
[Step 2: 生命週期掛接]
   └─ SandboxProvisioner.create_sandbox (整合滾動修剪)
           │
           ▼
[Step 3: 上層 CLI 呼叫端]
   └─ Tester._run_test in tester.py (整合 --all 全量清空)
           │
           ▼
[Step 4: 單元與整合測試]
   └─ test_sandbox.py & test_tester.py
```
