# 技術路線圖：常駐服務託管修復、IPC 管道隔離與生命週期加固 (`server_service_hosting_and_ipc_hardening_roadmap`) (Roadmap)

> 主題：常駐服務託管修復、IPC 管道隔離與生命週期加固 (`server_service_hosting_and_ipc_hardening_roadmap`)  
> 歸檔日期：2026-10-23  
> 狀態：Ready  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在對 `ys-codebase / module:server`（`v1.0.0.4`）進行全模組功能性與架構審查後，確認存在 **7 項功能缺陷與架構邊界問題（`S-01` ～ `S-07`）**：

1. **`S-01` [Critical] `server/service.py` 漏寫 `import os`，導致背景服務 100% 載入失敗且被靜默吞掉**：
   - `server/service.py` 全檔未匯入 `os`，當 `WarmWorker.pre_warm()` 呼叫 `self.service_manager.load_from_contributes(self.yscb_root)` 執行至第 72 行 `os.path.join(yscb_root, ".modules")` 時，100% 拋出 `NameError: name 'os' is not defined`。
   - 該例外被第 83 行 `except Exception:` 轉為 `logging.warning` 吞掉，導致任何模組透過 `contributes/server.json` 註冊的背景服務（如 `knowledge-db-worker`）在真實運行時永遠無法載入（`Background Svcs` 恆為 `0`）。
2. **`S-02` [High] `services` 擴充點在 `_format.json`、`README.md` 與 `service.py` 三方規格脫鉤，且忽略 `auto_start`**：
   - `contributes/_format.json`（L2–8）定義欄位為 `name`、`worker_class`、`description`、`auto_start`；但 `README.md`（L69–79）範例卻寫為 `"id"` 與 `"entry": "code.class://knowledge-db/service:KnowledgeDBServiceWorker"`。
   - `service.py:_load_service_item()`（L86–105）僅支援 `mod_path:ClassName` 或 `mod_path.ClassName` 純 Python 路徑，若模組照手冊帶入 `code.class://` 前綴或含連字號模組名（如 `knowledge-db`），`split(":", 1)` 會誤切為 `"code.class"` 導致匯入失敗。
   - `_format.json` 宣告了 `"auto_start": "bool? = true"`，但 `ServiceManager` 完全忽略該屬性，無條件啟動所有註冊服務。
3. **`S-03` [High] Worker `stdout` JSON IPC 管道易遭背景服務 `print` 污染，且停機時直接強殺導致 `service_manager.stop_all()` 永不執行**：
   - **IPC 管道污染**：`server/worker.py:worker_main()`（L169）直接使用原始 `sys.stdout` 作為傳給 Master 的 NDJSON IPC 管道。若任何背景服務執行緒在非任務執行期間呼叫 `print()` 或第三方套件寫入 `sys.stdout`，非 JSON 字串會直接寫入 `proc.stdout`，導致下次 `MasterSupervisor.dispatch_task()` 執行 `json.loads(line_str)`（`master.py:364`）時拋出 `JSONDecodeError` 而弄崩 CLI 任務。
   - **優雅停機失效**：`worker_main()` 雖設計了收到 `{"action": "exit"}` 時跳出迴圈並於 `finally:` 呼叫 `worker.service_manager.stop_all(timeout_sec=1.5)`（`worker.py:211`），但 `MasterSupervisor._kill_worker_locked()`（`master.py:259–274`）從未發送 `{"action": "exit"}`，而是直接呼叫 `kill_process_tree(proc.pid)` 強殺進程，導致背景服務永遠沒機會執行 `stop()` 釋放鎖或刷寫索引。
4. **`S-04` [Medium] `MasterSupervisor._write_state()` 重置 `start_time` 導致 Uptime 失真，且 Master 冗餘實例化空的 `ServiceManager`**：
   - `server/master.py:_write_state()`（L480）寫入 `daemon.json` 時傳入 `start_time=time.time()` 而非 `self._start_time`，導致每次重啟 Worker 或派發任務更新狀態檔時，Master 的啟動時間被重置為當下時間。
   - Master 已定調為純控制平面（背景服務全由 WarmWorker 託管），但 `MasterSupervisor.__init__`（L137）與 `stop()`（L235）仍保有未使用的 `self.service_manager = ServiceManager()`。
