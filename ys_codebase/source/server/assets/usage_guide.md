### 📦 Server 常駐服務引擎 (`server` — 毫秒級 CLI 熱啟動與背景微服務容器)

- **① 模組定位與適用時機**：
  - 採用 Master-Worker 雙層常駐架構，預先載入 Python 重型依賴與向量模型（Warm Worker），將高頻 CLI 指令（如 `knowledge-db search`）加速至毫秒級響應，並具備閒置超時自動休眠 (Idle TTL) 特性。
  - 日常由 CLI 自動按需喚醒；當你需要檢視常駐狀態、手動熱重載 Worker 記憶體或排解 Port 衝突時使用。
- **② 標準用法速查 (Golden Recipes)**：
  - **檢視常駐狀態與託管服務 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ server status`
  - **熱重載 Worker 記憶體快取 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ server reload`（修改代碼或組態後立即生效）
  - **手動啟停守護進程 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ server start --daemon` / `python __${yscb.host://yscb.py}__ server stop`
- **③ 隨包手冊語意連結**：
  - 深入探索 IPC 通訊協議與背景服務註冊方式請按需唯讀查閱 [`server 隨包手冊`](`__#{module://server/README.md}__`)。
