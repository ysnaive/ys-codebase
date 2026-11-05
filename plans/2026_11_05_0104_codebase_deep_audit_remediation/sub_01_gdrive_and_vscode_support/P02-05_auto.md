# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_01_gdrive_and_vscode_support  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

> 本子計畫之 P01 需求規格已於 [`P01_requirements_spec.md`](./P01_requirements_spec.md) 獨立確認定案；以下對齊摘要供跨階段追溯：

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `gdrive-support` 單向同步 (`pull`/`push`) 基準線防覆寫保護 | 於 `SyncCoordinator.run_sync()` 處理 `SyncActionType.IN_SYNC` 時，嚴格限定僅在 `act.local_entry`、`act.remote_entry` 皆存在且 `act.reason == "identical_digest"` 時才允許更新 `branch_state_dict[rel_p]`；保留單向略過對向修改時的原基準線。 | P0 | [P00:DR-01] |
| **FR-02** | `gdrive-support` 空 `sync_spaces` 阻斷守衛與專案組態對齊 | 於 `SyncCoordinator.run_sync()` 入口檢核 `self.config.sync_spaces`，若為空則立即拋出 `GDriveConfigError` 拒絕執行同步；並確認 `ys_codebase/config/gdrive-support/contribute.json` 宣告 `"sync_spaces": [{"space": "cloud"}]`。 | P0 | [P00:DR-01] |
| **FR-03** | 分支內部系統名稱解耦與 `.`/`_` 子目錄 Level 1 增量放行 | 獨立 `BRANCH_INTERNAL_SYSTEM_NAMES = {REPO_CONFIG_FILENAME, ".history", ".trash"}`（不含 `"README.md"`）避免誤濾 `<repo>/<branch>/README.md`；並於 Level 1 `pending_new_folders` 移除對分支內子目錄 `.` 與 `_` 字首的攔截。 | P0 | [P00:DR-01] |
| **FR-04** | CLI `--sandbox-dir` 全鏈路狀態與組態隔離 | 於 `gdrive-support/scripts/cli.py` 提取 `_build_coordinator(sandbox_dir)` 將 `state_path`、`lock_path`、`log_path`、`readme_state_path` 隔離錨定於沙盒目錄下，於 `SyncCoordinator._persist_active_branch_to_config()` 在沙盒模式下跳過改寫全域組態，並於 `contributes/core.json` 將 `init`、`branch`、`checkout`、`pull`、`push`、`sync` 設為 `"server_compatible": false` 防止與背景 `GDriveSyncServiceWorker` 發生同進程 `sync.lock` 死鎖。 | P1 | [P00:DR-01] |
| **FR-05** | 遠端空父目錄與已歸檔孤兒空殼自動清理 | 於 `SyncCoordinator.run_sync()` 執行 `DELETE_REMOTE` 後及比對分支 `dir_ids` 與 `curr_branch_files` 時，由深至淺自動清理無檔案且無存活子目錄之遠端空資料夾，並同步更新 `remote_repo_cache`。 | P1 | [P00:DR-01] |
| **FR-06** | `_folder_cache` 執行緒安全鎖、Level 0/1 預熱與按深度分層 BFS 平行建目錄 | 為 `GoogleDriveApiTransport` 新增 `_cache_lock = threading.RLock()`；於 Level 0/1 快取命中時將已知目錄預熱至 `transport._folder_cache` 並支援 `trash_file`/`move_file` 傳入 `file_id`/`entry_hint`；將 `_precreate_remote_dirs` 改為依深度分層 BFS + `ThreadPoolExecutor(max_workers=8)` 平行建立。 | P1 | [P00:DR-02] |
| **FR-07** | 同名資料夾非破壞性去重、傳輸重試、401 刷新與 Shortcut 平行解析 | `mkdir` 同名資料夾按 `modifiedTime` 降序排序，`list_files` 同名去重僅對非資料夾移入垃圾桶；`LocalSandboxTransport.upload_file` 複製納入 `_lock`；`download_file` 支援 `entry_hint` 與退避重試，`_request_json` 遇 HTTP `401` 重置 Token 重試；`_resolve_shortcut_targets` 平行化；非活躍分支引用快取遵守紅線 1。 | P2 | [P00:DR-02] |
| **FR-08** | `vscode-support` 卸載守衛 Fail-Closed、Schema 自然版號排序與狀態/還原加固 | `hook.core.py:on_remove` 收緊為 Fail-Closed（支援 `"vscode-support"` 與 `"vsc"`）；`schema_compiler.py` 採用 `core.semver.compare_semver` 選取最新 `.mirror` 壓縮包並快取 URI Snippets；`projector.py` 補齊 `get_status` 懸空連結 `os.path.isdir` 檢查、`strip_jsonc` 回退與 `revert_vscode_settings` 空排除字典清理。 | P2 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 單向 `pull` 略過本地修改或單向 `push` 略過遠端修改 | `act.reason != "identical_digest"` 時絕不覆寫 `branch_state_dict[rel_p]`，保留原基準線供後續雙向 `sync` 正確決策。 |
| **EC-02** | 雙端皆已刪除某受管檔案但基準線仍殘留紀錄 | 安全清除 `branch_state_dict[rel_p]` 與 `curr_branch_files[rel_p]` 並標記 `meta_dirty = True`。 |
| **EC-03** | 外部於雲端新建 `auto_discovered=True` 分支或分支檔案表為空時執行 `.history/` GC | 嚴守紅線 1：禁止跳過遠端分支掃描，強制實地掃描該分支 Shortcut 目標，防止 `.history/` 凍結實體檔遭誤刪。 |
| **EC-04** | 雲端同一父目錄下存在兩個同名子資料夾 | `list_files` 僅選取 `modifiedTime` 最新之資料夾作為有效項目，嚴禁將較舊之同名資料夾直接移入垃圾桶。 |
| **EC-05** | 遠端目錄因檔案刪除或歷史歸檔騰空為空殼資料夾 | 由深至淺自動檢查，確認無受管檔案與存活子目錄後移入垃圾桶並同步移除 `remote_repo_cache` 內對應項目。 |
| **EC-06** | `.vscode/settings.json` 為含註解之 JSONC 或穩定連結指向已刪除目標（Broken Symlink） | `get_status()` 回退使用 `strip_jsonc` 解析並以 `os.path.isdir(link_path)` 檢查連結有效性；`on_remove` 在 `ctx` 缺失或移除其他模組時回傳 `False`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與網路 I/O | Level 0/1 快取命中並預熱 `_folder_cache` 後，既有目錄下檔案上傳之父目錄重查 HTTP GET 降為 `0` 次；多層新建目錄分層平行建立；`sync_all_schemas` 單次執行僅收集 1 次 URI Scheme Snippets。 |
| **NFR-02** | 執行緒安全與沙盒隔離 | `GoogleDriveApiTransport._folder_cache` 與 `_scanned_prefixes` 100% 受 `_cache_lock` 保護；CLI `--sandbox-dir` 對生產環境達成 100% 零寫入污染。 |
| **NFR-03** | 架構合規與回歸零副作用 | 100% 通過 `gdrive-support` 與 `vscode-support` 之 `dev check` 靜態檢核（0 FAIL、0 WARN），且嚴守 `R01_codebase_deep_audit.md` 8 大防回歸紅線與 `CodeQualityStandards.md` 零工單註解鐵律。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 紅線 1（非活躍分支引用快取防誤刪 `.history/`）**：唯有在 `not branches[other_b].get("auto_discovered") and bool(branch_files_map.get(other_b))` 時方可復用帳本紀錄免除掃描。
- **`[!CAUTION]` 同名資料夾不可直接 `trash_file`**：`list_files` 同名去重自動移入垃圾桶必須嚴格限定於非資料夾（`loser.get("mimeType") != FOLDER_MIME_TYPE`）。
- **`[!CAUTION]` 零工單註解與 Zero-Probing 鐵律**：生產代碼嚴禁出現任何 `FR-XX`、`U1-P0-XX`、`D-01` 等工單/審計編號註解，且嚴禁出現硬編碼 `"config.project.json"` 或 `"module.source://"` 字面量。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[gdrive-support]
  scripts/cli.py
    └── _build_coordinator(sandbox_dir) ──> 隔離錨定 state/lock/log/readme_state 至 sandbox_dir
  gdrive_support/coordinator.py
    ├── run_sync()
    │     ├── 入口守衛: 檢查 self.config.sync_spaces 非空 + transport.reset_scan_state()
    │     ├── Stage 1 (Level 0/1/2):
    │     │     ├── BRANCH_INTERNAL_SYSTEM_NAMES 解耦 (保留分支內 README.md)
    │     │     ├── Level 1 pending_new_folders 放行分支內 '.' / '_' 開頭子目錄
    │     │     ├── Level 0/1 命中時 _warm_transport_folder_cache() 預熱 _folder_cache
    │     │     └── Level 2 非活躍分支掃描遵守紅線 1 (僅非 auto_discovered 且非空時復用 branch_files)
    │     └── Stage 3 (Execution & Cleanup):
    │           ├── IN_SYNC: 僅在 act.reason == "identical_digest" 時更新 branch_state_dict
    │           ├── _precreate_remote_dirs(): 按路徑深度分層 BFS + ThreadPoolExecutor(max_workers=8)
    │           ├── DELETE_REMOTE / CoW / Pull: 傳遞 file_id / entry_hint 免除重複路徑查詢
    │           └── _prune_empty_remote_branch_dirs(): 由深至淺清理遠端空目錄並同步更新 remote_repo_cache
  gdrive_support/transport.py
    ├── LocalSandboxTransport: upload_file 複製與雜湊計算納入 self._lock；同名去重跳過資料夾
    └── GoogleDriveApiTransport:
          ├── _cache_lock (RLock) 保護 _folder_cache 與 _scanned_prefixes
          ├── _request_json() 支援 HTTP 401 重置 _access_token 重試一次
          ├── download_file() 支援 entry_hint 與退避重試
          ├── trash_file() / move_file() 支援選填 file_id / entry_hint
          ├── mkdir() 對同名資料夾按 modifiedTime 降序排序
          └── _resolve_shortcut_targets() 以 ThreadPoolExecutor(max_workers=8) 平行解析

