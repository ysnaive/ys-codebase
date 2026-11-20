"""Full-duplex multiplexed length-prefixed socket protocol and persistent auto-reconnecting session."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import hmac
import json
import math
import os
import select
import selectors
import socket
import struct
import threading
import time
from typing import Callable, Mapping, Optional, Protocol, Sequence
import uuid

from core.filesystem.fs import read_json_dict
from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary
from core.foundation.observability import (
    MAX_SAFE_WAIT_SEC,
    CancellationToken,
    DeadlineGuard,
    clamp_wait_sec,
    ms_to_safe_sec,
    safe_real_to_float,
    validate_non_negative_sec,
)
from core.foundation.primitives import (
    IS_WINDOWS,
    MAX_ENVELOPE_JSON_DEPTH,
    HostPath,
    JsonObject,
    JsonValue,
    clone_strict_json_object,
    invoke_observer_safely,
    require_non_none,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    strict_parse_json_object,
    validate_wire_json_object,
)
from core.foundation.proc import is_process_alive

MAX_FRAME_BYTES: int = 64 * 1024 * 1024
DAEMON_SUBDIR: str = "daemon"
DAEMON_ENDPOINT_FILENAME: str = "daemon.json"
DAEMON_HANDOFF_FILENAME: str = "handoff_lease.json"
_MAX_HANDSHAKE_FRAME_BYTES: int = 64 * 1024
_RECV_CHUNK_BYTES: int = 64 * 1024
_MAX_CONCURRENT_HANDSHAKES: int = 32
_MAX_INBOUND_CALLS_PER_CHANNEL: int = 512
_MAX_INBOUND_CONTROLS_PER_CHANNEL: int = 128
_MAX_PENDING_PROGRESS_ITEMS: int = 4096
_PROTOCOL_VERSION: int = 2
_HEADER_STRUCT = struct.Struct(">I")


class FrameKind(Enum):
    """Wire frame kinds over full-duplex length-prefixed TCP loopback sockets."""

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


_INBOUND_CONTROL_KINDS: frozenset[FrameKind] = frozenset(
    {
        FrameKind.CONTROL_REQUEST,
        FrameKind.CONTROL_QUIESCE,
        FrameKind.CONTROL_RESUME,
        FrameKind.CONTROL_STATUS,
        FrameKind.CONTROL_RELOAD,
        FrameKind.CONTROL_STOP,
    }
)


@dataclass(frozen=True, slots=True)
class DaemonConnectionConfig:
    """Client-side daemon connection policy owned by execution.rpc to prevent reverse imports."""

    enabled: bool = True
    auto_spawn: bool = True
    strict_hot_dispatch: bool = False

    def __post_init__(self) -> None:
        require_pure_bool(self.enabled, "DaemonConnectionConfig.enabled")
        require_pure_bool(self.auto_spawn, "DaemonConnectionConfig.auto_spawn")
        require_pure_bool(self.strict_hot_dispatch, "DaemonConnectionConfig.strict_hot_dispatch")


@dataclass(frozen=True, slots=True)
class RpcEndpointInfo:
    """Verified coordinates of a live RPC listener."""

    pid: int
    host: str
    port: int
    boot_id: str
    auth_token: str
    workspace_root: HostPath

    def __post_init__(self) -> None:
        require_pure_int(self.pid, "RpcEndpointInfo.pid", min_val=1)
        require_pure_int(self.port, "RpcEndpointInfo.port", min_val=1, max_val=65535)
        if not isinstance(self.workspace_root, HostPath):
            raise ValueError("RpcEndpointInfo.workspace_root must be a HostPath.")
        require_pure_str(self.host, "RpcEndpointInfo.host", non_empty=True)
        require_pure_str(self.boot_id, "RpcEndpointInfo.boot_id", non_empty=True)
        require_pure_str(self.auth_token, "RpcEndpointInfo.auth_token", non_empty=True)
        if self.host != "127.0.0.1":
            raise ValueError(f"RpcEndpointInfo.host must be loopback '127.0.0.1', got {self.host!r}")


@dataclass(frozen=True, slots=True)
class RpcFrame:
    """Single multiplexed wire frame separating out-of-band transport meta from application payload."""

    kind: FrameKind
    stream_id: int
    payload: JsonObject = field(default_factory=dict)
    meta: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FrameKind):
            raise ValueError(f"RpcFrame.kind must be FrameKind, got {self.kind!r}")
        require_pure_int(self.stream_id, "RpcFrame.stream_id", min_val=0, max_val=0x7FFFFFFF)
        try:
            norm_pl = clone_strict_json_object(
                self.payload,
                max_depth=MAX_ENVELOPE_JSON_DEPTH,
                label="RpcFrame.payload",
            )
            norm_meta = clone_strict_json_object(
                self.meta,
                max_depth=MAX_ENVELOPE_JSON_DEPTH,
                label="RpcFrame.meta",
            )
        except TypeError as exc:
            raise ValueError(safe_exception_summary(exc)) from exc
        object.__setattr__(self, "payload", norm_pl)
        object.__setattr__(self, "meta", norm_meta)




@dataclass(frozen=True, slots=True)
class RemoteCallOutcome:
    """Uniform non-throwing call outcome distinguishing pre-accept vs. post-accept failures."""

    was_accepted: bool
    transport_lost: bool = False
    rejected_before_accept: bool = False
    error_code: Optional[ErrorCode] = None
    result_payload: Optional[JsonObject] = None
    error_message: Optional[str] = None
    error_remediation: Optional[str] = None
    error_source_task: Optional[str] = None

    def __post_init__(self) -> None:
        for flag, label in (
            (self.was_accepted, "was_accepted"),
            (self.transport_lost, "transport_lost"),
            (self.rejected_before_accept, "rejected_before_accept"),
        ):
            if not isinstance(flag, bool):
                raise ValueError(f"RemoteCallOutcome.{label} must be a bool, got {flag!r}")
        if self.error_code is not None and not isinstance(self.error_code, ErrorCode):
            raise ValueError(f"RemoteCallOutcome.error_code must be ErrorCode, got {self.error_code!r}")
        if self.result_payload is not None:
            try:
                validate_wire_json_object(
                    self.result_payload,
                    max_depth=MAX_ENVELOPE_JSON_DEPTH,
                    label="RemoteCallOutcome.result_payload",
                )
            except TypeError as exc:
                raise ValueError(safe_exception_summary(exc)) from exc
        if self.error_message is not None:
            require_pure_str(self.error_message, "RemoteCallOutcome.error_message")
        if self.error_remediation is not None:
            require_pure_str(self.error_remediation, "RemoteCallOutcome.error_remediation")
        if self.error_source_task is not None:
            require_pure_str(self.error_source_task, "RemoteCallOutcome.error_source_task")




def _frame_from_trusted_wire(kind: FrameKind, stream_id: int, payload: JsonObject, meta: JsonObject) -> RpcFrame:
    inst = object.__new__(RpcFrame)
    object.__setattr__(inst, "kind", kind)
    object.__setattr__(inst, "stream_id", stream_id)
    object.__setattr__(inst, "payload", payload)
    object.__setattr__(inst, "meta", meta)
    return inst


class InboundCallHandler(Protocol):
    """Implemented by Daemon, Runtime master callback router, and Tier 1 Worker host."""

    def on_call(
        self,
        stream_id: int,
        payload: JsonObject,
        ack_accepted: Callable[[], bool],
        emit_progress: Callable[[JsonObject], None],
        peer_cancel_token: CancellationToken,
    ) -> tuple[bool, JsonObject]: ...

    def on_control(self, kind: FrameKind, payload: JsonObject) -> JsonObject:
        _ = payload
        return {
            "ok": False,
            "error": ErrorCode.CODEC_VALIDATION_FAILED.value,
            "message": f"Unsupported control frame: {kind.value}",
        }


def _enable_tcp_nodelay(sock: socket.socket) -> None:
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass


def bind_loopback_ephemeral(*, backlog: int = 64) -> socket.socket:
    """Bind an ephemeral loopback TCP socket securely without Windows SO_REUSEADDR port hijacking."""
    safe_backlog = min(require_pure_int(backlog, "backlog", min_val=1, max_val=None), 4096)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if IS_WINDOWS:
            try:
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except (AttributeError, OSError):
                pass
        srv.bind(("127.0.0.1", 0))
        srv.listen(safe_backlog)
        return srv
    except BaseException:
        try:
            srv.close()
        except OSError:
            pass
        raise


def _shutdown_and_close_sock(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def _wait_sock_readable(sock: socket.socket, timeout_sec: float) -> Optional[bool]:
    if sock.fileno() < 0:
        return None
    try:
        rlist, _, _ = select.select([sock], [], [], timeout_sec)
        return bool(rlist)
    except ValueError:
        if sock.fileno() < 0:
            return None
        try:
            with selectors.DefaultSelector() as sel:
                sel.register(sock, selectors.EVENT_READ)
                return bool(sel.select(timeout=timeout_sec))
        except (OSError, ValueError):
            return None
    except OSError:
        return None


def _recv_exact(sock: socket.socket, n: int, *, deadline: Optional[float] = None) -> Optional[bytes]:
    chunks: list[bytes] = []
    remaining = n
    while remaining > 0:
        if deadline is not None:
            rem_sec = deadline - time.monotonic()
            if rem_sec <= 0.0:
                return None
            sock.settimeout(rem_sec)
        try:
            chunk = sock.recv(min(remaining, _RECV_CHUNK_BYTES))
        except (BlockingIOError, InterruptedError):
            while True:
                if deadline is not None and time.monotonic() >= deadline:
                    return None
                wait_s = 0.05 if deadline is None else min(0.05, max(0.001, deadline - time.monotonic()))
                ready = _wait_sock_readable(sock, wait_s)
                if ready is None:
                    return None
                if ready:
                    break
            continue
        except OSError:
            return None
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_raw_frame(
    sock: socket.socket,
    *,
    max_frame_bytes: int,
    deadline: Optional[float] = None,
) -> Optional[RpcFrame]:
    header = _recv_exact(sock, _HEADER_STRUCT.size, deadline=deadline)
    if header is None:
        return None
    (payload_len,) = _HEADER_STRUCT.unpack(header)
    if payload_len > max_frame_bytes:
        raise ValueError(f"Inbound RPC frame ({payload_len} bytes) exceeds limit ({max_frame_bytes} bytes)")
    body = _recv_exact(sock, payload_len, deadline=deadline)
    if body is None:
        return None
    decoded = strict_parse_json_object(body.decode("utf-8"))
    payload = decoded["payload"] if "payload" in decoded else {}
    meta = decoded["meta"] if "meta" in decoded else {}
    if not isinstance(payload, Mapping) or not isinstance(meta, Mapping):
        raise TypeError("Inbound RPC frame payload and meta must be JSON objects")
    stream_raw = decoded["stream_id"]
    if type(stream_raw) is not int or stream_raw < 0 or stream_raw > 0x7FFFFFFF:
        raise TypeError("Inbound RPC stream_id must be a non-negative 31-bit int")
    if not isinstance(payload, dict) or not isinstance(meta, dict):
        raise TypeError("Inbound RPC frame payload and meta must be JSON dicts")
    return _frame_from_trusted_wire(
        kind=FrameKind(str(decoded["kind"])),
        stream_id=stream_raw,
        payload=payload,
        meta=meta,
    )


def _resolve_msg_dontwait() -> int:
    if IS_WINDOWS:
        return 0
    try:
        return int(socket.MSG_DONTWAIT)
    except AttributeError:
        return 0


_MSG_DONTWAIT: int = _resolve_msg_dontwait()


def _encode_raw_frame(frame: RpcFrame, *, max_frame_bytes: int) -> bytes:
    wire_doc: dict[str, object] = {
        "kind": frame.kind.value,
        "stream_id": frame.stream_id,
        "payload": frame.payload,
    }
    if frame.meta:
        wire_doc["meta"] = frame.meta
    try:
        body = json.dumps(
            wire_doc,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except RecursionError as exc:
        raise ValueError("Outbound RPC frame exceeded maximum JSON recursion depth.") from exc
    if len(body) > max_frame_bytes:
        raise OverflowError(f"Outbound RPC frame ({len(body)} bytes) exceeds limit ({max_frame_bytes} bytes)")
    return _HEADER_STRUCT.pack(len(body)) + body


def _is_sock_writable_ready(sock: socket.socket, timeout_sec: float) -> Optional[bool]:
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(sock, selectors.EVENT_WRITE)
            return bool(sel.select(timeout=timeout_sec))
    except (OSError, ValueError):
        return None


def _try_send_slice(sock: socket.socket, view: memoryview) -> Optional[int]:
    try:
        return sock.send(view, _MSG_DONTWAIT)
    except (BlockingIOError, InterruptedError):
        return 0
    except OSError:
        return None


@dataclass(frozen=True, slots=True)
class _OutboundFrameItem:
    data: bytes
    flushed_ev: Optional[threading.Event] = None
    flush_ok: Optional[list[bool]] = None
    call_start_sid: int = 0


def _finish_outbound_item(item: _OutboundFrameItem, ok: bool) -> None:
    if item.flush_ok is not None:
        item.flush_ok.append(ok)
    if item.flushed_ev is not None:
        item.flushed_ev.set()


def _send_frame_bounded(
    sock: socket.socket,
    data: bytes,
    stall_sec: float,
    is_closed_fn: Callable[[], bool],
) -> bool:
    mv = memoryview(data)
    offset = 0
    total = len(data)
    stall_deadline = time.monotonic() + stall_sec
    while offset < total:
        if is_closed_fn():
            return False
        sent = _try_send_slice(sock, mv[offset : offset + 65536])
        if sent is None:
            return False
        if sent > 0:
            offset += sent
            stall_deadline = time.monotonic() + stall_sec
            continue
        if time.monotonic() >= stall_deadline:
            return False
        if _is_sock_writable_ready(sock, 0.05) is None:
            time.sleep(0.005)
    return True


class _PendingCallState:
    def __init__(self, on_progress: Optional[Callable[[JsonObject], None]]) -> None:
        self.on_progress = on_progress
        self.done = threading.Event()
        self.wake = threading.Event()
        self.prog_lock = threading.Lock()
        self.prog_items: deque[JsonObject] = deque()
        self.was_accepted = False
        self.transport_lost = False
        self.rejected_before_accept = False
        self.result_payload: Optional[JsonObject] = None
        self.error_code: Optional[ErrorCode] = None
        self.error_message: Optional[str] = None
        self.error_remediation: Optional[str] = None
        self.error_source_task: Optional[str] = None
        self.cancel_grace_deadline: Optional[float] = None
        self.cancel_preempted = False
        self.cancel_reason = ""

    def enqueue_progress(self, payload: JsonObject) -> None:
        if self.on_progress is None:
            return
        with self.prog_lock:
            if len(self.prog_items) >= _MAX_PENDING_PROGRESS_ITEMS:
                self.prog_items.popleft()
            self.prog_items.append(payload)
            self.wake.set()

    def drain_progress_inline(self) -> None:
        cb = self.on_progress
        if cb is None:
            return
        while True:
            with self.prog_lock:
                if not self.prog_items:
                    return
                item = self.prog_items.popleft()
            invoke_observer_safely(lambda cur=item: cb(cur))

    def to_outcome(self) -> RemoteCallOutcome:
        inst = object.__new__(RemoteCallOutcome)
        object.__setattr__(inst, "was_accepted", self.was_accepted)
        object.__setattr__(inst, "transport_lost", self.transport_lost)
        object.__setattr__(inst, "rejected_before_accept", self.rejected_before_accept)
        object.__setattr__(inst, "error_code", self.error_code)
        object.__setattr__(inst, "result_payload", self.result_payload)
        object.__setattr__(inst, "error_message", self.error_message)
        object.__setattr__(inst, "error_remediation", self.error_remediation)
        object.__setattr__(inst, "error_source_task", self.error_source_task)
        return inst


def _settle_stream_outcome(pending: _PendingCallState, outcome: RemoteCallOutcome) -> RemoteCallOutcome:
    if not outcome.transport_lost:
        pending.drain_progress_inline()
    return outcome


@dataclass(frozen=True, slots=True)
class _PendingControlWait:
    expected_kind: FrameKind
    done: threading.Event
    holder: dict[str, JsonObject]


class MultiplexedChannel:
    """Full-duplex multiplexed socket channel with odd/even stream IDs and table-driven dispatch."""

    def __init__(
        self,
        sock: socket.socket,
        *,
        is_initiator: bool,
        handler: Optional[InboundCallHandler] = None,
        max_frame_bytes: int = MAX_FRAME_BYTES,
        on_closed: Optional[Callable[[MultiplexedChannel], None]] = None,
        write_stall_timeout_sec: float = 15.0,
    ) -> None:
        stall_v = validate_non_negative_sec(write_stall_timeout_sec, label="write_stall_timeout_sec")
        if stall_v is None or stall_v <= 0.0:
            raise ValueError("write_stall_timeout_sec must be finite and > 0.")
        self._sock = sock
        _enable_tcp_nodelay(self._sock)
        self._sock.setblocking(False)
        self._handler = handler
        self._max_frame_bytes = require_pure_int(max_frame_bytes, "max_frame_bytes", min_val=1, max_val=None)
        self._write_stall_sec = max(0.2, stall_v)
        self._on_closed = on_closed
        self._cond = threading.Condition(threading.RLock())
        self._ctrl_out_queue: deque[_OutboundFrameItem] = deque()
        self._data_out_queue: deque[_OutboundFrameItem] = deque()
        self._writer_sending = False
        self._is_initiator = is_initiator
        self._next_stream_id = 1 if is_initiator else 2
        self._closed = False
        self._retiring = False
        self._inbound_controls_in_flight = 0
        self._inbound_calls_in_flight = 0
        self._pending_calls: dict[int, _PendingCallState] = {}
        self._pending_controls: dict[str, _PendingControlWait] = {}
        self._inbound_cancels: dict[int, CancellationToken] = {}
        self._frame_handlers: dict[FrameKind, Callable[[RpcFrame], None]] = {
            FrameKind.CALL_ACCEPTED: self._on_frame_accepted,
            FrameKind.PROGRESS: self._on_frame_progress,
            FrameKind.CALL_RESULT: self._on_frame_result,
            FrameKind.CANCEL: self._on_frame_cancel,
            FrameKind.CONTROL_ACK: self._on_frame_control_ack,
            FrameKind.PONG: self._on_frame_control_ack,
            FrameKind.PING: self._on_frame_ping,
            FrameKind.CALL_START: self._on_frame_call_start,
        }
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="yscb-rpc-writer",
            daemon=True,
        )
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="yscb-rpc-reader",
            daemon=True,
        )
        try:
            self._writer_thread.start()
            self._reader_thread.start()
        except BaseException:
            self.close()
            raise

    @property
    def is_closed(self) -> bool:
        with self._cond:
            return self._closed

    @property
    def is_usable(self) -> bool:
        with self._cond:
            return not self._closed and not self._retiring

    def _closed_or_retiring_outcome_locked(self) -> Optional[RemoteCallOutcome]:
        if self._closed:
            return RemoteCallOutcome(
                was_accepted=False,
                transport_lost=True,
                error_code=ErrorCode.TRANSPORT_LOST,
                error_message="RPC channel is already closed.",
            )
        if self._retiring:
            return RemoteCallOutcome(
                was_accepted=False,
                transport_lost=False,
                rejected_before_accept=True,
                error_code=ErrorCode.DAEMON_UNAVAILABLE,
                error_message="RPC channel is retiring.",
            )
        return None

    def wait_until_closed(self, timeout_sec: Optional[float] = None) -> bool:
        safe_sec = clamp_wait_sec(timeout_sec)
        end_at = (time.monotonic() + safe_sec) if safe_sec is not None else None
        if self._reader_thread is not threading.current_thread() and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=safe_sec)
        if self._writer_thread is not threading.current_thread() and self._writer_thread.is_alive():
            rem = max(0.0, end_at - time.monotonic()) if end_at is not None else None
            self._writer_thread.join(timeout=rem)
        return self.is_closed

    def wait_inbound_controls_flushed(self, timeout_sec: float = 1.0) -> None:
        safe_sec = max(0.05, require_non_none(validate_non_negative_sec(timeout_sec, label="timeout_sec")))
        deadline = time.monotonic() + safe_sec
        with self._cond:
            while (
                not self._closed
                and (
                    self._inbound_controls_in_flight > 0
                    or self._inbound_calls_in_flight > 0
                    or bool(self._ctrl_out_queue)
                    or bool(self._data_out_queue)
                    or self._writer_sending
                )
                and time.monotonic() < deadline
            ):
                self._cond.wait(timeout=0.02)

    def call(
        self,
        payload: JsonObject,
        *,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
        cancel_token: Optional[CancellationToken] = None,
        timeout_ms: Optional[int] = None,
        cancel_grace_ms: Optional[int] = None,
    ) -> RemoteCallOutcome:
        if timeout_ms is not None:
            require_pure_int(timeout_ms, "timeout_ms", min_val=None, max_val=None)
        if cancel_grace_ms is not None:
            require_pure_int(cancel_grace_ms, "cancel_grace_ms", min_val=None, max_val=None)
        if cancel_token is not None and cancel_token.is_cancelled:
            c_code = ErrorCode.TASK_PREEMPTED if cancel_token.is_preempted else ErrorCode.TASK_CANCELLED
            return RemoteCallOutcome(
                was_accepted=False,
                error_code=c_code,
                error_message=cancel_token.reason or "RPC call cancelled before start.",
            )
        if timeout_ms is not None and timeout_ms <= 0:
            return RemoteCallOutcome(
                was_accepted=False,
                error_code=ErrorCode.TASK_TIMEOUT,
                error_message=f"RPC call timed out immediately (timeout_ms={timeout_ms}).",
            )
        clamped_sec = ms_to_safe_sec(timeout_ms) if timeout_ms is not None else None
        early_err, stream_id, pending = self._open_outbound_call_stream(payload, on_progress)
        if early_err is not None or pending is None:
            return require_non_none(early_err)
        return self._await_outbound_call_stream(
            stream_id, pending, cancel_token, timeout_ms, clamped_sec, cancel_grace_ms
        )

    def _open_outbound_call_stream(
        self,
        payload: JsonObject,
        on_progress: Optional[Callable[[JsonObject], None]],
    ) -> tuple[Optional[RemoteCallOutcome], int, Optional[_PendingCallState]]:
        with self._cond:
            early = self._closed_or_retiring_outcome_locked()
            if early is not None:
                return (early, -1, None)
            while self._next_stream_id > 0x7FFFFFFF or self._next_stream_id in self._pending_calls:
                self._next_stream_id = (
                    (1 if self._is_initiator else 2)
                    if self._next_stream_id > 0x7FFFFFFF
                    else (self._next_stream_id + 2)
                )
            stream_id = self._next_stream_id
            self._next_stream_id += 2

        try:
            frame_bytes = _encode_raw_frame(
                RpcFrame(kind=FrameKind.CALL_START, stream_id=stream_id, payload=payload),
                max_frame_bytes=self._max_frame_bytes,
            )
        except OverflowError as exc:
            return (
                RemoteCallOutcome(
                    was_accepted=False,
                    error_code=ErrorCode.PAYLOAD_TOO_LARGE,
                    error_message=safe_exception_summary(exc),
                ),
                -1,
                None,
            )
        except (TypeError, ValueError) as exc:
            return (
                RemoteCallOutcome(
                    was_accepted=False,
                    error_code=ErrorCode.CODEC_VALIDATION_FAILED,
                    error_message=safe_exception_summary(exc),
                ),
                -1,
                None,
            )

        pending = _PendingCallState(on_progress)
        with self._cond:
            early = self._closed_or_retiring_outcome_locked()
            if early is not None:
                return (early, -1, None)
            if stream_id in self._pending_calls:
                return (
                    RemoteCallOutcome(
                        was_accepted=False,
                        transport_lost=True,
                        error_code=ErrorCode.TRANSPORT_LOST,
                        error_message="RPC stream_id collision on saturated channel.",
                    ),
                    -1,
                    None,
                )
            self._pending_calls[stream_id] = pending
            self._data_out_queue.append(_OutboundFrameItem(frame_bytes, call_start_sid=stream_id))
            self._cond.notify_all()
        return (None, stream_id, pending)

    def _drop_unsent_call_start_locked(self, stream_id: int) -> bool:
        for item in tuple(self._data_out_queue):
            if item.call_start_sid == stream_id:
                self._data_out_queue.remove(item)
                return True
        return False

    def _on_caller_cancel_outbound(
        self,
        stream_id: int,
        pending: _PendingCallState,
        preempted: bool,
        reason: str,
        cancel_grace_ms: Optional[int],
    ) -> None:
        dropped_unsent = False
        with self._cond:
            if self._drop_unsent_call_start_locked(stream_id):
                dropped_unsent = True
                self._pending_calls.pop(stream_id, None)
                pending.was_accepted = False
                pending.error_code = ErrorCode.TASK_PREEMPTED if preempted else ErrorCode.TASK_CANCELLED
                pending.error_message = reason or "RPC call cancelled before dispatch."
                pending.done.set()
        if dropped_unsent:
            pending.wake.set()
            self._check_retire_idle()
            return
        self._try_send_frame(
            RpcFrame(
                kind=FrameKind.CANCEL,
                stream_id=stream_id,
                payload={"preempted": preempted, "reason": reason},
            )
        )
        if cancel_grace_ms is not None:
            g_dl = time.monotonic() + ms_to_safe_sec(cancel_grace_ms, min_sec=0.05)
            with self._cond:
                if pending.cancel_grace_deadline is None or g_dl < pending.cancel_grace_deadline:
                    pending.cancel_grace_deadline = g_dl
                pending.cancel_preempted = preempted
                pending.cancel_reason = reason
            pending.wake.set()

    def _abandon_cancelled_outbound_stream(self, stream_id: int, pending: _PendingCallState) -> RemoteCallOutcome:
        already: Optional[RemoteCallOutcome] = None
        with self._cond:
            popped = self._pending_calls.pop(stream_id, None)
            if popped is None and pending.done.is_set():
                already = pending.to_outcome()
            accepted = pending.was_accepted
            code = ErrorCode.TASK_PREEMPTED if pending.cancel_preempted else ErrorCode.TASK_CANCELLED
            msg = pending.cancel_reason or "Cancelled stream exceeded grace window"
        self._check_retire_idle()
        if already is not None:
            return _settle_stream_outcome(pending, already)
        return RemoteCallOutcome(was_accepted=accepted, error_code=code, error_message=msg)

    def _timeout_outbound_call_stream(
        self,
        stream_id: int,
        pending: _PendingCallState,
        timeout_ms: Optional[int],
    ) -> RemoteCallOutcome:
        already: Optional[RemoteCallOutcome] = None
        send_cancel = False
        with self._cond:
            dropped = self._drop_unsent_call_start_locked(stream_id)
            popped = self._pending_calls.pop(stream_id, None)
            if popped is None and pending.done.is_set():
                already = pending.to_outcome()
            accepted = False if dropped else pending.was_accepted
            send_cancel = not dropped and already is None
        if send_cancel:
            self._try_send_frame(RpcFrame(kind=FrameKind.CANCEL, stream_id=stream_id, payload={}))
        self._check_retire_idle()
        if already is not None:
            return _settle_stream_outcome(pending, already)
        return RemoteCallOutcome(
            was_accepted=accepted,
            error_code=ErrorCode.TASK_TIMEOUT,
            error_message=f"RPC call timed out after {timeout_ms}ms.",
        )

    def _compute_stream_wait_slice(
        self,
        pending: _PendingCallState,
        deadline: Optional[float],
    ) -> tuple[bool, bool, Optional[float]]:
        now = time.monotonic()
        with self._cond:
            grace_dl = pending.cancel_grace_deadline
        if grace_dl is not None and now >= grace_dl:
            return (True, False, None)
        if deadline is not None and now >= deadline:
            return (False, True, None)
        candidates = [d - now for d in (deadline, grace_dl) if d is not None]
        if not candidates:
            return (False, False, None)
        rem = min(candidates)
        return (False, False, min(rem, MAX_SAFE_WAIT_SEC) if math.isfinite(rem) else MAX_SAFE_WAIT_SEC)

    def _wait_call_stream_loop(
        self,
        stream_id: int,
        pending: _PendingCallState,
        deadline: Optional[float],
        timeout_ms: Optional[int],
    ) -> RemoteCallOutcome:
        while True:
            pending.wake.clear()
            with self._cond:
                lost_now = pending.transport_lost
            if not lost_now:
                pending.drain_progress_inline()
            if pending.done.is_set():
                with self._cond:
                    settled = pending.to_outcome()
                return _settle_stream_outcome(pending, settled)
            grace_exp, timed_out, wait_slice = self._compute_stream_wait_slice(pending, deadline)
            if grace_exp:
                return self._abandon_cancelled_outbound_stream(stream_id, pending)
            if timed_out:
                return self._timeout_outbound_call_stream(stream_id, pending, timeout_ms)
            pending.wake.wait(timeout=wait_slice)

    def _await_outbound_call_stream(
        self,
        stream_id: int,
        pending: _PendingCallState,
        cancel_token: Optional[CancellationToken],
        timeout_ms: Optional[int],
        clamped_sec: Optional[float],
        cancel_grace_ms: Optional[int],
    ) -> RemoteCallOutcome:
        unregister_cancel: Optional[Callable[[], None]] = None
        try:
            if cancel_token is not None:
                unregister_cancel = cancel_token.register_callback(
                    lambda p, r: self._on_caller_cancel_outbound(stream_id, pending, p, r, cancel_grace_ms)
                )
            deadline = (time.monotonic() + clamped_sec) if clamped_sec is not None else None
            return self._wait_call_stream_loop(stream_id, pending, deadline, timeout_ms)
        except BaseException:
            send_cancel = False
            with self._cond:
                dropped = self._drop_unsent_call_start_locked(stream_id)
                self._pending_calls.pop(stream_id, None)
                send_cancel = not dropped and not pending.done.is_set()
            if send_cancel:
                self._try_send_frame(
                    RpcFrame(kind=FrameKind.CANCEL, stream_id=stream_id, payload={"reason": "Caller interrupted"})
                )
            self._check_retire_idle()
            raise
        finally:
            if unregister_cancel is not None:
                unregister_cancel()

    def send_control(
        self,
        kind: FrameKind,
        payload: JsonObject,
        *,
        timeout_ms: int = 5000,
    ) -> Optional[JsonObject]:
        require_pure_int(timeout_ms, "timeout_ms", min_val=None, max_val=None)
        if (kind not in _INBOUND_CONTROL_KINDS and kind != FrameKind.PING) or timeout_ms <= 0:
            return None
        wait_sec = ms_to_safe_sec(timeout_ms)
        expected_ack = FrameKind.PONG if kind == FrameKind.PING else FrameKind.CONTROL_ACK
        req_id = uuid.uuid4().hex
        done = threading.Event()
        holder: dict[str, JsonObject] = {}
        with self._cond:
            if self._closed:
                return None
            self._pending_controls[req_id] = _PendingControlWait(expected_ack, done, holder)
        try:
            try:
                out_frame = RpcFrame(kind=kind, stream_id=0, payload=payload, meta={"req_id": req_id})
            except (TypeError, ValueError):
                return None
            if not self._try_send_frame(out_frame):
                return None
            if not done.wait(timeout=wait_sec):
                return None
            return holder.get("response")
        finally:
            with self._cond:
                self._pending_controls.pop(req_id, None)
            self._check_retire_idle()

    def post_control(self, kind: FrameKind, payload: JsonObject) -> bool:
        if kind not in _INBOUND_CONTROL_KINDS and kind != FrameKind.PING:
            return False
        try:
            out_frame = RpcFrame(kind=kind, stream_id=0, payload=payload)
        except (TypeError, ValueError):
            return False
        return self._try_send_frame(out_frame)

    def ping(self, *, timeout_ms: int = 2000) -> bool:
        resp = self.send_control(FrameKind.PING, {}, timeout_ms=timeout_ms)
        return bool(resp and resp.get("ok") is True)

    def close_when_idle(self) -> None:
        with self._cond:
            self._retiring = True
        self._check_retire_idle()

    def _check_retire_idle(self) -> None:
        should_close = False
        with self._cond:
            if (
                self._retiring
                and not self._closed
                and not self._pending_calls
                and not self._pending_controls
                and not self._inbound_cancels
                and self._inbound_controls_in_flight == 0
                and self._inbound_calls_in_flight == 0
                and not self._ctrl_out_queue
                and not self._data_out_queue
                and not self._writer_sending
            ):
                should_close = True
        if should_close:
            self.close()

    def close(self) -> None:
        with self._cond:
            if self._closed:
                return
            self._closed = True
            aborted_out = (*self._ctrl_out_queue, *self._data_out_queue)
            self._ctrl_out_queue.clear()
            self._data_out_queue.clear()
            self._cond.notify_all()
            pending_calls = list(self._pending_calls.values())
            self._pending_calls.clear()
            pending_ctrls = list(self._pending_controls.values())
            self._pending_controls.clear()
            inbound_tokens = list(self._inbound_cancels.values())
            self._inbound_cancels.clear()
            for p in pending_calls:
                p.transport_lost = True
                p.error_code = ErrorCode.TRANSPORT_LOST
                p.error_message = "Peer socket closed before CALL_RESULT."
                p.done.set()

        _shutdown_and_close_sock(self._sock)
        for p in pending_calls:
            p.wake.set()
        for item_ab in aborted_out:
            _finish_outbound_item(item_ab, False)
        for cw in pending_ctrls:
            cw.done.set()
        cur_th = threading.current_thread()
        if cur_th is not self._reader_thread and cur_th is not self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=0.5)
        try:
            _dispatch_cancel_thunks(
                tuple(fn for token in inbound_tokens for fn in token.cancel_deferred(reason="peer disconnected")),
                from_io_thread=(cur_th in (self._reader_thread, self._writer_thread)),
            )
        finally:
            if self._on_closed is not None:
                self._on_closed(self)

    def _enqueue_outbound_bytes(
        self,
        data: bytes,
        *,
        priority: bool = False,
        wait_flushed: bool = False,
    ) -> bool:
        ev = threading.Event() if wait_flushed else None
        ok_box: Optional[list[bool]] = [] if wait_flushed else None
        item = _OutboundFrameItem(data, ev, ok_box)
        with self._cond:
            if self._closed:
                return False
            if priority:
                self._ctrl_out_queue.append(item)
            else:
                self._data_out_queue.append(item)
            self._cond.notify_all()
        if ev is None or ok_box is None:
            return True
        if not ev.wait(timeout=self._write_stall_sec + 1.0):
            need_close = False
            with self._cond:
                if ev.is_set():
                    return bool(ok_box and ok_box[0])
                target_q = self._ctrl_out_queue if priority else self._data_out_queue
                if item in target_q:
                    target_q.remove(item)
                    return False
                need_close = not self._closed
            if need_close:
                self.close()
            return False
        return bool(ok_box and ok_box[0])

    def _try_send_frame(self, frame: RpcFrame, *, wait_flushed: bool = False) -> bool:
        try:
            encoded = _encode_raw_frame(frame, max_frame_bytes=self._max_frame_bytes)
        except (OverflowError, TypeError, ValueError):
            return False
        prio = frame.kind not in (FrameKind.CALL_START, FrameKind.CALL_RESULT, FrameKind.PROGRESS)
        return self._enqueue_outbound_bytes(encoded, priority=prio, wait_flushed=wait_flushed)

    def _pop_outbound_frame(self) -> Optional[_OutboundFrameItem]:
        became_drain_idle = False
        with self._cond:
            was_sending = self._writer_sending
            self._writer_sending = False
            if was_sending and not self._ctrl_out_queue and not self._data_out_queue:
                self._cond.notify_all()
                became_drain_idle = self._retiring and not self._closed
        if became_drain_idle:
            self._check_retire_idle()
        with self._cond:
            while not self._closed and not self._ctrl_out_queue and not self._data_out_queue:
                self._cond.wait()
            if self._closed:
                return None
            self._writer_sending = True
            return self._ctrl_out_queue.popleft() if self._ctrl_out_queue else self._data_out_queue.popleft()

    def _writer_loop(self) -> None:
        try:
            while True:
                nxt = self._pop_outbound_frame()
                if nxt is None:
                    return
                ok = _send_frame_bounded(self._sock, nxt.data, self._write_stall_sec, lambda: self._closed)
                _finish_outbound_item(nxt, ok)
                if not ok:
                    self.close()
                    return
        finally:
            with self._cond:
                self._writer_sending = False

    def _reader_loop(self) -> None:
        try:
            while True:
                try:
                    frame = _read_raw_frame(self._sock, max_frame_bytes=self._max_frame_bytes)
                except (ValueError, KeyError, TypeError, RecursionError):
                    break
                if frame is None:
                    break
                self._dispatch_frame(frame)
        finally:
            self.close()

    def _is_valid_inbound_stream_id(self, frame: RpcFrame) -> bool:
        if frame.kind in (FrameKind.HELLO, FrameKind.HELLO_ACK):
            return False
        sid = frame.stream_id
        if frame.kind in _INBOUND_CONTROL_KINDS or frame.kind in (
            FrameKind.CONTROL_ACK,
            FrameKind.PING,
            FrameKind.PONG,
        ):
            return sid == 0
        if sid <= 0:
            return False
        peer_init_parity = 0 if self._is_initiator else 1
        own_init_parity = 1 if self._is_initiator else 0
        if frame.kind in (FrameKind.CALL_START, FrameKind.CANCEL):
            return (sid % 2) == peer_init_parity
        return (sid % 2) == own_init_parity

    def _dispatch_frame(self, frame: RpcFrame) -> None:
        if not self._is_valid_inbound_stream_id(frame):
            self.close()
            return
        direct_fn = self._frame_handlers.get(frame.kind)
        if direct_fn is not None:
            direct_fn(frame)
            return
        if frame.kind in _INBOUND_CONTROL_KINDS:
            self._dispatch_inbound_control(frame)

    def _dispatch_inbound_control(self, frame: RpcFrame) -> None:
        raw_rid = frame.meta.get("req_id")
        req_id = raw_rid if type(raw_rid) is str else ""
        overloaded = False
        with self._cond:
            if self._closed:
                return
            if self._inbound_controls_in_flight >= _MAX_INBOUND_CONTROLS_PER_CHANNEL:
                overloaded = True
            else:
                self._inbound_controls_in_flight += 1
        if overloaded:
            ack_b = _encode_control_ack_bytes(
                req_id,
                {"ok": False, "error": "Inbound RPC control concurrency limit exceeded."},
                self._max_frame_bytes,
            )
            if ack_b is not None:
                self._enqueue_outbound_bytes(ack_b, priority=True)
            return
        try:
            threading.Thread(
                target=self._handle_inbound_control,
                args=(frame.kind, frame.payload, req_id),
                name="yscb-rpc-ctrl",
                daemon=True,
            ).start()
        except BaseException as exc:
            with self._cond:
                self._inbound_controls_in_flight = max(0, self._inbound_controls_in_flight - 1)
                self._cond.notify_all()
            self.close()
            if not isinstance(exc, Exception):
                raise

    def _on_frame_accepted(self, frame: RpcFrame) -> None:
        with self._cond:
            p = self._pending_calls.get(frame.stream_id)
            if p is not None:
                p.was_accepted = True

    def _on_frame_progress(self, frame: RpcFrame) -> None:
        with self._cond:
            p = self._pending_calls.get(frame.stream_id)
        if p is not None:
            p.enqueue_progress(frame.payload)

    def _on_frame_result(self, frame: RpcFrame) -> None:
        err_code: Optional[ErrorCode] = None
        err_code_raw = frame.meta.get("error_code")
        if type(err_code_raw) is str:
            try:
                err_code = ErrorCode(err_code_raw)
            except ValueError:
                err_code = None
        err_msg_raw = frame.meta.get("error_message")
        err_msg = err_msg_raw if type(err_msg_raw) is str else None
        rem_raw = frame.meta.get("error_remediation")
        src_raw = frame.meta.get("error_source_task")
        with self._cond:
            p = self._pending_calls.pop(frame.stream_id, None)
            if p is None:
                return
            rejected = (frame.meta.get("rejected_before_accept") is True) and not p.was_accepted
            p.was_accepted = p.was_accepted or not rejected
            p.rejected_before_accept = rejected
            p.error_code = err_code
            p.error_message = err_msg
            p.error_remediation = rem_raw if type(rem_raw) is str else None
            p.error_source_task = src_raw if type(src_raw) is str else None
            p.result_payload = frame.payload
            p.done.set()
        p.wake.set()
        self._check_retire_idle()

    def _on_frame_cancel(self, frame: RpcFrame) -> None:
        with self._cond:
            tok = self._inbound_cancels.get(frame.stream_id)
        if tok is not None:
            is_pre = frame.payload.get("preempted") is True
            rsn_raw = frame.payload.get("reason")
            rsn = rsn_raw if isinstance(rsn_raw, str) and rsn_raw else "cancelled by peer CANCEL frame"
            thunks = tok.cancel_deferred(preempted=is_pre, reason=rsn)
            _dispatch_cancel_thunks(thunks, from_io_thread=True)

    def _on_frame_control_ack(self, frame: RpcFrame) -> None:
        req_id_raw = frame.meta.get("req_id")
        if type(req_id_raw) is not str or not req_id_raw:
            return
        matched: Optional[_PendingControlWait] = None
        with self._cond:
            cand = self._pending_controls.get(req_id_raw)
            if cand is not None and cand.expected_kind == frame.kind:
                matched = self._pending_controls.pop(req_id_raw)
        if matched is not None:
            matched.holder["response"] = dict(frame.payload)
            matched.done.set()
        self._check_retire_idle()

    def _on_frame_ping(self, frame: RpcFrame) -> None:
        raw_rid = frame.meta.get("req_id")
        meta_out: JsonObject = {"req_id": raw_rid if type(raw_rid) is str else ""}
        self._try_send_frame(RpcFrame(kind=FrameKind.PONG, stream_id=0, payload={"ok": True}, meta=meta_out))

    def _on_frame_call_start(self, frame: RpcFrame) -> None:
        peer_token = CancellationToken()
        duplicate_sid = False
        overloaded = False
        with self._cond:
            if self._closed:
                return
            if frame.stream_id in self._inbound_cancels:
                duplicate_sid = True
            elif self._inbound_calls_in_flight >= _MAX_INBOUND_CALLS_PER_CHANNEL:
                overloaded = True
            else:
                self._inbound_cancels[frame.stream_id] = peer_token
                self._inbound_calls_in_flight += 1
        if duplicate_sid:
            self.close()
            return
        if overloaded:
            self._try_send_frame(
                RpcFrame(
                    kind=FrameKind.CALL_RESULT,
                    stream_id=frame.stream_id,
                    payload={"ok": False},
                    meta={
                        "rejected_before_accept": True,
                        "error_code": ErrorCode.DAEMON_UNAVAILABLE.value,
                        "error_message": "Inbound RPC stream concurrency limit exceeded.",
                    },
                )
            )
            return
        self._spawn_inbound_call_worker(frame, peer_token)

    def _spawn_inbound_call_worker(self, frame: RpcFrame, peer_token: CancellationToken) -> None:
        try:
            threading.Thread(
                target=self._handle_inbound_call,
                args=(frame.stream_id, frame.payload, peer_token),
                name=f"yscb-rpc-call-{frame.stream_id}",
                daemon=True,
            ).start()
        except BaseException as exc:
            with self._cond:
                if self._inbound_cancels.get(frame.stream_id) is peer_token:
                    self._inbound_cancels.pop(frame.stream_id, None)
                self._inbound_calls_in_flight = max(0, self._inbound_calls_in_flight - 1)
                self._cond.notify_all()
            self.close()
            if not isinstance(exc, Exception):
                raise

    def _handle_inbound_control(self, kind: FrameKind, payload: JsonObject, req_id: str) -> None:
        try:
            resp: JsonObject = {"ok": False}
            if self._handler is not None:
                try:
                    resp = dict(self._handler.on_control(kind, payload))
                except (Exception, SystemExit, GeneratorExit) as exc:
                    resp = {"ok": False, "error": safe_exception_summary(exc)}
            if req_id:
                ack_bytes = _encode_control_ack_bytes(req_id, resp, self._max_frame_bytes)
                if ack_bytes is not None:
                    self._enqueue_outbound_bytes(ack_bytes, priority=True)
        except BaseException:
            self.close()
            raise
        finally:
            with self._cond:
                self._inbound_controls_in_flight = max(0, self._inbound_controls_in_flight - 1)
                self._cond.notify_all()
            self._check_retire_idle()

    def _handle_inbound_call(
        self,
        stream_id: int,
        payload: JsonObject,
        peer_token: CancellationToken,
    ) -> None:
        accepted_sent = False
        accept_lock = threading.Lock()

        def _ack_accepted() -> bool:
            nonlocal accepted_sent
            with accept_lock:
                if accepted_sent:
                    return True
                ok = self._try_send_frame(
                    RpcFrame(kind=FrameKind.CALL_ACCEPTED, stream_id=stream_id, payload={}),
                    wait_flushed=True,
                )
                if ok:
                    accepted_sent = True
                return ok

        try:
            if self._handler is None:
                self._try_send_frame(
                    RpcFrame(
                        kind=FrameKind.CALL_RESULT,
                        stream_id=stream_id,
                        payload={"ok": False},
                        meta={"rejected_before_accept": True, "error_message": "No handler bound"},
                    )
                )
                return
            try:
                def _emit_progress(prog: JsonObject) -> None:
                    if _ack_accepted():
                        self._try_send_frame(RpcFrame(kind=FrameKind.PROGRESS, stream_id=stream_id, payload=prog))

                accepted, res_payload = self._handler.on_call(
                    stream_id,
                    payload,
                    _ack_accepted,
                    _emit_progress,
                    peer_token,
                )
            except (Exception, SystemExit, GeneratorExit) as exc:
                err_code = exc.detail.code if isinstance(exc, YscbError) else ErrorCode.BUSINESS_FAILURE
                err_msg = exc.detail.message if isinstance(exc, YscbError) else safe_exception_summary(exc)
                err_meta: dict[str, JsonValue] = {
                    "rejected_before_accept": not accepted_sent,
                    "error_code": err_code.value,
                    "error_message": err_msg,
                }
                if isinstance(exc, YscbError) and exc.detail.remediation is not None:
                    err_meta["error_remediation"] = exc.detail.remediation
                if isinstance(exc, YscbError) and exc.detail.source_task is not None:
                    err_meta["error_source_task"] = exc.detail.source_task
                if not self._try_send_frame(
                    RpcFrame(kind=FrameKind.CALL_RESULT, stream_id=stream_id, payload={"ok": False}, meta=err_meta)
                ):
                    self.close()
                return
            self._send_inbound_call_result(stream_id, accepted or accepted_sent, res_payload, _ack_accepted)
        except BaseException:
            self.close()
            raise
        finally:
            with self._cond:
                if self._inbound_cancels.get(stream_id) is peer_token:
                    self._inbound_cancels.pop(stream_id, None)
                self._inbound_calls_in_flight = max(0, self._inbound_calls_in_flight - 1)
                self._cond.notify_all()
            self._check_retire_idle()

    def _send_inbound_call_result(
        self,
        stream_id: int,
        accepted: bool,
        res_payload: JsonObject,
        ack_accepted: Callable[[], bool],
    ) -> None:
        eff_accepted = accepted and ack_accepted()
        res_meta: JsonObject = {"rejected_before_accept": True} if not eff_accepted else {}
        accepted = eff_accepted
        try:
            encoded = _encode_raw_frame(
                RpcFrame(kind=FrameKind.CALL_RESULT, stream_id=stream_id, payload=res_payload, meta=res_meta),
                max_frame_bytes=self._max_frame_bytes,
            )
            self._enqueue_outbound_bytes(encoded, priority=False)
        except OverflowError as exc:
            err_meta: JsonObject = {
                "rejected_before_accept": not accepted,
                "error_code": ErrorCode.PAYLOAD_TOO_LARGE.value,
                "error_message": safe_exception_summary(exc),
            }
            if not self._try_send_frame(
                RpcFrame(kind=FrameKind.CALL_RESULT, stream_id=stream_id, payload={"ok": False}, meta=err_meta)
            ):
                self.close()
        except (TypeError, ValueError) as exc:
            err_meta = {
                "rejected_before_accept": not accepted,
                "error_code": ErrorCode.CODEC_VALIDATION_FAILED.value,
                "error_message": safe_exception_summary(exc),
            }
            if not self._try_send_frame(
                RpcFrame(kind=FrameKind.CALL_RESULT, stream_id=stream_id, payload={"ok": False}, meta=err_meta)
            ):
                self.close()


def _is_valid_protocol_version(payload: Mapping[str, object]) -> bool:
    proto = payload.get("protocol")
    return isinstance(proto, int) and not isinstance(proto, bool) and proto == _PROTOCOL_VERSION


def _is_valid_hello_payload(
    payload: Mapping[str, object],
    expected_auth_token: str,
    expected_boot_id: str,
    expected_workspace_root: Optional[HostPath],
) -> bool:
    if not _is_valid_protocol_version(payload):
        return False
    tok_raw = payload.get("auth_token")
    boot_raw = payload.get("boot_id")
    ws_raw = payload.get("workspace_root")
    if type(tok_raw) is not str or type(boot_raw) is not str or type(ws_raw) is not str or not ws_raw:
        return False
    tok_ok = _const_time_utf8_eq(tok_raw, expected_auth_token)
    boot_ok = _const_time_utf8_eq(boot_raw, expected_boot_id)
    try:
        parsed_ws = HostPath(ws_raw)
        ws_ok = expected_workspace_root is None or parsed_ws == expected_workspace_root
    except (ValueError, OSError):
        ws_ok = False
    return tok_ok and boot_ok and ws_ok


def _const_time_utf8_eq(left: str, right: str) -> bool:
    try:
        return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
    except UnicodeEncodeError:
        return False


def _send_reject_ack_quietly(conn: socket.socket, max_frame_bytes: int) -> None:
    try:
        conn.settimeout(2.0)
        conn.sendall(
            _encode_raw_frame(
                RpcFrame(FrameKind.HELLO_ACK, 0, {"ok": False, "protocol": _PROTOCOL_VERSION}),
                max_frame_bytes=max_frame_bytes,
            )
        )
    except OSError:
        pass


def _verify_inbound_hello(
    conn: socket.socket,
    expected_auth_token: str,
    expected_boot_id: str,
    expected_workspace_root: Optional[HostPath],
    max_frame_bytes: int,
    timeout_sec: float = 2.0,
) -> bool:
    try:
        _enable_tcp_nodelay(conn)
        hs_cap = min(max_frame_bytes, _MAX_HANDSHAKE_FRAME_BYTES)
        hello = _read_raw_frame(conn, max_frame_bytes=hs_cap, deadline=time.monotonic() + timeout_sec)
        if hello is None or hello.kind != FrameKind.HELLO or hello.stream_id != 0:
            _shutdown_and_close_sock(conn)
            return False
        if not _is_valid_hello_payload(
            hello.payload, expected_auth_token, expected_boot_id, expected_workspace_root
        ):
            _send_reject_ack_quietly(conn, max_frame_bytes)
            _shutdown_and_close_sock(conn)
            return False
        return True
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError, YscbError):
        _shutdown_and_close_sock(conn)
        return False
    except BaseException:
        _shutdown_and_close_sock(conn)
        raise


def _open_accepted_peer_channel(
    conn: socket.socket,
    boot_id: str,
    handler: InboundCallHandler,
    max_frame_bytes: int,
    on_closed: Optional[Callable[[MultiplexedChannel], None]] = None,
) -> Optional[MultiplexedChannel]:
    try:
        conn.sendall(
            _encode_raw_frame(
                RpcFrame(
                    kind=FrameKind.HELLO_ACK,
                    stream_id=0,
                    payload={"ok": True, "boot_id": boot_id, "protocol": _PROTOCOL_VERSION},
                ),
                max_frame_bytes=max_frame_bytes,
            )
        )
        return MultiplexedChannel(
            conn,
            is_initiator=False,
            handler=handler,
            max_frame_bytes=max_frame_bytes,
            on_closed=on_closed,
        )
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError, YscbError):
        _shutdown_and_close_sock(conn)
        return None
    except BaseException:
        _shutdown_and_close_sock(conn)
        raise


def accept_worker_handshake(
    conn: socket.socket,
    *,
    expected_auth_token: str,
    boot_id: str,
    handler: InboundCallHandler,
    expected_workspace_root: Optional[HostPath] = None,
    max_frame_bytes: int = MAX_FRAME_BYTES,
) -> Optional[MultiplexedChannel]:
    """Perform server-side constant-time HELLO handshake on an accepted peer socket."""
    try:
        safe_max = require_pure_int(max_frame_bytes, "max_frame_bytes", min_val=1, max_val=None)
        sock_tmo = conn.gettimeout()
        safe_hs = (
            min(10.0, max(0.05, sock_tmo))
            if (sock_tmo is not None and math.isfinite(sock_tmo) and sock_tmo > 0.0)
            else 2.0
        )
    except BaseException:
        _shutdown_and_close_sock(conn)
        raise
    if not _verify_inbound_hello(conn, expected_auth_token, boot_id, expected_workspace_root, safe_max, safe_hs):
        return None
    return _open_accepted_peer_channel(conn, boot_id, handler, safe_max)


def connect_and_handshake(
    endpoint: RpcEndpointInfo,
    *,
    handler: Optional[InboundCallHandler] = None,
    connect_timeout_sec: float = 1.0,
    max_frame_bytes: int = MAX_FRAME_BYTES,
) -> Optional[MultiplexedChannel]:
    """Connect to a loopback RPC endpoint, complete HELLO/HELLO_ACK handshake, and return a MultiplexedChannel."""
    safe_timeout = max(0.05, require_non_none(validate_non_negative_sec(connect_timeout_sec, label="connect_timeout_sec")))
    safe_max = require_pure_int(max_frame_bytes, "max_frame_bytes", min_val=1, max_val=None)
    deadline = time.monotonic() + safe_timeout
    hs_cap = min(safe_max, _MAX_HANDSHAKE_FRAME_BYTES)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(safe_timeout)
        sock.connect((endpoint.host, endpoint.port))
        _enable_tcp_nodelay(sock)
        rem_send = deadline - time.monotonic()
        if rem_send <= 0.0:
            sock.close()
            return None
        sock.settimeout(rem_send)
        hello = _encode_raw_frame(
            RpcFrame(
                kind=FrameKind.HELLO,
                stream_id=0,
                payload={
                    "protocol": _PROTOCOL_VERSION,
                    "auth_token": endpoint.auth_token,
                    "boot_id": endpoint.boot_id,
                    "workspace_root": str(endpoint.workspace_root),
                },
            ),
            max_frame_bytes=hs_cap,
        )
        sock.sendall(hello)
        ack = _read_raw_frame(sock, max_frame_bytes=hs_cap, deadline=deadline)
        if (
            ack is None
            or ack.kind != FrameKind.HELLO_ACK
            or ack.stream_id != 0
            or ack.payload.get("ok") is not True
            or not _is_valid_protocol_version(ack.payload)
        ):
            sock.close()
            return None
        ack_boot = ack.payload.get("boot_id")
        if type(ack_boot) is not str or not _const_time_utf8_eq(ack_boot, endpoint.boot_id):
            sock.close()
            return None
        return MultiplexedChannel(
            sock,
            is_initiator=True,
            handler=handler,
            max_frame_bytes=safe_max,
        )
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError, YscbError):
        try:
            sock.close()
        except OSError:
            pass
        return None
    except BaseException:
        try:
            sock.close()
        except OSError:
            pass
        raise


def build_daemon_endpoint_dict(info: RpcEndpointInfo) -> JsonObject:
    """Serialize RpcEndpointInfo using the canonical daemon.json field schema."""
    if not isinstance(info, RpcEndpointInfo):
        raise ValueError(f"Expected RpcEndpointInfo, got {info!r}")
    return {
        "pid": info.pid,
        "host": info.host,
        "port": info.port,
        "boot_id": info.boot_id,
        "auth_token": info.auth_token,
        "workspace_root": str(info.workspace_root),
    }


def build_handoff_lease_dict(old_boot_id: str, expires_epoch: float) -> JsonObject:
    """Serialize core handoff lease metadata using the canonical handoff_lease.json field schema."""
    require_pure_str(old_boot_id, "old_boot_id", non_empty=True)
    exp = safe_real_to_float(expires_epoch)
    if not math.isfinite(exp):
        raise ValueError("expires_epoch must be finite")
    return {"old_boot_id": old_boot_id, "expires_epoch": exp}


def read_daemon_endpoint_file(cache_dir: HostPath, workspace_root: HostPath) -> Optional[RpcEndpointInfo]:
    """Read and validate daemon.json coordinates without opening a network socket or following symlinks."""
    data = read_json_dict(cache_dir, DAEMON_SUBDIR, DAEMON_ENDPOINT_FILENAME)
    if not data:
        return None
    try:
        pid_raw = data["pid"]
        port_raw = data["port"]
        if type(pid_raw) is not int or type(port_raw) is not int or pid_raw <= 0 or not (1 <= port_raw <= 65535):
            return None
        host_raw = data.get("host", "127.0.0.1")
        boot_raw = data["boot_id"]
        tok_raw = data["auth_token"]
        ws_raw = data["workspace_root"]
        for s_val in (host_raw, boot_raw, tok_raw, ws_raw):
            require_pure_str(s_val, "daemon.json field", non_empty=True)
        info = RpcEndpointInfo(
            pid=pid_raw,
            host=str(host_raw),
            port=port_raw,
            boot_id=str(boot_raw),
            auth_token=str(tok_raw),
            workspace_root=HostPath(str(ws_raw)),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if info.workspace_root != workspace_root or not is_process_alive(info.pid):
        return None
    return info


def probe_daemon_endpoint(
    cache_dir: HostPath,
    workspace_root: HostPath,
    *,
    timeout_sec: float = 0.6,
) -> Optional[RpcEndpointInfo]:
    """Read-only endpoint discovery and mutual HELLO/HELLO_ACK probe (never mutates daemon.json)."""
    safe_timeout = max(0.05, require_non_none(validate_non_negative_sec(timeout_sec, label="timeout_sec")))
    info = read_daemon_endpoint_file(cache_dir, workspace_root)
    if info is None:
        return None
    ch = connect_and_handshake(info, connect_timeout_sec=safe_timeout)
    if ch is None:
        return None
    ch.close()
    return info


def read_active_handoff_boot_id(cache_dir: HostPath) -> Optional[str]:
    """Return old_boot_id if a cross-process core handoff lease is currently active, otherwise None."""
    data = read_json_dict(cache_dir, DAEMON_SUBDIR, DAEMON_HANDOFF_FILENAME)
    if not data:
        return None
    exp_raw = data.get("expires_epoch", 0.0)
    try:
        exp = safe_real_to_float(exp_raw)
    except ValueError:
        return None
    now_epoch = time.time()
    if not math.isfinite(exp) or exp <= now_epoch or (exp - now_epoch) > 30.0:
        return None
    old_raw = data.get("old_boot_id")
    return old_raw if (type(old_raw) is str and bool(old_raw)) else None


def wait_for_handoff_daemon_endpoint(
    cache_dir: HostPath,
    workspace_root: HostPath,
    cancel_token: Optional[CancellationToken] = None,
    *,
    max_wait_sec: float = 8.0,
    previous_boot_id: Optional[str] = None,
) -> Optional[RpcEndpointInfo]:
    """Wait for a replacement Daemon endpoint across core handoff, including fast-booted successors."""
    safe_wait = max(0.05, require_non_none(validate_non_negative_sec(max_wait_sec, label="max_wait_sec")))
    old_boot = read_active_handoff_boot_id(cache_dir)
    if old_boot is None:
        if previous_boot_id is None and read_json_dict(cache_dir, DAEMON_SUBDIR, DAEMON_HANDOFF_FILENAME) is not None:
            return None
        probed_now = probe_daemon_endpoint(cache_dir, workspace_root)
        if probed_now is not None and (previous_boot_id is None or probed_now.boot_id != previous_boot_id):
            return probed_now
        return None
    deadline = time.monotonic() + safe_wait
    while time.monotonic() < deadline:
        if cancel_token is not None and cancel_token.is_cancelled:
            return None
        info = read_daemon_endpoint_file(cache_dir, workspace_root)
        if info is not None and info.boot_id != old_boot:
            probed = probe_daemon_endpoint(cache_dir, workspace_root)
            if probed is not None and probed.boot_id != old_boot:
                return probed
        if read_active_handoff_boot_id(cache_dir) is None:
            probed = probe_daemon_endpoint(cache_dir, workspace_root)
            return probed if (probed is not None and probed.boot_id != old_boot) else None
        time.sleep(0.03)
    return None


class PersistentRpcSession:
    """Long-lived client session auto-healing across Daemon Idle TTL shutdowns and handoffs."""

    def __init__(
        self,
        cache_dir: HostPath,
        workspace_root: HostPath,
        *,
        handler: Optional[InboundCallHandler] = None,
        max_frame_bytes: int = MAX_FRAME_BYTES,
        connect_timeout_sec: float = 0.8,
    ) -> None:
        self._cache_dir = cache_dir
        self._workspace_root = workspace_root
        self._handler = handler
        self._max_frame_bytes = require_pure_int(max_frame_bytes, "max_frame_bytes", min_val=1, max_val=None)
        self._connect_timeout_sec = max(
            0.05, require_non_none(validate_non_negative_sec(connect_timeout_sec, label="connect_timeout_sec"))
        )
        self._lock = threading.RLock()
        self._closed = False
        self._close_token = CancellationToken()
        self._channel: Optional[MultiplexedChannel] = None
        self._last_boot_id: Optional[str] = None
        self._generation = 0

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._channel is not None and not self._channel.is_closed

    @property
    def channel_generation(self) -> int:
        with self._lock:
            return self._generation

    def call(
        self,
        payload: JsonObject,
        *,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
        cancel_token: Optional[CancellationToken] = None,
        timeout_ms: Optional[int] = None,
        on_reconnect_wait: Optional[Callable[[Optional[CancellationToken]], bool]] = None,
    ) -> RemoteCallOutcome:
        if timeout_ms is not None:
            require_pure_int(timeout_ms, "timeout_ms", min_val=None, max_val=None)
        if self._closed:
            return RemoteCallOutcome(
                was_accepted=False,
                error_code=ErrorCode.TASK_CANCELLED,
                error_message="PersistentRpcSession is closed.",
            )
        eff_tok, unreg = CancellationToken.combine(self._close_token, cancel_token)
        try:
            outcome, _reached = self.call_with_reachability(
                payload,
                on_progress=on_progress,
                cancel_token=eff_tok,
                timeout_ms=timeout_ms,
                on_reconnect_wait=on_reconnect_wait,
            )
        finally:
            unreg()
        if not outcome.was_accepted and self._closed and (cancel_token is None or not cancel_token.is_cancelled):
            return RemoteCallOutcome(
                was_accepted=False,
                error_code=ErrorCode.TASK_CANCELLED,
                error_message="PersistentRpcSession closed before call acceptance.",
            )
        return outcome

    def call_with_reachability(
        self,
        payload: JsonObject,
        *,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
        cancel_token: Optional[CancellationToken] = None,
        timeout_ms: Optional[int] = None,
        on_reconnect_wait: Optional[Callable[[Optional[CancellationToken]], bool]] = None,
    ) -> tuple[RemoteCallOutcome, bool]:
        if timeout_ms is not None:
            require_pure_int(timeout_ms, "timeout_ms", min_val=None, max_val=None)
        if cancel_token is not None and cancel_token.is_cancelled:
            c_code = ErrorCode.TASK_PREEMPTED if cancel_token.is_preempted else ErrorCode.TASK_CANCELLED
            return (
                RemoteCallOutcome(
                    was_accepted=False,
                    error_code=c_code,
                    error_message=cancel_token.reason or "RPC call cancelled before start.",
                ),
                False,
            )
        if timeout_ms is not None and timeout_ms <= 0:
            return (
                RemoteCallOutcome(
                    was_accepted=False,
                    error_code=ErrorCode.TASK_TIMEOUT,
                    error_message=f"RPC call timed out immediately (timeout_ms={timeout_ms}).",
                ),
                False,
            )
        guard = DeadlineGuard.from_timeout_ms(timeout_ms, cancel_token)
        reached_any = False
        attempt = 0
        while True:
            try:
                rem_ms = guard.remaining_ms(timeout_ms, expired_message=f"RPC call timed out after {timeout_ms}ms.")
            except YscbError as exc:
                return (
                    RemoteCallOutcome(was_accepted=False, error_code=ErrorCode.TASK_TIMEOUT, error_message=exc.detail.message),
                    reached_any,
                )
            ch = self._ensure_channel()
            if ch is None:
                if attempt < 2 and self._can_retry_missing(guard, on_reconnect_wait):
                    attempt += 1
                    continue
                return (
                    RemoteCallOutcome(
                        was_accepted=False,
                        transport_lost=True,
                        error_code=ErrorCode.DAEMON_UNAVAILABLE,
                        error_message="No online daemon endpoint available.",
                    ),
                    reached_any,
                )
            reached_any = True
            outcome = ch.call(
                payload,
                on_progress=on_progress,
                cancel_token=cancel_token,
                timeout_ms=rem_ms,
                cancel_grace_ms=500,
            )
            if outcome.transport_lost:
                self._discard_channel(ch, force_close=True)
            if (
                not outcome.was_accepted
                and (outcome.transport_lost or outcome.rejected_before_accept)
                and self._should_retry_unaccepted(ch, outcome, attempt, guard, on_reconnect_wait)
            ):
                attempt += 1
                continue
            return (outcome, True)

    def _can_retry_missing(
        self,
        guard: DeadlineGuard,
        on_reconnect_wait: Optional[Callable[[Optional[CancellationToken]], bool]],
    ) -> bool:
        with self._lock:
            if self._closed:
                return False
            prev_boot = self._last_boot_id
        return _wait_before_rpc_retry(
            self._cache_dir,
            self._workspace_root,
            guard,
            on_reconnect_wait,
            previous_boot_id=prev_boot,
        )

    def close(self) -> None:
        with self._lock:
            self._closed = True
            ch = self._channel
            self._channel = None
        self._close_token.cancel(reason="PersistentRpcSession closed.")
        if ch is not None:
            ch.close()

    def _ensure_channel(self) -> Optional[MultiplexedChannel]:
        with self._lock:
            if self._closed:
                return None
            if self._channel is not None and self._channel.is_usable:
                return self._channel
            self._channel = None
        info = read_daemon_endpoint_file(self._cache_dir, self._workspace_root)
        if info is None:
            return None
        new_ch = connect_and_handshake(
            info,
            handler=self._handler,
            connect_timeout_sec=self._connect_timeout_sec,
            max_frame_bytes=self._max_frame_bytes,
        )
        if new_ch is None:
            return None
        existing: Optional[MultiplexedChannel] = None
        with self._lock:
            if not self._closed and (self._channel is None or not self._channel.is_usable):
                self._channel = new_ch
                self._last_boot_id = info.boot_id
                self._generation += 1
                return new_ch
            if not self._closed:
                existing = self._channel
        new_ch.close()
        return existing

    def _should_retry_unaccepted(
        self,
        ch: MultiplexedChannel,
        outcome: RemoteCallOutcome,
        attempt: int,
        guard: DeadlineGuard,
        on_reconnect_wait: Optional[Callable[[Optional[CancellationToken]], bool]],
    ) -> bool:
        aborted = outcome.error_code in (
            ErrorCode.TASK_CANCELLED,
            ErrorCode.TASK_PREEMPTED,
            ErrorCode.TASK_TIMEOUT,
            ErrorCode.PAYLOAD_TOO_LARGE,
        ) or (guard.cancel_token is not None and guard.cancel_token.is_cancelled)
        if self._closed or aborted:
            return False
        if not outcome.transport_lost:
            self._discard_channel(ch, force_close=False)
        if attempt >= 2:
            return False
        with self._lock:
            prev_boot = self._last_boot_id
        return _wait_before_rpc_retry(
            self._cache_dir,
            self._workspace_root,
            guard,
            on_reconnect_wait,
            previous_boot_id=prev_boot,
        )

    def _discard_channel(self, target: MultiplexedChannel, *, force_close: bool) -> None:
        was_current = False
        with self._lock:
            if self._channel is target:
                self._channel = None
                was_current = True
        if force_close and (was_current or target.is_closed or target.is_usable):
            target.close()
        else:
            target.close_when_idle()


def _wait_before_rpc_retry(
    cache_dir: HostPath,
    workspace_root: HostPath,
    guard: DeadlineGuard,
    on_reconnect_wait: Optional[Callable[[Optional[CancellationToken]], bool]],
    *,
    previous_boot_id: Optional[str],
) -> bool:
    cancel_token = guard.cancel_token
    if cancel_token is not None and cancel_token.is_cancelled:
        return False
    if guard.deadline is not None and time.monotonic() >= guard.deadline:
        return False
    if on_reconnect_wait is not None and on_reconnect_wait(cancel_token):
        return True
    if on_reconnect_wait is None:
        max_w = 8.0 if guard.deadline is None else max(0.05, min(8.0, guard.deadline - time.monotonic()))
        if (
            wait_for_handoff_daemon_endpoint(
                cache_dir,
                workspace_root,
                cancel_token,
                max_wait_sec=max_w,
                previous_boot_id=previous_boot_id,
            )
            is not None
        ):
            return True
    if read_daemon_endpoint_file(cache_dir, workspace_root) is not None:
        time.sleep(0.03)
        return True
    return False


def call_ephemeral_daemon_rpc(
    endpoint_dirs: tuple[HostPath, HostPath],
    payload: JsonObject,
    *,
    on_progress: Optional[Callable[[JsonObject], None]] = None,
    cancel_token: Optional[CancellationToken] = None,
    timeout_ms: Optional[int] = None,
    on_reconnect_wait: Optional[Callable[[Optional[CancellationToken]], bool]] = None,
) -> Optional[RemoteCallOutcome]:
    """Single-call RPC helper sharing pre-accept reconnect semantics with PersistentRpcSession."""
    cache_dir, workspace_root = endpoint_dirs
    session = PersistentRpcSession(cache_dir, workspace_root, connect_timeout_sec=2.5)
    try:
        outcome, reached = session.call_with_reachability(
            payload,
            on_progress=on_progress,
            cancel_token=cancel_token,
            timeout_ms=timeout_ms,
            on_reconnect_wait=on_reconnect_wait,
        )
    finally:
        session.close()
    terminal_pre = outcome.error_code in (
        ErrorCode.TASK_TIMEOUT,
        ErrorCode.TASK_CANCELLED,
        ErrorCode.TASK_PREEMPTED,
        ErrorCode.PAYLOAD_TOO_LARGE,
    )
    return outcome if (reached or terminal_pre) else None


def _dispatch_cancel_thunks(thunks: Sequence[Callable[[], None]], *, from_io_thread: bool = True) -> None:
    if not thunks:
        return
    packed = tuple(thunks)
    if from_io_thread:
        try:
            threading.Thread(
                target=CancellationToken.run_callbacks,
                args=(packed,),
                name="yscb-rpc-cancel",
                daemon=True,
            ).start()
            return
        except RuntimeError:
            pass
    CancellationToken.run_callbacks(packed)


def _encode_control_ack_bytes(req_id: str, resp: JsonObject, max_frame_bytes: int) -> Optional[bytes]:
    meta_out: JsonObject = {"req_id": req_id}
    try:
        frame = RpcFrame(kind=FrameKind.CONTROL_ACK, stream_id=0, payload=resp, meta=meta_out)
        return _encode_raw_frame(frame, max_frame_bytes=max_frame_bytes)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        fallback: JsonObject = {"ok": False, "error": safe_exception_summary(exc)}
        try:
            return _encode_raw_frame(
                RpcFrame(kind=FrameKind.CONTROL_ACK, stream_id=0, payload=fallback, meta=meta_out),
                max_frame_bytes=max_frame_bytes,
            )
        except (TypeError, ValueError, OverflowError):
            return None


def query_daemon_control(
    cache_dir: HostPath,
    workspace_root: HostPath,
    kind: FrameKind,
    payload: Optional[JsonObject] = None,
    *,
    timeout_ms: int = 15000,
) -> Optional[JsonObject]:
    """Single-shot control frame request/ack helper against a live workspace daemon."""
    safe_ms = require_pure_int(timeout_ms, "timeout_ms", min_val=1, max_val=None)
    if kind not in _INBOUND_CONTROL_KINDS and kind != FrameKind.PING:
        return None
    ep = read_daemon_endpoint_file(cache_dir, workspace_root)
    if ep is None:
        return None
    conn_sec = min(1.0, ms_to_safe_sec(safe_ms, min_sec=0.05))
    ch = connect_and_handshake(ep, connect_timeout_sec=conn_sec)
    if ch is None:
        return None
    try:
        return ch.send_control(kind, payload or {}, timeout_ms=safe_ms)
    finally:
        ch.close()


class RpcServerListener:
    """Loopback TCP listener separating stop_accepting() from channel draining and cleanup."""

    def __init__(
        self,
        workspace_root: HostPath,
        handler: InboundCallHandler,
        *,
        boot_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        max_frame_bytes: int = MAX_FRAME_BYTES,
    ) -> None:
        self._workspace_root = workspace_root
        self._handler = handler
        self._boot_id = boot_id or uuid.uuid4().hex
        self._auth_token = auth_token or uuid.uuid4().hex
        self._max_frame_bytes = require_pure_int(max_frame_bytes, "max_frame_bytes", min_val=1, max_val=None)
        self._server_sock: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._stop_accept = False
        self._admitted_cond = threading.Condition()
        self._admitted_handshakes = 0
        self._closed_all = False
        self._stop_lock = threading.Lock()
        self._handshaking_socks: set[socket.socket] = set()
        self._handshake_sem = threading.BoundedSemaphore(_MAX_CONCURRENT_HANDSHAKES)
        self._handshake_threads: list[threading.Thread] = []
        self._channels: set[MultiplexedChannel] = set()
        self._endpoint: Optional[RpcEndpointInfo] = None

    @property
    def endpoint(self) -> Optional[RpcEndpointInfo]:
        with self._admitted_cond:
            return self._endpoint

    def start(self, *, pid: Optional[int] = None) -> RpcEndpointInfo:
        with self._stop_lock:
            with self._admitted_cond:
                if self._server_sock is not None:
                    raise RuntimeError("RpcServerListener is already running.")
                self._closed_all = False
                self._stop_accept = False
            eff_pid = os.getpid() if pid is None else require_pure_int(pid, "pid", min_val=1, max_val=None)
            srv = bind_loopback_ephemeral(backlog=64)
            srv.settimeout(0.05)
            port = int(srv.getsockname()[1])
            info = RpcEndpointInfo(
                pid=eff_pid,
                host="127.0.0.1",
                port=port,
                boot_id=self._boot_id,
                auth_token=self._auth_token,
                workspace_root=self._workspace_root,
            )
            accept_t = threading.Thread(target=self._accept_loop, name="yscb-rpc-accept", daemon=True)
            with self._admitted_cond:
                self._server_sock = srv
                self._endpoint = info
                self._accept_thread = accept_t
            try:
                accept_t.start()
            except BaseException:
                with self._admitted_cond:
                    self._server_sock = None
                    self._endpoint = None
                    self._accept_thread = None
                _shutdown_and_close_sock(srv)
                raise
            return info

    def stop_accepting(self) -> None:
        with self._stop_lock:
            with self._admitted_cond:
                self._stop_accept = True
                srv = self._server_sock
                self._server_sock = None
                t = self._accept_thread
                self._accept_thread = None
            if srv is not None:
                _shutdown_and_close_sock(srv)
            if t is not None and t.is_alive() and t is not threading.current_thread():
                t.join(timeout=2.0)
            with self._admitted_cond:
                hs_socks = list(self._handshaking_socks)
                hs_threads = [
                    ht for ht in self._handshake_threads if ht.is_alive() and ht is not threading.current_thread()
                ]
                self._handshake_threads.clear()
            for hs_sock in hs_socks:
                _shutdown_and_close_sock(hs_sock)
            for ht in hs_threads:
                ht.join(timeout=1.0)

    def flush_inbound_controls(self, timeout_sec: float = 1.0) -> None:
        safe_sec = max(0.05, require_non_none(validate_non_negative_sec(timeout_sec, label="timeout_sec")))
        deadline = time.monotonic() + safe_sec
        with self._admitted_cond:
            while self._admitted_handshakes > 0 and time.monotonic() < deadline:
                self._admitted_cond.wait(timeout=0.01)
            channels = list(self._channels)
        for ch in channels:
            ch.wait_inbound_controls_flushed(timeout_sec=max(0.05, deadline - time.monotonic()))

    def close_all(self) -> None:
        self.stop_accepting()
        self.flush_inbound_controls(timeout_sec=1.0)
        with self._admitted_cond:
            self._closed_all = True
            channels = list(self._channels)
            self._channels.clear()
        for ch in channels:
            ch.close()

    def _accept_loop(self) -> None:
        while True:
            with self._admitted_cond:
                srv = None if self._stop_accept else self._server_sock
            if srv is None:
                break
            try:
                conn, _addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if not self._handshake_sem.acquire(timeout=0.5):
                _shutdown_and_close_sock(conn)
                continue
            with self._admitted_cond:
                if self._stop_accept:
                    self._handshake_sem.release()
                    _shutdown_and_close_sock(conn)
                    break
                self._handshaking_socks.add(conn)
                self._handshake_threads = [ht for ht in self._handshake_threads if ht.is_alive()]
                hs_t = threading.Thread(
                    target=self._handshake_client,
                    args=(conn,),
                    name="yscb-rpc-handshake",
                    daemon=True,
                )
                self._handshake_threads.append(hs_t)
            try:
                hs_t.start()
            except BaseException as exc:
                self._handshake_sem.release()
                with self._admitted_cond:
                    self._handshaking_socks.discard(conn)
                _shutdown_and_close_sock(conn)
                if not isinstance(exc, Exception):
                    raise

    def _remove_closed_channel(self, ch: MultiplexedChannel) -> None:
        with self._admitted_cond:
            self._channels.discard(ch)

    def _try_admit_handshake_sock(self, conn: socket.socket) -> bool:
        with self._admitted_cond:
            self._handshaking_socks.discard(conn)
            if self._stop_accept or self._closed_all:
                return False
            self._admitted_handshakes += 1
            return True

    def _finish_admitted_handshake(self, ch: Optional[MultiplexedChannel]) -> None:
        reject = False
        with self._admitted_cond:
            if ch is not None:
                if self._closed_all or ch.is_closed:
                    reject = True
                else:
                    self._channels.add(ch)
            self._admitted_handshakes = max(0, self._admitted_handshakes - 1)
            self._admitted_cond.notify_all()
        if reject and ch is not None:
            ch.close()

    def _handshake_client(self, conn: socket.socket) -> None:
        try:
            with self._admitted_cond:
                info = None if self._stop_accept else self._endpoint
            if info is None:
                _shutdown_and_close_sock(conn)
                return
            if not _verify_inbound_hello(
                conn, info.auth_token, info.boot_id, info.workspace_root, self._max_frame_bytes
            ):
                return
            if not self._try_admit_handshake_sock(conn):
                _send_reject_ack_quietly(conn, self._max_frame_bytes)
                _shutdown_and_close_sock(conn)
                return
            ch: Optional[MultiplexedChannel] = None
            try:
                ch = _open_accepted_peer_channel(
                    conn,
                    info.boot_id,
                    self._handler,
                    self._max_frame_bytes,
                    on_closed=self._remove_closed_channel,
                )
            finally:
                self._finish_admitted_handshake(ch)
        finally:
            with self._admitted_cond:
                self._handshaking_socks.discard(conn)
            self._handshake_sem.release()
