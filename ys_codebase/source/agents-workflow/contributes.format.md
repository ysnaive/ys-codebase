# Agents-Workflow 模組貢獻擴充格式說明書 (contributes.format.md)

> 本文件定義其他模組在 `manifest.json` 中向 `agents-workflow` 宣告工作流、模板、標準資產、Token 錨點、內容注入與發布 Target 之標準擴充格式。

---

## 1. 支援之擴充點清單 (Contribution Points)

模組可在 `manifest.json` 的 `contributes["agents-workflow"]` 物件下宣告以下四大核心擴充點：

| 擴充鍵名 (Key) | 說明 | 格式型別 |
| :--- | :--- | :--- |
| **`export`** | 宣告導出供發布與投影的資產檔案（標準、工作流、模板） | `array[object]` |
| **`token`** | 宣告模板與工作流中可供其他模組注入的自訂 Token 錨點 | `array[object]` |
| **`insert`** | 宣告向特定 Token 錨點注入內容（支援 URI、純文字與 Computed 動態函式） | `array[object]` |
| **`release_target`** | 宣告發布目標環境與投影目錄規則（例 `antigravity`） | `array[object]` |

同時，`agents-workflow` 亦向 `core` 模組貢獻三大工作流專屬 URI 協議：

| 所屬貢獻 | 協議 Token | 類型 | 說明 |
| :--- | :--- | :---: | :--- |
| `contributes["core"]["uri_schemes"]` | **`workflow.plans`** | `config` | 指向活躍開發計畫目錄（綁定 `paths.plans`） |
| `contributes["core"]["uri_schemes"]` | **`workflow.archived`** | `config` | 指向歷史封存計畫目錄（綁定 `paths.archived`） |
| `contributes["core"]["uri_schemes"]` | **`workflow.docs`** | `config` | 指向專案知識庫文檔目錄（綁定 `paths.docs`） |

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
  "contributes": {
    "agents-workflow": {
      "release_target": [
        {
          "name": "antigravity",
          "description": "Google Antigravity IDE 原生 Slash Commands 與標準規範輸出",
          "projections": {
            "workflow": {
              "target_dir": ".agents/workflows",
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
  }
}
```

---

### 2.5 核心 CLI 指令與防呆情境宣告 (`contributes.core.commands`)
宣告本模組所提供之子指令、說明以及防呆情境（用於產生宿主 CLI Help 與 `AGENTS_CLI_GUILD` 動態手冊）。

- **欄位說明**：
  - `<command_name>` (`object`，必填)：子指令名稱。
    - `description` (`string`，必填)：指令功能簡述。
    - `case_pros` (`list[string]`, 選填)：推薦 / 適用情境列表（若 pros 與 cons 皆無或為空，自動排除於 Agent 防呆手冊）。
    - `case_cons` (`list[string]`, 選填)：絕對禁止 / 不適用情境列表（以 `🚨` 明確警示）。

```json
{
  "contributes": {
    "core": {
      "commands": {
        "plan": {
          "description": "Dev Plans management toolchain (status, archive, search, verify)",
          "case_pros": [
            "檢視計畫狀態: agents-workflow plan status",
            "搜尋歷史計畫: agents-workflow plan search <query>",
            "驗證計畫完整度: agents-workflow plan verify",
            "依開發者明確指示封存計畫: agents-workflow plan archive <plan_dir>"
          ],
          "case_cons": [
            "🚨 嚴禁 Agent 主動或擅自執行 plan archive (除非開發者明確指示歸檔)"
          ]
        }
      }
    }
  }
}
```


