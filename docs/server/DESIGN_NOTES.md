# Server 模組設計決策與工程註記 (DESIGN_NOTES.md)

| 決策編號 | 標題 / 主題 | 影響檔案 | 風險等級 |
| :--- | :--- | :--- | :---: |
| **[DN-01]** | 方案 C Master-Worker 雙進程模型 | `server/master.py`, `server/worker.py` | Low |
| **[DN-02]** | 500ms 防抖分流串流協議 | `server/streamer.py` | Low |
| **[DN-03]** | yscb 宿主四大耦合邊界 | `yscb.py` | Low |
| **[DN-04]** | 統一生命週期與共享 15 分鐘自毀 (TTL) | `server/master.py`, `server/service.py` | Low |

---

### [DN-01] 方案 C Master-Worker 雙進程模型
- **背景**：CLI 工具常駐化需兼顧啟動加速 (<30ms) 與模組記憶體隔離。
- **決策**：Master 進程處理 HTTP 與生命週期；Worker 子進程常駐預熱並按需延遲加載目標模組。模組崩潰由 Master 自動拉新 Worker 自癒。

### [DN-02] 500ms 防抖分流串流協議
- **背景**：避免頻繁微小 TCP 封包衝擊，兼顧終端即時互動感。
- **決策**：設置 500ms 緩衝閥值，有換行或結束時立即 flush，封包嚴格區分 `terminal_stream` 與 `task_finish`。

### [DN-03] yscb 宿主四大耦合邊界
- **背景**：防止 `yscb.py` 再次膨脹與硬依賴。
- **決策**：落實「軟依賴探測、自循環旁路、按需非同步拉起、極簡客戶端」四大原則。

### [DN-04] 統一生命週期與共享 15 分鐘自毀 (TTL)
- **背景**：業務 Service Worker（如 Watchdog）若獨立長駐會導致背景資源持續洩漏。
- **決策**：Service Worker 嚴格跟隨 Server 生命週期配置。有 TTL 則一同自毀，無 TTL 則一同常駐；手動 `stop` 時同步退出。
