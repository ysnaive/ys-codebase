# API 與介面規格書 (API & Interface Specification)

> 功能名稱：core_pip_sdk_and_environment_export  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `core.PipManager` | `source/core/core/__init__.py` | Public | 微環境管理與 pip 操作 SDK 主入口類別。 |
| `core.PipInstallError` | `source/core/core/__init__.py` | Public | pip 安裝失敗結構化異常。 |
| `PipManager.parse_pip_dependencies` | `source/core/core/pip_manager.py` | Public | 靜態方法，將 `pip_dependencies` 規格字典/清單正規化為 pip 字串清單。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. core/__init__.py 匯出
from core.pip_manager import PipManager, PipInstallError

__all__ = [
    # ... 現有匯出 ...
    "PipManager",
    "PipInstallError",
]

# 2. core/pip_manager.py 新增方法
class PipManager:
    @staticmethod
    def parse_pip_dependencies(pip_deps: Any) -> List[str]:
        """
        將 manifest.json 中的 pip_dependencies 宣告正規化為合法的 pip 規格字串清單。
        
        Args:
            pip_deps: dict (如 {"pkg": ">=1.0.0", "pkg2": ""}) 或 list (如 ["pkg>=1.0.0"])
            
        Returns:
            List[str]: 去重後之標準 pip 依賴規格清單 (如 ["pkg>=1.0.0", "pkg2"])
            
        Behavior:
            - 輸入 None、非 dict 非 list、空結構時安全回傳 [] (EC-01)
            - 過濾空白字串、None 鍵值，自動 strip() 去除首尾空白 (EC-02)
            - 維持順序去重 (Order-preserving deduplication)
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[1. core/pip_manager.py] ➔ 實作 parse_pip_dependencies 靜態方法
           │
           ▼
[2. core/__init__.py] ➔ 匯入並將 PipManager, PipInstallError 宣告至 __all__
           │
           ▼
[3. core/installer.py] ➔ 重構 sync_pip_dependencies 改用 PipManager.parse_pip_dependencies
           │
           ▼
[4. tests/test_pip_manager_sdk.py] ➔ 撰寫完整單元測試 (FT-01~04, ET-01~02)
```
