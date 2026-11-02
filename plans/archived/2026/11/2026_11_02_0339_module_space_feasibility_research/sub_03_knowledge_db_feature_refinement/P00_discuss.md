# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`knowledge-db` 功能細節優化（常駐背景 Worker、向量模型自動下載、忙碌毫秒探針與容差降級、`status` 詳盡觀測）  
> 建立日期：2026-11-02  
> 所屬主計畫：`2026_11_02_0339_module_space_feasibility_research`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 測試通過，原 `sub_03` 延後為 `sub_04`，新 `sub_03`：`knowledge-db` 功能細節優化。
  2. 首先最重要的是，`knowledge-db` 還是要維護自己的後台 worker，以此常駐分批解析並增量更新資料庫（尤其向量索引）。
  3. 因為模型是存放快取的關係，換環境或清垃圾很容易被清掉，但每次下載又不是自動的，每次都要跳警告 $\to$ Agents 反問確認 $\to$ 下載，太麻煩了；在有 worker 的情況下可以都交由 worker 在背景做完（若環境沒安裝 `server` 則維持原樣）。
  4. 添加一個探針函式 `is_worker_busy() -> int`（單位 `ms`），回傳已運行多久（`0` 代表空閒，`> 0` 代表已忙碌毫秒數）。當 `is_worker_busy()` 為忙碌時等效向量資料庫啟用但還沒準備好，此時搜尋功能給予 `jit_vector_timeout_ms` 毫秒（設定於 config，直接用 `ms` 當單位，預設 `3000`）容差等待：若後台已運行超過 `jit_vector_timeout_ms` 則前台不用再等，直接瞬時降級；若未滿 `jit_vector_timeout_ms` 則最多等待剩餘毫秒數，超過上限就降級純 BM25 並提示 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`（而當環境無 `server`，這個 `jit_vector_timeout_ms` 就是前台向量資料自癒上限熔斷時間）。
  5. `knowledge-db status` 指令不夠直白詳細，需聚焦強化 `knowledge-db status` 觀測資訊。
- **核心目標**：
  1. **專屬常駐 `KnowledgeDBServiceWorker` (`knowledge-db-worker`) 兩階段背景管線**：於不重複啟動 `watchdog` 的前提下（檔案監聽 100% 由 `module:space` 之 `space-watcher` 負責並透過 `on_space_changed` 事件通知），恢復 `knowledge-db` 專屬背景 Worker，執行「階段一：毫秒級 AST + BM25 + Call Graph 增量同步」與「階段二：微批次（Micro-batch）向量差集自癒補齊（比對 `unified_index.symbols` 與 `vector_index.doc_ids` 差集分批計算並落盤）」。
  2. **有 Worker 環境下之背景全自動向量模型下載**：當 `is_worker_active()` 為真且 `enable_vector_search=True` 時，若偵測到本地缺少 FastEmbed ONNX 模型，由 `knowledge-db-worker` 於背景自動呼叫 `download_model()` 並接續完成微批次向量建置，前台檢索與 Agent 絕不跳出 `[GUARD]` 阻斷反問；無 `server` 環境則維持既有 `[GUARD]` 安全詢問機制。
  3. **`is_worker_busy() -> int`（已運行毫秒數）探針與可由 Config 設定之 `jit_vector_timeout_ms`（預設 `3000`）動態剩餘容差等待／熔斷降級**：實作跨執行緒／跨行程忙碌時鐘探針 `is_worker_busy() -> int`，由 `KnowledgeDBConfig` 讀取毫秒設定 `jit_vector_timeout_ms: int = 3000`（向下相容舊設定鍵 `jit_vector_timeout_seconds` 自動換算毫秒），在有 Worker 時按 `remain_ms = timeout_ms - elapsed_ms` 動態等待或 `0ms` 瞬時降級純 BM25 並提示 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`；在無 Worker 時作為前台 JIT 自癒熔斷上限且不永久鎖死後續查詢。
  4. **`knowledge-db status` 直白詳盡化升級**：全面擴充 `engine.status()` 與 `scripts/cli.py:status()`，直觀展示「後台 Worker 狀態與忙碌毫秒／當前任務階段」、「BM25 倒排／Call Graph 圖譜／Vector 向量三大索引細部指標與向量覆蓋率 `%`」、「當前生效檢索模式與原因」、「向量模型與 Runtime 組態」以及「`space` 水位線世代同步狀態 (`acked_gen / head_gen`)」。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `module:server` 之 `BaseServiceWorker` 與 `is_worker_active("knowledge-db", "knowledge-db-worker")` 生命週期契約，註冊於 `ys_codebase/source/knowledge-db/contributes/server.json`。
  - 復用 `module:space` 之 `SpaceManager`、`consume_diff(consumer_id="knowledge-db")`、`ack_diff()` 與 `on_space_changed` hook (`ys_codebase/source/knowledge-db/scripts/hook.space.py`)，絕不在 `knowledge-db` 內重建任何 `watchdog` 或目錄掃描器。
  - 復用並擴充 `knowledge_db/embedding.py` (`EmbeddingService`、`VectorIndex`、`load_vectors`、`save_vectors`) 與 `knowledge_db/engine.py` (`KnowledgeEngine`)。
