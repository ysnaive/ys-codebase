# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_01_core_all_modules_sys_path  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`core.platform` 統一運行時全模組路徑管理原語**：於 `core/platform/venv.py`（並透過 `core.platform` 頂層匯出）實作 `list_installed_module_roots`、`ensure_installed_modules_path`、`build_runtime_pythonpath`、`init_subprocess_sys_path`、`activate_test_module_source_path` 與 `restore_sys_path` 六大權威原語，自動掃描 `yscb://.modules/<mod>` 下所有非隱藏已安裝模組根目錄（排除 `.staging_*` / `.old_*` 與 `/source` 路徑），並按 `[extra_paths, _ACTIVE_TEST_SOURCE_PATHS, .modules/<priority_module>, .modules/core, ...其餘字母序]` 確定性注入 `sys.path`。
  2. **四大執行入口與特殊路徑操作全面收斂**：將 `core/commands/dispatcher.py:dispatch_local`、`core/events.py:broadcast`、`core/symbols.py:resolve_callable`、`server/master.py:_spawn_worker_locked`、`server/worker.py:WarmWorker.pre_warm`、`server/service.py:_load_service_item`、`ast/ast_engine/bundler.py:_init_bundle_worker`、`ast/ast_engine/parsers/registry.py`、`dev/dev/testing/runner.py` 與 `dev/dev/testing/case.py` 全面收斂至 `core.platform` 原語，徹底解決冷派發（如 `python yscb.py gdrive auth`）跨模組匯入 `file_space` 失敗之問題。
  3. **拔除 13 處業務模組散落 `sys.path` 補丁並新增 `dev check` 零豁免 AST 靜態守門**：100% 物理刪除散落於 `agents-workflow`、`vscode-support`、`file-space`、`ast`、`knowledge-db`、`dev/checker.py` 中的手動 `sys.path` 補丁與 `../source/` 越界探測，並於 `dev/checker.py:_check_source_files` 新增 `_find_sys_path_mutations` 靜態 AST 檢查（非 `core` 生產代碼直接變動 `sys.path` 一律 `CheckSeverity.FAIL`，零模組豁免白名單）。
  4. **併入 `[TODO-22]` 完成 IDE 靜態 `python.analysis.extraPaths` 對偶投影**：於 `core.platform` 新增 `list_module_search_roots(yscb_root, prefer_source=True)`，並讓 `vscode-support` 之 `SettingsProjector._compute_managed_extra_paths` 自動將全模組搜尋根路徑（優先投影 `source/<mod>`，否則投影 `.modules/<mod>`）寫入 `.vscode/settings.json` 之 `python.analysis.extraPaths`，動態控制 `**/.modules/**` 排除規則並支援 `revert` 100% 乾淨還原。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| [`ys_codebase/source/core/core/platform/venv.py`](../../../../ys_codebase/source/core/core/platform/venv.py) | Modify | 新增 `list_installed_module_roots`、`ensure_installed_modules_path`、`build_runtime_pythonpath`、`init_subprocess_sys_path`、`activate_test_module_source_path`、`restore_sys_path` |
