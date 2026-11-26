# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Core 2.0 下游基建高優先回補（遷移回滾、熱 Worker 呈現、憑證防護、子行程 I/O 與空間反解）  
> 建立日期：2026-11-26  
> 所屬主計畫：無（獨立 Full Track 計畫，於 Wave 1.3 `dev 2.0` 與 Wave 2 模組移植前堵死盲眼審計檢出之 5 項高優先內核缺漏）  
> 狀態：Confirmed  
> 模型：Gemini 4 Neon (XHigh)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對 `/blind-subagent`（以虛構全新下游套件 `dep-guard` 視角）所檢出並經主代理第一手查證之 Core 2.0 基建缺漏，優先修復 5 項高優先內核回補（`P0-2`、`P1-1`、`P0-3`、`P0-4`、`P1-2`），並拍板採用 **`1A + 2A + 3B + 4A`** 方案組合。
- **核心目標**：
  1. **遷移生命週期與 `.storage.local/` 交易回滾 (`P0-2 / 1A`)**：修正升級執行 `@on_migrate` 前誤先觸發新版 `Module.on_init()` 之時序缺陷，並於 `migration_rollback_scope` 僅對本次升級且含 `@on_migrate` 之目標模組暫存備份 `.storage.local/<mod>/`（含 `.db-wal`/`.db-shm`），失敗時原子還原。
  2. **Tier 1 呈現與退出碼熱 Worker 化 (`P1-1`)**：將 `HumanRenderable`、`ExitCodeProvider` 與 `format_output` 下沉至 Domain 5，讓執行該步之溫熱 Worker（與 Tier 0 Slot）於 `CallerSurface.CLI` 直接在原物件上求值並隨 `WorkerStepReply` / `DaemonRpcInvokeReply` / `TaskOutcome` 帶回 `rendered_text` 與 `exit_code`，刪除每次熱呼叫另起冷子行程並根除失敗吞成退出碼 `0`（CI 假綠）。
  3. **Secret 憑證安全閉環 (`P0-3 / 2A`)**：於 SDK 提供 `secret_field(...)` 標記（`metadata={"yscb_secret": True}`，JSON Schema 導出 `writeOnly: true` 與 `x-yscb-secret: true`）；寫入 `.config.local/` 強制 POSIX `0o600`（目錄 `0o700`）；將 `.config.local/` 自常態 `SnapshotVault`（`.snapshots/`）排除；`core.config.{list,get,inspect}` 對 `config.local` 來源值、`secret_field` 標記鍵及敏感鍵名一律脫敏為 `"[REDACTED]"`。
  4. **受管子行程 `stdin` 與工具鏈環境透傳 (`P0-4 / 3B`)**：為 `ManagedProcessTree` 與 `TaskContext.run_process` 補齊 `input: Optional[str | bytes] = None`（獨立寫入執行緒防大 payload 管道死鎖）與 `inherit_toolchain_env: bool = True`（內建無憑證明文之 `TOOLCHAIN_ENV_ALLOWLIST`），不擴充 `manifest.json`。
  5. **`SpaceClient` 路徑反解與空間匹配 (`P1-2 / 4A`)**：新增 2 支無鎖併發讀 `SDK_ONLY` 系統任務 `core.space.resolve_uri` / `core.space.match_spaces` 及對應 `ctx.spaces.resolve_uri(space_id, rel_path) -> SemanticUri` 與 `ctx.spaces.match_spaces(uri_or_path) -> tuple[SpaceId, ...]`。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用既有 `foundation/profiler.py` 敏感鍵脫敏規則（抽為共用純函式供 `profiler` 與 `core.config.*` 共享，杜絕雙份敏感關鍵字表）。
  - 復用既有 `HumanRenderable`/`ExitCodeProvider`/`format_output` 下沉至 Domain 5 `execution/runtime/contracts.py`（維持 6 域 DAG 零反向依賴與 10 階段 `unplug` 全綠）。
  - 復用既有 `SpaceRegistry.resolve_file_path` 與 `SpaceRegistry.match_path` 暴露為無鎖 `SDK_ONLY` 任務。
  - 復用既有 `OfflinePackageEngine.migration_rollback_scope` 與 `atomic_write_json`（新增選配 `file_mode` 與父目錄 `dir_mode` 參數）。
