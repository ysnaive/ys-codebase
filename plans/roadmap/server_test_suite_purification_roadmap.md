# 技術路線圖：Server 測試集純化、自寫自驗修復與 IPC／服務託管路徑補盲 (`server_test_suite_purification_roadmap`) (Roadmap)

> 主題：Server 測試集純化、自寫自驗修復與 IPC／服務託管路徑補盲 (`server_test_suite_purification_roadmap`)  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
對 `ys-codebase / module:server`（`v1.0.0.4`）下的 `tests/` 目錄（共 **4 個測試檔案、30 個 `test_*` 測試方法**）執行六維度測試體檢後，發現現有測試集存在 **4 大類結構性病灶（`ST-01` ～ `ST-04`）**，這也是先前 `S-01`（`service.py` 漏匯入 `os` 必崩）與 `S-03`（Worker IPC 污染與強殺）在單元測試全綠下潛伏的核心原因：

1. **`ST-01` 虛假測驗與「自寫自驗」（Vacuous & Self-Simulated Tests，共 4 處）**：
   - **`tests/test_basic.py::TestBasic.test_sample`（整檔空殼）**：全檔僅有一行 `self.assertTrue(True)`，未匯入或測試 `server` 任何程式碼。
   - **`tests/test_server_logging.py::test_worker_ipc_logging_stream`（L234–269）**：Docstring 宣稱驗證 `MasterSupervisor` 從 Worker 串流攔截 `log` 封包且不外洩至 task chunks，但 L249–254 卻是在測試函式裡**自己手寫 `for pkt in [...]: if pkt.get("type") == "log": sup.logger.log(...) else: mock_chunk_emitter(pkt)` 迴圈**，完全未呼叫 `sup.dispatch_task()`。
   - **`tests/test_server.py::test_watcher_observability_status_payload`（L261–289）**：Docstring 宣稱驗證 `MasterSupervisor` 的 `status_payload` 包含 `ModulesWatcher` 可觀測性欄位，但 L268–272 與 L281–285 卻是在測試函式裡**自己手拼字典 `watcher_status = {"enabled": sup.enable_watcher, ...}`** 並斷言該局部變數，完全未呼叫 `sup.get_status_dict()`。
   - **`tests/test_server_logging.py::test_master_logging_integration`（L209–232）**：宣稱驗證 `MasterSupervisor` 啟動時初始化日誌，但內部並未呼叫 `sup.start()`，僅手動呼叫 `sup.logger.recover_and_open()` 與 `sup.logger.info()`（與同檔 `test_logger_write_and_flush` 重複）。
2. **`ST-02` 同檔重複測驗（Duplicate Tests Within `test_server.py`，共 3 組）**：
   - **`WarmWorker.pre_warm()` 事件廣播重複測 2 次**：`test_warm_worker_pre_warm_events`（L83–99）與 `test_worker_warming_event`（L204–212）皆在同一個類別中 `patch.object(events, "broadcast")` 後呼叫 `worker.pre_warm()`。
   - **`ServiceManager` 生命週期重複測 2 次**：`test_service_manager_lifecycle`（L119–136）與 `test_service_manager_metadata_and_status`（L184–202）皆測試 `register -> start_all -> get_status -> stop_all`，後者 100% 涵蓋前者。
   - **`ModulesWatcher` 變更偵測重複輪詢等待**：`test_modules_watcher_detection`（L138–158）與 `test_modules_watcher_affected_modules`（L214–236）分別啟動背景輪詢執行緒並執行多次 `time.sleep`（合計耗時約 1 秒）。
3. **`ST-03` 冗餘與過時死代碼測驗（Obsolete & Static Metadata Tests，共 2 處）**：
   - **`tests/test_server_config.py`（L23, L109–124）測試已廢棄之 `_handle_start`**：`test_cli_mutually_exclusive_args` 與 `test_server_disabled_blocks_start` 呼叫的是 `scripts/cli.py` 底部已無生產環境呼叫者的過渡期死代碼 `_handle_start(["--console", "--daemon"])`（對應 `S-07`），並未測試真實 CLI 入口 `start(CmdBags)` 與 `core.commands` 之 `OptionResolver` 正交群組互斥檢查。
   - **`tests/test_server.py::test_server_manifest_metadata`（L291–298）**：僅開啟 `manifest.json` 比對靜態 `description` 字面字串，未驗證 `contributes/core.json` 與 `contributes/_format.json` 的 Schema 合規性。
