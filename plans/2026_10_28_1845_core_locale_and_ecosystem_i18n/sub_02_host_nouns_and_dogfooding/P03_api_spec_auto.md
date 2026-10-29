# API 與介面規格書 (API & Interface Specification)

> 功能名稱：跨平台宿主環境專有名詞庫、多平台並發自動嗅探與首輪 Dogfooding 實機驗證 (`sub_02_host_nouns_and_dogfooding`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `detect_active_host_dialect` | `ys_codebase/source/core/core/locale.py` | Public | 從當前進程環境變數嗅探呼叫端 AI IDE / CLI 平台並回傳對應 `nouns-<host>` |
| `_get_all_registered_locale_modules` | `ys_codebase/source/core/core/locale.py` | Internal | 回傳全系統已宣告 `locales` 之模組有序清單（供無前綴穿透查找使用） |
| `resolve_raw` | `ys_codebase/source/core/core/locale.py` | Public | 支援帶 `<module>:` 前綴或無前綴（Caller-First + Global Lookup）之多層退避查找 |
| `ArtifactCompiler.resolve_stage2_uri` | `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Public | 執行 Stage 2 URI 相對路徑轉譯與 `__%{key}__` 宿主專有名詞目標平台展開 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# === ys_codebase/source/core/core/locale.py ===
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

def detect_active_host_dialect(
    env: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """
    Sniff the caller AI IDE / Agent environment variables and return the corresponding
    proper-noun dialect ID ('nouns-claude', 'nouns-codex', 'nouns-antigravity'),
    or None if running in a standard human terminal.
    """
    ...

def _get_all_registered_locale_modules(
    primary_module: str,
) -> List[str]:
    """
    Build the deterministic module search order for unqualified locale keys:
    [primary_module, 'agents-workflow', 'core', ...other registered modules sorted].
    """
    ...

def resolve_raw(
    key: str,
    *,
    module: Optional[str] = None,
    chain: Optional[Union[str, List[str]]] = None,
    base_dir: Optional[str] = None,
) -> Optional[Tuple[str, str, str]]:
    """
    Search for `key` strictly along the active explicit fallback chain.
    If `key` has no explicit '<module>:' prefix and `base_dir` is None, searches the
    caller module first and then falls back across `_get_all_registered_locale_modules`.
    """
    ...


# === ys_codebase/source/agents-workflow/agents_workflow/compiler.py ===
class ArtifactCompiler:
    def resolve_stage2_uri(
        self,
        content: str,
        current_dst_path: str,
        deployment_map: Dict[str, str],
        project_root: Optional[str] = None,
        target_name: Optional[str] = None,
    ) -> str:
        """
        Stage 2: Resolve `__#{...}__`, `__${...}__`, and `__%{key}__` proper-noun tags.
        When `target_name` is provided (e.g. 'antigravity', 'claude', 'codex'),
        resolves `__%{key}__` using chain `['nouns-' + target_name, *get_active_chain()]`.
        """
        ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `detect_active_host_dialect`：純環境變數鍵值讀取，絕不拋出例外；無匹配時回傳 `None`。
  - `ArtifactCompiler.resolve_stage2_uri`：遇無法解析之 `__%{unknown}__` 標籤時，向 `sys.stderr` 輸出 `[compiler:warning] Unresolved locale noun tag: 'unknown' in '<doc>'` 並保留原標籤文字（`[EC-02]`）。
- **階段決策紀錄**：`[P03:DR-01]` 當 `YSCB_LOCALE` 環境變數顯式指定時（例如測試或使用者強制指定 `YSCB_LOCALE="zh"`），`get_active_chain()` 尊重 `YSCB_LOCALE` 的顯式設定，不強制插入環境嗅探的 `nouns-<host>`；唯有在常規未指定 `explicit_chain` 與 `YSCB_LOCALE` 時，才由 `detect_active_host_dialect()` 自動前置 `nouns-<host>`，確保測試隔離性與顯式覆寫優先權！

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: core/locale.py (detect_active_host_dialect + unqualified global lookup in resolve_raw)
  └──> Step 2: agents-workflow/locales/*.json & contributes/core.json (agent_tool.* dictionary)
         └──> Step 3: agents-workflow/compiler.py & publisher.py (__%{key}__ Stage 2 expansion)
                └──> Step 4: knowledge-db/locales/*.json, cli.py & SKILL.md Dogfooding
                       └──> Step 5: Unit/Integration tests across core, agents-workflow, knowledge-db
```

