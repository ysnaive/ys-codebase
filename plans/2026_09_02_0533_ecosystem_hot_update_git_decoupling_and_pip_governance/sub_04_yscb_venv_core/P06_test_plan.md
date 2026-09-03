# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：yscb_venv_core  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `yscb.venv://` 空間協議可正確解析至 `yscb_abs/.venv/` | FR-05 | `pytest source/core/tests/test_venv_core.py -k test_uri_resolve` |
| **FT-02** | 單元測試 | 驗證 `PipManager` 依 Python 大小版本分層建立微環境及跨平台路徑解析 | FR-01 | `pytest source/core/tests/test_venv_core.py -k test_pip_manager_paths` |
| **FT-03** | 單元測試 | 驗證 Wheel-Only 靜默安裝參數封裝與 `PipInstallError` 異常捕獲 | FR-02 | `pytest source/core/tests/test_venv_core.py -k test_install_packages_flags` |
| **FT-04** | 單元測試 | 驗證 `_generate_internal_gitignore` 內部標記區塊軟合併包含 `/.venv/` | FR-05 | `pytest source/core/tests/test_venv_core.py -k test_internal_gitignore` |
| **FT-05** | 單元測試 | 驗證 `yscb.py` 前置 `_ensure_private_venv_path` 動態注入 `sys.path` 前端 | FR-04 | `pytest source/core/tests/test_venv_core.py -k test_sys_path_injection` |
| **FT-06** | 單元測試 | 驗證 `IdeProjector` 在 `project://.vscode` 不存在時靜默略過不建立目錄 | FR-06 | `pytest source/core/tests/test_venv_core.py -k test_ide_projector_skip` |
| **FT-07** | 單元測試 | 驗證 `IdeProjector` 明確標示 `_yscb_managed` 區塊與可復原軟合併（保留使用者自訂設定） | FR-06 | `pytest source/core/tests/test_venv_core.py -k test_ide_projector_soft_merge` |
| **FT-08** | 單元測試 | 驗證模組 `manifest.json` 之 `pip_dependencies` 宣告解析與安裝管線聯集聚合 | FR-03 | `pytest source/core/tests/test_venv_core.py -k test_installer_pip_deps` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_01_uri_resolve_yscb_venv`: 驗證 `yscb.venv://` 解析為 `yscb_abs/.venv/` 通過 | 2026-09-03 |
| **FT-02** | `Passed` | `test_ft_02_pip_manager_paths`: 驗證 `PipManager` 版本分層 (`py310` 等) 與跨平台路徑解析通過 | 2026-09-03 |
| **FT-03** | `Passed` | `test_ft_03_install_packages_flags`: 驗證 Wheel-Only 旗標與 `PipInstallError` 異常捕獲通過 | 2026-09-03 |
| **FT-04** | `Passed` | `test_ft_04_internal_gitignore_contains_venv`: 驗證內部標記區塊軟合併注入 `/.venv/` 通過 | 2026-09-03 |
| **FT-05** | `Passed` | `test_ft_05_sys_path_injection`: 驗證 `_ensure_private_venv_path` 動態注入 `sys.path[0]` 通過 | 2026-09-03 |
| **FT-06** | `Passed` | `test_ft_06_ide_projector_skip_when_no_vscode`: 驗證無 `.vscode` 目錄時靜默略過零目錄污染通過 | 2026-09-03 |
| **FT-07** | `Passed` | `test_ft_07_ide_projector_soft_merge_and_revert`: 驗證 `_yscb_managed` 明確標記與可復原軟合併通過 | 2026-09-03 |
| **FT-08** | `Passed` | `test_ft_08_installer_sync_pip_dependencies`: 驗證模組 manifest 依賴解析與物化對接通過 | 2026-09-03 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：實機檢視 `yscb://.gitignore`，確認包含 `/.venv/` 且處於 `# === YSCB INTERNAL IGNORE BEGIN ===` 區塊內。
- [x] **UX-02**：實機檢驗若專案存在 `.vscode/`，安裝後 `.vscode/settings.json` 包含 `_yscb_managed` 且原有自訂配置未被覆蓋。
- [x] **UX-03**：實機執行 `python yscb.py dev test core --quiet`，確認全生態系測試 100% 通過。
