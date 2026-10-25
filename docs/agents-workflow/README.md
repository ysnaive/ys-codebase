---
target: "Agents-Workflow"
doc_type: "readme"
status: "active"
source_paths:
  - "yscb://source/agents-workflow/agents_workflow/commands.py"
  - "yscb://source/agents-workflow/agents_workflow/compiler.py"
  - "yscb://source/agents-workflow/agents_workflow/publisher.py"
related_docs:
  - "./FACTORY_PIPELINE.md"
  - "./user_guide.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-10-25"
---

# Agents Workflow 模組 (General Agents Workflow Framework)

`agents-workflow` 為 YS-Codebase 體系的一等公民核心模組，提供通用、純淨且工廠化的 Agent 技能與規範治理體系。

---

## 1. 核心定位與資產架構

模組徹底剝離特定專案特化規則，採用 100% 純 Skill 分類架構（`standard`, `template`, `skill`），提供通用抽象資產與計畫生命周期治理：

- **規範 (`assets/standards/`)**：
  - `AgentsStandards.md`：Agent 通用核心原則、防呆紀律與條件式技能分流導航矩陣（自動注入至 `AGENTS.md`，頂部支援 `PROJECT_ROLE_AND_BOUNDARIES` 專案角色與空間邊界錨點注入）。
- **技能 (`assets/skills/<name>/SKILL.md`)**：
  - **工作流與生命週期技能**：`context-init`（上下文熱啟動）、`new-plan`（標準立項與延遲建檔）、`auto`（Phase 01~05 自動連續推進）、`discuss`（深度歸因與範疇保護）、`continue`（中斷現場接續）、`pause`（現場狀態凍結）、`research`（深度技術調研）、`roadmap`（長期路線圖推薦與 `Consume-on-Promote` 晉升）、`todo`（`TODO.md` 輕量待辦與微觀技術債管理）。
  - **互動引導與配置教練技能**：`how-to-config-yscb`（專案空間自適應探勘、多模組組態體檢與三位一體對齊教練）、`how-to-yscb`（跨模組功能導覽、6 大計畫模式選型與雙入口互動式上手教練）。
  - **領域與規範技能**：`development-sop`（SOP 0~7 與 6 大分支指南，含 `references/` 規範明細）、`testing-sop`（自動化測試建置六大鐵律、雙重守門與 `__@{TESTING_SOP_STANDARDS}__` 錨點）、`documentation`（知識庫 3 層架構與 7 大維度指南）、`yscb-cli-guide`（CLI 執行防呆慣例、技能內建指令直跑與非常規指令 `-h` 按需自省）、`skill-creator`（專案特化技能建置、三軌擴充智能分流與雙層編譯註冊閉環）、`skill-optimizer`（AI Agent 技能審查、診斷與重構工作流）、`yscb-module-dev`（生態系模組開發與 Dogfooding 閉環）。
- **模板 (`assets/templates/`)**：
  - 16 大標準模板庫（`P00_discuss`, `P01`~`P07`, `revision_log`, `fast_track_plan`, `umbrella_overview`, `changelog`, `RXX_research_report`, `handoff`, `roadmap`, `todo`）與共用標頭。
