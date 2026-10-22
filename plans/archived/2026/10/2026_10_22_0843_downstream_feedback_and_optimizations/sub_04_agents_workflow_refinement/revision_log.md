# 修訂紀錄書 (Revision Log)

> 功能名稱：sub_04_agents_workflow_refinement  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] 廢除並清理 `session-analysis` 技能與 `SESSION_ANALYSIS_CHECK_ITEMS` Token
- **修訂類別**：UI/UX/DX
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/assets/skills/session-analysis/` (Removed)
  - `ys_codebase/source/agents-workflow/contributes/agents-workflow.json`
  - `ys_codebase/source/agents-workflow/README.md`
  - `ys_codebase/source/agents-workflow/tests/test_session_analysis_workflow.py` (Removed)
  - `ys_codebase/source/agents-workflow/tests/test_compiler.py`
  - `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py`
  - `ys_codebase/source/knowledge-db/assets/session_analysis_check.md` (Removed)
  - `ys_codebase/source/knowledge-db/contributes/agents-workflow.json`
  - `docs/agents-workflow/README.md`
  - `.agents/skills/session-analysis/` (Removed)
- **修訂摘要**：
  1. **廢除 `session-analysis` 技能資產**：物理刪除 `ys_codebase/source/agents-workflow/assets/skills/session-analysis/`（含 `SKILL.md`、`scripts/analyzer.py`、`references/evaluation_guide.md`）與工作區已投影之 `.agents/skills/session-analysis/`。
  2. **移除匯出與擴充錨點**：自 `agents-workflow/contributes/agents-workflow.json` 移除 `session-analysis` 技能匯出與 `SESSION_ANALYSIS_CHECK_ITEMS` Token 宣告；自 `knowledge-db/contributes/agents-workflow.json` 移除對應 `insert` 並刪除 `session_analysis_check.md`。
  3. **文檔與測試同步**：移除 `docs/agents-workflow/README.md` 與 `ys_codebase/source/agents-workflow/README.md` 中之 `session-analysis` 描述，刪除專屬測試檔 `test_session_analysis_workflow.py`，並更新 `test_compiler.py` 與 `test_plans_model_record.py` 驗證其徹底除役。
- **驗證結果**：`dev check agents-workflow`、`dev check knowledge-db` 與 `dev test agents-workflow` 100% 通過。

### [REV-02] 選擇性融合外部 SKILL 優化包、通用技能去特化與新增純淨 `skill-optimizer` 標準資產
- **修訂類別**：UI/UX/DX
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/assets/skills/skill-optimizer/SKILL.md` (Added)
  - `ys_codebase/source/agents-workflow/assets/skills/skill-optimizer/references/audit-rubric.md` (Added)
  - `ys_codebase/source/agents-workflow/assets/skills/skill-optimizer/references/refactoring-patterns.md` (Added)
  - `ys_codebase/source/agents-workflow/assets/skills/skill-optimizer/references/ab-eval-guide.md` (Added)
  - `ys_codebase/source/agents-workflow/assets/skills/{auto,context-init,continue,development-sop,discuss,documentation,new-plan,pause,research,roadmap,yscb-cli-guild}/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/documentation/references/author_guide_and_checklist.md`
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/references/{plan_modes.md,phase_00_discuss.md..phase_07_walkthrough.md}`
  - `ys_codebase/source/agents-workflow/contributes/agents-workflow.json`
  - `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py`
  - `plans/2026_10_22_0843_downstream_feedback_and_optimizations/sub_04_agents_workflow_refinement/R01_skills_optimization_and_optimizer_asset.md` (Added)
- **修訂摘要**：
  1. **通用技能去特化（Zero Specialization Pollution）**：將外部優化包中新增之 `skill-optimizer`（含 `SKILL.md` 與 3 份 `references/`）及既有通用技能徹底移除 `ys-codebase` 內部編譯器特化教學（如反引號語意標籤錯誤教學、`compiler.py` 內部引用），確保 `agents-workflow` 基底提供的通用技能 100% 純淨跨專案通用。
  2. **註冊 `skill-optimizer` 資產與擴充錨點**：於 `contributes/agents-workflow.json` 新增 `skill-optimizer` 匯出項與 `SKILL_OPTIMIZER_STANDARDS` 動態擴充錨點，同時 100% 保留既有 `insert`、`release_target` 與全部 15 個動態錨點。
  3. **既有 11 個技能與 10 份 References 選擇性強化**：全數升級 YAML `description`（補齊顯式觸發詞與 `"請勿用於..."` 負向排他邊界）、植入執行檢核表與 `## 常見踩坑指南 (Gotchas)`，並為 `plan_modes.md` 與 `author_guide_and_checklist.md` 補齊頂部 `## 目錄 (Contents)`；同時 100% 保留單反引號語意標籤契約與 `sub_02` 狀態規則（`handoff.md` 閱後即焚、Umbrella 主從狀態連動、`P07` 三步管線順序、預設標頭狀態與模型紀錄規則）。
  4. **調研報告歸位與暫存包清理**：將調研報告校正標頭與內容後落檔至本子計畫 `R01_skills_optimization_and_optimizer_asset.md`，並移除根目錄暫存之 `ys-codebase-agents-workflow-optimized.zip`。
