# 專題調研與分析報告：`module:file-space` 底層架構打通與潛力解放專題調研 (R01_file_space_foundation_research.md)

> 調研主題：`module:file-space` 底層架構打通與 `gdrive-support` 雙端增量整合調研  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Medium)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - `module:file-space` 為 YS-Codebase 生態系中僅依賴 `core` 的第二大底層基座，承載了全系統「命名檔案空間幾何映射（`FileSpaceManager`）」、「雙階段單調世代指紋與 `YFP2` 快照（`FingerprintScanner` / `BinarySnapshotManager`）」、「多消費者獨立游標（`CursorStore`）」以及「常駐背景變動監聽（`FileSpaceWatcherServiceWorker`）」。
  - 在實際高頻開發與 `yscb gdrive sync` 雲端同步場景中，實測發現兩大顯著延遲痛點：
    1. **本地端掃描瓶頸（每次固定耗時 `33~40s`）**：即便遠端 Google Drive 命中 Level 0 Changes Token 快取（僅需 `~0.3s`），`gdrive sync` 仍耗時 `33~40s`；追蹤發現 `gdrive-support` 完全繞過了 `file-space` 的 `cloud.yfp2.bin` 二進位快照與常駐 Watcher，每次重新實例化 `FileSpaceManager` 跑 `iter_space_files("cloud")`，且在容器跨宿主掛載（`virtiofs` / bind mount）環境下對 2,200+ 個檔案執行了 5~6 次重複的 `stat()` 與 `Path.resolve()`（單次同步觸發逾 `12,000+` 次跨邊界 metadata syscall）。
    2. **背景監聽與雲端新增子目錄退化瓶頸（`35s` 全掃與 `138s` 遠端遞迴全掃）**：
       - `file-space` 的 `FileSpaceWatcherServiceWorker` 雖透過 `watchdog` 收到具體變動檔案路徑，但 `notify_file_event()` 僅將整個空間標記為 dirty（丟棄具體路徑），導致單一檔案存檔即觸發 `scanner.scan_space()` 重新遍歷全專案數千檔案（耗時 `~35s`）。
       - `gdrive-support` 的雲端 Level 1 增量引擎（`_try_incremental_remote_cache`）在遇到「新建計畫子目錄」（如立項 `plans/2026_11_05_.../`）時，因新建資料夾之 `file_id` 尚不在快取 `known_folder_ids` 中，直接放棄 Level 1 並退回 Level 2 全量遞迴掃描（耗時 `138s`，加上本地掃描總計 `179s`）。
- **調研目標與範疇（追溯錨點 `[P00:DR-01]`、`[P00:DR-02]`）**：
  1. 徹底解剖 `ys_codebase/source/file-space/file_space/`（`schema.py`、`manager.py`、`scanner.py`、`service.py`）之系統呼叫熱點、過濾演算法複雜度、Watcher 增量更新粒度與跨程序快照共享契約。
  2. 解剖 `ys_codebase/source/gdrive-support/gdrive_support/`（`config.py`、`coordinator.py`）與 `file-space` 之整合斷層，以及雲端 Level 1 子目錄增量修補機制。
  3. 制定一套內聚、無損向後相容的五項核心架構改造規範（`FS-01` ~ `FS-05`），作為後續實作計畫的唯一架構藍圖。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 痛點實證與鏈路耗時量化剖析

以下為當前 `yscb gdrive sync` 與 `file-space` 背景掃描在 2,200+ 檔案規模（容器 `virtiofs` 掛載）下的實測耗時分解：

| 執行階段 / 模組鏈路 | 無變更（Level 0 命中）現況 | 單檔修改（Level 1 命中）現況 | 新建子目錄（如新計畫立項）現況 | 根因定位 |
| :--- | :---: | :---: | :---: | :--- |
| **1. 本地端快照收集 (`_collect_local_snapshot`)** | `33.0 ~ 40.0s` | `35.0 ~ 40.0s` | `38.0 ~ 41.0s` | 繞過 `cloud.yfp2.bin`；每個檔案重複呼叫 `is_symlink/is_dir/is_file` + `Path.resolve()` + 雙重 `stat()` |
| **2. 遠端快照獲取 (`_fetch_remote_tree_cached`)** | `0.25 ~ 0.35s` (Level 0) | `0.6 ~ 1.2s` (Level 1) | `135.0 ~ 140.0s` (**退回 Level 2**) | `_try_incremental_remote_cache` 遇到 `not ch.removed` 之未知 `folder_id` 直接 `return None` |
| **3. `file-space` Watcher 單檔變更刷新 (`flush_dirty_spaces`)** | `0s` | `32.0 ~ 36.0s` (背景全掃) | `32.0 ~ 36.0s` (背景全掃) | `notify_file_event` 丟棄檔案路徑，強制對整個 Space 重跑 `scan_space()` 全量 `os.scandir` |
| **端到端總耗時 (`gdrive sync`)** | **`33.5 ~ 40.5s`** | **`36.0 ~ 42.0s`** | **`175.0 ~ 180.0s`** | **I/O 與網路雙重全掃放大** |