- **邊界排除 (Explicitly Excluded)**：
  - 不修改 `module:space` 或 `module:server` 的核心程式碼與公開 API。
  - 不在 `knowledge-db` 中引入 `watchdog` 套件或自建檔案系統輪詢器（Polling watcher）。
  - 不在無 `server` 常駐環境的前台 CLI 中偷渡自動下載數百 MB 向量模型的行為。
  - `sub_04` (`agents-workflow` 空間指紋整合) 明確維持 `Deferred`，不在本子計畫實作。
- **架構影響範圍**：
  - `ys_codebase/source/knowledge-db/contributes/server.json`（新增宣告 `knowledge-db-worker` 常駐服務）
  - `ys_codebase/source/knowledge-db/knowledge_db/service.py`（新增 `KnowledgeDBServiceWorker` 兩階段背景佇列、微批次向量自癒與忙碌時鐘狀態檔維護）
  - `ys_codebase/source/knowledge-db/knowledge_db/config.py`（設定參數改為 `jit_vector_timeout_ms: int = 3000`，新增 `vector_batch_size: int = 32`）
  - `ys_codebase/source/knowledge-db/knowledge_db/embedding.py`（Docstring 嵌入長度截斷保護、支援微批次增量向量計算與合併）
  - `ys_codebase/source/knowledge-db/knowledge_db/engine.py`（新增 `is_worker_busy() -> int`、`wait_for_worker_idle(timeout_ms)`、`search()` 動態剩餘容差等待與降級提示、`pre_warm()` 尊重 `enable_vector_search`、`status()` 結構化詳盡指標）
  - `ys_codebase/source/knowledge-db/scripts/hook.space.py` 與 `scripts/hook.server.py`（串接 `KnowledgeDBServiceWorker` 非阻塞喚醒與探針）
  - `ys_codebase/source/knowledge-db/scripts/cli.py`（升級 `knowledge-db status` 終端機排版與 `--json` 欄位）
  - `ys_codebase/source/knowledge-db/tests/`（新增對應單元與邊界測試）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 職責正交之 `KnowledgeDBServiceWorker` (`knowledge-db-worker`) 兩階段背景管線架構（五維度探針軸一／軸三）**：
  - **決策**：`module:space` 的 `space-watcher` 專責作業系統級檔案變更監控與 `YFP2` 快照更新；`knowledge-db` 則透過 `contributes/server.json` 註冊專屬 `KnowledgeDBServiceWorker` (`service_id: "knowledge-db-worker"`) 專責「高耗時知識庫解析與向量計算」。
  - 當 `space-watcher` 觸發 `on_space_changed(space_id="knowledge_space")` 時，`hook.space.py` 若偵測到 `KnowledgeDBServiceWorker` 在線，僅做 O(1) Event 喚醒（絕不阻塞 `space-watcher` 執行緒）；若不在常駐進程內則退回同步快篩消費。
  - `KnowledgeDBServiceWorker` 背景循環分為兩階段：
    1. **Stage 1（Fast Path — AST + BM25 + Call Graph）**：立即呼叫 `consume_diff(consumer_id="knowledge-db")` 解析變更檔案、更新 `unified.index.bin.gz` 與 `unified.graph.bin.gz` 並呼叫 `ack_diff()` 推進游標，使詞法與圖譜檢索在毫秒級內即時反映最新代碼。
    2. **Stage 2（Slow Path — 微批次向量差集自癒補齊）**：比對 `unified_index.symbols` 與 `vector_index.doc_ids`（同時剔除已刪除符號、找出缺少向量的符號 ID），以微批次（預設每批 `32` 個符號）呼叫 FastEmbed 計算向量並增量寫回 `unified.vectors.bin.gz`。每批之間檢查 `stop_event` 與新進 `space` Diff（若有新代碼變更優先插隊執行 Stage 1），徹底解決「首次缺少 `unified.vectors.bin.gz` 或單次超時跳過後，因 `space` 游標已 ACK 導致向量永遠無法自癒」的結構性問題。
