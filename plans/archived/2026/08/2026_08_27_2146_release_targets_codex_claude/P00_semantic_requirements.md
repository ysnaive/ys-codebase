<!--

Phase 0 執行指引：
1. 目標：在動筆寫任何規格前，以開放式對話完整釐清開發者的真實意圖與使用情境，建立可追溯的語意需求說明書 (P00_semantic_requirements.md)。
2. 討論模式三大原則：
   - Agent = 知識顧問：提問釐清、提供業界參考、揭示潛在邊界，絕對不主動提出設計方案或功能列表（除非開發者明確要求）。
   - 開發者主導結束：討論必須由開發者明確宣告結束，Agent 嚴禁自行判定需求完整並推進。
   - 先 P00 後分流：完整討論 ➔ P00 Confirmed ➔ 在同一輪呈遞三大層級分流判定建議。
3. 雙星伴隨初始化：開立計畫目錄時，P00 必須與 changelog.md 剛性伴隨同時建立，並立即寫入第 1 筆紀錄。
4. 深度調研 (Phase 0-R)：高複雜度或高未知需求啟動專題調研，產出 R{n:2d}_{topic}.md 專題調研報告，結論收斂回填 P00。
5. Checkpoint 等待關卡：等待開發者明確確認 P00 內容（狀態更新為 Confirmed），並由開發者決定後續執行 Track。

-->

# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：agents-workflow 添加 codex 與 claude code release targets  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：想於 agents-workflows 添加給 codex 和 claude code 的 release target
- **核心目標**：於 `agents-workflow` 模組中新增支援 Anthropic Claude Code (`claude`) 與 OpenAI Codex (`codex`) 的 Release Target 宣告與路徑投影，使多種 AI IDE 與 Agent 能共用同一套高保真工作流與標準規範。
- **邊界排除 (Explicitly Excluded)**：
  - 暫不實作 `CLAUDE.md` 專案規則檔的自動軟合併機制（專案規則目前依各平台現狀或由使用者自行維護）。
  - 暫不處理 Cursor / Windsurf 等其他未列入之 IDE 目錄特化。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 完成 Claude Code 與 Codex 規範深度調研，詳見 [R01_claude_codex_targets_spec.md](file:///h:/UseFolder/CodeRepo/ys_codebase/plans/2026_08_27_2146_release_targets_codex_claude/R01_claude_codex_targets_spec.md)。
- **[P00:DR-02]** Claude Code (`claude`) Target 拓撲定案：
  - `workflow`: 輸出至 `project://.claude/commands/{name}.md`，支援 YAML Frontmatter (`description: ...`)。
  - `template`: 輸出至 `project://.claude/.yscb/templates/{name}.md`。
  - `standard`: 輸出至 `project://.claude/.yscb/standards/{name}.md`。
  - `CLAUDE.md` 規則檔軟合併：依開發者指示**排除不實作**。
- **[P00:DR-03]** Codex (`codex`) Target 拓撲定案：
  - `workflow`: 輸出至 `project://.codex/workflows/{name}.md`，支援 YAML Frontmatter (`description: ...`)。
  - `template`: 輸出至 `project://.codex/.yscb/templates/{name}.md`。
  - `standard`: 輸出至 `project://.codex/.yscb/standards/{name}.md`。
  - `AGENTS.md` 專案規則檔：維持現有 `AGENTS.md` 軟合併機制。
- **[P00:DR-04]** 模組註冊名稱定案：Target 名稱分別為 `claude` 與 `codex`。

---

## 3. 開放議題與確認紀錄

- [x] **Claude Code 拓撲結構確認**：採方案 A，`workflow` 輸出至 `.claude/commands/{name}.md`，Templates 與 Standards 輸出至 `.claude/.yscb/`。
- [x] **Codex 拓撲結構確認**：採方案 A，`workflow` 輸出至 `.codex/workflows/{name}.md`，Templates 與 Standards 輸出至 `.codex/.yscb/`。
- [x] **專案層級規則檔案 (`CLAUDE.md`) 支援**：依指示排除，本次暫不處理。
- [x] **Target 名稱註冊命名**：註冊名稱定案為 `claude` 與 `codex`。
