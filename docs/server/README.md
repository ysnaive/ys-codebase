# Server 常駐服務與守護中樞模組 (Server Module)

> 模組名稱：`server`  
> 當前版本：`v1.0.0` (規劃發布)  
> 職責定位：Layer 1 平台通用服務模組，特化與 `yscb.py` 宿主深度協同之持久化加速與 Worker 守護中樞。

---

## 1. 核心特性 (Features)

1. **瞬發加速 (<30ms)**：常駐預熱 Python 運行期與微內核環境，消除冷啟動載入直譯器與 AST 索引之 1~2 秒開銷。
2. **Master-Worker 雙進程架構 (方案 C)**：
   - **Master Supervisor**：管理 Localhost HTTP 服務 (`127.0.0.1:0`)、安全 Token 認證、PID 鎖與 Worker 生命週期。
   - **Warm Worker**：常駐預熱子進程，單隊列序列化執行業務模組，攔截 `SystemExit` 保證進程不死。
3. **500ms 防抖分流串流協議**：攔截模組 `sys.stdout`/`sys.stderr`，以 500ms 防抖緩衝發送 `terminal_stream` 與 `task_finish` NDJSON 封包。
4. **按需延遲加載 (Lazy Load on Dispatch)**：Worker 啟動時不預載入任何業務模組；派發 A 模組絕不加載 B 模組，杜絕依賴交叉污染。
5. **雙軌模組熱重載 (Hot Reload)**：自動監控 `.modules/` 變動並精確解析模組歸屬；領域模組變動直接重啟全新 Worker，`server`/`core` 模組變動自動優雅重啟整個 Server (Master + Worker)，100% 杜絕 Python reload 幽靈 Bug 與記憶體殘留。
6. **統一生命週期自毀 (15m Idle TTL)**：支援配置空閒自毀，無操作 15 分鐘後 Master 與所有 Service Worker 一同優雅關閉，零資源浪費。

---

## 2. CLI 指令指南 (Commands)

```bash
# 啟動 Server 守護進程 (預設背景脫鉤模式)
python yscb.py server start [--daemon] [--ttl 900]

# 前台控制台模式啟動 (除錯與測試)
python yscb.py server start --console

# 檢視 Server Master、Worker PID、Port 與 Idle TTL 倒數
python yscb.py server status

# 手動熱重載 Worker 子進程 (刷新代碼記憶體)
python yscb.py server reload

# 優雅停止 Server 守護進程 (支援強殺兜底 --force)
python yscb.py server stop [--force]
```

---

## 3. 即時 Flush 日誌與歷史滾動自癒 (Real-time Logging)

Server 模組內建高可靠的集中式即時 flush 日誌機制：
- **運行中即時日誌**：`cache://server/log`（實體路徑為 `.cache/server/log`），所有寫入即時 `flush()`，斷電崩潰零丟失。
- **歷史運行檔案**：`{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}_log`，每次優雅關閉或異常重啟時自動歸檔，嚴格滾動保留最新 5 份。
- **異常中斷自癒**：新 Server 啟動若發現未正常歸檔之舊日誌，優先解析首行 `server start at time "..."` 時間戳轉存歷史並執行滾動，再行開啟新日誌。
- **詳盡規格手冊**：參見 [realtime_logging.md](realtime_logging.md)。

---

## 4. 組態管理與 IDE Agents 使用指南 (Configuration & Agents Guide)

### 4.1 組態設定 (`config://server/config.project.json`)

```json
{
  "enable": true,
  "enable_console": false,
  "idle_timeout_sec": 900.0,
  "auto_spawn": true
}
```

- `enable`: 是否啟用 server 模組能力（預設 `true`）。
- `auto_spawn`: 是否在執行非 server 指令時於背景自動喚醒常駐進程（預設 `true`）。若手動關閉 (`false`)，系統將保持純冷派發。
- `idle_timeout_sec`: 空閒超時自毀時間（秒，預設 `900.0`）。

### 4.2 IDE Agent 沙盒環境最佳實踐

在 IDE Agent（如 Antigravity / Cursor / Claude Code）環境下，因 Windows Job Object 沙盒未開啟 Breakaway 權限，單次 CLI 命令結束時背景進程會被 OS 連帶收割。
系統內建自適應環境探針，自動降級為本地極速冷派發（~86ms）並輸出引導提示。

若 IDE Agent 希望享受 Hot-IPC（<10ms）極速派發：
- **推薦做法**：透過 IDE 背景常駐任務機制（例如 Antigravity `run_command(IsDaemon: true)` 或 VS Code Task），在會話啟動時執行：
  ```bash
  python yscb.py server start --console
  ```
- 如此 Server 即成為長效常駐服務，後續所有 CLI 調用均會自動透過 `_try_hot_dispatch` 享受 Hot-IPC 加速。

