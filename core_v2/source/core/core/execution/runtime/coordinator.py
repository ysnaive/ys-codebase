"""ResourceCoordinator, StepFlight, PriorityHandle, and SharedCancelGroup for single-point step coordination."""

from __future__ import annotations

from collections import OrderedDict
import contextlib
from dataclasses import dataclass, field, replace
import hashlib
import os
import re
import threading
import time
from typing import Callable, Generic, Iterator, Mapping, Optional, Sequence, TypeVar
import uuid
import weakref

from core.execution.event import ScopedHop, hop_conflicts
from core.execution.rpc import FrameKind, query_daemon_control
from core.execution.runtime.contracts import DEFAULT_CACHE_DIRNAME, LOCKS_SUBDIR, CoalesceCallerView, ConcurrencyMode, ExecutionPriority
from core.filesystem.fs import (
    atomic_write_json,
    read_json_dict,
    CrossProcessLockPaths,
    FileLock,
    acquire_verified_cross_proc_pin,
    read_live_owner_dict,
    resolve_contained_subpath,
    silent_unlink,
    unlink_owner_under_pin,
    write_cross_proc_owner_json,
)
from core.foundation.codec import DataclassCodec
from core.foundation.errors import ErrorCode, ErrorDetail, TaskCancelledException, YscbError
from core.foundation.observability import CancellationToken, ms_to_safe_sec
from core.foundation.primitives import decrement_ref_count, invoke_observer_safely, require_non_none, HostPath, JsonObject, TaskId
from core.foundation.proc import get_process_start_tag, is_process_alive

TVal = TypeVar("TVal")
TResult = TypeVar("TResult")
TBundle = TypeVar("TBundle")

_SAFE_LOCK_PREFIX_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _build_resource_lock_stem(resource_key: str) -> str:
    prefix = _SAFE_LOCK_PREFIX_RE.sub("_", resource_key).strip("_")[:24] or "key"
    digest = hashlib.sha256(resource_key.encode("utf-8")).hexdigest()[:12]
    return f"res_{prefix}_{digest}"


class PriorityHandle:
    """Observable thread-safe effective priority holder supporting monotonic elevation to FOREGROUND."""

    def __init__(self, initial: ExecutionPriority) -> None:
        self._lock = threading.Lock()
        self._current = initial
        self._next_id = 0
        self._listeners: dict[int, Callable[[ExecutionPriority], None]] = {}

    @property
    def current(self) -> ExecutionPriority:
        with self._lock:
            return self._current

    def __call__(self) -> ExecutionPriority:
        return self.current

    def elevate_to_foreground(self) -> None:
        cbs: list[Callable[[ExecutionPriority], None]] = []
        with self._lock:
            if self._current == ExecutionPriority.FOREGROUND:
                return
            self._current = ExecutionPriority.FOREGROUND
            cbs = list(self._listeners.values())
        for cb in cbs:
            invoke_observer_safely(lambda fn=cb: fn(ExecutionPriority.FOREGROUND))

    def register_listener(self, cb: Callable[[ExecutionPriority], None]) -> Callable[[], None]:
        fire_now = False
        lid = -1
        with self._lock:
            if self._current == ExecutionPriority.FOREGROUND:
                fire_now = True
            else:
                lid = self._next_id
                self._next_id += 1
                self._listeners[lid] = cb
        if fire_now:
            invoke_observer_safely(lambda: cb(ExecutionPriority.FOREGROUND))
            return lambda: None

        def _unregister() -> None:
            with self._lock:
                self._listeners.pop(lid, None)

        return _unregister


class SharedCancelGroup:
    """Shared cancellation hub cancelling host_token ONLY when every active participant cancels or detaches."""

    def __init__(self) -> None:
        self.host_token = CancellationToken()
        self._lock = threading.Lock()
        self._closed = False
        self._next_id = 0
        self._active_ids: set[int] = set()
        self._unregs: dict[int, Callable[[], None]] = {}

    def add_participants(
        self,
        caller_tokens: Sequence[CancellationToken],
    ) -> tuple[Optional[Callable[[], None]], ...]:
        if not caller_tokens:
            return ()
        pids: list[int] = []
        with self._lock:
            if self._closed or self.host_token.is_cancelled:
                return tuple(None for _ in caller_tokens)
            for _tok in caller_tokens:
                pid = self._next_id
                self._next_id += 1
                self._active_ids.add(pid)
                pids.append(pid)
        return tuple(self._bind_participant_callback(pid, tok) for pid, tok in zip(pids, caller_tokens))

    def try_add_participant(self, caller_token: CancellationToken) -> Optional[Callable[[], None]]:
        return self.add_participants((caller_token,))[0]

    def _bind_participant_callback(self, pid: int, caller_token: CancellationToken) -> Callable[[], None]:
        def _on_caller_cancelled(preempted: bool, reason: str) -> None:
            should_cancel_host = False
            with self._lock:
                self._active_ids.discard(pid)
                if not self._active_ids and not self._closed:
                    self._closed = True
                    should_cancel_host = True
            if should_cancel_host:
                self.host_token.cancel(preempted=preempted, reason=reason)
                self.close_all()

        unreg = caller_token.register_callback(_on_caller_cancelled)
        with self._lock:
            if self._closed or pid not in self._active_ids:
                should_unreg = True
            else:
                self._unregs[pid] = unreg
                should_unreg = False
        if should_unreg:
            unreg()

        def _detach() -> None:
            should_cancel_host = False
            with self._lock:
                u = self._unregs.pop(pid, None)
                self._active_ids.discard(pid)
                if not self._active_ids and not self._closed:
                    self._closed = True
                    should_cancel_host = True
            if u is not None:
                u()
            if should_cancel_host:
                self.host_token.cancel(reason="all shared participants detached")
                self.close_all()

        return _detach

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active_ids)

    def close_all(self) -> None:
        with self._lock:
            self._closed = True
            unregs = list(self._unregs.values())
            self._unregs.clear()
            self._active_ids.clear()
        for u in unregs:
            u()


@dataclass(frozen=True, slots=True)
class FlightCallerRegistration:
    """Caller registration metadata attached to a symmetric StepFlight."""

    caller_turn_id: str
    call_tree_id: str
    caller_stack: tuple[tuple[HostPath, TaskId], ...]
    caller_hops: tuple[ScopedHop, ...]
    step_cancel: CancellationToken
    turn_cancel: CancellationToken
    enclosing_flights: tuple[StepFlight[object], ...] = ()
    inherited_views: tuple[CoalesceCallerView, ...] = ()
    coalesce_flights: tuple[str, ...] = ()
    turn_entry_stack: tuple[tuple[HostPath, TaskId], ...] = ()
    in_event_chain: bool = False
    deadline: Optional[float] = None


@dataclass(frozen=True, slots=True)
class LiveFlightParticipant:
    """Snapshot of a non-cancelled StepFlight participant pre-registered onto FlightCascade."""

    slot_id: int
    turn_cancel: CancellationToken
    caller_hops: tuple[ScopedHop, ...] = ()
    caller_views: tuple[CoalesceCallerView, ...] = ()


@dataclass(frozen=True, slots=True)
class HolderIdentity:
    turn_id: str = ""
    tree_id: str = ""
    flight_id: str = ""
    stack: tuple[tuple[HostPath, TaskId], ...] = ()
    alt_owners: tuple[HolderIdentity, ...] = ()


def _merge_caller_view(
    base: CoalesceCallerView,
    stack_frames: tuple[tuple[HostPath, TaskId], ...],
    hops: tuple[ScopedHop, ...],
    flights: Sequence[str],
    in_event: bool,
) -> CoalesceCallerView:
    extra_frames = tuple(f for f in stack_frames if f not in base.call_stack)
    extra_hops = tuple(h for h in hops if h not in base.caller_hops)
    extra_flights = tuple(fid for fid in flights if fid and fid not in base.flight_ids)
    return CoalesceCallerView(
        turn_id=base.turn_id,
        call_tree_id=base.call_tree_id,
        call_stack=(*base.call_stack, *extra_frames),
        caller_hops=(*base.caller_hops, *extra_hops),
        flight_ids=(*base.flight_ids, *extra_flights),
        in_event_chain=(base.in_event_chain or in_event),
    )


def _expand_single_caller_views(
    reg: FlightCallerRegistration,
    seen: set[int],
    *,
    post_step: bool = False,
) -> list[CoalesceCallerView]:
    eff_stack = reg.turn_entry_stack if post_step else reg.caller_stack
    own_flights = (*reg.coalesce_flights, *(ef.flight_id for ef in reg.enclosing_flights))
    parent_views: list[CoalesceCallerView] = []
    for ef in reg.enclosing_flights:
        parent_views.extend(ef.snapshot_caller_views(set(seen), post_step=post_step))
    if not parent_views and reg.inherited_views:
        parent_views.extend(reg.inherited_views)
    if parent_views:
        return [
            _merge_caller_view(pv, eff_stack, reg.caller_hops, own_flights, reg.in_event_chain)
            for pv in parent_views
        ]
    uniq_fl = tuple(dict.fromkeys(fid for fid in own_flights if fid))
    return [
        CoalesceCallerView(
            reg.caller_turn_id,
            reg.call_tree_id,
            eff_stack,
            reg.caller_hops,
            uniq_fl,
            reg.in_event_chain,
        )
    ]


def _is_ancestor_stack(
    holder_stack: tuple[tuple[HostPath, TaskId], ...],
    child_stack: tuple[tuple[HostPath, TaskId], ...],
) -> bool:
    if not holder_stack or len(child_stack) <= len(holder_stack):
        return False
    return child_stack[: len(holder_stack)] == holder_stack


def _is_ancestor_subslice(
    holder_stack: tuple[tuple[HostPath, TaskId], ...],
    descendant_stack: tuple[tuple[HostPath, TaskId], ...],
) -> bool:
    hlen = len(holder_stack)
    dlen = len(descendant_stack)
    if hlen == 0 or dlen <= hlen:
        return False
    max_start = dlen - hlen - 1
    return any(descendant_stack[idx : idx + hlen] == holder_stack for idx in range(max_start + 1))


def _view_matches_holder(
    view: CoalesceCallerView,
    ident: HolderIdentity,
    *,
    extra_flights: Sequence[str],
    leaf_frame: Optional[tuple[HostPath, TaskId]],
) -> bool:
    eff_stack = (*view.call_stack, leaf_frame) if (leaf_frame is not None and (not view.call_stack or view.call_stack[-1] != leaf_frame)) else view.call_stack
    same_root = (bool(ident.tree_id) and view.call_tree_id == ident.tree_id) or (
        bool(ident.turn_id) and view.turn_id == ident.turn_id
    )
    all_flights = (*extra_flights, *view.flight_ids)
    via_flight = (
        (bool(ident.flight_id) and ident.flight_id in all_flights)
        or (bool(ident.tree_id) and ident.tree_id in all_flights)
        or (bool(ident.turn_id) and ident.turn_id in all_flights)
    )
    if (same_root or via_flight) and ((not ident.stack and via_flight) or _is_ancestor_subslice(ident.stack, eff_stack)):
        return True
    return any(_view_matches_holder(view, alt, extra_flights=extra_flights, leaf_frame=leaf_frame) for alt in ident.alt_owners)


def _reg_matches_holder(
    reg: FlightCallerRegistration,
    ident: HolderIdentity,
    leaf_frame: Optional[tuple[HostPath, TaskId]],
) -> bool:
    reg_flights = (*reg.coalesce_flights, *(ef.flight_id for ef in reg.enclosing_flights))
    eff_reg_stack = (*reg.caller_stack, leaf_frame) if (leaf_frame is not None and (not reg.caller_stack or reg.caller_stack[-1] != leaf_frame)) else reg.caller_stack
    direct_match = (
        (bool(ident.tree_id) and (reg.call_tree_id == ident.tree_id or ident.tree_id in reg_flights))
        or (bool(ident.turn_id) and (reg.caller_turn_id == ident.turn_id or ident.turn_id in reg_flights))
        or (bool(ident.flight_id) and ident.flight_id in reg_flights)
    ) and (not ident.stack or _is_ancestor_subslice(ident.stack, eff_reg_stack))
    if direct_match:
        return True
    views = _expand_single_caller_views(reg, set())
    if views and any(_view_matches_holder(v, ident, extra_flights=reg_flights, leaf_frame=leaf_frame) for v in views):
        return True
    return any(_reg_matches_holder(reg, alt, leaf_frame) for alt in ident.alt_owners)


def _classify_slot_by_predicate(
    reg: FlightCallerRegistration,
    reg_pred: Callable[[FlightCallerRegistration], bool],
    view_pred: Callable[[CoalesceCallerView, tuple[str, ...]], bool],
    exc_factory: Callable[[Sequence[CoalesceCallerView]], BaseException],
) -> tuple[Optional[BaseException], bool]:
    reg_fl = (*reg.coalesce_flights, *(ef.flight_id for ef in reg.enclosing_flights))
    views = _expand_single_caller_views(reg, set())
    if not views:
        return (exc_factory(()) if reg_pred(reg) else None, False)
    matched = [v for v in views if view_pred(v, reg_fl)]
    if len(matched) == len(views):
        return (exc_factory(matched), False)
    if not matched or not reg.enclosing_flights:
        return (None, False)
    sub_ev = any(ef.evict_callers_where(reg_pred, view_pred, exc_factory)[0] for ef in reg.enclosing_flights)
    post = _expand_single_caller_views(reg, set())
    if not post:
        return (exc_factory(matched), False)
    post_m = [v for v in post if view_pred(v, reg_fl)]
    if len(post_m) == len(post):
        return (exc_factory(post_m), False)
    return (None, sub_ev and not post_m)


