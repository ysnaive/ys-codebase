"""Top-level Composition Root (WorkspaceKernelFactory, WorkspaceKernel, and ModuleProviderAdapter) uniting Domains 1-6."""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field, replace
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import MappingProxyType
from typing import Callable, Final, Iterable, Iterator, Mapping, Optional, Sequence
import uuid
import weakref

from core.execution.daemon import (
    DaemonReloadControl,
    DaemonResumeControl,
    DaemonStopControl,
    DaemonRunState,
    DaemonWatcherConfig,
    SingleFlightDaemonSpawner,
    WorkspaceDaemon,
    query_daemon_control,
)
from core.execution.lifecycle import ContainerState
from core.execution.rpc import (
    DAEMON_SUBDIR,
    DaemonConnectionConfig,
    FrameKind,
    call_ephemeral_daemon_rpc,
    probe_daemon_endpoint,
)
from core.execution.runtime import (
    CORE_MODULE_ID,
    CallPropagationContext,
    CallerSurface,
    ClientRoutingPolicy,
    ConfigViewPort,
    DEFAULT_CACHE_DIRNAME,
    DaemonRpcInvokeReply,
    DispatcherHostOptions,
    ExecutionPriority,
    InvokeRequest,
    LOCKS_SUBDIR,
    MODULES_DIRNAME,
    ModuleDescriptor,
    ModuleProviderPort,
    ModuleRuntimeServices,
    ProtectedModuleLoader,
    RuntimeDispatcher,
    TaskOutcome,
    TaskRouteSpec,
    YscbModule,
    build_workspace_module_services_factory,
    resolve_active_call_tree_id,
    resolve_active_caller_module,
)
from core.filesystem.fs import (
    FileLock,
    MAX_JSON_FILE_BYTES,
    atomic_write_json,
    has_symlink_raw_path,
    is_symlink_or_reparse,
    read_json_dict,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
    try_resolve_contained_subpath,
)
from core.filesystem.space import (
    GitignoreMaterializer,
    HashPolicy,
    SpaceRegistry,
    SpaceScanner,
    SpaceSpec,
)
from core.filesystem.storage import ModuleDatabase
from core.filesystem.vfs import (
    KernelVfs,
    MountRule,
    ReadonlyPolicy,
    UriMountTable,
    VfsCapabilities,
    VfsEchoGuard,
    VfsHub,
    build_standard_mount_rules,
)
from core.foundation import (
    CancellationToken,
    DataclassCodec,
    ErrorCode,
    ErrorDetail,
    FlightLogConfig,
    FlightLogRouter,
    HostPath,
    IS_WINDOWS,
    JsonObject,
    JsonValue,
    LocaleCatalog,
    ModuleId,
    NullProfiler,
    Profiler,
    ProfilerNodeSnapshot,
    ProfilerRingBuffer,
    SemanticUri,
    TEST_SANDBOX_ENV_KEY,
    TaskId,
    YscbError,
    build_isolated_python_env,
    guard_standard_streams,
    is_process_alive,
    is_public_env_truthy,
    read_flight_log_env,
    read_public_env_value,
    require_non_none,
    require_pure_bool,
    require_pure_int,
    safe_real_to_float,
    strict_parse_json_object,
)
from core.metadata.config import ConfigStore, ModuleManifest, SnapshotVault
from core.metadata.contributes import (
    AggregatedContributes,
    ContributesAggregator,
    ExtensionPointSpec,
    ProvenanceGraph,
    ResolvedProjectRoot,
    bind_locale_getter_dialect,
    bind_locale_getter_owner,
    core_builtin_extension_points,
    discover_installed_manifests_map,
    extract_parsed_space_contributions,
    extract_validated_uri_schemes,
    hash_workspace_surface_trees,
    is_active_cross_workspace_call,
    is_control_plane_reserved_path,
    is_permitted_contributed_mount_root,
    load_workspace_locale_catalog,
    probe_workspace_host_dir,
    register_managed_child_dispatcher,
    register_sdk_core_post_call_hook,
    resolve_sdk_core_dispatcher_binder,
    resolve_workspace_project_root,
    unbind_locale_getter_dialect,
    unbind_locale_getter_owner,
)
from core.packaging.env import (
    EnvGarbageCollector,
    EnvHealthProbe,
    EnvSpec,
    ImmutableVenvPool,
    acquire_env_lease_for_python,
    touch_env_last_used,
)
from core.packaging.installer import OfflinePackageEngine
from core.surface.bootstrap.system_module import (
    CoreSystemModule,
    DaemonStartInput,
    SystemKernelPort,
    SystemResultView,
    bind_system_kernel,
    lookup_active_system_kernel,
    unbind_system_kernel,
)
from core.surface.cli import (
    CLI_DEFAULT_PROVIDER_URL,
    CLI_DEFAULT_SELF_UPDATE_URL,
    CliKernelSession,
    IndexedTaskEntry,
    ModuleTasksIndex,
    WorkspaceTasksIndexCache,
    compile_tasks_index,
)
from core.surface.sdk import (
    ExitCodeProvider,
    InMemoryModule,
    MigrationRequest,
    Module,
    format_output,
)

DEFAULT_PROVIDER_URL: Final[str] = CLI_DEFAULT_PROVIDER_URL
DEFAULT_SELF_UPDATE_URL: Final[str] = CLI_DEFAULT_SELF_UPDATE_URL

@dataclass(frozen=True, slots=True)
class _SpaceNotifyRpcEnvelope:
    task_id: TaskId
    raw_input: JsonObject
    workspace_root: HostPath
    caller_cwd: HostPath
    caller_env: Mapping[str, str] = field(default_factory=dict)
    caller_surface: CallerSurface = CallerSurface.SDK
    priority: ExecutionPriority = ExecutionPriority.BACKGROUND
    approval_scope: frozenset[TaskId] = field(default_factory=frozenset)
    allow_conditional: bool = True
    timeout_ms: Optional[int] = 2000
    propagation: CallPropagationContext = field(default_factory=CallPropagationContext)


_TIER1_FORMAT_SNIPPET: Final[str] = (
    "import json, os, sys\n"
    "_proto_fd = os.dup(1)\n"
    "os.set_inheritable(_proto_fd, False)\n"
    "os.dup2(2, 1)\n"
    "_proto_out = os.fdopen(_proto_fd, 'w', encoding='utf-8', closefd=True)\n"
    "try:\n"
    "    from core.execution.runtime import ModuleDescriptor, ProtectedModuleLoader\n"
    "    from core.foundation import DataclassCodec, HostPath, TaskId, guard_standard_streams, require_pure_int\n"
    "    from core.surface.sdk import ExitCodeProvider, format_output\n"
    "    ws = HostPath(sys.argv[1])\n"
    "    desc = DataclassCodec.decode(ModuleDescriptor, json.loads(sys.argv[2]))\n"
    "    tid = TaskId(sys.argv[3])\n"
    "    render_human = sys.argv[4] == '1'\n"
    "    raw_val = json.loads(sys.stdin.read())\n"
    "    with guard_standard_streams():\n"
    "        loader = ProtectedModuleLoader(ws)\n"
    "        art = loader.load_module_artifact(desc)\n"
    "        try:\n"
    "            bt = next((t for t in art.instance.tasks() if t.task_id == tid), None)\n"
    "            if bt is None:\n"
    "                _payload = json.dumps({'ok': False})\n"
    "            else:\n"
    "                val = DataclassCodec.decode(bt.metadata.output_type, raw_val)\n"
    "                if render_human:\n"
    "                    txt, code = format_output(val)\n"
    "                    eff_code = int(code) if isinstance(val, ExitCodeProvider) else 0\n"
    "                else:\n"
    "                    txt = None\n"
    "                    eff_code = require_pure_int(val.exit_code(), 'ExitCodeProvider.exit_code()', min_val=None, max_val=None) if isinstance(val, ExitCodeProvider) else 0\n"
    "                _payload = json.dumps({'ok': True, 'text': txt, 'exit_code': eff_code}, ensure_ascii=False)\n"
    "        finally:\n"
    "            loader.cleanup_package(art.package_key)\n"
    "    _proto_out.write(_payload)\n"
    "    _proto_out.flush()\n"
    "finally:\n"
    "    _proto_out.close()\n"
)

_TIER1_COMPILE_INDEX_SNIPPET: Final[str] = (
    "import json, os, sys\n"
    "_proto_fd = os.dup(1)\n"
    "os.set_inheritable(_proto_fd, False)\n"
    "os.dup2(2, 1)\n"
    "_proto_out = os.fdopen(_proto_fd, 'w', encoding='utf-8', closefd=True)\n"
    "try:\n"
    "    from core.execution.runtime import ModuleDescriptor, ProtectedModuleLoader\n"
    "    from core.foundation import DataclassCodec, HostPath, guard_standard_streams\n"
    "    from core.surface.cli import ModuleTasksIndex, compile_tasks_index\n"
    "    ws = HostPath(sys.argv[1])\n"
    "    desc = DataclassCodec.decode(ModuleDescriptor, json.loads(sys.argv[2]))\n"
    "    mf_desc = sys.argv[3]\n"
    "    with guard_standard_streams():\n"
    "        loader = ProtectedModuleLoader(ws)\n"
    "        art = loader.load_module_artifact(desc)\n"
    "        try:\n"
    "            idx = compile_tasks_index(art.instance)\n"
    "            if not idx.description and mf_desc:\n"
    "                idx = ModuleTasksIndex(module_id=idx.module_id, module_aliases=idx.module_aliases, description=mf_desc, tasks=idx.tasks)\n"
    "            _payload = json.dumps({'ok': True, 'index': idx.to_json_dict()}, ensure_ascii=False)\n"
    "        finally:\n"
    "            loader.cleanup_package(art.package_key)\n"
    "    _proto_out.write(_payload)\n"
    "    _proto_out.flush()\n"
    "finally:\n"
    "    _proto_out.close()\n"
)


def _resolve_managed_env_dir_for_python(yscb_root: HostPath, venv_python: HostPath) -> Optional[HostPath]:
    venv_root = try_resolve_contained_subpath(yscb_root, ".venv")
    if venv_root is None or not os.path.isdir(str(venv_root)) or is_symlink_or_reparse(str(venv_root)):
        return None
    venv_root_key = venv_root.comparison_key
    cur_p = venv_python.path.parent
    env_dir_path: Optional[Path] = None
    while True:
        parent_p = cur_p.parent
        if parent_p == cur_p:
            break
        if os.path.normcase(str(parent_p)) == venv_root_key:
            env_dir_path = cur_p
            break
        cur_p = parent_p
    if env_dir_path is None or env_dir_path.name.startswith("."):
        return None
    env_dir = try_resolve_contained_subpath(venv_root, env_dir_path.name)
    if env_dir is None or is_symlink_or_reparse(str(env_dir)) or not os.path.isdir(str(env_dir)):
        return None
    return env_dir


def _build_unready_tier1_sentinel(yscb_root: HostPath, mod_id: ModuleId) -> HostPath:
    stem = f".yscb_unready_tier1_{mod_id.value}"
    cand_dir = yscb_root.path / stem
    if os.path.lexists(cand_dir):
        cand_dir = yscb_root.path / f"{stem}_{uuid.uuid4().hex[:8]}"
    rel_py = ("Scripts", "python.exe") if IS_WINDOWS else ("bin", "python")
    return HostPath(cand_dir.joinpath(*rel_py))


def _safe_aggregate_core(contributes: ContributesAggregator) -> AggregatedContributes:
    try:
        return contributes.aggregate(CORE_MODULE_ID, strict=False)
    except YscbError:
        return AggregatedContributes(
            target_module=CORE_MODULE_ID,
            raw_merged={},
            provenance=ProvenanceGraph({}),
        )


def _build_extra_mount_rules(
    host_dir: HostPath,
    yscb_root: HostPath,
    proj_info: ResolvedProjectRoot,
    cfg_store: ConfigStore,
    core_agg: AggregatedContributes,
) -> tuple[MountRule, ...]:
    rules: list[MountRule] = []
    caps = (
        VfsCapabilities.READABLE
        | VfsCapabilities.WRITABLE
        | VfsCapabilities.PERSISTENT
        | VfsCapabilities.ENUMERABLE
        | VfsCapabilities.PHYSICAL_PATH
        | VfsCapabilities.GIT_TRACKED
    )
    for item in extract_validated_uri_schemes(host_dir, cfg_store, core_agg):
        try:
            cand_rule = MountRule(
                scheme=item.scheme,
                target_path=item.target_path,
                target_uri=item.target_uri,
                capabilities=caps,
                provider_module=item.provider_module,
                config_binding=item.config_binding,
                description=item.description,
            )
            probe_table = UriMountTable(
                build_standard_mount_rules(
                    host_dir,
                    yscb_root,
                    project_root=proj_info.project_root,
                    extra_rules=(*rules, cand_rule),
                )
            )
        except (ValueError, YscbError):
            continue
        resolved_hp: Optional[HostPath] = None
        try:
            resolved_hp = probe_table.resolve_physical(SemanticUri(item.scheme, ""))
        except YscbError as exc:
            if exc.detail.code != ErrorCode.URI_UNDEFINED:
                continue
            resolved_hp = None
        if not is_permitted_contributed_mount_root(
            resolved_hp,
            owner=item.owner,
            host_dir=host_dir,
            yscb_root=yscb_root,
            proj_info=proj_info,
        ):
            continue
        rules.append(cand_rule)
    return tuple(rules)


def _extract_contributed_spaces(core_agg: AggregatedContributes) -> tuple[SpaceSpec, ...]:
    return tuple(
        SpaceSpec(
            space_id=item.space_id,
            entries=item.entries,
            include=item.include,
            exclude=item.exclude,
            presets=item.presets,
            compose=item.compose,
            watch=item.watch,
            hash_policy=HashPolicy(item.hash_policy_name),
            description=item.description,
        )
        for item in extract_parsed_space_contributions(core_agg)
    )


def _is_valid_disk_tasks_index(idx_hp: Optional[HostPath], expected_module: ModuleId) -> bool:
    if idx_hp is None or not os.path.isfile(str(idx_hp)) or is_symlink_or_reparse(str(idx_hp)):
        return False
    try:
        raw_bytes = read_nofollow_regular_bytes(str(idx_hp), max_bytes=MAX_JSON_FILE_BYTES)
    except OSError:
        return False
    if raw_bytes is None:
        return False
    try:
        doc = strict_parse_json_object(raw_bytes.decode("utf-8"))
        parsed = ModuleTasksIndex.from_json_dict(doc)
    except (UnicodeDecodeError, ValueError, YscbError):
        return False
    return parsed.module_id == expected_module


def _resolve_launcher_script_path(host_dir: HostPath, explicit: Optional[HostPath]) -> Optional[HostPath]:
    if explicit is not None:
        return explicit
    resolved_self = Path(__file__).resolve()
    candidates: list[Path] = [Path(host_dir.path) / "yscb.py"]
    for depth in (5, 6, 4):
        if len(resolved_self.parents) > depth:
            candidates.append(resolved_self.parents[depth] / "yscb.py")
    for cand in candidates:
        if (cand.drive or cand.anchor) and not cand.is_absolute():
            continue
        raw_cand = str(cand)
        if has_symlink_raw_path(raw_cand) or is_symlink_or_reparse(raw_cand):
            continue
        if os.path.isfile(raw_cand):
            return HostPath(raw_cand)
    return None


def _discover_peer_workspace_host_dir(peer_ws: HostPath) -> HostPath:
    raw_peer = str(peer_ws)
    if has_symlink_raw_path(raw_peer) or is_symlink_or_reparse(raw_peer) or not os.path.isdir(raw_peer):
        raise YscbError(ErrorCode.ACCESS_DENIED, f"Target workspace '{peer_ws}' does not exist or traverses a symlink.")
    found_host = probe_workspace_host_dir(peer_ws)
    if found_host is not None:
        return found_host
    raise YscbError(
        ErrorCode.ACCESS_DENIED,
        f"Target workspace '{peer_ws}' is not a valid initialized YS-Codebase workspace.",
    )


