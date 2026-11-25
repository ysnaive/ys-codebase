# 成果展示與結案報告 (Walkthrough)

> 功能名稱：Core 2.0 Wave 1.2 止血收斂與下游契約補齊計畫  
> 建立日期：2026-11-25  
> 所屬主計畫：無（獨立 Full Track 計畫）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (XHigh)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  - **10 項 P0 實作瑕疵全面止血 (`FR-01` ~ `FR-04`, `FR-08`)**：統一 `parse_manifest_dict` 相容 `release.type`／`release_type`；修正 POSIX 非 `/**` URI glob 匹配；封堵 `UriMountTable.iter_covering_mounts` 同址多掛載權限穿透並補齊 `config.local://`／`storage.local://` 跨模組讀取隔離；Windows `st_reparse_tag` 精準判別符號連結／接點並放行 OneDrive／WOF；細分 SQLite 忙碌／約束／損毀錯誤與併發 WAL 初始化重試；根治佇列 `COALESCE` Leader 取消、`QUIESCE`↔Step 5 雙波排空 AB-BA 死鎖、Daemon 輪詢 `100ms` 硬上限與 Watcher 預設雜訊目錄剪枝；落地 `.venv` 運行期共享租約與節流 `touch_env_last_used`；補齊 `core_v2/yscb.py` 非人類環境覆寫指令輕量守門（`--allow-bootstrap-mutation`）。
  - **下游模組契約與安全收斂 (`FR-05` ~ `FR-08`)**：建立 `core_v2/source/core/{manifest.json,configurable/config.project.json.tmpl,.yscbignore}` 真實元資料；補齊 `ScopedVfs.open_read() -> BinaryIO` 與 `core.space.ack_cursor`（含跨模組 `consumer` 命名空間所有權校驗）；`core.surface.sdk` 擴充至 **75 符號**並落地 `TaskGroup.parent_module` 以拔除 `CoreSystemModule` TLS 繞道；修正 `CallerMode` `AGENT > CI` 與精準 Session 環境鍵，並將 `worker_pool.py:_infer_env_host_dialect` 與之 1:1 對齊。
  - **Windows 11 實機驗收收斂 (`UX-01`)**：排查並根治 4 項 Win32 產品瑕疵（RFC 8089 Windows `file://` URI 校驗、`CreateProcess` 錯誤附加 `venv_python`、`-B` 下 Daemon 啟動視窗與動態空間通知 RPC 逾時調整）及 5 項跨平台測試競態，後續 2 項效能／工具改善登錄 `plans/roadmap/TODO.md`（`TODO-30`、`TODO-31`）。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `core_v2/source/core/manifest.json`、`configurable/config.project.json.tmpl`、`.yscbignore` | New | 建立 `core` 2.0 真實模組元資料、專案組態模板與打包忽略規則 |
| `core_v2/source/core/core/foundation/primitives.py` | Modify | 修正 POSIX 非 `/**` 語意 URI 萬用字元匹配 |
| `core_v2/source/core/core/filesystem/fs/{__init__,atomic,watcher}.py` | Modify | Windows `is_disallowed_reparse_tag` 精準判別與 `PollingDirectoryWatcher` 預設剪枝 |
| `core_v2/source/core/core/filesystem/vfs/{mount,readonly,scoped,__init__}.py` | Modify | `iter_covering_mounts` 最嚴格權限聚合、`ScopedVfs.open_read()` 與 `config.local://`/`storage.local://` 跨模組讀取隔離 |
| `core_v2/source/core/core/filesystem/storage/database.py` | Modify | SQLite `SQLITE_BUSY`/`IntegrityError`/`STORAGE_CORRUPT` 錯誤細分與併發 WAL 初始化退避重試 |
| `core_v2/source/core/core/metadata/config/{manifest,__init__}.py` | Modify | 統一 `parse_manifest_dict` 相容 `release.type`/`release_type` 並收斂模組掃描解析入口 |
| `core_v2/source/core/core/packaging/env/{__init__,pool,gc}.py`、`installer/provider.py` | Modify | 新增 `touch_env_last_used`／`acquire_env_shared_lease` 與 RFC 8089 Windows `file://` URI 校驗 |
| `core_v2/source/core/core/execution/runtime/{contracts,coordinator,dispatcher,gates,module_slot,worker_pool}.py`、`daemon/service.py` | Modify | 修正 `COALESCE` 佇列取消、`QUIESCE`↔Step 5 排空、Tier 1 共享 env 租約、精準環境方言推導、`venv_python` 錯誤診斷與解除輪詢 `100ms` 上限 |
| `core_v2/source/core/core/surface/sdk/{__init__,declarative,client}.py` | Modify | 擴充 SDK 門面至 75 符號、落地 `TaskGroup.parent_module` 與 `client.py` 統一套用 `st_reparse_tag` |
| `core_v2/source/core/core/surface/cli/caller_mode.py`、`bootstrap/{factory,system_module}.py` | Modify | `CallerMode` `AGENT > CI` 與精準鍵、拔除 `CoreSystemModule` TLS、新增 `core.space.ack_cursor`（含跨模組所有權隔離）與 Windows Daemon/RPC 視窗調整 |
| `core_v2/yscb.py` | Modify | 落地非人類環境覆寫守門（`--allow-bootstrap-mutation`）與 RFC 8089 Windows `file://` URI 校驗 |
| `core_v2/sub_module_design/{foundation,filesystem,metadata,packaging,execution,surface}/*.md` | Modify | 同步全部受影響之 Active Living Specs 與公開簽名契約 |
| `core_v2/tests/{_harness,test_foundation_fs,test_vfs_storage_space,test_metadata_packaging,test_runtime_daemon,test_surface_sdk,test_surface_cli_e2e,test_rc_e2e}.py` | Modify | 補齊 10 項 P0 修復、安全收斂、Pillar 3 加固與 Windows 確定性跨平台回歸測試 |
| `CHANGELOG.md`、`core_v2/ROADMAP.md`、`core_v2/handoff.md`、`plans/roadmap/TODO.md` | Modify | 同步三層結案文檔、最新規模數據與 `TODO-30`/`TODO-31` 技術債登錄 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - **Linux 雙模全 9 套件回歸**：標準模式 `217.00s` PASS、`-O` 模式 `273.97s` PASS（含 `unplug` 10 階段物理拔除，皆 `0 ResourceWarning`）。
  - **Pillar 3 加固後最終覆驗**：`gate0` `9.93s` PASS、`runtime_daemon` 標準 `9.80s` / `-O` `14.35s` PASS、`surface_cli_e2e` 標準 `128.40s` / `-O` `133.21s` PASS（`0 ResourceWarning`）。
  - **唯讀盲審守門**：Pre-UX 唯讀盲審與 Phase 7 Pillar 3 唯讀盲審均通過（`REVIEW_STATUS: PASSED`）；1.x 主線 `ys_codebase/source/*` 維持 0 異動。
