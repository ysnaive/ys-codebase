---
title: Server 模組設計決策與工程註記
category: design_notes
module: server
updated_at: 2026-10-14
---

# Server 模組設計決策與工程註記 (DESIGN_NOTES.md)

| 決策編號 | 標題 / 主題 | 影響檔案 | 風險等級 |
| :--- | :--- | :--- | :---: |
| **[DN-01]** | 方案 C Master-Worker 雙進程模型 | `server/master.py`, `server/worker.py` | Low |
| **[DN-02]** | 500ms 防抖分流串流協議 | `server/streamer.py` | Low |
| **[DN-03]** | yscb 宿主四大耦合邊界 | `yscb.py` | Low |
| **[DN-04]** | 統一生命週期與共享 15 分鐘自毀 (TTL) | `server/master.py`, `server/service.py` | Low |
| **[DN-05]** | Server 組態管理與 Console 啟動優先級分流 | `server/config.py`, `scripts/cli.py` | Low |
| **[DN-06]** | Worker 進程級模組快取與標準預熱事件廣播 | `server/worker.py` | Low |
| **[DN-07]** | Contributes Server 宣告規範與 Background Services 狀態可觀測性 | `server/service.py`, `scripts/cli.py` | Low |
| **[DN-08]** | 雙軌模組熱重載 (Worker 重啟 vs Master 自重啟) 與路徑感知規範 | `server/watcher.py`, `server/master.py` | Low |
| **[DN-09]** | 即時 Flush 日誌架構、異常中斷自癒與歷史滾動清理機制 | `server/logger.py`, `server/master.py`, `server/worker.py` | Low |
| **[DN-10]** | 環境權限自適應探針、auto_spawn 組態與 IDE Agent 常駐導引 | `core/platform/process.py`, `core/commands/dispatcher.py`, `server/config.py` | Low |
| **[DN-11]** | Master 純控制平面解耦、Worker 服務託管與 IPC 互斥鎖定 | `server/master.py`, `server/worker.py`, `server/logger.py` | Low |
| **[DN-12]** | 啟動參數橫幅、Console 日誌實時回顯與停機總結報告可觀測性架構 | `server/master.py`, `server/logger.py`, `scripts/cli.py` | Low |

---

### [DN-01] 方案 C Master-Worker 雙進程模型
- **背景**：CLI 工具常駐化需兼顧啟動加速 (<30ms) 與模組記憶體隔離。
- **決策**：Master 進程處理 HTTP 與生命週期；Worker 子進程常駐預熱並按需延遲加載目標模組。模組崩潰由 Master 自動拉新 Worker 自癒。

### [DN-02] 500ms 防抖分流串流協議
- **背景**：避免頻繁微小 TCP 封包衝擊，兼顧終端即時互動感。
- **決策**：設置 500ms 緩衝閥值，有換行或結束時立即 flush，封包嚴格區分 `terminal_stream` 與 `task_finish`。

### [DN-03] yscb 宿主四大耦合邊界
- **背景**：防止 `yscb.py` 再次膨脹與硬依賴。
- **決策**：落實「軟依賴探測、自循環旁路、按需非同步拉起、極簡客戶端」四大原則。

### [DN-04] 統一生命週期與共享 15 分鐘自毀 (TTL)
- **背景**：業務 Service Worker（如 Watchdog）若獨立長駐會導致背景資源持續洩漏。
- **決策**：Service Worker 嚴格跟隨 Server 生命週期配置。有 TTL 則一同自毀，無 TTL 則一同常駐；手動 `stop` 時同步退出。

### [DN-05] Server 組態管理與 Console 啟動優先級分流
- **背景**：開發者通常希望 Server 在背景安靜常駐，但在除錯或特定開發環境中需要能於終端機前台觀察即時日誌與派發。
- **決策**：
  1. 引入 `ServerConfig` 資料類別對接 `core.config.get("server", "enable_console", False)`，組態預設 `enable_console: false` 走靜默脫鉤背景常駐。
  2. `server start` 實作優先級仲裁：CLI `--console` 顯式參數（強制前台除錯）> CLI `--daemon` 顯式參數（強制背景常駐）> 設定檔 `enable_console` > 預設 `False`。
  3. CLI 採用 `add_mutually_exclusive_group()` 嚴格防止 `--console` 與 `--daemon` 同時傳入衝突。