class ModuleProviderAdapter(ModuleProviderPort):
    """Composition Root adapter bridging Domain 3/4 manifests, .venv pool, and tasks.index.json to ModuleProviderPort."""

    def __init__(
        self,
        *,
        yscb_root: HostPath,
        env_pool: ImmutableVenvPool,
        core_route_specs: Sequence[TaskRouteSpec],
        on_reload: Optional[Callable[[], None]] = None,
    ) -> None:
        self._yscb_root = yscb_root
        self._env_pool = env_pool
        self._core_routes = tuple(core_route_specs)
        self._on_reload = on_reload
        self._lock = threading.RLock()
        self._cached: Optional[tuple[ModuleDescriptor, ...]] = None
        self._pending_evicted: frozenset[ModuleId] = frozenset()

    @property
    def pending_evicted(self) -> frozenset[ModuleId]:
        with self._lock:
            return self._pending_evicted

    def set_pending_evicted(self, modules: frozenset[ModuleId]) -> None:
        with self._lock:
            had_evicted = bool(self._pending_evicted)
            self._pending_evicted = modules
            if not modules and had_evicted:
                self._cached = None

    def _build_descriptors(self) -> tuple[ModuleDescriptor, ...]:
        core_dir = resolve_contained_subpath(self._yscb_root, MODULES_DIRNAME, CORE_MODULE_ID.value)
        descs: list[ModuleDescriptor] = [
            ModuleDescriptor(
                module_id=CORE_MODULE_ID,
                module_dir=core_dir,
                declared_tasks=self._core_routes,
            )
        ]
        manifests = discover_installed_manifests_map(self._yscb_root)
        active_mfs = tuple(mf for mid, mf in manifests.items() if mid not in self._pending_evicted)
        group_specs = ImmutableVenvPool.resolve_group_specs(active_mfs)
        for mod_id in sorted(manifests.keys(), key=lambda m: m.value):
            if mod_id == CORE_MODULE_ID or mod_id in self._pending_evicted:
                continue
            mf = manifests[mod_id]
            mod_dir = try_resolve_contained_subpath(self._yscb_root, MODULES_DIRNAME, mod_id.value)
            if mod_dir is None:
                continue
            declared: tuple[TaskRouteSpec, ...] = ()
            idx_hp = try_resolve_contained_subpath(mod_dir, "tasks.index.json")
            if idx_hp is not None and not is_symlink_or_reparse(str(idx_hp)):
                try:
                    raw_idx = read_nofollow_regular_bytes(str(idx_hp), max_bytes=MAX_JSON_FILE_BYTES)
                except OSError:
                    raw_idx = None
                if raw_idx is not None:
                    try:
                        doc = strict_parse_json_object(raw_idx.decode("utf-8"))
                        idx_obj = ModuleTasksIndex.from_json_dict(doc)
                        declared = idx_obj.to_route_specs() if idx_obj.module_id == mod_id else ()
                    except (UnicodeDecodeError, ValueError, YscbError):
                        declared = ()

            venv_py: Optional[HostPath] = None
            env_spec = group_specs.get(mod_id)
            if env_spec is not None:
                venv_py = self._env_pool.get_python_executable(env_spec)
                if venv_py is None:
                    venv_py = _build_unready_tier1_sentinel(self._yscb_root, mod_id)
            elif mf.is_tier1:
                venv_py = _build_unready_tier1_sentinel(self._yscb_root, mod_id)

            descs.append(
                ModuleDescriptor(
                    module_id=mod_id,
                    module_dir=mod_dir,
                    entry_file=mf.entry,
                    venv_group=mf.venv_group,
                    venv_python=venv_py,
                    eager_warmup=mf.eager_warmup,
                    declared_tasks=declared,
                )
            )
        return tuple(descs)

    def list_modules(self) -> Sequence[ModuleDescriptor]:
        with self._lock:
            if self._cached is None:
                self._cached = self._build_descriptors()
            return self._cached

    def get_module(self, module_id: ModuleId) -> Optional[ModuleDescriptor]:
        for desc in self.list_modules():
            if desc.module_id == module_id:
                return desc
        return None

    def invalidate_cache(self) -> None:
        with self._lock:
            self._cached = None

    def reload(self) -> None:
        with self._lock:
            self._cached = None
        if self._on_reload is not None:
            self._on_reload()


def _compute_dir_py_fingerprint(mod_dir: HostPath) -> str:
    h = hashlib.sha256()
    root_s = str(mod_dir)
    stack: list[tuple[str, str]] = [("", root_s)]
    while stack:
        rel_pfx, cur_p = stack.pop()
        try:
            with os.scandir(cur_p) as it_d:
                entries = sorted(it_d, key=lambda e: e.name, reverse=True)
        except OSError:
            continue
        for ent in entries:
            if ent.name.startswith(".") or ent.name == "__pycache__" or ent.is_symlink() or is_symlink_or_reparse(ent.path):
                continue
            rel_name = f"{rel_pfx}/{ent.name}" if rel_pfx else ent.name
            try:
                if ent.is_dir(follow_symlinks=False):
                    stack.append((rel_name, ent.path))
                elif ent.name.endswith(".py") and ent.is_file(follow_symlinks=False):
                    st_p = os.stat(ent.path, follow_symlinks=False)
                    h.update(f"{rel_name}:{st_p.st_mtime_ns}:{st_p.st_size}\n".encode("utf-8"))
            except OSError:
                continue
    return h.hexdigest()


def _compute_peer_workspace_fingerprint(peer_host_dir: HostPath, peer_ws: HostPath) -> str:
    h = hashlib.sha256()
    h.update(f"host:{peer_host_dir}\nws:{peer_ws}\n".encode("utf-8"))
    for root_cfg_name in ("yscb.config.json", "yscb.config.local.json"):
        cand_cfg = os.path.join(str(peer_host_dir), root_cfg_name)
        try:
            if not has_symlink_raw_path(cand_cfg) and not is_symlink_or_reparse(cand_cfg):
                st = os.stat(cand_cfg, follow_symlinks=False)
                h.update(f"rcfg:{root_cfg_name}:{st.st_mtime_ns}:{st.st_size}\n".encode("utf-8"))
        except OSError:
            pass
    hash_workspace_surface_trees(
        h.update,
        peer_ws,
        include_space_db=True,
        include_tasks_index=True,
    )
    manifests_map = discover_installed_manifests_map(peer_ws)
    mods_root = try_resolve_contained_subpath(peer_ws, MODULES_DIRNAME)
    if mods_root is not None and not is_symlink_or_reparse(str(mods_root)) and os.path.isdir(str(mods_root)):
        try:
            with os.scandir(str(mods_root)) as it_mods:
                mod_entries = sorted(it_mods, key=lambda e: e.name)
            for mod_ent in mod_entries:
                if (
                    mod_ent.name.startswith(".")
                    or mod_ent.name == CORE_MODULE_ID.value
                    or mod_ent.is_symlink()
                    or is_symlink_or_reparse(mod_ent.path)
                ):
                    continue
                if not mod_ent.is_dir(follow_symlinks=False):
                    continue
                try:
                    cand_mid = ModuleId(mod_ent.name)
                except ValueError:
                    cand_mid = None
                mf_obj = manifests_map.get(cand_mid) if cand_mid is not None else None
                if mf_obj is None or not mf_obj.is_tier1:
                    mod_hp = try_resolve_contained_subpath(mods_root, mod_ent.name)
                    if mod_hp is not None:
                        h.update(f"mpy:{mod_ent.name}:{_compute_dir_py_fingerprint(mod_hp)}\n".encode("utf-8"))
        except OSError:
            pass
    return h.hexdigest()


def _compute_config_and_contributes_fingerprint(host_dir: HostPath, yscb_root: HostPath, cfg_fp: str) -> str:
    h = hashlib.sha256()
    h.update(f"cfg:{cfg_fp}\n".encode("utf-8"))
    hash_workspace_surface_trees(
        h.update,
        yscb_root,
        include_space_db=False,
        include_tasks_index=False,
    )
    _ = host_dir
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class _PendingDaemonSync:
    quiesced: bool
    quiesce_epoch: Optional[int]
    core_handoff: bool = False


def _close_retired_kernels_safely(kernels: Sequence[WorkspaceKernel]) -> None:
    if not kernels:
        return
    first_exc: Optional[Exception] = None
    for idx, k_inst in enumerate(kernels):
        try:
            k_inst.close()
        except Exception as exc:
            if first_exc is None:
                first_exc = exc
        except BaseException:
            for rem_k in kernels[idx + 1 :]:
                try:
                    rem_k.close()
                except BaseException:
                    pass
            raise
    if first_exc is not None:
        raise first_exc


@dataclass(frozen=True, slots=True)
class _DeferredDaemonOutcome:
    acquired_lock: bool
    daemon_rc: int
    post_close_rc: int


def _capture_kernel_profiler_caller() -> Optional[str]:
    frame = inspect.currentframe()
    try:
        cur = frame.f_back if frame is not None else None
        if cur is not None:
            cur = cur.f_back
        if cur is None:
            return None
        fname = os.path.basename(cur.f_code.co_filename) or "<unknown>"
        return f"{fname}:{cur.f_lineno}"
    finally:
        del frame


class _KernelActiveProfiler:
    """Profiler adapter delegating to init-time Profiler during boot and active service Profiler at runtime."""

    __slots__ = ("_init_profiler", "_svc_profiler")

    def __init__(self, init_profiler: Optional[Profiler] = None) -> None:
        self._init_profiler: Optional[Profiler] = init_profiler
        self._svc_profiler: Optional[Profiler] = None

    def bind_runtime_profiler(self, profiler: Profiler) -> None:
        self._svc_profiler = profiler

    def finish_init(self) -> None:
        self._init_profiler = None

    def _target(self) -> Profiler:
        if self._init_profiler is not None:
            return self._init_profiler
        if self._svc_profiler is not None:
            return self._svc_profiler
        return NullProfiler()

    def scope(
        self,
        path: Optional[str] = None,
        name: Optional[str] = None,
        *,
        caller: Optional[str] = None,
    ) -> AbstractContextManager[None]:
        target = self._target()
        if isinstance(target, NullProfiler):
            return target.scope(path, name, caller=caller)
        eff_caller = caller if caller is not None else _capture_kernel_profiler_caller()
        return target.scope(path, name, caller=eff_caller)

    def scope_relative(
        self,
        path: str,
        name: Optional[str] = None,
        *,
        caller: Optional[str] = None,
    ) -> AbstractContextManager[None]:
        target = self._target()
        if isinstance(target, NullProfiler):
            return target.scope_relative(path, name, caller=caller)
        eff_caller = caller if caller is not None else _capture_kernel_profiler_caller()
        return target.scope_relative(path, name, caller=eff_caller)

    def merge_subtree(
        self,
        subtree: ProfilerNodeSnapshot,
        *,
        mount_path: Optional[str] = None,
    ) -> None:
        self._target().merge_subtree(subtree, mount_path=mount_path)

    def snapshot(self) -> ProfilerNodeSnapshot:
        return self._target().snapshot()

    def current_span_path(self) -> str:
        return self._target().current_span_path()


def _load_flight_log_config(cfg_store: ConfigStore) -> FlightLogConfig:
    try:
        raw_obs = cfg_store.get_module_value(CORE_MODULE_ID, "observability", default=None)
    except (OSError, ValueError, YscbError):
        return FlightLogConfig()
    if isinstance(raw_obs, Mapping):
        try:
            return DataclassCodec.decode(FlightLogConfig, raw_obs)
        except (ValueError, TypeError, KeyError, YscbError):
            return FlightLogConfig()
    return FlightLogConfig()


def _run_deferred_daemon_host(
    host_dir: HostPath,
    yscb_root: HostPath,
    yscb_script_path: Optional[HostPath],
    run_mode: bool,
    on_ready: Optional[Callable[[], None]],
) -> _DeferredDaemonOutcome:
    daemon_kernel = WorkspaceKernelFactory.create(
        host_dir,
        yscb_root,
        is_daemon_host=True,
        yscb_script_path=yscb_script_path,
        dialect=None,
    )
    ready_fired = False

    def _handle_ready() -> None:
        nonlocal ready_fired
        ready_fired = True
        if on_ready is not None:
            on_ready()

    try:
        daemon = daemon_kernel.build_daemon()
        rc = int(daemon.run_forever(console_mode=run_mode, ready_callback=_handle_ready))
        acquired_lock = ready_fired or daemon.snapshot_status().state != DaemonRunState.BOOTING
        post_rc = rc if (ready_fired or not acquired_lock or rc != 0) else 1
        return _DeferredDaemonOutcome(acquired_lock=acquired_lock, daemon_rc=rc, post_close_rc=post_rc)
    finally:
        daemon_kernel.close()


