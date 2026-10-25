# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：Server 與 Knowledge-DB 背景服務並發鎖、預熱時序與記憶體暴增修復 (2026_10_25_1103_server_kdb_concurrency_and_memory_fix)  
> 建立日期：2026-10-25  
> 所屬主計畫：None  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)

### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)
- [x] **修改行數守門**：代碼修改行數預估 $\le 100$ 行（預估約 65 行）。
- [x] **API 契約守門**：Public API 簽名契約 0 變更（無破壞性與新增導出）。
- [x] **依賴邊界守門**：零跨模組新依賴引入。
- [x] **既有測試守門**：既有單元測試套件 100% 覆蓋守門。

### 1.2 核心需求與邊界
- **需求描述**：
  徹底修復常駐 `server` 與 `knowledge-db` 背景監聽服務在連續檔案變更與 CLI 調用時引發的 `RuntimeError: dictionary changed size during iteration`、背景無上限觸發 `ProcessPoolExecutor` + ONNX 全量重建導致記憶體暴增至 10GB，以及 `server` Worker 啟動時 `No module named 'knowledge_db'` 預熱失敗與 `restart_server()` / `stop()` 重入問題：
  1. **`[FP-01:DR-01]` `IndexingPipeline` 執行緒互斥鎖與 `KnowledgeDBServiceWorker` 尾隨排隊防重入**：
     - 於 `IndexingPipeline` 增設 `self._index_lock = threading.RLock()`，保護 `build_unified_index()`、`hot_patch_unified_index()` 與 `_ensure_jit_index_ready()` 的索引讀寫區段，杜絕背景 Timer 執行緒與前台 IPC 執行緒（或多個 Timer 執行緒之間）同時迭代與變異 `self._unified_index.symbols` / `self._unified_index.index` 引發 `dictionary changed size during iteration`。
     - 於 `KnowledgeDBServiceWorker` 增設 `self._patch_lock = threading.Lock()`，並將 `_execute_debounced_patch()` 改為迴圈排空 `_pending_dirty_paths`：若前一次修補仍在執行，新變更僅加入 `_pending_dirty_paths`，由當前持鎖執行緒在修補完畢後自動尾隨處理下一批，絕不並發衝撞。
  2. **`[FP-01:DR-02]` 背景修補禁止多進程衍生 (`allow_parallel=False`) 與字典迭代快照保護**：
     - 於 `SemanticBundler.bundle_union()` 新增預設相容參數 `allow_parallel: bool = True`；當在常駐背景服務或回退重建時傳入 `allow_parallel=False`，強制使用單進程串行解析，徹底杜絕常駐 Worker 在背景 spawn 4 個 `ProcessPoolExecutor` 子進程池造成記憶體倍增與進程洩漏。
     - 於 `InvertedIndex.to_dict()` 與 `patch_incremental()` 對 `self.index.items()`、`self.symbols.items()` 統一採 `list(...)` 淺快照迭代，消除序列化期間的並發迭代異常。
  3. **`[FP-01:DR-03]` `server/worker.py` 預熱路徑時序修正與 `master.py` `stop()` 冪等防重入**：
     - 修正 `WarmWorker.pre_warm()` 時序：先將 `.modules` 加入 `sys.path` 並呼叫 `self.service_manager.load_from_contributes(self.yscb_root)`（完成 `.modules/<provider>` 路徑注入），再廣播 `server_worker_warming` 與啟動服務，根除 `[hook.server] No module named 'knowledge_db'`。
     - 在 `MasterSupervisor.stop()` 入口加入 `if not self._is_running: return` 冪等守門，避免 `restart_server()` 背景執行緒呼叫 `self.stop()` 解鎖 `_httpd.serve_forever()` 後、`finally: self.stop()` 二次重入執行重複清理與日誌歸檔。
- **影響範圍**：
  - `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py`
  - `ys_codebase/source/knowledge-db/knowledge_db/service.py`
  - `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py`
  - `ys_codebase/source/knowledge-db/knowledge_db/bundler.py`
  - `ys_codebase/source/server/server/worker.py`
  - `ys_codebase/source/server/server/master.py`
  - `ys_codebase/source/knowledge-db/tests/test_service_worker.py`（及 `server/tests/test_server.py`）

### 1.3 實作任務與測試規劃
- [x] **TASK-01**：於 `knowledge_db/pipeline.py`、`service.py`、`retrieval.py`、`bundler.py` 實作 `_index_lock`、尾隨排隊修補、字典快照迭代與背景 `allow_parallel=False`。
- [x] **TASK-02**：於 `server/worker.py` 修正 `pre_warm()` 模組路徑載入與事件廣播時序，並於 `server/master.py` 補齊 `stop()` 冪等重入防護。
- [x] **TASK-03**：新增並發壓測單元測試，執行 `dev check`、`dev test` 並安裝 `@build` 驗證。
- **測試案例清冊**：
  - [x] **FT-01**：驗證多執行緒同時觸發 `KnowledgeDBServiceWorker._execute_debounced_patch()` 與 `hot_patch_unified_index()` / `to_dict()` 時，100% 零 `dictionary changed size during iteration` 異常且不觸發 `ProcessPoolExecutor`。
  - [x] **FT-02**：驗證 `WarmWorker.pre_warm()` 在廣播 `server_worker_warming` 前已備妥 `.modules/knowledge-db` 路徑，且 `MasterSupervisor.stop()` 連續呼叫兩次具備冪等性不重複歸檔。
  - [x] **RT-01**：`knowledge-db` 與 `server` 全模組既有單元測試 100% 回歸通過。

---

## 2. 實作與驗證成果 (FP-02 Execution & Test Log)

- **實作結果**：
  - 完成 `IndexingPipeline._index_lock` (`RLock`) 與 `KnowledgeDBServiceWorker._patch_lock` (`Lock`) 尾隨排隊迴圈防重入，徹底消除背景防抖 Timer 與前台查詢同時讀寫倒排索引字典之競態。
  - 完成 `InvertedIndex.to_dict()` 之 `list(...)` 淺快照迭代與 `SemanticBundler.bundle_union(allow_parallel=False)` 背景單進程解析限制，根除常駐 Worker 在背景衍生 4-worker `ProcessPoolExecutor` 子進程池導致記憶體暴增至 10GB 的問題；同步移除遺留的 `source/knowledge-db/configurable/config.local.json`。
  - 完成 `WarmWorker.pre_warm()` 先行執行 `service_manager.load_from_contributes()` 再廣播 `server_worker_warming` 事件，並為 `MasterSupervisor.stop()` 加入 `_stop_lock` 與 `_is_stopped` 冪等防重入保護。
  - 完成 `knowledge-db@1.1.0.build` 與 `server@1.0.0.build` 熱部署安裝。
- **實機測試日誌**：
  - `python yscb.py dev check knowledge-db`：`[PASS]`
  - `python yscb.py dev check server`：`[PASS]`
  - `python yscb.py dev test server -q`：`Pass: 41(100.0%), Fail: 0, Skip: 0`（含新增 `test_prewarm_load_order_and_master_stop_idempotency`）
  - `python yscb.py dev test knowledge-db -q`：`Pass: 151(100.0%), Fail: 0, Skip: 0`（含新增 `test_concurrent_debounced_patch_and_serialization_safety`）

---

## 3. SOP Review 審查與結案交付 (Review & FP-03 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（docs/ 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 CHANGELOG.md 發布摘要。
- [x] **標頭狀態更新**：完成上述審查並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

