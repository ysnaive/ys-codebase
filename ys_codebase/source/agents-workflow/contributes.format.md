# Agents-Workflow 模組貢獻擴充格式說明書 (contributes.format.md)

> 本文件定義其他模組在 `source/<donor>/contributes/agents-workflow.json` 中向 `agents-workflow` 宣告工作流、模板、標準資產、Token 錨點、內容注入與發布 Target 之標準擴充格式。

---

## 1. 支援之擴充點清單 (Contribution Points)

模組可在 `source/<donor>/contributes/agents-workflow.json` 檔案中宣告以下四大核心擴充點：

| 擴充鍵名 (Key) | 說明 | 格式型別 |
| :--- | :--- | :--- |
| **`export`** | 宣告導出供發布與投影的資產檔案（標準、工作流、模板） | `array[object]` |
| **`token`** | 宣告模板與工作流中可供其他模組注入的自訂 Token 錨點 | `array[object]` |
| **`insert`** | 宣告向特定 Token 錨點注入內容（支援 URI、純文字與 Computed 動態函式） | `array[object]` |
| **`release_target`** | 宣告發布目標環境與投影目錄規則（例 `antigravity`） | `array[object]` |

同時，`agents-workflow` 向 `core` 貢獻之 URI 協議與指令清冊則置於 `source/agents-workflow/contributes/core.json`。

---

## 2. Schema 定義與宣告語法

### 2.1 資產導出宣告 (`export`)
宣告本模組所提供、需由發布引擎編譯物化至專案目錄的資產檔案。

- **欄位說明**：
  - `type` (`string`，必填)：資產分類，可為 `"standard"`（標準規範）、`"workflow"`（工作流）或 `"template"`（計畫模板）。
  - `source` (`string`，必填)：資產實體來源之語意 URI（例 `module://agents-workflow/assets/workflows/NewPlan.md`）。
  - `description` (`string`，選填)：資產用途摘要（將作為發布時 Header 巨集 `{export.description}` 之插值來源）。

```json
{
  "export": [
    {
      "type": "standard",
      "source": "module://agents-workflow/assets/standards/AgentsStandards.md",
      "description": "Agent 專案核心原則與防呆紀律規範"
    },
    {
      "type": "workflow",
      "source": "module://agents-workflow/assets/workflows/NewPlan.md",
      "description": "標準開發作業流程 (NewPlan) — 定義專案從需求到發布的完整規範與三大分流管控"
    },
    {
      "type": "template",
      "source": "module://agents-workflow/assets/templates/P00_semantic_requirements.md",
      "description": "Phase 0 語意需求模板"
    }
  ]
}
```

---

### 2.2 Token 錨點宣告 (`token`)
宣告文本中可供其他模組擴充掛載的語意錨點（文本內部以 `__@{TOKEN_NAME}__` 表示）。

- **欄位說明**：
  - `value` (`string`，必填)：Token 識別名稱（全域唯一，例 `PHASE01_HEADER`、`WORKFLOW_SOP_STANDARDS`）。
  - `description` (`string`，選填)：錨點用途與注入位置說明。

```json
{
  "token": [
    {
      "value": "WORKFLOW_SOP_STANDARDS",
      "description": "工作流通用 SOP 標準規範注入錨點"
    },
    {
      "value": "PHASE00_HEADER",
      "description": "Phase 0 模板標頭特化擴充注入錨點"
    }
  ]
}
```

---

### 2.3 內容注入宣告 (`insert`)
宣告向已註冊之 Token 錨點注入具體內容。

- **欄位說明**：
  - `token` (`string`，必填)：目標 Token 識別名稱。
  - `type` (`string`，選填，預設 `"const"`):
    - `"uri"`：讀取指定語意 URI 檔案之文字內容注入。
    - `"const"`：直接注入字串常數。
    - `"computed"`：動態呼叫 Python 函式（格式 `code.func://<module>/<subpath>:<fn>`）計算回傳值注入。
  - `value` (`string`，必填)：檔案 URI、常數字串或動態函式指針。
  - `mode` (`string`，選填，預設 `"replace"`):
    - `"replace"`：完全取代目標錨點標籤行。
    - `"below"`：保留錨點並於其下方插入。
    - `"above"`：保留錨點並於其上方插入。

