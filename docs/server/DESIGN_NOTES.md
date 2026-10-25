---
target: "Server"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb://yscb.py"
  - "yscb://source/core/core/platform/process.py"
  - "yscb://source/core/core/commands/dispatcher.py"
  - "yscb://source/server/server/master.py"
  - "yscb://source/server/server/worker.py"
  - "yscb://source/server/scripts/cli.py"
related_docs:
  - "./README.md"
  - "./daemon_architecture.md"
  - "./hot_reload_and_services.md"
  - "./realtime_logging.md"
last_updated: "2026-10-25"
---

# Server 模組工程妥協與防坑邊界 (DESIGN_NOTES.md)

本文件僅記錄 `server` 模組與宿主協同中為解決「跨進程死鎖、作業系統沙盒與管道限制、自動化測試契約相容」而採取的反直覺工程妥協與防坑邊界（維度 ⑤）。常規雙進程架構、服務託管、熱重載與日誌機制請參閱 [README.md](./README.md)、[daemon_architecture.md](./daemon_architecture.md)、[hot_reload_and_services.md](./hot_reload_and_services.md) 與 [realtime_logging.md](./realtime_logging.md)。

| 決策編號 | 標題 / 主題 | 影響檔案 | 風險等級 |
| :--- | :--- | :--- | :---: |
| **[DN-01]** (原 DN-03) | 宿主 `module == "server"` 自循環熱派發旁路與零靜態耦合邊界 | `yscb.py`, `core/commands/dispatcher.py` | High |
| **[DN-02]** (原 DN-10) | Windows Job Object 沙盒收割防禦與 `IsProcessInJob` 權限探針自動降級 | `core/platform/process.py`, `core/commands/dispatcher.py` | High |
| **[DN-03]** (原 DN-11) | Worker `proc.stderr` OS 64KB Pipe 阻塞死鎖排空、IPC `_dispatch_lock` 與 FD 管道清理 | `server/master.py`, `server/worker.py` | High |
| **[DN-04]** (原 DN-12) | CLI 啟動橫幅與停機報告之自動化契約錨點字串保留 | `server/master.py`, `scripts/cli.py` | Medium |
| **[DN-05]** | Worker 私有 `_ipc_stdout` 管道隔離與全域 `stdout` 重導向防污染 | `server/worker.py` | High |
| **[DN-06]** | Master 兩階段平滑關閉協定 (NDJSON Exit Handshake + Process Tree Harvest) | `server/master.py` | High |
| **[DN-07]** | Server 執行期零 `source/` 嚴格沙盒路徑隔離與動態 Provider 注入 | `server/master.py`, `server/service.py` | High |
| **[DN-08]** | `WarmWorker.pre_warm()` 服務路徑先行載入時序與 `MasterSupervisor.stop()` 冪等防重入 | `server/worker.py`, `server/master.py` | High |

---

### [DN-01] (原 DN-03) 宿主 `module == "server"` 自循環熱派發旁路與零靜態耦合邊界
- **背景與陷阱**：
  1. 若 `yscb.py` 或核心命令派發器對所有指令無差別執行 Hot-IPC 轉發（`_try_hot_dispatch`），當開發者執行 `python yscb.py server stop`、`server status` 或 `server reload` 時，該管理指令會被轉發進入正在運行的 Server Worker 中執行，導致 Worker 嘗試關閉或重啟其宿主 Master 並等待自身 HTTP 回應，引發跨進程 **IPC 自我等待死鎖 (Self-Wait Deadlock)**。
  2. 此外，若 `yscb.py` 頂層靜態 `import server`，一旦 `.modules/server` 未安裝或重構損毀，將直接導致整個微內核 CLI 宿主崩潰無法啟動。
- **工程決策**：
  1. **自循環強制旁路**：在派發攔截入口強制檢查 `module == "server"`；凡目標為 `server` 本體之指令一律旁路跳過 `_try_hot_dispatch` 與 `auto_spawn`，100% 走本地進程冷啟動直接操作 PID/HTTP 控制介面。
  2. **零靜態耦合**：`yscb.py` 與 `core` 嚴禁頂層靜態引入 `server` 內部模組，僅透過標準庫 HTTP 與狀態檔探測進行軟依賴協同。

> [!CAUTION]
> 嚴禁移除命令派發器中對 `module == "server"` 的熱派發旁路特判，否則執行 `server stop` 或 `server reload` 時將因 Worker 向自身所屬 Master 發起同步控制請求而觸發永久死鎖；同時嚴禁在 `yscb.py` 頂層加入對 `server` 的靜態 import。

---

