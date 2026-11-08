# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Server Worker 常駐記憶體演算法治理、Core Space 快取共享、AST/KDB 查表去重與測試沙盒孤兒進程清理  
> 建立日期：2026-11-08  
> 所屬主計畫：N/A  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元與整合測試 | 驗證 `SpaceScanner` 基於 `(mtime_ns, size)` 的記憶體快照快取、Watcher 活躍時 `diff`/`consume_diff(auto_refresh=None)` 自動免重掃、顯式自訂 `storage_root` 自動回退重掃、`scan(None)` 物理雜湊複用與 `sync_dependent_snapshots_batch` 批次同步 | FR-01, EC-03, NFR-02 | `python yscb.py dev test --target=core:TestCoreSpaceAtomicEngine.test_snapshot_mem_cache_watcher_aware_diff_and_batch_sync -q` |
| **FT-02** | 單元與整合測試 | 驗證 `SemanticBundler.clear_transient_caches()` 於 `ASTEngine.build_index` 及 `hot_patch_index` 收尾後 100% 清空暫存字典，且於 `YSCB_IN_SERVER_WORKER=1` 常駐 Worker 環境內禁絕啟動 `ProcessPoolExecutor` | FR-02, NFR-01 | `python yscb.py dev test --target=ast:TestProvisionerAndJit.test_ast_engine_jit_sync_hot_patch_and_external_edge_preservation -q` |
| **FT-03** | 單元與整合測試 | 驗證 `ASTEngine._snapshot.symbols` 與 `InvertedIndex.symbols` 同進程共享 `UnifiedSymbol` 實例、非 AST 可解析檔案變更不觸發 `ast_engine.hot_patch_index`、以及 `KnowledgeDBServiceWorker` 世代/髒標記 O(1) 閒置守衛與離線降級感知 | FR-02, EC-02, NFR-01 | `python yscb.py dev test --target=knowledge-db:TestEngine.test_vector_probe_over_ten_symbols_and_timeout_degradation -q` |
| **FT-04** | 單元與邊界測試 | 驗證 `WorkerMemoryHealthMonitor` 演算法基線校準、嚴重膨脹 ($\ge 3.5\times$)、宿主可用記憶體壓力 ($< 15\%$ + $\ge 2.2\times$)、連續 5 視窗單調棘輪爬升偵測、冷卻防抖，以及 `MasterSupervisor._is_worker_completely_idle()` 背景服務繁忙防誤殺守衛 | FR-03, EC-01 | `python yscb.py dev test --target=server:TestServerModule.test_worker_memory_health_monitor_algorithm_and_idle_guard -q` |
| **ET-01** | 邊界與隔離測試 | 驗證 `kill_process_tree` 穿透 `start_new_session=True` (`setsid()`) 強制收割跨 Session 孫進程，以及 `reap_sandbox_processes(sandbox_dir)` 於 `cleanup_sandbox` 時依 `/proc` 徹底清除脫離沙盒之孤兒進程 | FR-04, EC-04, NFR-02 | `python yscb.py dev test --target=dev:TestSandboxArchitecture.test_cross_session_grandchild_and_sandbox_process_reaping -q` |
| **FT-05** | 單元與實機基準測試 | 驗證 `ASTEngine` 宣告式目標空間（`contributes/ast.json` + `register_spaces` / `on_register_ast_spaces` Hook）、`workflow.archived://` 排除、`Posting` 四整數槽位緊湊 6-tuple 序列化、前景任務讓渡，以及常駐 `WarmWorker` 連續執行 `ast` / `knowledge-db` CLI 之平均延遲與 RSS 記憶體指標 | FR-05, NFR-01 | `python yscb.py dev test ast -q --sync`、`python yscb.py dev test knowledge-db -q --sync`、`python yscb.py dev test agents-workflow -q --sync` |
| **RT-01** | 子系統全量回歸 | 驗證 `core`、`file-space`、`gdrive-support`、`ast`、`knowledge-db`、`server`、`dev`、`agents-workflow` 共 8 個受影響模組全量回歸測試 100% 通過並熱部署 `@build` | FR-01 ~ FR-05 | `python yscb.py dev test <module> -q --sync` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Pass: 1(100.0%), Fail: 0, Skip: 0` — 快照記憶體快取、Watcher O(1) diff 與 `sync_dependent_snapshots_batch` 驗證通過 | 2026-11-08 |
| **FT-02** | `Passed` | `Pass: 1(100.0%), Fail: 0, Skip: 0` — `SemanticBundler` 暫存快取於建構與熱修補後歸零、`YSCB_IN_SERVER_WORKER=1` 單執行緒執行驗證通過 | 2026-11-08 |
| **FT-03** | `Passed` | `Pass: 1(100.0%), Fail: 0, Skip: 0` — `UnifiedSymbol` 參照共享、非 AST 檔案免觸發 `hot_patch_index` 與背景服務兩階段同步驗證通過 | 2026-11-08 |
| **FT-04** | `Passed` | `Pass: 1(100.0%), Fail: 0, Skip: 0` — `WorkerMemoryHealthMonitor` 三維度演算法與 `_is_worker_completely_idle` 守衛驗證通過 | 2026-11-08 |
| **ET-01** | `Passed` | `Pass: 1(100.0%), Fail: 0, Skip: 0` — 穿透 `setsid()` 孫進程收割與 `reap_sandbox_processes` 孤兒進程清理驗證通過 | 2026-11-08 |
| **FT-05** | `Passed` | 母倉索引收斂為 `source` (351 檔)、`docs` (51 檔)、`plans` (60 檔) 共 3,892 符號 / 37,279 詞條（2,144.4 KB）；常駐 `WarmWorker` 連續處理 18 次 CLI 任務後 `Worker Memory` 穩定於 **386.5 MB**（較修復前 3.5~5.0 GB 下降 **>90%**）；Server 端派發平均耗時：`ast` **674.7 ms**（`outline` 274.4 ms）、`knowledge-db search` **509.4 ms** | 2026-11-08 |
| **RT-01** | `Passed` | 8 模組全量回歸合計 **811 項測試 100% 通過**（`core`: 285、`file-space`: 19、`gdrive-support`: 34、`ast`: 40、`knowledge-db`: 113、`server`: 65、`dev`: 110、`agents-workflow`: 145），並全數完成 `@build` 本機熱同步 | 2026-11-08 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py server status` 檢視儀表板新增之 `Worker Memory` 欄位（顯示即時 RSS、演算法基線 `Baseline`、峰值 `Peak` 與自動回收次數 `Auto-Recycles`），並觀察常駐 `worker.py` 在待機期間 CPU 回歸平穩、記憶體不再單向無上限膨脹 | `[測試通過]` | 開發者實機驗收通過（連續 18 次 CLI 查詢後 RSS 穩定於 386.5 MB，ast 平均派發 674.7 ms、kdb 平均派發 509.4 ms） |
