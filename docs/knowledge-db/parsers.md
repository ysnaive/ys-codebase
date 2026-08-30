# knowledge-db 多語言語意解析器使用指南 (Parsers Guide)

> 模組名稱：`knowledge-db`  
> 核心模組：`knowledge_db.parsers`  
> 依賴：100% Python 原生標準庫 (Zero External Dependency)  

---

## 📌 1. 概述與解析器架構

`knowledge-db` 解析器子系統負責將各類原始碼（Python, C/C++, C#）與 Markdown 文檔轉譯為統一語意資料模型 [`UnifiedSymbol`](./architecture.md#2-統一符號資料模型-unifiedsymbol)。

### 架構層次
- **`BaseParser`**：所有語言解析器之抽象基底類別，定義 `can_parse(file_path)` 與 `parse(file_path, content, space)`。
- **`ParserRegistry`**：動態外掛註冊與調度分發中心，支援依優先權覆蓋與副檔名分發。

---

## 🧩 2. 內建核心語言解析器

| 解析器名稱 | 支援副檔名 | 核心解析技術 | 提取語意維度 |
| :--- | :--- | :--- | :--- |
| **`PythonParser`** | `.py`, `.pyi` | Python 原生 `ast` 模組 | Class, Function, AsyncFunction, Method, Decorator, Docstring, Signature (含型別標註與預設值), MemberInfo |
| **`MarkdownParser`** | `.md`, `.markdown` | 語意狀態機 (純正則) | H1~H4 標題節點 (`DOC_HEADING_1~4`), 表格 (`DOC_TABLE`), 區塊摘要 (`DOC_SECTION`) |
| **`CppParser`** | `.cpp`, `.hpp`, `.h`, `.c`, `.cc`, `.cxx` | 語意狀態機 + 巨集掃描器 | Class, Struct, Enum, Function, `#define` 巨集, Doxygen 註解 (`///`, `/** */`) |
| **`CSharpParser`** | `.cs` | 語意狀態機 + XML Doc 提取器 | Namespace, Class, Interface, Struct, Method, Property, XML `<summary>` 註解 |
| **`JsTsParser`** | `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`, `.mts`, `.cts` | 語意狀態機 + JSDoc 提取器 | Class, Interface, Type Alias, Enum, Function, Arrow Function, Class Method, JSDoc 註解 |
| **`HtmlParser`** | `.html`, `.htm` | 語意標籤正則狀態機 | `<title>`, `<h1>`~`<h6>`, `#id` 選擇器, HTML5 語意標籤 (`<main>`, `<section>` 等), HTML 註解 |
| **`CssParser`** | `.css`, `.scss`, `.less` | 選擇器與變數正則狀態機 | Class 選擇器 (`.class`), ID 選擇器 (`#id`), CSS 變數 (`--var`), SASS (`$var`), LESS (`@var`), `@keyframes` |

---

## 🛠️ 3. Python SDK 使用範例

### 3.1 使用 ParserRegistry 批次調度
```python
from knowledge_db.parsers import ParserRegistry

registry = ParserRegistry(register_defaults=True)

# 解析 Python 檔案
py_symbols = registry.parse_file(
    file_path="src/engine.py",
    content="class Engine:\n    def run(self): pass",
    space="default"
)

# 解析 Markdown 文檔
md_symbols = registry.parse_file(
    file_path="docs/README.md",
    content="# Title\nIntroduction paragraph.",
    space="default"
)
```

### 3.2 註冊自訂解析器擴充 (Custom Parser)
```python
from knowledge_db.parsers import BaseParser, ParserRegistry
from knowledge_db.schema import UnifiedSymbol, SymbolKind, LanguageType

class RustParser(BaseParser):
    def can_parse(self, file_path):
        return str(file_path).endswith(".rs")

    def parse(self, file_path, content, space):
        # 自訂解析邏輯
        return [
            UnifiedSymbol(
                id=UnifiedSymbol.compute_id(space, file_path, "main", SymbolKind.FUNCTION.value, 1),
                name="main",
                kind=SymbolKind.FUNCTION.value,
                file_path=file_path,
                line_number=1,
                language="rust",
                signature="fn main()",
            )
        ]

registry = ParserRegistry()
registry.register_parser(RustParser(), priority=150)
```

---

## 🛡️ 4. 容錯與安全防護

- **語法錯誤防禦 (EC-01)**：`PythonParser` 捕獲 `SyntaxError`，發出 Warning 日誌並安全降級回傳空清單，嚴禁導致整體批次崩潰。
- **未知格式防禦 (EC-02)**：`ParserRegistry` 遇不支援的檔案副檔名時，安全回傳空清單。
- **純文字降級 (EC-03)**：`MarkdownParser` 面對無標題之純文字 Markdown 檔案，自動降級提取為 `DOC_SECTION` 符號。