- **6 大計畫分支拓撲、雙層儲備消耗 (`Consume-on-Promote`) 與 `/NewPlan` 延遲建檔守門 (Delayed Materialization)**：
  - **6 大計畫分支**：依據規模、風險與任務性質劃分為 **Full Track**（標準 SOP 0~7 八大階段）、**Fast Track**（FP-01 規劃、FP-02 實作與驗證、FP-03 SOP 審查與結案，4 大守門：代碼行數 $\le 100$、API 契約 0 變更、零跨模組新依賴、既有測試 100% 守門）、**Umbrella**（跨模組主計畫與 `sub_XX` 子計畫，支援預先規劃型 Pre-planned 與增量演進型 Incremental 兩大模式）、**修訂計畫 (Revision Track)**（正交修訂與強制留檔，適用於不牽涉核心業務邏輯之 UI/UX/DX、參數與文檔微調，排除 Bug Fix，具備 4 大升級熔斷，支援獨立開立或附掛既有計畫產出 `revision_log.md`）、**調研計畫 (Research Track)**（3 步深度調研，統一以 `R{NN}_{topic}.md` 命名產出報告，支援三大出口轉化）以及 **Roadmap / Todo 雙層儲備**（`workflow.roadmap://` 宏觀策略藍圖 `{topic}.md` 與微觀待辦帳本 `TODO.md`，支援 `roadmap promote` 物理移轉與 `todo promote` 打包提取立項）。
  - **延遲建檔與 `Seeded` 原地復用守門**：觸發 `/NewPlan` 進入 `P00` 需求討論階段時維持純對話，**嚴禁預先建立實體目錄**；若目錄已由 `roadmap promote` 或 `todo promote` 預先建立並置入起源種子檔（`roadmap.md` 或 `todo.md` + `changelog.md`），則直接於該 `Seeded` 目錄原地補齊首份正式規格檔，杜絕重複建檔與空殼垃圾目錄。
- **擴充手冊**：[`contributes/_manifest.md`](../../ys_codebase/source/agents-workflow/contributes/_manifest.md) 官方擴充宣告格式規格書。

---

## 2. 佔位符語法與渲染機制 (Placeholder Architecture)

系統採用 Markdown 原生可視的強定義佔位符語法，淘汰被 HTML 隱藏的舊註解格式：

| 佔位符類型 | 語法結構 | 正則表達式 | 核心職責與編譯行為 |
| :--- | :--- | :--- | :--- |
| **插入佔位符 (Token Anchor)** | `__@{TOKEN_NAME}__` | `r"__@\{\s*([A-Za-z0-9_]+)\s*\}__"` | 主動注入點。由編譯器 5-Step 狀態機進行 `replace` / `below` / `above` 多輪遞迴展開，解算完成後自動乾淨抹除殘留標籤行。 |
| **自身相對路徑 (Local URI Reference)** | `__#{URI_OR_PATH}__` | `r"__#\{\s*([^}]+)\s*\}__"` | 被動語意參照。於 Stage 1 快取中保留解耦，於 Stage 2 釋出發布時依三層階層動態轉譯為相對於目標檔案所在目錄之實體相對路徑（用於 Markdown 超連結跳轉）。 |
| **專案相對路徑 (Project URI Reference)** | `__${URI_OR_PATH}__` | `r"__\$\{\s*([^}]+)\s*\}__"` | 相對於專案根目錄之相對路徑（用於終端 CLI 提示與檔案路徑展示）。 |
| **動態起點相對路徑 (Anchor URI Reference)** | `__$(ANCHOR){URI_OR_PATH}__` | `r"__\$\(([^)]+)\)\{\s*([^}]+)\s*\}__"` | 相對於指定錨點目錄之相對路徑（用於跨目錄與跨模組特定基準導航）。 |

> [!TIP]
> 佔位符支援大括號內部微量空格容錯（例 `__@{ PHASEXX_STANDARD_HEADER }__` 與 `__@{PHASEXX_STANDARD_HEADER}__` 等價）。編譯器支援 Standalone（剝除反引號）與 Inline（保留代碼引號）二分法解析。

---

## 3. Workflow URI 協議體系與組態治理

模組向 Core 貢獻 4 大專屬語意 URI 協議，動態綁定至 `config://agents-workflow/config.project.json`：

| 協議名稱 | 類型 | 預設模板值 | 一鍵初始化推薦路徑 | 核心職責說明 |
| :--- | :---: | :---: | :--- | :--- |
| `workflow.plans://` | `config` | `!undefined` | `project://plans` | 指向當前專案活躍開發計畫目錄。 |
| `workflow.archived://` | `config` | `!undefined` | `workflow.plans://archived` | 指向歷史封存計畫目錄。 |
| `workflow.docs://` | `config` | `!undefined` | `project://docs` | 指向專案知識庫目錄。 |
| `workflow.roadmap://` | `config` | `!undefined` | `workflow.plans://roadmap` | 指向專案長期策略技術路線圖儲備庫。 |

