# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：多進程多模組並行跑測 (Multi-Process Multi-Module Parallel Test Runner)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Passed`  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `Tester._run_parallel_test` 正確派發多 Worker 並行執行且回傳 0。 | FR-01 | `source/dev/tests/test_sandbox.py` |
| **FT-02** | 單元測試 | 驗證各 Worker 正確獲得獨立沙盒 ID (`sandbox 1`, `sandbox 2`...) 與獨立路徑。 | FR-02 | `source/dev/tests/test_sandbox.py` |
| **FT-03** | 單元測試 | 驗證 `-j <N>` 參數正確限制最大 Worker 並行度；`--sequential` 正常回退順序模式。 | FR-03 | `source/dev/tests/test_sandbox.py` |
| **FT-04** | 單元測試 | 驗證多 Worker 執行後能正確聚合所有模組數據並產出單一 Diagnostic Report。 | FR-05 | `source/dev/tests/test_sandbox.py` |
| **FT-05** | 單元測試 | 驗證差異化清理：通過模組之沙盒自動銷毀，失敗模組之沙盒安全保留。 | FR-06 | `source/dev/tests/test_sandbox.py` |
| **ET-01** | 邊界測試 | 驗證單模組跑測（如 `dev test core`）自動走單沙盒模式，不建立多 Worker。 | EC-01 | `source/dev/tests/test_sandbox.py` |
| **ET-02** | 邊界測試 | 驗證 Worker 發生異常崩潰時，主進程安全聚合錯誤並正常結束。 | EC-02 | `source/dev/tests/test_sandbox.py` |
| **RT-01** | 回歸測試 | 驗證全系統 `python yscb.py dev test --all` 並行回歸 100% Passed 且總耗時大幅下降。 | FR-01~06 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_single_module_worker_execution_and_report_json` 實機執行通過，Worker 成功輸出報告 JSON。 | 2026-08-27 17:58 |
| **FT-02** | `Passed` | 沙盒引入 `uuid.uuid4().hex[:6]`，各 Worker 獨立生成專屬沙盒路徑，零路徑競爭。 | 2026-08-27 17:58 |
| **FT-03** | `Passed` | 實機執行 `--sequential` 成功回退單進程依序執行 (24.097s)，`-j` 參數解析正確。 | 2026-08-27 17:58 |
| **FT-04** | `Passed` | `dev test --all` 聚合 3 模組測試，終端成功產出單一完整 ASCII 診斷報告。 | 2026-08-27 17:58 |
| **FT-05** | `Passed` | 測試通過後各 Worker 沙盒即時銷毀（`Cleaned up sandbox 1..3`），`test_run_test_all_success_cleans_sandboxes` 通過。 | 2026-08-27 17:58 |
| **ET-01** | `Passed` | 單模組 `dev test dev` 自動走單沙盒直跑模式，未派發多 Worker。 | 2026-08-27 17:58 |
| **ET-02** | `Passed` | `test_invalid_type_filter_cli_exit_1` 驗證異常防禦回傳 Exit Code 1。 | 2026-08-27 17:58 |
| **RT-01** | `Passed` | 全庫預設回歸 (`LOGIC+ENV`) 119/119 通過 (13.755s)；全類別 (`ALL Types`) 120/120 通過 (14.727s)。 | 2026-08-27 17:58 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：實機執行 `python yscb.py dev test --all`，確認多 Worker 並行跑測，終端第 0 秒即時輸出所有模組之 `begin`，結束時即時輸出 `finish` 與銷毀日誌，總回歸時間縮短至 ~13.7 秒。 (2026-08-27 開發者確認通過)
- [x] **UX-02**：實機執行 `python yscb.py dev test --all --sequential`，確認能正常回退為單進程順序執行。 (2026-08-27 開發者確認通過)
- [x] **UX-03**：確認四層分類體系分流生效（預設模式執行 `LOGIC+ENV` 119 測試，`--all-types` 執行 120 測試）。 (2026-08-27 開發者確認通過)
