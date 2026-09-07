# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：品質更新 (Quality Update)  
> 建立日期：2026-09-07  
> 狀態：Completed  
> Umbrella 模式：Incremental (增量演進型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：以系統品質提升與架構純淨化為核心主題，聚焦「`core.commands` 活躍執行合約」與「Server 通用無感外殼」，使任意模組僅需宣告 contributes 並實作精確命令函式 `cmd(cmd_bags)`；由 `core.commands` 統一接管參數解析、別名標準化、正交群組互斥校驗、統一 `--help` 攔截，並依據 `server_compatible` 進行無感派發（常駐 Worker vs 隔離子進程）。同時建立剛性 Contributes Schema 校驗與 Ingress/Egress 邊界隔離體系。
- **架構邊界**：`yscb.py` 宿主、`core.commands` 微內核引擎、`core.contributes` 依賴注入與校驗引擎、`server` 模組（Master/Worker）、`dev` 工具鏈與全生態系 5 大模組 CLI 與貢獻宣告。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_core_commands_and_dispatch_architecture` | Full Track | `Completed` | 1. `core/__init__.py` Lazy Loading 淨化<br/>2. `core.commands` 引擎實作（新 schema、正交校驗、CmdBags、Help 攔截、`server_compatible`）<br/>3. `yscb.py` 瘦身下沉（除 `init` 外全轉派 `core.commands`）<br/>4. 暫時性向後相容層（優先 `cmd(cmd_bags)`，fallback `process(args)`）<br/>5. `core` 與 `server` 先驅模組遷移驗證 |
| **sub_02** | `sub_02_all_modules_cli_migration_and_legacy_removal` | Full Track | `Completed` | 1. 其餘領域模組全面遷移（`dev`, `knowledge-db`, `agents-workflow`）改寫為 `cmd(cmd_bags)`<br/>2. 🚨 **關鍵剛性守門：全面遷移完成後，徹底刪除 `core.commands` 內部向後相容過渡層，全生態系 100% 封閉舊 `process(args)` 契約** |
| **sub_03** | `sub_03_contributes_schema_and_rigid_validation` | Full Track | `Completed` | 1. `contributes/` 檔案拓撲標準化（`_format.json` Ingress、`_manifest.md` Egress、移除舊 `phases`）<br/>2. 輕量 Schema DSL 解析器與校驗引擎（100% Python 標準庫）<br/>3. `core` 模組新增 `contributes list` 與 `contributes check` 指令與 SDK<br/>4. `dev check` 與運行期 `ContributesAggregator` 剛性單向邊界阻斷<br/>5. `dev create module` 腳手架預置與 5 大模組生態遷移 |

---

## 3. 當前核心待處理項目 (Key Focus Areas)

1. **`core/__init__.py` 延遲載入 (PEP 562 Lazy Exports)**：
   - 移除頂層 eager imports，將 `core` 模組冷啟動加載時間由 ~77ms 驟降至 <2ms。
2. **`core.commands` 派發與驗證引擎**：
   - 解析新版 contributes `commands` 規範（移除 `phases` 耦合、引入 `options` 正交群組與 `server_compatible`）。
   - 統一攔截 `--help / -h / help`，動態注入 `tier`、`usage (pros/cons)` 與選項手冊。
   - 封裝強型別 `CmdBags`（含 `raw_cmd`, `command`, `args`, `options`），標準化別名與參數型別。
3. **`yscb.py` 薄宿主純粹化**：
   - 移除寫死黑名單與自製派發器，除 `init` 自舉外，全指令轉派 `core.commands`。
4. **兩階段遷移與過渡層徹底清除 (Two-Stage Migration & Legacy Wipe)**：
   - `sub_01` 建立新引擎並保留雙軌過渡相容。
   - `sub_02` 推進其餘模組遷移，並在驗收前剛性拔除向後相容代碼，不留任何架構技術債。
5. **Contributes 宣告架構升級與 Schema 剛性校驗 (`sub_03`)**：
   - 建立 `_format.json` 與 `_manifest.md` Ingress/Egress 邊界拓撲。
   - 實現 `core.contributes` 輕量型別 DSL 驗證器與指令。
   - 剛性阻斷跨目標注入與髒資料進入快取。

---

## 4. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1**：完成 CLI 問題深入討論，確立 `core.commands` 與兩階段遷移架構
- [x] **里程碑 2**：完成 sub_01（`core.commands` 核心架構、過渡相容層與先驅模組遷移）
- [x] **里程碑 3**：完成 sub_02（全模組遷移、**向後相容層徹底刪除**、全生態系測試 100% 通過與結案）
- [ ] **里程碑 4**：完成 sub_03（Contributes Schema DSL、`contributes list/check` 指令、剛性單向邊界檢測、腳手架與 5 大模組生態全面遷移）
