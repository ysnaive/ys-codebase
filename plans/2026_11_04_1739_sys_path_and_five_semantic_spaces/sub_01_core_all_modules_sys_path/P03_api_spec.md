# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_01_core_all_modules_sys_path  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `list_installed_module_roots` | `core/platform/venv.py` (`core.platform`) | Public | 掃描並回傳 `<yscb_root>/.modules/` 下所有有效已安裝模組根目錄之正規化絕對路徑清單（按優先序排列） |
| `list_module_search_roots` | `core/platform/venv.py` (`core.platform`) | Public | 回傳 `<yscb_root>` 下所有模組之搜尋根目錄清單（`prefer_source=True` 時優先選用 `source/<mod>`，否則回退至 `.modules/<mod>`，供 IDE `extraPaths` 靜態投影使用） |
| `SettingsProjector._compute_managed_extra_paths` | `vscode-support/vscode_support/projector.py` | Internal | 計算 YSCB 託管之 `python.analysis.extraPaths`（包含 `current-site-packages` 穩定連結與 `list_module_search_roots` 投影之各模組搜尋根目錄） |
| `ensure_installed_modules_path` | `core/platform/venv.py` (`core.platform`) | Public | 確保所有已安裝模組根目錄（及選配之 `extra_paths`、宿主根目錄）按優先序注入 `sys.path` |
| `build_runtime_pythonpath` | `core/platform/venv.py` (`core.platform`) | Public | 組裝包含 `.venv` `site-packages`、全已安裝模組 `.modules/<mod>` 與宿主根目錄（剔除 `/source`）之 `PYTHONPATH` 字串 |
| `init_subprocess_sys_path` | `core/platform/venv.py` (`core.platform`) | Public | 將父進程 `sys.path` 快照補齊至 `multiprocessing` 子進程之 `sys.path` |
| `activate_test_module_source_path` | `core/platform/venv.py` (`core.platform`) | Public | 供 `dev test` 掛載全已安裝模組後，剔除其他 `source/*` 並將受測模組 `src_real` 置於 `sys.path[0]`，回傳原 `sys.path` 快照 |
| `restore_sys_path` | `core/platform/venv.py` (`core.platform`) | Public | 原地還原 `sys.path[:] = list(snapshot)` |
| `Checker._find_sys_path_mutations` | `dev/dev/checker.py` | Internal | AST 靜態掃描非 `core` 生產源碼檔案，攔截任何變動 `sys.path` 之語法節點並回傳違規訊息清單 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# ys_codebase/source/core/core/platform/venv.py (exported in core.platform)
from typing import List, Optional, Sequence

def list_installed_module_roots(
    yscb_root: Optional[str] = None,
    priority_module: Optional[str] = None,
) -> List[str]:
    """
    Scan `<yscb_root>/.modules/` and return normalized absolute paths
    (`os.path.normpath(os.path.abspath(p))`) of all installed module directories.

    Ordering & Filtering Contract:
    1. If `yscb_root` is omitted, resolve via `core.uri.resolve("yscb://")`.
    2. Ignore hidden/temporary entries (`entry.startswith(".")`, e.g. `.staging_*`, `.old_*`)
       and non-directory entries.
    3. Defensively exclude any path whose normalized path contains `/source/` or ends with `/source`.
    4. Priority ordering:
       - `.modules/<priority_module>` first (if `priority_module` is given and exists)
       - `.modules/core` next (if exists and not already first)
       - Remaining `.modules/<mod>` sorted alphabetically by directory name.
    """

def list_module_search_roots(
    yscb_root: Optional[str] = None,
    prefer_source: bool = True,
) -> List[str]:
    """
    Return normalized absolute paths of all YSCB module search roots under `yscb_root`.

    When `prefer_source=True` (used for static IDE analysis projection such as
    VS Code `python.analysis.extraPaths`), `<yscb_root>/source/<mod>` is preferred
    whenever a valid non-hidden module directory exists under `source/`, falling back to
    `<yscb_root>/.modules/<mod>` for installed-only modules. When `prefer_source=False`,
    delegates to `list_installed_module_roots(yscb_root)`.
    Ordering places `core` first (if present), followed by all remaining modules
    sorted alphabetically by module directory name.
    """

def ensure_installed_modules_path(
    yscb_root: Optional[str] = None,
    priority_module: Optional[str] = None,
    include_host_roots: bool = False,
    extra_paths: Optional[Sequence[str]] = None,
) -> List[str]:
    """
    Ensure all installed `.modules/<mod>` roots (plus optional `extra_paths` and
    host roots) are mounted in `sys.path` with deterministic priority.

    Mutation Contract:
    1. Front-priority paths (in exact order, represented via `os.path.normpath(os.path.abspath(p))`
       and deduplicated by `os.path.normcase(os.path.realpath(p))`):
       - Valid existing directories from `extra_paths` (if provided)
       - Active test module source paths in `_ACTIVE_TEST_SOURCE_PATHS` (when inside a
         `dev test` suite execution so tested `source/<mod>` is never demoted behind `.modules/<mod>`)
       - `.modules/<priority_module>` (if `priority_module` is provided and exists)
       - `.modules/core` (if exists)
       If any front-priority path is already present in `sys.path`, it is moved
       to the front preserving this relative order; otherwise inserted at the front.
    2. Remaining `.modules/<mod>` roots from `list_installed_module_roots()`:
       Inserted immediately after the front-priority block if not already present
       in `sys.path`.
    3. If `include_host_roots=True`, resolve `yscb_root`, parent host root (if containing
       `yscb.config.json`), `project://`, and `yscb.host://` (excluding any path containing
       `/source/` or ending with `/source`) and append to `sys.path` if not already present.
    4. Returns the list of newly added or front-promoted paths.
    """

