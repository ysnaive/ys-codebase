# 需求規格說明書 (Requirements Specification)

> 功能名稱：core.commands 活躍執行合約與 CLI 派發管線重構  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 微內核延遲載入 (PEP 562 Lazy Loading) | 淨化 `core/__init__.py` 頂層 eager imports，改用 `__getattr__` 依需求動態加載。單獨引用 `core.commands`、`core.events` 或 `core.guard` 時，不喚醒 `AtomicEngine`、`Installer`、`PipManager`、`VFS` 等重型子模組。 | P0 | [P00:DR-05] |
| **FR-02** | Contributes Commands 新 Schema 解析 | `core.commands` 定義並解析新版 `commands` contributes 結構（含 `module_alias: list`、指令清單 `cmd`、模組 `description`、各指令 `tier`、`server_compatible`、`args` 參數字典、`options` 正交群組與 `usage: {pros, cons}`）；`module_alias` 宣告之所有別名均可替代模組名稱進行派發匹配（當前生態系模組均不提供別名，機制備用）；徹底剝除與 `agents-workflow` 耦合之 `phases`。 | P0 | [P00:DR-01] |
| **FR-03** | 正交選項互斥與別名標準化 | 同一 Orthogonal Group 內的 Option 視為互斥約束（Mutually Exclusive），同組多選直接報錯阻斷；Option 別名在解析階段自動轉為規範名 (Canonical Name)；完全移除 `has_value`，改以 Option 內部 `args` 字典精確定義選項參數。 | P0 | [P00:DR-01] |
| **FR-04** | 強型別 `CmdBags` 結構化封裝 | 封裝不可變 `CmdBags` 物件，包含 `raw_cmd: str`（原始輸入串）、`command: str`（目標子命令規範名）、`args: list[str]`（循序位置參數）與 `options: dict[str, CmdOption]`（以規範名索引；`CmdOption` 含 `name: str` 規範名與 `params: Any` 參數值），模組端完全免除 `argparse` 與手動剖析。 | P0 | [P00:DR-04] |
| **FR-05** | 全生態系統一 `--help` 攔截與渲染 | 使用者傳入 `--help / -h / help` 時於入口統一攔截。模組級 Help 輸出模組說明、可用別名與指令清單；指令級 Help 輸出 `description`、`tier` 安全等級、自動格式化之位置參數與選項提示（含 `<name=[c1 | c2]>` / `[name]` 視覺轉譯）、`ARGUMENTS` 區塊與 `usage: pros/cons`。 | P0 | [P00:DR-01] |
| **FR-06** | 指令級 `server_compatible` 雙管道分流 | `server_compatible` 於 **`cmd` 層級**獨立宣告（非模組級），允許同模組不同指令採用不同執行策略。為 `true` 且常駐 Server 在線時走 HTTP IPC 熱派發；為 `false` 或 Server 離線時走本地冷派發。 | P0 | [P00:DR-03] |
| **FR-07** | `yscb.py` 極致薄宿主化與入口職責界定 | 移除 `yscb.py` 自製派發邏輯、`_MODULE_CACHE` 與硬編碼黑名單。`yscb.py` 保留且僅保留以下兩大入口職責：① `init` 外部套件自舉（外部呼叫唯一入口，進入執行期後轉為 venv 內部管理）；② 探測注入私有 `.venv` site-packages 至 `sys.path` 並設定 `YSCB_HOST_DISPATCH_TOKEN` / `YSCB_HOST_DIR` 安全邊界。其餘所有指令一律轉派 `core.commands.dispatch(argv)`。 | P0 | [P00:DR-02] |
| **FR-08** | 雙軌向後相容過渡層（靜默退化） | 分派至未遷移模組時，優先調用新契約精確函式 `getattr(mod, cmd_name)(cmd_bags)`；若目標模組尚未遷移，靜默退化調用舊契約 `mod.process(args)`（無 warning 輸出，避免污染 JSON 等結構化輸出）。本過渡層視為**暫存債務**，在 `sub_02` 全模組遷移完成後**剛性刪除**，不保留任何 `process` 分支。 | P0 | [P00:DR-06] |
| **FR-09** | `core` 與 `server` 先驅模組遷移 | 將 `core` 與 `server` 的 `contributes` 遷移至新格式，並將 `scripts/cli.py` 全面改寫為精確命令函式模式（如 `def status(cmd_bags: CmdBags) -> int: ...`）。遷移後這兩個模組不得殘留任何 `process(args)` 實作。 | P0 | [P00:DR-06] |
| **FR-10** | 生命週期 Hook 執行環境對稱下沉 (Symmetric Lifecycle) | 將 `pre_cli_dispatch` / `post_cli_dispatch` Hook 廣播從 Client 宿主端移至 `core.commands` 執行鏈內部觸發（含 Worker 熱派發路徑與本地冷派發路徑），確保無論執行環境如何，Hook 均在**執行命令的當下環境**內對稱觸發；同時消除 `yscb.py` 在轉發前強行 `import core.events` 的冷啟動開銷。 | P0 | [P00:DR-02] |
| **FR-11** | 參數宣告 (args) 與 choice 自動格式化及校驗 | 指令本體與選項之參數統一以 `args` 字典宣告（`{arg_name: {description, required, choice}}`）。`core.commands` 於 Help 自動格式化轉譯為 `<name>` / `[name]` 或帶有列舉選項的 `<mode=[auto | safe | force]>`；並於 `OptionResolver` 分發前自動完成必填性與 `choice` 合法值校驗，阻斷無效輸入。完全移除 `has_value` 且不向下相容。 | P0 | [P01:DR-06] |
| **FR-12** | 遞迴同構指令樹與子指令派發 | `CommandSpec` 支援遞迴同構宣告 `cmd: Dict[str, CommandSpec]`。每個指令節點均具備完全一致之標準欄位（`description`, `tier`, `server_compatible`, `args`, `options`, `cmd`, `usage`）。支援純葉子（直接執行實作函式）、純分支（無函式，呼叫自動輸出子命令 Help）與可呼叫複合分支（命中子指令轉派子函式，未命中則執行自身函式）。函式約定以底線平鋪（如 `uri_list`）。 | P0 | [P01:DR-07] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 未註冊之未知模組或未知指令 | `core.commands` 拒絕執行，進行模糊拼寫比對建議候選指令，並返回退出碼 1。 |
| **EC-02** | 同正交群組多選衝突 | 使用者同時輸入同正交群組內多個 Option（如 `--json` 與 `--table`），拋出清晰互斥報錯並終止執行，退出碼 1。 |
| **EC-03** | 帶值 Option 缺少參數值 | 宣告含 `args` 的 Option 若未提供參數值，報錯提示缺少參數並終止，退出碼 1。 |
| **EC-04** | Server Worker 熱派發通訊異常 | `server_compatible: true` 走 HTTP IPC 遇連線失敗、超時或中斷時，自動透明降級為本地冷派發，指令執行不中斷。 |
| **EC-05** | 目標模組既無精確函式亦無 process | 目標模組 `scripts/cli.py` 既無對應命令函式，亦無舊 `process` 接口，拋出契約缺失錯誤並返回退出碼 127。 |
| **EC-06** | 模組別名衝突 | 不同模組宣告相同 `module_alias`，`core.commands` 載入時報衝突錯誤（載入失敗或拒絕啟動）。 |
| **EC-07** | 參數值不符合 choice 列舉 | 位置參數或 Option 傳入之值不在 `choice` 定義之合法集合內，拋出 `InvalidChoiceError`，印出合法選項並終止，退出碼 1。 |
| **EC-08** | 缺少必填位置參數 | 指令宣告之 `required: true` 位置參數未給齊，拋出 `MissingArgumentError`，印出錯誤與用法並終止，退出碼 1。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 啟動效能 | Lazy Loading 後，單純導入 `core.commands` 之耗時 $\le 5\text{ms}$（現況 ~77ms，提升 15 倍以上）；`yscb.py` 本身轉派至 `core.commands.dispatch()` 的純路由耗時 $\le 2\text{ms}$。 |
| **NFR-02** | 零第三方依賴 | `core.commands` 解析器與路由器 100% 依賴 Python 標準庫，不引入任何外部套件。 |
| **NFR-03** | 回歸無斷裂 | `sub_01` 階段既有未遷移模組（`dev`, `knowledge-db`, `agents-workflow`）的全套測試 100% 通過，無功能斷裂。 |

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 既有未遷移模組（如 `agents-workflow`、`dev`）內部常定義 `cmd_<action>(args: List[str])` 作為舊 `process` 之內部輔助函式，過渡層派發必須隔離未宣告 `commands` 之舊模組，靜默退化調用 `mod.process`，避免誤判傳參類型。

