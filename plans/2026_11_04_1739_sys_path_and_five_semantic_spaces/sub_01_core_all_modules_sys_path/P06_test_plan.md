# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_core_all_modules_sys_path  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 (`core`) | 驗證 `list_installed_module_roots` 與 `ensure_installed_modules_path`：正確按 `[extra_paths, priority_module, core, ...sorted_mods]` 排序並注入 `sys.path`，自動跳過 `.staging_*` / `.old_*` 隱藏目錄，排除任何 `<yscb_root>/source` 路徑，且單次執行耗時符合效能約束 | FR-01, EC-01, EC-03, NFR-01, NFR-03 | `python yscb.py dev test core` (`test_platform.py:test_installed_module_roots_and_sys_path_priority`) |
| **FT-02** | 單元測試 (`core`) | 驗證 `build_runtime_pythonpath`、`init_subprocess_sys_path`、`activate_test_module_source_path` 與 `restore_sys_path`：正確組裝 `PYTHONPATH`、同步子進程路徑、在沙盒測試中保留 `.modules/*` 相依同時剔除其他 `source/*` 並將受測模組置頂及完整還原 | FR-01, FR-02, EC-04 | `python yscb.py dev test core` (`test_platform.py:test_runtime_pythonpath_subprocess_and_test_source_activation`) |
| **FT-03** | 單元測試 (`dev`) | 驗證 `Checker._find_sys_path_mutations` 與 `_check_source_files`：非 `core` 模組生產檔案中出現 `sys.path.insert/append/extend/remove/pop/clear`、`sys.path[:] = ...`、`del sys.path[0]` 或別名變動時觸發 `CheckSeverity.FAIL`；唯讀存取 (`in sys.path`, `list(sys.path)`)、`core` 模組與 `tests/` 測試檔則正常通過 | FR-04, EC-05, NFR-02 | `python yscb.py dev test dev` (`test_checker.py:test_checker_forbids_non_core_sys_path_mutation`) |
| **FT-04** | 整合與回歸測試 (全模組 `dev check`) | 拔除 13 處散落補丁並收斂特殊路徑操作後，對全倉 9 大模組執行 `dev check --all`，確認 0 `FAIL`、0 非 `core` 生產代碼 `sys.path` 變動違規 | FR-03, FR-04, NFR-02 | `python yscb.py dev check --all` |
| **FT-05** | 整合與回歸測試 (全模組 `dev test` + 冷派發驗證) | 對全倉 9 模組執行 `dev test` 全數通過；實機執行冷派發指令 `python yscb.py gdrive auth --check --json` 確認不再拋出 `Sync space 'cloud' is not registered in file-space. Available spaces: []` | FR-02, FR-03, EC-02 | 全倉 `dev test` (715 tests) 及 `python yscb.py gdrive auth --check --json` |
| **FT-06** | 單元測試 (`vscode-support`) | 驗證 `SettingsProjector._compute_managed_extra_paths` 與 `sync_vscode_settings` / `revert_vscode_settings`：自動將 `list_module_search_roots` 發現之 `source/<mod>`（優先）與 `.modules/<mod>` 投影至 `python.analysis.extraPaths`（`core` 置於 `current-site-packages` 之後首位），當含 `.modules/` 時動態自 `python.analysis.exclude` 移除 `**/.modules/**`，且 `revert` 100% 乾淨還原 | FR-05, EC-06 | `python yscb.py dev test vscode-support` (`test_vscode_support.py:test_ft_07_module_and_source_extra_paths_projection_and_revert`) |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `core` 測試套件 `Pass: 242(100.0%), Fail: 0, Skip: 0`（含 `test_installed_module_roots_and_sys_path_priority`） | 2026-11-04 |
| **FT-02** | `Passed` | `core` 測試套件 `Pass: 242(100.0%), Fail: 0, Skip: 0`（含 `test_runtime_pythonpath_subprocess_and_test_source_activation`） | 2026-11-04 |
| **FT-03** | `Passed` | `dev` 測試套件 `Pass: 87(100.0%), Fail: 0, Skip: 0`（含 `test_checker_forbids_non_core_sys_path_mutation` 正反例測試） | 2026-11-04 |
| **FT-04** | `Passed` | `python yscb.py dev check --all`：`Summary: 9 Total, 9 Passed, 0 Warnings, 0 Failed` | 2026-11-04 |
| **FT-05** | `Passed` | 全倉 9 模組 `dev test` 共 715 項測試 100% 通過（`core`: 242, `dev`: 87, `file-space`: 17, `vscode-support`: 11, `ast`: 26, `knowledge-db`: 109, `server`: 56, `agents-workflow`: 141, `gdrive-support`: 26）；冷派發 `python yscb.py gdrive auth --check --json` 成功解析 `file_space` 並回傳 `"status": "credentials_ready"` | 2026-11-04 |
| **FT-06** | `Passed` | `vscode-support` 測試套件 `Pass: 11(100.0%), Fail: 0, Skip: 0`（含 `test_ft_07_module_and_source_extra_paths_projection_and_revert`） | 2026-11-04 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行冷派發跨模組指令 `python yscb.py gdrive auth --check --json` 與全模組 `python yscb.py dev check --all`，確認 `gdrive` 冷派發可正常解析 `file_space` 且全倉靜態檢查 100% 通過 | `[測試通過]` | 開發者確認驗收通過（2026-11-04） |
