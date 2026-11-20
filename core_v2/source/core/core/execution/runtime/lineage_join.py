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

    def _cleanup_slot() -> None:
        unreg_w()
        det()

    slot_detachers[lp.slot_id] = _AttachedSlot(base_lin, lp.caller_views, lp.turn_cancel, _cleanup_slot)


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

    def _collect_connected(self, seen: set[str], out: list[FlightCascade]) -> None:
        if self.cascade_id in seen:
            return
        seen.add(self.cascade_id)
        out.append(self)
        for par in self._parents:
            par._collect_connected(seen, out)
        for _rel, ch in self._child_joins:
            ch._collect_connected(seen, out)

    def _unify_cond_with(self, child: FlightCascade) -> None:
        while True:
            c_par = self._graph_cond
            c_ch = child._graph_cond
            if c_par is c_ch:
                return
            first, second = (c_par, c_ch) if id(c_par) < id(c_ch) else (c_ch, c_par)
            with first, second:
                if self._graph_cond is not c_par or child._graph_cond is not c_ch:
                    continue
                comp: list[FlightCascade] = []
                child._collect_connected(set(), comp)
                for node in comp:
                    node._graph_cond = c_par
                c_ch.notify_all()
                c_par.notify_all()
                return

    def _has_ancestor_locked(self, cand_anc: FlightCascade, visited: set[str]) -> bool:
        if self is cand_anc:
            return True
        if self.cascade_id in visited:
            return False
        visited.add(self.cascade_id)
        return any(par._has_ancestor_locked(cand_anc, visited) for par in self._parents)

    def _reaches_descendant_locked(self, cand_desc: FlightCascade, visited: set[str]) -> bool:
        if self is cand_desc:
            return True
        if self.cascade_id in visited:
            return False
        visited.add(self.cascade_id)
        return any(ch._reaches_descendant_locked(cand_desc, visited) for _rel, ch in self._child_joins)

    def _all_reachable_own_done_locked(self, visited: set[str]) -> bool:
        if self.cascade_id in visited:
            return True
        visited.add(self.cascade_id)
        if not self._own_done:
            return False
        return all(ch._all_reachable_own_done_locked(visited) for _rel, ch in self._child_joins)

    def _collect_unstarted_locked(self, visited: set[str], to_spawn: list[FlightCascade]) -> None:
        if self.cascade_id in visited:
            return
        visited.add(self.cascade_id)
        if not self._own_done and not self._started:
            self._started = True
            to_spawn.append(self)
        for _rel, ch in self._child_joins:
            ch._collect_unstarted_locked(visited, to_spawn)

    def _ensure_reachable_drains_started(
        self,
        drain_fn: Optional[Callable[[FlightCascade], TurnExecutionReport]],
    ) -> None:
        if drain_fn is None:
            return
        to_spawn: list[FlightCascade] = []
        with self._locked_cond():
            self._collect_unstarted_locked(set(), to_spawn)
        for idx, node in enumerate(to_spawn):
            node._spawn_drain_thread_or_fail_rest(drain_fn, to_spawn[idx:])

    def _spawn_drain_thread_or_fail_rest(
        self,
        drain_fn: Callable[[FlightCascade], TurnExecutionReport],
        remaining_on_error: Sequence[FlightCascade],
    ) -> None:
        try:
            threading.Thread(
                target=self._run_drain_worker,
                args=(drain_fn,),
                name=f"yscb-cascade-{self.cascade_id[:8]}",
                daemon=True,
            ).start()
        except BaseException as exc:
            err_det = ErrorDetail(
                ErrorCode.BUSINESS_FAILURE,
                f"Cascade worker spawn failed: {safe_exception_summary(exc)}",
                source_task=self.emitter_task,
            )
            for rem_node in remaining_on_error:
                rem_node.mark_own_completed(fatal_error=err_det)
            raise

    def _collect_settled_cleanups_locked(self, visited: set[str], out_cleanups: list[Callable[[], None]]) -> None:
        if self.cascade_id in visited:
            return
        visited.add(self.cascade_id)
        for slot in self._slot_detachers.values():
            out_cleanups.append(slot.cleanup)
        self._slot_detachers.clear()
        out_cleanups.extend(self._parent_detachers.values())
        self._parent_detachers.clear()
        out_cleanups.extend(self._aux_unregs)
        self._aux_unregs.clear()
        out_cleanups.append(self.drain_cg.close_all)
        for _rel, ch in self._child_joins:
            ch._collect_settled_cleanups_locked(visited, out_cleanups)

    def _is_live_root_locked(self) -> bool:
        if self._slot_detachers or (self._started and not self._own_done):
            return True
        return not self._had_slots and not self._parents and not self._started and not self._own_done

    def _register_reverse_parent_edges_locked(self, extra_children: dict[str, list[FlightCascade]]) -> None:
        for par in self._parents:
            extra_children.setdefault(par.cascade_id, []).append(self)

    def _mark_live_reachable_locked(
        self,
        live_ids: set[str],
        extra_children: dict[str, list[FlightCascade]],
    ) -> None:
        if self.cascade_id in live_ids:
            return
        live_ids.add(self.cascade_id)
        for _rel, ch in self._child_joins:
            ch._mark_live_reachable_locked(live_ids, extra_children)
        for cand in extra_children.get(self.cascade_id, ()):
            cand._mark_live_reachable_locked(live_ids, extra_children)

    def _detach_parent_link_locked(self, parent: FlightCascade, out_cleanups: list[Callable[[], None]]) -> None:
        if parent in self._parents:
            self._parents.remove(parent)
        det = self._parent_detachers.pop(parent.cascade_id, None)
        if det is not None:
            out_cleanups.append(det)

    def _unlink_from_children_locked(self, out_cleanups: list[Callable[[], None]]) -> None:
        for _rel, ch in self._child_joins:
            ch._detach_parent_link_locked(self, out_cleanups)

    def _retire_if_unreachable_unstarted_locked(
        self,
        live_ids: set[str],
        out_cleanups: list[Callable[[], None]],
    ) -> None:
        if not self._own_done and not self._started and self.cascade_id not in live_ids:
            self._own_done = True
            self._unlink_from_children_locked(out_cleanups)

    def _finalize_if_settled_locked(self, visited_clean: set[str], out_cleanups: list[Callable[[], None]]) -> None:
        if not self._all_reachable_own_done_locked(set()):
            return
        self._collect_settled_cleanups_locked(visited_clean, out_cleanups)
        if not self._slot_detachers and not self._parents:
            self._unlink_from_children_locked(out_cleanups)

    def _sweep_component_cleanups_locked(self, out_cleanups: list[Callable[[], None]]) -> None:
        comp: list[FlightCascade] = []
        self._collect_connected(set(), comp)
        extra_children: dict[str, list[FlightCascade]] = {}
        for cand in comp:
            cand._register_reverse_parent_edges_locked(extra_children)
        live_ids: set[str] = set()
        for root in comp:
            if root._is_live_root_locked():
                root._mark_live_reachable_locked(live_ids, extra_children)
        for node in comp:
            node._retire_if_unreachable_unstarted_locked(live_ids, out_cleanups)
        visited_clean: set[str] = set()
        for node in comp:
            node._finalize_if_settled_locked(visited_clean, out_cleanups)

    def _collect_tree_outcomes_locked(
        self,
        visited: set[str],
        ev_diags: list[ErrorDetail],
        td_diags: list[ErrorDetail],
        fatal_out: list[Optional[ErrorDetail]],
    ) -> None:
        if self.cascade_id in visited:
            return
        visited.add(self.cascade_id)
        ev_diags.extend(self.imm_diagnostics)
        ev_diags.extend(self._own_event_diagnostics if self._own_done else self._live_diagnostics)
        td_diags.extend(self.seed_teardown_diagnostics)
        td_diags.extend(self._teardown_diagnostics)
        if fatal_out[0] is None and self._fatal_error is not None:
            fatal_out[0] = self._fatal_error
        for _rel_hops, ch in self._child_joins:
            ch._collect_tree_outcomes_locked(visited, ev_diags, td_diags, fatal_out)

    def _collect_emitted_hops_locked(self, visited: set[str], merged: dict[ScopedHop, Optional[str]]) -> None:
        if self.cascade_id in visited:
            return
        visited.add(self.cascade_id)
        for key, src in self._emitted_hops.items():
            _record_hop_if_missing(merged, key, src)
        for rel_hops, ch in self._child_joins:
            for eh in rel_hops:
                _record_hop_if_missing(merged, (eh.workspace_scope, eh.event_id), eh.source_task)
            ch._collect_emitted_hops_locked(visited, merged)

    def _collect_ancestor_views_locked(self, visited: set[str], out_views: dict[CoalesceCallerView, None]) -> None:
        if self.cascade_id in visited:
            return
        visited.add(self.cascade_id)
        for slot_info in self._slot_detachers.values():
            if not slot_info.turn_cancel.is_cancelled:
                for v in slot_info.caller_views:
                    out_views.setdefault(v, None)
        for par in self._parents:
            par._collect_ancestor_views_locked(visited, out_views)

    def _dfs_check_acyclic_locked(
        self,
        ancestors: CausalLineage,
        memo: set[tuple[str, frozenset[ScopedHop]]],
    ) -> None:
        anc_key = (self.cascade_id, frozenset(ancestors.scoped_hops()))
        if anc_key in memo:
            return
        memo.add(anc_key)
        anc_hops = ancestors.scoped_hops()
        for (hop_scope, hop_eid), hop_src in self._emitted_hops.items():
            if any(hop_conflicts(ah, hop_scope, hop_eid) for ah in anc_hops):
                chain_str = " -> ".join([*(str(e) for e in ancestors.chain), str(hop_eid)])
                raise EventCycleError(
                    f"Event causal cycle detected: {chain_str}",
                    source_task=hop_src or self.emitter_task,
                )
        for rel_hops, ch in self._child_joins:
            next_anc = _advance_emitted_hops_checked(ancestors, rel_hops, self.emitter_task)
            ch._dfs_check_acyclic_locked(next_anc, memo)

    def assert_acyclic(self, base_lineage: CausalLineage) -> None:
        memo: set[tuple[str, frozenset[ScopedHop]]] = set()
        with self._locked_cond():
            self._dfs_check_acyclic_locked(base_lineage, memo)

    def _try_check_acyclic_detail(self, base_lineage: CausalLineage) -> Optional[ErrorDetail]:
        try:
            self.assert_acyclic(base_lineage)
            return None
        except EventCycleError as exc:
            return exc.detail

    def _collect_ancestors_locked(self, visited: set[str], out_nodes: list[FlightCascade]) -> None:
        if self.cascade_id in visited:
            return
        visited.add(self.cascade_id)
        out_nodes.append(self)
        for par in self._parents:
            par._collect_ancestors_locked(visited, out_nodes)

    def _prune_own_cycled_slots_locked(self, to_detach: list[Callable[[], None]]) -> None:
        for sid, slot_info in list(self._slot_detachers.items()):
            if self._try_check_acyclic_detail(slot_info.base_lineage) is not None:
                self._had_slots = True
                self._slot_detachers.pop(sid, None)
                to_detach.append(slot_info.cleanup)

    def _prune_cycled_ancestors(self) -> None:
        to_detach: list[Callable[[], None]] = []
        with self._locked_cond() as cond:
            ancestors: list[FlightCascade] = []
            self._collect_ancestors_locked(set(), ancestors)
            for anc in ancestors:
                anc._prune_own_cycled_slots_locked(to_detach)
            if to_detach:
                self._sweep_component_cleanups_locked(to_detach)
                cond.notify_all()
        for det in to_detach:
            det()

    def snapshot_emitted_hops(self) -> tuple[EmittedEventHop, ...]:
        merged: dict[ScopedHop, Optional[str]] = {}
        with self._locked_cond():
            self._collect_emitted_hops_locked(set(), merged)
        return tuple(
            EmittedEventHop(workspace_scope=ws_s, event_id=eid, source_task=src)
            for (ws_s, eid), src in merged.items()
        )

    def snapshot_live_caller_views(self) -> tuple[CoalesceCallerView, ...]:
        views: dict[CoalesceCallerView, None] = {}
        with self._locked_cond():
            self._collect_ancestor_views_locked(set(), views)
        return tuple(views.keys())

    def add_cleanup(self, unreg: Callable[[], None]) -> None:
        cleanup_now = False
        with self._locked_cond():
            if self._all_reachable_own_done_locked(set()):
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
            settled = self._all_reachable_own_done_locked(set())
            for lp, unreg_w, det in zip(callers, wake_unregs, cg_dets):
                _store_or_discard_caller_slot(self._slot_detachers, unused_wakes, lp, unreg_w, det, settled)
            if not self._slot_detachers:
                self._sweep_component_cleanups_locked(unused_wakes)
        for fn in unused_wakes:
            fn()

    def detach_caller_slot(self, slot_id: int) -> None:
        if slot_id < 0:
            return
        cleanups: list[Callable[[], None]] = []
        with self._locked_cond():
            self._had_slots = True
            entry = self._slot_detachers.pop(slot_id, None)
            self._sweep_component_cleanups_locked(cleanups)
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
    ) -> tuple[bool, bool, Optional[_AttachedSlot]]:
        if transfer_slot_id >= 0:
            self._had_slots = True
        if parent._has_ancestor_locked(self, set()) or self._reaches_descendant_locked(parent, set()):
            old_slot = self._slot_detachers.pop(transfer_slot_id, None) if transfer_slot_id >= 0 else None
            self._sweep_component_cleanups_locked(cleanups)
            return (False, False, old_slot)
        if parent not in self._parents:
            self._parents.append(parent)
        if not self._all_reachable_own_done_locked(set()) and parent.cascade_id not in self._parent_detachers:
            return (True, True, None)
        old_slot = self._slot_detachers.pop(transfer_slot_id, None) if transfer_slot_id >= 0 else None
        self._sweep_component_cleanups_locked(cleanups)
        return (True, False, old_slot)

    def bind_parent_cascade(self, parent: FlightCascade, transfer_slot_id: int = -1) -> bool:
        if parent is self:
            if transfer_slot_id >= 0:
                self.detach_caller_slot(transfer_slot_id)
            return False
        parent._unify_cond_with(self)
        cleanups: list[Callable[[], None]] = []
        with self._locked_cond():
            accepted, need_attach, old_slot = self._try_prepare_parent_link_locked(parent, transfer_slot_id, cleanups)
        if not need_attach:
            if old_slot is not None:
                old_slot.cleanup()
            for fn in cleanups:
                fn()
            return accepted

        unreg_prio = parent.prio_handle.register_listener(
            lambda p: self.prio_handle.elevate_to_foreground() if p == ExecutionPriority.FOREGROUND else None
        )
        with self._locked_cond():
            if self._all_reachable_own_done_locked(set()) or parent.cascade_id in self._parent_detachers:
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
            self._sweep_component_cleanups_locked(cleanups)
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
            self._prune_cycled_ancestors()

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
        self._unify_cond_with(child)
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
            self._prune_cycled_ancestors()

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
            self._sweep_component_cleanups_locked(cleanups)
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
            self.assert_acyclic(base_lineage)
        except EventCycleError as exc:
            self.detach_caller_slot(slot_id)
            return self._snapshot_partial_with_fatal(exc.detail)

        self._ensure_reachable_drains_started(drain_fn)
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
            self._ensure_reachable_drains_started(drain_fn)
            detach_reason: Optional[str] = None
            cyc: Optional[ErrorDetail] = None
            with self._locked_cond() as cond:
                cyc = self._try_check_acyclic_detail(base_lineage)
                if cyc is not None:
                    detach_reason = "cycle"
                elif caller_cancel.is_cancelled:
                    detach_reason = "cancel"
                elif self._all_reachable_own_done_locked(set()):
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
            self._collect_tree_outcomes_locked(set(), ev_diags, td_diags, fatal_out)
        return CascadeOutcome(tuple(ev_diags), tuple(td_diags), fatal_detail)

    def collect_outcomes(self, slot_id: int, base_lineage: CausalLineage) -> CascadeOutcome:
        try:
            self.assert_acyclic(base_lineage)
        except EventCycleError as exc:
            self.detach_caller_slot(slot_id)
            return self._snapshot_partial_with_fatal(exc.detail)
        ev_diags: list[ErrorDetail] = []
        td_diags: list[ErrorDetail] = []
        fatal_out: list[Optional[ErrorDetail]] = [None]
        cleanups: list[Callable[[], None]] = []
        with self._locked_cond():
            self._collect_tree_outcomes_locked(set(), ev_diags, td_diags, fatal_out)
            if self._all_reachable_own_done_locked(set()):
                self._collect_settled_cleanups_locked(set(), cleanups)
        for fn in cleanups:
            fn()
        return CascadeOutcome(tuple(ev_diags), tuple(td_diags), fatal_out[0])

