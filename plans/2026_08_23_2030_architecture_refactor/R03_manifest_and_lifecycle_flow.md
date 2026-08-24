# 技術調研報告：manifest 格式與 core 注入協議規範 (Manifest Format & Core Contributes Specification)

> 功能名稱：模組化體系宏觀架構重構與規範白皮書  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Draft  
> 擴充項目：none  
> 模板版本：v1.0  

---

## Ch.1 manifest 標準格式 (Manifest Specification)

`module://manifest.json` 是模組的身份、版本、相依性與能力宣告書。

> **SSOT 聲明**：`manifest.json` 以 `module.source://manifest.json` 為唯一真理來源 (SSOT)。打包流程將其複製至 `module.build://` 與 `module://`，各持一份快照副本。

### 1.1 抽象 Schema 定義

```json
{
  "name": "<module_name>",
  "version": "<semver_version>",
  "description": "<brief_description>",
  "dependencies": [
    "<dependent_module_name> [version_constraint]"
  ],
  "build_exclude": [
    "<exclude_glob_pattern>"
  ],
  "contributes": {
    "<target_module_name>": {
      "<contribution_key>": [
        /* 由目標模組規範之宣告式擴充資料清單 */
      ]
    }
  },
  "built_at": "<iso_timestamp>"
}
```

### 1.2 欄位定義說明

| 欄位名稱 | 型別 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| **`name`** | `string` | **是** | 模組唯一識別碼。 |
| **`version`** | `string` | **是** | 模組語意化版本號 (SemVer 2.0.0)。 |
| **`description`** | `string` | 否 | 模組功能之簡明描述。 |
| **`dependencies`** | `array[string]` | **是** | 該模組相依之其他模組名稱與版本約束條件清單（語法見 1.2.1）。 |
| **`build_exclude`** | `array[string]` | 否 | 模組打包 build 時應排除之 glob 規則清單。 |
| **`contributes`** | `object` | 否 | **抽象能力貢獻字典**：以目標模組名為 Key（`<target_module_name>`），宣告向該目標模組所貢獻的擴充能力與宣告式資料（`<contribution_key>: [...]`）。 |
| **`built_at`** | `string` | 自動 | 模組打包時由工具自動注入之 ISO 8601 時間戳記。 |

### 1.2.1 dependencies 版本約束語法規範

`dependencies` 陣列元素採用標準 **SemVer 2.0.0 相容約束語法**：

| 語法形態 | 範例 | 意義與相容區間 | 備註 |
| :--- | :--- | :--- | :--- |
| **精確版本** | `"linter ==1.0.0"` 或 `"linter 1.0.0"` | 僅接受完全一致之 `1.0.0` | 強度最高 |
| **相容大版本 (`^`)** | `"linter ^1.2.0"` | 允許 `>=1.2.0, <2.0.0` | **預設推薦**（不破壞性更新） |
| **相容次版本 (`~`)** | `"linter ~1.2.0"` | 允許 `>=1.2.0, <1.3.0` | 僅允許 Patch 修正 |
| **不等式區間** | `"linter >=1.0.0, <2.0.0"` | 自訂明確之版本上下限區間 | 靈活自訂 |
| **萬用字元 / 缺省** | `"linter *"` 或 `"linter"` | 匹配最新可用之任意版本 | 缺省約束時之預設解析 |

### 1.3 貢獻格式說明書規範 (module://contributes.format.md)
- **規範約束**：凡自身支援被其他模組擴充/注入能力的模組，**必須**於模組根目錄提供 `contributes.format.md`。
- **用途目的**：作為對外的能力擴充說明書，定義其他模組在 `manifest.json` 的 `contributes.<this_module>` 中可宣告的 `<contribution_key>` 與資料格式 Schema。

### 1.4 contributes 檢索來源矩陣 (Contributes Discovery Matrix)

系統在收集模組向目標模組（`{module}`）的貢獻注入時，依據以下 5 大來源進行聚合檢索：

