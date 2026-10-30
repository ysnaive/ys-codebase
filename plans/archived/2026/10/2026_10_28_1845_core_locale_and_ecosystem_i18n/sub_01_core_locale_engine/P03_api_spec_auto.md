# API 與介面規格書 (API & Interface Specification)

> 功能名稱：實作 `core.locale` 多層語系引擎與宣告式 `definition` 契約校驗 (`sub_01_core_locale_engine`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `get_active_chain` | `ys_codebase/source/core/core/locale.py` | Public | 解析當前生效之顯式語系退避鏈（優先順序：顯式參數 > `YSCB_LOCALE` 環境變數 > `config://core` 之 `locale` 設定 > `DEFAULT_LOCALE_CHAIN`） |
| `t` / `translate` | `ys_codebase/source/core/core/locale.py` | Public | 依顯式優先級鏈檢索指定模組與 Key 之語系字串，並執行 `kwargs` 參數替換與跨鍵專有名詞遞迴插值 |
| `resolve_raw` | `ys_codebase/source/core/core/locale.py` | Public | 依顯式優先級鏈查找未格式化的原始模板字串與命中之 `<lang-id>` |
| `get_definition` | `ys_codebase/source/core/core/locale.py` | Public | 讀取並返回指定模組之 `definition.json` 語意契約字典 |
| `validate_module_locales` | `ys_codebase/source/core/core/locale.py` | Public | 驗證指定模組 `locales` 宣告之檔案存在性、`definition` 結構、孤兒鍵與佔位符契約一致性，回傳 `ValidationResult` |
| `clear_cache` | `ys_codebase/source/core/core/locale.py` | Public | 清空 `core.locale` 內部之 `(file_path, mtime)` 語系字典記憶體快取 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from core.validator import ValidationIssue, ValidationResult

DEFAULT_LOCALE_CHAIN: List[str] = ["zh-TW", "zh", "en"]
MAX_INTERPOLATION_DEPTH: int = 5

def parse_locale_chain(raw_chain: Optional[Union[str, List[str]]]) -> List[str]:
    """將逗號分隔字串或字串列表正規化為去重保序之顯式 lang-id 列表（不做連字號自動切分）。"""

def get_active_chain(explicit_chain: Optional[Union[str, List[str]]] = None) -> List[str]:
    """解析當前生效之顯式優先級退避鏈。"""

def extract_placeholders(template_text: str) -> Set[str]:
    """剝除雙花括號轉義 '{{' 與 '}}' 後，提取字串中所有 '{placeholder}' 識別符集合。"""

def get_definition(module: str, base_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """讀取指定模組於 locales.definition 宣告之語意解釋字典。"""

def resolve_raw(
    key: str,
    *,
    module: Optional[str] = None,
    chain: Optional[Union[str, List[str]]] = None,
    base_dir: Optional[str] = None,
) -> Optional[Tuple[str, str, str]]:
    """沿顯式優先級鏈查找 (target_module, matched_lang_id, raw_template)；未命中時回傳 None。"""

def t(
    key: str,
    *,
    module: Optional[str] = None,
    chain: Optional[Union[str, List[str]]] = None,
    default: Optional[str] = None,
    base_dir: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """檢索並執行二階遞迴插值（kwargs 優先 -> 同優先級鏈遞迴解析專有名詞 -> 雙花括號反轉義）。"""

translate = t

def validate_module_locales(
    module_name: str,
    locales_decl: Dict[str, Any],
    base_dir: Optional[str] = None,
) -> ValidationResult:
    """對模組宣告之 locales 映射執行檔案存在性、路徑安全、definition 結構、孤兒鍵與佔位符契約校驗。"""

def clear_cache() -> None:
    """清除語系檔案記憶體快取。"""
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - **執行期容錯 (`t` / `resolve_raw`)**：遵循 `Strict Egress, Tolerant Ingress` 哲學，執行期查找若遇缺失檔案、未命中 Key 或漏傳未知佔位符，絕不拋出未捕獲例外崩潰，而是退回 `default`（若未指定則退回 `key` 本身）並保留未知 `{placeholder}` 字面量；遇循環引用或超過 `MAX_INTERPOLATION_DEPTH` 時自動終止展開 (`EC-01`~`EC-03`)。
  - **靜態檢核期剛性攔截 (`validate_module_locales`)**：缺少 `"definition"`、路徑越界 (`..`)、檔案不存在、JSON 語法損毀、`definition` 缺少非空字串 `"description"`、`<lang-id>` 出現孤兒鍵、或 `<lang-id>` 翻譯字串佔位符集合與 `definition.placeholders` 不一致時，一律記錄 `ValidationIssue(severity="ERROR")` (`FR-05`, `EC-01`, `EC-05`)。
- **階段決策紀錄**：`[P03:DR-01]` `t()` 支援 `"<module>:<key>"` 顯式命名空間前綴（如 `t("knowledge-db:cli.snippet.truncated_hint")`），若未帶 `:` 前綴且未傳入 `module` 參數，則自動透過 `uri.get_module_context() or "core"` 推導目標模組；遞迴插值時若佔位符為 `{other_mod:noun_key}` 支援跨模組查找，若為 `{noun_key}` 則先查當前模組再退回 `"core"` 公共名詞庫。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: ys_codebase/source/core/contributes/_format.json & _manifest.md (Schema 層)
  |
  v
Step 2: ys_codebase/source/core/core/contributes.py (locales.__modules__ 分桶聚合與快照追蹤)
  |
  v
Step 3: ys_codebase/source/core/core/locale.py & core/__init__.py (核心引擎與靜態校驗器)
  |
  v
Step 4: ys_codebase/source/core/core/commands/contributes_cmd.py & dev/dev/checker.py (CLI 與 Dev Check 串聯)
  |
  v
Step 5: ys_codebase/source/core/tests/test_locale.py & dev/tests/test_checker.py (單元與邊界測試)
```

