# 當前進度與暫停交接現場 (Handoff Context)

> 暫停時間：2026-11-07 16:52  
> 所屬計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails/sub_01_core_log_pipeline_and_streamer_unification  
> 當前所在階段：Phase 1 (P01_requirements_spec.md 狀態: Confirmed，待進入 Phase 2)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 現場已完成事項
- [x] 啟用主計畫 `2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails`（`umbrella_overview.md` 標頭轉為 `In Progress`，`sub_01` 狀態標記為 `In Progress`）。
- [x] 完成 `sub_01` 7 大正交維度與 6 個核心因素對齊討論，並派發盲眼子代理（原型 ③ Devil's Advocate）對 `core` 與 `server` 第一手源碼及測試執行反向證偽查驗。
- [x] 完成 `P00_discuss.md` (`Confirmed`) 與 `P01_requirements_spec.md` (`Confirmed`，涵蓋 `FR-01` ~ `FR-05`、`EC-01` ~ `EC-05`、`NFR-01` ~ `NFR-03`)，並通過 `plan verify --phase P01`。

---

## 2. 現場未完成 / 進行中待辦
- [ ] **Phase 2 (`P02_architecture_plan.md` `Confirmed` + `P06_test_plan.md` `Draft`)**：設計 `core/core/log.py` 分層架構、5 大執行平面 `ContextVar` 路由循序圖、受影響檔案清單與測試計畫草案。
- [ ] **Phase 3 (`P03_api_spec.md`)** 與 **Phase 4 (`P04_implementation_plan.md` + `P06_test_plan.md` `Confirmed`)**：定案 `core.log` 雙族系公開簽名與任務拆解（或由開發者指示以 `/auto` 一次推進 Phase 02~05）。
- [ ] **Phase 5 (`P05_task.md`)**：實作 `ys_codebase/source/core/core/log.py`、重構 `server/logger.py`、`server/streamer.py`、`core/telemetry.py`、`core/commands/dispatcher.py`，並完成 `core` 12 個檔案共 346 處輸出點遷移與 `core/tests/test_log.py` 測試。

---

## 3. 踩坑與注意事項 (Gotchas & Blockers)
- [WARN] **Stdout vs Stderr 既有測試斷言陷阱**：`core` 既有單元測試（`test_core_commands.py:281,314,669`、`test_cli_router.py:68,237`、`test_contributes_cmd.py:101,168`、`test_installer.py:438,491`）大量使用 `contextlib.redirect_stdout` 捕獲 `[yscb] Error:` 與 `[FAIL]`；僅 `events.py:133-139`、`guard.py:39-44`、`dispatcher.py:242,256,540` 顯式寫入 `sys.stderr`（由 `test_events_pipeline.py:289-319`、`test_guard.py:49` 以 `patch("sys.stderr")` 斷言）。因此 `log`、`log_info`、`log_warn`、`log_error` 預設必須維持 `stream="stdout"`（原樣輸出文字、不加重複 `[ERROR]` 前綴），唯有原顯式傳入 `file=sys.stderr` 處才傳入 `stream="stderr"`。
- [WARN] **`core.log` 與 `core.uri` 循環匯入及 `!undefined` URI 遞迴重入陷阱**：`core/log.py` 頂層嚴禁匯入 `core.uri`；`log_file*` 解析含 `://` 之語意 URI 時，必須於函式內延遲匯入 `core.uri` 並強制呼叫 `uri.resolve(target, interactive=False)`（見 `telemetry.py:55-57`），防止觸發 `uri.py:408-531` (`reconcile_undefined_uri`) 的 21 處互動式輸出導致無限遞迴。
- [WARN] **`ServerLogger` 屬性白箱相容與 `test_server_logging.py` Mock 標的**：`test_server_logging.py:82,337-349` 與 `master.py:335,389` 直接存取 `logger._file.fileno()`、`logger.log_file` 與 `logger.echo_console`，因此 `server/logger.py` 的 `ServerLogger` 必須直接繼承 `RollingFileLogger`（`class ServerLogger(RollingFileLogger)`）；同時將 `_safe_replace_file` 的 `os.rename` 升級為 `os.replace` 後，必須同步將 `test_server_logging.py:211,225` 的 `patch("server.logger.os.rename", ...)` 對齊更新為 `os.replace`。
- [WARN] **`error_hint` 關鍵字優先級與熱派發累積**：`telemetry.py:92-104` (`extract_error_hint`) 具關鍵字優先序（`[FAIL]` 優先於尾行一般訊息，見 `test_cli_router.py:130-141`）；`core.log` 必須將單次派發期間所有 `log_error` 與含錯誤標記之 `log_stream` 累積為 `List[str]`，於讀取 `get_last_error_hint()` 時交由 `extract_error_hint("\n".join(chunks))` 萃取，並在 `dispatcher.py:690` 進入 `post_cli_dispatch` 前鎖定主命令錯誤摘要。

