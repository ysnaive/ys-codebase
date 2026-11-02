# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：`knowledge-db` 功能細節優化（常駐背景 Worker、向量模型自動下載、忙碌毫秒探針與容差降級、`status` 詳盡觀測）  
> 建立日期：2026-11-02  
> 所屬主計畫：`2026_11_02_0339_module_space_feasibility_research`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 專屬常駐 `KnowledgeDBServiceWorker` (`knowledge-db-worker`) 與兩階段背景管線 | 1. 於 `ys_codebase/source/knowledge-db/contributes/server.json` 宣告 `knowledge-db-worker` (`KnowledgeDBServiceWorker`)，不啟動任何 `watchdog` 監聽器（檔案監聽 100% 由 `space-watcher` 負責）。<br/>2. 當 `space-watcher` 發出 `on_space_changed(space_id="knowledge_space")` 時，`hook.space.py` 若偵測到 Worker 運行中，僅以 O(1) Event 喚醒 Worker，不阻塞 `space-watcher`。<br/>3. Worker 執行兩階段背景循環：**Stage 1 (Fast Path)** 立即消費 `space` Diff 更新 `unified.index.bin.gz` 與 `unified.graph.bin.gz` 並呼叫 `ack_diff()`；**Stage 2 (Slow Path)** 比對 `unified_index.symbols` 與 `vector_index.doc_ids` 差集（剔除已刪符號、找出缺漏向量 ID），按 `vector_batch_size`（預設 `32`）微批次計算並持久化 `unified.vectors.bin.gz`，直到向量覆蓋率達 100%。 | P0 | [P00:DR-01] |
| **FR-02** | 常駐 Worker 背景自動下載向量模型 | 1. 當 `is_worker_active()` 為 `True` 且 `config.enable_vector_search=True` 時，若 `embedding_service.is_model_downloaded()` 為 `False`，由 `KnowledgeDBServiceWorker` 於背景自動執行 `embedding_service.download_model()`，下載完成後無縫銜接 Stage 2 微批次向量建置。<br/>2. 在常駐 Worker 運行期間，前台 `search()` 若遇到模型尚未下載完畢或向量建置中，平順降級純 BM25，**不向 `stderr` 輸出 `[GUARD]` 阻斷警告**。<br/>3. 當無 `server` / Worker 未運行時，維持原樣（前台不自動下載模型，並向 `stderr` 輸出 `[GUARD]` 詢問提示）。 | P0 | [P00:DR-02] |
| **FR-03** | `is_worker_busy() -> int`（已運行毫秒數）探針與 `jit_vector_timeout_ms` 動態剩餘容差降級 | 1. `KnowledgeDBConfig` 提供毫秒設定參數 `jit_vector_timeout_ms: int = 3000`（支援於 `config.json` 設定，並向下相容 `jit_vector_timeout_seconds` 自動換算）。<br/>2. 新增公開探針 `engine.is_worker_busy() -> int`（及 `service.get_worker_busy_ms(indices_dir)`）：回傳後台 Worker 當前連續忙碌之已運行毫秒數 `elapsed_ms`（`0` 代表空閒，`> 0` 代表已忙碌 `ms`）。<br/>3. 有 Worker 時，`search()` 讀取 `timeout_ms = config.jit_vector_timeout_ms`：若 `elapsed_ms == 0` 直接使用混合檢索；若 `elapsed_ms >= timeout_ms` 則等待 `0ms` 立即降級純 BM25 並向 `stderr` 輸出 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`；若 `0 < elapsed_ms < timeout_ms` 則最多等待剩餘 `timeout_ms - elapsed_ms` 毫秒，若期間內完成則熱重載向量執行 `hybrid_rrf`，若屆滿仍忙碌則降級純 BM25 並輸出相同提示。<br/>4. 無 Worker 時，`jit_vector_timeout_ms` 作為前台 JIT 10-symbol 探針熔斷上限，且單次超時不永久鎖死後續查詢。 | P0 | [P00:DR-03] |
| **FR-04** | `knowledge-db status` 直白詳盡化觀測升級 | 升級 `engine.status()` 與 `scripts/cli.py:status()`（含終端人類可讀排版與 `--json`），清晰展示：<br/>1. **後台服務狀態**：Worker `Running/Stopped`、`is_worker_busy` 毫秒數 (`0 ms` / `已運行 X ms`)、當前階段 (`phase`) 與進度 (`progress`)。<br/>2. **三大索引細部指標**：BM25 倒排（狀態、符號數、詞條數、檔案大小、更新時間）、Call Graph 圖譜（狀態、節點數、呼叫邊數、檔案大小）、Vector 向量（狀態、`embedded / total` 數量、覆蓋率 `%`、待補差集數、維度、檔案大小）。<br/>3. **檢索模式與模型組態**：當前生效檢索模式 (`hybrid_rrf` 或 `lexical_bm25` + 降級原因)、模型名稱與下載狀態、`enable_vector_search`、`jit_vector_timeout_ms`、`vector_batch_size`、`max_threads`。<br/>4. **空間指紋同步狀態**：`knowledge_space` 之 `acked_generation / head_generation`、`in_sync` 狀態與註冊解析器清單。 | P0 | [P00:DR-04] |
| **FR-05** | `pre_warm()` 守門與嵌入文本 Docstring 截斷優化 | 1. `KnowledgeEngine.pre_warm()` 於 `config.enable_vector_search=False` 時跳過向量載入與 `EmbeddingService` 初始化。<br/>2. `EmbeddingService` 組裝符號嵌入文本時，將 `symbol.docstring` 截斷至合理上限（預設 `1000` 字元），避免超長 Markdown 拖慢 ONNX 分詞。 | P1 | [P00:DR-05] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 後台 Worker 進程於忙碌期間意外被強制終止 (`SIGKILL`)，遺留 `.kdb_worker_state.json` 顯示 `busy: true` | `is_worker_busy()` 讀取狀態檔時同步檢查 `is_worker_active("knowledge-db", "knowledge-db-worker")` 與 `pid` 存活狀態；若 Worker 未在線或 `pid` 已死亡，立即視為空閒回傳 `0` 並清理陳舊狀態檔，絕不造成前台假性等待。 |
| **EC-02** | Stage 2 微批次計算向量中途，使用者又修改了程式碼觸發新的 `on_space_changed` | Worker 每完成一個微批次（32 個符號）即檢查 `_wake_event` 或 `space` 待消費 Diff；若有新 Diff 立即優先插隊執行 Stage 1 更新 AST/BM25/Graph，再基於最新 `unified_index.symbols` 繼續 Stage 2 微批次補齊。 |
| **EC-03** | 後台執行模型下載或大型全量向量建置已耗時超過 `jit_vector_timeout_ms`（如已運行 `4500` ms > `3000` ms）時前台發起 `search()` | `elapsed_ms (4500) >= timeout_ms (3000)`，前台等待 `0ms` 瞬時降級純 BM25 並輸出提示，避免每次搜尋都白等 3 秒。 |
| **EC-04** | 後台已忙碌 `2200` ms（`timeout_ms = 3000`），前台發起 `search()` 後後台在第 `2600` ms 完成向量寫盤並轉為空閒 | 前台計算剩餘容差 `remain_ms = 800 ms`，等待約 `400 ms` 後偵測到 `is_worker_busy() == 0`，立即熱重載最新 `unified.vectors.bin.gz` 並以 `hybrid_rrf` 返回混合檢索結果，不降級。 |
| **EC-05** | 常駐 Worker 背景自動下載模型時遭遇網路斷線或 HuggingFace 下載失敗 | Worker 捕獲例外記錄日誌、清除忙碌標記並設定冷卻退避時間（例如 60 秒內不重複重試下載），防止無窮緊密迴圈佔滿 CPU/網路。 |
| **EC-06** | `config.json` 使用舊版 `jit_vector_timeout_seconds`（如 `5.0`）或直接設定 `jit_vector_timeout_ms`（如 `1500`） | `KnowledgeDBConfig.from_dict()` 優先讀取 `jit_vector_timeout_ms`；若僅提供 `jit_vector_timeout_seconds` 則自動轉換為 `int(float(val) * 1000)`，確保 100% 向下相容。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 響應延遲 | 當 `is_worker_busy() >= jit_vector_timeout_ms` 時，前台 `search()` 降級決策額外延遲 `< 5 ms`（0ms 等待）。 |
| **NFR-02** | 職責正交與零重複監聽 | `knowledge-db` 嚴禁引入 `watchdog` 或檔案輪詢器；100% 透過 `module:space` 事件與快照差集驅動。 |
| **NFR-03** | 跨平台原子性 | Worker 狀態檔 `.kdb_worker_state.json` 與向量索引 `unified.vectors.bin.gz` 寫入皆採暫存檔 + `os.replace` 原子替換，避免讀寫撕裂。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `module:server` 的 `BaseServiceWorker.start()` 會在獨立 daemon thread 中呼叫 `run(self._stop_event)`；`on_stop()` 則在停止時觸發。`KnowledgeDBServiceWorker` 必須透過 `stop_event.is_set()` 隨時中斷微批次迴圈並在 `finally` 中清除 `.kdb_worker_state.json`。
- **`[!NOTE]`** 在同行程（In-process，如 `hook.server.py` 預熱引擎與 Worker 同在一個 프로세스或測試中）與跨行程（CLI 子進程呼叫 `knowledge-db search` / `status`）兩種場景下，`is_worker_busy()` 都必須能準確讀到毫秒數，因此需結合「同行程記憶體時間戳 + 跨行程 `indices/.kdb_worker_state.json`」。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[space-watcher (module:space)]
       │ (檔案變更 -> 更新 YFP2 快照 -> dispatch_hook("on_space_changed"))
       ▼
[scripts/hook.space.py]
       ├─► 若 KnowledgeDBServiceWorker 在線 ──► worker.notify_space_changed() [O(1) 非阻塞喚醒]
       └─► 若不在 Worker 進程內 ──────────────► engine.sync_from_space_diff() [僅輕量同步]

[KnowledgeDBServiceWorker (knowledge-db-worker)]
       │
       ├─► Stage 1 (Fast Path):
       │     標記 busy(phase="indexing_ast_bm25")
       │     consume_diff("knowledge-db") -> 更新 unified.index.bin.gz + unified.graph.bin.gz -> ack_diff()
       │
       ├─► Auto Model Check (when enable_vector_search=True):
       │     若 !is_model_downloaded() 且未處於下載冷卻期:
       │     標記 busy(phase="downloading_model") -> embedding_service.download_model()
       │
       └─► Stage 2 (Slow Path — Micro-batch Vector Self-Healing):
             比對 missing_ids = list(unified_index.symbols.keys() - set(vector_index.doc_ids))
             及 stale_ids = list(set(vector_index.doc_ids) - unified_index.symbols.keys())
             標記 busy(phase="embedding_vectors", progress="{done}/{total}")
             每批 32 符號計算 embedding -> 合併並原子寫入 unified.vectors.bin.gz
             全部完成 -> 清除 busy 標記 (elapsed_ms = 0) 並 set _idle_event

[Foreground / CLI search()]
       │
       ├─► elapsed_ms = engine.is_worker_busy()
       ├─► elapsed_ms == 0 ──────────────────────────► 熱重載最新向量 -> hybrid_rrf
       ├─► elapsed_ms >= jit_vector_timeout_ms ──────► 等待 0ms -> 立即降級 BM25 + stderr 提示
       └─► 0 < elapsed_ms < jit_vector_timeout_ms ───► 最多等待 (timeout_ms - elapsed_ms) ms:
                                                         ├─ 期間內變為 0 -> 熱重載向量 -> hybrid_rrf
                                                         └─ 超時仍忙碌   -> 降級 BM25 + stderr 提示
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/knowledge-db/contributes/server.json` | New | 註冊 `knowledge-db-worker` (`service.py:KnowledgeDBServiceWorker`) 至 `module:server` |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | New | 實作 `KnowledgeDBServiceWorker`（兩階段管線、背景模型自動下載、微批次向量差集自癒）與忙碌狀態讀寫探針 (`read_worker_state`、`get_worker_busy_ms`、`wait_until_worker_idle`) |
| `ys_codebase/source/knowledge-db/knowledge_db/config.py` | Modify | 新增 `jit_vector_timeout_ms: int = 3000`（向下相容 `jit_vector_timeout_seconds`）與 `vector_batch_size: int = 32` |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | Docstring 嵌入截斷保護（上限 `1000` 字元）與微批次符號嵌入輔助方法 `embed_symbols_batch()` |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 實作 `is_worker_busy() -> int`、`sync_vectors_microbatch()`、`search()` 動態剩餘容差等待與 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]` 提示、`pre_warm()` 守門、以及 `status()` 詳盡結構化診斷資訊 |
| `ys_codebase/source/knowledge-db/scripts/hook.space.py` | Modify | 優先喚醒在線之 `KnowledgeDBServiceWorker`，不在線時才走同步消費 |
| `ys_codebase/source/knowledge-db/scripts/hook.server.py` | Modify | 整合 `KnowledgeEngine` 預熱與 `KnowledgeDBServiceWorker` 協同 |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | 全面升級 `knowledge-db status` 終端機分區直白輸出與 `--json` 欄位 |
| `ys_codebase/source/knowledge-db/tests/test_engine.py` | Modify | 新增 `jit_vector_timeout_ms`、`status` 詳盡指標與 Docstring 截斷之正負向單元測試 |
| `ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | 新增 `is_worker_busy()` 毫秒探針、`jit_vector_timeout_ms` 動態剩餘等待與 0ms 瞬時降級、`KnowledgeDBServiceWorker` 兩階段微批次向量自癒與背景自動模型下載之正負向單元測試 |
| `ys_codebase/source/knowledge-db/tests/test_space.py` | Modify | 對齊 `configurable/config.project.json` 與 `KnowledgeDBConfig` 之 `jit_vector_timeout_ms: int = 3000` 預設契約斷言 |
| `ys_codebase/source/knowledge-db/configurable/config.project.json` | Modify | 更新預設組態為 `"jit_vector_timeout_ms": 3000` 與 `"vector_batch_size": 32` |
| `ys_codebase/source/knowledge-db/README.md` | Modify | 同步更新 `jit_vector_timeout_ms`、`vector_batch_size` 與 `knowledge-db-worker` 架構說明 |
| `docs/knowledge-db/README.md` | Modify | 同步更新 `jit_vector_timeout_ms`、`is_worker_busy()`、`knowledge-db-worker` 與 `status` 說明 |
| `docs/knowledge-db/incremental_hot_reload.md` | Modify | 同步更新 `space-watcher` + `knowledge-db-worker` 兩階段微批次向量自癒與容差降級架構圖 |
| `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 `[DN-10]` 兩階段微批次向量自癒與 `is_worker_busy` 動態剩餘容差熔斷設計筆記 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 忙碌狀態探針採「同行程單調時鐘 + 跨行程 `.kdb_worker_state.json` 狀態檔」雙軌設計**：
  - 為了讓 CLI 子進程與同進程呼叫都能在 $< 1\text{ ms}$ 內取得精確的已運行毫秒數 `elapsed_ms`（同時供 `knowledge-db status` 讀取當前階段 `phase` 與進度 `progress`），Worker 在開始一輪連續任務（Stage 1 / 模型下載 / Stage 2）時設定 `busy_start_ts = time.time()` 並寫入 `indices/.kdb_worker_state.json`。在同一次連續忙碌期間，子階段切換（如從 Stage 1 進入 Stage 2 或推進微批次進度 `32/320`）僅更新 `phase` 與 `progress`，**保持 `start_ts` 不變**，確保 `is_worker_busy()` 回傳的是「本次後台更新已連續運行的總毫秒數」。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/knowledge-db/knowledge_db/config.py
@dataclass
class KnowledgeDBConfig:
    max_threads: int = 4
    index_batch_size: int = 50
    vector_batch_size: int = 32
    default_top_k: int = 5
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    enable_vector_search: bool = True
    vector_model_name: str = "BAAI/bge-small-zh-v1.5"
    rrf_k: int = 60
    jit_vector_timeout_ms: int = 3000

    @property
    def jit_vector_timeout_seconds(self) -> float: ...


# ys_codebase/source/knowledge-db/knowledge_db/service.py
class KnowledgeDBServiceWorker(BaseServiceWorker):
    def __init__(self, module_id: str, service_id: str, config: Optional[Dict[str, Any]] = None) -> None: ...
    def on_start(self) -> None: ...
    def run(self, stop_event: threading.Event) -> None: ...
    def on_stop(self) -> None: ...
    def notify_space_changed(self) -> None: ...

def get_active_worker_instance() -> Optional[KnowledgeDBServiceWorker]: ...
def read_worker_state(indices_dir: Path) -> Dict[str, Any]: ...
def get_worker_busy_ms(indices_dir: Path) -> int: ...
def wait_until_worker_idle(indices_dir: Path, timeout_ms: int) -> bool: ...


# ys_codebase/source/knowledge-db/knowledge_db/engine.py
class KnowledgeEngine:
    def is_worker_busy(self) -> int: ...
    def sync_vector_deficit_step(
        self,
        batch_size: int = 32,
        stop_event: Optional[threading.Event] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, int]: ...
    def status(self) -> Dict[str, Any]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `is_worker_busy() -> int`：保證絕不拋出未處理之 I/O 或 JSON 解析例外；若狀態檔不存在、損毀或對應 Worker 未存活，一律安全回傳 `0`。
  - 當 `search()` 因後台 Worker 忙碌超時而降級時，必定透過 `sys.stderr.write("[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]\n")` 輸出明確提示，並正常回傳 BM25 檢索結果。
- **階段決策紀錄**：`[P03:DR-01]` `KnowledgeDBConfig` 以 `jit_vector_timeout_ms: int = 3000` 為主屬性，並保留 `@property def jit_vector_timeout_seconds(self) -> float` 唯讀計算屬性，確保外部或既有程式碼零破壞相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-06 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束（零 `watchdog` 重複引入、零跨層污染）
- **靈魂拷問與防護解法**：
  1. **問**：若 `unified.vectors.bin.gz` 在微批次更新過程中，前台 `search()` 剛好讀取磁碟上的向量檔，會不會讀到寫入一半的損毀檔案？
     - **解**：`save_vectors()` 強制先寫入同目錄下的 `.unified.vectors.bin.gz.tmp.<pid>.<tid>` 暫存檔，完成 `gzip` 壓縮與 flush 後再透過 `os.replace()` 原子覆蓋目標檔；且僅在整個微批次向量計算完成、寫入磁碟並釋放忙碌標記後，前台才會在 `is_worker_busy() == 0` 時熱重載。
  2. **問**：若某個專案有 1,500 個符號，微批次（每批 32 個）更新期間，Worker 的 `start_ts` 何時重置？
     - **解**：在同一次連續背景同步週期（從開始處理 Diff / 檢查向量差集，到所有缺漏向量全部補齊為止）中，`_busy_start_ts` 維持首次進入忙碌時的時間戳不重置！僅在所有待補齊向量 `remaining == 0`（真正進入空閒等待下一次事件）時才清除忙碌標記。這樣當一個長任務已經跑了 4 秒時，`is_worker_busy()` 會如實回傳 `4000+` ms，讓前台 `search()` 實現真正的 `0ms` 瞬時降級，不會因為批次切換而誤以為剛開始忙碌又白等 3 秒。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | Modify | 更新 `knowledge-db-worker`、`jit_vector_timeout_ms`、`is_worker_busy()` 與 `status` 輸出範例 |
| **專題手冊** | `docs/knowledge-db/incremental_hot_reload.md` | Modify | 更新兩階段微批次向量自癒與動態剩餘容差降級流程 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 新增 `[DN-KDB-06]` 記錄兩階段背景 Worker 與忙碌毫秒探針容差機制 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `config.py`、`service.py`、`engine.py`、`cli.py` Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄 `sub_03` 變更摘要 |

- **決策定稿**：**[P04:DR-01]** 鎖定 `P01-05_auto.md` 規格，準備執行 `Pre-Code Analyze Gate` 與實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新 `knowledge_db/config.py`（`jit_vector_timeout_ms: int = 3000`、`vector_batch_size: int = 32` 及向下相容解析）與 `knowledge_db/embedding.py`（Docstring 截斷與批次嵌入輔助）。
- [x] **TASK-02**：建立 `contributes/server.json` 與 `knowledge_db/service.py`（`KnowledgeDBServiceWorker` 兩階段背景同步、自動下載模型、微批次向量差集自癒、跨行程/同行程忙碌毫秒狀態管理），並更新 `scripts/hook.space.py` 與 `scripts/hook.server.py`。
- [x] **TASK-03**：更新 `knowledge_db/engine.py`（`is_worker_busy() -> int`、`sync_vector_deficit_step()`、`search()` 動態剩餘容差等待與 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]` 提示、`pre_warm()` 守門、`status()` 結構化詳盡指標）與 `scripts/cli.py`（直白詳盡之 `knowledge-db status` 輸出）。
- [x] **TASK-04**：於 `tests/test_engine.py`、`tests/test_service_worker.py` 與 `tests/test_space.py` 擴充單元與邊界測試（涵蓋 `FR-01`~`FR-05` 與 `EC-01`~`EC-06`），執行 `dev check knowledge-db`、`dev test knowledge-db -q` 與 `install space@build knowledge-db@build --force` 驗證。
- [x] **TASK-DOC**：同步更新模組內 `README.md`、`docs/knowledge-db/` 手冊與微觀代碼 Docstrings。

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
