---
target: "Knowledge-DB/Contributes"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb://source/knowledge-db/knowledge_db/space.py"
  - "yscb://source/knowledge-db/knowledge_db/parsers/registry.py"
  - "yscb://source/knowledge-db/contributes/knowledge-db.json"
related_docs:
  - "./README.md"
  - "./parsers.md"
  - "./tokenizer.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-10-15"
---

# `contributes.knowledge-db` 擴充點注入指南 (Contributes Guide)

> 本文件指導 YS-Codebase 生態中的 Donor 模組與專案如何透過 `contributes.knowledge-db` 宣告並注入自訂空間 (`spaces`)、多語言解析器 (`languages`) 與三階同義詞庫 (`thesaurus` / `aliases` / `related`)。

---

## 1. 注入途徑與格式 (Injection Pathways)

### 途徑 A：獨立貢獻檔案 (`module://<donor>/contributes/knowledge-db.json`)【推薦】

在模組 `contributes/` 目錄下建立 `knowledge-db.json`（或於專案層級 `config://knowledge-db/contribute.json` 宣告）：

```json
{
  "spaces": {
    "agents_workflow_docs": {
      "description": "agents-workflow 規範與技能空間",
      "include": [
        "module://agents-workflow/assets/standards",
        "module://agents-workflow/assets/skills"
      ],
      "exclude": [
        "**/__pycache__/**"
      ],
      "file_patterns": ["*.md"]
    }
  },
  "languages": {
    "python": {
      "id": "python",
      "name": "Python",
      "extensions": [".py", ".pyi"],
      "mode": "tree_sitter",
      "grammar": "tree_sitter_python",
      "query_file": "assets/queries/python.scm"
    },
    "spice": {
      "id": "spice",
      "name": "SPICE",
      "extensions": [".sp", ".cir", ".cdl", ".netlist"],
      "mode": "custom",
      "parser_entry": "knowledge_db.parsers.spice_parser:SpiceParser"
    }
  },
  "thesaurus": [
    ["工作流", "workflow", "pipeline", "流水線"],
    ["狀態機", "state_machine", "FSM"]
  ],
  "aliases": {
    "ngspice": ["spice", "circuit"]
  },
  "related": [
    ["parser", "ast", "lexer", "visitor"]
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
      ],
      "aliases": {
        "別名來源": ["展開目標A", "展開目標B"]
      },
      "related": [
        ["關聯詞A", "關聯詞B", "關聯詞C"]
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
| **`include`** | `List[string]` | **是** | 包含來源目錄/檔案之語意 URI 清單 (如 `module://donor/docs` 或 `project://src`) |
| **`exclude`** | `List[string]` | 否 | 排除 Glob 模式清單 (如 `**/__pycache__/**`) |
| **`file_patterns`** | `List[string]` | 否 | 檔名/副檔名 Glob 模式。**未宣告或為空時預設全包含 (include all)** |

---

## 3. 多語言解析器擴充宣告 (`languages` Extension Point)

`knowledge-db` 落實**零特權外掛自貢獻架構 (Zero-Privilege Dogfooding)**：`ParserRegistry` / `LanguageRegistry` 內部不硬編碼任何特定語言，包含內建之 10 大語言（Python, C, C++, C#, JavaScript, TypeScript, Markdown, SPICE, HTML, CSS）與第三方擴充語言，全數透過 `contributes.knowledge-db.languages` 動態載入（對應 `LanguageConfig` Schema），並同步驅動背景 Watcher 的動態副檔名監聽集合 (`resolve_watch_extensions`)。

支援兩種解析驅動模式 (`mode`)：

### 3.1 模式一：`tree_sitter` 宣告式 S-Expression 模式（預設）
透過 `TreeSitterDriver` 載入對應之 Tree-sitter 語法包與 `.scm` 查詢檔，零 Python 程式碼即可完成符號定義 (`@symbol.name`, `@definition.*`)、調用點 (`@call.site`, `@call.name`) 與檔頭引用 (`@import.stmt`) 提取：

```json
"typescript": {
  "id": "typescript",
  "name": "TypeScript",
  "extensions": [".ts", ".tsx"],
  "mode": "tree_sitter",
  "grammar": "tree_sitter_typescript:language_typescript",
  "query_file": "assets/queries/typescript.scm"
}
```

### 3.2 模式二：`custom` 自訂解析器類別模式
針對領域特化語言（如 SPICE 電路網表）或自訂輕量解析器，指定繼承自 `BaseParser` 之類別入口點 (`<module_path>:<ClassName>`)：

```json
"spice": {
  "id": "spice",
  "name": "SPICE",
  "extensions": [".sp", ".cir", ".cdl", ".netlist"],
  "mode": "custom",
  "parser_entry": "knowledge_db.parsers.spice_parser:SpiceParser"
}
```

### 3.3 `LanguageConfig` 欄位規範表
| 欄位 | 型別 | 必填 | 說明 |
| :--- | :---: | :---: | :--- |
| **`id`** | `string` | **是** | 語言唯一識別碼（如 `"python"`, `"cpp"`, `"spice"`） |
| **`name`** | `string` | 否 | 人類可讀顯示名稱（預設同 `id`） |
| **`extensions`** | `List[string]` | **是** | 綁定之副檔名清單（含前導點號，如 `[".py", ".pyi"]`） |
| **`mode`** | `string` | 否 | 解析驅動模式：`"tree_sitter"`（預設）或 `"custom"` |
| **`grammar`** | `string` | 條件 | `tree_sitter` 模式下必填，指定 Python grammar 模組或入口函式（如 `"tree_sitter_python"`） |
| **`query_file`** | `string` | 條件 | `tree_sitter` 模式下必填，相對於 Donor 模組根目錄之 `.scm` 查詢檔路徑 |
| **`parser_entry`** | `string` | 條件 | `custom` 模式下必填，`BaseParser` 子類別之匯入路徑（`<module>:<Class>`） |
| **`custom_kinds`** | `List[Dict]` | 否 | 自訂符號類型映射表 |

---

## 4. 優先權與雙軌階層覆蓋機制 (Dual-Track Hierarchy & Overrides)

`SpaceManager._load_contributes()` 採用**「Core Donor Contributes（基底）+ 專案 `contribute.json`（覆蓋）」雙軌階層合併機制**：

$$\text{Project Contributes (config://knowledge-db/contribute.json)} \;\succ\; \text{Module Contributes (module://<donor>/contributes/knowledge-db.json)}$$

1. **基底聚合 (Base Layer)**：系統首先透過 `core.contributes.get("knowledge-db")` 聚合所有已安裝 Donor 模組貢獻之 `spaces`、`languages` 與 `thesaurus` / `aliases` / `related`。
2. **專案階層覆蓋 (Project Override Layer)**：接著讀取專案層級 `config://knowledge-db/contribute.json`。
   - **空間 (`spaces`)**：若宣告同名空間，專案設定將精確覆蓋該空間之 `include`、`exclude` 與 `file_patterns`；未覆蓋之其他 Donor 空間則 **100% 完整保留**。
   - **同義詞庫 (`thesaurus` / `aliases` / `related`)**：專案新增之詞群會與基底詞庫進行聯集擴充合併，確保專案特化領域術語與通用軟工詞庫無縫共存。
