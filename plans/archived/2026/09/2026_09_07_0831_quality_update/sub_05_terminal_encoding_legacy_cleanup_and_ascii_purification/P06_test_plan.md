# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：終端編碼防護、舊版殘留清理、特殊字元徹底捨棄與測試狀態閉環 (sub_05)  
> 建立日期：2026-09-12  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `HelpRenderer` 輸出純文字 `[SAFE]`, `[CONDITIONAL]`, `[GATED]` 且不含任何 Emoji | FR-01 | `dev test core -k TestContributesHelp` |
| **FT-02** | 整合測試 | 驗證在 Windows CP950 Console 下執行 `--help` 零報錯、正常輸出 | FR-02 | `python yscb.py dev release-check --help` |
| **FT-03** | 靜態檢核 | 驗證 `dev check --all` 5 大模組 0 Failed / 0 Warning | FR-03, FR-04 | `python yscb.py dev check --all` |
| **FT-04** | 回歸測試 | 驗證 `dev test --all` 全量 511 測試 100% Passed (0 Failed, 0 Unknown) | FR-05 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `HelpRenderer` 輸出純文字 `[SAFE]`, `[CONDITIONAL]`, `[GATED]` 斷言通過 | 2026-09-12 |
| **FT-02** | `Passed` | Windows CP950 Console 下執行 `--help` 輸出正常無報錯 | 2026-09-12 |
| **FT-03** | `Passed` | `dev check --all` 5 大模組 5 Passed / 0 Failed / 0 Warning | 2026-09-12 |
| **FT-04** | `Passed` | `dev test --all` 511 測試 100% Passed (511 Passed, 0 Failed, 0 Unknown) | 2026-09-12 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於 Windows 終端執行 `python yscb.py dev release-check --help`，確認結構化說明輸出流暢且無 Emoji / 特殊字元編碼異常 | `[跳過/免測]` | 開發者指示免測 (2026-09-12) |
| **UX-02** | 執行 `python yscb.py dev check --all`，確認全生態系 5 大模組 0 Failed, 0 Warning | `[跳過/免測]` | 開發者指示免測 (2026-09-12) |
