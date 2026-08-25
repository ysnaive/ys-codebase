# 技術調研報告：模組運行週期與調用流規範 (Lifecycle & Invocation Flow Specification)

> 功能名稱：模組化體系宏觀架構重構與規範白皮書  
> 建立日期：2026-08-24  
> 所屬主計畫：無  
> 狀態：Draft  
> 擴充項目：none  
> 模板版本：v1.0  

---

## 說明
本調研報告正在透過「指令逐一推演 ➔ 原子行為萃取 ➔ 建立生命週期行為矩陣」之標準討論流程逐步建立中。

---

## 1. 原子行為清冊 (Atomic Behaviors Table)

| 行為編號 | 行為名稱 (Action ID) | 操作對象 (Target) | 行為描述 (Description) |
| :--- | :--- | :--- | :--- |
| **ACT-01** | `INIT` | 宿主環境 | 宿主環境一次性自舉：解析路徑、防呆檢查（`yscb_root != undefined`）、建立 `yscbRoot` 根目錄、寫入初始 `yscb.config.json`。 |
| **ACT-02** | `DOWNLOAD` | **`mirror://`** | 自遠端抓取指定模組的純淨 build 產物包/檔案至 `mirror://` 鏡像庫。 |
| **ACT-03** | `DELETE` | **`mirror://`** | 自 `mirror://` 鏡像庫中實體刪除指定模組之 build 產物。 |
| **ACT-04** | `REGISTER` | **`yscb.config.json`** | 於 `yscb.config.json` 的 `installed_modules` 清冊中登記或更新模組定義與版本元數據。 |
| **ACT-05** | `UNREGISTER` | **`yscb.config.json`** | 檢查反向相依安全後，自 `yscb.config.json` 的 `installed_modules` 清冊中移除指定模組。 |
| **ACT-06** | `SOLVE_DEPS` | **相依求解** | 給定目標模組與版本約束，讀取 manifest 求解版本相容性與相依拓撲樹，輸出合法之變更模組清單。 |
| **ACT-07** | `PREPARE` | **狀態同步** | 驗證安裝清單 ➔ 遍歷清冊中所有模組確認 `mirror://` 狀態 ➔ 按情況（缺失或版本不符）調用 `DOWNLOAD`。 |
| **ACT-08** | `RELOAD` | **`module.root://`** | 運行端調和重構：清空 `module.root://` ➔ 根據 `yscb.config.json` 將 `mirror/` 純淨模組載入 `module://` ➔ 自動分發/增量補齊模組組態至 `config://` ➔ 運行依賴注入與命名空間事件廣播。 |
| **ACT-09** | `FETCH<source>` | **來源傳輸協定** | 來源通道抓取器：依指定來源協定（`<git>`、`<https>`、`<local>` 等）自遠端或本地獲取模組產物包或 manifest 元數據。 |
| **ACT-10** | `SNAPSHOT` | **`snapshot://`** | 狀態快照備份：於執行破壞性變更前，將當前 `yscb.config.json` 與狀態點備份至 `snapshot://` 目錄。 |
| **ACT-11** | `RESTORE_SNAPSHOT` | **`snapshot://`** | 狀態快照還原：自 `snapshot://` 目錄讀取最近（或指定）之歷史狀態點，倒回覆蓋 `yscb.config.json`。 |
| **ACT-12** | `DISPATCH_CLI` | **模組進入點** | 動態指令派發：宿主探測目標模組之 `scripts/cli.py`，透傳參數委派執行（模組路徑與 I/O 統一由 `core` 控管）。 |

---

## 2. 指令生命週期映射 (Command Lifecycle Mappings)

### 2.1 `init {yscbRoot} [--provider="<source>"]`
```text
[輸入 init {yscbRoot} [--provider=...]] 
  ➔ ACT-01 (INIT: 防呆檢查、確保根目錄、寫入初始 yscb.config.json)
  ➔ 宿主原生 HTTP 自官方預設源（或 --provider）下載 core 純淨產物包
  ➔ 物化寫入 mirror://core/{version}/ 並部署至 yscb://modules/core/
  ➔ ACT-04 (REGISTER core: 寫入 provider、version、installed_at)
  ➔ ACT-08 (RELOAD: 執行依賴注入與事件廣播)
  ➔ 輸出初始化完成
```

