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
