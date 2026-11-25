"""Shared workspace Contributes 2.0 core extension point contracts, manifest discovery, and locale catalog loader."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import threading
from typing import Callable, ClassVar, Final, Iterator, Mapping, Optional, TypeAlias
import weakref

from core.filesystem.fs import (
    MAX_JSON_FILE_BYTES,
    is_symlink_or_reparse,
    read_nofollow_regular_bytes,
    try_resolve_contained_subpath,
)
from core.foundation import (
    HostPath,
    LocaleCatalog,
    ModuleId,
    SemVer4,
    YscbError,
    strict_parse_json_object,
)
from core.metadata.config import ConfigStore, ModuleManifest, parse_locale_chain_tokens, parse_manifest_dict
from core.metadata.contributes.aggregator import ContributesAggregator
from core.metadata.contributes.spec import ExtensionPointSpec, MergeStrategy

_CORE_ID: Final[ModuleId] = ModuleId("core")
_MODULES_DIR: Final[str] = ".modules"

SdkCoreSessionFactory: TypeAlias = Callable[
    [HostPath, HostPath],
    Optional[tuple[object, Callable[[], None]]],
]


class _SdkCoreSessionRegistry:
    """Thread-safe inversion-of-control registry binding CoreSystemModule session factory for YscbClient."""

    _LOCK: ClassVar[threading.Lock] = threading.Lock()
    _FACTORY: ClassVar[Optional[SdkCoreSessionFactory]] = None
    _POST_CALL_HOOKS: ClassVar[weakref.WeakKeyDictionary[object, Callable[[], None]]] = weakref.WeakKeyDictionary()
    _DISPATCHER_BINDERS: ClassVar[weakref.WeakKeyDictionary[object, Callable[[object], None]]] = (
        weakref.WeakKeyDictionary()
    )

    @classmethod
    def register(cls, factory: Optional[SdkCoreSessionFactory]) -> None:
        if factory is not None and not callable(factory):
            raise TypeError("SdkCoreSessionFactory must be callable or None")
        with cls._LOCK:
            cls._FACTORY = factory

    @classmethod
    def resolve(cls) -> Optional[SdkCoreSessionFactory]:
        with cls._LOCK:
            return cls._FACTORY

    @classmethod
    def register_post_call_hook(cls, core_module: object, hook: Callable[[], None]) -> None:
        if not callable(hook):
            raise TypeError("SDK core post-call hook must be callable")
        with cls._LOCK:
            cls._POST_CALL_HOOKS[core_module] = hook

    @classmethod
    def resolve_post_call_hook(cls, core_module: object) -> Optional[Callable[[], None]]:
        with cls._LOCK:
            return cls._POST_CALL_HOOKS.get(core_module)

    @classmethod
    def register_dispatcher_binder(cls, core_module: object, binder: Callable[[object], None]) -> None:
        if not callable(binder):
            raise TypeError("SDK core dispatcher binder must be callable")
        with cls._LOCK:
            cls._DISPATCHER_BINDERS[core_module] = binder

    @classmethod
    def resolve_dispatcher_binder(cls, core_module: object) -> Optional[Callable[[object], None]]:
        with cls._LOCK:
            return cls._DISPATCHER_BINDERS.get(core_module)


def register_sdk_core_session_factory(factory: Optional[SdkCoreSessionFactory]) -> None:
    """Register or clear the Composition Root factory providing CoreSystemModule to YscbClient."""
    _SdkCoreSessionRegistry.register(factory)


def resolve_sdk_core_session_factory() -> Optional[SdkCoreSessionFactory]:
    """Return the registered CoreSystemModule session factory for YscbClient, if available."""
    return _SdkCoreSessionRegistry.resolve()


def register_sdk_core_post_call_hook(core_module: object, hook: Callable[[], None]) -> None:
    """Attach a post-call daemon sync hook to a compiled CoreSystemModule instance."""
    _SdkCoreSessionRegistry.register_post_call_hook(core_module, hook)


def resolve_sdk_core_post_call_hook(core_module: object) -> Optional[Callable[[], None]]:
    """Look up any post-call daemon sync hook registered for a compiled CoreSystemModule instance."""
    return _SdkCoreSessionRegistry.resolve_post_call_hook(core_module)


def register_sdk_core_dispatcher_binder(core_module: object, binder: Callable[[object], None]) -> None:
    """Attach a shared-state dispatcher binder to a compiled CoreSystemModule instance."""
    _SdkCoreSessionRegistry.register_dispatcher_binder(core_module, binder)


def resolve_sdk_core_dispatcher_binder(core_module: object) -> Optional[Callable[[object], None]]:
    """Look up any shared-state dispatcher binder registered for a compiled CoreSystemModule instance."""
    return _SdkCoreSessionRegistry.resolve_dispatcher_binder(core_module)


class _ManagedChildDispatcherRegistry:
    """WeakSet registry tracking child RuntimeDispatchers owned by a parent WorkspaceKernel."""

    _LOCK: ClassVar[threading.Lock] = threading.Lock()
    _INSTANCES: ClassVar[weakref.WeakSet[object]] = weakref.WeakSet()

    @classmethod
    def register(cls, dispatcher: object) -> None:
        with cls._LOCK:
            cls._INSTANCES.add(dispatcher)

    @classmethod
    def contains(cls, dispatcher: object) -> bool:
        with cls._LOCK:
            return dispatcher in cls._INSTANCES


def register_managed_child_dispatcher(dispatcher: object) -> None:
    """Mark a RuntimeDispatcher instance as owned by a parent WorkspaceKernel child cache."""
    _ManagedChildDispatcherRegistry.register(dispatcher)


def is_managed_child_dispatcher(dispatcher: object) -> bool:
    """Return True iff the given dispatcher was registered as a managed child WorkspaceKernel dispatcher."""
    return _ManagedChildDispatcherRegistry.contains(dispatcher)


class _CrossWorkspaceCallTls(threading.local):
    def __init__(self) -> None:
        super().__init__()
        self.flags: list[bool] = []


class _CrossWorkspaceCallHolder:
    _TLS: ClassVar[Optional[_CrossWorkspaceCallTls]] = None
    _LOCK: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def flags(cls) -> list[bool]:
        if cls._TLS is None:
            with cls._LOCK:
                if cls._TLS is None:
                    cls._TLS = _CrossWorkspaceCallTls()
        return cls._TLS.flags


@contextmanager
def active_cross_workspace_call_scope(is_cross_workspace: bool) -> Iterator[None]:
    """Record whether the active Tier 0 step entered from a foreign workspace frame."""
    stack = _CrossWorkspaceCallHolder.flags()
    stack.append(bool(is_cross_workspace))
    try:
        yield
    finally:
        stack.pop()


def is_active_cross_workspace_call() -> bool:
    """Return True iff the active Tier 0 step was invoked directly across a workspace boundary."""
    stack = _CrossWorkspaceCallHolder.flags()
    return bool(stack[-1]) if stack else False


_PROTECTED_YSCB_SUBTREES: Final[tuple[str, ...]] = (
    ".modules",
    ".build",
    ".mirror",
    ".snapshots",
    ".venv",
    "config/core",
    ".config.local/core",
    "storage/core",
    "storage/project",
    ".storage.local/core",
    ".storage.local/project",
    ".cache/core",
    ".cache/project",
    ".cache/locks",
    ".cache/wheels",
    ".cache/daemon",
    ".cache/logs",
    ".cache/tasks.index.json",
)
_RESERVED_STORAGE_SECOND_SEGS: Final[frozenset[str]] = frozenset(
    {"core", "locks", "wheels", "daemon", "logs", "project"}
)
_ISOLATED_YSCB_SUBTREES: Final[tuple[str, ...]] = (
    "config",
    ".config.local",
    "storage",
    ".storage.local",
    ".cache",
)
_HOST_CONTROL_FILENAMES: Final[frozenset[str]] = frozenset(
    {
        "yscb.config.json",
        "yscb.config.local.json",
        "yscb.py",
        ".gitignore",
    }
)


def is_control_plane_reserved_path(
    hp: HostPath,
    *,
    yscb_root: HostPath,
    host_dir: HostPath,
    project_root: Optional[HostPath],
    project_root_disabled: bool = False,
    owner: Optional[str] = None,
    allow_any_module_storage: bool = False,
) -> bool:
    """Return True when hp targets control-plane or foreign private state off-limits to owner."""
    if owner == "core":
        return False
    p = hp.path
    yscb_p = yscb_root.path
    host_p = host_dir.path
    if p in yscb_p.parents or p in host_p.parents or p == host_p:
        return True
    eff_proj_p: Optional[Path] = (
        None
        if project_root_disabled
        else (project_root.path if project_root is not None else host_p)
    )
    if p == yscb_p or yscb_p in p.parents:
        rel_parts = () if p == yscb_p else p.relative_to(yscb_p).parts
        norm_segs = [os.path.normcase(seg) for seg in rel_parts if seg and seg != "."]
        if not norm_segs or any(seg == os.path.normcase(".git") for seg in norm_segs):
            return True
        norm_rel = "/".join(norm_segs)
        for prot in _PROTECTED_YSCB_SUBTREES:
            prot_norm = "/".join(os.path.normcase(s) for s in prot.split("/"))
            if (
                norm_rel == prot_norm
                or norm_rel.startswith(f"{prot_norm}/")
                or prot_norm.startswith(f"{norm_rel}/")
            ):
                return True
        iso_norms = tuple(os.path.normcase(s) for s in _ISOLATED_YSCB_SUBTREES)
        iso_hit = any(
            norm_rel == iso_n or norm_rel.startswith(f"{iso_n}/") or iso_n.startswith(f"{norm_rel}/")
            for iso_n in iso_norms
        )
        if iso_hit:
            top = norm_segs[0]
            if top in (os.path.normcase("config"), os.path.normcase(".config.local")):
                return True
            if allow_any_module_storage:
                if not (
                    len(norm_segs) >= 3
                    and top
                    in (
                        os.path.normcase("storage"),
                        os.path.normcase(".storage.local"),
                        os.path.normcase(".cache"),
                    )
                ):
                    return True
                seg_mod = rel_parts[1] if len(rel_parts) >= 2 else ""
                if seg_mod.lower() in _RESERVED_STORAGE_SECOND_SEGS:
                    return True
                try:
                    _ = ModuleId(seg_mod)
                except ValueError:
                    return True
            else:
                if owner is None or owner in ("", "project"):
                    return True
                owner_nc = os.path.normcase(owner)
                allowed_prefixes = (
                    f"{os.path.normcase('storage')}/{owner_nc}",
                    f"{os.path.normcase('.storage.local')}/{owner_nc}",
                    f"{os.path.normcase('.cache')}/{owner_nc}",
                )
                if not any(norm_rel == pfx or norm_rel.startswith(f"{pfx}/") for pfx in allowed_prefixes):
                    return True
        else:
            overlaps_project = (
                eff_proj_p is not None
                and (yscb_p == eff_proj_p or yscb_p in eff_proj_p.parents)
                and (p == eff_proj_p or eff_proj_p in p.parents)
            )
            if not overlaps_project:
                if not (
                    allow_any_module_storage
                    and (
                        yscb_p == host_p
                        or norm_segs[0] in (os.path.normcase("source"), os.path.normcase("release"))
                    )
                ):
                    return True
    elif host_p in p.parents and not allow_any_module_storage:
        if eff_proj_p is None or not (p == eff_proj_p or eff_proj_p in p.parents):
            return True

    if p.parent == host_p and os.path.normcase(p.name) in {os.path.normcase(n) for n in _HOST_CONTROL_FILENAMES}:
        return True
    if project_root is not None and p.parent == project_root.path and os.path.normcase(p.name) == os.path.normcase(".gitignore"):
        return True
    for base_dir in (host_p, project_root.path if project_root is not None else None):
        if base_dir is None:
            continue
        try:
            rel_parts_out = p.relative_to(base_dir).parts
        except ValueError:
            continue
        if any(os.path.normcase(seg) == os.path.normcase(".git") for seg in rel_parts_out):
            return True
    return False



@dataclass(frozen=True, slots=True)
class CoreUriSchemeContribution:
    """Typed Contributes 2.0 item for core uri_schemes (MergeStrategy.UNIQUE)."""

    token: Optional[str] = None
    target_uri: Optional[str] = None
    config_binding: Optional[str] = None
    provider_module: Optional[str] = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class CoreSpaceContribution:
    """Typed Contributes 2.0 item for core spaces (MergeStrategy.BUCKET_BY_DONOR)."""

    entries: tuple[str, ...] = ()
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    presets: tuple[str, ...] = ()
    compose: tuple[str, ...] = ()
    watch: Optional[bool] = None
    hash_policy: str = "adaptive"
    description: str = ""


def core_builtin_extension_points() -> tuple[ExtensionPointSpec[object], ...]:
    """Return the three built-in Contributes 2.0 extension points owned by 'core'."""
    return (
        ExtensionPointSpec(
            name="uri_schemes",
            payload_type=dict[str, CoreUriSchemeContribution],
            description="Semantic VFS URI scheme declarations contributed to core.",
            merge_strategy=MergeStrategy.UNIQUE,
        ),
        ExtensionPointSpec(
            name="spaces",
            payload_type=dict[str, CoreSpaceContribution],
            description="Logical file space declarations contributed to core.",
            merge_strategy=MergeStrategy.BUCKET_BY_DONOR,
        ),
        ExtensionPointSpec(
            name="locales",
            payload_type=dict[str, str],
            description="Module locale dictionary file pointers contributed to core.",
            merge_strategy=MergeStrategy.BUCKET_BY_DONOR,
        ),
    )


def discover_installed_manifests_map(yscb_root: HostPath) -> dict[ModuleId, ModuleManifest]:
    """Scan .modules/*/manifest.json safely without following symlinks and ensure synthetic 'core' fallback."""
    mods_hp = try_resolve_contained_subpath(yscb_root, _MODULES_DIR)
    found: dict[ModuleId, ModuleManifest] = {}
    if mods_hp is not None and os.path.isdir(str(mods_hp)) and not is_symlink_or_reparse(str(mods_hp)):
        try:
            with os.scandir(str(mods_hp)) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            entries = []
        for ent in entries:
            if ent.name.startswith(".") or ent.is_symlink() or is_symlink_or_reparse(ent.path):
                continue
            try:
                if not ent.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            mf_path = Path(ent.path) / "manifest.json"
            try:
                raw = read_nofollow_regular_bytes(str(mf_path), max_bytes=MAX_JSON_FILE_BYTES)
            except OSError:
                raw = None
            if raw is None:
                continue
            try:
                parsed = strict_parse_json_object(raw.decode("utf-8"))
                mf = parse_manifest_dict(parsed)
            except (UnicodeDecodeError, ValueError, YscbError):
                continue
            if mf.id.value == ent.name:
                found[mf.id] = mf
    if _CORE_ID not in found:
        found[_CORE_ID] = ModuleManifest(
            id=_CORE_ID,
            version=SemVer4.parse("2.0.0.0"),
            description="YS-Codebase Core Microkernel",
        )
    return found


def _read_string_kv_json(file_path: str) -> dict[str, str]:
    try:
        raw = read_nofollow_regular_bytes(file_path, max_bytes=MAX_JSON_FILE_BYTES)
    except OSError:
        return {}
    if raw is None:
        return {}
    try:
        parsed = strict_parse_json_object(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    return {k: v for k, v in parsed.items() if type(k) is str and type(v) is str}


def scan_workspace_locale_dictionaries(
    yscb_root: HostPath,
    *,
    contributes_aggregator: Optional[ContributesAggregator] = None,
) -> dict[ModuleId, dict[str, dict[str, str]]]:
    """Load per-module locale dictionaries honoring contributed core.locales pointers and locales/*.json fallback."""
    dicts: dict[ModuleId, dict[str, dict[str, str]]] = {}
    mods_hp = try_resolve_contained_subpath(yscb_root, _MODULES_DIR)
    contributed_locales: Mapping[str, object] = {}
    if contributes_aggregator is not None:
        try:
            core_agg = contributes_aggregator.aggregate(_CORE_ID, strict=False)
            raw_loc_bucket = core_agg.raw_merged.get("locales")
            if isinstance(raw_loc_bucket, Mapping):
                contributed_locales = raw_loc_bucket
        except YscbError:
            contributed_locales = {}

    if mods_hp is not None and os.path.isdir(str(mods_hp)) and not is_symlink_or_reparse(str(mods_hp)):
        for donor_key, ptr_map in sorted(contributed_locales.items()):
            if donor_key == "project" or type(donor_key) is not str or not isinstance(ptr_map, Mapping):
                continue
            try:
                donor_id = ModuleId(donor_key)
            except ValueError:
                continue
            donor_root = try_resolve_contained_subpath(mods_hp, donor_id.value)
            if donor_root is None or not os.path.isdir(str(donor_root)) or is_symlink_or_reparse(str(donor_root)):
                continue
            lang_map: dict[str, dict[str, str]] = {}
            for lang_id, rel_ptr in sorted(ptr_map.items()):
                if lang_id == "definition" or type(lang_id) is not str or type(rel_ptr) is not str:
                    continue
                rel_parts = tuple(p for p in rel_ptr.replace("\\", "/").split("/") if p)
                if not rel_parts:
                    continue
                target_hp = try_resolve_contained_subpath(donor_root, *rel_parts)
                if target_hp is None or is_symlink_or_reparse(str(target_hp)):
                    continue
                kv = _read_string_kv_json(str(target_hp))
                if kv:
                    lang_map[lang_id.strip()] = kv
            if lang_map:
                dicts[donor_id] = lang_map

        try:
            with os.scandir(str(mods_hp)) as it:
                mod_entries = sorted(it, key=lambda e: e.name)
        except OSError:
            mod_entries = []
        for ent in mod_entries:
            if ent.name.startswith(".") or ent.is_symlink() or is_symlink_or_reparse(ent.path):
                continue
            try:
                mod_id = ModuleId(ent.name)
            except ValueError:
                continue
            loc_dir = Path(ent.path) / "locales"
            if not loc_dir.is_dir() or is_symlink_or_reparse(str(loc_dir)):
                continue
            lang_map = dicts.setdefault(mod_id, {})
            try:
                with os.scandir(loc_dir) as lit:
                    loc_files = sorted(lit, key=lambda f: f.name)
            except OSError:
                loc_files = []
            for lf in loc_files:
                if not lf.name.endswith(".json") or lf.is_symlink() or is_symlink_or_reparse(lf.path):
                    continue
                stem = lf.name[:-5]
                if stem == "definition" or stem in lang_map:
                    continue
                kv = _read_string_kv_json(lf.path)
                if kv:
                    lang_map[stem] = kv
            if not lang_map:
                dicts.pop(mod_id, None)
    return dicts


def load_workspace_locale_catalog(
    yscb_root: HostPath,
    cfg_store: ConfigStore,
    *,
    contributes_aggregator: Optional[ContributesAggregator] = None,
    dialect: Optional[str] = None,
    raw_env_locale: Optional[str] = None,
) -> LocaleCatalog:
    """Construct a LocaleCatalog for a workspace from contributed/scanned locales and effective language chain."""
    dicts = scan_workspace_locale_dictionaries(yscb_root, contributes_aggregator=contributes_aggregator)
    chain = parse_locale_chain_tokens(raw_env_locale, cfg_store, dialect=dialect)
    return LocaleCatalog(dicts, default_chain=chain)


__all__ = (
    "CoreSpaceContribution",
    "CoreUriSchemeContribution",
    "SdkCoreSessionFactory",
    "active_cross_workspace_call_scope",
    "core_builtin_extension_points",
    "discover_installed_manifests_map",
    "is_active_cross_workspace_call",
    "is_control_plane_reserved_path",
    "is_managed_child_dispatcher",
    "load_workspace_locale_catalog",
    "parse_locale_chain_tokens",
    "register_managed_child_dispatcher",
    "register_sdk_core_dispatcher_binder",
    "register_sdk_core_post_call_hook",
    "register_sdk_core_session_factory",
    "resolve_sdk_core_dispatcher_binder",
    "resolve_sdk_core_post_call_hook",
    "resolve_sdk_core_session_factory",
    "scan_workspace_locale_dictionaries",
)