- **實機 UX / 人工驗證**：
  - `UX-01`：`[測試通過]` — 開發者於 Windows 11 本機跑通全部 9 大套件（`gate0` `16.48s`、`foundation_fs` `2.42s`、`vfs_storage_space` `41.50s`、`metadata_packaging` `40.88s`、`surface_sdk` `7.09s`、`runtime_daemon` `19.38s`、`surface_cli_e2e` `637.91s`、`rc_e2e` `RC-01~RC-08`、`unplug` 10 階段，`0 ResourceWarning`）並於 2026-11-25 10:54 明確簽核結案。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已更新 | 已記錄 Wave 1.2 止血收斂、下游契約補齊與雙平台驗收摘要 |
| **中觀 (Meso)** | `core_v2/ROADMAP.md`、`core_v2/handoff.md` | 已更新 | 已同步 `core` 規模（92 檔 / `62,130 LOC`、`yscb.py` `3,375 LOC`、`sdk` 75 符號）與雙平台驗證狀態 |
| **中觀 (Meso)** | `core_v2/sub_module_design/**/*.md`（17 份 Active Living Specs） | 已更新 | 已與實碼 1:1 雙向對齊並通過 `Gate 0` AST／Runtime 校驗 |
| **中觀 (Meso)** | `docs/<Category>/*.md` | 免更 | 嚴守 `./core_v2` 潔淨室邊界，不異動 1.x 系統知識庫 |
| **微觀 (Micro)** | 受異動之 `core_v2/source/core/core/**/*.py` | 已更新 | 新增與調整之公開介面與輔助函式均具精準 Docstring，0 工單編號殘留 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack（`Gate 0` AST 自審與 Phase 7 唯讀盲審全數通過）。
- [x] **測試完整覆蓋**：Linux 雙模與 Windows 11 全 9 套件 100% 通過，無跳過或被放寬之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(core_v2): land Wave 1.2 complete kernel, stabilization hardening, and Windows/Linux acceptance

- Land Core 2.0 Wave 1.2 all 6 orthogonal domains (92 files, 62,130 LOC), core_v2/yscb.py (3,375 LOC), 17 Active Living Specs, and 10-stage physical unplug test suite
- Fix all 10 P0 stabilization defects: unified manifest release.type parsing, POSIX URI glob, strict multi-mount VFS & cross-module local read isolation, Windows st_reparse_tag, SQLite error classification & WAL retry, queued COALESCE leader cancel, QUIESCE/Step-5 draining deadlock, watcher default pruning & daemon poll cadence, Tier 1 shared .venv leases, and yscb.py non-human mutation gate
- Complete downstream contracts & security hardening: core/ real metadata, ScopedVfs.open_read(), core.space.ack_cursor with cross-module consumer ownership guard, 75-symbol core.surface.sdk facade with TaskGroup.parent_module (removing CoreSystemModule TLS), CallerMode AGENT>CI exact-key parity with worker_pool.py
- Fix 4 Windows 11 runtime defects and pass all 9 live suites on both Linux (std/-O) and Windows 11 with 0 ResourceWarning
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_25_0706_core_v2_wave12_stabilization` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
