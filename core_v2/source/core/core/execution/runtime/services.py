"""Runtime module service bundle, isolated default fallbacks, and workspace-backed service factory."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import threading
from typing import Callable, ClassVar, Final, Iterator, Mapping, Optional

from core.execution.runtime.contracts import CORE_MODULE_ID, ModuleRuntimeServices
from core.filesystem.fs import (
    has_symlink_raw_path,
    is_symlink_or_reparse,
    try_resolve_contained_subpath,
)
from core.filesystem.space import HashPolicy, SpaceRegistry, SpaceSpec
from core.filesystem.vfs import (
    MemoryVfsProvider,
    MountRule,
    PhysicalDirectoryProvider,
    ReadonlyPolicy,
    ScopedVfs,
    UriMountTable,
    VfsCapabilities,
    VfsHub,
    VfsProvider,
    build_standard_mount_rules,
)
from core.foundation import (
    DataclassCodec,
    ErrorCode,
    HostPath,
    JsonObject,
    LocaleCatalog,
    LogLevel,
    LogRecord,
    LogRotator,
    ModuleId,
    SemanticUri,
    StructuredLogger,
    YscbError,
    clone_strict_json_object,
    read_public_env_value,
    require_pure_str,
)
from core.metadata.config import ConfigStore
from core.metadata.contributes import (
    AggregatedContributes,
    ContributesAggregator,
    ProvenanceGraph,
    ResolvedProjectRoot,
    core_builtin_extension_points,
    discover_installed_manifests_map,
    extract_parsed_space_contributions,
    extract_validated_uri_schemes,
    hash_workspace_surface_trees,
    is_control_plane_reserved_path,
    is_permitted_contributed_mount_root,
    bind_locale_getter_owner,
    lookup_cold_workspace_dialect,
    lookup_locale_getter_dialect,
    parse_locale_chain_tokens,
    resolve_workspace_project_root,
    scan_workspace_locale_dictionaries,
)

HOST_DIALECT_ENV_KEY: Final[str] = "_YSCB_HOST_DIALECT"
_RESERVED_NON_MODULE_IDS: Final[frozenset[str]] = frozenset({"locks", "wheels", "daemon", "project"})
_MEM_RW_CAPS: Final[VfsCapabilities] = (
    VfsCapabilities.READABLE | VfsCapabilities.WRITABLE | VfsCapabilities.ENUMERABLE
)
_MEM_RO_CAPS: Final[VfsCapabilities] = VfsCapabilities.READABLE | VfsCapabilities.ENUMERABLE
_LOCAL_STORAGE_CAPS: Final[VfsCapabilities] = (
    VfsCapabilities.READABLE
    | VfsCapabilities.WRITABLE
    | VfsCapabilities.PERSISTENT
    | VfsCapabilities.ENUMERABLE
    | VfsCapabilities.PHYSICAL_PATH
)


class _HostDialectRegistry:
    _LOCK: ClassVar[threading.RLock] = threading.RLock()
    _DIALECTS: ClassVar[dict[str, str]] = {}

    @classmethod
    def bind(cls, yscb_root: HostPath, dialect: Optional[str]) -> None:
        key = yscb_root.comparison_key
        clean = dialect.strip() if isinstance(dialect, str) and dialect.strip() else None
        with cls._LOCK:
            if clean is None:
                cls._DIALECTS.pop(key, None)
            else:
                cls._DIALECTS[key] = clean

    @classmethod
    def unbind(cls, yscb_root: HostPath) -> None:
        with cls._LOCK:
            cls._DIALECTS.pop(yscb_root.comparison_key, None)

    @classmethod
    def resolve(cls, yscb_root: HostPath) -> Optional[str]:
        with cls._LOCK:
            return cls._DIALECTS.get(yscb_root.comparison_key)


def register_workspace_host_dialect(yscb_root: HostPath, dialect: Optional[str]) -> None:
    """Internal runtime hook recording the detected AI host dialect for a workspace."""
    _HostDialectRegistry.bind(yscb_root, dialect)


def unregister_workspace_host_dialect(yscb_root: HostPath) -> None:
    """Internal runtime hook clearing the recorded host dialect for a workspace."""
    _HostDialectRegistry.unbind(yscb_root)


def resolve_explicit_workspace_host_dialect(yscb_root: HostPath) -> Optional[str]:
    """Internal runtime hook retrieving only explicitly bound workspace host dialect, if any."""
    return _HostDialectRegistry.resolve(yscb_root)


def resolve_workspace_host_dialect(yscb_root: HostPath) -> Optional[str]:
    """Internal runtime hook retrieving any recorded AI host dialect for a workspace."""
    return _HostDialectRegistry.resolve(yscb_root) or lookup_cold_workspace_dialect(yscb_root)


class _ActiveServicesTls(threading.local):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[ModuleRuntimeServices] = []
        self.invocations: list[tuple[Optional[ModuleId], Optional[str]]] = []
        self.step_env_locales: list[Optional[str]] = []


class _ActiveServicesHolder:
    _TLS: ClassVar[Optional[_ActiveServicesTls]] = None
    _LOCK: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def _tls(cls) -> _ActiveServicesTls:
        if cls._TLS is None:
            with cls._LOCK:
                if cls._TLS is None:
                    cls._TLS = _ActiveServicesTls()
        return cls._TLS

    @classmethod
    def invocations(cls) -> list[tuple[Optional[ModuleId], Optional[str]]]:
        return cls._tls().invocations

    @classmethod
    def stack(cls) -> list[ModuleRuntimeServices]:
        return cls._tls().stack

    @classmethod
    def step_env_locales(cls) -> list[Optional[str]]:
        return cls._tls().step_env_locales


class _NullStructuredLogger:
    """Side-effect-free StructuredLogger used by isolated default/in-memory module environments."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = require_pure_str(name, "logger name", non_empty=True)

    def log(self, level: LogLevel, message: str, *, fields: Optional[JsonObject] = None) -> None:
        if not isinstance(level, LogLevel):
            raise ValueError(f"StructuredLogger.log level must be LogLevel, got {level!r}")
        require_pure_str(message, "StructuredLogger.log message")
        if fields is not None:
            _ = clone_strict_json_object(fields, label="StructuredLogger.log fields")

    def debug(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.DEBUG, message, fields=fields)

    def info(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.INFO, message, fields=fields)

    def warning(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.WARNING, message, fields=fields)

    def error(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.ERROR, message, fields=fields)


