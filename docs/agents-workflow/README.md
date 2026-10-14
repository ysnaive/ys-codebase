---
title: Agents Workflow 模組手冊
category: overview
module: agents-workflow
updated_at: 2026-10-14
---

# Agents Workflow 模組 (General Agents Workflow Framework)

`agents-workflow` 為 YS-Codebase 體系的一等公民核心模組，提供通用、純淨且工廠化的 Agent 技能與規範治理體系。

---

## 1. 核心定位與資產架構

模組徹底剝離特定專案特化規則，採用 100% 純 Skill 分類架構（`standard`, `template`, `skill`），提供通用抽象資產：
- **規範 (`assets/standards/`)**：
  - `AgentsStandards.md`：Agent 通用核心原則、防呆紀律與條件式技能分流導航矩陣（自動注入至 `AGENTS.md`）。
- **技能 (`assets/skills/<name>/SKILL.md`)**：
  - **工作流與生命週期技能**：`context-init`（上下文熱啟動）、`new-plan`（標準立項與延遲建檔）、`auto`（Phase 01~05 自動連續推進）、`discuss`（深度歸因與範疇保護）、`continue`（中斷現場接續）、`pause`（現場狀態凍結）、`research`（深度技術調研）、`roadmap`（長期路線圖推薦）。
  - **領域與規範技能**：`development-sop`（SOP 0~7 與 6 大分支指南，含 `references/` 規範明細）、`documentation`（知識庫 3 層架構與 7 大維度指南）、`yscb-cli-guild`（CLI 指令防呆與權限矩陣）、`yscb-module-dev`（生態系模組開發與 Dogfooding 閉環）。
- **模板 (`assets/templates/`)**：
  - 14 大標準模板庫（`P00_discuss`, `P01`~`P07`, `fast_track_plan`, `umbrella_overview`, `changelog`, `RXX_research_report`, `handoff`, `roadmap`）與共用標頭。
- **擴充手冊**：[`contributes/_manifest.md`](../../ys_codebase/source/agents-workflow/contributes/_manifest.md) 官方擴充宣告格式規格書。

---

## 2. 佔位符語法與渲染機制 (Placeholder Architecture)

系統採用 Markdown 原生可視的強定義佔位符語法，淘汰被 HTML 隱藏的舊註解格式：

| 佔位符類型 | 語法結構 | 正則表達式 | 核心職責與編譯行為 |
| :--- | :--- | :--- | :--- |
| **插入佔位符 (Token Anchor)** | `__@{TOKEN_NAME}__` | `r"__@\{\s*([A-Za-z0-9_]+)\s*\}__"` | 主動注入點。由編譯器 5-Step 狀態機進行 `replace` / `below` / `above` 多輪遞迴展開，解算完成後自動乾淨抹除殘留標籤行。 |
| **自身相對路徑 (Local URI Reference)** | `__#{URI_OR_PATH}__` | `r"__#\{\s*([^}]+)\s*\}__"` | 被動語意參照。於 Stage 1 快取中保留解耦，於 Stage 2 釋出發布時依三層階層動態轉譯為相對於目標檔案所在目錄之實體相對路徑（用於 Markdown 超連結跳轉）。 |
| **專案相對路徑 (Project URI Reference)** | `__${URI_OR_PATH}__` | `r"__\$\{\s*([^}]+)\s*\}__"` | 相對於專案根目錄之相對路徑（用於終端 CLI 提示與檔案路徑展示）。 |
| **動態起點相對路徑 (Anchor URI Reference)** | `__$(ANCHOR){URI_OR_PATH}__` | `r"__\$\(([^)]+)\)\{\s*([^}]+)\s*\}__"` | 相對於指定錨點目錄之相對路徑（用於跨目錄與跨模組特定基準導航）。 |

> [!TIP]
> 佔位符支援大括號內部微量空格容錯（例 `__@{ PHASEXX_STANDARD_HEADER }__` 與 `__@{PHASEXX_STANDARD_HEADER}__` 等價）。編譯器支援 Standalone（剝除反引號）與 Inline（保留代碼引號）二分法解析。

---

## 3. Workflow URI 協議體系與組態治理

模組向 Core 貢獻 4 大專屬語意 URI 協議，動態綁定至 `config://agents-workflow/config.project.json`：

| 協議名稱 | 類型 | 預設模板值 | 一鍵初始化推薦路徑 | 核心職責說明 |
| :--- | :---: | :---: | :--- | :--- |
| `workflow.plans://` | `config` | `!undefined` | `project://plans` | 指向當前專案活躍開發計畫目錄。 |
| `workflow.archived://` | `config` | `!undefined` | `workflow.plans://archived` | 指向歷史封存計畫目錄。 |
| `workflow.docs://` | `config` | `!undefined` | `project://docs` | 指向專案知識庫目錄。 |
| `workflow.roadmap://` | `config` | `!undefined` | `workflow.plans://roadmap` | 指向專案長期策略技術路線圖儲備庫。 |

