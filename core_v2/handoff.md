# Core 2.0 跨對話與遠端異步開發交接快照 (`core_v2/handoff.md`)

> **最後更新**：`2026-11-26`
> **當前狀態**：**Wave 1.1 + Wave 1.2 全內核 6 大功能域 + 止血收斂 + 原生可觀測性/效能剖析 + 下游 SDK 雙層門面（53+38）與人體工學重構 + 下游基建高優先回補（遷移回滾、熱 Worker 呈現、Secret 憑證防護、子行程 stdin/bytes/工具鏈環境與空間反解）+ `core_v2/yscb.py` + 18 份正式活規格已 100% 實作完封並通過雙平台驗收（`Completed`），就緒推進 Wave 1.3 (`dev 2.0`) / Wave 2**
> **關聯總路線圖**：[ROADMAP.md](./ROADMAP.md)
> **關聯結案計畫**：[2026_11_26_0540_core_v2_greenfield_infra_hardening](../plans/archived/2026/11/2026_11_26_0540_core_v2_greenfield_infra_hardening/P07_walkthrough.md)（承接 [2026_11_25_1630_core_v2_sdk_ergonomics_overhaul](../plans/archived/2026/11/2026_11_25_1630_core_v2_sdk_ergonomics_overhaul/P07_walkthrough.md)）
> **封存完整版基線 Tag**：`archive/core-v2-maximalist`（`9847b1a`）

---

## 1. 目前已完成基線（Wave 1.1 + Wave 1.2 微內核、可觀測性、雙層 SDK 與下游基建加固）

* **內核與啟動器規模**：
  - `core_v2/source/core/core/` 共 **94 支 `.py`、`67,932 LOC`**（100% Python 3.11+ 標準庫、零第三方依賴、零 `Any`、零 `# type: ignore`），另含 `core_v2/source/core/{manifest.json,configurable/config.project.json.tmpl,.yscbignore}` 真實元資料：
    - **Domain 1 `foundation/`**（7 檔，`7,777 LOC`）：`primitives`（值物件、`PUBLIC_ENV_ALLOWLIST` + `TOOLCHAIN_ENV_ALLOWLIST`/`extract_toolchain_env`、`safe_realpath`）、`errors`（33 碼）、`codec`（`DataclassCodec`、`SECRET_FIELD_METADATA_KEY`/`secret_field` + `SchemaExporter` `writeOnly`/`x-yscb-secret`）、`observability`（`StructuredLogger`、側車鎖 `LogRotator`、`LocaleCatalog`）、`profiler`（ImTK 風格剖析器、3+1 日誌、共用 `is_sensitive_key` 與涵蓋 `config set --local` 之 `redact_cli_args`）、`proc`（Job Object / Session+PGID、`ManagedProcessTree(capture_output, pipe_stdin, bufsize=0)` + `stdin_pipe`、`build_isolated_python_env(..., include_toolchain_env=...)`、`read_flight_log_env`）。
    - **Domain 2 `filesystem/`**（21 檔，`11,329 LOC`）：`fs`（`safe_realpath` + Windows `st_reparse_tag` + Watcher 剪枝）、`vfs`（15 協議、雙層 `ReadonlyPolicy`、`VfsEchoGuard`、`ScopedVfs.{open_read,glob,resolve_caller_uri}`）、`storage`（SQLite WAL MVCC + 選配 `profiler` + `BlobVault`）、`space`（SQLite WAL `state.db` `SpaceRegistry`、`SpaceScanner` 選配 `profiler`、`GitignoreMaterializer`）。
    - **Domain 3 `metadata/`**（14 檔，`8,122 LOC`）：`config`（`ModuleManifest` 2.0、2×2 `ConfigStore` 含 `.config.local` `0o600`/`0o700` 與 Windows DACL + 遞迴 Secret/Local 脫敏 `get_module_redacted_dict`、`DeepInfiller`、嚴格排除 `.config.local`/`.storage.local`/`.cache` 之 `SnapshotVault`）、`contributes`（`@dataclass` SSOT、`_schema.json`、5 大合併策略、`ProvenanceGraph`、`ContributesAggregator`）。
    - **Domain 4 `packaging/`**（14 檔，`9,278 LOC`）：`env`（不可變雜湊 `.venv` 池、共享租約與節流 GC）、`installer`（純離線 `OfflinePackageEngine`、`MigrationRollbackHandle` 按需 `.storage.local/<mod>/` 交易快照還原與 `0o700`/`0o600` 權限保留、三級 `PurgeLevel`、`UpdateChecker`）。
    - **Domain 5 `execution/`**（22 檔，`18,042 LOC`）：`event`、`lifecycle`（`StepExecutionResult` 攜帶 `rendered_text`/`exit_code`）、`rpc`、`runtime`（5 段管線、下沉 `HumanRenderable`/`ExitCodeProvider`/`format_output` 與 `EncodedStepOutput`、熱 Worker 呈現管線、`skip_module_init` 冷遷移隔離守門、`ProcessResult(+stdout_bytes, stderr_bytes)`、`TaskContext.run_process(+input, inherit_toolchain_env)`、`SpaceClient(+resolve_uri, match_spaces)`、6 組強型別系統 `EventMetadata`、`ProtectedModuleLoader` 自動載入）、`daemon`（Stream 1 日誌、`profiler_summary`、20ms 雙條件 Racy-Clean `core_sig_cache`）。
    - **Domain 6 `surface/`**（15 檔，`13,381 LOC`）：雙層零反射 SDK 門面——主入口 `core.surface.sdk`（精確 **53 符號**，含 `secret_field`）與進階子套件 `core.surface.sdk.advanced`（精確 **38 符號**，零交集）；`cli`（直接消費熱 Worker `rendered_text`/`exit_code`、`--json` 純淨無呈現鍵、禁止 `custom_exit_code` 靜默回落 `0`）；`bootstrap`（移除冷 Tier 1 呈現子行程、新增 `scoped_vfs_for_module`、`@on_migrate` 跳過 `on_init()` 與 `.storage.local` 交易回滾、`core.config.{list,get,inspect,set}` 全面脫敏且無 `--reveal`、6 支無鎖併發讀 `SDK_ONLY` `core.space.{list,status,files,diff,resolve_uri,match_spaces}`）。
  - `core_v2/yscb.py`（**`3,386 LOC`**）：100% 純標準庫單檔超薄自舉啟動器。
