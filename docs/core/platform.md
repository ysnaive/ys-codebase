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

---

## 2. 跨平台跨進程檔案鎖 (`core.platform.lock`)

### `InterProcessLock(lock_file)`
提供統一的跨進程檔案排他互斥鎖，支援 Context Manager：
- **POSIX**：`fcntl.flock(fd, LOCK_EX | LOCK_NB)`。
- **Windows**：`msvcrt.locking(fd, LK_NBLCK, 1)`。
- **使用範例**：
  ```python
  from core.platform import InterProcessLock

  with InterProcessLock("path/to/daemon.lock"):
      # 互斥保護區
      pass
  ```