class StepFlight(Generic[TVal]):
    """Symmetric single-flight latch sharing cancellation, priority elevation, and live progress."""

    def __init__(self, priority_handle: PriorityHandle) -> None:
        self.flight_id: str = f"flight_{uuid.uuid4().hex}"
        self.priority_handle = priority_handle
        self.cancel_group = SharedCancelGroup()
        self.done = threading.Event()
        self.outcome: Optional[TVal] = None
        self.raised_exc: Optional[BaseException] = None
        self._lock = threading.Lock()
        self._sealed = False
        self._next_pid = 0
        self._callers: dict[int, FlightCallerRegistration] = {}
        self._slot_wakes: dict[int, threading.Event] = {}
        self._slot_detachers: dict[int, Callable[[], None]] = {}
        self._slot_errors: dict[int, BaseException] = {}
        self._prog_listeners: dict[int, Callable[[JsonObject], None]] = {}
        self._abort_hook: Optional[Callable[[int], None]] = None
        self._finalizing = False
        self._pending_aborts: set[int] = set()
        self._notified_workspaces: dict[HostPath, bool] = {}
        self._remote_done = False

    def record_notified_workspace(self, ws: HostPath, *, send_tcp: bool) -> bool:
        with self._lock:
            if self._remote_done or self.done.is_set():
                return False
            already = ws in self._notified_workspaces
            if send_tcp:
                self._notified_workspaces[ws] = True
                return True
            if already:
                return False
            self._notified_workspaces[ws] = False
            return True

    def drain_notified_workspaces(self) -> tuple[tuple[HostPath, bool], ...]:
        with self._lock:
            self._remote_done = True
            out = tuple(self._notified_workspaces.items())
            self._notified_workspaces.clear()
            return out

    def slot_wake_event(self, slot_id: int) -> threading.Event:
        with self._lock:
            return self._slot_wakes.get(slot_id, self.done)

    def seal(self) -> None:
        with self._lock:
            self._sealed = True

    def get_slot_error(self, slot_id: int) -> Optional[BaseException]:
        with self._lock:
            return self._slot_errors.get(slot_id)

    def effective_deadline(self) -> Optional[float]:
        with self._lock:
            live = [
                c
                for pid, c in self._callers.items()
                if pid not in self._slot_errors and not c.step_cancel.is_cancelled and not c.turn_cancel.is_cancelled
            ]
            if not live:
                return 0.0
            if any(c.deadline is None for c in live):
                return None
            return max(c.deadline for c in live if c.deadline is not None)

    def add_caller(
        self,
        reg: FlightCallerRegistration,
        on_progress: Optional[Callable[[JsonObject], None]],
    ) -> tuple[int, Optional[Callable[[], None]]]:
        with self._lock:
            if self._sealed:
                return (-1, None)
            cg_det = self.cancel_group.try_add_participant(reg.step_cancel)
            if cg_det is None:
                return (-1, None)
            pid = self._next_pid
            self._next_pid += 1
            wake_ev = threading.Event()
            if self.done.is_set():
                wake_ev.set()
            self._callers[pid] = reg
            self._slot_wakes[pid] = wake_ev
            self._slot_detachers[pid] = cg_det
            if on_progress is not None:
                self._prog_listeners[pid] = on_progress

        def _detach_caller() -> None:
            with self._lock:
                self._callers.pop(pid, None)
                self._prog_listeners.pop(pid, None)
                det_fn = self._slot_detachers.pop(pid, None)
            if det_fn is not None:
                det_fn()

        return (pid, _detach_caller)

    def evict_callers_where(
        self,
        reg_pred: Callable[[FlightCallerRegistration], bool],
        view_pred: Callable[[CoalesceCallerView, tuple[str, ...]], bool],
        exc_factory: Callable[[Sequence[CoalesceCallerView]], BaseException],
    ) -> tuple[bool, bool]:
        with self._lock:
            candidates = [
                (pid, reg)
                for pid, reg in self._callers.items()
                if pid not in self._slot_errors and not reg.step_cancel.is_cancelled
            ]
        evict_items: list[tuple[int, BaseException]] = []
        evicted_nested = False
        surviving = 0
        for pid, reg in candidates:
            slot_exc, sub_ev = _classify_slot_by_predicate(reg, reg_pred, view_pred, exc_factory)
            if slot_exc is not None:
                evict_items.append((pid, slot_exc))
            else:
                evicted_nested = evicted_nested or sub_ev
                surviving += 1
        if not evict_items and not evicted_nested:
            return (False, surviving > 0)
        if surviving == 0:
            self.seal()
            return (False, False)
        self._commit_slot_evictions(evict_items)
        return (True, True)

    def _commit_slot_evictions(self, evict_items: Sequence[tuple[int, BaseException]]) -> None:
        if not evict_items:
            return
        detachers: list[Callable[[], None]] = []
        wakes: list[threading.Event] = []
        with self._lock:
            for pid, slot_exc in evict_items:
                self._slot_errors[pid] = slot_exc
                self._callers.pop(pid, None)
                self._prog_listeners.pop(pid, None)
                det_fn = self._slot_detachers.pop(pid, None)
                if det_fn is not None:
                    detachers.append(det_fn)
                w_ev = self._slot_wakes.get(pid)
                if w_ev is not None:
                    wakes.append(w_ev)
        for det_fn in detachers:
            det_fn()
        for w_ev in wakes:
            w_ev.set()

    def evict_callers_matching_holder(
        self,
        ident: HolderIdentity,
        leaf_frame: Optional[tuple[HostPath, TaskId]],
        exc: BaseException,
    ) -> tuple[bool, bool]:
        """Evict only caller slots whose entire active view set matches ident; return (evicted_any, surviving_remain)."""
        return self.evict_callers_where(
            lambda reg: _reg_matches_holder(reg, ident, leaf_frame),
            lambda v, rfl: _view_matches_holder(v, ident, extra_flights=rfl, leaf_frame=leaf_frame),
            lambda _vs: exc,
        )

    def _commit_abort_hook_and_collect_missed(
        self,
        abort_hook: Optional[Callable[[int], None]],
        admitted_pids: Sequence[int],
    ) -> tuple[int, ...]:
        with self._lock:
            self._abort_hook = abort_hook
            self._finalizing = False
            evicted = [pid for pid in admitted_pids if pid in self._slot_errors or pid not in self._callers]
            missed = tuple(dict.fromkeys((*self._pending_aborts, *evicted)))
            self._pending_aborts.clear()
            return missed

    def seal_and_finalize(
        self,
        builder: Callable[[list[LiveFlightParticipant], int], tuple[TBundle, Optional[Callable[[int], None]]]],
    ) -> TBundle:
        """Seal admissions, expand nested views outside lock, and replay any interim slot aborts."""
        with self._lock:
            self._sealed = True
            self._finalizing = True
            total_admitted = self._next_pid
            raw_live = [
                (pid, c)
                for pid, c in self._callers.items()
                if pid not in self._slot_errors and not c.step_cancel.is_cancelled and not c.turn_cancel.is_cancelled
            ]
        try:
            live = [
                LiveFlightParticipant(
                    slot_id=pid,
                    turn_cancel=c.turn_cancel,
                    caller_hops=c.caller_hops,
                    caller_views=tuple(_expand_single_caller_views(c, set(), post_step=True)),
                )
                for pid, c in raw_live
            ]
            bundle, abort_hook = builder(live, total_admitted)
        except BaseException:
            with self._lock:
                self._finalizing = False
                self._pending_aborts.clear()
            raise
        missed = self._commit_abort_hook_and_collect_missed(abort_hook, [pid for pid, _c in raw_live])
        if abort_hook is not None:
            for sid in missed:
                abort_hook(sid)
        return bundle

    def notify_waiter_aborted(self, slot_id: int) -> None:
        if slot_id < 0:
            return
        with self._lock:
            hook = self._abort_hook
            if hook is None and self._finalizing:
                self._pending_aborts.add(slot_id)
        if hook is not None:
            hook(slot_id)

    def broadcast_progress(self, payload: JsonObject) -> None:
        with self._lock:
            cbs = list(self._prog_listeners.values())
        for cb in cbs:
            invoke_observer_safely(lambda fn=cb: fn(payload))

    def snapshot_caller_views(
        self,
        visited: Optional[set[int]] = None,
        *,
        post_step: bool = False,
    ) -> tuple[CoalesceCallerView, ...]:
        seen = visited if visited is not None else set()
        self_key = id(self)
        if self_key in seen:
            return ()
        seen.add(self_key)
        with self._lock:
            live = [
                c
                for pid, c in self._callers.items()
                if pid not in self._slot_errors and not c.step_cancel.is_cancelled
            ]
        expanded: list[CoalesceCallerView] = []
        for reg in live:
            for v in _expand_single_caller_views(reg, seen, post_step=post_step):
                fids = v.flight_ids if self.flight_id in v.flight_ids else (*v.flight_ids, self.flight_id)
                expanded.append(replace(v, flight_ids=fids))
        return tuple(expanded)

    def find_common_conflicting_hop(self, cand_hops: Sequence[ScopedHop]) -> Optional[ScopedHop]:
        """Return a single ScopedHop that conflicts with EVERY active caller view, or None."""
        if not cand_hops:
            return None
        views = self.snapshot_caller_views()
        if not views:
            return None
        for c_scope, c_eid in cand_hops:
            if all(any(hop_conflicts(h, c_scope, c_eid) for h in v.caller_hops) for v in views):
                self.seal()
                return (c_scope, c_eid)
        return None

    def all_active_callers_have_frame(self, frame: tuple[HostPath, TaskId]) -> bool:
        views = self.snapshot_caller_views()
        if bool(views) and all(frame in v.call_stack for v in views):
            self.seal()
            return True
        return False

    def depends_on_flight_ids(self, target_fids: frozenset[str], seen: Optional[set[int]] = None) -> bool:
        if self.flight_id in target_fids:
            return True
        vis = seen if seen is not None else set()
        if id(self) in vis:
            return False
        vis.add(id(self))
        with self._lock:
            regs = [
                c
                for pid, c in self._callers.items()
                if pid not in self._slot_errors and not c.step_cancel.is_cancelled
            ]
        for reg in regs:
            if any(f in target_fids for f in reg.coalesce_flights):
                return True
            if any(f in target_fids for v in reg.inherited_views for f in v.flight_ids):
                return True
            if any(ef.depends_on_flight_ids(target_fids, vis) for ef in reg.enclosing_flights):
                return True
        return False

    def has_reentrant_caller(
        self,
        ident: HolderIdentity,
        leaf_frame: Optional[tuple[HostPath, TaskId]] = None,
    ) -> bool:
        with self._lock:
            live = [
                reg
                for pid, reg in self._callers.items()
                if pid not in self._slot_errors and not reg.step_cancel.is_cancelled
            ]
        return any(_reg_matches_holder(reg, ident, leaf_frame) for reg in live)

    def complete(self, *, outcome: Optional[TVal] = None, raised_exc: Optional[BaseException] = None) -> None:
        with self._lock:
            self._sealed = True
            wakes = list(self._slot_wakes.values())
        self.outcome = outcome
        self.raised_exc = raised_exc
        self.done.set()
        for w_ev in wakes:
            w_ev.set()


@dataclass(frozen=True, slots=True)
class CoordinatedExecution(Generic[TResult]):
    """Typed outcome returned by ResourceCoordinator.execute without anonymous tuple indexing."""

    is_follower: bool
    caller_slot_id: int
    outcome: Optional[TResult]


@dataclass(frozen=True, slots=True)
class ResourceAcquireSpec:
    """Structured acquisition specification encapsulating resource key, mode, lineage hops, and priority."""

    resource_key: Optional[str]
    mode: ConcurrencyMode
    equiv_key: str
    priority: ExecutionPriority
    turn_id: str
    call_stack: tuple[tuple[HostPath, TaskId], ...]
    cancel_token: CancellationToken
    turn_cancel_token: Optional[CancellationToken] = None
    timeout_ms: Optional[int] = None
    external_priority_handle: Optional[PriorityHandle] = None
    allow_step_coalesce: bool = True
    call_tree_id: str = ""
    caller_hops: tuple[ScopedHop, ...] = ()
    enclosing_flights: tuple[StepFlight[object], ...] = ()
    coalesce_callers: tuple[CoalesceCallerView, ...] = ()
    coalesce_flights: tuple[str, ...] = ()
    turn_entry_stack: tuple[tuple[HostPath, TaskId], ...] = ()
    in_event_chain: bool = False
    on_progress: Optional[Callable[[JsonObject], None]] = None


@dataclass(slots=True)
class _ActiveHolder:
    turn_id: str
    call_stack: tuple[tuple[HostPath, TaskId], ...]
    mode: ConcurrencyMode
    equiv_key: str
    priority_handle: PriorityHandle
    cancel_token: CancellationToken
    allow_step_coalesce: bool = True
    flight: Optional[StepFlight[object]] = None
    call_tree_id: str = ""
    enclosing_flights: tuple[StepFlight[object], ...] = ()
    coalesce_callers: tuple[CoalesceCallerView, ...] = ()
    coalesce_flights: tuple[str, ...] = ()
    deadline: Optional[float] = None
    os_lock_live: bool = False
    pin_path: Optional[HostPath] = None
    self_exit_guard: Optional[threading.Event] = None
    lingering_guards: list[threading.Event] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _WaitEdge:
    bucket: _ResourceBucket
    waiter: _QueuedWaiter
    spec: ResourceAcquireSpec


@dataclass(frozen=True, slots=True)
class _PollingOsHolder:
    holder: _ActiveHolder
    owner_path: HostPath
    resource_key: str


@dataclass(frozen=True, slots=True)
class _RemoteFlightEntry:
    origin_ws: Optional[HostPath]
    view: CoalesceCallerView


@dataclass(slots=True)
class _QueuedWaiter:
    seq: int
    holder: _ActiveHolder
    wake_event: threading.Event = field(default_factory=threading.Event)
    aborted_preempt: bool = False
    promoted: bool = False
    reentrant_grant: Optional[_ReentrantGrant] = None
    cross_proc_bypass: bool = False


@dataclass(slots=True)
class _BucketAdmission:
    joined_flight: Optional[StepFlight[object]] = None
    caller_slot_id: int = -1
    detach_fn: Optional[Callable[[], None]] = None
    holder: Optional[_ActiveHolder] = None
    waiter: Optional[_QueuedWaiter] = None


class _ResourceBucket:
    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.active: Optional[_ActiveHolder] = None
        self.cross_proc_reentrant: list[_ActiveHolder] = []
        self.serial_stack_chain: list[HolderIdentity] = []
        self.turn_io_busy = False
        self.waiters: list[_QueuedWaiter] = []
        self.seq_counter = 0


def _wake_bucket_cond(bucket: _ResourceBucket) -> None:
    with bucket.cond:
        bucket.cond.notify_all()


def _encode_turn_frame_doc(
    frame_id: str,
    ident: HolderIdentity,
    coalesce_callers: Sequence[CoalesceCallerView],
) -> JsonObject:
    pid_now = os.getpid()
    st_tag = get_process_start_tag(pid_now) or ""
    return {
        "frame_id": frame_id,
        "pid": pid_now,
        "start_tag": st_tag,
        "turn_id": ident.turn_id,
        "call_tree_id": ident.tree_id,
        "flight_id": ident.flight_id,
        "call_stack": [[str(ws), str(tid)] for ws, tid in ident.stack],
        "callers": [
            {
                "turn_id": v.turn_id,
                "call_tree_id": v.call_tree_id,
                "call_stack": [[str(ws), str(tid)] for ws, tid in v.call_stack],
            }
            for v in coalesce_callers
            if v.call_tree_id
        ],
    }


def _read_live_turn_frames(turn_json_path: HostPath) -> list[JsonObject]:
    doc = read_json_dict(turn_json_path)
    raw_frames = doc.get("frames") if isinstance(doc, dict) else None
    if not isinstance(raw_frames, list):
        return []
    live: list[JsonObject] = []
    for item in raw_frames:
        if not isinstance(item, dict):
            continue
        pid_raw = item.get("pid")
        ct_raw = item.get("call_tree_id")
        if type(pid_raw) is not int or pid_raw <= 0 or type(ct_raw) is not str or not ct_raw:
            continue
        if not is_process_alive(pid_raw):
            continue
        rec_tag = item.get("start_tag")
        if type(rec_tag) is str and rec_tag:
            live_tag = get_process_start_tag(pid_raw)
            if live_tag is not None and live_tag != rec_tag:
                continue
        live.append(item)
    return live


def _decode_turn_frame_ident(item: JsonObject) -> HolderIdentity:
    raw_turn = item.get("turn_id")
    raw_tree = item.get("call_tree_id")
    raw_fid = item.get("flight_id")
    return HolderIdentity(
        turn_id=raw_turn if type(raw_turn) is str else "",
        tree_id=raw_tree if type(raw_tree) is str else "",
        flight_id=raw_fid if type(raw_fid) is str else "",
        stack=_decode_owner_stack(item.get("call_stack")),
        alt_owners=_decode_alt_owners(item.get("callers")),
    )


