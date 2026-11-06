# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：server 模組業務與測試代碼確定性優化 (server Deterministic Optimization)
> 建立日期：2026-11-06
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella
> 狀態：Completed
> 模型：Unknown
> 依據 P00：[P00_discuss.md](./P00_discuss.md)
> 模板版本：v1.0

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :---: | :--- | :--- | :---: | :---: |
| **FR-01** | `master.py` IPC 控制訊框、握手與 HTTP 分派去重 (`OPT-01~03`) | 提取 `_handle_worker_control_packet`、`_drain_worker_stderr`、`_read_worker_handshake`、`_emit_task_failure`、`_build_shutdown_summary` 與 `DispatcherHTTPHandler._parse_dispatch_request` / `_reject_bad_dispatch`。 | P1 | [P00:DR-01] |
| **FR-02** | `logger.py`、`service.py`、`streamer.py`、`watcher.py`、`worker.py`、`cli.py` 結構收斂 (`OPT-04~11`) | 提取 `_open_log_stream_locked`、`_resolve_service_root`、`_emit_log`、`_record_task_exception`、`_reconfigure_utf8_stream`、`_print_running_banner`、`_cleanup_stale_state_file`，清理死匯入與 `_last_flush_time` 並拉平巢狀迴圈。 | P1 | [P00:DR-01] |
| **FR-03** | 併發同步、生命週期與邊界防禦修復 (`FIX-01~10`) | `_last_active_time` 全路徑加鎖、`_current_task`/`_preempted_pids` 統一納入 `_worker_lock`、`_kill_worker_locked` 重置 `_worker_services`、前台 `_restarting` 等待 `_restart_thread`、`touch_activity` 統一節流鍵、`streamer` 保留交替順序與 `RLock`、`watcher` 掃描 `.dist-info/`、`config._parse_float` 防禦、`worker` `os.getcwd()` 防禦、`cli.stop` 強殺清理 `daemon.json`。 | P1 | [P00:DR-02] |
| **FR-04** | `test_server*.py` 測試套件純化與 0 `ResourceWarning` (`AUD-01~12`) | 實作 `_make_supervisor` 與 `_make_logger` LIFO 清理、真實檔案鎖驗證、IPC 隔離斷言、無條件 `/api/dispatch` 路徑正規化驗證、清零工單註解並補齊 56 項測試斷言。 | P1 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :---: | :--- | :--- |
| **EC-01** | 組態傳入 `bool`、`NaN`、`inf` 或負數 `idle_timeout_sec` | `_parse_float` 攔截並安全回退至 `DEFAULT_IDLE_TIMEOUT_SEC` 或 `DEFAULT_WORKER_ALIVE_TIMEOUT_SEC`。 |
| **EC-02** | `DebouncedIOStreamer` 單批次內交替寫入 `stdout`/`stderr` 且回呼重入 | `_flush_locked` 僅合併相鄰同串流區塊以保留時序，並以 `RLock` 防範重入死鎖。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :---: | :---: | :--- |
| **NFR-01** | 測試與資源純淨度 | 56 項單元測試於 `python3 -W default` 下 100% 通過且 `0 ResourceWarning`。 |
| **NFR-02** | 零工單註解 | 全模組 13 個 `.py` 檔案達成 0 工單/審計編號殘留。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **[!CAUTION] `InterProcessLock` 真實鎖檔驗證**：測試锁競爭時必須保留外層 `lock.acquire(blocking=False)` 以確保鎖檔存在於磁碟，不可在未建立鎖檔時移除鎖取得步驟。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