def build_runtime_pythonpath(
    yscb_root: Optional[str] = None,
    priority_module: Optional[str] = None,
    include_host_roots: bool = True,
    existing_pythonpath: Optional[str] = None,
) -> str:
    """
    Build an `os.pathsep`-joined `PYTHONPATH` string for child processes
    (e.g., WarmWorker subprocesses).

    Includes (deduplicated, preserving order, strictly excluding any path containing
    `/source/` or ending with `/source`):
    1. `.venv` site-packages (if present under `<yscb_root>/.venv`)
    2. All installed module roots from `list_installed_module_roots(yscb_root, priority_module)`
    3. `yscb_root`, parent host root (if `yscb.config.json` exists), `project://`, and
       `yscb.host://` roots (when `include_host_roots=True`)
    4. Existing entries from `existing_pythonpath` (filtered to exclude `/source`)
    """

def init_subprocess_sys_path(parent_sys_path: Sequence[str]) -> None:
    """
    Synchronize a child worker process's `sys.path` (e.g. `ProcessPoolExecutor`
    under `spawn` start method) with `parent_sys_path` by inserting missing entries
    at the front while preserving order.
    """

def activate_test_module_source_path(
    src_real: str,
    src_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> List[str]:
    """
    Prepare `sys.path` for `dev test` suite discovery of a single target module:
    1. Capture and return a copy of the original `sys.path` (`orig_sys_path = list(sys.path)`).
    2. Register `src_real` in `_ACTIVE_TEST_SOURCE_PATHS` and call
       `ensure_installed_modules_path(yscb_root=yscb_root)` so all installed
       dependency modules in `.modules/*` are available while `src_real` stays at the front.
    3. If `src_root` is provided, remove any `sys.path` entry whose realpath is
       inside `src_root` (except `src_real`) to prevent cross-module `source/` leakage.
    4. Ensure `src_real` is at `sys.path[0]`.
    """

def restore_sys_path(snapshot: Sequence[str]) -> None:
    """
    Restore `sys.path` in-place from a previously captured snapshot (`sys.path[:] = list(snapshot)`)
    and sync `_ACTIVE_TEST_SOURCE_PATHS` to only entries remaining in `snapshot`.
    """
```

```python
# ys_codebase/source/dev/dev/checker.py
class Checker:
    @staticmethod
    def _find_sys_path_mutations(tree: ast.AST) -> List[Tuple[int, str]]:
        """
        Inspect an AST tree and return `(lineno, description)` for every direct
        mutation of `sys.path`:
        1. Tracks aliases of `sys` (`import sys as s`) and `sys.path` (`from sys import path as p`).
        2. Detects method calls on `sys.path` where attr in
           `{"insert", "append", "extend", "remove", "pop", "clear", "sort", "reverse"}`.
        3. Detects `ast.Assign`, `ast.AnnAssign`, `ast.AugAssign`, and `ast.Delete`
           targeting `sys.path` or any subscript/slice of `sys.path` (e.g. `sys.path[:] = ...`,
           `sys.path[0] = ...`, `del sys.path[0]`, `sys.path += ...`).
        """
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `list_installed_module_roots` / `ensure_installed_modules_path`：當 `yscb_root` 無法解析或 `.modules/` 目錄尚未建立時，優雅回傳空清單 `[]`，不拋出 `FileNotFoundError`。
  - `Checker._check_source_files`：當 `name != "core" and not is_test_file` 的檔案被 `_find_sys_path_mutations(tree)` 檢出違規時，記錄 `CheckSeverity.FAIL`：
    `Forbidden direct sys.path mutation in '{rel_path}:{lineno}' ({detail}). Runtime sys.path management must be delegated to 'core.platform'.`
- **階段決策紀錄**：
  - `[P03:DR-01]` `ensure_installed_modules_path` 支援 `extra_paths` 參數並置於最前端，使 `core/events.py`（自訂 `search_roots`）、`core/symbols.py`（沙盒 `target_dir`）與 `ast/parsers/registry.py`（自訂解析器目錄）皆可透過單一原語完成路徑掛載，無需在各處手寫 `if p not in sys.path: sys.path.insert(0, p)`。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: core/platform/venv.py & core/platform/__init__.py
        (實作並匯出 6 大路徑管理原語)
          │
          ▼
Step 2: core/{commands/dispatcher.py, events.py, symbols.py} & core/tests/{test_config.py, test_platform.py}
        (完成 core 內部三大派發入口收斂與單元測試)
          │
          ▼
Step 3: server/{master.py, worker.py, service.py}
        ast/{ast_engine/__init__.py, bundler.py, parsers/registry.py, scripts/cli.py, scripts/hook.file-space.py}
        file-space/scripts/cli.py
        knowledge-db/{knowledge_db/__init__.py, io_utils.py, providers.py}
        agents-workflow/{compiler.py, publisher.py, scripts/hook.core.py}
        vscode-support/scripts/{cli.py, hook.core.py}
        (拔除業務模組散落補丁並收斂至 core.platform)
          │
          ▼
Step 4: dev/dev/{checker.py, testing/runner.py, testing/case.py} & dev/tests/test_checker.py
        (收斂 dev 內部 sys.path 操作並啟用 Checker 零豁免靜態 AST 守門)
          │
          ▼
Step 5: 熱部署安裝 (@build) 與全倉 9 模組 dev check / dev test 驗收
```