def _try_push_cross_proc_turn_frame(
    locks_dir: HostPath,
    stem: str,
    frame_doc: JsonObject,
    matches_top_fn: Optional[Callable[[HolderIdentity], bool]],
    reset_root: bool,
    cancel_token: CancellationToken,
    deadline: Optional[float],
) -> bool:
    turn_lk = FileLock(resolve_contained_subpath(locks_dir, f"{stem}.turn.lock"), allow_transitions=False)
    turn_json = resolve_contained_subpath(locks_dir, f"{stem}.turn.json")
    rem_tmo = None if deadline is None else max(0.0, deadline - time.monotonic())
    turn_lk.acquire(shared=False, blocking=True, timeout_sec=rem_tmo, cancel_token=cancel_token)
    try:
        if reset_root:
            atomic_write_json(turn_json, {"frames": [frame_doc]})
            return True
        live = _read_live_turn_frames(turn_json)
        if live and (matches_top_fn is None or not matches_top_fn(_decode_turn_frame_ident(live[-1]))):
            owner_path = resolve_contained_subpath(locks_dir, f"{stem}.owner.json")
            live_ow = _read_live_cross_proc_owner(owner_path)
            if not (
                len(live) == 1
                and live_ow is not None
                and matches_top_fn is not None
                and matches_top_fn(live_ow[0])
            ):
                return False
        live.append(frame_doc)
        atomic_write_json(turn_json, {"frames": live})
        return True
    finally:
        turn_lk.release()


def _pop_cross_proc_turn_frame(locks_dir: HostPath, stem: str, frame_id: str) -> None:
    turn_lk = FileLock(resolve_contained_subpath(locks_dir, f"{stem}.turn.lock"), allow_transitions=False)
    turn_json = resolve_contained_subpath(locks_dir, f"{stem}.turn.json")
    pending_fatal: Optional[BaseException] = None
    try:
        turn_lk.acquire(shared=False, blocking=True, timeout_sec=5.0)
    except (YscbError, TaskCancelledException, OSError, ValueError):
        return
    except BaseException as exc:
        pending_fatal = exc
        try:
            if not turn_lk.acquire(shared=False, blocking=False):
                raise exc
        except (YscbError, TaskCancelledException, OSError, ValueError):
            raise exc from None
    try:
        kept = [f for f in _read_live_turn_frames(turn_json) if f.get("frame_id") != frame_id]
        if kept:
            atomic_write_json(turn_json, {"frames": kept})
        else:
            silent_unlink(turn_json)
    except OSError:
        pass
    finally:
        turn_lk.release()
    if pending_fatal is not None:
        raise pending_fatal


def _wait_bucket_slice(
    bucket: _ResourceBucket,
    cancel_token: CancellationToken,
    deadline: Optional[float],
    max_slice: float,
    resource_key: Optional[str],
) -> None:
    cancel_token.raise_if_cancelled()
    if deadline is None:
        bucket.cond.wait(timeout=max_slice)
        return
    rem = deadline - time.monotonic()
    if rem <= 0.0:
        raise YscbError(
            ErrorCode.TASK_TIMEOUT,
            f"Timed out waiting on serialized reentrant turn for '{resource_key}'.",
        )
    bucket.cond.wait(timeout=min(max_slice, rem))


@contextlib.contextmanager
def _serial_execution_turn(
    bucket: _ResourceBucket,
    spec_or_holder_turn: str,
    spec_or_holder_tree: str,
    call_stack: tuple[tuple[HostPath, TaskId], ...],
    coalesce_callers: Sequence[CoalesceCallerView],
    matches_top_fn: Optional[Callable[[HolderIdentity], bool]],
    cancel_token: CancellationToken,
    timeout_sec: Optional[float],
    resource_key: Optional[str],
    locks_dir: Optional[HostPath] = None,
    *,
    reset_root: bool = False,
) -> Iterator[None]:
    deadline = (time.monotonic() + timeout_sec) if timeout_sec is not None else None
    alt_ows = tuple(
        HolderIdentity(v.turn_id, v.call_tree_id, "", v.call_stack)
        for v in coalesce_callers
        if v.call_tree_id
    )
    my_ident = HolderIdentity(
        turn_id=spec_or_holder_turn,
        tree_id=spec_or_holder_tree or spec_or_holder_turn,
        flight_id="",
        stack=call_stack,
        alt_owners=alt_ows,
    )
    stem = _build_resource_lock_stem(resource_key) if (locks_dir is not None and resource_key) else ""
    frame_id = uuid.uuid4().hex if stem else ""
    frame_doc = _encode_turn_frame_doc(frame_id, my_ident, coalesce_callers) if stem else {}
    unreg = cancel_token.register_callback(lambda _p, _r: _wake_bucket_cond(bucket))
    pushed_cross_proc = False
    try:
        while True:
            with bucket.cond:
                while bucket.turn_io_busy or (
                    not reset_root
                    and bool(bucket.serial_stack_chain)
                    and (matches_top_fn is None or not matches_top_fn(bucket.serial_stack_chain[-1]))
                ):
                    _wait_bucket_slice(bucket, cancel_token, deadline, 0.03, resource_key)
                cancel_token.raise_if_cancelled()
                if not stem:
                    if reset_root:
                        bucket.serial_stack_chain[:] = [my_ident]
                    else:
                        bucket.serial_stack_chain.append(my_ident)
                    break
                bucket.turn_io_busy = True
            admitted = False
            try:
                admitted = _try_push_cross_proc_turn_frame(
                    require_non_none(locks_dir), stem, frame_doc, matches_top_fn, reset_root, cancel_token, deadline
                )
            finally:
                with bucket.cond:
                    bucket.turn_io_busy = False
                    if admitted:
                        pushed_cross_proc = True
                        if reset_root:
                            bucket.serial_stack_chain[:] = [my_ident]
                        else:
                            bucket.serial_stack_chain.append(my_ident)
                    bucket.cond.notify_all()
            if admitted:
                break
            with bucket.cond:
                _wait_bucket_slice(bucket, cancel_token, deadline, 0.008, resource_key)
    finally:
        unreg()
    try:
        yield
    finally:
        with bucket.cond:
            if bucket.serial_stack_chain and bucket.serial_stack_chain[-1] is my_ident:
                bucket.serial_stack_chain.pop()
            elif my_ident in bucket.serial_stack_chain:
                bucket.serial_stack_chain.remove(my_ident)
            bucket.cond.notify_all()
        if pushed_cross_proc and locks_dir is not None:
            _pop_cross_proc_turn_frame(locks_dir, stem, frame_id)


