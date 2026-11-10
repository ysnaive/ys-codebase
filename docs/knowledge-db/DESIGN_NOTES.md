---
target: "Knowledge-DB"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb://source/knowledge-db/knowledge_db/engine.py"
  - "yscb://source/knowledge-db/knowledge_db/pipeline.py"
  - "yscb://source/knowledge-db/knowledge_db/embedding.py"
  - "yscb://source/knowledge-db/knowledge_db/bundler.py"
  - "yscb://source/knowledge-db/knowledge_db/retrieval.py"
  - "yscb://source/knowledge-db/scripts/hook.file-space.py"
  - "yscb://source/knowledge-db/scripts/cli.py"
related_docs:
  - "./README.md"
  - "../file-space/DESIGN_NOTES.md"
  - "./architecture.md"
  - "./retrieval.md"
  - "./incremental_hot_reload.md"
  - "./call_graph_and_reference_index.md"
last_updated: "2026-11-05"
---

# knowledge-db 設計決策與工程妥協手冊 (Design Notes)

> 模組名稱：`knowledge-db`  
> 職責定位：記錄 `knowledge-db` 模組中屬於「維度 ⑤ 工程妥協與防坑」之非直覺設計、硬體/作業系統排程保護、快取競態規避與安全邊界。  
> 維護規範：所有維護者與 Agent 在修改相關底層邏輯前，**必須強制閱讀本文件**，避免因看似「簡化」的重構而破壞既有防坑約束。

---

## 登錄決策清單 (Decision Registry)

| 決策編號 | 標題 / 主題 (含歷史編號對照) | 影響檔案 | 風險等級 |
| :---: | :--- | :--- | :---: |
| **DN-01** | `storage.local://knowledge-db/` 與 `storage.local://file-space/` 儲存雙軌分離、跨進程鎖分離 (`cache://`) 及 Pickle 二進位安全邊界 *(原 DN-02 + DN-17.2)* | `engine.py`, `pipeline.py`, `retrieval.py`, `graph.py`, `embedding.py` | 🚨 CRITICAL |
| **DN-02** | ONNX 執行緒硬上限、時間片主動讓渡 (`sleep(0.005)`)、向量低壓縮寫盤 (`compresslevel=1`) 與多進程 AST 單次走訪 *(原 DN-13 + DN-06.3)* | `embedding.py`, `bundler.py`, `parsers/` | 🚨 CRITICAL |
| **DN-03** | JIT 10 符號動態探針熔斷、離線 `.onnx` 權重探針先行 (`[GUARD]`) 與 `--json` 純淨通道保護 *(原 DN-14 + DN-25.2)* | `pipeline.py`, `embedding.py`, `config.py`, `scripts/cli.py` | 🚨 CRITICAL |
| **DN-04** | 背景 `file-space-watcher` 零阻塞旁路、`hook.file-space.py` 免重掃與 `_GLOBAL_INDEX_CACHE` 微秒級 `mtime` 熱刷新 *(原 DN-21 + DN-23)* | `pipeline.py`, `scripts/hook.file-space.py` | ⚠️ WARNING |
| **DN-05** | `FileSpaceManager._include_cache` 空間路徑解析記憶化防退化 *(已收斂至 `module:file-space`，原 DN-24)* | `engine.py`, `file_space/manager.py` | ⚠️ WARNING |
| **DN-06** | 圖譜查詢輕量 JIT 解耦 (`require_vectors=False`)、差量修補對稱路徑剔除與零偽造向量鐵律 *(原 DN-26)* | `pipeline.py`, `retrieval.py`, `embedding.py` | 🚨 CRITICAL |
| **DN-07** | 冷啟動向量載入需求區隔 (`want_vectors` vs `can_use_vector`) 解除死鎖 | `pipeline.py`, `hybrid.py` | 🚨 CRITICAL |
| **DN-08** | 調用圖譜雙階入度邊保留 (`Identity Remap` + `TopologyLinker`) 與服務單一託管 | `graph.py`, `pipeline.py`, `hook.server.py`, `scripts/hook.file-space.py` | 🚨 CRITICAL |
| **DN-09** | 常駐背景修補並發互斥鎖 (`_index_lock`)、字典快照迭代與背景禁用 `ProcessPoolExecutor` (`allow_parallel=False`) | `pipeline.py`, `scripts/hook.file-space.py`, `retrieval.py`, `bundler.py` | 🚨 CRITICAL |
| **DN-10** | 兩階段背景 `KnowledgeDBServiceWorker` (`knowledge-db-worker`)、`is_worker_busy() -> int` 已運行毫秒探針與 `jit_vector_timeout_ms` 動態容差降級 | `service.py`, `pipeline.py`, `engine.py`, `embedding.py`, `config.py` | 🚨 CRITICAL |