| 層級維度 | 檔案路徑 | 類型 | 職責與注入用途 |
| :--- | :--- | :--- | :--- |
| **模組層<br/>(靜態代碼)** | **`module://manifest.json`** | 不變 | **常數型注入**：定義具有絕對性質、與代碼綁定的靜態注入內容。 |
| | **`module://contributes.{module}.json`** | 可選 | **明確指向定義**：按目標模組物理拆分的靜態檔案（例：`contributes.core.json`），提供給不想在 manifest 塞入過多內容或想明確分類的開發者。 |
| **專案層<br/>(Git 追蹤)** | **`config://config.project.json`** | 增量 | **專案層級注入**：定義專案層級注入（例：`agents-workflow` 定義的各路徑擴充）。 |
| | **`config://contributes.{module}.json`** | 可選 | **專案指向注入**：`module://contributes.{module}.json` 的專案 config 版。 |
| **本地層<br/>(Git 忽略)** | **`config://config.local.json`** | 增量 | **本地層級注入**：定義本地層級注入（例：`agents-workflow` 定義的 IDE 使用類型；考慮到 Git 忽略一致性，無明確指向變種）。 |

---

## Ch.2 core 注入協議規範 (Core Contributes Specification)

凡向 `core` 基礎模組宣告擴充之項目，皆於 `contributes.core` 命名空間下宣告。

### 2.1 路徑佔位符注入 (path_placeholders)

#### 2.1.1 注入格式 Schema
```json
{
  "token": "token_name",
  "handler": "scripts/resolvers.py:resolve_function",
  "description": "佔位符之語意用途說明"
}
```

#### 2.1.2 欄位定義說明
| 欄位名稱 | 型別 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| **`token`** | `string` | **是** | 佔位符標識名稱（於 URI 模板中以 `{token}` 形式使用）。 |
| **`handler`** | `string` | 條件 | **按需解算提供者進入點**（格式：`相對路徑:函式名`）。自訂佔位符必須提供；`core` 原生 Token（如 `module`）可留空。 |
| **`description`** | `string` | 否 | 佔位符之功能與語意說明。 |

#### 2.1.3 ExecutionContext 介面定義
```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass(frozen=True)
class ExecutionContext:
    """執行期語意上下文介面 (Execution Context Interface)"""
    module_name: str                              # 當前目標模組名稱（供 {module} 等佔位符解算）
    command: Optional[str] = None                 # 當前執行的子指令名稱（例如 "install", "check" 等）
    args: List[str] = field(default_factory=list) # 透傳之命令列參數清單
```

| 欄位名稱 | 型別 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| **`module_name`** | `str` | **是** | 當前目標模組名稱（供 `{module}` 等佔位符解算）。 |
| **`command`** | `str` (可選) | 否 | 當前執行的子指令名稱。 |
| **`args`** | `list[str]` | 否 | 透傳之命令列參數清單。 |

#### 2.1.4 解算機制 (Resolution Mechanics)
1. **核心標準 Token**（例：`token: "module"`）：由 `core` 原生直接映射自 `ExecutionContext.module_name`。
   - > **注意**：雖然 `{module}` 由 `core` 內建原生解算，但 `core` 本身**仍必須於自身的宣告中提供對應的自注入定義與 description**（以落實 100% 自解釋與拓撲自舉）。
2. **模組自訂擴充 Token**：由 `handler` 指定之函式進行按需計算（On-Demand Provider / Strategy Pattern）：
   ```python
   def resolve_function(context: ExecutionContext) -> Optional[str]:
       """
       動態解算自訂路徑佔位符
       :param context: 當前宿主傳入之執行期上下文
       :return: 展開後字串，若無法處理則回傳 None
       """
       ...
   ```

### 2.2 URI 協議注入 (uri_schemes)

#### 2.2.1 注入格式 Schema
```json
{
  "token": "token_name",
  "type": "const | config",
  "value": "<depends on type>",
  "description": "協議語意用途說明"
}
```

#### 2.2.2 欄位定義說明
| 欄位名稱 | 型別 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| **`token`** | `string` | **是** | 協議名稱標識（呼叫時以 `token://` 形式使用，例：`"cache"`, `"plans"`）。 |
| **`type`** | `enum` | **是** | 目標類型：<br/>• `"const"`：常數型路徑目標（支援 `{name}` 佔位符）。<br/>• `"config"`：專案組態驅動型路徑目標（**僅讀取 `config.project.json`**）。 |
| **`value`** | `string` | **是** | 依 `type` 決定之目標值：<br/>• 若 `type="const"`：填寫實體/語意路徑模板（例：`"yscb://.cache/{module}/"`）。<br/>• 若 `type="config"`：填寫對應之專案組態鍵名（例：`"paths.plans_dir"`）。 |
| **`description`** | `string` | 否 | 該協議之功能與語意用途說明。 |

