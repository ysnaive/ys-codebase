# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：SyncCoordinator 預建目錄與 ThreadPoolExecutor 並發同步加速 (Parallel Sync & Branch Engine)  
> 建立日期：2026-11-04  
> 所屬主計畫：None  
> 狀態：Completed  
> 模型：Unknown  

> 計畫類型：Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)

### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)
- [x] **修改行數守門**：代碼修改行數預估 $\le 100$ 行（預估約 80~95 行）。
- [x] **API 契約守門**：Public API 簽名契約 0 變更（無破壞性與新增導出）。
- [x] **依賴邊界守門**：零跨模組新依賴引入（100% Python 標準庫 `concurrent.futures.ThreadPoolExecutor` / `threading`）。
- [x] **既有測試守門**：既有單元測試套件 100% 覆蓋守門。

### 1.2 核心需求與邊界
- **需求描述**：
  1. `[FP-01:DR-01]` **父目錄拓撲預建 (`_precreate_remote_dirs`) 與執行緒安全鎖**：於 `LocalSandboxTransport` 與 `GoogleDriveApiTransport` 補齊執行緒安全鎖（`_lock` / `_token_lock`），並於 `SyncCoordinator` 執行 `create_branch` 與 `run_sync`（`PUSH_NEW` / `PUSH_UPDATE`）前，先按路徑深度由淺入深依序預建所有目標父目錄，確保多執行緒平行上傳與建立 Shortcut 時 100% 命中已快取之父目錄 ID，杜絕並發搶建同名資料夾競態。
  2. `[FP-01:DR-02]` **`ThreadPoolExecutor` 多執行緒並發執行 (`push` / `pull` / `create_branch`)**：於 `SyncCoordinator.create_branch`（平行建立 Shortcut）與 `SyncCoordinator.run_sync`（平行執行 `PUSH_NEW` / `PUSH_UPDATE` 上傳及 `PULL_NEW` / `PULL_UPDATE` 下載，主執行緒透過 `as_completed` 逐筆增量持久化 `sync_state.json`）導入 `ThreadPoolExecutor(max_workers=8)`。
- **影響範圍**：
  - `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py`
  - `ys_codebase/source/gdrive-support/gdrive_support/transport.py`
  - `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py`

### 1.3 實作任務與測試規劃
- [x] **TASK-01**：於 `transport.py` 補齊 `LocalSandboxTransport._lock` 與 `GoogleDriveApiTransport._token_lock` 執行緒安全保護；於 `coordinator.py` 實作 `_precreate_remote_dirs` 及 `create_branch` / `run_sync` (`push` / `pull`) 之 `ThreadPoolExecutor` 並發管線。
- [x] **TASK-02**：於 `test_branch_and_sync_engine.py` 新增並發多目錄多檔案 `push`、`branch create` 與 `pull` 正確性及目錄預建順序驗證測試 (`test_ft_09_parallel_push_pull_and_branch_create_precreates_dirs`)。
- **測試案例清冊**：
  - [x] **FT-01**：驗證多子目錄多檔案在 `run_sync(mode="push")`、`create_branch` 與 `run_sync(mode="pull")` 並發執行下，所有父目錄預先建立、檔案與 Shortcut 100% 完整無損且 `sync_state.json` 狀態一致。
  - [x] **RT-01**：全模組既有單元測試 100% 回歸通過 (`26/26 PASSED`)。

---

## 2. 實作與驗證成果 (FP-02 Execution & Test Log)

- **實作結果**：
  1. `ys_codebase/source/gdrive-support/gdrive_support/transport.py`：為 `LocalSandboxTransport` 加入 `threading.RLock()` (`self._lock`) 保護跨執行緒 metadata 讀寫與目錄建立；為 `GoogleDriveApiTransport._ensure_access_token` 加入 `self._token_lock` 保護多執行緒共享 OAuth2 Token 刷新。
  2. `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py`：新增 `PARALLEL_TRANSFER_WORKERS = 8` 與 `SyncCoordinator._precreate_remote_dirs()`（收集所有目標檔案之各層父目錄並依深度排序預建），並於 `create_branch` 與 `run_sync`（`push` / `pull`）導入 `ThreadPoolExecutor` 平行執行與主執行緒 `as_completed` 增量 `sync_state.json` 寫入（即使中途單檔拋錯亦確保已完成檔案 100% 落盤）。
  3. `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py`：新增 `test_ft_09_parallel_push_pull_and_branch_create_precreates_dirs`。
- **實機測試日誌**：
  - `python yscb.py dev check gdrive-support`：`[PASS]`
  - `python yscb.py dev test gdrive-support -q`：`Pass: 26(100.0%), Fail: 0, Skip: 0`

---

## 3. SOP Review 審查與結案交付 (Review & FP-03 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/gdrive-support/README.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `CHANGELOG.md` 發布摘要。
- [x] **標頭狀態更新**：完成上述審查並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_04_1517_gdrive_parallel_sync` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
