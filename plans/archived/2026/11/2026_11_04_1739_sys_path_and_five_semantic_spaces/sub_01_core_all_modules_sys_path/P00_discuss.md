# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_core_all_modules_sys_path  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Completed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「首先對於 冷派發 file-space 模組尋址，是不是應由 core 派發前就寫入所有 module 模組進入 sys path ? (包含熱派發)」
  - 「sub 01: core 全模組 sys.path」
- **核心目標**：
  1. 於 `core` 建立統一的已安裝模組路徑注入機制（如 `ensure_installed_modules_in_sys_path`），將 `yscb://.modules/<mod>` 下所有已安裝模組根目錄寫入 `sys.path`。
  2. 統一接入四大執行入口：
     - 本地與熱派發 CLI 入口：`core/commands/dispatcher.py:dispatch_local`
     - 生命週期事件廣播入口：`core/events.py:broadcast`
     - 跨模組符號解析入口：`core/symbols.py:resolve_callable`
     - 常駐 Server Worker 預熱入口：`server/worker.py:WarmWorker.pre_warm`
  3. 依據 [`R01_sys_path_comprehensive_audit.md`](./R01_sys_path_comprehensive_audit.md) 三分區盲眼子代理地毯式盤點結果，徹底抽離並移除散落於 7 個模組中的 **13 處生產代碼手動 `sys.path` 補丁**（含 `agents-workflow`、`vscode-support`、`file-space`、`ast`、`knowledge-db`、`dev/checker.py` 等處之 `_ensure_module_path`、`_ensure_dependency_module_paths` 及 `../source/` 越界 fallback），並將特殊路徑初始化（`ProcessPoolExecutor` 子進程快照、宿主自訂解析器掛載、`dev test` 沙盒待測模組源碼掛載與還原）全數收斂為 `core.platform` 權威原語，達成 **非 `core` 生產程式碼 0 處直接修改 `sys.path`**。
  4. 於 `dev/checker.py:_check_source_files` 新增剛性靜態 AST 檢查（`CheckSeverity.FAIL`，**零模組豁免白名單**），禁止任何非 `core` 生產源碼檔案直接變動 `sys.path`。
  5. 併入 `[TODO-22]`：於 `core.platform` 擴充 `list_module_search_roots(yscb_root, prefer_source=True)`，並讓 `vscode-support` 之 `SettingsProjector._compute_managed_extra_paths` 自動將 YSCB 模組搜尋根路徑（優先投影 `<yscb_dir>/source/<mod>`，若無則投影 `<yscb_dir>/.modules/<mod>`）寫入 `.vscode/settings.json` 之 `python.analysis.extraPaths`，且當 `extraPaths` 包含 `.modules/<mod>` 時動態自 `python.analysis.exclude` 移除 `**/.modules/**`，達成執行期 `sys.path` 與 IDE 靜態 `extraPaths` 100% 對齊並支援 `_yscb_managed` 乾淨還原 (`revert`)。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 收斂並取代分散於 `core/commands/dispatcher.py`（L573-580）、`core/events.py`（L84-88）、`core/symbols.py`（L115-179）、`server/master.py`（L107-128, L742-770）、`server/worker.py`（L55-81）、`server/service.py`（L240-243）、`ast/ast_engine/bundler.py`（L394-400）、`ast/ast_engine/parsers/registry.py`（L123-163, L210-212）、`dev/testing/runner.py`（L165-181）與 `dev/testing/case.py`（L86, L137）中的 `sys.path` 操作邏輯，並拔除 13 處業務模組散落補丁。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁將任何 `source/<mod>` 開發源碼路徑注入生產運行時 `sys.path`（100% 維持 `.modules/` 剛性執行邊界；僅保留宿主根目錄 `yscb.py` Bootstrap 前置引導與 `core.platform` 受控之 `dev test` 沙盒單一待測模組隔離原語）。
  - 五大語意空間（`config.local://` / `storage.local://`）之擴充與遷移歸屬 `sub_02` 與 `sub_03`，不在本子計畫範疇內。
