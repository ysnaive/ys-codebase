# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：2026_11_05_0826_file_space_foundation_research  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Medium)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

> 本計畫已於啟動 `/auto` 前完成獨立 [`P01_requirements_spec.md`](./P01_requirements_spec.md) 定稿（涵蓋 `FR-01` ~ `FR-08`、`EC-01` ~ `EC-08`、`NFR-01` ~ `NFR-03` 與 `[P01:DR-01]` ~ `[P01:DR-03]`），以下為對齊摘要表。

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `FileSpaceConfig` 等價預編譯過濾與 `DirEntry.stat` 零冗餘遍歷 | 預編譯 `_exclude_exact_segments`、`_exclude_rel_exact`、`_exclude_rel_prefixes`、`_include_ext_suffixes` 與支援 `**/` 零層目錄之正則；保留 `iter_space_files` 三元組簽名並新增 `iter_space_files_with_stat`。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-02** | `FileSpaceWatcherServiceWorker` 路徑級增量 Patch 與目錄事件守門 | 前置過濾 `.git`/`.cache` 噪音；處理 `DirMovedEvent`/`DirDeletedEvent` 防幽靈殘留；新增 `patch_space_files(space_name, dirty_paths)` 與 `_pending_paths_by_space` 追蹤。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-03** | Watcher 活躍狀態精確判定與同進程零延遲 Flush 契約 | `is_watcher_active(project_root, space_name=None)` 檢查 `cfg.watch` 與 Watcher 實況；提供 `flush_space_now(space_name)` 消除同進程 500ms 防抖空窗。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-04** | `gdrive-support` 本地快照零冗餘 `stat` 管線對接 | `collect_space_local_files` 優先調用 `iter_space_files_with_stat`（對測試替身保持 fallback）並移除逐檔 `Path.resolve()`；`_collect_local_snapshot` 直接複用 `(mtime_ns, size)`。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-05** | `gdrive-support` 雲端 Level 1 拓撲序新建/移除子目錄增量修補 | 分支內無衝突新建子目錄按父子拓撲序掛載至 `dir_ids`；刪除子目錄時清理 `dir_ids`、`raw_entries` 與 `target_id_to_shortcuts` 跨分支 Shortcut。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-06** | 修復 `scanner.py` Racy-Clean `ctime_ns > prev_fp.mtime_ns` 永久快取擊穿與墓碑世代覆寫 | 移除 `ctime_ns > prev_fp.mtime_ns` 條件，防止 `os.utime`/`shutil.copy2` 檔案每次掃描重算雜湊；刪除後重建檔案保留原 `created_gen`。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-07** | `on_file_space_changed` 空間訂閱過濾與 `_diff_all_spaces` 動態世代聚合 | `ast/scripts/hook.file-space.py` 忽略非 AST 受管空間（如 `"cloud"`）；`_diff_all_spaces` 動態聚合子空間世代與 Merkle Root。 | P1 | [P00:DR-01], [P00:DR-03] |
| **FR-08** | `CursorStore` 跨進程原子寫入鎖與專案空間 Override 模式 | `CursorStore.ack`/`reset` 使用 `InterProcessLock` 保護；`FileSpaceManager._merge_project_space_override` 支援顯式 `"override_mode": "replace"`。 | P1 | [P00:DR-01], [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 含 `/` 目錄前綴排除與 `**/` 零層目錄匹配 | 同時支援精確匹配、`startswith(norm_pat + "/")` 與 `(?:.+/)?` 正則展開。 |
| **EC-02** | 多重重疊 `include` 根目錄 (`multi_root=True`) | 以正規路徑集合防止重複走訪同一子樹，並對齊 `_compute_rel_path` 多根計算。 |
| **EC-03** | Linux `inotify` 目錄改名 `mv` 或刪除 `rm -rf` | Watcher 捕獲目錄移動/刪除事件時標記該空間需完整重掃或清理該目錄前綴。 |
| **EC-04** | 大檔案 `LAZY_STABILIZED` 後無新事件 | 於 `_pending_paths_by_space` 保留待穩定檔案路徑，到期後由 `patch_space_files` 轉正雜湊。 |
| **EC-05** | 空間設定 `watch=False` 或無 `watchdog` | `is_watcher_active(project_root, space_name)` 回傳 `False`，自動觸發增量掃描。 |
| **EC-06** | 測試傳入僅有 `iter_space_files` 之替身 | `collect_space_local_files` 透過 `hasattr` 自動退回 `iter_space_files` + 單次 `stat()`。 |
| **EC-07** | 雲端根目錄 `<repo_sync_root>/` 新建分支或同名衝突 | `parent_id == repo_folder_id`、保留名或同名衝突時 `return None` 退回 Level 2（守護 `test_et_06`）。 |
| **EC-08** | 雲端刪除子目錄涉及跨分支 Shortcut | 同步查閱 `target_id_to_shortcuts` 移除其他分支指向被刪檔案之 Shortcut。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能（本地快照與增量掃描） | 無變更時 `gdrive sync` 本地快照收集 `< 0.5s`；Watcher 單檔變更更新 `YFP2` `< 0.05s`。 |
| **NFR-02** | 效能（雲端新增子目錄同步） | 分支內新建計畫子目錄命中 Level 1 拓撲修補（0 次 `list_files`），遠端階段 `< 1.0s`。 |
| **NFR-03** | 相容性與零破壞 | `file-space`、`gdrive-support`、`ast`、`knowledge-db` 測試 100% 通過，`YFP2` 格式不變。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 詳見 [`P01_requirements_spec.md`](./P01_requirements_spec.md) §4 之 `[P01:DR-01]` ~ `[P01:DR-03]`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[File System / Watchdog Event]
       │
       ├──► FileSpaceWatcherServiceWorker.notify_file_event(abs_path, is_dir, event_type)
       │       ├─ Fast prefix/segment ignore (.git, .cache, .storage.local, .modules) -> 0 syscall drop
       │       ├─ Directory moved/deleted -> mark _full_rescan_spaces[space]
       │       └─ File event -> _dirty_paths_by_space[space].add(abs_path)
       │
       ├──► flush_dirty_spaces() / flush_space_now(space_name)
       │       ├─ If space in _full_rescan_spaces or len(dirty) > threshold:
       │       │     scanner.scan_space(space_name)  [uses iter_space_files_with_stat + pre-compiled filters]
       │       └─ Else:
       │             scanner.patch_space_files(space_name, dirty_paths | pending_paths) -> O(|dirty|) YFP2 update
       │       └─ Broadcast on_file_space_changed(space_name) -> AST hook filters out "cloud" space
       │
[gdrive-support: yscb gdrive sync]
       │
       ├──► Local Snapshot (_collect_local_snapshot)
       │       └─ collect_space_local_files_with_stat("cloud") -> reuses DirEntry.stat() (mtime_ns, size)
       │          -> 0 Path.resolve(), 0 redundant stat() -> hits fingerprint_cache(mtime_ns, size) -> (md5, sha256)
       │
       └──► Remote Snapshot (_try_incremental_remote_cache Level 1)
               ├─ Folder removed -> purge b_data["dir_ids"] + b_data["raw_entries"] + target_id_to_shortcuts
               ├─ New folder at repo_folder_id or name conflict -> fallback to Level 2 (preserves test_et_06)
               └─ New subfolder under known branch dir -> topological parent-first registration into dir_ids -> 0 API calls
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/file-space/file_space/schema.py` | Modify | 於 `FileSpaceConfig` 預編譯等價排除與包含過濾結構（精確段名、含 `/` 前綴、純副檔名與 `**/` 展開正則）。 |
| `ys_codebase/source/file-space/file_space/manager.py` | Modify | 升級 `_is_dir_excluded` 使用預編譯過濾器；新增 `iter_space_files_with_stat` 複用 `os.DirEntry.stat()`；支援專案空間 Override `override_mode: "replace"`。 |
| `ys_codebase/source/file-space/file_space/scanner.py` | Modify | 修復 `is_racy` 之 `ctime_ns > prev_fp.mtime_ns` 永久快取擊穿與刪除重建 `created_gen` 覆寫；新增 `patch_space_files`；`is_watcher_active` 支援 `space_name` 與 `watch` 檢查；`_diff_all_spaces` 動態聚合世代；`CursorStore` 加入 `InterProcessLock`。 |
| `ys_codebase/source/file-space/file_space/service.py` | Modify | Watcher 前置快速過濾、支援目錄移動/刪除事件守門、路徑級 `_dirty_paths_by_space` 與 `_pending_paths_by_space` 增量刷新、同進程 `flush_space_now` 與活躍狀態記錄。 |
| `ys_codebase/source/ast/scripts/hook.file-space.py` | Modify | 於 `on_file_space_changed` 過濾非 AST 索引目標空間（如 `"cloud"`），消除單檔修改時的雙重 `hot_patch_index`。 |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | Modify | 新增 `collect_space_local_files_with_stat`（並最佳化 `collect_space_local_files` 移除逐檔 `Path.resolve()`，同時保持測試 fake 相容）。 |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | Modify | `_collect_local_snapshot` 改用 `collect_space_local_files_with_stat` 消除重複 `is_file()`/`stat()`；`_try_incremental_remote_cache` 實作雲端 Level 1 拓撲序新建/刪除子目錄修補與跨分支 Shortcut 清理。 |
| `ys_codebase/source/file-space/tests/test_fingerprint_scanner.py` | Modify | 新增預編譯過濾邊界、`ctime_ns > mtime_ns` Racy-Clean 快取命中、`patch_space_files` 增量更新、目錄移動/刪除與 `is_watcher_active(space_name)` 單元測試。 |
| `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py` | Modify | 新增 Level 1 拓撲序多層新建子目錄增量修補、刪除子目錄連動清理跨分支 Shortcut 及零冗餘本地快照收集測試。 |
| `docs/file-space/ARCHITECTURE.md` | Modify | 同步更新預編譯過濾、`iter_space_files_with_stat` 與 Watcher 路徑級增量 Patch 架構說明。 |
| `docs/gdrive-support/ARCHITECTURE.md` | Modify | 同步更新本地零冗餘 `stat` 快照管線與雲端 Level 1 拓撲子目錄修補機制說明。 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 雙層 `iter_space_files` 與 `iter_space_files_with_stat` 零破壞演進**：保留 `iter_space_files` 既有三元組 `(rel_path, abs_path, source_root)` 簽名，內部底層 `_walk_root` 直接產出 `os.DirEntry.stat()` 結果供 `iter_space_files_with_stat` 與 `FingerprintScanner._collect_space_entries` 消費，達成 0 外部破壞與 0 重複 `stat()`。
- **[P02:DR-02] Watcher 混合式增量更新（Hybrid Path-Patch + Fallback Full Scan）**：一般檔案增刪改走 $O(|\text{dirty}|)$ 的 `patch_space_files`；當遭遇目錄級移動/刪除或單批變更超過 200 檔時，自動標記 `_full_rescan_spaces` 退回加速版 `scan_space`，兼顧極致速度與 100% 狀態機強一致。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/file-space/file_space/manager.py
class FileSpaceManager:
    def iter_space_files_with_stat(
        self, space_name: str
    ) -> Iterator[Tuple[str, Path, Path, int, int, int]]: ...

# ys_codebase/source/file-space/file_space/scanner.py
def is_watcher_active(
    project_root: Optional[Path] = None,
    space_name: Optional[str] = None,
) -> bool: ...

class FingerprintScanner:
    def patch_space_files(
        self,
        space_name: str,
        dirty_paths: Iterable[Path],
        background: bool = False,
    ) -> SnapshotState: ...

# ys_codebase/source/file-space/file_space/service.py
class FileSpaceWatcherServiceWorker(BaseServiceWorker):
    def notify_file_event(
        self,
        abs_path: Path,
        is_directory: bool = False,
        event_type: str = "modified",
    ) -> List[str]: ...

    def flush_space_now(self, space_name: str) -> Optional[Dict[str, Any]]: ...

# ys_codebase/source/gdrive-support/gdrive_support/config.py
def collect_space_local_files_with_stat(
    space_name: str = DEFAULT_GDRIVE_SPACE_NAME,
    project_root: Optional[Path] = None,
    file_space_manager: Optional[Any] = None,
) -> List[Tuple[str, Path, Optional[int], Optional[int]]]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `iter_space_files_with_stat` 與 `patch_space_files` 於遇到未定義空間時拋出 `SpaceNotFoundError`；遍歷或單檔 `stat()` 期間若檔案瞬態消失（`FileNotFoundError` / `OSError`），安全忽略或標記刪除，不中斷整體掃描。
- **階段決策紀錄**：`[P03:DR-01]` `collect_space_local_files_with_stat` 回傳 `(rel_posix, abs_path, mtime_ns, size)`，當傳入僅支援 `iter_space_files` 之測試 fake 時，`mtime_ns` 與 `size` 由單次 `abs_path.stat()` 補齊，確保下游 `_collect_local_snapshot` 處理邏輯單一純淨。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-08 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-08 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  1. *若在 Linux 下對子目錄執行 `mv dir_a dir_b`，`patch_space_files` 是否會漏掉子檔案？*
     - 防護：`_FileSpaceWatchdogHandler` 將目錄之 `moved`/`deleted` 事件轉發至 `notify_file_event(..., is_directory=True, event_type=...)`，將該空間列入 `_full_rescan_spaces`，於防抖後執行完整空間重掃，100% 捕捉目錄級拓撲變更。
  2. *若 Google Drive 遠端直接在 `<repo_sync_root>/` 建立新分支資料夾，Level 1 是否會吞掉而未寫入 `.yscb_gdrive.json`？*
     - 防護：`_try_incremental_remote_cache` 明確檢查新建資料夾之 `parent_id == repo_folder_id`，一旦命中立即 `return None` 退回 Level 2 觸發 `_reconcile_unregistered_cloud_branches()`。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/file-space/README.md` | N/A | 公開 CLI 無變更 |
| **專題手冊** | `docs/file-space/ARCHITECTURE.md`、`docs/gdrive-support/ARCHITECTURE.md` | Modify | 更新預編譯過濾、Watcher 路徑級增量 Patch、零冗餘本地快照與雲端 Level 1 拓撲子目錄修補 |
| **設計決策** | `docs/file-space/DESIGN_NOTES.md` | Modify | 補充 Racy-Clean `ctime_ns` 防擊穿與混合式 Watcher Patch 設計筆記 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新新增與修改方法之公開契約 Docstring（嚴守零工單編號鐵律） |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄本計畫發布摘要 |

- **決策定稿**：**[P04:DR-01]** 確認規格、邊界與文檔衝擊無誤，進入 `Pre-Code Analyze Gate` 與實作階段。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `file-space` 底層引擎升級（`schema.py` 預編譯過濾、`manager.py` `iter_space_files_with_stat` 與 Override 模式、`scanner.py` Racy-Clean 修復/`patch_space_files`/`is_watcher_active`/`CursorStore` 鎖/`_diff_all_spaces`、`service.py` 路徑級增量 Watcher 與目錄事件守門）及 `ast` hook 空間過濾（`FR-01`~`FR-03`, `FR-06`~`FR-08`）
- [x] **TASK-02**：實作 `gdrive-support` 雙端增量升級（`config.py` `collect_space_local_files_with_stat` 與移除逐檔 `resolve`、`coordinator.py` `_collect_local_snapshot` 零冗餘 `stat` 與 `_try_incremental_remote_cache` 雲端 Level 1 拓撲序新建/刪除子目錄修補與跨分支 Shortcut 清理）（`FR-04`, `FR-05`）
- [x] **TASK-03**：編寫與執行 `file-space`、`gdrive-support`、`ast`、`knowledge-db` 單元測試與邊界條件回歸測試（`EC-01`~`EC-08`）
- [x] **TASK-DOC**：同步更新 `docs/file-space/ARCHITECTURE.md`、`docs/file-space/DESIGN_NOTES.md`、`docs/gdrive-support/ARCHITECTURE.md` 與源碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

