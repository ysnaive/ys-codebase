# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_04_onboarding_and_config_coaching  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：接續推進全局落地順序 Global Step 8 (`sub_04_onboarding_and_config_coaching`)，將合流遷入之兩份技術路線圖 [roadmap.md](./roadmap.md)（Part I：`how_to_config_yscb_and_project_role_roadmap` 與 Part II：`how_to_yscb_interactive_coaching_roadmap`）一次性完整落地至 `agents-workflow` 及生態系四大核心模組（`core`、`dev`、`server`、`knowledge-db`），完成 `PROJECT_ROLE_AND_BOUNDARIES` 空間邊界錨點、`/how-to-config-yscb` 設定體檢與代寫修復技能、`/how-to-yscb` 互動式教學引導技能，以及跨模組設定體檢卡與標準用法速查卡片段注入。
- **核心目標**：
  1. **`AgentsStandards.md` 專案角色與主客體空間邊界錨點 (`PROJECT_ROLE_AND_BOUNDARIES`)**：
     - 於 `ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md` 預留選配注入錨點 `` `__@{PROJECT_ROLE_AND_BOUNDARIES}__` ``，並於 `contributes/agents-workflow.json` 註冊 `PROJECT_ROLE_AND_BOUNDARIES` Token。
     - 標準化宣告三要素：① 開發者角色與專案使命、② 本體業務空間（First-Party Scope，開發與 `/discuss` 優先級 1~2 排查重心）、③ 外部工具包與黑盒依賴清單（External Toolkits，含 `.modules/` 運行空間與二層物化唯讀空間動態標註，預設禁深讀內部實作、禁直接修改）。
     - 專案層級之 `config://agents-workflow/snippets/project_role.md` 與 `testing_guide.md` 不於開發階段靜態預建，而於實機執行 `/how-to-config-yscb` 時自動探勘草擬、經開發者確認後代寫入 `ys_codebase/config/agents-workflow/`。
  2. **主動指令型技能 `/how-to-config-yscb`（診斷 + 確認後直接代寫／修復配置 + 三步編譯守門）**：
     - 建立 `ys_codebase/source/agents-workflow/assets/skills/how-to-config-yscb/SKILL.md`，採用主動指令型極簡 Frontmatter `description`。
     - 實作四步閉環：① 全專案設定與空間拓撲自動探勘（掃描目錄、檢查 `.gitignore` 是否涵蓋 `*.local.json`、檢查 `project_role.md` 與 `testing_guide.md` 及各模組設定現況）$\to$ ② 呈遞「設定健康度報告與代寫提案卡」（標示 `config.project.json` vs. `config.local.json` vs. `config://agents-workflow/snippets/{project_role.md,testing_guide.md}`，預設將 `.modules/` 與二層物化空間納入邊界）$\to$ ③ 獲確認後直接代寫／修復配置並強制執行三步嚴格編譯驗證守門（`contributes check` $\to$ `agents-workflow compile` 0 Error/0 Warning $\to$ `agents-workflow release`）$\to$ ④ 新開實戰 Session 隔離提醒。
     - 預留跨模組設定體檢注入錨點 `` `__@{HOW_TO_CONFIG_MODULES}__` ``（註冊於 `contributes/agents-workflow.json`）。
  3. **主動指令型技能 `/how-to-yscb`（互動式教練角色 + 開放式切入選單 + 實戰 Session 隔離）**：
     - 建立 `ys_codebase/source/agents-workflow/assets/skills/how-to-yscb/SKILL.md`，採用主動指令型極簡 Frontmatter `description`。
     - 實作四大核心機制：① 跨模組知識底座（工作流核心觀念、6 大計畫模式選軌心法 + `` `__@{HOW_TO_YSCB_MODULES}__` `` 各模組標準用法速查卡）$\to$ ② 互動式教練人格與開放式切入角度 A~D（去死板範式、漸進式互動、唯讀教學護欄）$\to$ ③ 按需深鑽隨包手冊（透過單反引號語意連結 `` [`<模組> 隨包手冊`](`__#{module://<mod>/README.md}__`) ``）$\to$ ④ 實戰 Session 物理隔離提醒與「新 Session 專屬起手式指令區塊」打包。
     - 於 `context-init/SKILL.md` 熱啟動狀態卡底部附上輕量提示，讓新手隨時知道有 `/how-to-yscb` 與 `/how-to-config-yscb` 可呼叫。
  4. **生態系四大模組（`core`、`dev`、`server`、`knowledge-db`）宣告式片段注入**：
     - 各模組於 `contributes/agents-workflow.json` 與 `assets/` 下注入各自精簡（15~25 行以內）之「模組設定與健康度速查卡（注入 `HOW_TO_CONFIG_MODULES`，固定以 `### ⚙️ <模組名稱> 設定與體檢` 為標題）」與「標準用法速查卡（注入 `HOW_TO_YSCB_MODULES`，固定以 `### 📦 <模組名稱> (<一句話定位>)` 為標題）」，並附帶單反引號語意連結指向 `module://<mod>/README.md`。
- **邊界排除 (Explicitly Excluded)**：
  - `/skill-creator` 三軌擴充引導工作流與 `references/extension-guide.md` 留待 Global Step 9 (`sub_05_skill_creator_extension_workflow`) 實作。
  - `agents-workflow/tests/` 存量測試集全面純化收斂與 6 份 Roadmap 最終封存驗收留待 Global Step 10 (`sub_06_final_acceptance_and_suite_purification`) 執行。