class WorkspaceKernel(SystemKernelPort, CliKernelSession):
    """Fully wired 6-domain microkernel instance for a single (host_dir, yscb_root) workspace."""

    def __init__(
        self,
        *,
        host_dir: HostPath,
        yscb_root: HostPath,
        is_daemon_host: bool,
        force_cold: bool,
        extra_modules: Sequence[YscbModule],
        yscb_script_path: Optional[HostPath],
        dialect: Optional[str] = None,
        extra_config_types: Mapping[ModuleId, type[object]] = MappingProxyType({}),
        extra_live_specs: Mapping[ModuleId, Sequence[ExtensionPointSpec[object]]] = MappingProxyType({}),
        allow_deferred_daemon_console: bool = False,
        is_managed_child: bool = False,
        allow_auto_spawn: bool = True,
        inherit_host_env_locale: bool = True,
        raw_env_locale_override: Optional[str] = None,
        profiler: Optional[Profiler] = None,
    ) -> None:
        self._kernel_profiler = _KernelActiveProfiler(profiler)
        self._daemon_boot_id: str = uuid.uuid4().hex if is_daemon_host else ""
        self._profiler_ring_buffer: Optional[ProfilerRingBuffer] = (
            ProfilerRingBuffer(maxlen=512) if is_daemon_host else None
        )
        self._host_dir = host_dir
        self._yscb_root = yscb_root
        self._cache_dir = resolve_contained_subpath(yscb_root, DEFAULT_CACHE_DIRNAME)
        self._is_daemon_host = is_daemon_host
        self._force_cold = bool(force_cold)
        self._has_extra_modules = bool(extra_modules)
        self._is_managed_child = bool(is_managed_child)
        self._inherit_host_env_locale = bool(inherit_host_env_locale) and not is_daemon_host
        self._yscb_script_path = yscb_script_path
        self._resolved_script_path = _resolve_launcher_script_path(host_dir, yscb_script_path)
        self._dialect: Optional[str] = (
            None
            if is_daemon_host
            else (dialect.strip() if isinstance(dialect, str) and dialect.strip() else None)
        )
        self._raw_env_locale_override: Optional[str] = (
            None
            if is_daemon_host
            else (raw_env_locale_override.strip() if isinstance(raw_env_locale_override, str) else None)
        )

        def _get_locale() -> LocaleCatalog:
            return self._current_locale()

        self._locale_getter_fn: Callable[[], LocaleCatalog] = _get_locale
        self._extra_config_types: dict[ModuleId, type[object]] = dict(extra_config_types)
        self._live_specs: dict[ModuleId, Sequence[ExtensionPointSpec[object]]] = {
            CORE_MODULE_ID: core_builtin_extension_points(),
            **dict(extra_live_specs),
        }
        self._reload_lock = threading.RLock()
        self._refresh_depth_by_tid: dict[int, int] = {}
        self._installer_op_lock = threading.RLock()
        self._installer_lock_depth = 0
        self._space_sync_op_lock = threading.RLock()
        self._space_sync_lock_depth = 0
        self._deferred_quiesce_space_sync = False
        self._has_mount_table = False
        self._retired_mount_tables: list[UriMountTable] = []
        self._active_custom_mount_roots: tuple[HostPath, ...] = ()
        self._retired_custom_mount_roots: list[HostPath] = []
        self._closing = False
        self._closed = False
        self._built_daemons: list[weakref.ReferenceType[WorkspaceDaemon]] = []
        self._allow_deferred_daemon_console = bool(allow_deferred_daemon_console)
        self._deferred_daemon_console_mode: Optional[bool] = None
        self._pending_daemon_sync: Optional[_PendingDaemonSync] = None
        self._pending_dynamic_space_notify: bool = False
        self._post_close_exit_code: Optional[int] = None
        self._tier0_loaded_pkgs: list[str] = []
        self._tier0_output_cache: dict[ModuleId, _Tier0OutputCacheEntry] = {}
        self._owned_child_kernels: dict[str, WorkspaceKernel] = {}
        self._owned_child_fingerprints: dict[str, str] = {}
        self._owned_child_sync_locks: dict[str, threading.RLock] = {}
        self._child_last_checkout_mono: dict[int, float] = {}
        self._retired_child_kernels: list[WorkspaceKernel] = []
        self._module_provider_opt: Optional[ModuleProviderAdapter] = None
        self._project_root: Optional[HostPath] = None
        self._project_root_disabled: bool = False
        self._applied_metadata_fp: str = ""
        self._applied_tier0_code_fp: str = ""
        self._last_notified_cfg_fp: str = ""

        with self._kernel_profiler.scope_relative("Kernel/ConfigAndVfs"):
            self._config_store = ConfigStore(host_dir=host_dir, yscb_root=yscb_root)
            self._flight_log_router = FlightLogRouter(
                resolve_contained_subpath(self._cache_dir, "logs"),
                config=_load_flight_log_config(self._config_store),
                env=read_flight_log_env(),
                daemon_boot_id=self._daemon_boot_id,
            )
            try:
                self._snapshot_vault = SnapshotVault(host_dir=host_dir, yscb_root=yscb_root)
                self._readonly_policy = ReadonlyPolicy()
                self._echo_guard = VfsEchoGuard()
                self._env_pool = ImmutableVenvPool(yscb_root=yscb_root, cache_dir=self._cache_dir)
                self._env_probe = EnvHealthProbe(self._env_pool)
                self._env_gc = EnvGarbageCollector(self._env_pool)

                manifests_map = discover_installed_manifests_map(yscb_root)
                self._contributes = ContributesAggregator(
                    yscb_root=yscb_root,
                    manifests=tuple(manifests_map.values()),
                    live_specs=self._live_specs,
                )
                core_agg = _safe_aggregate_core(self._contributes)
                self._rebuild_vfs_from_core_agg(core_agg)
            except BaseException:
                self._flight_log_router.close()
                self._kernel_profiler.finish_init()
                raise

        try:
            os.makedirs(str(resolve_contained_subpath(yscb_root, ".storage.local", "core", "space")), exist_ok=True)
            with self._kernel_profiler.scope_relative("Kernel/SpaceDb"):
                self._space_db = ModuleDatabase(
                    self._kernel_vfs,
                    SemanticUri("storage.local", "core/space/state.db"),
                    profiler=self._kernel_profiler,
                )
        except BaseException:
            self._flight_log_router.close()
            self._kernel_profiler.finish_init()
            raise
        try:
            with self._kernel_profiler.scope_relative("Kernel/SpaceAndServices"):
                self._rebuild_space_and_services_locked(core_agg)
            with self._kernel_profiler.scope_relative("Kernel/TasksIndex"):
                self.ensure_installed_tasks_indices()

            with self._kernel_profiler.scope_relative("Kernel/Dispatcher"):
                core_mod = CoreSystemModule(self).to_yscb_module()
                register_sdk_core_post_call_hook(core_mod, self.flush_pending_daemon_sync)
                all_in_mem = (core_mod, *extra_modules)
                self._output_types: dict[TaskId, object] = {
                    bt.task_id: bt.metadata.output_type
                    for ym in all_in_mem
                    for bt in ym.tasks()
                }
                self._module_provider = ModuleProviderAdapter(
                    yscb_root=yscb_root,
                    env_pool=self._env_pool,
                    core_route_specs=tuple(bt.route_spec for bt in core_mod.tasks()),
                    on_reload=self._on_provider_reloaded,
                )
                self._module_provider_opt = self._module_provider
                self._applied_metadata_fp = self._compute_metadata_state_fingerprint_locked()
                self._applied_tier0_code_fp = self._compute_tier0_code_fingerprint()
                self._last_notified_cfg_fp = self.config_and_contributes_fingerprint()
                spawner = self._build_daemon_spawner()
                conn_cfg = DaemonConnectionConfig(
                    enabled=(not is_daemon_host and not force_cold),
                    auto_spawn=(
                        not is_daemon_host
                        and not force_cold
                        and bool(allow_auto_spawn)
                        and spawner.can_spawn_in_environment()
                    ),
                    strict_hot_dispatch=False,
                )
                self._spawner = spawner
                self._dispatcher = RuntimeDispatcher(
                    workspace_root=yscb_root,
                    cache_dir=self._cache_dir,
                    module_provider=self._module_provider,
                    options=DispatcherHostOptions(
                        config_view=_DaemonConfigViewAdapter(self),
                        daemon_spawner=spawner,
                        connection_config=conn_cfg,
                        is_daemon_host=is_daemon_host,
                        child_dispatcher_factory=self._resolve_child_dispatcher,
                        peer_cache_dir_resolver=lambda peer_ws: resolve_contained_subpath(peer_ws, DEFAULT_CACHE_DIRNAME),
                        owns_child_dispatchers=False,
                        in_memory_modules=all_in_mem,
                        module_services_factory=self._resolve_module_services,
                        worker_host_dir=host_dir,
                        env_lease_acquire=self._acquire_env_lease,
                        env_touch_used=self._touch_env_used_for_python,
                        flight_log_router=self._flight_log_router,
                        daemon_boot_id=self._daemon_boot_id,
                        profiler_ring_buffer=self._profiler_ring_buffer,
                    ),
                )
                bind_locale_getter_owner(self._dispatcher, self._locale_getter_fn)
                self._persist_core_disk_index_if_present()
                if not self._is_managed_child:
                    bind_system_kernel(yscb_root, self)
        except BaseException:
            unbind_locale_getter_dialect(self._locale_getter_fn)
            self._space_db.close()
            self._flight_log_router.close()
            raise
        finally:
            self._kernel_profiler.finish_init()

    def _acquire_env_lease(self, venv_python: HostPath) -> Optional[Callable[[], None]]:
        lease = acquire_env_lease_for_python(self._env_pool, venv_python)
        return lease.release if lease is not None else None

    def _touch_env_used_for_python(self, venv_python: HostPath) -> None:
        env_dir = _resolve_managed_env_dir_for_python(self._yscb_root, venv_python)
        if env_dir is not None:
            touch_env_last_used(env_dir)

    def _rebuild_vfs_from_core_agg(self, core_agg: AggregatedContributes) -> None:
        proj_info = resolve_workspace_project_root(self._host_dir, self._config_store)
        proj_root, proj_disabled = proj_info.project_root, proj_info.disabled
        self._project_root = proj_root
        self._project_root_disabled = proj_disabled
        extra_mounts = _build_extra_mount_rules(
            self._host_dir,
            self._yscb_root,
            proj_info,
            self._config_store,
            core_agg,
        )
        prev_mt = self._mount_table if self._has_mount_table else None
        prev_roots = self._active_custom_mount_roots if self._has_mount_table else ()
        active_roots: list[HostPath] = []
        seen_root_keys: set[str] = set()
        raw_cand_roots: list[HostPath] = []
        if not proj_disabled and proj_root is not None:
            raw_cand_roots.append(proj_root)
        for m_rule in extra_mounts:
            if m_rule.target_path is not None:
                raw_cand_roots.append(m_rule.target_path)
        for cand_r in raw_cand_roots:
            if cand_r.path in self._host_dir.path.parents or cand_r.path in self._yscb_root.path.parents:
                continue
            r_ck = cand_r.comparison_key
            if r_ck not in seen_root_keys:
                seen_root_keys.add(r_ck)
                active_roots.append(cand_r)
        self._active_custom_mount_roots = tuple(active_roots)
        self._mount_table = UriMountTable(
            build_standard_mount_rules(
                self._host_dir,
                self._yscb_root,
                project_root=proj_root,
                extra_rules=extra_mounts,
            )
        )
        self._has_mount_table = True
        if prev_mt is not None:
            self._retired_mount_tables.append(prev_mt)
            if len(self._retired_mount_tables) > 32:
                del self._retired_mount_tables[:-32]
        for old_r in prev_roots:
            if all(x.comparison_key != old_r.comparison_key for x in self._retired_custom_mount_roots):
                self._retired_custom_mount_roots.append(old_r)
        if len(self._retired_custom_mount_roots) > 64:
            del self._retired_custom_mount_roots[:-64]
        self._vfs_hub = VfsHub(
            self._mount_table,
            readonly_policy=self._readonly_policy,
            echo_guard=self._echo_guard,
        )
        self._kernel_vfs = self._vfs_hub.for_kernel()

    def _rebuild_space_and_services_locked(self, core_agg: AggregatedContributes) -> None:
        static_spaces = _extract_contributed_spaces(core_agg)
        self._space_registry = SpaceRegistry(
            self._kernel_vfs,
            self._space_db,
            static_specs=static_spaces,
        )
        self._gitignore = GitignoreMaterializer(self._space_registry, self._kernel_vfs)
        self._package_engine = OfflinePackageEngine(
            host_dir=self._host_dir,
            yscb_root=self._yscb_root,
            config_store=self._config_store,
            snapshot_vault=self._snapshot_vault,
            env_pool=self._env_pool,
            vfs=self._kernel_vfs,
        )
        self._rebind_readonly_matcher()
        self._locale = load_workspace_locale_catalog(
            self._yscb_root,
            self._config_store,
            contributes_aggregator=self._contributes,
            dialect=(None if self._is_daemon_host else self._dialect),
            raw_env_locale=self._effective_raw_env_locale(),
        )
        self._sync_bound_locale_dialect_locked()
        self._svc_factory: Callable[[ModuleId], ModuleRuntimeServices] = build_workspace_module_services_factory(
            self._host_dir,
            self._yscb_root,
            config_store=self._config_store,
            contributes_aggregator=self._contributes,
            vfs_hub=self._vfs_hub,
            locale_getter=self._locale_getter_fn,
        )
        self._kernel_profiler.bind_runtime_profiler(self._svc_factory(CORE_MODULE_ID).profiler)
        self._space_scanner = SpaceScanner(
            self._space_registry,
            self._space_db,
            profiler=self._kernel_profiler,
        )

    def _collect_expired_retired_children_locked(self, now_mono: float) -> list[WorkspaceKernel]:
        expired: list[WorkspaceKernel] = []
        still_retired: list[WorkspaceKernel] = []
        for ret_k in self._retired_child_kernels:
            if ret_k.is_closed or ret_k.is_closing:
                self._child_last_checkout_mono.pop(id(ret_k), None)
                continue
            last_co = self._child_last_checkout_mono.get(id(ret_k), 0.0)
            if ret_k.dispatcher.active_turn_count == 0 and (now_mono - last_co) >= 2.0:
                self._child_last_checkout_mono.pop(id(ret_k), None)
                expired.append(ret_k)
            else:
                still_retired.append(ret_k)
        self._retired_child_kernels = still_retired
        return expired

    def _reap_expired_retired_children(self) -> None:
        with self._reload_lock:
            if self._closed or self._closing or not self._retired_child_kernels:
                return
            expired = self._collect_expired_retired_children_locked(time.monotonic())
        _close_retired_kernels_safely(expired)

    def _resolve_child_dispatcher(self, peer_ws: HostPath) -> RuntimeDispatcher:
        if self._closed or self._closing:
            raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "Parent WorkspaceKernel is closed.")
        if peer_ws == self._yscb_root:
            return self._dispatcher
        active_peer = lookup_active_system_kernel(peer_ws)
        if (
            isinstance(active_peer, WorkspaceKernel)
            and not active_peer.is_managed_child
            and not active_peer.is_daemon_host
            and (
                not active_peer.is_force_cold
                or active_peer.has_extra_modules
                or active_peer.dispatcher.active_turn_count > 0
            )
            and not active_peer.is_closed
            and not active_peer.is_closing
            and active_peer.dispatcher.container_lifecycle.state != ContainerState.STOPPED
        ):
            return active_peer.dispatcher
        peer_host_dir = _discover_peer_workspace_host_dir(peer_ws)
        peer_fp = _compute_peer_workspace_fingerprint(peer_host_dir, peer_ws)
        key = peer_ws.comparison_key
        now_mono = time.monotonic()
        stale_to_close: list[WorkspaceKernel] = []
        fast_child: Optional[WorkspaceKernel] = None
        child_sync_lk: Optional[threading.RLock] = None
        with self._reload_lock:
            if self._closed or self._closing:
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "Parent WorkspaceKernel is closed.")
            parent_dial = None if self._is_daemon_host else self._dialect
            parent_loc_ovr = None if self._is_daemon_host else self._raw_env_locale_override
            stale_to_close.extend(self._collect_expired_retired_children_locked(now_mono))
            cached_child = self._owned_child_kernels.get(key)
            cached_fp = self._owned_child_fingerprints.get(key)
            if cached_child is not None:
                child_stopped = cached_child.dispatcher.container_lifecycle.state == ContainerState.STOPPED
                if (
                    not cached_child.is_closed
                    and not cached_child.is_closing
                    and not child_stopped
                    and cached_child.host_dir == peer_host_dir
                    and cached_fp == peer_fp
                ):
                    self._child_last_checkout_mono[id(cached_child)] = now_mono
                    fast_child = cached_child
            if fast_child is None:
                child_sync_lk = self._owned_child_sync_locks.setdefault(key, threading.RLock())
        _close_retired_kernels_safely(stale_to_close)
        if fast_child is not None:
            if not self._is_daemon_host:
                fast_child.apply_caller_dialect(parent_dial, parent_loc_ovr)
            return fast_child.dispatcher

        with require_non_none(child_sync_lk):
            evicted_to_close: list[WorkspaceKernel] = []
            reload_existing: Optional[WorkspaceKernel] = None
            matched_cur_child: Optional[WorkspaceKernel] = None
            with self._reload_lock:
                if self._closed or self._closing:
                    raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "Parent WorkspaceKernel is closed.")
                parent_dial = None if self._is_daemon_host else self._dialect
                parent_loc_ovr = None if self._is_daemon_host else self._raw_env_locale_override
                cur_child = self._owned_child_kernels.get(key)
                cur_fp = self._owned_child_fingerprints.get(key)
                if cur_child is not None:
                    cur_stopped = cur_child.dispatcher.container_lifecycle.state == ContainerState.STOPPED
                    if (
                        not cur_child.is_closed
                        and not cur_child.is_closing
                        and not cur_stopped
                        and cur_child.host_dir == peer_host_dir
                    ):
                        if cur_fp == peer_fp:
                            self._child_last_checkout_mono[id(cur_child)] = time.monotonic()
                            matched_cur_child = cur_child
                        else:
                            reload_existing = cur_child
                            self._child_last_checkout_mono[id(cur_child)] = time.monotonic()
                    else:
                        self._owned_child_kernels.pop(key, None)
                        self._owned_child_fingerprints.pop(key, None)
                        if not cur_child.is_closed and not cur_child.is_closing:
                            last_co2 = self._child_last_checkout_mono.get(id(cur_child), 0.0)
                            if cur_child.dispatcher.active_turn_count == 0 and (time.monotonic() - last_co2) >= 2.0:
                                self._child_last_checkout_mono.pop(id(cur_child), None)
                                evicted_to_close.append(cur_child)
                            else:
                                unbind_system_kernel(peer_ws, cur_child)
                                self._retired_child_kernels.append(cur_child)
            _close_retired_kernels_safely(evicted_to_close)
            if matched_cur_child is not None:
                if not self._is_daemon_host:
                    matched_cur_child.apply_caller_dialect(parent_dial, parent_loc_ovr)
                return matched_cur_child.dispatcher

            if reload_existing is not None:
                child_closed_during_reload = False
                try:
                    reload_existing.ensure_installed_tasks_indices()
                    reload_existing.reload_workspace_metadata()
                except YscbError as exc:
                    if exc.detail.code == ErrorCode.DAEMON_UNAVAILABLE:
                        child_closed_during_reload = True
                    else:
                        raise
                refreshed_fp = _compute_peer_workspace_fingerprint(peer_host_dir, peer_ws)
                parent_closed_during_reload = False
                reloaded_usable = False
                reload_evicted_to_close: list[WorkspaceKernel] = []
                with self._reload_lock:
                    if self._closed or self._closing:
                        parent_closed_during_reload = True
                    elif (
                        not child_closed_during_reload
                        and not reload_existing.is_closed
                        and not reload_existing.is_closing
                        and reload_existing.dispatcher.container_lifecycle.state != ContainerState.STOPPED
                    ):
                        if self._owned_child_kernels.get(key) is reload_existing:
                            self._owned_child_fingerprints[key] = refreshed_fp
                        self._child_last_checkout_mono[id(reload_existing)] = time.monotonic()
                        reloaded_usable = True
                    else:
                        if self._owned_child_kernels.get(key) is reload_existing:
                            self._owned_child_kernels.pop(key, None)
                            self._owned_child_fingerprints.pop(key, None)
                        if not reload_existing.is_closed and not reload_existing.is_closing:
                            last_co_rel = self._child_last_checkout_mono.get(id(reload_existing), 0.0)
                            if (
                                reload_existing.dispatcher.active_turn_count == 0
                                and (time.monotonic() - last_co_rel) >= 2.0
                            ):
                                self._child_last_checkout_mono.pop(id(reload_existing), None)
                                reload_evicted_to_close.append(reload_existing)
                            else:
                                unbind_system_kernel(peer_ws, reload_existing)
                                if all(k is not reload_existing for k in self._retired_child_kernels):
                                    self._retired_child_kernels.append(reload_existing)
                        else:
                            self._child_last_checkout_mono.pop(id(reload_existing), None)
                _close_retired_kernels_safely(reload_evicted_to_close)
                if parent_closed_during_reload:
                    reload_existing.close()
                    raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "Parent WorkspaceKernel is closed.")
                if reloaded_usable:
                    if not self._is_daemon_host:
                        reload_existing.apply_caller_dialect(parent_dial, parent_loc_ovr)
                    return reload_existing.dispatcher

            built_child = WorkspaceKernel(
                host_dir=peer_host_dir,
                yscb_root=peer_ws,
                is_daemon_host=False,
                force_cold=False,
                extra_modules=(),
                yscb_script_path=self._yscb_script_path,
                dialect=parent_dial,
                is_managed_child=True,
                allow_auto_spawn=False,
                inherit_host_env_locale=((not self._is_daemon_host) and self._inherit_host_env_locale),
                raw_env_locale_override=parent_loc_ovr,
            )
            register_managed_child_dispatcher(built_child.dispatcher)
            built_fp = _compute_peer_workspace_fingerprint(peer_host_dir, peer_ws)
            abort_closed = False
            with self._reload_lock:
                if self._closed or self._closing:
                    abort_closed = True
                else:
                    self._owned_child_kernels[key] = built_child
                    self._owned_child_fingerprints[key] = built_fp
                    self._child_last_checkout_mono[id(built_child)] = time.monotonic()
            if abort_closed:
                built_child.close()
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "Parent WorkspaceKernel is closed.")
            return built_child.dispatcher

    def _resolve_module_services(self, module_id: ModuleId) -> ModuleRuntimeServices:
        with self._reload_lock:
            factory = self._svc_factory
        return factory(module_id)

    def _current_locale(self) -> LocaleCatalog:
        return self._locale

    def resolve_module_config_type(self, module_id: ModuleId) -> Optional[type[object]]:
        return self._extra_config_types.get(module_id)

    def _effective_raw_env_locale(self) -> Optional[str]:
        if self._is_daemon_host or not self._inherit_host_env_locale:
            return self._raw_env_locale_override if self._raw_env_locale_override else None
        if self._raw_env_locale_override is not None:
            return self._raw_env_locale_override if self._raw_env_locale_override else None
        return read_public_env_value("YSCB_LOCALE")

    def _sync_bound_locale_dialect_locked(self) -> None:
        if self._closed or self._closing:
            return
        eff_inherit = (not self._is_daemon_host) and self._inherit_host_env_locale
        bind_locale_getter_dialect(
            self._locale_getter_fn,
            self._yscb_root,
            self._dialect,
            is_daemon_host=self._is_daemon_host,
            register_cold_root=((not self._is_daemon_host) and (not self._is_managed_child) and self._inherit_host_env_locale),
            inherit_host_env_locale=eff_inherit,
            raw_env_locale_override=self._raw_env_locale_override,
        )

    def apply_caller_dialect(self, dialect: Optional[str], raw_env_locale: Optional[str] = None) -> None:
        if self._is_daemon_host:
            return
        clean = dialect.strip() if isinstance(dialect, str) and dialect.strip() else None
        loc_ovr = raw_env_locale.strip() if isinstance(raw_env_locale, str) else None
        with self._reload_lock:
            if self._closed or self._closing:
                return
            if clean == self._dialect and loc_ovr == self._raw_env_locale_override:
                return
            self._dialect = clean
            self._raw_env_locale_override = loc_ovr
            self._locale = load_workspace_locale_catalog(
                self._yscb_root,
                self._config_store,
                contributes_aggregator=self._contributes,
                dialect=self._dialect,
                raw_env_locale=self._effective_raw_env_locale(),
            )
            self._sync_bound_locale_dialect_locked()
            self._svc_factory = build_workspace_module_services_factory(
                self._host_dir,
                self._yscb_root,
                config_store=self._config_store,
                contributes_aggregator=self._contributes,
                vfs_hub=self._vfs_hub,
                locale_getter=self._locale_getter_fn,
            )
            self._kernel_profiler.bind_runtime_profiler(self._svc_factory(CORE_MODULE_ID).profiler)

    def consume_post_close_exit_code(self) -> Optional[int]:
        rc = self._post_close_exit_code
        self._post_close_exit_code = None
        return rc

    def _evict_cached_tier0_output_pkgs_locked(self) -> None:
        self._tier0_output_cache.clear()
        while self._tier0_loaded_pkgs:
            pkg = self._tier0_loaded_pkgs.pop()
            ProtectedModuleLoader.cleanup_package(pkg)

    def is_reserved_control_plane_path(
        self,
        hp: HostPath,
        *,
        owner: Optional[str] = None,
        allow_any_module_storage: bool = False,
    ) -> bool:
        return is_control_plane_reserved_path(
            hp,
            yscb_root=self._yscb_root,
            host_dir=self._host_dir,
            project_root=self._project_root,
            project_root_disabled=self._project_root_disabled,
            owner=owner,
            allow_any_module_storage=allow_any_module_storage,
        )

    def _rebind_readonly_matcher(self) -> None:
        reg = self._space_registry

        def _matches_readonly_space(hp: HostPath) -> bool:
            for spec in reg.list_spaces():
                if spec.space_id.owner == "":
                    continue
                if spec.space_id.name == "readonly":
                    if spec.space_id.owner != "core" and self.is_reserved_control_plane_path(
                        hp,
                        owner=spec.space_id.owner,
                    ):
                        continue
                    try:
                        if reg.match_path(spec.space_id, hp).matched:
                            return True
                    except YscbError:
                        continue
            return False

        self._readonly_policy.update_matcher(_matches_readonly_space)

    def _default_daemon_restart_argv(self) -> Optional[tuple[str, ...]]:
        if self._resolved_script_path is None:
            return None
        return (
            sys.executable,
            "-X",
            "utf8",
            str(self._resolved_script_path),
            f"--host-dir={self._host_dir}",
            "daemon",
            "start",
            "--supervisor",
        )

    def _build_daemon_spawner(self) -> SingleFlightDaemonSpawner:
        script_hp = self._resolved_script_path
        sandbox = is_public_env_truthy(TEST_SANDBOX_ENV_KEY) or script_hp is None
        host_flag = f"--host-dir={self._host_dir}"

        def _build_argv(_ws: HostPath) -> Sequence[str]:
            if script_hp is None:
                return (sys.executable, "-X", "utf8", "-c", "pass")
            return (sys.executable, "-X", "utf8", str(script_hp), host_flag, "daemon", "start", "--supervisor")

        return SingleFlightDaemonSpawner(
            self._cache_dir,
            _build_argv,
            lease_cooldown_sec=(5.0 if IS_WINDOWS else 1.5),
            sandbox_restricted=sandbox,
        )

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def is_closing(self) -> bool:
        return self._closing or self._closed

    @property
    def is_managed_child(self) -> bool:
        return self._is_managed_child

    @property
    def is_daemon_host(self) -> bool:
        return self._is_daemon_host

    @property
    def is_force_cold(self) -> bool:
        return self._force_cold

    @property
    def has_extra_modules(self) -> bool:
        return self._has_extra_modules

    @property
    def host_dir(self) -> HostPath:
        return self._host_dir

    @property
    def yscb_root(self) -> HostPath:
        return self._yscb_root

    @property
    def cache_dir(self) -> HostPath:
        return self._cache_dir

    @property
    def config_store(self) -> ConfigStore:
        return self._config_store

    @property
    def snapshot_vault(self) -> SnapshotVault:
        return self._snapshot_vault

    @property
    def contributes_aggregator(self) -> ContributesAggregator:
        return self._contributes

    @property
    def mount_table(self) -> UriMountTable:
        with self._reload_lock:
            return self._mount_table

    @property
    def readonly_policy(self) -> ReadonlyPolicy:
        return self._readonly_policy

    @property
    def echo_guard(self) -> VfsEchoGuard:
        return self._echo_guard

    @property
    def kernel_vfs(self) -> KernelVfs:
        with self._reload_lock:
            return self._kernel_vfs

    @property
    def space_registry(self) -> SpaceRegistry:
        with self._reload_lock:
            return self._space_registry

    @property
    def space_scanner(self) -> SpaceScanner:
        with self._reload_lock:
            return self._space_scanner

    @property
    def gitignore_materializer(self) -> GitignoreMaterializer:
        with self._reload_lock:
            return self._gitignore

    @property
    def env_pool(self) -> ImmutableVenvPool:
        return self._env_pool

    @property
    def env_probe(self) -> EnvHealthProbe:
        return self._env_probe

    @property
    def env_gc(self) -> EnvGarbageCollector:
        return self._env_gc

    @property
    def package_engine(self) -> OfflinePackageEngine:
        with self._reload_lock:
            return self._package_engine

    @property
    def module_provider(self) -> ModuleProviderAdapter:
        return self._module_provider

    @property
    def dispatcher(self) -> RuntimeDispatcher:
        return self._dispatcher

    def resolve_task_output_type(self, task_id: TaskId) -> Optional[object]:
        return self._output_types.get(task_id)

    def _resolve_tier0_disk_output_type(self, desc: ModuleDescriptor, task_id: TaskId) -> Optional[object]:
        fp = f"{desc.module_dir.comparison_key}:{desc.entry_file}:{_compute_dir_py_fingerprint(desc.module_dir)}"
        with self._reload_lock:
            if self._closed or self._closing:
                return None
            cached = self._tier0_output_cache.get(desc.module_id)
            if cached is not None and cached.fingerprint == fp:
                return cached.output_types.get(task_id)
            loader = ProtectedModuleLoader(self._yscb_root)
            loaded_pkg_key: Optional[str] = None
            try:
                with guard_standard_streams():
                    art = loader.load_module_artifact(desc)
                    loaded_pkg_key = art.package_key
                    mapping: dict[TaskId, object] = {
                        bt.task_id: bt.metadata.output_type
                        for bt in art.instance.tasks()
                    }
            except (Exception, SystemExit):
                if loaded_pkg_key is not None:
                    ProtectedModuleLoader.cleanup_package(loaded_pkg_key)
                return None
            except BaseException:
                if loaded_pkg_key is not None:
                    ProtectedModuleLoader.cleanup_package(loaded_pkg_key)
                raise
            if cached is not None:
                if cached.package_key in self._tier0_loaded_pkgs:
                    self._tier0_loaded_pkgs.remove(cached.package_key)
                ProtectedModuleLoader.cleanup_package(cached.package_key)
            self._tier0_loaded_pkgs.append(loaded_pkg_key)
            self._tier0_output_cache[desc.module_id] = _Tier0OutputCacheEntry(
                fingerprint=fp,
                package_key=loaded_pkg_key,
                output_types=mapping,
            )
            return mapping.get(task_id)

    def _resolve_tier1_disk_presentation(
        self,
        desc: ModuleDescriptor,
        task_id: TaskId,
        raw_value: JsonValue,
        *,
        render_human: bool,
    ) -> tuple[Optional[str], Optional[int]]:
        if desc.venv_python is None or not os.path.isfile(str(desc.venv_python)):
            return (None, None)
        sub_env = build_isolated_python_env()
        sub_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[3])
        sub_env["PYTHONDONTWRITEBYTECODE"] = "1"
        sub_env["PYTHONUTF8"] = "1"
        sub_env["PYTHONIOENCODING"] = "utf-8"
        slim_desc = replace(desc, declared_tasks=())
        desc_json = json.dumps(DataclassCodec.encode_object(slim_desc), separators=(",", ":"), ensure_ascii=False)
        win_flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
        try:
            cp = subprocess.run(
                [
                    str(desc.venv_python),
                    "-X",
                    "utf8",
                    "-B",
                    "-c",
                    _TIER1_FORMAT_SNIPPET,
                    str(self._yscb_root),
                    desc_json,
                    task_id.value,
                    "1" if render_human else "0",
                ],
                cwd=str(self._yscb_root),
                env=sub_env,
                input=json.dumps(raw_value, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10.0,
                check=False,
                creationflags=win_flags,
            )
        except (OSError, subprocess.SubprocessError):
            return (None, None)
        if cp.returncode != 0 or not cp.stdout.strip():
            return (None, None)
        try:
            doc = strict_parse_json_object(cp.stdout.strip())
        except ValueError:
            return (None, None)
        if doc.get("ok") is not True:
            return (None, None)
        raw_txt = doc.get("text")
        raw_code = doc.get("exit_code")
        txt = raw_txt if (render_human and type(raw_txt) is str) else None
        code = int(raw_code) if (type(raw_code) is int) else 0
        return (txt, code)

    def resolve_task_presentation(
        self,
        task_entry: IndexedTaskEntry,
        raw_value: JsonValue,
        *,
        render_human: bool,
    ) -> tuple[Optional[str], Optional[int]]:
        with self._reload_lock:
            if self._closed or self._closing:
                return (None, None)
        mem_tp = self._output_types.get(task_entry.task_id)
        if mem_tp is not None:
            if not render_human and not task_entry.custom_exit_code:
                return (None, 0)
            try:
                with guard_standard_streams():
                    typed_val = DataclassCodec.decode(mem_tp, raw_value)
                    if not render_human:
                        eff_code_only = (
                            require_pure_int(
                                typed_val.exit_code(),
                                "ExitCodeProvider.exit_code()",
                                min_val=None,
                                max_val=None,
                            )
                            if isinstance(typed_val, ExitCodeProvider)
                            else 0
                        )
                        return (None, eff_code_only)
                    txt, code = format_output(typed_val)
                eff_code = int(code) if isinstance(typed_val, ExitCodeProvider) else 0
                return (txt, eff_code)
            except (TypeError, ValueError, YscbError):
                return (None, None)

        needs_custom = (render_human and task_entry.custom_render) or task_entry.custom_exit_code
        if not needs_custom:
            return (None, None)

        desc = self._module_provider.get_module(task_entry.task_id.module_id)
        if desc is None or desc.module_id == CORE_MODULE_ID:
            return (None, None)
        if desc.venv_python is None:
            disk_tp = self._resolve_tier0_disk_output_type(desc, task_entry.task_id)
            if disk_tp is None:
                return (None, None)
            try:
                with guard_standard_streams():
                    typed_val = DataclassCodec.decode(disk_tp, raw_value)
                    if not render_human:
                        eff_disk_code = (
                            require_pure_int(
                                typed_val.exit_code(),
                                "ExitCodeProvider.exit_code()",
                                min_val=None,
                                max_val=None,
                            )
                            if isinstance(typed_val, ExitCodeProvider)
                            else 0
                        )
                        return (None, eff_disk_code)
                    txt, code = format_output(typed_val)
                eff_code = int(code) if isinstance(typed_val, ExitCodeProvider) else 0
                return (txt, eff_code)
            except (TypeError, ValueError, YscbError):
                return (None, None)

        return self._resolve_tier1_disk_presentation(
            desc,
            task_entry.task_id,
            raw_value,
            render_human=render_human,
        )

    def list_route_specs(self) -> Sequence[TaskRouteSpec]:
        return self._dispatcher.list_route_specs()

    def _persist_core_disk_index_if_present(self) -> None:
        core_dir = try_resolve_contained_subpath(self._yscb_root, MODULES_DIRNAME, CORE_MODULE_ID.value)
        if core_dir is None or not os.path.isdir(str(core_dir)) or is_symlink_or_reparse(str(core_dir)):
            return
        idx_hp = try_resolve_contained_subpath(core_dir, "tasks.index.json")
        running_disk_core = core_dir.path in Path(__file__).resolve().parents
        expected_doc = compile_tasks_index(CoreSystemModule).to_json_dict()
        if _is_valid_disk_tasks_index(idx_hp, CORE_MODULE_ID):
            if not running_disk_core or idx_hp is None:
                return
            try:
                raw_existing = read_nofollow_regular_bytes(str(idx_hp), max_bytes=MAX_JSON_FILE_BYTES)
                if raw_existing is not None and strict_parse_json_object(raw_existing.decode("utf-8")) == expected_doc:
                    return
            except (OSError, UnicodeDecodeError, ValueError):
                pass
        try:
            dest = resolve_contained_subpath(core_dir, "tasks.index.json")
            atomic_write_json(dest, expected_doc)
        except (OSError, ValueError, YscbError):
            pass

    def _compile_tier1_tasks_index(
        self,
        venv_py: HostPath,
        desc: ModuleDescriptor,
        mf_description: str,
    ) -> Optional[ModuleTasksIndex]:
        sub_env = build_isolated_python_env()
        sub_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[3])
        sub_env["PYTHONDONTWRITEBYTECODE"] = "1"
        sub_env["PYTHONUTF8"] = "1"
        sub_env["PYTHONIOENCODING"] = "utf-8"
        desc_json = json.dumps(DataclassCodec.encode_object(desc), separators=(",", ":"), ensure_ascii=False)
        win_flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
        try:
            cp = subprocess.run(
                [
                    str(venv_py),
                    "-X",
                    "utf8",
                    "-B",
                    "-c",
                    _TIER1_COMPILE_INDEX_SNIPPET,
                    str(self._yscb_root),
                    desc_json,
                    mf_description,
                ],
                cwd=str(self._yscb_root),
                env=sub_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15.0,
                check=False,
                creationflags=win_flags,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if cp.returncode != 0 or not cp.stdout.strip():
            return None
        try:
            doc = strict_parse_json_object(cp.stdout.strip())
            if doc.get("ok") is not True or not isinstance(doc.get("index"), Mapping):
                return None
            return ModuleTasksIndex.from_json_dict(doc["index"])
        except (ValueError, YscbError):
            return None

    def ensure_installed_tasks_indices(self, module_ids: Optional[Iterable[ModuleId]] = None) -> None:
        with self._reload_lock:
            if self._closed or self._closing:
                return
        manifests = discover_installed_manifests_map(self._yscb_root)
        group_specs = ImmutableVenvPool.resolve_group_specs(tuple(manifests.values()))
        targets = (
            tuple(dict.fromkeys(module_ids))
            if module_ids is not None
            else tuple(sorted(manifests.keys(), key=lambda m: m.value))
        )
        for mod_id in targets:
            with self._reload_lock:
                if self._closed or self._closing:
                    return
            if mod_id == CORE_MODULE_ID:
                continue
            mf = manifests.get(mod_id)
            if mf is None:
                continue
            mod_dir = try_resolve_contained_subpath(self._yscb_root, MODULES_DIRNAME, mod_id.value)
            if mod_dir is None or not os.path.isdir(str(mod_dir)) or is_symlink_or_reparse(str(mod_dir)):
                continue
            idx_hp = try_resolve_contained_subpath(mod_dir, "tasks.index.json")
            if _is_valid_disk_tasks_index(idx_hp, mod_id):
                continue

            compiled_idx: Optional[ModuleTasksIndex] = None
            if not mf.is_tier1:
                probe_desc = ModuleDescriptor(
                    module_id=mod_id,
                    module_dir=mod_dir,
                    entry_file=mf.entry,
                    eager_warmup=mf.eager_warmup,
                )
                loader = ProtectedModuleLoader(self._yscb_root)
                try:
                    with guard_standard_streams():
                        art = loader.load_module_artifact(probe_desc)
                except (Exception, SystemExit):
                    art = None
                if art is not None:
                    try:
                        with guard_standard_streams():
                            raw_idx = compile_tasks_index(art.instance)
                        if not raw_idx.description and mf.description:
                            raw_idx = ModuleTasksIndex(
                                module_id=raw_idx.module_id,
                                module_aliases=raw_idx.module_aliases,
                                description=mf.description,
                                tasks=raw_idx.tasks,
                            )
                        compiled_idx = raw_idx
                    except (Exception, SystemExit):
                        compiled_idx = None
                    finally:
                        ProtectedModuleLoader.cleanup_package(art.package_key)
            else:
                env_spec = group_specs.get(mod_id)
                venv_py = self._env_pool.get_python_executable(env_spec) if env_spec is not None else None
                if venv_py is not None:
                    probe_desc = ModuleDescriptor(
                        module_id=mod_id,
                        module_dir=mod_dir,
                        entry_file=mf.entry,
                        venv_group=mf.venv_group,
                        venv_python=venv_py,
                        eager_warmup=mf.eager_warmup,
                    )
                    compiled_idx = self._compile_tier1_tasks_index(venv_py, probe_desc, mf.description)

            if compiled_idx is not None:
                try:
                    dest_idx = resolve_contained_subpath(mod_dir, "tasks.index.json")
                    atomic_write_json(dest_idx, compiled_idx.to_json_dict())
                except (OSError, ValueError, YscbError):
                    pass

    def discover_installed_manifests(self) -> Mapping[ModuleId, ModuleManifest]:
        return MappingProxyType(discover_installed_manifests_map(self._yscb_root))

    def collect_active_env_specs(self) -> tuple[EnvSpec, ...]:
        manifests = discover_installed_manifests_map(self._yscb_root)
        group_specs = ImmutableVenvPool.resolve_group_specs(tuple(manifests.values()))
        specs: list[EnvSpec] = []
        seen: set[str] = set()
        for mod_id in sorted(group_specs.keys(), key=lambda m: m.value):
            spec = group_specs[mod_id]
            if spec.env_hash.value not in seen:
                seen.add(spec.env_hash.value)
                specs.append(spec)
        return tuple(specs)

    def _compute_metadata_state_fingerprint_locked(self) -> str:
        evicted_part = ",".join(sorted(m.value for m in self._module_provider_opt.pending_evicted)) if self._module_provider_opt is not None else ""
        return f"{self._config_store.fingerprint()}|{_compute_peer_workspace_fingerprint(self._host_dir, self._yscb_root)}|{evicted_part}"

    def _compute_tier0_code_fingerprint(self) -> str:
        h = hashlib.sha256()
        manifests = discover_installed_manifests_map(self._yscb_root)
        for mod_id in sorted(manifests.keys(), key=lambda m: m.value):
            if mod_id == CORE_MODULE_ID or manifests[mod_id].is_tier1:
                continue
            mod_dir = try_resolve_contained_subpath(self._yscb_root, MODULES_DIRNAME, mod_id.value)
            if mod_dir is not None and os.path.isdir(str(mod_dir)):
                h.update(f"{mod_id.value}:{_compute_dir_py_fingerprint(mod_dir)}\n".encode("utf-8"))
        return h.hexdigest()

    def _refresh_kernel_components_locked(self, *, clear_tier0_output_cache: bool) -> None:
        if clear_tier0_output_cache:
            self._evict_cached_tier0_output_pkgs_locked()
        if self._module_provider_opt is not None:
            self._module_provider_opt.invalidate_cache()
        self._config_store.reload()
        manifests_map = discover_installed_manifests_map(self._yscb_root)
        self._contributes.reload(
            manifests=tuple(manifests_map.values()),
            live_specs=self._live_specs,
        )
        core_agg = _safe_aggregate_core(self._contributes)
        self._rebuild_vfs_from_core_agg(core_agg)
        self._rebuild_space_and_services_locked(core_agg)
        self._applied_metadata_fp = self._compute_metadata_state_fingerprint_locked()
        self._applied_tier0_code_fp = self._compute_tier0_code_fingerprint()

    def _is_current_thread_refreshing_locked(self) -> bool:
        return self._refresh_depth_by_tid.get(threading.get_ident(), 0) > 0

    @contextmanager
    def _kernel_refresh_guard(self) -> Iterator[None]:
        tid_num = threading.get_ident()
        with self._reload_lock:
            self._refresh_depth_by_tid[tid_num] = self._refresh_depth_by_tid.get(tid_num, 0) + 1
        try:
            yield
        finally:
            with self._reload_lock:
                rem = self._refresh_depth_by_tid.get(tid_num, 1) - 1
                if rem <= 0:
                    self._refresh_depth_by_tid.pop(tid_num, None)
                else:
                    self._refresh_depth_by_tid[tid_num] = rem

    @contextmanager
    def installer_transaction_lock(self, cancel_token: Optional[CancellationToken] = None) -> Iterator[None]:
        with self._installer_op_lock:
            if self._installer_lock_depth > 0:
                self._installer_lock_depth += 1
                try:
                    yield
                finally:
                    self._installer_lock_depth -= 1
                return
            lock_hp = resolve_contained_subpath(self._cache_dir, LOCKS_SUBDIR, "tx_orchestrator.lock")
            os.makedirs(str(lock_hp.path.parent), exist_ok=True)
            flock = FileLock(lock_hp, allow_transitions=False)
            flock.acquire(
                shared=False,
                blocking=True,
                timeout_sec=120.0,
                cancel_token=cancel_token,
            )
            self._installer_lock_depth = 1
            try:
                yield
            finally:
                self._installer_lock_depth = 0
                flock.release()

    def _on_provider_reloaded(self) -> None:
        with self._reload_lock:
            if self._closed or self._closing or self._is_current_thread_refreshing_locked():
                return
        with self._kernel_refresh_guard():
            with self._reload_lock:
                if self._closed or self._closing:
                    return
                cur_t0_fp = self._compute_tier0_code_fingerprint()
                if cur_t0_fp != self._applied_tier0_code_fp:
                    self._evict_cached_tier0_output_pkgs_locked()
                    self._applied_tier0_code_fp = cur_t0_fp
                if self._compute_metadata_state_fingerprint_locked() != self._applied_metadata_fp:
                    self._refresh_kernel_components_locked(clear_tier0_output_cache=False)

    def is_daemon_quiesced(self) -> bool:
        return bool(self._is_daemon_host and self._dispatcher.reload_gate.is_globally_quiesced())

    def on_config_view_reload_requested(self) -> None:
        if self.is_daemon_quiesced():
            with self._reload_lock:
                self._deferred_quiesce_space_sync = True
            return
        with self._reload_lock:
            if self._closed or self._closing:
                return
            if self._is_current_thread_refreshing_locked():
                self._config_store.reload()
                return
        with self._kernel_refresh_guard():
            need_sync = False
            with self._reload_lock:
                if self._closed or self._closing:
                    return
                if self.is_daemon_quiesced():
                    self._deferred_quiesce_space_sync = True
                    return
                self._config_store.reload()
                need_sync = self._deferred_quiesce_space_sync
                self._deferred_quiesce_space_sync = False
                if self._compute_metadata_state_fingerprint_locked() != self._applied_metadata_fp:
                    self._refresh_kernel_components_locked(clear_tier0_output_cache=False)
                    need_sync = True
            if need_sync and not self._closed and not self._closing:
                _ = self.sync_gitignore_and_readonly()
            self._reap_expired_retired_children()

    def has_running_daemon(self) -> bool:
        with self._reload_lock:
            refs = list(self._built_daemons)
        for ref in refs:
            daemon_obj = ref()
            if daemon_obj is not None and daemon_obj.snapshot_status().state not in (
                DaemonRunState.BOOTING,
                DaemonRunState.STOPPED,
            ):
                return True
        return False

    def refresh_dynamic_spaces_only(self) -> tuple[str, ...]:
        with self._kernel_refresh_guard():
            with self._reload_lock:
                if self._closed:
                    raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "WorkspaceKernel is closed.")
                if self._closing:
                    return ()
                before_specs = {
                    str(s.space_id): s for s in self._space_registry.list_spaces() if s.space_id.owner != ""
                }
                core_agg = _safe_aggregate_core(self._contributes)
                static_spaces = _extract_contributed_spaces(core_agg)
                self._space_registry = SpaceRegistry(
                    self._kernel_vfs,
                    self._space_db,
                    static_specs=static_spaces,
                )
                self._space_scanner = SpaceScanner(
                    self._space_registry,
                    self._space_db,
                    profiler=self._kernel_profiler,
                )
                self._gitignore = GitignoreMaterializer(self._space_registry, self._kernel_vfs)
                self._rebind_readonly_matcher()
                after_specs = {
                    str(s.space_id): s for s in self._space_registry.list_spaces() if s.space_id.owner != ""
                }
                diff_ids = tuple(
                    sorted(
                        sid
                        for sid in (set(before_specs.keys()) | set(after_specs.keys()))
                        if before_specs.get(sid) != after_specs.get(sid)
                    )
                )
            _ = self.sync_gitignore_and_readonly()
            return diff_ids

    def config_and_contributes_fingerprint(self) -> str:
        return _compute_config_and_contributes_fingerprint(
            self._host_dir,
            self._yscb_root,
            self._config_store.fingerprint(),
        )

    def reload_config_only(self, changed_paths: Sequence[str] = ()) -> bool:
        with self._kernel_refresh_guard():
            with self._reload_lock:
                if self._closed:
                    raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "WorkspaceKernel is closed.")
                if self._closing:
                    return False
                self._refresh_kernel_components_locked(clear_tier0_output_cache=False)
                cur_cfg_fp = self.config_and_contributes_fingerprint()
                meta_changed = cur_cfg_fp != self._last_notified_cfg_fp
                self._last_notified_cfg_fp = cur_cfg_fp
            disp_changed = self._dispatcher.reload_config_and_contributes(
                changed_paths=tuple(str(p) for p in changed_paths),
                emit_event=False,
            )
            self._reap_expired_retired_children()
            return bool(disp_changed or meta_changed)

    def evict_local_modules_before_remove(self, modules: Sequence[ModuleId]) -> None:
        with self._reload_lock:
            if self._closed or self._closing:
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "WorkspaceKernel is closed.")
        targets = frozenset(m for m in modules if m != CORE_MODULE_ID)
        if not targets:
            return
        _ = self._module_provider.list_modules()
        self._module_provider.set_pending_evicted(targets)
        try:
            self._dispatcher.reload_affected_modules(targets)
        finally:
            self._module_provider.set_pending_evicted(frozenset())

    def reload_workspace_metadata(self) -> None:
        with self._kernel_refresh_guard():
            with self._reload_lock:
                if self._closed or self._closing:
                    raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "WorkspaceKernel is closed.")
                self._refresh_kernel_components_locked(clear_tier0_output_cache=True)
            self._dispatcher.reload_affected_modules(frozenset())
            self._reap_expired_retired_children()

    def schedule_post_close_daemon_sync(
        self,
        *,
        quiesced: bool,
        quiesce_epoch: Optional[int],
        core_handoff: bool = False,
    ) -> None:
        with self._reload_lock:
            prev = self._pending_daemon_sync
            if prev is not None:
                eff_quiesced = prev.quiesced or quiesced
                eff_epoch = (
                    quiesce_epoch
                    if (quiesced and quiesce_epoch is not None)
                    else prev.quiesce_epoch
                )
                self._pending_daemon_sync = _PendingDaemonSync(
                    quiesced=eff_quiesced,
                    quiesce_epoch=eff_epoch,
                    core_handoff=(prev.core_handoff or core_handoff),
                )
            else:
                self._pending_daemon_sync = _PendingDaemonSync(
                    quiesced=quiesced,
                    quiesce_epoch=quiesce_epoch,
                    core_handoff=core_handoff,
                )

    def _deliver_daemon_sync_pair(self, pending_sync: _PendingDaemonSync) -> None:
        if probe_daemon_endpoint(self._cache_dir, self._yscb_root) is None:
            return
        if pending_sync.core_handoff:
            stop_payload = DataclassCodec.encode_object(DaemonStopControl(force=False, core_handoff=True))
            stop_rep = query_daemon_control(
                self._cache_dir,
                self._yscb_root,
                FrameKind.CONTROL_STOP,
                stop_payload,
                timeout_ms=10000,
            )
            if (stop_rep is None or stop_rep.get("ok") is not True) and pending_sync.quiesced:
                force_payload = DataclassCodec.encode_object(DaemonStopControl(force=True, core_handoff=True))
                _ = query_daemon_control(
                    self._cache_dir,
                    self._yscb_root,
                    FrameKind.CONTROL_STOP,
                    force_payload,
                    timeout_ms=5000,
                )
            return
        if pending_sync.quiesced:
            res_payload = DataclassCodec.encode_object(DaemonResumeControl(expected_epoch=pending_sync.quiesce_epoch))
            _ = query_daemon_control(
                self._cache_dir,
                self._yscb_root,
                FrameKind.CONTROL_RESUME,
                res_payload,
                timeout_ms=5000,
            )
        else:
            rel_payload = DataclassCodec.encode_object(DaemonReloadControl(modules=()))
            _ = query_daemon_control(
                self._cache_dir,
                self._yscb_root,
                FrameKind.CONTROL_RELOAD,
                rel_payload,
                timeout_ms=5000,
            )

    def flush_pending_daemon_sync(self) -> None:
        with self._reload_lock:
            pending_sync = self._pending_daemon_sync
            self._pending_daemon_sync = None
            notify_space = self._pending_dynamic_space_notify
            self._pending_dynamic_space_notify = False
        if pending_sync is not None:
            self._deliver_daemon_sync_pair(pending_sync)
        if notify_space:
            self._notify_dynamic_space_mutation()

    def rebuild_tasks_index_cache(self) -> None:
        self._persist_core_disk_index_if_present()
        core_idx = compile_tasks_index(CoreSystemModule)
        cache = WorkspaceTasksIndexCache(self._yscb_root, builtin_indices=(core_idx,))
        _ = cache.load_all(force_rebuild=True)

    def _notify_dynamic_space_mutation(self) -> None:
        if self._is_daemon_host or self.has_running_daemon():
            return
        if probe_daemon_endpoint(self._cache_dir, self._yscb_root) is None:
            return
        notify_failed = False
        notify_timeout_ms = 5000 if IS_WINDOWS else 2000
        try:
            wire_payload = DataclassCodec.encode_envelope(
                _SpaceNotifyRpcEnvelope(
                    task_id=TaskId("core.space.on_dynamic_mutated"),
                    raw_input={},
                    workspace_root=self._yscb_root,
                    caller_cwd=self._host_dir,
                    timeout_ms=notify_timeout_ms,
                )
            )
            rpc_out = call_ephemeral_daemon_rpc(
                (self._cache_dir, self._yscb_root),
                wire_payload,
                cancel_token=CancellationToken(),
                timeout_ms=notify_timeout_ms + 250,
            )
            if rpc_out.transport_lost or rpc_out.error_code is not None or rpc_out.result_payload is None:
                notify_failed = rpc_out.error_code in (
                    ErrorCode.TASK_TIMEOUT,
                    ErrorCode.DAEMON_UNAVAILABLE,
                    ErrorCode.TRANSPORT_LOST,
                ) or (probe_daemon_endpoint(self._cache_dir, self._yscb_root) is not None)
            else:
                reply = DataclassCodec.decode_envelope(DaemonRpcInvokeReply, rpc_out.result_payload)
                if not reply.ok:
                    err_code = reply.error.code if reply.error is not None else None
                    notify_failed = err_code in (
                        ErrorCode.TASK_TIMEOUT,
                        ErrorCode.DAEMON_UNAVAILABLE,
                        ErrorCode.TRANSPORT_LOST,
                        ErrorCode.TASK_CANCELLED,
                        ErrorCode.TASK_PREEMPTED,
                    ) or (probe_daemon_endpoint(self._cache_dir, self._yscb_root) is not None)
        except (OSError, ValueError, YscbError):
            notify_failed = probe_daemon_endpoint(self._cache_dir, self._yscb_root) is not None
        if notify_failed:
            with self._reload_lock:
                if not self._closed:
                    self._pending_dynamic_space_notify = True

    def _schedule_or_notify_dynamic_space_mutation(self) -> None:
        if self._is_daemon_host or self.has_running_daemon() or resolve_active_call_tree_id() is None:
            self._notify_dynamic_space_mutation()
            return
        with self._reload_lock:
            if not self._closed:
                self._pending_dynamic_space_notify = True

    def set_dynamic_space(self, owner: ModuleId, name: str, spec: SpaceSpec) -> bool:
        with self.space_sync_guard():
            with self._reload_lock:
                if self._closed or (self._closing and self._dispatcher.active_turn_count == 0):
                    raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "WorkspaceKernel is closed.")
                changed = self._space_registry.set_dynamic_space(owner, name, spec)
            if changed:
                _ = self.sync_gitignore_and_readonly()
        if changed:
            self._schedule_or_notify_dynamic_space_mutation()
        return changed

    def clear_dynamic_spaces(self, owner: ModuleId, name: Optional[str] = None, *, sync: bool = True) -> int:
        with self.space_sync_guard():
            with self._reload_lock:
                if self._closed or (self._closing and self._dispatcher.active_turn_count == 0):
                    raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "WorkspaceKernel is closed.")
                if name is not None:
                    removed = 1 if self._space_registry.remove_dynamic_space(owner, name) else 0
                else:
                    removed = self._space_registry.clear_dynamic_spaces(owner)
            if removed > 0 and sync:
                _ = self.sync_gitignore_and_readonly()
        if removed > 0 and sync:
            self._schedule_or_notify_dynamic_space_mutation()
        return removed

    @contextmanager
    def _space_sync_file_lock(self) -> Iterator[None]:
        with self._space_sync_op_lock:
            if self._space_sync_lock_depth > 0:
                self._space_sync_lock_depth += 1
                try:
                    yield
                finally:
                    self._space_sync_lock_depth -= 1
                return
            lock_hp = resolve_contained_subpath(self._cache_dir, LOCKS_SUBDIR, "space_sync.lock")
            os.makedirs(str(lock_hp.path.parent), exist_ok=True)
            flock = FileLock(lock_hp, allow_transitions=False)
            flock.acquire(shared=False, blocking=True, timeout_sec=30.0)
            self._space_sync_lock_depth = 1
            try:
                yield
            finally:
                self._space_sync_lock_depth = 0
                flock.release()

    @contextmanager
    def space_sync_guard(self) -> Iterator[None]:
        with self._space_sync_file_lock():
            yield

    def sync_gitignore_and_readonly(self) -> JsonObject:
        with self.space_sync_guard():
            with self._reload_lock:
                if self._closed:
                    raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "WorkspaceKernel is closed.")
                gi_mat = self._gitignore
                sp_reg = self._space_registry
                cur_mt = self._mount_table
                retired_mts = tuple(self._retired_mount_tables)
                active_roots = self._active_custom_mount_roots
                retired_roots = tuple(self._retired_custom_mount_roots)
            gi_modified = False
            try:
                gi_res = gi_mat.sync()
                gi_modified = gi_res.changed
            except YscbError:
                gi_modified = False

            ro_files: list[HostPath] = []
            seen_ro_keys: set[str] = set()
            core_ro_keys: set[str] = set()
            for spec in sp_reg.list_spaces():
                if spec.space_id.owner == "":
                    continue
                if spec.space_id.name == "readonly":
                    is_core_ro = spec.space_id.owner == "core"
                    try:
                        entries = list(sp_reg.iter_files(spec.space_id))
                    except YscbError:
                        continue
                    for entry in entries:
                        if not is_core_ro and self.is_reserved_control_plane_path(
                            entry.abs_path,
                            owner=spec.space_id.owner,
                        ):
                            continue
                        ck = entry.abs_path.comparison_key
                        if is_core_ro:
                            core_ro_keys.add(ck)
                        if ck not in seen_ro_keys:
                            seen_ro_keys.add(ck)
                            ro_files.append(entry.abs_path)

            ro_state_hp = resolve_contained_subpath(
                self._yscb_root,
                ".storage.local",
                "core",
                "space",
                "readonly_managed.json",
            )
            persisted_hps: list[HostPath] = []
            persisted_core_keys: set[str] = set()
            persisted_roots: list[HostPath] = []
            try:
                raw_st_bytes = read_nofollow_regular_bytes(str(ro_state_hp), max_bytes=MAX_JSON_FILE_BYTES)
            except OSError:
                raw_st_bytes = None
            if raw_st_bytes is not None:
                try:
                    st_doc = strict_parse_json_object(raw_st_bytes.decode("utf-8"))
                    raw_mp = st_doc.get("managed_paths")
                    if isinstance(raw_mp, (list, tuple)):
                        for item_p in raw_mp:
                            if type(item_p) is str and item_p and not has_symlink_raw_path(item_p) and not is_symlink_or_reparse(item_p):
                                try:
                                    persisted_hps.append(HostPath(item_p))
                                except (OSError, RuntimeError, ValueError):
                                    continue
                    raw_cmp = st_doc.get("core_managed_paths")
                    if isinstance(raw_cmp, (list, tuple)):
                        for c_item_p in raw_cmp:
                            if type(c_item_p) is str and c_item_p and not has_symlink_raw_path(c_item_p) and not is_symlink_or_reparse(c_item_p):
                                try:
                                    persisted_core_keys.add(HostPath(c_item_p).comparison_key)
                                except (OSError, RuntimeError, ValueError):
                                    continue
                    raw_mr = st_doc.get("managed_roots")
                    if isinstance(raw_mr, (list, tuple)):
                        for r_item_p in raw_mr:
                            if type(r_item_p) is str and r_item_p and not has_symlink_raw_path(r_item_p) and not is_symlink_or_reparse(r_item_p):
                                try:
                                    cand_mr = HostPath(r_item_p)
                                    if cand_mr.path not in self._host_dir.path.parents and cand_mr.path not in self._yscb_root.path.parents:
                                        persisted_roots.append(cand_mr)
                                except (OSError, RuntimeError, ValueError):
                                    continue
                except (UnicodeDecodeError, ValueError):
                    persisted_hps = []
                    persisted_core_keys = set()
                    persisted_roots = []

            candidate_prev_roots = (*persisted_roots, *retired_roots)
            venv_root_hp = try_resolve_contained_subpath(self._yscb_root, ".venv")
            extra_unlocked = 0
            carryover_locked: list[HostPath] = []
            core_carryover_locked: list[HostPath] = []
            carryover_roots: list[HostPath] = []
            for prev_hp in persisted_hps:
                prev_ck = prev_hp.comparison_key
                if prev_ck in seen_ro_keys:
                    continue
                raw_prev = str(prev_hp)
                if not os.path.lexists(raw_prev) or is_symlink_or_reparse(raw_prev) or has_symlink_raw_path(raw_prev):
                    continue
                matched_prev_root: Optional[HostPath] = next(
                    (r_hp for r_hp in candidate_prev_roots if prev_hp == r_hp or r_hp.path in prev_hp.path.parents),
                    None,
                )
                in_known_roots = (
                    cur_mt.to_uri(prev_hp) is not None
                    or matched_prev_root is not None
                    or any(old_mt.to_uri(prev_hp) is not None for old_mt in retired_mts)
                    or self._host_dir.path in prev_hp.path.parents
                    or self._yscb_root.path in prev_hp.path.parents
                )
                if not in_known_roots:
                    continue
                was_core_ro = prev_ck in persisted_core_keys
                if was_core_ro and venv_root_hp is not None and (
                    prev_hp == venv_root_hp or venv_root_hp.path in prev_hp.path.parents
                ):
                    continue
                prev_owner = "core" if was_core_ro else None
                is_reserved_prev = self.is_reserved_control_plane_path(
                    prev_hp,
                    owner=prev_owner,
                    allow_any_module_storage=True,
                )
                if is_reserved_prev and matched_prev_root is not None:
                    is_reserved_prev = is_control_plane_reserved_path(
                        prev_hp,
                        yscb_root=self._yscb_root,
                        host_dir=self._host_dir,
                        project_root=matched_prev_root,
                        project_root_disabled=False,
                        owner=prev_owner,
                        allow_any_module_storage=True,
                    )
                if is_reserved_prev:
                    continue
                try:
                    if self._readonly_policy.is_os_readonly(prev_hp):
                        if self._readonly_policy.unlock_file(prev_hp):
                            extra_unlocked += 1
                        elif self._readonly_policy.is_os_readonly(prev_hp):
                            carryover_locked.append(prev_hp)
                            if matched_prev_root is not None:
                                carryover_roots.append(matched_prev_root)
                            if was_core_ro:
                                core_carryover_locked.append(prev_hp)
                except (OSError, YscbError):
                    carryover_locked.append(prev_hp)
                    if matched_prev_root is not None:
                        carryover_roots.append(matched_prev_root)
                    if was_core_ro:
                        core_carryover_locked.append(prev_hp)

            with self._reload_lock:
                if self._mount_table is cur_mt and (self._retired_mount_tables or self._retired_custom_mount_roots):
                    if not carryover_locked:
                        self._retired_mount_tables.clear()
                        self._retired_custom_mount_roots.clear()
                    else:
                        self._retired_mount_tables = [
                            old_mt
                            for old_mt in self._retired_mount_tables
                            if any(
                                cur_mt.to_uri(c_hp) is None and old_mt.to_uri(c_hp) is not None
                                for c_hp in carryover_locked
                            )
                        ]
                        self._retired_custom_mount_roots = [
                            old_r
                            for old_r in self._retired_custom_mount_roots
                            if any(c_hp == old_r or old_r.path in c_hp.path.parents for c_hp in carryover_locked)
                        ]
            ro_res = self._readonly_policy.sync_files(ro_files)
            active_ro_existing = [
                hp_item
                for hp_item in ro_files
                if os.path.isfile(str(hp_item)) and not is_symlink_or_reparse(str(hp_item))
            ]
            next_managed = sorted(
                {
                    *(str(hp_item) for hp_item in active_ro_existing),
                    *(str(hp_item) for hp_item in carryover_locked),
                }
            )
            next_core_managed = sorted(
                {
                    *(
                        str(hp_item)
                        for hp_item in active_ro_existing
                        if hp_item.comparison_key in core_ro_keys
                    ),
                    *(str(hp_item) for hp_item in core_carryover_locked),
                }
            )
            next_roots_set: set[str] = {str(r_hp) for r_hp in carryover_roots}
            if active_ro_existing:
                for act_r in active_roots:
                    if any(
                        hp_item == act_r or act_r.path in hp_item.path.parents
                        for hp_item in active_ro_existing
                    ):
                        next_roots_set.add(str(act_r))
            try:
                atomic_write_json(
                    ro_state_hp,
                    {
                        "managed_paths": next_managed,
                        "core_managed_paths": next_core_managed,
                        "managed_roots": sorted(next_roots_set),
                    },
                )
            except (OSError, ValueError, YscbError):
                pass

            return {
                "gitignore_modified": gi_modified,
                "readonly_locked": ro_res.locked_count,
                "readonly_already_locked": ro_res.already_locked_count,
                "readonly_unlocked": extra_unlocked + ro_res.unlocked_count,
            }

    def invoke_internal_migration(
        self,
        module_id: ModuleId,
        mig_req: MigrationRequest,
        call_tree_id: Optional[str],
        *,
        cancel_token: Optional[CancellationToken] = None,
    ) -> None:
        mig_tid = TaskId(f"{module_id.value}.yscb_on_migrate")
        out = self._dispatcher.invoke(
            InvokeRequest(
                task_id=mig_tid,
                raw_input=DataclassCodec.encode_object(mig_req),
                workspace_root=self._yscb_root,
                caller_cwd=self._host_dir,
                routing_policy=ClientRoutingPolicy.FORCE_COLD,
                propagation=CallPropagationContext(
                    call_tree_id=call_tree_id,
                    is_internal_trigger=True,
                ),
            ),
            cancel_token=cancel_token,
        )
        if not out.ok:
            err = out.error
            if err is not None:
                raise YscbError(err.code, err.message, remediation=err.remediation, source_task=err.source_task)
            raise YscbError(ErrorCode.BUSINESS_FAILURE, f"Migration task '{mig_tid}' failed.")

    def build_daemon(
        self,
        *,
        watcher_debounce_sec: float = 0.5,
        self_restart_argv: Optional[Sequence[str]] = None,
    ) -> WorkspaceDaemon:
        with self._reload_lock:
            if self._closed or self._closing:
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "WorkspaceKernel is closed.")
        cfg_roots: list[HostPath] = []
        for host_cfg_name in ("yscb.config.json", "yscb.config.local.json"):
            hp = try_resolve_contained_subpath(self._host_dir, host_cfg_name)
            if hp is not None and not is_symlink_or_reparse(str(hp)):
                cfg_roots.append(hp)
        for sub_cfg in ("config", ".config.local"):
            sub_hp = try_resolve_contained_subpath(self._yscb_root, sub_cfg)
            if sub_hp is not None and not is_symlink_or_reparse(str(sub_hp)):
                os.makedirs(str(sub_hp), exist_ok=True)
                cfg_roots.append(sub_hp)

        watch_cfg = DaemonWatcherConfig(
            echo_guard=self._echo_guard,
            space_watch_roots=self.space_registry.collect_watch_roots(),
            config_watch_roots=tuple(cfg_roots),
            on_space_changed_task=TaskId("core.watcher"),
            on_config_changed_task=TaskId("core.config.on_changed"),
            watcher_debounce_sec=watcher_debounce_sec,
        )
        eff_restart = (
            self_restart_argv
            if self_restart_argv is not None
            else self._default_daemon_restart_argv()
        )
        use_kernel_router = bool(self._daemon_boot_id)
        daemon = WorkspaceDaemon(
            workspace_root=self._yscb_root,
            cache_dir=self._cache_dir,
            dispatcher=self._dispatcher,
            config_view=_DaemonConfigViewAdapter(self),
            watch_config=watch_cfg,
            self_restart_argv=eff_restart,
            flight_log_router=self._flight_log_router if use_kernel_router else None,
            daemon_boot_id=self._daemon_boot_id if use_kernel_router else "",
        )
        with self._reload_lock:
            if self._closed or self._closing:
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "WorkspaceKernel is closed.")
            self._built_daemons.append(weakref.ref(daemon))
        return daemon

    def _is_daemon_spawn_in_progress(self) -> bool:
        lease_hp = resolve_contained_subpath(self._cache_dir, DAEMON_SUBDIR, "spawn_lease.json")
        lease_doc = read_json_dict(lease_hp)
        if lease_doc is None:
            return False
        try:
            spawned_ts = safe_real_to_float(lease_doc.get("spawned_epoch", 0.0))
        except ValueError:
            return False
        raw_pid = lease_doc.get("pid", 0)
        lease_pid = raw_pid if type(raw_pid) is int and raw_pid > 0 else 0
        now_epoch = time.time()
        spawn_window_sec = 10.0 if IS_WINDOWS else 5.0
        return bool(
            math.isfinite(spawned_ts)
            and lease_pid > 0
            and 0.0 <= (now_epoch - spawned_ts) < spawn_window_sec
            and is_process_alive(lease_pid)
        )

    def has_deferred_daemon(self) -> bool:
        return self._deferred_daemon_console_mode is not None

    def run_deferred_daemon(self, *, on_ready: Optional[Callable[[], None]] = None) -> tuple[bool, int]:
        run_mode = self._deferred_daemon_console_mode
        self._deferred_daemon_console_mode = None
        if run_mode is None:
            return (False, 0)
        res = _run_deferred_daemon_host(
            self._host_dir,
            self._yscb_root,
            self._yscb_script_path,
            run_mode,
            on_ready,
        )
        self._post_close_exit_code = res.post_close_rc
        return (res.acquired_lock, res.daemon_rc)

    def spawn_or_run_daemon(self, *, console: bool, detach: bool, supervisor: bool = False) -> JsonObject:
        with self._reload_lock:
            if self._closed or self._closing:
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "WorkspaceKernel is closed.")
        if (console or supervisor) and not detach:
            eff_console = bool(console and not supervisor)
            mode_label = "console" if eff_console else "supervisor"
            if not self._is_daemon_host:
                if not self._allow_deferred_daemon_console:
                    raise YscbError(
                        ErrorCode.EXPOSURE_DENIED,
                        f"Foreground daemon '{mode_label}' mode requires a CLI host session (use detach=True from SDK).",
                    )
                if probe_daemon_endpoint(self._cache_dir, self._yscb_root) is not None:
                    return {"mode": mode_label, "already_running": True, "started": False}
                self._deferred_daemon_console_mode = eff_console
                return {"mode": mode_label, "started": True}
            daemon = self.build_daemon()
            rc = daemon.run_forever(console_mode=eff_console)
            return {"mode": mode_label, "exit_code": rc}

        can_spawn = self._spawner.can_spawn_in_environment()
        if probe_daemon_endpoint(self._cache_dir, self._yscb_root) is not None:
            return {
                "mode": "background",
                "already_running": True,
                "spawned": False,
                "online": True,
                "sandbox_restricted": not can_spawn,
            }
        spawned = self._spawner.try_spawn_background(self._yscb_root)
        if spawned or can_spawn:
            deadline = time.monotonic() + (10.0 if IS_WINDOWS else 5.0)
            while time.monotonic() < deadline:
                if probe_daemon_endpoint(self._cache_dir, self._yscb_root) is not None:
                    break
                if not spawned and can_spawn and not self._is_daemon_spawn_in_progress():
                    spawned = self._spawner.try_spawn_background(self._yscb_root)
                time.sleep(0.03)
        online = probe_daemon_endpoint(self._cache_dir, self._yscb_root) is not None
        return {
            "mode": "background",
            "already_running": bool(online and not spawned),
            "spawned": spawned,
            "online": online,
            "sandbox_restricted": not can_spawn,
        }

    def close(self) -> None:
        with self._reload_lock:
            if self._closed or self._closing:
                return
            self._closing = True
            owned_children = [*self._retired_child_kernels, *self._owned_child_kernels.values()]
            self._retired_child_kernels.clear()
            self._owned_child_kernels.clear()
            self._owned_child_fingerprints.clear()
            self._owned_child_sync_locks.clear()
            daemon_refs = list(self._built_daemons)
            self._built_daemons.clear()
            pending_sync = self._pending_daemon_sync
            self._pending_daemon_sync = None
            notify_space = self._pending_dynamic_space_notify
            self._pending_dynamic_space_notify = False

        first_exc: Optional[BaseException] = None
        for child_k in reversed(owned_children):
            try:
                child_k.close()
            except BaseException as exc:
                if first_exc is None:
                    first_exc = exc

        for d_ref in reversed(daemon_refs):
            d_inst = d_ref()
            if d_inst is not None:
                try:
                    d_inst.request_shutdown(force=True)
                except BaseException as exc:
                    if first_exc is None:
                        first_exc = exc

        try:
            _ = self._dispatcher.shutdown()
        except BaseException as exc:
            if first_exc is None:
                first_exc = exc

        late_children: list[WorkspaceKernel] = []
        try:
            with self._reload_lock:
                self._closed = True
                late_children = [*self._retired_child_kernels, *self._owned_child_kernels.values()]
                self._retired_child_kernels.clear()
                self._owned_child_kernels.clear()
                self._owned_child_fingerprints.clear()
                self._owned_child_sync_locks.clear()
                self._child_last_checkout_mono.clear()
                if self._pending_dynamic_space_notify:
                    notify_space = True
                    self._pending_dynamic_space_notify = False
                self._evict_cached_tier0_output_pkgs_locked()
        except BaseException as exc:
            if first_exc is None:
                first_exc = exc
        finally:
            unbind_locale_getter_owner(self._dispatcher)
            unbind_locale_getter_dialect(self._locale_getter_fn)
            unbind_system_kernel(self._yscb_root, self)

        for late_k in reversed(late_children):
            try:
                late_k.close()
            except BaseException as exc:
                if first_exc is None:
                    first_exc = exc

        try:
            with self._space_sync_op_lock:
                self._space_db.close()
        except BaseException as exc:
            if first_exc is None:
                first_exc = exc

        try:
            self._flight_log_router.close()
        except BaseException as exc:
            if first_exc is None:
                first_exc = exc

        if pending_sync is not None:
            try:
                self._deliver_daemon_sync_pair(pending_sync)
            except BaseException as exc:
                if first_exc is None:
                    first_exc = exc

        if notify_space:
            try:
                self._notify_dynamic_space_mutation()
            except BaseException as exc:
                if first_exc is None:
                    first_exc = exc

        if first_exc is not None:
            raise first_exc


