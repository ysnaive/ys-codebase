# Core 模組貢獻擴充格式說明書 (contributes.format.md)

> 本文件定義其他模組在 `source/<donor>/contributes/core.json` 中向 `core` 宣告擴充之標準格式。

---

## 1. 支援之擴充點清單 (Contribution Points)

| 擴充鍵名 (Key) | 說明 | 格式型別 |
| :--- | :--- | :--- |
| **`uri_schemes`** | 註冊自訂語意 URI 協議（例 `workflow.plans://`, `knowledge.storage://`） | `array[object]` |
| **`commands`** | 註冊 CLI 子指令、描述、使用情境 (Pros) 與防呆條款 (Cons) | `object[string, object]` |

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
      "case_pros": [
        "正在開發當前模組，需驗證單元邏輯或整體功能 (Phase 5/6)",
        "微調時優先附加 --no-build 或 -k <pattern> 快速跑測"
      ],
      "case_cons": [
        "🚨 嚴禁在跑測前手動執行 dev build",
        "🚨 嚴禁在日常開發中執行 dev test --all"
      ]
    }
  }
}
```