def _dedup_flight_ids(raw_ids: Sequence[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for fid in raw_ids:
        if fid and fid not in seen:
            seen.append(fid)
    return tuple(seen)


def _all_spec_flight_ids(spec: ResourceAcquireSpec) -> tuple[str, ...]:
    return _dedup_flight_ids(
        (
            *(ef.flight_id for ef in spec.enclosing_flights),
            *spec.coalesce_flights,
            *(f for v in spec.coalesce_callers for f in v.flight_ids),
        )
    )


def _all_holder_flight_ids(holder: _ActiveHolder) -> tuple[str, ...]:
    own_id = (holder.flight.flight_id,) if holder.flight is not None else ()
    return _dedup_flight_ids(
        (
            *own_id,
            *(ef.flight_id for ef in holder.enclosing_flights),
            *holder.coalesce_flights,
            *(f for v in holder.coalesce_callers for f in v.flight_ids),
        )
    )


def _sort_waiters(waiters: list[_QueuedWaiter]) -> None:
    waiters.sort(
        key=lambda item: (0 if item.holder.priority_handle.current == ExecutionPriority.FOREGROUND else 1, item.seq)
    )


def wait_on_event_with_cancel(
    ev: threading.Event,
    cancel_token: CancellationToken,
    timeout_sec: Optional[float],
) -> None:
    deadline = (time.monotonic() + timeout_sec) if timeout_sec is not None else None
    while not ev.is_set():
        cancel_token.raise_if_cancelled()
        rem = 0.02
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0:
                raise YscbError(ErrorCode.TASK_TIMEOUT, "Timed out waiting in ResourceCoordinator.")
            rem = min(rem, left)
        ev.wait(timeout=rem)
    cancel_token.raise_if_cancelled()


def _await_step_flight(
    flight: StepFlight[TResult],
    adm: _BucketAdmission,
    cancel_token: CancellationToken,
    timeout_sec: Optional[float],
    *,
    is_follower: bool,
    on_early_abort: Optional[Callable[[], None]] = None,
) -> CoordinatedExecution[TResult]:
    slot_wake = flight.slot_wake_event(adm.caller_slot_id)
    try:
        wait_on_event_with_cancel(slot_wake, cancel_token, timeout_sec)
    except BaseException:
        if adm.detach_fn is not None:
            adm.detach_fn()
            adm.detach_fn = None
        slot_err = flight.get_slot_error(adm.caller_slot_id)
        if slot_err is None:
            flight.notify_waiter_aborted(adm.caller_slot_id)
        if on_early_abort is not None:
            on_early_abort()
        if slot_err is not None:
            raise slot_err from None
        raise
    finally:
        if adm.detach_fn is not None:
            adm.detach_fn()
    slot_err = flight.get_slot_error(adm.caller_slot_id)
    if slot_err is not None:
        if on_early_abort is not None:
            on_early_abort()
        raise slot_err
    if flight.raised_exc is not None:
        raise flight.raised_exc
    return CoordinatedExecution(is_follower, adm.caller_slot_id, flight.outcome)


@dataclass(frozen=True, slots=True)
class _ReentrantGrant:
    holder: _ActiveHolder
    step_guard: threading.Event


@dataclass(frozen=True, slots=True)
class _FlightJoinControl:
    action: str
    flight_id: str
    callers: tuple[CoalesceCallerView, ...]
    origin_ws: Optional[HostPath] = None


@dataclass(frozen=True, slots=True)
class _FlightJoinReply:
    ok: bool
    conflict: bool = False
    error: Optional[ErrorDetail] = None
    holder: Optional[HolderIdentity] = None


@dataclass(frozen=True, slots=True)
class _FlightEvictControl:
    action: str
    flight_id: str
    error: ErrorDetail
    holder: HolderIdentity = HolderIdentity()


@dataclass(frozen=True, slots=True)
class _FlightDoneControl:
    action: str
    flight_id: str


class ResourceCoordinator:
    """Single-point step coordinator unifying CallStack reentrancy, symmetric COALESCE, PREEMPT, and FileLock."""

    def __init__(
        self,
        locks_dir: Optional[HostPath] = None,
        *,
        cache_dir: Optional[HostPath] = None,
        workspace_root: Optional[HostPath] = None,
        resolve_cache_dir: Optional[Callable[[HostPath], HostPath]] = None,
        is_daemon_host: bool = False,
    ) -> None:
        if locks_dir is None and cache_dir is None:
            raise ValueError("ResourceCoordinator requires either locks_dir or cache_dir.")
        self._locks_dir = locks_dir
        self._cache_dir: Optional[HostPath] = (
            cache_dir
            if cache_dir is not None
            else (HostPath(require_non_none(locks_dir).path.parent) if workspace_root is None else None)
        )
        base_cache = cache_dir if cache_dir is not None else HostPath(require_non_none(locks_dir).path.parent)
        self._workspace_root = workspace_root or HostPath(base_cache.path.parent)
        self._resolve_cache_dir = resolve_cache_dir or (lambda ws: resolve_contained_subpath(ws, DEFAULT_CACHE_DIRNAME))
        self._is_daemon_host = is_daemon_host
        self._buckets_guard = threading.Lock()
        self._buckets: weakref.WeakValueDictionary[str, _ResourceBucket] = weakref.WeakValueDictionary()
        self._live_flights: weakref.WeakValueDictionary[str, StepFlight[object]] = weakref.WeakValueDictionary()
        self._peer_coordinators: Optional[weakref.WeakValueDictionary[str, ResourceCoordinator]] = None
        self._peer_cache_dirs: Optional[dict[str, HostPath]] = None
        self._peer_guard: Optional[threading.RLock] = None
        self._wait_lock = threading.Lock()
        self._wait_edges: dict[int, _WaitEdge] = {}
        self._polling_holders: dict[int, _PollingOsHolder] = {}
        self._remote_callers: OrderedDict[str, list[_RemoteFlightEntry]] = OrderedDict()
        self._pinned_flights: dict[str, int] = {}

    def _unpin_flights(self, uniq: tuple[str, ...]) -> None:
        with self._wait_lock:
            for fid in uniq:
                decrement_ref_count(self._pinned_flights, fid)

    def _effective_locks_dir(self) -> HostPath:
        if self._locks_dir is not None:
            return self._locks_dir
        return resolve_contained_subpath(require_non_none(self._cache_dir), LOCKS_SUBDIR)

    def _lookup_workspace_cache_dir(self, ws_root: HostPath) -> HostPath:
        if ws_root == self._workspace_root:
            return self._cache_dir if self._cache_dir is not None else self._resolve_cache_dir(ws_root)
        ws_key = ws_root.comparison_key
        if self._peer_cache_dirs is not None and self._peer_guard is not None:
            with self._peer_guard:
                cached = self._peer_cache_dirs.get(ws_key)
            if cached is not None:
                return cached
        resolved = self._resolve_cache_dir(ws_root)
        if self._peer_cache_dirs is not None and self._peer_guard is not None:
            with self._peer_guard:
                self._peer_cache_dirs.setdefault(ws_key, resolved)
        return resolved

    def _merge_known_remote_callers(self, spec: ResourceAcquireSpec) -> ResourceAcquireSpec:
        fids = _all_spec_flight_ids(spec)
        if not fids:
            return spec
        existing = set(spec.coalesce_callers)
        with self._wait_lock:
            merged = tuple(
                dict.fromkeys(
                    (*spec.coalesce_callers, *(ent.view for fid in fids for ent in self._remote_callers.get(fid, ())))
                )
            )
        return replace(spec, coalesce_callers=merged) if len(merged) > len(existing) else spec

    def _collect_remote_evict_workspaces(
        self,
        spec: ResourceAcquireSpec,
        fids: tuple[str, ...],
        views: Sequence[CoalesceCallerView],
    ) -> list[HostPath]:
        found: list[HostPath] = []
        with self._wait_lock:
            known_ws = [
                ent.origin_ws
                for fid in fids
                for ent in self._remote_callers.get(fid, ())
                if ent.origin_ws is not None
            ]
        stack_ws = [ws for ws, _t in (*spec.turn_entry_stack, *spec.call_stack[:-1])]
        view_ws = [ws for v in views for ws, _t in v.call_stack]
        for ws in (*known_ws, *reversed(stack_ws), *view_ws):
            if ws != self._workspace_root and ws not in found:
                found.append(ws)
        return found

    def _broadcast_remote_ident_evict(
        self,
        fids: tuple[str, ...],
        cand_workspaces: Sequence[HostPath],
        ident: HolderIdentity,
        detail: ErrorDetail,
    ) -> bool:
        hit = False
        for fid in fids:
            for ws in cand_workspaces:
                if self._send_remote_flight_evict(ws, fid, ident, detail):
                    hit = True
        return hit

    def _evict_remote_conflicting_callers(
        self,
        spec: ResourceAcquireSpec,
        ident: HolderIdentity,
        err: YscbError,
    ) -> Optional[ResourceAcquireSpec]:
        spec = self._merge_known_remote_callers(spec)
        fids = _all_spec_flight_ids(spec)
        if not fids or not spec.coalesce_callers:
            return None
        leaf = spec.call_stack[-1] if spec.call_stack else None
        bad_views = [
            v
            for v in spec.coalesce_callers
            if _view_matches_holder(v, ident, extra_flights=spec.coalesce_flights, leaf_frame=leaf)
        ]
        rem_views = tuple(
            v
            for v in spec.coalesce_callers
            if not _view_matches_holder(v, ident, extra_flights=spec.coalesce_flights, leaf_frame=leaf)
        )
        if not bad_views or not rem_views:
            return None
        cand_ws = self._collect_remote_evict_workspaces(spec, fids, spec.coalesce_callers)
        if not cand_ws or not self._broadcast_remote_ident_evict(fids, cand_ws, ident, err.detail):
            return None
        for fid in fids:
            for bv in bad_views:
                self._prune_remote_caller_view(fid, bv)
        pruned = replace(spec, coalesce_callers=rem_views)
        return pruned if not _spec_matches_ident(pruned, ident) else None

    def _prune_remote_caller_view(self, fid: str, view: CoalesceCallerView) -> None:
        with self._wait_lock:
            cur_list = self._remote_callers.get(fid)
            if cur_list is not None:
                self._remote_callers[fid] = [e for e in cur_list if e.view != view]



    @property
    def is_daemon_host(self) -> bool:
        return self._is_daemon_host

    def drain_local_borrowed_locks(self, spec: ResourceAcquireSpec, deadline: float) -> None:
        with self._buckets_guard:
            buckets = list(self._buckets.values())
        for b in buckets:
            _wait_active_borrowed_guards_for_caller(b, spec, deadline=deadline)

    def _drain_caller_borrowed_serialize_locks(self, spec: ResourceAcquireSpec) -> None:
        grace_deadline = time.monotonic() + 2.0
        self.drain_local_borrowed_locks(spec, grace_deadline)
        if self._peer_coordinators is None or self._peer_guard is None:
            return
        with self._peer_guard:
            peers = [p for p in self._peer_coordinators.values() if p is not self]
        for peer in peers:
            peer.drain_local_borrowed_locks(spec, grace_deadline)

    def _expand_dependent_flight_ids(self, root_fid: str) -> frozenset[str]:
        expanded: set[str] = {root_fid}
        with self._wait_lock:
            snap = [(k, tuple(v_list)) for k, v_list in self._remote_callers.items()]
        changed = True
        while changed:
            changed = False
            for child_fid, entries in snap:
                if child_fid in expanded:
                    continue
                if any(f in expanded for ent in entries for f in ent.view.flight_ids):
                    expanded.add(child_fid)
                    changed = True
        return frozenset(expanded)

    def _check_local_joined_wait_and_poll_edges(
        self,
        cand_flight: StepFlight[object],
        spec: ResourceAcquireSpec,
    ) -> Optional[tuple[HolderIdentity, ErrorDetail]]:
        target_fids = self._expand_dependent_flight_ids(cand_flight.flight_id)
        joined_views = _build_joined_views_for_flight(cand_flight.flight_id, spec)
        src_tid = str(spec.call_stack[-1][1]) if spec.call_stack else None
        with self._wait_lock:
            edges = list(self._wait_edges.values())
            polls = list(self._polling_holders.values())
        for edge in edges:
            if not _wait_edge_depends_on_fids(edge.waiter, edge.spec, target_fids):
                continue
            if edge.waiter.holder.flight is not cand_flight:
                cyc_e = _check_holder_or_flight_task_cycle(edge.waiter.holder, edge.spec.call_stack, joined_views)
                if cyc_e is not None:
                    return cyc_e
            conflict_ident = _try_promote_or_detect_wait_conflict(
                edge.bucket,
                edge.waiter,
                spec,
                locks_dir=self._effective_locks_dir(),
                resource_key=edge.spec.resource_key,
            )
            if conflict_ident is not None:
                return (conflict_ident, _reentrancy_error_detail(str(edge.spec.resource_key), src_tid))
        for p_item in polls:
            if not _holder_depends_on_fids(p_item.holder, target_fids):
                continue
            if p_item.holder.flight is not cand_flight:
                cyc_p = _check_join_task_cycle(p_item.holder.call_stack, joined_views)
                if cyc_p is not None:
                    return cyc_p
            live_ow = _read_live_cross_proc_owner(p_item.owner_path)
            if live_ow is None or not _spec_matches_ident(spec, live_ow[0]):
                continue
            if live_ow[1] != ConcurrencyMode.SERIALIZE.value or not _is_effective_serialize(
                p_item.holder.mode, p_item.holder.allow_step_coalesce
            ):
                return (live_ow[0], _reentrancy_error_detail(p_item.resource_key, src_tid))
        return None

    def _notify_remote_workspaces_flight_join(
        self,
        cand_flight: StepFlight[object],
        spec: ResourceAcquireSpec,
    ) -> Optional[tuple[HolderIdentity, ErrorDetail]]:
        if cand_flight.done.is_set():
            return None
        flight_id = cand_flight.flight_id
        joined_views = _build_joined_views_for_flight(flight_id, spec)
        live_all = tuple(
            replace(v, flight_ids=(flight_id, *(f for f in v.flight_ids if f != flight_id)))
            for v in cand_flight.snapshot_caller_views()
        )
        send_views = live_all if live_all else joined_views
        anc_workspaces = {ws for v in send_views for ws, _tid in v.call_stack if ws != self._workspace_root}
        for ws_anc in anc_workspaces:
            peer = self._lookup_inproc_peer(ws_anc)
            send_tcp = (peer is None) or (not peer.is_daemon_host)
            if not cand_flight.record_notified_workspace(ws_anc, send_tcp=send_tcp):
                continue
            peer_err = self._notify_single_ancestor_ws(ws_anc, flight_id, send_views, peer=peer, send_tcp=send_tcp)
            if cand_flight.done.is_set():
                self._send_single_flight_done(ws_anc, flight_id, send_tcp=send_tcp)
            if peer_err is not None:
                return peer_err
        return None

    def _lookup_inproc_peer(self, ws: HostPath) -> Optional[ResourceCoordinator]:
        if self._peer_coordinators is None or self._peer_guard is None:
            return None
        with self._peer_guard:
            peer = self._peer_coordinators.get(ws.comparison_key)
        return peer if (peer is not None and peer is not self) else None

    def _send_single_flight_done(self, ws_anc: HostPath, fid: str, *, send_tcp: bool) -> None:
        peer = self._lookup_inproc_peer(ws_anc)
        if peer is not None:
            peer.remove_remote_flight(fid)
        if send_tcp:
            payload = DataclassCodec.encode_object(_FlightDoneControl(action="flight_done", flight_id=fid))
            query_daemon_control(
                self._lookup_workspace_cache_dir(ws_anc), ws_anc, FrameKind.CONTROL_REQUEST, payload, timeout_ms=1500
            )

    def _notify_remote_workspaces_flight_done(self, flight: StepFlight[object]) -> None:
        for ws_anc, send_tcp in flight.drain_notified_workspaces():
            self._send_single_flight_done(ws_anc, flight.flight_id, send_tcp=send_tcp)

    def remove_remote_flight(self, flight_id: str) -> None:
        with self._wait_lock:
            self._remote_callers.pop(flight_id, None)

    def _notify_single_ancestor_ws(
        self,
        ws_anc: HostPath,
        flight_id: str,
        joined_views: tuple[CoalesceCallerView, ...],
        *,
        peer: Optional[ResourceCoordinator],
        send_tcp: bool,
    ) -> Optional[tuple[HolderIdentity, ErrorDetail]]:
        if peer is not None:
            in_mem = peer.register_remote_flight_join(flight_id, joined_views, origin_ws=self._workspace_root)
            if in_mem is not None or not send_tcp:
                return in_mem
        ctrl = _FlightJoinControl(
            action="flight_join",
            flight_id=flight_id,
            callers=joined_views,
            origin_ws=self._workspace_root,
        )
        ack = query_daemon_control(
            self._lookup_workspace_cache_dir(ws_anc),
            ws_anc,
            FrameKind.CONTROL_REQUEST,
            DataclassCodec.encode_object(ctrl),
            timeout_ms=1500,
        )
        if ack is None:
            return None
        try:
            reply = DataclassCodec.decode(_FlightJoinReply, ack)
        except YscbError as exc:
            return (HolderIdentity(), exc.detail) if ack.get("conflict") is True else None
        if reply.ok and reply.conflict:
            det = reply.error or ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, "Missing conflict error.")
            ident = replace(reply.holder, alt_owners=()) if reply.holder is not None else HolderIdentity()
            return (ident, det)
        return None

    def _send_remote_flight_evict(
        self,
        origin_ws: Optional[HostPath],
        flight_id: str,
        ident: HolderIdentity,
        detail: ErrorDetail,
    ) -> bool:
        if origin_ws is None:
            return False
        peer = self._lookup_inproc_peer(origin_ws)
        if peer is not None and peer.evict_local_flight_ident(flight_id, ident, detail):
            return True
        ctrl = _FlightEvictControl(
            action="flight_evict",
            flight_id=flight_id,
            error=detail,
            holder=replace(ident, alt_owners=()),
        )
        ack = query_daemon_control(
            self._lookup_workspace_cache_dir(origin_ws),
            origin_ws,
            FrameKind.CONTROL_REQUEST,
            DataclassCodec.encode_object(ctrl),
            timeout_ms=1500,
        )
        return ack is not None and ack.get("evicted") is True

    def evict_local_flight_ident(
        self,
        flight_id: str,
        ident: HolderIdentity,
        detail: ErrorDetail,
    ) -> bool:
        fl = self._live_flights.get(flight_id)
        if fl is None:
            return False
        err = YscbError(detail.code, detail.message, remediation=detail.remediation, source_task=detail.source_task)
        ev, surv = fl.evict_callers_matching_holder(ident, None, err)
        return ev and surv

    def handle_remote_flight_control(self, payload: JsonObject) -> JsonObject:
        try:
            if not isinstance(payload, Mapping):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "CONTROL_REQUEST payload must be a Mapping.")
            action = payload.get("action")
            if action == "flight_join":
                j_ctrl = DataclassCodec.decode(_FlightJoinControl, payload)
                if not j_ctrl.flight_id.strip() or any(
                    not c.turn_id.strip() or not c.call_tree_id.strip() for c in j_ctrl.callers
                ):
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "flight_id and caller IDs must be non-empty.")
                res = self.register_remote_flight_join(j_ctrl.flight_id, j_ctrl.callers, origin_ws=j_ctrl.origin_ws)
                if res is None:
                    return DataclassCodec.encode_object(_FlightJoinReply(ok=True, conflict=False))
                ident, det = res
                ack_obj = _FlightJoinReply(ok=True, conflict=True, error=det, holder=replace(ident, alt_owners=()))
                return DataclassCodec.encode_object(ack_obj)
            if action == "flight_evict":
                e_ctrl = DataclassCodec.decode(_FlightEvictControl, payload)
                h_id = replace(e_ctrl.holder, alt_owners=())
                if not e_ctrl.flight_id.strip() or not (
                    h_id.turn_id.strip() or h_id.tree_id.strip() or h_id.flight_id.strip()
                ):
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "flight_id and holder IDs must be non-empty.")
                ev = self.evict_local_flight_ident(e_ctrl.flight_id, h_id, e_ctrl.error)
                return {"ok": True, "evicted": ev}
            if action == "flight_done":
                d_ctrl = DataclassCodec.decode(_FlightDoneControl, payload)
                if not d_ctrl.flight_id.strip():
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "flight_id must be non-empty.")
                self.remove_remote_flight(d_ctrl.flight_id)
                return {"ok": True}
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported remote flight control action: {action!r}")
        except YscbError as exc:
            return {"ok": False, "error": exc.detail.code.value, "message": exc.detail.message}

    def _check_remote_join_edges_and_polls(
        self,
        flight_id: str,
        views: Sequence[CoalesceCallerView],
        probe_spec: ResourceAcquireSpec,
    ) -> Optional[tuple[HolderIdentity, ErrorDetail]]:
        target_fids = self._expand_dependent_flight_ids(flight_id)
        with self._wait_lock:
            edge_items = list(self._wait_edges.items())
            polls = list(self._polling_holders.values())
        for edge_key, edge in edge_items:
            if not _wait_edge_depends_on_fids(edge.waiter, edge.spec, target_fids):
                continue
            cyc_err = _check_holder_or_flight_task_cycle(edge.waiter.holder, edge.spec.call_stack, views)
            if cyc_err is not None:
                return cyc_err
            conflict = _try_promote_or_detect_wait_conflict(
                edge.bucket,
                edge.waiter,
                replace(probe_spec, call_stack=edge.spec.call_stack),
                locks_dir=self._effective_locks_dir(),
                resource_key=edge.spec.resource_key,
            )
            if conflict is not None:
                src_t = str(edge.spec.call_stack[-1][1]) if edge.spec.call_stack else None
                return (conflict, _reentrancy_error_detail(str(edge.spec.resource_key), src_t))
            self._append_views_to_wait_edge(edge_key, views)
        for p_item in polls:
            if not _holder_depends_on_fids(p_item.holder, target_fids):
                continue
            cyc_p = _check_holder_or_flight_task_cycle(p_item.holder, p_item.holder.call_stack, views)
            if cyc_p is not None:
                return cyc_p
            poll_err = _check_poll_item_reentrancy_conflict(p_item, probe_spec)
            if poll_err is not None:
                return poll_err
        return None

    def _append_views_to_wait_edge(self, edge_key: int, views: Sequence[CoalesceCallerView]) -> None:
        with self._wait_lock:
            cur_e = self._wait_edges.get(edge_key)
            if cur_e is not None:
                merged_v = tuple(dict.fromkeys((*cur_e.spec.coalesce_callers, *views)))
                self._wait_edges[edge_key] = replace(cur_e, spec=replace(cur_e.spec, coalesce_callers=merged_v))

    def register_remote_flight_join(
        self,
        flight_id: str,
        views: Sequence[CoalesceCallerView],
        *,
        origin_ws: Optional[HostPath] = None,
    ) -> Optional[tuple[HolderIdentity, ErrorDetail]]:
        if not flight_id or not views:
            return None
        probe_spec = ResourceAcquireSpec(
            resource_key=None,
            mode=ConcurrencyMode.COALESCE,
            equiv_key="",
            priority=ExecutionPriority.FOREGROUND,
            turn_id="",
            call_stack=(),
            cancel_token=CancellationToken(),
            coalesce_callers=tuple(views),
            coalesce_flights=(flight_id,),
        )
        err = self._check_remote_join_edges_and_polls(flight_id, views, probe_spec)
        if err is not None:
            return err
        with self._wait_lock:
            slot = self._remote_callers.setdefault(flight_id, [])
            seen_ents = set(slot)
            for v in views:
                ent = _RemoteFlightEntry(origin_ws, v)
                if ent not in seen_ents:
                    seen_ents.add(ent)
                    slot.append(ent)
            self._remote_callers.move_to_end(flight_id)
            self._prune_inactive_remote_callers_locked()
        with self._buckets_guard:
            all_b = list(self._buckets.values())
        for b in all_b:
            _wake_bucket_cond(b)
        return None

    def _prune_inactive_remote_callers_locked(self) -> None:
        if len(self._remote_callers) <= 4096:
            return
        protected: set[str] = set(self._pinned_flights.keys()) | set(self._live_flights.keys())
        for edge in self._wait_edges.values():
            protected.update(_all_spec_flight_ids(edge.spec))
        for poll in self._polling_holders.values():
            protected.update(_all_holder_flight_ids(poll.holder))
        for cand_fid in list(self._remote_callers.keys()):
            if len(self._remote_callers) <= 4096:
                break
            if cand_fid not in protected:
                self._remote_callers.pop(cand_fid, None)

    def _await_registered_waiter(
        self,
        bucket: _ResourceBucket,
        waiter: _QueuedWaiter,
        spec: ResourceAcquireSpec,
    ) -> _ActiveHolder:
        edge_key = id(waiter)
        try:
            eff_spec = self._merge_known_remote_callers(spec)
            with self._wait_lock:
                self._wait_edges[edge_key] = _WaitEdge(bucket, waiter, eff_spec)
            _recheck_enqueued_waiter_reentrancy(
                bucket,
                waiter,
                eff_spec,
                self._evict_remote_conflicting_callers,
                locks_dir=self._effective_locks_dir(),
            )
            return _await_queued_promotion(bucket, waiter)
        except BaseException as exc:
            _cleanup_failed_waiter_promotion(bucket, waiter, exc)
            raise
        finally:
            with self._wait_lock:
                self._wait_edges.pop(edge_key, None)

    def _mark_holder_os_lock_live_and_promote(
        self,
        bucket: _ResourceBucket,
        holder: _ActiveHolder,
        pin_path: Optional[HostPath],
    ) -> None:
        with bucket.cond:
            holder.os_lock_live = True
            holder.pin_path = pin_path
        with self._wait_lock:
            edges = [e for e in self._wait_edges.values() if e.bucket is bucket]
        for edge in edges:
            _try_promote_or_detect_wait_conflict(
                bucket,
                edge.waiter,
                edge.spec,
                locks_dir=self._effective_locks_dir(),
                resource_key=edge.spec.resource_key,
            )

    def _drive_coalesce_flight(
        self,
        bucket: _ResourceBucket,
        adm: _BucketAdmission,
        spec: ResourceAcquireSpec,
        leader_fn: Callable[[PriorityHandle, CancellationToken, Optional[StepFlight[TResult]]], TResult],
        extract_release_guard: Optional[Callable[[TResult], Optional[threading.Event]]],
    ) -> None:
        holder = adm.holder
        waiter = adm.waiter
        own_flight = holder.flight if holder is not None else (waiter.holder.flight if waiter is not None else None)
        try:
            if holder is None:
                holder = self._await_registered_waiter(bucket, require_non_none(waiter), spec)
            rkey = require_non_none(spec.resource_key)
            self._run_under_os_file_lock(bucket, holder, rkey, leader_fn, extract_release_guard)
        except BaseException as exc:
            _abort_admission_on_error(bucket, adm, exc)
            return
        finally:
            if own_flight is not None:
                self._notify_remote_workspaces_flight_done(own_flight)

    def _run_under_os_file_lock(
        self,
        bucket: _ResourceBucket,
        holder: _ActiveHolder,
        resource_key: str,
        leader_fn: Callable[[PriorityHandle, CancellationToken, Optional[StepFlight[TResult]]], TResult],
        extract_release_guard: Optional[Callable[[TResult], Optional[threading.Event]]],
    ) -> TResult:
        stem = _build_resource_lock_stem(resource_key)
        lock_paths = CrossProcessLockPaths.for_stem(self._effective_locks_dir(), stem, allow_transitions=False)
        reentrant_pin: Optional[FileLock] = None
        deferred_release = False
        owns_os_lock = False
        typed_flight: Optional[StepFlight[TResult]] = holder.flight
        poll_key = id(holder)
        with self._wait_lock:
            self._polling_holders[poll_key] = _PollingOsHolder(holder, lock_paths.owner_path, resource_key)
        try:
            try:
                owns_os_lock, reentrant_pin = _acquire_or_reenter_os_lock(
                    bucket,
                    lock_paths,
                    holder,
                    resource_key,
                    lambda: self._refresh_holder_remote_callers(holder),
                )
            finally:
                with self._wait_lock:
                    self._polling_holders.pop(poll_key, None)
            self._mark_holder_os_lock_live_and_promote(
                bucket, holder, lock_paths.pin_path if owns_os_lock else None
            )
            if _is_effective_serialize(holder.mode, holder.allow_step_coalesce):
                rem_tmo = None if holder.deadline is None else max(0.0, holder.deadline - time.monotonic())
                match_fn: Optional[Callable[[HolderIdentity], bool]] = (
                    None
                    if owns_os_lock
                    else (
                        lambda top: (
                            self._refresh_holder_remote_callers(holder),
                            _holder_matches_cross_proc_owner(holder, top),
                        )[1]
                    )
                )
                with _serial_execution_turn(
                    bucket,
                    holder.turn_id,
                    holder.call_tree_id,
                    holder.call_stack,
                    holder.coalesce_callers,
                    match_fn,
                    holder.cancel_token,
                    rem_tmo,
                    resource_key,
                    self._effective_locks_dir(),
                    reset_root=owns_os_lock,
                ):
                    res = leader_fn(holder.priority_handle, holder.cancel_token, typed_flight)
            else:
                res = leader_fn(holder.priority_handle, holder.cancel_token, typed_flight)
            guard_ev = extract_release_guard(res) if extract_release_guard is not None else None
            with bucket.cond:
                if guard_ev is not None and not guard_ev.is_set():
                    holder.self_exit_guard = guard_ev
                has_lingering = _has_any_holder_lingering_locked(holder)
                if not has_lingering:
                    holder.os_lock_live = False
            deferred_release, reentrant_pin = _finalize_holder_os_lock(
                bucket, holder, lock_paths, owns_os_lock, has_lingering, reentrant_pin
            )
            if typed_flight is not None and not typed_flight.done.is_set():
                typed_flight.complete(outcome=res)
            return res
        except BaseException as exc:
            with bucket.cond:
                has_err_lingering = _has_any_holder_lingering_locked(holder)
                if not has_err_lingering:
                    holder.os_lock_live = False
            deferred_release, reentrant_pin = _finalize_holder_os_lock(
                bucket, holder, lock_paths, owns_os_lock, has_err_lingering, reentrant_pin
            )
            if typed_flight is not None and not typed_flight.done.is_set():
                typed_flight.complete(raised_exc=exc)
            raise
        finally:
            if reentrant_pin is not None:
                reentrant_pin.release()
            if typed_flight is not None:
                typed_flight.cancel_group.close_all()
            if not deferred_release:
                _release_holder_if_active(bucket, holder)

    def coalesce_participant_count(self, resource_key: str) -> int:
        bucket = self._get_bucket(resource_key)
        with bucket.cond:
            if bucket.active is not None and bucket.active.flight is not None:
                return bucket.active.flight.cancel_group.active_count
            for w in bucket.waiters:
                if w.holder.flight is not None:
                    return w.holder.flight.cancel_group.active_count
            return 0

    def _refresh_holder_remote_callers(self, holder: _ActiveHolder) -> None:
        fids = _all_holder_flight_ids(holder)
        if not fids:
            return
        prev_len = len(holder.coalesce_callers)
        with self._wait_lock:
            merged = tuple(
                dict.fromkeys(
                    (*holder.coalesce_callers, *(ent.view for fid in fids for ent in self._remote_callers.get(fid, ())))
                )
            )
        if len(merged) > prev_len:
            holder.coalesce_callers = merged

    def _get_bucket(self, resource_key: str) -> _ResourceBucket:
        with self._buckets_guard:
            b = self._buckets.get(resource_key)
            if b is None:
                b = _ResourceBucket()
                self._buckets[resource_key] = b
            return b

    @contextlib.contextmanager
    def pin_inbound_flights(self, flight_ids: Sequence[str]) -> Iterator[None]:
        uniq = tuple(dict.fromkeys(fid for fid in flight_ids if fid))
        if not uniq:
            yield
            return
        with self._wait_lock:
            for fid in uniq:
                self._pinned_flights[fid] = self._pinned_flights.get(fid, 0) + 1
        try:
            yield
        finally:
            self._unpin_flights(uniq)

    def bind_shared_peers(
        self,
        peers: weakref.WeakValueDictionary[str, ResourceCoordinator],
        cache_dirs: dict[str, HostPath],
        guard: threading.RLock,
    ) -> None:
        self._peer_coordinators = peers
        self._peer_cache_dirs = cache_dirs
        self._peer_guard = guard

    def execute(
        self,
        spec: ResourceAcquireSpec,
        leader_fn: Callable[[PriorityHandle, CancellationToken, Optional[StepFlight[TResult]]], TResult],
        *,
        extract_release_guard: Optional[Callable[[TResult], Optional[threading.Event]]] = None,
    ) -> CoordinatedExecution[TResult]:
        own_prio = spec.external_priority_handle or PriorityHandle(spec.priority)
        if spec.priority == ExecutionPriority.FOREGROUND:
            own_prio.elevate_to_foreground()

        if not spec.resource_key or spec.mode == ConcurrencyMode.PARALLEL:
            return CoordinatedExecution(False, -1, leader_fn(own_prio, spec.cancel_token, None))

        if spec.timeout_ms is not None and spec.timeout_ms <= 0:
            raise YscbError(ErrorCode.TASK_TIMEOUT, f"Timed out immediately acquiring '{spec.resource_key}'.")

        timeout_sec = ms_to_safe_sec(spec.timeout_ms) if spec.timeout_ms is not None else None
        bucket = self._get_bucket(spec.resource_key)

        while True:
            spec = self._merge_known_remote_callers(spec)
            reentrant_pair, spec = _check_same_stack_reentrancy(
                bucket, spec, self._evict_remote_conflicting_callers
            )
            if reentrant_pair is not None:
                try:
                    return _run_reentrant_step(
                        bucket,
                        reentrant_pair,
                        lambda s=spec: self._merge_known_remote_callers(s),
                        own_prio,
                        timeout_sec,
                        self._effective_locks_dir(),
                        leader_fn,
                        extract_release_guard,
                    )
                except BaseException:
                    reentrant_pair.step_guard.set()
                    raise
            cross_pin, spec = _try_acquire_incoming_cross_proc_reentry(
                self._effective_locks_dir(), spec, timeout_sec, self._evict_remote_conflicting_callers
            )
            if cross_pin is not None:
                return _run_cross_proc_borrowed_step(
                    bucket,
                    cross_pin,
                    self._effective_locks_dir(),
                    lambda s=spec: self._merge_known_remote_callers(s),
                    own_prio,
                    timeout_sec,
                    leader_fn,
                    extract_release_guard,
                )

            adm = _admit_or_enqueue_in_bucket(bucket, spec, own_prio, self._live_flights)
            if adm.joined_flight is not None:
                pruned_join = self._verify_or_promote_joined_wait_edges(adm, spec)
                if pruned_join is not None:
                    spec = pruned_join
                    continue
                typed_joined: StepFlight[TResult] = adm.joined_flight
                abort_fn = lambda cur_s=spec: self._drain_caller_borrowed_serialize_locks(cur_s)
                return _await_step_flight(
                    typed_joined, adm, spec.cancel_token, timeout_sec, is_follower=True, on_early_abort=abort_fn
                )

            own_flight_raw = (
                adm.holder.flight
                if adm.holder is not None
                else (adm.waiter.holder.flight if adm.waiter is not None else None)
            )
            if own_flight_raw is not None:
                typed_own: StepFlight[TResult] = own_flight_raw
                try:
                    threading.Thread(
                        target=self._drive_coalesce_flight,
                        args=(bucket, adm, spec, leader_fn, extract_release_guard),
                        name=f"yscb-coalesce-{spec.resource_key}",
                        daemon=True,
                    ).start()
                except BaseException as exc:
                    _abort_admission_on_error(bucket, adm, exc)
                    if adm.detach_fn is not None:
                        adm.detach_fn()
                    raise
                abort_own = lambda cur_s=spec: self._drain_caller_borrowed_serialize_locks(cur_s)
                return _await_step_flight(
                    typed_own, adm, spec.cancel_token, timeout_sec, is_follower=False, on_early_abort=abort_own
                )

            bypass_retry = False
            try:
                holder = adm.holder
                if holder is None:
                    waiter_adm = require_non_none(adm.waiter)
                    holder = self._await_registered_waiter(bucket, waiter_adm, spec)
                    if waiter_adm.cross_proc_bypass:
                        bypass_retry = True
                    elif waiter_adm.reentrant_grant is not None:
                        return _run_reentrant_step(
                            bucket,
                            waiter_adm.reentrant_grant,
                            lambda s=spec: self._merge_known_remote_callers(s),
                            own_prio,
                            timeout_sec,
                            self._effective_locks_dir(),
                            leader_fn,
                            extract_release_guard,
                        )
                if not bypass_retry:
                    res = self._run_under_os_file_lock(bucket, holder, spec.resource_key, leader_fn, extract_release_guard)
                    return CoordinatedExecution(False, -1, res)
            except BaseException as exc:
                _abort_admission_on_error(bucket, adm, exc)
                raise
            finally:
                if adm.detach_fn is not None:
                    adm.detach_fn()
                    adm.detach_fn = None
            if bypass_retry:
                continue

    def _verify_or_promote_joined_wait_edges(
        self,
        adm: _BucketAdmission,
        spec: ResourceAcquireSpec,
    ) -> Optional[ResourceAcquireSpec]:
        cand_flight = require_non_none(adm.joined_flight)
        try:
            local_conflict = self._check_local_joined_wait_and_poll_edges(cand_flight, spec)
            if local_conflict is not None:
                ident, det = local_conflict
                return _reject_or_prune_late_join_detail(adm, spec, ident, det)
            rem_conflict = self._notify_remote_workspaces_flight_join(cand_flight, spec)
            if rem_conflict is not None:
                ident_r, err_det = rem_conflict
                return _reject_or_prune_late_join_detail(adm, spec, ident_r, err_det)
            return None
        except BaseException:
            if adm.detach_fn is not None:
                adm.detach_fn()
                adm.detach_fn = None
            raise


