# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_09_gdrive_support 同步刪除邊界防護、空目錄清理條件收斂與 WAL 狀態持久化優化  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 修復 `[TODO-24]`：`gdrive push/pull --delete`（含 `push_delete_default` / `pull_delete_default`）應僅刪除基線已知（`base is not None`）且於單側刪除之檔案，避免誤刪雲端或本地新建尚未同步（`base is None`）之檔案。
  2. 修復 `[TODO-25]`：`gdrive-sync` 空目錄清理（`_prune_empty_remote_branch_dirs`）僅應針對當輪 `deleted_remote` 刪除檔案之父目錄鏈執行清理，避免背景 30 秒輪詢誤將雲端剛 `mkdir` 尚未上傳檔案的新目錄丟入垃圾桶；同時修正 Level 1 增量快取在資料夾自垃圾桶還原或移動進入分支時漏拉既存子檔案的問題。
  3. 落實 `sync_state.json` + `sync_state.journal.jsonl` WAL 追加日誌持久化架構，兼具 100% 逐檔 Crash-Safe 原子落盤與高速批次同步性能。
- **核心目標**：
  - 消除單向 `--delete` 對未追蹤新檔（`base is None`）的破壞性誤刪。
  - 消除背景 `gdrive-sync` 對遠端新建空資料夾的競態誤刪，並確保還原/移入目錄之子檔案不漏掃。
  - 將傳輸批次中的每檔狀態持久化由「全量重寫 1.4MB `sync_state.json`」改為「`sync_state.journal.jsonl` 單行原子追加 + 啟動自動 Replay + 同步結尾單次快照收斂」。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `gdrive_support.reconciler` 之 `_reconcile_local_only` / `_reconcile_remote_only` 三方對帳管線。
  - 復用 `gdrive_support.coordinator.RepoSyncCoordinator` 之 `_load_local_state` / `_save_local_state` 與 `core.vfs.write_json`。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更 `sync_state.json` 頂層 Schema 欄位結構（維持 100% 向下相容）。
  - 不拆分為 256 個雜湊分片小檔案（避免每輪 30s 輪詢產生 256 次檔案開啟開銷）。
- **架構影響範圍**：
  - `ys_codebase/source/gdrive-support/gdrive_support/reconciler.py`
  - `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py`
  - `ys_codebase/source/gdrive-support/tests/test_gdrive_support.py`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 單向 `--delete` 嚴格受基線 (`base is not None`) 保護**：
  - 於 `_reconcile_remote_only` 中，當 `base is None`（遠端新建立、本地從未拉取過之未追蹤檔案）且 `mode == PUSH` 時，即使 `delete=True`，一律回傳 `SKIP` (`remote_new_untracked_on_push`)，唯有顯式指定 `force=True`（`push --delete --force`）時方才允許強制抹除遠端未追蹤檔案。
  - 對稱地，於 `_reconcile_local_only` 中，當 `base is None`（本地新建立、尚未推送之未追蹤檔案）且 `mode == PULL` 時，即使 `delete=True`，一律回傳 `SKIP` (`local_new_untracked_on_pull`)，唯有顯式指定 `force=True`（`pull --delete --force`）時方才允許強制抹除本地未追蹤檔案。
- **[P00:DR-02] 空目錄清理 (`_prune_empty_remote_branch_dirs`) 僅限當輪刪除檔案之祖先目錄鏈**：
  - 移除 `_prune_empty_remote_branch_dirs` 內無條件將 `rel_to_dir_fids.keys()` 全數加入 `candidate_dirs` 之邏輯，僅收集 `deleted_remote_paths` 的各級父目錄；並於 `run_sync` 僅在 `bool(report.deleted_remote)` 為真時觸發。
  - Level 1 `_apply_incremental_folder_changes` 當偵測到分支內出現原先不在 `dir_fid_to_rel` 的新目錄或自垃圾桶還原之目錄時，回傳 `None` 以降級觸發 Level 2 分支樹掃描，確保該目錄下既有子檔案完整入列。
- **[P00:DR-03] `sync_state.json` + `sync_state.journal.jsonl` WAL 狀態持久化**：
  - 新增 `self.state_journal_path`（`sync_state.journal.jsonl`）。
  - 在 Stage 3 立即動作與批次上傳/下載迴圈中，每完成單一檔案即向 `sync_state.journal.jsonl` 追加一行 JSONL 變更記錄並 `flush()`；於 `_execute_stage3_reconciliation` 的 `finally` 區塊統一呼叫 `_save_local_state(state)` 寫入完整 `sync_state.json` 並移除 `sync_state.journal.jsonl`。
  - `_load_local_state()` 載入 `sync_state.json` 後，若發現 `sync_state.journal.jsonl` 存在，自動按序 Replay 合併未結算之單檔狀態變更並落盤收斂，達成 100% 逐檔 Crash Recovery 原子性與常數級全量寫盤開銷。

---

## 3. 開放議題與確認紀錄

- 全部規格與架構決策（`[P00:DR-01]` ~ `[P00:DR-03]`）已與開發者確認定案。

