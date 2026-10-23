# 技術路線圖：主流 AI 開發平台與自訂模型客戶端 `release_target` 預設矩陣擴充 (Roadmap)

> 主題：主流 AI 開發平台與自訂模型客戶端 `release_target` 預設矩陣擴充  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
1. **預設 `release_target` 涵蓋率不足**：目前 `agents-workflow/contributes/agents-workflow.json` 僅預設提供 `antigravity`、`claude`、`codex` 三個發布目標，缺少對市面上其他廣泛使用的中游 AI IDE 與 CLI Agent（如 **Cursor**、**GitHub Copilot**、**Windsurf**、**OpenCode**、**Roo Code / Cline** 等）的開箱即用支援。
2. **自訂模型（GLM / DeepSeek / Qwen / Ollama）使用者存在認知斷層**：許多下游開發者使用 GLM（智譜）、DeepSeek 等模型時，不清楚 `release_target` 對應的是「中游 IDE / CLI 外殼工具（Client Harness）」而非「底層大模型（LLM）」，導致在初始化工作流時不知該啟用哪一個 Target。

### 1.2 現況與影響範圍評估
- **架構優勢確認（僅需極小化對齊 `compiler.py` 子目錄基準路徑 + 顯式 JSON 宣告）**：
  - 經核驗 `ReleasePublisher` (`publisher.py`) 與 `contributes/_format.json`，現有發布引擎已原生支援任意 `.md` 規範入口檔路徑（含子目錄如 `project://.github/copilot-instructions.md` 之自動建目與軟合併／軟剝離）以及任意隱藏目錄之 `projections` 投影。
  - **關鍵邊界防呆（`copilot` 子目錄 `agents_md` 相對連結基準路徑修正）**：現有 `compiler.py` (`_compile_stage2`) 在解析 `AgentsStandards.md`（`export.type == "standard"`）內的 `__#{...}__` 語意連結時，原先固定以 `project_root`（根目錄，深度 0）作為 `current_file_dir` 計算相對路徑；但 `copilot` Target 的 `agents_md` 為 `project://.github/copilot-instructions.md`（位於 `.github/` 子目錄，深度 1），若仍以根目錄計算相對連結，寫入 `.github/copilot-instructions.md` 後內文的 `.github/skills/...` 連結會在 Markdown 解析下變成 `.github/.github/skills/...` 而斷鏈。因此需於 `compiler.py` 微調約 5 行邏輯：當 `export.name == "AgentsStandards"` 時，優先以該 Target 設定的 `agents_md` 父目錄（`agents_md_path.parent`）作為 `current_file_dir` 計算相對路徑。
  - **Open Agent Standard (`.agents/` + `AGENTS.md`) 家族收斂**：Google Gemini CLI、Cline 等工具已與 Antigravity / Codex 同步採用根目錄 `AGENTS.md` + `.agents/skills/` 標準，無需重複建立冗餘目錄或複雜別名繼承機制。
  - 因此僅需以 **顯式 JSON 宣告擴充 `contributes/agents-workflow.json` ＋ `compiler.py` `agents_md.parent` 基準路徑對齊**，並於隨包文檔與教學／配置技能中補齊「主流平台與自訂模型（GLM / DeepSeek）外殼選型對照表」，即可一步到位支援全生態系主流工具。

### 1.3 核心根因
1. `contributes/agents-workflow.json` 尚未將 Cursor、GitHub Copilot、Windsurf、OpenCode、Roo Code 等具備獨立技能投影目錄（`.cursor/`、`.github/`、`.windsurf/`、`.opencode/`、`.roo/`）之主流平台納入預設 `release_target` 清冊。
2. 隨包 `README.md` 與 `user_guide.md` 尚未說明共用 `.agents/` 標準之平台範圍（Gemini CLI、Cline）及自訂模型（GLM / DeepSeek）與客戶端外殼之映射關係。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：維持現有 3 個 Target，由下游自行手動配置** | 下游專案自行在 `contribute.json` 撰寫 Cursor / Copilot 等投影規則 | 零改動 | 下游需自行查閱各 IDE 的 Skills 規範路徑，開箱體驗差 | ⭐️⭐️ |
| **方案 2：修改 Python 編譯器新增 `aliases` 別名與繼承語法** | 修改 `_format.json`、`compiler.py` 與 `cli.py` 支援 Target 別名與模板繼承 | 減少 JSON 中約 15 行的重複路徑宣告 | 違反 YAGNI / KISS 原則；為極少數靜態 JSON 引入額外 Python 代碼與測試維護成本，且降低 JSON 直觀可讀性 | ⭐️⭐️⭐️ |
| **方案 3：顯式 JSON 宣告擴充 + `agents_md` 子目錄基準路徑對齊 + 平台／模型外殼選型對照表（推薦採納）** | 直接於 `contributes/agents-workflow.json` 顯式新增 `cursor`、`copilot`、`windsurf`、`opencode`、`roo` 五大 Target，微調 `compiler.py` 使 `AgentsStandards` 以 `agents_md` 父目錄計算相對連結，更新 `antigravity` 描述涵蓋 Gemini CLI / Cline，並於文檔補齊 GLM / DeepSeek 外殼選型指南 | 1. **解決 `.github/copilot-instructions.md` 子目錄相對連結深度偏移問題**<br/>2. **顯式宣告一目了然**，未來單一平台改路徑可獨立微調<br/>3. 徹底解決 GLM / DeepSeek 使用者選型困惑 | 約 90 行靜態 JSON 宣告、`compiler.py` 約 5 行基準目錄對齊與文檔表格更新 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（維持現狀） | 方案 2（Python 別名機制） | 方案 3（0 改碼顯式 JSON 宣告） |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 中（需改 Schema 與 CLI） | **極高（現有 `ReleasePublisher` 100% 原生支援）** |
| **後續維護難度 (Maintenance)** | 高（下游重複造輪子） | 中（需維護別名解析邏輯） | **極低（純靜態 JSON 與文檔對齊）** |
| **可靠性 (Reliability)** | 中 | 高 | **最高（完全複用既有雙階 Diff 與軟合併/軟剝離管線）** |
| **落地難度 (Implementation)** | 無 | 中 | **極低（Fast Track 級別即可完成）** |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