---

## 詳細設計決策與防坑邊界

### [DN-01] `storage.local://knowledge-db/` 與 `storage.local://file-space/` 儲存雙軌分離、跨進程鎖分離 (`cache://`) 及 Pickle 二進位安全邊界 *(原 DN-02 + DN-17.2)*

- **背景與根因**：
  1. 早期 `get_cache_dir` 曾保留舊版候選路徑搜尋或 `Path.cwd() / ".cache"` 隱式降級兜底；且在導入 `module:file-space` 後，若 `KnowledgeEngine.storage_dir` 直接共用 `space_manager.storage_dir`（`storage.local://file-space/`），會導致知識庫索引與空間指紋快照混雜於同一目錄，`clean()` 時互相誤刪。此外，若將百 MB 級向量模型與持久索引存放於揮發性 `cache://`，於容器或 `tmpfs` 環境清空快取時將導致模型與索引全毀。
  2. 倒排索引 (`unified.index.bin.gz`)、調用圖譜 (`unified.graph.bin.gz`) 與向量索引 (`unified.vectors.bin.gz`) 為追求 $< 20\text{ ms}$ 的反序列化速度，採用了 Python `pickle` Protocol 5，而 `pickle.loads` 對不可信來源具有任意代碼執行風險。
- **工程妥協與解法**：
  1. **本機持久儲存零 Fallback、雙軌分離與鎖檔分離**：`file_space.FileSpaceManager` 固定解析 `file-space.storage://` (`storage.local://file-space/`) 儲存 `YFP2` 快照與消費者游標；`KnowledgeEngine.storage_dir` 獨立解析 `knowledge.storage://` (`storage.local://knowledge-db/`) 儲存模型權重 (`models/`)、AST bundles 與索引檔，而跨進程鎖檔 `.kdb_index.lock` 則於預設模式下分離至 `knowledge.cache://.kdb_index.lock` (`cache://knowledge-db/.kdb_index.lock`)（單元測試顯式注入自訂 `storage_dir` 時留駐於測試沙盒內隔離）；歷史 `.cache/knowledge-db/` 舊資產統一由 `scripts/migrations/1.2.1.x.py` 在版本晉升時自動冪等遷移，業務代碼維持 0 舊路徑 Fallback。
  2. **二進位與跨機傳輸職責分離**：`pickle` 二進位索引嚴格限定於本機受保護之 `storage.local://knowledge-db/indices/` 目錄讀寫（並透過 `core.vfs.write_bytes(atomic=True)` 原子替換）；凡涉及跨環境分享或外部導出（`index --export`），一律使用純 JSON Schema 之 `SemanticBundle` (`.bundle.json`)。

> [!CAUTION]
> **嚴禁將 `KnowledgeEngine.storage_dir` 指向 `space_manager.storage_dir`，嚴禁加入 `os.getcwd()` / `Path.cwd()` 或舊路徑 `.cache/` 執行期降級兜底，且嚴禁對外部匯入檔案 (`import_bundle`) 調用 `pickle.loads`！** 違反此邊界將造成跨模組索引誤刪、宿主目錄污染與反序列化安全漏洞。

---

### [DN-02] ONNX 執行緒硬上限、時間片主動讓渡 (`sleep(0.005)`)、向量低壓縮寫盤 (`compresslevel=1`) 與多進程 AST 單次走訪 *(原 DN-13 + DN-06.3)*

