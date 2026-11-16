"""Active turn session lifecycle, step event capture queries, and coalesce caller lineage tracking."""

from __future__ import annotations

from collections import OrderedDict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
import threading
from typing import Callable, Iterator, Optional, Sequence
import uuid

from core.execution.event import CausalLineage, RawEventRecord, ScopedHop, hop_conflicts
from core.execution.lifecycle import TurnKind, TurnScope
from core.execution.rpc import InboundCallHandler
from core.execution.runtime.contracts import (
    CallPropagationContext,
    CoalesceCallerView,
    ExecutionPriority,
    ModuleProviderPort,
)
from core.execution.runtime.coordinator import PriorityHandle
from core.execution.runtime.gates import SharedWorkspaceState
from core.execution.runtime.lineage_join import (
    ChildCascadeJoin,
    FlightCascade,
    StepEventCapture,
    extract_emitted_hops_from_records,
)
from core.execution.runtime.module_slot import LocalModuleSlotRegistry
from core.execution.runtime.wire import EmittedEventHop
from core.execution.runtime.worker_pool import OneShotVenvHost
from core.foundation.errors import CallCycleError, ErrorCode, ErrorDetail, EventCycleError, YscbError
from core.foundation.observability import CancellationToken
from core.foundation.primitives import HostPath, JsonObject, TaskId


def merge_deadlines(d1: Optional[float], d2: Optional[float]) -> Optional[float]:
    if d1 is None:
        return d2
    if d2 is None:
        return d1
    return min(d1, d2)


@dataclass(frozen=True, slots=True)
class AttachedCascade:
    base_lineage: CausalLineage
    cascade: FlightCascade
    slot_id: int
    unreg_prio: Callable[[], None]


@dataclass(slots=True)
class ActiveTurnSession:
    """Unified per-Turn runtime session tracking scoped resources, cascades, and transitive lineage."""

    scope: TurnScope
    caller_cancel: CancellationToken
    prio_handle: PriorityHandle
    refs: int = 1
    on_progress: Optional[Callable[[JsonObject], None]] = None
    root_call_tree_id: str = ""
    primary_task_id: str = ""
    inherit_call_tree: bool = False
    turn_deadline: Optional[float] = None
    hot_workspaces: frozenset[HostPath] = frozenset()
    cold_shared_workspaces: frozenset[HostPath] = frozenset()
    coalesce_callers: tuple[CoalesceCallerView, ...] = ()
    turn_entry_stack: tuple[tuple[HostPath, TaskId], ...] = ()
    owner_cascade: Optional[FlightCascade] = None
    effective_deadline: Optional[float] = None
    cold_slots: Optional[LocalModuleSlotRegistry] = None
    cold_venv_host: Optional[OneShotVenvHost] = None
    closing: bool = False
    invoked_tasks: dict[tuple[HostPath, TaskId], None] = field(default_factory=dict)
    emitted_hops: dict[ScopedHop, EmittedEventHop] = field(default_factory=dict)
    extra_teardown_diags: list[ErrorDetail] = field(default_factory=list)
    attached_cascades: list[AttachedCascade] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ActiveStepBinding:
    cancel_token: CancellationToken
    prio_handle: PriorityHandle
    approval_scope: frozenset[TaskId] = frozenset()
    allow_conditional: bool = True
    deadline_fn: Optional[Callable[[], Optional[float]]] = None

    def current_deadline(self) -> Optional[float]:
        return self.deadline_fn() if self.deadline_fn is not None else None


def abort_remaining_attached(items: Sequence[AttachedCascade]) -> None:
    for item in items:
        item.unreg_prio()
        item.cascade.detach_caller_slot(item.slot_id)


def capture_matches_prop(
    ws_key: str,
    own_ws: str,
    cap: StepEventCapture,
    prop: CallPropagationContext,
    eff_tid: str,
) -> bool:
    same_turn = (
        ws_key == own_ws
        and bool(eff_tid)
        and cap.turn_id == eff_tid
        and len(prop.call_stack) >= len(cap.prefix_stack)
        and prop.call_stack[: len(cap.prefix_stack)] == cap.prefix_stack
    )
    if same_turn:
        return True
    return cap.turn_id != eff_tid and (
        (bool(prop.call_tree_id) and cap.turn_id == prop.call_tree_id)
        or cap.turn_id in prop.coalesce_flights
    )


def record_unique_frames(
    dest: dict[tuple[HostPath, TaskId], None],
    frames: Sequence[tuple[HostPath, TaskId]],
) -> None:
    for frame in frames:
        dest.setdefault(frame, None)


