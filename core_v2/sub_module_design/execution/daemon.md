# 子模組架構設計規格：`core.execution.daemon`（每專案常駐守護外殼、單一條件監督迴圈與四大背景觸發器）

> **所屬功能域**：`Domain 5 — 執行與常駐調度域 (execution/)`
> **模組路徑**：`core_v2/source/core/core/execution/daemon/`（`service.py`、`__init__.py`）
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.fs`、`execution.{runtime, lifecycle, rpc}`
> **禁止反向依賴（Forbidden Imports）**：`execution.event`、`metadata/*`、`packaging/*`、`surface/*`
> **狀態**：`Active Living Spec — Clean-Sheet Simplified & Orthogonal Benchmark Aligned`

## 1. 模組定位與極簡外殼邊界 (Positioning & Thin-Shell Principle)

所有派發決策、`resource_key` 鎖、`StepFlight` 與 `Tier1WorkerPool` 均已收斂至 `execution.runtime`；**`core.execution.daemon` 專職扮演「每專案獨立常駐進程外殼 + 單一條件監督迴圈 + 背景信號觸發器」**（且 `DaemonRunState = ContainerState` 直接複用 `lifecycle.ContainerState`，零重複狀態列舉）：
1. **零分流邏輯**：收到外部 RPC 業務請求或內部監視/定時觸發，**100% 委派同一個 `RuntimeDispatcher` 執行**。
2. **事件驅動單一監督迴圈（Single Supervisor Loop + `_DirtyPathsAccumulator`）**：所有檔案監視回呼於 `daemon.json` 發布前即建立初始目錄快照基線（確保 `WARMING` 預熱期間之組態或模組異動零漏接），並僅以 $O(1)$ 非阻塞寫入內部 `_DirtyPathsAccumulator` 喚醒單一條件變數 `_cond`；執行重載或讓位恢復時，於共享 `installer.lock` 內**先完成監視器快照重同步與髒佇列修剪，再讀取磁碟重載模組/組態**，確保重載預熱期間新發生的第二次檔案修改絕不被覆蓋漏接。

## 2. 核心架構與競態防禦機制 (Core & Race-Free Mechanisms)

### 2.1 單實例權威鎖、`spawn.lock` 防啟動風暴與 `daemon.json` 寫入獨佔權

1. **雙鎖職責分離（根除啟動風暴與搶鎖早退）**：
   - **`.cache/daemon/daemon.lock`（Daemon 存活獨佔鎖）**：僅由常駐 Daemon 進程自身於啟動首步獨佔持有（一般啟動非阻塞獲取防殭屍排隊；僅於 `handoff_lease.json` 有效交棒窗口內短暫等待 `0.25s` 平滑接手；外部客戶端**嚴禁以獨佔模式試探此鎖**）。
   - **`.cache/daemon/spawn.lock`（背景拉起單飛鎖）**：外部多個 CLI / SDK 進程同時觸發 `auto_spawn` 時，`SingleFlightDaemonSpawner` 以非阻塞競爭 `spawn.lock` 並核驗 `spawn_lease.json`——僅搶到鎖的唯一 1 個進程負責呼叫 `spawn_detached` 拉起 Daemon，徹底消滅多進程同時拉起風暴。
2. **`daemon.json` 寫入與刪除獨佔鐵律**：
   - **唯有已成功持有 `daemon.lock` 的 Daemon 進程自身**有權原子寫入（權限 `0o600`）或於停機釋放 `daemon.lock` 前刪除 `.cache/daemon/daemon.json`；顯式 `CONTROL_STOP`（`core_handoff=False`）或系統終止信號會不可逆鎖存終止意圖、原子清除待定交棒旗標與 `handoff_lease.json`（杜絕並行 `core` 重載覆寫復活），並排空回報容器 `teardown_diagnostics`。

### 2.2 原子狀態鎖：根除 Idle TTL 停機瞬間競態與空閒長連線不卡休眠

1. **單一 `_cond` 原子互斥與鎖外 I/O**：Daemon 以條件變數 `_cond` 保護 `state`（`BOOTING / WARMING / READY / QUIESCED / DRAINING / STOPPED`）與在途計數器，並將 `stop_accepting()` 與 `installer.lock` 檔案鎖探測移出 `_cond` 臨界區外避免阻塞入站串流。
2. **無縫拒收降級與空閒長連線休眠保證**：
   - 入站請求於 `_cond` 內通過收單閘門後原子遞增 `_active_fg_calls`（或背景 `_active_bg_turns`）、預先登記 `reload_gate.enter_rpc_call` 防收單至派發間隙被靜默，刷新 `IdleTtlMonitor` 後送出 `CALL_ACCEPTED`；若進入 `DRAINING / STOPPED` 或 `_explicit_stop_latched`，收單閘門立即放行並**不送出 `CALL_ACCEPTED`** 直接回傳未收單拒收結果（客戶端拿到 `was_accepted=False`，100% 安全無感轉為本地冷跑或透明重連新 Daemon）。
   - `IdleTtlMonitor.is_expired()` 到期時，唯有當 `_active_fg_calls == 0`、`_active_bg_turns == 0` 且無待處理髒路徑時才原子切換為 `DRAINING`，隨後於鎖外呼叫 `RpcServerListener.stop_accepting()` 並於收尾階段刪除 `daemon.json` 與關閉空閒連線，保證**任何已收到 `CALL_ACCEPTED` 的請求絕不會被 Idle TTL 中途腰斬**。
3. **精確活動計時**：僅外部前景業務 `CALL_START`（排除背景優先級與唯讀控制查詢 `CONTROL_STATUS / PING`）與非免回音之真實外部檔案/設定變動會刷新 `Idle TTL`；內部 `PeriodicTriggerLoop` 輪詢絕不續命。

### 2.3 四大背景觸發源、單趟批次去重與 `core` 自重啟安全交棒時序

1. **空間變更監視（`space_watch_roots`）**：於 `WARMING` 前先行啟動 `PollingDirectoryWatcher` 建立快照基線，並在首次進入 `READY` 時確保觸發唯一一次 `startup_catchup=True`（即便啟動期間曾經歷 `installer.lock` 讓位延遲預熱亦自動刷新定時排程 `refresh_schedules()` 並補發啟動追趕）。
2. **組態與模組單趟去重重載（`_process_dirty_batch`）**：合併 `reload_modules` 與 `module_paths`，在共享 `installer.lock` 保護下先重同步監視器基線再單趟完成模組與組態重載，釋放生命週期重載計數後再非阻塞派發 `core.config_changed` 事件與 `on_config_changed_task`。
3. **`PeriodicTriggerLoop`（組態閘控 + `fixed-delay` 定時觸發器）**：
   - 依 `TaskRouteSpec.periodic`（`PeriodicScheduleSpec`）運作：若綁定之 `enabled_config_key` 為 `False`，完全靜默待機零觸發；組態開啟或週期變更時動態啟停。
   - 嚴格採用**「上一輪執行完畢後再起算間隔（`fixed-delay`）」**，杜絕慢任務造成背景排程重疊堆積。
4. **模組熱重載與 `core` 自重啟交棒時序**：
   - **啟動期固定核心內容雜湊基線（`_boot_core_snapshot`）**：於 `__init__` 擷取記憶體載入時之 `.modules/core` `sha256` 內容基線，忽略純時間戳 `touch` 雜訊並精確捕捉任何實質 `core` 變更。
   - **`core` 內核自身變動（先寫 `handoff_lease.json`、先釋鎖、後拉起新進程！）**：嚴格執行 **① 原子寫入 `.cache/daemon/handoff_lease.json` 並切換 `DRAINING` 停收新單、排空在途請求 $\rightarrow$ ② 關閉監聽埠、清除本身 `daemon.json` 並釋放 `daemon.lock` $\rightarrow$ ③ 在 `spawn.lock` 與 `spawn_lease.json` 保護下透過 `spawn_detached(self_restart_argv)` 啟動全新 Daemon 進程接手後立即退出舊進程**。

### 2.4 `QUIESCED` 逐模組獨立租約、無阻塞局部恢復與崩潰自癒

1. **按模組粒度精確閘控與獨立租約（Per-Module Selective Quiesce Gate & Leases）**：當外部冷安裝發送 `CONTROL_QUIESCE` 僅讓位特定模組（如 `modules=["mod_a"]`）時，由 `LifecycleReloadGate` 單一狀態機採單調上界 `max` 統一追蹤全域與各模組租約期限（短租約絕不縮短既有長租約，且支援全域靜默期間按模組局部恢復降級），針對 `mod_a`（及其共置 `venv_group` 兄弟模組）之外部與跨模組巢狀請求安全排隊等待恢復，而**未受影響之其他健康模組（如 `mod_b`）在靜默與局部恢復預熱全期間皆直接放行熱執行，零全域無謂停擺**。
2. **可取消共享鎖恢復與租約到期自癒**：收到 `CONTROL_RESUME`（支援全域或指定 `modules`；若 `installer.lock` 正被獨佔則立即標記到期交由單一監督迴圈排程，不丟失連續靜默／恢復信號）或租約到期且確認 `.cache/locks/installer.lock` 已釋放時，以共享鎖安全完成局部或全域 `dispatcher.resume_from_quiesce()`，待所有靜默模組皆恢復後自動回到 `READY`。

## 3. 核心 OOP 類別與強型別契約規格 (`core/execution/daemon/`)

```python
from dataclasses import dataclass
from typing import Callable, Optional, Sequence
from core.execution.lifecycle import ContainerState
from core.execution.rpc import FrameKind, InboundCallHandler
from core.execution.runtime import ConfigViewPort, DaemonSpawner, RuntimeDispatcher, VfsEchoGuardPort, WorkerProcessSnapshot
from core.foundation.observability import CancellationToken
from core.foundation.errors import ErrorDetail
from core.foundation.primitives import HostPath, JsonObject, ModuleId, TaskId

DaemonRunState = ContainerState


@dataclass(frozen=True, slots=True)
class DaemonStatusSnapshot:
    state: ContainerState
    pid: int
    boot_id: str
    port: int
    uptime_sec: float
    idle_ttl_remaining_sec: Optional[float]
    active_foreground_calls: int
    tasks_handled: int
    active_tier1_workers: tuple[WorkerProcessSnapshot, ...]
    degraded_modules: tuple[str, ...] = ()
    background_error_count: int = 0


@dataclass(frozen=True, slots=True)
class DaemonQuiesceControl:
    modules: tuple[ModuleId, ...] = ()
    lease_sec: float = 10.0
    drain_timeout_sec: float = 3.0


@dataclass(frozen=True, slots=True)
class DaemonResumeControl:
    modules: tuple[ModuleId, ...] = ()
    expected_epoch: Optional[int] = None


@dataclass(frozen=True, slots=True)
class DaemonReloadControl:
    modules: tuple[ModuleId, ...] = ()


@dataclass(frozen=True, slots=True)
class DaemonStopControl:
    force: bool = False
    core_handoff: bool = False


@dataclass(frozen=True, slots=True)
class DaemonWatcherConfig:
    echo_guard: Optional[VfsEchoGuardPort] = None
    space_watch_roots: tuple[HostPath, ...] = ()
    config_watch_roots: tuple[HostPath, ...] = ()
    on_space_changed_task: Optional[TaskId] = None
    on_config_changed_task: Optional[TaskId] = None
    watcher_debounce_sec: float = 0.5


class SingleFlightDaemonSpawner(DaemonSpawner):
    """實作 runtime.DaemonSpawner 協定：透過 .cache/daemon/spawn.lock 與 spawn_lease.json 確保並發冷啟動僅拉起唯一 Daemon。"""
    def __init__(
        self,
        cache_dir: HostPath,
        daemon_argv_builder: Callable[[HostPath], Sequence[str]],
        *,
        lease_cooldown_sec: float = 1.5,
        sandbox_restricted: bool = False,
    ) -> None: ...
    def can_spawn_in_environment(self) -> bool: ...
    def try_spawn_background(self, workspace_root: HostPath) -> bool: ...


class IdleTtlMonitor:
    """精確業務空閒計時器（唯讀控制與心跳不續命）。"""
    def __init__(self, ttl_sec: Optional[float]) -> None: ...
    @property
    def ttl_sec(self) -> Optional[float]: ...
    def record_external_activity(self) -> None: ...
    def remaining_sec(self) -> Optional[float]: ...
    def is_expired(self) -> bool: ...


class PeriodicTriggerLoop:
    """支援組態開關閘控 (enabled_config_key)、fixed-delay 防堆積與背景異常診斷記錄之定時排程迴圈。"""
    def __init__(
        self,
        *,
        dispatcher: RuntimeDispatcher,
        config_view: Optional[ConfigViewPort],
        can_run_background: Callable[[], bool],
        execute_periodic_task: Callable[[TaskId], None],
        can_run_task: Optional[Callable[[TaskId], bool]] = None,
        on_error: Optional[Callable[[ErrorDetail], None]] = None,
    ) -> None: ...
    def start(self) -> None: ...
    def refresh_schedules(self) -> None: ...
    def wake(self) -> None: ...
    def stop(self, *, drain_timeout_sec: float = 3.0) -> None: ...


class WorkspaceDaemon(InboundCallHandler):
    """每專案獨立常駐守護主控外殼（單一條件監督迴圈）。"""
    def __init__(
        self,
        *,
        workspace_root: HostPath,
        cache_dir: HostPath,
        dispatcher: RuntimeDispatcher,
        config_view: Optional[ConfigViewPort] = None,
        watch_config: DaemonWatcherConfig = DaemonWatcherConfig(),
        self_restart_argv: Optional[Sequence[str]] = None,
    ) -> None: ...

    @property
    def quiesce_epoch(self) -> int: ...
    def run_forever(
        self,
        *,
        ttl_override_sec: Optional[float] = None,
        console_mode: bool = False,
        ready_callback: Optional[Callable[[], None]] = None,
    ) -> int: ...
    def request_shutdown(self, *, force: bool = False, core_handoff: bool = False) -> None: ...
    def quiesce(
        self,
        affected_modules: frozenset[ModuleId],
        lease_sec: float = 10.0,
        *,
        drain_timeout_sec: float = 3.0,
    ) -> bool: ...
    def resume_from_quiesce(
        self,
        *,
        expected_epoch: Optional[int] = None,
        modules: Optional[frozenset[ModuleId]] = None,
    ) -> bool: ...
    def drain_background_errors(self) -> tuple[ErrorDetail, ...]: ...
    def snapshot_status(self) -> DaemonStatusSnapshot: ...
    def on_call(
        self,
        stream_id: int,
        payload: JsonObject,
        ack_accepted: Callable[[], bool],
        emit_progress: Callable[[JsonObject], None],
        peer_cancel_token: CancellationToken,
    ) -> tuple[bool, JsonObject]: ...
    def on_control(self, kind: FrameKind, payload: JsonObject) -> JsonObject: ...


# 實作於 core/execution/rpc/channel.py，由 core/execution/daemon/__init__.py 轉發匯出
def query_daemon_control(
    cache_dir: HostPath,
    workspace_root: HostPath,
    kind: FrameKind,
    payload: Optional[JsonObject] = None,
    *,
    timeout_ms: int = 15000,
) -> Optional[JsonObject]: ...
```

### 3.1 `CONTROL_*` 控制訊框回應結構契約 (`WorkspaceDaemon.on_control` / `query_daemon_control`)

- **`CONTROL_STATUS`**：無參數；成功回傳 `{"ok": True, "status": <DaemonStatusSnapshot dict>}`。
- **`CONTROL_QUIESCE`**（`DaemonQuiesceControl`）：成功進入靜默回傳 `{"ok": True, "state": <str>, "epoch": <int>, "teardown_diagnostics": [<ErrorDetail>, ...]}`；排水逾時或狀態不符回傳 `{"ok": False, "state": <str>, "error": "daemon_busy"}`（且絕不吞沒待排空之 `teardown_diagnostics`）。
- **`CONTROL_RESUME`**（`DaemonResumeControl`）：回傳 `{"ok": True, "state": <str>, "handoff": <bool>, "teardown_diagnostics": [<ErrorDetail>, ...]}`。
- **`CONTROL_RELOAD`**（`DaemonReloadControl`）：啟動預熱（`warming`）或目標靜默期間排入延遲重載回傳 `{"ok": True, "reloaded": False, "deferred": True}`（若預熱期間含 `core` 變更則於預熱收尾自動觸發交棒重啟）；核心交棒回傳 `{"ok": True, "handoff": <bool>}`；即時重載完成回傳 `{"ok": True, "reloaded": True, "teardown_diagnostics": [<ErrorDetail>, ...]}`；停機排水期間回傳 `{"ok": False, "state": <str>, "error": "daemon_stopping"}`。
- **`CONTROL_STOP`**（`DaemonStopControl`）：不可逆鎖存終止並排空回傳 `{"ok": True, "teardown_diagnostics": [<ErrorDetail>, ...]}`。
- **`CONTROL_REQUEST`**：轉發跨工作區單飛協調控制（`flight_join` 回傳 `{"ok": True, "conflict": <bool>, ...}`、`flight_evict` 回傳 `{"ok": True, "evicted": <bool>}`、`flight_done` 回傳 `{"ok": True}`）。
- **格式驗證失敗**：未知欄位、未知動作、空白識別碼、型別不符或非法 `ModuleId` 一律回傳 `{"ok": False, "error": "codec_validation_failed", "message": <str>}`。

## 4. 必測驗收門檻 (Verification Gate — 對標 `verify_execution_live.py` `RC-01, RC-04, RC-05, RC-06`)

1. **10 進程並發 `auto_spawn` 風暴與唯讀狀態查詢測試**：驗證僅誕生 1 個 Daemon、`daemon.json` 不被誤刪，且 `CONTROL_STATUS` 不續命 TTL。
2. **Idle TTL 邊界同毫秒連入與空閒長連線休眠壓測**：驗證空閒長連線不阻擋到期休眠，且 `_cond` 保證 0 次假收單斷線。
3. **`WARMING` 期間組態/模組異動不漏接、延遲預熱排程自動刷新與 `PeriodicTriggerLoop` 動態啟停 / `fixed-delay` 防堆積測試**。
4. **`core` 自重啟先釋鎖交棒（含啟動鎖競爭期間升級 `core`）、逐模組獨立靜默租約、無阻塞局部恢復與 `CONTROL_STOP` 釋放診斷回傳測試**。
