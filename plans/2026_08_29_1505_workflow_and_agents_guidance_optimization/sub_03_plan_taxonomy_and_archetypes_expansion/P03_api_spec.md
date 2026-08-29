# API 與介面規格書 (API & Interface Specification)

> 功能名稱：計畫分流維度重構、工作類型拓撲擴充與策略資產規範 (Plan Taxonomy, Archetypes & Strategic Assets)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Draft  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別 / 檔案名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| **`RoadmapManager`** | `agents_workflow/roadmap.py` | Public | 負責 `workflow.plans://roadmap/` 空間掃描、Markdown AST/Regex Header 元資料提取與問題背景摘要格式化。 |
| **`RoadmapItem`** | `agents_workflow/roadmap.py` | Public | Roadmap 條目資料模型（結構化儲存主題、狀態、日期、背景量化摘要、完整路徑）。 |
| **`cmd_roadmap`** | `scripts/cli.py` | Public | CLI 指令分發入口，支援 `python yscb.py agents-workflow roadmap` 與可選參數。 |
| **`contributes/core.json`** | `contributes/core.json` | Public | 向 Core 註冊 `workflow.roadmap` 語意 URI 協議與 `roadmap` CLI 指令元資料（三級權限 tier: safe）。 |
| **`contributes/agents-workflow.json`** | `contributes/agents-workflow.json` | Public | 註冊新模板（`roadmap.md`、`P00_discuss.md`）、新工作流（`Roadmap.md`）與新 Token 錨點。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `RoadmapItem` 資料模型 (`agents_workflow/roadmap.py`)

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any

@dataclass
class RoadmapItem:
    """Roadmap 條目結構化模型"""
    topic: str                     # 主題名稱 (自檔名或 Header 提取)
    filename: str                  # 實體檔案名稱 (例: release_binary_storage_optimization.md)
    path: Path                     # 絕對路徑
    title: str                     # 頂部 H1 標題
    status: str                    # 狀態 (Backlog | Proposed | Deferred | In Progress)
    date: str                      # 歸檔/更新日期 (YYYY-MM-DD)
    problem_summary: str           # "## 1. 問題陳述與根因量化" 區塊提取之摘要 (前 3~5 行文字或核心結論)
    has_valid_header: bool         # 是否具備合規之標準元資料 Header
```

### 2.2 `RoadmapManager` API 簽名 (`agents_workflow/roadmap.py`)

```python
class RoadmapManager:
    """Roadmap 策略資產掃描與摘要管理器 (零外部依賴)"""

    def __init__(self, roadmap_dir: Optional[Path] = None, host_dir: Optional[str] = None):
        """
        初始化 RoadmapManager。
        若未傳入 roadmap_dir，自動透過 core.uri.resolve("workflow.roadmap://") 解析；
        若解析失敗或未定義，fallback 至 host_dir/plans/roadmap/。
        """
        pass

    def scan_roadmaps(self) -> List[RoadmapItem]:
        """
        掃描 roadmap_dir 下的所有 *.md 檔案。
        強韌容錯 (EC-04)：逐檔提取 Header 與問題背景區塊，若格式非標準則自動 fallback，絕不拋出例外。
        返回依日期倒序排列的 RoadmapItem 清單。
        """
        pass

    def format_summary_table(self, items: Optional[List[RoadmapItem]] = None) -> str:
        """
        格式化輸出極簡 ASCII / Markdown 摘要對照表。
        若 items 為空 (EC-03)，回傳友好提示「目前無任何待啟動之 Roadmap 技術儲備」。
        每筆條目輸出：[狀態] 主題名稱 (更新日期) + 2~3 行問題背景摘要。
        """
        pass

    def get_roadmap(self, topic_or_file: str) -> Optional[RoadmapItem]:
        """依主題名稱或檔名精準查找單一 Roadmap 條目。"""
        pass
```

### 2.3 CLI 指令簽名 (`scripts/cli.py`)

```python
def cmd_roadmap(args: List[str]) -> int:
    """
    處理 `agents-workflow roadmap` CLI 指令。
    用法:
      python yscb.py agents-workflow roadmap          # 條列所有 Roadmap 條目與摘要
      python yscb.py agents-workflow roadmap <topic>  # 檢視特定 Roadmap 詳細內容
    返回:
      0: 成功執行 (含無儲備安全提示)
      1: 參數或嚴重 IO 錯誤
    """
    pass