def record_unique_emitted_hops(
    dest: dict[ScopedHop, EmittedEventHop],
    hops: Sequence[EmittedEventHop],
) -> None:
    for eh in hops:
        key = (eh.workspace_scope, eh.event_id)
        prev = dest.get(key)
        if prev is None or (prev.source_task is None and eh.source_task is not None):
            dest[key] = eh


def append_frames_to_views(
    views: Sequence[CoalesceCallerView],
    extra_stack: Sequence[tuple[HostPath, TaskId]],
    extra_hops: Sequence[ScopedHop],
) -> tuple[CoalesceCallerView, ...]:
    if not extra_stack and not extra_hops:
        return tuple(views)
    return tuple(
        CoalesceCallerView(
            turn_id=v.turn_id,
            call_tree_id=v.call_tree_id,
            call_stack=tuple(dict.fromkeys((*v.call_stack, *extra_stack))),
            caller_hops=tuple(dict.fromkeys((*v.caller_hops, *extra_hops))),
            flight_ids=v.flight_ids,
            in_event_chain=(v.in_event_chain or bool(extra_hops)),
        )
        for v in views
    )


def filter_and_advance_coalesce_views(
    views: Sequence[CoalesceCallerView],
    cand_hops: Sequence[ScopedHop],
) -> tuple[CoalesceCallerView, ...]:
    if not views:
        return ()
    if not cand_hops:
        return tuple(views)
    surviving = [
        v
        for v in views
        if not any(hop_conflicts(h, cs, ce) for h in v.caller_hops for cs, ce in cand_hops)
    ]
    return append_frames_to_views(surviving, (), cand_hops)


def live_session_coalesce_views(sess: ActiveTurnSession) -> tuple[CoalesceCallerView, ...]:
    if sess.owner_cascade is not None:
        return sess.owner_cascade.snapshot_live_caller_views()
    return sess.coalesce_callers


def find_common_view_conflicting_hop(
    views: Sequence[CoalesceCallerView],
    cand_hops: Sequence[ScopedHop],
) -> Optional[ScopedHop]:
    if not views or not cand_hops:
        return None
    for cs, ce in cand_hops:
        if all(any(hop_conflicts(h, cs, ce) for h in v.caller_hops) for v in views):
            return (cs, ce)
    return None


def first_caller_hop_cycle(
    caller_lineage: CausalLineage,
    emitted_hops: Sequence[EmittedEventHop],
    fallback_task: str,
) -> Optional[ErrorDetail]:
    cur = caller_lineage
    try:
        for ehop in emitted_hops:
            cur = cur.advance(
                ehop.event_id,
                source_task=ehop.source_task or fallback_task,
                workspace_scope=ehop.workspace_scope,
            )
    except EventCycleError as exc:
        return exc.detail
    return None


def lineage_to_emitted_hops(
    lineage: CausalLineage,
    known_hops: Sequence[EmittedEventHop],
    fallback_task: Optional[str],
) -> tuple[EmittedEventHop, ...]:
    src_map = {(h.workspace_scope, h.event_id): h.source_task for h in known_hops if h.source_task is not None}
    raw = lineage.scoped_hops()
    return tuple(
        EmittedEventHop(
            workspace_scope=ws_s,
            event_id=eid,
            source_task=src_map.get((ws_s, eid)) or (fallback_task if idx == len(raw) - 1 else None),
        )
        for idx, (ws_s, eid) in enumerate(raw)
    )