---

## 4. 釋出目標體系 (`release_target` Contributes)

模組支援宣告 `release_target`，定義不同開發環境（如 Google Antigravity IDE、Claude Code、OpenAI Codex 等）的資產投影規則：
- **`projections`**：定義 `template`、`standard` 與 `skill` 的目標目錄、副檔名與純文字/陣列 `header` 模板（`workflow` 投影已全面除役並收斂至 `skill`）。
- **`skill` 領域技能包**：支援目錄級與單檔級 Skill 套件導出與發布，保留內部 `references/`、`scripts/` 結構並以 `{export.name}` 巨集插值投影至 `.agents/skills/<name>/`。
- **`agents_md` 規範投影**：支援宣告 Target 專屬規範檔案路徑（如 `project://AGENTS.md` 或 `project://CLAUDE.md`），以 `AgentsStandards.md` 內容執行軟合併。
- **巨集插值**：`target_dir` 與 `header` 支援 `{export.description}`、`{export.name}`、`{export.basename}`、`{target.name}` 等巨集變數動態替換。
- **原子交易發布與舊目錄清理**：由 `ReleasePublisher` 基於本地 `cache://agents-workflow/project_release_manifest.json`（不入 Git 追蹤；舊版 `storage://` 清單自動遷移並刪除）執行雙階 Diff 防護（Stage 0 來源指紋短路 + Stage 4 落地內容比對），並在發布時自動偵測清理歷史遺留之 `.agents/workflows/` 與 `.claude/commands/` 目錄。
- **JIT 變更感知自愈與自動投影 (`ensure_jit_release`)**：在執行任何 `agents-workflow` CLI 指令前自動檢驗來源指紋（含目錄級 Skill 遞迴 SHA-1 聚合指紋）。若模組資產、模板或片段發生變更，管線會自動原子同步最新內容至 `.agents/` 等 Target 目錄與 `AGENTS.md`。

---

## 5. 核心 Token 與行為準則擴充 (Tokens & Standards Injection)

模組支援宣告式 Token 錨點供生態系模組或專案組態擴充：
- **`PHASEXX_HEADER`**：共用計畫標頭插槽，提供標準標頭與後台模型 (`> 模型：[平台宣告之模型名稱；無法確認填 Unknown]`) 溯源支援（填寫規則見核心原則「模型紀錄」，詳見 `[DN-AW-08]`）。
- **`WORKFLOW_SOP_STANDARDS`**：SOP 標準開發流程擴充錨點。
- **`TESTING_SOP_STANDARDS`**：位於 `testing-sop` 之擴充錨點，供生態系模組或專案組態注入專屬測試框架指令、沙盒規範與跑測注意事項。
- **`AGENTS_SKILL_ROUTING` / `AGENTS_STANDARDS` / `PROJECT_ROLE_AND_BOUNDARIES`**：位於 `AgentsStandards.md` 之擴充錨點，支援子模組或專案組態透過 `insert` 注入專案角色與主客體空間邊界、專屬技能分流與行為準則。
- **`HOW_TO_CONFIG_MODULES` / `HOW_TO_YSCB_MODULES`**：位於 `how-to-config-yscb` 與 `how-to-yscb` 之動態聚合錨點，自動匯聚各已安裝模組（`core`、`dev`、`server`、`knowledge-db` 等）之設定體檢片段與使用速查面板。
- **`SKILL_CREATOR_STANDARDS` / `SKILL_OPTIMIZER_STANDARDS`**：位於 `skill-creator` 與 `skill-optimizer` 尾部之擴充錨點，供專案注入專屬技能建置規範或審查標準。
- **`AGENTS_CLI_GUIDE`**：位於 `yscb-cli-guide` 之預留擴充錨點（核心已移除全量指令大表動態傾倒，改採 `-h` 按需自省；僅供下游專案按需追加特化 CLI 注意事項）。
- **`spaces.docs` 貢獻**：透過 `contributes/knowledge-db.json` 向知識庫微內核宣告 `workflow.docs://` 文檔空間。