* **18 份正式活規格（Active Living Specs）**：
  - 全數 18 份活規格（本次同步 8 份）與實碼維持 1:1 雙向對齊並通過 `Gate 0` 雙向校驗與跨包邊界檢查；僅 [dev/dev.md](./sub_module_design/dev/dev.md) 維持 `Draft — Prototype Design`。
* **雙平台驗證體系與盲審收斂**：
  - [verify_execution_live.py](./verify_execution_live.py) + `core_v2/tests/`（共 12 檔、`28,309 LOC`），涵蓋全部 9 大套件。
  - **Linux 雙模全綠**：全 9 套件標準（`265.42s`）與 `-O`（`289.40s`）全通過，終版微調後覆驗 `gate0`+`metadata_packaging`+`unplug`+`surface_cli_e2e`（`-B` `189.29s` / `-O -B` `206.30s`）全綠（`0 ResourceWarning`）；3 輪零錨定盲眼靜態審查收斂至 `REVIEW_STATUS: PASSED (0 BLOCKER)` 且所有 ADVISORY 清零。
  - **Windows 11 實機驗收（`UX-01` `[測試通過]` / `UX-02` `[跳過/免測]`）**：Windows 11 `-O` 全數受異動 8 大套件（`gate0` `13.11s`、`foundation_fs` `2.81s`、`vfs_storage_space` `40.59s`、`metadata_packaging` `47.17s`、`surface_sdk` `8.19s`、`surface_cli_e2e` `524.73s`、`unplug` `8.36s`、`runtime_daemon` `42.05s`）與 `RC-01`~`04` 100% 通過（`0 ResourceWarning`）；未觸及之 `rc_e2e` `RC-05` `put_pre_to`（`1000ms` 夾具預算抖動）經開發者裁示免測跳過。
  - 潔淨室隔離護欄：`ys_codebase/source/*`（1.x 主線）與 `.vscode/settings.json` 全程零異動。

---

## 2. 本機拉取驗收指令（Local Acceptance Commands）

1. 拉取雲端同步倉變更：
   ```bash
   python yscb.py gdrive pull
   ```
2. 執行全內核 9 大套件實機驗證（標準模式與 `-O` 模式）：
   ```bash
   python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all
   python -O -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all
   ```

---

## 3. 下次對話建議入口（Pick Next）

1. **推進 Wave 1.3：`dev 2.0` 工具鏈設計定案與實作（主線首選）**：以 [dev/dev.md](./sub_module_design/dev/dev.md) §4 開放議題為起點，拍板 `dev build`、`dev check 2.0` 與跨平台模組測試沙盒（含本地單元測試工作台 `TestBench`、`TODO-36` CLI 分支測試、`TODO-37` 自動生成 manifest），落地 `core_v2/source/dev/`。
2. **推進 Wave 2：Tier 0 輕模組移植（`vscode-support` / `agents-workflow` / `gdrive-support`）**：基於已鎖定的 **53+38 雙層 SDK 門面**（`secret_field`、`@on_migrate` 交易回滾、熱 Worker 呈現、`ctx.run_process(+stdin/bytes/toolchain)`、`ctx.spaces.{resolve_uri,match_spaces}`），將三大 Tier 0 模組純 `Task` 化遷移至 `core_v2/source/`。
3. **排程跟進技術債與歸檔（選配）**：視需要推進 `TODO-32`（`yscb diag`）、`TODO-33`（Daemon 活體現場檢視）、`TODO-34`（CLI 熱轉發瘦身）、`TODO-35`（`core.http` 協同設計）或封存已結案歷史計畫。
