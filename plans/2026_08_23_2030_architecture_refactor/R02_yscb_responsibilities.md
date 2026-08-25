# 技術調研報告：yscb/core 職責總覽 (yscb/core Responsibilities Overview)

> 功能名稱：模組化體系宏觀架構重構與規範白皮書  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Draft  
> 擴充項目：none  
> 模板版本：v1.0  

---

## Ch.1 體系架構總覽 (Architecture Topology)

1. **宿主與核心雙層體系 (yscb.py vs. module:core)**
2. **yscb.py 職責定義 (Ultra-Thin Bootstrapper & CLI Router)**
3. **module:core 職責定義 (Core Infrastructure Module)**
4. **yscb.config.json 格式規範 (Installed Modules Ledger)**

---

## Ch.2 yscb.py 宿主職責定義

### 2.1 語意化定義 (Semantic Definition)
- **主要職責**：環境自舉 (Bootstrapper) 與泛用 CLI 轉接器 (Universal CLI Dispatcher)。
- **入口定位**：唯一單檔工具入口（超薄單檔，約百餘行）。
- **獨立性約束**：本身為自獨立體系，不依賴任何非原生組件（100% 純原生實現）。
- **軟引用邊界**：對 `module:core` 與其他模組皆為軟引用，僅負責根據規範傳遞與下發參數，不靜態相依模組代碼。
- **唯一相依檔案**：`yscb.config.json`，且必須放置於與 `yscb.py` 同層級之資料夾。
- **作用域邊界**：作用域僅限於自身，以及 `yscb.config.json` 中定義的核心路徑。

### 2.2 yscb.py 原生指令集 (Host Native Commands)
`yscb.py` 僅內建 2 項最核心之環境自舉與自體維護原生指令（100% Python 標準庫實現，不依賴任何模組）：
1. **`init`**：
   - **語法**：`init {yscbRoot} [--provider="<source>"]`
   - **參數**：`yscbRoot`（必選相對路徑）、`--provider`（可選自訂下載源）。
   - **執行邏輯**：建立 `yscb.config.json`，僅保證 `yscbRoot` 與 `core` 安裝所需之必要路徑存在，透過 Python 原生標準庫自官方預設位址（或 `--provider`）下載 `core` 純淨產物包至 `mirror://core/{version}/`，部署物化至 `yscb://modules/core/` 並寫入清冊完成自舉。
2. **`self-update`**：
   - **語法**：`self-update [--provider="<source>"]`
   - **執行邏輯**：透過 Python 原生標準庫自官方預設位址（或 `--provider`）檢索最新版 `yscb.py` 腳本，經語法校驗後原子覆蓋替換自身，達成宿主層級零相依自癒與升級。

### 2.3 yscb.py CLI 派發語法與規則
- **唯一呼叫語法**：`yscb.py {module name} {any}`
- **動態派發判定**：`yscb.py` 接收到非 `init` 且非 `self-update` 的任何指令時，皆自動視為 module cli 派發。
- **未初始化攔截**：若目標模組（或 `core`）不存在，輸出友善提示並引導執行 `init`。

---

## Ch.3 module:core 核心模組職責定義

### 3.1 核心 Installer 套件管理職責 (Core Installer Subcommands)
`core` 作為核心基礎模組，其 `scripts/cli.py` 承接 7 項純 Installer 指令集，所有模組實體存放路徑基礎定義為 `yscb://modules/`：
1. **`install`**：語法 `install <module_name>[@version] [--provider="<source>"]`。固定以 `<module_name>` 為第一參數，依相依拓撲自預設源或 `--provider` 抓取純淨產物至 `mirror://`，執行 Double-Check 模組名稱校驗後部署至 `yscb://modules/`。
2. **`update`**：拉取遠端最新版本，經相依求解後升級已安裝模組。
3. **`remove`**：語法 `remove <module> [--clean]`。檢查相依安全後，自清冊註銷並重構運行端；若帶有 `--clean` 則一併自 `mirror://` 實體刪除對應產物。
4. **`list`**：查詢並列出本地與遠端倉庫中所有可安裝之模組清單。
5. **`status`**：檢視目前已安裝模組之版本、安裝模式與實體健全度。
6. **`rollback`**：自本地備份快照中還原指定模組至升級前之版本狀態。
7. **`reload`**：**重載與重新建置** — 重新掃描並聚合所有已安裝模組之 `contributes` 注入宣告，重新建置/刷新本地運行端狀態。

