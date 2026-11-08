# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_06_deep_audit_remediation_and_hardening  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core.log` 防抖、重入、背景第三方串流分流與 `--json` 純淨度加固 (`P0-06`, `P1-07`) | 1. `RollingFileLogger.write_raw` 在 `scope.background_sink is self` 時直接寫入底層 `sys.stdout`，消除 `echo_console=True` 無限遞迴。<br>2. `_write_to_active_target` 寫入 `scope.streamer` 時不立即呼叫 `streamer.flush()`，保留 500ms / 4KB 防抖合併；`DebouncedIOStreamer.start_capture()` 加入重入守衛並強制 `background_sink=None`、獨立 `error_chunks=[]`。<br>3. `_StreamProxy.write` 檢查 `_ACTIVE_LOG_SCOPE.get()`：若存在 `background_sink` 則轉寫入背景日誌而不污染前景 `streamer` 與 `error_hint`；`isolated_error_scope=True` 時不寫入/不清空全域 `ctx.log_error_chunks`。<br>4. `_rotate_lines_file` 改用 `.split("\n")` 避免切碎含 `\u2028`/`\u2029` 之 JSONL，暫存檔名納入 `threading.get_ident()` 且於內部加鎖。<br>5. `dispatcher.py` 在 `argv` 含 `--json`/`-j` 時跳過 `print_tips_if_available()`；`core/scripts/cli.py:config_list` 在 `--json` 且無組態時直接輸出 `{}`。 | P0 | [P00:DR-03] |
| **FR-02** | `core.context`、`core.uri`、`core.loader` 熱重載穿透与 `get_env` 全倉收口 (`P0-04`, `P0-05`, `P1-08`, `P1-09`, `P2-02`) | 1. `core/uri.py` 將 `RuntimeScope` (`ContextVar`) 優先級調高於 `uri_tls` (`threading.local`)，並於 `RuntimeContext.reset_all_caches()` 清空 `uri_tls.__dict__.clear()` 與 `uri_reentrancy.__dict__.clear()`。<br>2. `dispatcher.py:L650-668` 移除無世代檢查之 `mod_cache` 短路（僅保留對非 loader 注入之白箱測試 mock 短路），每次派發調用 `load_module_from_path(..., reload_if_changed=True)`；`symbols.py:resolve_callable` 對檔案型符號驗證 `(mtime_ns, size)` 世代指紋，消除 Track 1 與 `callable_cache` 短路；`core/loader.py` 追蹤 `alias_keys` 並於清理/回滾時同步還原。<br>3. 將 `core/platform/process.py:L128` (`spawn_detached`) 改為 `dict(get_env_snapshot())`、`core/locale.py:L204` 改為 `get_env_snapshot()`，並將 `core`、`agents-workflow`、`knowledge-db` 共 14 處 `os.environ.get(...)` 統一改為 `get_env(...)`。<br>4. 為含可變容器欄位之 `@dataclass(frozen=True)` 設定 `eq=False`（或容器欄位 `compare=False`）消除 `unhashable type`，補齊 `SpaceConfig.__post_init__` 6 個 tuple 欄位正規化，並為 `_ConfigManagerMeta` 與 `_ContributesValidatorMeta` 補齊 property setter。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | `server` 跨執行緒 `ContextVar` 傳播、服務狀態同步與五態機收斂 (`P0-04`, `P1-06`) | 1. `server/worker.py:worker_main` 外層常駐包裹預設 `bind_runtime_context` 與 `bind_log_context(background_sink=worker._ipc_log_sink, isolated_error_scope=True)`。<br>2. `BaseServiceWorker.start_managed_thread`、Watchdog `_CoreSpaceWatchdogHandler` 回呼入口與 `gdrive-support` 之 `ThreadPoolExecutor` 任務提交統一透過 `contextvars.copy_context().run` 並綁定 `bind_runtime_context` 與 `bind_worker_log_context`。<br>3. 當 `BaseServiceWorker.set_state` 狀態改變（或於 `task_finish` / 控制通道）時向 `MasterSupervisor` 同步最新 `services` 清單以更新 `self._worker_services`；對齊 `GDriveSyncServiceWorker.start()`、`CoreSpaceWatcherServiceWorker.stop()` (`self._thread = None`) 與 `flush_space_now()` 之五態轉換。 | P0 | [P00:DR-01] |
| **FR-04** | 上層業務模組 `FrozenInstanceError` / `TypeError` 修復、KDB 零阻塞檢索與 `stderr` 保真 (`P0-01`~`P0-03`, `P0-06`, `P1-05`, `P1-10`, `P2-01`~`P2-04`) | 1. `file-space/file_space/manager.py:L232` 改用 `dataclasses.replace(cfg, weight=float(w))`；`file_space/__init__.py` 補上 `globals().pop("_DEFAULT_MANAGER")` / `globals().pop("_DEFAULT_SCANNER")`。<br>2. `knowledge-db/scripts/hook.core.py:L58` 將 `to_generation=` 修正為 `generation=`；`pipeline.py:L1148-1153` 刪除重複游標重置區塊；`pipeline.py:_resolve_vector_availability_with_worker_tolerance` 將 `has_local_model()` 與 `downloading_model`/`degraded_offline` 檢查移至 `wait_until_worker_idle` 之前；`engine.py:model_status()` 在 `!has_local_model()` 時直接回傳靜態字典不觸發 `_ensure_model()`。<br>3. `ast/ast_engine/engine.py:L577, L632` 移除不存在之 `is_ephemeral=` 參數、讀取 `head_generation` 並正確解析 `get_cursor()` 回傳字典；`schema.py:UnifiedSymbol.__post_init__` 雙向正規化 `children`/`members`/`parameters` 為 `tuple`。<br>4. 為 `knowledge-db`（29 處，含 `embedding.py` 5 處）與 `ast`（16 處）內部診斷 `log_warn`/`log_info` 補上 `stream="stderr"`；於 `ast_engine.get_engine()` 與 `knowledge_db.get_engine()` 檢驗 `project_root` 一致性並讓 `KnowledgeEngine` 預設複用 `get_default_registry()`、`get_default_scanner()` 與 `ast_engine.get_engine()`。 | P0 | [P00:DR-03] |
| **FR-05** | `module:dev` 靜態守門規則補完、沙盒測試隔離修復與測試強化 (`P1-01`~`P1-04`, `P2-05`) | 1. `dev/dev/tester.py:L735` 補上 `if not is_nested and get_env("YSCB_TEST_SANDBOX") != "1":` 守門，並於 `dev/tests/test_tester.py:L168` mock `adapt_build_pip_dependencies`，使離線標準庫環境下 `dev test dev` 109/109 全過。<br>2. `dev/dev/checker.py` (`_SourceGuardrailVisitor`)：將別名追蹤改為作用域堆疊；補齊 `D10` 對 `sys.argv` 改寫與 `importlib.reload()` 之攔截；補齊 `F13` 對 `urllib.request.urlopen` 缺 `timeout=`、`subprocess.*(..., shell=True)` 與 `timeout=None` 之攔截；將 `E12` 限縮為 `os.rename/renames` 與 `Path.rename`（不誤殺自訂 `.rename()`）；修正 `B4` 提示為 `core.context.get_virtual_cwd()`；於 `C8`/`C9` 支援拆包賦值目標檢查與 `@dataclass(frozen=True)` 內 `ClassVar` 可變屬性檢查。<br>3. `Checker._check_sandbox_hooks`（`L1600-1630`）：移除頂層 `ast.Assign`/`ast.AnnAssign` 無條件 `continue`（僅允許常數或同步原語賦值），將參數檢查納入 `posonlyargs`、排除單純 `**kwargs` 並涵蓋所有候選事件函式名。<br>4. `dev/dev/testing/sandbox.py:L75` 模板 `print` 改為 `core.log.log`，並強化 `dev/tests/test_checker.py` 精確行號與新子項正負向斷言。 | P0 | [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 在常駐 `WarmWorker` 中執行 `--json` 命令時適逢 12 小時版本更新提示或本地未下載 KDB 向量模型 | 更新提示在 `--json` 模式下自動抑制，KDB 向量模型降級提示走 `stream="stderr"`（且 `model status` 不觸發模型載入），確保 `stdout` 100% 為合法 JSON。 |
| **EC-02** | 業務代碼中一般類別定義 `.rename()` 方法（如分支或節點改名），或局部函式內 `import` 同名變數 | `E12` 僅攔截 `os.rename`/`os.renames`/`Path.rename`（或明確的 Path 變數），不誤殺自訂方法；作用域堆疊確保局部 `import` 不污染其他函式。 |
| **EC-03** | 背景 `CoreSpaceWatcher` 之 Watchdog `Observer` 執行緒或 `GDriveSync` 之 `ThreadPoolExecutor` 衍生子執行緒呼叫 `core.uri` 或 `core.log` | 透過 `contextvars.copy_context().run` 與入口上下文綁定，所有衍生子執行緒均能正確讀取 `RuntimeScope` 之 `host_dir`/`yscb_dir`/`virtual_cwd` 並將日誌導向背景 `RollingFileLogger` / IPC `log` 封包。 |
| **EC-04** | 白箱單元測試透過 `patch.dict("core.commands.dispatcher._MODULE_CACHE", ...)` 或 `file_space._DEFAULT_MANAGER = None` 注入/重置狀態 | `dispatcher.py` 識別非 `core.loader` 快取之注入物件並保留相容性；`file_space/__init__.py` 與 `core` 各模組在讀取時自動將 `globals()` 覆寫同步回 `RuntimeContext` 並 `pop` 清除，防止遮蔽 PEP 562 `__getattr__`。 |
| **EC-05** | 在無網路且無 `ensurepip` 的純標準庫沙盒環境執行 `python yscb.py dev test dev -q` | `Tester._run_parallel_test` 檢測到 `is_nested` 或 `YSCB_TEST_SANDBOX == "1"` 時跳過 `adapt_build_pip_dependencies`，109/109 測試 100% 通過。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 離線檢索反應延遲 | 當本地無向量模型（`!has_local_model()`）時，無論背景 `KnowledgeDBServiceWorker` 是否正在嘗試下載模型，前景 `yscb kdb search` 與 `yscb kdb model status` 均須在 $< 50\text{ ms}$ 內完成非阻塞降級返回（零 `wait_until_worker_idle` 3 秒等待）。 |
| **NFR-02** | 全倉合規與測試通過率 | 全倉 9 大模組 `python yscb.py dev check --all` 維持 `9 Passed, 0 Warnings, 0 Failed`，且全倉沙盒單元測試 100% 通過。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** Python 標準庫的 `threading.Thread(target=...).start()` 與 `concurrent.futures.ThreadPoolExecutor.submit(...)` 預設**不會**複製呼叫端執行緒的 `contextvars.ContextVar`！必須在父執行緒呼叫 `ctx = contextvars.copy_context()`，並於子執行緒以 `ctx.run(fn, *args)` 啟動，才能將 `RuntimeScope` 與 `LogExecutionScope` 傳遞至子執行緒。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Parent Thread: WarmWorker / ServiceWorker]
  with bind_runtime_context(virtual_cwd, env, host_dir, yscb_dir), bind_log_context(background_sink):
      ctx = contextvars.copy_context()
      ├── BaseServiceWorker.start_managed_thread  --> Thread(target=lambda: ctx.run(_wrapped_entry))
      ├── Watchdog _CoreSpaceWatchdogHandler      --> on_any_event wraps worker.bind_worker_context()
      └── GDrive ThreadPoolExecutor               --> pool.submit(ctx.copy().run, task_fn, *args)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/log.py` | Modify | 修復 `RollingFileLogger.write_raw` 遞迴、`_write_to_active_target` 防抖擊穿、`start_capture` 重入、`_StreamProxy.write` 背景分流、`isolated_error_scope` 全域隔離與 `_rotate_lines_file` `.split("\n")` (`FR-01`) |
| `ys_codebase/source/core/core/context.py` | Modify | `reset_all_caches()` 清空 `uri_tls.__dict__` / `uri_reentrancy.__dict__` 並清理 `loaded_modules_cache` 對應之 `sys.modules` 鍵；`bind_runtime_context` 過濾空字串 `virtual_cwd` (`FR-02`) |
| `ys_codebase/source/core/core/uri.py` | Modify | 將 `get_host_dir()` / `get_yscb_root()` / `get_module_context()` 之 `RuntimeScope` (`ContextVar`) 優先級調高於 `uri_tls` (`FR-02`) |
| `ys_codebase/source/core/core/loader.py` | Modify | 追蹤 `alias_keys`，於 `clear_loaded_modules()` 一併清除別名鍵，並於熱重載失敗時還原舊快取條目 (`FR-02`) |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | 移除 `mod_cache` 對 `load_module_from_path(..., reload_if_changed=True)` 之短路；`--json` 模式下抑制 `print_tips_if_available()`；`L218` 改用 `get_env` (`FR-01`, `FR-02`) |
| `ys_codebase/source/core/core/symbols.py` | Modify | `resolve_callable` 對檔案型符號記錄並比對 `(mtime_ns, size)` 指紋，消除 `callable_cache` 與 Track 1 短路；`L152` 改用 `get_env` (`FR-02`) |
| `ys_codebase/source/core/core/{locale,telemetry,update_checker,config,validator}.py` & `platform/{process,venv}.py` & `commands/{registry,bags}.py` & `space/{schema,scanner,watcher}.py` & `scripts/cli.py` | Modify | 將 12 處 `os.environ` 改為 `get_env`/`get_env_snapshot`；補齊 `_ConfigManagerMeta`/`_ContributesValidatorMeta` setter；補齊 `SpaceConfig` tuple 正規化與含可變欄位之凍結 dataclass `eq=False`/`compare=False`；修復 `config_list --json` 與 `is_watcher_active` (`FR-01`, `FR-02`, `P2-04`) |
| `ys_codebase/source/server/server/{worker,service,master,space_watcher}.py` | Modify | `worker_main` 常駐綁定預設上下文；`start_managed_thread` 與 Watchdog Handler 傳播 `RuntimeScope` & `LogExecutionScope`；狀態變更同步回 `MasterSupervisor._worker_services`；對齊 `space_watcher.stop()` `_thread = None` (`FR-03`) |
| `ys_codebase/source/file-space/file_space/{__init__,manager}.py` | Modify | `manager.py:L232` 改用 `dataclasses.replace(cfg, weight=float(w))`；`__init__.py` 補齊 `globals().pop` 與 `project_root` 單例檢驗 (`FR-04`) |
| `ys_codebase/source/knowledge-db/knowledge_db/{embedding,engine,pipeline,hybrid,service,config}.py` & `scripts/hook.core.py` | Modify | 修復 `hook.core.py:L58` `generation=`；`pipeline.py` 前置 `has_local_model()` 消除 3 秒阻塞並刪除 `L1148-1153` 重複區塊；`engine.py:model_status` 純本地返回、複用共享 `SpaceRegistry`/`SpaceScanner`/`ASTEngine` 並改用 `get_env`；29 處內部 `log_warn`/`log_info` 補上 `stream="stderr"` (`FR-04`) |
| `ys_codebase/source/ast/ast_engine/{engine,schema,bundler}.py` & `parsers/{registry,treesitter}.py` & `scripts/hook.core.py` | Modify | 修復 `engine.py:L577, L632` `_load_snapshot_state` 與 `get_cursor` 型別錯誤；`UnifiedSymbol.__post_init__` 雙向轉 `tuple`；16 處 `log_warn` 補上 `stream="stderr"`；`hook.core.py` 對齊 `UNIFIED_KEY` 游標 (`FR-04`) |
| `ys_codebase/source/gdrive-support/gdrive_support/{service,coordinator,transport}.py` & `scripts/cli.py` | Modify | `ThreadPoolExecutor` 透過 `contextvars.copy_context().run` 傳遞上下文；`GDriveSyncServiceWorker.start()` 狀態對齊；`GDriveConfig` 改用 `dataclasses.replace`；`transport.py` OAuth 提示改走 `stream="stderr"` (`FR-03`, `P2-03`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py` & `scripts/hook.core.py` | Modify | `session_trace.py:L38, 147` 改用 `get_env`；`hook.core.py:L35, 37` 錯誤輸出導向 `stderr` (`FR-02`, `FR-04`) |
| `ys_codebase/source/dev/dev/{checker,tester}.py` & `testing/sandbox.py` & `tests/{test_checker,test_tester}.py` | Modify | 修復 `tester.py:L735` 與 `test_tester.py:L168`；升級 `checker.py` 作用域別名堆疊、`D10` (`sys.argv`/`reload`)、`F13` (`urlopen`/`shell=True`/`timeout=None`)、`E12`、`B4`、`C8`/`C9` 與 `_check_sandbox_hooks`；升級 `sandbox.py:L75` 模板並擴充 `test_checker.py` (`FR-05`) |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `contextvars.copy_context().run` 統一跨執行緒上下文繼承模式**：
  - 在 `BaseServiceWorker.start_managed_thread` 與 `gdrive-support` 執行緒池提交處統一封裝 `ctx = contextvars.copy_context()`，確保無論是常駐受管執行緒或其內部再衍生的工作池子執行緒，皆自動繼承父執行緒之 `RuntimeScope` 與 `LogExecutionScope`。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/server/server/service.py