---

### 2.2 五大核心架構瓶頸與根因解剖 (`FS-01` ~ `FS-05`)

#### [FS-01] `FileSpaceConfig` 過濾規則未預編譯 & `FileSpaceManager._walk_root` 重複 `stat()` / `Path.resolve()`
- **現況代碼定位**：
  - `ys_codebase/source/file-space/file_space/schema.py:L93-130` (`FileSpaceConfig.is_file_included`)
  - `ys_codebase/source/file-space/file_space/manager.py:L739-843` (`_walk_root`、`_is_dir_excluded`)
  - `ys_codebase/source/gdrive-support/gdrive_support/config.py:L528-556` (`collect_space_local_files`)
- **根因剖析**：
  1. **字元級重複 `fnmatch` 迴圈**：`FileSpaceConfig.is_file_included` 與 `_is_dir_excluded` 對每個目錄與檔案的每一個 path part 執行雙層迴圈 `fnmatch.fnmatch(part, pat)`。每次呼叫 `fnmatch` 都會透過 `_compile_pattern`（LRU cache 雖存在，但仍需逐段函式呼叫與正則匹配）。對於 `cloud` 空間（15+ 條 exclude patterns，2,200+ 檔案 × 平均 5 層路徑深度），單次遍歷產生逾 **165,000+ 次 `fnmatch` 呼叫**。
  2. **`_walk_root` 忽略 `os.DirEntry` 快取之 `stat_result`**：
     - `_walk_root` (`manager.py:L750`) 先對每個目錄額外呼叫 `current_dir.stat()` 取得 `(st_dev, st_ino)`（即便 `follow_symlinks=False` 不可能發生 symlink 環路，仍無條件 `stat`）。
     - 接著對每個 `entry` 呼叫 `entry.is_symlink()`、`entry.is_dir()`、`entry.is_file()`，最後只 `yield Path(entry.path)`，**將 `os.scandir` 底層已持有的 `DirEntry` 丟棄**。
     - 下游 `FingerprintScanner._evaluate_entry_fingerprint` (`scanner.py:L1135`) 或 `gdrive-support` 收到 `Path` 後，被迫再次呼叫 `abs_path.stat()`。
  3. **`collect_space_local_files` 與 `_collect_local_snapshot` 的冗餘 Syscall 鏈**：
     - `collect_space_local_files` (`config.py:L547`) 對 `iter_space_files` 產出的每個 `abs_path` 執行 `abs_path = Path(abs_path).resolve()`。在 Python `pathlib` 中，`resolve()` 會沿路徑對每一層執行 `lstat`/`readlink`；而在 `follow_symlinks=False` 且 `inc_root` 已預先 `resolve()` 的前提下，`entry.path` 本身即為正規絕對路徑，完全不需要逐檔 `resolve()`。
     - `coordinator.py:L1614` 先呼叫 `if not abs_path.is_file():`（第 1 次 `stat`），`L1621` 又呼叫 `st = abs_path.stat()`（第 2 次 `stat`）。

#### [FS-02] `FileSpaceWatcherServiceWorker` 缺乏路徑級 Dirty Queue 與前置快速過濾
- **現況代碼定位**：
  - `ys_codebase/source/file-space/file_space/service.py:L114-149` (`_SpaceEventHandler`)
  - `ys_codebase/source/file-space/file_space/service.py:L302-383` (`notify_file_event`、`flush_dirty_spaces`)
- **根況剖析**：
  1. **`watchdog` 監聽根目錄包含高頻寫入黑盒區**：當空間包含 `project://`（如 `cloud` 或 `workspace`）時，`observer.schedule(handler, str(inc_dir), recursive=True)` 會監聽整個 `/workspace/ys-codebase`，包含 `.git/`、`ys_codebase/.cache/`、`ys_codebase/.storage.local/`、`ys_codebase/.modules/`。任何 log 寫入、快照更新或索引寫入都會觸發 `watchdog` 事件進入 `notify_file_event(abs_path)`。
  2. **`notify_file_event` 每次執行高成本 `Path.resolve()`**：`file_belongs_to_space()` (`manager.py:L622`) 第一行即呼叫 `target = Path(file_path).resolve()`，導致 `.cache` 或 `.git` 的背景寫入事件也觸發跨系統呼叫。
  3. **丟棄變動檔案路徑，退化為全量 `scan_space()`**：`notify_file_event` 確認某檔案屬於空間 `s_name` 後，僅執行 `self._dirty_spaces.add(s_name)`，**完全丟棄了 `abs_path`**！防抖計時器到期後，`flush_dirty_spaces()` 呼叫 `self.scanner.scan_space(s_name)`，對整個空間重跑 `os.scandir` 全量遍歷（耗時 `~35s`）。

