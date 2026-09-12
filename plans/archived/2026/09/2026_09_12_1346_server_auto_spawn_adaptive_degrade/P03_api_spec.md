# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Server 自動喚醒環境自適應降級與 Agents 導引提示 (Server Auto Spawn Adaptive Degrade & Agent Guidance)  
> 建立日期：2026-09-12  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `can_spawn_background_daemon` | `source/core/core/platform/process.py` | Public | 檢測環境是否允許建立脫鉤背景守護進程，具備記憶體快取。 |
| `ServerConfig.auto_spawn` | `source/server/server/config.py` | Public | 組態模型欄位，控制是否允許自動拉起背景服務。 |
| `_maybe_auto_spawn_server` | `source/core/core/commands/dispatcher.py` | Internal | 自動喚醒守門與自適應降級核心實作。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `core.platform.process.can_spawn_background_daemon`

```python
def can_spawn_background_daemon(force_reprobe: bool = False) -> bool:
    """
    Probes whether the current execution environment allows spawning a persistent
    background daemon process detached from the parent process group / Job Object.

    Args:
        force_reprobe: If True, bypasses the in-memory cache and re-probes the environment.

    Returns:
        bool: True if background daemon spawning is supported, False otherwise.
    """
```

### 2.2 `server.config.ServerConfig`

```python
DEFAULT_AUTO_SPAWN: bool = True

@dataclass
class ServerConfig:
    enable: bool = DEFAULT_ENABLE
    enable_console: bool = DEFAULT_ENABLE_CONSOLE
    idle_timeout_sec: float = DEFAULT_IDLE_TIMEOUT_SEC
    auto_spawn: bool = DEFAULT_AUTO_SPAWN
```

### 2.3 `core.commands.dispatcher._maybe_auto_spawn_server`

```python
_AUTO_SPAWN_WARNED: bool = False

def _maybe_auto_spawn_server(host_dir: str, yscb_abs: str) -> None:
    """
    在背景非同步按需拉起 Server 守護進程。
    支援 auto_spawn 組態檢核與環境權限自適應降級。
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1] core.platform.process.can_spawn_background_daemon
   │
   ├─► [Step 2] server.config (auto_spawn 支援)
   │
   └─► [Step 3] core.commands.dispatcher (_maybe_auto_spawn_server 整合與提示輸出)
```
