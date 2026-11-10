# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：2026_11_09_2023_server_hot_dispatch_worker_race_and_ux_feedback  
> 建立日期：2026-11-10  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  

> 依據 P01-05：[P01-05_auto.md](./P01-05_auto.md)  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元 / 整合測試 | 驗證 `gdrive-support` 之 `branch` (`list` / `create` / `delete`) 已啟用 `server_compatible: true`；驗證客戶端於熱派發串流中途斷線時，`MasterSupervisor` 主動偵測並發送 `{"action": "cancel"}` 至 `WarmWorker` 觸發 `TaskCancelledError` 提前中止耗時任務且後續新派發正常運作。 | FR-01, EC-01, EC-02 | `python3 yscb.py dev test server core gdrive-support --no-build` |
| **FT-02** | 單元 / 並發測試 | 驗證 `CoreSpaceWatcherServiceWorker.flush_dirty_spaces(force=False)` 於 `server.worker.foreground_active=True` 時主動禮讓並累加 `deferred_by_foreground_count`；驗證 `KnowledgeDBServiceWorker` 在啟用向量但未下載本地模型時絕不呼叫 `download_model()` 且零阻塞進入 `DEGRADED_OFFLINE` (`busy=False`)；驗證 `EmbeddingService._ensure_model()` 在 `_init_lock` 被佔用時 0ms 非阻塞返回且 `HybridSearchEngine.is_vector_available` 優先短路。 | FR-02 | `python3 yscb.py dev test server knowledge-db --no-build` |
| **FT-03** | 單元 / UX 串流測試 | 驗證 `DebouncedIOStreamer` 對 `flush=True` 與 `stderr` `\r` 立即刷新（同時保留一般無 `flush` 換行緩衝合併）；驗證 `ASTEngine.build_index` / `hot_patch_index` 與 `IndexingPipeline.build_unified_index` 透過 `ProgressReporter` 輸出明確階段與百分比至 `stderr`，且 `--json` 模式下 `stdout` 100% 為合法純淨 JSON。 | FR-03, EC-05, NFR-02 | `python3 yscb.py dev test core ast knowledge-db --no-build` |
| **FT-04** | 單元 / 效能測試 | 驗證 `KnowledgeEngine.status()` 透過 `unified.meta.json` 與 `BinarySnapshotManager.load_summary()` 在 $<30\text{ms}$ 內完成查詢，全程零 `.bin.gz` 解壓且零 `iter_space_files()` 呼叫；驗證背景持鎖建圖時 `ASTEngine.status()` 與 `KnowledgeEngine.status()` 均非阻塞回傳 `building_in_progress: True`。 | FR-04, EC-03, NFR-01 | `python3 yscb.py dev test knowledge-db ast core --no-build` |
| **FT-05** | 單元 / 隔離測試 | 驗證 `ASTEngine.slice_part("<rel_path>::<fqn>")` 與 `slice_part(UnifiedSymbol)` 直接走單檔 `parse_file()` $O(1)$ 快速路徑（Mock `get_workspace_graph` 斷言 `assert_not_called()`），且對 C++ 雙冒號選擇器（非檔案路徑）平滑回退至工作區解析。 | FR-04, EC-04, NFR-01 | `python3 yscb.py dev test ast --no-build` |
| **FT-06** | 深度審計與全倉回歸 | 執行 `P06` 斷點最多三輪雙盲子代理靶向深度審計（`OPT/ARCH` x `PERF` x `AUD`），並驗證全倉 `dev check --all` 與 `-W error::ResourceWarning` 測試套件 100% 通過。 | FR-05, NFR-03 | `python3 -W error::ResourceWarning yscb.py dev test --no-build && python3 yscb.py dev check --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `server` (69/69)、`core` (305/305)、`gdrive-support` (38/38) 全數通過；驗證 `task_id` 取消隔離、`branch` 熱派發與取消回滾 | 2026-11-10 |
| **FT-02** | `Passed` | `CoreSpaceWatcherServiceWorker` 前景禮讓 + `5.0s` 防飢餓上限、`KnowledgeDBServiceWorker` `STATE_DEGRADED_OFFLINE` 離線守門與 `_ensure_model(blocking=False)` 通過 | 2026-11-10 |
| **FT-03** | `Passed` | `ProgressReporter` 250ms 節流與 `DebouncedIOStreamer` `stderr` 即時沖刷驗證通過，`--json` `stdout` 100% 純淨 | 2026-11-10 |
| **FT-04** | `Passed` | 實測冷啟動 `ASTEngine.status()` `0.95ms`、`KnowledgeEngine.status()` `2.02ms`、`SpaceScanner.get_snapshot_summary()` 暖快取 `0.15ms`（`0` 次 `gzip.open`） | 2026-11-10 |
| **FT-05** | `Passed` | 實測 `ASTEngine.slice_part("<rel>::<fqn>")` 冷啟動 `10.31ms` / 暖快取 `1.23ms`（加速 `246x~971x`），支援 C++ `::` 回退與 CRLF 無損切片 | 2026-11-10 |
| **FT-06** | `Passed` | 完成 Loop 1 ~ Loop 3 三軌雙盲子代理深度審計與修復；`dev check --all` `9/9 PASS (0 WARN)`，全倉 9 模組 `--all-types` + `-W error::ResourceWarning` `902/902 Passed` | 2026-11-10 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 檢查項 | 驗證方式 | 預期觀測結果 |
| :--- | :--- | :--- |
| **建圖即時進度反饋** | 強制重建 `ast` 或 `knowledge-db` 索引並觀察 `stderr` 與 `--json` `stdout` | `stderr` 即時串流顯示階段 `(1/3: 解析檔案 X/Y [Z%]...)` 與完成耗時，不再黑盒靜默；`stdout` 維持純淨結構化輸出。 |
| **靜態速查毫秒級回應** | 於背景建圖持鎖期間執行 `yscb ast status` 與 `yscb knowledge-db status` | 指令於 `<30ms` 內立即返回索引元數據與 `building_in_progress` 狀態，零卡死等待。 |
