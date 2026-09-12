# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：core.commands 活躍執行合約與 CLI 派發管線重構  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 單元測試 | 驗證 PEP 562 Lazy Loading：單獨 import `core.commands` 時不加載 `AtomicEngine`、`Installer` 等重模組 | FR-01 | `python -c "import sys; import core.commands; assert 'core.engine' not in sys.modules"` |
| **FT-02** | 單元測試 | 驗證新版 Contributes Commands Schema 解析 (含 module_alias, tier, server_compatible, options, usage) | FR-02 | `python yscb.py dev test core -k test_commands_schema_parser` |
| **FT-03** | 單元測試 | 驗證 OptionResolver 之正交群組互斥檢查、別名規範化與 has_value 解析 | FR-03 | `python yscb.py dev test core -k test_option_resolver` |
| **FT-04** | 單元測試 | 驗證強型別 `CmdBags` 與 `CmdOption` 屬性完整度與不可變性 | FR-04 | `python yscb.py dev test core -k test_cmdbags_dataclass` |
| **FT-05** | 單元測試 | 驗證模組級與指令級 `--help` 渲染格式與各字段輸出 | FR-05 | `python yscb.py dev test core -k test_help_renderer` |
| **FT-06** | 整合測試 | 驗證指令級 `server_compatible` 分流：true 走 HTTP IPC，false 走本地冷派發 | FR-06 | `python yscb.py dev test server -k test_server_compatible_routing` |
| **FT-07** | 整合測試 | 驗證 `yscb.py` 薄宿主轉派：移除非必要快取與黑名單，全轉派至 core.commands.dispatch | FR-07 | `python yscb.py dev test core -k test_yscb_thin_host` |
| **FT-08** | 整合測試 | 驗證雙軌向後相容過渡層：未遷移模組靜默退化調用 `mod.process(args)` 無 Warning | FR-08 | `python yscb.py dev test core -k test_backward_compat_silent_fallback` |
| **FT-09** | 整合測試 | 驗證先驅模組 `core` 與 `server` 遷移後無殘留 `process(args)` 且各命令正常工作 | FR-09 | `python yscb.py dev test core -k test_pioneer_modules_contract` |
| **FT-10** | 單元測試 | 驗證 `pre_cli_dispatch` / `post_cli_dispatch` 生命週期 Hook 於執行環境對稱觸發 | FR-10 | `python yscb.py dev test core -k test_symmetric_lifecycle_hooks` |
| **FT-11** | 單元測試 | 驗證同構遞迴指令樹解析、多層走訪 (resolve_command_path) 與子命令 Help 渲染 | FR-12 | `python yscb.py dev test core -k test_ft11_recursive_subcommand_tree` |
| **ET-01** | 邊界測試 | 驗證未註冊之未知模組或指令：返回退出碼 1 並提供模糊拼寫建議 | EC-01 | `python yscb.py dev test core -k test_unknown_cmd_fuzzy_suggest` |
| **ET-02** | 邊界測試 | 驗證同正交群組多選衝突：拋出清晰互斥報錯並返回退出碼 1 | EC-02 | `python yscb.py dev test core -k test_orthogonal_group_conflict` |
| **ET-03** | 邊界測試 | 驗證帶值 Option 缺少參數值時拋出錯誤並返回退出碼 1 | EC-03 | `python yscb.py dev test core -k test_missing_option_value` |
| **ET-04** | 邊界測試 | 驗證 Server Worker 熱派發通訊異常時透明降級為本地冷派發 | EC-04 | `python yscb.py dev test core -k test_hot_dispatch_fallback` |
| **ET-05** | 邊界測試 | 驗證目標模組無精確函式亦無 process 接口時返回退出碼 127 | EC-05 | `python yscb.py dev test core -k test_missing_entrypoint_contract` |
| **ET-06** | 邊界測試 | 驗證不同模組宣告重複 `module_alias` 時報衝突錯誤 | EC-06 | `python yscb.py dev test core -k test_module_alias_conflict` |
| **ET-07** | 邊界測試 | 驗證非法 choice 選項值或參數值：拋出 InvalidChoiceError 並返回退出碼 1 | EC-07 | `python yscb.py dev test core -k test_invalid_choice_option_and_arg` |
| **ET-08** | 邊界測試 | 驗證缺少必填 positional argument：拋出 MissingArgumentError 並返回退出碼 1 | EC-08 | `python yscb.py dev test core -k test_missing_required_positional_arg` |
| **PT-01** | 效能測試 | 驗證 `core.commands` 載入耗時 $\le 5\text{ms}$，`yscb.py` 純路由耗時 $\le 2\text{ms}$ | NFR-01 | `python yscb.py dev test core -k test_dispatch_performance` |
| **RT-01** | 全量回歸 | 驗證既有未遷移模組 (`dev`, `knowledge-db`, `agents-workflow`) 測試 100% 通過 | NFR-03 | `python yscb.py dev test core && python yscb.py dev test server` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 單獨 import `core.commands` 耗時 < 1ms，未加載 `core.engine`、`Installer` 等重模組 | 2026-09-07 |
| **FT-02** | `Passed` | Contributes Commands Schema 完整解析，正確識別 args 字典、orthogonal_groups 與 usage pros/cons | 2026-09-07 |
| **FT-03** | `Passed` | OptionResolver 正交群組衝突 (EC-02)、missing value (EC-03)、choice 約束 (EC-07) 與 missing arg (EC-08) 攔截驗證通過 | 2026-09-07 |
| **FT-04** | `Passed` | CmdBags / CmdOption frozen dataclass 不可變性與 has/get_option API 驗證通過 | 2026-09-07 |
| **FT-05** | `Passed` | HelpRenderer 全域、模組級與指令級說明輸出結構、args 參數視覺化及 pros/cons 渲染正確 | 2026-09-07 |
| **FT-06** | `Passed` | Server Worker 熱派發 IPC 與本地冷派發雙通道分流決策驗證通過 | 2026-09-07 |
| **FT-07** | `Passed` | yscb.py 薄宿主純路由派發通過，保留 init 特例與 private venv 注入 | 2026-09-07 |
| **FT-08** | `Passed` | 雙軌向後相容過渡層靜默退化調用 legacy process(args) 無 Warning 污染輸出 | 2026-09-07 |
| **FT-09** | `Passed` | core 與 server 先驅模組無殘留 process(args) 且精確命令函式完全就緒 | 2026-09-07 |
| **FT-10** | `Passed` | pre_cli_dispatch 與 post_cli_dispatch 對稱生命週期 Hook 正常廣播 | 2026-09-07 |
| **FT-11** | `Passed` | 同構遞迴指令樹走訪、子命令參數隔離與 SUBCOMMANDS 清單格式化驗證通過 | 2026-09-07 |
| **ET-01** | `Passed` | 未知指令返回退出碼 1 並提供 difflib 模糊建議 (如 stauts -> status) | 2026-09-07 |
| **ET-02** | `Passed` | 正交群組互斥選項衝突時清晰拋出 MutualExclusionError | 2026-09-07 |
| **ET-03** | `Passed` | 帶值 Option 缺少參數值時拋出 MissingValueError | 2026-09-07 |
| **ET-04** | `Passed` | Server Worker 通訊失敗時透明自動降級為本地冷派發 | 2026-09-07 |
| **ET-05** | `Passed` | 無精確函式亦無 process 接口時返回退出碼 127 (EC-05) | 2026-09-07 |
| **ET-06** | `Passed` | 重複宣告 module_alias 衝突時拋出模組別名衝突例外 (EC-06) | 2026-09-07 |
| **ET-07** | `Passed` | 非法 choice 傳參時攔截並提示可用候選列表 (EC-07) | 2026-09-07 |
| **ET-08** | `Passed` | 缺少必填 positional argument 時清晰攔截 (EC-08) | 2026-09-07 |
| **PT-01** | `Passed` | core.commands 模組載入耗時 < 1ms，派發解析延遲 < 0.1ms (NFR-01) | 2026-09-07 |
| **RT-01** | `Passed` | core (162/162 tests passed) 與 server (23/23 tests passed) 回歸 100% 通過 | 2026-09-07 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python yscb.py uri --help`、`python yscb.py uri resolve --help` 與 `python yscb.py config --help`，檢視格式化 CLI 說明、`AVAILABLE SUBCOMMANDS:` 清單與參數格式化提示（`<uri>`、`<module> [key]`）輸出是否清晰美觀 | `[測試通過]` | 開發者實機核驗通過 (2026-09-07)：SUBCOMMANDS 與選項渲染清晰符合預期 |
| **UX-02** | 實機執行 `python yscb.py uri resolve project://AGENTS.md`、`python yscb.py config get core project_root` 與 `python yscb.py server status`，驗證巢狀子指令派發、參數解析與執行結果正確 | `[測試通過]` | 開發者實機核驗通過 (2026-09-07)：巢狀子指令派發與底線函式執行無誤，回傳狀態正常 |

