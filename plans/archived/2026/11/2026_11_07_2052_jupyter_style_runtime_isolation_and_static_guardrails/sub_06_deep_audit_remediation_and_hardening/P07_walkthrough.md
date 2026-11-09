# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_06_deep_audit_remediation_and_hardening  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`core.log` 防抖、重入、背景第三方串流分流與 `--json` 純淨度加固（`FR-01`）**：消除 `RollingFileLogger.write_raw` 在 `echo_console=True` 且作為 `background_sink` 時的無限遞迴；移除 `_write_to_active_target` 對 `scope.streamer` 的無條件 `flush()` 以保留 500ms / 4KB 防抖合併；為 `DebouncedIOStreamer.start_capture()` 加入重入守衛與獨立 `error_chunks`；於 `_StreamProxy.write` 依 `_ACTIVE_LOG_SCOPE` 將背景執行緒之第三方原生輸出導向 `background_sink` 而不污染前景 `streamer` 與 `error_hint`；將 `_rotate_lines_file` 改用 `.split("\n")` 保留含 `\u2028`/`\u2029` 之單行 JSONL 並納入執行緒識別碼與鎖保護；於 `dispatcher.py` 與 `core/scripts/cli.py` 確保 `--json` 模式下抑制更新提示並輸出合法 `{}`。
  2. **`core.context`、`core.uri`、`core.loader` 熱重載穿透與 `get_env` 全倉收口（`FR-02`）**：將 `core/uri.py` 之 `RuntimeScope` (`ContextVar`) 優先級調高於 `uri_tls` (`threading.local`)，並於 `RuntimeContext.reset_all_caches()` 清理 `uri_tls`/`uri_reentrancy` 並委派 `core.loader.clear_loaded_modules()` 同步清除模組與 `alias_keys`；移除 `dispatcher.py` 與 `symbols.py` 對檔案 `(mtime_ns, size)` 世代檢查之快取短路；將全倉殘留 14 處 `os.environ` 讀取統一收口至 `get_env` / `get_env_snapshot`；補齊 `SpaceConfig.__post_init__` 6 個 tuple 欄位正規化、凍結 `@dataclass` 可變容器欄位 `compare=False`（確保 hashability）與 `_ConfigManagerMeta`/`_ContributesValidatorMeta` property setter。
  3. **`server` 跨執行緒 `ContextVar` 傳播、服務狀態同步與五態機收斂（`FR-03`）**：於 `server/worker.py:worker_main` 綁定常駐預設上下文；於 `BaseServiceWorker.start_managed_thread`、Watchdog `_CoreSpaceWatchdogHandler` 與 `gdrive-support` `ThreadPoolExecutor` 統一透過 `contextvars.copy_context().run` 及 `bind_worker_context` 傳播 `RuntimeScope` 與 `LogExecutionScope`；將 `ServiceManager._lock` 升級為 `threading.RLock()` 並透過 `service_status` IPC 封包即時同步 `MasterSupervisor._worker_services` 狀態；對齊 `CoreSpaceWatcherServiceWorker` 與 `GDriveSyncServiceWorker` 五態轉換。
  4. **上層業務模組 `FrozenInstanceError` / `TypeError` 修復、KDB 零阻塞檢索與 `stderr` 保真（`FR-04`）**：修復 `file-space/file_space/manager.py` 單空間權重 `dataclasses.replace`、`knowledge-db/scripts/hook.core.py` `scanner.ack(generation=...)` 與 `ast/ast_engine/engine.py` `_load_snapshot_state`/`get_cursor` 契約；於 `knowledge-db` 將 `has_local_model()` 與 `downloading_model`/`degraded_offline` 檢查前置至 `wait_until_worker_idle` 之前，使離線環境下 `kdb search` 與 `kdb model status` 0ms 瞬時返回；將 `knowledge-db`（29 處）與 `ast`（16 處）內部診斷日誌分流至 `stream="stderr"`。
  5. **`module:dev` 靜態守門規則補完、沙盒測試隔離修復與測試強化（`FR-05`）**：於 `dev/dev/tester.py` 補上 `YSCB_TEST_SANDBOX` 離線守門；將 `dev/dev/checker.py` (`_SourceGuardrailVisitor`) 別名追蹤升級為作用域堆疊，補齊 `D10` (`sys.argv`/`importlib.reload`)、`F13` (`urlopen` 缺 `timeout=`、`shell=True`、`timeout=None`)、`E12`（僅攔截 `os.rename`/`os.renames`/`Path.rename`）、`B4` 提示修正、`C8`/`C9` 拆包與 `ClassVar` 檢查，並堵住 `_check_sandbox_hooks` 頂層賦值與參數檢查漏洞。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/log.py` | Modify | 修復 `RollingFileLogger.write_raw` 遞迴、防抖擊穿、`start_capture` 重入、`_StreamProxy` 背景分流、`isolated_error_scope` 與 `_rotate_lines_file` `.split("\n")` |
| `ys_codebase/source/core/core/{uri,context,loader,symbols,config,validator,locale,telemetry,update_checker}.py` | Modify | 調升 `RuntimeScope` 優先級、`reset_all_caches` 委派 `clear_loaded_modules`、`alias_keys` 回滾、檔案世代熱重載穿透、`get_env` 收口、凍結 dataclass `compare=False` 與 Metaclass setter |
| `ys_codebase/source/core/core/commands/{dispatcher,registry,bags}.py` & `platform/{process,venv}.py` & `space/{schema,scanner,watcher}.py` & `scripts/cli.py` | Modify | 移除 `dispatcher` `mod_cache` 短路、`--json` 抑制更新提示、`spawn_detached` 改用 `get_env_snapshot`、`SpaceConfig` tuple 正規化與 `config_list --json` 修復 |
| `ys_codebase/source/core/tests/{test_log,test_runtime_context,test_symbols,test_cli_router}.py` | Modify | 新增 `FT-01` 與 `FT-02` 正負向單元與回歸測試 |
| `ys_codebase/source/server/server/{worker,service,master,space_watcher}.py` & `tests/{test_server,test_space_watcher}.py` | Modify | 落地 `worker_main` 常駐上下文、`start_managed_thread` 與 Watchdog `contextvars.copy_context()` 傳播、`ServiceManager` `RLock` 與 `service_status` IPC 同步及 `FT-03` 測試 |
| `ys_codebase/source/gdrive-support/gdrive_support/{service,coordinator,transport}.py` & `scripts/cli.py` & `tests/{test_atomic_api_and_config,test_branch_and_sync_engine}.py` | Modify | `ThreadPoolExecutor` 跨執行緒上下文傳播、`GDriveSyncServiceWorker` 狀態對齊、`GDriveConfig` `dataclasses.replace` 與 OAuth `stderr` 分流 |
| `ys_codebase/source/file-space/file_space/{__init__,manager,schema}.py` & `tests/test_file_space_manager.py` | Modify | 修復單空間權重 `dataclasses.replace`、`globals().pop` 單例同步與 `FileSpaceConfig` hashability 測試 |
| `ys_codebase/source/knowledge-db/knowledge_db/{embedding,engine,pipeline,hybrid,service,schema}.py` & `scripts/hook.core.py` & `tests/test_service_worker.py` | Modify | 修復 `hook.core.py` `generation=`、前置 `has_local_model()` 消除離線 3 秒等待、`model_status` 純本地返回、29 處診斷 `stream="stderr"` 與共享單例覆寫保護 |
| `ys_codebase/source/ast/ast_engine/{engine,schema,bundler}.py` & `parsers/{registry,treesitter}.py` & `scripts/hook.core.py` & `tests/{test_ast_engine,test_provisioner_and_jit}.py` | Modify | 修復 `_load_snapshot_state`/`get_cursor`、`UnifiedSymbol` tuple 正規化、16 處 `log_warn(..., stream="stderr")` 與 `UNIFIED_KEY` 游標對齊 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py` & `scripts/hook.core.py` & `tests/{test_plans_toolchain,test_publisher}.py` | Modify | `session_trace.py` 改用 `get_env`、`hook.core.py` 錯誤導向 `stderr` 與對應測試對齊 |
| `ys_codebase/source/dev/dev/{checker,tester}.py` & `testing/sandbox.py` & `tests/{test_checker,test_tester}.py` | Modify | 補齊 `Tester` 沙盒守門、`_SourceGuardrailVisitor` 作用域別名堆疊、`D10`/`F13`/`E12`/`B4`/`C8`/`C9`、`_check_sandbox_hooks` 強化與 `FT-05` 測試 |
| `docs/dev/architecture.md`, `docs/server/hot_reload_and_services.md`, `CHANGELOG.md` | Modify | 同步三層架構文檔與全域發布日誌 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - 全倉 9 大模組靜態合規檢核（`python yscb.py dev check --all`）：**`9 Total, 9 Passed, 0 Warnings, 0 Failed`**。
  - 全倉 9 大模組沙盒測試套件：**共 828 項測試，100.0% Passed (`Fail: 0, Skip: 0`)**（`core` 284/284、`dev` 109/109、`server` 64/64、`file-space` 19/19、`ast` 38/38、`knowledge-db` 113/113、`agents-workflow` 145/145、`vscode-support` 22/22、`gdrive-support` 34/34）。
