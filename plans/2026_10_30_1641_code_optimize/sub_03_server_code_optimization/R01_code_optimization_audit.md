# 技術調研報告：`server` 模組五維度靜態診斷與 Mode A 無損重構處方 (R01_code_optimization_audit.md)

> 調研主題：sub_03_server_code_optimization (`server` 模組五維度靜態診斷與 Mode A 無損重構處方)  
> 建立日期：2026-10-30  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  1. **隱藏執行期 `NameError` 被 `except Exception: pass` 靜默吞噬（`D4` — `P0`）**：`ys_codebase/source/server/server/logger.py` 頂層未匯入 `sys`，卻在 `RotatingFileLogger.write_raw()`（`L276-281`）於 `self.echo_console=True`（即 `yscb server start --console` 模式）時呼叫 `sys.stdout.write(text)` 與 `sys.stdout.flush()`，拋出之 `NameError: name 'sys' is not defined` 又被外層 `except Exception: pass`（`L282-283`）靜默吞沒，導致 `--console` 模式下 Worker 串流輸出在主控台完全靜默失效。
  2. **單檔職責過載與啟動資源鎖洩漏風險（`D1` / `D4`）**：`server/master.py`（757 LOC，佔全模組 33.5%）同時混雜「Worker 槽位資料模型 (`WorkerSlot`)、HTTP 路由與 SSE/JSON 串流 (`DispatcherHTTPHandler`)、`daemon.json` 狀態序列化、Master 雙背景迴圈與子進程調度 (`MasterSupervisor`)」四大職責；且 `MasterSupervisor.start()`（`L178-255`）在取得檔案鎖後若於初始化階段拋出異常，未進入 `finally: self._release_lock()`；`worker.py:worker_main`（`L282-286`）若 `WarmWorker()` 建構失敗，其 `finally` 存取 `worker` 亦會引發 `UnboundLocalError`。
  3. **`master.py` 與 `scripts/cli.py` 跨檔重複實作（`D2` / `D3`）**：`daemon.json` 讀取邏輯（`MasterSupervisor.read_state` vs `cli._read_daemon_state`）、Detached Master 跨平台背景啟動命令與 `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` 旗標組裝、離線預設狀態字典、Uptime 時間格式化與 Watcher 狀態字串組裝在兩支檔案中雙重維護。
  4. **殭屍參數、過渡相容分支與無作用屬性（`D2` / `D5`）**：`ServerConfig.load(workspace_root=...)`、`MasterSupervisor.stop(force=...)`、`ServiceManager.stop_all(timeout_sec=...)` 均為函式體完全未使用的殭屍參數；`server/__init__.py` 頂層飢渴匯入 7 個 0 外部調用之內部類別並硬編碼過時 `__version__ = "1.0.0"`；`service.py` 與 `watcher.py` 殘留舊版 Schema 與 0 參數回呼反射相容分支。
- **調研目標**：
  - 鎖定 **範圍 = 單一模組（`ys_codebase/source/server/`，含 `server/` 8 檔與 `scripts/cli.py` 1 檔，共 9 檔 / 2,263 LOC）** 與 **生命週期 = `Mode A：新功能收斂期（Convergence Mode / 可破壞性變更）`**。
  - 融合雙子代理（Auditor A / Auditor B）獨立盲測共識，產出完整基線盤點、`Mode A` 破壞性清除清冊（11 大項）、`D1~D5` 分級問題單（`P0/P1/P2`）與 `S1~S6` 無損重構處方。

### 1.1 `server` 模組基線盤點表 (9 檔 / 2,263 LOC)

