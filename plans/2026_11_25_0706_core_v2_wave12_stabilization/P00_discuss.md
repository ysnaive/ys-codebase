# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Core 2.0 Wave 1.2 止血收斂與下游契約補齊計畫  
> 建立日期：2026-11-25  
> 所屬主計畫：無（獨立 Full Track 計畫）  
> 狀態：Confirmed  
> 模型：Gemini 4 Neon (XHigh)  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：於完成 Core 2.0（Wave 1.1 + Wave 1.2）全量架構與品質評估後，開立一輪定向「Wave 1.2 止血收斂計畫」，於啟動 Wave 1.3 (`dev 2.0`) 與 Wave 2/3 下游模組遷移前，集中排除實證 P0 缺陷、全面鎖緊安全邊界並補齊下游必要契約。
- **核心目標**：
  1. 一次清零全量評估實證確認之 10 項 P0 缺陷（涵蓋 `metadata`/`packaging`、`filesystem/{fs,vfs,storage,space}`、`execution/{runtime,daemon}` 與 `core_v2/yscb.py`）。
  2. 全面鎖緊 `CallerMode`、`yscb.py` 自舉原語與 `config.local://`／`storage.local://` 跨模組讀取隔離，同時根治 `CI=true` 與 AI Agent 並存時之誤判及測試沙盒污染。
  3. 以根因收斂方式統一 `manifest.json` 解析、於 `core.surface.sdk` 建立正規 `Module -> TaskGroup` 狀態共享並拔除 `CoreSystemModule` TLS 繞道、補齊 `core` 真實打包元資料、`core.space.ack_cursor`、`ScopedVfs.open_read()` 與 SDK 簽名缺漏型別。
- **既有組件復用與查重 (Reuse Discovery)**：
  - `manifest.json` 2.0 解析統一收斂於 `core.metadata.config.manifest`，由 `core.packaging.installer.models` 與 `core.metadata.contributes.workspace_builtins` 共同復用，杜絕雙份解析漂移。
  - `ScopedVfs.open_read()` 直接復用已實作的 `VfsProvider.open_read()`（`vfs/provider.py:520-588`），不另造平行串流層。
  - `core.space.ack_cursor` 直接薄封裝既有的 `SpaceScanner.ack_cursor()`（`space/scanner.py:800`）。
  - `yscb.py` 僅新增極簡零外部依賴環境變數守門函式，不重複複製完整兩段式 `ApprovalTokenStore`。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴守潔淨室邊界：零異動 `ys_codebase/source/*`（1.x 主線源碼）與根目錄 `.vscode/settings.json`。
  - 排除 Wave 1.3 `dev 2.0` 工具鏈實作與 `dev.md` 開放議題定案。
  - 排除波段 B/C 大規模結構重構與進階效能優化：Domain 3 膠水遷移、`WorkspaceKernel`/`system_module.py`/`yscb.py` 拆檔、Tier 1 每呼叫 SHA-256 快取化與 `HumanRenderable` 熱 Worker 移轉、`UpdateChecker` 真非阻塞改造、真實 `tree-sitter`/`fastembed` 輪子壓測與 1.x→2.0 遷移工具。
- **架構影響範圍**：
  - 內核 6 大功能域：`foundation/observability.py`、`filesystem/{fs,vfs,storage,space}`、`metadata/{config,contributes}`、`packaging/{env,installer}`、`execution/{runtime,daemon}`、`surface/{sdk,cli,bootstrap}`。
  - 啟動器與打包元資料：`core_v2/yscb.py` 與新增 `core_v2/source/core/{manifest.json,configurable/,contributes/,.yscbignore}`。
  - 活規格與驗證：`core_v2/sub_module_design/**/*.md` 對應契約同步、`core_v2/tests/` 全套 9 套件回歸與新增鎖死測試。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 10 項實證 P0 缺陷一次清零**：
  1. `P0-1` 統一 `manifest.json` 2.0 解析於 `metadata.config.manifest`，使 `ReleaseMeta` 正確接受規格定義之 `"type"` 欄位（相容別名），`installer/models.py` 與 `workspace_builtins.py` 統一調用，消除已裝模組遭靜默丟棄。
  2. `P0-2` 修正 `space/rules.py` URI 座標萬用字元編譯保留 POSIX 絕對路徑前導 `/`，恢復 `project://plans/*.md` 等規則於 Linux/macOS 匹配。
  3. `P0-3` 修正 `vfs/mount.py` 與 `vfs/scoped.py` 反向掛載寫入檢查改為檢驗「所有覆蓋目標實體路徑之掛載並取最嚴格權限」，封堵同址工作區 `project://yscb.py` 覆寫與唯讀別名穿透。
  4. `P0-4` 修正 `fs/atomic.py` 與 `foundation/observability.py` Windows Reparse Point 檢查，依 `st_reparse_tag` 僅攔截 `IO_REPARSE_TAG_SYMLINK` (`0xA000000C`) 與 `IO_REPARSE_TAG_MOUNT_POINT` (`0xA0000003`)，放行 OneDrive Cloud Files 與 WOF 壓縮檔。
  5. `P0-5` 修正 `storage/database.py` `_stg_translate_db_error`，區分暫時性 `SQLITE_BUSY`/`SQLITE_FULL`、約束/語法錯（`IntegrityError`/`ProgrammingError`）與真實磁碟損毀 `STORAGE_CORRUPT`。
  6. `P0-6` 修正 `execution/runtime/coordinator.py` 佇列中 `COALESCE` Leader 等待晉升與取 OS 鎖時改傳 `holder.cancel_token` 與動態 `flight.effective_deadline()`，防止單一 Leader 取消或短逾時誤殺存活 Follower。
  7. `P0-7` 修正 `execution/runtime/{dispatcher,gates}.py`，將 `StepFlight` Step 5 排空納入 `LifecycleReloadGate` 重入排空豁免並傳遞動態 deadline，根除 `QUIESCE` 與 Step 5 之 AB-BA 死鎖。
  8. `P0-8` 修正 `execution/daemon/service.py` 與 `filesystem/fs/{atomic,watcher}.py`，移除 100ms 輪詢硬上限（改以可配置輪詢間隔運作）並預設剪枝 `.git`、`node_modules`、`.venv`、`.cache`、`build`、`dist`、`target`。
  9. `P0-9` 修正 `packaging/env/{pool,gc}.py` 與 `execution/runtime/{worker_pool,step_host}.py`，於 Tier 1 執行期節流刷新 `last_used_epoch_sec` 並對 `env_<hash>.lock` 取共享讀鎖，修復 7 天回滾寬限期失效與 POSIX 運行中 `.venv` 遭 GC 誤刪競態。
  10. `P0-10` 於 `core_v2/yscb.py` 為 `init --fix` 與 `self-update` 補齊輕量環境守門，阻擋非互動 `AGENT`/`CI`/`NON_TTY` 未授權覆寫啟動器或 `.modules/core`。