#### [FS-03] `FingerprintScanner` 缺乏跨程序「信任活躍 Watcher 快照 (`get_live_state`)」之零 I/O 直讀契約
- **現況代碼定位**：
  - `ys_codebase/source/file-space/file_space/scanner.py:L691-755` (`scan_space`)
  - `ys_codebase/source/file-space/file_space/scanner.py:L947-961` (`snapshot`)
  - `ys_codebase/source/file-space/file_space/service.py:L80-108` (`is_watcher_active`)
- **根因剖析**：
  1. `BinarySnapshotManager.load(space_name)` 載入 `cloud.yfp2.bin`（含完整 `active_entries: Dict[str, FileFingerprint]`、`mtime_ns`、`size`、`sha256`、`source_root`、`merkle_root`、`config_hash`）僅需 **`~1.5ms`**。
  2. 然而 `scanner.scan_space()` 與 `scanner.diff()` 預設每次都會執行 `_collect_space_entries()`（全量磁碟遍歷），而 `scanner.snapshot(refresh_first=False)` 雖然只讀 `YFP2`，但卻：
     - 未校驗當前 `config_hash` 是否與 `YFP2` 標頭一致；
     - 未結合 `is_watcher_active(project_root)` 判斷常駐 Watcher 是否正在即時維護該 `YFP2`；
     - 當 `is_watcher_active()` 為 `True` 時，若有極短防抖視窗內（例如 `< 0.5s`）剛寫入的檔案尚未 flush，消費者無法透過輕量 IPC 或檔案新鮮度確保一致。

#### [FS-04] `gdrive-support` 本地端快照收集與 `file-space` `YFP2` 脫節
- **現況代碼定位**：
  - `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py:L1599-1662` (`_collect_local_snapshot`)
  - `ys_codebase/source/gdrive-support/gdrive_support/config.py:L528-556` (`collect_space_local_files`)
- **根因剖析**：
  1. `gdrive-support` 的 `cloud` 空間已註冊於 `ys_codebase/config/file-space/contribute.json:L49-79`。
  2. `cloud.yfp2.bin` 內的每一筆 `FileFingerprint` 已經儲存了 `path`（相對於 `source_root`）、`source_root`、`size`、`mtime_ns` 與 `sha256`。
  3. 只要 `file-space` 提供 `iter_space_files_with_stat(space_name, use_live_snapshot=True)`（當 Watcher 活躍且 `YFP2` 之 `config_hash` 匹配時直接從 `YFP2` 讀取 `(rel_path, abs_path, mtime_ns, size, sha256)`，否則執行優化後的單次 `DirEntry.stat()` 遍歷並同步更新 `YFP2`），`gdrive-support` 在 `_collect_local_snapshot()` 中：
     - 直接以 `(mtime_ns, size)` 命中 `fingerprint_cache` 取得 `(md5, sha256)`（甚至 `sha256` 可直接複用 `FileFingerprint.sha256`！）；
     - 本地端收集 2,200+ 個檔案的耗時將從 **`35~40s` 驟降至 `< 0.02s`（20 毫秒內）**！

#### [FS-05] `gdrive-support` 雲端 Level 1 增量引擎對「新建/刪除子目錄」直接放棄並退回 Level 2 全掃
- **現況代碼定位**：
  - `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py:L1873-2085` (`_try_incremental_remote_cache`)
