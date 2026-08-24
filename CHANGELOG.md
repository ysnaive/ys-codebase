# 專案變更歷史 (Changelog)

本檔案記錄 `ys-codebase` 專案的所有高階功能、規範與架構變更。以開發計畫 (Dev Plan) 目錄名稱為版本區分單位。

---

## 2026_08_23_2030_architecture_refactor

### Added
- **超薄無狀態宿主 (Ultra-Thin Host `yscb.py`)**：100% Python 標準庫原生實現，體積縮減至百餘行，僅負責路徑定位、最小自舉與動態命令轉發，徹底擺脫單檔膨脹與自引用死鎖。
- **Core 微內核基礎設施模組 (`module:core`)**：
  - **First-Class VFS SDK (`core.uri`)**：原生支援語意 URI 讀寫、目錄操作、最長前綴匹配與原子安全寫入。
  - **`AtomicEngine` 12 大原子操作生命週期**：將系統狀態變更分解為 `INIT`, `DOWNLOAD`, `DELETE`, `REGISTER`, `UNREGISTER`, `SOLVE_DEPS`, `PREPARE`, `RELOAD`, `FETCH`, `SNAPSHOT`, `RESTORE_SNAPSHOT`, `DISPATCH_CLI`。
  - **套件管理器 (`core.installer`)**：提供 `install`, `update`, `remove`, `list`, `status`, `rollback`, `reload` 完整套件生命週期。
  - **5 來源依賴注入聚合器 (`core.contributes`)**：支援 Manifest、指向性 JSON、專案與本地層級宣告式能力注入，產出中介層快照至 `cache://` 加速查表。
- **Dev 開發者工具箱模組 (`module:dev`)**：
  - **模組腳手架 (`dev create`)**：一鍵生成符合規範之模組標準骨架與測試模板。
  - **靜態合規檢查器 (`dev check`)**：驗證 Manifest SemVer 規範、CLI 進入點語法與 `.yscbignore`。
  - **純淨套件打包器 (`dev build`)**：自動排除 `tests/` 與 `.yscbignore`，產出純淨版本化套件包並注入 `built_at` 時間戳記。
  - **沙盒測試引擎 (`dev test`)**：提供 `YSCBTestCase` 隔離沙盒、Auto-Contract 動態契約合成與兩階段測試執行。
- **14 組自宣告注入語意 URI 協議**：
  - 核心協議：`yscb://`, `mirror://`, `temp://`, `snapshot://`, `module.root://`, `module://`, `config.root://`, `config://`, `cache.root://`, `cache://`。
  - 開發協議：`module.source.root://`, `module.source://`, `module.build.root://`, `module.build://`。
- **三階測試指令體系與遞迴語意解耦 (`sub_10`)**：
  - `dev op-mksb`：純沙盒建造工廠，支援指定路徑與 `temp://sandbox_{timestamp}/` 動態微秒命名。
  - `dev op-test`：純原地單元測試執行器（100% 零沙盒、零遞迴），支援 `--type=<logic|host_cli|network>` 與 `-k` 遞迴過濾。
  - `dev test`：高階組合門面，自動建造沙盒 ➔ 進入沙盒執行 ➔ 通過後自動銷毀清理。
- **完全對標微型虛擬環境 (`SandboxProvisioner`) (`sub_10`)**：
  - 鋪設 `mock_downstream_project/`、`host_env/`（含 `yscb.py`, `yscb.config.json` 與 `modules/`）、`mock_provider/` 三大標準子空間。
  - 完整繼承父層已安裝模組與配置，消除測試環境混血狀態，嚴格維持 `yscb.py` 僅調用 `modules/` 之單一真相來源。
- **模組測試前置自治 Hook (`scripts/hook.dev.py`) (`sub_10`)**：
  - 各模組提供 `on_test_setup` 與 `on_test_teardown`，隨 `build` 套件打包發布，`core` 自動配置沙盒 `project_root` 解除 `!undefined`。
- **精準命名空間 Hook 對接體系 (`scripts/hook.{emit_module}.py`)**：
  - 模組以發起端命名對接檔案（例 `hook.core.py`, `hook.dev.py`），提供 `ExecutionContext` 凍結資料介面與 try-except 例外隔離防護。
- **系統全域知識庫綠地重建 (`docs/`)**：
  - 依據 7 大抽象維度落成 10 大標準手冊（全域地圖、核心規範、Core 架構、URI 協議、Hook 手冊、Dev 工具箱、測試指南、設計註記 `DN-01~03` 及專案首頁）。

### Changed
- **`project://` 顯式配置與零 Fallback 鐵律**：`project_root` 預設為 `!undefined`，未定義時精準拋出 `ValueError` 顯式阻斷，杜絕隱式猜測與環境路徑漂移。
- **2x2 組態空間顯式化**：將原 `.config/` 隱藏目錄導正為顯式之 `config/` 專案目錄（受 Git 追蹤資產）。
- **中介快照空間純淨化**：框架衍生之 `contributes.merged.json` 導正至 `cache://`（即 `.cache/`，受 Git 忽略），並實施空檔抑制機制。
- **套件倉庫空間追蹤**：本機 Provider 套件庫 `ys_codebase/build/` 正式受 Git 追蹤以利開箱自舉。
- **版本升級**：`core` 升級至 `1.0.0`，`dev` 升級至 `1.0.0`，超薄宿主 `yscb.py` 升級至 `1.0.0`。

