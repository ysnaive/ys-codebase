# API 規格書 (API Specification)

> 功能名稱：超薄宿主單檔實現 (Ultra-Thin Host Bootstrapper)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.2  

---

## 1. 模組與函式總覽

| 模組名稱 | 檔案路徑 | 類型 | 職責概述 |
| :--- | :--- | :---: | :--- |
| **`yscb` (Host)** | `project://yscb.py` | Add | 唯一單檔宿主自舉器：包含配置讀寫、`init` 自舉、`self-update` 自更新與 CLI 派發路由 |

---

## 2. API 介面定義 (Python Signature & Specs)

### 模組：`yscb.py`

```python
"""
YS-Codebase Ultra-Thin Single-File Host Bootstrapper & CLI Router.
100% Python Standard Library, Zero Third-Party Dependency.
"""

from typing import List, Optional, Dict, Any, Tuple
import sys
import os
import json
import urllib.request
import subprocess
import shutil
import ast

# ── 全域常數定義 (Constants) ──────────────────────────────────
CONFIG_FILENAME: str = "yscb.config.json"
DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/build"
CORE_COMMANDS: set = {
    "install",
    "update",
    "remove",
    "list",
    "status",
    "rollback",
    "reload"
}


# ── 組態管理工具函式 (Config Management) ───────────────────────

def load_config(start_dir: Optional[str] = None) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    自當前工作目錄向上或於同層級讀取 yscb.config.json 組態檔。
    
    :param start_dir: 起始搜尋目錄，預設為當前目錄。
    :return: (config_abs_path, config_data) 若未找到則回傳 (None, None)。
    """
    ...


def save_config(config_path: str, data: Dict[str, Any]) -> None:
    """
    將組態字典以標準格式原子寫入 yscb.config.json。
    
    :param config_path: 組態檔實體絕對路徑。
    :param data: 待寫入之組態資料字典。
    :raises OSError: 當磁碟寫入失敗或權限不足時拋出。
    """
    ...


# ── 原生指令實現 (Native Commands) ────────────────────────────

def cmd_init(argv: List[str]) -> int:
    """
    原生自舉初始化指令 (FR-01)。
    語法: yscb.py init {yscbRoot} [--provider="<source>"]
    
    :param argv: 排除 'init' 後之其餘參數清單。
    :return: 執行 Exit Code (0 為成功，非 0 為失敗)。
    """
    ...


def cmd_self_update(argv: List[str]) -> int:
    """
    宿主自我更新指令 (FR-02)。
    語法: yscb.py self-update [--provider="<source>"]
    
    :param argv: 排除 'self-update' 後之其餘參數清單。
    :return: 執行 Exit Code (0 為成功，非 0 為失敗)。
    """
    ...


# ── 泛用 CLI 派發器 (Generic CLI Dispatcher) ──────────────────

def dispatch_module(module_name: str, args: List[str]) -> int:
    """
    泛用模組 CLI 派發器 (FR-03, FR-04)。
    負責探測目標模組 scripts/cli.py，並以獨立子進程執行透傳參數。
    嚴守路徑封裝鐵律，不向模組暴露底層實體路徑。
    
    :param module_name: 目標模組名稱（例如 "core", "dev", "linter" 等）。
    :param args: 透傳給模組 CLI 之完整參數清單。
    :return: 子進程之 Exit Code。
    """
    ...


# ── 頂層進入點 (Main Entry Point) ──────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    """
    宿主命令列總中控進入點。
    階梯式路由：init -> self-update -> CORE_COMMANDS 智能轉發 -> 泛用模組派發。
    
    :param argv: 命令列參數（預設為 sys.argv[1:]）。
    :return: Exit Code。
    """
    ...
```

---

## 3. 關鍵依賴與第三方套件

| 呼叫功能 | 標準庫模組與函式 | 呼叫方式 / 簽名 | 驗證狀態 |
| :--- | :--- | :--- | :---: |
| **語法解析校驗** | `ast.parse` | `ast.parse(source_code, filename="yscb.py")` | ✅ 原生支援 |
| **子進程派發** | `subprocess.run` | `subprocess.run([sys.executable, cli_path, *args])` | ✅ 原生支援 |
| **HTTP 下載** | `urllib.request.urlopen` | `urllib.request.urlopen(req)` | ✅ 原生支援 |
| **檔案原子操作** | `shutil.copyfile` / `os.replace` | `os.replace(tmp_path, target_path)` | ✅ 原生支援 |

> **第三方依賴**：**無**（100% 使用 Python 3.8+ 標準庫）。

---

## 4. Decision Records

### [P03:DR-01] 函式型輕量架構與單檔內聚性
- **議題**：`yscb.py` 應設計為物件導向 class 結構還是函式型結構？
- **結論**：採用扁平純函式型架構（Top-level pure functions + `main()`）。
- **理由**：
  1. 函式型架構在單檔腳本中行數最精簡，執行開銷最低；
  2. 易於閱讀與維護，維持單檔在 150 行以內的極致輕量；
  3. 各指令（`cmd_init`, `cmd_self_update`, `dispatch_module`）邊界清晰獨立。