| 檔案路徑 (`ys_codebase/source/server/...`) | 行數 (LOC) | 核心職責與主要類別/函式 | 入向耦合 (`server` 內 / 跨模組) | 診斷熱點等級 |
| :--- | :---: | :--- | :--- | :---: |
| `server/master.py` | 757 | `WorkerSlot`、`DispatcherHTTPHandler`、`MasterSupervisor`：Master 守護進程、Worker 池與 HTTP 閘道 | `cli`、`core.dispatcher`、`tests/` | **P0 / P1** |
| `scripts/cli.py` | 405 | `server` CLI 子命令處理器（`start`/`stop`/`status`/`reload`）與 ANSI 面板渲染 | `core.dispatcher`、`tests/` | **P1** |
| `server/logger.py` | 306 | `RotatingFileLogger`：伺服器日誌滾動、過期歸檔壓縮與 Console 鏡像輸出 | `master`、`cli`、`tests/` | **P0 / P1** |
| `server/worker.py` | 290 | `WarmWorker`、`worker_main`：常駐預熱 Worker IPC 執行迴圈与命令派發 | `master` (subprocess)、`tests/` | **P1** |
| `server/service.py` | 220 | `ServiceContext`、`ServiceManager`：背景常駐服務生命週期管理 | `worker`、`tests/` | **P1** |
| `server/watcher.py` | 163 | `ModulesWatcher`：`.modules/` 目錄快照輪詢與變更通知 | `master`、`tests/` | **P1 / P2** |
| `server/streamer.py` | 53 | `StreamMultiplexer`、`MultiplexedStream`：`stdout`/`stderr` 攔截與雙路串流封裝 | `worker`、`tests/` | **P2** |
| `server/config.py` | 49 | `ServerConfig`：伺服器組態載入與數值邊界正規化 | `master`、`cli`、`core.dispatcher`、`tests/` | **P1** |
| `server/__init__.py` | 21 | 套件匯出門面 | `tests/` | **P1** |

---

## 2. 候選方案分析與對比 (Candidate Evaluation)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：`Mode A` 破壞性介面收斂 + `master.py` 職責解耦 + Bug 根除**<br/>*(Recommended — Full Track)* | 立即修復 `logger.py` 缺失 `import sys` 之 `P0` 缺陷與 `master.py`/`worker.py` 資源釋放保護；移除 `ServerConfig.load(workspace_root)`、`stop(force)`、`stop_all(timeout_sec)` 等殭屍參數（同步更新 `core/commands/dispatcher.py:140` 調用點）與舊版 Schema 相容分支；合併 `master.py` 與 `cli.py` 重複之狀態/啟動邏輯並拆解 `master.py` 長方法。 | 100% 根除隱藏 `NameError` 與鎖洩漏風險，消除跨檔重複代碼，預計淨減 ~250 LOC。 | 變更 `ServerConfig.load()` 簽名需同步更新 `core/commands/dispatcher.py:140` 與 `server/tests/`。 | ⭐⭐⭐⭐⭐ **(推薦)** |
| **方案 B：僅修補 `logger.py` 與保留全部舊參數/相容分支** | 僅補上 `import sys`，保留所有未使用參數與重複 helper。 | 變更極小。 | 未解決 `master.py` 職責過載、雙份 `daemon.json` 狀態讀取與殭屍參數問題。 | ⭐⭐ |

---

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 `Mode A` 公開入口收斂、薄轉發層、相容別名與死代碼清除清冊 (`S5`)

