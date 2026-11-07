# 技術路線圖：知識庫向量模型離線守門與常駐服務非阻塞降級治理架構 (Roadmap)

> 主題：知識庫向量模型離線守門與常駐服務非阻塞降級治理架構 (`kdb_vector_model_offline_guard_and_nonblocking_worker`)
> 歸檔日期：2026-11-06
> 狀態：Ready
> 目標範疇：`knowledge-db` (`service` / `embedding` / `pipeline` / `hybrid`) 與 `server` (`WarmWorker` 常駐背景服務協同)
> 前置解鎖條件：無（已完整定位死鎖與阻塞根因，隨時可透過 `roadmap promote` 晉升立項修復）
> 模型：Unknown
> 模板版本：v1.1

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **背景服務越權自動下載違反離線探針先行契約**：當下游專案維持預設啟用向量檢索（`enable_vector_search=True`）但尚未顯式執行模型下載（`knowledge-db model download`）時，原本單機模式之設計契約（`[DN-03]` 與 Pre-flight 指引）明定「本地 `.onnx` 權重探針先行、若未下載則絕不主動發起網路連線、立即降級純 BM25 並輸出 `[GUARD]` 由開發者決策下載或關閉」。然而當常駐 `server` 啟動並拉起 `KnowledgeDBServiceWorker` 時，背景服務卻強制將全域單例之 `suppress_guard_prompt` 設為 `True` 靜默屏蔽 `[GUARD]` 提示，並在未獲授權下於背景迴圈內自動觸發 ~130MB 遠端模型同步下載（失敗時每 60 秒重複嘗試）。
  - **同步網路下載長時間獨佔初始化鎖（`_init_lock`）引發 `WarmWorker` 主執行緒與全系統派發死鎖**：背景執行緒執行 `download_model()` 時全程持有進程級單例 `EmbeddingService._init_lock`，且在遠端權重下載與 ONNX Runtime 初始化完成前，初始化完成旗標（`_init_attempted`）維持 `False`（若下載中途 `.onnx` 檔案先落盤而推論實例尚未就緒，本地探針亦會提前轉為真值）。此時任何經由 `server` 派發至 `WarmWorker` 主執行緒的前台指令（如 `search`、`index`、`status`、`model status`），只要在 JIT 索引檢查或向量可用性探測中觸及 `EmbeddingService.is_available` / `dimension` $\to$ `_ensure_model()`，即因阻塞式等待 `with self._init_lock:` 而被無限期卡死；由於 `MasterSupervisor._dispatch_lock` 與 `WarmWorker._task_lock` 採單工序列化派發，單一任務卡死將連帶凍結後續所有發往 `server` 的跨模組 CLI 指令（直至 120 秒派發逾時）。
  - **複合檢索可用性短路順序反置與前台容差等待疊加**：`HybridSearchEngine.is_vector_available` 先評估會觸發模型載入鎖的 `embedding_service.is_available`，而非先以 O(1) 檢查記憶體向量索引是否已具備有效向量（`len(vector_index.doc_ids) > 0`）；同時 `IndexingPipeline` 在進入背景忙碌容差判定前先執行 `_ensure_jit_index_ready(require_vectors=True)`，導致前台查詢在進入毫秒級降級判定前即已撞上模型初始化鎖，或於背景下載初期白白消耗完整 `jit_vector_timeout_ms`（預設 3000ms）等待視窗。
  - **第三方下載進度流污染與停機阻塞**：背景執行緒呼叫第三方模型庫下載時未強制關閉 `tqdm` / Hugging Face 進度條輸出，導致背景 `stderr` 串流於前台任務執行期間混入 `DebouncedIOStreamer`；且同步網路 I/O 無法響應 `_stop_event`，造成 `server stop` / `reload` 時 Worker 執行緒退出延遲。
- **長期願景與目標定位**：
  - 確立「向量模型顯式供給（Explicit Model Provisioning）」與「常駐檢索絕對非阻塞降級（Non-Blocking Retrieval Degradation）」之雙重架構邊界：拔除背景服務未授權的隱式外網模型下載行為，統一單機與常駐模式下之離線探針與 `[GUARD]` 決策體驗，並從鎖機制、評估短路順序與服務生命週期三層面保證常駐 `WarmWorker` 主執行緒在任何背景負載或模型缺失狀態下均能以 $O(1)$ 時間瞬時降級至純 BM25 檢索，徹底根除 `server` 派發卡死風險。
