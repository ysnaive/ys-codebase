# 專案變更歷史 (Changelog)

本檔案記錄 `ys-codebase` 專案的所有高階功能、規範與架構變更。以開發計畫 (Dev Plan) 目錄名稱為版本區分單位。

---

## 2026_08_23_extensibility_reliability_hardening

### Fixed
- **[P0] 下游 `build` 指令崩潰修復**：`build_module()` 之 `dest_path` 於「源碼僅存在於遠端快取 (.yscb_cache)」情境（即標準下游專案）缺少 fallback 分支，導致 `UnboundLocalError`。現回退輸出至本地 `build/`。
- **[P0] `YSCB_MODULE_DIR` 跨模組汙染修復**：`ProjectContext.get_module_dir()` 先前在環境變數存在時無條件回傳該路徑（完全忽略 `module_name` 參數），導致模組 A 執行期查詢模組 B 的目錄/設定時被汙染。現僅於環境變數目錄名稱與目標模組相符時採用。
- **Slot 匹配規則一致性修復**：`SOPSynthesizer.synthesize_sop()` 改用與 `SLOT_PATTERN` 一致的容錯正則匹配插槽（支援 `<!--YSCB_SLOT:x-->` 等空白變體），並於找不到插槽降級附加檔尾時輸出 `[WARN]` 明確提示，消除靜默錯置。
- **`remove` 相依防護真實化**：先前僅硬編碼保護 `core`；現依各已安裝模組 `manifest.json` 宣告之 `dependencies` 執行真實相依阻斷（`--force` 可越過）。
- **`version check-update` 計數器修復**：修正模組更新計數在 installer 檢查後被重置歸零、導致「發現更新」與「無待更新項目」同時輸出的自相矛盾訊息。
- **指令與文檔一致性**：`pull` / `remove` 新增 argparse 別名 `update` / `uninstall`（README 與內建 help 先前已宣稱存在但實際未註冊，執行必 exit 2）；`pull` 支援顯式 `--all` 旗標。
- **清除過期測試副本**：移除 `test/yscb_installer.py`、`test/yscb_cli.py`、`test/yscb_config.json`——與根目錄版本號相同 (2.1.0) 但缺少整套互鎖廣播機制的 stale 拷貝（測試實際 import 的是 `ys_codebase/` 版本，該副本為誤留死重量）。

### Added
- **URI Scheme 開放註冊協定 (Contract III)**：`ProjectURI.get_dynamic_schemes()` 動態聚合各模組 `manifest.json` 之 `contributes["core"]["uri_schemes"]` 宣告，core SDK 不再硬編碼 `agents-workflow` 模組名稱；`agents-workflow` 改以宣言式註冊 `plans/archive/docs/sop_ext` 四協議；舊版映射表保留為向後相容 fallback；`project://`、`yscb://` 為保留字不可覆蓋。
- **IDE Adapter 註冊表與 per-adapter 快取**：`cli.py` 新增 `IDE_ADAPTERS` 開放擴充點與泛用 `generate_ide_commands(adapter)`；`IDECacheTracker` 改為每個 adapter 獨立 manifest (`.yscb_cache/ide_manifest_<adapter>.json`)，杜絕未來多 IDE 並存時互刪產物，並自動平滑遷移舊版全域 manifest。
- **`installer rollback` 指令**：`rollback <module> [--list] [--to <備份名稱>]` 自 `.yscb_cache/backup/` 快照一鍵還原模組並同步回寫安裝紀錄；快照新增保留策略（每模組保留最近 5 份）。
- **`installer status` 孤兒偵測**：新增「實體狀態」欄位，模組目錄遺失時標記 `[MISSING]` 並提示修復指令。
- **SOP Patch 決定性疊加順序**：`sop_patches` 支援選填 `priority` 欄位（預設 100，越小越先注入），依 `(priority, 模組名稱)` 穩定排序；`get_contributions()` 與 `get_all_installed_manifests()` 改為名稱排序掃描，跨平台結果具決定性。
- **GitHub Actions CI**：新增 `.github/workflows/ci.yml`，於 ubuntu/windows × Python 3.11/3.12 矩陣自動執行全量回歸套件（含下游沙盒 E2E）。
- **強化回歸測試套件**：新增 `test/test_hardening.py` (HT-01~HT-07)，覆蓋上述全部修復與版本 SSOT 同步防護。

### Changed
- **Hook 執行逾時防護**：`_migration.py` (600s)、`_installed.py` / `_uninstall.py` (120s)、`_on_modules_changed.py` (120s)、自訂 `build.py` (600s)、Extension Verifier (120s) 與全部 git 子程序 (600s) 均加上 timeout，杜絕無限掛起；遷移逾時視同失敗並觸發快照回滾。
- **錯誤診斷體驗**：頂層錯誤訊息附帶例外類別名稱，並支援 `YSCB_DEBUG=1` 環境變數輸出完整堆疊。
- **版本號 SSOT 收斂**：`yscb_core.__version__` 改為自 `manifest.json` 動態讀取，消除三處硬編碼版本號發散風險。
- **版本升級**：`core` v2.1.0 ➔ v2.2.0、`agents-workflow` v1.0.1 ➔ v1.1.0、起手腳本 v2.1.0 ➔ v2.2.0。

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
