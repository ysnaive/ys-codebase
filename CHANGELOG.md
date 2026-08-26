# 專案變更歷史 (Changelog)

本檔案記錄 `ys-codebase` 專案的所有高階功能、規範與架構變更。以開發計畫 (Dev Plan) 目錄名稱為版本區分單位。

## 2026_08_25_2200_agents_workflow_migration

- **開發標準規範與流程分離重構及 Contributes 文檔建立 (`sub_09_standards_refactor_and_contributes_doc`)**：
  - **標準規範與開發流程資產徹底解耦**：
    - 新增 `AgentsStandards.md`：專門收斂 Agent 通用核心原則、防呆紀律與絕對禁止條款。
    - 重構 `DevelopmentStandards.md`：收斂工作目錄管理、追溯鏈矩陣、模板尋址指針、三大分流矩陣、SOP 0~7 階段流程與 Fast Track 流程。
    - `NewPlan.md` 維持完整載入 `DevelopmentStandards.md` 流程指引。
  - **`AGENTS.md` 精簡軟合併與 Prompt 上下文優化**：
    - `ReleasePublisher` 發布時僅提取極簡版 `AgentsStandards.md` 注入至 `AGENTS.md` 的標記區間，縮減 Prompt 冗餘 Token 60% 以上，100% 保留專案特化工程規範。
  - **專案組態開關落實與預設調整**：
    - `config.project.json` 中 `"release_targets"` 預設改為空陣列 `[]`（無），避免未宣告時主動生成未預期的 IDE 目錄。
    - 完整支援 `enable_agents_md` 與 `enable_project_changelog` 開關控制。
  - **官方 Contributes 規格書建立**：
    - 交付 `source/agents-workflow/contributes.format.md`，完整定義 `core.uri_schemes`、`export`、`token`、`insert`、`release_target` 的欄位型別與使用範例。
  - **全量測試與回歸驗證**：
    - 模組內部單元測試 21/21 100% Passed。
    - 全系統端到端沙盒測試 114/114 100% Ready。
    - 交付 `docs/agents-workflow/README.md` 與 `docs/agents-workflow/user_guide.md`。

- **Plans CLI 工具鏈補齊與舊版功能遷移 (`sub_08_plans_cli_toolchain_migration`)**：
  - **Plans 工具鏈子套件體系 (`agents_workflow.plans`)**：
    - 將舊版 4 大孤立維護腳本（`archive_plan.py`, `scan_plan_status.py`, `search_dev_plans.py`, `verify_plan.py`）完整重構為高內聚子套件，定義自定義例外基底與型別（`PlanNotFoundError`, `PlanFormatError`, `PlanIncompleteError`, `PlanDestinationExistsError`）。
    - 100% 透過 `core.uri.resolve` 解析語意空間（`workflow.plans://`, `workflow.archived://`, `project://`），消除所有硬編碼路徑。
  - **計畫安全歸檔服務 (`PlanArchiver`)**：
    - 實作 4 重安全檢查守門模型（Completed 狀態、全域 CHANGELOG 登載、清理暫時 `handoff.md`、目的地同名防護）。
    - 依據時間戳前綴 `YYYY_MM_` 自動分流至 `workflow.archived://{YYYY}/{MM}/{plan_name}/`；支援 `--force` 放行。
  - **計畫狀態矩陣掃描服務 (`PlanScanner`)**：
    - 專注掃描活躍進行中計畫（明確排除歷史目錄），精確識別 4 大 Track（Umbrella, Fast Track, Full Track, Phase 0）與當前 Phase 狀態，輸出純 ASCII 樹狀縮排清冊。
  - **歷史與決策檢索服務 (`PlanSearcher`)**：
    - 支援 `--dr` 模式正則結構化擷取去重跨計畫決策記錄，相容中英文與 Markdown 列表/標題格式；支援全文程式碼與上下文行檢索，提供 `--year`, `--month`, `--limit` 篩選。
  - **文件合規性與規範稽核服務 (`PlanVerifier`)**：
    - 稽核 Markdown 是否殘留 `<!-- AGENT_GUIDANCE -->` 模板指引註解；檢查 Blockquote Header 元數據（`功能名稱`, `建立日期`, `狀態`）齊備性；遞迴稽核 `sub_*` 子計畫目錄。
  - **CLI 路由派發與平鋪別名 (`scripts/cli.py`)**：
    - 實作 `agents-workflow plan <archive|status|search|verify>` 路由，並提供 `plan-archive`, `plan-status`, `plan-search`, `plan-verify` 雙軌別名支援。
    - 內建 Windows 控制台 UTF-8 安全轉碼保護與純 ASCII 格式渲染，徹底消除編碼崩潰。
  - **全量測試與回歸驗證**：
    - 模組內部單元測試 20/20 100% Passed。
    - 全系統端到端沙盒測試 111/111 100% Ready。
    - 交付 `docs/agents-workflow/README.md` 與 `docs/agents-workflow/user_guide.md`。

