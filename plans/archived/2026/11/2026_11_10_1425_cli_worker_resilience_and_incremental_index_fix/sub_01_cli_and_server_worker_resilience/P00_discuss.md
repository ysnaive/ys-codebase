# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：CLI 觸發鍊與 Server/Worker 防卡死韌性加固  
> 建立日期：2026-11-10  
> 所屬主計畫：2026_11_10_1425_cli_worker_resilience_and_incremental_index_fix  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：深度修復 CLI 觸發鍊與 `server` / `WarmWorker` 協作邏輯中容易卡住的確定性問題。
- **核心目標**：徹底消除 Worker 重入 Hot-Dispatch 死鎖、子進程繼承 IPC 管道句柄導致 EOF 死鎖與 NDJSON 穿刺、`sys.stdin` 控制管線競爭、`Ctrl+C` 中斷後孤兒任務永久霸佔 `_dispatch_lock`、長耗時任務 120s 假逾時、停機/重載競態、`GDriveSync` 破壞 Idle TTL 及無逾時外部網路/子進程呼叫。
- **既有組件復用與查重 (Reuse Discovery)**：復用 `core.context.get_env`、`core.platform.process.kill_process_tree`、`core.service_contract` 前景活躍感知與 `MasterSupervisor` 既有 `_kill_worker_locked` 重建機制。
- **邊界排除 (Explicitly Excluded)**：不改為多進程 Worker Pool（維持單例低記憶體常駐模型，透過重入旁路與取消強殺升級確保零死鎖）。
- **架構影響範圍**：`core`（`dispatcher.py`、`pip_manager.py`、`installer.py`、`update_checker.py`）、`server`（`master.py`、`worker.py`、`watcher.py`、`space_watcher.py`、`scripts/cli.py`）、`gdrive-support`（`service.py`）、`knowledge-db`（`service.py`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 重入旁路守衛**：於 `dispatcher._dispatch_inner` 檢查 `YSCB_IN_SERVER_WORKER == "1"` 與 `YSCB_NO_HOT_DISPATCH == "1"`，命中時強制走本地 `dispatch_local`，阻斷單例 Worker 自我等待死鎖。
- **[P00:DR-02] 真實子進程模式專用 IPC FD 與 `stdin` 隔離**：當 `worker_main(in_stream=None, out_stream=None)` 以真實子進程啟動時，以 `os.dup(1)` 複製並標記 `os.set_inheritable(ipc_fd, False)` 作為唯一 NDJSON 輸出通道，將 OS `fd 0` 與 `fd 1` 重導向至 `os.devnull`（保留 `in_stream`/`out_stream` 注入參數相容既有記憶體測試），且任務執行期將 `sys.stdin` 綁定空 `io.StringIO("")`；Master 端於 `_stream_task_over_worker_pipe` 每輪輪詢檢查 `proc.poll()`，修正重複 `worker_ready` `continue` 與有界 `task_q(maxsize=512)`。
- **[P00:DR-03] 兩段式取消強殺升級與心跳協定**：Master 在串流等待期間每 `15.0s` 發送 `{"type": "heartbeat"}` 保活（Client 端自動略過並支援選配 `YSCB_DISPATCH_MAX_WALL_SEC` 總時限）；當偵測 Client Socket 斷線並送出協作式 `cancel` 後，若超過寬限期（預設 `5.0s`，可由 `YSCB_CANCEL_GRACE_SEC` 覆寫）仍未結束，自動強殺回收該卡死 Worker 並釋放 `_dispatch_lock`。
- **[P00:DR-04] 停機狀態機閉鎖與溫和重載**：自訂 `ThreadingHTTPServer` 子類設 `block_on_close = False` 並設 `DispatcherHTTPHandler.timeout = 10.0`；`restart_worker()` 與 `_spawn_worker_locked()` 嚴格檢查 `_is_stopped`；`ModulesWatcher` 改用 `Event.wait` 與快照鎖，且若前景任務超過排空時間仍在執行，改設 `_pending_worker_reload = True` 於任務結束時自動重載而非腰斬使用者指令；`server/scripts/cli.py` `stop`/`reload` 等待預算調升至 `15.0s`。
- **[P00:DR-05] 背景服務 Idle TTL 保護、前景禮讓與外部 I/O 逾時**：`GDriveSyncServiceWorker` 支援 `is_foreground_active()` 禮讓、抑制自身同步期間的 `core.space` 自我喚醒，且僅在實際發生遠端/本地變更動作時才觸發 `touch_activity()`；`KnowledgeDBServiceWorker` 禮讓前景時延遲 `flush_vector_index` 至前景結束後執行；`CoreSpaceWatcher` 加入 `max_debounce_seconds = 5.0` 防餓死上限；補齊 `PipManager.install_packages(timeout=300)`、`fetch_and_extract_zip(..., timeout=30)`，並在 `--json` 跳過 `UpdateChecker` 及預寫節流時間戳防離線重複卡頓。

---

## 3. 開放議題與確認紀錄

- 全部決策均為確定性修復，無開放待決議題。
