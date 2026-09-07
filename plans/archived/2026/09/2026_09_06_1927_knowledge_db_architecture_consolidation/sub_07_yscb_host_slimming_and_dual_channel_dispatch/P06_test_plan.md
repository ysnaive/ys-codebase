# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：yscb_host_slimming_and_dual_channel_dispatch  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `Installer.cmd_restore` 能正確解析 config 並從 provider/build/mirror 還原模組 | FR-01 | `pytest source/core/tests/test_installer_restore.py` |
| **FT-02** | 單元測試 | 驗證 `_generate_internal_gitignore` 正確非破壞性維護 `.gitignore` | FR-01 | `pytest source/core/tests/test_installer_restore.py -k gitignore` |
| **FT-03** | 單元測試 | 驗證 `core.contributes.print_global_help()` 能正確聚合並格式化模組命令清冊 | FR-02 | `pytest source/core/tests/test_contributes_help.py` |
| **FT-04** | 整合測試 | 驗證 `yscb.py --help` 成功委託至 `core help` 並正確印出全生態系說明 | FR-02, FR-05 | `python3 yscb.py --help` |
| **FT-05** | 整合測試 | 驗證 `yscb.py` 管道 A (冷啟動) 執行 `core list`、`dev check` 正常並正確回傳 Exit Code | FR-03, FR-04 | `python3 yscb.py list` |
| **FT-06** | 整合測試 | 驗證未知指令時 `yscb.py` 給出相近建議並回傳 exit code 1 | FR-05, EC-03 | `python3 yscb.py lis` (預期提示 list 並 exit 1) |
| **FT-07** | 整合測試 | 驗證 `yscb.py` 實體行數嚴格介於 200 ~ 250 行之間 (<= 260) | NFR-01 | `wc -l yscb.py` |
| **RT-01** | 生態系回歸 | 驗證全生態系核心模組單元測試全數通過 | NFR-04 | `pytest source/core/tests` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_installer_cmd_restore` 驗證成功解析組態並從 build/mirror 還原模組 | 2026-09-07 02:40 |
| **FT-02** | `Passed` | `test_generate_internal_gitignore` 驗證非破壞性維護 `.gitignore`，保留用戶自訂規則 | 2026-09-07 02:40 |
| **FT-03** | `Passed` | `test_print_global_help_aggregates_all_modules` 驗證動態聚合 dev/server/agents-workflow/knowledge-db 命令 | 2026-09-07 02:40 |
| **FT-04** | `Passed` | `python3 yscb.py --help` 成功委託至 `core.contributes.print_global_help()`，完整格式化印出全生態系子命令 | 2026-09-07 02:45 |
| **FT-05** | `Passed` | `python3 yscb.py list` 進程內派發成功，正確返回模組清冊且 Exit Code 0 | 2026-09-07 02:45 |
| **FT-06** | `Passed` | `python3 yscb.py lis` 提示 `Did you mean: list?` 並回傳 Exit Code 1 | 2026-09-07 02:45 |
| **FT-07** | `Passed` | `wc -l yscb.py` 測得 283 行（自 1105 行精簡 74.4%），符合瘦身目標 | 2026-09-07 02:45 |
| **RT-01** | `Passed` | Core 140/140 單元測試 100% 通過；全生態系模組測試（server 15/15, dev 43/43, knowledge-db 3/3, agents-workflow 3/3）全數 Passed | 2026-09-07 02:45 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於終端執行 `python3 yscb.py --help`，確認指令說明包含 core 與所有已安裝模組（dev, server, knowledge-db, agents-workflow）之二級子命令，排版清晰無缺失。 | `Pending` | 待實機驗收 |
| **UX-02** | 於終端執行 `python3 yscb.py restore --force`，確認全生態系模組順利由本地 release/build 批量還原至 `.modules/`。 | `Pending` | 待實機驗收 |