5. **`S-05` [Medium] 違反 `.modules/` 剛性架構約束，向 Worker 注入 `source/` 開發空間路徑**：
   - `server/master.py:_spawn_worker_locked()`（L405–407）與 `server/worker.py`（L22–25）將 `source/`、`source/core`、`source/server` 注入 `PYTHONPATH` 與 `sys.path`，違反系統「僅允許 `.modules/` 運行時空間載入執行，嚴禁向 `sys.path` 注入 `source/` 空間」的剛性架構約束。
6. **`S-06` [Medium] `contributes/core.json` 漏註冊 `events` 清冊、Worker 重複廣播事件，且 `server reload` 未同步刷新 `ServerConfig`**：
   - `server/worker.py:pre_warm()`（L46–47, L66）廣播了 `server_worker_warming`、`worker_warming`（新舊名重複發送兩次）與 `server_worker_ready`，但 `contributes/core.json` 未宣告 `"events"` 節點，`python yscb.py event list` 無法查閱。
   - 當開發者更新 `config://server`（如調整 `idle_timeout_sec`）後執行 `python yscb.py server reload`，Master 僅重啟 Worker 子進程，未重新讀取 `ServerConfig.load()` 更新 Master 自身的 `self.idle_timeout_sec`。
7. **`S-07` [Low] `scripts/cli.py` 底部殘留過渡期死代碼 `_handle_start`**：
   - `scripts/cli.py`（L258–280）的 `_handle_start()` 為早期尚未切換至 `CmdBags` 與 `OptionResolver` 前的舊版包裝函式，生產環境已無任何呼叫點。

### 1.2 現況與影響範圍評估
- **架構定調：打通 `core.contributes` 標準背景服務託管鏈路，落實 Worker IPC 通道硬隔離與優雅停機協議，並嚴格對齊 `.modules/` 運行時剛性邊界**：
  1. **100% SDK 驅動之服務發現（SDK-Driven Service Hosting）**：`ServiceManager` 改由 `core.contributes.get("server", "services")` 讀取已合併之服務宣告，完整支援 `auto_start`、模組名正規化與 `code.class://` / `code.func://` 符號解析。
  2. **零污染 IPC 管道與兩階段優雅停機（Dedicated IPC Handle & Graceful Exit Handshake）**：將 Worker 內部預設 `sys.stdout` 重導向至 `sys.stderr`，保留私有 `_ipc_stdout` 專供 NDJSON 封包寫出；Master 終止 Worker 前先發送 `{"action": "exit"}` 握手等待 `stop_all()` 完成，逾時才兜底強殺。
  3. **純淨控制平面與剛性邊界合規**：清除 Master 上的冗餘 `ServiceManager`、修復 `start_time` 持久化、移除所有 `source/` 路徑注入、補齊 `events` 註冊與 `reload` 組態熱刷新。

### 1.3 核心根因
1. **`ServiceManager` 未接入 `core.contributes` 聚合快取且異常被過度吞沒**：`service.py` 手寫目錄掃描卻漏匯入 `os`，外層又以寬泛 `except Exception:` 靜默吞掉 `NameError`，導致功能失效卻未在啟動階段報錯。
2. **單一標準輸出通道混用（Control IPC vs. Standard Output Multiplexing Hazard）**：子進程直接以全域 `sys.stdout` 作為 IPC 管道，未防範背景執行緒在非 `DebouncedIOStreamer` 攔截期間的標準輸出寫入。
3. **進程終止缺少應用層握手階段**：`_kill_worker_locked()` 直接跳至作業系統層級 `kill_process_tree`，跳過了 `worker.py` 已實作的 `{"action": "exit"}` 應用層退場迴圈。

---

## 2. 候選架構方案對比 (Candidate Solutions)

