# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge_db_service_worker_and_pipeline  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `KnowledgeDBServiceWorker` 實作 | 繼承 `server.service.BaseServiceWorker`，命名為 `"knowledge-db-watcher"`，實作 `start(context)`、`stop()` 與 `health_check()`。於背景啟動 Watchdog 檔案監聽線程，以 500ms 防抖聚合變更事件，動態自 `SpaceManager` 彙整副檔名，觸發增量熱修補並安全捕獲異常 | P0 | [P00:DR-01] |
| **FR-02** | 刪除 `knowledge-db daemon` CLI 命令 | 自 `scripts/cli.py` 徹底拔除 `daemon` 子命令分支與說明文案；精簡 `daemon.py`，廢除自製 `HotReloadServer`、PID 鎖檔、Console 視窗與自製進程生命週期 | P0 | [P00:DR-02] |
| **FR-03** | Worker 預熱事件響應 (Eager Preload) | 監聽 `server_worker_warming` 核心事件；當常駐 Worker 預熱時，提前初始化 `KnowledgeEngine` 並將 FastEmbed 向量模型單例與倒排索引/圖譜快照載入記憶體 | P0 | [P00:DR-03] |
| **FR-04** | 記憶體快取與 mtime 微秒級熱刷新 | 查詢引擎持有記憶體快照之 `last_modified_time`；每次執行檢索/拓撲分析前微秒級比對磁碟快照 mtime，若檢測到背景已熱修補則自動重新載入記憶體快取 | P0 | [P00:DR-05] |
| **FR-05** | 微內核底層原語全面對齊 | 知識庫檔案排他鎖全面採用 `core.platform.lock.InterProcessLock`；二進位快照、快取讀寫全面對齊 `core.vfs` 的 `atomic_write` 與路徑防逃逸約束 | P0 | [P00:DR-04] |
| **FR-06** | 冷模式透明降級 (JIT Check) | 當 `server` 未啟動或離線調用時，CLI 自動 fallback 執行輕量 JIT 檢查與磁碟冷讀取，保障無 Server 環境下功能 100% 完整可用 | P1 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Service Worker 正在熱寫入快照時併發查詢 | 透過 `core.vfs.atomic_write` 原子覆蓋，讀取端永遠僅能看見舊版或新版完整快照，絕不讀取到半寫入損毀檔案 |
| **EC-02** | 高頻連續檔案變更 (如 Git 切分支) | Watcher 內部 500ms 防抖定時器聚合批次事件，合併為單次增量修補，避免反覆重建導致 CPU 飆高 |
| **EC-03** | 向量模型 FastEmbed 載入失敗或相依異常 | 自動安全降級為 Lexical-only (BM25) 檢索，不中斷檢索與拓撲分析流程，並記錄 Debug 警告 |
| **EC-04** | Service Worker 異常中斷 | `health_check()` 返回 `False`，Master Supervisor 記錄異常但不影響 Worker 派發與其他模組 |
| **EC-05** | 尚未建置全域索引即發起查詢 | 提示 "未建立全域倒排索引，請先執行 python yscb.py knowledge-db index" 並安全退出（Exit Code 1） |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 延遲 | 常駐 Worker 預熱完成後，檢索命令純執行時間降至 <30ms |
| **NFR-02** | 資源 / 生命週期 | Watcher 與快取完全跟隨 Server 配置（15 分鐘 TTL 共享自毀），無單獨長駐孤兒進程 |
| **NFR-03** | 代碼品質與合規 | 移除 `daemon.py` 1200+ 行非核心負擔，代碼簡潔純淨，通過 `dev check knowledge-db` |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** Worker 子進程與 Master 進程職責分離：Watcher 監聽線程僅由 Master 納管之 ServiceWorker 運行；Worker 進程專注於序列化執行 CLI 指令，切勿在 Worker 內部重複啟動 Watcher。
- **`[!CAUTION]`** 檔案 mtime 比對時需考慮檔案系統時間解析度限制（通常為微秒級），比對時應判定 `current_mtime > cached_mtime`。
