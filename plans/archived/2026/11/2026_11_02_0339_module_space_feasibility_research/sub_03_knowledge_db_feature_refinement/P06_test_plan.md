# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：`knowledge-db` 功能細節優化（常駐背景 Worker、向量模型自動下載、忙碌毫秒探針與容差降級、`status` 詳盡觀測）  
> 建立日期：2026-11-02  
> 所屬主計畫：`2026_11_02_0339_module_space_feasibility_research`  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 單元測試 | 驗證 `KnowledgeDBServiceWorker` 兩階段背景管線（Stage 1 `skip_vectors=True` 快篩更新 AST/BM25/圖譜 + Stage 2 微批次 `vector_batch_size` 逐步補齊向量差集直至覆蓋率 100%，以及微批次中途 `notify_space_changed` 事件插隊與零 `watchdog` 正交性） | FR-01, EC-02, NFR-02 | `TestSpaceEventHookAndCacheSync.test_knowledge_db_service_worker_two_stage_and_auto_model_download` |
| **FT-02** | 單元測試 | 驗證常駐 Worker 背景自動下載向量模型（當 `enable_vector_search=True` 且 `is_model_downloaded()=False` 時由 Worker 自動呼叫 `download_model()`，且不向 `stderr` 輸出 `[GUARD]` 阻斷提示） | FR-02, EC-05 | `TestSpaceEventHookAndCacheSync.test_knowledge_db_service_worker_two_stage_and_auto_model_download` |
| **FT-03** | 單元測試 | 驗證 `engine.is_worker_busy() -> int`（已運行 ms）探針、`elapsed_ms >= jit_vector_timeout_ms` 時等待 `0ms` 瞬時降級純 BM25 並印出 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`、`0 < elapsed_ms < timeout_ms` 剩餘容差等待、陳舊 PID 清理與跨平台狀態檔原子寫入 | FR-03, EC-01, EC-03, EC-04, NFR-01, NFR-03 | `TestSpaceEventHookAndCacheSync.test_is_worker_busy_probe_and_dynamic_tolerance_degradation` |
| **FT-04** | 單元測試 | 驗證 `KnowledgeDBConfig` 之 `jit_vector_timeout_ms: int = 3000` 預設值、`config.json` 優先權覆寫與舊鍵 `jit_vector_timeout_seconds` 向下相容自動換算 | FR-03, EC-06 | `TestEngine.test_config_loading_priority` & `TestSpaceIntegrationAndWeights.test_ft_02_knowledgedb_config_purity` |
| **FT-05** | 單元測試 | 驗證 `engine.status()` 與 `knowledge-db status`（含 `--json`）詳盡輸出：後台服務與忙碌毫秒數、當前檢索模式與原因、BM25/Graph/Vector 三大索引細部指標（含覆蓋率與待補數量）、模型與組態參數、空間游標 `acked_generation / head_generation` 對齊 | FR-04, FR-05 | `TestEngine.test_status_detailed_metrics_and_docstring_truncation` & `TestCLI.test_status_json_output` |
| **FT-06** | 回歸與合規測試 | 執行 `knowledge-db` 模組 AST 靜態合規檢查 (`dev check`) 與全套 155 項自動化回歸測試 (`dev test knowledge-db -q`) | FR-01, FR-02, FR-03, FR-04, FR-05, NFR-01, NFR-02, NFR-03 | `python yscb.py dev check knowledge-db && python yscb.py dev test knowledge-db -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestSpaceEventHookAndCacheSync.test_knowledge_db_service_worker_two_stage_and_auto_model_download` 通過：6 符號分批微批次補齊，`coverage_pct == 100.0`，`missing_count == 0` | 2026-11-02 |
| **FT-02** | `Passed` | `mock_dl.called == True` 且 `stderr` 無 `[GUARD]` 阻斷輸出 | 2026-11-02 |
| **FT-03** | `Passed` | `is_worker_busy()` 空閒回傳 `0`；忙碌 `1200ms >= 500ms` 時前台耗時 `< 150ms` 瞬時降級純 BM25 並輸出 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`；死進程 PID `99999999` 自動清理回傳 `0` | 2026-11-02 |
| **FT-04** | `Passed` | `jit_vector_timeout_ms` 預設 `3000` (`3.0s`)，支援 `config.json` 設定與 `jit_vector_timeout_seconds` 向下相容 | 2026-11-02 |
| **FT-05** | `Passed` | `status` 完整輸出 `worker`、`indices.{bm25,graph,vector}`、`retrieval_mode`、`jit_vector_timeout_ms` 與各空間 `acked_generation == head_generation` (`in_sync == True`) | 2026-11-02 |
| **FT-06** | `Passed` | `dev check knowledge-db`：`[PASS]`；`dev test knowledge-db -q`：`Pass: 155(100.0%), Fail: 0, Skip: 0`；本機 `install space@build knowledge-db@build --force` 熱部署驗證通過 | 2026-11-02 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py knowledge-db status` 與 `python yscb.py knowledge-db search "KnowledgeDBServiceWorker"`，確認終端機直白詳盡顯示後台 `knowledge-db-worker` 狀態、三大索引指標（BM25 / CallGraph / Vector 覆蓋率與待補數）、檢索模式與空間游標水位，且在後台向量更新超過 `jit_vector_timeout_ms` (`3000ms`) 時瞬時降級純 BM25 並提示 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]` | `[測試通過]` | 開發者確認實機動態測試（含物理刪除向量模型與向量索引之背景自動下載與微批次自癒）通過 |