## 2026_08_26_1747_core_dev_refinement

- **Dev 模組發布強制覆蓋模式與 release-git 智慧略過 (`sub_03_dev_release_force_override`)**：
  - **發布強制覆蓋模式 (`--force` / `-f`)**：
    - 為 `dev release`、`dev release-check` 與 `dev release-git` 擴充 `--force` 旗標支援。
    - 剛打包發布發現文檔/註解小瑕疵時，允許原地覆蓋同名 `<ver>.zip` 產物並同步更新 `release/<mod>/index.json`，免被迫 bump revision 造成版本膨脹。
    - **Gate 2 / Gate 3 放行邊界**：`force=True` 時放行 Gate 2 覆蓋與 Gate 3 同版本（`target == highest`）修訂；但若版本小於歷史舊版本（`target < highest`），依然嚴格拋出 `VersionRollbackError` 阻斷。
  - **`dev release-git` 智慧感應機制**：
    - 自動感應目標版本是否已在庫：尚未發布則打包，已發布且無 force 自動略過打包步驟直接接續 Local Git Commit & Tag，已發布且傳入 force 則強制重新打包覆蓋並更新 tag。
  - **全量測試與回歸驗證**：
    - 模組單元測試 29/29 100% Passed。
    - 全系統端到端沙盒測試 113/113 100% Ready。
    - 交付 `docs/dev/README.md` 與 `docs/dev/user_guide.md`。

- **Dev 模組發布與驗證工具鏈重構 (`sub_02_dev_release_verification_refactor`)**：
  - **建置與純淨發布職責分離 (`Builder` & `Releaser`)**：
    - `dev build`：移除 `--clean` 選項（打包前一律自動物理清空目標 `build/<mod>/` 目錄），100% 完整保留 `tests/` 與開發檔案，產出 `<ver>.build.zip` 並更新 `build/<mod>/index.json`。
    - `dev release`：重構為純淨打包器（嚴格排除 `tests/` 與 `.yscbignore`），產出 `release/<mod>/<ver>.zip`；移除舊版冗餘的 bump 選項，與 `build` 對標極簡簽名。
  - **發布產物時序滑動窗口與跨三元組收斂演算法 (`3-Revision Retention Policy`)**：
    - 同三元組 `X.Y.Z` 依時序保留至多 3 份最新 Revision zip，第 4 份及更早者自動物理淘汰。
    - 跨三元組升級時，所有歷史舊三元組自動收斂僅保留最後最高 1 份 Revision zip，徹底消除歷史殘留。
    - 以磁碟真實存在的 zip 檔案為唯一事實來源 (SSOT) 同步生成 `release/<mod>/index.json`，已被物理刪除的舊 Revision 自動自清冊排除。
  - **3-Gate 發布品質守門閘門 (`3-Gate Verification`)**：
    - Gate 1 (靜態合規性)：Manifest 格式完整性與 `scripts/cli.py` 語法/進入點存在性。
    - Gate 2 (版本不可變性 - Immutability)：檢查四元版本庫是否已存在同名 zip，重複發布拋出 `ReleaseVersionExistsError` 阻斷。
    - Gate 3 (版本單調遞增 - Monotonicity)：待發布版本號必須嚴格大於同三元組在庫最高 revision，防止倒退，拋出 `VersionRollbackError` 阻斷。
  - **版本遞增、預檢與安全流水線 CLI 工具鏈 (`scripts/cli.py`)**：
    - 實作 `dev bump-[major|minor|patch|revision] <mod>`：單向遞增模組 `manifest.json` 版本號。
    - 實作 `dev release-check <mod>`：獨立執行 3-Gate 發布就緒預檢（明確阻斷 `--all`）。
    - 實作 `dev release-git <mod> "<msg>"`：依序執行 `test` ➔ `release-check` ➔ `release` ➔ 本地 `git commit & tag`（🚨 嚴禁遠端 push）。
  - **測試流水線前置自動建置 (`Tester`)**：
    - `dev test` 預設自動前置執行 `dev build`，構建失敗立即阻斷；支援 `--no-build` 旗標跳過前置打包直接跑測。
  - **全量測試與回歸驗證**：
    - 新增專用測試套件 `test/test_dev_toolchain_refactor.py` (15/15 Passed)。
    - 全系統沙盒端到端測試 109/109 全數通過 (100% Ready)。

