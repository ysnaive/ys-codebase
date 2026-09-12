# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：server_console_config  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Passed  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `ServerConfig` 預設值檢驗（`enable_console == False`） | FR-01 | `python yscb.py dev test --target=server:TestServerConfig.test_default_config` |
| **FT-02** | 單元測試 | `ServerConfig.load()` 支援字典與 `core.config` 覆蓋（含字串 `"true"` 寬鬆轉型） | FR-01, EC-02 | `python yscb.py dev test --target=server:TestServerConfig.test_config_override_and_type_defense` |
| **FT-03** | 單元測試 | `_resolve_enable_console` 優先級：CLI `--console` 強制回傳 `True`（覆蓋 config False） | FR-02, FR-03 | `python yscb.py dev test --target=server:TestServerConfig.test_cli_console_override` |
| **FT-04** | 單元測試 | `_resolve_enable_console` 優先級：CLI `--daemon` 強制回傳 `False`（覆蓋 config True） | FR-02, FR-03 | `python yscb.py dev test --target=server:TestServerConfig.test_cli_daemon_override` |
| **FT-05** | 單元測試 | `_resolve_enable_console` 在無 CLI 參數時精確回退至 config 設定值（True/False） | FR-02 | `python yscb.py dev test --target=server:TestServerConfig.test_config_fallback_when_no_cli_args` |
| **FT-06** | 回歸測試 | `server` 全套既有單元與契約測試 100% 通過 | FR-04, FR-05 | `python yscb.py dev test server --quiet` |
| **FT-07** | 靜態合規 | `server` 模組通過微內核 `dev check server` 合規檢驗 | NFR-01 | `python yscb.py dev check server` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 驗證 `ServerConfig` 預設常數與類別屬性為 `enable_console=False`, `idle_timeout_sec=900.0` | 2026-09-07 02:13 |
| **FT-02** | `Passed` | 驗證 override_dict 與 `core.config` 雙層覆蓋及 `"true"`/`"1"`/`"yes"` 寬鬆型別防禦解析 | 2026-09-07 02:13 |
| **FT-03** | `Passed` | 驗證 CLI `--console` 強制覆蓋組態並確保 `_resolve_enable_console` 恆回傳 `True` | 2026-09-07 02:13 |
| **FT-04** | `Passed` | 驗證 CLI `--daemon` 強制覆蓋組態並確保 `_resolve_enable_console` 恆回傳 `False` | 2026-09-07 02:13 |
| **FT-05** | `Passed` | 驗證未指定 CLI 旗標時精確回退讀取設定檔之 `enable_console` 布林值 | 2026-09-07 02:13 |
| **FT-06** | `Passed` | `server` 模組 16/16 測試 PASSED (100.0%)，既有 Streamer/Worker/Watcher/Master 零回歸 | 2026-09-07 02:13 |
| **FT-07** | `Passed` | `dev check server` 模組合規性 100% 通過，符合微內核架構規範 | 2026-09-07 02:13 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py server start --help`，確認參數說明標明 `--console` 為除錯附加項且預設以設定檔為準 | `[跳過/免測]` | 開發者指示免測 (2026-09-07) |