| 編號 | 檔案與行號座標 | 冗餘轉發 / 相容別名 / 死代碼 | 調用方盤點（`server` 內部 / 跨模組 / `tests/`） | `Mode A` 物理清除與收斂處方 (`S5`) |
| :---: | :--- | :--- | :--- | :--- |
| **M-01** | `server/__init__.py:5-21` | 頂層飢渴重匯出 7 個內部類別（`ServerConfig`, `MasterSupervisor`, `WarmWorker`, `StreamMultiplexer`, `ServiceManager`, `ModulesWatcher`, `RotatingFileLogger`）與過時硬編碼 `__version__ = "1.0.0"`（`manifest.json` 已為 `"1.0.4.0"`） | 全倉 **0 callers** 從 `from server import ...` 匯入（均從具體子模組匯入） | 清空飢渴重匯出（或改為 PEP 562 `__getattr__` 按需延遲載入），物理刪除過時之 `__version__ = "1.0.0"`。 |
| **M-02** | `server/config.py:45-49` | `ServerConfig.load(cls, workspace_root: Optional[str] = None)` 之未使用參數 `workspace_root` | `cli.py:122, 225`、`master.py:333`、`core/commands/dispatcher.py:140`、`test_server.py:559, 578` | 物理移除未使用的 `workspace_root` 參數，簽名收斂為 `ServerConfig.load(cls) -> ServerConfig`，同步更新 4 處調用點。 |
| **M-03** | `server/master.py:257` | `MasterSupervisor.stop(self, force: bool = False)` 之未使用參數 `force` | `master.py:255, 623`（均為無參數 `.stop()`） | 物理移除未使用的 `force: bool = False` 參數。 |
| **M-04** | `server/service.py:196` | `ServiceManager.stop_all(self, timeout_sec: float = 2.0)` 之未使用參數 `timeout_sec` | `worker.py:241`、`test_server.py` | 物理移除未使用的 `timeout_sec` 參數並同步更新 `worker.py:241`。 |
| **M-05** | `server/master.py:481-483` | `MasterSupervisor._spawn_worker(self)` 2 行薄轉發方法（僅 `with self._lock: return self._spawn_worker_locked()`） | 僅 `master.py:222` 1 處調用 | 將 `L222` 內聯為 `with self._lock: self._spawn_worker_locked()`，物理刪除 `_spawn_worker`。 |
| **M-06** | `server/master.py:586-594`<br/>`scripts/cli.py:56-65` | `MasterSupervisor.read_state` 與 `cli._read_daemon_state` 雙份完全重複的 `daemon.json` 讀取器 | `master.py`、`cli.py`、`core/commands/dispatcher.py:198` | 收斂為單一正統入口（保留 `MasterSupervisor.read_state` 或獨立 `daemon_state` 輔助函式），物理刪除 `cli._read_daemon_state`。 |
| **M-07** | `server/service.py:100, 121, 125, 136` | 舊版 `contributes` Schema 相容退避：`svc_decl.get("_provider") or svc_decl.get("provider")`、`svc_decl.get("entry_point") or svc_decl.get("entry")`、`svc_decl.get("id")`、以及 `code.func://` 雙重前綴處理 | 現況 Schema 已強制規範為 `_provider`、`name`、`entry_point` 與 `code://` | 物理刪除舊版 `"provider"`、`"entry"`、`"id"` 與 `"code.func://"` 相容分支。 |
| **M-08** | `server/watcher.py:121-135` & `L156-162` | `ModulesWatcher._notify_change` 針對舊版 0 參數 callback 之 `inspect.signature` 反射與 `TypeError` 退避；`_has_changed` 手寫 7 行字典比對迴圈 | 全倉 callback 均為單參數 `Callable[[List[str]], None]`；Python `dict != dict` 原生支援相等比對 | 簡化 `_notify_change` 為直接呼叫 `cb(changed_modules)`；將 `_has_changed` 收斂為 `return prev != curr`。 |
| **M-09** | `server/logger.py:29` | `START_BANNER_PREFIX = "=== YSCB Server Started at "` 宣告後從未引用之常數（`L34` 與 `L191` 卻各自硬編碼相同字串） | **0 references** | 讓 `HEADER_TIME_REGEX` (`L34`) 與啟動橫幅寫入 (`L191`) 直接引用 `START_BANNER_PREFIX` 常數，消除魔法字串重複。 |
| **M-10** | `server/worker.py:37` & `L122-123` | `WarmWorker._is_running = True` 從未讀取之死屬性；`_execute_command` 內 `L122-123` 賦值後於 `L139-140` 立即被覆寫之死變數 `cmd_name`/`sub_args` | **0 references** | 物理刪除 `self._is_running` 與 `L122-123` 冗餘賦值。 |
| **M-11** | 6 支檔案頂部未引用 `import` | `master.py:16, 20` (`shutil`, ` Set`)、`worker.py:12` (`List`)、`service.py:11` (`Callable`)、`streamer.py:7` (` Optional`)、`watcher.py:12` (` Tuple`)、`scripts/cli.py:12` (`Tuple`) | **0 references** | 物理清除全部未引用之匯入。 |

---

### 3.2 五維度靜態診斷問題單 (`D1~D5` × `P0/P1/P2`)

