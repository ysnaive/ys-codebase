# 成果展示與結案報告 (Walkthrough)

> 功能名稱：Core 2.0 下游基建高優先回補（遷移回滾、熱 Worker 呈現、憑證防護、子行程 I/O 與空間反解）  
> 建立日期：2026-11-26  
> 所屬主計畫：無（獨立 Full Track 計畫）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (XHigh)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：於 Wave 1.3 (`dev 2.0`) 與 Wave 2 模組移植前，一次補齊盲眼下游開發體驗審計檢出之 5 項高優先內核基建缺漏（`FR-01` ~ `FR-05`、`EC-01` ~ `EC-06`、`NFR-01` ~ `NFR-03`），全程維持 100% Python 3.11+ 標準庫、零 `Any`、零 `# type: ignore` 與 6 域嚴格單向 DAG（`core_v2/source/core/core/` 現為 94 檔 / `67,932 LOC`）：
  1. **`FR-01` (`1A`) `@on_migrate` 跳過新版 `on_init()` 與 `.storage.local/<mod>/` 交易回滾**：實作受嚴格授權守門（拒絕非內部／非遷移／熱容器 `is_daemon_host=True` 含 `FORCE_COLD`／巢狀呼叫）之 `skip_module_init=True` 冷遷移隔離路徑，並於 `OfflinePackageEngine.migration_rollback_scope()` 落地向下相容之 `MigrationRollbackHandle`（`snapshot_module_storage_local` + `restore`，含 `-wal`/`-shm`、刪除新建目錄、`0o700` `.temp/` 與 `.config.local` `0o600` / Win32 owner-only DACL 還原保留）。
  2. **`FR-02` (`P1-1`) Tier 0/1 熱 Worker 內呈現與防 CI 假綠**：將 `HumanRenderable`/`ExitCodeProvider`/`format_output` 單一真理下沉至 Domain 5 `execution.runtime.contracts`（由 `sdk`/`sdk.advanced` 單向 Re-export），貫通 `EncodedStepOutput` 與 `include_presentation`/`rendered_text`/`exit_code` 管線；溫熱 Tier 0/1 Worker 直接於原始強型別物件求值（非 `HumanRenderable` 設 `rendered_text=None, exit_code=0` 避免大負載 RPC 雙倍序列化且支援 `Optional[ExitCodeProvider]` 回傳 `None`），徹底刪除 `factory.py` `_resolve_tier1_disk_presentation` 冷子行程與 `_TIER1_FORMAT_SNIPPET`，確保 `--json` 零呈現鍵洩漏且 `custom_exit_code=True` 遺失退出碼時拒絕靜默回落 `0`。
  3. **`FR-03` (`2A`，無 `--reveal`) Secret 憑證安全閉環**：於 `foundation/codec.py` 新增 `SECRET_FIELD_METADATA_KEY` 與 `secret_field(...)`（預設 `repr=False`，`SchemaExporter` 輸出 `writeOnly` + `x-yscb-secret`）並匯出至 `core.surface.sdk`（主入口精確 **53 符號** + `sdk.advanced` **38 符號**）；公開 `is_sensitive_key` 並於 `redact_cli_args` 遮罩 `config set --local`（含 `=` 密文）；`ConfigStore` 強制 `.config.local` `0o600`/`0o700` 與 Win32 DACL、`SnapshotVault` 嚴格排除 `.config.local/`，`core.config.{list,get,inspect,set}` 全面遞迴脫敏為 `"[REDACTED]"`（含兄弟巢狀、`list`/`Mapping`、`Annotated`/`Optional`、磁碟 `config.schema.json` 與頂層原義含點鍵，預設無 `--reveal`）。
  4. **`FR-04` (`3B`) 受管子行程雙向 `stdin`、無損 `bytes` 與工具鏈環境白名單**：新增 `TOOLCHAIN_ENV_ALLOWLIST` / `extract_toolchain_env`、`build_isolated_python_env(..., include_toolchain_env=...)`、`ManagedProcessTree(pipe_stdin=...)` / `stdin_pipe`、`ProcessResult(+stdout_bytes, stderr_bytes)` 與 `TaskContext.run_process(+input, inherit_toolchain_env)`（背景分塊寫入執行緒防管道互鎖、`BrokenPipeError` 安全收斂、`inherit_toolchain_env=False` 同步濾除 `caller_env` 代理/CA）。
  5. **`FR-05` (`4A`) `SpaceClient` 無鎖路徑反解與空間匹配**：於 `CoreSystemModule` 新增 2 支 `PARALLEL` `SDK_ONLY` 任務 `core.space.{resolve_uri,match_spaces}`（透過 `scoped_vfs_for_module` 強制呼叫模組讀隔離並容錯空間 TOCTOU），同步擴充 `SpaceClient.{resolve_uri,match_spaces}`，Tier 0/1 100% 對稱。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `core_v2/source/core/core/foundation/{primitives,codec,profiler,proc,__init__}.py` | Modify | 新增工具鏈白名單、`secret_field` + `SchemaExporter` 標記、`is_sensitive_key` / `redact_cli_args`、`ManagedProcessTree(pipe_stdin=...)` 與 `build_isolated_python_env` |
