# 專題調研與分析報告：全專案 `sys.path` 與動態模組尋址地毯式盤點及抽離方案 (R01_sys_path_comprehensive_audit.md)

> 調研主題：全專案 `sys.path`、`PYTHONPATH` 與跨模組動態尋址邏輯地毯式盤點與統一抽離方案  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces (`sub_01_core_all_modules_sys_path`)  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - 過去 `core/commands/dispatcher.py:dispatch_local`、`core/events.py:broadcast` 與 `server/worker.py:WarmWorker.pre_warm` 在執行前僅將單一目標模組（`.modules/<target>`）與 `.modules/core` 注入 `sys.path`，未將 `yscb://.modules/` 下所有已安裝模組一併掛載。
  - 此缺口導致各上層業務模組（`file-space`、`ast`、`knowledge-db`、`agents-workflow`、`vscode-support`、`dev`、`server`）為了在冷派發、Hook 觸發、Token Provider 解析或單元測試中成功 `import` 跨模組相依套件，各自在模組頂層、`__init__.py`、`scripts/cli.py` 或 `scripts/hook.*.py` 中撰寫了大量手工拼接 `sys.path` 的防禦性補丁（甚至包含偷偷回退探測 `../source/<dep>` 的越界邏輯）。
  - 當新模組 `gdrive-support` 遵循純淨原則未撰寫手工 `sys.path` 補丁時，執行冷派發指令 `python yscb.py gdrive auth` 即因找不到 `file_space` 而拋出 `ModuleNotFoundError`。
- **調研目標與範疇**：
  - 透過 3 名平行盲眼子代理將全專案（宿主 `yscb.py` + 9 大模組源碼與 `tests/`）劃分為三個正交分區，執行 100% 地毯式盤點。
  - 將所有 `sys.path`、`PYTHONPATH` 與動態載入座標精確分類為：
    1. **類別 A（可徹底拔除之散落補丁，共 13 處生產代碼）**：由 `core` 統一掛載全模組後可 100% 物理刪除。
    2. **類別 B（需收斂至 `core` 單一運行時路徑管理器之核心入口，共 6 處）**：統一收斂為單一 `core` 標準 API。
    3. **類別 C（合法且必須保留之特殊隔離邊界，共 4 類）**：Bootstrap 前置引導、`ProcessPoolExecutor` `spawn` 子進程快照、宿主專案自訂解析器動態載入、以及 `dev test` 沙盒待測模組 `source/<mod>` 隔離。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 類別 A：可徹底拔除之散落 `sys.path` 補丁清單（共 13 處生產代碼 + 1 處冗餘測試）

當 `core` 統一在派發、預熱、Hook 與符號解析前掛載所有 `.modules/<mod>` 後，以下散落於 7 個模組的 `sys.path` 手工補丁（含違反 `.modules/` 剛性邊界之 `source/` 越界探測）可 **100% 物理抽離移除**：