### 4.1 預設 8 大 `release_target` 完整投影矩陣

於 `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` 顯式定義以下 8 大預設 Target：

| 分類 | Target 名稱 | 適用主流平台 / CLI 外殼 | 規範入口檔 (`agents_md`) | Skills 投影目錄 (`projections.skill`) | Templates / Standards 目錄 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **既有（更新描述）** | **`antigravity`** | Google Antigravity IDE / **Gemini CLI** / **Cline** | `project://AGENTS.md` | `project://.agents/skills/{export.name}` | `project://.agents/.yscb/{templates,standards}` |
| **既有** | **`claude`** | Anthropic Claude Code | `project://CLAUDE.md` | `project://.claude/skills/{export.name}` | `project://.claude/.yscb/{templates,standards}` |
| **既有** | **`codex`** | OpenAI Codex CLI / VS Code Extension | `project://AGENTS.md` | `project://.agents/skills/{export.name}` | `project://.agents/.yscb/{templates,standards}` |
| **新增 1** | **`cursor`** | **Cursor IDE** (Agent Mode) | `project://AGENTS.md` | `project://.cursor/skills/{export.name}` | `project://.cursor/.yscb/{templates,standards}` |
| **新增 2** | **`copilot`** | **GitHub Copilot** (VS Code / CLI / Coding Agent) | `project://.github/copilot-instructions.md` | `project://.github/skills/{export.name}` | `project://.github/.yscb/{templates,standards}` |
| **新增 3** | **`windsurf`** | **Windsurf IDE** (Cascade Agent) | `project://AGENTS.md` | `project://.windsurf/skills/{export.name}` | `project://.windsurf/.yscb/{templates,standards}` |
| **新增 4** | **`opencode`** | **OpenCode CLI** | `project://AGENTS.md` | `project://.opencode/skills/{export.name}` | `project://.opencode/.yscb/{templates,standards}` |
| **新增 5** | **`roo`** | **Roo Code** (VS Code Extension) | `project://AGENTS.md` | `project://.roo/skills/{export.name}` | `project://.roo/.yscb/{templates,standards}` |

### 4.2 自訂模型（GLM / DeepSeek / Qwen / Ollama）使用者選型指引

於 `README.md`、`docs/agents-workflow/user_guide.md`（及未來之 `how-to-config-yscb` / `how-to-yscb`）明確補充說明：
- **`release_target` 綁定的是「客戶端工具（IDE / CLI 外殼）」，而非底層模型名稱**。
- 當開發者使用 **GLM（智譜清言）、DeepSeek、Qwen 或本地 Ollama** 時，應依據實際掛載 API 的客戶端工具啟用對應 Target：
  - 透過 **Claude Code CLI**（設定 `ANTHROPIC_BASE_URL` 掛載 GLM / DeepSeek）$\to$ 啟用 **`claude`**
  - 透過 **VS Code Roo Code 外掛** 掛載 GLM / DeepSeek $\to$ 啟用 **`roo`**（若用 Cline 外掛則啟用 **`antigravity`**）
  - 透過 **OpenCode CLI** 掛載 GLM / DeepSeek $\to$ 啟用 **`opencode`**
  - 透過 **Cursor / Windsurf IDE** 掛載自訂模型 API $\to$ 啟用 **`cursor`** 或 **`windsurf`**

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 列為 `Ready` 技術儲備，因屬於宣告式 JSON 擴充、`compiler.py` 單點基準路徑對齊與文檔同步，可單獨以 `Fast Track` 快速落地，或併入近期 `agents-workflow` 演進計畫一併交付。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1（`contributes/agents-workflow.json` 宣告擴充與 `compiler.py` 子目錄基準對齊）**：新增 `cursor`、`copilot`、`windsurf`、`opencode`、`roo` 五組 `release_target` 定義，更新 `antigravity` 描述涵蓋 Gemini CLI 與 Cline；並修正 `compiler.py` 中 `AgentsStandards` 的 Stage 2 `current_file_dir` 計算邏輯，使其以目標 Target 之 `agents_md` 父目錄（如 `project://.github/`）為基準計算相對連結（確保 `.github/copilot-instructions.md` 內之連結正確指向 `skills/...` 而非 `.github/skills/...`）。
2. **Stage 2（測試驗證）**：新增單元測試驗證各新增 Target（特別是帶子目錄之 `.github/copilot-instructions.md` 內相對連結深度 `skills/development-sop/SKILL.md` 與各 `.<target>/skills/`）之 Stage 2 相對路徑計算、軟合併與移除時之軟剝離行為。
3. **Stage 3（三層文檔與平台選型表對齊）**：同步更新根目錄 `README.md`、`ys_codebase/source/agents-workflow/README.md` 與 `docs/agents-workflow/user_guide.md` 之 Target 矩陣與 GLM / DeepSeek 客戶端選型提示。

