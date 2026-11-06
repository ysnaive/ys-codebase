# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：vscode-support 模組業務與測試代碼確定性優化 (vscode-support Deterministic Optimization)
> 建立日期：2026-11-06
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella
> 狀態：Passed
> 模型：Unknown
> 模板版本：v1.4

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `strip_jsonc` 單趟掃描、`_load_settings_jsonc` 處理非 `dict` JSON/JSONC 不誤建 `.bak`、`_is_under_yscb_venv` 與 `_set_or_pop_list` | FR-01, EC-01, NFR-01 | `TestVSCodeSupport` (`test_strip_jsonc_*`, `test_projector_*`, `test_non_dict_settings_*`) |
| **FT-02** | 單元測試 | 驗證 `SchemaCompiler` 鏡像檢索去重（無 `.zip` 時單次傳遞 `latest_zip=""`）、`_compile_type_defs` 與孤兒 Schema 清理 | FR-02, EC-02, NFR-01 | `TestVSCodeSupport` (`test_schema_compiler_*`, `test_mirror_fallback_*`) |
| **FT-03** | 單元測試 | 驗證 CLI (`sync`, `status`, `revert`) JSON/人類可讀雙模式、Lifecycle Hooks、PEP 562 延遲載入與 19 項單一職責測試無虛假 stub | FR-03, FR-04, NFR-02 | `TestVSCodeSupport` (`test_cli_*`, `test_hooks_*`, `test_pep562_lazy_loading`) |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Ran 22 tests in 0.436s — OK (0 ResourceWarning)` | 2026-11-06 |
| **FT-02** | `Passed` | `Ran 22 tests in 0.436s — OK (0 ResourceWarning)` | 2026-11-06 |
| **FT-03** | `Passed` | `Ran 22 tests in 0.436s — OK (0 ResourceWarning)` | 2026-11-06 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 驗證 `vscode-support` 全量單元與合約測試（`22 / 22` 通過、`0 ResourceWarning`）、`Checker().check_module("vscode-support")`（`0 FAIL, 0 WARN`）與五步盲測閉環融斷結果 | `[測試通過]` | 經 Blind Subagents D / E 驗證通過 |
