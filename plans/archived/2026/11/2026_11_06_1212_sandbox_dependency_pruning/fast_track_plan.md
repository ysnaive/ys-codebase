# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：2026_11_06_1212_sandbox_dependency_pruning  
> 建立日期：2026-11-06  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)

### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)
- [x] **修改行數守門**：代碼修改行數預估 $\le 100$ 行。
- [x] **API 契約守門**：Public API 簽名契約 0 變更（無破壞性與新增導出）。
- [x] **依賴邊界守門**：零跨模組新依賴引入。
- [x] **既有測試守門**：既有單元測試套件 100% 覆蓋守門。

### 1.2 核心需求與邊界
- **需求描述**：
  - 目前 `SandboxProvisioner._deploy_target_and_dependency_modules` 在建立虛擬沙盒時忽略 `target_modules`，無條件將 `module.build://` 與宿主 `module://`（`.modules/`）中的所有已安裝模組全量解壓或複製至沙盒的 `engine/.modules/`。當執行 `python yscb.py dev test core` 時，不相干的下游模組（如 `agents-workflow`）一併被帶入 `core` 測試沙盒，導致每次 `core` 測試觸發 `on_reload` 時引發 `agents-workflow` 全量技能編譯並逾時。
  - 本計畫使 `SandboxProvisioner` 支援依 `target_modules`（或沙盒內跨子行程環境變數 `YSCB_TEST_TARGET_MODULES`）計算目標模組之**遞迴硬性相依閉包（Transitive Dependency Closure）**，加上測試基座必備的 `core` 與 `dev`，僅將閉包內的模組部署至沙盒 `engine/.modules/` 並寫入 `yscb.config.json["installed_modules"]`。當 `target_modules` 未指定且無環境變數約束（或包含 `--all`）時，維持全量部署向後相容。
- **影響範圍**：
  - `ys_codebase/source/dev/dev/testing/sandbox.py`
  - `ys_codebase/source/dev/dev/tester.py`
  - `ys_codebase/source/dev/tests/test_sandbox.py`

### 1.3 實作任務與測試規劃
- [x] **TASK-01**：於 `SandboxProvisioner` (`ys_codebase/source/dev/dev/testing/sandbox.py`) 新增 `_read_module_manifest` 與 `_resolve_dependency_closure` 內部輔助方法，支援從 `target_modules` 參數或 `YSCB_TEST_TARGET_MODULES` 環境變數解析目標模組，並以 `{"core", "dev", *targets}` 為起點依 `manifest.json` 之 `dependencies` 計算遞迴閉包；更新 `_deploy_target_and_dependency_modules` 與 `adapt_build_pip_dependencies` 僅處理閉包內之模組。
- [x] **TASK-02**：於 `Tester` (`ys_codebase/source/dev/dev/tester.py`) 更新 `_run_test`（省略模組名時預設 `cand_targets = ["core"]`）、`_execute_single_module_in_sandbox`（設定子行程 `YSCB_TEST_TARGET_MODULES` 供沙盒內 `ISOLATED_SANDBOX` 繼承剪枝範圍）與 `_run_op_mksb`（支援位置參數傳入 `target_modules`）。
- **測試案例清冊**：
  - [x] **FT-01**：驗證 `SandboxProvisioner.create_sandbox(target_modules=["mod_top"])`（及 `_deploy_target_and_dependency_modules`）遞迴解析 `mod_top -> mod_mid -> mod_leaf` 相依閉包，沙盒 `.modules/` 與 `installed_modules` 僅包含 `core`、`dev`、`mod_top`、`mod_mid`、`mod_leaf`，排除不相干的 `mod_unrelated`，同時驗證 `YSCB_TEST_TARGET_MODULES` 環境變數繼承與 `target_modules=None` 全量向後相容。
  - [x] **RT-01**：全模組既有單元測試（`dev` 與 `core`）100% 回歸通過，且 `dev test core` 免受下游非相依模組 `on_reload` 干擾快速完測。

---

## 2. 實作與驗證成果 (FP-02 Execution & Test Log)

- **實作結果**：
  - 完成 `ys_codebase/source/dev/dev/testing/sandbox.py`（`_read_module_manifest`、`_resolve_dependency_closure`、`_deploy_target_and_dependency_modules`、`adapt_build_pip_dependencies`）與 `ys_codebase/source/dev/dev/tester.py`（`_run_op_mksb`、`_execute_single_module_in_sandbox`、`_run_test`）之遞迴相依閉包部署剪枝與 `YSCB_TEST_TARGET_MODULES` 傳遞，並同步安裝 `dev@1.1.4.build` 至本機環境。
  - 於 `ys_codebase/source/dev/tests/test_sandbox.py` 新增 `test_deploy_modules_prunes_to_transitive_dependency_closure` 驗證三層遞迴相依（`mod_top -> mod_mid -> mod_leaf`）與 `YSCB_TEST_TARGET_MODULES` 環境繼承剪枝。
- **實機測試日誌**：
  - `python yscb.py dev check dev`：`PASSED`（0 FAIL, 0 WARN）。
  - `python yscb.py dev test dev -q --sync`：`Pass: 109(100.0%), Fail: 0, Skip: 0`，並成功同步安裝 `dev@1.1.4.build`。
  - `python yscb.py dev test core --no-build`：`263 Total, 263 Passed, 0 Failed, 0 Skipped (139.150s) | Status: PASSED (100% Ready)`（不再載入 `agents-workflow` 等非相依下游模組，徹底消除 `on_reload` 編譯風暴與逾時）。

---

## 3. SOP Review 審查與結案交付 (Review & FP-03 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `CHANGELOG.md` 發布摘要。
- [x] **標頭狀態更新**：完成上述審查並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