### 2.2 `install <module_name>[@version] [--provider="<source>"]`
```text
[輸入 install <module_name> [--provider=...]] 
  ➔ ACT-10 (SNAPSHOT: 建立當前組態快照)
  ➔ ACT-06 (SOLVE_DEPS: 分析模組與相依樹) 
  ➔ ACT-04 (REGISTER: 登記目標模組與相依項) 
  ➔ ACT-07 (PREPARE: 經 FETCH 齊備鏡像產物並執行 Double-Check name 校驗) 
  ➔ ACT-08 (RELOAD: 重構運行端並依賴注入) 
  ➔ 輸出安裝完成
```

### 2.3 `update <module>`
```text
[輸入 update <module> 或 update --all] 
  ➔ ACT-10 (SNAPSHOT: 建立當前組態快照)
  ➔ ACT-06 (SOLVE_DEPS: 查詢最新版本並求解相依相容性) 
  ➔ ACT-04 (REGISTER: 更新版本元數據) 
  ➔ ACT-07 (PREPARE: 下載新版產物至鏡像) 
  ➔ ACT-08 (RELOAD: 重構運行端並依賴注入) 
  ➔ 輸出升級完成
```

### 2.4 `remove <module> [--clean]`
```text
[輸入 remove <module> [--clean]] 
  ➔ ACT-10 (SNAPSHOT: 建立當前組態快照)
  ➔ ACT-05 (UNREGISTER: 反向相依安全檢查並自清冊註銷) 
  ➔ (若帶有 --clean) ACT-03 (DELETE: 自 mirror:// 刪除該模組之產物)
  ➔ ACT-08 (RELOAD: 重構運行端並依賴注入) 
  ➔ 輸出移除完成
```

### 2.5 `reload`
```text
[輸入 reload] 
  ➔ ACT-07 (PREPARE) 
  ➔ ACT-08 (RELOAD) 
  ➔ 輸出刷新完成
```

### 2.6 `list`
```text
[輸入 list] 
  ➔ 讀取 yscb.config.json (本地已登記安裝清冊) 
  ➔ (可選) ACT-09 (FETCH<remote_https|remote_git>: 檢索遠端倉庫可用清冊與版本) 
  ➔ 格式化輸出清單對照表
```

### 2.7 `status`
```text
[輸入 status] 
  ➔ 讀取 yscb.config.json (期望狀態) 
  ➔ 遍歷校驗 modules/ 與 mirror/ 實體完整性與版本一致性 
  ➔ 檢測相依完整度與注入健康狀態 
  ➔ 格式化輸出系統診斷報告
```

### 2.8 `rollback`
```text
[輸入 rollback [module | --last]] 
  ➔ ACT-11 (RESTORE_SNAPSHOT: 還原組態清冊至歷史快照點) 
  ➔ ACT-08 (RELOAD: 重構運行端並依賴注入) 
  ➔ 輸出回滾完成報告
```

### 2.9 `yscb.py {module} {any}` (泛用 CLI 動態派發)
```text
[輸入 yscb.py {module} {any}] 
  ➔ ACT-12 (DISPATCH_CLI: 探測模組進入點並透傳參數委派執行) 
  ➔ 透傳模組執行 Exit Code
```

---

## 3. 宿主原生指令生命週期映射 (Host Native Command Lifecycles)

### 3.1 `self-update [--provider="<source>"]` (宿主原生指令)
```text
[輸入 self-update [--provider=...]] 
  ➔ 宿主原生 HTTP 自官方預設源（或 --provider）查詢最新版 yscb.py 與雜湊值
  ➔ 版本比對（若已為最新版則直接退出）
  ➔ 下載至 temp:// 暫存檔並執行 Python 語法校驗
  ➔ 備份當前 yscb.py 並原子覆蓋替換
  ➔ 輸出宿主升級完成報告
```