| `core_v2/source/core/core/metadata/config/{matrix,snapshot}.py` | Modify | `ConfigStore` 強化 `.config.local` `0o600`/`0o700` 與遞迴脫敏查詢（含磁碟 Schema）；`SnapshotVault` 嚴格排除 `.config.local/` |
| `core_v2/source/core/core/packaging/installer/{engine,__init__}.py` | Modify | 實作 `MigrationRollbackHandle`（`snapshot_module_storage_local` / `restore`）、`0o700` `.temp/` 與還原私密權限保留 |
| `core_v2/source/core/core/execution/lifecycle/engine.py` | Modify | `StepExecutionResult` 新增 `rendered_text` 與 `exit_code` 欄位 |
| `core_v2/source/core/core/execution/runtime/{contracts,wire,gates,module_slot,step_host,worker_entry,dispatcher,__init__}.py` | Modify | 下沉 `HumanRenderable`/`ExitCodeProvider`/`format_output`、新增 `EncodedStepOutput`、貫通 `skip_module_init` 與 `include_presentation`、擴充 `ProcessResult(+bytes)`、`TaskContext.run_process(+input, inherit_toolchain_env)` 與 `SpaceClient.{resolve_uri,match_spaces}` |
| `core_v2/source/core/core/surface/sdk/{declarative,__init__,advanced/__init__}.py` | Modify | 單向 Re-export Domain 5 呈現契約與 Domain 1 `secret_field`（`sdk` 精確 53 符號、`sdk.advanced` 維持 38 符號） |
| `core_v2/source/core/core/surface/cli/entrypoint.py` | Modify | CLI 消費熱 Worker 呈現與退出碼、`--json` 剔除呈現鍵並禁止 `custom_exit_code` 缺席靜默回落 `0` |
| `core_v2/source/core/core/surface/bootstrap/{factory,system_module,__init__}.py` | Modify | 刪除冷 Tier 1 呈現子行程、新增 `scoped_vfs_for_module`（`ModuleId("project")` 預設）、接線遷移回滾、`core.config.*` 全量脫敏與無鎖 `core.space.{resolve_uri,match_spaces}` |
| `core_v2/sub_module_design/{foundation/foundation,metadata/config,packaging/installer,execution/lifecycle,execution/runtime,surface/sdk,surface/sdk_advanced,surface/composition_and_bootstrap}.md` | Modify | 1:1 同步 8 份 Active Living Specs 簽名、常數與行為不變量（通過 `Gate 0` 雙向校驗） |
| `core_v2/tests/{test_foundation_fs,test_metadata_packaging,test_runtime_daemon,test_surface_sdk,test_surface_cli_e2e}.py` | Modify | 新增並通過 `FR-01`~`FR-05` 與 `EC-01`~`EC-06` 全量單元、安全與端到端回歸測試 |
| `core_v2/{ROADMAP,handoff}.md`, `CHANGELOG.md`, `plans/roadmap/TODO.md` | Modify | 對齊 Core 2.0 路線圖、交接快照與全域變更日誌；另於 P00 前置登記非本計畫跨計畫待辦 `TODO-35`~`TODO-37` |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率（100% 通過，零殘留警告）**：
  - **Linux 標準模式 (`-B -W error::ResourceWarning --suite all`)**：全 9 大套件 100% 通過（`265.42s`，`0 ResourceWarning`）。
  - **Linux 最佳化模式 (`-O -B -W error::ResourceWarning --suite all`)**：全 9 大套件 100% 通過（`289.40s`，`0 ResourceWarning`）。
  - **終版 ADVISORY 微調後雙模覆驗 (`gate0`, `metadata_packaging`, `unplug`, `surface_cli_e2e`)**：`-B` `189.29s` / `-O -B` `206.30s` 全綠，`0 ResourceWarning`。
  - **盲眼靜態審查收斂**：Pre-Code Analyze Gate 通過，Pre-UX 歷經 3 輪零錨定盲審收斂至 `REVIEW_STATUS: PASSED (0 BLOCKER)` 且最終 2 項 ADVISORY 亦全數落實修復；Phase 06 UX 驗證期間零源碼／測試改動，依 Phase 07 Pillar 3 情況 A 執行主 Agent 常規三層審查與 Docstring 稽核（`MISSING_DOCSTRINGS: []`）。
