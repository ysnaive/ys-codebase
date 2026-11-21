# 子模組架構設計規格：`core.execution.rpc`（全雙工多工訊框協議、唯讀端點探測與持久雙向傳輸通道）

> **所屬功能域**：`Domain 5 — 執行與常駐調度域 (execution/)`
> **模組路徑**：`core_v2/source/core/core/execution/rpc/`（`channel.py`、`__init__.py`）
> **依賴上限（Allowed Imports）**：`foundation.{primitives, errors, observability, proc}`、`filesystem.fs`（僅唯讀 `read_json_dict`）
> **禁止反向依賴（Forbidden Imports）**：`execution.{event, lifecycle, runtime, daemon}`、`surface/*`
> **狀態**：`Active Living Spec — Clean-Sheet Simplified & Orthogonal Benchmark Aligned`

## 1. 模組定位與職責純化 (Positioning & Zero-Routing Boundary)

**`core.execution.rpc` 為全系統唯一的純標準庫全雙工 Socket 訊框傳輸、端點握手與持久連線自癒層**：
1. **100% 零路由決策**：`rpc` 不感知業務模組或事件拓撲，僅負責端點存活握手探測、雙向多工訊框收發、`64 MiB` 訊框體積守衛與斷線狀態回報（將 `DaemonConnectionConfig` 與 `RpcEndpointInfo` 下沉於此，使 `execution.runtime` 無須逆向匯入 `execution.daemon`）。
2. **內外完全同構與帶外標頭正交隔離（`RpcFrame.meta`）**：`Client <-> Daemon`、`Daemon <-> Tier 1 常駐 Worker` 與 `ColdTurn <-> OneShotVenvHost` 100% 共用同一套封包協議、常數時間 `hmac.compare_digest` 握手驗證（`accept_worker_handshake` / `connect_and_handshake`）與雙向多工重入通道；傳輸層控制請求編號（`req_id`）、收單前拒收標記（`rejected_before_accept`）與傳輸異常碼統一封裝於獨立 `RpcFrame.meta`，與業務負載 `RpcFrame.payload` 100% 物理隔離零鍵名碰撞。

## 2. 線路協議、訊框上限守衛與唯讀端點探測 (Wire Protocol, Frame Guard & Read-Only Discovery)

### 2.1 長度前綴二進位封裝與 `64 MiB` 雙端訊框護欄
- **傳輸媒介**：Python 標準庫原生 `socket` 本機迴路連線（`bind_loopback_ephemeral` `127.0.0.1:0` 動態埠，Windows 啟用 `SO_EXCLUSIVEADDRUSE`，免疫系統 `HTTP_PROXY` 干擾）。子進程 `stdin=DEVNULL`，RPC 走獨立回連 Socket，物理隔絕標準輸出雜訊。
- **訊框格式**：`[4-byte uint32 BE payload_len] + [UTF-8 JSON Frame]`（透過 `strict_parse_json_object` 拒絕 `NaN / Infinity`、指數溢位浮點數 `1e400` 與孤立 UTF-16 代理字元）。
- **巨量負載與佇列容量硬邊界（`MAX_FRAME_BYTES = 64 MiB`）**：發送端序列化後與接收端讀取 `payload_len` 標頭瞬間雙向強制檢查上限；一旦超過 `64 MiB`，發送端拒絕寫入 Socket 並直接回傳結構化 `PAYLOAD_TOO_LARGE` 錯誤（接收端若遇非法超長標頭則立即斷開該異常通道），且單通道入站活躍呼叫/控制流與進度佇列皆具明確容量護欄避免執行緒或記憶體耗盡。

### 2.2 客戶端唯讀探測鐵律（嚴禁外部刪除 `daemon.json`！）
為根治多客戶端並發時「慢半拍客戶端連舊埠失敗後誤刪新 Daemon 剛寫好的 `daemon.json`」之競態：
- **客戶端 100% 唯讀與防符號連結穿越**：`probe_daemon_endpoint()` 僅透過 `read_daemon_endpoint_file()` 以不跟隨符號連結之 `read_json_dict` 讀取 `.cache/daemon/daemon.json`，核驗進程存活並執行 `HELLO` 握手驗證（常數時間比對 `auth_token`、`boot_id` 與 `workspace_root`）；即使握手失敗或連線被拒，**外部客戶端絕對禁止刪除或修改 `daemon.json`**（僅持有獨佔 `daemon.lock` 的 Daemon 進程自身有權覆寫與清理）。

