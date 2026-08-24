# 計畫變更紀錄 (Changelog)

> 功能名稱：架構設計重構與不良處優化 (Architecture Refactor & Optimization)  
> 模板版本：v1.0  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
|---------|------|------|
| 2026-08-24 19:15 | `DECISION` | R01~R05 地毯式審查 16 項議題全數定案與閉環修訂：跨文件一致性 (I-01~04)、文件遺漏 (G-01~07)、邏輯缺口 (L-01~03) 與建議補強 (E-02) 完成收斂 |
| 2026-08-24 18:47 | `CONTEXT` | 全域移除 `latest/` 實體目錄/符號，純淨產物空間僅由純版本號資料夾（`{version}/`）組成，無指定版本時一律透過 `index.json` 之 SemVer 索引解算最新版本 |
| 2026-08-24 18:46 | `CONTEXT` | R04/R05 校正 build 與 Provider 結構：每個版本為完全獨立純淨之 `module://{version}/`（內含專屬 `manifest.json` 快照），模組層級僅自動生成/維護一份 `index.json` |
| 2026-08-24 18:34 | `CONTEXT` | R04 (附錄 5) 確立 Provider 核心抽象為 `module.build.root://` 結構 |
| 2026-08-24 18:31 | `CONTEXT` | 全域新增 `*.root://` 協議族（`module.root://`, `config.root://`, `cache.root://`, `module.source.root://`, `module.build.root://`） |
| 2026-08-24 18:27 | `CONTEXT` | R01/R02/R03/R05 確立版本化建置產物空間規範 |
| 2026-08-24 18:24 | `CONTEXT` | 統一 Installer 指令第一參數固定為 `<module_name>`（來源收斂至 `--provider="<source>"`），確立物化時強制比對 `manifest.json.name == <module_name>` 之 Double-Check 安全防禦機制 |
| 2026-08-24 18:21 | `CONTEXT` | R04 (附錄 5) 確立「模組根目錄物化契約 (Module Root Invariant)」 |
| 2026-08-24 18:15 | `CONTEXT` | R02/R03 新增常數協議 `temp://`（指向 `yscb://.temp/`，由 core 維護之系統暫存目錄）；R05 (Ch.4) 確立開發者套件 `module:dev` 規格 |
| 2026-08-24 18:07 | `CONTEXT` | 建立 R05 (`R05_developer_ecosystem_and_migration.md`)：收錄開發者 A/B 雙角色生態流、三大自引用解耦防護屏障與五階段專案重構遷移路線圖 |
| 2026-08-24 17:51 | `CONTEXT` | R04 提煉動態派發原子操作 `ACT-12: DISPATCH_CLI`，完成泛用 CLI 路由調用流映射與附錄 9 記錄 |
| 2026-08-24 17:49 | `CONTEXT` | R04 完成 `self-update`（宿主單檔自我更新）指令生命週期映射與附錄 8 記錄 |
| 2026-08-24 17:48 | `CONTEXT` | R04 提煉快照原子操作 `ACT-10: SNAPSHOT` 與 `ACT-11: RESTORE_SNAPSHOT`，完成模式 B 快照災難恢復之 `rollback` 指令生命週期映射 |
| 2026-08-24 17:46 | `CONTEXT` | R04 完成 `status`（環境自檢）指令生命週期映射與附錄 6 記錄 |
| 2026-08-24 17:45 | `CONTEXT` | R04 校正 `FETCH<source>` 語意為來源通道傳輸協定抽象（支援 `remote_git`, `remote_https`, `local` 等） |
| 2026-08-24 17:14 | `CONTEXT` | R04 提煉參數化元數據讀取原子操作 `ACT-09: FETCH<source>`，並完成 `list` 指令生命週期映射 |
| 2026-08-24 17:11 | `CONTEXT` | R04 提煉相依求解原子操作 `ACT-06: SOLVE_DEPS`（版本約束與相依拓撲求解），並完成 `update` 與 `install` 的相依求解生命週期映射 |
| 2026-08-24 17:08 | `CONTEXT` | R04 提煉 7 大原子操作：DOWNLOAD/DELETE (對象 mirror)、REGISTER/UNREGISTER (對象 config)、PREPARE (狀態同步) 與 RELOAD (運行重構) |
| 2026-08-24 01:38 | `CONTEXT` | R04 提煉「期望狀態獲取 (TRY_INSTALL) vs. 運行端重構調和 (RELOAD)」職責分離模型 |
| 2026-08-24 01:31 | `CONTEXT` | 確立重大空間邊界認知（運行端僅有 `modules/` 與 `mirror/`；`source/build` 由開發模組提供）；定義原子操作 `ACT-02: TRY_INSTALL` |
| 2026-08-24 01:18 | `CONTEXT` | R04 新增「附錄：各指令生命週期推演詳細紀要」，精確收錄 `init` 微觀 7 步行為與防呆約束 |
| 2026-08-24 01:16 | `CONTEXT` | R04 確立第一項原子行為 `ACT-01: INIT`（宿主一次性自舉流程壓縮為單一原子行為），並完成 `init` 生命週期映射 |
| 2026-08-24 01:11 | `CONTEXT` | 清空 R04 預擬內容回歸乾淨草稿骨架，改採「指令逐一推演 ➔ 原子行為萃取 ➔ 建立生命週期行為矩陣」的標準迭代流程 |
| 2026-08-24 01:07 | `CONTEXT` | 建立 R04 (`R04_lifecycle_invocation_flow.md`)：獨立專題調研生命週期與調用流規範 |
| 2026-08-24 01:05 | `CONTEXT` | R03 (Ch.2.1, Ch.2.3) 確立二元機制：佔位符結合 `handler` 按需解算 (Provider)，新增 `events` 生命週期廣播注入；P00 登記初始化自舉階段事件調度防呆議題 |
| 2026-08-24 00:52 | `CONTEXT` | R02 (Ch.2.2, Ch.4) 移除 `mode` 欄位（三空間語意已取代其職責），更新 `init` 為最小路徑保證；R03 (Ch.1) 補宣告 manifest SSOT 為 `module.source://` |
| 2026-08-24 00:41 | `CONTEXT` | R01 (Ch.2.2)、R02 (Ch.3.2) 與 R03 (Ch.2.2.4) 確立「三階段模組空間協議」：定義 `module.source://` (源碼開發)、`module.build://` (純淨產物) 與 `module://` (注入後運行端) |
| 2026-08-24 00:25 | `CONTEXT` | 更新 P00 語意需求書：定案範疇界定 (In-Scope: yscb.py + core + test; Out-of-Scope: agents-workflow + 開發工具模組) 與 4 大不可破壞約束 |
| 2026-08-24 00:20 | `CONTEXT` | R02 (Ch.3.2) 與 R03 (Ch.2.2.4) 新增常數協議 `mirror://`（指向 `yscb://.mirror/`），用於維護本地端倉庫鏡像 |
| 2026-08-24 00:09 | `CONTEXT` | R02 (Ch.3.1) 新增 installer 類別指令 `reload`：重新掃描並聚合全域模組 contributes 注入，刷新本地運行端狀態 |
| 2026-08-24 00:03 | `CONTEXT` | R03 寫入「Ch.2 core 注入協議規範 -> 2.2 URI 協議注入」：定義 token/type/value Schema，並建立 config 類型禁止讀取 local 之路徑版控防呆鐵律 |
| 2026-08-23 23:56 | `CONTEXT` | R03 寫入「Ch.2 core 注入協議規範 -> 2.1 路徑佔位符注入」：規範 token/description Schema、core 自注入與 hook 簽章解算機制 |
| 2026-08-23 23:41 | `CONTEXT` | R02 (Ch.3.2 & Ch.4) 將 `yscb://` 來源重定義為 `yscb.config.json` 之 `yscb_root`（由 `init {yscbRoot}` 寫入之實體錨點） |
| 2026-08-23 23:30 | `CONTEXT` | R03 (Ch.1.4) 與 R01 (Ch.2.2) 確立「contributes 5 大檢索來源矩陣」：定義靜態常數、指向性定義、專案級注入與本地級注入 |
| 2026-08-23 23:19 | `CONTEXT` | R01 (Ch.2.2) 與 R03 (Ch.1.3) 增量模組規範：新增條件必須檔案 `module://contributes.format.md` 作為模組擴充能力說明書 |
| 2026-08-23 23:17 | `CONTEXT` | R03 寫入「Ch.1 manifest 標準格式」：抽象化規範 Schema、欄位定義與 contributes 貢獻結構 |
| 2026-08-23 23:13 | `CONTEXT` | 開立專題 R03「manifest 格式與運行週期調用流 (R03_manifest_and_lifecycle_flow.md)」 |
| 2026-08-23 23:11 | `CONTEXT` | R02 與 R01 定義路徑佔位符 `PathPlaceholder`（格式 `"{name}"`），導入 `{module}` 規範 `cache://`、`config://` 與 `module://` 之動態基底 |
| 2026-08-23 23:07 | `CONTEXT` | R01 寫入「Ch.2 檔案結構架構規範 -> 2.2 模組檔案結構規範」：定義 `module://` 協議與 1 必須 + 4 可選之模組標準檔案骨架 |
| 2026-08-23 22:51 | `CONTEXT` | R01 寫入「Ch.2 檔案結構架構規範 -> 2.1 yscb.py 與 yscb.config.json 存放規範」 |
| 2026-08-23 22:49 | `CONTEXT` | R02 更新「Ch.3 module:core 核心模組職責定義 -> 3.2 uri 系統職責」：定義 core.uri 為唯一路徑入口與 4 大通用協議 (`project://`, `yscb://`, `cache://`, `config://`) |
| 2026-08-23 22:34 | `CONTEXT` | R02 寫入「Ch.4 yscb.config.json 格式規範」：定性為僅持有 `installed_modules` 之純安裝清冊 |
| 2026-08-23 22:29 | `CONTEXT` | R02 正式重定義為「yscb/core 職責總覽 (yscb/core Responsibilities Overview)」，確立 yscb.py 超薄宿主與 module:core 雙層體系 |
| 2026-08-23 22:21 | `CONTEXT` | R02 更新「Ch.3 installer 職責定義 -> 3.1 核心 Installer 指令集」：補完模組基礎路徑 `yscb://modules/` 與 `init {yscbRoot}` 指令細則 |
| 2026-08-23 22:04 | `CONTEXT` | R02 更新「Ch.1 維度概覽」：擴充插入第 4 維度「tools 職責」，順延「使用者視角 & API」為第 5 維度 |
| 2026-08-23 22:03 | `CONTEXT` | R02 寫入「Ch.4 cli 職責定義 -> 4.1 CLI 派發語法與規則」 |
| 2026-08-23 21:59 | `CONTEXT` | R02 寫入「Ch.3 installer 職責定義 -> 3.1 核心 Installer 指令集 (8 項純 Installer 語意指令)」 |
| 2026-08-23 21:52 | `CONTEXT` | R02 寫入「Ch.2 執行邊界定義 -> 2.1 語意化定義 (Semantic Definition)」 |
| 2026-08-23 21:45 | `CONTEXT` | R02 寫入「Ch.1 維度概覽」純骨架（包含 4 大核心維度） |
| 2026-08-23 21:40 | `CONTEXT` | 分流調研主題：R01 定位為調研總覽，開立 R02 專題「yscb 職責總覽 (R02_yscb_responsibilities.md)」 |
| 2026-08-23 21:14 | `CONTEXT` | R01 寫入第一章節「程式邏輯架構規範 (Programmatic Logical Architecture)」 |
| 2026-08-23 20:38 | `CONTEXT` | 重新定義 R01 為「模組化體系宏觀架構調研 (Module Architecture Survey)」，提升至宏觀高度審視模組定義與架構債 |
| 2026-08-23 20:30 | `PHASE` | 開立計畫目錄、P00 語意需求草案與 R01 增量調研報告 (狀態: Discussing) |

---

## 類型標籤說明

| 標籤 | 用途 |
|------|------|
| `PHASE` | Phase 轉換（含 Checkpoint 通過） |
| `DECISION` | Deep Discussion 結論 |
| `DEVIATION` | 偏差處理記錄 |
| `SUB-PLAN` | 子計畫新增 |
| `SUB-DONE` | 子計畫完成 |
| `CONTEXT` | 跨 Conversation 的新增指示或偏好調整 |
| `EXTENSION` | 專案擴充機制的執行記錄 |
