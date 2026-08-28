# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge_db_search_snippet_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `CodeSnippet` | `source/knowledge-db/knowledge_db/retrieval.py` | Public | 結構化代碼片段資料類別，支援文字行號渲染與字典轉換。 |
| `SnippetExtractor` | `source/knowledge-db/knowledge_db/retrieval.py` | Public | 原始碼安全切片讀取器，負責行號邊界截斷、編碼容錯與 Docstring 提取。 |
| `SearchResult` | `source/knowledge-db/knowledge_db/retrieval.py` | Public | 搜尋結果資料類別，擴充 `code_snippet: Optional[CodeSnippet]` 欄位。 |
| `KnowledgeEngine.search` | `source/knowledge-db/knowledge_db/engine.py` | Public | 核心搜尋入口，新增 `snippet: bool` 與 `context_lines: int` 參數。 |
| `cli.main` (search router) | `source/knowledge-db/scripts/cli.py` | Public | CLI 檢索進入點，新增 `--snippet` / `-s` / `--preview` 解析與排版。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

@dataclass
class CodeSnippet:
    """結構化代碼片段與摘要"""
    lines: List[Tuple[int, str]]
    start_line: int
    end_line: int
    target_line: int
    docstring_summary: str = ""
    is_truncated: bool = False
    error: Optional[str] = None

    def format_text(self, prefix: str = "    ") -> str:
        """格式化為帶有行號對齊的純文字區塊"""
        ...

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典結構 (供 JSON 輸出)"""
        ...


class SnippetExtractor:
    """原始碼片段延遲提取器"""

    def __init__(self, workspace_root: Optional[Union[str, Path]] = None, max_lines: int = 12):
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self.max_lines = max_lines

    def resolve_rel_path(self, file_path: Union[str, Path]) -> str:
        """將實體檔案路徑正規化為相對於 Workspace 根目錄之標準路徑"""
        ...

    def extract(
        self,
        file_path: Union[str, Path],
        line_number: int,
        context_before: int = 2,
        context_after: int = 4,
        docstring: str = "",
    ) -> CodeSnippet:
        """
        自實體檔案中安全切片提取原始碼區塊。
        :param file_path: 檔案實體路徑或相對於 workspace 路徑
        :param line_number: 目標符號起始行號 (1-indexed)
        :param context_before: 前置上下文行數 (預設 2 行)
        :param context_after: 後置上下文行數 (預設 4 行)
        :param docstring: 符號已有之 docstring 內文
        :return: CodeSnippet 物件
        """
        ...


class KnowledgeEngine:
    ...
    def search(
        self,
        query: str,
        space: Optional[str] = None,
        kinds: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        min_score: float = 0.01,
        limit: int = 10,
        snippet: bool = False,
        context_lines: int = 3,
    ) -> List[SearchResult]:
        """
        執行語意搜尋。當 snippet=True 時，為 Top-K 結果延遲附加 CodeSnippet 物件。
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Stage 1: Core Extractor]
source/knowledge-db/knowledge_db/retrieval.py (定義 CodeSnippet, SnippetExtractor, 更新 SearchResult)
         │
         ▼
[Stage 2: Engine Facade & Path Normalization]
source/knowledge-db/knowledge_db/engine.py (更新 KnowledgeEngine.search，串接 Snippet 提取與路徑解算)
         │
         ▼
[Stage 3: CLI Router & Presentation]
source/knowledge-db/scripts/cli.py (支援 --snippet/-s/--preview, 渲染格式化代碼區塊與 JSON 結構)
         │
         ▼
[Stage 4: Workflow Assets & Contributes]
source/knowledge-db/assets/KnowledgeAgentsStandards.md, phase00_guild.md, research_guild.md, contributes/core.json
         │
         ▼
[Stage 5: Test Suite Verification]
source/knowledge-db/tests/test_retrieval.py, test_cli.py (FT-01~06, ET-01~04 測試套件)
```
