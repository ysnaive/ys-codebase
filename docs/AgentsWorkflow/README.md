---
target: "Modules/AgentsWorkflow"
doc_type: "readme"
status: "active"
source_paths:
  - "source/agents-workflow/manifest.json"
  - "source/agents-workflow/config.project.template.json"
  - "source/agents-workflow/config.local.template.json"
  - "source/agents-workflow/workflows/"
  - "source/agents-workflow/scripts/"
related_docs:
  - "./THREE_TRACK_SYSTEM.md"
  - "./DETERMINISTIC_SCRIPTS.md"
  - "../_project/ARCHITECTURE.md"
last_updated: "2026-08-22"
---

# Agents Workflow 模組 (`agents-workflow`)

`agents-workflow` 是專為 AI Agent 與開發者協作打造的嚴謹、可追溯、防臆測的工程規範標準庫。

---

## 🌟 核心規範體系 (9 大 SOP 工作流)

| 工作流檔案 | 核心職責與適用場景 |
| :--- | :--- |
| **`ContextInit.md`** | 新對話 Session 開啟時，秒級熱啟動專案規範與脈絡記憶。 |
| **`NewPlan.md`** | 新功能開發/重大重構，執行 Phase 0~7 與三大分流體系。 |
| **`Continue.md`** | 任務中斷或跨 Session 時，依 `handoff.md` 自動恢復現場進度。 |
| **`Pause.md`** | 任務暫停、現場凍結並生成 `handoff.md`。 |
| **`Review.md`** | 結案前嚴格審查、調用 `verify_plan.py` 進行 Extension 深度稽核。 |
| **`Discuss.md`** | 開發遇阻/報錯時強制停手，執行 5-Whys 根因分析，防止淺層亂修。 |
| **`Research.md`** | 高複雜度架構方案選型、深度技術調研與 `R01_xxx.md` 報告產出。 |
| **`Idea.md`** | 開放式靈感孵化池，產出 What/Why/How 提案書。 |
| **`DocumentationStandards.md`** | 知識庫 1:1 鏡像四分法與 `docs/` 規範。 |

---

## ⚙️ 2×2 設定協定與 `!undefined` 剛性約束

- **專案級規範 (`config.project.json`)**：
  初始範本採用 `!undefined` 標記，強制要求專案初始化，避免盲目建立預設垃圾目錄：
  ```json
  {
    "version": "1.0",
    "paths": {
      "plans_dir": "!undefined",
      "archive_dir": "!undefined",
      "docs_dir": "!undefined"
    }
  }
  ```
- **本機個人偏好 (`config.local.json`)**：
  記錄開發者本機選擇之 IDE（如 `antigravity`）、前綴偏好等。

---

## 🛠️ 模組專案路徑初始化 (`init`)

安裝後可透過 `init` 指令快速設定專案 SOP 路徑：
```bash
# 1. 完整自訂路徑
python yscb_cli.py agents-workflow init --plans-dir plans --archive-dir archive_plans --docs-dir docs

# 2. 使用標準推薦預設值 (plans, archive_plans, docs)
python yscb_cli.py agents-workflow init --default
```

---

## 🤖 IDE 引用式指令生成與清理器 (`--ide-antigravity` / `--ide-clear`)

```bash
# 生成 Google Antigravity / Gemini 引用式指令 (例如 .agents/workflows/NewPlan.md)
python yscb_cli.py agents-workflow --ide-antigravity

# 附帶 sop_ 前綴生成 (例如 sop_NewPlan.md)
python yscb_cli.py agents-workflow --ide-antigravity -prefix "sop_"

# 附帶自訂前綴與後綴
python yscb_cli.py agents-workflow --ide-antigravity -prefix "sop-" -postfix "_v2"

# 一鍵清理所有由 IDE 生成器產生的指令
python yscb_cli.py agents-workflow --ide-clear
```

- **自動清理 (Pre-Generation Cleanup)**：調用 `--ide-antigravity` 時先檢查舊檔案並精準移除，防止孤兒檔案殘留。
- **引用式設計 (SSOT)**：生成的指令檔案僅包含 YAML Frontmatter 描述與指向核心工作流的相對路徑連結。
- **設定留痕**：相關生成紀錄自動保存於 `config.local.json`（個人本機偏好，不污染 Git）。

---

## 📚 深度主題文件

- [三大分流管控體系 (Three-Track System)](./THREE_TRACK_SYSTEM.md)：Level 0 (Fast Track)、Level 1 (Full Track) 與 Level 2 (Umbrella 主計畫)。
- [定式 Python 腳本工具庫](./DETERMINISTIC_SCRIPTS.md)：`verify_plan.py`、`scan_plan_status.py`、`search_dev_plans.py`、`archive_plan.py`。