class WorkspaceKernelFactory:
    """Single Composition Root factory constructing wired WorkspaceKernel and CLI/Daemon sessions."""

    @staticmethod
    def create(
        host_dir: HostPath,
        yscb_root: HostPath,
        *,
        is_daemon_host: bool = False,
        force_cold: bool = False,
        extra_modules: Sequence[Module | InMemoryModule | YscbModule] = (),
        yscb_script_path: Optional[HostPath] = None,
        dialect: Optional[str] = None,
    ) -> WorkspaceKernel:
        if not isinstance(host_dir, HostPath) or not isinstance(yscb_root, HostPath):
            raise TypeError("host_dir and yscb_root must be HostPath instances")
        require_pure_bool(is_daemon_host, "is_daemon_host")
        require_pure_bool(force_cold, "force_cold")
        coerced: list[YscbModule] = []
        extra_cfg_types: dict[ModuleId, type[object]] = {}
        extra_live_specs: dict[ModuleId, Sequence[ExtensionPointSpec[object]]] = {}
        for item in extra_modules:
            if isinstance(item, Module):
                ym = item.to_yscb_module()
                coerced.append(ym)
                if item.config_type is not None:
                    extra_cfg_types[ym.module_id] = item.config_type
                if item.extension_points:
                    extra_live_specs[ym.module_id] = item.extension_points
            elif isinstance(item, InMemoryModule):
                coerced.append(item.to_yscb_module())
            elif isinstance(item, YscbModule):
                coerced.append(item)
            else:
                raise TypeError(f"Unsupported extra_modules entry: {item!r}")
        return WorkspaceKernel(
            host_dir=host_dir,
            yscb_root=yscb_root,
            is_daemon_host=is_daemon_host,
            force_cold=force_cold,
            extra_modules=tuple(coerced),
            yscb_script_path=yscb_script_path,
            dialect=dialect,
            extra_config_types=extra_cfg_types,
            extra_live_specs=extra_live_specs,
        )

    @staticmethod
    def open_cli_session(
        host_dir: HostPath,
        yscb_root: HostPath,
        force_cold: bool = False,
        *,
        yscb_script_path: Optional[HostPath] = None,
    ) -> CliKernelSession:
        if not isinstance(host_dir, HostPath) or not isinstance(yscb_root, HostPath):
            raise TypeError("host_dir and yscb_root must be HostPath instances")
        require_pure_bool(force_cold, "force_cold")
        return _LazyCliKernelSession(
            host_dir=host_dir,
            yscb_root=yscb_root,
            force_cold=force_cold,
            yscb_script_path=yscb_script_path,
        )

    @staticmethod
    def open_sdk_core_session(
        host_dir: HostPath,
        yscb_root: HostPath,
    ) -> tuple[object, Callable[[], None]]:
        lazy_port = _LazySdkKernelPort(host_dir=host_dir, yscb_root=yscb_root)
        ymod = CoreSystemModule(lazy_port).to_yscb_module()
        lazy_port.bind_core_module(ymod)
        register_sdk_core_post_call_hook(ymod, lazy_port.flush_pending_daemon_sync)

        def _close_lazy_port() -> None:
            lazy_port.close()

        return (ymod, _close_lazy_port)

    @staticmethod
    def builtin_cli_indices() -> tuple[ModuleTasksIndex, ...]:
        return (compile_tasks_index(CoreSystemModule),)