| 編號 | 維度 | 嚴重度 | 座標 (`file:line`) | 病徵描述與根因剖析 | 對應重構策略 |
| :---: | :---: | :---: | :--- | :--- | :---: |
| **F-01** | **D4** | **P0** | `server/logger.py:276-283` | **`write_raw()` 缺失 `import sys` 引發 `NameError` 且被 `except Exception: pass` 靜默吞噬**：`logger.py` 未匯入 `sys`，當 `self.echo_console=True`（`--console` 旗標）時，`write_raw()` 呼叫 `sys.stdout.write(text)` 必拋出 `NameError`，卻因外層 `except Exception: pass` 被完全掩蓋。 | **S4**（頂層補齊 `import sys`，將 `except Exception` 收窄為 `except OSError`） |
| **F-02** | **D4** | **P0** | `server/master.py:178-255`<br/>`server/worker.py:276-286` | **啟動與結束階段之資源釋放對稱缺口 (`Scoped Resource Lifecycle`)**：`MasterSupervisor.start()` 在 `L180` 取得 `server.lock` 後，若 `L186-248`（清理舊 Worker、啟動 HTTP Server 或 Watcher）拋出例外，未受 `try...finally` 保護而洩漏鎖檔；`worker_main()` 在 `try` 塊內賦值 `worker = WarmWorker()`，若建構拋錯，`finally: worker._stop_services()` 將拋出 `UnboundLocalError`。 | **S4**（`start()` 全程納入 `try...finally: self.stop()`；`worker = None` 預先初始化） |
| **F-03** | **D1 / D2** | **P0** | `server/master.py:1-757` | **`master.py` (757 LOC) 四職責耦合單體巨檔**：單一檔案同時定義 `WorkerSlot` 資料結構、`DispatcherHTTPHandler` HTTP/SSE 協定處理、`daemon.json` 狀態讀寫與 `MasterSupervisor` 進程池監控，違反單一職責原則。 | **S1 + S2**（詳見 §3.3） |
| **F-04** | **D2 / D3** | **P1** | `server/master.py:586-733`<br/>`scripts/cli.py:56-297` | **`master.py` 與 `scripts/cli.py` 5 處跨檔重複邏輯**：(1) `daemon.json` 讀取；(2) Detached Master `subprocess.Popen` 跨平台旗標與命令組裝（`master.py:678-694` vs `cli.py:139-155`）；(3) 離線預設狀態字典（`master.py:92-104` vs `cli.py:226-237`）；(4) Uptime 格式化（`master.py:725-733` vs `cli.py:30-38`）；(5) Watcher 狀態字串格式化（`master.py:719-723` vs `cli.py:258-262`）。 | **S2 + S3**（抽取共用純函式與統一入口） |
| **F-05** | **D3** | **P1** | `server/logger.py:63-267` | **`logger.py` 內部時間戳推導與安全搬移重複**：`_compress_to_archive` (`L137-159`)、`_rotate` (`L213-225`)、`_startup_maintenance` (`L244-255`) 3 處重複實作「優先解析 Header 正則、失敗退避 `os.path.getmtime`」；`L96-102` 與 `L231-237` 2 處重複實作「若目標存在先刪除再 `shutil.move`」。 | **S3**（抽取 `_resolve_file_timestamp(filepath)` 與 `_safe_move_file(src, dst)`） |
| **F-06** | **D1 / D3** | **P1** | `server/master.py:66-143, 484-580`<br/>`server/worker.py:95-232` | **HTTP Handler 與 Worker 命令執行長方法**：`DispatcherHTTPHandler.do_POST` (`L106-143`) 與 `_send_json` (`L66-72`) 混雜路由與底層 socket 寫入；`MasterSupervisor.dispatch_task` (`L517-580`) 混雜雙重重試與串流解析；`WarmWorker._execute_command` (`L95-232`, 138 LOC) 混雜模組重載、多工器掛載、命令派發與 Telemetry 記錄。 | **S1 + S2**（詳見 §3.3） |
| **F-07** | **D4** | **P2** | `server/master.py`、`worker.py`、`service.py`、`watcher.py`、`logger.py`（共 36 處） | **過度寬泛之 `except Exception: pass`**：除進程終止清理外，多處檔案 I/O 與 JSON 解析亦使用無日誌之 `except Exception: pass`，增加除錯難度。 | **S4**（區分預期之 `OSError`/`ProcessLookupError` 與非預期異常） |

---

### 3.3 `S1` 業務階段邏輯聚合與 `S2` 無狀態邏輯剝離藍圖（5 大核心檔案）

#### 1. `server/master.py` (757 LOC $\to$ 預估 ~520 LOC)
* **`S2` 無狀態邏輯剝離**（將不依賴 `self` 的方法轉為模組級純函式，並開放 `scripts/cli.py` 共用）：
  - `spawn_detached_master(workspace_root: str) -> subprocess.Popen`（收斂 `master.py:678-694` 與 `cli.py:139-155` 重複之跨平台背景啟動邏輯）
  - `build_offline_status_payload(cfg: ServerConfig) -> Dict[str, Any]`（收斂 `master.py:92-104` 與 `cli.py:226-237`）
  - `format_uptime(uptime_sec: float) -> str` 與 `format_watcher_status(enabled: bool, interval: float) -> str`（收斂 `master.py:719-733` 與 `cli.py:30-38, 258-262`）
  - `_terminate_process_tree(pid: int)`（將原 `_kill_pid_forcefully` 剝離為無狀態純函式）
