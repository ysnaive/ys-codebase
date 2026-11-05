# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_core_all_modules_sys_path  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Completed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core.platform` 統一運行時路徑與 `PYTHONPATH` 管理原語 | 1. 於 `core/platform/venv.py`（並透過 `core/platform/__init__.py` 公開導出）實作權威路徑管理 API：<br/>   - `list_installed_module_roots(yscb_root: Optional[str] = None, priority_module: Optional[str] = None) -> List[str]`：掃描 `<yscb_root>/.modules/` 下所有非隱藏（不以 `.` 開頭）且為實體目錄的已安裝模組根目錄；回傳路徑字串統一使用 `os.path.normpath(os.path.abspath(p))`（內部去重與比對使用 `os.path.normcase(os.path.realpath(p))`）；排序規則為 `[.modules/<priority_module> (若指定且存在), .modules/core (若存在), ...其餘按模組名稱字典序]`，且防衛性過濾任何含 `/source/` 或以 `/source` 結尾之開發路徑。<br/>   - `ensure_installed_modules_path(yscb_root: Optional[str] = None, priority_module: Optional[str] = None, include_host_roots: bool = False, extra_paths: Optional[Sequence[str]] = None) -> List[str]`：將 `extra_paths`（若提供）、受測模組沙盒釘選路徑 `_ACTIVE_TEST_SOURCE_PATHS`（若正處於 `activate_test_module_source_path` 生命週期內）與 `list_installed_module_roots` 確保注入 `sys.path`；其中 `[extra_paths, _ACTIVE_TEST_SOURCE_PATHS, .modules/<priority_module>, .modules/core]` 強制維持在前端優先序（確保測試期間受測模組 `source/<mod>` 永遠優先於 `.modules/<mod>`），其餘已安裝模組若不在 `sys.path` 則緊隨其後插入（不重複插入）；若 `include_host_roots=True`，額外確保 `yscb_root`、父目錄宿主根、`project://` 與 `yscb.host://`（排除含 `/source` 路徑）存在於 `sys.path` 末端。<br/>   - `build_runtime_pythonpath(yscb_root: Optional[str] = None, priority_module: Optional[str] = None, include_host_roots: bool = True, existing_pythonpath: Optional[str] = None) -> str`：組裝供子進程（如 WarmWorker）使用的 `PYTHONPATH` 字串，包含 `.venv` `site-packages`、`list_installed_module_roots()`、宿主與 `yscb_root` 候選根目錄（當 `include_host_roots=True`）與既有 `existing_pythonpath`，並強制剔除任何含 `/source/` 或以 `/source` 結尾的開發源碼目錄。<br/>   - `init_subprocess_sys_path(parent_sys_path: Sequence[str]) -> None`：供 `multiprocessing` (`spawn` 模式) Worker 初始化時將父進程 `sys.path` 快照中缺失之路徑補入當前子進程 `sys.path`。<br/>   - `activate_test_module_source_path(src_real: str, src_root: Optional[str] = None, yscb_root: Optional[str] = None) -> List[str]` 與 `restore_sys_path(snapshot: Sequence[str]) -> None`：供 `dev test` 測試執行器在掛載全模組 `.modules/*` 後，剔除 `src_root` 下其他模組的 `source/*`、將當前唯一受測模組 `src_real` 釘選於 `_ACTIVE_TEST_SOURCE_PATHS` 並置於 `sys.path[0]`，回傳修改前之 `sys.path` 快照供測試結束後透過 `restore_sys_path` 原地還原 (`sys.path[:] = list(snapshot)`) 並清除釘選。 | P0 | [P00:DR-01]<br/>[P00:DR-04] |
| **FR-02** | 四大核心執行入口與特殊路徑操作全面收斂至 `core.platform` | 1. **CLI 冷派發與 Worker 本地派發** (`core/commands/dispatcher.py:dispatch_local`)：移除手動僅注入 `core_dir` 與單一 `mod_root` 的邏輯，改為調用 `ensure_installed_modules_path(yscb_abs, priority_module=module_name)`。<br/>2. **事件廣播** (`core/events.py:broadcast`)：在迴圈執行 Hook 前先調用 `ensure_installed_modules_path(priority_module="core")`；執行個別 `(mod_name, hook_path, hook_root)` 時，調用 `ensure_installed_modules_path(priority_module=mod_name, extra_paths=[hook_root])`。當 `search_roots is not None`（如測試沙盒生命週期廣播）時，於廣播前快照 `orig_sys_path = list(sys.path)` 並於 `finally` 透過 `restore_sys_path(orig_sys_path)` 還原，防止臨時沙盒路徑殘留於宿主進程。<br/>3. **跨模組符號解析** (`core/symbols.py:resolve_callable`)：進入軌道 1 (`importlib.import_module`) 前先調用 `ensure_installed_modules_path(priority_module=module_name)`；軌道 2 僅在 `os.environ.get("YSCB_TEST_SANDBOX") == "1"` 時才允許回退至 `module.source://`，徹底阻斷生產期誤載 `source/`。<br/>4. **Server 進程與服務載入** (`server/master.py`、`server/worker.py`、`server/service.py`)：`MasterSupervisor._spawn_worker_locked` 統一使用 `build_runtime_pythonpath`（保留 `spawn_detached_master` 既有 8 參數 `cmd` 前置引導契約）；`WarmWorker.pre_warm` 與 `ServiceManager._load_service_item`（使用參數 `yscb_root`）統一使用 `ensure_installed_modules_path`。<br/>5. **AST 與 Dev 測試框架委派** (`ast/ast_engine/bundler.py`、`ast/ast_engine/parsers/registry.py`、`dev/dev/checker.py:_check_custom_rules`、`dev/dev/testing/runner.py`、`dev/dev/testing/case.py`)：全數改為調用 `core.platform` 對應原語，移除直接對 `sys.path` 的增刪改操作；且 `runner.py` 在載入受測模組前以實際 Python 套件名（`ast_engine` 或 `module_name.replace("-", "_")`，絕不誤刪標準庫 `ast`）清除 `sys.modules` 預載快取。 | P0 | [P00:DR-02]<br/>[P00:DR-03]<br/>[P00:DR-04] |
| **FR-03** | 徹底拔除 13 處業務模組散落 `sys.path` 補丁與 1 處冗餘測試注入 | 依據 [`R01_sys_path_comprehensive_audit.md`](./R01_sys_path_comprehensive_audit.md) 類別 A 清單（`A-01` ~ `A-14`），100% 物理刪除散落於 `agents-workflow` (`compiler.py`, `publisher.py`, `scripts/hook.core.py`)、`vscode-support` (`scripts/cli.py`, `scripts/hook.core.py`)、`file-space` (`scripts/cli.py`)、`ast` (`ast_engine/__init__.py`, `scripts/cli.py`, `scripts/hook.file-space.py`)、`knowledge-db` (`knowledge_db/__init__.py`, `io_utils.py`, `providers.py`)、`dev` (`dev/checker.py:_check_custom_rules` 改委派 `ensure_installed_modules_path` + `restore_sys_path`) 及 `core/tests/test_config.py` 中的手動 `sys.path` 補丁與 `../source/` 越界探測。 | P0 | [P00:DR-01]<br/>[P00:DR-02] |
| **FR-04** | `dev check` 新增禁止非 `core` 模組修改 `sys.path` 之剛性靜態 AST 檢查 | 於 `dev/dev/checker.py:Checker._check_source_files(self, name: str, real_dir: str, report: CheckReport)` 中，針對所有 `name != "core" and not is_test_file` 的 Python 源碼檔新增 AST 靜態檢查（**零豁免白名單**）：<br/>1. 追蹤 `import sys`（含別名 `import sys as s`）與 `from sys import path`（含別名 `from sys import path as p`）。<br/>2. 攔截任何針對 `sys.path` 的變動方法呼叫（`insert`, `append`, `extend`, `remove`, `pop`, `clear`, `sort`, `reverse`）、直接賦值或切片/下標賦值（`Assign`, `AnnAssign`, `AugAssign`）以及刪除（`Delete`，如 `del sys.path[0]`）。<br/>3. 違規時發出 `CheckSeverity.FAIL`，訊息明確指出檔案相對路徑、行號，並指引改用 `core.platform` 統一介面。 | P0 | [P00:DR-04] |
| **FR-05** | `vscode-support` 自動投影 YSCB 模組與源碼搜尋路徑至 `python.analysis.extraPaths`（併入 `TODO-22`） | 1. 於 `core/platform/venv.py`（並透過 `core.platform` 匯出）新增 `list_module_search_roots(yscb_root: Optional[str] = None, prefer_source: bool = True) -> List[str]`：當 `prefer_source=True` 時，針對每個模組（`core` 置頂、其餘按模組名稱字典序）優先回傳 `<yscb_root>/source/<mod>`（若存在且為非隱藏目錄），否則回傳 `<yscb_root>/.modules/<mod>`。<br/>2. 於 `vscode_support/projector.py:SettingsProjector._compute_managed_extra_paths` 串接 `list_module_search_roots(self.yscb_dir, prefer_source=True)`，將各模組根目錄轉為相對於 `proj_root` 的 POSIX 相對路徑（如 `./ys_codebase/source/core` 或 `./.yscb/.modules/core`）依序追加於 `./<rel>/current-site-packages` 之後，並記錄於 `_yscb_managed.extraPaths`。<br/>3. 於 `_apply_vscode_settings_merge` 中，當 `new_managed_paths` 包含任何 `/.modules/` 路徑時，動態自 `python.analysis.exclude` 省略 `**/.modules/**`，確保下游專案僅安裝 `.modules/<mod>` 時 Pylance 不會因排除規則忽略模組索引；當全數由 `source/<mod>` 投影或無 `.modules/<mod>` 時則保留 `**/.modules/**` 防止重複索引。<br/>4. `revert_vscode_settings` 依據 `_yscb_managed` 100% 乾淨移除所有投影之模組與源碼 `extraPaths`。 | P0 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `.modules/` 下存在熱部署暫存或備份目錄（如 `.staging_ast_1234`、`.old_ast_1234`）或非目錄檔案 | `list_installed_module_roots` 嚴格過濾 `entry.startswith(".")` 或 `not os.path.isdir(full_path)`，絕不將暫存交換目錄或雜項檔案注入 `sys.path`。 |
| **EC-02** | 冷派發指令（`server_compatible: false`，如 `python yscb.py gdrive auth --check --json`）跨模組引用 `file_space` | `dispatch_local` 執行 `scripts/cli.py` 前已透過 `ensure_installed_modules_path` 掛載 `.modules/file-space` 等全模組，跨模組 `from file_space.manager import FileSpaceManager` 正常解析，不再拋出 `ModuleNotFoundError`。 |
| **EC-03** | 多模組皆有 `scripts/cli.py` 或 `scripts/hook.*.py` 時的頂層套件優先權 | `ensure_installed_modules_path(..., priority_module=module_name)` 將目標模組根目錄 `.modules/<module_name>` 強制置於 `sys.path` 最前端，確保目標模組自身的局部匯入優先於其他模組。 |
| **EC-04** | 單元測試透過 `events.broadcast(..., search_roots=[temp_dir])` 測試未安裝在 `.modules/` 的臨時 Hook | `events.broadcast` 將當前 Hook 的 `hook_root` 作為 `extra_paths=[hook_root]` 傳入 `ensure_installed_modules_path`，確保臨時沙盒目錄位於 `sys.path[0]`，同時底層 `.modules/*` 仍可作為相依基底被匯入。 |
| **EC-05** | 業務模組僅「唯讀」存取 `sys.path`（例如 `'foo' in sys.path`、`list(sys.path)` 或傳遞 `list(sys.path)` 給 `init_subprocess_sys_path`） | `dev/checker.py` 的 AST 規則僅攔截「變動 (Mutation)」操作（變動方法呼叫、賦值、切片賦值、`del`），唯讀讀取或切片複製不觸發誤報。 |
| **EC-06** | 母倉同時存在 `source/<mod>` 與 `.modules/<mod>`，或下游專案僅存在 `.modules/<mod>` 與部分自訂 `source/<custom>` | `list_module_search_roots(..., prefer_source=True)` 對同名模組優先選用 `source/<mod>`（避免同模組雙重路徑注入），對僅安裝於 `.modules/` 之模組選用 `.modules/<mod>`，且在 `revert_vscode_settings` 時連同使用者自訂 `extraPaths` 差集精準還原。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 執行邊界純淨度 | 生產環境（非 `YSCB_TEST_SANDBOX=="1"`）下，`sys.path` 與 `PYTHONPATH` 內包含 `<yscb_root>/source/` 的路徑數必須為 `0`。 |
| **NFR-02** | 職責單一性 (SSOT) | 全專案 8 個非 `core` 模組之非測試 `.py` 源碼檔中，直接變動 `sys.path` 的出現次數必須為 `0`，且全數通過 `python yscb.py dev check <mod>`。 |
| **NFR-03** | 效能開銷 | `ensure_installed_modules_path` 單次掃描 `.modules/`（約 9 個子目錄）並在記憶體內去重重排 `sys.path`，耗時 $< 0.5\text{ ms}$，對 CLI 冷熱派發零可感知延遲。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 禁止生產環境回退載入 `source/`**：過去 `agents-workflow`、`ast`、`knowledge-db` 與 `core/symbols.py` 為圖方便在找不到模組時回退探測 `../source/<mod>`，導致開發者修改 `source/` 卻未執行 `dev install --build` 時出現半新半舊的幽靈狀態。本次重構必須徹底斬斷所有生產期 `source/` fallback（`core/symbols.py` 軌道 2 僅限 `YSCB_TEST_SANDBOX == "1"` 時才允許回退 `module.source://`）。
- **`[!IMPORTANT]` `dev test` 拔除模組內 `_ensure_dependency_module_paths` 後的沙盒相依載入**：當我們刪除 `ast_engine/__init__.py` 與 `knowledge_db/__init__.py` 頂層的 `_ensure_dependency_module_paths()` 後，在執行 `dev test ast` 或 `dev test knowledge-db` 時，`dev/testing/runner.py:TestDiscovery.build_suite_for_module` 必須透過 `activate_test_module_source_path` 先確保沙盒 `.modules/*`（含 `file-space`、`ast`）已掛載至 `sys.path`，再將受測模組的 `source/<mod>` 置於 `sys.path[0]`。

