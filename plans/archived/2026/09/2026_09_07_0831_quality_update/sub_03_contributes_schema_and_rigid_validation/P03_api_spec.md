# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Contributes 宣告架構升級與 Schema 剛性校驗 (Contributes Schema & Rigid Validation)  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ValidationIssue` | `source/core/core/validator.py` | Public | 結構化表達單一校驗錯誤或警告（路徑、訊息、層級、建議修復）。 |
| `ValidationResult` | `source/core/core/validator.py` | Public | 封裝整體校驗結果（`is_valid`, `issues`, `errors`, `warnings`）。 |
| `ContributesValidator` | `source/core/core/validator.py` | Public | 輕量 Schema DSL 驗證引擎（型別解析、通配比對、遞迴檢查、Meta-Check）。 |
| `core.contributes` SDK | `source/core/core/contributes.py` | Public | 提供模組開發者與工具調用之公開 API（`get_format`, `validate`, `list_points`）。 |
| `ContributesCmd` | `source/core/core/commands/contributes_cmd.py` | Internal | CLI 子指令執行入口，負責參數轉發與輸出渲染（`list`, `check`）。 |
| `ContributesCheckPass` | `source/dev/dev/checker.py` | Public | `dev check` 靜態合規檢測 Pass，執行 pre-flight 嚴格校驗。 |
| `Scaffolder` | `source/dev/dev/scaffold.py` | Public | 更新 `create_module`，自動產生包含 `_format.json` 與 `_manifest.md` 的骨架。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 驗證結果與錯誤模型 (`core.validator`)

```python
from typing import List, Dict, Any, Optional, Tuple, NamedTuple

class ValidationIssue(NamedTuple):
    path: str               # JSON 路徑，例如 "commands.cmd.build.tier"
    message: str            # 錯誤原因，例如 "Invalid enum value 'saf'"
    severity: str = "ERROR" # "ERROR" | "WARNING"
    suggestion: Optional[str] = None # 近似拼寫建議，例如 "Did you mean 'safe'?"

class ValidationResult:
    def __init__(self, is_valid: bool, issues: List[ValidationIssue], payload: Optional[Dict[str, Any]] = None):
        self.is_valid: bool = is_valid
        self.issues: List[ValidationIssue] = issues
        self.payload: Optional[Dict[str, Any]] = payload  # 經預設值填補後的 payload
    
    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]
    
    def format_report(self, file_label: str = "") -> str:
        """格式化輸出親和的終端錯誤報告。"""
        ...
```

### 2.2 核心驗證器 (`core.validator.ContributesValidator`)

```python
class ContributesValidator:
    """
    100% Python 標準庫輕量型別 DSL 校驗引擎。
    """
    @classmethod
    def parse_type_signature(cls, sig: str) -> Dict[str, Any]:
        """
        解析 "str!", "enum(a, b)? = a", "bool? = false", "list[str]"
        返回規則字典: {"type": str, "required": bool, "default": Any, "enum": Optional[List[str]], "is_ref": bool}
        """
        ...

    @classmethod
    def validate(
        cls,
        target_mod: str,
        payload: Dict[str, Any],
        donor_mod: str = "",
        format_schema: Optional[Dict[str, Any]] = None,
        strict_points: bool = True
    ) -> ValidationResult:
        """
        校驗 donor_mod 欲注入至 target_mod 之 payload 是否合法。
        - 檢查頂層 key 是否為 target_mod 宣告之擴充點。
        - 遞迴比對欄位結構、型別、必填與列舉。
        - 回填預設值。
        """
        ...

    @classmethod
    def validate_format_schema(cls, format_schema: Dict[str, Any]) -> ValidationResult:
        """
        Meta-Check: 檢查 _format.json 本身語法是否合法。
        - 檢查 _types 定義完整性、無懸空參照。
        - 檢查各擴充點是否具備 description 與合法 format。
        """
        ...
```

### 2.3 核心 SDK 導出 (`core.contributes`)

```python
def get_format(module: str) -> Optional[Dict[str, Any]]:
    """讀取並返回指定模組之 contributes/_format.json 字典，若無則返回 None。"""
    ...

def validate(target_module: str, payload: Dict[str, Any], donor_module: str = "") -> ValidationResult:
    """便捷 SDK: 自動定位 target_module 之 _format.json 並執行校驗。"""
    ...

def list_points(module: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    查詢生態系開放之擴充點清單。
    若指定 module 則僅返回該模組；若為 None 則遍歷所有已安裝模組。
    回傳 [{"module": str, "point": str, "description": str, "format_type": str}, ...]
    """
    ...
```

### 2.4 CLI 子指令處理器 (`core.commands.contributes_cmd`)

```python
def cmd(cmd_bags: Any) -> int:
    """
    contributes 子指令進入點：
    - contributes list [--module=<mod>]
    - contributes check [<target_or_uri>] [--format]
    """
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1] core.validator (基礎 DSL 解析與驗證引擎，完全零依賴)
   │
   ▼
[Step 2] core.contributes (整合 validator、更新 scan_and_inject 排除 _ 特殊檔與過濾、導出 Public SDK)
   │
   ▼
[Step 3] core.commands.contributes_cmd & core/contributes/core.json (註冊 CLI 指令)
   │
   ▼
[Step 4] dev.checker & dev.scaffold (擴充靜態 check 與模組建立骨架)
   │
   ▼
[Step 5] 5 大模組生態落地 (core, server, dev, agents-workflow, knowledge-db 落地 _format.json 與 _manifest.md)
   │
   ▼
[Step 6] 單元測試與回歸驗收 (FT-01 ~ FT-09)
```
