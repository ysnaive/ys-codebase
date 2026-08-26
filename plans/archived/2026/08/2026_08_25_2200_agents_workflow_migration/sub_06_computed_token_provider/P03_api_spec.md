# API 規格說明書 (Phase 3: API & Interface Specification)

> 功能名稱：Contributes 擴充支援 Computed Token 與 code.func:// 函式定位協議  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. Public API 簽名與型態契約 (Public Interfaces)

### 1.1 `core.symbols` 符號解析模組 (`source/core/core/symbols.py`)

```python
from typing import Any, Callable, Optional, Tuple

class SymbolError(Exception):
    """符號定位與加載基礎異常。"""
    pass

class InvalidSymbolURIError(SymbolError, ValueError):
    """當 code.func:// URI 格式無效時拋出。"""
    pass

class SymbolNotFoundError(SymbolError, ImportError, AttributeError):
    """當目標模組、檔案或函式符號不存在或不可呼叫時拋出。"""
    pass

def parse_code_func_uri(uri_str: str) -> Tuple[str, str, str]:
    """
    解析 code.func://<module>/<subpath>:<function_name> 語法。
    
    Args:
        uri_str: code.func:// 協議字串
    Returns:
        (module_name, subpath, function_name) 三元組
    Raises:
        InvalidSymbolURIError: 若協議格式不正確或缺少 ':'
    """
    ...

def resolve_callable(uri_str: str, context: Optional[Any] = None) -> Callable[..., Any]:
    """
    解析 code.func:// 協議並動態載入返回 Python 可呼叫物件 (Callable)。
    
    具備雙軌載入策略：
      1. 優先透過 sys.modules / 標準 package import 載入已安裝模組。
      2. 若未載入，透過 uri.resolve 尋找模組實體檔案並使用 importlib.util 載入。
    
    Args:
        uri_str: code.func:// 協議字串
        context: 可選之執行期/編譯期上下文
    Returns:
        Python Callable 物件
    Raises:
        InvalidSymbolURIError: 格式錯誤
        SymbolNotFoundError: 模組或函式符號不存在、非 Callable
    """
    ...
```

### 1.2 `agents_workflow.providers` 模組 (`source/agents-workflow/agents_workflow/providers.py`)

```python
from typing import Optional, Any

def get_dynamic_context_map(context: Optional[Any] = None) -> str:
    """
    動態生成當前專案已註冊之語意 URI 協議即時解析地圖 Markdown 表格。
    
    Args:
        context: 編譯期上下文 (包含 uri SDK 實例)
    Returns:
        包含 JIT Dynamic Context 表格之 Markdown 字串
    """
    ...
```

---

## 2. Contributes Insert 宣告規格擴充

在 `manifest.json` 或 `contributes` 中支援動態計算 Token：

```json
{
  "type": "computed",
  "token": "DYNAMIC_CONTEXT_MAP",
  "value": "code.func://agents-workflow/providers:get_dynamic_context_map",
  "mode": "replace"
}
```

- **`type`**：剛性限定為 `"computed"`。
- **`token`**：目標插入佔位符（如 `DYNAMIC_CONTEXT_MAP`）。
- **`value`**：`code.func://` 協議 URI。
- **`mode`**：支援 `"replace"`（替換標籤）或 `"append"`（追加至尾部）。

---

## 3. 實作依賴拓撲順序 (Implementation Dependency Topology)

```text
[Task 1: core/symbols.py (符號解析與 resolve_callable + test_symbols.py)]
                               │
                               ▼
[Task 2: core/compiler.py & agents_workflow/compiler.py (支援 type: "computed")]
                               │
                               ▼
[Task 3: agents-workflow/providers.py (實作 get_dynamic_context_map)]
                               │
                               ▼
[Task 4: agents-workflow/manifest.json (配置 DYNAMIC_CONTEXT_MAP 注入)]
                               │
                               ▼
[Task 5: test_compiler.py (端對端 Computed Token 整合驗證)]
```

---

## 4. 依據需求 (Traceability)

- 本規格直接對應 [P01_requirements_spec.md](./P01_requirements_spec.md) 之 FR-01 ~ FR-05 與 [P02_architecture_plan.md](./P02_architecture_plan.md)。
