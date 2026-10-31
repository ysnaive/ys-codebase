# 技術調研報告：Server 模組業務代碼五維度靜態診斷與無損重構審計 (R03_code_optimization_audit.md)

> 調研主題：Server 常駐服務端模組 (`ys_codebase/source/server/`) 業務代碼五維度靜態診斷與重構處方  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize / sub_03_server_code_optimization  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  `server` 模組作為 YS-Codebase 的「Master 控制平面 + WarmWorker 資料平面」雙進程常駐守護基座，共包含 8 個業務 Python 檔案（合計 1,977 行，排除 `tests/`）。隨著雙軌熱重載（`ModulesWatcher`）、背景微服務容器（`ServiceManager`）、防抖串流攔截（`DebouncedIOStreamer`）與即時落盤滾動日誌（`ServerLogger`）演進，核心檔案 [`master.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py) 已膨脹至 **784 行**，同時承載「Daemon 狀態序列化與 CLI 橫幅格式化」、「MasterSupervisor 進程生命週期與 Worker 管道管理」及「Localhost HTTP 路由與 Chunked NDJSON 伺服器」三大正交職責（`D1` P0 巨型破窗檔案）。此外，Worker 啟動與任務派發存在重複的 NDJSON 管道迴圈與長程序（`D3` P1）、跨模組邊界存在繞過 `core` 標準抽象的硬編碼路徑與裸 I/O（`D5` P1），以及多處宽泛異常靜默吞噬（`D4` P1）。
- **調研目標**：
  1. **定錨基準與範圍摘要**：
     - **檢視範圍**：單一模組（`Module Scope`：`ys_codebase/source/server/`，涵蓋 `scripts/cli.py` 與 `server/{__init__,config,logger,master,service,streamer,watcher,worker}.py` 共 8 個業務源碼檔，排除 `tests/`）。
     - **生命週期模式**：同時完整盤點 `Mode B（維護期 / 嚴守向下相容，保護公開與跨模組契約、收斂 0 外部調用之純內部工具函式）` 與 `Mode A（收斂期 / 允許破壞性清理）` 雙基準之契約邊界，確保無論主計畫採納何種相容策略皆具備 100% 精確的施工座標。
  2. **契約邊界與內部工具函式查驗表**：基于 `knowledge-db` 全空間調用圖譜與跨模組檢索，嚴格區分「對外公開/跨模組契約入口」與「0 外部跨模組調用之純內部工具函式/私有結構」。
  3. **`D1 ~ D5` 五維度分級診斷**：對全部 8 個業務檔案執行微觀至中觀掃描，標定精確行號區間、嚴重度（`P0 / P1 / P2`）與對應重構手術刀（`S1 ~ S6`）。

### 1.1 模組檔案規模與職責盤點表

| 檔案路徑 | 行數 (LOC) | 核心職責與角色定位 | 結構健康度初評 |
| :--- | :---: | :--- | :---: |
| [`server/master.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py) | 784 | `ServerDaemonState`、CLI 橫幅格式化、`MasterSupervisor` 控制平面、`_create_http_server` HTTP 端點 | 🔴 **P0 巨型破窗檔**（多重正交職責混雜、長方法） |
| [`server/logger.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/logger.py) | 288 | `ServerLogger` 即時 flush 日誌、崩潰恢復歸檔、5 代歷史滾動清理 | 🟡 **P1 局部重複**（歸檔流程重複、魔術常數） |
| [`scripts/cli.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py) | 255 | CLI 入口（`start`、`stop`、`status`、`reload`）、HTTP 探針與狀態面板渲染 | 🟡 **P1 抽象混雜**（`start`/`stop` 含輪詢迴圈、手動路徑回退） |
| [`server/worker.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/worker.py) | 251 | `WarmWorker` 預熱、環境隔離、命令攔截派發、`worker_main` 迴圈 | 🟡 **P1 長函式**（`worker_main` 72 行混雜初始化與 IPC 迴圈） |
| [`server/service.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/service.py) | 218 | `BaseServiceWorker` 抽象基類、`ServiceManager` 動態載入與健康檢查 | 🟡 **P1 巢狀與職責**（URI 動態匯入字串處理、4 層巢狀讀取） |
| [`server/streamer.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/streamer.py) | 159 | `DebouncedIOStreamer` 與 `_StreamProxy` 500ms 防抖串流攔截 | 🟢 **健康**（僅局部 `D4`/`D2` 小異味） |
| [`server/watcher.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/watcher.py) | 138 | `ModulesWatcher` `.modules/` mtime 快照輪詢與跨進程鎖退避 | 🟡 **P1 控制流**（`_poll_loop` 雙重防抖等待與靜默吞異常） |
| [`server/config.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/config.py) | 79 | `ServerConfig` 組態載入與 `_parse_bool` 寬鬆型別防禦 | 🟢 **健康**（結構清晰，僅局部異常吞噬） |
| [`server/__init__.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/__init__.py) | 3 | 套件 Docstring | 🟢 **Pass** |

