# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Agents-Workflow Release 預設 Local 模式、Gitignore 軟合併同步與 Core Config 來源層級探測 (Release Local Mode, Gitignore Sync & Core Config Origin Inspection)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_05)  
> 狀態：Passed  
> 模板版本：v1.3  


---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `core.config.get_raw()` 單層原始未合併讀取能力 | FR-01 | `test_config_get_raw_project_and_local` |
| **FT-02** | 單元測試 | `core.config.inspect()` 來源層級診斷與覆蓋狀態 | FR-01 | `test_config_inspect_origin_and_overridden` |
| **FT-03** | 單元測試 | `ReleaseTargetManager.add_target()` 預設寫入 Local 組態 | FR-02 | `test_release_target_add_default_local` |
| **FT-04** | 單元測試 | `ReleaseTargetManager.add_target(is_project=True)` 寫入 Project 組態 | FR-02 | `test_release_target_add_project_mode` |
| **FT-05** | 單元測試 | `ReleaseTargetManager.list_targets()` 多層來源標註 (`[LOCAL]`, `[PROJECT]`, `[BOTH]`) | FR-03 | `test_release_target_list_multi_tier` |
| **FT-06** | 單元測試 | CLI `release-target --add / --remove` 支援 `--proj` 旗標切換 | FR-04 | `test_cli_release_target_proj_flag` |
| **FT-07** | 單元測試 | `ReleasePublisher.sync_gitignore()` 軟合併建立與非破壞性更新 | FR-05 | `test_publisher_sync_gitignore_soft_merge` |
| **FT-08** | 單元測試 | `ReleasePublisher` 複合來源 Targets 聯集發布 | FR-06 | `test_publisher_release_union_targets` |
| **ET-01** | 異常測試 | `.gitignore` 不存在或無結尾換行時安全補齊建立 | EC-01 | `test_publisher_sync_gitignore_edge_cases` |
| **ET-02** | 異常測試 | 同一 Target 於 Local 與 Project 同時啟用之去重處置 | EC-02 | `test_release_target_both_enabled` |
| **RT-01** | 回歸測試 | 全生態系 4 大核心模組沙盒回歸測試 | NFR-01 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 成功驗證 `core.config.get_raw()` 專案與本機單層讀取 | 2026-08-28 20:39 |
| **FT-02** | `Passed` | 成功驗證 `core.config.inspect()` source 與 is_overridden 診斷 | 2026-08-28 20:39 |
| **FT-03** | `Passed` | 成功驗證 `ReleaseTargetManager.add_target()` 預設寫入 Local | 2026-08-28 20:39 |
| **FT-04** | `Passed` | 成功驗證 `is_project=True` 寫入 Project 組態 | 2026-08-28 20:39 |
| **FT-05** | `Passed` | 成功驗證 `list_targets()` 來源標註 (`[LOCAL]`, `[PROJECT]`, `[BOTH]`) | 2026-08-28 20:39 |
| **FT-06** | `Passed` | 成功驗證 CLI `--proj` / `--project` 旗標切換與彩色排版 | 2026-08-28 20:39 |
| **FT-07** | `Passed` | 成功驗證 `sync_gitignore()` 軟合併、標記區塊維護與自訂規則 100% 保留 | 2026-08-28 20:39 |
| **FT-08** | `Passed` | 成功驗證 `ReleasePublisher` 複合來源 Targets 聯集發布 | 2026-08-28 20:39 |
| **ET-01** | `Passed` | 成功驗證 `.gitignore` 不存在時新建與末行無換行時補齊追加 | 2026-08-28 20:39 |
| **ET-02** | `Passed` | 成功驗證同一 Target 雙重啟用時之去重處置 | 2026-08-28 20:39 |
| **RT-01** | `Passed` | 全生態系 4 大核心模組沙盒測試 181/181 100% Passed (14.589s) | 2026-08-28 20:39 |


---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01 (CLI release-target 預設 Local 與 `--proj` 手感體驗)**：
  - 實機執行 `python yscb.py agents-workflow release-target --list`、`--add <t>`、`--add <t> --proj` 與檢查 `.gitignore` 軟合併內容（已實機驗收通過，成功遷移既有 target 至 Local）。

