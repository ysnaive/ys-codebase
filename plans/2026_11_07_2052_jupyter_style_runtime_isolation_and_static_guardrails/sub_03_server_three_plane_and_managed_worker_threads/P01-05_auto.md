# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_03_server_three_plane_and_managed_worker_threads  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Completed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `WarmWorker` 控制與執行通道分離及零全域突變派發 | `server/server/worker.py` 之 `worker_main()` 移除 `sys.stdout = sys.stderr` 重導向；`WarmWorker.execute_task()` 移除 `os.getcwd()`、`os.chdir(cwd)`、`os.environ.update(env)` 與 `_restore_env_diff(orig_env)`，全面透過 `core.context.bind_runtime_context(virtual_cwd=cwd, env=task_env, host_dir=..., yscb_dir=self.yscb_root, module_name=module)` 與 `core.log.DebouncedIOStreamer` 執行熱派發，並精準回傳 `exit_code` 與結構化 `error_hint`。 | P0 | [P00:DR-01] |
| **FR-02** | `BaseServiceWorker` 原生受管執行緒、非阻塞狀態機與背景日誌隔離 | `server/server/service.py:BaseServiceWorker` 內建標準狀態常數（`STARTING`, `UPDATING`, `READY`, `DEGRADED_OFFLINE`, `STOPPED`）、受管 Daemon 執行緒生命週期（`_thread`, `_stop_event`, `start_managed_thread`, `stop_managed_thread`, `run_loop`）與 `bind_log_context(background_sink=..., component=self.name)` 串流隔離；收斂 `_LAST_TOUCH_TS` 與 `_LAST_TOUCH_BY_ROOT` 頂層可變狀態，並使 `ServiceManager.get_status_list()` 同時回傳 `name`、`provider`、`alive` 與 `state`。 | P0 | [P00:DR-02] |
| **FR-03** | 三大常駐服務對齊與移除 `hook.server.py` 野執行緒 | 對齊 `CoreSpaceWatcherServiceWorker`、`KnowledgeDBServiceWorker` 與 `GDriveSyncServiceWorker` 至 `BaseServiceWorker` 狀態與受管執行緒契約；物理刪除 `ys_codebase/source/file-space/scripts/hook.server.py` 與 `ys_codebase/source/knowledge-db/scripts/hook.server.py`（消除私開野執行緒與 `GitignoreEvaluator` 舊版匯入警告），並對齊 `server` 模組生產代碼至 `core.log` 與 `@dataclass(frozen=True)`。 | P0 | [P00:DR-02] |
| **FR-04** | `knowledge-db` 離線模型預檢 `has_local_model()` 與背景受管執行緒非阻塞自動下載 | 於 `knowledge_db/embedding.py:EmbeddingService` 實作 `< 1ms` 純本地檢查 `has_local_model() -> bool`（與 `is_model_downloaded()` 對齊）；`KnowledgeDBServiceWorker._run_sync_cycle` 保留背景受管執行緒自動下載模型機制（先完成 Stage 1 AST/BM25 落盤並釋放 `_index_lock`，再於 Stage 2 非阻塞執行 `download_model(force=False)`；若離線或下載失敗則標記狀態為 `DEGRADED_OFFLINE` 並於 60 秒冷卻後重試，成功補齊向量後轉為 `READY`）；將手動 `kdb model download` CLI 解耦為 `server_compatible: false`。 | P0 | [P00:DR-03] |
| **FR-05** | `IndexingPipeline._ensure_jit_index_ready` 前景 `search` 零搶鎖快速路徑 | 於 `knowledge_db/pipeline.py:IndexingPipeline._ensure_jit_index_ready` 建立非阻塞快速路徑：當磁碟已存在 `unified.index.bin.gz`（或記憶體已載入 `_unified_index`）且背景 `is_worker_running(self._storage_dir)` 為 `True`（或 `_index_lock` 已被背景持有）時，前景 `search` 直接載入既有索引快照（且當 `not emb_svc.has_local_model()` 時直接走純 BM25 零等待返回），不阻塞等待背景 Worker 釋放鎖或下載模型。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 熱派發任務執行期間同時有背景 `ServiceWorker` 執行緒讀取 `get_virtual_cwd()` 或呼叫 `log_info()` | 因熱派發使用 `bind_runtime_context` 與 `DebouncedIOStreamer`（皆基於 `contextvars.ContextVar`），背景執行緒完全不受前景請求之 `virtual_cwd`、`env` 或串流捕獲影響，背景日誌 100% 透過 `background_sink` 寫入 Server 日誌檔，零前景串音。 |
| **EC-02** | 離線環境下啟動 Server 與 `KnowledgeDBServiceWorker`，本地無 FastEmbed ONNX 模型權重 | Stage 1 AST/BM25 毫秒級完成並落盤釋放 `_index_lock`；Stage 2 於獨立受管執行緒嘗試自動下載失敗後捕獲例外、記錄背景日誌並將 Worker 狀態設為 `DEGRADED_OFFLINE`（60 秒退避），主執行緒與前景 `kdb search` 100% 零阻塞、零崩潰。 |
| **EC-03** | 背景 `KnowledgeDBServiceWorker` 正在執行耗時索引或模型下載時，前景併發執行 `yscb kdb search` | `_ensure_jit_index_ready` 偵測到 `bin_file.exists()` 且背景 Worker 運行中（或 `_index_lock` 非阻塞探測忙碌），立即跳過 `_consume_space_diff` 與鎖等待，直接讀取既有 `unified.index.bin.gz` 快照秒級返回搜尋結果。 |
| **EC-04** | `ServiceManager.stop_all()` 或 `BaseServiceWorker.stop()` 被重複呼叫或服務啟動拋出例外 | 具備完整冪等性（Idempotent Teardown），重複 `stop()` 安全無副作用；單一服務啟動失敗時隔離記錄 `log_error` 並標記 `STOPPED`，不阻斷其他常駐服務與 `WarmWorker` 就緒。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 離線預檢與前景延遲 | `EmbeddingService.has_local_model()` 純本地檔案檢查耗時 `< 1ms`，零網路 I/O；離線環境下前景 `search` 不因缺模型發生任何網路超時等待。 |
| **NFR-02** | 靜態守門合規 (`module:server`) | `ys_codebase/source/server/` 達成 0 處生產 `print()` / `logging.*`、0 處 `os.chdir()` / `os.getcwd()`、0 處 `os.environ` 執行期寫入、0 處頂層可變快取與 `global`、所有 `@dataclass` 100% 標註 `frozen=True`。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` Windows 命名空間與雙模組匯入陷阱**：`server/server/worker.py` 既可能以 `python worker.py` 作為子進程主腳本執行，也可能在測試中以 `from server.worker import WarmWorker` 匯入；頂層狀態與輔助函式必須確保無全域副作用。
- **`[!NOTE]` `ServerDaemonState` 與 `ServerConfig` 不可變契約**：將 `ServerDaemonState` 與 `ServerConfig` 標註 `@dataclass(frozen=True)` 時，須確認所有呼叫端皆為屬性讀取或 `asdict(state)`，無原地屬性賦值。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[MasterSupervisor (HTTP Control & Dispatch Queue)]
       │
       ├── stdin (NDJSON Action) ──► [WarmWorker Main Thread (Shell Execution Channel)]
       │                                  │
       │                                  ├── bind_runtime_context(virtual_cwd=cwd, env=env, ...)
       │                                  └── with DebouncedIOStreamer(ipc_pipe):
       │                                        └── dispatch_cli(module, args)
       │
       └── stdout (ipc_pipe NDJSON) ◄────┼── terminal_stream / task_finish (error_hint)
                                         └── touch_activity / log (from Background Service Threads)
                                                ▲
                                                │ bind_log_context(background_sink=ipc_log, component=svc.name)
                                     [ServiceManager & BaseServiceWorker Managed Threads]
                                       ├── CoreSpaceWatcherServiceWorker (STARTING -> READY -> STOPPED)
                                       ├── KnowledgeDBServiceWorker (STARTING -> UPDATING -> READY / DEGRADED_OFFLINE)
                                       │     ├── Stage 1: AST + BM25 Fast Sync (<100ms, releases _index_lock)
                                       │     └── Stage 2: Managed Thread Auto-Download & Micro-Batch Vectors
                                       └── GDriveSyncServiceWorker (READY standby / active -> STOPPED)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/server/server/worker.py` | Modify | 拔除 `sys.stdout = sys.stderr`、`os.getcwd()`、`os.chdir()` 與 `os.environ` 原地突變；改用 `bind_runtime_context`、`DebouncedIOStreamer` 與 `core.log` |
