---
name: skill-creator
description: 引導建立專案功能特化 Skill、環境注意事項攔截規則或階段錨點注入配置，自動對接語意 URI 與雙層編譯註冊閉環。僅於顯式輸入 /skill-creator 或明確指示建立新 Skill 與擴充工作流規範時觸發。
---

# 專案特化技能建置與宣告式擴充工作流 (Skill Creator)

本工作流用於引導開發者在第一層組態空間（`__${config://agents-workflow}__/`）從零建立**專案功能特化 Skill**、**被動環境攔截型 Skill** 或**局部階段錨點注入片段（Snippet）**，並完成語意 URI 封裝、`__${config://agents-workflow}__/contribute.json` 宣告註冊與三步編譯發布驗證閉環。

---

## 適用情境與觸發時機

- **適用情境**：
  - 為專案特定子系統建立標準化多步驟開發或建置工作流（Feature Skill）。
  - 為專案高風險操作（如資料庫遷移、底層引擎修改、特定目錄寫入）建立自動攔截規範（Ambient Skill）。
  - 在既有開發階段（如 Phase 00 ~ Phase 07、`/context-init`、`testing-sop`）注入專案專屬防呆規則或檢查清單（Anchor-Only Injection）。
- **觸發時機**：開發者顯式輸入 `/skill-creator`，或明確要求建立新 Skill、新增工作流擴充規則與階段注入片段。
- **排除情境（負向邊界）**：
  - **審查或重構既有 Skill**：若目標 `SKILL.md` 已存在且需診斷觸發率、精簡行數或生成 A/B 評測，請改用 [`/skill-optimizer`](`__#{module://agents-workflow/assets/skills/skill-optimizer/SKILL.md}__`)。
  - **檢查或修復工具包基礎組態**：若需診斷 `config.project.json`、`config.local.json` 或初始化專案三大基礎片段，請改用 [`/how-to-config-yscb`](`__#{module://agents-workflow/assets/skills/how-to-config-yscb/SKILL.md}__`)。
  - **日常業務功能開發立項**：一般程式碼功能開發或 Bug 修復請走 [`/new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`)。

---

## 執行步驟

開始執行時，請複製以下檢核表追蹤擴充與建置進度：

```markdown
/SkillCreator 四步建置與擴充檢核表：
- [ ] 步驟 1：需求意圖訪談與三軌擴充智能分流（判定軌跡 ① 純錨點注入 / 軌跡 ② 環境攔截型 Skill / 軌跡 ③ 功能特化型 Skill）
- [ ] 步驟 2：執行 CLI 檢索可用錨點與語意 URI、讀取 extension-guide.md，呈遞「🛠️ /SkillCreator 專案擴充藍圖確認卡」並 End Turn 等待拍板
- [ ] 步驟 3：於第一層扁平路徑生成合規資產（落實雙軌 description、同技能相對路徑 vs. 跨空間單反引號語意 URI 分流）
- [ ] 步驟 4：最小增量更新 contribute.json，依序通過「contributes check -> compile -> release」三步驗證守門並呈遞完成卡
```

### 步驟 1：需求意圖訪談與三軌擴充智能分流 (`3-Track Extension Triage`)

根據開發者提出的規則或工作流需求，優先依下表判定最契合的擴充軌跡（若需求細節不明，遵守零臆測原則先行提問釐清）：

| 擴充軌跡 | 判定條件與特徵 | 第一層產出資產 (`__${config://agents-workflow}__/`) | 註冊與掛載方式 |
| :--- | :--- | :--- | :--- |
| **軌跡 ①：純錨點注入模式**<br>(`Anchor-Only Injection`) | 僅需在特定階段（如 `Phase 05` 實作、`Phase 06` 測試）或 `/context-init` 補充局部注意事項（$\le 15$ 行），無獨立多步流程 | `snippets/<name>.md`<br>*(不建立新 Skill，0 路由表膨脹)* | 於 `contribute.json` 宣告 `insert` 注入目標 Stage 1 錨點（如 `PHASE05_AGENTS_GUIDE`） |
| **軌跡 ②：被動環境攔截型 Skill**<br>(`Ambient / Guardrail Skill`) | 當 Agent 操作特定目錄、工具或領域代碼時必須自動攔截並遵循之完整規範 | `skills/<name>/SKILL.md` (+ 選配單層 `references/`)<br>`snippets/<name>_routing.md` | 宣告 `export` 匯出 Skill（採**三段式 `description`**），並 `insert` 表格列至 `AGENTS_SKILL_ROUTING` |
| **軌跡 ③：功能特化型 Skill**<br>(`Feature / Workflow Skill`) | 專案特定子系統的多步驟標準作業流（如自訂資產編譯、專項發布或特定分析流程） | `skills/<name>/SKILL.md` (+ 選配單層 `references/`) | 宣告 `export` 匯出 Skill（Slash 指令採**極簡契約**，或環境觸發採三段式），選配掛載路由或 `WORKFLOW_SOP_STANDARDS` |

