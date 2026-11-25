# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：Core 2.0 內核可觀測性、ImTK 風格效能剖析器與 3+1 全 JSONL 日誌體系  
> 建立日期：2026-11-25  
> 所屬主計畫：無（獨立 Full Track 計畫，承接 `TODO-31`）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (XHigh)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | ImTK 風格無全域單例階層 Profiler 基元 | 於 `core.foundation` 提供純標準庫 `Profiler` 協定、`ProfilerSession`、`ProfilerNodeSnapshot`、`NullProfiler`、`MemoryTrackingGuard`、`render_profiler_tree` 與 `read_process_rss_kb`；支援 `scope(path, name)`、`scope_relative(path, name)`、自動 Self/Total 拆帳、節點級 Caller 來源快取、`merge_subtree` 跨進程子樹合併及可選 `tracemalloc` 記憶體配置量測。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-02** | 3+1 全 JSONL 運行日誌與舊檔收斂 | 於 `.cache/logs/` 落地四條統一 JSONL 串流並共用 `trace_id`（`call_tree_id`）與 `daemon_boot_id`：(1) `daemon/daemon_<YYYYMMDD_HHMMSS>_<pid>_<boot8>.jsonl` 單次 Daemon 生命週期與熱請求收發摘要；(2) `daily/YYYY-MM-DD.jsonl` 跨冷熱單日主幹，任務前寫 `[IN]`、結束後寫 `[OUT]` 並收錄 Core 關鍵事件與模組 `WARNING`/`ERROR` 冒泡摘要；(3) `perf/YYYY-MM-DD.jsonl` 效能與任務分派日誌（全面取代 `.cache/core/telemetry.jsonl` 與 `SessionTelemetry*`），含分派 `Task` 清單、階層效能樹、RSS 水位，失敗或超慢時自動附加完整異常與現場快照；(4) `modules/<module_id>.jsonl` 承接原 `.cache/logs/<module>.jsonl`，保留模組完整中間態並自動注入關聯鍵。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | 跨進程貫穿、SDK 暴露與 Daemon Ring Buffer | `core.surface.sdk` 匯出 Profiler 公開契約並於 `TaskContext.profiler` / `ModuleEnv.profiler` 注入實例；`CallPropagationContext` 與 RPC / Tier 1 Worker 協議支援透傳 `profile_mem` 並回傳合併子進程 `ProfilerNodeSnapshot`；`WorkspaceDaemon` 維護有界記憶體 `ProfilerRingBuffer`（支援計算 `Latest/Avg/P95/Max`）並於關鍵接縫（`RuntimeDispatcher`、`HotWorkerPool`、`OneShotVenvHost`、`WorkspaceKernelFactory`、`SpaceScanner`、`ModuleDatabase`、`yscb.py`）埋設輕量 Scope。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-04** | 極簡全域 CLI 旗標與脫敏/組態控管 | `cli/parser.py`、`sdk/declarative.py`、`cli/help_renderer.py` 與 `core_v2/yscb.py` 同步登記極簡全域旗標 `--profile`（結束時將 ImTK 風格耗時樹輸出至 `stderr`，`--json` `stdout` 零污染）與 `--profile-mem`（並相容 `YSCB_PROFILE_MEM=1`，按需開啟 `tracemalloc` 並於 `finally` 冪等還原）；新增 `redact_sensitive_value`/`redact_cli_args` 脫敏器與 `core` 專案組態 `observability` 保留天數／檔案上限／慢查詢門檻設定；於 `primitives.py` `PUBLIC_ENV_ALLOWLIST` 註冊 `YSCB_PROFILE_MEM` 並定義私有 `_YSCB_FORCE_FLIGHT_LOGS`。 | P0 | [P00:DR-04] |
| **FR-05** | `TODO-31` Daemon 啟動效能實戰優化 | 運用本期 `perf/` 效能樹量測 `daemon start --supervisor`，於 `yscb.py` / `cli/entrypoint.py` / `bootstrap/factory.py`（相容既有 3 參數 `CliKernelFactoryFn` 與顯式 `kernel_factory`）消除雙重 `WorkspaceKernel` 建置，並為 `_CoreFileSig` 建立受 20ms Racy-Clean 窗口保護之持久化 stat→sha256 快取（`.cache/daemon/core_sig_cache.json`），維持 `os.utime()` 不誤觸交接與同大小內容改寫必觸交接之雙重契約。 | P0 | [P00:DR-05] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 行程硬當機（`SIGKILL`/OOM/死鎖）導致任務無機會執行結束收尾 | `daily/YYYY-MM-DD.jsonl` 於任務開始前先原子寫入 `[IN]` 紀錄，確保任何硬中斷後仍可精準定位未閉合 `[IN]` 之 `task_id`/`trace_id`/`pid`。 |
| **EC-02** | `TEST_SANDBOX_ENV_KEY`（`_YSCB_TEST_SANDBOX=1` 含相容注入鍵 `YSCB_TEST_SANDBOX=1`）、冷 `--help`、未初始化工作區或唯讀檔案系統 | 冷 `--help` 與未初始化目錄 0 寫盤；沙盒旗標為真時預設抑制自動 `daemon/`/`daily/`/`perf/` 落盤（提供顯式 `respect_sandbox=False` 或 `_YSCB_FORCE_FLIGHT_LOGS=1` 供實測，`profiler.py` 僅讀取注入之 `env` 參數不直讀 `os.environ`）；磁碟寫入遇 `OSError` / 權限拒絕一律 fail-open 絕不中斷業務 `Task`。 |
| **EC-03** | 多進程併發寫入 `daily/`、`perf/` 或跨日／達容量上限觸發輪替淘汰 | 複用 `LogRotator`（`O_NOFOLLOW` + 非繼承 FD + 崩潰換行修復）並於 Domain 1 以純標準庫（POSIX `fcntl.flock` / Windows `LockFileEx` 搭配 `O_NOFOLLOW` 同層 `.lock` 檔）實作輪替跨進程防呆鎖，確保 Windows/Linux 併發零截斷、零損毀、零 `ResourceWarning`。 |
| **EC-04** | CLI 參數或日誌 `fields` 夾帶機密（Token、Password、API Key、`_YSCB_*`、`--approve=`、`--flag val`、URL 憑證、`config set <mod> <secret_key> <val>`） | 落盤前於 `FlightLogRouter` 與 `_RotatorStructuredLogger` 強制經 `redact_cli_args` 與 `redact_sensitive_value` 遞迴替換為 `[REDACTED]`（不篡改原始 `LogRecord` 純值物件），杜絕下游回報日誌外洩機密。 |
| **EC-05** | `--profile-mem` 執行期間任務拋出例外或巢狀呼叫前外部已啟用 `tracemalloc` | `MemoryTrackingGuard` 記錄進場前 `tracemalloc.is_tracing()` 狀態，僅於自行啟動時在 `finally` 停止，確保異常安全與冪等還原。 |
| **EC-06** | 惡意或損壞之 Tier 1 Worker 回傳畸形 `profiler_tree` 欄位 | Wire DTO（`WorkerStepReply` / `DaemonRpcInvokeReply`）將 `profiler_tree` 型別設為 `Optional[JsonValue] = None`，通過 `DataclassCodec` 後由 `decode_profiler_snapshot(max_depth=32, max_nodes=512)` 嚴格校驗，畸形資料安全降級回傳 `None` 而不中斷主任務結果。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能開銷 | 預設常開時間樹（30 個巢狀 Scope、無 `tracemalloc`）單次呼叫純計時開銷 `< 0.5ms`；`TODO-31` 優化後 `daemon start --supervisor` 僅建置 1 次 `WorkspaceKernel` 且重啟未變更時透過 `core_sig_cache.json` 避免重算全量 92 檔 SHA-256。 |
| **NFR-02** | 空間與資源有界 | 三流與模組日誌均受 `max_bytes`、`max_history_files`、`retention_days`/`max_daemon_files` 嚴格封頂；`0 ResourceWarning`、0 遺留 FD。 |
| **NFR-03** | 架構純淨與雙模相容 | 100% 通過 `Gate 0`（更新後 6 域 DAG 白名單、17 份活規格 1:1 雙向對齊、0 `Any`/`print`/`getattr`/可變模組全域變數）、10 階段物理拔除 `unplug`、以及 Linux 標準與 `-O` 雙模全 9 套件驗證；1.x `ys_codebase/source/*` 零異動。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` `Gate 0` 剛性紅線**：`core_v2/tests/test_gate0.py` 禁止所有模組級可變全域物件（含裸 `dict`/`list`/`set`/`ContextVar`，常數映射須採 `Final[Mapping[...]] = MappingProxyType(...)`）、禁止 `Any`/`print`/`getattr`/`sys._getframe`（跨模組私有屬性呼叫）與審計工單標籤、限制 `os.environ` 僅限 5 支白名單檔，且 **允許** `inspect.currentframe()`（須於 `try ... finally: del frame` 防循環參照）；`test_gate0.py` 並強制維護 `_ALLOWED_CORE_IMPORTS_BY_PREFIX` 白名單及全部 17 份 Active Living Specs 1:1 雙向簽名與 `__abstractmethods__` 對齊。
- **`[!NOTE]` `yscb.py` 單檔純標準庫約束**：`core_v2/yscb.py` 在載入 `.modules/core` 前不能匯入 `core.*`，啟動時間點須透過關鍵字參數 `cli.main(..., boot_start_ns=...)` 傳遞（避免污染 `os.environ` 外洩至子進程）。
- **`[!NOTE]` `TODO-31` 雙契約守門**：`SingleFlightDaemonSpawner` 經由 `yscb.py` 顯式傳入 `kernel_factory` 啟動 `--supervisor`，優化須在顯式 `kernel_factory` 下依然生效；`_CoreFileSig` 須保留真 SHA-256 基線以同時滿足 `test_runtime_daemon.py:1069-1079`（`os.utime()` 不觸發 handoff + 同大小內容改寫必觸發 handoff）。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[yscb.py] (boot_start_ns)
   │
   ▼
[surface.cli: parser (--profile/--profile-mem) -> entrypoint]
   │ 1. 建立 root ProfilerSession(track_memory=profile_mem) + trace_id
   │ 2. 冷/RPC 邊界寫入 Stream 2 daily/[IN]，結束寫 [OUT] + Stream 3 perf/
   │ 3. 若 --profile，渲染 ImTK 階層樹輸出至 stderr (stdout 100% 純淨)
   ▼
[surface.bootstrap: factory (單次建核 --supervisor 直啟路徑, TODO-31)]
   │
   ▼
[execution.runtime: RuntimeDispatcher + services.py]
   ├── 綁定每呼叫上下文 (trace_id, span_id, task_id, exec_mode, daemon_boot_id, profiler)
   ├── 寫入 Stream 2 daily/YYYY-MM-DD.jsonl ([IN] 前置 / [OUT] 後置 / WARN+ERROR ALERT)
   ├── ctx.logger -> .cache/logs/modules/<mod>.jsonl (自動帶關聯鍵，完整中間態串流)
   ├── ctx.profiler -> ImTK 風格 scope() / scope_relative() (Tier 0 & Tier 1 對稱)
   ├── RPC / Worker 回包攜帶 profiler_tree + dispatched_tasks -> merge_subtree 掛回父樹
   └── 結束寫入 Stream 3 perf/YYYY-MM-DD.jsonl (失敗/超慢自動附 error_detail + runtime_snapshot)
   │
   ▼
[execution.daemon: WorkspaceDaemon]
   ├── 獨佔寫入 Stream 1 daemon/daemon_<ts>_<pid>_<boot8>.jsonl (生命週期 + 熱請求精簡收發)
   └── 記憶體 ProfilerRingBuffer (最近 512 筆 Turn 彙總，暴露輕量統計於狀態快照)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `core_v2/source/core/core/foundation/profiler.py` | New | ImTK 風格 `Profiler` 協定、`ProfilerSession`/`ProfilerScope`/`ProfilerNodeSnapshot`/`NullProfiler`、`MemoryTrackingGuard`、`ProfilerRingBuffer`、`render_profiler_tree`、`read_process_rss_kb`（Linux/macOS/Windows）、敏感脫敏與 3+1 JSONL 飛行日誌路由器 (`FlightLogConfig`/`FlightLogRouter`/`DaemonLogRecord`/`DailyEventRecord`/`ExecutionTraceRecord`) |
| `core_v2/source/core/core/foundation/{primitives,observability,__init__}.py` | Modify | `primitives.py` 註冊 `YSCB_PROFILE_MEM` 至 `PUBLIC_ENV_ALLOWLIST` 並新增私有 `FORCE_FLIGHT_LOGS_ENV_KEY = "_YSCB_FORCE_FLIGHT_LOGS"`；`observability.py` 擴充 `LogRecord` 關聯欄位、強化 `LogRotator` 純標準庫跨進程輪替鎖、移除退役 `SessionTelemetry*` 並自 `foundation/__init__.py` 匯出新可觀測性契約 |
| `core_v2/source/core/core/filesystem/space/scanner.py`、`storage/database.py` | Modify | 於 `SpaceScanner.__init__` 與 `ModuleDatabase.__init__` 新增選配 `profiler: Optional[Profiler] = None` 埋點（預設 `None` 零侵入） |
| `core_v2/source/core/core/execution/runtime/{contracts,wire,services,dispatcher,module_slot,worker_pool,worker_entry}.py` | Modify | 注入 `ModuleRuntimeServices.profiler` 與 `TaskContext.profiler` 預設具體屬性、擴充 `CallPropagationContext.profile_mem` 與 Wire DTO `profiler_tree: Optional[JsonValue]`（複用 `invoked_tasks`）、擴充既有 `_ActiveServicesHolder` 關聯鍵注入、遷移模組日誌至 `modules/<mod>.jsonl` 並冒泡 `WARN/ERROR` 至 `daily/`、落地單寫入者主權矩陣與關鍵接縫埋點 |
| `core_v2/source/core/core/execution/daemon/service.py` | Modify | 產生 `daemon_boot_id`、落盤 Stream 1 單次 Daemon 日誌、維護記憶體 `ProfilerRingBuffer` 並暴露於 `DaemonStatusSnapshot`、記錄 `daemon.boot`/`daemon.reload` 效能樹、為 `_CoreFileSig` 落地受 20ms Racy-Clean 保護之 `.cache/daemon/core_sig_cache.json` |
| `core_v2/source/core/core/surface/sdk/{__init__,declarative,client}.py` | Modify | 匯出 5 個 Profiler 契約至 `core.surface.sdk`（75 → 80 符號）、新增 `ModuleEnv.profiler`、於 `_RESERVED_GLOBAL_CLI_FLAGS` 登記 `profile`/`profile-mem` 並透傳 `YscbClient` 剖析設定 |
| `core_v2/source/core/core/surface/cli/{parser,help_renderer,entrypoint,__init__}.py` | Modify | 新增全域旗標 `--profile` / `--profile-mem`（含 `YSCB_PROFILE_MEM=1`）、更新 `help_renderer.py` 說明、以 `cli.main(..., boot_start_ns=...)` 承接自舉耗時、依單寫入者主權以 Stream 2/3 取代 `_record_cli_telemetry` 並於 `stderr` 渲染 `--profile` 樹 |
| `core_v2/source/core/core/surface/bootstrap/{factory,system_module}.py`、`core_v2/yscb.py`、`core_v2/source/core/configurable/config.project.json.tmpl` | Modify | `yscb.py` 同步 `_GLOBAL_LAUNCHER_FLAGS` 並傳遞 `boot_start_ns`；`factory.py` 透過輕量延遲 `CliKernelSession` 消除 `--supervisor` 雙重 `WorkspaceKernel` 建置（相容顯式 3 參數 `kernel_factory`）並補建核埋點；更新 `config.project.json.tmpl` 加入預設 `observability` 組態 |
| `core_v2/sub_module_design/{foundation/foundation,filesystem/space,filesystem/storage,execution/runtime,execution/daemon,surface/sdk,surface/cli,surface/composition_and_bootstrap}.md` | Modify | 同步更新全部 8 份受影響 Active Living Specs 與公開簽名對齊 |
| `core_v2/tests/{test_gate0,test_foundation_fs,test_runtime_daemon,test_surface_sdk,test_surface_cli_e2e,test_rc_e2e}.py` | Modify | 更新 `test_gate0.py` DAG 白名單（`core.foundation.profiler` 及 Domain 2 許可 + 負向 DAG 測試）；替換舊 `SessionTelemetry*` 測試為 3+1 JSONL / Profiler / 跨進程合併 / 脫敏 / `--profile` / `TODO-31` 全維度驗證 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 獨立 `foundation/profiler.py` 並顯式擴充 `Gate 0` 6 域白名單**：將 Profiler 與 3+1 JSONL 路由封裝於 Domain 1 `core/foundation/profiler.py`（純標準庫、僅讀注入 `env`、不直讀 `os.environ`、輪替鎖以純標準庫 `fcntl.flock`/`LockFileEx` 實作），並於 `test_gate0.py` 顯式將其加入 `_ALLOWED_CORE_IMPORTS_BY_PREFIX` 與 `core.filesystem.{space,storage}` 允許集合，確保 10 階段 `unplug` 100% 通過。
- **[P02:DR-02] 零可變模組全域與復用 `_ActiveServicesHolder`**：`ProfilerSession` 採實例私有 `threading.local()` 堆疊，Caller 來源於節點首次建立時透過 `inspect.currentframe()`（`try ... finally: del frame`）快取 `file:line`（嚴禁 `sys._getframe`）；執行期關聯鍵（`trace_id`/`span_id`/`task_id`/`exec_mode`/`daemon_boot_id`）直接擴充既有 `services.py:_ActiveServicesHolder`（實例級 TLS）並透過 `WorkerBootstrapConfig`/`WorkerCommandEnvelope` 透傳至 Tier 1 Worker，達成 0 模組級可變全域與零重複 TLS。
- **[P02:DR-03] 單寫入者主權矩陣（杜絕 Stream 2 / Stream 3 雙寫）**：
  1. **CLI 冷啟動**：`entrypoint.py` 為唯一寫入者（於調度前寫 `daily/[IN]`，結束寫 `daily/[OUT]` + 完整合併之 `perf/`），呼叫 `RuntimeDispatcher.invoke(..., external_flight_owner=True)` 抑制內層重複寫盤。
  2. **CLI → 熱 Daemon RPC**：`entrypoint.py` 為磁碟 `daily/` 與 `perf/` 之唯一寫入者（合併 CLI + RPC + Daemon + Tier 1 子樹為單筆 `perf/`）；Daemon 端僅寫入 **Stream 1 (`daemon/`)** 精簡收發摘要並更新記憶體 `ProfilerRingBuffer`（因 `caller_surface == CLI` 由外層主寫；若客戶端中途斷線則由 Daemon 補記異常摘要）。
  3. **CLI 前置解析／安全守門失敗**：`entrypoint.py` 直接寫入單組 `daily/[IN]/[OUT]` 與失敗 `perf/`（冷 `--help` 與未初始化目錄維持 0 寫盤）。
  4. **SDK `YscbClient` 直呼與 Daemon 背景任務（`watcher`/`periodic`/`emit_background_event`/`daemon.boot`）**：`external_flight_owner=False`，由 `RuntimeDispatcher`（或 `WorkspaceDaemon`）擔任 `daily/` 與 `perf/` 唯一寫入者。
- **[P02:DR-04] `TODO-31` 雙重消除策略**：(a) `WorkspaceKernelFactory.open_cli_session` 改回傳輕量延遲 `CliKernelSession` 代理（或在偵測 `core.daemon.start` `--supervisor`/`--console` 前置不急建冷核心，延後至 `run_deferred_daemon` 單次建置 `is_daemon_host=True` `WorkspaceKernel`），完整相容 `yscb.py` 顯式傳入之 3 參數 `kernel_factory`、pre-ready exit 1 與 `already_running` 契約；(b) `_scan_core_module_tree` 引入持久化 `.cache/daemon/core_sig_cache.json`（鍵值 `(rel_path, mtime_ns, size, ino) -> sha256`，受 20ms Racy-Clean 窗口保護），重啟未變更時免讀 92 檔同時保持 `_boot_core_snapshot` 真 SHA-256 契約。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# core/foundation/profiler.py (re-exported via core.foundation & selected subset via core.surface.sdk)
@dataclass(frozen=True, slots=True)
class ProfilerNodeSnapshot:
    name: str
    self_ms: float
    total_ms: float
    calls: int
    alloc_kb: float = 0.0
    callers: tuple[str, ...] = ()
    children: tuple[ProfilerNodeSnapshot, ...] = ()

class Profiler(Protocol):
    def scope(self, path: Optional[str] = None, name: Optional[str] = None, *, caller: Optional[str] = None) -> AbstractContextManager[None]: ...
    def scope_relative(self, path: str, name: Optional[str] = None, *, caller: Optional[str] = None) -> AbstractContextManager[None]: ...
    def merge_subtree(self, subtree: ProfilerNodeSnapshot, *, mount_path: Optional[str] = None) -> None: ...
    def snapshot(self) -> ProfilerNodeSnapshot: ...
    def current_span_path(self) -> str: ...

class NullProfiler:
    def scope(self, path: Optional[str] = None, name: Optional[str] = None, *, caller: Optional[str] = None) -> AbstractContextManager[None]: ...
    def scope_relative(self, path: str, name: Optional[str] = None, *, caller: Optional[str] = None) -> AbstractContextManager[None]: ...
    def merge_subtree(self, subtree: ProfilerNodeSnapshot, *, mount_path: Optional[str] = None) -> None: ...
    def snapshot(self) -> ProfilerNodeSnapshot: ...
    def current_span_path(self) -> str: ...

class ProfilerSession:
    def __init__(self, root_name: str = "Root", *, track_memory: bool = False, capture_callers: bool = True) -> None: ...
    @property
    def track_memory(self) -> bool: ...
    def scope(self, path: Optional[str] = None, name: Optional[str] = None, *, caller: Optional[str] = None) -> AbstractContextManager[None]: ...
    def scope_relative(self, path: str, name: Optional[str] = None, *, caller: Optional[str] = None) -> AbstractContextManager[None]: ...
    def merge_subtree(self, subtree: ProfilerNodeSnapshot, *, mount_path: Optional[str] = None) -> None: ...
    def snapshot(self) -> ProfilerNodeSnapshot: ...
    def current_span_path(self) -> str: ...

class MemoryTrackingGuard:
    def __init__(self, enabled: bool) -> None: ...
    def __enter__(self) -> MemoryTrackingGuard: ...
    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None: ...

@dataclass(frozen=True, slots=True)
class FlightLogConfig:
    enabled: bool = True
    max_bytes_per_file: int = 5242880
    max_history_files: int = 3
    retention_days: int = 7
    max_daemon_files: int = 10
    slow_threshold_ms: float = 1000.0
    respect_sandbox: bool = True

@dataclass(frozen=True, slots=True)
class DaemonLogRecord:
    ts_utc: str
    epoch_ms: int
    daemon_boot_id: str
    pid: int
    event: str
    level: LogLevel = LogLevel.INFO
    trace_id: str = ""
    task_id: str = ""
    detail: JsonObject = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class DailyEventRecord:
    ts_utc: str
    epoch_ms: int
    kind: str
    trace_id: str
    daemon_boot_id: str
    pid: int
    exec_mode: str
    module: str
    task_id: str = ""
    level: LogLevel = LogLevel.INFO
    ok: Optional[bool] = None
    duration_ms: Optional[float] = None
    exit_code: Optional[int] = None
    message: str = ""
    fields: JsonObject = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ExecutionTraceRecord:
    ts_utc: str
    epoch_ms: int
    trace_id: str
    daemon_boot_id: str
    pid: int
    task_id: str
    args: tuple[str, ...]
    caller_mode: str
    caller_cwd: str
    executed_hot: bool
    exit_code: int
    ok: bool
    duration_ms: float
    rss_kb: int = 0
    rss_delta_kb: int = 0
    mem_tracked: bool = False
    dispatched_tasks: tuple[str, ...] = ()
    profiler_tree: Optional[ProfilerNodeSnapshot] = None
    error_code: str = ""
    error_detail: Optional[JsonObject] = None
    runtime_snapshot: Optional[JsonObject] = None

class ProfilerRingBuffer:
    def __init__(self, maxlen: int = 512) -> None: ...
    def record(self, trace: ExecutionTraceRecord) -> None: ...
    def recent(self, limit: int = 50) -> tuple[ExecutionTraceRecord, ...]: ...
    def summarize(self) -> JsonObject: ...

class FlightLogRouter:
    def __init__(self, logs_root: HostPath, *, config: Optional[FlightLogConfig] = None, env: Optional[Mapping[str, str]] = None, daemon_boot_id: str = "") -> None: ...
    @property
    def enabled(self) -> bool: ...
    @property
    def daemon_boot_id(self) -> str: ...
    def daemon_log_path(self) -> Optional[HostPath]: ...
    def daily_log_path(self, *, date_str: Optional[str] = None) -> HostPath: ...
    def perf_log_path(self, *, date_str: Optional[str] = None) -> HostPath: ...
    def module_log_path(self, module_id: str) -> HostPath: ...
    def record_daemon(self, entry: DaemonLogRecord) -> None: ...
    def record_daily(self, entry: DailyEventRecord) -> None: ...
    def record_perf(self, entry: ExecutionTraceRecord) -> None: ...
    def read_recent_perf(self, *, limit: int = 100, date_str: Optional[str] = None) -> tuple[ExecutionTraceRecord, ...]: ...
    def close(self) -> None: ...

def redact_sensitive_value(value: JsonValue, *, key_hint: str = "") -> JsonValue: ...
def redact_cli_args(args: Sequence[str]) -> tuple[str, ...]: ...
def render_profiler_tree(root: ProfilerNodeSnapshot, *, include_mem: bool = False, include_callers: bool = True) -> str: ...
def read_process_rss_kb() -> int: ...
def decode_profiler_snapshot(raw: object, *, max_depth: int = 32, max_nodes: int = 512) -> Optional[ProfilerNodeSnapshot]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 所有值物件 `__post_init__` 採純型別與有界校驗（非法型別或負值拋 `ValueError`）；`decode_profiler_snapshot` 遇畸形或超深／超節點輸入回傳 `None`（永不拋例外破壞回包）。
  - `FlightLogRouter` 所有磁碟寫入與過期清理採 fail-open（捕獲 `OSError`/`YscbError`/`ValueError` 靜默降級），絕不影響業務 `Task` 退出碼；`LogRotator` 本體遇符號連結攻擊仍維持嚴格拒絕（`ErrorCode.ACCESS_DENIED`）。

### 3.2 既有活規格介面與 Wire DTO 變更差量 (Mutated Contracts & Wire DTOs)

```python
# core/foundation/primitives.py
FORCE_FLIGHT_LOGS_ENV_KEY: Final[str] = "_YSCB_FORCE_FLIGHT_LOGS"
# PUBLIC_ENV_ALLOWLIST adds "YSCB_PROFILE_MEM"

