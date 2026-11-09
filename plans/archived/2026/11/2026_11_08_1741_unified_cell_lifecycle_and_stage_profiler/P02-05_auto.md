# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：統一 Cell 生命週期快取原語、Epoch 世代常駐對稱與 Stage 耗時剖析器  
> 建立日期：2026-11-08  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

> 完整需求規格已定義於 [P01_requirements_spec.md](./P01_requirements_spec.md)（涵蓋 `FR-01` ~ `FR-04`、`EC-01` ~ `EC-04`、`NFR-01` ~ `NFR-02` 與 `[P01:DR-01]` ~ `[P01:DR-05]`）。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Host Runner: Cold CLI or WarmWorker.execute_task]
  └── with bind_cell_context(module_name, command, reuse_existing=True) as cell:
        ├── dispatch_local(...)
        │     ├── with cell_span("pre_hooks"):    _ensure_hooks("pre_cli_dispatch")
        │     ├── with cell_span("option_resolve"): OptionResolver.resolve(...)
        │     ├── with cell_span("mod_load"):     load_module_from_path(...)
        │     ├── with cell_span("cmd_exec"):     fn(cmd_bags)
        │     │     ├── get_or_compute_cell_state(key, builder_fn)  [Cell-Scoped Memoization]
        │     │     ├── get_or_compute_epoch_state(key, epoch_fn, builder_fn) [Lock-Free Epoch Cache]
        │     │     └── with cell_span("<mod>.<stage>"): ...
        │     └── with cell_span("post_hooks"):   _ensure_hooks("post_cli_dispatch")
        └── finally (outermost):
              cell.mark_closed_and_clear_cache()  [Prevents background thread copy_context() leak]
  └── stages_summary = cell.format_stages_summary()
        └── DebouncedIOStreamer.send_task_finish(..., stages=stages_summary)
              └── MasterSupervisor logs: "Task dispatch finished: ... [pre_hooks=..., cmd_exec=...]"
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/context.py` | Modify | 新增 `@dataclass(frozen=True)` 之 `CellScope`、`bind_cell_context`、`get_current_cell`、`get_or_compute_cell_state`、`invalidate_cell_state`、`get_or_compute_epoch_state`、`invalidate_epoch_state` 與 `cell_span` |
| `ys_codebase/source/core/core/log.py` | Modify | `DebouncedIOStreamer.send_task_finish` 支援選填 `stages: Optional[str] = None` 夾帶至 `task_finish` IPC 封包 |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | `dispatch_local` 綁定 `bind_cell_context` 與五大基礎 `cell_span`（`pre_hooks`、`option_resolve`、`mod_load`、`cmd_exec`、`post_hooks`），並將 `_read_server_spawn_config` 收口至 `get_or_compute_cell_state` |
| `ys_codebase/source/core/core/space/watcher.py` | Modify | `is_watcher_active` 支援讀取 `worker.project_root` 並將 `state_file` 探針收口至 `get_or_compute_cell_state` |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | `has_watcher_dirty_marker` 收口至 `get_or_compute_cell_state`，`CursorStore` 新增 `(mtime_ns, size)` 記憶體快取與 `set_cursor` 無變動短路防呆，並埋設 `cell_span("space.scan")` |
| `ys_codebase/source/core/core/space/registry.py` | Modify | `compute_config_hash` 收口至 `get_or_compute_cell_state` |
| `ys_codebase/source/core/core/uri.py` | Modify | `_resolve_config_uri_token` 收口至 `get_or_compute_cell_state`，移除冗餘轉發空殼 `_clear_caches_internal` |
| `ys_codebase/source/core/core/contributes.py` | Modify | `_get_mtime_fingerprint` 收口至 `get_or_compute_cell_state` |
| `ys_codebase/source/server/server/worker.py` | Modify | `WarmWorker.execute_task` 外層包裹 `bind_cell_context` 並傳遞 `stages` 摘要；`get_active_service_manager` 收口至 `get_or_compute_epoch_state` |
| `ys_codebase/source/server/server/master.py` | Modify | `_dispatch_to_worker` 解析 `task_finish` 之 `stages` 與 `args` 並輸出至 `Task dispatch finished` 日誌 |
| `ys_codebase/source/server/server/space_watcher.py` | Modify | 新增 `project_root` 屬性對齊 `is_watcher_active`；忽略 Linux `inotify` 唯讀 `opened`/`closed_no_write` 事件；`_get_active_watcher_instance` 收口至 `get_or_compute_epoch_state` |
| `ys_codebase/source/server/server/config.py` | Modify | `ServerConfig.load` 收口至 `get_or_compute_cell_state` |
| `ys_codebase/source/dev/dev/checker.py` | Modify | `check_all` / `check_module` 埋設 `cell_span("dev.check")` |
| `ys_codebase/source/dev/dev/runner.py` | Modify | `run_tests` 埋設 `cell_span("dev.test")` |
| `ys_codebase/source/dev/dev/packager.py` | Modify | `build_module` 埋設 `cell_span("dev.build")` |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | `_get_default_engine_instance` 收口至 `get_or_compute_epoch_state`；`get_persisted_meta` 收口至 `get_or_compute_cell_state`；埋設 `cell_span("ast.jit_sync")`、`cell_span("ast.build")`、`cell_span("ast.outline")` |
| `ys_codebase/source/ast/ast_engine/resolver.py` | Modify | `_get_or_create_resolver` 收口至 `get_or_compute_epoch_state` 並埋設 `cell_span("ast.resolve")` |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | `_get_or_create_default_bundler` 收口至 `get_or_compute_epoch_state` |
| `ys_codebase/source/ast/ast_engine/parsers.py` | Modify | `_get_or_create_default_registry` 收口至 `get_or_compute_epoch_state` |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | `get_engine` 收口至 `get_or_compute_epoch_state`；`get_persisted_meta` 收口至 `get_or_compute_cell_state`；埋設 `cell_span("kdb.build")` |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 埋設 `cell_span("kdb.jit_sync")` 與 `cell_span("kdb.search")` |
| `ys_codebase/source/knowledge-db/knowledge_db/embedder.py` | Modify | `_get_shared_onnx_session` 收口至 `get_or_compute_epoch_state` |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | `get_active_worker` 收口至 `get_or_compute_epoch_state` |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | `_resolve_source_path` 優先透過 `self.module_root` 直接解析 `module://agents-workflow/...` 避免跨模組 URI 重載；`compile_all` 埋設 `cell_span("aw.compile")` |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | `_load_source_sha1_cache`、`.gitignore` 指紋與 `ensure_jit_release` 乾淨桶收口至 `get_or_compute_epoch_state`；埋設 `cell_span("aw.jit_release")` 與 `cell_span("aw.release")` |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/manager.py` | Modify | `PlanManager._load_config` 收口至 `get_or_compute_cell_state`；`verify_plan` 埋設 `cell_span("aw.plan_verify")` |
| `ys_codebase/source/vscode-support/vscode_support/projector.py` | Modify | `_load_module_config` 收口至 `get_or_compute_cell_state`；埋設 `cell_span("vscode.sync")` |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | Modify | `load_gdrive_config` 收口至 `get_or_compute_cell_state` |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | Modify | `pull` / `push` / `sync` 埋設 `cell_span("gdrive.pull" / "gdrive.push" / "gdrive.sync")` |
| `ys_codebase/source/core/tests/test_context_isolation.py` | Modify | 新增 `CellScope`、`get_or_compute_cell_state`、背景執行緒 `copy_context()` 防洩漏、`get_or_compute_epoch_state` 鎖外求值與 `cell_span` 單元測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** `CellScope` 遵循 `C9` 宣告為 `@dataclass(frozen=True)`，內部以 `_state: Dict[str, Any]`（`compare=False`）封裝 `"closed": False`、`"cache": {}` 與 `"stages_ms": {}`；最外層退出時設 `"closed": True` 並 `.clear()` 快取字典，使任何透過 `contextvars.copy_context()` 繼承該 `CellScope` 的背景執行緒在呼叫 `get_current_cell()` 時立即判定為 `None`。
- **[P02:DR-02]** `get_or_compute_epoch_state` 將狀態儲存於 `RuntimeContext.epoch_states: Dict[str, Tuple[Any, Any]]`（受獨立輕量 `epoch_states_lock` 保護，並在 `reset_all_caches()` 中 `.clear()`），且 `epoch_fn()` 與 `builder_fn()` 均在鎖外執行，100% 避免阻塞背景 `ServiceWorker`。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# module:core - core/context.py
@dataclass(frozen=True)
class CellScope:
    cell_id: int
    module_name: Optional[str] = None
    command: Optional[str] = None
    _state: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def is_closed(self) -> bool: ...
    def record_stage_ms(self, stage_name: str, elapsed_ms: float) -> None: ...
    def format_stages_summary(self, min_ms: float = 0.5) -> str: ...
    def close_and_clear_cache(self) -> None: ...

