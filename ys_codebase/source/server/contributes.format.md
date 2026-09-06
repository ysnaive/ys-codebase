# Server 模組貢獻格式說明書 (contributes.format.md)

本文件定義 `server` 模組向微內核 `core` 註冊之指令與擴充規範。

## 1. 導出命令清單

- `server start`: 啟動 Server 守護進程（支援 `--daemon` 背景脫鉤與 `--console` 前台運行）。
- `server stop`: 優雅停止 Server 守護進程（支援 `--force` 強殺兜底）。
- `server status`: 檢視 Server Master、Warm Worker PID、動態 Port 與 Idle TTL 倒數計時。
- `server reload`: 手動重啟 Warm Worker 子進程，刷新已加載之模組記憶體。
