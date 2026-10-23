# 技術路線圖：專案角色空間邊界宣告與跨模組設定體檢修復技能 (`how-to-config-yscb`) (Roadmap)

> 主題：專案角色空間邊界宣告與跨模組設定體檢修復技能 (`how-to-config-yscb`)  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在中大型下游專案引入 `ys-codebase`（YSCB）發布包（含 `agents-workflow` 及多個工具模組）以及第三方外部工具包時，實務運作存在兩大結構性缺口：
1. **缺乏「專案角色與主客體空間邊界（First-Party vs. External Toolkits）」常駐宣告，導致無效 Token 消耗**：
   - 對 Agent 而言，工作區內的所有資料夾預設皆被視為平等的源碼。當專案包含多個外部工具包（如 YSCB 工具模組、第三方 Vendor 庫或物化框架目錄）時，Agent 在執行理解專案、全局檢索或 `/discuss` 排查時，無法直接分辨「哪部分是本專案核心業務內容」與「哪部分是引用的外部工具包」，導致耗費大量 Context / Token 去深入翻閱外部工具包內部實作，甚至誤改工具包源碼。
2. **缺乏跨模組的「工具包設定狀況體檢與代寫配置引導（Config Doctor & Setup Coach）」**：
   - 下游專案引入多個 YSCB 模組後，往往不確定各模組的設定檔是否皆已正確配置、工作流語意空間與專案 Role 邊界是否已填寫、以及第一層組態修改後是否已正確編譯物化至第二層（`AGENTS.md`、`.agents/` 等）。

### 1.2 現況與影響範圍評估
- **架構定調：於 `AgentsStandards.md` 增設「專案角色與空間邊界」選配錨點，並建立由 `agents-workflow` 主導、各模組貢獻之主動指令型技能 `how-to-config-yscb`（與 `how-to-yscb`、`skill-creator` 獨立分工）**：
  1. **在 `AgentsStandards.md` 內建「專案角色與主客體空間邊界」宣告錨點（Turn 0 零延遲過濾）**：
     - 由於防止誤讀外部工具包屬於「搜尋前的負向過濾器（Pre-Search Filter）」，必須常駐於 Turn 0 視野（`AGENTS.md`）而非做成按需觸發的 `role` Skill。
     - 於 `AgentsStandards.md` 預留角色與邊界注入錨點，標準化宣告三要素：**① 開發者角色與專案核心目的**、**② 本體業務空間（First-Party Scope，開發與排查重心）**、**③ 外部工具包與黑盒依賴清單（External Toolkits，預設禁深讀內部實作、禁直接修改）**。未配置時由編譯器自動清除空錨點，僅花約 80～120 Tokens 即可為全專案省下數萬 Tokens 的無效檢索。
  2. **建立獨立主動指令型技能 `how-to-config-yscb`（診斷 ＋ 確認後直接代寫／修復配置）**：
     - 歸入 `how-to-*` 引導家族，專責「確認工具包使用與設定狀況良好，並協助配置專案 Role 邊界與各模組組態」。
     - **跨模組宣告式貢獻**：由 `agents-workflow` 提供基底組態與 Role 邊界體檢骨架，並預留跨模組設定注入錨點；各已安裝模組於錨點中注入精簡的**「模組設定與健康度速查卡（含必備設定項、健康度檢查方式、隨包設定手冊語意連結 `` [`設定手冊`](`__#{...}__`) ``）」**。
     - **確認後直接代寫／修復閉環**：Agent 自動探勘專案目錄與各模組設定現況後，向開發者呈遞「設定健康度報告與推薦配置草稿（含自動識別出的本體目錄 vs. 外部工具包清單）」，**經開發者確認後直接代寫／修復組態檔並完成編譯物化驗證**。
  3. **與相鄰技能的正交職責邊界**：
     - **`how-to-yscb`**：教日常使用者「怎麼使用已安裝的工具與下達黃金指令」。
     - **`how-to-config-yscb`**：幫專案維護者「體檢、配置與代寫修復 YSCB 各模組設定及 `AGENTS.md` 專案 Role 空間邊界」。
     - **`skill-creator`**：幫進階開發者「從零建立專案專屬的新 Skill 或階段防呆規則」。