---

## 6. CLI 快速使用指南

```bash
# 執行原子發布流水線（具備雙階 Diff 檢測，無變更時自動短路）
python yscb.py agents-workflow release

# 強制忽略 Diff 檢測，全量重新編譯與強制覆寫所有發布目標檔案
python yscb.py agents-workflow release --force

# 查詢全系統可用 Release Targets 與本專案啟用狀態
python yscb.py agents-workflow release-target --list

# 啟用指定 Release Target 並自動觸發原子發布
python yscb.py agents-workflow release-target --add antigravity [--proj]

# 停用指定 Release Target 並自動清理已發布檔案
python yscb.py agents-workflow release-target --remove antigravity [--proj]

# 一鍵初始化 Workflow 協議、建立推薦目錄並寫入組態 (支援 -y 自動確認)
python yscb.py agents-workflow init --default [-y]

# 列出全系統已註冊之 Token 錨點清單與說明
python yscb.py agents-workflow tokens

# 列出當前所有模組導出之 Standards, Skills, Templates 清冊
python yscb.py agents-workflow list

# 執行 Stage 1 內容編譯並寫入 cache://agents-workflow/resolved_contents/
python yscb.py agents-workflow compile

# --- Dev Plans 工具鏈 (Plans Management Toolchain) ---
# 掃描並輸出進行中開發計畫狀態矩陣，或執行斷點領航與 handoff.md 原子閱後即焚 (--resume)
python yscb.py agents-workflow plan status [--plan <plan_name_or_subpath>] [--resume]

# 跨計畫檢索決策記錄 (DR) 或全文程式碼
python yscb.py agents-workflow plan search --dr [--year=YYYY] [--month=MM] [--limit=N]
python yscb.py agents-workflow plan search "關鍵字" [--limit=N]

# 稽核計畫文件合規性、階段左移雙檔檢核、P01<->P06 追溯差集、伴隨檔自癒與免讀盲寫追加 changelog.md
python yscb.py agents-workflow plan verify [plan_name_or_subpath] [--phase <P00..P07|current|all>] [--log "<摘要>" [--type PHASE|DECISION|REVISION] [--model "<ModelName>"]] [--all]

# 安全歸檔已完成計畫至 workflow.archived://YYYY/MM/ (具備 4 重守門與 handoff 清理)
python yscb.py agents-workflow plan archive <plan_name> [--force]

# --- 雙層技術儲備與待辦工具鏈 (Roadmap & Todo Toolchain) ---
# 檢視或過濾宏觀路線圖儲備 (自動排除 TODO.md)，或執行 Consume-on-Promote 物理移轉立項
python yscb.py agents-workflow roadmap [list|<topic>] [--status <Backlog|Proposed|Ready|Deferred>]
python yscb.py agents-workflow roadmap promote <topic> [--plan <dir>] [--model "<ModelName>"]

# 免讀盲寫追加、過濾查詢與單筆/多筆打包提取輕量待辦 (workflow.roadmap://TODO.md)
python yscb.py agents-workflow todo add "<標題>" [--scope <範疇>] [--note "<備忘>"] [--model "<ModelName>"]
python yscb.py agents-workflow todo list [--scope <關鍵字>]
python yscb.py agents-workflow todo promote <TODO-ID> [TODO-ID...] --slug <plan_slug> [--plan <dir>] [--model "<ModelName>"]
```

---

## 7. 架構與專題手冊導引

- **Dev Plans 工具鏈完整操作手冊**：詳見 [user_guide.md](./user_guide.md)。
- **協議產物工廠化與 6 步語意管線**：詳見 [FACTORY_PIPELINE.md](./FACTORY_PIPELINE.md)。
- **設計決策與工程妥協**：詳見 [DESIGN_NOTES.md](./DESIGN_NOTES.md)。