# core/foundation/observability.py (backward-compatible trailing defaults)
@dataclass(frozen=True, slots=True)
class LogRecord:
    ts_utc: str
    level: LogLevel
    logger_name: str
    message: str
    fields: JsonObject = field(default_factory=dict)
    trace_id: str = ""
    span_id: str = ""
    task_id: str = ""
    exec_mode: str = ""
    daemon_boot_id: str = ""
    pid: int = 0

# core/filesystem/space/scanner.py & storage/database.py
# SpaceScanner.__init__(..., profiler: Optional[Profiler] = None)
# ModuleDatabase.__init__(..., profiler: Optional[Profiler] = None)

# core/execution/runtime/contracts.py
# CallPropagationContext: adds profile_mem: bool = False (10 -> 11 fields)
# ModuleRuntimeServices: adds profiler: Profiler = field(default_factory=NullProfiler)
# TaskContext: adds concrete default property def profiler(self) -> Profiler (non-abstract)
# InvokeRequest: adds profile_mem: bool = False, external_flight_owner: bool = False, active_profiler: Optional[Profiler] = None

# core/execution/runtime/wire.py (EC-06 safe JsonValue; reuses existing invoked_tasks)
# WorkerBootstrapConfig: adds daemon_boot_id: str = "", flight_log_config: Optional[JsonObject] = None
# WorkerCommandEnvelope: adds profile_mem: bool = False, trace_id: str = "", exec_mode: str = "worker"
# WorkerStepReply: adds profiler_tree: Optional[JsonValue] = None
# DaemonRpcInvokeReply: adds profiler_tree: Optional[JsonValue] = None (reuses invoked_tasks)