4. **`ST-04` 高風險真實邏輯漏測（Critical Coverage Gaps，共 4 大區塊）**：
   - **`ServiceManager.load_from_contributes()` 與 `_load_service_item()` 為 0 覆蓋**：現有測試僅呼叫手動 `mgr.register(MockService())`，從未測試從 `contributes` 載入服務定義、`code.class://` 解析與 `auto_start: true / false` 分支（導致 `S-01`、`S-02` 漏網）。
   - **`worker_main()` 迴圈、`_ipc_stdout` 隔離與 `{"action": "exit"}` 優雅停機為 0 覆蓋**：從未測試 `worker_main()` 收到 `dispatch` / `exit` 指令、背景服務執行緒 `print()` 不污染 `stdout` IPC 通道、以及 `MasterSupervisor._kill_worker_locked()` 兩階段優雅停機握手（導致 `S-03` 漏網）。
   - **`MasterSupervisor` 之 `POST /api/dispatch`、`/api/reload`、`/api/shutdown` 與 `start_time` 恆定性為 0 覆蓋**：僅測了 `GET /api/status`，未測試透過 HTTP `POST /api/dispatch` 讀取 Chunked NDJSON 串流、Workspace Root 不符回傳 `400`、以及 `/api/reload` 保持 `start_time` 不變並同步刷新 `ServerConfig`（導致 `S-04`、`S-06` 漏網）。
   - **`scripts/cli.py` 四大指令（`start` / `stop` / `status` / `reload`）之 `CmdBags` 入口漏測**：缺乏對非法負數 `--ttl` 阻斷、已在運行時呼叫 `start` 輸出狀態橫幅、以及 `stop` / `status` / `reload` 的單元測試。

### 1.2 現況與影響範圍評估
- **架構定調：裁撤空殼 `test_basic.py`，將 `server/tests/` 收斂為 3 個高內聚子系統測試檔，100% 消滅「自寫自驗」並補齊 IPC 與服務託管真實測試**：
  1. **檔案結構收斂（4 檔 $\rightarrow$ 3 檔）**：刪除空殼 `test_basic.py`，由 `test_server.py`（Master / Worker / Service / Streamer / Watcher）、`test_server_config.py`（Config / CLI `CmdBags` / Contributes Schema）與 `test_server_logging.py`（ServerLogger 崩潰自癒與滾動歸檔）三分天下。
  2. **100% 呼叫真實目標方法**：將所有在測試內手寫迴圈或手拼字典的「自寫自驗」全數改為直接調用 `sup.dispatch_task()`、`sup.get_status_dict()` 與 `sup.start()`。
  3. **與 `server` 功能加固路線圖（`S-01` ～ `S-07`）1:1 閉環對齊**：每一項功能修復皆有對應的正向與負向回歸測試守門。

### 1.3 核心根因
1. **以「模擬片段」替代「真實方法呼叫」**：過往撰寫 `FT-04`（Watcher 狀態）與 `FT-08`（Worker IPC 日誌攔截）測試時，為省去構造 Worker 管道或啟動 Watcher，直接在測試內複製了目標邏輯的字典結構與 `if/else` 迴圈，形成自欺欺人的 Tautological Test。
2. **僅測手動 API（`register`）而略過宣告式入口（`load_from_contributes`）**：測試 `ServiceManager` 時直接塞入記憶體 `MockService` 實例，跳過了真實環境必經的 `load_from_contributes()` 載入管線。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：僅刪除 `test_basic.py` 並修改 2 個自寫自驗測試** | 僅做最小表面清理，不補齊 `load_from_contributes`、`worker_main` 與 `/api/dispatch` 測試 | 改動量最小 | 核心 IPC 管線、背景服務載入與 CLI `CmdBags` 入口依然處於 0 覆蓋盲區 | ⭐️⭐️ |
| **方案 2：所有測試皆啟動真實外部背景 Daemon 進程跑端到端測試** | 每個測試案例都透過 `spawn_detached` 拉起真實背景進程並 sleep 等待 | 接近真實作業系統環境 | 測試耗時暴增（每個測試需 1～2 秒）、在受限沙盒環境（`can_spawn_background_daemon() == False`）容易不穩定或殘留孤兒進程 | ⭐️⭐️⭐️ |
| **方案 3：收斂為 3 大子系統測試檔 ＋ 記憶體管道 (`io.StringIO` / `BytesIO`) 實測 IPC ＋ 單例 HTTP 整合測試（推薦採納）** | 1. 刪除 `test_basic.py` 並去重整併為 3 檔。<br/>2. 對 `worker_main` 與 `dispatch_task` 使用記憶體串流（`StringIO` / `BytesIO` Pipe）直接測試真實函式邏輯與 `_ipc_stdout` 隔離。<br/>3. 在 `test_master_supervisor_http_and_lifecycle` 中集中完成 `/api/status`、`/api/dispatch`、`/api/reload`、`/api/shutdown` 全端點實測。 | 1. **100% 測試真實生產函式**<br/>2. **極速穩定**（全套跑測 < 1.5s，不留孤兒進程）<br/>3. 完整覆蓋 `S-01` ～ `S-07` 所有修復項 | 需重構 `test_server.py`、`test_server_config.py` 與 `test_server_logging.py` 共 3 個檔案 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1：最小表面清理 | 方案 2：全子進程重度端到端 | 方案 3：3 檔高內聚收斂 ＋ 記憶體管道實測 IPC（採納） |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 中（受沙盒進程權限限制） | **極高**（`worker_main(in_stream, out_stream)` 原生已預留串流注入介面） |
| **後續維護難度 (Maintenance)** | 中 | 高（進程競態除錯困難） | **極低**（職責清晰：Core Runtime / Config & CLI / Logger 三檔分明） |
| **缺陷攔截可靠性 (Reliability)** | 低（漏測仍在） | 高 | **極高**（精準攔截 `NameError`、IPC 雜訊污染、Uptime 重置與非預期強殺） |
| **落地難度 (Implementation)** | 極低 | 中 | **低**（聚焦於 3 個測試檔的去重與補盲） |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

