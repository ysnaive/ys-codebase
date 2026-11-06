# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_09_gdrive_support 同步刪除邊界防護、空目錄清理條件收斂與 WAL 狀態持久化優化  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `push --delete` 與 `pull --delete` 在 `base is None` 時預設不刪除未追蹤新檔（僅 `force=True` 時強制刪除），且 `base is not None` 時正常刪除 | FR-01, NFR-02 | `TestGDriveBranchAndSyncEngine.test_ft_15_untracked_delete_guard_restored_folder_scan_and_wal_journal_replay` |
| **FT-02** | 單元測試 | 驗證 `_prune_empty_remote_branch_dirs` 在 `deleted_remote` 為空時不誤刪雲端新建空資料夾，且還原/新目錄僅有 folder ChangeRecord 時自動降級至 Level 2 掃描找回子檔案 | FR-02, EC-02 | `test_ft_14_audit_remediation_*` & `test_ft_15_untracked_delete_guard_*` |
| **FT-03** | 單元測試 | 驗證 Stage 3 透過 `sync_state.journal.jsonl` 執行逐檔 WAL 追加、僅於 `finally` 執行單次全量 `sync_state.json` 寫入，且 `_load_local_state` 自動 Replay 未結算 journal（並忽略末尾截斷損毀行） | FR-03, EC-01, NFR-01 | `TestGDriveBranchAndSyncEngine.test_ft_15_untracked_delete_guard_restored_folder_scan_and_wal_journal_replay` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Summary : 34 Total, 34 Passed, 0 Failed, 0 Skipped (4.493s)` | 2026-11-06 |
| **FT-02** | `Passed` | `Summary : 34 Total, 34 Passed, 0 Failed, 0 Skipped (4.493s)` | 2026-11-06 |
| **FT-03** | `Passed` | `Summary : 34 Total, 34 Passed, 0 Failed, 0 Skipped (4.493s)` | 2026-11-06 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 確認 `gdrive-support` 全部 34 項單元與合約測試通過、`dev check` 0 FAIL / 0 WARN，且 WAL `sync_state.journal.jsonl` 與單向 `--delete` 基線保護符合預期 | `[跳過/免測]` | 開發者授權免測結案 |

