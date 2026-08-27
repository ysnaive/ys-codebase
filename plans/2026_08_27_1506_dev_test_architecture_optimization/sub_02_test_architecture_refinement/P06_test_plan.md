# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：測試架構完善 (Test Architecture Refinement)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Passed`  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `Requirement.ISOLATED_SANDBOX` 列舉值與 Flag 組合運算正常。 | FR-01 | `source/dev/tests/test_case.py` |
| **FT-02** | 單元測試 | 驗證預設共用沙盒機制（同類別測試共用同一個 `sandbox_dir`）。 | FR-02 | `source/dev/tests/test_case.py` |
| **FT-03** | 單元測試 | 驗證 `@require(Requirement.ISOLATED_SANDBOX)` 獨立沙盒建立與自動清理。 | FR-02 | `source/dev/tests/test_case.py` |
| **FT-04** | 單元測試 | 驗證 `YSCB_TEST_SANDBOX=1` 時 `core.uri.reconcile_undefined_uri` 與 `resolve` 自動靜默拋出 `UndefinedURIError`。 | FR-03, FR-04 | `source/core/tests/test_uri.py` |
| **FT-05** | 單元測試 | 驗證 `YSCBTestCase.run_cli` 子行程中自動透傳 `YSCB_TEST_SANDBOX=1`。 | FR-03 | `source/dev/tests/test_case.py` |
| **ET-01** | 邊界測試 | 驗證同一類別內混合共用測試與獨立沙盒測試時狀態不互相污染。 | EC-01 | `source/dev/tests/test_case.py` |
| **ET-02** | 邊界測試 | 驗證非測試環境（未設 `YSCB_TEST_SANDBOX`）且為非 TTY 時拋出 `UndefinedURIError`。 | EC-03 | `source/core/tests/test_uri.py` |
| **RT-01** | 回歸測試 | 執行 `dev test core` (70/70) 與 `dev test dev` (41/41) 確保全部既有與新增測試 100% 通過。 | EC-04, NFR-02 | `python yscb.py dev test dev` |
| **RT-02** | 全量回歸 | 執行 `dev test --all` 確保全系統（`core`, `dev`, `agents-workflow` 共 141 個測試）100% 通過。 | EC-04, NFR-01 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_requirement_isolated_sandbox_flag` 通過，Flag 位元 OR 組合正確 | 2026-08-27 15:50 |
| **FT-02** | `Passed` | `test_shared_and_isolated_sandbox_dispatch` 通過，共用方法沙盒路徑一致 | 2026-08-27 15:50 |
| **FT-03** | `Passed` | `test_shared_and_isolated_sandbox_dispatch` 通過，獨立方法取得專屬沙盒 | 2026-08-27 15:50 |
| **FT-04** | `Passed` | `test_test_sandbox_env_suppresses_jit_interaction` 通過，靜默拋出 `UndefinedURIError` | 2026-08-27 15:47 |
| **FT-05** | `Passed` | `test_dev_test_high_level_orchestration` 通過，子行程成功透傳 `YSCB_TEST_SANDBOX` | 2026-08-27 15:50 |
| **ET-01** | `Passed` | 同一類別內混合共用與獨立測試方法完全無污染 | 2026-08-27 15:50 |
| **ET-02** | `Passed` | `test_project_root_undefined_raises_undefined_uri_error` 通過 | 2026-08-27 15:47 |
| **RT-01** | `Passed` | `dev test core` (70/70) + `dev test dev` (41/41) 全數 100% 通過 | 2026-08-27 15:50 |
| **RT-02** | `Passed` | `dev test --all` 141 Total, 141 Passed, 0 Failed (100% Ready) | 2026-08-27 15:51 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：實機執行 `python yscb.py dev test --all`，確認跑測總耗時大幅降低，且全程無任何鍵盤 JIT 互動打斷。
