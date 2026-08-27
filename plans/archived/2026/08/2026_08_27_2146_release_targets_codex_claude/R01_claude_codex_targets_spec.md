<!--

技術調研報告撰寫指引：
1. 定位與目的：針對高複雜度、新技術選型、演算法評估或多方案權衡進行深度可行性論證與專題探討。
2. 命名規範：統一採用前綴 R{n:2d}_{topic}.md（例：R01_architecture_reference.md）。
3. 正文免除死板模板限制：本模板僅定義標準標頭與調研指引。正文由 Agent 依調研主題特性自由排版論述（可包含痛點背景、候選方案對比表 Pros & Cons、Mermaid 架構/時序圖、PoC 程式碼範例、Benchmark 數據、風險評估與明確落地建議）。
4. 結論收斂：調研成果收斂後，應將關鍵結論回填至 P00 語意需求書或主計畫路線圖，並於 changelog.md 登記。

-->

# 技術調研報告：Claude Code 與 Codex 規範與發布路徑調研

> 調研主題：Claude Code 與 Codex Release Target 路徑與規範調研  
> 建立日期：2026-08-27  
> 所屬主計畫：無  
> 調研狀態：Concluded  
> 模板版本：v1.0  

---

## 1. 背景與調研目標

本報告針對 Anthropic **Claude Code** 與 OpenAI **Codex CLI** 體系之行為規範、工作流指令 (Workflows / Slash Commands / Skills)、模板 (Templates) 與標準手冊 (Standards) 的官方檔案與目錄路徑約定進行深度調研，作為 `agents-workflow` 模組擴充 `release_target` 的架構依據。

---

## 2. 各平台核心目錄與檔案規範對照

| 維度 / 平台 | Google Antigravity (既有) | Anthropic Claude Code | OpenAI Codex CLI |
| :--- | :--- | :--- | :--- |
| **全域/專案行為規範** | `project://AGENTS.md` | `project://CLAUDE.md` | `project://AGENTS.md` |
| **自訂工作流 / 技能** | `project://.agents/workflows/{name}.md` | `project://.claude/commands/{name}.md` 或 `project://.claude/skills/{name}/SKILL.md` | `project://.agents/skills/{name}/SKILL.md` 或 `project://.codex/skills/{name}/` |
| **模板 (Templates)** | `project://.agents/.yscb/templates/` | `project://.claude/.yscb/templates/` (或 `.claude/templates/`) | `project://.codex/.yscb/templates/` (或 `.agents/.yscb/templates/`) |
| **標準 (Standards)** | `project://.agents/.yscb/standards/` | `project://.claude/.yscb/standards/` (或 `.claude/standards/`) | `project://.codex/.yscb/standards/` (或 `.agents/.yscb/standards/`) |
| **Slash Command 語法** | `/slash-command` | `/command` | `$ skill-name` 或 `/init` 等內建 |
| **指令 Frontmatter** | YAML: `description: ...` | YAML: `description: ...` | YAML Frontmatter (`name`, `description`) |

---

## 3. 詳細架構分析

### 3.1 Anthropic Claude Code
- **全域規則檔案**：專案根目錄下的 `CLAUDE.md`。Claude 在每次開啟工作階段時會優先載入此檔案作為專案指引。
- **Slash Commands 輸出方式**：
  - **模式 A (簡單指令 - `.claude/commands/{name}.md`)**：直接以單一 Markdown 檔案輸出，終端可直接以 `/{name}` 調用，檔案頂部可支援 YAML Frontmatter。
  - **模式 B (標準 Skill - `.claude/skills/{name}/SKILL.md`)**：每個指令為一子目錄，內含 `SKILL.md`。
- **建議 Release Target 拓撲**：
  - `workflow`: 輸出至 `project://.claude/commands` 或 `project://.claude/skills`。
  - `template`: 輸出至 `project://.claude/.yscb/templates`。
  - `standard`: 輸出至 `project://.claude/.yscb/standards`。
  - 另外提供 `CLAUDE.md` 的軟合併 (Soft-Merge) 注入機制。

### 3.2 OpenAI Codex (VS Code Extension 與 CLI 體系)
- **核心架構共用性**：
  - OpenAI Codex 的 **VS Code Extension** 與 **Codex CLI** 核心底層遵循相同的專案指引標準。
  - **專案行為準則**：兩者皆原生讀取專案根目錄下的 `project://AGENTS.md` 作為首要的「全域專案指令 (Always-on Project Instructions)」。
- **自訂指令 / 技能 (Workflows / Skills)**：
  - **通用標準**：Codex 體系原生掃描專案層級的 `project://.agents/skills/` 與 `project://.codex/` 目錄。
  - **VS Code Extension 擴充**：VS Code Extension 會讀取專案根目錄與 `.vscode/` 設定，並直接支援專案根目錄的 `AGENTS.md`。
- **建議 Release Target 拓撲**：
  - `workflow`: 輸出至 `project://.codex/workflows/`（或 `.agents/workflows/`）。
  - `template`: 輸出至 `project://.codex/.yscb/templates/`。
  - `standard`: 輸出至 `project://.codex/.yscb/standards/`。
  - 專案根目錄 `AGENTS.md` 自動與 Antigravity/Codex 共享標準規範。

---

## 4. 落地架構建議與待確認事項

1. **Claude Code 拓撲選型**：
   - 方案 A（推薦）：`workflow` 採用 `.claude/commands/{name}.md`，最貼合原生 Slash Commands 輕量體驗；Templates 與 Standards 置於 `.claude/.yscb/`。
   - 方案 B：`workflow` 採用 `.claude/skills/{name}/SKILL.md`。
2. **Codex 拓撲選型**：
   - 方案 A（專用目錄）：`workflow` 採用 `.codex/workflows/{name}.md`，Templates 與 Standards 置於 `.codex/.yscb/`。
   - 方案 B（OpenAI Agents 共享）：`workflow` 輸出至 `.agents/skills/{name}/SKILL.md`。
3. **專案規則檔同步**：
   - `CLAUDE.md`：需確認是否在 `ReleasePublisher` 中新增對 `CLAUDE.md` 的軟合併支援。
