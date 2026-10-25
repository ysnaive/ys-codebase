# 需求規格說明書 (Requirements Specification)

> 功能名稱：專案特化技能建置與 Layer 2 宣告式擴充引導工作流 (sub_05_skill_creator_extension_workflow)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 建立主動指令型技能 `skill-creator/SKILL.md` 與三軌擴充智能分流 (`3-Track Extension Triage`) | 1. 於 `ys_codebase/source/agents-workflow/assets/skills/skill-creator/SKILL.md` 建立技能主檔，YAML Frontmatter `name: skill-creator`，`description` 採用主動指令型極簡契約：`引導建立專案功能特化 Skill、環境注意事項攔截規則或階段錨點注入配置，自動對接語意 URI 與雙層編譯註冊閉環。僅於顯式輸入 /skill-creator 或明確指示建立新 Skill 與擴充工作流規範時觸發。`（`[P01:DR-01]`）。<br/>2. 內建四步擴充與建置工作流檢核表，並於「步驟 1：需求意圖訪談與三軌分流」明確定義三大擴充軌跡判定矩陣：① **軌跡 ①（純錨點注入模式 `Anchor-Only Injection`）**：局部階段／熱啟動注意事項，不建新 Skill，直接於 `config://agents-workflow/snippets/<name>.md` 撰寫片段並注入既有 `__@{...}__` 錨點（0 路由開銷）；② **軌跡 ②（被動環境攔截型 Skill `Ambient Skill`）**：專案全局注意事項／工具攔截，於 `config://agents-workflow/skills/<name>/SKILL.md` 新建技能（採三段式結構化 `description`）並注入 `AGENTS_SKILL_ROUTING`；③ **軌跡 ③（功能特化型 Skill `Feature Skill`）**：專案特定子系統多步驟工作流，於 `config://agents-workflow/skills/<name>/SKILL.md` 新建技能（依觸發方式採極簡指令契約或三段式邊界）並註冊匯出與中樞/路由掛載。<br/>3. 尾部預留獨立行擴充錨點 `` `__@{SKILL_CREATOR_STANDARDS}__` `` 與 `## 常見踩坑指南 (Gotchas)`。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | 可用錨點與語意 URI 自動檢索及「擴充藍圖確認卡」強制守門 (`Discovery & Blueprint Gate`) | 1. 於 `skill-creator/SKILL.md`「步驟 2：可用錨點與語意 URI 自動檢索與提案確認」規範 Agent 自動調用 `[SAFE]` CLI 指令（`python yscb.py agents-workflow tokens` 與 `python yscb.py uri list`）並讀取同目錄參考手冊 `[references/extension-guide.md](./references/extension-guide.md)`，動態配對目標 Stage 1 錨點與 Stage 2 語意 URI。<br/>2. 強制規定在實際建立第一層檔案與修改 `config://agents-workflow/contribute.json` 前，必須向開發者呈遞 **「🛠️ /SkillCreator 專案擴充藍圖確認卡」**（包含：需求分類、預計產出資產 `config://agents-workflow/{skills,snippets}/`、掛載錨點、引用語意 URI、待確認事項）並立即 End Turn 等待拍板（開發者之確認同時構成後續執行 `agents-workflow release` 物化投影之顯式授權）。 | P0 | [P00:DR-03], [P00:DR-04] |
| **FR-03** | 合規第一層資產生成、路徑語意化分流與三步編譯驗證守門 (`Compliant Asset Generation & 3-Step Verification Gate`) | 1. 於 `skill-creator/SKILL.md`「步驟 3：合規資產生成與單反引號語法封裝」規定第一層源碼固定存放於扁平路徑 `config://agents-workflow/skills/<name>/SKILL.md`（及按需拆分之單層 `references/`）或 `config://agents-workflow/snippets/<name>.md`（嚴禁額外多套一層 `assets/`）。<br/>2. 明確規範路徑引用分流防呆：指向**同技能自身的 `references/`** 使用標準相對路徑（如 `./references/xxx.md`）；指向**其他技能、模板或專案目錄**強制使用單反引號包覆之語意 URI（如 `` [`text`](`__#{uri}__`) ``、`` `__${uri}__` ``）。<br/>3. 於「步驟 4：宣告式組態註冊與三步嚴格編譯驗證守門」規定以最小增量（Additive Edit）更新 `config://agents-workflow/contribute.json`，並強制依序執行：① `python yscb.py contributes check`（0 Error）$\to$ ② `python yscb.py agents-workflow compile`（Stage 1 試編譯，確認 0 Error / 0 Warning，無拼錯 Token 或裸寫標籤）$\to$ ③ 100% 通過後方可執行 `python yscb.py agents-workflow release` 物化至目標平台，最後呈遞極簡完成狀態卡（`[P01:DR-02]`）。 | P0 | [P00:DR-02], [P00:DR-03], [P00:DR-04] |
| **FR-04** | 建立單層擴充參考手冊 `references/extension-guide.md`（收錄全系統 22 個 Stage 1 Token 錨點地圖） | 1. 於 `ys_codebase/source/agents-workflow/assets/skills/skill-creator/references/extension-guide.md` 建立單層參考手冊，頂部具備 `## 目錄 (Contents)`（TOC）。<br/>2. 完整收錄並分類說明全系統 **22 個已註冊 Stage 1 Token 錨點地圖**（包含：`PHASEXX_HEADER`、`WORKFLOW_SOP_STANDARDS`、`AGENTS_STANDARDS`、`AGENTS_SKILL_ROUTING`、`AGENTS_CLI_GUIDE`、`WORKFLOW_CONTEXTINIT`、`RESEARCH_AGENTS_GUIDE`、`PHASE00_AGENTS_GUIDE`~`PHASE07_AGENTS_GUIDE`、`SKILL_OPTIMIZER_STANDARDS`、`TESTING_SOP_STANDARDS`、`PROJECT_ROLE_AND_BOUNDARIES`、`HOW_TO_CONFIG_MODULES`、`HOW_TO_YSCB_MODULES`、`KNOWLEDGE_DB_SPACE` 及本次新增之 `SKILL_CREATOR_STANDARDS`），標明各錨點宿主檔案位置、注入型態（獨立區塊 vs. 表格行）與適用場景。<br/>3. 完整說明 Stage 2 語意 URI（`__#{...}__` 路徑連結與 `__${...}__` 散文顯示路徑）轉換規則、單反引號防呆正反對照範例，以及 `config://agents-workflow/contribute.json` 針對軌跡 ①/②/③ 之最小增量 JSON 註冊範本。 | P0 | [P00:DR-03], [P00:DR-05] |
| **FR-05** | 模組組態註冊、中樞技能互指導流、單元測試與三層文檔同步 | 1. 於 `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` 及 `_manifest.md` 註冊 `skill-creator` 技能匯出（內建匯出技能總數由 16 個增為 17 個）與 `SKILL_CREATOR_STANDARDS` Token（模組自身 Token 由 20 個增為 21 個，全系統總計 22 個）。<br/>2. 於 `development-sop/SKILL.md` §1 生命週期工作流中樞分流與 `skill-optimizer/SKILL.md` 排除情境補齊 `/skill-creator` 導流連結。<br/>3. 更新 `tests/test_plans_model_record.py` 之 `test_ft_08`（納入 `"skill-creator"` 進行雙軌 `description`、零裸寫標籤與零特化耦合斷言），並新增 `test_ft_11_sub05_skill_creator_extension_workflow` 驗證 `skill-creator` 三軌分流、藍圖確認卡、單層參考手冊 22 個錨點完整性與三步編譯驗證守門。<br/>4. 同步更新 `ys_codebase/source/agents-workflow/README.md` 與 `docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}`，並完成 `@build` 安裝與 `agents-workflow release` 物化驗證。 | P0 | [P00:DR-01], [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `skill-creator/SKILL.md` 或 `references/extension-guide.md` 內文教學範例出現佔位符語法說明時，誤觸發 `ArtifactCompiler` 的 `Unenclosed placeholder tag` 或 `Unresolved semantic URI tag` 警告 | 凡在散文或表格中展示抽象佔位符語法格式（非指向真實存在之 Token 或 URI 路徑）時，嚴禁寫成可被編譯器正則直接匹配之真實佔位符格式（或於 Fenced Code Block 內展示、或使用非匹配結構說明）；所有真實語意標籤 100% 以單反引號包覆，確保 `python yscb.py agents-workflow compile` 0 Error / 0 Warning 且通過 `UNENCLOSED_TAG_REGEX` 剛性掃描（`[P01:DR-03]`）。 |
| **EC-02** | 下游僅需在特定階段（如 `Phase 05`）追加 5 行防呆規則，卻誤要求建立獨立新 Skill | `skill-creator` 步驟 1 強制依據「三大擴充軌跡判定矩陣」攔截，於步驟 2「擴充藍圖確認卡」主動推薦改採 **「軌跡 ①：純錨點注入模式（`Anchor-Only Injection`）」** 注入 `PHASE05_AGENTS_GUIDE`，避免無意義的技能路由表膨脹與上下文浪費。 |
| **EC-03** | 生成之新技能在引用自身 `references/` 時誤用跨模組語意 URI，或在引用其他技能時誤寫死 `.agents/skills/...` 硬編碼相對路徑 | 於步驟 3 與 `references/extension-guide.md` 設立明確的「同技能內部（`./references/...`）vs. 跨技能／跨空間（單反引號語意 URI）」雙軌路徑檢核規則，杜絕跨平台（Antigravity / Claude / Codex）投影時連結斷裂。 |
| **EC-04** | 下游組態 `config://agents-workflow/contribute.json` 寫入時拼錯 Token 名稱或遺漏單反引號，直接執行 `release` 污染第二層物化目錄 | 步驟 4 嚴格執行「先 `contributes check` $\to$ 次 `compile` $\to$ 0 錯誤與 0 警告後方可 `release`」的三步守門順序；若前兩步出現任何 Error 或 `[compiler:warning]`，強制原地修正第一層資產，嚴禁強行執行 `release`。 |
| **EC-05** | `AGENTS_SKILL_ROUTING` 屬於 Markdown 表格行內部錨點，而其餘錨點屬於獨立段落區塊錨點，注入格式混用導致排版破損 | 於 `references/extension-guide.md` 明確標註各錨點之結構屬性：注入 `AGENTS_SKILL_ROUTING` 的片段必須為 `\| **觸發條件** \| \`skill-name\` \|` 表格列格式；注入獨立區塊錨點的片段則為標準 Markdown 標題／清單段落。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 上下文經濟與漸進式揭露 | `skill-creator/SKILL.md` 主檔嚴格控制在 $\le 180$ 行（遠低於 500 行上限），將詳細的 22 個錨點地圖、URI 規則與 JSON 範本拆分至單層 `references/extension-guide.md`（頂部附 TOC），確保平時載入極致輕量。 |
| **NFR-02** | 通用去特化與零靜態組態污染 | `skill-creator/SKILL.md` 與 `references/extension-guide.md` 保持 100% 通用去特化（Zero Specialization Pollution，通過 `test_ft_08` 禁字掃描）；且開發過程中不在母倉 `ys_codebase/config/agents-workflow/` 預建任何測試用 dummy snippet 或 dummy skill。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 編譯器正則掃描與教學範例防呆（`[DN-AW-03]` / `[P01:DR-03]`）**：
  `ArtifactCompiler` 的 `UNENCLOSED_TAG_REGEX` 會掃描 Markdown 內未用單反引號包覆的標籤，而 `TOKEN_TAG_REGEX` / `URI_LINK_REGEX` / `URI_DISPLAY_REGEX` 會嘗試解析所有被單反引號包覆之標籤！因此，在撰寫教學文檔舉例說明抽象語法（例如想表達 `token_name` 或 `uri_path`）時，**切勿寫成單反引號包覆之假標籤**（否則 `compile` 時會報 `Unresolved semantic URI tag` 或未定義 Token），亦**切勿寫成未加反引號之雙底線標籤**（否則會報 `Unenclosed placeholder tag` 且使 `test_ft_08` 失敗）。教學抽象語法範例應統一置於 Fenced Code Block 內，或對真實存在的語意 URI／已註冊 Token 進行單反引號包覆展示。
- **`[!NOTE]` 階段決策彙整**：
  - **`[P01:DR-01]`**：`skill-creator` 採主動指令型極簡 Frontmatter 契約，並與 `skill-optimizer`、`development-sop` 形成雙向導流閉環。
  - **`[P01:DR-02]`**：第一層客戶端擴充資產路徑統一為扁平結構 `config://agents-workflow/skills/<name>/SKILL.md` 與 `config://agents-workflow/snippets/<name>.md`，並強制落實 `contributes check` $\to$ `compile` $\to$ `release` 三步編譯發布守門。
  - **`[P01:DR-03]`**：教學範例嚴格規避編譯器假陽性與未解析標籤警告，確保 `compile` 與 `test_ft_08` 100% 零警告通過。

