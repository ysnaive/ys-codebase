"""Active turn session lifecycle, step binding tracking, and cold per-turn slot allocation."""

from __future__ import annotations

from collections import OrderedDict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
import threading
from types import MappingProxyType
from typing import Callable, Iterator, Mapping, Optional, Sequence
import uuid

from core.execution.event import RawEventRecord
from core.execution.lifecycle import TurnKind, TurnScope
from core.execution.rpc import InboundCallHandler
from core.execution.runtime.contracts import (
    MODULES_DIRNAME,
    CallPropagationContext,
    ClientRoutingPolicy,
    EnvLeaseAcquireFn,
    EnvTouchUsedFn,
    ExecutionPriority,
    ModuleDescriptor,
    ModuleProviderPort,
    ModuleRuntimeServices,
    YscbModule,
)
from core.execution.runtime.coordinator import PriorityHandle
from core.execution.runtime.module_slot import LocalModuleSlotRegistry
from core.execution.runtime.services import InvocationCorrelationContext
from core.execution.runtime.worker_pool import OneShotVenvHost
from core.foundation.errors import ErrorCode, ErrorDetail, YscbError
from core.foundation.observability import CancellationToken
from core.foundation.primitives import HostPath, JsonObject, ModuleId, TaskId
from core.metadata.contributes import BoundLocaleDialect


def merge_deadlines(d1: Optional[float], d2: Optional[float]) -> Optional[float]:
    if d1 is None:
        return d2
    if d2 is None:
        return d1
    return min(d1, d2)


@dataclass(slots=True)
class ActiveTurnSession:
    """Unified per-Turn runtime session tracking scoped resources and transitive invoked frames."""

    scope: TurnScope
    caller_cancel: CancellationToken
    prio_handle: PriorityHandle
    refs: int = 1
    on_progress: Optional[Callable[[JsonObject], None]] = None
    root_call_tree_id: str = ""
    primary_task_id: str = ""
    inherit_call_tree: bool = False
    turn_deadline: Optional[float] = None
    turn_deadline_fn: Optional[Callable[[], Optional[float]]] = None
    hot_workspaces: frozenset[HostPath] = frozenset()
    cold_shared_workspaces: frozenset[HostPath] = frozenset()
    effective_deadline: Optional[float] = None
    cold_slots: Optional[LocalModuleSlotRegistry] = None
    cold_venv_host: Optional[OneShotVenvHost] = None
    closing: bool = False
    invoked_tasks: dict[tuple[HostPath, TaskId], None] = field(default_factory=dict)
    extra_teardown_diags: list[ErrorDetail] = field(default_factory=list)
    nested_committed_events: list[RawEventRecord] = field(default_factory=list)

    def current_turn_deadline(self) -> Optional[float]:
        if self.turn_deadline_fn is not None:
            return merge_deadlines(self.turn_deadline, self.turn_deadline_fn())
        return self.turn_deadline


@dataclass(frozen=True, slots=True)
class ActiveStepBinding:
    cancel_token: CancellationToken
    prio_handle: PriorityHandle
    turn_id: str = ""
    propagation: CallPropagationContext = field(default_factory=CallPropagationContext)
    parent_routing_policy: ClientRoutingPolicy = ClientRoutingPolicy.AUTO_SPAWN
    approval_scope: frozenset[TaskId] = frozenset()
    allow_conditional: bool = True
    deadline_fn: Optional[Callable[[], Optional[float]]] = None
    correlation: Optional[InvocationCorrelationContext] = None

    def current_deadline(self) -> Optional[float]:
        return self.deadline_fn() if self.deadline_fn is not None else None


