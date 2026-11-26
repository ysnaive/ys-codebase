# 成果展示與結案報告 (Walkthrough)

> 功能名稱：Core 2.0 下游模組 SDK 門面雙層收斂與開發人體工學重構  
> 建立日期：2026-11-26  
> 所屬主計畫：無（獨立 Full Track 計畫，為 Wave 1.3 `dev 2.0` 與 Wave 2 下游模組移植之前置門面鎖定）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (XHigh)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **雙層零反射 SDK 門面 (`FR-01`)**：將主入口 `core.surface.sdk` 收斂為業務模組（`knowledge-db`、`agents-workflow` 等）高頻必用之精確 **52 符號**；新建進階子套件 `core.surface.sdk.advanced`（`sdk/advanced/__init__.py`）承接外部客戶端、剖析器、低階轉接與值物件之精確 **38 符號**（與主入口零交集）；清退 4 組 `Space*Input`（移至 `surface/bootstrap/system_module.py`）與 2 組 `SPACE_*_EVENT_ID_STR`（全倉退役），兩層 `__all__` 完整接入 `Gate 0` 雙向校驗（`sdk.md` + 新建 `sdk_advanced.md`）。
  2. **一等空間門面 `ctx.spaces: SpaceClient` 與強型別系統事件 (`FR-02`)**：於 Domain 5 單一真理下沉 `Empty`、3 組事件 Payload DTO、2 組新 `SPACE_*_EVENT_ID` 與 6 組強型別 `EventMetadata` 常數（`MODULE_REMOVING_EVENT` 為 `EventOrdering.ORDERED`）；實作 `SpaceClient` 並新增 4 支無鎖併發讀 `SDK_ONLY` 系統任務 `core.space.{list,status,files,diff}`，Tier 0/1 跨進程 100% 對稱。
  3. **VFS 橋接／`glob` 與受管子行程 `ctx.run_process` (`FR-03`)**：於 `ManagedProcessTree` 新增無緩衝 `bufsize=0` `capture_output` 雙管道與 `close_pipes()`；於 `ScopedVfs` 新增 `glob` 與防未折疊符號連結／防 `.yscb/` 降級外洩之 `resolve_caller_uri`；於 `TaskContext` 新增 `resolve_uri` 與 `run_process`（隔離環境、Windows 大小寫去重、`CREATE_NO_WINDOW`、取消保留 `TASK_PREEMPTED` 並終止整棵進程樹）。
  4. **統一跨模組強型別呼叫與零樣板模組人體工學 (`FR-04`, `FR-05`)**：新增不可變 `TaskRef[TIn, TOut]`，以統一重載之 `TaskContext.call(...)` 與 `YscbClient.call(TaskRef, ...)` 取代 `invoke_task`/`invoke_typed`；實作 `ProtectedModuleLoader` 無 `create_module()` 唯一具象非抽象子類自動探索、協變 `TaskGroup[TModule_co]`/`.module`、`ctx.module_id`、`@task(..., equivalence_fn=...)` 與 `@on_event` 錯誤指引強化。
  5. **UX-01 實機連帶加固**：針對 Windows 11 `-O` 實機驗證捕獲之 `core_sig_cache` 時間窗競態，經開發者授權同步補強 `execution/daemon/service.py` `cache_mtime_ns` / `_boot_core_snapshot_ns` 20ms 雙條件 Racy-Clean 守衛與對應跨重啟測試。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `core_v2/source/core/core/foundation/{proc,errors}.py` | Modify | `ManagedProcessTree` 支援 `capture_output`/`bufsize=0`/`close_pipes()`；`CallCycleError` 修復指引遷移至 `ctx.call()` |