維持 `MasterSupervisor`、`WarmWorker`、`DebouncedIOStreamer`、`ModulesWatcher`、`ServiceManager`、`ServerLogger` 與 `ServerConfig` 原有架構拓撲，強化執行緒鎖保護邊界與內部輔助方法收斂。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
54: | :--- | :---: | :--- |
| `ys_codebase/source/server/server/config.py` | Modify | 新增 `_parse_float` 攔截 `bool`、`NaN`、`inf` 與非法負值 |
| `ys_codebase/source/server/server/logger.py` | Modify | 早退衛語句、提取 `_open_log_stream_locked`、複用 `get_expected_archive_path()` |
| `ys_codebase/source/server/server/master.py` | Modify | 提取 IPC/握手/HTTP 輔助方法，統一 `_activity_lock` 與 `_worker_lock` 併發保護，重置 `_worker_services` |
| `ys_codebase/source/server/server/service.py` | Modify | 提取 `_resolve_service_root` 並統一顯式/隱式 `yscb_root` 節流鍵，拉平 `load_from_contributes` |
| `ys_codebase/source/server/server/streamer.py` | Modify | 移除死狀態 `_last_flush_time`，改用 `RLock` 並保留 `stdout`/`stderr` 交替時序 |
| `ys_codebase/source/server/server/watcher.py` | Modify | 拉平 `_scan_modules_dir` 與 `_poll_loop` 並支援掃描 `.dist-info/` 目錄內檔案 |
| `ys_codebase/source/server/server/worker.py` | Modify | 提取 `_emit_log`、`_record_task_exception`、`_reconfigure_utf8_stream` 並防禦 `os.getcwd()` `OSError` |
| `ys_codebase/source/server/scripts/cli.py` | Modify | 提取 `_print_running_banner` 與 `_cleanup_stale_state_file`，於強殺路徑後清理孤兒 `daemon.json` |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 實作 `_make_supervisor` LIFO 清理、提取 `_load_server_cli`、純化並補強 38 項核心測試 |
| `ys_codebase/source/server/tests/test_server_config.py` | Modify | 清理死匯入、隔離暫存目錄並補強 `_parse_float` 與節流視窗等 9 項測試 |
| `ys_codebase/source/server/tests/test_server_logging.py` | Modify | 實作 `_make_logger` / `_make_supervisor` 清理並補強 FD 不可繼承與 inode 輪替等 9 項測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 鎖序與跨鎖競態消除**：`MasterSupervisor` 嚴守 `_dispatch_lock -> _worker_lock -> _activity_lock` 鎖序，將 `_current_task` 與 `_preempted_pids` 統一收攏於 `_worker_lock` 保護。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
def _parse_float(val: Any, default: float, allow_zero: bool = True) -> float: ...
def _resolve_service_root(yscb_root: Optional[str]) -> str: ...
def _reconfigure_utf8_stream(stream_obj: Any) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：維持所有對外 SDK（`BaseServiceWorker`, `ServiceManager`, `touch_activity`）與 CLI（`start`, `stop`, `status`, `reload`）Mode B 100% 向下相容。
- **階段決策紀錄**：[P03:DR-01] `WarmWorker._record_task_exception` 透過 `stop_capture: bool = False` 參數精確區分內層與外層異常捕獲時序。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- **需求對齊**：FR-01 ~ FR-04 與 EC-01 ~ EC-02 全數落實。
- **邊界防護**：通過盲眼子代理 B、D、E 驗證，P0=0, P1=0, P2=0, P3=0。
- **依賴純淨**：100% Python 標準庫實作。
- **靈魂拷問與防護解法**：
  - *問：`_kill_worker_locked` 清空 `self._worker_services = []` 是否會導致 `/api/shutdown` 的 `services_stopped` 統計歸零？*
  - *答*：`do_POST('/api/shutdown')` 先呼叫 `supervisor._build_shutdown_summary()` 取得快照，隨後才啟動背景執行緒呼叫 `supervisor.stop()`，故關閉摘要仍精確反映停機前運行的服務數。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **模組手冊** | `ys_codebase/source/server/README.md` | N/A | 內部確定性優化與併發防禦修復，無外部 CLI 語法變更 |
| **微觀註解** | `server` 源碼與測試檔 | Modify | 清零工單編號註解並同步更新 Docstring |

- **決策定稿**：**[P04:DR-01]** 通過五步盲眼閉環驗證（Loop 1 熔斷）並完成雲端受控 CoW 交付。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：完成 Loop 1 Step 1~2 盲眼子代理 A1/A2 初審與子代理 B1/B2 反向查證
- [x] **TASK-02**：完成 Loop 1 Step 3 子代理 C1 業務代碼重構 (`OPT-01~11`) 與子代理 C2 測試純化 (`AUD-01~12`)
- [x] **TASK-03**：完成 Loop 1 Step 4 盲眼子代理 D 驗收與子代理 Fix-02 併發/邏輯/防禦補丁 (`FIX-01~10`) 並同步至雲端
- [x] **TASK-04**：完成 Loop 1 Step 5 盲眼子代理 E 二次零錨定分析（P0=0, P1=0, P2=0, P3=0）並觸發熔斷結案

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
