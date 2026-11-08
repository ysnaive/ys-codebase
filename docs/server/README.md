---
target: "Server"
doc_type: "readme"
status: "active"
source_paths:
  - "yscb://source/server/server/master.py"
  - "yscb://source/server/server/worker.py"
  - "yscb://source/server/server/service.py"
  - "yscb://source/server/server/space_watcher.py"
  - "yscb://source/server/server/config.py"
  - "yscb://source/server/scripts/cli.py"
  - "yscb://source/server/contributes/core.json"
  - "yscb://source/core/core/commands/dispatcher.py"
related_docs:
  - "./daemon_architecture.md"
  - "./hot_reload_and_services.md"
  - "./realtime_logging.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-11-08"
---

# Server 常駐服務與守護中樞模組 (Server Module)

> 模組名稱：`server`  
> 當前版本：`v1.0.0` (規劃發布)  
> 職責定位：Layer 1 平台通用服務模組，特化與 `yscb.py` 宿主深度協同之持久化加速與 Worker 守護中樞。

---

## 1. 核心特性 (Features)

1. **瞬發加速 (<30ms)**：常駐預熱 Python 運行期與微內核環境，消除冷啟動載入直譯器與 AST 索引之 1~2 秒開銷。
2. **三平面常駐架構 (Master Supervisor / Warm Worker / Managed Service Workers)**：
   - **Master Supervisor (控制平面)**：管理 Localhost HTTP 服務 (`127.0.0.1:0`)、安全 Token 認證、PID 鎖、`_dispatch_lock` 序列化 IPC 與兩階段優雅停機（NDJSON Exit 握手與進程樹收割）；運行狀態封裝為不可變快照 `ServerDaemonState` (`@dataclass(frozen=True)`)。
   - **Warm Worker (前台執行平面)**：常駐預熱資料平面，透過獨立私有 `_ipc_stdout` 管道傳輸 IPC 封包；以 `_task_lock` 與 `core.context.bind_runtime_context(virtual_cwd=..., env_overrides=...)` 進行無全域突變的虛擬環境與工作目錄綁定（零 `os.chdir`、零 `os.environ` 污染），攔截 `SystemExit` 保證進程不死，並透過 `core.log.DebouncedIOStreamer` 將標準串流與 `core.log` 結構化日誌路由至 IPC 管道。
   - **Managed Service Workers (受管背景服務平面)**：透過 `ServiceManager` 統一託管各模組於 `contributes/server.json` 宣告之背景服務（`core-space-watcher`、`knowledge-db-worker`、`gdrive-sync`）。所有背景服務繼承 `BaseServiceWorker`，採用受管執行緒生命週期（`start_managed_thread` / `stop_managed_thread`）、五態狀態機（`STARTING`, `UPDATING`, `READY`, `DEGRADED_OFFLINE`, `STOPPED`）與 `bind_log_context(background_sink=..., component=..., isolated_error_scope=True)` 獨立背景日誌隔離，杜絕野生執行緒 (`threading.Thread`) 污染前台 CLI stdout/stderr。
3. **500ms 防抖分流串流協議 (`core.log.DebouncedIOStreamer`)**：攔截模組 `sys.stdout`/`sys.stderr` 並接入 `core.log` 前台日誌管線，以 500ms 防抖緩衝發送 `terminal_stream`、`log` 與 `task_finish` NDJSON 封包。
4. **按需延遲加載與進程級模組快取 (Lazy Load & Module Cache)**：Worker 啟動時不預載入業務命令腳本，首次派發後快取於 `core.commands.dispatcher._MODULE_CACHE`，並透過 `server_worker_warming` 事件廣播觸發重型模組預熱。
5. **雙軌模組熱重載 (Hot Reload)**：自動監控 `.modules/` 變動並精確解析模組歸屬；領域模組變動直接重啟全新 Worker，`server`/`core` 模組變動自動優雅重啟整個 Server (Master + Worker)，100% 杜絕 Python reload 幽靈 Bug 與記憶體殘留。
6. **統一生命週期自毀 (15m Idle TTL) 與演算法化 Worker 記憶體健康守護 (`WorkerMemoryHealthMonitor`)**：支援配置空閒自毀，無操作 15 分鐘後 Master 與所有 Service Worker 一同優雅關閉；同時由 `WorkerMemoryHealthMonitor` 動態校正預熱後工作集基準線（$B_{\text{base}}$），並於前台與所有背景 `ServiceWorker` 完全閒置時透過相對膨脹倍率、連續單調棘輪漂移與宿主 `MemAvailable` 水位演算法偵測異常記憶體滯留，自動觸發無縫 `restart_worker()` 回收。
7. **全週期 Console 可觀測性反饋**：
   - **啟動參數橫幅 (`format_startup_banner`)**：`server start`（含背景脫鉤與 `--console` 前台模式）即時回饋結構化 ASCII 橫幅，展示運行模式、Master/Worker PID、IPC Port、Idle TTL、Modules Watcher 狀態、託管背景服務清冊與即時日誌路徑；**當已在運行中再次呼叫 `server start` 時，亦自動輸出提示並附帶當前運行現況橫幅**。
   - **Console 實時日誌回顯**：`--console` 模式下除強制寫入 `.cache/server/log` 外，同步 Tee 輸出至 `sys.stdout`。
   - **停機總結報告 (`format_shutdown_summary`)**：`server stop` 關閉時回饋運行總時長 (Uptime)、累計執行任務數 (Tasks Handled)、終止服務數與歷史歸檔日誌路徑。