### [DN-02] (原 DN-10) Windows Job Object 沙盒收割防禦與 `IsProcessInJob` 權限探針自動降級
- **背景與陷阱**：IDE Agent（如 Antigravity / Cursor / Claude Code）或受限 CI 容器在執行單次工具命令時，通常將子進程置於未開啟 `JOB_OBJECT_LIMIT_BREAKAWAY_OK` 權限的 Windows Job Object 沙盒中。當單次 CLI 命令結束時，作業系統會強制收割整棵進程樹。若此時盲目觸發 `auto_spawn` 背景拉起 Server，新拉起的 Master 進程會在命令退出的瞬間被 OS 連帶殺死，導致「每次 CLI 呼叫都耗費數百毫秒重複拉起 Server 又立即被殺」的嚴重效能退化與進程抖動。
- **工程決策**：
  1. 於 `core.platform.process` 實作 `can_spawn_background_daemon()` 探針並配置進程級記憶體快取。
  2. 在 Windows 環境下透過 `ctypes` 調用 `kernel32.IsProcessInJob` 檢測當前進程是否受困於 Job Object，並透過 1 次輕量級 Breakaway 探針確認是否具備脫鉤權限。
  3. 當 `auto_spawn` 為 `true` 但探針判定無背景脫鉤權限時，**強制阻斷背景拉起**並自動降級至本地極速冷派發（~86ms），同時於 `sys.stderr` 輸出防洗頻診斷提示。

> [!CAUTION]
> 在修改 `spawn_detached` 或自動喚醒邏輯時，嚴禁繞過 `can_spawn_background_daemon()` 探針直接呼叫底層進程建立 API，否則在受限沙盒環境下將引發每次 CLI 調用無效重啟與孤兒鎖檔殘留。

---

### [DN-03] (原 DN-11) Worker `proc.stderr` OS 64KB Pipe 阻塞死鎖排空、IPC `_dispatch_lock` 與 FD 管道清理
- **背景與陷阱**：
  1. **OS 64KB Pipe Buffer 阻塞死鎖**：`WarmWorker` 透過 `subprocess.Popen` 拉起時，其 `stdout` 用於 NDJSON IPC 通訊，而底層 C 擴充套件（如向量引擎、Tokenizer）或未捕獲之底層警告會直接寫入原生 `proc.stderr` 管道。若 Master 未持續讀取 `proc.stderr`，一旦輸出累積超過作業系統 Pipe 緩衝區上限（通常為 **64KB**），Worker 進程將在底層 `write(2)` 系統調用處被 OS 永久阻塞，導致 IPC 主迴圈無預警卡死。
  2. **Stdio IPC 並發交錯**：當多個 HTTP 請求（如狀態查詢與命令派發）並發抵達 Master 時，若同時對同一個 Worker 的 `stdin`/`stdout` 進行讀寫，會造成 NDJSON 封包交錯損毀。
  3. **FD 管道洩漏**：Worker 重啟或退場時若僅 `terminate()` 而未顯式關閉 `stdin`/`stdout`/`stderr` Stream，長駐重載多次後將耗盡檔案描述符 (File Descriptors)。
- **工程決策**：
  1. **專屬 Daemon 執行緒持續排空 `stderr`**：Master 每次啟動 Worker 子進程時，強制拉起一條背景 Daemon 執行緒持續讀取並排空 `proc.stderr`（轉發至 `ServerLogger`），徹底根除 64KB 緩衝區填滿死鎖。
  2. **`_dispatch_lock` 互斥序列化**：Master 引入 `self._dispatch_lock` (`threading.Lock`)，嚴格保護所有對 Worker `stdin` 寫入與 `stdout` 封包讀取的完整週期。
  3. **終止時顯式關閉管道**：在 `_stop_worker()` 中，終止子進程前後必須顯式 `close()` 其 `stdin`、`stdout` 與 `stderr` 管道以釋放 OS FD。

> [!CAUTION]
> 嚴禁在 `MasterSupervisor` 中移除 `proc.stderr` 背景排空執行緒、移除 `_dispatch_lock` 鎖保護，或省略 `_stop_worker` 中的管道 `close()` 清理，否則將在重型模組輸出、並發請求或多次熱重載時引發進程死鎖與 FD 資源洩漏。

---

### [DN-04] (原 DN-12) CLI 啟動橫幅與停機報告之自動化契約錨點字串保留
- **背景與陷阱**：`server start` 與 `server stop` 的終端輸出已升級為多行結構化 ASCII 啟動橫幅 (`format_startup_banner()`) 與停機統計總結報告 (`format_shutdown_summary()`)。然而，全系統整合測試套件與外部自動化腳本依賴特定的標準子字串來判讀守護進程是否成功啟動或優雅停止。
- **工程決策**：
  1. `format_startup_banner()` 渲染之結構化橫幅內，固定包含 `[Server] Daemon successfully started!` 標準標誌行。
  2. `format_shutdown_summary()` 渲染之停機統計報告內，固定包含 `[Server] Daemon stopped gracefully.` 標準標誌行。

> [!CAUTION]
> 調整或美化 `format_startup_banner()` 與 `format_shutdown_summary()` 的排版格式時，**必須原字保留** `[Server] Daemon successfully started!` 與 `[Server] Daemon stopped gracefully.` 兩個精確子字串，否則將直接破壞既有 CLI 整合測試斷言與自動化腳本的狀態判讀契約。

