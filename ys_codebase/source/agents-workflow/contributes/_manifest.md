# Agents-Workflow 模組貢獻導覽清冊 (Contributes Manifest)

> 本清冊記錄 `agents-workflow` 模組對外貢獻之擴充能力與協議。

## 1. 外部注入清冊 (Egress Contributions)

### 1.1 `core.json`（微內核指令與 URI 擴充）
- **語意 URI**：`workflow.plans://`（活躍計畫空間）、`workflow.archived://`（封存歷史空間）、`workflow.docs://`（專案文檔空間）、`workflow.roadmap://`（路線圖空間）。
- **CLI 指令樹**：
  - `plan status` / `plan search` / `plan check` / `plan verify` / `plan archive`：Dev Plans 計畫生命週期管理工具鏈。
  - `release` / `compile` / `list` / `tokens` / `release-target`：工作流與技能多目標編譯發布系統。
  - `roadmap`：長期技術路線圖管理與推薦。
  - `init`：工作流目錄結構與協議一鍵初始化。

### 1.2 `agents-workflow.json`（自身資產導出）
- 導出 15 大領域、工作流與引導教練純 Skill 技能包（`.agents/skills/` 或 `.claude/skills/`），含 `/how-to-config-yscb` 與 `/how-to-yscb`。
- 導出 16 個標準計畫模板（P00~P07、Fast Track、Umbrella、Roadmap、Todo、Changelog 等）與 `AgentsStandards` 核心規範（含 `PROJECT_ROLE_AND_BOUNDARIES` 錨點）。

## 2. 開放擴充點清冊 (Ingress Points)
- `export`: 允許其他領域模組導出 Skill、模板或標準規範資產。
- `token`: 宣告動態注入錨點（如 `PHASEXX_HEADER`、`AGENTS_SKILL_ROUTING` 等）。
- `insert`: 允許向特定錨點注入內容。
- `release_target`: 允許擴充第三方 IDE 或目標平台投影規則（如 `antigravity`, `claude`, `codex`）。
