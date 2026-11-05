# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Google Drive Changes API 增量快照與前景 CLI 優先搶占讓鎖機制 (GDrive Changes API Incremental Snapshot & CLI Lock Preemption)  
> 建立日期：2026-11-05  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 當 `server` 後端 `gdrive-sync` Worker 運行時，手動輸入 `python yscb.py gdrive push --force`（或 `sync`/`pull`）會因背景 Worker 長時間持有 `sync.lock`（掃描 2,218 個雲端檔案耗時 35~50 秒）而超過 30 秒等待時間報錯 `Could not acquire sync lock`。
  2. 為「前景 CLI 優先搶占背景 `gdrive-sync` 鎖」與「導入 Google Drive `changes` API (`changes.getStartPageToken` / `changes.list`) 增量感知與遠端快照快取」立項實作，並納入 `/blind-subagent` 反向證偽查出之 4 大加固對策。
- **核心目標**：
  1. **導入 Google Drive REST API v3 `changes` API 游標短路與遠端快照增量快取**：於 `AbstractSyncTransport`（含 `GoogleDriveApiTransport` 與 `LocalSandboxTransport`）實作 `get_start_page_token()` 與 `list_changes(page_token)`；於 `storage.local://gdrive-support/sync_state.json` 保存 `changes_page_token` 與完整遠端倉庫快取 (`remote_repo_cache`，涵蓋 `repo_meta`、各分支快照、目錄映射與 Shortcut `target_file_id` 索引）。當 `changes.list` 無雲端受管變更時，100% 免除 `_collect_remote_branch_snapshot`、`_read_remote_repo_meta`、`_reconcile_unregistered_cloud_branches`、`_flush_external_repo_trash` 與其他分支重掃（將背景輪詢與前景 `push`/`sync` 的雲端對帳耗時從 35~50 秒降至 **~0.2 秒**）。
  2. **輕量精準增量 Patch + 結構變動局部回退 + 零 TOCTOU 游標跳躍**：當 `changes.list` 僅包含已知受管檔案（或被 Shortcut 指向之 `target_file_id`）的內容更新/移除、或已知受管目錄下的新增非目錄檔案時，直接增量更新快取快照；當涉及新增/搬移資料夾、`.yscb_gdrive.json` 外部變更或未知父目錄時，自動退回單次安全全量刷新（且全量刷新必須在掃描**開始前**先取 `get_start_page_token()`，日常寫入後嚴禁盲目以 `get_start_page_token()` 覆蓋游標，避免跳過併發時間窗內之外部變更）。
  3. **前景 CLI 協同搶占讓鎖 (`cli_yield.signal`) 與單檔原子 CoW + 異常安全落盤**：前景 CLI 等鎖時寫入含 `{"pid": os.getpid(), "ts": time.time()}` 之 `cache://gdrive-support/cli_yield.signal`，取鎖成功瞬間立即清除，且背景 `should_yield()` 對超過 TTL (`120s`) 或死進程之孤兒訊號自動清理忽略；Stage 3 將 `PUSH_UPDATE` 之 CoW（移入 `.history/` 或刪除舊 Shortcut）與 `upload_file` 封裝為單檔原子工作單元，且中途讓鎖退出時 `finally` 區塊同步寫回 `sync_state.json` 與 `meta_dirty` 之 `.yscb_gdrive.json`。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `gdrive_support/transport.py` 既有之 `GoogleDriveApiTransport._request_json`（Thread-Local `HTTPSConnection` Keep-Alive 連線池）、`_folder_cache` 與 `LocalSandboxTransport._sync_filesystem_into_meta`。
  - 復用 `gdrive_support/coordinator.py` 既有之 `SyncCoordinator`、`InterProcessLock`、`core.platform.is_process_alive` 與 `storage.local://gdrive-support/sync_state.json` 狀態帳本。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更 `reconcile_three_way` 的三方對帳語意矩陣與 `.yscb_gdrive.json` 的雲端 Schema。
  - 不引入任何第三方套件（維持 100% Python 標準庫）。
- **架構影響範圍**：
  - `ys_codebase/source/gdrive-support/gdrive_support/transport.py`
  - `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py`
  - `ys_codebase/source/gdrive-support/gdrive_support/service.py`
  - `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py`
  - `docs/gdrive-support/README.md`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `changes.getStartPageToken` 與 `changes.list` 雙模同構抽象（含沙盒 `.yscb_sandbox_meta.json` 虛擬項目與 Shortcut 感知）**：
  - 於 `AbstractSyncTransport` 新增 `ChangeRecord` 資料結構與 `get_start_page_token() -> str`、`list_changes(page_token: str) -> Tuple[List[ChangeRecord], str]` 介面。
  - `GoogleDriveApiTransport` 調用 `GET /drive/v3/changes/startPageToken` 與 `GET /drive/v3/changes`（含 `nextPageToken` 分頁拉取至 `newStartPageToken`）。
  - `LocalSandboxTransport` 結合 `_sync_filesystem_into_meta()` 後之 `meta["items"]`（含虛擬項目、Shortcut `target_file_id` 解析後目標指紋與 `trashed` 狀態）產生狀態快照 token，並比對前後差異產出同構之 `ChangeRecord` 清單。
- **[P00:DR-02] 全域遠端倉庫快取 (`remote_repo_cache`)、Shortcut `target_file_id` 反向連動與零 TOCTOU 游標推進**：
  - 於 `sync_state.json` 儲存 `remote_repo_cache`（含 `changes_page_token`、`root_folder_id`、`repo_sync_prefix`、`repo_meta`、各分支 `raw_entries` + `dir_ids` 映射、以及 `tracked_folder_ids` / `tracked_file_ids` / `shortcut_target_ids`）。
  - **Level 0（零雲端受管變更）**：當 `list_changes(page_token)` 無任何屬於受管 `file_id`、`target_file_id` 或 `parent_id` 之外部變更時，直接復用快取之 `repo_meta` 與各分支快照，並短路跳過 `_reconcile_unregistered_cloud_branches`、其他分支重掃與 `_flush_external_repo_trash`（若本地無 `PUSH/DELETE` 則一併跳過 `_gc_unreferenced_history_files`），達成單次 `changes.list` HTTP 請求短路。
  - **Level 1（已知檔案、Shortcut 目標檔或已知父目錄下之單純非目錄檔案變更）**：直接在快取內增量更新對應分支（含引用同一 `target_file_id` 之所有 Shortcut 分支條目）。
  - **Level 2（目錄結構變動、`.yscb_gdrive.json` 外部變更或未知父目錄安全回退）**：標記快取失效，在全量掃描**開始前**先呼叫 `get_start_page_token()` 取得基準游標，完成全量校準後寫入快取（日常本地 `PUSH`/`DELETE` 與分支操作僅更新本地快取中之對應條目並保留 Stage 1 之 `newStartPageToken`，下次 `list_changes` 讀到自身寫入之相同 `(file_id, md5)` 自然冪等吸收，絕不盲目呼叫 `get_start_page_token()` 跳過併發外部變更）。
- **[P00:DR-03] 具 PID/TTL 自癒之 `cli_yield.signal` 前景搶占讓鎖與 Stage 3 單檔原子 CoW + `meta_dirty` 安全落盤**：
  - `SyncCoordinator._acquire_lock(non_blocking=False)`：前景模式首次非阻塞取鎖未果時，寫入 `cache://gdrive-support/cli_yield.signal`（JSON `{"pid": os.getpid(), "ts": time.time()}`），一旦取得 `sync.lock` 或退出即刻刪除訊號檔；背景 `should_yield()` 檢查時若訊號檔 `age > 120s` 或 `not is_process_alive(pid)`，自動刪除孤兒訊號並忽略。
  - Stage 3 將 `PUSH_UPDATE` 之 CoW（移入 `.history/` 或刪除舊 Shortcut）與 `upload_file` 封裝於單一檔案工作單元內原子執行（禁止預先全量搬移），且 `run_sync` 的 `finally` 區塊在儲存本地 `sync_state.json` 之餘，若 `meta_dirty` 為 True 則同步呼叫 `_write_remote_repo_meta(meta)` 確保雲端與本地帳本 100% 一致。

---

## 3. 開放議題與確認紀錄

- **Q1**：當 `changes.list` 偵測到雲端有變更時，是否採用「輕量精準增量 Patch + 結構變動局部回退」策略？ $\to$ **開發者確認：是**。
- **Q2**：離線沙盒 (`LocalSandboxTransport`) 是否以沙盒目錄狀態建立同構虛擬 `page_token` 與變更比對？ $\to$ **開發者確認：可以**。
- **Q3**：先前由雲端同步拉回之兩份 `plans/` 調研計畫是否保留？ $\to$ **開發者確認：保留**。
- **Q4**：`/blind-subagent` 反向查驗發現之 4 項加固對策（Level 0 外圍 API 全面短路、零 TOCTOU 游標推進與 Shortcut `target_file_id` 連動、`cli_yield.signal` PID+TTL 防死鎖、Stage 3 單檔原子 CoW 與 `meta_dirty` `finally` 寫回）是否納入並啟動 `/auto`？ $\to$ **開發者確認：是，`/auto`**。