| `core_v2/source/core/core/filesystem/vfs/scoped.py` | Modify | 新增 `ScopedVfs.glob` 與安全優先之 `ScopedVfs.resolve_caller_uri` |
| `core_v2/source/core/core/execution/runtime/{contracts,module_slot,__init__}.py` | Modify | 下沉 `Empty`/6 組系統事件/`TaskRef`/`ProcessResult`/`SpaceClient`/`YscbModuleConvertible`；新增 `TaskContext.{module_id,spaces,call,resolve_uri,run_process}` 與模組自動探索 |
| `core_v2/source/core/core/execution/daemon/service.py` | Modify | 補強 `core_sig_cache` 跨重啟 `cache_mtime_ns` 與 `_boot_core_snapshot_ns` 20ms 雙條件 Racy-Clean 守衛 |
| `core_v2/source/core/core/surface/sdk/{__init__,declarative,client}.py` | Modify | 收斂 52 符號主入口；協變 `TaskGroup[TModule_co]`/`.module`、`@task(..., equivalence_fn=...)`、`YscbClient.call(TaskRef)` |
| `core_v2/source/core/core/surface/sdk/advanced/__init__.py` | New | 新建進階二層子套件（精確 38 符號 `__all__`，與主入口零交集） |
| `core_v2/source/core/core/surface/{cli/entrypoint,bootstrap/factory,bootstrap/system_module,bootstrap/__init__}.py` | Modify | 遷移內部匯入至 `sdk.advanced`（含 `_TIER1_FORMAT_SNIPPET`）；承接 4 組 `Space*Input` 並新增 4 支無鎖併發讀 `core.space.{list,status,files,diff}` 系統任務 |
| `core_v2/sub_module_design/{foundation/foundation,filesystem/vfs,execution/runtime,execution/daemon,surface/sdk,surface/composition_and_bootstrap}.md` | Modify | 1:1 同步 6 份既有 Active Living Specs |
| `core_v2/sub_module_design/surface/sdk_advanced.md` | New | 新建 `core.surface.sdk.advanced` 正式活規格並納入 `Gate 0` 雙向校驗 |
| `core_v2/tests/{_harness,test_gate0,test_foundation_fs,test_vfs_storage_space,test_runtime_daemon,test_surface_sdk,test_surface_cli_e2e}.py` | Modify | 更新 `Gate 0` 雙層校驗與跨包白名單；遷移測試至 `ctx.call` / `sdk.advanced` 並補齊 `FR-01`~`FR-05`、`EC-01`~`EC-06` 及雙條件 `core_sig_cache` 測試 |
| `core_v2/{ROADMAP,handoff}.md`, `CHANGELOG.md`, `plans/roadmap/TODO.md` | Modify | 同步 52+38 雙層 SDK 與 18 份活規格基線、追加全域變更日誌、登記黑箱盲區 `TODO-33`/`TODO-34` |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：Linux 全 9 大套件標準模式（`248.35s`）與 `-O` 模式（`278.37s`）100% 通過（`0 ResourceWarning`）；UX-01 補強 `core_sig_cache` 雙條件 Racy-Clean 後覆驗 Linux 雙模 `gate0`（`11.24s`/`10.94s`）、`runtime_daemon`（`14.69s`/`18.70s`）、`unplug`（`2.62s`/`4.36s`）與 `rc_e2e`（`59.98s`/`69.89s`）100% 全綠（`0 ResourceWarning`）。Pre-Code Analyze Gate (`ANALYZE_GATE: PASSED`) 與 Pre-UX 盲眼靜態審查 (`REVIEW_STATUS: PASSED`，0 Blockers) 皆通過；Phase 7 屬情況 A（UX 期間僅單一內聚 Racy-Clean 補強）經內聯審查確認零敷衍與零架構漂移。
- **實機 UX / 人工驗證**：**UX-01 `[測試通過]`** — Windows 11 `-O` 實機全 9 大套件 100% 全綠且 `0 ResourceWarning`（`gate0` `22.55s`、`foundation_fs` `3.83s`、`vfs_storage_space` `103.80s`、`metadata_packaging` `64.53s`、`surface_sdk` `8.53s`、`surface_cli_e2e` `718.12s`、`unplug` `8.16s`、`runtime_daemon` `39.92s`、`rc_e2e` `137.41s`），經開發者顯式確認簽核。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已更新 | 追加 `2026_11_25_1630_core_v2_sdk_ergonomics_overhaul` 高階發布與雙平台驗收摘要 |
| **中觀 (Meso)** | `core_v2/{ROADMAP,handoff}.md` | 已更新 | 同步 52+38 雙層 SDK、94 檔 / `66,952 LOC`、18 份 Active Living Specs 與 Wave 1.3/2 入口 |
| **中觀 (Meso)** | `core_v2/sub_module_design/{foundation/foundation,filesystem/vfs,execution/runtime,execution/daemon,surface/sdk,surface/sdk_advanced,surface/composition_and_bootstrap}.md` | 已更新 | 7 份正式活規格（含新建 `sdk_advanced.md`）100% 通過 `Gate 0` 1:1 雙向校驗 |
| **中觀 (Meso)** | `docs/<Category>/DESIGN_NOTES.md` | 免更 | 嚴守 `core_v2` 潔淨室邊界，不異動 1.x `docs/`；無額外反直覺妥協需跨區補記 |
| **微觀 (Micro)** | 受異動之 `core_v2/source/core/core/**/*.py` | 已更新 | 全部新增與異動公開介面具備完整型別契約、Docstrings 與關鍵安全動機註解 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack；`ys_codebase/source/*` 與 `.vscode/settings.json` 零異動。
- [x] **測試完整覆蓋**：全 9 大套件於 Linux 雙模與 Windows 11 `-O` 100% 通過（`0 ResourceWarning`），無跳過或放寬之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
refactor(core-v2): split SDK into 52+38 tiers and overhaul module ergonomics

- Split core.surface.sdk into 52 primary business-module exports and new core.surface.sdk.advanced (38 advanced/client exports) with full Gate 0 1:1 living-spec parity (sdk.md + sdk_advanced.md)
- Add first-class ctx.spaces (SpaceClient) backed by 4 lock-free PARALLEL SDK_ONLY core.space.{list,status,files,diff} tasks and sink Empty + 6 typed system EventMetadata singletons to Domain 5
- Add ManagedProcessTree(capture_output=True, bufsize=0), ScopedVfs.{glob,resolve_caller_uri}, and TaskContext.{module_id,resolve_uri,run_process}
- Introduce immutable TaskRef[TIn, TOut] with unified TaskContext.call / YscbClient.call replacing invoke_task / invoke_typed
- Support zero-boilerplate concrete Module subclass auto-discovery, covariant TaskGroup[TModule_co].module, @task(equivalence_fn=...), and dual-condition Racy-Clean core_sig_cache hardening
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_25_1630_core_v2_sdk_ergonomics_overhaul` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
