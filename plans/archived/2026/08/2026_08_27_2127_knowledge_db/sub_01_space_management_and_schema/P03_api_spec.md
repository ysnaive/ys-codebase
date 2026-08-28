# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge-db 子計畫 01: 空間管理與資料架構 (Space Management & Data Schema)  
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
| **`SymbolKind` / `LanguageType` / `SpaceOrigin`** | `knowledge_db/schema.py` | Public | 定義符號類型、程式語言與空間來源之標準列舉型別 |
| **`MemberInfo`** | `knowledge_db/schema.py` | Public | 結構化類別成員/函式參數模型，支援字典序列化 |
| **`UnifiedSymbol`** | `knowledge_db/schema.py` | Public | 跨語言不可變統一符號模型，提供 SHA1 唯一 ID 計算與序列化 |
| **`SpaceConfig`** | `knowledge_db/schema.py` | Public | 獨立解耦之空間組態模型，包含路徑清單與 `file_patterns` 過濾 |
| **`ThesaurusConfig`** | `knowledge_db/schema.py` | Public | 獨立解耦之同義詞群組資料結構與來源追蹤 |
| **`FileFingerprint` / `ScanDiffResult`** | `knowledge_db/scanner.py` | Public | 檔案增量指紋記錄與差異比對結果模型 |
| **`SpaceManager`** | `knowledge_db/space.py` | Public | 多空間雙軌聚合、階層優先權合併、語意 URI 解算與 VFS 目錄定位 |
| **`FingerprintScanner`** | `knowledge_db/scanner.py` | Public | 雙階增量指紋比對引擎、全空間聯集掃描與快取自癒持久化 |
| **`KnowledgeDBError` 及其子類** | `knowledge_db/exceptions.py` | Public | 模組專屬例外體系 (`SpaceNotFoundError`, `InvalidSpaceConfigError`, ...) |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 例外階層 (`knowledge_db/exceptions.py`)

```python
class KnowledgeDBError(Exception):
    """knowledge-db 模組基礎例外類別"""

class SpaceNotFoundError(KnowledgeDBError):
    """指定之空間名稱未註冊或不存在"""
    def __init__(self, space_name: str, available_spaces: Optional[List[str]] = None):
        msg = f"Space '{space_name}' not found."
        if available_spaces:
            msg += f" Available spaces: {', '.join(available_spaces)}"
        super().__init__(msg)
        self.space_name = space_name

class InvalidSpaceConfigError(KnowledgeDBError):
    """空間組態缺失必填欄位或格式不合法"""

class SchemaValidationError(KnowledgeDBError):
    """UnifiedSymbol 或 MemberInfo 資料校驗失敗"""

class FingerprintCorruptedError(KnowledgeDBError):
    """指紋庫快取檔案損毀或無法解析"""
```

---

### 2.2 核心資料模型 (`knowledge_db/schema.py`)

```python
class SymbolKind(str, Enum):
    CLASS = "class"
    STRUCT = "struct"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    ENUM = "enum"
    MACRO = "macro"
    VARIABLE = "variable"
    CONSTANT = "constant"
    DOC_HEADING_1 = "doc_heading_1"
    DOC_HEADING_2 = "doc_heading_2"
    DOC_HEADING_3 = "doc_heading_3"
    DOC_HEADING_4 = "doc_heading_4"
    DOC_TABLE = "doc_table"
    DOC_SECTION = "doc_section"

class LanguageType(str, Enum):
    PYTHON = "python"
    MARKDOWN = "markdown"
    CPP = "cpp"
    CSHARP = "csharp"
    JSON = "json"
    TEXT = "text"
    UNKNOWN = "unknown"

class SpaceOrigin(str, Enum):
    CONTRIBUTED = "contributed"
    PROJECT = "project"
    LOCAL = "local"

@dataclass(frozen=True)
class MemberInfo:
    name: str
    kind: str
    signature: str = ""
    docstring: str = ""
    visibility: str = "public"
    line_number: int = 0

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "MemberInfo": ...

@dataclass(frozen=True)
class UnifiedSymbol:
    id: str
    name: str
    kind: str
    file_path: str
    line_number: int
    language: str
    docstring: str = ""
    signature: str = ""
    members: List[MemberInfo] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def compute_id(cls, space: str, file_path: str, name: str, kind: str, line_number: int) -> str:
        """計算唯一 SHA1 雜湊識別碼"""
        raw = f"{space}:{file_path}:{name}:{kind}:{line_number}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "UnifiedSymbol": ...

@dataclass
class SpaceConfig:
    name: str
    description: str = ""
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    file_patterns: Optional[List[str]] = None
    origin: str = "project"

    def is_file_included(self, filename: str) -> bool:
        """判斷檔案是否匹配 include 規則；file_patterns 未指定或為空時預設全包含 (include all)"""
        if not self.file_patterns:
            return True
        return any(fnmatch.fnmatch(filename, pat) for pat in self.file_patterns)

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, name: str, data: dict, origin: str = "project") -> "SpaceConfig": ...

ThesaurusGroup = List[str]

@dataclass
class ThesaurusConfig:
    groups: List[ThesaurusGroup] = field(default_factory=list)
    origin: str = "project"

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: Any, origin: str = "project") -> "ThesaurusConfig": ...
```

