# 計畫變更紀錄 (Changelog)

> 功能名稱：core.commands 活躍執行合約與 CLI 派發管線重構  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Completed  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 2026-09-07 11:30 | `PHASE` | 進入 Phase 7 成果展示與結案階段，產出 P07_walkthrough.md，全項驗收合規完成，子計畫圓滿結案 (狀態：`Completed`) |
| 2026-09-07 11:28 | `REVIEW` | 通過 SOP Review 結案審查：三層文檔對齊（CHANGELOG.md 預擬高階摘要、專題手冊已同步、代碼註解完整）、自動化測試 100% 通過（core 162/162, server 23/23）、開發者實機 UX 驗證（UX-01/02）標註完成、`plan check` 合規性檢核 PASSED |
| 2026-09-07 11:25 | `PASS` | 開發者實機核驗 UX-01（`uri --help`, `uri resolve --help`, `config --help`）與 UX-02（巢狀子指令派發與執行）通過，標註 `[測試通過]` |
| 2026-09-07 11:23 | `DECISION` | 確立 [P02:DR-08]（參數型態之結構化推導原則）：維持零冗餘標籤之結構化推導（頂層 `args` 為位置變數 Positional Var、Option 無 `args` 為布林旗標 Boolean Flag、Option 含 `args` 為帶值選項 Option Var）；並於專題手冊 `cli_commands_architecture.md` 確立對照表與行為約束 |
| 2026-09-07 11:02 | `FEAT` | 完成同構遞迴指令樹實作：升級 `CommandsRegistry`、`dispatcher`、`HelpRenderer`（SUBCOMMANDS 渲染）；遷移 `uri`、`config`、`event` 為巢狀結構；重構 `cli.py` 為底線平鋪函式；新增 FT-11 測試；`core` (162) 與 `server` (23) 測試 100% 通過；同步更新 `docs/Core/cli_commands_architecture.md` 規格手冊 |
| 2026-09-07 10:52 | `DECISION` | 確立 [P02:DR-07]（同構遞迴指令樹與三態派發模型）：`CommandSpec` 支援同構 `cmd` 樹，支援純葉子、純分支與可呼叫複合分支三態；實作端約定以底線平鋪命名函式（如 `uri_list`、`config_get`）；純分支呼叫自動輸出 Help |
| 2026-09-07 10:38 | `FEAT` | 全面移除 `has_value`，指令與選項統一採用 `args` 字典規格，支援 `choice` 列舉約束與自動 CLI 視覺格式化 (<mode=[a \| b]>)；補齊 ET-07、ET-08 測試，core (161) 與 server (23) 測試 100% 通過 |
| 2026-09-07 10:25 | `PHASE` | 完成 Phase 6 自動化測試 (FT-01~10, ET-01~06, PT-01, RT-01 100% 通過)，抵達 P06 UX 驗收 Checkpoint |
| 2026-09-07 10:20 | `PHASE` | 完成 Phase 5 任務實作 (TASK-01~05)：core.commands 核心子模組、PEP 562 Lazy Loading、yscb.py 薄宿主、先驅模組遷移與 test_core_commands.py |
| 2026-09-07 10:15 | `PHASE` | 進入 Phase 5 任務實作階段，產出 P05_task.md (TASK-01~05) |
| 2026-09-07 10:10 | `DECISION` | 確立 [P04:DR-01] ~ [P04:DR-02]（全域派發與退化執行點收斂、IDE 友好 PEP 562 宣告） |
| 2026-09-07 10:10 | `PHASE` | 完成 Phase 4 實作計畫與審查，產出 P04_implementation_plan.md，定稿 P06_test_plan.md (狀態：`Confirmed`) |
| 2026-09-07 10:05 | `PHASE` | 完成 Phase 3 API 規格定義，產出 P03_api_spec.md (CmdOption/CmdBags, CommandsRegistry, OptionResolver, HelpRenderer, CommandDispatcher) |
| 2026-09-07 10:00 | `DECISION` | 確立 [P02:DR-01] ~ [P02:DR-05]（引擎子包職責單一化、PEP 562 快取、對稱 Hook、靜默退化與模糊防護） |
| 2026-09-07 10:00 | `PHASE` | 完成 Phase 2 架構設計，產出 P02_architecture_plan.md 並初始化 P06_test_plan.md (Draft: FT-01~10, ET-01~06, PT-01, RT-01) |
| 2026-09-07 09:55 | `DECISION` | P01 核查更新：確立 [P01:DR-03] ~ [P01:DR-05]（入口職責邊界、靜默過渡層、module_alias 派發匹配）；補入 FR-10（Hook 對稱下沉）、EC-06（別名衝突）、調整 FR-06 為指令級、FR-07 明訂 yscb.py 入口職責、FR-08 移除 warning 靜默化 |
| 2026-09-07 09:47 | `DECISION` | 確立 [P01:DR-01] ~ [P01:DR-02] 正交群組命名空間化與原生布林型態 server_compatible |
| 2026-09-07 09:47 | `PHASE` | 完成 Phase 1 規格轉譯，產出 P01_requirements_spec.md (FR-01~09, EC-01~05, NFR-01~03) |
| 2026-09-07 09:45 | `DECISION` | 確立 [P00:DR-01] ~ [P00:DR-06] 活躍執行合約、Lazy Loading 與兩階段遷移守門 |
| 2026-09-07 09:45 | `PHASE` | 開立子計畫目錄，伴隨建立 P00 需求討論書與本變更日誌 (狀態：`Confirmed`) |
