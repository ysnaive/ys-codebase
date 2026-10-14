# YS-Codebase Server 常駐服務端模組 (Daemon & Service Runtime)

> 模組名稱：`server`  
> 職責定位：高效能常駐服務調度、Master/Worker IPC 通訊、背景服務託管 (`ServiceManager`)、檔案熱重載守護與全專案 Console 可觀測性。

---

## 1. 模組架構全景 (Architecture Overview)

`server` 模組採用嚴格的「Master 控制平面 + WarmWorker 資料平面」雙進程隔離模型：

```mermaid
graph TD
    classDef master fill:#1e3a8a,stroke:#3b82f6,stroke-width:2px,color:#fff;
    classDef worker fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#fff;
    classDef svc fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fff;

    subgraph MasterProcess ["Master 進程 (純控制平面 Control Plane)"]
        MasterCore["Master 控制核心<br/><code>server.master.MasterSupervisor</code>"]:::master
        IPCServer["IPC 路由伺服器<br/><i>動態 Port 綁定 / _dispatch_lock 序列化</i>"]:::master
        LogEngine["日誌引擎 (ServerLogger)<br/><i>Console 即時回顯 / 5 代歷史滾動</i>"]:::master
        Watcher["檔案變更監視器 (ModulesWatcher)<br/><i>.modules/ 雙軌變更自癒</i>"]:::master
    end

    subgraph WorkerProcess ["WarmWorker 進程 (資料執行平面 Data Plane)"]
        WorkerCore["Worker 核心<br/><code>server.worker.WarmWorker</code>"]:::worker
        ServiceMgr["服務管理器 (ServiceManager)<br/><i>託管 contributes/server.json 宣告之服務</i>"]:::worker
        Services["背景服務群<br/><code>KnowledgeDBServiceWorker</code> 等"]:::svc
    end

    MasterCore --> IPCServer
    MasterCore --> LogEngine
    MasterCore --> Watcher
    IPCServer -- "HTTP / NDJSON IPC" --> WorkerCore
    WorkerCore --> ServiceMgr
    ServiceMgr --> Services
```

---

## 2. 核心機制說明 (Core Mechanisms)

### 2.1 控制平面與執行平面分離 (Master vs Worker)
- **Master 進程**：純控制平面，負責啟動參數解析、進程樹維護、`_dispatch_lock` 序列化 IPC、Worker `stderr` 持續排空與檔案變更重啟分流。Master 本身絕不直接執行重型業務任務或加載重量級領域函式庫。
- **WarmWorker 子進程**：預熱執行環境，持有 `ServiceManager` 實例，負責實際執行由各模組註冊的長駐背景服務，並支援極速記憶體內熱派發。

### 2.2 背景服務託管架構 (ServiceManager)
各模組透過在自身 `contributes/server.json`（或 `contribute.json`）中宣告 `services` 節點，由 `WarmWorker` 自動發現並託管生命週期：
```json
{
  "services": [
    {
      "id": "knowledge-db-worker",
      "entry": "code.class://knowledge-db/service:KnowledgeDBServiceWorker",
      "description": "Knowledge-DB Background File Watcher & Incremental Patcher"
    }
  ]
}
```
Worker 在啟動時依序初始化各 ServiceWorker，並透過 `worker_ready` 封包將服務清單與狀態回傳 Master 供 `server start` 橫幅與 `server status` 呈現。

### 2.3 檔案監視與自癒重載 (ModulesWatcher)
- 監視 `project://.modules/` 運行空間變更。
- **領域模組變更**（如 `knowledge-db`）：觸發 Worker 子進程優雅重啟，sub-500ms 完成刷新。
- **核心模組變更**（如 `core`、`server`）：觸發 Master 自重啟整棵進程樹。

### 2.4 全週期可觀測性與終端反饋
- **結構化啟動橫幅 (`format_startup_banner`)**：`server start`（含背景脫鉤與 `--console`）統一輸出對齊的 ASCII 橫幅，完整顯示運行模式、Master/Worker PID、Port、Idle TTL、Modules Watcher 狀態、託管服務與即時日誌路徑。
- **停機運行總結 (`format_shutdown_summary`)**：`server stop` 優雅關閉時輸出本次運行總時長 (Uptime)、累計執行任務數 (Tasks Handled)、終止服務數與歸檔日誌路徑。

---

## 3. CLI 指令參考 (CLI Commands)

| 指令 | 核心參數 / 選項 | 說明 |
| :--- | :--- | :--- |
| `python yscb.py server start` | `[--daemon]` `[--console]` `[--ttl <sec>]` | 啟動 Master 伺服器進程樹並輸出啟動參數橫幅 |
| `python yscb.py server stop` | `[--force]` | 優雅停止常駐伺服器進程樹並輸出運行總結報告 |
| `python yscb.py server reload` | 無 | 重新加載 Worker 子進程與各背景服務 |
| `python yscb.py server status` | 無 | 查詢進程狀態、Uptime、Idle TTL、Port 與服務清冊 |

---

## 4. 相關技術文件

- [Server 模組總覽手冊 (`docs/server/README.md`)](../../../docs/server/README.md)
- [Server 設計決策與工程手冊 (`docs/server/DESIGN_NOTES.md`)](../../../docs/server/DESIGN_NOTES.md)
