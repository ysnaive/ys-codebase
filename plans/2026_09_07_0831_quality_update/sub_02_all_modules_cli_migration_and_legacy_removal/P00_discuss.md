# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：全生態系模組 CLI 活躍執行合約遷移與向後相容過渡層徹底拔除  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：使用者指示「啟動下一階段子計畫」，接續推進 Umbrella 主計畫 `2026_09_07_0831_quality_update` 之 `sub_02_all_modules_cli_migration_and_legacy_removal`。
- **核心目標**：
  1. **其餘三大生態系模組全量遷移**：將 `dev`、`knowledge-db`、`agents-workflow` 三大領域模組全面遷移至 `core.commands` 活躍執行合約與同構遞迴指令樹架構：
     - 於各自 `contributes/<module>.json` 宣告新版 `commands` schema（`tier`、`server_compatible`、`args` 字典、`options` 正交群組、同構 `cmd` 樹與 `usage: pros/cons`）。
     - 重構 `scripts/cli.py`：改為宣告精確命令函式 `def <func_name>(cmd_bags: CmdBags) -> int` 或階層底線平鋪命名對應同構指令路徑，徹底廢棄內部 `argparse` 與舊 `process(args)` 接口。
  2. 🚨 **核心剛性架構守門 (Hard Sunset Gate)**：在三大模組完成遷移且全生態系測試（400+ 測試案例）100% 綠燈後，**徹底自 `core.commands.dispatcher` 拔除雙軌向後相容過渡層（`hasattr(mod, 'process')` fallback 分支與相關暫存邏輯）**，全系統 100% 封閉歷史 `process(args)` 契約，不留任何過渡期架構技術債。
- **邊界排除 (Explicitly Excluded)**：
  - 不修改模組底層核心領域引擎（如 `knowledge_db.engine`、`dev.runner`、`agents_workflow.compiler`），僅重構 CLI 入口與契約解析層。
  - 不引入新的外部第三方依賴，維持 100% Python 標準庫。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 三大生態系模組分步遷移序列**：
  依據模組依賴鏈與複雜度，採取有序分步推進策略：
  1. **第一步：`dev` 模組遷移**：涵蓋 `test`、`check`、`build`、`create`、`bump-*`、`release*` 等指令，清理其 CLI 入口中的 `argparse`。
  2. **第二步：`knowledge-db` 模組遷移**：涵蓋 `search`、`callers`、`callees`、`impact`、`bundle`、`index`、`scan`、`clean`、`status` 等指令，全面開啟 `server_compatible: true`，實現常駐 Worker 熱派發。
  3. **第三步：`agents-workflow` 模組遷移**：涵蓋複合分支 `plan`（子指令 `archive`、`status`、`search`、`check/verify`）、`release`、`compile`、`roadmap`、`tokens`、`list`、`init`，全面落地為同構遞迴指令樹。
- **[P00:DR-02] 剛性拔除向後相容過渡層 (Legacy Removal Gate)**：
  `sub_01` 引入之 `process(args)` 靜默退化過渡層為**具備確定生命週期之暫存債務**。當三大模組依序遷移完成並通過回歸測試後，必須於 `sub_02` 結案前直接自代碼庫中刪除該過渡分支。任何未註冊或未實作精確命令函式的模組將嚴格拋出 `EC-05` 契約缺失錯誤（退出碼 127），完成向新架構的剛性躍遷。
- **[P00:DR-03] 同構遞迴指令樹與結構化推導最佳實踐**：
  所有遷移模組全面依據 [P02:DR-07] 與 [P02:DR-08] 規範實作：
  - 複合命令群組以巢狀 `cmd` 樹定義，支援純葉子、純分支（自動輸出 SUBCOMMANDS 清單）與複合分支。
  - 參數定義統一採 `args` 字典，徹底廢除 `has_value`，嚴格依結構化推導位置變數 (Positional Var)、布林旗標 (Boolean Flag) 與帶值選項 (Option Var)。

---

## 3. 開放議題與確認紀錄

- [x] 是否同意將生態系其餘三大模組依序分步遷移（`dev` ➔ `knowledge-db` ➔ `agents-workflow`）？（已拍板確認）
- [x] 是否同意在三大模組遷移完成並測試綠燈後，剛性刪除 `core.commands` 內部向後相容過渡層？（已拍板確認）
