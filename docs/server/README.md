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