針對 `S-01 / S-02`（背景服務載入機制）與 `S-03`（Worker IPC 通道隔離與停機握手），對比以下三種方案：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：最小修補（僅加 `import os`，維持手動讀檔與直接 `kill_process_tree`）** | 於 `service.py` 補上 `import os`，不改動 IPC 通道與停機流程 | 僅改 2 行代碼 | 1. 無法支援 `config://server/contribute.json` 專案級覆寫與 `auto_start`<br/>2. 背景服務 `print` 仍會打崩 Master JSON 解析<br/>3. 背景服務 `stop()` 依然永遠不會執行 | ⭐️⭐️ |
| **方案 2：另開獨立 Socket 作為 Worker IPC 管道** | 捨棄 `stdin/stdout` 管道，讓 Worker 再綁定一個隨機 TCP Port 與 Master 通訊 | 徹底避開 `stdout` 混用 | 增加額外本地 Port 綁定、認證與防火牆開銷，違反輕量單子進程管道設計 | ⭐️⭐️⭐️ |
| **方案 3：`core.contributes` 統一載入 ＋ 底層 `_ipc_stdout` 轉向隔離 ＋ `exit` 握手停機（推薦採納）** | 1. `ServiceManager` 透過 `core.contributes.get("server", "services")` 載入並落實 `auto_start` 與類別路徑正規化。<br/>2. `worker_main` 啟動即保存私有 `_ipc_stdout = sys.stdout` 並執行 `sys.stdout = sys.stderr`，確保任何背景執行緒 `print` 皆走 `stderr` 進入 `ServerLogger`。<br/>3. `_kill_worker_locked` 先寫入 `{"action": "exit"}\n` 並 `proc.wait(timeout=1.0)`，逾時才呼叫 `kill_process_tree`。 | 1. 零額外 Socket 開銷即可 100% 杜絕 IPC 管道污染<br/>2. 確保背景服務 `stop_all()` 100% 優雅執行<br/>3. 與 `core.contributes` 生態系完全對齊 | 需同步更新 `service.py`、`worker.py`、`master.py`、`scripts/cli.py` 與 `README.md` | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1：最小修補 | 方案 2：另開獨立 TCP Socket | 方案 3：SDK 載入 ＋ `_ipc_stdout` 隔離 ＋ `exit` 握手（採納） |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 高 | 中 | **極高**（100% Python 標準庫內閉環實現） |
| **IPC 穩定度與抗干擾能力** | 低（背景執行緒 `print` 即崩潰） | 高 | **極高**（私有 `_ipc_stdout` 句柄隔離，背景雜訊自動導向 `stderr` 日誌） |
| **背景服務資料安全性** | 低（強殺進程易損毀背景索引） | 中 | **極高**（兩階段 `exit` 握手保證 `stop_all()` 優雅落盤） |
| **落地難度 (Implementation)** | 極低 | 高 | **低**（聚焦於 `server` 模組內部 5 個檔案的精準重構） |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

### 4.1 `S-01` & `S-02` 背景服務載入器修復與 Schema 統一 (`server/service.py`, `contributes/_format.json`, `README.md`)
1. **補齊 `import os` 並優先透過 `core.contributes` 載入服務（含 `__provider__` 溯源與 `.modules/<provider>` 路徑注入防呆）**：
   - 於 `server/service.py` 頂部補齊 `import os`。
   - `ServiceManager.load_from_contributes(yscb_root)` 優先呼叫 `core.contributes.get("server", "services", default=[])` 取得已聚合之服務清單，並自每個項目讀取 `provider = item.get("__provider__", item.get("provider", "unknown"))`（保留 `.modules/*/contributes/server.json` 掃描作為無快取時的 fallback）。
   - **關鍵路徑注入防呆**：由於連字號命名模組（如 `knowledge-db`）在 `.modules/` 下之實體路徑為 `.modules/knowledge-db/knowledge_db/service.py`，單靠將 `.modules` 加入 `sys.path` 無法直接匯入 `knowledge_db.service`。因此於 `_load_service_item(item, provider, yscb_root)` 呼叫 `importlib.import_module()` 前，**強制先將 `os.path.join(yscb_root, ".modules", provider)` 插入 `sys.path`**（比照 `dispatcher.py:dispatch_local` 之 `mod_root` 注入機制），確保跨模組服務類別 100% 可匯入。