class _DaemonConfigViewAdapter(ConfigViewPort):
    """ConfigViewPort bridge exposing live SpaceRegistry watch roots to WorkspaceDaemon without signature changes."""

    def __init__(self, kernel: WorkspaceKernel) -> None:
        self._kernel = kernel

    def get_module_value(self, module_id: ModuleId, dotted_key: str, default: JsonValue = None) -> JsonValue:
        if module_id == CORE_MODULE_ID and dotted_key == "_yscb_space_watch_roots":
            return [str(p) for p in self._kernel.space_registry.collect_watch_roots()]
        return self._kernel.config_store.get_module_value(module_id, dotted_key, default=default)

    def fingerprint(self) -> str:
        return self._kernel.config_and_contributes_fingerprint()

    def reload(self) -> None:
        self._kernel.on_config_view_reload_requested()


@dataclass(frozen=True, slots=True)
class _Tier0OutputCacheEntry:
    fingerprint: str
    package_key: str
    output_types: Mapping[TaskId, object]


class _LazySdkKernelPort(SystemKernelPort):
    """Zero-overhead lazy SystemKernelPort materializing a cold WorkspaceKernel only on local core.* task execution."""

    def __init__(self, *, host_dir: HostPath, yscb_root: HostPath) -> None:
        self._host_dir = host_dir
        self._yscb_root = yscb_root
        self._lock = threading.RLock()
        self._inner: Optional[WorkspaceKernel] = None
        self._core_ymod_ref: Optional[weakref.ref[object]] = None
        self._bound_inner_id: Optional[int] = None
        self._closed = False

    def bind_core_module(self, core_ymod: object) -> None:
        with self._lock:
            self._core_ymod_ref = weakref.ref(core_ymod)

    def _resolve_effective_host_dir_locked(self) -> HostPath:
        if self._host_dir != self._yscb_root or (self._host_dir.path / "yscb.config.json").is_file():
            return self._host_dir
        found_host = probe_workspace_host_dir(self._yscb_root)
        if found_host is not None:
            self._host_dir = found_host
            return found_host
        return self._host_dir

    def _ensure(self) -> SystemKernelPort:
        stale_inner: Optional[WorkspaceKernel] = None
        with self._lock:
            if self._closed:
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"SDK core session for '{self._yscb_root}' is closed.")
            eff_host = self._resolve_effective_host_dir_locked()
            if self._inner is not None and not self._inner.is_closed and self._inner.host_dir != eff_host:
                stale_inner = self._inner
                self._inner = None
                self._bound_inner_id = None
            if self._inner is None or self._inner.is_closed:
                self._inner = WorkspaceKernel(
                    host_dir=eff_host,
                    yscb_root=self._yscb_root,
                    is_daemon_host=False,
                    force_cold=True,
                    extra_modules=(),
                    yscb_script_path=None,
                    is_managed_child=True,
                    allow_auto_spawn=False,
                )
                self._bound_inner_id = None
            active_inner = self._inner
            if self._bound_inner_id != id(active_inner) and self._core_ymod_ref is not None:
                ymod_obj = self._core_ymod_ref()
                if ymod_obj is not None:
                    binder = resolve_sdk_core_dispatcher_binder(ymod_obj)
                    if binder is not None:
                        binder(active_inner.dispatcher)
                        self._bound_inner_id = id(active_inner)
        if stale_inner is not None:
            stale_inner.close()
        return active_inner

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            inner = self._inner
            self._inner = None
        if inner is not None:
            inner.close()

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def is_closing(self) -> bool:
        return self._closed

    @property
    def is_managed_child(self) -> bool:
        return True

    @property
    def host_dir(self) -> HostPath:
        with self._lock:
            return self._resolve_effective_host_dir_locked()

    @property
    def yscb_root(self) -> HostPath:
        return self._yscb_root

    @property
    def cache_dir(self) -> HostPath:
        return self._ensure().cache_dir

    @property
    def config_store(self) -> ConfigStore:
        return self._ensure().config_store

    @property
    def snapshot_vault(self) -> SnapshotVault:
        return self._ensure().snapshot_vault

    @property
    def contributes_aggregator(self) -> ContributesAggregator:
        return self._ensure().contributes_aggregator

    @property
    def mount_table(self) -> UriMountTable:
        return self._ensure().mount_table

    @property
    def readonly_policy(self) -> ReadonlyPolicy:
        return self._ensure().readonly_policy

    @property
    def kernel_vfs(self) -> KernelVfs:
        return self._ensure().kernel_vfs

    @property
    def space_registry(self) -> SpaceRegistry:
        return self._ensure().space_registry

    @property
    def space_scanner(self) -> SpaceScanner:
        return self._ensure().space_scanner

    @property
    def gitignore_materializer(self) -> GitignoreMaterializer:
        return self._ensure().gitignore_materializer

    @property
    def env_pool(self) -> ImmutableVenvPool:
        return self._ensure().env_pool

    @property
    def env_probe(self) -> EnvHealthProbe:
        return self._ensure().env_probe

    @property
    def env_gc(self) -> EnvGarbageCollector:
        return self._ensure().env_gc

    @property
    def package_engine(self) -> OfflinePackageEngine:
        return self._ensure().package_engine

    def list_route_specs(self) -> Sequence[TaskRouteSpec]:
        return self._ensure().list_route_specs()

    def ensure_installed_tasks_indices(self, module_ids: Optional[Iterable[ModuleId]] = None) -> None:
        self._ensure().ensure_installed_tasks_indices(module_ids)

    def resolve_module_config_type(self, module_id: ModuleId) -> Optional[type[object]]:
        return self._ensure().resolve_module_config_type(module_id)

    def invoke_internal_migration(
        self,
        module_id: ModuleId,
        mig_req: MigrationRequest,
        call_tree_id: Optional[str],
        *,
        cancel_token: Optional[CancellationToken] = None,
    ) -> None:
        self._ensure().invoke_internal_migration(module_id, mig_req, call_tree_id, cancel_token=cancel_token)

    @contextmanager
    def installer_transaction_lock(self, cancel_token: Optional[CancellationToken] = None) -> Iterator[None]:
        with self._ensure().installer_transaction_lock(cancel_token):
            yield

    @contextmanager
    def space_sync_guard(self) -> Iterator[None]:
        with self._ensure().space_sync_guard():
            yield

    def has_running_daemon(self) -> bool:
        with self._lock:
            inner = self._inner
            closed = self._closed
        if closed or inner is None or inner.is_closed:
            return False
        return inner.has_running_daemon()

    def is_daemon_quiesced(self) -> bool:
        with self._lock:
            inner = self._inner
            closed = self._closed
        if closed or inner is None or inner.is_closed:
            return False
        return inner.is_daemon_quiesced()

    def refresh_dynamic_spaces_only(self) -> tuple[str, ...]:
        return self._ensure().refresh_dynamic_spaces_only()

    def reload_config_only(self, changed_paths: Sequence[str] = ()) -> bool:
        return self._ensure().reload_config_only(changed_paths)

    def evict_local_modules_before_remove(self, modules: Sequence[ModuleId]) -> None:
        self._ensure().evict_local_modules_before_remove(modules)

    def reload_workspace_metadata(self) -> None:
        self._ensure().reload_workspace_metadata()

    def schedule_post_close_daemon_sync(
        self,
        *,
        quiesced: bool,
        quiesce_epoch: Optional[int],
        core_handoff: bool = False,
    ) -> None:
        self._ensure().schedule_post_close_daemon_sync(
            quiesced=quiesced,
            quiesce_epoch=quiesce_epoch,
            core_handoff=core_handoff,
        )

    def flush_pending_daemon_sync(self) -> None:
        with self._lock:
            inner = self._inner
            closed = self._closed
        if not closed and inner is not None and not inner.is_closed:
            try:
                inner.flush_pending_daemon_sync()
            except (OSError, ValueError, YscbError):
                pass

    def rebuild_tasks_index_cache(self) -> None:
        self._ensure().rebuild_tasks_index_cache()

    def set_dynamic_space(self, owner: ModuleId, name: str, spec: SpaceSpec) -> bool:
        return self._ensure().set_dynamic_space(owner, name, spec)

    def clear_dynamic_spaces(self, owner: ModuleId, name: Optional[str] = None, *, sync: bool = True) -> int:
        return self._ensure().clear_dynamic_spaces(owner, name, sync=sync)

    def is_reserved_control_plane_path(
        self,
        hp: HostPath,
        *,
        owner: Optional[str] = None,
        allow_any_module_storage: bool = False,
    ) -> bool:
        return self._ensure().is_reserved_control_plane_path(
            hp,
            owner=owner,
            allow_any_module_storage=allow_any_module_storage,
        )

    def sync_gitignore_and_readonly(self) -> JsonObject:
        return self._ensure().sync_gitignore_and_readonly()

    def collect_active_env_specs(self) -> tuple[EnvSpec, ...]:
        return self._ensure().collect_active_env_specs()

    def discover_installed_manifests(self) -> Mapping[ModuleId, ModuleManifest]:
        return self._ensure().discover_installed_manifests()

    def spawn_or_run_daemon(self, *, console: bool, detach: bool, supervisor: bool = False) -> JsonObject:
        return self._ensure().spawn_or_run_daemon(console=console, detach=detach, supervisor=supervisor)