def _has_any_holder_lingering_locked(holder: _ActiveHolder) -> bool:
    if holder.self_exit_guard is not None and not holder.self_exit_guard.is_set():
        return True
    return any(not g.is_set() for g in holder.lingering_guards)


def _drain_holder_lingering_guards(
    bucket: _ResourceBucket,
    holder: _ActiveHolder,
    *,
    max_wait_sec: float = 30.0,
) -> None:
    deadline = time.monotonic() + max_wait_sec
    while True:
        with bucket.cond:
            pending = [g for g in holder.lingering_guards if not g.is_set()]
            holder.lingering_guards = pending
            self_g = holder.self_exit_guard
            if self_g is not None and self_g.is_set():
                holder.self_exit_guard = None
                self_g = None
            next_g = pending[0] if pending else self_g
            timed_out = next_g is not None and time.monotonic() >= deadline
            if next_g is None or timed_out:
                holder.os_lock_live = False
        if next_g is None or timed_out:
            return
        next_g.wait(timeout=max(0.01, min(0.25, deadline - time.monotonic())))


def _wait_active_borrowed_guards_for_caller(
    bucket: _ResourceBucket,
    spec: ResourceAcquireSpec,
    *,
    deadline: Optional[float] = None,
) -> None:
    eff_dl = deadline if deadline is not None else (time.monotonic() + 2.0)
    pins_to_wait: list[HostPath] = []
    while True:
        with bucket.cond:
            candidates = (*( (bucket.active,) if bucket.active is not None else () ), *bucket.cross_proc_reentrant)
            matched = [c for c in candidates if _spec_matches_ident(spec, _build_active_holder_ident(c))]
            if not matched:
                return
            next_g: Optional[threading.Event] = None
            for act in matched:
                pending = [g for g in act.lingering_guards if not g.is_set()]
                act.lingering_guards = pending
                if next_g is None and pending:
                    next_g = pending[0]
            if next_g is None:
                pins_to_wait = [act.pin_path for act in matched if act.os_lock_live and act.pin_path is not None]
        if next_g is None or time.monotonic() >= eff_dl:
            break
        next_g.wait(timeout=max(0.01, min(0.2, eff_dl - time.monotonic())))
    for pin_path in pins_to_wait:
        rem_pin = eff_dl - time.monotonic()
        if rem_pin <= 0.0:
            break
        pin_gate = FileLock(pin_path, allow_transitions=False)
        try:
            if pin_gate.acquire(shared=False, blocking=True, timeout_sec=max(0.02, rem_pin)):
                pin_gate.release()
        except YscbError:
            return


