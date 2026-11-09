# 成果展示與結案報告 (Walkthrough)

> 功能名稱：統一 Cell 生命週期快取原語、Epoch 世代常駐對稱與 Stage 耗時剖析器  
> 建立日期：2026-11-09  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`CellScope` 單次派發生命週期快取與防背景執行緒洩漏 (`FR-01`, `EC-01`, `[P01:DR-02]`)**：於 `core/context.py` 實作 `@dataclass(frozen=True)` 之 `CellScope`、`bind_cell_context`、`get_current_cell`、`get_or_compute_cell_state` 與 `invalidate_cell_state`。最外層 `bind_cell_context` 退出時強制將 `_state["closed"]` 設為 `True` 並清空快取字典，確保透過 `contextvars.copy_context()` 啟動的背景執行緒不會繼承已結束任務的凍結 `CellState`。
  2. **`EpochState` 跨 Cell 世代感知常駐快取 (`FR-02`, `EC-03`, `[P01:DR-03]`)**：於 `core/context.py` 實作 `get_or_compute_epoch_state(key, epoch_fn, builder_fn)` 與 `invalidate_epoch_state`；`epoch_fn()` 與 `builder_fn()` 100% 於鎖外執行以避免阻塞背景 `ServiceWorker`，並納入 `RuntimeContext.reset_all_caches()` 一鍵清空。
  3. **零配置 `cell_span` 階段耗時剖析與 `task_finish` IPC 顯影 (`FR-03`, `EC-02`, `[P01:DR-04]`)**：於 `dispatcher.py:dispatch_local` 綁定五大主幹階段（`pre_hooks`、`option_resolve`、`mod_load`、`cmd_exec`、`post_hooks`），於 8 大模組埋設 20 處子階段，並透過 `DebouncedIOStreamer.send_task_finish(..., stages=...)` 將 `cell.format_stages_summary()` 單向回傳至 `MasterSupervisor` 寫入 `.cache/server/log`。
  4. **全倉 8 大活躍模組 `Cell/Epoch` 收口、I/O 瓶頸根治與 `Mode A` 無損清理 (`FR-04`, `EC-04`, `NFR-01` ~ `NFR-02`)**：
     - 透過 `ArtifactCompiler._resolve_source_path` 優先以 `self.module_root` 直解 `module://` 及 `ensure_jit_release` 乾淨時間桶快取，將熱派發 `pre_hooks` 由 `130~280ms` 降至 **`7.1~8.6ms`**（`-94%~-97%`）。
     - 補齊 `CoreSpaceWatcherServiceWorker.project_root` 對齊 `is_watcher_active`、過濾 Linux `inotify` 唯讀 `opened`/`closed_no_write` 事件，並為 `CursorStore` 新增 `(mtime_ns, size)` 快取與 `set_cursor` 無變動寫入短路，使 `ast callers/callees/impact` 之 `ast.jit_sync` 由 `540~685ms`（8 次無變動 `fsync`）降至 **`3.2~4.2ms`**（`-99.3%`）。
     - 移除全倉 9 處 0-caller 死函式並收斂 `_trace_parser.py`（`-111 LOC`）。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/context.py` | Modify | 新增 `CellScope`、`bind_cell_context`、`get_or_compute_cell_state`、`get_or_compute_epoch_state` 與 `cell_span` |
| `ys_codebase/source/core/core/log.py` | Modify | `DebouncedIOStreamer.send_task_finish` 新增選填 `stages: Optional[str] = None` 參數 |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | `dispatch_local` 綁定 `bind_cell_context` 與五大基礎 `cell_span`，收口 `_read_server_spawn_config` 至 `CellState` |
| `ys_codebase/source/core/core/space/watcher.py` | Modify | `is_watcher_active` 支援讀取 `worker.project_root` 並將狀態檔 PID 探針收口至 `CellState` |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | `has_watcher_dirty_marker` 收口至 `CellState`；`CursorStore` 新增 `(mtime_ns, size)` 快取與 `set_cursor` 無變動短路；埋設 `cell_span("space.scan")` |
| `ys_codebase/source/core/core/space/{registry,schema}.py` | Modify | 移除 0-caller 死函式 `_expand_compose_children` 與 `is_dir_excluded` |
| `ys_codebase/source/core/core/{contributes,config,telemetry}.py` | Modify | `_get_mtime_fingerprint` 收口至 `EpochState`；移除 `_rotate_telemetry_file` 死代碼 |
| `ys_codebase/source/server/server/{worker,master,space_watcher}.py` | Modify | `execute_task` 包裹 `bind_cell_context` 並回傳 `stages`；`space_watcher` 補齊 `project_root`、過濾唯讀 `opened`/`closed_no_write` 事件並移除 `get_active_watcher_safe` |
| `ys_codebase/source/dev/dev/{builder,checker,testing/case,testing/sandbox}.py` | Modify | `sandbox._get_core_version` 收口至 `CellState`；埋設 `dev.check` 與 `dev.build` `cell_span` |
| `ys_codebase/source/ast/ast_engine/{bundler,engine,formatter,resolver}.py` & `scripts/cli.py` | Modify | `_get_or_create_resolver` 收口至 `EpochState`；埋設 `ast.jit_sync`、`ast.resolve`、`ast.outline` `cell_span`；移除 `_create_default_resolver_cache` 與 `_setup_stream_encodings` |
| `ys_codebase/source/knowledge-db/knowledge_db/{config,embedding,engine,formatter,pipeline,service}.py` | Modify | `_get_project_root` 與 `_load_persisted_state` 收口至 `CellState`；埋設 `kdb.jit_sync` 與 `kdb.search` `cell_span`；移除 `wait_for_worker_idle` |
| `ys_codebase/source/agents-workflow/agents_workflow/{compiler,publisher,plans/_trace_parser}.py` & `scripts/cli.py` | Modify | `publisher.py` 狀態全面收口至 `EpochState`（0 裸 `module_state`）；`_resolve_source_path` 優先直解 `self.module_root`；`_trace_parser.py` 收斂 `-111 LOC`；移除 `_setup_stream_encodings` |
| `ys_codebase/source/vscode-support/vscode_support/{projector,schema_compiler}.py` | Modify | 埋設 `vscode.sync` 與 `vscode.schema` `cell_span` |
| `ys_codebase/source/gdrive-support/gdrive_support/{__init__,coordinator,service}.py` | Modify | 埋設 `gdrive.sync` `cell_span` 並精簡 `service.py` 降級樣板 |
| `ys_codebase/source/core/tests/test_runtime_context.py` | Modify | 新增 `test_ft05_cell_scope_epoch_symmetry_and_stage_profiler` 單元測試 |
| `CHANGELOG.md`, `docs/core/{README,DESIGN_NOTES}.md`, `docs/server/{README,daemon_architecture}.md` | Modify | 三層文檔同步更新 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `python yscb.py dev check --all`：**9 Total, 9 Passed, 0 Warnings, 0 Failed**
  - 全倉 8 大活躍模組沙盒測試（`core`: 286/286、`server`: 65/65、`dev`: 110/110、`ast`: 40/40、`knowledge-db`: 113/113、`agents-workflow`: 145/145、`vscode-support`: 22/22、`gdrive-support`: 34/34）：合計 **815 / 815 Passed (100.0%)**
- **實機 UX / 人工驗證**：
  - 全數模組完成 `@build` 本機自部署，重啟常駐 Server Daemon 後連續調用 18 組常用 CLI 指令全數 `rc=0`，且 `.cache/server/log` 自動顯影 `[pre_hooks=..., cmd_exec=...]` 階段耗時明細（`pre_hooks` 穩定於 `~7.5ms`，`ast.jit_sync` 穩定於 `~3.2ms`）。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已交付 | 增補 `2026_11_08_1741_unified_cell_lifecycle_and_stage_profiler (Completed)` 完整變更紀錄 |
| **中觀 (Meso)** | `docs/core/README.md`, `docs/server/README.md` | 已交付 | 更新 `core.context` 之 `CellScope`、`EpochState`、`cell_span` 與 `WarmWorker` 階段耗時轉發說明 |
| **中觀 (Meso)** | `docs/server/daemon_architecture.md` | 已交付 | 更新 `task_finish` NDJSON 封包之 `stages` 欄位規格 |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md` | 已交付 | 新增 `[DN-21]`（`CellScope` 退場關閉防 `copy_context()` 洩漏、`EpochState` 鎖外求值與 `CursorStore` 無變動寫入短路） |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已交付 | `core/context.py`、`core/log.py`、`core/space/scanner.py` 等公開介面 Docstring 與型別契約 100% 對齊 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(core,server): add unified CellScope/EpochState caching, cell_span stage profiler, and Mode A cleanup across 8 modules

- Implement frozen CellScope, bind_cell_context (with is_closed guard against background copy_context leaks), get_or_compute_cell_state, lock-free get_or_compute_epoch_state, and cell_span in core.context
- Instrument dispatch_local with 5 backbone stages (pre_hooks, option_resolve, mod_load, cmd_exec, post_hooks) and forward stage summaries via DebouncedIOStreamer.send_task_finish to MasterSupervisor server log
- Optimize ArtifactCompiler._resolve_source_path via module_root and cache ensure_jit_release clean bucket via EpochState (reducing warm pre_hooks from ~220ms to ~7.5ms)
- Add project_root property on CoreSpaceWatcherServiceWorker, ignore read-only inotify opened/closed_no_write events, and short-circuit no-op CursorStore.set_cursor writes (reducing ast.jit_sync from ~580ms to ~3.2ms)
- Refactor non-local probes across 8 active modules to CellState/EpochState and remove 9 dead 0-caller functions + duplicate trace parser logic (-111 LOC)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
