# `contributes.knowledge-db` 擴充點規格說明書

> 本文件定義其他模組 (Donor Modules) 如何向 `knowledge-db` 宣告並注入自訂空間 (Spaces) 與同義詞庫 (Thesaurus)。

---

## 1. 注入途徑 (唯一標準路徑)

在模組目錄建立 `source/<donor>/contributes/knowledge-db.json`：

```json
{
  "spaces": {
    "<space_name>": {
      "description": "模組專屬知識庫空間說明",
      "include": [
        "module://<donor>/docs"
      ],
      "exclude": [
        "**/__pycache__/**",
        "**/.git/**"
      ],
      "file_patterns": ["*.py", "*.md"]
    }
  },
  "thesaurus": [
    ["詞組A", "synonym_a", "alias_a"],
    ["狀態機", "state_machine", "FSM"]
  ]
}
```

---

## 2. 欄位定義與行為約束

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :---: | :---: | :---: | :--- |
| **`description`** | `string` | 否 | `""` | 空間之語意用途說明 |
| **`include`** | `List[string]` | **是** | - | 來源目錄或檔案之語意 URI 清單 (如 `module://mod/docs`) |
| **`exclude`** | `List[string]` | 否 | `[]` | 排除路徑之 Glob 模式清單 (如 `**/__pycache__/**`) |
| **`file_patterns`** | `List[string]` | 否 | `null` | 副檔名/檔名過濾 Glob (如 `["*.py", "*.md"]`)。**省略或為空時預設全包含 (include all)** |

---

## 3. 全空間聯集處理公理 (Union Scope Axiom)

- `knowledge-db` **無單一 `default_space` 強制約定**。
- 所有合法注入之空間均會被系統接收，全域檢索與掃描天然以所有空間之聯集作為處理範圍。
- 專案組態檔 (`config.project.json` / `config.local.json`) 可宣告同名空間以覆蓋 Donor 模組之預設設定。