class TurnSessionRegistry:
    """Thread-safe active turn session and step binding tracker."""

    def __init__(
        self,
        *,
        workspace_root: HostPath,
        module_provider: ModuleProviderPort,
        tier0_slots: LocalModuleSlotRegistry,
        callback_bridge: InboundCallHandler,
        in_memory_modules: Mapping[ModuleId, YscbModule] = MappingProxyType({}),
        module_services_factory: Optional[Callable[[ModuleId], ModuleRuntimeServices]] = None,
        worker_host_dir: Optional[HostPath] = None,
        cold_dialect_resolver: Optional[Callable[[], Optional[BoundLocaleDialect]]] = None,
        env_lease_acquire: Optional[EnvLeaseAcquireFn] = None,
        env_touch_used: Optional[EnvTouchUsedFn] = None,
        daemon_boot_id: str = "",
        flight_log_config: Optional[JsonObject] = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._module_provider = module_provider
        self._tier0_slots = tier0_slots
        self._callback_bridge = callback_bridge
        self._in_memory_modules = MappingProxyType(dict(in_memory_modules))
        self._module_services_factory = module_services_factory
        self._worker_host_dir = worker_host_dir
        self._cold_dialect_resolver = cold_dialect_resolver
        self._env_lease_acquire = env_lease_acquire
        self._env_touch_used = env_touch_used
        self._daemon_boot_id = daemon_boot_id
        self._flight_log_config = flight_log_config
        self._lock = threading.Lock()
        self._sessions: dict[str, ActiveTurnSession] = {}
        self._closed_turn_ids: OrderedDict[str, None] = OrderedDict()
        self._active_steps: dict[str, ActiveStepBinding] = {}
        self._pending_host_teardown_diags: deque[ErrorDetail] = deque(maxlen=256)
        self._reload_seq: int = 0

    def update_observability(
        self,
        *,
        daemon_boot_id: str = "",
        flight_log_config: Optional[JsonObject] = None,
    ) -> None:
        with self._lock:
            if daemon_boot_id:
                self._daemon_boot_id = daemon_boot_id
            if flight_log_config is not None:
                self._flight_log_config = flight_log_config

    @property
    def active_turn_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def active_turn_breakdown(self) -> tuple[int, int]:
        with self._lock:
            fg = sum(1 for s in self._sessions.values() if s.scope.kind != TurnKind.HOT_BACKGROUND)
            bg = len(self._sessions) - fg
            return (fg, bg)

    def record_host_teardown_diags(self, diags: Sequence[ErrorDetail]) -> None:
        if not diags:
            return
        with self._lock:
            self._pending_host_teardown_diags.extend(diags)

    def drain_teardown_diagnostics(self) -> tuple[ErrorDetail, ...]:
        slot_pending = self._tier0_slots.drain_pending_teardown_diagnostics()
        with self._lock:
            if not self._pending_host_teardown_diags and not slot_pending:
                return ()
            out = (*self._pending_host_teardown_diags, *slot_pending)
            self._pending_host_teardown_diags.clear()
            return out

    def record_step_teardown_diags(self, turn: TurnScope, diags: Sequence[ErrorDetail]) -> None:
        if not diags:
            return
        recorded = False
        with self._lock:
            sess = self._sessions.get(turn.turn_id)
            if sess is not None and not sess.closing:
                sess.extra_teardown_diags.extend(diags)
                recorded = True
        if not recorded:
            self.record_host_teardown_diags(diags)

    def snapshot_active_turn_and_tree_ids(self) -> frozenset[str]:
        ids: set[str] = set()
        with self._lock:
            for tid, sess in self._sessions.items():
                if tid:
                    ids.add(tid)
                if sess.root_call_tree_id:
                    ids.add(sess.root_call_tree_id)
        return frozenset(ids)

    def has_admitted_session(self, prop: CallPropagationContext) -> bool:
        tid = prop.turn_id or ""
        with self._lock:
            return bool(tid) and tid in self._sessions

    def ensure_fresh_turn_id(self, prop: CallPropagationContext) -> tuple[str, CallPropagationContext]:
        tid = prop.turn_id or uuid.uuid4().hex
        with self._lock:
            if tid in self._sessions or tid in self._closed_turn_ids:
                old_tid = tid
                tid = uuid.uuid4().hex
                is_nested_turn = prop.is_nested_call or bool(prop.call_stack)
                eff_ctree = (
                    (prop.call_tree_id or old_tid)
                    if is_nested_turn
                    else (prop.call_tree_id if (prop.call_tree_id and prop.call_tree_id != old_tid) else tid)
                )
                prop = replace(prop, turn_id=tid, call_tree_id=eff_ctree)
            elif prop.turn_id != tid:
                prop = replace(prop, turn_id=tid)
        return (tid, prop)

    def cancel_all(self, reason: str) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
        for sess in sessions:
            sess.scope.cancel_token.cancel(reason=reason)
            sess.caller_cancel.cancel(reason=reason)

    def bind_active_step(self, step_run_id: str, binding: ActiveStepBinding) -> None:
        with self._lock:
            self._active_steps[step_run_id] = binding

    def unbind_active_step(self, step_run_id: str) -> None:
        with self._lock:
            self._active_steps.pop(step_run_id, None)

    def lookup_active_step(self, step_run_id: str) -> Optional[ActiveStepBinding]:
        with self._lock:
            return self._active_steps.get(step_run_id)

    def try_retain_session_scope(self, turn_id: str) -> Optional[TurnScope]:
        if not turn_id:
            return None
        with self._lock:
            sess = self._sessions.get(turn_id)
            if sess is not None and not sess.closing:
                sess.refs += 1
                return sess.scope
        return None

    @contextmanager
    def managed_session(self, session: ActiveTurnSession) -> Iterator[None]:
        tid = session.scope.turn_id
        with self._lock:
            self._sessions[tid] = session
        session.scope.scoped_stack.push_diagnostic_closeable(
            f"turn_session.{tid}",
            lambda s=session: self.close_managed_session(s),
        )
        try:
            yield
        finally:
            self.close_managed_session(session)

    def snapshot_session_invoked_tasks(self, session: ActiveTurnSession) -> tuple[tuple[HostPath, TaskId], ...]:
        with self._lock:
            return tuple(session.invoked_tasks.keys())

    def _mark_turn_closed_locked(self, turn_id: str) -> None:
        if not turn_id:
            return
        self._closed_turn_ids[turn_id] = None
        while len(self._closed_turn_ids) > 512:
            self._closed_turn_ids.popitem(last=False)

    def _drain_session_resources(self, session: ActiveTurnSession) -> tuple[ErrorDetail, ...]:
        with self._lock:
            cold_reg = session.cold_slots
            session.cold_slots = None
            cold_venv = session.cold_venv_host
            session.cold_venv_host = None
        cold_diags = cold_reg.unload_all_modules() if cold_reg is not None else ()
        venv_diags = cold_venv.close_all(grace_sec=0.4, lifo_stack=session.scope.scoped_stack) if cold_venv is not None else ()
        with self._lock:
            extra = (*session.extra_teardown_diags, *cold_diags, *venv_diags)
            session.extra_teardown_diags.clear()
            return extra

    def close_managed_session(self, session: ActiveTurnSession) -> tuple[ErrorDetail, ...]:
        tid = session.scope.turn_id
        with self._lock:
            already_closing = session.closing
            session.closing = True
            self._mark_turn_closed_locked(tid)
        extra = self._drain_session_resources(session)
        if not already_closing:
            self.release_turn_session(tid)
        return extra

    def get_or_bind_turn_session(self, turn: TurnScope, *, retain: bool = False) -> ActiveTurnSession:
        created: Optional[ActiveTurnSession] = None
        with self._lock:
            sess = self._sessions.get(turn.turn_id)
            if sess is not None:
                if sess.closing and retain:
                    raise YscbError(ErrorCode.TASK_CANCELLED, f"Turn '{turn.turn_id}' is closing.")
                if retain:
                    sess.refs += 1
                return sess
            if turn.turn_id in self._closed_turn_ids:
                raise YscbError(ErrorCode.TASK_CANCELLED, f"Turn '{turn.turn_id}' has already closed.")
            init_p = ExecutionPriority.BACKGROUND if turn.kind == TurnKind.HOT_BACKGROUND else ExecutionPriority.FOREGROUND
            created = ActiveTurnSession(
                scope=turn,
                caller_cancel=turn.cancel_token,
                prio_handle=PriorityHandle(init_p),
                refs=2 if retain else 1,
            )
            self._sessions[turn.turn_id] = created
        turn.scoped_stack.push_diagnostic_closeable(
            f"turn_session.{turn.turn_id}",
            lambda s=created: self.close_managed_session(s),
        )
        return created

    def release_turn_session(self, turn_id: str) -> None:
        final_sess: Optional[ActiveTurnSession] = None
        with self._lock:
            sess = self._sessions.get(turn_id)
            if sess is None:
                return
            if sess.refs <= 1:
                sess.closing = True
                self._mark_turn_closed_locked(turn_id)
                self._sessions.pop(turn_id, None)
                final_sess = sess
            else:
                sess.refs -= 1
        if final_sess is not None:
            late = self._drain_session_resources(final_sess)
            if late:
                self.record_host_teardown_diags(late)

    def _build_cold_tier0_descriptors(
        self,
        provider_descriptors: Optional[Sequence[ModuleDescriptor]] = None,
    ) -> list[ModuleDescriptor]:
        src = provider_descriptors if provider_descriptors is not None else self._module_provider.list_modules()
        tier0 = [d for d in src if d.venv_python is None]
        existing_mids = {d.module_id for d in tier0}
        for mid, mod_inst in self._in_memory_modules.items():
            if mid not in existing_mids:
                tier0.append(
                    ModuleDescriptor(
                        module_id=mid,
                        module_dir=self._workspace_root.join(MODULES_DIRNAME, mid.value),
                        declared_tasks=tuple(bt.route_spec for bt in mod_inst.tasks()),
                    )
                )
        return tier0

    def slots_for_turn(self, turn: Optional[TurnScope]) -> LocalModuleSlotRegistry:
        if turn is None or turn.kind != TurnKind.COLD:
            return self._tier0_slots
        sess = self.get_or_bind_turn_session(turn)
        for _ in range(3):
            with self._lock:
                if sess.closing:
                    raise YscbError(ErrorCode.TASK_CANCELLED, f"Turn '{turn.turn_id}' is closing.")
                if sess.cold_slots is not None:
                    return sess.cold_slots
                seq_before = self._reload_seq
            tier0 = self._build_cold_tier0_descriptors()
            with self._lock:
                if sess.closing:
                    raise YscbError(ErrorCode.TASK_CANCELLED, f"Turn '{turn.turn_id}' is closing.")
                if sess.cold_slots is not None:
                    return sess.cold_slots
                if self._reload_seq != seq_before:
                    continue
                reg = LocalModuleSlotRegistry(
                    self._workspace_root,
                    turn.scoped_stack,
                    in_memory_modules=self._in_memory_modules,
                    module_services_factory=self._module_services_factory,
                )
                reg.register_descriptors(tier0)
                sess.cold_slots = reg
                return sess.cold_slots
        raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"Cold slot initialization raced with reload in turn '{turn.turn_id}'.")

    def sync_cold_slots_on_reload(
        self,
        unload_mods: frozenset[ModuleId],
        fresh_descriptors: Sequence[ModuleDescriptor],
        *,
        grace_sec: float = 0.2,
        evict_all: bool = False,
    ) -> tuple[ErrorDetail, ...]:
        with self._lock:
            self._reload_seq += 1
            cold_regs = [
                sess.cold_slots
                for sess in self._sessions.values()
                if not sess.closing and sess.cold_slots is not None
            ]
            cold_venvs = [
                (sess.cold_venv_host, sess.scope.scoped_stack)
                for sess in self._sessions.values()
                if not sess.closing and sess.cold_venv_host is not None
            ]
        if not cold_regs and not cold_venvs:
            return ()
        diags: list[ErrorDetail] = []
        for venv_host, scoped_stack in cold_venvs:
            diags.extend(
                venv_host.sync_on_reload(
                    unload_mods,
                    fresh_descriptors,
                    scoped_stack,
                    grace_sec=max(0.2, grace_sec),
                    evict_all=evict_all,
                )
            )
        if cold_regs:
            tier0_descs = self._build_cold_tier0_descriptors(fresh_descriptors)
            for reg in cold_regs:
                if evict_all or unload_mods:
                    eff_unload = (
                        frozenset(d.module_id for d in tier0_descs if d.module_id not in self._in_memory_modules)
                        | unload_mods
                    ) if evict_all else unload_mods
                    if eff_unload:
                        diags.extend(reg.unload_modules(eff_unload, drain_in_flight=False, grace_sec=grace_sec))
                reg.register_descriptors(tier0_descs)
                diags.extend(reg.drain_pending_teardown_diagnostics())
        return tuple(diags)

    def evict_cold_tier1_for_quiesce(self, *, grace_sec: float = 0.4) -> tuple[ErrorDetail, ...]:
        with self._lock:
            cold_venvs = [
                (sess.cold_venv_host, sess.scope.scoped_stack)
                for sess in self._sessions.values()
                if not sess.closing and sess.cold_venv_host is not None
            ]
        diags: list[ErrorDetail] = []
        for venv_host, scoped_stack in cold_venvs:
            diags.extend(venv_host.close_all(grace_sec=grace_sec, lifo_stack=scoped_stack))
        return tuple(diags)

    def cold_venv_for_turn(self, turn: TurnScope) -> OneShotVenvHost:
        sess = self.get_or_bind_turn_session(turn)
        with self._lock:
            if sess.closing:
                raise YscbError(ErrorCode.TASK_CANCELLED, f"Turn '{turn.turn_id}' is closing.")
            if sess.cold_venv_host is None:
                sess.cold_venv_host = OneShotVenvHost(
                    self._workspace_root,
                    self._callback_bridge,
                    host_dir=self._worker_host_dir,
                    dialect_resolver=self._cold_dialect_resolver,
                    on_teardown_diagnostics=lambda diags, t=turn: self.record_step_teardown_diags(t, diags),
                    env_lease_acquire=self._env_lease_acquire,
                    env_touch_used=self._env_touch_used,
                    daemon_boot_id=self._daemon_boot_id,
                    flight_log_config=self._flight_log_config,
                )
            return sess.cold_venv_host

    def record_session_invoked_frame(self, sess: ActiveTurnSession, frame: tuple[HostPath, TaskId]) -> None:
        with self._lock:
            sess.invoked_tasks.setdefault(frame, None)

    def record_transitive_invoked_tasks(
        self,
        prop: CallPropagationContext,
        invoked: Sequence[tuple[HostPath, TaskId]],
    ) -> None:
        if not invoked or not prop.turn_id:
            return
        with self._lock:
            sess = self._sessions.get(prop.turn_id)
            if sess is not None:
                for frame in invoked:
                    sess.invoked_tasks.setdefault(frame, None)

    def record_nested_committed_events(
        self,
        turn: TurnScope,
        events: tuple[RawEventRecord, ...],
    ) -> None:
        if not events:
            return
        with self._lock:
            sess = self._sessions.get(turn.turn_id)
            if sess is not None and not sess.closing:
                sess.nested_committed_events.extend(events)
        turn.event_queue.append_committed(events)

    def drain_session_nested_events(self, session: ActiveTurnSession) -> tuple[RawEventRecord, ...]:
        with self._lock:
            if not session.nested_committed_events:
                return ()
            out = tuple(session.nested_committed_events)
            session.nested_committed_events.clear()
            return out

    def record_imm_or_turn_diagnostic(
        self,
        turn: TurnScope,
        detail: ErrorDetail,
    ) -> None:
        turn.record_event_diagnostic(detail)
