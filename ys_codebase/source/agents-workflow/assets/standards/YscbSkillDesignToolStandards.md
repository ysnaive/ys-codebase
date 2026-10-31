# YSCB 技能雙層架構、動態佔位符與編譯發布工具標準 (YSCB Skill Design Tool Standards)

本文件定義在 **YS-Codebase (`agents-workflow`)** 工具包環境中，撰寫、修改、註冊與編譯發布技能（`SKILL.md`、`references/*.md`）與注入片段（`snippets/*.md`）時必須遵循的雙層空間邊界、四大動態佔位符語法與三步 CLI 編譯驗收契約。

---

## 1. [!] 雙層物化空間邊界與第一層扁平路徑鐵律 (Two-Layer Architecture & Flat Source Paths)

YSCB 工作流嚴格區分「第一層宣告式源碼空間（Layer 1 Source / Config SSOT）」與「第二層平台物化投影空間（Layer 2 Materialized Target）」：

1. **第一層（唯一可寫入之 SSOT 空間）**：
   - **專案客製化擴充空間（`__${config://agents-workflow}__/`）**：
     - 專案自訂技能：`__${config://agents-workflow}__/skills/<skill-name>/SKILL.md`（及單層 `references/<file>.md`）
     - 專案自訂注入片段：`__${config://agents-workflow}__/snippets/<snippet-name>.md`
     - 專案擴充註冊組態：`__${config://agents-workflow}__/contribute.json`
     - **扁平路徑防呆**：在 `__${config://agents-workflow}__/` 下**嚴禁額外多套一層 `assets/` 目錄**！
   - **母倉模組內建資產空間（僅母倉開發 `agents-workflow` 本體時寫入）**：
     - 位於 `ys_codebase/source/agents-workflow/assets/{skills,standards,templates}/` 與 `contributes/agents-workflow.json`。
2. **第二層（編譯器自動投影之唯讀物化空間，嚴禁手動修改）**：
   - 依當前生效之 `release_target`（如 `antigravity`、`claude`、`codex`）中 `projections` 映射設定，由 `agents-workflow release` 自動將第一層資產編譯投影至目標目錄（如 `.agents/skills/`、`.agents/.yscb/{standards,templates}/` 與根目錄 `AGENTS.md` 受託管區塊）。
   - **唯讀紅線**：任何對第二層物化檔案的直接手動修改，都會在下次執行 `release` 時被無情覆蓋抹除。

---

## 2. 雙軌路徑引用與四大動態佔位符語法 (Dual-Track Path References & 4 Dynamic Placeholders)

### 2.1 雙軌路徑引用分流鐵律

| 引用目標範圍 | 強制採用語法 | 技術原因 (Why) |
| :--- | :--- | :--- |
| **① 同技能自身的附屬檔案**<br>*(例如 `my-skill/SKILL.md` 引用同目錄下的 `references/guide.md`)* | **標準相對路徑**：<br>`[參考手冊](./references/guide.md)` | 整個技能資料夾在 Stage 2 會隨 `projections.skills` 整體投影至 `<target>/<skill-name>/`，使用 `./references/...` 零編譯開銷且天然跨平台相容。 |
| **② 跨技能、中央標準、計畫模板或專案空間路徑**<br>*(例如引用其他 Skill、`CodeQualityStandards.md`、`plans/`、`yscb.py`)* | **單反引號包覆之 Stage 2 語意 URI**（詳見下方 `2.2` 區塊範例） | 不同 `release_target` 的 `projections` 目錄深度可能不同；透過語意 URI 可由編譯器在 Stage 2 動態解算精確相對路徑，杜絕硬編碼 `.agents/`、`.claude/` 或 `../other-skill/` 造成跨平台斷連。 |

### 2.2 四大動態佔位符語法、單反引號封裝與 `<!-- yscb:literal -->` 字面量保護

1. **強制單反引號封裝鐵律（Single-Backtick Enclosure）**：
   - 所有動態佔位符在 Markdown 散文、清單或表格中，**必須 100% 以單反引號（`` `...` ``）完整包覆**（注意：不可使用雙反引號 `` ``...`` `` 包覆待解算標籤，且裸露未包覆之標籤將觸發 `[compiler:warning] Unenclosed placeholder tag` 並跳過解算）。
2. **教學與範例字面量保護（`<!-- yscb:literal -->`）**：
   - 若在 `SKILL.md`、中央標準或 `references/*.md` 內文中，需要展示「不被編譯器解算展開」的佔位符原始語法作為教學範例（或包含假名如 `<name>`、`foo://`），必須將範例置於**首行緊接 `<!-- yscb:literal -->` 標記之三反引號 Fenced Code Block** 內：

