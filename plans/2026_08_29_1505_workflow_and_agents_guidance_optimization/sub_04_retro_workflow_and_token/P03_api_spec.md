# API 與介面規格書 (API & Interface Specification)

> 功能名稱：開發歷程自檢工作流與擴充 Token (Retro Workflow & Contributed Token)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `Retro.md` (Workflow Asset) | `assets/workflows/Retro.md` | Public | 提供 `/Retro` Slash Command 工作流引導，包含溯源分析、三維自檢、優化建議與成果卡 |
| `RETRO_CHECK_ITEMS` (Token) | `contributes/agents-workflow.json` | Public | 擴充 Token 錨點，供下游模組宣告注入特定自檢項目清冊 |
| `WORKFLOW_RETRO` (Token) | `contributes/agents-workflow.json` | Public | 擴充 Token 錨點，供專案/模組於 `Retro.md` 尾部注入特化規則 |
| `contributes.export` | `contributes/agents-workflow.json` | Public | 宣告導出 `Retro.md` 作為通用工作流資產 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 Token 宣告契約 (`contributes/agents-workflow.json`)

```json
{
  "export": [
    {
      "type": "workflow",
      "source": "module://agents-workflow/assets/workflows/Retro.md",
      "description": "開發歷程自檢工作流 (Retro) — 支援對話歷程回顧、合規性與 Search 效益稽核及模組注入自檢項"
    }
  ],
  "token": [
    {
      "value": "RETRO_CHECK_ITEMS",
      "description": "模組自評與自檢項目清單（由下游模組如 knowledge-db, core 等宣告注入至 /Retro 工作流）"
    },
    {
      "value": "WORKFLOW_RETRO",
      "description": "Retro 工作流特化擴充注入錨點（位於 Retro.md 尾部）"
    }
  ]
}
```

### 2.2 模組注入規範格式 (`contributes/agents-workflow.json` / `contributes.format.md`)

```json
{
  "insert": [
    {
      "type": "const",
      "token": "RETRO_CHECK_ITEMS",
      "mode": "below",
      "value": "#### 2.2 知識庫檢索效益評測 (knowledge-db: Search Efficiency & Ranking Quality)\n- **調用次數統計**：統計當前 Session 調用 `knowledge-db search` 總次數。\n- **調用時機合理性**：是否在探索未知符號/架構時及時調用？有無過度濫用或漏調用？\n- **效益性對比**：相較傳統 `grep_search` / `list_dir` / `view_file` 盲目翻找，估算節省之 Token、Turn 數與往返時間。\n- **演算法有效性**：檢索結果對解決問題之實質貢獻度，以及高相關內容是否排名靠前 (Top 1~3)。"
    },
    {
      "type": "const",
      "token": "RETRO_CHECK_ITEMS",
      "mode": "below",
      "value": "#### 2.3 CLI 指令 Default-Deny 守門查核 (core: CLI Execution & Safety Guardrails)\n- **CLI 執行全量查核**：檢查 Session 中調用的每一個指令是否 100% 符合 `AgentsCliGuild.md` 推薦清單。\n- **Default-Deny 阻斷有效性**：是否有未授權執行未列指令或違反禁止情境之情事。"
    }
  ]
}
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 新建 Workflow 資產]
  └─ source/agents-workflow/assets/workflows/Retro.md
       │
       v
[Step 2: 註冊 Contributes 導出與 Token 錨點]
  └─ source/agents-workflow/contributes/agents-workflow.json
       │
       v
[Step 3: 規範手冊與標準文檔同步]
  ├─ source/agents-workflow/contributes.format.md
  └─ source/agents-workflow/assets/standards/DevelopmentStandards.md
       │
       v
[Step 4: 單元與編譯測試撰寫]
  └─ source/agents-workflow/tests/test_compiler.py (新增 test_retro_workflow_export_and_token)
```