---

## 附錄：各指令生命週期推演詳細紀要 (Appendix: Detailed Lifecycle Discussion Notes)

> 本附錄完整保留各指令在架構調研期間的微觀推演細節、決策脈絡與防呆設計，作為未來實作時的白皮書與抽象實作參考。

### 附錄 1：`init {yscbRoot}` 微觀生命週期推演紀錄

1. **第 1 步：解析輸入路徑 (Resolve Input Path)**
   - 提取使用者輸入的 `{yscbRoot}`，計算相對於 `yscb.py` 所在目錄的實體目標路徑。
2. **第 2 步：防呆檢查 (Assertion Check)**
   - 判定標準：檢查 `yscb.config.json` 中的 `yscb_root` 是否已被定義且非空（`yscb_root != undefined`）。
   - 若已定義有效值，立即阻斷並提示已初始化，防止意外覆蓋現有環境。
3. **第 3 步：確保根目錄存在 (Ensure Root Directory)**
   - 僅確保 `yscbRoot` 實體目錄與載入 `core` 的最小必要路徑存在。其餘目錄結構由後續路徑管理模組自適應處理。
4. **第 4 步：寫入宿主初始組態 (Write Host Config)**
   - 建立並寫入 `yscb.config.json`（寫入 `yscb_root` 實體基準，初始化 `installed_modules: {}`）。
5. **第 5 步：自舉下載與部署 `core` 模組 (Bootstrap Core)**
   - 宿主以極簡原生 HTTP 下載方式自預設官方遠端倉庫（或 `--provider` 指定源）獲取 `core` 純淨產物包，物化寫入 `mirror://core/{version}/` 並部署至 `yscb://modules/core/`。
6. **第 6 步：登記 `core` 清冊 (Register Module)**
   - 於 `yscb.config.json` 的 `installed_modules` 登記 `core` 的版本與安裝時間戳。
7. **第 7 步：`yscb://` 參數解算約束 (Host-Core Internal Path Binding)**
   - **防呆鐵律**：`core` 內部微內核引擎僅在宿主 `yscb.py` 啟動載入時接收內部私有配置以錨定 `yscb://` 實體路徑，嚴禁在 `core` 內部進行隱式向上目錄探測或猜測使用環境，且對外暴露的 `ExecutionContext` 絕不包含底層實體路徑。

### 附錄 2：套件管理四大基礎原子操作與對象劃分 (Atomic Primitives)

1. **`DOWNLOAD` / `DELETE`（對象：`mirror://`）**
   - 僅負責本地鏡像庫 `mirror://` 的實體維護。
   - `DOWNLOAD`：內部調用 `FETCH<source>` 自指定來源下載模組之 build 純淨產物至 `mirror://`。
   - `DELETE`：自 `mirror://` 實體刪除模組純淨產物。
2. **`REGISTER` / `UNREGISTER`（對象：`yscb.config.json`）**
   - 僅負責期望組態清冊之維護。
   - `REGISTER`：於 `installed_modules` 寫入/更新模組版本與元數據。
   - `UNREGISTER`：反向相依安全檢查後，自 `installed_modules` 註銷模組。

### 附錄 3：調和與重構原子操作 (PREPARE & RELOAD)

1. **`PREPARE`（狀態同步原子操作）**
   - **第 1 步：驗證安裝清單**：讀取 `yscb.config.json` 的 `installed_modules`。
   - **第 2 步：遍歷檢查與按需下載**：對清冊中每個模組檢查 `mirror://` 狀態，若缺失或版本不符則調用 `DOWNLOAD`。
2. **`RELOAD`（運行端調和重構原子操作）**
   - **階段一：全量純淨物化 (Clean Pure Materialization)**：
     - 依據 `yscb.config.json` 模組清冊，自 `mirror://` 將所有登記模組之純淨 build 產物全量覆蓋/重新物化至 `modules/`。
     - 清理所有未在清冊中之幽靈模組或舊殘留檔案，確保 `modules/` 處於 100% 純淨初始狀態，杜絕上一輪運行殘留。
   - **階段二：依賴注入與事件廣播 (Dependency Injection & Events)**：
     - 於純淨環境之上，掃描聚合 5 大來源 contributes 宣告。
     - 按相依拓撲排序執行各項注入邏輯，並依序廣播生命週期事件（如 `on_reload`）。

