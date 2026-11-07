# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_04_ecosystem_migration_and_legacy_removal  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 啟動 `sub_04_ecosystem_migration_and_legacy_removal`。
  - 「對於要跟進版本更新的模組，皆採用 `/code-optimizer` `Mode A` 標準，不遺留任何舊版內容，對於有需要的模組註冊遷移 hook，對於 `file-space` 本體，考慮也添加一個空殼轉發 `core` 的版本並在版本組態上建議將 `core` 更新到 xxx 版後移除 `file-space`。」
- **核心目標**：
  1. **下游業務模組 `Mode A` 純淨遷移至 `core.space`（零遺留舊版相容垃圾）**：
     - 將 `agents-workflow`、`ast`、`knowledge-db`、`gdrive-support` 與 `core` 內部殘留之舊 `file_space` 參考全面遷移至 `core.space` 原生公開介面（`SpaceRegistry`、`SpaceScanner`、`SpaceConfig`、`SpaceNotFoundError`、`SpaceError`、`consume_diff`、`reset_cursor`、`subscribe` 等）。
     - 嚴守 `/code-optimizer` **`Mode A（收斂期 / 允許破壞性清理）`** 原則：在業務模組（`ast`、`knowledge-db`、`gdrive-support`、`agents-workflow`、`core`）中，**100% 物理根除對 `file_space` 的 import、舊型別別名轉發、舊 `contributes/file-space.json` 與舊 `scripts/hook.file-space.py`**（統一更名為 `scripts/hook.core.py` 監聽 `emit_module="core"` 之 `on_file_space_changed`），並從 `ast`、`knowledge-db`、`gdrive-support` 之 `manifest.json` 移除 `"file-space"` 相依。
  2. **模組與宿主層級自動遷移 Hook (`scripts/migrations/*.py`)**：
     - 於 `core` 升級遷移腳本（`scripts/migrations/1.2.7.x.py`）新增自動遷移邏輯：當偵測到宿主存在舊版 `config://file-space/contribute.json` 時，自動將舊版空間定義（`include` + `file_patterns` $\to$ `entries` + `include`）無損轉換並合併至 `config://core/contribute.json` 之 `spaces` 區段，且遷移舊版 `.storage.local/file-space/{snapshots,cursors}` 或清理遺留空目錄；同步將本倉 `ys_codebase/config/file-space/contribute.json` 正式遷移為 `ys_codebase/config/core/contribute.json` 並刪除舊目錄。
     - 於有需要的下游模組（如 `ast`、`knowledge-db`）提供對應版本之 `scripts/migrations/` 腳本，於升級時自動重置舊版格式之游標水位，確保升級後首次查詢自動對齊 `core.space` 世代。
  3. **`module:file-space` 終極空殼轉發過渡版 (`Facade Deprecation Shell`) 與退役指引**：
     - 將 `ys_codebase/source/file-space/` 重構為極簡空殼轉發層（移除舊版獨立 `manager.py`/`scanner.py`/`service.py` 龐大重複實作與 `contributes/server.json` 背景 `file-space-watcher` 註冊，杜絕雙 Watcher 雙重掃描，100% 轉發至 `core.space` 與 `core file-space` CLI）。
     - 於 `ys_codebase/source/file-space/manifest.json`（及 `release` / `onboarding` 組態）提升 `dependencies.core` 下限至 `>=1.2.7.5`（或當前包含完整 `core.space` 之目標版號），移除 `watchdog` 第三方依賴，並於 `description`、`onboarding` 與 `release.summary` 明確標示：**「[Deprecated] 檔案空間引擎已內聚併入 core.space；請將 core 更新至 >=1.2.7.5 並升級下游模組後，執行 `python yscb.py remove file-space` 移除本模組」**。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 全面復用 `sub_01` ~ `sub_03` 已建置完成之 `core.space`（`SpaceRegistry`、`SpaceScanner`、`BinarySnapshotManager`、`CursorStore`、`subscribe`、`is_watcher_active`）與 `server.space_watcher.CoreSpaceWatcherServiceWorker`。
  - 動態文檔 Token `FILE_SPACE_REGISTERED_TABLE` 移交至 `core`（`core/space/providers.py` + `core/contributes/agents-workflow.json`），`knowledge-db` 之 `get_knowledge_db_spaces` 直接讀取 `core.space.SpaceRegistry` 與 `knowledge-db` 之 `space_weights`。
- **邊界排除 (Explicitly Excluded)**：
  - 不在本子計畫執行 `[GATED]` 軌道 B 正式版本打包發布（`dev bump-*` / `dev release` 留待開發者於結案後顯式指示 `/bump-revision` 時統一處理；本計畫內準備好 `manifest.json` 描述與 `scripts/migrations/` 腳本，並以 `@build` 完成本機全模組自部署驗證）。
  - 不變更 `ast`、`knowledge-db`、`gdrive-support` 對外之業務搜尋演算法或雲端同步協議。