- **驗證結果**：新增 `FT-08` 單元測試驗證 12 技能負向邊界、去特化純淨度與零未包覆標籤，`dev check agents-workflow` 與 `dev test agents-workflow` 100% 通過。

### [REV-03] 修正全庫 `guild` -> `guide` 拼字筆誤（Skill、Token、Provider、資產檔與知識庫）
- **修訂類別**：UI/UX/DX
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/assets/skills/yscb-cli-guide/SKILL.md` (Renamed from `yscb-cli-guild/SKILL.md`)
  - `ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md`
  - `ys_codebase/source/agents-workflow/assets/skills/{context-init,development-sop,research}/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/references/phase_00_discuss.md..phase_07_walkthrough.md`
  - `ys_codebase/source/agents-workflow/contributes/agents-workflow.json`
  - `ys_codebase/source/agents-workflow/tests/{test_compiler.py,test_plans_model_record.py}`
  - `ys_codebase/source/core/core/providers.py`
  - `ys_codebase/source/core/contributes/agents-workflow.json`
  - `ys_codebase/source/core/tests/{test_contributes.py,test_cli_router.py}`
  - `ys_codebase/source/knowledge-db/assets/{phase00_guide.md,phase07_guide.md,research_guide.md}` (Renamed from `*_guild.md`)
  - `ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md`
  - `ys_codebase/source/knowledge-db/contributes/agents-workflow.json`
  - `ys_codebase/source/knowledge-db/README.md`
  - `ys_codebase/source/dev/assets/skills/yscb-module-dev/SKILL.md`
  - `ys_codebase/source/dev/assets/skills/yscb-module-dev/references/{acceptance_checklist.md,cli_and_commands.md,contributes_guide.md,testing_and_sandbox.md}`
  - `ys_codebase/source/dev/tests/test_checker.py`
  - `docs/agents-workflow/{README.md,user_guide.md}`
  - `docs/core/contributes_architecture.md`
- **修訂摘要**：
  1. **Skill 與目錄正名**：將 `yscb-cli-guild` 更名為 `yscb-cli-guide`（含目錄、`SKILL.md` 標題 `Agents CLI Guide`、`AgentsStandards.md` 路由表、`context-init` 與 `development-sop` 引用）。
  2. **Token 錨點與 Provider 函式正名**：將 `AGENTS_CLI_GUILD`、`RESEARCH_AGENTS_GUILD`、`PHASE00_AGENTS_GUILD`~`PHASE07_AGENTS_GUILD` 全數正名為 `*_GUIDE`；將 `core/providers.py` 中 `get_agents_cli_guild`、`get_phase_cli_guild`、`get_phase00_cli_guild`~`get_research_cli_guild` 全數正名為 `*_guide`。
  3. **跨模組資產與手冊正名**：將 `knowledge-db` 注入檔 `phase00_guild.md`、`phase07_guild.md`、`research_guild.md` 更名為 `*_guide.md`；修正 `dev` 與 `knowledge-db` 技能標題中 `Guild` -> `Guide` 及 `user_guild.md`/`dev_guild.md`/`install_guild.md` -> `*_guide.md` 筆誤。
- **驗證結果**：`ys_codebase/source` 與 `docs` 內 `guild` 殘留數為 0，`core`、`dev`、`agents-workflow`、`knowledge-db` 四大模組 `dev check` 與 `dev test` 100% 通過，並完成 `@build` 自部署同步。

### [REV-04] 確立三段式 `description` 高密度與自包含規範並重構全 15 項技能與匯出清單
- **修訂類別**：UI/UX/DX
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/assets/skills/skill-optimizer/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/skill-optimizer/references/{audit-rubric.md,refactoring-patterns.md}`
  - `ys_codebase/source/agents-workflow/assets/skills/{auto,context-init,continue,development-sop,discuss,documentation,new-plan,pause,research,roadmap,yscb-cli-guide}/SKILL.md`
  - `ys_codebase/source/agents-workflow/contributes/agents-workflow.json`
  - `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py`
  - `ys_codebase/source/dev/assets/skills/yscb-module-dev/SKILL.md`
  - `ys_codebase/source/dev/contributes/agents-workflow.json`
  - `ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md`
  - `ys_codebase/source/knowledge-db/contributes/agents-workflow.json`
  - `ys_codebase/config/agents-workflow/skills/bump-revision/SKILL.md`
  - `ys_codebase/config/agents-workflow/contribute.json`
