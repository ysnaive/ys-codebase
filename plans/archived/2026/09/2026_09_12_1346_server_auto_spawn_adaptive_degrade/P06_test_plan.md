# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Server 自動喚醒環境自適應降級與 Agents 導引提示 (Server Auto Spawn Adaptive Degrade & Agent Guidance)  
> 建立日期：2026-09-12  
> 所屬主計畫：無  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `can_spawn_background_daemon()` 探針檢測與記憶體快取行為 | FR-01 | `python yscb.py dev test core -k test_can_spawn_background_daemon` |
| **FT-02** | 單元測試 | 驗證 `ServerConfig` 正確解析 `auto_spawn` 預設值 (True) 與顯式配置 | FR-02 | `python yscb.py dev test server -k test_auto_spawn_config` |
| **FT-03** | 單元測試 | 驗證 `auto_spawn: false` 時 `_maybe_auto_spawn_server` 靜默跳過無輸出 | EC-01 | `python yscb.py dev test core -k test_maybe_auto_spawn_auto_spawn_disabled` |
| **FT-04** | 單元測試 | 驗證探針判定 False 時 `_maybe_auto_spawn_server` 輸出 stderr 警告與 Agent 指引 | FR-03 | `python yscb.py dev test core -k test_maybe_auto_spawn_degrade_warning` |
| **FT-05** | 單元測試 | 驗證 stderr 警告具備單次進程防洗頻抑制 (Debounce) 機制 | FR-04 | `python yscb.py dev test core -k test_maybe_auto_spawn_warning_debounce` |
| **RT-01** | 回歸測試 | Core 模組全套回歸測試 100% 通過 | NFR-01 | `python yscb.py dev test core` |
| **RT-02** | 回歸測試 | Server 模組全套回歸測試 100% 通過 | NFR-03 | `python yscb.py dev test server` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_can_spawn_background_daemon` 探針與記憶體快取測試通過 | 2026-09-12 13:53 |
| **FT-02** | `Passed` | `test_auto_spawn_config` 預設 True 與覆蓋防禦轉型測試通過 | 2026-09-12 13:53 |
| **FT-03** | `Passed` | `test_ft11_maybe_auto_spawn_server_auto_spawn_disabled` 靜默跳過測試通過 | 2026-09-12 13:53 |
| **FT-04** | `Passed` | `test_ft12_maybe_auto_spawn_server_probe_false_warning` 輸出 stderr 警告與 Agent 指引測試通過 | 2026-09-12 13:53 |
| **FT-05** | `Passed` | `test_ft13_maybe_auto_spawn_server_warning_debounce` 單進程防洗頻抑制測試通過 | 2026-09-12 13:53 |
| **RT-01** | `Passed` | `dev test core` 180/180 全數通過 (36.53s, 0 Failed, 0 Skipped) | 2026-09-12 13:53 |
| **RT-02** | `Passed` | `dev test server` 32/32 全數通過 (3.47s, 0 Failed, 0 Skipped) | 2026-09-12 13:53 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 在 IDE Agent 沙盒環境下執行 CLI 指令（如 `python yscb.py uri list`），驗證 `stderr` 輸出自適應降級警告與 IDE Agent 常駐指引，且功能正常回傳 0。 | `[測試通過]` | 開發者實機驗收通過 |
