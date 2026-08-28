# Agents Workflow 模組 (General Agents Workflow Framework)

`agents-workflow` 為 YS-Codebase 體系的一等公民核心模組，提供通用、純淨且工廠化的 Agent 工作流程與規範治理體系。

---

## 1. 核心定位與資產架構

模組徹底剝離特定專案特化規則，提供 100% 通用抽象資產：
- **規範 (`assets/standards/`)**：
  - `AgentsStandards.md`：Agent 通用核心原則、防呆紀律與絕對禁止條款（自動注入至 `AGENTS.md`）。
  - `DevelopmentStandards.md`：SOP 0~7 標準生命週期、三大分流矩陣、追溯鏈與工作目錄規範。
  - `DocumentationStandards.md`：知識庫 7 大抽象維度、Topic 專題文檔與 1:1 交付原則。
- **流程 (`assets/workflows/`)**：
  - `ContextInit.md`：上下文熱啟動流程。
  - `NewPlan.md`：標準立項流程（完整載入 `DevelopmentStandards.md`）。
- **模板 (`assets/templates/`)**：
  - 13 大標準模板庫（`P00`~`P07`, `FT_plan`, `umbrella_overview`, `changelog`, `R_research_report`, `handoff`）與共用標頭 `header.md`。
- **擴充手冊**：[`contributes.format.md`](../../source/agents-workflow/contributes.format.md) 官方擴充宣告格式規格書。

---

## 2. 佔位符語法與渲染機制 (Placeholder Architecture)

系統採用 Markdown 原生可視的強定義佔位符語法，淘汰被 HTML 隱藏的舊註解格式：

| 佔位符類型 | 語法結構 | 正則表達式 | 核心職責與編譯行為 |
| :--- | :--- | :--- | :--- |
| **插入佔位符 (Token Anchor)** | `__@{TOKEN_NAME}__` | `r"__@\{\s*([A-Za-z0-9_]+)\s*\}__"` | 主動注入點。由編譯器 5-Step 狀態機進行 `replace` / `below` / `above` 多輪遞迴展開，解算完成後自動乾淨抹除殘留標籤行。 |
| **路徑佔位符 (URI Reference)** | `__#{URI_OR_PATH}__` | `r"__#\{\s*([^}]+)\s*\}__"` | 被動語意參照。於 Stage 1 快取中保留解耦，於 Stage 2 釋出發布時依三層階層（Tier 1 拓撲表 ➔ Tier 2 Core 協議 ➔ Tier 3 降級）動態轉譯為相對於目標檔案之本機實體相對路徑。 |

> [!TIP]
> 插入佔位符支援大括號內部微量空格容錯（例 `__@{ PHASEXX_STANDARD_HEADER }__` 與 `__@{PHASEXX_STANDARD_HEADER}__` 等價）。

---

## 3. Workflow URI 協議體系與組態治理

模組向 Core 貢獻 3 大專屬語意 URI 協議，動態綁定至 `config://agents-workflow/config.project.json`：

| 協議名稱 | 類型 | 預設模板值 | 一鍵初始化推薦路徑 | 核心職責說明 |
| :--- | :---: | :---: | :--- | :--- |
| `workflow.plans://` | `config` | `!undefined` | `project://.agent_workflow/plans` | 指向當前專案活躍開發計畫目錄。 |
| `workflow.archived://` | `config` | `!undefined` | `project://.agent_workflow/plans/archived` | 指向歷史封存計畫目錄。 |
| `workflow.docs://` | `config` | `!undefined` | `project://docs` | 指向專案知識庫目錄。 |

---

## 4. 釋出目標體系 (`release_target` Contributes)

模組支援宣告 `release_target`，定義不同開發環境（如 Google Antigravity IDE、Claude Code 等）的資產投影規則：
- **`projections`**：定義 `workflow`、`template`、`standard` 的目標目錄、副檔名與純文字/陣列 `header` 模板。
- **巨集插值**：`header` 支援 `{export.description}`、`{export.name}`、`{target.name}` 等巨集變數動態替換。
- **原子交易發布**：由 `ReleasePublisher` 基於 `storage://` 執行雙階 Diff 防護（Stage 0 來源指紋短路 + Stage 4 落地內容比對），大幅消除模組 reload 與重複發布的無效 File I/O，並依 `enable_agents_md` 軟合併專案根目錄 `AGENTS.md`。

---

## 5. 動態計算 Token (Computed Token Provider)

模組支援透過 `code.func://` 協議在編譯解算期動態調用 Python 函式生成內容：
- **`DYNAMIC_CONTEXT_MAP`**：由 `code.func://agents-workflow/providers:get_dynamic_context_map` 即時生成當前專案活躍語意 URI 解析地圖，注入 `ContextInit.md`。

---

## 6. CLI 快速使用指南

```bash
# 執行原子發布流水線（具備雙階 Diff 檢測，無變更時自動短路）
python yscb.py agents-workflow release

# 強制忽略 Diff 檢測，全量重新編譯與強制覆寫所有發布目標檔案
python yscb.py agents-workflow release --force

# 查詢全系統可用 Release Targets 與本專案啟用狀態
python yscb.py agents-workflow release-target --list

# 啟用指定 Release Target 並自動觸發原子發布
python yscb.py agents-workflow release-target --add antigravity

# 停用指定 Release Target 並自動清理已發布檔案
python yscb.py agents-workflow release-target --remove antigravity

# 一鍵初始化 Workflow 協議、建立推薦目錄並寫入組態 (支援 -y 自動確認)
python yscb.py agents-workflow --init-default [-y]

# 列出全系統已註冊之 Token 錨點清單與說明
python yscb.py agents-workflow tokens

# 列出當前所有模組導出之 Standards, Workflows, Templates 清冊
python yscb.py agents-workflow list

# 執行 Stage 1 內容編譯並寫入 cache.root://agents-workflow/resolved_contents/
python yscb.py agents-workflow compile

# --- Dev Plans 工具鏈 (Plans Management Toolchain) ---
# 掃描並輸出進行中開發計畫狀態矩陣 (ASCII 樹狀清冊)
python yscb.py agents-workflow plan status

# 跨計畫檢索決策記錄 (DR) 或全文程式碼
python yscb.py agents-workflow plan search --dr [--year=YYYY] [--month=MM] [--limit=N]
python yscb.py agents-workflow plan search "關鍵字" [--limit=N]

# 稽核計畫文件合規性與 Header 規範 (偵測未剝除之 AGENT_GUIDANCE 註解)
python yscb.py agents-workflow plan verify [plan_name] [--all]

# 安全歸檔已完成計畫至 workflow.archived://YYYY/MM/ (具備 4 重守門與 handoff 清理)
python yscb.py agents-workflow plan archive <plan_name> [--force]
```

---

## 7. 架構與專題手冊導引

- **Dev Plans 工具鏈完整操作手冊**：詳見 [user_guide.md](./user_guide.md)。
- **協議產物工廠化與 6 步語意管線**：詳見 [FACTORY_PIPELINE.md](./FACTORY_PIPELINE.md)。
- **設計決策與工程妥協**：詳見 [DESIGN_NOTES.md](./DESIGN_NOTES.md)。
