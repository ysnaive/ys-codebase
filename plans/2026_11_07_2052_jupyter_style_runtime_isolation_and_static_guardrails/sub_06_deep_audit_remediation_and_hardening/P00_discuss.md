# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_06_deep_audit_remediation_and_hardening  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Confirmed  
> 模型：Gemini 3.1 Pro  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對 `sub_01` ~ `sub_05` 完成後的 GitHub 最新進度執行四軌平行深潛審計（`R02_post_implementation_deep_audit.md`），並建立 `sub_06` 修補計畫，將檢出的全部 P0 ~ P2 跨模組邊界缺陷、執行期崩潰風險、跨執行緒 `ContextVar` 斷裂与靜態規則盲區一次性收斂修復。
- **核心目標**：
  1. **根除 6 項 P0 執行期崩潰與核心隔離斷裂（`P0-01` ~ `P0-06`）**：
     - 修復 `file-space/file_space/manager.py:L232` 對已凍結 `FileSpaceConfig` 直接賦值 `cfg.weight` 引發之 `FrozenInstanceError`（`P0-01`）；
     - 修復 `knowledge-db/scripts/hook.core.py:L58` 呼叫 `scanner.ack` 傳入錯誤參數名 `to_generation=` 引發之 `TypeError`（`P0-02`）；
     - 修復 `ast/ast_engine/engine.py:L577, L632` 呼叫 `_load_snapshot_state` 傳入不存在之 `is_ephemeral=` 參數與誤將 `get_cursor()` 回傳 `dict` 轉 `int` 導致 `space_generations` 卡死在 `1` 的問題（`P0-03`）；
     - 修復 `server/service.py:start_managed_thread`、Watchdog `Observer` 與 `gdrive-support` `ThreadPoolExecutor` 未傳播 `ContextVar`（`bind_runtime_context` / `bind_log_context`），以及 `core/uri.py` 將 `uri_tls`（`threading.local`）優先級置於 `RuntimeScope`（`ContextVar`）之上導致 `WarmWorker` 屏蔽 `bind_runtime_context` 的缺陷（`P0-04`）；
     - 修復 `core/commands/dispatcher.py:L651`（`mod_cache`）與 `core/symbols.py:L114, L140`（`callable_cache` 及 Track 1 `importlib.import_module` 命中別名）外層快取無條件短路，導致 `core.loader.load_module_from_path(..., reload_if_changed=True)` 檔案世代熱重載 100% 失效的問題（`P0-05`）；
     - 修復 `knowledge-db/knowledge_db/embedding.py`（5 處 `log_info`/`log_warn`）、`engine.py:model_status()`、`core/commands/dispatcher.py`（`--json` 下觸發 `print_tips_if_available`）與 `core/scripts/cli.py:config_list` 將非 JSON 訊息寫入 `stdout` 導致 `--json` 模式 `JSONDecodeError` 崩潰的問題（`P0-06`）。
  2. **修復 10 項 P1 靜態守門盲區、前景 3 秒阻塞、測試沙盒失敗與狀態隔離缺口（`P1-01` ~ `P1-10`）**：
     - 修復 `dev/dev/tester.py:L735`（`_run_parallel_test`）漏加 `if not is_nested and get_env("YSCB_TEST_SANDBOX") != "1":` 守門導致離線沙盒 `TestDevTester.test_run_test_all_success_cleans_sandboxes` 拋出 `PipInstallError` 的問題（`P1-01`）；
     - 補齊 `dev/dev/checker.py`（`_SourceGuardrailVisitor`）對 `D10`（`sys.argv` 改寫與 `importlib.reload`）、`F13`（`urllib.request.urlopen` 缺 `timeout=`、`subprocess` 之 `shell=True` 與 `timeout=None`）之攔截，收緊 `E12` 避免誤殺自訂物件 `.rename()`，修正 `B4` 錯誤訊息為 `core.context.get_virtual_cwd()`，將別名追蹤改為作用域堆疊，補齊 `C8`/`C9` 拆包賦值與 `@dataclass(frozen=True)` 內 `ClassVar` 可變容器檢查，並修復 `_check_sandbox_hooks`（`L1604, L1617`）頂層賦值無條件放行與 `posonlyargs`/`**kwargs` 判定（`P1-02` ~ `P1-04`）；
     - 將 `knowledge-db/knowledge_db/pipeline.py:_resolve_vector_availability_with_worker_tolerance` 的 `has_local_model()` 與離線/下載中狀態檢查移至 `wait_until_worker_idle` 之前，消除離線環境下前景 `kdb search` 3000ms 阻塞（`P1-05`）；
     - 補齊 `server` 服務狀態變更時向 `MasterSupervisor._worker_services` 的同步機制、於 `worker_main` 外層常駐綁定預設 `bind_runtime_context` 與 `bind_log_context`，並對齊三個 `ServiceWorker` 的五態轉換與 `_thread = None` 清理（`P1-06`）；
     - 修復 `core/core/log.py` 中 `RollingFileLogger(echo_console=True)` 作為 `background_sink` 時的無限遞迴、`log_stream` 擊穿 `DebouncedIOStreamer` 防抖、`start_capture()` 重入、`_StreamProxy.write` 背景執行緒第三方 `stderr` 分流、`isolated_error_scope` 污染全域 `log_error_chunks` 與 `_rotate_lines_file` `splitlines()` 切碎 JSONL 問題（`P1-07`）；
     - 將全倉殘留的 16 處直讀 `os.environ`（含 `core/platform/process.py:L128` `spawn_detached` 的 `os.environ.copy()`）統一遷移至 `get_env()` / `get_env_snapshot()`（`P1-08`）；
     - 為含可變容器欄位之 `@dataclass(frozen=True)` 處理 hashability、補齊 `SpaceConfig` 與 `UnifiedSymbol` 的 `tuple` 正規化與 Metaclass property setter（`P1-09`）；
     - 為 `knowledge-db`（24 處）與 `ast`（16 處）內部診斷 `log_warn`/`log_info` 補上 `stream="stderr"`，並於 `ast_engine.get_engine()`、`knowledge_db.get_engine()` 與 `file_space` 單例檢驗 `project_root` 一致性及補齊 `globals().pop`（`P1-10`）。
  3. **完成 5 項 P2 微觀清理與測試斷言強化（`P2-01` ~ `P2-05`）**。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 直接在 `sub_01` ~ `sub_05` 已建置之 `core.log`、`core.context`、`core.loader`、`server.service` 與 `dev.checker` 架構上原位加固，不引入任何新模組或外部依賴。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更任何公開 CLI 命令樹結構或模組 `contributes` Schema 定義；不涉及 Tier 2 之 `module:ast` 圖譜引擎重寫。
