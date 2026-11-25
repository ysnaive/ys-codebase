# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Core 2.0 Wave 1.2 止血收斂與下游契約補齊計畫  
> 建立日期：2026-11-25  
> 所屬主計畫：無（獨立 Full Track 計畫）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (XHigh)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元 / 整合測試 | 統一 `parse_manifest_dict` 支援 `"release": {"type": ...}` / `"release_type"` 並拒絕同時出現與非法鍵；`discover_installed_manifests_map` 正常辨識帶 `release.type` 已裝模組；`core_v2/source/core/{manifest.json,configurable/config.project.json.tmpl,.yscbignore}` 通過結構校驗。 | FR-01, FR-06, EC-01 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite metadata_packaging` |
| **FT-02** | 單元 / 安全測試 | Windows `is_disallowed_reparse_tag` 精準攔截 `0xA000000C`/`0xA0000003` 並放行 OneDrive/WOF；`PollingDirectoryWatcher` 預設剪枝 `.git`/`node_modules`/`.venv`/`.cache`/`build`/`dist`/`target`（不誤殺祖先路徑）；POSIX `project://plans/*.md` 等非 `/**` URI 萬用字元正確匹配。 | FR-02, FR-03, EC-03, NFR-04 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite foundation_fs` 與 `--suite vfs_storage_space` |
| **FT-03** | 安全 / 儲存測試 | `UriMountTable.iter_covering_mounts` 封堵同址 `project://yscb.py` 覆寫與唯讀別名穿透；`ScopedVfs.open_read()` 物理/記憶體串流與負向錯誤；`config.local://`/`storage.local://` 跨模組讀取隔離且保留 `storage.local://` 根目錄供 `ModuleDatabase` 驗界；SQLite `SQLITE_BUSY -> TASK_TIMEOUT`、`IntegrityError -> BUSINESS_FAILURE`（遷移轉 `SCHEMA_MIGRATION_ERROR`）、真實損毀 -> `STORAGE_CORRUPT` 及併發 WAL 切換重試。 | FR-02, FR-05, FR-07, EC-02, EC-04 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite vfs_storage_space` |
| **FT-04** | 並發 / 生命週期測試 | 佇列中 `COALESCE` Leader 取消／短逾時後存活 Follower 正常完成；Step 5 雙波事件期間發起全域 `QUIESCE` 零死鎖順利排空且取消優先於逾時；`DaemonWatcherConfig` 輪詢頻率解除 100ms 硬上限；`HotWorkerPool`/`OneShotVenvHost` 完整成對取得與釋放 `env_lease_acquire`／`env_touch_used` DI 回呼。 | FR-03, FR-04, EC-05, EC-06 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite runtime_daemon` 與 `--suite rc_e2e` |
| **FT-05** | 隔離 / 回收測試 | `touch_env_last_used` 節流刷新恢復 7 天寬限期；持有 `acquire_env_shared_lease` / `acquire_env_lease_for_python` 或 `WorkspaceKernel` 活體 Tier 1 環境期間 `EnvGarbageCollector.collect()` 必將其列為 `skipped_locked_dirs` 零誤刪，關閉後正常回收。 | FR-04, EC-06 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite metadata_packaging` 與 `--suite surface_cli_e2e` |
| **FT-06** | SDK / CLI / 端對端安全測試 | `core.surface.sdk` 75 符號門面、`TaskGroup.parent_module` 共享狀態與無參相容、`CoreSystemModule` 零 TLS 正常運行、`core.space.ack_cursor` 端對端 CAS 成功與過期拒絕；`CallerMode`（`AGENT > CI`、`YSCB_CALLER_MODE=ci` 保留、禁 PTY 下 Agent 降級 `human`、精準 Session 鍵不誤傷人類組態鍵）；`yscb.py` 4 種非人類環境 × 5 條覆寫指令攔截 `exit 4`/`security_gated`，空工作區全新 `init` 與無參冪等 `init` 放行。 | FR-05, FR-07, FR-08, EC-07, EC-08 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite surface_sdk` 與 `--suite surface_cli_e2e` |
| **RT-01** | 架構守門與雙模全量回歸 | `Gate 0`（6 域 DAG、17 份活規格 1:1 雙向對齊、0 `Any`/`print`/`getattr`/`assert`、測試自審）、10 階段物理拔除（`unplug`）及全部 9 大套件於標準模式與 `-O` 最佳化模式在本容器 `CI=true` + `ANTIGRAVITY_AGENT=1` 原環境全量驗證，加上 Pre-UX 唯讀盲審複核通過與 1.x 潔淨室零異動。 | NFR-01, NFR-02, NFR-03 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all` 與 `python3 -O -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `metadata_packaging` 全通過（標準 12.65s / `-O` 19.65s，`0 ResourceWarning`），驗證 `parse_manifest_dict`、`release.type`、`core` 真實元資料與 `.venv` 共享租約。 | 2026-11-25 08:40 |
| **FT-02** | `Passed` | `foundation_fs`（標準 0.66s / `-O` 0.76s）與 `vfs_storage_space`（標準 2.76s / `-O` 2.72s）全通過，`0 ResourceWarning`。 | 2026-11-25 08:40 |
| **FT-03** | `Passed` | `vfs_storage_space` 覆蓋掛載最嚴格權限、`ScopedVfs.open_read()`、`config.local://`/`storage.local://` 跨模組讀取隔離與 SQLite 錯誤細分全通過；併發 4 進程 WAL 切換重試於 `surface_cli_e2e` 併發自癒測項全綠。 | 2026-11-25 08:40 |
| **FT-04** | `Passed` | `runtime_daemon`（標準 11.04s / `-O` 14.64s）與 `rc_e2e` `RC-01~RC-08`（標準 59.53s / `-O` 69.54s）全通過，`0 ResourceWarning`。 | 2026-11-25 08:40 |
| **FT-05** | `Passed` | `metadata_packaging` 與 `surface_cli_e2e` 活體 `.venv` 租約保護與關閉後 GC 回收均 100% 通過，`0 ResourceWarning`。 | 2026-11-25 08:49 |
| **FT-06** | `Passed` | 歷經 Pre-UX 盲審、Windows 11 實測收斂與 Phase 7 Pillar 3 盲審補齊 `fs_ack_cursor` 跨模組所有權與 `worker_pool.py` 精準環境鍵後最終覆驗：`surface_cli_e2e` 標準（`128.40s`）與 `-O`（`133.21s`）、`runtime_daemon` 標準（`9.80s`）與 `-O`（`14.35s`）於 `CI=true` 環境全通過，`0 ResourceWarning`。 | 2026-11-25 11:19 |
| **RT-01** | `Passed` | Windows 修正收斂後 Linux 雙模全 9 套件全綠（標準 `217.00s` / `-O` `273.97s`，`unplug` 10 階段通過，`0 ResourceWarning`）；Pillar 3 盲審兩項加固後覆驗 `gate0`（`9.93s`）、`runtime_daemon`（std `9.80s` / `-O` `14.35s`）、`surface_cli_e2e`（std `128.40s` / `-O` `133.21s`）100% 通過；Phase 7 唯讀盲審複核回傳 `REVIEW_STATUS: PASSED`；`ys_codebase/source/*` 零異動。 | 2026-11-25 11:19 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 開發者於本機 Windows 11 主機拉取同步後，執行 `python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all` 驗證所有 Win32 代碼路徑與 9 大套件零回歸。 | `[測試通過]` | 開發者於 Windows 11 實機逐套件跑通全部 9 大套件（`gate0` `16.48s`、`foundation_fs` `2.42s`、`vfs_storage_space` `41.50s`、`metadata_packaging` `40.88s`、`surface_sdk` `7.09s`、`runtime_daemon` `19.38s`、`surface_cli_e2e` `637.91s`、`rc_e2e` `RC-01~RC-08`、`unplug` 10 階段，皆 `0 ResourceWarning`）；實測期間定位並根治 4 項 Windows 產品缺陷與 5 項測試跨平台競態，開發者已於 2026-11-25 10:54 明確簽核通過並核准結案。 |
