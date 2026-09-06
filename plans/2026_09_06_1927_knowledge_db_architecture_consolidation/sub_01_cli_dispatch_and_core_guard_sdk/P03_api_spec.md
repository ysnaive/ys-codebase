# API 與介面規格書 (API & Interface Specification)

> 功能名稱：cli_dispatch_and_core_guard_sdk  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `guard_dispatch` | `source/core/core/guard.py` | Public | 檢驗當前調用是否具備宿主目錄與合法 Dispatch Token，違規立即阻斷 |
| `process` | `source/<module>/scripts/cli.py` | Public | 各生態系模組標準 CLI 進入點，解析參數列並執行對應命令 |
| `Scaffolder.create_module` | `source/dev/dev/scaffold.py` | Public | 生成標準模組骨架，預裝合規 `scripts/cli.py` 與守門調用 |
| `Checker._check_cli_compliance` | `source/dev/dev/checker.py` | Private | 透過 AST 靜態檢驗模組 CLI 入口是否滿足 process 存在、禁 main、禁頂層執行代碼 |
| `dispatch_module` | `yscb.py` | Internal | 宿主分發路由器，動態注入 Token 並呼叫目標模組之 `process(args)` |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 Core 守門 SDK (`core.guard.guard_dispatch`)
```python
GUARD_ENV_TOKEN: str = "YSCB_HOST_DISPATCH_TOKEN"
GUARD_ENV_HOST: str = "YSCB_HOST_DIR"
GUARD_ENV_TESTING: str = "YSCB_TESTING"

def guard_dispatch(module_name: str) -> None:
    """
    Core 通用 CLI 守門機制。
    各模組 scripts/cli.py 的 process(args) 函式首行強制調用。
    
    行為邏輯：
    1. 若環境變數 YSCB_TESTING == "1"，認定為測試套件跑測，安全豁免放行。
    2. 檢查 os.environ 是否同時存在 YSCB_HOST_DIR 與 YSCB_HOST_DISPATCH_TOKEN。
    3. 若缺失任一項，認定為未經宿主分派之非法繞道調用：
       - 向 sys.stderr 輸出醒目 [YSCB Security Guard] 錯誤資訊。
       - 輸出正確的 'python yscb.py <module_name> <command>' 調用引導。
       - 調用 sys.exit(126) 剛性熔斷終止進程。
    """
```

### 2.2 模組標準 CLI 進入點簽名 (`scripts/cli.py`)
```python
"""
CLI entry point for module: <name>.
"""
from typing import List
import sys
import os

from core.guard import guard_dispatch

def process(args: List[str]) -> int:
    """
    全生態系統一規範之模組 CLI 進入點。
    
    :param args: 傳遞給該模組之命令列參數列 (排除模組名稱本身，等同原 sys.argv[1:])
    :return: 命令執行退出碼 (0 為成功，非 0 為失敗)
    """
    guard_dispatch("<module_name>")
    
    # 模組專屬 Windows 編碼保護 (必須包覆在 process 內，嚴禁寫在模組頂層)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # 業務子命令分派邏輯...
    return 0
```

### 2.3 Dev Checker 靜態檢核函式 (`dev.checker.Checker`)
```python
def _check_cli_compliance(self, real_dir: str, report: CheckReport) -> None:
    """
    以 ast 模組深度檢驗 scripts/cli.py 的合規性：
    1. 檔案必須存在。
    2. 頂層節點白名單過濾：除 ast.Import, ast.ImportFrom, ast.FunctionDef, 
       ast.AsyncFunctionDef, ast.ClassDef, 以及作為 docstring 的 ast.Expr(ast.Constant(str)) 外，
       嚴禁任何未包覆在 func/class 內的語句（例如裸賦值、裸函式調用、裸 if 分支）。
    3. 函式定義檢核：必須包含名為 'process' 的 FunctionDef。
    4. 禁絕標識檢核：絕對不可包含名為 'main' 的 FunctionDef。
    5. 執行塊檢核：絕對不可包含 if __name__ == '__main__': 區塊。
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Core 基礎]
  └─ 建立 core.guard.py，導出 guard_dispatch
  └─ 編寫 core/tests/test_guard.py 並跑通單元測試

[Step 2: Dev 骨架與檢測]
  └─ 升級 dev.scaffold: 產出合規 scripts/cli.py 範本
  └─ 升級 dev.checker: 實裝 AST 靜態檢核 pipeline
  └─ 編寫 dev/tests/test_cli_compliance.py 跑通測試

[Step 3: 宿主分發適配]
  └─ 改造 yscb.py: 注入 Token，改為調用 process(args)

[Step 4: 生態系模組遷移]
  └─ 依序遷移 core -> dev -> agents-workflow -> knowledge-db 的 scripts/cli.py
  └─ 執行全生態系回歸驗證
```
