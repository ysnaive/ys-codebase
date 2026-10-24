# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_03_server_hosting_ipc_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `ServiceManager` SDK 驅動服務載入、連字號模組注入與 `auto_start` 控制 (`S-01`, `S-02`) | 於 `server/service.py` 補齊 `import os`；`load_from_contributes(yscb_root)` 優先透過 `core.contributes.get("server", "services", default=[])` 載入並溯源 `__provider__`；於 `_load_service_item` 匯入前強制將 `.modules/<provider>` 注入 `sys.path`，雙向相容 `worker_class`/`entry` 與 `name`/`id`、支援 `code.class://` / `code.func://` 協議頭與連字號模組名正規化；`start_all` 嚴格遵循 `auto_start` 屬性；對齊 `README.md` 與 `contributes/_format.json`。 | P0 | [P00:DR-01] |
| **FR-02** | `worker_main` 私有 `_ipc_stdout` 硬隔離、寫入鎖與兩階段優雅停機握手 (`S-03`) | `worker_main` 進入時保存 `orig_stdout = sys.stdout` 與 `ipc_out = out_stream or orig_stdout`，將全域 `sys.stdout` 重導向至 `sys.stderr`（`finally` 還原），並以 `ipc_lock = threading.Lock()` 保護 `emit_fn` 寫入；`MasterSupervisor._kill_worker_locked` 先向 `proc.stdin` 發送 `{"action": "exit"}\n` 並 `proc.wait(timeout=min(timeout_sec, 1.5))` 等待 `stop_all()` 完成，逾時才兜底呼叫 `kill_process_tree`。 | P0 | [P00:DR-02] |
| **FR-03** | Master `start_time` 持久化修正與冗餘 `ServiceManager` 清理 (`S-04`) | 修正 `MasterSupervisor._write_state()` 傳入 `start_time=self._start_time`，確保 Worker 重啟或派發任務時不重置 Master Uptime；移除 Master 上未使用的 `self.service_manager` 實例與回退引用。 | P0 | 原始意圖 3 |
| **FR-04** | `.modules/` 運行時剛性邊界對齊與 `source/` 路徑注入清除 (`S-05`) | 自 `server/master.py:_spawn_worker_locked()` 與 `server/worker.py` 移除所有 `source/`、`source/core`、`source/server` 之 `PYTHONPATH` 與 `sys.path` 注入，僅保留 `.modules/` 運行時空間與 `.venv` `site-packages`。 | P0 | 原始意圖 3 |
| **FR-05** | 生命週期事件宣告、Reload 組態熱刷新與死代碼清除 (`S-06`, `S-07`) | 於 `contributes/core.json` 補齊 `events` 清冊（`server_worker_warming`、`server_worker_ready`），移除 `worker.py:pre_warm()` 舊版重複 `worker_warming` 廣播；`MasterSupervisor.restart_worker()` 同步呼叫 `ServerConfig.load()` 刷新 `self.idle_timeout_sec`；自 `scripts/cli.py` 刪除已廢棄之 `_handle_start()` 死代碼。 | P0 | 原始意圖 3 |
| **FR-06** | 測試集 4 檔 $\to$ 3 檔收斂與「自寫自驗」測試實質重寫 (`ST-01` ~ `ST-03`) | 物理刪除空殼 `tests/test_basic.py`，收斂為 `test_server.py`、`test_server_config.py`、`test_server_logging.py` 3 檔；合併同檔重複測試、移除 `_handle_start` 舊呼叫與靜態 `manifest.json` 字面檢查；將 `test_worker_ipc_logging_stream` 與 `test_watcher_observability_status_payload` 重寫為真實呼叫 `sup.dispatch_task()` 與 `sup.get_status_dict()`。 | P0 | 原始意圖 4 |
| **FR-07** | 4 大高風險路徑（服務託管、IPC 隔離、HTTP 全端點、CLI `CmdBags`）回歸補盲 (`ST-04`) | 補齊 `ServiceManager.load_from_contributes`（含連字號模組與 `auto_start: true/false`）、`worker_main` `out_stream=None` 實機重導向與 `exit` 握手、`POST /api/dispatch`（含 `400` 攔截）/ `/api/reload` / `/api/shutdown` 全端點、以及 `scripts/cli.py` 四大指令 `CmdBags` 單元與整合測試。 | P0 | [P00:DR-01], [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 外部模組以連字號命名（如 `knowledge-db`）且服務宣告使用 `code.class://knowledge-db/service:KnowledgeDBServiceWorker` | `_load_service_item` 先將 `.modules/<provider>` 注入 `sys.path`，剝除 `code.class://` 並將模組路徑首段 `-` 轉為 `_`（`knowledge_db.service`），確保跨模組服務類別 100% 成功匯入且不拋出 `ModuleNotFoundError`。 |
| **EC-02** | 服務宣告設定 `"auto_start": false` | `ServiceManager.load_from_contributes` 正常完成註冊並記錄元數據，但 `start_all()` 略過啟動該服務，其 `get_status()` 中 `alive` 為 `False`。 |
| **EC-03** | 背景服務執行緒在非任務執行期間或任務期間直接呼叫 `print("noise")` 寫入標準輸出 | 因 `worker_main` 將全域 `sys.stdout` 重導向至 `sys.stderr` 且僅透過 `ipc_lock` 保護之私有 `ipc_out` 寫出 NDJSON，所有非結構化雜訊均導向 `stderr`（由 Master `_drain_stderr` 收錄），`ipc_out` 維持 100% 純淨 JSON Lines。 |
| **EC-04** | Worker 子進程在收到 `{"action": "exit"}` 後僵死或超過 `1.5s` 仍未退出 | `MasterSupervisor._kill_worker_locked` 於 `proc.wait(timeout=min(timeout_sec, 1.5))` 拋出 `TimeoutExpired` 時，自動降級呼叫 `kill_process_tree(proc.pid)` 強制終止進程樹並關閉 `stdin/stdout/stderr` 管道。 |
| **EC-05** | `POST /api/dispatch` 收到與 Master 當前 `yscb_root` 不一致之請求，或 `server start --ttl -5` 傳入非法負數 | `/api/dispatch` 立即攔截並回傳 HTTP `400 Workspace Root Mismatch`；`scripts/cli.py:start` 攔截 `ttl <= 0` 輸出錯誤並回傳退出碼 `1`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 架構純淨度與執行緒安全 | 100% 遵循 `.modules/` 運行時剛性隔離（零 `source/` 路徑注入），`emit_fn` 具備 `threading.Lock` 保護無並發交錯。 |
| **NFR-02** | 測試速度與零孤兒進程 | `server/tests/` 收斂為 3 個子系統測試檔，`ModulesWatcher` 測試輪詢間隔壓縮至 `0.02s`，全套測試 100% 通過且測試後零殘留背景進程或暫存目錄。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** 遵循 `docs/server/DESIGN_NOTES.md` 之 `[DN-01]`～`[DN-04]`：嚴禁移除 `module == "server"` 自循環熱派發旁路、嚴禁繞過 `can_spawn_background_daemon()` 探針、嚴禁移除 `proc.stderr` 背景排空執行緒與 `_dispatch_lock`，且必須原字保留 `[Server] Daemon successfully started!` 與 `[Server] Daemon stopped gracefully.` 自動化契約錨點字串。
- **`[P01:DR-01]`** **`worker_main` 隔離測試防假陽性契約**：測試 `worker_main` 之 `stdout` 隔離時，強制以 `out_stream=None` 搭配 `patch.object(sys, "stdout", ...)` 進行驗證，確保真實覆蓋子進程預設串流重導向邏輯。

