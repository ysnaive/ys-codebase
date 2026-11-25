"""Single-point RuntimeDispatcher implementing the 5-stage invocation pipeline across Cold/Hot and Tier 0/1."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math
import os
import threading
import time
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Sequence, TypeVar, overload
import uuid
import weakref

from core.execution.event import CausalLineage, EventBatchEnvelope, EventOrdering, RawEventRecord
from core.execution.lifecycle import (
    ContainerState, StepExecutionResult, TaskStepExecutor, TurnEngine, TurnExecutionReport,
    TurnKind, TurnScope, WorkerContainerLifecycle,
)
from core.execution.rpc import DaemonConnectionConfig, PersistentRpcSession, call_ephemeral_daemon_rpc
from core.execution.runtime.contracts import (
    CONFIG_CHANGED_EVENT_ID, CORE_MODULE_ID, MODULES_DIRNAME, WATCHER_TASK_ID,
    CallPropagationContext, CallerSurface, ClientRoutingPolicy, ConcurrencyMode, ConfigViewPort, CoordinatorPort,
    DaemonSpawner, DispatchMode, EnvLeaseAcquireFn, EnvTouchUsedFn, ExecutionPriority, InvokeRequest, ModuleDescriptor,
    ModuleProviderPort, ModuleRuntimeServices, SelfMutationScope, TaskMetadata, TaskOutcome, TaskRouteSpec,
    Tier1WorkerPool, YscbModule, decode_outcome_as, sanitize_caller_env,
)
from core.execution.runtime.coordinator import (
    CoordinatedExecution, PriorityHandle, ResourceAcquireSpec, ResourceCoordinator, SharedCancelGroup, StepFlight,
)
from core.execution.runtime.gates import (
    ColdInstallerLockManager, ConfigFingerprintTracker, LifecycleReloadGate, QuiesceResumeResult,
    SharedWorkspaceState, expand_colocated_tier1_siblings, normalize_drain_deadline, validate_stage1_gates,
)
from core.execution.runtime.module_slot import LocalModuleSlotRegistry, StepContextCallbacks
from core.execution.runtime.route_index import RouteIndexRegistry
from core.execution.runtime.services import (
    InvocationCorrelationContext,
    active_invocation_correlation_scope,
    resolve_active_correlation,
    resolve_active_profiler,
)
from core.execution.runtime.step_host import (
    EquivCallContext, RawInvokeResult, StepExecutionEnv, StepHostRunner, WorkerCallbackBridge,
    cancelled_task_outcome, default_nested_routing_policy, report_to_outcome, safe_invoke_progress,
    translate_remote_daemon_outcome,
)
from core.execution.runtime.turn_session import ActiveStepBinding, ActiveTurnSession, TurnSessionRegistry, merge_deadlines
from core.execution.runtime.wire import (
    DaemonRpcInvokeEnvelope, DaemonRpcInvokeReply, WorkerCallbackEnvelope, WorkerCallbackKind,
    WorkerCallbackReply, WorkerWarmupReply,
)
from core.execution.runtime.worker_pool import HotWorkerPool, PoolHostCallbacks, RetiringGroupBusyError, tier1_group_key_for
from core.foundation.codec import DataclassCodec
from core.foundation.errors import (
    ErrorCode, ErrorDetail, TaskCancelledException, YscbError, is_fatal_error_code, safe_exception_summary,
)
from core.foundation.observability import MAX_TIMEOUT_MS, CancellationToken, DeadlineGuard, LogLevel, ms_to_safe_sec
from core.foundation.primitives import (
    MAX_USER_JSON_DEPTH, EventId, HostPath, JsonObject, JsonValue, ModuleId, MutableJsonObject, TaskId,
    require_non_none, require_pure_int, require_pure_str, safe_real_to_float, validate_wire_json_object,
)
from core.foundation.profiler import (
    DailyEventRecord,
    ExecutionTraceRecord,
    FlightLogConfig,
    FlightLogRouter,
    MemoryTrackingGuard,
    Profiler,
    ProfilerRingBuffer,
    ProfilerSession,
    read_process_rss_kb,
    redact_sensitive_value,
)
from core.metadata.contributes import (
    BoundLocaleDialect,
    is_managed_child_dispatcher,
    lookup_owner_locale_dialect,
    register_sdk_core_dispatcher_binder,
    resolve_sdk_core_post_call_hook,
)

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


def _now_utc_and_epoch_ms() -> tuple[str, int]:
    now_dt = datetime.now(timezone.utc)
    return (now_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), int(now_dt.timestamp() * 1000))


def _read_observability_config_map(config_view: Optional[ConfigViewPort]) -> Optional[Mapping[str, JsonValue]]:
    if config_view is None:
        return None
    try:
        raw = config_view.get_module_value(CORE_MODULE_ID, "observability", None)
    except (Exception, SystemExit, GeneratorExit):
        return None
    return raw if isinstance(raw, Mapping) else None


def _resolve_slow_threshold_ms(config_view: Optional[ConfigViewPort]) -> float:
    obs_map = _read_observability_config_map(config_view)
    if obs_map is not None and "slow_threshold_ms" in obs_map:
        try:
            val = safe_real_to_float(obs_map["slow_threshold_ms"], label="slow_threshold_ms")
            if math.isfinite(val) and val >= 0.0:
                return val
        except ValueError:
            pass
    return FlightLogConfig().slow_threshold_ms


def _build_worker_flight_log_config(
    config_view: Optional[ConfigViewPort],
    router: Optional[FlightLogRouter],
) -> Optional[JsonObject]:
    obs_map = _read_observability_config_map(config_view)
    if obs_map is None and router is None:
        return None
    base_cfg = FlightLogConfig()
    if obs_map is not None:
        try:
            base_cfg = DataclassCodec.decode(FlightLogConfig, obs_map)
        except (ValueError, TypeError, KeyError, YscbError):
            base_cfg = FlightLogConfig()
    if router is not None:
        base_cfg = (
            replace(base_cfg, enabled=True, respect_sandbox=False)
            if router.enabled
            else replace(base_cfg, enabled=False)
        )
    return DataclassCodec.encode_object(base_cfg)


def _redacted_error_detail_dict(err: Optional[ErrorDetail]) -> Optional[JsonObject]:
    if err is None:
        return None
    raw = DataclassCodec.encode_object(err)
    redacted = redact_sensitive_value(raw)
    return redacted if isinstance(redacted, Mapping) else None


def _collect_dispatched_task_names(primary: TaskId, invoked: Sequence[tuple[HostPath, TaskId]]) -> tuple[str, ...]:
    seen: list[str] = []
    for _ws, tid in invoked:
        s_tid = str(tid)
        if s_tid not in seen:
            seen.append(s_tid)
    p_str = str(primary)
    if not seen:
        seen.append(p_str)
    elif p_str not in seen:
        seen.insert(0, p_str)
    return tuple(seen)


def _resolve_authoritative_child_lineage(base_lin: CausalLineage, candidate: CausalLineage) -> CausalLineage:
    base_hops = base_lin.scoped_hops()
    cand_hops = candidate.scoped_hops()
    if len(cand_hops) >= len(base_hops) and cand_hops[: len(base_hops)] == base_hops:
        return candidate
    return base_lin


def _validate_in_memory_modules(raw: object) -> tuple[YscbModule, ...]:
    if isinstance(raw, (str, bytes, bytearray, memoryview)) or not isinstance(raw, Sequence):
        raise ValueError("DispatcherHostOptions.in_memory_modules must be a Sequence of YscbModule.")
    mods = tuple(raw)
    seen: set[ModuleId] = set()
    for mod in mods:
        if not isinstance(mod, YscbModule):
            raise ValueError(f"DispatcherHostOptions.in_memory_modules elements must be YscbModule, got {mod!r}")
        if mod.module_id in seen:
            raise ValueError(f"Duplicate in_memory_modules entry for '{mod.module_id}'.")
        seen.add(mod.module_id)
    return mods


def _failed_step_result(
    err: ErrorDetail,
    task_id: TaskId,
    *,
    coalesced: bool = False,
    fatal: Optional[bool] = None,
) -> StepExecutionResult[JsonValue]:
    det = err.with_fallback_task(str(task_id))
    return StepExecutionResult(
        ok=False,
        error=det,
        preempted=(det.code == ErrorCode.TASK_PREEMPTED),
        fatal_abort_turn=(fatal if fatal is not None else is_fatal_error_code(det.code)),
        coalesced=coalesced,
    )


@dataclass(frozen=True, slots=True)
class DispatcherHostOptions:
    """Runtime host configuration keeping RuntimeDispatcher construction concise."""

    config_view: Optional[ConfigViewPort] = None
    daemon_spawner: Optional[DaemonSpawner] = None
    connection_config: DaemonConnectionConfig = DaemonConnectionConfig()
    is_daemon_host: bool = False
    persistent_rpc_session: Optional[PersistentRpcSession] = None
    child_dispatcher_factory: Optional[Callable[[HostPath], RuntimeDispatcher]] = None
    peer_cache_dir_resolver: Optional[Callable[[HostPath], HostPath]] = None
    owns_child_dispatchers: bool = True
    in_memory_modules: tuple[YscbModule, ...] = ()
    module_services_factory: Optional[Callable[[ModuleId], ModuleRuntimeServices]] = None
    worker_host_dir: Optional[HostPath] = None
    env_lease_acquire: Optional[EnvLeaseAcquireFn] = None
    env_touch_used: Optional[EnvTouchUsedFn] = None
    flight_log_router: Optional[FlightLogRouter] = None
    daemon_boot_id: str = ""
    profiler_ring_buffer: Optional[ProfilerRingBuffer] = None

    def __post_init__(self) -> None:
        if self.config_view is not None:
            try:
                m1, m2, m3 = self.config_view.get_module_value, self.config_view.fingerprint, self.config_view.reload
            except AttributeError as exc:
                raise ValueError(f"Invalid ConfigViewPort: {self.config_view!r}") from exc
            if not (callable(m1) and callable(m2) and callable(m3)):
                raise ValueError(f"Invalid ConfigViewPort methods on {self.config_view!r}")
        if self.daemon_spawner is not None:
            try:
                c1, c2 = self.daemon_spawner.can_spawn_in_environment, self.daemon_spawner.try_spawn_background
            except AttributeError as exc:
                raise ValueError(f"Invalid DaemonSpawner: {self.daemon_spawner!r}") from exc
            if not (callable(c1) and callable(c2)):
                raise ValueError(f"Invalid DaemonSpawner methods on {self.daemon_spawner!r}")
        if not isinstance(self.connection_config, DaemonConnectionConfig):
            raise ValueError("DispatcherHostOptions.connection_config must be DaemonConnectionConfig.")
        if not isinstance(self.is_daemon_host, bool) or not isinstance(self.owns_child_dispatchers, bool):
            raise ValueError("DispatcherHostOptions boolean flags must be bool.")
        if self.persistent_rpc_session is not None and not isinstance(self.persistent_rpc_session, PersistentRpcSession):
            raise ValueError("DispatcherHostOptions.persistent_rpc_session must be PersistentRpcSession or None.")
        if self.child_dispatcher_factory is not None and not callable(self.child_dispatcher_factory):
            raise ValueError("DispatcherHostOptions.child_dispatcher_factory must be callable or None.")
        if self.peer_cache_dir_resolver is not None and not callable(self.peer_cache_dir_resolver):
            raise ValueError("DispatcherHostOptions.peer_cache_dir_resolver must be callable or None.")
        if self.module_services_factory is not None and not callable(self.module_services_factory):
            raise ValueError("DispatcherHostOptions.module_services_factory must be callable or None.")
        if self.worker_host_dir is not None and not isinstance(self.worker_host_dir, HostPath):
            raise ValueError("DispatcherHostOptions.worker_host_dir must be HostPath or None.")
        if self.env_lease_acquire is not None and not callable(self.env_lease_acquire):
            raise ValueError("DispatcherHostOptions.env_lease_acquire must be callable or None.")
        if self.env_touch_used is not None and not callable(self.env_touch_used):
            raise ValueError("DispatcherHostOptions.env_touch_used must be callable or None.")
        if self.flight_log_router is not None and not isinstance(self.flight_log_router, FlightLogRouter):
            raise ValueError("DispatcherHostOptions.flight_log_router must be FlightLogRouter or None.")
        require_pure_str(self.daemon_boot_id, "DispatcherHostOptions.daemon_boot_id")
        if self.profiler_ring_buffer is not None and not isinstance(self.profiler_ring_buffer, ProfilerRingBuffer):
            raise ValueError("DispatcherHostOptions.profiler_ring_buffer must be ProfilerRingBuffer or None.")
        object.__setattr__(self, "in_memory_modules", _validate_in_memory_modules(self.in_memory_modules))
@dataclass(slots=True)
class _CoordinatedStepBundle:
    step_result: StepExecutionResult[JsonValue]
    flight: Optional[StepFlight[_CoordinatedStepBundle]] = None
    imm_diagnostics: tuple[ErrorDetail, ...] = ()
    step_td_diags: tuple[ErrorDetail, ...] = ()
    invoked_tasks: tuple[tuple[HostPath, TaskId], ...] = ()
    release_guard: Optional[threading.Event] = None
    retry_group_busy: bool = False


@dataclass(frozen=True, slots=True)
class _NestedInvokeSpec:
    child_task_id: TaskId
    raw_input: JsonObject
    target_workspace: HostPath
    caller_cwd: HostPath
    caller_env: dict[str, str]
    routing_policy: ClientRoutingPolicy
    priority: ExecutionPriority
    approval_scope: frozenset[TaskId]
    allow_conditional: bool
    propagation: CallPropagationContext
    parent_prio: Optional[PriorityHandle]
    step_deadline: Optional[float]


@dataclass(frozen=True, slots=True)
class _ImmediateEventDispatchSpec:
    event_id: EventId
    raw_payload: JsonObject
    propagation: CallPropagationContext
    strict: bool
    emitter_task: Optional[TaskId]
    parent_step_cancel: Optional[CancellationToken]
    parent_prio: Optional[PriorityHandle]
    step_deadline: Optional[float]


class RuntimeDispatcher(TaskStepExecutor[InvokeRequest]):
    """Single-point orchestrator executing the 5-stage pipeline across Cold/Hot and Tier 0/1."""

    def __init__(
        self,
        *,
        workspace_root: HostPath,
        cache_dir: HostPath,
        module_provider: ModuleProviderPort,
        options: DispatcherHostOptions = DispatcherHostOptions(),
    ) -> None:
        self._workspace_root, self._cache_dir = workspace_root, cache_dir
        self._module_provider, self._opts = module_provider, options
        self._flight_log_router: Optional[FlightLogRouter] = options.flight_log_router
        self._daemon_boot_id: str = options.daemon_boot_id.strip() or (
            options.flight_log_router.daemon_boot_id if options.flight_log_router is not None else ""
        )
        self._profiler_ring_buffer: Optional[ProfilerRingBuffer] = options.profiler_ring_buffer
        init_fl_cfg = _build_worker_flight_log_config(options.config_view, self._flight_log_router)
        self._in_mem_map = MappingProxyType({m.module_id: m for m in options.in_memory_modules})
        self._cfg_tracker = ConfigFingerprintTracker(options.config_view)
        self._gates = LifecycleReloadGate(workspace_root)
        self._container = WorkerContainerLifecycle(quiesce_probe=self._gates.has_any_quiesced)
        slot_q_pred = self._gates.is_module_slot_quiesced if options.is_daemon_host else None
        self._tier0_slots = LocalModuleSlotRegistry(
            workspace_root, self._container.resource_stack, container=self._container,
            is_module_quiesced=slot_q_pred, require_eager_start=options.is_daemon_host, in_memory_modules=self._in_mem_map,
            module_services_factory=options.module_services_factory,
        )
        self._routes = RouteIndexRegistry(
            cache_dir=cache_dir, is_daemon_host=options.is_daemon_host, module_provider=module_provider,
            tier0_slots=self._tier0_slots, container=self._container, gates=self._gates, in_memory_modules=self._in_mem_map,
        )
        self._callback_bridge = WorkerCallbackBridge(self._handle_worker_callback)
        self._bind_lock = threading.RLock()
        self._shared_ws = SharedWorkspaceState()
        disp_ref = weakref.ref(self)
        msf_ref = weakref.ref(options.module_services_factory) if options.module_services_factory is not None else None

        def _resolve_cold_dialect_policy() -> Optional[BoundLocaleDialect]:
            owner_disp = disp_ref()
            if owner_disp is not None:
                direct = lookup_owner_locale_dialect(owner_disp)
                if direct is not None:
                    return direct
            if msf_ref is not None:
                msf_obj = msf_ref()
                if msf_obj is not None:
                    return lookup_owner_locale_dialect(msf_obj)
            return None

        self._sessions = TurnSessionRegistry(
            workspace_root=workspace_root, module_provider=module_provider, tier0_slots=self._tier0_slots,
            callback_bridge=self._callback_bridge, in_memory_modules=self._in_mem_map,
            module_services_factory=options.module_services_factory, worker_host_dir=options.worker_host_dir,
            cold_dialect_resolver=_resolve_cold_dialect_policy,
            env_lease_acquire=options.env_lease_acquire, env_touch_used=options.env_touch_used,
            daemon_boot_id=self._daemon_boot_id, flight_log_config=init_fl_cfg,
        )
        self._tier1_pool = HotWorkerPool(
            workspace_root, self._callback_bridge, lifo_stack=self._container.resource_stack,
            host_dir=options.worker_host_dir,
            daemon_boot_id=self._daemon_boot_id,
            flight_log_config=init_fl_cfg,
            host_callbacks=PoolHostCallbacks(
                on_warmup_reply=self._apply_tier1_warmup_reply,
                on_module_crashed=self._container.record_degraded,
                is_module_degraded=lambda m: self._container.get_degraded(m) is not None,
                is_module_quiesced=slot_q_pred,
                is_group_reloading=self._gates.any_descriptor_reloading,
                resolve_group_descriptors=self._routes.resolve_fresh_group_descriptors,
                on_teardown_diagnostics=self._sessions.record_host_teardown_diags,
                env_lease_acquire=options.env_lease_acquire,
                env_touch_used=options.env_touch_used,
            ),
        )
        self._gates.register_gate_listener(self._tier1_pool.notify_gate_changed)
        self._step_host = StepHostRunner(
            is_daemon_host=options.is_daemon_host, tier1_pool=self._tier1_pool, container=self._container,
            gates=self._gates, routes=self._routes, sessions=self._sessions,
        )
        self._coordinator = ResourceCoordinator(
            cache_dir=cache_dir, workspace_root=workspace_root,
            resolve_cache_dir=options.peer_cache_dir_resolver, is_daemon_host=options.is_daemon_host,
        )
        self._turn_engine: TurnEngine[InvokeRequest] = TurnEngine(self)
        self._cold_locks = ColdInstallerLockManager(workspace_root, cache_dir, self._turn_engine, self._cold_bootstrap_hook)
        self._bind_shared_coordinators(self._shared_ws)
        if not options.is_daemon_host:
            core_ym = self._in_mem_map.get(CORE_MODULE_ID)
            if core_ym is not None:
                self_ref = weakref.ref(self)

                def _bind_sdk_inner_dispatcher(peer_disp: object) -> None:
                    owner_disp = self_ref()
                    if owner_disp is not None:
                        owner_disp._bind_peer_dispatcher_shared_state(peer_disp)

                register_sdk_core_dispatcher_binder(core_ym, _bind_sdk_inner_dispatcher)
        self._force_drain = threading.Event()
        self._routes.init_index()

    @property
    def is_daemon_host(self) -> bool:
        return self._opts.is_daemon_host

    def _bind_shared_coordinators(self, shared_ws: SharedWorkspaceState) -> None:
        if self._opts.is_daemon_host and shared_ws is not self._shared_ws:
            return
        ws_key = self._workspace_root.comparison_key
        with self._bind_lock:
            old_ws = self._shared_ws
            if old_ws is shared_ws:
                with shared_ws.guard:
                    if ws_key in shared_ws.coordinators:
                        return
                    self._coordinator = self._cold_locks.bind_shared(shared_ws, self._coordinator)
                return
            first_g, second_g = (
                (old_ws.guard, shared_ws.guard)
                if id(old_ws.guard) < id(shared_ws.guard)
                else (shared_ws.guard, old_ws.guard)
            )
            with first_g, second_g:
                if (
                    self.active_turn_count > 0
                    or self._gates.has_any_active_work()
                    or bool(old_ws.installer_leases)
                ):
                    return
                self._shared_ws = shared_ws
                self._coordinator = self._cold_locks.bind_shared(shared_ws, self._coordinator)

    def _bind_peer_dispatcher_shared_state(self, peer_dispatcher: object) -> None:
        if isinstance(peer_dispatcher, RuntimeDispatcher) and peer_dispatcher is not self:
            peer_dispatcher._bind_shared_coordinators(self._shared_ws)

    @property
    def cache_dir(self) -> HostPath:
        return self._cache_dir

    @property
    def container_lifecycle(self) -> WorkerContainerLifecycle:
        return self._container

    @property
    def tier1_pool(self) -> Tier1WorkerPool:
        return self._tier1_pool

    @property
    def reload_gate(self) -> LifecycleReloadGate:
        return self._gates

    @property
    def coordinator(self) -> CoordinatorPort:
        return self._coordinator

    @property
    def module_provider(self) -> ModuleProviderPort:
        return self._module_provider

    @property
    def active_turn_count(self) -> int:
        return self._sessions.active_turn_count

    @property
    def flight_log_router(self) -> Optional[FlightLogRouter]:
        return self._flight_log_router

    @property
    def profiler_ring_buffer(self) -> Optional[ProfilerRingBuffer]:
        return self._profiler_ring_buffer

    def bind_daemon_observability(
        self,
        *,
        daemon_boot_id: str = "",
        flight_log_router: Optional[FlightLogRouter] = None,
        profiler_ring_buffer: Optional[ProfilerRingBuffer] = None,
    ) -> None:
        """Attach daemon boot_id, flight log router, and profiler ring buffer when constructed externally."""
        require_pure_str(daemon_boot_id, "daemon_boot_id")
        if flight_log_router is not None and not isinstance(flight_log_router, FlightLogRouter):
            raise ValueError("flight_log_router must be FlightLogRouter or None.")
        if profiler_ring_buffer is not None and not isinstance(profiler_ring_buffer, ProfilerRingBuffer):
            raise ValueError("profiler_ring_buffer must be ProfilerRingBuffer or None.")
        with self._bind_lock:
            clean_boot = daemon_boot_id.strip()
            if clean_boot and not self._daemon_boot_id:
                self._daemon_boot_id = clean_boot
            if flight_log_router is not None and self._flight_log_router is None:
                self._flight_log_router = flight_log_router
            if profiler_ring_buffer is not None and self._profiler_ring_buffer is None:
                self._profiler_ring_buffer = profiler_ring_buffer
            fl_cfg = _build_worker_flight_log_config(self._opts.config_view, self._flight_log_router)
            self._tier1_pool.update_observability(daemon_boot_id=self._daemon_boot_id, flight_log_config=fl_cfg)
            self._sessions.update_observability(daemon_boot_id=self._daemon_boot_id, flight_log_config=fl_cfg)

    def drain_teardown_diagnostics(self) -> tuple[ErrorDetail, ...]:
        return self._sessions.drain_teardown_diagnostics()

    def list_route_specs(self) -> tuple[TaskRouteSpec, ...]:
        return self._routes.list_route_specs()

    def subscribed_modules(self, event_id: EventId) -> frozenset[ModuleId]:
        return self._routes.subscribed_modules_for_event(event_id)
    def _all_known_descriptors(self) -> list[ModuleDescriptor]:
        descs = list(self._module_provider.list_modules())
        seen = {d.module_id for d in descs}
        for mid, mod_inst in self._in_mem_map.items():
            if mid not in seen:
                descs.append(
                    ModuleDescriptor(
                        module_id=mid,
                        module_dir=self._workspace_root.join(MODULES_DIRNAME, mid.value),
                        declared_tasks=tuple(bt.route_spec for bt in mod_inst.tasks()),
                    )
                )
        return descs

    def warmup_daemon_container(self, only_modules: Optional[frozenset[ModuleId]] = None) -> None:
        """Warm up modules declaring eager_warmup=True across Tier 0 and Tier 1 before marking READY."""
        if self._gates.is_globally_quiesced():
            return
        prev_base = self._container.base_state
        was_boot = prev_base in (ContainerState.UNINITIALIZED, ContainerState.BOOTING, ContainerState.WARMING)
        if was_boot:
            self._container.transition_boot_phase(ContainerState.WARMING)
        try:
            descs = self._all_known_descriptors()
            self._tier0_slots.register_descriptors([d for d in descs if d.venv_python is None])
            self._container.warmup(dict(self._tier0_slots.warmup_modules(only_modules)))
            if was_boot and only_modules is None:
                self._container.transition_boot_phase(ContainerState.WARMING)
            t1_groups: dict[str, list[ModuleDescriptor]] = {}
            for d in descs:
                if d.venv_python is not None:
                    t1_groups.setdefault(tier1_group_key_for(d), []).append(d)
            for g_descs in t1_groups.values():
                if only_modules is None or any(d.module_id in only_modules for d in g_descs):
                    self._tier1_pool.warmup_group(g_descs, only_modules)
            if was_boot and only_modules is None:
                self._container.transition_boot_phase(ContainerState.READY)
        except BaseException:
            if (
                was_boot and only_modules is None and self._container.base_state == ContainerState.WARMING
                and prev_base in (ContainerState.UNINITIALIZED, ContainerState.BOOTING)
            ):
                self._container.transition_boot_phase(prev_base)
            raise

    def _apply_tier1_warmup_reply(self, eager_mods: Sequence[ModuleId], reply: WorkerWarmupReply) -> None:
        for mid in eager_mods:
            err = reply.degraded.get(str(mid))
            if err is not None:
                self._container.record_degraded(mid, err)
            else:
                self._container.clear_degraded(frozenset({mid}))

    @overload
    def invoke(
        self, request: InvokeRequest, *, output_type: type[TOut], cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def invoke(
        self, request: InvokeRequest, *, output_type: None = None, cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[JsonValue]: ...

    def invoke(
        self, request: InvokeRequest, *, output_type: Optional[type[TOut]] = None,
        cancel_token: Optional[CancellationToken] = None, on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]:
        raw_res = self._invoke_raw(request, cancel_token=cancel_token, on_progress=on_progress)
        return decode_outcome_as(raw_res.outcome, output_type, source_task=str(request.task_id)) if output_type is not None else raw_res.outcome

    def invoke_daemon_rpc(
        self, payload: JsonObject, cancel_token: CancellationToken, on_progress: Callable[[JsonObject], None],
        *, pre_turn_id: str = "",
    ) -> DaemonRpcInvokeReply:
        """Decode, execute, and encode a hot DaemonRpcInvokeEnvelope preserving transitive call lineage."""
        try:
            rpc_env = DataclassCodec.decode_envelope(DaemonRpcInvokeEnvelope, payload)
            if rpc_env.workspace_root != self._workspace_root:
                return DaemonRpcInvokeReply(
                    ok=False, error=ErrorDetail(ErrorCode.SECURITY_GATED, f"Cross-workspace top-level RPC rejected: expected {self._workspace_root}, got {rpc_env.workspace_root}", source_task=str(rpc_env.task_id)),
                )
            prop = rpc_env.propagation
            rpc_prof = ProfilerSession(root_name=f"Daemon/{rpc_env.task_id.value}", track_memory=prop.profile_mem)
            req = InvokeRequest(
                task_id=rpc_env.task_id, raw_input=rpc_env.raw_input, workspace_root=rpc_env.workspace_root,
                caller_cwd=rpc_env.caller_cwd, caller_env=rpc_env.caller_env, caller_surface=rpc_env.caller_surface,
                priority=rpc_env.priority, approval_scope=frozenset() if prop.in_event_chain else rpc_env.approval_scope,
                allow_conditional=rpc_env.allow_conditional,
                propagation=replace(
                    prop, turn_id=pre_turn_id or prop.turn_id or None,
                    call_tree_id=prop.call_tree_id or (prop.turn_id if (prop.is_nested_call or bool(prop.call_stack)) else (pre_turn_id or None)),
                    is_internal_trigger=False, from_hot_container=True, hot_workspaces=prop.hot_workspaces | frozenset({self._workspace_root}),
                ),
                profile_mem=prop.profile_mem,
                external_flight_owner=bool(rpc_env.client_owns_flight_logs or rpc_env.caller_surface == CallerSurface.CLI),
                active_profiler=rpc_prof,
            )
            _ = DeadlineGuard.from_timeout_ms(rpc_env.timeout_ms, cancel_token)
        except (YscbError, KeyError, ValueError, TypeError) as exc:
            err_d = exc.detail if isinstance(exc, YscbError) else ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, f"Malformed RPC InvokeRequest: {safe_exception_summary(exc)}")
            return DaemonRpcInvokeReply(ok=False, error=err_d)
        raw_res = self._invoke_raw(
            req,
            cancel_token=cancel_token,
            on_progress=on_progress,
            initial_timeout_ms=rpc_env.timeout_ms,
        )
        out = raw_res.outcome
        return DaemonRpcInvokeReply(
            ok=out.ok, raw_value=out.value, error=out.error, event_diagnostics=out.event_diagnostics,
            teardown_diagnostics=out.teardown_diagnostics, invoked_tasks=raw_res.invoked_tasks, coalesced=out.coalesced,
            profiler_tree=DataclassCodec.encode_object(rpc_prof.snapshot()),
        )

    def invoke_typed(
        self, task_meta: TaskMetadata[TIn, TOut], req: TIn, *, caller_cwd: Optional[HostPath] = None,
        routing_policy: ClientRoutingPolicy = ClientRoutingPolicy.AUTO_SPAWN,
        approval_scope: frozenset[TaskId] = frozenset(), cancel_token: Optional[CancellationToken] = None,
    ) -> TaskOutcome[TOut]:
        """Strongly typed SDK entry checking both TIn and TOut at compile time and runtime."""
        if not isinstance(task_meta, TaskMetadata):
            return TaskOutcome(ok=False, error=ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected TaskMetadata, got {task_meta!r}"))
        try:
            encoded_req = DataclassCodec.encode_object(req, expected_type=task_meta.input_type)
        except YscbError as exc:
            return TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(task_meta.task_id)))
        envelope = InvokeRequest(
            task_id=task_meta.task_id, raw_input=encoded_req, workspace_root=self._workspace_root,
            caller_cwd=caller_cwd or self._workspace_root, routing_policy=routing_policy, approval_scope=approval_scope,
        )
        return self.invoke(envelope, output_type=task_meta.output_type, cancel_token=cancel_token)
    def _build_runtime_snapshot(self) -> MutableJsonObject:
        fg_cnt, bg_cnt = self._sessions.active_turn_breakdown()
        return {
            "is_daemon_host": self._opts.is_daemon_host,
            "container_state": self._container.state.value,
            "active_turns": self.active_turn_count,
            "active_foreground_turns": fg_cnt,
            "active_background_turns": bg_cnt,
            "quiesced": self._gates.is_globally_quiesced(),
            "quiesce_epoch": self._gates.quiesce_epoch,
            "active_tier1_workers": len(self._tier1_pool.active_worker_snapshots()),
            "degraded_module_count": len(self._container.degraded_modules),
        }

    def _record_flight_completion(
        self,
        *,
        request: InvokeRequest,
        eff_tree_id: str,
        exec_mode: str,
        eff_profile_mem: bool,
        active_prof: Profiler,
        rss_before: int,
        t0_ns: int,
        raw_res: Optional[RawInvokeResult],
        raised_exc: Optional[BaseException],
        write_disk: bool,
        record_ring: bool,
    ) -> None:
        duration_ms = round(max(0.0, (time.perf_counter_ns() - t0_ns) / 1_000_000.0), 4)
        rss_after = read_process_rss_kb()
        out_ts, out_ms = _now_utc_and_epoch_ms()
        if raw_res is not None:
            ok = raw_res.outcome.ok
            err = raw_res.outcome.error
            executed_hot = raw_res.outcome.executed_hot
            dispatched = _collect_dispatched_task_names(request.task_id, raw_res.invoked_tasks)
        else:
            ok = False
            err = ErrorDetail(
                ErrorCode.BUSINESS_FAILURE,
                safe_exception_summary(raised_exc) if raised_exc is not None else "Invocation aborted",
                source_task=str(request.task_id),
            )
            executed_hot = self._opts.is_daemon_host
            dispatched = (str(request.task_id),)
        exit_code = 0 if ok else 1
        err_code = err.code.value if err is not None else ""
        attach_diag = (not ok) or (duration_ms >= _resolve_slow_threshold_ms(self._opts.config_view))
        trace_rec = ExecutionTraceRecord(
            ts_utc=out_ts,
            epoch_ms=out_ms,
            trace_id=eff_tree_id,
            daemon_boot_id=self._daemon_boot_id,
            pid=os.getpid(),
            task_id=str(request.task_id),
            args=(),
            caller_mode=request.caller_surface.value,
            caller_cwd=str(request.caller_cwd),
            executed_hot=executed_hot,
            exit_code=exit_code,
            ok=ok,
            duration_ms=duration_ms,
            rss_kb=rss_after,
            rss_delta_kb=rss_after - rss_before,
            mem_tracked=eff_profile_mem,
            dispatched_tasks=dispatched,
            profiler_tree=active_prof.snapshot(),
            error_code=err_code,
            error_detail=_redacted_error_detail_dict(err) if attach_diag else None,
            runtime_snapshot=self._build_runtime_snapshot() if attach_diag else None,
        )
        ring = self._profiler_ring_buffer
        if record_ring and ring is not None:
            ring.record(trace_rec)
        router = self._flight_log_router
        if write_disk and router is not None and router.enabled:
            router.record_daily(
                DailyEventRecord(
                    ts_utc=out_ts,
                    epoch_ms=out_ms,
                    kind="OUT",
                    trace_id=eff_tree_id,
                    daemon_boot_id=self._daemon_boot_id,
                    pid=os.getpid(),
                    exec_mode=exec_mode,
                    module=request.task_id.module_id.value,
                    task_id=str(request.task_id),
                    level=LogLevel.INFO if ok else LogLevel.ERROR,
                    ok=ok,
                    duration_ms=duration_ms,
                    exit_code=exit_code,
                    message=err.message if err is not None else f"task_done:{request.task_id}",
                )
            )
            router.record_perf(trace_rec)

    def _invoke_raw(
        self, request: InvokeRequest, *, cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None, turn_guard: Optional[DeadlineGuard] = None,
        initial_timeout_ms: Optional[int] = None,
    ) -> RawInvokeResult:
        prop = request.propagation
        eff_tree_id = prop.call_tree_id or uuid.uuid4().hex
        eff_profile_mem = request.profile_mem or prop.profile_mem
        is_top_level = (not prop.is_nested_call) and (not prop.call_stack)
        owns_flight_disk = (
            is_top_level
            and (not request.external_flight_owner)
            and not (self._opts.is_daemon_host and request.caller_surface == CallerSurface.CLI)
        )
        exec_mode = "hot" if self._opts.is_daemon_host else "cold"
        if request.active_profiler is not None:
            active_prof: Profiler = request.active_profiler
        elif not is_top_level and resolve_active_correlation() is not None:
            active_prof = resolve_active_profiler()
        else:
            active_prof = ProfilerSession(root_name=str(request.task_id), track_memory=eff_profile_mem)
        router = self._flight_log_router
        write_disk = owns_flight_disk and router is not None and router.enabled
        record_ring = is_top_level and self._profiler_ring_buffer is not None
        corr = InvocationCorrelationContext(
            trace_id=eff_tree_id,
            task_id=str(request.task_id),
            exec_mode=exec_mode,
            daemon_boot_id=self._daemon_boot_id,
            profiler=active_prof,
            flight_log_router=router,
        )
        if write_disk and router is not None:
            in_ts, in_ms = _now_utc_and_epoch_ms()
            router.record_daily(
                DailyEventRecord(
                    ts_utc=in_ts,
                    epoch_ms=in_ms,
                    kind="IN",
                    trace_id=eff_tree_id,
                    daemon_boot_id=self._daemon_boot_id,
                    pid=os.getpid(),
                    exec_mode=exec_mode,
                    module=request.task_id.module_id.value,
                    task_id=str(request.task_id),
                    level=LogLevel.INFO,
                    message=f"task_start:{request.task_id}",
                )
            )
        rss_before = read_process_rss_kb() if (write_disk or record_ring) else 0
        eff_turn_guard = (
            turn_guard
            if turn_guard is not None
            else (
                DeadlineGuard.from_timeout_ms(initial_timeout_ms, cancel_token)
                if initial_timeout_ms is not None
                else None
            )
        )
        t0_ns = time.perf_counter_ns()
        raw_res: Optional[RawInvokeResult] = None
        raised_exc: Optional[BaseException] = None
        try:
            with MemoryTrackingGuard(eff_profile_mem), active_invocation_correlation_scope(corr):
                raw_res = self._invoke_raw_body(
                    request,
                    eff_tree_id=eff_tree_id,
                    eff_profile_mem=eff_profile_mem,
                    cancel_token=cancel_token,
                    on_progress=on_progress,
                    turn_guard=eff_turn_guard,
                )
                return raw_res
        except BaseException as exc:
            raised_exc = exc
            raise
        finally:
            if write_disk or record_ring:
                self._record_flight_completion(
                    request=request,
                    eff_tree_id=eff_tree_id,
                    exec_mode=exec_mode,
                    eff_profile_mem=eff_profile_mem,
                    active_prof=active_prof,
                    rss_before=rss_before,
                    t0_ns=t0_ns,
                    raw_res=raw_res,
                    raised_exc=raised_exc,
                    write_disk=write_disk,
                    record_ring=record_ring,
                )

    def _invoke_raw_body(
        self, request: InvokeRequest, *, eff_tree_id: str, eff_profile_mem: bool,
        cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None, turn_guard: Optional[DeadlineGuard] = None,
    ) -> RawInvokeResult:
        token = cancel_token or CancellationToken()
        fallback_tid = str(request.task_id)
        if token.is_cancelled:
            return RawInvokeResult(cancelled_task_outcome(token, fallback_tid))
        try:
            validate_wire_json_object(request.raw_input, max_depth=MAX_USER_JSON_DEPTH, label="InvokeRequest.raw_input")
        except (TypeError, ValueError) as exc:
            err = ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid InvokeRequest.raw_input: {safe_exception_summary(exc)}", source_task=fallback_tid)
            return RawInvokeResult(TaskOutcome(ok=False, error=err, executed_hot=self._opts.is_daemon_host))
        prop = request.propagation
        eff_hot_ws = prop.hot_workspaces | (frozenset({self._workspace_root}) if self._opts.is_daemon_host else frozenset())
        sanitized_req = replace(
            request,
            caller_env=sanitize_caller_env(request.caller_env),
            profile_mem=eff_profile_mem,
            propagation=replace(prop, call_tree_id=eff_tree_id, hot_workspaces=eff_hot_ws, profile_mem=eff_profile_mem),
        )
        if self._is_draining_or_stopped_for(sanitized_req.propagation):
            return RawInvokeResult(
                TaskOutcome(
                    ok=False,
                    error=ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, self._draining_or_stopped_message(), source_task=fallback_tid),
                    executed_hot=self._opts.is_daemon_host,
                )
            )
        if sanitized_req.workspace_root != self._workspace_root:
            return self._delegate_to_child_workspace(sanitized_req, token, on_progress, turn_guard)
        return self._invoke_local_or_routed(sanitized_req, eff_tree_id, fallback_tid, token, on_progress, turn_guard)

    def _invoke_local_or_routed(
        self, sanitized_req: InvokeRequest, eff_tree_id: str, fallback_tid: str, token: CancellationToken,
        on_progress: Optional[Callable[[JsonObject], None]], turn_guard: Optional[DeadlineGuard],
    ) -> RawInvokeResult:
        eff_guard = turn_guard
        if eff_guard is None:
            pre_entry = self._routes.lookup(sanitized_req.task_id, ensure_ready=True)
            if pre_entry is not None and pre_entry[1].timeout_ms is not None:
                eff_guard = DeadlineGuard.from_timeout_ms(pre_entry[1].timeout_ms, token)
        if self._opts.is_daemon_host:
            try:
                gate_tmo = eff_guard.remaining_ms() if eff_guard is not None else None
                with resolve_active_profiler().scope_relative("Runtime/QuiesceWait"):
                    self._gates.wait_for_unquiesced(sanitized_req, token, self._step_host.is_reentrant_retiring, timeout_ms=gate_tmo)
            except (TaskCancelledException, YscbError) as exc:
                return RawInvokeResult(TaskOutcome(ok=False, error=exc.detail.with_fallback_task(fallback_tid), executed_hot=True))
            if token.is_cancelled:
                return RawInvokeResult(cancelled_task_outcome(token, fallback_tid))
        with resolve_active_profiler().scope_relative("Runtime/Route"):
            gate_err, resolved = self._validate_stage1_gates(sanitized_req)
            if gate_err is not None and gate_err.code in (ErrorCode.TASK_NOT_FOUND, ErrorCode.MODULE_DEGRADED) and not self._opts.is_daemon_host:
                ref_err = self._cold_locks.refresh_cold_routes(token, eff_tree_id, deadline=eff_guard.deadline if eff_guard is not None else None)
                if ref_err is not None:
                    return RawInvokeResult(TaskOutcome(ok=False, error=ref_err.with_fallback_task(fallback_tid)))
                gate_err, resolved = self._validate_stage1_gates(sanitized_req)
            if gate_err is not None:
                return RawInvokeResult(TaskOutcome(ok=False, error=gate_err.with_fallback_task(fallback_tid)))
            _mod_desc, spec = require_non_none(resolved)
        if eff_guard is None and spec.timeout_ms is not None:
            eff_guard = DeadlineGuard.from_timeout_ms(spec.timeout_ms, token)
        if not self._opts.is_daemon_host and not sanitized_req.propagation.is_nested_call:
            return self._route_external_turn(sanitized_req, spec, token, on_progress, eff_guard)
        return self._run_full_turn_locally(
            sanitized_req, spec, is_hot=self._opts.is_daemon_host, cancel_token=token, on_progress=on_progress, turn_guard=eff_guard,
        )

    def _delegate_to_child_workspace(
        self, request: InvokeRequest, token: CancellationToken,
        on_progress: Optional[Callable[[JsonObject], None]], turn_guard: Optional[DeadlineGuard],
    ) -> RawInvokeResult:
        if self._opts.child_dispatcher_factory is None:
            err = ErrorDetail(ErrorCode.TASK_NOT_FOUND, f"No child workspace dispatcher configured for {request.workspace_root}", source_task=str(request.task_id))
            return RawInvokeResult(TaskOutcome(ok=False, error=err))
        child_req = replace(request, propagation=replace(request.propagation, is_nested_call=False, from_hot_container=False))
        try:
            child_disp = self._opts.child_dispatcher_factory(child_req.workspace_root)
        except YscbError as exc:
            return RawInvokeResult(TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(request.task_id))))
        raw_res: Optional[RawInvokeResult] = None
        child_td: tuple[ErrorDetail, ...] = ()
        is_owned_or_managed = (
            (self._opts.owns_child_dispatchers or is_managed_child_dispatcher(child_disp))
            and child_disp is not self
            and not child_disp.is_daemon_host
        )
        try:
            if isinstance(child_disp, RuntimeDispatcher):
                if is_owned_or_managed:
                    child_disp._bind_shared_coordinators(self._shared_ws)
                raw_res = child_disp._invoke_raw(child_req, cancel_token=token, on_progress=on_progress, turn_guard=turn_guard)
            else:
                raw_res = RawInvokeResult(child_disp.invoke(child_req, cancel_token=token, on_progress=on_progress))
            if raw_res.invoked_tasks:
                self._sessions.record_transitive_invoked_tasks(request.propagation, raw_res.invoked_tasks)
        finally:
            is_eph = (
                self._opts.owns_child_dispatchers and child_disp is not self
                and not child_disp.is_daemon_host and child_disp.container_lifecycle.state == ContainerState.UNINITIALIZED
                and child_disp.active_turn_count == 0
            )
            can_drain_owned_td = is_owned_or_managed and child_disp.active_turn_count == 0
            child_td = (
                child_disp.shutdown(grace_ms=500)
                if is_eph
                else (child_disp.drain_teardown_diagnostics() if can_drain_owned_td else ())
            )
            if child_td and raw_res is None:
                self._sessions.record_host_teardown_diags(child_td)
        raw_res = require_non_none(raw_res)
        if child_td:
            return replace(raw_res, outcome=replace(raw_res.outcome, teardown_diagnostics=(*raw_res.outcome.teardown_diagnostics, *child_td)))
        return raw_res

    def _route_external_turn(
        self, request: InvokeRequest, spec: TaskRouteSpec, token: CancellationToken,
        on_progress: Optional[Callable[[JsonObject], None]], turn_guard: Optional[DeadlineGuard],
    ) -> RawInvokeResult:
        conn_cfg = self._opts.connection_config
        requires_hot = (
            request.routing_policy == ClientRoutingPolicy.STRICT_HOT
            or (conn_cfg.strict_hot_dispatch and request.routing_policy != ClientRoutingPolicy.FORCE_COLD)
            or spec.dispatch_mode == DispatchMode.DAEMON_ONLY
        )
        prefer_local_cold = (self._workspace_root in request.propagation.cold_shared_workspaces) and not requires_hot
        auto_spawned = False
        if conn_cfg.enabled and spec.dispatch_mode != DispatchMode.COLD_ONLY and request.routing_policy != ClientRoutingPolicy.FORCE_COLD and not prefer_local_cold:
            hot_res = self._try_remote_daemon_call(request, spec, token, on_progress, turn_guard)
            if hot_res is not None:
                return hot_res
            if requires_hot:
                return RawInvokeResult(TaskOutcome(ok=False, error=ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, f"Daemon required for '{request.task_id}' but unavailable.", remediation="Run 'yscb daemon start' or omit strict hot mode.", source_task=str(request.task_id))))
            sp = self._opts.daemon_spawner
            auto_spawned = request.routing_policy == ClientRoutingPolicy.AUTO_SPAWN and conn_cfg.auto_spawn and sp is not None and sp.can_spawn_in_environment()
        elif spec.dispatch_mode != DispatchMode.COLD_ONLY and requires_hot:
            return RawInvokeResult(TaskOutcome(ok=False, error=ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, f"Daemon required for '{request.task_id}' but disabled or unavailable.", source_task=str(request.task_id))))
        try:
            return self._run_full_turn_locally(request, spec, is_hot=False, cancel_token=token, on_progress=on_progress, turn_guard=turn_guard)
        finally:
            core_ym = self._in_mem_map.get(CORE_MODULE_ID)
            post_hook = resolve_sdk_core_post_call_hook(core_ym) if core_ym is not None else None
            if post_hook is not None:
                try:
                    post_hook()
                except (OSError, ValueError, YscbError):
                    pass
            if auto_spawned and self._opts.daemon_spawner is not None:
                self._opts.daemon_spawner.try_spawn_background(self._workspace_root)
    def try_quiesce_global(self, *, drain_deadline: Optional[float] = None, leased: bool = False) -> bool:
        safe_dl = normalize_drain_deadline(drain_deadline)
        with self._gates.lifecycle_scope():
            pre_ids = self._sessions.snapshot_active_turn_and_tree_ids() if leased else frozenset()
            if not self._gates.try_begin_global_quiesce(drain_deadline=safe_dl, leased=leased, pre_accepted_ids=pre_ids):
                return False
            rem_ms = 2000 if safe_dl is None else max(100, min(2000, int(max(0.0, min(10.0, safe_dl - time.monotonic())) * 1000.0)))
            all_descs = self._all_known_descriptors()
            all_mods = frozenset(d.module_id for d in all_descs if d.module_id != CORE_MODULE_ID)
            try:
                if all_mods:
                    self._sessions.record_host_teardown_diags(self._tier1_pool.stop_groups_for_modules(all_mods, all_descs, grace_ms=rem_ms, drain_in_flight=False))
                    self._sessions.record_host_teardown_diags(self._tier0_slots.unload_modules(all_mods, drain_in_flight=True, grace_sec=ms_to_safe_sec(rem_ms, min_sec=0.1)))
                self._sessions.record_host_teardown_diags(
                    self._sessions.evict_cold_tier1_for_quiesce(grace_sec=ms_to_safe_sec(rem_ms, min_sec=0.1))
                )
                return True
            except BaseException:
                if leased:
                    self._gates.record_quiesce_lease(0.5)
                else:
                    with self._gates.resume_reload_scope():
                        pass
                raise

    def quiesce_global(self, grace_ms: int = 3000) -> None:
        if isinstance(grace_ms, bool) or not isinstance(grace_ms, int) or grace_ms < 0:
            raise ValueError(f"grace_ms must be a non-negative int (not bool), got {grace_ms!r}")
        self.try_quiesce_global(drain_deadline=time.monotonic() + ms_to_safe_sec(grace_ms, min_sec=0.05), leased=False)

    def execute_daemon_quiesce_resume(
        self, *, expected_epoch: Optional[int], check_core_mutated: Callable[[], bool], on_before_warmup: Callable[[], None],
    ) -> QuiesceResumeResult:
        if expected_epoch is not None:
            require_pure_int(expected_epoch, "expected_epoch", min_val=0)

        def _run_resume_body() -> bool:
            if check_core_mutated():
                return True
            self._resume_quiesce_core(on_before_warmup=on_before_warmup)
            return False

        return self._gates.run_global_resume_guarded(expected_epoch, _run_resume_body)

    def resume_from_quiesce(self, *, on_before_warmup: Optional[Callable[[], None]] = None) -> None:
        self._resume_quiesce_core(on_before_warmup=on_before_warmup)

    def _resume_quiesce_core(self, *, on_before_warmup: Optional[Callable[[], None]]) -> None:
        with self._gates.lifecycle_scope():
            prev_descs = self._all_known_descriptors()
            self._module_provider.reload()
            plan_descs = self._all_known_descriptors()
            with self._gates.resume_reload_scope():
                re_warm = frozenset(d.module_id for d in (*prev_descs, *plan_descs) if d.module_id != CORE_MODULE_ID)
                if re_warm:
                    stop_descs = (*prev_descs, *(d for d in plan_descs if d not in prev_descs))
                    self._sessions.record_host_teardown_diags(self._tier1_pool.stop_groups_for_modules(re_warm, stop_descs, grace_ms=1000, drain_in_flight=False))
                    self._sessions.record_host_teardown_diags(self._tier0_slots.unload_modules(re_warm, drain_in_flight=True, grace_sec=1.0))
                self._sessions.record_host_teardown_diags(self._sessions.evict_cold_tier1_for_quiesce(grace_sec=1.0))
                if on_before_warmup is not None:
                    on_before_warmup()
                self._module_provider.reload()
                self._cfg_tracker.reload_always()
                self._sessions.record_host_teardown_diags(
                    self._sessions.sync_cold_slots_on_reload(re_warm, self._all_known_descriptors())
                )
                self._container.clear_degraded()
                self._routes.rebuild()
                if self._opts.is_daemon_host:
                    self.warmup_daemon_container()

    def reload_config_and_contributes(self, *, changed_paths: Sequence[str] = (), emit_event: bool = True) -> bool:
        with self._gates.lifecycle_scope():
            changed = self._cfg_tracker.reload_always()
            self._module_provider.reload()
            self._sessions.record_host_teardown_diags(
                self._sessions.sync_cold_slots_on_reload(frozenset(), self._all_known_descriptors())
            )
            self._routes.rebuild()
        st = self._container.state
        cfg_sub_gated = any(self._gates.is_call_gated_for_quiesce(mid) for mid in self.subscribed_modules(CONFIG_CHANGED_EVENT_ID))
        if emit_event and changed and self._opts.is_daemon_host and st in (ContainerState.UNINITIALIZED, ContainerState.READY, ContainerState.QUIESCED) and not self._gates.is_globally_quiesced() and not cfg_sub_gated:
            self.emit_background_event(CONFIG_CHANGED_EVENT_ID, {"changed_paths": list(changed_paths)})
        return changed

    def reload_affected_modules(self, modules: frozenset[ModuleId], grace_ms: int = 2000) -> None:
        with self._gates.lifecycle_scope():
            all_descs = self._all_known_descriptors()
            reload_all = (not bool(modules)) or (CORE_MODULE_ID in modules)
            base_mods = (modules - frozenset({CORE_MODULE_ID})) if not reload_all else frozenset(d.module_id for d in all_descs if d.module_id != CORE_MODULE_ID)
            gated_mods = base_mods if reload_all else expand_colocated_tier1_siblings(base_mods, all_descs)
            with self._gates.module_reload_scope(reload_all, gated_mods):
                self._tier1_pool.bump_groups_epoch(gated_mods, all_descs)
                self._sessions.record_host_teardown_diags(self._tier1_pool.stop_groups_for_modules(gated_mods, all_descs, grace_ms=grace_ms, drain_in_flight=True))
                grace_s = ms_to_safe_sec(grace_ms, min_sec=0.1)
                self._sessions.record_host_teardown_diags(self._tier0_slots.unload_modules(base_mods, drain_in_flight=True, grace_sec=grace_s))
                self._cfg_tracker.reload_always()
                self._module_provider.reload()
                fresh_descs = self._all_known_descriptors()
                self._sessions.record_host_teardown_diags(
                    self._sessions.sync_cold_slots_on_reload(
                        base_mods,
                        fresh_descs,
                        grace_sec=grace_s,
                        evict_all=reload_all,
                    )
                )
                fresh_ids = frozenset(d.module_id for d in fresh_descs if d.module_id != CORE_MODULE_ID)
                now_mods = fresh_ids if reload_all else ((gated_mods | expand_colocated_tier1_siblings(base_mods, fresh_descs)) & fresh_ids)
                self._container.reload_modules(None if reload_all else gated_mods)
                self._routes.rebuild()
                self._gates.bump_reload_epochs(base_mods | gated_mods | now_mods)
                if self._opts.is_daemon_host and (reload_all or now_mods) and not self._gates.is_globally_quiesced():
                    self.warmup_daemon_container(only_modules=None if reload_all else now_mods)

    def emit_background_event(
        self, event_id: EventId, raw_payload: JsonObject, *, ordering: EventOrdering = EventOrdering.UNORDERED,
    ) -> TurnExecutionReport:
        tid, caller_tok, turn_cg = uuid.uuid4().hex, CancellationToken(), SharedCancelGroup()
        detach_bg = turn_cg.try_add_participant(caller_tok)
        if self._opts.is_daemon_host:
            scope = None if self._gates.is_globally_quiesced() else self._container.begin_hot_turn(TurnKind.HOT_BACKGROUND, cancel_token=turn_cg.host_token, turn_id=tid)
            if scope is None:
                if detach_bg is not None:
                    detach_bg()
                turn_cg.close_all()
                return TurnExecutionReport(turn_id=tid, primary_result=StepExecutionResult(ok=False, error=ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, "Container is draining, stopped, or quiesced.")))
        else:
            if self._container.state in (ContainerState.DRAINING, ContainerState.STOPPED):
                if detach_bg is not None:
                    detach_bg()
                turn_cg.close_all()
                return TurnExecutionReport(turn_id=tid, primary_result=StepExecutionResult(ok=False, error=ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, self._draining_or_stopped_message())))
            scope = TurnScope(turn_id=tid, kind=TurnKind.COLD, cancel_token=turn_cg.host_token)
        session = ActiveTurnSession(
            scope=scope, caller_cancel=caller_tok, prio_handle=PriorityHandle(ExecutionPriority.BACKGROUND),
            hot_workspaces=frozenset({self._workspace_root}) if self._opts.is_daemon_host else frozenset(),
            cold_shared_workspaces=frozenset() if self._opts.is_daemon_host else frozenset({self._workspace_root}),
        )
        rec = RawEventRecord(event_id=event_id, emitter_task=WATCHER_TASK_ID, raw_payload=raw_payload, ordering=ordering, lineage=CausalLineage().advance(event_id, workspace_scope=self._workspace_root.comparison_key))
        ev_label = f"event:{event_id.value}"
        ev_prof = ProfilerSession(root_name=ev_label)
        exec_mode = "hot" if self._opts.is_daemon_host else "cold"
        router = self._flight_log_router
        write_disk = router is not None and router.enabled
        record_ring = self._profiler_ring_buffer is not None
        corr = InvocationCorrelationContext(
            trace_id=tid,
            task_id=ev_label,
            exec_mode=exec_mode,
            daemon_boot_id=self._daemon_boot_id,
            profiler=ev_prof,
            flight_log_router=router,
        )
        if write_disk and router is not None:
            in_ts, in_ms = _now_utc_and_epoch_ms()
            router.record_daily(
                DailyEventRecord(
                    ts_utc=in_ts,
                    epoch_ms=in_ms,
                    kind="IN",
                    trace_id=tid,
                    daemon_boot_id=self._daemon_boot_id,
                    pid=os.getpid(),
                    exec_mode=exec_mode,
                    module=event_id.module_id.value,
                    task_id=ev_label,
                    level=LogLevel.INFO,
                    message=f"event_start:{event_id.value}",
                )
            )
        rss_before = read_process_rss_kb() if (write_disk or record_ring) else 0
        t0_ns = time.perf_counter_ns()
        report_out: Optional[TurnExecutionReport] = None
        try:
            with active_invocation_correlation_scope(corr), self._sessions.managed_session(session):
                if self._opts.is_daemon_host:
                    report_out = self._turn_engine.execute_event_turn(scope, (rec,))
                    return report_out
                if self._container.state in (ContainerState.DRAINING, ContainerState.STOPPED):
                    report_out = TurnExecutionReport(turn_id=tid, primary_result=StepExecutionResult(ok=False, error=ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, self._draining_or_stopped_message())))
                    return report_out
                report_out = self._cold_locks.run_cold_event_turn(scope, lambda: self._turn_engine.execute_event_turn(scope, (rec,)))
                return report_out
        finally:
            if detach_bg is not None:
                detach_bg()
            turn_cg.close_all()
            if write_disk or record_ring:
                ev_dur_ms = round(max(0.0, (time.perf_counter_ns() - t0_ns) / 1_000_000.0), 4)
                ev_rss = read_process_rss_kb()
                out_ts, out_ms = _now_utc_and_epoch_ms()
                ev_err = (
                    (report_out.fatal_event_error or report_out.primary_result.error)
                    if report_out is not None
                    else None
                )
                ev_ok = report_out is not None and ev_err is None and report_out.primary_result.ok
                ev_diag = (not ev_ok) or (ev_dur_ms >= _resolve_slow_threshold_ms(self._opts.config_view))
                ev_trace = ExecutionTraceRecord(
                    ts_utc=out_ts,
                    epoch_ms=out_ms,
                    trace_id=tid,
                    daemon_boot_id=self._daemon_boot_id,
                    pid=os.getpid(),
                    task_id=ev_label,
                    args=(),
                    caller_mode="event",
                    caller_cwd=str(self._workspace_root),
                    executed_hot=self._opts.is_daemon_host,
                    exit_code=0 if ev_ok else 1,
                    ok=ev_ok,
                    duration_ms=ev_dur_ms,
                    rss_kb=ev_rss,
                    rss_delta_kb=ev_rss - rss_before,
                    mem_tracked=False,
                    dispatched_tasks=(ev_label,),
                    profiler_tree=ev_prof.snapshot(),
                    error_code=ev_err.code.value if ev_err is not None else "",
                    error_detail=_redacted_error_detail_dict(ev_err) if ev_diag else None,
                    runtime_snapshot=self._build_runtime_snapshot() if ev_diag else None,
                )
                if record_ring and self._profiler_ring_buffer is not None:
                    self._profiler_ring_buffer.record(ev_trace)
                if write_disk and router is not None:
                    router.record_daily(
                        DailyEventRecord(
                            ts_utc=out_ts,
                            epoch_ms=out_ms,
                            kind="OUT",
                            trace_id=tid,
                            daemon_boot_id=self._daemon_boot_id,
                            pid=os.getpid(),
                            exec_mode=exec_mode,
                            module=event_id.module_id.value,
                            task_id=ev_label,
                            level=LogLevel.INFO if ev_ok else LogLevel.ERROR,
                            ok=ev_ok,
                            duration_ms=ev_dur_ms,
                            exit_code=0 if ev_ok else 1,
                            message=ev_err.message if ev_err is not None else f"event_done:{event_id.value}",
                        )
                    )
                    router.record_perf(ev_trace)
    def cancel_all_active_turns(self, reason: str = "Forced shutdown") -> None:
        require_pure_str(reason, "reason")
        self._force_drain.set()
        self._sessions.cancel_all(reason)

    def _wait_in_flight_drain(self, grace_ms: int) -> int:
        now0 = time.monotonic()
        deadline = now0 + ms_to_safe_sec(grace_ms)
        while True:
            eff_dl = min(deadline, now0 + 0.25) if self._force_drain.is_set() else deadline
            rem = eff_dl - time.monotonic()
            if rem <= 0.0 or (self.active_turn_count == 0 and not self._gates.has_any_active_work()):
                break
            time.sleep(min(0.01, max(0.001, rem)))
        return min(MAX_TIMEOUT_MS, max(100, int((deadline - time.monotonic()) * 1000)))

    def shutdown(self, grace_ms: int = 3000) -> tuple[ErrorDetail, ...]:
        if isinstance(grace_ms, bool) or not isinstance(grace_ms, int) or grace_ms < 0:
            raise ValueError(f"grace_ms must be a non-negative int (not bool), got {grace_ms!r}")
        safe_grace_ms = min(max(0, grace_ms), MAX_TIMEOUT_MS)
        pre_diags: list[ErrorDetail] = list(self.drain_teardown_diagnostics())
        container_diags: tuple[ErrorDetail, ...] = ()
        pool_diags: tuple[ErrorDetail, ...] = ()
        try:
            container_diags = self._container.drain_and_stop(
                grace_period_ms=safe_grace_ms,
                on_drain=lambda gms: pre_diags.extend(self._tier1_pool.prepare_lifo_shutdown(grace_ms=self._wait_in_flight_drain(gms))),
            )
        finally:
            try:
                pool_diags = self._tier1_pool.collect_lifo_shutdown_diagnostics()
            finally:
                slot_diags = self._tier0_slots.unload_all_modules(grace_sec=0.05)
        return (*pre_diags, *container_diags, *pool_diags, *slot_diags)

    def run_primary_step(self, request: InvokeRequest, turn: TurnScope) -> StepExecutionResult[JsonValue]:
        tagged = replace(request, caller_env=sanitize_caller_env(request.caller_env), propagation=replace(request.propagation, turn_id=turn.turn_id))
        return self._execute_single_step_with_coordination(request=tagged, turn=turn)

    def run_event_step(self, batch: EventBatchEnvelope, turn: TurnScope) -> Sequence[StepExecutionResult[JsonValue]]:
        results: list[StepExecutionResult[JsonValue]] = []
        session = self._sessions.get_or_bind_turn_session(turn)
        with resolve_active_profiler().scope_relative("Runtime/EventDrain", batch.event_id.value):
            for m in self._routes.find_matching_subscribers(batch.event_id):
                if turn.cancel_token.is_cancelled:
                    break
                if turn.kind == TurnKind.COLD and m.spec.dispatch_mode == DispatchMode.DAEMON_ONLY:
                    continue
                filtered, sub_lineage = batch.filter_for_subscription(m.sub.payload_filter)
                if not filtered:
                    continue
                step_res = self._run_matched_event_subscriber(m.desc, m.spec, batch.event_id, filtered, sub_lineage, session)
                if step_res is None:
                    continue
                results.append(step_res)
                if step_res.fatal_abort_turn:
                    break
        return results

    def finalize_turn_events(self, turn: TurnScope, *, abort_only: bool = False) -> Optional[ErrorDetail]:
        _ = (turn, abort_only)
        return None

    def _prepare_and_map_subscriber(
        self, desc: ModuleDescriptor, spec: TaskRouteSpec, turn: TurnScope, eff_ctree: str,
        prio: ExecutionPriority, base_prop: CallPropagationContext, event_id: EventId,
        filtered: Sequence[JsonObject], wait_tok: CancellationToken,
        ctx_cancel: Optional[CancellationToken], guard: DeadlineGuard,
    ) -> tuple[Optional[ErrorDetail], bool, InvokeRequest]:
        req = InvokeRequest(
            task_id=spec.task_id, raw_input={}, workspace_root=self._workspace_root, caller_cwd=self._workspace_root,
            priority=prio,
            propagation=replace(base_prop, turn_id=turn.turn_id, call_tree_id=eff_ctree, is_internal_trigger=True, is_nested_call=True, in_event_chain=True),
        )
        if wait_tok.is_cancelled:
            c_code = ErrorCode.TASK_PREEMPTED if wait_tok.is_preempted else ErrorCode.TASK_CANCELLED
            return (ErrorDetail(c_code, wait_tok.reason or "Task cancelled", source_task=str(spec.task_id)), False, req)
        try:
            gate_tmo = guard.remaining_ms(spec.timeout_ms)
        except YscbError as exc:
            return (exc.detail.with_fallback_task(str(spec.task_id)), False, req)
        if self._opts.is_daemon_host:
            try:
                self._gates.wait_for_unquiesced(req, wait_tok, self._step_host.is_reentrant_retiring, timeout_ms=gate_tmo)
            except (TaskCancelledException, YscbError) as exc:
                return (exc.detail.with_fallback_task(str(spec.task_id)), False, req)
            if self._gates.is_quiesced_blocked(req, desc.module_id, True):
                return (ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, f"Module '{desc.module_id}' is currently quiesced.", source_task=str(spec.task_id)), False, req)
            refreshed = self._routes.lookup(spec.task_id)
            if refreshed is None:
                return (None, True, req)
            desc, spec = refreshed
        degraded = self._container.get_degraded(desc.module_id)
        if degraded is not None:
            return (degraded.with_fallback_task(str(spec.task_id)), False, req)
        m_out = self._step_host.map_event_batch(desc, spec.task_id, event_id, filtered, EquivCallContext(turn=turn, call_tree_id=eff_ctree, cancel_token=ctx_cancel, guard=guard))
        if not m_out.ok:
            return (m_out.error, False, req)
        if m_out.skip:
            return (None, True, req)
        return (None, False, replace(req, raw_input=m_out.mapped_input))

    def _run_matched_event_subscriber(
        self, desc: ModuleDescriptor, spec: TaskRouteSpec, event_id: EventId,
        filtered: Sequence[JsonObject], sub_lineage: CausalLineage, session: ActiveTurnSession,
    ) -> Optional[StepExecutionResult[JsonValue]]:
        turn = session.scope
        step_ctree = (session.root_call_tree_id if session.inherit_call_tree else "") or uuid.uuid4().hex
        spec_dl = (time.monotonic() + ms_to_safe_sec(spec.timeout_ms)) if spec.timeout_ms is not None else None
        sub_dl = merge_deadlines(session.current_turn_deadline(), spec_dl)
        sub_guard = DeadlineGuard(cancel_token=turn.cancel_token, deadline=sub_dl)
        base_prop = CallPropagationContext(lineage=sub_lineage, hot_workspaces=session.hot_workspaces, cold_shared_workspaces=session.cold_shared_workspaces)
        sub_err, skip, mapped_req = self._prepare_and_map_subscriber(
            desc, spec, turn, step_ctree, session.prio_handle.current, base_prop, event_id, filtered, turn.cancel_token, None, sub_guard,
        )
        if sub_err is not None:
            return _failed_step_result(sub_err, spec.task_id, fatal=False)
        if skip:
            return None
        return self._execute_single_step_with_coordination(request=mapped_req, turn=turn, parent_prio=session.prio_handle, parent_deadline=spec_dl)
    def _handle_worker_callback(self, env: WorkerCallbackEnvelope, peer_cancel_token: CancellationToken) -> WorkerCallbackReply:
        step_bind = self._sessions.lookup_active_step(env.context_meta.step_run_id)
        if step_bind is None:
            if env.callback == WorkerCallbackKind.EMIT_IMM:
                return WorkerCallbackReply(ok=False, error=ErrorDetail(ErrorCode.TASK_CANCELLED, "Parent step is no longer active for emit_imm"))
            return WorkerCallbackReply(
                ok=False,
                error=ErrorDetail(
                    ErrorCode.TASK_CANCELLED,
                    "Parent step inactive for invoke_task",
                    source_task=str(env.task_id) if env.task_id is not None else None,
                ),
                executed_hot=self._opts.is_daemon_host,
            )
        turn_id = step_bind.turn_id
        turn = self._sessions.try_retain_session_scope(turn_id) if turn_id else None
        try:
            if step_bind.correlation is not None:
                with active_invocation_correlation_scope(step_bind.correlation):
                    if env.callback == WorkerCallbackKind.EMIT_IMM:
                        return self._on_worker_emit_imm(env, step_bind, turn, peer_cancel_token)
                    return self._on_worker_invoke_task(env, step_bind, turn, peer_cancel_token)
            if env.callback == WorkerCallbackKind.EMIT_IMM:
                return self._on_worker_emit_imm(env, step_bind, turn, peer_cancel_token)
            return self._on_worker_invoke_task(env, step_bind, turn, peer_cancel_token)
        finally:
            if turn is not None:
                self._sessions.release_turn_session(turn.turn_id)

    def _on_worker_emit_imm(
        self, env: WorkerCallbackEnvelope, step_bind: ActiveStepBinding, turn: Optional[TurnScope], peer_cancel_token: CancellationToken,
    ) -> WorkerCallbackReply:
        if turn is None or env.event_id is None:
            return WorkerCallbackReply(ok=False, error=ErrorDetail(ErrorCode.TASK_CANCELLED, "Parent step is no longer active for emit_imm"))
        cb_cancel, detach_cb = CancellationToken.combine(step_bind.cancel_token, peer_cancel_token)
        auth_prop = step_bind.propagation
        emit_tid = auth_prop.call_stack[-1][1] if auth_prop.call_stack else None
        try:
            imm_lin = auth_prop.lineage.advance(
                env.event_id,
                source_task=str(emit_tid) if emit_tid is not None else None,
                workspace_scope=self._workspace_root.comparison_key,
            )
            self._dispatch_immediate_event(
                _ImmediateEventDispatchSpec(
                    event_id=env.event_id, raw_payload=env.raw_payload, propagation=replace(auth_prop, lineage=imm_lin),
                    strict=env.strict, emitter_task=emit_tid, parent_step_cancel=cb_cancel,
                    parent_prio=step_bind.prio_handle, step_deadline=step_bind.current_deadline(),
                ),
                turn,
            )
            return WorkerCallbackReply(ok=True)
        except YscbError as exc:
            return WorkerCallbackReply(ok=False, error=exc.detail)
        except (Exception, SystemExit, GeneratorExit) as exc:
            return WorkerCallbackReply(ok=False, error=ErrorDetail(ErrorCode.BUSINESS_FAILURE, safe_exception_summary(exc), source_task=str(emit_tid) if emit_tid is not None else None))
        finally:
            detach_cb()

    def _on_worker_invoke_task(
        self, env: WorkerCallbackEnvelope, step_bind: ActiveStepBinding, turn: Optional[TurnScope], peer_cancel_token: CancellationToken,
    ) -> WorkerCallbackReply:
        if turn is None:
            return WorkerCallbackReply(
                ok=False,
                error=ErrorDetail(
                    ErrorCode.TASK_CANCELLED,
                    "Parent step inactive for invoke_task",
                    source_task=str(env.task_id) if env.task_id is not None else None,
                ),
                executed_hot=self._opts.is_daemon_host,
            )
        if env.task_id is None:
            return WorkerCallbackReply(ok=False, error=ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, "INVOKE_TASK callback requires task_id."), executed_hot=self._opts.is_daemon_host)
        cb_cancel, detach_cb = CancellationToken.combine(step_bind.cancel_token, peer_cancel_token)
        try:
            target_ws = env.target_workspace or self._workspace_root
            r_pol = env.routing_policy or default_nested_routing_policy(target_ws != self._workspace_root, step_bind.parent_routing_policy)
            parent_ph = step_bind.prio_handle
            auth_prop = step_bind.propagation
            eff_lineage = _resolve_authoritative_child_lineage(auth_prop.lineage, env.lineage)
            nested_spec = _NestedInvokeSpec(
                child_task_id=env.task_id, raw_input=env.raw_input, target_workspace=target_ws,
                caller_cwd=env.context_meta.caller_cwd, caller_env=sanitize_caller_env(env.context_meta.caller_env),
                routing_policy=r_pol, priority=parent_ph.current, approval_scope=step_bind.approval_scope,
                allow_conditional=step_bind.allow_conditional, propagation=replace(auth_prop, lineage=eff_lineage),
                parent_prio=parent_ph, step_deadline=step_bind.current_deadline(),
            )
            nested_out = self._invoke_nested_within_turn(turn, nested_spec, cb_cancel)
            return WorkerCallbackReply(
                ok=nested_out.ok, raw_value=nested_out.value, error=nested_out.error,
                event_diagnostics=nested_out.event_diagnostics, teardown_diagnostics=nested_out.teardown_diagnostics,
                coalesced=nested_out.coalesced, executed_hot=nested_out.executed_hot, fatal_abort_turn=False,
            )
        except YscbError as exc:
            return WorkerCallbackReply(ok=False, error=exc.detail, executed_hot=self._opts.is_daemon_host, fatal_abort_turn=is_fatal_error_code(exc.detail.code))
        except (Exception, SystemExit, GeneratorExit) as exc:
            err = ErrorDetail(ErrorCode.BUSINESS_FAILURE, safe_exception_summary(exc), source_task=str(env.task_id))
            return WorkerCallbackReply(ok=False, error=err, executed_hot=self._opts.is_daemon_host, fatal_abort_turn=False)
        finally:
            detach_cb()

    def _cold_bootstrap_hook(self) -> None:
        with self._gates.lifecycle_scope():
            self._container.clear_degraded()
            self._cfg_tracker.reload_if_changed()
            self._module_provider.reload()
            self._routes.rebuild()

    def _draining_or_stopped_message(self) -> str:
        return "Hot container is draining or stopped." if self._opts.is_daemon_host else "RuntimeDispatcher is draining or stopped."

    def _is_draining_or_stopped_for(self, prop: CallPropagationContext) -> bool:
        c_state = self._container.state
        if c_state == ContainerState.STOPPED:
            return True
        if c_state == ContainerState.DRAINING:
            admitted = self._sessions.has_admitted_session(prop) or self._gates.has_admitted_rpc_turn(prop.turn_id or "")
            return not admitted
        return False

    def _validate_stage1_gates(
        self, request: InvokeRequest, *, in_cold_turn: bool = False,
    ) -> tuple[Optional[ErrorDetail], Optional[tuple[ModuleDescriptor, TaskRouteSpec]]]:
        blocked_lifecycle = self._is_draining_or_stopped_for(request.propagation)
        found = self._routes.lookup(request.task_id, ensure_ready=(not blocked_lifecycle))
        mod_id = found[0].module_id if found is not None else request.task_id.module_id
        if blocked_lifecycle:
            block_err: Optional[ErrorDetail] = ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, self._draining_or_stopped_message(), source_task=str(request.task_id))
        elif self._gates.is_quiesced_blocked(request, mod_id, self._opts.is_daemon_host):
            block_err = ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, f"Module '{request.task_id.module_id}' is currently quiesced.", source_task=str(request.task_id))
        else:
            deg = self._container.get_degraded(mod_id)
            block_err = deg.with_fallback_task(str(request.task_id)) if deg is not None else None
        return validate_stage1_gates(
            request, found, block_err, is_daemon_host=self._opts.is_daemon_host,
            conn_enabled=self._opts.connection_config.enabled, in_cold_turn=in_cold_turn,
        )

    def _try_remote_daemon_call(
        self, request: InvokeRequest, spec: TaskRouteSpec, cancel_token: CancellationToken,
        on_progress: Optional[Callable[[JsonObject], None]], turn_guard: Optional[DeadlineGuard],
    ) -> Optional[RawInvokeResult]:
        try:
            eff_req_tmo = turn_guard.remaining_ms(spec.timeout_ms) if turn_guard is not None else spec.timeout_ms
            client_owns_flight = bool(
                request.external_flight_owner
                or (self._flight_log_router is not None and self._flight_log_router.enabled)
            )
            wire_payload = DataclassCodec.encode_envelope(
                DaemonRpcInvokeEnvelope(
                    task_id=request.task_id, raw_input=request.raw_input, workspace_root=request.workspace_root,
                    caller_cwd=request.caller_cwd, caller_env=request.caller_env, caller_surface=request.caller_surface,
                    priority=request.priority, approval_scope=request.approval_scope,
                    allow_conditional=request.allow_conditional, timeout_ms=eff_req_tmo, propagation=request.propagation,
                    client_owns_flight_logs=client_owns_flight,
                )
            )
        except YscbError as exc:
            return RawInvokeResult(TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(request.task_id))))
        rpc_tmo = None if eff_req_tmo is None else eff_req_tmo + 250
        active_prof = resolve_active_profiler()
        with active_prof.scope_relative("Runtime/RpcCall"):
            if self._opts.persistent_rpc_session is not None:
                outcome = self._opts.persistent_rpc_session.call(wire_payload, on_progress=on_progress, cancel_token=cancel_token, timeout_ms=rpc_tmo)
            else:
                outcome = call_ephemeral_daemon_rpc((self._cache_dir, self._workspace_root), wire_payload, on_progress=on_progress, cancel_token=cancel_token, timeout_ms=rpc_tmo)
            translated = translate_remote_daemon_outcome(outcome, cancel_token, str(request.task_id))
            if translated is not None and translated.profiler_tree is not None:
                active_prof.merge_subtree(translated.profiler_tree)
        if translated is not None and translated.invoked_tasks:
            self._sessions.record_transitive_invoked_tasks(request.propagation, translated.invoked_tasks)
        return translated
    def _run_full_turn_locally(
        self, request: InvokeRequest, spec: TaskRouteSpec, *, is_hot: bool,
        cancel_token: CancellationToken, on_progress: Optional[Callable[[JsonObject], None]], turn_guard: Optional[DeadlineGuard],
    ) -> RawInvokeResult:
        raw_prop = request.propagation
        was_admitted = self._sessions.has_admitted_session(raw_prop) or self._gates.has_admitted_rpc_turn(raw_prop.turn_id or "")
        tid, prop = self._sessions.ensure_fresh_turn_id(replace(raw_prop, turn_id=raw_prop.turn_id or uuid.uuid4().hex))
        tagged_req = replace(request, propagation=prop)
        turn_kind = (TurnKind.HOT_BACKGROUND if request.priority == ExecutionPriority.BACKGROUND else TurnKind.HOT_FOREGROUND) if is_hot else TurnKind.COLD
        turn_cg = SharedCancelGroup()
        if turn_kind == TurnKind.COLD:
            cur_st = self._container.state
            turn_scope: Optional[TurnScope] = (
                None
                if (cur_st == ContainerState.STOPPED or (cur_st == ContainerState.DRAINING and not was_admitted))
                else TurnScope(turn_id=tid, kind=turn_kind, cancel_token=turn_cg.host_token)
            )
        else:
            turn_scope = self._container.begin_hot_turn(turn_kind, cancel_token=turn_cg.host_token, turn_id=tid)
            if turn_scope is None and self._container.state == ContainerState.DRAINING and self._gates.has_admitted_rpc_turn(tid):
                turn_scope = TurnScope(turn_id=tid, kind=turn_kind, cancel_token=turn_cg.host_token)
        if turn_scope is None:
            turn_cg.close_all()
            rej = TurnExecutionReport(turn_id=tid, primary_result=StepExecutionResult(ok=False, error=ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, self._draining_or_stopped_message(), source_task=str(tagged_req.task_id))))
            return RawInvokeResult(report_to_outcome(rej, is_hot=is_hot, fallback_task=str(request.task_id)), ())
        detach_caller = turn_cg.try_add_participant(cancel_token)
        cold_shared = prop.cold_shared_workspaces | (frozenset({self._workspace_root}) if (turn_kind == TurnKind.COLD and spec.mutation_scope == SelfMutationScope.NONE) else frozenset())
        spec_dl = (time.monotonic() + ms_to_safe_sec(spec.timeout_ms)) if spec.timeout_ms is not None else None
        deadline = merge_deadlines(turn_guard.deadline if turn_guard is not None else None, spec_dl)
        session = ActiveTurnSession(
            scope=turn_scope, caller_cancel=cancel_token, prio_handle=PriorityHandle(tagged_req.priority),
            on_progress=on_progress, root_call_tree_id=prop.call_tree_id or tid, primary_task_id=str(tagged_req.task_id),
            inherit_call_tree=bool(prop.call_stack), turn_deadline=turn_guard.deadline if turn_guard is not None else None,
            effective_deadline=deadline, hot_workspaces=prop.hot_workspaces, cold_shared_workspaces=cold_shared,
        )
        try:
            with self._sessions.managed_session(session):
                if turn_kind == TurnKind.COLD:
                    post_st = self._container.state
                    if post_st == ContainerState.STOPPED or (post_st == ContainerState.DRAINING and not was_admitted):
                        rej_post = TurnExecutionReport(turn_id=tid, primary_result=StepExecutionResult(ok=False, error=ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, self._draining_or_stopped_message(), source_task=str(tagged_req.task_id))))
                        return RawInvokeResult(report_to_outcome(rej_post, is_hot=False, fallback_task=str(request.task_id)), ())
                report = (
                    self._cold_locks.run_cold_turn(tagged_req, spec, turn_scope, deadline=deadline)
                    if turn_kind == TurnKind.COLD
                    else self._turn_engine.execute_turn(tagged_req, turn_kind, scope=turn_scope)
                )
                inv_snap = self._sessions.snapshot_session_invoked_tasks(session)
        finally:
            if detach_caller is not None:
                detach_caller()
            turn_cg.close_all()
        return RawInvokeResult(report_to_outcome(report, is_hot=is_hot, fallback_task=str(request.task_id)), inv_snap)

    def _execute_single_step_with_coordination(
        self, *, request: InvokeRequest, turn: TurnScope, parent_step_cancel: Optional[CancellationToken] = None,
        parent_prio: Optional[PriorityHandle] = None, parent_deadline: Optional[float] = None,
    ) -> StepExecutionResult[JsonValue]:
        sess = self._sessions.get_or_bind_turn_session(turn)
        self._sessions.record_session_invoked_frame(sess, (request.workspace_root, request.task_id))
        prop = request.propagation
        eff_prog = sess.on_progress if not prop.is_internal_trigger else None
        if not prop.is_nested_call and not prop.is_internal_trigger:
            step_ph, unreg_p = sess.prio_handle, (lambda: None)
        else:
            step_ph = PriorityHandle(parent_prio.current if parent_prio is not None else request.priority)
            unreg_p = parent_prio.register_listener(lambda p: step_ph.elevate_to_foreground() if p == ExecutionPriority.FOREGROUND else None) if parent_prio is not None else (lambda: None)
        try:
            static_outer_dl = merge_deadlines(sess.turn_deadline, parent_deadline)
            eff_outer_dl, step_started = merge_deadlines(sess.current_turn_deadline(), parent_deadline), time.monotonic()
            wait_tok = parent_step_cancel or turn.cancel_token
            pre_found = self._routes.lookup(request.task_id)
            pre_tmo = pre_found[1].timeout_ms if pre_found is not None else None
            pre_guard = DeadlineGuard(cancel_token=wait_tok, deadline=merge_deadlines(eff_outer_dl, (step_started + ms_to_safe_sec(pre_tmo)) if pre_tmo is not None else None))
            try:
                wait_tok.raise_if_cancelled()
                with resolve_active_profiler().scope_relative("Runtime/QuiesceWait"):
                    self._gates.wait_for_unquiesced(request, wait_tok, self._step_host.is_reentrant_retiring, timeout_ms=pre_guard.remaining_ms(pre_tmo))
            except (TaskCancelledException, YscbError) as exc:
                return _failed_step_result(exc.detail, request.task_id, fatal=False)
            gate_err, resolved = self._validate_stage1_gates(request, in_cold_turn=(turn.kind == TurnKind.COLD))
            if gate_err is not None:
                return _failed_step_result(gate_err, request.task_id)
            desc, spec = require_non_none(resolved)
            self._sessions.record_transitive_invoked_tasks(prop, ((request.workspace_root, request.task_id),))
            step_req = replace(request, propagation=replace(prop, call_stack=(*prop.call_stack, (request.workspace_root, request.task_id))))
            step_cancel = CancellationToken()
            parent_cancel = parent_step_cancel if parent_step_cancel is not None else (sess.caller_cancel if not prop.in_event_chain else turn.cancel_token)
            unreg = parent_cancel.register_callback(lambda p, r: step_cancel.cancel(preempted=p, reason=r))
            spec_dl = (step_started + ms_to_safe_sec(spec.timeout_ms)) if spec.timeout_ms is not None else None
            step_env = StepExecutionEnv(
                desc=desc, spec=spec, step_req=step_req, turn=turn, step_cancel=step_cancel, on_progress=eff_prog,
                step_guard=DeadlineGuard(cancel_token=step_cancel, deadline=merge_deadlines(static_outer_dl, spec_dl)),
                dynamic_deadline_fn=sess.turn_deadline_fn,
                reload_epoch=self._gates.current_epoch(desc.module_id),
            )
            step_ok = False
            try:
                res = self._dispatch_parallel_step_safe(step_env, step_ph, step_cancel) if (not spec.resource_key or spec.concurrency_mode == ConcurrencyMode.PARALLEL) else self._coordinate_and_dispatch_step(step_env, step_ph)
                step_ok = res.ok
            finally:
                unreg()
                if not step_ok and not step_cancel.is_cancelled:
                    step_cancel.cancel(reason="Parent step terminated")
            if res.error is not None and res.error.source_task is None:
                return replace(res, error=res.error.with_fallback_task(str(request.task_id)))
            return res
        finally:
            unreg_p()

    def _dispatch_parallel_step_safe(
        self, step_env: StepExecutionEnv, ph: PriorityHandle, step_cancel: CancellationToken,
    ) -> StepExecutionResult[JsonValue]:
        try:
            res, guard_ev = self._step_host.dispatch_to_host(step_env, ph, step_cancel, self._build_tier0_callbacks)
            if guard_ev is not None and not guard_ev.is_set() and step_env.turn.kind == TurnKind.COLD:
                guard_ev.wait(timeout=3.0)
            return res
        except (TaskCancelledException, YscbError) as exc:
            return _failed_step_result(exc.detail, step_env.spec.task_id, fatal=False)
    def _build_tier0_callbacks(self, env: StepExecutionEnv, priority_getter: PriorityHandle) -> StepContextCallbacks:
        step_req, turn = env.step_req, env.turn
        prop = step_req.propagation
        ctree = prop.call_tree_id or turn.turn_id
        return StepContextCallbacks(
            on_emit_imm=lambda eid, ev_raw, imm_lin, strict: self._dispatch_immediate_event(
                _ImmediateEventDispatchSpec(
                    event_id=eid, raw_payload=ev_raw, propagation=replace(prop, call_tree_id=ctree, lineage=imm_lin),
                    strict=strict, emitter_task=env.spec.task_id, parent_step_cancel=env.step_cancel,
                    parent_prio=priority_getter, step_deadline=env.current_guard().deadline,
                ),
                turn,
            ),
            on_invoke_task=lambda c_tid, encoded_in, t_ws, r_pol: self._invoke_nested_within_turn(
                turn,
                _NestedInvokeSpec(
                    child_task_id=c_tid, raw_input=encoded_in, target_workspace=t_ws or self._workspace_root,
                    caller_cwd=step_req.caller_cwd, caller_env=dict(step_req.caller_env),
                    routing_policy=r_pol or default_nested_routing_policy(bool(t_ws and t_ws != self._workspace_root), step_req.routing_policy),
                    priority=priority_getter(), approval_scope=step_req.approval_scope, allow_conditional=step_req.allow_conditional,
                    propagation=replace(prop, call_tree_id=ctree), parent_prio=priority_getter, step_deadline=env.current_guard().deadline,
                ),
                env.step_cancel,
            ),
            on_progress=lambda p: safe_invoke_progress(env.on_progress, p),
        )

    def _run_locked_leader_step(
        self, env: StepExecutionEnv, prio_handle: PriorityHandle, eff_cancel: CancellationToken,
        flight: Optional[StepFlight[_CoordinatedStepBundle]],
    ) -> _CoordinatedStepBundle:
        group_descs = self._routes.collect_group_descriptors(env.desc) if env.desc.venv_python is not None else (env.desc,)
        prop = env.step_req.propagation
        ctree = prop.call_tree_id or env.turn.turn_id
        parent_req = replace(env.step_req, propagation=replace(prop, call_stack=prop.call_stack[:-1]))
        if self._opts.is_daemon_host and (
            self._gates.is_step_blocked_by_reload(parent_req, self._step_host.is_reentrant_retiring)
            or self._gates.current_epoch(env.desc.module_id) != env.reload_epoch
        ):
            return _CoordinatedStepBundle(StepExecutionResult(ok=False), retry_group_busy=True)
        bypass_rel = self._gates.is_request_reload_exempt(parent_req, self._step_host.is_reentrant_retiring)
        if self._tier1_pool.needs_retiring_drain_for_turn(group_descs, env.turn.turn_id, ctree, bypass_rel):
            return _CoordinatedStepBundle(StepExecutionResult(ok=False), retry_group_busy=True)
        if flight is None:
            try:
                res, guard_ev = self._step_host.dispatch_to_host(env, prio_handle, eff_cancel, self._build_tier0_callbacks, forbid_retiring_wait=True)
            except RetiringGroupBusyError:
                return _CoordinatedStepBundle(StepExecutionResult(ok=False), retry_group_busy=True)
            return _CoordinatedStepBundle(step_result=res, release_guard=guard_ev)
        return self._run_neutral_coalesce_flight(env, prio_handle, eff_cancel, flight)

    def _run_neutral_coalesce_flight(
        self, env: StepExecutionEnv, prio_handle: PriorityHandle, eff_cancel: CancellationToken,
        flight: StepFlight[_CoordinatedStepBundle],
    ) -> _CoordinatedStepBundle:
        flight_tid = flight.flight_id
        step_exec_cancel, unreg_flight_cancel = CancellationToken.combine(eff_cancel)
        flight_scope = TurnScope(turn_id=flight_tid, kind=env.turn.kind, cancel_token=step_exec_cancel)
        hot_ws = frozenset({self._workspace_root}) if self._opts.is_daemon_host else frozenset()
        cold_ws = frozenset({self._workspace_root}) if not self._opts.is_daemon_host else frozenset()
        flight_sess = ActiveTurnSession(
            scope=flight_scope, caller_cancel=step_exec_cancel, prio_handle=prio_handle,
            root_call_tree_id=flight_tid, primary_task_id=str(env.spec.task_id),
            hot_workspaces=hot_ws, cold_shared_workspaces=cold_ws,
        )
        neutral_prop = CallPropagationContext(
            turn_id=flight_tid, call_tree_id=flight_tid, call_stack=((env.step_req.workspace_root, env.spec.task_id),),
            is_nested_call=False, from_hot_container=self._opts.is_daemon_host, hot_workspaces=hot_ws, cold_shared_workspaces=cold_ws,
            profile_mem=env.step_req.propagation.profile_mem,
        )
        exec_env = replace(
            env, turn=flight_scope, step_req=replace(env.step_req, propagation=neutral_prop), on_progress=flight.broadcast_progress,
            step_guard=DeadlineGuard(cancel_token=step_exec_cancel, deadline=None), dynamic_deadline_fn=flight.effective_deadline,
        )
        step_td: tuple[ErrorDetail, ...] = ()
        try:
            with self._sessions.managed_session(flight_sess):
                try:
                    res, guard_ev = self._step_host.dispatch_to_host(exec_env, prio_handle, step_exec_cancel, self._build_tier0_callbacks, forbid_retiring_wait=True)
                    nested_ev = self._sessions.drain_session_nested_events(flight_sess)
                    if not res.fatal_abort_turn and nested_ev:
                        res = replace(res, committed_events=(*nested_ev, *res.committed_events))
                    inv_tasks = self._sessions.snapshot_session_invoked_tasks(flight_sess)
                finally:
                    step_td = flight_scope.scoped_stack.close_all_lifo()
        except RetiringGroupBusyError:
            flight.seal()
            return _CoordinatedStepBundle(StepExecutionResult(ok=False), flight=flight, retry_group_busy=True)
        finally:
            unreg_flight_cancel()
            imm_diags = flight_scope.snapshot_event_diagnostics()
            flight.seal()
        return _CoordinatedStepBundle(
            step_result=res, flight=flight, imm_diagnostics=imm_diags, step_td_diags=step_td, invoked_tasks=inv_tasks, release_guard=guard_ev,
        )

    def _drain_flight_step5(
        self, flight_id: str, turn_kind: TurnKind, prio_handle: PriorityHandle,
        seed_events: tuple[RawEventRecord, ...], drain_cancel: CancellationToken, deadline_fn: Callable[[], Optional[float]],
    ) -> TurnExecutionReport:
        tid = f"{flight_id}_step5"
        scope = TurnScope(turn_id=tid, kind=turn_kind, cancel_token=drain_cancel)
        hot_ws = frozenset({self._workspace_root}) if self._opts.is_daemon_host else frozenset()
        sess = ActiveTurnSession(
            scope=scope, caller_cancel=drain_cancel, prio_handle=prio_handle,
            hot_workspaces=hot_ws, turn_deadline_fn=deadline_fn,
        )
        with self._gates.register_draining_exempt_turn(tid), self._sessions.managed_session(sess):
            return self._turn_engine.execute_event_turn(scope, seed_events)

    def _recheck_hot_step_before_coord(
        self, env: StepExecutionEnv, ext_prio: PriorityHandle,
    ) -> tuple[StepExecutionEnv, Optional[StepExecutionResult[JsonValue]]]:
        prop = env.step_req.propagation
        parent_req = replace(env.step_req, propagation=replace(prop, call_stack=prop.call_stack[:-1]))
        env.step_cancel.raise_if_cancelled()
        self._gates.wait_for_unquiesced(parent_req, env.step_cancel, self._step_host.is_reentrant_retiring, timeout_ms=env.current_guard().remaining_ms(env.spec.timeout_ms))
        gate_err, resolved = self._validate_stage1_gates(parent_req, in_cold_turn=(env.turn.kind == TurnKind.COLD))
        if gate_err is not None:
            return (env, _failed_step_result(gate_err, env.spec.task_id))
        new_desc, new_spec = require_non_none(resolved)
        cur_ep = self._gates.current_epoch(new_desc.module_id)
        if new_desc == env.desc and new_spec == env.spec and cur_ep == env.reload_epoch:
            return (env, None)
        next_env = replace(env, desc=new_desc, spec=new_spec, reload_epoch=cur_ep)
        if not next_env.spec.resource_key or next_env.spec.concurrency_mode == ConcurrencyMode.PARALLEL:
            return (next_env, self._dispatch_parallel_step_safe(next_env, ext_prio, next_env.step_cancel))
        return (next_env, None)
    def _finalize_coalesce_post_step(
        self, env: StepExecutionEnv, bundle: _CoordinatedStepBundle, coord: CoordinatedExecution[_CoordinatedStepBundle],
    ) -> StepExecutionResult[JsonValue]:
        flight = require_non_none(bundle.flight)
        try:
            if bundle.step_result.fatal_abort_turn or not bundle.step_result.committed_events:
                return replace(bundle.step_result, coalesced=coord.is_follower)
            sess = self._sessions.get_or_bind_turn_session(env.turn)
            eff_dl = sess.effective_deadline if sess.effective_deadline is not None else sess.current_turn_deadline()
            rem_sec = max(0.0, eff_dl - time.monotonic()) if eff_dl is not None else None
            seed_events = bundle.step_result.committed_events
            try:
                post_raw = flight.run_or_await_post_step(
                    coord.caller_slot_id, env.turn.cancel_token, rem_sec,
                    lambda drain_c, dl_fn: self._drain_flight_step5(
                        flight.flight_id, env.turn.kind, flight.priority_handle, seed_events, drain_c, dl_fn
                    ),
                )
            except (TaskCancelledException, YscbError) as exc:
                return _failed_step_result(exc.detail, env.spec.task_id, coalesced=coord.is_follower, fatal=False)
            if isinstance(post_raw, TurnExecutionReport):
                for diag in post_raw.event_diagnostics:
                    env.turn.record_event_diagnostic(diag)
                self._sessions.record_step_teardown_diags(env.turn, post_raw.teardown_diagnostics)
                if post_raw.fatal_event_error is not None:
                    return _failed_step_result(post_raw.fatal_event_error, env.spec.task_id, coalesced=coord.is_follower, fatal=True)
            return replace(bundle.step_result, committed_events=(), coalesced=coord.is_follower)
        finally:
            flight.detach_post_step(coord.caller_slot_id)

    def _coordinate_and_dispatch_step(self, env: StepExecutionEnv, ext_prio: PriorityHandle) -> StepExecutionResult[JsonValue]:
        _ = require_non_none(env.spec.resource_key)
        prop = env.step_req.propagation
        allow_coalesce = (env.turn.kind != TurnKind.COLD) and not prop.is_nested_call and not prop.call_stack[:-1] and not prop.in_event_chain
        group_descs: Sequence[ModuleDescriptor] = tuple(self._routes.collect_group_descriptors(env.desc)) if env.desc.venv_python is not None else (env.desc,)
        equiv_key: Optional[str] = None
        while True:
            try:
                if self._opts.is_daemon_host:
                    next_env, early_res = self._recheck_hot_step_before_coord(env, ext_prio)
                    if early_res is not None:
                        return early_res
                    if next_env is not env:
                        env, equiv_key = next_env, None
                        group_descs = tuple(self._routes.collect_group_descriptors(env.desc)) if env.desc.venv_python is not None else (env.desc,)
                coord, equiv_key = self._acquire_single_coord_attempt(env, group_descs, allow_coalesce, equiv_key, ext_prio)
            except TaskCancelledException as exc:
                return _failed_step_result(exc.detail, env.spec.task_id, fatal=False)
            except YscbError as exc:
                return _failed_step_result(exc.detail, env.spec.task_id)
            bundle = require_non_none(coord.outcome)
            if bundle.retry_group_busy:
                if bundle.flight is not None:
                    bundle.flight.detach_post_step(coord.caller_slot_id)
                try:
                    env.step_cancel.raise_if_cancelled()
                    env.current_guard().remaining_ms(None, expired_message="Timed out waiting for retiring worker group.")
                except TaskCancelledException as exc:
                    return _failed_step_result(exc.detail, env.spec.task_id, fatal=False)
                except YscbError as exc:
                    return _failed_step_result(exc.detail, env.spec.task_id)
                env.step_cancel.wait(0.005)
                continue
            if bundle.invoked_tasks:
                self._sessions.record_transitive_invoked_tasks(env.step_req.propagation, bundle.invoked_tasks)
            for diag in bundle.imm_diagnostics:
                self._sessions.record_imm_or_turn_diagnostic(env.turn, diag)
            if bundle.step_td_diags:
                self._sessions.record_step_teardown_diags(env.turn, bundle.step_td_diags)
            if bundle.flight is None:
                return replace(bundle.step_result, coalesced=coord.is_follower)
            return self._finalize_coalesce_post_step(env, bundle, coord)

    def _acquire_single_coord_attempt(
        self, env: StepExecutionEnv, group_descs: Sequence[ModuleDescriptor],
        allow_coalesce: bool, equiv_key: Optional[str], ext_prio: PriorityHandle,
    ) -> tuple[CoordinatedExecution[_CoordinatedStepBundle], str]:
        prop = env.step_req.propagation
        ctree = prop.call_tree_id or env.turn.turn_id
        parent_req = replace(env.step_req, propagation=replace(prop, call_stack=prop.call_stack[:-1]))
        bypass_rel = self._gates.is_request_reload_exempt(parent_req, self._step_host.is_reentrant_retiring)
        q_pre = self._gates.has_leased_pre_quiesce(env.turn.turn_id, ctree)
        eff_allow = allow_coalesce and not bypass_rel and not q_pre
        env.step_cancel.raise_if_cancelled()
        cur_guard = env.current_guard()
        self._tier1_pool.await_group_ready_before_lock(
            group_descs, turn_id=env.turn.turn_id, call_tree_id=ctree, bypass_reload=bypass_rel,
            cancel_token=env.step_cancel, timeout_ms=cur_guard.remaining_ms(env.spec.timeout_ms),
        )
        need_equiv = env.spec.concurrency_mode == ConcurrencyMode.COALESCE and eff_allow
        eff_eq = equiv_key or (
            self._step_host.compute_isolated_equiv_key(parent_req, EquivCallContext(env.turn, ctree, False, env.step_cancel, bypass_rel, cur_guard))
            if need_equiv else f"{env.spec.task_id}:direct"
        )
        acq_spec = ResourceAcquireSpec(
            resource_key=env.spec.resource_key, mode=env.spec.concurrency_mode, equiv_key=eff_eq,
            priority=env.step_req.priority, turn_id=env.turn.turn_id, call_stack=prop.call_stack,
            cancel_token=env.step_cancel, turn_cancel_token=env.turn.cancel_token,
            timeout_ms=cur_guard.remaining_ms(env.spec.timeout_ms), external_priority_handle=ext_prio,
            allow_step_coalesce=eff_allow, call_tree_id=ctree, in_event_chain=prop.in_event_chain, on_progress=env.on_progress,
        )
        coord = self._coordinator.execute(
            acq_spec, lambda ph, tok, fl: self._run_locked_leader_step(env, ph, tok, fl), extract_release_guard=lambda b: b.release_guard,
        )
        return (coord, eff_eq)
    def _invoke_nested_within_turn(
        self, turn: Optional[TurnScope], spec: _NestedInvokeSpec, cancel_token: CancellationToken,
    ) -> TaskOutcome[JsonValue]:
        is_cross_ws, prop = spec.target_workspace != self._workspace_root, spec.propagation
        eff_tid = turn.turn_id if turn is not None else (prop.turn_id or "")
        ext_route = (
            True if (is_cross_ws or turn is None)
            else (False if (turn.kind != TurnKind.COLD or self._opts.is_daemon_host or spec.routing_policy != ClientRoutingPolicy.STRICT_HOT) else True)
        )
        strip_scope = is_cross_ws or prop.in_event_chain
        nested_prop = CallPropagationContext(
            turn_id=None if ext_route else (turn.turn_id if turn is not None else None),
            call_tree_id=prop.call_tree_id or (turn.turn_id if turn is not None else None),
            call_stack=prop.call_stack, lineage=prop.lineage, is_internal_trigger=False, is_nested_call=not ext_route,
            in_event_chain=prop.in_event_chain, from_hot_container=False if ext_route else self._opts.is_daemon_host,
            hot_workspaces=prop.hot_workspaces, cold_shared_workspaces=prop.cold_shared_workspaces,
            profile_mem=prop.profile_mem,
        )
        try:
            nested_req = InvokeRequest(
                task_id=spec.child_task_id, raw_input=spec.raw_input, workspace_root=spec.target_workspace,
                caller_cwd=spec.caller_cwd, caller_env=spec.caller_env, routing_policy=spec.routing_policy,
                priority=spec.parent_prio.current if spec.parent_prio is not None else spec.priority,
                approval_scope=frozenset() if strip_scope else spec.approval_scope,
                allow_conditional=spec.allow_conditional, propagation=nested_prop,
                profile_mem=prop.profile_mem,
                active_profiler=resolve_active_profiler() if ext_route else None,
            )
            validate_wire_json_object(nested_req.raw_input, max_depth=MAX_USER_JSON_DEPTH, label="InvokeRequest.raw_input")
        except (TypeError, ValueError) as exc:
            err = ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, safe_exception_summary(exc), source_task=str(spec.child_task_id))
            return TaskOutcome(ok=False, error=err, executed_hot=False if is_cross_ws else self._opts.is_daemon_host)
        self._sessions.record_transitive_invoked_tasks(replace(prop, turn_id=eff_tid or None), ((nested_req.workspace_root, nested_req.task_id),))
        if ext_route or turn is None:
            raw_res = self._invoke_raw(nested_req, cancel_token=cancel_token, turn_guard=DeadlineGuard(cancel_token=cancel_token, deadline=spec.step_deadline))
            out = raw_res.outcome
            if not out.ok and out.error is not None and is_fatal_error_code(out.error.code):
                out.error.raise_as_exception()
            return out
        found = self._routes.lookup(nested_req.task_id, ensure_ready=True)
        if turn.kind != TurnKind.COLD or found is None or found[1].mutation_scope == SelfMutationScope.NONE:
            step_res = self._execute_single_step_with_coordination(
                request=nested_req, turn=turn, parent_step_cancel=cancel_token, parent_prio=spec.parent_prio, parent_deadline=spec.step_deadline,
            )
        else:
            gate_err, _ = self._validate_stage1_gates(nested_req, in_cold_turn=True)
            if gate_err is not None:
                step_res = StepExecutionResult(ok=False, error=gate_err, fatal_abort_turn=is_fatal_error_code(gate_err.code))
            else:
                nested_prop2 = nested_req.propagation
                excl_req = replace(nested_req, propagation=replace(nested_prop2, cold_shared_workspaces=nested_prop2.cold_shared_workspaces - frozenset({self._workspace_root})))
                step_res = self._cold_locks.run_upgraded_nested(
                    nested_prop2.call_tree_id or turn.turn_id, nested_req.task_id, cancel_token,
                    lambda: self._execute_single_step_with_coordination(
                        request=excl_req, turn=turn, parent_step_cancel=cancel_token, parent_prio=spec.parent_prio, parent_deadline=spec.step_deadline,
                    ),
                    deadline=spec.step_deadline,
                )
        if not step_res.fatal_abort_turn and step_res.committed_events:
            self._sessions.record_nested_committed_events(turn, step_res.committed_events)
        if step_res.fatal_abort_turn and step_res.error is not None:
            step_res.error.raise_as_exception()
        return TaskOutcome(ok=step_res.ok, value=step_res.outcome, error=step_res.error, coalesced=step_res.coalesced, executed_hot=self._opts.is_daemon_host)

    def _dispatch_immediate_event(self, spec: _ImmediateEventDispatchSpec, turn: TurnScope) -> None:
        if spec.parent_step_cancel is not None:
            spec.parent_step_cancel.raise_if_cancelled()
        sess = self._sessions.get_or_bind_turn_session(turn)
        batch = EventBatchEnvelope(event_id=spec.event_id, ordering=EventOrdering.ORDERED, payloads=(spec.raw_payload,), merged_lineage=spec.propagation.lineage)
        eff_ph = spec.parent_prio or PriorityHandle(ExecutionPriority.BACKGROUND if turn.kind == TurnKind.HOT_BACKGROUND else ExecutionPriority.FOREGROUND)
        for m in self._routes.find_matching_subscribers(spec.event_id):
            if spec.parent_step_cancel is not None and spec.parent_step_cancel.is_cancelled:
                spec.parent_step_cancel.raise_if_cancelled()
            if turn.kind == TurnKind.COLD and m.spec.dispatch_mode == DispatchMode.DAEMON_ONLY:
                continue
            filtered, _ = batch.filter_for_subscription(m.sub.payload_filter)
            if filtered:
                self._run_single_immediate_subscriber(m.desc, m.spec, spec, filtered, eff_ph, sess)

    def _fail_or_record_imm_subscriber(self, spec: _ImmediateEventDispatchSpec, turn: TurnScope, sub_task_id: TaskId, err: ErrorDetail) -> None:
        det = err.with_fallback_task(str(sub_task_id))
        if spec.strict:
            det.raise_as_exception()
        if det.code == ErrorCode.TASK_PREEMPTED:
            return
        if det.code == ErrorCode.TASK_CANCELLED and (turn.cancel_token.is_cancelled or (spec.parent_step_cancel is not None and spec.parent_step_cancel.is_cancelled)):
            return
        self._sessions.record_imm_or_turn_diagnostic(turn, det)

    def _run_single_immediate_subscriber(
        self, desc: ModuleDescriptor, route_spec: TaskRouteSpec, spec: _ImmediateEventDispatchSpec,
        filtered: tuple[JsonObject, ...], eff_ph: PriorityHandle, sess: ActiveTurnSession,
    ) -> None:
        turn, prop = sess.scope, spec.propagation
        eff_ctree = prop.call_tree_id or turn.turn_id
        eff_tok = spec.parent_step_cancel or turn.cancel_token
        imm_dl = merge_deadlines(sess.current_turn_deadline(), spec.step_deadline)
        imm_guard = DeadlineGuard(cancel_token=eff_tok, deadline=imm_dl)
        sub_err, skip, mapped_req = self._prepare_and_map_subscriber(
            desc, route_spec, turn, eff_ctree, eff_ph.current, replace(prop, is_nested_call=True),
            spec.event_id, filtered, eff_tok, spec.parent_step_cancel, imm_guard,
        )
        if sub_err is not None:
            self._fail_or_record_imm_subscriber(spec, turn, route_spec.task_id, sub_err)
            return
        if skip:
            return
        sub_res = self._execute_single_step_with_coordination(
            request=mapped_req, turn=turn, parent_step_cancel=spec.parent_step_cancel, parent_prio=eff_ph, parent_deadline=spec.step_deadline,
        )
        if sub_res.fatal_abort_turn and sub_res.error is not None:
            sub_res.error.raise_as_exception()
        if spec.parent_step_cancel is not None and spec.parent_step_cancel.is_cancelled:
            spec.parent_step_cancel.raise_if_cancelled()
        if not sub_res.fatal_abort_turn and sub_res.committed_events:
            self._sessions.record_nested_committed_events(turn, sub_res.committed_events)
        if not sub_res.ok and sub_res.error is not None:
            if spec.strict:
                sub_res.error.with_fallback_task(str(route_spec.task_id)).raise_as_exception()
            if not sub_res.preempted:
                self._fail_or_record_imm_subscriber(spec, turn, route_spec.task_id, sub_res.error)
