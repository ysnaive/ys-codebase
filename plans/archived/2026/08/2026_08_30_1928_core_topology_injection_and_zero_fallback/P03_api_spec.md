# API 與介面規格書 (API & Interface Specification)

> 功能名稱：core 核心拓撲注入 (yscb_root) 與全庫 Fallback 剛性收斂  
> 建立日期：2026-08-30  
> 所屬計畫：2026_08_30_1928_core_topology_injection_and_zero_fallback  
> 狀態：Confirmed  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `set_yscb_root(yscb_dir)` | `source/core/core/uri.py` | Public | 顯式注入/重設工具庫核心根目錄 (記憶體狀態) |
| `get_yscb_root()` | `source/core/core/uri.py` | Public | 取得當前活躍之核心根目錄 (優先讀取記憶體，次讀取環境變數) |
| `yscb_scope(yscb_dir)` | `source/core/core/uri.py` | Public | 核心根目錄安全作用域 Context Manager，保證 finally 100% 還原 |
| `_get_yscb_root()` | `source/core/core/uri.py` | Internal | 三階梯自省求值核心路徑 (記憶體 > 環境變數 > 常數基準) |
| `ConfigManager._get_yscb_root()` | `source/core/core/config.py` | Internal | 統一委任 `uri._get_yscb_root()`，完全清除 while 迴圈 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# ==============================================================================
# core.uri (source/core/core/uri.py)
# ==============================================================================

_active_yscb_dir: Optional[str] = None


def set_yscb_root(yscb_dir: Optional[str]) -> None:
    """
    顯式設定或清空記憶體注入之 YSCB 工具庫根目錄。
    
    :param yscb_dir: 實體資料夾路徑，若為 None 則清空注入狀態。
    """
    global _active_yscb_dir
    _active_yscb_dir = os.path.normpath(os.path.abspath(yscb_dir)) if yscb_dir else None


def get_yscb_root() -> Optional[str]:
    """
    取得活躍之工具庫根目錄：
    1. 優先返回 _active_yscb_dir (記憶體注入)。
    2. 次之讀取環境變數 YSCB_ROOT_DIR (若存在且為目錄)。
    3. 若皆未設定返回 None。
    """
    if _active_yscb_dir:
        return _active_yscb_dir
    env_dir = os.environ.get("YSCB_ROOT_DIR")
    if env_dir and os.path.isdir(env_dir):
        return os.path.normpath(os.path.abspath(env_dir))
    return None


@contextmanager
def yscb_scope(yscb_dir: Optional[str]) -> Generator[None, None, None]:
    """
    工具庫核心目錄安全作用域 (Context Manager)：
    進入時注入 yscb_dir，退出時以 finally 100% 保證還原舊全域 _active_yscb_dir。
    """
    old = get_yscb_root()
    set_yscb_root(yscb_dir)
    try:
        yield
    finally:
        set_yscb_root(old)


def _get_yscb_root() -> str:
    """
    三階梯物理拓撲不變性自省：
    1. get_yscb_root() (記憶體或環境變數注入)
    2. __file__ 向上推算 3 層 (常數自省)
    """
    injected = get_yscb_root()
    if injected and os.path.isdir(injected):
        return injected
    curr = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.dirname(os.path.dirname(os.path.dirname(curr))))
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: core.uri] (底層 VFS 注入介面實作)
       │
       ▼
[Step 2: core.config] (消除 while 迴圈與 CWD 回退)
       │
       ▼
[Step 3: dev.testing.sandbox] (雙重 Scope 注入調度)
       │
       ▼
[Step 4: agents-workflow & tests] (路徑收斂與單元測試編寫)
```