### 4.1 測試集檔案結構收斂與去重映射表（4 檔 $\rightarrow$ 3 檔）

| 目標測試檔 | 處置動作與整併內容 |
| :--- | :--- |
| **`tests/test_basic.py`** | **直接物理刪除**：移除僅含 `self.assertTrue(True)` 的空殼模板測試檔。 |
| **`tests/test_server.py`** | **主核心測試集（去重 ＋ 修復自寫自驗 ＋ 補齊 IPC 與服務託管）**：<br/>• 合併重複的 `test_warm_worker_pre_warm_events` 與 `test_worker_warming_event` 為單一測試（驗證 `server_worker_warming` 與 `server_worker_ready`）。<br/>• 合併重複的 `test_service_manager_lifecycle` 與 `test_service_manager_metadata_and_status`，並擴充測試 `load_from_contributes()`。<br/>• 合併 `ModulesWatcher` 兩項測試並將 `poll_interval_sec` 設為 `0.02s`、`debounce_sec` 設為 `0.02s`，將等待耗時壓縮 80%。<br/>• 修復 `test_watcher_observability_status_payload`，改為直接呼叫 `sup.get_status_dict()["watcher"]` 進行斷言。 |
| **`tests/test_server_config.py`** | **組態、CLI `CmdBags` 與 Contributes Schema 測試集**：<br/>• 移除對已廢棄 `_handle_start` 的匯入與呼叫（配合 `S-07`）。<br/>• 改為直接以 `CmdBags` 測試 `scripts/cli.py` 的 `start()`、`stop()`、`status()`、`reload()`。<br/>• 透過 `OptionResolver` 與 `ContributesValidator` 驗證 `contributes/core.json`（含 `mode` 群組 `--console` / `--daemon` 互斥與 `events` 宣告）及 `contributes/_format.json` 的 Schema 合法性。 |
| **`tests/test_server_logging.py`** | **日誌引擎與 IPC Log 攔截測試集**：<br/>• 移除與 `test_logger_write_and_flush` 重複的 `test_master_logging_integration`（將 `sup.start()` / `sup.stop()` 日誌歸檔驗證併入 `test_server.py`）。<br/>• 徹底重寫 `test_worker_ipc_logging_stream`：建立帶有偽造 `stdin/stdout` 管道的 Mock Worker Process 掛入 `sup._worker_proc`，**真實呼叫 `sup.dispatch_task()`**，驗證 Worker 送出的 `{"type": "log"}` 被 `dispatch_task` 寫入 `sup.logger.log_file_path` 且未進入 `chunk_emitter`。 |

### 4.2 4 大高風險漏測路徑 (`ST-04`) 補盲規格
1. **`ServiceManager.load_from_contributes`、跨模組連字號路徑注入與 `auto_start` 實測（於 `test_server.py`）**：
   - 於測試沙盒建立連字號外部模組目錄 `.modules/mock-svc-mod/mock_svc_mod/worker.py`（定義繼承自 `BaseServiceWorker` 之測試 Worker），並 Mock `core.contributes.get("server", "services")` 回傳兩筆服務：一筆為 `auto_start: True`（設定 `"__provider__": "mock-svc-mod"`, `"worker_class": "code.class://mock-svc-mod/worker:MockServiceWorker"`）、一筆為 `auto_start: False`。
   - 呼叫 `mgr.load_from_contributes(self.root_dir)` 與 `mgr.start_all({"yscb_root": self.root_dir})`，斷言不拋出 `NameError` 或 `ModuleNotFoundError`、兩筆服務皆已註冊，且僅 `auto_start: True` 之服務 `alive` 為 `True`。
