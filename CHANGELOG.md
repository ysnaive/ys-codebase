# 專案變更歷史 (Changelog)

本檔案記錄 `ys-codebase` 專案的所有高階功能、規範與架構變更。以開發計畫 (Dev Plan) 目錄名稱為版本區分單位。

---

## 2026_08_23_1112_module_interlock_system

### Added
- **安裝期生命週期連動廣播機制 (Contract I)**：於 `yscb_installer.py` 的 `ModuleManager` 實作 `_broadcast_modules_changed(changes)`，在整批 `install`、`pull`、`remove` 完成後單次派發 `action:module` 變更清單至已安裝模組之 `scripts/_on_modules_changed.py`。`build` 指令嚴格排除廣播。
- **Core SDK 跨模組貢獻查詢通道 (Contract II)**：於 `source/core/scripts/context.py` 實作 `ProjectContext.get_contributions(namespace)` 與 `get_all_installed_manifests()`，為上層模組提供零領域偏見的宣言式貢獻提取通道。
- **SOP Slot 插槽動態注入與標記剝除引擎 (`SOPSynthesizer`)**：建立 `SOPSynthesizer` 類別，支援 `target_slot` 匹配與 `append`/`prepend` 注入，並在具體化輸出時強制透過 `strip_slot_markers()` 100% 正則剝除 `<!-- YSCB_SLOT:... -->` 標記，保證產物純淨。
- **基準指令庫目錄與 Slot 全集植入**：建立 `source/agents-workflow/workflows/commands/` 作為單一事實來源 (SSOT)，並於 `NewPlan.md` (`Phase0`~`Phase7`)、`Review.md` (`Step1`~`Step4`)、`ContextInit.md` (`Step1`~`Step4`) 植入共 16 個標準 Slot 標記。
- **IDE 生成快取與孤兒檔案清理追蹤器 (`IDECacheTracker`)**：於 `source/agents-workflow/scripts/ide_sync.py` 實作快取追蹤器，維護 `.yscb_cache/ide_workflow_manifest.json` 並自動刪除廢棄孤兒指令檔案。
- **雙層 Extension 發現與優先級調度器 (`ExtensionRegistry`)**：於 `source/agents-workflow/scripts/ext_registry.py` 實作雙層調度器，專案根目錄自定義擴充 (`sop_ext://`) 優先覆蓋外掛模組宣告之擴充 (`contributes.sop_extensions`)，並升級 `ext list` 終端輸出為雙層來源標籤排版。
- **動態合成與環境感知 Hook (`_on_modules_changed.py`)**：建立 `agents-workflow` 生命週期 Hook，接收廣播後具體化合成 `workflows/*.md`，並自動偵測專案環境完成 IDE 工作流無感即時同步。
- **連動協定專題手冊與設計筆記**：產出 `docs/AgentsWorkflow/SOP_INTERLOCK_PROTOCOL.md`，並於 `docs/Installer/DESIGN_NOTES.md` 追加 `DN-07` (build 排除鐵律) 與 `DN-08` (Slot 標記剝除防呆)。
- **連動系統全量測試套件**：建立 `test/test_interlock.py`，覆蓋 FT-01~08、ET-01~08、PT-01 等 17 項功能、邊界與效能測試。

### Changed
- **模組空間定義昇華**：`modules/` 定義正式由「從遠端 build 抓取的運行產物」昇華為「於本地和相關模組相依連動後的具體化運行版本」。
- **SOP 基準庫與發布庫結構拆分**：`source/agents-workflow/workflows/` 下移除了 9 份舊版靜態指令，統一收斂至 `commands/` 基準庫管理。
- **CLI 工具鏈全面升級**：升級 `generate_antigravity_ide_commands()`、`ext list`、`ext show` 與 `verify_plan.py` 支援雙層來源調度與跨模組驗證腳本執行。

---

## 2026_08_23_1017_versioning_system

