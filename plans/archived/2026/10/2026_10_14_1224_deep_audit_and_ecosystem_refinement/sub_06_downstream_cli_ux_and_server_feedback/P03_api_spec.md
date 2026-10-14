# Phase 3: API 與介面契約規格書 (P03 API Spec)

> 功能名稱：sub_06_downstream_cli_ux_and_server_feedback  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 介面契約與資料結構 (Interface Contracts & Data Structures)

### 1.1 `GET /api/status` Payload
回傳物件擴充欄位：
```json
{
  "status": "running",
  "state": "ready",
  "pid": 12345,
  "worker_pid": 12346,
  "port": 54321,
  "root": "/path/to/yscb",
  "start_time": 1728912345.67,
  "uptime_seconds": 45.2,
  "tasks_executed": 3,
  "idle_seconds_left": 854.8,
  "log_file": "/path/to/yscb/.cache/server/log",
  "services": [...],
  "watcher": {...}
}
```

### 1.2 `POST /api/shutdown` Payload
回傳物件擴充欄位：
```json
{
  "status": "shutting_down",
  "summary": {
    "pid": 12345,
    "worker_pid": 12346,
    "uptime_seconds": 123.4,
    "tasks_executed": 5,
    "services_stopped": 1,
    "reason": "Graceful CLI shutdown request",
    "archive_log": "/path/to/yscb/.cache/server/2026_10_14_14.18.00_log"
  }
}
```

---

## 2. 核心 API 簽名與詳細規格 (API Signatures)

### 2.1 啟動橫幅輸出簽名
`def format_startup_banner(info: Dict[str, Any]) -> str`
輸出格式：
```text
======================================================================
  __   __ ____   ____     ____                               
  \ \ / // ___| / ___|   / ___|  ___ _ ____   _____ _ __     
   \ V / \___ \| |   ____\___ \ / _ \ '__\ \ / / _ \ '__|    
    | |   ___) | |__|_____|__) |  __/ |   \ V /  __/ |       
    |_|  |____/ \____|   |____/ \___|_|    \_/ \___|_|       
======================================================================
[Server] Daemon successfully started!
  ├── Master PID      : 12345
  ├── Worker PID      : 12346 (State: READY)
  ├── Listening Port  : 54321 (http://127.0.0.1:54321)
  ├── Workspace Root  : /workspace/ys-codebase
  ├── Idle Timeout    : 900.0s (Auto-shutdown when idle)
  ├── Modules Watcher : ACTIVE (Monitoring .modules/)
  ├── Background Svcs : 1 registered (search-sync)
  └── Real-time Log   : /workspace/ys-codebase/.cache/server/log
======================================================================
```

### 2.2 停機總結輸出簽名
`def format_shutdown_summary(summary: Dict[str, Any]) -> str`
輸出格式：
```text
======================================================================
YS-Codebase Server Shutdown Summary
======================================================================
[Server] Daemon stopped gracefully.
  ├── Total Uptime    : 2m 15s (135.2s)
  ├── Tasks Handled   : 8 tasks executed
  ├── Services Stopped: 1 background services terminated
  ├── Shutdown Reason : Graceful CLI shutdown request
  └── Archived Log    : /workspace/ys-codebase/.cache/server/2026_10_14_14.18.00_log
======================================================================
```

---

## 3. 依賴拓撲與實作順序 (Dependency Topology)

1. `logger.py`（預期歸檔路徑與 echo 控制）
2. `master.py`（啟動時間戳、status/shutdown API 擴充與格式化純函式）
3. `cli.py`（終端呼叫與呈現整合）