### 3.2 uri 系統職責 (URI System Responsibilities)
`core.uri` 職責為 codebase 唯一路徑處理入口：

- **路徑佔位符 (PathPlaceholder)**：
  - 定義格式：`"{name}"`
  - 現定義佔位符：`{module}` = 當前模塊名稱。

- **通用協議清單**：
  - **`project://`**：來源為 `config://core/config.project.json` 之 `project_root`（未配置則拋錯，完全禁止 Fallback）。
  - **`yscb://`**：來源為 `yscb.config.json`（即 `init {yscbRoot}` 所配置之路徑），代表 ys-codebase root。
  - **`mirror://`**：常數 `const="yscb://.mirror/"`，本地端倉庫鏡像目錄（內部採 `<module>/<version>/` 版本化目錄拓撲）。
  - **`temp://`**：常數 `const="yscb://.temp/"`，系統暫存目錄（可隨時清空，不被 git 追蹤）。
  - **`snapshot://`**：常數 `const="yscb://.snapshots/"`，系統組態歷史快照目錄（用於 `rollback` 災難恢復）。
  - **`module://`**：常數 `const="yscb://modules/{module}/"`，本地模組運行端空間（對應根目錄協議 **`module.root://`** ➔ `yscb://modules/`）。
  - **`config://`**：常數 `const="yscb://config/{module}/"`，模組專屬設定檔目錄（對應根目錄協議 **`config.root://`** ➔ `yscb://config/`，非隱藏受 Git 追蹤資產）。
  - **`cache://`**：常數 `const="yscb://.cache/{module}/"`，模組快取目錄（對應根目錄協議 **`cache.root://`** ➔ `yscb://.cache/`）。
  - *(開發專用)* **`module.source://`**：常數 `const="yscb://source/{module}/"`，源碼開發空間（對應根目錄協議 **`module.source.root://`** ➔ `yscb://source/`）。
  - *(開發專用)* **`module.build://`**：常數 `const="yscb://build/{module}/"`，純淨產物空間（輸出為版本化目錄 `module.build://{version}/`；對應根目錄協議 **`module.build.root://`** ➔ `yscb://build/`）。

---

## Ch.4 yscb.config.json 格式規範

`yscb.config.json` 是整個體系的頂層全域檔案，定位為**核心路徑指引與模組安裝狀態紀錄清冊**。必須與 `yscb.py` 存放於同一層級之目錄。

### 4.1 Schema 結構範例

```json
{
  "yscb_root": "./ys_codebase",
  "installed_modules": {
    "core": {
      "version": "1.0.0",
      "installed_at": "2026-08-23T22:00:00",
      "provider": "builtin",
      "description": "YS-Codebase 核心套件管理與基礎 SDK"
    }
  }
}
```

### 4.2 欄位定義說明

| 頂層欄位 | 子欄位 | 型別 | 必填 | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| **`yscb_root`** | - | `string` | **是** | `yscb://` 實體根目錄（相對於 `yscb.py` 所在位置之相對路徑，由 `init {yscbRoot}` 寫入）。 |
| **`installed_modules`** | `{module_name}` | `object` | **是** | 已安裝模組之字典清冊（由 `core` 管理與維護）。 |
| | `version` | `string` | **是** | 該模組安裝時之語意化版本號 (SemVer)。 |
| | `installed_at` | `string` | **是** | 模組安裝/更新之 ISO 8601 時間戳。 |
| | `provider` | `string` | **是** | 模組安裝來源標識（例如 `"builtin"`、`"https://..."` 或本地路徑），供 `update` 自動定位來源。 |
| | `description` | `string` | 否 | 模組之功能簡介摘要。 |
