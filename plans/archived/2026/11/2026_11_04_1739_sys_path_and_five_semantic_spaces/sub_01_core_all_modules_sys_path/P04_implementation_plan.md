# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_01_core_all_modules_sys_path  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書（`P03_api_spec.md`）中有完整一對一介面定義與簽名契約。
- [x] **邊界防護**：EC-01 ~ EC-06（`.staging_*` 過濾、冷派發跨模組匯入、同名 `scripts/cli.py` 優先序、沙盒 `search_roots`、唯讀 `sys.path` 不誤判、IDE 模組與源碼 `extraPaths` 投影及還原）皆有具體防禦與單元測試覆蓋。
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-03 約束，`core.platform.venv` 不引入任何第三方或上層模組依賴，且非 `core` 生產程式碼達成 0 處 `sys.path` 變動。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | [`docs/core/README.md`](../../../../docs/core/README.md)<br/>[`docs/vscode-support/README.md`](../../../../docs/vscode-support/README.md) | Modify | 更新 `core.platform` 統一全模組 `sys.path` 注入原語與 `vscode-support` 自動投影模組 `extraPaths` 說明 |
| **專題手冊** | [`docs/dev/architecture.md`](../../../../docs/dev/architecture.md) | Modify | 補充 `Checker._check_source_files` Step 4 禁止非 `core` 模組變動 `sys.path` 之零豁免靜態 AST 檢核規則 |
| **設計決策** | [`docs/core/DESIGN_NOTES.md`](../../../../docs/core/DESIGN_NOTES.md)<br/>[`docs/dev/DESIGN_NOTES.md`](../../../../docs/dev/DESIGN_NOTES.md)<br/>[`docs/vscode-support/DESIGN_NOTES.md`](../../../../docs/vscode-support/DESIGN_NOTES.md) | Modify | 新增 `DN-18`、`DN-DEV-06` 與更新 `vscode-support` `DN-02`：由 `core.platform` 壟斷全模組 `sys.path` 注入、於 `dev check` 實施零豁免 AST 守門，並將模組/源碼路徑自動投影至 `python.analysis.extraPaths` |
| **微觀註解** | 源碼檔案 Docstrings (`core/platform/venv.py`, `dev/checker.py`) | Modify | 同步更新關鍵介面契約與模組 Docstring |
| **發布日誌** | [`CHANGELOG.md`](../../../../CHANGELOG.md) | Modify | 於母計畫結案或模組版本推進時記錄 `core` 全模組 `sys.path` 統一注入與 `dev check` 靜態守門 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：拔除 `ast_engine/__init__.py` 與 `knowledge_db/__init__.py` 頂層的 `_ensure_dependency_module_paths()` 後，當執行 `python yscb.py dev test ast` 或 `python yscb.py dev test knowledge-db` 時，沙盒內如何找到相依的 `file_space` 或 `ast`？  
> [*] **防護解法**：在 `dev/testing/runner.py:TestDiscovery.build_suite_for_module` 中，透過 `core.platform.activate_test_module_source_path(src_real, src_root=src_root)` 先呼叫 `ensure_installed_modules_path()` 將當前環境（或測試沙盒）`.modules/` 下所有已安裝模組（含 `file-space`、`ast`）掛載進 `sys.path`，再剔除其他模組的 `source/*` 並將受測模組的 `src_real` 置於 `sys.path[0]`。如此一來，待測模組本身走 `source/<mod>` 最新代碼，而其跨模組相依則穩定走 `.modules/<dep>`，完全不需要在各模組 `__init__.py` 手寫路徑補丁。

> [?] **尖銳問題 2**：在 `WarmWorker` 長時間常駐期間，若開發者執行 `python yscb.py dev install <new_mod> --build` 新安裝了一個模組，已預熱的 `WarmWorker` 如何感知新模組路徑？  
> [*] **防護解法**：`WarmWorker.execute_request` 最終仍會透過 `core.commands.dispatcher.dispatch_local` 派發指令（或透過 `events.broadcast` / `symbols.resolve_callable`），而 `dispatch_local` 每次派發都會呼叫 `ensure_installed_modules_path(yscb_abs, priority_module=module_name)`，動態將 `.modules/` 下新增的模組補入 `sys.path` 並將當前目標模組置頂，且在目錄匯入快取上呼叫 `importlib.invalidate_caches()`，確保熱派發同樣能即時載入新安裝模組。

