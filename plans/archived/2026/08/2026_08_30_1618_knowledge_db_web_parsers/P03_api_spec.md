# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge-db 模組 Web 語言解譯器 (JS/TS/HTML/CSS Parsers)  
> 建立日期：2026-08-30  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `LanguageType` | `source/knowledge-db/knowledge_db/schema.py` | Public | 新增 `JAVASCRIPT`, `TYPESCRIPT`, `HTML`, `CSS` 列舉 |
| `JsTsParser` | `source/knowledge-db/knowledge_db/parsers/js_ts_parser.py` | Public | JS/TS 類別、介面、型別、函式與 JSDoc 解析 |
| `HtmlParser` | `source/knowledge-db/knowledge_db/parsers/html_parser.py` | Public | HTML 網頁標題、標題階層、ID 標籤元素解析 |
| `CssParser` | `source/knowledge-db/knowledge_db/parsers/css_parser.py` | Public | CSS/SCSS/LESS Class/ID 選擇器與變數解析 |
| `ParserRegistry` | `source/knowledge-db/knowledge_db/parsers/registry.py` | Public | 預設註冊新 Web 解析器實例 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
from pathlib import Path
from typing import List, Set, Union
from knowledge_db.parsers.base import BaseParser
from knowledge_db.schema import UnifiedSymbol

class JsTsParser(BaseParser):
    SUPPORTED_EXTENSIONS: Set[str] = {
        ".js", ".jsx", ".mjs", ".cjs",
        ".ts", ".tsx", ".mts", ".cts"
    }

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        """判斷副檔名是否屬於 JS/TS 技術棧"""
        ...

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """解析 JS/TS 代碼並返回 UnifiedSymbol 清單"""
        ...

class HtmlParser(BaseParser):
    SUPPORTED_EXTENSIONS: Set[str] = {".html", ".htm"}

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        """判斷副檔名是否屬於 HTML"""
        ...

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """解析 HTML 標籤結構並返回 UnifiedSymbol 清單"""
        ...

class CssParser(BaseParser):
    SUPPORTED_EXTENSIONS: Set[str] = {".css", ".scss", ".less"}

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        """判斷副檔名是否屬於 CSS/SCSS/LESS"""
        ...

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """解析 CSS 選擇器與變數並返回 UnifiedSymbol 清單"""
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. [Schema Layer] schema.py (LanguageType Enum)
       ↓
2. [Parser Implementations]
   ├── js_ts_parser.py (JsTsParser)
   ├── html_parser.py  (HtmlParser)
   └── css_parser.py   (CssParser)
       ↓
3. [Registry & Export Layer]
   ├── registry.py (ParserRegistry)
   └── __init__.py (Package export)
       ↓
4. [Test Layer] test_web_parsers.py
```