### 1.3 核心根因
1. `AgentsStandards.md` 缺乏標準化的「專案角色定位與本體／外部工具包黑盒邊界」宣告結構，導致 `/discuss` 的「本體優先 vs. 外部組件」排查原則缺乏明確的目錄路徑依據。
2. 缺乏聚合各已安裝模組設定要求並支援自動體檢、草擬配置與代寫修復的互動式設定技能。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：將專案 Role 做成獨立 `role` Skill + 手動翻手冊改 Config** | 建立按需觸發的 `role/SKILL.md`；開發者自行翻閱各模組手冊手寫設定檔 | 不改動 `AGENTS.md` 結構 | **攔截失效**：Agent 在觸發 `role` Skill 前就已用 `grep/find` 掃描外部工具包污染 Context；且缺乏跨模組設定健康度檢查 | ⭐️⭐️ |
| **方案 2：`how-to-config-yscb` 僅做唯讀診斷，不代寫配置** | 檢查出缺失後僅印出教學說明，要求開發者自己去改 JSON 與設定檔 | 技能邏輯單純 | 開發者仍需手動編輯組態檔與記憶欄位格式，摩擦依然存在 | ⭐️⭐️⭐️ |
| **方案 3：`AgentsStandards.md` Role 邊界錨點 + `how-to-config-yscb` 體檢與確認後代寫修復（推薦採納）** | 將專案 Role 與外部工具包黑盒邊界注入 `AGENTS.md` 常駐視野；由 `how-to-config-yscb` 聚合各模組設定速查卡，執行「自動體檢 $\to$ 擬定配置草稿 $\to$ 確認後直接代寫修復與物化驗證」 | 1. **Turn 0 徹底阻斷亂翻外部工具包**<br/>2. **一鍵全身體檢所有已安裝模組設定**<br/>3. **確認後直接代寫修復**，零手寫組態負擔 | 需於 `AgentsStandards.md` 預留 Role 邊界錨點，並建立 `how-to-config-yscb` 技能與跨模組配置注入錨點 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（獨立 `role` Skill + 手動改設定） | 方案 3（`AGENTS.md` 邊界錨點 + `how-to-config-yscb` 體檢代寫） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | **極高（100% 複用雙層編譯錨點與檔案探勘能力）** |
| **防外部工具包 Token 浪費效果** | 低（按需載入太晚，無法攔截初期全局搜尋） | **最高（Turn 0 常駐視野直接標明主體目錄與黑盒工具包目錄）** |
| **專案接入與設定維護體驗** | 低（需逐一核對各模組設定手冊） | **最高（自動掃描診斷 + 擬定草稿 + 開發者點頭即代寫修復生效）** |
| **實戰上下文純淨度 (Context Purity)** | 中 | **最高（約 100 Tokens 邊界宣告換取整場對話不誤讀外部工具包；設定完成後開新 Session 實戰）** |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```markdown
# 1. AgentsStandards.md 專案角色與主客體空間邊界結構 (Turn 0 注入區塊)
- 開發者角色與專案使命：你是 [XXX 專案] 的開發人員，本專案核心目的為 [YYY]。
- 本體業務空間 (First-Party Scope)：[本專案自有源碼目錄清單]，日常開發與 /discuss 優先級 1~2 排查 100% 聚焦於此。
- 外部工具包與黑盒依賴 (External Toolkits)：[ZZZ / WWW 等外部工具包目錄] 為引用之外部工具，除查閱介面或隨包手冊外，嚴禁於排查或了解專案時浪費 Token 深入翻閱其內部實作或直接修改。

# 2. /how-to-config-yscb 四步體檢與代寫修復閉環
1. [步驟 1：全專案設定與空間拓撲自動探勘 (Auto-Discovery & Health Audit)]
   - 掃描專案目錄結構（識別本體源碼 vs. 外部工具包）、檢查專案 Role 邊界是否已配置，並檢查 `.gitignore` 是否已涵蓋 `*.local.json`
   - 依跨模組注入錨點內各模組之「配置速查與體檢卡」，逐一檢查各已安裝模組之設定檔、語意路徑映射與二層物化同步狀態

2. [步驟 2：呈遞「設定健康度報告與代寫提案卡」(Diagnosis & Draft Gate)]
   - 列出 [✅ 已就緒項目] 與 [⚠️ 待配置/異常項目]（含 `.gitignore` 之 `*.local.json` 檢查結果）
   - 針對缺失項（如未設定專案 Role 與外部工具包邊界、或缺少某模組組態），直接基於探勘結果擬定「推薦配置草稿」（預設自動將 `.modules/` 與常見第三方目錄納入外部工具包黑盒底盤，並自啟用之 `release_target` contribute 宣告動態解析二層物化唯讀空間），明確標示目標組態層級（`config.project.json` 團隊共享 vs. `config.local.json` 本機個人，或 `config://agents-workflow/snippets/project_role.md` 角色邊界片段），詢問開發者是否確認由 Agent 代寫修復並執行 `agents-workflow release` 物化同步