- **[P00:DR-02] 安全邊界全面鎖緊（`CallerMode` + `config.local://` / `storage.local://` 讀取隔離）**：
  - `surface/cli/caller_mode.py`：調整偵測優先序使顯式 AI Agent 識別優先於 `CI`（保留 `YSCB_CALLER_MODE=ci` 顯式強制覆寫）；當偵測到活躍 Agent 環境時禁止以 `YSCB_CALLER_MODE=human` 自我降級；將過寬前綴收窄為精準 Agent Session 識別鍵以防誤傷人類開發者終端。同步修正 `test_surface_cli_e2e.py` `_build_sanitized_subproc_env` 清除 `CI*` 變數。
  - `filesystem/vfs/scoped.py`：針對非核心模組鎖死 `config.local://` 與 `storage.local://` 之跨模組讀取隔離（僅允許讀取自身 `@/` 命名空間），核心模組維持全權限以支援系統管理與快照備份。
- **[P00:DR-03] `core` 自身真實打包元資料落地**：
  - 於 `core_v2/source/core/` 建立符合 2.0 規格的 `manifest.json`、`configurable/config.project.json.tmpl`、`contributes/`（如有必要）與 `.yscbignore`，使 `core` 可被 Wave 1.3 `dev 2.0` 原生打包與驗證。
- **[P00:DR-04] 下游契約與 SDK 根因補齊**：
  - `CoreSystemModule` 新增 `core.space.ack_cursor` 系統任務；`ScopedVfs` 公開串流 `open_read()`。
  - `core.surface.sdk`：於 `__all__` 補齊 `TaskContext` 簽名缺漏 4 型別（`TaskMetadata`、`ClientRoutingPolicy`、`ExecutionPriority`、`JsonValue`）及標準核心事件 ID／常用系統 DTO；為 `Module` / `TaskGroup` 提供正規狀態共享注入機制並拔除 `CoreSystemModule` 之 TLS + 弱引用註冊表繞道。
  - 同步更新受影響之 Active Living Specs 並通過 Gate 0 1:1 雙向校驗。
- **[P00:DR-05] Linux 全量驗證結案與本機 Windows 另行驗收**：
  - 本計畫於本 Linux 容器完成實作、新增鎖死測試（含 Windows `st_reparse_tag` 行為模擬、`CI=true` + `ANTIGRAVITY_AGENT=1` 實境、10 項 P0 回歸與跨模組讀取隔離）並通過 9 大套件標準/`-O` 雙模全綠（`0 ResourceWarning`）即行結案；本機 Windows 11 實機驗證於 P06 登記為 `UX-01` 並依開發者裁決標記為 `[跳過/免測]` 另行於 Windows 主機驗收。

---

## 3. 開放議題與確認紀錄

- **Q1（範疇邊界）**：開發者確認採**完整波段 A**（10 項 P0 + `CallerMode` 修正 + `core` 真實打包元資料 + `ack_cursor` / `ScopedVfs.open_read` / SDK 缺漏型別與狀態共享），波段 B/C 重構與效能優化顯式排除。
- **Q2（安全邊界力道）**：開發者確認採**全面鎖緊**（`AGENT` 優先於 `CI`、封鎖 Agent 環境 `human` 降級、收窄過寬前綴、`yscb.py` 輕量守門，並一併鎖死 `config.local://`／`storage.local://` 跨模組讀取隔離）。
- **Q3（重複解析與 SDK 狀態共享修法）**：開發者確認採**根因收斂**（統一 `manifest.json` 解析於 `metadata.config.manifest`；SDK 提供正規 `Module -> TaskGroup` 狀態注入並拔除 `CoreSystemModule` TLS 繞道）。
- **Q4（計畫模式與 Windows 實測銜接）**：開發者確認採**獨立 Full Track 計畫**，於本 Linux 端完成模擬測試與全量回歸即結案，本機 Windows 11 實測另行驗收。
- **當前開放議題**：無，所有邊界與決策均已拍板定案。