- **實機 UX / 人工驗證**：
  - `UX-01`：開發者確認標記為 **`[跳過/免測]`**（已由自動化測試與實機 `dev check --all` 100% 覆蓋）。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已交付 | 頂部新增 `sub_06` 實作後深潛審計 21 項缺口閉環修補與全倉 13 項 AST 靜態守門加固紀錄 |
| **中觀 (Meso)** | `docs/dev/architecture.md` | 已交付 | 同步更新 `_SourceGuardrailVisitor` 作用域別名堆疊、`D10` (`sys.argv`/`reload`)、`F13` (`urlopen`/`shell=True`/`timeout=None`)、`E12` 精準化與 `_check_sandbox_hooks` 規範 |
| **中觀 (Meso)** | `docs/server/hot_reload_and_services.md` | 已交付 | 同步更新 `BaseServiceWorker` 跨執行緒 `contextvars.copy_context()` 繼承契約與 `service_status` IPC 狀態同步機制 |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md` | 免更 | 既有設計筆記無衝突，無新增反直覺工程妥協（防膨脹守門） |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已交付 | 嚴格維護 `BaseServiceWorker.bind_worker_context` / `start_managed_thread` 等公開介面 Docstring，且生產代碼 0 工單編號殘留 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(runtime,dev): remediate 21 post-audit isolation gaps and harden AST static guardrails

- Fix core.log RollingFileLogger echo_console recursion, preserve 500ms/4KB debounce in _write_to_active_target, guard start_capture reentrancy, route background _StreamProxy writes to background_sink, and split lines by '\n' in _rotate_lines_file
- Prioritize RuntimeScope ContextVar over uri_tls in core.uri, delegate module cache reset to core.loader.clear_loaded_modules with alias rollback, enforce (mtime_ns, size) hot-reload checks in dispatcher and symbols, and migrate 14 remaining os.environ reads to get_env/get_env_snapshot
- Propagate RuntimeScope and LogExecutionScope across BaseServiceWorker managed threads, Watchdog callbacks, and gdrive-support ThreadPoolExecutor via contextvars.copy_context().run, and sync worker service_status packets to MasterSupervisor
- Fix FileSpaceConfig weight dataclasses.replace, knowledge-db hook.core.py ack(generation=...), non-blocking offline vector fallback in kdb search/model status, ASTEngine cursor/snapshot resolution, and stderr diagnostic routing
- Harden dev/checker.py _SourceGuardrailVisitor with lexical scope alias stacks, D10 sys.argv/importlib.reload checks, F13 urlopen/shell=True/timeout=None checks, precise E12 rename detection, C8/C9 tuple-unpacking and ClassVar checks, and strict hook.dev.py signature validation
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
