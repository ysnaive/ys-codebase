# API 與介面規格書 (API & Interface Specification)

> 功能名稱：`sub_02_agents_workflow_injection_optimization` (agents workflow 注入內容優化)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1049_knowledge_db_algorithm_optimization`  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 資產 / 介面名稱 | 所屬檔案路徑 | 注入 Token / 類型 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `KnowledgeAgentsStandards.md` | `ys_codebase/source/knowledge-db/assets/` | `AGENTS_STANDARDS` | 規範全域 Agent 檢索決策樹（簽章/複合詞/語意敘述分流）、定向閱讀哲學與 Docstring 符號防護 |
| `phase00_guild.md` | `ys_codebase/source/knowledge-db/assets/` | `PHASE00_AGENTS_GUILD` | Phase 0 需求探索時的定向檢索與 `-s` 代碼切片 JIT 指引 |
| `research_guild.md` | `ys_codebase/source/knowledge-db/assets/` | `RESEARCH_AGENTS_GUILD` | Research 調研前的既有能力預檢與複合詞檢索 JIT 指引 |
| `phase07_guild.md` | `ys_codebase/source/knowledge-db/assets/` | `PHASE07_AGENTS_GUILD` | Phase 7 結案時的 JIT 熱自愈說明（移除強制手動 index） |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `KnowledgeAgentsStandards.md` 規範規格
```markdown
### 🧠 知識庫檢索與註解防護規範 (Knowledge-DB Standards)

- **日常檢索決策樹與定向閱讀紀律 (Search Decision Tree & Targeted Reading Axiom)**：
  - **剛性檢索決策樹 (Search Decision Tree)**：
    Agent 在日常任何開發、除錯、排查、架構探索或概念搜尋時，必須嚴格依據以下決策路徑選擇工具：
    1. **已包含明確、獨一無二的符號/簽章？**（例：`foo.doSomething`、`class SnippetExtractor`、精確常數名）
       ➔ **直接調用原生精準工具**（如 `grep_search` 進行單一精確字串匹配）。
    2. **具備明確分類或模組功能概念？**（例："實體智能尋路模組"、"倒排索引快照"）
       ➔ **調用複合關鍵詞檢索**：`python yscb.py knowledge-db search '<關鍵詞組合>' -s`（例：`"實體 A* 尋路 pathfinding entity"`）。
    3. **廣義需求、語意探索或跨模組關聯？**（例："修改角色尋路行為"、"快取失效機制"）
       ➔ **調用語意化敘述檢索**：`python yscb.py knowledge-db search '<語意化需求>' -s`（例：`"修改角色尋路行為"`）。
  - **「定位 ➔ 定向閱讀」核心哲學**：
    - **非無條件暴力廣蒐**：嚴禁在未經知識庫收斂或未知精確簽章前，盲目發起全專案大範圍正則遍歷、暴力 grep 或逐檔翻找。
    - **代碼切片即時預覽**：一律優先附加 `-s`（或 `--snippet`）直接獲取精確行號、Docstring 摘要與上下文切片。
    - **定向閱讀最小化**：利用檢索結果之精確檔案與行號，進行極小範圍的定向閱讀（`view_file`）或單一目標確認，消除無效的二次磁碟 I/O。
- **Docstring 與符號結構防護鐵律 (Docstring Integrity Guardrail)**：
  - Agent 在編寫或重構 Public API 時，**嚴禁刪除或破壞已有的標準 Docstring 註解結構**，必須確保符號能被 `knowledge-db` AST 解析器無損提取。
```

### 2.2 `phase00_guild.md` 規格
```markdown
- **知識庫定向檢索指引**：在啟動 Phase 0 需求發想或架構釐清前，優先執行 `python yscb.py knowledge-db search <關鍵字> -s` 檢索既有符號、Docstring 與代碼切片，快速定位行位址並進行定向閱讀，避免盲目翻找原始碼。
```

### 2.3 `research_guild.md` 規格
```markdown
- **調研知識庫預檢指引**：在啟動技術調研 (Research) 前，優先以複合關鍵詞或語意敘述執行 `python yscb.py knowledge-db search <關鍵字> -s` 檢索既有架構設計與模組能力，避免重複發明輪子。
```

### 2.4 `phase07_guild.md` 規格
```markdown
- **知識庫索引同步指引**：本專案已具備 JIT 查詢智能變更感知與背景熱自愈機制，日常無需手動維護索引；若欲在交付後立即執行全量校準，亦可調用 `python yscb.py knowledge-db index`。
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[TASK-01] 編輯更新 KnowledgeAgentsStandards.md
    │
[TASK-02] 編輯更新 phase00_guild.md
    │
[TASK-03] 編輯更新 research_guild.md
    │
[TASK-04] 編輯更新 phase07_guild.md
    │
    ▼
[TASK-05] 執行 Stage 2: build knowledge-db
    │
    ▼
[TASK-06] 執行 Stage 3: run regression tests (198/198 passed)
    │
    ▼
[TASK-07] 執行 Stage 4: Dogfooding sync (install --force & agents-workflow --ide-antigravity)
```
