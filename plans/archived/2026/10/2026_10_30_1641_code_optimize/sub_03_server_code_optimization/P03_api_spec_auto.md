# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_03_server_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ServerConfig.load` | `ys_codebase/source/server/server/config.py` | Public | 載入 Server 組態並執行型別防禦轉型（移除殭屍參數 `workspace_root`） |
| `ServerLogger` | `ys_codebase/source/server/server/logger.py` | Public | 伺服器即時日誌寫入、Console 鏡像、滾動保留與崩潰歸檔恢復 |
| `_extract_log_file_timestamp` | `ys_codebase/source/server/server/logger.py` | Internal | 自日誌首行橫幅或檔案 `mtime` 推導時間戳字串之純函式 |
| `_safe_replace_file` | `ys_codebase/source/server/server/logger.py` | Internal | 跨平台安全搬移/覆寫日誌歸檔之純函式 |
| `MasterSupervisor` | `ys_codebase/source/server/server/master.py` | Public | 伺服器守護進程生命週期、Worker 池與 HTTP 任務派發管理 |
| `read_daemon_state` | `ys_codebase/source/server/server/master.py` | Public | 讀取並反序列化 `.cache/server/daemon.json` 之單一正統純函式 |
| `spawn_detached_master` | `ys_codebase/source/server/server/master.py` | Public | 組裝跨平台命令並在背景分離啟動 `MasterSupervisor` 之純函式 |
| `build_fallback_status_payload` | `ys_codebase/source/server/server/master.py` | Public | 當 HTTP 狀態探針暫不可用時由 `ServerDaemonState` 建構退避狀態字典 |
| `format_uptime` / `format_watcher_status` | `ys_codebase/source/server/server/master.py` | Public | 格式化運行時間與 `ModulesWatcher` 狀態顯示字串 |
| `WarmWorker` / `worker_main` | `ys_codebase/source/server/server/worker.py` | Public | 常駐預熱 Worker 任務派發器與 IPC 主迴圈入口 |
| `ServiceManager` | `ys_codebase/source/server/server/service.py` | Public | 背景常駐服務註冊、動態載入與對稱啟停管理（移除殭屍參數 `timeout_sec`） |
| `ModulesWatcher` | `ys_codebase/source/server/server/watcher.py` | Public | `.modules/` 目錄快照輪詢與變更通知器 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# ys_codebase/source/server/server/config.py
class ServerConfig:
    @classmethod
    def load(cls, override_dict: Optional[Dict[str, Any]] = None) -> "ServerConfig": ...

# ys_codebase/source/server/server/logger.py
def _extract_log_file_timestamp(file_path: str, time_format: str, header_regex: re.Pattern) -> str: ...
def _safe_replace_file(src: str, dst: str) -> None: ...

class ServerLogger:
    TIME_FORMAT: str
    HIST_REGEX: re.Pattern
    MAX_HIST_FILES: int
    START_BANNER_PREFIX: str
    HEADER_TIME_REGEX: re.Pattern
    def write_raw(self, line: str) -> None: ...

# ys_codebase/source/server/server/service.py
def _load_service_class_from_uri(uri_str: str, provider: str = "unknown") -> Optional[type]: ...

class ServiceManager:
    def stop_all(self) -> None: ...

# ys_codebase/source/server/server/watcher.py
def _scan_modules_dir(modules_dir: str) -> Dict[str, float]: ...

class ModulesWatcher:
    def _notify_change(self, affected_modules: Set[str]) -> None: ...
    def _has_changed(self, prev: Dict[str, float], curr: Dict[str, float]) -> bool: ...

# ys_codebase/source/server/server/worker.py
class WarmWorker:
    def _prepare_execution_env(self, cwd: str, env: Optional[Dict[str, str]]) -> None: ...
    def _dispatch_command_with_captured_streams(self, module: str, args: List[str], streamer: DebouncedIOStreamer) -> int: ...
    def execute_task(self, module: str, args: List[str], cwd: str, env: Optional[Dict[str, str]] = None) -> int: ...

def worker_main(yscb_root: str, in_stream: Any = None, out_stream: Any = None) -> None: ...

# ys_codebase/source/server/server/master.py
def format_uptime(uptime_sec: float) -> str: ...
def format_watcher_status(watcher: Optional[Dict[str, Any]], include_slash: bool = True) -> str: ...
def read_daemon_state(yscb_root: str) -> Optional[ServerDaemonState]: ...
def build_fallback_status_payload(state: ServerDaemonState) -> Dict[str, Any]: ...
def spawn_detached_master(yscb_root: str, idle_timeout_sec: float, enable_watcher: bool = True) -> int: ...

class MasterSupervisor:
    def start(self, foreground: bool = False) -> int: ...
    def stop(self) -> None: ...
    def _initialize_daemon_environment(self) -> None: ...
    def _start_http_and_watcher_services(self) -> None: ...
    def _run_supervisor_main_loop(self, foreground: bool) -> None: ...
    def _ensure_ready_worker(self) -> subprocess.Popen: ...
    def _stream_task_over_worker_pipe(
        self,
        proc: subprocess.Popen,
        target_mod: str,
        req_payload: Dict[str, Any],
        chunk_emitter: Callable[[Dict[str, Any]], None],
    ) -> int: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `ServerLogger.write_raw`：當 `echo_console=True` 且標準輸出管道關閉或中斷時，僅捕獲 `OSError` 並忽略，確保檔案日誌正常落盤且不拋出 `NameError`（對應 `FR-01`）。
  - `MasterSupervisor.start`：若成功取得 `daemon.lock` 後於初始化階段拋出任何 `Exception`，強制執行 `self.stop()` 釋放鎖與資源後再向外拋出（對應 `FR-02`, `EC-01`）。
  - `worker_main`：`finally` 區段保證在 `worker` 為 `None` 時不觸發 `AttributeError` / `UnboundLocalError`，且無條件還原 `sys.stdout`（對應 `FR-02`, `EC-02`）。
- **階段決策紀錄**：`[P03:DR-01]` 遵循 `Mode A` 零容忍清除規範，直接移除 `ServerConfig.load(workspace_root)`、`MasterSupervisor.stop(force)` 與 `ServiceManager.stop_all(timeout_sec)` 三個無作用參數，不保留預設值相容層（全倉外部模組 `0` 處傳入該等參數）。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: 獨立底層與門面模組純化
  ├── server/__init__.py (M-01)
  ├── server/config.py   (M-02)
  ├── server/logger.py   (M-09, F-01, F-05)
  ├── server/service.py  (M-04, M-07, M-11)
  └── server/watcher.py  (M-08, M-11)
        │
        ▼
Step 2: Worker 與 Master 核心調度層重構
  ├── server/worker.py   (M-10, M-11, F-02, F-06)
  └── server/master.py   (M-03, M-05, M-06, F-02, F-03, F-04, F-06)
        │
        ▼
Step 3: CLI 控制面板收斂與測試集同步更新
  ├── scripts/cli.py     (M-06, M-11, F-04, F-06)
  └── tests/test_*.py    (同步更新呼叫簽名與補齊 P0 缺陷回歸測試)
```