### Fixed
- **隔離歷史干擾**：舊版代碼、舊起手腳本與歷史工作流全數移至 `.quarantine/` 封存。
- **[Critical] 宿主組態與專案空間徹底解耦 (BUG-01, BUG-02)**：`AtomicEngine` 內部所有對 `yscb.config.json` 的讀寫、清冊維護與快照還原全面改由 `host_dir` 實體路徑執行，徹底與 `project://` 解耦，確保在下游外部專案中執行套件管理時 100% 零阻斷。
- **[Critical] `yscb://` 代碼位置常數確定性自定位 (BUG-03, D-07)**：`yscb://` 解析基準直接由 `core.uri` 的實體檔案位置（`__file__` 往上 3 層）確定性常數計算；宿主 Context 顯式注入；徹底刪除動態爬目錄與 `os.getcwd()` 猜測。
- **Provider `index.json` 版本清冊自動維護 (D-06)**：`dev build` 打包時自動增量更新 `build/{module}/index.json`，支援 SemVer 升序排序與去重。
- **`remove` 反向相依安全阻斷防護 (D-08)**：`cmd_remove` 實作反向依賴掃描，被依賴模組未帶 `--force` 時阻斷移除。
- **相依格式雙向相容與遞迴相依拓撲求解 (D-01, D-02)**：`act_solve_deps` 支援 Dict 與 List 格式雙向相容，實作遞迴依賴分析與循環相依檢測。
- **全量回歸測試守門**：Auto-Contract (6/6) + Custom Persistent Tests (32/32) = **38/38 測試全數 Passed (0.555s)**。

---

## 2026_08_23_sop_template_consistency

### Fixed
- **[Critical] Extension「必跑」自動化稽核死碼修復**：`ext_registry.py` 從未解析 `ext_template.md` 規範定義的 `phase:` frontmatter 欄位，`verify_plan.py` 之 `parse_extensions()` 將每個 Extension 的 `phase` 硬編碼為字面字串 `"All"`，導致 `verify_plan.py` 中「檢查必跑 Extension (trigger: always)」的自動化把關邏輯恆為死碼——無論任何 Phase 文件是否漏宣告 `always` 型擴充皆不會被攔截。已於 `ext_registry.py` 新增 `_normalize_phase()` 將 phase 宣告正規化為大寫 Token 集合並貫通三處 Extension 發現迴圈；`verify_plan.py` 新增 `compute_phase_code()` 正確處理 `FT_plan.md` 的 Token 對應（避免誤推導為 `"FT"` 而永遠比對不到 frontmatter 宣告的 `"FT_plan"`）。已用實際 `dogfooding_pipeline_ext.md` 驗證修復生效。
- **`P05_task.md` 模板缺失補齊**：P00~P04、P06、P07 皆有標準模板可鏡像，唯獨 Phase 5 任務清單（被 `NewPlan.md`、`Continue.md`、`Discuss.md`、`scan_plan_status.py` 四處引用/依賴，`/Continue` 更需解析其 `[x]`/`[ ]` 標記定位斷點）從未有對應模板，違反「全階段文件模板剛性對齊」鐵律。新增 `workflows/templates/P05_task.md`，並將 `NewPlan.md` Phase 5 步驟 1 補上明確模板引用。
- **P03/P06 模板語言中立化**：`P03_api_spec.md` 原整份以真實 C# 語法（`namespace UIToolkit.[Subsystem]`、XML doc、`ArgumentNullException`）示範，`P06_test_plan.md` 原寫死 `dotnet test`，與工具庫「純標準庫、任何下游專案皆可用」定位衝突。已改為語言中立偽代碼並比照 `FT_plan.md` 既有的多語言測試指令範例（`pytest` / `dotnet test` / `npm test` / `cargo test` 等）泛化；`P00_semantic_requirements.md` 中一處貼有 `csharp` 語法標籤但內容實為純中文偽代碼註解的程式碼區塊，亦一併修正為語言中立標籤。
- **決策紀錄 (DR) ID 前綴格式統一**：`NewPlan.md` 定義的 `[REQ:DR-XX]` / `[ARCH:DR-XX]` / `[API:DR-XX]` 格式從未被任何模板實際使用，P01/P02/P03/umbrella_overview 各自使用裸 `DR-01`、P04 使用 `[P01:DR-01]`、FT_plan 使用 `DR-XX` + 獨立分類標籤，四種格式並存且互不相容，破壞可追溯鏈的跨文件唯一性承諾。已統一收斂為 P04 既有先例格式 `[{Phase}:DR-XX]`（Phase 為產出該決策之文件對應 Token，如 `P01`/`P02`/`P03`/`P04`/`FT`/`UMBRELLA`），並同步更新 `NewPlan.md` ID 表、`Discuss.md`、`Continue.md`、`changelog.md` 模板、`AGENTS.template.md` 及全部 6 份會產出 DR 的模板。
- **`scan_plan_status.py` Fast Track 狀態解析脆弱性修復**：Umbrella 與 P00 分支皆用精確比對 `狀態：{st}`，唯獨 Fast Track 分支用裸字串 `if st in content`，正文任何角落偶然出現同名字詞（如 "Reviewing"）即可能誤判狀態。已統一改為與其他分支一致的 Header 精確比對。
- **`master_plan_*.md` 孤兒相容分支澄清**：`scan_plan_status.py` 與 `Continue.md` 仍偵測此舊版/人工遷移專案之相容命名，但沒有任何 SOP 文件教 Agent 主動建立此檔名。已於原始碼註解與 `Continue.md` 表格明確標註其為「僅相容偵測、Agent 不應主動建立」，避免未來維護者誤解為與 `umbrella_overview.md` 對等的兩種標準選項。

