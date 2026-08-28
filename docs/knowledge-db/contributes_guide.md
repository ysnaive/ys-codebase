# `contributes.knowledge-db` 擴充點注入指南 (Contributes Guide)

> 本文件指導 YS-Codebase 生態中的 Donor 模組如何透過 `contributes.knowledge-db` 宣告並注入自訂空間 (Spaces) 與同義詞庫 (Thesaurus)。

---

## 1. 注入途徑與格式 (Injection Pathways)

### 途徑 A：獨立貢獻檔案 (`module://<donor>/contributes.knowledge-db.json`)【推薦】

在模組根目錄建立 `contributes.knowledge-db.json`：

```json
{
  "spaces": {
    "agents_workflow_docs": {
      "description": "agents-workflow 工作流規範與文檔空間",
      "include": [
        "module://agents-workflow/assets/standards",
        "module://agents-workflow/assets/workflows"
      ],
      "exclude": [
        "**/__pycache__/**"
      ],
      "file_patterns": ["*.md"]
    }
  },
  "thesaurus": [
    ["工作流", "workflow", "pipeline", "流水線"],
    ["狀態機", "state_machine", "FSM"]
  ]
}
```

### 途徑 B：模組清單 (`module://<donor>/manifest.json`)

在 `manifest.json` 的 `contributes` 物件下宣告：

```json
{
  "name": "donor-module",
  "version": "1.0.0.0",
  "contributes": {
    "knowledge-db": {
      "spaces": {
        "donor_space": {
          "description": "Donor 模組專屬空間",
          "include": ["module://donor-module/source"],
          "exclude": ["**/__pycache__/**"]
        }
      },
      "thesaurus": [
        ["同義詞A", "synonym_a"]
      ]
    }
  }
}
```

---

## 2. 空間欄位與規則 (Space Fields)

| 欄位 | 型別 | 必填 | 說明 |
| :--- | :---: | :---: | :--- |
| **`description`** | `string` | 否 | 空間用途說明 |
| **`include`** | `List[string]` | **是** | 包含來源目錄/檔案之語意 URI 清單 (如 `module://donor/docs`) |
| **`exclude`** | `List[string]` | 否 | 排除 Glob 模式清單 (如 `**/__pycache__/**`) |
| **`file_patterns`** | `List[string]` | 否 | 檔名/副檔名 Glob 模式。**未宣告或為空時預設全包含 (include all)** |

---

## 3. 優先權與覆蓋機制 (Priority & Overrides)

當同名空間在多個來源重複出現時，系統依以下階層進行覆蓋合併：
$$\text{Local Config} > \text{Project Config} > \text{Module Contributes}$$

專案開發者可隨時在 `config://knowledge-db/config.project.json` 中宣告同名空間以自訂 `include` 或 `exclude` 範圍。
