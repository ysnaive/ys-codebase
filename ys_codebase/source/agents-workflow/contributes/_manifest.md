# Agents-Workflow 模組貢獻導覽清冊 (Contributes Manifest)

> 本清冊記錄 `agents-workflow` 模組對外貢獻之擴充能力與協議。

## 1. 外部注入清冊 (Egress Contributions)

### 1.1 `core.json`（微內核指令與 URI 擴充）
- **語意 URI**：`workflow.plans://`（指向活躍計畫空間）、`workflow.standards://`、`workflow.templates://`。
- **CLI 指令樹**：
  - `plans status`: 檢視當前活躍計畫進度與階段。
  - `plans search`: 語意檢索歷史與活躍計畫。
  - `plans verify`: 計畫合規性校驗。
  - `plans archive`: 結案計畫封存歸檔。
  - `workflow release`: 投影編譯規範資產至指定 target（如 antigravity）。

### 1.2 `agents-workflow.json`（自身資產導出）
- 導出 `NewPlan`, `Auto`, `Continue`, `Pause` 等標準工作流。
- 導出 P00~P07 計畫模板與 `AgentsStandards` 核心規範。

## 2. 開放擴充點清冊 (Ingress Points)
- `export`: 允許其他領域模組導出 Skill、模板或標準資產。
- `token`: 宣告模板可注入錨點。
- `insert`: 允許向特定錨點注入內容。
- `release_target`: 允許擴充第三方 IDE 或目標平台投影規則。