#### 2.2.3 路徑版本控管防呆約束 (Path Determinism Guardrail)
> **路徑版控一致性鐵律**：
> `type: "config"` 類型的協議**僅允許讀取受 Git 版控之 `config://config.project.json`**。
> **嚴禁**從不會被 Git 追蹤的 `config.local.json` 讀取路徑配置，以確保團隊協作與跨環境下語意路徑解析的 100% 一致性與可重現性。

#### 2.2.4 典型宣告範例
- **常數型（`const`）**：
  ```json
  {
    "token": "cache",
    "type": "const",
    "value": "yscb://.cache/{module}/",
    "description": "模組快取目錄"
  },
  {
    "token": "mirror",
    "type": "const",
    "value": "yscb://.mirror/",
    "description": "本地端遠端倉庫鏡像目錄（內部採 <module>/<version>/ 拓撲）"
  },
  {
    "token": "temp",
    "type": "const",
    "value": "yscb://.temp/",
    "description": "系統暫存目錄（可隨時清空）"
  },
  {
    "token": "snapshot",
    "type": "const",
    "value": "yscb://.snapshots/",
    "description": "系統組態歷史快照目錄（用於 rollback 災難恢復）"
  },
  {
    "token": "module",
    "type": "const",
    "value": "yscb://modules/{module}/",
    "description": "模組本地運行端空間"
  },
  {
    "token": "module.root",
    "type": "const",
    "value": "yscb://modules/",
    "description": "模組存放層級根目錄"
  },
  {
    "token": "config",
    "type": "const",
    "value": "yscb://.config/{module}/",
    "description": "模組專屬設定檔目錄"
  },
  {
    "token": "config.root",
    "type": "const",
    "value": "yscb://.config/",
    "description": "模組設定檔存放層級根目錄"
  },
  {
    "token": "cache.root",
    "type": "const",
    "value": "yscb://.cache/",
    "description": "模組快取存放層級根目錄"
  },
  {
    "token": "module.source",
    "type": "const",
    "value": "yscb://source/{module}/",
    "description": "模組原始碼開發空間"
  },
  {
    "token": "module.source.root",
    "type": "const",
    "value": "yscb://source/",
    "description": "模組原始碼存放層級根目錄"
  },
  {
    "token": "module.build",
    "type": "const",
    "value": "yscb://build/{module}/",
    "description": "純淨安裝產物空間（輸出為版本化目錄 module.build://{version}/）"
  },
  {
    "token": "module.build.root",
    "type": "const",
    "value": "yscb://build/",
    "description": "純淨安裝產物存放層級根目錄"
  }
  ```
- **專案組態型（`config`）**：
  ```json
  {
    "token": "plans",
    "type": "config",
    "value": "paths.plans_dir",
    "description": "活躍開發計畫目錄"
  }
  ```

---

### 2.3 生命週期事件廣播注入 (events)

專門用於模組生命週期各關鍵里程碑的廣播事件監聽（Observer / Pub-Sub 模式）。

#### 2.3.1 注入格式 Schema
```json
{
  "event": "event_name",
  "handler": "scripts/lifecycle.py:handler_function",
  "priority": 100,
  "description": "事件處理用途說明"
}
```

#### 2.3.2 欄位定義說明
| 欄位名稱 | 型別 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| **`event`** | `string` | **是** | 目標事件名稱（由 `core` 定義之生命週期事件標識，例：`post_install`, `on_reload`）。 |
| **`handler`** | `string` | **是** | **事件回呼函式進入點**（格式：`相對路徑:函式名`）。 |
| **`priority`** | `integer` | 否 | 執行優先級權重（預設 `100`，數值越小越先執行）。 |
| **`description`** | `string` | 否 | 該事件監聽器之處理行為與用途說明。 |

#### 2.3.3 調度與自舉防呆注意事項
1. **廣播全量執行**：當 `core` 觸發指定事件時，所有登記該事件的模組依 **「相依拓撲排序 ➔ Priority 權重」** 依序全部調度執行。
2. **初始化自舉防呆 (Bootstrap Guardrail)**：在 `yscb.py init` 初始安裝 `core` 的自引用階段，必須確保最小基礎設施（路徑解算與檔案系統）就緒後方可發送事件，避免在未完全就緒前觸發未定義的 `events`。

