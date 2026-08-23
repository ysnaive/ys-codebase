---
target: "Modules/AgentsWorkflow"
doc_type: "readme"
status: "active"
source_paths:
  - "source/agents-workflow/manifest.json"
  - "source/agents-workflow/config.project.template.json"
  - "source/agents-workflow/config.local.template.json"
  - "source/agents-workflow/workflows/commands/"
  - "source/agents-workflow/scripts/"
related_docs:
  - "./THREE_TRACK_SYSTEM.md"
  - "./DETERMINISTIC_SCRIPTS.md"
  - "./SOP_INTERLOCK_PROTOCOL.md"
  - "../_project/ARCHITECTURE.md"
last_updated: "2026-08-23"
---

# Agents Workflow 模組 (`agents-workflow`)

`agents-workflow` 是專為 AI Agent 與開發者協作打造的嚴謹、可追溯、防臆測的工程規範標準庫。

---

## 🌟 核心規範體系 (9 大 SOP 工作流)

基準工作流由 `workflows/commands/*.md` 維護（單一事實來源 SSOT），並支援外掛模組動態插槽注入：

| 工作流檔案 | 核心職責與適用場景 | 具備之 Slot 插槽 |
| :--- | :--- | :---: |
| **`ContextInit.md`** | 新對話 Session 開啟時，秒級熱啟動專案規範與脈絡記憶。 | `Step1` ~ `Step4` |
| **`NewPlan.md`** | 新功能開發/重大重構，執行 Phase 0~7 與三大分流體系。 | `Phase0` ~ `Phase7` |
| **`Continue.md`** | 任務中斷或跨 Session 時，依 `handoff.md` 自動恢復現場進度。 | 無 |
| **`Pause.md`** | 任務暫停、現場凍結並生成 `handoff.md`。 | 無 |
| **`Review.md`** | 結案前嚴格審查、調用 `verify_plan.py` 進行 Extension 深度稽核。 | `Step1` ~ `Step4` |
| **`Discuss.md`** | 開發遇阻/報錯時強制停手，執行 5-Whys 根因分析，防止淺層亂修。 | 無 |
| **`Research.md`** | 高複雜度架構方案選型、深度技術調研與 `R01_xxx.md` 報告產出。 | 無 |
| **`Idea.md`** | 開放式靈感孵化池，產出 What/Why/How 提案書。 | 無 |
| **`DocumentationStandards.md`** | 知識庫 1:1 鏡像四分法與 `docs/` 規範。 | 無 |

---

## 🔗 安裝期模組連動與動態插槽補丁 (SOP Interlock Protocol)

`agents-workflow` 作為宿主模組，公開 `"agents-workflow"` 命名空間協定，允許下游外掛模組在安裝期透過 `manifest.json` 貢獻補丁與擴充：

- **動態 Slot 注入**：支援向 `NewPlan.md`、`Review.md`、`ContextInit.md` 的指定插槽執行 `append` 或 `prepend` 注入。
- **雙層 Extension 發現**：`ExtensionRegistry` 自動調度 `sop_ext://`（專案自定義，優先覆蓋）與 `modules/<plugin>/` 貢獻之擴充清單與驗證腳本。
- **無感自動同步**：在安裝外掛時，自動感知並即時重構 `.agents/workflows/` 指令，清理孤兒檔案。

> 📖 **詳細協定規格請參閱專題手冊**：[模組安裝期連動協定與動態插槽注入手冊 (SOP_INTERLOCK_PROTOCOL.md)](./SOP_INTERLOCK_PROTOCOL.md)

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
      "docs_dir": "!undefined",
      "extensions_dir": "!undefined",
      "agents_md_path": "!undefined"
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
python yscb_cli.py agents-workflow init --plans-dir plans --archive-dir archive_plans --docs-dir docs --extensions-dir extensions

# 2. 使用標準推薦預設值 (plans, archive_plans, docs, extensions, AGENTS.md)
python yscb_cli.py agents-workflow init --default
```

---

## 🧩 SOP Extension 擴充查詢與檢視 (`ext`)

```bash
# 列出專案所有可用 Extension 清單 (含 [sop_ext] 與 [module: xxx] 雙層來源標籤)
python yscb_cli.py agents-workflow ext list

# 檢視指定 Extension 完整內容
python yscb_cli.py agents-workflow ext show <extension_name>
```

---

## 🤖 IDE 指令生成與清理器 (`--ide-antigravity` / `--ide-clear`)

```bash
# 為 Google Antigravity / Gemini 生成引用式指令 (自動連動合成 + JIT 語意解析注入 + 孤兒清理)
python yscb_cli.py agents-workflow --ide-antigravity

# 附帶 sop_ 前綴生成 (例如 sop_NewPlan.md)
python yscb_cli.py agents-workflow --ide-antigravity -prefix "sop_"

# 一鍵清理所有由 IDE 生成器產生的指令
python yscb_cli.py agents-workflow --ide-clear
```

---

## 📚 深度主題文件

- [模組安裝期連動協定與動態插槽注入手冊 (SOP_INTERLOCK_PROTOCOL.md)](./SOP_INTERLOCK_PROTOCOL.md)：三大合約、Slot 插槽表與無感同步流水線。
- [三大分流管控體系 (THREE_TRACK_SYSTEM.md)](./THREE_TRACK_SYSTEM.md)：Level 0 (Fast Track)、Level 1 (Full Track) 與 Level 2 (Umbrella 主計畫)。
- [定式 Python 腳本工具庫 (DETERMINISTIC_SCRIPTS.md)](./DETERMINISTIC_SCRIPTS.md)：`verify_plan.py`、`scan_plan_status.py`、`search_dev_plans.py`、`archive_plan.py`。