- **[P00:DR-02] 常駐 Worker 背景自動下載向量模型與無 Server 環境雙軌分流（五維度探針軸二）**：
  - **決策**：
    - **有常駐 Worker 時 (`is_worker_active() == True`)**：當 `config.enable_vector_search=True` 且 `embedding_service.is_model_downloaded() == False`（例如快取被清除或新環境啟動），由 `KnowledgeDBServiceWorker` 在背景執行緒直接執行 `embedding_service.download_model()`，完成後自動進入 Stage 2 微批次向量建置。在此期間前台 `search()` 因偵測到 Worker 忙碌或向量尚未備妥，僅平順降級為純 BM25 檢索，**不向 `stderr` 輸出 `[GUARD]` 警告，亦不要求 Agent 停手反問使用者**。
    - **無常駐 Worker 時 (`is_worker_active() == False`)**：維持既有非破壞性預設行為——前台絕不擅自下載模型，於 `search()` 時降級純 BM25 並輸出 `[GUARD]` 提示（每進程僅提示一次）。
- **[P00:DR-03] `is_worker_busy() -> int`（已運行毫秒數）探針與 Config 可配置 `jit_vector_timeout_ms`（預設 `3000`）動態剩餘容差等待／熔斷契約（五維度探針軸四）**：
  - **決策**：
    - 新增公開方法 `engine.is_worker_busy() -> int`（及模組級輔助函式）：回傳後台 Worker 當前連續忙碌的**已運行毫秒數 (`elapsed_ms: int`)**；`0` 代表空閒（或 Worker 未運行），`> 0` 代表目前已持續執行任務 `elapsed_ms` 毫秒。
    - **跨行程與同行程雙重同步機制**：`KnowledgeDBServiceWorker` 進入忙碌區段（模型下載、Stage 1 索引更新、Stage 2 向量批次計算）時，同步記錄同行程單調時間戳 `_busy_since_ts` 並原子寫入狀態檔 `indices/.kdb_worker_state.json`（含 `busy: true`、`start_ts: float`、`pid: int`、`phase: str`、`progress: str`）；完成全部批次轉為空閒或 `on_stop()` 卸載時，清除忙碌標記（重置為 `0`）。讀取端若發現 `pid` 已不存在則自動視為陳舊狀態回傳 `0`，確保異常崩潰後之冪等自癒。
    - **搜尋端動態讀取 Config `jit_vector_timeout_ms: int = 3000`（直接以 `ms` 為單位，支援於 `ys_codebase/config/knowledge-db/config.json` 任意自訂，絕不硬編碼寫死 `3000`）雙模行為**：
      - 動態讀取 `timeout_ms = max(0, int(self.config.jit_vector_timeout_ms))`。
      1. **當後台 Worker 啟用時 (`is_worker_active() == True`)**：
         - `elapsed_ms = engine.is_worker_busy()`
         - 若 `elapsed_ms == 0`：後台空閒，若磁碟已有最新向量檔則熱重載後直接執行 `hybrid_rrf`。
         - 若 `elapsed_ms >= timeout_ms`（例如後台正在下載模型或執行大型全量向量建置，已耗時 $\ge \text{timeout\_ms}$）：**前台等待 `0ms`**，立即降級為純 BM25 並向 `stderr` 輸出：`[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`。
         - 若 `0 < elapsed_ms < timeout_ms`：前台最多等待剩餘容差時間 `remain_ms = timeout_ms - elapsed_ms`（即 `remain_ms / 1000.0` 秒，輪詢或等待 `idle_event`）。若在 `remain_ms` 內後台完成（`is_worker_busy() == 0`），立即熱重載最新 `unified.vectors.bin.gz` 並執行 `hybrid_rrf`；若屆滿仍忙碌，則降級為純 BM25 並向 `stderr` 輸出：`[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`。
      2. **當環境無 Server / Worker 未啟用時 (`is_worker_active() == False`)**：
         - `self.config.jit_vector_timeout_ms`（預設 `3000` ms，即 `3.0` 秒）作為前台 JIT 向量自癒的探針熔斷時間上限；且修正單次探針超時僅針對當次（或短暫冷卻窗口）降級，不在常駐記憶體中永久鎖死 `_vector_degraded = True`。
