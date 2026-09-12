# 生態系 Contributes 擴充注入與 Schema 規範指南 (Contributes & Schema Guild)

本手冊定義 YSCB 模組間 Contributes 依賴注入機制、輕量 Schema DSL 語法、定義檔查找方法與 Ingress/Egress 契約規範。

---

## 1. 雙向邊界哲學 (Strict Egress, Tolerant Ingress)

YS-Codebase 採用微內核外掛架構，模組間的能力擴充與依賴注入透過 `contributes/` 宣告完成：

- **Host（擴充點提供方）**：
  在自身 `contributes/` 下宣告 Ingress 剛性契約（`_format.json`）與 Egress 導覽手冊（`_manifest.md`），對外定義自身開放哪些擴充點及對應格式。  
  *(註：本機儲存庫路徑為 `project://source/<host>/contributes/`；下游第三方開發者環境無源碼目錄，應透過 `module://<host>/contributes/` 語意 URI 查閱，詳見第 3 節。)*
- **Donor（擴充能力注入方）**：
  在自身 `contributes/<host>.json` 宣告欲注入 Host 的內容。  
  *(註：本機儲存庫路徑為 `project://source/<donor>/contributes/<host>.json`。)*
- **雙向邊界防禦原則**：
  - **靜態檢核期 (Strict Egress)**：在執行 `dev check` 與 `contributes check` 時實施剛性驗證，攔截未宣告擴充點、型別錯誤或越權欄位。
  - **運行聚合期 (Tolerant Ingress)**：在系統運行聚合時採容錯防禦，記錄格式告警但保留動態欄位，防止單一擴充格式瑕疵拖垮整個運行環境。

---

## 2. `_format.json` Schema DSL 語法規範

YSCB 內建純標準庫實現的輕量 Schema DSL (`core.validator.ContributesValidator`)，零第三方依賴（嚴禁引入 pydantic 或 jsonschema）。

### 2.1 型別標記語法 (Type Tokens)
| DSL 標記 | 語意說明 | 範例 |
| :--- | :--- | :--- |
| `<type>!` | **必填欄位**（不可為 None 且型別必須吻合） | `"name": "str!"`, `"id": "int!"` |
| `<type>?` | **選填欄位**（值可為 None 或鍵名可省略） | `"description": "str?"` |
| `<type>? = <default>` | **具預設值之選填欄位** | `"enabled": "bool? = true"`, `"tier": "int? = 0"` |
| `enum(val1, val2, ...)` | **受限列舉字串**（值必須在指定集合內） | `"level": "enum(low, medium, high)"` |
| `list[<type>]` / `array[<type>]` | **型別約束列表**（列表元素需符合指定型別） | `"aliases": "list[str]?"`, `"tags": "list[str]!"` |
| `"*"` | **萬用映射字典**（約束字典下所有動態鍵之子結構） | `"*": "$CustomDef"` |
| `$TypeName` | **結構指針**（參照 `_types` 定義的複合子結構） | `"config": "$ConfigSpec"` |

### 2.2 `_format.json` 頂層結構設計
`_format.json` 檔案由可選的 `_types` 字典與各大擴充點定義組成：

```json
{
  "_types": {
    "RuleDef": {
      "name": "str!",
      "description": "str?",
      "severity": "enum(PASS, WARN, FAIL)? = WARN",
      "checker": "str!"
    }
  },

  "<point_name_a>": {
    "description": "擴充點 A 的功能與業務用途說明",
    "format": [
      "$RuleDef"
    ]
  },

  "<point_name_b>": {
    "description": "擴充點 B 的功能與業務用途說明 (字典映射型態)",
    "format": {
      "*": {
        "enabled": "bool? = true",
        "handler": "str!"
      }
    }
  }
}
```

- **`_types`**：定義該 Host 內部可複用的複合資料結構。
- **頂層鍵名 (`<point_name>`)**：即為 Host 對外公開的擴充點名稱。
- **`description`**：對該擴充點用途之說明。
- **`format`**：定義注入資料的結構約束（可為列表 `[ ... ]`、字典 `{ ... }` 或指針 `"$TypeName"`）。

---

## 3. 如何查找其他模組的 Contributes 定義

當模組作為 Donor 欲向其他模組貢獻能力時，**嚴禁盲猜欄位結構**。下游第三方開發端不會有目標模組的源碼（`source`）目錄，必須依循標準 `module://` 語意 URI 或 CLI 探索方法查找目標 Host 的定義：