### [DN-06] Worker 進程級模組快取與標準預熱事件廣播
- **背景**：Worker 進程在每次派發任務時若重新執行 `importlib.util.module_from_spec` 與 `exec_module`，會產生無謂的直譯解析與符號重複評估開銷；且重型模組（如向量推論、倒排索引）若在首次請求才冷加載，會造成初次調用顯著卡頓。
- **決策**：
  1. 在 `Worker._module_cache` 實作模組級進程記憶體快取，首次執行後快取 `cli_module`，跨任務調用直接提取執行 `process()`。
  2. 於 Worker 初始化完成後透過微內核標準廣播原語 `core.events.broadcast("worker_warming", emit_module="server")` 發送預熱廣播，讓各領域模組（如 `knowledge-db`）自定義 Pre-warm 邏輯。

### [DN-07] Contributes Server 宣告規範與 Background Services 狀態可觀測性
- **背景**：既有 ServiceWorker 依賴硬編碼或全量掃描所有模組代碼，缺乏宣告式標準擴充介面；同時 `server status` 缺乏對背景服務運行健康狀態之可觀測性。
- **決策**：
  1. 制定 `contributes/server.json` 規範，各模組透過純宣告方式聲明 `service_worker` 類別路徑、名稱與描述。
  2. `ServiceManager` 透過 `core.contributes.get("server")` 動態發現並拉起背景服務，並持有 provider 與 description 元數據。
  3. `server status` 格式化輸出包含 Process Info、Service Counters 以及 Background Services 清冊（含狀態與模組歸屬），提升運維透明度。

### [DN-08] 雙軌模組熱重載 (Worker 重啟 vs Master 自重啟) 與路徑感知規範
- **背景**：既有 `ModulesWatcher` 監控 `.modules/` 變動時，無差別呼叫 `restart_worker`。當 `knowledge-db` 等領域模組更新時重啟 Worker 能完美刷新，但當 `server` 本體或 `core` 底層模組更新時，Master 進程記憶體中已載入的 Python 代碼無法刷新。
- **決策**：
  1. `ModulesWatcher` 比對 mtime 快照時精確解析變動檔案所屬頂層模組目錄 `affected_modules: Set[str]`，並加入 500ms 批次變更防抖。
  2. 實作雙軌重載分流：
     - 若 `affected_modules` 包含 `server` 或 `core`：調用 `MasterSupervisor.restart_server()`，透過 `core.platform.spawn_detached` 重新拉起全新 Master 進程，並安全釋放鎖、狀態與 HTTP 資源後平滑退出舊進程。
     - 若僅包含其他領域模組：僅調用 `restart_worker()` 重啟 Worker 子進程，保持 Master 進程與 HTTP 端口連線零中斷。

### [DN-09] 即時 Flush 日誌架構、異常中斷自癒與歷史滾動清理機制
- **背景**：Server 常駐進程在背景默默運行，過去輸出僅重定向至 `/dev/null` 或依賴 Console 前台，缺乏可靠的磁碟日誌；同時若遭遇強殺崩潰或斷電，未 flush 的緩衝區將完全遺失，重啟後殘留的舊日誌亦無法有序追溯。
- **決策**：
  1. 實作 `ServerLogger`，日誌固定寫入 `cache://server/log`（`.cache/server/log`），所有寫入行強制 `flush()`，保證 OS Page Cache 刷新。
  2. 首行寫入時間基準標誌 `server start at time "{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}"`。
  3. 新 Server 啟動時執行異常自癒：偵測未正常歸檔之舊 log，優先解析其首行時間戳（失敗退化 mtime）轉存歷史檔 `{timestamp}_log`，並自動滾動保留最新 5 份。
  4. Master 集中管理日誌寫入 Handle，Worker 透過 IPC stdout 串流以 `{"type": "log"}` 發送封包由 Master 攔截寫入，杜絕跨進程並發檔案鎖爭搶。

