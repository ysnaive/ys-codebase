# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：專案特化技能建置與 Layer 2 宣告式擴充引導工作流 (sub_05_skill_creator_extension_workflow)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  落實跨主計畫全局推進順序 **Global Step 9 (`AW/sub_05_skill_creator_extension_workflow`)**，將前置已規劃並物理遷入之技術路線圖 [roadmap.md](./roadmap.md)（原 `skill_creator_and_layer2_extension_roadmap.md`）轉化為實作。在 `sub_03`（`testing-sop`）與 `sub_04`（`/how-to-config-yscb`、`/how-to-yscb` 與 `PROJECT_ROLE_AND_BOUNDARIES`）所有新增錨點 100% 定型後，建立主動指令型技能 `/skill-creator` 與附屬單層參考手冊 `references/extension-guide.md`，與既有 `/skill-optimizer` 形成「事前建置與 Layer 2 掛載 $\leftrightarrow$ 事後體檢與無損重構」的全生命週期閉環。
- **核心目標**：
  1. **三軌擴充智能分流（3-Track Extension Triage）**：引導下游開發者與 Agent 依需求性質判定最適擴充載體，杜絕為簡短規則濫建碎片 Skill 或繞過編譯管線手寫一次性二層檔案：
     - **軌跡 ①（純錨點注入模式 `Anchor-Only Injection`）**：局部階段／熱啟動注意事項 $\to$ 不建新 Skill，直接於 `config://agents-workflow/snippets/<name>.md` 撰寫片段並注入既有 `__@{...}__` 錨點（0 額外路由開銷）。
     - **軌跡 ②（被動環境攔截型 Skill `Ambient Skill`）**：專案全局注意事項／工具調用攔截 $\to$ 於 `config://agents-workflow/skills/<name>/SKILL.md` 新建技能（採三段式 `核心用途 → 觸發情境 → 排除情境` `description`）並注入 `AGENTS_SKILL_ROUTING`。
     - **軌跡 ③（功能特化型 Skill `Feature Skill`）**：專案特定子系統多步驟工作流 $\to$ 於 `config://agents-workflow/skills/<name>/SKILL.md` 新建技能（Slash 主動呼叫採極簡指令契約；意圖自動觸發採三段式邊界）並註冊匯出與中樞/路由掛載。
  2. **可用錨點與語意 URI 自動檢索及「擴充藍圖確認卡」強制守門（Discovery & Blueprint Gate）**：
     - 引導調用 `[SAFE]` CLI（`python yscb.py agents-workflow tokens` 與 `python yscb.py uri list`）搭配 `./references/extension-guide.md` 動態檢索系統預留錨點與語意 URI。
     - 在實際生成檔案與修改組態前，強制呈遞 **「🛠️ /SkillCreator 專案擴充藍圖確認卡」** 並 End Turn 等待開發者拍板。
  3. **合規第一層資產生成、路徑語意化分流與單反引號語法封裝（Compliant Asset Generation）**：
     - 嚴格遵循第一層扁平存放慣例：`config://agents-workflow/skills/<name>/SKILL.md`（及單層 `references/`）或 `config://agents-workflow/snippets/<name>.md`（不額外套 `assets/`）。
     - 區分「同技能內部 `references/`（使用標準相對路徑 `./references/xxx.md`）」與「跨技能／模板／專案目錄引用（強制使用單反引號包覆之語意 URI `` [`text`](`__#{uri}__`) ``、`` `__${uri}__` ``）」。
     - `skill-creator/SKILL.md` 自身保持通用去特化（Zero Specialization Pollution），預留 `` `__@{SKILL_CREATOR_STANDARDS}__` `` 擴充錨點與 `## 常見踩坑指南 (Gotchas)`。
  4. **附屬單層參考手冊 `references/extension-guide.md` 建置**：
     - 頂部附帶 `## 目錄 (Contents)`（TOC），完整收錄全系統 **22 個已註冊 Stage 1 Token 錨點地圖**（含本次新增之 `SKILL_CREATOR_STANDARDS`）、Stage 2 語意 URI 轉換規則、單反引號防呆正反範例與 `config://agents-workflow/contribute.json` (`export` / `insert`) 最小增量註冊範本。
  5. **宣告式組態註冊與三步嚴格編譯驗證守門（Declarative Registration & 3-Step Verification Gate）**：
     - 以最小增量（Additive Edit）更新 `config://agents-workflow/contribute.json`，強制依序執行：① `python yscb.py contributes check` $\to$ ② `python yscb.py agents-workflow compile`（確認 0 Error / 0 Warning）$\to$ ③ 100% 通過後方可執行 `python yscb.py agents-workflow release` 物化投影。
     - 完成 `agents-workflow` 模組之 `contributes/agents-workflow.json`、`_manifest.md`、單元測試與三層文檔同步，並執行 `@build` 與 `release` 物化驗證。
