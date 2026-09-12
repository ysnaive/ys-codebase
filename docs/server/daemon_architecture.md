# Server 常駐架構與通訊協定專題 (daemon_architecture.md)

本文件深入說明 `server` 模組內部 Master-Worker 進程模型、500ms 防抖串流協議與四大耦合邊界。

---

## 1. Master-Worker 進程模型

```text
[yscb.py]  <── Localhost HTTP (127.0.0.1:0 + Token) ──>  [Master Supervisor]
                                                                  │
                                                        IPC Pipe  │ (Queue)
                                                                  ▼
                                                          [Warm Worker]
                                                                  │
                                                                  ├── process(args)
                                                                  └── DebouncedIOStreamer (500ms)
```

- **Master Supervisor**：負責外部網絡、安全守門、狀態鎖 (`cache://server/daemon.json`)、Idle TTL 計時器與子進程守護自癒。
- **Warm Worker**：常駐預熱進程，內部攔截 `SystemExit` 避免被模組中斷。收到請求時以 `importlib.import_module` 延遲加載目標模組。

---

## 2. 500ms 防抖串流協議 (Debounced Streaming Protocol)

Worker 攔截 `sys.stdout` 與 `sys.stderr`，緩衝 500ms 或在有換行/結束時透過 NDJSON 分送：
- **`terminal_stream`**：`{"type": "terminal_stream", "stream": "stdout"|"stderr", "text": "..."}`
- **`task_finish`**：`{"type": "task_finish", "exit_code": 0, "duration_ms": 24.5, "error": null}`

---

## 3. yscb 宿主四大耦合邊界

1. **軟依賴探測**：`yscb.py` 零靜態 import server，探測未啟動即 100% 透明冷啟動降級。
2. **自循環旁路**：`module == "server"` 之指令強制直接走本地冷啟動，嚴禁熱派發循環。
3. **按需非同步拉起**：未運行時背景脫鉤拉起 Master，當前命令走冷啟動執行，首發零等待感。
4. **極簡客戶端**：`yscb.py` 僅內嵌 ~60 行標準庫轉發器與 wait loop。

---

## 4. 環境權限自適應探針與沙盒防護 (Adaptive Environment Probing)

1. **Windows Job Object 限制感知**：在 IDE Agent 或 CI 虛擬環境中，進程可能繫屬於未開啟 `JOB_OBJECT_LIMIT_BREAKAWAY_OK` 的 Job Object。
2. **記憶體快取探針 (`can_spawn_background_daemon`)**：
   - 透過 `ctypes` 呼叫 `kernel32.IsProcessInJob` 檢測進程狀態。
   - 非 Job 環境直接回傳 True；Job 環境下執行 1 次非破壞性探針測試 Breakaway 權限，結果快取於進程記憶體中。
3. **自適應冷派發降級**：探針失敗時，自動跳過背景拉起，直接走極速冷派發，並透過 `stderr` 提供診斷資訊與 IDE Agents 常駐指引，杜絕進程建立與被殺抖動。