def get_current_cell() -> Optional[CellScope]: ...

@contextmanager
def bind_cell_context(
    *,
    module_name: Optional[str] = None,
    command: Optional[str] = None,
    reuse_existing: bool = True,
) -> Iterator[CellScope]: ...

def get_or_compute_cell_state(key: Any, builder_fn: Callable[[], Any]) -> Any: ...
def invalidate_cell_state(key_or_prefix: Optional[Any] = None) -> None: ...

def get_or_compute_epoch_state(
    key: str,
    epoch_fn: Callable[[], Any],
    builder_fn: Callable[[], Any],
) -> Any: ...
def invalidate_epoch_state(key: Optional[str] = None) -> None: ...

@contextmanager
def cell_span(stage_name: str) -> Iterator[None]: ...

# module:core - core/log.py
class DebouncedIOStreamer:
    def send_task_finish(
        self,
        exit_code: int,
        duration_ms: float,
        error: Optional[str] = None,
        stages: Optional[str] = None,
    ) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `get_or_compute_cell_state` 與 `get_or_compute_epoch_state` 不吞掉 `builder_fn()` 拋出之業務例外；若 `builder_fn()` 拋出例外，該次未成功結果絕不寫入快取。
  - `cell_span` 在區塊內部拋出例外或 `SystemExit` 時，仍於 `finally` 記錄已耗費毫秒數並向上原樣傳遞例外。
