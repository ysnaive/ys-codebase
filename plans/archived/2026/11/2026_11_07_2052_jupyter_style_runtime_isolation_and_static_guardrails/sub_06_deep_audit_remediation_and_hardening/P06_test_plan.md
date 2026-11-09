# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_06_deep_audit_remediation_and_hardening  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `core.log` 防抖緩衝不因 `log_stream` 預設 `flush=True` 提前擊穿、`RollingFileLogger(echo_console=True)` 作為 `background_sink` 不發生遞迴、`_StreamProxy.write` 背景第三方串流分流、`isolated_error_scope` 全域隔離與 `_rotate_lines_file` `.split("\n")` 保留 `\u2028`/`\u2029` | FR-01, EC-01, NFR-02 | `python yscb.py dev test --target=core:TestCoreLogPipeline` |
| **FT-02** | 單元測試 | 驗證 `core.uri` 將 `RuntimeScope` (`ContextVar`) 優先級置於 `uri_tls` 之上、`dispatcher` 與 `symbols` 穿透檔案 `(mtime_ns, size)` 熱重載、`core.loader` 別名追蹤回滾、`spawn_detached` 與 14 處 `get_env`/`get_env_snapshot`、以及凍結 `@dataclass` hashability 與 `SpaceConfig` tuple 正規化 | FR-02, EC-04, NFR-02 | `python yscb.py dev test --target=core:TestRuntimeContextAndLoader` |
| **FT-03** | 單元測試 | 驗證 `server` 之 `worker_main` 常駐預設上下文、`BaseServiceWorker.start_managed_thread` 與 Watchdog/`gdrive-support` `ThreadPoolExecutor` 跨執行緒 `contextvars.copy_context()` 傳播、以及 `service_status` 即時更新 `MasterSupervisor._worker_services` | FR-03, EC-03, NFR-02 | `python yscb.py dev test --target=server:TestServerModule` & `python yscb.py dev test gdrive-support -q` |
| **FT-04** | 單元測試 | 驗證 `file-space` `FileSpaceConfig` 權重 `dataclasses.replace` 無 `FrozenInstanceError`、`knowledge-db` Hook `scanner.ack(generation=...)`、離線環境 `kdb search`/`model status` 零 3 秒阻塞且 `--json` 標準輸出 100% 純淨、以及 `ast` `_load_snapshot_state`/`get_cursor` 與 `UnifiedSymbol` tuple 正規化 | FR-04, EC-01, NFR-01, NFR-02 | `python yscb.py dev test file-space -q` & `python yscb.py dev test ast -q` & `python yscb.py dev test knowledge-db -q` |
| **FT-05** | 單元測試 | 驗證 `dev` `Tester._run_parallel_test` 離線沙盒守門（`109/109` 全過）、`Checker` 作用域別名堆疊、`D10` (`sys.argv`/`importlib.reload`)、`F13` (`urlopen`/`shell=True`/`timeout=None`)、`E12` 不誤殺自訂 `.rename()`、`C8`/`C9` 拆包與 `ClassVar`、以及 `_check_sandbox_hooks` 頂層賦值與參數檢核 | FR-05, EC-02, EC-05, NFR-02 | `python yscb.py dev test dev -q` |
| **RT-01** | 整合與回歸測試 | 驗證全倉 9 大模組靜態合規檢核（`dev check --all` `9 Passed, 0 Failed, 0 Warnings`）與全倉 9 大模組沙盒回歸測試 100% 通過 | FR-01 ~ FR-05, EC-01 ~ EC-05, NFR-01, NFR-02 | `python yscb.py dev check --all` & `python yscb.py dev test --all -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `python yscb.py dev test core -q` 通過（284/284, 100.0%）；驗證 `core.log` 防抖緩衝、`RollingFileLogger(echo_console=True)` 零遞迴、`_StreamProxy.write` 背景分流、`isolated_error_scope` 全域隔離與 `_rotate_lines_file` `.split("\n")` | 2026-11-08 |
| **FT-02** | `Passed` | `python yscb.py dev test core -q` 通過（284/284, 100.0%）；驗證 `core.uri` `RuntimeScope` 優先於 `uri_tls`、`dispatcher` 與 `symbols` 檔案 `(mtime_ns, size)` 熱重載穿透、`core.loader` 別名回滾、14 處 `get_env`/`get_env_snapshot` 與凍結 dataclass hashability | 2026-11-08 |
| **FT-03** | `Passed` | `python yscb.py dev test server -q`（64/64, 100.0%）與 `python yscb.py dev test gdrive-support -q`（34/34, 100.0%）全數通過；驗證 `worker_main` 預設上下文、`start_managed_thread` 與 Watchdog/`ThreadPoolExecutor` 跨執行緒 `contextvars.copy_context()` 傳播、以及 `service_status` IPC 同步與 `ServiceManager` `RLock` 無死鎖 | 2026-11-08 |
| **FT-04** | `Passed` | `file-space`（19/19）、`ast`（38/38）、`knowledge-db`（113/113）與 `agents-workflow`（145/145）全數 100% 通過；驗證 `FileSpaceConfig` `dataclasses.replace`、`knowledge-db` 離線零阻塞返回、`stderr` 診斷分流與 `ast` 游標/世代解析 | 2026-11-08 |
| **FT-05** | `Passed` | `python yscb.py dev test dev -q`（109/109, 100.0%）通過；驗證離線沙盒守門、作用域別名堆疊、`D10` (`sys.argv`/`reload`)、`F13` (`urlopen`/`shell=True`/`timeout=None`)、`E12` 精準化、`C8`/`C9` 與 `_check_sandbox_hooks` | 2026-11-08 |
| **RT-01** | `Passed` | `python yscb.py dev check --all`（`9 Total, 9 Passed, 0 Warnings, 0 Failed`）與全倉 9 大模組沙盒測試（共 828 項測試，100.0% Passed, 0 Failed）全數通過 | 2026-11-08 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py dev check --all` 與 `python yscb.py kdb model status --json`，確認全倉 9 大模組 13 項 AST 靜態守門 0 違規，且離線/未載入向量模型時 `--json` 輸出 100% 純淨可解析 | `[跳過/免測]` | 開發者於 2026-11-08 指示免測（已由自動化測試與實機檢核 100% 覆蓋） |