- **根因剖析**：
  1. 在 `coordinator.py:L1960-1987` 中，當 `changes.list` 回傳 `is_folder_change`（`mimeType == 'application/vnd.google-apps.folder'`）：
     - 若為**新建資料夾**（`not ch.removed` 且 `fid not in known_folder_ids`），`L1985-1987` 直接判定「無法安全得知其內部子樹與歸屬路徑」並 `return None`，強制退回 Level 2 對遠端所有分支執行遞迴 `list_files`（耗時 `~138s`）。
     - 若為**刪除/移出資料夾**（`ch.removed or is_trashed` 且 `fid in known_folder_ids`），`L1965-1967` 也直接 `return None`。
  2. **為什麼可以在 Level 1 內 100% 安全處理？**
     - Google Drive 的 `changes.list` 會在同一個變更批次中回傳**所有新建的資料夾項目及其下的新建檔案項目**（因為每個新建的 Google Drive 檔案與子資料夾都有獨立的 `change` 紀錄，且帶有 `parents: [parent_id]` 與 `name`）。
     - 只要對 `dedup_changes` 中的新建資料夾按**拓撲層級（Parent-first Topological Resolution）**迭代解析：
       - 若某新建資料夾 `fid` 的 `parent_id` 位於已知的 `all_branch_dir_ids[b_name]`（映射表 `dir_id -> rel_dir_path`）中，則該新建資料夾的相對路徑即為 `f"{parent_rel}/{ch.name}"`（若 `parent_rel == ""` 則為 `ch.name`）！
       - 將 `(fid, rel_dir_path)` 動態註冊進 `all_branch_dir_ids[b_name]`、`known_folder_ids` 與 `folder_meta`；若存在多層嵌套新建子目錄（如 `plans/archived/2026/11/plan_x`），透過 `while progress:` 拓撲推進即可在 $O(D)$ 記憶體迭代內全部解析完畢。
       - 同理，當已知資料夾 `fid` 被移除（`ch.removed` 或 `is_trashed`）時，從 `all_branch_dir_ids[b_name]` 找出其 `rel_dir_path`，並將所有位於 `rel_dir_path` 或以 `f"{rel_dir_path}/"` 為前綴的子目錄與快取檔案一併從 `cache_branches[b_name]` 移除即可。
       - 唯有當某個變更項目的 `parent_id` 屬於某個「既不在原本 `known_folder_ids`、也不在本次 `changes` 新建資料夾集合中」的未知外部資料夾（例如將一個既有非空資料夾從雲端硬碟其他位置整個拖曳移入專案目錄），才需要安全退回 Level 2（或僅針對該新移入資料夾呼叫單次 `_list_tree_recursive`）。

---

### 2.3 候選架構設計與演進方案（經 `/blind-subagent` 雙軌盲審補強之 `FS-01` ~ `FS-08` 規格詳解）

以下規格已整合兩名盲眼子代理（原型 ③ Devil's Advocate 反向事實查驗 + 原型 ① 無假設盲眼探索）所發掘之 12 項邊界不變量修正與 3 項新增底層盲點（`FS-06` ~ `FS-08`）：

#### 方案一：`FS-01` — `FileSpaceConfig` 等價預編譯過濾器與 `DirEntry` 零冗餘遍歷引擎
1. **`FileSpaceConfig` 語意 100% 等價之預編譯快取 (`schema.py:L93-130`, `manager.py:L826-843`)**：
   - **盲審修正（防跨段萬用字元與目錄前綴逃逸）**：
     - 不含 `/` 與萬用字元 `*?[` 之 `exclude` 項目（如 `.git`、`__pycache__`、`.venv`）編譯為 `_exclude_exact_segments: frozenset[str]`，以 $O(1)$ `bool(parts_set & _exclude_exact_segments)` 攔截。
     - 含 `/` 但不含萬用字元 `*?[` 之 `exclude` 項目（如 `ys_codebase/.modules`、`ys_codebase/.storage.local`）編譯為 `_exclude_rel_exact: frozenset[str]` 與 `_exclude_rel_prefixes: tuple[str, ...]`（自帶尾隨 `"/"`），以 `posix_str in _exclude_rel_exact or posix_str.startswith(_exclude_rel_prefixes)` $O(1)$ 攔截，完整保留目錄前綴排除語意。
     - 針對 `ast` 等動態注入之 `f"{rel_st}/**"` 與 `f"**/{rel_st}/**"`（`ast_engine/engine.py:L392`）及其他含萬用字元模式，分別針對單段（`part`）與相對路徑（`posix_str`）預編譯正則，並確保 `**/` 轉換為 `(?:.+/)?`（可匹配 0 或多層目錄），同時保留 `posix_str.startswith(norm_pat + "/")` 相容性。
     - 針對 `file_patterns`（如 `*.py`、`*.md`），將純副檔名模式提取為 `_include_ext_suffixes: tuple[str, ...]` 針對 `filename` 做 $O(1)$ `filename.endswith(...)` 匹配，避免 `fnmatch.translate` 將 `*` 轉為跨 `/` 之 `.*`。
2. **`FileSpaceManager` 零冗餘 `DirEntry` 走訪與簽名相容 (`manager.py:L724-825`)**：
   - **盲審修正（保留三元組簽名與多根去重）**：
     - 既有 `iter_space_files(space_name)` **嚴格維持原簽名 `Iterator[Tuple[str, Path, Path]]`**（產出 `(rel_path, abs_path, source_root)`），確保 `ast`、`knowledge-db`、`gdrive-support` 與測試替身 100% 相容。
     - 新增 `iter_space_files_with_stat(space_name: str) -> Iterator[Tuple[str, Path, Path, int, int, int]]`，額外一併產出 `os.DirEntry.stat()` 已快取之 `(mtime_ns, ctime_ns, size)`，供 `FingerprintScanner` 與 `gdrive-support` 免二次 `stat()` 直接消費。
     - 當 `follow_symlinks=False` 時免除目錄級 `current_dir.stat()`；若單一空間配置多個 `include` 根目錄（`len(inc_roots) > 1`），改以正規路徑字串集合 `visited_dir_paths: Set[str]` 阻擋父子重疊 `include` 二次走訪同一子樹。