- **背景與根因**：
  在 200+ 檔案、數千個符號的全庫索引重建實機壓測中，曾觸發嚴重的系統級卡死與效能退化：
  1. `FastEmbed` 底層 ONNX Runtime 預設搶佔本機 100% 邏輯核心，連續推論數千個符號時造成 OS 排程器飢餓、Windows DPC 軟中斷逾時甚至硬體保護重開機。
  2. 浮點數陣列 (`float32` 向量矩陣) 具高熵值特性，若對 `VectorIndex.save_binary` 使用預設 `compresslevel=6` Gzip 壓縮，會耗費極高 CPU 時間卻僅獲得極低壓縮率收益。
  3. 多進程 `ProcessPoolExecutor` 若在每次任務內部重新實例化 `ParserRegistry`，會導致重複編譯 Tree-sitter `.scm` 語法查詢數百次；同時若 `extract_call_sites` 內部再次調用 `self.parse()`，會導致全庫 AST 被重複解析 3 遍。
- **工程妥協與解法**：
  1. **ONNX 執行緒硬上限**：在 `EmbeddingService._init_model` 初始化時，將預設 `"auto"` 執行緒數限制為 `min(2, max(1, cpu_count // 2))`，同步寫入 `OMP_NUM_THREADS`、`ONNXRUNTIME_INTRA_OP_NUM_THREADS` 並傳遞 `threads=max_threads` 予 ONNX Session。
  2. **批次切片與主動時間片讓渡**：`embed_texts` 以 `batch_size=64` 分批推論，每完成一批次強制調用 `time.sleep(0.005)`（5 毫秒），主動將 CPU 時間片讓渡予 OS 排程器與前台 UI。
  3. **向量快取 `compresslevel=1` 低壓縮高速寫盤**：`VectorIndex.save_binary` 與增量熱修補統一採用 `gzip.compress(..., compresslevel=1)`，消除浮點陣列高壓縮比之無效 CPU 燃燒，寫盤延遲降低 80%+。
  4. **Worker 進程級單例與 AST 單次走訪復用**：`SemanticBundler` 於檔案數 $\ge 10$ 且多核時啟用 `ProcessPoolExecutor`，透過頂層 `_get_worker_registry()` 維持進程內單例 `ParserRegistry`（每個 Worker 僅編譯 `.scm` 一次）；`extract_call_sites` 接收已提取之 `symbols` 實例，徹底根除二次 AST 解析。

> [!CAUTION]
> **嚴禁移除 `EmbeddingService.embed_texts` 批次迴圈內的 `time.sleep(0.005)`、嚴禁解除 ONNX 執行緒上限，且嚴禁將 `VectorIndex` 的 Gzip 壓縮等級調高至 6！** 這些看似微小的常數是防止大型專案索引建置時主機 CPU 100% 鎖死與硬體保護重啟的關鍵防線。

---

### [DN-03] JIT 10 符號動態探針熔斷、離線 `.onnx` 權重探針先行 (`[GUARD]`) 與 `--json` 純淨通道保護 *(原 DN-14 + DN-25.2)*

- **背景與根因**：
  1. 當開發者切換大型 Git 分支導致數百個符號同時變更時，若前台 `search` 的 JIT 熱修補直接對全數變更符號執行 CPU 向量推論，會導致 CLI 檢索卡頓數秒至數十秒。
  2. 在未下載向量模型或無外網環境下，`FastEmbed` 預設會向 Hugging Face Hub 發起未認證網路請求並拋出連線逾時或 Symlink 權限警告 (`WinError 1314`)，不僅阻塞檢索，其輸出的雜訊更會直接污染 `--json` 的 `stdout` 結構化串流，導致呼叫端 AI Agent 解析 JSON 失敗。
- **工程妥協與解法**：
  1. **JIT 10 符號動態探針與超時熔斷 (Dynamic Probe & Fuse)**：在 `hot_patch_unified_index` 中，當新增/修改符號數 $\le 10$ 時直接完成向量化；當 $> 10$ 個時，先以**首批 10 個符號實測推論耗時**並線性推估全量耗時。若預估總時長超過 `jit_vector_timeout_seconds`（預設 `5.0s`），立即觸發熔斷跳過剩餘向量推論，無縫退回純 BM25 模式。
  2. **本地 `.onnx` 權重探針先行 (Probe First)**：`EmbeddingService` 初始化前先以純本機檔案系統探測 `.onnx` 權重是否存在；若未下載則**絕不發起任何網路連線**，立即降級為純 BM25 檢索。
  3. **Agent 剛性防呆信號與 `stdout` 純淨隔離**：設定 `HF_HUB_DISABLE_SYMLINKS_WARNING=1` 屏蔽第三方庫警告；所有 JIT 重建進度、熔斷提示與模型缺失之 `[GUARD]` 阻斷指引（提示開發者執行 `model download` 或關閉 `enable_vector_search`）**100% 強制導向 `sys.stderr`**，確保 `--json` 模式下 `stdout` 永遠保持 100% 純淨 JSON。

