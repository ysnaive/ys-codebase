"""WorkspaceDaemon, _DirtyPathsAccumulator, SingleFlightDaemonSpawner, IdleTtlMonitor, and PeriodicTriggerLoop."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
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
    DAEMON_ENDPOINT_FILENAME, DAEMON_HANDOFF_FILENAME, DAEMON_SUBDIR, FrameKind, InboundCallHandler,
    RpcServerListener, build_daemon_endpoint_dict, build_handoff_lease_dict, probe_daemon_endpoint,
    read_active_handoff_boot_id,
)
from core.execution.runtime import (
    CONFIG_CHANGED_EVENT_ID, CORE_MODULE_ID, INSTALLER_LOCK_FILENAME, LOCKS_SUBDIR, MODULES_DIRNAME,
    CallPropagationContext, ConfigViewPort, DaemonRpcInvokeReply, DaemonSpawner, ExecutionPriority,
    InvokeRequest, RuntimeDispatcher, TaskRouteSpec, VfsEchoGuardPort, WorkerProcessSnapshot,
)
from core.filesystem.fs import (
    IGNORED_FS_PREFIXES, FileLock, PollingDirectoryWatcher, atomic_write_json, hash_nofollow_regular_sha256,
    is_atomic_staging_filename, is_symlink_or_reparse, read_json_dict, resolve_contained_subpath,
    silent_unlink_contained, try_acquire_contained_lock, try_resolve_contained_subpath, walk_nonsymlink_dir_tree,
)
from core.foundation.codec import DataclassCodec
from core.foundation.errors import ErrorCode, ErrorDetail, YscbError, safe_exception_summary
from core.foundation.observability import CancellationToken, clamp_positive_sec, validate_non_negative_sec
from core.foundation.primitives import (
    IS_WINDOWS, MAX_SAFE_WAIT_SEC, HostPath, JsonObject, ModuleId, TaskId, require_non_none,
    require_pure_bool, require_pure_int, require_pure_str, require_typed_tuple, safe_real_to_float,
)
from core.foundation.proc import SignalWakeupGuard, is_process_alive, spawn_detached

DaemonRunState = ContainerState
_HANDOFF_LEASE_SUBPATH: tuple[str, str] = (DAEMON_SUBDIR, DAEMON_HANDOFF_FILENAME)
_DAEMON_LOCK_FILENAME: str = "daemon.lock"
_SPAWN_LOCK_FILENAME: str = "spawn.lock"
_SPAWN_LEASE_FILENAME: str = "spawn_lease.json"


@dataclass(frozen=True, slots=True)
class DaemonStatusSnapshot:
    """Immutable point-in-time status snapshot reported by CONTROL_STATUS and snapshot_status()."""

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
        for iv, nm, mx in ((self.pid, "pid", None), (self.port, "port", 65535), (self.active_foreground_calls, "active_foreground_calls", None), (self.tasks_handled, "tasks_handled", None), (self.background_error_count, "background_error_count", None)):
            require_pure_int(iv, f"DaemonStatusSnapshot.{nm}", min_val=0, max_val=mx)
        up_s = validate_non_negative_sec(self.uptime_sec, label="uptime_sec")
        if up_s is None:
            raise ValueError("DaemonStatusSnapshot.uptime_sec required.")
        object.__setattr__(self, "uptime_sec", up_s)
        if self.idle_ttl_remaining_sec is not None:
            object.__setattr__(self, "idle_ttl_remaining_sec", validate_non_negative_sec(self.idle_ttl_remaining_sec, label="idle_ttl_remaining_sec"))
        require_pure_str(self.boot_id, "DaemonStatusSnapshot.boot_id")
        object.__setattr__(self, "active_tier1_workers", require_typed_tuple(self.active_tier1_workers, WorkerProcessSnapshot, "active_tier1_workers"))
        object.__setattr__(self, "degraded_modules", require_typed_tuple(self.degraded_modules, str, "degraded_modules"))


@dataclass(frozen=True, slots=True)
class DaemonQuiesceControl:
    """Control payload requesting global daemon quiesce and active-work drain."""

    lease_sec: float = 10.0
    drain_timeout_sec: float = 3.0

    def __post_init__(self) -> None:
        s_lease, s_drain = validate_non_negative_sec(self.lease_sec, label="lease_sec"), validate_non_negative_sec(self.drain_timeout_sec, label="drain_timeout_sec")
        if s_lease is None or s_lease <= 0.0 or s_drain is None or s_drain <= 0.0:
            raise ValueError("DaemonQuiesceControl lease_sec and drain_timeout_sec must be finite and > 0.")
        object.__setattr__(self, "lease_sec", s_lease)
        object.__setattr__(self, "drain_timeout_sec", s_drain)


@dataclass(frozen=True, slots=True)
class DaemonResumeControl:
    """Control payload releasing global daemon quiesce with optional epoch guard."""

    expected_epoch: Optional[int] = None

    def __post_init__(self) -> None:
        if self.expected_epoch is not None:
            require_pure_int(self.expected_epoch, "DaemonResumeControl.expected_epoch", min_val=0)


@dataclass(frozen=True, slots=True)
class DaemonReloadControl:
    """Control payload requesting disk reload of all or targeted modules."""

    modules: tuple[ModuleId, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "modules", require_typed_tuple(self.modules, ModuleId, "DaemonReloadControl.modules"))


@dataclass(frozen=True, slots=True)
class DaemonStopControl:
    """Control payload requesting daemon shutdown or core-upgrade handoff."""

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
        object.__setattr__(self, "space_watch_roots", require_typed_tuple(self.space_watch_roots, HostPath, "space_watch_roots"))
        object.__setattr__(self, "config_watch_roots", require_typed_tuple(self.config_watch_roots, HostPath, "config_watch_roots"))
        for tv, lb in ((self.on_space_changed_task, "on_space_changed_task"), (self.on_config_changed_task, "on_config_changed_task")):
            if tv is not None and not isinstance(tv, TaskId):
                raise ValueError(f"{lb} must be TaskId or None.")
        safe_deb = validate_non_negative_sec(self.watcher_debounce_sec, label="watcher_debounce_sec")
        if safe_deb is None or safe_deb <= 0.0:
            raise ValueError(f"watcher_debounce_sec must be finite and > 0, got {self.watcher_debounce_sec!r}")
        object.__setattr__(self, "watcher_debounce_sec", safe_deb)


@dataclass(frozen=True, slots=True)
class _CoreFileSig:
    mtime_ns: int = field(compare=False)
    size: int
    ino: int = field(compare=False)
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
        return bool(self.reload_all or self.reload_modules or self.module_paths or self.config_paths or self.notify_config_paths or self.space_paths)


class _DirtyPathsAccumulator:
    """Thread-safe O(1) dirty-path buffer decoupling Watchers from Daemon lifecycle locks."""

    __slots__ = ("_lock", "_reload_all", "_reload_modules", "_module_paths", "_config_paths", "_notify_config_paths", "_space_paths")

    def __init__(self) -> None:
        self._lock, self._reload_all = threading.Lock(), False
        self._reload_modules: set[ModuleId] = set()
        self._module_paths: set[HostPath] = set()
        self._config_paths: set[HostPath] = set()
        self._notify_config_paths: set[HostPath] = set()
        self._space_paths: set[HostPath] = set()

    @property
    def has_pending(self) -> bool:
        with self._lock:
            return bool(self._reload_all or self._reload_modules or self._module_paths or self._config_paths or self._notify_config_paths or self._space_paths)

    def add_reload(self, modules: frozenset[ModuleId]) -> None:
        with self._lock:
            if modules:
                self._reload_modules.update(modules)
            else:
                self._reload_all = True

    def add_paths(self, kind: str, paths: frozenset[HostPath]) -> None:
        if not paths:
            return
        with self._lock:
            {"module": self._module_paths, "config": self._config_paths, "notify_config": self._notify_config_paths, "space": self._space_paths}[kind].update(paths)

    def drain(self, *, modules_only: bool = False) -> _DirtyBatch:
        with self._lock:
            batch = _DirtyBatch(
                reload_all=self._reload_all, reload_modules=frozenset(self._reload_modules), module_paths=frozenset(self._module_paths),
                config_paths=frozenset() if modules_only else frozenset(self._config_paths),
                notify_config_paths=frozenset() if modules_only else frozenset(self._notify_config_paths),
                space_paths=frozenset() if modules_only else frozenset(self._space_paths),
            )
            self._reload_all = False
            self._reload_modules.clear()
            self._module_paths.clear()
            if not modules_only:
                self._config_paths.clear()
                self._notify_config_paths.clear()
                self._space_paths.clear()
            return batch

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
                self._module_paths = {p for p in self._module_paths if _extract_module_id_under(p, mods_root) not in mods}

    def has_explicit_core_reload(self) -> bool:
        with self._lock:
            return CORE_MODULE_ID in self._reload_modules


class SingleFlightDaemonSpawner(DaemonSpawner):
    """Implements DaemonSpawner using non-blocking .cache/daemon/spawn.lock and wall-clock spawn lease."""

    def __init__(
        self, cache_dir: HostPath, daemon_argv_builder: Callable[[HostPath], Sequence[str]],
        *, lease_cooldown_sec: float = 1.5, sandbox_restricted: bool = False,
    ) -> None:
        self._cache_dir, self._argv_builder = cache_dir, daemon_argv_builder
        self._lease_cooldown_sec = require_non_none(validate_non_negative_sec(lease_cooldown_sec, label="lease_cooldown_sec"))
        self._sandbox_restricted = sandbox_restricted

    def can_spawn_in_environment(self) -> bool:
        return not self._sandbox_restricted

    def try_spawn_background(self, workspace_root: HostPath) -> bool:
        if not self.can_spawn_in_environment() or probe_daemon_endpoint(self._cache_dir, workspace_root) is not None:
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
            spawned_pid = spawn_detached(list(self._argv_builder(workspace_root)), cwd=workspace_root)
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
    *,
    ignore_pid: Optional[int] = None,
) -> bool:
    if lease_data is None:
        return False
    ts_raw, pid_raw = lease_data.get("spawned_epoch", 0.0), lease_data.get("pid", 0)
    try:
        last_ts = safe_real_to_float(ts_raw)
    except ValueError:
        return False
    lease_pid = pid_raw if isinstance(pid_raw, int) and not isinstance(pid_raw, bool) else 0
    return (
        math.isfinite(last_ts)
        and lease_pid > 0
        and lease_pid != ignore_pid
        and 0.0 <= (now_epoch - last_ts) < cooldown_sec
        and is_process_alive(lease_pid)
    )


def _normalize_idle_ttl_sec(ttl_sec: Optional[float]) -> Optional[float]:
    if ttl_sec is None:
        return None
    f_val = safe_real_to_float(ttl_sec, label="ttl_sec")
    if math.isnan(f_val):
        raise ValueError(f"IdleTtlMonitor ttl_sec must be a real number or None, got {ttl_sec!r}")
    return None if (f_val <= 0.0 or math.isinf(f_val)) else min(MAX_SAFE_WAIT_SEC, f_val)


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
        self, *, dispatcher: RuntimeDispatcher, config_view: Optional[ConfigViewPort],
        can_run_background: Callable[[], bool], execute_periodic_task: Callable[[TaskId], None],
        can_run_task: Optional[Callable[[TaskId], bool]] = None, on_error: Optional[Callable[[ErrorDetail], None]] = None,
    ) -> None:
        self._dispatcher, self._config_view = dispatcher, config_view
        self._can_run_bg, self._can_run_task, self._exec_periodic, self._on_error = can_run_background, can_run_task, execute_periodic_task, on_error
        self._cond = threading.Condition()
        self._wake_seq, self._stopped, self._starting = 0, True, False
        self._next_due: dict[TaskId, float] = {}
        self._last_base: dict[TaskId, float] = {}
        self._in_flight: set[TaskId] = set()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the background scheduler thread idempotently after initial schedule computation."""
        with self._cond:
            if (self._thread is not None and self._thread.is_alive()) or self._starting:
                return
            self._stopped, self._starting = False, True
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
                self._stopped, self._thread = True, None
                raise
            self._thread = t

    def refresh_schedules(self) -> None:
        """Re-evaluate periodic task config gates and wake the scheduler loop."""
        now, specs = time.monotonic(), self._dispatcher.list_route_specs()
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
                elif spec.task_id not in self._in_flight:
                    base = self._last_base.get(spec.task_id)
                    self._next_due[spec.task_id] = max(now, base + interval) if base is not None else now
            for stale_tid in tuple(self._next_due.keys() | self._last_base.keys()):
                if stale_tid not in seen_ids:
                    self._next_due.pop(stale_tid, None)
                    self._last_base.pop(stale_tid, None)
            self._wake_seq += 1
            self._cond.notify_all()

    def wake(self) -> None:
        """Wake the scheduler thread to re-check runnable gates without recomputing intervals."""
        with self._cond:
            self._wake_seq += 1
            self._cond.notify_all()

    def stop(self, *, drain_timeout_sec: float = 3.0) -> None:
        """Stop scheduling new ticks and drain active periodic executions up to drain_timeout_sec."""
        safe_drain = max(0.05, require_non_none(validate_non_negative_sec(drain_timeout_sec, label="drain_timeout_sec")))
        with self._cond:
            self._stopped = True
            self._cond.notify_all()
            t, self._thread = self._thread, None
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2.0)
        deadline = time.monotonic() + safe_drain
        with self._cond:
            while self._in_flight and time.monotonic() < deadline:
                self._cond.wait(timeout=0.02)

    def _emit_error(self, message: str, *, source_task: Optional[str] = None) -> None:
        if self._on_error is not None:
            self._on_error(ErrorDetail(ErrorCode.BUSINESS_FAILURE, message, source_task=source_task))

    def _resolve_periodic_config(self, spec: TaskRouteSpec) -> tuple[bool, float]:
        p = require_non_none(spec.periodic)
        mod_id = spec.task_id.module_id
        enabled = True if p.enabled_config_key is None else (self._config_view is not None and self._config_view.get_module_value(mod_id, p.enabled_config_key, False) is True)
        interval = clamp_positive_sec(p.default_interval_sec, min_sec=0.05, max_sec=604800.0, default_sec=60.0)
        if p.interval_config_key is not None and self._config_view is not None:
            raw_iv = self._config_view.get_module_value(mod_id, p.interval_config_key, interval)
            if not isinstance(raw_iv, bool) and isinstance(raw_iv, (int, float)) and math.isfinite(safe_real_to_float(raw_iv)) and safe_real_to_float(raw_iv) > 0.0:
                interval = clamp_positive_sec(raw_iv, min_sec=0.05, max_sec=604800.0, default_sec=interval)
        return (enabled, interval)

    def _loop(self) -> None:
        while True:
            with self._cond:
                if self._stopped:
                    return
            try:
                due_list = self._wait_and_pop_due_specs()
            except (Exception, SystemExit, GeneratorExit) as exc:
                self._emit_error(f"Periodic scheduler poll failed: {safe_exception_summary(exc)}")
                time.sleep(0.05)
                continue
            for spec in due_list:
                try:
                    threading.Thread(target=self._run_periodic_once, args=(spec,), name=f"yscb-periodic-{spec.task_id}", daemon=True).start()
                except BaseException as exc:
                    with self._cond:
                        self._in_flight.discard(spec.task_id)
                        self._cond.notify_all()
                    if not isinstance(exc, Exception):
                        raise
                    self._emit_error(f"Periodic thread spawn failed for '{spec.task_id}': {safe_exception_summary(exc)}", source_task=str(spec.task_id))

    def _wait_and_pop_due_specs(self) -> list[TaskRouteSpec]:
        with self._cond:
            snap_seq = self._wake_seq
        runnable = (
            {s.task_id: s for s in self._dispatcher.list_route_specs() if s.periodic is not None and (self._can_run_task is None or self._can_run_task(s.task_id)) and self._resolve_periodic_config(s)[0]}
            if self._can_run_bg() else {}
        )
        with self._cond:
            if self._stopped or self._wake_seq != snap_seq:
                return []
            eligible_dues = [due_at for tid, due_at in self._next_due.items() if tid in runnable and tid not in self._in_flight]
            if not eligible_dues:
                self._cond.wait(timeout=3600.0 if self._next_due else None)
                return []
            now = time.monotonic()
            wait_sec = min(eligible_dues) - now
            if wait_sec > 0:
                self._cond.wait(timeout=min(wait_sec, 3600.0))
                return []
            due_specs: list[TaskRouteSpec] = []
            for tid, due_at in list(self._next_due.items()):
                if now >= due_at and tid not in self._in_flight and tid in runnable:
                    self._next_due.pop(tid, None)
                    self._in_flight.add(tid)
                    due_specs.append(runnable[tid])
            return due_specs

    def _run_periodic_once(self, spec: TaskRouteSpec) -> None:
        try:
            self._exec_periodic(spec.task_id)
        except (Exception, SystemExit, GeneratorExit) as exc:
            self._emit_error(f"Periodic task '{spec.task_id}' raised: {safe_exception_summary(exc)}", source_task=str(spec.task_id))
        finally:
            while True:
                with self._cond:
                    snap_seq = self._wake_seq
                try:
                    latest = next((s for s in self._dispatcher.list_route_specs() if s.task_id == spec.task_id and s.periodic is not None), None)
                    enabled, interval = (False, 0.0) if latest is None else self._resolve_periodic_config(latest)
                except (Exception, SystemExit, GeneratorExit) as exc:
                    self._emit_error(f"Post-periodic schedule refresh failed for '{spec.task_id}': {safe_exception_summary(exc)}", source_task=str(spec.task_id))
                    p = spec.periodic
                    enabled, interval = (False, 0.0) if p is None else (p.enabled_config_key is None, clamp_positive_sec(p.default_interval_sec, min_sec=0.05, max_sec=604800.0, default_sec=60.0))
                with self._cond:
                    if self._wake_seq != snap_seq:
                        continue
                    self._in_flight.discard(spec.task_id)
                    done_now = time.monotonic()
                    if enabled and not self._stopped:
                        self._last_base[spec.task_id], self._next_due[spec.task_id] = done_now, done_now + interval
                    else:
                        self._next_due.pop(spec.task_id, None)
                        self._last_base.pop(spec.task_id, None)
                    self._wake_seq += 1
                    self._cond.notify_all()
                    return


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


