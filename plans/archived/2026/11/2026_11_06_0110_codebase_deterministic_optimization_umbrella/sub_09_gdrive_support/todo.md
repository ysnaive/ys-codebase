# 計畫前置待辦來源清單 (Promoted TODOs)

> 主題：sub_09_gdrive_support  
> 建立日期：2026-11-06  
> 狀態：Active  
> 模型：Unknown  

---

## 立項待辦條目 (Promoted Items)

### [TODO-24] 修正 gdrive push/pull --delete 僅刪除基線已知(base!=None)且於單側刪除之檔案，避免誤刪未追蹤新檔
- **建立日期**：2026-11-05
- **目標範疇**：`ys_codebase/source/gdrive-support/gdrive_support/reconciler.py`
- **備忘與解法要點**：調整 _reconcile_remote_only 與 _reconcile_local_only：當 base is None 時，push/pull --delete 不應預設觸發 DELETE_REMOTE/DELETE_LOCAL (push_delete_untracked_remote / pull_delete_untracked_local)，應僅針對 base is not None 且單側刪除之已知追蹤檔案執行刪除（或要求顯式 --force 才清理 untracked）

### [TODO-25] 修正 gdrive-sync 空目錄清理 (_prune_empty_remote_branch_dirs) 誤刪雲端新建中目錄與 Level 1 父目錄 trashed=false 還原時子項漏拉問題
- **建立日期**：2026-11-05
- **目標範疇**：`ys_codebase/source/gdrive-support/gdrive_support/coordinator.py`
- **備忘與解法要點**：1. _prune_empty_remote_branch_dirs 僅應針對本次 deleted_remote 之父目錄鏈進行空目錄清理，嚴禁把全部 rel_to_dir_fids 無條件列入 candidate_dirs，避免背景輪詢撞上雲端剛 mkdir 尚在寫入檔案的新資料夾而誤丟垃圾桶；2. Level 1 _apply_incremental_folder_changes 偵測到目錄從垃圾桶還原或新建目錄時，需遞迴補抓或觸發子樹掃描避免漏拉子檔案
