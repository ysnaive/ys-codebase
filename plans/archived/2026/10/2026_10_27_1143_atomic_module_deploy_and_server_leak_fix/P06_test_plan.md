# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：2026_10_27_1143_atomic_module_deploy_and_server_leak_fix  
> 建立日期：2026-10-27  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `MasterSupervisor.start()` 當 `daemon.lock` 已被持有且 `daemon.json` 尚未建立時，立即返回 `0` 且絕不穿透建立 HTTP Server 或 `WarmWorker`。 | FR-01, EC-01, NFR-02 | `python yscb.py dev test server -k test_master_start_lock_contention_never_falls_through` |
| **FT-02** | 單元測試 | 驗證 `MasterSupervisor.restart_server()` 並發多次呼叫時僅觸發單次 `spawn_detached`，且 `ModulesWatcher._is_core_transaction_locked()` 精準偵測 `.yscb.lock`。 | FR-02, FR-05, NFR-02 | `python yscb.py dev test server -k test_master_restart_server_reentrancy_guard_and_watcher_transaction_lock` |
| **FT-03** | 單元/邊界測試 | 驗證 `AtomicEngine._atomic_swap_dir` 執行 `.staging` 與目標目錄原子替換、異常時自動將 `.old` 回滾還原至目標目錄且零殘留，並驗證 `act_reload` 組態預剝離相容性。 | FR-03, EC-02, EC-03, EC-04, NFR-01 | `python yscb.py dev test core -k test_atomic_swap_dir_and_reload_staging_strip` |
| **FT-04** | 單元測試 | 驗證 `dispatcher.dispatch()` 執行 `core` 生命週期變異指令（`update`, `install`, `reload`, `restore` 等）時跳過 `_maybe_auto_spawn_server()`。 | FR-04, NFR-01 | `python yscb.py dev test core -k test_lifecycle_mutation_commands_skip_auto_spawn_server` |
| **RT-01** | 回歸測試 | 執行 `core` 與 `server` 靜態合規檢查與完整測試套件，確認 100% 通過無退化。 | FR-01 ~ FR-05, EC-01 ~ EC-04, NFR-01, NFR-02 | `python yscb.py dev check core && python yscb.py dev check server && python yscb.py dev test core -q && python yscb.py dev test server -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestServerModule.test_master_start_lock_contention_never_falls_through` 通過，驗證 `daemon.lock` 被佔用時 `start()` 返回 `0` 且 `mock_spawn` / `mock_http` 0 次呼叫。 | 2026-10-27 12:10 |
| **FT-02** | `Passed` | `TestServerModule.test_master_restart_server_reentrancy_guard_and_watcher_transaction_lock` 通過，連續 3 次 `restart_server()` 僅執行 1 次 `spawn_detached`，且 `.yscb.lock` 鎖定期間 `_is_core_transaction_locked()` 返回 `True`。 | 2026-10-27 12:10 |
| **FT-03** | `Passed` | `TestDistributionLifecycle.test_atomic_swap_dir_and_reload_staging_strip` 通過，正向切換為 `v2`、負向缺 staging 異常時自動將 `.old` 還原回 `target_dir` 且無 `.old_*`/`.staging_*` 殘留。 | 2026-10-27 12:10 |
| **FT-04** | `Passed` | `TestDistributionLifecycle.test_lifecycle_mutation_commands_skip_auto_spawn_server` 通過，`dispatch(["update"])` 未觸發 `_maybe_auto_spawn_server`。 | 2026-10-27 12:10 |
| **RT-01** | `Passed` | `dev check core` (PASSED)、`dev check server` (PASSED)、`dev test core -q` (192/192, 100.0% Passed)、`dev test server -q` (39/39, 100.0% Passed)，並完成 `core@build` 與 `server@build` 熱部署。 | 2026-10-27 12:10 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py update` 或 `python yscb.py reload` 時，驗證模組透過 `.staging_*` 原子替換更新，且後台不會衍生重複的 `yscb server` 進程或造成記憶體暴漲。 | `[跳過/免測]` | 開發者指示免測 |