- **模組資料管理相關 URI 協議釐清與遷移 (`sub_01_module_data_uri_refactor`)**：
  - **方案 B：全量 Root 化與 `@/` 自省語法模型 (`core.uri`)**：
    - 徹底廢除全系統所有 `*.root://` 協議（`storage.root`, `cache.root`, `config.root`, `module.root`, `module.source.root`, `module.build.root`, `module.release.root`, `module.mirror.root`）與 `temp://` 協議，協議庫精簡 50%，確立 8 大清晰正交標準協議。
    - 支援顯式跨模組尋址 `{scheme}://{module}/{path}` 與當前模組自省語法 `{scheme}://@/{path}`，無模組上下文調用 `@/` 時拋出結構化 `UndefinedModuleContextError`。
    - 內建舊協議 DeprecationWarning 向下相容轉向與路徑穿越 (`..`) 沙盒逃逸防護。
  - **模組資料三位一體與生命週期治理 (`core:remove --purge`)**：
    - 確立 `storage://` (持久化/Git 追蹤)、`config://` (專案設定/Git 追蹤)、`cache://` (暫存快取/Git 忽略) 之三位一體原則與 Git 版本控制策略。
    - 實作模組標準卸載自動清空 `cache://{module}/` 並保留持久資料；新增 `--purge` 旗標支援物理銷毀 `storage`、`config` 與 `cache`。
  - **開發工具鏈與測試沙盒遷移 (`dev`)**：
    - 測試沙盒環境全面自 `temp://` 遷移至 `cache://dev/sandbox/` (`.cache/dev/sandbox/`)，測試完畢自動乾淨銷毀。
    - `builder.py`、`releaser.py`、`checker.py` 等工具鏈全面升級方案 B 協議。
  - **發布清冊錯誤路徑修復與歷史清理 (`agents-workflow`)**：
    - 修復發布清冊至 `storage://@/release_manifest.json` (`storage/agents-workflow/release_manifest.json`)，根除雙重嵌套缺陷，物理清理歷史遺留之 `storage/core/agents-workflow/` 與 `.temp/`。
  - **全量回歸驗證**：
    - 全專案 110/110 自動化測試全數通過 (100% Ready)。

## 2026_08_25_2200_agents_workflow_migration

- **佔位符解析管線優化、三層 URI 重映射與多環境原子發布 (`sub_07`)**：
  - **兩階段 6 步語意編譯發布流水線 (`ArtifactCompiler` & `ReleasePublisher`)**：
    - 徹底廢棄模組安裝目錄原 `exports/` 殘留目錄，將 Stage 1 內容佔位符展開物化寫入 `cache.root://agents-workflow/resolved_contents/` 微內核快取中繼。
    - Stage 2 依啟用之 Release Targets 建立發布拓撲映射表，動態轉譯 `__#{uri}__` 為相對於落地檔案之本機實體相對路徑 (`os.path.relpath`)。
  - **三層 URI 重映射階層演算 (3-Tier Resolution)**：
    - Tier 1: 本次發布拓撲表 (Deployment Map) ➔ 精確計算相對路徑。
    - Tier 2: Core 專案級語意協議 (`project://`, `docs://`, `plans://`) ➔ 調用 `core.uri.resolve` 計算相對路徑。
    - Tier 3: 未知/未決協議安全降級原樣輸出並發出警告。
  - **消除 Agent 模板尋址盲區**：
    - 於 `DevelopmentStandards.md` 與 `AGENTS.md` 中全面注入標準模板之語意 URI 引用指針，自動轉譯為有效跳轉路徑（如 `../templates/P00_semantic_requirements.md`、`.agents/templates/...`），徹底根除 Agent 模板幻覺。
  - **`release_target` Contributes 體系與純文字/陣列 Header 巨集插值**：
    - 在模組 `manifest.json` 支援宣告 `release_target`（如 `antigravity`），定義 `projections` 與 Header 模板。
    - 支援 `{export.description}`, `{export.name}`, `{target.name}` 等巨集插值，徹底告別 YAML 格式綁定。
  - **4 步原子發布交易與孤立檔案精確清理**：
    - 基於 `storage://agents-workflow/release_manifest.json` 實現「過往清理 ➔ 提前解算防污染 ➔ 持久紀錄 ➔ 目錄落地與 `AGENTS.md` 軟合併」原子交易保證。
  - **完整 CLI 指令體系實裝**：
    - 實作 `python yscb.py agents-workflow release`、`release-target --list`、`release-target --add <t>`、`release-target --remove <t>`。