def _write_handoff_lease(cache_dir: HostPath, old_boot_id: str, ttl_sec: float) -> None:
    try:
        lease_file = resolve_contained_subpath(cache_dir, *_HANDOFF_LEASE_SUBPATH)
        clamped_ttl = clamp_positive_sec(ttl_sec, min_sec=0.5, max_sec=30.0, default_sec=10.0)
        atomic_write_json(lease_file, build_handoff_lease_dict(old_boot_id, time.time() + clamped_ttl))
    except (OSError, ValueError, YscbError):
        return


def _scan_core_module_tree(workspace_root: HostPath, cached: Optional[Mapping[str, _CoreFileSig]] = None) -> dict[str, _CoreFileSig]:
    core_hp = try_resolve_contained_subpath(workspace_root, MODULES_DIRNAME, str(CORE_MODULE_ID))
    if core_hp is None or not os.path.isdir(str(core_hp)):
        return {}
    snap: dict[str, _CoreFileSig] = {}
    for cur_dir, entries in walk_nonsymlink_dir_tree(str(core_hp)):
        for ent in sorted(entries, key=lambda e: e.name):
            if ent.name.startswith(IGNORED_FS_PREFIXES) or is_atomic_staging_filename(ent.name) or ent.name.endswith(".pyc"):
                continue
            try:
                if ent.is_symlink() or is_symlink_or_reparse(ent.path) or ent.is_dir(follow_symlinks=False):
                    continue
                fpath = os.path.join(cur_dir, ent.name)
                st = os.stat(fpath, follow_symlinks=False)
            except OSError:
                continue
            prev = cached.get(fpath) if cached is not None else None
            if prev is not None and (prev.mtime_ns, prev.size, prev.ino) == (st.st_mtime_ns, st.st_size, st.st_ino):
                snap[fpath] = prev
            else:
                is_reg = not is_symlink_or_reparse(fpath) and stat.S_ISREG(st.st_mode)
                snap[fpath] = _CoreFileSig(st.st_mtime_ns, st.st_size, st.st_ino, hash_nofollow_regular_sha256(fpath, expected_stat=st) if is_reg else "")
    return snap


