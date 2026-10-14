# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_02_dev_and_server_reliability_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `dev create` 生成包含 `CmdBags`、`YSCBTestCase` 與四位版號的標準骨架 | FR-01, FR-03 | `python yscb.py dev test dev -k test_scaffold` |
| **FT-02** | 單元測試 | 驗證 `dev test -k <pattern>` 參數解析能正確篩選執行指定測試 | FR-02 | `python yscb.py dev test dev -k test_tester` |
| **FT-03** | 單元測試 | 驗證 `dev release-check --all` 能成功走訪所有模組並輸出預檢結果清冊 | FR-04 | `python yscb.py dev test dev -k test_releaser` |
| **FT-04** | 單元測試 | 驗證 `Checker` 當宣告 `commands.cmd` 時強制檢查具名葉節點函式且排除首行 Docstring | FR-05 | `python yscb.py dev test dev -k test_checker` |
| **FT-05** | 單元測試 | 驗證 `MasterSupervisor` 透過 `_dispatch_lock` 序列化 Worker IPC 且 Stderr 正常排空 | FR-06, FR-07 | `python yscb.py dev test server -k test_master` |
| **FT-06** | 單元測試 | 驗證 `WarmWorker` 透過 `ServiceManager` 託管服務且支援多層指令解析 | FR-08 | `python yscb.py dev test server -k test_worker` |
| **FT-07** | 單元測試 | 驗證 `ServerLogger` 歷史清理正則能正確匹配時間後綴日誌 | FR-09 | `python yscb.py dev test server -k test_server_logging` |
| **ET-01** | 邊界測試 | 驗證無 `commands.cmd` 宣告的最小化 Mock 模組在 `Checker` 下相容 `process` | EC-01 | `python yscb.py dev test dev -k test_checker` |
| **RT-01** | 全量回歸 | 驗證 `dev` 模組全套 134+ 單元測試 100% 通過 | NFR-02 | `python yscb.py dev test dev` |
| **RT-02** | 全量回歸 | 驗證 `server` 模組全套 35+ 單元測試 100% 通過 | NFR-02 | `python yscb.py dev test server` |
| **RT-03** | 生態系回歸 | 驗證全生態系 550+ 測試 100% 通過，0 失敗 0 警告 | NFR-02 | `python yscb.py dev test --all --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `PASS` | `test_scaffold` 測試通過，驗證微內核契約骨架與四位版號生成正常 | 2026-10-14 |
| **FT-02** | `PASS` | `test_tester` 測試通過，`-k` / `--pattern` 解析與精確篩選功能正常 | 2026-10-14 |
| **FT-03** | `PASS` | `test_releaser` 測試通過，`release-check --all` 批次清冊正常 | 2026-10-14 |
| **FT-04** | `PASS` | `test_checker` 測試通過，具名函式強制檢查與 docstring 排除正常 | 2026-10-14 |
| **FT-05** | `PASS` | `test_master` 測試通過，`_dispatch_lock` 互斥與 Stderr 排空安全穩定 | 2026-10-14 |
| **FT-06** | `PASS` | `test_worker` 測試通過，`ServiceManager` 託管與多層指令路由正常 | 2026-10-14 |
| **FT-07** | `PASS` | `test_server_logging` 測試通過，時間序號日誌滾動正則匹配正確 | 2026-10-14 |
| **ET-01** | `PASS` | `test_checker` Mock 相容通過，無 `commands.cmd` 時相容 `process` | 2026-10-14 |
| **RT-01** | `PASS` | `dev` 模組全量 88 測試全綠 (100.0% Ready) | 2026-10-14 |
| **RT-02** | `PASS` | `server` 模組全量 34 測試全綠 (100.0% Ready) | 2026-10-14 |
| **RT-03** | `PASS` | 全生態系 550 測試全綠 (Pass: 550 (100.0%), Fail: 0, Skip: 0) | 2026-10-14 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py dev test dev -k test_scaffold`，驗證僅執行 scaffold 相關測試 | `PASS` | 實機輸出：1 test passed in 0.077s，精確秒級篩選通過 |
| **UX-02** | 執行 `python yscb.py dev release-check --all`，確認能批次檢查全部 5 個模組且正常回傳 0 | `PASS` | 實機輸出：全 5 個模組（core, dev, server, knowledge-db, agents-workflow）均為 READY，全部 3 道 Gate 通過 |


