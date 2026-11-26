"""Built-in CoreSystemModule implementing all workspace, daemon, package, config, VFS, space, and env system Tasks."""

from __future__ import annotations

import ast
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from types import MappingProxyType
from typing import Annotated, Callable, ClassVar, Final, Iterable, Mapping, Optional, Protocol, Sequence
import weakref

from core.execution.daemon import (
    DaemonQuiesceControl,
    DaemonReloadControl,
    DaemonResumeControl,
    DaemonStopControl,
    query_daemon_control,
)
from core.execution.rpc import FrameKind, probe_daemon_endpoint, read_daemon_endpoint_file
from core.execution.runtime import (
    BoundTask,
    CONFIG_CHANGED_EVENT,
    CORE_MODULE_ID,
    ConfigChangedEventPayload,
    DispatchMode,
    Empty,
    MODULE_INSTALLED_EVENT,
    MODULE_REMOVING_EVENT,
    ModuleLifecycleEventPayload,
    SPACE_REGISTRY_CHANGED_EVENT,
    SPACE_UPDATED_EVENT,
    SecurityTier,
    SelfMutationScope,
    SpaceUpdatedEventPayload,
    TaskContext,
    TaskExposure,
    TaskMetadata,
    TaskRouteSpec,
    WORKSPACE_RELOADED_EVENT,
    YscbModule,
    resolve_active_call_tree_id,
    resolve_active_caller_module,
)
from core.filesystem.fs import (
    MAX_JSON_FILE_BYTES,
    assert_no_symlink_raw_path,
    has_symlink_raw_path,
    is_symlink_or_reparse,
    read_nofollow_regular_bytes,
    try_resolve_contained_subpath,
)
from core.filesystem.space import (
    GitignoreMaterializer,
    SpaceDiffBatch,
    SpaceFileEntry,
    SpaceMatchExplain,
    SpaceRegistry,
    SpaceScanner,
    SpaceSpec,
    SpaceStatusSnapshot,
)
from core.filesystem.vfs import KernelVfs, ReadonlyPolicy, UriMountTable
from core.foundation import (
    CancellationToken,
    DataclassCodec,
    ErrorCode,
    HostPath,
    INT64_MAX,
    INT64_MIN,
    JsonObject,
    JsonValue,
    ModuleId,
    MutableJsonObject,
    SemanticUri,
    SnapshotGen,
    SpaceId,
    SpacePath,
    TaskId,
    YscbError,
    is_process_alive,
    require_pure_int,
    require_pure_str,
    strict_parse_json_object,
)
from core.metadata.config import (
    ConfigStore,
    ModuleManifest,
    SnapshotVault,
    parse_manifest_dict,
    register_compiled_module_surface_meta,
)
from core.metadata.contributes import ContributesAggregator, is_active_cross_workspace_call
from core.packaging.env import EnvGarbageCollector, EnvHealthProbe, EnvSpec, ImmutableVenvPool
from core.packaging.installer import (
    DeploymentReport,
    OfflinePackageEngine,
    PackageRequest,
    ProviderClient,
    PurgeLevel,
)
from core.surface.cli import CLI_DEFAULT_PROVIDER_URL
from core.surface.sdk import (
    Arg,
    ExitCodeProvider,
    HumanRenderable,
    MigrationRequest,
    Module,
    Option,
    TaskGroup,
    task,
)

_SPACE_MUTATION_LOCK: Final[str] = "core:space_state"

_MUTATION_SCOPE_BY_TASK: Final[Mapping[str, SelfMutationScope]] = MappingProxyType({
    "core.reload": SelfMutationScope.MUTATES_MODULES,
    "core.restore": SelfMutationScope.MUTATES_MODULES,
    "core.remove": SelfMutationScope.MUTATES_MODULES,
    "core.purge": SelfMutationScope.MUTATES_MODULES,
    "core.env.repair": SelfMutationScope.MUTATES_MODULES,
    "core.env.gc": SelfMutationScope.MUTATES_MODULES,
    "core.install": SelfMutationScope.MUTATES_CORE,
    "core.update": SelfMutationScope.MUTATES_CORE,
    "core.rollback": SelfMutationScope.MUTATES_CORE,
})
_INTERNAL_TRIGGER_TASKS: Final[frozenset[str]] = frozenset(
    {"core.watcher", "core.config.on_changed"}
)
_KERNEL_ONLY_LOCK_SCHEMES: Final[frozenset[str]] = frozenset(
    {
        "yscb",
        "module",
        "module.mirror",
        "snapshot",
        "yscb.venv",
    }
)

class SystemKernelPort(Protocol):
    """Public kernel collaboration port consumed by CoreSystemModule task groups."""

    @property
    def is_closed(self) -> bool: ...

    @property
    def is_closing(self) -> bool: ...

    @property
    def is_managed_child(self) -> bool: ...

    @property
    def host_dir(self) -> HostPath: ...

    @property
    def yscb_root(self) -> HostPath: ...

    @property
    def cache_dir(self) -> HostPath: ...

    @property
    def config_store(self) -> ConfigStore: ...

    @property
    def snapshot_vault(self) -> SnapshotVault: ...

    @property
    def contributes_aggregator(self) -> ContributesAggregator: ...

    @property
    def mount_table(self) -> UriMountTable: ...

    @property
    def readonly_policy(self) -> ReadonlyPolicy: ...

    @property
    def kernel_vfs(self) -> KernelVfs: ...

    @property
    def space_registry(self) -> SpaceRegistry: ...

    @property
    def space_scanner(self) -> SpaceScanner: ...

    @property
    def gitignore_materializer(self) -> GitignoreMaterializer: ...

    @property
    def env_pool(self) -> ImmutableVenvPool: ...

    @property
    def env_probe(self) -> EnvHealthProbe: ...

    @property
    def env_gc(self) -> EnvGarbageCollector: ...

    @property
    def package_engine(self) -> OfflinePackageEngine: ...

    def list_route_specs(self) -> Sequence[TaskRouteSpec]: ...

    def ensure_installed_tasks_indices(self, module_ids: Optional[Iterable[ModuleId]] = None) -> None: ...

    def resolve_module_config_type(self, module_id: ModuleId) -> Optional[type[object]]: ...

    def invoke_internal_migration(
        self,
        module_id: ModuleId,
        mig_req: MigrationRequest,
        call_tree_id: Optional[str],
        *,
        cancel_token: Optional[CancellationToken] = None,
    ) -> None: ...

    def installer_transaction_lock(self, cancel_token: Optional[CancellationToken] = None) -> AbstractContextManager[None]: ...

    def space_sync_guard(self) -> AbstractContextManager[None]: ...

    def has_running_daemon(self) -> bool: ...

    def is_daemon_quiesced(self) -> bool: ...

    def refresh_dynamic_spaces_only(self) -> tuple[str, ...]: ...

    def reload_config_only(self, changed_paths: Sequence[str] = ()) -> bool: ...

    def evict_local_modules_before_remove(self, modules: Sequence[ModuleId]) -> None: ...

    def reload_workspace_metadata(self) -> None: ...

    def schedule_post_close_daemon_sync(self, *, quiesced: bool, quiesce_epoch: Optional[int], core_handoff: bool = False) -> None: ...

    def flush_pending_daemon_sync(self) -> None: ...

    def rebuild_tasks_index_cache(self) -> None: ...

    def set_dynamic_space(self, owner: ModuleId, name: str, spec: SpaceSpec) -> bool: ...

    def clear_dynamic_spaces(self, owner: ModuleId, name: Optional[str] = None, *, sync: bool = True) -> int: ...

    def is_reserved_control_plane_path(
        self,
        hp: HostPath,
        *,
        owner: Optional[str] = None,
        allow_any_module_storage: bool = False,
    ) -> bool: ...

    def sync_gitignore_and_readonly(self) -> JsonObject: ...

    def collect_active_env_specs(self) -> tuple[EnvSpec, ...]: ...

    def discover_installed_manifests(self) -> Mapping[ModuleId, ModuleManifest]: ...

    def spawn_or_run_daemon(self, *, console: bool, detach: bool, supervisor: bool = False) -> JsonObject: ...


class _SystemKernelRegistry:
    """Thread-safe LIFO weakref stack tracking active WorkspaceKernel instances per workspace."""

    _LOCK: ClassVar[threading.RLock] = threading.RLock()
    _STACKS: ClassVar[dict[str, list[weakref.ReferenceType[SystemKernelPort]]]] = {}

    @classmethod
    def bind(cls, yscb_root: HostPath, kernel: SystemKernelPort) -> None:
        key = yscb_root.comparison_key
        with cls._LOCK:
            cur = cls._STACKS.get(key, [])
            alive = [ref for ref in cur if (obj := ref()) is not None and not obj.is_closed and obj is not kernel]
            alive.append(weakref.ref(kernel))
            cls._STACKS[key] = alive

    @classmethod
    def unbind(cls, yscb_root: HostPath, kernel: SystemKernelPort) -> None:
        key = yscb_root.comparison_key
        with cls._LOCK:
            cur = cls._STACKS.get(key)
            if cur is None:
                return
            alive = [ref for ref in cur if (obj := ref()) is not None and not obj.is_closed and obj is not kernel]
            if alive:
                cls._STACKS[key] = alive
            else:
                cls._STACKS.pop(key, None)

    @classmethod
    def lookup(cls, yscb_root: HostPath) -> Optional[SystemKernelPort]:
        key = yscb_root.comparison_key
        with cls._LOCK:
            cur = cls._STACKS.get(key)
            if cur is None:
                return None
            alive: list[weakref.ReferenceType[SystemKernelPort]] = []
            resolved: Optional[SystemKernelPort] = None
            for ref in cur:
                obj = ref()
                if obj is not None and not obj.is_closed:
                    alive.append(ref)
                    if not obj.is_closing and not obj.is_managed_child:
                        resolved = obj
            if alive:
                cls._STACKS[key] = alive
            else:
                cls._STACKS.pop(key, None)
            return resolved

    @classmethod
    def require(cls, yscb_root: HostPath) -> SystemKernelPort:
        found = cls.lookup(yscb_root)
        if found is not None:
            return found
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"No active WorkspaceKernel bound for '{yscb_root}'.",
        )


def _resolve_bound_kernel(owner: TaskGroup | CoreSystemModule, yscb_root: HostPath) -> SystemKernelPort:
    mod = owner if isinstance(owner, CoreSystemModule) else owner.parent_module
    if isinstance(mod, CoreSystemModule):
        bound_obj = mod.kernel
        if bound_obj is not None:
            if bound_obj.is_closed:
                raise YscbError(
                    ErrorCode.DAEMON_UNAVAILABLE,
                    f"WorkspaceKernel bound for '{yscb_root}' is already closed.",
                )
            if bound_obj.yscb_root == yscb_root:
                return bound_obj
    return _SystemKernelRegistry.require(yscb_root)


def bind_system_kernel(yscb_root: HostPath, kernel: SystemKernelPort) -> None:
    """Bind a WorkspaceKernel instance for CoreSystemModule lookups."""
    _SystemKernelRegistry.bind(yscb_root, kernel)


def unbind_system_kernel(yscb_root: HostPath, kernel: SystemKernelPort) -> None:
    """Unbind a WorkspaceKernel instance on close."""
    _SystemKernelRegistry.unbind(yscb_root, kernel)


def lookup_active_system_kernel(yscb_root: HostPath) -> Optional[SystemKernelPort]:
    """Return an active unclosed SystemKernelPort registered in-process for yscb_root, if any."""
    return _SystemKernelRegistry.lookup(yscb_root)


@dataclass(frozen=True, slots=True)
class SystemResultView(HumanRenderable, ExitCodeProvider):
    """Generic structured JSON result with crisp human CLI summary rendering and custom exit code."""

    summary: str
    data: JsonObject = field(default_factory=dict)
    code: int = 0

    def __post_init__(self) -> None:
        require_pure_str(self.summary, "SystemResultView.summary")
        require_pure_int(self.code, "SystemResultView.code", min_val=INT64_MIN, max_val=INT64_MAX)

    def render_text(self) -> str:
        if not self.data:
            return self.summary
        return f"{self.summary}\n{json.dumps(DataclassCodec.encode(self.data), indent=2, ensure_ascii=False)}"

    def exit_code(self) -> int:
        return self.code


