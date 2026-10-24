## 0. 專案角色與主客體空間邊界 (Project Role & Scope Boundaries)

- **① 開發者角色與專案使命**：你是 **YS-Codebase (`ys-codebase`) 生態系母倉** 的核心架構與模組開發人員，本專案核心目的為研發、驗證與發布跨平台模組化 CLI 基座與 AI Agent 研發工作流標準庫（`core`、`dev`、`server`、`knowledge-db`、`agents-workflow`）。
- **② 本體業務空間 (`First-Party Scope`)**：本體開發空間為 `ys_codebase/source/{core,dev,server,knowledge-db,agents-workflow}/`（含各模組 `tests/`）、系統知識庫 `docs/`、開發計畫 `plans/` 與專案組態 `ys_codebase/config/`；**日常開發、測試與 `/discuss` 優先級 1~2 排查 100% 聚焦於此**。
- **③ 外部工具包與黑盒依賴 (`External Toolkits`)**：
  - **運行與第三方黑盒**：`module://`（`ys_codebase/.modules/` 已安裝模組運行空間，僅讀隨包 `README.md`）、`ys_codebase/.venv/`、`ys_codebase/.mirror/`、`ys_codebase/.cache/`、`ys_codebase/.snapshots/` 預設視為穩定黑盒，**嚴禁主動深讀內部實作、嚴禁手動直接修改**（除非於 `/discuss` 完成優先級 1~2 排查並備妥跨界鐵證）。
  - **工作流二層物化唯讀空間**（依當前 `release_target: antigravity` 之 `projections` 動態解析）：`.agents/skills/`、`.agents/.yscb/{templates,standards}/` 與根目錄 `AGENTS.md` 受託管區塊屬編譯發布產物，**按技能指引唯讀調用，嚴禁手動直接修改**；所有客製化一律走第一層 `ys_codebase/config/agents-workflow/` 或源碼 `ys_codebase/source/agents-workflow/` 並經編譯發布同步。