3. [步驟 3：授權後直接代寫／修復配置與三步嚴格編譯驗證守門 (Guided Fix & 3-Step Verification Gate)]
   - 獲開發者確認後（如需深入某模組特殊參數則按語意連結讀取該模組隨包手冊），透過 `yscb.py config set` 或標準組態空間路徑（`config://`，嚴禁直接修改 `.modules/` 運行空間）代寫或修復組態檔
   - 若修改觸及 `agents-workflow` 組態（如 `release_targets`、`contribute.json`）或第一層文檔片段（`config://agents-workflow/snippets/`、`config://agents-workflow/skills/`），強制依序自動串接執行：① `contributes check` $\to$ ② `agents-workflow compile`（確認 0 Error / 0 Warning）$\to$ ③ `agents-workflow release` 編譯物化驗證，確保根目錄規範檔與二層物化空間立即熱更新生效且無斷鏈異常

4. [步驟 4：新開實戰 Session 隔離提醒 (Clean-Session Handoff Notice)]
   - 提醒開發者：「設定已完成修復並生效！為載入最新物化之 AGENTS.md 並釋放最完整的 Agent 實戰能力，請開啟『全新對話 Session』進行開發，且不要觸發 /how-to-config-yscb」
```

### 4.1 雙核心組件規格設計

1. **組件一：`AgentsStandards.md` 專案角色與主客體空間邊界錨點 (`PROJECT_ROLE_AND_BOUNDARIES`)**：
   - 於 `AgentsStandards.md` 頂部預留選配注入錨點（`PROJECT_ROLE_AND_BOUNDARIES`），專門承接下游專案之角色與空間邊界定義。
   - **統一存放與跨平台同步規範（對齊現行 `config://agents-workflow/{snippets,skills}/` 扁平結構）**：下游專案之角色與空間邊界片段統一存放於 **`config://agents-workflow/snippets/project_role.md`**，並於 **`config://agents-workflow/contribute.json`** 宣告 `insert` 至 `PROJECT_ROLE_AND_BOUNDARIES` 錨點（與現行 `config/agents-workflow/contribute.json` 之 `snippets/` 與 `skills/` 第一層源碼存放慣例及 `skill-creator` 100% 統一，不額外嵌套冗餘 `assets/` 層級；編譯發布時自動同步物化至各啟用 `release_target` 宣告之 `agents_md` 託管區塊內，未配置時自動抹除空錨點）。
   - **預設外部工具包黑盒底盤與動態二層物化空間區分（防呆 1）**：
     - 當 `how-to-config-yscb` 為開發者草擬 `project_role.md` 時，預設自動將 **`module://`（`.modules/` YSCB 模組運行空間，僅查閱隨包 `README.md`）** 以及常見第三方目錄（如 `vendor/`、`third_party/`、`external/`）納入「外部工具包與黑盒依賴清單」候選草稿（禁止於排查業務邏輯時深讀其內部代碼或直接修改）。
     - 針對工作流二層物化目錄，**嚴禁硬編碼 `.agents/` 或 `.claude/`**，強制依據當前啟用之 `release_target` 在 `contributes` 中宣告的 `projections` 目標路徑動態解析，並於角色邊界中標註為**「工作流二層物化唯讀空間（按技能指引唯讀調用，嚴禁手動直接修改，所有客製化一律走第一層 `config://agents-workflow/`）」**。
   - **核心作用**：讓 Agent 在 Turn 0 立即建立「我是誰（專案角色）」、「我該改哪裡（本體業務目錄）」與「哪些目錄是外部工具包（禁止無故深讀源碼消耗 Token）」的空間認知，並直接作為 `/discuss` 三級排查（本體優先 $\to$ 呼叫端 $\to$ 外部工具包）的物理判定依據。
