---
target: "Dev/Reference"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb://source/core/core/contributes.py"
  - "yscb://source/dev/dev/scaffold.py"
related_docs:
  - "../README.md"
  - "../../core/README.md"
  - "../../_project/STANDARDS.md"
last_updated: "2026-09-07"
---

# YSCB 模組貢獻擴充架構與 Schema 語法手冊 (Contributes Reference)

> **適用對象**：YS-Codebase 生態系第三方模組開發者、擴充套件作者。  
> **核心目標**：指導模組開發者如何向其他模組注入功能（如向 `core` 註冊 CLI 指令），以及如何為自己的模組定義標準擴充點（`_format.json`）。

---

## 1. 架構概覽與目錄拓撲 (Architecture Overview)

在 YS-Codebase (YSCB) 微內核架構中，所有模組均為**彼此獨立、零硬編碼依賴**的套件。模組之間若需協同（例如擴充 CLI 指令、掛載工作流模板、宣告語意 URI），均透過統一的 **`contributes` 依賴注入機制** 達成。

### 1.1 目錄結構與三大檔案角色

每個模組的源碼目錄中，皆擁有一個專屬的 `contributes/` 目錄（語意 URI 為 `module.source://<my-module>/contributes/`）：

```text
module.source://<my-module>/contributes/
├── _format.json        # [Ingress / 輸入契約] 定義「其他模組如何為我注入擴充」
├── _manifest.md        # [Egress / 輸出清冊] 紀錄「我為其他模組貢獻了哪些能力」
├── core.json           # [Egress / 實際注入] 我向 core 模組注入的擴充實體
└── <target>.json       # [Egress / 實際注入] 我向特定模組 <target> 注入的擴充實體
```

| 檔案名稱 | 角色方向 | 說明 |
| :--- | :---: | :--- |
| **`_format.json`** | **Ingress** (輸入契約) | 若你的模組允許其他模組對你擴充（例如你開發了一個任務排程模組，允許別人註冊定時 Job），你必須撰寫此檔定義擴充點 Schema。以 `_` 開頭命名，受命名空間保護。 |
| **`_manifest.md`** | **Egress** (輸出導覽) | 作為人類與 Agent 閱讀的說明手冊，陳述本模組對外貢獻了哪些功能、協議與指令。 |
| **`<target>.json`** | **Egress** (實際注入) | 實際貢獻給目標模組的宣告（例：若要向微內核註冊指令，則建立 `contributes/core.json`）。 |

> [!IMPORTANT]
> **嚴格單向邊界隔離 (Strict Boundary Isolation)**：  
> `contributes/<target>.json` 檔案內部**「僅能且必須」包含對 `<target>` 模組的注入**。嚴禁在 `core.json` 中宣告其他模組的擴充點，反之亦然。違者將被靜態檢查器與運行期引擎剛性阻斷！

---

## 2. 定義擴充點：`_format.json` 語法規範

如果你的模組提供了開放接口供其他模組注入，你需要在模組的 `contributes/_format.json` 中定義這些擴充點的 Schema。

### 2.1 頂層結構

```json
{
  "_types": {
    "<CustomTypeA>": { ... },
    "<CustomTypeB>": { ... }
  },
  "<contribute_point_1>": {
    "description": "該擴充點的中文語意說明",
    "format": { ... }
  },
  "<contribute_point_2>": {
    "description": "第二個擴充點說明",
    "format": [ ... ]
  }
}
```

- **`_types` (選填)**：共用自訂結構定義區，用於消除重複並支援遞迴結構（如樹狀子指令）。
- **`<contribute_point>`**：擴充點名稱（對應貢獻者 JSON 中的頂層鍵名）。
- **`description` (必填)**：簡明描述該擴充點的業務用途。
- **`format` (必填)**：該擴充點期望接收的資料結構（陣列、字典或物件）。

---

### 2.2 輕量型別 DSL 語法 (Type Signature DSL)

