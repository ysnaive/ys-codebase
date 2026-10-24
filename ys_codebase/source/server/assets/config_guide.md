### ⚙️ Server 常駐服務守護進程設定與體檢 (`server`)

- **① 組態項目與用途（雙層組態分流）**：
  - **團隊共享組態**：[`config/server/config.project.json`](`__#{config://server/config.project.json}__`)（定義預設 `idle_timeout` 閒置休眠秒數、Worker 預熱與健康檢查間隔）。
  - **個人環境覆寫**：`config/server/config.local.json`（若開發者本機發生 Port 衝突或需調整本機專屬 `host`/`port` 時，強制寫入 `config.local.json` 避免影響團隊）。
- **② 健康度檢查條件（供 Step 1 自動驗證）**：
  - `python __${yscb.host://yscb.py}__ server status`：檢查 Master 守護進程與 Warm Worker 子進程狀態、綁定 Port、運行時長與 Idle TTL 倒數。
  - **常見異常修復**：`server` 支援 CLI 自動按需喚醒，`STOPPED` 狀態屬正常閒置休眠；若更新模組代碼或組態後需刷新記憶體，執行 `python __${yscb.host://yscb.py}__ server reload`；若遇殭屍鎖定則執行 `server stop --force` 後再喚醒。
- **③ 隨包設定手冊語意連結**：
  - 進階 Master-Worker 架構與組態參數請按需唯讀查閱 [`server 隨包手冊`](`__#{module://server/README.md}__`)。
