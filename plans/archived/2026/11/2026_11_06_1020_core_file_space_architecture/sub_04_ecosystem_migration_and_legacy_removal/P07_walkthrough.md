# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_04_ecosystem_migration_and_legacy_removal  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`core.space` 微觀對齊、`FILE_SPACE_REGISTERED_TABLE` 移交與 CLI 避讓移除 (`FR-01`, `EC-01`)**：將 `ScanDiffDetail.dirty_files` 修正為 `self.added | self.modified`（與 `deleted` 嚴格正交）；新建 `core/space/providers.py` 實作 `get_registered_file_spaces_table` 與 `get_knowledge_db_spaces`，由 `core/contributes/agents-workflow.json` 原生接管 `FILE_SPACE_REGISTERED_TABLE` 計算標籤；移除 `core/commands/dispatcher.py` 中頂層 `file-space` 對外部舊模組之過渡期避讓，並從 `core/installer.py` 的預設 `candidate_mods` 移除 `"file-space"`。
  2. **宿主專案與 `agents-workflow` 空間組態遷移及自動遷移 Hook (`FR-02`, `EC-03`)**：將 `ys_codebase/config/file-space/contribute.json` 遷移為 `ys_codebase/config/core/contribute.json`（舊 `"include"` 路徑根轉 `"entries"`、舊 `"file_patterns"` 萬用字元轉 `"include"`）並刪除舊目錄；將 `agents-workflow` 之 `docs` 與 `plans` 空間併入 `agents-workflow/contributes/core.json` 並刪除 `contributes/file-space.json`；於 `core/scripts/migrations/1.2.7.x.py` 新增 `_migrate_legacy_file_space_config(yscb_dir)` 自動遷移舊版組態，並於 `ast` (`scripts/migrations/1.0.1.x.py`) 與 `knowledge-db` (`scripts/migrations/1.2.1.x.py`) 實作消費者游標重置遷移腳本。
  3. **下游業務模組 (`ast`、`knowledge-db`、`gdrive-support`) `Mode A` 純淨遷移至 `core.space` (`FR-03`, `EC-02`, `EC-04`, `NFR-01`, `NFR-02`)**：從 `ast`、`knowledge-db`、`gdrive-support` 之 `manifest.json` 移除 `"file-space"` 相依（`"core": ">=1.2.7.4"`），將內部與測試全面切換至 `core.space`（`SpaceRegistry`、`SpaceScanner`、`SpaceConfig`、`SpaceNotFoundError`、`SpaceError`、`ScanDiffDetail`、`ScanDiffResult`、`consume_diff`、`reset_cursor`、`subscribe`），100% 根除 `from file_space import ...`；將 `ast` 與 `knowledge-db` 之事件訂閱腳本遷移為 `scripts/hook.core.py`（同時支援 `<owner>/<space>` 與 `short_name` 雙向匹配）。
  4. **`module:file-space` 棄用空殼轉發版 (`Facade Deprecation Shell`) 與本機退役 (`FR-04`, `EC-05`, `NFR-03`)**：將 `ys_codebase/source/file-space/` 重構為無 `watchdog` 依賴、無 `contributes/{server,agents-workflow}.json` 之極簡 `core.space` 轉發空殼（`dependencies: {"core": ">=1.2.7.4"}`），並於母倉本機環境執行 `remove file-space` 完成退役。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/config/core/contribute.json` | New | 由 `config/file-space/contribute.json` 遷移而來之 `source` 與 `cloud` 空間定義（`entries` + `include` 格式） |
| `ys_codebase/config/file-space/contribute.json` | Delete | 舊專案空間設定檔移除 |
| `ys_codebase/config/agents-workflow/snippets/project_role.md` | Modify | 更新母倉核心模組清單與過渡說明 |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | `ScanDiffDetail.dirty_files` 修正為 `self.added \| self.modified`、單一短名查詢正規化為 `<owner>/<name>`、顯式 `storage_root` 鎖檔目錄隔離 |
| `ys_codebase/source/core/core/space/providers.py` | New | 實作 `get_registered_file_spaces_table` 與 `get_knowledge_db_spaces` 動態表格生成 |
| `ys_codebase/source/core/core/space/__init__.py` | Modify | 匯出 `get_registered_file_spaces_table` 與 `get_knowledge_db_spaces` |
| `ys_codebase/source/core/contributes/agents-workflow.json` | Modify | 接管註冊 `FILE_SPACE_REGISTERED_TABLE` token 與 `computed` 注入 |
| `ys_codebase/source/core/assets/config_guide.md` | Modify | 納入 `config/core/contribute.json` 空間設定與 `__@{FILE_SPACE_REGISTERED_TABLE}__` |
| `ys_codebase/source/core/assets/usage_guide.md` | Modify | 納入 `yscb fs` / `yscb file-space` 標準指令速查 |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | 移除過渡期對外部同名模組的避讓邏輯 |
| `ys_codebase/source/core/core/installer.py` | Modify | 從預設 `candidate_mods` 移除 `"file-space"` |
| `ys_codebase/source/core/scripts/migrations/1.2.7.x.py` | Modify | 新增 `_migrate_legacy_file_space_config` 自動轉換合併 `config/file-space/contribute.json` 至 `config/core/contribute.json` |
| `ys_codebase/source/core/tests/test_space.py` | Modify | 更新 CLI 路由測試並新增 `providers` 與 `1.2.7.x.py` 空間組態自動遷移測試 |
| `ys_codebase/source/core/tests/test_platform.py` | Modify | 測試夾具移除舊 `file-space` 耦合 |
| `ys_codebase/source/core/tests/test_validator.py` | Modify | 測試夾具更新為 `$SpaceDef` |
| `ys_codebase/source/agents-workflow/contributes/core.json` | Modify | 新增 `spaces`（`docs` 與 `plans`）定義 |
| `ys_codebase/source/agents-workflow/contributes/file-space.json` | Delete | 舊空間貢獻檔移除 |
| `ys_codebase/source/agents-workflow/contributes/_manifest.md` | Modify | 移除 `file-space.json` 說明 |
| `ys_codebase/source/ast/manifest.json` | Modify | 移除 `"file-space"` 相依，將 `"core"` 設為 `">=1.2.7.4"` |
| `ys_codebase/source/ast/contributes/file-space.json` | Delete | 移除空白舊貢獻檔 |
| `ys_codebase/source/ast/contributes/_manifest.md` | Modify | 移除 `file-space.json` 紀錄 |
| `ys_codebase/source/ast/contributes/core.json` | Modify | 更新描述文字為 `core.space` |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | `Mode A` 全面切換至 `core.space` (`SpaceRegistry`, `SpaceScanner`, `SpaceConfig`, `consume_diff`, `reset_cursor`) |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | `Mode A` 全面切換至 `core.space` (`SpaceRegistry`, `SpaceScanner`, `SpaceConfig`, `SpaceFileEntry`) 與短名映射 |
| `ys_codebase/source/ast/ast_engine/resolver.py` | Modify | `SnippetExtractor` 對齊 `SpaceRegistry.resolve_file_path` |
| `ys_codebase/source/ast/scripts/cli.py` | Modify | 切換為 `from core.space import SpaceNotFoundError` |
| `ys_codebase/source/ast/scripts/hook.core.py` | New | 由 `hook.file-space.py` 遷移並切換至 `from core.space import consume_diff` |
| `ys_codebase/source/ast/scripts/hook.file-space.py` | Delete | 移除舊 Hook 檔案 |
| `ys_codebase/source/ast/scripts/migrations/1.0.1.x.py` | New | 升級時清理舊格式 `ast` 消費者游標 |
| `ys_codebase/source/ast/README.md` | Modify | 更新依賴與架構說明為 `core.space` |
| `ys_codebase/source/ast/assets/config_guide.md` | Modify | 更新空間組態說明為 `config/core/contribute.json` |
| `ys_codebase/source/ast/tests/test_ast_engine.py` | Modify | `Mode A` 切換至 `core.space` 與 `hook.core.py` |
| `ys_codebase/source/ast/tests/test_provisioner_and_jit.py` | Modify | `Mode A` 切換至 `core.space` 與 `hook.core.py` |
| `ys_codebase/source/knowledge-db/manifest.json` | Modify | 移除 `"file-space"` 相依，更新 `onboarding` 為 `config/core/contribute.json` |
| `ys_codebase/source/knowledge-db/contributes/_manifest.md` | Modify | 更新說明為 `core.space` |
| `ys_codebase/source/knowledge-db/knowledge_db/providers.py` | Modify | 委派至 `core.space.providers.get_knowledge_db_spaces` |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | `Mode A` 全面切換至 `core.space` (`SpaceRegistry`, `SpaceScanner`, `SpaceNotFoundError`, `SpaceError`) |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | `Mode A` 全面切換至 `core.space` |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | `SnippetExtractor` 對齊 `SpaceRegistry.resolve_file_path` |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 更新註解為 `core-space-watcher` |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | 切換至 `from core.space import SpaceNotFoundError` |
| `ys_codebase/source/knowledge-db/scripts/hook.core.py` | New | 由 `hook.file-space.py` 遷移並切換至 `from core.space import ScanDiffResult, consume_diff` |
| `ys_codebase/source/knowledge-db/scripts/hook.file-space.py` | Delete | 移除舊 Hook 檔案 |
| `ys_codebase/source/knowledge-db/scripts/migrations/1.2.1.x.py` | New | 升級時清理舊格式 `knowledge-db` 消費者游標 |
| `ys_codebase/source/knowledge-db/README.md` | Modify | 更新為 `core.space` 與 `config/core/contribute.json` |
| `ys_codebase/source/knowledge-db/assets/config_guide.md` | Modify | 更新為 `config/core/contribute.json` |
| `ys_codebase/source/knowledge-db/assets/usage_guide.md` | Modify | 更新為 `core.space` |
| `ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md` | Modify | 更新為 `core.space` |
| `ys_codebase/source/knowledge-db/tests/test_engine.py` | Modify | `Mode A` 切換至 `core.space` |
| `ys_codebase/source/knowledge-db/tests/test_file_space.py` | Modify | `Mode A` 切換至 `core.space` |
| `ys_codebase/source/knowledge-db/tests/test_hot_reload.py` | Modify | `Mode A` 切換至 `core.space` 與 `hook.core.py` |
| `ys_codebase/source/knowledge-db/tests/test_schema.py` | Modify | `Mode A` 切換至 `core.space` |
| `ys_codebase/source/knowledge-db/tests/test_self_healing.py` | Modify | `Mode A` 切換至 `core.space` |
| `ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | `Mode A` 切換至 `core.space` 與 `hook.core.py` |
| `ys_codebase/source/gdrive-support/manifest.json` | Modify | 移除 `"file-space"` 相依 |
| `ys_codebase/source/gdrive-support/contributes/_format.json` | Modify | 更新描述文字為 `core.space` |
| `ys_codebase/source/gdrive-support/contributes/_manifest.md` | Modify | 更新描述文字為 `core.space` |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | Modify | `Mode A` 切換至 `core.space.SpaceRegistry` (`entries`, `large_file_threshold_mb`, `iter_space_files`) |
| `ys_codebase/source/gdrive-support/gdrive_support/service.py` | Modify | `Mode A` 切換至 `from core.space import subscribe` |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | Modify | 對齊 `space_registry` / `file_space_manager` 介面 |
| `ys_codebase/source/gdrive-support/assets/usage_guide.md` | Modify | 更新為 `core.space` |
| `ys_codebase/source/gdrive-support/assets/skills/gdrive-local-ops/SKILL.md` | Modify | 更新為 `core.space` |
| `ys_codebase/source/gdrive-support/tests/test_atomic_api_and_config.py` | Modify | `Mode A` 切換至 `core.space` |
| `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py` | Modify | `Mode A` 切換至 `core.space` |
| `ys_codebase/source/file-space/manifest.json` | Modify | 升級為棄用空殼組態（`core >=1.2.7.4`、移除 `watchdog`、標註更新 `core` 後執行 `remove file-space`） |
| `ys_codebase/source/file-space/contributes/server.json` | Delete | 移除舊 `file-space-watcher` 註冊 |
| `ys_codebase/source/file-space/contributes/agents-workflow.json` | Delete | 移除舊 `FILE_SPACE_REGISTERED_TABLE` 註冊（已由 `core` 接管） |
| `ys_codebase/source/file-space/skills/how-to-yscb/file_space_guide.md` | Delete | 移除舊導引片段 |
| `ys_codebase/source/file-space/file_space/__init__.py` | Modify | 轉發至 `core.space` |
| `ys_codebase/source/file-space/file_space/exceptions.py` | Modify | 轉發 `core.space.exceptions` |
| `ys_codebase/source/file-space/file_space/schema.py` | Modify | 轉發 `core.space` 資料結構 |
| `ys_codebase/source/file-space/file_space/manager.py` | Modify | 輕量適配轉發至 `core.space.SpaceRegistry` |
| `ys_codebase/source/file-space/file_space/scanner.py` | Modify | 輕量適配轉發至 `core.space.SpaceScanner` |
| `ys_codebase/source/file-space/file_space/service.py` | Modify | 輕量轉發 `core.space.watcher` |
| `ys_codebase/source/file-space/file_space/providers.py` | Modify | 轉發 `core.space.providers` |
| `ys_codebase/source/file-space/scripts/cli.py` | Modify | 轉發至 `core` 之 `file-space` CLI 處理器並印出棄用提示 |
| `ys_codebase/source/file-space/README.md` | Modify | 標註棄用與 `remove file-space` 升級指引 |
| `ys_codebase/source/file-space/tests/` | Modify | 收斂為驗證空殼轉發契約之精簡測試集 |
| `docs/README.md` | Modify | 更新系統知識庫導航表（`file-space` 併入 `core`） |
| `docs/core/README.md` | Modify | 增補 `config/core/contribute.json` 空間組態與遷移說明 |
| `docs/ast/README.md` | Modify | 更新為 `core.space` 與 `hook.core.py` |
| `docs/knowledge-db/README.md` | Modify | 更新為 `core.space` 與 `hook.core.py` |
| `docs/gdrive-support/README.md` | Modify | 更新為 `core.space` |
| `docs/file-space/README.md` | Modify | 標註已併入 `core.space` 與退役指引 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `python yscb.py dev check --all`：`9 Total, 9 Passed, 0 Warnings, 0 Failed`
  - `python yscb.py dev test core -q`：`Pass: 267(99.6%), Fail: 0, Skip: 1`
  - `python yscb.py dev test agents-workflow -q`：`Pass: 145(100.0%), Fail: 0, Skip: 0`
  - `python yscb.py dev test ast -q`：`Pass: 37(100.0%), Fail: 0, Skip: 0`
  - `python yscb.py dev test knowledge-db -q`：`Pass: 109(100.0%), Fail: 0, Skip: 0`
  - `python yscb.py dev test gdrive-support -q`：`Pass: 34(100.0%), Fail: 0, Skip: 0`
  - `python yscb.py dev test file-space -q`：`Pass: 18(100.0%), Fail: 0, Skip: 0`
