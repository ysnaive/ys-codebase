# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：統一 Cell 生命週期快取原語、Epoch 世代常駐對稱與 Stage 耗時剖析器  
> 建立日期：2026-11-08  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：反思本次難以追溯耗時與各處塞滿手寫探針、Bug 頻出的原因，在於採用類 Jupyter (`ipynb`) 常駐設計，又要兼顧冷熱派發邏輯，卻未提供統一的 `Cell` 生命週期機制與快取原語供下游使用。優先針對「統一 Cell 生命週期快取與 Stage 剖析原語」開立計畫（前置於 `ast` 重構之 `sub_02` / `sub_03`）。
- **核心目標**：
  1. **確立 `CellExecutionScope`（單次 CLI 任務執行單元）與 `cell_memoize` / `get_or_compute_cell_state` 原語**：無論是冷派發（`dispatch_local`）或熱派發（`WarmWorker.execute_task`），每一次 CLI 指令派發皆自動綁定一個獨立的 `CellExecutionScope`（含唯一 `cell_id`、命令識別、請求級快取字典 `_cell_cache` 與階段耗時追蹤器 `_stage_spans`）。在同一個 Cell 生命週期內，重複的環境探針（如 `is_watcher_active`、`space.head_generation`、`contributes` 匯聚、`.gitignore` 檢查）保證最多僅計算 1 次，Cell 結束時 `finally` 100% 釋放，杜絕跨請求污染。
  2. **確立冷熱對稱之 `EpochCache` / `get_or_compute_epoch_state(key, epoch_fn, builder_fn)` 原語**：提供綁定「輕量世代指紋（Epoch Tuple，如空間世代 `(gen, watcher_active)`、檔案 `(mtime_ns, size)` 或記憶體圖譜 `id/generation`）」的跨 Cell 常駐快取原語，且對 `epoch_fn()` 本身自動套用當前 Cell 級短路（同一 Cell 內連 `epoch_fn` 都不重複執行）。在 `WarmWorker` 中實現 $O(1)$ 零重算命中，在 Cold CLI 中自動退化為單次載入，並隨 `RuntimeContext.reset_all_caches()` 原位清空。
  3. **內建零開銷 `cell_span(stage_name)` 階段耗時剖析與慢查詢透明顯影**：於 `dispatcher.dispatch_local`（`pre_hooks`、`option_resolve`、`module_load`、`cmd_exec`、`post_hooks`）及關鍵下游階段（如 `agents_workflow.jit_sync`、`ast.jit_sync`、`ast.resolver`、`kdb.jit_sync`、`kdb.search`）內建 `cell_span` 記錄。當透過 `WarmWorker` 派發完成或開啟 `--debug` / `YSCB_PROFILE_CELL=1` 時，將結構化 Stage 耗時明細（如 `stages=[pre_hooks=1.2ms, cmd_exec=240.5ms (ast.jit_sync=0.3ms)]`）隨 `task_finish` 帶回 `MasterSupervisor` Server Log（或 `--debug` `stderr`），徹底終結黑盒耗時盲猜。
  4. **收斂既有模組手寫探針**：將 `agents-workflow` (`publisher.py` 之 `source_sha1_cache` 與 `gitignore_sync`)、`ast` (`resolver.py` 之 `_get_or_create_resolver` 與 `engine.py` 世代探針) 及 `core.space` (`is_watcher_active` Cell 級短路) 統一遷移至標準 Cell / Epoch 原語，為緊接其後的 `ast` `sub_02` / `sub_03` 提供標準基座。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 直接擴充 `ys_codebase/source/core/core/context.py` 既有之 `RuntimeScope` (`_ACTIVE_RUNTIME_SCOPE` ContextVar) 與 `RuntimeContext`（`module_states`），不另起平行的 ContextVar 體系或獨立套件。
  - 直接對接 `ys_codebase/source/server/server/worker.py` (`DebouncedIOStreamer.send_task_finish`) 與 `ys_codebase/source/server/server/master.py` (`Task dispatch finished` 日誌格式)，不新增額外 IPC 封包類型。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更 `ast` 之 `WorkspaceSymbolGraph` 連結演算法本體（留待 `ast` `sub_02` 執行）。
  - 不引入任何第三方 Telemetry / Tracing 外部依賴（維持 100% Python 標準庫 `time.perf_counter` 與 `contextvars`）。
  - 在非 `--debug` / 非 `YSCB_PROFILE_CELL=1` 之一般前台終端輸出中，絕不向 `stdout` 或 `stderr` 印出剖析數據，100% 保證 `--json` 與 CLI 輸出純淨。
