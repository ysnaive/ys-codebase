"""HotWorkerPool, OneShotVenvHost, and PoolHostCallbacks with unified step execution and single-probe isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import os
import socket
import sys
import threading
import time
from types import MappingProxyType
from typing import Callable, Final, Mapping, Optional, Sequence
import uuid

from core.execution.lifecycle import LifoResourceStack
from core.execution.rpc import FrameKind, InboundCallHandler, MultiplexedChannel, RemoteCallOutcome, accept_worker_handshake, bind_loopback_ephemeral
from core.execution.runtime.contracts import (
    WORKER_AUTH_ENV_KEY,
    EnvLeaseAcquireFn,
    EnvTouchUsedFn,
    ExecutionPriority,
    ModuleDescriptor,
    WorkerProcessSnapshot,
)
from core.execution.runtime.services import (
    HOST_DIALECT_ENV_KEY,
    resolve_active_profiler,
    resolve_explicit_workspace_host_dialect,
)
from core.execution.runtime.coordinator import PriorityHandle, wait_on_event_with_cancel
from core.execution.runtime.wire import (
    WorkerBootstrapConfig, WorkerCommandEnvelope, WorkerCommandKind, WorkerControlAction, WorkerElevateControl,
    WorkerModInitControl, WorkerStopAck, WorkerStopControl, WorkerUnloadReply, WorkerWarmupReply,
)
from core.filesystem.fs import (
    has_symlink_raw_path,
    hash_nofollow_regular_sha256,
    is_symlink_or_reparse,
    walk_nonsymlink_dir_tree,
)
from core.foundation.codec import DataclassCodec
from core.foundation.errors import ErrorCode, ErrorDetail, TaskCancelledException, YscbError, safe_exception_summary
from core.foundation.observability import MAX_SAFE_WAIT_SEC, MAX_TIMEOUT_MS, CancellationToken, DeadlineGuard, ms_to_safe_sec
from core.foundation.primitives import PYTHON_LAUNCHER_HIJACK_ENV_KEYS, decrement_ref_count, HostPath, JsonObject, ModuleId, invoke_observer_safely, require_non_none
from core.foundation.proc import ManagedProcessTree
from core.foundation.profiler import decode_profiler_snapshot
from core.metadata.contributes import BoundLocaleDialect, lookup_cold_workspace_dialect_state


class RetiringGroupBusyError(Exception):
    """Internal runtime signal indicating a Tier 1 group must finish retiring before running under a resource lock."""


@dataclass(frozen=True, slots=True)
class WorkerCallSpec:
    """Encapsulated specification for calling a Tier 1 .venv worker pool or Cold Turn host."""

    group_descriptors: Sequence[ModuleDescriptor]
    command: WorkerCommandEnvelope
    on_progress: Optional[Callable[[JsonObject], None]] = None
    cancel_token: Optional[CancellationToken] = None
    priority_handle: Optional[PriorityHandle] = None
    timeout_ms: Optional[int] = None
    grace_ms: int = 400
    inherit_tty: bool = False
    turn_id: str = ""
    call_tree_id: str = ""
    forbid_retiring_wait: bool = False
    bypass_reload_gate: bool = False


class _HandlePhase(Enum):
    HEALTHY = "healthy"
    TAINTED = "tainted"
    RELOAD_DRAINING = "reload_draining"
    RELOAD_CLOSING = "reload_closing"
    CLOSING = "closing"


class _ActiveWorkerHandle(InboundCallHandler):
    """Represents one running Tier 1 .venv subprocess with monotonic phase tracking and callback routing."""

    def __init__(
        self, proc_tree: ManagedProcessTree, group_key: str, delegate: InboundCallHandler,
        on_module_init: Optional[Callable[[_ActiveWorkerHandle, ModuleId], None]] = None,
        *, venv_python: Optional[HostPath] = None, env_lease_release: Optional[Callable[[], None]] = None,
    ) -> None:
        self.proc_tree, self.group_key, self._delegate, self._on_module_init = proc_tree, group_key, delegate, on_module_init
        self.venv_python: Optional[HostPath] = venv_python
        self._env_lease_release: Optional[Callable[[], None]] = env_lease_release
        self._channel: Optional[MultiplexedChannel] = None
        self.boot_fingerprint: str = ""
        self.bound_modules: frozenset[ModuleId] = frozenset()
        self.warmed_modules: set[ModuleId] = set()
        self._lifo_claimed_mods: set[ModuleId] = set()
        self._warmed_lifo_order: list[ModuleId] = []
        self._shutdown_diags: tuple[ErrorDetail, ...] = ()
        self._diags_consumed = False
        self._cond = threading.Condition()
        self._stop_lock = threading.Lock()
        self._stopped_event = threading.Event()
        self._healthy_in_flight = 0
        self._active_turns: dict[str, int] = {}
        self._active_call_trees: dict[str, int] = {}
        self._phase = _HandlePhase.HEALTHY

    @property
    def channel(self) -> MultiplexedChannel:
        return require_non_none(self._channel)

    def bind_channel(self, channel: MultiplexedChannel) -> None:
        self._channel = channel

    def on_call(
        self, stream_id: int, payload: JsonObject, ack_accepted: Callable[[], bool],
        emit_progress: Callable[[JsonObject], None], peer_cancel_token: CancellationToken,
    ) -> tuple[bool, JsonObject]:
        return self._delegate.on_call(stream_id, payload, ack_accepted, emit_progress, peer_cancel_token)

    def on_control(self, kind: FrameKind, payload: JsonObject) -> JsonObject:
        if self._on_module_init is not None and kind == FrameKind.CONTROL_REQUEST and payload.get("action") == WorkerControlAction.MODULE_INITIALIZED.value:
            try:
                ctrl = DataclassCodec.decode(WorkerModInitControl, payload)
            except YscbError as exc:
                return {"ok": False, "error": exc.detail.code.value, "message": exc.detail.message}
            self._on_module_init(self, ctrl.module_id)
            return {"ok": True}
        return self._delegate.on_control(kind, payload)

    def record_or_claim_lifo_module(self, mod_id: ModuleId, *, is_committed: bool) -> bool:
        with self._cond:
            if mod_id in self._lifo_claimed_mods:
                return False
            self._lifo_claimed_mods.add(mod_id)
            if not is_committed:
                self._warmed_lifo_order.append(mod_id)
                return False
            return True

    def drain_warmed_lifo_order(self) -> tuple[ModuleId, ...]:
        with self._cond:
            out = tuple(self._warmed_lifo_order)
            self._warmed_lifo_order.clear()
            return out

    @property
    def stopped_event(self) -> threading.Event:
        return self._stopped_event

    @property
    def is_stopped(self) -> bool:
        return self._stopped_event.is_set() or not self.proc_tree.peek_alive()

    def _enter_closing_phase_locked(self) -> None:
        self._phase = _HandlePhase.RELOAD_CLOSING if self._phase in (_HandlePhase.RELOAD_DRAINING, _HandlePhase.RELOAD_CLOSING) else _HandlePhase.CLOSING
    @property
    def is_closing_for_reload(self) -> bool:
        with self._cond:
            return self._phase in (_HandlePhase.RELOAD_DRAINING, _HandlePhase.RELOAD_CLOSING)

    def mark_closing_for_reload(self) -> None:
        with self._cond:
            if self._phase in (_HandlePhase.HEALTHY, _HandlePhase.TAINTED):
                self._phase = _HandlePhase.RELOAD_DRAINING

    @property
    def is_alive(self) -> bool:
        with self._cond:
            if self._phase != _HandlePhase.HEALTHY:
                return False
        ch = self._channel
        return ch is not None and not self._stopped_event.is_set() and not ch.is_closed and self.proc_tree.peek_alive()

    def can_accept_reentrant_turn(self, turn_id: str, call_tree_id: str, *, allow_drain_bypass: bool = False) -> bool:
        ch = self._channel
        if ch is None or self._stopped_event.is_set() or ch.is_closed or not self.proc_tree.peek_alive():
            return False
        with self._cond:
            if self._phase in (_HandlePhase.RELOAD_CLOSING, _HandlePhase.CLOSING) or self._stopped_event.is_set():
                return False
            if allow_drain_bypass:
                return True
            return (bool(turn_id) and self._active_turns.get(turn_id, 0) > 0) or (bool(call_tree_id) and self._active_call_trees.get(call_tree_id, 0) > 0)

    def _dec_turn_locked(self, turn_id: str, call_tree_id: str) -> None:
        decrement_ref_count(self._active_turns, turn_id)
        decrement_ref_count(self._active_call_trees, call_tree_id)

    def try_enter_call(
        self, turn_id: str, call_tree_id: str, *, allow_reentrant: bool = False, allow_drain_bypass: bool = False,
    ) -> bool:
        ch = self._channel
        if ch is None or self._stopped_event.is_set() or ch.is_closed or not self.proc_tree.peek_alive():
            return False
        with self._cond:
            if self._stopped_event.is_set() or self._phase in (_HandlePhase.RELOAD_CLOSING, _HandlePhase.CLOSING):
                return False
            if self._phase in (_HandlePhase.TAINTED, _HandlePhase.RELOAD_DRAINING):
                if not allow_reentrant:
                    return False
                has_turn = (bool(turn_id) and self._active_turns.get(turn_id, 0) > 0) or (bool(call_tree_id) and self._active_call_trees.get(call_tree_id, 0) > 0)
                if not has_turn and not allow_drain_bypass:
                    return False
            self._healthy_in_flight += 1
            if turn_id:
                self._active_turns[turn_id] = self._active_turns.get(turn_id, 0) + 1
            if call_tree_id:
                self._active_call_trees[call_tree_id] = self._active_call_trees.get(call_tree_id, 0) + 1
            return True

    def mark_tainted_call(self, turn_id: str, call_tree_id: str) -> None:
        with self._cond:
            if self._phase == _HandlePhase.HEALTHY:
                self._phase = _HandlePhase.TAINTED
            self._healthy_in_flight = max(0, self._healthy_in_flight - 1)
            self._dec_turn_locked(turn_id, call_tree_id)
            self._cond.notify_all()

    def exit_healthy_call(self, turn_id: str, call_tree_id: str) -> None:
        with self._cond:
            self._healthy_in_flight = max(0, self._healthy_in_flight - 1)
            self._dec_turn_locked(turn_id, call_tree_id)
            self._cond.notify_all()

    def terminate_when_healthy_drained(self, *, max_wait_sec: float) -> None:
        kill_now = False
        with self._cond:
            if self._phase == _HandlePhase.HEALTHY:
                self._phase = _HandlePhase.TAINTED
            if self._healthy_in_flight <= 0:
                self._enter_closing_phase_locked()
                kill_now = True
        if kill_now:
            self.kill_immediately()
            return
        try:
            threading.Thread(
                target=self._drain_then_finish, args=(max(0.1, max_wait_sec), 0.0, True),
                name=f"yscb-drain-{self.group_key}", daemon=True,
            ).start()
        except BaseException:
            self.kill_immediately()
            raise

    def shutdown_when_healthy_drained(
        self, *, grace_sec: float, max_wait_sec: float, on_drained: Callable[[tuple[ErrorDetail, ...]], None],
    ) -> tuple[bool, tuple[ErrorDetail, ...]]:
        stop_now = False
        with self._cond:
            if self._phase in (_HandlePhase.HEALTHY, _HandlePhase.TAINTED):
                self._phase = _HandlePhase.RELOAD_DRAINING
            if self._healthy_in_flight <= 0:
                self._enter_closing_phase_locked()
                stop_now = True
        if stop_now:
            return (True, self.shutdown(grace_sec=grace_sec))
        try:
            threading.Thread(
                target=self._drain_then_finish, args=(max(0.1, max_wait_sec), grace_sec, False, on_drained),
                name=f"yscb-reload-drain-{self.group_key}", daemon=True,
            ).start()
        except BaseException as exc:
            diags = self.shutdown(grace_sec=grace_sec)
            if isinstance(exc, Exception):
                return (True, diags)
            raise
        return (False, ())

    def _drain_then_finish(
        self, max_wait_sec: float, grace_sec: float, force_kill: bool,
        on_drained: Optional[Callable[[tuple[ErrorDetail, ...]], None]] = None,
    ) -> None:
        deadline = time.monotonic() + max_wait_sec
        with self._cond:
            while self._healthy_in_flight > 0 and time.monotonic() < deadline:
                self._cond.wait(timeout=min(0.05, max(0.005, deadline - time.monotonic())))
            self._enter_closing_phase_locked()
        diags = () if force_kill else self.shutdown(grace_sec=grace_sec)
        if force_kill:
            self.kill_immediately()
        if on_drained is not None:
            on_drained(diags)

    def consume_shutdown_diagnostics(self) -> tuple[ErrorDetail, ...]:
        with self._cond:
            if self._diags_consumed or not self._shutdown_diags:
                return ()
            self._diags_consumed = True
            return self._shutdown_diags
    def _release_env_lease_locked(self) -> None:
        rel = self._env_lease_release
        if rel is None:
            return
        self._env_lease_release = None
        invoke_observer_safely(rel)

    def shutdown(self, *, grace_sec: float = 1.0) -> tuple[ErrorDetail, ...]:
        with self._cond:
            self._enter_closing_phase_locked()
        with self._stop_lock:
            if self._stopped_event.is_set():
                return self.consume_shutdown_diagnostics()
            try:
                self.proc_tree.snapshot_descendants()
                if self._channel is not None and not self._channel.is_closed:
                    drain_ms = max(50, int(grace_sec * 1000))
                    rep = self._channel.send_control(
                        FrameKind.CONTROL_STOP, DataclassCodec.encode_object(WorkerStopControl(grace_ms=drain_ms)),
                        timeout_ms=min(MAX_TIMEOUT_MS, drain_ms + 1000),
                    )
                    fb_mod = sorted(str(m) for m in self.bound_modules)[0] if self.bound_modules else None
                    raw_diags = _decode_stop_diagnostics(rep)
                    self._shutdown_diags = tuple(d.with_fallback_task(fb_mod) if fb_mod is not None else d for d in raw_diags)
                    self._channel.close()
                self.proc_tree.terminate_tree(grace_sec=grace_sec)
            finally:
                self._release_env_lease_locked()
                self._stopped_event.set()
        return self.consume_shutdown_diagnostics()

    def kill_immediately(self) -> None:
        with self._cond:
            self._enter_closing_phase_locked()
        with self._stop_lock:
            if self._stopped_event.is_set():
                return
            try:
                self.proc_tree.snapshot_descendants()
                if self._channel is not None:
                    self._channel.close()
                self.proc_tree.kill_tree_now()
            finally:
                self._release_env_lease_locked()
                self._stopped_event.set()


def _unload_module_on_handle(handle: _ActiveWorkerHandle, mod_id: ModuleId, *, timeout_sec: float) -> tuple[ErrorDetail, ...]:
    if handle.is_stopped or handle.channel.is_closed:
        return ()
    out = handle.channel.call(
        DataclassCodec.encode_envelope(WorkerCommandEnvelope(action=WorkerCommandKind.UNLOAD_MODULES, modules=(mod_id,))),
        timeout_ms=max(200, int(timeout_sec * 1000)),
    )
    if out.transport_lost:
        return ()
    if out.error_code is not None:
        return (ErrorDetail(ErrorCode.TEARDOWN_ERROR, out.error_message or out.error_code.value, source_task=str(mod_id)),)
    if out.result_payload is None:
        return ()
    try:
        return DataclassCodec.decode_envelope(WorkerUnloadReply, out.result_payload).teardown_diagnostics
    except (YscbError, KeyError, TypeError, ValueError):
        return ()


def _decode_stop_diagnostics(reply: Optional[JsonObject]) -> tuple[ErrorDetail, ...]:
    if not isinstance(reply, dict):
        return ()
    try:
        return DataclassCodec.decode(WorkerStopAck, reply).teardown_diagnostics
    except (YscbError, KeyError, TypeError, ValueError):
        return ()


def _fingerprint_tier1_descriptor_files(desc: ModuleDescriptor) -> str:
    h = hashlib.sha256()
    if desc.venv_python is not None:
        try:
            vp_st = os.lstat(desc.venv_python.path)
            h.update(f"vp:{vp_st.st_mtime_ns}:{vp_st.st_size}\n".encode("utf-8"))
        except OSError:
            pass
    root_s = str(desc.module_dir)
    if has_symlink_raw_path(root_s) or is_symlink_or_reparse(root_s):
        return h.hexdigest()
    file_hashes: list[tuple[str, str]] = []
    for _cur_dir, entries in walk_nonsymlink_dir_tree(root_s, ignored_dir_prefixes=(".", "__pycache__")):
        for ent in entries:
            if ent.name.startswith(".") or ent.name in ("__pycache__", ".git", ".venv") or ent.is_symlink() or is_symlink_or_reparse(ent.path):
                continue
            if not (ent.name == "manifest.json" or ent.name.endswith(".py")):
                continue
            try:
                if not ent.is_file(follow_symlinks=False):
                    continue
                digest = hash_nofollow_regular_sha256(ent.path)
                if not digest:
                    continue
                rel_name = os.path.relpath(ent.path, root_s).replace("\\", "/")
                file_hashes.append((rel_name, digest))
            except (OSError, ValueError, YscbError):
                continue
    for rel_name, digest in sorted(file_hashes):
        h.update(f"f:{rel_name}:{digest}\n".encode("utf-8"))
    return h.hexdigest()


def _compute_group_desc_fingerprint(descs: Sequence[ModuleDescriptor]) -> str:
    items = sorted(
        [
            str(d.module_id), d.module_dir.comparison_key, d.entry_file, d.venv_group or "",
            d.venv_python.comparison_key if d.venv_python is not None else "",
            d.eager_warmup, [DataclassCodec.encode_object(t) for t in d.declared_tasks],
            _fingerprint_tier1_descriptor_files(d),
        ]
        for d in descs
    )
    return DataclassCodec.canonical_hash(items)


def _accept_authenticated_worker_channel(
    listen_sock: socket.socket, proc_tree: ManagedProcessTree, handle: _ActiveWorkerHandle,
    group_key: str, auth_token: str, boot_id: str, workspace_root: HostPath, guard: DeadlineGuard,
) -> MultiplexedChannel:
    listen_sock.settimeout(0.05)
    boot_deadline = time.monotonic() + 8.0
    while time.monotonic() < boot_deadline:
        if guard.cancel_token is not None:
            guard.cancel_token.raise_if_cancelled()
        if guard.deadline is not None and time.monotonic() >= guard.deadline:
            raise YscbError(ErrorCode.TASK_TIMEOUT, f"Timed out waiting for Tier 1 worker {group_key!r} startup.")
        rc = proc_tree.poll()
        if rc is not None:
            raise YscbError(ErrorCode.WORKER_CRASHED, f"Tier 1 worker {group_key!r} exited during startup with code {rc}.")
        try:
            conn, _addr = listen_sock.accept()
        except socket.timeout:
            continue
        rem_cap = min(boot_deadline - time.monotonic(), (guard.deadline - time.monotonic()) if guard.deadline is not None else 0.5)
        conn.settimeout(max(0.05, min(0.5, rem_cap)))
        ch = accept_worker_handshake(
            conn, expected_auth_token=auth_token, boot_id=boot_id, handler=handle, expected_workspace_root=workspace_root,
        )
        if ch is not None:
            return ch
    raise YscbError(ErrorCode.WORKER_CRASHED, f"Tier 1 worker {group_key!r} timed out connecting.")


@dataclass(frozen=True, slots=True)
class _WorkerSpawnOpts:
    group_key: str
    is_hot: bool = True
    inherit_tty: bool = False
    on_module_init: Optional[Callable[[_ActiveWorkerHandle, ModuleId], None]] = None
    host_dir: Optional[HostPath] = None
    bound_dialect: Optional[BoundLocaleDialect] = None
    env_lease_acquire: Optional[EnvLeaseAcquireFn] = None
    daemon_boot_id: str = ""
    flight_log_config: Optional[JsonObject] = None


_STRIPPED_WORKER_PYTHON_ENV_UPPER: frozenset[str] = frozenset(
    k.upper() for k in (*PYTHON_LAUNCHER_HIJACK_ENV_KEYS, "PYTHONHOME", "VIRTUAL_ENV", "PYTHONUSERBASE")
)
_FALSY_ENV_TOKENS: frozenset[str] = frozenset({"", "0", "false", "no", "off"})


_WORKER_ANTIGRAVITY_ENV_KEYS: frozenset[str] = frozenset({
    "ANTIGRAVITY_AGENT",
    "ANTIGRAVITY_CONVERSATION_ID",
    "ANTIGRAVITY_TRAJECTORY_ID",
    "ANTIGRAVITY_SESSION",
    "AGY_AGENT",
    "AGY_SESSION",
})
_WORKER_CLAUDE_ENV_KEYS: frozenset[str] = frozenset({
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_SSE_PORT",
})
_WORKER_CODEX_ENV_KEYS: frozenset[str] = frozenset({
    "CODEX_SANDBOX",
    "CODEX_THREAD_ID",
    "CODEX_CI",
})
_WORKER_GEMINI_ENV_KEYS: frozenset[str] = frozenset({"GEMINI_CLI"})
_WORKER_CURSOR_ENV_KEYS: frozenset[str] = frozenset({"CURSOR_AGENT"})
_WORKER_SUPPRESS_DIALECT_MODES: frozenset[str] = frozenset({"ci", "ci_pipeline", "non_tty"})
_WORKER_EXPLICIT_MODE_RANK: Final[Mapping[str, int]] = MappingProxyType({
    "agent": 3,
    "ci": 3,
    "ci_pipeline": 3,
    "non_tty": 2,
    "human": 1,
})


def _resolve_worker_explicit_caller_mode(env_map: dict[str, str]) -> str:
    exact_raw = env_map.get("YSCB_CALLER_MODE")
    if isinstance(exact_raw, str):
        exact_tok = exact_raw.strip().lower()
        if exact_tok in _WORKER_EXPLICIT_MODE_RANK:
            return exact_tok
    best_tok = ""
    best_rank = 0
    for k, v in env_map.items():
        if k.upper() == "YSCB_CALLER_MODE":
            cand = v.strip().lower()
            rank = _WORKER_EXPLICIT_MODE_RANK.get(cand, 0)
            if rank > best_rank:
                best_rank = rank
                best_tok = cand
    return best_tok


def _infer_env_host_dialect(env_map: dict[str, str]) -> Optional[str]:
    if _resolve_worker_explicit_caller_mode(env_map) in _WORKER_SUPPRESS_DIALECT_MODES:
        return None
    upper_keys = {
        k.upper(): v.strip()
        for k, v in env_map.items()
        if v.strip().lower() not in _FALSY_ENV_TOKENS
    }
    if any(k in upper_keys for k in _WORKER_ANTIGRAVITY_ENV_KEYS):
        return "nouns-antigravity"
    if any(k in upper_keys for k in _WORKER_CLAUDE_ENV_KEYS):
        return "nouns-claude"
    if any(k in upper_keys for k in _WORKER_CODEX_ENV_KEYS):
        return "nouns-codex"
    if any(k in upper_keys for k in _WORKER_GEMINI_ENV_KEYS):
        return "nouns-gemini"
    if any(k in upper_keys for k in _WORKER_CURSOR_ENV_KEYS):
        return "nouns-cursor"
    return None


def _strip_env_key_ci(env_map: dict[str, str], target_key: str) -> None:
    target_up = target_key.upper()
    for existing_k in [k for k in env_map if k.upper() == target_up]:
        env_map.pop(existing_k, None)


def _build_worker_subproc_env(auth_token: str, workspace_root: HostPath, opts: _WorkerSpawnOpts) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() not in _STRIPPED_WORKER_PYTHON_ENV_UPPER}
    env["PYTHONPATH"] = str(HostPath(__file__).path.parents[3])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if sys.flags.optimize > 0:
        env["PYTHONOPTIMIZE"] = str(sys.flags.optimize)
    env[WORKER_AUTH_ENV_KEY] = auth_token
    _strip_env_key_ci(env, HOST_DIALECT_ENV_KEY)
    if opts.is_hot:
        return env
    bd = opts.bound_dialect
    if bd is not None:
        if not bd.is_daemon_host and bd.dialect is not None:
            env[HOST_DIALECT_ENV_KEY] = bd.dialect
        if bd.is_daemon_host or not bd.inherit_host_env_locale or bd.raw_env_locale_override is not None:
            _strip_env_key_ci(env, "YSCB_LOCALE")
            if bd.raw_env_locale_override:
                env["YSCB_LOCALE"] = bd.raw_env_locale_override
        return env
    explicit_dial = resolve_explicit_workspace_host_dialect(workspace_root)
    if explicit_dial is not None:
        env[HOST_DIALECT_ENV_KEY] = explicit_dial
        return env
    cold_state = lookup_cold_workspace_dialect_state(workspace_root)
    if cold_state.has_active_kernel:
        if cold_state.dialect is not None:
            env[HOST_DIALECT_ENV_KEY] = cold_state.dialect
        return env
    inferred_dialect = _infer_env_host_dialect(env)
    if inferred_dialect is not None:
        env[HOST_DIALECT_ENV_KEY] = inferred_dialect
    return env


def _spawn_connected_worker(
    *, workspace_root: HostPath, descriptors: Sequence[ModuleDescriptor],
    master_callback_handler: InboundCallHandler, opts: _WorkerSpawnOpts, guard: DeadlineGuard,
) -> _ActiveWorkerHandle:
    group_key = opts.group_key
    py_paths = {require_non_none(d.venv_python) for d in descriptors}
    if len(py_paths) != 1:
        raise YscbError(ErrorCode.MODULE_DEGRADED, f"Conflicting venv_python interpreters in Tier 1 group '{group_key}'.")
    venv_python = next(iter(py_paths))
    env_lease_release: Optional[Callable[[], None]] = None
    listen_sock: Optional[socket.socket] = None
    proc_tree: Optional[ManagedProcessTree] = None
    channel: Optional[MultiplexedChannel] = None
    handle: Optional[_ActiveWorkerHandle] = None
    try:
        with resolve_active_profiler().scope_relative("WorkerSpawn", group_key):
            if opts.env_lease_acquire is not None:
                env_lease_release = opts.env_lease_acquire(venv_python)
            listen_sock = bind_loopback_ephemeral(backlog=16)
            port = int(listen_sock.getsockname()[1])
            boot_id, auth_token = uuid.uuid4().hex, uuid.uuid4().hex
            mods = tuple(
                ModuleDescriptor(module_id=d.module_id, module_dir=d.module_dir, entry_file=d.entry_file, eager_warmup=d.eager_warmup, declared_tasks=d.declared_tasks)
                for d in descriptors
            )
            cfg_arg = json.dumps(
                DataclassCodec.encode_object(
                    WorkerBootstrapConfig(
                        "127.0.0.1",
                        port,
                        boot_id,
                        workspace_root,
                        mods,
                        opts.is_hot,
                        opts.host_dir,
                        opts.daemon_boot_id,
                        opts.flight_log_config,
                    )
                ),
                separators=(",", ":"),
                ensure_ascii=False,
            )
            argv = [str(venv_python), "-c", "from core.execution.runtime.worker_entry import worker_main; raise SystemExit(worker_main())", cfg_arg]
            try:
                proc_tree = ManagedProcessTree(
                    argv,
                    cwd=workspace_root,
                    env=_build_worker_subproc_env(auth_token, workspace_root, opts),
                    inherit_tty=opts.inherit_tty,
                )
            except OSError as exc:
                raise YscbError(
                    ErrorCode.WORKER_CRASHED,
                    f"Failed to spawn Tier 1 worker '{group_key}' ({venv_python}): {safe_exception_summary(exc)}",
                ) from exc
            handle = _ActiveWorkerHandle(
                proc_tree,
                group_key,
                master_callback_handler,
                opts.on_module_init,
                venv_python=venv_python,
                env_lease_release=env_lease_release,
            )
            env_lease_release = None
            channel = _accept_authenticated_worker_channel(listen_sock, proc_tree, handle, group_key, auth_token, boot_id, workspace_root, guard)
            handle.bind_channel(channel)
            handle.boot_fingerprint = _compute_group_desc_fingerprint(descriptors)
            handle.bound_modules = frozenset(d.module_id for d in descriptors)
            return handle
    except BaseException:
        if handle is not None:
            handle.kill_immediately()
        else:
            if channel is not None:
                channel.close()
            if proc_tree is not None:
                proc_tree.kill_tree_now()
            if env_lease_release is not None:
                invoke_observer_safely(env_lease_release)
        raise
    finally:
        if listen_sock is not None:
            try:
                listen_sock.close()
            except OSError:
                pass


def _execute_rpc_call_with_watchdog(
    handle: _ActiveWorkerHandle, wire_payload: JsonObject, spec: WorkerCallSpec,
    effective_timeout_ms: Optional[int], on_uncoop_abort: Callable[[], None],
) -> RemoteCallOutcome:
    ph, srid = spec.priority_handle, spec.command.step_run_id
    if ph is not None and srid and spec.command.priority != ExecutionPriority.FOREGROUND:
        def _push_elevate(_p: ExecutionPriority) -> None:
            if not handle.channel.is_closed:
                handle.channel.post_control(FrameKind.CONTROL_REQUEST, DataclassCodec.encode_object(WorkerElevateControl(action=WorkerControlAction.ELEVATE_STEP, step_run_id=srid)))
        unreg_prio = ph.register_listener(_push_elevate)
    else:
        unreg_prio = lambda: None
    try:
        outcome = handle.channel.call(
            wire_payload, on_progress=spec.on_progress, cancel_token=spec.cancel_token,
            timeout_ms=effective_timeout_ms, cancel_grace_ms=max(100, spec.grace_ms),
        )
        uncoop = spec.cancel_token is not None and spec.cancel_token.is_cancelled and outcome.result_payload is None
        if outcome.error_code == ErrorCode.TASK_TIMEOUT or outcome.transport_lost or uncoop:
            on_uncoop_abort()
        return outcome
    finally:
        unreg_prio()


def _abort_warmup_if_caller_stopped(handle: _ActiveWorkerHandle, out: RemoteCallOutcome, guard: DeadlineGuard) -> None:
    if guard.cancel_token is not None and guard.cancel_token.is_cancelled:
        handle.kill_immediately()
        guard.cancel_token.raise_if_cancelled()
    if out.error_code in (ErrorCode.TASK_CANCELLED, ErrorCode.TASK_PREEMPTED):
        handle.kill_immediately()
        raise YscbError(out.error_code, out.error_message or "Tier 1 warmup cancelled.")
    if guard.deadline is not None and (time.monotonic() >= guard.deadline or out.error_code == ErrorCode.TASK_TIMEOUT):
        handle.kill_immediately()
        raise YscbError(ErrorCode.TASK_TIMEOUT, "Timed out during Tier 1 worker auto-warmup.")


@dataclass(slots=True)
class _GroupBootFlight:
    target_fp: str
    cancel_token: CancellationToken = field(default_factory=CancellationToken)
    done_event: threading.Event = field(default_factory=threading.Event)
    error: Optional[BaseException] = None
    thread: Optional[threading.Thread] = None


def _filter_non_degraded_eager(
    descriptors: Sequence[ModuleDescriptor],
    is_degraded: Optional[Callable[[ModuleId], bool]],
    is_quiesced: Optional[Callable[[ModuleId], bool]],
) -> tuple[ModuleId, ...]:
    return tuple(
        d.module_id for d in descriptors
        if d.eager_warmup and (is_degraded is None or not is_degraded(d.module_id)) and (is_quiesced is None or not is_quiesced(d.module_id))
    )


@dataclass(frozen=True, slots=True)
class PoolHostCallbacks:
    """Host lifecycle callbacks keeping HotWorkerPool decoupled from RuntimeDispatcher."""

    on_warmup_reply: Optional[Callable[[Sequence[ModuleId], WorkerWarmupReply], None]] = None
    on_module_crashed: Optional[Callable[[ModuleId, ErrorDetail], None]] = None
    is_module_degraded: Optional[Callable[[ModuleId], bool]] = None
    is_module_quiesced: Optional[Callable[[ModuleId], bool]] = None
    is_group_reloading: Optional[Callable[[Sequence[ModuleDescriptor]], bool]] = None
    resolve_group_descriptors: Optional[Callable[[str, Sequence[ModuleDescriptor]], Sequence[ModuleDescriptor]]] = None
    on_teardown_diagnostics: Optional[Callable[[Sequence[ErrorDetail]], None]] = None
    env_lease_acquire: Optional[EnvLeaseAcquireFn] = None
    env_touch_used: Optional[EnvTouchUsedFn] = None


def _invoke_worker_handle_with_taint(
    handle: _ActiveWorkerHandle, wire_payload: JsonObject, spec: WorkerCallSpec,
    timeout_ms: Optional[int], on_detach: Callable[[], None], *, drain_wait_sec: float,
) -> tuple[RemoteCallOutcome, Optional[threading.Event]]:
    tainted_lock, tainted_by_call = threading.Lock(), False

    def _on_abort() -> None:
        nonlocal tainted_by_call
        with tainted_lock:
            if tainted_by_call:
                return
            tainted_by_call = True
        on_detach()
        handle.mark_tainted_call(spec.turn_id, spec.call_tree_id)
        handle.terminate_when_healthy_drained(max_wait_sec=drain_wait_sec)

    try:
        prof = resolve_active_profiler()
        step_lbl = str(spec.command.task_id) if spec.command.task_id is not None else spec.command.action.value
        with prof.scope_relative("WorkerStep", step_lbl):
            out = _execute_rpc_call_with_watchdog(handle, wire_payload, spec, timeout_ms, _on_abort)
            if (
                spec.command.action == WorkerCommandKind.RUN_STEP
                and out.error_code is None
                and not out.transport_lost
                and out.result_payload is not None
            ):
                child_tree = decode_profiler_snapshot(out.result_payload.get("profiler_tree"))
                if child_tree is not None:
                    prof.merge_subtree(child_tree)
        with tainted_lock:
            was_tainted = tainted_by_call
        return (out, (None if handle.is_stopped else handle.stopped_event) if was_tainted else None)
    finally:
        with tainted_lock:
            already = tainted_by_call
        if not already:
            handle.exit_healthy_call(spec.turn_id, spec.call_tree_id)


_GROUP_WARMUP_TIMEOUT_MS: int = 15000
_WARMUP_CANCEL_GRACE_MS: int = 200


def tier1_group_key_for(desc: ModuleDescriptor) -> str:
    return desc.venv_group if desc.venv_group is not None else f"mod_{desc.module_id}"
class HotWorkerPool:
    """Manages warm Tier 1 .venv subprocesses grouped by venv_group with single-probe crash isolation."""

    def __init__(
        self, workspace_root: HostPath, master_callback_handler: InboundCallHandler, *,
        host_callbacks: PoolHostCallbacks = PoolHostCallbacks(), lifo_stack: Optional[LifoResourceStack] = None,
        host_dir: Optional[HostPath] = None, daemon_boot_id: str = "", flight_log_config: Optional[JsonObject] = None,
    ) -> None:
        self._workspace_root, self._callback_handler, self._lifo_stack = workspace_root, master_callback_handler, lifo_stack
        self._host_dir = host_dir
        self._daemon_boot_id = daemon_boot_id
        self._flight_log_config = flight_log_config
        self._on_warmup_reply, self._on_module_crashed = host_callbacks.on_warmup_reply, host_callbacks.on_module_crashed
        self._is_module_degraded, self._is_module_quiesced = host_callbacks.is_module_degraded, host_callbacks.is_module_quiesced
        self._is_group_reloading, self._resolve_group_descs = host_callbacks.is_group_reloading, host_callbacks.resolve_group_descriptors
        self._on_teardown_diags = host_callbacks.on_teardown_diagnostics
        self._env_lease_acquire, self._env_touch_used = host_callbacks.env_lease_acquire, host_callbacks.env_touch_used
        self._state_cond = threading.Condition()
        self._gate_seq, self._closed, self._shutdown_grace_sec = 0, False, 1.0
        self._group_epochs: dict[str, int] = {}
        self._boot_flights: dict[str, _GroupBootFlight] = {}
        self._workers: dict[str, _ActiveWorkerHandle] = {}
        self._retiring_workers: dict[str, list[_ActiveWorkerHandle]] = {}
        self._deferred_retire_warmups: dict[str, tuple[tuple[ModuleDescriptor, ...], Optional[frozenset[ModuleId]]]] = {}

    def update_observability(
        self,
        *,
        daemon_boot_id: str = "",
        flight_log_config: Optional[JsonObject] = None,
    ) -> None:
        with self._state_cond:
            if daemon_boot_id:
                self._daemon_boot_id = daemon_boot_id
            if flight_log_config is not None:
                self._flight_log_config = flight_log_config

    def _register_spawned_worker_lifo(self, group_key: str, spawned: _ActiveWorkerHandle) -> None:
        if self._lifo_stack is None:
            return
        tag = f"tier1_pool.{group_key}"
        self._lifo_stack.pop_tagged_by_prefixes(frozenset({tag}))
        self._lifo_stack.push_diagnostic_closeable(tag, lambda: self._lifo_shutdown_handle(group_key, spawned))
        for mid in spawned.drain_warmed_lifo_order():
            self._push_module_lifo_closer(group_key, spawned, mid)

    def _push_module_lifo_closer(self, group_key: str, handle: _ActiveWorkerHandle, mod_id: ModuleId) -> None:
        if self._lifo_stack is not None:
            self._lifo_stack.push_diagnostic_closeable(
                f"tier1_pool.{group_key}.{mod_id}",
                lambda m=mod_id, h=handle: _unload_module_on_handle(h, m, timeout_sec=self._shutdown_grace_sec),
            )

    def _claim_and_push_hot_lifo(self, group_key: str, handle: _ActiveWorkerHandle, mod_id: ModuleId) -> None:
        with self._state_cond:
            if handle.record_or_claim_lifo_module(mod_id, is_committed=(self._workers.get(group_key) is handle)):
                self._push_module_lifo_closer(group_key, handle, mod_id)

    def warmup_group(self, group_descriptors: Sequence[ModuleDescriptor], only_modules: Optional[frozenset[ModuleId]] = None) -> None:
        if not group_descriptors or self._closed or (self._is_module_quiesced is not None and any(self._is_module_quiesced(d.module_id) for d in group_descriptors)):
            return
        targets = tuple(
            d.module_id for d in group_descriptors
            if d.eager_warmup and (only_modules is None or d.module_id in only_modules)
            and (self._is_module_quiesced is None or not self._is_module_quiesced(d.module_id))
        )
        if not targets:
            return
        gkey = tier1_group_key_for(group_descriptors[0])
        with self._state_cond:
            if any(not h.is_stopped for h in self._live_retiring_locked(gkey)):
                self._deferred_retire_warmups[gkey] = (tuple(group_descriptors), only_modules)
                return
            self._deferred_retire_warmups.pop(gkey, None)
        guard = DeadlineGuard.from_timeout_ms(_GROUP_WARMUP_TIMEOUT_MS, None)
        spec = WorkerCallSpec(group_descriptors=group_descriptors, command=WorkerCommandEnvelope(action=WorkerCommandKind.WARMUP, modules=targets), timeout_ms=_GROUP_WARMUP_TIMEOUT_MS)
        try:
            handle = self._ensure_worker(gkey, spec, guard=guard)
            pending = tuple(m for m in targets if m not in handle.warmed_modules and (self._is_module_degraded is None or not self._is_module_degraded(m)))
            if pending and not self._try_warmup_explicit_modules(handle, pending, guard):
                self._detach_worker_only(gkey, handle)
                handle.terminate_when_healthy_drained(max_wait_sec=5.0)
                self._ensure_worker(gkey, spec, guard=guard)
        except YscbError as exc:
            if exc.detail.code == ErrorCode.DAEMON_UNAVAILABLE or (self._is_module_quiesced is not None and any(self._is_module_quiesced(d.module_id) for d in group_descriptors)):
                return
            if self._on_module_crashed is not None:
                for mid in targets:
                    if self._is_module_degraded is None or not self._is_module_degraded(mid):
                        self._on_module_crashed(mid, ErrorDetail(ErrorCode.MODULE_DEGRADED, f"Tier 1 warmup failed for '{mid}': {exc.detail.message}"))

    def stop_groups_for_modules(
        self, modules: frozenset[ModuleId], all_descriptors: Sequence[ModuleDescriptor],
        *, grace_ms: int = 1000, drain_in_flight: bool = False,
    ) -> tuple[ErrorDetail, ...]:
        if isinstance(grace_ms, bool) or not isinstance(grace_ms, int) or grace_ms < 0:
            raise ValueError(f"grace_ms must be a non-negative int (not bool), got {grace_ms!r}")
        grace_s = ms_to_safe_sec(grace_ms, min_sec=0.1)
        target_groups = {tier1_group_key_for(d) for d in all_descriptors if d.module_id in modules and d.venv_python is not None}
        to_stop: list[tuple[str, _ActiveWorkerHandle]] = []
        existing_retiring: list[tuple[str, _ActiveWorkerHandle]] = []
        with self._state_cond:
            for g, wh in list(self._workers.items()):
                if bool(wh.bound_modules & modules):
                    target_groups.add(g)
            for g, rlist in list(self._retiring_workers.items()):
                if any(bool(rh.bound_modules & modules) for rh in rlist):
                    target_groups.add(g)
            boot_cancels: list[_GroupBootFlight] = []
            for g in target_groups:
                self._group_epochs[g] = self._group_epochs.get(g, 0) + 1
                fl = self._boot_flights.get(g)
                if fl is not None:
                    boot_cancels.append(fl)
                existing_retiring.extend((g, rh) for rh in self._live_retiring_locked(g))
                h = self._workers.pop(g, None)
                if h is not None:
                    self._retiring_workers.setdefault(g, []).append(h)
                    to_stop.append((g, h))
            if self._lifo_stack is not None and target_groups:
                self._lifo_stack.pop_tagged_by_prefixes(frozenset(f"tier1_pool.{g}" for g in target_groups))
            self._state_cond.notify_all()
        for fl in boot_cancels:
            fl.cancel_token.cancel(reason="Tier 1 group stopped.")
        join_sec = min(MAX_SAFE_WAIT_SEC, max(0.5, grace_s + 0.3))
        for fl in boot_cancels:
            if fl.thread is not None and fl.thread is not threading.current_thread() and fl.thread.is_alive():
                fl.thread.join(timeout=join_sec)
        if drain_in_flight:
            return self._retire_detached_handles(to_stop, grace_s)
        diags: list[ErrorDetail] = []
        with self._state_cond:
            for g in target_groups:
                self._deferred_retire_warmups.pop(g, None)
        for g, h in (*to_stop, *existing_retiring):
            diags.extend(h.shutdown(grace_sec=grace_s))
            with self._state_cond:
                self._live_retiring_locked(g)
        return tuple(diags)

    def _retire_detached_handles(self, pairs: Sequence[tuple[str, _ActiveWorkerHandle]], grace_sec: float) -> tuple[ErrorDetail, ...]:
        diags: list[ErrorDetail] = []
        for g, h in pairs:
            stopped_now, sub_diags = h.shutdown_when_healthy_drained(
                grace_sec=grace_sec, max_wait_sec=min(MAX_SAFE_WAIT_SEC, max(30.0, grace_sec)),
                on_drained=lambda d, gk=g: self._on_retiring_handle_drained(gk, d),
            )
            if stopped_now:
                diags.extend(sub_diags)
                with self._state_cond:
                    self._live_retiring_locked(g)
        return tuple(diags)
    def _any_quiesced(self, descriptors: Sequence[ModuleDescriptor]) -> bool:
        return self._is_module_quiesced is not None and any(self._is_module_quiesced(d.module_id) for d in descriptors)

    def _on_retiring_handle_drained(self, group_key: str, diags: tuple[ErrorDetail, ...]) -> None:
        if diags and self._on_teardown_diags is not None:
            self._on_teardown_diags(diags)
        deferred: Optional[tuple[tuple[ModuleDescriptor, ...], Optional[frozenset[ModuleId]]]] = None
        with self._state_cond:
            if not self._closed and not any(not h.is_stopped for h in self._live_retiring_locked(group_key)):
                deferred = self._deferred_retire_warmups.pop(group_key, None)
        if deferred is not None:
            fresh = self._resolve_group_descs(group_key, deferred[0]) if self._resolve_group_descs is not None else deferred[0]
            self.warmup_group(fresh, only_modules=deferred[1])

    def _lifo_shutdown_handle(self, group_key: str, handle: _ActiveWorkerHandle) -> tuple[ErrorDetail, ...]:
        with self._state_cond:
            if self._workers.get(group_key) is handle:
                self._workers.pop(group_key, None)
            grace_s = self._shutdown_grace_sec
        return handle.shutdown(grace_sec=grace_s)

    def active_worker_snapshots(self) -> tuple[WorkerProcessSnapshot, ...]:
        with self._state_cond:
            entries = tuple(self._workers.items())
        return tuple(
            WorkerProcessSnapshot(group=k, pid=h.proc_tree.pid, alive=(h.proc_tree.poll() is None and h.is_alive))
            for k, h in entries
        )

    def _find_reentrant_retiring_worker(
        self, group_key: str, turn_id: str, call_tree_id: str, *, allow_drain_bypass: bool = False,
    ) -> Optional[_ActiveWorkerHandle]:
        if not turn_id and not call_tree_id and not allow_drain_bypass:
            return None
        with self._state_cond:
            candidates = list(self._live_retiring_locked(group_key))
            cur_w = self._workers.get(group_key)
            if cur_w is not None and not cur_w.is_alive:
                candidates.append(cur_w)
        return next((c for c in candidates if c.can_accept_reentrant_turn(turn_id, call_tree_id, allow_drain_bypass=allow_drain_bypass)), None)

    def _commit_spawned_worker_or_abort(
        self,
        group_key: str,
        descriptors: Sequence[ModuleDescriptor],
        spawned: _ActiveWorkerHandle,
        start_epoch: int,
        flight: _GroupBootFlight,
    ) -> Optional[_ActiveWorkerHandle]:
        quiesced_now = self._any_quiesced(descriptors)
        with self._state_cond:
            closed_or_q = self._closed or quiesced_now
            if (
                not closed_or_q
                and not flight.cancel_token.is_cancelled
                and self._boot_flights.get(group_key) is flight
                and self._group_epochs.get(group_key, 0) == start_epoch
                and group_key not in self._workers
            ):
                self._workers[group_key] = spawned
                self._register_spawned_worker_lifo(group_key, spawned)
                return spawned
        spawned.kill_immediately()
        if closed_or_q:
            raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "Tier 1 worker group shut down or quiesced during startup.")
        return None

    def _try_spawn_under_group_lock(
        self, group_key: str, descriptors: Sequence[ModuleDescriptor], allow_during_reload: bool, guard: DeadlineGuard,
    ) -> Optional[_ActiveWorkerHandle]:
        has_eager, target_fp = (any(d.eager_warmup for d in descriptors) and not allow_during_reload), _compute_group_desc_fingerprint(descriptors)
        mismatched_live: Optional[_ActiveWorkerHandle] = None
        with self._state_cond:
            cur_h = self._workers.get(group_key)
            if cur_h is not None and cur_h.is_alive and cur_h.boot_fingerprint != target_fp:
                self._group_epochs[group_key] = self._group_epochs.get(group_key, 0) + 1
                self._workers.pop(group_key, None)
                cur_h.mark_closing_for_reload()
                self._retiring_workers.setdefault(group_key, []).append(cur_h)
                if self._lifo_stack is not None:
                    self._lifo_stack.pop_tagged_by_prefixes(frozenset({f"tier1_pool.{group_key}"}))
                self._state_cond.notify_all()
                mismatched_live = cur_h
        if mismatched_live is not None:
            mis_diags = self._retire_detached_handles(((group_key, mismatched_live),), 1.0)
            if mis_diags and self._on_teardown_diags is not None:
                self._on_teardown_diags(mis_diags)
        quiesced_now = self._any_quiesced(descriptors)
        reloading_now = self._is_group_reloading is not None and self._is_group_reloading(descriptors)
        ready_handle: Optional[_ActiveWorkerHandle] = None
        stale_handle: Optional[_ActiveWorkerHandle] = None
        superseded_flight: Optional[_GroupBootFlight] = None
        flight: Optional[_GroupBootFlight] = None
        retry_later, start_epoch, start_flight = False, 0, False
        with self._state_cond:
            if self._closed or quiesced_now:
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "Tier 1 worker group is shut down or quiesced.")
            if reloading_now and not allow_during_reload:
                retry_later = True
            else:
                existing = self._workers.get(group_key)
                if existing is not None and existing.is_alive and existing.boot_fingerprint == target_fp:
                    ready_handle = existing
                elif any(not h.is_stopped and (has_eager or h.is_closing_for_reload) for h in self._live_retiring_locked(group_key)):
                    retry_later = True
                else:
                    stale_handle = self._workers.pop(group_key, None) if existing is not None else None
                    flight = self._boot_flights.get(group_key)
                    if flight is not None and not flight.done_event.is_set() and flight.target_fp != target_fp:
                        superseded_flight, flight = flight, None
                    if stale_handle is not None or superseded_flight is not None:
                        self._group_epochs[group_key] = self._group_epochs.get(group_key, 0) + 1
                    start_epoch = self._group_epochs.get(group_key, 0)
                    if flight is None or flight.done_event.is_set():
                        flight = _GroupBootFlight(target_fp=target_fp)
                        self._boot_flights[group_key] = flight
                        start_flight = True
        if superseded_flight is not None:
            superseded_flight.cancel_token.cancel(reason="Tier 1 group fingerprint superseded.")
        if stale_handle is not None:
            stale_handle.kill_immediately()
        if ready_handle is not None or retry_later:
            return ready_handle
        flight = require_non_none(flight)
        if start_flight:
            th = threading.Thread(
                target=self._run_group_boot_flight, args=(group_key, tuple(descriptors), start_epoch, flight),
                name=f"yscb-t1-boot-{group_key}", daemon=True,
            )
            flight.thread = th
            try:
                th.start()
            except BaseException as exc:
                flight.thread = None
                flight.error = exc if isinstance(exc, Exception) else RuntimeError(safe_exception_summary(exc))
                flight.done_event.set()
                with self._state_cond:
                    if self._boot_flights.get(group_key) is flight:
                        self._boot_flights.pop(group_key, None)
                    self._state_cond.notify_all()
                raise
        rem_sec = (guard.deadline - time.monotonic()) if guard.deadline is not None else None
        if rem_sec is not None and rem_sec <= 0:
            raise YscbError(ErrorCode.TASK_TIMEOUT, "Timed out waiting for Tier 1 worker startup.")
        with resolve_active_profiler().scope_relative("WorkerSpawn", group_key):
            wait_on_event_with_cancel(flight.done_event, guard.cancel_token or CancellationToken(), rem_sec)
        if flight.error is not None:
            if isinstance(flight.error, (YscbError, TaskCancelledException)):
                raise flight.error
            raise YscbError(ErrorCode.WORKER_CRASHED, f"Tier 1 worker boot failed: {safe_exception_summary(flight.error)}")
        with self._state_cond:
            ready = self._workers.get(group_key)
            return ready if (ready is not None and ready.is_alive and ready.boot_fingerprint == target_fp) else None
    def _run_group_boot_flight(self, group_key: str, descriptors: tuple[ModuleDescriptor, ...], start_epoch: int, flight: _GroupBootFlight) -> None:
        pool_guard = DeadlineGuard.from_timeout_ms(_GROUP_WARMUP_TIMEOUT_MS, flight.cancel_token)
        try:
            spawned = self._spawn_and_warmup_worker(group_key, descriptors, pool_guard)
            _ = self._commit_spawned_worker_or_abort(group_key, descriptors, spawned, start_epoch, flight)
        except BaseException as exc:
            if not flight.cancel_token.is_cancelled:
                flight.error = exc
        finally:
            with self._state_cond:
                if self._boot_flights.get(group_key) is flight:
                    self._boot_flights.pop(group_key, None)
                self._state_cond.notify_all()
            flight.done_event.set()

    def _notify_env_touch_used(self, handle: _ActiveWorkerHandle) -> None:
        touch_fn = self._env_touch_used
        if touch_fn is not None and handle.venv_python is not None:
            vp = handle.venv_python
            invoke_observer_safely(lambda: touch_fn(vp))

    def _spawn_and_warmup_worker(self, group_key: str, descriptors: Sequence[ModuleDescriptor], guard: DeadlineGuard) -> _ActiveWorkerHandle:
        spawned = _spawn_connected_worker(
            workspace_root=self._workspace_root, descriptors=descriptors, master_callback_handler=self._callback_handler,
            opts=_WorkerSpawnOpts(
                group_key,
                on_module_init=lambda h, mid: self._claim_and_push_hot_lifo(group_key, h, mid),
                host_dir=self._host_dir,
                env_lease_acquire=self._env_lease_acquire,
                daemon_boot_id=self._daemon_boot_id,
                flight_log_config=self._flight_log_config,
            ),
            guard=guard,
        )
        try:
            eager_mods = _filter_non_degraded_eager(descriptors, self._is_module_degraded, self._is_module_quiesced)
            if self._try_warmup_explicit_modules(spawned, eager_mods, guard):
                return spawned
        except BaseException:
            spawned.kill_immediately()
            raise
        spawned.kill_immediately()
        return self._isolate_crashed_eager_and_respawn(group_key, descriptors, guard)

    def _try_warmup_explicit_modules(self, handle: _ActiveWorkerHandle, eager_mods: tuple[ModuleId, ...], guard: DeadlineGuard) -> bool:
        if not eager_mods:
            return True
        rem_ms = guard.remaining_ms(10000, expired_message="Timed out before Tier 1 auto-warmup.")
        warm_cmd = WorkerCommandEnvelope(action=WorkerCommandKind.WARMUP, modules=eager_mods)
        out = handle.channel.call(DataclassCodec.encode_envelope(warm_cmd), cancel_token=guard.cancel_token, timeout_ms=rem_ms, cancel_grace_ms=_WARMUP_CANCEL_GRACE_MS)
        _abort_warmup_if_caller_stopped(handle, out, guard)
        if out.transport_lost or out.error_code is not None or out.result_payload is None:
            return False
        try:
            rep = DataclassCodec.decode_envelope(WorkerWarmupReply, out.result_payload)
        except YscbError:
            return False
        for mid in eager_mods:
            if str(mid) not in rep.degraded:
                handle.warmed_modules.add(mid)
        if self._on_warmup_reply is not None:
            self._on_warmup_reply(eager_mods, rep)
        return True

    def _probe_single_eager_module(self, probe_h: _ActiveWorkerHandle, mod_id: ModuleId, guard: DeadlineGuard) -> tuple[bool, bool]:
        w_cmd = WorkerCommandEnvelope(action=WorkerCommandKind.WARMUP, modules=(mod_id,))
        out = probe_h.channel.call(
            DataclassCodec.encode_envelope(w_cmd), cancel_token=guard.cancel_token,
            timeout_ms=guard.remaining_ms(5000, expired_message="Timed out during Tier 1 probe warmup."), cancel_grace_ms=_WARMUP_CANCEL_GRACE_MS,
        )
        _abort_warmup_if_caller_stopped(probe_h, out, guard)
        if out.transport_lost or out.error_code is not None or out.result_payload is None:
            if self._on_module_crashed is not None:
                self._on_module_crashed(mod_id, ErrorDetail(ErrorCode.MODULE_DEGRADED, f"Module '{mod_id}' crashed during Tier 1 warmup."))
            return (False, False)
        try:
            rep = DataclassCodec.decode_envelope(WorkerWarmupReply, out.result_payload)
        except YscbError as exc:
            if self._on_module_crashed is not None:
                self._on_module_crashed(mod_id, exc.detail)
            return (False, False)
        mod_healthy = str(mod_id) not in rep.degraded
        if mod_healthy:
            probe_h.warmed_modules.add(mod_id)
        if self._on_warmup_reply is not None:
            self._on_warmup_reply((mod_id,), rep)
        return (True, mod_healthy)

    def _isolate_crashed_eager_and_respawn(self, group_key: str, descriptors: Sequence[ModuleDescriptor], guard: DeadlineGuard) -> _ActiveWorkerHandle:
        probe_h: Optional[_ActiveWorkerHandle] = None
        healthy_mods: list[ModuleId] = []
        warmed_on_probe: set[ModuleId] = set()
        try:
            for mod_id in _filter_non_degraded_eager(descriptors, self._is_module_degraded, self._is_module_quiesced):
                if probe_h is None:
                    probe_h = _spawn_connected_worker(
                        workspace_root=self._workspace_root, descriptors=descriptors, master_callback_handler=self._callback_handler,
                        opts=_WorkerSpawnOpts(
                            group_key,
                            on_module_init=lambda h, mid: self._claim_and_push_hot_lifo(group_key, h, mid),
                            host_dir=self._host_dir,
                            env_lease_acquire=self._env_lease_acquire,
                            daemon_boot_id=self._daemon_boot_id,
                            flight_log_config=self._flight_log_config,
                        ),
                        guard=guard,
                    )
                alive, mod_ok = self._probe_single_eager_module(probe_h, mod_id, guard)
                if not alive:
                    probe_h.kill_immediately()
                    probe_h = None
                    warmed_on_probe.clear()
                elif mod_ok:
                    healthy_mods.append(mod_id)
                    warmed_on_probe.add(mod_id)
            if probe_h is not None:
                missing = tuple(m for m in healthy_mods if m not in warmed_on_probe)
                if not missing or self._try_warmup_explicit_modules(probe_h, missing, guard):
                    return probe_h
                probe_h.kill_immediately()
                probe_h = None
        except BaseException:
            if probe_h is not None:
                probe_h.kill_immediately()
            raise
        fresh = _spawn_connected_worker(
            workspace_root=self._workspace_root, descriptors=descriptors, master_callback_handler=self._callback_handler,
            opts=_WorkerSpawnOpts(
                group_key,
                on_module_init=lambda h, mid: self._claim_and_push_hot_lifo(group_key, h, mid),
                host_dir=self._host_dir,
                env_lease_acquire=self._env_lease_acquire,
                daemon_boot_id=self._daemon_boot_id,
                flight_log_config=self._flight_log_config,
            ),
            guard=guard,
        )
        try:
            eager_mods = _filter_non_degraded_eager(descriptors, self._is_module_degraded, self._is_module_quiesced)
            if not self._try_warmup_explicit_modules(fresh, eager_mods, guard):
                fresh.kill_immediately()
                raise YscbError(ErrorCode.WORKER_CRASHED, f"Respawned worker '{group_key}' failed auto-warmup.")
            return fresh
        except BaseException:
            fresh.kill_immediately()
            raise

    def _wait_if_group_reloading(self, group_key: str, descriptors: Sequence[ModuleDescriptor], guard: DeadlineGuard) -> None:
        while not self._closed:
            with self._state_cond:
                seen_seq = self._gate_seq
            if not (self._is_group_reloading is not None and self._is_group_reloading(descriptors)) or self._closed:
                return
            if guard.cancel_token is not None:
                guard.cancel_token.raise_if_cancelled()
            if guard.deadline is not None and time.monotonic() >= guard.deadline:
                raise YscbError(ErrorCode.TASK_TIMEOUT, f"Timed out waiting for group '{group_key}' reload.")
            with self._state_cond:
                if not self._closed and self._gate_seq == seen_seq:
                    self._state_cond.wait(timeout=0.02)
    def _ensure_worker(self, group_key: str, spec: WorkerCallSpec, *, guard: DeadlineGuard) -> _ActiveWorkerHandle:
        allow_during_reload = (spec.command.action == WorkerCommandKind.WARMUP) or spec.bypass_reload_gate
        while True:
            cur_descs = (
                self._resolve_group_descs(group_key, spec.group_descriptors)
                if (self._resolve_group_descs is not None and spec.command.action != WorkerCommandKind.WARMUP)
                else spec.group_descriptors
            )
            if cur_descs:
                group_key = tier1_group_key_for(cur_descs[0])
            if not allow_during_reload:
                self._wait_if_group_reloading(group_key, cur_descs, guard)
                cur_descs = (
                    self._resolve_group_descs(group_key, spec.group_descriptors)
                    if (self._resolve_group_descs is not None and spec.command.action != WorkerCommandKind.WARMUP)
                    else spec.group_descriptors
                )
                if cur_descs:
                    group_key = tier1_group_key_for(cur_descs[0])
            has_eager = any(d.eager_warmup for d in cur_descs) and not spec.bypass_reload_gate
            cur_fp, quiesced_now = _compute_group_desc_fingerprint(cur_descs), self._any_quiesced(cur_descs)
            with self._state_cond:
                if self._closed or quiesced_now:
                    raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "Tier 1 worker group is shut down or quiesced.")
                fast = self._workers.get(group_key)
                if fast is not None and fast.is_alive and fast.boot_fingerprint == cur_fp:
                    return fast
                need_wait = any(not h.is_stopped and (h.is_closing_for_reload or (has_eager and not spec.bypass_reload_gate)) for h in self._live_retiring_locked(group_key))
                if spec.forbid_retiring_wait and need_wait:
                    raise RetiringGroupBusyError(group_key)
            if need_wait:
                self._await_retiring_group_stopped(group_key, cancel_token=guard.cancel_token, timeout_ms=guard.remaining_ms(spec.timeout_ms))
            spawned = self._try_spawn_under_group_lock(group_key, cur_descs, allow_during_reload, guard)
            if spawned is not None:
                return spawned
            if spec.forbid_retiring_wait:
                raise RetiringGroupBusyError(group_key)
            if guard.cancel_token is not None:
                guard.cancel_token.raise_if_cancelled()
            _ = guard.remaining_ms(spec.timeout_ms, expired_message="Timed out waiting for Tier 1 worker group.")
            with self._state_cond:
                if not self._closed:
                    self._state_cond.wait(timeout=0.01)

    def _live_retiring_locked(self, group_key: str) -> list[_ActiveWorkerHandle]:
        cur = self._retiring_workers.get(group_key)
        if not cur:
            return []
        alive_ret = [h for h in cur if not h.is_stopped]
        if alive_ret:
            self._retiring_workers[group_key] = alive_ret
        else:
            self._retiring_workers.pop(group_key, None)
        return alive_ret

    def _await_retiring_group_stopped(self, group_key: str, *, cancel_token: Optional[CancellationToken], timeout_ms: Optional[int]) -> None:
        with self._state_cond:
            retiring = list(self._live_retiring_locked(group_key))
        if not retiring:
            return
        tok = cancel_token or CancellationToken()
        deadline = time.monotonic() + (ms_to_safe_sec(timeout_ms) if timeout_ms is not None else 62.0)
        for rh in retiring:
            wait_on_event_with_cancel(rh.stopped_event, tok, max(0.01, deadline - time.monotonic()))
        with self._state_cond:
            self._live_retiring_locked(group_key)

    def _detach_worker_only(self, group_key: str, handle: _ActiveWorkerHandle) -> None:
        with self._state_cond:
            if self._workers.get(group_key) is handle:
                self._workers.pop(group_key, None)
                if self._lifo_stack is not None:
                    self._lifo_stack.pop_tagged_by_prefixes(frozenset({f"tier1_pool.{group_key}"}))
            ret_list = self._live_retiring_locked(group_key)
            if not handle.is_stopped and handle not in ret_list:
                ret_list.append(handle)
                self._retiring_workers[group_key] = ret_list
            self._state_cond.notify_all()

    def notify_gate_changed(self) -> None:
        with self._state_cond:
            self._gate_seq += 1
            self._state_cond.notify_all()

    def bump_groups_epoch(self, modules: frozenset[ModuleId], all_descriptors: Sequence[ModuleDescriptor]) -> None:
        groups = {tier1_group_key_for(d) for d in all_descriptors if d.module_id in modules and d.venv_python is not None}
        if not groups:
            return
        flights_to_cancel: list[_GroupBootFlight] = []
        with self._state_cond:
            for g in groups:
                self._group_epochs[g] = self._group_epochs.get(g, 0) + 1
                fl = self._boot_flights.get(g)
                if fl is not None:
                    flights_to_cancel.append(fl)
            self._state_cond.notify_all()
        for fl in flights_to_cancel:
            fl.cancel_token.cancel(reason="Tier 1 group epoch bumped.")

    def call_worker_with_guard(self, spec: WorkerCallSpec) -> tuple[RemoteCallOutcome, Optional[threading.Event]]:
        try:
            gkey, guard, wire_payload = _prepare_worker_call(spec)
        except YscbError as exc:
            return (RemoteCallOutcome(was_accepted=False, error_code=exc.detail.code, error_message=exc.detail.message), None)
        transport_retries = 0
        for _guard_step in range(8):
            reentrant = self._find_reentrant_retiring_worker(gkey, spec.turn_id, spec.call_tree_id, allow_drain_bypass=spec.bypass_reload_gate)
            try:
                handle = reentrant if reentrant is not None else self._ensure_worker(gkey, spec, guard=guard)
                rem_ms = guard.remaining_ms(spec.timeout_ms, expired_message="Timed out before Tier 1 worker call.")
            except TaskCancelledException as exc:
                return (RemoteCallOutcome(was_accepted=False, error_code=exc.detail.code, error_message=exc.detail.message), None)
            except YscbError as exc:
                is_lost = self._closed or exc.detail.code in (ErrorCode.DAEMON_UNAVAILABLE, ErrorCode.WORKER_CRASHED)
                return (RemoteCallOutcome(was_accepted=False, transport_lost=is_lost, error_code=exc.detail.code, error_message=exc.detail.message), None)
            if not handle.try_enter_call(spec.turn_id, spec.call_tree_id, allow_reentrant=(reentrant is not None), allow_drain_bypass=spec.bypass_reload_gate):
                continue
            self._notify_env_touch_used(handle)
            outcome, release_guard = _invoke_worker_handle_with_taint(handle, wire_payload, spec, rem_ms, lambda h=handle: self._detach_worker_only(gkey, h), drain_wait_sec=3.0)
            if outcome.error_code == ErrorCode.TASK_TIMEOUT:
                return (outcome, release_guard)
            if outcome.transport_lost:
                if reentrant is not None or (spec.cancel_token is not None and spec.cancel_token.is_cancelled) or outcome.was_accepted or transport_retries >= 1:
                    return (outcome, release_guard)
                transport_retries += 1
                continue
            return (outcome, release_guard)
        return (RemoteCallOutcome(was_accepted=False, transport_lost=True, error_code=ErrorCode.WORKER_CRASHED), None)
    def prepare_lifo_shutdown(self, *, grace_ms: int = 1000) -> tuple[ErrorDetail, ...]:
        grace_s = ms_to_safe_sec(grace_ms, min_sec=0.1)
        retiring_handles: list[_ActiveWorkerHandle] = []
        active_boots: list[_GroupBootFlight] = []
        with self._state_cond:
            self._closed, self._shutdown_grace_sec = True, grace_s
            active_boots.extend(self._boot_flights.values())
            for retiring_list in self._retiring_workers.values():
                retiring_handles.extend(retiring_list)
            self._retiring_workers.clear()
            self._deferred_retire_warmups.clear()
            self._state_cond.notify_all()
        diags: list[ErrorDetail] = []
        try:
            for fl in active_boots:
                fl.cancel_token.cancel(reason="HotWorkerPool shutting down.")
            join_sec = min(MAX_SAFE_WAIT_SEC, max(0.5, grace_s + 0.3))
            for fl in active_boots:
                if fl.thread is not None and fl.thread is not threading.current_thread() and fl.thread.is_alive():
                    fl.thread.join(timeout=join_sec)
        finally:
            for rh in retiring_handles:
                diags.extend(rh.shutdown(grace_sec=grace_s))
        return tuple(diags)

    def collect_lifo_shutdown_diagnostics(self) -> tuple[ErrorDetail, ...]:
        with self._state_cond:
            stragglers = list(self._workers.values())
            self._workers.clear()
            grace_s = self._shutdown_grace_sec
        diags: list[ErrorDetail] = []
        for sh in stragglers:
            diags.extend(sh.shutdown(grace_sec=grace_s))
        return tuple(diags)

    def has_reentrant_retiring_turn(self, group_key: str, turn_id: str, call_tree_id: str) -> bool:
        if not group_key or (not turn_id and not call_tree_id):
            return False
        with self._state_cond:
            ret_list = list(self._live_retiring_locked(group_key))
        return any(h.can_accept_reentrant_turn(turn_id, call_tree_id) for h in ret_list)

    def needs_retiring_drain_for_turn(
        self, group_descs: Sequence[ModuleDescriptor], turn_id: str, call_tree_id: str = "", bypass_reload: bool = False,
    ) -> bool:
        primary = group_descs[0]
        if primary.venv_python is None or bypass_reload:
            return False
        gkey = tier1_group_key_for(primary)
        if self._find_reentrant_retiring_worker(gkey, turn_id, call_tree_id) is not None:
            return False
        has_eager = any(d.eager_warmup for d in group_descs)
        with self._state_cond:
            fast = self._workers.get(gkey)
            if fast is not None and fast.is_alive:
                return False
            return any(not h.is_stopped and (has_eager or h.is_closing_for_reload) for h in self._live_retiring_locked(gkey))

    def await_group_ready_before_lock(
        self, group_descs: Sequence[ModuleDescriptor], *, turn_id: str, call_tree_id: str = "",
        bypass_reload: bool = False, cancel_token: CancellationToken, timeout_ms: Optional[int],
    ) -> None:
        primary = group_descs[0]
        if primary.venv_python is None or bypass_reload:
            return
        gkey = tier1_group_key_for(primary)
        if self._find_reentrant_retiring_worker(gkey, turn_id, call_tree_id) is not None:
            return
        if not any(d.eager_warmup for d in group_descs):
            with self._state_cond:
                need_wait = any(not h.is_stopped and h.is_closing_for_reload for h in self._live_retiring_locked(gkey))
            if not need_wait:
                return
        self._await_retiring_group_stopped(gkey, cancel_token=cancel_token, timeout_ms=timeout_ms)


def _prepare_worker_call(spec: WorkerCallSpec) -> tuple[str, DeadlineGuard, JsonObject]:
    primary = spec.group_descriptors[0]
    _ = require_non_none(primary.venv_python)
    return (tier1_group_key_for(primary), DeadlineGuard.from_timeout_ms(spec.timeout_ms, spec.cancel_token), DataclassCodec.encode_envelope(spec.command))


def _acquire_lock_interruptible(lock: threading.Lock, guard: DeadlineGuard) -> None:
    while not lock.acquire(timeout=0.02):
        if guard.cancel_token is not None:
            guard.cancel_token.raise_if_cancelled()
        if guard.deadline is not None and time.monotonic() >= guard.deadline:
            raise YscbError(ErrorCode.TASK_TIMEOUT, "Timed out waiting for Tier 1 worker group lock.")


def _push_cold_module_lifo(prefix: str, handle: _ActiveWorkerHandle, mod_id: ModuleId, lifo_stack: LifoResourceStack) -> None:
    if handle.record_or_claim_lifo_module(mod_id, is_committed=True):
        lifo_stack.push_diagnostic_closeable(f"{prefix}.{mod_id}", lambda m=mod_id, h=handle: _unload_module_on_handle(h, m, timeout_sec=0.4))
@dataclass(frozen=True, slots=True)
class _ColdGroupHandleEntry:
    group_key: str
    handle: _ActiveWorkerHandle
    tag_prefix: str


class OneShotVenvHost:
    """Executes Cold Turn Tier 1 steps, reusing per-Turn venv_group sessions with TurnScope LIFO teardown."""

    def __init__(
        self,
        workspace_root: HostPath,
        master_callback_handler: InboundCallHandler,
        *,
        host_dir: Optional[HostPath] = None,
        dialect_resolver: Optional[Callable[[], Optional[BoundLocaleDialect]]] = None,
        on_teardown_diagnostics: Optional[Callable[[Sequence[ErrorDetail]], None]] = None,
        env_lease_acquire: Optional[EnvLeaseAcquireFn] = None,
        env_touch_used: Optional[EnvTouchUsedFn] = None,
        daemon_boot_id: str = "",
        flight_log_config: Optional[JsonObject] = None,
    ) -> None:
        self._workspace_root, self._callback_handler, self._host_dir = workspace_root, master_callback_handler, host_dir
        self._dialect_resolver = dialect_resolver
        self._on_teardown_diags = on_teardown_diagnostics
        self._env_lease_acquire = env_lease_acquire
        self._env_touch_used = env_touch_used
        self._daemon_boot_id = daemon_boot_id
        self._flight_log_config = flight_log_config
        self._lock = threading.Lock()
        self._group_locks: dict[str, threading.Lock] = {}
        self._handles: dict[str, _ColdGroupHandleEntry] = {}

    def _notify_env_touch_used(self, handle: _ActiveWorkerHandle) -> None:
        touch_fn = self._env_touch_used
        if touch_fn is not None and handle.venv_python is not None:
            vp = handle.venv_python
            invoke_observer_safely(lambda: touch_fn(vp))

    def _current_bound_dialect(self) -> Optional[BoundLocaleDialect]:
        return self._dialect_resolver() if self._dialect_resolver is not None else None

    def _emit_async_diags(self, diags: Sequence[ErrorDetail]) -> None:
        if diags and self._on_teardown_diags is not None:
            self._on_teardown_diags(diags)

    def _retire_cold_handle(
        self,
        entry: _ColdGroupHandleEntry,
        lifo_stack: Optional[LifoResourceStack],
        *,
        grace_sec: float,
    ) -> tuple[ErrorDetail, ...]:
        if lifo_stack is not None:
            lifo_stack.pop_tagged_by_prefixes(frozenset({entry.tag_prefix}))
        _done_sync, diags = entry.handle.shutdown_when_healthy_drained(
            grace_sec=grace_sec,
            max_wait_sec=min(MAX_SAFE_WAIT_SEC, max(5.0, grace_sec)),
            on_drained=self._emit_async_diags,
        )
        return diags

    def sync_on_reload(
        self,
        unload_mods: frozenset[ModuleId],
        fresh_descriptors: Sequence[ModuleDescriptor],
        lifo_stack: LifoResourceStack,
        *,
        grace_sec: float = 0.4,
        evict_all: bool = False,
    ) -> tuple[ErrorDetail, ...]:
        grouped: dict[str, list[ModuleDescriptor]] = {}
        for desc in fresh_descriptors:
            if desc.venv_python is not None:
                grouped.setdefault(tier1_group_key_for(desc), []).append(desc)
        fresh_fps = {gk: _compute_group_desc_fingerprint(ds) for gk, ds in grouped.items()}
        evicted: list[_ColdGroupHandleEntry] = []
        with self._lock:
            for hkey, entry in list(self._handles.items()):
                fresh_fp = fresh_fps.get(entry.group_key)
                if (
                    evict_all
                    or bool(entry.handle.bound_modules & unload_mods)
                    or fresh_fp is None
                    or entry.handle.boot_fingerprint != fresh_fp
                ):
                    self._handles.pop(hkey, None)
                    self._group_locks.pop(hkey, None)
                    evicted.append(entry)
        diags: list[ErrorDetail] = []
        for entry in evicted:
            diags.extend(self._retire_cold_handle(entry, lifo_stack, grace_sec=grace_sec))
        return tuple(diags)

    def close_all(
        self,
        *,
        grace_sec: float = 0.4,
        lifo_stack: Optional[LifoResourceStack] = None,
    ) -> tuple[ErrorDetail, ...]:
        with self._lock:
            entries = list(self._handles.values())
            self._handles.clear()
            self._group_locks.clear()
        diags: list[ErrorDetail] = []
        for entry in entries:
            diags.extend(self._retire_cold_handle(entry, lifo_stack, grace_sec=grace_sec))
        return tuple(diags)

    def run_once_with_guard(
        self, spec: WorkerCallSpec, lifo_stack: LifoResourceStack,
    ) -> tuple[RemoteCallOutcome, Optional[threading.Event]]:
        return self._run_ephemeral_tty(spec, lifo_stack) if spec.inherit_tty else self._call_in_turn(spec, lifo_stack)

    def _call_in_turn(
        self, spec: WorkerCallSpec, lifo_stack: LifoResourceStack,
    ) -> tuple[RemoteCallOutcome, Optional[threading.Event]]:
        try:
            gkey, guard, wire_payload = _prepare_worker_call(spec)
        except YscbError as exc:
            return (RemoteCallOutcome(was_accepted=False, error_code=exc.detail.code, error_message=exc.detail.message), None)
        hkey = f"{spec.turn_id}:{gkey}" if spec.turn_id else gkey
        for _attempt in range(4):
            try:
                handle = self._acquire_turn_handle(hkey, gkey, spec, lifo_stack, guard)
                rem_ms = guard.remaining_ms(spec.timeout_ms, expired_message="Timed out before cold Tier 1 call.")
            except TaskCancelledException as exc:
                return (RemoteCallOutcome(was_accepted=False, error_code=exc.detail.code, error_message=exc.detail.message), None)
            except YscbError as exc:
                is_lost = exc.detail.code == ErrorCode.WORKER_CRASHED
                return (RemoteCallOutcome(was_accepted=False, transport_lost=is_lost, error_code=exc.detail.code, error_message=exc.detail.message), None)
            if not handle.try_enter_call(spec.turn_id, spec.call_tree_id, allow_reentrant=True):
                continue
            self._notify_env_touch_used(handle)
            return _invoke_worker_handle_with_taint(
                handle, wire_payload, spec, rem_ms, lambda h=handle: self._detach_turn_handle(hkey, h), drain_wait_sec=10.0,
            )
        return (RemoteCallOutcome(was_accepted=False, transport_lost=True, error_code=ErrorCode.WORKER_CRASHED), None)

    def _detach_turn_handle(self, hkey: str, handle: _ActiveWorkerHandle) -> None:
        with self._lock:
            cur = self._handles.get(hkey)
            if cur is not None and cur.handle is handle:
                self._handles.pop(hkey, None)

    def _acquire_turn_handle(
        self, hkey: str, gkey: str, spec: WorkerCallSpec, lifo_stack: LifoResourceStack, guard: DeadlineGuard,
    ) -> _ActiveWorkerHandle:
        target_fp = _compute_group_desc_fingerprint(spec.group_descriptors)
        with self._lock:
            fast_entry = self._handles.get(hkey)
            if fast_entry is not None and fast_entry.handle.is_alive and fast_entry.handle.boot_fingerprint == target_fp:
                return fast_entry.handle
            glk = self._group_locks.setdefault(hkey, threading.Lock())
        _acquire_lock_interruptible(glk, guard)
        try:
            with self._lock:
                existing_entry = self._handles.get(hkey)
                if existing_entry is not None and existing_entry.handle.is_alive and existing_entry.handle.boot_fingerprint == target_fp:
                    return existing_entry.handle
                stale_entry = self._handles.pop(hkey, None)
            if stale_entry is not None:
                stale_diags = self._retire_cold_handle(stale_entry, lifo_stack, grace_sec=0.4)
                self._emit_async_diags(stale_diags)
            tag_prefix = f"cold_venv.{gkey}"
            bd = self._current_bound_dialect()
            spawned = _spawn_connected_worker(
                workspace_root=self._workspace_root, descriptors=spec.group_descriptors, master_callback_handler=self._callback_handler,
                opts=_WorkerSpawnOpts(
                    f"cold_{gkey}",
                    is_hot=False,
                    on_module_init=lambda h, mid: _push_cold_module_lifo(tag_prefix, h, mid, lifo_stack),
                    host_dir=self._host_dir,
                    bound_dialect=bd,
                    env_lease_acquire=self._env_lease_acquire,
                    daemon_boot_id=self._daemon_boot_id,
                    flight_log_config=self._flight_log_config,
                ),
                guard=guard,
            )
            try:
                with self._lock:
                    self._handles[hkey] = _ColdGroupHandleEntry(group_key=gkey, handle=spawned, tag_prefix=tag_prefix)
                lifo_stack.push_diagnostic_closeable(tag_prefix, lambda: self._close_turn_handle(hkey, spawned))
                return spawned
            except BaseException:
                spawned.kill_immediately()
                raise
        finally:
            glk.release()

    def _close_turn_handle(self, hkey: str, handle: _ActiveWorkerHandle) -> tuple[ErrorDetail, ...]:
        with self._lock:
            cur = self._handles.get(hkey)
            if cur is not None and cur.handle is handle:
                self._handles.pop(hkey, None)
            if hkey not in self._handles:
                self._group_locks.pop(hkey, None)
        return handle.shutdown(grace_sec=0.4)

    def _run_ephemeral_tty(
        self, spec: WorkerCallSpec, lifo_stack: LifoResourceStack,
    ) -> tuple[RemoteCallOutcome, Optional[threading.Event]]:
        try:
            gkey_base, guard, wire_payload = _prepare_worker_call(spec)
        except YscbError as exc:
            return (RemoteCallOutcome(was_accepted=False, error_code=exc.detail.code, error_message=exc.detail.message), None)
        eph_key = f"oneshot_{gkey_base}_{uuid.uuid4().hex[:6]}"
        tag_prefix = f"cold_tty.{eph_key}"
        try:
            bd = self._current_bound_dialect()
            handle = _spawn_connected_worker(
                workspace_root=self._workspace_root, descriptors=spec.group_descriptors, master_callback_handler=self._callback_handler,
                opts=_WorkerSpawnOpts(
                    eph_key,
                    is_hot=False,
                    inherit_tty=True,
                    on_module_init=lambda h, mid: _push_cold_module_lifo(tag_prefix, h, mid, lifo_stack),
                    host_dir=self._host_dir,
                    bound_dialect=bd,
                    env_lease_acquire=self._env_lease_acquire,
                    daemon_boot_id=self._daemon_boot_id,
                    flight_log_config=self._flight_log_config,
                ),
                guard=guard,
            )
            try:
                with self._lock:
                    self._handles[eph_key] = _ColdGroupHandleEntry(
                        group_key=gkey_base,
                        handle=handle,
                        tag_prefix=tag_prefix,
                    )
                lifo_stack.push_diagnostic_closeable(tag_prefix, lambda: self._close_turn_handle(eph_key, handle))
                rem_ms = guard.remaining_ms(spec.timeout_ms, expired_message="Timed out before TTY Tier 1 call.")
            except BaseException:
                with self._lock:
                    self._handles.pop(eph_key, None)
                handle.kill_immediately()
                raise
        except TaskCancelledException as exc:
            return (RemoteCallOutcome(was_accepted=False, error_code=exc.detail.code, error_message=exc.detail.message), None)
        except YscbError as exc:
            is_lost = exc.detail.code == ErrorCode.WORKER_CRASHED
            return (RemoteCallOutcome(was_accepted=False, transport_lost=is_lost, error_code=exc.detail.code, error_message=exc.detail.message), None)
        if not handle.try_enter_call(spec.turn_id, spec.call_tree_id, allow_reentrant=True):
            return (RemoteCallOutcome(was_accepted=False, transport_lost=True, error_code=ErrorCode.WORKER_CRASHED), None)
        self._notify_env_touch_used(handle)
        return _invoke_worker_handle_with_taint(
            handle,
            wire_payload,
            spec,
            rem_ms,
            lambda h=handle: self._detach_turn_handle(eph_key, h),
            drain_wait_sec=10.0,
        )
