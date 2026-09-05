# knowledge-db 多語言語意解析器使用指南 (Parsers Guide)

> 模組名稱：`knowledge-db`  
> 核心模組：`knowledge_db.parsers`  
> 核心引擎：`tree-sitter` S-Expression 宣告式查詢驅動器 (`TreeSitterDriver`)  
> 架構原則：100% 透過 `contributes.knowledge_db` 動態驅動 (Zero-Privilege Dogfooding)  

---

## 📌 1. 概述與解析器架構

`knowledge-db` 解析器子系統負責將各類原始碼（Python, C/C++, C#, JS/TS, Markdown, SPICE 等）轉譯為統一巢狀語意資料模型 [`UnifiedSymbol`](./architecture.md#2-統一符號資料模型-unifiedsymbol)。

### 架構層次
- **`BaseParser`**：所有語言解析器之抽象基底類別，定義 `can_parse(file_path)`、`parse(file_path, content, space)`、`extract_call_sites` 與 `extract_imports`。
- **`TreeSitterDriver`**：通用聲明式 AST 解析驅動器，透過載入指定語言之 S-Expression (`assets/queries/*.scm`) 語法規則，自動完成符號樹建構、階層推導、呼叫點解析與檔頭 import 提取。
- **`LanguageRegistry` / `ParserRegistry`**：動態外掛註冊中心，完全由 `contributes.knowledge_db.languages` 驅動，模組內建語言亦透過自貢獻 (`contributes/knowledge-db.json`) 物化，核心無特權代碼。

---

## 🧩 2. 內建核心語言解析器

| 解析器名稱 | 支援副檔名 | 核心解析技術 | 提取語意維度 |
| :--- | :--- | :--- | :--- |
| **`PythonParser`** | `.py`, `.pyi` | Tree-sitter (`tree_sitter_python`) + `python.scm` | Module, Class, Method, Function, Decorator, Parameters, Docstring, Return Type, Call Sites, Imports |
| **`MarkdownParser`** | `.md`, `.markdown` | Tree-sitter (`tree_sitter_markdown`) + `markdown.scm` | Headings (H1~H6), Blockquote, Code Blocks, Links (`DOC_LINK`), Call Sites (`DOC_CALL_SITE`) |
| **`CppParser`** | `.cpp`, `.hpp`, `.h`, `.c`, `.cc`, `.cxx` | Tree-sitter (`tree_sitter_cpp`, `tree_sitter_c`) | Class, Struct, Enum, Function, Method, Doxygen/Comments, Call Sites (`->`, `::`), Imports (`#include`, `using`) |
| **`CSharpParser`** | `.cs` | Tree-sitter (`tree_sitter_c_sharp`) + `c_sharp.scm` | Namespace, Class, Interface, Struct, Method, Property, XML Doc, Call Sites, Imports (`using`) |
| **`JsTsParser`** | `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs` | Tree-sitter (`tree_sitter_typescript`) + `typescript.scm` | Class, Interface, Type Alias, Enum, Function, Method, JSDoc, Call Sites, Imports (`import`, `require`) |
| **`SpiceParser`** | `.cir`, `.sp`, `.spice`, `.net` | 自訂自貢獻解析器 (`SpiceParser`) | Subcircuit (`.subckt`), Model (`.model`), Component Instance, Directives, Parameters |
| **`HtmlParser`** | `.html`, `.htm` | 自訂自貢獻解析器 (`HtmlParser`) | `<title>`, `<h1>`~`<h6>`, `#id` 選擇器, HTML5 語意標籤, HTML 註解 |
| **`CssParser`** | `.css`, `.scss`, `.less` | 自訂自貢獻解析器 (`CssParser`) | Class 選擇器 (`.class`), ID 選擇器 (`#id`), CSS 變數 (`--var`), `@keyframes` |

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
