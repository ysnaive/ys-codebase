# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_10_server_hot_reload_dispatch_and_master_self_restart  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ModulesWatcher` | `source/server/server/watcher.py` | Internal | 監控 `.modules/` 變動，解析受影響模組並防抖回調 |
| `MasterSupervisor` | `source/server/server/master.py` | Public | Master 守護中樞，實作雙軌重載分流與 `restart_server()` |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
class ModulesWatcher:
    def __init__(
        self,
        modules_dir: str,
        on_change_callback: Callable[..., None],
        poll_interval_sec: float = 1.0,
        debounce_sec: float = 0.5,
    ) -> None: ...

    def _extract_affected_modules(self, changed_paths: Set[str]) -> Set[str]:
        """
        從變更的檔案絕對路徑中，解析相對於 modules_dir 的頂層子目錄名作為模組名稱。
        例如: /path/.modules/server/manifest.json -> 'server'
        """
        ...

    def _notify_change(self, affected_modules: Set[str]) -> None:
        """
        依 inspect.signature 判斷回調函式是否支援參數:
        - 支援參數: 傳入 affected_modules (Set[str])
        - 無參函式: 直接呼叫 on_change_callback()
        """
        ...

class MasterSupervisor:
    def on_modules_changed(self, affected_modules: Optional[Set[str]] = None) -> None:
        """
        雙軌重載分流決策點:
        - 若 affected_modules 包含 'server' 或 'core': 呼叫 self.restart_server()
        - 否則: 呼叫 self.restart_worker()
        """
        ...

    def restart_server(self) -> None:
        """
        重啟整個 Server (Master + Worker):
        1. 停止 Watcher 與 Background Services
        2. 釋放 HTTP Server 與 State 鎖
        3. 透過 core.platform.spawn_detached 拉起全新 Master 進程
        4. 舊 Master 優雅退出自身 (sys.exit(0))
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. source/server/server/watcher.py
   └── 實作 _extract_affected_modules 與 _notify_change 參數向下相容

2. source/server/server/master.py
   └── 實作 on_modules_changed 分流與 restart_server 脫鉤重啟

3. source/server/tests/test_server.py
   └── 編寫 FT-01 ~ FT-03 自動化測試案例
```