2. **組件二：`how-to-config-yscb` 技能與跨模組配置速查注入**：
   - **Frontmatter 極致精簡指令契約（主動指令型技能）**：
     ```yaml
     ---
     name: how-to-config-yscb
     description: 盤點與診斷專案內 YSCB 各模組組態、工作流空間映射及專案角色邊界設定狀況，並於確認後代寫修復配置。僅於顯式輸入 /how-to-config-yscb 或明確要求檢查與設定工具包組態時觸發。
     ---
     ```
   - **2x2 組態矩陣、`*.local.json` `.gitignore` 連動體檢與三步編譯守門（防呆 2）**：
     - **步驟 1 `.gitignore` 連動體檢**：探勘階段同步檢查專案或 `yscb://.gitignore` 是否已涵蓋 `*.local.json`（若未涵蓋則於體檢報告列為提醒與修復項），防止本機私密設定或個人路徑被誤 Commit 上傳。
     - **步驟 2 組態層級標示**：強制標明預計寫入之組態層級（`config://<mod>/config.project.json` 團隊共享組態、`config://<mod>/config.local.json` 本機個人組態，或 `config://agents-workflow/contribute.json` 擴充宣告），開發者對提案卡之確認同時構成步驟 3 執行 `agents-workflow release` 之顯式授權；**絕對禁止直接修改 `module://` (`.modules/`) 運行空間檔案**。
     - **步驟 3 先檢核後發布守門**：代寫配置後，強制先執行 `python yscb.py contributes check` 與 `python yscb.py agents-workflow compile` 確認 0 Error / 0 Warning，通過後方可執行 `python yscb.py agents-workflow release`。
   - **跨模組「模組設定與健康度速查卡（Config & Health Snippet）」注入規格與防膨脹契約**：
     由 `agents-workflow` 預留跨模組設定注入錨點，各模組透過組態注入精簡三要素，並**嚴格限制每模組 15 ~ 25 行以內（固定以 `### ⚙️ <模組名稱> 設定與體檢` 為三級標題）**：
     1. **組態項目與用途**：該模組所需之設定項、關鍵參數與預設行為。
     2. **健康度檢查條件（Health Check Criteria）**：如何判定該模組在當前專案已設定良好（如檢查組態欄位、索引狀態或執行 `yscb.py status` / `uri check` / `knowledge-db status` 等 `[SAFE]` 診斷指令）。
     3. **隨包設定手冊語意連結**：附上單反引號語意連結 `` [`<模組名稱> 隨包手冊`](`__#{module://<mod>/README.md}__`) ``，當開發者需要進階微調時由 Agent 按需讀取並代寫配置。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 列為 `Ready` 技術儲備，可與 `how-to-yscb` 及 `skill-creator` 構成完整的下游賦能三劍客（`/how-to-config-yscb` 管設定體檢與 Role 邊界、`/how-to-yscb` 管日常使用教學、`/skill-creator` 管擴充專屬技能）。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1 (`AgentsStandards.md` 專案 Role 邊界規範與 `how-to-config-yscb` 主技能建置)**：於 `AgentsStandards.md` 定義專案角色與本體／外部工具包黑盒邊界注入規範；建立 `how-to-config-yscb/SKILL.md`，實作「自動探勘體檢 $\to$ 擬定草稿確認 $\to$ 代寫修復與物化驗證 $\to$ 新開實戰 Session 提醒」四步閉環。
2. **Stage 2（跨模組配置速查卡錨點建置與規範定義）**：設定跨模組設定注入錨點，定義各模組貢獻「配置速查與體檢卡 ＋ 隨包手冊語意連結」之標準結構。
3. **Stage 3（各模組配置檢核接入與驗證）**：由 `agents-workflow` 與各核心模組注入設定檢核項，驗證配置代寫、物化同步與單反引號語意連結完整性。
