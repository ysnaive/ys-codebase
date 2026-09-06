# API 與介面規格書 (API & Interface Specification)

> 功能名稱：server_module_daemon_supervisor  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `spawn_detached` | `source/core/core/platform/process.py` | Public | 跨平台背景脫鉤拉起進程 (POSIX setsid / Win detached) |
| `is_process_alive` | `source/core/core/platform/process.py` | Public | 跨平台探測 PID 是否存活 |
| `kill_process_tree` | `source/core/core/platform/process.py` | Public | 跨平台強殺指定進程及其所有子進程 |
| `InterProcessLock` | `source/core/core/platform/lock.py` | Public | 跨平台跨進程檔案排他鎖 (flock / msvcrt) |
| `process(args)` | `source/server/scripts/cli.py` | Public | Server CLI 進入點，首行守門校驗，子指令分流 |
| `MasterSupervisor` | `source/server/master.py` | Public | 管理 Master 守護進程、HTTP 服務、15 分鐘 TTL、Worker 與 Service Worker 生命週期 |
| `WarmWorker` | `source/server/worker.py` | Public | 常駐預熱子進程，發布預熱 Event，按需延遲加載業務模組，攔截 SystemExit |
| `BaseServiceWorker` | `source/server/service.py` | Public | 業務長常駐服務抽象基底（共享 Server 15 分鐘 TTL，不獨立長駐） |
| `DebouncedIOStreamer` | `source/server/streamer.py` | Public | `sys.stdout`/`sys.stderr` 攔截器，500ms 防抖緩衝封包協議 |
| `ModulesWatcher` | `source/server/watcher.py` | Public | 監控 `.modules/` 變動並通知 Master 重啟 Worker |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 Core Platform 底層原語契約 (`core.platform`)

```python
from typing import List, Optional, Dict

def spawn_detached(cmd: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> int:
    """以非同步脫鉤方式在背景啟動獨立進程，父進程退出不影響子進程。回傳子進程 PID。"""
    ...

def is_process_alive(pid: int) -> bool:
    """跨平台探測指定 PID 之進程是否存在且存活。"""
    ...

def kill_process_tree(pid: int, timeout_sec: float = 3.0) -> bool:
    """跨平台強制收割指定 PID 及其衍生之整個進程樹。"""
    ...

class InterProcessLock:
    """跨平台跨進程檔案排他鎖 (POSIX fcntl.flock / Windows msvcrt.locking)"""
    def __init__(self, lock_file: str) -> None: ...
    def acquire(self, blocking: bool = False) -> bool: ...
    def release(self) -> None: ...
    def __enter__(self) -> "InterProcessLock": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...
```

---

### 2.2 預熱生命週期事件規格 (`core.events`)

1. **`server:worker:warming`**：
   - 時機：Worker 子進程拉起，開始初始化環境與微內核。
   - Payload: `{"worker_pid": int, "start_time": float}`
2. **`server:worker:ready`**：
   - 時機：Worker 子進程預熱完成，正式就緒可受理任務。
   - Payload: `{"worker_pid": int, "duration_ms": float}`

---

### 2.3 業務 Service Worker 抽象基底 (`source/server/service.py`)

```python
from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseServiceWorker(ABC):
    """
    業務背景常駐服務抽象基底（例：Watchdog 檔案監聽）。
    生命週期嚴格跟隨 Server 主進程共享 15 分鐘空閒自毀 (Idle TTL)，不獨立永久長駐。
    """
    @property
    @abstractmethod
    def name(self) -> str:
        """服務唯一識別名 (例: 'knowledge-db-watcher')"""
        ...

    @abstractmethod
    def start(self, context: Dict[str, Any]) -> None:
        """啟動背景監聽工作"""
        ...

    @abstractmethod
    def stop(self) -> None:
        """優雅關閉釋放資源"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """健康檢查探針"""
        ...
```

---

### 2.4 HTTP 路由與封包協議契約 (Master 127.0.0.1:0)

所有 HTTP 呼叫均需帶 Header：`Authorization: Bearer <token>`。

#### 1. `POST /api/dispatch` (核心任務熱派發)
- **Request Body (JSON)**:
  ```json
  {
    "module": "dev",
    "args": ["test"],
    "cwd": "/workspace/ys-codebase",
    "env": {"DEBUG": "1"},
    "yscb_root": "/workspace/ys-codebase"
  }
  ```
- **Response**: HTTP 200 `Transfer-Encoding: chunked` (NDJSON 封包串流)
  - 終端串流區塊 (每 500ms 防抖或有輸出時發送)：
    ```json
    {"type": "terminal_stream", "stream": "stdout", "text": "[*] Running sandbox tests...\n"}
    ```
  - 任務完成封包 (執行結束發送)：
    ```json
    {"type": "task_finish", "exit_code": 0, "duration_ms": 24.5, "error": null}
    ```

#### 2. `GET /api/status` (健康診斷與統計)
- **Response (JSON)**:
  ```json
  {
    "status": "running",
    "state": "ready",
    "pid": 23456,
    "worker_pid": 23457,
    "port": 54321,
    "root": "/workspace/ys-codebase",
    "tasks_executed": 42,
    "idle_seconds_left": 840.5,
    "services": [{"name": "knowledge-db-watcher", "alive": true}]
  }
  ```

#### 3. `POST /api/reload` (手動熱重載 Worker)
- **Response (JSON)**:
  ```json
  {"status": "worker_restarted", "new_worker_pid": 23460}
  ```

#### 4. `POST /api/shutdown` (優雅關閉進程)
- **Response (JSON)**:
  ```json
  {"status": "shutting_down"}
  ```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: ──> core.platform (process.py, lock.py 及 test_platform.py 先行就位)
              │
Step 2: ──────┼──> streamer.py (DebouncedIOStreamer: 500ms 防抖與 NDJSON 封包)
              │
Step 3: ──────┼──> service.py (BaseServiceWorker 擴充基底介面)
              │
Step 4: ──────┼──> worker.py (WarmWorker: 預熱 Event、延遲加載、SystemExit 攔截)
              │
Step 5: ──────┼──> watcher.py (ModulesWatcher: .modules/ 變更感知)
              │
Step 6: ──────┼──> master.py (MasterSupervisor: 127.0.0.1:0、Token、15m TTL、Service 託管)
              │
Step 7: ──────┼──> scripts/cli.py (Server CLI 入口: start/stop/status/reload)
              │
Step 8: ──────┼──> yscb.py (宿主改裝: 軟依賴探測、自循環旁路、按需非同步拉起、極簡客戶端)
              │
Step 9: ──────┴──> tests/test_server.py (完整 Master-Worker、預熱 Event、防抖串流與沙盒測試)
```
