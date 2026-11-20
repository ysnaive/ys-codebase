"""Single-point RuntimeDispatcher unifying Cold/Hot turns, symmetric COALESCE cascades, and Tier 0/1 hosts."""

from __future__ import annotations

from dataclasses import dataclass, replace
import threading
import time
from typing import Callable, Optional, Sequence, TypeVar, overload
import uuid

from core.execution.event import (
    CausalLineage,
    EventBatchEnvelope,
    EventOrdering,
    RawEventRecord,
    ScopedHop,
    hop_conflicts,
)
from core.execution.lifecycle import (
    ContainerState,
    StepExecutionResult,
    TaskStepExecutor,
    TurnEngine,
    TurnExecutionReport,
    TurnKind,
    TurnScope,
    WorkerContainerLifecycle,
)
from core.execution.rpc import (
    DaemonConnectionConfig,
    PersistentRpcSession,
    RemoteCallOutcome,
    call_ephemeral_daemon_rpc,
)
from core.execution.runtime.contracts import (
    CONFIG_CHANGED_EVENT_ID,
    CORE_MODULE_ID,
    DEFAULT_CACHE_DIRNAME,
    WATCHER_TASK_ID,
    CallPropagationContext,
    ClientRoutingPolicy,
    CoalesceCallerView,
    ConcurrencyMode,
    ConfigViewPort,
    DaemonSpawner,
    DispatchMode,
    ExecutionPriority,
    CoordinatorPort,
    InvokeRequest,
    ModuleDescriptor,
    Tier1WorkerPool,
    ModuleProviderPort,
    SelfMutationScope,
    TaskMetadata,
    TaskOutcome,
    TaskRouteSpec,
    decode_outcome_as,
    sanitize_caller_env,
)
from core.execution.runtime.coordinator import (
    CoordinatedExecution,
    LiveFlightParticipant,
    PriorityHandle,
    ResourceAcquireSpec,
    ResourceCoordinator,
    SharedCancelGroup,
    StepFlight,
)
from core.execution.runtime.gates import (
    ColdInstallerLockManager,
    ConfigFingerprintTracker,
    LifecycleReloadGate,
    QuiesceResumeResult,
    SharedWorkspaceState,
    expand_colocated_tier1_siblings,
    normalize_drain_deadline,
    validate_stage1_gates,
)
from core.execution.runtime.lineage_join import (
    CascadeOutcome,
    FlightCascade,
    StepEventCapture,
    advance_hops_checked,
    extract_emitted_hops_from_records,
)
from core.execution.runtime.module_slot import LocalModuleSlotRegistry, StepContextCallbacks
from core.execution.runtime.route_index import RouteIndexRegistry
from core.execution.runtime.step_host import (
    EquivCallContext,
    RawInvokeResult,
    StepExecutionEnv,
    StepHostRunner,
    WorkerCallbackBridge,
    cancelled_task_outcome,
    default_nested_routing_policy,
    report_to_outcome,
    safe_invoke_progress,
    translate_remote_daemon_outcome,
)
from core.execution.runtime.turn_session import (
    ActiveTurnSession,
    TurnSessionRegistry,
    abort_remaining_attached,
    record_unique_emitted_hops,
    filter_and_advance_coalesce_views,
    find_common_view_conflicting_hop,
    first_caller_hop_cycle,
    live_session_coalesce_views,
    merge_deadlines,
)
from core.execution.runtime.wire import (
    DaemonRpcInvokeEnvelope,
    DaemonRpcInvokeReply,
    EmittedEventHop,
    WorkerCallbackEnvelope,
    WorkerCallbackKind,
    WorkerCallbackReply,
    WorkerWarmupReply,
)
from core.execution.runtime.worker_pool import (
    HotWorkerPool,
    PoolHostCallbacks,
    RetiringGroupBusyError,
    tier1_group_key_for,
)
from core.filesystem.fs import resolve_contained_subpath
from core.foundation.codec import DataclassCodec
from core.foundation.errors import (
    is_fatal_error_code,
    CallCycleError,
    ErrorCode,
    ErrorDetail,
    EventCycleError,
    TaskCancelledException,
    YscbError,
    safe_exception_summary,
)
from core.foundation.observability import (
    MAX_TIMEOUT_MS,
    CancellationToken,
    DeadlineGuard,
    ms_to_safe_sec,
)
from core.foundation.primitives import (
    require_pure_int,
    MAX_USER_JSON_DEPTH,
    EventId,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    TaskId,
    require_non_none,
    require_pure_str,
    require_typed_frozenset,
    validate_wire_json_object,
)

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


def _validate_daemon_spawner_port(sp: DaemonSpawner) -> None:
    try:
        c1, c2 = sp.can_spawn_in_environment, sp.try_spawn_background
    except AttributeError as exc:
        raise ValueError(f"Invalid DaemonSpawner: {sp!r}") from exc
    if not callable(c1) or not callable(c2):
        raise ValueError(f"Invalid DaemonSpawner methods on {sp!r}")


def _validate_config_view_port(cv: ConfigViewPort) -> None:
    try:
        m1, m2, m3 = cv.get_module_value, cv.fingerprint, cv.reload
    except AttributeError as exc:
        raise ValueError(f"Invalid ConfigViewPort: {cv!r}") from exc
    if not callable(m1) or not callable(m2) or not callable(m3):
        raise ValueError(f"Invalid ConfigViewPort methods on {cv!r}")


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

    def __post_init__(self) -> None:
        if self.config_view is not None:
            _validate_config_view_port(self.config_view)
        if self.daemon_spawner is not None:
            _validate_daemon_spawner_port(self.daemon_spawner)
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


@dataclass(slots=True)
class _CoordinatedStepBundle:
    step_result: StepExecutionResult[JsonValue]
    cascade: Optional[FlightCascade] = None
    needs_lineage_rebase: bool = False
    inline_imm_hops: tuple[EmittedEventHop, ...] = ()
    inline_imm_diags: tuple[ErrorDetail, ...] = ()
    inline_td_diags: tuple[ErrorDetail, ...] = ()
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
    parent_prio: Optional[PriorityHandle] = None
    step_deadline: Optional[float] = None


@dataclass(frozen=True, slots=True)
class _ImmediateEventDispatchSpec:
    event_id: EventId
    raw_payload: JsonObject
    propagation: CallPropagationContext
    strict: bool
    emitter_task: Optional[TaskId] = None
    parent_step_cancel: Optional[CancellationToken] = None
    parent_prio: Optional[PriorityHandle] = None
    step_deadline: Optional[float] = None


def _check_caller_invoked_cycle(
    caller_ancestors: tuple[tuple[HostPath, TaskId], ...],
    coalesce_callers: Sequence[CoalesceCallerView],
    invoked_tasks: Sequence[tuple[HostPath, TaskId]],
) -> Optional[ErrorDetail]:
    anc_set = set(caller_ancestors)
    view_sets = tuple(set(v.call_stack) for v in coalesce_callers)
    for inv_frame in invoked_tasks:
        if inv_frame in anc_set:
            chain_str = " -> ".join(f"{tid}" for _ws, tid in (*caller_ancestors, inv_frame))
            return CallCycleError(
                f"Synchronous task call cycle detected: {chain_str}",
                source_task=str(inv_frame[1]),
            ).detail
        if view_sets and all(inv_frame in vs for vs in view_sets):
            ref_s = coalesce_callers[0].call_stack
            chain_str = " -> ".join(f"{tid}" for _ws, tid in (*ref_s, inv_frame))
            return CallCycleError(
                f"Synchronous task call cycle detected: {chain_str}",
                source_task=str(inv_frame[1]),
            ).detail
    return None


def _collect_fatal_bundle_hops(
    imm_hops: dict[ScopedHop, EmittedEventHop],
    seeds: Sequence[RawEventRecord],
) -> tuple[EmittedEventHop, ...]:
    merged = dict(imm_hops)
    record_unique_emitted_hops(merged, extract_emitted_hops_from_records(seeds))
    return tuple(merged.values())


def _wire_flight_cascade(
    seeds: tuple[RawEventRecord, ...],
    capture: StepEventCapture,
    td_diags: tuple[ErrorDetail, ...],
    prio_handle: PriorityHandle,
    live_callers: list[LiveFlightParticipant],
) -> FlightCascade:
    cascade = FlightCascade(
        seed_events=seeds,
        imm_hops=tuple(capture.imm_hops.values()),
        imm_diagnostics=capture.imm_diagnostics,
        seed_teardown_diagnostics=td_diags,
        initial_priority=prio_handle.current,
        graph_cond=capture.graph_cond,
    )
    for cj in capture.child_joins:
        cascade.add_child_join(cj.rel_hops, cj.cascade)
    cascade.add_cleanup(
        prio_handle.register_listener(
            lambda p: cascade.prio_handle.elevate_to_foreground() if p == ExecutionPriority.FOREGROUND else None
        )
    )
    cascade.register_caller_slots(live_callers, prio_handle.current)
    for cj in capture.child_joins:
        cj.cascade.detach_caller_slot(cj.slot_id)
    return cascade


def _build_coalesce_flight_bundle(
    res: StepExecutionResult[JsonValue],
    guard_ev: Optional[threading.Event],
    capture: StepEventCapture,
    flight: StepFlight[_CoordinatedStepBundle],
    prio_handle: PriorityHandle,
    td_diags: tuple[ErrorDetail, ...],
) -> _CoordinatedStepBundle:
    seeds = (*capture.deferred_events, *res.committed_events)
    inv_tuple = tuple(capture.invoked_tasks.keys())
    has_work = bool(seeds or capture.imm_hops or capture.imm_diagnostics or capture.child_joins or td_diags)
    detach_children = False

    def _on_sealed(
        live_callers: list[LiveFlightParticipant],
        total_admitted: int,
    ) -> tuple[_CoordinatedStepBundle, Optional[Callable[[int], None]]]:
        nonlocal detach_children
        if res.fatal_abort_turn or not live_callers or not has_work:
            detach_children = bool(capture.child_joins)
            f_hops = _collect_fatal_bundle_hops(capture.imm_hops, seeds) if res.fatal_abort_turn else ()
            f_diags = tuple(capture.imm_diagnostics) if res.fatal_abort_turn else ()
            return (
                _CoordinatedStepBundle(
                    step_result=replace(res, committed_events=()),
                    inline_imm_hops=f_hops,
                    inline_imm_diags=f_diags,
                    inline_td_diags=td_diags,
                    invoked_tasks=inv_tuple,
                    release_guard=guard_ev,
                ),
                None,
            )
        if total_admitted == 1 and len(live_callers) == 1 and not capture.child_joins:
            return (
                _CoordinatedStepBundle(
                    step_result=replace(res, committed_events=seeds),
                    needs_lineage_rebase=True,
                    inline_imm_hops=tuple(capture.imm_hops.values()),
                    inline_imm_diags=tuple(capture.imm_diagnostics),
                    inline_td_diags=td_diags,
                    invoked_tasks=inv_tuple,
                    release_guard=guard_ev,
                ),
                None,
            )
        cascade = _wire_flight_cascade(seeds, capture, td_diags, prio_handle, live_callers)
        b_out = _CoordinatedStepBundle(
            replace(res, committed_events=()), cascade=cascade, invoked_tasks=inv_tuple, release_guard=guard_ev
        )
        return (b_out, cascade.detach_caller_slot)

    bundle = flight.seal_and_finalize(_on_sealed)
    if detach_children:
        for cj in capture.child_joins:
            cj.cascade.detach_caller_slot(cj.slot_id)
    return bundle


def _compute_post_reload_targets(
    reload_all: bool,
    base_mods: frozenset[ModuleId],
    gated_mods: frozenset[ModuleId],
    fresh_descs: Sequence[ModuleDescriptor],
) -> tuple[frozenset[ModuleId], frozenset[ModuleId]]:
    fresh_ids = frozenset(d.module_id for d in fresh_descs if d.module_id != CORE_MODULE_ID)
    post_exp = expand_colocated_tier1_siblings(base_mods, fresh_descs)
    now_mods = fresh_ids if reload_all else ((gated_mods | post_exp) & fresh_ids)
    extra_siblings = (now_mods - gated_mods) if not reload_all else frozenset()
    return (now_mods, extra_siblings)


def _should_shutdown_ephemeral_child(parent: RuntimeDispatcher, child_disp: RuntimeDispatcher, owns_flag: bool) -> bool:
    return (
        owns_flag
        and child_disp is not parent
        and not child_disp.is_daemon_host
        and child_disp.container_lifecycle.state == ContainerState.UNINITIALIZED
        and child_disp.active_turn_count == 0
    )


def _make_peer_cache_resolver(
    parent: RuntimeDispatcher,
    opts: DispatcherHostOptions,
) -> Callable[[HostPath], HostPath]:
    memo_lock = threading.Lock()
    memo: dict[str, HostPath] = {}

    def _resolve(ws_root: HostPath) -> HostPath:
        if opts.peer_cache_dir_resolver is not None:
            return opts.peer_cache_dir_resolver(ws_root)
        ws_key = ws_root.comparison_key
        with memo_lock:
            cached = memo.get(ws_key)
        if cached is not None:
            return cached
        if opts.child_dispatcher_factory is None:
            return resolve_contained_subpath(ws_root, DEFAULT_CACHE_DIRNAME)
        peer_disp = opts.child_dispatcher_factory(ws_root)
        try:
            resolved = peer_disp.cache_dir
        finally:
            if _should_shutdown_ephemeral_child(parent, peer_disp, opts.owns_child_dispatchers):
                peer_disp.shutdown(grace_ms=0)
        with memo_lock:
            memo.setdefault(ws_key, resolved)
        return resolved

    return _resolve


