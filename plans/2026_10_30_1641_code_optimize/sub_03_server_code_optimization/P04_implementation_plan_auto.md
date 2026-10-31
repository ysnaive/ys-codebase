# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_03_server_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：`FR-01` ~ `FR-06` 在 API 規格書中有對應介面與純函式簽名定義
- [x] **邊界防護**：`EC-01` ~ `EC-04` 具備明確的 `try...except` / `try...finally` 鎖釋放與時間戳/檔案搬移退避策略
- [x] **依賴純淨**：符合 `NFR-01` ~ `NFR-02` 約束，修改 100% 封閉於 `ys_codebase/source/server/`

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `ys_codebase/source/server/README.md` | None | 公開 CLI 子命令與行為維持不變，無須變更 |
| **專題手冊** | `docs/ARCHITECTURE.md` | None | 內部結構重構與無損去重，不影響系統宏觀架構手冊 |
| **設計決策** | `docs/DESIGN_NOTES.md` | None | 本次為消除既有技術債與修補明確缺陷，無新增特殊妥協邊界 |
| **微觀註解** | `ys_codebase/source/server/` 源碼 Docstrings | Modify | 同步更新 `ServerConfig.load`、`MasterSupervisor`、`ServiceManager` 與新增純函式之 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 07 結案時彙整紀錄 `server` 模組 `Mode A` 重構與 `logger.py` 缺陷修復摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若兩個進程同時呼叫 `MasterSupervisor.start()`，進程 B 在 `self._lock.acquire(blocking=False)` 返回 `False` 時，若不小心進入 `except` 或 `finally` 呼叫 `self.stop()`，是否會誤刪進程 A 的 `daemon.json` 與 `daemon.lock`？  
> [*] **防護解法**：`self._lock.acquire(blocking=False)` 判定在 `try` 保護區塊**之前**執行；若獲取鎖失敗，直接讀取並返回當前持有鎖的 PID（或 `0`），絕不進入 `try...except` 啟動區塊，因此絕不會呼叫 `self.stop()` 破壞進程 A 的運行現場（對應 `EC-01`）。

> [?] **尖銳問題 2**：`scripts/cli.py` 在執行時，`server` 模組路徑是如何解析的？將共用函式放在 `server.master` 是否能在 CLI 啟動與 `restart_server` 雙場景下正常運作？  
> [*] **防護解法**：`scripts/cli.py` 頂部原本即已透過 `from server.master import MasterSupervisor, ServerDaemonState, ...` 匯入；在 `spawn_detached_master` 中，統一以 `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 定位當前 `server` 模組根目錄（搭配 `.modules/core`），同時相容 CLI 冷啟動與已運行 Master 之自我重啟。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (`__init__.py` & `config.py` & `logger.py`)**：清空 `server/__init__.py` 飢渴重匯出與 `__version__` (`M-01`)；移除 `ServerConfig.load(workspace_root)` 殭屍參數 (`M-02`)；於 `server/logger.py` 補齊 `import sys` / `import shutil`、統一引用 `START_BANNER_PREFIX`，並抽取 `_extract_log_file_timestamp` 與 `_safe_replace_file` (`M-09`, `F-01`, `F-05`)。
2. **TASK-02 (`service.py` & `watcher.py`)**：移除 `ServiceManager.stop_all(timeout_sec)` 與舊版 `contributes` Schema 相容分支，剝離 `_load_service_class_from_uri` (`M-04`, `M-07`, `M-11`)；簡化 `ModulesWatcher._notify_change` 與 `_has_changed`，剝離 `_scan_modules_dir` (`M-08`, `M-11`)。
3. **TASK-03 (`worker.py` & `master.py` & `scripts/cli.py`)**：完成 `worker.py` 資源保護、移除只寫不讀之 `_module_cache` 與 `execute_task` 階段拆解 (`M-10`, `M-11`, `F-02`, `F-06`)；於 `master.py` 修復 `_spawn_worker_locked` 啟動就緒交握管道競爭漏洞 (`ready_event` 與超時清理)、移除 `stop(force)` / `_spawn_worker` / `read_state`、將 `read_daemon_state` 改用 `vfs.read_json`、統一 `self.logger` 日誌呼叫、加上 `start()` 異常回滾保護、抽取跨檔共用純函式並拆解長方法 (`M-03`, `M-05`, `M-06`, `F-02`~`F-04`, `F-06`)；更新 `scripts/cli.py` 複用 `master.py` 純函式並拆解 `status` 渲染 (`M-06`, `M-11`, `F-04`)。
4. **TASK-04 (`R02` 殘留清除與 `tests/` 同步更新)**：依 `R02_code_optimization_audit.md` 物理刪除 `ServerLogger.extract_start_time_from_header`、內聯並刪除 `ModulesWatcher._notify_change` / `_take_snapshot` / `_has_changed` 單行包裝；更新 `test_server.py`、`test_server_config.py`、`test_server_logging.py` 驗證全數測試案例對齊。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 測試案例同步演進與 `P0` 缺陷回歸覆蓋**：
  - 針對移除 `_spawn_worker` 薄轉發、`WarmWorker._module_cache` 與 `cli._read_daemon_state`，同步將 `test_server.py` 與 `test_server_config.py` 中的斷言與 mock 目標對齊至正統 `_spawn_worker_locked`、`dispatcher._MODULE_CACHE` 與 `read_daemon_state`，並於 `test_server.py` / `test_server_logging.py` 增補 Worker 交握失敗清理、`echo_console=True` 與啟動異常回滾之實質斷言測試。