# core/execution/runtime/dispatcher.py & core/execution/daemon/service.py
# DispatcherHostOptions: adds flight_log_router: Optional[FlightLogRouter] = None, daemon_boot_id: str = "", profiler_ring_buffer: Optional[ProfilerRingBuffer] = None
# WorkspaceDaemon.__init__(..., flight_log_router: Optional[FlightLogRouter] = None, daemon_boot_id: str = "")
# DaemonStatusSnapshot: adds daemon_boot_id: str = "", profiler_summary: JsonObject = field(default_factory=dict)

# core/surface/sdk/declarative.py & core/surface/cli/{parser,entrypoint}.py
# ModuleEnv: adds @property def profiler(self) -> Profiler
# GlobalCliFlags: adds profile: bool = False, profile_mem: bool = False
# cli.main(..., boot_start_ns: Optional[int] = None) -> int
```

- **階段決策紀錄**：`[P03:DR-01]` 移除 `SessionTelemetryRecord` / `SessionTelemetryWriter` 並以 `ExecutionTraceRecord` / `FlightLogRouter` 全面取代；`core.surface.sdk.__all__` 新增匯出 `Profiler`、`ProfilerNodeSnapshot`、`ProfilerSession`、`NullProfiler`、`render_profiler_tree`（由 75 升至 80 符號）；`TaskContext.profiler` 採具預設實作之非抽象屬性以保護外部與測試 Stub 實作並維持 `runtime.md` `__abstractmethods__` 對齊。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與檔案矩陣完整對齊。
- [x] **邊界防護**：EC-01 ~ EC-06 涵蓋硬當機孤兒 `[IN]`、沙盒/冷 `--help` 0 寫盤、多進程輪替鎖、敏感欄位脫敏、`tracemalloc` 冪等還原與惡意子樹限深。
- [x] **依賴純淨**：Domain 1 純標準庫、0 可變模組全域、6 域 DAG 與 10 階段 `unplug` 100% 守門。
- **靈魂拷問與防護解法**：
  1. *若 `--profile` 印樹時遇到 `--json` 模式是否會污染機器解析？* -> 強制輸出至 `stderr`，`stdout` 僅保留合法 JSON 並以自動化測試斷言 `json.loads(stdout)` 100% 純淨。
  2. *若 `daemon start --supervisor` 跳過首次冷核心建置，是否會繞過原有安全守門或參數校驗？* -> 仍經由 `cli/parser.py` 靜態解析與 `CallerMode` 安全分級檢查，僅將 `WorkspaceKernelFactory.create` 收斂至 `run_deferred_daemon` 單點建立，安全邊界 0 放寬。
  3. *若 `_CoreFileSig` 避免啟動期全量 SHA-256，檔案同秒同大小原地改寫會不會漏檢熱重載？* -> 改採持久化 `.cache/daemon/core_sig_cache.json`（鍵值 `(rel_path, mtime_ns, size, ino) -> sha256` 並加 20ms Racy-Clean 窗口保護），啟動期 `_boot_core_snapshot` 仍持有 100% 真實 SHA-256 摘要，同時滿足 `os.utime()` 不誤觸 handoff 與同大小內容改寫必觸 handoff（`test_runtime_daemon.py:1069-1079`）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **活規格 (Meso)** | `core_v2/sub_module_design/{foundation/foundation,filesystem/space,filesystem/storage,execution/runtime,execution/daemon,surface/sdk,surface/cli,surface/composition_and_bootstrap}.md` | Modify | 同步新增/替換之公開類別、函式簽名、`__all__` 與 3+1 日誌契約（8 份 Active Living Specs） |
| **交接與路線圖** | `core_v2/ROADMAP.md`、`core_v2/handoff.md` | Modify | Phase 7 結案時更新 3+1 日誌、Profiler 與 `TODO-31` 優化成果 |
| **1.x 知識庫** | `docs/<Category>/*.md` | N/A | 潔淨室邊界不異動 1.x 文檔 |
| **微觀註解** | 受異動之 `core_v2/source/core/core/**/*.py` | Modify | 同步更新新增模組與公開介面 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | Phase 7 結案時記錄本計畫發布摘要 |

- **決策定稿**：**[P04:DR-01]** 採 3 路嚴格分層推進（Domain 1 底座 + Domain 2 選配埋點 -> Domain 5 跨進程執行與 Daemon 日誌 -> Domain 6 SDK/CLI/Bootstrap 與 `TODO-31` 實戰優化），動刀前先過盲眼 `Pre-Code Analyze Gate`，每層完成即跑靶向套件，最終通過 `Gate 0`、10 階段 `unplug`、雙模全 9 套件與 Pre-UX 唯讀盲審。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 Domain 1 `foundation/profiler.py`（ImTK 風格 `Profiler`/`ProfilerSession`/`ProfilerNodeSnapshot`/`NullProfiler`/`MemoryTrackingGuard`/`ProfilerRingBuffer`/`render_profiler_tree`/`read_process_rss_kb`、脫敏器、3+1 JSONL `FlightLogRouter` 與紀錄 DTO）、擴充 `LogRecord` 與輪替跨進程保護、移除 `SessionTelemetry*` 並更新 `foundation/__init__.py` 與 `test_foundation_fs.py`
- [x] **TASK-02**：於 Domain 2 (`SpaceScanner`/`ModuleDatabase`) 與 Domain 5 (`execution/runtime/*` + `execution/daemon/service.py`) 落地 `ModuleRuntimeServices.profiler`、跨進程 `profile_mem`/`profiler_tree` 回傳合併、每呼叫關聯鍵自動注入 `modules/<mod>.jsonl` + `WARN/ERROR` 冒泡、Stream 1 (`daemon/`)、Stream 2 (`daily/` `[IN]`/`[OUT]`)、Stream 3 (`perf/`)、Daemon `ProfilerRingBuffer` 與關鍵接縫埋點，補齊 `test_runtime_daemon.py` / `test_rc_e2e.py` 驗證
- [x] **TASK-03**：於 Domain 6 (`surface/sdk/*`、`surface/cli/*`、`surface/bootstrap/*`) 與 `core_v2/yscb.py` 匯出 SDK `Profiler` 契約與 `ctx.profiler`/`env.profiler`、新增極簡全域 `--profile`/`--profile-mem` 旗標、移除 `_record_cli_telemetry` 改走 Stream 2/3、更新 `config.project.json.tmpl` 並完成 **`TODO-31`** 實戰剖析與優化，補齊 `test_surface_sdk.py` / `test_surface_cli_e2e.py` 測試
- [x] **TASK-DOC**：同步更新全部 8 份受影響之 `core_v2/sub_module_design/{foundation/foundation,filesystem/space,filesystem/storage,execution/runtime,execution/daemon,surface/sdk,surface/cli,surface/composition_and_bootstrap}.md` 活規格與源碼 Docstrings，確保 `Gate 0`、10 階段 `unplug` 與標準/`-O` 雙模全 9 套件 100% 通過

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-02** | Minor | `DaemonStatusSnapshot` 既有欄位已含 `boot_id: str`，避免重複新增 `daemon_boot_id`；另 `FlightLogRouter` 維持 `_config` 私有避免跨協作私有存取違規。 | 複用 `DaemonStatusSnapshot.boot_id` 並僅新增 `profiler_summary`（同步 `daemon.md`）；`dispatcher.py` 由 `config_view` 讀取 `observability.slow_threshold_ms`。 |
| **TASK-03** | Minor | `cli/index.py` 另有 `_RESERVED_GLOBAL_CLI_FLAGS` 需與 `declarative.py`/`parser.py` 同步；`TODO-31` Part A 透過 `open_cli_session` 回傳輕量 `_LazyCliKernelSession` 兼顧 `yscb.py` 顯式 3 參數 `kernel_factory`。 | 同步登記 `--profile`/`--profile-mem` 於全部 5 處全域旗標表；於 `factory.py` 落地 `_LazyCliKernelSession` 並以實測確認 `WorkspaceKernel.__init__` 嚴格降為 1 次。 |
| **PRE-UX** | Minor | Pre-UX 唯讀盲審檢出 4 項實質瑕疵（`YscbClient`→熱 Daemon 雙寫 `daily/`/`perf/`、`factory`/`daemon`/`sdk` 漏讀 `_YSCB_FORCE_FLIGHT_LOGS` 與舊 `YSCB_TEST_SANDBOX`、巢狀 RPC 硬編 `mount_path="Runtime/RpcCall"` 雙計時、`_LazyCliDispatcherProxy` 繞過 `allow_conditional`/`DaemonStartInput` 校驗）及 4 項衛生細節。 | 於 `wire.py` 新增 `DaemonRpcInvokeEnvelope.client_owns_flight_logs`、於 `proc.py` 新增並於 `foundation.md` 同步 `read_flight_log_env()`、`dispatcher.py` 改無參 `merge_subtree`、`factory.py` 補嚴格守門與解碼、修補 4 項細節與補齊回歸測項，重跑雙模全綠並獲盲審 `REVIEW_STATUS: PASSED`。 |
| **WIN-UX** | Minor | Windows 11 實機全 9 套件驗收揭露 3 項跨平台實務問題：(1) 4 進程併發 `os.makedirs` 下 CPython `ntpath.realpath()` TOCTOU 殘留 `\\?\` 前綴導致 `commonpath` 拋 `SECURITY_GATED`；(2) `invoke_daemon_rpc` 於 `daily/[IN]` 寫盤前即啟動 `DeadlineGuard` 倒數，在 Windows NTFS 尖峰下吃掉 `space.tier0_timeout` 逾時預算；(3) `test_rc_e2e.py` `RC-03` 缺少 `on_progress` 屏障且 `RC-08` `timeout_ms=120` 視窗過窄。 | 新增並於 `foundation/__init__.py` 與 `foundation.md` 匯出 `safe_realpath()` 剝除瞬態 `\\?\X:\`/`\\?\UNC\` 前綴並替換全核心所有 `os.path.realpath` 呼叫點；將 `invoke_daemon_rpc` 改為先校驗再傳 `initial_timeout_ms` 至 `_invoke_raw` 於 `daily/[IN]` 後起算 `DeadlineGuard`；補齊 `RC-03` `bg_in_loop` 屏障與 `RC-08` `timeout_ms=250` 視窗，Windows 11 全 9 套件 100% 通過。 |
| **P7-BLIND** | Minor | Phase 7 Pillar 3 跨模組冷眼盲審檢出 3 處遺漏之裸 `os.path.realpath`（`packaging/env/pool.py`、`packaging/installer/provider.py`、`filesystem/space/scanner.py`）、`safe_realpath` 缺單測、`_LazyCliDispatcherProxy` 漏檢 `STRICT_HOT`/事件鏈/熱容器/呼叫者模組守門，以及測試重用單一 `lazy_sess` 導致後續 4 例繞過代理。 | 全數收斂 3 處為 `safe_realpath` 並於 `test_foundation_fs.py` 補齊 drive/UNC/Volume/顯式前綴單測；於 `factory.py` 補齊 Stage-1 與 `resolve_active_caller_module() is None` 完整條件並將 `test_surface_cli_e2e.py` 改為 5 例獨立未物化會話，複核獲 `REVIEW_STATUS: PASSED`。 |
