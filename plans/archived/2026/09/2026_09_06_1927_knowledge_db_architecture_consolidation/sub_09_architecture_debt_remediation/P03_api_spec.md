# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_09_architecture_debt_remediation  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ensure_private_venv` | `source/core/core/platform/venv.py` | Public | 跨平台定位專用虛擬環境 site-packages 並解析 `host_venv.pth` 注入 `sys.path` |
| `AtomicEngine.act_lock` / `act_unlock` | `source/core/core/engine.py` | Public | 透過 `InterProcessLock` 獲取與釋放跨進程互斥鎖，取代舊版自製 JSON 鎖 |
| `VFS.copy` / `VFS.move` | `source/core/core/vfs/vfs.py` | Public | 增加同後端防護校驗，若跨後端拷貝移動拋出 `NotImplementedError` |
| `get_engine` | `source/knowledge-db/knowledge_db/engine.py` | Public | 模組級唯一的 `KnowledgeEngine` 單例工廠函式，進程內全域複用 |
| `is_path_watched` | `source/knowledge-db/knowledge_db/service.py` | Public | 精確匹配註冊空間 include roots，徹底移除工作區根目錄寬鬆兜底 |
| `BaseServiceWorker.start` | `source/server/server/service.py` | Abstract | 補齊 context 參數字典結構契約（`yscb_root`, `workspace_root`, `config` 等） |
| `_try_hot_dispatch` / `dispatch_module` | `yscb.py` | Internal | 加入 `_MODULE_CACHE`、FD 洩漏安全修復、環境變數動態逾時與 main if 結構展開 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 虛擬環境定位原語 (`core.platform.venv`)
```python
def ensure_private_venv(yscb_root: str) -> None:
    """
    跨平台定位私有虛擬環境的 site-packages 目錄，並遞迴解析 host_venv.pth 注入 sys.path。
    
    Args:
        yscb_root: YSCB 專案根目錄絕對或相對路徑。
    """
```

### 2.2 Core 進程鎖統一 (`core.engine`)
```python
class AtomicEngine:
    def __init__(self):
        self._active_locks: Dict[str, InterProcessLock] = {}

    def act_lock(self, operation: str, timeout: float = 10.0) -> None:
        """
        透過 core.platform.InterProcessLock 獲取 cache://.yscb.lock 互斥鎖。
        若鎖遭佔用且超時，拋出 BlockingIOError。
        """

    def act_unlock(self, operation: str) -> None:
        """釋放指定 operation 所持有的 InterProcessLock 實例。"""
```

### 2.3 Knowledge-DB 進程單例工廠 (`knowledge_db.engine`)
```python
def get_engine() -> KnowledgeEngine:
    """取得進程級唯一 KnowledgeEngine 單例，惰性初始化並全域複用。"""
```

### 2.4 ServiceWorker Context 契約規格 (`server.service`)
```python
class BaseServiceWorker(ABC):
    @abstractmethod
    def start(self, context: Dict[str, Any]) -> None:
        """
        在背景線程或子進程中啟動常駐服務。
        
        Args:
            context: 守護進程上下文字典，約定包含：
                - "yscb_root" (str): YSCB 專案根目錄絕對路徑 (必備)
                - "workspace_root" (str, optional): 宿主工作區根目錄
                - "config" (dict, optional): 伺服器或特定模組配置
        """
```

### 2.5 VFS 跨後端防禦 (`core.vfs`)
```python
class VFS:
    def copy(self, src: Union[str, Any], dst: Union[str, Any]) -> None:
        """若 src 與 dst 分屬不同 Backend，拋出 NotImplementedError。"""
    
    def move(self, src: Union[str, Any], dst: Union[str, Any]) -> None:
        """若 src 與 dst 分屬不同 Backend，拋出 NotImplementedError。"""
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Tier 1: High]
  1. core.engine (H-01: InterProcessLock 替換)
  2. knowledge-db.service (H-02: 移除 workspace_root 兜底)
         |
[Tier 2: Med]
  3. core.platform.venv (M-01: 下沉 ensure_private_venv)
  4. server.master / server.worker (M-01: 複用 ensure_private_venv; M-02: VFS 原子狀態)
  5. yscb.py (M-03: _MODULE_CACHE; M-04: FD 洩漏安全修復)
  6. knowledge-db.engine (M-05: 導出 get_engine 單例; L-04: 清理無用常數)
  7. knowledge-db.service & scripts/cli.py (M-05: 共享 get_engine)
         |
[Tier 3: Low & Design]
  8. core.guard (L-01: Guard Docstring)
  9. knowledge-db.pipeline (L-02: _CACHE_LOCK)
  10. yscb.py (L-03: 動態逾時; L-05: main 展開)
  11. server.service (D-01: BaseServiceWorker 契約)
  12. core.vfs (D-02: copy/move 跨後端檢查)
```
