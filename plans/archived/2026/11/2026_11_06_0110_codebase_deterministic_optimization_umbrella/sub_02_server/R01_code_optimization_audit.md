# 技術調研與程式碼優化診斷報告 (Research & Code Optimization Audit)

> 調研主題：server 模組業務與測試代碼確定性優化審計 (server Optimization & Test Audit)
> 建立日期：2026-11-06
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella
> 調研狀態：Concluded
> 模型：Unknown
> 依據 P00：[P00_discuss.md](./P00_discuss.md)
> 模板版本：v1.1

---

## 1. 背景與調研目標 (Background & Objectives)

- **目標模組**：`ys_codebase/source/server/`（業務程式碼 9 檔、測試程式碼 4 檔）。
- **閉環進度**：完成 Loop 1 五步盲眼子代理閉環（`A1/A2 -> B1/B2 -> C1/C2 -> D -> Fix-02 -> E`），經盲眼子代理 E 二次零錨定審查判定 **P0=0, P1=0, P2=0, P3=0**，正式觸發熔斷結案。
- **原業務功能缺失分流**：依對齊後基準（僅功能缺失列入 `issue_report.md`，實作邏輯錯誤、併發問題與防禦疏失直接於計畫內修復），原 10 項併發/實作邏輯/防禦缺失已全數於本計畫修復並補齊測試，僅 1 項跨進程強殺日誌歸檔規格缺失登錄於 [issue_report.md](./issue_report.md)。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 目標 1：業務程式碼確定性優化與邏輯/併發修復清單 (`OPT-01 ~ OPT-11` + `FIX-01 ~ FIX-10`)

| 編號 | 目標檔案 | 優化與修復內容摘要 | 狀態 |
| :---: | :--- | :--- | :---: |
| **OPT-01** | `server/master.py` | 提取 `_handle_worker_control_packet`、`_drain_worker_stderr` 與 `_read_worker_handshake(self, proc, alive_event, ready_event)` 消除重複 IPC 控制處理與巢狀閉包。 | Completed |
| **OPT-02** | `server/master.py` | 提取 `DispatcherHTTPHandler._parse_dispatch_request` / `_reject_bad_dispatch` 與 `MasterSupervisor._build_shutdown_summary` 收斂 HTTP 請求驗證與私有屬性封裝。 | Completed |
| **OPT-03** | `server/master.py` | 提取靜態輔助方法 `_emit_task_failure` 統一 6 處失敗 `task_finish` 訊框組裝。 | Completed |
| **OPT-04~05** | `server/service.py` | 提取 `_resolve_service_root`、拉平 `touch_activity` 與 `load_from_contributes` 巢狀結構、簡化 `_load_service_class_from_uri`。 | Completed |
| **OPT-06** | `server/worker.py` | 提取 `_emit_log`、`_record_task_exception(..., stop_capture=...)` 與 `_reconfigure_utf8_stream`。 | Completed |
| **OPT-07** | `server/logger.py` | `_extract_log_file_timestamp` 早退衛語句、`archive_and_close` 複用 `get_expected_archive_path()`、提取 `_open_log_stream_locked`。 | Completed |
| **OPT-08** | `scripts/cli.py` | 提取 `_print_running_banner` 與 `_cleanup_stale_state_file` 消除重複啟動橫幅與孤兒狀態清理樣板。 | Completed |
| **OPT-09~11** | 全模組業務檔 | 清理死匯入與死狀態（`streamer._last_flush_time`）、提升安全頂層匯入、以 `continue` 早退衛語句拉平 `watcher.py`。 | Completed |
| **FIX-01~04** | `server/master.py` | `_last_active_time` 全路徑納入 `_activity_lock`；`_current_task` 與 `_preempted_pids` 統一納入 `_worker_lock`；`_kill_worker_locked` 重置 `_worker_services = []`；前台模式 `_restarting` 時 `join` `_restart_thread`。 | Completed |
| **FIX-05~10** | `config.py`, `service.py`, `streamer.py`, `watcher.py`, `worker.py`, `cli.py` | `_parse_float` 攔截 `bool`/`NaN`/`inf`/負數；`touch_activity` 統一節流鍵；`streamer` 保留 `stdout`/`stderr` 交替時序並改用 `RLock`；`watcher` 支援 `.dist-info/` 目錄內檔案；`worker` 防禦 `os.getcwd()` `OSError`；`cli.stop` 強殺後清理孤兒 `daemon.json`。 | Completed |

### 2.2 目標 2：測試程式碼純化與斷言補強清單 (`AUD-01 ~ AUD-12`)

| 編號 | 目標測試檔 | 純化與補強重點摘要 | 狀態 |
| :---: | :--- | :--- | :---: |
| **AUD-01~02** | `tests/test_server.py` | 以 `exit_called = threading.Event()` 取代脆弱 `sleep`；實作 `_make_supervisor` 依 LIFO 順序自動執行 `stop()` 與 `archive_and_close()`，消除全部 `ResourceWarning`。 | Completed |
| **AUD-03~06** | `tests/test_server.py` | 保留真實 `InterProcessLock` 磁碟鎖驗證、補測 `.modules/core` 缺 `manifest.json` 交易鎖、強化 `worker_main` IPC 隔離與 `read_daemon_state` 真實寫盤斷言、無條件執行 `/api/dispatch` 相對/父路徑 200 OK 驗證。 | Completed |
| **AUD-07~12** | 三檔測試套件 | 完整清理 `sys.modules` / `_MODULE_CACHE` / `_LAST_TOUCH_*`、提取 `_load_server_cli`、補齊 FD `os.get_inheritable` 與 `last_inode` 輪替斷言、清零工單編號註解，並補齊全部 10 項邏輯/併發修復之單元測試。 | Completed |

---

## 3. 結論 (Conclusion)

- 經盲測子代理 D 驗收與盲測子代理 E 二次零錨定審計，確認業務碼與測試碼皆達成 `P0 = 0, P1 = 0, P2 = 0, P3 = 0`（觸發融斷 `CIRCUIT BREAKER TRIGGERED`），全數單元與合約測試 100% 通過（`0 ResourceWarning`），`Checker().check_module("server")` 為 `0 FAIL, 0 WARN`。
