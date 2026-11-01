# 技術路線圖：主流 AI 開發平台與自訂模型客戶端 `release_target` 預設矩陣擴充 (Roadmap)

> 主題：主流 AI 開發平台與自訂模型客戶端 `release_target` 預設矩陣擴充 (`multi_platform_release_targets_expansion_roadmap`)  
> 歸檔日期：2026-11-01  
> 狀態：Ready  
> 目標範疇：`agents-workflow`（`contributes/agents-workflow.json`、`compiler.py`、`publisher.py`、隨包 `README.md` 與 `docs/agents-workflow/user_guide.md`）  
> 前置解鎖條件：完成 `[TODO-05]` 同實體路徑多 `release_target` 並聯渲染與覆寫守門機制  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **預設 `release_target` 涵蓋率不足**：目前 `agents-workflow` 僅預設提供 `antigravity`、`claude`、`codex` 三個發布目標，缺少對市面上其他廣泛使用的中游 AI IDE 與 CLI Agent（如 **Cursor**、**GitHub Copilot**、**Windsurf**、**OpenCode**、**Roo Code / Cline** 等）的開箱即用支援。
  - **自訂模型（GLM / DeepSeek / Qwen / Ollama）使用者存在認知斷層**：許多下游開發者使用自訂大模型時，不清楚 `release_target` 對應的是「中游 IDE / CLI 外殼工具（Client Harness）」而非「底層大模型（LLM）」，導致初始化工作流時不知該啟用哪一個 Target。
- **長期願景與目標定位**：
  - 透過宣告式 JSON 擴充與多 Target 共用路徑並聯渲染機制，一步到位支援主流 AI 開發平台（`antigravity` / `Gemini CLI` / `Cline`、`claude`、`codex`、`cursor`、`copilot`、`windsurf`、`opencode`、`roo`），並建立清晰的「客戶端外殼 vs. 底層模型」選型指引。
- **範疇與邊界約束**：
  - 涵蓋 `agents-workflow` 預設 `release_target` 宣告矩陣、子目錄規範入口檔（如 `.github/copilot-instructions.md`）之相對連結基準目錄對齊、多 Target 共用實體路徑（如共用 `AGENTS.md` 或 `.agents/skills/`）之並聯渲染，以及三層文檔同步。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **顯式宣告優於隱式別名繼承**：各平台 Target 之 `agents_md` 與 `projections` 採顯式 JSON 宣告，確保單一平台調整目錄規範時可獨立演進；共用 Open Agent Standard（`AGENTS.md` + `.agents/skills/`）之工具（如 Gemini CLI、Cline）直接複用 `antigravity` Target。
  - **子目錄規範入口檔相對路徑基準對齊**：當 Target 之 `agents_md` 位於子目錄（例如 `copilot` 之 `project://.github/copilot-instructions.md`）時，Stage 2 編譯 `AgentsStandards` 的相對連結必須以 `agents_md` 所屬父目錄為基準計算，防止相對路徑深度偏移斷鏈。
  - **同路徑多 Target 零無聲覆寫（綁定 `[TODO-05]`）**：當專案同時啟用多個指向相同實體路徑（如共用 `project://AGENTS.md` 或 `project://.agents/skills/`）之 Target 時，編譯與發布管線必須對宿主工具專有名詞（`__%{agent_tool.*}__`）與技能路由連結執行去重並聯渲染或衝突守門，嚴禁後執行的 Target 無聲覆寫前一個 Target 的物化內容。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **8 大預設 `release_target` 投影拓撲**：
    - `antigravity`（Google Antigravity / Gemini CLI / Cline）：`project://AGENTS.md` + `project://.agents/skills/{export.name}`
    - `claude`（Claude Code）：`project://CLAUDE.md` + `project://.claude/skills/{export.name}`
    - `codex`（OpenAI Codex）：`project://AGENTS.md` + `project://.agents/skills/{export.name}`
    - `cursor`（Cursor IDE）：`project://AGENTS.md` + `project://.cursor/skills/{export.name}`
    - `copilot`（GitHub Copilot）：`project://.github/copilot-instructions.md` + `project://.github/skills/{export.name}`
    - `windsurf`（Windsurf IDE）：`project://AGENTS.md` + `project://.windsurf/skills/{export.name}`
    - `opencode`（OpenCode CLI）：`project://AGENTS.md` + `project://.opencode/skills/{export.name}`
    - `roo`（Roo Code）：`project://AGENTS.md` + `project://.roo/skills/{export.name}`
  - **外殼與模型解耦選型指引**：於文檔與教學技能中明確規範，使用 GLM、DeepSeek、Qwen 或 Ollama 時，一律依實際掛載 API 之「客戶端外殼（IDE / CLI）」選擇對應 `release_target`。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - 需先完成或於同一計畫內併入 `[TODO-05]`（解決多個 `release_target` 共用 `project://AGENTS.md` 或 `project://.agents/skills/` 時之專有名詞與路由連結覆寫問題），確保多 Target 並發啟用時 100% 相容。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（編譯器基準路徑與多 Target 共用路徑並聯加固）**：對齊 `AgentsStandards` 子目錄相對連結基準計算，並落實同實體路徑多 Target 之專有名詞/路由並聯渲染與衝突守門。
  2. **Stage 2（預設 Target 矩陣擴充與單元測試）**：於 `contributes/agents-workflow.json` 擴充 `cursor`、`copilot`、`windsurf`、`opencode`、`roo` 五大 Target，並驗證單 Target 與多 Target 並發物化及軟剝離行為。
  3. **Stage 3（三層文檔與外殼選型指南同步）**：更新 `README.md`、`user_guide.md` 與配置引導技能之平台對照表。
