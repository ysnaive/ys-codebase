---
target: "File-Space"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb://source/file-space/file_space/scanner.py"
  - "yscb://source/file-space/file_space/service.py"
  - "yscb://source/file-space/file_space/manager.py"
related_docs:
  - "./README.md"
  - "./ARCHITECTURE.md"
  - "../knowledge-db/DESIGN_NOTES.md"
last_updated: "2026-11-05"
---

# file-space 設計決策與工程妥協手冊 (Design Notes)

> 模組名稱：`file-space`  
> 職責定位：記錄 `file-space` 模組中屬於「維度 ⑤ 工程妥協與防坑」之非直覺設計、Racy-Clean 時間窗防護、二進位格式自癒與多消費者游標隔離不變量。

---

## 登錄決策清單 (Decision Registry)

| 決策編號 | 標題 / 主題 | 影響檔案 | 風險等級 |
| :---: | :--- | :--- | :---: |
| **DN-SP-01** | 10ms Racy-Clean 時間窗穿透防護、排除 `ctime > prev.mtime` 永久擊穿與 `adaptive` 192KB 稀疏抽樣 | `scanner.py` | 🚨 CRITICAL |
| **DN-SP-02** | `YFP2` 單調世代墓碑保留、復活項目 `created_gen` 延續與 `CursorStore` 跨程序鎖防護 | `scanner.py` | 🚨 CRITICAL |
| **DN-SP-03** | `FileSpaceWatcherServiceWorker` 混合式路徑修補、目錄搬移/刪除全量重掃與 `watcher_state.json` 活性感知 | `service.py`, `scanner.py` | ⚠️ WARNING |

---

## 詳細設計決策與防坑邊界

### [DN-SP-01] 10ms Racy-Clean 時間窗穿透防護、排除 `ctime > prev.mtime` 永久擊穿與 `adaptive` 192KB 稀疏抽樣

- **背景與根因**：
  1. 在自動化測試或高速程式碼生成器連續寫入同一檔案且檔案大小 (`size`) 未改變時，若檔案寫入時間與當次掃描時間落在 `< 10ms` 視窗內，單純依賴 `(mtime_ns, size)` 比對可能誤判為未修改（Racy-Clean 漏檢）。
  2. 當檔案經過 `shutil.copy2`、`os.utime`、跨分支 `checkout` 或雲端同步回填歷史 `mtime` 時，作業系統之 `st_ctime_ns`（inode 變更時間，恆為當下）必然大於回填後的 `st_mtime_ns`。若將 `ctime_ns > prev_fp.mtime_ns` 列為 `is_racy` 條件，該檔案在後續每一次掃描中都會永遠成立 `ctime_ns > prev_fp.mtime_ns`，導致快取永久擊穿、每次掃描皆重算雜湊。
  3. 若對空間內偶發出現之數十 MB 大型資產檔執行全量雜湊，會阻塞前台 CLI 與背景 Watcher 執行緒。
- **工程妥協與解法**：
  1. **10ms Racy-Clean 對齊 `scan_start_ns`**：於 `FingerprintScanner._evaluate_entry_fingerprint` Stage 1 比對時，僅檢查 `abs(scan_start_ns - mtime_ns) < 10_000_000` 或 `abs(scan_start_ns - max(mtime_ns, ctime_ns)) < 10_000_000`（10 毫秒）；一旦距離當次掃描起點超過 10ms 且 `(mtime_ns, size)` 與前次快照一致，即穩定命中快取，不再因 `ctime_ns > prev_fp.mtime_ns` 永久重算。
  2. **`adaptive` 頭中尾 64KB 稀疏抽樣**：對 `>= large_file_threshold_mb`（預設 10MB）之大檔，讀取頭 `64KB`、正中 `64KB`、尾 `64KB` 共 `192KB` 連同 `size` 計算 `blake2b(digest_size=20)` 並冠上 `"sample2b:"` 前綴。

> [!CAUTION]
> **嚴禁移除 Stage 1 中的 `RACY_CLEAN_WINDOW_NS` (`10_000_000`) 判斷條件，亦嚴禁加回 `ctime_ns > prev_fp.mtime_ns` 條件！** 前者會導致同毫秒等長覆寫漏檢，後者會導致任何經 `os.utime` / `copy2` 保留歷史時間戳之檔案永久失去指紋快取。

---

### [DN-SP-02] `YFP2` 單調世代墓碑保留、復活項目 `created_gen` 延續與 `CursorStore` 跨程序鎖防護