- **架構影響範圍**：
  - `ys_codebase/source/core/`（`core/space/providers.py`、`contributes/agents-workflow.json`、`commands/dispatcher.py`、`scripts/migrations/1.2.7.x.py`、`assets/{config_guide.md,usage_guide.md}`）
  - `ys_codebase/source/agents-workflow/`（`contributes/file-space.json` 併入 `contributes/core.json`）
  - `ys_codebase/source/ast/`（`manifest.json`、`contributes/`、`ast_engine/{engine,bundler,resolver}.py`、`scripts/cli.py`、`scripts/hook.file-space.py` $\to$ `scripts/hook.core.py`、`scripts/migrations/`、`tests/`）
  - `ys_codebase/source/knowledge-db/`（`manifest.json`、`contributes/`、`knowledge_db/{engine,pipeline,providers,retrieval}.py`、`scripts/cli.py`、`scripts/hook.file-space.py` $\to$ `scripts/hook.core.py`、`scripts/migrations/`、`tests/`）
  - `ys_codebase/source/gdrive-support/`（`manifest.json`、`contributes/_format.json`、`gdrive_support/{config,coordinator,service}.py`、`tests/`）
  - `ys_codebase/source/file-space/`（收斂為純 `core.space` 轉發空殼與棄用提示）
  - `ys_codebase/config/file-space/contribute.json` $\to$ `ys_codebase/config/core/contribute.json`
  - `docs/`（更新 `core`、`ast`、`knowledge-db`、`gdrive-support`、`file-space` 知識庫文檔）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 跟進模組全面採用 `/code-optimizer` `Mode A` 純淨收斂標準**：
  - 在 `core`、`agents-workflow`、`ast`、`knowledge-db`、`gdrive-support` 中，不保留任何 `try: import file_space except: import core.space` 之雙軌過渡分支或 `FileSpace*` 舊名稱遺留，直接 100% 切換至 `core.space` 原生型別與方法，並將 `scripts/hook.file-space.py` 物理替換為 `scripts/hook.core.py`。
- **[P00:DR-02] 組態與狀態自動遷移 Hook (`scripts/migrations/`)**：
  - 於 `core/scripts/migrations/1.2.7.x.py` 實作 `_migrate_legacy_file_space_config(yscb_dir)`：自動偵測 `<yscb_dir>/config/file-space/contribute.json`，將舊格式空間（`include` 轉 `entries`、`file_patterns` 轉 `include`）無損寫入 `<yscb_dir>/config/core/contribute.json` 並移除舊檔與空目錄。
  - 於 `ast` 與 `knowledge-db` 的 `scripts/migrations/` 註冊遷移腳本，升級時自動清理舊版 `file-space` 世代游標快取，確保無縫銜接 `core.space`。
- **[P00:DR-03] `module:file-space` 空殼轉發版 (`Facade Deprecation Shell`) 設計**：
  - `ys_codebase/source/file-space/` 移除舊版獨立掃描器、二進位讀寫器、`watchdog` 依賴與 `contributes/server.json`、`contributes/agents-workflow.json`，其 Python API (`file_space/__init__.py` 等) 與 CLI (`scripts/cli.py`) 全數輕量委派至 `core.space`。
  - 於 `manifest.json` 的 `dependencies` 設定 `"core": ">=1.2.7.5"`，並於 `description`、`onboarding` 與 `release.summary` 提示使用者在將 `core` 更新至 `>=1.2.7.5` 後即可安全執行 `python yscb.py remove file-space` 移除 `file-space`；本母倉工作區在驗證完空殼模組獨立沙盒測試後，於本機環境卸載 `file-space` 驗證純 `core.space` 運作。
- **[P00:DR-04] 盲眼 Devil's Advocate 反向查驗揭露之 6 大微觀契約對齊措施**：
  1. **`ScanDiffDetail.dirty_files` 語義收斂**：將 `core.space.scanner.ScanDiffDetail.dirty_files` 對齊為 `self.added | self.modified`（不含 `deleted`），防止 `ast` 與 `knowledge-db` 熱修補管線將已刪除檔案誤當存活檔案重新解析或重複計數。
  2. **短名 (`short_name`) 與 `<owner>/<space>` 對齊**：`ast`（`UnifiedSymbol.spaces`）與 `knowledge-db`（`space_weights: {"source": 1.0, "docs": 1.2, "plans": 0.85}` 及 `--space` 過濾）在 `core.space` 下對齊 `s_cfg.short_name` 與 `s_cfg.qualified_name` 雙向匹配，確保短名權重配置與 `--space=docs` / `--space=source` 100% 命中。
  3. **跟進模組 `Mode A` 全面切換至 `core.space` 原生 API**：`ast`、`knowledge-db`、`gdrive-support` 全面改用 `SpaceRegistry`（`list_spaces`、`resolve_spaces`、`iter_space_files` 回傳之 `SpaceFileEntry.{rel_path,abs_path,entry_path,mtime_ns,ctime_ns,size,matched_spaces}`）、`SpaceScanner`（`space_query`、`snapshot`、`consume_diff`、`reset_cursor`）與 `SpaceConfig`（`entries`/`include`/`exclude`），同步將模組內 `tests/` 測試夾具之 `custom_spaces` / `contributes_data` 升級為 `core.space` 原生 `entries`/`include` 結構。
  4. **`core` 接管 `FILE_SPACE_REGISTERED_TABLE` 與移除頂層 CLI 避讓**：於 `core/space/providers.py` 與 `core/contributes/agents-workflow.json` 原生提供 `FILE_SPACE_REGISTERED_TABLE` 動態表格；移除 `core/commands/dispatcher.py` 對外部 `file-space` 的過渡期避讓邏輯。
  5. **`act_migrate` 升級腳本與 `@build` 開發環境雙重保障**：除於 `core/scripts/migrations/1.2.7.x.py`（及 `ast`/`knowledge-db` 的 `scripts/migrations/`）註冊標準版本升級遷移外，同步將本倉 `ys_codebase/config/file-space/contribute.json` 轉換為 `ys_codebase/config/core/contribute.json`（舊 `"include"` 轉 `"entries"`、舊 `"file_patterns"` 轉 `"include"`）並將 `agents-workflow/contributes/file-space.json` 併入 `agents-workflow/contributes/core.json`。

---

## 3. 開放議題與確認紀錄

- 遷移原則（跟進模組採 `Mode A` 零遺留、註冊遷移 Hook、`file-space` 本體改為轉發 `core` 空殼並於版本組態提示更新 `core` 後移除）已全數確認，進入規格與實作階段。
