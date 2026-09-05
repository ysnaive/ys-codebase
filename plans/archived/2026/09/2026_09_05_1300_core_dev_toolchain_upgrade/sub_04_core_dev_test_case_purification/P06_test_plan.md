# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：core_dev_test_case_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `test_tester.py` 整合吸收 sync 與 throttle 邏輯，舊零散檔案刪除後全通 | FR-01 | `python yscb.py dev test dev -k test_tester` |
| **FT-02** | 單元測試 | 驗證 Core 測試整併：`test_cli_router.py` 整合 help/guild；`test_contributes.py` 整合 jit；`test_pip_manager_sdk.py` 精簡收斂 | FR-02 | `python yscb.py dev test core -k "test_cli_router or test_contributes or test_pip_manager_sdk"` |
| **FT-03** | 整合測試 | 驗證 `@require(Requirement.WORKFLOW)` 標註案例在 `--type=workflow` 模式下能被精準識別並執行 | FR-03 | `python yscb.py dev test dev --type=workflow` |
| **FT-04** | 回歸測試 | 驗證全量模式（`--all-types`）下所有 LOGIC, ENV 與 WORKFLOW 測試 100% 通過，0 邏輯遺失 | FR-04 | `python yscb.py dev test dev --all-types; python yscb.py dev test core --all-types` |
| **ET-01** | 邊界測試 | 驗證測試分類過濾器（Taxonomy Filter）在各組合旗標下排他性與包含性完全精確 | EC-01 | `test_filter_suite_taxonomy_and_target` |
| **ET-02** | 邊界測試 | 驗證舊測試檔刪除後，`TestDiscovery` 與 Auto-Contract 動態合成 100% 正常，無殘留路徑例外 | EC-02 | `test_discovery_and_suite_building` |
| **RT-01** | 效能回歸 | 驗證預設模式（LOGIC + ENV）日常測試耗時顯著下降（目標 $\le 4.5\text{s}$） | NFR-01 | `python yscb.py dev test dev --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Pass: 74(100.0%), Fail: 0, Skip: 0`；sync/throttle 吸收至 `test_tester.py` 驗證完整通過 | 2026-09-05 |
| **FT-02** | `Passed` | `Pass: 119(100.0%), Fail: 0, Skip: 0`；`test_cli_router.py`、`test_contributes.py`、`test_pip_manager_sdk.py` 整合通過 | 2026-09-05 |
| **FT-03** | `Passed` | 實體沙盒案例（`test_sandbox.py` 與 `test_engine.py`）標註 WORKFLOW 正常分流 | 2026-09-05 |
| **FT-04** | `Passed` | dev: 80/80 (9.58s) 全數通過；core: 121/121 (20.29s) 全數通過，0 邏輯遺失 | 2026-09-05 |
| **ET-01** | `Passed` | `test_filter_suite_taxonomy_and_target` 驗證 4-Tier 分流與 target pinning 完全正確 | 2026-09-05 |
| **ET-02** | `Passed` | 舊測試檔刪除後，Auto-Contract 與 `TestDiscovery` 兩階段探索引擎 100% 正常 | 2026-09-05 |
| **RT-01** | `Passed` | dev `--quiet` 測試耗時顯著降至 ~2.8s，core 預設快測僅 ~4s，大幅提升日常回饋速度 | 2026-09-05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python yscb.py dev test dev --quiet`，確認預設秒級返回且 100% 通過 | `[測試通過]` | 開發者實機確認通過 |
| **UX-02** | 實機執行 `python yscb.py dev test dev --all-types`，確認 WORKFLOW 重型測試完整保留並全數通過 | `[測試通過]` | 開發者實機確認通過 |
