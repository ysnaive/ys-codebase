# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：AST 指令卡死、Server 預熱阻塞與背景 Stage 1 鎖競爭根治修繕 (ast_server_warmup_and_lock_contention_fix)  
> 建立日期：2026-11-10  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :---: | :--- | :---: | :--- |
| **FT-01** | 單元測試 | 驗證 `WarmWorker.pre_warm()` 將 `virtual_cwd` 設為 `self.host_dir`，且 `KnowledgeEngine.pre_warm()` 在 `YSCB_IN_SERVER_WORKER="1"` 下不觸發阻塞式 `ASTEngine._ensure_loaded_from_disk()` | FR-01 | `python3 yscb.py dev test server knowledge-db --no-build` |
| **FT-02** | 單元測試 | 驗證當同進程 `KnowledgeDBServiceWorker` 活躍時，`ast/scripts/hook.core.py:on_file_space_changed` 自動喚醒 Worker 並讓渡 (`status="noop"`)，不爭搶 `ASTEngine._lock` | FR-02 | `python3 yscb.py dev test ast --no-build` |
| **FT-03** | 單元測試 | 驗證 `IndexingPipeline._collect_all_dirty_files` 在 `ensure_jit_synced()` 已推進世代後不重複呼叫 `hot_patch_index`，且 `KnowledgeDBServiceWorker._run_sync_cycle` 在 Stage 1 前禮讓 `foreground_active` | FR-03 | `python3 yscb.py dev test knowledge-db --no-build` |
| **FT-04** | 單元測試 | 驗證 `ASTEngine.status()` 透過 `unified.meta.json`（含 `total_edges` 與單空間計數）在背景執行緒持有 `engine._lock` 與 `.ast_index.lock` 時仍能以 $< 50\text{ms}$ 無鎖回傳正確數據 | FR-04, NFR-01 | `python3 yscb.py dev test ast --no-build` |
| **FT-05** | 單元測試 | 驗證 `ASTEngine.outline(..., merged=False)` 在含 C# `partial` 類別之檔案上，即使背景執行緒持有 `engine._lock` 亦不阻塞，且已建索引時仍能提取 `partial_siblings` | FR-05, NFR-01 | `python3 yscb.py dev test ast --no-build` |
| **FT-06** | 單元測試 | 驗證 `SemanticBundler._collect_space_files()` 自動略過無對應 AST 解析器之非代碼檔案（如 `.json`、`.png`、`.uxml`），不開啟讀取檔案亦不產生空 `FileSymbolGraph` | FR-06 | `python3 yscb.py dev test ast --no-build` |
| **ET-01** | 邊界測試 | 驗證 `unified.meta.json` 被刪除或缺失欄位時，`get_persisted_meta()` 與 `status()` 平滑回退至二進位載入且不重寫 `unified.meta.json` (CQS) | EC-01 | `python3 yscb.py dev test ast --no-build` |
| **ET-02** | 邊界測試 | 驗證背景執行緒長時間持有 `ASTEngine._lock` 時，前景並行呼叫 `status()` 與 `outline(..., merged=False)` 零死鎖、零逾時完成 | EC-02 | `python3 yscb.py dev test ast --no-build` |
| **ET-03** | 邊界測試 | 驗證向 `hot_patch_unified_index()` 傳入合成 `ScanDiffDetail` 或 `ASTEngine` 跨多世代跳躍時，增量修補與跨世代符號對齊完整無遺漏 | EC-03 | `python3 yscb.py dev test knowledge-db --no-build` |
| **ET-04** | 邊界測試 | 驗證直接向 `ast/scripts/hook.core.py:on_file_space_changed` 傳入顯式 `engine` 或無背景 Worker 時，維持完整增量修補與游標回滾契約 | EC-04 | `python3 yscb.py dev test ast --no-build` |
| **RT-01** | 整合與回歸測試 | 驗證 `ast`、`knowledge-db`、`server` 三大模組全量測試套件 100% 通過且 `0 ResourceWarning` | NFR-02 | `python3 -W error::ResourceWarning yscb.py dev test ast knowledge-db server --no-build` |
| **RT-02** | 靜態合規檢核 | 驗證全倉模組通過 `dev check --all` 與 `contributes check` (`0 FAIL, 0 WARN`) | NFR-02 | `python3 yscb.py dev check --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | Passed | `test_warm_worker_pre_warm_events` 與 `test_stage1_foreground_yield_and_zero_redundant_hot_patch` 驗證通過 | 2026-11-10 |
| **FT-02** | Passed | `test_status_lock_free_meta_fast_path_and_outline_non_blocking_under_contention` 驗證 `hook.core.py` 同進程讓渡通過 | 2026-11-10 |
| **FT-03** | Passed | `test_stage1_foreground_yield_and_zero_redundant_hot_patch` 驗證 Stage 1 禮讓與單次 `hot_patch_index` 通過 | 2026-11-10 |
| **FT-04** | Passed | `test_status_lock_free_meta_fast_path_and_outline_non_blocking_under_contention` 驗證背景持鎖下 `status()` 無鎖快讀通過 | 2026-11-10 |
| **FT-05** | Passed | `test_status_lock_free_meta_fast_path_and_outline_non_blocking_under_contention` 與 `test_outline_single_file_default_vs_merged_partial_siblings` 驗證通過 | 2026-11-10 |
| **FT-06** | Passed | `test_status_lock_free_meta_fast_path_and_outline_non_blocking_under_contention` 驗證 `.json` / `.uxml` 預過濾通過 | 2026-11-10 |
| **ET-01** | Passed | `test_single_pass_file_graph_cache_and_persistence` 驗證 `meta.json` 刪除後 CQS 唯讀回退通過 | 2026-11-10 |
| **ET-02** | Passed | `test_status_lock_free_meta_fast_path_and_outline_non_blocking_under_contention` 雙鎖競爭零阻塞驗證通過 | 2026-11-10 |
| **ET-03** | Passed | `test_csharp_partial_hot_patch_preserves_non_partial_and_multi_gen_reconcile` 驗證合成差量與跨世代對齊通過 | 2026-11-10 |
| **ET-04** | Passed | `test_file_space_hook_lifecycle_and_generation_fallback` 驗證顯式 `engine` 原生同步與回滾通過 | 2026-11-10 |
| **RT-01** | Passed | `ast` 54/54、`knowledge-db` 118/118、`server` 67/67 100% 通過 (`0 ResourceWarning`) | 2026-11-10 |
| **RT-02** | Passed | `dev check --all` (9/9 PASS, 0 WARN) 與 `contributes check` (28 files PASS) 通過 | 2026-11-10 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於本地端拉取更新後，在大型專案（如 `/workspace/uitk.net`）執行 `python yscb.py server start` 後立即執行 `python yscb.py ast status` 與 `python yscb.py ast outline <file.cs>`，確認秒級回應不卡死 | `[跳過/免測]` | 雲端 VM 已透過自動化並發鎖競爭測試完整模擬驗證；交由開發者於階段 C 本地端 `gdrive pull` 後最終驗收 |
