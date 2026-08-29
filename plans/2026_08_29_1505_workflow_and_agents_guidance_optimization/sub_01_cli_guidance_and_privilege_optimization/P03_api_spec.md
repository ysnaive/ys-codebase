# API 與介面規格書 (API & Interface Specification)

> 功能名稱：`sub_01_cli_guidance_and_privilege_optimization`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `get_agents_cli_guild` | `source/core/core/providers.py` | Public | 動態編譯全系統已聚合之 commands 為三級權限分組之 Markdown 表格與防呆手冊。 |
| `get_phase_cli_guild` | `source/core/core/providers.py` | Public | 依據給定之 Phase 標籤過濾全系統 commands，動態生成該階段專屬之 JIT 推薦指令與紅線警示。 |
| `commands` Schema 契約 | `source/core/contributes.format.md` | Public Specification | 定義模組向 core 宣告 commands 之擴充 Schema（含 `tier`, `phases`, `case_pros`, `case_cons`）。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
from typing import Dict, Any, Optional, List, Tuple

def get_agents_cli_guild(context: Optional[Any] = None, **kwargs: Any) -> str:
    """
    動態編譯全系統已宣告之 contributes.core.commands 為三級權限 Markdown 防呆手冊。

    分級分組邏輯：
    - 🟢 safe: 自主安全指令（唯讀、沙盒跑測、靜態預檢、知識庫檢索）
    - 🟡 conditional: 階段約束指令（需在特定 Phase 或滿足除錯前置條件下方可執行）
    - 🔴 gated: 授權守門指令（🚨 絕對禁止擅自執行，必須獲開發者顯式指示方可調用）

    Fallback 契約：
    - 若指令缺失 tier 或 tier 非標準值，自動 fallback 為 'conditional' (🟡)。
    - 若 pros 與 cons 皆無，自動排除於手冊中。

    :param context: 可選之編譯期上下文（由 agents-workflow compiler 提供）
    :return: 格式化完成之三級分組 Markdown 防呆手冊文字
    """
    ...

def get_phase_cli_guild(context: Optional[Any] = None, phase: Optional[str] = None, **kwargs: Any) -> str:
    """
    依據給定之 Phase 標籤動態過濾 commands，產出適用於該階段之極簡 JIT 指令引導。

    過濾邏輯：
    - 檢查 commands 中宣告之 phases 清單。
    - 若 cmd.phases 包含目標 phase（或全域通用通用標籤），則納入該階段推薦指令清單。
    - 若 cmd.tier == 'gated' 且不屬於當前階段，輸出明確之禁止提醒。

    :param context: 可選之編譯期上下文（可自 context.token 或 context.phase 提取 Phase 名稱）
    :param phase: 明確指定之 Phase 字串（例："P00", "P05", "P06", "P07", "FT-1", "RESEARCH"）
    :return: 適用於模板頂部 HTML 註解之 JIT 指令導引文字
    """
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Core Schema & Providers]
  ├── source/core/contributes.format.md (定義 Schema 規格)
  └── source/core/core/providers.py (實作 get_agents_cli_guild 三級分組與 get_phase_cli_guild)
       │
       ▼
[Step 2: Contributes Metadata Updates]
  ├── source/core/contributes/core.json (補齊 core 指令之 tier/phases)
  ├── source/dev/contributes/core.json (補齊 dev 指令之 tier/phases)
  ├── source/knowledge-db/contributes/core.json (補齊 knowledge-db 指令之 tier/phases)
  └── source/agents-workflow/contributes/core.json (補齊 agents-workflow 指令之 tier/phases)
       │
       ▼
[Step 3: Assets & Workflow Standards Refinement]
  ├── source/knowledge-db/assets/KnowledgeAgentsStandards.md (強化日常搜尋強制替代與 --ftype 決策樹)
  ├── source/agents-workflow/assets/workflows/ContextInit.md (職責解耦：聚焦 AgentsStandards)
  └── source/agents-workflow/assets/standards/AgentsStandards.md (剛性純化：排除流程細節)
       │
       ▼
[Step 4: Unit Testing & Full Regression]
  ├── source/core/tests/test_cli_guild.py (新增三級權限、Phase JIT 與容錯單元測試)
  └── 全系統回歸驗證 (python test/run_regression.py)
```