> [!TIP]
> **過度建技攔截防呆（`EC-02`）**：若開發者要求「新增一個 Skill 來提醒 Phase 5 實作時注意某件事」，請主動在步驟 2 藍圖確認卡建議改採**「軌跡 ①：純錨點注入模式」**直接注入 `PHASE05_AGENTS_GUIDE`，避免技能路由表無謂膨脹。

### 步驟 2：可用錨點與語意 URI 自動檢索及「擴充藍圖確認卡」守門 (`Discovery & Blueprint Gate`)

1. **自動執行 `[SAFE]` 探勘指令與讀取參考手冊**：
   - 執行 `python __${yscb.host://yscb.py}__ agents-workflow tokens` 檢索當前全系統已註冊之 Stage 1 Token 錨點清單。
   - 執行 `python __${yscb.host://yscb.py}__ uri list` 檢索當前專案可用之 Stage 2 語意 URI 映射。
   - **[!] 強制按需載入**：讀取 [`references/extension-guide.md`](./references/extension-guide.md)，核對全系統 **24 個標準 Stage 1 錨點地圖**（含專案或模組自訂擴充錨點時以 CLI 實機輸出為準）之宿主位置與結構屬性（獨立段落區塊 vs. `AGENTS_SKILL_ROUTING` Markdown 表格列），以及 Stage 2 語意 URI 封裝規則。
2. **呈遞「擴充藍圖確認卡」並強制 End Turn 等待拍板**：
   在實際建立檔案或修改 `__${config://agents-workflow}__/contribute.json` 前，必須先向開發者輸出以下確認卡並**立即 End Turn**（開發者之確認同時構成步驟 4 執行正式物化發布之顯式授權）：