[vscode-support]
  scripts/hook.core.py
    └── on_remove(ctx): Fail-Closed 守衛，僅當 ctx.args 為 list/tuple 且含 {"vscode-support", "vsc"} 時觸發
  vscode_support/schema_compiler.py
    ├── _select_latest_mirror_zip(): 以 core.semver.compare_semver 自然版本排序選取最新 .zip
    └── sync_all_schemas(): 單次執行期間透過 _cached_uri_snippets 快取 URI Scheme Snippets
  vscode_support/projector.py
    ├── get_status(): 檢查 os.path.isdir(link_path) 識別懸空連結，並支援 strip_jsonc 回退解析
    └── revert_vscode_settings(): 清理被清空之排除設定字典 (files.exclude 等)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/config/gdrive-support/contribute.json` | Modify | 確認宣告 `"sync_spaces": [{"space": "cloud"}]` 防止空映射 |
| `ys_codebase/source/gdrive-support/contributes/core.json` | Modify | 將 `init`、`branch`、`checkout`、`pull`、`push`、`sync` 設為 `"server_compatible": false`，防止 `WarmWorker` 同進程 `sync.lock` 死鎖 |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | Modify | 實作空 `sync_spaces` 守衛、`BRANCH_INTERNAL_SYSTEM_NAMES` 解耦、Level 1 `.`/`_` 子目錄放行、Level 0/1 `_folder_cache` 預熱、紅線 1 非活躍分支快取守衛、`IN_SYNC` `identical_digest` 保護、分層 BFS 平行 `_precreate_remote_dirs`、遠端空資料夾由深至淺清理與沙盒組態持久化隔離 |
| `ys_codebase/source/gdrive-support/gdrive_support/transport.py` | Modify | 實作 `_cache_lock` 執行緒安全保護、`reset_scan_state`、`warm_folder_cache`、`mkdir` 時間排序、`list_files` 非破壞性資料夾去重、HTTP 401 Token 重置刷新、`download_file` 退避重試與 `entry_hint`、`trash_file`/`move_file` 直通 `file_id`/`entry_hint`、Shortcut 平行解析及 `LocalSandboxTransport.upload_file` 鎖擴充 |
| `ys_codebase/source/gdrive-support/scripts/cli.py` | Modify | 提取 `_build_coordinator(sandbox_dir)` 統一隔離 `init`、`branch_*`、`checkout`、`pull`、`push`、`sync` 之沙盒狀態路徑 |
| `ys_codebase/source/gdrive-support/tests/test_atomic_api_and_config.py` | Modify | 擴充測試驗證同名資料夾非破壞性去重、`mkdir` 時間排序、HTTP 401 Token 刷新、`download_file` 重試與 `entry_hint`、Shortcut 平行解析及 CLI `--sandbox-dir` 狀態隔離 |
| `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py` | Modify | 擴充測試驗證單向 `pull`/`push` 基準線保護、空 `sync_spaces` 阻斷、分支根目錄 `README.md` 與 `.`/`_` 子目錄 Level 1 增量同步、Level 0/1 `_folder_cache` 預熱、遠端空父目錄與歸檔空殼自動清理、紅線 1 非活躍分支快取守衛與分層平行建目錄 |
| `ys_codebase/source/vscode-support/scripts/hook.core.py` | Modify | 收緊 `on_remove` 為 Fail-Closed 守衛（檢驗 `isinstance(targets, (list, tuple))` 且包含 `"vscode-support"` 或 `"vsc"`） |
| `ys_codebase/source/vscode-support/vscode_support/schema_compiler.py` | Modify | 新增 `_select_latest_mirror_zip` 使用 `core.semver.compare_semver` 排序，並於 `sync_all_schemas` 期間快取 `_collect_uri_scheme_snippets` |
| `ys_codebase/source/vscode-support/vscode_support/projector.py` | Modify | 於 `get_status` 補齊 `os.path.isdir(link_path)` 與 `strip_jsonc` 回退；於 `revert_vscode_settings` 清理空排除設定字典 |
| `ys_codebase/source/vscode-support/tests/test_vscode_support.py` | Modify | 擴充測試驗證 `on_remove` Fail-Closed（含 `None`、空參數、`"vsc"` 別名）、多位數版本號 `.mirror` 選取、URI Snippets 快取、懸空連結與 JSONC `get_status` 及 `revert` 空排除字典清理 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 分支內部系統名稱與倉庫頂層系統名稱解耦**：頂層 `<repo>/` 包含託管說明檔 `README.md`，因此 `SYSTEM_NAMES` 需保留 `REPO_README_FILENAME`；而分支目錄 `<repo>/<branch>/` 內部僅需排除 `BRANCH_INTERNAL_SYSTEM_NAMES = {REPO_CONFIG_FILENAME, ".history", ".trash"}`，確保專案根目錄 `README.md` 正常納管同步。
- **[P02:DR-02] 遠端空資料夾由深至淺自動清理機制**：於 `run_sync` 階段，除了記錄 `DELETE_REMOTE` 刪除檔案之父目錄外，同時檢查當前分支 `remote_repo_cache`（或掃描所得）之 `dir_ids` 中所有不再包含任何 `curr_branch_files` 檔案前綴之空資料夾（包含既有殘留之已歸檔空資料夾空殼），按路徑深度（`rel_dir.count("/")`）由深至淺排序，當確認無受管檔案且無未清理之子資料夾時，呼叫 `transport.trash_file` 將其移入垃圾桶並同步更新 `remote_repo_cache`。
- **[P02:DR-03] Level 0/1 `_folder_cache` 預熱與 `file_id` 直通操作**：當 `_try_incremental_remote_cache` 命中 Level 0 或 Level 1 時，由 `remote_repo_cache` 內之 `repo_folder_id`、各分支 `dir_ids` 與 `folder_meta` 重建 `RemoteEntry` 並呼叫 `transport.warm_folder_cache()` 寫入 `_folder_cache`，使後續 `mkdir` / `upload_file` 完全免除對既有父目錄的 `_list_children_raw` 查詢。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/gdrive-support/gdrive_support/transport.py
class AbstractSyncTransport(ABC):
    def reset_scan_state(self) -> None: ...
    def warm_folder_cache(self, entries: Dict[str, RemoteEntry]) -> None: ...
    @abstractmethod
    def download_file(
        self,
        remote_path: str,
        local_path: Path,
        entry_hint: Optional[RemoteEntry] = None,
    ) -> RemoteEntry: ...
    @abstractmethod
    def trash_file(
        self,
        remote_path: str,
        file_id: Optional[str] = None,
    ) -> bool: ...
    @abstractmethod
    def move_file(
        self,
        src_remote_path: str,
        dst_remote_path: str,
        entry_hint: Optional[RemoteEntry] = None,
    ) -> RemoteEntry: ...

# ys_codebase/source/gdrive-support/gdrive_support/coordinator.py
BRANCH_INTERNAL_SYSTEM_NAMES: Set[str]

class SyncCoordinator:
    def _warm_transport_folder_cache(self, state: Dict[str, Any], branch: str) -> None: ...
    def _prune_empty_remote_branch_dirs(
        self,
        state: Dict[str, Any],
        branch: str,
        curr_branch_files: Dict[str, str],
        deleted_remote_paths: List[str],
    ) -> List[str]: ...

# ys_codebase/source/gdrive-support/scripts/cli.py
def _build_coordinator(sandbox_dir: str = "") -> Tuple[Any, Any, Any]: ...

# ys_codebase/source/vscode-support/vscode_support/schema_compiler.py
class SchemaCompiler:
    def _select_latest_mirror_zip(self, mirror_dir: str) -> Optional[str]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `SyncCoordinator.run_sync()`：當 `not self.config.sync_spaces` 時立即拋出 `GDriveConfigError`。
  - `GoogleDriveApiTransport._request_json()`：遇 HTTP `401` 時在鎖保護下清除 `self._access_token` 與過期時間並重試一次；若仍失敗則拋出 `GDriveTransportError`。
- **階段決策紀錄**：`[P03:DR-01]` `download_file`、`trash_file` 與 `move_file` 新增之 `entry_hint` / `file_id` 參數均設為選填預設 `None`，100% 向後相容所有既有呼叫端與測試樁。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-08 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-06 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  1. *若外部測試替換了 `transport.upload_file` 或 `transport.trash_file` 為不接受新選填參數之單參數/雙參數函式怎麼辦？*
     - 防護解法：在 `AbstractSyncTransport` 與子類別方法簽名中提供選填參數 `entry_hint: Optional[RemoteEntry] = None` / `file_id: Optional[str] = None`，同時於 `SyncCoordinator` 內部呼叫時若傳遞選填參數，可保留標準位置參數或安全調用，確保既有測試中的 monkeypatch（如 `_spy_upload(local_path, remote_rel_path, in_place_file_id=None)`）100% 無縫相容。
  2. *清理遠端空資料夾時，若某新建立的空目錄不在 `curr_branch_files` 中是否會誤刪分支根目錄或系統目錄？*
     - 防護解法：嚴格限定僅針對當前分支下的子目錄（`rel_dir != ""` 且不在 `SYSTEM_NAMES` / `BRANCH_INTERNAL_SYSTEM_NAMES` 內），且確認無任何 `curr_branch_files` 以 `f"{rel_dir}/"` 開頭，並由最深層往上清理。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/gdrive-support/README.md` | N/A | 屬內部缺陷修復與快取預熱強化，不影響模組頂層概覽 |
