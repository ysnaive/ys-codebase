# 測試計畫書 (Test Plan)

> 功能名稱：套件框架健壯性強化與缺陷修復 (Framework Robustness & Bug Fixes)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：Confirmed (CLI 自動化測試 100% 通過，等候 UX / 手動驗證 Checkpoint)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 測試策略與驗證維度

本測試計畫遵循 Test-First 原則，針對剛性拓撲隔離、SemVer 2.0.0 版本運算器、雙層快照還原、Context Manager 隔離防護與精確測試報表進行全面覆蓋：
- **功能測試 (FT)**：驗證 SemVer 數值排序、依賴範圍求解、雙層快照備份還原、同層剛性組態載入、沙盒動態版本繼承與精確分類計數。
- **邊界測試 (ET)**：驗證無效 URI 格式攔截、畸形版本字串報錯、無合規版本阻斷與 Context Manager 例外安全性。
- **回歸測試 (RT)**：驗證全模組 (core, dev) 現有 48 項測試與新增 11 項測試全數 100% 綠燈通過。

---

## 2. 測試案例清冊 (Test Cases Matrix)

| 測試編號 | 測試名稱 | 驗證目標 | 執行方式 / 斷言 | 對應 FR / EC | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FT-01** | `test_semver_numerical_ordering_and_comparison` | 驗證 SemVer 2.0.0 數值排序物理保證 `1.10.0 > 1.9.0`、`1.0.1 > 1.0.0` 與 prerelease 比對 | 呼叫 `parse_semver` 並執行 `sorted()`，斷言 `1.10.0` 排在 `1.9.0` 之後 | FR-05 | ✅ Passed |
| **FT-02** | `test_semver_constraint_matching_and_solver` | 驗證 `>=, >, <=, <, ==, ~=, *` 範圍匹配與 `act_solve_deps` 選取最高合規版本 | 給定版本清單與約束 `">=1.0.0"`，斷言 `find_best_version` 與 `act_solve_deps` 精確命中最高版本 | FR-05<br/>EC-03 | ✅ Passed |
| **FT-03** | `test_context_manager_scope_auto_restore` | 驗證 `module_scope` 與 `host_scope` 退出時 `finally` 100% 自動還原舊全域狀態 | 在 `with module_scope("dev"):` 修改上下文，退出後斷言全域狀態恢復原狀 | FR-10 | ✅ Passed |
| **FT-04** | `test_dual_layer_snapshot_and_rollback` | 驗證 `act_snapshot` 同步備份 `config.root://`，且 `act_restore_snapshot` 同步完整還原 `config/` 目錄 | 修改 `config/core/config.project.json` 後還原快照，斷言設定檔 100% 恢復至快照前狀態 | FR-08<br/>EC-04 | ✅ Passed |
| **FT-05** | `test_load_config_rigid_same_dir_anchor` | 驗證 `yscb.py:load_config` 僅探測同層目錄，無向上爬目錄逃逸 | 在無設定檔的子目錄執行 `load_config`，斷言返回 `(None, None)`，不向上爬至宿主根 | FR-01 | ✅ Passed |
| **FT-06** | `test_act_download_strict_version_matching` | 驗證本地 Provider 下載僅拷貝特定版本目錄，杜絕整包巢狀多版本拷貝 | 模擬包含多版本的 Provider 目錄，執行 `act_download`，斷言鏡像中無巢狀版本資料夾 | FR-09<br/>EC-05 | ✅ Passed |
| **FT-07** | `test_sandbox_manifest_dynamic_version_inheritance` | 驗證沙盒繼承模組時讀取真實 `manifest.json` 版本號與描述寫入沙盒設定 | 建立沙盒，斷言沙盒內 `yscb.config.json` 記錄之版本與真實模組 manifest 一致 | FR-11 | ✅ Passed |
| **FT-08** | `test_test_runner_accurate_counting_and_failure_list` | 驗證 Contract/Custom 精準分類計數與失敗案例獨立清單輸出 | 執行包含失敗案例之測試套件，斷言 `contract_passed` 與 `custom_passed` 無交叉誤扣且輸出失敗清單 | FR-12 | ✅ Passed |
| **ET-01** | `test_invalid_uri_string_raises_value_error` | 驗證傳入非標準 URI 字串至 `resolve()` 拋出 `ValueError`，杜絕模糊推測 | 呼叫 `uri.resolve("invalid/path/string")`，斷言拋出 `ValueError` | FR-03<br/>EC-01 | ✅ Passed |
| **ET-02** | `test_malformed_semver_raises_value_error` | 驗證傳入畸形版本字串至 SemVer 解析器拋出 `ValueError` | 呼叫 `parse_semver("v1.x.y")`，斷言拋出 `ValueError` | FR-05<br/>EC-02 | ✅ Passed |
| **ET-03** | `test_unsatisfiable_constraint_raises_runtime_error` | 驗證無可用版本滿足依賴約束時 `act_solve_deps` 拋出 `RuntimeError` | 請求約束 `">=2.0.0"` 但僅有 `1.0.0`，斷言 `act_solve_deps` 拋出 `RuntimeError` | FR-05<br/>EC-03 | ✅ Passed |
| **ET-04** | `test_context_manager_exception_safety` | 驗證 Context Manager 內部發生例外時仍保證全域狀態還原且例外向上正常拋出 | 在 `module_scope` 內故意 raise 例外，斷言外層捕獲例外且全域狀態已還原 | FR-10<br/>EC-06 | ✅ Passed |
| **RT-01** | `test_full_regression_all_modules` | 驗證全模組 (core, dev) 既有 48 項測試與新增測試 100% 綠燈通過 | 實機執行 `python yscb.py dev test --all`，斷言全部測試 100% Passed (59/59) | 全功能 | ✅ Passed |

---

## 3. 測試執行結果 (Test Execution Log)

實機執行命令：`python yscb.py dev test --all`

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Module: core                                                   [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (32/32)
[*] Module: dev                                                    [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (21/21)
----------------------------------------------------------------------
Summary : 59 Total, 59 Passed, 0 Failed, 0 Skipped (5.077s)
Status  : PASSED (100% Ready)
======================================================================
```

---

## 4. UX / 人工驗證 Checkpoint

- [ ] 開發者實機執行 `python yscb.py core update <mod>` 驗證 SemVer 排序升級行為符合預期。
- [ ] 開發者實機檢視 `build/core/1.0.0` 與 `build/dev/1.0.0`，確認無 `tests/` 與 `.yscbignore`。
- [ ] 開發者實機檢視測試報告輸出，確認 Contract/Custom 分離統計與失敗清單排版視覺體驗。
