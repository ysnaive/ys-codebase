# Phase 0: 語意需求與討論模式 (Semantic Requirements) - agents-workflow 配置治理與一鍵初始化

> 計畫名稱：`sub_04_agents_workflow_injection_config_and_init_default`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 當前狀態：`Confirmed` (Phase 0 討論確認完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 原始需求摘要 (Raw Requirements Summary)

- **核心目標**：實作 `agents-workflow` 模組的專案級組態治理（`config.project.json`）與 `--init-default` 一鍵初始化協議綁定及目錄建立指令。
- **剛性架構原則 (Zero Speculation)**：
  - `config.project.json` 模板中所有專案路徑**預設必定為 `"!undefined"`**，嚴禁在靜態模板中填入預設實體路徑。
  - `"project://.agent_workflow/plans"` 等路徑為 **`--init-default` 專屬之「一鍵初始化預設推薦值」**，僅在使用者明確執行 `--init-default` 並確認後才寫入設定檔。
- **範疇邊界**：
  - ✅ **涵蓋範疇**：`workflow.*` 4 大 URI 協議註冊、`config.project.json` 模板（值皆為 `"!undefined"`）與保留欄位、`--init-default` 互動式初始化與 `--path-{plans|archived|ext|docs}` 變種參數覆蓋。
  - 🚫 **排除範疇**：注入內容 (Inserts/Tokens) 不納入本次子計畫範圍，留待後續子計畫處理。

---

## 2. 釐清與架構決策紀錄 (Clarification & Decision Records)

### [P00:DR-01] 4 大 Workflow 語意 URI 協議註冊與 `!undefined` 預設
- **語意**：`agents-workflow` 模組於其 `manifest.json` 中註冊 4 組標準 URI 協議，在 `config.project.json` 中預設值全部為 `"!undefined"`：
  1. `workflow.plans://` $\rightarrow$ `paths.plans: "!undefined"`
  2. `workflow.archived://` $\rightarrow$ `paths.archived: "!undefined"`
  3. `workflow.ext://` $\rightarrow$ `paths.ext: "!undefined"`
  4. `workflow.docs://` $\rightarrow$ `paths.docs: "!undefined"`

### [P00:DR-02] `config.project.json` 模板 Schema 與保留欄位
- **語意**：模組安裝時產出之預設組態模板結構：
  ```json
  {
    "paths": {
      "plans": "!undefined",
      "archived": "!undefined",
      "ext": "!undefined",
      "docs": "!undefined"
    },
    "ide": [],
    "enable_agents_md": true,
    "enable_project_changelog": true
  }
  ```
- **說明**：`ide`, `enable_agents_md`, `enable_project_changelog` 為先行保留欄位，本階段無功能邏輯，保留給未來功能擴充。

### [P00:DR-03] `--init-default` 一鍵初始化預設值與目錄建立
- **語意**：
  - `--init-default` 內建的一鍵初始化預設綁定路徑：
    - `plans` $\rightarrow$ `"project://.agent_workflow/plans"`
    - `archived` $\rightarrow$ `"project://.agent_workflow/plans/archived"`
    - `ext` $\rightarrow$ `"project://.agent_workflow/extensions"`
    - `docs` $\rightarrow$ `"project://docs"`
  - **互動執行流程**：
    1. 掃描各目標路徑是否已存在於實體檔案系統。
    2. 若目錄已存在，額外提示「`[提示] 目錄 <path> 已存在，確認要自動綁定在該路徑嗎?`」。
    3. 依次條列並提示 `將建立以下資料夾 [-y / -n]: ...`。
    4. 使用者確認後，自動建立缺失目錄，並將解析後的路徑寫回 `config/agents-workflow/config.project.json`（取代 `"!undefined"`）。

### [P00:DR-04] `--path-*` 變種參數自訂路徑支援
- **語意**：`--init-default` 支援附加參數以覆蓋一鍵初始化的預設值：
  - `--path-plans="<custom_path>"`
  - `--path-archived="<custom_path>"`
  - `--path-ext="<custom_path>"`
  - `--path-docs="<custom_path>"`
  - 支援 `-y` / `--yes` 非互動無提示自動同意模式。

---

## 3. 開發者釐清確認結果 (Clarification Outcomes)

| 釐清項目 | 開發者確認規格 | 對應決策 |
| :--- | :--- | :---: |
| **1. Config 模板初始值** | 必須剛性為 `"!undefined"`，貫徹微內核零臆測原則 | `[P00:DR-01]`, `[P00:DR-02]` |
| **2. 一鍵初始化預設值** | 僅由 `--init-default` 指令攜帶推薦預設路徑 (`project://.agent_workflow/...`) | `[P00:DR-03]` |
| **3. 互動模式** | 依次條列並提示 `[-y / -n]`，已存在路徑額外提醒是否綁定 | `[P00:DR-03]` |
| **4. 變種指令參數** | `--path-plans`, `--path-archived`, `--path-ext`, `--path-docs` | `[P00:DR-04]` |
| **5. Config 保留欄位** | `ide: []`, `enable_agents_md: true`, `enable_project_changelog: true` | `[P00:DR-02]` |
| **6. 注入內容範疇** | 本次排除注入內容 (Inserts)，專注於 config 與 init 指令 | 範疇邊界收斂 |

---

## 4. 當前階段確認狀態

- **討論狀態**：`Draft` (已校正 `!undefined` 與一鍵初始化預設值定義)  
- **推進關卡**：請開發者確認本階段內容是否無誤，可否定稿 `P00` 並進入三大分流層級評估？