YSCB 採用直覺、簡潔的型別字串表示法，不需要手寫複雜臃腫的 JSON Schema：

| 語法標記 | 語意說明 | 範例 | 解釋 |
| :--- | :--- | :--- | :--- |
| **基礎型別** | `str`, `int`, `bool`, `float`, `any` | `"token": "str!"` | 必填字串欄位 |
| **必填修飾符** | 後綴 `!` | `"name": "str!"` | 該欄位為必填，缺失時校驗報錯 |
| **選填修飾符** | 後綴 `?` | `"desc": "str?"` | 該欄位為選填（未標記亦預設為選填） |
| **列舉限制** | `enum(val1, val2, ...)` | `"tier": "enum(safe, conditional, gated)"` | 值必須為指定清單中的一員 |
| **預設值補全** | `= <default_value>` | `"server_compatible": "bool? = false"` | 若貢獻者未提供，引擎自動注入預設值 |
| **清單容器** | `list[<type>]` 或 `[ <schema> ]` | `[ { "token": "str!" } ]` | 物件陣列清單 |
| **任意動態鍵** | 通配符 `"*"` | `"*": { "description": "str!" }` | 鍵名為任意名稱的字典映射 (Map) |
| **型別參照** | `$<TypeName>` | `"*": "$CommandNode"` | 引用 `_types` 中定義的結構（支援遞迴） |

> [!TIP]
> **別名容錯機制**：型別解析器原生支援常見同義詞容錯：`str` 與 `string`、`bool` 與 `boolean`、`int` 與 `integer` 皆通用。

---

### 2.3 典型範例：定義階層化指令樹 (`core/_format.json`)

以下為 YSCB 核心微內核用於校驗全系統 CLI 指令註冊的標準 `_format.json` 範本，展示了共用型別、選項群組、列舉值與遞迴樹狀結構的組合應用：

```json
{
  "_types": {
    "ArgDef": {
      "description": "str!",
      "required": "bool? = false"
    },
    "OptionDef": {
      "description": "str!",
      "alias": "list[str]?",
      "args": {
        "*": "$ArgDef"
      }
    },
    "CommandNode": {
      "description": "str!",
      "tier": "enum(safe, conditional, gated)? = conditional",
      "server_compatible": "bool? = false",
      "args": {
        "*": "$ArgDef"
      },
      "options": {
        "*": {
          "*": "$OptionDef"
        }
      },
      "usage": {
        "pros": "list[str]?",
        "cons": "list[str]?"
      },
      "cmd": {
        "*": "$CommandNode"
      }
    }
  },

  "uri_schemes": {
    "description": "註冊自訂語意 URI 協議（例 workflow.plans://, knowledge.storage://）",
    "format": [
      {
        "token": "str!",
        "type": "enum(config, const, module)!",
        "value": "str!",
        "description": "str?"
      }
    ]
  },

  "commands": {
    "description": "註冊 CLI 模組指令樹、權限分級與防呆情境",
    "format": {
      "module_alias": "list[str]?",
      "description": "str?",
      "cmd": {
        "*": "$CommandNode"
      }
    }
  },

  "events": {
    "description": "宣告模組派送之生命週期或自訂事件清冊",
    "format": [
      {
        "name": "str!",
        "description": "str!"
      }
    ]
  }
}
```

---

## 3. 貢獻功能：撰寫 `<target>.json`

當你的模組要向其他模組擴充時，只需在 `contributes/` 下新增 `<target>.json`。

### 3.1 範例：向 `core` 註冊 CLI 子指令 (`contributes/core.json`)

```json
{
  "commands": {
    "description": "My Custom Extension Module CLI",
    "cmd": {
      "hello": {
        "description": "Print greeting message",
        "tier": "safe",
        "server_compatible": true,
        "args": {
          "user": {
            "description": "Target username",
            "required": false
          }
        },
        "options": {
          "flags": {
            "uppercase": {
              "description": "Convert output to uppercase",
              "alias": ["u"]
            }
          }
        },
        "usage": {
          "pros": ["快速輸出打招呼文字與環境測試"],
          "cons": []
        }
      }
    }
  }
}
```

