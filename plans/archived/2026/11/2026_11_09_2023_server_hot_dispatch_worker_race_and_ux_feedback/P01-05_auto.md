# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：2026_11_09_2023_server_hot_dispatch_worker_race_and_ux_feedback  
> 建立日期：2026-11-10  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 全量 `server` 熱派發覆蓋與客戶端斷線協作取消 | 1. 於 `gdrive-support/contributes/core.json` 將 `branch` 及其子指令 `list`、`create`、`delete` 升級為 `"server_compatible": true`。<br>2. 於 `core/context.py` 新增任務協作取消狀態（`request_task_cancel`、`reset_task_cancelled`、`is_task_cancelled`），並將 `WarmWorker` 之 `foreground_active` 升級為引用計數安全管理。<br>3. 於 `server/master.py` 偵測客戶端 HTTP 串流斷線（`wfile.write` `OSError` 或非阻塞 socket FIN 探針），向 `WarmWorker` stdin 發送 `{"action": "cancel"}` 控制包，並由 `worker_main` 專屬讀取執行緒即時觸發 `request_task_cancel()`；同時 `core/commands/dispatcher.py` 對 `KeyboardInterrupt` 優雅關閉連線並返回 `130`。 | P0 | `[P00:DR-01]` |
| **FR-02** | 前景絕對優先、背景 Worker 退讓與離線模型非阻塞守門 | 1. 於 `server/space_watcher.py` (`CoreSpaceWatcherServiceWorker`) 之 `flush_dirty_spaces(force=False)` 與啟動預掃描迴圈檢查 `server.worker.foreground_active`，前景活躍時主動延後背景掃描並記錄 `deferred_by_foreground_count`。<br>2. 於 `knowledge_db/service.py` (`KnowledgeDBServiceWorker._run_sync_cycle`) 移除未獲授權之背景 `download_model()` 呼叫；當本地無模型權重時直接設為 `STATE_DEGRADED_OFFLINE` (`busy=False`)。<br>3. 於 `knowledge_db/embedding.py` 將 `_ensure_model(blocking=False)` 改為預設 `self._init_lock.acquire(blocking=False)` 非阻塞探測，並於 `_suppress_hf_warnings()` 注入 `HF_HUB_DISABLE_PROGRESS_BARS=1` 與 `TQDM_DISABLE=1`。<br>4. 於 `knowledge_db/hybrid.py` (`is_vector_available`) 優先以 $O(1)$ 檢查 `len(vector_index.doc_ids) > 0` 及本地模型存在性，最後才探測 `embedding_service.is_available`。 | P0 | `[P00:DR-02]` |
| **FR-03** | 人機雙通道分離之即時 `stderr` 進度反饋與低延遲串流刷新 | 1. 於 `core/log.py` 修正 `_write_to_active_target` 將 `flush=True` 傳遞至 `DebouncedIOStreamer.write(..., flush=flush)`，並使 `_StreamProxy` 對 `stderr` 含 `\r` 之寫入即時刷新（保留普通無 `flush` 換行寫入之批次緩衝行為）。<br>2. 於 `core/log.py` 新增 `ProgressReporter`（具備 `initial_delay_ms=200` 靜默門檻、`interval_ms=250` 節流、背景 `ServiceWorker` 自動靜默、`YSCB_FORCE_PROGRESS=1` 強制輸出與 `record_hint=False` 純 `stderr` 輸出）。<br>3. 於 `ast`（`build_index`、`hot_patch_index`、`WorkspaceGraphLinker.link_workspace`）與 `knowledge-db`（`build_unified_index`、`sync_incremental_changes`）植入階段與百分比進度回報及協作取消檢查點，確保 `--json` `stdout` 100% 純淨。 | P0 | `[P00:DR-03]` |
| **FR-04** | `knowledge-db` / `ast` / `core.space` 靜態 `status` $O(1)$ 輕量化與單檔 `slice` 快速路徑 | 1. 於 `knowledge_db/pipeline.py` 在索引建置、熱修補與向量刷寫時原子寫入 `indices/unified.meta.json`（含 `symbol_count`, `term_count`, `acked_ast_generation`, `space_symbol_counts`, `embedded_count`, `missing_count`, `stale_count`, `coverage_pct`, `vector_dim`, `vector_model_name`, `vector_compatible` 及檔案 `mtime_ns`/`size`），並於 `clean()` 同步清除。<br>2. 重構 `KnowledgeEngine.status()` 優先讀取記憶體或 `unified.meta.json` 與 `BinarySnapshotManager.load_summary()`，拔除阻塞式 `_ensure_indices_loaded` 與 `iter_space_files()` 全盤掃描。<br>3. 強化 `ASTEngine.status()` 為純非阻塞鎖探測，建圖鎖忙碌時立即回傳 `building_in_progress: True` 與即時進度。<br>4. 優化 `ASTEngine._resolve_symbol_node_for_slice()` 對 `<rel_path>::<fqn>` 與 `UnifiedSymbol` 走單檔 `parse_file()` $O(1)$ 快速路徑，不觸發 `get_workspace_graph(auto_sync=True)`。 | P0 | `[P00:DR-04]` |
| **FR-05** | `P06` 斷點強制三輪靶向深度審計融斷守門 | 於 `P06` 全量測試通過後，依 `@codebase-deep-auditor` 與 `@yscb-async-deep-audit` 執行最多 3 輪雙盲子代理審查（`OPT/ARCH` x `PERF` x `AUD`），達成零 `P0/P1/P2` 與零 `ARCH`/`PERF` 債後方可推進 `P07`。 | P0 | `[P00:DR-05]` |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 單元測試以 `io.StringIO` 傳入多行指令（`dispatch` + `exit`）測試 `worker_main` | `worker_main` 讀取執行緒將 `"dispatch"` 與 `"exit"` 嚴格依序排入 `cmd_queue` FIFO 執行，僅對 `"cancel"` 執行緒外即時置位取消事件，100% 相容同步串流測試。 |
| **EC-02** | 客戶端於寫入型指令或索引持久化中途按下 `Ctrl+C` 斷線 | 協作取消僅於解析/連結/嵌入之讀取計算迴圈安全中斷（拋出 `TaskCancelledError` 並回滾游標），已進入 `vfs` 原子寫入或 `InterProcessLock` 臨界區之落盤交易完整走完，且 `MasterSupervisor` 持續排空至 `task_finish` 確保管道零殘留封包。 |
| **EC-03** | 舊版工作區已有 `unified.index.bin.gz` 但尚無 `unified.meta.json`，或背景正在建置索引時執行 `kdb status` / `ast status` | 若鎖空閒則非阻塞讀取既有索引一次；若鎖正被背景或他進程持有，立即以 $<30\text{ms}$ 非阻塞返回 `building_in_progress: True` 與當前階段進度，絕不卡死等待。 |
| **EC-04** | C++ 符號選擇器含雙冒號（如 `ast slice Engine::Bootstrapper::init`）而非 `<rel_path>::<fqn>` | `_resolve_symbol_node_for_slice()` 先驗證 `::` 左側是否可由 `_resolve_target_file()` 解析為真實存在之檔案；若非檔案路徑則平滑回退至工作區符號解析，絕不誤拋 `FileNotFoundError`。 |
| **EC-05** | 微小型專案或單元測試建圖耗時 $<200\text{ms}$，或於背景 `ServiceWorker` 執行緒內執行同步 | `ProgressReporter` 在未超過 `initial_delay_ms=200`（且未設 `YSCB_FORCE_PROGRESS=1`）或處於 `background_sink` 作用域時保持 0 輸出，確保既有測試之 `stderr` 斷言與背景日誌純淨。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 靜態速查與單檔延遲 | 在已建立 `.meta.json`（或背景正持鎖建圖中）之工作區，`ast status`、`knowledge-db status`、`core file-space status` 與單檔 `ast slice <rel_path>::<fqn>` 引擎層呼叫延遲 $< 30\text{ms}$。 |
| **NFR-02** | 串流進度即時性與純淨度 | `ProgressReporter` 觸發時經由 `DebouncedIOStreamer` 刷新延遲 $< 20\text{ms}$，節流頻率 $\le 5\text{Hz}$，且 `--json` 模式下 `stdout` 100% 可由 `json.loads()` 直接解析。 |
| **NFR-03** | 靜態合規與零資源洩漏 | 全倉通過 `dev check --all`（`C8` 零頂層可變狀態、`0 FAIL, 0 WARN`）及 `-W error::ResourceWarning` 全模組測試。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- `test_server.py:test_debounced_streamer_max_buffer_bytes` 明確驗證 `streamer.write("stdout", "line1\n")` 在未達 `max_buffer_bytes` 且未呼叫 `flush()` 時必須維持緩衝合併；因此即時刷新必須綁定顯式 `flush=True` 參數（與 `_StreamProxy` 對 `stderr` `\r` 進度覆寫），不可無條件對所有 `\n` 強制刷新。
- `test_service_worker.py:test_hook_server_no_duplicate_watcher` 明確鎖定 `knowledge-db model download` 為 `server_compatible: false`，須嚴格保留。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```
[CLI Client (dispatcher.py)]
   │  HTTP POST /api/dispatch (Chunked NDJSON)
   │  (Ctrl+C -> TCP FIN / KeyboardInterrupt -> exit 130)
   ▼
[MasterSupervisor (server/master.py)]
   ├── Non-blocking socket EOF probe + chunk_emitter OSError -> disconnect_event
   ├── Sends {"action": "cancel"}\n over worker stdin on client disconnect
   ▼
[WarmWorker (server/worker.py)]
   ├── Stdin Reader Thread: routes "dispatch"/"exit" -> FIFO cmd_q; "cancel" -> request_task_cancel()
   ├── Ref-counted `server.worker.foreground_active` around foreground task
   │     ├── yields CoreSpaceWatcherServiceWorker.flush_dirty_spaces()
   │     └── yields KnowledgeDBServiceWorker Stage 1 & Stage 2 micro-batches
   └── DebouncedIOStreamer(flush=True immediate emit) <--- ProgressReporter (stderr, 250ms throttled)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 異動類型 | 職責與變更摘要 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/context.py` | Modify | 新增執行緒安全之 `foreground_active` 計數輔助與任務協作取消 API (`request_task_cancel`, `reset_task_cancelled`, `is_task_cancelled`, `TaskCancelledError`) |