> [!WARNING]
> **任何新增於檢索、掃描或熱修補管線中的狀態提示、進度條或降級警告，一律強制寫入 `sys.stderr`，絕對禁止在業務管線中使用預設 `print()` 輸出至 `sys.stdout`！** 否則將直接破壞 AI Agent 工具鏈的 `--json` 解析契約。

---

### [DN-04] 背景 `file-space-watcher` 零阻塞旁路、`hook.file-space.py` 免重掃與 `_GLOBAL_INDEX_CACHE` 微秒級 `mtime` 熱刷新 *(原 DN-21 + DN-23)*

- **背景與根因**：
  當 `server` 常駐模組託管 `FileSpaceWatcherServiceWorker` (`file-space-watcher`) 在背景執行 Watchdog 500ms 防抖監聽並觸發 `hook.file-space.py` 時，若前台 `IndexingPipeline.search()` 每次仍照常執行同步 `os.scandir` 與 `hot_patch_unified_index`，前台進程會與背景修補發生磁碟寫入與重算競態 (Race Condition)。同時，常駐 Worker 進程內若不感知磁碟快取檔案更新，會持續回傳舊的記憶體索引。
- **工程妥協與解法**：
  1. **`file_space.is_watcher_active()` 與 `hook.file-space.py` 免重掃協調**：當 `file-space-watcher` 常駐運行且無 `.watcher_dirty` 時，前台檢索管線透過 `file_space.is_watcher_active()` 0ms 直接旁路略過同步 `os.scandir` 掃描；而 `hook.file-space.py` 接收 `on_file_space_changed` 事件時，由於 `file-space-watcher` 剛完成 `YFP2` 快照更新，直接呼叫 `scanner.diff(..., auto_refresh=False)` 零重複掃描消費差量。
  2. **`_GLOBAL_INDEX_CACHE` 微秒級 `mtime` 熱刷新**：進程級全域快取 `_GLOBAL_INDEX_CACHE` 同時保存 `unified_index`、`graph_index`、`vector_index` 及其對應磁碟檔案之浮點數 `st_mtime`。每次查詢前以微秒級精度比對磁碟 `*.bin.gz` 的 `mtime`，一旦背景完成原子替換 (`core.vfs.write_bytes(atomic=True)`)，記憶體立即原地熱重載最新索引。

> [!CAUTION]
> **嚴禁在 `hook.file-space.py` 的 `on_file_space_changed` 事件回呼中開啟 `auto_refresh=True` 造成重複全目錄 `scandir`，且嚴禁破壞 `_GLOBAL_INDEX_CACHE` 的 `st_mtime` 比對熱重載機制！**

---

### [DN-05] `FileSpaceManager._include_cache` 空間路徑解析記憶化防退化 *(原 DN-24)*

- **背景與根因**：
  在 `KnowledgeEngine.status()` 或多空間歸屬判定 (`_file_belongs_to_space`) 中，系統需針對 `unified.meta.bin` 內的數百個檔案逐一比對所有空間。若每次呼叫 `FileSpaceManager.resolve_space_include(space_name)` 皆重新調用 `core.contributes.get("knowledge-db")` 與 `Path.resolve()`，在 300 檔 $\times$ 3 空間規模下會觸發超過 2,600 次高成本磁碟系統呼叫，導致 `status` 耗時暴增至 $7.1\text{s}$。
- **工程妥協與解法**：
  - 在 `FileSpaceManager` 實例內部引入 `self._include_cache: Dict[Tuple[str, tuple], List[Path]] = {}`，以 `(space_name, tuple(space.include))` 為快取鍵。首次解析出實體絕對路徑清單後即駐留記憶體，使 `status` 總耗時由 $7.1\text{s}$ 驟降至 $0.14\text{s}$（提速 50 倍以上）。

> [!WARNING]
> **切勿在迴圈內部重複實例化 `FileSpaceManager()` 或繞過 `self._include_cache` 直接解析語意 URI！** 若動態更新了空間配置（如呼叫 `register_space`），必須同步清空 `_include_cache` 以維持快取一致性。

---