---

## 4. 上下文交接 (Compressed Task Context)
- **任務核心脈絡與定案清單**：
  1. **API 命名契約 (`[P00:DR-01]`)**：全面採用 `snake_case`。
     - `log*` 族系：`log(*objects, sep=" ", end="\n", flush=False, stream="stdout")`、`log_stream(text: str, *, stream="stdout", flush=True)`、`log_info(msg, *, stream="stdout", flush=False)`、`log_warn(msg, *, stream="stdout", flush=False)`、`log_error(msg, *, stream="stdout", flush=False, record_hint=True)`、`log_debug(msg, *, stream="stderr", flush=False)`。
     - `log_file*` 族系：`RollingFileLogger`、`log_file(target, line, *, max_bytes=0, keep_lines=0)`、`log_file_jsonl(target, record, *, max_bytes=0, keep_lines=0)`、`read_log_file_jsonl(target, ...)`、`read_log_file_tail(target, last_offset=0, last_inode=None)`。
     - 串流防抖與上下文：`DebouncedIOStreamer`、`_StreamProxy`、`LogExecutionScope`、`bind_log_context(...)`、`record_error_hint(text)`、`get_last_error_hint()`、`clear_error_hint()`。
  2. **`core` 內部 12 個待遷移生產檔案與輸出點座標（共 346 處，豁免 `yscb.py` 40 處）**：
     - `ys_codebase/source/core/scripts/cli.py`：244 處 `print(...)`
     - `ys_codebase/source/core/core/commands/dispatcher.py`：49 處（含 `L242-257` `out.write`/`sys.stderr.write`、`L540` `file=sys.stderr`、及消除 5 處 `global _LAST_DISPATCH_ERROR_HINT`）
     - `ys_codebase/source/core/core/engine.py`：24 處 `print(...)`
     - `ys_codebase/source/core/core/uri.py`：14 處（實際含 `reconcile_undefined_uri` 與 `check` 等 `print(...)`）
     - `ys_codebase/source/core/core/update_checker.py`：8 處 `print(...)`
     - `ys_codebase/source/core/core/commands/contributes_cmd.py`、`ys_codebase/source/core/core/guard.py`（`L39-44` `file=sys.stderr`）、`ys_codebase/source/core/core/pip_manager.py`（3 處）、`ys_codebase/source/core/core/installer.py`（2 處）、`ys_codebase/source/core/core/commands/help_renderer.py`（1 處）、`ys_codebase/source/core/core/events.py`（`L133-139` `file=sys.stderr`）。
- **關鍵檔案與行號座標**：
  - `ys_codebase/source/server/server/logger.py:L21-L336`（`_extract_log_file_timestamp`、`_safe_replace_file`、`ServerLogger`）
  - `ys_codebase/source/server/server/streamer.py:L14-L158`（`DebouncedIOStreamer`、`_StreamProxy`）
  - `ys_codebase/source/core/core/telemetry.py:L92-L259`（`extract_error_hint`、`record_cli_event`、`_rotate_telemetry_file`、`read_telemetry_records`）
  - `ys_codebase/source/core/core/commands/dispatcher.py:L154-L287, L545-L694, L709-L924`（熱/冷派發與 `_LAST_DISPATCH_ERROR_HINT`）
  - `ys_codebase/source/server/tests/test_server_logging.py:L205-L233, L336-L360`（`_safe_replace_file` mock 與 `_file.fileno()` 斷言）

---

## 5. 下一次接手時的第 1 步 (Immediate Next Action)
- 讀取 `.agents/skills/development-sop/references/phase_02_architecture.md`、`.agents/.yscb/templates/P02_architecture_plan.md` 與 `.agents/.yscb/templates/P06_test_plan.md`，為 `sub_01_core_log_pipeline_and_streamer_unification` 產出 `P02_architecture_plan.md` (`Confirmed`) 與 `P06_test_plan.md` (`Draft`)（若開發者授權 `/auto`，則依 `.agents/skills/auto/SKILL.md` 直接讀取 `.agents/.yscb/templates/PXX-05_auto.md` 連續推進 `P02-05_auto.md` 與代碼實作）。
