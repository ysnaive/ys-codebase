# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_03_server_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `logger.py` 補齊 `import sys`、常數統一與純函式抽取 (`M-09`, `F-01`, `F-05`) | 1. 頂層匯入 `sys` 與 `shutil`，修復 `write_raw()` 於 `echo_console=True` 時之隱藏 `NameError`，並將 `except Exception` 收窄為 `except OSError`。<br/>2. 定義 `HEADER_TIME_REGEX` 與啟動橫幅寫入統一引用 `START_BANNER_PREFIX` 常數。<br/>3. 抽取無狀態純函式 `_extract_log_file_timestamp(filepath: str) -> str` 與 `_safe_replace_file(src: str, dst: str) -> None`，消除 3 處時間戳推導與 2 處安全搬移重複邏輯。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | `MasterSupervisor.start` 與 `worker_main` 資源釋放對稱保護 (`F-02`) | 1. `MasterSupervisor.start()` 取得 `daemon.lock` 後，將初始化環境、啟動 HTTP Server / Worker / Watcher 全程納入 `try...except Exception` 保護，若初始化失敗立即呼叫 `self.stop()` 釋放檔案鎖與資源並重新拋出例外。<br/>2. `worker.py:worker_main()` 於 `try` 區塊前預先初始化 `worker: Optional[WarmWorker] = None`，並在 `finally` 中檢查 `if worker is not None: worker.service_manager.stop_all()`，根除建構失敗時之 `UnboundLocalError`。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | `Mode A` 飢渴重匯出、殭屍參數、薄轉發與死代碼清除 (`M-01`~`M-05`, `M-10`, `M-11`) | 1. 清空 `server/__init__.py` 頂層飢渴重匯出與過時 `__version__ = "1.0.0"`，改為純套件門面 docstring。<br/>2. 物理移除 `ServerConfig.load(workspace_root)`、`MasterSupervisor.stop(force)`、`ServiceManager.stop_all(timeout_sec)` 三處未使用的殭屍參數並同步更新模組內呼叫點。<br/>3. 內聯並物理刪除 `MasterSupervisor._spawn_worker` 2 行薄轉發方法。<br/>4. 刪除 `WarmWorker._is_running` 死屬性與 `execute_task` 內冗餘死賦值 `cmd_name`/`sub_args`。<br/>5. 清除 `master.py`、`worker.py`、`service.py`、`streamer.py`、`watcher.py`、`scripts/cli.py` 頂部未引用之匯入。 | P0 | [P00:DR-01] |
| **FR-04** | `service.py` 與 `watcher.py` 舊版相容分支移除與純函式剝離 (`M-07`, `M-08`, `S2`) | 1. `service.py` 移除舊版 `contributes` Schema 鍵名 fallback（`provider`、`entry`、`id`、`code.func://`），僅保留正統 `__provider__`/`_provider`、`name`、`worker_class` 與 `code.class://`，並剝離無狀態類別載入純函式 `_load_service_class_from_uri(uri_str: str, provider: str)`。<br/>2. `watcher.py` 移除 `_notify_change` 針對 0 參數 callback 之 `inspect.signature` 反射與 `TypeError` 退避，直接呼叫 `self.on_change_callback(affected_modules)`；將 `_has_changed` 簡化為 `return prev != curr`，並剝離無狀態目錄掃描純函式 `_scan_modules_dir(modules_dir: str) -> Dict[str, float]`。 | P1 | [P00:DR-01], [P00:DR-02] |
| **FR-05** | `master.py` 與 `scripts/cli.py` 跨檔去重與共用純函式收斂 (`M-06`, `F-03`, `F-04`) | 1. 於 `master.py` 公開單一正統 `read_daemon_state(yscb_root: str) -> Optional[ServerDaemonState]`（`MasterSupervisor.read_state` 直接委派調用），物理刪除 `cli._read_daemon_state`。<br/>2. 於 `master.py` 抽取並公開共用純函式：`spawn_detached_master(yscb_root: str, idle_timeout_sec: float, enable_watcher: bool = True) -> int`、`build_fallback_status_payload(state: ServerDaemonState) -> Dict[str, Any]`、`format_uptime(uptime_sec: float) -> str` 與 `format_watcher_status(watcher: Dict[str, Any]) -> str`，消除 `master.py` 與 `scripts/cli.py` 間的 5 處重複邏輯。 | P1 | [P00:DR-01], [P00:DR-02] |
| **FR-06** | `master.py`、`worker.py`、`scripts/cli.py` 之 `S1` 業務階段拆解 (`F-03`, `F-06`) | 1. `MasterSupervisor.start` 拆解為 `_initialize_daemon_environment`、`_start_http_and_watcher_services`、`_run_supervisor_main_loop`；`dispatch_task` 拆解為 `_ensure_ready_worker` 與 `_stream_task_over_worker_pipe`；`DispatcherHTTPHandler` 抽取 `_send_json_response(status_code: int, payload: Dict[str, Any])`。<br/>2. `WarmWorker.execute_task` 拆解為 `_prepare_execution_env` 與 `_dispatch_command_with_captured_streams`。<br/>3. `scripts/cli.py:status` 拆解為 `_render_status_dashboard(info: Dict[str, Any], state: ServerDaemonState)`。 | P1 | [P00:DR-01], [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `MasterSupervisor.start()` 取得 `daemon.lock` 後於 HTTP 綁定或 Worker 啟動時拋出異常 | `try...except Exception` 捕獲異常並立即呼叫 `self.stop()` 釋放 `daemon.lock`、清理 `daemon.json` 與關閉 Logger，避免殘留死鎖，隨後向上重新拋出異常。 |
| **EC-02** | `worker_main()` 在 `WarmWorker()` 建構或 `pre_warm()` 階段拋出異常 | `worker` 變數已預先初始化為 `None`，`finally` 區塊安全檢查 `if worker is not None:` 後才呼叫 `worker.service_manager.stop_all()`，並始終還原 `sys.stdout = orig_stdout`。 |
| **EC-03** | 崩潰留存之舊日誌檔首行缺失或損毀啟動橫幅時間戳 | `_extract_log_file_timestamp` 優先透過正則提取 `START_BANNER_PREFIX` 時間戳，若失敗則退避讀取檔案 `os.path.getmtime`，若仍失敗則退避使用當前系統時間，確保歸檔絕不崩潰。 |
| **EC-04** | 跨檔案系統或 Windows 檔案控制代碼競爭導致 `os.rename` 歸檔失敗 | `_safe_replace_file` 捕獲 `OSError` 後自動退避為 `shutil.copy2` 複製加 `os.remove` 清理原檔。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 代碼精簡與去重 | 消除 `server` 模組內所有跨檔重複與殭屍代碼，全模組總行數相較基線淨減少，單一方法行數控制在清晰易讀範圍內。 |
| **NFR-02** | 零跨模組污染與邊界隔離 | 100% 限制於 `ys_codebase/source/server/` 目錄內修改，不引入任何第三方外部套件，並維持既有 CLI 與 HTTP 端點行為 100% 相容。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `worker_main` 執行期間會將全域 `sys.stdout` 重導向至 `sys.stderr`，以確保背景執行緒的 `print()` 不會污染 NDJSON IPC 管道；因此在 `finally` 區塊必須無條件還原 `sys.stdout = orig_stdout`。
- **`[!NOTE]`** `MasterSupervisor.start()` 若因 `daemon.lock` 已被其他活躍實例持有而提前返回（返回既有 PID 或 `0`），不得觸發 `self.stop()` 誤刪正在運行實例之鎖檔與狀態檔；僅在成功取得鎖之後的初始化失敗才執行 `self.stop()` 回滾。
