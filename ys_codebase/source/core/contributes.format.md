# Core 模組貢獻擴充格式說明書 (contributes.format.md)

> 本文件定義其他模組在 `source/<donor>/contributes/core.json` 中向 `core` 宣告擴充之標準格式。

---

## 1. 支援之擴充點清單 (Contribution Points)

| 擴充鍵名 (Key) | 說明 | 格式型別 |
| :--- | :--- | :--- |
| **`uri_schemes`** | 註冊自訂語意 URI 協議（例 `workflow.plans://`, `knowledge.storage://`） | `array[object]` |
| **`commands`** | 註冊 CLI 子指令、描述、使用情境 (Pros) 與防呆條款 (Cons) | `object[string, object]` |
| **`events`** | 宣告該模組派送之生命週期或自訂事件清冊（中繼資料查表） | `array[object]` |

---

## 2. 宣告檔案路徑

模組必須將欲向 `core` 貢獻之內容建立於以下標準路徑：
```text
source/<module>/contributes/core.json
```

---

## 3. Schema 定義與宣告範例

### 3.1 語意 URI 協議 (`uri_schemes`)
```json
{
  "uri_schemes": [
    {
      "token": "workflow.plans",
      "type": "config",
      "value": "paths.plans",
      "description": "指向專案活躍開發計畫目錄"
    },
    {
      "token": "knowledge.storage",
      "type": "const",
      "value": "cache://knowledge-db/",
      "description": "知識庫模組專屬快取存儲目錄"
    }
  ]
}
```

### 3.2 CLI 子指令與防呆手冊 (`commands`)
```json
{
  "commands": {
    "test": {
      "description": "Run module tests inside an isolated sandbox",
      "tier": "safe",
      "phases": ["P05", "P06", "FT-2"],
      "case_pros": [
        "正在開發當前模組，需驗證單元邏輯或整體功能 (Phase 5/6)",
        "微調時優先附加 --no-build 或 -k <pattern> 快速跑測"
      ],
      "case_cons": [
        "🚨 嚴禁在跑測前手動執行 dev build",
        "🚨 嚴禁在日常開發中執行 dev test --all"
      ]
    },
    "release": {
      "description": "Formally package and release module",
      "tier": "gated",
      "phases": ["P07", "FT-3"],
      "case_pros": [
        "模組通過全部測試，正式打包發布 (Phase 7 結案前)"
      ],
      "case_cons": [
        "🚨 嚴禁在未獲開發者明確指示前擅自執行",
        "🚨 開發者 Prompt 未顯式要求發布時絕對禁止調用"
      ]
    }
  }
}
```

#### `commands` 屬性說明：
- `tier` (`string`，可選，預設 `"conditional"`):
  - `"safe"`: 🟢 自主安全指令（唯讀、沙盒跑測、靜態合規預檢、知識庫檢索），Agent 在對應情境下可自主調用。
  - `"conditional"`: 🟡 階段條件指令（需滿足特定 SOP 階段或除錯前置條件）。
  - `"gated"`: 🔴 🚨 授權守門指令（高危、發布、版本遞增或覆蓋安裝），必須在開發者 Prompt 顯式指示授權下方可調用。
- `phases` (`array[string]`，可選，預設 `[]`): 適用之 SOP 階段清單（例 `["P05", "P06", "FT-2"]`），供 JIT 指令引導動態過濾。

### 3.3 事件清冊宣告 (`events`)
```json
{
  "events": [
    { "pre_cli_dispatch": "在 CLI 執行各模組指令前觸發，提供自癒與生命週期檢查" },
    { "post_cli_dispatch": "在 CLI 執行結束後觸發，提供更新檢查提示" },
    { "on_reload": "當核心模組被重載後觸發" }
  ]
}
```

#### `events` 說明：
- 型別：`list[dict[str, str]]`（格式為 `[{"<name>": "description"}]`）。
- **非執行期依賴**：程式層無任何執行期阻斷或分發依賴，僅供 `python yscb.py event list` CLI 快速查表與手冊索引。建議任何會派送事件的模組皆提供該資訊。


---

## 4. 專案特化注入 (`config://<target>/contribute.json`)

當下游專案欲對目標模組注入特化擴充時，應建立於：
```text
config/<target>/contribute.json
```
- **Git 追蹤原則**：`contribute.json` **強制受 Git 追蹤**（禁止 `contribute.local.json`，保障環境與編譯一致性）。
- **聚合優先權**：專案層級 `contribute.json` 於 `core.contributes.ContributesAggregator` 階層 ② 自動覆蓋 Donor 模組預設之 contributes 宣告。

