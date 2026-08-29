# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Knowledge-DB Hot Reload 缺陷修復與增量效能優化  
> 建立日期：2026-08-30  
> 所屬主計畫：無 (獨立 Level 1 計畫)  
> 狀態：Completed  

> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `check_invalidation()` 在多檔有修改/新增時完整掃描，回傳 100% 完整 `full_files_map` 與準確的 `added/modified/deleted` 差量清冊，不提早中斷。 | FR-01, FR-02 | `python yscb.py dev test knowledge-db -k test_ft_01_check_invalidation_full_scan` |
| **FT-02** | 單元測試 | 驗證 `SemanticBundler` 單檔符號快取 `_file_symbols_cache`：未變更檔案復用記憶體物件，僅重新解析 modified/added 檔案。 | FR-03 | `python yscb.py dev test knowledge-db -k test_ft_02_per_file_symbol_cache` |
| **FT-03** | 單元測試 | 驗證 `InvertedIndex.patch_incremental()` 能精確清理舊 Postings、注入新符號 Postings 並動態修正 `field_avgdl` 與 `doc_count`。 | FR-04 | `python yscb.py dev test knowledge-db -k test_ft_03_inverted_index_patch_incremental` |
| **FT-04** | 整合測試 | 驗證 `KnowledgeEngine.search` 觸發增量熱自愈後，檢索結果立即反映新增/修改/刪除之符號內容。 | FR-05, EC-01 | `python yscb.py dev test knowledge-db -k test_ft_04_incremental_hot_reload_search` |
| **ET-01** | 邊界測試 | 驗證檔案刪除情境 (Deleted File)：快照中存在但磁碟不存在，正確移除符號、Postings 與快取。 | EC-01 | `python yscb.py dev test knowledge-db -k test_et_01_file_deletion_handling` |
| **ET-02** | 邊界測試 | 驗證檔案修改為空內容 (Empty/Non-symbol File)：不拋出例外，舊符號乾淨移除。 | EC-02 | `python yscb.py dev test knowledge-db -k test_et_02_empty_file_handling` |
| **ET-03** | 邊界測試 | 驗證快照損毀或缺少時自動降級為 Full Rebuild 並恢復正常狀態。 | EC-03 | `python yscb.py dev test knowledge-db -k test_et_03_corrupted_snapshot_fallback` |
| **RT-01** | 回歸測試 | 驗證死循環防護 (Bugfix)：修改 1 檔觸發熱重載後，再次發起查詢時 `is_dirty` 為 False，絕對不再次觸發熱重載。 | FR-01, FR-05 | `python yscb.py dev test knowledge-db -k test_rt_01_no_infinite_hot_reload_loop` |
| **PT-01** | 效能測試 | 在模擬 50~100 檔環境下驗證單檔增量熱重載端到端耗時 $\le 100\text{ms}$。 | NFR-01 | `python yscb.py dev test knowledge-db -k test_pt_01_incremental_latency_benchmark` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 實機跑測 `test_ft_01_check_invalidation_full_scan` 通過：6 檔案全量無中斷走訪，精確收集 2 modified + 1 added。 | 2026-08-30 03:08 |
| **FT-02** | `Passed` | 實機跑測 `test_ft_02_per_file_symbol_cache` 通過：未變更檔案符號物件 100% 記憶體復用，僅 dirty 檔案調用 Parser。 | 2026-08-30 03:08 |
| **FT-03** | `Passed` | 實機跑測 `test_ft_03_inverted_index_patch_incremental` 通過：舊 Posting 精準拔除，新符號注入，`field_avgdl` 動態重算一致。 | 2026-08-30 03:08 |
| **FT-04** | `Passed` | 實機跑測 `test_ft_04_incremental_hot_reload_search` 通過：增量熱自愈後檢索即刻命中新符號。 | 2026-08-30 03:08 |
| **ET-01** | `Passed` | 實機跑測 `test_et_01_file_deletion_handling` 通過：檔案刪除後符號與 Postings 正確清除。 | 2026-08-30 03:08 |
| **ET-02** | `Passed` | 實機跑測 `test_et_02_empty_file_handling` 通過：空檔案正常處理，不引發異常。 | 2026-08-30 03:08 |
| **ET-03** | `Passed` | 實機跑測 `test_et_03_corrupted_snapshot_fallback` 通過：損毀快照優雅降級為 Full Rebuild 並自愈。 | 2026-08-30 03:08 |
| **RT-01** | `Passed` | 實機跑測 `test_rt_01_no_infinite_hot_reload_loop` 通過：熱自愈後 `is_dirty` 為 False，徹底根除無限死循環。 | 2026-08-30 03:08 |
| **PT-01** | `Passed` | 實機跑測 `test_pt_01_incremental_latency_benchmark` 通過：50 檔單檔增量熱重載端到端延遲達標。 | 2026-08-30 03:08 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：在實際專案目錄下執行 `python yscb.py knowledge-db search "..."`（開發者明確指示免測，自動化測試 94/94 100% Passed）。