#### 關鍵欄位約束：
1. **`tier` 權限安全階層**（預設 `"conditional"`）：
   - `"safe"`：🟢 自主安全指令（唯讀、沙盒測試、健康檢查、無副作用）。
   - `"conditional"`：🟡 階段條件指令（需在特定工作流階段或前置作業完成後調用）。
   - `"gated"`：🔴 授權守門指令（高危、外部發布、破壞性清理，必須獲明確授權）。
2. **`server_compatible` 背景服務相容性**：
   - 宣告該指令是否能在 `server` 常駐進程環境下熱派發執行。預設為 `false`。
3. **`usage.pros` 與 `usage.cons`**：
   - 用於 JIT CLI 推薦引導與 Agent 防呆阻斷手冊。

---

## 4. 專案特化覆蓋 (`config://<target>/contribute.json`)

若下游特定專案需要覆蓋或特化目標模組的 contributes 行為，可以在專案根目錄建立：
```text
config://<target>/contribute.json
```

- **單一目標覆蓋**：該檔案內宣告的內容僅能作用於 `<target>` 模組。
- **Git 追蹤原則**：專案層級 `contribute.json` **強制受 Git 追蹤**（禁止 `contribute.local.json`，確保跨環境與 CI 構建一致性）。
- **聚合優先權**：專案層級組態會在微內核聚合時，以最高優先權 Deep Merge 覆蓋模組預設值。

---

## 5. 開發者工具鏈與剛性驗證 (Tooling & Diagnostics)

YSCB 提供了完整的合規檢測工具，幫助你在編寫或發布前確保 Schema 與貢獻 100% 正確。

### 5.1 擴充點速查 (`contributes list`)
檢視全系統或特定模組目前開放的擴充點契約：
```bash
python yscb.py contributes list
python yscb.py contributes list --module=core
```

### 5.2 貢獻正確性校驗 (`contributes check`)
檢查你的模組貢獻格式是否完全合規：
```bash
python yscb.py contributes check <my-module>
# 或指定語意 URI 檔案進行精確校驗：
python yscb.py contributes check module.source://<my-module>/contributes/core.json
```

### 5.3 常見錯誤反饋與修復指南

| 錯誤類型 | 診斷輸出範例 | 修復說明 |
| :--- | :--- | :--- |
| **未知欄位 / 拼寫錯誤** | `[Error] commands.cmd.test: unknown field 'pros'. Did you mean 'case_pros'?` | 透過 Levenshtein 距離提供近似拼寫建議，依提示修正鍵名。 |
| **列舉值非法** | `[Error] commands.cmd.test.tier got 'saf', expected one of ['safe', 'conditional', 'gated']` | 檢查 Enum 定義，修正為合法選項。 |
| **必填欄位缺失** | `[Error] commands.cmd.test is missing required field 'description'` | 補齊定義中標記 `!` 的必填鍵。 |
| **越權/錯置注入** | `[Error] In 'contributes/core.json': key 'export' is not accepted by target 'core'` | 確保只有 `_format.json` 中定義的擴充點才能被注入。 |

---

## 6. 第三方開發者 Checklist

在提交模組前，請依序核對：
- [ ] 若本模組開放他人注入，已在 `contributes/_format.json` 定義了包含 `description` 與 `format` 的標準 Schema。
- [ ] 若本模組對外注入其他模組，所有檔案均以 `<target>.json` 精確命名（如 `core.json`），且絕無跨目標鍵名。
- [ ] 已在 `contributes/_manifest.md` 簡要列出本模組對外貢獻的能力與用途。
- [ ] 執行 `python yscb.py dev check <my-module>` 驗證合規性通過。
