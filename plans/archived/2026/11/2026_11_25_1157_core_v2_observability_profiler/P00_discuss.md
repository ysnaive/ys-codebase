# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Core 2.0 內核可觀測性、ImTK 風格效能剖析器與 3+1 全 JSONL 日誌體系  
> 建立日期：2026-11-25  
> 所屬主計畫：無（獨立 Full Track 計畫，承接 `TODO-31`）  
> 狀態：Confirmed  
> 模型：Gemini 4 Neon (XHigh)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：Core 2.0 已具備 62K+ LOC 跨進程微內核規模，屬高密度運維黑箱卻仍缺乏效能分析與系統化飛行紀錄。期望參考既有機制 `ysnaive/ImTK`（`ImTKProfiler` 階層路徑樹與 `DebugTools` 設計思路），將輕量效能剖析與結構化 JSONL 運行日誌直接歸入 `Core 2.0` 預設常開，讓下游真實使用端遇問題時可直接附帶日誌回報，並順勢以真實剖析數據優化 `TODO-31`。
- **核心目標**：
  1. 於 `Core 2.0` 內建 ImTK 風格極薄階層式效能剖析器（時間樹 + RSS 水位預設常開，記憶體配置 `tracemalloc` 按需開啟），支援跨進程（CLI → Daemon → Tier 1 Worker）子樹自動合併並透過 `ctx.profiler` / `env.profiler` 暴露給下游模組。
  2. 落地統一採 JSONL 格式、共用 `trace_id` 與 `daemon_boot_id` 之 **3+1 運行日誌架構**（單次 Daemon 日誌、單日跨冷熱 `[IN]`/`[OUT]` 主幹日誌、效能與任務分派日誌、以及各模組完整中間態串流），具容量/天數封頂與敏感資料脫敏。
  3. 新增極簡全域 CLI 旗標 `--profile`（`stderr` 印樹，不污染 `--json`）與 `--profile-mem`（啟用 `tracemalloc`），並以新剖析樹實戰驗證並根治 `TODO-31`（`daemon start --supervisor` 雙重 `WorkspaceKernel` 建置與全量 `.modules/core` SHA-256 重算）。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用並擴充 `core.foundation.observability` 既有 `LogRotator`（無符號連結、非繼承 FD、崩潰恢復）、`LogRecord`、`StructuredLogger` 及 `CallPropagationContext.call_tree_id`（統一作為 `trace_id`）。
  - 演進升級並取代既有外殼殘缺之 `.cache/core/telemetry.jsonl`（`SessionTelemetryRecord` / `SessionTelemetryWriter`）為 Stream 3 效能運行日誌；將 `execution/runtime/services.py` 既有 `.cache/logs/<module>.jsonl` 整理至 `.cache/logs/modules/<module>.jsonl` 並自動注入關聯鍵。
- **邊界排除 (Explicitly Excluded)**：
  - **延後 CLI 檢視／打包 UX**：`yscb diag <perf|logs|inspect|bundle>` 與 Chrome Trace 匯出明確排除於本期之外（已獨立登錄為 `TODO-32`），本期直接以結構化 JSONL 檔案與 `--profile` 輸出供開發者／AI 查閱。
  - **非本期技術債與波段**：不更動 `TODO-30`（Windows 測試孤兒行程清理）、不展開 `dev 2.0`（Wave 1.3）、不觸碰 1.x `ys_codebase/source/*` 與 `.vscode/settings.json`。