- **範疇與邊界約束**：
  - 涵蓋 `module:knowledge-db` 之背景服務調度契約（`service`）、向量推論服務鎖與環境變數隔離（`embedding`）、檢索管線與複合引擎可用性短路判定（`pipeline` / `hybrid`），以及對應之系統設計手冊（`docs/knowledge-db/`）與回歸測試；對外 CLI 指令與公開 SDK 簽名維持 100% 向下相容。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **顯式模型供給與零隱式外網連線不變量（Explicit Provisioning & Zero Implicit Network I/O）**：向量模型權重（~130MB）僅能由開發者或經授權之 Agent 透過顯式指令（`knowledge-db model download`）觸發下載；不論處於單機冷啟動或 `server` 常駐背景服務模式，只要本地快取未探測到完整模型權重，系統一律禁止在背景或前台私自發起遠端下載請求。
  - **前台派發執行緒零阻塞鎖探測不變量（Non-Blocking Foreground Lock Probing）**：前台檢索、狀態查詢與熱修補管線在探測或按需初始化模型實例時，嚴禁對可能正在執行耗時 I/O 的模型初始化鎖進行無限期阻塞等待；若模型鎖正被佔用或模型尚未就緒，必須立即返回不可用並無縫降級為純 BM25 模式。
  - **O(1) 索引就緒度優先短路不變量（Index-Readiness Short-Circuit First）**：判定向量檢索是否可用時，必須優先以零鎖開銷之 O(1) 記憶體檢查確認向量索引已載入且包含有效向量項目（`doc_ids` 非空）及本地模型檔案已存在，最後才探測推論服務實例狀態。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **背景服務 Stage 2 前置守門與 `[GUARD]` 作用域隔離**：`KnowledgeDBServiceWorker` 於完成 Stage 1（AST + BM25 增量同步）後，進入 Stage 2 前先檢查本地模型是否已下載；若未下載則直接結束本輪同步（不標記 `busy`、不呼叫 `download_model()`），僅在本地模型已就緒且存在向量差集時才執行微批次向量補齊。同時將 `suppress_guard_prompt` 收斂為背景執行緒局部（或傳參）控制，避免背景 Worker 常駐時永久屏蔽前台 CLI 的 `[GUARD]` 決策提示。
  - **非阻塞模型初始化鎖與第三方進度流靜默隔離**：於 `EmbeddingService._ensure_model()` 採用非阻塞鎖擷取（`acquire(blocking=False)`），一旦發現鎖被持有即刻快速退回 `False`；並在 `download_model()` 進入下載前預先標記進行中狀態、於 `finally` 確保異常狀態明確落盤，同時於 `_suppress_hf_warnings()` 強制注入 `HF_HUB_DISABLE_PROGRESS_BARS=1` 與 `TQDM_DISABLE=1`，杜絕第三方進度條污染常駐 IPC 串流。
  - **檢索管線與複合引擎短路順序對齊**：於 `HybridSearchEngine.is_vector_available` 將 `vector_index` 非空檢查置於 `embedding_service.is_available` 之前；並於 `IndexingPipeline` 確保當本地未下載模型或背景 Worker 忙碌時，`_ensure_jit_index_ready` 自動跳過向量同步與載入，消除進入容差判定前的冗餘模型觸發與無謂等待。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：無前置依賴阻塞，可隨時透過 `python yscb.py agents-workflow roadmap promote kdb_vector_model_offline_guard_and_nonblocking_worker` 晉升立項執行修復。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（移除背景隱式下載與 `[GUARD]` 作用域收斂）**：移除 `KnowledgeDBServiceWorker` 於模型缺失時之背景自動下載邏輯，對齊單機與常駐模式下之離線探針與 `[GUARD]` 提示行為，並同步更新 `docs/knowledge-db/`（`incremental_hot_reload.md` 與 `DESIGN_NOTES.md` `[DN-10]`）。
  2. **Stage 2（非阻塞鎖探測、O(1) 短路順序與進度條靜默加固）**：重構 `EmbeddingService._ensure_model()` 為非阻塞鎖擷取、補齊 `HF_HUB_DISABLE_PROGRESS_BARS=1` / `TQDM_DISABLE=1`，並調整 `HybridSearchEngine.is_vector_available` 與 `IndexingPipeline` 之短路評估順序。
  3. **Stage 3（併發壓力與離線降級回歸驗證）**：於 `test_service_worker.py` 更新並新增「啟用向量檢索但未下載模型 + 常駐 Worker 運行 + 併發執行前景 `search`/`status`/`model status`」之非阻塞瞬時降級測試，確保零鎖等待與 `0 ResourceWarning`。