| `ys_codebase/source/core/core/log.py` | Modify | 支援 `_write_to_active_target` 傳遞 `flush=True` 至 `DebouncedIOStreamer.write`、`_StreamProxy` `stderr` `\r` 即時刷新，並新增統一 `ProgressReporter` |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | `_hot_dispatch_attempt` 與 `dispatch` 優雅處理 `KeyboardInterrupt`（關閉 HTTP 串流觸發遠端取消並返回 `130`） |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | 於 `BinarySnapshotManager` 新增零物件配置之 `load_summary()` 加速 `SpaceScanner.status()` 與 `KnowledgeEngine.status()` |
| `ys_codebase/source/gdrive-support/contributes/core.json` | Modify | 將 `branch` 及 `branch list/create/delete` 標記為 `server_compatible: true` |
| `ys_codebase/source/server/server/master.py` | Modify | 實作客戶端斷線探測、向 Worker 發送 `{"action": "cancel"}` 並安全排空至 `task_finish` |
| `ys_codebase/source/server/server/worker.py` | Modify | 實作 `worker_main` 非阻塞取消訊號分流、引用計數 `foreground_active` 與 `TaskCancelledError` 收斂處理 |
| `ys_codebase/source/server/server/space_watcher.py` | Modify | 於 `flush_dirty_spaces` 與預掃描迴圈補齊 `foreground_active` 禮讓與 `deferred_by_foreground_count` 指標 |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 植入 `ProgressReporter` 與 `.ast_build_state.json`、非阻塞 `status()` `building_in_progress` 探針、外部刪除快取失效清理、以及 `_resolve_symbol_node_for_slice()` 單檔 `parse_file()` $O(1)$ 快速路徑 |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 於 `bundle_union`、`bundle_dirty_files`、`extract_all_file_graphs` 支援進度回呼與協作取消檢查 |
| `ys_codebase/source/ast/ast_engine/linker.py` | Modify | 於 `WorkspaceGraphLinker.link_workspace` 支援階段/檔案進度回呼與協作取消檢查 |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | `_ensure_model(blocking=False)` 非阻塞鎖擷取與 `HF_HUB_DISABLE_PROGRESS_BARS=1` / `TQDM_DISABLE=1` |
| `ys_codebase/source/knowledge-db/knowledge_db/hybrid.py` | Modify | `is_vector_available` 調整為 `len(vector_index.doc_ids) > 0` 與本地模型存在性優先之 $O(1)$ 短路順序 |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 移除背景隱式 `download_model()`，無本地模型時零阻塞進入 `DEGRADED_OFFLINE` (`busy=False`) |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 實作 `unified.meta.json` 原子持久化與清理、植入 `ProgressReporter` 進度反饋，並優化前景忙碌/無模型時跳過冗餘向量載入 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 重構 `status()` 優先走記憶體與 `unified.meta.json` + `load_summary()`，拔除阻塞解壓與 `iter_space_files()` |
| `docs/server/`, `docs/ast/`, `docs/knowledge-db/` | Modify | 同步更新系統設計筆記與架構契約說明 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **ADR-01（協作式取消優於信號強殺）**：在單一常駐 `WarmWorker` 架構下，直接對子進程發送 `SIGINT`/`SIGTERM` 可能打斷 `vfs` 原子替換或損毀記憶體單例鎖狀態；透過 stdin 控制通道傳遞 `{"action": "cancel"}` 置位 `RuntimeContext` 取消事件，可讓唯讀計算迴圈於 `<50ms` 內安全退出，同時保護落盤交易完整性與 NDJSON 串流邊界。
- **ADR-02（雙層 `unified.meta.json` 對稱快取）**：比照 `ASTEngine` 為 `KnowledgeEngine` 建立包含 `mtime_ns` 與 `size` 雙重校驗之 `unified.meta.json`，使 `kdb status` 從 $O(N)$ 全量反序列化降為 $O(1)$ 單一 JSON 讀取。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# core/context.py
class TaskCancelledError(RuntimeError):
    """Raised cooperatively when an in-flight server worker task is cancelled by client disconnect."""

