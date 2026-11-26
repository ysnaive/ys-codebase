# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Core 2.0 下游基建高優先回補（遷移回滾、熱 Worker 呈現、憑證防護、子行程 I/O 與空間反解）  
> 建立日期：2026-11-26  
> 所屬主計畫：無（獨立 Full Track 計畫）  
> 狀態：Passed  
> 模型：Gemini 4 Neon (XHigh)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 靜態守門與活規格 | 6 域單向 DAG、8 份受異動 Active Living Specs 1:1 雙向對齊、零 `Any`/`# type: ignore`/`print`/`getattr`、無未授權 `os.environ` 與黑盒測試審計 | NFR-01, NFR-02 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite gate0` |
| **FT-02** | 單元與契約測試 | `TOOLCHAIN_ENV_ALLOWLIST`、`extract_toolchain_env`、`build_isolated_python_env(include_toolchain_env=...)`、`is_sensitive_key`、`redact_cli_args`（含 `config set --local` 與 `=` 密文）、`ManagedProcessTree(pipe_stdin=True)` | FR-03, FR-04, EC-03, EC-04 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite foundation_fs` |
| **FT-03** | 單元與 SDK 門面 | `core.surface.sdk` 精確 53 符號（含 `secret_field`）與 `sdk.advanced` 38 符號、`HumanRenderable`/`ExitCodeProvider`/`format_output` 單一真理對齊、`secret_field` 預設 `repr=False` / `SchemaExporter` `writeOnly` + `x-yscb-secret` / 互斥與 metadata 合併校驗 | FR-02, FR-03, EC-06, NFR-02 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite surface_sdk` |
| **FT-04** | 整合與安全測試 | `ConfigStore` `0o600`/`0o700` 寫刪權限、`get_module_local_dict` / `get_module_redacted_dict`（涵蓋 `config.local`、同型別兄弟巢狀、`list`/`Mapping`、`Annotated`/`Optional` 與磁碟 `config.schema.json`）、`SnapshotVault` 嚴格排除 `.config.local/`、`MigrationRollbackHandle` 按需快照還原 `.storage.local/<mod>/`（含 `-wal`/`-shm`、原不存在目錄刪除與 `.config.local` 權限保留） | FR-01, FR-03, EC-01, EC-03 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite metadata_packaging` |
| **FT-05** | 執行期與並發測試 | `skip_module_init=True` 嚴格授權守門（拒絕非內部／非遷移／熱容器 `is_daemon_host=True` 含 `FORCE_COLD`／巢狀呼叫）與冷遷移跳過 `on_init()`；`ctx.run_process` 256 KiB `str`/`bytes` stdin、`BrokenPipeError` 提早退出、非 UTF-8 `stdout_bytes`/`stderr_bytes`、`inherit_toolchain_env=True/False`（含 `caller_env` 代理/CA 濾除）與非法參數校驗 | FR-01, FR-04, EC-01, EC-04 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite runtime_daemon` |
| **FT-06** | 端到端與雙模回歸 | `@on_migrate` 升級失敗跳過新版 `on_init()` 並原子還原 `.storage.local/dbmig/state.db` 使 v1 無 `SCHEMA_MIGRATION_ERROR` 重啟；溫熱 Tier 1 Daemon 單 Worker PID（`import_count==1`）內計算 `HumanRenderable`/`ExitCodeProvider`（含 `Optional[WarmOut]` 回傳 `None`、失敗顯式報錯非退出碼 0 與 `--json` 零呈現鍵洩漏）；`core.config.{list,get,inspect,set}` 全面脫敏（無 `--reveal`）且 `ctx.load_config` 取回原值；Tier 0/1 `ctx.spaces.{resolve_uri,match_spaces}` 與 `EC-05` 讀隔離；10 階段物理拔除與 RC-01~08 全量雙模驗證 | FR-01, FR-02, FR-03, FR-04, FR-05, EC-01, EC-02, EC-03, EC-04, EC-05, EC-06, NFR-01, NFR-02, NFR-03 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all` 與 `python3 -O -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Pass` | Linux `-B` (`10.74s`) 與 `-O -B` (`10.36s`) 雙模通過，8 份活規格 1:1 對齊，`0 ResourceWarning` | 2026-11-26 |
| **FT-02** | `Pass` | Linux `-B` (`0.88s`) 與 `-O -B` (`0.90s`) 全綠，`0 ResourceWarning` | 2026-11-26 |
| **FT-03** | `Pass` | Linux `-B` (`1.80s`) 與 `-O -B` (`2.17s`) 全綠，53+38 SDK 契約驗證通過，`0 ResourceWarning` | 2026-11-26 |
| **FT-04** | `Pass` | Linux `-B` (`12.10s`) 與 `-O -B` (`17.32s`) 全綠，`0 ResourceWarning` | 2026-11-26 |
| **FT-05** | `Pass` | Linux `-B` (`14.36s`) 與 `-O -B` (`18.23s`) 全綠，`0 ResourceWarning` | 2026-11-26 |
| **FT-06** | `Pass` | Linux 全 9 套件雙模全綠（`-B`: `265.42s`；`-O -B`: `289.40s`；最終微調複測 `gate0`+`metadata_packaging`+`unplug`+`surface_cli_e2e`：`-B` `189.29s` / `-O -B` `206.30s`），3 輪盲眼靜態審查收斂至 `REVIEW_STATUS: PASSED (0 BLOCKER)`，全數 `0 ResourceWarning` | 2026-11-26 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於 Windows 11 實機執行 `python -O -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all`，驗證本次變更範疇（Win32 owner-only DACL `.config.local` 寫入與還原、Win32 `ManagedProcessTree(pipe_stdin=True)`、`@on_migrate` SQLite WAL 回滾無殘留鎖、溫熱 Tier 1 呈現、空間反解與 `0 ResourceWarning`） | `[測試通過]` | 開發者於 Windows 11 `-O -B -W error::ResourceWarning` 實機通過全數受異動 8 大套件：`gate0` (`13.11s`)、`foundation_fs` (`2.81s`)、`vfs_storage_space` (`40.59s`)、`metadata_packaging` (`47.17s`)、`surface_sdk` (`8.19s`)、`surface_cli_e2e` (`524.73s`)、`unplug` (`8.36s`)、`runtime_daemon` (`42.05s`) 與 `RC-01`~`RC-04`（全數 `0 ResourceWarning`） |
| **UX-02** | 未異動範疇 `rc_e2e` `RC-05`（`test_rc_e2e.py:731` `put_pre_to` 於 `_harness.py:1728,2270` `timeout_ms=1000` 夾具預算下於 Windows 11 冷重啟 `.venv` 觸發超時抖動）補測 | `[跳過/免測]` | 確認零回歸且屬本計畫未觸及檔案（Linux `-B`/`-O -B` 全綠），開發者裁示「屬於未碰到的範圍，先免測跳過」 |
