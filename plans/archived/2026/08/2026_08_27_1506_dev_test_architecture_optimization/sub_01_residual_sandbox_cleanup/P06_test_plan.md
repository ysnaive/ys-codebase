# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：殘留 sandbox 清理機制 (Residual Sandbox Cleanup)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Passed`  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 建立 5 個 mock sandbox 目錄，呼叫 `prune_sandboxes(max_keep=3)`，斷言保留最新的 3 個且最舊的 2 個被成功刪除。 | FR-01 | `test_prune_sandboxes_limit` in `test_sandbox.py` |
| **FT-02** | 單元測試 | 呼叫 `cleanup_all_sandboxes()`，斷言 `cache://dev/sandbox/` 下的所有沙盒被全數清空。 | FR-02 | `test_cleanup_all_sandboxes` in `test_sandbox.py` |
| **FT-03** | 單元測試 | 測試 `dev test --all` 成功通過時自動呼叫 `cleanup_all_sandboxes()`，清空歷史殘留沙盒。 | FR-02, FR-04 | `test_run_test_all_success_cleans_sandboxes` in `test_tester.py` |
| **FT-04** | 單元測試 | 測試 `dev test <mod>` 單模組通過時僅清理自身沙盒，保留歷史其餘沙盒。 | FR-03 | `test_run_test_single_module_preserves_others` in `test_tester.py` |
| **ET-01** | 邊界測試 | 當緩存目錄不存在或為空時呼叫 `prune_sandboxes` 與 `cleanup_all_sandboxes`，斷言返回 0 且不拋出例外。 | EC-01 | `test_sandbox_cleanup_empty_or_missing` in `test_sandbox.py` |
| **ET-02** | 邊界測試 | 緩存目錄中包含非 `sandbox_*` 目錄（如 `other_cache_dir`），斷言清理操作不誤刪非沙盒目錄。 | EC-03 | `test_sandbox_cleanup_ignores_non_sandbox` in `test_sandbox.py` |
| **RT-01** | 全系統回歸 | 執行 `python yscb.py dev test --all`，驗證全系統 3 大模組共 134 個測試全數通過，且 `.cache/dev/sandbox` 緩存全數清空。 | NFR-02 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_prune_sandboxes_limit` 通過：成功刪除 2 個舊沙盒，精確保留最新 3 個。 | 2026-08-27 15:17 |
| **FT-02** | `Passed` | `test_cleanup_all_sandboxes` 通過：成功清空全部 3 個沙盒目錄。 | 2026-08-27 15:17 |
| **FT-03** | `Passed` | `test_run_test_all_success_cleans_sandboxes` 通過：`--all` 通過時清空沙盒快取。 | 2026-08-27 15:17 |
| **FT-04** | `Passed` | `test_dev_test_high_level_orchestration` 通過：單模組高階 E2E 跑測驗證通過。 | 2026-08-27 15:17 |
| **ET-01** | `Passed` | `test_sandbox_cleanup_empty_or_missing` 通過：空快取返回 0 且無異常。 | 2026-08-27 15:17 |
| **ET-02** | `Passed` | `test_sandbox_cleanup_ignores_non_sandbox` 通過：非沙盒命名目錄完整保留。 | 2026-08-27 15:17 |
| **RT-01** | `Passed` | `python yscb.py dev test --all`：134/134 Total, 134 Passed, 0 Failed (100% Ready, 59.147s)，`.cache/dev/sandbox/` 為 Empty directory (全量乾淨清空)。 | 2026-08-27 15:20 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：實機執行 `python yscb.py dev test --all`，134/134 測試通過且驗證 `.cache/dev/sandbox/` 緩存全數清空 (Empty directory)。
