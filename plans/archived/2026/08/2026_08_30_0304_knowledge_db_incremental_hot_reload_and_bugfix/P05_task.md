# 實作任務清單 (Task Breakdown)

> 功能名稱：Knowledge-DB Hot Reload 缺陷修復與增量效能優化  
> 建立日期：2026-08-30  
> 所屬主計畫：無 (獨立 Level 1 計畫)  
> 狀態：Completed  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `scanner.py` 定義 `ScanDiffDetail`，重構 `check_invalidation()` 採用 `os.scandir` 完整掃描全庫，杜絕提早中斷，輸出 100% 完整 `full_files_map` 與差量明細。
- [x] **TASK-02**：在 `bundler.py` 為 `SemanticBundler` 引入 `_file_symbols_cache`，實作 `bundle_dirty_files()` 差量解析與快取更新。
- [x] **TASK-03**：在 `retrieval.py` 實作 `InvertedIndex.patch_incremental()`，並優化 `save_binary()` 支援 `compresslevel=1` 快速壓縮。
- [x] **TASK-04**：在 `engine.py` 整合增量熱自愈管線 `_hot_patch_unified_index()`，確保 `search()` 與 `build_unified_index()` 剛性持久化完整快照。
- [x] **TASK-05**：編寫單元、整合、邊界與效能基準測試 `tests/test_incremental_hot_reload.py`，全量執行驗證。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