- **Contributes 擴充支援 Computed Token 與 `code.func://` 函式定位協議 (`sub_06`)**：
  - **`code.func://` 符號定位協議 (`core.symbols`)**：
    - 建立全專案標準的程式碼函式與符號定位協議：`code.func://<module>/<subpath>:<function_name>`。
    - 實作雙軌動態載入器（Package Import + VFS 檔案 Spec 載入），支援 Zip 模組與源碼開發環境、命名空間隔離與 Callable 快取。
  - **Contributes Insert 支援 `type: "computed"`**：
    - 工廠編譯器解算器升級，於 `compile` 階段即時調用 Provider 函式並注入執行期上下文 `ExecutionContext`，具備型別安全轉型防護。
  - **`agents-workflow` 動態路徑地圖實裝**：
    - 實作 `providers.py:get_dynamic_context_map`，成功在 `ContextInit.md` 物化產物中即時動態渲染專案活躍語意 URI 解析地圖。

- **HTML 註解 Token 自宣告與 Core `yscb.host://` 協議支援 (`sub_05`)**：
  - **HTML 註解 Token 自宣告與 Replace 展開**：
    - 於 `agents-workflow/manifest.json` 宣告 `BEGIN_HTML_ANNOTATION` 與 `END_HTML_ANNOTATION` Token。
    - 配置 replace 模式分別物化為字面值 `<!--` 與 `-->`，由工廠編譯器安全展開，避免 Markdown 預覽干擾。
  - **Core `yscb.host://` 專案宿主協議**：
    - 於 `core` 模組引入 `yscb.host://` 一等公民常數協議，模板值為 `{yscb_host}`。
    - 強制指向起手腳本 `yscb.py` 與 `yscb.config.json` 所在之專案宿主工程根目錄，支援 O(1) fast-path 路由。

- **Agents Workflow 配置治理與一鍵初始化引導 (`sub_04`)**：
  - **4 大 Workflow URI 協議體系貢獻**：
    - 於 `manifest.json` 中宣告 `workflow.plans://`, `workflow.archived://`, `workflow.ext://`, `workflow.docs://` 協議，動態綁定至專案級組態 `paths.*`。
  - **專案級組態模板與 `!undefined` 剛性解耦**：
    - 新增 `config.project.json` 模板，所有路徑預設剛性為 `"!undefined"`，貫徹微內核零臆測鐵律。
    - 宣告保留欄位 `ide: []`, `enable_agents_md: true`, `enable_project_changelog: true` 供未來 IDE 適配擴充。
  - **`--init-default` 一鍵初始化與目錄引導引擎 (`WorkflowInitializer`)**：
    - 封裝官方推薦路徑（`project://.agent_workflow/plans` 等），提供實體路徑存在性探測、已存在路徑警示與互動確認 `[-y / -n]`。
    - 自動建立缺失目錄並原子增量持久化至 `config/agents-workflow/config.project.json`，刷新 Core URI 快取。
  - **`--path-*` 變種覆蓋參數支援**：
    - CLI 支援 `--path-plans`, `--path-archived`, `--path-ext`, `--path-docs` 以及 `-y` / `--yes` 自動確認模式。

- **Workflow 佔位符格式重構與可視化語法遷移 (`sub_03`)**：
  - **全新 Markdown 可視化佔位符語法**：
    - 徹底淘汰原易被 Markdown / HTML 預覽引擎隱藏的 HTML 註解格式（`<!-- __TOKEN__ -->`）。
    - 引入**插入佔位符 (Token Anchor)**：`__@{token}__`（如 `__@{PHASEXX_STANDARD_HEADER}__`、`__@{DYNAMIC_CONTEXT_MAP}__`），支援大括號內部微量空格容錯。
    - 引入**路徑佔位符 (URI Reference)**：`__#{uri}__`（如 `__#{module.root://agents-workflow/assets/...}__`），編譯期 100% 原樣保留，作為 Markdown 文檔的語意參照與路徑錨點。
  - **工廠編譯器 5-Step 狀態機與殘留抹除升級**：
    - 升級 `ArtifactCompiler`，支援 `replace` / `below` / `above` 多輪遞迴展開與自指死鎖防護。
    - 實作智慧抹除正則工廠，解算完成後自動吞噬行首縮排與換行，確保產物排版純淨無多餘空行。
  - **全域資產 1:1 語法遷移**：
    - 全面更新 `assets/templates/` (P01~P07)、`DevelopmentStandards.md` 與 `ContextInit.md` 中的標籤。