def request_task_cancel() -> None: ...
def reset_task_cancelled() -> None: ...
def is_task_cancelled() -> bool: ...
def check_task_cancelled() -> None: ...

# core/log.py
class ProgressReporter:
    def __init__(
        self,
        component: str,
        title: str,
        *,
        total_stages: int = 1,
        initial_delay_ms: float = 200.0,
        interval_ms: float = 250.0,
        enabled: Optional[bool] = None,
    ) -> None: ...
    def stage(self, stage_idx: int, stage_label: str, current: int = 0, total: int = 0) -> None: ...
    def advance(self, current: int, total: int, detail: str = "") -> None: ...
    def finish(self, summary: str = "") -> None: ...

# core/space/scanner.py (BinarySnapshotManager)
def load_summary(self, path: Union[str, Path]) -> Tuple[int, str, str, int]:
    """Return (head_generation, merkle_root, config_hash, active_file_count) with zero entry object allocations."""
```

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

1. **問：當客戶端斷線觸發 `TaskCancelledError` 時，`ASTEngine.ensure_jit_synced` 或 `IndexingPipeline.sync_incremental_changes` 的空間游標是否會被錯誤推進？**
   - 答：不會。兩者皆包裹於 `with ExitStack() as stack: stack.enter_context(self._consume_space_diff(...))` 交易作用域內；拋出 `TaskCancelledError`（繼承自 `RuntimeError`）時，`consume_diff` 因偵測到未捕獲異常自動跳過 `ack()`，下次執行仍能完整重試差集！但需注意 `ASTEngine.ensure_jit_synced` 外層的 `except Exception as exc:` 必須明確 `except TaskCancelledError: raise` 重新拋出，不可吞沒取消例外！
2. **問：移除 `KnowledgeEngine.status()` 的 `iter_space_files()` 後，對於尚未執行 `scan` 或 `index` 的全新空間，`cached_files` 回傳什麼？**
   - 答：回傳 `0`（與欄位名稱 `cached_files` 語意完全一致：尚未建立快取快照前快取檔案數即為 `0`，建置或掃描後即從 `.yfp2` 或 `meta.json` 精確回傳活躍檔案數）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

- 更新 `docs/knowledge-db/DESIGN_NOTES.md`（記錄顯式模型供給、非阻塞 `_init_lock` 與 `unified.meta.json` $O(1)$ `status`）。
- 更新 `docs/ast/DESIGN_NOTES.md`（記錄單檔 `<rel_path>::<fqn>` `slice` $O(1)$ 快速路徑、即時進度反饋與非阻塞 `building_in_progress` 探針）。
- 更新 `docs/server/`（記錄客戶端斷線協作取消與 `CoreSpaceWatcherServiceWorker` 前景禮讓協議）與根目錄 `CHANGELOG.md`。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **T1（`core` 基礎設施）**：擴充 `core/context.py`（取消旗標與前景計數）、`core/log.py`（`DebouncedIOStreamer` `flush=True` 直通與 `ProgressReporter`）、`core/commands/dispatcher.py`（`KeyboardInterrupt` 優雅處理）與 `core/space/scanner.py`（`BinarySnapshotManager.load_summary`）。
- [x] **T2（`gdrive-support` & `server` 熱派發與競態治理）**：更新 `gdrive-support/contributes/core.json` (`branch` 熱派發)；強化 `server/master.py` 斷線偵測與 `"cancel"` 發送、`server/worker.py` 非阻塞取消讀取執行緒與前景引用計數、`server/space_watcher.py` 前景活躍禮讓。
- [x] **T3（`knowledge-db` 離線守門、非阻塞鎖、進度反饋與 `unified.meta.json`）**：更新 `service.py`、`embedding.py`、`hybrid.py`、`pipeline.py`、`engine.py`。
- [x] **T4（`ast` 即時進度反饋、非阻塞 `status` 與單檔 `slice` $O(1)$ 快速路徑）**：更新 `ast_engine/engine.py`、`bundler.py`、`linker.py`。
- [x] **T5（測試、建置安裝與 `P06` 三輪雙盲靶向深度審計）**：擴充並執行 `core`、`server`、`gdrive-support`、`ast`、`knowledge-db` 測試套件，通過三輪 `@codebase-deep-auditor` + `@yscb-async-deep-audit` 審查與 `0 ResourceWarning` 驗證。

### 5.2 實作偏差紀錄表 (Implementation Deviations)

- **D-01（`TaskCancelledError` 繼承 `BaseException` 與 `task_id` 端對端綁定）**：為防止業務層 `except Exception:` 誤攔截取消例外並觸發全量回退重建，`TaskCancelledError` 升級為繼承 `BaseException`，並透過 `bind_active_task_cancel_scope(task_id)` 對齊 `dispatch`/`cancel` IPC 封包以杜絕跨任務取消污染。
- **D-02（`huggingface_hub.utils` 取代 `os.environ` 突變）**：為嚴守 `[B5]` 靜態守門零 `os.environ` 執行期寫入，改以 `huggingface_hub.utils.disable_progress_bars()` 靜默進度條。
- **D-03（`hot_patch_index` 延遲 `workspace_graph` 建構與 CRLF 無損位元組對齊）**：單檔熱修補將 4-pass `WorkspaceGraphLinker.link_workspace()` 延遲至 `callers`/`callees`/`impact`/`get_workspace_graph` 按需水合（耗時下降 ~84%），並引入 `normalize_source_bytes` 確保 Windows CRLF 與多語系 UTF-8 切片零偏移。
