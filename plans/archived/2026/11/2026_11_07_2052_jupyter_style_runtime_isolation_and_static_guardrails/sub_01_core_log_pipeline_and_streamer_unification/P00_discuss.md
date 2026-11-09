# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_core_log_pipeline_and_streamer_unification  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：準備啟用 `2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails` 主計畫，依序推進第一個子計畫 `sub_01_core_log_pipeline_and_streamer_unification`。
- **核心目標**：
  1. 於 `ys_codebase/source/core/core/log.py` 建立統一 `core.log` 雙族系管線：
     - **`log*` 族系（Caller Stream 調用者終端輸出）**：提供 `log()`（標準結果輸出）與分級診斷輸出 `log_info()`、`log_warn()`、`log_error()`、`log_debug()`，以及顯式原始串流寫入輔助（供熱派發回傳與進度刷新使用）；依當前 `contextvars.ContextVar` 綁定之執行期串流上下文自動投遞至實體終端、請求專屬 IPC 回傳通道或背景日誌檔，並在呼叫 `log_error()` 時自動將結構化錯誤摘要登記至當次請求之 `error_hint`。
     - **`logFile*` 族系（Incremental Rolling File Sink 增量滾動檔案紀錄）**：提供 `RollingFileLogger` 與高階便捷函式 `log_file()`、`log_file_jsonl()`、`read_log_file_tail()`，支援語意 URI 或 `Path`、三大滾動視窗策略（`keep_lines + max_bytes` 按筆數與大小截斷、`max_backups` 歷史世代輪替與啟動時 Crash 遺留檔自動歸檔、`os.set_inheritable(fd, False)` 句柄保護與即時 Flush）及基於 `(byte_offset, inode)` 之增量尾端讀取。
  2. 統一收編既有日誌、防抖串流與輪替組件：
     - 收編 `ys_codebase/source/server/server/logger.py` (`ServerLogger`) 與 `ys_codebase/source/server/server/streamer.py` (`DebouncedIOStreamer`) 底層實作至 `core.log`，一併將 `_safe_replace_file` 中的 `os.rename(src, dst)` 升級為原子性的 `os.replace(src, dst)`（根除全倉唯一 1 處 `E12` 違規），並於 `server/logger.py` 與 `server/streamer.py` 保留薄相容委派門面，確保 `server` 模組既有呼叫端與測試 100% 無縫相容且避免 `sub_03` 重複修改。
     - 收編 `ys_codebase/source/core/core/telemetry.py` 之檔案追加與 `_rotate_telemetry_file` (`keep_lines + max_bytes`) 滾動截斷邏輯至 `core.log` 之 `log_file*` 族系，並讓 `dispatcher.py` 之 `_LAST_DISPATCH_ERROR_HINT` 優先由 `core.log` 請求級錯誤提示上下文供給。
  3. 完成 `module:core` 內部生產代碼（扣除頂層單檔啟動器 `yscb.py` 豁免之 40 處 Bootstrap 原生輸出後，共計 346 處 `print` / `sys.stdout` / `sys.stderr`）100% 遷移至 `core.log`，並匯出 `core.log` 公開 API。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 經 `knowledge-db search` 與 `ast outline` 查證，現有日誌與串流邏輯分散於 `server/server/logger.py` (`ServerLogger`)、`core/core/telemetry.py` (`record_cli_event` / `_rotate_telemetry_file`) 與 `server/server/streamer.py` (`DebouncedIOStreamer`)。本子計畫直接抽提並統合 `ServerLogger`、`DebouncedIOStreamer` 與 `telemetry.py` 之核心機制至 `core/core/log.py`，不平行重造輪子，並保留 `ServerLogger`、`DebouncedIOStreamer` 與 `telemetry.py` 公開介面委派向後相容。