class _LazyCliDispatcherProxy:
    """Lightweight CLI dispatcher proxy intercepting foreground daemon start before creating a cold kernel."""

    def __init__(self, session: _LazyCliKernelSession) -> None:
        self._session = session

    def invoke(
        self,
        request: InvokeRequest,
        *,
        output_type: Optional[type[object]] = None,
        cancel_token: Optional[CancellationToken] = None,
        on_progress: Optional[Callable[[JsonObject], None]] = None,
    ) -> TaskOutcome[object]:
        prop = request.propagation
        if (
            request.task_id == TaskId("core.daemon.start")
            and request.workspace_root == self._session.yscb_root
            and not self._session.is_closed
            and output_type is None
            and request.allow_conditional
            and request.routing_policy != ClientRoutingPolicy.STRICT_HOT
            and not prop.in_event_chain
            and not prop.call_stack
            and not prop.from_hot_container
            and not prop.is_nested_call
            and not prop.is_internal_trigger
            and resolve_active_caller_module() is None
        ):
            try:
                decoded_start = DataclassCodec.decode(DaemonStartInput, request.raw_input)
            except (YscbError, ValueError, TypeError, KeyError):
                decoded_start = None
            if decoded_start is not None and (decoded_start.console or decoded_start.supervisor) and not decoded_start.detach:
                return self._session.handle_fast_foreground_daemon_start(
                    console=decoded_start.console,
                    supervisor=decoded_start.supervisor,
                    cancel_token=cancel_token,
                    profiler=request.active_profiler,
                )
        kernel = self._session.ensure_kernel(profiler=request.active_profiler)
        return kernel.dispatcher.invoke(
            request,
            output_type=output_type,
            cancel_token=cancel_token,
            on_progress=on_progress,
        )


