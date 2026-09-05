# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge_db_hot_reload_server_and_watcher  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `KnowledgeDBConfig` 正確載入 `enable_hot_reload_server` 與 `hot_reload_server_inactivity_timer_sec`，型態轉換防禦生效 | FR-01 | `test_config_loading_and_type_casting` |
| **FT-02** | 單元測試 | `HotReloadServer` PID 寫入 `cache://knowledge-db/daemon.pid`，包含 pid, start_time, version, log_file | FR-09 | `test_daemon_pid_lifecycle_and_location` |
| **FT-03** | 單元測試 | `HotReloadServer` 日誌寫入 `cache://knowledge-db/logs/`，滾動保留最多 3 份歷史檔案 | FR-10 | `test_daemon_log_rolling_retention` |
| **FT-04** | 整合測試 | Watcher 偵測檔案變更，防抖 500ms 後觸發增量更新並原子替換二進位快取 | FR-03, FR-04, FR-05 | `test_watcher_debounce_and_hot_patch` |
| **FT-05** | 整合測試 | 閒置時間超過 `inactivity_timer_sec`，Server 自動優雅退出並清理 PID | FR-06 | `test_inactivity_auto_shutdown` |
| **FT-06** | 整合測試 | 模組版本不符時，`ensure_running` 強制終止舊進程並重啟新進程 | FR-11 | `test_version_mismatch_restart` |
| **FT-07** | 單元測試 | `on_pre_cli_dispatch` 於 `enable_hot_reload_server=True` 時自動拉起 Server，耗時 $\le 10\text{ms}$ | FR-02 | `test_pre_cli_dispatch_hook_autostart` |
| **FT-08** | 整合測試 | CLI `knowledge-db daemon [start\|stop\|status]` 正確控制與回報 | FR-07 | `test_cli_daemon_commands` |
| **FT-09** | 邊界測試 | 殭屍 PID 殘留時自動清理並重啟 (EC-01)；信號中斷清理 (EC-05) | EC-01, EC-05 | `test_stale_pid_cleanup_and_signals` |
| **FT-10** | 邊界測試 | 密集連鎖檔案儲存時防抖重設，僅執行一次熱修補 (EC-02) | EC-02 | `test_burst_save_events_debounce` |
| **FT-11** | 回歸測試 | 第一軌 Standalone JIT 與原有 133 個全模組單元測試 100% 通過 | FR-08, NFR-04 | `python3 yscb.py dev test -m knowledge-db` |
| **FT-12** | 整合測試 | Watcher 監聽目錄由 SpaceManager 動態解算，空間簽名失配時自動重啟 | FR-03, FR-11, EC-09 | `test_dynamic_space_watching_and_signature_mismatch` |
| **FT-13** | 整合測試 | 運行 CLI 時若後台存在 server 則跳過 JIT 並輸出指定提示 | FR-12, EC-11 | `test_cli_jit_skip_notification_when_server_running` |
| **FT-14** | 整合測試 | Server 啟動時執行與 JIT 相同的離線變更預檢熱修補 | FR-13, EC-10 | `test_server_startup_offline_check` |
| **FT-15** | 單元測試 | 啟用 Server 時，config 中的 JIT 設定視為無效 (`resolve_jit_vector_timeout` 為 None) | FR-14 | `test_config_jit_disabled_when_server_enabled` |
| **FT-16** | 整合測試 | Contributes 驅動之副檔名動態解算與 Space exclude/pattern 動態過濾 (零硬編碼) | FR-15 | `test_contributes_driven_extensions_and_path_filter` |
| **FT-17** | 單元測試 | Core 組態軟合併於 local 層級時，若 project 已有對應設定則自動跳過 | FR-16 | `test_local_config_infill_skips_project_keys` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `PASSED` | 預設值、字串布林容錯與負數防禦解析通過 | 2026-09-05 11:17 |
| **FT-02** | `PASSED` | PID 檔案安全寫入 cache://knowledge-db/daemon.pid，Git 零污染 | 2026-09-05 11:17 |
| **FT-03** | `PASSED` | 日誌滾動機制驗證通過，5 份日誌自動清理保留最新 3 份 | 2026-09-05 11:17 |
| **FT-04** | `PASSED` | Watcher 變更過濾與 500ms 防抖熱修補驗證通過 | 2026-09-05 11:17 |
| **FT-05** | `PASSED` | 閒置時間逾時自動關閉 Server 邏輯驗證通過 | 2026-09-05 11:17 |
| **FT-06** | `PASSED` | 模組版本失配 (0.1.0 vs 1.0.1.22) 自動強制停止並重啟驗證通過 | 2026-09-05 11:17 |
| **FT-07** | `PASSED` | 沙盒隔離、禁用與啟用時 hook 自動拉起驗證通過 | 2026-09-05 11:17 |
| **FT-08** | `PASSED` | CLI daemon status (JSON) 與 stop 指令驗證通過 | 2026-09-05 11:17 |
| **FT-09** | `PASSED` | 殭屍 PID 自動清理探針驗證通過 | 2026-09-05 11:17 |
| **FT-10** | `PASSED` | Burst Events 連續密集變更防抖聚合驗證通過 | 2026-09-05 11:17 |
| **FT-11** | `PASSED` | 全生態系 147/147 (100.0%) 單元測試全數通過，Unknown: 0 | 2026-09-05 11:44 |
| **FT-12** | `PASSED` | SpaceManager 動態目錄解算與 spaces_signature 簽名失配重啟通過 | 2026-09-05 11:28 |
| **FT-13** | `PASSED` | CLI 探測後台 Server 跳過 JIT 並輸出 Hot reload server(pid:X) exist, skip JIT check 通過 | 2026-09-05 11:28 |
| **FT-14** | `PASSED` | Server 啟動時 _run_startup_check 離線變更增量補丁執行通過 | 2026-09-05 11:28 |
| **FT-15** | `PASSED` | 啟用 Server 時 JIT 設定邏輯與參數全面失效驗證通過 | 2026-09-05 11:28 |
| **FT-16** | `PASSED` | ParserRegistry 動態副檔名、Space file_patterns 結合與 exclude 雙軌過濾全數通過 | 2026-09-05 11:44 |
| **FT-17** | `PASSED` | 驗證 _deep_infill_dict 與 act_deploy_configs_from_modules 在 project 既有設定下 local 跳過覆蓋通過 | 2026-09-05 12:09 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 設定 `enable_hot_reload_server=true`，執行 `python yscb.py knowledge-db status` 驗證 hook 自動喚醒 Server，檢視 `cache://knowledge-db/daemon.pid` 與 logs | `[測試通過]` | 實機測試通過：成功以 Detached 背景啟動 (PID: 49488)，日誌與 PID 隔離寫入 cache:// |
| **UX-02** | 編輯 `docs/` 或源碼檔案，觀察 log file 輸出 500ms 防抖與 AST/BM25/Graph/Vector 即時熱更新 | `[測試通過]` | 實機測試通過：啟動即時預檢修補離線變更 (201.9ms)，Live 變更防抖 (1.6ms) 運作正常 |
| **UX-03** | 執行 `python yscb.py knowledge-db daemon stop` 驗證進程安全退出與 PID 清理 | `[測試通過]` | 實機測試通過：發送終止信號進程安全退出，PID 檔案自動清理 |
| **UX-04** | 後台運行 Server 時執行 `python yscb.py knowledge-db search "query"`，驗證 stderr 輸出 `Hot reload server(pid:<pid>) exist, skip JIT check.` 且跳過 JIT 檢查 | `[測試通過]` | 實機測試通過：精確向 stderr 輸出指定提示，跳過 JIT 檢查，--json 輸出純淨解析無誤 |