2. **支援多格式類別定址與 `auto_start` 生命週期控制**：
   - 於 `_load_service_item(item, provider, yscb_root)` 中：
     - 同時相容 `item.get("worker_class")` 與 `item.get("entry")`，以及 `item.get("name")` 與 `item.get("id")`（確保 `README.md` 與 `_format.json` 雙向相容，並將 `README.md` §2.2 範例統一校正為 `_format.json` 標準欄位 `name` / `worker_class` / `auto_start`）。
     - 若字串帶有 `code.class://` 或 `code.func://` 前綴，先剝除協議頭並將模組路徑首段的連字號 `-` 轉為底線 `_`（例如 `code.class://knowledge-db/service:KnowledgeDBServiceWorker` $\to$ 模組 `knowledge_db.service`、類別 `KnowledgeDBServiceWorker`），再透過 `importlib.import_module` 載入實例化。
     - 於 `self._metadata[service_name]` 記錄 `"auto_start": bool(item.get("auto_start", True))`。
   - 於 `start_all(context)` 中檢查 `meta.get("auto_start", True)`，僅自動啟動 `auto_start=True` 之服務。

### 4.2 `S-03` Worker `stdout` IPC 管道硬隔離與兩階段優雅停機 (`server/worker.py`, `server/master.py`)
1. **`worker_main` 私有 IPC 通道隔離與執行緒安全寫入鎖（`server/worker.py` L162–180）**：
   - 進入 `worker_main` 時先保存 `orig_stdout = sys.stdout` 與 `ipc_out = out_stream or orig_stdout`，隨即執行 **`sys.stdout = sys.stderr`**（並於 `worker_main` 的 `finally:` 區塊還原 `sys.stdout = orig_stdout`）。
   - 建立 `ipc_lock = threading.Lock()`，`emit_fn` 在 `with ipc_lock:` 保護下獨佔寫入 `ipc_out` 並 `flush()`，防止主迴圈、`DebouncedIOStreamer` 定時執行緒與背景服務日誌並發寫入時發生 NDJSON 行交錯（Interleaved Writes）；而在 `execute_task()` 期間，`DebouncedIOStreamer` 攔截 `sys.stdout` 與 `sys.stderr` 並透過 `emit_fn` 發送 `terminal_stream` 封包，退出 `with streamer:` 後自動還原為 `sys.stderr`。如此可 100% 保證背景服務執行緒在任何時刻呼叫 `print()` 均只會進入 `sys.stderr`（由 Master 的 `_drain_stderr` 安全收錄至日誌），絕不污染 `ipc_out` JSON Lines 管道。
2. **`_kill_worker_locked` 兩階段優雅停機握手（`server/master.py` L259–274）**：
   - 第一階段（應用層優雅握手）：若 `proc.stdin` 可寫且進程存活，先寫入 `b'{"action": "exit"}\n'` 並 `flush()`，接著呼叫 `proc.wait(timeout=min(timeout_sec, 1.5))`，讓 Worker 正常跳出迴圈並執行 `finally: worker.service_manager.stop_all(timeout_sec=1.5)`。
   - 第二階段（作業系統層兜底強殺）：僅當 `proc.wait()` 逾時或拋出例外時，才呼叫 `kill_process_tree(proc.pid, timeout_sec=timeout_sec)` 強制終止進程樹，最後關閉 `stdin/stdout/stderr` 管道。

### 4.3 `S-04` & `S-05` Master 狀態準確性修復與 `.modules/` 剛性邊界對齊 (`server/master.py`, `server/worker.py`)
1. **修復 `_write_state()` 的 `start_time` 並移除 Master 冗餘 `ServiceManager`（`S-04`）**：
   - 將 `server/master.py:_write_state()`（L480）之 `start_time=time.time()` 修正為 `start_time=self._start_time`。
   - 移除 `MasterSupervisor.__init__` 中的 `self.service_manager = ServiceManager()`、`stop()` 中的 `self.service_manager.stop_all()`，以及 `get_status_dict()` / `/api/shutdown` 中對 `self.service_manager` 的無效回退。
