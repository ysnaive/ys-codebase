# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_10_server_hot_reload_dispatch_and_master_self_restart  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Draft  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「我發現你手動重啟了 server，之前有設計，當非 server module 更新時，只重啟 worker，當 server 本體更新時，重啟整個 server，現在有辦法驗證嗎?」➔「開啟 sub 10 優化計畫，修復此問題」
- **核心目標**：
  1. 賦予 `ModulesWatcher` 精確的變更路徑感知能力，識別變動檔案屬於哪個模組。
  2. 實現雙軌重載分流：
     - 當非 `server` 領域模組更新時，僅重啟 Warm Worker 子進程（維持 Master PID、Port 與常駐連接）。
     - 當 `server` 本體（或底層 `core` 模組）更新時，自動優雅重啟整個 Server（包含 Master 進程與 Worker 子進程，刷新全部 Python 模組記憶體）。
  3. 杜絕手動介入重啟與半成品狀態不一致問題。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更現有 HTTP Dispatch 協議格式與 500ms 防抖串流規範。
  - 不破壞現有 `server reload` 手動 CLI 指令相容性。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 模組變更路徑精準解析**：
  - `ModulesWatcher` 在 polling snapshot 比對時，計算變動檔案集合 `changed_files: Set[str]`。
  - 解析路徑相對於 `.modules/` 之第一層目錄名，提取受影響模組清單 `affected_modules: Set[str]`。
- **[P00:DR-02] 雙軌重載分流策略**：
  - 若 `affected_modules` 包含 `"server"` 或 `"core"`（涉及 Master 進程代碼記憶體）：調用 `on_server_change` 回調（觸發整個 Server 重啟）。
  - 若 `affected_modules` 僅包含其他領域模組（如 `"knowledge-db"`, `"dev"`, `"agents-workflow"`）：調用 `on_worker_change` 回調（僅重啟 Worker 子進程）。
- **[P00:DR-03] Master 優雅自重啟機制 (Graceful Respawn)**：
  - Master 需具備 `restart_server()` 能力：先釋放 state/lock 或啟動同等參數的新 Master detached 進程，並在確認新進程就緒後優雅退出自身。

---

## 3. 開放議題與確認紀錄

- [x] 非 server 模組更新已實測由 `ModulesWatcher` 自動重啟 Worker（Master PID 不變，Worker PID 更新）。
- [ ] 確定 Master 自重啟是透過外部 detached 拉起新進程後自我終止，或是透過 `os.execv` 原地替換進程影像。
