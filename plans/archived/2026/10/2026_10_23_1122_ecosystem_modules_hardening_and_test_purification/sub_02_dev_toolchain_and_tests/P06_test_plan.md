# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_02_dev_toolchain_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash (Medium)  

> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 整合測試 | 驗證 `dev test core -k manifest -q` 子進程參數無損傳遞，不覆寫模組名且節流輸出 | FR-01 | `test_tester.py::test_op_test_single_token_normalization` |
| **FT-02** | 單元測試 | 驗證 `Releaser.release_check` Gate 3 攔截跨三元組版本回退（如在庫 1.1.0.0 退回 1.0.0.5） | FR-02 | `test_release_pipeline.py::test_release_gate3_cross_triplet_rollback_blocking` |
| **FT-03** | 單元測試 | 驗證 `release_all` 字母序穩定 DAG 拓撲排序，且上游失敗時自動跳過下游模組 | FR-02 | `test_release_pipeline.py::test_release_all_kahn_dag_and_failure_propagation` |
| **FT-04** | 整合測試 | 驗證 `release_git` 在 `git commit` 非零且非 working tree clean 時中止打 Tag | FR-02 | `test_release_pipeline.py::test_release_git_fatal_commit_error_handling` |
| **FT-05** | 單元測試 | 驗證未呼叫 `mark_passed()` 之測試導致 `UNKNOWN > 0`、回傳 1 且 `custom_passed` 正確扣除 | FR-03 | `test_tester.py::test_unknown_fails_tester_and_deducts_custom_passed` |
| **FT-06** | 單元測試 | 驗證 `Requirement.NETWORK` 納入預設發現且離線時觸發 `SkipTest`，`_FailedTest` 保留不漏報 | FR-03 | `test_tester.py::test_filter_suite_retains_failed_test_and_discovers_network` |
| **FT-07** | 整合測試 | 驗證 `Checker._check_custom_rules` 僅臨時注入 `module://<donor>` 且異常轉 `WARN` 不吞沒 | FR-04 | `test_checker.py::test_checker_custom_rules_dispatch_and_isolation` |
| **FT-08** | 單元測試 | 驗證 `Checker._check_core_injection` 優先讀取源碼 Schema，CLI 檢核精確對齊 `{full_fn, primary_fn}` | FR-04 | `test_checker.py::test_checker_core_injection_format_priority` |
| **FT-09** | 單元測試 | 驗證 `Scaffolder` 與 Mock 產生器不再產生 `process(args)`，預設通過 `check_module` | FR-05 | `test_scaffold.py::test_create_module_creates_all_templates` |
| **FT-10** | 單元測試 | 驗證 `SandboxProvisioner` 以數值 SemVer 排序選包，`YSCBTestCase` 自動還原 CWD | FR-06 | `test_sandbox.py::test_sort_zip_filenames_by_semver_and_bad_zip` |
| **FT-11** | 體檢去重 | 驗證 `test_cli_compliance.py`、`test_output_purification.py`、`test_pip_adaptation.py` 收斂為 7 檔 | FR-08 | `python yscb.py dev test dev -q` (檢查檔數為 7) |
| **FT-12** | 規格對稱 | 驗證 `yscb-module-dev` 技能手冊與 `contributes/core.json` events/options 契約一致，PEP 562 延遲載入 | FR-07 | `test_tester.py::test_dev_pep562_lazy_loading_and_cli_test_dispatch` |
| **FT-13** | 回歸補盲 | 驗證 `D-01`~`D-08` 五大高風險路徑（DAG/防回退/UNKNOWN/自訂檢核/bump-*）整合回歸測試 | FR-09 | `test_release_pipeline.py::test_cli_bump_and_release_check_commands` |
| **ET-01** | 邊界測試 | `dev test` 傳入 `-k <pat>` 或 `--pattern=<pat>` 時子進程不將 pattern 誤判為模組 | EC-01 | `test_tester.py::test_op_test_single_token_normalization` |
| **ET-02** | 邊界測試 | `release_check` 帶 `--force` 嘗試回退版本（`target < global_highest`）依然剛性阻斷 | EC-02 | `test_release_pipeline.py::test_release_gate3_cross_triplet_rollback_blocking` |
| **ET-03** | 邊界測試 | `release_git` 遇非零退出碼時正確區分 `nothing to commit`（放行）與 Git 配置錯誤（阻斷） | EC-03 | `test_release_pipeline.py::test_release_git_fatal_commit_error_handling` |
| **ET-04** | 邊界測試 | `release_all` 偵測到循環依賴拋出 `CyclicDependencyError` | EC-04 | `test_release_pipeline.py::test_release_all_kahn_dag_and_failure_propagation` |
| **ET-05** | 邊界測試 | 含 `SyntaxError` 測試檔在 `--type=env/workflow` 下依然被 `filter_suite` 保留並回傳失敗 | EC-05 | `test_tester.py::test_unknown_fails_tester_and_deducts_custom_passed` |
| **ET-06** | 邊界測試 | 自訂檢核函式拋出未捕獲例外，轉換為 `WARN` 且 `sys.path` 於 finally 正確還原 | EC-06 | `test_checker.py::test_checker_custom_rules_dispatch_and_isolation` |
| **ET-07** | 邊界測試 | `.build` 目錄含 `1.9.0.build.zip` 與 `1.10.0.build.zip`，正確選出 `1.10.0` 且防護損毀 Zip | EC-07 | `test_sandbox.py::test_sort_zip_filenames_by_semver_and_bad_zip` |
| **RT-01** | 全量回歸 | 執行 `python yscb.py dev check dev` 與 `python yscb.py dev test dev -q` 100% 通過且零殘留 | NFR-01, NFR-02 | `dev check dev` && `dev test dev -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-13** | `Passed` | 79/79 tests passed in 6.19s (0 Fail, 0 Unknown, 0 Skip) | 2026-10-24 |
| **ET-01 ~ ET-07** | `Passed` | 覆蓋全數邊界與剛性阻斷路徑，反向驗證補強斷言全數通過 | 2026-10-24 |
| **RT-01** | `Passed` | `dev check dev` (0 Fail 0 Warn) & `dev test dev --sync` 全綠通過，工作區零殘留 | 2026-10-24 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 在終端機執行 `python yscb.py dev test core -k manifest -q`，驗證子進程不再報錯 `Module 'manifest' not found in source/.` 且輸出美觀節流。 | `Verified` | 實機執行輸出 `Pass: 2(100.0%), Fail: 0, Skip: 0`，Exit 0 |
| **UX-02** | 在終端機執行 `python yscb.py dev release-check`（無參數），驗證預設對全模組進行 3-Gate 檢核並正確列出合規狀態。 | `Verified` | 實機預設掃描全數 5 模組並逐一列出 3-Gate 檢核狀態 |