- **[P00:DR-04] `knowledge-db status` 直白詳盡化觀測契約**：
  - **決策**：升級 `engine.status()` 回傳結構與 `python yscb.py knowledge-db status` 終端機輸出，明確分區呈現：
    1. **後台服務與工作狀態 (Background Worker)**：
       - Worker 狀態：`Running` / `Stopped (Standalone Mode)`
       - 忙碌探針：`Idle (0 ms)` 或 `Busy (已運行 {elapsed_ms} ms | 階段: {phase} | 進度: {progress})`
    2. **三大核心索引詳情 (Core Indices Breakdown)**：
       - **BM25 倒排索引 (`unified.index.bin.gz`)**：狀態（`Ready` / `Missing`）、符號總數 (`symbol_count`)、詞條總數 (`term_count`)、檔案大小 (`size_kb`)、最後更新時間。
       - **呼叫圖譜索引 (`unified.graph.bin.gz`)**：狀態（`Ready` / `Missing`）、節點數 (`node_count`)、呼叫邊總數 (`edge_count`)、檔案大小 (`size_kb`)。
       - **語意向量索引 (`unified.vectors.bin.gz`)**：狀態（`Ready` / `Syncing` / `Missing` / `Disabled`）、已嵌入向量數 / 符號總數（`{vector_count} / {symbol_count}`，覆蓋率 `{coverage_pct}%`）、待補齊差集數 (`pending_vectors`)、向量維度 (`dimension`)、檔案大小 (`size_kb`)。
    3. **檢索模式與向量模型 (Retrieval & Vector Model)**：
       - 當前生效檢索模式：`hybrid_rrf (BM25 + Vector)` 或 `lexical_bm25 (純詞法降級 — 原因: ...)`
       - 模型名稱 (`model_name`)、模型快取狀態（`Downloaded` / `Downloading` / `Not Downloaded`）、向量檢索開關 (`enable_vector_search`)、容差等待／熔斷毫秒數 (`jit_vector_timeout_ms: 3000 ms`)。
    4. **空間指紋游標同步 (`module:space` Cursor Sync)**：
       - 綁定空間：`knowledge_space`、快照世代對齊：`acked_generation / head_generation`、同步狀態（`In Sync` / `Pending Diff`）、最後掃描耗時。
- **[P00:DR-05] 向量建置周邊細節補強（`pre_warm` 守門與超長 Docstring 截斷）**：
  - **決策**：
    - `KnowledgeEngine.pre_warm()` 先檢查 `self.config.enable_vector_search`，若為 `False` 則不載入向量亦不初始化 `EmbeddingService`。
    - `EmbeddingService` 組裝符號嵌入文本時，對 `symbol.docstring` 施加合理字元上限截斷（例如前 `1000` 字元），避免超長 Markdown 章節拖慢 ONNX Tokenization 卻因超過 512 tokens 上限而被無效丟棄。

---

## 3. 開放議題與確認紀錄

- **[已全數釐清確認]**：
  1. 恢復 `knowledge-db` 專屬背景 Worker (`knowledge-db-worker`) 負責兩階段解析與微批次向量自癒（檔案監聽維持由 `space-watcher` 負責）：**已確認**。
  2. 有 Worker 環境下於背景自動下載遺失之向量模型並建置向量，無 Server 環境維持原樣：**已確認**。
  3. 新增 `is_worker_busy() -> int` 回傳**已運行毫秒數 (`ms`)**（`0` 代表空閒），搭配 Config 參數 `jit_vector_timeout_ms`（預設 `3000`）動態剩餘等待與超時降級提示 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`：**已確認**。
  4. 聚焦強化 `knowledge-db status` 指令之直白度與詳盡指標：**已確認**。

