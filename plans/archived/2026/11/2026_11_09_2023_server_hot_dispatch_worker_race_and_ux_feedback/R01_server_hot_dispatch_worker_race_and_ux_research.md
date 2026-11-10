# 專題調研與分析報告：常駐 Server 全量熱派發、下游 Worker 競態與 CLI 即時進度暨靜態速查架構調研 (R01_server_hot_dispatch_worker_race_and_ux_research.md)

> 調研主題：全模組熱派發覆蓋、客戶端斷線感知、前景/背景跨層鎖競態、即時 `stderr` 進度串流與 $O(1)$ 狀態速查深度剖析  
> 建立日期：2026-11-10  
> 所屬主計畫：2026_11_09_2023_server_hot_dispatch_worker_race_and_ux_feedback  
> 調研狀態：Concluded  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - 在完成 `2026_11_10_0055`（消除 `WARMING` 預熱長阻塞與 `ASTEngine.status` 基礎 `meta.json`）與 `2026_11_10_0025`（`core.file_lock` 宣告式唯讀保護）後，針對大型專案日常高頻互動場景進行全鏈路體檢，仍存在四類結構性體驗與併發缺口：
    1. **熱派發覆蓋與斷線殘留缺口**：`gdrive-support` 之 `branch list/create/delete` 仍未啟用 `server_compatible: true`；且當使用者對耗時熱派發指令按下 `Ctrl+C` 時，`MasterSupervisor` 之 `chunk_emitter` 吞沒 `OSError`、未探測 socket EOF，亦無取消通道通知 `WarmWorker`。
    2. **背景 Worker 跨層鎖競態與隱式模型下載死鎖**：`CoreSpaceWatcherServiceWorker` 於 100ms 輪詢刷新時未檢查 `server.worker.foreground_active`，易與前景指令爭搶 `SpaceScanner` 鎖；`KnowledgeDBServiceWorker` 在模型缺失時私自呼叫 `download_model()` 獨佔 `EmbeddingService._init_lock`，而 `EmbeddingService._ensure_model()` 採阻塞式 `with self._init_lock:` 且 `HybridSearchEngine.is_vector_available` 先觸發模型探測才檢查 `vector_index` 是否非空。
    3. **耗時建圖「黑盒靜默」與串流刷新延遲**：`ASTEngine.build_index` / `hot_patch_index` / `WorkspaceGraphLinker.link_workspace` 與 `IndexingPipeline` 缺乏即時階段與百分比回報；且 `core/log.py` 之 `_write_to_active_target` 在路由至 `DebouncedIOStreamer` 時忽略 `flush=True` 參數，導致進度提示被延遲最高 500ms。
    4. **靜態 `status` 重載與單檔 `slice` 誤觸全倉建圖**：`KnowledgeEngine.status()` 仍同步解壓 `unified.index.bin.gz` / `unified.vectors.bin.gz` 並在無快照時呼叫 `iter_space_files()` 全盤掃描；`ASTEngine.status()` 在無 `meta.json` 或建圖期間仍退回阻塞式 `with self._lock:`；`ASTEngine._resolve_symbol_node_for_slice()` 對 `<rel_path>::<fqn>` 無條件呼叫 `get_workspace_graph(auto_sync=True)`。
- **調研目標**：
  - 精確定位上述四大支柱對應之全部檔案行號座標、設計非破壞性修繕方案，並確保與既有單元測試契約（如 `DebouncedIOStreamer` 一般換行緩衝、`model download` 冷派發約束）100% 相容。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 全模組 `contributes/core.json` 熱派發盤點矩陣

| 模組 | 已啟用 `server_compatible: true` 指令 | 維持 `false` 之合理冷派發指令 | 本期補齊升級項目 |
| :--- | :--- | :--- | :--- |
| `core` | `list`, `status`, `uri`, `config`, `event`, `contributes`, `gitignore`, `file-space`, `file-lock` | `install`, `update`, `remove`, `reload`, `rollback`, `restore`（變更 `.modules` 結構） | 已於 Task 1 補齊 `file-lock` 全子指令；維持完整 |
| `dev` | `create`, `check`, `build`, `release`, `release-check`, `index-patch`, `bump-*` | `test`, `op-mksb`, `op-test`, `release-git`（沙盒隔離與外部 Git 程序） | 維持完整 |
| `agents-workflow` | `plan`, `release`, `release-target`, `compile`, `roadmap`, `todo`, `tokens`, `session-trace`, `list` | `init`（工作區初始化） | 維持完整 |
| `vscode-support` | `status`, `sync`, `revert` | 無 | 維持完整 |
| `file-space` | `status`, `scan`, `files`, `diff` | `clean`（清除底層快取） | 維持完整 |
| `gdrive-support` | `status`, `ls`, `get`, `put`, `rm`, `mkdir`, `shortcut` | `auth`, `init`, `checkout`, `pull`, `push`, `sync`（OAuth 互動或全樹雙向同步） | **將 `branch` 及其子指令 `list`, `create`, `delete` 升級為 `server_compatible: true`** |
| `ast` | `outline`, `callers`, `callees`, `impact`, `status`, `slice`, `traverse` | `clean`（並補強 `_ensure_symbols_loaded` 於檔案刪除後清記憶體快取） | 維持路由並補強外部 `clean` 記憶體失效同步 |
| `knowledge-db` | `status`, `index`, `search`, `model` (`status`) | `clean`, `model download`（契約測試鎖定冷派發） | 維持完整 |
| `server` | 無 | `start`, `stop`, `status`, `reload`（守護進程控制面） | 維持完整 |