| # | 所屬模組 | 精確檔案與行號座標 | 既有散落邏輯內容 | 危害與抽離處置 |
| :---: | :---: | :--- | :--- | :--- |
| **A-01** | `agents-workflow` | [`compiler.py:L15-L34`](../../../../ys_codebase/source/agents-workflow/agents_workflow/compiler.py#L15-L34) | 手動拼接 `[_mods_root_aw/core, ../source/core, ../.modules/core]` 插入 `sys.path` | 含 `source/core` 越界探測；**徹底移除**，直接 `from core import ...` |
| **A-02** | `agents-workflow` | [`publisher.py:L20-L37`](../../../../ys_codebase/source/agents-workflow/agents_workflow/publisher.py#L20-L37) | 手動拼接 `[_mods_root_aw/core, ../source/core, ../.modules/core]` 插入 `sys.path` | 同上；**徹底移除**，直接 `from core import uri, vfs` |
| **A-03** | `agents-workflow` | [`scripts/hook.core.py:L8-L25`](../../../../ys_codebase/source/agents-workflow/scripts/hook.core.py#L8-L25) | 手動將 `_pkg_root`、`_modules_root` 與 `source/core`、`.modules/core` 插入 `sys.path` | 含 `source/core` 越界探測；**徹底移除** |
| **A-04** | `vscode-support` | [`scripts/cli.py:L16-L20`](../../../../ys_codebase/source/vscode-support/scripts/cli.py#L16-L20) (及 `L57,89,115`) | `_ensure_module_path()` 手動將自身 `module_root` 插入 `sys.path` | **徹底移除** `_ensure_module_path` 定義與 3 處呼叫 |
| **A-05** | `vscode-support` | [`scripts/hook.core.py:L13-L16`](../../../../ys_codebase/source/vscode-support/scripts/hook.core.py#L13-L16) (及 `L21,50`) | `_ensure_module_path()` 手動將自身 `module_root` 插入 `sys.path` | **徹底移除** `_ensure_module_path` 定義與 2 處呼叫 |
| **A-06** | `file-space` | [`scripts/cli.py:L10-L15`](../../../../ys_codebase/source/file-space/scripts/cli.py#L10-L15) (及 `L57,70,169,212,267,321`) | `_ensure_module_path()` 手動將自身 `module_root` 插入 `sys.path` | **徹底移除** `_ensure_module_path` 定義與 6 處呼叫 |
| **A-07** | `ast` | [`ast_engine/__init__.py:L12-L35`](../../../../ys_codebase/source/ast/ast_engine/__init__.py#L12-L35) | `_ensure_dependency_module_paths()` 手動探測 `module://file-space`、`../file-space` (`source/`) 與 `.modules/file-space` | 含 `source/file-space` 越界探測；**徹底移除** |
| **A-08** | `ast` | [`scripts/cli.py:L15-L23`](../../../../ys_codebase/source/ast/scripts/cli.py#L15-L23) (及 `L119,329`) | `_ensure_module_path()` 手動將自身與鄰居 `file-space` 插入 `sys.path` | **徹底移除** `_ensure_module_path` 定義與 2 處呼叫 |
| **A-09** | `ast` | [`scripts/hook.file-space.py:L15-L23`](../../../../ys_codebase/source/ast/scripts/hook.file-space.py#L15-L23) (及 `L32,87`) | `_ensure_module_path()` 手動將自身與鄰居 `file-space` 插入 `sys.path` | **徹底移除** `_ensure_module_path` 定義與 2 處呼叫 |
| **A-10** | `knowledge-db` | [`knowledge_db/__init__.py:L13-L38`](../../../../ys_codebase/source/knowledge-db/knowledge_db/__init__.py#L13-L38) | `_ensure_dependency_module_paths()` 手動探測 `file-space` 與 `ast`（含 `source/` fallback） | 含 `source/` 越界探測；**徹底移除** |
| **A-11** | `knowledge-db` | [`knowledge_db/io_utils.py:L10-L29`](../../../../ys_codebase/source/knowledge-db/knowledge_db/io_utils.py#L10-L29) | `_ensure_ast_path()` 手動拼接 `../ast` 或 `.modules/ast` 插入 `sys.path` | **徹底移除** `_ensure_ast_path` 定義與呼叫 |
| **A-12** | `knowledge-db` | [`knowledge_db/providers.py:L12-L32`](../../../../ys_codebase/source/knowledge-db/knowledge_db/providers.py#L12-L32) | `_ensure_file_space_path()` 手動探測並插入 `file-space` 路徑 | **徹底移除** `_ensure_file_space_path` 定義與呼叫 |
| **A-13** | `dev` | [`dev/checker.py:L1170-L1215`](../../../../ys_codebase/source/dev/dev/checker.py#L1170-L1215) | `Checker._check_custom_rules` 手動解析 `module://<donor_pkg>` 並直接以 `sys.path.insert` / `sys.path[:] = ...` 修改與還原 `sys.path` | **抽離裸 `sys.path` 操作**：改為委派呼叫 `core.platform.ensure_installed_modules_path(priority_module=donor_pkg)` 與 `finally: core.platform.restore_sys_path(orig_sys_path)` |
| **A-14** | `core/tests` | [`tests/test_config.py:L8`](../../../../ys_codebase/source/core/tests/test_config.py#L8) | 頂層 `sys.path.insert(0, "..")` | **移除**歷史殘留之相對路徑注入 |

---

### 2.2 類別 B：需收斂至 `core` 統一運行時路徑管理器之核心入口（共 6 處）

我們應於 `core`（如 `core/platform/venv.py` 或新建/擴充 `ensure_installed_modules_path(yscb_root=None, priority_module=None, extra_roots=None)`）提供單一權威實作，統一收斂以下 6 處核心入口：

| # | 所屬模組 | 精確檔案與行號座標 | 現況問題 | 收斂設計 |
| :---: | :---: | :--- | :--- | :--- |
| **B-01** | `core` | [`core/commands/dispatcher.py:L573-L580`](../../../../ys_codebase/source/core/core/commands/dispatcher.py#L573-L580) | `dispatch_local` 僅注入 `core_dir` 與單一 `mod_root`，導致冷派發跨模組 `import` 失敗 | 改為調用 `ensure_installed_modules_path(yscb_abs, priority_module=module_name)`，一次性掛載 `.modules/*` 全已安裝模組 |
| **B-02** | `core` | [`core/events.py:L84-L88`](../../../../ys_codebase/source/core/core/events.py#L84-L88) | `broadcast` 逐個執行 Hook 時僅注入單一 `hook_root` | 廣播前先調用 `ensure_installed_modules_path()` 掛載全模組；若傳入自訂 `search_roots`（如沙盒測試），僅需將當前 `hook_root` 置頂 |
| **B-03** | `core` | [`core/symbols.py:L115-L179`](../../../../ys_codebase/source/core/core/symbols.py#L115-L179) | `resolve_callable` 軌道 1 前未確保 `.modules/*` 已在 `sys.path`，導致退入軌道 2 手動插 `sys.path` 且含無守衛之 `module.source://` fallback | 進入軌道 1 (`importlib.import_module`) 前先調用 `ensure_installed_modules_path(priority_module=module_name)`；軌道 2 僅在 `YSCB_TEST_SANDBOX=="1"` 時才允許 `module.source://` fallback，防止生產期污染 `source/` |
| **B-04** | `server` | [`server/master.py:L742-L770`](../../../../ys_codebase/source/server/server/master.py#L742-L770) | `_spawn_worker_locked` 組裝 `env["PYTHONPATH"]` 時僅列入 `.modules/core` 與 `.modules/server`，未展開其餘 `.modules/<mod>` | 調用 `core` 標準路徑收集函式（含 `.venv`、所有 `.modules/<mod>`、`project://` / `yscb.host://` 且強制剔除 `/source`）組裝 `PYTHONPATH` |
| **B-05** | `server` | [`server/worker.py:L55-L81`](../../../../ys_codebase/source/server/server/worker.py#L55-L81) | `WarmWorker.pre_warm` 僅將父目錄 `.modules` 插入 `sys.path`，未展開各 `.modules/<mod>` | 改為調用 `ensure_installed_modules_path(self.yscb_root, include_host_roots=True)` 統一完成全模組與宿主根目錄掛載 |
| **B-06** | `server` & `ast` | [`server/service.py:L240-L243`](../../../../ys_codebase/source/server/server/service.py#L240-L243)<br/>[`ast/ast_engine/parsers/registry.py:L123-L163`](../../../../ys_codebase/source/ast/ast_engine/parsers/registry.py#L123-L163) | `ServiceManager._load_service_item` 與 `ParserRegistry._ensure_search_paths` 手動逐個解析 `.modules/<provider>` 插入 `sys.path` | 改由 `ensure_installed_modules_path` 統一確保 `.modules/<provider>` 已在 `sys.path`（`ParserRegistry` 僅保留宿主專案自訂解析器單檔/目錄載入） |

---

### 2.3 類別 C：合法特殊邊界收斂至 `core.platform` 並落實 `dev check` 零豁免靜態守門

經盲眼子代理交叉查證，以下 4 類屬於 Python 運行時或測試沙盒的物理隔離需求，透過將前 3 類模組內操作統一封裝為 `core.platform` 權威原語，可達成 **非 `core` 生產程式碼 0 處直接修改 `sys.path`（`dev check` 零豁免白名單）**：

1. **宿主根目錄與脫離子進程 Bootstrap 前置引導（[`yscb.py:L128-L165`](../../../../yscb.py#L128-L165)、[`server/master.py:L107-L128`](../../../../ys_codebase/source/server/server/master.py#L107-L128)）**：
   - 在 `import core` 或 `import server.master` 發生之前，Python 解譯器尚不知道模組在哪裡，因此根目錄入口腳本 `yscb.py:_activate_runtime_env()` 與 `spawn_detached_master()` 傳給 `python -c` 的引導字串必須先掛載基礎路徑（且 `spawn_detached_master` 的 8 參數 `cmd` 契約受 `test_server.py:L759-L773` 保護，其字串常數亦不構成模組自身對 `sys.path` 的 AST 變動）；一旦進入 `MasterSupervisor._spawn_worker_locked` 與 `WarmWorker.pre_warm`，立即由 `core.platform.build_runtime_pythonpath` 與 `ensure_installed_modules_path` 接管全模組路徑。
2. **`ProcessPoolExecutor` 多進程 `spawn` 快照傳遞（[`ast/ast_engine/bundler.py:L394-L400, L901-L905`](../../../../ys_codebase/source/ast/ast_engine/bundler.py#L394-L400)）**：
   - 在 Windows / macOS 的 `multiprocessing` `spawn` 模式下，Worker 子進程不會繼承父進程執行期動態修改的 `sys.path`；將 `_init_bundle_worker(parent_sys_path)` 內部對 `sys.path` 的補齊收斂為委派呼叫 `core.platform.init_subprocess_sys_path(parent_sys_path)`。
3. **宿主專案自訂解析器動態載入（[`ast/ast_engine/parsers/registry.py:L123-L163, L210-L212`](../../../../ys_codebase/source/ast/ast_engine/parsers/registry.py#L123-L163)）**：
   - `ParserRegistry._ensure_search_paths` 與 `_instantiate_custom_parser` 原本直接操作 `sys.path`，改為委派呼叫 `core.platform.ensure_installed_modules_path(..., include_host_roots=True, extra_paths=...)`。
4. **`dev test` 沙盒待測模組 `source/<mod>` 置頂、還原與單元測試 `tests/test_*.py` 自舉（[`dev/testing/runner.py:L165-L181`](../../../../ys_codebase/source/dev/dev/testing/runner.py#L165-L181)、[`case.py:L86,L137`](../../../../ys_codebase/source/dev/dev/testing/case.py#L86)）**：
   - 將 `TestDiscovery.build_suite_for_module` 掛載單一待測模組 `module.source://<mod>`（同時確保沙盒 `.modules/*` 已在 `sys.path` 並剔除其他 `source/*`）及 `YSCBTestCase.tearDown` 還原 `sys.path` 快照之操作，收斂為 `core.platform.activate_test_module_source_path(src_real, src_root=...)` 與 `core.platform.restore_sys_path(snapshot)`。
   - 各模組 `tests/test_*.py` 為支援單檔直跑而寫的頂層 `_pkg_root` 注入屬於測試檔（`is_test_file == True`），不在生產源碼限制範圍內。

---

## 3. 結論 (Conclusion)

- **核心結論**：
  1. 本次全倉地毯式排查共定位出 **13 處散落於各業務模組生產代碼中的手動 `sys.path` 補丁**（其中 `agents-workflow` 3 處、`ast` 1 處、`knowledge-db` 2 處甚至帶有偷掛 `../source/` 的越界風險）。
  2. 透過在 `core.platform` 建立統一運行時路徑管理 API（`ensure_installed_modules_path`、`build_runtime_pythonpath`、`init_subprocess_sys_path`、`activate_test_module_source_path`、`restore_sys_path`），可將 **13 處散落補丁 100% 物理刪除**，並將其餘跨模組入口與特殊隔離邊界全數收斂至 `core`，達成 **非 `core` 生產代碼 0 處直接修改 `sys.path`**。
  3. 同步於 `dev/checker.py:_check_source_files` 新增針對 `name != "core" and not is_test_file` 的剛性 AST 靜態檢查（`CheckSeverity.FAIL`，零豁免白名單），從工具鏈層級永久封堵業務模組私自注入 `sys.path`。
- **後續建議**：
  - 採納 **出口 ①（立即實作）**：將本調研報告結論直接併入 `sub_01_core_all_modules_sys_path` P01~P04 與 P06 規格書，執行 `/blind-subagent` 規格審查後推進實作。