- **邊界排除 (Explicitly Excluded)**：
  - 頂層單檔啟動器 `yscb.py`（40 處原生 `print`）因在 `core` 物化前須維持零外部依賴，明文列入啟動器白名單豁免，不在本子計畫改寫。
  - `core` 內部 29 個頂層可變快取收斂、`@dataclass(frozen=True)` 凍結與受保護命名空間載入器屬 `sub_02` 範疇。
  - `server` 常駐 `WarmWorker` 控制/執行通道分離与 `BaseServiceWorker` 受管獨立執行緒屬 `sub_03` 範疇（本子計畫於 `core.log` 一併收編 `DebouncedIOStreamer` 並讓 `with streamer:` 同時綁定 `ContextVar` 串流路由與相容代理，使 `sub_01` ~ `sub_03` 零重複修改）。
  - 上層 7 大業務模組之 `core.log` 遷移屬 `sub_04` 範疇；`dev/checker.py` 13 項靜態守門啟用屬 `sub_05` 範疇。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/log.py`（新建核心模組）
  - `ys_codebase/source/core/core/__init__.py`、`ys_codebase/source/core/core/telemetry.py`、`ys_codebase/source/core/core/commands/dispatcher.py` 及 `core` 內其餘含原生輸出之生產檔案（共計遷移 346 處輸出點）
  - `ys_codebase/source/server/server/logger.py` 與 `ys_codebase/source/server/server/streamer.py`（重構為委派至 `core.log` 之相容門面，消除 `server/logger.py` 之 `os.rename` 與 `sys.stdout` 並消除 `server/streamer.py` 之原生串流操作）
  - `ys_codebase/source/core/tests/`（新增 `test_log.py` 完整覆蓋 `log*`、`log_file*` 與 `DebouncedIOStreamer`，並確保既有 `core` 與 `server` 測試 100% 通過）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `core.log` 雙族系 `snake_case` API 契約與既有三組件（`ServerLogger`、`DebouncedIOStreamer`、`telemetry.py`）收編策略（軸一：既有組件復用）**：
  - **全面採用 `snake_case` 命名**：
    1. **`log*` 調用者終端輸出族系**：提供 `log(*objects, sep=" ", end="\n", flush=False, stream="stdout")`、`log_stream(text, *, stream="stdout", flush=True)`、以及分級診斷函式 `log_info(msg, *, flush=False)`、`log_warn(msg, *, flush=False)`、`log_error(msg, *, flush=False, record_hint=True)`、`log_debug(msg, *, flush=False)`，並收編 `DebouncedIOStreamer`（含 `_StreamProxy`）作為熱派發防抖封包緩衝器。
    2. **`log_file*` 增量滾動檔案紀錄族系**：提供 `RollingFileLogger`（吸收 `ServerLogger` 完整能力）以及通用函式 `log_file(target, line, *, max_bytes=0, keep_lines=0, ...)`、`log_file_jsonl(target, record, *, max_bytes=0, keep_lines=0)`、`read_log_file_jsonl(target, ...)`、`read_log_file_tail(target, last_offset=0, last_inode=None)`。
- **[P00:DR-02] 5 大執行平面 `ContextVar` 路由、前景原樣輸出與背景結構化前綴、及 `error_hint` 自動連動（軸二：預設值與隱性副作用）**：
  - 於 `core.log` 內建基於 `contextvars.ContextVar` 之 `LogExecutionScope`（支援 `bind_log_context(...)` 上下文管理器，且 `DebouncedIOStreamer.start_capture()` / `stop_capture()` 自動掛載與卸載 `ContextVar`）：
    1. **前景原樣輸出與 1:1 串流對齊（方案 3A）**：在本地冷派發（P2）、常駐熱派發主執行緒（P3）與沙盒測試（P5）下，`log`、`log_info`、`log_warn`、`log_error` 預設 `stream="stdout"`（與既有 `print(...)` 1:1 對齊，原顯式 `file=sys.stderr` 處則傳入 `stream="stderr"`），`log_debug` 預設僅於 `debug/verbose=True` 時輸出；全數**保持呼叫端文字原樣輸出**，不硬加重複 `[ERROR]`/`[INFO]` 前綴，且每次呼叫時動態讀取當下 `sys.stdout` / `sys.stderr`（若內層套用 `redirect_stdout` / `patch("sys.stderr")` 則自動尊重內層攔截），確保既有單元測試斷言 100% 零破壞。
    2. **背景無終端自動轉發與結構化欄位**：當處於 `bind_log_context(background_sink=..., component=...)`（P4 常駐背景 `ServiceWorker` 執行緒）時，`log*` 嚴禁流向前景終端，自動格式化為 `[{YYYY}-{MM}-{DD} {HH}:{MM}:{SS}.{fff}] [{PID}] [{LEVEL}] [{component}] {msg}` 轉寫入背景日誌檔。
    3. **`error_hint` 累積緩衝與優先級萃取**：當次派發期間呼叫 `log_error()` 或向 `log_stream()` 寫入含錯誤標記之訊息（含熱派發 Client 端接收之 `terminal_stream` 錯誤塊）時，自動追加至當前請求之錯誤緩衝列表，並由 `get_last_error_hint()` 交由 `extract_error_hint("\n".join(chunks))` 依關鍵字優先級萃取，防止尾行一般輸出或 `post_cli_dispatch` 覆蓋主因。
- **[P00:DR-03] 檔案句柄生命週期、跨平台原子替換、零循環匯入與拆卸冪等性（軸三：生命週期與逆向拆卸）**：
  - `core/log.py` 頂層僅匯入 Python 標準庫（零頂層 `core.uri` 匯入）；解析語意 URI 時於函式內延遲匯入 `core.uri` 並強制傳入 `resolve(target, interactive=False)`，徹底杜絕 `uri.py` 互動式輸出引發之循環匯入或無限重入。
  - `RollingFileLogger` 與 `server/logger.py:_safe_replace_file` 全面以 `os.replace(src, dst)` 取代 `os.rename(src, dst)`（若遇跨磁碟區或極端權限鎖定則退回 `shutil.copy2` + `os.remove`），並同步更新 `test_server_logging.py` 對應 mock 標的。
  - `ServerLogger` 直接繼承 `RollingFileLogger`（100% 保留 `_file`、`log_file`、`echo_console` 等屬性），所有長持檔案句柄強制設定 `os.set_inheritable(fd, False)`，且 `archive_and_close()` 與 `DebouncedIOStreamer.stop_capture()` 保證可重複呼叫之冪等性（Idempotent Teardown）。
- **[P00:DR-04] 日誌時間戳、NDJSON 封包與增量游標跨切面不變量（軸四：全局座標與時鐘不變量）**：
  - `ServerLogger` 委派至 `core.log` 後，100% 維持既有啟動 Banner（`server start at time "{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}"`）、歷史檔名格式（`{YYYY}_{MM}_{DD}_{HH}.{MM}.{SS}_log`）、日誌行格式（`[{YYYY}-{MM}-{DD} {HH}:{MM}:{SS}.{fff}] [{PID}] [{LEVEL}] [{COMPONENT}] {MESSAGE}`）與 `read_tail_chunks` 回傳之 `(chunk, new_offset, current_inode)` 三元組契約不變。

---

## 3. 開放議題與確認紀錄

- 全數架構邊界、五維度防放水反詰探針與 `R01` 量化影響半徑已 100% 對齊確認，無未決開放議題。