> [?] **尖銳問題 3**：`dev/checker.py` 靜態 AST 檢查若只檢查 `sys.path.insert`，會不會被 `sys.path[:] = ...`、`sys.path.append(...)` 或 `from sys import path; path.insert(...)` 繞過？又會不會誤傷 `'x' in sys.path` 或 `list(sys.path)`？  
> [*] **防護解法**：`_find_sys_path_mutations(tree)` 先收集該檔案內 `import sys [as alias]` 與 `from sys import path [as alias]` 的本地別名集合，再精確匹配：(a) 對 `sys.path` 呼叫 8 種變動方法（`insert`, `append`, `extend`, `remove`, `pop`, `clear`, `sort`, `reverse`）；(b) `Assign` / `AnnAssign` / `AugAssign` / `Delete` 的寫入目標（`targets` / `target`）為 `sys.path` 本身或其 `Subscript`（如 `sys.path[:]`、`sys.path[0]`）。讀取表達式（如 `in sys.path`、`list(sys.path)`、`len(sys.path)`）不在寫入目標或變動方法集合中，因此 0 漏報且 0 誤報。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (`core.platform` 權威路徑原語實作與匯出)**：
   - 修改 [`ys_codebase/source/core/core/platform/venv.py`](../../../../ys_codebase/source/core/core/platform/venv.py) 與 [`ys_codebase/source/core/core/platform/__init__.py`](../../../../ys_codebase/source/core/core/platform/__init__.py)，實作並匯出 `list_installed_module_roots`、`ensure_installed_modules_path`、`build_runtime_pythonpath`、`init_subprocess_sys_path`、`activate_test_module_source_path`、`restore_sys_path`。
2. **TASK-02 (`core` 三大派發入口收斂與 `core` 單元測試)**：
   - 修改 [`dispatcher.py`](../../../../ys_codebase/source/core/core/commands/dispatcher.py)、[`events.py`](../../../../ys_codebase/source/core/core/events.py)、[`symbols.py`](../../../../ys_codebase/source/core/core/symbols.py) 統一接入 `ensure_installed_modules_path`；移除 [`core/tests/test_config.py`](../../../../ys_codebase/source/core/tests/test_config.py) L8 冗餘 `sys.path.insert`；於 [`core/tests/test_platform.py`](../../../../ys_codebase/source/core/tests/test_platform.py) 新增完整單元測試。
3. **TASK-03 (`server`、`ast`、`file-space`、`knowledge-db`、`agents-workflow`、`vscode-support` 散落補丁拔除與委派)**：
   - 依 `R01` 與 `P02` 清單修改 `server/{master.py,worker.py,service.py}`、`ast/{ast_engine/__init__.py,bundler.py,parsers/registry.py,scripts/cli.py,scripts/hook.file-space.py}`、`file-space/scripts/cli.py`、`knowledge-db/{knowledge_db/__init__.py,io_utils.py,providers.py}`、`agents-workflow/{compiler.py,publisher.py,scripts/hook.core.py}`、`vscode-support/scripts/{cli.py,hook.core.py}`。
4. **TASK-04 (`dev` 內部收斂與 `Checker` 零豁免靜態 AST 守門實作)**：
   - 修改 [`dev/dev/testing/runner.py`](../../../../ys_codebase/source/dev/dev/testing/runner.py) 與 [`dev/dev/testing/case.py`](../../../../ys_codebase/source/dev/dev/testing/case.py) 委派至 `core.platform`。
   - 修改 [`dev/dev/checker.py`](../../../../ys_codebase/source/dev/dev/checker.py) 移除 `_check_custom_rules` 手動 `sys.path` 操作，並於 `_check_source_files` 新增 `_find_sys_path_mutations` 靜態檢查（`CheckSeverity.FAIL`）。
   - 於 [`dev/tests/test_checker.py`](../../../../ys_codebase/source/dev/tests/test_checker.py) 新增正反例單元測試。
5. **TASK-05 (全模組 `@build` 熱部署、回歸測試與三層文檔同步)**：
   - 依拓撲順序安裝受影響模組 `@build`，重啟 Server，驗證 `python yscb.py gdrive auth --check --json`（冷派發跨模組載入 `file_space`），並對全倉模組執行 `dev check` 與 `dev test`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確認 `sub_01` 採納零豁免白名單之 `dev check` 靜態 AST 規則：除 `core` 模組及各模組測試檔 (`tests/`) 外，任何模組生產源碼皆禁止直接變動 `sys.path`。
- **[P04:DR-02]** 已完成 `/blind-subagent` 規格審查（[`cf1ce5d0-bd55-48d7-8e2b-8f6a465a3fd2`](conversation://cf1ce5d0-bd55-48d7-8e2b-8f6a465a3fd2)），並將子代理檢出之 3 項 Blocker 與 4 項 Major 邊界防護（`spawn_detached_master` 8 參數 `cmd` 契約相容、`_load_service_item(yscb_root)` 與 `_check_source_files(name)` 參數名修正、`_check_custom_rules` 委派 `restore_sys_path`、`_ACTIVE_TEST_SOURCE_PATHS` 測試釘選與 `sys.modules` 套件名映射、`abspath` 字串保真與 `/source` 過濾、`events.broadcast(search_roots)` 退場還原）100% 納入 `R01`、`P01`~`P04` 規格定稿。

