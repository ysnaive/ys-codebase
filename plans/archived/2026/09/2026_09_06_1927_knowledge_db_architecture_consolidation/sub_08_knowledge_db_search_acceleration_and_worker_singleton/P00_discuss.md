# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_08_knowledge_db_search_acceleration_and_worker_singleton  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 計畫類型：Performance  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：用戶反饋「為甚麼 knowledge db search 要這麼久? 有 server 運行的化，這個操作應該要很快吧?」，並於性能瓶頸架構深度剖析後指示「規劃為 sub 08」。
- **核心目標**：
  1. **Worker 常駐單例化 (KnowledgeEngine & Pipeline Singleton)**：Worker 常駐進程生命週期內維持單例快取，避免每次 CLI 派發皆重新 `spec.loader.exec_module` 與重複建構 10+ 個內部子物件 (~100ms)。
  2. **守護進程開機預熱 (Daemon Boot Pre-warm)**：於 Server 啟動或 Worker 準備就緒時，背景預先反序列化載入倒排索引、向量特徵庫與圖譜，消除首次查詢 ~850ms 的 Gzip 磁碟解壓懲罰。
  3. **事件驅動變更感知 (Watcher-driven Cache Invalidation)**：整合 `server` 背景檔案監聽器，由監聽事件被動標記 Dirty Flag，取代每次 `search` 前無差別主動走訪全庫 280+ 檔案執行 `os.stat` (~80ms)。
  4. **達成極致性能目標**：常駐運行下，純關鍵字檢索穩定達到 **< 20ms** 響應，混合向量語意檢索達到 **< 50ms** 瞬發。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁破壞 BM25 檢索排序、向量 RRF 倒數排名融合演算法之準確度與結果一致性。
  - 嚴禁破壞無 Server 守護進程運行時的獨立 In-process 派發相容性（無 server 時維持既有 JIT stat 兜底防護）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 模組進入點與引擎單例快取策略**：
  在 `server.worker` 內優化模組載入機制，對已載入之 `scripts.cli` 模組避免重複執行 `exec_module`；同時在 `knowledge-db` 端將 `KnowledgeEngine` 提升為進程級安全單例，跨請求復用 `IndexingPipeline` 記憶體狀態。
- **[P00:DR-02] 標準生命週期事件預熱 (core.events.broadcast)**：
  Server Worker 初始化完成進入 `READY` 狀態時，透過標準事件總線廣播 `events.broadcast("worker_warming", emit_module="server")`。各模組透過 `scripts/hook.server.py` 之 `on_worker_warming` 勾點非同步預熱記憶體快取與模型單例，消除首次查詢解壓冷啟動。
- **[P00:DR-03] Watcher 事件驅動快取有效性機制 (Event-driven Dirty Flag)**：
  利用 `server.watcher`（`ModulesWatcher` / `KnowledgeDBServiceWorker`）監控專案目錄，變更發生時置位 `is_dirty`；`pipeline.search()` 僅在 `is_dirty == True` 時才觸發熱補丁或增量掃描，未變更時 0ms 跳過 stat 走訪。
- **[P00:DR-04] contributes/server.json 純淨宣告與 core SDK 統一注入**：
  各模組於 `contributes/server.json` 專注宣告常駐背景服務 (`services`)，不混雜生命週期邏輯。Server Master 嚴禁自行遍歷檔案系統，強制調用 `core.contributes.get("server")` 取得由 core 聚合與標註 `__provider__` 的宣告，動態實例化並統一納管。
- **[P00:DR-05] Background Services 運作狀態可觀測性**：
  `server status` 透過 `ServiceManager` 動態收集所有模組註冊之 ServiceWorker 運行狀態（名稱、所屬模組、健康狀態），在 CLI 終端儀表板格式化展示。

---

## 3. 開放議題與確認紀錄

- [x] 無 server 守護進程時是否保持 100% 行為一致？（確認：無 server 時維持既有主動 stat 嗅探兜底）。
- [x] Background Services 是否改為標準 Hook？（確認：採 `contributes/server.json` 並由 `core.contributes` SDK 取得）。
- [x] 預熱機制是否走生命週期事件？（確認：不塞進 contributes，走標準 `core.events.broadcast("worker_warming", emit_module="server")`）。


