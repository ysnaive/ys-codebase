# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：全生態系模組 CLI 活躍執行合約遷移與向後相容過渡層徹底拔除  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 單元/整合 | 驗證 `dev` 模組 contributes commands schema 解析與精確命令函式接收 `CmdBags` 正常工作 | FR-01 | `python yscb.py dev test dev` |
| **FT-02** | 單元/整合 | 驗證 `knowledge-db` 模組 contributes commands schema 解析與精確命令函式接收 `CmdBags` 正常工作 | FR-02 | `python yscb.py dev test knowledge-db` |
| **FT-03** | 整合測試 | 驗證 `knowledge-db` 查詢/分析類指令（`search`, `status` 等）宣告 `server_compatible: true` 並經 HTTP IPC 熱派發成功 | FR-02 | `python yscb.py dev test server` |
| **FT-04** | 單元/整合 | 驗證 `agents-workflow` 模組 contributes commands 巢狀指令樹解析與 `plan` 純分支 Help 格式化輸出 | FR-03 | `python yscb.py dev test agents-workflow` |
| **FT-05** | 單元/整合 | 驗證 `agents-workflow` 巢狀子指令（`plan check`, `plan status` 等）正確派發至底線平鋪函式執行 | FR-03 | `python yscb.py dev test agents-workflow` |
| **FT-06** | 整合測試 | 驗證剛性守門（Hard Sunset Gate）：過渡層徹底拔除後，未定義精確函式之模組調用必拋出 EC-05 契約缺失錯誤（退出碼 127） | FR-05 | `python yscb.py dev test core` |
| **ET-01** | 邊界測試 | 驗證 `dev test` 正交選項互斥（如 `--quiet` 與 `--verbose`）時拋出互斥報錯並返回退出碼 1 | EC-02 | `python yscb.py dev test dev` |
| **ET-02** | 邊界測試 | 驗證 `knowledge-db search` 格式化正交選項（`--preview` 與 `--detail`）互斥時清晰阻斷並返回退出碼 1 | EC-03 | `python yscb.py dev test knowledge-db` |
| **ET-03** | 邊界測試 | 驗證 `agents-workflow plan archive` 缺少必填位置參數 `<plan_name>` 時拋出 MissingArgumentError | EC-04 | `python yscb.py dev test agents-workflow` |
| **RT-01** | 全量回歸 | 驗證全生態系 5 大模組（`core`, `server`, `dev`, `knowledge-db`, `agents-workflow`）400+ 測試 100% 通過 | NFR-01 | 全模組依序回歸測試 |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `dev` commands schema 解析正確，`op-test`/`op-mksb` 納管，83/83 案例通過 | 2026-09-07 11:48 |
| **FT-02** | `Passed` | `knowledge-db` contributes commands 宣告與 `CmdBags` 派發 144/144 案例通過 | 2026-09-07 11:50 |
| **FT-03** | `Passed` | `knowledge-db` server_compatible 唯讀指令熱派發通過，23/23 案例通過 | 2026-09-07 11:48 |
| **FT-04** | `Passed` | `agents-workflow` commands 巢狀指令樹解析正確，`plan --help` 輸出清晰 | 2026-09-07 11:43 |
| **FT-05** | `Passed` | `agents-workflow` 巢狀子指令派發至底線平鋪函式，74/74 案例通過 | 2026-09-07 11:53 |
| **FT-06** | `Passed` | Hard Sunset Gate 守門生效：`test_ft08_hard_sunset_ec05_enforcement` 斷言返回 127 (EC-05)，`core` 162/162 案例通過 | 2026-09-07 11:47 |
| **ET-01** | `Passed` | `dev test` 正交選項互斥校驗通過 | 2026-09-07 11:48 |
| **ET-02** | `Passed` | `knowledge-db search` 選項互斥與邊界防禦校驗通過 | 2026-09-07 11:50 |
| **ET-03** | `Passed` | `agents-workflow plan archive` 缺少必填參數阻斷校驗通過 | 2026-09-07 11:53 |
| **RT-01** | `Passed` | 全生態系 5 大模組回歸（`core` 162 + `server` 23 + `dev` 83 + `knowledge-db` 144 + `agents-workflow` 74 = 486 Total），100% 綠燈通過 | 2026-09-07 11:53 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python yscb.py dev --help`、`python yscb.py knowledge-db --help` 與 `python yscb.py agents-workflow --help`，檢視格式化 CLI 說明、SUBCOMMANDS 與參數提示是否美觀清晰 | `[測試通過]` | 開發者實機驗證 Help 說明、動態 [options] 與美觀格式無誤 |
| **UX-02** | 實機執行 `python yscb.py agents-workflow plan check` 與 `python yscb.py knowledge-db status`，驗證同構巢狀子指令派發與執行結果正確 | `[測試通過]` | 開發者實機驗證同構巢狀子指令、server 派發與背景自動喚醒無誤 |
