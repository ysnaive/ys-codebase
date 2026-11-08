# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_03_server_three_plane_and_managed_worker_threads  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：完成 `sub_02` 並提交後，啟動第三個子計畫 `sub_03_server_three_plane_and_managed_worker_threads`。
- **核心目標**：
  1. **Jupyter 式常駐三平面解耦與 `WarmWorker` 全域突變根除（`server/server/worker.py`）**：
     - 解耦常駐進程之控制通道（Control Channel）與命令執行通道（Shell Execution Channel）：拔除 `worker_main()` 啟動期將全域 `sys.stdout = sys.stderr` 重導向之污染作法，以及 `WarmWorker.execute_task()` 在每次熱派發期間呼叫 `os.getcwd()`、`os.chdir(cwd)`、`os.environ.update(env)` 與 `_restore_env_diff(orig_env)` 的進程級全域突變。
     - 將 `WarmWorker.execute_task()` 對接 `core.context.bind_runtime_context(virtual_cwd=cwd, env=merged_env, host_dir=..., yscb_dir=self.yscb_root, module_name=module)` 與 `core.log.DebouncedIOStreamer`（`with streamer:`），使前景熱派發輸出 100% 經由 `ContextVar` 隔離投遞至 IPC 通道，同時背景執行緒完全不受 `virtual_cwd`、`env` 或串流切換干擾。
  2. **`BaseServiceWorker` 原生受管獨立執行緒、非阻塞狀態機與移除 `hook.server.py` 野執行緒（`server/server/service.py`、`space_watcher.py`、`knowledge_db/service.py`、`gdrive_support/service.py`）**：
     - 擴充 `ys_codebase/source/server/server/service.py:BaseServiceWorker`，內建受管 Daemon 執行緒生命週期（`_thread`、`_stop_event`、`start_managed_thread` / `stop_managed_thread`、可覆寫之 `_run_loop()`）與標準非阻塞狀態機（`STARTING`、`UPDATING`、`READY`、`DEGRADED_OFFLINE`、`STOPPED`），並在受管執行緒內自動掛載 `bind_log_context(background_sink=..., component=self.name)`，確保背景服務日誌 100% 導向 Server 日誌管線而絕不混入前景終端串流。
     - 將 `server/server/service.py` 頂層可變狀態（`_LAST_TOUCH_TS`、`_LAST_TOUCH_BY_ROOT`）收斂至實例或受控狀態容器，並將 `server` 模組內部生產代碼（`master.py`、`worker.py`、`service.py`、`space_watcher.py`、`watcher.py`、`config.py`、`scripts/cli.py`）之 `print` / `logging` / `os.getcwd` / 未凍結 `@dataclass` 對齊至 `core.log` 與 `core.context` 規範。
     - 對齊全倉 3 個註冊常駐服務（`CoreSpaceWatcherServiceWorker`、`KnowledgeDBServiceWorker`、`GDriveSyncServiceWorker`）之狀態回報與受管執行緒契約，並**物理刪除** `ys_codebase/source/file-space/scripts/hook.server.py` 與 `ys_codebase/source/knowledge-db/scripts/hook.server.py`（消除啟動期私開野執行緒與 `file-space` 舊版 `GitignoreEvaluator` 匯入警告）。
  3. **`knowledge-db` 離線模型預檢（`has_local_model()`）、背景受管執行緒非阻塞自動下載、CLI 解耦與修復前景搜尋搶鎖阻塞（`knowledge_db/embedding.py`、`service.py`、`pipeline.py`、`engine.py`、`contributes/core.json`）**：
     - 於 `ys_codebase/source/knowledge-db/knowledge_db/embedding.py:EmbeddingService` 實作純本地 `< 1ms` 磁碟快取預檢方法 `has_local_model() -> bool`（與 `is_model_downloaded()` 雙向對齊，不觸發任何網路 I/O 或 FastEmbed 初始化）。
     - 於 `ys_codebase/source/knowledge-db/knowledge_db/service.py:KnowledgeDBServiceWorker._run_sync_cycle` **保留背景受管執行緒自動下載模型機制**：確保 Stage 1（AST / BM25 毫秒級熱更新）優先落盤並釋放 `_index_lock` 後，才在 Stage 2 由專屬受管執行緒（綁定 `bind_log_context` 背景日誌隔離）非阻塞嘗試 `emb_svc.download_model(force=False)`（含冷卻退避）；若離線或下載失敗則標記狀態為 `DEGRADED_OFFLINE`，一旦下載完成並補齊向量即自動轉為 `READY`。
     - 於 `ys_codebase/source/knowledge-db/contributes/core.json` 將手動觸發之 `model.cmd.download` 標註為 `"server_compatible": false`，使開發者顯式手動下載模型時於前景獨立進程執行，不佔用常駐主執行緒命令通道。
     - 修復 `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py:IndexingPipeline._ensure_jit_index_ready` 前景 `search` 搶鎖阻塞問題：當背景 `knowledge-db-worker` 正在運行（`is_worker_running`）且磁碟已存在可用之 `unified.index.bin.gz`（或記憶體已載入 `_unified_index`）時，前景 `search` 直接非阻塞讀取既有索引快照（若 `!has_local_model()` 則 `< 1ms` 秒退純 BM25 零等待）返回，不與背景 Worker 爭搶 `_index_lock` 或重複觸發 `_consume_space_diff` / `build_index`。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 直接復用 `sub_01` 建立之 `core.log`（`DebouncedIOStreamer`、`bind_log_context`、`log*`、`RollingFileLogger`）與 `sub_02` 建立之 `core.context`（`bind_runtime_context`、`get_runtime_context`、`get_virtual_cwd`）及 `core.loader`（`load_module_from_path`），不另造平行上下文或日誌機制。