class _RotatorStructuredLogger:
    """Workspace-backed StructuredLogger writing bounded JSONL records via LogRotator."""

    __slots__ = ("_name", "_rotator")

    def __init__(self, name: str, log_path: HostPath) -> None:
        self._name = require_pure_str(name, "logger name", non_empty=True)
        self._rotator = LogRotator(log_path, max_bytes=524288, max_history_files=3)

    def log(self, level: LogLevel, message: str, *, fields: Optional[JsonObject] = None) -> None:
        ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        rec = LogRecord(
            ts_utc=ts_utc,
            level=level,
            logger_name=self._name,
            message=message,
            fields=fields if fields is not None else {},
        )
        self._rotator.append_jsonl(DataclassCodec.encode_object(rec))

    def debug(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.DEBUG, message, fields=fields)

    def info(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.INFO, message, fields=fields)

    def warning(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.WARNING, message, fields=fields)

    def error(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.ERROR, message, fields=fields)


def _can_mount_physical_storage_local(workspace_root: HostPath) -> bool:
    raw_ws = str(workspace_root)
    if has_symlink_raw_path(raw_ws) or is_symlink_or_reparse(raw_ws):
        return False
    return workspace_root.path.is_dir() or workspace_root.path.parent.is_dir()


def _build_default_scoped_vfs(workspace_root: HostPath, module_id: ModuleId) -> ScopedVfs:
    providers: dict[str, VfsProvider] = {
        "project": MemoryVfsProvider("project", base_capabilities=_MEM_RW_CAPS),
        "config": MemoryVfsProvider("config", base_capabilities=_MEM_RO_CAPS),
        "config.local": MemoryVfsProvider("config.local", base_capabilities=_MEM_RW_CAPS),
        "cache": MemoryVfsProvider("cache", base_capabilities=_MEM_RW_CAPS),
        "storage": MemoryVfsProvider("storage", base_capabilities=_MEM_RW_CAPS),
        "temp": MemoryVfsProvider("temp", base_capabilities=_MEM_RW_CAPS),
    }
    if _can_mount_physical_storage_local(workspace_root):
        storage_local_hp = try_resolve_contained_subpath(workspace_root, ".storage.local")
        if storage_local_hp is not None:
            providers["storage.local"] = PhysicalDirectoryProvider(
                "storage.local",
                storage_local_hp,
                base_capabilities=_LOCAL_STORAGE_CAPS,
            )
        else:
            providers["storage.local"] = MemoryVfsProvider("storage.local", base_capabilities=_MEM_RW_CAPS)
    else:
        providers["storage.local"] = MemoryVfsProvider("storage.local", base_capabilities=_MEM_RW_CAPS)
    table = UriMountTable((), providers=providers)
    return VfsHub(table).for_module(module_id)