---

## 4. 釋出目標體系 (`release_target` Contributes)

模組支援宣告 `release_target`，定義不同開發環境（如 Google Antigravity IDE、Claude Code、OpenAI Codex 等）的資產投影規則：
- **`projections`**：定義 `template`、`standard` 與 `skill` 的目標目錄、副檔名與純文字/陣列 `header` 模板（`workflow` 投影已全面除役並收斂至 `skill`）。
- **`skill` 領域技能包**：支援目錄級與單檔級 Skill 套件導出與發布，保留內部 `references/`、`scripts/` 結構並以 `{export.name}` 巨集插值投影至 `.agents/skills/<name>/`。
- **`agents_md` 規範投影**：支援宣告 Target 專屬規範檔案路徑（如 `project://AGENTS.md` 或 `project://CLAUDE.md`），以 `AgentsStandards.md` 內容執行軟合併。
- **巨集插值**：`target_dir` 與 `header` 支援 `{export.description}`、`{export.name}`、`{export.basename}`、`{target.name}` 等巨集變數動態替換。
- **原子交易發布與舊目錄清理**：由 `ReleasePublisher` 基於 `storage://` 執行雙階 Diff 防護（Stage 0 來源指紋短路 + Stage 4 落地內容比對），並在發布時自動偵測清理歷史遺留之 `.agents/workflows/` 與 `.claude/commands/` 目錄。
- **JIT 變更感知自愈與自動投影 (`ensure_jit_release`)**：在執行任何 `agents-workflow` CLI 指令前自動檢驗來源指紋（含目錄級 Skill 遞迴 SHA-1 聚合指紋）。若模組資產、模板或片段發生變更，管線會自動原子同步最新內容至 `.agents/` 等 Target 目錄與 `AGENTS.md`。

---

## 5. 核心 Token 與行為準則擴充 (Tokens & Standards Injection)

模組支援宣告式 Token 錨點供生態系模組或專案組態擴充：
- **`PHASEXX_HEADER`**：共用計畫標頭插槽，提供標準標頭與後台模型 (`> 模型：[模型名稱]`) 溯源支援。
- **`WORKFLOW_SOP_STANDARDS`**：SOP 標準開發流程擴充錨點。
- **`AGENTS_SKILL_ROUTING` / `AGENTS_STANDARDS`**：位於 `AgentsStandards.md` 之擴充錨點，支援子模組或專案組態透過 `insert` 注入專屬技能分流與行為準則。
- **`AGENTS_CLI_GUILD`**：位於 `yscb-cli-guild` 之擴充錨點，供第三方模組追加專屬 CLI 操作情境手冊。
- **`SESSION_ANALYSIS_CHECK_ITEMS`**：位於 `session-analysis` 之對話審計項目擴充錨點。
- **`spaces.docs` 貢獻**：透過 `contributes/knowledge-db.json` 向知識庫微內核宣告 `workflow.docs://` 文檔空間。

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
python yscb.py agents-workflow release-target --add antigravity [--proj]

# 停用指定 Release Target 並自動清理已發布檔案
python yscb.py agents-workflow release-target --remove antigravity [--proj]

# 一鍵初始化 Workflow 協議、建立推薦目錄並寫入組態 (支援 -y 自動確認)
python yscb.py agents-workflow init --default [-y]

# 列出全系統已註冊之 Token 錨點清單與說明
python yscb.py agents-workflow tokens

# 列出當前所有模組導出之 Standards, Skills, Templates 清冊
python yscb.py agents-workflow list

# 執行 Stage 1 內容編譯並寫入 cache://agents-workflow/resolved_contents/
python yscb.py agents-workflow compile

# --- Dev Plans 工具鏈 (Plans Management Toolchain) ---
# 掃描並輸出進行中開發計畫狀態矩陣 (ASCII 樹狀清冊)
python yscb.py agents-workflow plan status

# 跨計畫檢索決策記錄 (DR) 或全文程式碼
python yscb.py agents-workflow plan search --dr [--year=YYYY] [--month=MM] [--limit=N]
python yscb.py agents-workflow plan search "關鍵字" [--limit=N]

# 稽核計畫文件合規性、模型標頭、佔位符與 Checkbox 完成度（--all 檢核所有活躍計畫）
python yscb.py agents-workflow plan verify [plan_name] [--all]

# 安全歸檔已完成計畫至 workflow.archived://YYYY/MM/ (具備 4 重守門與 handoff 清理)
python yscb.py agents-workflow plan archive <plan_name> [--force]
```

---

## 7. 架構與專題手冊導引

- **Dev Plans 工具鏈完整操作手冊**：詳見 [user_guide.md](./user_guide.md)。
- **協議產物工廠化與 6 步語意管線**：詳見 [FACTORY_PIPELINE.md](./FACTORY_PIPELINE.md)。
- **設計決策與工程妥協**：詳見 [DESIGN_NOTES.md](./DESIGN_NOTES.md)。