def _defer_lingering_reentrant_release(
    bucket: _ResourceBucket,
    holder: _ActiveHolder,
    reentrant_pin: Optional[FileLock],
) -> None:
    def _wait_and_release_pin() -> None:
        try:
            _drain_holder_lingering_guards(bucket, holder)
        finally:
            try:
                if reentrant_pin is not None:
                    reentrant_pin.release()
            finally:
                _release_holder_if_active(bucket, holder)

    try:
        threading.Thread(target=_wait_and_release_pin, name="yscb-pin-lingering", daemon=True).start()
    except BaseException:
        _wait_and_release_pin()
        raise


def _finalize_holder_os_lock(
    bucket: _ResourceBucket,
    holder: _ActiveHolder,
    paths: CrossProcessLockPaths,
    owns_os_lock: bool,
    has_lingering: bool,
    reentrant_pin: Optional[FileLock],
) -> tuple[bool, Optional[FileLock]]:
    if has_lingering and owns_os_lock:
        if reentrant_pin is not None:
            reentrant_pin.release()
        _defer_lingering_lock_release(bucket, holder, paths)
        return (True, None)
    if has_lingering:
        _defer_lingering_reentrant_release(bucket, holder, reentrant_pin)
        return (True, None)
    if reentrant_pin is not None:
        reentrant_pin.release()
    if owns_os_lock:
        unlink_owner_under_pin(paths.owner_path, paths.pin_path, paths.lock_file.release)
    return (False, None)


def _run_reentrant_step(
    bucket: _ResourceBucket,
    grant: _ReentrantGrant,
    spec_fn: Callable[[], ResourceAcquireSpec],
    own_prio: PriorityHandle,
    timeout_sec: Optional[float],
    locks_dir: Optional[HostPath],
    leader_fn: Callable[[PriorityHandle, CancellationToken, Optional[StepFlight[TResult]]], TResult],
    extract_release_guard: Optional[Callable[[TResult], Optional[threading.Event]]],
) -> CoordinatedExecution[TResult]:
    spec = spec_fn()
    reentrant, step_guard = grant.holder, grant.step_guard
    try:
        if own_prio.current == ExecutionPriority.FOREGROUND:
            reentrant.priority_handle.elevate_to_foreground()
        with _serial_execution_turn(
            bucket,
            spec.turn_id,
            spec.call_tree_id,
            spec.call_stack,
            spec.coalesce_callers,
            lambda top: _spec_matches_ident(spec_fn(), top),
            spec.cancel_token,
            timeout_sec,
            spec.resource_key,
            locks_dir if reentrant.os_lock_live else None,
        ):
            sub_res = leader_fn(reentrant.priority_handle, spec.cancel_token, None)
        sub_guard = extract_release_guard(sub_res) if extract_release_guard is not None else None
        if sub_guard is not None and not sub_guard.is_set():
            with bucket.cond:
                reentrant.lingering_guards.append(sub_guard)
        return CoordinatedExecution(False, -1, sub_res)
    finally:
        step_guard.set()


def _is_effective_serialize(mode: ConcurrencyMode, allow_step_coalesce: bool) -> bool:
    return mode == ConcurrencyMode.SERIALIZE or (mode == ConcurrencyMode.COALESCE and not allow_step_coalesce)


def _spec_matches_ident(spec: ResourceAcquireSpec, ident: HolderIdentity) -> bool:
    leaf = spec.call_stack[-1] if spec.call_stack else None
    same_tree = (bool(spec.call_tree_id) and ident.tree_id == spec.call_tree_id) or (
        bool(ident.turn_id) and ident.turn_id == spec.turn_id
    )
    if same_tree and _is_ancestor_stack(ident.stack, spec.call_stack):
        return True
    if bool(ident.flight_id) and any(fl.flight_id == ident.flight_id for fl in spec.enclosing_flights):
        return True
    if any(fl.has_reentrant_caller(ident, leaf) for fl in spec.enclosing_flights):
        return True
    if any(
        _view_matches_holder(v, ident, extra_flights=spec.coalesce_flights, leaf_frame=leaf)
        for v in spec.coalesce_callers
    ):
        return True
    return any(_spec_matches_ident(spec, alt) for alt in ident.alt_owners)


def _try_evict_partial_flight_callers(
    spec: ResourceAcquireSpec,
    ident: HolderIdentity,
    exc: YscbError,
) -> Optional[ResourceAcquireSpec]:
    """Return pruned spec when only a subset of enclosing flight callers conflicted and were evicted."""
    same_direct = (
        (bool(spec.call_tree_id) and ident.tree_id == spec.call_tree_id)
        or (bool(ident.turn_id) and ident.turn_id == spec.turn_id)
        or (bool(ident.flight_id) and ident.flight_id in spec.coalesce_flights)
        or (bool(ident.tree_id) and ident.tree_id in spec.coalesce_flights)
    )
    if same_direct or not spec.enclosing_flights:
        return None
    leaf = spec.call_stack[-1] if spec.call_stack else None
    evicted_any = False
    for ef in spec.enclosing_flights:
        ev, surv = ef.evict_callers_matching_holder(ident, leaf, exc)
        if ev and surv:
            evicted_any = True
    if not evicted_any:
        return None
    rem_views = tuple(
        v for v in spec.coalesce_callers if not _view_matches_holder(v, ident, extra_flights=spec.coalesce_flights, leaf_frame=leaf)
    )
    pruned = replace(spec, coalesce_callers=rem_views)
    return pruned if not _spec_matches_ident(pruned, ident) else None


def _build_active_holder_ident(act: _ActiveHolder) -> HolderIdentity:
    fl_alts = (
        tuple(HolderIdentity(v.turn_id, v.call_tree_id, "", v.call_stack) for v in act.flight.snapshot_caller_views())
        if act.flight is not None
        else ()
    )
    return HolderIdentity(
        turn_id=act.turn_id,
        tree_id=act.call_tree_id,
        flight_id=act.flight.flight_id if act.flight is not None else "",
        stack=act.call_stack,
        alt_owners=fl_alts,
    )


def _build_joined_views_for_flight(flight_id: str, spec: ResourceAcquireSpec) -> tuple[CoalesceCallerView, ...]:
    own_fids = (*spec.coalesce_flights, flight_id) if flight_id not in spec.coalesce_flights else spec.coalesce_flights
    leaf_tail = spec.call_stack[-1:]
    if spec.coalesce_callers:
        return tuple(
            replace(
                v,
                call_stack=(*v.call_stack, *leaf_tail) if v.call_stack[-1:] != leaf_tail else v.call_stack,
                flight_ids=(*v.flight_ids, *(f for f in own_fids if f not in v.flight_ids)),
            )
            for v in spec.coalesce_callers
        )
    return (
        CoalesceCallerView(
            turn_id=spec.turn_id,
            call_tree_id=spec.call_tree_id or spec.turn_id,
            call_stack=spec.call_stack,
            caller_hops=spec.caller_hops,
            flight_ids=own_fids,
            in_event_chain=spec.in_event_chain,
        ),
    )


def _reject_or_prune_late_join_detail(
    adm: _BucketAdmission,
    spec: ResourceAcquireSpec,
    conflict_ident: HolderIdentity,
    det: ErrorDetail,
) -> Optional[ResourceAcquireSpec]:
    if adm.detach_fn is not None:
        adm.detach_fn()
        adm.detach_fn = None
    err = YscbError(det.code, det.message, remediation=det.remediation, source_task=det.source_task)
    pruned = _try_evict_partial_flight_callers(spec, conflict_ident, err)
    if pruned is not None:
        return pruned
    raise err


def _reentrancy_error_detail(resource_key: str, source_task: Optional[str] = None) -> ErrorDetail:
    return ErrorDetail(
        ErrorCode.ILLEGAL_LOCK_REENTRANCY,
        f"Cannot re-enter held resource_key '{resource_key}' via StepFlight.",
        source_task=source_task,
    )


def _check_poll_item_reentrancy_conflict(
    p_item: _PollingOsHolder,
    probe_spec: ResourceAcquireSpec,
) -> Optional[tuple[HolderIdentity, ErrorDetail]]:
    live_ow = _read_live_cross_proc_owner(p_item.owner_path)
    if live_ow is None or not _spec_matches_ident(
        replace(probe_spec, call_stack=p_item.holder.call_stack), live_ow[0]
    ):
        return None
    if live_ow[1] != ConcurrencyMode.SERIALIZE.value or not _is_effective_serialize(
        p_item.holder.mode, p_item.holder.allow_step_coalesce
    ):
        src_t = str(p_item.holder.call_stack[-1][1]) if p_item.holder.call_stack else None
        return (live_ow[0], _reentrancy_error_detail(p_item.resource_key, src_t))
    return None


def _check_join_task_cycle(
    target_stack: tuple[tuple[HostPath, TaskId], ...],
    views: Sequence[CoalesceCallerView],
) -> Optional[tuple[HolderIdentity, ErrorDetail]]:
    if not target_stack:
        return None
    leaf = target_stack[-1]
    for v in views:
        if leaf in v.call_stack:
            ident = HolderIdentity(v.turn_id, v.call_tree_id, "", v.call_stack)
            det = ErrorDetail(
                ErrorCode.CALL_CYCLE_DETECTED,
                f"Synchronous task cycle on '{leaf[1]}' via StepFlight.",
                source_task=str(leaf[1]),
            )
            return (ident, det)
    return None


def _check_holder_or_flight_task_cycle(
    holder: _ActiveHolder,
    fallback_stack: tuple[tuple[HostPath, TaskId], ...],
    views: Sequence[CoalesceCallerView],
) -> Optional[tuple[HolderIdentity, ErrorDetail]]:
    cyc = _check_join_task_cycle(fallback_stack, views)
    if cyc is not None or holder.flight is None:
        return cyc
    for hv in holder.flight.snapshot_caller_views():
        sub = _check_join_task_cycle(hv.call_stack, views)
        if sub is not None:
            return sub
    return None


def _holder_depends_on_fids(holder: _ActiveHolder, target_fids: frozenset[str]) -> bool:
    if any(f in target_fids for f in _all_holder_flight_ids(holder)):
        return True
    if holder.flight is not None and holder.flight.depends_on_flight_ids(target_fids):
        return True
    return any(ef.depends_on_flight_ids(target_fids) for ef in holder.enclosing_flights)


def _wait_edge_depends_on_fids(
    w_waiter: _QueuedWaiter,
    w_spec: ResourceAcquireSpec,
    target_fids: frozenset[str],
) -> bool:
    if any(f in target_fids for f in _all_spec_flight_ids(w_spec)):
        return True
    if w_waiter.holder.flight is not None and w_waiter.holder.flight.depends_on_flight_ids(target_fids):
        return True
    return any(ef.depends_on_flight_ids(target_fids) for ef in w_spec.enclosing_flights)


def _try_promote_or_detect_wait_conflict(
    w_bucket: _ResourceBucket,
    w_waiter: _QueuedWaiter,
    join_spec: ResourceAcquireSpec,
    *,
    locks_dir: Optional[HostPath] = None,
    resource_key: Optional[str] = None,
) -> Optional[HolderIdentity]:
    with w_bucket.cond:
        if w_waiter not in w_bucket.waiters:
            return None
        wh = w_waiter.holder
        candidates = (*( (w_bucket.active,) if w_bucket.active is not None else () ), *w_bucket.cross_proc_reentrant)
        for w_act in candidates:
            w_ident = _build_active_holder_ident(w_act)
            if not _spec_matches_ident(join_spec, w_ident):
                continue
            both_ser = (
                wh.flight is None
                and _is_effective_serialize(w_act.mode, w_act.allow_step_coalesce)
                and _is_effective_serialize(wh.mode, wh.allow_step_coalesce)
            )
            if not both_ser:
                return w_ident
            if not w_act.os_lock_live:
                continue
            step_guard = threading.Event()
            w_act.lingering_guards.append(step_guard)
            w_waiter.reentrant_grant = _ReentrantGrant(w_act, step_guard)
            w_waiter.promoted = True
            w_bucket.waiters.remove(w_waiter)
            w_waiter.wake_event.set()
            return None
    if locks_dir is None or not resource_key:
        return None
    lock_paths = CrossProcessLockPaths.for_stem(
        locks_dir, _build_resource_lock_stem(resource_key), allow_transitions=False
    )
    live_ow = _read_live_cross_proc_owner(lock_paths.owner_path)
    if live_ow is None or not _spec_matches_ident(join_spec, live_ow[0]):
        return None
    with w_bucket.cond:
        if w_waiter not in w_bucket.waiters:
            return None
        wh = w_waiter.holder
        both_ser = (
            wh.flight is None
            and live_ow[1] == ConcurrencyMode.SERIALIZE.value
            and _is_effective_serialize(wh.mode, wh.allow_step_coalesce)
        )
        if not both_ser:
            return live_ow[0]
        w_waiter.cross_proc_bypass = True
        w_waiter.promoted = True
        w_bucket.waiters.remove(w_waiter)
        w_waiter.wake_event.set()
        return None


RemoteEvictFn = Callable[[ResourceAcquireSpec, HolderIdentity, YscbError], Optional[ResourceAcquireSpec]]


