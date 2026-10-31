# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_01_core_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `get_yscb_dir` / `resolve` / `reconcile_undefined_uri` | `ys_codebase/source/core/core/uri.py` | Public | 提供 `.yscb_root` 根目錄定位、URI 語法解析與未定義 URI 探測調解（移除 15 個 VFS I/O 轉發與舊別名）。 |
| `AtomicEngine.transaction_lock` / `_extract_zip_safely` | `ys_codebase/source/core/core/engine.py` | Public / Internal | 提供具 `try...finally` 保證之交易鎖 Context Manager、安全 Zip 解壓與模組原子部署。 |
| `ensure_yscb_gitignore` | `ys_codebase/source/core/core/pip_manager.py` | Public | 單點維護 `.yscb_root/.gitignore` 5 條標準忽略規則合併。 |
| `Installer` | `ys_codebase/source/core/core/installer.py` | Public | 模組安裝、更新、列表、重載與快照還原編排器。 |
| `validate_module_locales` | `ys_codebase/source/core/core/locale.py` | Public | 三階段模組語系契約、孤兒鍵與佔位符一致性檢驗。 |
| `validate_node` / `parse_type_signature` | `ys_codebase/source/core/core/validator.py` | Public | 基於 `_KIND_VALIDATORS` 分派表之宣告式型別遞迴驗證器。 |
| `ContributesAggregator.scan_and_inject` | `ys_codebase/source/core/core/contributes.py` | Public | 跨模組 `contributes/*.json` 四階段掃描、校驗與快取聚合（移除冗餘 `clean` 參數）。 |
| `dispatch` / `dispatch_local` | `ys_codebase/source/core/core/commands/dispatcher.py` | Public | CLI 命令路由解析、環境掛載與常駐 Server / 本地進程派發。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# === ys_codebase/source/core/core/uri.py ===
def get_yscb_dir() -> Optional[str]: ...
def _normalize_and_split_uri(uri_str: str) -> Tuple[str, str, str]: ...
def _dispatch_scheme_resolution(
    scheme: str, authority: str, path_part: str, raw_uri: str, ctx_mod: Optional[str]
) -> str: ...
def _expand_anchors_and_enforce_sandbox(
    resolved_path: str, scheme: str, authority: str, raw_uri: str
) -> str: ...
def resolve(uri_str: str) -> str: ...

def _discover_undefined_uri_candidates(
    filename: str, search_root: str
) -> List[str]: ...
def _prompt_uri_reconciliation_choice(
    uri_key: str, mod_name: str, rel_candidates: List[str]
) -> Optional[str]: ...
def _persist_reconciled_uri_to_config(
    config_file: str, uri_key: str, chosen_uri: str
) -> bool: ...
def reconcile_undefined_uri(
    mod_name: str, uri_key: str, default_rel_path: Optional[str] = None
) -> Optional[str]: ...

# === ys_codebase/source/core/core/engine.py ===
def _parse_dependencies(deps_raw: Any) -> Dict[str, str]: ...
def _deep_infill_dict(
    target: Dict[str, Any], template: Dict[str, Any]
) -> Tuple[Dict[str, Any], bool]: ...
def _force_rmtree_with_retry(target_path: str, max_retries: int = 5) -> None: ...
def _cleanup_stale_swap_dirs(parent_dir: str, mod_name: str) -> None: ...
def _atomic_swap_dir(staging_dir: str, target_dir: str, mod_name: str) -> None: ...
def _clean_module_cache(mod_name: str) -> None: ...
def _extract_zip_safely(zip_path: str, dest_dir: str) -> None: ...

class AtomicEngine:
    @contextmanager
    def transaction_lock(
        self, target_name: str, operation: str = "unknown"
    ) -> Iterator[bool]: ...
    def _seed_or_infill_module_config(
        self, mod_name: str, staging_dir: str, host_cfg_dir: str
    ) -> None: ...
    def _apply_yscbignore_and_strip_templates(self, staging_dir: str) -> None: ...
    def _deploy_and_strip_single_module_config(
        self, mod_name: str, staging_dir: str
    ) -> None: ...

# === ys_codebase/source/core/core/pip_manager.py ===
def ensure_yscb_gitignore(yscb_root: Optional[str] = None) -> None: ...

# === ys_codebase/source/core/core/locale.py ===
def _validate_locales_decl_header(
    module_name: str, locales_decl: Any, module_root: str
) -> Tuple[Optional[str], Dict[str, str], List[str]]: ...
def _load_and_validate_definition_contract(
    module_name: str, def_abs_path: str
) -> Tuple[Optional[Dict[str, Set[str]]], List[str]]: ...
def _validate_single_lang_file(
    module_name: str,
    lang_id: str,
    lang_abs_path: str,
    def_placeholders: Dict[str, Set[str]],
) -> List[str]: ...
def validate_module_locales(
    module_name: str, locales_decl: Dict[str, Any], module_root: str
) -> List[str]: ...