#### 方案二：`FS-02` — `FileSpaceWatcherServiceWorker` 前置過濾、目錄級事件守門與路徑級增量 Patch (`patch_space_files`)
1. **Watcher 事件前置快速攔截與目錄事件守門 (`service.py:L114-180, L302-398`)**：
   - **前置 0-syscall 噪音過濾**：於 `notify_file_event` 執行 `Path.resolve()` 前，先以字串切片/分段檢查是否命中 `.git`、`ys_codebase/.cache`、`ys_codebase/.storage.local`、`ys_codebase/.modules` 等排除前綴。
   - **盲審修正 A（目錄移動/刪除事件處理）**：修正 `service.py:L173` 無條件忽略 `event.is_directory` 之盲點——當 `watchdog` 收到目錄級 `DirMovedEvent` 或 `DirDeletedEvent` 時，因 Linux `inotify` 不會為目錄內既有子檔案逐一發送檔案事件，將該目錄路徑（或將該空間標記入 `_full_rescan_spaces` / 掃描該目錄前綴）納入處理，彻底杜絕 `mv dir_a dir_b` 或 `rm -rf dir_a` 造成幽靈項目殘留。
   - **盲審修正 B（`LAZY_STABILIZED` 待穩定項目追蹤）**：當 `scan_space` 或 `patch_space_files` 發現 `fp.pending_stabilization == True` 時，將該檔案之具體 `abs_path` 記錄於 `self._pending_paths_by_space[s_name]`，確保 2 秒後重刷時能精確重驗該檔案並轉正為真實雜湊，不會因無新 watchdog 事件而餓死。
2. **`FingerprintScanner.patch_space_files(space_name, dirty_paths)` (`scanner.py:L691-771`)**：
   - **盲審修正 C（墓碑 `is_deleted` 與 `multi_root` 相對路徑一致性）**：
     - 嚴格複用 `manager._compute_rel_path(abs_path, inc_root, multi_root=len(inc_roots) > 1, proj_root=...)` 計算 `rel_path`。
     - 當檔案被刪除或不再滿足 `is_file_included` 時，於 `state.entries[rel_path]` **原地更新為 `FileFingerprint(..., created_gen=prev_fp.created_gen, updated_gen=next_gen_candidate, is_deleted=True, pending_stabilization=False)`**（對齊 `_mark_deleted_entries` 契約，使 `scanner.py:L1021` 之瞬態新增刪除抵銷邏輯 `fp.created_gen <= acked_gen < fp.updated_gen` 完全成立）。
     - 若單次防抖視窗內累積之 `dirty_paths` 超過閾值（如 `> 200` 檔）或空間位於 `_full_rescan_spaces`，自動退回加速版 `scan_space(space_name)`。

#### 方案三：`FS-03` — 消除 Watcher 假陽性與 500ms 防抖空窗之安全快照讀取契約
1. **盲審修正（解決 `is_watcher_active` 假陽性與 500ms 防抖競態視窗，`scanner.py:L43-78, L1182-1194`）**：
   - **問題根因**：現況 `is_watcher_active(project_root)` 只要 `.cache/server/daemon.json` 存活即回傳 `True`，導致（a）`cfg.watch == False` 的空間、（b）未安裝 `watchdog`（`HAS_WATCHDOG == False`）的環境、（c）Agent 剛改完檔案後 500ms 防抖視窗內立即執行 CLI 查詢（如 `kdb search`、`ast`、`gdrive sync`）時，`consume_diff` 因 `auto_refresh=False` 讀到過期 `YFP2` 快照。
   - **根治設計**：
     1. `is_watcher_active(project_root, space_name=None)` 必須同時驗證：Daemon 存活、Watcher 狀態檔（或記憶體）標記 `watchdog_running == True`、且目標 `space_name` 之 `cfg.watch == True`。
     2. **同進程 Worker 零延遲同步 Flush**：當 `ast`、`knowledge-db`、`gdrive-support` 於常駐 Server Worker 進程內執行時，讀取快照前若 `FileSpaceWatcherServiceWorker` 存在待處理之 `_dirty_paths_by_space[space_name]`，直接同步呼叫 `watcher_worker.flush_space_now(space_name)`（因 `FS-02` 已改為單檔增量 patch，僅耗時 `< 5ms`），實現 **0 防抖時間差之強一致讀取**！
     3. **跨進程 / 強制新鮮度兜底**：憑藉 `FS-01` 的預編譯過濾與 `DirEntry.stat()` 傳遞，即便執行一次完整的增量 `scan_space("cloud")`（Stage 1 全命中無變更檔案），在 2,200 檔規模下耗時亦從 `35s` 降至 **`< 0.15s`**。