## 3. 全雙工多工串流、無飢餓重入與持久客戶端自癒重連 (Full-Duplex & Persistent Session)

- **奇偶流編號防碰撞與亂序回傳**：連線主動發起端分配奇數 `stream_id`（`1, 3, 5, ...`），被動接受端分配偶數 `stream_id`（`2, 4, 6, ...`）；同一連線上多路並發請求支援**亂序完成回傳（零 Head-of-Line 阻塞）**與單流精準 `CANCEL`（完整傳遞 `preempted: bool` 與 `reason: str`，不斷開底層 Socket）。

### 3.1 完整訊框型別清冊

| `FrameKind` | `stream_id` | 方向 | 語意與可靠度保證 |
| :--- | :---: | :--- | :--- |
| **`HELLO` / `HELLO_ACK`** | `0` | 雙向控制流 | 客戶端提示 `.cache/daemon/daemon.json`（`0o600`）之 `auth_token`、`boot_id` 與 `workspace_root` 接受常數時間核驗，伺服端回傳 `HELLO_ACK` 確認協定版本與 `boot_id` 一致。 |
| **`CALL_START`** | `> 0` | 呼叫方 $\rightarrow$ 執行方 | 發起呼叫，攜帶序列化請求封包。 |
| **`CALL_ACCEPTED`** | `> 0` | 執行方 $\rightarrow$ 呼叫方 | **收單確認屏障**：執行方通過停機/讓位閘門收單後回傳此幀；呼叫方收到瞬間標記 `was_accepted = True`（若執行方正處於 `DRAINING` 停機中，則於 `RpcFrame.meta` 標註 `rejected_before_accept=True` 回傳 `CALL_RESULT` 而不發 `CALL_ACCEPTED`，確保 `was_accepted = False` 可安全冷降級或透明重連）。 |
| **`PROGRESS`** | `> 0` | 執行方 $\rightarrow$ 呼叫方 | 非阻塞依序投遞結構化階段進度（於 `CALL_RESULT` 抵達前完成序向排空）。 |
| **`CANCEL`** | `> 0` | 呼叫方 $\rightarrow$ 執行方 | 於同一條連線傳送指定 `stream_id` 取消信號（精確攜帶 `{"preempted": bool, "reason": str}`，不影響同連線其他活躍流）。 |
| **`CALL_RESULT`** | `> 0` | 執行方 $\rightarrow$ 呼叫方 | 終結該 `stream_id`（正常業務輸出置於 `payload`，傳輸異常與未收單拒收標記置於 `meta`）。 |
| **`CONTROL_REQUEST` / `CONTROL_QUIESCE` / `RESUME` / `STATUS` / `RELOAD` / `STOP` / `ACK`** | `0` | 雙向控制流 | 管理控制幀（全域讓位釋鎖 `CONTROL_QUIESCE`、恢復 `CONTROL_RESUME`、狀態查詢 `CONTROL_STATUS`、熱重載 `CONTROL_RELOAD`、停機 `CONTROL_STOP`；`CONTROL_REQUEST` 僅供 `Daemon <-> Worker` 內部優先級抬升與初始化通知，外部 Daemon 控制面已退役拒收）及確認幀 `CONTROL_ACK`（透過 `meta.req_id` 配對）。 |
| **`PING` / `PONG`** | `0` | 雙向控制流 | 連線健康度探針與長任務心跳（`MultiplexedChannel.ping()`，不刷新 Daemon 業務 Idle TTL）。 |

