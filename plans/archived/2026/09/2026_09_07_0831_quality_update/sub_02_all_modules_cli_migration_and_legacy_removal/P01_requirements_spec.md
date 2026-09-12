# 需求規格說明書 (Requirements Specification)

> 功能名稱：全生態系模組 CLI 活躍執行合約遷移與向後相容過渡層徹底拔除  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `dev` 模組 Contributes 與 CLI 精確函式重構 | 於 `source/dev/contributes/core.json` 定義新版 `commands` schema（含 `test`, `check`, `build`, `create`, `bump-*`, `release*` 之 `tier`, `server_compatible`, `args`, `options`, `usage`）；重構 `source/dev/scripts/cli.py` 為精確命令函式（如 `def test(cmd_bags: CmdBags) -> int`），徹底移除 `def process(args)` 與 `argparse` 手工剖析。 | P0 | [P00:DR-01] |
| **FR-02** | `knowledge-db` 模組 Contributes 與 CLI 精確函式重構 | 於 `source/knowledge-db/contributes/core.json` 宣告新版 `commands` schema，查詢與分析類指令（`search`, `callers`, `callees`, `impact`, `status`）宣告 `server_compatible: true` 以支援常駐 Worker 熱派發；重構 `source/knowledge-db/scripts/cli.py` 為精確函式，徹底移除 `def process(args)`。 | P0 | [P00:DR-01] |
| **FR-03** | `agents-workflow` 模組 Contributes 與同構遞迴指令樹重構 | 於 `source/agents-workflow/contributes/agents-workflow.json` 補齊 `commands` schema；落地 `plan` 複合分支（巢狀 `cmd` 含 `archive`, `status`, `search`, `check`, `verify`）及 `release`, `release-target`, `compile`, `roadmap`, `tokens`, `list`, `init` 等指令；重構 `cli.py` 以底線平鋪函式（如 `plan_status(cmd_bags)`）對接，徹底移除 `def process(args)`。 | P0 | [P00:DR-01] |
| **FR-04** | 全生態系模組廢除 `argparse` 與 `sys.argv` 手工剖析 | 全生態系 5 大模組 CLI 實作全面以強型別 `CmdBags` 作為唯一外部呼叫接口，透過 `cmd_bags.args` 取用位置參數、透過 `cmd_bags.options` 取用正交選項與參數值，達成零外部參數解析膠水層。 | P0 | [P00:DR-03] |
| **FR-05** | 剛性拔除向後相容過渡層 (Hard Sunset Gate) | 三大模組遷移完成後，自 `source/core/core/commands/dispatcher.py` 徹底刪除 `process(args)` fallback 分支及相關暫存向後相容代碼；若目標模組未定義精確命令函式亦非純分支，嚴格拋出 `EC-05` 契約缺失錯誤（退出碼 127），全生態系 100% 封閉舊 `process` 契約。 | P0 | [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 未定義精確命令函式且無 process fallback | 過渡層刪除後，調用未定義精確函式的指令時，不再有任何 fallback 退化路徑，嚴格輸出 `EC-05` 契約缺失錯誤並返回退出碼 127。 |
| **EC-02** | `dev test` 正交選項互斥與別名解析 | `--quiet` 與 `--verbose` 宣告為同一正交群組，同時傳入時由 `OptionResolver` 攔截阻斷；`-k`、`--no-build`、`--all` 正確解析為 `CmdOption`。 |
| **EC-03** | `knowledge-db search` 輸出格式正交互斥 | `--preview/-s`、`--detail/-d`、`--simple` 宣告為同一正交群組，傳入多個時拋出 `MutualExclusionError`；缺少必填 `<query>` 時拋出 `MissingArgumentError`。 |
| **EC-04** | `agents-workflow plan` 巢狀參數與未知子指令 | 執行 `plan unknown_action` 時，Help 系統自動攔截並提供 `AVAILABLE SUBCOMMANDS:` 與模糊建議；執行 `plan archive` 缺少 `<plan_name>` 時由 `OptionResolver` 阻斷提示必填。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 全生態系回歸 | 全生態系 5 大模組全量測試套件（400+ 案例，包含 `core`, `server`, `dev`, `knowledge-db`, `agents-workflow`）100% 綠燈通過，無功能破壞。 |
| **NFR-02** | 零架構技術債 | 全專案代碼庫（`source/` 下所有模組）不再存在任何 `def process(args: List[str])` 接口，徹底消滅雙軌並存。 |
| **NFR-03** | 派發效能 | 本地冷派發參數解析延遲 $\le 1\text{ms}$；`knowledge-db` 常駐 Worker 熱派發端到端延遲 $\le 5\text{ms}$。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `knowledge-db` 模組在 `scripts/cli.py` 重構為精確函式時，必須維持 `get_engine()` 進程級單例共享，確保 Worker 進程內多命令共享索引與模型快取，避免重複初始化重型模型。
- **`[!NOTE]`** `agents-workflow plan` 原有 `check` 與 `verify` 在使用習慣上具有同義性質，在同構指令樹中應將 `verify` 作為 `check` 之同義子指令或別名委派，避免破壞現有 Agent 工作流與合規檢核指令。
- **`[!CAUTION]`** 在執行 FR-05 徹底刪除向後相容過渡層前，必須確保三大模組之單元測試已完成更新（包含 `test_core_commands.py` 原 FT-08 退化測試需改寫為 FT-08 嚴格 EC-05 斷言）。

---

## 5. 關鍵架構決策 (Design Decisions)

- **[P01:DR-01] 模組 Contributes Commands Schema 統一就地規範**：
  各模組 commands 宣告優先維護於各自 `contributes/<module_name>.json` 或 `core.json`，對齊各模組現有 contributes 空間，消除 `phases` 等歷史遺留欄位。
- **[P01:DR-02] `knowledge-db` 指令熱派發分流矩陣**：
  唯有安全唯讀與狀態查詢類指令（`search`, `callers`, `callees`, `impact`, `status`）宣告 `server_compatible: true`，走常駐 Worker 瞬發響應；有環境副作用或破壞性之指令（`clean`, `bundle`, `scan`, `index`）維持 `server_compatible: false`，走本地隔離進程執行。
- **[P01:DR-03] `agents-workflow plan` 複合同構分支落地**：
  `plan` 宣告為複合分支（Hybrid Group），直接執行 `python yscb.py agents-workflow plan` 預設輸出子指令 Help；其子指令 `archive`, `status`, `search`, `check`, `verify` 宣告於其 `cmd` 字典下，由 `plan_archive(cmd_bags)` 等平鋪函式承接。
- **[P01:DR-04] 剛性過渡層拔除之回歸斷言**：
  刪除 `dispatcher.py` 內部 `hasattr(mod, "process")` 邏輯後，新增專屬測試案例驗證：任何未實作精確函式的未知模組調用，必返回 127 並明確指出缺乏 `cmd(cmd_bags)` 契約。
