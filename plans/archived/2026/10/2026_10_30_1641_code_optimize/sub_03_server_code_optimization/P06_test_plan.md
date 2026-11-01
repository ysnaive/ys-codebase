# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_03_server_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `ServerLogger` 啟動橫幅、`echo_console=True` 主控台輸出無 `NameError`、滾動保留與崩潰恢復時間戳提取 | FR-01, EC-03, EC-04 | `python yscb.py dev test server -k TestServerLogging` |
| **FT-02** | 單元測試 | 驗證 `MasterSupervisor.start()` 啟動異常時自動觸發 `stop()` 釋放檔案鎖、`_spawn_worker_locked()` 交握失敗自動清理防管道競爭，以及 `worker_main()` 生命週期對稱清理 | FR-02, EC-01, EC-02 | `python yscb.py dev test server -k "test_master_start_lock or test_worker_and_master_zero_source"` |
| **FT-03** | 單元測試 | 驗證 `ServerConfig.load()` 簽名收斂後預設載入、字典覆蓋與 CLI 啟動覆蓋優先級正常 | FR-03, NFR-01 | `python yscb.py dev test server -k TestServerConfig` |
| **FT-04** | 單元測試 | 驗證 `ServiceManager` 動態載入 `contributes` 與 `ModulesWatcher` 內聯 `_scan_modules_dir` 後目錄變更偵測 | FR-04, NFR-02 | `python yscb.py dev test server -k "test_service_manager or test_modules_watcher"` |
| **FT-05** | 整合測試 | 驗證 `MasterSupervisor`、`scripts/cli.py` 與 `WarmWorker` 跨檔共用純函式、`vfs.read_json` 收斂與 `S1/S2` 階段拆解後全流程無損 | FR-05, FR-06, NFR-01, NFR-02 | `python yscb.py dev test server -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestServerLogging` 實機通過；`echo_console=True` 與滾動保留驗證無誤 (`Pass: 39(100.0%), Fail: 0`) | 2026-10-31 |
| **FT-02** | `Passed` | `MasterSupervisor.start()` 異常自動釋放鎖與 `worker_main()` 對稱清理實機通過 (`39/39 Passed`) | 2026-10-31 |
| **FT-03** | `Passed` | `TestServerConfig` 實機通過；`vfs.<io>` 遷移與組態覆蓋優先級正常 (`39/39 Passed`) | 2026-10-31 |
| **FT-04** | `Passed` | `ServiceManager` 與 `ModulesWatcher` 單元測試實機通過 (`39/39 Passed`) | 2026-10-31 |
| **FT-05** | `Passed` | `server@1.0.1.build` 打包安裝完成，`python yscb.py dev check server` (`PASSED`) 與 `python yscb.py dev test server -q` 全數通過 (`Pass: 39(100.0%), Fail: 0, Skip: 0`) | 2026-10-31 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 確認 `server` 模組 `Mode A` 死代碼清除、`logger.py` 缺陷修復與 `master.py`/`cli.py` 階段拆解成果及後續全系統整合測試 | `Pending` | 待驗收 |