```markdown
<!-- yscb:literal -->
# ① Stage 1 內容注入錨點 (`__@{TOKEN}__` — 置於宿主檔獨立行，由 contribute.json 之 insert 規則注入內容，未匹配時自動抹除整行)
`__@{SKILL_CREATOR_STANDARDS}__`

# ② Stage 2 跨檔案 Markdown 超連結 (`__#{URI}__` — 目標括號內必須以單反引號包覆，發布時自動轉譯為相對於當前檔案之實體相對路徑並剝除反引號)
- 引用其他技能：請遵循 [`development-sop`](`__#{module://agents-workflow/assets/skills/development-sop/SKILL.md}__`)
- 引用中央標準：請參閱 [`CodeQualityStandards.md`](`__#{module://agents-workflow/assets/standards/CodeQualityStandards.md}__`)
- 引用計畫模板：請讀取 [`P00_discuss.md`](`__#{module://agents-workflow/assets/templates/P00_discuss.md}__`)

# ③ Stage 2 專案相對顯示路徑 (`__${URI}__` — 轉譯為相對於專案根目錄之顯示路徑，支援 Standalone 獨立路徑或 Inline 穿插於反引號命令中)
- 獨立路徑顯示：產物落檔於 `__${project://plans}__/{plan_name}/` 或知識庫 `__${workflow.docs://}__/`
- 行內命令穿插：執行 `python __${yscb.host://yscb.py}__ agents-workflow plan verify` 檢核

# ④ Stage 2 宿主平台工具專有名詞投影 (`__%{KEY}__` — 依 antigravity / claude / codex 目標平台自動展開為對應原生工具名)
- 已定義之合法 KEY 清單（定義於 locales/definition.json）：
  - `__%{agent_tool.file_read_range}__`（區段讀檔）
  - `__%{agent_tool.file_read}__`（全檔讀取）
  - `__%{agent_tool.file_edit}__`（精確區塊編輯）
  - `__%{agent_tool.file_grep_single}__`（單檔關鍵字檢索）
  - `__%{agent_tool.shell_exec}__`（終端指令執行）
  - `__%{agent_tool.shell_bg_daemon}__`（背景常駐程序啟動）

# ❌ 常見錯誤寫法對照（將導致跨平台斷連或編譯器警告）：
- 錯誤 A（跨技能硬編碼相對路徑）：[development-sop](../development-sop/SKILL.md)
- 錯誤 B（漏加單反引號或誤用雙反引號）：請查閱 __${project://plans}__/ 目錄
- 錯誤 C（捏造未註冊於 locales/definition.json 之專有名詞 KEY）：`__%{agent_tool.unknown_tool}__`
```

---

## 3. `contribute.json` 宣告規範與三步 CLI 編譯驗收守門 (Registration & 3-Step Verification Gate)

1. **`SKILL.md` Frontmatter 單一真理來源（SSOT）與 `contribute.json` 宣告規範**：
   - 在 `contribute.json` 之 `export` 陣列註冊技能（`type: "skill"`）時，僅需宣告 `type`、`name` 與 `source` 三個欄位；技能描述以 `SKILL.md` YAML Frontmatter 之 `description` 為**唯一真理來源（SSOT）**（編譯器與 `agents-workflow list` 會自動從 `SKILL.md` 擷取，無須於 `contribute.json` 重複填寫 `description`）。
   - 向 `AGENTS_SKILL_ROUTING` 注入路由規則時，因該錨點位於 `AgentsStandards.md` 的 Markdown 表格內部，注入之 snippet **必須為合法的兩欄式 Markdown 表格列**（`| **觸發條件** | \`skill-name\` |`），嚴禁注入標題或獨立段落。
2. **強制三步 CLI 編譯驗收閉環（3-Step CLI Verification Gate）**：
   凡新增或修改任何第一層技能、標準、模板或 `contribute.json` 後，必須依序實機執行以下三步驗證且 **0 Errors / 0 Warnings**：
   - **步驟 ①（組態 Schema 檢核）**：`python yscb.py contributes check` — 驗證所有 `contribute.json` 結構、型別與 Token 引用合法性。
   - **步驟 ②（Stage 1/2 試編譯與語法靜態守門）**：`python yscb.py agents-workflow compile` — 嚴格確認輸出 **0 Error 且 0 `[compiler:warning]`**（攔截未包覆反引號標籤、未解析之語意 URI、未知之 Token 或未知之 `__%{<KEY>}__` 專有名詞標籤）。**若出現任何警告，嚴禁執行下一步 `release`，必須原地修復第一層檔案並重驗！**
   - **步驟 ③（正式物化投影發布）**：`python yscb.py agents-workflow release` — 將通過驗證之資產正式投影至第二層目標平台空間（若為修改母倉 `ys_codebase/source/agents-workflow/` 源碼，須先執行 `dev build` 與 `install agents-workflow@build --force -y` 更新運行模組後再驗證發布）。