@dataclass(frozen=True, slots=True)
class SetDynamicSpaceInput:
    """Input DTO for registering or updating a dynamic logical space via core.space.set_dynamic."""

    owner: ModuleId
    name: str
    spec: SpaceSpec


@dataclass(frozen=True, slots=True)
class ClearDynamicSpaceInput:
    """Input DTO for clearing one or all dynamic logical spaces via core.space.clear_dynamic."""

    owner: ModuleId
    name: Optional[str] = None


@dataclass(frozen=True, slots=True)
class SpaceScanInput:
    """Input DTO for triggering an incremental space scan via core.space.scan."""

    space_id: Optional[str] = None
    force: bool = False


@dataclass(frozen=True, slots=True)
class SpaceAckCursorInput:
    """CAS input DTO for advancing a space consumer cursor via core.space.ack_cursor."""

    space: str
    consumer: str
    from_gen: int
    to_gen: int
    config_hash: str
    merkle_root: str

    def __post_init__(self) -> None:
        clean_space = require_pure_str(self.space, "SpaceAckCursorInput.space", non_empty=True).strip()
        if not clean_space:
            raise ValueError("SpaceAckCursorInput.space cannot be blank whitespace")
        _ = SpaceId.parse(clean_space)
        clean_consumer = require_pure_str(self.consumer, "SpaceAckCursorInput.consumer", non_empty=True).strip()
        if not clean_consumer:
            raise ValueError("SpaceAckCursorInput.consumer cannot be blank whitespace")
        fg = require_pure_int(self.from_gen, "SpaceAckCursorInput.from_gen", min_val=0)
        tg = require_pure_int(self.to_gen, "SpaceAckCursorInput.to_gen", min_val=0)
        if fg > tg:
            raise ValueError(f"SpaceAckCursorInput.from_gen ({fg}) cannot exceed to_gen ({tg})")
        cfg_h = require_pure_str(self.config_hash, "SpaceAckCursorInput.config_hash")
        merkle = require_pure_str(self.merkle_root, "SpaceAckCursorInput.merkle_root")
        object.__setattr__(self, "space", clean_space)
        object.__setattr__(self, "consumer", clean_consumer)
        object.__setattr__(self, "config_hash", cfg_h)
        object.__setattr__(self, "merkle_root", merkle)


@dataclass(frozen=True, slots=True)
class SpaceListInput:
    """Input DTO for listing compiled logical spaces via core.space.list."""

    owner: Optional[str] = None


@dataclass(frozen=True, slots=True)
class SpaceStatusInput:
    """Input DTO for querying a logical space SQLite WAL status snapshot via core.space.status."""

    space_id: str


@dataclass(frozen=True, slots=True)
class SpaceFilesInput:
    """Input DTO for enumerating files in a logical space via core.space.files."""

    space_id: str
    pattern: Optional[str] = None


@dataclass(frozen=True, slots=True)
class SpaceDiffInput:
    """Input DTO for querying unacknowledged incremental file deltas via core.space.diff."""

    space_id: str
    consumer: str


@dataclass(frozen=True, slots=True)
class DaemonStartInput:
    console: Annotated[bool, Option(summary="Run daemon supervisor in foreground console mode", group="mode")] = False
    detach: Annotated[bool, Option(short="d", summary="Spawn detached background daemon", group="mode")] = False
    supervisor: Annotated[
        bool,
        Option(long_name="supervisor", summary="Internal detached background daemon supervisor entry", group="mode"),
    ] = False


@dataclass(frozen=True, slots=True)
class DaemonStopInput:
    force: Annotated[bool, Option(short="f", summary="Force immediate shutdown without draining")] = False


@dataclass(frozen=True, slots=True)
class DaemonReloadInput:
    modules: Annotated[tuple[str, ...], Arg(name="module", summary="Optional module IDs to reload")] = ()


@dataclass(frozen=True, slots=True)
class PackageListInput:
    remote: Annotated[bool, Option(summary="Also query remote provider index")] = False


@dataclass(frozen=True, slots=True)
class PackageInstallInput:
    specs: Annotated[tuple[str, ...], Arg(name="spec", summary="Package spec(s) <module[@constraint]>")]
    provider: Annotated[Optional[str], Option(summary="Override package provider URL or path")] = None
    force: Annotated[bool, Option(short="f", summary="Force reinstall even if version matches")] = False
    offline: Annotated[bool, Option(summary="Install strictly from local mirror/cache")] = False
    ignore_sha256: Annotated[bool, Option(summary="Skip archive SHA-256 verification")] = False


@dataclass(frozen=True, slots=True)
class PackageUpdateInput:
    modules: Annotated[tuple[str, ...], Arg(name="module", summary="Optional module ID(s) to update")] = ()
    provider: Annotated[Optional[str], Option(summary="Override package provider URL or path")] = None
    offline: Annotated[bool, Option(summary="Update strictly from local mirror")] = False
    ignore_sha256: Annotated[bool, Option(summary="Skip archive SHA-256 verification")] = False


@dataclass(frozen=True, slots=True)
class PackageRestoreInput:
    provider: Annotated[Optional[str], Option(summary="Override package provider URL or path")] = None
    force: Annotated[bool, Option(short="f", summary="Force rematerialization of all modules")] = False
    offline: Annotated[bool, Option(summary="Restore strictly from local mirror")] = False
    ignore_sha256: Annotated[bool, Option(summary="Skip archive SHA-256 verification")] = False


@dataclass(frozen=True, slots=True)
class PackageRemoveInput:
    modules: Annotated[tuple[str, ...], Arg(name="module", summary="Target module ID(s)")]
    clean: Annotated[bool, Option(summary="Also clear cache:// and storage.local://")] = False
    force: Annotated[bool, Option(short="f", summary="Force removal despite reverse dependencies")] = False


@dataclass(frozen=True, slots=True)
class PackagePurgeInput:
    modules: Annotated[tuple[str, ...], Arg(name="module", summary="Target module ID(s) to permanently purge")]
    force: Annotated[bool, Option(short="f", summary="Force purge despite reverse dependencies")] = False


@dataclass(frozen=True, slots=True)
class PackageRollbackInput:
    snapshot_id: Annotated[Optional[str], Arg(name="snapshot-id", summary="Optional snapshot ID (defaults to latest)")] = None


@dataclass(frozen=True, slots=True)
class ConfigModuleOptInput:
    module: Annotated[Optional[str], Arg(name="module", summary="Optional target module ID")] = None


@dataclass(frozen=True, slots=True)
class ConfigGetInput:
    module: Annotated[str, Arg(name="module", summary="Target module ID")]
    key: Annotated[str, Arg(name="key", summary="Dotted configuration key")]


@dataclass(frozen=True, slots=True)
class ConfigInspectInput:
    module: Annotated[str, Arg(name="module", summary="Target module ID")]


@dataclass(frozen=True, slots=True)
class ConfigSetInput:
    module: Annotated[str, Arg(name="module", summary="Target module ID")]
    key: Annotated[str, Arg(name="key", summary="Dotted configuration key")]
    value: Annotated[str, Arg(name="value", summary="JSON value or string literal")]
    local: Annotated[bool, Option(summary="Write to machine-local .config.local/ layer")] = False


@dataclass(frozen=True, slots=True)
class ConfigUnsetInput:
    module: Annotated[str, Arg(name="module", summary="Target module ID")]
    key: Annotated[str, Arg(name="key", summary="Dotted configuration key")]
    local: Annotated[bool, Option(summary="Remove from machine-local .config.local/ layer")] = False


@dataclass(frozen=True, slots=True)
class ContributesCheckInput:
    strict: Annotated[bool, Option(summary="Treat validation issues as strict errors")] = True


@dataclass(frozen=True, slots=True)
class ContributesInspectInput:
    module: Annotated[str, Arg(name="module", summary="Target module ID")]
    provenance: Annotated[bool, Option(summary="Include field-level ProvenanceGraph")] = False


@dataclass(frozen=True, slots=True)
class UriResolveInput:
    uri: Annotated[str, Arg(name="uri", summary="Semantic URI to resolve")]


@dataclass(frozen=True, slots=True)
class UriFromPathInput:
    path: Annotated[str, Arg(name="path", summary="Physical path to convert to SemanticUri")]


@dataclass(frozen=True, slots=True)
class FileLockPathOptInput:
    path: Annotated[Optional[str], Arg(name="path", summary="Optional target file path or URI")] = None


@dataclass(frozen=True, slots=True)
class FileLockPathReqInput:
    path: Annotated[str, Arg(name="path", summary="Target file path or URI")]


@dataclass(frozen=True, slots=True)
class FsSpacesInput:
    owner: Annotated[Optional[str], Option(summary="Filter spaces by owner module ID")] = None


@dataclass(frozen=True, slots=True)
class FsMatchInput:
    space_id: Annotated[str, Arg(name="space-id", summary="Target space (<owner>/<name>)")]
    target: Annotated[str, Arg(name="target", summary="Target physical path or URI")]


@dataclass(frozen=True, slots=True)
class FsLsInput:
    space_id: Annotated[str, Arg(name="space-id", summary="Target space (<owner>/<name>)")]
    pattern: Annotated[Optional[str], Option(summary="Optional glob filter pattern")] = None


@dataclass(frozen=True, slots=True)
class FsHashInput:
    space_id: Annotated[str, Arg(name="space-id", summary="Target space (<owner>/<name>)")]
    rel_path: Annotated[str, Arg(name="rel-path", summary="Relative path inside space")]


@dataclass(frozen=True, slots=True)
class FsSpaceOptInput:
    space_id: Annotated[Optional[str], Arg(name="space-id", summary="Optional space (<owner>/<name>)")] = None


@dataclass(frozen=True, slots=True)
class FsDiffInput:
    space_id: Annotated[str, Arg(name="space-id", summary="Target space (<owner>/<name>)")]
    consumer: Annotated[str, Option(summary="Consumer cursor identifier")] = "cli"


@dataclass(frozen=True, slots=True)
class FsScanInput:
    space_id: Annotated[Optional[str], Arg(name="space-id", summary="Optional space (<owner>/<name>)")] = None
    force: Annotated[bool, Option(short="f", summary="Force full content re-hash")] = False


@dataclass(frozen=True, slots=True)
class FsCleanInput:
    space_id: Annotated[Optional[str], Arg(name="space-id", summary="Optional space (<owner>/<name>)")] = None
    consumer: Annotated[Optional[str], Option(summary="Optional consumer cursor to clear")] = None


@dataclass(frozen=True, slots=True)
class EnvCheckInput:
    module: Annotated[Optional[str], Arg(name="module", summary="Optional module ID to check")] = None
    deep: Annotated[bool, Option(summary="Run subprocess deep import probe")] = False


@dataclass(frozen=True, slots=True)
class EnvRepairInput:
    module: Annotated[str, Arg(name="module", summary="Target Tier 1 module ID to repair")]
    offline: Annotated[bool, Option(summary="Repair using cached wheels only")] = False


@dataclass(frozen=True, slots=True)
class EnvGcInput:
    all_inactive: Annotated[bool, Option(long_name="all", summary="Purge all inactive environments ignoring grace window")] = False


@dataclass(frozen=True, slots=True)
class WatcherTriggerInput:
    changed_paths: tuple[str, ...] = ()
    startup_catchup: bool = False


@dataclass(frozen=True, slots=True)
class ConfigChangedTriggerInput:
    changed_paths: tuple[str, ...] = ()