def _safe_config_module_id(module_id: ModuleId) -> ModuleId:
    if module_id.value in _RESERVED_NON_MODULE_IDS:
        return ModuleId(f"mod-{module_id.value}")
    return module_id


def build_default_module_services(workspace_root: HostPath, module_id: ModuleId) -> ModuleRuntimeServices:
    """Build isolated side-effect-free default runtime services for unit tests and in-memory modules."""
    if not isinstance(workspace_root, HostPath):
        raise TypeError(f"workspace_root must be HostPath, got {type(workspace_root).__name__}")
    if not isinstance(module_id, ModuleId):
        raise TypeError(f"module_id must be ModuleId, got {type(module_id).__name__}")
    scoped_vfs = _build_default_scoped_vfs(workspace_root, module_id)
    logger: StructuredLogger = _NullStructuredLogger(module_id.value)
    locale = LocaleCatalog({})
    cfg_store = ConfigStore(host_dir=workspace_root, yscb_root=workspace_root)
    cfg_lock = threading.RLock()
    eff_cfg_mod = _safe_config_module_id(module_id)
    empty_contrib = AggregatedContributes(
        target_module=module_id,
        raw_merged={},
        provenance=ProvenanceGraph({}),
    )

    def _load_cfg(config_cls: type[object]) -> object:
        with cfg_lock:
            cfg_store.reload()
            return cfg_store.load_typed(eff_cfg_mod, config_cls)

    def _load_contrib() -> AggregatedContributes:
        return empty_contrib

    return ModuleRuntimeServices(
        module_id=module_id,
        workspace_root=workspace_root,
        vfs=scoped_vfs,
        logger=logger,
        locale=locale,
        config_loader=_load_cfg,
        contributes_loader=_load_contrib,
    )