2. **`worker_main` 迴圈、`stdout` IPC 硬隔離與 `exit` 優雅停機實測（於 `test_server.py`，防假陽性設計）**：
   - **防假陽性關鍵**：為真實測到子進程模式下 `ipc_out = sys.stdout; sys.stdout = sys.stderr` 的重導向隔離（而非因傳入獨立 `out_stream` 物件而天然避開 `sys.stdout`），測試時須以 `patch.object(sys, "stdout", new=ipc_capture)` 與 `patch.object(sys, "stderr", new=err_capture)` 替換標準串流，並以 **`out_stream=None`** 呼叫 `worker_main(yscb_root, in_stream=in_io, out_stream=None)`。
   - 構造背景服務在 `start()` 後直接呼叫 `print("unstructured background stdout noise")`，向 `in_io` 送入 `{"action": "dispatch", ...}` 與 `{"action": "exit"}`。
   - 斷言 `ipc_capture` 輸出的每一行皆為合法 JSON（`worker_ready`、`terminal_stream`、`task_finish`），背景雜訊確實在 `err_capture` 中被捕獲而未污染 `ipc_capture`，且退出 `worker_main` 後背景服務之 `stopped` 狀態確為 `True` 且 `sys.stdout` 已於 `finally` 還原。
   - 測試 `MasterSupervisor._kill_worker_locked()` 會先向 `proc.stdin` 寫入 `{"action": "exit"}\n` 並呼叫 `proc.wait()`。
3. **`MasterSupervisor` 全 HTTP 端點（`/api/dispatch`、`/api/reload`、`/api/shutdown`）與 `start_time` 恆定實測（於 `test_server.py`）**：
   - 擴充 `test_master_supervisor_http_and_lifecycle`：
     - 測試 `POST /api/dispatch` 傳入不匹配的 `yscb_root` 時回傳 HTTP `400 Workspace Root Mismatch`；傳入合法請求時回傳 HTTP `200` Chunked NDJSON 串流。
     - 測試 `POST /api/reload` 回傳 `new_worker_pid`，且讀取 `daemon.json` 驗證 `start_time` 與重載前完全相等（不重置），同時驗證修改組態後 `reload` 會同步刷新 `sup.idle_timeout_sec`。
     - 測試 `POST /api/shutdown` 回傳含 `summary` 的 JSON 並優雅關閉伺服器、歸檔日誌。
4. **`scripts/cli.py` 四大 CLI 入口之 `CmdBags` 測試（於 `test_server_config.py`）**：
   - 測試 `start(CmdBags(..., options={"ttl": CmdOption("ttl", "-5")}))` 返回 `1` 並攔截非法負數 TTL。
   - 測試當 Daemon 已在運行時呼叫 `start(CmdBags(...))` 返回 `0` 並印出 `Daemon is already running` 與啟動橫幅。
   - 測試 `status(CmdBags(...))`、`reload(CmdBags(...))` 與 `stop(CmdBags(...))` 在 Daemon 運行與未運行雙狀態下的返回碼與輸出。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- **雙路線圖強制綁定／合併立項建議**：由於本測試純化路線圖之 `ST-03`（移除 `_handle_start`）與 `ST-04`（補測 `S-01` ～ `S-06` 服務載入、IPC 隔離、優雅停機與 Reload 組態刷新）直接與 `server_service_hosting_and_ipc_hardening_roadmap.md` 共生，**立項時應將兩份 `server` 路線圖合併為單一 `server` 升級計畫（Full Track）同步交付**。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1：裁撤空殼檔、移除過時 `_handle_start` 測試與合併重複測試（`ST-01` 部分、`ST-02`、`ST-03`）**
   - 刪除 `tests/test_basic.py`。
   - 於 `tests/test_server.py` 合併重複的 `pre_warm`、`ServiceManager` 與 `ModulesWatcher` 測試，移除靜態 `manifest.json` 字面檢查。
   - 於 `tests/test_server_config.py` 移除對 `_handle_start` 的依賴，改用 `CmdBags` 與 `OptionResolver`。
2. **Stage 2：修復「自寫自驗」虛假測試（`ST-01` 核心）**
   - 重寫 `test_server_logging.py::test_worker_ipc_logging_stream`，改為真實呼叫 `sup.dispatch_task()`。
   - 重寫 `test_server.py::test_watcher_observability_status_payload`，改為真實呼叫 `sup.get_status_dict()`。
3. **Stage 3：補齊 4 大高風險漏測路徑並全量驗收（`ST-04`）**
   - 於 `test_server.py` 補齊 `load_from_contributes()`、`worker_main()` IPC 隔離與 `exit` 握手、以及 `/api/dispatch`、`/api/reload`、`/api/shutdown` 測試。
   - 於 `test_server_config.py` 補齊 CLI 四大指令 `CmdBags` 測試與 `contributes` Schema 驗證，執行 `python yscb.py dev test server` 確認 100% 通過且無殘留背景進程。
