# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：`module:gdrive-support` 雲端分支管理機制、三方對帳與雙向同步引擎 (`sub_02_branch_and_sync_engine`)  
> 建立日期：2026-11-04  
> 所屬主計畫：`2026_11_04_0858_gdrive_bidirectional_sync_module`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `reconciler.py` 100% 無狀態三方對帳與 `.history/` 引用計數純函式 | 實作 `FileEntry`、`SyncAction`、`SyncActionType` 與 `reconcile_three_way()`（零磁碟/網路 I/O、零 `time.time_ns()` 呼叫，僅依賴標準庫與 `config.py`），比較本地、雲端（含 Shortcut 目標摘要）與基準線快照產出 8 態 `SyncAction`；實作 `compute_history_ref_counts()` 與 `is_file_id_referenced_by_other_branches()`。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | 雲端 `<root_folder_id>` 初始化 (`init`)、`.yscb_gdrive.json` 與 `README.md` 託管 | 實作 `SyncCoordinator.init_repo()`：建立 `.yscb_gdrive.json`（含 `repo_id`、`active_branch`、`branches` 註冊表與 `branch_shortcuts` 引用表）、自動生成記載 `yscb module:gdrive-support` 管理與操作規範之 `README.md`、以及 `.history/`、`.trash/`、`main/`。 | P0 | [P00:DR-02] |
| **FR-03** | Shortcut 差量分支管理 (`branch list/create/delete`) 與 `checkout` 原子工作樹切換 | `branch create <name>` 建立真實資料夾骨架並為來源分支所有檔案建立 Google Drive Shortcut；`branch delete <name>` 移除分支並觸發 `.history/` 無引用檔案移入 `.trash/` GC；`checkout <target_branch>` 驗證本地乾淨後拉取差異檔、清理舊分支獨有本地受管檔並逐檔更新基準線帳本。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-04** | 受引用時 Copy-on-Write (`.history/`)、無引用自動回收至 `.trash/` 與單檔增量帳本落盤 (`pull`/`push`/`sync`) | 更新檔案時若舊 `file_id` 被其他分支引用（`ref_count > 0`），將舊實體檔移入 `.history/` 並新建實體檔（使舊分支 Shortcut 凍結不變）；若在分支修改 Shortcut 則將 Shortcut 移入 `.trash/` 並新建實體檔；當 `.history/` 檔案 `ref_count == 0` 時自動移入 `.trash/`；每完成單檔傳輸立即於 `try/finally` 增量更新 `sync_state.json`。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-05** | `service.py` 選配常駐背景服務 (`GDriveSyncServiceWorker`) 與 CLI 擴充 | 實作 `GDriveSyncServiceWorker`：當 `auto_sync: false`（預設）時處於 `standby` 模式，`health_check()` 回傳 `True`；當 `auto_sync: true` 時訂閱 `file_space.service.subscribe` 並於 `stop()` 確定性呼叫 `_unsubscribe()`；於 `scripts/cli.py` 與 `contributes/core.json` 擴充 `init`, `branch` (`list`/`create`/`delete`), `checkout`, `pull`, `push`, `sync` 指令。 | P0 | [P00:DR-01], [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 雲端 `<root_folder_id>` 非空但缺少 `.yscb_gdrive.json`，且使用者直接執行 `pull`/`push`/`sync` | 協調器立即拋出 `GDriveRepoUninitializedError` 熔斷阻斷，防止誤綁非空私人雲端目錄導致覆寫，提示須先執行 `yscb gdrive init`。 |
| **EC-02** | 雙邊同時修改同一檔案（`CONFLICT`）：背景/一般 `sync` vs. `pull`/`push` vs. `--force --backup` | 一般 `sync` 遇 `CONFLICT` 按檔隔離保留雙邊原狀不覆寫（其餘無衝突檔照常完成同步並回傳 Exit Code 2）；單向 `pull`/`push` 未帶 `--force` 時遇衝突阻斷；帶 `--force --backup` 時自動將被覆寫方備份為 `.conflict.<ts>.bak`。 |
| **EC-03** | 本地工作區存在未同步修改（`PUSH_NEW` / `PUSH_UPDATE`）時執行 `checkout <target_branch>` | 未帶 `--force` 時立即拋出 `GDriveDirtyWorktreeError` 拒絕切換分支，防止未同步修改遺失或污染目標分支。 |
| **EC-04** | 大檔案（`>= large_file_threshold_mb`）距離最後修改時間 `< 2.0s` 尚在寫入中，或同步中途於第 K 個檔案發生異常中斷 | `< 2.0s` 之不穩定大檔於本次掃描暫緩推送；中途發生異常時，`try/finally` 確保前 K-1 個已完成檔案之基準線狀態已原子寫入 `sync_state.json`，重試時零假衝突。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 嚴格單向 DAG 與 `reconciler.py` 純函式 (`S2`) | `config.py <- reconciler.py <- transport.py <- coordinator.py <- (service.py, scripts/cli.py)`；`reconciler.py` 100% 無 I/O 與無時間呼叫。 |
| **NFR-02** | 自動化測試 100% 本地沙盒隔離 | `tests/test_branch_and_sync_engine.py` 100% 基於 `LocalSandboxTransport` 與本地沙盒執行，**嚴禁針對對外 `GoogleDriveApiTransport` 編寫需使用者金鑰之自動化 test cases**。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `server/service.py` 以 `worker.health_check()` 判定服務存活；當 `auto_sync=False` 時 `GDriveSyncServiceWorker` 雖不啟動背景輪詢執行緒，其 `health_check()` 仍須在 `standby` 狀態下回傳 `True`（並在狀態摘要標記 `mode="standby"`）。
- **`[!NOTE]`** `file_space.service.subscribe(callback)` 回傳 `_unsubscribe` 閉包，Worker 於 `stop()` 時必須呼叫並清空該閉包以符合 `D4` 確定性資源釋放。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
scripts/cli.py ──┐
                 ├──► coordinator.py (SyncCoordinator: Lock, sync_state.json, CoW .history -> .trash GC, 4-stage sync)
service.py ──────┘          │
                            ├──► transport.py (LocalSandboxTransport / GoogleDriveApiTransport)
                            └──► reconciler.py (100% Pure 3-way diff & history ref_count calculator)
                                   └──► config.py (GDriveConfig & SyncSpaceSpec)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | Modify | 新增 `GDriveRepoUninitializedError`、`GDriveConflictError`、`GDriveDirtyWorktreeError` 例外類別 |
| `ys_codebase/source/gdrive-support/gdrive_support/reconciler.py` | New | 100% 無狀態純函式三方對帳演算法 (`reconcile_three_way`) 與 `.history/` 跨分支引用計數計算 (`compute_history_ref_counts`) |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | New | `SyncCoordinator`：管理跨進程鎖、`sync_state.json` 單檔增量落盤、`init`、`branch`、`checkout`、`.history/` CoW 與 `.trash/` GC、`pull`/`push`/`sync` |
| `ys_codebase/source/gdrive-support/gdrive_support/service.py` | New | `GDriveSyncServiceWorker`：受 `auto_sync: false` 守門之常駐背景服務（含 `standby` 健康檢查與 `_unsubscribe` 確定性釋放） |
| `ys_codebase/source/gdrive-support/gdrive_support/__init__.py` | Modify | 延遲匯出 `reconciler`、`coordinator`、`service` 公開符號 |
| `ys_codebase/source/gdrive-support/scripts/cli.py` | Modify | 新增 `init`、`branch_list`、`branch_create`、`branch_delete`、`checkout`、`pull`、`push`、`sync` CLI 處理函式 |
| `ys_codebase/source/gdrive-support/contributes/core.json` | Modify | 宣告 `init`、`branch` (`list`/`create`/`delete`)、`checkout`、`pull`、`push`、`sync` 命令節點 |
| `ys_codebase/source/gdrive-support/contributes/server.json` | New | 向 `server` 註冊 `gdrive-sync` 背景服務 Worker (`GDriveSyncServiceWorker`) |
| `ys_codebase/source/gdrive-support/contributes/_manifest.md` | Modify | 登記 `contributes/server.json` Egress 契約與新增 CLI 命令 |
| `ys_codebase/source/gdrive-support/USAGE.md` | Modify | 補充 `init`、`branch`、`checkout`、`pull`、`push`、`sync` 使用範例 |
| `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py` | New | 100% 基於 `LocalSandboxTransport` 驗證三方對帳、Shortcut 分支、`.history/` CoW、無引用移入 `.trash/` GC、`checkout`、增量落盤與 `service.py` |
| `docs/gdrive-support/README.md` | Modify | 更新完整五大正交部件架構、分支管理與雙向同步說明 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 雲端 `.yscb_gdrive.json` 記錄 `branches`（分支清單與建立時間）及 `branch_shortcuts: dict[branch_name, dict[rel_path, target_file_id]]`。當任何分支建立、更新或刪除時，`coordinator.py` 透過 `reconciler.compute_history_ref_counts()` 即時算出每個歷史 `file_id` 的跨分支被引用次數，實現 $O(1)$ 雲端請求開銷之 Copy-on-Write 判斷與 `.history/` $\to$ `.trash/` 自動垃圾回收。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# gdrive_support/reconciler.py
class SyncActionType(str, Enum):
    IN_SYNC = "IN_SYNC"
    PUSH_NEW = "PUSH_NEW"
    PUSH_UPDATE = "PUSH_UPDATE"
    PULL_NEW = "PULL_NEW"
    PULL_UPDATE = "PULL_UPDATE"
    DELETE_REMOTE = "DELETE_REMOTE"
    DELETE_LOCAL = "DELETE_LOCAL"
    CONFLICT = "CONFLICT"

@dataclass(frozen=True)
class FileEntry:
    rel_path: str
    md5: str
    sha256: str = ""
    size: int = 0
    mtime_ns: int = 0
    file_id: str = ""
    is_shortcut: bool = False
    target_file_id: str = ""

@dataclass(frozen=True)
class SyncAction:
    rel_path: str
    action: SyncActionType
    local_entry: Optional[FileEntry] = None
    remote_entry: Optional[FileEntry] = None
    baseline_entry: Optional[FileEntry] = None
    reason: str = ""

def reconcile_three_way(
    local_snap: dict[str, FileEntry],
    remote_snap: dict[str, FileEntry],
    baseline_snap: dict[str, FileEntry],
    mode: str = "sync",
    allow_pull_delete: bool = False,
    allow_push_delete: bool = False,
    force: bool = False,
) -> list[SyncAction]: ...

def is_file_id_referenced_by_other_branches(
    file_id: str,
    active_branch: str,
    branch_files_map: dict[str, dict[str, str]],
) -> bool: ...

def compute_orphan_history_file_ids(
    history_file_ids: set[str],
    branch_files_map: dict[str, dict[str, str]],
) -> list[str]: ...

# gdrive_support/coordinator.py
@dataclass
class SyncReport:
    branch: str
    mode: str
    pushed: list[str]
    pulled: list[str]
    deleted_local: list[str]
    deleted_remote: list[str]
    conflicts: list[str]
    moved_to_history: list[str]
    gc_history_to_trash: list[str]
    skipped_stabilizing: list[str]
    exit_code: int = 0
    def to_dict(self) -> dict[str, Any]: ...

class SyncCoordinator:
    def __init__(
        self,
        config: GDriveConfig,
        transport: AbstractSyncTransport,
        project_root: Optional[Path] = None,
        state_path: Optional[Path] = None,
        lock_path: Optional[Path] = None,
        file_space_manager: Optional[Any] = None,
    ) -> None: ...
    def init_repo(self, force: bool = False) -> dict[str, Any]: ...
    def list_branches(self) -> dict[str, Any]: ...
    def create_branch(self, branch_name: str, from_branch: Optional[str] = None) -> dict[str, Any]: ...
    def delete_branch(self, branch_name: str) -> dict[str, Any]: ...
    def checkout_branch(self, target_branch: str, force: bool = False, backup: bool = False) -> dict[str, Any]: ...
    def run_sync(
        self,
        mode: str = "sync",
        delete: bool = False,
        force: bool = False,
        backup: bool = False,
        now_ns: Optional[int] = None,
        non_blocking_lock: bool = False,
    ) -> SyncReport: ...

# gdrive_support/service.py
class GDriveSyncServiceWorker:
    def __init__(self, config: Optional[GDriveConfig] = None, coordinator: Optional[SyncCoordinator] = None) -> None: ...
    def start(self, context: Any = None) -> None: ...
    def stop(self) -> None: ...
    def health_check(self) -> bool: ...
    def get_service_status(self) -> dict[str, Any]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `GDriveRepoUninitializedError(GDriveError)`：雲端根目錄非空且無 `.yscb_gdrive.json` 時拋出。
  - `GDriveConflictError(GDriveError)`：單向 `pull`/`push` 未帶 `--force` 遭遇衝突時拋出。
  - `GDriveDirtyWorktreeError(GDriveError)`：`checkout` 時本地有未同步修改且未帶 `--force` 時拋出。
- **階段決策紀錄**：`[P03:DR-01]` `run_sync` 回傳結構化 `SyncReport`，其中 `exit_code` 在無衝突時為 `0`，在 `sync` 模式遭遇按檔隔離之 `CONFLICT` 時為 `2`（非衝突檔仍 100% 完成同步並增量落盤）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 與 NFR-02 指標約束
- **靈魂拷問與防護解法**：
  - *問：當 `main/` 下的檔案 `file_A`（`id=fid_1`）先前已被 `v1.0` 的 Shortcut 引用，隨後 `main/` 更新了 `file_A`（觸發 CoW 將 `fid_1` 移入 `.history/` 並在 `main/` 產生 `fid_2`），之後使用者又在 `v1.0` 修改或刪除了 `file_A`（或刪除了 `v1.0` 分支），`fid_1` 如何確保不會永遠殘留在 `.history/`？*
  - *答*：`.yscb_gdrive.json` 的 `branch_files` 記錄每個分支下每個 `rel_path` 當前引用的實體 `file_id`（不論它是實體檔還是 Shortcut 的 `target_file_id`），並維護 `history_files: dict[file_id, rel_name]`。每次 `run_sync`、`create_branch`、`delete_branch` 或分支內檔案覆寫/刪除結束時，`compute_orphan_history_file_ids()` 會掃描 `history_files` 中所有不在任何活躍分支 `branch_files` 值集合內的 `file_id`，立即將它們從 `.history/` 移入 `.trash/` 並從 `history_files` 移除。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/gdrive-support/README.md` | Modify | 補充五大正交部件、Shortcut 分支、`.history/` CoW 與 `.trash/` GC、三方同步狀態機 |
| **專題手冊** | `ys_codebase/source/gdrive-support/USAGE.md` | Modify | 補充 `init`、`branch`、`checkout`、`pull`、`push`、`sync` 指令說明 |
| **設計決策** | `docs/gdrive-support/README.md` | Modify | 記錄增量帳本落盤與 `.history/` 引用計數自動回收設計 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 完整編寫 `reconciler.py`、`coordinator.py`、`service.py` Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 P07 結案時記錄 `sub_02` 發布摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_02` 所有自動化測試 100% 基於 `LocalSandboxTransport` 執行，零對外 Google API test cases。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `gdrive_support/reconciler.py`（100% 純函式三方對帳與 `.history/` 引用計數計算）並擴充 `config.py` 例外類別
- [x] **TASK-02**：實作 `gdrive_support/coordinator.py`（`.yscb_gdrive.json`、`README.md`、`init`、`branch list/create/delete`、`checkout`、`.history/` CoW 與無引用自動移入 `.trash/` GC、單檔增量帳本落盤與 `pull`/`push`/`sync`）
- [x] **TASK-03**：實作 `gdrive_support/service.py`（`GDriveSyncServiceWorker`）並更新 `gdrive_support/__init__.py`、`scripts/cli.py`、`contributes/{core,server}.json` 與 `_manifest.md`
- [x] **TASK-04**：編寫 `tests/test_branch_and_sync_engine.py`（100% 基於 `LocalSandboxTransport` 驗證所有分支、CoW、GC、同步、衝突隔離与背景服務）並通過 `dev check` 與 `dev test`
- [x] **TASK-DOC**：更新 `docs/gdrive-support/README.md` 與 `USAGE.md`

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

