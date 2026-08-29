# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge-db 模組 SPICE 網表語系解譯器 (SpiceParser) 整合  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `LanguageType.SPICE` | `knowledge_db/schema.py` | Public | SPICE 語言類型列舉值 (`"spice"`) |
| `SpiceParser` | `knowledge_db/parsers/spice_parser.py` | Public | SPICE 雙階段多方言符號解析器 |
| `LogicalLine` | `knowledge_db/parsers/spice_parser.py` | Internal | 預處理邏輯行資料容器 (含原始行號區間與 Docstring) |
| `ParserRegistry` (擴充) | `knowledge_db/parsers/registry.py` | Public | 預設註冊 `SpiceParser` (優先級 100) |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# === 1. schema.py 擴充 ===
class LanguageType(str, Enum):
    PYTHON = "python"
    MARKDOWN = "markdown"
    CPP = "cpp"
    CSHARP = "csharp"
    SPICE = "spice"       # [NEW]
    JSON = "json"
    TEXT = "text"
    UNKNOWN = "unknown"


# === 2. spice_parser.py 介面契約 ===
@dataclass
class LogicalLine:
    """SPICE 預處理後之邏輯行模型"""
    raw_text: str          # 原始合併後文字
    clean_text: str        # 剝離註解與首尾空白之純淨文字
    start_line: int        # 原始起始行號 (1-indexed)
    end_line: int          # 原始結束行號 (含接續行)
    docstring: str = ""    # 前置連續 '*' 註解


class SpiceParser(BaseParser):
    """
    SPICE 網表語意解析器 (支援 .cir, .sp, .spice, .net, .cdl)
    """
    SUPPORTED_EXTENSIONS = {".cir", ".sp", ".spice", ".net", ".cdl"}

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        """
        判斷檔案副檔名是否為支援之 SPICE 網表類型 (大小寫不敏感)。
        """
        ...

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """
        執行雙階段 SPICE 語意解析：
        Stage 1: 呼叫 _aggregate_logical_lines(content)
        Stage 2: 呼叫 _parse_state_machine(logical_lines, file_path, space)
        回傳提取之 UnifiedSymbol 清單。
        """
        ...

    def _aggregate_logical_lines(self, content: str) -> List[LogicalLine]:
        """
        Stage 1: 合併 '+' 接續行、剝離 ';' / '$' 行尾註解、萃取前置 '*' 註解為 Docstring。
        """
        ...

    def _parse_state_machine(
        self, logical_lines: List[LogicalLine], file_path: str, space: str
    ) -> List[UnifiedSymbol]:
        """
        Stage 2: 階層狀態機解析，處理 .subckt, .model, .param, .include, .lib, .global 及 X/M 實例。
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Schema 基礎模型擴充]
  └── knowledge_db/schema.py (新增 LanguageType.SPICE)
         │
         ▼
[Step 2: SpiceParser 核心解析引擎實作]
  └── knowledge_db/parsers/spice_parser.py
      ├── LogicalLine 聚合容器
      ├── _aggregate_logical_lines (Stage 1)
      └── _parse_state_machine (Stage 2)
         │
         ▼
[Step 3: 導出與動態註冊整合]
  ├── knowledge_db/parsers/__init__.py (導出 SpiceParser)
  └── knowledge_db/parsers/registry.py (ParserRegistry 註冊)
         │
         ▼
[Step 4: 單元測試與邊界回歸測試]
  └── tests/test_spice_parser.py (FT-01~05, ET-01~04, RT-01)
```
