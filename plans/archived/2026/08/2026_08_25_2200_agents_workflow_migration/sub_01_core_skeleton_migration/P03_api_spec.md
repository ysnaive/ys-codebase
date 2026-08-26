# API 與介面規格書 (API & Interface Specification)

> 功能名稱：agents-workflow 核心骨架與 SOP 本體遷移 (Core Skeleton & SOP Body Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據架構：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：`Confirmed`  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| **`ArtifactCompiler`** | `agents_workflow/compiler.py` | Public | 工廠物化編譯核心，執行依賴拓撲收集、多輪遞迴狀態機解算與 exports 分流物化。 |
| **`cmd_compile`** | `scripts/cli.py` | Public | CLI 指令處理器，調用編譯器物化全系統資產並印出編譯報告。 |
| **`cmd_tokens`** | `scripts/cli.py` | Public | CLI 指令處理器，自省查詢全系統已註冊的 Token 錨點並格式化輸出表格。 |
| **`cmd_list`** | `scripts/cli.py` | Public | CLI 指令處理器，自省查詢當前已導出的 Standards/Workflows/Templates 物料清冊。 |
| **`on_reload`** | `scripts/hook.core.py` | Hook | 微內核生命週期監聽函式，在 `yscb reload` 後自動觸發編譯器更新 exports/。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `ArtifactCompiler` 核心工廠編譯器

```python
# ── source/agents-workflow/agents_workflow/compiler.py ───────────────────
from typing import Dict, List, Any, Optional, Tuple

class ArtifactCompiler:
    """
    協議產物工廠編譯器 (Artifact Factory Compiler).
    負責解析微內核已安裝模組之 contributes (export, insert, token)，
    執行多輪遞迴狀態機展開，並將標準資產物化寫入 module://exports/。
    """

    def __init__(self, host_dir: Optional[str] = None):
        """初始化編譯器，綁定微內核 Engine 與 VFS 協議環境。"""
        ...

    def compile_all(self) -> Dict[str, Any]:
        """
        執行全量工廠物化編譯流水線：
        1. 取得模組依賴拓撲順序 (Topological Order)。
        2. 有序收集全系統之 export, insert, token 宣告清冊。
        3. 逐一讀取 export 檔案，調用 resolve_single_artifact 執行多輪解算。
        4. 依 type (standards|workflows|templates) 分流原子覆蓋寫入至 module://exports/。
        
        Returns:
            Dict[str, Any]: {
                "success": bool,
                "exported_count": int,
                "inserted_count": int,
                "tokens_count": int,
                "errors": List[str]
            }
        """
        ...

    def resolve_single_artifact(
        self, 
        content: str, 
        inserts: List[Dict[str, Any]], 
        mod_order: List[str]
    ) -> str:
        """
        單一 Export 檔案之多輪遞迴解算狀態機：
        - Step 1: 掃描文本建立目前 <!-- __TOKEN__ --> 錨點快照 CurrentTokens。
        - Step 2: 依 mod_order 拓撲順序遍歷匹配的 insert (replace / below / above)。
        - Step 3: 移除本輪已完成解算之 Token 錨點標籤。
        - Step 4: 遞迴檢查文本是否仍有新 Token（有則回 Step 1，無則結束）。
        - Step 5: 保持 <!-- __URI(...)__ --> 標籤原樣返回。
        
        Args:
            content: 原始檔案字串內容
            inserts: 全系統 insert 宣告清冊
            mod_order: 模組依賴拓撲名稱清單
            
        Returns:
            str: 完全收斂解算後之最終字串
        """
        ...

    def get_registered_tokens(self) -> List[Dict[str, Any]]:
        """
        自省查詢全系統所有模組註冊之 token 錨點元數據。
        
        Returns:
            List[Dict[str, Any]]: 每筆包含 {"module": str, "value": str, "description": str}
        """
        ...

    def get_exported_artifacts(self) -> List[Dict[str, Any]]:
        """
        自省查詢全系統所有模組宣告之 export 資產清單。
        
        Returns:
            List[Dict[str, Any]]: 每筆包含 {"module": str, "type": str, "source": str, "description": str}
        """
        ...
```

---

### 2.2 CLI 進入點與子指令合約

```python
# ── source/agents-workflow/scripts/cli.py ─────────────────────────────────
from typing import List

def main(args: List[str]) -> int:
    """
    CLI 進入點路由器。
    支援指令：
      - compile (別名: build)
      - tokens (別名: --list-token)
      - list
    """
    ...

def cmd_compile(args: List[str]) -> int:
    """執行 ArtifactCompiler.compile_all() 並輸出格式化進度日誌。"""
    ...

def cmd_tokens(args: List[str]) -> int:
    """調用 get_registered_tokens() 並以對齊表格輸出 Token 列表。"""
    ...

def cmd_list(args: List[str]) -> int:
    """調用 get_exported_artifacts() 並以對齊表格輸出導出物料清冊。"""
    ...
```

---

### 2.3 微內核 Hook 合約

```python
# ── source/agents-workflow/scripts/hook.core.py ───────────────────────────
from core.events import ExecutionContext

def on_reload(ctx: ExecutionContext) -> None:
    """
    微內核 Stage 4 依賴注入與事件廣播回呼。
    自動調用 ArtifactCompiler().compile_all() 完成物化自愈。
    """
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[1. 靜態資產空間]
├── standards/ (DocumentationStandards.md, DevelopmentStandards.md)
├── workflows/ (ContextInit.md)
├── templates/ (header.md, P00~P07.md, FT_plan.md, umbrella_overview.md, changelog.md, R_research_report.md, handoff.md)
│       │
│       ▼
[2. 工廠核心編譯器]
└── agents_workflow/compiler.py (Topological Scan + Multi-pass State Machine)
        │
        ▼
[3. CLI & Hook 門面]
├── scripts/cli.py (compile, tokens, list)
└── scripts/hook.core.py (on_reload)
        │
        ▼
[4. 宣告式 Manifest 綁定]
└── manifest.json (export 16 項, insert header replace, token)
        │
        ▼
[5. 單元與沙盒測試]
└── tests/test_compiler.py (100% 覆蓋驗證)
```
