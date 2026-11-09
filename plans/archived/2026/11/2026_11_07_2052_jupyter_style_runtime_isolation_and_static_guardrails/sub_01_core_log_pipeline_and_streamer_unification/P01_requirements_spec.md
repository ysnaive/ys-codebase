# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_core_log_pipeline_and_streamer_unification  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core.log` 調用者終端串流族系 (`log*`) 與 `ContextVar` 執行平面路由 | 1. 於 `ys_codebase/source/core/core/log.py` 實作 `snake_case` 調用者終端輸出 API：`log(*objects, sep=" ", end="\n", flush=False, stream="stdout")`、`log_stream(text: str, *, stream="stdout", flush=True)`、`log_info(msg, *, stream="stdout", flush=False)`、`log_warn(msg, *, stream="stdout", flush=False)`、`log_error(msg, *, stream="stdout", flush=False, record_hint=True)`、`log_debug(msg, *, stream="stderr", flush=False)`。<br>2. 實作 `LogExecutionScope` 與 `bind_log_context(...)` 上下文管理器（基於 `contextvars.ContextVar`）：在 P2（冷派發）、P3（熱派發主執行緒）與 P5（沙盒測試）下保持呼叫端文字原樣輸出（不硬加重複 `[INFO]`/`[ERROR]` 前綴，`[P01:DR-01]`）；在 P4（`background_sink` 背景 `ServiceWorker` 執行緒）下嚴禁寫入前景終端，自動格式化為 `[{YYYY}-{MM}-{DD} {HH}:{MM}:{SS}.{fff}] [{PID}] [{LEVEL}] [{component}] {msg}` 轉寫入背景日誌檔。<br>3. `log_debug()` 僅在當前上下文或環境啟用 `debug/verbose` 時輸出，預設靜默忽略。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | `DebouncedIOStreamer` 下沉收編與 `server/streamer.py` 相容門面 | 1. 將 `DebouncedIOStreamer` 與 `_StreamProxy` 核心實作收編至 `core/core/log.py`，維持 `threading.RLock()`、500ms 預設防抖、`max_buffer_bytes`（預設 4096）累積刷新、連續同串流合併、`terminal_stream` 與 `task_finish` NDJSON 封包結構。<br>2. `DebouncedIOStreamer.start_capture()` 同時綁定 `ContextVar` 串流路由與 `sys.stdout`/`sys.stderr` 代理；當內層測試使用 `redirect_stdout` / `patch("sys.stderr")` 替換當前串流時，`log*` 自動感知並寫入被替換之內層串流，確保內外層攔截皆相容。<br>3. `ys_codebase/source/server/server/streamer.py` 轉為純相容匯出門面（`from core.log import DebouncedIOStreamer, _StreamProxy`），使 `server/streamer.py` 本身達成 0 處原生 `sys.stdout`/`sys.stderr` 操作。 | P0 | [P00:DR-01], [P00:DR-02], [P00:DR-03] |
| **FR-03** | `core.log` 增量滾動檔案紀錄族系 (`log_file*`) 與 `ServerLogger` 收編 | 1. 於 `core/core/log.py` 實作 `RollingFileLogger` 類別及高階函式 `log_file(target, line, *, max_bytes=0, keep_lines=0)`、`log_file_jsonl(target, record, *, max_bytes=0, keep_lines=0)`、`read_log_file_jsonl(target, ...)`、`read_log_file_tail(target, last_offset=0, last_inode=None)`。<br>2. `RollingFileLogger` 完整收編原 `ServerLogger` 能力：啟動前 Crash 殘留檔時間戳提取（首行 Banner 或 `mtime`）與歸檔、啟動 Banner（`server start at time "{ts}"`）、停機歸檔（`archive_and_close()`）、`max_backups=5` 歷史世代清理、`os.set_inheritable(fd, False)` 句柄非繼承保護、`echo_console` 同步呼叫 `log_stream()`，以及基於 `(last_offset, last_inode)` 之 `read_tail_chunks()`。<br>3. 將 `_safe_replace_file` 內的 `os.rename(src, dst)` 全面升級為原子性的 `os.replace(src, dst)`（失敗退回 `shutil.copy2` + `os.remove`）；`ys_codebase/source/server/server/logger.py` 之 `ServerLogger` 直接繼承 `RollingFileLogger`（100% 保留 `_file`、`log_file`、`echo_console` 等屬性），並同步對齊 `test_server_logging.py` 之 `os.replace` mock 標的（`[P01:DR-02]`）。 | P0 | [P00:DR-01], [P00:DR-03], [P00:DR-04] |
| **FR-04** | `telemetry.py` 滾動截斷收編與派發級 `error_hint` 累積萃取連動 | 1. 重構 `ys_codebase/source/core/core/telemetry.py`：將 JSONL 追加與 `_rotate_telemetry_file`（`max_bytes` + `keep_lines` 原子 `.tmp.{pid}` + `os.replace` 截斷）及 `read_telemetry_records` 底層委派至 `core.log` 之 `log_file_jsonl` / `read_log_file_jsonl`，保留 `telemetry.py` 所有公開函式簽名。<br>2. 於 `core.log` 實作請求級錯誤提示累積緩衝（`record_error_hint`、`get_last_error_hint`、`clear_error_hint`）：凡呼叫 `log_error(..., record_hint=True)` 或 `log_stream` 含錯誤標記（如熱派發 `stderr` 或含 `Error` / `[FAIL]` / `[BLOCKER]` 之 chunk），自動追加至緩衝列表，讀取時統一由 `extract_error_hint("\n".join(chunks))` 依關鍵字優先級萃取，並在 `dispatcher.py` 徹底消除 `global _LAST_DISPATCH_ERROR_HINT` 寫入。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-05** | `module:core` 內部 346 處生產輸出全量遷移與公開 API 匯出 | 1. 將 `ys_codebase/source/core/` 下所有非測試 `.py` 檔案（共 12 個含原生輸出的檔案，合計 346 處 `print` / `sys.stdout.write` / `sys.stderr.write`）全數遷移至 `core.log`（僅 `core/core/log.py` 底層實作與 `core/commands/dispatcher.py` 啟動串流 `reconfigure` 保留標準庫串流存取；頂層 `yscb.py` 40 處維持啟動器白名單豁免）。<br>2. 於 `ys_codebase/source/core/core/__init__.py` 註冊並匯出 `log` 子模組與核心公開符號。 | P0 | [P00:DR-01], [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `core.log` 與 `core.uri` 循環匯入或 `!undefined` URI 互動重入 | `core/log.py` 頂層僅匯入 Python 標準庫（0 頂層 `core.*` 匯入）；當 `log_file*` 傳入語意 URI 字串（含 `://`）時，於函式內部延遲匯入 `core.uri` 並強制呼叫 `uri.resolve(target, interactive=False)`，若解析失敗或為 `!undefined` 則安全拋出 `ValueError` 或靜默回傳 `False`，絕不觸發 `reconcile_undefined_uri` 互動輸出。 |
| **EC-02** | 單元測試使用 `contextlib.redirect_stdout` / `redirect_stderr` 或 `unittest.mock.patch("sys.stdout")` 攔截輸出 | `core.log` 嚴禁於模組 import 時快取 `sys.stdout` / `sys.stderr`；每次寫入時動態取得當下 `sys.stdout` / `sys.stderr`。若正處於 `DebouncedIOStreamer` 捕獲期間，但內層測試又以 `redirect_stdout` 將 `sys.stdout` 替換為非 `_stdout_proxy` 物件，則優先寫入內層被替換的 `sys.stdout` 以保證測試斷言命中。 |
| **EC-03** | `DebouncedIOStreamer` 在 `emit_chunk` 回呼內重入呼叫 `flush()`，或 `stop_capture()` 被多次重複呼叫 | `DebouncedIOStreamer._flush_locked()` 必須在持有 `threading.RLock()` 下先複製並清空 `self._buffer` 與 `self._buffer_bytes = 0`，隨後才呼叫 `self.emit_chunk(packet)`，確保重入 `flush()` 時緩衝已空不死鎖、不重複發包；`stop_capture()` 檢查 `_is_closed` 旗標並安全重置 `ContextVar` token，保證多次呼叫 100% 冪等。 |
| **EC-04** | 跨磁碟區或 Windows 檔案鎖定導致 `os.replace(src, dst)` 拋出 `OSError` | `_safe_replace_file(src, dst)` 先嘗試 `os.replace(src, dst)`；若拋出 `OSError`，自動退回 `shutil.copy2(src, dst)` 並嘗試 `os.remove(src)`（忽略 `os.remove` 之 `OSError`），確保跨檔案系統或句柄競爭時歸檔不崩潰。 |
| **EC-05** | 單次 CLI 派發期間多次呼叫 `log_error()`，或 `post_cli_dispatch` 輸出次要訊息 | `error_hint` 緩衝按呼叫順序保存當次派發的多筆錯誤片段（上限 16 筆），並在讀取 `get_last_error_hint()` 時交由 `extract_error_hint()` 按關鍵字優先級（`[BLOCKER]` / `[FAIL]` / `Error:` > 首行非空文字）萃取；且 `dispatcher.py` 在進入 `post_cli_dispatch` 前即鎖定主命令之 `error_hint`，防止被 post-hook 覆蓋。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴與啟動速度 | `core/core/log.py` 100% 僅使用 Python 標準庫，模組載入時間 $< 1\text{ms}$，不影響 `yscb.py` 冷派發 sub-100ms 效能基準。 |
| **NFR-02** | 靜態守門合規性 (`A1` & `E12`) | 遷移完成後，除 `core/core/log.py` 底層單點出口與 `dispatcher.py` 啟動串流編碼設定外，`ys_codebase/source/core/`（共 45 個生產 `.py` 檔）及 `server/{logger,streamer}.py` 達成 **0 處 `print()`、0 處 `sys.stdout/stderr.write()`、0 處 `os.rename()`**。 |
| **NFR-03** | 執行緒安全與檔案描述符隔離 | `RollingFileLogger`、`DebouncedIOStreamer` 與 `error_hint` 緩衝全程具備 `threading.RLock()` / `ContextVar` 隔離保護，且長持檔案描述符 100% 設定 `os.set_inheritable(fd, False)`。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 既有測試對 `stdout` vs `stderr` 的剛性斷言依賴**：
  經盲眼子代理反向查驗實證，`core` 既有測試（如 `test_core_commands.py`、`test_cli_router.py`、`test_contributes_cmd.py`、`test_installer.py`）大量使用 `redirect_stdout` 捕獲 `[yscb] Error:` 與 `[FAIL]` 輸出；僅 `events.py`、`guard.py`、`dispatcher.py:540` 等處使用 `file=sys.stderr`（由 `test_events_pipeline.py`、`test_guard.py` 以 `patch("sys.stderr")` 斷言）。因此遷移時必須嚴格維持原呼叫點的目標串流（原無 `file=sys.stderr` 者維持預設 `stream="stdout"`，原有 `file=sys.stderr` 者顯式傳入 `stream="stderr"`），切勿改變既有輸出的標準串流通道。
- **`[!NOTE]` `test_server_logging.py` 對 `ServerLogger` 內部屬性與 `os.rename` 的白箱斷言**：
  `test_server_logging.py:337-349` 直接檢查 `logger._file.fileno()`，且 `L211, L225` 使用 `patch("server.logger.os.rename", ...)` 模擬跨磁碟錯誤。因此 `ServerLogger` 必須以類別繼承 `RollingFileLogger` 保留 `_file` 屬性，並將 `test_server_logging.py` 的 mock 目標同步升級為 `os.replace`。