def _parse_package_spec_str(raw: str, provider: Optional[str]) -> PackageRequest:
    clean = require_pure_str(raw, "package spec", non_empty=True).strip()
    is_build = False
    if "@" in clean:
        mod_part, ver_part = clean.split("@", 1)
        mid = ModuleId(mod_part.strip())
        v_clean = ver_part.strip()
        if not v_clean:
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"Missing version constraint after '@' in package spec: {raw!r}",
            )
        v_low = v_clean.lower()
        if v_low == "build":
            is_build = True
            ver_spec: Optional[str] = None
        else:
            if v_low.endswith(".build"):
                is_build = True
            ver_spec = f"=={v_clean}" if v_clean[0].isdigit() else v_clean
    else:
        mid = ModuleId(clean)
        ver_spec = None
    return PackageRequest(module_id=mid, version_spec=ver_spec, is_build=is_build, provider_override=provider)


def _normalize_cli_provider_override(
    kernel: SystemKernelPort,
    raw_provider: Optional[str],
    caller_cwd: HostPath,
) -> Optional[str]:
    if raw_provider is None:
        return None
    clean = require_pure_str(raw_provider, "provider").strip()
    if not clean or "://" in clean:
        return clean if clean else None
    raw_abs = _build_validated_raw_cli_local_path(clean, caller_cwd)
    assert_no_symlink_raw_path(raw_abs)
    resolved_hp = HostPath(raw_abs)
    cand = Path(clean)
    if cand.is_absolute() or caller_cwd == kernel.host_dir:
        return clean
    try:
        rel_inside = resolved_hp.path.relative_to(kernel.host_dir.path).as_posix()
        return f"./{rel_inside}" if rel_inside != "." else "./"
    except ValueError:
        return str(resolved_hp)


def _build_validated_raw_cli_local_path(raw: str, caller_cwd: HostPath) -> str:
    clean = require_pure_str(raw, "path", non_empty=True).strip()
    cand = Path(clean)
    if (cand.drive or cand.anchor) and not cand.is_absolute():
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Half-qualified drive or root-relative path is forbidden: {raw!r}")
    segs_to_check = cand.parts[1:] if cand.is_absolute() else cand.parts
    if any(":" in seg or "\x00" in seg for seg in segs_to_check):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Illegal stream or control syntax in path: {raw!r}")
    return str(cand) if cand.is_absolute() else os.path.join(str(caller_cwd), clean)


def _resolve_cli_path_or_uri(kernel: SystemKernelPort, raw: str, caller_cwd: HostPath) -> HostPath:
    clean = require_pure_str(raw, "path", non_empty=True).strip()
    if "://" in clean:
        uri = SemanticUri.parse(clean)
        return kernel.mount_table.resolve_physical(uri)
    raw_abs = _build_validated_raw_cli_local_path(clean, caller_cwd)
    assert_no_symlink_raw_path(raw_abs)
    return HostPath(raw_abs)


def _decorator_is_on_migrate(dec: ast.expr) -> bool:
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Name):
        return target.id == "on_migrate"
    if isinstance(target, ast.Attribute):
        return target.attr == "on_migrate"
    return False


def _module_declares_on_migrate(kernel: SystemKernelPort, module_id: ModuleId) -> bool:
    target_tid = TaskId(f"{module_id.value}.yscb_on_migrate")
    if any(s.task_id == target_tid for s in kernel.list_route_specs()):
        return True
    yscb_root = kernel.yscb_root
    mod_dir = try_resolve_contained_subpath(yscb_root, ".modules", module_id.value)
    if mod_dir is None or is_symlink_or_reparse(str(mod_dir)):
        return False

    idx_hp = try_resolve_contained_subpath(mod_dir, "tasks.index.json")
    if idx_hp is not None and not is_symlink_or_reparse(str(idx_hp)):
        try:
            raw = read_nofollow_regular_bytes(str(idx_hp), max_bytes=MAX_JSON_FILE_BYTES)
        except OSError:
            raw = None
        if raw is not None:
            try:
                doc = strict_parse_json_object(raw.decode("utf-8"))
                tasks = doc.get("tasks")
                if isinstance(tasks, list):
                    target_tid = f"{module_id.value}.yscb_on_migrate"
                    return any(isinstance(t, Mapping) and t.get("task_id") == target_tid for t in tasks)
            except (UnicodeDecodeError, ValueError):
                pass

    entry_rel = "module_entry.py"
    mf_hp = try_resolve_contained_subpath(mod_dir, "manifest.json")
    if mf_hp is not None and not is_symlink_or_reparse(str(mf_hp)):
        try:
            raw_mf = read_nofollow_regular_bytes(str(mf_hp), max_bytes=MAX_JSON_FILE_BYTES)
        except OSError:
            raw_mf = None
        if raw_mf is not None:
            try:
                mf_doc = strict_parse_json_object(raw_mf.decode("utf-8"))
                mf = parse_manifest_dict(mf_doc)
                entry_rel = mf.entry
            except (UnicodeDecodeError, ValueError, YscbError):
                entry_rel = "module_entry.py"

    cand_files: list[Path] = []
    seen_py_paths: set[str] = set()
    entry_parts = tuple(p for p in entry_rel.replace("\\", "/").split("/") if p)
    entry_hp = try_resolve_contained_subpath(mod_dir, *entry_parts) if entry_parts else None
    if entry_hp is not None and not is_symlink_or_reparse(str(entry_hp)):
        cand_files.append(entry_hp.path)
        seen_py_paths.add(entry_hp.comparison_key)

    dir_stack: list[Path] = [mod_dir.path]
    while dir_stack:
        cur_d = dir_stack.pop()
        if is_symlink_or_reparse(str(cur_d)):
            continue
        try:
            with os.scandir(str(cur_d)) as it_d:
                entries = sorted(it_d, key=lambda e: e.name)
        except OSError:
            continue
        for ent in entries:
            if ent.name.startswith(".") or ent.name == "__pycache__" or ent.is_symlink() or is_symlink_or_reparse(ent.path):
                continue
            try:
                if ent.is_dir(follow_symlinks=False):
                    dir_stack.append(Path(ent.path))
                elif ent.is_file(follow_symlinks=False) and ent.name.endswith(".py"):
                    ent_hp = HostPath(ent.path)
                    if ent_hp.comparison_key not in seen_py_paths:
                        seen_py_paths.add(ent_hp.comparison_key)
                        cand_files.append(ent_hp.path)
            except (OSError, ValueError):
                continue

    for py_p in cand_files:
        if is_symlink_or_reparse(str(py_p)):
            continue
        try:
            raw_py = read_nofollow_regular_bytes(str(py_p), max_bytes=4 * MAX_JSON_FILE_BYTES)
        except OSError:
            continue
        if raw_py is None:
            continue
        try:
            tree = ast.parse(raw_py.decode("utf-8"), filename=str(py_p))
        except (UnicodeDecodeError, SyntaxError, ValueError, RecursionError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(_decorator_is_on_migrate(d) for d in node.decorator_list):
                    return True
    return False


def _capture_core_install_fingerprint(kernel: SystemKernelPort) -> str:
    h = hashlib.sha256()
    try:
        kernel.config_store.reload()
        host_cfg = kernel.config_store.load_host_config()
        core_rec = host_cfg.installed_modules.get(CORE_MODULE_ID)
        if core_rec is not None:
            h.update(f"{core_rec.version}:{core_rec.installed_at}|".encode("utf-8"))
    except (OSError, ValueError, YscbError):
        h.update(b"no-cfg|")

    core_dir = try_resolve_contained_subpath(kernel.yscb_root, ".modules", CORE_MODULE_ID.value)
    if core_dir is not None and os.path.isdir(str(core_dir)) and not is_symlink_or_reparse(str(core_dir)):
        mf_hp = try_resolve_contained_subpath(core_dir, "manifest.json")
        if mf_hp is not None and not is_symlink_or_reparse(str(mf_hp)):
            try:
                raw_mf = read_nofollow_regular_bytes(str(mf_hp), max_bytes=MAX_JSON_FILE_BYTES)
            except OSError:
                raw_mf = None
            if raw_mf is not None:
                h.update(hashlib.sha256(raw_mf).digest())
            try:
                st = os.lstat(str(mf_hp))
                h.update(f":{st.st_mtime_ns}:{st.st_size}".encode("ascii"))
            except OSError:
                pass
    return h.hexdigest()


def _quiesce_online_daemon(kernel: SystemKernelPort) -> tuple[bool, Optional[int]]:
    ep = probe_daemon_endpoint(kernel.cache_dir, kernel.yscb_root)
    if ep is None:
        return (False, None)
    payload = DataclassCodec.encode_object(DaemonQuiesceControl(lease_sec=60.0, drain_timeout_sec=5.0))
    reply = query_daemon_control(kernel.cache_dir, kernel.yscb_root, FrameKind.CONTROL_QUIESCE, payload, timeout_ms=8000)
    if reply is not None and reply.get("ok") is True:
        raw_ep = reply.get("epoch")
        ep_int = raw_ep if isinstance(raw_ep, int) and not isinstance(raw_ep, bool) else None
        return (True, ep_int)

    time.sleep(0.05)
    ep_after = probe_daemon_endpoint(kernel.cache_dir, kernel.yscb_root)
    if ep_after is None or not is_process_alive(ep_after.pid):
        return (False, None)
    reason = str(reply.get("error") or reply.get("message") or "drain timeout") if isinstance(reply, Mapping) else "control timeout"
    raise YscbError(
        ErrorCode.DAEMON_UNAVAILABLE,
        f"Online workspace daemon (pid={ep_after.pid}) failed to enter quiesced state ({reason}); aborting package mutation.",
    )


def _resume_or_handoff_online_daemon(
    kernel: SystemKernelPort,
    quiesced: bool,
    quiesce_epoch: Optional[int],
    *,
    core_mutated: bool,
) -> None:
    if probe_daemon_endpoint(kernel.cache_dir, kernel.yscb_root) is None:
        return
    if core_mutated:
        stop_payload = DataclassCodec.encode_object(DaemonStopControl(force=False, core_handoff=True))
        reply_stop = query_daemon_control(kernel.cache_dir, kernel.yscb_root, FrameKind.CONTROL_STOP, stop_payload, timeout_ms=15000)
        if reply_stop is None or reply_stop.get("ok") is not True:
            if probe_daemon_endpoint(kernel.cache_dir, kernel.yscb_root) is not None:
                kernel.schedule_post_close_daemon_sync(
                    quiesced=quiesced,
                    quiesce_epoch=quiesce_epoch,
                    core_handoff=True,
                )
        return
    if quiesced:
        res_payload = DataclassCodec.encode_object(DaemonResumeControl(expected_epoch=quiesce_epoch))
        reply = query_daemon_control(kernel.cache_dir, kernel.yscb_root, FrameKind.CONTROL_RESUME, res_payload, timeout_ms=5000)
        if reply is None or reply.get("state") == "quiesced":
            kernel.schedule_post_close_daemon_sync(quiesced=True, quiesce_epoch=quiesce_epoch)
    else:
        reload_payload = DataclassCodec.encode_object(DaemonReloadControl(modules=()))
        reply = query_daemon_control(kernel.cache_dir, kernel.yscb_root, FrameKind.CONTROL_RELOAD, reload_payload, timeout_ms=5000)
        if reply is None or reply.get("deferred") is True:
            kernel.schedule_post_close_daemon_sync(quiesced=False, quiesce_epoch=None)


def _run_space_scan_batches(
    kernel: SystemKernelPort,
    ctx: TaskContext,
    *,
    space_id: Optional[str],
    force: bool,
) -> tuple[SpaceDiffBatch, ...]:
    changed_spaces: list[str] = []
    batches: list[SpaceDiffBatch] = []
    if space_id is not None:
        batch = kernel.space_scanner.scan(space_id, force=force, cancel_token=ctx.cancel_token)
        batches.append(batch)
        if batch.has_changes:
            changed_spaces.append(str(batch.space_id))
    else:
        for s_spec in kernel.space_registry.list_spaces():
            if s_spec.space_id.name in ("gitignore", "readonly"):
                continue
            b = kernel.space_scanner.scan(s_spec.space_id, force=force, cancel_token=ctx.cancel_token)
            batches.append(b)
            if b.has_changes:
                changed_spaces.append(str(b.space_id))
    if changed_spaces:
        ctx.emit(SPACE_UPDATED_EVENT, SpaceUpdatedEventPayload(spaces=tuple(changed_spaces)))
    return tuple(batches)


def _verify_control_plane_mutation_access(action: str) -> None:
    if is_active_cross_workspace_call():
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Cross-workspace caller is not permitted to {action}.",
        )
    caller_mod = resolve_active_caller_module()
    if caller_mod is not None and caller_mod != CORE_MODULE_ID:
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Module '{caller_mod}' is not permitted to {action}.",
        )


