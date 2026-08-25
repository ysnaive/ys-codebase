# 測試計畫書 (Test Plan)

> 功能名稱：第三方真實使用者原生情境測試、問題排查與框架加固 (Native Consumer Testing & Hardening)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 檔案狀態：`Passed`  
> 對應需求規格：[P01_requirements_spec.md](./P01_requirements_spec.md) (FR-01 ~ FR-05, EC-01 ~ EC-04, NFR-01 ~ NFR-04)  
> 對應架構設計：[P02_architecture_plan.md](./P02_architecture_plan.md) ([P02:DR-01] ~ [P02:DR-04])  
> 實作計畫關聯：[P04_implementation_plan.md](./P04_implementation_plan.md) (TASK-01 ~ TASK-07)  
> 擴充項目：無  

---

## 1. 測試策略與驗證維度

| 驗證維度 | 測試層級 | 測試手段與工具 | 通過標準 (Gate) | 執行狀態 |
| :--- | :--- | :--- | :--- | :--- |
| **功能測試 (FT)** | 單元與整合測試 | Python `unittest` | 100% Passed (無斷言錯誤) | **PASS** |
| **邊界與例外測試 (ET)** | 異常情境注入 | Python `unittest` | 捕獲預期例外且無髒資料殘留 | **PASS** |
| **全模組回歸測試 (RT)** | 端到端黑盒沙盒 | `python yscb.py dev test --all` | 74/74 (100%) 全部通過 | **PASS** |

---

## 2. 測試案例清冊 (Test Cases Matrix)

| 測試編號 | 測試名稱 | 驗證目標 | 執行方式 / 斷言 | 對應 FR / EC | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FT-01** | `test_dev_build_outputs_single_zip` | 驗證 `dev build` 產出 `build/<mod>/<ver>.build.zip`（含 tests/）且不落地散裝目錄 | 呼叫 `build_module("core")`，斷言產生單一 `.zip` 檔案，且無散裝目錄 | FR-03 | ✅ Passed |
| **FT-02** | `test_dev_release_outputs_pure_single_zip` | 驗證 `dev release` 產出 `release/<mod>/<ver>.zip`（排除 tests/）且不落地散裝目錄 | 呼叫 `package_release("core", "1.0.0.0")`，斷言產生單一 `.zip`，內部無 `tests/` 與 `.yscbignore` | FR-02 | ✅ Passed |
| **FT-03** | `test_revision_purge_deletes_old_zip` | 驗證發布同 `X.Y.Z` 新 Revision 時直接刪除舊 `.zip` 單檔並更新 `index.json` | 模擬存在 `1.0.0.1.zip`，發布 `1.0.0.2.zip`，斷言舊 zip 被刪除，`index.json` 更新 | FR-04 | ✅ Passed |
| **FT-04** | `test_yscb_init_remote_zip_bootstrap` | 驗證 `yscb.py init` 遇遠端 HTTP Provider 串流下載 `core.zip` 並原生解包自舉 | 啟動 mock server，執行 `init`，斷言解包成功並順暢 `reload` | FR-01<br/>FR-05 | ✅ Passed |
| **FT-05** | `test_installer_remote_zip_install` | 驗證 `core.installer` 遇遠端 Provider 單次下載 `<mod>.zip` 並解包安裝 | 執行 `cmd_install` 指向 mock 遠端，斷言成功下載解包至 `.mirror/` 與 `modules/` | FR-05 | ✅ Passed |
| **FT-06** | `test_modules_pure_code_after_zip_extraction` | 驗證 Zip 解包至 `modules/` 後自動將 `config.*.json` 模板剝除 | 檢查解包後的 `modules/core/`，斷言不存在 `config.project.json` 或 `config.local.json` | FR-05 | ✅ Passed |
| **ET-01** | `test_corrupted_zip_fails_safely` | 驗證損壞的 Zip 檔案在解包前被拒絕且不污染 `modules/` | 注入損壞字節至 zip，執行解包，斷言拋出 `BadZipFile` 且工作區保持乾淨 | EC-01 | ✅ Passed |
| **ET-02** | `test_remote_404_raises_package_not_found` | 驗證遠端 Provider 回應 404 時精準拋出例外且無殘留檔案 | 請求不存在模組，斷言拋出例外且無殘留 `.tmp.zip` | EC-04 | ✅ Passed |
| **ET-03** | `test_local_provider_isomorphic_zip_ingestion` | 驗證本地 Provider 同構讀取 `.zip` 解包正常運作 | 指向本機目錄 Provider，執行 `install`，斷言讀取本機 `.zip` 解包成功 | EC-02 | ✅ Passed |
| **ET-04** | `test_remote_download_timeout_handling` | 驗證遠端下載超過 30 秒時精準拋出 Timeout 例外 | 模擬慢速伺服器，斷言 30s 逾時攔截並清理暫存檔 | EC-03 | ✅ Passed |
| **RT-01** | `test_full_regression_all_modules` | 驗證全模組 (core, dev) 既有與新增測試全數 100% 綠燈通過 | 實機執行 `python yscb.py dev test --all`，斷言 100% Passed (74/74) | 全功能 | ✅ Passed |

---

## 3. 測試執行結果記錄 (Phase 6 實機回填)

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Module: core                                                   [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (44/44)
[*] Module: dev                                                    [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (24/24)
----------------------------------------------------------------------
Summary : 74 Total, 74 Passed, 0 Failed, 0 Skipped (10.407s)
Status  : PASSED (100% Ready)
======================================================================
```
