# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：`module:gdrive-support` 雲端分支管理機制、三方對帳與雙向同步引擎 (`sub_02_branch_and_sync_engine`)  
> 建立日期：2026-11-04  
> 所屬主計畫：`2026_11_04_0858_gdrive_bidirectional_sync_module`  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `reconciler.py` 100% 無狀態三方對帳 8 態輸出與 `.history/` 跨分支引用計數計算 | FR-01, NFR-01, NFR-02 | `TestGDriveBranchAndSyncEngine.test_ft_01_stateless_reconciler_8_states_and_history_ref_counts` |
| **FT-02** | 整合測試 | 驗證 `init_repo()` 建立 `.yscb_gdrive.json`、`README.md`、`.history/`、`.trash/` 與 `main/` | FR-02 | `TestGDriveBranchAndSyncEngine.test_ft_02_init_repo_and_readme_generation` |
| **FT-03** | 整合測試 | 驗證 `branch create` Shortcut 建立、`main` 更新時 Copy-on-Write 移入 `.history/` 保全舊分支內容凍結、以及 `branch delete` 後無引用 `.history/` 檔案自動移入 `.trash/` GC | FR-03, FR-04 | `TestGDriveBranchAndSyncEngine.test_ft_03_branch_shortcut_cow_history_and_unreferenced_gc_to_trash` |
| **FT-04** | 整合測試 | 驗證 `checkout_branch()` 原子切換工作樹、拉取目標分支檔案並清理舊分支獨有本地受管檔 | FR-03 | `TestGDriveBranchAndSyncEngine.test_ft_04_checkout_branch_worktree_alignment_and_orphan_cleanup` |
| **FT-05** | 單元測試 | 驗證 `GDriveSyncServiceWorker` 在 `auto_sync=False` 時保持 `standby` 且 `health_check() -> True`，以及 `stop()` 確定性呼叫 `_unsubscribe()` | FR-05 | `TestGDriveBranchAndSyncEngine.test_ft_05_service_worker_standby_health_and_unsubscribe_on_stop` |
| **ET-01** | 邊界測試 | 驗證非空且缺少 `.yscb_gdrive.json` 之雲端根目錄執行同步時拋出 `GDriveRepoUninitializedError` | EC-01 | `TestGDriveBranchAndSyncEngine.test_et_01_non_empty_uninitialized_remote_root_aborts_sync` |
| **ET-02** | 邊界測試 | 驗證雙向 `sync` 遇衝突按檔隔離保留不覆寫（回傳 `exit_code=2`）且其餘無衝突檔照常同步，以及 `pull --force --backup` 建立 `.conflict.<ts>.bak` | EC-02 | `TestGDriveBranchAndSyncEngine.test_et_02_conflict_isolation_in_sync_vs_force_backup_resolution` |
| **ET-03** | 邊界測試 | 驗證本地存在未同步修改時執行 `checkout` 拋出 `GDriveDirtyWorktreeError` | EC-03 | `TestGDriveBranchAndSyncEngine.test_et_03_dirty_worktree_blocks_checkout_without_force` |
| **ET-04** | 邊界測試 | 驗證批次同步中途失敗時，已完成檔案之狀態已透過 `try/finally` 增量落盤至 `sync_state.json` | EC-04 | `TestGDriveBranchAndSyncEngine.test_et_04_stabilization_window_and_incremental_state_commit_on_mid_sync_failure` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01 ~ FT-05** | `Passed` | `python yscb.py dev check gdrive-support` (PASSED) & `python yscb.py dev test gdrive-support -q` (`Pass: 20(100.0%), Fail: 0, Skip: 0`) | 2026-11-04 10:13 |
| **ET-01 ~ ET-04** | `Passed` | 100% 基於 `LocalSandboxTransport` 驗證通過，零外部 Google Drive API test cases | 2026-11-04 10:13 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 確認 `sub_02_branch_and_sync_engine` 之 Shortcut 差量分支、`.history/` CoW 與無引用自動回收至 `.trash/`、三方對帳及 `service.py` 成果 | `[跳過/免測]` | 開發者指示與 `sub_01` 相同標記 `[跳過/免測]`，併入 `sub_03_live_gdrive_verification` 統一驗證 |