---

## 2. CLI 指令指南與啟動模式優先級 (Commands & Mode Arbitration)

```bash
# 啟動 Server 守護進程 (預設背景脫鉤模式，輸出結構化啟動參數橫幅；若已在運行則輸出當前運行現況橫幅)
python yscb.py server start [--daemon] [--ttl 900]

# 前台控制台模式啟動 (輸出啟動橫幅並即時回顯日誌至 stdout)
python yscb.py server start --console

# 檢視 Server 狀態 (WARMING/READY/RESTARTING)、Current Task、Master/Worker PID、Port、Uptime、Idle TTL 倒數與服務狀態
python yscb.py server status

# 手動熱重載 Worker 子進程 (刷新代碼記憶體與背景服務)
python yscb.py server reload

# 優雅停止 Server 守護進程並輸出本次運行總結報告 (支援強殺兜底 --force)
python yscb.py server stop [--force]
```

### 2.1 `server start` 啟動模式優先級仲裁與互斥約束
- **互斥參數組 (`add_mutually_exclusive_group`)**：CLI 嚴格禁止 `--console` 與 `--daemon` 同時傳入，避免啟動意圖衝突。
- **啟動模式優先級分流**：
  $$\text{CLI }\texttt{--console}\text{ (強制前台除錯)} \;\succ\; \text{CLI }\texttt{--daemon}\text{ (強制背景常駐)} \;\succ\; \text{組態 }\texttt{enable\_console}\text{ (`ServerConfig`)} \;\succ\; \text{預設 }\texttt{False}\text{ (靜默脫鉤背景常駐)}$$

### 2.2 指令行為合約 (Exit Codes \& Side Effects)

| 指令 | 行為與 Exit Code |
| :--- | :--- |
| `server start -d` | 輪詢 readiness 成功 → `0`；逾時但 spawn 之 PID 仍存活 → 印「still starting up」並回傳 `0`；逾時且 PID 已死 → 印錯誤（指向 `.cache/server/log`）並回傳 `1` |
| `server status` | 一律於本地冷執行（`contributes/core.json` 中 `server_compatible=false`），不經 Worker 佇列，故 Worker 忙碌或卡住時仍可即時回報；`State` 為 `WARMING (pre-warming Ns)` / `READY` / `RESTARTING`，`Current Task` 顯示進行中指令與已執行秒數（無則 `Idle`） |
| `server reload` | 搶占式：不等待進行中任務，直接終止現役 Worker（被搶占之任務回傳 `1`，`error="Worker terminated by restart/stop"`）後再 spawn 新 Worker |
| `server stop [--force]` | 優雅停止，逾時或 `--force` 時強殺進程樹；兩種路徑皆寫入 clean-exit 標記（見 [daemon_architecture.md](./daemon_architecture.md) §5）。僅刪除 `daemon.json`，**`daemon.lock` 永久保留**（見 DN-10） |

---

## 3. 即時 Flush 日誌與歷史滾動自癒 (Real-time Logging)

