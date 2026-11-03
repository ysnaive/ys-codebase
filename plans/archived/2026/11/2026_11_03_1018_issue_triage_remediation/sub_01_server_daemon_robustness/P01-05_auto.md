# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：Server 與 Daemon 生命週期穩健性修復  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Completed  
> 模型：Claude Opus 5.5 (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 搶占式 worker 重啟/停止 | `restart_worker()` 與 `stop()` 不先取 `_dispatch_lock`；先於 `_worker_lock` 內強殺現役 worker（使阻塞中 `readline()` 得 EOF 而令進行中 dispatch 回傳 1 並釋放 `_dispatch_lock`），之後才取 `_dispatch_lock` 再 spawn 新 worker。卡住的 worker 存在時 `restart_worker()` 於 `kill 逾時 + 5s` 內返回 | P0 | [P00:DR-03] |
| **FR-02** | status 回報執行中指令 | `get_status_dict()` 新增 `current_task: {module, args, started_at, elapsed_sec} \| None`；`server status` 儀表板顯示 `Current Task` 列；`server/contributes/core.json` 之 `status.server_compatible` 改 `false`；`get_status_dict()` 不取 `_dispatch_lock` | P0 | [P00:DR-03] |
| **FR-03** | 實證回收偵測 | 新增 `core.platform.daemon_probe`：auto-spawn 時記錄 `{pid, spawned_at, env_fingerprint}` 至 `cache://server/spawn_probe.json`；daemon 正常關閉時 `mark_clean_exit()`；下次判定時若記錄之 pid 已死、無 clean_exit、且 daemon 不活躍，`reaped_count += 1`；同一 fingerprint `reaped_count >= 2` 即判不可常駐；任一次 clean exit 歸零 | P1 | [P00:DR-07] |
| **FR-04** | POSIX 能力判定接入 | `can_spawn_background_daemon()` 判定順序：`YSCB_FORCE_DAEMON=1` → True；`YSCB_NO_DAEMON=1` → False；Windows 既有 Job 探針；POSIX 依 FR-03 判定（需傳入 `yscb_root`；未傳入時維持 True） | P1 | [P00:DR-07], UD-02 |
| **FR-05** | 提示不改 exit code | 判定不可常駐時印 [BLOCKER] 一次、照常冷派發、原 exit code 不變（非嚴格模式） | P1 | UD-01 |
| **FR-06** | readiness 逾時非零 | `server start -d` 輪詢逾時且 spawn 之 pid 已死時回傳 1；pid 仍活著則印「仍在啟動中」並回傳 0 | P1 | UD-03 |
| **FR-07** | `strict_hot_dispatch` | `ServerConfig`/模板新增 `strict_hot_dispatch: false`。為 `true` 且指令 `server_compatible=true`、`enable=true` 時：熱派發失敗 →（可常駐且 `auto_spawn=true`）auto-spawn 並等待 daemon 活躍（≤ 10s）後重試熱派發一次 → 仍失敗則印 strict [BLOCKER]、回傳 1、不冷派發。`server_compatible=false` 指令不受影響；`enable=false` 時嚴格模式失效 | P1 | [P00:DR-04], [P00:DR-06] |
| **FR-08** | [BLOCKER] 文案統一 | `_print_agent_daemon_blocker(strict: bool)` 兩種文案（advisory：冷派發兜底；strict：已阻斷）；`yscb-cli-guide` SKILL.md §1.3 改寫為 `strict_hot_dispatch` 與實際文案 | P2 | [P00:DR-04] |
| **FR-09** | 兩段式 worker 握手 | worker 啟動即送 `{"type":"worker_alive"}`，完成 pre_warm 後送 `worker_ready`。master 等 alive ≤ `worker_alive_timeout_sec`（預設 5.0），逾時判失敗並拋 `WorkerSpawnError`；alive 後狀態 `warming`，背景執行緒等待 ready（存活即無上限）；dispatch 於 warming 期間阻塞等待 ready（或 worker 死亡即回傳 1） | P1 | [P00:DR-08] |
| **FR-10** | status 顯示預熱 | `get_status_dict()` `state ∈ {warming, ready, restarting}`，warming 時含 `warming_elapsed_sec` | P1 | [P00:DR-08] |
| **FR-11** | worker 程序樹終止 | POSIX worker 以 `start_new_session=True` 啟動；新增 `terminate_popen_tree(proc, timeout_sec)`：`killpg` SIGTERM → `proc.wait(timeout)` → SIGKILL → `proc.wait`，由 Popen 自行回收；master worker 存活判定改用 `proc.poll()` | P1 | T-05 |
| **FR-12** | 載入例外攔截 | `dispatch_local` 之 `exec_module` 納入 try：失敗時自 `sys.modules` 移除半初始化模組、印 `[yscb] Error loading CLI for '<module>': <ExcType>: <msg>`、回傳 1；`yscb.py` `except ImportError` 僅包 `from core.commands import dispatch` | P2 | T-12 |
| **FR-13** | 鎖檔保留與 EEXIST 重試 | `_cleanup_state()` 僅刪 `state_file`；`InterProcessLock.acquire()` 之 `os.open` 遇 `FileExistsError` 最多重試 3 次（間隔 50ms，重試時改以不帶 `O_CREAT` 開啟），其他 errno 照拋 | P2 | UD-05 |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 無進行中 dispatch 時 restart | 直接 kill + spawn，行為同既有 |
| **EC-02** | 被搶占之 dispatch | 回傳 exit 1 + `task_finish.error="Worker terminated by restart/stop"`，不得重試、不得死鎖 |
| **EC-03** | `spawn_probe.json` 損壞/不可讀 | 視為無紀錄（不判不可常駐），覆寫新紀錄 |
| **EC-04** | Windows Host 與 Linux Guest 共用 `.cache` | 以 `env_fingerprint`（`socket.gethostname()` + `sys.platform`）分鍵儲存，互不污染 |
| **EC-05** | daemon 崩潰（非環境回收）1 次 | 只累計 1，不判不可常駐（門檻 2） |
| **EC-06** | strict 模式下 `server start` 等冷派發指令 | `server_compatible=false` 照常執行 |
| **EC-07** | worker alive 後於 warming 中死亡 | 等待中之 dispatch 回傳 1；下次請求重新 spawn |
| **EC-08** | worker 從未送 alive（啟動即崩潰） | `WorkerSpawnError`，dispatch 回傳 1 並帶錯誤訊息，不回傳 PID 0 冒充 |
| **EC-09** | `exec_module` 拋非 ImportError（如 SyntaxError） | 同 FR-12 攔截並回傳 1 |
| **EC-10** | EEXIST 重試 3 次仍失敗 | 拋出原始 `FileExistsError` |
| **EC-11** | `daemon.lock` 長期存在 | 判定活躍與否一律以能否取得鎖為準，既有 probe 邏輯不變 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴 | 僅標準庫；`core.platform.daemon_probe` 不得 import `server` |
| **NFR-02** | 效能 | 非嚴格模式下每次 CLI 額外成本 ≤ 1 次 JSON 讀取 + 1 次 pid 存活檢查 |
| **NFR-03** | 相容 | Windows 既有 Job 探針與行為不變；新組態鍵皆有預設值，舊組態檔可直接載入 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `_try_hot_dispatch` 以 `YSCB_DISPATCH_TIMEOUT`（120s）為 socket 讀取逾時，逾時即降級冷派發，可能導致長時間無輸出之任務被重複執行；本計畫不處理，登記至 sub_04（偏差表 DEV-01）。
- **`[!NOTE]`** `is_process_alive()` 內含 `os.waitpid(WNOHANG)`，對自身子進程會搶走 Popen 回收；master 對 worker 一律改用 `proc.poll()`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
CLI dispatch(argv)
 ├─ cmd.server_compatible?
 │   ├─ yes → _try_hot_dispatch ─ok→ return
 │   │         └─fail→ strict_hot_dispatch?
 │   │               ├─ yes → can_spawn(yscb_root)? → auto-spawn + wait ≤10s → retry hot
 │   │               │        └─ still fail → [BLOCKER strict] → return 1
 │   │               └─ no  → (cold path below)
 │   └─ no
 ├─ _maybe_auto_spawn_server → can_spawn(yscb_root)
 │        ├─ False → [BLOCKER advisory] once
 │        └─ True  → daemon_probe.record_spawn(pid) ; spawn_detached
 └─ dispatch_local (exec_module guarded)

can_spawn: FORCE → NO_DAEMON → win32 Job probe → POSIX daemon_probe.is_reaping_env()
Master.stop / idle TTL / reload → daemon_probe.mark_clean_exit()

Worker handshake: spawn → [worker_alive ≤5s] → state=warming → [worker_ready] → state=ready
restart/stop: _worker_lock{terminate_popen_tree} → (blocked readline EOF releases _dispatch_lock) → _dispatch_lock{spawn}
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | FR-12：收斂 `except ImportError` |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | FR-05/07/08/12：strict 分流、blocker 參數化、exec_module 攔截、spawn 紀錄 |
| `ys_codebase/source/core/core/platform/process.py` | Modify | FR-04/11：`can_spawn_background_daemon(yscb_root=None)`、`terminate_popen_tree` |
| `ys_codebase/source/core/core/platform/daemon_probe.py` | New | FR-03：實證回收偵測 |
| `ys_codebase/source/core/core/platform/__init__.py` | Modify | 匯出新函式 |
| `ys_codebase/source/core/core/platform/lock.py` | Modify | FR-13：EEXIST 重試 |
| `ys_codebase/source/server/server/master.py` | Modify | FR-01/02/09/10/11/13：搶占、current_task、兩段握手、popen 終止、不刪鎖、clean exit |
| `ys_codebase/source/server/server/worker.py` | Modify | FR-09：送 `worker_alive` |
| `ys_codebase/source/server/server/config.py` | Modify | FR-07/09：`strict_hot_dispatch`、`worker_alive_timeout_sec` |
| `ys_codebase/source/server/configurable/config.project.json` | Modify | 新鍵預設值 |
| `ys_codebase/source/server/contributes/core.json` | Modify | FR-02：`status.server_compatible=false` |
| `ys_codebase/source/server/scripts/cli.py` | Modify | FR-02/06/10：儀表板、readiness 回傳值 |
| `ys_codebase/source/agents-workflow/assets/skills/yscb-cli-guide/SKILL.md` | Modify | FR-08 |
| `ys_codebase/source/core/tests/test_platform.py`, `test_core_commands.py` | Modify | 測試 |
| `ys_codebase/source/server/tests/test_server.py`, `test_server_config.py` | Modify | 測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 實證偵測置於 `core.platform`（非 `server`），因 dispatcher 屬 core 且不得依賴 server（NFR-01）；`server` 透過 import core 呼叫 `mark_clean_exit`。
- **[P02:DR-02]** 搶占以「殺 worker 解除 readline」實現，而非 readline 加逾時，避免誤殺合法長任務（[P00:DR-03]）。
- **[P02:DR-03]** dispatcher 讀取 `strict_hot_dispatch` 沿用 `_read_server_spawn_config` 直讀 JSON（core 不 import server.config），擴充為回傳具名結構。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# core/platform/daemon_probe.py
PROBE_REL_PATH: str  # ".cache/server/spawn_probe.json"
REAP_THRESHOLD: int = 2
def env_fingerprint() -> str: ...
def record_spawn(yscb_root: str, pid: int) -> None: ...
def mark_clean_exit(yscb_root: str) -> None: ...
def is_reaping_env(yscb_root: str, daemon_active: Optional[bool] = None) -> bool: ...  # None 時延遲探測
def is_daemon_lock_held(yscb_root: str) -> bool: ...

# core/platform/process.py
def can_spawn_background_daemon(force_reprobe: bool = False, yscb_root: Optional[str] = None) -> bool: ...
def terminate_popen_tree(proc: subprocess.Popen, timeout_sec: float = 2.0) -> bool: ...

# core/commands/dispatcher.py
@dataclass(frozen=True)
class _ServerSpawnConfig: enabled: bool; auto_spawn: bool; strict_hot_dispatch: bool
def _read_server_spawn_config(yscb_abs: str) -> _ServerSpawnConfig: ...
def _print_agent_daemon_blocker(strict: bool = False) -> None: ...
def _maybe_auto_spawn_server(host_dir: str, yscb_abs: str) -> None: ...
@dataclass(frozen=True)
class _HotDispatchResult: exit_code: Optional[int]; accepted: bool  # accepted=請求已送達 server
def _hot_dispatch_attempt(module_name, cmd_path_or_name, args, yscb_abs) -> _HotDispatchResult: ...
def _try_hot_dispatch(module_name, cmd_path_or_name, args, yscb_abs) -> Optional[int]: ...  # 薄包裝，非嚴格模式行為不變
def _strict_hot_dispatch_or_block(module_name, cmd_path, sub_args, host_dir, yscb_abs) -> int: ...  # 僅對 accepted=False 重試

# server/server/master.py
class WorkerSpawnError(RuntimeError): ...
class MasterSupervisor:
    def _spawn_worker_locked(self) -> int  # raises WorkerSpawnError
    def _wait_worker_ready(self, timeout_sec: Optional[float] = None) -> bool
    def get_status_dict(self) -> Dict[str, Any]  # + current_task, warming_elapsed_sec

# server/server/config.py
DEFAULT_STRICT_HOT_DISPATCH: bool = False
DEFAULT_WORKER_ALIVE_TIMEOUT_SEC: float = 5.0
```

- **錯誤與例外契約 (Error & Exception Contracts)**：`WorkerSpawnError` 由 `dispatch_task` 攔截轉 `task_finish(exit_code=1, error=...)`；`restart_worker` 失敗回傳 0 改為記錄錯誤並拋出 `WorkerSpawnError`（HTTP 層轉 500）；`daemon_probe` 全部 I/O 錯誤內部吞並視為無紀錄（EC-03，屬可降級之觀測性資料，非業務錯誤）；`lock.acquire` 僅吞 `FileExistsError` 重試。
- **階段決策紀錄**：`[P03:DR-01]` `can_spawn_background_daemon` 新增 `yscb_root` 為關鍵字選配參數，舊呼叫端相容（NFR-03）；POSIX 判定結果不進程級快取（daemon 狀態會變），Windows 維持快取。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-13 皆已於介面簽名對齊
- [x] **邊界防護**：EC-01 ~ EC-11 皆有具體處理
- [x] **依賴純淨**：僅標準庫，core 不依賴 server
- **靈魂拷問與防護解法**：
  - 搶占 kill 期間 dispatch 執行緒同時讀 stdout？→ readline 得 EOF/ValueError 後返回 1；pipe close 於 kill 後執行，以 try 包覆。
  - warming 無上限是否會讓 dispatch 永久等待？→ 等待條件含 `proc.poll() is None`，worker 死亡即返回；客戶端仍有 `YSCB_DISPATCH_TIMEOUT`。
  - 回收偵測在桌機誤判？→ 只在「auto-spawn 後未經 clean exit 即死亡」累計，桌機 daemon 以 idle TTL 正常退出會寫 clean_exit；`kill -9` 手動殺 2 次會誤判，可由 `YSCB_FORCE_DAEMON=1` 或任一次正常關閉歸零。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/server/README.md` | Modify | `strict_hot_dispatch`、`worker_alive_timeout_sec`、status current_task |
| **專題手冊** | `docs/core/` 平台/派發相關頁 | Modify | 實證回收偵測與 `YSCB_FORCE_DAEMON` |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 搶占式重啟、兩段握手、鎖檔不刪 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 新增/變更介面 |
| **發布日誌** | `CHANGELOG.md` | Modify | P07 結案時追加 |

- **決策定稿**：**[P04:DR-01]** 文檔於 P07 三層對齊時交付；本階段僅同步 Docstring 與 SKILL.md。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：`daemon_probe.py` + `process.py`（FR-03/04/11）
- [x] **TASK-02**：`lock.py` EEXIST 重試（FR-13）
- [x] **TASK-03**：`dispatcher.py` + `yscb.py`（FR-05/07/08/12）
- [x] **TASK-04**：`server` config / contributes / worker / master / cli（FR-01/02/06/09/10/11/13）
- [x] **TASK-05**：單元與邊界測試（core / server）
- [x] **TASK-DOC**：Docstrings 與 `yscb-cli-guide` SKILL.md

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| TASK-01 | Minor | 新增 `daemon_probe.is_daemon_lock_held`（§3.1 未列），供 process.py 判定 daemon 活躍而不依賴 dispatcher；`is_reaping_env` 之 `daemon_active` 改為 `Optional`，僅於紀錄 pid 已死且非 clean exit 時才延遲探鎖 | 向下相容擴充，Pre-UX 複審通過 |
| TASK-03 | Major | Pre-UX 盲審發現 strict 模式於「請求已送達後中途失敗」仍會重試導致雙重執行；新增 `_HotDispatchResult(exit_code, accepted)` 與 `_hot_dispatch_attempt` 區分未送達/已送達，strict 僅對未送達重試，已送達失敗回傳 1 | 已修正並補測試；已回寫 §2/§3 |
| TASK-04 | Major | 盲審發現 `server stop --force` 與優雅停止逾時後強殺未呼叫 `mark_clean_exit`，桌機兩次強制停止即誤判回收；已於強殺後補標記 | 已修正並補測試；已回寫 §2/§3 |
| TASK-04 | Minor | `restart_worker` 改為先載入 `ServerConfig` 再殺 worker；`master.start` 非阻塞取鎖失敗且無活躍 daemon 時以 0.5s 阻塞重試，避免探鎖瞬態競爭 | 已修正並補測試；已回寫 §2/§3 |
| TASK-04 | Minor | daemon 啟動時首個 worker spawn 失敗僅記錄、daemon 保持運行，由下次請求重新 spawn（EC-08 一致） | 接受 |
| TASK-05 | Minor | `test_server_logging.py` 因 FR-09 行為變更需於 mock worker 設定 `_worker_ready_event`；`test_server_config.py` 未修改（預設值由其他測試間接覆蓋） | 接受 |
| DEV-01 | Info | `_try_hot_dispatch` 非嚴格模式下 120s 讀取逾時後冷派發重複執行問題維持原狀 | 移交 sub_04 |

