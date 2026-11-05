# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：Google Drive Changes API 增量快照與前景 CLI 優先搶占讓鎖機制 (GDrive Changes API Incremental Snapshot & CLI Lock Preemption)  
> 建立日期：2026-11-05  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `AbstractSyncTransport` 雙模 `changes` API 抽象 | 於 `AbstractSyncTransport` 新增 `ChangeRecord` 資料結構與 `get_start_page_token() -> str`、`list_changes(page_token: str) -> Tuple[List[ChangeRecord], str]`；`GoogleDriveApiTransport` 串接 `/drive/v3/changes/startPageToken` 與 `/drive/v3/changes`（自動分頁拉取至 `newStartPageToken`），`LocalSandboxTransport` 結合 `.yscb_sandbox_meta.json` (`meta["items"]` 含虛擬項目與 Shortcut 目標指紋) 產生同構差異紀錄與游標 | P0 | [P00:DR-01] |
| **FR-02** | 全域遠端倉庫快取 (`remote_repo_cache`) 與三級增量短路 | 於 `storage.local://gdrive-support/sync_state.json` 持久化 `remote_repo_cache`（含 `changes_page_token`、`repo_meta`、各分支 `raw_entries` / `dir_ids` 與 Shortcut `target_file_id` 索引）；Level 0（無雲端受管變更）直接復用快取並短路跳過 `_read_remote_repo_meta`、`_reconcile_unregistered_cloud_branches`、其他分支重掃與 `_flush_external_repo_trash`（本地無寫入時並跳過 `_gc_unreferenced_history_files`）；Level 1 記憶體增量 Patch 已知檔案、Shortcut 目標檔或已知父目錄下之新增非目錄檔；Level 2 於結構變動時安全回退重掃 | P0 | [P00:DR-02] |
| **FR-03** | 前景 CLI 協同搶占讓鎖 (`cli_yield.signal`) 與單檔原子 CoW | 前景 CLI (`non_blocking=False`) 首次取鎖未果時寫入 `cache://gdrive-support/cli_yield.signal` (`{"pid": os.getpid(), "ts": time.time()}`)，取得 `sync.lock` 的瞬間或異常退出時立即清除；背景 Worker 在掃描與傳輸迴圈檢查 `should_yield()`（對 `age > 120s` 或死進程之孤兒訊號自動刪除忽略），觸發讓鎖時優雅中止，且 Stage 3 將 `PUSH_UPDATE` 之 CoW 與 `upload_file` 封裝為單檔原子任務，於 `finally` 同步落盤 `sync_state.json` 與 `meta_dirty` 之 `.yscb_gdrive.json` | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | TOCTOU 併發外部變更與自身寫入回音 | 全量建置快取必須於掃描**開始前**呼叫 `get_start_page_token()`；日常本地 `PUSH`/`DELETE` 後直接更新本地 `remote_repo_cache` 而不盲目呼叫 `get_start_page_token()` 覆蓋游標，下次 `list_changes` 讀到自身上傳之相同 `(file_id, md5)` 自然冪等吸收，不漏失併發外部變更 |
| **EC-02** | Shortcut 指向目標實體檔 (`target_file_id`) 於雲端被修改或刪除 | `remote_repo_cache` 追蹤所有 Shortcut 之 `target_file_id`；當 `changes.list` 回報 `target_file_id` 變更或移除時，同步更新或觸發引用該目標之所有分支快取重算 |
| **EC-03** | 前景 CLI 遭 `SIGKILL` 強殺殘留孤兒 `cli_yield.signal` 或背景 Stage 3 中途讓鎖 | 背景 `should_yield()` 驗證訊號檔 `pid` 存活 (`is_process_alive`) 與 `ts` TTL (`<= 120s`)，過期或死進程訊號自動刪除忽略；Stage 3 單檔 CoW + 上傳原子綁定，中途讓鎖時 `finally` 確保已變更之 `meta` 寫回 `.yscb_gdrive.json` |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與 API 配額 | 當雲端與本地皆無變更時，單次 `run_sync` 僅發起 **1 次** `changes.list` HTTP 請求（0 次 `files.list` 目錄掃描），雲端對帳耗時 $< 0.5\text{s}$ |
| **NFR-02** | 依賴與測試隔離 | 100% Python 標準庫實現；所有單元測試於 `LocalSandboxTransport` 離線沙盒 100% 通過 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** `LocalSandboxTransport` 的 Shortcut 與虛擬項目僅存在於 `.yscb_sandbox_meta.json`，無實體檔案，因此沙盒 `get_start_page_token` / `list_changes` 必須基於 `_sync_filesystem_into_meta()` 後之 `meta["items"]` 計算。
- **`[!CAUTION]`** `Stage 3` 的 Copy-on-Write (`move_file` 至 `.history/`) 若在提交執行緒池前預先執行，一旦中途被 `cli_yield.signal` 搶占中斷，會造成雲端分支檔案消失，必須將 CoW 搬移與新檔上傳封裝在同一個單檔任務中。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[CLI Foreground (push/pull/sync/branch/checkout)]        [Background GDriveSyncServiceWorker]
                     │                                                    │
       _acquire_lock(non_blocking=False)                    run_sync(non_blocking_lock=True,
       ├─ Try flock(LOCK_NB)                                         background_worker=True)
       ├─ If busy: write cli_yield.signal {pid, ts}                       │
       ├─ Block wait flock (timeout=60s) ◄── yields lock < 1s ── Checks should_yield()
       └─ Immediately unlink cli_yield.signal                             │
                     │                                                    ▼
                     └──────────────────────► SyncCoordinator.run_sync() ◄┘
                                                    │
                     ┌──────────────────────────────┴──────────────────────────────┐
                     ▼                                                             ▼
      [Has valid remote_repo_cache & page_token]                    [No cache or Level 2 Fallback]
      transport.list_changes(page_token)                            1. token = transport.get_start_page_token()
      ├─ Level 0 (0 relevant changes):                              2. Full scan repo_meta, branches, dirs
      │   Reuse cached repo_meta & branch snapshots                 3. Save remote_repo_cache + token
      │   (0 list_files calls!)
      ├─ Level 1 (file update/delete or new file in known dir):
      │   Patch cached branch entries & shortcut targets in-memory
      └─ Level 2 (folder change / .yscb_gdrive.json / unknown parent):
          Fallback to full scan
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/gdrive-support/gdrive_support/transport.py` | Modify | 新增 `ChangeRecord` dataclass，於 `AbstractSyncTransport`、`LocalSandboxTransport` 與 `GoogleDriveApiTransport` 實作 `get_start_page_token()` 與 `list_changes(page_token)`，並支援可選 `abort_check` |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | Modify | 實作 `remote_repo_cache` 三級增量快取與 `changes.list` 短路、`cli_yield.signal` 前景搶占讓鎖（含 PID/TTL 自癒）、Stage 3 單檔原子 CoW + 上傳與 `meta_dirty` `finally` 落盤 |
| `ys_codebase/source/gdrive-support/gdrive_support/service.py` | Modify | `GDriveSyncServiceWorker.run_once()` 傳入 `background_worker=True` 與 `_stop_event.is_set` 協同讓鎖檢查 |
| `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py` | Modify | 新增 `changes` API Level 0/1/2 快取短路、Shortcut 目標變更連動、前景 CLI `cli_yield.signal` 搶占背景鎖、孤兒訊號 TTL/PID 自癒與 Stage 3 中途讓鎖 CoW 一致性測試 |
| `docs/gdrive-support/README.md` | Modify | 更新 `changes` API 增量快照快取與前景 CLI 搶占讓鎖機制說明 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** `LocalSandboxTransport` 於 `.yscb_sandbox_meta.json` 維護遞增整數 `change_seq` 與 `snapshots` 歷史表（保留最近 16 個 token 快照），每次呼叫 `get_start_page_token()` 或 `list_changes(page_token)` 時先執行 `_sync_filesystem_into_meta()` 並解析 Shortcut 目標指紋，精確比對兩個 token 間的新增、修改、移入垃圾桶與刪除項目，若傳入未知的過期 token 則拋出 `GDriveTransportError` 觸發 Level 2 全量重掃。
- **[P02:DR-02]** `SyncCoordinator` 在 Stage 3 平行上傳時，以 `self._meta_lock = threading.Lock()` 保護每個檔案上傳前之 CoW `.history/` 搬移與 `history_files`/`curr_branch_files` 字典更新，確保單檔 CoW 與上傳在同一個 worker task 中完成且執行緒安全。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/gdrive-support/gdrive_support/transport.py
@dataclass(frozen=True)
class ChangeRecord:
    file_id: str
    removed: bool = False
    entry: Optional[RemoteEntry] = None

class AbstractSyncTransport(ABC):
    def get_start_page_token(self) -> str: ...
    def list_changes(
        self, page_token: str
    ) -> Tuple[List[ChangeRecord], str]: ...

# ys_codebase/source/gdrive-support/gdrive_support/coordinator.py
class SyncCoordinator:
    def should_yield_background(self) -> bool: ...
    def run_sync(
        self,
        mode: str = "sync",
        allow_delete: Optional[bool] = None,
        force: bool = False,
        backup: bool = False,
        non_blocking_lock: bool = False,
        background_worker: bool = False,
    ) -> SyncReport: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 當 `list_changes(page_token)` 因 token 過期或網路錯誤拋出 `GDriveTransportError` 時，`SyncCoordinator` 自動捕獲並降級為 Level 2 全量掃描重建快取，絕不中斷同步流程。
  - 當背景 Worker (`background_worker=True`) 偵測到 `should_yield_background() == True` 時，立即停止後續掃描或取消未執行之傳輸任務，在 `finally` 落盤已完成狀態並正常返回 `SyncReport`（標記 `yielded=True`）。
- **階段決策紀錄**：`[P03:DR-01]` `get_start_page_token` 與 `list_changes` 在 `AbstractSyncTransport` 提供預設實作（回傳空 token），並在 `LocalSandboxTransport` 與 `GoogleDriveApiTransport` 完整實作，確保任何自訂 Mock Transport 向後相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-03 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-03 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：若本地執行 `create_branch`、`delete_branch` 或 `checkout_branch` 修改了雲端分支結構，快取如何保持一致？*
  - *答*：在 `init_repo`、`create_branch`、`delete_branch` 與 `checkout_branch` 變更雲端結構時，直接失效或同步更新 `sync_state.json` 中的 `remote_repo_cache`，確保下一次 `run_sync` 不會讀到過期的分支快照。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/gdrive-support/README.md` | Modify | 增補 `changes` API 三級增量快照快取與前景 CLI `cli_yield.signal` 搶占讓鎖說明 |