def _reject_cross_workspace_mutation(action: str) -> None:
    if is_active_cross_workspace_call():
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Cross-workspace caller is not permitted to {action}.",
        )


def _is_path_inside_module_owned_storage(kernel: SystemKernelPort, hp: HostPath, mod_id: ModuleId) -> bool:
    for sub in ("storage", ".storage.local", ".cache"):
        own_root = try_resolve_contained_subpath(kernel.yscb_root, sub, mod_id.value)
        if own_root is not None and own_root.path in hp.path.parents:
            return True
    return False


def _verify_file_lock_target_access(kernel: SystemKernelPort, hp: HostPath, *, action: str) -> None:
    uri = kernel.mount_table.to_uri(hp)
    if uri is None:
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Cannot {action} '{hp}': path is outside workspace managed mounts.",
        )
    caller_mod = resolve_active_caller_module()
    if caller_mod != CORE_MODULE_ID:
        if action != "inspect" and is_active_cross_workspace_call():
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Cross-workspace caller is not permitted to {action} '{hp}'.",
            )
        strict_kernel_schemes = _KERNEL_ONLY_LOCK_SCHEMES - {"yscb"}
        if uri.scheme in strict_kernel_schemes:
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Cannot {action} '{hp}': scheme '{uri.scheme}://' is reserved for kernel control plane.",
            )
        if caller_mod is None or is_active_cross_workspace_call():
            if is_active_cross_workspace_call():
                if (
                    uri.scheme in {"config", "config.local", "yscb", "yscb.host", "storage", "storage.local", "cache"}
                    or kernel.is_reserved_control_plane_path(hp, owner=None, allow_any_module_storage=False)
                ):
                    raise YscbError(
                        ErrorCode.ACCESS_DENIED,
                        f"Cross-workspace caller is not permitted to {action} '{hp}'.",
                    )
            elif kernel.is_reserved_control_plane_path(hp, owner=None, allow_any_module_storage=True):
                raise YscbError(
                    ErrorCode.ACCESS_DENIED,
                    f"Cannot {action} '{hp}': path belongs to reserved workspace control plane.",
                )
        else:
            if action != "inspect" and not _is_path_inside_module_owned_storage(kernel, hp, caller_mod):
                raise YscbError(
                    ErrorCode.ACCESS_DENIED,
                    f"Module '{caller_mod}' is only permitted to {action} files inside its own storage/cache spaces.",
                )
            first_seg = uri.rel_path.split("/", 1)[0] if uri.rel_path else ""
            if (
                uri.scheme in {"config", "config.local", "yscb", "yscb.host"}
                or (uri.scheme in {"storage", "storage.local", "cache"} and first_seg != caller_mod.value)
                or kernel.is_reserved_control_plane_path(hp, owner=caller_mod.value)
            ):
                raise YscbError(
                    ErrorCode.ACCESS_DENIED,
                    f"Module '{caller_mod}' is not permitted to {action} '{hp}'.",
                )


def _execute_package_transaction(
    kernel: SystemKernelPort,
    ctx: TaskContext,
    operation_fn: Callable[[], DeploymentReport],
    *,
    removing_modules: Sequence[ModuleId] = (),
    force_remove: bool = False,
) -> DeploymentReport:
    with kernel.installer_transaction_lock(ctx.cancel_token):
        return _execute_package_transaction_locked(
            kernel,
            ctx,
            operation_fn,
            removing_modules=removing_modules,
            force_remove=force_remove,
        )


def _execute_package_transaction_locked(
    kernel: SystemKernelPort,
    ctx: TaskContext,
    operation_fn: Callable[[], DeploymentReport],
    *,
    removing_modules: Sequence[ModuleId] = (),
    force_remove: bool = False,
) -> DeploymentReport:
    quiesced, q_epoch = _quiesce_online_daemon(kernel)
    before_core_fp = _capture_core_install_fingerprint(kernel)
    core_mutated = False
    try:
        validated_removing: tuple[ModuleId, ...] = ()
        if removing_modules:
            validated_removing = kernel.package_engine.validate_remove_targets(removing_modules, force=force_remove)
            if validated_removing:
                ctx.emit_imm(
                    MODULE_REMOVING_EVENT,
                    ModuleLifecycleEventPayload(modules=tuple(m.value for m in validated_removing)),
                    strict=False,
                )
                kernel.evict_local_modules_before_remove(validated_removing)

        with kernel.package_engine.migration_rollback_scope() as restore_pre_tx:
            try:
                report = operation_fn()
            except BaseException:
                if validated_removing:
                    kernel.reload_workspace_metadata()
                raise

            cur_mig_label = "post-deploy sync"
            try:
                after_core_fp = _capture_core_install_fingerprint(kernel)
                core_mutated = (before_core_fp != after_core_fp) or any(
                    t.module_id == CORE_MODULE_ID for t in report.transitions
                )

                kernel.ensure_installed_tasks_indices(tuple(report.installed.keys()))
                kernel.reload_workspace_metadata()
                kernel.rebuild_tasks_index_cache()

                active_ctree = resolve_active_call_tree_id()
                for trans in report.transitions:
                    if not trans.is_upgrade or trans.old_version is None or trans.new_version is None:
                        continue
                    cur_mig_label = f"'{trans.module_id}' ({trans.old_version} -> {trans.new_version})"
                    if not _module_declares_on_migrate(kernel, trans.module_id):
                        continue
                    kernel.invoke_internal_migration(
                        trans.module_id,
                        MigrationRequest(old_version=trans.old_version, new_version=trans.new_version),
                        active_ctree,
                        cancel_token=ctx.cancel_token,
                    )
            except BaseException as mig_exc:
                try:
                    restore_pre_tx()
                finally:
                    rb_core_fp = _capture_core_install_fingerprint(kernel)
                    core_mutated = before_core_fp != rb_core_fp
                    kernel.ensure_installed_tasks_indices()
                    kernel.reload_workspace_metadata()
                    kernel.rebuild_tasks_index_cache()
                    _ = kernel.sync_gitignore_and_readonly()
                if isinstance(mig_exc, YscbError) or not isinstance(mig_exc, Exception):
                    raise
                raise YscbError(
                    ErrorCode.BUSINESS_FAILURE,
                    f"Migration failed for {cur_mig_label}; rolled back transaction state: {mig_exc}",
                ) from mig_exc

        for rm_mod in dict.fromkeys((*validated_removing, *report.removed)):
            _ = kernel.clear_dynamic_spaces(rm_mod, sync=False)
        _ = kernel.sync_gitignore_and_readonly()
        active_specs = kernel.collect_active_env_specs()
        _ = kernel.env_gc.collect(active_specs, force_all=False)

        touched = tuple(str(m) for m in report.installed.keys())
        if touched:
            ctx.emit(MODULE_INSTALLED_EVENT, ModuleLifecycleEventPayload(modules=touched))
        ctx.emit(WORKSPACE_RELOADED_EVENT, Empty())
        return report
    finally:
        _resume_or_handoff_online_daemon(
            kernel,
            quiesced,
            q_epoch,
            core_mutated=core_mutated,
        )


class DaemonTaskGroup(TaskGroup):
    """Built-in daemon lifecycle control tasks."""

    @task(
        cli=("daemon", "status"),
        name="core.daemon.status",
        summary="Query live workspace daemon status without extending Idle TTL",
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.SAFE,
    )
    def daemon_status(self, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        reply = query_daemon_control(kernel.cache_dir, kernel.yscb_root, FrameKind.CONTROL_STATUS, {}, timeout_ms=2000)
        if reply is None:
            return SystemResultView("Daemon is offline.", {"online": False})
        if reply.get("ok") is not True:
            err_msg = str(reply.get("message") or reply.get("error") or "CONTROL_STATUS rejected")
            raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"Daemon status query failed: {err_msg}")
        return SystemResultView("Daemon is online.", {"online": True, "status": reply})

    @task(
        cli=("daemon", "start"),
        name="core.daemon.start",
        summary="Start the per-workspace warm daemon supervisor",
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.CONDITIONAL,
    )
    def daemon_start(self, req: DaemonStartInput, ctx: TaskContext) -> SystemResultView:
        _verify_control_plane_mutation_access("start workspace daemon")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        eff_detach = req.detach or (not req.console and not req.supervisor)
        info = kernel.spawn_or_run_daemon(console=req.console, detach=eff_detach, supervisor=req.supervisor)
        if (
            info.get("mode") == "background"
            and info.get("online") is not True
            and info.get("already_running") is not True
            and info.get("sandbox_restricted") is not True
        ):
            return SystemResultView("Daemon failed to start within startup window.", info, code=1)
        return SystemResultView("Daemon start processed.", info)

    @task(
        cli=("daemon", "stop"),
        name="core.daemon.stop",
        summary="Stop the active workspace daemon and report teardown diagnostics",
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.CONDITIONAL,
    )
    def daemon_stop(self, req: DaemonStopInput, ctx: TaskContext) -> SystemResultView:
        _verify_control_plane_mutation_access("stop workspace daemon")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        ep_before = probe_daemon_endpoint(kernel.cache_dir, kernel.yscb_root)
        payload = DataclassCodec.encode_object(DaemonStopControl(force=req.force, core_handoff=False))
        stop_timeout_ms = 5000 if req.force else 15000
        reply = query_daemon_control(
            kernel.cache_dir,
            kernel.yscb_root,
            FrameKind.CONTROL_STOP,
            payload,
            timeout_ms=stop_timeout_ms,
        )
        if reply is None:
            if ep_before is not None:
                wait_dl = time.monotonic() + 0.25
                while time.monotonic() < wait_dl:
                    ep_chk = read_daemon_endpoint_file(kernel.cache_dir, kernel.yscb_root)
                    if ep_chk is None or ep_chk.boot_id != ep_before.boot_id or not is_process_alive(ep_chk.pid):
                        break
                    time.sleep(0.02)
            ep_after = probe_daemon_endpoint(kernel.cache_dir, kernel.yscb_root)
            ep_file = read_daemon_endpoint_file(kernel.cache_dir, kernel.yscb_root) if ep_before is not None else None
            still_draining = ep_after is not None or (
                ep_before is not None
                and ep_file is not None
                and ep_file.boot_id == ep_before.boot_id
                and is_process_alive(ep_file.pid)
            )
            if still_draining:
                live_pid = (
                    ep_after.pid
                    if ep_after is not None
                    else (ep_file.pid if ep_file is not None else (ep_before.pid if ep_before is not None else 0))
                )
                raise YscbError(
                    ErrorCode.DAEMON_UNAVAILABLE,
                    f"Workspace daemon (pid={live_pid}) did not finish stopping within {stop_timeout_ms}ms; retry with --force.",
                )
            if ep_before is not None:
                return SystemResultView(
                    "Daemon stop acknowledged.",
                    {"stopped": True, "reply": {"ok": True, "teardown_diagnostics": []}},
                )
            return SystemResultView("Daemon was already stopped.", {"stopped": False})
        if reply.get("ok") is not True:
            err_msg = str(reply.get("message") or reply.get("error") or "CONTROL_STOP rejected")
            raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"Daemon stop failed: {err_msg}")
        return SystemResultView("Daemon stop acknowledged.", {"stopped": True, "reply": reply})

    @task(
        cli=("daemon", "reload"),
        name="core.daemon.reload",
        summary="Trigger warm reload of installed modules or core handoff",
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.CONDITIONAL,
    )
    def daemon_reload(self, req: DaemonReloadInput, ctx: TaskContext) -> SystemResultView:
        _verify_control_plane_mutation_access("reload workspace daemon")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        mods = tuple(ModuleId(m) for m in req.modules)
        payload = DataclassCodec.encode_object(DaemonReloadControl(modules=mods))
        reply = query_daemon_control(kernel.cache_dir, kernel.yscb_root, FrameKind.CONTROL_RELOAD, payload, timeout_ms=5000)
        if reply is None:
            return SystemResultView(
                "Daemon is offline; nothing to reload.",
                {"reloaded": False, "deferred": False, "handoff": False},
            )
        if reply.get("ok") is not True:
            err_msg = str(reply.get("message") or reply.get("error") or "CONTROL_RELOAD rejected")
            raise YscbError(ErrorCode.DAEMON_UNAVAILABLE, f"Daemon reload failed: {err_msg}")
        reloaded = reply.get("reloaded") is True
        deferred = reply.get("deferred") is True
        handoff = reply.get("handoff") is True
        if handoff:
            summary = "Daemon core handoff initiated."
        elif deferred:
            summary = "Daemon reload deferred."
        else:
            summary = "Daemon reload completed."
        return SystemResultView(
            summary,
            {"reloaded": reloaded, "deferred": deferred, "handoff": handoff, "reply": reply},
        )


