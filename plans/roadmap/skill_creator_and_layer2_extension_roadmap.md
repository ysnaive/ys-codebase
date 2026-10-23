# 技術路線圖：專案特化技能建置與 Layer 2 宣告式擴充引導工作流 (`skill-creator`) (Roadmap)

> 主題：專案特化技能建置與 Layer 2 宣告式擴充引導工作流 (`skill-creator`)  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在 `agents-workflow` 的「純淨通用基底（Layer 1）＋ 下游宣告式注入與多平台投影（Layer 2）」架構下，下游專案在接入與日常演進時，高頻出現兩大客製化擴充需求：
1. **添加針對專案特定功能特化的 Skill（Feature-Specialized Skill）**：例如針對專案特有子系統、業務模組開發規範或專屬工具鏈建立獨立 SOP 技能。
2. **添加針對專案注意事項的環境 Skill 或階段守門規則（Ambient Guardrails / Stage Injection）**：例如專案特有的架構禁令、目錄與工具調用攔截規則，或在特定開發階段（如熱啟動、`Phase 02` 架構、`Phase 05` 編碼）追加專案防呆事項。

然而在缺乏專屬引導技能的情況下，下游開發者與 Agent 面臨三大接入門檻，導致許多下游專案放棄使用 `agents-workflow` 的雙層編譯管線，轉而直接在第二層目錄（如 `.agents/skills/` 或 `.claude/skills/`）手寫一次性 Skill：
1. **決策斷層（「注入既有錨點」vs.「新建獨立 Skill」分界不明）**：不清楚何時只需將幾行專案注意事項注入既有 Stage 1 錨點（如 `__@{PHASE05_AGENTS_GUIDE}__`），何時才需要獨立建立 `SKILL.md` 並掛載至 `__@{AGENTS_SKILL_ROUTING}__`，容易造成「為 5 行規則建一個新 Skill」的路由膨脹，或直接去硬改物化後的 `AGENTS.md`。
2. **檢索與語法斷層（查找可用錨點與語意 URI 成本過高）**：在不翻閱底層定義的情況下，難以直覺掌握系統有哪些預留錨點（`__@{...}__`）與語意 URI（`__#{...}__`、`__${...}__`）可用，且常遺忘單反引號包覆契約（`[DN-AW-03]`），退化為寫死硬編碼相對路徑。
3. **持久性斷層（繞過組態註冊直接修改第二層物化檔）**：因不熟悉第一層源碼與組態宣告流程，直接於第二層建立一次性 Skill，不僅喪失跨平台（Antigravity / Claude / Codex）自動投影能力，更會在下次執行工作流更新時遭覆蓋遺失。

### 1.2 現況與影響範圍評估
- **架構定調：新增獨立主動指令型技能 `skill-creator`，與 `skill-optimizer` 形成「建立與掛載 $\leftrightarrow$ 診斷與重構」全生命週期閉環**：
  1. **明確職責分工**：
     - **`skill-creator`（事前建置與 Layer 2 掛載）**：負責引導下游從零建立符合雙層編譯規範的「專案功能特化 Skill」、「環境攔截型 Skill」或「階段錨點注入片段」，自動完成可用錨點／URI 檢索映射與組態註冊。
     - **`skill-optimizer`（事後體檢與無損重構）**：負責針對已存在的 `SKILL.md` 執行五維度靜態診斷、漸進式揭露拆分與 A/B 基準評測。
  2. **三軌擴充智能分流（3-Track Extension Triage）**：
     - 針對下游需求自動判斷最適載體：① 輕量階段注意事項導向**「純錨點注入（Anchor-Only Injection，0 路由開銷）」**；② 全局環境注意事項導向**「被動環境攔截型 Skill（三段式 `description` + `AGENTS_SKILL_ROUTING` 掛載）」**；③ 特定功能 SOP 導向**「功能特化型 Skill（主動指令型或中樞導流型）」**。
  3. **內建錨點與語意 URI 自動檢索映射與單反引號防呆**：
     - 由 `skill-creator` 引導 Agent 自動調取系統既有之錨點與 URI 清單（或查閱隨附速查參考檔），在生成草案時自動將路徑轉譯為單反引號包覆之 `` `__@{...}__` ``、`` [`text`](`__#{...}__`) `` 與 `` `__${...}__` ``，讓下游開發者以「純自然語言描述需求」即可產出 100% 合規的第一層資產與組態宣告。