class TurnSessionRegistry:
    """Thread-safe active turn session, step binding, and cross-workspace capture tracker."""

    def __init__(
        self,
        *,
        workspace_root: HostPath,
        module_provider: ModuleProviderPort,
        tier0_slots: LocalModuleSlotRegistry,
        callback_bridge: InboundCallHandler,
        shared_ws_getter: Callable[[], SharedWorkspaceState],
    ) -> None:
        self._workspace_root = workspace_root
        self._module_provider = module_provider
        self._tier0_slots = tier0_slots
        self._callback_bridge = callback_bridge
        self._shared_ws_getter = shared_ws_getter
        self._lock = threading.Lock()
        self._sessions: dict[str, ActiveTurnSession] = {}
        self._closed_turn_ids: OrderedDict[str, None] = OrderedDict()
        self._active_steps: dict[str, ActiveStepBinding] = {}
        self._pending_host_teardown_diags: deque[ErrorDetail] = deque(maxlen=256)

    @property
    def active_turn_count(self) -> int:
        with self._lock:
            return len(self._sessions)

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
                for att in sess.attached_cascades:
                    ids.add(f"cascade_{att.cascade.cascade_id}")
        return frozenset(ids)

    def has_admitted_session(self, prop: CallPropagationContext) -> bool:
        tid = prop.turn_id or ""
        with self._lock:
            return (bool(tid) and tid in self._sessions) or any(
                c.turn_id in self._sessions for c in prop.coalesce_callers
            )

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

    def register_flight_session(self, flight_tid: str, flight_sess: ActiveTurnSession, capture: StepEventCapture) -> None:
        with self._lock:
            self._sessions[flight_tid] = flight_sess
        shared_ws = self._shared_ws_getter()
        with shared_ws.guard:
            shared_ws.captures_by_ws.setdefault(self._workspace_root.comparison_key, []).append(capture)

    def remove_step_capture(self, capture: Optional[StepEventCapture]) -> None:
        if capture is None:
            return
        shared_ws = self._shared_ws_getter()
        ws_key = self._workspace_root.comparison_key
        with shared_ws.guard:
            local_caps = shared_ws.captures_by_ws.get(ws_key)
            if local_caps is not None and capture in local_caps:
                local_caps.remove(capture)

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

    def snapshot_session_lineage(
        self,
        session: ActiveTurnSession,
    ) -> tuple[tuple[tuple[HostPath, TaskId], ...], tuple[EmittedEventHop, ...]]:
        with self._lock:
            return (tuple(session.invoked_tasks.keys()), tuple(session.emitted_hops.values()))

    def pop_attached_cascades(
        self,
        turn_id: str,
    ) -> tuple[Optional[ActiveTurnSession], list[AttachedCascade]]:
        with self._lock:
            session = self._sessions.get(turn_id)
            if session is None or not session.attached_cascades:
                return (session, [])
            cascades = list(session.attached_cascades)
            session.attached_cascades.clear()
            return (session, cascades)

    def record_cascade_outcome(
        self,
        session: ActiveTurnSession,
        hops: Sequence[EmittedEventHop],
        td_diags: Sequence[ErrorDetail],
    ) -> None:
        with self._lock:
            record_unique_emitted_hops(session.emitted_hops, hops)
            session.extra_teardown_diags.extend(td_diags)

    def _mark_turn_closed_locked(self, turn_id: str) -> None:
        if not turn_id:
            return
        self._closed_turn_ids[turn_id] = None
        while len(self._closed_turn_ids) > 512:
            self._closed_turn_ids.popitem(last=False)

    def _drain_session_resources(self, session: ActiveTurnSession) -> tuple[ErrorDetail, ...]:
        with self._lock:
            leftover = list(session.attached_cascades)
            session.attached_cascades.clear()
            cold_reg = session.cold_slots
            session.cold_slots = None
        if leftover:
            abort_remaining_attached(leftover)
        cold_diags = cold_reg.unload_all_modules() if cold_reg is not None else ()
        with self._lock:
            extra = (*session.extra_teardown_diags, *cold_diags)
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

    def slots_for_turn(self, turn: Optional[TurnScope]) -> LocalModuleSlotRegistry:
        if turn is None or turn.kind != TurnKind.COLD:
            return self._tier0_slots
        sess = self.get_or_bind_turn_session(turn)
        with self._lock:
            if sess.cold_slots is not None:
                return sess.cold_slots
        tier0 = [d for d in self._module_provider.list_modules() if d.venv_python is None]
        with self._lock:
            if sess.cold_slots is None:
                reg = LocalModuleSlotRegistry(self._workspace_root, turn.scoped_stack)
                reg.register_descriptors(tier0)
                sess.cold_slots = reg
            return sess.cold_slots

    def cold_venv_for_turn(self, turn: TurnScope) -> OneShotVenvHost:
        sess = self.get_or_bind_turn_session(turn)
        with self._lock:
            if sess.cold_venv_host is None:
                sess.cold_venv_host = OneShotVenvHost(self._workspace_root, self._callback_bridge)
            return sess.cold_venv_host

    def record_session_invoked_frame(self, sess: ActiveTurnSession, frame: tuple[HostPath, TaskId]) -> None:
        with self._lock:
            sess.invoked_tasks.setdefault(frame, None)

    def find_innermost_step_capture(
        self,
        turn_id: str,
        call_stack: tuple[tuple[HostPath, TaskId], ...],
    ) -> Optional[StepEventCapture]:
        shared_ws = self._shared_ws_getter()
        with shared_ws.guard:
            return self._lookup_innermost_capture_locked(shared_ws, turn_id, call_stack)

    def find_call_tree_captures(
        self,
        prop: CallPropagationContext,
        turn_id: str,
    ) -> list[StepEventCapture]:
        eff_tid = turn_id or (prop.turn_id or "")
        own_ws = self._workspace_root.comparison_key
        shared_ws = self._shared_ws_getter()
        with shared_ws.guard:
            entries = [(ws_key, cap) for ws_key, caps in shared_ws.captures_by_ws.items() for cap in caps]
        return [cap for ws_key, cap in entries if capture_matches_prop(ws_key, own_ws, cap, prop, eff_tid)]

    def snapshot_coalesce_callers(
        self,
        prop: CallPropagationContext,
        turn_id: str,
    ) -> tuple[CoalesceCallerView, ...]:
        caps = self.find_call_tree_captures(prop, turn_id)
        base_views = caps[-1].flight.snapshot_caller_views() if caps else prop.coalesce_callers
        if not base_views and turn_id:
            with self._lock:
                sess = self._sessions.get(turn_id)
                owner_c = sess.owner_cascade if sess is not None else None
                sess_views = sess.coalesce_callers if sess is not None else ()
            base_views = owner_c.snapshot_live_caller_views() if owner_c is not None else sess_views
        if not base_views:
            return ()
        return append_frames_to_views(base_views, prop.call_stack, prop.lineage.scoped_hops())

    def record_transitive_invoked_tasks(
        self,
        prop: CallPropagationContext,
        invoked: Sequence[tuple[HostPath, TaskId]],
    ) -> None:
        if not invoked:
            return
        caps = self.find_call_tree_captures(prop, prop.turn_id or "")
        if caps:
            shared_ws = self._shared_ws_getter()
            with shared_ws.guard:
                for cap in caps:
                    record_unique_frames(cap.invoked_tasks, invoked)
        if prop.turn_id:
            with self._lock:
                sess = self._sessions.get(prop.turn_id)
                if sess is not None:
                    record_unique_frames(sess.invoked_tasks, invoked)

    def record_capture_invoked_task(
        self,
        turn: Optional[TurnScope],
        prop: CallPropagationContext,
        frame: tuple[HostPath, TaskId],
    ) -> None:
        eff_tid = turn.turn_id if turn is not None else (prop.turn_id or "")
        caps = self.find_call_tree_captures(prop, eff_tid)
        for cap in caps:
            cyc_exc = CallCycleError(
                f"Synchronous task call cycle detected across coalesce callers on '{frame[1]}'",
                source_task=str(frame[1]),
            )
            ev, surv = cap.flight.evict_callers_where(
                lambda reg, f=frame: f in reg.caller_stack,
                lambda v, _rfl, f=frame: f in v.call_stack,
                lambda _vs, e=cyc_exc: e,
            )
            if not ev and not surv and cap.flight.all_active_callers_have_frame(frame):
                raise cyc_exc
        if prop.coalesce_callers and all(frame in v.call_stack for v in prop.coalesce_callers):
            raise CallCycleError(
                f"Synchronous task call cycle detected across coalesce callers on '{frame[1]}'",
                source_task=str(frame[1]),
            )
        self.record_transitive_invoked_tasks(replace(prop, turn_id=eff_tid or None), (frame,))

    def record_session_emitted_hops(self, turn_id: str, hops: Sequence[EmittedEventHop]) -> None:
        if not hops or not turn_id:
            return
        with self._lock:
            sess = self._sessions.get(turn_id)
            if sess is not None:
                record_unique_emitted_hops(sess.emitted_hops, hops)

    def record_session_emitted_records(self, turn_id: str, records: Sequence[RawEventRecord]) -> None:
        if records and turn_id:
            self.record_session_emitted_hops(turn_id, extract_emitted_hops_from_records(records))

    def record_transitive_emitted_hops(
        self,
        prop: CallPropagationContext,
        hops: Sequence[EmittedEventHop],
    ) -> None:
        if not hops:
            return
        caps = self.find_call_tree_captures(prop, prop.turn_id or "")
        if caps:
            shared_ws = self._shared_ws_getter()
            with shared_ws.guard:
                for cap in caps:
                    record_unique_emitted_hops(cap.imm_hops, hops)
        if prop.turn_id:
            self.record_session_emitted_hops(prop.turn_id, hops)
            with self._lock:
                sess = self._sessions.get(prop.turn_id)
                owner_c = sess.owner_cascade if sess is not None else None
            if owner_c is not None:
                owner_c.record_emitted_hops(hops)

    def _lookup_innermost_capture_locked(
        self,
        shared_ws: SharedWorkspaceState,
        turn_id: str,
        call_stack: tuple[tuple[HostPath, TaskId], ...],
    ) -> Optional[StepEventCapture]:
        local_caps = shared_ws.captures_by_ws.get(self._workspace_root.comparison_key, ())
        matched = [
            cap
            for cap in local_caps
            if cap.turn_id == turn_id
            and len(call_stack) >= len(cap.prefix_stack)
            and call_stack[: len(cap.prefix_stack)] == cap.prefix_stack
        ]
        return matched[-1] if matched else None

    def record_nested_committed_events(
        self,
        turn: TurnScope,
        call_stack: tuple[tuple[HostPath, TaskId], ...],
        events: tuple[RawEventRecord, ...],
    ) -> None:
        if not events:
            return
        shared_ws = self._shared_ws_getter()
        with shared_ws.guard:
            cap = self._lookup_innermost_capture_locked(shared_ws, turn.turn_id, call_stack)
            if cap is not None:
                cap.deferred_events.extend(events)
                return
        self.record_session_emitted_records(turn.turn_id, events)
        try:
            sess = self.get_or_bind_turn_session(turn)
        except YscbError:
            return
        if sess.owner_cascade is not None:
            sess.owner_cascade.record_emitted_hops(extract_emitted_hops_from_records(events))
        turn.event_queue.append_committed(events)

    def record_imm_or_turn_diagnostic(
        self,
        turn: TurnScope,
        call_stack: tuple[tuple[HostPath, TaskId], ...],
        detail: ErrorDetail,
    ) -> None:
        shared_ws = self._shared_ws_getter()
        with shared_ws.guard:
            cap = self._lookup_innermost_capture_locked(shared_ws, turn.turn_id, call_stack)
            if cap is not None:
                cap.imm_diagnostics.append(detail)
                return
        turn.record_event_diagnostic(detail)

    def resolve_hop_source_task(
        self,
        hop: ScopedHop,
        caps: Sequence[StepEventCapture],
        sess: ActiveTurnSession,
        fallback: str,
    ) -> str:
        shared_ws = self._shared_ws_getter()
        with shared_ws.guard:
            for cap in caps:
                eh_c = cap.imm_hops.get(hop)
                if eh_c is not None and eh_c.source_task is not None:
                    return eh_c.source_task
        with self._lock:
            eh_s = sess.emitted_hops.get(hop)
            if eh_s is not None and eh_s.source_task is not None:
                return eh_s.source_task
        return fallback

    def attach_resolved_cascade(
        self,
        turn: TurnScope,
        caller_ancestors: tuple[tuple[HostPath, TaskId], ...],
        caller_lineage: CausalLineage,
        cascade: FlightCascade,
        caller_slot_id: int,
        fallback_src: str,
    ) -> None:
        shared_ws = self._shared_ws_getter()
        with shared_ws.guard:
            enclosing_cap = self._lookup_innermost_capture_locked(shared_ws, turn.turn_id, caller_ancestors)
            if enclosing_cap is not None:
                rel_ehops = lineage_to_emitted_hops(caller_lineage, tuple(enclosing_cap.imm_hops.values()), fallback_src)
                enclosing_cap.child_joins.append(ChildCascadeJoin(rel_ehops, cascade, caller_slot_id))
                return
        try:
            sess = self.get_or_bind_turn_session(turn)
        except YscbError:
            cascade.detach_caller_slot(caller_slot_id)
            return
        if sess.owner_cascade is not None:
            with self._lock:
                if sess.closing:
                    known_hops: Optional[tuple[EmittedEventHop, ...]] = None
                else:
                    known_hops = tuple(sess.emitted_hops.values())
            if known_hops is None:
                cascade.detach_caller_slot(caller_slot_id)
                return
            rel_ehops = lineage_to_emitted_hops(caller_lineage, known_hops, fallback_src)
            sess.owner_cascade.add_child_join(rel_ehops, cascade, transfer_slot_id=caller_slot_id)
            return
        unreg_p = sess.prio_handle.register_listener(
            lambda p: cascade.prio_handle.elevate_to_foreground() if p == ExecutionPriority.FOREGROUND else None
        )
        abort_attach = False
        with self._lock:
            if sess.closing or self._sessions.get(turn.turn_id) is not sess:
                abort_attach = True
            else:
                sess.attached_cascades.append(AttachedCascade(caller_lineage, cascade, caller_slot_id, unreg_p))
        if abort_attach:
            unreg_p()
            cascade.detach_caller_slot(caller_slot_id)
