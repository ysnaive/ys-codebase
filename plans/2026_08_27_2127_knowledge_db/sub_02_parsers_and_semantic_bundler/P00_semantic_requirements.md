# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge-db 子計畫 02: 多語言解析與語意打包 (Parsers & Semantic Bundler)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：接續 `knowledge-db` 主計畫之子計畫 02（`sub_02_parsers_and_semantic_bundler`）。基於 `sub_01` 建立的 `UnifiedSymbol`、`SpaceManager` 與 `FingerprintScanner` 基礎設施，實作可插拔多語言代碼與文檔語意解析器矩陣（`ParserRegistry`、`PythonParser`、`MarkdownParser`、`CppParser`、`CSharpParser`）以及符號語意打包與解包引擎（`SemanticBundler`）。
- **核心目標**：
  1. **解析器抽象與外掛註冊表 (`BaseParser` & `ParserRegistry`)**：
     - 定義 `BaseParser` 統一抽象介面（`can_parse` 與 `parse`）。
     - 實作 `ParserRegistry`，支援依副檔名/特徵動態分發解析器，並支援模組擴充注入。
  2. **多語言原生語意解析器矩陣 (Pluggable Parsers)**：
     - **`PythonParser`**：利用 Python 原生 `ast` 模組，完整解析 Class、Function、AsyncFunction、Method、Decorator、Docstring、Signature 與成員變數。
     - **`MarkdownParser`**：模擬輕量 Markdown 語意狀態機，提取 H1~H4 標題節點、表格 (`doc_table`)、段落/小節 (`doc_section`) 與代碼區塊。
     - **`CppParser`**：語意正則狀態機解析 C/C++（Class, Struct, Enum, Function, Macro, Doxygen/註解）。
     - **`CSharpParser`**：語意正則狀態機解析 C#（Namespace, Class, Interface, Struct, Method, Property, XML `<summary>` 註解）。
  3. **語意打包與解包引擎 (`SemanticBundler` & `SemanticBundle`)**：
     - 定義 `SemanticBundle` 自包含資料結構（版本、空間名、符號清單、同義詞、元數據）。
     - 實作 `bundle_space`、`export_bundle`（原子輸出至 `storage://knowledge-db/bundles/<space>.bundle.json` 或指定路徑）與 `import_bundle`（反序列化還原）。
  4. **零外部相依 (Zero External Dependency)**：100% 採用 Python 3.9+ 原生標準庫（`ast`, `re`, `json`, `pathlib`, `dataclasses` 等）。
- **邊界排除 (Explicitly Excluded)**：
  - 分詞器 (`CodeTokenizer`)、BM25 倒排索引構建與檢索引擎留待 `sub_03` 實作。
  - 對外完整 CLI 指令集與 agents-workflow 深度連動留待 `sub_04` 實作。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

### [P00:DR-01] 解析器架構與外掛註冊模型 (ParserRegistry)
- **`BaseParser` 契約**：
  ```python
  class BaseParser(ABC):
      @abstractmethod
      def can_parse(self, file_path: Union[str, Path]) -> bool:
          """判斷是否能解析該檔案 (依副檔名或前綴特徵)"""
          ...

      @abstractmethod
      def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
          """解析檔案字串內容並產出 UnifiedSymbol 清單"""
          ...
  ```
- **`ParserRegistry` 行為**：
  - 預設內建註冊 `PythonParser` (`.py`, `.pyi`)、`MarkdownParser` (`.md`, `.markdown`)、`CppParser` (`.cpp`, `.hpp`, `.h`, `.c`, `.cc`)、`CSharpParser` (`.cs`)。
  - 提供 `register_parser(parser: BaseParser, priority: int = 100)`。
  - 提供 `get_parser(file_path: Union[str, Path]) -> Optional[BaseParser]` 與 `parse_file(file_path, content, space) -> List[UnifiedSymbol]`。

---

### [P00:DR-02] 各語言解析深度與語意提取規範

#### 1. PythonParser (AST 原生解析)
- 使用 `ast.parse`。
- 類別提取：`name`, `kind="class"`, `signature="class ClassName(Base1, Base2)"`, `docstring=ast.get_docstring(node)`, `members` 包含公開/內部方法與屬性。
- 函式提取：`name`, `kind="function" / "method"`, `signature="def func(a: int, b: str = '') -> bool"`, `docstring`。
- 容錯：若 AST 語法錯誤（`SyntaxError`），降級記錄 Warning 並安全回傳空清單，不中斷整體批次解析。

#### 2. MarkdownParser (文檔節點提取)
- H1~H4 標題：提取為 `SymbolKind.DOC_HEADING_1` ~ `DOC_HEADING_4`，`name` 為標題文字，`docstring` 為該標題下至下一個同級/高級標題前的正文內容摘要。
- 表格提取：`SymbolKind.DOC_TABLE`，`name` 為表格前導標題或表格首行欄位清單，`docstring` 包含 Markdown 表格原始字串。

#### 3. CppParser (C/C++ 語意狀態機)
- 支援 Class / Struct / Enum / Function / Macro 定義提取。
- 支援 Doxygen 註解（`/** ... */` 與 `/// ...`）與一般註解綁定至緊鄰的符號。

#### 4. CSharpParser (C# 語意狀態機)
- 支援 Namespace, Class, Interface, Struct, Method, Property 提取。
- 支援 XML 註解 `<summary>...</summary>` 提取為 `docstring`。

---

### [P00:DR-03] 語意打包資料結構與 Bundle 格式 (`SemanticBundle`)

```python
@dataclass(frozen=True)
class SemanticBundle:
    version: str                                     # Bundle 格式版本 (如 "1.0.0")
    space_name: str                                  # 所屬空間識別名稱
    created_at: str                                  # ISO-8601 時間戳
    symbols: List[UnifiedSymbol] = field(default_factory=list)
    thesaurus: List[ThesaurusGroup] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "SemanticBundle": ...
```

- **檔案輸出**：預設輸出至 `storage://knowledge-db/bundles/<space_name>.bundle.json`。
- **寫入安全**：使用暫存檔 + `os.replace` 原子寫入。

---

## 3. 開放議題與確認紀錄

- [x] **確認 1 (Parser 覆蓋度與副檔名擴充)**：內建 Python (.py, .pyi)、Markdown (.md, .markdown)、C++ (.cpp, .hpp, .h, .c, .cc)、C# (.cs) 4 大解析器，符合預期。
- [x] **確認 2 (Markdown 解析顆粒度)**：以 Heading (H1~H4) 作為主要符號切割邊界，包含表格與內文摘要。
- [x] **確認 3 (Bundle 格式)**：打包格式採用 `.bundle.json`，原子輸出至 `storage://knowledge-db/bundles/<space>.bundle.json`。