* **`S1` 業務階段拆解**：
  - `MasterSupervisor.start`（原 `L178-255`，78 LOC）$\to$ 納入 `try...finally: self.stop()` 保護，拆為 `_initialize_daemon_environment`、`_start_http_and_watcher_services`、`_run_supervisor_main_loop`。
  - `MasterSupervisor.dispatch_task`（原 `L517-580`，64 LOC）$\to$ 拆為 `_acquire_ready_worker_with_retry` 與 `_stream_task_over_worker_pipe`。

#### 2. `server/logger.py` (`RotatingFileLogger`, 306 LOC $\to$ 預估 ~230 LOC)
* **`S2 + S3` 去重與純化**：
  - 補齊頂層 `import sys`，並讓 `HEADER_TIME_REGEX` 與啟動橫幅統一引用 `START_BANNER_PREFIX`。
  - 抽取純函式 `_extract_log_file_timestamp(filepath: str) -> datetime`（消除 3 處重複之正則 + `getmtime` 退避）與 `_safe_replace_file(src: str, dst: str) -> None`（消除 2 處重複之檔案覆寫搬移）。

#### 3. `server/worker.py` (`WarmWorker`, 290 LOC $\to$ 預估 ~210 LOC)
* **`S1 + S2` 階段拆解**：
  - 將 `_execute_command`（原 `L95-232`，138 LOC）拆解為：
    1. `_sync_dirty_modules_before_exec(dirty_mods: List[str])`（處理熱重載與 `sys.modules` 清除）
    2. `_dispatch_command_with_captured_streams(payload: Dict[str, Any]) -> int`（掛載 `StreamMultiplexer`、執行 `core.dispatcher.dispatch_local` 並保證 `finally` 卸載）
    3. `_record_worker_telemetry(cmd_str: str, exit_code: int, duration_ms: float)`

#### 4. `server/service.py` (220 LOC) & `server/watcher.py` (163 LOC)
* **`S2 + S5` 瘦身**：
  - `service.py`：移除舊版 Schema 鍵名 fallback（`_provider`/`entry`/`id`/`code.func://`）與未使用的 `stop_all(timeout_sec)` 參數；將 `_load_Callable_from_uri(uri_str, mod_name)` 剝離為模組級純函式。
  - `watcher.py`：將 `_scan_modules_dir(modules_dir)` 剝離為純函式，`_has_changed` 簡化為 `prev != curr`，`_notify_change` 移除 `inspect.signature` 0 參數反射分支。

#### 5. `scripts/cli.py` (405 LOC $\to$ 預估 ~290 LOC)
* **`S1 + S3` 消除跨檔重複**：
  - 移除本地重複的 `_read_daemon_state`、`_format_uptime`、Detached Master `Popen` 組裝與離線狀態字典，直接調用 `master.py` 公開之單一正統純函式。
  - 將 `cmd_status`（105 LOC）拆為 `_fetch_server_status_data(yscb_root)` 與 `_render_status_dashboard(status_data)`。

---

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **推薦落地策略**：
  - 採納 **方案 A（`Mode A` 破壞性介面收斂 + `master.py` 職責解耦 + Bug 根除）**，於後續啟動實作時將本子計畫 `sub_03_server_code_optimization` 原地升級為 **標準開發計畫 (`Full Track`, `P01~P07`)**。
  - **預估量化收益**：
    1. 修復 `logger.py:write_raw` 缺失 `import sys` 之 **P0 隱藏 `NameError`** 與 `MasterSupervisor.start()` / `worker_main()` 的資源釋放漏洞。
    2. 物理清除 **11 項殭屍參數、飢渴匯出、舊版 Schema 分支與未引用匯入**，並消除 `master.py` 與 `cli.py` 之間的 5 處重複實作，預計淨減約 **220~280 LOC**（約佔全模組 10%~12%）。
- **後續行動與 P00 銜接（Step 3 三大流轉出口）**：
  1. **出口 ① 立即/後續升級實作（推薦）**：將 `R01_code_optimization_audit.md` 標記為 `Concluded`，並於 `sub_03_server_code_optimization` 原地追加 `P01~P07` 升級為 `Full Track` 實作計畫。
  2. **出口 ② 轉入長期技術儲備**：轉入 `/roadmap` 或 `/todo` 分批排程。
  3. **出口 ③ 結案存檔**：僅保留調研診斷報告備查。
