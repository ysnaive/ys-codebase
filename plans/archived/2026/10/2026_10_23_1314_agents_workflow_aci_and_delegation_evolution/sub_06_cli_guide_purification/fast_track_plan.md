# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：`yscb-cli-guide` 深度瘦身與 `-h` 按需自省重構 (sub_06_cli_guide_purification)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)

### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)
- [x] **修改行數守門**：代碼修改行數預估 $\le 100$ 行（重構 `yscb-cli-guide/SKILL.md` 約 45 行，並移除 `core/providers.py` 死代碼與對應舊測試）。
- [x] **API 契約守門**：Public API 簽名契約 0 變更（無破壞性與新增導出；`AGENTS_CLI_GUIDE` Token 仍保留於 `agents-workflow` 供下游專案按需注入）。
- [x] **依賴邊界守門**：零跨模組新依賴引入（進一步消除 `core` 對 `agents-workflow` Markdown 表格渲染之殘留耦合）。
- [x] **既有測試守門**：既有單元測試套件 100% 覆蓋守門。

### 1.2 核心需求與邊界
- **需求描述**：
  1. **`[FP-01:DR-01]` 徹底拔除動態指令大表，消除字元隨指令數無上限膨脹**：
     - 自 `ys_codebase/source/core/contributes/agents-workflow.json` 移除 `AGENTS_CLI_GUIDE` 之 `code.func://core/providers:get_agents_cli_guide` computed 注入宣告。
     - 物理刪除 `ys_codebase/source/core/core/providers.py`（並同步清理 `core/__init__.py`、`_manifest.md` 與 `core/tests/` 中針對舊 `get_agents_cli_guide` 動態表格的遺留測試），使 `core` 微內核 100% 脫離工作流 Markdown 渲染邏輯。
  2. **`[FP-01:DR-02]` `yscb-cli-guide/SKILL.md` 純化為「調用慣例 + 技能內建指令直跑 + 非常規指令 `-h` 按需自省」**：
     - **終端執行防呆慣例**：保留單行指令紀律（禁止多行與互動輸入，依 Shell 使用 `;` 或 `&&`）、雙引號文字參數逃逸防呆（`--log`、`--note` 內禁夾雙引號 `"` 與反引號 `` ` ``）及常駐 `yscb server` 之 `[BLOCKER]` 處置規範。
     - **分流執行與 `-h` 按需自省機制**：
       1. **技能內建指令免查直跑 (`Skill-Vetted Fast Pass`)**：凡在其他活躍 Skill（如 `development-sop`、`knowledge-db-search`、`yscb-module-dev`、`todo`、`roadmap` 等）之標準步驟中明確列出的常規指令，預設均已通過 `[SAFE]` 審核（或由該技能內建確認卡守門），Agent 直接依該技能語法執行，無須額外查表或跑 `-h`。
       2. **非常規指令／未知選項強制 `-h` 自省 (`Just-in-Time -h Inspection`)**：凡欲執行當前 Skill 未明確列出之子命令、嘗試非標準選項旗標，或不確定操作安全等級時，強制先執行 `python __${yscb.host://yscb.py}__ <module> [command] [subcommand] -h`，由原生 `HelpRenderer` 輸出之 `Security`、`RECOMMENDED USAGE (Pros)` 與 `RESTRICTIONS & GATES (Cons)` 確認權限分級與限制。
     - **三級權限與 `[GATED]` 紅線家族原則**：精煉定義 `[SAFE]`、`[CONDITIONAL]`（如 `dev test` 已內建前置構建，跑測前禁手動跑 `dev build`；`knowledge-db search` 已內建懶索引，日常免手動跑 `index`）與 `[GATED]` 紅線家族特徵（凡涉及模組安裝移除 `install` / `remove` / `update` / `rollback`、正式打包發布 `release*`、版本晉升 `bump-*`、環境初始化 `init`、計畫封存 `archive`、快取清除 `clean` 及內部原子操作 `op-*` 一律屬 `[GATED]` Default-Deny，未獲當下對話顯式授權嚴禁執行）。
     - 尾部保留獨立行 `` `__@{AGENTS_CLI_GUIDE}__` `` 錨點（移除舊 `<!-- YSCB_AGENTS_CLI_GUIDE_BEGIN -->` 註解框），供下游專案透過 `contribute.json` 注入專案特化 CLI 規則。
- **影響範圍**：
  - `ys_codebase/source/agents-workflow/assets/skills/yscb-cli-guide/SKILL.md`
  - `ys_codebase/source/core/contributes/agents-workflow.json`、`contributes/_manifest.md`、`core/__init__.py`、`core/providers.py` (Delete)
  - `ys_codebase/source/core/tests/test_cli_router.py`、`test_contributes.py`
  - `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py`
  - `docs/agents-workflow/{README.md,user_guide.md}`

### 1.3 實作任務與測試規劃
- [x] **TASK-01**：重構 `ys_codebase/source/agents-workflow/assets/skills/yscb-cli-guide/SKILL.md`，實作純慣例、技能內建直跑、非常規指令 `-h` 按需自省與三級權限紅線家族規範。
- [x] **TASK-02**：自 `ys_codebase/source/core/contributes/agents-workflow.json` 移除 `get_agents_cli_guide` 注入，刪除 `core/providers.py` 並同步清理 `core/__init__.py`、`core/contributes/_manifest.md` 與 `core/tests/{test_cli_router.py,test_contributes.py}`。
- [x] **TASK-03**：於 `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py` 新增驗證 `yscb-cli-guide/SKILL.md` 行數預算（$\le 65$ 行）、`-h` 按需自省指引與 Stage 1 編譯後零動態大表殘留之測試斷言，並同步更新 `docs/agents-workflow/` 文檔。
- **測試案例清冊**：
  - [x] **FT-01**：驗證 `yscb-cli-guide/SKILL.md` 包含技能內建直跑 (`Skill-Vetted Fast Pass`)、非常規指令 `-h` 自省 (`-h` / `--help`)、`[SAFE]` / `[CONDITIONAL]` / `[GATED]` 紅線家族原則與 `AGENTS_CLI_GUIDE` 錨點，且經 Stage 1 編譯後無舊動態指令表殘留、行數 $\le 65$ 行。
  - [x] **RT-01**：`core` 與 `agents-workflow` 全模組單元測試套件 100% 回歸通過。

---

## 2. 實作與驗證成果 (FP-02 Execution & Test Log)

- **實作結果**：
  1. 重構 `ys_codebase/source/agents-workflow/assets/skills/yscb-cli-guide/SKILL.md`（收斂至 62 行、約 1,020 tokens，較原先 3,385 tokens 大幅縮減 `-70%`）並同步 `contributes/agents-workflow.json` 之 `description`，落實「單行與引號防呆 + 常駐 Server `[BLOCKER]` 處置 + 軌跡 A 技能內建指令免查直跑 (`Skill-Vetted Fast Pass`) + 軌跡 B 非常規指令／未知旗標強制 `-h` 按需自省 (`Just-in-Time -h Inspection`) + 三級權限與 `[GATED]` 紅線家族原則」。
  2. 自 `ys_codebase/source/core/contributes/agents-workflow.json` 移除 `AGENTS_CLI_GUIDE` computed 注入，物理刪除 `ys_codebase/source/core/core/providers.py`，並同步清理 `core/__init__.py`、`core/contributes/_manifest.md` 與 `core/tests/{test_cli_router.py,test_contributes.py}`（將 `test_cli_router.py` 升級為 `TestHelpRendererMetadata`，直接驗證 `HelpRenderer.render_cmd_help` 渲染 `Security : [SAFE]/[CONDITIONAL]/[GATED]`、`RECOMMENDED USAGE (Pros)` 與 `RESTRICTIONS & GATES (Cons)`）。
  3. 於 `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py` 新增 `test_ft_12_sub06_cli_guide_purification_and_help_first`，並更新 `docs/agents-workflow/{README.md,user_guide.md}`。
- **實機測試日誌**：
  - `python yscb.py dev check core` & `python yscb.py dev check agents-workflow`: 100% PASSED
  - `python yscb.py dev test core -q`: `Pass: 190(100.0%), Fail: 0, Skip: 0`
  - `python yscb.py dev test agents-workflow -q`: `Pass: 135(100.0%), Fail: 0, Skip: 0`
  - `python yscb.py contributes check` & `compile` & `release --force`: 57 份檔案物化成功（0 Error, 0 Warning）

---

## 3. SOP Review 審查與結案交付 (Review & FP-03 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（docs/ 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 CHANGELOG.md 發布摘要。
- [x] **標頭狀態更新**：完成上述審查並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_10_23_1314_agents_workflow_aci_and_delegation_evolution/sub_06_cli_guide_purification` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

