# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_02_dev_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `Mode A` 相容別名、死例外、`Builder._should_ignore` 孤兒轉發方法、`CheckReport` 解包方法、`Requirement` 舊別名與殭屍參數清除 (`M-01`~`M-12`, `R02`) | FR-01, FR-02 | `python yscb.py dev test dev -k "TestReleasePipeline or TestCaseSandboxLifecycleTest or TestDevScaffolder"` |
| **FT-02** | 整合測試 | 驗證全模組 `uri.<io>` 遷移至 `vfs.<io>`、6 處 `discover_source_modules` 統一探索、`cli.py` `check()` 單一迴圈報表與 `case.py` 公開 URI Context API 運作正常 (`R01`, `R02`) | FR-03, NFR-01 | `python yscb.py dev test dev -k "TestDevBuilder or TestDevChecker"` |
| **FT-03** | 單元/邊界測試 | 驗證 `SandboxProvisioner` `_SANDBOX_LOCK` 加鎖保護、`_sweep_sandboxes` 清理收斂、`_find_latest_build_zip` 共用檢索、建置失敗回滾與 4 階段拆解 (`R01`, `R02`) | FR-04, EC-01, EC-03 | `python yscb.py dev test dev -k "TestSandboxArchitecture"` |
| **FT-04** | 單元/邊界測試 | 驗證 `Builder._create_module_archive_atomic` 原子打包與 `.zip.tmp` `try...finally` 異常清理 | FR-05, EC-02 | `python yscb.py dev test dev -k "TestDevBuilder"` |
| **FT-05** | 單元測試 | 驗證 `Tester` `_TestRunConfig` 與 `_execute_single_module_in_sandbox` 單一/平行測試管線 | FR-06 | `python yscb.py dev test dev -k "TestDevTester"` |
| **FT-06** | 單元/邊界測試 | 驗證 `Checker` 扁平化 AST 檢查（巢狀 $\le 3$ 層）、`def <cmd>(cmd_bags)` 契約與 `SyntaxError` 結構化攔截 | FR-07, EC-05, NFR-02 | `python yscb.py dev test dev -k "TestDevChecker"` |
| **FT-07** | 單元/邊界測試 | 驗證 `resolve_module_dependency_order` 拓撲排序、循環依賴 `CyclicDependencyError` 攔截與 `contract.py` 合約測試 | FR-08, EC-04, NFR-03 | `python yscb.py dev test dev -k "test_release_all_kahn_dag"` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-07** | `Passed` | `dev@1.1.2.build` 打包安裝完成，`python yscb.py dev check dev` (`PASSED`) 與 `python yscb.py dev test dev -q` 全數通過 (`Pass: 80(100.0%), Fail: 0, Skip: 0`) | 2026-10-31 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 待 5 個子計畫全數進入 P06 後，由主 Agent 統一執行 `dev build`、`install @build` 與全系統 `dev test --all` 驗收 | `Pending` | 待驗收 |