class PackageTaskGroup(TaskGroup):
    """Built-in transactional offline/online package management tasks."""

    @task(
        cli="list",
        name="list",
        summary="List installed workspace modules, versions, tiers, and environment status",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def list_modules(self, req: PackageListInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        host_cfg = kernel.config_store.load_host_config()
        manifests = kernel.discover_installed_manifests()
        group_specs = ImmutableVenvPool.resolve_group_specs(tuple(manifests.values()))
        rows: list[JsonValue] = []
        prov_url = host_cfg.default_provider.strip() or CLI_DEFAULT_PROVIDER_URL
        prov_client = ProviderClient(yscb_root=kernel.yscb_root, default_provider=prov_url, host_dir=kernel.host_dir) if req.remote else None

        for mod_id in sorted(host_cfg.installed_modules.keys(), key=lambda m: (0 if m == CORE_MODULE_ID else 1, m.value)):
            rec = host_cfg.installed_modules[mod_id]
            mf = manifests.get(mod_id)
            tier = (1 if mf.is_tier1 else 0) if mf is not None else 0
            venv_ready: Optional[bool] = None
            mod_env_spec = group_specs.get(mod_id)
            if mod_env_spec is not None:
                venv_ready = kernel.env_probe.check_quick(mod_env_spec).quick_ok
            entry_doc: MutableJsonObject = {
                "module_id": mod_id.value,
                "version": str(rec.version),
                "tier": tier,
                "venv_ready": venv_ready,
                "provider": rec.provider,
            }
            if prov_client is not None:
                try:
                    r_idx = prov_client.fetch_index(mod_id, provider=rec.provider or None)
                    entry_doc["remote_versions"] = [str(v) for v in r_idx.versions]
                except (OSError, ValueError, YscbError):
                    entry_doc["remote_versions"] = []
            rows.append(entry_doc)
        return SystemResultView(f"Installed modules ({len(rows)}):", {"modules": rows})

    @task(
        cli="status",
        name="status",
        summary="Inspect overall workspace, daemon, module, and virtual environment health",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def workspace_status(self, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        host_cfg = kernel.config_store.load_host_config()
        ep = probe_daemon_endpoint(kernel.cache_dir, kernel.yscb_root)
        envs = kernel.env_pool.list_envs()
        spaces = kernel.space_registry.list_spaces()
        return SystemResultView(
            "Workspace status:",
            {
                "host_dir": str(kernel.host_dir),
                "yscb_root": str(kernel.yscb_root),
                "daemon_online": ep is not None,
                "installed_module_count": len(host_cfg.installed_modules),
                "registered_space_count": len(spaces),
                "venv_count": len(envs),
            },
        )

    @task(
        cli="reload",
        name="reload",
        summary="Rematerialize installed modules from local mirror and synchronize workspace state",
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.CONDITIONAL,
    )
    def reload_workspace(self, ctx: TaskContext) -> SystemResultView:
        _verify_control_plane_mutation_access("reload workspace modules")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        report = _execute_package_transaction(
            kernel,
            ctx,
            lambda: kernel.package_engine.reload_from_mirror(offline=True),
        )
        return SystemResultView("Workspace reloaded from mirror.", DataclassCodec.encode_object(report))

    @task(
        cli="install",
        name="install",
        summary="Install or upgrade module(s) transactionally with dependency solving and migration",
        usage_pros=("交易式安裝模組並自動建置獨立 Tier 1 虛擬環境與靜態索引",),
        usage_cons=("需通過兩段式授權或人類終端互動確認",),
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.GATED,
    )
    def install_packages(self, req: PackageInstallInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        norm_prov = _normalize_cli_provider_override(kernel, req.provider, ctx.caller_cwd)
        pkg_reqs = tuple(_parse_package_spec_str(s, norm_prov) for s in req.specs)
        report = _execute_package_transaction(
            kernel,
            ctx,
            lambda: kernel.package_engine.install(
                pkg_reqs,
                force=req.force,
                ignore_sha256=req.ignore_sha256,
                offline=req.offline,
                cancel_token=ctx.cancel_token,
            ),
        )
        return SystemResultView("Package installation completed.", DataclassCodec.encode_object(report))

    @task(
        cli="update",
        name="update",
        summary="Upgrade installed module(s) within major version bounds with core-first ordering",
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.GATED,
    )
    def update_packages(self, req: PackageUpdateInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        target_mods = tuple(ModuleId(m) for m in req.modules)
        report = _execute_package_transaction(
            kernel,
            ctx,
            lambda: kernel.package_engine.update(
                target_mods,
                provider=_normalize_cli_provider_override(kernel, req.provider, ctx.caller_cwd),
                ignore_sha256=req.ignore_sha256,
                offline=req.offline,
                cancel_token=ctx.cancel_token,
            ),
        )
        return SystemResultView("Package update completed.", DataclassCodec.encode_object(report))

    @task(
        cli="restore",
        name="restore",
        summary="Restore all modules declared in yscb.config.json including pruned same-triplet fallback",
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.GATED,
    )
    def restore_packages(self, req: PackageRestoreInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        report = _execute_package_transaction(
            kernel,
            ctx,
            lambda: kernel.package_engine.restore(
                provider=_normalize_cli_provider_override(kernel, req.provider, ctx.caller_cwd),
                force=req.force,
                ignore_sha256=req.ignore_sha256,
                offline=req.offline,
                cancel_token=ctx.cancel_token,
            ),
        )
        return SystemResultView("Workspace modules restored.", DataclassCodec.encode_object(report))

    @task(
        cli="remove",
        name="remove",
        aliases=("rm",),
        summary="Uninstall module(s) while preserving config and storage",
        usage_pros=("移除不再使用之擴充模組",),
        usage_cons=("若欲連同設定與資料永久清除，請改由人類終端執行 critical 指令 yscb purge",),
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.GATED,
    )
    def remove_packages(self, req: PackageRemoveInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        mods = tuple(ModuleId(m) for m in req.modules)
        p_level = PurgeLevel.CLEAN if req.clean else PurgeLevel.NONE
        report = _execute_package_transaction(
            kernel,
            ctx,
            lambda: kernel.package_engine.remove(mods, purge_level=p_level, force=req.force),
            removing_modules=mods,
            force_remove=req.force,
        )
        return SystemResultView("Module removal completed.", DataclassCodec.encode_object(report))

    @task(
        cli="purge",
        name="purge",
        summary="Uninstall module(s) and permanently erase all five config/cache/storage data spaces",
        usage_pros=("徹底清除廢棄模組及其全部本地與共享資料空間",),
        usage_cons=("屬不可逆高危操作，僅允許人類互動終端親自輸入確認詞執行",),
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.CRITICAL,
    )
    def purge_packages(self, req: PackagePurgeInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        mods = tuple(ModuleId(m) for m in req.modules)
        report = _execute_package_transaction(
            kernel,
            ctx,
            lambda: kernel.package_engine.remove(mods, purge_level=PurgeLevel.PURGE, force=req.force),
            removing_modules=mods,
            force_remove=req.force,
        )
        return SystemResultView("Module purge completed.", DataclassCodec.encode_object(report))

    @task(
        cli="rollback",
        name="rollback",
        summary="Restore SnapshotVault configuration and rematerialize modules from local mirror",
        usage_pros=("於升級異常時離線秒級還原工作區組態與模組版本",),
        usage_cons=("屬全域狀態回溯高危指令，僅限人類互動終端確認執行",),
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.CRITICAL,
    )
    def rollback_workspace(self, req: PackageRollbackInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        report = _execute_package_transaction(
            kernel,
            ctx,
            lambda: kernel.package_engine.rollback(req.snapshot_id),
        )
        return SystemResultView("Workspace rollback completed.", DataclassCodec.encode_object(report))


def _reject_nonfinite_json_constant(token: str) -> object:
    raise ValueError(f"Non-standard JSON constant forbidden: {token}")


def _verify_config_read_access(target_module: Optional[ModuleId]) -> None:
    caller_mod = resolve_active_caller_module()
    if is_active_cross_workspace_call():
        if caller_mod != CORE_MODULE_ID and target_module != CORE_MODULE_ID:
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                "Cross-workspace caller is only permitted to read 'core' public configuration.",
            )
        return
    if caller_mod is not None and caller_mod != CORE_MODULE_ID:
        if target_module is None or target_module not in (caller_mod, CORE_MODULE_ID):
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Module '{caller_mod}' is not permitted to read configuration for '{target_module or '*'}'.",
            )


def _verify_config_write_access(target_module: Optional[ModuleId], *, action: str) -> None:
    if is_active_cross_workspace_call():
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Cross-workspace caller is not permitted to {action} workspace configuration.",
        )
    caller_mod = resolve_active_caller_module()
    if caller_mod is not None and caller_mod != CORE_MODULE_ID and target_module is not None:
        if target_module != caller_mod:
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Module '{caller_mod}' is not permitted to {action} configuration for '{target_module}'.",
            )


def _verify_fs_clean_access(req: FsCleanInput) -> None:
    if is_active_cross_workspace_call():
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            "Cross-workspace caller is not permitted to clean logical space state.",
        )
    caller_mod = resolve_active_caller_module()
    if caller_mod is not None and caller_mod != CORE_MODULE_ID:
        if req.space_id is None:
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Module '{caller_mod}' cannot clean all workspace spaces; specify an owned space_id.",
            )
        sp_id = SpaceId.parse(req.space_id)
        if sp_id.owner != caller_mod.value or (req.consumer is not None and req.consumer != caller_mod.value):
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Module '{caller_mod}' is not permitted to clean space '{sp_id}'.",
            )


def _verify_fs_ack_cursor_access(req: SpaceAckCursorInput) -> None:
    _reject_cross_workspace_mutation("acknowledge space consumer cursor")
    caller_mod = resolve_active_caller_module()
    if caller_mod is not None and caller_mod != CORE_MODULE_ID:
        own = caller_mod.value
        consumer = req.consumer
        if not (
            consumer == own
            or consumer.startswith(f"{own}:")
            or consumer.startswith(f"{own}/")
            or consumer.startswith(f"{own}.")
        ):
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Module '{caller_mod}' is not permitted to acknowledge cursor '{consumer}'.",
            )


class ConfigContributesTaskGroup(TaskGroup):
    """Built-in 2x2 configuration matrix and Contributes 2.0 introspection tasks."""

    @task(
        cli=("config", "list"),
        name="core.config.list",
        summary="List merged 2x2 configuration values for one or all installed modules",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def config_list(self, req: ConfigModuleOptInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        if req.module is not None:
            mid = ModuleId(req.module)
            _verify_config_read_access(mid)
            return SystemResultView(f"Config for '{mid}':", {mid.value: kernel.config_store.get_module_dict(mid)})
        _verify_config_read_access(None)
        host_cfg = kernel.config_store.load_host_config()
        merged_all: MutableJsonObject = {}
        for mid in sorted(host_cfg.installed_modules.keys(), key=lambda m: m.value):
            merged_all[mid.value] = kernel.config_store.get_module_dict(mid)
        return SystemResultView("Workspace module configurations:", merged_all)

    @task(
        cli=("config", "get"),
        name="core.config.get",
        summary="Read an effective dotted configuration key for a module",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def config_get(self, req: ConfigGetInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        mid = ModuleId(req.module)
        _verify_config_read_access(mid)
        val = kernel.config_store.get_module_value(mid, req.key, default=None)
        return SystemResultView(f"{mid}.{req.key} = {json.dumps(val, ensure_ascii=False)}", {"value": val})

    @task(
        cli=("config", "inspect"),
        name="core.config.inspect",
        summary="Inspect merged configuration and packaged JSON schema for a module",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def config_inspect(self, req: ConfigInspectInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        mid = ModuleId(req.module)
        _verify_config_read_access(mid)
        merged = kernel.config_store.get_module_dict(mid)
        schema_doc: Optional[JsonObject] = None
        schema_hp = try_resolve_contained_subpath(kernel.yscb_root, ".modules", mid.value, "config.schema.json")
        if schema_hp is not None and not is_symlink_or_reparse(str(schema_hp)):
            try:
                raw_b = read_nofollow_regular_bytes(str(schema_hp), max_bytes=MAX_JSON_FILE_BYTES)
            except OSError:
                raw_b = None
            if raw_b is not None:
                try:
                    schema_doc = strict_parse_json_object(raw_b.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    schema_doc = None
        return SystemResultView(
            f"Configuration inspection for '{mid}':",
            {"module": mid.value, "effective": merged, "schema": schema_doc},
        )

    @task(
        cli=("config", "set"),
        name="core.config.set",
        summary="Validate and atomically set a module configuration key",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.CONDITIONAL,
        lock=_SPACE_MUTATION_LOCK,
    )
    def config_set(self, req: ConfigSetInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        mid = ModuleId(req.module)
        _verify_config_write_access(mid, action="modify")
        try:
            parsed_val: JsonValue = json.loads(req.value, parse_constant=_reject_nonfinite_json_constant)
        except ValueError:
            parsed_val = req.value
        schema_cls = kernel.resolve_module_config_type(mid)
        kernel.config_store.set_value(mid, req.key, parsed_val, local=req.local, schema_cls=schema_cls)
        kernel.reload_config_only((f"{mid.value}:{req.key}",))
        _ = kernel.sync_gitignore_and_readonly()
        ctx.emit(CONFIG_CHANGED_EVENT, ConfigChangedEventPayload(changed_paths=(f"{mid.value}:{req.key}",)))
        return SystemResultView(f"Updated {mid}.{req.key}.", {"module": mid.value, "key": req.key, "value": parsed_val, "local": req.local})

    @task(
        cli=("config", "unset"),
        name="core.config.unset",
        summary="Remove a configuration key from project or machine-local config layer",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.CONDITIONAL,
        lock=_SPACE_MUTATION_LOCK,
    )
    def config_unset(self, req: ConfigUnsetInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        mid = ModuleId(req.module)
        _verify_config_write_access(mid, action="unset")
        removed = kernel.config_store.unset_value(mid, req.key, local=req.local)
        if removed:
            kernel.reload_config_only((f"{mid.value}:{req.key}",))
            _ = kernel.sync_gitignore_and_readonly()
            ctx.emit(CONFIG_CHANGED_EVENT, ConfigChangedEventPayload(changed_paths=(f"{mid.value}:{req.key}",)))
        return SystemResultView(
            f"Unset {mid}.{req.key} (removed={removed}).",
            {"module": mid.value, "key": req.key, "removed": removed},
        )

    @task(
        cli=("config", "reload"),
        name="core.config.reload",
        summary="Reload workspace configuration matrix, contributes, spaces, and locale catalog",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.CONDITIONAL,
        lock=_SPACE_MUTATION_LOCK,
    )
    def config_reload(self, ctx: TaskContext) -> SystemResultView:
        _verify_config_write_access(None, action="reload")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        kernel.reload_config_only(())
        sync_res = kernel.sync_gitignore_and_readonly()
        ctx.emit(CONFIG_CHANGED_EVENT, ConfigChangedEventPayload())
        return SystemResultView("Configuration reloaded.", sync_res)

    @task(
        cli=("contributes", "list"),
        name="core.contributes.list",
        summary="List declared Contributes 2.0 extension points",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def contributes_list(self, req: ConfigModuleOptInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        target = ModuleId(req.module) if req.module is not None else None
        bundles = kernel.contributes_aggregator.list_extension_points(target)
        out: MutableJsonObject = {}
        for mid, bundle in sorted(bundles.items(), key=lambda kv: kv[0].value):
            raw_props = bundle.points_schema.get("properties")
            pt_names = sorted(k for k in raw_props.keys() if type(k) is str) if isinstance(raw_props, Mapping) else []
            out[mid.value] = pt_names
        return SystemResultView("Extension points:", out)

    @task(
        cli=("contributes", "check"),
        name="core.contributes.check",
        summary="Validate all donor contributes payloads against target _schema.json contracts",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def contributes_check(self, req: ContributesCheckInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        reports = kernel.contributes_aggregator.validate_all(strict=req.strict)
        all_ok = all(r.ok for r in reports)
        encoded = [DataclassCodec.encode_object(r) for r in reports]
        return SystemResultView(
            f"Contributes validation ok={all_ok}.",
            {"ok": all_ok, "reports": encoded},
            code=0 if all_ok else 1,
        )

    @task(
        cli=("contributes", "inspect"),
        name="core.contributes.inspect",
        summary="Inspect merged Contributes 2.0 payload and optional ProvenanceGraph for a module",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def contributes_inspect(self, req: ContributesInspectInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        mid = ModuleId(req.module)
        agg = kernel.contributes_aggregator.aggregate(mid, strict=False)
        res: MutableJsonObject = {
            "target_module": mid.value,
            "merged": agg.raw_merged,
        }
        if req.provenance:
            res["provenance"] = agg.provenance.to_json()
        return SystemResultView(f"Aggregated contributes for '{mid}':", res)


class VfsReadonlyTaskGroup(TaskGroup):
    """Built-in semantic URI routing and dual-layer readonly file-lock tasks."""

    @task(
        cli=("uri", "list"),
        name="core.uri.list",
        summary="List all mounted Scheme B semantic URI protocols and capabilities",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def uri_list(self, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        rules = [
            {
                "scheme": r.scheme,
                "target_path": str(r.target_path) if r.target_path is not None else None,
                "target_uri": str(r.target_uri) if r.target_uri is not None else None,
                "description": r.description,
            }
            for r in kernel.mount_table.list_rules()
        ]
        return SystemResultView(f"Mounted URI schemes ({len(rules)}):", {"schemes": rules})

    @task(
        cli=("uri", "resolve"),
        name="core.uri.resolve",
        summary="Resolve a semantic URI to its canonical physical HostPath",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def uri_resolve(self, req: UriResolveInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        uri = SemanticUri.parse(req.uri)
        resolved = kernel.mount_table.resolve_physical(uri)
        return SystemResultView(str(resolved), {"uri": str(uri), "path": str(resolved)})

    @task(
        cli=("uri", "to-uri"),
        name="core.uri.to_uri",
        summary="Convert a physical filesystem path to its canonical SemanticUri",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def uri_from_path(self, req: UriFromPathInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        hp = _resolve_cli_path_or_uri(kernel, req.path, ctx.caller_cwd)
        uri = kernel.mount_table.to_uri(hp)
        uri_str = str(uri) if uri is not None else None
        return SystemResultView(uri_str or "Unmapped path", {"path": str(hp), "uri": uri_str})

    @task(
        cli=("uri", "check"),
        name="core.uri.check",
        summary="Verify health of all mounted standard and contributed URI schemes",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def uri_check(self, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        entries = kernel.mount_table.check_health()
        all_ok = all(e.healthy for e in entries)
        return SystemResultView(
            f"URI mount health ok={all_ok}.",
            {"healthy": all_ok, "entries": [DataclassCodec.encode_object(e) for e in entries]},
            code=0 if all_ok else 1,
        )

    @task(
        cli=("file-lock", "status"),
        name="core.file_lock.status",
        summary="Inspect VFS readonly protection and OS readonly attribute status",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def file_lock_status(self, req: FileLockPathOptInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        if req.path is not None:
            hp = _resolve_cli_path_or_uri(kernel, req.path, ctx.caller_cwd)
            if kernel.mount_table.to_uri(hp) is None:
                raise YscbError(
                    ErrorCode.ACCESS_DENIED,
                    f"Cannot inspect '{hp}': path is outside workspace managed mounts.",
                )
            st_caller = resolve_active_caller_module()
            if (st_caller is not None and st_caller != CORE_MODULE_ID) or is_active_cross_workspace_call():
                _verify_file_lock_target_access(kernel, hp, action="inspect")
            prot = kernel.readonly_policy.is_protected(hp)
            os_ro = kernel.readonly_policy.is_os_readonly(hp)
            return SystemResultView(
                f"{hp}: protected={prot}, os_readonly={os_ro}",
                {"path": str(hp), "protected": prot, "os_readonly": os_ro},
            )
        st_caller_all = resolve_active_caller_module()
        enforce_isolation = (st_caller_all is not None and st_caller_all != CORE_MODULE_ID) or is_active_cross_workspace_call()
        ro_spaces = [
            s
            for s in kernel.space_registry.list_spaces()
            if s.space_id.name == "readonly" and s.space_id.owner != ""
        ]
        files: list[JsonValue] = []
        for sp_spec in ro_spaces:
            sp_owner = sp_spec.space_id.owner
            try:
                iter_entries = list(kernel.space_registry.iter_files(sp_spec.space_id))
            except YscbError:
                continue
            for fe in iter_entries:
                if sp_owner != "core" and kernel.is_reserved_control_plane_path(fe.abs_path, owner=sp_owner):
                    continue
                if enforce_isolation:
                    try:
                        _verify_file_lock_target_access(kernel, fe.abs_path, action="inspect")
                    except YscbError:
                        continue
                files.append(
                    {
                        "space": str(sp_spec.space_id),
                        "path": str(fe.abs_path),
                        "os_readonly": kernel.readonly_policy.is_os_readonly(fe.abs_path),
                    }
                )
        return SystemResultView(f"Readonly-protected files ({len(files)}):", {"files": files})

    @task(
        cli=("file-lock", "sync"),
        name="core.file_lock.sync",
        summary="Synchronize OS readonly attributes across all <owner>/readonly spaces",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.CONDITIONAL,
        lock=_SPACE_MUTATION_LOCK,
    )
    def file_lock_sync(self, ctx: TaskContext) -> SystemResultView:
        _verify_control_plane_mutation_access("synchronize workspace file locks")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        res = kernel.sync_gitignore_and_readonly()
        return SystemResultView("Readonly file locks synchronized.", res)

    @task(
        cli=("file-lock", "lock"),
        name="core.file_lock.lock",
        summary="Apply OS readonly lock to a specific file",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.CONDITIONAL,
        lock=_SPACE_MUTATION_LOCK,
    )
    def file_lock_lock(self, req: FileLockPathReqInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        with kernel.space_sync_guard():
            hp = _resolve_cli_path_or_uri(kernel, req.path, ctx.caller_cwd)
            _verify_file_lock_target_access(kernel, hp, action="lock")
            locked = kernel.readonly_policy.lock_file(hp)
        return SystemResultView(f"Locked {hp}: {locked}", {"path": str(hp), "locked": locked})

    @task(
        cli=("file-lock", "unlock"),
        name="core.file_lock.unlock",
        summary="Unlock OS readonly attribute on a managed file for emergency maintenance",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.GATED,
        lock=_SPACE_MUTATION_LOCK,
    )
    def file_lock_unlock(self, req: FileLockPathReqInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        with kernel.space_sync_guard():
            hp = _resolve_cli_path_or_uri(kernel, req.path, ctx.caller_cwd)
            _verify_file_lock_target_access(kernel, hp, action="unlock")
            unlocked = kernel.readonly_policy.unlock_file(hp)
        return SystemResultView(f"Unlocked {hp}: {unlocked}", {"path": str(hp), "unlocked": unlocked})


class SpaceGitignoreTaskGroup(TaskGroup):
    """Built-in logical file spaces, incremental WAL scanner, and .gitignore materializer tasks."""

    @task(
        cli=("fs", "spaces"),
        name="core.fs.spaces",
        summary="List compiled logical file spaces",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def fs_spaces(self, req: FsSpacesInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        specs = kernel.space_registry.list_spaces(owner=req.owner)
        return SystemResultView(
            f"Registered spaces ({len(specs)}):",
            {"spaces": [DataclassCodec.encode_object(s) for s in specs]},
        )

    @task(
        cli=("fs", "match"),
        name="core.fs.match",
        summary="Explain rule matching provenance for a path against a logical space",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def fs_match(self, req: FsMatchInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        sp_id = SpaceId.parse(req.space_id)
        if "://" in req.target:
            explain = kernel.space_registry.match_path(sp_id, SemanticUri.parse(req.target))
        else:
            raw_abs = _build_validated_raw_cli_local_path(req.target, ctx.caller_cwd)
            if has_symlink_raw_path(raw_abs) or is_symlink_or_reparse(raw_abs):
                if not any(s.space_id == sp_id for s in kernel.space_registry.list_spaces()):
                    raise YscbError(ErrorCode.SPACE_NOT_FOUND, f"Logical space '{sp_id}' is not registered.")
                explain = SpaceMatchExplain(
                    space_id=sp_id,
                    matched=False,
                    reason="symlink_rejected",
                )
            else:
                explain = kernel.space_registry.match_path(sp_id, HostPath(raw_abs))
        return SystemResultView(
            f"Match {explain.space_id}: matched={explain.matched} ({explain.reason})",
            DataclassCodec.encode_object(explain),
        )

    @task(
        cli=("fs", "ls"),
        name="core.fs.ls",
        summary="Enumerate matched files inside a logical space",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def fs_ls(self, req: FsLsInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        entries = list(kernel.space_registry.iter_files(req.space_id, pattern=req.pattern))
        return SystemResultView(
            f"Files in '{req.space_id}' ({len(entries)}):",
            {"files": [DataclassCodec.encode_object(e) for e in entries]},
        )

    @task(
        cli=("fs", "hash"),
        name="core.fs.hash",
        summary="Resolve and hash a single file inside a logical space",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def fs_hash(self, req: FsHashInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        target_rel = SpacePath.parse(req.rel_path)
        for entry in kernel.space_registry.iter_files(req.space_id):
            if entry.rel_path == target_rel:
                return SystemResultView(
                    f"{entry.rel_path}: {entry.content_hash}",
                    DataclassCodec.encode_object(entry),
                )
        raise YscbError(ErrorCode.SPACE_NOT_FOUND, f"File '{target_rel}' not found in space '{req.space_id}'.")

    @task(
        cli=("fs", "status"),
        name="core.fs.status",
        summary="Inspect SQLite WAL generation, Merkle root, and consumer cursors for space(s)",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def fs_status(self, req: FsSpaceOptInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        if req.space_id is not None:
            st = kernel.space_scanner.status(req.space_id)
            return SystemResultView(f"Space '{st.space_id}' gen={st.generation}:", DataclassCodec.encode_object(st))
        snaps = [
            DataclassCodec.encode_object(kernel.space_scanner.status(s.space_id))
            for s in kernel.space_registry.list_spaces()
        ]
        return SystemResultView(f"Space statuses ({len(snaps)}):", {"spaces": snaps})

    @task(
        cli=("fs", "diff"),
        name="core.fs.diff",
        summary="Read unacknowledged delta batch for a consumer cursor without advancing it",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def fs_diff(self, req: FsDiffInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        batch = kernel.space_scanner.diff(req.space_id, req.consumer)
        return SystemResultView(
            f"Diff for '{batch.space_id}' ({batch.from_gen} -> {batch.to_gen}):",
            DataclassCodec.encode_object(batch),
        )

    @task(
        cli=("fs", "scan"),
        name="core.fs.scan",
        summary="Run incremental two-stage SQLite WAL scan across one or all spaces",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.CONDITIONAL,
        lock=_SPACE_MUTATION_LOCK,
    )
    def fs_scan(self, req: FsScanInput, ctx: TaskContext) -> SystemResultView:
        _reject_cross_workspace_mutation("scan workspace spaces")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        batches = _run_space_scan_batches(kernel, ctx, space_id=req.space_id, force=req.force)
        changed_cnt = sum(1 for b in batches if b.has_changes)
        res_data: JsonObject = (
            DataclassCodec.encode_object(batches[0])
            if req.space_id is not None and len(batches) == 1
            else {"batches": [DataclassCodec.encode_object(b) for b in batches]}
        )
        return SystemResultView(f"Scan completed (changed={changed_cnt}).", res_data)

    @task(
        cli=("fs", "clean"),
        name="core.fs.clean",
        summary="Clear stored space snapshots or consumer cursors safely preserving monotonicity",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.CONDITIONAL,
        lock=_SPACE_MUTATION_LOCK,
    )
    def fs_clean(self, req: FsCleanInput, ctx: TaskContext) -> SystemResultView:
        _verify_fs_clean_access(req)
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        removed = kernel.space_scanner.clean(req.space_id, consumer_id=req.consumer)
        return SystemResultView(f"Cleaned {removed} space state rows.", {"removed_rows": removed})

    @task(
        cli=("fs", "ack-cursor"),
        name="core.space.ack_cursor",
        summary="Acknowledge a consumer cursor generation for a logical space using CAS verification",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
        lock=_SPACE_MUTATION_LOCK,
    )
    def fs_ack_cursor(self, req: SpaceAckCursorInput, ctx: TaskContext) -> SystemResultView:
        _verify_fs_ack_cursor_access(req)
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        resolved_id = SpaceId.parse(req.space)
        batch = SpaceDiffBatch(
            space_id=resolved_id,
            from_gen=SnapshotGen(req.from_gen),
            to_gen=SnapshotGen(req.to_gen),
            config_hash=req.config_hash,
            merkle_root=req.merkle_root,
        )
        acked = kernel.space_scanner.ack_cursor(resolved_id, req.consumer, batch)
        return SystemResultView(
            f"Ack cursor '{req.consumer}' for '{resolved_id}' ({req.from_gen} -> {req.to_gen}): acked={acked}.",
            {
                "space": str(resolved_id),
                "consumer": req.consumer,
                "from_gen": req.from_gen,
                "to_gen": req.to_gen,
                "acked": acked,
            },
        )

    @task(
        cli=("gitignore", "status"),
        name="core.gitignore.status",
        summary="Preview managed #<owner> ignore rule groups for project://.gitignore",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def gitignore_status(self, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        block_txt, groups = kernel.gitignore_materializer.render_managed_block()
        return SystemResultView(
            block_txt,
            {"groups": {k: list(v) for k, v in groups.items()}},
        )

    @task(
        cli=("gitignore", "sync"),
        name="core.gitignore.sync",
        summary="Synchronize the managed block inside project://.gitignore with Zero-Touch idempotency",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.CONDITIONAL,
        lock=_SPACE_MUTATION_LOCK,
    )
    def gitignore_sync(self, ctx: TaskContext) -> SystemResultView:
        _verify_control_plane_mutation_access("synchronize workspace .gitignore")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        with kernel.space_sync_guard():
            sync_res = kernel.gitignore_materializer.sync()
        return SystemResultView(
            f"Gitignore sync modified={sync_res.changed}.",
            DataclassCodec.encode_object(sync_res),
        )


class EnvTaskGroup(TaskGroup):
    """Built-in content-addressed virtual environment pool inspection, probe, repair, and GC tasks."""

    @task(
        cli=("env", "list"),
        name="core.env.list",
        summary="List content-addressed Tier 1 virtual environments in yscb.venv://",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def env_list(self, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        items: list[JsonValue] = []
        for env_dir, meta in kernel.env_pool.list_envs():
            items.append(
                {
                    "env_dir": str(env_dir),
                    "metadata": DataclassCodec.encode_object(meta) if meta is not None else None,
                }
            )
        return SystemResultView(f"Virtual environments ({len(items)}):", {"environments": items})

    @task(
        cli=("env", "check"),
        name="core.env.check",
        summary="Run quick O(1) marker check or deep subprocess import probe on Tier 1 environments",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def env_check(self, req: EnvCheckInput, ctx: TaskContext) -> SystemResultView:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        manifests = kernel.discover_installed_manifests()
        group_specs = ImmutableVenvPool.resolve_group_specs(tuple(manifests.values()))
        if req.module is not None:
            target_mid = ModuleId(req.module)
            single_mf = manifests.get(target_mid)
            if single_mf is None:
                raise YscbError(ErrorCode.TASK_NOT_FOUND, f"Installed module '{target_mid}' not found.")
            targets = [single_mf] if target_mid in group_specs else []
        else:
            targets = [mf for mf in manifests.values() if mf.id in group_specs]
        reports: list[JsonValue] = []
        all_ok = True
        for mf in targets:
            spec = group_specs.get(mf.id)
            if spec is None:
                continue
            rep = (
                kernel.env_probe.check_deep(spec)
                if req.deep
                else kernel.env_probe.check_quick(spec)
            )
            ok = rep.quick_ok and (rep.deep_import_ok is not False)
            all_ok = all_ok and ok
            reports.append({"module": mf.id.value, "report": DataclassCodec.encode_object(rep)})
        return SystemResultView(
            f"Environment check ok={all_ok}.",
            {"ok": all_ok, "reports": reports},
            code=0 if all_ok else 1,
        )

    @task(
        cli=("env", "repair"),
        name="core.env.repair",
        summary="Rebuild a corrupted Tier 1 virtual environment under hash lock",
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.CONDITIONAL,
    )
    def env_repair(self, req: EnvRepairInput, ctx: TaskContext) -> SystemResultView:
        _verify_control_plane_mutation_access("repair workspace virtual environments")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        mid = ModuleId(req.module)
        with kernel.installer_transaction_lock(ctx.cancel_token):
            manifests = kernel.discover_installed_manifests()
            group_specs = ImmutableVenvPool.resolve_group_specs(tuple(manifests.values()))
            spec = group_specs.get(mid)
            if spec is None:
                raise YscbError(ErrorCode.CONFIG_INVALID, f"Module '{mid}' is not an installed Tier 1 module.")
            quiesced, q_epoch = _quiesce_online_daemon(kernel)
            try:
                res = kernel.env_probe.repair(spec, offline=req.offline, cancel_token=ctx.cancel_token)
                affected_mods = tuple(
                    m_id for m_id, g_spec in group_specs.items() if g_spec.env_hash == spec.env_hash
                )
                kernel.ensure_installed_tasks_indices(affected_mods)
                kernel.reload_workspace_metadata()
                kernel.rebuild_tasks_index_cache()
            finally:
                _resume_or_handoff_online_daemon(kernel, quiesced, q_epoch, core_mutated=False)
        return SystemResultView(f"Repaired environment for '{mid}'.", DataclassCodec.encode_object(res))

    @task(
        cli=("env", "gc"),
        name="core.env.gc",
        summary="Garbage-collect orphan staging dirs and expired inactive virtual environments",
        dispatch_mode=DispatchMode.COLD_ONLY,
        security=SecurityTier.CONDITIONAL,
    )
    def env_gc(self, req: EnvGcInput, ctx: TaskContext) -> SystemResultView:
        _verify_control_plane_mutation_access("garbage-collect workspace virtual environments")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        with kernel.installer_transaction_lock(ctx.cancel_token):
            quiesced, q_epoch = _quiesce_online_daemon(kernel) if req.all_inactive else (False, None)
            try:
                active_specs = kernel.collect_active_env_specs()
                gc_res = kernel.env_gc.collect(active_specs, force_all=req.all_inactive)
            finally:
                if quiesced:
                    _resume_or_handoff_online_daemon(kernel, quiesced, q_epoch, core_mutated=False)
        return SystemResultView("Environment GC completed.", DataclassCodec.encode_object(gc_res))


class _CustomizedBoundTask(BoundTask):
    """Thin BoundTask wrapper binding privileged TaskMetadata."""

    def __init__(
        self,
        inner: BoundTask,
        metadata: TaskMetadata[object, object],
    ) -> None:
        self._inner = inner
        self._meta = metadata
        self._route = metadata.to_route_spec()

    @property
    def task_id(self):
        return self._meta.task_id

    @property
    def route_spec(self) -> TaskRouteSpec:
        return self._route

    @property
    def interactive_tty(self) -> bool:
        return self._meta.interactive_tty

    @property
    def metadata(self) -> TaskMetadata[object, object]:
        return self._meta

    def compute_normalized_equivalence(self, raw_input: JsonObject) -> str:
        return self._inner.compute_normalized_equivalence(raw_input)

    def map_subscription_batch(self, event_id, raw_payloads):
        return self._inner.map_subscription_batch(event_id, raw_payloads)

    def execute_encoded(self, raw_input: JsonObject, ctx: TaskContext) -> JsonValue:
        return self._inner.execute_encoded(raw_input, ctx)


class _CustomizedYscbModule(YscbModule):
    """YscbModule adapter exposing CoreSystemModule tasks with exact SelfMutationScope & INTERNAL_TRIGGER."""

    def __init__(self, inner: YscbModule, tasks: tuple[BoundTask, ...]) -> None:
        self._inner = inner
        self._tasks = tasks

    @property
    def module_id(self) -> ModuleId:
        return self._inner.module_id

    def tasks(self) -> Sequence[BoundTask]:
        return self._tasks

    def on_init(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        return self._inner.on_init(workspace_root)

    def on_start(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        return self._inner.on_start(workspace_root)


class CoreSystemModule(Module):
    """Built-in Tier 0 Core Microkernel system module."""

    id = "core"
    description = "YS-Codebase Core Microkernel"
    groups = (
        DaemonTaskGroup,
        PackageTaskGroup,
        ConfigContributesTaskGroup,
        VfsReadonlyTaskGroup,
        SpaceGitignoreTaskGroup,
        EnvTaskGroup,
    )

    def __init__(self, kernel: Optional[SystemKernelPort] = None) -> None:
        super().__init__()
        self._kernel_ref: Optional[weakref.ReferenceType[SystemKernelPort]] = (
            weakref.ref(kernel) if kernel is not None else None
        )

    @property
    def kernel(self) -> Optional[SystemKernelPort]:
        """Return the active SystemKernelPort bound to this module, if any."""
        return self._kernel_ref() if self._kernel_ref is not None else None

    @task(
        name="core.space.set_dynamic",
        summary="Register or update a dynamic logical space owned by the calling module",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
        lock=_SPACE_MUTATION_LOCK,
    )
    def set_dynamic_space(self, req: SetDynamicSpaceInput, ctx: TaskContext) -> bool:
        _reject_cross_workspace_mutation("modify dynamic spaces")
        caller_mod = resolve_active_caller_module()
        if caller_mod is None or (caller_mod != CORE_MODULE_ID and caller_mod != req.owner):
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Caller '{caller_mod}' cannot modify dynamic spaces owned by '{req.owner}'.",
            )
        if req.owner == CORE_MODULE_ID and caller_mod != CORE_MODULE_ID:
            raise YscbError(ErrorCode.ACCESS_DENIED, "External callers cannot overwrite 'core' spaces.")
        expected_sid = SpaceId(req.owner.value, req.name)
        if req.spec.space_id != expected_sid:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Dynamic space_id '{req.spec.space_id}' must match '{expected_sid}'.",
            )
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        changed = kernel.set_dynamic_space(req.owner, req.name, req.spec)
        if changed:
            ctx.emit(SPACE_REGISTRY_CHANGED_EVENT, SpaceUpdatedEventPayload(spaces=(str(expected_sid),)))
        return changed

    @task(
        name="core.space.clear_dynamic",
        summary="Remove one or all dynamic logical spaces owned by the calling module",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
        lock=_SPACE_MUTATION_LOCK,
    )
    def clear_dynamic_space(self, req: ClearDynamicSpaceInput, ctx: TaskContext) -> int:
        _reject_cross_workspace_mutation("clear dynamic spaces")
        caller_mod = resolve_active_caller_module()
        if caller_mod is None or (caller_mod != CORE_MODULE_ID and caller_mod != req.owner):
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Caller '{caller_mod}' cannot clear dynamic spaces owned by '{req.owner}'.",
            )
        if req.owner == CORE_MODULE_ID and caller_mod != CORE_MODULE_ID:
            raise YscbError(ErrorCode.ACCESS_DENIED, "External callers cannot clear 'core' spaces.")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        before_specs = {str(s.space_id): s for s in kernel.space_registry.list_spaces(owner=req.owner.value)}
        removed = kernel.clear_dynamic_spaces(req.owner, req.name)
        if removed > 0:
            if req.name is not None:
                cleared_ids: tuple[str, ...] = (str(SpaceId(req.owner.value, req.name)),)
            else:
                after_specs = {str(s.space_id): s for s in kernel.space_registry.list_spaces(owner=req.owner.value)}
                diff_ids = sorted(sid for sid, old_sp in before_specs.items() if after_specs.get(sid) != old_sp)
                cleared_ids = tuple(diff_ids) if diff_ids else tuple(sorted(before_specs.keys()))
            ctx.emit(SPACE_REGISTRY_CHANGED_EVENT, SpaceUpdatedEventPayload(spaces=cleared_ids))
        return removed

    @task(
        name="core.space.list",
        summary="List compiled logical file spaces via SDK",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def list_spaces(self, req: SpaceListInput, ctx: TaskContext) -> tuple[SpaceSpec, ...]:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        return tuple(kernel.space_registry.list_spaces(owner=req.owner))

    @task(
        name="core.space.status",
        summary="Inspect SQLite WAL generation, Merkle root, and consumer cursors for a space via SDK",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def get_space_status(self, req: SpaceStatusInput, ctx: TaskContext) -> SpaceStatusSnapshot:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        return kernel.space_scanner.status(req.space_id)

    @task(
        name="core.space.files",
        summary="Enumerate matched files inside a logical space via SDK",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def list_space_files(self, req: SpaceFilesInput, ctx: TaskContext) -> tuple[SpaceFileEntry, ...]:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        return tuple(kernel.space_registry.iter_files(req.space_id, pattern=req.pattern))

    @task(
        name="core.space.diff",
        summary="Read unacknowledged delta batch for a consumer cursor via SDK",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
    )
    def diff_space(self, req: SpaceDiffInput, ctx: TaskContext) -> SpaceDiffBatch:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        return kernel.space_scanner.diff(req.space_id, req.consumer)

    @task(
        name="core.space.scan",
        summary="Run incremental two-stage SQLite WAL scan via SDK with single-point space mutex",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
        lock=_SPACE_MUTATION_LOCK,
    )
    def scan_space(self, req: SpaceScanInput, ctx: TaskContext) -> tuple[SpaceDiffBatch, ...]:
        _reject_cross_workspace_mutation("scan workspace spaces")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        return _run_space_scan_batches(kernel, ctx, space_id=req.space_id, force=req.force)

    @task(
        name="watcher",
        summary="Internal daemon watcher callback patching SpaceScanner and emitting core.space_updated",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
        lock=_SPACE_MUTATION_LOCK,
    )
    def on_watcher_dirty(self, req: WatcherTriggerInput, ctx: TaskContext) -> None:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        changed_ids: list[str] = []
        if req.startup_catchup:
            for spec in kernel.space_registry.list_spaces():
                if not spec.watch or spec.space_id.name in ("gitignore", "readonly"):
                    continue
                batch = kernel.space_scanner.scan(spec.space_id, force=False, cancel_token=ctx.cancel_token)
                if batch.has_changes:
                    changed_ids.append(str(batch.space_id))
        elif req.changed_paths:
            dirty_hps: set[HostPath] = set()
            saw_symlink_or_unresolvable = False
            for raw_p in req.changed_paths:
                if not raw_p:
                    continue
                try:
                    if is_symlink_or_reparse(raw_p) or has_symlink_raw_path(raw_p):
                        saw_symlink_or_unresolvable = True
                        continue
                except OSError:
                    saw_symlink_or_unresolvable = True
                    continue
                try:
                    dirty_hps.add(HostPath(raw_p))
                except (OSError, RuntimeError):
                    saw_symlink_or_unresolvable = True
                except (ValueError, YscbError):
                    continue
            seen_changed: set[str] = set()
            if dirty_hps:
                for batch in kernel.space_scanner.patch_paths(frozenset(dirty_hps), cancel_token=ctx.cancel_token):
                    if batch.has_changes:
                        sid_s = str(batch.space_id)
                        if sid_s not in seen_changed:
                            seen_changed.add(sid_s)
                            changed_ids.append(sid_s)
            if saw_symlink_or_unresolvable:
                for spec in kernel.space_registry.list_spaces():
                    if not spec.watch or spec.space_id.name in ("gitignore", "readonly"):
                        continue
                    batch = kernel.space_scanner.scan(spec.space_id, force=False, cancel_token=ctx.cancel_token)
                    if batch.has_changes:
                        sid_s = str(batch.space_id)
                        if sid_s not in seen_changed:
                            seen_changed.add(sid_s)
                            changed_ids.append(sid_s)
        if changed_ids:
            ctx.emit(SPACE_UPDATED_EVENT, SpaceUpdatedEventPayload(spaces=tuple(changed_ids)))

    @task(
        name="core.config.on_changed",
        summary="Internal daemon config watcher callback reloading metadata, spaces, readonly, and gitignore",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
        lock=_SPACE_MUTATION_LOCK,
    )
    def on_config_changed(self, req: ConfigChangedTriggerInput, ctx: TaskContext) -> None:
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        if kernel.is_daemon_quiesced():
            return
        if kernel.has_running_daemon():
            _ = kernel.sync_gitignore_and_readonly()
            return
        changed = kernel.reload_config_only(req.changed_paths)
        _ = kernel.sync_gitignore_and_readonly()
        if changed:
            ctx.emit(CONFIG_CHANGED_EVENT, ConfigChangedEventPayload(changed_paths=tuple(str(p) for p in req.changed_paths)))

    @task(
        name="core.space.on_dynamic_mutated",
        summary="Refresh online daemon dynamic space registry from SQLite without restarting modules or core",
        dispatch_mode=DispatchMode.HYBRID,
        security=SecurityTier.SAFE,
        lock=_SPACE_MUTATION_LOCK,
    )
    def on_dynamic_space_mutated(self, ctx: TaskContext) -> tuple[str, ...]:
        _reject_cross_workspace_mutation("refresh dynamic spaces")
        kernel = _resolve_bound_kernel(self, ctx.workspace_root)
        diff_spaces = kernel.refresh_dynamic_spaces_only()
        if diff_spaces:
            ctx.emit(SPACE_REGISTRY_CHANGED_EVENT, SpaceUpdatedEventPayload(spaces=diff_spaces))
        return diff_spaces

    def to_yscb_module(self) -> YscbModule:
        base_mod = super().to_yscb_module()
        customized: list[BoundTask] = []
        for bt in base_mod.tasks():
            tid_s = bt.task_id.value
            meta: TaskMetadata[object, object] = bt.metadata
            mut_scope = _MUTATION_SCOPE_BY_TASK.get(tid_s)
            if mut_scope is not None:
                meta = replace(meta, mutation_scope=mut_scope)
            if tid_s in _INTERNAL_TRIGGER_TASKS:
                meta = replace(meta, exposure=TaskExposure.INTERNAL_TRIGGER, cli=None)
            if meta is not bt.metadata:
                customized.append(_CustomizedBoundTask(bt, meta))
            else:
                customized.append(bt)
        wrapped = _CustomizedYscbModule(base_mod, tuple(customized))
        register_compiled_module_surface_meta(
            wrapped,
            aliases=tuple(type(self).aliases),
            description=type(self).description,
        )
        return wrapped