### 附錄 4：`update` 與 `SOLVE_DEPS` 相依求解微觀推演紀錄

1. **`SOLVE_DEPS` 原子相依求解器**
   - **輸入**：目標模組名稱、版本約束、現有 `yscb.config.json` 清冊、遠端與本地 manifest 元數據。
   - **處理**：
     - 分析依賴拓撲，檢查目標版本是否滿足其他所有模組之版本約束。
     - 若升級或安裝引入新的相依項，自動將相依模組遞迴排入變更清單。
   - **輸出**：合法且無衝突之待登記模組與版本清單（若存在衝突則立即阻斷報錯）。
2. **`update` 指令執行管線**
   - 調用 `SOLVE_DEPS` 求解出目標模組最新版本與連帶升級清冊。
   - 調用 `REGISTER` 更新 `yscb.config.json` 中的版本定義。
   - 調用 `PREPARE` 觸發 `DOWNLOAD` 下載新版純淨產物至 `mirror://`。
   - 調用 `RELOAD` 清空並以新版本重構 `modules/` 運行端與執行注入。

### 附錄 5：`FETCH<source>`、Provider 抽象與 `module.build.root://` 結構規範

1. **Provider 核心抽象：`module.build.root://` 倉庫結構**
   - **核心理念**：任何 Provider（無論是官方倉庫、私有 Git 儲存庫還是本地 build 空間）本質上皆代表/提供一個 **`module.build.root://` 結構**。
   - **標準目錄拓撲**：
      ```text
      <provider_root> (即 module.build.root://)
        ├── <module_A>/
        │     ├── index.json        (模組清冊索引：通用元數據與可用版本號清單)
        │     ├── 1.0.0/            (完全獨立之純淨模組，含自身的 manifest.json)
        │     │     ├── manifest.json
        │     │     ├── scripts/
        │     │     └── ...
        │     └── 1.1.0/            (完全獨立之純淨模組，含自身的 manifest.json)
        │           ├── manifest.json
        │           ├── scripts/
        │           └── ...
        └── <module_B>/
              └── ...
      ```
   - **`index.json` 最小 Schema 定義**：
     ```json
     {
       "name": "<module_name>",
       "description": "<brief_description>",
       "versions": [
         "1.0.0",
         "1.1.0"
       ]
     }
     ```
     | 欄位名稱 | 型別 | 必填 | 說明 |
     | :--- | :--- | :--- | :--- |
     | **`name`** | `string` | **是** | 模組名稱標識（供 Double-Check 名稱校驗）。 |
     | **`description`** | `string` | 否 | 模組功能簡介摘要（供 `list` 遠端清冊檢視）。 |
     | **`versions`** | `array[string]` | **是** | 已發布之 SemVer 版本號清單（供 `SOLVE_DEPS` 進行版本求解與可用性檢查）。 |
2. **Provider 兩大原生能力**：
   - **可提供模組清單發現 (Discovery & Listing)**：`list --remote` 透過讀取 Provider 頂層/模組層的 `index.json` 或掃描目錄，即可獲取所有可用模組清冊與版本列表。
   - **狀態與版本自動檢測 (Version Resolution)**：
     - 當指定版本時（如 `linter@1.0.0`），自 `<provider_root>/linter/1.0.0/` 物化。
     - 當無指定版本時（如 `linter`），透過 `index.json`（或比對目錄版本號）解算出最高版本號（如 `1.1.0`），自 `<provider_root>/linter/1.1.0/` 物化。
3. **模組根物化契約 (The Module Root Invariant)**
   - 任何外部來源經 `FETCH<source>` 獲取並解壓後，物化寫入 `mirror://{module}/{version}/` 的目錄根**必須 100% 等同於 `module://`（即直接持有 `manifest.json`）**。