- **背景與根因**：
  1. 當多個下游消費者（如 `ast`、`knowledge-db` 與 `gdrive-support`）共用同一份空間指紋快照時，若直接物理移除已刪除檔案紀錄，較晚執行的消費者將丟失 `deleted` 事件。
  2. 若檔案曾被刪除（留存 `is_deleted=True` 墓碑）後再次於原路徑建立，若將 `created_gen` 覆寫為新世代，處於舊游標 (`acked_gen >= 原始 created_gen`) 的消費者在比對時需依賴穩定的歷史創建世代。
  3. 多進程同時執行 `consume_diff` / `ack` 時，僅靠單進程 `threading.RLock` 無法防止跨進程 Read-Modify-Write 覆蓋同一 `cursors/<consumer_id>.json`。
- **工程妥協與解法**：
  1. **單調遞增世代 (`head_generation`) 與軟刪除墓碑 (`is_deleted`)**：檔案刪除時原地標記 `is_deleted=True` 並更新 `updated_gen = new_gen`；若該路徑後續重新出現，延續既有墓碑之 `created_gen = prev_fp.created_gen` 並更新 `updated_gen = new_gen, is_deleted = False`。
  2. **配置雜湊 (`config_hash`) 變更自動失效**：當空間配置變更導致 `config_hash` 不一致或 `acked_gen > head_generation` 時，游標自動視為無效並回退全量差異 (`baseline_missing=True`)。
  3. **`CursorStore` 跨程序鎖 (`InterProcessLock`)**：於 `set_cursor` 與 `reset_cursor` 內部結合 `self._lock` 與 `InterProcessLock(cursors_dir / f".{consumer_id}.cursor.lock")`，確保跨進程讀改寫原子性。

> [!CAUTION]
> **嚴禁在 `FingerprintScanner.scan_space()` 或 `patch_space_files()` 發現檔案消失時直接從 `YFP2` 字典中 `del` 移除該筆記錄（除非執行 `clean` 全清）！** 直接刪除將導致尚未消費該世代的下游模組丟失 `deleted` 事件而殘留幽靈索引。

---

### [DN-SP-03] `FileSpaceWatcherServiceWorker` 混合式路徑修補、目錄搬移/刪除全量重掃與 `watcher_state.json` 活性感知

- **背景與根因**：
  1. 當背景 Watcher 收到單一檔案修改事件時，若對整個空間執行全量 `os.scandir` 重掃，在大規模倉儲中會造成不必要的 I/O 放大；但若對目錄搬移或刪除事件也僅修補目錄本身路徑，將遺漏目錄下所有子檔案的墓碑標記。
  2. 當宿主正在執行 `yscb.py install / update / remove` 批次原子交易時，目錄正處於密集搬移狀態，不應立即廣播半成品快照。
  3. 若僅憑 Server `daemon.json` PID 存在即判定 Watcher 活躍，當 `watchdog` 因未安裝或空間設為 `watch=False` 時，`consume_diff` 跳過 `auto_refresh` 會讀到陳舊快照。
- **工程妥協與解法**：
  1. **混合式局部修補 (`patch_space_files`) 與目錄事件升級 (`_full_rescan_spaces`)**：一般檔案事件累積 `<= 200` 筆時呼叫 `scanner.patch_space_files` 進行 $O(|\text{dirty}|)$ 局部更新；一旦收到 `is_directory=True` 且 `event_type in ("moved", "deleted")`，立即將該空間排入 `_full_rescan_spaces` 強制執行全量 `scan_space`。
  2. **`.yscb.lock` 交易鎖延遲讓路**：防抖計時器觸發時若偵測到 `cache://.yscb.lock` 或專案 `.yscb.lock` 被持有，自動重設防抖計時器延後執行。
  3. **`watcher_state.json` 與空間級 `watch` 校驗**：`FileSpaceWatcherServiceWorker` 透過 `file-space.cache://watcher_state.json`（降級錨定 `core.uri.resolve_yscb_root()`）維護 `watchdog_running` 與 `watched_spaces`；`is_watcher_active(project_root, space_name)` 同時驗證該空間 `cfg.watch` 與 `watchdog_running` 真實狀態，並委託 `core.vfs.write_bytes(..., atomic=True)` 完成二進位快照與信標之原子寫入。

> [!WARNING]
> **修改 `FileSpaceWatcherServiceWorker.start/stop` 時，務必保證 `finally` 區塊更新/清理 `watcher_state.json`、`.watcher_active` 與 `.watcher_dirty` 信標！**

