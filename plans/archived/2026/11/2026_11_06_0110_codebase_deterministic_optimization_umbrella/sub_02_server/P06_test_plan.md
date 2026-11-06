# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：server 模組業務與測試代碼確定性優化 (server Deterministic Optimization)
> 建立日期：2026-11-06
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella
> 狀態：Passed
> 模型：Unknown
> 模板版本：v1.4

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `master.py` IPC 控制訊框、握手、HTTP 分派去重與併發同步鎖（`_activity_lock`, `_worker_lock`, `_worker_services` 重置與前台 `_restart_thread` join） | FR-01, FR-03 | `test_server.py` (38 tests) |
| **FT-02** | 單元測試 | 驗證 `config._parse_float` 攔截 `bool`/`NaN`/`inf`/負數、`service.touch_activity` 統一節流鍵、`watcher` 掃描 `.dist-info/`、`worker` 防禦 `os.getcwd()` `OSError` 與 `cli.stop` 清理孤兒 `daemon.json` | FR-02, FR-03, EC-01 | `test_server_config.py` (9 tests) & `test_server.py` |
| **FT-03** | 單元測試 | 驗證 `DebouncedIOStreamer` 交替時序與 `RLock` 重入安全、`ServerLogger` FD 不可繼承與 inode 輪替，以及全套件 0 `ResourceWarning` 與 0 工單註解 | FR-02, FR-04, EC-02, NFR-01, NFR-02 | `test_server_logging.py` (9 tests) & 全模組測試 |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Ran 59 tests in 4.307s — OK (0 ResourceWarning)` | 2026-11-06 |
| **FT-02** | `Passed` | `Ran 59 tests in 4.307s — OK (0 ResourceWarning)` | 2026-11-06 |
| **FT-03** | `Passed` | `Ran 59 tests in 4.307s — OK (0 ResourceWarning)` | 2026-11-06 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 驗證 `server` 全量單元與合約測試（`59 / 59` 通過、`0 ResourceWarning`）、`Checker().check_module("server")`（`0 FAIL, 0 WARN`）與五步盲測閉環融斷結果 | `[測試通過]` | 經 Blind Subagents D / E 驗證通過 |