### Added
- **強化回歸測試套件擴充 (HT-08~HT-11)**：新增 `test/test_hardening.py` 測試涵蓋 Extension phase 死碼修復（含正向攔截與負向不誤觸發兩案例）、`_normalize_phase()`/`compute_phase_code()` 正規化邏輯、`P05_task.md` 模板存在性與必要欄位、`scan_plan_status.py` Fast Track 精確 Header 比對防迴歸。

### Changed
- **版本升級**：`agents-workflow` v1.1.0 ➔ v1.2.0。

## 2026_08_23_1505_fix_yscb_root_path_isolation

### Fixed
- **[P0] `paths.yscb_root` 工具庫與專案空間 100% 物理隔離**：重構 `ProjectContext.get_yscb_root()`、`get_module_dir()` 與 `get_module_cache_dir()`，徹底消除 `yscb_tools` 子目錄配置時殘留專案根目錄 `modules/` 的空間污染問題。
- **[P0] 遠端 Git 倉庫快取與模組執行期快取目錄混雜隔離 ([ARCH:DR-CACHE-02])**：透過衍生 Fast Track 子計畫 `sub_01_cache_mirror_isolation`，將 `GitRemoteClient.cache_dir` 預設路徑隔離收斂至 `yscb://.yscb_cache/mirror/`，杜絕 Git 鏡像同步失敗觸發 `sync_cache(force_refresh=True)` 時誤刪 `modules/` 快取與 `backup/` 快照的重大缺陷。

### Added
- **五層語意 URI 協議體系與統一路徑轉換器 (`ProjectURI`)**：實作 `project://`, `yscb://`, `cache://<module>/`, `storage://<module>/`, `temp://` 及動態擴充協議，支援 Windows/POSIX 雙向正規化、最長前綴匹配 (LPM) 反向轉換、沙盒圍欄安全防護 (Chroot Guard) 與高階 Direct I/O 操作門面。
- **極致記憶體快取與 Fast-Path 系統呼叫避障 (3.8 µs/次)**：`ProjectURI.resolve()` 採用預編譯正規表達式與純 Python 快速通道，避開 Windows 內核系統呼叫開銷，單次解析速度達 3.82 µs（PT-01 10,000 次基準耗時 38.16 ms）。
- **`ConfigManager.resolve_config_uris()` 自動展開**：`ConfigManager.load()` 預設自動遞迴解析字典與陣列中的語意 URI，使模組設定檔能無縫使用 `project://` 或 `cache://` 協定。
- **快取管理終端工具鏈 (`yscb_cli.py cache status / clean`)**：新增 `cache status` 模組快取容量統計表格與 `cache clean <module> [--all]` 清理工具，並於模組卸載 (`remove`) 時自動連動清理快取空間。
- **CLI URI 診斷與健康巡檢工具 (`yscb_cli.py uri check / list / resolve / to-uri`)**：支援全協議健康度診斷、實體路徑逆向轉譯與沙盒逃逸測試。
- **主執行器三位一體公理 ([ARCH:DR-EXEC-01])**：確立 `yscb_config.json`、`yscb_installer.py` 與 `yscb_cli.py` 必須共生於同一目錄，自升級以當前實體路徑為主，其餘受管資產全面錨定 `paths.yscb_root`。
- **全量完備性回歸測試套件**：新增 `test/test_uri_completeness.py` (FT-01~08, ET-01~07, PT-01)，全專案測試覆蓋增至 77/77 項單元/整合測試與下游沙盒 E2E 100% Passed。

### Changed
- **模組快取命名空間升級與自動平滑遷移**：`ide_sync.py` 快取路徑升級為 `cache://agents-workflow/`，啟動時自動將舊版根目錄快取檔案平滑遷移至模組命名空間。
- **版本遞進**：`core` v2.2.0 ➔ v2.3.0、`agents-workflow` v1.1.0 ➔ v1.2.0、`installer` (CLI) v2.2.0 ➔ v2.3.1。

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