| `ys_codebase/source/server/server/service.py` | Modify | 擴充 `BaseServiceWorker` 內建受管執行緒生命週期、狀態機（`STARTING`/`UPDATING`/`READY`/`DEGRADED_OFFLINE`/`STOPPED`）與 `bind_log_context` 背景日誌隔離；收斂 `_LAST_TOUCH_TS` 頂層可變狀態並改用 `core.log` |
| `ys_codebase/source/server/server/space_watcher.py` | Modify | 對齊 `BaseServiceWorker` 狀態常數並將 `logging` 遷移至 `core.log` |
| `ys_codebase/source/server/server/master.py` | Modify | `ServerDaemonState` 標註 `frozen=True`；將前景 Banner `print` 遷移至 `core.log.log`；状态面板支援顯示服務 `state` |
| `ys_codebase/source/server/server/watcher.py` | Modify | 將 `logging.warning` 遷移至 `core.log.log_warn` |
| `ys_codebase/source/server/server/config.py` | Modify | `ServerConfig` 標註 `@dataclass(frozen=True)` |
| `ys_codebase/source/server/scripts/cli.py` | Modify | 將 `print` 與 `os.getcwd()` 遷移至 `core.log` 與 `core.context.get_virtual_cwd()`，並於 `server status` 呈現服務狀態（含 `DEGRADED_OFFLINE` 等） |
| `ys_codebase/source/file-space/scripts/hook.server.py` | Delete | 物理刪除舊版 `file-space` 啟動期野執行緒 Hook（消除 `GitignoreEvaluator` 警告） |
| `ys_codebase/source/knowledge-db/scripts/hook.server.py` | Delete | 物理刪除舊版 `knowledge-db` 啟動期野執行緒 Hook（統一由 `KnowledgeDBServiceWorker` 受管執行緒負責） |
| `ys_codebase/source/knowledge-db/contributes/core.json` | Modify | 將手動執行之 `model.cmd.download`（與 `model` 頂層說明）標註 `"server_compatible": false` |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | 新增 `< 1ms` 純本地模型檢查方法 `has_local_model() -> bool`（與 `is_model_downloaded()` 對齊） |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 對齊 `BaseServiceWorker` 受管執行緒與狀態機（`STARTING`/`UPDATING`/`READY`/`DEGRADED_OFFLINE`/`STOPPED`），保留受管執行緒 Stage 2 自動下載模型（離線時降級標記 `DEGRADED_OFFLINE`） |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 修復 `_ensure_jit_index_ready`：當已有索引快照且背景 Worker 運行或持鎖時，前景 `search` 非阻塞讀取既有索引，且於 `!has_local_model()` 時零等待退回 BM25 |
| `ys_codebase/source/gdrive-support/gdrive_support/service.py` | Modify | 對齊 `BaseServiceWorker` 狀態屬性（`state`）與受管執行緒回報 |
| `ys_codebase/source/core/core/context.py` | Modify | 於 `RuntimeContext` 擴充 `server_touch_lock` 與 `server_last_touch_by_root` 欄位 |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 新增並更新 `WarmWorker` 零全域突變（`virtual_cwd` / `env` 隔離、`get_last_error_hint`）與 `BaseServiceWorker` 狀態機/背景日誌隔離測試 |
| `ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | 驗證 `has_local_model()`、離線 `DEGRADED_OFFLINE` 狀態轉移、背景自動下載保留與前景 `search` 非阻塞快速路徑 |
| `ys_codebase/source/file-space/tests/test_service_and_cli.py` | Modify | 移除對已刪除 `scripts/hook.server.py` 之載入並斷言該野執行緒腳本維持移除 |
| `docs/server/README.md` | Modify | 同步更新三平面隔離、`BaseServiceWorker` 受管執行緒與狀態機說明 |
| `docs/knowledge-db/README.md` | Modify | 同步更新 `has_local_model()`、受管執行緒自動下載與 `DEGRADED_OFFLINE` 狀態說明 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `WarmWorker` 標準串流保真與控制通道物理隔離**：
  - 在 `worker_main()` 中不再將 `sys.stdout` 覆寫為 `sys.stderr`；`WarmWorker` 保存原始控制管線 `ipc_pipe` 供 NDJSON 封包寫入，並在非熱派發期間於執行緒預設掛載 `bind_log_context(background_sink=self._emit_ipc_log, component="worker")`，使任何非預期或背景 `core.log` 呼叫自動封裝為 `{"type": "log", ...}` 控制封包回傳 Master，而熱派發期間則由 `with streamer:` 精準捕獲前景輸出為 `terminal_stream` 封包。
- **[P02:DR-02] `BaseServiceWorker` 受管執行緒雙模式相容（繼承 `_run_loop` vs. 自訂 `start`）**：
  - `BaseServiceWorker` 提供原生 `start_managed_thread(target=..., name=...)` 與 `stop_managed_thread(timeout=...)` 以及預設 `start(context)`（若子類別定義 `_run_loop` 則自動以受管執行緒包覆 `bind_log_context` 啟動）；同時若子類別覆寫 `start(context)` 自行啟動執行緒或呼叫 `start_managed_thread`，`ServiceManager.start_all()` 亦會在呼叫 `worker.start(svc_context)` 時外包 `bind_log_context(background_sink=..., component=worker.name)`，因 `ContextVar` 在 `threading.Thread.start()` 或輔助封裝時可傳遞，確保 100% 背景執行緒皆受日誌隔離保護。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/server/server/service.py
class BaseServiceWorker:
    STATE_STARTING: str = "STARTING"
    STATE_UPDATING: str = "UPDATING"
    STATE_READY: str = "READY"
    STATE_DEGRADED_OFFLINE: str = "DEGRADED_OFFLINE"
    STATE_STOPPED: str = "STOPPED"

    @property
    def name(self) -> str: ...
    @property
    def state(self) -> str: ...
    def set_state(self, new_state: str) -> None: ...
    def start_managed_thread(
        self,
        target: Optional[Callable[[], None]] = None,
        *,
        name: Optional[str] = None,
    ) -> threading.Thread: ...
    def stop_managed_thread(self, timeout: float = 2.0) -> None: ...
    def start(self, context: Dict[str, Any]) -> None: ...
    def stop(self) -> None: ...
    def health_check(self) -> bool: ...
    def touch_activity(self) -> bool: ...

# ys_codebase/source/knowledge-db/knowledge_db/embedding.py
class EmbeddingService:
    def has_local_model(self) -> bool: ...
    def is_model_downloaded(self) -> bool: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `WarmWorker.execute_task` 捕獲 `SystemExit` 時提取整數退出碼，捕獲一般 `Exception` 時記錄錯誤並回傳 `exit_code=1`，最終必然發送 `task_finish` NDJSON 封包，絕不導致 Worker 進程崩潰退出。
  - `EmbeddingService.has_local_model()` 於任何檔案系統權限或路徑異常時安全回傳 `False`，絕不拋出未捕獲例外。
- **階段決策紀錄**：`[P03:DR-01]` `ServiceManager.get_status_list()` 回傳項目格式擴充為 `{"name": str, "provider": str, "alive": bool, "state": str}`，保留 `alive` 布林值以 100% 相容既有測試與狀態面板。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：刪除 `knowledge-db/scripts/hook.server.py` 後，原本在 `server_worker_warming` 事件中預載索引與檢查的行為由誰承接？*
  - *答*：`KnowledgeDBServiceWorker.start()` 在 `WarmWorker.initialize()` 階段即由 `ServiceManager.start_all()` 啟動專屬受管執行緒，直接執行首次 `_run_sync_cycle`（先載入/同步 Stage 1 AST/BM25 索引，再執行 Stage 2 模型檢查/自動下載與向量補齊），完全涵蓋原 `hook.server.py` 功能且具備受管生命週期與優雅停止能力。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/server/README.md` | Modify | 更新 `WarmWorker` 三平面隔離、`BaseServiceWorker` 受管執行緒與狀態機說明 |