- **架構影響範圍**：
  - 核心入口與原語收斂：`core/{platform/venv.py,platform/__init__.py,commands/dispatcher.py,events.py,symbols.py}`、`server/{master.py,worker.py,service.py}`、`ast/ast_engine/{bundler.py,parsers/registry.py}`、`dev/dev/testing/{runner.py,case.py}`
  - 靜態 AST 守門新增：`dev/dev/checker.py`、`dev/tests/test_checker.py`
  - 散落補丁拔除：`agents-workflow/{agents_workflow/compiler.py,agents_workflow/publisher.py,scripts/hook.core.py}`、`vscode-support/scripts/{cli.py,hook.core.py}`、`file-space/scripts/cli.py`、`ast/{ast_engine/__init__.py,scripts/cli.py,scripts/hook.file-space.py}`、`knowledge-db/knowledge_db/{__init__.py,io_utils.py,providers.py}`、`dev/dev/checker.py`、`core/tests/test_config.py`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 統一由 `core` 注入所有已安裝 `.modules/<mod>` 並確立 `sys.path` 優先序**：
  - 掃描 `yscb_root/.modules/` 下所有非隱藏子目錄（跳過 `.` 開頭之 `.staging_*`、`.old_*` 暫存交換目錄，且防衛性排除任何含 `/source` 之開發路徑）。
  - `sys.path` 前置優先序：當前目標模組 `.modules/<priority_module>` 置於 `sys.path[0]`，其次為 `.modules/core`，其餘已安裝 `.modules/<mod>` 按字典序確保存在於 `sys.path` 中（不重複添加）。
- **[P00:DR-02] 四大執行通道全覆蓋（冷派發 / 熱派發 / 事件廣播 / 符號解析）**：
  - `dispatch_local`、`events.broadcast`、`symbols.resolve_callable` 與 `WarmWorker.pre_warm` 均調用同一套 `core` 路徑注入原語，確保像 `gdrive auth`（`server_compatible: false` 冷派發）載入 `file_space` 時與 Server 熱派發 100% 行為一致。
- **[P00:DR-03] 沙盒測試與 `events.broadcast(search_roots=...)` 相容性**：
  - 當 `events.broadcast` 指定自訂 `search_roots`（如單元測試沙盒）時，除注入 `module://` 已安裝模組外，該 `search_roots` 內之目標 hook 模組根目錄仍置於最前，確保既有單元測試與沙盒隔離 100% 無損。
- **[P00:DR-04] `dev/checker.py` 新增剛性靜態 AST 檢查（零豁免白名單）**：
  - 將 `ast/bundler.py`（子進程快照）、`ast/parsers/registry.py`（自訂解析器路徑掛載）、`dev/testing/runner.py` 與 `case.py`（沙盒測試待測模組路徑掛載與還原）全數收斂為 `core.platform` 導出原語。
  - 於 `dev/checker.py:_check_source_files` 新增對 `name != "core" and not is_test_file` 的 AST 檢查：凡偵測到 `sys.path.<mutating_method>(...)`、對 `sys.path`（含切片/下標）之賦值（`Assign` / `AnnAssign` / `AugAssign`）或刪除（`Delete`），一律觸發 `CheckSeverity.FAIL`，杜絕未來任何業務模組再度私自塞入 `sys.path` 補丁。
- **[P00:DR-05] 執行期 `sys.path` 與 IDE 靜態 `python.analysis.extraPaths` 雙面對齊（併入 `TODO-22`）**：
  - 拔除手動 `sys.path` 補丁後，為使 VS Code / Pylance 靜態分析能解析 `from core import uri, vfs` 等跨模組匯入，由 `core.platform.list_module_search_roots(yscb_root, prefer_source=True)` 統一發現各模組搜尋根目錄（若 `<yscb_root>/source/<mod>` 存在則優先選用，否則回退至 `<yscb_root>/.modules/<mod>`），並由 `vscode-support` (`SettingsProjector`) 自動投影至 `.vscode/settings.json` 的 `python.analysis.extraPaths` 與 `_yscb_managed.extraPaths`，支援 `vscode-support revert` 100% 乾淨還原。

---

## 3. 開放議題與確認紀錄

- 開發者已確認由 `core` 在派發前統一將所有已安裝模組寫入 `sys.path`（包含冷派發與熱派發）、抽離全專案散落 `sys.path` 邏輯、同步於 `dev` 工具箱添加禁止非 `core` 模組注入 `sys.path` 之靜態檢查，並指示對完善後之規格書執行 `/blind-subagent` 審查。