```

---

## 3. 佔位符體系嚴格規範與二分法二次確認 (Placeholders & Token Anchors)

依據專案 Stage 2 佔位符二分法解析機制 (`compiler.py`)，本計畫產出之所有文檔原始碼必須 100% 嚴格遵守以下佔位符規範：

### 3.1 路徑佔位符規範 (Path Placeholders)

| 佔位符語法 | 解算目標 | 適用情境 | 範例與編譯預期 |
| :--- | :--- | :--- | :--- |
| **`__#{uri}__`**<br/>*(Local Relative)* | 相對於產物目標發布目錄之**相對路徑** | **Markdown 超連結**（編譯器會自動吞噬外層反引號，產出合規 CommonMark） | `` [標準模板](`__#{module://agents-workflow/assets/templates/roadmap.md}__`) ``<br/>➔ `[標準模板](../templates/roadmap.md)` |
| **`__${uri}__`**<br/>*(Project Relative)* | 相對於**專案根目錄之確定性路徑** | **Agent view_file 指引或終端 CLI 指令**（保留反引號） | `` `python __${yscb.host://yscb.py}__ agents-workflow roadmap` ``<br/>➔ `` `python yscb.py agents-workflow roadmap` `` |

### 3.2 現有內容 Token 復用與無損繼承清單 (Existing Token Reuse)

- **`__@{BEGIN_HTML_ANNOTATION}__` / `__@{END_HTML_ANNOTATION}__`**：所有新增/修改之模板與工作流頂部導引註解。
- **`__@{PHASEXX_HEADER}__`**：`P00_discuss.md` 等模板共通標頭。
- **`__@{PHASE00_HEADER}__` / `__@{PHASE00_AGENTS_GUILD}__` / `__@{PHASE00_TEMPLATE}__`**：**既有 Phase 0 Token 100% 無損繼承**（維持 `PHASE{XX}_*` 全域命名一致性，僅更新 Token 描述使其指向 `P00_discuss.md`）。
- **`__@{AGENTS_CLI_GUILD}__`**：工作流與標準規範中動態注入 CLI 防呆對照表。
- **`__@{DYNAMIC_CONTEXT_MAP}__`**：`ContextInit.md` 頂部 JIT 語意 URI 地圖注入。

### 3.3 新增內容 Token 宣告清單 (New Tokens to Register)

| 新增 Token 名稱 | 宣告位置 | 核心用途與注入情境 |
| :--- | :--- | :--- |
| **`ROADMAP_HEADER`** | `contributes/agents-workflow.json` | `roadmap.md` 模板專屬標頭（`> 主題：... \n > 狀態：... \n > 歸檔日期：...`）。 |
| **`ROADMAP_TEMPLATE`** | `contributes/agents-workflow.json` | `roadmap.md` 模板尾部供專案特化擴充注入錨點。 |
| **`WORKFLOW_ROADMAP`** | `contributes/agents-workflow.json` | `Roadmap.md` 工作流尾部特化擴充注入錨點。 |

---

## 4. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 基礎協議與 Contributes 定義]
  ├── contributes/core.json (註冊 workflow.roadmap 協議與 roadmap CLI command)
  └── contributes/agents-workflow.json (註冊新 export、token 與模板更名)
            │
            ▼
[Step 2: 核心 SDK 與 CLI 工具實作]
  ├── agents_workflow/roadmap.py (實作 RoadmapManager 與 RoadmapItem)
  └── scripts/cli.py (實作 cmd_roadmap 並接入 CLI router)
            │
            ▼
[Step 3: 模板資產重構與新增]
  ├── assets/templates/P00_discuss.md (新建開放討論模板)
  ├── assets/templates/roadmap.md (新建標準技術路線圖模板)
  ├── assets/templates/umbrella_overview.md (修改標頭模式 B-1 / B-2)
  └── assets/templates/P00_semantic_requirements.md (安全移除/廢除舊名)
            │
            ▼
[Step 4: 工作流導引與標準手冊演進]
  ├── assets/workflows/Roadmap.md (新建 /Roadmap 工作流)
  ├── assets/workflows/NewPlan.md (重構延遲建檔、JIT分流、長對話調研阻斷)
  ├── assets/standards/DevelopmentStandards.md (4維度FastTrack/Umbrella雙軌/修訂計畫/調研3步SOP)
  └── assets/standards/AgentsStandards.md (P00_discuss 顧問紀律與分流守門)
            │
            ▼
[Step 5: 測試套件更新與全量驗證]
  ├── test/test_agents_workflow.py (新增 RoadmapManager、CLI 與佔位符測試)
  └── run_regression.py (全量 209/209 迴歸驗證)
```
