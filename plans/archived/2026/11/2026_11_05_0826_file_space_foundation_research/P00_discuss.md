# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_11_05_0826_file_space_foundation_research  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Medium)  

> 計畫類型：Standard  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「我們確立一下事實，可以說，除了 core 之外，file-space 是另一個重要地基對吧？」
  - 「我想先把 file-space 的底層完全打通解放潛力，先建立調研計畫吧，等等準備開始調研」
  - 「先處理剛剛的 gdrive 問題分析」$\to$「方向 A」（將 `gdrive-support` 本地端快照耗時 35~40s 與雲端 Level 1 新建子目錄退回 Level 2 全掃 138s 之根因與整合架構，一併納入 `file-space` 底層架構打通調研）。
- **核心目標**：
  - 針對生態系第二大底層基座 `module:file-space`（`ys_codebase/source/file-space/`）及其關鍵消費者 `module:gdrive-support`（`ys_codebase/source/gdrive-support/`）進行全方位架構診斷與潛力打通調研，梳理：
    1. `FileSpaceConfig` 路徑過濾編譯化與 `FileSpaceManager._walk_root` 零冗餘 `stat()` / `resolve()` 走訪契約（`FS-01`）。
    2. `FileSpaceWatcherServiceWorker` 路徑級增量 Dirty Queue（$O(|\text{dirty}|)$ 局部 Patch 取代 35s 全量 `scan_space`）與前置快速過濾（`FS-02`）。
    3. `FingerprintScanner` 零 I/O 快照直讀契約（`get_live_state` / `read_or_scan_space`，當 Watcher 活躍且 `config_hash` 一致時免重掃磁碟直接讀取 `YFP2`）（`FS-03`）。
    4. `gdrive-support` 本地快照收集（`_collect_local_snapshot`）對接 `file-space` 之 `cloud.yfp2.bin` 單調世代快照與零冗餘 `stat` 契約，將本地掃描從 35~40s 降至 `< 0.05s`（`FS-04`）。
    5. `gdrive-support` 雲端 Level 1 `changes.list` 支援拓撲序新建/移除子目錄增量修補，消除新增計畫目錄時退回 138s Level 2 全量遞迴掃描（`FS-05`）。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 現有 `ys_codebase/source/file-space/file_space/` 包含：
    - `schema.py`（`FileSpaceConfig`、`FileFingerprint`、`HashPolicy`、`ScanDiffResult` 等資料模型）
    - `manager.py`（`FileSpaceManager` 空間宣告聚合、路徑映射與 `iter_space_files`）
    - `scanner.py`（`FingerprintScanner`、`BinarySnapshotManager` `YFP2` 二進位快照、`CursorStore` 游標與 `compute_merkle_root`）
    - `service.py`（`FileSpaceWatcherServiceWorker` 背景 `watchdog` 監聽、防抖與 `on_file_space_changed` 事件派發）
  - 現有 `ys_codebase/source/gdrive-support/gdrive_support/` 包含：
    - `config.py`（`collect_space_local_files` 空間列舉橋接）
    - `coordinator.py`（`SyncCoordinator._collect_local_snapshot` 與 `_try_incremental_remote_cache` 雲端 Level 0/1/2 快取階層）
- **邊界排除 (Explicitly Excluded)**：
  - 不變更 `YFP2` 二進位檔案格式標頭結構與既有 `iter_space_files` 三元組公開簽名，確保既有快照與測試替身 100% 向後相容。
- **架構影響範圍**：
  - 核心聚焦於 `ys_codebase/source/file-space/`、`ys_codebase/source/gdrive-support/` 與 `ys_codebase/source/ast/scripts/hook.file-space.py`（空間事件過濾），並維持對 `ast`、`knowledge-db`、`server` 之向後相容契約。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 確立 `module:file-space` 作為僅次於 `core` 之動態空間與變更感知地基定位**：
  - `core` 負責靜態微內核（URI 路由、VFS、Contributes、模組載入）；`file-space` 則負責動態檔案空間拓撲、單調世代指紋（`YFP2` + Merkle Root）、多消費者游標（Watermark Cursors）與檔案變動事件流，為所有上層增量引擎（`ast`、`knowledge-db`、`gdrive-support`）的共同地基。
- **[P00:DR-02] 採納「方向 A」：將 `gdrive-support` 本地 `YFP2` 快照直讀與雲端 Level 1 子目錄增量修補併入 `file-space` 底層打通調研**：
  - 經實測診斷，`gdrive sync` 在遠端 Level 0 快取命中（0.3s）時仍耗時 33~40s，根因在於 `gdrive-support` 繞過 `file-space` 的 `cloud.yfp2.bin` 快照，每次重跑 `iter_space_files("cloud")` 並在容器 bind mount (`virtiofs`) 上對 2,200+ 檔案執行 5~6 次重複 `stat()` / `Path.resolve()`；而當新增計畫子目錄時，雲端 Level 1 因拒絕未知 `folder_id` 而退回 138s Level 2 全掃。
  - 開發者裁定採納「方向 A」，於 `R01_file_space_foundation_research.md` 統一完成 `file-space` 底層三大引擎升級（`FS-01` ~ `FS-03`）與 `gdrive-support` 雙端增量打通（`FS-04` ~ `FS-05`）之完整架構設計。
- **[P00:DR-03] 納入 `/blind-subagent` 雙軌盲審補強（`FS-01` ~ `FS-08`）並原地升級為 Standard 開發計畫**：
  - 經 Devil's Advocate 與無假設盲審核驗，補強 `FS-01` ~ `FS-05` 共 12 項邊界不變量（目錄前綴排除、`iter_space_files` 三元組簽名、Watcher 目錄事件守門、Blake2b vs MD5/SHA256 區分、雲端根目錄新分支 `test_et_06` 退回 Level 2 與跨分支 Shortcut 清理），並將新發掘之 `FS-06`（Racy-Clean `ctime_ns > prev_fp.mtime_ns` 永久快取擊穿修復與刪除重建世代保留）、`FS-07`（`ast` hook 空間訂閱過濾與 `_diff_all_spaces` 動態世代聚合）、`FS-08`（`CursorStore` 跨進程鎖與專案 Override 模式）一併納入本計畫原地推進 Phase 01~07 實作。

---

## 3. 開放議題與確認紀錄

- [x] **議題 1（調研切入維度與核心痛點盤點）**：已確認採納「方向 A」，將 `file-space` 底層遍歷/監聽/快照直讀引擎與 `gdrive-support` 本地快照對接及雲端 Level 1 新建子目錄增量修補統一納入 `R01` 調研報告。
- [x] **議題 2（調研出口裁決）**：開發者於完成 `/blind-subagent` 雙軌審查後指示「立即轉入開發實作」（出口 ①），原地追加 `P01` ~ `P07` 升級為標準開發計畫。