### [DN-06] 圖譜查詢輕量 JIT 解耦 (`require_vectors=False`)、差量修補對稱路徑剔除與零偽造向量鐵律 *(原 DN-26)*

- **背景與根因**：
  1. `callers`、`callees`、`impact` 本質為純靜態 AST 語法樹與圖論拓撲查詢，早期因共用 `search()` 預設入口，導致查詢調用關係時被動觸發重量級 FastEmbed ONNX 模型載入與向量 JIT 推論。
  2. 在沙盒測試或跨目錄解析基準下，符號內部記錄之相對路徑（如 `src/foo.py`）與磁碟掃描傳入之絕對路徑（如 `/tmp/.../src/foo.py`）格式不完全等價，若僅做單向字串相等比對，會導致檔案刪除或清空時舊符號殘留於倒排索引中（幽靈符號）。
  3. 當向量模型未載入或推論失敗時，若為求表面陣列維度匹配而回傳隨機或全零 dummy 向量，將嚴重扭曲餘弦相似度排名，違反專案「零淺層敷衍」核心原則。
- **工程妥協與解法**：
  1. **圖譜查詢輕量 JIT 解耦**：`IndexingPipeline` 抽離 `_ensure_jit_index_ready(require_vectors=False)`；執行 `act_callers`、`act_callees`、`act_impact` 時強制傳入 `require_vectors=False`，僅確保倒排索引與 `CallGraphIndex` 就緒並完全跳過向量推論，將拓撲分析延遲壓制於 $< 30\text{ ms}$。
  2. **對稱式路徑匹配剔除**：`InvertedIndex.patch_incremental` 與 `IndexingPipeline` 實作正規化路徑與後綴端點之對稱式匹配 (`_paths_match`)，確保無論傳入相對或絕對路徑，`deleted` 與 `modified` 檔案之舊 Postings、符號池記錄與圖譜邊皆被 100% 乾淨拔除。
  3. **零偽造向量與全域快取徹底清理**：`EmbeddingService.embed_texts` 在非測試 mock 模式且模型不可用時，剛性回傳 `np.empty((0, dim), dtype=np.float32)` 空矩陣，嚴禁生成偽造向量；`clean()` 除刪除磁碟檔案外，強制清理 `unified.vectors.bin.gz` 並重置 `_GLOBAL_INDEX_CACHE` 所有記憶體指標與 `mtime`。

> [!CAUTION]
> **嚴禁在 `EmbeddingService` 推論失敗時回傳隨機數或零向量充當 Fallback，且嚴禁在圖譜拓撲指令 (`callers`/`callees`/`impact`) 中開啟 `require_vectors=True`！**

---

### [DN-07] 冷啟動向量載入需求區隔 (`want_vectors` vs `can_use_vector`) 解除死鎖

- **背景與根因**：
  在 `IndexingPipeline.search()` 中，早期邏輯於調用 `_ensure_jit_index_ready()` 前直接檢查 `can_use_vector = (... and self.hybrid_engine.is_vector_available)`。在冷啟動新進程中，磁碟上的向量快取尚未被載入，故 `is_vector_available` 恆為 `False`，導致傳入 `require_vectors=False`，進而永遠跳過磁碟向量載入，形成冷啟動向量搜尋死鎖。
- **工程妥協與解法**：
  區隔「預期載入需求 (`want_vectors`)」與「載入後可用判定 (`can_use_vector`)」：
  1. 呼叫 `_ensure_jit_index_ready(require_vectors=want_vectors)`，依組態與參數意圖觸發向量載入。
  2. 索引載入就緒後始評估 `can_use_vector = (want_vectors and self.hybrid_engine.is_vector_available)`。

---

### [DN-08] 調用圖譜雙階入度邊保留 (`Identity Remap` + `TopologyLinker`) 與服務單一託管

- **背景與根因**：
  1. 單一檔案增量熱修補時，若僅拔除修改檔案之舊符號並重鏈接該檔之 outgoing 邊，會導致外部未修改檔案指向該檔之 incoming edges 被誤刪丟失。直接調用 `TopologyLinker` 又因缺少外部檔案檔頭 imports 而丟棄裸函式調用。
  2. `hook.server.py` 早期私自建立並啟動 `_watcher_instance`，與 `server.ServiceManager` 託管之服務產生雙重監聽競態。