### 1.3 核心根因
1. 現有技能組僅提供針對既有技能的審查工具（`skill-optimizer`），缺乏針對下游「從零建立專案特化／環境 Skill 並對接雙層編譯錨點與 URI」的引導工作流。
2. 系統雖已具備完整的錨點、語意 URI 與組態注入能力，但缺乏面向 Agent 與下游開發者的「意圖分流決策樹」與「自動化組態掛載閉環」指引。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：維持現狀（僅靠文檔說明與手動查閱組態）** | 下游開發者自行翻閱文檔查找可用錨點與 URI，手動撰寫 `SKILL.md` 與組態檔 | 無需新增技能資產 | 認知與查表門檻高，下游極易繞過編譯管線直接手寫一次性二層 Skill，導致升級覆蓋與跨平台失步 | ⭐️⭐️ |
| **方案 2：將建立與錨點掛載邏輯塞入 `skill-optimizer`** | 擴充 `skill-optimizer` 同時負責「從零建立新 Skill」、「錨點注入」與「既有 Skill 審查重構」 | 不增加技能數量 | 違反單一職責原則；「五維度靜態審查 + A/B 評測」與「下游需求分流 + URI/錨點組態掛載」流程截然不同，混在同一主檔會導致上下文膨脹與觸發邊界模糊 | ⭐️⭐️⭐️ |
| **方案 3：建立獨立主動指令型技能 `skill-creator`（推薦採納）** | 新增專責「三軌擴充模式分流、可用錨點/URI 自動檢索映射、合規 `SKILL.md` 生成與宣告式組態掛載」之 `skill-creator` 技能 | 1. **下游零學習成本**：自然語言提出需求即可自動配對最佳錨點與 URI<br/>2. **杜絕一次性野雞 Skill**：強制走第一層源碼與組態宣告閉環，100% 具備跨平台投影能力<br/>3. **與 `skill-optimizer` 職責正交**：建立歸 `skill-creator`，體檢重構歸 `skill-optimizer` | 需新增 `skill-creator` 技能目錄與對應參考手冊 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（手動查表配置） | 方案 2（併入 `skill-optimizer`） | 方案 3（獨立 `skill-creator` 技能） |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 中（主檔行數與流程分支易超標） | **極高（直接複用現有錨點、URI 與組態機制）** |
| **下游接入體驗 (Developer UX)** | 低（需理解底層語法細節） | 中 | **最高（對話式引導自動完成分流、URI 替換與註冊）** |
| **可靠性與合規度 (Reliability)** | 低（易漏單反引號或寫死路徑） | 高 | **極高（內建 `[DN-AW-03]` 單反引號與雙軌 `description` 生成檢核）** |
| **後續維護難度 (Maintenance)** | 高（下游一次性 Skill 易腐敗） | 中 | **極低（純規範與引導層封裝，與底層實作解耦）** |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```markdown
# /skill-creator 四步擴充與建置工作流閉環
1. [步驟 1：需求意圖訪談與三軌分流 (3-Track Triage)]
   - 軌跡 ① (輕量階段/環境注意事項) -> 判定為「純錨點注入模式 (Anchor-Only Injection)」，不建新 Skill，直接鎖定目標 __@{...}__ 錨點
   - 軌跡 ② (專案全局注意事項/工具攔截) -> 判定為「被動環境攔截型 Skill (Ambient Skill)」，配對三段式 description + __@{AGENTS_SKILL_ROUTING}__ 注入
   - 軌跡 ③ (專案特定功能 SOP/工作流) -> 判定為「功能特化型 Skill (Feature Skill)」，依觸發性質配對極簡指令契約或三段式邊界 + 中樞/分流表掛載

2. [步驟 2：可用錨點與語意 URI 自動檢索與提案確認 (Discovery & Blueprint Gate)]
   - 調取系統可用之 Stage 1 錨點清單 (__@{...}__) 與 Stage 2 語意 URI 清單 (__#{...}__, __${...}__)
   - 呈遞「擴充藍圖確認卡」（含推薦軌跡、目標存放位置、預計使用之語意 URI、預計掛載之錨點），強制 End Turn 等待開發者拍板

3. [步驟 3：合規資產生成與單反引號語法封裝 (Compliant Asset Generation)]
   - 依拍板藍圖於 `config://agents-workflow/assets/` 生成 SKILL.md（及按需拆分之單層 references/）或錨點注入片段
   - 自動執行路徑語意化轉換，並強制套用單反引號包覆（`__@{token}__`、[`text`](`__#{uri}__`)、`__${uri}__`）與雙軌 description 規範