### Added
- **SemVer 2.0.0 與 VersionConstraint 引擎**：於 `source/core/scripts/semver.py` 實作純標準庫語意化版本引擎，支援完整優先級富比較、預發布比對、剛性 bump 以及 `^, ~, >=, <=, ==, !=, *` 相依約束匹配。
- **鏈式線性增量遷移框架 (`MigrationRunner`)**：於 `source/core/scripts/migration.py` 實作 `@runner.step("X.Y.x")` 裝飾器與 $O(N)$ 線性代際遷移，支援跨版本平滑升級與失敗自動回滾。
- **五階段事務性安全升級流水線**：於 `yscb_installer.py` 實作 Pre-flight 相依約束校驗、舊版快照備份至 `.yscb_cache/backup/`、2×2 專案配置增量深層合併 (`deep_merge`)、本地配置唯讀保留、`AGENTS.md` 標記軟合併與例外自動 `_rollback_snapshot()` 還原。
- **統一 CLI 版本管理工具鏈**：新增 `python yscb_cli.py version <status|check|check-update|bump>`，提供三態版本狀態矩陣、相依相容性檢查、一鍵更新掃描與版本遞進。
- **Installer 單檔自舉升級 (`installer self-update`)**：提供 `python yscb_cli.py installer self-update [--force]`，採用 Windows `.tmp` 原子安全覆蓋，徹底規避執行中檔案鎖定問題。
- **抽象外掛式 Extension Verifier Hook**：加固 `verify_plan.py`，動態掃描並調用 `sop_ext://<ext>_verify.py`，建立專案特化 `dogfooding_pipeline_verify.py` 守門外掛。
- **全量主題與設計筆記手冊**：產出 `docs/Core/SEMVER_ENGINE.md`、`docs/Core/MIGRATION_FRAMEWORK.md`、`docs/Installer/UPGRADE_PIPELINE.md`、`docs/AgentsWorkflow/EXTENSION_VERIFIERS.md`，並於 `docs/Installer/DESIGN_NOTES.md` 追加 `DN-04 ~ DN-06`。

### Changed
- **模組版本號正式升級**：`core` 升級至 `v2.1.0`，`agents-workflow` 升級至 `v1.0.1`，核心起手腳本 `yscb_installer.py` 與 `yscb_cli.py` 升級至 `v2.1.0`。
- **相依宣告語法支援 SemVer 約束**：`agents-workflow/manifest.json` 相依宣告改為 `core >= 2.0.0`，安裝器拓撲解析自動提取模組名稱與校驗約束。

---

## 2026_08_23_0055_architecture_migration

### Added
- **Dogfooding 自引用 SOP 擴充**：新增 `extensions/dogfooding_pipeline_ext.md` 與源碼模板，定義 Stage 1~4（源碼空間 ➔ build ➔ regression ➔ install）全流程 Checkpoint。
- **Dogfooding 行為準則公理**：於 `AGENTS.md` 專案特化規範（第 4 節）寫入三層空間權限矩陣與標準四步閉環流水線。
- **知識庫定式工具庫指南**：於 `DocumentationStandards.md` 追加第 7 節「知識庫定式維護工具鏈」(`docs init/new-topic/audit`)。

### Changed
- **SOP NewPlan 雙星伴隨初始化**：修改 `NewPlan.md` Phase 0 步驟 1/2，強制規定開立計畫目錄時必須【同時】建立 `P00_semantic_requirements.md` 與 `changelog.md`，徹底消除時序滯後問題。
- **定式工具鏈指令聯動**：更新 `Review.md` 步驟 2 引入 `ext list/show`、步驟 3 引入 `docs audit`；更新 `AGENTS.md` 與 `AGENTS.template.md` 補齊定式作業 CLI 清單 (`<verify|scan|search|archive|docs|ext>`)。
- **知識庫手冊路徑更新**：更新 `docs/AgentsWorkflow/DETERMINISTIC_SCRIPTS.md` 與 `docs/_project/CONTRIBUTING.md` 為最新 `python yscb_cli.py` 路由器指令語法。

### Fixed
- **verify_plan.py 檢查盲區加固**：加固 `verify_plan.py`，移除 `changelog.md` 略過邏輯，改為嚴格檢查存在性與 Markdown 標題/表格格式。
- **CLI discover_all_extensions 語意 URI 解析修復**：修正 `cli.py` 中直接拼接 `Path(ext_setting)` 導致 `project://` URI 解析錯誤問題，統一改為調用 `get_extensions_dir` 解析。
