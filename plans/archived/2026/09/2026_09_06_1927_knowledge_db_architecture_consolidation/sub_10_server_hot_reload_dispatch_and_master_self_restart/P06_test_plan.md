# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_10_server_hot_reload_dispatch_and_master_self_restart  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `ModulesWatcher` 精確解析變更路徑所屬模組名稱，且支援無參/有參回調向下相容 | FR-01 | `python yscb.py dev test --target=server:TestServerModule.test_modules_watcher_affected_modules` |
| **FT-02** | 整合測試 | 非 server 模組變更時，觸發 `restart_worker`，Master PID 維持不變而 Worker PID 更新 | FR-02 | `python yscb.py dev test --target=server:TestServerModule.test_watcher_reload_dispatch_worker` |
| **FT-03** | 整合測試 | server/core 模組變更時，觸發 `restart_server` 分流調用 | FR-02, FR-03 | `python yscb.py dev test --target=server:TestServerModule.test_watcher_reload_dispatch_server` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `PASSED` | `ModulesWatcher` 提取變動模組為 `knowledge-db`，回調傳參正確執行無誤 | 2026-09-07 08:16 |
| **FT-02** | `PASSED` | 傳入 `{"knowledge-db", "dev"}` 正確觸發 `restart_worker` 且未調用 `restart_server` | 2026-09-07 08:16 |
| **FT-03** | `PASSED` | 傳入 `{"server"}` 與 `{"core", "knowledge-db"}` 皆正確觸發 `restart_server` 分流 | 2026-09-07 08:16 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於運行端執行 `touch ys_codebase/.modules/server/manifest.json`，Server Daemon 自動重啟整個 Master (Master PID 更新) | `[跳過/免測]` | 開發者明確指示免測 |
