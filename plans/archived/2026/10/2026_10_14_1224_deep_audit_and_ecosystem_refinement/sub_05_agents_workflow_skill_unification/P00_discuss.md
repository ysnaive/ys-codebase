# 方案討論與技術對齊書 (Discussion & Alignment)

> 功能名稱：sub_05_agents_workflow_skill_unification  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

在原先的 `agents-workflow` 設計中，資產分為四大類型：
1. `standard`：通用工程規範與原則（如 `AgentsStandards.md`）
2. `template`：SOP 與研究文檔模板（如 `P00_discuss.md`）
3. `skill`：現代化 Agent 技能包（目錄結構含 `SKILL.md`，如 `development-sop`, `yscb-cli-guild`）
4. `workflow`：舊式單檔 Markdown 流程（輸出至 `.agents/workflows/`，如 `ContextInit.md`, `Discuss.md`, `NewPlan.md`）

現代 Agent 開發平台（包括 Google Antigravity、Claude Code、OpenAI 等）已全面以 **Skills（技能包）** 作為一等公民擴充標準。在同一生態系中並存 `workflow` 與 `skill` 兩套模型，帶來了諸多問題：
1. **概念分叉與認知負擔**：使用者與 Agent 經常混淆何時呼叫 `/Workflow`、何時觸發 `Skill`。
2. **目錄拓撲冗餘**：專案根目錄下同時存在 `.agents/workflows/` 與 `.agents/skills/`。
3. **擴充性受限**：單檔 workflow 無法攜帶附屬腳本（scripts）、參考文件（references）或微資料集，限制了流程的自動化擴充能力。

依照使用者明確指示（延伸子計畫 2.a）：「**agents-workflow 分類純化，不再有 WORKFLOW 類型，皆遷移為 SKILL**」。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

### 2.1 廢除 `workflow` 資產類型，全面收斂為 `skill`
- **資產類型收斂為三大純粹類型**：`standard`、`template`、`skill`。
- **Schema DSL 更新 (`_format.json`)**：
  `ExportAssetDef.type` 純化為 `enum(standard, template, skill)!`。
- **向下相容容錯（軟轉譯）**：若第三方歷史模組宣告 `type: "workflow"`，編譯器自動視為 `type: "skill"` 並發出轉換提示，保障舊擴充平滑過渡。

### 2.2 既有 8+1 個 Workflows 全面遷移至 Skills
將現有 8 個模組級 Workflows 與 1 個專案級 Workflow 重構遷移為標準 Skill 套件目錄：

| 原 Workflow 檔案 | 遷移後目標 Skill 名稱 | 目標路徑 |
| :--- | :--- | :--- |
| `ContextInit.md` | `context-init` | `assets/skills/context-init/SKILL.md` |
| `NewPlan.md` | `new-plan` | `assets/skills/new-plan/SKILL.md` |
| `Continue.md` | `continue` | `assets/skills/continue/SKILL.md` |
| `Pause.md` | `pause` | `assets/skills/pause/SKILL.md` |
| `Discuss.md` | `discuss` | `assets/skills/discuss/SKILL.md` |
| `Research.md` | `research` | `assets/skills/research/SKILL.md` |
| `Auto.md` | `auto` | `assets/skills/auto/SKILL.md` |
| `Roadmap.md` | `roadmap` | `assets/skills/roadmap/SKILL.md` |
| `BumpRevision.md` (專案級) | `bump-revision` | `config/agents-workflow/skills/bump-revision/SKILL.md` |

### 2.3 產物發布引擎與舊 Workflows 自動清理
- **Release Targets 投影收斂**：移除 `projections.workflow`，保留 `skill`, `standard`, `template`。
- **歷史目錄自動安全清理**：發布引擎 `publisher.py` 在發布交易中，自動感應專案中殘留的舊 `.agents/workflows/`（及 `.claude/commands/` 舊殘留），安全予以清理或清空，防止殭屍舊檔案干擾。
- **超連結全面對齊**：校準 `AGENTS.md`、`DevelopmentStandards.md`、各 Skill 內部指向 `.agents/workflows/` 的舊路徑為 `.agents/skills/<name>/SKILL.md`。

---

## 3. 開放議題與確認事項 (Open Issues)

- [x] **已完成確認**：所有既有 Workflow 單檔皆完整重構為相應的 `assets/skills/<name>/SKILL.md`，並更新所有單元測試與關聯超連結。


