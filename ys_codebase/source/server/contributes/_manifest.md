# Server 模組貢獻導覽清冊 (Contributes Manifest)

> 本清冊記錄 `server` 模組對外貢獻之擴充能力與協議。

## 1. 外部注入清冊 (Egress Contributions)

### 1.1 `core.json`（微內核指令擴充）
- **CLI 指令樹**：
  - `server start`: 啟動背景常駐服務（支援 `--daemon`, `--console`）。
  - `server stop`: 優雅關閉背景服務進程。
  - `server status`: 檢視 Master/Worker PID、Port 與 Idle TTL 倒數。
  - `server reload`: 重載 Warm Worker 子進程與模組快取。

## 2. 開放擴充點清冊 (Ingress Points)
- `services`: 允許領域模組註冊背景常駐 Worker（例 `knowledge-db-watcher`）。