- **實機 UX / 人工驗證**：
  - `UX-01` (`[測試通過]`)：於母倉本機環境及臨時隔離工作區（`/tmp/ys-codebase-ux01-verify`）完成 7 階段全鏈路實機驗證（舊版 `config/file-space/contribute.json` 升級自動轉譯合併至 `config/core/contribute.json`、游標重置、`file-space` 空殼轉發、`remove file-space` 後之 `fs`/`ast`/`knowledge-db`/`kdb search`/`agents-workflow compile` 全指令零殘留運作）。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已交付 | 記錄 `sub_04` 生態系 `Mode A` 全面遷移、`file-space` 空殼化與 `2026_11_06_1020_core_file_space_architecture` 主計畫結案 |
| **中觀 (Meso)** | `docs/core/README.md`, `docs/ast/README.md`, `docs/knowledge-db/README.md`, `docs/gdrive-support/README.md`, `docs/file-space/README.md` | 已交付 | 對齊 `core.space`、`config/core/contribute.json`、`hook.core.py` 與 `file-space` 退役指引 |
| **中觀 (Meso)** | `docs/README.md`, `docs/_project/ARCHITECTURE.md` | 已交付 | 更新全系統知識庫導航表與核心模組拓撲 |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md` | 免更 | 無新增反直覺工程妥協（遵守 DN 防膨脹守門） |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已交付 | 同步更新 `core/space/providers.py`、`scripts/migrations/`、`hook.core.py` 與各模組 Docstrings |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
refactor(space): migrate ecosystem modules to core.space and deprecate file-space shell
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