### 3.2 按需動態重入、一致斷線契約與長連線跨休眠/交棒透明重連
1. **無飢餓動態重入（On-Demand Reentrant Dispatch）**：`MultiplexedChannel` 將「I/O 讀取執行緒」與「入站執行器」分離，入站重入採用按需動態執行緒（嵌套深度由 `CallStack` 無環檢查自然封頂），杜絕多層 `Daemon <-> Worker` 嵌套反向呼叫飢餓死鎖。
2. **一致值物件斷線契約（`RemoteCallOutcome`）**：`MultiplexedChannel.call()` 對網路斷線、超長訊框或對端 EOF **統一回傳值物件 `RemoteCallOutcome(was_accepted=..., transport_lost=..., rejected_before_accept=..., error_code=...)`**，讓上層以單一布林判準 `outcome.was_accepted` 區分收單前（`False`，安全重連/重拉/冷降級）與收單後（`True`，回報 `TRANSPORT_LOST` 嚴禁重跑）。
3. **持久連線與臨時呼叫自癒（`PersistentRpcSession` & `call_ephemeral_daemon_rpc`）**：
   - 空閒未發單之長連線 Socket 不阻擋服務端 `Idle TTL` 停機（服務端停機呼叫 `stop_accepting()` 排空在途握手並於 `close_all()` 主動斷開空閒 Socket；單一連線關閉時透過 `on_closed` 立即從伺服器清單移除零殘留），且重連握手於會話互斥鎖外進行，取消時設定 `cancel_grace_ms=500` 防止無協作阻塞。
   - 當發送請求收到 `was_accepted=False` 或端點短暫消失（如舊 Daemon 已休眠關機或正在執行 `core` 自重啟交棒）時，內建 `wait_for_handoff_daemon_endpoint`（或自訂 `on_reconnect_wait`）自動依單調 `DeadlineGuard` 剩餘預算等待 `daemon/handoff_lease.json` 交棒新端點並透明重試，確保零誤報斷線。

### 3.3 伺服端「先確認收單再產生副作用」鐵律與本機迴路信任邊界
1. **先送達 `CALL_ACCEPTED` 再執行業務副作用（Ack-Before-Side-Effects Rule）**：為使客戶端 `was_accepted=False` 透明重連與非冪等任務「收單後絕不重跑」承諾在雙端嚴格成立，所有 `InboundCallHandler.on_call` 實作（含 `WorkspaceDaemon` 與 `WorkerSubprocessHandler`）**必須在呼叫業務派發或修改任何模組/環境狀態前先行呼叫 `ack_accepted()` 並確認其回傳 `True`**；一旦 `ack_accepted()` 因底層連線中斷回傳 `False`，伺服端必須立即中止而不執行目標步驟。
2. **本機同使用者 `0o600` 憑證邊界**：跨進程連線認證錨定於宿主工作區 `.cache/daemon/daemon.json`（POSIX `0o600` 權限）內隨機產生的 `auth_token` 與 `boot_id`；持有合法 `auth_token` 之同機同使用者進程屬於同一作業系統主體信任域，上層 `InvokeRequest.approval_scope` 與 `allow_conditional` 定位為**防誤觸與防背景/事件暗中觸發之顯式工作流安全確認護欄（Workflow Safety Gate）**，而非多租戶跨權限隔離邊界。

## 4. 核心 OOP 類別與強型別契約規格 (`core/execution/rpc/channel.py`)