- **邊界排除 (Explicitly Excluded)**：
  - **不修改既有 `skill-optimizer` 的核心審查邏輯**：`skill-creator` 與 `skill-optimizer` 職責正交（可在彼此排除情境或導流說明中互指，但不合併主檔）。
  - **不在母倉 `ys_codebase/config/agents-workflow/` 預建任何測試用靜態 snippet 或 dummy skill**：`sub_05` 僅於 `source/agents-workflow/` 提供通用 `skill-creator` 技能與 `SKILL_CREATOR_STANDARDS` 空錨點，不污染本倉實際專案組態。
  - **不在此子計畫執行 `agents-workflow/tests/` 全量測試集純化重構**：測試集子系統 1:1 歸戶純化屬於收官子計畫 `sub_06_final_acceptance_and_suite_purification`（Global Step 10）範疇。
- **架構影響範圍**：
  - 新增技能與參考手冊：`ys_codebase/source/agents-workflow/assets/skills/skill-creator/SKILL.md`、`ys_codebase/source/agents-workflow/assets/skills/skill-creator/references/extension-guide.md`。
  - 模組組態與清單宣告：`ys_codebase/source/agents-workflow/contributes/agents-workflow.json`、`ys_codebase/source/agents-workflow/_manifest.md`（內建匯出技能由 16 個增為 17 個；系統總註冊 Token 由 21 個增為 22 個）。
  - 中樞導流微調：`ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md`、`ys_codebase/source/agents-workflow/assets/skills/skill-optimizer/SKILL.md`（補齊 `/skill-creator` 互指導流）。
  - 單元測試與三層文檔：`ys_codebase/source/agents-workflow/tests/test_plans_model_record.py`、`ys_codebase/source/agents-workflow/README.md`、`docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 獨立主動指令型技能定位與極簡 Frontmatter 契約**：
  採納 [roadmap.md](./roadmap.md) 方案 3，建立獨立技能 `skill-creator`，與 `skill-optimizer` 正交分工。Frontmatter `description` 遵循主動指令型極簡契約：`引導建立專案功能特化 Skill、環境注意事項攔截規則或階段錨點注入配置，自動對接語意 URI 與雙層編譯註冊閉環。僅於顯式輸入 /skill-creator 或明確指示建立新 Skill 與擴充工作流規範時觸發。`
- **[P00:DR-02] 三軌擴充智能分流（3-Track Extension Triage）與第一層扁平存放契約**：
  強制於步驟 1 區分「軌跡 ① 純錨點注入（`config://agents-workflow/snippets/<name>.md`，0 路由開銷）」、「軌跡 ② 被動環境攔截型 Skill（`config://agents-workflow/skills/<name>/SKILL.md` + 三段式 `description` + `AGENTS_SKILL_ROUTING` 注入）」與「軌跡 ③ 功能特化型 Skill（`config://agents-workflow/skills/<name>/SKILL.md` + 雙軌 `description` + 匯出與路由掛載）」，第一層路徑嚴格對齊扁平結構（不套 `assets/`）。
- **[P00:DR-03] 同技能內部相對路徑 vs. 跨技能語意 URI 單反引號封裝防呆**：
  指向同技能自身附屬手冊時使用標準相對路徑 `./references/<file>.md`；指向其他技能、模板或專案目錄時強制使用單反引號包覆之語意 URI（`` [`text`](`__#{uri}__`) ``、`` `__${uri}__` ``）。同時在 `skill-creator/SKILL.md` 與 `references/extension-guide.md` 撰寫語法教學範例時，確保範例佔位符皆合規包覆或逃逸，保證 `ArtifactCompiler` 0 Warning 且通過 `UNENCLOSED_TAG_REGEX` 剛性測試。
- **[P00:DR-04] 強制「擴充藍圖確認卡」Gate 與三步編譯發布守門**：
  步驟 2 必須先呈遞「🛠️ /SkillCreator 專案擴充藍圖確認卡」並 End Turn 等待開發者授權；步驟 4 寫入 `config://agents-workflow/contribute.json` 後，強制依序執行 `contributes check` $\to$ `agents-workflow compile`（確認 0 Error / 0 Warning）$\to$ `agents-workflow release` 物化驗證。
- **[P00:DR-05] 全系統 22 個 Stage 1 Token 錨點完整收錄與 `SKILL_CREATOR_STANDARDS` 預留**：
  於 `contributes/agents-workflow.json` 新增第 21 個模組自身 Token `SKILL_CREATOR_STANDARDS`（連同 `knowledge-db` 註冊之 `KNOWLEDGE_DB_SPACE` 合為全系統 22 個已註冊 Token），並於 `references/extension-guide.md` 完整建檔，供下游與 Agent 查表即用。

---

## 3. 開放議題與確認紀錄

- 需求與架構邊界已由前置 [roadmap.md](./roadmap.md) 與主計畫藍圖完整定義，無開放未決議題，狀態直接標記為 `Confirmed`。

