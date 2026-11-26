# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Core 2.0 下游模組 SDK 門面雙層收斂與開發人體工學重構  
> 建立日期：2026-11-25  
> 所屬主計畫：無（獨立 Full Track 計畫，為 Wave 1.3 `dev 2.0` 與 Wave 2 下游模組移植之前置門面鎖定）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (XHigh)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 靜態架構守門 | 驗證 `core.surface.sdk` 52 符號與 `core.surface.sdk.advanced` 38 符號零交集、6 份活規格 1:1 雙向對齊、跨包匯出邊界、`EventMetadata` 不可變全域、零 `Any` / `# type: ignore` / `print` / `getattr` | FR-01, FR-02, NFR-01, NFR-02 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite gate0`（標準與 `-O` 雙模） |
| **FT-02** | 單元測試 | 驗證 `ManagedProcessTree(capture_output=True, bufsize=0)` 雙管道捕捉、`close_pipes()` 確定關閉與零 FD 洩漏、`CallCycleError` 提示與環境隔離基底 | FR-03, FR-04, EC-02, NFR-03 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite foundation_fs`（標準與 `-O` 雙模） |
| **FT-03** | 單元測試 | 驗證 `ScopedVfs.glob`（單星不跨目錄、`[!...]` 排除 `/`、字元類跳脫、非法 pattern 拋 `ValueError`、異模組 `storage.local` 隔離）與 `ScopedVfs.resolve_caller_uri`（raw symlink 拋 `SECURITY_GATED`、最深掛載防 `.yscb/` 降級外洩、越界拋 `ACCESS_DENIED`、空/半限定路徑拋 `ValueError`） | FR-03, EC-01, EC-06 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite vfs_storage_space`（標準與 `-O` 雙模） |
| **FT-04** | 單元測試 | 驗證元資料解析、契約雜湊與 Manifest 封裝回歸不受 SDK 雙層拆包與 Domain 5 下沉影響 | FR-01, NFR-01 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite metadata_packaging`（標準與 `-O` 雙模） |
| **FT-05** | 單元 / 整合測試 | 驗證 52+38 雙層門面匯出與退休符號清理、`TaskRef` 契約與巢狀 `Any` 防呆、`TaskContext.call` / `YscbClient.call` 重載與型別錯誤碼、協變 `TaskGroup[TModule_co]` / `.module`、`@task(equivalence_fn=...)` 熱派發 `COALESCE`、`@on_event` 錯誤指引與 `ctx.spaces.*` 全 8 支 API | FR-01, FR-02, FR-04, FR-05, EC-03, EC-05, EC-06 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite surface_sdk`（標準與 `-O` 雙模） |
| **FT-06** | 單元 / 整合測試 | 驗證 `ProtectedModuleLoader.load_module_artifact` 唯一具象子類自動探索（優先 `create_module()`、排除 `ABC`/`Protocol`/外部匯入、0 或多子類拋 `MODULE_DEGRADED`）、`ctx.module_id`、`_StepTaskContext.call`、`ctx.run_process` 逾時/取消（保留 `TASK_PREEMPTED`）/截斷/孫行程清理/環境去重/越界 `cwd` | FR-03, FR-04, FR-05, EC-02, EC-04 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite runtime_daemon`（標準與 `-O` 雙模） |
| **FT-07** | 端對端測試 | 驗證 Tier 0 (`sp_t0`) 與 Tier 1 `.venv` (`sp_t1`) 零樣板模組跨進程 `ctx.spaces.*` 全 8 操作、強型別 `SPACE_UPDATED_EVENT` 觸發、`ctx.resolve_uri` / `ctx.run_process` 實機整合與 CLI `yscb fs ack-cursor` 相容性 | FR-01, FR-02, FR-03, FR-04, FR-05, EC-01, EC-02, EC-03, NFR-03 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite surface_cli_e2e`（標準與 `-O` 雙模） |
| **FT-08** | 物理拔除守門 | 驗證 6 域 DAG 零反向匯入（`execution` 嚴禁匯入 `surface`）與 10 階段物理拔除獨立啟動 | NFR-01 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite unplug`（標準與 `-O` 雙模） |
| **FT-09** | 系統回歸測試 | 驗證 RC 全生命週期、守護行程熱重載、併發取消與異常恢復於雙層門面重構後 100% 通過 | NFR-01, NFR-03 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite rc_e2e`（標準與 `-O` 雙模） |

---

## 2. 測試執行紀錄表 (Test Execution Log)

> 補充品質守門：Pre-Code Analyze Gate (`ANALYZE_GATE: PASSED`) 與支柱三 Pre-UX 盲眼靜態審查 (`REVIEW_STATUS: PASSED`，0 Blockers) 均已通過；以下 9 套件係於所有審查修復完成並清除 `__pycache__` 後，在 Linux 環境連續執行標準模式（總計 `248.35s`）與 `-O` 優化模式（總計 `278.37s`）全量實測結果（`0 ResourceWarning`）；於 Windows 11 UX-01 實機補強 `core_sig_cache` 雙條件 Racy-Clean 後，並覆驗 Linux 雙模 `gate0`（`11.24s`/`10.94s`）、`runtime_daemon`（`14.69s`/`18.70s`）、`unplug`（`2.62s`/`4.36s`）與 `rc_e2e`（`59.98s`/`69.89s`）100% 全綠（`0 ResourceWarning`）。

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `gate0` 雙模全綠：標準 `10.61s` / `-O` `10.88s`（`sdk` 52 符號 + `sdk.advanced` 38 符號、6 份活規格 1:1 通過、`0 ResourceWarning`） | 2026-11-25 |
| **FT-02** | `Passed` | `foundation_fs` 雙模全綠：標準 `0.88s` / `-O` `0.90s`（`ManagedProcessTree(capture_output=True, bufsize=0)` 零死鎖與零 FD 洩漏） | 2026-11-25 |
| **FT-03** | `Passed` | `vfs_storage_space` 雙模全綠：標準 `3.53s` / `-O` `3.28s`（`glob` 與 `resolve_caller_uri` 全安全邊界驗證通過） | 2026-11-25 |
| **FT-04** | `Passed` | `metadata_packaging` 雙模全綠：標準 `11.89s` / `-O` `17.90s` | 2026-11-25 |
| **FT-05** | `Passed` | `surface_sdk` 雙模全綠：標準 `1.84s` / `-O` `2.29s`（52+38 分流、`TaskRef`/`call`、`TaskGroup[T]`、`equivalence_fn` 與 `SpaceClient` 全綠） | 2026-11-25 |
| **FT-06** | `Passed` | `runtime_daemon` 雙模全綠：標準 `14.45s` / `-O` `19.05s`（模組自動探索、`ctx.run_process` 取消/逾時/截斷與進程樹回收全綠） | 2026-11-25 |
| **FT-07** | `Passed` | `surface_cli_e2e` 雙模全綠：標準 `143.99s` / `-O` `150.11s`（含 Tier 0 `sp_t0` + Tier 1 `.venv` `sp_t1` `ctx.spaces.*` 跨進程與 `-O` 競態修復） | 2026-11-25 |
| **FT-08** | `Passed` | `unplug` 雙模全綠：標準 `2.50s` / `-O` `4.64s`（6 域 DAG 10 階段物理拔除零違規） | 2026-11-25 |
| **FT-09** | `Passed` | `rc_e2e` 雙模全綠：標準 `58.49s` / `-O` `69.12s`（全生命週期回歸通過、`0 ResourceWarning`） | 2026-11-25 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於 **Windows 11** 實機執行標準與 `-O` 雙模全量測試：`python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all` 與 `python -O -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all`。預期全 9 套件 100% 通過且 `0 ResourceWarning`，涵蓋 Win32 Job Object + `ManagedProcessTree(capture_output=True, bufsize=0)` 進程樹終止、`ctx.run_process` 大小寫不敏感環境變數與 `CREATE_NO_WINDOW`、`ScopedVfs.resolve_caller_uri` Windows 磁碟機/反斜線/半限定路徑防禦，以及 Tier 0/1 `ctx.spaces.*` 跨進程 E2E。 | `[測試通過]` | 2026-11-26 Windows 11 `-O` 實機全 9 套件全綠且 `0 ResourceWarning`（`gate0` `22.55s`、`foundation_fs` `3.83s`、`vfs_storage_space` `103.80s`、`metadata_packaging` `64.53s`、`surface_sdk` `8.53s`、`surface_cli_e2e` `718.12s`、`unplug` `8.16s`；補強 `core_sig_cache` 雙條件 Racy-Clean 後補測 `runtime_daemon` `39.92s`、`rc_e2e` `137.41s`）；開發者顯式確認簽核 `[測試通過]`（免另跑 Windows 標準模式） |
