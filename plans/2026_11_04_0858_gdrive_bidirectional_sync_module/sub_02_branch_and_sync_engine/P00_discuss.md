# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`module:gdrive-support` 雲端分支管理機制、三方對帳與雙向同步引擎 (`sub_02_branch_and_sync_engine`)  
> 建立日期：2026-11-04  
> 所屬主計畫：`2026_11_04_0858_gdrive_bidirectional_sync_module`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 作為主計畫 `2026_11_04_0858_gdrive_bidirectional_sync_module` 之第二個子計畫 `sub_02_branch_and_sync_engine`，在 `sub_01` 完成之原子傳輸基座上，實作雲端 `<root_folder_id>` 標準頂層結構與 Shortcut 差量分支管理機制（`.yscb_gdrive.json`、`README.md`、`init`、`branch list/create/delete`、`checkout` 原子工作樹切換、`.history/` Copy-on-Write 與無引用自動回收至 `.trash/`）、100% 無狀態三方對帳演算法（`reconciler.py`）、增量帳本落盤與跨進程鎖編排器（`coordinator.py` 之 `pull`/`push`/`sync`）及預設 `auto_sync: false` 待機之選配背景服務（`service.py`）。
- **核心目標**：
  1. **實作 `gdrive_support/reconciler.py`（100% 無狀態純函式三方對帳與 `.history/` 引用計數計算）**：
     - 嚴守 `S2` 無狀態純函式（零磁碟 I/O、零網路 I/O、零 `time.time_ns()` 系統時間呼叫，且僅依賴標準庫與 `config.py`，嚴禁匯入 `transport.py`）。
     - 接收記憶體快照 `(local_snapshot, remote_snapshot, baseline_state)`，基於原檔案類型 `(md5, sha256, size)`（含解析後之 Shortcut 目標摘要）執行三方比對，輸出 8 態 `SyncAction`（`IN_SYNC`, `PUSH_NEW`, `PUSH_UPDATE`, `PULL_NEW`, `PULL_UPDATE`, `DELETE_REMOTE`, `DELETE_LOCAL`, `CONFLICT`）。
     - 提供純函式 `compute_history_ref_counts(history_ids, branch_shortcut_targets)` 與 `is_file_id_referenced_by_other_branches(file_id, active_branch, branch_shortcut_targets)`，精確計算某 `file_id` 是否受其他分支 Shortcut 引用（`ref_count > 0` 時觸發 Copy-on-Write 移入 `.history/`；`.history/` 中 `ref_count == 0` 之檔案則列入自動移入 `.trash/` 的回收清單）。
  2. **實作 `gdrive_support/coordinator.py`（雲端 `<root_folder_id>` 分支管理、增量帳本落盤與 4 階段同步管線）**：
     - **雲端根目錄初始化與非空目錄防呆 (`init`)**：若雲端根目錄非空且缺少 `.yscb_gdrive.json`，未顯式執行 `init` 時拒絕同步（拋出 `GDriveRepoUninitializedError`）；`init` 時建立 `.yscb_gdrive.json`、自動生成標註由 `yscb module:gdrive-support` 自動管理與操作規範之 `README.md`、以及 `.history/`、`.trash/`、`main/`。
     - **Shortcut 差量分支與 `.history/` $\to$ `.trash/` 引用計數自動回收 (`branch list/create/delete`, `checkout`)**：
       - `branch create <name>`：建立 `<name>/` 真實資料夾骨架，並將來源分支（預設 `main`）的所有檔案以 Google Drive Shortcut 指向原實體 `file_id`，記錄各分支 Shortcut 引用表至 `.yscb_gdrive.json`。
       - **更新時之 Copy-on-Write vs. In-Place `PATCH`**：當更新某檔案 `old_file_id` 時，若 `ref_count > 0`（被其他分支引用），將 `old_file_id` 移入 `.history/` 並新建實體檔（使舊分支 Shortcut 內容永遠凍結不變）；若在非 `main` 分支修改一個 Shortcut，先將該 Shortcut 移入 `.trash/` 再新建實體檔；若 `ref_count == 0`，直接原地 `PATCH`。
       - **`.history/` 無引用自動回收至 `.trash/`**：每當分支刪除、Shortcut 被替換/刪除或同步收尾時，自動將 `.history/` 中 `ref_count == 0` 的檔案移入 `.trash/`。
       - **`checkout <target_branch>` 原子工作樹切換**：先檢查當前本地是否有未同步修改（若有且未帶 `--force` 則阻斷）；切換時拉取目標分支差異檔、清理舊分支獨有但目標分支不存在之本地受管檔，並逐檔更新基準線帳本。
     - **跨進程鎖與單檔增量帳本落盤 (`pull`, `push`, `sync`)**：以 `core.uri.resolve("cache://gdrive-support/sync.lock")` 取得 `InterProcessLock`；背景 `sync` 遇 `CONFLICT` 按檔隔離保留雙邊原狀不覆寫並回傳 Exit Code 2（手動 `--force --backup` 則產出 `.conflict.<ts>.bak`）；每完成單一檔案傳輸立即更新記憶體帳本並於 `try/finally` 中原子落盤 `cache://gdrive-support/sync_state.json`。
  3. **實作 `gdrive_support/service.py`（預設 `auto_sync: false` 待機之 `GDriveSyncServiceWorker`）**：
     - 當 `config.auto_sync == False` 時處於 `standby` 模式，不註冊監聽亦不輪詢，且 `health_check()` 回傳 `True`；當 `auto_sync == True` 時訂閱 `file_space.service.subscribe` 並在 `stop()` 時確定性呼叫 `_unsubscribe()` 釋放回呼（遵循 `D4`）。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `sub_01` 之 `gdrive_support/config.py` 與 `gdrive_support/transport.py`。
  - 復用 `core.platform.InterProcessLock`、`core.uri`、`core.vfs`、`file_space.service.subscribe` 與 `server.service.BaseServiceWorker`。
