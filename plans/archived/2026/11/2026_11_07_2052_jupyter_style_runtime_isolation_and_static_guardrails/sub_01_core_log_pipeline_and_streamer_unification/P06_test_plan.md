# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_core_log_pipeline_and_streamer_unification  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `core.log` 調用者終端串流族系 (`log`, `log_stream`, `log_info`, `log_warn`, `log_error`, `log_debug`) 於前景保持原樣輸出，於 `bind_log_context(background_sink=...)` (P4 ServiceWorker) 自動格式化轉寫至背景日誌且不污染前景，且 `log_debug` 依 `debug_enabled` 門控。 | FR-01 | `python yscb.py dev test --target=core:TestCoreLogPipeline -q` (`test_ft01_terminal_stream_family_and_contextvar_routing`) |
| **FT-02** | 單元測試 | 驗證 `DebouncedIOStreamer` 下沉至 `core.log` 後之 500ms 防抖、累積刷新、同串流合併、`task_finish` 封包發送，以及 `server.streamer` 相容匯出門面無損運作。 | FR-02 | `python yscb.py dev test --target=core:TestCoreLogPipeline -q` (`test_ft02_debounced_io_streamer_and_server_facade`) & `python yscb.py dev test server -q` |
| **FT-03** | 單元測試 | 驗證 `RollingFileLogger`（Crash 殘留恢復、啟動 Banner、停機歸檔、`MAX_HIST_FILES=5` 清理、`os.set_inheritable(fd, False)`、`read_tail_chunks`）、`_safe_replace_file` (`os.replace`) 與 `log_file*` 增量滾動檔案紀錄族系，以及 `ServerLogger(RollingFileLogger)` 繼承相容性。 | FR-03 | `python yscb.py dev test --target=core:TestCoreLogPipeline -q` (`test_ft03_rolling_file_logger_and_log_file_family`) & `python yscb.py dev test server -q` (`TestServerLogging`) |
| **FT-04** | 單元測試 | 驗證 `telemetry.py` 滾動截斷與讀取委派至 `core.log` (`log_file_jsonl` / `read_log_file_jsonl`)，以及派發級 `error_hint` 累積緩衝 (`record_error_hint`, `get_last_error_hint`, `clear_error_hint`) 與 `dispatcher.py` 連動。 | FR-04 | `python yscb.py dev test --target=core:TestCoreLogPipeline -q` (`test_ft04_telemetry_delegation_and_error_hint_accumulation`) & `python yscb.py dev test --target=core:TestCoreCommandsSubsystem -q` |
| **FT-05** | 靜態與結構測試 | 以 AST 掃描 `ys_codebase/source/core/` 下全部非測試 `.py` 生產檔案，斷言除 `core/core/log.py` 底層單點出口與 `dispatcher.py` 串流編碼設定外，達成 0 `print()`、0 `sys.stdout/stderr` 寫入、0 `import logging`、0 `os.rename()`，且 `core.log` 已於 `core/__init__.py` 公開匯出。 | FR-05, NFR-01, NFR-02 | `python yscb.py dev test --target=core:TestCoreLogPipeline -q` (`test_ft05_core_module_zero_a1_violations_and_public_export`) |
| **ET-01** | 邊界測試 | 驗證 `core/log.py` 頂層 0 `core.*` 匯入，且當 `log_file*` 傳入 `!undefined` 或非法語意 URI 時，延遲呼叫 `uri.resolve(..., interactive=False)` 安全回傳 `False` / `[]` / `("", 0, None)` 而不觸發互動重入。 | EC-01 | `python yscb.py dev test --target=core:TestCoreLogPipeline -q` (`test_et01_no_circular_import_or_undefined_uri_reentry`) |
| **ET-02** | 邊界測試 | 驗證在 `DebouncedIOStreamer` 捕獲期間，內層測試使用 `redirect_stdout` / `redirect_stderr` 替換串流時，`core.log` 優先寫入內層替換串流，解除後恢復寫入 `DebouncedIOStreamer`。 | EC-02 | `python yscb.py dev test --target=core:TestCoreLogPipeline -q` (`test_et02_inner_redirect_stdout_precedence_inside_streamer`) |
| **ET-03** | 邊界測試 | 驗證 `DebouncedIOStreamer` 於 `emit_chunk` 回呼內重入呼叫 `flush()` 不死鎖、不重複發包，且 `stop_capture()` 多次呼叫具備冪等保護。 | EC-03, NFR-03 | `python yscb.py dev test --target=core:TestCoreLogPipeline -q` (`test_et03_streamer_reentrant_flush_and_idempotent_stop`) |
| **ET-04** | 邊界測試 | 驗證 `_safe_replace_file(src, dst)` 當 `os.replace` 拋出 `OSError` 時，自動退回 `shutil.copy2` + `os.remove` 且忽略 `os.remove` 之 `OSError`。 | EC-04 | `python yscb.py dev test --target=core:TestCoreLogPipeline -q` (`test_et04_safe_replace_file_os_replace_and_fallback`) |
| **ET-05** | 邊界測試 | 驗證單次派發期間多次呼叫 `log_error()` 時保留前 16 筆並按關鍵字優先序 (`[BLOCKER]` > `[FAIL]` > `Error:`) 萃取，且 `dispatcher.py` 於 `post_cli_dispatch` 前鎖定主命令錯誤摘要不被覆蓋。 | EC-05 | `python yscb.py dev test --target=core:TestCoreLogPipeline -q` (`test_ft04_telemetry_delegation_and_error_hint_accumulation` & `test_et05_dispatcher_locks_error_hint_before_post_cli_dispatch`) |
| **RT-01** | 回歸測試 | 執行 `module:core` 與 `module:server` 完整模組規範檢查與全量單元/整合回歸測試套件，驗證所有既有功能與 CLI 串流斷言 100% 相容無退化。 | FR-01 ~ FR-05, NFR-01 ~ NFR-03 | `python yscb.py dev check core`、`python yscb.py dev check server`、`python yscb.py dev test core -q --sync`、`python yscb.py dev test server -q --sync` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestCoreLogPipeline.test_ft01_terminal_stream_family_and_contextvar_routing` 通過，前景原樣輸出與 P4 `background_sink` 結構化日誌路由正常。 | 2026-11-08 |
| **FT-02** | `Passed` | `TestCoreLogPipeline.test_ft02_debounced_io_streamer_and_server_facade` 與 `server:TestServerLogging` 通過，防抖緩衝與門面相容 100% 正常。 | 2026-11-08 |
| **FT-03** | `Passed` | `TestCoreLogPipeline.test_ft03_rolling_file_logger_and_log_file_family` 通過。 | 2026-11-08 |
| **FT-04** | `Passed` | `TestCoreLogPipeline.test_ft04_telemetry_delegation_and_error_hint_accumulation` 與 `TestCoreCommandsSubsystem` (39/39) 通過。 | 2026-11-08 |
| **FT-05** | `Passed` | `TestCoreLogPipeline.test_ft05_core_module_zero_a1_violations_and_public_export` 通過，`core` 全模組非測試 `.py` 檔 0 A1/E12 違規。 | 2026-11-08 |
| **ET-01** | `Passed` | `TestCoreLogPipeline.test_et01_no_circular_import_or_undefined_uri_reentry` 通過，`log_file*` 強制 `interactive=False` 不觸發互動重入。 | 2026-11-08 |
| **ET-02** | `Passed` | `TestCoreLogPipeline.test_et02_inner_redirect_stdout_precedence_inside_streamer` 內層 `redirect_stdout` / `redirect_stderr` 優先序斷言通過。 | 2026-11-08 |
| **ET-03** | `Passed` | `TestCoreLogPipeline.test_et03_streamer_reentrant_flush_and_idempotent_stop` 重入 `flush()` 與重複 `stop_capture()` 冪等斷言通過。 | 2026-11-08 |
| **ET-04** | `Passed` | `TestCoreLogPipeline.test_et04_safe_replace_file_os_replace_and_fallback` 模擬 `os.replace` 拋出 `OSError` 之降級複製通過。 | 2026-11-08 |
| **ET-05** | `Passed` | `TestCoreLogPipeline.test_et05_dispatcher_locks_error_hint_before_post_cli_dispatch` 驗證 `post_cli_dispatch` 錯誤不覆蓋主命令 `error_hint` 通過。 | 2026-11-08 |
| **RT-01** | `Passed` | `dev check core` (PASSED)、`dev check server` (PASSED)、`dev test core -q --sync` (Pass: 277, Fail: 0, Skip: 1)、`dev test server -q --sync` (Pass: 62, Fail: 0, Skip: 0) 全數通過並同步 `@build`。 | 2026-11-08 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於終端機實機執行 `python yscb.py list` 與 `python yscb.py server status`，確認 CLI 前景終端輸出格式與遷移前完全一致（無多餘 `[INFO]` 前綴或破版）。 | `[測試通過]` | 2026-11-08 本機 `@build` 自部署與實機調用驗收通過 |