#### 方案四：`FS-04` — `gdrive-support` 本地快照零冗餘 `stat` 管線與 `file-space` 對接
1. **盲審修正（區分 Blake2b 與 MD5/SHA-256，保留測試替身 Duck-Typing 相容，`config.py:L528-556`, `coordinator.py:L1599-1662`）**：
   - **雜湊語意邊界**：`file-space` 之 `FileFingerprint.content_hash` 為 20-byte Blake2b（`40 hex`）或大檔取樣雜湊，用於本地空間變更偵測；而 `gdrive-support` 的 `fingerprint_cache` 需要完整檔案之 `(md5, sha256)` 以對齊 Google Drive `md5Checksum`。因此**不將 `content_hash` 混充為 `sha256`**，而是複用 `(mtime_ns, size)` 作為 Stage 1 快取鍵！
   - **消除 5 重冗餘 Syscall**：
     1. 於 `collect_space_local_files()`（`config.py:L528-556`）：
        - 若 `fs_mgr` 實作了 `iter_space_files_with_stat(space_name)`（正式 `FileSpaceManager`），直接產出 `(rel_posix, abs_path, mtime_ns, size)`；若為單元測試傳入之 `_FakeFileSpaceManager` / `_SimpleFileSpaceManager`（僅有 `iter_space_files`），則透過 `hasattr` 優雅退回 `iter_space_files`。
        - **徹底移除逐檔 `Path(abs_path).resolve()`**（因 `inc_root` 初始化時已正規化，且 `follow_symlinks` 由 `FileSpaceManager` 管控）。
     2. 於 `SyncCoordinator._collect_local_snapshot()`（`coordinator.py:L1599-1662`）：
        - 直接接收 `(rel_path, abs_path, mtime_ns, size)`，**免除 `abs_path.is_file()` 與 `abs_path.stat()` 兩次系統呼叫**，直接以 `mtime_ns` 與 `size` 查驗 `self.state_store.get_cached_hashes(rel_path, mtime_ns, size)`。
        - 若在 Server Worker 內且 `cloud` 空間之 `YFP2` 已由 Watcher 即時同步（`FS-03`），甚至可直接由 `SnapshotState.active_entries` 讀取 `(rel_path, mtime_ns, size)`，實現 **0 次磁碟目錄遍歷（`< 20ms`）**。

#### 方案五：`FS-05` — `gdrive-support` 雲端 Level 1 拓撲序子目錄增量修補（含新建分支與 Shortcut 防護）
1. **盲審修正（對齊 `raw_entries` 結構、雲端新建分支退回 Level 2 與跨分支 Shortcut 清理，`coordinator.py:L1955-2040`）**：
   - **邊界 A（雲端根目錄新建分支偵測 — 守護 `test_et_06`）**：
     - 當 `changes.list` 出現未移除之新建資料夾，且其 `ch.parent_id == repo_folder_id`（即直接在 `<repo_sync_root>/` 下建立新分支資料夾，如 `cloud_feat`）時，**必須 `return None` 退回 Level 2**，以觸發 `_ensure_remote_repo_initialized() -> _reconcile_unregistered_cloud_branches()` 自動將新雲端分支註冊進 `.yscb_gdrive.json`。
   - **邊界 B（分支內部新建子目錄之拓撲序註冊）**：
     - 針對 `parent_id` 位於已知分支 `all_branch_dir_ids[b_name]` 內的新建資料夾：
       - 若資料夾名稱為系統保留名（`SYSTEM_NAMES` 或以 `.` / `_` 開頭），或同一分支 `b_data["dir_ids"].values()` / `b_data["raw_entries"]` 已存在同名 `rel_dir`（同名衝突），則安全 `return None` 退回 Level 2。
       - 否則按父子拓撲序（`while progress:`）計算 `rel_dir`，若未命中 `is_excluded(rel_dir)`，則將 `fid -> rel_dir` 註冊進 `b_data["dir_ids"]`、`all_branch_dir_ids[b_name]`、`known_folder_ids` 與 `folder_meta`，使同批次內的新增檔案（如新計畫下的 `P00_discuss.md`）直接完成 Level 1 增量掛載。
   - **邊界 C（分支內部資料夾移除與跨分支 Shortcut 連動清理）**：
     - 當已知分支子目錄 `fid` 被移除（`ch.removed or is_trashed`，且 `rel_dir != ""`）：
       - 從 `b_data["dir_ids"]`、`known_folder_ids`、`folder_meta` 移除 `rel_dir` 及其子目錄（`d_rel == rel_dir or d_rel.startswith(rel_dir + "/")`）。
       - 從 `b_data["raw_entries"]`（注意：正確鍵名為 `"raw_entries"` 而非 `"files"`）移除屬於該目錄前綴的所有項目，並收集這些被刪實體檔案之 `file_id`；若 `file_id` 存在於 `target_id_to_shortcuts`，同步從其他分支的 `raw_entries` 中移除指向該實體檔之懸空 Shortcut。

