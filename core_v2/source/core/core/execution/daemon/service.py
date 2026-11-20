"""WorkspaceDaemon, _DirtyPathsAccumulator, SingleFlightDaemonSpawner, IdleTtlMonitor, and PeriodicTriggerLoop."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import os
from pathlib import Path
import signal
import stat
import threading
import time
from typing import Callable, Mapping, Optional, Sequence
import uuid

from core.execution.lifecycle import ContainerState
from core.execution.rpc import (
    DAEMON_ENDPOINT_FILENAME,
    DAEMON_HANDOFF_FILENAME,
    DAEMON_SUBDIR,
    FrameKind,
    InboundCallHandler,
    RpcServerListener,
    build_daemon_endpoint_dict,
    build_handoff_lease_dict,
    probe_daemon_endpoint,
    read_active_handoff_boot_id,
)
from core.execution.runtime import (
    CONFIG_CHANGED_EVENT_ID,
    CORE_MODULE_ID,
    INSTALLER_LOCK_FILENAME,
    LOCKS_SUBDIR,
    MODULES_DIRNAME,
    CallPropagationContext,
    DaemonRpcInvokeReply,
    ConfigViewPort,
    DaemonSpawner,
    DueQuiesceResume,
    ExecutionPriority,
    InvokeRequest,
    RuntimeDispatcher,
    TaskRouteSpec,
    VfsEchoGuardPort,
    WorkerProcessSnapshot,
)
from core.filesystem.fs import (
    IGNORED_FS_PREFIXES,
    FileLock,
    PollingDirectoryWatcher,
    atomic_write_json,
    hash_nofollow_regular_sha256,
    is_atomic_staging_filename,
    is_symlink_or_reparse,
    read_json_dict,
    resolve_contained_subpath,
    silent_unlink_contained,
    try_acquire_contained_lock,
    try_resolve_contained_subpath,
    walk_nonsymlink_dir_tree,
)
from core.foundation.codec import DataclassCodec
from core.foundation.errors import ErrorCode, ErrorDetail, TaskCancelledException, YscbError, safe_exception_summary
from core.foundation.observability import (
    clamp_positive_sec,
    MAX_SAFE_WAIT_SEC,
    CancellationToken,
    DeadlineGuard,
    safe_real_to_float,
    validate_non_negative_sec,
)
from core.foundation.primitives import (
    IS_WINDOWS,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    TaskId,
    require_non_none,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    require_typed_frozenset,
    require_typed_tuple,
)
from core.foundation.proc import SignalWakeupGuard, is_process_alive, spawn_detached

DaemonRunState = ContainerState


_HANDOFF_LEASE_SUBPATH: tuple[str, str] = (DAEMON_SUBDIR, DAEMON_HANDOFF_FILENAME)
_DAEMON_LOCK_FILENAME: str = "daemon.lock"
_SPAWN_LOCK_FILENAME: str = "spawn.lock"
_SPAWN_LEASE_FILENAME: str = "spawn_lease.json"


@dataclass(frozen=True, slots=True)
class DaemonStatusSnapshot:
    state: ContainerState
    pid: int
    boot_id: str
    port: int
    uptime_sec: float
    idle_ttl_remaining_sec: Optional[float]
    active_foreground_calls: int
    tasks_handled: int
    active_tier1_workers: tuple[WorkerProcessSnapshot, ...]
    degraded_modules: tuple[str, ...] = ()
    background_error_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.state, ContainerState):
            raise ValueError(f"DaemonStatusSnapshot.state must be ContainerState, got {self.state!r}")
        require_pure_int(self.pid, "DaemonStatusSnapshot.pid", min_val=0)
        require_pure_int(self.port, "DaemonStatusSnapshot.port", min_val=0, max_val=65535)
        require_pure_int(self.active_foreground_calls, "DaemonStatusSnapshot.active_foreground_calls", min_val=0)
        require_pure_int(self.tasks_handled, "DaemonStatusSnapshot.tasks_handled", min_val=0)
        require_pure_int(self.background_error_count, "DaemonStatusSnapshot.background_error_count", min_val=0)
        up_s = validate_non_negative_sec(self.uptime_sec, label="uptime_sec")
        if up_s is None:
            raise ValueError("DaemonStatusSnapshot.uptime_sec required.")
        object.__setattr__(self, "uptime_sec", up_s)
        if self.idle_ttl_remaining_sec is not None:
            ttl_s = validate_non_negative_sec(self.idle_ttl_remaining_sec, label="idle_ttl_remaining_sec")
            object.__setattr__(self, "idle_ttl_remaining_sec", ttl_s)
        require_pure_str(self.boot_id, "DaemonStatusSnapshot.boot_id")
        object.__setattr__(
            self,
            "active_tier1_workers",
            require_typed_tuple(self.active_tier1_workers, WorkerProcessSnapshot, "active_tier1_workers"),
        )
        object.__setattr__(
            self, "degraded_modules", require_typed_tuple(self.degraded_modules, str, "degraded_modules")
        )


@dataclass(frozen=True, slots=True)
class DaemonQuiesceControl:
    modules: tuple[ModuleId, ...] = ()
    lease_sec: float = 10.0
    drain_timeout_sec: float = 3.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "modules", require_typed_tuple(self.modules, ModuleId, "DaemonQuiesceControl.modules"))
        s_lease = validate_non_negative_sec(self.lease_sec, label="lease_sec")
        s_drain = validate_non_negative_sec(self.drain_timeout_sec, label="drain_timeout_sec")
        if s_lease is None or s_lease <= 0.0 or s_drain is None or s_drain <= 0.0:
            raise ValueError("DaemonQuiesceControl lease_sec and drain_timeout_sec must be finite and > 0.")
        object.__setattr__(self, "lease_sec", s_lease)
        object.__setattr__(self, "drain_timeout_sec", s_drain)


@dataclass(frozen=True, slots=True)
class DaemonResumeControl:
    modules: tuple[ModuleId, ...] = ()
    expected_epoch: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "modules", require_typed_tuple(self.modules, ModuleId, "DaemonResumeControl.modules"))
        if self.expected_epoch is not None:
            require_pure_int(self.expected_epoch, "DaemonResumeControl.expected_epoch", min_val=0)


@dataclass(frozen=True, slots=True)
class DaemonReloadControl:
    modules: tuple[ModuleId, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "modules", require_typed_tuple(self.modules, ModuleId, "DaemonReloadControl.modules"))


@dataclass(frozen=True, slots=True)
class DaemonStopControl:
    force: bool = False
    core_handoff: bool = False

    def __post_init__(self) -> None:
        require_pure_bool(self.force, "DaemonStopControl.force")
        require_pure_bool(self.core_handoff, "DaemonStopControl.core_handoff")


@dataclass(frozen=True, slots=True)
class DaemonWatcherConfig:
    """Watcher and background callback configuration for WorkspaceDaemon."""

    echo_guard: Optional[VfsEchoGuardPort] = None
    space_watch_roots: tuple[HostPath, ...] = ()
    config_watch_roots: tuple[HostPath, ...] = ()
    on_space_changed_task: Optional[TaskId] = None
    on_config_changed_task: Optional[TaskId] = None
    watcher_debounce_sec: float = 0.5

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "space_watch_roots", require_typed_tuple(self.space_watch_roots, HostPath, "space_watch_roots")
        )
        object.__setattr__(
            self, "config_watch_roots", require_typed_tuple(self.config_watch_roots, HostPath, "config_watch_roots")
        )
        if self.on_space_changed_task is not None and not isinstance(self.on_space_changed_task, TaskId):
            raise ValueError("on_space_changed_task must be TaskId or None.")
        if self.on_config_changed_task is not None and not isinstance(self.on_config_changed_task, TaskId):
            raise ValueError("on_config_changed_task must be TaskId or None.")
        safe_deb = validate_non_negative_sec(self.watcher_debounce_sec, label="watcher_debounce_sec")
        if safe_deb is None or safe_deb <= 0.0:
            raise ValueError(f"watcher_debounce_sec must be finite and > 0, got {self.watcher_debounce_sec!r}")
        object.__setattr__(self, "watcher_debounce_sec", safe_deb)


@dataclass(frozen=True, slots=True)
class _CoreFileSig:
    mtime_ns: int
    size: int
    ino: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _DirtyBatch:
    reload_all: bool = False
    reload_modules: frozenset[ModuleId] = frozenset()
    module_paths: frozenset[HostPath] = frozenset()
    config_paths: frozenset[HostPath] = frozenset()
    notify_config_paths: frozenset[HostPath] = frozenset()
    space_paths: frozenset[HostPath] = frozenset()

    @property
    def has_any(self) -> bool:
        return bool(
            self.reload_all
            or self.reload_modules
            or self.module_paths
            or self.config_paths
            or self.notify_config_paths
            or self.space_paths
        )


class _DirtyPathsAccumulator:
    """Thread-safe O(1) dirty-path buffer decoupling Watchers from Daemon lifecycle locks."""

    __slots__ = (
        "_lock",
        "_reload_all",
        "_reload_modules",
        "_module_paths",
        "_config_paths",
        "_notify_config_paths",
        "_space_paths",
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reload_all = False
        self._reload_modules: set[ModuleId] = set()
        self._module_paths: set[HostPath] = set()
        self._config_paths: set[HostPath] = set()
        self._notify_config_paths: set[HostPath] = set()
        self._space_paths: set[HostPath] = set()

    @property
    def has_pending(self) -> bool:
        with self._lock:
            return bool(
                self._reload_all
                or self._reload_modules
                or self._module_paths
                or self._config_paths
                or self._notify_config_paths
                or self._space_paths
            )

    def add_reload(self, modules: frozenset[ModuleId]) -> None:
        with self._lock:
            if modules:
                self._reload_modules.update(modules)
            else:
                self._reload_all = True

    def add_module_paths(self, paths: frozenset[HostPath]) -> None:
        if paths:
            with self._lock:
                self._module_paths.update(paths)

    def add_config_paths(self, paths: frozenset[HostPath]) -> None:
        if paths:
            with self._lock:
                self._config_paths.update(paths)

    def add_notify_config_paths(self, paths: frozenset[HostPath]) -> None:
        if paths:
            with self._lock:
                self._notify_config_paths.update(paths)

    def add_space_paths(self, paths: frozenset[HostPath]) -> None:
        if paths:
            with self._lock:
                self._space_paths.update(paths)

    def drain_ready(
        self,
        quiesced_mods: frozenset[ModuleId],
        mods_root: Optional[Path],
        *,
        space_gated: bool = False,
        config_gated: bool = False,
    ) -> _DirtyBatch:
        with self._lock:
            if not quiesced_mods:
                r_all = self._reload_all
                self._reload_all = False
                ready_mods = frozenset(self._reload_modules)
                self._reload_modules.clear()
                ready_mpaths = frozenset(self._module_paths)
                self._module_paths.clear()
            else:
                r_all = False
                blocked = quiesced_mods | frozenset({CORE_MODULE_ID})
                ready_mods = frozenset(m for m in self._reload_modules if m not in blocked)
                self._reload_modules.difference_update(ready_mods)
                ready_mpaths = frozenset(
                    p for p in self._module_paths if not _is_path_in_modules(p, mods_root, blocked)
                )
                self._module_paths.difference_update(ready_mpaths)
            ready_cfg = frozenset() if config_gated else frozenset(self._config_paths)
            ready_ncfg = frozenset() if config_gated else frozenset(self._notify_config_paths)
            if not config_gated:
                self._config_paths.clear()
                self._notify_config_paths.clear()
            ready_space = frozenset() if space_gated else frozenset(self._space_paths)
            if not space_gated:
                self._space_paths.clear()
            return _DirtyBatch(
                reload_all=r_all,
                reload_modules=ready_mods,
                module_paths=ready_mpaths,
                config_paths=ready_cfg,
                notify_config_paths=ready_ncfg,
                space_paths=ready_space,
            )

    def drain_config_paths(self) -> frozenset[HostPath]:
        with self._lock:
            cfg = frozenset(self._config_paths)
            self._config_paths.clear()
            return cfg

    def clear_all_modules(self) -> None:
        with self._lock:
            self._reload_all = False
            self._reload_modules.clear()
            self._module_paths.clear()

    def prune_modules(self, mods: frozenset[ModuleId], mods_root: Optional[Path]) -> None:
        if not mods:
            return
        with self._lock:
            self._reload_modules.difference_update(mods)
            if mods_root is not None:
                self._module_paths = {p for p in self._module_paths if not _is_path_in_modules(p, mods_root, mods)}

    def has_explicit_core_reload(self) -> bool:
        with self._lock:
            return CORE_MODULE_ID in self._reload_modules


class SingleFlightDaemonSpawner(DaemonSpawner):
    """Implements DaemonSpawner using non-blocking .cache/daemon/spawn.lock and wall-clock spawn lease."""

    def __init__(
        self,
        cache_dir: HostPath,
        daemon_argv_builder: Callable[[HostPath], Sequence[str]],
        *,
        lease_cooldown_sec: float = 1.5,
        sandbox_restricted: bool = False,
    ) -> None:
        self._cache_dir = cache_dir
        self._argv_builder = daemon_argv_builder
        self._lease_cooldown_sec = require_non_none(
            validate_non_negative_sec(lease_cooldown_sec, label="lease_cooldown_sec")
        )
        self._sandbox_restricted = sandbox_restricted

    def can_spawn_in_environment(self) -> bool:
        return not self._sandbox_restricted

    def try_spawn_background(self, workspace_root: HostPath) -> bool:
        if not self.can_spawn_in_environment():
            return False
        if probe_daemon_endpoint(self._cache_dir, workspace_root) is not None:
            return False

        try:
            lock = FileLock(resolve_contained_subpath(self._cache_dir, DAEMON_SUBDIR, _SPAWN_LOCK_FILENAME), allow_transitions=False)
            if not lock.acquire(blocking=False):
                return False
        except (OSError, ValueError, YscbError):
            return False

        try:
            if probe_daemon_endpoint(self._cache_dir, workspace_root) is not None:
                return False
            lease_path = resolve_contained_subpath(self._cache_dir, DAEMON_SUBDIR, _SPAWN_LEASE_FILENAME)
            now_epoch = time.time()
            if _is_spawn_lease_active(read_json_dict(lease_path), now_epoch, self._lease_cooldown_sec):
                return False
            argv = list(self._argv_builder(workspace_root))
            spawned_pid = spawn_detached(argv, cwd=workspace_root)
            atomic_write_json(lease_path, {"spawned_epoch": now_epoch, "pid": spawned_pid})
            return True
        except (OSError, ValueError, YscbError):
            return False
        finally:
            lock.release()


def _is_spawn_lease_active(
    lease_data: Optional[JsonObject],
    now_epoch: float,
    cooldown_sec: float,
) -> bool:
    if lease_data is None:
        return False
    ts_raw = lease_data.get("spawned_epoch", 0.0)
    pid_raw = lease_data.get("pid", 0)
    try:
        last_ts = safe_real_to_float(ts_raw)
    except ValueError:
        return False
    lease_pid = pid_raw if isinstance(pid_raw, int) and not isinstance(pid_raw, bool) else 0
    if not math.isfinite(last_ts) or lease_pid <= 0:
        return False
    return 0.0 <= (now_epoch - last_ts) < cooldown_sec and is_process_alive(lease_pid)


def _normalize_idle_ttl_sec(ttl_sec: Optional[float]) -> Optional[float]:
    if ttl_sec is None:
        return None
    f_val = safe_real_to_float(ttl_sec, label="ttl_sec")
    if math.isnan(f_val):
        raise ValueError(f"IdleTtlMonitor ttl_sec must be a real number or None, got {ttl_sec!r}")
    if f_val <= 0.0 or math.isinf(f_val):
        return None
    return min(MAX_SAFE_WAIT_SEC, f_val)


class IdleTtlMonitor:
    """Tracks external foreground activity timestamps without allowing background polls to reset Idle TTL."""

    def __init__(self, ttl_sec: Optional[float]) -> None:
        self._ttl_sec = _normalize_idle_ttl_sec(ttl_sec)
        self._lock = threading.Lock()
        self._last_activity = time.monotonic()

    @property
    def ttl_sec(self) -> Optional[float]:
        return self._ttl_sec

    def record_external_activity(self) -> None:
        with self._lock:
            self._last_activity = time.monotonic()

    def remaining_sec(self) -> Optional[float]:
        if self._ttl_sec is None:
            return None
        with self._lock:
            elapsed = time.monotonic() - self._last_activity
        return max(0.0, self._ttl_sec - elapsed)

    def is_expired(self) -> bool:
        rem = self.remaining_sec()
        return rem is not None and rem <= 0.0


class PeriodicTriggerLoop:
    """Zero-wakeup idle, exact-sleep, config-gated fixed-delay periodic task trigger."""

    def __init__(
        self,
        *,
        dispatcher: RuntimeDispatcher,
        config_view: Optional[ConfigViewPort],
        can_run_background: Callable[[], bool],
        execute_periodic_task: Callable[[TaskId], None],
        can_run_task: Optional[Callable[[TaskId], bool]] = None,
        on_error: Optional[Callable[[ErrorDetail], None]] = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._config_view = config_view
        self._can_run_bg = can_run_background
        self._can_run_task = can_run_task
        self._exec_periodic = execute_periodic_task
        self._on_error = on_error
        self._cond = threading.Condition()
        self._wake_seq = 0
        self._stopped = True
        self._starting = False
        self._next_due: dict[TaskId, float] = {}
        self._last_base: dict[TaskId, float] = {}
        self._in_flight: set[TaskId] = set()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        with self._cond:
            if (self._thread is not None and self._thread.is_alive()) or self._starting:
                return
            self._stopped = False
            self._starting = True
        try:
            self.refresh_schedules()
        except BaseException:
            with self._cond:
                self._starting = False
            raise
        with self._cond:
            self._starting = False
            if self._stopped or (self._thread is not None and self._thread.is_alive()):
                return
            t = threading.Thread(target=self._loop, name="yscb-periodic-loop", daemon=True)
            try:
                t.start()
            except BaseException:
                self._stopped = True
                self._thread = None
                raise
            self._thread = t

    def refresh_schedules(self) -> None:
        now = time.monotonic()
        specs = self._dispatcher.list_route_specs()
        with self._cond:
            seen_ids: set[TaskId] = set()
            for spec in specs:
                if spec.periodic is None:
                    continue
                seen_ids.add(spec.task_id)
                enabled, interval = self._resolve_periodic_config(spec)
                if not enabled:
                    self._next_due.pop(spec.task_id, None)
                    self._last_base.pop(spec.task_id, None)
                    continue
                base = self._last_base.get(spec.task_id)
                if spec.task_id not in self._in_flight:
                    self._next_due[spec.task_id] = max(now, base + interval) if base is not None else now
            for stale_tid in [tid for tid in list(self._next_due.keys() | self._last_base.keys()) if tid not in seen_ids]:
                self._next_due.pop(stale_tid, None)
                self._last_base.pop(stale_tid, None)
            self._wake_seq += 1
            self._cond.notify_all()

    def wake(self) -> None:
        with self._cond:
            self._wake_seq += 1
            self._cond.notify_all()

    def stop(self, *, drain_timeout_sec: float = 3.0) -> None:
        safe_drain = max(0.05, require_non_none(validate_non_negative_sec(drain_timeout_sec, label="drain_timeout_sec")))
        with self._cond:
            self._stopped = True
            self._cond.notify_all()
            t = self._thread
            self._thread = None
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2.0)
        deadline = time.monotonic() + safe_drain
        with self._cond:
            while self._in_flight and time.monotonic() < deadline:
                self._cond.wait(timeout=0.02)

    def _resolve_periodic_config(self, spec: TaskRouteSpec) -> tuple[bool, float]:
        p = require_non_none(spec.periodic)
        mod_id = spec.task_id.module_id
        enabled = True
        if p.enabled_config_key is not None:
            raw_en = self._config_view.get_module_value(mod_id, p.enabled_config_key, False) if self._config_view is not None else False
            enabled = raw_en is True
        interval = clamp_positive_sec(p.default_interval_sec, min_sec=0.05, max_sec=604800.0, default_sec=60.0)
        if p.interval_config_key is not None and self._config_view is not None:
            raw_iv = self._config_view.get_module_value(mod_id, p.interval_config_key, interval)
            if not isinstance(raw_iv, bool) and isinstance(raw_iv, (int, float)):
                f_iv = safe_real_to_float(raw_iv)
                if math.isfinite(f_iv) and f_iv > 0.0:
                    interval = clamp_positive_sec(f_iv, min_sec=0.05, max_sec=604800.0, default_sec=interval)
        return (enabled, interval)

    def _loop(self) -> None:
        while True:
            with self._cond:
                if self._stopped:
                    return
            try:
                due_list = self._wait_and_pop_due_specs()
            except (Exception, SystemExit, GeneratorExit) as exc:
                if self._on_error is not None:
                    self._on_error(
                        ErrorDetail(
                            ErrorCode.BUSINESS_FAILURE,
                            f"Periodic scheduler poll failed: {safe_exception_summary(exc)}",
                        )
                    )
                time.sleep(0.05)
                continue
            for spec in due_list:
                self._spawn_periodic_worker(spec)

    def _spawn_periodic_worker(self, spec: TaskRouteSpec) -> None:
        try:
            threading.Thread(
                target=self._run_periodic_once,
                args=(spec,),
                name=f"yscb-periodic-{spec.task_id}",
                daemon=True,
            ).start()
        except BaseException as exc:
            with self._cond:
                self._in_flight.discard(spec.task_id)
                self._cond.notify_all()
            if not isinstance(exc, Exception):
                raise
            if self._on_error is not None:
                self._on_error(
                    ErrorDetail(
                        ErrorCode.BUSINESS_FAILURE,
                        f"Periodic thread spawn failed for '{spec.task_id}': {safe_exception_summary(exc)}",
                        source_task=str(spec.task_id),
                    )
                )

    def _snapshot_runnable_periodic_specs(self) -> dict[TaskId, TaskRouteSpec]:
        if not self._can_run_bg():
            return {}
        return {
            s.task_id: s
            for s in self._dispatcher.list_route_specs()
            if s.periodic is not None
            and (self._can_run_task is None or self._can_run_task(s.task_id))
            and self._resolve_periodic_config(s)[0]
        }

    def _wait_and_pop_due_specs(self) -> list[TaskRouteSpec]:
        with self._cond:
            snap_seq = self._wake_seq
        runnable = self._snapshot_runnable_periodic_specs()
        due_specs: list[TaskRouteSpec] = []
        with self._cond:
            if self._stopped or self._wake_seq != snap_seq:
                return []
            eligible_dues = [
                due_at
                for tid, due_at in self._next_due.items()
                if tid in runnable and tid not in self._in_flight
            ]
            if not eligible_dues:
                self._cond.wait(timeout=3600.0 if self._next_due else None)
                return []
            now = time.monotonic()
            wait_sec = min(eligible_dues) - now
            if wait_sec > 0:
                self._cond.wait(timeout=min(wait_sec, 3600.0))
                return []
            self._collect_due_locked(now, runnable, due_specs)
        return due_specs

    def _collect_due_locked(
        self,
        now: float,
        runnable: dict[TaskId, TaskRouteSpec],
        due_specs: list[TaskRouteSpec],
    ) -> None:
        for tid, due_at in list(self._next_due.items()):
            if now < due_at or tid in self._in_flight or tid not in runnable:
                continue
            spec = runnable[tid]
            self._next_due.pop(tid, None)
            self._in_flight.add(tid)
            due_specs.append(spec)

    def _safe_post_periodic_schedule(self, spec: TaskRouteSpec) -> tuple[bool, float]:
        try:
            latest = next(
                (s for s in self._dispatcher.list_route_specs() if s.task_id == spec.task_id and s.periodic is not None),
                None,
            )
            if latest is None:
                return (False, 0.0)
            return self._resolve_periodic_config(latest)
        except (Exception, SystemExit, GeneratorExit) as exc:
            if self._on_error is not None:
                self._on_error(
                    ErrorDetail(
                        ErrorCode.BUSINESS_FAILURE,
                        f"Post-periodic schedule refresh failed for '{spec.task_id}': {safe_exception_summary(exc)}",
                        source_task=str(spec.task_id),
                    )
                )
            p = spec.periodic
            if p is None:
                return (False, 0.0)
            return (p.enabled_config_key is None, clamp_positive_sec(p.default_interval_sec, min_sec=0.05, max_sec=604800.0, default_sec=60.0))

    def _commit_periodic_completion(self, spec: TaskRouteSpec) -> None:
        while True:
            with self._cond:
                snap_seq = self._wake_seq
            enabled, interval = self._safe_post_periodic_schedule(spec)
            with self._cond:
                if self._wake_seq != snap_seq:
                    continue
                self._in_flight.discard(spec.task_id)
                done_now = time.monotonic()
                if enabled and not self._stopped:
                    self._last_base[spec.task_id] = done_now
                    self._next_due[spec.task_id] = done_now + interval
                else:
                    self._next_due.pop(spec.task_id, None)
                    self._last_base.pop(spec.task_id, None)
                self._wake_seq += 1
                self._cond.notify_all()
                return

    def _run_periodic_once(self, spec: TaskRouteSpec) -> None:
        try:
            self._exec_periodic(spec.task_id)
        except (Exception, SystemExit, GeneratorExit) as exc:
            if self._on_error is not None:
                self._on_error(
                    ErrorDetail(
                        ErrorCode.BUSINESS_FAILURE,
                        f"Periodic task '{spec.task_id}' raised: {safe_exception_summary(exc)}",
                        source_task=str(spec.task_id),
                    )
                )
        finally:
            self._commit_periodic_completion(spec)


def _resolve_diag_owners(diag: ErrorDetail, scope_mods: frozenset[ModuleId]) -> frozenset[ModuleId]:
    head = (diag.source_task or "").split(".", 1)[0]
    if head and head != "tier1_pool":
        try:
            return frozenset({ModuleId(head)})
        except ValueError:
            pass
    return scope_mods


def _extract_module_id_under(p: HostPath, mods_root: Optional[Path]) -> Optional[ModuleId]:
    if mods_root is None:
        return None
    try:
        rel = p.path.relative_to(mods_root)
    except ValueError:
        return None
    if not rel.parts or rel.parts[0].startswith("."):
        return None
    try:
        return ModuleId(rel.parts[0])
    except ValueError:
        return None


def _is_path_in_modules(p: HostPath, mods_root: Optional[Path], targets: frozenset[ModuleId]) -> bool:
    mid = _extract_module_id_under(p, mods_root)
    return mid is not None and mid in targets


def _extract_payload_propagation(payload: JsonObject) -> Optional[CallPropagationContext]:
    raw_p = payload.get("propagation")
    if not isinstance(raw_p, Mapping):
        return None
    try:
        return DataclassCodec.decode(CallPropagationContext, raw_p)
    except (YscbError, KeyError, ValueError, TypeError):
        return None


def _extract_payload_module_id(payload: JsonObject) -> Optional[ModuleId]:
    raw_tid = payload.get("task_id")
    if not isinstance(raw_tid, str):
        return None
    try:
        return TaskId(raw_tid).module_id
    except ValueError:
        return None


def _is_installer_exclusively_locked(cache_dir: HostPath) -> bool:
    probe = try_acquire_contained_lock(cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME, shared=True)
    if probe is None:
        return True
    probe.release()
    return False


def _write_handoff_lease(cache_dir: HostPath, old_boot_id: str, ttl_sec: float) -> None:
    try:
        lease_file = resolve_contained_subpath(cache_dir, *_HANDOFF_LEASE_SUBPATH)
        clamped_ttl = clamp_positive_sec(ttl_sec, min_sec=0.5, max_sec=30.0, default_sec=10.0)
        atomic_write_json(lease_file, build_handoff_lease_dict(old_boot_id, time.time() + clamped_ttl))
    except (OSError, ValueError, YscbError):
        return


def _record_core_dir_files(
    dir_path: str,
    filenames: Sequence[str],
    snap: dict[str, _CoreFileSig],
    cached: Optional[Mapping[str, _CoreFileSig]],
) -> None:
    for fname in filenames:
        if is_atomic_staging_filename(fname) or fname.endswith(".pyc"):
            continue
        fpath = os.path.join(dir_path, fname)
        try:
            st = os.stat(fpath, follow_symlinks=False)
            prev = cached.get(fpath) if cached is not None else None
            if prev is not None and (prev.mtime_ns, prev.size, prev.ino) == (st.st_mtime_ns, st.st_size, st.st_ino):
                snap[fpath] = prev
                continue
            is_reg = not is_symlink_or_reparse(fpath) and stat.S_ISREG(st.st_mode)
            digest = hash_nofollow_regular_sha256(fpath, expected_stat=st) if is_reg else ""
            snap[fpath] = _CoreFileSig(st.st_mtime_ns, st.st_size, st.st_ino, digest)
        except OSError:
            continue


def _is_nonsymlink_dir_entry(ent: os.DirEntry[str]) -> bool:
    if ent.is_symlink() or is_symlink_or_reparse(ent.path):
        return False
    try:
        return ent.is_dir(follow_symlinks=False)
    except OSError:
        return False


def _scan_core_module_tree(
    workspace_root: HostPath,
    cached: Optional[Mapping[str, _CoreFileSig]] = None,
) -> dict[str, _CoreFileSig]:
    core_hp = try_resolve_contained_subpath(workspace_root, MODULES_DIRNAME, str(CORE_MODULE_ID))
    if core_hp is None or not os.path.isdir(str(core_hp)):
        return {}
    snap: dict[str, _CoreFileSig] = {}
    for cur_dir, entries in walk_nonsymlink_dir_tree(str(core_hp)):
        fnames = sorted(
            ent.name
            for ent in entries
            if not ent.name.startswith(IGNORED_FS_PREFIXES) and not _is_nonsymlink_dir_entry(ent)
        )
        _record_core_dir_files(cur_dir, fnames, snap, cached)
    return snap


class WorkspaceDaemon(InboundCallHandler):
    """Per-workspace daemon shell delegating module/quiesce gates to RuntimeDispatcher SSOT."""

    def __init__(
        self,
        *,
        workspace_root: HostPath,
        cache_dir: HostPath,
        dispatcher: RuntimeDispatcher,
        config_view: Optional[ConfigViewPort] = None,
        watch_config: DaemonWatcherConfig = DaemonWatcherConfig(),
        self_restart_argv: Optional[Sequence[str]] = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._cache_dir = cache_dir
        self._dispatcher = dispatcher
        self._config_view = config_view
        self._watch_cfg = watch_config
        self._self_restart_argv = tuple(self_restart_argv) if self_restart_argv else None

        self._cond = threading.Condition()
        self._stopping = False
        dispatcher.container_lifecycle.transition_boot_phase(ContainerState.BOOTING)
        self._active_fg_calls = 0
        self._active_bg_turns = 0
        self._lifecycle_ops_in_flight = 0
        self._tasks_handled = 0
        self._quiesce_waiters = 0
        self._handoff_lease_lock = threading.Lock()
        self._explicit_stop_latched = False
        self._pending_core_handoff = False
        self._force_shutdown = False
        self._supervisor_active = False
        self._shutdown_started = False
        self._dispatcher_stopped = False
        self._shutdown_diagnostics: tuple[ErrorDetail, ...] = ()
        self._bg_teardown_diags: deque[tuple[frozenset[ModuleId], ErrorDetail]] = deque(maxlen=256)
        self._bg_error_diags: deque[ErrorDetail] = deque(maxlen=256)
        self._started_at = time.monotonic()

        self._dirty = _DirtyPathsAccumulator()
        self._stopped = False
        self._boot_warming_active = False
        self._deferred_boot_warmup = False
        self._inst_wait_cancels: set[CancellationToken] = set()
        self._pending_ready_callback: Optional[Callable[[], None]] = None
        self._pending_startup_catchup = False

        self._daemon_lock = FileLock(resolve_contained_subpath(cache_dir, DAEMON_SUBDIR, _DAEMON_LOCK_FILENAME), allow_transitions=False)
        _ = resolve_contained_subpath(cache_dir, DAEMON_SUBDIR, DAEMON_ENDPOINT_FILENAME)
        _ = resolve_contained_subpath(cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME)
        self._listener = RpcServerListener(workspace_root, self)
        self._idle_monitor = IdleTtlMonitor(None)
        self._periodic_loop = PeriodicTriggerLoop(
            dispatcher=dispatcher,
            config_view=config_view,
            can_run_background=self._can_run_any_background,
            can_run_task=lambda tid: self._can_run_any_background() and not dispatcher.reload_gate.is_call_gated_for_quiesce(tid.module_id),
            execute_periodic_task=lambda tid: self._trigger_bg_task(tid, {}),
            on_error=self._record_bg_error_diag,
        )
        self._watchers: list[PollingDirectoryWatcher] = []
        self._modules_watcher: Optional[PollingDirectoryWatcher] = None
        self._config_watcher: Optional[PollingDirectoryWatcher] = None
        self._boot_core_snapshot = _scan_core_module_tree(workspace_root)
        self._dispatcher.reload_gate.register_gate_listener(self._wake_cond)

    def _wake_cond(self) -> None:
        with self._cond:
            self._cond.notify_all()
        self._periodic_loop.wake()

    @property
    def quiesce_epoch(self) -> int:
        return self._dispatcher.reload_gate.quiesce_epoch

    def _record_bg_error_diag(self, detail: ErrorDetail) -> None:
        with self._cond:
            self._bg_error_diags.append(detail)

    def drain_background_errors(self) -> tuple[ErrorDetail, ...]:
        with self._cond:
            if not self._bg_error_diags:
                return ()
            out = tuple(self._bg_error_diags)
            self._bg_error_diags.clear()
            return out

    def _base_phase_locked(self) -> ContainerState:
        lc_base = self._dispatcher.container_lifecycle.base_state
        if self._stopped or lc_base == ContainerState.STOPPED:
            return ContainerState.STOPPED
        if self._stopping or lc_base == ContainerState.DRAINING:
            return ContainerState.DRAINING
        if (self._boot_warming_active or self._deferred_boot_warmup) and lc_base == ContainerState.READY:
            return ContainerState.WARMING
        return lc_base

    def _effective_state_locked(self) -> ContainerState:
        base = self._base_phase_locked()
        if base in (ContainerState.WARMING, ContainerState.READY):
            if self._dispatcher.container_lifecycle.state == ContainerState.QUIESCED:
                return ContainerState.QUIESCED
        return base

    def _can_run_any_background(self) -> bool:
        with self._cond:
            if self._base_phase_locked() != ContainerState.READY or self._deferred_boot_warmup:
                return False
        return not self._dispatcher.reload_gate.is_globally_gated()

    def _resolve_default_idle_ttl(self) -> Optional[float]:
        default_ttl = 1800.0
        if self._config_view is None:
            return default_ttl
        try:
            raw_val = self._config_view.get_module_value(CORE_MODULE_ID, "idle_timeout_sec", default_ttl)
        except (Exception, SystemExit, GeneratorExit):
            return default_ttl
        if raw_val is None:
            return None
        return clamp_positive_sec(
            raw_val,
            min_sec=0.05,
            max_sec=MAX_SAFE_WAIT_SEC,
            default_sec=default_ttl,
            label="idle_timeout_sec",
        )

    def run_forever(
        self,
        *,
        ttl_override_sec: Optional[float] = None,
        console_mode: bool = False,
        ready_callback: Optional[Callable[[], None]] = None,
    ) -> int:
        if ttl_override_sec is not None:
            effective_ttl: Optional[float] = ttl_override_sec
        elif console_mode:
            effective_ttl = None
        else:
            effective_ttl = self._resolve_default_idle_ttl()
        norm_ttl = _normalize_idle_ttl_sec(effective_ttl)
        if not self._acquire_daemon_singleton_lock():
            return 0

        handoff_argv: Optional[tuple[str, ...]] = None
        sig_guard: Optional[SignalWakeupGuard] = None
        try:
            sig_guard = self._install_main_thread_signals()
            with self._cond:
                self._supervisor_active = True
            self._boot_and_publish_endpoint(norm_ttl, ready_callback)
            self._run_supervisor_loop()
            handoff_argv = self._drain_before_shutdown()
        finally:
            with self._cond:
                self._supervisor_active = False
                self._cond.notify_all()
            self._teardown_all_resources(sig_guard)

        if handoff_argv is not None:
            self._spawn_handoff_successor(handoff_argv)
        return 0

    def _acquire_daemon_singleton_lock(self) -> bool:
        if self._daemon_lock.acquire(blocking=False):
            return True
        if read_active_handoff_boot_id(self._cache_dir) is None:
            return False
        try:
            return self._daemon_lock.acquire(shared=False, blocking=True, timeout_sec=0.25)
        except YscbError:
            return False

    def _finish_deferred_boot_warmup(self) -> None:
        if not self._is_warming_deferred_boot():
            return
        inst_lock = self._acquire_cancellable_shared_installer_lock(timeout_sec=30.0)
        if inst_lock is None:
            return
        try:
            if self._is_warming_deferred_boot():
                leased_now = self._dispatcher.reload_gate.active_quiesced_modules()
                self._execute_synchronous_quiesce_resume(None, None, leased_now)
        finally:
            inst_lock.release()

    def _run_supervisor_loop(self) -> None:
        gate = self._dispatcher.reload_gate
        while True:
            due_resume: Optional[DueQuiesceResume] = None
            dirty_batch: Optional[_DirtyBatch] = None
            probe_deferred_boot = False
            stop_due_to_ttl = False
            cfg_consumers = self._config_consumer_modules() if gate.has_any_quiesced() else frozenset()
            with self._cond:
                if self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED):
                    return
                now = time.monotonic()
                due_resume = gate.due_quiesce_resume(now) if gate.has_any_quiesced() else None
                if due_resume is None and self._check_idle_ttl_expired_locked():
                    self._stopping = True
                    self._cond.notify_all()
                    stop_due_to_ttl = True
                elif due_resume is None and self._base_phase_locked() == ContainerState.WARMING and self._deferred_boot_warmup:
                    probe_deferred_boot = not gate.is_globally_quiesced()
                    if not probe_deferred_boot:
                        self._cond.wait(timeout=self._compute_supervisor_sleep_locked(now))
                elif due_resume is None:
                    dirty_batch = self._claim_dirty_batch_if_ready_locked(cfg_consumers)
                    if dirty_batch is None:
                        self._cond.wait(timeout=self._compute_supervisor_sleep_locked(now))

            if stop_due_to_ttl:
                self._listener.stop_accepting()
                return
            if dirty_batch is not None and dirty_batch.has_any:
                self._run_dirty_batch_counted(dirty_batch)
                continue
            if not probe_deferred_boot and due_resume is None:
                continue
            locked_excl = _is_installer_exclusively_locked(self._cache_dir)
            if probe_deferred_boot and not locked_excl:
                self._finish_deferred_boot_warmup()
                continue
            if due_resume is not None and not locked_excl:
                self._run_due_quiesce_resume(due_resume)
                continue
            if due_resume is not None:
                gate.postpone_due_lease(due_resume.epoch, due_resume.modules, 0.05)
            with self._cond:
                self._cond.wait(timeout=0.05)

    def _config_consumer_modules(self) -> frozenset[ModuleId]:
        base = self._dispatcher.subscribed_modules(CONFIG_CHANGED_EVENT_ID)
        cfg_task = self._watch_cfg.on_config_changed_task
        return base if cfg_task is None else (base | frozenset({cfg_task.module_id}))

    def _claim_dirty_batch_if_ready_locked(
        self,
        cfg_consumers: frozenset[ModuleId],
    ) -> Optional[_DirtyBatch]:
        gate = self._dispatcher.reload_gate
        if (
            self._base_phase_locked() != ContainerState.READY
            or self._deferred_boot_warmup
            or self._quiesce_waiters > 0
            or self._lifecycle_ops_in_flight > 0
            or gate.is_globally_gated()
            or not self._dirty.has_pending
        ):
            return None
        q_mods = gate.active_quiesced_modules()
        space_tid = self._watch_cfg.on_space_changed_task
        space_gated = bool(q_mods) and space_tid is not None and gate.is_call_gated_for_quiesce(space_tid.module_id)
        cfg_gated = bool(q_mods) and any(gate.is_call_gated_for_quiesce(m) for m in cfg_consumers)
        batch = self._dirty.drain_ready(
            q_mods,
            self._contained_modules_path(),
            space_gated=space_gated,
            config_gated=cfg_gated,
        )
        if not batch.has_any:
            return None
        self._active_bg_turns += 1
        self._lifecycle_ops_in_flight += 1
        return batch

    def _finish_lifecycle_reload_op(self, pending_cfg: frozenset[HostPath]) -> None:
        with self._cond:
            self._lifecycle_ops_in_flight = max(0, self._lifecycle_ops_in_flight - 1)
            if not pending_cfg:
                self._active_bg_turns = max(0, self._active_bg_turns - 1)
            self._cond.notify_all()
        if pending_cfg:
            try:
                threading.Thread(
                    target=self._run_async_config_notifications,
                    args=(pending_cfg,),
                    name="yscb-cfg-notify",
                    daemon=True,
                ).start()
            except BaseException as exc:
                self._requeue_notify_config_paths(pending_cfg)
                with self._cond:
                    self._active_bg_turns = max(0, self._active_bg_turns - 1)
                    self._cond.notify_all()
                if not isinstance(exc, Exception):
                    raise
                self._record_bg_error_diag(
                    ErrorDetail(
                        ErrorCode.BUSINESS_FAILURE,
                        f"Config notification thread spawn failed: {safe_exception_summary(exc)}",
                    )
                )

    def _run_dirty_batch_counted(self, dirty_batch: _DirtyBatch) -> None:
        pending_cfg: frozenset[HostPath] = frozenset()
        try:
            pending_cfg = self._process_dirty_batch(dirty_batch)
        finally:
            self._finish_lifecycle_reload_op(pending_cfg)

    def _run_async_config_notifications(self, paths: frozenset[HostPath]) -> None:
        try:
            self._emit_config_changed_notifications(paths)
        finally:
            with self._cond:
                self._active_bg_turns = max(0, self._active_bg_turns - 1)
                self._cond.notify_all()

    def _check_idle_ttl_expired_locked(self) -> bool:
        if (
            self._base_phase_locked() != ContainerState.READY
            or self._dispatcher.reload_gate.has_any_quiesced()
            or self._active_fg_calls > 0
            or self._active_bg_turns > 0
        ):
            return False
        return self._idle_monitor.is_expired() and not self._dirty.has_pending

    def _compute_supervisor_sleep_locked(self, now: float) -> Optional[float]:
        wake_q = self._dispatcher.reload_gate.next_quiesce_wakeup(now)
        rem_ttl = self._idle_monitor.remaining_sec() if self._base_phase_locked() == ContainerState.READY else None
        ttl_s = min(MAX_SAFE_WAIT_SEC, max(0.01, rem_ttl)) if rem_ttl is not None else None
        raw_sleep = min(wake_q, ttl_s) if (wake_q is not None and ttl_s is not None) else (wake_q if wake_q is not None else ttl_s)
        return min(MAX_SAFE_WAIT_SEC, max(0.001, raw_sleep)) if raw_sleep is not None else None

    def _spawn_handoff_successor(self, handoff_argv: tuple[str, ...]) -> None:
        with self._cond:
            if self._explicit_stop_latched or not self._pending_core_handoff:
                silent_unlink_contained(self._cache_dir, *_HANDOFF_LEASE_SUBPATH)
                return
        try:
            sp_lock = FileLock(resolve_contained_subpath(self._cache_dir, DAEMON_SUBDIR, _SPAWN_LOCK_FILENAME), allow_transitions=False)
            sp_lock.acquire(shared=False, blocking=True, timeout_sec=5.0)
        except (OSError, ValueError, YscbError):
            silent_unlink_contained(self._cache_dir, *_HANDOFF_LEASE_SUBPATH)
            return
        try:
            if probe_daemon_endpoint(self._cache_dir, self._workspace_root) is not None:
                silent_unlink_contained(self._cache_dir, *_HANDOFF_LEASE_SUBPATH)
                return
            lease_path = resolve_contained_subpath(self._cache_dir, DAEMON_SUBDIR, _SPAWN_LEASE_FILENAME)
            if _is_spawn_lease_active(read_json_dict(lease_path), time.time(), 1.5):
                return
            inst_lk = try_acquire_contained_lock(
                self._cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME, shared=True, timeout_sec=5.0
            )
            if inst_lk is not None:
                inst_lk.release()
            ep = self._listener.endpoint
            _write_handoff_lease(self._cache_dir, ep.boot_id if ep is not None else "", ttl_sec=6.0)
            succ_pid = spawn_detached(handoff_argv, cwd=self._workspace_root)
            atomic_write_json(lease_path, {"spawned_epoch": time.time(), "pid": succ_pid})
        except (OSError, ValueError, YscbError):
            silent_unlink_contained(self._cache_dir, *_HANDOFF_LEASE_SUBPATH)
        finally:
            sp_lock.release()

    def _install_main_thread_signals(self) -> SignalWakeupGuard:
        sigs = (int(signal.SIGINT), int(signal.SIGTERM), int(signal.SIGBREAK)) if IS_WINDOWS else (
            int(signal.SIGINT),
            int(signal.SIGTERM),
        )
        guard = SignalWakeupGuard(
            sigs,
            self.request_shutdown,
            on_second_signal=lambda: self.request_shutdown(force=True),
        )
        guard.install()
        return guard

    def _boot_and_publish_endpoint(
        self,
        effective_ttl: Optional[float],
        ready_callback: Optional[Callable[[], None]],
    ) -> None:
        self._idle_monitor = IdleTtlMonitor(effective_ttl)
        boot_tok = CancellationToken()
        with self._cond:
            if self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED):
                return
            self._boot_warming_active = True
            self._dispatcher.container_lifecycle.transition_boot_phase(ContainerState.WARMING)
            self._inst_wait_cancels.add(boot_tok)
            self._pending_ready_callback = ready_callback
            self._pending_startup_catchup = self._watch_cfg.on_space_changed_task is not None
        try:
            self._start_watchers_only()
            ep = self._listener.start(pid=os.getpid())
            daemon_json_path = resolve_contained_subpath(self._cache_dir, DAEMON_SUBDIR, DAEMON_ENDPOINT_FILENAME)
            atomic_write_json(
                daemon_json_path,
                build_daemon_endpoint_dict(ep),
                file_mode=0o600,
            )
            deferred = self._run_initial_boot_warmup(boot_tok)
        except BaseException:
            with self._cond:
                self._boot_warming_active = False
            raise
        finally:
            with self._cond:
                self._inst_wait_cancels.discard(boot_tok)
        aborted_boot = False
        with self._cond:
            self._boot_warming_active = False
            if self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED):
                aborted_boot = True
            elif not deferred and self._base_phase_locked() == ContainerState.WARMING:
                self._dispatcher.container_lifecycle.transition_boot_phase(ContainerState.READY)
            self._idle_monitor.record_external_activity()
            self._cond.notify_all()
        with self._handoff_lease_lock:
            with self._cond:
                clear_lease = not self._pending_core_handoff
            if clear_lease:
                silent_unlink_contained(self._cache_dir, *_HANDOFF_LEASE_SUBPATH)
        if aborted_boot:
            return
        self._periodic_loop.start()
        self._consume_and_fire_post_boot_hooks()

    def _consume_and_fire_post_boot_hooks(self) -> None:
        cb: Optional[Callable[[], None]] = None
        need_catchup = False
        with self._cond:
            if self._base_phase_locked() != ContainerState.READY or self._dispatcher.reload_gate.is_globally_gated():
                return
            cb = self._pending_ready_callback
            self._pending_ready_callback = None
            need_catchup = self._pending_startup_catchup
            self._pending_startup_catchup = False
        if cb is not None:
            cb()
        if not need_catchup or self._watch_cfg.on_space_changed_task is None:
            return
        if self._spawn_detached_bg_task(
            self._watch_cfg.on_space_changed_task,
            {"changed_paths": [], "startup_catchup": True},
        ):
            return
        with self._cond:
            if self._base_phase_locked() not in (ContainerState.DRAINING, ContainerState.STOPPED):
                self._pending_startup_catchup = True

    def _acquire_cancellable_shared_installer_lock(
        self,
        timeout_sec: float,
        *,
        require_ready: bool = False,
    ) -> Optional[FileLock]:
        tok = CancellationToken()
        with self._cond:
            not_ready = (self._base_phase_locked() != ContainerState.READY) if require_ready else (
                self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED)
            )
            if self._quiesce_waiters > 0 or not_ready:
                return None
            self._inst_wait_cancels.add(tok)
        try:
            return try_acquire_contained_lock(
                self._cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME, shared=True, timeout_sec=timeout_sec, cancel_token=tok
            )
        finally:
            with self._cond:
                self._inst_wait_cancels.discard(tok)

    def _run_initial_boot_warmup(self, boot_tok: CancellationToken) -> bool:
        inst_lock = try_acquire_contained_lock(
            self._cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME, shared=True, timeout_sec=30.0, cancel_token=boot_tok
        )
        with self._cond:
            self._inst_wait_cancels.discard(boot_tok)
            if inst_lock is None:
                if self._base_phase_locked() not in (ContainerState.DRAINING, ContainerState.STOPPED):
                    self._deferred_boot_warmup = True
                self._cond.notify_all()
                return True
        need_handoff = False
        try:
            with self._dispatcher.reload_gate.lifecycle_scope():
                if self._has_deferred_core_mutation():
                    need_handoff = True
                else:
                    self._dispatcher.reload_config_and_contributes(emit_event=False)
                    self._dispatcher.warmup_daemon_container()
                    need_handoff = self._apply_warmup_queued_reloads_locked()
        finally:
            inst_lock.release()
        if need_handoff:
            self.request_shutdown(core_handoff=True)
            return True
        return False

    def _apply_warmup_queued_reloads_locked(self) -> bool:
        if self._has_deferred_core_mutation():
            return True
        gate = self._dispatcher.reload_gate
        if gate.is_globally_gated():
            return False
        q_mods = gate.active_quiesced_modules()
        batch = self._dirty.drain_ready(
            q_mods, self._contained_modules_path(), space_gated=True, config_gated=True
        )
        raw_mods = batch.reload_modules | frozenset(self._extract_touched_modules(batch.module_paths))
        if CORE_MODULE_ID in raw_mods:
            return True
        target = frozenset() if batch.reload_all else (raw_mods - frozenset({CORE_MODULE_ID}))
        if batch.reload_all or target:
            drained_cfg = self._resync_watchers_before_reload(target)
            if drained_cfg:
                self._dirty.add_config_paths(drained_cfg)
            self._dispatcher.reload_affected_modules(target)
            if self._has_deferred_core_mutation():
                return True
        return False

    def _is_warming_deferred_boot(self) -> bool:
        with self._cond:
            return self._base_phase_locked() == ContainerState.WARMING and self._deferred_boot_warmup

    def _cancel_installer_lock_waits_locked(self) -> None:
        for tok in list(self._inst_wait_cancels):
            tok.cancel(reason="yield_to_quiesce")
        self._inst_wait_cancels.clear()

    def _release_singleton_registration(self) -> None:
        if not self._daemon_lock.is_acquired:
            return
        silent_unlink_contained(self._cache_dir, DAEMON_SUBDIR, DAEMON_ENDPOINT_FILENAME)
        doc = read_json_dict(self._cache_dir, DAEMON_SUBDIR, _SPAWN_LEASE_FILENAME)
        if doc is None or doc.get("pid") == os.getpid():
            silent_unlink_contained(self._cache_dir, DAEMON_SUBDIR, _SPAWN_LEASE_FILENAME)
        self._daemon_lock.release()

    def _execute_full_shutdown(self, *, force: bool) -> tuple[ErrorDetail, ...]:
        should_stop_io = False
        with self._cond:
            if self._dispatcher_stopped:
                return self._shutdown_diagnostics
            if not self._shutdown_started:
                self._shutdown_started = True
                should_stop_io = True
        if should_stop_io:
            self._listener.stop_accepting()
            self._stop_watchers_and_periodic()
        with self._dispatcher.reload_gate.lifecycle_scope():
            with self._cond:
                if self._dispatcher_stopped:
                    return self._shutdown_diagnostics
            diags: tuple[ErrorDetail, ...] = ()
            try:
                diags = self._dispatcher.shutdown(grace_ms=300 if force else 3000)
            except (Exception, SystemExit, GeneratorExit) as exc:
                diags = (ErrorDetail(code=ErrorCode.TEARDOWN_ERROR, message=safe_exception_summary(exc)),)
            finally:
                self._release_singleton_registration()
                with self._cond:
                    diags = (*(d for _, d in self._bg_teardown_diags), *diags)
                    self._bg_teardown_diags.clear()
                    self._shutdown_diagnostics = diags
                    self._dispatcher_stopped = True
                    self._cond.notify_all()
            return diags

    def _drain_before_shutdown(self) -> Optional[tuple[str, ...]]:
        with self._cond:
            force = self._force_shutdown
        self._execute_full_shutdown(force=force)
        self._listener.flush_inbound_controls(timeout_sec=2.0)
        with self._cond:
            return self._self_restart_argv if self._pending_core_handoff else None

    def _teardown_all_resources(self, sig_guard: Optional[SignalWakeupGuard]) -> None:
        try:
            if sig_guard is not None:
                sig_guard.close()
            with self._cond:
                force = self._force_shutdown
            self._execute_full_shutdown(force=force)
            self._listener.close_all()
            with self._cond:
                self._stopping = True
                self._stopped = True
                self._cond.notify_all()
        finally:
            self._release_singleton_registration()

    def request_shutdown(self, *, force: bool = False, core_handoff: bool = False) -> None:
        with self._handoff_lease_lock:
            with self._cond:
                if not core_handoff:
                    self._explicit_stop_latched = True
                    self._pending_core_handoff = False
                elif not self._explicit_stop_latched and self._self_restart_argv is not None:
                    self._pending_core_handoff = True
                eff_handoff = self._pending_core_handoff
            if eff_handoff:
                ep = self._listener.endpoint
                _write_handoff_lease(self._cache_dir, ep.boot_id if ep is not None else "", ttl_sec=10.0)
            else:
                silent_unlink_contained(self._cache_dir, *_HANDOFF_LEASE_SUBPATH)
            with self._cond:
                if force:
                    self._force_shutdown = True
                self._stopping = True
                self._cancel_installer_lock_waits_locked()
                self._cond.notify_all()
        if force:
            self._dispatcher.cancel_all_active_turns("Forced daemon shutdown")

    def _wait_daemon_pre_quiesce_locked(self, drain_deadline: float) -> bool:
        if self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED):
            return False
        self._cancel_installer_lock_waits_locked()
        while (
            (
                (self._base_phase_locked() == ContainerState.WARMING and not self._deferred_boot_warmup)
                or self._lifecycle_ops_in_flight > 0
            )
            and time.monotonic() < drain_deadline
        ):
            self._cancel_installer_lock_waits_locked()
            self._cond.wait(timeout=min(0.02, max(0.001, drain_deadline - time.monotonic())))
        return not (
            (self._base_phase_locked() == ContainerState.WARMING and not self._deferred_boot_warmup)
            or self._lifecycle_ops_in_flight > 0
            or self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED)
        )

    def _release_quiesce_wait_counters(self) -> None:
        retry_hooks = False
        with self._cond:
            self._quiesce_waiters = max(0, self._quiesce_waiters - 1)
            retry_hooks = self._base_phase_locked() == ContainerState.READY and self._pending_startup_catchup
            self._cond.notify_all()
        if retry_hooks:
            self._consume_and_fire_post_boot_hooks()

    def quiesce(
        self,
        affected_modules: frozenset[ModuleId],
        lease_sec: float = 10.0,
        *,
        drain_timeout_sec: float = 3.0,
    ) -> bool:
        affected_modules = require_typed_frozenset(affected_modules, ModuleId, "affected_modules")
        v_lease = validate_non_negative_sec(lease_sec, label="lease_sec")
        v_drain = validate_non_negative_sec(drain_timeout_sec, label="drain_timeout_sec")
        if v_lease is None or v_lease <= 0.0 or v_drain is None or v_drain <= 0.0:
            raise ValueError("quiesce lease_sec and drain_timeout_sec must be finite and > 0.")
        clamped_lease = min(3600.0, max(0.2, v_lease))
        clamped_drain = min(300.0, max(0.05, v_drain))
        drain_deadline = time.monotonic() + clamped_drain
        is_global = (not bool(affected_modules)) or (CORE_MODULE_ID in affected_modules)
        with self._cond:
            self._quiesce_waiters += 1
        try:
            with self._cond:
                pre_ok = self._wait_daemon_pre_quiesce_locked(drain_deadline)
            if not pre_ok:
                return False
            with self._dispatcher.reload_gate.try_lifecycle_scope(max(0.0, drain_deadline - time.monotonic())) as got_scope:
                if not got_scope:
                    return False
                with self._cond:
                    unquiesceable = self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED)
                if unquiesceable:
                    return False
                self._record_scoped_bg_diags(self._dispatcher.drain_teardown_diagnostics(), frozenset())
                expanded = (
                    frozenset()
                    if is_global
                    else (self._dispatcher.expand_quiesce_targets(affected_modules) - frozenset({CORE_MODULE_ID}))
                )
                entered = self._dispatcher.try_quiesce_modules(
                    expanded,
                    drain_deadline=drain_deadline,
                    leased=True,
                )
                self._record_scoped_bg_diags(self._dispatcher.drain_teardown_diagnostics(), expanded)
                if not entered:
                    return False
                if CORE_MODULE_ID in affected_modules:
                    self._dirty.add_reload(frozenset({CORE_MODULE_ID}))
                self._dispatcher.reload_gate.record_quiesce_lease(is_global, expanded, clamped_lease)
                with self._cond:
                    self._cond.notify_all()
                return True
        finally:
            self._release_quiesce_wait_counters()

    def _has_deferred_core_mutation(self) -> bool:
        with self._dispatcher.reload_gate.lifecycle_scope():
            if self._dirty.has_explicit_core_reload():
                return True
            cur_core_snap = _scan_core_module_tree(self._workspace_root, self._boot_core_snapshot)
            cur_digests = {k: v.sha256 for k, v in cur_core_snap.items()}
            boot_digests = {k: v.sha256 for k, v in self._boot_core_snapshot.items()}
            if cur_digests != boot_digests:
                return True
            self._boot_core_snapshot = cur_core_snap
            return False

    def _probe_core_mutation_under_installer_lock(self) -> Optional[bool]:
        if self._dirty.has_explicit_core_reload():
            return True
        inst_lk = self._acquire_cancellable_shared_installer_lock(timeout_sec=2.0)
        if inst_lk is None:
            return None
        try:
            return self._has_deferred_core_mutation()
        finally:
            inst_lk.release()

    def _resync_watchers_for_quiesce_resume(
        self,
        touched_all: frozenset[ModuleId],
        was_all: bool,
    ) -> None:
        if was_all:
            self._resync_all_modules_watcher()
            self._dirty.clear_all_modules()
            return
        if touched_all:
            self._resync_selected_modules_watcher(touched_all)
            self._dirty.prune_modules(touched_all, self._contained_modules_path())

    def _run_due_quiesce_resume(self, due: DueQuiesceResume) -> None:
        inst_lock = try_acquire_contained_lock(self._cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME, shared=True)
        if inst_lock is None:
            self._dispatcher.reload_gate.postpone_due_lease(due.epoch, due.modules, 0.05)
            with self._cond:
                self._cond.wait(timeout=0.05)
            return
        try:
            self._execute_synchronous_quiesce_resume(due.epoch, due.modules, due.preserve_modules)
        finally:
            inst_lock.release()

    def resume_from_quiesce(
        self,
        *,
        expected_epoch: Optional[int] = None,
        modules: Optional[frozenset[ModuleId]] = None,
    ) -> bool:
        if expected_epoch is not None:
            require_pure_int(expected_epoch, "expected_epoch", min_val=0)
        if modules is not None:
            modules = require_typed_frozenset(modules, ModuleId, "modules")
        eff_mods = (
            None
            if (modules is None or len(modules) == 0 or CORE_MODULE_ID in modules)
            else modules
        )
        inst_lock = try_acquire_contained_lock(self._cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME, shared=True)
        if inst_lock is not None:
            try:
                return self._execute_synchronous_quiesce_resume(expected_epoch, eff_mods, frozenset())
            finally:
                inst_lock.release()
        with self._cond:
            can_defer = self._base_phase_locked() in (ContainerState.READY, ContainerState.WARMING) and (
                self._deferred_boot_warmup or self._dispatcher.reload_gate.has_any_quiesced()
            )
        if can_defer:
            self._dispatcher.reload_gate.schedule_deferred_resume(expected_epoch, eff_mods)
        return False

    def _execute_synchronous_quiesce_resume(
        self,
        expected_epoch: Optional[int],
        eff_mods: Optional[frozenset[ModuleId]],
        preserve_modules: frozenset[ModuleId],
    ) -> bool:
        with self._dispatcher.reload_gate.lifecycle_scope():
            with self._cond:
                def_boot = self._deferred_boot_warmup
                active_q = self._dispatcher.reload_gate.has_any_quiesced()
                if self._base_phase_locked() not in (ContainerState.READY, ContainerState.WARMING) or (
                    not def_boot and not active_q
                ):
                    return False
            self._record_scoped_bg_diags(self._dispatcher.drain_teardown_diagnostics(), frozenset())
            q_res = self._dispatcher.execute_daemon_quiesce_resume(
                expected_epoch=expected_epoch,
                modules=eff_mods,
                preserve_modules=preserve_modules,
                deferred_boot=def_boot,
                check_core_mutated=self._has_deferred_core_mutation,
                on_before_warmup=self._resync_watchers_for_quiesce_resume,
            )
            scope_mods = self._dispatcher.expand_quiesce_targets(eff_mods) if eff_mods else frozenset()
            self._record_scoped_bg_diags(self._dispatcher.drain_teardown_diagnostics(), scope_mods)
            if not q_res.started:
                return False
            if not q_res.need_handoff:
                self._periodic_loop.refresh_schedules()
            with self._cond:
                if def_boot and not q_res.need_handoff:
                    self._deferred_boot_warmup = False
                    if self._base_phase_locked() == ContainerState.WARMING:
                        self._dispatcher.container_lifecycle.transition_boot_phase(ContainerState.READY)
                if self._base_phase_locked() == ContainerState.READY and not q_res.still_quiesced and not q_res.need_handoff:
                    self._idle_monitor.record_external_activity()
                self._cond.notify_all()
            self._periodic_loop.wake()
        if q_res.need_handoff:
            self.request_shutdown(core_handoff=True)
            return True
        self._consume_and_fire_post_boot_hooks()
        return True

    def snapshot_status(self) -> DaemonStatusSnapshot:
        workers = self._dispatcher.tier1_pool.active_worker_snapshots()
        degraded = tuple(str(m) for m in self._dispatcher.container_lifecycle.degraded_modules.keys())
        ep = self._listener.endpoint
        with self._cond:
            now = time.monotonic()
            st = self._effective_state_locked()
            fg = self._active_fg_calls
            handled = self._tasks_handled
            bg_errs = len(self._bg_error_diags)
            idle_rem = self._idle_monitor.remaining_sec()
        return DaemonStatusSnapshot(
            state=st,
            pid=os.getpid(),
            boot_id=ep.boot_id if ep else "",
            port=ep.port if ep else 0,
            uptime_sec=round(max(0.0, now - self._started_at), 3),
            idle_ttl_remaining_sec=None if st in (ContainerState.DRAINING, ContainerState.STOPPED) else idle_rem,
            active_foreground_calls=fg,
            tasks_handled=handled,
            active_tier1_workers=() if st == ContainerState.STOPPED else workers,
            degraded_modules=degraded,
            background_error_count=bg_errs,
        )

    def on_call(
        self,
        stream_id: int,
        payload: JsonObject,
        ack_accepted: Callable[[], bool],
        emit_progress: Callable[[JsonObject], None],
        peer_cancel_token: CancellationToken,
    ) -> tuple[bool, JsonObject]:
        _ = stream_id
        raw_ws = payload.get("workspace_root")
        if type(raw_ws) is str and raw_ws:
            try:
                req_ws = HostPath(raw_ws)
            except ValueError:
                req_ws = None
            if req_ws is not None and req_ws != self._workspace_root:
                with self._cond:
                    if self._base_phase_locked() != ContainerState.READY:
                        return (False, {"ok": False})
                if not ack_accepted():
                    return (False, {"ok": False})
                raw_tid = payload.get("task_id")
                src_t = raw_tid if (type(raw_tid) is str and bool(raw_tid)) else None
                rej = DaemonRpcInvokeReply(
                    ok=False,
                    error=ErrorDetail(
                        ErrorCode.SECURITY_GATED,
                        f"Cross-workspace top-level RPC rejected: expected {self._workspace_root}, got {req_ws}",
                        source_task=src_t,
                    ),
                )
                return (True, DataclassCodec.encode_envelope(rej))
        is_bg_rpc = payload.get("priority") == ExecutionPriority.BACKGROUND.value
        target_mod = _extract_payload_module_id(payload)
        prop = _extract_payload_propagation(payload)
        rpc_turn_id = uuid.uuid4().hex
        tm_raw = payload.get("timeout_ms")
        has_tm = isinstance(tm_raw, int) and not isinstance(tm_raw, bool)
        if has_tm and tm_raw < 0:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"timeout_ms must be >= 0, got {tm_raw}")
        if has_tm and tm_raw == 0:
            raise YscbError(ErrorCode.TASK_TIMEOUT, "Timed out after 0ms waiting on daemon gate.")
        guard = DeadlineGuard.from_timeout_ms(tm_raw if has_tm else None, peer_cancel_token)
        admitted = False
        unreg = peer_cancel_token.register_callback(lambda _p, _r: self._wake_cond())
        try:
            with self._cond:
                while True:
                    self._wait_until_gate_open_locked(target_mod, peer_cancel_token, guard, prop)
                    if self._base_phase_locked() != ContainerState.READY:
                        break
                    if target_mod is not None and not self._dispatcher.reload_gate.enter_rpc_call(
                        target_mod, rpc_turn_id, prop
                    ):
                        continue
                    if is_bg_rpc:
                        self._active_bg_turns += 1
                    else:
                        self._active_fg_calls += 1
                        self._idle_monitor.record_external_activity()
                    admitted = True
                    break
        finally:
            unreg()
        if not admitted:
            return (False, {"ok": False})

        mark_done_activity = False
        try:
            eff_payload = payload
            if guard.deadline is not None:
                rem_ms = require_non_none(
                    guard.remaining_ms(expired_message=f"Timed out after {tm_raw}ms waiting on daemon gate.")
                )
                eff_payload = {**payload, "timeout_ms": rem_ms}
            if not ack_accepted():
                return (False, {"ok": False})
            mark_done_activity = not is_bg_rpc
            with self._cond:
                self._tasks_handled += 1
            reply = self._dispatcher.invoke_daemon_rpc(
                eff_payload, peer_cancel_token, emit_progress, pre_turn_id=rpc_turn_id
            )
            return (True, DataclassCodec.encode_envelope(reply))
        finally:
            if target_mod is not None:
                self._dispatcher.reload_gate.exit_rpc_call(target_mod, rpc_turn_id)
            self._release_active_call_slot(is_bg_rpc, mark_activity=mark_done_activity)

    def _release_active_call_slot(self, is_bg_rpc: bool, *, mark_activity: bool) -> None:
        with self._cond:
            if is_bg_rpc:
                self._active_bg_turns = max(0, self._active_bg_turns - 1)
            else:
                self._active_fg_calls = max(0, self._active_fg_calls - 1)
                if mark_activity:
                    self._idle_monitor.record_external_activity()
            self._cond.notify_all()

    def _is_call_gated_locked(
        self,
        target_mod: Optional[ModuleId],
        prop: Optional[CallPropagationContext],
    ) -> bool:
        if self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED):
            return False
        if self._base_phase_locked() == ContainerState.WARMING or self._deferred_boot_warmup:
            return True
        return self._dispatcher.reload_gate.is_rpc_call_gated(target_mod, prop)

    def _wait_until_gate_open_locked(
        self,
        target_mod: Optional[ModuleId],
        peer_cancel_token: CancellationToken,
        guard: DeadlineGuard,
        prop: Optional[CallPropagationContext],
    ) -> None:
        while self._is_call_gated_locked(target_mod, prop):
            if peer_cancel_token.is_cancelled:
                raise TaskCancelledException(
                    peer_cancel_token.reason or "Cancelled while waiting on daemon gate.",
                    preempted=peer_cancel_token.is_preempted,
                )
            if guard.deadline is not None:
                rem = guard.deadline - time.monotonic()
                if rem <= 0:
                    raise YscbError(ErrorCode.TASK_TIMEOUT, "Timed out waiting on daemon gate.")
                self._cond.wait(timeout=rem)
            else:
                self._cond.wait()

    def on_control(self, kind: FrameKind, payload: JsonObject) -> JsonObject:
        try:
            if not isinstance(kind, FrameKind):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported control kind: {kind!r}")
            if not isinstance(payload, Mapping):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Control payload must be a Mapping.")
            if kind == FrameKind.CONTROL_REQUEST:
                return self._dispatcher.coordinator.handle_remote_flight_control(payload)
            if kind == FrameKind.CONTROL_STATUS:
                if payload:
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "CONTROL_STATUS does not accept fields.")
                return {"ok": True, "status": DataclassCodec.encode_object(self.snapshot_status())}
            if kind == FrameKind.CONTROL_QUIESCE:
                return self._handle_control_quiesce(DataclassCodec.decode(DaemonQuiesceControl, payload))
            if kind == FrameKind.CONTROL_RESUME:
                return self._handle_control_resume(DataclassCodec.decode(DaemonResumeControl, payload))
            if kind == FrameKind.CONTROL_RELOAD:
                return self._handle_control_reload(DataclassCodec.decode(DaemonReloadControl, payload))
            if kind == FrameKind.CONTROL_STOP:
                return self._handle_control_stop(DataclassCodec.decode(DaemonStopControl, payload))
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported control kind: {kind.value}")
        except YscbError as exc:
            return {"ok": False, "error": exc.detail.code.value, "message": exc.detail.message}

    def _handle_control_resume(self, ctrl: DaemonResumeControl) -> JsonObject:
        mods = frozenset(ctrl.modules)
        eff_scope = frozenset() if (not mods or CORE_MODULE_ID in mods) else mods
        resumed_sync = self.resume_from_quiesce(
            expected_epoch=ctrl.expected_epoch, modules=mods if mods else None
        )
        td = self._pop_matching_bg_diags(eff_scope) if resumed_sync else ()
        with self._cond:
            cur_st = self._effective_state_locked().value
            handoff = self._pending_core_handoff
        return {
            "ok": True,
            "state": cur_st,
            "handoff": handoff,
            "teardown_diagnostics": [DataclassCodec.encode_object(d) for d in td],
        }

    def _handle_control_stop(self, ctrl: DaemonStopControl) -> JsonObject:
        self.request_shutdown(force=ctrl.force, core_handoff=ctrl.core_handoff)
        run_inline = False
        with self._cond:
            deadline = time.monotonic() + 12.0
            while not self._dispatcher_stopped and self._supervisor_active and time.monotonic() < deadline:
                self._cond.wait(timeout=0.05)
            run_inline = (not self._supervisor_active) and (not self._dispatcher_stopped)
        if run_inline:
            self._execute_full_shutdown(force=ctrl.force)
        with self._cond:
            td = self._shutdown_diagnostics
        return {
            "ok": True,
            "teardown_diagnostics": [DataclassCodec.encode_object(d) for d in td],
        }

    def _handle_control_quiesce(self, ctrl: DaemonQuiesceControl) -> JsonObject:
        mods = frozenset(ctrl.modules)
        entered = self.quiesce(mods, lease_sec=ctrl.lease_sec, drain_timeout_sec=ctrl.drain_timeout_sec)
        with self._cond:
            cur_st = self._effective_state_locked().value
        if not entered:
            return {"ok": False, "state": cur_st, "error": "daemon_busy"}
        eff_scope = frozenset() if (not mods or CORE_MODULE_ID in mods) else mods
        td = self._pop_matching_bg_diags(eff_scope)
        return {
            "ok": True,
            "state": cur_st,
            "epoch": self.quiesce_epoch,
            "teardown_diagnostics": [DataclassCodec.encode_object(d) for d in td],
        }

    def _check_empty_reload_core_handoff(self, mods: frozenset[ModuleId]) -> Optional[JsonObject]:
        core_probe = self._probe_core_mutation_under_installer_lock()
        if core_probe is None:
            self._dirty.add_reload(mods)
            return {"ok": True, "reloaded": False, "deferred": True}
        if not core_probe:
            return None
        self.request_shutdown(core_handoff=True)
        with self._cond:
            return {"ok": True, "handoff": self._pending_core_handoff}

    def _is_reload_target_gated_locked(
        self,
        mods: frozenset[ModuleId],
        expanded_mods: frozenset[ModuleId],
    ) -> bool:
        gate = self._dispatcher.reload_gate
        if self._base_phase_locked() == ContainerState.WARMING or self._deferred_boot_warmup or gate.is_globally_gated():
            return True
        if not mods or CORE_MODULE_ID in mods:
            return gate.has_any_quiesced()
        return any(gate.is_call_gated_for_quiesce(m) for m in expanded_mods)

    def _handle_control_reload(self, ctrl: DaemonReloadControl) -> JsonObject:
        mods = frozenset(ctrl.modules)
        expanded_mods = (
            (self._dispatcher.expand_quiesce_targets(mods) - frozenset({CORE_MODULE_ID}))
            if (mods and CORE_MODULE_ID not in mods)
            else frozenset()
        )
        with self._cond:
            if self._base_phase_locked() in (ContainerState.READY, ContainerState.WARMING) and self._is_reload_target_gated_locked(
                mods, expanded_mods
            ):
                self._dirty.add_reload(mods)
                self._cond.notify_all()
                return {"ok": True, "reloaded": False, "deferred": True}
            if self._base_phase_locked() != ContainerState.READY:
                return {"ok": False, "state": self._effective_state_locked().value, "error": "daemon_stopping"}
            if CORE_MODULE_ID in mods:
                immediate_handoff = True
            else:
                self._active_bg_turns += 1
                self._lifecycle_ops_in_flight += 1
                immediate_handoff = False
        if immediate_handoff:
            self.request_shutdown(core_handoff=True)
            with self._cond:
                return {"ok": True, "handoff": self._pending_core_handoff}
        drained_cfg: frozenset[HostPath] = frozenset()
        try:
            if not mods:
                probe_reply = self._check_empty_reload_core_handoff(mods)
                if probe_reply is not None:
                    return probe_reply
            res, drained_cfg = self._apply_locked_module_reload(mods, include_teardown_diags=True)
            return res
        finally:
            self._finish_lifecycle_reload_op(drained_cfg)

    def _resync_watchers_before_reload(self, mods: frozenset[ModuleId]) -> frozenset[HostPath]:
        flushed_cfg = (
            self._config_watcher.resync_paths(self._watch_cfg.config_watch_roots)
            if self._config_watcher is not None
            else frozenset()
        )
        drained_cfg = self._dirty.drain_config_paths() | flushed_cfg
        if not mods:
            self._resync_all_modules_watcher()
            self._dirty.clear_all_modules()
            return drained_cfg
        expanded = self._dispatcher.expand_quiesce_targets(mods)
        self._resync_selected_modules_watcher(expanded)
        self._dirty.prune_modules(expanded, self._contained_modules_path())
        return drained_cfg



    def _record_scoped_bg_diags(self, diags: Sequence[ErrorDetail], scope_mods: frozenset[ModuleId] = frozenset()) -> None:
        if not diags:
            return
        entries = tuple((_resolve_diag_owners(d, scope_mods), d) for d in diags)
        with self._cond:
            self._bg_teardown_diags.extend(entries)

    def _pop_matching_bg_diags(self, mods: frozenset[ModuleId]) -> tuple[ErrorDetail, ...]:
        expanded = self._dispatcher.expand_quiesce_targets(mods) if mods else frozenset()
        with self._cond:
            if not self._bg_teardown_diags:
                return ()
            if not mods:
                out_all = tuple(d for _, d in self._bg_teardown_diags)
                self._bg_teardown_diags.clear()
                return out_all
            matched = tuple(d for owners, d in self._bg_teardown_diags if not owners or bool(owners & expanded))
            kept = [(owners, d) for owners, d in self._bg_teardown_diags if owners and not bool(owners & expanded)]
            self._bg_teardown_diags.clear()
            self._bg_teardown_diags.extend(kept)
            return matched

    def _apply_locked_module_reload(
        self,
        mods: frozenset[ModuleId],
        *,
        include_teardown_diags: bool = False,
    ) -> tuple[JsonObject, frozenset[HostPath]]:
        drained_holder: list[frozenset[HostPath]] = []
        diags_holder: list[list[JsonObject]] = []

        def _sync_and_reload() -> None:
            with self._dispatcher.reload_gate.lifecycle_scope():
                self._record_scoped_bg_diags(self._dispatcher.drain_teardown_diagnostics(), frozenset())
                drained_holder.append(self._resync_watchers_before_reload(mods))
                self._dispatcher.reload_affected_modules(mods)
                op_td = self._dispatcher.drain_teardown_diagnostics()
                if include_teardown_diags:
                    bg_matched = self._pop_matching_bg_diags(mods)
                    diags_holder.append([DataclassCodec.encode_object(d) for d in (*bg_matched, *op_td)])
                elif op_td:
                    exp_mods = self._dispatcher.expand_quiesce_targets(mods) if mods else frozenset()
                    self._record_scoped_bg_diags(op_td, exp_mods)
                self._periodic_loop.refresh_schedules()

        if not self._run_under_shared_installer_lock(_sync_and_reload, lambda: self._dirty.add_reload(mods)):
            return ({"ok": True, "reloaded": False, "deferred": True}, frozenset())
        reply: dict[str, JsonValue] = {"ok": True, "reloaded": True}
        if include_teardown_diags:
            reply["teardown_diagnostics"] = diags_holder[0] if diags_holder else []
        return (reply, drained_holder[0] if drained_holder else frozenset())

    def _start_watchers_only(self) -> None:
        sup_fn = self._watch_cfg.echo_guard.is_suppressed if self._watch_cfg.echo_guard is not None else None
        if self._watch_cfg.space_watch_roots and self._watch_cfg.on_space_changed_task is not None:
            sw = PollingDirectoryWatcher(
                self._watch_cfg.space_watch_roots,
                lambda paths: self._record_watched_dirty(paths, self._dirty.add_space_paths),
                debounce_sec=self._watch_cfg.watcher_debounce_sec,
                is_suppressed=sup_fn,
            )
            sw.start()
            self._watchers.append(sw)

        if self._watch_cfg.config_watch_roots:
            cw = PollingDirectoryWatcher(
                self._watch_cfg.config_watch_roots,
                lambda paths: self._record_watched_dirty(paths, self._dirty.add_config_paths),
                debounce_sec=self._watch_cfg.watcher_debounce_sec,
                is_suppressed=sup_fn,
            )
            cw.start()
            self._config_watcher = cw
            self._watchers.append(cw)

        mods_hp = try_resolve_contained_subpath(self._workspace_root, MODULES_DIRNAME)
        if mods_hp is not None:
            mw = PollingDirectoryWatcher(
                (mods_hp,),
                lambda paths: self._record_watched_dirty(paths, self._dirty.add_module_paths),
                debounce_sec=self._watch_cfg.watcher_debounce_sec,
                is_suppressed=None,
            )
            mw.start()
            self._modules_watcher = mw
            self._watchers.append(mw)

    def _stop_watchers_and_periodic(self) -> None:
        self._periodic_loop.stop(drain_timeout_sec=0.1 if self._force_shutdown else 3.0)
        for w in list(self._watchers):
            w.stop()
        self._watchers.clear()
        self._modules_watcher = None
        self._config_watcher = None

    def _record_watched_dirty(
        self,
        paths: frozenset[HostPath],
        record_fn: Callable[[frozenset[HostPath]], None],
    ) -> None:
        if not paths:
            return
        record_fn(paths)
        with self._cond:
            if self._base_phase_locked() == ContainerState.READY:
                self._idle_monitor.record_external_activity()
            self._cond.notify_all()

    def _requeue_notify_config_paths(self, paths: frozenset[HostPath]) -> None:
        with self._cond:
            if self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED):
                return
            self._dirty.add_notify_config_paths(paths)
            self._cond.notify_all()

    def _is_local_config_consumer_gated(self) -> bool:
        gate = self._dispatcher.reload_gate
        return gate.is_globally_gated() or any(
            gate.is_call_gated_for_quiesce(m) for m in self._config_consumer_modules()
        )

    def _emit_config_changed_notifications(self, paths: frozenset[HostPath]) -> None:
        if not paths:
            return
        with self._cond:
            if self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED):
                return
        gate = self._dispatcher.reload_gate
        seq_before = gate.transition_seq
        if self._is_local_config_consumer_gated():
            self._requeue_notify_config_paths(paths)
            return
        sorted_paths = sorted(str(p) for p in paths)
        consumers = self._config_consumer_modules()
        rep = self._dispatcher.emit_background_event(CONFIG_CHANGED_EVENT_ID, {"changed_paths": sorted_paths})
        if rep.teardown_diagnostics:
            self._record_scoped_bg_diags(rep.teardown_diagnostics, consumers)
        prim_err = rep.primary_result.error
        if prim_err is not None and prim_err.code != ErrorCode.DAEMON_UNAVAILABLE:
            self._record_bg_error_diag(prim_err)
        if rep.fatal_event_error is not None and rep.fatal_event_error.code != ErrorCode.DAEMON_UNAVAILABLE:
            self._record_bg_error_diag(rep.fatal_event_error)
        for ev_d in rep.event_diagnostics:
            if ev_d.code != ErrorCode.DAEMON_UNAVAILABLE:
                self._record_bg_error_diag(ev_d)
        ev_blocked = (prim_err is not None and prim_err.code == ErrorCode.DAEMON_UNAVAILABLE) or any(
            d.code == ErrorCode.DAEMON_UNAVAILABLE for d in rep.event_diagnostics
        )
        task_blocked = self._watch_cfg.on_config_changed_task is not None and not self._trigger_bg_task(
            self._watch_cfg.on_config_changed_task, {"changed_paths": sorted_paths}
        )
        gate_raced = self._is_local_config_consumer_gated() or gate.transition_seq != seq_before
        if task_blocked or (ev_blocked and gate_raced):
            self._requeue_notify_config_paths(paths)

    def _process_dirty_batch(self, batch: _DirtyBatch) -> frozenset[HostPath]:
        raw_touched = batch.reload_modules | frozenset(self._extract_touched_modules(batch.module_paths))
        explicit_core = CORE_MODULE_ID in batch.reload_modules
        core_probe: Optional[bool] = True if explicit_core else False
        if not explicit_core and (CORE_MODULE_ID in raw_touched or batch.reload_all):
            core_probe = self._probe_core_mutation_under_installer_lock()
        if core_probe is None:
            self._requeue_unapplied_dirty_batch(batch)
            return frozenset()
        if core_probe:
            if batch.space_paths:
                self._dirty.add_space_paths(batch.space_paths)
            self.request_shutdown(core_handoff=True)
            return frozenset()

        touched = raw_touched - frozenset({CORE_MODULE_ID})
        pending_cfg = self._resolve_dirty_config_work(batch, touched)
        if pending_cfg is None:
            return frozenset()
        if batch.space_paths and self._watch_cfg.on_space_changed_task is not None:
            payload: JsonObject = {
                "changed_paths": sorted(str(p) for p in batch.space_paths),
                "startup_catchup": False,
            }
            if not self._spawn_detached_bg_task(self._watch_cfg.on_space_changed_task, payload):
                self._dirty.add_space_paths(batch.space_paths)
        return pending_cfg

    def _resolve_dirty_config_work(
        self,
        batch: _DirtyBatch,
        touched: frozenset[ModuleId],
    ) -> Optional[frozenset[HostPath]]:
        if batch.reload_all or touched:
            target = frozenset() if batch.reload_all else touched
            res, drained_cfg = self._apply_locked_module_reload(target)
            if not res.get("reloaded", False):
                self._dirty.add_config_paths(batch.config_paths)
                self._dirty.add_notify_config_paths(batch.notify_config_paths)
                self._dirty.add_space_paths(batch.space_paths)
                return None
            return batch.config_paths | batch.notify_config_paths | drained_cfg
        if batch.config_paths:
            applied = self._apply_dirty_config_paths(batch.config_paths)
            if not applied:
                self._dirty.add_notify_config_paths(batch.notify_config_paths)
                self._dirty.add_space_paths(batch.space_paths)
                return None
            return applied | batch.notify_config_paths
        return batch.notify_config_paths

    def _requeue_unapplied_dirty_batch(self, batch: _DirtyBatch) -> None:
        if batch.reload_all:
            self._dirty.add_reload(frozenset())
        elif batch.reload_modules:
            self._dirty.add_reload(batch.reload_modules)
        self._dirty.add_module_paths(batch.module_paths)
        self._dirty.add_config_paths(batch.config_paths)
        self._dirty.add_notify_config_paths(batch.notify_config_paths)
        self._dirty.add_space_paths(batch.space_paths)

    def _apply_dirty_config_paths(self, paths: frozenset[HostPath]) -> frozenset[HostPath]:
        drained_extra: list[frozenset[HostPath]] = []

        def _sync_and_reload_cfg() -> None:
            with self._dispatcher.reload_gate.lifecycle_scope():
                flushed_cfg = (
                    self._config_watcher.resync_paths(self._watch_cfg.config_watch_roots)
                    if self._config_watcher is not None
                    else frozenset()
                )
                drained_extra.append(self._dirty.drain_config_paths() | flushed_cfg)
                self._dispatcher.reload_config_and_contributes(emit_event=False)
                self._periodic_loop.refresh_schedules()

        if not self._run_under_shared_installer_lock(
            _sync_and_reload_cfg, lambda: self._dirty.add_config_paths(paths)
        ):
            return frozenset()
        return paths | (drained_extra[0] if drained_extra else frozenset())

    def _contained_modules_path(self) -> Optional[Path]:
        mods_hp = try_resolve_contained_subpath(self._workspace_root, MODULES_DIRNAME)
        return mods_hp.path if mods_hp is not None else None

    def _resync_all_modules_watcher(self) -> None:
        mods_hp = try_resolve_contained_subpath(self._workspace_root, MODULES_DIRNAME)
        if self._modules_watcher is not None and mods_hp is not None:
            self._modules_watcher.resync_paths((mods_hp,))

    def _resync_selected_modules_watcher(self, mods: frozenset[ModuleId]) -> None:
        if self._modules_watcher is None:
            return
        targets = tuple(
            hp
            for m in mods
            if (hp := try_resolve_contained_subpath(self._workspace_root, MODULES_DIRNAME, str(m))) is not None
        )
        if targets:
            self._modules_watcher.resync_paths(targets)

    def _extract_touched_modules(self, paths: frozenset[HostPath]) -> set[ModuleId]:
        mods_root = self._contained_modules_path()
        return {mid for p in paths if (mid := _extract_module_id_under(p, mods_root)) is not None}

    def _run_under_shared_installer_lock(
        self,
        fn: Callable[[], None],
        requeue_fn: Callable[[], None],
    ) -> bool:
        inst_lock = self._acquire_cancellable_shared_installer_lock(10.0, require_ready=True)
        if inst_lock is None:
            requeue_fn()
            return False
        try:
            with self._cond:
                ready_now = self._base_phase_locked() == ContainerState.READY
            if not ready_now:
                requeue_fn()
                return False
            fn()
            return True
        finally:
            inst_lock.release()

    def _try_admit_bg_turn_locked(self, mod_id: ModuleId, bg_tid: str) -> bool:
        if self._base_phase_locked() != ContainerState.READY or self._deferred_boot_warmup:
            return False
        if self._dispatcher.reload_gate.is_call_gated_for_quiesce(mod_id):
            return False
        if not self._dispatcher.reload_gate.enter_rpc_call(mod_id, bg_tid):
            return False
        self._active_bg_turns += 1
        return True

    def _spawn_detached_bg_task(self, task_id: TaskId, payload: JsonObject) -> bool:
        bg_tid = uuid.uuid4().hex
        with self._cond:
            if not self._try_admit_bg_turn_locked(task_id.module_id, bg_tid):
                return False
        try:
            threading.Thread(
                target=self._run_acquired_bg_task,
                args=(task_id, payload, bg_tid),
                name="yscb-space-bg-turn",
                daemon=True,
            ).start()
        except BaseException as exc:
            self._dispatcher.reload_gate.exit_rpc_call(task_id.module_id, bg_tid)
            with self._cond:
                self._active_bg_turns = max(0, self._active_bg_turns - 1)
                self._cond.notify_all()
            if not isinstance(exc, Exception):
                raise
            self._record_bg_error_diag(
                ErrorDetail(
                    ErrorCode.BUSINESS_FAILURE,
                    f"Background task thread spawn failed for '{task_id}': {safe_exception_summary(exc)}",
                    source_task=str(task_id),
                )
            )
            return False
        return True

    def _run_bg_invoke_unlocked(self, task_id: TaskId, raw_input: JsonObject, bg_tid: str) -> None:
        req = InvokeRequest(
            task_id=task_id,
            raw_input=raw_input,
            workspace_root=self._workspace_root,
            caller_cwd=self._workspace_root,
            priority=ExecutionPriority.BACKGROUND,
            propagation=CallPropagationContext(
                turn_id=bg_tid, is_internal_trigger=True, from_hot_container=True
            ),
        )
        out = self._dispatcher.invoke(req)
        with self._cond:
            stopping_now = self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED)
        quiesced_now = self._dispatcher.reload_gate.is_call_gated_for_quiesce(task_id.module_id)
        if not out.ok and out.error is not None and out.error.code not in (
            ErrorCode.TASK_CANCELLED,
            ErrorCode.TASK_PREEMPTED,
        ):
            if not (out.error.code == ErrorCode.DAEMON_UNAVAILABLE and (stopping_now or quiesced_now)):
                self._record_bg_error_diag(out.error)
        for diag in (*out.event_diagnostics, *out.teardown_diagnostics):
            if diag.code in (ErrorCode.TASK_CANCELLED, ErrorCode.TASK_PREEMPTED):
                continue
            if diag.code == ErrorCode.DAEMON_UNAVAILABLE and (stopping_now or quiesced_now):
                continue
            self._record_bg_error_diag(diag)

    def _run_acquired_bg_task(self, task_id: TaskId, raw_input: JsonObject, bg_tid: str) -> None:
        try:
            self._run_bg_invoke_unlocked(task_id, raw_input, bg_tid)
        finally:
            self._dispatcher.reload_gate.exit_rpc_call(task_id.module_id, bg_tid)
            with self._cond:
                self._active_bg_turns = max(0, self._active_bg_turns - 1)
                self._cond.notify_all()

    def _trigger_bg_task(self, task_id: TaskId, raw_input: JsonObject) -> bool:
        bg_tid = uuid.uuid4().hex
        with self._cond:
            if not self._try_admit_bg_turn_locked(task_id.module_id, bg_tid):
                return False
        self._run_acquired_bg_task(task_id, raw_input, bg_tid)
        return True