- **階段決策紀錄**：`[P03:DR-01]` `DebouncedIOStreamer.send_task_finish` 新增選填參數 `stages: Optional[str] = None`，向後相容所有既有呼叫端。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：若 `builder_fn()` 內部又巢狀呼叫了另一個 `get_or_compute_epoch_state`，是否會造成鎖死？*
  - *答*：因為 `epoch_fn()` 與 `builder_fn()` 均在鎖外執行，且 `epoch_states_lock` 採用可重入 `threading.RLock()` 並僅在短暫字典讀寫時持鎖，100% 無死鎖風險。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md`、`docs/server/README.md` | Modify | 補充 `CellScope`、`EpochState` 與 `cell_span` 階段剖析說明 |
| **專題手冊** | `docs/server/daemon_architecture.md` | Modify | 更新 `task_finish` 階段耗時顯影機制 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify / N/A | 視需要補充 `CellScope` 關閉防背景執行緒洩漏說明 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新關鍵介面契約與模組 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄本版本發布摘要 |

- **決策定稿**：**[P04:DR-01]** 確認通過 Pre-Code Analyze Gate，並於階段二啟動多路 `/blind-subagent` 對全專案 8 大模組（排除已廢除之 `file-space`）執行深度排查與 `Mode A` 無損清理。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `module:core` 之 `CellScope`、`bind_cell_context`、`get_or_compute_cell_state`、`get_or_compute_epoch_state`、`cell_span`、`DebouncedIOStreamer.send_task_finish(..., stages=...)`、`dispatcher.py` 五大基礎 Stage 與 `watcher.py` 探針收口，並接入 `module:server` (`worker.py` / `master.py`)
- [x] **TASK-02**：分批派發多路 `/blind-subagent` 對全專案 8 大活躍模組（`core`、`server`、`dev`、`ast`、`knowledge-db`、`agents-workflow`、`vscode-support`、`gdrive-support`）進行非局部狀態 `Cell/Epoch` 收口、硬編碼移除與 `/code-optimizer` `Mode A` 死代碼排查並落實重構
- [x] **TASK-03**：撰寫單元測試，執行全倉 `dev check --all` 與 8 大模組 `dev test <mod> -q --sync` 本機自部署，重啟常駐 Server 並對所有常用 CLI 執行調用實測與 Stage 耗時剖析紀錄
- [x] **TASK-DOC**：同步更新模組微觀 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