### 1.2 契約邊界與內部工具函式查驗表 (`Contract & Helper Verification`)

經 `knowledge-db` 全空間檢索與 `contributes/` 契約核對，`server` 模組之符號邊界分類如下：

| 分類層級 | 符號名稱與定義座標 | 外部/跨模組引用實證 | 處置原則（Mode B 門面保護 / Mode A & 內部直接收斂） |
| :--- | :--- | :--- | :--- |
| **第一層：對外公開契約與跨模組入口**<br>*(Public / Exported Surface)* | • [`start`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L83-L134)、[`stop`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L137-L181)、[`status`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L218-L237)、[`reload`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L240-L255)<br>• [`BaseServiceWorker`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/service.py#L57-L94) (`name`, `start`, `stop`, `health_check`)<br>• [`ServiceManager`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/service.py#L97-L218)<br>• [`MasterSupervisor`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L182-L667)、[`ServerDaemonState`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L35-L43)<br>• [`ServerConfig.load`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/config.py#L45-L79)<br>• [`ServerLogger`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/logger.py#L58-L288)<br>• [`ModulesWatcher`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/watcher.py#L37-L138)<br>• [`DebouncedIOStreamer`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/streamer.py#L15-L145)<br>• [`WarmWorker`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/worker.py#L24-L169)、[`worker_main`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/worker.py#L172-L243) | • `contributes/core.json` 註冊 4 大 CLI 子命令與 2 個事件 (`server_worker_warming`, `server_worker_ready`)。<br>• `knowledge-db/knowledge_db/service.py:19` 直接 `from server.service import BaseServiceWorker`。<br>• `core/commands/dispatcher.py:182,295` 耦合 `.cache/server/daemon.json`、`daemon.lock`、HTTP `/api/dispatch` 與 `server start --daemon`。<br>• `spawn_detached_master` 子進程命令直接匯入 `from server.master import MasterSupervisor`；`_spawn_worker_locked` 直接呼叫 `server/worker.py`。 | **[凍結門面]**<br>維持類別名稱、公開方法簽名、HTTP JSON/NDJSON 協議格式、`daemon.json` 欄位結構與 CLI 選項 100% 相容。若對 `master.py` 執行 `S6` 物理拆檔，於 `server.master` 透過匯入重匯出（Re-export）維持原路徑可用（`Mode A` 則同步更新 `cli.py` 匯入點）。 |
| **第二層：模組內跨檔輔助函式**<br>*(Intra-Module Shared Helpers，0 外部跨模組調用)* | • [`format_uptime`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L46-L53)<br>• [`format_watcher_status`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L56-L64)<br>• [`read_daemon_state`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L67-L78)<br>• [`build_fallback_status_payload`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L81-L90)<br>• [`spawn_detached_master`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L93-L114)<br>• [`format_startup_banner`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L117-L156)<br>• [`format_shutdown_summary`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L159-L179) | 經全空間檢索確認：**100% 僅由 `server/scripts/cli.py` 與 `server/server/master.py` 內部互相調用**，0 外部跨模組引用。 | **[可抽離收斂]**<br>在執行 `S6` 將 CLI 格式化與狀態讀寫從 `master.py` 抽離至獨立內部子模組時，`Mode A` 直接更新 `cli.py` 與 `master.py` 匯入點；`Mode B` 若測試有引用則於 `master.py` 保留薄重匯出。 |
| **第三層：經嚴格查證 0 外部調用之純內部工具函式/私有方法**<br>*(Strictly Verified Internal Helpers)* | • `cli.py`: [`_resolve_enable_console`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L32-L47), [`_get_yscb_root`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L50-L58), [`_http_request`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L61-L80), [`_render_status_dashboard`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L184-L215)<br>• `config.py`: [`_parse_bool`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/config.py#L20-L34)<br>• `logger.py`: [`_extract_log_file_timestamp`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/logger.py#L21-L43), [`_safe_replace_file`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/logger.py#L46-L55), [`_resolve_safe_archive_path`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/logger.py#L107-L122), [`_close_active_handle_locked`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/logger.py#L157-L163)<br>• `master.py`: [`_initialize_daemon_environment`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L249-L260), [`_start_http_and_watcher_services`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L262-L283), [`_run_supervisor_main_loop`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L285-L300), [`_kill_worker_locked`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L356-L385), [`_ensure_ready_worker`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L459-L465), [`_stream_task_over_worker_pipe`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L467-L519), [`_spawn_worker_locked`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L541-L634), [`_idle_ttl_loop`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L636-L645), [`_write_state`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L647-L659), [`_cleanup_state`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L661-L667), [`_create_http_server`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L670-L784)<br>• `service.py`: [`_load_service_class_from_uri`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/service.py#L19-L54), [`_load_service_item`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/service.py#L156-L182)<br>• `streamer.py`: [`_flush_locked`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/streamer.py#L64-L94), [`_ensure_timer_locked`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/streamer.py#L96-L100), [`_on_timer`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/streamer.py#L102-L104), [`_StreamProxy`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/streamer.py#L147-L159)<br>• `watcher.py`: [`_scan_modules_dir`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/watcher.py#L16-L34), [`_is_core_transaction_locked`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/watcher.py#L77-L95), [`_poll_loop`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/watcher.py#L97-L121), [`_extract_affected_modules`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/watcher.py#L123-L138)<br>• `worker.py`: [`_prepare_execution_env`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/worker.py#L82-L95), [`_dispatch_command_with_captured_streams`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/worker.py#L97-L127) | 經全空間檢索確認：**0 外部跨模組引用**，純屬單檔或類別內部私有實作。 | **[直接破壞性收斂]**<br>無論 `Mode A` 或 `Mode B`，皆直接執行參數重構、階段拆解、同構合併或無狀態剝離，**嚴禁保留任何相容別名或轉發死代碼**。 |

---

## 2. 候選方案分析與對比 (Candidate Evaluation)

針對 `server` 模組發現之 `D1 ~ D5` 結構病灶（特別是 `master.py` 784 行多重職責耦合與跨檔案重複樣板），提出三種重構深度方案進行權衡：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：單檔內聯拆解與物理模組拆分 (`S1~S6` Full Track 標準手術)** | 1. 將 `master.py` 784 行按正交職責物理拆分為狀態與橫幅格式器、HTTP 路由處理器與 `MasterSupervisor` 核心編排（`S6`），並在 `master.py` 維持公開符號重匯出。<br>2. 對 `_spawn_worker_locked`、`worker_main`、`start`/`stop` 執行 `S1` 業務階段拆解與 `S3` NDJSON 管道讀取聚合。<br>3. 收斂 `logger.py`、`service.py`、`watcher.py` 之重複骨架與深層巢狀（`S2/S3/S4`）。 | • 徹底解除 `master.py` P0 巨型破窗檔案，單檔行數降至 $\le 450$ 行，最大函式降至 $\le 45$ 行。<br>• 100% 維持對 `core`、`knowledge-db` 與現有測試套件的相容性。<br>• 消除 Worker 管道讀取與日誌歸檔之結構性重複。 | • 涉及模組內新子檔案建立或跨檔移動，變更行數 $> 100$ 行，需走 Full Track 完整回歸驗證。 | ⭐⭐⭐⭐⭐<br>**(推薦首選)** |
| **方案 B：保守局部打磨 (`S1/S3/S4` 不拆檔)** | 僅在現有 8 個檔案內部進行長函式階段提取（`S1`）、衛語句扁平化（`S4`）與常數提取（`S5`），不拆分 `master.py`。 | • 零新增檔案，改動範圍完全封閉於各單檔內部。<br>• 實作速度極快。 | • `master.py` 仍將維持在 750+ 行，甚至因提取輔助函式而突破 800 行，無法根治 `D1` P0 巨型檔案破窗。 | ⭐⭐⭐☆☆ |
| **方案 C：維持現狀 (No-Op)** | 僅保留診斷報告作為架構參考，暫不動刀修改任何業務代碼。 | • 零修改風險與回歸成本。 | • `master.py` 持續累積控制平面、HTTP 協議與 CLI 視圖三方耦合技術債。 | ⭐⭐☆☆☆ |

---

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 `D1 ~ D5` 五維度分級診斷矩陣 (`Diagnostic Matrix`)

以下詳列對 `ys_codebase/source/server/` 全數業務檔案之五維度靜態診斷結果（共計 **P0：1 項**、**P1：11 項**、**P2：5 項**）：

| 編號 | 檔案路徑與行號座標 | 維度 | 嚴重度 | 具體結構病徵與根因分析 | 對應策略 |
| :---: | :--- | :---: | :---: | :--- | :---: |
| **F-01** | [`server/master.py:1-784`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L1-L784) | `D1` | **P0** | **巨型破窗檔案 (God File，784 行) 承載多重正交職責**：單一檔案同時混雜 ① 資料結構與磁碟狀態讀寫（`ServerDaemonState`, `read_daemon_state`）、② CLI 終端視覺格式化（`format_uptime`, `format_watcher_status`, `format_startup_banner`, `format_shutdown_summary` 共 135 行純字串組裝）、③ `MasterSupervisor` 進程監督與 Worker 管道管理、④ `_create_http_server` 與 `DispatcherHTTPHandler` 內嵌類別（115 行 HTTP 協議解析與 Chunked 編碼）。任何 UI 橫幅微調、HTTP 路由擴充或進程管理變更皆擠在同一檔案。 | `S6`, `S2` |
| **F-02** | [`server/master.py:541-634`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L541-L634) | `D1` / `D3` | **P1** | **超長方法且內嵌雙閉包執行緒 (`_spawn_worker_locked`，94 行)**：單一方法內混雜 ① 跨平台 `.venv` `site-packages` 與 `PYTHONPATH` 拼裝（L545-565）、② `subprocess.Popen` 啟動、③ 內嵌閉包函式 `_drain_stderr`（L583-599）、④ 內嵌閉包函式 `_read_ready`（L603-623）與超時握手清理。抽象層級嚴重混雜，且環境變數建構屬無狀態純運算卻綁定於方法內。 | `S1`, `S2` |
| **F-03** | [`server/master.py:670-784`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L670-L784) | `D1` / `D3` | **P1** | **深層函式內嵌類別與協定細節混雜 (`_create_http_server`，115 行)**：在函式內部動態定義 `DispatcherHTTPHandler`（縮排起始即達 2~4 層），其中 `_handle_post_dispatch`（L708-748）同時處理 JSON 解析、Workspace Root 比對、HTTP `Transfer-Encoding: chunked` 十六進位標頭底層位元組拼接（`f"{len(chunk_bytes):X}\r\n"`）與任務派發，違反 SLAP。 | `S1`, `S6` |
| **F-04** | [`server/master.py:467-519`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L467-L519) & [`583-623`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L583-L623) | `D3` | **P1** | **Worker NDJSON 管道讀取與日誌轉發邏輯結構性重複**：`_stream_task_over_worker_pipe`（L485-516）與 `_spawn_worker_locked._read_ready`（L605-620）重複編寫相同的「`proc.stdout.readline()` $\to$ `decode('utf-8', errors='replace').strip()` $\to$ `json.loads` $\to$ 攔截 `type == 'log'` 寫入 `self.logger.log(...)` $\to$ 終止條件判定」骨架。 | `S3` |
| **F-05** | [`server/worker.py:172-243`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/worker.py#L172-L243) | `D1` / `D3` | **P1** | **`worker_main` 長程序混雜多個職責階段（72 行，縮排 4 層）**：單一函式內同時包含進程標題設定、標準輸出入重導向、內嵌 `emit_fn` 閉包鎖、Worker 實例預熱與 `worker_ready` 發送、以及無限 IPC `readline` 命令解析迴圈（L208-236）。此外，L97-127 `_dispatch_command_with_captured_streams` 的命令路徑解析可進一步提煉。 | `S1`, `S4` |
| **F-06** | [`scripts/cli.py:83-181`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L83-L181) | `D1` / `D3` | **P1** | **CLI `start`（52 行）與 `stop`（45 行）混雜命令編排與底層輪詢等待迴圈**：`start` 混雜參數校驗、已運行檢查、組態載入、前台/背景分支與 30 次 `time.sleep(0.1)` 就緒探針迴圈（L125-132）；`stop` 混雜孤兒 `daemon.json` 清理、HTTP 優雅關機請求、20 次等待進程退出迴圈（L159-166）與強殺兜底摘要建構。 | `S1`, `S3` |
| **F-07** | [`server/logger.py:165-237`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/logger.py#L165-L237) | `D3` | **P1** | **日誌歸檔與時間戳提取邏輯在 3 個方法間重複**：`recover_and_open`（L180-185）、`archive_and_close`（L222-227）與 `get_expected_archive_path`（L230-237）重複執行「提取 `start_time_str` 或 `_extract_log_file_timestamp` $\to$ `_resolve_safe_archive_path` $\to$ `_safe_replace_file` + `clean_rolling_history`」同構流程。 | `S3` |
| **F-08** | [`server/service.py:19-54`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/service.py#L19-L54) & [`122-182`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/service.py#L122-L182) | `D1` / `D3` | **P1** | **深層巢狀與 URI 解析職責混雜**：① `load_from_contributes`（L141-152）在回退掃描 `.modules/*/contributes/server.json` 時達 **5 層縮排巢狀**（Arrow Anti-pattern）；② `_load_service_class_from_uri`（L19-54）將「字串分割正規化」與「雙階段 `importlib.import_module` 退避重試」耦合於單一函式；③ `_load_service_item`（L164-167）直接變異全域 `sys.path`。 | `S1`, `S4` |
| **F-09** | [`server/watcher.py:97-121`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/watcher.py#L97-L121) & [`16-34`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/watcher.py#L16-L34) | `D3` / `D4` | **P1** | **`_poll_loop` 雙重防抖條件重複與靜默吞噬回呼異常**：① `_poll_loop` 在防抖前後重複檢查 `not self._is_running or self._is_core_transaction_locked()` 並二次呼叫 `_scan_modules_dir`（縮排達 4 層）；② L120-121 `except Exception: pass` 完全靜默吞掉 `on_change_callback` 異常，導致重載失敗無跡可尋；③ `_scan_modules_dir`（L22-32）達 5 層縮排。 | `S4`, `D4` |
| **F-10** | [`scripts/cli.py:50-58`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L50-L58) & [`server/service.py:141-152`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/service.py#L141-L152) | `D5` | **P1** | **繞過 `core.vfs` 統一基礎設施抽象與重複路徑常數**：① `service.py:147` 與 `logger.py:30` 直接使用原生 `open() + json.load()`，未統一遵循 `core.vfs.read_json`（對比 `master.py:73` 已使用 `vfs.read_json`）；② `.cache/server/daemon.json`、`.cache/server/daemon.lock`、`.cache/server/log` 在 `cli.py:146,178,201`、`master.py:69,89,200,201`、`logger.py:86,89` 多處重複硬編碼拼接。 | `S3`, `S5` |
| **F-11** | [`server/master.py:222-247`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L222-L247) & [`764-774`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L764-L774) & [`scripts/cli.py:171-179`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L171-L179) | `D4` | **P1** | **跨模組/跨層傳遞鬆散無型別裸字典 (`Dict[str, Any]`)**：`get_status_dict`、`build_fallback_status_payload` 與 `shutdown_summary` 在 `master.py:766` 與 `cli.py:171` 兩處重複手動拼裝相同鍵名（`pid`, `worker_pid`, `uptime_seconds`, `tasks_executed`, `services_stopped`, `reason`, `archive_log`）的裸字典，缺乏統一結構化建構函式或 Dataclass 契約。 | `S5` |
| **F-12** | [`server/master.py:394-399`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L394-L399), [`server/worker.py:56,72,241`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/worker.py#L56), [`server/config.py:59`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/config.py#L59) | `D4` | **P1** | **過度寬泛之 `except Exception: pass` 靜默吞噬潛在錯誤**：`master.py`、`worker.py`、`watcher.py`、`streamer.py` 存在多處無日誌紀錄之 `except Exception: pass`。雖然針對 IPC 斷管或進程退出之 `OSError` 容錯合理，但對業務組態載入（`master.py:398`）或事件廣播（`worker.py:56,72`）使用無差別 `Exception` 吞噬會掩蓋非預期缺陷。 | `S3`, `D4` |
| **F-13** | [`server/master.py:117-179`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L117-L179) & [`scripts/cli.py:184-215`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L184-L215) | `D2` / `D1` | **P2** | **CLI 視覺格式化函式分散於 `master.py` 與 `cli.py` 兩處**：`format_startup_banner`、`format_shutdown_summary`、`format_uptime`、`format_watcher_status` 放在 `master.py`，而高度同質的 `_render_status_dashboard` 卻放在 `cli.py:184`，且兩邊重複格式化 Idle TTL 與 Watcher 狀態。 | `S2`, `S6` |
| **F-14** | [`server/master.py:367,626,638`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L367) & [`scripts/cli.py:125,159,231,250`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L125) | `D5` | **P2** | **散落之超時與輪詢魔術常數 (Magic Literals)**：如 Worker 握手超時 `3.0` 秒、Idle TTL 檢查週期 `2.0` 秒、CLI 啟動探針 `30 * 0.1` 秒、關機探針 `20 * 0.1` 秒、防抖 `500` ms 等直接硬編碼於迴圈與參數中，未提取為模組頂層具名常數。 | `S5` |
| **F-15** | [`server/logger.py:252`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/logger.py#L252) | `D2` | **P2** | **冗餘之動態屬性防禦 (`getattr(self, "echo_console", False)`)**：`self.echo_console` 已於 `__init__`（L94）明確初始化為 `bool` 實例屬性，L252 無須使用 `getattr` 反射。 | `S4` |
| **F-16** | [`server/watcher.py:25`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/watcher.py#L25) | `D5` | **P2** | **受監視副檔名元組硬編碼於內層迴圈**：`(".py", ".json", ".zip", ".dist-info")` 硬編碼於 `os.walk` 內層，宜提昇為模組級常數 `WATCHED_EXTENSIONS`。 | `S5` |
| **F-17** | [`server/streamer.py:73-79`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/streamer.py#L73-L79) | `D3` | **P2** | **`_flush_locked` 緩衝聚合樣板可簡化**：手動檢查 `if s_name not in consolidated` 並初始化清單，以及 L49 以單鍵字典 `{"stream": ..., "text": ...}` 儲存 tuple 資料，可改用輕量 `Tuple[str, str]` 提升高頻 `write` 效率並精簡聚合邏輯。 | `S5` |

---

### 3.2 類別/模組業務階段與狀態依賴分析（供 `S1` & `S2`）

#### 1. `MasterSupervisor`（[`server/master.py:182-667`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py#L182-L667)）
- **實例狀態依賴盤點（供 `S2` 無狀態邏輯剝離）**：
  - `_spawn_worker_locked`（L541-634）中，L542-570 的 **Worker 啟動命令、跨平台 `.venv` `site-packages` 路徑解析、`PYTHONPATH` 組合與 Windows `CREATE_NO_WINDOW` 旗標計算** 僅讀取常數設定 `self.yscb_root`，完全不變異實例狀態 $\rightarrow$ 可剝離為純函式 `_build_worker_popen_args(yscb_root: str) -> Tuple[List[str], Dict[str, str], int]`。
  - `_spawn_worker_locked` 內嵌之 `_drain_stderr(pipe, pid)`（L583-598）僅依賴 `self.logger` $\rightarrow$ 可提昇為類別方法或模組級輔助函式 `_start_worker_stderr_drainer(proc: subprocess.Popen, logger: ServerLogger) -> None`。
  - 檔案頂層之 `format_uptime`、`format_watcher_status`、`format_startup_banner`、`format_shutdown_summary`、`read_daemon_state`、`build_fallback_status_payload`（L46-179）完全無涉 `MasterSupervisor` 內部鎖與進程控制 $\rightarrow$ 可透過 `S6` 物理拆離至獨立子模組（如 `server/presenter.py` 或 `server/state.py`）。
- **長方法階段拆解藍圖（供 `S1` 主幹管線化）**：
  - `_spawn_worker_locked`（94 行）拆解為 3 個清晰階段：
    1. `_build_worker_spawn_env(self.yscb_root)`（準備跨平台命令與環境變數）
    2. `_start_worker_stderr_drainer(proc, self.logger)`（啟動非阻塞 stderr 排空執行緒）
    3. `_await_worker_ready_handshake(proc, timeout_sec=3.0)`（等待 `worker_ready` 事件並回傳服務清單）
  - `_create_http_server`（115 行）拆解：将 `DispatcherHTTPHandler` 提昇為獨立頂層類別（或拆至 `server/http_handler.py`），並將 Chunked NDJSON 編碼封裝為 `_write_chunked_ndjson(wfile, packet)` 與 `_finish_chunked_stream(wfile)`。

#### 2. `WarmWorker` & `worker_main`（[`server/worker.py:24-243`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/worker.py#L24-L243)）
- **狀態依賴與階段拆解（`S1` & `S2`）**：
  - `_prepare_execution_env`（L82-95）中計算 `host_dir` 的邏輯僅依賴 `yscb_root`，且 `worker_main`（L172-243，72 行）混雜了「IPC 輸出閉包建構」、「Worker 預熱與就緒廣播」與「stdin NDJSON 命令迴圈」。
  - 將 `worker_main` 拆解為：`_create_threadsafe_ipc_emitter(ipc_out)`（建立執行緒安全發射器）與 `_run_worker_ipc_loop(worker, in_io, emit_fn, yscb_root)`（純粹處理命令迴圈與錯誤防禦）。

#### 3. `scripts/cli.py`（[`scripts/cli.py:83-255`](file:///d:/repos/ys_codebase/ys_codebase/source/server/scripts/cli.py#L83-L255)）
- **階段拆解與同構聚合（`S1` & `S3`）**：
  - 提取 `_parse_ttl_option(cmd_bags) -> Tuple[Optional[float], bool]` 消化 `start` 的參數解析衛語句。
  - 提取 `_wait_for_daemon_ready(yscb_root, timeout_sec=3.0) -> Optional[ServerDaemonState]` 與 `_wait_for_process_exit(pid, timeout_sec=2.0) -> bool`，消除 `start` 與 `stop` 中的手寫 `for _ in range(N): time.sleep(0.1)` 輪詢迴圈。
  - 提取 `build_shutdown_summary(...)` 統一 `cli.py:171` 與 `master.py:766` 的關機摘要字典結構（`S5`）。

---

### 3.3 `S1 ~ S6` 外科手術重構處方箋 (`Refactoring Blueprint`)

1. **`S6` 正交職責之物理模組拆分（解決 F-01、F-10、F-11、F-13）**：
   - 將 [`server/master.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py)（784 行）拆解為三個單向依賴的正交模組：
     - **`server/state.py`（狀態契約與 CLI 視圖層，約 180 行）**：收攏 `ServerDaemonState`、統一快取路徑常數（`daemon.json`, `daemon.lock`, `log`）、`read_daemon_state`、`build_fallback_status_payload`、`build_shutdown_summary`，以及 `format_uptime`、`format_watcher_status`、`format_startup_banner`、`format_shutdown_summary` 與 `cli.py` 移入之 `render_status_dashboard`。
     - **`server/http_server.py`（HTTP 協議與 Chunked 串流路由層，約 140 行）**：收攏 `DispatcherHTTPHandler` 與 `_create_http_server`，將 Chunked 十六進位封包寫入抽離為獨立輔助方法，使路由分派（`/api/status`, `/api/dispatch`, `/api/reload`, `/api/shutdown`）扁平清晰。
     - **`server/master.py`（核心控制平面編排器，降至約 380 行）**：專注於 `MasterSupervisor` 進程生命週期、Worker 子進程監督、`_dispatch_lock` 序列化與 Idle TTL 迴圈；並於頂層重匯出 `ServerDaemonState`、`read_daemon_state`、`format_*` 等符號以確保 `Mode B` 100% 向下相容。
2. **`S1` & `S2` 業務階段拆解與無狀態邏輯剝離（解決 F-02、F-05、F-06、F-08）**：
   - 於 `master.py` 將 `_spawn_worker_locked`（94 行）拆分為 `_build_worker_spawn_env`（無狀態純函式）、`_start_worker_stderr_drainer` 與 `_await_worker_ready_handshake`，使主幹縮減至 $\le 25$ 行。
   - 於 `worker.py` 將 `worker_main`（72 行）拆離出 `_run_worker_ipc_loop`，消除 4 層 `while -> try -> if` 巢狀。
   - 於 `service.py` 將 `_load_service_class_from_uri` 拆分為 `_parse_class_uri(uri_str) -> Optional[Tuple[str, str]]`（純字串解析）與動態模組匯入；將 `load_from_contributes` 的 `.modules/` 目錄掃描回退拆為 `_scan_module_service_manifests(modules_dir)`，將縮排由 5 層壓降至 $\le 3$ 層。
3. **`S3` 跨方法同構模式聚合（解決 F-04、F-07）**：
   - 於 `master.py` 提取共用之 Worker stdout NDJSON 讀取器 `_iter_worker_ndjson_packets(proc, logger)`，自動攔截並轉發 `type == "log"` 封包，統一供給 `_await_worker_ready_handshake` 與 `_stream_task_over_worker_pipe` 使用。
   - 於 `logger.py` 提取 `_archive_current_log_locked() -> Optional[str]`，合併 `recover_and_open` 與 `archive_and_close` 中重複的時間戳解析、安全歸檔路徑計算、檔案替換與滾動歷史清理。
4. **`S4` & `S5` 控制流扁平化、常數集中與異常精確化（解決 F-09、F-12、F-14 ~ F-17）**：
   - 於 `watcher.py` 提煉 `_can_proceed_scan() -> bool` 衛語句簡化 `_poll_loop`，提取 `WATCHED_EXTENSIONS` 常數，並為 `on_change_callback` 異常加上 `logging.warning` 紀錄而非完全靜默吞噬。
   - 於 `service.py` 改用 `core.vfs.read_json` 取代手寫 `open() + json.load()`，對齊專案基礎設施慣例（`D5`）。

### 3.4 預期 Before / After 結構量化指標預估

| 量化指標 (Metric) | 重構前 (Before) | 預計重構後 (After) | 變化幅度 (Delta) | 結構改善說明 |
| :--- | :---: | :---: | :---: | :--- |
| **最大單一檔案行數 (`master.py`)** | `784 行` | `~380 行` | `-51.5%` | `S6` 拆離 `state.py` 與 `http_server.py`，徹底消除 P0 God File |
| **最大單一函式行數 (`_create_http_server` / `_spawn_worker_locked`)** | `115 行 / 94 行` | `≤ 40 行` | `-65.2%` | `S1` 業務階段拆解與 `DispatcherHTTPHandler` 頂層化 |
| **最大控制流縮排深度 (`service.py` / `watcher.py` / `master.py`)** | `5 層` | `≤ 3 層` | `-2 層` | `S4` 衛語句反轉與內部掃描輔助函式提取 |
| **剝離之無狀態純函式 / 聚合之重複樣板數** | `0` | `8 個` | `+8` | 含 Worker 環境建構、NDJSON 管道迭代器、日誌歸檔、輪詢等待器等 |
| **現有測試集對應與回歸保障** | `tests/test_*.py` | `100% Passed` | `100% 無損` | 執行 `python yscb.py dev check server` 與 `python yscb.py dev test server` |

---

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **推薦落地策略**：
  強烈建議採納 **「方案 A：單檔內聯拆解與物理模組拆分 (`S1~S6` 標準手術)」**。優先解決 [`server/master.py`](file:///d:/repos/ys_codebase/ys_codebase/source/server/server/master.py) 784 行之 P0 巨型破窗病灶（`F-01`），並同步收斂 `_spawn_worker_locked`、`worker_main`、`logger.py` 與 `service.py` 中的 P1 結構性重複與深層巢狀（`F-02` ~ `F-12`）。在重構期間嚴守防過度設計四大紅線與 `Mode B` 門面相容保護（於 `server.master` 保留原公開符號重匯出），確保對 `core` 熱派發與 `knowledge-db` 背景微服務 100% 零破壞。
- **後續行動與流轉出口銜接**：
  - **推薦流轉出口**：**出口 ①（立即原地升級實作）**——由於涉及 `server` 模組內跨檔重構與 `S6` 物理拆檔（總變更規模 $> 100$ 行），建議於主計畫統籌下走 **Full Track**（或子計畫實作軌道）推進 `S1 ~ S6` 無損重構，並以 `python yscb.py dev check server` 與 `python yscb.py dev test server` 完成回歸驗收。