- **Core Contribute 系統優化與語意 URI 系統打磨 (`sub_02`)**：
  - **Contribute 來源自動標記 (`__provider__`)**：
    - 在微內核搜集 donor 模組 contributes 時，自動遞迴為 Dict 與 List[Dict] 項目注入 `"__provider__": donor_name`（顯式指定保留不覆蓋），確保下游模組可無痛自省貢獻來源。
  - **依賴拓撲聚合排序 (Topological Ingestion Order)**：
    - 依據已安裝模組之依賴拓撲順序有序合併，保證底層基礎設施優先註冊，擴充模組後續追加覆蓋。
  - **微內核標準 Contribute 查詢 SDK**：
    - 提供 `core.contributes.get(target_module, key=None, default=None)` 與 `get_for_current_module()`，內建自愈快取。
  - **JIT `!undefined` URI 熱更新補齊機制**：
    - 在 `uri.resolve()` 探測到 `!undefined` 或未配置路徑時，於 TTY 終端主動彈出 `[-y <path> / -n / --help]` 互動選單。
    - 相對路徑一律以 `yscb://` 為基準展開，支援連鎖未定義依賴遞迴解算與自引用循環死鎖防護 (`CyclicURIDependencyError`)。
    - 自動原子寫回所屬模組之 `config.project.json` 並刷新記憶體快取無縫繼續運行；非 TTY 或靜態檢查時拋出結構化 `UndefinedURIError`。
  - **語意協議高度對稱化與自省清冊**：
    - 徹底清除歷史殘留別名 `build://`。
    - 將鏡像空間與發布空間納入 `module` 分支（`module.mirror.root://` / `module.mirror://`、`module.release.root://` / `module.release://`），與源碼、建置、運行空間達成 6 大空間高度對稱。
    - 新增 `python yscb.py uri list` / `--list`、`resolve`、`to-uri`、`check` CLI 自省命令，支援清晰展示原始宣告值 (`RAW TARGET / VALUE`) 與展開後實體路徑。

- **Agents Workflow 核心骨架遷移與協議產物工廠化 (`sub_01`)**：
  - **純淨通用內核與三位一體資產 (`assets/`)**：
    - 徹底剝離專案特化規則，提供 100% 通用抽象資產：`assets/standards/` (2 項規範: DocumentationStandards, DevelopmentStandards)、`assets/workflows/` (ContextInit)、`assets/templates/` (`header.md` 與 13 大標準模板庫)。
  - **協議產物工廠化與宣告式依賴注入引擎 (`compiler.py`)**：
    - 支援宣告式 `export`（資產導出）、`insert`（錨點注入，支援 `const`/`uri` 與 `replace`/`below`/`above`）與 `token`（自省元數據）Schema 規範。
    - 實作 5-Step 多輪遞迴狀態機（建立快照 ➔ 依拓撲注入 ➔ 移除已解算錨點標籤 ➔ 遞迴探測收斂 ➔ 分流原子寫入至 `module://exports/`），保證自指死鎖防護與無殘留標籤。
    - 完成 `PHASEXX_STANDARD_HEADER` 標頭解耦與 replace 自注入閉環驗證。
  - **CLI 自省與微內核 Hook 自治閉環**：
    - 提供 `agents-workflow compile` (物化編譯)、`tokens` (錨點清單查詢) 與 `list` (物料清冊查詢) 指令。
    - 註冊 `scripts/hook.core.py:on_reload` 事件監聽，在 `yscb reload` 後自動自主編譯物化。
  - **腳手架與資產空間優化**：
    - 統一收納靜態資產至 `assets/` 目錄。
    - 修復 `dev:scaffold` 腳手架對連字號模組名稱之自動底線套件轉換。

## 2026_08_23_2030_architecture_refactor