| **專題手冊** | `docs/gdrive-support/[topic].md` | N/A | 機制直接整合於 `docs/gdrive-support/README.md` |
| **設計決策** | `docs/gdrive-support/DESIGN_NOTES.md` | N/A | 免更 |
| **微觀註解** | `transport.py`, `coordinator.py`, `service.py` | Modify | 同步更新公開方法與類別 Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 P07 結案時記錄本計畫變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認無外部模組依賴變更，直接進入實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：於 `gdrive_support/transport.py` 實作 `ChangeRecord`、`get_start_page_token()` 與 `list_changes(page_token)`（涵蓋 `GoogleDriveApiTransport` 與 `LocalSandboxTransport`）
- [x] **TASK-02**：於 `gdrive_support/coordinator.py` 與 `service.py` 實作 `remote_repo_cache` 三級增量快取、`cli_yield.signal` 前景搶占讓鎖（含 PID/TTL 自癒）與 Stage 3 單檔原子 CoW + `meta_dirty` 安全落盤
- [x] **TASK-03**：於 `tests/test_branch_and_sync_engine.py` 編寫 `changes` API Level 0/1/2 快取短路、Shortcut 目標連動與前景 CLI 搶占背景鎖單元測試
- [x] **TASK-DOC**：同步更新 `docs/gdrive-support/README.md` 與源碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

