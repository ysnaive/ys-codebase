# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_03_server_three_plane_and_managed_worker_threads  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `WarmWorker.execute_task` 零全域突變（不呼叫 `os.chdir` / `os.environ` 原地覆寫），以 `bind_runtime_context` 綁定 `virtual_cwd` 與 `env`，並透過 `DebouncedIOStreamer` 傳遞輸出與 `error_hint` | FR-01 | `python yscb.py dev test server -q` (`TestWarmWorker`) |
| **FT-02** | 單元測試 | `BaseServiceWorker` 內建狀態機（`STARTING` / `UPDATING` / `READY` / `DEGRADED_OFFLINE` / `STOPPED`）、受管執行緒生命週期（`start_managed_thread` / `stop_managed_thread`）與 `ServiceManager.get_status()` 狀態輸出 | FR-02 | `python yscb.py dev test server -q` (`TestServiceManager`) |
| **FT-03** | 單元測試 | `CoreSpaceWatcherServiceWorker`、`GDriveSyncServiceWorker` 對齊 `BaseServiceWorker` 受管執行緒與狀態機，且移除 `file-space` / `knowledge-db` 之 `scripts/hook.server.py` 野生執行緒 | FR-03 | `python yscb.py dev test server -q` & `python yscb.py dev test file-space -q` & `python yscb.py dev test gdrive-support -q` |
| **FT-04** | 單元測試 | `EmbeddingService.has_local_model()` `< 1ms` 純本地檢查、`KnowledgeDBServiceWorker` 受管執行緒自動下載保留與離線 `DEGRADED_OFFLINE` 狀態轉移，以及 `model.cmd.download` `server_compatible: false` | FR-04 | `python yscb.py dev test knowledge-db -q` (`TestKnowledgeDBServiceWorker`) |
| **FT-05** | 單元測試 | `IndexingPipeline._ensure_jit_index_ready` 當 `unified.index.bin.gz` 存在且背景 Worker 運行中或 `!has_local_model()` 時走非阻塞快篩路徑，前台 `search` 零搶鎖等待 | FR-05 | `python yscb.py dev test knowledge-db -q` (`test_foreground_search_fast_path_skips_lock_when_worker_busy`) |
| **ET-01** | 邊界測試 | 熱派發執行期間背景 `ServiceWorker` 執行緒輸出日誌與讀取 `get_virtual_cwd()`，驗證背景日誌透過 `background_sink` 隔離為 `{"type": "log"}` IPC 封包，零污染前台 `terminal_stream` | EC-01 | `python yscb.py dev test server -q` (`test_execute_task_isolates_virtual_cwd_and_env_without_os_mutation`) |
| **ET-02** | 邊界測試 | 離線環境下 `KnowledgeDBServiceWorker` Stage 1 快速完成並釋放 `_index_lock`，Stage 2 自動下載失敗時轉為 `DEGRADED_OFFLINE` 並設 60 秒退避，零崩潰、零阻塞 | EC-02 | `python yscb.py dev test knowledge-db -q` (`test_stage2_auto_download_and_degraded_offline_state`) |
| **ET-03** | 邊界測試 | 背景 `KnowledgeDBServiceWorker` 持有 `_index_lock` 時前台併發呼叫 `_ensure_jit_index_ready(require_vectors=True)`，驗證非阻塞直接讀取既有索引快照且不等待鎖 | EC-03 | `python yscb.py dev test knowledge-db -q` (`test_foreground_search_fast_path_skips_lock_when_worker_busy`) |
| **ET-04** | 邊界測試 | `BaseServiceWorker.stop_managed_thread()` 與 `ServiceManager.stop_all()` 重複呼叫冪等性，以及 `server` 模組靜態合規檢查（零 `print`/`logging`/`os.chdir`/`os.environ` 突變、`@dataclass(frozen=True)`） | EC-04, NFR-02 | `python yscb.py dev check server` & `python yscb.py dev test server -q` |
| **PT-01** | 效能與離線預檢測試 | `EmbeddingService.has_local_model()` 純本地檔案檢查耗時 `< 1ms`，離線環境下前景 `search` 零網路超時等待 | NFR-01 | `python yscb.py dev test knowledge-db -q` (`test_has_local_model_is_fast_and_strict`) |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `server` 沙盒測試 63/63 (100.0%) 通過；`WarmWorker` 零 `os.chdir`/`os.environ` 突變，虛擬 CWD、環境隔離與 `get_last_error_hint()` 斷言正確 | 2026-11-08 |
| **FT-02** | `Passed` | `BaseServiceWorker` 五態狀態機、`start_managed_thread` / `stop_managed_thread` 與 `ServiceManager.get_status()` / `server status` 狀態輸出全綠 | 2026-11-08 |
| **FT-03** | `Passed` | `file-space` (17/17 passed, 1 skipped) 與 `gdrive-support` (34/34 passed) 全數通過，確認舊版 `hook.server.py` 已物理移除 | 2026-11-08 |
| **FT-04** | `Passed` | `knowledge-db` 沙盒測試 112/112 (100.0%) 通過；`has_local_model()` `< 1ms`、Stage 2 自動下載與離線 `DEGRADED_OFFLINE` 驗證通過 | 2026-11-08 |
| **FT-05** | `Passed` | 前台 `_ensure_jit_index_ready` 在背景 Worker 運行中/忙碌或無本地模型時零搶鎖直接載入 `unified.index.bin.gz` | 2026-11-08 |
| **ET-01** | `Passed` | 背景執行緒 `bind_log_context` 串流隔離驗證通過，前景與背景日誌零混流 | 2026-11-08 |
| **ET-02** | `Passed` | 離線環境模擬 `download_model` 失敗時 Worker 狀態平滑轉為 `DEGRADED_OFFLINE` (`phase="degraded_offline"`) | 2026-11-08 |
| **ET-03** | `Passed` | 背景持鎖時前台檢索 `< 5ms` 非阻塞返回既有索引快照 | 2026-11-08 |
| **ET-04** | `Passed` | `dev check server / knowledge-db / file-space / gdrive-support` 全數 `[PASS]`，且 `core` 281/281 測試回歸通過 | 2026-11-08 |
| **PT-01** | `Passed` | `test_has_local_model_is_fast_and_strict` 驗證單次純本地檢查耗時 `< 1ms`，離線環境零網路等待 | 2026-11-08 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 啟動或查詢 `python yscb.py server status` 與 `python yscb.py kdb search "BaseServiceWorker" --limit 3`，確認常駐服務狀態（如 `READY` / `DEGRADED_OFFLINE`）正常顯示、啟動日誌不再出現 `hook.server` 野生執行緒 `GitignoreEvaluator` 錯誤，且前景檢索瞬時返回無阻塞 | `[測試通過]` | 2026-11-08 實機自部署驗證通過 |