### 2.2 客戶端斷線感知與前景/背景競態根因定位

| 編號 | 定位座標 | 問題機制 | 定案工程解法 |
| :--- | :--- | :--- | :--- |
| **RC-T2-01** | `server/master.py:L1038-1058, L1513-1522`<br>`server/worker.py:L379-405` | `chunk_emitter` 吞沒 `OSError`，`task_q.get()` 無逾時輪詢 socket FIN，且 `worker_main` 同步阻塞於 `execute_task` 無法接收取消控制訊號 | 1. `chunk_emitter` 捕獲 `OSError` 時置位 `disconnect_event`，搭配非阻塞 socket EOF 探針 `_is_client_socket_closed()`。<br>2. `_stream_task_over_worker_pipe` 以 `0.2s` 輪詢，偵測斷線時發送 `{"action": "cancel"}\n` 至 Worker stdin 並持續排空至 `task_finish` 保持幀同步。<br>3. `worker_main` 以專屬讀取執行緒將 `"dispatch"`/`"exit"` 放入 FIFO 佇列，遇 `"cancel"` 立即置位 `RuntimeContext` 之協作取消旗標。 |
| **RC-T2-02** | `server/space_watcher.py:L734-777, L895-915` | `CoreSpaceWatcherServiceWorker.flush_dirty_spaces` 僅檢查 `.yscb.lock`，未檢查 `server.worker.foreground_active` | 於 `flush_dirty_spaces(force=False)` 與啟動預掃描迴圈檢查 `_is_foreground_active()`，前景活躍時遞增 `_deferred_by_foreground_count` 並主動禮讓。 |
| **RC-T2-03** | `knowledge_db/service.py:L647-670`<br>`knowledge_db/embedding.py:L310-325`<br>`knowledge_db/hybrid.py:L87-94` | Stage 2 未獲授權自動呼叫 `download_model()` 獨佔 `_init_lock`；`_ensure_model()` 阻塞等待 `_init_lock`；`is_vector_available` 先調用 `embedding_service.is_available` | 1. 移除 Stage 2 自動 `download_model()`，無本地模型時直接零阻塞標記 `DEGRADED_OFFLINE` (`busy=False`)。<br>2. `_ensure_model(blocking=False)` 預設採 `acquire(blocking=False)`，鎖忙碌時 0ms 返回。<br>3. `is_vector_available` 改為先檢查 `len(vector_index.doc_ids) > 0` 與 `has_local_model()`。 |

### 2.3 低延遲進度反饋與靜態速查 $O(1)$ 優化設計

| 編號 | 定位座標 | 現況瓶頸 | 定案工程解法 |
| :--- | :--- | :--- | :--- |
| **RC-T2-04** | `core/log.py:L229-240, L369-388, L459-477` | `_write_to_active_target` 路由至 `scope.streamer` 時忽略 `flush=True`；`test_server.py:L1488` 要求普通無 `flush` 之換行寫入維持緩衝合併 | `DebouncedIOStreamer.write(stream_name, text, *, flush=False)` 支援顯式 `flush=True`（及 `_StreamProxy` 對 `stderr` 含 `\r` 之進度覆寫即時刷新），既保留一般 `stdout`/`stderr` 批次合併契約，又讓進度訊號 0ms 直達終端。 |
| **RC-T2-05** | `ast_engine/{engine,bundler,linker}.py`<br>`knowledge_db/pipeline.py` | 耗時建圖與索引過程 0 輸出 | 於 `core.log` 實作 `ProgressReporter`（`initial_delay_ms=200`、`interval_ms=250`、支援 `is_task_cancelled()` 檢查與背景 `ServiceWorker` 自動靜默），植入 `ASTEngine` 與 `IndexingPipeline` 輸出階段與百分比至 `stderr`。 |
| **RC-T2-06** | `knowledge_db/engine.py:L601-820`<br>`core/space/scanner.py:L272-330` | `KnowledgeEngine.status()` 同步解壓 `.bin.gz` 並退回 `iter_space_files()`；`BinarySnapshotManager.load_state` 解碼全部路徑字串 | 1. 建置/修補/刷寫時同步寫入 `indices/unified.meta.json`，`KnowledgeEngine.status()` 優先讀取記憶體或 `unified.meta.json`，移除 `iter_space_files()`。<br>2. `BinarySnapshotManager.load_summary()` 僅掃描二進位標頭與記錄長度計算活躍檔案數，零字串解碼與零物件分配。 |
| **RC-T2-07** | `ast_engine/engine.py:L1524-1580, L2002-2019` | `ASTEngine.status()` 回退路徑仍阻塞等鎖；`_resolve_symbol_node_for_slice()` 無條件觸發 `get_workspace_graph(auto_sync=True)` | 1. `ASTEngine.status()` 全面改為非阻塞鎖探測並回報 `building_in_progress` 與即時進度。<br>2. `_resolve_symbol_node_for_slice()` 對 `<rel_path>::<fqn>` 與 `UnifiedSymbol` 直接呼叫單檔 `parse_file()` $O(1)$ 解析。 |

---

## 3. 結論 (Conclusion)

- 透過上述四大支柱協同改造，可在 **100% 向下相容既有 CLI 與 JSON 輸出契約** 的前提下，徹底消除常駐 `server` 下前景與背景執行緒之鎖競爭與模型下載死鎖，賦予耗時建圖毫秒級即時進度透明度，並確保所有 `status` 速查與單檔 `slice` 指令恆定於 $<30\text{ms}$ 內瞬時回應。