- **工程妥協與解法**：
  1. **雙階入度保留**：拔除舊符號前先透過 `CallGraphIndex.get_external_incoming_edges()` 備份入度邊；符號更新後執行 Stage 1 `Identity Remap`（依同檔案路徑與符號名稱直接對映）＋ Stage 2 `TopologyLinker` 跨檔消歧回退。
  2. **服務單一託管与事件解耦**：`hook.server.py` 僅保留 `pre_warm()`，背景檔案監聽 100% 委由 `module:file-space` 之 `file-space-watcher` 服務統一託管，並由 `scripts/hook.file-space.py` 訂閱 `on_file_space_changed` 事件驅動增量熱修補。

---

### [DN-09] 常駐背景修補並發互斥鎖 (`_index_lock`)、字典快照迭代與背景禁用 `ProcessPoolExecutor` (`allow_parallel=False`)

- **背景與根因**：
  1. 當常駐 `server` Worker 接收 `on_file_space_changed` 觸發 `hot_patch_unified_index()` 時，若與前台 IPC 查詢執行緒同時重入讀寫 `self._unified_index.symbols` 與 `self._unified_index.index`，會引發 `RuntimeError: dictionary changed size during iteration`。
  2. 一旦背景修補回退呼叫 `build_unified_index(force=True)`，若預設啟動 4-worker `ProcessPoolExecutor` 子進程池，在常駐 daemon 背景會衍生子進程風暴。
- **工程妥協與解法**：
  1. **管線與事件鉤子互斥防重入**：`IndexingPipeline` 設 `self._index_lock = threading.RLock()` 保護 `build_unified_index`、`hot_patch_unified_index` 與 `_ensure_jit_index_ready`；`scripts/hook.file-space.py` 內部亦設模組級 `_patch_lock` 確保背景事件序列執行。
  2. **序列化字典淺快照與背景禁用多進程**：`InvertedIndex.to_dict()` 對 `self.index.items()` 與 `self.symbols.items()` 統一採 `list(...)` 淺快照迭代；`bundle_union()` 與 `build_unified_index()` 增設 `allow_parallel: bool = True`，`hook.file-space.py` 回退重建時強制傳入 `allow_parallel=False`，杜絕常駐 daemon 在背景衍生 `ProcessPoolExecutor` 子進程池。

> [!CAUTION]
> **嚴禁在常駐背景事件 (`scripts/hook.file-space.py`) 中以 `allow_parallel=True` 呼叫全量索引重建，亦嚴禁移除 `_index_lock` 與 `to_dict()` 的 `list(...)` 快照保護！** 違反此防護將重新引發多執行緒字典迭代崩潰與子進程記憶體風暴。

---

### [DN-10] 兩階段背景 `KnowledgeDBServiceWorker` (`knowledge-db-worker`)、`is_worker_busy() -> int` 已運行毫秒探針與 `jit_vector_timeout_ms` 動態容差降級

- **背景與根因**：
  1. 若於 `on_file_space_changed` 事件回呼中同步執行全量或大批量 ONNX 向量嵌入，不僅會阻塞 `file-space-watcher` 事件執行緒，亦會導致缺失 `unified.vectors.bin.gz`（而游標已 `in_sync`）時無法在背景自動自癒補齊。
  2. 本地 FastEmbed 模型存放於系統快取，切換環境或清理快取後容易遺失；若每次皆須跳出 `[GUARD]` 警告要求 Agent 反問開發者確認下載，在已有常駐 Server Worker 的環境下會造成不必要的人工中斷。
  3. 當背景 Worker 正在執行長耗時任務（如初次全量向量化或背景下載模型）時，若前台每次搜尋皆固定死等完整超時時間（如 3000ms），將造成連續搜尋每次都被無謂延遲 3 秒。