#### 方案六：`FS-06`（盲審新發掘）— 修復 `scanner.py` Racy-Clean `ctime_ns > prev_fp.mtime_ns` 永久快取擊穿陷阱與墓碑重置缺陷
1. **根因與代碼座標 (`scanner.py:L667-686, L701-715`)**：
   - **盲點 1（Racy-Clean 永久擊穿）**：`scanner.py:L674` 將 `prev_fp is not None and ctime_ns > prev_fp.mtime_ns` 列為 `is_racy = True` 的條件。然而在 Linux/POSIX 與容器掛載下，凡經 `gdrive sync` 下載後呼叫 `os.utime` 設定遠端 `mtime`、`shutil.copy2` 保留舊 `mtime`、或 `chmod` 修改權限的檔案，其 `st_ctime_ns` 永遠大於 `st_mtime_ns`！因為 `FileFingerprint` 未記錄 `ctime_ns`，這導致**所有這類檔案在之後的每一次 `scan_space()` 中永遠判定 `is_racy = True`**，100% 擊穿 Stage 1 `stat` 快取並被迫重讀全檔計算 Blake2b！
   - **盲點 2（刪除後重建覆寫 `created_gen`）**：`scanner.py:L701-715` 當 `prev_fp.is_deleted == True` 的檔案在同一路徑重新建立時，將 `created_gen` 覆寫為 `next_gen_candidate`。若某消費者之 `acked_gen` 處於舊檔案存續期間（`old_created_gen <= acked_gen`），在 `diff()`（`L1021`）中會將「刪除後重建修改」誤判為全新 `"added"` 而非 `"modified"`。
2. **修復設計**：
   - **Racy-Clean 修正**：Racy-Clean 的本質是「檔案之 `mtime_ns` 或 `ctime_ns` 與**前次掃描開始時間（或前次快照更新時間）**過於接近（落在同一檔案系統時間戳粒度視窗內）」，而非 `ctime_ns > mtime_ns`！應改為比對 `abs(scan_start_ns - mtime_ns) < RACY_CLEAN_WINDOW_NS`，消除 `ctime_ns > prev_fp.mtime_ns` 造成的永久快取擊穿。
   - **刪除後重建之世代保留**：當 `prev_fp is not None and prev_fp.is_deleted` 重新出現時，保留 `created_gen=prev_fp.created_gen`（僅更新 `updated_gen=next_gen_candidate, is_deleted=False`），確保跨世代游標消費者能正確識別其狀態轉移。

#### 方案七：`FS-07`（盲審新發掘）— `on_file_space_changed` 空間訂閱過濾與 `unified.yfp2.bin` 世代同步
1. **根因與代碼座標 (`service.py:L362-386`, `ast/scripts/hook.file-space.py:L118-170`, `scanner.py:L1050-1095`)**：
   - 當單一原始碼檔案修改時，因其同時屬於 `source` 與 `cloud` 空間，Watcher 會依序廣播兩次 `on_file_space_changed`（一次 `spaces=["cloud"]`，一次 `spaces=["source"]`）。
   - `ast` 的 `hook.file-space.py` 未過濾非 AST 目標空間（如 `"cloud"`），導致每次改檔 `ast` 都會對 `"cloud"` 執行一次冗餘的 `hot_patch_index` 並污染 `snap.space_generations`。
   - 同時，當消費者以 `space_name=None` 呼叫 `_diff_all_spaces()` 時，Watcher 從未更新 `unified.yfp2.bin`，導致 `to_generation` 停留在舊世代。
2. **修復設計**：
   - 於 `ast/scripts/hook.file-space.py` 與 `knowledge-db/scripts/hook.file-space.py` 中，若收到的事件 `target_space` 不在該引擎受管空間集合內（例如 `"cloud"` 僅供 `gdrive-support` 使用），直接 `return {"status": "ignored_space"}` 略過。
   - 於 `scanner._diff_all_spaces()` 中，動態聚合各受管空間 `.yfp2.bin` 之世代號（如 `sum(state.generation)` 與組合 Merkle Root），不再依賴未更新之靜態 `unified.yfp2.bin`。

#### 方案八：`FS-08`（盲審新發掘）— `CursorStore` 跨進程原子寫入鎖與專案空間 Override 模式
1. **根因與代碼座標 (`scanner.py:L367-436`, `manager.py:L396-460`)**：
   - `CursorStore.ack()` 在多消費者併發更新 `cursors.json` 時僅使用 `os.replace` 而無讀取-修改-寫入期間的 `InterProcessLock`，可能造成 `ast` 與 `knowledge-db` 同時 `ack` 時互相覆蓋游標。
   - `FileSpaceManager._merge_project_space_override` 對 `include/exclude/file_patterns` 僅支援聯集追加（`+`），專案層 `config/file-space/contribute.json` 無法顯式覆寫或替換模組預設列表。
