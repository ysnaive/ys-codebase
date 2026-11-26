# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Core 2.0 Wave 1.2 全內核子模組實作、雙盲語境裁決閉環與活規格轉正  
> 建立日期：2026-11-22  
> 所屬主計畫：無（獨立 Full Track 實作計畫）  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 靜態架構與活規格守門 (`gate0`) | 驗證全內核 6 大功能域 `.py`、`core_v2/yscb.py` 與全部分域測試檔 `0 Any`/`0 print`/`0` 非法反射/`0` 工單噪訊註解、嚴格單向匯入白名單、跨套件 `__all__` 邊界、Markdown 圍欄平衡與無圍欄外殘留宣告，以及轉正後全部 17 份 Active Living Specs 1:1 簽名與常數對齊 | FR-01 ~ FR-06, NFR-01, NFR-02, NFR-04 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite gate0` |
| **FT-02** | 基礎底座與物理檔案測試 (`foundation_fs`) | 驗證 `SemVer4`、`VersionConstraint`、`SemanticUri`、`SpaceId`、`SpacePath`、`SnapshotGen`、`EnvHash` 與 `DataclassCodec` 往返、`SchemaExporter` Draft 2020-12、`LogRotator`（含 `\u2028` 與 FD 隔離）、`LocaleCatalog`（顯式鏈與深度 5 防環）、`SessionTelemetryWriter`、`_YSCB_WORKER_AUTH_TOKEN` 環境洗淨及既有 FS/Event/Lifecycle/RPC 回歸 | FR-01, EC-05, NFR-03 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite foundation_fs` |
| **FT-03** | 虛擬檔案、WAL 儲存與空間測試 (`vfs_storage_space`) | 驗證 Scheme B 15 協議能力遮罩、`!undefined`/`URI_CYCLE`、雙層 `ReadonlyPolicy` 穿隧、`VfsEchoGuard`、`ScopedVfs` 跨模組 `@/` 隔離、`MemoryVfsProvider`；`ModuleDatabase` / `BlobVault` 唯獨放行 `storage.local://`、WAL MVCC 並發讀寫零鎖、`BEGIN IMMEDIATE` + `cancel_token` 回滾、單向遷移防降級；`SpaceRegistry` `DN-20` 對稱/剪枝/純差集、動態空間持久化、多消費者游標與 `GitignoreMaterializer` Zero-Touch | FR-02, EC-01, EC-02, EC-05 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite vfs_storage_space` |
| **FT-04** | 組態擴充與離線套件環境測試 (`metadata_packaging`) | 驗證 `manifest.json` 2.0、2x2 `ConfigStore`（解耦 `project://`）、`DeepInfiller`、智能 `SnapshotVault`（去重/60s 折疊/3 份 7 天淘汰/排除 `.storage.local` 與 `.cache`）；`Contributes 2.0` `@dataclass` SSOT 與 `_schema.json` 等價、5 大合併策略、離帶 `ProvenanceGraph`、`contribute.json` 同構；離線 `.whl` 合成 `ImmutableVenvPool`、E3-A GC、`OfflinePackageEngine` Zip 安全、`*.tmpl` 零殘留剝離、遷移回滾守衛跨進程鎖與 `UpdateChecker` | FR-03, FR-04, EC-03, EC-05 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite metadata_packaging` |
| **FT-05** | 擴充 SDK、零匯入 CLI 與自舉端到端測試 (`surface_sdk` + `surface_cli_e2e`) | 驗證 `core.surface.sdk` 61 符號、Wave 1.1 零回歸、`ModuleEnv.open_database` LIFO 關閉、Tier 0/1 服務等價；驗證 `surface.cli` 零匯入業務源碼 `--help` 與 `HelpRenderer`、5 層 `CallerMode`（PTY Agent 防誤判）、4x3 安全矩陣、兩段式單次 `--approve=<tok>` 防重放/`CRITICAL` 硬阻斷、Tier 1 子行程 OS `fd 1` 串流隔離，以及 `core_v2/yscb.py init -> install -> daemon -> @on_migrate -> rollback` 全閉環 | FR-05, EC-03, EC-04, NFR-03 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite surface_sdk,surface_cli_e2e` |
| **FT-06** | 跨領域逐層拔除測試 (`unplug`) | 於隔離沙盒依序執行 10 階段物理刪除（Domain 6 `surface` -> Domain 5 `execution` -> `packaging.installer` -> `packaging` -> `metadata.contributes` -> `metadata` -> `filesystem.space` -> `filesystem.storage` -> `filesystem.vfs` -> `filesystem` 僅剩 `foundation`），每階段透過 `pkgutil.walk_packages` 全子模組匯入與獨立子行程契約探針驗證零反向耦合 | FR-06, EC-06, NFR-01 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite unplug` |
| **FT-07** | 運行守護與多進程全量壓測回歸 (`runtime_daemon` + `rc_e2e` + 全套標準與 `-O`) | 驗證更名 `_YSCB_WORKER_AUTH_TOKEN` 與注入 `ModuleRuntimeServices` 後，全套 9 大測試套件於標準模式與 `-O` 最佳化模式下一次跑通，`0 ResourceWarning`、零殘留孤兒行程 | FR-01 ~ FR-06, EC-01 ~ EC-06, NFR-03 | `python3 -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all` & `python3 -O -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | Pass | `gate0` 100% 通過（標準 `12.46s` / `-O` `12.37s`）：92 支核心 `.py`、`core_v2/yscb.py`、13 支測試與調度檔及全數 17 份 Active Living Specs 雙向簽名與圍欄衛生檢查全綠（`0 ResourceWarning`） | 2026-11-24 |
| **FT-02** | Pass | `foundation_fs` 100% 通過（標準 `0.39s` / `-O` `0.47s`）：Wave 1.2 值物件、`SchemaExporter`、`LogRotator`、`LocaleCatalog`、`SessionTelemetryWriter` 與物理 FS/鎖/監聽回歸全綠 | 2026-11-24 |
| **FT-03** | Pass | `vfs_storage_space` 100% 通過（標準 `1.01s` / `-O` `1.01s`）：15 協議矩陣、雙層唯讀穿隧、`storage.local://` SQLite WAL MVCC、`BlobVault`、三源兩趟空間與 `.gitignore` Zero-Touch 全綠 | 2026-11-24 |
| **FT-04** | Pass | `metadata_packaging` 100% 通過（標準 `16.54s` / `-O` `22.33s`）：`manifest.json` 2.0、2×2 `ConfigStore`、`SnapshotVault`、`Contributes 2.0`、離線 `.venv` 池、`OfflinePackageEngine` 與遷移回滾鎖全綠 | 2026-11-24 |
| **FT-05** | Pass | `surface_sdk`（標準 `1.01s` / `-O` `1.36s`）+ `surface_cli_e2e`（標準 `126.56s` / `-O` `130.41s`）100% 通過：61 符號門面、零匯入 CLI、兩段式 `--approve`、Tier 1 `fd 1` 隔離與 `yscb.py` 全生命週期 E2E 全綠 | 2026-11-24 |
| **FT-06** | Pass | `unplug` 100% 通過（標準 `2.40s` / `-O` `4.22s`）：Domain 6 -> 1 共 10 階段同域與跨域物理 `rmtree` + `pkgutil.walk_packages` 掃描 + 子行程探針零反向耦合 | 2026-11-24 |
| **FT-07** | Pass | 全量 `--suite all` 9 大套件一次跑通：標準模式 `209.16s`（`runtime_daemon` `6.12s`、`rc_e2e` `42.49s`）、`-O` 模式 `232.87s`（`runtime_daemon` `8.42s`、`rc_e2e` `52.11s`），`0 ResourceWarning`、零孤兒行程 | 2026-11-24 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 拉取同步後於本機執行 `python -B -W error::ResourceWarning core_v2/verify_execution_live.py` 驗證全內核 6 大功能域、分域套件與 `RC-01 ~ RC-08` 全綠通過 | `[跳過/免測]` | 依開發者授權雲端全閉環後本地統一驗收（預設免阻斷結案，留待本地實機跑測） |
| **UX-02** | 檢視 `core_v2/yscb.py --help`、`HelpRenderer` 排版、兩段式 `--approve=<token>` 提示與轉正後之 Active Living Specs | `[跳過/免測]` | 依開發者授權雲端全閉環後本地統一驗收 |