### 3.1 步驟一：透過 CLI 檢視全生態系註冊清冊
```bash
# 檢視全系統當前所有模組公開之擴充點清單、提供者與簡要說明
python yscb.py contributes list
```

### 3.2 步驟二：查閱目標模組的人性導覽手冊 (`_manifest.md`)
每個宣告擴充點的模組均附帶 Egress 導覽手冊，供下游開發者查閱：
- **標準語意 URI**：`module://<target_module>/contributes/_manifest.md`
- **內容重點**：查閱該模組對外公開之擴充點業務背景、使用情境與官方標準範例。

### 3.3 步驟三：查閱目標模組的剛性 Schema 契約 (`_format.json`)
若需確認精確的欄位型別、是否必填、預設值或列舉值：
- **標準語意 URI**：`module://<target_module>/contributes/_format.json`
- **內容重點**：查閱 DSL 標記（如 `enum(...)`、`$TypeName`、`bool? = false`），確保注入宣告 100% 吻合契約。

### 3.4 步驟四：透過知識庫語意搜尋
```bash
# 精確搜尋擴充點相關契約與定義檔
python yscb.py knowledge-db search --ftype=json "_format"
python yscb.py knowledge-db search --ftype=md "_manifest"
```

---

## 4. Donor 注入檔案撰寫範式

當查明目標模組的擴充點規格後，Donor 在自身目錄建立宣告檔案：

### 4.1 檔名與路徑命名鐵律
- **檔名必須嚴格對齊目標 Host 模組名稱**：
  `contributes/<target_host>.json`（本機儲存庫路徑：`project://source/<donor>/contributes/<target_host>.json`）。
  例如：若欲注入給模組 `xyz`，檔名強制為 `contributes/xyz.json`。

### 4.2 注入內容結構範式
檔案頂層鍵名必須 100% 存在於目標 Host 的 `_format.json` 頂層擴充點清單中：

```json
{
  "<target_point_name>": [
    {
      "name": "my_feature",
      "severity": "FAIL",
      "checker": "module://my_mod/scripts/check.py"
    }
  ],
  "<target_point_map>": {
    "feature_key": {
      "enabled": true,
      "handler": "module://my_mod/scripts/handler.py"
    }
  }
}
```

> [!CAUTION]
> **嚴禁未宣告注入**：若在 `<target_host>.json` 宣告了未定義在該 Target Host `_format.json` 的頂層鍵名，靜態檢查將判定為越權注入並拋出錯誤。

### 4.3 實作與注入宣告對稱性鐵律 (Implementation-Declaration Symmetry)
- **程式碼與宣告 1:1 對稱**：Donor 在自身程式碼（如 `scripts/`）實作之功能若需透過 Host 派發或註冊，必須在 `contributes/<target_host>.json` 宣告完整對應的節點。
- **嚴禁單邊留存**：
  - 嚴禁「有實作未宣告」：導致 Host 無法感知該能力，使用者或 Agent 無法透過標準入口調用。
  - 嚴禁「有宣告無實作」：導致派發時拋出函式或模組缺失異常。
- **CLI 命令宣告對齊**：若向 `core.json` 注入 `commands`，必須完整宣告參數字典 (`args`)、正交選項 (`options`)、安全位階 (`tier`) 與使用說明 (`usage`)，詳見 [CLI 活躍合約與指令手冊](./cli_and_commands.md) 第 2 節之對稱性規範。

---

## [TOOL] 5. 合規檢查與智能診斷工具鏈

### 5.1 執行靜態合規驗證
```bash
# 檢查指定模組的 Contributes 注入與 Schema 合規性
python yscb.py contributes check <mod_name>

# 檢查全生態系所有模組的 Contributes 契約 (適合交付前全量驗證)
python yscb.py contributes check --all
```

### 5.2 智能拼寫診斷 (Did you mean)
驗證引擎內建 Levenshtein 距離演算法。當屬性鍵名或 enum 列舉值拼寫相近時，檢查器會主動提示正確合法名稱：
```
[contributes:error] Unknown property 'sever_severity' in point 'custom_checks'. Did you mean 'severity'?
```
出現此類診斷時，請對照目標 Host 的 `_format.json` 修正欄位拼寫後重新執行 `contributes check`。