- **架構影響範圍**：
  - `ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md`（新增 `__@{PROJECT_ROLE_AND_BOUNDARIES}__` 錨點）
  - `ys_codebase/source/agents-workflow/assets/skills/how-to-config-yscb/SKILL.md`（新建）
  - `ys_codebase/source/agents-workflow/assets/skills/how-to-yscb/SKILL.md`（新建）
  - `ys_codebase/source/agents-workflow/assets/skills/context-init/SKILL.md`（狀態卡底部新增輕量提示）
  - `ys_codebase/source/agents-workflow/contributes/agents-workflow.json`（匯出 `how-to-config-yscb`、`how-to-yscb` 技能，註冊 `PROJECT_ROLE_AND_BOUNDARIES`、`HOW_TO_CONFIG_MODULES`、`HOW_TO_YSCB_MODULES` Token）
  - `ys_codebase/source/{core,dev,server,knowledge-db}/contributes/agents-workflow.json` 及對應 `assets/` 速查卡片段（注入設定體檢卡與黃金用法速查卡）
  - `ys_codebase/config/agents-workflow/snippets/project_role.md` 及 `ys_codebase/config/agents-workflow/contribute.json`（Dogfooding 掛載本專案角色與空間邊界）
  - `ys_codebase/source/agents-workflow/tests/` 與 `docs/agents-workflow/`（同步更新單元測試與知識庫文檔）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `PROJECT_ROLE_AND_BOUNDARIES` 常駐於 `AgentsStandards.md` Turn 0 視野**：
  將專案角色定位、本體業務空間（First-Party Scope）與外部工具包黑盒邊界（External Toolkits + 二層物化唯讀空間）以 `__@{PROJECT_ROLE_AND_BOUNDARIES}__` 錨點置於 `AgentsStandards.md` 核心原則與技能路由之間；未配置時由 Stage 1 編譯器自動抹除空錨點，已配置時在 Turn 0 直接作為搜尋過濾器與 `/discuss` 三級排查（本體優先 $\to$ 呼叫端 $\to$ 外部工具包）的物理目錄依據。
- **[P00:DR-02] `/how-to-config-yscb` 四步體檢代寫閉環與三步嚴格編譯驗證守門**：
  `/how-to-config-yscb` 聚合 `HOW_TO_CONFIG_MODULES` 錨點內各模組之設定體檢卡，自動探勘目錄拓撲、`.gitignore` 之 `*.local.json` 保護、`config://agents-workflow/snippets/{project_role.md,testing_guide.md}` 與各模組組態，呈遞提案卡獲開發者確認後直接代寫，並強制依序執行 `contributes check` $\to$ `agents-workflow compile` (0 Error/0 Warning) $\to$ `agents-workflow release`。
- **[P00:DR-03] `/how-to-yscb` 互動式教練角色、唯讀護欄與新開實戰 Session 物理隔離**：
  `/how-to-yscb` 採主動指令型極簡契約，觸發後切換為啟發式教練角色（提供開放式切入角度 A~D，嚴格遵守唯讀教學護欄禁改代碼或建計畫），結合 `HOW_TO_YSCB_MODULES` 各模組標準用法速查卡與隨包手冊單反引號語意連結按需解說，並於收尾時強制提醒開啟全新實戰 Session 且打包「新 Session 專屬起手式指令區塊」。
- **[P00:DR-04] 四大核心模組跨模組片段高密度契約（每卡 15~25 行）**：
  `core`、`dev`、`server`（新建 `contributes/agents-workflow.json`）與 `knowledge-db` 分別提供設定體檢卡（`### ⚙️ <模組名稱> 設定與體檢`）與標準用法速查卡（`### 📦 <模組名稱> (<一句話定位>)`），嚴格控制每段 15~25 行以內並使用單反引號包裹之 `` [`<模組名稱> 隨包手冊`](`__#{module://<mod>/README.md}__`) ``。
- **[P00:DR-05] 全面評估雕琢：三處聯動對齊、全綠短路、雙入口自適應教練與底層編譯器/CLI 兩處根治**：
  1. **本體空間三處一次對齊（First-Party Trinity Alignment）**：`/how-to-config-yscb` 探勘出專案本體源碼目錄與測試框架後，提案卡同步草擬 `config://agents-workflow/snippets/project_role.md`、`config://agents-workflow/snippets/testing_guide.md` 及（若安裝 `knowledge-db`）`config://knowledge-db/contribute.json` 之 `spaces.source.include`；若全項已就緒則觸發「全綠免改短路（All-Green Short-Circuit）」。
  2. **`/how-to-yscb` 雙入口自適應開場（Dual-Entry Adaptive Onboarding）**：純輸入 `/how-to-yscb` 時呈現已安裝模組與 A~D 四大探索角度選單；若輸入 `/how-to-yscb <具體問題>` 則跳過選單直接解答並附上新開實戰 Session 起手式 Prompt。
  3. **順手根治底層 2 處微觀瑕疵**：修復 `agents-workflow/scripts/cli.py:tokens()` 兼容 `tok.get("value") or tok.get("name")`（並統一 `knowledge-db/contributes/agents-workflow.json` 為 `"value": "KNOWLEDGE_DB_SPACE"`），以及修正 `ArtifactCompiler._resolve_source_path` 針對跨模組 `module://<mod>/...` 之同級模組目錄 Fallback 防串線。

---

## 3. 開放議題與確認紀錄

- 兩份來源路線圖之所有組件規格、錨點設計與防呆守門均已 100% 明確，無未決開放議題。

