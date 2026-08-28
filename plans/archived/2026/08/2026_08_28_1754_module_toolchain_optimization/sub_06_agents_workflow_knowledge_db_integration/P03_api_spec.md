# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Knowledge-DB 與 Agents-Workflow 雙向 Contributes 聯動與 Space 解耦 (Knowledge-DB & Agents-Workflow Bidirectional Contributes & Space Decoupling)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_06)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 宣告 / 資產名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `configurable/contribute.json` | `source/knowledge-db/configurable/contribute.json` | Public / Config | 模組組態模板：清空預設空間，提供空空間骨架 |
| `contributes/knowledge-db.json` | `source/agents-workflow/contributes/knowledge-db.json` | Public / Contributes | 宣告 `docs` 空間，指向 `workflow.docs://` |
| `config/knowledge-db/contribute.json` | `config/knowledge-db/contribute.json` | Project / Config | 宿主專案宣告 `source` 空間，指向專案源碼目錄 |
| `contributes/agents-workflow.json` | `source/knowledge-db/contributes/agents-workflow.json` | Public / Contributes | 宣告 `insert` 映射，注入行為準則與 JIT 指引 |
| `KnowledgeAgentsStandards.md` | `source/knowledge-db/assets/KnowledgeAgentsStandards.md` | Public / Asset | 知識檢索優先紀律 (Knowledge-First) 與 Docstring 防護鐵律 |
| `phase00_guild.md` / `research_guild.md` | `source/knowledge-db/assets/*_guild.md` | Public / Asset | Phase 0 / Research JIT 指引：引導使用 `knowledge-db search` |
| `phase07_guild.md` | `source/knowledge-db/assets/phase07_guild.md` | Public / Asset | Phase 7 JIT 指引：引導使用 `knowledge-db index` 更新索引庫 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `source/agents-workflow/contributes/knowledge-db.json`
```json
{
  "spaces": {
    "docs": {
      "description": "專案知識庫與設計文檔空間 (由 agents-workflow 貢獻)",
      "include": [
        "workflow.docs://"
      ],
      "exclude": [
        "**/__pycache__/**",
        "**/.git/**"
      ]
    }
  }
}
```

### 2.2 `source/knowledge-db/contributes/agents-workflow.json`
```json
{
  "insert": [
    {
      "type": "uri",
      "token": "AGENTS_STANDARDS",
      "value": "module://knowledge-db/assets/KnowledgeAgentsStandards.md",
      "mode": "below"
    },
    {
      "type": "uri",
      "token": "RESEARCH_AGENTS_GUILD",
      "value": "module://knowledge-db/assets/research_guild.md",
      "mode": "below"
    },
    {
      "type": "uri",
      "token": "PHASE00_AGENTS_GUILD",
      "value": "module://knowledge-db/assets/phase00_guild.md",
      "mode": "below"
    },
    {
      "type": "uri",
      "token": "PHASE07_AGENTS_GUILD",
      "value": "module://knowledge-db/assets/phase07_guild.md",
      "mode": "below"
    }
  ]
}
```

### 2.3 `source/knowledge-db/assets/KnowledgeAgentsStandards.md`
```markdown
### 🧠 知識庫檢索與註解防護規範 (Knowledge-DB Standards)

- **知識檢索優先紀律 (Knowledge-First Axiom)**：
  - Agent 在探索專案架構、查找類別/函式或尋找既有實現時，**必須優先調用 `python yscb.py knowledge-db search <query>` 或查閱 `workflow.docs://` 知識庫**。
  - **絕對禁止**在未經定向索引前，盲目發起大範圍檔案正則遍歷、暴力 grep 或逐檔全文讀取。
- **Docstring 與符號結構防護鐵律 (Docstring Integrity Guardrail)**：
  - Agent 在編寫或重構 Public API 時，**嚴禁刪除或破壞已有的標準 Docstring 註解結構**，必須確保符號能被 `knowledge-db` AST 解析器無損提取。
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 空間模板解耦]
   └── source/knowledge-db/configurable/contribute.json (清空預設 spaces)
   └── config/knowledge-db/contribute.json (宣告專案 source 空間)

[Step 2: 工作流錨點與空間貢獻]
   └── source/agents-workflow/assets/standards/AgentsStandards.md (補齊 __@{AGENTS_STANDARDS}__)
   └── source/agents-workflow/contributes/agents-workflow.json (宣告 token AGENTS_STANDARDS)
   └── source/agents-workflow/contributes/knowledge-db.json (宣告 spaces.docs)

[Step 3: 知識庫標準資產與 Contributes 宣告]
   └── source/knowledge-db/assets/KnowledgeAgentsStandards.md
   └── source/knowledge-db/assets/phase00_guild.md
   └── source/knowledge-db/assets/research_guild.md
   └── source/knowledge-db/assets/phase07_guild.md
   └── source/knowledge-db/contributes/agents-workflow.json

[Step 4: 測試與發布驗證]
   └── 單元/整合測試更新 (test_space.py, test_targets.py)
   └── 全生態系回歸驗證 (python yscb.py dev test --all)
```