def _recheck_enqueued_waiter_reentrancy(
    bucket: _ResourceBucket,
    waiter: _QueuedWaiter,
    spec: ResourceAcquireSpec,
    remote_evict_fn: Optional[RemoteEvictFn] = None,
    *,
    locks_dir: Optional[HostPath] = None,
) -> None:
    cur_spec = spec
    while True:
        conflict_ident = _try_promote_or_detect_wait_conflict(
            bucket,
            waiter,
            cur_spec,
            locks_dir=locks_dir,
            resource_key=cur_spec.resource_key,
        )
        if conflict_ident is None:
            return
        src_tid = str(cur_spec.call_stack[-1][1]) if cur_spec.call_stack else None
        err = YscbError(
            ErrorCode.ILLEGAL_LOCK_REENTRANCY,
            f"Cannot re-enter resource_key '{cur_spec.resource_key}' with {cur_spec.mode.value} on same CallStack.",
            source_task=src_tid,
        )
        pruned = _try_evict_partial_flight_callers(cur_spec, conflict_ident, err)
        if pruned is None and remote_evict_fn is not None:
            pruned = remote_evict_fn(cur_spec, conflict_ident, err)
        if pruned is not None:
            cur_spec = pruned
            continue
        _cleanup_failed_waiter_promotion(bucket, waiter, err)
        raise err


def _check_same_stack_reentrancy(
    bucket: _ResourceBucket,
    spec: ResourceAcquireSpec,
    remote_evict_fn: Optional[RemoteEvictFn] = None,
) -> tuple[Optional[_ReentrantGrant], ResourceAcquireSpec]:
    matched_pair: Optional[_ReentrantGrant] = None
    conflict_ident: Optional[HolderIdentity] = None
    with bucket.cond:
        candidates = (*( (bucket.active,) if bucket.active is not None else () ), *bucket.cross_proc_reentrant)
        for cand in candidates:
            ident = _build_active_holder_ident(cand)
            if not _spec_matches_ident(spec, ident):
                continue
            if _is_effective_serialize(cand.mode, cand.allow_step_coalesce) and _is_effective_serialize(
                spec.mode, spec.allow_step_coalesce
            ):
                if cand.os_lock_live:
                    step_guard = threading.Event()
                    cand.lingering_guards.append(step_guard)
                    matched_pair = _ReentrantGrant(cand, step_guard)
                    break
                continue
            conflict_ident = ident
            break
    if matched_pair is not None:
        return (matched_pair, spec)
    if conflict_ident is None:
        return (None, spec)
    src_tid = str(spec.call_stack[-1][1]) if spec.call_stack else None
    err = YscbError(
        ErrorCode.ILLEGAL_LOCK_REENTRANCY,
        f"Cannot re-enter resource_key '{spec.resource_key}' with {spec.mode.value} on same CallStack.",
        source_task=src_tid,
    )
    pruned = _try_evict_partial_flight_callers(spec, conflict_ident, err)
    if pruned is None and remote_evict_fn is not None:
        pruned = remote_evict_fn(spec, conflict_ident, err)
    if pruned is not None:
        return (None, pruned)
    raise err

def _compose_detach(
    base_detach: Optional[Callable[[], None]],
    extra_unreg: Callable[[], None],
) -> Callable[[], None]:
    def _detach_both() -> None:
        try:
            if base_detach is not None:
                base_detach()
        finally:
            extra_unreg()

    return _detach_both


def _apply_post_admit_notifications(
    bucket: _ResourceBucket,
    elevate_targets: list[PriorityHandle],
    tokens_to_cancel: list[tuple[CancellationToken, str]],
    prio_forwards: Sequence[tuple[PriorityHandle, PriorityHandle]],
    adm: _BucketAdmission,
) -> None:
    for ph in elevate_targets:
        ph.elevate_to_foreground()
    if elevate_targets:
        with bucket.cond:
            if bucket.waiters:
                _sort_waiters(bucket.waiters)
    for src_ph, dst_ph in prio_forwards:
        unreg_pf = src_ph.register_listener(lambda _p, dst=dst_ph: dst.elevate_to_foreground())
        adm.detach_fn = _compose_detach(adm.detach_fn, unreg_pf)
    for tok, reason_msg in tokens_to_cancel:
        tok.cancel(preempted=True, reason=reason_msg)


def _make_flight_caller_reg(spec: ResourceAcquireSpec) -> FlightCallerRegistration:
    dl = (time.monotonic() + ms_to_safe_sec(spec.timeout_ms)) if spec.timeout_ms is not None else None
    return FlightCallerRegistration(
        caller_turn_id=spec.turn_id,
        call_tree_id=spec.call_tree_id,
        caller_stack=spec.call_stack,
        caller_hops=spec.caller_hops,
        step_cancel=spec.cancel_token,
        turn_cancel=spec.turn_cancel_token or spec.cancel_token,
        enclosing_flights=spec.enclosing_flights,
        inherited_views=spec.coalesce_callers,
        coalesce_flights=spec.coalesce_flights,
        turn_entry_stack=spec.turn_entry_stack,
        in_event_chain=spec.in_event_chain,
        deadline=dl,
    )


def _try_join_existing_coalesce(
    bucket: _ResourceBucket,
    spec: ResourceAcquireSpec,
    own_prio: PriorityHandle,
    elevate_targets: list[PriorityHandle],
    prio_forwards: list[tuple[PriorityHandle, PriorityHandle]],
    adm: _BucketAdmission,
) -> bool:
    reg = _make_flight_caller_reg(spec)
    act = bucket.active
    if (
        act is not None
        and act.mode == ConcurrencyMode.COALESCE
        and act.allow_step_coalesce
        and act.equiv_key == spec.equiv_key
        and act.flight is not None
        and not act.flight.done.is_set()
    ):
        pid, d_act = act.flight.add_caller(reg, spec.on_progress)
        if d_act is not None:
            if own_prio.current == ExecutionPriority.FOREGROUND:
                elevate_targets.append(act.priority_handle)
            else:
                prio_forwards.append((own_prio, act.priority_handle))
            adm.joined_flight, adm.caller_slot_id, adm.detach_fn = act.flight, pid, d_act
            return True

    for w in bucket.waiters:
        wh = w.holder
        if not (
            wh.mode == ConcurrencyMode.COALESCE
            and wh.allow_step_coalesce
            and wh.equiv_key == spec.equiv_key
            and wh.flight is not None
            and not wh.flight.done.is_set()
        ):
            continue
        pid_w, d_w = wh.flight.add_caller(reg, spec.on_progress)
        if d_w is None:
            continue

        if own_prio.current == ExecutionPriority.FOREGROUND:
            elevate_targets.append(wh.priority_handle)
            if bucket.active is not None:
                elevate_targets.append(bucket.active.priority_handle)
        else:
            prio_forwards.append((own_prio, wh.priority_handle))
        adm.joined_flight, adm.caller_slot_id, adm.detach_fn = wh.flight, pid_w, d_w
        return True
    return False


def _can_preempt_holder(incoming_prio: ExecutionPriority, target: _ActiveHolder) -> bool:
    if _is_effective_serialize(target.mode, target.allow_step_coalesce):
        return False
    if incoming_prio == ExecutionPriority.BACKGROUND and target.priority_handle.current == ExecutionPriority.FOREGROUND:
        return False
    return True


def _collect_preempt_targets(
    bucket: _ResourceBucket,
    resource_key: str,
    incoming_prio: ExecutionPriority,
    tokens_to_cancel: list[tuple[CancellationToken, str]],
) -> None:
    if bucket.active is not None and _can_preempt_holder(incoming_prio, bucket.active):
        tokens_to_cancel.append((bucket.active.cancel_token, f"Preempted on '{resource_key}'"))
    for w in list(bucket.waiters):
        if w.holder.mode == ConcurrencyMode.PREEMPT and _can_preempt_holder(incoming_prio, w.holder):
            w.aborted_preempt = True
            tokens_to_cancel.append((w.holder.cancel_token, f"Superseded in queue on '{resource_key}'"))
            bucket.waiters.remove(w)


def _admit_or_enqueue_in_bucket(
    bucket: _ResourceBucket,
    spec: ResourceAcquireSpec,
    own_prio: PriorityHandle,
    live_flights: weakref.WeakValueDictionary[str, StepFlight[object]],
) -> _BucketAdmission:
    adm = _BucketAdmission()
    elevate_targets: list[PriorityHandle] = []
    prio_forwards: list[tuple[PriorityHandle, PriorityHandle]] = []
    tokens_to_cancel: list[tuple[CancellationToken, str]] = []

    with bucket.cond:
        spec.cancel_token.raise_if_cancelled()
        joined = False
        if spec.mode == ConcurrencyMode.COALESCE and spec.allow_step_coalesce:
            joined = _try_join_existing_coalesce(bucket, spec, own_prio, elevate_targets, prio_forwards, adm)
        if not joined:
            if spec.mode == ConcurrencyMode.PREEMPT:
                _collect_preempt_targets(bucket, str(spec.resource_key), own_prio.current, tokens_to_cancel)
            flight: Optional[StepFlight[object]] = None
            eff_token = spec.cancel_token
            holder_prio = own_prio
            if spec.mode == ConcurrencyMode.COALESCE and spec.allow_step_coalesce:
                flight_prio = PriorityHandle(own_prio.current)
                holder_prio = flight_prio
                if own_prio.current != ExecutionPriority.FOREGROUND:
                    prio_forwards.append((own_prio, flight_prio))
                flight = StepFlight(flight_prio)
                adm.caller_slot_id, adm.detach_fn = flight.add_caller(_make_flight_caller_reg(spec), spec.on_progress)
                eff_token = flight.cancel_group.host_token
            init_dl = (time.monotonic() + ms_to_safe_sec(spec.timeout_ms)) if spec.timeout_ms is not None else None
            new_holder = _ActiveHolder(
                turn_id=flight.flight_id if flight is not None else spec.turn_id,
                call_stack=spec.call_stack[-1:] if flight is not None else spec.call_stack,
                mode=spec.mode,
                equiv_key=spec.equiv_key,
                priority_handle=holder_prio,
                cancel_token=eff_token,
                allow_step_coalesce=spec.allow_step_coalesce,
                flight=flight,
                call_tree_id=flight.flight_id if flight is not None else spec.call_tree_id,
                enclosing_flights=() if flight is not None else spec.enclosing_flights,
                coalesce_callers=() if flight is not None else spec.coalesce_callers,
                coalesce_flights=() if flight is not None else spec.coalesce_flights,
                deadline=init_dl,
            )
            if bucket.active is None and not bucket.waiters:
                adm.holder = new_holder
                bucket.active = new_holder
            else:
                if own_prio.current == ExecutionPriority.FOREGROUND and bucket.active is not None:
                    elevate_targets.append(bucket.active.priority_handle)
                bucket.seq_counter += 1
                adm.waiter = _QueuedWaiter(seq=bucket.seq_counter, holder=new_holder)
                bucket.waiters.append(adm.waiter)
                _sort_waiters(bucket.waiters)
            own_fl = adm.holder.flight if adm.holder is not None else (adm.waiter.holder.flight if adm.waiter is not None else None)
            if own_fl is not None:
                live_flights[own_fl.flight_id] = own_fl

    _apply_post_admit_notifications(bucket, elevate_targets, tokens_to_cancel, prio_forwards, adm)
    return adm

def _abort_cancelled_waiter_flight(waiter: _QueuedWaiter, default_code: Optional[ErrorCode] = None) -> None:
    fl = waiter.holder.flight
    tok = waiter.holder.cancel_token
    if fl is None:
        return
    fl.cancel_group.close_all()
    if not fl.done.is_set():
        code = default_code or (ErrorCode.TASK_PREEMPTED if tok.is_preempted else ErrorCode.TASK_CANCELLED)
        fl.complete(raised_exc=YscbError(code, tok.reason or "Waiter cancelled"))


def _release_and_promote_next_locked(
    bucket: _ResourceBucket,
) -> tuple[list[_QueuedWaiter], Optional[PriorityHandle]]:
    aborted: list[_QueuedWaiter] = []
    while bucket.waiters:
        _sort_waiters(bucket.waiters)
        nxt = bucket.waiters.pop(0)
        if nxt.holder.cancel_token.is_cancelled:
            aborted.append(nxt)
            nxt.wake_event.set()
            continue
        has_fg_behind = any(
            w.holder.priority_handle.current == ExecutionPriority.FOREGROUND
            and not w.holder.cancel_token.is_cancelled
            for w in bucket.waiters
        )
        elevate_ph = nxt.holder.priority_handle if has_fg_behind else None
        nxt.promoted = True
        bucket.active = nxt.holder
        nxt.wake_event.set()
        return (aborted, elevate_ph)
    bucket.active = None
    return (aborted, None)


def _flush_post_promote_callbacks(
    aborted: list[_QueuedWaiter],
    elevate_ph: Optional[PriorityHandle],
) -> None:
    for w in aborted:
        _abort_cancelled_waiter_flight(w)
    if elevate_ph is not None:
        elevate_ph.elevate_to_foreground()


def _release_holder_if_active(bucket: _ResourceBucket, holder: _ActiveHolder) -> None:
    holder.pin_path = None
    aborted: list[_QueuedWaiter] = []
    elevate_ph: Optional[PriorityHandle] = None
    with bucket.cond:
        if bucket.active is holder:
            aborted, elevate_ph = _release_and_promote_next_locked(bucket)
    _flush_post_promote_callbacks(aborted, elevate_ph)


def _decode_owner_stack(raw_stack: object) -> tuple[tuple[HostPath, TaskId], ...]:
    if not isinstance(raw_stack, list):
        return ()
    entries: list[tuple[HostPath, TaskId]] = []
    for item in raw_stack:
        if not (isinstance(item, list) and len(item) == 2 and isinstance(item[0], str) and isinstance(item[1], str)):
            return ()
        try:
            entries.append((HostPath(item[0]), TaskId(item[1])))
        except (ValueError, OSError):
            return ()
    return tuple(entries)


def _holder_matches_cross_proc_owner(holder: _ActiveHolder, ident: HolderIdentity) -> bool:
    leaf = holder.call_stack[-1] if holder.call_stack else None
    if holder.call_tree_id and holder.call_tree_id == ident.tree_id and _is_ancestor_stack(ident.stack, holder.call_stack):
        return True
    if bool(ident.flight_id) and (
        ident.flight_id in holder.coalesce_flights
        or any(ef.flight_id == ident.flight_id for ef in holder.enclosing_flights)
    ) and (not ident.stack or _is_ancestor_subslice(ident.stack, holder.call_stack)):
        return True
    if holder.flight is not None and holder.flight.has_reentrant_caller(ident, leaf):
        return True
    if any(ef.has_reentrant_caller(ident, leaf) for ef in holder.enclosing_flights):
        return True
    if any(
        _view_matches_holder(v, ident, extra_flights=holder.coalesce_flights, leaf_frame=leaf)
        for v in holder.coalesce_callers
    ):
        return True
    return any(_holder_matches_cross_proc_owner(holder, alt) for alt in ident.alt_owners)


def _decode_alt_owners(raw_callers: object) -> tuple[HolderIdentity, ...]:
    if not isinstance(raw_callers, list):
        return ()
    out: list[HolderIdentity] = []
    for item in raw_callers:
        if isinstance(item, dict):
            raw_ct = item.get("call_tree_id")
            if type(raw_ct) is str and raw_ct:
                raw_tid = item.get("turn_id")
                tid_s = raw_tid if type(raw_tid) is str else ""
                out.append(HolderIdentity(tid_s, raw_ct, "", _decode_owner_stack(item.get("call_stack"))))
    return tuple(out)


