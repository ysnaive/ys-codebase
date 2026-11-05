# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：2026_11_05_0321_kdb_cli_and_engine_optimization  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 狀態：Passed  
> 模型：Gemini  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `ResultFormatter` (`knowledge-db`) 與 `ASTResultFormatter` (`ast`) 預設 `file_uri=False` 時輸出純相對路徑與行號（如 `source/core/core/uri.py:L10-25`），傳入 `--file-uri` 或 `--md` 時輸出完整 `[...](file:///...)` 超連結。 | FR-01, NFR-01 | `python yscb.py dev op-test ast -q --all-types` / `python yscb.py dev op-test knowledge-db -q --all-types` |
| **FT-02** | 單元測試 | 驗證 `kdb search` 未帶顯示旗標時預設為 `detail_mode="auto"`（單命中折疊單行、多命中子項不重複印出檔名），顯式傳入 `--simple` 時維持 `"清單模式"` 標頭。 | FR-02, NFR-01 | `python yscb.py dev op-test knowledge-db -q --all-types` (`TestCLI.test_cli_search_modes`) |
| **FT-03** | 單元測試 | 驗證 `kdb search --json` 與 `ast callers/callees/impact --json` 在 `simple`/`preview` 層級預設省略 `"file_uri"` 與空字串選填欄位，而在 `--detail` 或 `--file-uri` 時完整保留 `"file_uri"`。 | FR-03, EC-01, NFR-01 | `python yscb.py dev op-test knowledge-db -q --all-types` (`TestCLI.test_cli_search_modes`) |
| **FT-04** | 單元測試 | 驗證 `knowledge-db/contributes/core.json` 宣告 `"module_alias": ["kdb"]`，且 `agents_workflow/plans/_trace_parser.py` 正確識別 `python yscb.py kdb search` 並將模組統計歸一化至 `"knowledge-db"`。 | FR-04 | `python yscb.py dev op-test agents-workflow -q --all-types` (`TestPlansModelRecord.test_ft_16_pxx_05_auto_consolidated_search_capsule_and_portability`) |
| **FT-05** | 單元測試 | 驗證 `ASTEngine` 寫入 `unified.meta.json`，`get_persisted_meta()` 在無變更時免解壓 `unified.symbols.bin.gz`，且 `ensure_jit_synced()` 在無變更時僅載入 `_snapshot` 而不載入 `_graph` (`unified.graph.bin.gz`)。 | FR-05, EC-02, NFR-02 | `python yscb.py dev op-test ast -q --all-types` (`TestASTEnginePolish.test_t36_file_uri_opt_in_and_lazy_graph_meta`) |
| **FT-06** | 單元測試 | 驗證 `KnowledgeEngine.search(adaptive_limit=True)` 相對斷崖截斷、`InvertedIndex` `0..n` `doc_idx` + `SparseFieldFreqs` 稀疏欄位詞頻，以及 `KnowledgeEngine.status()` 直接自 `snap_state.entries` 計算存活檔案數免除二次 `iter_space_files` 磁碟遍歷。 | FR-06, FR-07, FR-08, EC-03, EC-04, NFR-02 | `python yscb.py dev op-test knowledge-db -q --all-types` (`TestEngine.test_opt05_06_08_meta_adaptive_limit_and_status_snapshot`, `TestHybridSearchEngine.test_posting_slots_and_memory_savings`) |
| **ET-01** | 邊界測試 | 驗證同時傳入 `--json` 與 `--file-uri` 不觸發互斥錯誤且強制輸出 `"file_uri"`。 | EC-01, FR-01, FR-03 | `python yscb.py dev op-test knowledge-db -q --all-types` (`TestCLI.test_cli_search_modes`) |
| **ET-02** | 邊界測試 | 驗證 `unified.meta.json` 缺失或指紋失效時，`get_persisted_meta()` 自動回退至 `_ensure_symbols_loaded()` 並自癒重寫 `unified.meta.json`。 | EC-02, FR-05 | `python yscb.py dev op-test ast -q --all-types` (`TestASTEnginePolish.test_t36_file_uri_opt_in_and_lazy_graph_meta`) |
| **ET-03** | 邊界測試 | 驗證 `InvertedIndex.patch_incremental` 刪除舊檔案符號時透過 `_free_doc_indices` 回收 `doc_idx`，不影響既有存活符號之 `doc_idx` 映射。 | EC-03, FR-07 | `python yscb.py dev op-test knowledge-db -q --all-types` (`TestHybridSearchEngine.test_posting_slots_and_memory_savings`) |
| **ET-04** | 邊界測試 | 驗證 `KnowledgeEngine.status()` 讀取 `snap_state.entries` 時排除 `is_deleted=True` 之 Tombstone 條目。 | EC-04, FR-08 | `python yscb.py dev op-test knowledge-db -q --all-types` (`TestEngine.test_opt05_06_08_meta_adaptive_limit_and_status_snapshot`) |
| **RT-01** | 迴歸測試 | 驗證 `ast`、`knowledge-db`、`agents-workflow` 三模組通過 `dev check` 靜態架構與零 `sys.path` 變動合規檢查。 | NFR-02 | `python yscb.py dev check ast` / `python yscb.py dev check knowledge-db` / `python yscb.py dev check agents-workflow` |
| **RT-02** | 迴歸測試 | 驗證 `ast` (27/27)、`knowledge-db` (109/109) 與 `agents-workflow` (142/142) 全量自動化測試 100% 通過。 | NFR-01, NFR-02 | `python yscb.py dev test {ast,knowledge-db,agents-workflow} -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestEngine.test_ft_07_to_file_uri_and_formatting` 與 `TestASTEnginePolish.test_t36_file_uri_opt_in_and_lazy_graph_meta` 驗證通過：`file_uri=False` 輸出純相對路徑，`file_uri=True` 輸出 RFC 8089 超連結。 | 2026-11-05 |
| **FT-02** | `Passed` | `TestCLI.test_cli_search_modes` 驗證通過：預設 `auto` 模式單項單行化、多項子節點無重複檔名，`--simple` 維持清單模式。 | 2026-11-05 |
| **FT-03** | `Passed` | `TestCLI.test_cli_search_modes` 驗證通過：`--json` 預設省略 `file_uri`，`--json --file-uri` 與 `--json --detail` 保留 `file_uri`。 | 2026-11-05 |
| **FT-04** | `Passed` | `TestPlansModelRecord.test_ft_16_pxx_05_auto_consolidated_search_capsule_and_portability` 驗證通過：`yscb.py kdb search` 重置盲讀計數並歸一化至 `knowledge-db`。 | 2026-11-05 |
| **FT-05** | `Passed` | `TestASTEnginePolish.test_t36_file_uri_opt_in_and_lazy_graph_meta` 驗證通過：`get_persisted_meta()` 讀取 `unified.meta.json` 時 `_snapshot` 與 `_graph` 均維持 `None`；`ensure_jit_synced()` 不載入 `_graph`。 | 2026-11-05 |
| **FT-06** | `Passed` | `TestEngine.test_opt05_06_08_meta_adaptive_limit_and_status_snapshot` 與 `TestHybridSearchEngine.test_posting_slots_and_memory_savings` 驗證通過。 | 2026-11-05 |
| **ET-01** | `Passed` | `--json --file-uri` 複合旗標解析與輸出驗證通過。 | 2026-11-05 |
| **ET-02** | `Passed` | `get_persisted_meta()` 於 `unified.meta.json` 重建與自癒回退驗證通過。 | 2026-11-05 |
| **ET-03** | `Passed` | `patch_incremental` 透過 `_free_doc_indices` 回收索引且不偏移存活 `doc_idx` 驗證通過。 | 2026-11-05 |
| **ET-04** | `Passed` | `status()` 透過 `snap_state.entries` 過濾 `not fp.is_deleted` 並免除 `iter_space_files` 調用驗證通過。 | 2026-11-05 |
| **RT-01** | `Passed` | `dev check ast`、`dev check knowledge-db`、`dev check agents-workflow` 全數 `[PASS]`。 | 2026-11-05 |
| **RT-02** | `Passed` | `ast` 27/27 (100.0%)、`knowledge-db` 109/109 (100.0%)、`agents-workflow` 142/142 (100.0%) 全數通過。 | 2026-11-05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於本地拉取雲端變更後，執行 `python yscb.py kdb search InvertedIndex`、`python yscb.py kdb search InvertedIndex --file-uri` 與 `python yscb.py kdb status`，確認 CLI 短別名、預設無 `file:///` 相對路徑輸出與單檔/多檔折疊排版符合預期。 | `[測試通過]` | 開發者實機驗收確認通過（2026-11-05） |