### [DN-10] 環境權限自適應探針、auto_spawn 組態與 IDE Agent 常駐導引
- **背景**：IDE Agent (如 Antigravity / Cursor / Claude Code) 在執行工具命令時，通常運行於未開啟 Breakaway 權限的 Windows Job Object 沙盒中，命令結束時整棵進程樹會被強制收割。這導致背景自動拉起的 Server 進程在單次命令結束時立即遭殺死，形成每次 CLI 呼叫重複拉起又被殺死的無效進程開銷。
- **決策**：
  1. 於 `core.platform.process` 實作 `can_spawn_background_daemon()` 探針與進程級記憶體快取，在 Windows 下透過 `IsProcessInJob` 與 1 次輕量探針偵測 Job Object Breakaway 權限。
  2. 於 `ServerConfig` 與 `config/server/config.project.json` 支援 `auto_spawn: bool = True` 配置（預設為 `true`）。
  3. 當 `auto_spawn` 為 true 但探針檢測無背景權限時，自動降級至本地極速冷派發（~86ms），並透過 `sys.stderr` 輸出具備防洗頻抑制的環境診斷提示與 IDE Agents 常駐指引（建議透過 `IsDaemon: true` / Background Task 啟動 `python yscb.py server start --console`）。

---

### [DN-11] Master 純控制平面解耦、Worker 服務託管與 IPC 互斥鎖定
- **背景**：原設計中 `MasterSupervisor` 混雜了領域背景服務（如 KnowledgeDBServiceWorker）之生命週期調度，違反微內核「Master 為純控制平面」架構界限；同時多個 HTTP 請求並發時，Worker Stdio IPC 缺乏序列化保護易發生交錯，且 Worker 大量 Stderr 輸出容易填滿作業系統 64KB Pipe Buffer 造成死鎖。
- **決策**：
  1. **職責純化與服務託管**：Master 剝離領域 Worker 初始化，僅保留通用程序調度；背景領域服務（`ServiceManager`）改由 `WarmWorker` 獨立託管與啟動，並在 `worker_ready` 封包中將服務狀態回傳 Master，供 `/api/status` 查詢。
  2. **IPC 原子鎖定與 Stderr 持續排空**：Master 引入 `_dispatch_lock` 序列化所有對 Worker stdin/stdout 的操作；啟動 Worker 時拉起專屬 Daemon 執行緒排空 `proc.stderr`，終結 Pipe 阻塞；在終止 Worker 時安全關閉所有 stdio 管道。
  3. **滾動日誌檔案後綴防呆**：`ServerLogger` 擴充 `HIST_REGEX` 支援 `_01` 等序號後綴，確保異常重啟產生的歷史檔案能正確納入滾動清理。

---

### [DN-12] 啟動參數橫幅、Console 日誌實時回顯與停機總結報告可觀測性架構
- **背景**：原 `server start` 於背景脫鉤啟動後終端僅有一行冷淡文字，缺乏啟動參數（PID、Port、TTL、監聽目錄、背景服務清冊、即時日誌路徑）之全局可觀測性；`--console` 前台模式缺乏實時日誌終端回顯；`server stop` 關閉時缺乏本次運行的統計總結（Uptime、累計處理任務數、服務終止數與歸檔日誌路徑）。
- **決策**：
  1. **結構化 ASCII 啟動橫幅**：實作 `format_startup_banner()`，於背景啟動脫鉤前及前台模式統一打印對齊的 ASCII 橫幅（嚴格包含 `[Server] Daemon successfully started!` 保持測試相容）；當已在運行中再次呼叫 `server start` 時，輸出提示並附帶運行現況橫幅。
  2. **Console 實時日誌回顯**：`ServerLogger` 支援 `echo_console: bool = False` 參數；當以 `--console` 前台啟動時，日誌除強制寫入 `.cache/server/log` 外，同步 Tee 輸出至 `sys.stdout`，實現即時串流觀測。
  3. **停機總結報告**：`MasterSupervisor` 於啟動時記錄 `self._start_time`，並於 `/api/status` 與 `/api/shutdown` API Payload 注入 `uptime_seconds` 與 `tasks_executed` 統計；`format_shutdown_summary()` 格式化停機報告（嚴格包含 `[Server] Daemon stopped gracefully.` 保持測試相容），清晰回饋運行時長、任務數與日誌歸檔實體路徑。

> [!CAUTION]
> `format_startup_banner()` 輸出字串必須保留 `[Server] Daemon successfully started!`，且 `format_shutdown_summary()` 必須保留 `[Server] Daemon stopped gracefully.` 子字串，否則將破壞既有 CLI 契約測試與自動化腳本的啟動/停機狀態判讀。