```json
{
  "insert": [
    {
      "type": "uri",
      "token": "AGENTS_STANDARDS",
      "value": "module://agents-workflow/assets/standards/AgentsStandards.md",
      "mode": "replace"
    },
    {
      "type": "const",
      "token": "BEGIN_HTML_ANNOTATION",
      "value": "<!--",
      "mode": "replace"
    },
    {
      "type": "computed",
      "token": "DYNAMIC_CONTEXT_MAP",
      "value": "code.func://agents-workflow/providers:get_dynamic_context_map",
      "mode": "replace"
    },
    {
      "type": "const",
      "token": "RETRO_CHECK_ITEMS",
      "mode": "below",
      "value": "##### 知識庫 Search 效益評測 (knowledge-db: Search Efficiency & Ranking Quality)\n- **調用次數統計**：統計當前 Session 調用 `knowledge-db search` 總次數。\n- **調用時機合理性**：是否在未知符號/架構探索時及時調用？有無過度濫用或應調用而漏調用？\n- **效益性對比**：相較傳統 `grep_search` / `list_dir` / `view_file` 盲目翻找，估算節省之 Token、Turn 數與往返時間。\n- **演算法有效性**：檢索結果對解決問題之實質貢獻度，以及高相關內容是否排名靠前 (Top 1~3)。"
    },
    {
      "type": "const",
      "token": "RETRO_CHECK_ITEMS",
      "mode": "below",
      "value": "##### CLI 指令 Default-Deny 守門查核 (core: CLI Execution & Safety Guardrails)\n- **CLI 執行全量查核**：檢查 Session 中調用的每一個指令是否 100% 符合 `AgentsCliGuild.md` 推薦清單。\n- **Default-Deny 阻斷有效性**：是否有未授權執行未列指令或違反禁止情境之情事。"
    }
  ]
}
```

---

### 2.4 發布目標宣告 (`release_target`)
定義特定 IDE 或環境的發布投影規則。

- **欄位說明**：
  - `name` (`string`，必填)：發布 Target 識別碼（例 `antigravity`、`cursor`）。
  - `description` (`string`，選填)：Target 說明。
  - `projections` (`object`，必填)：針對不同資產 `type` 定義輸出路徑與格式：
    - `target_dir` (`string`)：目標輸出目錄之路徑（例 `.agents/workflows`）。
    - `extension` (`string`)：目標檔案副檔名（預設 `.md`）。
    - `header` (`list[string]`, 可選)：檔案開頭注入之 Frontmatter 標頭，支援 `{export.description}` 等元數據插值。

```json
{
  "release_target": [
    {
      "name": "antigravity",
      "description": "Google Antigravity IDE 原生 Slash Commands 與標準規範輸出",
      "projections": {
        "workflow": {
          "target_dir": "project://.agents/workflows",
          "extension": ".md",
          "header": [
            "---",
            "description: {export.description}",
            "---"
          ]
        },
        "template": {
          "target_dir": "project://.agents/.yscb/templates",
          "extension": ".md"
        },
        "standard": {
          "target_dir": "project://.agents/.yscb/standards",
          "extension": ".md"
        }
      }
    }
  ]
}
```

---

## 3. 模板佔位符三層語意體系規範 (Three-Tier Placeholder System)

編譯器在執行資產編譯與物化時，支援三大結構化語意佔位符：

| 佔位符語法 | 語意分類 | 解析階段 | 基準路徑 | 適用情境與範例 |
| :--- | :--- | :---: | :--- | :--- |
| **`` `__@{token}__` ``** | **文件內容佔位符**<br/>(Content Token) | Stage 1 | 內容狀態機 | 常數注入、模板片段嵌入、`code.func://` 動態計算產出。<br/>例：`` `__@{AGENTS_CLI_GUILD}__` `` ➔ 展開為 Markdown 表格正文。 |
| **`` `__#{uri}__` ``** | **文件自身相對路徑佔位符**<br/>(Local Relative URI) | Stage 2 | 當前 Markdown 文件所在目錄 (`cur_doc_dir`) | Markdown 內部超連結導航、相對文件引用。<br/>例：`[標準](`__#{module://.../DevStandards.md}__`)` ➔ `[標準](../.yscb/standards/DevStandards.md)` |
| **`` `__${uri}__` ``** | **專案根目錄相對路徑佔位符**<br/>(Project Relative URI) | Stage 2 | 專案根目錄 (`project://`) | 終端機 Shell 執行指令、相對於根目錄之設定檔參照。<br/>例：`` `python __${yscb.host://yscb.py}__ run` `` ➔ `` `python yscb.py run` ``（子目錄自適應為 `` `python tools/yscb.py run` ``） |

---

## 4. 專案特化注入 (`config://agents-workflow/contribute.json`)

當下游專案欲對工作流系統注入專案特化擴充（例如專案自訂 release_targets、專案特化 Token 注入）時，應建立於：
```text
config/agents-workflow/contribute.json
```
- **Git 追蹤原則**：`contribute.json` **強制受 Git 追蹤**（禁止 `contribute.local.json`，保障工作流編譯與產物之確定性）。
- **聚合優先權**：專案層級 `contribute.json` 於 `core.contributes.ContributesAggregator` 階層 ② 自動覆蓋 Donor 模組預設之 contributes 宣告。