Server 模組內建高可靠的集中式即時 flush 日誌機制：
- **運行中即時日誌**：`cache://server/log`（實體路徑為 `.cache/server/log`），所有寫入即時 `flush()`，斷電崩潰零丟失。
- **歷史運行檔案**：`{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}_log`（支援 `_01` 同秒序號後綴），每次優雅關閉或異常重啟時自動歸檔，嚴格滾動保留最新 5 份。
- **異常中斷自癒**：新 Server 啟動若發現未正常歸檔之舊日誌，優先解析首行 `server start at time "..."` 時間戳轉存歷史並執行滾動，再行開啟新日誌。
- **詳盡規格手冊**：參見 [realtime_logging.md](./realtime_logging.md)。

---

## 4. 組態管理與 IDE Agents 使用指南 (Configuration & Agents Guide)

### 4.1 組態設定 (`config://server/config.project.json`)

```json
{
  "enable": true,
  "enable_console": false,
  "idle_timeout_sec": 900.0,
  "auto_spawn": true,
  "strict_hot_dispatch": false,
  "worker_alive_timeout_sec": 5.0
}
```

- `enable`: 是否啟用 server 模組能力（預設 `true`）。
- `enable_console`: `ServerConfig` 預設啟動模式（對接 `core.config.get("server", "enable_console", False)`，預設 `false` 走背景脫鉤常駐；設為 `true` 時無參數 `server start` 預設走前台 Console 模式，仍可被 `--daemon` 覆寫）。
- `auto_spawn`: 是否在執行非 server 指令時於背景自動喚醒常駐進程（預設 `true`）。若手動關閉 (`false`)，系統將保持純冷派發。
- `idle_timeout_sec`: 空閒超時自毀時間（秒，預設 `900.0`）。
- `strict_hot_dispatch`: 嚴格熱派發（預設 `false`）。為 `true` 且 `enable=true` 時，`server_compatible=true` 之指令熱派發失敗不再冷派發兜底，而是（可常駐且 `auto_spawn=true` 時）auto-spawn、等待 daemon 活躍 ≤ 10s 後重試一次，仍失敗則印 strict `[BLOCKER]` 並回傳 `1`。`server_compatible=false` 指令不受影響；重試規則見 [daemon_architecture.md](./daemon_architecture.md) §6。
- `worker_alive_timeout_sec`: Worker 啟動後送出 `worker_alive` 的等待上限（秒，預設 `5.0`，非正數或非法值回退預設）。僅約束「進程存活」階段，pre-warm 預熱階段不設上限。

### 4.2 IDE Agent 沙盒環境最佳實踐

在 IDE Agent（如 Antigravity / Cursor / Claude Code）環境下，因 Windows Job Object 沙盒未開啟 Breakaway 權限，單次 CLI 命令結束時背景進程會被 OS 連帶收割。
系統內建自適應環境探針（Windows Job 探針；POSIX 依實證回收偵測），自動輸出 `[BLOCKER]` 診斷與處置提示；非嚴格模式下僅提示、照常冷派發且不改變 exit code。可用環境變數 `YSCB_FORCE_DAEMON=1`（強制視為可常駐）或 `YSCB_NO_DAEMON=1`（強制不常駐）覆寫判定，詳見 [daemon_architecture.md](./daemon_architecture.md) §4–§5。

若 IDE Agent 希望享受 Hot-IPC（<10ms）極速派發：
- **推薦做法**：透過 IDE 背景常駐任務機制（例如 Antigravity `run_command(IsDaemon: true)` 或 VS Code Task），在會話啟動時執行：
  ```bash
  python yscb.py server start --console
  ```
- 如此 Server 即成為長效常駐服務，後續所有 CLI 調用均會自動透過 `_try_hot_dispatch` 享受 Hot-IPC 加速。

---

## 5. 相關架構專題手冊 (Architecture Topics)

- [常駐架構與通訊協定專題](./daemon_architecture.md)：Master-Worker 雙進程模型、`dispatcher._MODULE_CACHE` 預熱廣播、500ms 防抖串流協議與宿主四大耦合邊界。
- [熱重載與背景服務託管專題](./hot_reload_and_services.md)：常駐中樞、Warm Worker 資料平面、`ServiceManager` 宣告式掛載與雙軌自動熱重載協調機制。
- [即時 Flush 日誌與歷史滾動架構](./realtime_logging.md)：`ServerLogger` 規格、`echo_console` 雙向回顯與異常自癒細節。
- [Server 設計決策與工程手冊](./DESIGN_NOTES.md)：核心工程妥協與防坑邊界紀錄。