4. [步驟 4：宣告式組態註冊與三步嚴格編譯驗證守門 (Declarative Registration & 3-Step Verification Gate)]
   - 以最小增量方式（Additive Edit）將新資產與錨點注入項註冊至 `config://agents-workflow/contribute.json`
   - 強制依序執行：① `contributes check`（確認組態 Schema 與錨點宣告 0 Error）$\to$ ② `agents-workflow compile`（Stage 1 試編譯，確認 0 `[compiler:warning]` 裸寫標籤警告且尚未改動第二層目錄）$\to$ ③ 100% 通過後方可執行 `agents-workflow release` 物化至目標平台，防止錯誤組態覆寫第二層環境，最後輸出極簡完成狀態卡
```

### 4.1 `skill-creator` 技能規格與雙軌契約設計

1. **Frontmatter 極致精簡指令契約（主動指令型技能）**：
   ```yaml
   ---
   name: skill-creator
   description: 引導建立專案功能特化 Skill、環境注意事項攔截規則或階段錨點注入配置，自動對接語意 URI 與雙層編譯註冊閉環。僅於顯式輸入 /skill-creator 或明確指示建立新 Skill 與擴充工作流規範時觸發。
   ---
   ```
   *(同時支援於 `development-sop` 或 `AgentsStandards.md` 註解說明中按需導流：當下游開發者要求「新增專案專屬 Skill 或環境注意事項」時引導使用 `/skill-creator`。)*

2. **核心機制一：三大擴充軌跡判定矩陣（防止過度建立碎片 Skill）**：
   `skill-creator` 在步驟 1 強制協助開發者區分「這段規則該放哪裡最省 Token 且最不會漏觸發」：

   | 下游需求類型 | 判定條件 | 推薦擴充軌跡 | 路由與 Token 影響 |
   | :--- | :--- | :--- | :--- |
   | **A. 局部階段／熱啟動注意事項** | 僅在特定時機（如 `/context-init`、`Phase 02` 架構、`Phase 05` 編碼、`Phase 07` 結案）生效之簡短防呆規則 | **軌跡 ①：純錨點注入模式**<br>*(不新建 Skill，直接注入既有 `__@{...}__`)* | **0 額外路由開銷**：僅在進入該階段時隨宿主檔案按需載入 |
   | **B. 專案環境注意事項／工具攔截** | 涉及特定目錄、特定工具呼叫或跨階段領域規範，不遵守會違反團隊工程標準之長篇規範 | **軌跡 ②：被動環境攔截型 Skill**<br>*(新建 `SKILL.md` + 注入 `__@{AGENTS_SKILL_ROUTING}__`)* | 採用**三段式結構化 `description`**，並掛載於全域條件式分流表強制攔截 |
   | **C. 專案特定功能工作流** | 針對專案特定子系統之多步驟建置、打包、遷移或專屬業務 SOP | **軌跡 ③：功能特化型 Skill**<br>*(新建 `SKILL.md` + 註冊匯出與中樞/路由掛載)* | 屬 Slash 主動呼叫者採**極簡指令契約**；屬意圖自動觸發者採**三段式結構化邊界** |

3. **核心機制二：標準存放空間 (`config://agents-workflow/assets/`)、錨點／URI 自動檢索與語法防呆**：
   - **第一層源碼與組態唯一標準位置（去特化純淨基底）**：
     - 專案特化 Skill 或注入片段之第一層源碼固定存放於 **`config://agents-workflow/assets/`**（例如 `config://agents-workflow/assets/skills/<name>/SKILL.md`），並於 **`config://agents-workflow/contribute.json`** 中以 `config://...` URI 宣告 `export` 與 `insert`。
     - 通用 `skill-creator` 嚴格保持去特化（不混入特定模組開發路徑說明），並暴露 `SKILL_CREATOR_STANDARDS` 擴充錨點供進階開發模組按需注入專屬分流選項。
   - **自動盤點可用資源**：Agent 執行 `skill-creator` 時，直接調用系統 `[SAFE]` CLI（`python yscb.py agents-workflow tokens` 與 `python yscb.py uri list`）並搭配內建參考指南（`references/extension-guide.md`）動態檢索：
     1. **系統預留之 Stage 1 注入錨點（`__@{...}__`）**：例如全域條件分流表錨點（`AGENTS_SKILL_ROUTING`）、CLI 權限表錨點（`AGENTS_CLI_GUIDE`）、熱啟動錨點（`WORKFLOW_CONTEXTINIT`）、SOP 主檔與各階段錨點（`WORKFLOW_SOP_STANDARDS`、`PHASE00_AGENTS_GUIDE` ～ `PHASE07_AGENTS_GUIDE`）、調研與技能審查錨點（`RESEARCH_AGENTS_GUIDE`、`SKILL_OPTIMIZER_STANDARDS`）。
     2. **系統與專案可用之 Stage 2 語意 URI（`__#{...}__` 與 `__${...}__`）**：例如指向專案根目錄、組態空間 (`config://`) 與計畫／文檔空間的語意協議，以及指向基底模組資產的跨檔案連結協議。
   - **生成期路徑分流與語法強制轉換（防呆 1：同技能內部 vs. 跨技能語意 URI）**：
     - **指向同技能自身的 `references/`**：直接使用標準相對路徑（如 `[參考手冊](./references/xxx.md)`），因為發布器會將整個技能目錄原樣遞迴複製至第二層物化目錄。
     - **指向其他技能、模板或專案目錄**：嚴禁寫死目標平台的物化相對路徑（如 `../../.agents/skills/...`），強制使用**單反引號包覆之語意 URI**（如 `` [`development-sop`](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`) ``、`` `__${project://...}__` ``、`` `__#{config://...}__` ``），確保 100% 通過編譯器標籤檢查。

4. **核心機制三：強制藍圖討論卡點（Mandatory Blueprint Gate）與步驟 4 先檢核後發布守門（防呆 2）**：
   - 在實際寫入檔案與修改組態前，`skill-creator` 必須先向開發者呈遞極簡**「擴充藍圖確認卡」**並 End Turn（開發者之確認同時構成後續執行 `agents-workflow release` 物化投影之顯式授權）：
     ```markdown
     ### 🛠️ /SkillCreator 專案擴充藍圖確認卡
     - **需求分類**：[軌跡 ① 純錨點注入 | 軌跡 ② 環境攔截型 Skill | 軌跡 ③ 功能特化型 Skill]
     - **預計產出資產 (`config://agents-workflow/assets/`)**：[新建 Skill 名稱與參考檔規劃 / 或純注入片段說明]
     - **掛載錨點 (`__@{...}__`)**：[預計於 `config://agents-workflow/contribute.json` 注入之目標錨點名稱與觸發條件]
     - **引用語意 URI (`__#{...}__` / `__${...}__`)**：[預計於內文引用之標準語意 URI 清單（同技能內部 `references/` 則採 `./references/...`）]
     - **待確認事項**：請問是否同意此擴充藍圖？確認後將生成第一層資產、寫入 `contribute.json`，並依序通過 `contributes check` 與 `compile` 檢核後執行 `agents-workflow release` 物化驗證。
     ```
   - **步驟 4 嚴格守門順序（防呆 2）**：獲確認並完成資產生成與最小增量組態註冊後，**強制規定必須先執行 `python yscb.py contributes check` 與 `python yscb.py agents-workflow compile` 並確認 0 Error / 0 Warning（包含攔截拼錯的鍵名/錨點名與未加單反引號的裸寫標籤），全數通過後方可執行 `python yscb.py agents-workflow release`**，防止錯誤組態污染第二層物化環境；同時自動對齊 `skill-optimizer` 核心合規清單（Frontmatter 雙軌規範、`< 500` 行上限、單層 `references/`、Gotchas 區塊與單反引號標籤完整性）。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 列為 `Ready` 技術儲備，待團隊排程啟動時，可由開發團隊依據當下專案與下游組態規範決定具體資產存放路徑與 CLI 調用細節，透過 `/new-plan` 開立標準計畫落地。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1 (`skill-creator` 主檔與三軌分流工作流建置)**：建立 `skill-creator/SKILL.md`（採用主動指令型極簡 `description` 契約），定義「三軌擴充模式判定樹」、「擴充藍圖確認卡 Checkpoint」與「生成後編譯驗證閉環」。
2. **Stage 2（錨點、語意 URI 與組態掛載參考手冊建置）**：建立附屬單層參考手冊（如 `references/extension-guide.md`），彙整系統可用之 Stage 1 錨點地圖、Stage 2 語意 URI 轉換規則、單反引號防呆範例與宣告式組態（`export` / `insert`）最小增量註冊範本。
3. **Stage 3（組態匯出註冊與測試驗證）**：將 `skill-creator` 納入 `agents-workflow` 標準匯出技能清單，補齊結構與標籤合規單元測試並完成自部署驗證。
