---
target: "Core"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb://source/core/core/platform/process.py"
  - "yscb://source/core/core/platform/lock.py"
  - "yscb://source/core/core/platform/daemon_probe.py"
related_docs:
  - "./README.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-11-04"
---

# Core Platform 跨平台底層原語手冊 (core.platform)

> 所屬模組：`core`  
> 首次引入版本：`v1.1.0` (sub_03)  
> 核心職責：收斂跨平台（Linux/POSIX 與 Windows）作業系統與進程管理差異，提供無第三方依賴的純標準庫原語。

---

## 1. 進程生命週期原語 (`core.platform.process`)

### 1.1 `spawn_detached(cmd, cwd=None, env=None) -> int`
以非同步脫鉤方式在背景啟動獨立進程，父進程退出不波及子進程：
- **POSIX**：`start_new_session=True` (`os.setsid`)，重定向標準串流至 `/dev/null`。
- **Windows**：`CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`。

### 1.2 `is_process_alive(pid: int) -> bool`
精確探測指定 PID 是否真正在線運行：
- **POSIX**：透過 `os.kill(pid, 0)` 探測，並主動解析 `/proc/<pid>/status` 狀態以精確排除殭屍進程 (`Z` / `X`)；嘗試非阻塞 `os.waitpid` 收割子進程。
- **Windows**：透過 Win32 `OpenProcess` + `GetExitCodeProcess` 判斷 `STILL_ACTIVE`。

### 1.3 `kill_process_tree(pid: int, timeout_sec: float = 3.0) -> bool`
優雅且強制收割指定 PID 及其整棵衍生進程樹：
- **POSIX**：優先發送 `os.killpg(pgid, SIGTERM)`，等待寬限期；超時自動升級為 `SIGKILL`。
- **Windows**：調用 `taskkill /F /T /PID <pid>`。

### 1.4 `terminate_popen_tree(proc, timeout_sec: float = 2.0) -> bool`
終止自身持有 `Popen` 句柄之子進程（及其進程群組），並由 `Popen` 自行回收退出狀態：
- **POSIX**：子進程須以 `start_new_session=True` 啟動；`killpg` SIGTERM → `proc.wait(timeout)` → SIGKILL → `proc.wait`。
- **Windows**：`taskkill /F /T` → `proc.wait`，逾時再 `proc.kill()`。
- 對自身子進程應優先使用本函式與 `proc.poll()`，而非 `is_process_alive()`（其非阻塞 `waitpid` 會與 `Popen` 搶回收）。

### 1.5 `can_spawn_background_daemon(force_reprobe=False, yscb_root=None) -> bool`
判定當前環境能否讓背景 daemon 存活：`YSCB_FORCE_DAEMON=1` → `True`；`YSCB_NO_DAEMON=1` → `False`；Windows 走 Job Object breakaway 探針（進程級快取）；POSIX 有 `yscb_root` 時依 `daemon_probe.is_reaping_env()`（不快取），否則 `True`。

## 1A. 背景 daemon 實證回收探針 (`core.platform.daemon_probe`)

僅標準庫、不依賴 `server`，記錄於 `<yscb_root>/.cache/server/spawn_probe.json`（依 `env_fingerprint()` 分鍵）：

| 函式 | 職責 |
| :--- | :--- |
| `env_fingerprint()` | `hostname\|sys.platform` |
| `record_spawn(root, pid)` | auto-spawn 後記錄 PID，`clean_exit=false` |
| `bind_master_pid(root, pid)` | Master 取鎖後將紀錄 PID 由 launcher 改綁為自身 |
| `mark_clean_exit(root)` | 正常/強制停止後標記並將 `reaped_count` 歸零 |
| `is_reaping_env(root, daemon_active=None)` | 紀錄 PID 已死、未 clean exit、daemon 不活躍時累計；`reaped_count >= REAP_THRESHOLD (2)` 回傳 `True` |
| `is_daemon_lock_held(root)` | 以能否取得 `daemon.lock` 判定 daemon 活躍 |

所有 I/O 錯誤內部降級（視為無紀錄）。機制全貌見 [server/daemon_architecture.md](../server/daemon_architecture.md) §5。

---

## 2. 跨平台跨進程檔案鎖 (`core.platform.lock`)

### `InterProcessLock(lock_file)`
提供統一的跨進程檔案排他互斥鎖，支援 Context Manager：
- **POSIX**：`fcntl.flock(fd, LOCK_EX | LOCK_NB)`。
- **Windows**：`msvcrt.locking(fd, LK_NBLCK, 1)`。
- **句柄不可繼承保證**：開啟鎖檔案描述符後強制執行 `os.set_inheritable(fd, False)`，防止父進程在持鎖期間派生 Worker 或自我重啟子進程時洩漏鎖句柄。
- **開檔重試**：部分共享/9p 檔案系統在並發建立同一檔案時會對 `O_CREAT` 瞬態拋 `FileExistsError`；`acquire()` 對此最多重試 3 次（間隔 50ms，改以不帶 `O_CREAT` 開啟），仍失敗則拋出原始例外，其他錯誤照拋。
- **使用範例**：
  ```python
  from core.platform import InterProcessLock

  with InterProcessLock("path/to/daemon.lock"):
      # 互斥保護區
      pass
  ```
