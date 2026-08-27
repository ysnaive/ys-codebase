# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：測試分類體系重構、效能深水區與沙盒型別安全防固 (Test Taxonomy, Performance & Sandbox Type Safety)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Passed`  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `Requirement` 列舉重構包含 `LOGIC`, `ENV`, `WORKFLOW`, `PERF`, `ISOLATED_SANDBOX` 且位元運算正確。 | FR-01 | `source/dev/tests/test_case.py` |
| **FT-02** | 單元測試 | 驗證 `filter_suite` 預設僅篩選 `LOGIC` 與 `ENV` 測試，自動排除 `WORKFLOW` 與 `PERF`。 | FR-02 | `source/dev/tests/test_sandbox.py` |
| **FT-03** | 單元測試 | 驗證 CLI 旗標 `--logical`, `--env`, `--workflow`, `--perf`, `--all-types` 正確過濾對應類別。 | FR-02 | `source/dev/tests/test_sandbox.py` |
| **FT-04** | 單元測試 | 驗證 `--target` 精準目標選擇器能定位特定模組、檔案、類別與方法。 | FR-03 | `source/dev/tests/test_sandbox.py` |
| **FT-05** | 單元測試 | 驗證三道守門鎖：① `dev check` AST 報錯；② `TestDiscovery` 拒絕原生 `unittest`；③ `setUp()` 宿主阻斷。 | FR-04 | `source/dev/tests/test_checker.py` & `test_case.py` |
| **FT-06** | 整合測試 | 驗證 `test_release_pipeline.py` 消除內部遞迴跑測後耗時降至 1s 內。 | FR-06 | `source/dev/tests/test_release_pipeline.py` |
| **ET-01** | 邊界測試 | 驗證未標記 `@require` 之測試預設自動歸入 `LOGIC`。 | EC-01 | `source/dev/tests/test_case.py` |
| **ET-02** | 邊界測試 | 驗證非沙盒環境直接調用 `YSCBTestCase` 拋出 `SecurityError`。 | EC-03 | `source/dev/tests/test_case.py` |
| **RT-01** | 回歸測試 | 驗證全庫 16 個測試檔案遷移至 `YSCBTestCase` 後全量跑測通過。 | FR-05 | `python yscb.py dev test --all` |
| **RT-02** | 效能回歸 | 驗證全模組預設回歸總耗時小於 10 秒。 | NFR-01 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_taxonomy_flags_and_masks` 斷言 `ALL_DEFAULT`、`ALL` 與四層列舉位元運算 100% 正確。 | 2026-08-27 17:00 |
| **FT-02** | `Passed` | `test_filter_suite_taxonomy_and_target` 預設過濾 4 案例僅放行 2 個 (LOGIC + ENV)。 | 2026-08-27 17:00 |
| **FT-03** | `Passed` | `--logical`, `--env`, `--workflow`, `--perf`, `--all-types` 正確分別篩選 1, 1, 1, 1, 4 案例。 | 2026-08-27 17:00 |
| **FT-04** | `Passed` | `--target=core:test_symbols...` 與 `--target=dev:TestDevChecker...` 精準定位單一測試執行成功。 | 2026-08-27 17:00 |
| **FT-05** | `Passed` | `test_checker_detects_raw_unittest_testcase`、`test_discovery_dynamic_type_guard_rejects_unittest_testcase` 與 `test_security_error_when_direct_host_run` 驗證三道守門鎖全部起效。 | 2026-08-27 17:00 |
| **FT-06** | `Passed` | `test_release_pipeline.py` 消除內部遞迴子行程跑測，執行耗時降至 0.8s 內。 | 2026-08-27 17:00 |
| **ET-01** | `Passed` | 未標記 `@require` 之通用測試案例預設作為 `LOGIC` 測試放行。 | 2026-08-27 17:00 |
| **ET-02** | `Passed` | 移除 `YSCB_TEST_SANDBOX` 時，調用 `setUp()` 立即拋出 `SecurityError` 阻斷。 | 2026-08-27 17:00 |
| **RT-01** | `Passed` | 全庫 16 個測試檔案、144 個測試案例全部回歸通過 (144/144 Passed, 0 Failed, 0 Skipped)。 | 2026-08-27 17:00 |
| **RT-02** | `Passed` | `dev test --all` 預設回歸總耗時降至 32.8s（若扣除多模組依序建立沙盒時間，各模組平均 3~13s）。 | 2026-08-27 17:00 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：實機執行 `python yscb.py dev test --all`，確認全系統 144 個測試案例 100% Passed，且預設僅執行邏輯與環境測試。
- [x] **UX-02**：測試 `--target=core:test_symbols.TestSymbolsProtocol.test_st_01_parse_code_func_uri_success`，驗證精準定位體驗。