| [`ys_codebase/source/core/core/platform/__init__.py`](../../../../ys_codebase/source/core/core/platform/__init__.py) | Modify | 公開匯出 6 大 `core.platform` 運行時路徑管理原語 |
| [`ys_codebase/source/core/core/commands/dispatcher.py`](../../../../ys_codebase/source/core/core/commands/dispatcher.py) | Modify | `dispatch_local` 統一調用 `ensure_installed_modules_path` 掛載全模組 |
| [`ys_codebase/source/core/core/events.py`](../../../../ys_codebase/source/core/core/events.py) | Modify | `broadcast` 統一調用 `ensure_installed_modules_path`，並在 `search_roots is not None` 時於 `finally` 調用 `restore_sys_path` |
| [`ys_codebase/source/core/core/symbols.py`](../../../../ys_codebase/source/core/core/symbols.py) | Modify | `resolve_callable` 進入軌道 1 前調用 `ensure_installed_modules_path`；軌道 2 僅在 `YSCB_TEST_SANDBOX=="1"` 時允許回退 `module.source://` |
| [`ys_codebase/source/core/tests/test_config.py`](../../../../ys_codebase/source/core/tests/test_config.py) | Modify | 移除頂層冗餘 `sys.path.insert(0, "..")` |
| [`ys_codebase/source/core/tests/test_platform.py`](../../../../ys_codebase/source/core/tests/test_platform.py) | Modify | 新增 `test_installed_module_roots_and_sys_path_priority` 與 `test_runtime_pythonpath_subprocess_and_test_source_activation` 單元測試 |
| [`ys_codebase/source/server/server/master.py`](../../../../ys_codebase/source/server/server/master.py) | Modify | `_spawn_worker_locked` 統一調用 `build_runtime_pythonpath` 組裝 Worker `PYTHONPATH` |
| [`ys_codebase/source/server/server/worker.py`](../../../../ys_codebase/source/server/server/worker.py) | Modify | `WarmWorker.pre_warm` 統一調用 `ensure_installed_modules_path(..., include_host_roots=True)` |
| [`ys_codebase/source/server/server/service.py`](../../../../ys_codebase/source/server/server/service.py) | Modify | `ServiceManager._load_service_item` 統一調用 `ensure_installed_modules_path(yscb_root=yscb_root, priority_module=provider)` |
| [`ys_codebase/source/agents-workflow/agents_workflow/compiler.py`](../../../../ys_codebase/source/agents-workflow/agents_workflow/compiler.py) | Modify | 移除頂層手動 `sys.path` 補丁與 `source/core` 越界探測 |
| [`ys_codebase/source/agents-workflow/agents_workflow/publisher.py`](../../../../ys_codebase/source/agents-workflow/agents_workflow/publisher.py) | Modify | 移除頂層手動 `sys.path` 補丁與 `source/core` 越界探測 |
| [`ys_codebase/source/agents-workflow/scripts/hook.core.py`](../../../../ys_codebase/source/agents-workflow/scripts/hook.core.py) | Modify | 移除頂層手動 `sys.path` 補丁與 `source/core` 越界探測 |
| [`ys_codebase/source/vscode-support/scripts/cli.py`](../../../../ys_codebase/source/vscode-support/scripts/cli.py) | Modify | 移除 `_ensure_module_path()` 定義與 3 處呼叫 |
| [`ys_codebase/source/vscode-support/scripts/hook.core.py`](../../../../ys_codebase/source/vscode-support/scripts/hook.core.py) | Modify | 移除 `_ensure_module_path()` 定義與 2 處呼叫 |
| [`ys_codebase/source/vscode-support/vscode_support/projector.py`](../../../../ys_codebase/source/vscode-support/vscode_support/projector.py) | Modify | 串接 `core.platform.list_module_search_roots` 自動投影全模組與源碼搜尋路徑至 `python.analysis.extraPaths`，並於含 `.modules/` 時動態省略 `**/.modules/**` 排除規則（`TODO-22`） |
| [`ys_codebase/source/vscode-support/tests/test_vscode_support.py`](../../../../ys_codebase/source/vscode-support/tests/test_vscode_support.py) | Modify | 新增 `test_ft_07_module_and_source_extra_paths_projection_and_revert` 單元測試 |
| [`ys_codebase/source/file-space/scripts/cli.py`](../../../../ys_codebase/source/file-space/scripts/cli.py) | Modify | 移除 `_ensure_module_path()` 定義與 6 處呼叫 |
| [`ys_codebase/source/ast/ast_engine/__init__.py`](../../../../ys_codebase/source/ast/ast_engine/__init__.py) | Modify | 移除 `_ensure_dependency_module_paths()` 定義與呼叫 |
| [`ys_codebase/source/ast/ast_engine/bundler.py`](../../../../ys_codebase/source/ast/ast_engine/bundler.py) | Modify | `_init_bundle_worker` 委派呼叫 `core.platform.init_subprocess_sys_path` |
| [`ys_codebase/source/ast/ast_engine/parsers/registry.py`](../../../../ys_codebase/source/ast/ast_engine/parsers/registry.py) | Modify | `_ensure_search_paths` 與 `_instantiate_custom_parser` 委派呼叫 `core.platform.ensure_installed_modules_path` |
| [`ys_codebase/source/ast/scripts/cli.py`](../../../../ys_codebase/source/ast/scripts/cli.py) | Modify | 移除 `_ensure_module_path()` 定義與 2 處呼叫 |
| [`ys_codebase/source/ast/scripts/hook.file-space.py`](../../../../ys_codebase/source/ast/scripts/hook.file-space.py) | Modify | 移除 `_ensure_module_path()` 定義與 2 處呼叫 |
| [`ys_codebase/source/knowledge-db/knowledge_db/__init__.py`](../../../../ys_codebase/source/knowledge-db/knowledge_db/__init__.py) | Modify | 移除 `_ensure_dependency_module_paths()` 定義與呼叫 |
| [`ys_codebase/source/knowledge-db/knowledge_db/io_utils.py`](../../../../ys_codebase/source/knowledge-db/knowledge_db/io_utils.py) | Modify | 移除 `_ensure_ast_path()` 定義與呼叫 |
| [`ys_codebase/source/knowledge-db/knowledge_db/providers.py`](../../../../ys_codebase/source/knowledge-db/knowledge_db/providers.py) | Modify | 移除 `_ensure_file_space_path()` 定義與呼叫 |
| [`ys_codebase/source/dev/dev/checker.py`](../../../../ys_codebase/source/dev/dev/checker.py) | Modify | 1. `_check_custom_rules` 委派 `ensure_installed_modules_path` 與 `restore_sys_path`；<br/>2. 於 `_check_source_files` 新增 `_find_sys_path_mutations` 零豁免 AST 檢查 |
| [`ys_codebase/source/dev/dev/testing/runner.py`](../../../../ys_codebase/source/dev/dev/testing/runner.py) | Modify | `TestDiscovery.build_suite_for_module` 委派 `activate_test_module_source_path` 並修正 `sys.modules` 套件名清除邏輯 |
| [`ys_codebase/source/dev/dev/testing/case.py`](../../../../ys_codebase/source/dev/dev/testing/case.py) | Modify | `YSCBTestCase.tearDown` 委派 `restore_sys_path` |
| [`ys_codebase/source/dev/tests/test_checker.py`](../../../../ys_codebase/source/dev/tests/test_checker.py) | Modify | 新增 `test_checker_forbids_non_core_sys_path_mutation` 正反例單元測試 |
| [`docs/core/README.md`](../../../../docs/core/README.md) | Modify | 同步更新 5.2 節 `core.platform` 統一全模組路徑管理說明 |
| [`docs/core/DESIGN_NOTES.md`](../../../../docs/core/DESIGN_NOTES.md) | Modify | 新增 `DN-18`：`core.platform` 統一全模組 `sys.path` 注入與非 `core` 模組零豁免靜態守門 |
| [`docs/dev/architecture.md`](../../../../docs/dev/architecture.md) | Modify | 更新 Step 4 `_check_source_files` 禁止非 `core` 生產代碼直接變動 `sys.path` 規則 |
| [`docs/dev/DESIGN_NOTES.md`](../../../../docs/dev/DESIGN_NOTES.md) | Modify | 新增 `DN-DEV-06`：非 `core` 生產源碼禁止直接變動 `sys.path` 之零豁免 AST 靜態守門 |
| [`docs/vscode-support/README.md`](../../../../docs/vscode-support/README.md) | Modify | 更新 `SettingsProjector` 模組與源碼 `extraPaths` 自動投影說明 |
| [`docs/vscode-support/DESIGN_NOTES.md`](../../../../docs/vscode-support/DESIGN_NOTES.md) | Modify | 更新 `DN-02` 補充 `list_module_search_roots` 投影與 `analysisExclude` 動態控制決策 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `python yscb.py dev check --all`：9 大模組 100% `PASSED`（0 Warnings, 0 Failed）。
  - 全倉 9 大模組 `dev test`：共 **715 項測試 100.0% 通過**（`core`: 242, `dev`: 87, `file-space`: 17, `vscode-support`: 11, `ast`: 26, `knowledge-db`: 109, `server`: 56, `agents-workflow`: 141, `gdrive-support`: 26）。