---

### [DN-05] Worker 私有 `_ipc_stdout` 管道隔離與全域 `stdout` 重導向防污染
- **背景與陷阱**：
  在 Worker 進程執行任務期間，若業務模組或第三方函式庫內部存在未受控的 `print()` 或直接寫入 `sys.stdout` 的日誌，非結構化的純文字將直接竄入 NDJSON IPC 傳輸管道，導致 Master 在 `json.loads()` 時拋出 `JSONDecodeError`，損毀任務傳輸協定。
- **工程決策**：
  1. Worker 啟動時建立獨立私有的 `_ipc_stdout` 控制代碼（直接綁定原生底層 `sys.stdout.buffer`），所有 IPC 結構化封包均透過私有代碼序列化發送。
  2. 將全域 `sys.stdout` 重導向至 `sys.stderr`（由 Master 專屬 daemon thread 排空並記入日誌檔），並於 `finally` 區塊恢復。
  3. 引入 `ipc_lock` 互斥鎖，保證多執行緒發送封包時 NDJSON 行結構不交錯。

> [!CAUTION]
> 嚴禁將 `_ipc_stdout` 替換為全域 `sys.stdout`，亦嚴禁移除 `sys.stdout = sys.stderr` 重導向與 `ipc_lock` 保護，否則業務模組的 stdout 雜訊將直接摧毀 IPC 通訊。

---

### [DN-06] Master 兩階段平滑關閉協定 (NDJSON Exit Handshake + Process Tree Harvest)
- **背景與陷阱**：
  若 Master 終止 Worker 時直接調用 OS 層級之 `kill_process_tree` 或 `SIGKILL`，Worker 託管的背景服務（如檔案監聽、快取序列化）將無機會執行 `stop()` 清理，造成 lockfile 殘留或資料損毀。
- **工程決策**：
  實作兩階段優雅停機協定：
  - **第一階段**：透過 Stdin 管道向 Worker 發送 `{"action": "exit"}\n` 應用層握手，並等待至多 1.5 秒讓 Worker 依序呼叫各背景服務之 `stop()`。
  - **第二階段**：若超時未退出或管道破裂，自動降級為 `kill_process_tree` 強制收割進程樹，並徹底關閉所有 pipe。

---

### [DN-07] Server 執行期零 `source/` 嚴格沙盒路徑隔離與動態 Provider 注入
- **背景與陷阱**：
  在開發環境中，若 Master 或 Worker 的 `sys.path` 滲入 `source/` 源碼路徑，會引發「開發源碼覆蓋已發布模組」、「熱重載失效」及「沙盒測試自欺」等嚴重視線污染與架構債。
- **工程決策**：
  1. Master 在生成 Worker 子進程時，`PYTHONPATH` 僅允許注入根目錄、`.modules` 及私有 `.venv`，嚴格剔除所有 `source/` 目錄。
  2. `ServiceManager` 載入第三方服務宣告時，動態將 `.modules/<provider>` 注入 `sys.path`，並相容 `code.class://` 前綴與連字號轉底線（優先直接匯入），確保生態系模組正確隔離載入。

---

### [DN-08] `WarmWorker.pre_warm()` 服務路徑先行載入時序與 `MasterSupervisor.stop()` 冪等防重入
- **背景與陷阱**：
  1. 在零 `source/` 隔離環境下，第三方模組（如 `.modules/knowledge-db`）是由 `ServiceManager.load_from_contributes()` 動態注入 `sys.path`。若 `WarmWorker.pre_warm()` 先廣播 `server_worker_warming` 事件才呼叫 `load_from_contributes()`，會導致 `hook.server.py` 在處理預熱事件時因 `sys.path` 尚未包含 `.modules/knowledge-db` 而拋出 `No module named 'knowledge_db'`。
  2. 當 `/api/shutdown`、Idle TTL 或 `restart_server()` 背景執行緒呼叫 `MasterSupervisor.stop()` 關閉 `_httpd` 時，主執行緒 `start(foreground=True)` 的 `finally: self.stop()` 會立即被喚醒並二次進入 `stop()`，引發重複清理與日誌歸檔競態。
- **工程決策**：
  1. **服務路徑先行注入**：`WarmWorker.pre_warm()` 必須先將 `.modules` 加入 `sys.path` 並完成 `self.service_manager.load_from_contributes(self.yscb_root)`，隨後才廣播 `server_worker_warming` 與執行 `start_all()`。
  2. **停機互斥與 `_is_stopped` 冪等守門**：`MasterSupervisor` 增設 `self._stop_lock` 與 `self._is_stopped` 旗標，確保 `stop()` 在多執行緒與 `finally` 區塊重入時嚴格具備單次執行冪等性。

> [!CAUTION]
> 嚴禁將 `events.broadcast("server_worker_warming")` 移至 `service_manager.load_from_contributes()` 之前，亦嚴禁移除 `MasterSupervisor.stop()` 的 `_stop_lock` 與 `_is_stopped` 冪等守門。