2. **修復設計**：
   - `CursorStore` 的讀寫更新統一納入 `core.utils.file_lock.InterProcessLock` 保護。
   - `_merge_project_space_override` 支援當專案配置顯式聲明 `"override_mode": "replace"` 時直接替換對應欄位，預設維持 `"merge"` 向後相容。

---

### 2.4 改善前後端到端性能對比預估

| 場景 | 現況總耗時 | 導入 `FS-01` ~ `FS-05` 後預估耗時 | 加速倍率 |
| :--- | :---: | :---: | :---: |
| **`gdrive sync`（無變更 / Level 0 命中）** | `33.5 ~ 40.5s` | **`0.35 ~ 0.60s`** | **~70x 加速** |
| **`gdrive sync`（修改少數檔案 / Level 1 命中）** | `36.0 ~ 42.0s` | **`1.0 ~ 2.5s`** *(依實際上傳/下載檔案數)* | **~25x 加速** |
| **`gdrive sync`（新建計畫子目錄 + 3 個檔案）** | `175.0 ~ 180.0s` | **`1.5 ~ 3.0s`** | **~75x 加速** |
| **`file-space` Watcher 單檔變更更新 `YFP2`** | `32.0 ~ 36.0s` | **`< 0.01s` (`< 10ms`)** | **>3,000x 加速** |
| **`file-space` 冷啟動全量 `scan_space("cloud")`** | `33.0 ~ 38.0s` | **`4.0 ~ 7.0s`** *(消除重複 `stat`/`resolve` 與預編譯過濾)* | **~6x 加速** |

---

## 3. 結論 (Conclusion)

- **核心結論**：
  1. `module:file-space` 已具備完善的 `YFP2` 二進位快照格式與雙階段指紋模型，但經主視窗剖析與雙盲子代理審計（Devil's Advocate + 無假設探索），定位出 6 項底層引擎瓶頸與盲點：
     - **過濾與走訪開銷 (`FS-01`)**：`FileSpaceConfig` 未預編譯過濾規則，且 `_walk_root` 丟棄 `os.DirEntry.stat()` 導致下游重複 `stat()`。
     - **Watcher 全量重掃與目錄事件漏接 (`FS-02`)**：`FileSpaceWatcherServiceWorker` 丟棄單檔路徑觸發 `35s` 全掃，且忽略 `event.is_directory` 導致目錄改名/刪除產生幽靈項目。
     - **Watcher 假陽性與 500ms 防抖空窗 (`FS-03`)**：`is_watcher_active` 未檢查 `cfg.watch` 與 `watchdog` 實況，且缺乏同進程 Worker 零延遲同步 flush 機制。
     - **Racy-Clean `ctime_ns > prev_fp.mtime_ns` 永久快取擊穿與墓碑世代覆寫 (`FS-06`)**：凡經 `gdrive sync` (`os.utime`) 或 `shutil.copy2` 處理之檔案因 `ctime_ns > mtime_ns`，在每次掃描中永遠觸發 `is_racy=True` 重讀全檔算 Blake2b。
     - **跨空間事件重複廣播與 `unified.yfp2.bin` 失步 (`FS-07`)**：`cloud` 空間變動未過濾即廣播至 `ast` hook 造成雙重熱修補。
     - **`CursorStore` 缺乏跨進程鎖與專案 Override 僅能追加 (`FS-08`)**。
  2. `module:gdrive-support` 在本地端繞過 `file-space` `DirEntry.stat()` / `YFP2` 且逐檔重複執行 `Path.resolve()` + 雙重 `stat()`（`FS-04`），在雲端 Level 1 則對分支內新建子目錄無條件退回 Level 2 全掃（`FS-05`），兩者疊加造成了日常 `gdrive sync` 動輒 35s~180s 的嚴重延遲。
  3. 透過落地 **`FS-01` ~ `FS-08`** 八項內聚改造（並完整守護 `iter_space_files` 三元組簽名、Blake2b vs MD5/SHA256 雜湊邊界、雲端根目錄新分支 `test_et_06` 自動發現與跨分支 Shortcut 連動清理），可在 **100% 維持既有 Public API 與測試契約相容**的前提下，將 `file-space` 背景增量刷新壓至毫秒級，並將 `gdrive sync` 日常同步與新計畫立項同步全面拉入 **0.4s ~ 3s** 的秒級體驗。
- **後續建議（選填）**：
  - 建議直接採納**出口 ①（立即轉入開發實作）**，開立跨 `file-space`、`gdrive-support`（及 `ast` hook 空間過濾）之標準實作計畫（Standard Plan），將 `FS-01` ~ `FS-08` 轉化為具體模組變更與回歸測試並一步到位落地驗證。