- **架構影響範圍**：
  - `module:core`：`core/context.py`（新增 `CellScope`、`bind_cell_context`、`get_or_compute_cell_state`、`get_or_compute_epoch_state`、`cell_span`）、`core/commands/dispatcher.py`（於 `dispatch_local` 自動包裹 `bind_cell_context` 與五大標準 Stage Spans）、`core/space/watcher.py`（`is_watcher_active` 接入 Cell 級快取）。
  - `module:server`：`server/worker.py` 與 `server/master.py`（將 Cell Stage 耗時摘要隨 `task_finish` 寫入 Server Log，於慢查詢或一般任務一眼可見各階段耗時）。
  - `module:agents-workflow` / `module:ast` / `module:knowledge-db`：將散落之手刻 `get_module_state` 探針收口至 `get_or_compute_epoch_state` 與 `cell_span`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 既有組件復用與單一 ContextVar 階層 (`Reuse Discovery`)**：
  - `CellScope` 直接掛載於 `core.context` 模組，與 `RuntimeScope` 協同運作；當 `dispatch_local` 啟動時，若當前尚無活躍 `CellScope`（例如冷派發或直接調用），自動建立頂層 `CellScope`；若由 `WarmWorker.execute_task` 啟動，則整個 Task 即為一個完整 Cell，內部巢狀呼叫自動複用同一 `CellScope`。
- **[P00:DR-02] 預設值與零輸出污染守衛 (`Default & Side-Effect Probe`)**：
  - 若業務函式在「非 CLI 派發環境」（如單元測試直接呼叫 Python SDK `ASTEngine().outline(...)` 且未包裹 `bind_cell_context`）中呼叫 `get_or_compute_cell_state`：當無活躍 `CellScope` 時，自動退化為直接執行 `builder_fn()`（不快取於全域，避免無界駐留與跨測試案例狀態污染）；而 `get_or_compute_epoch_state` 則因其綁定明確的 `epoch_fn()`（如 `(mtime_ns, size)` 或 `ast_generation`）且受 `RuntimeContext.reset_all_caches()` 管轄，在 SDK 與 CLI 下皆可安全命中。
- **[P00:DR-03] 生命週期與拆卸冪等性 (`Lifecycle & Teardown Probe`)**：
  - `bind_cell_context` 以 `try...finally` 確保無論命令正常返回、拋出例外或觸發 `SystemExit`，都會在退出時重置 `ContextVar` Token 並清空該 `CellScope._cell_cache`，確保 Cell 內暫存物件（Request-scoped objects）100% 立即釋放，零常駐記憶體殘留。
- **[P00:DR-04] 階段耗時座標與跨切面不變量 (`Cross-Cutting Invariant Probe`)**：
  - `cell_span(name)` 統一使用單調時鐘 `time.perf_counter()` 計算毫秒耗時（`float`, 小數點後 1 位），支援同名累加（例如迴圈內多次呼叫）或階層名稱（如 `pre_hooks`、`ast.jit_sync`），並輸出穩定排序之緊湊摘要字串（僅顯示 $\ge 0.5\text{ ms}$ 之顯著階段，避免微小雜訊洗版）。

---

## 3. 開放議題與確認紀錄

- 已完成五維度防放水反詰掃描，無阻塞性未決歧義，建議採 **Full Track**（搭配 `/auto` 自動連續推進）落地。