---

### 2.3 空間管理器 (`knowledge_db/space.py`)

```python
class SpaceManager:
    def __init__(self, core_context: Optional[Any] = None, config_dir: Optional[Union[str, Path]] = None, storage_dir: Optional[Union[str, Path]] = None):
        """
        初始化 SpaceManager。
        :param core_context: Core 模組上下文實例 (可選，便於整合與沙盒注入)
        :param config_dir: 覆蓋之組態檔案目錄 (可選，便於測試隔離)
        :param storage_dir: 覆蓋之存儲根目錄 (可選，便於測試隔離)
        """

    def load_spaces(self) -> Dict[str, SpaceConfig]:
        """
        載入並聚合所有來源 (Contributes + Project Config + Local Config) 之空間清單。
        依 Local > Project > Contributed 進行同名空間覆蓋。
        :return: 空間字典 {space_name: SpaceConfig}
        """

    def load_thesaurus(self) -> List[ThesaurusGroup]:
        """
        載入並聚合所有來源之同義詞群組清單。
        :return: 聚合後之同義詞群組列表
        """

    def get_space(self, name: str) -> SpaceConfig:
        """
        取得指定名稱之 SpaceConfig。若不存在則拋出 SpaceNotFoundError。
        """

    def list_spaces(self) -> List[SpaceConfig]:
        """
        回傳當前所有有效 SpaceConfig 清單。
        """

    def get_union_spaces(self) -> List[SpaceConfig]:
        """
        取得所有空間之聯集清單 (全量處理範圍)。
        """

    def resolve_space_include(self, space_name: str) -> List[Path]:
        """
        將空間宣告之 include 語意 URI 清單解算為本機實體絕對路徑清單。
        過濾不存在的路徑並發出 Warning 日誌 (EC-02)。
        """

    def get_space_storage_dir(self, space_name: str) -> Path:
        """
        定位該空間專屬之 VFS 存儲目錄 (storage://knowledge-db/spaces/<space_name>/)。
        若目錄不存在則自動建立。
        """
```

---

### 2.4 指紋掃描器 (`knowledge_db/scanner.py`)

```python
@dataclass(frozen=True)
class FileFingerprint:
    relpath: str
    source_root: str
    mtime: float
    size: int
    sha1: str

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "FileFingerprint": ...

@dataclass
class ScanDiffResult:
    space_name: str
    added: List[FileFingerprint] = field(default_factory=list)
    modified: List[FileFingerprint] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    unchanged: List[FileFingerprint] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

class FingerprintScanner:
    def __init__(self, space_manager: SpaceManager):
        """
        初始化增量指紋掃描器。
        :param space_manager: SpaceManager 實例
        """

    def scan_space(self, space_config: SpaceConfig, force: bool = False) -> ScanDiffResult:
        """
        對單一空間執行雙階增量指紋比對。
        - Stage 1: 比對 mtime 與 size (相同則判定 UNCHANGED)
        - Stage 2: Stage 1 不符時計算 SHA1 (若一致更新 mtime 判定 UNCHANGED；不一致判定 MODIFIED)
        - 新增檔案標記 ADDED；磁碟不存在檔案標記 DELETED
        - 自動原子寫入更新後的指紋庫
        """

    def scan_all_spaces(self, spaces: Optional[List[SpaceConfig]] = None, force: bool = False) -> Dict[str, ScanDiffResult]:
        """
        對所有空間之聯集 (Union Scope) 執行增量掃描，回傳 {space_name: ScanDiffResult}。
        """

    def load_fingerprints(self, space_name: str) -> Dict[str, FileFingerprint]:
        """
        載入指定空間之指紋快取。若檔案損毀則記錄 Warning 並自癒重置為空字典 (EC-03)。
        """

    def save_fingerprints(self, space_name: str, fingerprints: Dict[str, FileFingerprint]) -> None:
        """
        以原子寫入方式 (tempfile + os.replace) 持久化指紋快取至 storage://knowledge-db/spaces/<space_name>/fingerprints.json。
        """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
┌────────────────────────────────────────────────────────┐
│ Level 1: 基礎例外定義 (knowledge_db/exceptions.py)     │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 2: 核心模型與 Schema (knowledge_db/schema.py)    │
│ (Enums, MemberInfo, UnifiedSymbol, SpaceConfig, etc.)   │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 3: 空間管理與聚合 (knowledge_db/space.py)        │
│ (SpaceManager, Dual-Track Aggregation, Priority Merge) │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 4: 雙階增量比對 (knowledge_db/scanner.py)        │
│ (FingerprintScanner, Two-Stage Diff, Atomic Cache)     │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 5: 入口、組態、格式說明與 Manifest               │
│ (manifest.json, contributes.format.md, scripts/cli.py) │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Level 6: 完整單元測試套件 (tests/)                     │
│ (test_schema.py, test_space.py, test_scanner.py)       │
└────────────────────────────────────────────────────────┘
```
