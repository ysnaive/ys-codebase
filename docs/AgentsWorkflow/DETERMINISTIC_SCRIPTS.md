---
target: "Modules/AgentsWorkflow/DeterministicScripts"
doc_type: "topic"
status: "active"
source_paths:
  - "source/agents-workflow/scripts/verify_plan.py"
  - "source/agents-workflow/scripts/scan_plan_status.py"
  - "source/agents-workflow/scripts/search_dev_plans.py"
  - "source/agents-workflow/scripts/archive_plan.py"
  - "source/agents-workflow/scripts/docs_tool.py"
related_docs:
  - "./README.md"
last_updated: "2026-08-23"
---

# 定式 Python 腳本工具庫指南 (Deterministic Scripts)

`agents-workflow` 包含一系列定式作業工具腳本，透過統一 CLI 路由器（`python yscb_cli.py agents-workflow <command>`）調度，旨在節省 Agent Context Token、提高執行可預測性並落實安全防護。

---

## 🛠️ 工具列表與使用手冊

### 1. `verify` (`verify_plan.py`) — Dev Plan 合規性與 Extension 深度稽核
- **用途**：秒級自動驗證 Dev Plan 的 Header 元數據格式、`changelog.md` 存在性、佔位符以及 `extensions/` 規範落實情況。
- **Agent 紀律**：執行 `/Review` 時**必須優先呼叫**此腳本。
- **語法**：
  ```bash
  python yscb_cli.py agents-workflow verify [plan_name]
  python yscb_cli.py agents-workflow verify --all
  ```

---

### 2. `scan` (`scan_plan_status.py`) — 專案進度與狀態矩陣掃描
- **用途**：快速掃描 `plans://` 中所有進行中與已完成計畫的進度矩陣。
- **Agent 紀律**：執行 `/Continue` 接續任務時優先調用。
- **語法**：
  ```bash
  python yscb_cli.py agents-workflow scan
  python yscb_cli.py agents-workflow scan --all
  ```

---

### 3. `search` (`search_dev_plans.py`) — 歷史計畫與 DR 決策全文檢索
- **用途**：快速全文檢索進行中與已歸檔計畫內容與 Decision Records (DR)。
- **Agent 紀律**：檢索歷史決策時優先調用，避免大範圍讀取 Markdown 檔消耗 Token。
- **語法**：
  ```bash
  python yscb_cli.py agents-workflow search --query "關鍵字"
  python yscb_cli.py agents-workflow search --dr --query "關鍵字"
  ```

---

### 4. `archive` (`archive_plan.py`) — Dev Plan 安全歸檔
- **用途**：將已完成的計畫目錄安全搬移至 `archive://YYYY/MM/`，並自動清理暫時性 `handoff.md`。
- **Agent 紀律**：⚠️ **絕對禁止 Agent 自行主動歸檔**，僅在開發者明確下達指令後方可執行。
- **語法**：
  ```bash
  python yscb_cli.py agents-workflow archive <plan_name> [--force]
  ```

---

### 5. `docs` (`docs_tool.py`) — 知識庫骨架、中觀專題與巡檢
- **用途**：自動化建立知識庫骨架、生成標準專題手冊 (Topic Docs) 與死鏈巡檢。
- **語法**：
  ```bash
  python yscb_cli.py agents-workflow docs init
  python yscb_cli.py agents-workflow docs new-topic <ModuleName> <TopicName>
  python yscb_cli.py agents-workflow docs audit
  ```

---

### 6. `ext` — 專案特化 SOP 擴充清單
- **用途**：查詢專案已註冊之 SOP 擴充與各 Phase 的 Checklist。
- **語法**：
  ```bash
  python yscb_cli.py agents-workflow ext list
  python yscb_cli.py agents-workflow ext show <extension_name>
  ```