class WorkspaceDaemon(InboundCallHandler):
    """Per-workspace daemon shell delegating dispatch and global quiesce gates to RuntimeDispatcher."""

    def __init__(
        self, *, workspace_root: HostPath, cache_dir: HostPath, dispatcher: RuntimeDispatcher,
        config_view: Optional[ConfigViewPort] = None, watch_config: DaemonWatcherConfig = DaemonWatcherConfig(),
        self_restart_argv: Optional[Sequence[str]] = None,
    ) -> None:
        self._workspace_root, self._cache_dir, self._dispatcher, self._config_view, self._watch_cfg = workspace_root, cache_dir, dispatcher, config_view, watch_config
        self._self_restart_argv = tuple(self_restart_argv) if self_restart_argv else None
        self._cond, self._handoff_lease_lock = threading.Condition(), threading.Lock()
        dispatcher.container_lifecycle.transition_boot_phase(ContainerState.BOOTING)
        self._active_fg_calls = self._active_bg_turns = self._lifecycle_ops_in_flight = self._tasks_handled = self._quiesce_waiters = 0
        self._stopping = self._stopped = self._explicit_stop_latched = self._pending_core_handoff = False
        self._force_shutdown = self._supervisor_active = self._shutdown_started = self._dispatcher_stopped = False
        self._boot_warming_active = self._deferred_boot_warmup = self._pending_startup_catchup = False
        self._shutdown_diagnostics: tuple[ErrorDetail, ...] = ()
        self._bg_teardown_diags: deque[ErrorDetail] = deque(maxlen=256)
        self._bg_error_diags: deque[ErrorDetail] = deque(maxlen=256)
        self._started_at, self._dirty = time.monotonic(), _DirtyPathsAccumulator()
        self._inst_wait_cancels: set[CancellationToken] = set()
        self._pending_ready_callback: Optional[Callable[[], None]] = None
        self._daemon_lock = FileLock(resolve_contained_subpath(cache_dir, DAEMON_SUBDIR, _DAEMON_LOCK_FILENAME), allow_transitions=False)
        _ = resolve_contained_subpath(cache_dir, DAEMON_SUBDIR, DAEMON_ENDPOINT_FILENAME)
        _ = resolve_contained_subpath(cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME)
        self._listener, self._idle_monitor = RpcServerListener(workspace_root, self), IdleTtlMonitor(None)
        self._periodic_loop = PeriodicTriggerLoop(
            dispatcher=dispatcher, config_view=config_view, can_run_background=self._can_run_any_background,
            can_run_task=lambda tid: self._can_run_any_background() and not dispatcher.reload_gate.is_call_gated_for_quiesce(tid.module_id),
            execute_periodic_task=lambda tid: self._dispatch_bg_task(tid, {}, detached=False),
            on_error=lambda d: self._record_bg_diags(error=d),
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

    def _record_bg_diags(
        self, teardown_diags: Sequence[ErrorDetail] = (), event_diags: Sequence[ErrorDetail] = (), error: Optional[ErrorDetail] = None,
    ) -> None:
        if not teardown_diags and not event_diags and error is None:
            return
        with self._cond:
            self._bg_teardown_diags.extend(teardown_diags)
            self._bg_error_diags.extend(event_diags)
            if error is not None:
                self._bg_error_diags.append(error)

    def drain_background_errors(self) -> tuple[ErrorDetail, ...]:
        """Drain bounded background watcher and periodic execution errors."""
        with self._cond:
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
        if base in (ContainerState.WARMING, ContainerState.READY) and self._dispatcher.container_lifecycle.state == ContainerState.QUIESCED:
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
        return clamp_positive_sec(raw_val, min_sec=0.05, max_sec=MAX_SAFE_WAIT_SEC, default_sec=default_ttl, label="idle_timeout_sec")

    def run_forever(
        self, *, ttl_override_sec: Optional[float] = None, console_mode: bool = False,
        ready_callback: Optional[Callable[[], None]] = None,
    ) -> int:
        """Acquire daemon.lock, boot RPC/watchers, run supervisor loop, and handle core handoff."""
        eff_ttl = ttl_override_sec if ttl_override_sec is not None else (None if console_mode else self._resolve_default_idle_ttl())
        norm_ttl = _normalize_idle_ttl_sec(eff_ttl)
        got_lock = self._daemon_lock.acquire(blocking=False)
        if not got_lock and read_active_handoff_boot_id(self._cache_dir) is not None:
            try:
                got_lock = self._daemon_lock.acquire(shared=False, blocking=True, timeout_sec=0.25)
            except YscbError:
                got_lock = False
        if not got_lock:
            return 0
        handoff_argv: Optional[tuple[str, ...]] = None
        sig_guard: Optional[SignalWakeupGuard] = None
        try:
            sigs = (int(signal.SIGINT), int(signal.SIGTERM), int(signal.SIGBREAK)) if IS_WINDOWS else (int(signal.SIGINT), int(signal.SIGTERM))
            sig_guard = SignalWakeupGuard(sigs, self.request_shutdown, on_second_signal=lambda: self.request_shutdown(force=True))
            sig_guard.install()
            with self._cond:
                self._supervisor_active = True
            self._boot_and_publish_endpoint(norm_ttl, ready_callback)
            self._run_supervisor_loop()
            with self._cond:
                force_drain = self._force_shutdown
            self._execute_full_shutdown(force=force_drain)
            self._listener.flush_inbound_controls(timeout_sec=2.0)
            with self._cond:
                handoff_argv = self._self_restart_argv if self._pending_core_handoff else None
        finally:
            try:
                if sig_guard is not None:
                    sig_guard.close()
                with self._cond:
                    self._supervisor_active = False
                    force_end = self._force_shutdown
                    self._cond.notify_all()
                self._execute_full_shutdown(force=force_end)
                self._listener.close_all()
                with self._cond:
                    self._stopping = self._stopped = True
                    self._cond.notify_all()
            finally:
                silent_unlink_contained(self._cache_dir, DAEMON_SUBDIR, DAEMON_ENDPOINT_FILENAME)
                self._daemon_lock.release()
        if handoff_argv is not None:
            self._spawn_handoff_successor(handoff_argv)
        return 0

    def _run_supervisor_loop(self) -> None:
        gate = self._dispatcher.reload_gate
        while True:
            due_epoch: Optional[int] = None
            dirty_batch: Optional[_DirtyBatch] = None
            probe_deferred_boot = stop_due_to_ttl = False
            with self._cond:
                base = self._base_phase_locked()
                if base in (ContainerState.DRAINING, ContainerState.STOPPED):
                    return
                due_epoch = gate.due_quiesce_epoch() if gate.has_any_quiesced() else None
                ttl_expired = (
                    base == ContainerState.READY and not gate.has_any_quiesced() and self._active_fg_calls == 0
                    and self._active_bg_turns == 0 and self._idle_monitor.is_expired() and not self._dirty.has_pending
                )
                if due_epoch is None and ttl_expired:
                    self._stopping = stop_due_to_ttl = True
                    self._cond.notify_all()
                elif due_epoch is None and base == ContainerState.WARMING and self._deferred_boot_warmup and not gate.is_globally_quiesced():
                    probe_deferred_boot = True
                elif (
                    due_epoch is None and base == ContainerState.READY and not self._deferred_boot_warmup
                    and self._quiesce_waiters == 0 and self._lifecycle_ops_in_flight == 0
                    and not gate.is_globally_gated() and self._dirty.has_pending
                ):
                    cand = self._dirty.drain()
                    if cand.has_any:
                        dirty_batch = cand
                        self._active_bg_turns += 1
                        self._lifecycle_ops_in_flight += 1
                if due_epoch is None and not stop_due_to_ttl and not probe_deferred_boot and dirty_batch is None:
                    wake_q = gate.next_quiesce_wakeup()
                    rem_ttl = self._idle_monitor.remaining_sec() if base == ContainerState.READY else None
                    ttl_s = min(MAX_SAFE_WAIT_SEC, max(0.01, rem_ttl)) if rem_ttl is not None else None
                    raw_sleep = min(wake_q, ttl_s) if (wake_q is not None and ttl_s is not None) else (wake_q if wake_q is not None else ttl_s)
                    self._cond.wait(timeout=min(MAX_SAFE_WAIT_SEC, max(0.001, raw_sleep)) if raw_sleep is not None else None)
            if stop_due_to_ttl:
                self._listener.stop_accepting()
                return
            if dirty_batch is not None:
                pending_cfg: frozenset[HostPath] = frozenset()
                try:
                    pending_cfg = self._process_dirty_batch(dirty_batch)
                finally:
                    with self._cond:
                        self._lifecycle_ops_in_flight = max(0, self._lifecycle_ops_in_flight - 1)
                        self._active_bg_turns = max(0, self._active_bg_turns - 1)
                        self._cond.notify_all()
                if pending_cfg:
                    self._run_async_config_notifications(pending_cfg)
                continue
            if not probe_deferred_boot and due_epoch is None:
                continue
            probe_lk = try_acquire_contained_lock(self._cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME, shared=True)
            locked_excl = probe_lk is None
            if probe_lk is not None:
                probe_lk.release()
            if not locked_excl:
                self._run_pending_warmup_or_resume(due_epoch)
                continue
            if due_epoch is not None:
                gate.postpone_due_lease(due_epoch, 0.05)
            with self._cond:
                self._cond.wait(timeout=0.05)

    def _run_async_config_notifications(self, cfg_paths: frozenset[HostPath]) -> None:
        if not cfg_paths:
            return
        with self._cond:
            if self._base_phase_locked() != ContainerState.READY or self._deferred_boot_warmup:
                return
            self._active_bg_turns += 1
        try:
            gate = self._dispatcher.reload_gate
            if gate.is_globally_gated():
                return
            path_strs = [str(p) for p in sorted(cfg_paths, key=str)]
            cfg_subs = self._dispatcher.subscribed_modules(CONFIG_CHANGED_EVENT_ID)
            if not any(gate.is_call_gated_for_quiesce(mid) for mid in cfg_subs):
                rep = self._dispatcher.emit_background_event(CONFIG_CHANGED_EVENT_ID, {"changed_paths": path_strs})
                self._record_bg_diags(rep.teardown_diagnostics, rep.event_diagnostics, rep.fatal_event_error or rep.primary_result.error)
            cfg_task = self._watch_cfg.on_config_changed_task
            if cfg_task is not None and not gate.is_call_gated_for_quiesce(cfg_task.module_id):
                self._run_acquired_bg_task(cfg_task, {"changed_paths": path_strs})
        finally:
            with self._cond:
                self._active_bg_turns = max(0, self._active_bg_turns - 1)
                self._cond.notify_all()

    def _spawn_handoff_successor(self, handoff_argv: Sequence[str]) -> None:
        if not handoff_argv:
            return
        lock: Optional[FileLock] = None
        try:
            lock = FileLock(resolve_contained_subpath(self._cache_dir, DAEMON_SUBDIR, _SPAWN_LOCK_FILENAME), allow_transitions=False)
            if not lock.acquire(shared=False, blocking=True, timeout_sec=0.5):
                return
            if probe_daemon_endpoint(self._cache_dir, self._workspace_root) is not None:
                return
            lease_path = resolve_contained_subpath(self._cache_dir, DAEMON_SUBDIR, _SPAWN_LEASE_FILENAME)
            now_epoch = time.time()
            if _is_spawn_lease_active(read_json_dict(lease_path), now_epoch, 1.5, ignore_pid=os.getpid()):
                return
            spawned_pid = spawn_detached(list(handoff_argv), cwd=self._workspace_root)
            atomic_write_json(lease_path, {"spawned_epoch": now_epoch, "pid": spawned_pid})
        except (OSError, ValueError, YscbError) as exc:
            self._record_bg_diags(error=ErrorDetail(ErrorCode.TRANSPORT_LOST, f"Core handoff successor spawn failed: {safe_exception_summary(exc)}"))
        finally:
            if lock is not None:
                lock.release()

    def _boot_and_publish_endpoint(self, norm_ttl: Optional[float], ready_callback: Optional[Callable[[], None]]) -> None:
        self._idle_monitor = IdleTtlMonitor(norm_ttl)
        with self._cond:
            if self._stopping or self._stopped:
                return
            self._pending_ready_callback = ready_callback
            self._pending_startup_catchup = self._watch_cfg.on_space_changed_task is not None
        ep_info = self._listener.start(pid=os.getpid())
        with self._cond:
            stop_early = self._stopping or self._stopped
        if stop_early:
            self._listener.stop_accepting()
            return
        self._dispatcher.container_lifecycle.transition_boot_phase(ContainerState.WARMING)
        self._start_watchers_only()
        ep_path = resolve_contained_subpath(self._cache_dir, DAEMON_SUBDIR, DAEMON_ENDPOINT_FILENAME)
        atomic_write_json(ep_path, build_daemon_endpoint_dict(ep_info), file_mode=0o600)
        silent_unlink_contained(self._cache_dir, *_HANDOFF_LEASE_SUBPATH)
        self._run_initial_boot_warmup()

    def _consume_and_fire_post_boot_hooks(self) -> None:
        with self._cond:
            if self._base_phase_locked() != ContainerState.READY:
                return
            cb = self._pending_ready_callback
            self._pending_ready_callback = None
            catchup_task = self._watch_cfg.on_space_changed_task
            do_catchup = self._pending_startup_catchup and catchup_task is not None
            self._pending_startup_catchup = False
        self._periodic_loop.start()
        self._periodic_loop.refresh_schedules()
        if cb is not None:
            try:
                cb()
            except (Exception, SystemExit, GeneratorExit) as exc:
                self._record_bg_diags(error=ErrorDetail(ErrorCode.BUSINESS_FAILURE, f"ready_callback failed: {safe_exception_summary(exc)}"))
        if do_catchup and catchup_task is not None and not self._dispatcher.reload_gate.is_call_gated_for_quiesce(catchup_task.module_id):
            self._dispatch_bg_task(catchup_task, {"changed_paths": [], "startup_catchup": True}, detached=True)

    def _acquire_cancellable_shared_installer_lock(self, *, timeout_sec: float) -> tuple[Optional[FileLock], bool]:
        tok = CancellationToken()
        with self._cond:
            if self._stopping or self._stopped:
                return (None, True)
            self._inst_wait_cancels.add(tok)
        try:
            lk = try_acquire_contained_lock(self._cache_dir, LOCKS_SUBDIR, INSTALLER_LOCK_FILENAME, shared=True, timeout_sec=timeout_sec, cancel_token=tok)
            return (lk, tok.is_cancelled)
        finally:
            with self._cond:
                self._inst_wait_cancels.discard(tok)

    def _run_locked_boot_warmup(self, *, deferred_boot: bool) -> None:
        with self._cond:
            if self._stopping or self._stopped or (deferred_boot and not self._deferred_boot_warmup):
                return
            self._boot_warming_active = True
        try:
            if self._has_deferred_core_mutation():
                self.request_shutdown(core_handoff=True)
                return
            if deferred_boot:
                if self._dispatcher.reload_gate.is_globally_quiesced():
                    return
                self._prepare_deferred_warmup_state()
                self._dispatcher.reload_config_and_contributes(emit_event=False)
            self._dispatcher.warmup_daemon_container()
            queued = self._dirty.drain(modules_only=True)
            while queued.has_any:
                with self._cond:
                    if self._stopping or self._stopped:
                        return
                mods = self._extract_touched_modules(queued)
                if CORE_MODULE_ID in mods or (queued.reload_all and self._has_deferred_core_mutation()):
                    self.request_shutdown(core_handoff=True)
                    return
                self._apply_locked_module_reload(mods, reload_all=queued.reload_all)
                queued = self._dirty.drain(modules_only=True)
        finally:
            with self._cond:
                self._boot_warming_active = False
                self._cond.notify_all()
        self._consume_and_fire_post_boot_hooks()

    def _run_initial_boot_warmup(self) -> None:
        inst_lk, cancelled = self._acquire_cancellable_shared_installer_lock(timeout_sec=0.05)
        if cancelled:
            return
        if inst_lk is None:
            with self._cond:
                if not (self._stopping or self._stopped):
                    self._deferred_boot_warmup = True
                    self._cond.notify_all()
            return
        try:
            self._run_locked_boot_warmup(deferred_boot=False)
        finally:
            inst_lk.release()

    def _execute_full_shutdown(self, *, force: bool = False) -> None:
        with self._cond:
            if self._shutdown_started:
                while not self._dispatcher_stopped:
                    self._cond.wait(timeout=0.05)
                return
            self._shutdown_started = self._stopping = True
            for tok in tuple(self._inst_wait_cancels):
                tok.cancel(reason="Daemon shutdown requested.")
            self._cond.notify_all()
        self._listener.stop_accepting()
        if force:
            self._dispatcher.cancel_all_active_turns("Daemon forced shutdown")
        for w in tuple(self._watchers):
            w.stop()
        self._periodic_loop.stop(drain_timeout_sec=0.2 if force else 1.0)
        deadline = time.monotonic() + (0.2 if force else 3.0)
        with self._cond:
            while (self._active_fg_calls > 0 or self._active_bg_turns > 0) and time.monotonic() < deadline:
                self._cond.wait(timeout=min(0.02, max(0.001, deadline - time.monotonic())))
        if force:
            self._dispatcher.cancel_all_active_turns("Daemon shutdown deadline")
        disp_diags: tuple[ErrorDetail, ...] = ()
        try:
            disp_diags = self._dispatcher.shutdown(grace_ms=200 if force else 3000)
        finally:
            with self._cond:
                bg_diags = tuple(self._bg_teardown_diags)
                self._bg_teardown_diags.clear()
                self._shutdown_diagnostics = (*bg_diags, *disp_diags)
                self._dispatcher_stopped = True
                self._cond.notify_all()
        silent_unlink_contained(self._cache_dir, DAEMON_SUBDIR, DAEMON_ENDPOINT_FILENAME)

    def request_shutdown(self, *, force: bool = False, core_handoff: bool = False) -> None:
        """Signal the supervisor loop to drain and shut down cleanly or hand off after core upgrade."""
        require_pure_bool(force, "WorkspaceDaemon.request_shutdown.force")
        require_pure_bool(core_handoff, "WorkspaceDaemon.request_shutdown.core_handoff")
        ep = self._listener.endpoint
        write_handoff = unlink_handoff = False
        with self._cond:
            if self._stopped:
                return
            self._stopping = True
            if force:
                self._force_shutdown = True
            if core_handoff and not self._explicit_stop_latched:
                self._pending_core_handoff = write_handoff = True
            elif not core_handoff:
                self._explicit_stop_latched, self._pending_core_handoff, unlink_handoff = True, False, True
            for tok in tuple(self._inst_wait_cancels):
                tok.cancel(reason="Daemon shutdown requested.")
            self._cond.notify_all()
        if write_handoff:
            with self._handoff_lease_lock:
                with self._cond:
                    still_handoff = self._pending_core_handoff and not self._explicit_stop_latched
                if still_handoff:
                    _write_handoff_lease(self._cache_dir, ep.boot_id if ep is not None else "boot", 10.0)
        elif unlink_handoff:
            with self._handoff_lease_lock:
                silent_unlink_contained(self._cache_dir, *_HANDOFF_LEASE_SUBPATH)
        self._listener.stop_accepting()
        if force:
            self._dispatcher.cancel_all_active_turns("Forced shutdown requested")
        self._periodic_loop.wake()

    def quiesce(self, lease_sec: float = 10.0, *, drain_timeout_sec: float = 3.0) -> bool:
        """Enter global QUIESCED state with a monotonic lease and drain active non-core work."""
        s_lease, s_drain = validate_non_negative_sec(lease_sec, label="lease_sec"), validate_non_negative_sec(drain_timeout_sec, label="drain_timeout_sec")
        if s_lease is None or s_lease <= 0.0 or s_drain is None or s_drain <= 0.0:
            raise ValueError("WorkspaceDaemon.quiesce lease_sec and drain_timeout_sec must be finite and > 0.")
        dl = time.monotonic() + s_drain
        with self._cond:
            if self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED):
                return False
            self._quiesce_waiters += 1
            self._cond.notify_all()
            try:
                while self._lifecycle_ops_in_flight > 0:
                    if self._stopping or self._stopped or (rem := dl - time.monotonic()) <= 0.0:
                        return False
                    self._cond.wait(timeout=min(0.02, rem))
                if self._stopping or self._stopped:
                    return False
            finally:
                self._quiesce_waiters = max(0, self._quiesce_waiters - 1)
                self._cond.notify_all()
        with self._dispatcher.reload_gate.lifecycle_scope():
            with self._cond:
                if self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED):
                    return False
            if not self._dispatcher.try_quiesce_global(drain_deadline=dl, leased=True):
                return False
            self._dispatcher.reload_gate.record_quiesce_lease(s_lease)
        self._wake_cond()
        return True

    def _has_deferred_core_mutation(self) -> bool:
        return self._dirty.has_explicit_core_reload() or _scan_core_module_tree(self._workspace_root, cached=self._boot_core_snapshot) != self._boot_core_snapshot

    def _prepare_deferred_warmup_state(self) -> None:
        self._resync_modules_watcher(None)
        if self._config_watcher is not None:
            self._config_watcher.resync_paths(self._watch_cfg.config_watch_roots)
        self._dirty.drain_config_paths()
        with self._cond:
            self._deferred_boot_warmup = False
            self._cond.notify_all()

    def _execute_resume_under_lock(self, expected_epoch: Optional[int]) -> bool:
        res = self._dispatcher.execute_daemon_quiesce_resume(
            expected_epoch=expected_epoch, check_core_mutated=self._has_deferred_core_mutation, on_before_warmup=self._prepare_deferred_warmup_state,
        )
        if res.need_handoff:
            self.request_shutdown(core_handoff=True)
            return True
        if res.started:
            self._consume_and_fire_post_boot_hooks()
        return False

    def _run_pending_warmup_or_resume(self, due_epoch: Optional[int]) -> None:
        inst_lk, cancelled = self._acquire_cancellable_shared_installer_lock(timeout_sec=0.05)
        if cancelled:
            return
        if inst_lk is None:
            if due_epoch is not None:
                self._dispatcher.reload_gate.postpone_due_lease(due_epoch, 0.05)
            return
        try:
            if due_epoch is not None:
                self._execute_resume_under_lock(due_epoch)
            else:
                self._run_locked_boot_warmup(deferred_boot=True)
        finally:
            inst_lk.release()

    def resume_from_quiesce(self, *, expected_epoch: Optional[int] = None) -> bool:
        """Resume daemon from global QUIESCED state, returning True when a core upgrade handoff is triggered."""
        if expected_epoch is not None:
            require_pure_int(expected_epoch, "expected_epoch", min_val=0)
        with self._cond:
            if self._stopping or self._stopped:
                return False
        inst_lk, cancelled = self._acquire_cancellable_shared_installer_lock(timeout_sec=0.05)
        if cancelled:
            return False
        if inst_lk is None:
            self._dispatcher.reload_gate.schedule_deferred_resume(expected_epoch)
            self._wake_cond()
            return False
        try:
            return self._execute_resume_under_lock(expected_epoch)
        finally:
            inst_lk.release()

    def snapshot_status(self) -> DaemonStatusSnapshot:
        """Return an immutable point-in-time status snapshot of the daemon shell."""
        ep = self._listener.endpoint
        t1_workers = self._dispatcher.tier1_pool.active_worker_snapshots()
        deg_mods = tuple(sorted(str(m) for m in self._dispatcher.container_lifecycle.degraded_modules.keys()))
        with self._cond:
            return DaemonStatusSnapshot(
                state=self._effective_state_locked(), pid=ep.pid if ep is not None else os.getpid(),
                boot_id=ep.boot_id if ep is not None else "", port=ep.port if ep is not None else 0,
                uptime_sec=max(0.0, time.monotonic() - self._started_at), idle_ttl_remaining_sec=self._idle_monitor.remaining_sec(),
                active_foreground_calls=self._active_fg_calls, tasks_handled=self._tasks_handled,
                active_tier1_workers=t1_workers, degraded_modules=deg_mods, background_error_count=len(self._bg_error_diags),
            )

    def on_call(
        self, stream_id: int, payload: JsonObject, ack_accepted: Callable[[], bool],
        emit_progress: Callable[[JsonObject], None], peer_cancel_token: CancellationToken,
    ) -> tuple[bool, JsonObject]:
        """Admit, track, and dispatch an inbound RPC call frame through RuntimeDispatcher."""
        _ = stream_id
        task_id_raw, prop_raw = payload.get("task_id"), payload.get("propagation")
        try:
            target_mod = TaskId(task_id_raw).module_id if isinstance(task_id_raw, str) else CORE_MODULE_ID
        except ValueError:
            target_mod = CORE_MODULE_ID
        prop: Optional[CallPropagationContext] = None
        if isinstance(prop_raw, Mapping):
            try:
                prop = DataclassCodec.decode_envelope(CallPropagationContext, prop_raw)
            except (YscbError, KeyError, TypeError, ValueError):
                prop = None
        is_bg = payload.get("priority") == ExecutionPriority.BACKGROUND.value
        call_id = (prop.turn_id if prop is not None and prop.turn_id else "") or uuid.uuid4().hex
        if not self._wait_and_admit_rpc_call(target_mod, call_id, prop, is_bg, peer_cancel_token):
            return (False, {"ok": False})
        try:
            if not ack_accepted():
                return (False, {"ok": False})
            reply: DaemonRpcInvokeReply = self._dispatcher.invoke_daemon_rpc(payload, peer_cancel_token, emit_progress, pre_turn_id=call_id)
            return (True, DataclassCodec.encode_envelope(reply))
        finally:
            self._dispatcher.reload_gate.exit_rpc_call(target_mod, call_id)
            with self._cond:
                if is_bg:
                    self._active_bg_turns = max(0, self._active_bg_turns - 1)
                else:
                    self._active_fg_calls = max(0, self._active_fg_calls - 1)
                self._cond.notify_all()

    def _wait_and_admit_rpc_call(
        self, target_mod: ModuleId, call_id: str, prop: Optional[CallPropagationContext], is_bg: bool, peer_cancel_token: CancellationToken,
    ) -> bool:
        if peer_cancel_token.is_cancelled:
            return False
        reentrant, gate = prop is not None and (prop.is_nested_call or bool(prop.call_stack)), self._dispatcher.reload_gate
        unreg = peer_cancel_token.register_callback(lambda _p, _r: self._wake_cond())
        try:
            with self._cond:
                while True:
                    if self._explicit_stop_latched or self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED) or peer_cancel_token.is_cancelled:
                        return False
                    wait_boot = self._deferred_boot_warmup and target_mod != CORE_MODULE_ID and not reentrant
                    if not wait_boot and not gate.is_rpc_call_gated(target_mod, prop) and gate.enter_rpc_call(target_mod, call_id, prop):
                        if is_bg:
                            self._active_bg_turns += 1
                        else:
                            self._active_fg_calls += 1
                            self._idle_monitor.record_external_activity()
                        self._tasks_handled += 1
                        return True
                    wake = gate.next_quiesce_wakeup()
                    self._cond.wait(timeout=min(0.05, wake) if wake is not None else 0.05)
        finally:
            unreg()

    def on_control(self, kind: FrameKind, payload: JsonObject) -> JsonObject:
        """Handle inbound CONTROL_* frames with strict DataclassCodec validation."""
        if kind == FrameKind.CONTROL_STATUS:
            return {"ok": False, "error": ErrorCode.CODEC_VALIDATION_FAILED.value, "message": "CONTROL_STATUS accepts no payload fields."} if payload else {"ok": True, "status": DataclassCodec.encode_envelope(self.snapshot_status())}
        ctrl_cls = {FrameKind.CONTROL_QUIESCE: DaemonQuiesceControl, FrameKind.CONTROL_RESUME: DaemonResumeControl, FrameKind.CONTROL_RELOAD: DaemonReloadControl, FrameKind.CONTROL_STOP: DaemonStopControl}.get(kind)
        if ctrl_cls is None:
            return {"ok": False, "error": ErrorCode.CODEC_VALIDATION_FAILED.value, "message": f"Unsupported control frame: {kind.value}"}
        try:
            ctrl = DataclassCodec.decode_envelope(ctrl_cls, payload)
        except (YscbError, KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": ErrorCode.CODEC_VALIDATION_FAILED.value, "message": safe_exception_summary(exc)}
        if isinstance(ctrl, DaemonQuiesceControl):
            entered = self.quiesce(ctrl.lease_sec, drain_timeout_sec=ctrl.drain_timeout_sec)
            diags, cur_st = [DataclassCodec.encode_envelope(d) for d in self._dispatcher.drain_teardown_diagnostics()], self.snapshot_status().state.value
            return {"ok": True, "state": cur_st, "epoch": self.quiesce_epoch, "teardown_diagnostics": diags} if entered else {"ok": False, "state": cur_st, "error": "daemon_busy", "teardown_diagnostics": diags}
        if isinstance(ctrl, DaemonResumeControl):
            handoff = self.resume_from_quiesce(expected_epoch=ctrl.expected_epoch)
            diags = [DataclassCodec.encode_envelope(d) for d in self._dispatcher.drain_teardown_diagnostics()]
            return {"ok": True, "state": self.snapshot_status().state.value, "handoff": handoff, "teardown_diagnostics": diags}
        if isinstance(ctrl, DaemonReloadControl):
            return self._handle_control_reload(ctrl)
        self.request_shutdown(force=ctrl.force, core_handoff=ctrl.core_handoff)
        self._execute_full_shutdown(force=ctrl.force)
        with self._cond:
            return {"ok": True, "teardown_diagnostics": [DataclassCodec.encode_envelope(d) for d in self._shutdown_diagnostics]}

    def _handle_control_reload(self, ctrl: DaemonReloadControl) -> JsonObject:
        mods = frozenset(ctrl.modules)
        reload_all = not mods
        immediate_handoff = False
        with self._cond:
            if self._base_phase_locked() in (ContainerState.DRAINING, ContainerState.STOPPED):
                return {"ok": False, "state": self._effective_state_locked().value, "error": "daemon_stopping"}
            if self._boot_warming_active or self._deferred_boot_warmup or self._dispatcher.reload_gate.is_globally_quiesced():
                self._dirty.add_reload(mods)
                self._cond.notify_all()
                return {"ok": True, "reloaded": False, "deferred": True}
            if CORE_MODULE_ID in mods:
                immediate_handoff = True
            else:
                self._lifecycle_ops_in_flight += 1
        if immediate_handoff:
            self.request_shutdown(core_handoff=True)
            with self._cond:
                return {"ok": True, "handoff": self._pending_core_handoff}
        try:
            inst_lk, cancelled = self._acquire_cancellable_shared_installer_lock(timeout_sec=0.25)
            if cancelled:
                return {"ok": False, "state": self.snapshot_status().state.value, "error": "daemon_stopping"}
            if inst_lk is None:
                self._dirty.add_reload(mods)
                self._wake_cond()
                return {"ok": True, "reloaded": False, "deferred": True}
            try:
                if reload_all and self._has_deferred_core_mutation():
                    self.request_shutdown(core_handoff=True)
                    return {"ok": True, "handoff": True}
                self._apply_locked_module_reload(mods, reload_all=reload_all)
                return {"ok": True, "reloaded": True, "teardown_diagnostics": [DataclassCodec.encode_envelope(d) for d in self._dispatcher.drain_teardown_diagnostics()]}
            finally:
                inst_lk.release()
        finally:
            with self._cond:
                self._lifecycle_ops_in_flight = max(0, self._lifecycle_ops_in_flight - 1)
                self._cond.notify_all()

    def _start_watchers_only(self) -> None:
        echo_guard, deb = self._watch_cfg.echo_guard, self._watch_cfg.watcher_debounce_sec
        supp, poll = (echo_guard.is_suppressed if echo_guard is not None else None), max(0.02, min(0.1, deb * 0.5))
        mods_hp = try_resolve_contained_subpath(self._workspace_root, MODULES_DIRNAME)
        if mods_hp is not None and os.path.isdir(str(mods_hp)):
            self._modules_watcher = PollingDirectoryWatcher((mods_hp,), lambda ps: self._record_watched_dirty("module", ps), debounce_sec=deb, poll_interval_sec=poll, is_suppressed=supp)
            self._watchers.append(self._modules_watcher)
        if self._watch_cfg.config_watch_roots:
            self._config_watcher = PollingDirectoryWatcher(self._watch_cfg.config_watch_roots, lambda ps: self._record_watched_dirty("config_both", ps), debounce_sec=deb, poll_interval_sec=poll, is_suppressed=supp)
            self._watchers.append(self._config_watcher)
        if self._watch_cfg.space_watch_roots:
            self._watchers.append(PollingDirectoryWatcher(self._watch_cfg.space_watch_roots, lambda ps: self._record_watched_dirty("space", ps), debounce_sec=deb, poll_interval_sec=poll, is_suppressed=supp))
        started: list[PollingDirectoryWatcher] = []
        try:
            for w in self._watchers:
                w.start()
                started.append(w)
        except BaseException:
            for w in reversed(started):
                w.stop()
            raise

    def _record_watched_dirty(self, kind: str, paths: frozenset[HostPath]) -> None:
        if not paths:
            return
        with self._cond:
            if self._stopping or self._stopped:
                return
            self._idle_monitor.record_external_activity()
            if kind == "config_both":
                self._dirty.add_paths("config", paths)
                self._dirty.add_paths("notify_config", paths)
            else:
                self._dirty.add_paths(kind, paths)
            self._cond.notify_all()

    def _extract_touched_modules(self, batch: _DirtyBatch) -> frozenset[ModuleId]:
        hp_root = try_resolve_contained_subpath(self._workspace_root, MODULES_DIRNAME)
        mods_root = hp_root.path if hp_root is not None else None
        return frozenset(batch.reload_modules) | {mid for hp in batch.module_paths if (mid := _extract_module_id_under(hp, mods_root)) is not None}

    def _resync_modules_watcher(self, modules: Optional[frozenset[ModuleId]]) -> None:
        hp_root = try_resolve_contained_subpath(self._workspace_root, MODULES_DIRNAME)
        mods_root = hp_root.path if hp_root is not None else None
        if not modules:
            self._dirty.clear_all_modules()
            if self._modules_watcher is not None and mods_root is not None:
                self._modules_watcher.resync_paths((HostPath(mods_root),))
            return
        self._dirty.prune_modules(modules, mods_root)
        if self._modules_watcher is not None and mods_root is not None:
            if sub_roots := tuple(r for m in modules if (r := try_resolve_contained_subpath(self._workspace_root, MODULES_DIRNAME, str(m))) is not None):
                self._modules_watcher.resync_paths(sub_roots)

    def _apply_locked_module_reload(self, modules: frozenset[ModuleId], *, reload_all: bool) -> None:
        target_mods = frozenset() if reload_all else modules
        self._resync_modules_watcher(None if reload_all else target_mods)
        self._dirty.drain_config_paths()
        if self._config_watcher is not None and self._watch_cfg.config_watch_roots:
            self._config_watcher.resync_paths(self._watch_cfg.config_watch_roots)
        self._dispatcher.reload_affected_modules(target_mods)
        self._periodic_loop.refresh_schedules()

    def _process_dirty_batch(self, batch: _DirtyBatch) -> frozenset[HostPath]:
        inst_lk, cancelled = self._acquire_cancellable_shared_installer_lock(timeout_sec=0.1)
        if cancelled:
            return frozenset()
        requeue = inst_lk is None
        try:
            with self._cond:
                if self._stopping or self._stopped:
                    return frozenset()
                requeue = requeue or self._deferred_boot_warmup or self._dispatcher.reload_gate.is_globally_gated()
            if requeue:
                if batch.reload_all or batch.reload_modules:
                    self._dirty.add_reload(frozenset() if batch.reload_all else batch.reload_modules)
                for kind, paths in (("module", batch.module_paths), ("config", batch.config_paths), ("notify_config", batch.notify_config_paths), ("space", batch.space_paths)):
                    self._dirty.add_paths(kind, paths)
                return frozenset()
            touched_mods = self._extract_touched_modules(batch)
            if CORE_MODULE_ID in batch.reload_modules or ((batch.reload_all or CORE_MODULE_ID in touched_mods) and self._has_deferred_core_mutation()):
                self.request_shutdown(core_handoff=True)
                return frozenset()
            if CORE_MODULE_ID in touched_mods:
                self._resync_modules_watcher(frozenset({CORE_MODULE_ID}))
            non_core_mods, pending_notify = touched_mods - frozenset({CORE_MODULE_ID}), set()
            if batch.reload_all or non_core_mods:
                self._apply_locked_module_reload(non_core_mods, reload_all=batch.reload_all)
                pending_notify.update(batch.notify_config_paths)
            elif batch.config_paths or batch.notify_config_paths:
                if self._config_watcher is not None and self._watch_cfg.config_watch_roots:
                    self._config_watcher.resync_paths(self._watch_cfg.config_watch_roots)
                self._dirty.drain_config_paths()
                if self._dispatcher.reload_config_and_contributes(changed_paths=[str(p) for p in sorted(batch.config_paths, key=str)], emit_event=False):
                    pending_notify.update(batch.notify_config_paths or batch.config_paths)
                self._periodic_loop.refresh_schedules()
            sp_tid = self._watch_cfg.on_space_changed_task
            if batch.space_paths and sp_tid is not None and not self._dispatcher.reload_gate.is_call_gated_for_quiesce(sp_tid.module_id):
                self._dispatch_bg_task(sp_tid, {"changed_paths": [str(p) for p in sorted(batch.space_paths, key=str)], "startup_catchup": False}, detached=True)
            return frozenset(pending_notify)
        finally:
            if inst_lk is not None:
                inst_lk.release()

    def _dispatch_bg_task(self, task_id: TaskId, raw_input: JsonObject, *, detached: bool = False) -> None:
        with self._cond:
            if self._base_phase_locked() != ContainerState.READY or self._deferred_boot_warmup or self._dispatcher.reload_gate.is_call_gated_for_quiesce(task_id.module_id):
                return
            self._active_bg_turns += 1

        def _run_bg_slot() -> None:
            try:
                self._run_acquired_bg_task(task_id, raw_input)
            finally:
                with self._cond:
                    self._active_bg_turns = max(0, self._active_bg_turns - 1)
                    self._cond.notify_all()

        if not detached:
            _run_bg_slot()
            return
        try:
            threading.Thread(target=_run_bg_slot, name=f"yscb-daemon-bg-{task_id}", daemon=True).start()
        except BaseException:
            with self._cond:
                self._active_bg_turns = max(0, self._active_bg_turns - 1)
                self._cond.notify_all()
            raise

    def _run_acquired_bg_task(self, task_id: TaskId, raw_input: JsonObject) -> None:
        out = self._dispatcher.invoke(InvokeRequest(
            task_id=task_id, raw_input=raw_input, workspace_root=self._workspace_root, caller_cwd=self._workspace_root,
            priority=ExecutionPriority.BACKGROUND, propagation=CallPropagationContext(is_internal_trigger=True),
        ))
        self._record_bg_diags(out.teardown_diagnostics, out.event_diagnostics, out.error if not out.ok else None)
