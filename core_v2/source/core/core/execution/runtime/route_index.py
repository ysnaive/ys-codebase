"""Route index registry, O(1) subscriber lookup, and atomic index-degraded SSOT synchronization."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Optional, Sequence

from core.execution.lifecycle import ContainerState, LifoResourceStack, WorkerContainerLifecycle
from core.execution.runtime.contracts import (
    INSTALLER_LOCK_FILENAME,
    LOCKS_SUBDIR,
    ModuleDescriptor,
    ModuleProviderPort,
    SubscriptionRouteSpec,
    TaskRouteSpec,
)
from core.execution.runtime.gates import LifecycleReloadGate
from core.execution.runtime.module_slot import LocalModuleSlotRegistry
from core.execution.runtime.worker_pool import tier1_group_key_for
from core.filesystem.fs import try_acquire_contained_lock
from core.foundation.errors import ErrorCode, ErrorDetail, YscbError, safe_exception_summary
from core.foundation.primitives import EventId, HostPath, ModuleId, TaskId


@dataclass(frozen=True, slots=True)
class MatchedSubscriber:
    """Resolved module descriptor, task route, and matching subscription specification."""

    desc: ModuleDescriptor
    spec: TaskRouteSpec
    sub: SubscriptionRouteSpec


def _build_event_indexes(
    route_entries: Sequence[tuple[ModuleDescriptor, TaskRouteSpec]],
) -> tuple[dict[EventId, tuple[MatchedSubscriber, ...]], dict[EventId, frozenset[ModuleId]]]:
    by_ev: dict[EventId, list[MatchedSubscriber]] = {}
    mods_by_ev: dict[EventId, set[ModuleId]] = {}
    for desc, spec in route_entries:
        for sub in spec.subscriptions:
            by_ev.setdefault(sub.event_id, []).append(MatchedSubscriber(desc, spec, sub))
            mods_by_ev.setdefault(sub.event_id, set()).add(desc.module_id)
    return (
        {eid: tuple(items) for eid, items in by_ev.items()},
        {eid: frozenset(mids) for eid, mids in mods_by_ev.items()},
    )


class RouteIndexRegistry:
    """Thread-safe route table synchronizing ModuleProviderPort manifests, O(1) event maps, and index diagnostics."""

    def __init__(
        self,
        *,
        cache_dir: HostPath,
        is_daemon_host: bool,
        module_provider: ModuleProviderPort,
        tier0_slots: LocalModuleSlotRegistry,
        container: WorkerContainerLifecycle,
        gates: LifecycleReloadGate,
    ) -> None:
        self._workspace_root = tier0_slots.workspace_root
        self._cache_dir = cache_dir
        self._is_daemon_host = is_daemon_host
        self._module_provider = module_provider
        self._tier0_slots = tier0_slots
        self._container = container
        self._gates = gates
        self._lock = threading.RLock()
        self._route_index: dict[TaskId, tuple[ModuleDescriptor, TaskRouteSpec]] = {}
        self._route_specs: tuple[TaskRouteSpec, ...] = ()
        self._subscribers_by_event: dict[EventId, tuple[MatchedSubscriber, ...]] = {}
        self._subscribed_modules_by_event: dict[EventId, frozenset[ModuleId]] = {}
        self._deferred_boot_index = False

    def init_index(self) -> None:
        if not self._is_daemon_host:
            self.rebuild()
            return
        probe = try_acquire_contained_lock(self._cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME, shared=True)
        if probe is not None:
            try:
                self.rebuild()
            finally:
                probe.release()
            return
        with self._lock:
            self._deferred_boot_index = True
        self.rebuild(manifest_only=True)

    def _has_deferred_boot_index(self) -> bool:
        with self._lock:
            return self._deferred_boot_index

    def ensure_ready(self) -> None:
        if not self._has_deferred_boot_index():
            return
        probe = try_acquire_contained_lock(self._cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME, shared=True)
        if probe is None:
            return
        try:
            with self._gates.lifecycle_scope():
                if self._has_deferred_boot_index():
                    self._module_provider.reload()
                    self.rebuild()
        finally:
            probe.release()

    def lookup(
        self,
        task_id: TaskId,
        *,
        ensure_ready: bool = False,
    ) -> Optional[tuple[ModuleDescriptor, TaskRouteSpec]]:
        if ensure_ready:
            self.ensure_ready()
        with self._lock:
            return self._route_index.get(task_id)

    def list_route_specs(self) -> tuple[TaskRouteSpec, ...]:
        self.ensure_ready()
        with self._lock:
            return self._route_specs

    def find_matching_subscribers(self, event_id: EventId) -> list[MatchedSubscriber]:
        self.ensure_ready()
        with self._lock:
            return list(self._subscribers_by_event.get(event_id, ()))

    def subscribed_modules_for_event(self, event_id: EventId) -> frozenset[ModuleId]:
        self.ensure_ready()
        with self._lock:
            return self._subscribed_modules_by_event.get(event_id, frozenset())

    def collect_group_descriptors(self, primary: ModuleDescriptor) -> list[ModuleDescriptor]:
        gkey = tier1_group_key_for(primary)
        all_mods = self._module_provider.list_modules()
        grouped = [d for d in all_mods if d.venv_python is not None and tier1_group_key_for(d) == gkey]
        return grouped if grouped else [primary]

    def resolve_fresh_group_descriptors(
        self,
        group_key: str,
        fallback: Sequence[ModuleDescriptor],
    ) -> Sequence[ModuleDescriptor]:
        all_mods = self._module_provider.list_modules()
        fresh = [d for d in all_mods if d.venv_python is not None and tier1_group_key_for(d) == group_key]
        return fresh if fresh else fallback

    def is_reentrant_retiring_for_module(
        self,
        task_id: TaskId,
        has_retiring_fn: Callable[[str, str, str], bool],
        turn_id: str,
        call_tree_id: str,
        coalesce_turns: Sequence[tuple[str, str]],
    ) -> bool:
        found = self.lookup(task_id)
        desc = found[0] if found is not None else self._module_provider.get_module(task_id.module_id)
        if desc is None or desc.venv_python is None:
            return False
        gkey = tier1_group_key_for(desc)
        if has_retiring_fn(gkey, turn_id, call_tree_id):
            return True
        return any(has_retiring_fn(gkey, c_tid, c_tree) for c_tid, c_tree in coalesce_turns)

    def rebuild(self, *, manifest_only: bool = False) -> None:
        descriptors = list(self._module_provider.list_modules())
        tier0_descs = [d for d in descriptors if d.venv_python is None]
        self._tier0_slots.register_descriptors(tier0_descs)
        present_mods = {d.module_id for d in descriptors}
        stale_deg = frozenset(m for m in self._container.degraded_modules if m not in present_mods)
        if stale_deg:
            self._container.clear_degraded(stale_deg)

        prev_errors = self._container.snapshot_index_degraded()
        with self._lock:
            prev_snap = list(self._route_index.values())
        prev_by_mod: dict[ModuleId, list[TaskRouteSpec]] = {}
        for prev_d, prev_spec in prev_snap:
            prev_by_mod.setdefault(prev_d.module_id, []).append(prev_spec)

        next_errors = _detect_conflicting_venv_group_modules(descriptors)
        new_index: dict[TaskId, tuple[ModuleDescriptor, TaskRouteSpec]] = {}
        for d in descriptors:
            if d.module_id in next_errors:
                continue
            specs = self._collect_descriptor_routes(d, prev_by_mod, prev_errors, next_errors, manifest_only)
            if d.module_id not in next_errors:
                _index_module_routes(d, specs, new_index, next_errors)

        entries = tuple(new_index.values())
        subs_by_ev, mods_by_ev = _build_event_indexes(entries)
        self._container.sync_index_degraded(next_errors)
        with self._lock:
            self._route_index = new_index
            self._route_specs = tuple(spec for _desc, spec in entries)
            self._subscribers_by_event = subs_by_ev
            self._subscribed_modules_by_event = mods_by_ev
            if not manifest_only:
                self._deferred_boot_index = False

    def _should_skip_dynamic_introspection(self, mod_id: ModuleId, manifest_only: bool) -> bool:
        if manifest_only:
            return True
        if not self._is_daemon_host:
            return False
        if self._container.state in (ContainerState.DRAINING, ContainerState.STOPPED):
            return True
        return self._gates.is_module_quiesced(mod_id)

    def _collect_descriptor_routes(
        self,
        desc: ModuleDescriptor,
        prev_by_mod: dict[ModuleId, list[TaskRouteSpec]],
        prev_errors: dict[ModuleId, ErrorDetail],
        next_errors: dict[ModuleId, ErrorDetail],
        manifest_only: bool,
    ) -> Sequence[TaskRouteSpec]:
        if desc.declared_tasks:
            return desc.declared_tasks
        if desc.venv_python is not None:
            return ()
        if self._should_skip_dynamic_introspection(desc.module_id, manifest_only):
            if desc.module_id in prev_errors:
                next_errors[desc.module_id] = prev_errors[desc.module_id]
            return prev_by_mod.get(desc.module_id, ())
        return self._introspect_tier0_routes(desc, next_errors)

    def _introspect_tier0_routes(
        self,
        descriptor: ModuleDescriptor,
        next_errors: dict[ModuleId, ErrorDetail],
    ) -> tuple[TaskRouteSpec, ...]:
        if self._is_daemon_host:
            return _load_routes_from_slots(self._tier0_slots, descriptor.module_id, next_errors)
        temp_stack = LifoResourceStack()
        temp_slots = LocalModuleSlotRegistry(self._workspace_root, temp_stack)
        temp_slots.register_descriptors([descriptor])
        try:
            return _load_routes_from_slots(temp_slots, descriptor.module_id, next_errors)
        finally:
            temp_slots.unload_modules(frozenset({descriptor.module_id}))
            temp_stack.close_all_lifo()


def _detect_conflicting_venv_group_modules(descriptors: Sequence[ModuleDescriptor]) -> dict[ModuleId, ErrorDetail]:
    by_grp: dict[str, list[ModuleDescriptor]] = {}
    for d in descriptors:
        if d.venv_python is not None and d.venv_group is not None:
            by_grp.setdefault(d.venv_group, []).append(d)
    errors: dict[ModuleId, ErrorDetail] = {}
    for grp_name, members in by_grp.items():
        if len({m.venv_python for m in members}) > 1:
            for m in members:
                errors[m.module_id] = ErrorDetail(
                    ErrorCode.MODULE_DEGRADED,
                    f"Module '{m.module_id}' in venv_group '{grp_name}' has conflicting venv_python.",
                )
    return errors


def _index_module_routes(
    desc: ModuleDescriptor,
    specs: Sequence[TaskRouteSpec],
    out_index: dict[TaskId, tuple[ModuleDescriptor, TaskRouteSpec]],
    next_errors: dict[ModuleId, ErrorDetail],
) -> None:
    mod_routes: list[TaskRouteSpec] = []
    seen_ids: set[TaskId] = set()
    for spec in specs:
        if spec.task_id.module_id != desc.module_id or spec.task_id in seen_ids or spec.task_id in out_index:
            next_errors[desc.module_id] = ErrorDetail(
                ErrorCode.MODULE_DEGRADED,
                f"Module '{desc.module_id}' declared invalid or conflicting route '{spec.task_id}'.",
            )
            return
        seen_ids.add(spec.task_id)
        mod_routes.append(spec)
    for spec in mod_routes:
        out_index[spec.task_id] = (desc, spec)


def _load_routes_from_slots(
    slots: LocalModuleSlotRegistry,
    mod_id: ModuleId,
    next_errors: dict[ModuleId, ErrorDetail],
) -> tuple[TaskRouteSpec, ...]:
    try:
        return slots.introspect_bound_route_specs(mod_id)
    except YscbError as exc:
        if exc.detail.code not in (ErrorCode.DAEMON_UNAVAILABLE, ErrorCode.TASK_NOT_FOUND):
            next_errors[mod_id] = exc.detail
        return ()
    except (Exception, SystemExit, GeneratorExit) as exc:
        next_errors[mod_id] = ErrorDetail(
            ErrorCode.MODULE_DEGRADED,
            f"Module '{mod_id}' route introspection failed: {safe_exception_summary(exc)}",
        )
        return ()