- **實機 UX / 人工驗證**：
  - `UX-01`（`[測試通過]`）：實機執行冷派發跨模組指令 `python yscb.py gdrive auth --check --json` 成功解析 `file_space` 並回傳 `"status": "credentials_ready"`，開發者已確認驗收通過。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | [`CHANGELOG.md`](../../../../CHANGELOG.md) | 免更（待母計畫三子計畫全數完成與模組版本發布時統一記錄） | 發布亮點與變更歷史同步 |
| **中觀 (Meso)** | [`docs/core/README.md`](../../../../docs/core/README.md) | 已更新 | 模組手冊 5.2 節新增 `core.platform` 統一全模組路徑管理說明 |
| **中觀 (Meso)** | [`docs/dev/architecture.md`](../../../../docs/dev/architecture.md) | 已更新 | 專題手冊 Step 4 補充 `_find_sys_path_mutations` 靜態 AST 檢核規則 |
| **中觀 (Meso)** | [`docs/core/DESIGN_NOTES.md`](../../../../docs/core/DESIGN_NOTES.md)<br/>[`docs/dev/DESIGN_NOTES.md`](../../../../docs/dev/DESIGN_NOTES.md) | 已更新 | 登錄 `DN-18` 與 `DN-DEV-06`（全模組路徑注入、沙盒受測源碼前端釘選與零豁免 AST 守門） |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 (`core/platform/venv.py`, `dev/checker.py`) | 已更新 | 嚴格維護 Docstring，零工單與審計編號殘留 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
refactor(core,dev): centralize runtime sys.path management in core.platform and enforce AST guardrail

- Add list_installed_module_roots, ensure_installed_modules_path, build_runtime_pythonpath, init_subprocess_sys_path, activate_test_module_source_path, and restore_sys_path in core.platform
- Converge CLI cold/warm dispatch, event broadcast, symbol resolution, server worker pre-warm, AST bundler/registry, and dev test runner onto core.platform primitives
- Remove 13 scattered manual sys.path patches and source/ fallbacks across agents-workflow, vscode-support, file-space, ast, knowledge-db, and dev
- Add zero-exemption static AST check (_find_sys_path_mutations) in dev.checker forbidding direct sys.path mutations in non-core production source files
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

