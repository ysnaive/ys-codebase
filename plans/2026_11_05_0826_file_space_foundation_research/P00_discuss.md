# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_11_05_0826_file_space_foundation_research  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 狀態：Discussing  
> 模型：Gemini 4 Argon (Medium)  

> 計畫類型：Research  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「我們確立一下事實，可以說，除了 core 之外，file-space 是另一個重要地基對吧？」
  - 「我想先把 file-space 的底層完全打通解放潛力，先建立調研計畫吧，等等準備開始調研」
- **核心目標**：
  - 針對生態系第二大底層基座 `module:file-space`（`ys_codebase/source/file-space/`）進行全方位架構檢視與潛力打通調研，梳理其在跨模組空間幾何路由、雙階段指紋快照（`YFP2`）、多消費者增量游標（`CursorStore`）、背景事件監聽（`FileSpaceWatcherServiceWorker`）以及向上支撐 `ast`、`knowledge-db`、`gdrive-support`、`server` 等消費者時的底層瓶頸與演進方向。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 現有 `ys_codebase/source/file-space/file_space/` 包含：
    - `schema.py`（`FileSpaceConfig`、`FileFingerprint`、`HashPolicy`、`ScanDiffResult` 等資料模型）
    - `manager.py`（`FileSpaceManager` 空間宣告聚合、路徑映射與 `iter_space_files`）
    - `scanner.py`（`FingerprintScanner`、`BinarySnapshotManager` `YFP2` 二進位快照、`CursorStore` 游標與 `compute_merkle_root`）
    - `service.py`（`FileSpaceWatcherServiceWorker` 背景 `watchdog` 監聽、防抖與 `on_file_space_changed` 事件派發）
    - `exceptions.py` 與 `scripts/cli.py`
- **邊界排除 (Explicitly Excluded)**：
  - 本階段為前置深度調研（`Research Plan`），在未與開發者逐一確認調研重點與架構決策前，不直接修改業務程式碼。
- **架構影響範圍**：
  - 核心聚焦於 `ys_codebase/source/file-space/`，並涵蓋其與 `core`（URI / VFS / Contributes / FileLock）及上游消費者（`ast`、`knowledge-db`、`gdrive-support`、`server`）之介面契約。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 確立 `module:file-space` 作為僅次於 `core` 之動態空間與變更感知地基定位**：
  - `core` 負責靜態微內核（URI 路由、VFS、Contributes、模組載入）；`file-space` 則負責動態檔案空間拓撲、單調世代指紋（`YFP2` + Merkle Root）、多消費者游標（Watermark Cursors）與檔案變動事件流，為所有上層增量引擎（`ast`、`knowledge-db`、`gdrive-support`）的共同地基。

---

## 3. 開放議題與確認紀錄

- [ ] **議題 1（調研切入維度與核心痛點盤點）**：待開發者指示希望優先剖析與打通的 `file-space` 底層機制或具體方向。