def _extract_contributed_mount_rules(
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


def _extract_contributed_space_specs(core_agg: AggregatedContributes) -> tuple[SpaceSpec, ...]:
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


def _create_workspace_services_factory_impl(
    host_dir: HostPath,
    yscb_root: HostPath,
    *,
    config_store: Optional[ConfigStore] = None,
    contributes_aggregator: Optional[ContributesAggregator] = None,
    vfs_hub: Optional[VfsHub] = None,
    locale_getter: Optional[Callable[[], LocaleCatalog]] = None,
    dialect: Optional[str] = None,
    is_hot_container: bool = False,
) -> Callable[[ModuleId], ModuleRuntimeServices]:
    if not isinstance(host_dir, HostPath) or not isinstance(yscb_root, HostPath):
        raise TypeError("host_dir and yscb_root must be HostPath instances")
    @dataclass(frozen=True, slots=True)
    class _CachedSurfaceHubAgg:
        base_fp: str
        agg: ContributesAggregator
        hub: VfsHub

    lock = threading.RLock()
    cache: dict[tuple[ModuleId, str], ModuleRuntimeServices] = {}
    loggers_by_module: dict[tuple[ModuleId, str], StructuredLogger] = {}
    active_base_fp: list[str] = [""]
    cached_hub_agg: list[_CachedSurfaceHubAgg] = []
    cached_locale_dicts: list[tuple[str, dict[ModuleId, dict[str, dict[str, str]]]]] = []
    pinned_inj_refs: list[object] = []
    owns_config_store = config_store is None
    eff_cfg = config_store if config_store is not None else ConfigStore(host_dir=host_dir, yscb_root=yscb_root)

    def _compute_modules_surface_fingerprint() -> str:
        h = hashlib.sha256()
        hash_workspace_surface_trees(
            h.update,
            yscb_root,
            include_space_db=True,
            include_tasks_index=False,
        )
        return h.hexdigest()[:24]

    @dataclass(frozen=True, slots=True)
    class _ResolvedWorkspaceBundle:
        hub: VfsHub
        agg: ContributesAggregator
        loc: LocaleCatalog

    def _resolve_hub_and_agg(
        cfg_fp: str,
        eff_raw_env_loc: Optional[str],
        eff_dialect: Optional[str],
        pre_loc: Optional[LocaleCatalog] = None,
    ) -> _ResolvedWorkspaceBundle:
        if contributes_aggregator is None and vfs_hub is None and cached_hub_agg and cached_hub_agg[0].base_fp == cfg_fp:
            agg = cached_hub_agg[0].agg
            hub = cached_hub_agg[0].hub
        else:
            if contributes_aggregator is not None:
                agg = contributes_aggregator
            else:
                manifests_map = discover_installed_manifests_map(yscb_root)
                agg = ContributesAggregator(
                    yscb_root=yscb_root,
                    manifests=tuple(manifests_map.values()),
                    live_specs={CORE_MODULE_ID: core_builtin_extension_points()},
                )
            if vfs_hub is not None:
                hub = vfs_hub
            else:
                try:
                    core_agg = agg.aggregate(CORE_MODULE_ID, strict=False)
                except YscbError:
                    core_agg = AggregatedContributes(
                        target_module=CORE_MODULE_ID,
                        raw_merged={},
                        provenance=ProvenanceGraph({}),
                    )
                proj_info = resolve_workspace_project_root(host_dir, eff_cfg)
                extra_rules = _extract_contributed_mount_rules(host_dir, yscb_root, proj_info, eff_cfg, core_agg)
                std_rules = build_standard_mount_rules(
                    host_dir,
                    yscb_root,
                    project_root=proj_info.project_root,
                    extra_rules=extra_rules,
                )
                ro_policy = ReadonlyPolicy()
                mount_tbl = UriMountTable(std_rules)
                probe_hub = VfsHub(mount_tbl, readonly_policy=ro_policy)
                dyn_db_hp = try_resolve_contained_subpath(yscb_root, ".storage.local", "core", "space", "state.db")
                static_sp = _extract_contributed_space_specs(core_agg)

                def _reserved_for_owner(cand_hp: HostPath, owner_s: str) -> bool:
                    return is_control_plane_reserved_path(
                        cand_hp,
                        yscb_root=yscb_root,
                        host_dir=host_dir,
                        project_root=proj_info.project_root,
                        project_root_disabled=proj_info.disabled,
                        owner=owner_s,
                    )

                ro_policy.update_matcher(
                    SpaceRegistry.build_stateless_readonly_matcher(
                        probe_hub.for_kernel(),
                        static_specs=static_sp,
                        dynamic_db_path=dyn_db_hp,
                        reserved_filter=_reserved_for_owner,
                    )
                )
                hub = probe_hub
            if contributes_aggregator is None and vfs_hub is None:
                cached_hub_agg[:] = [_CachedSurfaceHubAgg(base_fp=cfg_fp, agg=agg, hub=hub)]

        if pre_loc is not None:
            loc = pre_loc
        elif locale_getter is not None and resolve_active_step_env_locale() is None:
            loc = locale_getter()
        else:
            if cached_locale_dicts and cached_locale_dicts[0][0] == cfg_fp:
                loc_dicts = cached_locale_dicts[0][1]
            else:
                loc_dicts = scan_workspace_locale_dictionaries(yscb_root, contributes_aggregator=agg)
                cached_locale_dicts[:] = [(cfg_fp, loc_dicts)]
            chain = parse_locale_chain_tokens(eff_raw_env_loc, eff_cfg, dialect=eff_dialect)
            loc = LocaleCatalog(loc_dicts, default_chain=chain)
        return _ResolvedWorkspaceBundle(hub=hub, agg=agg, loc=loc)

    def _for_module(module_id: ModuleId) -> ModuleRuntimeServices:
        if not isinstance(module_id, ModuleId):
            raise TypeError(f"module_id must be ModuleId, got {type(module_id).__name__}")
        step_loc = resolve_active_step_env_locale()
        eff_raw_env_loc = (
            step_loc
            if step_loc is not None
            else (None if (is_hot_container or locale_getter is not None) else read_public_env_value("YSCB_LOCALE"))
        )
        step_has_dialect = bool(
            step_loc is not None
            and any(tok.strip().lower().startswith("nouns-") for tok in step_loc.split(",") if tok.strip())
        )
        bound_dial = lookup_locale_getter_dialect(locale_getter) if locale_getter is not None else None
        if step_has_dialect or is_hot_container or (bound_dial is not None and bound_dial.is_daemon_host):
            eff_dial: Optional[str] = None
        elif bound_dial is not None:
            eff_dial = bound_dial.dialect
        elif locale_getter is not None:
            eff_dial = None
        else:
            eff_dial = resolve_workspace_host_dialect(yscb_root) or dialect
        injected_mode = (
            not owns_config_store
            and contributes_aggregator is not None
            and vfs_hub is not None
            and locale_getter is not None
        )
        with lock:
            direct_loc: Optional[LocaleCatalog] = None
            if injected_mode and locale_getter is not None:
                cur_loc = locale_getter()
                base_fp = f"inj:{id(contributes_aggregator)}:{id(vfs_hub)}:{id(cur_loc)}:{eff_cfg.fingerprint()}"
                if step_loc is None:
                    fp = f"{base_fp}:default"
                    direct_loc = cur_loc
                else:
                    fp = f"{base_fp}:step:{eff_dial or ''}:{eff_raw_env_loc or ''}"
            else:
                if owns_config_store:
                    eff_cfg.reload()
                cfg_fp = eff_cfg.fingerprint()
                mods_fp = _compute_modules_surface_fingerprint()
                base_fp = f"{cfg_fp}:{mods_fp}"
                fp = f"{base_fp}:{eff_dial or ''}:{eff_raw_env_loc or ''}"
            if active_base_fp[0] != base_fp:
                cache.clear()
                active_base_fp[0] = base_fp
                if injected_mode and locale_getter is not None:
                    pinned_inj_refs[:] = [contributes_aggregator, vfs_hub, locale_getter()]
                else:
                    pinned_inj_refs.clear()
            cached = cache.get((module_id, fp))
            if cached is not None:
                return cached
            bundle = _resolve_hub_and_agg(base_fp, eff_raw_env_loc, eff_dial, pre_loc=direct_loc)
            hub, agg, loc = bundle.hub, bundle.agg, bundle.loc
            scoped_vfs = hub.for_module(module_id)
            logs_hp = try_resolve_contained_subpath(yscb_root, ".cache", "logs", f"{module_id.value}.jsonl")
            if logs_hp is not None:
                log_key = (module_id, logs_hp.comparison_key)
                existing_logger = loggers_by_module.get(log_key)
                if existing_logger is None:
                    existing_logger = _RotatorStructuredLogger(module_id.value, logs_hp)
                    loggers_by_module[log_key] = existing_logger
                logger: StructuredLogger = existing_logger
            else:
                logger = _NullStructuredLogger(module_id.value)
            eff_cfg_mod = _safe_config_module_id(module_id)

            def _load_cfg(config_cls: type[object], _m: ModuleId = eff_cfg_mod) -> object:
                if owns_config_store:
                    with lock:
                        eff_cfg.reload()
                        return eff_cfg.load_typed(_m, config_cls)
                return eff_cfg.load_typed(_m, config_cls)

            def _load_contrib(_m: ModuleId = module_id, _agg: ContributesAggregator = agg) -> AggregatedContributes:
                return _agg.aggregate(_m)

            svc = ModuleRuntimeServices(
                module_id=module_id,
                workspace_root=yscb_root,
                vfs=scoped_vfs,
                logger=logger,
                locale=loc,
                config_loader=_load_cfg,
                contributes_loader=_load_contrib,
            )
            if len(cache) >= 64:
                cache.pop(next(iter(cache)), None)
            cache[(module_id, fp)] = svc
            return svc

    return _for_module


def build_workspace_module_services_factory(
    host_dir: HostPath,
    yscb_root: HostPath,
    *,
    config_store: Optional[ConfigStore] = None,
    contributes_aggregator: Optional[ContributesAggregator] = None,
    vfs_hub: Optional[VfsHub] = None,
    locale_getter: Optional[Callable[[], LocaleCatalog]] = None,
) -> Callable[[ModuleId], ModuleRuntimeServices]:
    """Create a thread-safe per-module runtime service factory backed by a live workspace."""
    fac = _create_workspace_services_factory_impl(
        host_dir,
        yscb_root,
        config_store=config_store,
        contributes_aggregator=contributes_aggregator,
        vfs_hub=vfs_hub,
        locale_getter=locale_getter,
    )
    if locale_getter is not None:
        bind_locale_getter_owner(fac, locale_getter)
    return fac


def build_worker_module_services_factory(
    host_dir: HostPath,
    yscb_root: HostPath,
    *,
    dialect: Optional[str] = None,
    is_hot_container: bool = False,
) -> Callable[[ModuleId], ModuleRuntimeServices]:
    """Internal Tier 1 worker service factory wiring workspace configuration, VFS, and host dialect."""
    return _create_workspace_services_factory_impl(
        host_dir,
        yscb_root,
        dialect=(None if is_hot_container else dialect),
        is_hot_container=is_hot_container,
    )


@contextmanager
def active_module_services_scope(services: ModuleRuntimeServices) -> Iterator[None]:
    """Bind ModuleRuntimeServices onto thread-local state during module lifecycle hooks."""
    _ActiveServicesHolder.stack().append(services)
    try:
        yield
    finally:
        _ActiveServicesHolder.stack().pop()


def resolve_active_module_services(workspace_root: HostPath, module_id: ModuleId) -> ModuleRuntimeServices:
    """Return active hook-scoped ModuleRuntimeServices if matching, else safe isolated defaults."""
    for candidate in reversed(_ActiveServicesHolder.stack()):
        if candidate.module_id == module_id and candidate.workspace_root == workspace_root:
            return candidate
    return build_default_module_services(workspace_root, module_id)


@contextmanager
def active_step_caller_env_scope(caller_env: Mapping[str, str]) -> Iterator[None]:
    """Bind per-step caller_env YSCB_LOCALE onto thread-local state across Tier 0 and Tier 1 execution."""
    raw_loc = caller_env.get("YSCB_LOCALE")
    clean_loc = raw_loc.strip() if type(raw_loc) is str and raw_loc.strip() else None
    _ActiveServicesHolder.step_env_locales().append(clean_loc)
    try:
        yield
    finally:
        _ActiveServicesHolder.step_env_locales().pop()


def resolve_active_step_env_locale() -> Optional[str]:
    """Return the active step's sanitized caller_env YSCB_LOCALE override, if present."""
    stack = _ActiveServicesHolder.step_env_locales()
    return stack[-1] if stack else None


@contextmanager
def active_step_invocation_scope(
    caller_module: Optional[ModuleId],
    call_tree_id: Optional[str],
) -> Iterator[None]:
    """Bind caller module identity and call_tree_id onto thread-local state during Tier 0 step execution."""
    _ActiveServicesHolder.invocations().append((caller_module, call_tree_id))
    try:
        yield
    finally:
        _ActiveServicesHolder.invocations().pop()


def resolve_active_caller_module() -> Optional[ModuleId]:
    """Return the immediate parent caller ModuleId for the active Tier 0 step, if nested."""
    inv = _ActiveServicesHolder.invocations()
    return inv[-1][0] if inv else None


def resolve_active_call_tree_id() -> Optional[str]:
    """Return the active call_tree_id for the executing Tier 0 step, if bound."""
    inv = _ActiveServicesHolder.invocations()
    return inv[-1][1] if inv else None


__all__: tuple[str, ...] = (
    "HOST_DIALECT_ENV_KEY",
    "active_module_services_scope",
    "active_step_caller_env_scope",
    "active_step_invocation_scope",
    "build_default_module_services",
    "build_worker_module_services_factory",
    "build_workspace_module_services_factory",
    "register_workspace_host_dialect",
    "resolve_active_call_tree_id",
    "resolve_active_caller_module",
    "resolve_active_module_services",
    "resolve_active_step_env_locale",
    "resolve_explicit_workspace_host_dialect",
    "resolve_workspace_host_dialect",
    "unregister_workspace_host_dialect",
)
