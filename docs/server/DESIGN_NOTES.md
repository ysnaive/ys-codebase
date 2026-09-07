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