- **架構影響範圍**：
  - `Domain 1 (core/foundation/)`：新增輕量 Profiler 基元、脫敏與 3+1 日誌路由／保留策略，升級 `LogRecord` 與取代 `SessionTelemetry*`（100% 純標準庫，零 `Gate 0` 可變全域違反）。
  - `Domain 2 (core/filesystem/)`：於 `SpaceScanner` / `ModuleDatabase` 關鍵熱點注入選配輕量 Profiler 埋點。
  - `Domain 5 (core/execution/)`：`RuntimeDispatcher`、`HotWorkerPool`/`OneShotVenvHost`、`worker_entry.py`、`wire.py`、`services.py`、`WorkspaceDaemon`（跨進程 `trace_id` 與子樹回傳合併、Daemon 記憶體 Ring Buffer、Stream 1/2/3/Module 日誌掛鉤）。
  - `Domain 6 (core/surface/)`：`core.surface.sdk` 匯出 `Profiler` 契約與 `ctx.profiler`/`env.profiler`；`cli/parser.py` 與 `cli/entrypoint.py` 支援 `--profile`/`--profile-mem` 並整合 Stream 2/3；`bootstrap/factory.py` 與 `core_v2/yscb.py` 補齊自舉與建核埋點並收斂 `TODO-31`；同步更新受影響之 Active Living Specs、組態模板與 `core_v2/tests/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 歸屬 Core 內建與預設常開低開銷策略（Axis 1 & 2）**：剖析器與 3+1 日誌直接歸入 `Core 2.0` 預設開啟，確保下游真實運行端無須安裝開發模組即可留存故障證據；預設僅啟用 `perf_counter_ns` 階層時間樹（關鍵接縫 ~15–40 Scope，目標額外開銷 `< 0.3ms / 次`）與起訖 OS RSS 水位，`tracemalloc` 逐 Scope 記憶體配置剖析僅於 `--profile-mem` 或 `YSCB_PROFILE_MEM=1` 開啟。
- **[P00:DR-02] 3+1 全 JSONL 日誌拓撲與舊檔收斂（Axis 1 & 4）**：統一落盤於 `.cache/logs/` 且四流全採 JSONL，共用 `trace_id`（`call_tree_id`）與 `daemon_boot_id`：
  1. `daemon/daemon_<YYYYMMDD_HHMMSS>_<pid>_<boot8>.jsonl`：純粹單次 Daemon 行程生命週期事件與熱請求精簡收發摘要（單寫入者無鎖競爭，不重複抄寫模組業務中間態）。
  2. `daily/YYYY-MM-DD.jsonl`：跨冷熱單日動態滾動主幹，採任務開始前寫 `[IN]`、結束後寫 `[OUT]`（確保 OOM/`SIGKILL`/死鎖留存孤兒 `[IN]` 軌跡），並收錄 Core 關鍵事件與模組 `WARNING`/`ERROR` 冒泡摘要。
  3. `perf/YYYY-MM-DD.jsonl`：效能與任務分派運行日誌，**直接升級取代 `.cache/core/telemetry.jsonl` 及 `SessionTelemetry*`**，記錄完整跨進程分派樹（含巢狀呼叫、Tier 1 Worker 子樹與 Step 5 訂閱 `Task`）、ImTK 風格階層耗時樹（`self_ms`/`total_ms`/`pct`/`calls`/`caller`/`alloc_kb`）、RSS 水位，以及失敗／超慢自動附帶完整異常與鎖/佇列現場快照；Daemon 端同步維護記憶體 Rolling Ring Buffer。
  4. `modules/<module_id>.jsonl`：承接並遷入原 `.cache/logs/<module>.jsonl`，保留各模組經 `ctx.logger`/`env.logger` 寫出之完整中間態串流，自動補齊關聯鍵（`trace_id`/`span_id`/`task_id`/`exec_mode`/`daemon_boot_id`）。
- **[P00:DR-03] ImTK 風格無全域單例 Profiler 設計（Axis 1 & 4）**：於 `foundation` 實作不可變快照 + 作用域式 `ProfilerSession`/`ProfilerScope`（支援 `scope("A/B")`、`scope_relative("C")`、`scope("Group", name)`、自動 Self/Total 拆帳、節點首次建立快取 Caller `file:line` 避免熱路徑反射），透過顯式 DI 與 `ContextVar` 傳遞以嚴守 `Gate 0` 零可變模組全域與 6 域 DAG 紅線。
- **[P00:DR-04] 極簡全域 CLI 旗標與安全/沙盒/異常防呆（Axis 2 & 3）**：新增全域旗標 `--profile`（結束時將階層耗時樹渲染至 `stderr`，嚴守 `--json` `stdout` 100% 純淨）與 `--profile-mem`（含 `YSCB_PROFILE_MEM=1`，啟用 `tracemalloc` 並於 `finally` 冪等恢復原狀態）；落盤前強制對敏感鍵（`token`/`secret`/`password`/`key`/`auth`/`_YSCB_*` 等）脫敏；冷 `--help` 與未初始化工作區維持 0 寫盤；`TEST_SANDBOX_ENV_KEY`（`_YSCB_TEST_SANDBOX=1`，並相容注入之 `YSCB_TEST_SANDBOX=1`）預設抑制自動飛行日誌寫盤（提供顯式參數或 `_YSCB_FORCE_FLIGHT_LOGS=1` 覆寫供實測驗證）；日誌 I/O 遇異常 fail-open 絕不中斷業務任務。
- **[P00:DR-05] `TODO-31` 實戰狗食優化納入本期**：完成內核埋點後，即以新 `perf/` 效能樹量測 `daemon start --supervisor` 啟動瓶頸，消除 CLI 會話與 `run_deferred_daemon` 間重複建置 `WorkspaceKernel` 與啟動期無條件全掃 `.modules/core` SHA-256 熱點，驗證優化前後耗時改善。
- **[P00:DR-06] 顯式排除與分流模式（Axis 5）**：`yscb diag` CLI UX 已延後至 `TODO-32`；本計畫跨 Domain 1/2/5/6 與多份 Active Living Specs 且含公開 SDK/Foundation API 演進，判定採 **Full Track** 模式推進。

---

## 3. 開放議題與確認紀錄

- 所有核心設計議題（預設常開歸入 Core、3+1 全 JSONL 分流與 `[IN]`/`[OUT]` 收斂、取代 `telemetry.jsonl`、極簡 `--profile`/`--profile-mem`、延後 `yscb diag` 至 `TODO-32`、納入 `TODO-31` 實戰優化）均已於討論階段獲開發者明確拍板確認，無遺留未決事項。