- **架構影響範圍**：
  - `module:core`：`log.py`, `context.py`, `loader.py`, `uri.py`, `config.py`, `validator.py`, `symbols.py`, `locale.py`, `telemetry.py`, `update_checker.py`, `commands/{dispatcher,registry,bags}.py`, `platform/{process,venv}.py`, `space/{schema,scanner,watcher}.py`, `scripts/cli.py`
  - `module:server`：`worker.py`, `service.py`, `master.py`, `space_watcher.py`
  - `module:dev`：`checker.py`, `tester.py`, `testing/sandbox.py`, `tests/{test_checker,test_tester}.py`
  - `module:file-space`：`file_space/{__init__,manager}.py`
  - `module:ast`：`ast_engine/{engine,schema,bundler}.py`, `ast_engine/parsers/{registry,treesitter}.py`, `scripts/hook.core.py`
  - `module:knowledge-db`：`knowledge_db/{embedding,engine,pipeline,hybrid,service,config}.py`, `scripts/hook.core.py`
  - `module:gdrive-support`：`gdrive_support/{service,coordinator,transport}.py`, `scripts/cli.py`
  - `module:agents-workflow`：`agents_workflow/plans/session_trace.py`, `scripts/hook.core.py`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 跨執行緒 `ContextVar` 顯式傳播與 `RuntimeScope` 最內層優先原則**：
  - `BaseServiceWorker.start_managed_thread`、Watchdog `_CoreSpaceWatchdogHandler` 與 `gdrive-support` `ThreadPoolExecutor` 統一透過 `contextvars.copy_context().run` 與顯式 `bind_runtime_context` / `bind_worker_log_context` 傳遞執行期上下文；`core/uri.py` 將 `RuntimeScope`（`ContextVar`）優先級置於 `uri_tls`（`threading.local`）之上，確保熱派發與巢狀 `bind_runtime_context` 不被啟動期 `set_host_dir` 屏蔽。
- **[P00:DR-02] 消除外層無世代快取短路，統一由 `core.loader` 執行 `(mtime_ns, size)` 熱刷新**：
  - `dispatcher.py` 與 `symbols.py` 不再以無世代指紋的外層字典短路跳過 `load_module_from_path(..., reload_if_changed=True)`，同時保留對單元測試 `patch.dict` 白箱注入物件之識別相容。
- **[P00:DR-03] 內部診斷與警告預設導向 `stderr`，確保 `--json` 標準輸出 100% 純淨**：
  - 所有非 CLI 主結果之內部降級警告、模型載入提示、OAuth 互動提示與更新橫幅在 `--json` 或底層引擎中一律導向 `stream="stderr"`（或於 `--json` 下靜默跳過更新提示），並使 `kdb model status` 在未下載模型時採純本地非阻塞返回。
- **[P00:DR-04] 補齊 `_SourceGuardrailVisitor` 作用域別名堆疊與 `D10`/`F13`/`_check_sandbox_hooks` 完整契約**：
  - 將別名追蹤升級為隨函式/類別作用域推入彈出之堆疊，補齊 `sys.argv`、`importlib.reload`、`urlopen(timeout=...)`、`shell=True`、`timeout=None` 攔截，收緊 `E12` 僅針對 `os`/`Path` 之 `rename`，並移除 `_check_sandbox_hooks` 頂層賦值無條件放行漏洞。

---

## 3. 開放議題與確認紀錄

- 開發者已審閱四軌深潛審計報告（`R02_post_implementation_deep_audit.md`）並指示建立 `sub_06_deep_audit_remediation_and_hardening` 修補計畫，直接產出 `P01-05_auto.md` 供本地端接手實作與驗收。
