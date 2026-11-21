"""Admission gates, coalesce context isolation, single global quiesce/reload barrier, and cold installer locks."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
import math
import os
import threading
import time
from typing import Callable, Iterator, Mapping, Optional, Sequence
import weakref

from core.execution.lifecycle import ColdTurnRunner, StepExecutionResult, TurnEngine, TurnExecutionReport, TurnScope
from core.execution.runtime.contracts import (
    LOCKS_SUBDIR, CallPropagationContext, CallerSurface, ClientRoutingPolicy, CORE_MODULE_ID, ConfigViewPort,
    DispatchMode, ExecutionPriority, INSTALLER_LOCK_STEM, InvokeRequest, ModuleDescriptor, SecurityTier,
    SelfMutationScope, TaskExposure, TaskRouteSpec, WATCHER_TASK_ID, sanitize_caller_env,
)
from core.execution.runtime.coordinator import ResourceCoordinator
from core.execution.runtime.worker_pool import tier1_group_key_for
from core.filesystem.fs import (
    CrossProcessLockPaths, FileLock, acquire_verified_cross_proc_pin, read_live_owner_dict,
    resolve_contained_subpath, silent_unlink, unlink_owner_under_pin, write_cross_proc_owner_json,
)
from core.foundation.codec import DataclassCodec
from core.foundation.errors import CallCycleError, ErrorCode, ErrorDetail, TaskCancelledException, YscbError, safe_exception_summary
from core.foundation.observability import CancellationToken, MAX_SAFE_WAIT_SEC, clamp_positive_sec, ms_to_safe_sec, safe_real_to_float
from core.foundation.primitives import (
    HostPath, JsonObject, JsonValue, ModuleId, TaskId, decrement_ref_count, invoke_observer_safely,
    require_non_none, require_pure_int,
)


@dataclass(frozen=True, slots=True)
class QuiesceResumeResult:
    """Typed outcome of execute_daemon_quiesce_resume avoiding anonymous bool tuples."""

    started: bool
    need_handoff: bool

    def __post_init__(self) -> None:
        for flag, label in ((self.started, "started"), (self.need_handoff, "need_handoff")):
            if not isinstance(flag, bool):
                raise ValueError(f"QuiesceResumeResult.{label} must be a bool.")


def normalize_drain_deadline(drain_deadline: Optional[float]) -> Optional[float]:
    if drain_deadline is None:
        return None
    f_dl = safe_real_to_float(drain_deadline, label="drain_deadline")
    if math.isinf(f_dl) and f_dl > 0.0:
        return None
    if math.isnan(f_dl) or f_dl < 0.0:
        raise ValueError(f"drain_deadline must be finite and >= 0 (or +inf/None), got {drain_deadline!r}")
    return f_dl


@dataclass(slots=True)
class _ColdLockLease:
    """Refcounted per-(call_tree_id, lock_path) cold installer lock lease."""

    lock: Optional[FileLock]
    pin_lock: Optional[FileLock] = None
    shared_refs: int = 0
    excl_refs: int = 0
    cross_proc_excl: bool = False
    os_exclusive: bool = False
    has_owner_file: bool = False
    op_lock: threading.RLock = field(default_factory=threading.RLock)

    @property
    def is_exclusive(self) -> bool:
        return self.excl_refs > 0 or self.cross_proc_excl

    def dec_counts(self, was_excl: bool) -> tuple[int, bool]:
        if was_excl:
            self.excl_refs = max(0, self.excl_refs - 1)
        else:
            self.shared_refs = max(0, self.shared_refs - 1)
        need_down = self.os_exclusive and self.excl_refs == 0 and self.shared_refs > 0
        if need_down:
            self.os_exclusive = False
            self.has_owner_file = False
        return (self.shared_refs, need_down)


@dataclass(slots=True)
class SharedWorkspaceState:
    """Shared in-process cross-workspace coordinator registry and cold installer locks."""

    coordinators: weakref.WeakValueDictionary[str, ResourceCoordinator] = field(default_factory=weakref.WeakValueDictionary)
    installer_leases: dict[tuple[str, str], _ColdLockLease] = field(default_factory=dict)
    guard: threading.RLock = field(default_factory=threading.RLock)


def compute_coalesce_context_suffix(
    caller_cwd: HostPath, caller_env: Mapping[str, str], approval_scope: frozenset[TaskId], allow_conditional: bool,
) -> str:
    """Isolate COALESCE equivalence keys across caller security scopes and working directories."""
    env_pairs = tuple(sorted(sanitize_caller_env(caller_env).items()))
    approvals = tuple(sorted(str(t) for t in approval_scope))
    digest_doc: JsonObject = {"cwd": caller_cwd.comparison_key, "env": [[k, v] for k, v in env_pairs], "apr": list(approvals), "cond": allow_conditional}
    return DataclassCodec.canonical_hash(digest_doc)[:24]


def expand_colocated_tier1_siblings(target_mods: frozenset[ModuleId], all_descs: Sequence[ModuleDescriptor]) -> frozenset[ModuleId]:
    """Expand target modules to include all co-located Tier 1 venv_group siblings."""
    affected_groups = {tier1_group_key_for(d) for d in all_descs if d.module_id in target_mods and d.venv_python is not None}
    if not affected_groups:
        return target_mods
    return target_mods | frozenset(d.module_id for d in all_descs if d.venv_python is not None and tier1_group_key_for(d) in affected_groups)


def check_exposure_and_security_gates(request: InvokeRequest, spec: TaskRouteSpec) -> Optional[ErrorDetail]:
    """Validate task exposure surface and conditional/gated security tier authorization."""
    prop, sid = request.propagation, str(request.task_id)
    if spec.exposure == TaskExposure.INTERNAL_TRIGGER and not prop.is_internal_trigger:
        return ErrorDetail(ErrorCode.EXPOSURE_DENIED, f"Task '{request.task_id}' is INTERNAL_TRIGGER only.", source_task=sid)
    if spec.exposure == TaskExposure.SDK_ONLY and request.caller_surface == CallerSurface.CLI:
        return ErrorDetail(ErrorCode.EXPOSURE_DENIED, f"Task '{request.task_id}' is SDK_ONLY and cannot be called from CLI.", source_task=sid)
    if spec.security_tier == SecurityTier.CONDITIONAL and (not request.allow_conditional or prop.in_event_chain or any(ws != request.workspace_root for ws, _ in prop.call_stack)):
        return ErrorDetail(ErrorCode.SECURITY_GATED, f"CONDITIONAL Task '{request.task_id}' blocked by caller policy, event chain, or cross-workspace boundary.", source_task=sid)
    if spec.security_tier == SecurityTier.GATED:
        if prop.is_internal_trigger or prop.in_event_chain or request.priority == ExecutionPriority.BACKGROUND:
            return ErrorDetail(ErrorCode.SECURITY_GATED, f"GATED Task '{request.task_id}' cannot run in background or event-triggered context.", source_task=sid)
        if request.task_id not in request.approval_scope:
            return ErrorDetail(ErrorCode.SECURITY_GATED, f"Task '{request.task_id}' requires explicit GATED approval token.", source_task=sid)
    return None
def check_host_and_mutation_gates(
    request: InvokeRequest, spec: TaskRouteSpec, *, is_daemon_host: bool, conn_enabled: bool, in_cold_turn: bool = False,
) -> Optional[ErrorDetail]:
    """Validate interactive TTY, environment self-mutation, and cold/hot dispatch mode constraints."""
    prop, sid = request.propagation, str(request.task_id)
    if spec.interactive_tty and (
        prop.is_nested_call or bool(prop.call_stack) or bool(prop.hot_workspaces) or prop.is_internal_trigger
        or prop.in_event_chain or prop.from_hot_container or is_daemon_host or request.priority != ExecutionPriority.FOREGROUND
    ):
        return ErrorDetail(ErrorCode.TTY_REQUIRED, f"Interactive TTY task '{request.task_id}' must run from foreground cold CLI.", remediation=f"Execute '{request.task_id}' directly in an interactive terminal.", source_task=sid)
    if spec.mutation_scope != SelfMutationScope.NONE and (
        prop.from_hot_container or is_daemon_host or bool(prop.hot_workspaces) or prop.is_internal_trigger
        or prop.in_event_chain or request.priority != ExecutionPriority.FOREGROUND
    ):
        return ErrorDetail(ErrorCode.HOT_MUTATION_FORBIDDEN, f"Environment-mutating task '{request.task_id}' requires foreground cold execution.", remediation="Invoke environment mutations from a foreground cold CLI process or COLD_ONLY orchestrator.", source_task=sid)
    if spec.dispatch_mode == DispatchMode.COLD_ONLY and (request.routing_policy == ClientRoutingPolicy.STRICT_HOT or is_daemon_host or prop.from_hot_container):
        return ErrorDetail(ErrorCode.COLD_DISPATCH_FORBIDDEN, f"COLD_ONLY task '{request.task_id}' rejects hot container dispatch.", source_task=sid)
    if spec.dispatch_mode == DispatchMode.DAEMON_ONLY:
        if request.routing_policy == ClientRoutingPolicy.FORCE_COLD:
            return ErrorDetail(ErrorCode.COLD_DISPATCH_FORBIDDEN, f"Task '{request.task_id}' is DAEMON_ONLY and rejects --cold.", source_task=sid)
        if not is_daemon_host and (in_cold_turn or not conn_enabled or prop.is_nested_call):
            return ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, f"Task '{request.task_id}' is DAEMON_ONLY and cannot execute in a local ColdTurn.", source_task=sid)
    return None


def validate_stage1_gates(
    request: InvokeRequest, found: Optional[tuple[ModuleDescriptor, TaskRouteSpec]],
    module_block_error: Optional[ErrorDetail], *, is_daemon_host: bool, conn_enabled: bool, in_cold_turn: bool = False,
) -> tuple[Optional[ErrorDetail], Optional[tuple[ModuleDescriptor, TaskRouteSpec]]]:
    """Run complete admission checks surfacing quiesce/degradation before TASK_NOT_FOUND."""
    if module_block_error is not None:
        return (module_block_error, None)
    if found is None:
        return (ErrorDetail(ErrorCode.TASK_NOT_FOUND, f"Task '{request.task_id}' is not registered.", source_task=str(request.task_id)), None)
    desc, spec = found
    gate_err = check_exposure_and_security_gates(request, spec) or check_host_and_mutation_gates(
        request, spec, is_daemon_host=is_daemon_host, conn_enabled=conn_enabled, in_cold_turn=in_cold_turn,
    )
    if gate_err is not None:
        return (gate_err, None)
    stack_entry, prop = (request.workspace_root, request.task_id), request.propagation
    if stack_entry in prop.call_stack:
        chain_str = " -> ".join(f"{tid}" for _ws, tid in (*prop.call_stack, stack_entry))
        return (CallCycleError(f"Synchronous task call cycle detected: {chain_str}", source_task=str(request.task_id)).detail, None)
    return (None, (desc, spec))


@dataclass(slots=True)
class _GlobalQuiesceState:
    epoch: int = 0
    draining: bool = False
    quiesced: bool = False
    leased: bool = False
    lease_deadline: Optional[float] = None
    deferred_resume: bool = False
    resuming: bool = False
    pre_quiesce_ids: set[str] = field(default_factory=set)


class LifecycleReloadGate:
    """Single authoritative global state machine for step tracking, quiesce barrier, and reload gates."""

    def __init__(self, workspace_root: HostPath) -> None:
        self._workspace_root = workspace_root
        self._gate_listeners: list[Callable[[], None]] = []
        self._op_lock = threading.RLock()
        self._cond = threading.Condition(threading.Lock())
        self._in_flight_turns: dict[str, int] = {}
        self._in_flight_trees: dict[str, int] = {}
        self._in_flight_mods: dict[ModuleId, int] = {}
        self._admitted_rpc_turns: dict[tuple[str, ModuleId], int] = {}
        self._q = _GlobalQuiesceState()
        self._reloading_mod_counts: dict[ModuleId, int] = {}
        self._reload_exempt_turns: dict[str, int] = {}
        self._module_reload_epochs: dict[ModuleId, int] = {}
        self._global_reload_epoch: int = 0
        self._reloading_all_count: int = 0
        self._transition_seq: int = 0

    @property
    def quiesce_epoch(self) -> int:
        with self._cond:
            return self._q.epoch

    @property
    def transition_seq(self) -> int:
        with self._cond:
            return self._transition_seq

    def lifecycle_scope(self) -> threading.RLock:
        return self._op_lock

    @contextmanager
    def try_lifecycle_scope(self, timeout_sec: Optional[float] = None) -> Iterator[bool]:
        acq = self._op_lock.acquire() if timeout_sec is None else self._op_lock.acquire(blocking=True, timeout=max(0.0, timeout_sec))
        try:
            yield acq
        finally:
            if acq:
                self._op_lock.release()

    def has_any_active_work(self) -> bool:
        with self._cond:
            return any(c > 0 for c in self._in_flight_mods.values()) or any(c > 0 for c in self._admitted_rpc_turns.values())

    def has_any_quiesced(self) -> bool:
        with self._cond:
            return self._q.quiesced or self._q.draining or self._q.resuming

    def register_gate_listener(self, listener: Callable[[], None]) -> None:
        with self._cond:
            self._gate_listeners.append(listener)

    def _fire_gate_change(self) -> None:
        with self._cond:
            self._transition_seq += 1
            listeners = tuple(self._gate_listeners)
        for cb in listeners:
            invoke_observer_safely(cb)

    def is_globally_quiesced(self) -> bool:
        with self._cond:
            return self._q.quiesced or self._q.draining

    def is_globally_gated(self) -> bool:
        with self._cond:
            return self._q.quiesced or self._q.draining or self._q.resuming

    def is_call_gated_for_quiesce(self, target_mod: Optional[ModuleId]) -> bool:
        if target_mod is None or target_mod == CORE_MODULE_ID:
            return False
        with self._cond:
            return self._q.quiesced or self._q.draining or self._q.resuming
    def _is_prop_reentrant_draining_locked(self, prop: CallPropagationContext) -> bool:
        tid, ctree = prop.turn_id or "", prop.call_tree_id or ""
        if bool(tid) and self._q.draining and any(k_t == tid and cnt > 0 for (k_t, _m), cnt in self._admitted_rpc_turns.items()):
            return True
        if (bool(tid) and tid in self._in_flight_turns) or (bool(ctree) and ctree in self._in_flight_trees):
            return True
        return self._q.draining and any(ws == self._workspace_root for ws, _ in prop.call_stack)

    def _is_prop_pre_quiesce_locked(self, prop: CallPropagationContext) -> bool:
        tid, ctree = prop.turn_id or "", prop.call_tree_id or ""
        return (bool(tid) and tid in self._q.pre_quiesce_ids) or (bool(ctree) and ctree in self._q.pre_quiesce_ids)

    def _is_rpc_blocked_locked(self, target_mod: ModuleId, prop: Optional[CallPropagationContext]) -> bool:
        if target_mod == CORE_MODULE_ID:
            return False
        if self._q.resuming:
            return True
        if self._q.draining and (prop is None or not self._is_prop_reentrant_draining_locked(prop)):
            return True
        return self._q.quiesced and (not self._q.leased or prop is None or not self._is_prop_pre_quiesce_locked(prop))

    def is_rpc_call_gated(self, target_mod: Optional[ModuleId], prop: Optional[CallPropagationContext] = None) -> bool:
        if target_mod is None or target_mod == CORE_MODULE_ID:
            return False
        with self._cond:
            return self._is_rpc_blocked_locked(target_mod, prop)

    def has_admitted_rpc_turn(self, call_id: str) -> bool:
        if not call_id:
            return False
        with self._cond:
            return any(cid == call_id and cnt > 0 for (cid, _m), cnt in self._admitted_rpc_turns.items())

    def enter_rpc_call(self, mod_id: ModuleId, call_id: str, prop: Optional[CallPropagationContext] = None) -> bool:
        with self._cond:
            if mod_id != CORE_MODULE_ID and self._is_rpc_blocked_locked(mod_id, prop):
                return False
            key = (call_id or "_", mod_id)
            self._admitted_rpc_turns[key] = self._admitted_rpc_turns.get(key, 0) + 1
            return True

    def exit_rpc_call(self, mod_id: ModuleId, call_id: str) -> None:
        with self._cond:
            decrement_ref_count(self._admitted_rpc_turns, (call_id or "_", mod_id))
            self._cond.notify_all()

    def enter_host_step(self, mod_id: ModuleId, turn_id: str, call_tree_id: str = "") -> None:
        with self._cond:
            self._in_flight_mods[mod_id] = self._in_flight_mods.get(mod_id, 0) + 1
            if turn_id:
                self._in_flight_turns[turn_id] = self._in_flight_turns.get(turn_id, 0) + 1
            if call_tree_id:
                self._in_flight_trees[call_tree_id] = self._in_flight_trees.get(call_tree_id, 0) + 1

    def exit_host_step(self, mod_id: ModuleId, turn_id: str, call_tree_id: str = "") -> None:
        with self._cond:
            decrement_ref_count(self._in_flight_mods, mod_id)
            decrement_ref_count(self._in_flight_turns, turn_id)
            decrement_ref_count(self._in_flight_trees, call_tree_id)
            self._cond.notify_all()

    @contextmanager
    def host_step_scope(self, mod_id: ModuleId, turn_id: str, call_tree_id: str = "") -> Iterator[None]:
        self.enter_host_step(mod_id, turn_id, call_tree_id)
        try:
            yield
        finally:
            self.exit_host_step(mod_id, turn_id, call_tree_id)

    def _has_non_core_active_work_locked(self) -> bool:
        return any(m != CORE_MODULE_ID and c > 0 for m, c in self._in_flight_mods.items()) or any(
            m != CORE_MODULE_ID and c > 0 for (_cid, m), c in self._admitted_rpc_turns.items()
        )

    def try_begin_global_quiesce(
        self, drain_deadline: Optional[float] = None, *, leased: bool = False, pre_accepted_ids: frozenset[str] = frozenset(),
    ) -> bool:
        safe_dl = normalize_drain_deadline(drain_deadline)
        with self._cond:
            prev_draining = self._q.draining
            self._q.draining = True
            self._cond.notify_all()
            while self._has_non_core_active_work_locked() and (safe_dl is None or time.monotonic() < safe_dl):
                rem = 0.02 if safe_dl is None else min(0.02, max(0.001, safe_dl - time.monotonic()))
                self._cond.wait(timeout=rem)
            still_busy = self._has_non_core_active_work_locked()
            self._q.draining = prev_draining
            aborted_busy = still_busy and leased
            if not aborted_busy:
                if not self._q.quiesced:
                    self._q.epoch += 1
                self._q.quiesced = True
                if leased:
                    self._q.leased = True
                    live_ids = (
                        frozenset(self._in_flight_turns.keys()) | frozenset(self._in_flight_trees.keys())
                        | frozenset(tid for tid, _m in self._admitted_rpc_turns.keys() if tid != "_") | pre_accepted_ids
                    )
                    self._q.pre_quiesce_ids.update(k for k in live_ids if k)
            self._cond.notify_all()
        self._fire_gate_change()
        return not aborted_busy

    def record_quiesce_lease(self, lease_sec: float) -> None:
        exp_at = time.monotonic() + clamp_positive_sec(lease_sec, min_sec=0.05, max_sec=3600.0, label="lease_sec")
        with self._cond:
            self._q.epoch += 1
            self._q.leased = True
            self._q.deferred_resume = False
            self._q.lease_deadline = max(self._q.lease_deadline or 0.0, exp_at)
            self._cond.notify_all()
        self._fire_gate_change()

    def next_quiesce_wakeup(self) -> Optional[float]:
        with self._cond:
            if self._q.resuming or not self._q.quiesced:
                return None
            if self._q.deferred_resume:
                return 0.01
            return min(MAX_SAFE_WAIT_SEC, max(0.01, self._q.lease_deadline - time.monotonic())) if self._q.lease_deadline is not None else None

    def due_quiesce_epoch(self) -> Optional[int]:
        with self._cond:
            if self._q.resuming or not self._q.quiesced:
                return None
            if self._q.deferred_resume or (self._q.lease_deadline is not None and time.monotonic() >= self._q.lease_deadline):
                return self._q.epoch
            return None

    def postpone_due_lease(self, epoch: int, delay_sec: float) -> None:
        require_pure_int(epoch, "epoch", min_val=0)
        bump_dl = time.monotonic() + clamp_positive_sec(delay_sec, min_sec=0.05, max_sec=3600.0, label="delay_sec")
        with self._cond:
            if self._q.epoch == epoch and self._q.quiesced:
                self._q.deferred_resume = False
                self._q.lease_deadline = max(self._q.lease_deadline or 0.0, bump_dl)
    def schedule_deferred_resume(self, expected_epoch: Optional[int]) -> None:
        if expected_epoch is not None:
            require_pure_int(expected_epoch, "expected_epoch", min_val=0)
        with self._cond:
            if expected_epoch is not None and self._q.epoch != expected_epoch:
                return
            if self._q.quiesced:
                self._q.deferred_resume = True
                self._cond.notify_all()
        self._fire_gate_change()

    def run_global_resume_guarded(self, expected_epoch: Optional[int], body_fn: Callable[[], bool]) -> QuiesceResumeResult:
        if expected_epoch is not None:
            require_pure_int(expected_epoch, "expected_epoch", min_val=0)
        with self._cond:
            target_ep = expected_epoch if expected_epoch is not None else self._q.epoch
            if self._q.resuming or self._q.epoch != target_ep:
                return QuiesceResumeResult(started=False, need_handoff=False)
            self._q.resuming = True
            self._cond.notify_all()
        self._fire_gate_change()
        try:
            need_handoff = body_fn()
        finally:
            with self._cond:
                self._q.resuming = False
                self._cond.notify_all()
            self._fire_gate_change()
        return QuiesceResumeResult(started=True, need_handoff=need_handoff)

    @contextmanager
    def resume_reload_scope(self) -> Iterator[None]:
        with self._cond:
            self._q.quiesced = self._q.leased = self._q.deferred_resume = False
            self._q.lease_deadline = None
            self._q.pre_quiesce_ids.clear()
            self._reloading_all_count += 1
            self._global_reload_epoch += 1
            self._cond.notify_all()
        self._fire_gate_change()
        try:
            yield
        finally:
            with self._cond:
                self._reloading_all_count = max(0, self._reloading_all_count - 1)
                self._cond.notify_all()
            self._fire_gate_change()

    @contextmanager
    def module_reload_scope(self, reload_all: bool, initial_gated: frozenset[ModuleId]) -> Iterator[None]:
        with self._cond:
            exempt_now = frozenset(k for k in self._in_flight_turns if k) | frozenset(k for k in self._in_flight_trees if k)
            if reload_all:
                self._reloading_all_count += 1
            for m in initial_gated:
                self._reloading_mod_counts[m] = self._reloading_mod_counts.get(m, 0) + 1
            for eid in exempt_now:
                self._reload_exempt_turns[eid] = self._reload_exempt_turns.get(eid, 0) + 1
            self._cond.notify_all()
        self._fire_gate_change()
        try:
            yield
        finally:
            with self._cond:
                if reload_all:
                    self._reloading_all_count = max(0, self._reloading_all_count - 1)
                for m in initial_gated:
                    decrement_ref_count(self._reloading_mod_counts, m)
                for eid in exempt_now:
                    decrement_ref_count(self._reload_exempt_turns, eid)
                self._cond.notify_all()
            self._fire_gate_change()

    def bump_reload_epochs(self, mods: frozenset[ModuleId]) -> None:
        with self._cond:
            for m in mods:
                self._module_reload_epochs[m] = self._module_reload_epochs.get(m, 0) + 1

    def any_descriptor_reloading(self, descriptors: Sequence[ModuleDescriptor]) -> bool:
        with self._cond:
            return self._reloading_all_count > 0 or any(d.module_id in self._reloading_mod_counts for d in descriptors)

    def has_leased_pre_quiesce(self, turn_id: str, call_tree_id: str) -> bool:
        with self._cond:
            return any(bool(k) and k in self._q.pre_quiesce_ids for k in (turn_id, call_tree_id))

    def _can_wait_leased_quiesce_locked(self, request: InvokeRequest) -> bool:
        if not self._q.leased:
            return False
        return True if self._is_prop_pre_quiesce_locked(request.propagation) else not request.propagation.in_event_chain

    def _is_reload_exempt_locked(self, request: InvokeRequest) -> bool:
        prop = request.propagation
        if (bool(prop.turn_id) and prop.turn_id in self._reload_exempt_turns) or (
            bool(prop.call_tree_id) and prop.call_tree_id in self._reload_exempt_turns
        ):
            return True
        all_rel, rel_mods = self._reloading_all_count > 0, self._reloading_mod_counts
        return any(ws == self._workspace_root and (all_rel or tid.module_id in rel_mods) for ws, tid in prop.call_stack)

    def _should_wait_on_gate_locked(self, request: InvokeRequest, target_mod: ModuleId) -> bool:
        if target_mod == CORE_MODULE_ID:
            return False
        if self._q.resuming or (self._q.draining and not self._is_prop_reentrant_draining_locked(request.propagation)):
            return True
        if self._q.quiesced and not self._is_prop_pre_quiesce_locked(request.propagation) and self._can_wait_leased_quiesce_locked(request):
            return True
        return not self._is_reload_exempt_locked(request) and (self._reloading_all_count > 0 or target_mod in self._reloading_mod_counts)

    def is_quiesced_blocked(self, request: InvokeRequest, target_mod: ModuleId, is_daemon_host: bool) -> bool:
        if not is_daemon_host or target_mod == CORE_MODULE_ID:
            return False
        with self._cond:
            if not self._q.quiesced or self._is_prop_pre_quiesce_locked(request.propagation):
                return False
            return not self._can_wait_leased_quiesce_locked(request)

    def current_epoch(self, mod_id: ModuleId) -> int:
        with self._cond:
            return self._global_reload_epoch + self._module_reload_epochs.get(mod_id, 0)

    def has_turn_or_tree_exempt(self, turn_id: str, call_tree_id: str) -> bool:
        with self._cond:
            return (bool(turn_id) and turn_id in self._reload_exempt_turns) or (bool(call_tree_id) and call_tree_id in self._reload_exempt_turns)

    def is_request_reload_exempt(self, request: InvokeRequest, is_reentrant_retiring: Callable[[InvokeRequest], bool]) -> bool:
        if is_reentrant_retiring(request):
            return True
        with self._cond:
            return self._is_reload_exempt_locked(request)

    def is_step_blocked_by_reload(self, parent_req: InvokeRequest, is_reentrant_retiring: Callable[[InvokeRequest], bool]) -> bool:
        if is_reentrant_retiring(parent_req):
            return False
        with self._cond:
            return self._should_wait_on_gate_locked(parent_req, parent_req.task_id.module_id)

    def wait_for_unquiesced(
        self, request: InvokeRequest, token: CancellationToken, is_reentrant_retiring: Callable[[InvokeRequest], bool],
        *, timeout_ms: Optional[int] = None,
    ) -> None:
        deadline = (time.monotonic() + ms_to_safe_sec(timeout_ms)) if timeout_ms is not None else None
        target_mod = request.task_id.module_id

        def _wake_gate(_p: bool, _r: Optional[str]) -> None:
            with self._cond:
                self._cond.notify_all()

        unreg = token.register_callback(_wake_gate)
        try:
            while not token.is_cancelled and not is_reentrant_retiring(request):
                with self._cond:
                    if not self._should_wait_on_gate_locked(request, target_mod) or token.is_cancelled:
                        return
                    if deadline is not None and time.monotonic() >= deadline:
                        raise YscbError(ErrorCode.TASK_TIMEOUT, f"Timed out waiting for module '{target_mod}' lifecycle gate.", source_task=str(request.task_id))
                    self._cond.wait(timeout=0.02 if deadline is None else min(0.02, max(0.001, deadline - time.monotonic())))
        finally:
            unreg()
def _is_same_tree_installer_owner(owner_path: HostPath, call_tree_id: str) -> bool:
    if not call_tree_id:
        return False
    doc = read_live_owner_dict(owner_path)
    raw_tree = doc.get("call_tree_id") if doc is not None else None
    return type(raw_tree) is str and bool(raw_tree) and raw_tree == call_tree_id


def _abort_cold_turn_scope(turn_scope: TurnScope, detail: ErrorDetail, *, fatal_abort: bool = False) -> TurnExecutionReport:
    td_errs = turn_scope.close_scoped_stack_recorded()
    return TurnExecutionReport(turn_id=turn_scope.turn_id, primary_result=StepExecutionResult(ok=False, error=detail, fatal_abort_turn=fatal_abort), teardown_diagnostics=td_errs)


def _rem_lock_sec(deadline: Optional[float], default_sec: float, lock_path: HostPath) -> float:
    if deadline is None:
        return default_sec
    rem = deadline - time.monotonic()
    if rem <= 0:
        raise YscbError(ErrorCode.TASK_TIMEOUT, f"Timed out waiting for lock: {lock_path}")
    return rem


class ColdInstallerLockManager:
    """Manages cross-process installer.lock shared/exclusive reentrancy and nested cold lock upgrades."""

    def __init__(
        self, workspace_root: HostPath, cache_dir: HostPath, turn_engine: TurnEngine[InvokeRequest], bootstrap_hook: Callable[[], None],
    ) -> None:
        self._workspace_root, self._cache_dir, self._bootstrap_hook = workspace_root, cache_dir, bootstrap_hook
        self._cold_runner = ColdTurnRunner(turn_engine, on_bootstrap_check=lambda _s: bootstrap_hook())
        self.reentry_lock: threading.RLock = threading.RLock()
        self.leases: dict[tuple[str, str], _ColdLockLease] = {}

    def _installer_paths(self) -> CrossProcessLockPaths:
        return CrossProcessLockPaths.for_stem(resolve_contained_subpath(self._cache_dir, LOCKS_SUBDIR), INSTALLER_LOCK_STEM)

    def _lock_scope_key(self, scope_id: str) -> tuple[str, str]:
        return (scope_id, self._cache_dir.comparison_key)

    def _downgrade_lease_os_lock(self, lock_key: tuple[str, str], lease: _ColdLockLease, rem_shared: int) -> None:
        lk_ref = require_non_none(lease.lock)

        def _do_downgrade() -> None:
            if rem_shared <= 0 or not lk_ref.is_acquired:
                return
            try:
                lk_ref.downgrade_to_shared()
            except BaseException:
                self._evict_broken_lease(lock_key, lease)
                raise

        paths = self._installer_paths()
        unlink_owner_under_pin(paths.owner_path, paths.pin_path, _do_downgrade)

    def _release_lease_slot(self, lock_key: tuple[str, str], lease: _ColdLockLease, *, was_excl: bool) -> None:
        with lease.op_lock:
            with self.reentry_lock:
                rem_shared, need_downgrade = lease.dec_counts(was_excl)
            if need_downgrade:
                self._downgrade_lease_os_lock(lock_key, lease, rem_shared)
            with self.reentry_lock:
                idle_lock: Optional[FileLock] = None
                idle_pin: Optional[FileLock] = None
                unlink_ow = False
                if lease.excl_refs <= 0 and lease.shared_refs <= 0:
                    if self.leases.get(lock_key) is lease:
                        self.leases.pop(lock_key, None)
                    idle_lock, idle_pin, unlink_ow = lease.lock, lease.pin_lock, lease.has_owner_file
                    lease.pin_lock = None
                    lease.has_owner_file = False
        if idle_pin is not None:
            idle_pin.release()
        if unlink_ow:
            paths = self._installer_paths()
            unlink_owner_under_pin(paths.owner_path, paths.pin_path, lambda: idle_lock.release() if idle_lock is not None else None)
        elif idle_lock is not None:
            idle_lock.release()

    def bind_shared(self, shared_ws: SharedWorkspaceState, own_coordinator: ResourceCoordinator) -> ResourceCoordinator:
        with shared_ws.guard:
            existing = shared_ws.coordinators.get(self._workspace_root.comparison_key)
            if isinstance(existing, ResourceCoordinator):
                chosen = existing
            else:
                shared_ws.coordinators[self._workspace_root.comparison_key] = own_coordinator
                chosen = own_coordinator
        self.leases, self.reentry_lock = shared_ws.installer_leases, shared_ws.guard
        return chosen

    def run_cold_event_turn(self, turn_scope: TurnScope, fn: Callable[[], TurnExecutionReport]) -> TurnExecutionReport:
        lock_key = self._lock_scope_key(turn_scope.turn_id)
        try:
            lock = self._installer_paths().lock_file
            lock.acquire(shared=True, blocking=True, timeout_sec=30.0, cancel_token=turn_scope.cancel_token)
        except (TaskCancelledException, YscbError) as exc:
            return _abort_cold_turn_scope(turn_scope, exc.detail.with_fallback_task(str(WATCHER_TASK_ID)))
        lease: Optional[_ColdLockLease] = None
        try:
            boot_err = self._invoke_bootstrap_safely()
            if boot_err is not None:
                return _abort_cold_turn_scope(turn_scope, boot_err.with_fallback_task(str(WATCHER_TASK_ID)))
            with self.reentry_lock:
                cur = self.leases.get(lock_key)
                if cur is None:
                    lease = _ColdLockLease(lock=lock, shared_refs=1)
                    self.leases[lock_key] = lease
                elif not cur.is_exclusive:
                    cur.shared_refs += 1
                    lease = cur
            if lease is None:
                return fn()
            if lease.lock is not lock:
                lock.release()
            return fn()
        finally:
            if lease is not None:
                self._release_lease_slot(lock_key, lease, was_excl=False)
            else:
                lock.release()

    def _invoke_bootstrap_safely(self) -> Optional[ErrorDetail]:
        try:
            self._bootstrap_hook()
            return None
        except (TaskCancelledException, YscbError) as exc:
            return exc.detail
        except (Exception, SystemExit, GeneratorExit) as exc:
            return ErrorDetail(ErrorCode.BUSINESS_FAILURE, safe_exception_summary(exc))
    def refresh_cold_routes(self, token: CancellationToken, call_tree_id: str, *, deadline: Optional[float] = None) -> Optional[ErrorDetail]:
        lock_key = self._lock_scope_key(call_tree_id)
        with self.reentry_lock:
            in_mem_held = bool(call_tree_id) and (lock_key in self.leases)
        if in_mem_held:
            return self._invoke_bootstrap_safely()
        paths = self._installer_paths()
        try:
            pin_lk = (
                acquire_verified_cross_proc_pin(
                    paths.owner_path, paths.pin_path, lambda ow: _is_same_tree_installer_owner(ow, call_tree_id),
                    timeout_sec=_rem_lock_sec(deadline, 10.0, paths.pin_path), cancel_token=token,
                )
                if call_tree_id else None
            )
            if pin_lk is not None:
                try:
                    return self._invoke_bootstrap_safely()
                finally:
                    pin_lk.release()
            lock = paths.lock_file
            lock.acquire(shared=True, blocking=True, timeout_sec=_rem_lock_sec(deadline, 10.0, lock.lock_path), cancel_token=token)
        except (TaskCancelledException, YscbError) as exc:
            return exc.detail
        try:
            return self._invoke_bootstrap_safely()
        finally:
            lock.release()

    def run_cold_turn(
        self, tagged_req: InvokeRequest, spec: TaskRouteSpec, turn_scope: TurnScope, *, deadline: Optional[float] = None,
    ) -> TurnExecutionReport:
        prop, need_excl = tagged_req.propagation, spec.mutation_scope != SelfMutationScope.NONE
        eff_ctree = prop.call_tree_id or turn_scope.turn_id
        in_cold_shared = self._workspace_root in prop.cold_shared_workspaces
        next_req = replace(tagged_req, propagation=replace(prop, cold_shared_workspaces=prop.cold_shared_workspaces | frozenset({self._workspace_root}))) if not need_excl else tagged_req
        lock_key = self._lock_scope_key(eff_ctree)
        reentered, reenter_err = self._try_reenter_in_memory_cold_lease(lock_key, tagged_req.task_id, need_excl=need_excl, in_cold_shared_ws=in_cold_shared)
        if reenter_err is not None:
            return _abort_cold_turn_scope(turn_scope, reenter_err, fatal_abort=True)
        if reentered is not None:
            try:
                return self._cold_runner.execute_leased_turn(next_req, scope=turn_scope, fallback_task=str(next_req.task_id))
            finally:
                self._release_lease_slot(lock_key, reentered, was_excl=need_excl)
        host_token, lock, pin_lk = turn_scope.cancel_token, None, None
        try:
            try:
                paths = self._installer_paths()
                if paths.lock_file.acquire(shared=not need_excl, blocking=False):
                    lock = paths.lock_file
                else:
                    pin_lk = acquire_verified_cross_proc_pin(
                        paths.owner_path, paths.pin_path, lambda ow: _is_same_tree_installer_owner(ow, eff_ctree),
                        timeout_sec=_rem_lock_sec(deadline, 10.0, paths.pin_path), cancel_token=host_token,
                    )
                    if pin_lk is None:
                        paths.lock_file.acquire(shared=not need_excl, blocking=True, timeout_sec=_rem_lock_sec(deadline, 30.0, paths.lock_file.lock_path), cancel_token=host_token)
                        lock = paths.lock_file
            except (TaskCancelledException, YscbError) as exc:
                return _abort_cold_turn_scope(turn_scope, exc.detail.with_fallback_task(str(next_req.task_id)))
            if pin_lk is not None:
                return self._run_pinned_cross_proc_cold(next_req, lock_key, pin_lk, turn_scope)
        except BaseException:
            if lock is not None:
                lock.release()
            turn_scope.close_scoped_stack_recorded()
            raise
        lock = require_non_none(lock)
        cand = _ColdLockLease(lock=lock, shared_refs=0 if need_excl else 1, excl_refs=1 if need_excl else 0, os_exclusive=need_excl)
        try:
            lease, joined = self._install_or_join_cold_lease(lock_key, cand, eff_ctree, as_excl=need_excl)
        except YscbError as exc:
            lock.release()
            return _abort_cold_turn_scope(turn_scope, exc.detail.with_fallback_task(str(next_req.task_id)), fatal_abort=True)
        except BaseException:
            lock.release()
            turn_scope.close_scoped_stack_recorded()
            raise
        if joined:
            lock.release()
        try:
            return self._cold_runner.execute_leased_turn(next_req, scope=turn_scope, fallback_task=str(next_req.task_id))
        finally:
            self._release_lease_slot(lock_key, lease, was_excl=need_excl)

    def _try_reenter_in_memory_cold_lease(
        self, lock_key: tuple[str, str], task_id: TaskId, *, need_excl: bool, in_cold_shared_ws: bool,
    ) -> tuple[Optional[_ColdLockLease], Optional[ErrorDetail]]:
        err_up = ErrorDetail(ErrorCode.ILLEGAL_LOCK_REENTRANCY, f"Cannot upgrade shared installer.lock to exclusive in '{task_id}'.", source_task=str(task_id))
        with self.reentry_lock:
            cand = self.leases.get(lock_key)
        if cand is not None:
            with cand.op_lock, self.reentry_lock:
                if self.leases.get(lock_key) is cand:
                    if need_excl and not cand.is_exclusive:
                        return (None, err_up)
                    cand.excl_refs += 1 if need_excl else 0
                    cand.shared_refs += 0 if need_excl else 1
                    return (cand, None)
        if in_cold_shared_ws and need_excl:
            return (None, err_up)
        return (None, None)

    def _install_or_join_cold_lease(
        self, lock_key: tuple[str, str], new_lease: _ColdLockLease, eff_ctree: str, *, as_excl: bool,
    ) -> tuple[_ColdLockLease, bool]:
        while True:
            with new_lease.op_lock:
                with self.reentry_lock:
                    cur = self.leases.get(lock_key)
                    if cur is None:
                        self.leases[lock_key] = new_lease
                        cur = None
                if cur is None:
                    if as_excl and not new_lease.cross_proc_excl:
                        owner_p = self._installer_paths().owner_path
                        try:
                            write_cross_proc_owner_json(owner_p, {"pid": os.getpid(), "call_tree_id": eff_ctree})
                            new_lease.has_owner_file = True
                        except BaseException:
                            silent_unlink(owner_p)
                            self._evict_broken_lease(lock_key, new_lease)
                            raise
                    return (new_lease, False)
            with cur.op_lock, self.reentry_lock:
                if self.leases.get(lock_key) is not cur:
                    continue
                if not as_excl:
                    cur.shared_refs += 1
                    return (cur, True)
                if cur.is_exclusive:
                    cur.excl_refs += 1
                    return (cur, True)
                raise YscbError(ErrorCode.ILLEGAL_LOCK_REENTRANCY, "Cannot upgrade shared cold installer.lock lease without explicit upgrade path.")
    def _run_pinned_cross_proc_cold(
        self, next_req: InvokeRequest, lock_key: tuple[str, str], pin_lk: FileLock, turn_scope: TurnScope,
    ) -> TurnExecutionReport:
        cand = _ColdLockLease(lock=None, pin_lock=pin_lk, excl_refs=1, cross_proc_excl=True)
        try:
            lease, joined = self._install_or_join_cold_lease(lock_key, cand, "", as_excl=True)
        except YscbError as exc:
            pin_lk.release()
            return _abort_cold_turn_scope(turn_scope, exc.detail.with_fallback_task(str(next_req.task_id)), fatal_abort=True)
        except BaseException:
            pin_lk.release()
            turn_scope.close_scoped_stack_recorded()
            raise
        if joined:
            pin_lk.release()
        try:
            return self._cold_runner.execute_leased_turn(next_req, scope=turn_scope, fallback_task=str(next_req.task_id))
        finally:
            self._release_lease_slot(lock_key, lease, was_excl=True)

    def _evict_broken_lease(self, lock_key: tuple[str, str], lease: _ColdLockLease) -> None:
        with self.reentry_lock:
            if self.leases.get(lock_key) is lease:
                self.leases.pop(lock_key, None)

    def _upgrade_lease_os_lock(
        self, lock_key: tuple[str, str], lease: _ColdLockLease, eff_ctree: str,
        task_id: TaskId, cancel_token: CancellationToken, deadline: Optional[float],
    ) -> Optional[StepExecutionResult[JsonValue]]:
        lk_ref, paths = require_non_none(lease.lock), self._installer_paths()
        try:
            lk_ref.upgrade_to_exclusive(timeout_sec=_rem_lock_sec(deadline, 10.0, lk_ref.lock_path), cancel_token=cancel_token)
            lease.os_exclusive = True
        except (TaskCancelledException, YscbError) as exc:
            if not lk_ref.is_acquired:
                self._evict_broken_lease(lock_key, lease)
            det = exc.detail.with_fallback_task(str(task_id))
            return StepExecutionResult(ok=False, error=det, fatal_abort_turn=(det.code == ErrorCode.ILLEGAL_LOCK_REENTRANCY or not lk_ref.is_acquired))
        except BaseException:
            if not lk_ref.is_acquired:
                self._evict_broken_lease(lock_key, lease)
            raise
        try:
            write_cross_proc_owner_json(paths.owner_path, {"pid": os.getpid(), "call_tree_id": eff_ctree})
        except YscbError as exc:
            self._rollback_failed_lease_upgrade(lock_key, lease, paths.owner_path, try_downgrade=True)
            return StepExecutionResult(ok=False, error=exc.detail.with_fallback_task(str(task_id)), fatal_abort_turn=not lk_ref.is_acquired)
        except Exception:
            self._rollback_failed_lease_upgrade(lock_key, lease, paths.owner_path, try_downgrade=True)
            raise
        except BaseException:
            self._rollback_failed_lease_upgrade(lock_key, lease, paths.owner_path, try_downgrade=False)
            raise
        lease.has_owner_file = True
        return None

    def _rollback_failed_lease_upgrade(self, lock_key: tuple[str, str], lease: _ColdLockLease, owner_path: HostPath, *, try_downgrade: bool) -> None:
        lease.os_exclusive = False
        silent_unlink(owner_path)
        lk = require_non_none(lease.lock)
        if not try_downgrade:
            lk.release()
            self._evict_broken_lease(lock_key, lease)
            return
        try:
            lk.downgrade_to_shared(timeout_sec=2.0)
        except BaseException as sub_exc:
            lk.release()
            self._evict_broken_lease(lock_key, lease)
            if not isinstance(sub_exc, Exception):
                raise

    def _enter_upgraded_lease(
        self, lock_key: tuple[str, str], lease: _ColdLockLease, eff_ctree: str,
        task_id: TaskId, cancel_token: CancellationToken, deadline: Optional[float],
    ) -> tuple[bool, Optional[StepExecutionResult[JsonValue]]]:
        with lease.op_lock:
            with self.reentry_lock:
                if self.leases.get(lock_key) is not lease or lease.lock is None or not lease.lock.is_acquired:
                    return (False, None)
            if not lease.os_exclusive:
                up_err = self._upgrade_lease_os_lock(lock_key, lease, eff_ctree, task_id, cancel_token, deadline)
                if up_err is not None:
                    return (True, up_err)
            with self.reentry_lock:
                if self.leases.get(lock_key) is not lease or lease.lock is None or not lease.lock.is_acquired:
                    return (False, None)
                lease.excl_refs += 1
        return (True, None)

    def run_upgraded_nested(
        self, eff_ctree: str, task_id: TaskId, cancel_token: CancellationToken,
        step_fn: Callable[[], StepExecutionResult[JsonValue]], *, deadline: Optional[float] = None,
    ) -> StepExecutionResult[JsonValue]:
        lock_key = self._lock_scope_key(eff_ctree)
        with self.reentry_lock:
            lease = self.leases.get(lock_key)
        if lease is not None and (lease.cross_proc_excl or lease.lock is None):
            with lease.op_lock, self.reentry_lock:
                if self.leases.get(lock_key) is lease:
                    lease.excl_refs += 1
                    try:
                        return step_fn()
                    finally:
                        self._release_lease_slot(lock_key, lease, was_excl=True)
        if lease is not None:
            claimed, up_err = self._enter_upgraded_lease(lock_key, lease, eff_ctree, task_id, cancel_token, deadline)
            if up_err is not None:
                return up_err
            if claimed:
                try:
                    return step_fn()
                finally:
                    self._release_lease_slot(lock_key, lease, was_excl=True)
        try:
            paths = self._installer_paths()
            pin_lk = acquire_verified_cross_proc_pin(
                paths.owner_path, paths.pin_path, lambda ow: _is_same_tree_installer_owner(ow, eff_ctree),
                timeout_sec=_rem_lock_sec(deadline, 10.0, paths.pin_path), cancel_token=cancel_token,
            )
        except (TaskCancelledException, YscbError) as exc:
            return StepExecutionResult(ok=False, error=exc.detail.with_fallback_task(str(task_id)))
        if pin_lk is not None:
            try:
                return step_fn()
            finally:
                pin_lk.release()
        err = ErrorDetail(ErrorCode.ILLEGAL_LOCK_REENTRANCY, f"Cannot upgrade shared installer.lock across processes in '{task_id}'.", source_task=str(task_id))
        return StepExecutionResult(ok=False, error=err, fatal_abort_turn=True)


class ConfigFingerprintTracker:
    """Tracks config fingerprint reloads under unified lifecycle lock."""

    def __init__(self, config_view: Optional[ConfigViewPort]) -> None:
        self._config_view = config_view
        self._last_fp: Optional[str] = config_view.fingerprint() if config_view is not None else None

    def reload_always(self) -> bool:
        """Reload config view unconditionally and return True when the fingerprint changed."""
        if self._config_view is None:
            return False
        prev = self._last_fp
        self._config_view.reload()
        self._last_fp = self._config_view.fingerprint()
        return prev is not None and self._last_fp != prev

    def reload_if_changed(self) -> bool:
        if self._config_view is None:
            return False
        cur_fp = self._config_view.fingerprint()
        if cur_fp != self._last_fp:
            self._config_view.reload()
            self._last_fp = self._config_view.fingerprint()
            return True
        return False
