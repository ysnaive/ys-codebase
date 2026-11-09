# 需求規格說明書 (Requirements Specification)

> 功能名稱：統一 Cell 生命週期快取原語、Epoch 世代常駐對稱與 Stage 耗時剖析器  
> 建立日期：2026-11-08  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `CellScope` 請求級生命週期容器與 `get_or_compute_cell_state` 原語（`core` 零 `server` 耦合） | 1. 於 `core.context` 實作純標準庫之 `@dataclass(frozen=True)` `CellScope` 與 `bind_cell_context(module_name=..., command=..., reuse_existing=True)`（基於 `ContextVar`，`core` 100% 不知悉 `server` 或 `WarmWorker` 存在，`[P01:DR-02]`；`cell_id` 計數器存放於 `RuntimeContext`，嚴禁頂層 `global`）。<br/>2. **關閉失效防洩漏 (`is_closed` 守衛)**：`CellScope` 內建封裝狀態旗標，當最外層退出 `bind_cell_context` 時於 `finally` 標記為 `closed` 並清空 `cache`；`get_current_cell()` 若偵測到 `ContextVar` 中的 `CellScope` 已 `closed`（例如被 `contextvars.copy_context()` 複製到背景執行緒），自動視同 `None`，杜絕背景執行緒向已結束之 `CellScope` 寫入導致記憶體洩漏（`[P01:DR-03]`）。<br/>3. 於 `core/commands/dispatcher.py:dispatch_local` 入口自動綁定 `CellScope`（`reuse_existing=True`），並由宿主執行器 `server/server/worker.py:WarmWorker.execute_task` 外層包裹 `with bind_cell_context(...) as cell:`，使冷派發與熱派發期間皆有同一活躍 `CellScope`。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-02** | 冷熱對稱之 `get_or_compute_epoch_state` 跨 Cell 世代常駐快取與無鎖重算原語 | 1. 於 `core.context` 實作 `get_or_compute_epoch_state(key: str, epoch_fn: Callable[[], Any], builder_fn: Callable[[], T]) -> T` 與 `invalidate_epoch_state(key: str) -> None`。<br/>2. **鎖外求值與防髒讀 (`Lock-Free Evaluation & Safe Epoch Check`)**：每次呼叫時於 `module_states_lock` **鎖外**執行輕量 `epoch_fn()`（若 `epoch_fn` 內部需避免重複系統呼叫，由呼叫端將底層 I/O 探針包裝於 `get_or_compute_cell_state`，而非盲目將純記憶體參數如 `id(symbols_map)` 鎖死於單一 `key`，防止同 Cell 傳入不同參數或原地寫入變異時產生髒讀，`[P01:DR-04]`）。<br/>3. 比對 `RuntimeContext` 內儲存之 `(cached_epoch, cached_value)`：若 `cached_epoch == current_epoch` 則 $O(1)$ 返回 `cached_value`；否則於**鎖外**執行 `builder_fn()` 後再持鎖原子寫入 `(current_epoch, new_value)`，避免阻塞背景 `ServiceWorker` 執行緒，且隨 `RuntimeContext.reset_all_caches()` 原位清空。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | `cell_span` 階段耗時剖析器與 `task_finish` 單向夾帶顯影 | 1. 於 `core.context` 實作 `cell_span(stage_name: str)` Context Manager，使用 `time.perf_counter()` 記錄毫秒耗時至當前活躍（未 `closed`）之 `CellScope.stages_ms`（支援同名階段累加與首次出現順序保留），並於 `CellScope` 提供 `format_stages_summary(min_ms: float = 0.5) -> str`。<br/>2. 於 `dispatcher.dispatch_local` 自動包裹 `pre_hooks`、`option_resolve`、`mod_load`、`cmd_exec`、`post_hooks` 五大基礎 Stage（對齊 `P00`）。<br/>3. **單向封包夾帶（零額外 IPC）**：擴充 `core/log.py:DebouncedIOStreamer.send_task_finish(..., stages: Optional[str] = None)`；`WarmWorker.execute_task` 於 `dispatch_local` 完成後從手上的 `cell` 讀取 `stages_summary = cell.format_stages_summary()` 並傳入 `send_task_finish`，夾帶於既有 `{"type": "task_finish"}` IPC 封包傳予 `MasterSupervisor` 寫入 Server Log；冷派發時僅當 `get_env("YSCB_PROFILE_CELL") == "1"` 且 `get_env("YSCB_IN_SERVER_WORKER") != "1"` 時，透過 `log_stream(..., stream="stderr", record_hint=False)` 輸出摘要，杜絕污染 `error_hint`。 | P0 | [P00:DR-04] |
| **FR-04** | 核心模組探針與常駐快取統一遷移收口 | 1. `core/space/watcher.py:is_watcher_active`：針對底層最耗時的「讀取 `state_file` (`watcher_state.json`) 並驗證 Daemon PID 存活」步驟，以 `("core.space.watcher_daemon_alive", norm_state_file)` 透過 `get_or_compute_cell_state` 快取（保留上層各 `space_query` 獨立的 `cfg.watch` 判斷，避免 `watch=False` 空間毒化同 Cell 後續查詢，`[P01:DR-05]`）。<br/>2. `agents-workflow/agents_workflow/publisher.py`：將 `_load_source_sha1_cache`（回傳 `dict(...)` 淺拷貝以防原地變異污染快取，並於 `_save_sha1_cache` 同步更新）與 `ensure_jit_release` 遷移至 `get_or_compute_epoch_state` 與 `cell_span("aw.jit_release")`。<br/>3. `ast/ast_engine/resolver.py` 與 `engine.py`：將 `_get_or_create_resolver` 遷移至 `get_or_compute_epoch_state`，並於 `ensure_jit_synced` 及拓撲解析埋設 `cell_span("ast.jit_sync")` 與 `cell_span("ast.resolve")`。<br/>4. `knowledge-db/knowledge_db/pipeline.py`：於 `IndexingPipeline.search` 與 `_ensure_jit_index_ready` 埋設 `cell_span("kdb.jit_sync")` 與 `cell_span("kdb.search")`。 | P0 | [P00:DR-01], [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 在無活躍 `CellScope` 的純 Python SDK 或單元測試環境中直接呼叫 `get_or_compute_cell_state` 或 `cell_span` | `get_or_compute_cell_state` 偵測到 `get_current_cell() is None` 時，不寫入任何全域字典，直接執行並回傳 `builder_fn()`，保證零跨測試污染；`cell_span` 則作為零開銷 no-op 直接 `yield`。 |
| **EC-02** | 巢狀 CLI 派發（例如在某個 CLI 命令或 Hook 內部再次呼叫 `dispatch_local`） | `bind_cell_context(..., reuse_existing=True)` 偵測到當前已有活躍 `CellScope` 時，直接複用外層 `CellScope` 並共享同一份 `_cell_cache` 與階段計時器；僅在最外層退出時執行清空釋放。 |
| **EC-03** | 同一 Cell 內先讀取 `is_watcher_active()`（快取於 `CellScope`），隨後在同一 Cell 內啟動/停止 Watcher 或觸發狀態變更 | 提供 `invalidate_cell_state(key_prefix)` 輔助函式，當同一進程內變更 Watcher 狀態或執行 `SpaceScanner.scan/clean` 時主動失效當前 Cell 快取對應鍵值。 |
| **EC-04** | 命令執行中途拋出未預期例外或觸發 `SystemExit` | `bind_cell_context` 與 `cell_span` 均以 `try...finally` 保護，即使命令異常退出仍能完整記錄已執行階段之耗時並 100% 釋放 `_cell_cache`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 純標準庫與靜態守門合規 | 100% Python 標準庫實現，零第三方依賴；完全符合 `dev check` 之 `A1`~`F13` 靜態守門（含 `@dataclass(frozen=True)`、零頂層可變單例、零未受管 `print`）。 |
| **NFR-02** | 輸出純淨度與極低開銷 | 常規 CLI（未設 `YSCB_PROFILE_CELL=1`）之 `stdout`/`stderr` 0 額外字元輸出；單次 `cell_span` 與 `get_or_compute_cell_state` 命中開銷 $< 5\,\mu\text{s}$。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** `dev check` 規則 `C9` 要求所有 `@dataclass` 必須宣告 `@dataclass(frozen=True)`，因此 `CellScope` 若使用 `@dataclass(frozen=True)`，其內部的可变容器欄位（如 `cache: Dict[Any, Any]` 與 `stage_durations_ms: Dict[str, float]`）必須搭配 `compare=False` 定義，且於退出時透過 `.clear()` 原位清空。