- **工程妥協與解法**：
  1. **職責分離與兩階段背景同步 (`KnowledgeDBServiceWorker`)**：檔案系統 `watchdog` 監聽 100% 維持由 `file-space` 模組 (`file-space-watcher`) 單一負責；`knowledge-db` 註冊專屬 `KnowledgeDBServiceWorker` (`knowledge-db-worker`)。Stage 1 以 `skip_vectors=True` 秒級更新 AST/BM25/圖譜並推進游標；Stage 2 以微批次 (`vector_batch_size=32`，且將 `symbol.docstring` 截斷至 `1000` 字元防止超長 Token 拖慢 ONNX) 自動補齊缺失向量；若本地尚未下載模型權重，嚴禁背景私自聯網下載，立即以 `busy=False` 轉入 `DEGRADED_OFFLINE` 純 BM25 模式（模型下載統一由使用者顯式執行冷啟動 `yscb knowledge-db model download`）。
  2. **`is_worker_busy() -> int` 已運行毫秒探針與剩餘容差計算**：`is_worker_busy()` 回傳 `0`（空閒）或已連續忙碌毫秒數 `elapsed_ms > 0`（具備陳舊 PID 存活校驗）。前台 `search()` 根據 `config.jit_vector_timeout_ms`（預設 `3000` ms）：當 `elapsed_ms >= timeout_ms` 時等待 `0ms` 瞬時降級純 BM25；當 `0 < elapsed_ms < timeout_ms` 時最多等待剩餘時間 `timeout_ms - elapsed_ms`，逾時即降級並於 `sys.stderr` 輸出 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`。

> [!CAUTION]
> **嚴禁在 `KnowledgeDBServiceWorker` 中重複建立 `watchdog.Observer` 監聽檔案系統，且嚴禁將前台容差等待改為不論 `elapsed_ms` 皆固定睡眠完整 `jit_vector_timeout_ms`！** 必須維持 `elapsed_ms >= timeout_ms` 時 0ms 瞬時降級之防呆不變量。

---

### [DN-30] `file-space -> ast -> knowledge-db` 三階單向無環圖（Strict 3-Tier DAG）、單次解析符號共享（Single-Parse Symbol Sharing）與 `acked_ast_generation` 雙水位線協議

- **背景與根因**：
  1. 過去語法樹解析、C# `partial class` 跨檔聚合與呼叫拓撲 (`CallGraphIndex` / `TopologyLinker`) 與全文/向量混合檢索耦合於單一 `knowledge-db` 模組中，導致僅需單檔結構大綱 (`outline`) 或靜態呼叫拓撲 (`callers/callees/impact`) 時連帶綁定檢索與向量子系統。
  2. 獨立出 Layer 2 `module:ast` 後，若 `knowledge-db` 仍自行對原始碼重複執行 Tree-sitter 解析，將造成雙倍 I/O 與 CPU 浪費；且當執行 `ast clean` 重建 `ASTSnapshot` 而 `file-space` 游標已處於 `in_sync` 時，單憑 `file-space` 游標無法感知 `ast_generation` 重置。
- **工程妥協與解法**：
  1. **單次解析符號共享（Zero Re-parse）**：`knowledge-db` 物理移除內部 `.scm` 與 Tree-sitter 解析器實作，於 `IndexingPipeline.build_unified_index()`、`build_index(space=...)`、`hot_patch_unified_index()` 與 `KnowledgeEngine.bundle()` 中，100% 透過 `self.ast_engine.ensure_jit_synced()` 取得 `ASTSnapshot`（`storage.local://ast/indices/unified.symbols.bin.gz`）與 `CallGraphIndex`（`storage.local://ast/indices/unified.graph.bin.gz`），不再重跑語法樹解析。
  2. **`acked_ast_generation` 雙水位線自癒**：`IndexingPipeline` 將當次消費之 `ASTSnapshot.ast_generation` 持久化於 `unified.index.bin.gz` 之 `InvertedIndex.acked_ast_generation` 並緩存於 `_GLOBAL_INDEX_CACHE["acked_ast_generation"]`；在 `_ensure_jit_index_ready_locked()` 與 `KnowledgeDBServiceWorker._sync_stage1_lexical_and_graph()` 中，即便 `file-space` 游標 `has_changes == False`，只要 `acked_ast_generation != snapshot.ast_generation` 即自動觸發全量重建並對齊最新 AST 世代。
  3. **`pre_aggregated=True` 免二次分部聚合與刪除分部連坐**：因 `ASTSnapshot.symbols` 已由 `module:ast` 完成雙層 `partial class` 聚合，`InvertedIndex.patch_incremental(..., pre_aggregated=True)` 直接索引符號之 `_own_members` 而不重複執行分部拆解；同時 `_collect_all_dirty_files()` 結合 `self._unified_index.symbols` 追蹤被刪除之 C# 分部檔案，確保刪除任一分部時其餘姊妹分部強制納入重算。

