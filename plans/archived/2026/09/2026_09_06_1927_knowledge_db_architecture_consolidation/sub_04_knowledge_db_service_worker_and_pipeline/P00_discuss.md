# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge_db_service_worker_and_pipeline  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：進入 sub 04，推進 knowledge-db 本體的常駐架構適配與管線重構。
- **核心目標**：
  1. **常駐服務與 Watcher 納管對齊**：將 `knowledge-db` 現有之專屬守護進程 (`HotReloadServer` / 53KB daemon.py) 與檔案變更監聽器重構適配為 `server` 模組的 `BaseServiceWorker` 擴充，統一由 `server` 守護中樞納管生命週期（共享 15 分鐘 TTL、同步停止、消除重複守護進程與孤兒進程）。
  2. **Core 底層原語全面對齊 (`core.platform` & `core.vfs`)**：替換 `knowledge-db` 內部私有之進程拉起、PID 檢測、跨平台檔案鎖，全面對齊 `core.platform.process`、`core.platform.lock` 與 `core.vfs`。
  3. **向量與索引管線熱常駐加速 (Warm Pipeline & Memory Cache)**：善用 `server` 模組之 Warm Worker 機制，讓全域倒排索引與向量快取在常駐 Worker 內保持熱狀態，避免每次 CLI 查詢重複反序列化與模型冷加載，使 `search`、`callers`、`callees`、`impact` 具備亞秒級瞬發體驗。
  4. **CLI 與降級調度邊界**：處理 `python yscb.py knowledge-db daemon [start|stop|status|watch]` 指令與 `server` 模組之整合（如無損相容/轉發導引）；當 Server 模組未運行時維持透明冷降級 (JIT 檢查)。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴格遵守全域重構期管制紀律：**嚴禁執行本地 `@build` 自部署**。
  - 不變動知識庫的檢索算法核心（BM25、Hybrid Rerank、Tree-sitter AST 解析器邏輯維持現狀）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 廢除自製守護進程，收斂為 `KnowledgeDBServiceWorker`**：徹底拆除現有 `daemon.py` 中的進程拉起、Console 視窗、PID 鎖檔、日誌輪轉等系統級負擔，全面交由 `server` 模組與 `core.platform` 掌理；知識庫僅保留專門負責檔案變更防抖 (500ms) 與熱自癒修補管線之 `KnowledgeDBServiceWorker` (實作 `server.service.BaseServiceWorker`)，由 `server` 模組統一啟停並共享 15 分鐘 TTL 生命週期。
- **[P00:DR-02] 拔除 `knowledge-db daemon` CLI 子命令 (不保留兼容)**：本次為架構性 minor 升級，直接從 `scripts/cli.py` 徹底刪除 `daemon` 子命令與相關分支，不保留任何 legacy code 或代理相容，守護進程由全域統一指令 `python yscb.py server` 管理。
- **[P00:DR-03] Worker 預熱階段提前載入模型與索引 (Eager Preload)**：善用 sub_03 的 `server_worker_warming` 預熱事件機制，在 Worker 啟動預熱階段提前載入 FastEmbed 向量模型、全域倒排索引與呼叫圖譜至記憶體單例中，後續檢索與拓撲分析命令直接 0 等待即刻秒發。
- **[P00:DR-04] 微內核原語全面對齊 (`core.platform` & `core.vfs`)**：知識庫全模組內部進程檢測、鎖定全面遷移至 `core.platform`（`InterProcessLock`），二進位快照與檔案讀寫全面透過 `core.vfs`（`OSBackend` 與 `atomic_write`）實作，禁絕各模組各自為政。
- **[P00:DR-05] 記憶體快取以微秒級檔案時間戳 (mtime) 比對熱刷新**：常駐 Worker 快取持有磁碟二進位快照的時間戳；執行查詢時以微秒級比對磁碟快照 mtime，若檢測到 Service Worker 已在背景熱修補完成，則原地熱刷新記憶體快取，邏輯自洽且徹底杜絕跨進程事件競態。

---

## 3. 開放議題與確認紀錄

- [x] **議題 1 (Daemon 職責重構與瘦身)**：將進程管理、Lock、生命週期交給 `server`，收斂為 `KnowledgeDBServiceWorker`。（確認：是）
- [x] **議題 2 (CLI 指令相容性)**：`knowledge-db daemon` 處置方式。（確認：直接刪除，不向下相容）
- [x] **議題 3 (常駐 Worker 快取機制)**：模型與索引加載策略。（確認：預熱階段提前載入）
- [x] **議題 4 (記憶體快取與熱修補同步)**：常駐 Worker 透過微秒級檔案時間戳比對更新快取。（確認：採用方案 A）


