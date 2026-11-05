# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：2026_11_05_0826_file_space_foundation_research  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Medium)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `FileSpaceConfig` 預編譯過濾器對精確段名（`.git`）、含 `/` 前綴（`ys_codebase/.modules`）、`**/` 零層與多層目錄萬用字元（`**/.storage.local/**`）及副檔名之語意 100% 等價 | FR-01, EC-01 | `python yscb.py dev test --target=file-space:TestFileSpaceManager.test_ft04_precompiled_filter_equivalence_and_zero_depth_glob` |
| **FT-02** | 單元測試 | 驗證 `FileSpaceManager.iter_space_files_with_stat` 產出 6 元組 `(rel_path, abs_path, src_root, mtime_ns, ctime_ns, size)`、多重重疊 `include` 去重與 `override_mode="replace"` | FR-01, FR-08, EC-02 | `python yscb.py dev test --target=file-space:TestFileSpaceManager.test_ft05_iter_space_files_with_stat_and_override_mode_replace` |
| **FT-03** | 單元測試 | 驗證 `ctime_ns > mtime_ns`（如 `os.utime` 回溯時間戳）首次掃描後不再觸發永久 `is_racy=True` 重算雜湊，且刪除後重建檔案保留原 `created_gen` | FR-06, NFR-01 | `python yscb.py dev test --target=file-space:TestFingerprintScannerSelfHealing.test_ft_03_backdated_mtime_no_permanent_racy_and_tombstone_resurrection` |
| **FT-04** | 單元/邊界測試 | 驗證 `FingerprintScanner.patch_space_files` $O(\|\text{dirty}\|)$ 局部增刪改更新、`notify_file_event` 前置 `.git` 過濾、以及目錄刪除事件觸發 `_full_rescan_spaces` 清除幽靈項目与 `LAZY_STABILIZED` 路徑追蹤 | FR-02, EC-03, EC-04 | `python yscb.py dev test --target=file-space:TestFingerprintScannerSelfHealing.test_ft_04_patch_space_files_and_watcher_directory_move_delete_guard` |
| **FT-05** | 單元/邊界測試 | 驗證 `is_watcher_active(project_root, space_name)` 對 `watcher_state.json` (`watchdog_running`) 與空間 `watch=False` 之精確識別，以及 `_diff_all_spaces()` 動態聚合子空間世代 | FR-03, FR-07, EC-05 | `python yscb.py dev test --target=file-space:TestFingerprintScannerSelfHealing.test_ft_05_watcher_state_awareness_and_diff_all_spaces_aggregation` |
| **FT-06** | 單元/邊界測試 | 驗證 `gdrive-support` 雲端 Level 1 拓撲序多層新建子目錄（0 次 `list_files`）、刪除子目錄連動清理跨分支 Shortcut、雲端根目錄新分支退回 Level 2（`test_et_06`）與本地零冗餘 `stat` 快照收集 | FR-04, FR-05, EC-06, EC-07, EC-08, NFR-02 | `python yscb.py dev test --target=gdrive-support:TestGDriveBranchAndSyncEngine.test_ft_13_level1_topological_nested_subdirs_removal_shortcut_purge_and_zero_stat_snapshot` |
| **RT-01** | 回歸測試 | 執行 `file-space`、`gdrive-support`、`ast`、`knowledge-db` 四大模組全量單元與回歸測試套件與 `dev check` 合規守門 | NFR-03 | `python yscb.py dev test file-space -q --sync && python yscb.py dev test gdrive-support -q --sync && python yscb.py dev test ast -q --sync && python yscb.py dev test knowledge-db -q --sync` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft04_precompiled_filter_equivalence_and_zero_depth_glob` 100% 通過 | 2026-11-05 |
| **FT-02** | `Passed` | `test_ft05_iter_space_files_with_stat_and_override_mode_replace` 100% 通過 | 2026-11-05 |
| **FT-03** | `Passed` | `test_ft_03_backdated_mtime_no_permanent_racy_and_tombstone_resurrection` 100% 通過（二次掃描 `compute_file_hash` 呼叫次數為 0） | 2026-11-05 |
| **FT-04** | `Passed` | `test_ft_04_patch_space_files_and_watcher_directory_move_delete_guard` 100% 通過 | 2026-11-05 |
| **FT-05** | `Passed` | `test_ft_05_watcher_state_awareness_and_diff_all_spaces_aggregation` 100% 通過 | 2026-11-05 |
| **FT-06** | `Passed` | `test_ft_13_level1_topological_nested_subdirs_removal_shortcut_purge_and_zero_stat_snapshot` 100% 通過（多層新子目錄與刪除子目錄均命中 Level 1，`list_files` 呼叫 0 次，本地快照 0 次冗餘 `Path.stat()`） | 2026-11-05 |
| **RT-01** | `Passed` | 四大模組全量回歸 100% 通過：`file-space` (22/22)、`gdrive-support` (31/31)、`ast` (27/27)、`knowledge-db` (109/109)，且 `dev check` 全數 `PASSED` | 2026-11-05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python yscb.py file-space status` 與 `python yscb.py gdrive sync`，驗證本地空間掃描與雲端 Level 0/1 增量同步端到端耗時由原本 `33~40s` 顯著下降至秒級且狀態一致 | `[測試通過]` | 開發者確認通過（2026-11-05） |