> [!CAUTION]
> **嚴禁在 `knowledge-db` 管線中繞過 `ASTEngine.ensure_jit_synced()` 私自呼叫底層 Parser 重複解析原始碼，亦嚴禁移除 `acked_ast_generation != snapshot.ast_generation` 水位線檢核！**




---

### [DN-31] `unified.meta.json` $O(1)$ 純元數據 `status` 快讀、離線模型守門與非阻塞 `_ensure_model(blocking=False)`
- **背景與根因**：
  1. 過去 `KnowledgeEngine.status()` 在記憶體尚未載入索引時會嘗試獲取 `_index_lock` 並解壓 `unified.index.bin.gz` / `unified.vectors.bin.gz`，甚至在缺少空間快照時退回 `iter_space_files()` 全盤走訪目錄，違反唯讀狀態速查之 $O(1)$ 低延遲原則。
  2. 此外，若 `KnowledgeDBServiceWorker` 在背景自動觸發 `download_model()`，在離線或受限網路環境中會長時間佔用 `EmbeddingService._init_lock` 並寫入忙碌狀態，拖累前景查詢。
- **工程妥協與解法**：
  1. **`unified.meta.json` 與 `BinarySnapshotManager.load_summary()`**：`IndexingPipeline` 於每次持久化索引與向量微批次落盤時同步原子寫入 `unified.meta.json`（記錄 `symbol_count`、`term_count`、`acked_ast_generation` 與向量覆蓋統計並綁定二進位檔 `(mtime_ns, size)` 指紋）；`KnowledgeEngine.status()` 直接讀取 `unified.meta.json` 與 `scanner.get_snapshot_summary()` 標頭統計，全程零 `.bin.gz` 解壓、零目錄走訪，並透過 `_probe_kdb_lock_busy()` 非阻塞回報 `building_in_progress`。
  2. **離線模型守門與非阻塞推論鎖**：移除背景 `KnowledgeDBServiceWorker` 未授權之隱式 `download_model()` 呼叫；`EmbeddingService._ensure_model(blocking=False)` 於 `_init_lock` 被佔用或正在下載時 `0ms` 立即返回降級，`HybridSearchEngine.is_vector_available` 亦優先以 $O(1)$ 檢查 `len(vector_index.doc_ids) > 0` 與 `has_local_model()` 短路，杜絕前景搜尋阻塞。

---

### [DN-32] `VectorIndex.doc_text_hashes` 內容指紋比對、行號平移 $O(1)$ 向量復用與世代對齊倒排清理
- **背景與根因**：
  1. `UnifiedSymbol.compute_id` 以起始行號計算 ID：同行號修改函式內容或 Docstring 時 ID 不變，若僅以集合差集 `sym_ids - vec_ids` 判斷向量缺口，Stage 2 微批次同步將漏更舊向量；反之在檔案頂部插入空行導致下方數十個未改動函式行號平移時，ID 改變若全部重算 ONNX 特徵將產生不必要推論開銷。
  2. 同進程內若 `ASTEngine._snapshot` 已推進至新世代，而 `_align_index_symbols_with_ast_snapshot` 無條件將舊世代 `InvertedIndex.symbols` 指針覆寫為新符號物件，後續 `InvertedIndex.patch_incremental` 對舊符號斷詞移除時會讀到新文本，導致舊關鍵詞殘留為幽靈倒排紀錄。
- **工程妥協與解法**：
  1. **`doc_text_hashes` 與行號平移零推論復用**：`VectorIndex` 持久化 `doc_text_hashes`（Blake2b 8-byte hex），缺口探測同步納入文本雜湊不一致之同 ID 符號；前台熱修補則以 `(norm_file_path, name, kind, text_hash)` 比對被逐出之舊符號向量直接 $O(1)$ 搬移復用。
  2. **世代相等守衛與混合檢索無鎖快照傳遞**：`_align_index_symbols_with_ast_snapshot` 嚴格限定 `snap.ast_generation == idx.acked_ast_generation` 始共享符號指針；`HybridSearchEngine.search` 改以呼叫端區域參數傳遞索引引用、拔除實例屬性原地突變並將查詢向量推論置於 `_index_lock` 外；當背景 Worker 處於 `yielded_to_foreground` 且存在向量缺口時，前景自動降級 `lexical_bm25` 確保召回完整度。