4. **`list` 指令執行管線**
   - 讀取 `yscb.config.json` 取得本地已登記安裝清冊。
   - （可選）若帶有 `--remote` 或需比對最新版本，調用 `FETCH<source>` 掃描 Provider 的 `module.build.root://` 獲取可用清冊。
   - 格式化並輸出模組清冊對照表格（名稱、安裝版本、最新版本、描述）。

### 附錄 6：`status` 環境自檢微觀推演紀錄

1. **`status` 核心定位**：非侵入式環境診斷與自檢工具。
2. **微觀檢查維度**：
   - **清冊與實體對齊**：比對 `yscb.config.json` 與 `yscb://modules/` 資料夾，確保無缺失模組或未登記之幽靈目錄。
   - **鏡像庫健全度**：檢查 `yscb://.mirror/` 中對應版本之純淨 build 產物是否齊備。
   - **相依性閉包檢驗**：驗證所有已安裝模組的 `dependencies` 是否 100% 存在且版本相容。
   - **注入衝突檢驗**：掃描 5 大來源 contributes，確保無重複 token 衝突或無效 handler 指標。

### 附錄 7：`rollback` 與快照災難恢復微觀推演紀錄

1. **快照機制原則 (Snapshot Principle)**
   - 拒絕單純的「版本降級別名」，定位為**系統狀態快照與災難恢復 (Disaster Recovery)** 機制。
   - 在執行任何可能破壞現狀的操作前（如大型升級、移除等），系統自動調用 `ACT-10: SNAPSHOT` 保存當前組態點。
2. **`rollback` 指令執行管線**
   - 調用 `ACT-11 (RESTORE_SNAPSHOT)` 自快照區提取最近一次可用快照點，倒回復原 `yscb.config.json`。
   - 調用 `ACT-08 (RELOAD)` 依快照組態自 `mirror/` 重新乾淨載入純淨模組並重建注入。
   - 輸出還原報告，確保在無網路或離線情境下亦能 100% 秒級自癒。

### 附錄 8：`self-update` 宿主自我更新微觀推演紀錄

1. **`self-update` 核心定位**：更新 `yscb.py` 自身起手單檔至遠端最新發布版。此為**宿主原生指令**，100% 使用 Python 標準庫實現，完全不依賴 `core` 模組或 `FETCH<source>` 原子操作。
2. **微觀執行步驟**：
   - **檢索最新版**：以宿主原生 HTTP 工具查詢遠端發布之最新 `yscb.py` 腳本與雜湊值。
   - **版本比對**：比對本地版本，若已為最新版本則直接退出。
   - **暫存與語法驗證**：下載至 `temp://` 暫存檔，執行 Python 語法解析確保腳本非空且無損壞。
   - **原子覆蓋替換**：將當前 `yscb.py` 備份為 `.bak` 後，原子覆蓋替換為新版腳本。
   - **輸出升級報告**：向使用者提示升級完畢與最新版本號。

### 附錄 9：`ACT-12: DISPATCH_CLI` 泛用 CLI 派發與路徑封裝鐵律

1. **路徑無知性與封裝防呆鐵律 (Path Encapsulation Axiom)**
   - 宿主 `yscb.py` 在派發 CLI 時，**嚴禁**向業務模組暴露或傳遞底層路徑字串（如 `yscb_root`、`project_root` 等）。
   - 所有業務模組內部**一律嚴格透過 `core` 模組之語意 URI 系統（`ProjectURI` SDK）統一進行路徑解算與檔案 I/O**。
2. **CLI 派發執行管線**
   - **目標探測**：檢查 `yscb.config.json` 中目標模組是否已安裝，且 `yscb://modules/{module}/scripts/cli.py` 是否存在。
   - **參數透傳**：宿主將除 `{module}` 外的所有後續命令、子指令與旗標無損透傳至目標模組。
   - **狀態碼透傳**：以原生方式捕獲模組 `cli.py` 執行之 Exit Code 並透傳回終端。