- **邊界排除 (Explicitly Excluded)**：
  - 磁碟模組 `config.schema.json` / `contributes/_schema.json` 編譯載入閉環（已登記 `TODO-35`，歸屬 `dev 2.0` 協同設計）。
  - 強隔離下跨模組 `TaskRef` / DTO / 自訂事件契約共享機制（已登記 `TODO-36`，歸屬 `dev 2.0` 協同設計）。
  - `@periodic` 持久化排程基準、長週期與 Idle TTL 協調及背景錯誤檢視（已登記 `TODO-37`）。
  - 不擴充 `manifest.json` 欄位（不加 `allowed_env_keys`，依 `3B` 決策）。
  - 不實作跨進程有狀態 `consume_diff` 租約 pin（依 `4A` 決策）。
  - 1.x 主線源碼 `ys_codebase/source/*` 與既有 `.vscode/settings.json` 全程零異動。
- **架構影響範圍**：Domain 1（`foundation/{primitives,codec,proc,profiler}`）、Domain 2（`filesystem/fs/atomic.py`）、Domain 3（`metadata/config/{matrix,snapshot}`）、Domain 4（`packaging/installer/engine.py`）、Domain 5（`execution/runtime/{contracts,wire,module_slot,step_host,worker_entry,dispatcher}`）、Domain 6（`surface/{sdk,cli,bootstrap}`），對應 Active Living Specs 與 `core_v2/tests/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `@on_migrate` 跳過 `on_init()` 與按需 `.storage.local/<mod>/` 交易回滾 (`1A`)**：
  - `invoke_internal_migration` 透過專用內部旗標 `skip_module_init=True`（僅允許 `is_internal_trigger=True` 且目標任務為 `<mod>.yscb_on_migrate`）於冷派發載入新版模組但不呼叫 `on_init()`，並確保冷 Tier 0/1 資源於返回前 100% 關閉（防 Windows SQLite 檔案句柄鎖定）。
  - `migration_rollback_scope()` 回傳具備 `snapshot_module_storage_local(module_id)` 與 `restore()` 之交易控制物件；`system_module.py` 僅於確認 `trans.is_upgrade` 且 `_module_declares_on_migrate` 為真時，在執行遷移前即刻快照 `.storage.local/<mod>/` 至 `0o700` `.temp/`，遷移異常時原子還原（含 WAL/SHM 清理與回復），成功或 `finally` 即刻清理暫存；常態 `SnapshotVault`（`.snapshots/`）維持排除 `.storage.local/`。
- **[P00:DR-02] Tier 1/0 呈現與退出碼移回執行期（消滅冷子行程與 CI 假綠）**：
  - 將 `HumanRenderable`、`ExitCodeProvider` 與 `format_output` 下沉至 `core.execution.runtime.contracts`（由 `core.surface.sdk` / `core.surface.sdk.advanced` 單向 Re-export，維持 52+38 層級不變）。
  - 於 `InvokeRequest` / `WorkerCommandEnvelope` / `DaemonRpcInvokeEnvelope` 新增 `include_presentation: bool = False`（CLI 呼叫才啟用），並於 `WorkerStepReply` / `StepExecutionResult` / `DaemonRpcInvokeReply` / `TaskOutcome` 新增 `rendered_text: Optional[str] = None` 與 `exit_code: Optional[int] = None`；由原執行 Slot / 溫熱 Worker 直接在強型別物件上求值回傳，移除 `factory.py` `_resolve_tier1_disk_presentation` 冷子行程與 `_TIER1_FORMAT_SNIPPET`，若 `render_text()` 或 `exit_code()` 拋例外則明確失敗回報，杜絕退出碼靜默回落 `0`。
- **[P00:DR-03] Secret 憑證安全閉環 (`2A`)**：
  - 於 `core.surface.sdk` 新增 `secret_field(...)`（回傳 `dataclasses.field(..., metadata={"yscb_secret": True})`；`core.surface.sdk` 升級為 53 符號並同步更新 `sdk.md` 與 `Gate 0`），`SchemaExporter` 辨識 `yscb_secret` 並輸出 `"writeOnly": true` 與 `"x-yscb-secret": true`。
  - `atomic_write_json` / `atomic_write_bytes` 新增選配 `file_mode: Optional[int] = None`，`ConfigStore` 寫入 `.config.local/<mod>/config.local.json` 時傳入 `0o600`（POSIX 生效，父目錄 `0o700`）；`SnapshotVault._CFG_BACKUP_AREAS` 移除 `.config.local`（僅留 `config`、`storage` 與 `yscb.config.json`）。
  - `core.config.{list,get,inspect}` 對所有源自 `config.local.json` 的鍵、Schema/dataclass 標記 `yscb_secret`/`writeOnly` 的鍵，以及命中共用敏感鍵名規則的鍵一律遮罩為 `"[REDACTED]"`（`core.config.set` 對 local 或敏感鍵亦遮罩回傳值；模組業務邏輯仍透過 `ctx.load_config(MyCfg)` 讀取強型別原值）。
- **[P00:DR-04] `run_process` `stdin`、`bytes` 輸出與工具鏈環境白名單 (`3B`)**：
  - `ManagedProcessTree` 新增 `pipe_stdin: bool = False` 與 `stdin_pipe`（併入 `close_pipes()` 防 FD 洩漏）；`ProcessResult` 補入 `stdout_bytes: bytes = b""` 與 `stderr_bytes: bytes = b""`；`TaskContext.run_process` 新增 `input: Optional[str | bytes] = None`（以背景寫入執行緒分塊寫入並 `close()`，處理 `BrokenPipeError` 與取消中斷防死鎖）與 `inherit_toolchain_env: bool = True`。
  - 於 `foundation.primitives` 新增無憑證明文之 `TOOLCHAIN_ENV_ALLOWLIST`（代理 `HTTP(S)_PROXY`/`NO_PROXY`、CA 憑證路徑 `SSL_CERT_FILE`/`SSL_CERT_DIR`/`REQUESTS_CA_BUNDLE`/`NODE_EXTRA_CA_CERTS`、工具鏈與 SSH 代理 `SSH_AUTH_SOCK`/`GIT_SSH_COMMAND`/`CARGO_HOME`/`RUSTUP_HOME`/`GOPATH`/`GOMODCACHE`/`NPM_CONFIG_REGISTRY`/`XDG_CONFIG_HOME`/`XDG_CACHE_HOME`），於 `run_process` 依 `inherit_toolchain_env` 疊加（仍過濾 `_YSCB_*` 與 Python 劫持鍵），不改動 `manifest.json`。
- **[P00:DR-05] `SpaceClient` 新增無鎖路徑反解與匹配 (`4A`)**：
  - 於 `CoreSystemModule` 新增 2 支 `ConcurrencyMode.PARALLEL`、`TaskExposure.SDK_ONLY` 系統任務：`core.space.resolve_uri`（依 `SpaceRegistry.resolve_file_path` 轉為 `SemanticUri`，經 `ScopedVfs` 讀權限核驗防越權外洩）與 `core.space.match_spaces`（依 `SpaceRegistry.match_path` 回傳 `tuple[SpaceId, ...]`）。
  - 於 `SpaceClient` 新增對應方法 `resolve_uri(space_id, rel_path) -> SemanticUri` 與 `match_spaces(uri_or_path) -> tuple[SpaceId, ...]`。

---

## 3. 開放議題與確認紀錄

- **子項確認 1（2A — `yscb config get` 不提供 `--reveal`）**：已由開發者確認定案——CLI 永不明文回顯 Secret 與 `config.local` 原文，模組內部透過 `ctx.load_config(MyCfg)` 讀取強型別原值。
- **子項確認 2（3B — `ProcessResult` 補入原始 `bytes`）**：已由開發者確認定案——`ProcessResult` 新增 `stdout_bytes: bytes = b""` 與 `stderr_bytes: bytes = b""` 保留無損原始位元組，並同步維持 UTF-8 `stdout`/`stderr`。
- **確認狀態**：開發者已明確拍板 `1A + 2A(無 --reveal) + 3B(ProcessResult 補 bytes) + 4A` 並授權 `/auto` 推進；`P00` 鎖定為 `Confirmed`。
