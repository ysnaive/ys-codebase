# 需求規格說明書 (Requirements Specification)

> 功能名稱：2026_11_05_0826_file_space_foundation_research  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Medium)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `FileSpaceConfig` 等價預編譯過濾與 `DirEntry.stat` 零冗餘遍歷 (`FS-01`) | 1. 於 `FileSpaceConfig.__post_init__` 將 `exclude` 與 `file_patterns` 預先分類編譯為 $O(1)$ `_exclude_exact_segments`、`_exclude_rel_exact`、`_exclude_rel_prefixes`（含尾隨 `"/"`）、`_include_ext_suffixes` 及支援 `**/` 零或多層目錄語意的正則，與既有 `is_file_included` / `_is_dir_excluded` 語意 100% 等價（`[P01:DR-01]`）。<br>2. `FileSpaceManager.iter_space_files(space_name)` 維持原簽名 `Iterator[Tuple[str, Path, Path]]`；新增 `iter_space_files_with_stat(space_name)` 產出 `(rel_path, abs_path, source_root, mtime_ns, ctime_ns, size)`，直接複用 `os.DirEntry.stat()`，當 `follow_symlinks=False` 時免除目錄級 `current_dir.stat()`。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-02** | `FileSpaceWatcherServiceWorker` 路徑級增量 Patch 與目錄事件守門 (`FS-02`) | 1. `notify_file_event` 於 `Path.resolve()` 前以字串分段快速過濾 `.git`、`.cache`、`.storage.local`、`.modules` 噪音，並將有效檔案路徑記錄於 `_dirty_paths_by_space[space_name]`。<br>2. 修正 `_FileSpaceWatchdogHandler` 忽略 `event.is_directory` 的盲點：當收到目錄級 `DirMovedEvent` 或 `DirDeletedEvent` 時，將所屬空間標記入 `_full_rescan_spaces`（或展開處理該目錄前綴），防止 `mv/rm -rf` 目錄造成幽靈項目殘留。<br>3. 新增 `FingerprintScanner.patch_space_files(space_name, dirty_paths)`，以 $O(\|\text{dirty}\|)$ 局部更新 `state.entries`（刪除項目原地標記 `is_deleted=True, updated_gen=next_gen`），並將 `pending_stabilization` 路徑精確保留至下一輪重刷。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-03** | Watcher 活躍狀態精確判定與同進程零延遲 Flush 契約 (`FS-03`) | 1. `is_watcher_active(project_root, space_name=None)` 必須同時核驗 Daemon 存活、Watcher 實際啟用（非空轉）且目標空間 `cfg.watch == True`。<br>2. 當在常駐 Server Worker 進程內消費空間快照或 diff 時，若 `FileSpaceWatcherServiceWorker` 尚有待 flush 之 dirty 項目，提供 `flush_space_now(space_name)` 同步完成毫秒級增量 patch，消除 500ms 防抖空窗時間差。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-04** | `gdrive-support` 本地快照零冗餘 `stat` 管線對接 (`FS-04`) | 1. `collect_space_local_files` 優先調用 `fs_mgr.iter_space_files_with_stat(space_name)`（若為僅實作 `iter_space_files` 之測試 fake 則自動 fallback），並移除逐檔 `Path(abs_path).resolve()`。<br>2. `SyncCoordinator._collect_local_snapshot` 直接使用傳入之 `(mtime_ns, size)`（或已同步之 `cloud.yfp2.bin` 活躍項目）查詢 `state_store.get_cached_hashes(rel_path, mtime_ns, size)`，免除逐檔重複呼叫 `abs_path.is_file()` 與 `abs_path.stat()`（`[P01:DR-02]`）。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-05** | `gdrive-support` 雲端 Level 1 拓撲序新建/移除子目錄增量修補 (`FS-05`) | 1. 於 `SyncCoordinator._try_incremental_remote_cache` 中，針對 `parent_id` 位於已知分支 `all_branch_dir_ids[b_name]` 內的新建子資料夾，按父子拓撲序解析 `rel_dir` 並註冊進 `b_data["dir_ids"]`、`known_folder_ids` 與 `folder_meta`，使同批次新建子目錄內之檔案在 Level 1 完成 0 額外網路請求修補。<br>2. 當已知分支子目錄被刪除（`ch.removed or is_trashed` 且 `rel_dir != ""`）時，從 `b_data["dir_ids"]` 與 `b_data["raw_entries"]` 移除該目錄前綴之所有子目錄與檔案，並同步清理 `target_id_to_shortcuts` 關聯之跨分支懸空 Shortcut（`[P01:DR-03]`）。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-06** | 修復 `scanner.py` Racy-Clean `ctime_ns > prev_fp.mtime_ns` 永久快取擊穿與墓碑世代覆寫 (`FS-06`) | 1. 移除 `FingerprintScanner._evaluate_entry_fingerprint` 中 `prev_fp is not None and ctime_ns > prev_fp.mtime_ns` 的錯誤條件（僅保留 `scan_start_ns` 與 `mtime_ns`/`ctime_ns` 落在 `RACY_CLEAN_WINDOW_NS` 視窗內之判定），解決經 `os.utime` / `shutil.copy2` 處理後檔案永久重算雜湊之問題。<br>2. 當 `prev_fp is not None and prev_fp.is_deleted` 的路徑重新建立檔案時，保留原 `created_gen=prev_fp.created_gen` 並更新 `updated_gen=next_gen_candidate, is_deleted=False`。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-07** | `on_file_space_changed` 空間訂閱過濾與 `_diff_all_spaces` 動態世代聚合 (`FS-07`) | 1. 於 `ast/scripts/hook.file-space.py` 中，當事件傳入之 `target_space`（或單一 `spaces`）不在 `engine` 目標空間內（如 `"cloud"` 空間變動事件）時，直接返回 `{"status": "noop", "patched_count": 0}`，避免對同一原始碼檔案重複執行兩次 `hot_patch_index`。<br>2. 於 `FingerprintScanner._diff_all_spaces()` 中，動態由各子空間之最新世代與 Merkle Root 聚合計算 `to_generation` 與 `merkle_root`，不再受限於未更新之靜態 `unified.yfp2.bin`。 | P1 | [P00:DR-01], [P00:DR-03] |
| **FR-08** | `CursorStore` 跨進程原子寫入鎖與專案空間 Override 模式 (`FS-08`) | 1. `CursorStore` 之讀寫修改（`ack` / `reset`）納入 `InterProcessLock` 保護，防止多消費者併發覆蓋 `cursors.json`。<br>2. `FileSpaceManager._merge_project_space_override` 支援顯式 `"override_mode": "replace"`（或於預設模式下對齊專案覆寫語意），允許專案層精準控制空間配置。 | P1 | [P00:DR-01], [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 含 `/` 目錄前綴排除與 `**/` 零層目錄匹配（如 `ys_codebase/.modules` 與 `ast` 注入之 `**/.storage.local/**`） | 預編譯過濾器必須同時支援 `posix_str == norm_pat`、`posix_str.startswith(norm_pat + "/")` 與 `**/` 匹配零層或多層目錄，確保深層子路徑 `ys_codebase/.modules/foo/bar.py` 100% 被攔截。 |
| **EC-02** | 單一空間包含父子重疊之多個 `include` 根目錄（`multi_root=True`） | `_walk_root` 以正規化目錄路徑集合 `visited_dir_paths` 防止重複走訪同一實體子樹，且 `patch_space_files` 嚴格使用 `manager._compute_rel_path(..., multi_root=len(inc_roots) > 1)` 計算一致鍵值。 |
| **EC-03** | Linux `inotify` 下直接執行目錄改名 `mv dir_a dir_b` 或刪除 `rm -rf dir_a` | `_FileSpaceWatchdogHandler` 捕獲 `is_directory=True` 之移動/刪除事件時，將該空間標記入 `_full_rescan_spaces`（或掃描受影響目錄前綴），確保 `dir_a/*` 標記為 `is_deleted=True` 且 `dir_b/*` 入庫。 |
| **EC-04** | 大檔案處於 `LAZY_STABILIZED` (`pending_stabilization=True`) 後無後續檔案修改事件 | `FileSpaceWatcherServiceWorker` 將待穩定檔案之具體 `abs_path` 存入 `_pending_paths_by_space`，於延遲到期後交由 `patch_space_files` 重算真實雜湊並清除 `pending_stabilization`。 |
| **EC-05** | 目標空間設定為 `watch=False` 或宿主環境未安裝 `watchdog` | `is_watcher_active(project_root, space_name)` 回傳 `False`，促使 `consume_diff(auto_refresh=None)` 自動觸發 `FS-01` 加速版增量掃描，絕不返回過期快照。 |
| **EC-06** | 單元測試傳入僅實作 `iter_space_files` 的 Duck-Typed 替身（如 `_FakeFileSpaceManager`、`_SimpleFileSpaceManager`） | `collect_space_local_files` 檢查 `hasattr(fs_mgr, "iter_space_files_with_stat")`；若無則平滑退回 `fs_mgr.iter_space_files(space_name)` 並執行單次 `abs_path.stat()`。 |
| **EC-07** | 雲端根目錄 `<repo_sync_root>/` 下直接新增未知分支資料夾（`ch.parent_id == repo_folder_id`）或同名資料夾衝突 | `_try_incremental_remote_cache` 偵測到 `parent_id == repo_folder_id`、系統保留名（`SYSTEM_NAMES` 或 `.` / `_` 開頭）或同名衝突時，立即 `return None` 安全退回 Level 2，100% 守護 `test_et_06` 雲端新分支自動註冊契約。 |
| **EC-08** | 雲端某分支刪除子目錄，而另一分支存有指向該目錄內檔案之 Google Drive Shortcut | Level 1 移除該子目錄下之 `raw_entries` 時，一併查表 `target_id_to_shortcuts`，將其他分支中指向被刪 `file_id` 的 Shortcut 同步移除，防止跨分支懸空引用。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能（本地快照與增量掃描） | 於 2,200+ 檔案之容器掛載環境下，無變更時 `gdrive sync` 本地快照收集耗時由 `35~40s` 降至 `< 0.5s`；Watcher 單檔變更增量更新 `YFP2` 耗時由 `35s` 降至 `< 0.05s`。 |
| **NFR-02** | 效能（雲端新增子目錄同步） | 於新建計畫子目錄（含多個子檔案）場景下，`gdrive sync` 遠端快照獲取直接命中 Level 1 拓撲修補（0 次 `list_files` 遞迴請求），遠端階段耗時由 `138s` 降至 `< 1.0s`。 |
| **NFR-03** | 相容性與零破壞 | 100% 通過 `file-space`、`gdrive-support`、`ast`、`knowledge-db` 既有單元測試與邊界測試套件，不改變 `YFP2` 二進位序列化格式。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` 階段決策紀錄**：
  - **`[P01:DR-01]` 預編譯過濾器語意等價契約**：不依賴單純的 `fnmatch.translate` 跨段匹配，而是將精確段名、含 `/` 之路徑前綴、純副檔名與含萬用字元模式分層處理，徹底避免 `ys_codebase/.modules` 前綴逃逸或 `*.py` 跨 `/` 誤判。
  - **`[P01:DR-02]` 雜湊職責邊界**：`file-space` 維持高速 20-byte Blake2b (`40 hex`) / 大檔取樣雜湊；`gdrive-support` 透過 `iter_space_files_with_stat` 共享 `(mtime_ns, size)` 零 `stat` 命中其 `fingerprint_cache` 之 `(md5, sha256)`，不強行混用兩種雜湊演算法。
  - **`[P01:DR-03]` Level 1 雲端資料夾拓撲修補安全圍欄**：僅對嚴格位於既有分支目錄樹內（`parent_id in all_branch_dir_ids`）之無衝突新子目錄執行記憶體拓撲掛載；凡涉及根目錄新分支（`parent_id == repo_folder_id`）或已知資料夾跨目錄搬移/改名，一律退回 Level 2 全掃以確保絕對安全。