- **邊界排除 (Explicitly Excluded)**：
  - `knowledge-db` 與 `gdrive-support` 其餘非 `sub_03` 目標檔案之全量 `print()` / `@dataclass(frozen=True)` 機械合規遷移屬 `sub_04` 範疇。
  - `dev/checker.py` 13 項 AST 靜態守門正式啟用屬 `sub_05` 範疇。
- **架構影響範圍**：
  - `ys_codebase/source/server/server/{worker,service,space_watcher,master,watcher,config}.py` 與 `ys_codebase/source/server/scripts/cli.py`
  - `ys_codebase/source/file-space/scripts/hook.server.py`（物理刪除）
  - `ys_codebase/source/knowledge-db/scripts/hook.server.py`（物理刪除）
  - `ys_codebase/source/knowledge-db/contributes/{core,server}.json`
  - `ys_codebase/source/knowledge-db/knowledge_db/{embedding,service,pipeline,engine}.py` 與 `ys_codebase/source/knowledge-db/scripts/cli.py`
  - `ys_codebase/source/gdrive-support/gdrive_support/service.py`
  - `ys_codebase/source/server/tests/` 與 `ys_codebase/source/knowledge-db/tests/`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `WarmWorker` 控制/執行通道分離與零全域突變派發契約（軸一 & 軸二：既有組件復用與無副作用隔離）**：
  - `WarmWorker` 維持專用 `ipc_pipe` 傳遞 NDJSON 控制與串流封包；`execute_task()` 移除 `os.chdir(cwd)` 與 `os.environ.update(env)` / `_restore_env_diff`，改以 `with bind_runtime_context(virtual_cwd=cwd, env=task_env, host_dir=host_dir, yscb_dir=self.yscb_root, module_name=module):` 包裹 `with streamer:` 與 `dispatch_cli(...)`。
  - 同時在 `execute_task()` 結尾由 `core.log.get_last_error_hint()` 與 `dispatcher.get_last_dispatch_error_hint()` 取得結構化 `error_hint`，確保異常與 `SystemExit` 退出碼、錯誤摘要 100% 精準回傳。
- **[P00:DR-02] `BaseServiceWorker` 原生受管執行緒、狀態機與背景日誌隔離（軸三：生命週期與逆向拆卸冪等性）**：
  - `BaseServiceWorker` 定義標準狀態常數（`STATE_STARTING = "STARTING"`, `STATE_UPDATING = "UPDATING"`, `STATE_READY = "READY"`, `STATE_DEGRADED_OFFLINE = "DEGRADED_OFFLINE"`, `STATE_STOPPED = "STOPPED"`），內建 `_state`、`_thread`、`_stop_event` 與受管執行緒包裝器 `_managed_thread_entry()`（自動以 `bind_log_context(background_sink=..., component=self.name)` 將背景 `log*` 轉發為 IPC `{"type": "log", ...}` 封包寫入 Server 日誌檔）。
  - `ServiceManager.stop_all()` 與 `BaseServiceWorker.stop()` 保證可重複呼叫之冪等性（Idempotent Teardown），且 `get_status_list()` 同時回報 `name`、`provider`、`alive` 與 `state`（向後相容既有 `alive: bool` 欄位）。
- **[P00:DR-03] `knowledge-db` 離線模型預檢 `has_local_model()`、保留背景受管執行緒自動下載與前景 `search` 零搶鎖快速路徑（軸二 & 軸四：預設行為與跨切面不變量）**：
  - `EmbeddingService.has_local_model()` 直接委派/對齊純本地檔案系統檢查（檢查 `cache_dir` 下 ONNX 權重檔是否存在且大小 `> 0`，耗時 `< 1ms`）；`KnowledgeDBServiceWorker._run_sync_cycle` 在獨立受管執行緒內先完成 Stage 1 AST/BM25 同步並釋放 `_index_lock`，隨後於 Stage 2 若發現 `enable_vector_search=True` 且 `not emb_svc.has_local_model()`，則在受管執行緒中（受 `bind_log_context` 串流隔離保護且具 60 秒重試退避）非阻塞執行 `download_model(force=False)`；若離線下載失敗則標記 Worker 狀態為 `DEGRADED_OFFLINE`（`phase="degraded_offline"`），下載成功並完成向量微批次補齊後即轉為 `READY`。
  - `IndexingPipeline._ensure_jit_index_ready` 新增快速非阻塞路徑：當磁碟已有 `unified.index.bin.gz`（或記憶體已有 `_unified_index`）且背景 `is_worker_running(self._storage_dir)` 為 `True`（或 `_index_lock.acquire(blocking=False)` 顯示正在建置）時，前景 `search` 直接載入既有索引快照立即可用（且當 `not emb_svc.has_local_model()` 時直接走純 BM25 零等待返回），不阻塞等待背景 Worker 釋放鎖或下載模型。

---

## 3. 開放議題與確認紀錄

- 全數架構邊界與主計畫 `umbrella_overview.md` 支柱三規格已 100% 對齊，無未決開放議題。
