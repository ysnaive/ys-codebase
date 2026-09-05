# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_01_universal_ast_and_contributed_tree_sitter  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `UnifiedSymbol` | `knowledge_db/schema.py` | Public | 階層化 Universal AST 符號模型 (支援 parent_id/children, FQN, Search Payload) |
| `LanguageConfig` | `knowledge_db/schema.py` | Public | 語言擴充配置資料模型 (對齊 contributes.knowledge_db 結構) |
| `BaseParser` | `knowledge_db/parsers/base.py` | Public | 所有 AST 解析驅動器之抽象基類契約 |
| `LanguageRegistry` | `knowledge_db/parsers/registry.py` | Public | 語言外掛發現器與動態分發註冊表 |
| `TreeSitterDriver` | `knowledge_db/parsers/treesitter.py` | Public | 基於 Tree-sitter 與 S-Expression 的通用宣告式解析器 |
| `SpiceNetlistParser` | `knowledge_db/parsers/spice.py` | Internal | 特化 DSL 之 Custom Parser 範例實作 (相容硬體網表) |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

@dataclass(frozen=True)
class UnifiedSymbol:
    """通用階層化代碼與文檔符號模型 (一等公民符號節點)"""
    id: str
    name: str
    kind: str
    file_path: str
    line_number: int
    end_line: int
    language: str
    fqn: str = ""                                     # 全限定名 (如 pkg.module.Class.method)
    scope_path: str = ""                              # 符號作用域路徑
    parent_id: Optional[str] = None                   # 父節點 ID (None 代表頂層符號)
    children: Tuple["UnifiedSymbol", ...] = ()        # 遞迴子符號元組
    docstring: str = ""
    signature: str = ""                               # 完整簽名表示
    parameters: Tuple[Dict[str, Any], ...] = ()       # 結構化參數 [{"name": "x", "type": "int", "default": None}]
    return_type: str = ""                             # 回傳型別註解
    search_payload: str = ""                          # 專供 BM25 與向量檢索消費之精煉語意區塊
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def members(self) -> List[Any]:
        """向後相容：動態映射 children 為 members"""
        return list(self.children)

    def to_dict(self) -> Dict[str, Any]:
        """無損序列化為字典結構"""
        ...

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedSymbol":
        """自字典反序列化"""
        ...


@dataclass
class LanguageConfig:
    """YSCB contributes.knowledge_db 語言宣告規格"""
    id: str
    name: str
    extensions: List[str]
    mode: str = "tree_sitter"                         # "tree_sitter" | "custom"
    grammar: Optional[str] = None                     # tree_sitter_python 等模組名稱
    query_file: Optional[str] = None                  # 語意 URI (如 module://.../queries/python.scm)
    parser_entry: Optional[str] = None                # 自訂 parser 進入點 (module:path:Class)
    custom_kinds: List[Dict[str, str]] = field(default_factory=list)


class BaseParser:
    """AST 解析器抽象基礎類別"""
    def parse_file(self, file_path: str, content: Optional[str] = None) -> List[UnifiedSymbol]:
        """解析指定路徑之原始檔案並產出 UnifiedSymbol 清單"""
        ...

    def parse_content(self, content: str, file_path: str = "") -> List[UnifiedSymbol]:
        """直接解析文字內容"""
        ...


class LanguageRegistry:
    """動態外掛語言註冊表 (管理 contributes 發現與分發)"""
    def __init__(self):
        self._languages: Dict[str, LanguageConfig] = {}
        self._ext_map: Dict[str, LanguageConfig] = {}
        self._parser_cache: Dict[str, BaseParser] = {}

    def register_language(self, config: LanguageConfig) -> None:
        """手動或動態註冊單一語言配置"""
        ...

    def discover_contributed_languages(self, search_roots: Optional[List[str]] = None) -> int:
        """從全生態系模組 contributes.knowledge_db 探索並註冊語言"""
        ...

    def resolve_parser(self, file_path: str) -> Optional[BaseParser]:
        """依檔案路徑或副檔名解析並回傳對應之 Parser 執行實例"""
        ...


class TreeSitterDriver(BaseParser):
    """Tree-sitter S-Expression 通用查詢驅動器"""
    def __init__(self, config: LanguageConfig):
        self.config = config
        ...

    def parse_file(self, file_path: str, content: Optional[str] = None) -> List[UnifiedSymbol]:
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[1. pip_dependencies 宣告] ➔ (tree-sitter, tree-sitter-languages 或專屬 grammars)
           │
           ▼
[2. schema.py] ➔ UnifiedSymbol (遞迴階層、FQN、parameters、search_payload)
           │
           ▼
[3. base.py] ➔ BaseParser 抽象基類
           │
           ▼
[4. S-Expression 規則資產] ➔ queries/*.scm (python, cpp, js, ts, csharp, markdown)
           │
           ▼
[5. treesitter.py] ➔ TreeSitterDriver 實作 (解析 CST ➔ SCM 走訪 ➔ 建立 UnifiedSymbol 樹)
           │
           ▼
[6. registry.py] ➔ LanguageRegistry (contributes 動態發現與副檔名分發)
           │
           ▼
[7. contributes/knowledge-db.json] ➔ 自身宣告內建語言能力 (Zero-Privilege Dogfooding)
           │
           ▼
[8. 舊手刻 parsers 與過時測試清理] ➔ 刪除舊 regex parsers，重構/精煉測試套件
```