---

## 5. 關鍵架構決策 (Design Decisions)

- **[P01:DR-01] 正交群組命名空間化**：Option 在 contributes 內透過 Orthogonal Group 分組，群組名稱作為互斥檢查與 Help 分組標題；`CmdBags.options` 字典以各 Option 規範名稱直接索引，與群組名無關。
- **[P01:DR-02] `server_compatible` 為指令維度宣告**：採用原生 JSON 布林值於 `cmd` 層級宣告，允許同模組不同指令擁有不同派發策略，消除模組級黑白名單。
- **[P01:DR-03] `yscb.py` 入口職責邊界**：`yscb.py` 作為系統唯一外部呼叫入口，保留且僅保留 `init` 自舉與進入執行期前的環境注入（`.venv` 注入與安全 Token），進入執行期後全部交由 `core.commands` 接管。
- **[P01:DR-04] 過渡相容層靜默且有期限**：舊契約退化不輸出任何 warning，避免污染結構化輸出；並在 `sub_02` 結案前強制刪除，不作為長期設計保留。
- **[P01:DR-05] `module_alias` 參與派發匹配**：別名可替代模組名用於命令行派發，`core.commands` 初始化時建立別名→模組名的映射表；當前模組均不宣告別名，機制備用。
- **[P01:DR-06] 參數模型全面統一為 args 字典並徹底移除 has_value**：不向下相容歷史 `has_value` 旗標；子指令位置參數與選項參數全面以 `args` 字典宣告，支援 `description`、`required` 與可選之 `choice` 列舉；Help 自動轉譯為視覺提示（如 `<mode=[a | b]>`），`OptionResolver` 自動完成必填性與列舉合法值校驗。
- **[P01:DR-07] 同構遞迴指令樹與階層式派發約定**：每個 `cmd` 節點同構遞迴，可自由嵌套子 `cmd`。模組端實作函式以底線連接階層路徑（如 `uri_list`、`uri_resolve`、`config_get`）；純分支無須定義實體函式，自動由 Help 系統接管；每個節點獨立擁有各自專屬的 `args` 字典與 `options` 正交群組，徹底消除不同子命令間的參數污染。