- **邊界排除 (Explicitly Excluded)**：
  - **測試鐵律**：`tests/` 下所有自動化測試案例 **100% 基於 `LocalSandboxTransport` 與純記憶體/本地沙盒執行**，**嚴禁針對對外 `GoogleDriveApiTransport` 編寫需使用者金鑰之自動化 test cases**（對外 API 實機驗證歸屬 `sub_03`）。
- **架構影響範圍**：
  - 新增 `gdrive_support/{reconciler,coordinator,service}.py`、擴充 `gdrive_support/__init__.py`、`scripts/cli.py`、`contributes/{core,server}.json` 與 `tests/test_branch_and_sync_engine.py`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `reconciler.py` 100% 純函式隔離 (`S2`) 與單向 DAG**：
  - `reconciler.py` 僅依賴標準庫與 `config.py`，零磁碟/網路 I/O、零系統時間呼叫；所有磁碟帳本 (`sync_state.json`)、指紋快取 (`FingerprintCache`) 與 `< 2.0s` 大檔靜置過濾統一由 `coordinator.py` 執行。
- **[P00:DR-02] 受引用時 Copy-on-Write (`.history/`) 與無引用自動回收至 `.trash/`**：
  - 實體檔更新時依跨分支引用數 `ref_count` 決定原地更新（`ref_count == 0`）或移入 `.history/` 後新建（`ref_count > 0`）；當 `.history/` 內檔案 `ref_count == 0` 時立即自動移入 `.trash/`。
- **[P00:DR-03] 單檔增量帳本落盤 (Incremental State Commit) 與 `checkout` 孤兒清理**：
  - `coordinator.py` 每完成一檔傳輸即更新帳本並在 `try/finally` 寫回 `sync_state.json`；`checkout` 自動清理舊分支獨有、新分支不存在之本地受管檔案。
- **[P00:DR-04] 自動化測試 100% 鎖定本地沙盒 (`LocalSandboxTransport`)**：
  - `tests/test_branch_and_sync_engine.py` 100% 使用 `LocalSandboxTransport` 驗證分支建立、Shortcut 差量、`.history/` CoW 與 `.trash/` GC、`checkout`、三方對帳與 `GDriveSyncServiceWorker` 生命週期。

---

## 3. 開放議題與確認紀錄

- 子計畫 `sub_02_branch_and_sync_engine` 需求與邊界已完全承接自主計畫 `P00_discuss.md` 與 `R01_gdrive_architecture_and_design.md`。