2. **清除 `source/` 開發空間路徑注入（`S-05`）**：
   - 於 `server/master.py:_spawn_worker_locked()`（L401–408）中，移除 `os.path.join(self.yscb_root, "source")`、`source/core`、`source/server`，僅保留 `self.yscb_root`、`.modules`、`.modules/core`、`.modules/server` 與私有 `.venv` `site-packages`。
   - 於 `server/worker.py`（L19–25）中，移除將 `_source_dir` 注入 `sys.path` 的邏輯，嚴格遵守 `.modules/` 運行時剛性架構約束。
   - 於 `WarmWorker.execute_task()` 中，確保每次讀取指令註冊表時若 `_GLOBAL_REGISTRY` 尚未初始化或 Worker 剛重啟皆以 `.modules/` 為唯一真理來源。

### 4.4 `S-06` & `S-07` 生命週期事件宣告、Reload 組態同步與死代碼清理 (`contributes/core.json`, `server/worker.py`, `server/master.py`, `scripts/cli.py`)
1. **補齊 `contributes/core.json` 之 `events` 宣告並收斂重複事件廣播（`S-06`）**：
   - 於 `server/contributes/core.json` 新增 `"events"` 陣列：
     ```json
     "events": [
       { "server_worker_warming": "當常駐 Warm Worker 子進程啟動並開始預熱環境時觸發" },
       { "server_worker_ready": "當常駐 Warm Worker 完成預熱與背景服務初始化時觸發" }
     ]
     ```
   - 於 `server/worker.py:pre_warm()` 移除舊版重複的 `events.broadcast("worker_warming", ...)`，統一使用標準命名的 `server_worker_warming` 與 `server_worker_ready`。
2. **`server reload` 同步熱刷新 `ServerConfig`（`S-06`）**：
   - 於 `MasterSupervisor.restart_worker()`（或 `/api/reload` 處理常式）中，同步呼叫 `cfg = ServerConfig.load(workspace_root=self.yscb_root)` 更新 `self.idle_timeout_sec = cfg.idle_timeout_sec` 與 `self._last_active_time = time.time()`。
3. **移除 `scripts/cli.py` 過渡期死代碼 `_handle_start`（`S-07`）**：
   - 刪除 `scripts/cli.py` 第 258–280 行的 `_handle_start()` 函式（並於後續測試集純化時將舊測試呼叫點統一升級為 `start(CmdBags(...))`）。

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 列為 `Ready` 技術路線圖，以單次版本迭代（如 `v1.0.0.5` 或 `v1.0.1.0`）一次性修復背景服務託管斷鏈、加固 Master/Worker IPC 隔離，並消除違反 `.modules/` 剛性約束之路徑注入。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1：背景服務託管引擎修復與 Schema 對齊（`S-01`、`S-02`）**
   - 修復 `server/service.py` 的 `import os` 缺失，接入 `core.contributes.get("server", "services")`，支援 `auto_start` 與 `code.class://` 類別解析，並對齊 `README.md` 與 `contributes/_format.json`。
2. **Stage 2：Worker IPC 通道隔離與兩階段優雅停機（`S-03`、`S-04`、`S-05`）**
   - 於 `server/worker.py` 實作 `_ipc_stdout` 獨立句柄與 `sys.stdout -> sys.stderr` 重導向，並移除 `source/` 路徑注入。
   - 於 `server/master.py` 實作 `_kill_worker_locked` 的 `{"action": "exit"}` 優雅停機握手、修正 `_write_state` 的 `start_time=self._start_time`，並移除 Master 冗餘的 `ServiceManager`。
3. **Stage 3：事件契約註冊、Reload 組態同步與 CLI 清理（`S-06`、`S-07`）**
   - 於 `contributes/core.json` 補齊 `events` 宣告、統一 `worker.py` 預熱事件名稱、在 `restart_worker()` 同步刷新 `ServerConfig`，並移除 `scripts/cli.py:_handle_start` 死代碼。