class RuntimeDispatcher(TaskStepExecutor[InvokeRequest]):
    """Single-point orchestrator executing the invocation pipeline across Cold/Hot and Tier 0/1."""

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
        self._cfg_tracker = ConfigFingerprintTracker(options.config_view)
        self._gates = LifecycleReloadGate(workspace_root)
        self._container = WorkerContainerLifecycle(quiesce_probe=self._gates.has_any_quiesced)
        quiesce_pred = self._gates.is_module_quiesced if options.is_daemon_host else None
        self._tier0_slots = LocalModuleSlotRegistry(
            workspace_root, self._container.resource_stack, container=self._container,
            is_module_quiesced=quiesce_pred, require_eager_start=options.is_daemon_host,
        )
        self._routes = RouteIndexRegistry(
            cache_dir=cache_dir, is_daemon_host=options.is_daemon_host, module_provider=module_provider,
            tier0_slots=self._tier0_slots, container=self._container, gates=self._gates,
        )
        self._callback_bridge = WorkerCallbackBridge(self._handle_worker_callback)
        self._bind_lock = threading.RLock()
        self._shared_ws = SharedWorkspaceState()
        self._sessions = TurnSessionRegistry(
            workspace_root=workspace_root, module_provider=module_provider, tier0_slots=self._tier0_slots,
            callback_bridge=self._callback_bridge, shared_ws_getter=lambda: self._shared_ws,
        )
        self._tier1_pool = HotWorkerPool(
            workspace_root, self._callback_bridge, lifo_stack=self._container.resource_stack,
            host_callbacks=PoolHostCallbacks(
                on_warmup_reply=self._apply_tier1_warmup_reply,
                on_module_crashed=self._container.record_degraded,
                is_module_degraded=lambda m: self._container.get_degraded(m) is not None,
                is_module_quiesced=quiesce_pred,
                is_group_reloading=self._gates.any_descriptor_reloading,
                resolve_group_descriptors=self._routes.resolve_fresh_group_descriptors,
                on_teardown_diagnostics=self._sessions.record_host_teardown_diags,
            ),
        )
        self._gates.register_gate_listener(self._tier1_pool.notify_gate_changed)
        self._step_host = StepHostRunner(
            is_daemon_host=options.is_daemon_host, tier1_pool=self._tier1_pool, container=self._container,
            gates=self._gates, routes=self._routes, sessions=self._sessions,
        )
        self._coordinator = ResourceCoordinator(
            cache_dir=cache_dir,
            workspace_root=workspace_root,
            resolve_cache_dir=_make_peer_cache_resolver(self, self._opts),
            is_daemon_host=self._opts.is_daemon_host,
        )
        self._turn_engine: TurnEngine[InvokeRequest] = TurnEngine(self)
        self._cold_locks = ColdInstallerLockManager(
            workspace_root, cache_dir, self._turn_engine, self._cold_bootstrap_hook,
        )
        self._bind_shared_coordinators(self._shared_ws)
        self._force_drain = threading.Event()
        self._routes.init_index()

    @property
    def is_daemon_host(self) -> bool:
        return self._opts.is_daemon_host

    def _bind_shared_coordinators(self, shared_ws: SharedWorkspaceState) -> None:
        ws_key = self._workspace_root.comparison_key
        with self._bind_lock:
            with shared_ws.guard:
                if self._shared_ws is shared_ws and ws_key in shared_ws.cache_dirs_by_ws:
                    return
                shared_ws.captures_by_ws.setdefault(ws_key, [])
                shared_ws.cache_dirs_by_ws[ws_key] = self._cache_dir
                self._shared_ws = shared_ws
                self._coordinator = self._cold_locks.bind_shared(shared_ws, self._coordinator)

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

    def drain_teardown_diagnostics(self) -> tuple[ErrorDetail, ...]:
        return self._sessions.drain_teardown_diagnostics()

    def expand_quiesce_targets(self, modules: frozenset[ModuleId]) -> frozenset[ModuleId]:
        if not modules:
            return frozenset()
        return expand_colocated_tier1_siblings(modules, self._module_provider.list_modules())

    def list_route_specs(self) -> tuple[TaskRouteSpec, ...]:
        return self._routes.list_route_specs()

    def subscribed_modules(self, event_id: EventId) -> frozenset[ModuleId]:
        return self._routes.subscribed_modules_for_event(event_id)

    def warmup_daemon_container(self, only_modules: Optional[frozenset[ModuleId]] = None) -> None:
        """Warm up modules declaring eager_warmup=True across Tier 0 and Tier 1 before marking READY."""
        if self._gates.is_globally_quiesced():
            return
        prev_base = self._container.base_state
        was_initial_boot = prev_base in (ContainerState.UNINITIALIZED, ContainerState.BOOTING, ContainerState.WARMING)
        if was_initial_boot:
            self._container.transition_boot_phase(ContainerState.WARMING)
        try:
            descriptors = list(self._module_provider.list_modules())
            tier0 = [d for d in descriptors if d.venv_python is None]
            self._tier0_slots.register_descriptors(tier0)
            self._container.warmup(dict(self._tier0_slots.warmup_modules(only_modules)))
            if was_initial_boot and only_modules is None:
                self._container.transition_boot_phase(ContainerState.WARMING)

            tier1_groups: dict[str, list[ModuleDescriptor]] = {}
            for d in descriptors:
                if d.venv_python is not None:
                    tier1_groups.setdefault(tier1_group_key_for(d), []).append(d)
            for g_descs in tier1_groups.values():
                if only_modules is None or any(d.module_id in only_modules for d in g_descs):
                    self._tier1_pool.warmup_group(g_descs, only_modules)
            if was_initial_boot and only_modules is None:
                self._container.transition_boot_phase(ContainerState.READY)
        except BaseException:
            if (
                was_initial_boot
                and only_modules is None
                and self._container.base_state == ContainerState.WARMING
                and prev_base in (ContainerState.UNINITIALIZED, ContainerState.BOOTING)
            ):
                self._container.transition_boot_phase(prev_base)
            raise

    def _apply_tier1_warmup_reply(self, eager_mods: Sequence[ModuleId], reply: WorkerWarmupReply) -> None:
        for mid in eager_mods:
            err_detail = reply.degraded.get(str(mid))
            if err_detail is not None:
                self._container.record_degraded(mid, err_detail)
            else:
                self._container.clear_degraded(frozenset({mid}))

    @overload
    def invoke(
        self,
        request: InvokeRequest,
        *,
        output_type: type[TOut],
        cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[TOut]: ...

    @overload
    def invoke(
        self,
        request: InvokeRequest,
        *,
        output_type: None = None,
        cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[JsonValue]: ...

    def invoke(
        self,
        request: InvokeRequest,
        *,
        output_type: Optional[type[TOut]] = None,
        cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[TOut] | TaskOutcome[JsonValue]:
        raw_res = self._invoke_raw(request, cancel_token=cancel_token, on_progress=on_progress)
        if output_type is not None:
            return decode_outcome_as(raw_res.outcome, output_type, source_task=str(request.task_id))
        return raw_res.outcome

    def invoke_daemon_rpc(
        self,
        payload: JsonObject,
        cancel_token: CancellationToken,
        on_progress: Callable[[JsonObject], None],
        *,
        pre_turn_id: str = "",
    ) -> DaemonRpcInvokeReply:
        """Decode, execute, and encode a hot DaemonRpcInvokeEnvelope preserving transitive call & event lineage."""
        try:
            rpc_env = DataclassCodec.decode_envelope(DaemonRpcInvokeEnvelope, payload)
            if rpc_env.workspace_root != self._workspace_root:
                return DaemonRpcInvokeReply(
                    ok=False,
                    error=ErrorDetail(
                        ErrorCode.SECURITY_GATED,
                        f"Cross-workspace top-level RPC rejected: expected {self._workspace_root}, got {rpc_env.workspace_root}",
                        source_task=str(rpc_env.task_id),
                    ),
                )
            prop = rpc_env.propagation
            eff_scope = frozenset() if prop.in_event_chain else rpc_env.approval_scope
            req = InvokeRequest(
                task_id=rpc_env.task_id,
                raw_input=rpc_env.raw_input,
                workspace_root=rpc_env.workspace_root,
                caller_cwd=rpc_env.caller_cwd,
                caller_env=rpc_env.caller_env,
                caller_surface=rpc_env.caller_surface,
                priority=rpc_env.priority,
                approval_scope=eff_scope,
                allow_conditional=rpc_env.allow_conditional,
                propagation=replace(
                    prop,
                    turn_id=pre_turn_id or prop.turn_id or None,
                    call_tree_id=prop.call_tree_id
                    or (prop.turn_id if (prop.is_nested_call or bool(prop.call_stack)) else (pre_turn_id or None)),
                    is_internal_trigger=False,
                    from_hot_container=True,
                    hot_workspaces=prop.hot_workspaces | frozenset({self._workspace_root}),
                ),
            )
            turn_guard = DeadlineGuard.from_timeout_ms(rpc_env.timeout_ms, cancel_token)
        except (YscbError, KeyError, ValueError, TypeError) as exc:
            err_d = (
                exc.detail
                if isinstance(exc, YscbError)
                else ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, f"Malformed RPC InvokeRequest: {safe_exception_summary(exc)}")
            )
            return DaemonRpcInvokeReply(ok=False, error=err_d)
        raw_res = self._invoke_raw(req, cancel_token=cancel_token, on_progress=on_progress, turn_guard=turn_guard)
        out = raw_res.outcome
        return DaemonRpcInvokeReply(
            ok=out.ok,
            raw_value=out.value,
            error=out.error,
            event_diagnostics=out.event_diagnostics,
            teardown_diagnostics=out.teardown_diagnostics,
            invoked_tasks=raw_res.invoked_tasks,
            emitted_hops=raw_res.emitted_hops,
            coalesced=out.coalesced,
        )

    def invoke_typed(
        self,
        task_meta: TaskMetadata[TIn, TOut],
        req: TIn,
        *,
        caller_cwd: Optional[HostPath] = None,
        routing_policy: ClientRoutingPolicy = ClientRoutingPolicy.AUTO_SPAWN,
        approval_scope: frozenset[TaskId] = frozenset(),
        cancel_token: Optional[CancellationToken] = None,
    ) -> TaskOutcome[TOut]:
        """Strongly typed SDK entry checking both TIn and TOut at compile time and runtime."""
        if not isinstance(task_meta, TaskMetadata):
            return TaskOutcome(
                ok=False,
                error=ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected TaskMetadata, got {task_meta!r}"),
            )
        try:
            encoded_req = DataclassCodec.encode_object(req, expected_type=task_meta.input_type)
        except YscbError as exc:
            return TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(task_meta.task_id)))
        envelope = InvokeRequest(
            task_id=task_meta.task_id,
            raw_input=encoded_req,
            workspace_root=self._workspace_root,
            caller_cwd=caller_cwd or self._workspace_root,
            routing_policy=routing_policy,
            approval_scope=approval_scope,
        )
        return self.invoke(envelope, output_type=task_meta.output_type, cancel_token=cancel_token)

    def _pre_lookup_turn_guard(self, task_id: TaskId, token: CancellationToken) -> Optional[DeadlineGuard]:
        pre_entry = self._routes.lookup(task_id, ensure_ready=True)
        if pre_entry is not None and pre_entry[1].timeout_ms is not None:
            return DeadlineGuard.from_timeout_ms(pre_entry[1].timeout_ms, token)
        return None


    def _wait_hot_reload_gate(
        self,
        req: InvokeRequest,
        token: CancellationToken,
        guard: Optional[DeadlineGuard],
        fallback_tid: str,
    ) -> Optional[RawInvokeResult]:
        try:
            gate_tmo = guard.remaining_ms() if guard is not None else None
            self._gates.wait_if_module_reloading(
                req, token, self._step_host.is_reentrant_retiring, timeout_ms=gate_tmo
            )
        except (TaskCancelledException, YscbError) as exc:
            return RawInvokeResult(
                TaskOutcome(ok=False, error=exc.detail.with_fallback_task(fallback_tid), executed_hot=True)
            )
        return RawInvokeResult(cancelled_task_outcome(token, fallback_tid)) if token.is_cancelled else None

    def _invoke_raw(
        self,
        request: InvokeRequest,
        *,
        cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
        turn_guard: Optional[DeadlineGuard] = None,
    ) -> RawInvokeResult:
        token = cancel_token or CancellationToken()
        fallback_tid = str(request.task_id)
        if token.is_cancelled:
            return RawInvokeResult(cancelled_task_outcome(token, fallback_tid))
        try:
            validate_wire_json_object(
                request.raw_input,
                max_depth=MAX_USER_JSON_DEPTH,
                label="InvokeRequest.raw_input",
            )
        except (TypeError, ValueError) as exc:
            return RawInvokeResult(
                TaskOutcome(
                    ok=False,
                    error=ErrorDetail(
                        code=ErrorCode.CODEC_VALIDATION_FAILED,
                        message=f"Invalid InvokeRequest.raw_input: {safe_exception_summary(exc)}",
                        source_task=fallback_tid,
                    ),
                    executed_hot=self._opts.is_daemon_host,
                )
            )
        prop = request.propagation
        eff_tree_id = prop.call_tree_id or uuid.uuid4().hex
        eff_hot_ws = prop.hot_workspaces | (
            frozenset({self._workspace_root}) if self._opts.is_daemon_host else frozenset()
        )
        sanitized_req = replace(
            request,
            caller_env=sanitize_caller_env(request.caller_env),
            propagation=replace(prop, call_tree_id=eff_tree_id, hot_workspaces=eff_hot_ws),
        )
        if sanitized_req.workspace_root != self._workspace_root:
            return self._delegate_to_child_workspace(sanitized_req, token, on_progress, turn_guard)
        inbound_fids = (*prop.coalesce_flights, *(f for v in prop.coalesce_callers for f in v.flight_ids))
        with self._coordinator.pin_inbound_flights(inbound_fids):
            return self._invoke_local_or_routed(sanitized_req, eff_tree_id, fallback_tid, token, on_progress, turn_guard)

    def _invoke_local_or_routed(
        self,
        sanitized_req: InvokeRequest,
        eff_tree_id: str,
        fallback_tid: str,
        token: CancellationToken,
        on_progress: Optional[Callable[[JsonObject], None]],
        turn_guard: Optional[DeadlineGuard],
    ) -> RawInvokeResult:
        eff_guard = turn_guard or self._pre_lookup_turn_guard(sanitized_req.task_id, token)
        if self._opts.is_daemon_host:
            hot_err = self._wait_hot_reload_gate(sanitized_req, token, eff_guard, fallback_tid)
            if hot_err is not None:
                return hot_err

        gate_err, resolved = self._validate_stage1_gates(sanitized_req)
        if (
            gate_err is not None
            and gate_err.code in (ErrorCode.TASK_NOT_FOUND, ErrorCode.MODULE_DEGRADED)
            and not self._opts.is_daemon_host
        ):
            ref_err = self._cold_locks.refresh_cold_routes(
                token, eff_tree_id, deadline=eff_guard.deadline if eff_guard is not None else None
            )
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
            sanitized_req,
            spec,
            is_hot=self._opts.is_daemon_host,
            cancel_token=token,
            on_progress=on_progress,
            turn_guard=eff_guard,
        )

    def _delegate_to_child_workspace(
        self,
        request: InvokeRequest,
        token: CancellationToken,
        on_progress: Optional[Callable[[JsonObject], None]],
        turn_guard: Optional[DeadlineGuard],
    ) -> RawInvokeResult:
        if self._opts.child_dispatcher_factory is None:
            return RawInvokeResult(
                TaskOutcome(
                    ok=False,
                    error=ErrorDetail(
                        code=ErrorCode.TASK_NOT_FOUND,
                        message=f"No child workspace dispatcher configured for {request.workspace_root}",
                        source_task=str(request.task_id),
                    ),
                )
            )
        child_req = replace(
            request,
            propagation=replace(request.propagation, is_nested_call=False, from_hot_container=False),
        )
        try:
            child_disp = self._opts.child_dispatcher_factory(child_req.workspace_root)
        except YscbError as exc:
            return RawInvokeResult(TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(request.task_id))))
        raw_res: Optional[RawInvokeResult] = None
        child_td: tuple[ErrorDetail, ...] = ()
        try:
            if isinstance(child_disp, RuntimeDispatcher):
                child_disp._bind_shared_coordinators(self._shared_ws)
                raw_res = child_disp._invoke_raw(
                    child_req, cancel_token=token, on_progress=on_progress, turn_guard=turn_guard
                )
            else:
                raw_res = RawInvokeResult(
                    child_disp.invoke(child_req, cancel_token=token, on_progress=on_progress)
                )
            if raw_res.invoked_tasks:
                self._sessions.record_transitive_invoked_tasks(request.propagation, raw_res.invoked_tasks)
            if raw_res.emitted_hops:
                self._sessions.record_transitive_emitted_hops(request.propagation, raw_res.emitted_hops)
        finally:
            child_td = (
                child_disp.shutdown(grace_ms=500)
                if _should_shutdown_ephemeral_child(self, child_disp, self._opts.owns_child_dispatchers)
                else child_disp.drain_teardown_diagnostics()
            )
            if child_td and raw_res is None:
                self._sessions.record_host_teardown_diags(child_td)
        raw_res = require_non_none(raw_res)
        if child_td:
            merged_out = replace(
                raw_res.outcome,
                teardown_diagnostics=(*raw_res.outcome.teardown_diagnostics, *child_td),
            )
            return replace(raw_res, outcome=merged_out)
        return raw_res

    def _route_external_turn(
        self,
        request: InvokeRequest,
        spec: TaskRouteSpec,
        token: CancellationToken,
        on_progress: Optional[Callable[[JsonObject], None]],
        turn_guard: Optional[DeadlineGuard],
    ) -> RawInvokeResult:
        conn_cfg = self._opts.connection_config
        requires_hot = (
            request.routing_policy == ClientRoutingPolicy.STRICT_HOT
            or (conn_cfg.strict_hot_dispatch and request.routing_policy != ClientRoutingPolicy.FORCE_COLD)
            or spec.dispatch_mode == DispatchMode.DAEMON_ONLY
        )
        prefer_local_cold_reentry = (
            self._workspace_root in request.propagation.cold_shared_workspaces
        ) and not requires_hot
        if (
            conn_cfg.enabled
            and spec.dispatch_mode != DispatchMode.COLD_ONLY
            and request.routing_policy != ClientRoutingPolicy.FORCE_COLD
            and not prefer_local_cold_reentry
        ):
            hot_res = self._try_remote_daemon_call(request, spec, token, on_progress, turn_guard)
            if hot_res is not None:
                return hot_res
            if requires_hot:
                return RawInvokeResult(
                    TaskOutcome(
                        ok=False,
                        error=ErrorDetail(
                            code=ErrorCode.DAEMON_UNAVAILABLE,
                            message=f"Daemon required for '{request.task_id}' but unavailable.",
                            remediation="Run 'yscb daemon start' or omit strict hot mode.",
                            source_task=str(request.task_id),
                        ),
                    )
                )
            spawner = self._opts.daemon_spawner
            auto_spawned = (
                request.routing_policy == ClientRoutingPolicy.AUTO_SPAWN
                and conn_cfg.auto_spawn
                and spawner is not None
                and spawner.can_spawn_in_environment()
            )
        elif spec.dispatch_mode != DispatchMode.COLD_ONLY and requires_hot:
            return RawInvokeResult(
                TaskOutcome(
                    ok=False,
                    error=ErrorDetail(
                        code=ErrorCode.DAEMON_UNAVAILABLE,
                        message=f"Daemon required for '{request.task_id}' but disabled or unavailable.",
                        source_task=str(request.task_id),
                    ),
                )
            )
        else:
            auto_spawned = False

        try:
            return self._run_full_turn_locally(
                request,
                spec,
                is_hot=False,
                cancel_token=token,
                on_progress=on_progress,
                turn_guard=turn_guard,
            )
        finally:
            if auto_spawned and self._opts.daemon_spawner is not None:
                self._opts.daemon_spawner.try_spawn_background(self._workspace_root)

    def try_quiesce_modules(
        self,
        modules: frozenset[ModuleId],
        *,
        drain_deadline: Optional[float] = None,
        leased: bool = False,
    ) -> bool:
        modules = require_typed_frozenset(modules, ModuleId, "modules")
        safe_dl = normalize_drain_deadline(drain_deadline)
        with self._gates.lifecycle_scope():
            all_descs = list(self._module_provider.list_modules())
            pre_ids = self._sessions.snapshot_active_turn_and_tree_ids() if leased else frozenset()
            target_mods = self._gates.try_begin_quiesce(
                modules,
                all_descs,
                drain_deadline=safe_dl,
                leased=leased,
                pre_accepted_ids=pre_ids,
            )
            if target_mods is None:
                return False
            rem_ms = (
                2000
                if safe_dl is None
                else max(100, min(2000, int(max(0.0, min(10.0, safe_dl - time.monotonic())) * 1000.0)))
            )
            q_all = (not bool(modules)) or (CORE_MODULE_ID in modules)
            try:
                self._sessions.record_host_teardown_diags(
                    self._tier1_pool.stop_groups_for_modules(
                        target_mods, all_descs, grace_ms=rem_ms, drain_in_flight=False
                    )
                )
                self._sessions.record_host_teardown_diags(
                    self._tier0_slots.unload_modules(
                        target_mods,
                        drain_in_flight=True,
                        grace_sec=ms_to_safe_sec(rem_ms, min_sec=0.1),
                    )
                )
                return True
            except BaseException:
                if leased:
                    self._gates.record_quiesce_lease(q_all, target_mods, 0.5)
                raise

    def quiesce_modules(self, modules: frozenset[ModuleId], grace_ms: int = 3000) -> None:
        checked_mods = require_typed_frozenset(modules, ModuleId, "modules")
        if isinstance(grace_ms, bool) or not isinstance(grace_ms, int) or grace_ms < 0:
            raise ValueError(f"grace_ms must be a non-negative int (not bool), got {grace_ms!r}")
        deadline = time.monotonic() + ms_to_safe_sec(grace_ms, min_sec=0.05)
        self.try_quiesce_modules(checked_mods, drain_deadline=deadline, leased=False)

    def execute_daemon_quiesce_resume(
        self,
        *,
        expected_epoch: Optional[int],
        modules: Optional[frozenset[ModuleId]],
        preserve_modules: frozenset[ModuleId] = frozenset(),
        deferred_boot: bool = False,
        check_core_mutated: Callable[[], bool],
        on_before_warmup: Callable[[frozenset[ModuleId], bool], None],
    ) -> QuiesceResumeResult:
        if expected_epoch is not None:
            require_pure_int(expected_epoch, "expected_epoch", min_val=0)
        if modules is not None:
            modules = require_typed_frozenset(modules, ModuleId, "modules")
        preserve_modules = require_typed_frozenset(preserve_modules, ModuleId, "preserve_modules")
        eff_mods = None if deferred_boot else modules
        expanded_cands = (
            (self.expand_quiesce_targets(eff_mods) - frozenset({CORE_MODULE_ID}))
            if eff_mods is not None
            else frozenset()
        )
        def _run_resume_body() -> bool:
            if check_core_mutated():
                return True
            self._resume_quiesce_core(
                modules=modules,
                preserve_modules=preserve_modules,
                deferred_boot=deferred_boot,
                on_before_warmup=on_before_warmup,
            )
            return False

        return self._gates.run_quiesce_resume_guarded(
            expected_epoch, eff_mods, expanded_cands, _run_resume_body, force_global=deferred_boot
        )

    def resume_from_quiesce(
        self,
        *,
        modules: Optional[frozenset[ModuleId]] = None,
        preserve_modules: frozenset[ModuleId] = frozenset(),
        on_before_warmup: Optional[Callable[[frozenset[ModuleId], bool], None]] = None,
    ) -> tuple[frozenset[ModuleId], bool]:
        if modules is not None:
            modules = require_typed_frozenset(modules, ModuleId, "modules")
        preserve_modules = require_typed_frozenset(preserve_modules, ModuleId, "preserve_modules")
        return self._resume_quiesce_core(
            modules=modules,
            preserve_modules=preserve_modules,
            deferred_boot=False,
            on_before_warmup=on_before_warmup,
        )

    def _resume_quiesce_core(
        self,
        *,
        modules: Optional[frozenset[ModuleId]],
        preserve_modules: frozenset[ModuleId],
        deferred_boot: bool,
        on_before_warmup: Optional[Callable[[frozenset[ModuleId], bool], None]],
    ) -> tuple[frozenset[ModuleId], bool]:
        with self._gates.lifecycle_scope():
            prev_descs = list(self._module_provider.list_modules())
            self._module_provider.reload()
            plan_descs = list(self._module_provider.list_modules())
            with self._gates.resume_reload_scope(
                plan_descs,
                modules,
                preserve_modules=preserve_modules,
                deferred_boot=deferred_boot,
            ) as c_plan:
                re_warm, touched_all, was_all = c_plan.re_warm, c_plan.touched_all, c_plan.was_all
                if re_warm:
                    stop_descs = (*prev_descs, *(d for d in plan_descs if d not in prev_descs))
                    self._sessions.record_host_teardown_diags(
                        self._tier1_pool.stop_groups_for_modules(re_warm, stop_descs, grace_ms=1000, drain_in_flight=False)
                    )
                    self._sessions.record_host_teardown_diags(
                        self._tier0_slots.unload_modules(re_warm, drain_in_flight=True, grace_sec=1.0)
                    )
                if on_before_warmup is not None:
                    on_before_warmup(touched_all, was_all)
                self._module_provider.reload()
                self._cfg_tracker.reload_always()
                if was_all:
                    self._container.clear_degraded()
                elif touched_all:
                    self._container.clear_degraded(touched_all)
                self._routes.rebuild()
                if self._opts.is_daemon_host:
                    self.warmup_daemon_container(only_modules=None if was_all else re_warm)
                return (touched_all, was_all)

    def reload_config_and_contributes(
        self,
        *,
        changed_paths: Sequence[str] = (),
        emit_event: bool = True,
    ) -> bool:
        with self._gates.lifecycle_scope():
            changed = self._cfg_tracker.reload_always()
            self._module_provider.reload()
            self._routes.rebuild()
        st = self._container.state
        cfg_sub_gated = any(
            self._gates.is_call_gated_for_quiesce(mid)
            for mid in self.subscribed_modules(CONFIG_CHANGED_EVENT_ID)
        )
        can_emit = (
            st in (ContainerState.UNINITIALIZED, ContainerState.READY, ContainerState.QUIESCED)
            and not self._gates.is_globally_quiesced()
            and not cfg_sub_gated
        )
        if emit_event and changed and self._opts.is_daemon_host and can_emit:
            self.emit_background_event(CONFIG_CHANGED_EVENT_ID, {"changed_paths": list(changed_paths)})
        return changed

    def reload_affected_modules(self, modules: frozenset[ModuleId], grace_ms: int = 2000) -> None:
        with self._gates.lifecycle_scope():
            all_descs = list(self._module_provider.list_modules())
            reload_all = (not bool(modules)) or (CORE_MODULE_ID in modules)
            base_mods = (
                (modules - frozenset({CORE_MODULE_ID}))
                if not reload_all
                else frozenset(d.module_id for d in all_descs if d.module_id != CORE_MODULE_ID)
            )
            gated_mods = base_mods if reload_all else expand_colocated_tier1_siblings(base_mods, all_descs)
            with self._gates.module_reload_scope(reload_all, gated_mods) as update_reload_stage:
                self._tier1_pool.bump_groups_epoch(gated_mods, all_descs)
                self._sessions.record_host_teardown_diags(
                    self._tier1_pool.stop_groups_for_modules(gated_mods, all_descs, grace_ms=grace_ms, drain_in_flight=True)
                )
                self._sessions.record_host_teardown_diags(
                    self._tier0_slots.unload_modules(base_mods, drain_in_flight=True, grace_sec=ms_to_safe_sec(grace_ms, min_sec=0.1))
                )
                self._cfg_tracker.reload_always()
                self._module_provider.reload()
                fresh_descs = list(self._module_provider.list_modules())
                _ = self._gates.sync_colocated_quiesce_siblings(fresh_descs)
                now_mods, extra_siblings = _compute_post_reload_targets(reload_all, base_mods, gated_mods, fresh_descs)
                if extra_siblings:
                    update_reload_stage(extra_siblings, False)
                    gated_mods = gated_mods | extra_siblings
                    self._tier1_pool.bump_groups_epoch(extra_siblings, fresh_descs)
                    self._sessions.record_host_teardown_diags(
                        self._tier1_pool.stop_groups_for_modules(
                            extra_siblings, fresh_descs, grace_ms=grace_ms, drain_in_flight=True
                        )
                    )
                self._container.reload_modules(None if reload_all else gated_mods)
                self._routes.rebuild()
                update_reload_stage(base_mods | gated_mods | now_mods, True)
                if self._opts.is_daemon_host and (reload_all or now_mods):
                    warm_mods = (
                        None
                        if reload_all
                        else frozenset(m for m in now_mods if not self._gates.is_module_quiesced(m))
                    )
                    if reload_all or warm_mods:
                        self.warmup_daemon_container(only_modules=warm_mods)

    def emit_background_event(
        self,
        event_id: EventId,
        raw_payload: JsonObject,
        *,
        ordering: EventOrdering = EventOrdering.UNORDERED,
    ) -> TurnExecutionReport:
        tid = uuid.uuid4().hex
        caller_tok = CancellationToken()
        turn_cg = SharedCancelGroup()
        detach_bg = turn_cg.try_add_participant(caller_tok)
        if self._opts.is_daemon_host:
            scope = (
                None
                if self._gates.is_globally_quiesced()
                else self._container.begin_hot_turn(TurnKind.HOT_BACKGROUND, cancel_token=turn_cg.host_token, turn_id=tid)
            )
            if scope is None:
                if detach_bg is not None:
                    detach_bg()
                turn_cg.close_all()
                return TurnExecutionReport(
                    turn_id=tid,
                    primary_result=StepExecutionResult(
                        ok=False,
                        error=ErrorDetail(ErrorCode.DAEMON_UNAVAILABLE, "Container is draining, stopped, or quiesced."),
                    ),
                )
        else:
            scope = TurnScope(turn_id=tid, kind=TurnKind.COLD, cancel_token=turn_cg.host_token)

        session = ActiveTurnSession(
            scope=scope,
            caller_cancel=caller_tok,
            prio_handle=PriorityHandle(ExecutionPriority.BACKGROUND),
            hot_workspaces=frozenset({self._workspace_root}) if self._opts.is_daemon_host else frozenset(),
            cold_shared_workspaces=frozenset() if self._opts.is_daemon_host else frozenset({self._workspace_root}),
        )
        rec = RawEventRecord(
            event_id=event_id,
            emitter_task=WATCHER_TASK_ID,
            raw_payload=raw_payload,
            ordering=ordering,
            lineage=CausalLineage().advance(event_id, workspace_scope=self._workspace_root.comparison_key),
        )
        try:
            with self._sessions.managed_session(session):
                if self._opts.is_daemon_host:
                    return self._turn_engine.execute_event_turn(scope, (rec,))
                return self._cold_locks.run_cold_event_turn(
                    scope,
                    lambda: self._turn_engine.execute_event_turn(scope, (rec,)),
                )
        finally:
            if detach_bg is not None:
                detach_bg()
            turn_cg.close_all()

    def _drain_flight_cascade(self, cascade: FlightCascade) -> TurnExecutionReport:
        tid = f"cascade_{cascade.cascade_id}"
        kind = TurnKind.HOT_BACKGROUND if self._opts.is_daemon_host else TurnKind.COLD
        scope = TurnScope(
            turn_id=tid,
            kind=kind,
            cancel_token=cascade.drain_cg.host_token,
            on_diagnostic=cascade.record_live_diagnostic,
        )
        session = ActiveTurnSession(
            scope=scope,
            caller_cancel=cascade.drain_cg.host_token,
            prio_handle=cascade.prio_handle,
            hot_workspaces=frozenset({self._workspace_root}) if self._opts.is_daemon_host else frozenset(),
            coalesce_callers=cascade.snapshot_live_caller_views(),
            owner_cascade=cascade,
        )
        with self._sessions.managed_session(session):
            return self._turn_engine.execute_event_turn(
                scope,
                cascade.seed_events,
                on_events_staged=lambda recs: cascade.record_emitted_hops(extract_emitted_hops_from_records(recs)),
            )

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

        def _prepare_hosts(gms: int) -> None:
            rem_gms = self._wait_in_flight_drain(gms)
            pre_diags.extend(self._tier1_pool.prepare_lifo_shutdown(grace_ms=rem_gms))

        container_diags: tuple[ErrorDetail, ...] = ()
        pool_diags: tuple[ErrorDetail, ...] = ()
        try:
            container_diags = self._container.drain_and_stop(grace_period_ms=safe_grace_ms, on_drain=_prepare_hosts)
        finally:
            try:
                pool_diags = self._tier1_pool.collect_lifo_shutdown_diagnostics()
            finally:
                slot_diags = self._tier0_slots.unload_all_modules(grace_sec=0.05)
        return (*pre_diags, *container_diags, *pool_diags, *slot_diags)

    def _check_coalesce_committed_events(
        self,
        turn: TurnScope,
        prop: CallPropagationContext,
        events: Sequence[RawEventRecord],
    ) -> Optional[ErrorDetail]:
        if not events:
            return None
        caps = self._sessions.find_call_tree_captures(prop, turn.turn_id)
        sess = self._sessions.get_or_bind_turn_session(turn)
        eff_views = prop.coalesce_callers or live_session_coalesce_views(sess)
        base_hops = prop.lineage.scoped_hops()
        for rec in events:
            rec_hops = rec.lineage.scoped_hops()
            if not rec_hops:
                continue
            for cap in caps:
                common = cap.flight.find_common_conflicting_hop(rec_hops)
                if common is not None:
                    src = self._sessions.resolve_hop_source_task(common, caps, sess, str(rec.emitter_task))
                    return EventCycleError(
                        f"Deferred event cycle across all active coalesce callers on '{common[1]}'",
                        source_task=src,
                    ).detail
            delta_hops = tuple(h for h in rec_hops if h not in base_hops) or rec_hops[-1:]
            common_v = find_common_view_conflicting_hop(eff_views, delta_hops)
            if common_v is not None:
                src_v = self._sessions.resolve_hop_source_task(common_v, caps, sess, str(rec.emitter_task))
                return EventCycleError(
                    f"Deferred event cycle across all active coalesce callers on '{common_v[1]}'",
                    source_task=src_v,
                ).detail
        return None

    def run_primary_step(self, request: InvokeRequest, turn: TurnScope) -> StepExecutionResult[JsonValue]:
        tagged = replace(
            request,
            caller_env=sanitize_caller_env(request.caller_env),
            propagation=replace(request.propagation, turn_id=turn.turn_id),
        )
        res = self._execute_single_step_with_coordination(request=tagged, turn=turn)
        if res.committed_events and not res.fatal_abort_turn:
            cyc_err = self._check_coalesce_committed_events(turn, tagged.propagation, res.committed_events)
            if cyc_err is not None:
                res = StepExecutionResult(ok=False, error=cyc_err, fatal_abort_turn=True, coalesced=res.coalesced)
            else:
                self._sessions.record_session_emitted_records(turn.turn_id, res.committed_events)
        return res

    def run_event_step(self, batch: EventBatchEnvelope, turn: TurnScope) -> Sequence[StepExecutionResult[JsonValue]]:
        results: list[StepExecutionResult[JsonValue]] = []
        session = self._sessions.get_or_bind_turn_session(turn)
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
            if step_res.committed_events and not step_res.fatal_abort_turn:
                raw_views = live_session_coalesce_views(session)
                sub_views = filter_and_advance_coalesce_views(raw_views, sub_lineage.scoped_hops())
                cyc_err = self._check_coalesce_committed_events(
                    turn,
                    CallPropagationContext(turn_id=turn.turn_id, lineage=sub_lineage, coalesce_callers=sub_views),
                    step_res.committed_events,
                )
                if cyc_err is not None:
                    step_res = StepExecutionResult(
                        ok=False, error=cyc_err, fatal_abort_turn=True, coalesced=step_res.coalesced
                    )
                else:
                    self._sessions.record_session_emitted_records(turn.turn_id, step_res.committed_events)
            results.append(step_res)
            if step_res.fatal_abort_turn:
                break
        return results

    def _prepare_subscriber_target(
        self,
        probe_req: InvokeRequest,
        desc: ModuleDescriptor,
        spec: TaskRouteSpec,
        wait_tok: CancellationToken,
        guard: DeadlineGuard,
    ) -> tuple[Optional[ErrorDetail], ModuleDescriptor, TaskRouteSpec]:
        try:
            gate_tmo = guard.remaining_ms(spec.timeout_ms)
        except YscbError as exc:
            return (exc.detail.with_fallback_task(str(spec.task_id)), desc, spec)
        if self._opts.is_daemon_host:
            try:
                self._gates.wait_if_module_reloading(
                    probe_req, wait_tok, self._step_host.is_reentrant_retiring, timeout_ms=gate_tmo
                )
            except (TaskCancelledException, YscbError) as exc:
                return (exc.detail.with_fallback_task(str(spec.task_id)), desc, spec)
            if self._gates.is_quiesced_blocked(probe_req, desc.module_id, self._opts.is_daemon_host):
                q_err = ErrorDetail(
                    ErrorCode.DAEMON_UNAVAILABLE,
                    f"Module '{desc.module_id}' is currently quiesced.",
                    source_task=str(spec.task_id),
                )
                return (q_err, desc, spec)
            refreshed = self._routes.lookup(spec.task_id)
            if refreshed is not None:
                desc, spec = refreshed
        degraded = self._container.get_degraded(desc.module_id)
        if degraded is not None:
            return (degraded.with_fallback_task(str(spec.task_id)), desc, spec)
        return (None, desc, spec)

    def _run_matched_event_subscriber(
        self,
        desc: ModuleDescriptor,
        spec: TaskRouteSpec,
        event_id: EventId,
        filtered: Sequence[JsonObject],
        sub_lineage: CausalLineage,
        session: ActiveTurnSession,
    ) -> Optional[StepExecutionResult[JsonValue]]:
        turn = session.scope
        inherited_ctree = session.root_call_tree_id if session.inherit_call_tree else ""
        step_ctree = inherited_ctree or uuid.uuid4().hex
        sub_dl = merge_deadlines(
            session.turn_deadline,
            (time.monotonic() + ms_to_safe_sec(spec.timeout_ms)) if spec.timeout_ms is not None else None,
        )
        sub_guard = DeadlineGuard(cancel_token=turn.cancel_token, deadline=sub_dl)
        raw_views = live_session_coalesce_views(session)
        probe_req = self._build_event_subscriber_request(
            spec.task_id,
            session.scope.turn_id,
            step_ctree,
            session.prio_handle.current,
            CallPropagationContext(
                lineage=sub_lineage,
                hot_workspaces=session.hot_workspaces,
                cold_shared_workspaces=session.cold_shared_workspaces,
                coalesce_callers=raw_views,
            ),
        )
        sub_err, desc, spec = self._prepare_subscriber_target(probe_req, desc, spec, turn.cancel_token, sub_guard)
        if sub_err is not None:
            return StepExecutionResult(
                ok=False, error=sub_err, preempted=(sub_err.code == ErrorCode.TASK_PREEMPTED)
            )
        m_out = self._step_host.map_event_batch(
            desc,
            spec.task_id,
            event_id,
            filtered,
            EquivCallContext(turn=turn, call_tree_id=step_ctree, guard=sub_guard),
        )
        if not m_out.ok:
            is_pre = m_out.error is not None and m_out.error.code == ErrorCode.TASK_PREEMPTED
            return StepExecutionResult(ok=False, error=m_out.error, preempted=is_pre)
        if m_out.skip:
            return None
        sub_req = replace(probe_req, raw_input=m_out.mapped_input)
        return self._execute_single_step_with_coordination(
            request=sub_req,
            turn=turn,
            parent_prio=session.prio_handle,
            parent_deadline=session.turn_deadline,
        )

    def _build_event_subscriber_request(
        self,
        task_id: TaskId,
        turn_id: str,
        call_tree_id: str,
        priority: ExecutionPriority,
        base_prop: CallPropagationContext,
    ) -> InvokeRequest:
        eff_hot = base_prop.hot_workspaces | (
            frozenset({self._workspace_root}) if self._opts.is_daemon_host else frozenset()
        )
        coal_views = filter_and_advance_coalesce_views(base_prop.coalesce_callers, base_prop.lineage.scoped_hops())
        return InvokeRequest(
            task_id=task_id,
            raw_input={},
            workspace_root=self._workspace_root,
            caller_cwd=self._workspace_root,
            priority=priority,
            approval_scope=frozenset(),
            propagation=CallPropagationContext(
                turn_id=turn_id,
                call_tree_id=call_tree_id,
                call_stack=base_prop.call_stack,
                lineage=base_prop.lineage,
                is_internal_trigger=True,
                is_nested_call=bool(base_prop.call_stack) or base_prop.is_nested_call,
                in_event_chain=True,
                from_hot_container=self._opts.is_daemon_host,
                hot_workspaces=eff_hot,
                cold_shared_workspaces=base_prop.cold_shared_workspaces,
                coalesce_callers=coal_views,
                coalesce_flights=base_prop.coalesce_flights,
            ),
        )

    def _handle_worker_callback(
        self,
        env: WorkerCallbackEnvelope,
        peer_cancel_token: CancellationToken,
    ) -> WorkerCallbackReply:
        cb_tid = env.context_meta.propagation.turn_id or ""
        turn = self._sessions.try_retain_session_scope(cb_tid)
        if cb_tid and turn is None:
            return WorkerCallbackReply(
                ok=False,
                error=ErrorDetail(ErrorCode.TASK_CANCELLED, "Parent turn is no longer active"),
                executed_hot=self._opts.is_daemon_host,
            )
        try:
            if env.callback == WorkerCallbackKind.EMIT_IMM:
                return self._on_worker_emit_imm(env, turn, peer_cancel_token)
            if env.callback == WorkerCallbackKind.INVOKE_TASK:
                return self._on_worker_invoke_task(env, turn, peer_cancel_token)
            return WorkerCallbackReply(
                ok=False,
                error=ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, f"Unknown worker callback: {env.callback}"),
            )
        finally:
            if turn is not None:
                self._sessions.release_turn_session(cb_tid)

    def _on_worker_emit_imm(
        self,
        env: WorkerCallbackEnvelope,
        turn: Optional[TurnScope],
        peer_cancel_token: CancellationToken,
    ) -> WorkerCallbackReply:
        if env.event_id is None:
            return WorkerCallbackReply(
                ok=False,
                error=ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, "EMIT_IMM callback requires event_id."),
            )
        if turn is None:
            return WorkerCallbackReply(
                ok=False,
                error=ErrorDetail(ErrorCode.BUSINESS_FAILURE, "Active TurnScope not found for emit_imm"),
            )
        step_bind = self._sessions.lookup_active_step(env.context_meta.step_run_id)
        if step_bind is None:
            return WorkerCallbackReply(
                ok=False,
                error=ErrorDetail(ErrorCode.TASK_CANCELLED, "Parent step is no longer active for emit_imm"),
            )
        cb_cancel, detach_cb = CancellationToken.combine(step_bind.cancel_token, peer_cancel_token)
        imm_prop = replace(env.context_meta.propagation, lineage=env.lineage)
        emit_tid = imm_prop.call_stack[-1][1] if imm_prop.call_stack else None
        try:
            self._dispatch_immediate_event(
                _ImmediateEventDispatchSpec(
                    event_id=env.event_id,
                    raw_payload=env.raw_payload,
                    propagation=imm_prop,
                    strict=env.strict,
                    emitter_task=emit_tid,
                    parent_step_cancel=cb_cancel,
                    parent_prio=step_bind.prio_handle,
                    step_deadline=step_bind.current_deadline(),
                ),
                turn,
            )
            return WorkerCallbackReply(ok=True)
        except YscbError as exc:
            return WorkerCallbackReply(ok=False, error=exc.detail)
        except (Exception, SystemExit, GeneratorExit) as exc:
            det_imm = ErrorDetail(ErrorCode.BUSINESS_FAILURE, safe_exception_summary(exc), source_task=str(emit_tid))
            return WorkerCallbackReply(ok=False, error=det_imm)
        finally:
            detach_cb()

    def _on_worker_invoke_task(
        self,
        env: WorkerCallbackEnvelope,
        turn: Optional[TurnScope],
        peer_cancel_token: CancellationToken,
    ) -> WorkerCallbackReply:
        if env.task_id is None:
            return WorkerCallbackReply(
                ok=False,
                error=ErrorDetail(ErrorCode.CODEC_VALIDATION_FAILED, "INVOKE_TASK callback requires task_id."),
                executed_hot=self._opts.is_daemon_host,
            )
        step_bind = self._sessions.lookup_active_step(env.context_meta.step_run_id)
        if step_bind is None:
            det_c = ErrorDetail(ErrorCode.TASK_CANCELLED, "Parent step inactive for invoke_task", source_task=str(env.task_id))
            return WorkerCallbackReply(ok=False, error=det_c, executed_hot=self._opts.is_daemon_host)
        cb_cancel, detach_cb = CancellationToken.combine(step_bind.cancel_token, peer_cancel_token)
        try:
            target_ws = env.target_workspace or self._workspace_root
            r_pol = env.routing_policy or default_nested_routing_policy(
                target_ws != self._workspace_root, env.context_meta.parent_routing_policy
            )
            parent_ph = step_bind.prio_handle
            nested_spec = _NestedInvokeSpec(
                child_task_id=env.task_id,
                raw_input=env.raw_input,
                target_workspace=target_ws,
                caller_cwd=env.context_meta.caller_cwd,
                caller_env=sanitize_caller_env(env.context_meta.caller_env),
                routing_policy=r_pol,
                priority=parent_ph.current,
                approval_scope=step_bind.approval_scope,
                allow_conditional=step_bind.allow_conditional,
                propagation=replace(env.context_meta.propagation, lineage=env.lineage),
                parent_prio=parent_ph,
                step_deadline=step_bind.current_deadline(),
            )
            nested_out = self._invoke_nested_within_turn(turn, nested_spec, cb_cancel)
            return WorkerCallbackReply(
                ok=nested_out.ok,
                raw_value=nested_out.value,
                error=nested_out.error,
                event_diagnostics=nested_out.event_diagnostics,
                teardown_diagnostics=nested_out.teardown_diagnostics,
                coalesced=nested_out.coalesced,
                executed_hot=nested_out.executed_hot,
                fatal_abort_turn=False,
            )
        except YscbError as exc:
            return WorkerCallbackReply(
                ok=False,
                error=exc.detail,
                executed_hot=self._opts.is_daemon_host,
                fatal_abort_turn=is_fatal_error_code(exc.detail.code),
            )
        except (Exception, SystemExit, GeneratorExit) as exc:
            return WorkerCallbackReply(
                ok=False,
                error=ErrorDetail(
                    ErrorCode.BUSINESS_FAILURE,
                    safe_exception_summary(exc),
                    source_task=str(env.task_id) if env.task_id is not None else None,
                ),
                executed_hot=self._opts.is_daemon_host,
                fatal_abort_turn=False,
            )
        finally:
            detach_cb()

    def _cold_bootstrap_hook(self) -> None:
        with self._gates.lifecycle_scope():
            self._container.clear_degraded()
            self._cfg_tracker.reload_if_changed()
            self._module_provider.reload()
            self._routes.rebuild()

    def _validate_stage1_gates(
        self,
        request: InvokeRequest,
        *,
        in_cold_turn: bool = False,
    ) -> tuple[Optional[ErrorDetail], Optional[tuple[ModuleDescriptor, TaskRouteSpec]]]:
        found = self._routes.lookup(request.task_id, ensure_ready=True)
        mod_id = found[0].module_id if found is not None else request.task_id.module_id
        c_state = self._container.state
        draining_blocked = c_state == ContainerState.STOPPED or (
            c_state == ContainerState.DRAINING and not self._is_draining_admitted_turn(request.propagation)
        )
        if self._opts.is_daemon_host and draining_blocked:
            block_err: Optional[ErrorDetail] = ErrorDetail(
                code=ErrorCode.DAEMON_UNAVAILABLE,
                message="Hot container is draining or stopped.",
                source_task=str(request.task_id),
            )
        elif self._gates.is_quiesced_blocked(request, mod_id, self._opts.is_daemon_host):
            block_err = ErrorDetail(
                code=ErrorCode.DAEMON_UNAVAILABLE,
                message=f"Module '{request.task_id.module_id}' is currently quiesced.",
                source_task=str(request.task_id),
            )
        else:
            deg = self._container.get_degraded(mod_id)
            block_err = deg.with_fallback_task(str(request.task_id)) if deg is not None else None
        prop = request.propagation
        if not prop.coalesce_callers and (prop.coalesce_flights or prop.turn_id):
            live_views = self._sessions.snapshot_coalesce_callers(prop, prop.turn_id or "")
            if live_views:
                request = replace(request, propagation=replace(prop, coalesce_callers=live_views))
        return validate_stage1_gates(
            request,
            found,
            block_err,
            is_daemon_host=self._opts.is_daemon_host,
            conn_enabled=self._opts.connection_config.enabled,
            in_cold_turn=in_cold_turn,
        )

    def _try_remote_daemon_call(
        self,
        request: InvokeRequest,
        spec: TaskRouteSpec,
        cancel_token: CancellationToken,
        on_progress: Optional[Callable[[JsonObject], None]],
        turn_guard: Optional[DeadlineGuard],
    ) -> Optional[RawInvokeResult]:
        try:
            eff_req_tmo = turn_guard.remaining_ms(spec.timeout_ms) if turn_guard is not None else spec.timeout_ms
        except YscbError as exc:
            return RawInvokeResult(TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(request.task_id))))
        rpc_env = DaemonRpcInvokeEnvelope(
            task_id=request.task_id,
            raw_input=request.raw_input,
            workspace_root=request.workspace_root,
            caller_cwd=request.caller_cwd,
            caller_env=request.caller_env,
            caller_surface=request.caller_surface,
            priority=request.priority,
            approval_scope=request.approval_scope,
            allow_conditional=request.allow_conditional,
            timeout_ms=eff_req_tmo,
            propagation=request.propagation,
        )
        try:
            wire_payload = DataclassCodec.encode_envelope(rpc_env)
        except YscbError as exc:
            return RawInvokeResult(TaskOutcome(ok=False, error=exc.detail.with_fallback_task(str(request.task_id))))
        rpc_timeout_ms = None if eff_req_tmo is None else eff_req_tmo + 250
        if self._opts.persistent_rpc_session is not None:
            outcome: Optional[RemoteCallOutcome] = self._opts.persistent_rpc_session.call(
                wire_payload,
                on_progress=on_progress,
                cancel_token=cancel_token,
                timeout_ms=rpc_timeout_ms,
            )
        else:
            outcome = call_ephemeral_daemon_rpc(
                (self._cache_dir, self._workspace_root),
                wire_payload,
                on_progress=on_progress,
                cancel_token=cancel_token,
                timeout_ms=rpc_timeout_ms,
            )
        translated = translate_remote_daemon_outcome(outcome, cancel_token, str(request.task_id))
        if translated is None:
            return None
        if translated.invoked_tasks:
            self._sessions.record_transitive_invoked_tasks(request.propagation, translated.invoked_tasks)
        if translated.emitted_hops:
            self._sessions.record_transitive_emitted_hops(request.propagation, translated.emitted_hops)
        return translated

    def _is_draining_admitted_turn(self, prop: CallPropagationContext) -> bool:
        if self._sessions.has_admitted_session(prop):
            return True
        return self._gates.has_admitted_rpc_turn(prop.turn_id or "")

    def _build_turn_scope_or_reject(
        self,
        tid: str,
        turn_kind: TurnKind,
        host_token: CancellationToken,
    ) -> Optional[TurnScope]:
        if turn_kind == TurnKind.COLD:
            return TurnScope(turn_id=tid, kind=turn_kind, cancel_token=host_token)
        scope = self._container.begin_hot_turn(turn_kind, cancel_token=host_token, turn_id=tid)
        if scope is None and self._container.state == ContainerState.DRAINING and self._gates.has_admitted_rpc_turn(tid):
            return TurnScope(turn_id=tid, kind=turn_kind, cancel_token=host_token)
        return scope

    def _run_full_turn_locally(
        self,
        request: InvokeRequest,
        spec: TaskRouteSpec,
        *,
        is_hot: bool,
        cancel_token: CancellationToken,
        on_progress: Optional[Callable[[JsonObject], None]],
        turn_guard: Optional[DeadlineGuard],
    ) -> RawInvokeResult:
        raw_prop = request.propagation
        init_tid = raw_prop.turn_id or uuid.uuid4().hex
        tid, prop = self._sessions.ensure_fresh_turn_id(replace(raw_prop, turn_id=init_tid))
        tagged_req = replace(request, propagation=prop)
        turn_kind = (
            (TurnKind.HOT_BACKGROUND if request.priority == ExecutionPriority.BACKGROUND else TurnKind.HOT_FOREGROUND)
            if is_hot
            else TurnKind.COLD
        )
        turn_cg = SharedCancelGroup()
        turn_scope = self._build_turn_scope_or_reject(tid, turn_kind, turn_cg.host_token)
        if turn_scope is None:
            turn_cg.close_all()
            err = ErrorDetail(
                ErrorCode.DAEMON_UNAVAILABLE, "Hot container is draining or stopped.", source_task=str(tagged_req.task_id)
            )
            rej_rep = TurnExecutionReport(turn_id=tid, primary_result=StepExecutionResult(ok=False, error=err))
            return RawInvokeResult(report_to_outcome(rej_rep, is_hot=is_hot, fallback_task=str(request.task_id)), (), ())

        detach_caller = turn_cg.try_add_participant(cancel_token)
        cold_shared = prop.cold_shared_workspaces | (
            frozenset({self._workspace_root})
            if (turn_kind == TurnKind.COLD and spec.mutation_scope == SelfMutationScope.NONE)
            else frozenset()
        )
        spec_dl = (time.monotonic() + ms_to_safe_sec(spec.timeout_ms)) if spec.timeout_ms is not None else None
        deadline = merge_deadlines(turn_guard.deadline if turn_guard is not None else None, spec_dl)
        session = ActiveTurnSession(
            scope=turn_scope,
            caller_cancel=cancel_token,
            prio_handle=PriorityHandle(tagged_req.priority),
            on_progress=on_progress,
            root_call_tree_id=prop.call_tree_id or tid,
            primary_task_id=str(tagged_req.task_id),
            inherit_call_tree=bool(prop.call_stack),
            turn_deadline=turn_guard.deadline if turn_guard is not None else None,
            effective_deadline=deadline,
            hot_workspaces=prop.hot_workspaces,
            cold_shared_workspaces=cold_shared,
            coalesce_callers=prop.coalesce_callers,
            turn_entry_stack=prop.call_stack,
        )
        try:
            with self._sessions.managed_session(session):
                report = (
                    self._cold_locks.run_cold_turn(tagged_req, spec, turn_scope, deadline=deadline)
                    if turn_kind == TurnKind.COLD
                    else self._turn_engine.execute_turn(tagged_req, turn_kind, scope=turn_scope)
                )
                inv_snap, em_snap = self._sessions.snapshot_session_lineage(session)
        finally:
            if detach_caller is not None:
                detach_caller()
            turn_cg.close_all()
        return RawInvokeResult(
            report_to_outcome(report, is_hot=is_hot, fallback_task=str(request.task_id)),
            inv_snap,
            em_snap,
        )

    def finalize_turn_events(self, turn: TurnScope, *, abort_only: bool = False) -> Optional[ErrorDetail]:
        session, cascades = self._sessions.pop_attached_cascades(turn.turn_id)
        if session is None or not cascades:
            return None
        if abort_only:
            abort_remaining_attached(cascades)
            return None
        fallback_tid = session.primary_task_id or "cascade"
        eff_dl = session.effective_deadline if session.effective_deadline is not None else session.turn_deadline
        for idx, item in enumerate(cascades):
            try:
                out: CascadeOutcome = item.cascade.activate_and_await(
                    item.slot_id, item.base_lineage, session.caller_cancel, eff_dl, self._drain_flight_cascade
                )
            except (TaskCancelledException, YscbError) as exc:
                abort_remaining_attached(cascades[idx:])
                return exc.detail.with_fallback_task(fallback_tid)
            finally:
                item.unreg_prio()
            for diag in out.event_diagnostics:
                turn.record_event_diagnostic(diag)
            self._sessions.record_cascade_outcome(
                session, item.cascade.snapshot_emitted_hops(), out.teardown_diagnostics
            )
            if out.fatal_error is not None:
                abort_remaining_attached(cascades[idx + 1 :])
                return out.fatal_error
        return None

    def _execute_single_step_with_coordination(
        self,
        *,
        request: InvokeRequest,
        turn: TurnScope,
        parent_step_cancel: Optional[CancellationToken] = None,
        parent_prio: Optional[PriorityHandle] = None,
        parent_deadline: Optional[float] = None,
    ) -> StepExecutionResult[JsonValue]:
        sess = self._sessions.get_or_bind_turn_session(turn)
        self._sessions.record_session_invoked_frame(sess, (request.workspace_root, request.task_id))
        prop = request.propagation
        eff_prog = sess.on_progress if not prop.is_internal_trigger else None
        if not prop.is_nested_call and not prop.is_internal_trigger:
            step_ph = sess.prio_handle
            unreg_p: Callable[[], None] = lambda: None
        else:
            init_p = parent_prio.current if parent_prio is not None else request.priority
            step_ph = PriorityHandle(init_p)
            unreg_p = (
                parent_prio.register_listener(
                    lambda p: step_ph.elevate_to_foreground() if p == ExecutionPriority.FOREGROUND else None
                )
                if parent_prio is not None
                else (lambda: None)
            )
        try:
            eff_outer_dl = merge_deadlines(sess.turn_deadline, parent_deadline)
            step_started = time.monotonic()
            wait_tok = parent_step_cancel or turn.cancel_token
            pre_found = self._routes.lookup(request.task_id)
            pre_tmo = pre_found[1].timeout_ms if pre_found is not None else None
            pre_dl = merge_deadlines(eff_outer_dl, (step_started + ms_to_safe_sec(pre_tmo)) if pre_tmo is not None else None)
            pre_guard = DeadlineGuard(cancel_token=wait_tok, deadline=pre_dl)
            try:
                self._gates.wait_if_module_reloading(
                    request, wait_tok, self._step_host.is_reentrant_retiring, timeout_ms=pre_guard.remaining_ms(pre_tmo)
                )
            except (TaskCancelledException, YscbError) as exc:
                res = StepExecutionResult(
                    ok=False, error=exc.detail, preempted=(exc.detail.code == ErrorCode.TASK_PREEMPTED)
                )
                return (
                    replace(res, error=res.error.with_fallback_task(str(request.task_id)))
                    if res.error is not None and res.error.source_task is None
                    else res
                )
            gate_err, resolved = self._validate_stage1_gates(request, in_cold_turn=(turn.kind == TurnKind.COLD))
            if gate_err is not None:
                res = StepExecutionResult(ok=False, error=gate_err, fatal_abort_turn=is_fatal_error_code(gate_err.code))
                return (
                    replace(res, error=res.error.with_fallback_task(str(request.task_id)))
                    if res.error is not None and res.error.source_task is None
                    else res
                )
            desc, spec = require_non_none(resolved)
            self._sessions.record_transitive_invoked_tasks(prop, ((request.workspace_root, request.task_id),))
            step_req = replace(
                request,
                propagation=replace(prop, call_stack=(*prop.call_stack, (request.workspace_root, request.task_id))),
            )
            step_cancel = CancellationToken()
            parent_cancel = (
                parent_step_cancel
                if parent_step_cancel is not None
                else (sess.caller_cancel if not prop.in_event_chain else turn.cancel_token)
            )
            unreg = parent_cancel.register_callback(lambda p, r: step_cancel.cancel(preempted=p, reason=r))
            spec_dl = (step_started + ms_to_safe_sec(spec.timeout_ms)) if spec.timeout_ms is not None else None
            step_guard = DeadlineGuard(cancel_token=step_cancel, deadline=merge_deadlines(eff_outer_dl, spec_dl))
            step_env = StepExecutionEnv(
                desc=desc,
                spec=spec,
                step_req=step_req,
                turn=turn,
                step_cancel=step_cancel,
                on_progress=eff_prog,
                step_guard=step_guard,
                reload_epoch=self._gates.current_epoch(desc.module_id),
            )
            step_ok = False
            try:
                if not spec.resource_key or spec.concurrency_mode == ConcurrencyMode.PARALLEL:
                    res = self._dispatch_parallel_step_safe(step_env, step_ph, step_cancel)
                else:
                    res = self._coordinate_and_dispatch_step(step_env, step_ph)
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
        self,
        step_env: StepExecutionEnv,
        ph: PriorityHandle,
        step_cancel: CancellationToken,
    ) -> StepExecutionResult[JsonValue]:
        try:
            res, guard_ev = self._step_host.dispatch_to_host(
                step_env, ph, step_cancel, self._build_tier0_callbacks
            )
            if guard_ev is not None and not guard_ev.is_set() and step_env.turn.kind == TurnKind.COLD:
                guard_ev.wait(timeout=3.0)
            return res
        except (TaskCancelledException, YscbError) as exc:
            return StepExecutionResult(
                ok=False, error=exc.detail, preempted=(exc.detail.code == ErrorCode.TASK_PREEMPTED)
            )

    def _build_tier0_callbacks(
        self,
        env: StepExecutionEnv,
        priority_getter: PriorityHandle,
    ) -> StepContextCallbacks:
        step_req = env.step_req
        prop = step_req.propagation
        turn = env.turn
        ctree = prop.call_tree_id or turn.turn_id
        return StepContextCallbacks(
            on_emit_imm=lambda eid, ev_raw, imm_lin, strict: self._dispatch_immediate_event(
                _ImmediateEventDispatchSpec(
                    event_id=eid,
                    raw_payload=ev_raw,
                    propagation=replace(prop, call_tree_id=ctree, lineage=imm_lin),
                    strict=strict,
                    emitter_task=env.spec.task_id,
                    parent_step_cancel=env.step_cancel,
                    parent_prio=priority_getter,
                    step_deadline=env.current_guard().deadline,
                ),
                turn,
            ),
            on_invoke_task=lambda c_tid, encoded_in, t_ws, r_pol: self._invoke_nested_within_turn(
                turn,
                _NestedInvokeSpec(
                    child_task_id=c_tid,
                    raw_input=encoded_in,
                    target_workspace=t_ws or self._workspace_root,
                    caller_cwd=step_req.caller_cwd,
                    caller_env=dict(step_req.caller_env),
                    routing_policy=r_pol
                    or default_nested_routing_policy(
                        bool(t_ws and t_ws != self._workspace_root), step_req.routing_policy
                    ),
                    priority=priority_getter(),
                    approval_scope=step_req.approval_scope,
                    allow_conditional=step_req.allow_conditional,
                    propagation=replace(prop, call_tree_id=ctree),
                    parent_prio=priority_getter,
                    step_deadline=env.current_guard().deadline,
                ),
                env.step_cancel,
            ),
            on_progress=lambda p: safe_invoke_progress(env.on_progress, p),
        )

    def _run_locked_leader_step(
        self,
        env: StepExecutionEnv,
        prio_handle: PriorityHandle,
        eff_cancel: CancellationToken,
        flight: Optional[StepFlight[_CoordinatedStepBundle]],
    ) -> _CoordinatedStepBundle:
        group_descs = (
            self._routes.collect_group_descriptors(env.desc) if env.desc.venv_python is not None else (env.desc,)
        )
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
                res, guard_ev = self._step_host.dispatch_to_host(
                    env, prio_handle, eff_cancel, self._build_tier0_callbacks, forbid_retiring_wait=True
                )
            except RetiringGroupBusyError:
                return _CoordinatedStepBundle(StepExecutionResult(ok=False), retry_group_busy=True)
            return _CoordinatedStepBundle(step_result=res, release_guard=guard_ev)

        return self._run_neutral_coalesce_flight(env, prio_handle, eff_cancel, flight)

    def _run_neutral_coalesce_flight(
        self,
        env: StepExecutionEnv,
        prio_handle: PriorityHandle,
        eff_cancel: CancellationToken,
        flight: StepFlight[_CoordinatedStepBundle],
    ) -> _CoordinatedStepBundle:
        flight_tid = flight.flight_id
        step_exec_cancel, unreg_flight_cancel = CancellationToken.combine(eff_cancel)
        flight_scope = TurnScope(turn_id=flight_tid, kind=env.turn.kind, cancel_token=step_exec_cancel)
        hot_ws = frozenset({self._workspace_root}) if self._opts.is_daemon_host else frozenset()
        cold_ws = frozenset({self._workspace_root}) if not self._opts.is_daemon_host else frozenset()
        flight_sess = ActiveTurnSession(
            scope=flight_scope,
            caller_cancel=step_exec_cancel,
            prio_handle=prio_handle,
            root_call_tree_id=flight_tid,
            primary_task_id=str(env.spec.task_id),
            hot_workspaces=hot_ws,
            cold_shared_workspaces=cold_ws,
        )
        neutral_stack = ((env.step_req.workspace_root, env.spec.task_id),)
        capture = StepEventCapture(flight_tid, neutral_stack, eff_cancel, flight, graph_cond=self._shared_ws.cascade_cond)
        neutral_prop = CallPropagationContext(
            turn_id=flight_tid,
            call_tree_id=flight_tid,
            call_stack=neutral_stack,
            is_nested_call=True,
            from_hot_container=self._opts.is_daemon_host,
            hot_workspaces=hot_ws,
            cold_shared_workspaces=cold_ws,
            coalesce_flights=(flight_tid,),
        )
        exec_env = replace(
            env,
            turn=flight_scope,
            step_req=replace(env.step_req, propagation=neutral_prop),
            on_progress=flight.broadcast_progress,
            step_guard=DeadlineGuard(cancel_token=step_exec_cancel, deadline=None),
            dynamic_deadline_fn=flight.effective_deadline,
        )
        self._sessions.register_flight_session(flight_tid, flight_sess, capture)
        td_diags: tuple[ErrorDetail, ...] = ()
        bundle_built = False
        try:
            res, guard_ev = self._step_host.dispatch_to_host(
                exec_env, prio_handle, step_exec_cancel, self._build_tier0_callbacks, forbid_retiring_wait=True
            )
            if res.fatal_abort_turn:
                flight.seal()
            bundle_built = True
        except RetiringGroupBusyError:
            flight.seal()
            return _CoordinatedStepBundle(StepExecutionResult(ok=False), retry_group_busy=True)
        except BaseException:
            flight.seal()
            raise
        finally:
            unreg_flight_cancel()
            self._sessions.remove_step_capture(capture)
            if not bundle_built:
                for cj in capture.child_joins:
                    cj.cascade.detach_caller_slot(cj.slot_id)
            capture.imm_diagnostics.extend(flight_scope.snapshot_event_diagnostics())
            stack_td = flight_scope.scoped_stack.close_all_lifo()
            sess_td = self._sessions.close_managed_session(flight_sess)
            td_diags = (*stack_td, *sess_td)

        return _build_coalesce_flight_bundle(res, guard_ev, capture, flight, prio_handle, td_diags)

    def _recheck_hot_step_before_coord(
        self,
        env: StepExecutionEnv,
        ext_prio: PriorityHandle,
    ) -> tuple[StepExecutionEnv, Optional[StepExecutionResult[JsonValue]]]:
        prop = env.step_req.propagation
        parent_req = replace(env.step_req, propagation=replace(prop, call_stack=prop.call_stack[:-1]))
        rem_tmo = env.current_guard().remaining_ms(env.spec.timeout_ms)
        self._gates.wait_if_module_reloading(
            parent_req, env.step_cancel, self._step_host.is_reentrant_retiring, timeout_ms=rem_tmo
        )
        gate_err, resolved = self._validate_stage1_gates(
            parent_req, in_cold_turn=(env.turn.kind == TurnKind.COLD)
        )
        if gate_err is not None:
            return (
                env,
                StepExecutionResult(ok=False, error=gate_err, fatal_abort_turn=is_fatal_error_code(gate_err.code)),
            )
        new_desc, new_spec = require_non_none(resolved)
        cur_ep = self._gates.current_epoch(new_desc.module_id)
        if new_desc == env.desc and new_spec == env.spec and cur_ep == env.reload_epoch:
            return (env, None)
        next_env = replace(env, desc=new_desc, spec=new_spec, reload_epoch=cur_ep)
        if not next_env.spec.resource_key or next_env.spec.concurrency_mode == ConcurrencyMode.PARALLEL:
            return (next_env, self._dispatch_parallel_step_safe(next_env, ext_prio, next_env.step_cancel))
        return (next_env, None)

    def _coordinate_and_dispatch_step(
        self,
        env: StepExecutionEnv,
        ext_prio: PriorityHandle,
    ) -> StepExecutionResult[JsonValue]:
        _ = require_non_none(env.spec.resource_key)
        allow_coalesce = env.turn.kind != TurnKind.COLD
        group_descs = (
            tuple(self._routes.collect_group_descriptors(env.desc))
            if env.desc.venv_python is not None
            else (env.desc,)
        )
        equiv_key: Optional[str] = None
        while True:
            try:
                if self._opts.is_daemon_host:
                    next_env, early_res = self._recheck_hot_step_before_coord(env, ext_prio)
                    if early_res is not None:
                        return early_res
                    if next_env is not env:
                        env = next_env
                        equiv_key = None
                        group_descs = (
                            tuple(self._routes.collect_group_descriptors(env.desc))
                            if env.desc.venv_python is not None
                            else (env.desc,)
                        )
                coord, equiv_key = self._acquire_single_coord_attempt(
                    env, group_descs, allow_coalesce, equiv_key, ext_prio
                )
            except TaskCancelledException as exc:
                return StepExecutionResult(
                    ok=False, error=exc.detail, preempted=(exc.detail.code == ErrorCode.TASK_PREEMPTED)
                )
            except YscbError as exc:
                return StepExecutionResult(
                    ok=False, error=exc.detail, fatal_abort_turn=is_fatal_error_code(exc.detail.code)
                )
            c_out = require_non_none(coord.outcome)
            if c_out.retry_group_busy:
                try:
                    env.step_cancel.raise_if_cancelled()
                    env.current_guard().remaining_ms(None, expired_message="Timed out waiting for retiring worker group.")
                except TaskCancelledException as exc:
                    return StepExecutionResult(
                        ok=False, error=exc.detail, preempted=(exc.detail.code == ErrorCode.TASK_PREEMPTED)
                    )
                except YscbError as exc:
                    return StepExecutionResult(
                        ok=False, error=exc.detail, fatal_abort_turn=is_fatal_error_code(exc.detail.code)
                    )
                env.step_cancel.wait(0.005)
                continue
            try:
                return self._resolve_coordinated_bundle(env, coord)
            except BaseException:
                if c_out.cascade is not None:
                    c_out.cascade.detach_caller_slot(coord.caller_slot_id)
                raise

    def _resolve_inline_uncontended_bundle(
        self,
        env: StepExecutionEnv,
        bundle: _CoordinatedStepBundle,
        step_res: StepExecutionResult[JsonValue],
    ) -> StepExecutionResult[JsonValue]:
        prop = env.step_req.propagation
        caller_lin = prop.lineage
        fallback_src = str(env.spec.task_id)
        parent_stack = prop.call_stack[:-1]
        for diag in bundle.inline_imm_diags:
            self._sessions.record_imm_or_turn_diagnostic(env.turn, parent_stack, diag)
        if bundle.inline_imm_hops:
            parent_prop = replace(prop, call_stack=parent_stack, turn_id=env.turn.turn_id)
            self._sessions.record_transitive_emitted_hops(parent_prop, bundle.inline_imm_hops)
        try:
            for ehop in bundle.inline_imm_hops:
                _ = caller_lin.advance(
                    ehop.event_id,
                    source_task=ehop.source_task or fallback_src,
                    workspace_scope=ehop.workspace_scope,
                )
            rebased = tuple(
                replace(
                    rec,
                    lineage=advance_hops_checked(
                        caller_lin,
                        rec.lineage.scoped_hops(),
                        source_task=str(rec.emitter_task),
                    ),
                )
                for rec in step_res.committed_events
            )
        except EventCycleError as exc:
            return StepExecutionResult(ok=False, error=exc.detail, fatal_abort_turn=True)
        return replace(step_res, committed_events=rebased)

    def _resolve_coordinated_bundle(
        self,
        env: StepExecutionEnv,
        coord: CoordinatedExecution[_CoordinatedStepBundle],
    ) -> StepExecutionResult[JsonValue]:
        bundle = require_non_none(coord.outcome)
        prop = env.step_req.propagation
        caller_ancestors = prop.call_stack[:-1]
        parent_prop = replace(prop, call_stack=caller_ancestors)
        live_caller_views = self._sessions.snapshot_coalesce_callers(parent_prop, env.turn.turn_id) or prop.coalesce_callers
        cyc_det = _check_caller_invoked_cycle(caller_ancestors, live_caller_views, bundle.invoked_tasks)
        if cyc_det is not None:
            if bundle.cascade is not None:
                bundle.cascade.detach_caller_slot(coord.caller_slot_id)
            return StepExecutionResult(
                ok=False,
                error=cyc_det,
                fatal_abort_turn=True,
                coalesced=coord.is_follower,
            )

        if bundle.invoked_tasks:
            self._sessions.record_transitive_invoked_tasks(
                replace(parent_prop, turn_id=env.turn.turn_id), bundle.invoked_tasks
            )

        if bundle.inline_td_diags:
            self._sessions.record_step_teardown_diags(env.turn, bundle.inline_td_diags)
        step_res = replace(bundle.step_result, coalesced=coord.is_follower)
        if bundle.cascade is None:
            if bundle.needs_lineage_rebase:
                return self._resolve_inline_uncontended_bundle(env, bundle, step_res)
            for diag in bundle.inline_imm_diags:
                self._sessions.record_imm_or_turn_diagnostic(env.turn, caller_ancestors, diag)
            if bundle.inline_imm_hops and step_res.fatal_abort_turn:
                caller_cyc = first_caller_hop_cycle(prop.lineage, bundle.inline_imm_hops, str(env.spec.task_id))
                if caller_cyc is not None:
                    return StepExecutionResult(
                        ok=False,
                        error=caller_cyc,
                        fatal_abort_turn=True,
                        coalesced=coord.is_follower,
                    )
            return step_res

        caller_lineage = prop.lineage
        try:
            bundle.cascade.assert_acyclic(caller_lineage)
        except EventCycleError as exc:
            bundle.cascade.detach_caller_slot(coord.caller_slot_id)
            return StepExecutionResult(
                ok=False,
                error=exc.detail,
                fatal_abort_turn=True,
                coalesced=coord.is_follower,
            )

        fallback_src = str(caller_ancestors[-1][1]) if caller_ancestors else str(env.spec.task_id)
        self._sessions.attach_resolved_cascade(
            env.turn, caller_ancestors, caller_lineage, bundle.cascade, coord.caller_slot_id, fallback_src
        )
        return step_res

    def _acquire_single_coord_attempt(
        self,
        env: StepExecutionEnv,
        group_descs: Sequence[ModuleDescriptor],
        allow_coalesce: bool,
        equiv_key: Optional[str],
        ext_prio: PriorityHandle,
    ) -> tuple[CoordinatedExecution[_CoordinatedStepBundle], str]:
        prop = env.step_req.propagation
        ctree = prop.call_tree_id or env.turn.turn_id
        is_nested = len(prop.call_stack) > 1 or bool(prop.coalesce_callers)
        parent_req = replace(env.step_req, propagation=replace(prop, call_stack=prop.call_stack[:-1]))
        bypass_rel = self._gates.is_request_reload_exempt(parent_req, self._step_host.is_reentrant_retiring)
        q_pre = self._gates.has_leased_pre_quiesce(env.turn.turn_id, ctree) or any(
            self._gates.has_leased_pre_quiesce(c.turn_id, c.call_tree_id) for c in prop.coalesce_callers
        )
        eff_allow_coalesce = allow_coalesce and not bypass_rel and not q_pre
        cur_guard = env.current_guard()
        self._tier1_pool.await_group_ready_before_lock(
            group_descs,
            turn_id=env.turn.turn_id,
            call_tree_id=ctree,
            bypass_reload=bypass_rel,
            cancel_token=env.step_cancel,
            timeout_ms=cur_guard.remaining_ms(env.spec.timeout_ms),
        )
        need_equiv = env.spec.concurrency_mode == ConcurrencyMode.COALESCE and eff_allow_coalesce
        eff_eq = equiv_key or (
            self._step_host.compute_isolated_equiv_key(
                parent_req,
                EquivCallContext(env.turn, ctree, is_nested, env.step_cancel, bypass_rel, cur_guard),
            )
            if need_equiv
            else f"{env.spec.task_id}:direct"
        )
        local_cap = self._sessions.find_innermost_step_capture(env.turn.turn_id, prop.call_stack[:-1])
        tree_caps = self._sessions.find_call_tree_captures(parent_req.propagation, env.turn.turn_id)
        turn_cancel_for_flight = local_cap.flight_cancel if local_cap is not None else env.turn.cancel_token
        enclosing_fl = tuple(c.flight for c in tree_caps)
        live_views = self._sessions.snapshot_coalesce_callers(parent_req.propagation, env.turn.turn_id)
        eff_in_ev = parent_req.propagation.in_event_chain or (
            bool(live_views) and all(v.in_event_chain for v in live_views)
        )
        acq_spec = ResourceAcquireSpec(
            resource_key=env.spec.resource_key,
            mode=env.spec.concurrency_mode,
            equiv_key=eff_eq,
            priority=env.step_req.priority,
            turn_id=env.turn.turn_id,
            call_stack=prop.call_stack,
            cancel_token=env.step_cancel,
            turn_cancel_token=turn_cancel_for_flight,
            timeout_ms=cur_guard.remaining_ms(env.spec.timeout_ms),
            external_priority_handle=ext_prio,
            allow_step_coalesce=eff_allow_coalesce,
            call_tree_id=ctree,
            caller_hops=prop.lineage.scoped_hops(),
            enclosing_flights=enclosing_fl,
            coalesce_callers=live_views,
            coalesce_flights=prop.coalesce_flights,
            turn_entry_stack=self._sessions.get_or_bind_turn_session(env.turn).turn_entry_stack,
            in_event_chain=eff_in_ev,
            on_progress=env.on_progress,
        )
        coord = self._coordinator.execute(
            acq_spec,
            leader_fn=lambda ph, ec, fl: self._run_locked_leader_step(env, ph, ec, fl),
            extract_release_guard=lambda b: b.release_guard,
        )
        return (coord, eff_eq)

    def _invoke_nested_within_turn(
        self,
        turn: Optional[TurnScope],
        spec: _NestedInvokeSpec,
        cancel_token: CancellationToken,
    ) -> TaskOutcome[JsonValue]:
        is_cross_ws = spec.target_workspace != self._workspace_root
        if cancel_token.is_cancelled:
            c_code = ErrorCode.TASK_PREEMPTED if cancel_token.is_preempted else ErrorCode.TASK_CANCELLED
            return TaskOutcome(
                ok=False,
                error=ErrorDetail(c_code, cancel_token.reason or c_code.value, source_task=str(spec.child_task_id)),
                executed_hot=False if is_cross_ws else self._opts.is_daemon_host,
            )
        prop = spec.propagation
        eff_tid = turn.turn_id if turn is not None else (prop.turn_id or "")
        if is_cross_ws or turn is None:
            ext_route = True
        elif turn.kind != TurnKind.COLD or self._opts.is_daemon_host or spec.routing_policy != ClientRoutingPolicy.STRICT_HOT:
            ext_route = False
        else:
            ext_route = True

        try:
            nested_req = self._build_nested_invoke_request(turn, spec, eff_tid, is_cross_ws, ext_route)
            validate_wire_json_object(
                nested_req.raw_input,
                max_depth=MAX_USER_JSON_DEPTH,
                label="InvokeRequest.raw_input",
            )
        except (TypeError, ValueError) as exc:
            return TaskOutcome(
                ok=False,
                error=ErrorDetail(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    safe_exception_summary(exc),
                    source_task=str(spec.child_task_id),
                ),
                executed_hot=False if is_cross_ws else self._opts.is_daemon_host,
            )
        self._sessions.record_capture_invoked_task(turn, prop, (nested_req.workspace_root, nested_req.task_id))
        if ext_route or turn is None:
            cross_guard = DeadlineGuard(cancel_token=cancel_token, deadline=spec.step_deadline)
            raw_res = self._invoke_raw(nested_req, cancel_token=cancel_token, turn_guard=cross_guard)
            if raw_res.emitted_hops and eff_tid:
                self._sessions.record_transitive_emitted_hops(replace(prop, turn_id=eff_tid), raw_res.emitted_hops)
            out = raw_res.outcome
            if not out.ok and out.error is not None and is_fatal_error_code(out.error.code):
                out.error.raise_as_exception()
            return out

        found = self._routes.lookup(nested_req.task_id, ensure_ready=True)
        if turn.kind != TurnKind.COLD or found is None or found[1].mutation_scope == SelfMutationScope.NONE:
            step_res = self._execute_single_step_with_coordination(
                request=nested_req,
                turn=turn,
                parent_step_cancel=cancel_token,
                parent_prio=spec.parent_prio,
                parent_deadline=spec.step_deadline,
            )
        else:
            gate_err, _ = self._validate_stage1_gates(nested_req, in_cold_turn=True)
            if gate_err is not None:
                step_res = StepExecutionResult(
                    ok=False, error=gate_err, fatal_abort_turn=is_fatal_error_code(gate_err.code)
                )
            else:
                nested_prop = nested_req.propagation
                eff_ctree = nested_prop.call_tree_id or turn.turn_id
                excl_req = replace(
                    nested_req,
                    propagation=replace(
                        nested_prop,
                        cold_shared_workspaces=nested_prop.cold_shared_workspaces - frozenset({self._workspace_root}),
                    ),
                )
                step_res = self._cold_locks.run_upgraded_nested(
                    eff_ctree,
                    nested_req.task_id,
                    cancel_token,
                    lambda: self._execute_single_step_with_coordination(
                        request=excl_req,
                        turn=turn,
                        parent_step_cancel=cancel_token,
                        parent_prio=spec.parent_prio,
                        parent_deadline=spec.step_deadline,
                    ),
                    deadline=spec.step_deadline,
                )

        if not step_res.fatal_abort_turn and step_res.committed_events:
            cyc_err = self._check_coalesce_committed_events(turn, prop, step_res.committed_events)
            if cyc_err is not None:
                cyc_err.raise_as_exception()
            self._sessions.record_nested_committed_events(turn, prop.call_stack, step_res.committed_events)
        if step_res.fatal_abort_turn and step_res.error is not None:
            step_res.error.raise_as_exception()
        return TaskOutcome(
            ok=step_res.ok,
            value=step_res.outcome,
            error=step_res.error,
            coalesced=step_res.coalesced,
            executed_hot=self._opts.is_daemon_host,
        )

    def _build_nested_invoke_request(
        self,
        turn: Optional[TurnScope],
        spec: _NestedInvokeSpec,
        eff_tid: str,
        is_cross_ws: bool,
        ext_route: bool,
    ) -> InvokeRequest:
        prop = spec.propagation
        coal_views = self._sessions.snapshot_coalesce_callers(prop, eff_tid)
        eff_in_ev = prop.in_event_chain or (bool(coal_views) and all(v.in_event_chain for v in coal_views))
        strip_scope = is_cross_ws or prop.in_event_chain or any(v.in_event_chain for v in coal_views)
        nested_prop = CallPropagationContext(
            turn_id=None if ext_route else (turn.turn_id if turn is not None else None),
            call_tree_id=prop.call_tree_id or (turn.turn_id if turn is not None else None),
            call_stack=prop.call_stack,
            lineage=prop.lineage,
            is_internal_trigger=False,
            is_nested_call=not ext_route,
            in_event_chain=eff_in_ev,
            from_hot_container=False if ext_route else self._opts.is_daemon_host,
            hot_workspaces=prop.hot_workspaces,
            cold_shared_workspaces=prop.cold_shared_workspaces,
            coalesce_callers=coal_views,
            coalesce_flights=prop.coalesce_flights,
        )
        return InvokeRequest(
            task_id=spec.child_task_id,
            raw_input=spec.raw_input,
            workspace_root=spec.target_workspace,
            caller_cwd=spec.caller_cwd,
            caller_env=spec.caller_env,
            routing_policy=spec.routing_policy,
            priority=spec.parent_prio.current if spec.parent_prio is not None else spec.priority,
            approval_scope=frozenset() if strip_scope else spec.approval_scope,
            allow_conditional=spec.allow_conditional,
            propagation=nested_prop,
        )

    def _evict_or_raise_imm_flight_cycle(
        self,
        cap: StepEventCapture,
        imm_hops: tuple[ScopedHop, ...],
        caps: Sequence[StepEventCapture],
        sess: ActiveTurnSession,
        src_t: Optional[str],
    ) -> None:
        common = cap.flight.find_common_conflicting_hop(imm_hops)
        if common is not None:
            c_src = self._sessions.resolve_hop_source_task(common, caps, sess, src_t or "")
            raise EventCycleError(
                f"Immediate event cycle across all active coalesce callers on '{common[1]}'",
                source_task=c_src or src_t,
            )

        def _make_hop_exc(matched_views: Sequence[CoalesceCallerView]) -> BaseException:
            hit = next(
                (
                    (cs, ce)
                    for cs, ce in imm_hops
                    if any(hop_conflicts(h, cs, ce) for v in matched_views for h in v.caller_hops)
                ),
                imm_hops[-1],
            )
            c_src = self._sessions.resolve_hop_source_task(hit, caps, sess, src_t or "")
            return EventCycleError(
                f"Immediate event cycle across coalesce caller on '{hit[1]}'",
                source_task=c_src or src_t,
            )

        ev, surv = cap.flight.evict_callers_where(
            lambda reg: any(hop_conflicts(h, cs, ce) for h in reg.caller_hops for cs, ce in imm_hops),
            lambda v, _rfl: any(hop_conflicts(h, cs, ce) for h in v.caller_hops for cs, ce in imm_hops),
            _make_hop_exc,
        )
        if not ev and not surv:
            common_post = cap.flight.find_common_conflicting_hop(imm_hops)
            if common_post is not None:
                c_src = self._sessions.resolve_hop_source_task(common_post, caps, sess, src_t or "")
                raise EventCycleError(
                    f"Immediate event cycle across all active coalesce callers on '{common_post[1]}'",
                    source_task=c_src or src_t,
                )

    def _dispatch_immediate_event(self, spec: _ImmediateEventDispatchSpec, turn: TurnScope) -> None:
        if spec.parent_step_cancel is not None:
            spec.parent_step_cancel.raise_if_cancelled()
        prop = spec.propagation
        imm_hops = prop.lineage.scoped_hops()
        src_t = str(spec.emitter_task) if spec.emitter_task is not None else None
        em_hops = tuple(
            EmittedEventHop(
                workspace_scope=ws_s,
                event_id=eid,
                source_task=(src_t if idx == len(imm_hops) - 1 else None),
            )
            for idx, (ws_s, eid) in enumerate(imm_hops)
        )
        self._sessions.record_transitive_emitted_hops(replace(prop, turn_id=turn.turn_id), em_hops)
        caps = self._sessions.find_call_tree_captures(prop, turn.turn_id)
        sess = self._sessions.get_or_bind_turn_session(turn)
        for cap in caps:
            self._evict_or_raise_imm_flight_cycle(cap, imm_hops, caps, sess, src_t)
        eff_views = prop.coalesce_callers or live_session_coalesce_views(sess)
        common_v = find_common_view_conflicting_hop(eff_views, imm_hops[-1:])
        if common_v is not None:
            raise EventCycleError(
                f"Immediate event cycle across all active coalesce callers on '{common_v[1]}'",
                source_task=src_t,
            )

        batch = EventBatchEnvelope(
            event_id=spec.event_id,
            ordering=EventOrdering.ORDERED,
            payloads=(spec.raw_payload,),
            merged_lineage=prop.lineage,
        )
        default_prio = (
            ExecutionPriority.BACKGROUND if turn.kind == TurnKind.HOT_BACKGROUND else ExecutionPriority.FOREGROUND
        )
        eff_ph = spec.parent_prio or PriorityHandle(default_prio)
        for m in self._routes.find_matching_subscribers(spec.event_id):
            if spec.parent_step_cancel is not None and spec.parent_step_cancel.is_cancelled:
                spec.parent_step_cancel.raise_if_cancelled()
            if turn.kind == TurnKind.COLD and m.spec.dispatch_mode == DispatchMode.DAEMON_ONLY:
                continue
            filtered, _ = batch.filter_for_subscription(m.sub.payload_filter)
            if not filtered:
                continue
            self._run_single_immediate_subscriber(m.desc, m.spec, spec, filtered, eff_ph, sess)

    def _fail_or_record_imm_subscriber(
        self,
        spec: _ImmediateEventDispatchSpec,
        turn: TurnScope,
        sub_task_id: TaskId,
        err: ErrorDetail,
    ) -> None:
        det = err.with_fallback_task(str(sub_task_id))
        if spec.strict:
            det.raise_as_exception()
        if det.code == ErrorCode.TASK_PREEMPTED:
            return
        if det.code == ErrorCode.TASK_CANCELLED and (
            turn.cancel_token.is_cancelled
            or (spec.parent_step_cancel is not None and spec.parent_step_cancel.is_cancelled)
        ):
            return
        self._sessions.record_imm_or_turn_diagnostic(turn, spec.propagation.call_stack, det)

    def _run_single_immediate_subscriber(
        self,
        desc: ModuleDescriptor,
        route_spec: TaskRouteSpec,
        spec: _ImmediateEventDispatchSpec,
        filtered: tuple[JsonObject, ...],
        eff_ph: PriorityHandle,
        sess: ActiveTurnSession,
    ) -> None:
        turn = sess.scope
        prop = spec.propagation
        eff_ctree = prop.call_tree_id or turn.turn_id
        imm_base = replace(
            prop,
            is_nested_call=True,
            coalesce_callers=self._sessions.snapshot_coalesce_callers(prop, turn.turn_id),
        )
        imm_req = self._build_event_subscriber_request(
            route_spec.task_id, turn.turn_id, eff_ctree, eff_ph.current, imm_base
        )
        eff_tok = spec.parent_step_cancel or turn.cancel_token
        imm_dl = merge_deadlines(sess.turn_deadline, spec.step_deadline)
        imm_guard = DeadlineGuard(cancel_token=eff_tok, deadline=imm_dl)
        sub_err, desc, route_spec = self._prepare_subscriber_target(imm_req, desc, route_spec, eff_tok, imm_guard)
        if sub_err is not None:
            self._fail_or_record_imm_subscriber(spec, turn, route_spec.task_id, sub_err)
            return
        m_out = self._step_host.map_event_batch(
            desc,
            route_spec.task_id,
            spec.event_id,
            filtered,
            EquivCallContext(turn=turn, call_tree_id=eff_ctree, cancel_token=spec.parent_step_cancel, guard=imm_guard),
        )
        if not m_out.ok:
            if m_out.error is not None:
                self._fail_or_record_imm_subscriber(spec, turn, route_spec.task_id, m_out.error)
            return
        if m_out.skip:
            return
        sub_res = self._execute_single_step_with_coordination(
            request=replace(imm_req, raw_input=m_out.mapped_input),
            turn=turn,
            parent_step_cancel=spec.parent_step_cancel,
            parent_prio=eff_ph,
            parent_deadline=imm_dl,
        )
        self._handle_imm_subscriber_outcome(sub_res, route_spec.task_id, spec, turn)

    def _handle_imm_subscriber_outcome(
        self,
        sub_res: StepExecutionResult[JsonValue],
        sub_task_id: TaskId,
        spec: _ImmediateEventDispatchSpec,
        turn: TurnScope,
    ) -> None:
        if sub_res.fatal_abort_turn and sub_res.error is not None:
            sub_res.error.raise_as_exception()
        if spec.parent_step_cancel is not None and spec.parent_step_cancel.is_cancelled:
            spec.parent_step_cancel.raise_if_cancelled()
        call_stack = spec.propagation.call_stack
        if not sub_res.fatal_abort_turn and sub_res.committed_events:
            cyc_err = self._check_coalesce_committed_events(turn, spec.propagation, sub_res.committed_events)
            if cyc_err is not None:
                cyc_err.raise_as_exception()
            self._sessions.record_nested_committed_events(turn, call_stack, sub_res.committed_events)
        if not sub_res.ok and sub_res.error is not None:
            if spec.strict:
                sub_res.error.with_fallback_task(str(sub_task_id)).raise_as_exception()
            if not sub_res.preempted:
                self._fail_or_record_imm_subscriber(spec, turn, sub_task_id, sub_res.error)
