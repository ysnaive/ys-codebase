# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge-db 子計畫 02: 多語言解析與語意打包 (Parsers & Semantic Bundler)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| **`BaseParser`** | `knowledge_db/parsers/base.py` | Public (ABC) | 多語言解析器基礎抽象介面 |
| **`ParserRegistry`** | `knowledge_db/parsers/registry.py` | Public | 動態解析器註冊、副檔名匹配與解析分發中心 |
| **`PythonParser`** | `knowledge_db/parsers/python_parser.py` | Public | Python 原始碼 AST 原生語法樹解析器 |
| **`MarkdownParser`** | `knowledge_db/parsers/markdown_parser.py` | Public | Markdown 文檔標題/表格/段落狀態機解析器 |
| **`CppParser`** | `knowledge_db/parsers/cpp_parser.py` | Public | C/C++ 類別/結構/函式/巨集語意狀態機解析器 |
| **`CSharpParser`** | `knowledge_db/parsers/csharp_parser.py` | Public | C# 命名空間/類別/介面/XML 註解狀態機解析器 |
| **`SemanticBundle`** | `knowledge_db/bundler.py` | Public | 自包含語意打包資料模型 (不可變 `@dataclass`) |
| **`SemanticBundler`** | `knowledge_db/bundler.py` | Public | 空間語意打包、原子導出與載入還原引擎 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 解析器抽象與註冊表 (`knowledge_db/parsers/`)

```python
class BaseParser(ABC):
    """多語言解析器基礎抽象類別"""

    @abstractmethod
    def can_parse(self, file_path: Union[str, Path]) -> bool:
        """
        判斷此解析器是否支援解析該檔案。
        :param file_path: 檔案路徑或檔名
        :return: 若支援回傳 True，否則 False
        """

    @abstractmethod
    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """
        解析檔案文字內容並產生 UnifiedSymbol 符號清單。
        :param file_path: 相對於來源根目錄之正規化路徑 (forward slash)
        :param content: 檔案文字內容
        :param space: 所屬空間識別名稱
        :return: 提取之 UnifiedSymbol 清單
        """


class ParserRegistry:
    """動態外掛解析器註冊表與分發中心"""

    def __init__(self, register_defaults: bool = True):
        """
        初始化解析器註冊表。
        :param register_defaults: 是否自動註冊 Python, Markdown, C++, C# 預設解析器
        """

    def register_parser(self, parser: BaseParser, priority: int = 100) -> None:
        """
        註冊解析器實例。
        :param parser: BaseParser 子類實例
        :param priority: 優先級數值 (數值愈大優先級愈高，預設 100)
        """

    def get_parser(self, file_path: Union[str, Path]) -> Optional[BaseParser]:
        """
        依檔案路徑或副檔名尋找符合且優先級最高之解析器。
        若無匹配解析器回傳 None。
        """

    def parse_file(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """
        尋找合適解析器並執行解析；若無匹配解析器回傳空清單 [] (EC-02)。
        """
```

---

### 2.2 具體語言解析器規格

```python
class PythonParser(BaseParser):
    SUPPORTED_EXTENSIONS = {".py", ".pyi"}
    def can_parse(self, file_path: Union[str, Path]) -> bool: ...
    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """使用 ast.parse 走訪 AST 節點，提取 Class, Function, Method, Docstring, Members"""

class MarkdownParser(BaseParser):
    SUPPORTED_EXTENSIONS = {".md", ".markdown"}
    def can_parse(self, file_path: Union[str, Path]) -> bool: ...
    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """狀態機掃描 H1~H4 (DOC_HEADING_1~4), Tables (DOC_TABLE), 段落摘要"""

class CppParser(BaseParser):
    SUPPORTED_EXTENSIONS = {".cpp", ".hpp", ".h", ".c", ".cc", ".cxx", ".hxx"}
    def can_parse(self, file_path: Union[str, Path]) -> bool: ...
    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """語意狀態機提取 Class, Struct, Enum, Function, Macro 與 Doxygen 註解"""

class CSharpParser(BaseParser):
    SUPPORTED_EXTENSIONS = {".cs"}
    def can_parse(self, file_path: Union[str, Path]) -> bool: ...
    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """語意狀態機提取 Namespace, Class, Interface, Struct, Method, Property 與 XML Doc"""
```

---

### 2.3 語意打包資料結構與 Bundler 引擎 (`knowledge_db/bundler.py`)

```python
@dataclass(frozen=True)
class SemanticBundle:
    version: str                                     # Bundle 規範版本 (預設 "1.0.0")
    space_name: str                                  # 所屬空間名稱
    created_at: str                                  # ISO-8601 產生時間戳
    symbols: List[UnifiedSymbol] = field(default_factory=list)
    thesaurus: List[ThesaurusGroup] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SemanticBundle": ...


class SemanticBundler:
    """語意打包與解包引擎"""

    def __init__(
        self,
        space_manager: SpaceManager,
        parser_registry: Optional[ParserRegistry] = None,
        scanner: Optional[FingerprintScanner] = None,
    ):
        """
        初始化 SemanticBundler。
        :param space_manager: SpaceManager 實例
        :param parser_registry: ParserRegistry 實例 (若為 None 則自動建立預設註冊表)
        :param scanner: FingerprintScanner 實例 (若為 None 則自動建立)
        """

    def bundle_space(
        self,
        space_config: SpaceConfig,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> SemanticBundle:
        """
        掃描並解析空間內所有有效來源檔案，產出完整之 SemanticBundle。
        """

    def export_bundle(
        self,
        bundle: SemanticBundle,
        target_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """
        以原子寫入方式導出 Bundle 為 JSON 檔案。
        若未指定 target_path，預設寫入至 storage://knowledge-db/bundles/<space_name>.bundle.json。
        :return: 導出之實體檔案 Path
        """

    def import_bundle(self, bundle_path: Union[str, Path]) -> SemanticBundle:
        """
        載入並反序列化 Bundle 檔案。若檔案不存在或損毀拋出 KnowledgeDBError。
        """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
┌────────────────────────────────────────────────────────┐
│ Level 1: 解析器基礎抽象 (knowledge_db/parsers/base.py)  │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 2: 四大多元語言解析器實作                        │
│ - python_parser.py (AST 原生解析)                      │
│ - markdown_parser.py (文檔狀態機)                      │
│ - cpp_parser.py (C/C++ 狀態機)                         │
│ - csharp_parser.py (C# 狀態機)                         │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 3: 解析器註冊表與套件導出                        │
│ - registry.py (ParserRegistry)                         │
│ - parsers/__init__.py                                  │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 4: 語意打包引擎 (knowledge_db/bundler.py)        │
│ (SemanticBundle, SemanticBundler)                      │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 5: CLI 入口擴充與公開導出                        │
│ - scripts/cli.py (bundle 子指令)                       │
│ - manifest.json (命令防呆宣告)                         │
│ - knowledge_db/__init__.py                             │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 6: 完整單元測試套件                              │
│ - tests/test_parsers.py (FT-01~06)                     │
│ - tests/test_bundler.py (FT-07~08, ET-01)              │
└────────────────────────────────────────────────────────┘
```