class _LazyCliKernelSession:
    """Deferred CliKernelSession avoiding duplicate WorkspaceKernel instantiation on foreground daemon start."""

    def __init__(
        self,
        *,
        host_dir: HostPath,
        yscb_root: HostPath,
        force_cold: bool,
        yscb_script_path: Optional[HostPath],
    ) -> None:
        self._host_dir = host_dir
        self._yscb_root = yscb_root
        self._cache_dir = resolve_contained_subpath(yscb_root, DEFAULT_CACHE_DIRNAME)
        self._force_cold = force_cold
        self._yscb_script_path = yscb_script_path
        self._lock = threading.RLock()
        self._kernel: Optional[WorkspaceKernel] = None
        self._config_store_cache: Optional[ConfigStore] = None
        self._dialect: Optional[str] = None
        self._raw_env_locale: Optional[str] = None
        self._dialect_applied = False
        self._deferred_daemon_console_mode: Optional[bool] = None
        self._post_close_exit_code: Optional[int] = None
        self._closed = False
        self._proxy_dispatcher = _LazyCliDispatcherProxy(self)

    @property
    def yscb_root(self) -> HostPath:
        return self._yscb_root

    @property
    def is_closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def dispatcher(self) -> RuntimeDispatcher | _LazyCliDispatcherProxy:
        with self._lock:
            if self._kernel is not None:
                return self._kernel.dispatcher
            return self._proxy_dispatcher

    @property
    def config_store(self) -> Optional[ConfigStore]:
        with self._lock:
            if self._kernel is not None:
                return self._kernel.config_store
            if self._config_store_cache is None:
                self._config_store_cache = ConfigStore(host_dir=self._host_dir, yscb_root=self._yscb_root)
            return self._config_store_cache

    def ensure_kernel(self, *, profiler: Optional[Profiler] = None) -> WorkspaceKernel:
        with self._lock:
            if self._closed:
                raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, "CLI kernel session is closed.")
            if self._kernel is not None:
                return self._kernel
            eff_dialect = self._dialect
            eff_raw_loc = self._raw_env_locale if self._dialect_applied else None
            if profiler is not None:
                with profiler.scope_relative("Bootstrap/CreateKernel"):
                    built = WorkspaceKernel(
                        host_dir=self._host_dir,
                        yscb_root=self._yscb_root,
                        is_daemon_host=False,
                        force_cold=self._force_cold,
                        extra_modules=(),
                        yscb_script_path=self._yscb_script_path,
                        dialect=eff_dialect,
                        allow_deferred_daemon_console=True,
                        raw_env_locale_override=eff_raw_loc,
                        profiler=profiler,
                    )
            else:
                built = WorkspaceKernel(
                    host_dir=self._host_dir,
                    yscb_root=self._yscb_root,
                    is_daemon_host=False,
                    force_cold=self._force_cold,
                    extra_modules=(),
                    yscb_script_path=self._yscb_script_path,
                    dialect=eff_dialect,
                    allow_deferred_daemon_console=True,
                    raw_env_locale_override=eff_raw_loc,
                )
            self._kernel = built
            return built

    def handle_fast_foreground_daemon_start(
        self,
        *,
        console: bool,
        supervisor: bool,
        cancel_token: Optional[CancellationToken],
        profiler: Optional[Profiler],
    ) -> TaskOutcome[JsonValue]:
        if cancel_token is not None and cancel_token.is_cancelled:
            return TaskOutcome(
                ok=False,
                error=ErrorDetail(
                    ErrorCode.TASK_CANCELLED,
                    cancel_token.reason or "Task cancelled.",
                    source_task="core.daemon.start",
                ),
            )
        if is_active_cross_workspace_call():
            return TaskOutcome(
                ok=False,
                error=ErrorDetail(
                    ErrorCode.ACCESS_DENIED,
                    "Cross-workspace callers are not permitted to start workspace daemon.",
                    source_task="core.daemon.start",
                ),
            )
        eff_console = bool(console and not supervisor)
        mode_label = "console" if eff_console else "supervisor"
        if profiler is not None:
            with profiler.scope_relative("Daemon/FastStartProbe"):
                live_ep = probe_daemon_endpoint(self._cache_dir, self._yscb_root)
        else:
            live_ep = probe_daemon_endpoint(self._cache_dir, self._yscb_root)
        if live_ep is not None:
            view = SystemResultView(
                "Daemon start processed.",
                {"mode": mode_label, "already_running": True, "started": False},
            )
            return TaskOutcome(ok=True, value=DataclassCodec.encode_object(view), executed_hot=False)
        with self._lock:
            if self._closed:
                return TaskOutcome(
                    ok=False,
                    error=ErrorDetail(
                        ErrorCode.DAEMON_UNAVAILABLE,
                        "CLI kernel session is closed.",
                        source_task="core.daemon.start",
                    ),
                )
            self._deferred_daemon_console_mode = eff_console
        view = SystemResultView("Daemon start processed.", {"mode": mode_label, "started": True})
        return TaskOutcome(ok=True, value=DataclassCodec.encode_object(view), executed_hot=False)

    def apply_caller_dialect(self, dialect: Optional[str], raw_env_locale: Optional[str] = None) -> None:
        with self._lock:
            self._dialect = dialect.strip() if isinstance(dialect, str) and dialect.strip() else None
            self._raw_env_locale = raw_env_locale.strip() if isinstance(raw_env_locale, str) else None
            self._dialect_applied = True
            kernel = self._kernel
        if kernel is not None:
            kernel.apply_caller_dialect(dialect, raw_env_locale)

    def resolve_task_output_type(self, task_id: TaskId) -> Optional[object]:
        with self._lock:
            kernel = self._kernel
        if kernel is not None:
            return kernel.resolve_task_output_type(task_id)
        if task_id == TaskId("core.daemon.start"):
            return SystemResultView
        return None

    def resolve_task_presentation(
        self,
        task_entry: IndexedTaskEntry,
        raw_value: JsonValue,
        *,
        render_human: bool,
    ) -> tuple[Optional[str], Optional[int]]:
        with self._lock:
            kernel = self._kernel
        if kernel is not None:
            return kernel.resolve_task_presentation(task_entry, raw_value, render_human=render_human)
        if task_entry.task_id == TaskId("core.daemon.start"):
            try:
                typed_val = DataclassCodec.decode(SystemResultView, raw_value)
            except (TypeError, ValueError, YscbError):
                return (None, None)
            if not render_human:
                return (None, typed_val.exit_code())
            return format_output(typed_val)
        return (None, None)

    def has_deferred_daemon(self) -> bool:
        with self._lock:
            if self._kernel is not None:
                return self._kernel.has_deferred_daemon()
            return self._deferred_daemon_console_mode is not None

    def run_deferred_daemon(self, *, on_ready: Optional[Callable[[], None]] = None) -> tuple[bool, int]:
        with self._lock:
            kernel = self._kernel
            run_mode = self._deferred_daemon_console_mode
            self._deferred_daemon_console_mode = None
        if kernel is not None:
            return kernel.run_deferred_daemon(on_ready=on_ready)
        if run_mode is None:
            return (False, 0)
        res = _run_deferred_daemon_host(
            self._host_dir,
            self._yscb_root,
            self._yscb_script_path,
            run_mode,
            on_ready,
        )
        with self._lock:
            self._post_close_exit_code = res.post_close_rc
        return (res.acquired_lock, res.daemon_rc)

    def consume_post_close_exit_code(self) -> Optional[int]:
        with self._lock:
            kernel = self._kernel
            rc = self._post_close_exit_code
            self._post_close_exit_code = None
        if kernel is not None:
            return kernel.consume_post_close_exit_code()
        return rc

    def close(self) -> None:
        with self._lock:
            self._closed = True
            kernel = self._kernel
        if kernel is not None:
            kernel.close()


__all__: tuple[str, ...] = (
    "DEFAULT_PROVIDER_URL",
    "DEFAULT_SELF_UPDATE_URL",
    "ModuleProviderAdapter",
    "WorkspaceKernel",
    "WorkspaceKernelFactory",
)