```markdown
### 🛠️ /SkillCreator 專案擴充藍圖確認卡
- **需求分類與選定軌跡**：[軌跡 ① 純錨點注入 / 軌跡 ② 被動環境攔截型 Skill / 軌跡 ③ 功能特化型 Skill]
- **預計產出第一層資產**：
  - [例如：`__${config://agents-workflow}__/skills/<name>/SKILL.md` 或 `__${config://agents-workflow}__/snippets/<name>.md`]
- **預計掛載之 Stage 1 錨點**：[例如：`AGENTS_SKILL_ROUTING` / `PHASE05_AGENTS_GUIDE` / 無]
- **預計引用之 Stage 2 語意 URI**：[例如：`project://plans/`、`workflow.docs://`、同技能 `./references/...`]
- **組態註冊變更**：將於 `__${config://agents-workflow}__/contribute.json` 增量更新 `[export / insert]` 宣告
- **待確認事項**：請問是否同意依此藍圖生成第一層擴充資產，並於驗證通過後執行 `release` 物化同步？
```

### 步驟 3：合規第一層資產生成與雙軌路徑語法封裝 (`Compliant Asset Generation`)

獲開發者確認後，遵循 [`references/extension-guide.md`](./references/extension-guide.md) §3 與 §5 規範生成第一層檔案：

1. **第一層扁平路徑鐵律**：
   - 專案自訂技能固定置於：`__${config://agents-workflow}__/skills/<name>/SKILL.md`（附屬參考檔置於單層 `skills/<name>/references/<file>.md`，長於 100 行須附 `## 目錄 (Contents)`）。
   - 專案自訂注入片段固定置於：`__${config://agents-workflow}__/snippets/<name>.md`。
   - **嚴禁**在 `__${config://agents-workflow}__/` 下多套一層 `assets/` 目錄，亦**嚴禁**直接寫入由 `release_target` 之 `projections` 定義的第二層物化投影空間。
2. **雙軌結構化 `description` 契約**：
   - **被動環境攔截型（軌跡 ②）**：採用三段式 `核心用途與支援範圍。觸發情境：...。排除情境：...。`
   - **主動指令型（軌跡 ③ Slash 指令）**：採用極簡契約 `1 句話核心目的與交付物。僅於顯式輸入 /<name> 或明確指示<核心動作>時觸發。`
   - 每個新 `SKILL.md` 必須控制在 **500 行以內**，並內建步驟檢核表與 `## 常見踩坑指南 (Gotchas)`。
3. **雙軌路徑引用與單反引號封裝防呆（`EC-01`, `EC-03`）**：
   - **指向同技能自身的 `references/`**：一律使用標準相對路徑（如 `[參考手冊](./references/xxx.md)`）。
   - **指向其他技能、標準模板或專案空間路徑**：強制使用**單反引號包覆**之 Stage 2 語意 URI（穿插路徑如 `__${config://agents-workflow}__/contribute.json` 可於物化後保留行內反引號格式）。
   - **教學與範例區塊保護**：若技能或參考手冊內文需展示不被編譯器解算之字面量動態標籤語法，須置於首行標註 `<!-- yscb:literal -->` 之三反引號 Fenced Code Block 內保護：

```markdown
<!-- yscb:literal -->
- Stage 1 錨點（獨立行）：`__@{SKILL_CREATOR_STANDARDS}__`
- Stage 2 跨檔超連結：[`/new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`)
- Stage 2 顯示路徑：`__${project://plans}__/` 或 `__${config://agents-workflow}__/contribute.json`
```

### 步驟 4：宣告式組態註冊與三步嚴格編譯驗證守門 (`3-Step Verification Gate`)

1. **最小增量更新 `__${config://agents-workflow}__/contribute.json`**：
   依 [`references/extension-guide.md`](./references/extension-guide.md) §4 範本，以最小增量（Additive Edit）將新條目加入 `export` 或 `insert` 陣列，保留既有全部設定；並確認 `export.description` 與 `SKILL.md` Frontmatter `description` 完全一致。
2. **強制依序執行三步編譯驗證守門（`EC-04`）**：
   - **守門 ①（組態 Schema 檢核）**：執行 `python __${yscb.host://yscb.py}__ contributes check`，確認 `0 Errors`。
   - **守門 ②（Stage 1 試編譯與語法檢核）**：執行 `python __${yscb.host://yscb.py}__ agents-workflow compile`，嚴格確認輸出 **0 Error 且 0 `[compiler:warning]`**（無拼錯之 Token 名稱、無未包覆反引號之標籤）。
   - **異常阻斷**：若守門 ① 或守門 ② 出現任何錯誤或警告，**嚴禁執行下一步 `release`**！必須立即回到步驟 3 或步驟 4 修正第一層檔案並重驗至 100% 乾淨通過。
   - **守門 ③（Stage 2 正式物化投影）**：前兩步 100% 通過後，執行 `python __${yscb.host://yscb.py}__ agents-workflow release` 將資產物化至目標平台目錄。
3. **呈遞極簡完成狀態卡**：輸出產出之第一層檔案路徑、物化後之第二層目標路徑與三步驗證結果，並提示開發者可開啟新對話或直接體驗新技能。

`__@{SKILL_CREATOR_STANDARDS}__`

---

## 常見踩坑指南 (Gotchas)

- **切勿直接手動新建或修改第二層物化投影目錄（由生效之 `release_target.projections` 定義）下的檔案**：第二層空間屬於編譯發布產物，下次執行 `agents-workflow release` 時會被覆蓋；所有自訂技能與片段必須建於第一層 `__${config://agents-workflow}__/`。
- **切勿將獨立段落格式注入 `AGENTS_SKILL_ROUTING`（`EC-05`）**：`AGENTS_SKILL_ROUTING` 位於 `AgentsStandards.md` 的 Markdown 表格內部，注入該錨點的 snippet 必須是 `| **觸發條件** | \`skill-name\` |` 表格列格式。
- **切勿在散文中裸寫未加反引號之動態標籤或假造不存在的語意 URI（`EC-01`）**：真實語意標籤必須以單反引號包覆，抽象語法教學範例必須置於三反引號 Fenced Code Block 內，否則會在 `compile` 階段觸發警告。
