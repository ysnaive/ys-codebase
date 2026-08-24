# API 規格書 (API Specification)

> 功能名稱：開發者工具模組 (Dev Developer Tools Module)
> 建立日期：2026-08-24
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)
> 狀態：Confirmed
> 擴充項目：none
> 模板版本：v1.2

---

## 1. 模組與類別總覽

| 模組 / 檔案路徑 | 匯出成員 | 類型 | 職責概述 |
| :--- | :--- | :---: | :--- |
| `source/dev/dev/scaffold.py` | `Scaffolder` | Add | 模組名稱合法性檢查、標準 3 層骨架生成器 |
| `source/dev/dev/checker.py` | `Checker` | Add | `manifest.json`、進入點、AST 語法與路徑封裝規範檢查器 |
| `source/dev/dev/builder.py` | `Builder` | Add | 前置合規檢查、快取過濾與純淨發布產物建置器 |
| `source/dev/dev/__init__.py` | `Scaffolder`, `Checker`, `Builder` | Add | 套件頂層匯出 |
| `source/dev/scripts/cli.py` | `main(argv)` | Add | `dev` 模組對外 CLI 進入點，解析 `create`, `check`, `build` 指令 |

---

## 2. API 介面定義 (Python Signature & Specs)

### 2.1 模組：`dev.scaffold`

```python
from typing import Tuple

class Scaffolder:
    """
    模組骨架生成器。
    """
    def __init__(self): ...

    def create_module(self, name: str, description: str = '', author: str = '') -> Tuple[bool, str]:
        """
        於 source/<name>/ 建立標準模組骨架。
        
        :param name: 模組名稱（需符合 Python 識別碼規範）
        :param description: 模組功能描述
        :param author: 作者資訊
        :return: (成功與否, 提示或錯誤訊息)
        """
        ...
```

---

### 2.2 模組：`dev.checker`

```python
from typing import Tuple, List, Dict

class Checker:
    """
    模組規範合規檢查器。
    """
    def __init__(self): ...

    def check_module(self, name: str) -> Tuple[bool, List[str]]:
        """
        檢查指定模組是否符合規範：
        1. source/<name>/manifest.json 存在且包含必要欄位 (name, version, entry)
        2. source/<name>/scripts/cli.py 存在
        3. 遍歷所有 Python 檔案執行 ast.parse 語法檢查
        
        :param name: 模組名稱
        :return: (是否全數通過, 錯誤/警告清單)
        """
        ...

    def check_all(self) -> Dict[str, Tuple[bool, List[str]]]:
        """
        掃描 source/ 下所有模組並執行全量檢查。
        
        :return: {module_name: (是否通過, 錯誤清單)}
        """
        ...
```

---

### 2.3 模組：`dev.builder`

```python
from typing import Tuple, Dict

class Builder:
    """
    純淨建置發布工具。
    """
    def __init__(self): ...

    def build_module(self, name: str, clean: bool = False) -> Tuple[bool, str]:
        """
        執行指定模組之純淨建置：
        1. 調用 Checker.check_module 執行合規檢查（不通過則終止）
        2. 建立 build/<name>/ 目錄
        3. 排除 __pycache__、*.pyc、*.tmp、*.bak 等暫存垃圾
        4. 複製純淨源碼產物至 build/<name>/
        
        :param name: 模組名稱
        :param clean: 是否先清空既有 build 目錄
        :return: (建置成功與否, 產物路徑或錯誤訊息)
        """
        ...

    def build_all(self, clean: bool = False) -> Dict[str, Tuple[bool, str]]:
        """
        批次建置 source/ 下所有合法模組。
        """
        ...
```

---

### 2.4 模組：`dev.scripts.cli`

```python
from typing import Optional, List

def main(argv: Optional[List[str]] = None) -> int:
    """
    dev 模組對外 CLI 命令分發器。
    """
    ...
```

---

## 3. 關鍵依賴與第三方套件

| 呼叫功能 | 標準庫模組與函式 | 呼叫方式 / 簽名 | 驗證狀態 |
| :--- | :--- | :--- | :---: |
| **識別碼校驗** | `re` / `str.isidentifier` | `name.isidentifier()` | ✅ 原生支援 |
| **語法 AST 驗證** | `ast` | `ast.parse(source_code, filename=...)` | ✅ 原生支援 |
| **JSON 讀寫** | `json` / `core.uri` | `uri.read_json` / `uri.write_json` | ✅ 原生支援 |
| **目錄遍歷與過濾** | `os` / `shutil` / `core.uri` | `uri.listdir` / `shutil.copy2` | ✅ 原生支援 |

> **第三方依賴**：**無**（100% 純 Python 3.8+ 標準庫）。

---

## 4. Decision Records

### [P03:DR-01] 檢查與建置的管線式串聯
- **議題**：`dev build` 是否應自動包含 `dev check`？
- **結論**：是。`Builder.build_module` 強制在複製產物前先調用 `Checker.check_module`，若合規檢查未通過，立即拒絕建置發布。
- **理由**：落實守門員原則，防止任何帶有語法錯誤或缺少進入點的殘缺模組流入 `build/` 或 `mirror://`。
