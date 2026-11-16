"""Symmetric FlightCascade owning shared COALESCE event draining and O(V+E) causal cycle detection."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
import threading
import time
from typing import Callable, Iterator, Optional, Sequence
import uuid

from core.execution.event import CausalLineage, RawEventRecord, ScopedHop, hop_conflicts
from core.execution.lifecycle import TurnExecutionReport
from core.execution.runtime.contracts import CoalesceCallerView, ExecutionPriority
from core.execution.runtime.coordinator import LiveFlightParticipant, PriorityHandle, SharedCancelGroup, StepFlight
from core.execution.runtime.wire import EmittedEventHop
from core.foundation.errors import ErrorCode, ErrorDetail, EventCycleError, YscbError, safe_exception_summary
from core.foundation.observability import CancellationToken
from core.foundation.primitives import HostPath, TaskId


@dataclass(frozen=True, slots=True)
class ChildCascadeJoin:
    """Directed edge from an enclosing step or cascade to a nested FlightCascade."""

    rel_hops: tuple[EmittedEventHop, ...]
    cascade: FlightCascade
    slot_id: int = -1


@dataclass(frozen=True, slots=True)
class _AttachedSlot:
    base_lineage: CausalLineage
    caller_views: tuple[CoalesceCallerView, ...]
    turn_cancel: CancellationToken
    cleanup: Callable[[], None]


@dataclass(frozen=True, slots=True)
class _ParentLinkPrep:
    accepted: bool
    need_attach: bool
    old_slot: Optional[_AttachedSlot] = None


@dataclass(frozen=True, slots=True)
class CascadeOutcome:
    """Aggregated diagnostics and fatal error collected across a FlightCascade DAG."""

    event_diagnostics: tuple[ErrorDetail, ...] = ()
    teardown_diagnostics: tuple[ErrorDetail, ...] = ()
    fatal_error: Optional[ErrorDetail] = None


@dataclass(slots=True)
class StepEventCapture:
    """Captures relative nested events, immediate hops, diagnostics, invoked tasks, and child cascades inside COALESCE."""

    turn_id: str
    prefix_stack: tuple[tuple[HostPath, TaskId], ...]
    flight_cancel: CancellationToken
    flight: StepFlight[object]
    graph_cond: threading.Condition = field(default_factory=lambda: threading.Condition(threading.RLock()))
    deferred_events: list[RawEventRecord] = field(default_factory=list)
    imm_hops: dict[ScopedHop, EmittedEventHop] = field(default_factory=dict)
    imm_diagnostics: list[ErrorDetail] = field(default_factory=list)
    child_joins: list[ChildCascadeJoin] = field(default_factory=list)
    invoked_tasks: dict[tuple[HostPath, TaskId], None] = field(default_factory=dict)


def advance_hops_checked(
    base: CausalLineage,
    rel_hops: Sequence[ScopedHop],
    *,
    source_task: Optional[str] = None,
) -> CausalLineage:
    cur = base
    for ws_scope, eid in rel_hops:
        cur = cur.advance(eid, source_task=source_task, workspace_scope=ws_scope)
    return cur


def extract_emitted_hops_from_records(records: Sequence[RawEventRecord]) -> list[EmittedEventHop]:
    extracted: list[EmittedEventHop] = []
    for rec in records:
        rec_hops = rec.lineage.scoped_hops()
        for idx, (ws_s, eid) in enumerate(rec_hops):
            src = str(rec.emitter_task) if idx == len(rec_hops) - 1 else None
            extracted.append(EmittedEventHop(workspace_scope=ws_s, event_id=eid, source_task=src))
    return extracted


class FlightCascade:
    """Self-contained event cascade shared symmetrically across all non-cycled COALESCE step participants."""

    def __init__(
        self,
        *,
        seed_events: Sequence[RawEventRecord] = (),
        imm_hops: Sequence[EmittedEventHop] = (),
        imm_diagnostics: Sequence[ErrorDetail] = (),
        seed_teardown_diagnostics: Sequence[ErrorDetail] = (),
        initial_priority: ExecutionPriority = ExecutionPriority.BACKGROUND,
        graph_cond: Optional[threading.Condition] = None,
    ) -> None:
        self._graph_cond: threading.Condition = (
            graph_cond if graph_cond is not None else threading.Condition(threading.RLock())
        )
        self.cascade_id: str = uuid.uuid4().hex
        self.drain_cg: SharedCancelGroup = SharedCancelGroup()
        self.prio_handle: PriorityHandle = PriorityHandle(initial_priority)
        self.seed_events: tuple[RawEventRecord, ...] = tuple(seed_events)
        self.imm_diagnostics: tuple[ErrorDetail, ...] = tuple(imm_diagnostics)
        self.seed_teardown_diagnostics: tuple[ErrorDetail, ...] = tuple(seed_teardown_diagnostics)
        self.emitter_task: Optional[str] = (
            str(self.seed_events[0].emitter_task)
            if self.seed_events
            else (imm_hops[-1].source_task if imm_hops else None)
        )
        self._emitted_hops: dict[ScopedHop, Optional[str]] = {}
        self._child_joins: list[tuple[tuple[EmittedEventHop, ...], FlightCascade]] = []
        self._slot_detachers: dict[int, _AttachedSlot] = {}
        self._parent_detachers: dict[str, Callable[[], None]] = {}
        self._aux_unregs: list[Callable[[], None]] = []
        self._parents: list[FlightCascade] = []
        self._live_diagnostics: list[ErrorDetail] = []
        self._had_slots: bool = False
        self._started: bool = False
        self._own_done: bool = not bool(seed_events)
        self._own_event_diagnostics: tuple[ErrorDetail, ...] = ()
        self._teardown_diagnostics: tuple[ErrorDetail, ...] = ()
        self._fatal_error: Optional[ErrorDetail] = None
        for eh in (*imm_hops, *extract_emitted_hops_from_records(seed_events)):
            key = (eh.workspace_scope, eh.event_id)
            if key not in self._emitted_hops or (self._emitted_hops[key] is None and eh.source_task is not None):
                self._emitted_hops[key] = eh.source_task

    @contextlib.contextmanager
    def _locked_cond(self) -> Iterator[threading.Condition]:
        while True:
            cond = self._graph_cond
            with cond:
                if self._graph_cond is cond:
                    yield cond
                    return

    def snapshot_emitted_hops(self) -> tuple[EmittedEventHop, ...]:
        merged: dict[ScopedHop, Optional[str]] = {}
        with self._locked_cond():
            _collect_cascade_emitted_hops_locked(self, set(), merged)
        return tuple(
            EmittedEventHop(workspace_scope=ws_s, event_id=eid, source_task=src)
            for (ws_s, eid), src in merged.items()
        )

    def snapshot_live_caller_views(self) -> tuple[CoalesceCallerView, ...]:
        views: dict[CoalesceCallerView, None] = {}
        with self._locked_cond():
            _collect_ancestor_caller_views_locked(self, set(), views)
        return tuple(views.keys())

    def add_cleanup(self, unreg: Callable[[], None]) -> None:
        cleanup_now = False
        with self._locked_cond():
            if _all_reachable_own_done_locked(self, set()):
                cleanup_now = True
            else:
                self._aux_unregs.append(unreg)
        if cleanup_now:
            unreg()

    def register_caller_slots(
        self,
        callers: Sequence[LiveFlightParticipant],
        priority: ExecutionPriority,
    ) -> None:
        if not callers:
            return
        if priority == ExecutionPriority.FOREGROUND:
            self.prio_handle.elevate_to_foreground()
        wake_unregs = [lp.turn_cancel.register_callback(lambda _p, _r: self._notify_graph()) for lp in callers]
        cg_dets = self.drain_cg.add_participants([lp.turn_cancel for lp in callers])
        unused_wakes: list[Callable[[], None]] = []
        with self._locked_cond():
            self._had_slots = True
            settled = _all_reachable_own_done_locked(self, set())
            for lp, unreg_w, det in zip(callers, wake_unregs, cg_dets):
                _store_or_discard_caller_slot(self._slot_detachers, unused_wakes, lp, unreg_w, det, settled)
            if not self._slot_detachers:
                _sweep_component_cleanups_locked(self, unused_wakes)
        for fn in unused_wakes:
            fn()

    def detach_caller_slot(self, slot_id: int) -> None:
        if slot_id < 0:
            return
        cleanups: list[Callable[[], None]] = []
        with self._locked_cond():
            self._had_slots = True
            entry = self._slot_detachers.pop(slot_id, None)
            _sweep_component_cleanups_locked(self, cleanups)
        if entry is not None:
            entry.cleanup()
            self._notify_graph()
        for fn in cleanups:
            fn()

    def _try_prepare_parent_link_locked(
        self,
        parent: FlightCascade,
        transfer_slot_id: int,
        cleanups: list[Callable[[], None]],
    ) -> _ParentLinkPrep:
        if transfer_slot_id >= 0:
            self._had_slots = True
        if _is_ancestor_cascade_locked(self, parent, set()) or _reaches_descendant_locked(self, parent, set()):
            old_slot = self._slot_detachers.pop(transfer_slot_id, None) if transfer_slot_id >= 0 else None
            _sweep_component_cleanups_locked(self, cleanups)
            return _ParentLinkPrep(False, False, old_slot)
        if parent not in self._parents:
            self._parents.append(parent)
        if not _all_reachable_own_done_locked(self, set()) and parent.cascade_id not in self._parent_detachers:
            return _ParentLinkPrep(True, True, None)
        old_slot = self._slot_detachers.pop(transfer_slot_id, None) if transfer_slot_id >= 0 else None
        _sweep_component_cleanups_locked(self, cleanups)
        return _ParentLinkPrep(True, False, old_slot)

    def bind_parent_cascade(self, parent: FlightCascade, transfer_slot_id: int = -1) -> bool:
        if parent is self:
            if transfer_slot_id >= 0:
                self.detach_caller_slot(transfer_slot_id)
            return False
        _unify_cascade_cond(parent, self)
        cleanups: list[Callable[[], None]] = []
        with self._locked_cond():
            prep = self._try_prepare_parent_link_locked(parent, transfer_slot_id, cleanups)
        old_slot = prep.old_slot
        if not prep.need_attach:
            if old_slot is not None:
                old_slot.cleanup()
            for fn in cleanups:
                fn()
            return prep.accepted

        unreg_prio = parent.prio_handle.register_listener(
            lambda p: self.prio_handle.elevate_to_foreground() if p == ExecutionPriority.FOREGROUND else None
        )
        with self._locked_cond():
            if _all_reachable_own_done_locked(self, set()) or parent.cascade_id in self._parent_detachers:
                cleanups.append(unreg_prio)
            else:
                det = self.drain_cg.try_add_participant(parent.drain_cg.host_token)
                if det is not None:
                    unreg_wake = parent.drain_cg.host_token.register_callback(lambda _p, _r: self._notify_graph())
                    self._parent_detachers[parent.cascade_id] = _make_lifo_parent_detacher(unreg_wake, det, unreg_prio)
                else:
                    cleanups.append(unreg_prio)
            if transfer_slot_id >= 0:
                old_slot = self._slot_detachers.pop(transfer_slot_id, None)
            _sweep_component_cleanups_locked(self, cleanups)
        if old_slot is not None:
            old_slot.cleanup()
        for fn in cleanups:
            fn()
        return True

    def record_emitted_hops(self, hops: Sequence[EmittedEventHop]) -> None:
        if not hops:
            return
        changed = False
        with self._locked_cond() as cond:
            for eh in hops:
                key = (eh.workspace_scope, eh.event_id)
                if key not in self._emitted_hops:
                    self._emitted_hops[key] = eh.source_task
                    changed = True
                elif self._emitted_hops[key] is None and eh.source_task is not None:
                    self._emitted_hops[key] = eh.source_task
            if changed:
                cond.notify_all()
        if changed:
            _prune_cycled_ancestors(self)

    def record_live_diagnostic(self, detail: ErrorDetail) -> None:
        with self._locked_cond() as cond:
            self._live_diagnostics.append(detail)
            cond.notify_all()

    def add_child_join(
        self,
        call_rel_hops: Sequence[EmittedEventHop | ScopedHop],
        child: FlightCascade,
        transfer_slot_id: int = -1,
    ) -> None:
        """Record causal child hop edge while keeping _parents wait-forest strictly acyclic."""
        if child is self:
            if transfer_slot_id >= 0:
                self.detach_caller_slot(transfer_slot_id)
            return
        _unify_cascade_cond(self, child)
        norm_hops = tuple(
            h if isinstance(h, EmittedEventHop) else EmittedEventHop(workspace_scope=h[0], event_id=h[1])
            for h in call_rel_hops
        )
        added = False
        with self._locked_cond() as cond:
            edge = (norm_hops, child)
            if edge not in self._child_joins:
                self._child_joins.append(edge)
                added = True
                cond.notify_all()
        _ = child.bind_parent_cascade(self, transfer_slot_id=transfer_slot_id)
        if added:
            _prune_cycled_ancestors(self)

    def mark_own_completed(
        self,
        *,
        event_diagnostics: Sequence[ErrorDetail] = (),
        teardown_diagnostics: Sequence[ErrorDetail] = (),
        fatal_error: Optional[ErrorDetail] = None,
    ) -> None:
        cleanups: list[Callable[[], None]] = []
        with self._locked_cond() as cond:
            self._own_event_diagnostics = tuple(event_diagnostics)
            self._teardown_diagnostics = tuple(teardown_diagnostics)
            self._fatal_error = fatal_error
            self._own_done = True
            _sweep_component_cleanups_locked(self, cleanups)
            cond.notify_all()
        for fn in cleanups:
            fn()

    def _notify_graph(self) -> None:
        with self._locked_cond() as cond:
            cond.notify_all()

    def activate_and_await(
        self,
        slot_id: int,
        base_lineage: CausalLineage,
        caller_cancel: CancellationToken,
        deadline: Optional[float],
        drain_fn: Optional[Callable[[FlightCascade], TurnExecutionReport]],
    ) -> CascadeOutcome:
        try:
            check_cascade_acyclic(base_lineage, self)
        except EventCycleError as exc:
            self.detach_caller_slot(slot_id)
            return self._snapshot_partial_with_fatal(exc.detail)

        _ensure_reachable_drains_started(self, drain_fn)
        cyc_err = self._wait_until_resolved(slot_id, base_lineage, caller_cancel, deadline, drain_fn)
        if cyc_err is not None:
            return self._snapshot_partial_with_fatal(cyc_err)
        return self.collect_outcomes(slot_id, base_lineage)

    def _run_drain_worker(self, drain_fn: Callable[[FlightCascade], TurnExecutionReport]) -> None:
        try:
            rep = drain_fn(self)
            self.mark_own_completed(
                event_diagnostics=rep.event_diagnostics,
                teardown_diagnostics=rep.teardown_diagnostics,
                fatal_error=rep.fatal_event_error,
            )
        except YscbError as exc:
            self.mark_own_completed(fatal_error=exc.detail)
        except (Exception, SystemExit, GeneratorExit) as exc:
            self.mark_own_completed(
                fatal_error=ErrorDetail(
                    ErrorCode.BUSINESS_FAILURE,
                    f"Cascade drain error: {safe_exception_summary(exc)}",
                    source_task=self.emitter_task,
                )
            )
        except BaseException as base_exc:
            self.mark_own_completed(
                fatal_error=ErrorDetail(
                    ErrorCode.TASK_CANCELLED,
                    f"Cascade drain interrupted: {type(base_exc).__name__}",
                    source_task=self.emitter_task,
                )
            )
            raise

    def _wait_until_resolved(
        self,
        slot_id: int,
        base_lineage: CausalLineage,
        caller_cancel: CancellationToken,
        deadline: Optional[float],
        drain_fn: Optional[Callable[[FlightCascade], TurnExecutionReport]],
    ) -> Optional[ErrorDetail]:
        unreg = caller_cancel.register_callback(lambda _p, _r: self._notify_graph())
        try:
            return self._poll_graph_until_settled(slot_id, base_lineage, caller_cancel, deadline, drain_fn)
        finally:
            unreg()

    def _poll_graph_until_settled(
        self,
        slot_id: int,
        base_lineage: CausalLineage,
        caller_cancel: CancellationToken,
        deadline: Optional[float],
        drain_fn: Optional[Callable[[FlightCascade], TurnExecutionReport]],
    ) -> Optional[ErrorDetail]:
        while True:
            _ensure_reachable_drains_started(self, drain_fn)
            detach_reason: Optional[str] = None
            cyc: Optional[ErrorDetail] = None
            with self._locked_cond() as cond:
                cyc = _try_check_acyclic_detail(base_lineage, self)
                if cyc is not None:
                    detach_reason = "cycle"
                elif caller_cancel.is_cancelled:
                    detach_reason = "cancel"
                elif _all_reachable_own_done_locked(self, set()):
                    return None
                elif deadline is not None and time.monotonic() >= deadline:
                    detach_reason = "timeout"
                else:
                    wait_sec = 0.03 if deadline is None else min(0.03, max(0.001, deadline - time.monotonic()))
                    cond.wait(timeout=wait_sec)
            if detach_reason is not None:
                self.detach_caller_slot(slot_id)
                if detach_reason == "cycle":
                    return cyc
                if detach_reason == "cancel":
                    caller_cancel.raise_if_cancelled()
                raise YscbError(ErrorCode.TASK_TIMEOUT, "Timed out waiting on shared FlightCascade.")

    def _snapshot_partial_with_fatal(self, fatal_detail: ErrorDetail) -> CascadeOutcome:
        ev_diags: list[ErrorDetail] = []
        td_diags: list[ErrorDetail] = []
        fatal_out: list[Optional[ErrorDetail]] = [fatal_detail]
        with self._locked_cond():
            _collect_cascade_tree_locked(self, set(), ev_diags, td_diags, fatal_out)
        return CascadeOutcome(tuple(ev_diags), tuple(td_diags), fatal_detail)

    def collect_outcomes(self, slot_id: int, base_lineage: CausalLineage) -> CascadeOutcome:
        try:
            check_cascade_acyclic(base_lineage, self)
        except EventCycleError as exc:
            self.detach_caller_slot(slot_id)
            return self._snapshot_partial_with_fatal(exc.detail)
        ev_diags: list[ErrorDetail] = []
        td_diags: list[ErrorDetail] = []
        fatal_out: list[Optional[ErrorDetail]] = [None]
        cleanups: list[Callable[[], None]] = []
        with self._locked_cond():
            _collect_cascade_tree_locked(self, set(), ev_diags, td_diags, fatal_out)
            if _all_reachable_own_done_locked(self, set()):
                _collect_settled_cleanups_locked(self, set(), cleanups)
        for fn in cleanups:
            fn()
        return CascadeOutcome(tuple(ev_diags), tuple(td_diags), fatal_out[0])


def _collect_connected_cascades(node: FlightCascade, seen: set[str], out: list[FlightCascade]) -> None:
    if node.cascade_id in seen:
        return
    seen.add(node.cascade_id)
    out.append(node)
    for par in node._parents:
        _collect_connected_cascades(par, seen, out)
    for _rel, ch in node._child_joins:
        _collect_connected_cascades(ch, seen, out)


def _try_unify_cascade_pair(
    parent: FlightCascade,
    child: FlightCascade,
    c_par: threading.Condition,
    c_ch: threading.Condition,
) -> bool:
    first, second = (c_par, c_ch) if id(c_par) < id(c_ch) else (c_ch, c_par)
    with first, second:
        if parent._graph_cond is not c_par or child._graph_cond is not c_ch:
            return False
        comp: list[FlightCascade] = []
        _collect_connected_cascades(child, set(), comp)
        for n in comp:
            n._graph_cond = c_par
        c_ch.notify_all()
        c_par.notify_all()
        return True


def _unify_cascade_cond(parent: FlightCascade, child: FlightCascade) -> None:
    while True:
        c_par, c_ch = parent._graph_cond, child._graph_cond
        if c_par is c_ch or _try_unify_cascade_pair(parent, child, c_par, c_ch):
            return


def _is_ancestor_cascade_locked(cand_anc: FlightCascade, node: FlightCascade, visited: set[str]) -> bool:
    if node is cand_anc:
        return True
    if node.cascade_id in visited:
        return False
    visited.add(node.cascade_id)
    return any(_is_ancestor_cascade_locked(cand_anc, par, visited) for par in node._parents)


def _reaches_descendant_locked(node: FlightCascade, cand_desc: FlightCascade, visited: set[str]) -> bool:
    if node is cand_desc:
        return True
    if node.cascade_id in visited:
        return False
    visited.add(node.cascade_id)
    return any(_reaches_descendant_locked(child, cand_desc, visited) for _rel, child in node._child_joins)


def _make_lifo_parent_detacher(
    unreg_wake: Callable[[], None],
    det: Callable[[], None],
    unreg_prio: Callable[[], None],
) -> Callable[[], None]:
    def _detach_parent() -> None:
        unreg_wake()
        det()
        unreg_prio()

    return _detach_parent


def _make_slot_cleanup(unreg_w: Callable[[], None], det: Callable[[], None]) -> Callable[[], None]:
    def _cleanup_slot() -> None:
        unreg_w()
        det()

    return _cleanup_slot


def _store_or_discard_caller_slot(
    slot_detachers: dict[int, _AttachedSlot],
    unused: list[Callable[[], None]],
    lp: LiveFlightParticipant,
    unreg_w: Callable[[], None],
    det: Optional[Callable[[], None]],
    settled: bool,
) -> None:
    if det is None or settled:
        unused.append(unreg_w)
        if det is not None:
            unused.append(det)
        return
    base_lin = CausalLineage(
        chain=tuple(eid for _s, eid in lp.caller_hops),
        scopes=tuple(s for s, _eid in lp.caller_hops),
    )
    slot_detachers[lp.slot_id] = _AttachedSlot(base_lin, lp.caller_views, lp.turn_cancel, _make_slot_cleanup(unreg_w, det))


def _try_check_acyclic_detail(base_lineage: CausalLineage, cascade: FlightCascade) -> Optional[ErrorDetail]:
    try:
        check_cascade_acyclic(base_lineage, cascade)
        return None
    except EventCycleError as exc:
        return exc.detail


def _ensure_reachable_drains_started(
    root: FlightCascade,
    drain_fn: Optional[Callable[[FlightCascade], TurnExecutionReport]],
) -> None:
    if drain_fn is None:
        return
    to_spawn: list[FlightCascade] = []
    with root._locked_cond():
        _collect_unstarted_nodes_locked(root, set(), to_spawn)
    for idx, node in enumerate(to_spawn):
        try:
            threading.Thread(
                target=node._run_drain_worker,
                args=(drain_fn,),
                name=f"yscb-cascade-{node.cascade_id[:8]}",
                daemon=True,
            ).start()
        except BaseException as exc:
            err_det = ErrorDetail(
                ErrorCode.BUSINESS_FAILURE,
                f"Cascade worker spawn failed: {safe_exception_summary(exc)}",
                source_task=node.emitter_task,
            )
            for rem_node in to_spawn[idx:]:
                rem_node.mark_own_completed(fatal_error=err_det)
            raise


def _collect_unstarted_nodes_locked(
    node: FlightCascade,
    visited: set[str],
    to_spawn: list[FlightCascade],
) -> None:
    if node.cascade_id in visited:
        return
    visited.add(node.cascade_id)
    if not node._own_done and not node._started:
        node._started = True
        to_spawn.append(node)
    for _rel, child in node._child_joins:
        _collect_unstarted_nodes_locked(child, visited, to_spawn)


def _all_reachable_own_done_locked(node: FlightCascade, visited: set[str]) -> bool:
    if node.cascade_id in visited:
        return True
    visited.add(node.cascade_id)
    if not node._own_done:
        return False
    return all(_all_reachable_own_done_locked(child, visited) for _rel, child in node._child_joins)


def _collect_settled_cleanups_locked(
    node: FlightCascade,
    visited: set[str],
    out_cleanups: list[Callable[[], None]],
) -> None:
    if node.cascade_id in visited:
        return
    visited.add(node.cascade_id)
    for slot in node._slot_detachers.values():
        out_cleanups.append(slot.cleanup)
    node._slot_detachers.clear()
    out_cleanups.extend(node._parent_detachers.values())
    node._parent_detachers.clear()
    out_cleanups.extend(node._aux_unregs)
    node._aux_unregs.clear()
    out_cleanups.append(node.drain_cg.close_all)
    for _rel, child in node._child_joins:
        _collect_settled_cleanups_locked(child, visited, out_cleanups)


def _is_live_cascade_root_locked(node: FlightCascade) -> bool:
    if node._slot_detachers or (node._started and not node._own_done):
        return True
    return not node._had_slots and not node._parents and not node._started and not node._own_done


def _mark_live_reachable_locked(
    node: FlightCascade,
    live_ids: set[str],
    extra_children: dict[str, list[FlightCascade]],
) -> None:
    if node.cascade_id in live_ids:
        return
    live_ids.add(node.cascade_id)
    for _rel, ch in node._child_joins:
        _mark_live_reachable_locked(ch, live_ids, extra_children)
    for cand in extra_children.get(node.cascade_id, ()):
        _mark_live_reachable_locked(cand, live_ids, extra_children)


def _unlink_parent_from_children_locked(node: FlightCascade, out_cleanups: list[Callable[[], None]]) -> None:
    for _rel, ch in node._child_joins:
        if node in ch._parents:
            ch._parents.remove(node)
        det = ch._parent_detachers.pop(node.cascade_id, None)
        if det is not None:
            out_cleanups.append(det)


def _sweep_component_cleanups_locked(anchor: FlightCascade, out_cleanups: list[Callable[[], None]]) -> None:
    comp: list[FlightCascade] = []
    _collect_connected_cascades(anchor, set(), comp)
    extra_children: dict[str, list[FlightCascade]] = {}
    for cand in comp:
        for par in cand._parents:
            extra_children.setdefault(par.cascade_id, []).append(cand)
    live_ids: set[str] = set()
    for root in comp:
        if _is_live_cascade_root_locked(root):
            _mark_live_reachable_locked(root, live_ids, extra_children)
    for node in comp:
        if not node._own_done and not node._started and node.cascade_id not in live_ids:
            node._own_done = True
            _unlink_parent_from_children_locked(node, out_cleanups)
    visited_clean: set[str] = set()
    for node in comp:
        if _all_reachable_own_done_locked(node, set()):
            _collect_settled_cleanups_locked(node, visited_clean, out_cleanups)
            if not node._slot_detachers and not node._parents:
                _unlink_parent_from_children_locked(node, out_cleanups)


def _collect_cascade_tree_locked(
    node: FlightCascade,
    visited: set[str],
    ev_diags: list[ErrorDetail],
    td_diags: list[ErrorDetail],
    fatal_out: list[Optional[ErrorDetail]],
) -> None:
    if node.cascade_id in visited:
        return
    visited.add(node.cascade_id)
    ev_diags.extend(node.imm_diagnostics)
    ev_diags.extend(node._own_event_diagnostics if node._own_done else node._live_diagnostics)
    td_diags.extend(node.seed_teardown_diagnostics)
    td_diags.extend(node._teardown_diagnostics)
    if fatal_out[0] is None and node._fatal_error is not None:
        fatal_out[0] = node._fatal_error
    for _rel_hops, child in node._child_joins:
        _collect_cascade_tree_locked(child, visited, ev_diags, td_diags, fatal_out)


def check_cascade_acyclic(base_lineage: CausalLineage, root_cascade: FlightCascade) -> None:
    """Verify exact O(V+E) causal acyclicity across a FlightCascade and all reachable child cascade joins."""
    memo: set[tuple[str, frozenset[ScopedHop]]] = set()
    with root_cascade._locked_cond():
        _dfs_check_acyclic_locked(base_lineage, root_cascade, memo)


def _advance_emitted_hops_checked(
    base: CausalLineage,
    rel_hops: Sequence[EmittedEventHop],
    fallback_task: Optional[str],
) -> CausalLineage:
    cur = base
    for eh in rel_hops:
        cur = cur.advance(eh.event_id, source_task=eh.source_task or fallback_task, workspace_scope=eh.workspace_scope)
    return cur


def _record_hop_if_missing(merged: dict[ScopedHop, Optional[str]], key: ScopedHop, src: Optional[str]) -> None:
    if key not in merged or (merged[key] is None and src is not None):
        merged[key] = src


def _collect_cascade_emitted_hops_locked(
    node: FlightCascade,
    visited: set[str],
    merged: dict[ScopedHop, Optional[str]],
) -> None:
    if node.cascade_id in visited:
        return
    visited.add(node.cascade_id)
    for key, src in node._emitted_hops.items():
        _record_hop_if_missing(merged, key, src)
    for rel_hops, child in node._child_joins:
        for eh in rel_hops:
            _record_hop_if_missing(merged, (eh.workspace_scope, eh.event_id), eh.source_task)
        _collect_cascade_emitted_hops_locked(child, visited, merged)


def _append_slot_views(slot_info: _AttachedSlot, out_views: dict[CoalesceCallerView, None]) -> None:
    if slot_info.turn_cancel.is_cancelled:
        return
    for v in slot_info.caller_views:
        out_views.setdefault(v, None)


def _collect_ancestor_caller_views_locked(
    node: FlightCascade,
    visited: set[str],
    out_views: dict[CoalesceCallerView, None],
) -> None:
    if node.cascade_id in visited:
        return
    visited.add(node.cascade_id)
    for slot_info in node._slot_detachers.values():
        _append_slot_views(slot_info, out_views)
    for par in node._parents:
        _collect_ancestor_caller_views_locked(par, visited, out_views)


def _dfs_check_acyclic_locked(
    ancestors: CausalLineage,
    cascade: FlightCascade,
    memo: set[tuple[str, frozenset[ScopedHop]]],
) -> None:
    anc_key = (cascade.cascade_id, frozenset(ancestors.scoped_hops()))
    if anc_key in memo:
        return
    memo.add(anc_key)
    anc_hops = ancestors.scoped_hops()
    for (hop_scope, hop_eid), hop_src in cascade._emitted_hops.items():
        if any(hop_conflicts(ah, hop_scope, hop_eid) for ah in anc_hops):
            chain_str = " -> ".join([*(str(e) for e in ancestors.chain), str(hop_eid)])
            raise EventCycleError(
                f"Event causal cycle detected: {chain_str}",
                source_task=hop_src or cascade.emitter_task,
            )
    for rel_hops, child in cascade._child_joins:
        next_anc = _advance_emitted_hops_checked(ancestors, rel_hops, cascade.emitter_task)
        _dfs_check_acyclic_locked(next_anc, child, memo)


def _collect_ancestor_cascades_locked(
    node: FlightCascade,
    visited: set[str],
    out_nodes: list[FlightCascade],
) -> None:
    if node.cascade_id in visited:
        return
    visited.add(node.cascade_id)
    out_nodes.append(node)
    for par in node._parents:
        _collect_ancestor_cascades_locked(par, visited, out_nodes)


def _prune_single_cascade_slots_locked(anc: FlightCascade, to_detach: list[Callable[[], None]]) -> None:
    for sid, slot_info in list(anc._slot_detachers.items()):
        if _try_check_acyclic_detail(slot_info.base_lineage, anc) is not None:
            anc._had_slots = True
            anc._slot_detachers.pop(sid, None)
            to_detach.append(slot_info.cleanup)


def _prune_cycled_ancestors(start_node: FlightCascade) -> None:
    to_detach: list[Callable[[], None]] = []
    with start_node._locked_cond() as cond:
        ancestors: list[FlightCascade] = []
        _collect_ancestor_cascades_locked(start_node, set(), ancestors)
        for anc in ancestors:
            _prune_single_cascade_slots_locked(anc, to_detach)
        if to_detach:
            _sweep_component_cleanups_locked(start_node, to_detach)
            cond.notify_all()
    for det in to_detach:
        det()