# === ys_codebase/source/core/core/validator.py ===
def _validate_dict_shape_node(
    data: Any, node_spec: Dict[str, Any], path: str
) -> List[str]: ...
def _validate_list_node(
    data: Any, node_spec: Dict[str, Any], path: str
) -> List[str]: ...
def _validate_tuple_node(
    data: Any, node_spec: Dict[str, Any], path: str
) -> List[str]: ...
def _validate_union_node(
    data: Any, node_spec: Dict[str, Any], path: str
) -> List[str]: ...
def _validate_literal_node(
    data: Any, node_spec: Dict[str, Any], path: str
) -> List[str]: ...
def _validate_scalar_node(
    data: Any, node_spec: Dict[str, Any], path: str
) -> List[str]: ...
def validate_node(
    data: Any, node_spec: Dict[str, Any], path: str = "root"
) -> List[str]: ...

# === ys_codebase/source/core/core/contributes.py ===
def _deep_merge(target: Any, source: Any) -> Any: ...

class ContributesAggregator:
    def scan_and_inject(self) -> Dict[str, Any]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `_extract_zip_safely`：當壓縮包成員目標路徑脫離 `dest_dir` 時，強制拋出 `ValueError("Security Error: Zip-Slip detected ...")` (`EC-02`)。
  - `AtomicEngine.transaction_lock`：若無法取得鎖（`act_lock` 回傳 `False`），yield `False` 且不誤刪既有他進程之鎖檔；若成功取得鎖（`True`），於離開 `with` 區塊時在 `finally` 內保證執行 `act_unlock(target_name)` (`EC-01`)。
  - `uri.<io>` / `Config` / `emit` / `translate` / `get_execution_context`：物理刪除後對此類廢棄符號之屬性存取將直接觸發標準 `AttributeError` (`FR-01`, `FR-03`)。
- **階段決策紀錄**：`[P03:DR-01]` 移除 `ContributesAggregator.scan_and_inject(self)` 未使用之 `clean: bool = False` 參數 (`M-11`)，並統一 `core` 內部所有調用端為無參數呼叫 `scan_and_inject()`。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1 (底層核心與單向依賴確立):
  uri.py (移除 VFS 轉發與舊別名、公開 get_yscb_dir、拆解 resolve/reconcile)
    └──> vfs.py / symbols.py / exceptions.py

Step 2 (基礎組態、事件、語系與驗證服務重構):
  config.py (移除 Config 別名、改用 uri.get_yscb_dir)
  events.py (移除 emit 別名、uri.<io> -> vfs.<io>)
  telemetry.py / update_checker.py (改用 uri.get_yscb_dir、uri.<io> -> vfs.<io>)
  locale.py (移除死快取與 translate 別名、三階段拆解 validate_module_locales、uri.<io> -> vfs.<io>)
  validator.py (_KIND_VALIDATORS 分派表拆解 validate_node)

Step 3 (貢獻點與引擎/安裝器生命週期重構):
  pip_manager.py (公開 ensure_yscb_gitignore、改用 uri.get_yscb_dir)
  ide_projector.py (三階段拆解 sync_vscode_settings、改用 uri.get_yscb_dir)
  contributes.py (移除 clean 參數、四階段拆解 scan_and_inject、剝離 _deep_merge、uri.<io> -> vfs.<io>)
  engine.py (修復 core locale 初始化並刪除 2 死方法、新增 transaction_lock、剝離 7 無狀態函式與階段拆解、uri.<io> -> vfs.<io>)
  installer.py (套用 transaction_lock、共用 _extract_zip_safely 與 ensure_yscb_gitignore、階段拆解、uri.<io> -> vfs.<io>)

Step 4 (CLI 路由、命令入口與測試同步):
  commands/contributes_cmd.py (刪除 cmd()、抽取 _append_locale_validation_errors、uri.<io> -> vfs.<io>)
  commands/dispatcher.py (刪除 cmd_* fallback、抽取共用路由與 Server 喚醒 helper)
  scripts/cli.py (刪除 bootstrap 與底部 12 個 cmd_* 轉發、提取 _render_subcommand_group_help)
  core/__init__.py (補齊 TYPE_CHECKING 宣告)
  tests/*.py (同步遷移所有測試調用點至正統 API)
```