```python
from dataclasses import dataclass, field
from enum import Enum
import socket
from typing import Callable, Optional, Protocol
from core.foundation.errors import ErrorCode
from core.foundation.observability import CancellationToken
from core.foundation.primitives import HostPath, JsonObject

MAX_FRAME_BYTES: int = 64 * 1024 * 1024  # 64 MiB 硬上限
DAEMON_SUBDIR: str = "daemon"
DAEMON_ENDPOINT_FILENAME: str = "daemon.json"
DAEMON_HANDOFF_FILENAME: str = "handoff_lease.json"


class FrameKind(Enum):
    HELLO = "hello"
    HELLO_ACK = "hello_ack"
    CALL_START = "call_start"
    CALL_ACCEPTED = "call_accepted"
    PROGRESS = "progress"
    CANCEL = "cancel"
    CALL_RESULT = "call_result"
    CONTROL_REQUEST = "control_request"
    CONTROL_QUIESCE = "control_quiesce"
    CONTROL_RESUME = "control_resume"
    CONTROL_STATUS = "control_status"
    CONTROL_RELOAD = "control_reload"
    CONTROL_STOP = "control_stop"
    CONTROL_ACK = "control_ack"
    PING = "ping"
    PONG = "pong"


@dataclass(frozen=True, slots=True)
class DaemonConnectionConfig:
    """下沉至 rpc 之連線策略值物件，供 runtime 讀取而無須匯入 daemon。"""
    enabled: bool = True
    auto_spawn: bool = True
    strict_hot_dispatch: bool = False


@dataclass(frozen=True, slots=True)
class RpcEndpointInfo:
    pid: int
    host: str
    port: int
    boot_id: str
    auth_token: str
    workspace_root: HostPath


@dataclass(frozen=True, slots=True)
class RpcFrame:
    kind: FrameKind
    stream_id: int
    payload: JsonObject = field(default_factory=dict)
    meta: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RemoteCallOutcome:
    """統一遠端呼叫結果契約：明確區分未收單拒收/斷線 (was_accepted=False) 與收單後中斷 (was_accepted=True)。"""
    was_accepted: bool
    transport_lost: bool = False
    rejected_before_accept: bool = False
    error_code: Optional[ErrorCode] = None
    result_payload: Optional[JsonObject] = None
    error_message: Optional[str] = None
    error_remediation: Optional[str] = None
    error_source_task: Optional[str] = None


def bind_loopback_ephemeral(*, backlog: int = 64) -> socket.socket: ...


def build_daemon_endpoint_dict(info: RpcEndpointInfo) -> JsonObject: ...


def build_handoff_lease_dict(old_boot_id: str, expires_epoch: float) -> JsonObject: ...


def read_daemon_endpoint_file(cache_dir: HostPath, workspace_root: HostPath) -> Optional[RpcEndpointInfo]: ...


def probe_daemon_endpoint(
    cache_dir: HostPath,
    workspace_root: HostPath,
    *,
    timeout_sec: float = 0.6,
) -> Optional[RpcEndpointInfo]:
    """100% 唯讀探測並驗證 daemon.json（嚴禁修改或刪除檔案）。"""
    ...


def read_active_handoff_boot_id(cache_dir: HostPath) -> Optional[str]: ...


def wait_for_handoff_daemon_endpoint(
    cache_dir: HostPath,
    workspace_root: HostPath,
    cancel_token: Optional[CancellationToken] = None,
    *,
    max_wait_sec: float = 8.0,
    previous_boot_id: Optional[str] = None,
) -> Optional[RpcEndpointInfo]: ...


class InboundCallHandler(Protocol):
    """由上層 runtime / daemon 實作注入之入站處理介面。"""
    def on_call(
        self,
        stream_id: int,
        payload: JsonObject,
        ack_accepted: Callable[[], bool],
        emit_progress: Callable[[JsonObject], None],
        peer_cancel_token: CancellationToken,
    ) -> tuple[bool, JsonObject]: ...

    def on_control(self, kind: FrameKind, payload: JsonObject) -> JsonObject: ...


class MultiplexedChannel:
    """封裝單一已握手 Socket 之雙向多工讀寫、64MiB 訊框守衛、按需動態重入與 EOF 自動回收。"""
    def __init__(
        self,
        sock: socket.socket,
        *,
        is_initiator: bool,
        handler: Optional[InboundCallHandler] = None,
        max_frame_bytes: int = MAX_FRAME_BYTES,
        on_closed: Optional[Callable[["MultiplexedChannel"], None]] = None,
        write_stall_timeout_sec: float = 15.0,
    ) -> None: ...
    @property
    def is_closed(self) -> bool: ...
    @property
    def is_usable(self) -> bool: ...
    def wait_until_closed(self, timeout_sec: Optional[float] = None) -> bool: ...
    def wait_inbound_controls_flushed(self, timeout_sec: float = 1.0) -> None: ...
    def call(
        self,
        payload: JsonObject,
        *,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
        cancel_token: Optional[CancellationToken] = None,
        timeout_ms: Optional[int] = None,
        cancel_grace_ms: Optional[int] = None,
    ) -> RemoteCallOutcome: ...
    def send_control(self, kind: FrameKind, payload: JsonObject, *, timeout_ms: int = 5000) -> Optional[JsonObject]: ...
    def post_control(self, kind: FrameKind, payload: JsonObject) -> bool: ...
    def ping(self, *, timeout_ms: int = 2000) -> bool: ...
    def close_when_idle(self) -> None: ...
    def close(self) -> None: ...


def connect_and_handshake(
    endpoint: RpcEndpointInfo,
    *,
    handler: Optional[InboundCallHandler] = None,
    connect_timeout_sec: float = 1.0,
    max_frame_bytes: int = MAX_FRAME_BYTES,
) -> Optional[MultiplexedChannel]: ...


def accept_worker_handshake(
    conn: socket.socket,
    *,
    expected_auth_token: str,
    boot_id: str,
    handler: InboundCallHandler,
    expected_workspace_root: Optional[HostPath] = None,
    max_frame_bytes: int = MAX_FRAME_BYTES,
) -> Optional[MultiplexedChannel]: ...


class PersistentRpcSession:
    """供長連線客戶端 (IDE / SDK) 複用之自動重探測會話封裝：於 was_accepted=False 舊連線失效時透明重連。"""
    def __init__(
        self,
        cache_dir: HostPath,
        workspace_root: HostPath,
        *,
        handler: Optional[InboundCallHandler] = None,
        max_frame_bytes: int = MAX_FRAME_BYTES,
        connect_timeout_sec: float = 0.8,
    ) -> None: ...
    @property
    def is_connected(self) -> bool: ...
    @property
    def channel_generation(self) -> int: ...
    def call(
        self,
        payload: JsonObject,
        *,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
        cancel_token: Optional[CancellationToken] = None,
        timeout_ms: Optional[int] = None,
        on_reconnect_wait: Optional[Callable[[Optional[CancellationToken]], bool]] = None,
    ) -> RemoteCallOutcome: ...
    def call_with_reachability(
        self,
        payload: JsonObject,
        *,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
        cancel_token: Optional[CancellationToken] = None,
        timeout_ms: Optional[int] = None,
        on_reconnect_wait: Optional[Callable[[Optional[CancellationToken]], bool]] = None,
    ) -> tuple[RemoteCallOutcome, bool]: ...
    def close(self) -> None: ...


def call_ephemeral_daemon_rpc(
    endpoint_dirs: tuple[HostPath, HostPath],
    payload: JsonObject,
    *,
    on_progress: Optional[Callable[[JsonObject], None]] = None,
    cancel_token: Optional[CancellationToken] = None,
    timeout_ms: Optional[int] = None,
    on_reconnect_wait: Optional[Callable[[Optional[CancellationToken]], bool]] = None,
) -> Optional[RemoteCallOutcome]: ...


def query_daemon_control(
    cache_dir: HostPath,
    workspace_root: HostPath,
    kind: FrameKind,
    payload: Optional[JsonObject] = None,
    *,
    timeout_ms: int = 15000,
) -> Optional[JsonObject]: ...


class RpcServerListener:
    """監聽 127.0.0.1 動態埠：支援 stop_accepting() 停收新連線與 close_all() 斷開空閒長連線。"""
    def __init__(
        self,
        workspace_root: HostPath,
        handler: InboundCallHandler,
        *,
        boot_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        max_frame_bytes: int = MAX_FRAME_BYTES,
    ) -> None: ...
    @property
    def endpoint(self) -> Optional[RpcEndpointInfo]: ...
    def start(self, *, pid: Optional[int] = None) -> RpcEndpointInfo: ...
    def stop_accepting(self) -> None: ...
    def flush_inbound_controls(self, timeout_sec: float = 1.0) -> None: ...
    def close_all(self) -> None: ...
```

## 5. 必測驗收門檻 (Verification Gate — 對標 `verify_execution_live.py` `RC-01, RC-04, RC-05, RC-08`)

1. **高並發多路亂序回傳、單流 `CANCEL`（含 `preempted=True` 語意保留）、`PING/PONG` 與三層重入無飢餓壓測**：驗證同連線快任務不被慢任務阻塞、取消單流不斷連線，且 16 路三層重入零死鎖。
2. **`PersistentRpcSession` 跨 Daemon 停機/換埠與 `handoff_lease.json` 透明重連及 `was_accepted` 契約測試**：驗證舊 Daemon 關機或交棒期間長連線與臨時客戶端於 `was_accepted=False` 自動重連新 Daemon 成功，而收單後斷線恆回報 `was_accepted=True, transport_lost=True`。
3. **唯讀探測不刪檔、帶外標頭零碰撞與 `64 MiB` 訊框上限攔截測試**：驗證慢速客戶端不刪新 `daemon.json`、業務負載含任意保留字不干擾控制/錯誤狀態，且超長負載立即回報 `PAYLOAD_TOO_LARGE`。