| **專題手冊** | `docs/gdrive-support/DESIGN_NOTES.md` | N/A | 將於主計畫 Phase 07 結案時統一檢視同步 |
| **設計決策** | `docs/vscode-support/DESIGN_NOTES.md` | N/A | 將於主計畫 Phase 07 結案時統一檢視同步 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新關鍵介面契約與模組 Docstring（嚴守零工單編號註解） |
| **發布日誌** | `CHANGELOG.md` | N/A | 於模組正式版本發布時統一生成 |

- **決策定稿**：**[P04:DR-01]** 確認所有變更均落於 `sub_01` 授權範圍內，無跨模組寫入衝突。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `gdrive-support` 傳輸層強化（`transport.py`：`_cache_lock`、`reset_scan_state`、`warm_folder_cache`、`mkdir` 時間排序、`list_files` 非破壞性資料夾去重、HTTP 401 Token 重置刷新、`download_file` 退避重試與 `entry_hint`、`trash_file`/`move_file` 選填 `file_id`/`entry_hint`、`_resolve_shortcut_targets` 平行化及 `LocalSandboxTransport.upload_file` 鎖保護）
- [x] **TASK-02**：實作 `gdrive-support` 協調器與 CLI 隔離修復（`coordinator.py`、`scripts/cli.py`、`contribute.json`：空 `sync_spaces` 阻斷守衛、`IN_SYNC` `identical_digest` 基準線保護、`BRANCH_INTERNAL_SYSTEM_NAMES` 解耦、Level 1 `.`/`_` 子目錄放行、Level 0/1 `_folder_cache` 預熱、分層 BFS 平行 `_precreate_remote_dirs`、遠端空父目錄與孤兒空殼清理、紅線 1 非活躍分支快取守衛與 CLI `_build_coordinator` 沙盒隔離）
- [x] **TASK-03**：實作 `vscode-support` 鉤子守衛、Schema 自然版本排序與投影器加固（`hook.core.py`、`schema_compiler.py`、`projector.py`）
- [x] **TASK-04**：於 `gdrive-support/tests/` 與 `vscode-support/tests/` 既有子系統測試檔擴充完整正向與負向單元測試案例（`FT-01` ~ `FT-08`、`ET-01` ~ `ET-06`），並通過靜態檢查（`dev check` 與 `py_compile`）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
