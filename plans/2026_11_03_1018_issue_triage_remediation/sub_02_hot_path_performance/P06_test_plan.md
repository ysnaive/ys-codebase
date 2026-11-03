# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：熱路徑效能與增量管線深度優化  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `contributes.get()` 記憶體快取命中（連續 10 次呼叫僅觸發 1 次 `_scan_contributes_inputs`）、`invalidate_cache()` 強制失效與 `scan_and_inject()` / 雙 mtime 變更自動刷新 | FR-01, EC-01, NFR-01, NFR-02 | `python yscb.py dev test core -q` |
| **FT-02** | 單元測試 | 驗證 `FileSpaceManager.project_root` 快取、`load_spaces(force=False)` 免重複載入守衛、`load_spaces(force=True)` 強制重載，以及 `follow_symlinks=True` 與 symlink 子目錄解析行為 | FR-02, EC-02, NFR-02 | `python yscb.py dev test file-space -q` |
| **FT-03** | 單元測試 | 驗證 `ASTEngine.hot_patch_index` 與 `ensure_jit_synced` 單檔增量熱修補期間 `iter_space_files` 呼叫次數為 `0`、非快照路徑回退解析（EC-03）、`file_to_symbol_ids` $O(|\text{dirty}|)$ 淘汰與 C# partial class 兄弟節點重聚合、以及 `bundle_union` 單次讀檔快取複用 | FR-02, FR-03, FR-05, FR-06, EC-03, NFR-01, NFR-02 | `python yscb.py dev test ast -q` |
| **FT-04** | 單元測試 | 驗證 `InvertedIndex.patch_incremental` 僅修剪 `removed_terms` Posting、Stage 2 `sync_vector_deficit_step` 於 `embed_texts()` 期間釋放 `_index_lock` 且重新加鎖後過濾已刪除符號（EC-04）、以及 `KnowledgeDBServiceWorker` 批次持久化節流與中斷時 `flush_vector_index()` 保底落盤（EC-05） | FR-02, FR-04, FR-05, EC-04, EC-05, NFR-02 | `python yscb.py dev test knowledge-db -q` |
| **FT-05** | 單元測試 | 驗證 `SandboxProvisioner` 對具備有效 `.build.zip` 之模組直接解壓（跳過前置 `shutil.copytree` 與 `shutil.rmtree`），且於 `.build.zip` 損壞時自動回退至 `shutil.copytree`（EC-06） | FR-07, EC-06, NFR-02 | `python yscb.py dev test dev -q` |
| **FT-06** | 靜態合規與盲審 | 驗證 `core`、`file-space`、`ast`、`knowledge-db`、`dev` 5 個模組 `dev check` 結構與契約合規，並通過 Pre-UX 盲眼子代理審查 | FR-01, FR-02, FR-03, FR-04, FR-05, FR-06, FR-07, NFR-02 | `python yscb.py dev check core file-space ast knowledge-db dev` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `core` 測試集 239 passed（含 `test_get_memory_cache_eliminates_redundant_disk_reads_and_scans`、`test_invalidate_cache_and_scan_inject_refresh`） | 2026-11-03 |
| **FT-02** | `Passed` | `file-space` 測試集 16 passed（含 `test_project_root_cached`、`test_load_spaces_cached_unless_forced`、`test_follow_symlinks_still_resolves`） | 2026-11-03 |
| **FT-03** | `Passed` | `ast` 測試集 21 passed（含 `test_hot_patch_index_zero_full_space_walks`、`test_bundle_union_single_read_caches_call_sites_and_imports`、`test_partial_class_reaggregation_with_fast_symbol_eviction`） | 2026-11-03 |
| **FT-04** | `Passed` | `knowledge-db` 測試集 106 passed（含 `test_inverted_index_patch_incremental_prunes_only_removed_terms`、`test_sync_vector_deficit_step_releases_lock_and_filters_deleted_symbols`、`test_worker_throttles_persistence_and_flushes_on_stop`） | 2026-11-03 |
| **FT-05** | `Passed` | `dev` 測試集 84 passed（含 `test_sandbox_skips_copytree_when_valid_build_zip_exists`、`test_sandbox_falls_back_to_copytree_when_build_zip_corrupt`） | 2026-11-03 |
| **FT-06** | `Passed` | 5 模組 `dev check` 全數 `PASS`；Pre-UX 盲眼子代理（`34a993d2`）審查回傳 `REVIEW_STATUS: PASSED`（0 阻塞項） | 2026-11-03 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 確認 `core.contributes` 快取、`FileSpaceManager` 路徑優化與 `dev` 沙盒 `.build.zip` 直接解壓之實作與測試結果 | `[測試通過]` | 於臨時兄弟目錄 `/workspace/ys-codebase-uat-sub02` 完成端到端實測（20 次連發 `contributes.get/locale.t` 0 次重掃、`.build.zip` 直接解壓與壞包回退均符合預期） |
| **UX-02** | 確認 `ast` 單檔增量 $O(|\text{dirty}|)$ 熱修補、全量建置單次讀檔快取，以及 `knowledge-db` Stage 2 鎖分離與批次持久化節流之實作與測試結果 | `[測試通過]` | 於臨時兄弟目錄完成端到端實測（單檔 `hot_patch_index` 0 次全倉走訪、`sync_vector_deficit_step` 鎖外推論與檢查點落盤均符合預期） |