- **實機 UX / 人工驗證**：
  - **`UX-01` `[測試通過]`**：開發者於 Windows 11 實機執行 `python -O -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite all`，本次變更範疇所涵蓋之全 8 大套件（`gate0` `13.11s`、`foundation_fs` `2.81s`、`vfs_storage_space` `40.59s`、`metadata_packaging` `47.17s`、`surface_sdk` `8.19s`、`surface_cli_e2e` `524.73s`、`unplug` `8.36s`、`runtime_daemon` `42.05s`）與 `RC-01`~`04` 100% 通過，`0 ResourceWarning`。
  - **`UX-02` `[跳過/免測]`**：未觸及檔案之 `rc_e2e` `RC-05`（`test_rc_e2e.py:731` `put_pre_to` 受 `_harness.py` `timeout_ms=1000` 夾具預算於 Windows 11 冷重啟 `.venv` 抖動影響，確認零回歸且 Linux 雙模全綠）依開發者裁示免測跳過。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已更新 | 已於頂部追加本計畫高階成果、驗證數據與 `TODO-35`~`37` 追蹤摘要 |
| **中觀 (Meso)** | `core_v2/ROADMAP.md`、`core_v2/handoff.md` | 已更新 | 已更新 6 域 LOC（`67,932 LOC`）、53+38 SDK、5 項基建加固與雙平台驗收快照（1.x `docs/` 維持潔淨室零異動） |
| **中觀 (Meso)** | `core_v2/sub_module_design/` 8 份活規格 | 已更新 | `foundation` / `config` / `installer` / `lifecycle` / `runtime` / `sdk` / `sdk_advanced` / `composition_and_bootstrap` 1:1 同步並通過 `Gate 0` 雙向校驗 |
| **中觀 (Meso)** | `docs/<Category>/DESIGN_NOTES.md` | 免更 | 本計畫嚴守 `./core_v2/` 潔淨室隔離，1.x `docs/` 零異動，所有反直覺邊界已內化至對應 Active Living Specs |
| **微觀 (Micro)** | `core_v2/source/core/core/**/*.py` Public API 註解 | 已更新 | AST 全數核對新增／下沉之 13 項公開符號 Docstrings（`MISSING_DOCSTRINGS: []`），關鍵防死鎖與權限邏輯皆具 Why-Driven 註解 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack（`Gate 0` 與 3 輪零錨定盲審雙重核驗通過，且 `ys_codebase/source/*` 與 `.vscode/settings.json` 零異動）。
- [x] **測試完整覆蓋**：所有受影響之單元測試、整合測試、物理拔除與雙模端到端測試 100% 通過，無被破壞之斷言（`UX-02` 未異動範疇依開發者指示明確標記 `[跳過/免測]`）。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(core-v2): harden migration rollback, warm worker presentation, secret hygiene, process I/O and space resolution
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_26_0540_core_v2_greenfield_infra_hardening` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