| **專題手冊** | `docs/knowledge-db/README.md` | Modify | 更新 `has_local_model()` 離線預檢、背景受管執行緒自動下載與 `DEGRADED_OFFLINE` 狀態說明 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | N/A | 核心設計已收錄於模組手冊與主計畫報告 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `worker.py`、`service.py`、`embedding.py`、`pipeline.py` 公開介面 Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄 `sub_03` 變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認所有規格無歧義，進入 `Pre-Code Analyze Gate` 與實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：重構 `ys_codebase/source/server/`（`worker.py`、`service.py`、`space_watcher.py`、`master.py`、`watcher.py`、`config.py`、`scripts/cli.py`），落地三平面解耦、`BaseServiceWorker` 受管執行緒與狀態機，並達成 `server` 模組零 `print`/`logging`/`os.chdir`/`os.environ` 突變與 `@dataclass(frozen=True)`
- [x] **TASK-02**：物理刪除 `file-space/scripts/hook.server.py` 與 `knowledge-db/scripts/hook.server.py`，並更新 `gdrive_support/service.py` 對齊 `BaseServiceWorker` 狀態契約
- [x] **TASK-03**：於 `knowledge-db` 實作 `EmbeddingService.has_local_model()`、更新 `KnowledgeDBServiceWorker` 狀態機與受管執行緒自動下載降級（`DEGRADED_OFFLINE`）、將 `contributes/core.json` 之 `model.cmd.download` 設為 `server_compatible: false`，並修復 `IndexingPipeline._ensure_jit_index_ready` 前景 `search` 搶鎖阻塞
- [x] **TASK-04**：擴充並執行 `server`、`knowledge-db`、`file-space`、`gdrive-support` 單元與邊界測試（`FT-01` ~ `ET-04`），確保全量測試與 `dev check` 100% 通過
- [x] **TASK-DOC**：同步更新 `docs/server/README.md`、`docs/knowledge-db/README.md` 與微觀代碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