- **修訂摘要**：
  1. **沉澱 `description` 三大黃金法則至 `skill-optimizer`**：於 `skill-optimizer/SKILL.md`、`references/audit-rubric.md` 與 `references/refactoring-patterns.md` 植入「高密度且具高召回率」、「自包含且具體可觀測（嚴禁依賴外部未知脈絡如『依循 xxx 規範』，直接描述輸入標的、處理動作與輸出交付物）」及「三段式結構化邊界（`{核心用途與支援範圍}。觸發情境：{高頻正樣本意圖}。排除情境：{易誤觸發負樣本邊界}。`）」。
  2. **重構全 15 項技能 `SKILL.md` 與對應 `contributes` 匯出清單**：將 `agents-workflow`（12 項）、`dev`（`yscb-module-dev`）、`knowledge-db`（`knowledge-db-search`）與專案本地（`bump-revision`）共 15 項技能的 YAML `description` 及 `contributes/*.json` / `contribute.json` 註冊描述全數對齊三段式結構化邊界與自包含 I/O 規範。
  3. **擴充 `FT-08` 剛性單元測試**：於 `test_plans_model_record.py` 斷言全 12 項 `agents-workflow` 技能之 `description` 強制包含 `"觸發情境："` 與 `"排除情境："` 三段式標記。
- **驗證結果**：`agents-workflow`、`dev`、`knowledge-db` 三大模組 `dev check` 與 `dev test` 100% 通過，並完成 `@build` 自部署同步與 `plan verify --all` 檢驗。

### [REV-05] 確立 `description` 雙軌模式（環境攔截三段式 vs. 主動指令極簡契約）並收斂 6 項指令型技能與中樞導流
- **修訂類別**：UI/UX/DX
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/assets/skills/skill-optimizer/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/skill-optimizer/references/{audit-rubric.md,refactoring-patterns.md}`
  - `ys_codebase/source/agents-workflow/assets/skills/{auto,pause,continue,context-init,development-sop}/SKILL.md`
  - `ys_codebase/source/agents-workflow/contributes/agents-workflow.json`
  - `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py`
  - `ys_codebase/config/agents-workflow/skills/bump-revision/SKILL.md`
  - `ys_codebase/config/agents-workflow/contribute.json`
- **修訂摘要**：
  1. **升級 `skill-optimizer` 為雙軌結構化邊界規範**：於 `SKILL.md`、`audit-rubric.md` 與 `refactoring-patterns.md` 明確區分「被動／環境攔截型技能（Ambient / Intent-Driven Skills，採完整三段式結構化邊界）」與「主動指令型技能（Command-Driven / Slash-Invoked Skills，採『`{1 句話核心目的與交付物}。僅於顯式輸入 /{cmd} 或明確指示{核心動作}時觸發。`』極致精簡指令契約，省略內部步驟細節與 `(或 /Cmd)` 大小寫變體等過度相容敘述，將延伸呼叫時機交由中樞技能（Hub Skill）按需導流）」，確保通用且無特化用語。
  2. **極致精簡 6 項主動指令型技能之 `description`**：將 `auto`、`pause`、`continue`、`context-init`、`bump-revision`、`skill-optimizer` 之 `SKILL.md` 與對應 `contributes` 匯出描述壓縮至 ~50-65 字元之極致精簡指令契約，剔除內部步驟背誦與 `(或 /Cmd)` 冗詞，消除跨技能模糊語意搶路由並大幅降低常駐 System Prompt Token 消耗。
  3. **補強中樞技能按需導流錨點**：於 `development-sop/SKILL.md` 補齊生命週期工作流中樞分流清單，並於 `context-init` 與 `continue` 補上對 `/continue`、`/new-plan` 與 `/pause` 的上下游導流指引。
- **驗證結果**：`dev check agents-workflow`、`dev test agents-workflow` 100% 通過，並完成 `@build` 自部署與 `plan verify --all` 檢驗。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 docs/ 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 CHANGELOG.md。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