- **全系統 CLI UX 標準化與本地發布守門精簡 (`sub_14`)**：
  - **全域 Banner 與層次化 Help (`yscb --help`)**：重構輸出視覺架構，整合 Banner、Usage、`CORE COMMANDS` (整併 `init`)，並動態掃描聚合已安裝模組之 `MODULE COMMANDS` 清冊。
  - **智慧指令拼寫建議 (Did you mean?)**：採用 Python 標準庫 `difflib`，在使用者輸入未知指令時提供精準候選提示。
  - **本地發布守門精簡 (`dev.releaser`)**：移除 Gate 1 Git Dirty 限制，支援非 Git 倉庫與本地敏捷發布打包。
- **全面 Zip 單檔打包與同構自舉管線 (`sub_13`)**：
  - **明文空間嚴格二分法**：全系統僅 `source/` 與 `modules/` 維持展開檔案，中間快取與產物庫（`build/`、`release/`、`.mirror/`）全面強制改為 `{version}.zip` 單檔格式。
  - **4-Stage Atomic Reload 流水線**：解耦為 Stage 1 (自癒拉取) ➔ Stage 2 (解壓物化，解壓前剛性清空) ➔ Stage 3 (組態治理，掃描部署並無條件刪除模板) ➔ Stage 4 (依賴注入)。
  - **同構 Zip 下載與自舉**：`yscb.py init` 預設遠端指向 GitHub 官方 Release 庫，100% 透過 Python 標準庫串流下載與解包自舉。
  - **職責精確邊界**：`release.root` 與 `release` 語意協議精準歸由 `dev` 模組貢獻治理。
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
- **套件框架健壯性強化與缺陷修復 (`sub_11`)**：
  - **100% Python 標準庫 SemVer 2.0.0 運算器 (`core.semver`)**：純標準庫實作，支援四元組解析、數值排序（保證 `1.10.0 > 1.9.0`）、`>=, >, <=, <, ==, !=, ~=, *` 範圍匹配與最高合規版本依賴求解。
  - **剛性拓撲隔離與 6 大軟相容手段清除**：`yscb.py` 移除向上爬樹；`contributes.py` 清除對 `source/` 與 `project://` 穿透；`installer.py` 清除硬編碼後門；`uri.resolve()` 嚴格攔截非標準 URI 拋出 `ValueError`。
  - **不可變 `ExecutionContext` SSOT 與 CM 作用域**：`core.context` 集中定義不可變數據載體；`core.uri` 提供 `module_scope` 與 `host_scope` 上下文管理器，例外安全自動還原。
  - **雙層組態快照與 Hermetic Clean Build**：快照還原同步備份覆蓋 `config.root://`；`dev.builder` 預設強制清空發布版本目錄，100% 排除 `tests/` 與 `.yscbignore` 污染。
  - **Contract/Custom 分離統計與獨立失敗清單**：測試框架精準分離計數，杜絕交叉誤扣，並提供獨立失敗案例清單。全量測試 59/59 項 100% Passed。
- **四段式版本號、雙軌來源庫、三層降級鏈與發布流水線 (`sub_12`)**：
  - **四段式語意化版本 (`core.semver`)**：支援 `(major, minor, patch, revision)` 解析與正規化，前三段數值比大小（`1.10.0.0 > 1.9.0.0`），尾號 `revision` 支援微小修訂號或 `build` 本地標籤，日常三元版本常態安裝。
  - **雙軌來源庫架構 (`build://` vs `release://`)**：
    - `build/` (開發庫)：`dev build` 產出完整包（包含 `tests/`，版本強制為 `X.Y.Z.build`），供全黑盒測試直接解析與安裝。
    - `release/` (發布庫)：`dev release` 產出純淨發布包（排除 `tests/`），針對同 `X.Y.Z` 實施單一最新 Revision 淘汰清理。
  - **三層安裝降級鏈 (`build://` ➔ `mirror://` ➔ `provider`)**：依序滿足本地開發即時測試、離線快取與遠端發布庫解析，三層同構維護 `index.json`。
  - **模組增量遷移階梯調用引擎 (`act_migrate`)**：升級時依序遞增調用 `scripts/migrations/{minor}.x.py` 增量腳本，缺腳本自動靜默跳過，失敗自動 Snapshot 原子回滾。
  - **Dev Releaser 發布安全交易防護 (`dev release`)**：Pre-flight 4 大守門、Version Bump、純淨打包、智慧 Git Tag（Major/Minor 自動打 Tag，Patch/Revision 預設不打）與失敗 100% 原子回滾。
  - **運行空間純粹化與自治忽略**：模組物化安裝後自動剝除 `modules/` 內的 `config.*.json` 模板；`init` 自動生成 `yscb://.gitignore` 確保專案根目錄零污染。全量測試 70/70 項 100% Passed。

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
