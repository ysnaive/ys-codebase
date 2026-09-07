# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：core.commands 活躍執行合約與 CLI 派發管線重構  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 趁優化 CLI 派發，建立 `core.commands`，將 contributes commands 建立為真正有邏輯效益的注入貢獻。
  - 修改現有 commands contributes 格式（包含 `module_alias`、`cmd`、`description`、`tier`、`server_compatible`、`options` 正交群組與 `usage: {pros, cons}`），徹底移除與 `agents-workflow` 耦合的 `phases`。
  - `yscb.py` 除 `init` 初始化特例外，一律轉派給 `core.commands` 處理任何派發與命令邏輯。
  - 全面升級 commands 派發匹配機制：`core` 僅派發明確註冊的指令；若帶有 `--help / -h / help` 則由 `core` 統一攔截並輸出 `tier`、`usage` 與選項說明；通過 contributes 約束解決子模組實作品質不一問題（如未處理 help、別名或正交參數驗證）。
  - 模組 CLI 規範升級：不再要求定義脆弱的 `process(args)`，而是依據 contributes 定義提供對應的精確函式（例 `status(cmd_bags)`）。
  - 規劃為兩階段演進：`sub_01` 實作核心引擎、過渡相容層與先驅模組；`sub_02` 推進全生態系遷移，並**著重標記需同時於 `sub_02` 結案前徹底移除向後相容過渡層**。
- **核心目標**：
  1. **微內核延遲載入 (PEP 562 Lazy Loading)**：淨化 `core/__init__.py` 頂層 eager imports，將 `core` 冷啟動導入開銷由 ~77ms 驟降至 <2ms。
  2. **`core.commands` 核心引擎實作**：
     - 解析新版 contributes commands 規範。
     - 正交群組互斥（Mutually Exclusive）校驗防禦。
     - 別名自動轉換標準全名，強型別封裝為 `CmdBags`。
     - 全生態系統一攔截與格式化輸出 `--help`（整合 tier、usage、options）。
     - 依據 `server_compatible` 進行無感雙管道路由分流（Server Worker HTTP IPC vs 隔離子進程）。
  3. **`yscb.py` 極致薄宿主化**：除 `init` 外部套件自舉外，全指令無條件轉派 `core.commands`，移除宿主自製派發器與寫死黑名單。
  4. **雙軌過渡相容層**：優先尋找精確函式 `cmd(cmd_bags)`，若未遷移暫時退化為 `process(args)`。
  5. **先驅模組遷移與驗證**：完成 `core` 與 `server` 模組的 contributes 新格式宣告與精確命令函式改寫，100% 通過單元與回歸測試。
- **邊界排除 (Explicitly Excluded)**：
  - `dev`、`knowledge-db`、`agents-workflow` 等領域模組的全面改寫不包含在 `sub_01`，留待 `sub_02` 推進。
  - 向後相容過渡層的刪除嚴格留待 `sub_02` 結案前作為剛性守門執行。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 活躍執行合約 (Active Runtime Contract)**：contributes 由過去僅供生成的靜態 help 文本，升級為執行期命令匹配、別名解析、正交驗證與參數切分的唯一 SSOT。
- **[P00:DR-02] 宿主業務徹底下沉**：`yscb.py` 剝除自製派發邏輯與 `_MODULE_CACHE`，除 `init` 自舉外，全量轉派 `core.commands.dispatch(argv)`。
- **[P00:DR-03] 宣告式 `server_compatible` 取代黑名單**：廢除 `yscb.py` 寫死之 `dev, core, server` 排除邏輯，改由指令維度宣告 `server_compatible: true | false`，決定走 Worker 熱派發或隔離執行。
- **[P00:DR-04] 強型別 `CmdBags` 資料契約**：模組接收統一封裝之 `CmdBags`（包含 `raw_cmd`、`command`、`args` 位置參數列表、`options` 規範化鍵值字典），模組內部不再需要依賴 `argparse`。
- **[P00:DR-05] `core/__init__.py` 延遲載入**：採用 PEP 562 `__getattr__` 延遲導出重型子系統，確保 `core` 模組被 `yscb.py` 喚醒時維持 <2ms 瞬發效能。
- **[P00:DR-06] 兩階段遷移與剛性過渡層清理**：`sub_01` 實作過渡層（支援舊 `process(args)`）；`sub_02` 於全模組遷移驗收完成時，強制將該相容層自代碼庫徹底刪除，杜絕技術債沉積。

---

## 3. 開放議題與確認紀錄

- [x] 是否徹底剝離與 `agents-workflow` 耦合之 `phases` 欄位？（決策：已確認剝離）
- [x] 正交群組 options 是否為互斥約束？（決策：同組內選項互斥，違規直接報錯阻斷）
- [x] 遷移策略是否包含過渡層清除時限？（決策：已標記於 `sub_02` 結案前剛性移除）