class BaseServiceWorker(ABC):
    def bind_worker_context(self, context: Optional[Dict[str, Any]] = None) -> ContextManager[Any]: ...
    def start_managed_thread(
        self,
        target: Callable[[], None],
        *,
        context: Optional[Dict[str, Any]] = None,
        thread_name: Optional[str] = None,
    ) -> threading.Thread: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `FileSpaceManager._adapt_matched_spaces`、`knowledge-db/scripts/hook.core.py:_resolve_consume_diff` 與 `ASTEngine._collect_space_generations_and_files_map` 不再拋出 `FrozenInstanceError` 或 `TypeError`。
  - `_SourceGuardrailVisitor` 對 `sys.argv` 改寫、`importlib.reload()`、`urlopen` 無 `timeout=`、`subprocess` 帶 `shell=True` 或 `timeout=None` 均回報 `CheckIssue(severity=CheckSeverity.FAIL, ...)`。
- **階段決策紀錄**：`[P03:DR-01]` 維持所有模組外部公開 API 簽名 100% 向下相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 完整覆蓋 `R02_post_implementation_deep_audit.md` 檢出之全部 21 項（P0-01~06、P1-01~10、P2-01~05）問題
- [x] **邊界防護**：EC-01 ~ EC-05 皆具備明確防禦與回歸測試驗證點
- [x] **依賴純淨**：100% 符合 NFR 指標約束

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/dev/architecture.md` | Modify | 補充 `D10` (`sys.argv`/`reload`)、`F13` (`urlopen`/`shell=True`) 與作用域別名堆疊說明 |
| **專題手冊** | `docs/server/architecture.md` | Modify | 補充 `BaseServiceWorker` 跨執行緒 `contextvars.copy_context()` 繼承與 `service_status` IPC 同步說明 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | N/A | 既有設計筆記無衝突 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新修改處之函式 Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 P07 結案時記錄 `sub_06` 深潛審計修補摘要 |

- **決策定稿**：**[P04:DR-01]** 規格審查通過，交由本機端依序執行 `TASK-01` ~ `TASK-05` 實作與測試驗收。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01（`module:core` 修補）**：修復 `core/log.py`（`echo_console` 遞迴、防抖擊穿、`start_capture` 重入、`_StreamProxy` 背景分流、`isolated_error_scope`、`_rotate_lines_file`）、`core/uri.py`（`RuntimeScope` 優先於 `uri_tls`）、`core/context.py`（`reset_all_caches` 清理 `uri_tls` 與 `sys.modules`）、`core/loader.py`（`alias_keys` 追蹤與回滾）、`core/commands/dispatcher.py`（移除 `mod_cache` 短路、`--json` 抑制更新提示）、`core/symbols.py`（檔案世代校驗）、12 處 `os.environ` 遷移 `get_env`/`get_env_snapshot`、`SpaceConfig` tuple 正規化、凍結 dataclass `eq=False`/`compare=False` 與 Metaclass property setter
- [x] **TASK-02（`module:server` 與 `gdrive-support` 修補）**：於 `server/worker.py:worker_main` 綁定常駐預設上下文；於 `server/service.py:start_managed_thread`、`server/space_watcher.py` Watchdog Handler 與 `gdrive-support` `ThreadPoolExecutor` 實作 `contextvars.copy_context()` 及 `bind_runtime_context` / `bind_worker_log_context` 傳播；實作 Worker 服務狀態變更同步回 `MasterSupervisor._worker_services` 並對齊五態轉換、`GDriveConfig` `dataclasses.replace` 與 `transport.py` `stderr` 提示
- [x] **TASK-03（`file-space`、`knowledge-db`、`ast`、`agents-workflow` 修補）**：修復 `file-space/file_space/manager.py:L232` `FrozenInstanceError` 與 `file_space/__init__.py` `globals().pop`；修復 `knowledge-db/scripts/hook.core.py:L58` `generation=`、`pipeline.py` 前置 `has_local_model()` 消除 3 秒阻塞並移除重複區塊、`engine.py:model_status` 純本地返回與共享 `SpaceRegistry`/`SpaceScanner`/`ASTEngine`；修復 `ast/ast_engine/engine.py:L577, L632` 與 `UnifiedSymbol.__post_init__`；將 `knowledge-db`（29 處）與 `ast`（16 處）內部 `log_warn`/`log_info` 補上 `stream="stderr"`；更新 `session_trace.py` 改用 `get_env`
- [x] **TASK-04（`module:dev` 靜態守門與測試沙盒修補）**：修復 `dev/dev/tester.py:L735` 與 `dev/tests/test_tester.py:L168` 沙盒 `adapt_build_pip_dependencies` 隔離；升級 `dev/dev/checker.py`（作用域別名堆疊、`D10` `sys.argv`/`reload`、`F13` `urlopen`/`shell=True`/`timeout=None`、`E12` 精準化、`B4` 提示修正、`C8`/`C9` 拆包與 `ClassVar` 檢查、`_check_sandbox_hooks` 移除頂層賦值無條件放行並修正 `posonlyargs`/`**kwargs`）；更新 `sandbox.py:L75` 模板並擴充 `test_checker.py`
- [x] **TASK-05（全倉靜態守門與沙盒單元測試驗收）**：實機執行 `python yscb.py dev check --all`（確認 9 大模組 0 Failed, 0 Warnings）與全倉 9 大模組沙盒測試（`core` 284/284、`dev` 109/109、`server` 64/64、`file-space` 19/19、`ast` 38/38、`knowledge-db` 113/113、`agents-workflow` 145/145、`vscode-support` 22/22、`gdrive-support` 34/34，共 828/828 100% 通過），產出 `P06_test_plan.md`
- [x] **TASK-DOC**：同步更新 `docs/dev/architecture.md`、`docs/server/hot_reload_and_services.md`、`CHANGELOG.md` 與主計畫 `umbrella_overview.md`

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 尚無偏差 | - |