def _read_live_cross_proc_owner(owner_path: HostPath) -> Optional[tuple[HolderIdentity, str]]:
    doc = read_live_owner_dict(owner_path)
    if doc is None:
        return None
    raw_tree = doc.get("call_tree_id")
    if type(raw_tree) is not str or not raw_tree:
        return None
    raw_turn = doc.get("turn_id")
    raw_fid = doc.get("flight_id")
    raw_mode = doc.get("mode")
    ident = HolderIdentity(
        turn_id=raw_turn if type(raw_turn) is str else "",
        tree_id=raw_tree,
        flight_id=raw_fid if type(raw_fid) is str else "",
        stack=_decode_owner_stack(doc.get("call_stack")),
        alt_owners=_decode_alt_owners(doc.get("callers")),
    )
    return (ident, raw_mode if type(raw_mode) is str else "")


def _try_acquire_incoming_cross_proc_reentry(
    locks_dir: HostPath,
    spec: ResourceAcquireSpec,
    timeout_sec: Optional[float],
    remote_evict_fn: Optional[RemoteEvictFn] = None,
) -> tuple[Optional[FileLock], ResourceAcquireSpec]:
    if not spec.resource_key:
        return (None, spec)
    stem = _build_resource_lock_stem(spec.resource_key)
    paths = CrossProcessLockPaths.for_stem(locks_dir, stem, allow_transitions=False)
    cur_spec = spec
    while True:
        live_owner = _read_live_cross_proc_owner(paths.owner_path)
        if live_owner is None:
            return (None, cur_spec)
        ident, owner_mode = live_owner
        if not _spec_matches_ident(cur_spec, ident):
            return (None, cur_spec)
        if owner_mode == ConcurrencyMode.SERIALIZE.value and _is_effective_serialize(
            cur_spec.mode, cur_spec.allow_step_coalesce
        ):
            pin_tmo = timeout_sec if timeout_sec is not None else 10.0
            pin_lk = acquire_verified_cross_proc_pin(
                paths.owner_path,
                paths.pin_path,
                lambda ow: (
                    (lo := _read_live_cross_proc_owner(ow)) is not None
                    and lo[1] == ConcurrencyMode.SERIALIZE.value
                    and _spec_matches_ident(cur_spec, lo[0])
                ),
                timeout_sec=pin_tmo,
                cancel_token=cur_spec.cancel_token,
            )
            return (pin_lk, cur_spec)
        src_tid = str(cur_spec.call_stack[-1][1]) if cur_spec.call_stack else None
        err = YscbError(
            ErrorCode.ILLEGAL_LOCK_REENTRANCY,
            f"Cannot re-enter resource_key '{cur_spec.resource_key}' with {cur_spec.mode.value} across process CallStack.",
            source_task=src_tid,
        )
        pruned = _try_evict_partial_flight_callers(cur_spec, ident, err)
        if pruned is None and remote_evict_fn is not None:
            pruned = remote_evict_fn(cur_spec, ident, err)
        if pruned is not None:
            cur_spec = pruned
            continue
        raise err


def _spawn_borrowed_lingering_unpin(
    bucket: _ResourceBucket,
    borrowed_holder: _ActiveHolder,
    pin_lk: FileLock,
) -> None:
    def _drain_and_unpin() -> None:
        try:
            _drain_holder_lingering_guards(bucket, borrowed_holder)
        finally:
            with bucket.cond:
                if borrowed_holder in bucket.cross_proc_reentrant:
                    bucket.cross_proc_reentrant.remove(borrowed_holder)
            pin_lk.release()

    try:
        threading.Thread(target=_drain_and_unpin, name="yscb-borrowed-pin", daemon=True).start()
    except BaseException:
        _drain_and_unpin()
        raise


def _run_cross_proc_borrowed_step(
    bucket: _ResourceBucket,
    pin_lk: FileLock,
    locks_dir: HostPath,
    spec_fn: Callable[[], ResourceAcquireSpec],
    own_prio: PriorityHandle,
    timeout_sec: Optional[float],
    leader_fn: Callable[[PriorityHandle, CancellationToken, Optional[StepFlight[TResult]]], TResult],
    extract_release_guard: Optional[Callable[[TResult], Optional[threading.Event]]],
) -> CoordinatedExecution[TResult]:
    spec = spec_fn()
    borrowed_holder = _ActiveHolder(
        turn_id=spec.turn_id,
        call_stack=spec.call_stack,
        mode=spec.mode,
        equiv_key=spec.equiv_key,
        priority_handle=own_prio,
        cancel_token=spec.cancel_token,
        allow_step_coalesce=spec.allow_step_coalesce,
        flight=None,
        call_tree_id=spec.call_tree_id,
        enclosing_flights=spec.enclosing_flights,
        coalesce_callers=spec.coalesce_callers,
        coalesce_flights=spec.coalesce_flights,
        os_lock_live=True,
    )
    with bucket.cond:
        bucket.cross_proc_reentrant.append(borrowed_holder)
    deferred_pin = False
    try:
        with _serial_execution_turn(
            bucket,
            spec.turn_id,
            spec.call_tree_id,
            spec.call_stack,
            spec.coalesce_callers,
            lambda top: _spec_matches_ident(spec_fn(), top),
            spec.cancel_token,
            timeout_sec,
            spec.resource_key,
            locks_dir,
        ):
            res = leader_fn(own_prio, spec.cancel_token, None)
        guard_ev = extract_release_guard(res) if extract_release_guard is not None else None
        with bucket.cond:
            if guard_ev is not None and not guard_ev.is_set():
                borrowed_holder.self_exit_guard = guard_ev
            has_lingering = _has_any_holder_lingering_locked(borrowed_holder)
            if not has_lingering:
                borrowed_holder.os_lock_live = False
        if has_lingering:
            deferred_pin = True
            _spawn_borrowed_lingering_unpin(bucket, borrowed_holder, pin_lk)
        return CoordinatedExecution(False, -1, res)
    except BaseException:
        with bucket.cond:
            has_err_ling = _has_any_holder_lingering_locked(borrowed_holder)
            if not has_err_ling:
                borrowed_holder.os_lock_live = False
        if has_err_ling:
            deferred_pin = True
            _spawn_borrowed_lingering_unpin(bucket, borrowed_holder, pin_lk)
        raise
    finally:
        if not deferred_pin:
            with bucket.cond:
                if borrowed_holder in bucket.cross_proc_reentrant:
                    bucket.cross_proc_reentrant.remove(borrowed_holder)
            pin_lk.release()

def _check_cross_proc_lock_owner(owner_path: HostPath, holder: _ActiveHolder, resource_key: str) -> bool:
    live_owner = _read_live_cross_proc_owner(owner_path)
    if live_owner is None:
        return False
    ident, owner_mode = live_owner
    if not _holder_matches_cross_proc_owner(holder, ident):
        return False
    if owner_mode == ConcurrencyMode.SERIALIZE.value and _is_effective_serialize(
        holder.mode, holder.allow_step_coalesce
    ):
        return True
    src_tid = str(holder.call_stack[-1][1]) if holder.call_stack else None
    err = YscbError(
        ErrorCode.ILLEGAL_LOCK_REENTRANCY,
        f"Cannot re-enter resource_key '{resource_key}' with {holder.mode.value} across process CallStack.",
        source_task=src_tid,
    )
    leaf = holder.call_stack[-1] if holder.call_stack else None
    evicted_any = False
    for fl in (*( (holder.flight,) if holder.flight is not None else () ), *holder.enclosing_flights):
        ev, surv = fl.evict_callers_matching_holder(ident, leaf, err)
        if ev and surv:
            evicted_any = True
    if evicted_any:
        holder.coalesce_callers = tuple(
            v for v in holder.coalesce_callers if not _view_matches_holder(v, ident, extra_flights=holder.coalesce_flights, leaf_frame=leaf)
        )
        return False
    raise err


def _effective_holder_deadline(bucket: _ResourceBucket, holder: _ActiveHolder) -> Optional[float]:
    if holder.flight is not None:
        return holder.flight.effective_deadline()
    with bucket.cond:
        base_dl = holder.deadline
    fl_dls = [d for ef in holder.enclosing_flights if (d := ef.effective_deadline()) is not None]
    if not fl_dls:
        return base_dl
    min_fl = min(fl_dls)
    return min(base_dl, min_fl) if base_dl is not None else min_fl


def _acquire_or_reenter_os_lock(
    bucket: _ResourceBucket,
    paths: CrossProcessLockPaths,
    holder: _ActiveHolder,
    resource_key: str,
    refresh_remote_fn: Callable[[], None],
) -> tuple[bool, Optional[FileLock]]:
    sleep_s = 0.002
    while True:
        holder.cancel_token.raise_if_cancelled()
        refresh_remote_fn()
        if paths.lock_file.acquire(shared=False, blocking=False):
            break
        eff_dl_pin = _effective_holder_deadline(bucket, holder)
        pin_tmo = 10.0
        if eff_dl_pin is not None:
            rem_pin = eff_dl_pin - time.monotonic()
            if rem_pin <= 0:
                raise YscbError(ErrorCode.TASK_TIMEOUT, f"Timed out waiting for pin lock: {paths.pin_path}")
            pin_tmo = rem_pin
        pin_lk = acquire_verified_cross_proc_pin(
            paths.owner_path,
            paths.pin_path,
            lambda ow: _check_cross_proc_lock_owner(ow, holder, resource_key),
            timeout_sec=pin_tmo,
            cancel_token=holder.cancel_token,
        )
        if pin_lk is not None:
            return (False, pin_lk)
        eff_dl = _effective_holder_deadline(bucket, holder)
        now = time.monotonic()
        if eff_dl is not None and now >= eff_dl:
            raise YscbError(ErrorCode.TASK_TIMEOUT, f"Timed out waiting for file lock: {paths.lock_file.lock_path}")
        holder.cancel_token.wait(min(sleep_s, max(0.001, eff_dl - now)) if eff_dl is not None else sleep_s)
        sleep_s = min(0.015, sleep_s * 2.0)
    owner_doc: JsonObject = {
        "pid": os.getpid(),
        "turn_id": holder.turn_id,
        "call_tree_id": holder.call_tree_id,
        "flight_id": holder.flight.flight_id if holder.flight is not None else "",
        "mode": (
            ConcurrencyMode.SERIALIZE.value
            if _is_effective_serialize(holder.mode, holder.allow_step_coalesce)
            else holder.mode.value
        ),
        "call_stack": [[str(ws), str(tid)] for ws, tid in holder.call_stack],
        "callers": (
            [
                {
                    "turn_id": v.turn_id,
                    "call_tree_id": v.call_tree_id,
                    "call_stack": [[str(ws), str(tid)] for ws, tid in v.call_stack],
                }
                for v in holder.flight.snapshot_caller_views()
            ]
            if holder.flight is not None
            else []
        ),
    }
    try:
        write_cross_proc_owner_json(paths.owner_path, owner_doc)
    except BaseException:
        silent_unlink(paths.owner_path)
        paths.lock_file.release()
        raise
    return (True, None)


def _defer_lingering_lock_release(
    bucket: _ResourceBucket,
    holder: _ActiveHolder,
    paths: CrossProcessLockPaths,
) -> None:
    def _wait_and_release() -> None:
        try:
            _drain_holder_lingering_guards(bucket, holder)
        finally:
            try:
                unlink_owner_under_pin(paths.owner_path, paths.pin_path, paths.lock_file.release)
            finally:
                _release_holder_if_active(bucket, holder)

    try:
        threading.Thread(target=_wait_and_release, name="yscb-lock-lingering", daemon=True).start()
    except BaseException:
        _wait_and_release()
        raise


def _wait_waiter_promotion_loop(bucket: _ResourceBucket, waiter: _QueuedWaiter) -> None:
    wh = waiter.holder
    while not waiter.wake_event.is_set():
        wh.cancel_token.raise_if_cancelled()
        if wh.flight is not None:
            eff_dl = wh.flight.effective_deadline()
        else:
            with bucket.cond:
                eff_dl = wh.deadline
        rem = 0.02
        if eff_dl is not None:
            left = eff_dl - time.monotonic()
            if left <= 0:
                raise YscbError(ErrorCode.TASK_TIMEOUT, "Timed out waiting in ResourceCoordinator.")
            rem = min(rem, left)
        waiter.wake_event.wait(timeout=rem)
    wh.cancel_token.raise_if_cancelled()


def _abort_admission_on_error(
    bucket: _ResourceBucket,
    adm: _BucketAdmission,
    exc: BaseException,
) -> None:
    if adm.waiter is not None:
        _cleanup_failed_waiter_promotion(bucket, adm.waiter, exc)
        return
    if adm.holder is not None:
        h = adm.holder
        _release_holder_if_active(bucket, h)
        if h.flight is not None:
            h.flight.cancel_group.close_all()
            if not h.flight.done.is_set():
                h.flight.complete(raised_exc=exc)


def _cleanup_failed_waiter_promotion(
    bucket: _ResourceBucket,
    waiter: _QueuedWaiter,
    exc: BaseException,
) -> None:
    wh = waiter.holder
    aborted: list[_QueuedWaiter] = []
    elevate_ph: Optional[PriorityHandle] = None
    with bucket.cond:
        if waiter.reentrant_grant is not None:
            waiter.reentrant_grant.step_guard.set()
        if waiter in bucket.waiters:
            bucket.waiters.remove(waiter)
        elif waiter.promoted and bucket.active is wh:
            aborted, elevate_ph = _release_and_promote_next_locked(bucket)
    _flush_post_promote_callbacks(aborted, elevate_ph)
    if wh.flight is not None:
        wh.flight.cancel_group.close_all()
        if not wh.flight.done.is_set():
            wh.flight.complete(raised_exc=exc)


def _await_queued_promotion(
    bucket: _ResourceBucket,
    waiter: _QueuedWaiter,
) -> _ActiveHolder:
    wh = waiter.holder

    def _on_waiter_elevated(_p: ExecutionPriority) -> None:
        act_ph: Optional[PriorityHandle] = None
        with bucket.cond:
            if waiter in bucket.waiters:
                _sort_waiters(bucket.waiters)
                if bucket.active is not None:
                    act_ph = bucket.active.priority_handle
        if act_ph is not None:
            act_ph.elevate_to_foreground()

    unreg_prio = wh.priority_handle.register_listener(_on_waiter_elevated)
    unreg = wh.cancel_token.register_callback(lambda _p, _r: waiter.wake_event.set())
    try:
        _wait_waiter_promotion_loop(bucket, waiter)
    except BaseException as exc:
        _cleanup_failed_waiter_promotion(bucket, waiter, exc)
        raise
    finally:
        unreg_prio()
        unreg()

    with bucket.cond:
        aborted_pre = waiter.aborted_preempt or not waiter.promoted
    if aborted_pre:
        _abort_cancelled_waiter_flight(waiter, ErrorCode.TASK_PREEMPTED)
        wh.cancel_token.raise_if_cancelled()
        raise TaskCancelledException(wh.cancel_token.reason or "Superseded in queue", preempted=True)
    return wh

