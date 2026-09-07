# API 與介面規格書 (API & Interface Specification)

> 功能名稱：server_console_config  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ServerConfig` | `source/server/server/config.py` | Public | 封裝 `enable_console` 等組態欄位，對接 `core.config` |
| `_resolve_enable_console` | `source/server/scripts/cli.py` | Internal | 仲裁 CLI 顯式輸入與組態設定，決定最終啟動模式 |
| `_handle_start` | `source/server/scripts/cli.py` | Internal | CLI `server start` 處理器，支援互斥群組與模式分流 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
from dataclasses import dataclass
from typing import Any, Dict, Optional

DEFAULT_ENABLE_CONSOLE: bool = False
DEFAULT_IDLE_TIMEOUT_SEC: float = 900.0


@dataclass
class ServerConfig:
    enable_console: bool = DEFAULT_ENABLE_CONSOLE
    idle_timeout_sec: float = DEFAULT_IDLE_TIMEOUT_SEC

    @classmethod
    def load(
        cls,
        workspace_root: Optional[str] = None,
        override_dict: Optional[Dict[str, Any]] = None,
    ) -> "ServerConfig":
        """
        載入 Server 模組組態。
        支援 core.config (Local > Project) 雙層合併與防禦型態轉型。
        """
        ...


def _resolve_enable_console(
    console_arg: Optional[bool],
    daemon_arg: Optional[bool],
    config_val: bool = False,
) -> bool:
    """
    啟動模式仲裁邏輯：
    1. console_arg is True: 回傳 True (CLI --console 強制覆蓋除錯)
    2. daemon_arg is True: 回傳 False (CLI --daemon 強制覆蓋背景)
    3. 兩者皆為 None/未給予: 回傳 config_val (回退至設定檔值)
    """
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. core.config (底層微內核組態管理 SDK)
   └── 2. server/config.py (ServerConfig 資料類別與載入器)
         └── 3. scripts/cli.py (_resolve_enable_console 與互斥參數解析)
               └── 4. tests/test_server_config.py (單元測試與邊界測試驗證)
```
