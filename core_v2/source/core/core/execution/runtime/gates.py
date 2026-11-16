"""Admission gates, coalesce context isolation, unified quiesce/reload gates, and cold installer locks."""

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
    CallPropagationContext,
    CallerSurface,
    ClientRoutingPolicy,
    ConfigViewPort,
    DispatchMode,
    ExecutionPriority,
    InvokeRequest,
    ModuleDescriptor,
    SecurityTier,
    SelfMutationScope,
    TaskExposure,
    TaskRouteSpec,
    sanitize_caller_env,
)
from core.execution.runtime.coordinator import ResourceCoordinator
from core.execution.runtime.lineage_join import StepEventCapture
from core.execution.runtime.worker_pool import tier1_group_key_for
from core.filesystem.fs import (
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
from core.foundation.errors import (
    CallCycleError,
    ErrorCode,
    ErrorDetail,
    TaskCancelledException,
    YscbError,
    safe_exception_summary,
)
from core.foundation.observability import (
    clamp_positive_sec,
    safe_real_to_float,
    MAX_SAFE_WAIT_SEC,
    CancellationToken,
    ms_to_safe_sec,
)
from core.foundation.primitives import (
    require_pure_int,
    decrement_ref_count,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    TaskId,
    invoke_observer_safely,
    require_non_none,
    require_typed_frozenset,
)


@dataclass(frozen=True, slots=True)
class QuiesceResumeResult:
    """Typed outcome of execute_daemon_quiesce_resume avoiding anonymous bool triples."""

    started: bool
    need_handoff: bool
    still_quiesced: bool

    def __post_init__(self) -> None:
        for flag, label in (
            (self.started, "started"),
            (self.need_handoff, "need_handoff"),
            (self.still_quiesced, "still_quiesced"),
        ):
            if not isinstance(flag, bool):
                raise ValueError(f"QuiesceResumeResult.{label} must be a bool.")


@dataclass(frozen=True, slots=True)
class ResumeConsumePlan:
    re_warm: frozenset[ModuleId]
    touched_all: frozenset[ModuleId]
    was_all: bool

    def __post_init__(self) -> None:
        if not isinstance(self.was_all, bool):
            raise ValueError(f"ResumeConsumePlan.was_all must be a bool, got {self.was_all!r}")
        object.__setattr__(self, "re_warm", require_typed_frozenset(self.re_warm, ModuleId, "ResumeConsumePlan.re_warm"))
        object.__setattr__(self, "touched_all", require_typed_frozenset(self.touched_all, ModuleId, "ResumeConsumePlan.touched_all"))


@dataclass(frozen=True, slots=True)
class _ResumePlanInternal:
    re_warm: frozenset[ModuleId]
    touched: frozenset[ModuleId]
    remaining: frozenset[ModuleId]
    was_all: bool


@dataclass(frozen=True, slots=True)
class _IdleColdLeaseHandles:
    lock: Optional[FileLock] = None
    pin_lock: Optional[FileLock] = None
    unlink_owner: bool = False


def normalize_drain_deadline(drain_deadline: Optional[float]) -> Optional[float]:
    if drain_deadline is None:
        return None
    f_dl = safe_real_to_float(drain_deadline, label="drain_deadline")
    if math.isnan(f_dl):
        raise ValueError(f"drain_deadline must not be bool or NaN, got {drain_deadline!r}")
    now = time.monotonic()
    return min(now + MAX_SAFE_WAIT_SEC, max(now - MAX_SAFE_WAIT_SEC, f_dl))


def _validate_monotonic_now(now: float) -> float:
    f_now = safe_real_to_float(now, label="now")
    if not math.isfinite(f_now):
        raise ValueError(f"now must be finite (not bool/NaN/inf), got {now!r}")
    return f_now


@dataclass(frozen=True, slots=True)
class DueQuiesceResume:
    """Expired or deferred quiesce lease target produced by LifecycleReloadGate."""

    epoch: int
    modules: Optional[frozenset[ModuleId]] = None
    preserve_modules: frozenset[ModuleId] = frozenset()

    def __post_init__(self) -> None:
        require_pure_int(self.epoch, "DueQuiesceResume.epoch", min_val=0)
        if self.modules is not None:
            object.__setattr__(self, "modules", require_typed_frozenset(self.modules, ModuleId, "DueQuiesceResume.modules"))
        object.__setattr__(
            self, "preserve_modules", require_typed_frozenset(self.preserve_modules, ModuleId, "DueQuiesceResume.preserve_modules")
        )


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
    """Shared in-process cross-workspace coordination, cache directories, active captures, and cold installer locks."""

    coordinators: weakref.WeakValueDictionary[str, ResourceCoordinator] = field(
        default_factory=weakref.WeakValueDictionary
    )
    cache_dirs_by_ws: dict[str, HostPath] = field(default_factory=dict)
    installer_leases: dict[tuple[str, str], _ColdLockLease] = field(default_factory=dict)
    captures_by_ws: dict[str, list[StepEventCapture]] = field(default_factory=dict)
    guard: threading.RLock = field(default_factory=threading.RLock)
    cascade_cond: threading.Condition = field(default_factory=lambda: threading.Condition(threading.RLock()))


def compute_coalesce_context_suffix(
    caller_cwd: HostPath,
    caller_env: Mapping[str, str],
    approval_scope: frozenset[TaskId],
    allow_conditional: bool,
) -> str:
    """Isolate COALESCE equivalence keys across caller security scopes and working directories."""
    env_pairs = tuple(sorted(sanitize_caller_env(caller_env).items()))
    approvals = tuple(sorted(str(t) for t in approval_scope))
    digest_doc: JsonObject = {
        "cwd": caller_cwd.comparison_key,
        "env": [[k, v] for k, v in env_pairs],
        "apr": list(approvals),
        "cond": allow_conditional,
    }
    return DataclassCodec.canonical_hash(digest_doc)[:24]


def expand_colocated_tier1_siblings(
    target_mods: frozenset[ModuleId],
    all_descs: Sequence[ModuleDescriptor],
) -> frozenset[ModuleId]:
    """Expand target modules to include all co-located Tier 1 venv_group siblings."""
    affected_groups = {
        tier1_group_key_for(d)
        for d in all_descs
        if d.module_id in target_mods and d.venv_python is not None
    }
    if not affected_groups:
        return target_mods
    siblings = frozenset(
        d.module_id
        for d in all_descs
        if d.venv_python is not None and tier1_group_key_for(d) in affected_groups
    )
    return target_mods | siblings


def check_exposure_and_security_gates(request: InvokeRequest, spec: TaskRouteSpec) -> Optional[ErrorDetail]:
    """Validate task exposure surface and conditional/gated security tier authorization."""
    prop = request.propagation
    if spec.exposure == TaskExposure.INTERNAL_TRIGGER and not prop.is_internal_trigger:
        return ErrorDetail(
            code=ErrorCode.EXPOSURE_DENIED,
            message=f"Task '{request.task_id}' is INTERNAL_TRIGGER only.",
            source_task=str(request.task_id),
        )
    if spec.exposure == TaskExposure.SDK_ONLY and request.caller_surface == CallerSurface.CLI:
        return ErrorDetail(
            code=ErrorCode.EXPOSURE_DENIED,
            message=f"Task '{request.task_id}' is SDK_ONLY and cannot be called from CLI.",
            source_task=str(request.task_id),
        )
    if spec.security_tier == SecurityTier.CONDITIONAL and not request.allow_conditional:
        return ErrorDetail(
            code=ErrorCode.SECURITY_GATED,
            message=f"CONDITIONAL Task '{request.task_id}' blocked by caller policy.",
            source_task=str(request.task_id),
        )
    if spec.security_tier == SecurityTier.GATED:
        if prop.is_internal_trigger or prop.in_event_chain or request.priority == ExecutionPriority.BACKGROUND:
            return ErrorDetail(
                code=ErrorCode.SECURITY_GATED,
                message=f"GATED Task '{request.task_id}' cannot run in background or event-triggered context.",
                source_task=str(request.task_id),
            )
        if request.task_id not in request.approval_scope:
            return ErrorDetail(
                code=ErrorCode.SECURITY_GATED,
                message=f"Task '{request.task_id}' requires explicit GATED approval token.",
                source_task=str(request.task_id),
            )
    return None


def check_host_and_mutation_gates(
    request: InvokeRequest,
    spec: TaskRouteSpec,
    *,
    is_daemon_host: bool,
    conn_enabled: bool,
    in_cold_turn: bool = False,
) -> Optional[ErrorDetail]:
    """Validate interactive TTY, environment self-mutation, and cold/hot dispatch mode constraints."""
    prop = request.propagation
    if spec.interactive_tty and (
        prop.is_nested_call
        or bool(prop.call_stack)
        or bool(prop.coalesce_callers)
        or bool(prop.hot_workspaces)
        or prop.is_internal_trigger
        or prop.in_event_chain
        or prop.from_hot_container
        or is_daemon_host
        or request.priority != ExecutionPriority.FOREGROUND
    ):
        return ErrorDetail(
            code=ErrorCode.TTY_REQUIRED,
            message=f"Interactive TTY task '{request.task_id}' must run from foreground cold CLI.",
            remediation=f"Execute '{request.task_id}' directly in an interactive terminal.",
            source_task=str(request.task_id),
        )
    if spec.mutation_scope != SelfMutationScope.NONE and (
        prop.from_hot_container
        or is_daemon_host
        or bool(prop.hot_workspaces)
        or prop.is_internal_trigger
        or prop.in_event_chain
        or request.priority != ExecutionPriority.FOREGROUND
    ):
        return ErrorDetail(
            code=ErrorCode.HOT_MUTATION_FORBIDDEN,
            message=f"Environment-mutating task '{request.task_id}' requires foreground cold execution.",
            remediation="Invoke environment mutations from a foreground cold CLI process or COLD_ONLY orchestrator.",
            source_task=str(request.task_id),
        )
    return _check_dispatch_mode_constraints(
        request,
        spec,
        is_daemon_host=is_daemon_host,
        conn_enabled=conn_enabled,
        in_cold_turn=in_cold_turn,
    )


def _check_dispatch_mode_constraints(
    request: InvokeRequest,
    spec: TaskRouteSpec,
    *,
    is_daemon_host: bool,
    conn_enabled: bool,
    in_cold_turn: bool,
) -> Optional[ErrorDetail]:
    prop = request.propagation
    if spec.dispatch_mode == DispatchMode.COLD_ONLY and (
        request.routing_policy == ClientRoutingPolicy.STRICT_HOT or is_daemon_host or prop.from_hot_container
    ):
        return ErrorDetail(
            code=ErrorCode.COLD_DISPATCH_FORBIDDEN,
            message=f"COLD_ONLY task '{request.task_id}' rejects hot container dispatch.",
            source_task=str(request.task_id),
        )
    if spec.dispatch_mode == DispatchMode.DAEMON_ONLY:
        if request.routing_policy == ClientRoutingPolicy.FORCE_COLD:
            return ErrorDetail(
                code=ErrorCode.COLD_DISPATCH_FORBIDDEN,
                message=f"Task '{request.task_id}' is DAEMON_ONLY and rejects --cold.",
                source_task=str(request.task_id),
            )
        if not is_daemon_host and (in_cold_turn or not conn_enabled or prop.is_nested_call):
            return ErrorDetail(
                code=ErrorCode.DAEMON_UNAVAILABLE,
                message=f"Task '{request.task_id}' is DAEMON_ONLY and cannot execute in a local ColdTurn.",
                source_task=str(request.task_id),
            )
    return None


def validate_stage1_gates(
    request: InvokeRequest,
    found: Optional[tuple[ModuleDescriptor, TaskRouteSpec]],
    module_block_error: Optional[ErrorDetail],
    *,
    is_daemon_host: bool,
    conn_enabled: bool,
    in_cold_turn: bool = False,
) -> tuple[Optional[ErrorDetail], Optional[tuple[ModuleDescriptor, TaskRouteSpec]]]:
    """Run complete admission checks surfacing quiesce/degradation before TASK_NOT_FOUND."""
    if module_block_error is not None:
        return (module_block_error, None)
    if found is None:
        return (
            ErrorDetail(
                code=ErrorCode.TASK_NOT_FOUND,
                message=f"Task '{request.task_id}' is not registered.",
                source_task=str(request.task_id),
            ),
            None,
        )
    desc, spec = found
    sec_err = check_exposure_and_security_gates(request, spec)
    if sec_err is not None:
        return (sec_err, None)
    host_err = check_host_and_mutation_gates(
        request,
        spec,
        is_daemon_host=is_daemon_host,
        conn_enabled=conn_enabled,
        in_cold_turn=in_cold_turn,
    )
    if host_err is not None:
        return (host_err, None)
    stack_entry = (request.workspace_root, request.task_id)
    prop = request.propagation
    if stack_entry in prop.call_stack or (
        bool(prop.coalesce_callers) and all(stack_entry in c.call_stack for c in prop.coalesce_callers)
    ):
        ref_stack = prop.call_stack if stack_entry in prop.call_stack else prop.coalesce_callers[0].call_stack
        chain_str = " -> ".join(f"{tid}" for _ws, tid in (*ref_stack, stack_entry))
        return (
            CallCycleError(
                f"Synchronous task call cycle detected: {chain_str}",
                source_task=str(request.task_id),
            ).detail,
            None,
        )
    return (None, (desc, spec))


@dataclass(slots=True)
class _ModuleQuiesceEntry:
    leased: bool = False
    deadline: Optional[float] = None
    deferred_resume: bool = False


@dataclass(slots=True)
class _QuiesceLeaseState:
    epoch: int = 0
    draining_all: bool = False
    draining_mods: set[ModuleId] = field(default_factory=set)
    quiesced_all: bool = False
    leased_all: bool = False
    global_deadline: Optional[float] = None
    deferred_all: bool = False
    known_at_quiesce: Optional[frozenset[ModuleId]] = None
    active_resume_target: Optional[frozenset[ModuleId]] = None
    modules: dict[ModuleId, _ModuleQuiesceEntry] = field(default_factory=dict)
    pre_quiesce_mods: dict[str, set[ModuleId]] = field(default_factory=dict)
    pre_quiesce_all_ids: set[str] = field(default_factory=set)

    def record_lease(self, eff_global: bool, expanded_mods: frozenset[ModuleId], exp_at: float) -> int:
        self.epoch += 1
        if eff_global:
            self.deferred_all = False
            new_g = max(self.global_deadline or 0.0, exp_at)
            self.global_deadline = new_g
            for e in self.modules.values():
                e.deferred_resume = False
                if e.deadline is not None and e.deadline <= new_g:
                    e.deadline = None
            return self.epoch
        floor_dl = self.global_deadline or 0.0
        for m in expanded_mods:
            ent = self.modules.setdefault(m, _ModuleQuiesceEntry(leased=True))
            ent.leased = True
            ent.deferred_resume = False
            ent.deadline = max(ent.deadline or 0.0, floor_dl, exp_at)
        return self.epoch

    def postpone_due(self, due_mods: Optional[frozenset[ModuleId]], bump_dl: float) -> None:
        if due_mods is None:
            if self.global_deadline is not None:
                self.global_deadline = max(self.global_deadline, bump_dl)
            return
        for m in due_mods:
            ent = self.modules.get(m)
            if ent is not None and ent.deadline is not None:
                ent.deadline = max(ent.deadline, bump_dl)

    def schedule_deferred(self, eff_mods: Optional[frozenset[ModuleId]]) -> None:
        if eff_mods is None:
            if self.quiesced_all or self.modules:
                self.deferred_all = True
                for e in self.modules.values():
                    e.deferred_resume = False
            return
        for m in eff_mods:
            existing = self.modules.get(m)
            if existing is not None:
                existing.deferred_resume = True
            elif self.quiesced_all:
                self.modules[m] = _ModuleQuiesceEntry(
                    leased=self.leased_all,
                    deadline=self.global_deadline,
                    deferred_resume=True,
                )


class LifecycleReloadGate:
    """Single authoritative state machine for module step tracking, quiesce leases, and reload gates."""

    def __init__(self, workspace_root: HostPath) -> None:
        self._workspace_root = workspace_root
        self._gate_listeners: list[Callable[[], None]] = []
        self._op_lock = threading.RLock()
        self._cond = threading.Condition(threading.Lock())
        self._in_flight_turns: dict[str, int] = {}
        self._in_flight_trees: dict[str, int] = {}
        self._in_flight_mods: dict[ModuleId, int] = {}
        self._admitted_rpc_turns: dict[tuple[str, ModuleId], int] = {}
        self._q = _QuiesceLeaseState()
        self._reloading_mod_counts: dict[ModuleId, int] = {}
        self._reload_exempt_turns: dict[str, int] = {}
        self._module_reload_epochs: dict[ModuleId, int] = {}
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
        acquired = (
            self._op_lock.acquire()
            if timeout_sec is None
            else self._op_lock.acquire(blocking=True, timeout=max(0.0, timeout_sec))
        )
        try:
            yield acquired
        finally:
            if acquired:
                self._op_lock.release()

    def has_any_active_work(self) -> bool:
        with self._cond:
            return any(c > 0 for c in self._in_flight_mods.values()) or any(
                c > 0 for c in self._admitted_rpc_turns.values()
            )

    def has_any_quiesced(self) -> bool:
        with self._cond:
            return bool(
                self._q.quiesced_all
                or self._q.draining_all
                or self._q.modules
                or self._q.draining_mods
                or self._q.active_resume_target is not None
            )

    def register_gate_listener(self, listener: Callable[[], None]) -> None:
        with self._cond:
            self._gate_listeners.append(listener)

    def _fire_gate_change(self) -> None:
        with self._cond:
            self._transition_seq += 1
            listeners = tuple(self._gate_listeners)
        for cb in listeners:
            invoke_observer_safely(cb)

    def _is_global_resuming_locked(self) -> bool:
        return self._q.active_resume_target is not None and not self._q.active_resume_target

    def _is_mod_resuming_locked(self, mod_id: ModuleId) -> bool:
        return self._q.active_resume_target is not None and (
            not self._q.active_resume_target or mod_id in self._q.active_resume_target
        )

    def is_globally_quiesced(self) -> bool:
        with self._cond:
            return self._q.quiesced_all or self._q.draining_all

    def is_globally_gated(self) -> bool:
        with self._cond:
            return self._q.quiesced_all or self._q.draining_all or self._is_global_resuming_locked()

    def active_quiesced_modules(self) -> frozenset[ModuleId]:
        with self._cond:
            return frozenset(self._q.modules.keys())

    def is_module_quiesced(self, target_mod: ModuleId) -> bool:
        if target_mod == ModuleId("core"):
            return False
        with self._cond:
            return self._q.quiesced_all or (target_mod in self._q.modules)

    def is_call_gated_for_quiesce(self, target_mod: Optional[ModuleId]) -> bool:
        with self._cond:
            if target_mod is None:
                return False
            if target_mod == ModuleId("core"):
                return False
            if self._q.draining_all or self._q.quiesced_all or self._is_global_resuming_locked():
                return True
            return (
                target_mod in self._q.draining_mods
                or target_mod in self._q.modules
                or self._is_mod_resuming_locked(target_mod)
            )

    def _is_prop_reentrant_draining_locked(self, prop: CallPropagationContext) -> bool:
        tid = prop.turn_id or ""
        ctree = prop.call_tree_id or ""
        if self._turn_admitted_for_draining_locked(tid):
            return True
        if (bool(tid) and tid in self._in_flight_turns) or (bool(ctree) and ctree in self._in_flight_trees):
            return True
        if any(
            self._turn_admitted_for_draining_locked(c.turn_id)
            or (bool(c.turn_id) and c.turn_id in self._in_flight_turns)
            or (bool(c.call_tree_id) and c.call_tree_id in self._in_flight_trees)
            for c in prop.coalesce_callers
        ):
            return True
        dr_all, dr_mods = self._q.draining_all, self._q.draining_mods
        stacks = (prop.call_stack, *(c.call_stack for c in prop.coalesce_callers))
        return any(ws == self._workspace_root and (dr_all or tid.module_id in dr_mods) for st in stacks for ws, tid in st)

    def _is_prop_leased_exempt_locked(self, prop: CallPropagationContext, target_mod: ModuleId) -> bool:
        ent = self._q.modules.get(target_mod)
        if not (self._q.leased_all or (ent is not None and ent.leased)):
            return False
        return self._is_leased_pre_quiesce_locked(prop, target_mod)

    def _is_rpc_mod_blocked_locked(
        self,
        target_mod: ModuleId,
        prop: Optional[CallPropagationContext],
    ) -> bool:
        if target_mod == ModuleId("core"):
            return False
        if self._is_mod_resuming_locked(target_mod):
            return True
        is_draining = self._q.draining_all or target_mod in self._q.draining_mods
        if is_draining and (prop is None or not self._is_prop_reentrant_draining_locked(prop)):
            return True
        is_quiesced = self._q.quiesced_all or target_mod in self._q.modules
        if is_quiesced and (prop is None or not self._is_prop_leased_exempt_locked(prop, target_mod)):
            return True
        return False

    def is_rpc_call_gated(
        self,
        target_mod: Optional[ModuleId],
        prop: Optional[CallPropagationContext] = None,
    ) -> bool:
        if target_mod is None or target_mod == ModuleId("core"):
            return False
        with self._cond:
            return self._is_rpc_mod_blocked_locked(target_mod, prop)

    def _id_exempt_for_mod_locked(self, ident: str, target_mod: ModuleId) -> bool:
        if not ident:
            return False
        if ident in self._q.pre_quiesce_all_ids:
            return True
        allowed = self._q.pre_quiesce_mods.get(ident)
        return allowed is not None and target_mod in allowed

    def _is_leased_pre_quiesce_locked(self, prop: CallPropagationContext, target_mod: ModuleId) -> bool:
        if self._id_exempt_for_mod_locked(prop.turn_id or "", target_mod) or self._id_exempt_for_mod_locked(
            prop.call_tree_id or "", target_mod
        ):
            return True
        return any(
            self._id_exempt_for_mod_locked(c.turn_id, target_mod)
            or self._id_exempt_for_mod_locked(c.call_tree_id, target_mod)
            for c in prop.coalesce_callers
        )

    def has_admitted_rpc_turn(self, call_id: str) -> bool:
        if not call_id:
            return False
        with self._cond:
            return any(cid == call_id and cnt > 0 for (cid, _m), cnt in self._admitted_rpc_turns.items())

    def enter_rpc_call(
        self,
        mod_id: ModuleId,
        call_id: str,
        prop: Optional[CallPropagationContext] = None,
    ) -> bool:
        with self._cond:
            if self._is_rpc_mod_blocked_locked(mod_id, prop):
                return False
            key = (call_id or "_", mod_id)
            self._admitted_rpc_turns[key] = self._admitted_rpc_turns.get(key, 0) + 1
            return True

    def exit_rpc_call(self, mod_id: ModuleId, call_id: str) -> None:
        with self._cond:
            decrement_ref_count(self._admitted_rpc_turns, (call_id or "_", mod_id))
            self._cond.notify_all()

    def record_quiesce_lease(
        self,
        eff_global: bool,
        expanded_mods: frozenset[ModuleId],
        lease_sec: float,
    ) -> int:
        safe_sec = clamp_positive_sec(lease_sec, min_sec=0.05, max_sec=3600.0, label="lease_sec")
        with self._cond:
            ep = self._q.record_lease(eff_global, expanded_mods, time.monotonic() + safe_sec)
            self._cond.notify_all()
        self._fire_gate_change()
        return ep

    def due_quiesce_resume(self, now: float) -> Optional[DueQuiesceResume]:
        f_now = _validate_monotonic_now(now)
        with self._cond:
            if self._q.active_resume_target is not None:
                return None
            if self._q.deferred_all:
                return DueQuiesceResume(self._q.epoch, modules=None)
            def_mods = frozenset(m for m, e in self._q.modules.items() if e.deferred_resume)
            if def_mods:
                return DueQuiesceResume(self._q.epoch, modules=def_mods)
            if self._q.global_deadline is not None:
                if f_now < self._q.global_deadline:
                    return None
                longer = frozenset(m for m, e in self._q.modules.items() if e.deadline is not None and e.deadline > f_now)
                return DueQuiesceResume(self._q.epoch, modules=None, preserve_modules=longer)
            due_mods = frozenset(m for m, e in self._q.modules.items() if e.deadline is not None and f_now >= e.deadline)
            return DueQuiesceResume(self._q.epoch, modules=due_mods) if due_mods else None

    def next_quiesce_wakeup(self, now: float) -> Optional[float]:
        f_now = _validate_monotonic_now(now)
        with self._cond:
            if self._q.active_resume_target is not None:
                return None
            cands: list[float] = []
            if self._q.deferred_all or any(e.deferred_resume for e in self._q.modules.values()):
                cands.append(0.01)
            if self._q.global_deadline is not None:
                cands.append(min(MAX_SAFE_WAIT_SEC, max(0.01, self._q.global_deadline - f_now)))
            for e in self._q.modules.values():
                if e.deadline is not None:
                    cands.append(min(MAX_SAFE_WAIT_SEC, max(0.01, e.deadline - f_now)))
            return min(cands) if cands else None

    def postpone_due_lease(
        self,
        epoch: int,
        due_mods: Optional[frozenset[ModuleId]],
        retry_after_sec: float,
    ) -> None:
        require_pure_int(epoch, "epoch", min_val=0)
        safe_retry = clamp_positive_sec(retry_after_sec, min_sec=0.05, max_sec=3600.0, label="retry_after_sec")
        bump_dl = time.monotonic() + safe_retry
        with self._cond:
            if self._q.epoch == epoch:
                self._q.postpone_due(due_mods, bump_dl)

    def schedule_deferred_resume(
        self,
        expected_epoch: Optional[int],
        eff_mods: Optional[frozenset[ModuleId]],
    ) -> None:
        if expected_epoch is not None:
            require_pure_int(expected_epoch, "expected_epoch", min_val=0)
        with self._cond:
            if expected_epoch is not None and self._q.epoch != expected_epoch:
                return
            self._q.schedule_deferred(eff_mods)
            self._cond.notify_all()
        self._fire_gate_change()

    def _can_wait_leased_quiesce_locked(self, request: InvokeRequest, target_mod: ModuleId) -> bool:
        ent = self._q.modules.get(target_mod)
        if not (self._q.leased_all or (ent is not None and ent.leased)):
            return False
        if self._is_leased_pre_quiesce_locked(request.propagation, target_mod):
            return True
        prop = request.propagation
        if prop.in_event_chain:
            return False
        if prop.coalesce_callers:
            return any(not c.in_event_chain for c in prop.coalesce_callers)
        return True

    def _is_reload_exempt_locked(self, request: InvokeRequest) -> bool:
        prop = request.propagation
        if (bool(prop.turn_id) and prop.turn_id in self._reload_exempt_turns) or (
            bool(prop.call_tree_id) and prop.call_tree_id in self._reload_exempt_turns
        ):
            return True
        all_rel = self._reloading_all_count > 0
        rel_mods = self._reloading_mod_counts
        stacks = (prop.call_stack, *(c.call_stack for c in prop.coalesce_callers))
        if any(c.turn_id in self._reload_exempt_turns or c.call_tree_id in self._reload_exempt_turns for c in prop.coalesce_callers):
            return True
        return any(ws == self._workspace_root and (all_rel or tid.module_id in rel_mods) for st in stacks for ws, tid in st)

    def _turn_admitted_for_draining_locked(self, turn_id: str) -> bool:
        if not turn_id:
            return False
        return any(
            tid == turn_id and cnt > 0 and (self._q.draining_all or m in self._q.draining_mods)
            for (tid, m), cnt in self._admitted_rpc_turns.items()
        )

    def _should_wait_on_gate_locked(self, request: InvokeRequest, target_mod: ModuleId) -> bool:
        if target_mod == ModuleId("core"):
            return False
        if (self._q.draining_all or target_mod in self._q.draining_mods) and not self._is_prop_reentrant_draining_locked(
            request.propagation
        ):
            return True
        if (
            self._q.quiesced_all or target_mod in self._q.modules
        ) and self._can_wait_leased_quiesce_locked(request, target_mod):
            return True
        if not self._is_reload_exempt_locked(request) and (
            self._reloading_all_count > 0 or target_mod in self._reloading_mod_counts
        ):
            return True
        return False


    def run_quiesce_resume_guarded(
        self,
        expected_epoch: Optional[int],
        eff_mods: Optional[frozenset[ModuleId]],
        expanded_cands: frozenset[ModuleId],
        body_fn: Callable[[], bool],
        *,
        force_global: bool = False,
    ) -> QuiesceResumeResult:
        if not self._begin_quiesce_resume(expected_epoch, eff_mods, expanded_cands, force_global=force_global):
            return QuiesceResumeResult(started=False, need_handoff=False, still_quiesced=True)
        try:
            need_handoff = body_fn()
        finally:
            still_quiesced = self._end_quiesce_resume()
        return QuiesceResumeResult(started=True, need_handoff=need_handoff, still_quiesced=still_quiesced)

    @contextmanager
    def resume_reload_scope(
        self,
        fresh_descs: Sequence[ModuleDescriptor],
        target_modules: Optional[frozenset[ModuleId]] = None,
        *,
        preserve_modules: frozenset[ModuleId] = frozenset(),
        deferred_boot: bool = False,
    ) -> Iterator[ResumeConsumePlan]:
        plan = self._consume_for_resume(
            fresh_descs,
            target_modules,
            preserve_modules=preserve_modules,
            deferred_boot=deferred_boot,
        )
        try:
            yield plan
        finally:
            self._exit_reload_gate(plan.was_all, plan.touched_all, ())

    @contextmanager
    def module_reload_scope(
        self,
        reload_all: bool,
        initial_gated: frozenset[ModuleId],
    ) -> Iterator[Callable[[frozenset[ModuleId], bool], None]]:
        acc_gated = initial_gated
        exempt_batches: list[frozenset[str]] = [self._enter_reload_gate(reload_all, initial_gated)]

        def _update_stage(mods: frozenset[ModuleId], bump_epochs: bool) -> None:
            nonlocal acc_gated
            if bump_epochs:
                self._bump_reload_epochs(mods)
                return
            new_mods = mods - acc_gated
            if new_mods:
                exempt_batches.append(self._enter_reload_gate(False, new_mods))
                acc_gated = acc_gated | new_mods

        try:
            yield _update_stage
        finally:
            self._exit_reload_gate(reload_all, acc_gated, exempt_batches)

    def _compute_deferred_boot_keep_locked(
        self,
        fresh_descs: Sequence[ModuleDescriptor],
        all_now: frozenset[ModuleId],
        selective_mods: Optional[frozenset[ModuleId]],
        preserve_modules: frozenset[ModuleId],
    ) -> frozenset[ModuleId]:
        base_keep = (
            (expand_colocated_tier1_siblings(preserve_modules, fresh_descs) - frozenset({ModuleId("core")}))
            if preserve_modules
            else frozenset()
        )
        if selective_mods is None:
            return base_keep & all_now
        resumed_exp = expand_colocated_tier1_siblings(selective_mods, fresh_descs) - frozenset({ModuleId("core")})
        now = time.monotonic()
        if self._q.global_deadline is not None and now < self._q.global_deadline:
            leased_active = all_now - resumed_exp
        else:
            seeds = frozenset(m for m, e in self._q.modules.items() if e.deadline is not None and now < e.deadline)
            leased_active = (expand_colocated_tier1_siblings(seeds, fresh_descs) & all_now) - resumed_exp
        return ((base_keep | leased_active) - resumed_exp) & all_now

    def any_descriptor_reloading(self, descriptors: Sequence[ModuleDescriptor]) -> bool:
        with self._cond:
            return self._reloading_all_count > 0 or any(d.module_id in self._reloading_mod_counts for d in descriptors)

    def has_leased_pre_quiesce(self, turn_id: str, call_tree_id: str) -> bool:
        with self._cond:
            return any(
                bool(k) and (k in self._q.pre_quiesce_all_ids or k in self._q.pre_quiesce_mods)
                for k in (turn_id, call_tree_id)
            )

    def enter_host_step(self, mod_id: ModuleId, turn_id: str, call_tree_id: str) -> None:
        with self._cond:
            if turn_id:
                self._in_flight_turns[turn_id] = self._in_flight_turns.get(turn_id, 0) + 1
            if call_tree_id:
                self._in_flight_trees[call_tree_id] = self._in_flight_trees.get(call_tree_id, 0) + 1
            self._in_flight_mods[mod_id] = self._in_flight_mods.get(mod_id, 0) + 1

    def exit_host_step(self, mod_id: ModuleId, turn_id: str, call_tree_id: str) -> None:
        with self._cond:
            decrement_ref_count(self._in_flight_turns, turn_id)
            decrement_ref_count(self._in_flight_trees, call_tree_id)
            decrement_ref_count(self._in_flight_mods, mod_id)
            self._cond.notify_all()

    @contextmanager
    def host_step_scope(self, mod_id: ModuleId, turn_id: str, call_tree_id: str) -> Iterator[None]:
        self.enter_host_step(mod_id, turn_id, call_tree_id)
        try:
            yield
        finally:
            self.exit_host_step(mod_id, turn_id, call_tree_id)

    def _has_active_quiesce_conflict_locked(self, q_all: bool, target_mods: frozenset[ModuleId]) -> bool:
        if q_all:
            return any(m != ModuleId("core") and cnt > 0 for m, cnt in self._in_flight_mods.items()) or any(
                m != ModuleId("core") and cnt > 0 for (_cid, m), cnt in self._admitted_rpc_turns.items()
            )
        return any(self._in_flight_mods.get(m, 0) > 0 for m in target_mods) or any(
            m in target_mods and cnt > 0 for (_cid, m), cnt in self._admitted_rpc_turns.items()
        )

    def _commit_quiesce_state_locked(
        self,
        known_now: frozenset[ModuleId],
        target_mods: frozenset[ModuleId],
        q_all: bool,
        leased: bool,
        pre_accepted_ids: frozenset[str],
    ) -> None:
        if self._q.known_at_quiesce is None:
            self._q.known_at_quiesce = known_now
            self._q.quiesced_all = q_all
        elif q_all:
            self._q.quiesced_all = True
        for m in target_mods:
            ent = self._q.modules.setdefault(m, _ModuleQuiesceEntry())
            if leased:
                ent.leased = True
        if leased:
            if q_all:
                self._q.leased_all = True
            live_ids = (
                frozenset(self._in_flight_turns.keys())
                | frozenset(self._in_flight_trees.keys())
                | frozenset(tid for tid, _m in self._admitted_rpc_turns.keys() if tid != "_")
                | pre_accepted_ids
            )
            if q_all:
                self._q.pre_quiesce_all_ids.update(live_ids)
            else:
                for lid in live_ids:
                    self._q.pre_quiesce_mods.setdefault(lid, set()).update(target_mods)

    def try_begin_quiesce(
        self,
        modules: frozenset[ModuleId],
        all_descs: Sequence[ModuleDescriptor],
        *,
        drain_deadline: Optional[float] = None,
        leased: bool = False,
        pre_accepted_ids: frozenset[str] = frozenset(),
    ) -> Optional[frozenset[ModuleId]]:
        safe_dl = normalize_drain_deadline(drain_deadline)
        known_now = frozenset(d.module_id for d in all_descs if d.module_id != ModuleId("core"))
        q_all = (not bool(modules)) or (ModuleId("core") in modules)
        target_mods = (
            known_now
            if q_all
            else (expand_colocated_tier1_siblings(modules, all_descs) - frozenset({ModuleId("core")}))
        )
        with self._cond:
            newly_draining = target_mods - self._q.draining_mods
            prev_drain_all = self._q.draining_all
            self._q.draining_mods.update(newly_draining)
            if q_all:
                self._q.draining_all = True
            self._cond.notify_all()
            while self._has_active_quiesce_conflict_locked(q_all, target_mods) and (
                safe_dl is None or time.monotonic() < safe_dl
            ):
                rem = 0.02 if safe_dl is None else min(0.02, max(0.001, safe_dl - time.monotonic()))
                self._cond.wait(timeout=rem)
            still_busy = self._has_active_quiesce_conflict_locked(q_all, target_mods)
            self._q.draining_mods.difference_update(newly_draining)
            self._q.draining_all = prev_drain_all
            aborted_busy = still_busy and leased
            if not aborted_busy:
                self._commit_quiesce_state_locked(known_now, target_mods, q_all, leased, pre_accepted_ids)
            self._cond.notify_all()
        self._fire_gate_change()
        return None if aborted_busy else target_mods

    def _compute_resume_plan_locked(
        self,
        fresh_descs: Sequence[ModuleDescriptor],
        all_now: frozenset[ModuleId],
        selective_req: bool,
        target_modules: Optional[frozenset[ModuleId]],
        keep_mods: frozenset[ModuleId],
    ) -> _ResumePlanInternal:
        cur_mods = frozenset(self._q.modules.keys())
        universe = all_now | cur_mods
        if not selective_req and keep_mods:
            remaining = all_now & keep_mods
            raw_seed = universe - remaining
            re_warm = ((expand_colocated_tier1_siblings(raw_seed, fresh_descs) | raw_seed) & all_now) - remaining
            return _ResumePlanInternal(re_warm, raw_seed | re_warm, remaining, False)
        if selective_req and target_modules is not None:
            exp_targets = expand_colocated_tier1_siblings(target_modules, fresh_descs) - frozenset({ModuleId("core")})
            raw_seed = (cur_mods & exp_targets) | exp_targets
            re_warm = (expand_colocated_tier1_siblings(raw_seed, fresh_descs) | raw_seed) & all_now
            touched = raw_seed | re_warm
            rem = ((universe - touched) if self._q.quiesced_all else (cur_mods - touched)) & all_now
            return _ResumePlanInternal(re_warm, touched, rem, False)
        known_prev = self._q.known_at_quiesce
        newly_added = (all_now - known_prev) if known_prev is not None else frozenset()
        was_all = self._q.quiesced_all
        raw_seed = cur_mods | newly_added
        re_warm = all_now if was_all else ((expand_colocated_tier1_siblings(raw_seed, fresh_descs) | raw_seed) & all_now)
        touched = all_now if was_all else (raw_seed | re_warm)
        return _ResumePlanInternal(re_warm, touched, frozenset(), was_all)

    def _apply_remaining_quiesce_entries_locked(
        self,
        all_now: frozenset[ModuleId],
        remaining: frozenset[ModuleId],
        touched_all: frozenset[ModuleId],
        full_global: bool,
    ) -> None:
        if full_global or not remaining:
            self._q.modules.clear()
            self._q.leased_all = False
            self._q.quiesced_all = False
            self._q.known_at_quiesce = None
            self._q.global_deadline = None
            self._q.deferred_all = False
            self._q.pre_quiesce_mods.clear()
            self._q.pre_quiesce_all_ids.clear()
            return
        prev_g = self._q.global_deadline
        prev_leased_all = self._q.leased_all
        fallback_dl = prev_g if prev_g is not None else (time.monotonic() + 10.0)
        self._q.global_deadline = None
        self._q.quiesced_all = False
        self._q.leased_all = False
        self._q.known_at_quiesce = all_now
        for lid in self._q.pre_quiesce_all_ids:
            self._q.pre_quiesce_mods.setdefault(lid, set()).update(remaining)
        self._q.pre_quiesce_all_ids.clear()
        for lid in list(self._q.pre_quiesce_mods.keys()):
            s = self._q.pre_quiesce_mods[lid]
            s.difference_update(touched_all)
            s.intersection_update(remaining)
            if not s:
                self._q.pre_quiesce_mods.pop(lid, None)
        next_mods: dict[ModuleId, _ModuleQuiesceEntry] = {}
        for m in remaining:
            old_e = self._q.modules.get(m)
            was_leased = prev_leased_all or (old_e.leased if old_e is not None else False)
            old_dl = old_e.deadline if old_e is not None else None
            new_dl = (
                (max(old_dl or 0.0, prev_g) if prev_g is not None else (old_dl or fallback_dl))
                if was_leased
                else None
            )
            def_r = (old_e.deferred_resume if old_e is not None else False) and m not in touched_all
            next_mods[m] = _ModuleQuiesceEntry(leased=was_leased, deadline=new_dl, deferred_resume=def_r)
        self._q.modules = next_mods

    def _consume_for_resume(
        self,
        fresh_descs: Sequence[ModuleDescriptor],
        target_modules: Optional[frozenset[ModuleId]] = None,
        *,
        preserve_modules: frozenset[ModuleId] = frozenset(),
        deferred_boot: bool = False,
    ) -> ResumeConsumePlan:
        all_now = frozenset(d.module_id for d in fresh_descs if d.module_id != ModuleId("core"))
        raw_sel = target_modules if (target_modules and ModuleId("core") not in target_modules) else None
        with self._cond:
            if deferred_boot:
                keep_mods = self._compute_deferred_boot_keep_locked(fresh_descs, all_now, raw_sel, preserve_modules)
                eff_target: Optional[frozenset[ModuleId]] = None
                selective_req = False
                was_boot_all = not keep_mods
            else:
                selective_req = raw_sel is not None
                eff_target = raw_sel
                keep_mods = (
                    (expand_colocated_tier1_siblings(preserve_modules, fresh_descs) - frozenset({ModuleId("core")}))
                    if (not selective_req and preserve_modules)
                    else frozenset()
                )
                was_boot_all = False
            plan = self._compute_resume_plan_locked(
                fresh_descs, all_now, selective_req, eff_target, keep_mods
            )
            was_all = plan.was_all or was_boot_all
            if was_all:
                self._reloading_all_count += 1
            for m in plan.touched:
                self._reloading_mod_counts[m] = self._reloading_mod_counts.get(m, 0) + 1
                self._module_reload_epochs[m] = self._module_reload_epochs.get(m, 0) + 1
            self._apply_remaining_quiesce_entries_locked(
                all_now, plan.remaining, plan.touched, eff_target is None and not keep_mods
            )
            self._cond.notify_all()
        self._fire_gate_change()
        return ResumeConsumePlan(plan.re_warm, plan.touched, was_all)

    def _begin_quiesce_resume(
        self,
        expected_epoch: Optional[int],
        eff_mods: Optional[frozenset[ModuleId]],
        expanded_cands: frozenset[ModuleId],
        *,
        force_global: bool = False,
    ) -> bool:
        if expected_epoch is not None:
            require_pure_int(expected_epoch, "expected_epoch", min_val=0)
        with self._cond:
            if self._q.active_resume_target is not None:
                return False
            target_ep = expected_epoch if expected_epoch is not None else self._q.epoch
            if self._q.epoch != target_ep:
                return False
            all_cur = frozenset(self._q.modules.keys())
            is_global = force_global or (
                eff_mods is None
                and (
                    self._q.global_deadline is not None
                    or self._q.deferred_all
                    or self._q.quiesced_all
                    or self._q.draining_all
                )
            )
            self._q.active_resume_target = (
                frozenset() if is_global else (expanded_cands if eff_mods is not None else all_cur)
            )
            self._cond.notify_all()
        self._fire_gate_change()
        return True

    def _end_quiesce_resume(self) -> bool:
        with self._cond:
            self._q.active_resume_target = None
            still_active = bool(
                self._q.draining_all
                or self._q.quiesced_all
                or self._q.draining_mods
                or self._q.modules
                or self._q.global_deadline is not None
            )
            self._cond.notify_all()
        self._fire_gate_change()
        return still_active

    def is_quiesced_blocked(self, request: InvokeRequest, target_mod: ModuleId, is_daemon_host: bool) -> bool:
        if not is_daemon_host or target_mod == ModuleId("core"):
            return False
        with self._cond:
            if self._can_wait_leased_quiesce_locked(request, target_mod):
                return False
            return self._q.quiesced_all or (target_mod in self._q.modules)

    def _bump_reload_epochs(self, mods: frozenset[ModuleId]) -> None:
        with self._cond:
            for m in mods:
                self._module_reload_epochs[m] = self._module_reload_epochs.get(m, 0) + 1

    def current_epoch(self, mod_id: ModuleId) -> int:
        with self._cond:
            return self._module_reload_epochs.get(mod_id, 0)

    def _enter_reload_gate(self, reload_all: bool, gated_mods: frozenset[ModuleId]) -> frozenset[str]:
        with self._cond:
            exempt_now = frozenset(k for k in self._in_flight_turns if k) | frozenset(
                k for k in self._in_flight_trees if k
            )
            if reload_all:
                self._reloading_all_count += 1
            for m in gated_mods:
                self._reloading_mod_counts[m] = self._reloading_mod_counts.get(m, 0) + 1
            for eid in exempt_now:
                self._reload_exempt_turns[eid] = self._reload_exempt_turns.get(eid, 0) + 1
            self._cond.notify_all()
        self._fire_gate_change()
        return exempt_now

    def _exit_reload_gate(
        self,
        reload_all: bool,
        gated_mods: frozenset[ModuleId],
        exempt_batches: Sequence[frozenset[str]],
    ) -> None:
        with self._cond:
            if reload_all:
                self._reloading_all_count = max(0, self._reloading_all_count - 1)
            for m in gated_mods:
                decrement_ref_count(self._reloading_mod_counts, m)
            for batch in exempt_batches:
                for eid in batch:
                    decrement_ref_count(self._reload_exempt_turns, eid)
            self._cond.notify_all()
        self._fire_gate_change()

    def has_turn_or_tree_exempt(self, turn_id: str, call_tree_id: str) -> bool:
        with self._cond:
            return (bool(turn_id) and turn_id in self._reload_exempt_turns) or (
                bool(call_tree_id) and call_tree_id in self._reload_exempt_turns
            )

    def is_request_reload_exempt(
        self,
        request: InvokeRequest,
        is_reentrant_retiring: Callable[[InvokeRequest], bool],
    ) -> bool:
        if is_reentrant_retiring(request):
            return True
        with self._cond:
            return self._is_reload_exempt_locked(request)

    def is_step_blocked_by_reload(
        self,
        parent_req: InvokeRequest,
        is_reentrant_retiring: Callable[[InvokeRequest], bool],
    ) -> bool:
        if is_reentrant_retiring(parent_req):
            return False
        target_mod = parent_req.task_id.module_id
        with self._cond:
            return self._should_wait_on_gate_locked(parent_req, target_mod)

    def _wait_one_reload_slice(
        self,
        request: InvokeRequest,
        target_mod: ModuleId,
        token: CancellationToken,
        deadline: Optional[float],
    ) -> bool:
        with self._cond:
            if not self._should_wait_on_gate_locked(request, target_mod) or token.is_cancelled:
                return False
            if deadline is not None and time.monotonic() >= deadline:
                raise YscbError(
                    ErrorCode.TASK_TIMEOUT,
                    f"Timed out waiting for module '{target_mod}' lifecycle gate.",
                    source_task=str(request.task_id),
                )
            rem = 0.02 if deadline is None else min(0.02, max(0.001, deadline - time.monotonic()))
            self._cond.wait(timeout=rem)
            return True

    def wait_if_module_reloading(
        self,
        request: InvokeRequest,
        token: CancellationToken,
        is_reentrant_retiring: Callable[[InvokeRequest], bool],
        *,
        timeout_ms: Optional[int] = None,
    ) -> None:
        deadline = (time.monotonic() + ms_to_safe_sec(timeout_ms)) if timeout_ms is not None else None
        target_mod = request.task_id.module_id
        def _wake_gate(_p: bool, _r: Optional[str]) -> None:
            with self._cond:
                self._cond.notify_all()

        unreg = token.register_callback(_wake_gate)
        try:
            while not token.is_cancelled and not is_reentrant_retiring(request):
                if not self._wait_one_reload_slice(request, target_mod, token, deadline):
                    return
        finally:
            unreg()


def _is_same_tree_installer_owner(owner_path: HostPath, call_tree_id: str) -> bool:
    if not call_tree_id:
        return False
    doc = read_live_owner_dict(owner_path)
    return doc is not None and doc.get("call_tree_id") == call_tree_id


def _abort_cold_turn_scope(
    turn_scope: TurnScope,
    detail: ErrorDetail,
    *,
    fatal_abort: bool = False,
) -> TurnExecutionReport:
    td_errs = turn_scope.close_scoped_stack_recorded()
    return TurnExecutionReport(
        turn_id=turn_scope.turn_id,
        primary_result=StepExecutionResult(ok=False, error=detail, fatal_abort_turn=fatal_abort),
        teardown_diagnostics=td_errs,
    )


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
        self,
        workspace_root: HostPath,
        cache_dir: HostPath,
        turn_engine: TurnEngine[InvokeRequest],
        bootstrap_hook: Callable[[], None],
    ) -> None:
        self._workspace_root = workspace_root
        self._cache_dir = cache_dir
        self._bootstrap_hook = bootstrap_hook
        self._cold_runner = ColdTurnRunner(turn_engine, on_bootstrap_check=lambda _s: bootstrap_hook())
        self.reentry_lock: threading.RLock = threading.RLock()
        self.leases: dict[tuple[str, str], _ColdLockLease] = {}

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

        paths = CrossProcessLockPaths.for_stem(resolve_contained_subpath(self._cache_dir, "locks"), "installer")
        unlink_owner_under_pin(paths.owner_path, paths.pin_path, _do_downgrade)

    def _take_idle_lease_handles_locked(
        self,
        lock_key: tuple[str, str],
        lease: _ColdLockLease,
    ) -> _IdleColdLeaseHandles:
        if lease.excl_refs > 0 or lease.shared_refs > 0:
            return _IdleColdLeaseHandles()
        if self.leases.get(lock_key) is lease:
            self.leases.pop(lock_key, None)
        pin = lease.pin_lock
        lease.pin_lock = None
        unlink_ow = lease.has_owner_file
        lease.has_owner_file = False
        return _IdleColdLeaseHandles(lease.lock, pin, unlink_ow)

    def _release_lease_slot(self, lock_key: tuple[str, str], lease: _ColdLockLease, *, was_excl: bool) -> None:
        with lease.op_lock:
            with self.reentry_lock:
                rem_shared, need_downgrade = lease.dec_counts(was_excl)
            if need_downgrade:
                self._downgrade_lease_os_lock(lock_key, lease, rem_shared)
            with self.reentry_lock:
                idle_h = self._take_idle_lease_handles_locked(lock_key, lease)
        if idle_h.pin_lock is not None:
            idle_h.pin_lock.release()
        if idle_h.unlink_owner:
            paths = CrossProcessLockPaths.for_stem(resolve_contained_subpath(self._cache_dir, "locks"), "installer")
            unlink_owner_under_pin(
                paths.owner_path,
                paths.pin_path,
                lambda: idle_h.lock.release() if idle_h.lock is not None else None,
            )
        elif idle_h.lock is not None:
            idle_h.lock.release()

    def bind_shared(
        self,
        shared_ws: SharedWorkspaceState,
        own_coordinator: ResourceCoordinator,
    ) -> ResourceCoordinator:
        with shared_ws.guard:
            existing = shared_ws.coordinators.get(self._workspace_root.comparison_key)
            if isinstance(existing, ResourceCoordinator):
                chosen = existing
            else:
                shared_ws.coordinators[self._workspace_root.comparison_key] = own_coordinator
                chosen = own_coordinator
        chosen.bind_shared_peers(shared_ws.coordinators, shared_ws.cache_dirs_by_ws, shared_ws.guard)
        self.leases = shared_ws.installer_leases
        self.reentry_lock = shared_ws.guard
        return chosen

    def run_cold_event_turn(
        self,
        turn_scope: TurnScope,
        fn: Callable[[], TurnExecutionReport],
    ) -> TurnExecutionReport:
        turn_id = turn_scope.turn_id
        lock_key = self._lock_scope_key(turn_id)
        try:
            lock = CrossProcessLockPaths.for_stem(resolve_contained_subpath(self._cache_dir, "locks"), "installer").lock_file
            lock.acquire(shared=True, blocking=True, timeout_sec=30.0, cancel_token=turn_scope.cancel_token)
        except (TaskCancelledException, YscbError) as exc:
            det = exc.detail.with_fallback_task("core.watcher")
            td_errs = turn_scope.close_scoped_stack_recorded()
            return TurnExecutionReport(
                turn_id=turn_id,
                primary_result=StepExecutionResult(ok=False, error=det),
                teardown_diagnostics=td_errs,
            )
        lease = _ColdLockLease(lock=lock, shared_refs=1)
        installed = False
        try:
            with self.reentry_lock:
                self.leases[lock_key] = lease
                installed = True
            return self._execute_bootstrapped_event_turn(turn_scope, fn)
        finally:
            if installed:
                self._release_lease_slot(lock_key, lease, was_excl=False)
            else:
                lock.release()

    def _execute_bootstrapped_event_turn(
        self,
        turn_scope: TurnScope,
        fn: Callable[[], TurnExecutionReport],
    ) -> TurnExecutionReport:
        try:
            self._bootstrap_hook()
        except (TaskCancelledException, YscbError) as exc:
            return _abort_cold_turn_scope(turn_scope, exc.detail.with_fallback_task("core.watcher"))
        except KeyboardInterrupt:
            det_k = ErrorDetail(ErrorCode.TASK_CANCELLED, "Interrupted during cold bootstrap.", source_task="core.watcher")
            return _abort_cold_turn_scope(turn_scope, det_k)
        except (Exception, SystemExit, GeneratorExit) as exc:
            det_e = ErrorDetail(ErrorCode.BUSINESS_FAILURE, safe_exception_summary(exc), source_task="core.watcher")
            return _abort_cold_turn_scope(turn_scope, det_e)
        except BaseException:
            _ = turn_scope.close_scoped_stack_recorded()
            raise
        return fn()

    def _invoke_bootstrap_safely(self) -> Optional[ErrorDetail]:
        try:
            self._bootstrap_hook()
            return None
        except (TaskCancelledException, YscbError) as exc:
            return exc.detail
        except (Exception, SystemExit, GeneratorExit) as exc:
            return ErrorDetail(ErrorCode.BUSINESS_FAILURE, safe_exception_summary(exc))

    def refresh_cold_routes(
        self,
        token: CancellationToken,
        call_tree_id: str,
        *,
        deadline: Optional[float] = None,
    ) -> Optional[ErrorDetail]:
        lock_key = self._lock_scope_key(call_tree_id)
        with self.reentry_lock:
            in_mem_held = bool(call_tree_id) and (lock_key in self.leases)
        if in_mem_held:
            return self._invoke_bootstrap_safely()
        try:
            paths = CrossProcessLockPaths.for_stem(resolve_contained_subpath(self._cache_dir, "locks"), "installer")
            pin_lk = (
                acquire_verified_cross_proc_pin(
                    paths.owner_path,
                    paths.pin_path,
                    lambda ow: _is_same_tree_installer_owner(ow, call_tree_id),
                    timeout_sec=_rem_lock_sec(deadline, 10.0, paths.pin_path),
                    cancel_token=token,
                )
                if call_tree_id
                else None
            )
        except (TaskCancelledException, YscbError) as exc:
            return exc.detail
        if pin_lk is not None:
            try:
                return self._invoke_bootstrap_safely()
            finally:
                pin_lk.release()
        lock = paths.lock_file
        try:
            tmo = _rem_lock_sec(deadline, 10.0, lock.lock_path)
            lock.acquire(shared=True, blocking=True, timeout_sec=tmo, cancel_token=token)
        except (TaskCancelledException, YscbError) as exc:
            return exc.detail
        try:
            return self._invoke_bootstrap_safely()
        finally:
            lock.release()

    def _claim_cand_lease_reentry(
        self,
        lock_key: tuple[str, str],
        cand: _ColdLockLease,
        need_excl: bool,
        task_id: TaskId,
        tid: str,
    ) -> tuple[Optional[_ColdLockLease], Optional[TurnExecutionReport]]:
        with cand.op_lock:
            with self.reentry_lock:
                if self.leases.get(lock_key) is not cand:
                    return (None, None)
                if need_excl and not cand.is_exclusive:
                    err = ErrorDetail(
                        code=ErrorCode.ILLEGAL_LOCK_REENTRANCY,
                        message=f"Cannot upgrade shared installer.lock to exclusive in '{task_id}'.",
                        source_task=str(task_id),
                    )
                    rep = TurnExecutionReport(
                        turn_id=tid,
                        primary_result=StepExecutionResult(ok=False, error=err, fatal_abort_turn=True),
                    )
                    return (None, rep)
                cand.excl_refs += 1 if need_excl else 0
                cand.shared_refs += 0 if need_excl else 1
                return (cand, None)

    def _try_reenter_existing_lease(
        self,
        lock_key: tuple[str, str],
        need_excl: bool,
        in_cold_shared_ws: bool,
        task_id: TaskId,
        tid: str,
    ) -> tuple[Optional[_ColdLockLease], Optional[TurnExecutionReport]]:
        with self.reentry_lock:
            cand = self.leases.get(lock_key)
        if cand is not None:
            got_pair = self._claim_cand_lease_reentry(lock_key, cand, need_excl, task_id, tid)
            if got_pair[0] is not None or got_pair[1] is not None:
                return got_pair
        if in_cold_shared_ws and need_excl:
            err = ErrorDetail(
                code=ErrorCode.ILLEGAL_LOCK_REENTRANCY,
                message=f"Cannot upgrade shared installer.lock to exclusive in '{task_id}'.",
                source_task=str(task_id),
            )
            return (
                None,
                TurnExecutionReport(
                    turn_id=tid,
                    primary_result=StepExecutionResult(ok=False, error=err, fatal_abort_turn=True),
                ),
            )
        return (None, None)

    def run_cold_turn(
        self,
        tagged_req: InvokeRequest,
        spec: TaskRouteSpec,
        turn_scope: TurnScope,
        *,
        deadline: Optional[float] = None,
    ) -> TurnExecutionReport:
        tid = turn_scope.turn_id
        prop = tagged_req.propagation
        eff_ctree = prop.call_tree_id or tid
        need_excl = spec.mutation_scope != SelfMutationScope.NONE
        next_req = (
            replace(
                tagged_req,
                propagation=replace(
                    prop,
                    cold_shared_workspaces=prop.cold_shared_workspaces | frozenset({self._workspace_root}),
                ),
            )
            if not need_excl
            else tagged_req
        )
        lock_key = self._lock_scope_key(eff_ctree)
        reentered, err_rep = self._try_reenter_existing_lease(
            lock_key, need_excl, self._workspace_root in prop.cold_shared_workspaces, tagged_req.task_id, tid
        )
        if err_rep is not None:
            td_errs = turn_scope.close_scoped_stack_recorded()
            return replace(err_rep, teardown_diagnostics=(*err_rep.teardown_diagnostics, *td_errs))
        if reentered is not None:
            try:
                return self._cold_runner.execute_leased_turn(
                    next_req, scope=turn_scope, fallback_task=str(next_req.task_id)
                )
            finally:
                self._release_lease_slot(lock_key, reentered, was_excl=need_excl)
        return self._acquire_and_run_cold(next_req, eff_ctree, lock_key, need_excl, turn_scope, deadline)

    def _acquire_os_or_pinned_cold(
        self,
        next_req: InvokeRequest,
        eff_ctree: str,
        lock_key: tuple[str, str],
        need_excl: bool,
        turn_scope: TurnScope,
        deadline: Optional[float],
    ) -> tuple[Optional[FileLock], Optional[TurnExecutionReport]]:
        host_token = turn_scope.cancel_token
        try:
            paths = CrossProcessLockPaths.for_stem(resolve_contained_subpath(self._cache_dir, "locks"), "installer")
            lock = paths.lock_file
            if lock.acquire(shared=not need_excl, blocking=False):
                return (lock, None)
            pin_lk = acquire_verified_cross_proc_pin(
                paths.owner_path,
                paths.pin_path,
                lambda ow: _is_same_tree_installer_owner(ow, eff_ctree),
                timeout_sec=_rem_lock_sec(deadline, 10.0, paths.pin_path),
                cancel_token=host_token,
            )
        except (TaskCancelledException, YscbError) as exc:
            return (None, _abort_cold_turn_scope(turn_scope, exc.detail.with_fallback_task(str(next_req.task_id))))
        if pin_lk is not None:
            return (None, self._run_pinned_cross_proc_cold(next_req, lock_key, pin_lk, turn_scope))
        try:
            tmo = _rem_lock_sec(deadline, 30.0, lock.lock_path)
            lock.acquire(shared=not need_excl, blocking=True, timeout_sec=tmo, cancel_token=host_token)
            return (lock, None)
        except (TaskCancelledException, YscbError) as exc:
            return (None, _abort_cold_turn_scope(turn_scope, exc.detail.with_fallback_task(str(next_req.task_id))))

    def _acquire_and_run_cold(
        self,
        next_req: InvokeRequest,
        eff_ctree: str,
        lock_key: tuple[str, str],
        need_excl: bool,
        turn_scope: TurnScope,
        deadline: Optional[float],
    ) -> TurnExecutionReport:
        try:
            lock, early_rep = self._acquire_os_or_pinned_cold(
                next_req, eff_ctree, lock_key, need_excl, turn_scope, deadline
            )
        except BaseException:
            turn_scope.close_scoped_stack_recorded()
            raise
        if early_rep is not None or lock is None:
            return require_non_none(early_rep)
        cand_lease = _ColdLockLease(
            lock=lock,
            shared_refs=0 if need_excl else 1,
            excl_refs=1 if need_excl else 0,
            os_exclusive=need_excl,
            has_owner_file=False,
        )
        try:
            lease, joined_existing = self._install_or_join_cold_lease(
                lock_key, cand_lease, eff_ctree, as_excl=need_excl
            )
        except YscbError as exc:
            lock.release()
            return _abort_cold_turn_scope(
                turn_scope, exc.detail.with_fallback_task(str(next_req.task_id)), fatal_abort=True
            )
        except BaseException:
            lock.release()
            turn_scope.close_scoped_stack_recorded()
            raise
        if joined_existing:
            lock.release()
        try:
            return self._cold_runner.execute_leased_turn(next_req, scope=turn_scope, fallback_task=str(next_req.task_id))
        finally:
            self._release_lease_slot(lock_key, lease, was_excl=need_excl)

    def _try_commit_cold_lease_under_cur(
        self,
        lock_key: tuple[str, str],
        cur: _ColdLockLease,
        as_excl: bool,
    ) -> Optional[tuple[_ColdLockLease, bool]]:
        with cur.op_lock:
            with self.reentry_lock:
                if self.leases.get(lock_key) is not cur:
                    return None
                if not as_excl:
                    cur.shared_refs += 1
                    return (cur, True)
                if cur.is_exclusive:
                    cur.excl_refs += 1
                    return (cur, True)
                raise YscbError(
                    ErrorCode.ILLEGAL_LOCK_REENTRANCY,
                    "Cannot upgrade shared cold installer.lock lease without explicit upgrade path.",
                )

    def _write_cold_owner_or_evict(
        self,
        lock_key: tuple[str, str],
        new_lease: _ColdLockLease,
        eff_ctree: str,
    ) -> None:
        owner_p = CrossProcessLockPaths.for_stem(resolve_contained_subpath(self._cache_dir, "locks"), "installer").owner_path
        try:
            write_cross_proc_owner_json(owner_p, {"pid": os.getpid(), "call_tree_id": eff_ctree})
            new_lease.has_owner_file = True
        except BaseException:
            silent_unlink(owner_p)
            self._evict_broken_lease(lock_key, new_lease)
            raise

    def _install_fresh_cold_lease_locked(
        self,
        lock_key: tuple[str, str],
        new_lease: _ColdLockLease,
        eff_ctree: str,
        as_excl: bool,
    ) -> bool:
        with new_lease.op_lock:
            with self.reentry_lock:
                if self.leases.get(lock_key) is not None:
                    return False
                self.leases[lock_key] = new_lease
            if as_excl and not new_lease.cross_proc_excl:
                self._write_cold_owner_or_evict(lock_key, new_lease, eff_ctree)
            return True

    def _install_or_join_cold_lease(
        self,
        lock_key: tuple[str, str],
        new_lease: _ColdLockLease,
        eff_ctree: str,
        *,
        as_excl: bool,
    ) -> tuple[_ColdLockLease, bool]:
        while True:
            if self._install_fresh_cold_lease_locked(lock_key, new_lease, eff_ctree, as_excl):
                return (new_lease, False)
            with self.reentry_lock:
                cur = self.leases.get(lock_key)
            if cur is not None:
                res = self._try_commit_cold_lease_under_cur(lock_key, cur, as_excl)
                if res is not None:
                    return res

    def _run_pinned_cross_proc_cold(
        self,
        next_req: InvokeRequest,
        lock_key: tuple[str, str],
        pin_lk: FileLock,
        turn_scope: TurnScope,
    ) -> TurnExecutionReport:
        cand_lease = _ColdLockLease(lock=None, pin_lock=pin_lk, excl_refs=1, cross_proc_excl=True)
        try:
            lease, joined_existing = self._install_or_join_cold_lease(lock_key, cand_lease, "", as_excl=True)
        except YscbError as exc:
            pin_lk.release()
            return _abort_cold_turn_scope(
                turn_scope, exc.detail.with_fallback_task(str(next_req.task_id)), fatal_abort=True
            )
        except BaseException:
            pin_lk.release()
            turn_scope.close_scoped_stack_recorded()
            raise
        if joined_existing:
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
        self,
        lock_key: tuple[str, str],
        lease: _ColdLockLease,
        eff_ctree: str,
        task_id: TaskId,
        cancel_token: CancellationToken,
        deadline: Optional[float],
    ) -> Optional[StepExecutionResult[JsonValue]]:
        lk_ref = require_non_none(lease.lock)
        try:
            paths = CrossProcessLockPaths.for_stem(resolve_contained_subpath(self._cache_dir, "locks"), "installer")
            tmo = _rem_lock_sec(deadline, 10.0, lk_ref.lock_path)
            lk_ref.upgrade_to_exclusive(timeout_sec=tmo, cancel_token=cancel_token)
            lease.os_exclusive = True
        except (TaskCancelledException, YscbError) as exc:
            if not lk_ref.is_acquired:
                self._evict_broken_lease(lock_key, lease)
            det = exc.detail.with_fallback_task(str(task_id))
            is_fatal = det.code == ErrorCode.ILLEGAL_LOCK_REENTRANCY or not lk_ref.is_acquired
            return StepExecutionResult(ok=False, error=det, fatal_abort_turn=is_fatal)
        try:
            write_cross_proc_owner_json(paths.owner_path, {"pid": os.getpid(), "call_tree_id": eff_ctree})
        except YscbError as exc:
            self._rollback_failed_lease_upgrade(lock_key, lease, paths.owner_path, try_downgrade=True)
            det_w = exc.detail.with_fallback_task(str(task_id))
            return StepExecutionResult(ok=False, error=det_w, fatal_abort_turn=not lk_ref.is_acquired)
        except Exception:
            self._rollback_failed_lease_upgrade(lock_key, lease, paths.owner_path, try_downgrade=True)
            raise
        except BaseException:
            self._rollback_failed_lease_upgrade(lock_key, lease, paths.owner_path, try_downgrade=False)
            raise
        lease.has_owner_file = True
        return None

    def _rollback_failed_lease_upgrade(
        self,
        lock_key: tuple[str, str],
        lease: _ColdLockLease,
        owner_path: HostPath,
        *,
        try_downgrade: bool,
    ) -> None:
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
        self,
        lock_key: tuple[str, str],
        lease: _ColdLockLease,
        eff_ctree: str,
        task_id: TaskId,
        cancel_token: CancellationToken,
        deadline: Optional[float],
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

    def _claim_direct_excl_lease(
        self,
        lock_key: tuple[str, str],
        lease: Optional[_ColdLockLease],
    ) -> Optional[_ColdLockLease]:
        if lease is None or not (lease.cross_proc_excl or lease.lock is None):
            return None
        with lease.op_lock:
            with self.reentry_lock:
                if self.leases.get(lock_key) is not lease:
                    return None
                lease.excl_refs += 1
                return lease

    def run_upgraded_nested(
        self,
        eff_ctree: str,
        task_id: TaskId,
        cancel_token: CancellationToken,
        step_fn: Callable[[], StepExecutionResult[JsonValue]],
        *,
        deadline: Optional[float] = None,
    ) -> StepExecutionResult[JsonValue]:
        lock_key = self._lock_scope_key(eff_ctree)
        with self.reentry_lock:
            lease = self.leases.get(lock_key)
        direct_lease = self._claim_direct_excl_lease(lock_key, lease)
        if direct_lease is not None:
            try:
                return step_fn()
            finally:
                self._release_lease_slot(lock_key, direct_lease, was_excl=True)
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
            paths = CrossProcessLockPaths.for_stem(resolve_contained_subpath(self._cache_dir, "locks"), "installer")
            pin_lk = acquire_verified_cross_proc_pin(
                paths.owner_path,
                paths.pin_path,
                lambda ow: _is_same_tree_installer_owner(ow, eff_ctree),
                timeout_sec=_rem_lock_sec(deadline, 10.0, paths.pin_path),
                cancel_token=cancel_token,
            )
        except (TaskCancelledException, YscbError) as exc:
            return StepExecutionResult(ok=False, error=exc.detail.with_fallback_task(str(task_id)))
        if pin_lk is not None:
            try:
                return step_fn()
            finally:
                pin_lk.release()
        err = ErrorDetail(
            code=ErrorCode.ILLEGAL_LOCK_REENTRANCY,
            message=f"Cannot upgrade shared installer.lock across processes in '{task_id}'.",
            source_task=str(task_id),
        )
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
