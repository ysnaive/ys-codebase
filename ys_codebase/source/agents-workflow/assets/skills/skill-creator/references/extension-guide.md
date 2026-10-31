# 專案特化技能與 Layer 2 宣告式擴充參考指南 (Skill Creator & Layer 2 Extension Guide)

本指南為 [`/skill-creator`](../SKILL.md) 的單層按需參考手冊，完整收錄雙階段語意編譯架構下之 **24 個已註冊 Stage 1 Token 錨點地圖**、**Stage 2 語意 URI 轉換與單反引號封裝規則**，以及三大擴充軌跡之 `config://agents-workflow/contribute.json` 最小增量配置範本。

## 目錄 (Contents)

- [1. 雙層物化架構與三大擴充軌跡總覽](#1-雙層物化架構與三大擴充軌跡總覽)
- [2. 全系統 24 個 Stage 1 Token 錨點地圖 (Token Anchor Map)](#2-全系統-24-個-stage-1-token-錨點地圖-token-anchor-map)
- [3. Stage 2 語意 URI 轉換與單反引號語法防呆](#3-stage-2-語意-uri-轉換與單反引號語法防呆)
- [4. 三軌擴充之 contribute.json 最小增量配置範本](#4-三軌擴充之-contributejson-最小增量配置範本)
- [5. 新建 Skill 結構與雙軌 Description 檢核清單](#5-新建-skill-結構與雙軌-description-檢核清單)

---

## 1. 雙層物化架構與三大擴充軌跡總覽

工作流系統嚴格區分「第一層宣告式源碼空間（Layer 1 Source / Config SSOT）」與「第二層平台物化投影空間（Layer 2 Materialized Target）」：

- **第一層（唯一可寫入之 SSOT）**：
  - 專案客製化技能：`__${config://agents-workflow}__/skills/<skill-name>/SKILL.md`（及選配之單層 `references/<file>.md`）
  - 專案客製化注入片段：`__${config://agents-workflow}__/snippets/<snippet-name>.md`
  - 專案擴充宣告檔：`__${config://agents-workflow}__/contribute.json`
- **第二層（編譯器自動投影之唯讀產物，嚴禁直接手改）**：
  - 依當前生效之 `release_targets` 與 `contributes` 中 `release_target.projections` 映射設定，動態投影至目標平台之二層物化目錄（`skills` / `templates` / `standards`）與根目錄規範入口檔受託管區塊（亦支援使用者透過 `contribute` 自訂擴充之發布目標）。

> [!CAUTION]
> **第一層目錄扁平化鐵律**：在 `__${config://agents-workflow}__/` 下存放專案自訂資產時，路徑固定為 `skills/<name>/SKILL.md` 或 `snippets/<name>.md`，**嚴禁在中間額外套一層 `assets/` 目錄**！

---

## 2. 全系統 24 個 Stage 1 Token 錨點地圖 (Token Anchor Map)

執行 `python __${yscb.host://yscb.py}__ agents-workflow tokens` 可即時查詢當前環境已安裝模組與專案自訂 `contribute` 註冊之所有 Stage 1 錨點。下表為標準生態系模組提供之 **24 個內建錨點**（`agents-workflow` 內建 23 個 ＋ `knowledge-db` 選配模組註冊 1 個；若專案或額外模組自訂擴充新 Token，以 CLI 實機查詢結果為準）之完整對照地圖：

### 2.1 全域行為準則、角色邊界與技能路由錨點（3 個）

| Token 名稱 | 宿主檔案位置 | 結構屬性 | 注入用途與適用場景 |
| :--- | :--- | :---: | :--- |
| `PROJECT_ROLE_AND_BOUNDARIES` | `AgentsStandards.md` §0（核心原則之前） | 獨立段落區塊 | 注入專案開發者角色定位、第一方業務源碼範圍 (`First-Party Scope`) 與外部黑盒邊界 |
| `AGENTS_SKILL_ROUTING` | `AgentsStandards.md` §2 條件路由表內 | **Markdown 表格列** | **軌跡 ② / ③ 必用**：將新增之專案 Skill 掛載至全域條件觸發路由表（必須為 `\| **條件** \| \`skill\` \|` 表格行格式） |
| `AGENTS_STANDARDS` | `AgentsStandards.md` 尾部 | 獨立段落區塊 | 注入全專案共通之額外行為紀律或全域鐵律 |

### 2.2 核心中樞與專項技能擴充錨點（11 個）

| Token 名稱 | 宿主檔案位置 | 結構屬性 | 注入用途與適用場景 |
| :--- | :--- | :---: | :--- |
| `WORKFLOW_SOP_STANDARDS` | `development-sop/SKILL.md` 尾部 | 獨立段落區塊 | 注入專案特化之開發流程規範，或於中樞掛載 **軌跡 ③（功能特化型 Skill）** 之按需導流說明 |
| `WORKFLOW_CONTEXTINIT` | `context-init/SKILL.md` | 獨立段落區塊 | 注入 `/context-init` 對話熱啟動時需額外載入或檢查之專案特化步驟 |
| `AGENTS_CLI_GUIDE` | `yscb-cli-guide/SKILL.md` | 獨立段落區塊 | 注入專案或模組專屬之 CLI 子命令速查與權限守門規則 |
| `TESTING_SOP_STANDARDS` | `testing-sop/SKILL.md` §4 | 獨立段落區塊 | 注入專案專屬測試執行指令、測試目錄命名規範與測試框架基底類別契約 |
| `RESEARCH_AGENTS_GUIDE` | `research/SKILL.md` | 獨立段落區塊 | 注入 `/research` 技術調研階段之專案特化檢索或評估指引 |
| `SKILL_OPTIMIZER_STANDARDS` | `skill-optimizer/SKILL.md` 尾部 | 獨立段落區塊 | 注入 `/skill-optimizer` 審查既有技能時之專案特化檢核規則 |
| `SKILL_CREATOR_STANDARDS` | `skill-creator/SKILL.md` 尾部 | 獨立段落區塊 | 注入 `/skill-creator` 建立新技能或擴充配置時之專案特化命名或目錄規範 |
| `SESSION_AUDIT_STANDARDS` | `session-audit/SKILL.md` §2 | 獨立段落區塊 | 注入 `/session-audit` 事後隱形摩擦自檢時之專案特化歸因規則或檢核項 |
| `CODE_OPTIMIZER_STANDARDS` | `code-optimizer/SKILL.md` 尾部 | 獨立段落區塊 | 注入 `/code-optimizer` 業務代碼五維度診斷、專案架構慣例 (`D5`) 與無損重構驗證規則 |
| `HOW_TO_CONFIG_MODULES` | `how-to-config-yscb/SKILL.md` | 獨立段落區塊 | 聚合各已安裝模組之設定項目、健康檢查條件與隨包手冊連結 (`config_guide.md`) |
| `HOW_TO_YSCB_MODULES` | `how-to-yscb/SKILL.md` | 獨立段落區塊 | 聚合各已安裝模組之定位、標準用法速查 (`Golden Recipes`) 與手冊連結 (`usage_guide.md`) |

### 2.3 Full Track SOP 八大階段專屬擴充錨點（9 個）

| Token 名稱 | 宿主檔案位置 | 結構屬性 | 注入用途與適用場景 |
| :--- | :--- | :---: | :--- |
| `PHASEXX_HEADER` | `P00` ~ `P07` 計畫模板頂部 | 獨立段落區塊 | 系統內建用於注入標準計畫標頭 (`header.md`)，一般專案無須覆寫 |
| `PHASE00_AGENTS_GUIDE` | `references/phase_00_discuss.md` | 獨立段落區塊 | **軌跡 ① 常用**：注入 Phase 0 需求討論與前置程式碼探索之專案注意事項 |
| `PHASE01_AGENTS_GUIDE` | `references/phase_01_requirements.md` | 獨立段落區塊 | **軌跡 ① 常用**：注入 Phase 1 需求規格定義與邊界條件盤點之專案注意事項 |
| `PHASE02_AGENTS_GUIDE` | `references/phase_02_architecture.md` | 獨立段落區塊 | **軌跡 ① 常用**：注入 Phase 2 架構設計、圖表規範與測試預排之專案注意事項 |
| `PHASE03_AGENTS_GUIDE` | `references/phase_03_api_spec.md` | 獨立段落區塊 | **軌跡 ① 常用**：注入 Phase 3 公開介面簽名、型別與錯誤契約之專案注意事項 |
| `PHASE04_AGENTS_GUIDE` | `references/phase_04_plan.md` | 獨立段落區塊 | **軌跡 ① 常用**：注入 Phase 4 實作計畫定稿、文檔衝擊與測試定稿之專案注意事項 |
| `PHASE05_AGENTS_GUIDE` | `references/phase_05_task.md` | 獨立段落區塊 | **軌跡 ① 常用**：注入 Phase 5 編碼實作、目錄隔離與微觀註解之專案防呆規則 |
| `PHASE06_AGENTS_GUIDE` | `references/phase_06_test.md` | 獨立段落區塊 | **軌跡 ① 常用**：注入 Phase 6 自動化測試驗證、回歸守門與驗收之專案注意事項 |
| `PHASE07_AGENTS_GUIDE` | `references/phase_07_walkthrough.md` | 獨立段落區塊 | **軌跡 ① 常用**：注入 Phase 7 三層文檔對齊審查與結案交付之專案注意事項 |

### 2.4 跨模組檢索空間擴充錨點（1 個）

| Token 名稱 | 宿主檔案位置 (`knowledge-db` 註冊) | 結構屬性 | 注入用途與適用場景 |
| :--- | :--- | :---: | :--- |
| `KNOWLEDGE_DB_SPACE` | `knowledge-db` 注入之檢索指南片段內 | 獨立段落區塊 | 由 `knowledge-db` 動態計算並渲染當前專案已註冊之語意檢索空間速查表 (`--space=<name>`) |

> [!WARNING]
> **結構屬性防呆（`EC-05`）**：上表中唯獨 `AGENTS_SKILL_ROUTING` 位於 `AgentsStandards.md` 的 Markdown 表格內部，向其注入的片段內容**必須是合法的兩欄式 Markdown 表格列**；其餘 23 個錨點均為獨立段落區塊，可注入標準 Markdown 標題、清單或引用塊。

---

## 3. Stage 2 語意 URI 轉換與單反引號語法防呆

在第一層資產（`SKILL.md`、`references/*.md`、`snippets/*.md`）中引用路徑時，必須嚴格遵守**「同技能內部相對路徑 vs. 跨空間單反引號語意 URI」**雙軌分流規則：

### 3.1 雙軌路徑引用分流表

| 引用目標範圍 | 強制採用語法 | 原因說明 (Why) |
| :--- | :--- | :--- |
| **① 同技能自身的附屬檔案**<br>*(例如 `my-skill/SKILL.md` 引用同目錄下的 `references/guide.md`)* | 標準相對路徑：<br>`[參考手冊](./references/guide.md)` | 整個技能目錄在 Stage 2 會依 `release_target.projections.skills` 原封不動投影至目標平台技能目錄下之 `<name>/`，使用 `./references/...` 最直觀且零編譯開銷。 |
| **② 跨技能、標準模板或專案空間路徑**<br>*(例如引用其他 Skill、`plans/`、`docs/`、`yscb.py`)* | **單反引號包覆之 Stage 2 語意 URI** | 不同 `release_target`（含內建或使用者自訂 `contribute` 之發布目標）的 `projections` 投影目錄層級可能不同，透過語意 URI 可由編譯器在 Stage 2 自動解算為精確相對路徑。 |

### 3.2 三大動態佔位符語法與單反引號封裝範例

所有動態佔位符在 Markdown 散文或表格中，**必須 100% 使用單反引號（`` `...` ``）完整包覆**（在 `contribute.json` 的 JSON 字串值內亦建議以單反引號包覆語意路徑標籤）：

```markdown
<!-- yscb:literal -->
<!-- 1. Stage 1 內容注入錨點 (Standalone Anchor，於目標宿主檔置於獨立行) -->
`__@{SKILL_CREATOR_STANDARDS}__`

<!-- 2. Stage 2 跨檔案 Markdown 超連結 (Target Link URI，注意目標端以單反引號包覆) -->
請參閱 [`new-plan`](`__#{module://agents-workflow/assets/skills/new-plan/SKILL.md}__`) 或模板 [`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`)。

<!-- 3. Stage 2 散文/命令列顯示路徑 (Display Path URI，自動轉譯為相對於專案根目錄之顯示路徑) -->
- 計畫目錄：`__${project://plans}__/`
- 文檔目錄：`__${workflow.docs://}__`
- 執行指令：`python __${yscb.host://yscb.py}__ agents-workflow tokens`
```

### 3.3 正反寫法防呆對照（避免編譯警告與連結斷裂）

```markdown
<!-- yscb:literal -->
# ❌ 錯誤寫法 1：跨技能硬編碼相對路徑（當不同 release_target 之 projections 目錄層級不同時會斷連）
請參考 [development-sop](../development-sop/SKILL.md)

# ✅ 正確寫法 1：跨技能使用單反引號包覆之語意連結 URI
請參考 [`development-sop`](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)

# ❌ 錯誤寫法 2：於一般文字中寫出不存在之假 URI（會觸發 Unresolved semantic URI 警告）或於 config://agents-workflow/ 下額外套一層 assets/
範例路徑：`__${foo://non_existent_path}__`
錯誤目錄：<config-dir>/agents-workflow/assets/skills/my-skill/SKILL.md

# ✅ 正確寫法 2：展示字面量語法範例時於代碼塊首行標註 <!-- yscb:literal -->，且第一層自訂資產採扁平目錄結構
<config-dir>/agents-workflow/skills/my-skill/SKILL.md
<config-dir>/agents-workflow/snippets/my_snippet.md
```

---

## 4. 三軌擴充之 contribute.json 最小增量配置範本

在 `__${config://agents-workflow}__/contribute.json` 中註冊擴充資產時，請依據步驟 1 判定的軌跡，採用以下最小增量（Additive Edit）結構：

### 4.1 軌跡 ①：純錨點注入模式 (`Anchor-Only Injection`)

適用於在特定開發階段（如 Phase 05 實作或 Phase 06 測試）追加局部防呆規則，**不建立新 Skill**，僅建立 `__${config://agents-workflow}__/snippets/<name>.md` 並注入對應錨點：

```json
{
  "insert": [
    {
      "type": "uri",
      "token": "PHASE05_AGENTS_GUIDE",
      "value": "config://agents-workflow/snippets/p05_custom_rules.md",
      "mode": "below"
    }
  ]
}
```

### 4.2 軌跡 ②：被動環境攔截型 Skill (`Ambient / Guardrail Skill`)

適用於當 Agent 操作特定領域代碼、資料庫或工具時必須自動攔截觸發的專案規範。需建立 `__${config://agents-workflow}__/skills/<skill-name>/SKILL.md`、建立路由表格列片段 `snippets/<skill-name>_routing.md`，並同時註冊 `export` 與 `AGENTS_SKILL_ROUTING` 注入：

```markdown
<!-- 檔案：config://agents-workflow/snippets/db_migration_routing.md (單行表格列格式) -->
| **修改資料庫 Schema 或執行 Migration 腳本前**<br/>*(調用檔案編輯或終端工具操作 db/migrations/ 時)* | `db-migration-guard` |
```

```json
{
  "export": [
    {
      "type": "skill",
      "name": "db-migration-guard",
      "source": "config://agents-workflow/skills/db-migration-guard"
    }
  ],
  "insert": [
    {
      "type": "uri",
      "token": "AGENTS_SKILL_ROUTING",
      "value": "config://agents-workflow/snippets/db_migration_routing.md",
      "mode": "below"
    }
  ]
}
```

### 4.3 軌跡 ③：功能特化型 Skill (`Feature / Workflow Skill`)

適用於專案特定子系統的多步驟標準作業程序（如新增繪圖節點、編譯特效 Shader、執行專案特定部署流程）。依觸發方式可設為主動指令型（`B-Strict` 或 `B-Assist`）或 `A1` 正向邊界環境型，並可選配注入 `AGENTS_SKILL_ROUTING` 或 `WORKFLOW_SOP_STANDARDS`：

```json
{
  "export": [
    {
      "type": "skill",
      "name": "shader-build-flow",
      "source": "config://agents-workflow/skills/shader-build-flow"
    }
  ]
}
```

---

## 5. 新建 Skill 結構與雙軌 Description 檢核清單

透過 `/skill-creator` 產出任何新 `SKILL.md` 時，必須遵循通用技能設計標準 [`SkillDesignStandards.md`](`__#{module://agents-workflow/assets/standards/SkillDesignStandards.md}__`)、YSCB 工具包編譯標準 [`YscbSkillDesignToolStandards.md`](`__#{module://agents-workflow/assets/standards/YscbSkillDesignToolStandards.md}__`) 與 [`/skill-optimizer`](`__#{module://agents-workflow/assets/skills/skill-optimizer/SKILL.md}__`) 五維度標準的黃金結構：

1. **YAML Frontmatter 單一真理來源與 `contribute.json` 宣告（[`SkillDesignStandards.md`](`__#{module://agents-workflow/assets/standards/SkillDesignStandards.md}__`) §1 & [`YscbSkillDesignToolStandards.md`](`__#{module://agents-workflow/assets/standards/YscbSkillDesignToolStandards.md}__`) §3）**：
   - `SKILL.md` 頂部 YAML Frontmatter 之 `description` 為技能描述之**唯一真理來源（SSOT）**；`contribute.json` 的 `export` 條目（`type: "skill"`）僅宣告 `type`、`name`、`source`，不重複填寫 `description`。
   - **被動環境攔截型（軌跡 ② — A1 正向邊界契約）**：採用 `{核心用途、處理對象與交付物}。觸發情境：{具體動詞、目標檔案路徑特徵與前置攔截時機}。`（預設不寫 `排除情境：`；僅於同領域易混淆時選配無點名負向邊界，嚴禁跨技能點名 `(改用 xxx)`）。
   - **主動指令型（軌跡 ③ — B2 分級命令鎖定）**：重型／破壞性指令（**B-Strict**）採用 `{1 句話核心目的與交付物}。僅於顯式輸入 /{cmd} 時觸發，嚴禁主動觸發。`；會話／教學輔助類（**B-Assist**）採用 `{1 句話核心目的與交付物}。僅於顯式輸入 /{cmd} 或明確要求{具體委託動作}時觸發。`（嚴禁包含括號大小寫變體如 `(或 /Cmd)`）。
2. **四元素目錄拓撲與單層參考拆分（[`SkillDesignStandards.md`](`__#{module://agents-workflow/assets/standards/SkillDesignStandards.md}__`) §2）**：
   - `SKILL.md` 本體嚴格控制在 **500 行以內**（建議 60~180 行）。
   - 若包含長篇 API 表、Schema 或範例，拆分至同目錄下單層 `references/<topic>.md`（超過 100 行之參考檔頂部須附 `## 目錄 (Contents)`）；決定性格式或結構校驗優先下沉至 CLI 或 `scripts/`。
3. **條件式進度檢核表、雙模狀態卡與 Gotchas 收尾（[`SkillDesignStandards.md`](`__#{module://agents-workflow/assets/standards/SkillDesignStandards.md}__`) §3）**：
   - 包含 3 個以上具相依性步驟之技能，於 `## 執行步驟` 開頭提供可勾選之 Markdown Checklist，並依 `Artifact-in-File` vs. `Artifact-in-Chat` 校準輸出節流。
   - 檔案末尾提供 `## 常見踩坑指南 (Gotchas)`，提煉最關鍵的反直覺防呆要點。
