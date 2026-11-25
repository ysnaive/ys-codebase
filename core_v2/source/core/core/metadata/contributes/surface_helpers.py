"""Shared DAG-legal workspace host discovery, surface hashing, and Contributes 2.0 mount/space parsers."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import threading
from typing import Callable, ClassVar, Final, Mapping, Optional
import weakref

from core.filesystem.fs import (
    has_symlink_raw_path,
    is_symlink_or_reparse,
    try_resolve_contained_subpath,
)
from core.foundation import (
    HostPath,
    ModuleId,
    SemanticUri,
    SpaceId,
    YscbError,
)
from core.metadata.config import ConfigStore
from core.metadata.contributes.aggregator import AggregatedContributes
from core.metadata.contributes.workspace_builtins import is_control_plane_reserved_path

_CORE_ID: Final[ModuleId] = ModuleId("core")
_MODULES_DIR: Final[str] = ".modules"
_FORBIDDEN_CONTRIBUTED_TARGET_SCHEMES: Final[frozenset[str]] = frozenset(
    {
        "yscb",
        "yscb.host",
        "module",
        "module.mirror",
        "snapshot",
        "yscb.venv",
    }
)
_ISOLATED_CONTRIBUTED_TARGET_SCHEMES: Final[frozenset[str]] = frozenset(
    {
        "config",
        "config.local",
        "cache",
        "storage",
        "storage.local",
    }
)
_VALID_SPACE_HASH_POLICIES: Final[frozenset[str]] = frozenset({"stat_only", "adaptive", "full_hash"})


@dataclass(frozen=True, slots=True)
class BoundLocaleDialect:
    """Bound host-dialect metadata associated with a WorkspaceKernel locale_getter callback."""

    dialect: Optional[str]
    is_daemon_host: bool = False
    inherit_host_env_locale: bool = True
    raw_env_locale_override: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ColdWorkspaceDialectState:
    """Active cold WorkspaceKernel dialect stack snapshot for a workspace root."""

    has_active_kernel: bool
    dialect: Optional[str] = None


@dataclass(frozen=True, slots=True)
class _ColdRootDialectEntry:
    token: int
    getter_ref: weakref.ReferenceType[object]
    dialect: Optional[str]


class _LocaleGetterDialectRegistry:
    """Thread-safe weak registry associating WorkspaceKernel locale_getter callables with host dialect."""

    _LOCK: ClassVar[threading.RLock] = threading.RLock()
    _NEXT_TOKEN: ClassVar[int] = 0
    _BY_GETTER: ClassVar[weakref.WeakKeyDictionary[object, BoundLocaleDialect]] = weakref.WeakKeyDictionary()
    _GETTER_ROOT_KEY: ClassVar[weakref.WeakKeyDictionary[object, tuple[str, int]]] = weakref.WeakKeyDictionary()
    _COLD_STACK_BY_ROOT: ClassVar[dict[str, list[_ColdRootDialectEntry]]] = {}
    _OWNER_TO_GETTER: ClassVar[weakref.WeakKeyDictionary[object, weakref.ReferenceType[object]]] = (
        weakref.WeakKeyDictionary()
    )

    @classmethod
    def _purge_token_locked(cls, rk: str, token: int) -> None:
        stack = cls._COLD_STACK_BY_ROOT.get(rk)
        if stack is None:
            return
        next_stack = [item for item in stack if item.token != token and item.getter_ref() is not None]
        if next_stack:
            cls._COLD_STACK_BY_ROOT[rk] = next_stack
        else:
            cls._COLD_STACK_BY_ROOT.pop(rk, None)

    @classmethod
    def _purge_dead_token(cls, rk: str, token: int) -> None:
        with cls._LOCK:
            cls._purge_token_locked(rk, token)

    @classmethod
    def _remove_cold_locked(cls, getter: object) -> None:
        prev = cls._GETTER_ROOT_KEY.pop(getter, None)
        if prev is None:
            return
        rk, tok = prev
        cls._purge_token_locked(rk, tok)

    @classmethod
    def bind(
        cls,
        getter: object,
        yscb_root: HostPath,
        dialect: Optional[str],
        *,
        is_daemon_host: bool = False,
        register_cold_root: bool = True,
        inherit_host_env_locale: bool = True,
        raw_env_locale_override: Optional[str] = None,
    ) -> None:
        clean_dial = dialect.strip() if isinstance(dialect, str) and dialect.strip() else None
        eff_dial = None if is_daemon_host else clean_dial
        clean_ovr = raw_env_locale_override.strip() if isinstance(raw_env_locale_override, str) else None
        with cls._LOCK:
            cls._remove_cold_locked(getter)
            cls._BY_GETTER[getter] = BoundLocaleDialect(
                dialect=eff_dial,
                is_daemon_host=bool(is_daemon_host),
                inherit_host_env_locale=(False if is_daemon_host else bool(inherit_host_env_locale)),
                raw_env_locale_override=clean_ovr,
            )
            if not is_daemon_host and register_cold_root:
                rk = yscb_root.comparison_key
                cls._NEXT_TOKEN += 1
                tok = cls._NEXT_TOKEN
                ref = weakref.ref(
                    getter,
                    lambda _dead, _rk=rk, _tok=tok: cls._purge_dead_token(_rk, _tok),
                )
                cls._GETTER_ROOT_KEY[getter] = (rk, tok)
                live_prev = [item for item in cls._COLD_STACK_BY_ROOT.get(rk, ()) if item.getter_ref() is not None]
                live_prev.append(_ColdRootDialectEntry(token=tok, getter_ref=ref, dialect=eff_dial))
                cls._COLD_STACK_BY_ROOT[rk] = live_prev

    @classmethod
    def unbind(cls, getter: object) -> None:
        try:
            with cls._LOCK:
                cls._remove_cold_locked(getter)
                cls._BY_GETTER.pop(getter, None)
        except TypeError:
            pass

    @classmethod
    def lookup(cls, getter: object) -> Optional[BoundLocaleDialect]:
        try:
            with cls._LOCK:
                return cls._BY_GETTER.get(getter)
        except TypeError:
            return None

    @classmethod
    def bind_owner(cls, owner: object, getter: object) -> None:
        try:
            with cls._LOCK:
                cls._OWNER_TO_GETTER[owner] = weakref.ref(getter)
        except TypeError:
            pass

    @classmethod
    def unbind_owner(cls, owner: object) -> None:
        try:
            with cls._LOCK:
                cls._OWNER_TO_GETTER.pop(owner, None)
        except TypeError:
            pass

    @classmethod
    def lookup_owner(cls, owner: object) -> Optional[BoundLocaleDialect]:
        try:
            with cls._LOCK:
                g_ref = cls._OWNER_TO_GETTER.get(owner)
                if g_ref is None:
                    return None
                getter = g_ref()
                if getter is None:
                    cls._OWNER_TO_GETTER.pop(owner, None)
                    return None
                bound = cls._BY_GETTER.get(getter)
                if bound is not None:
                    return bound
                return BoundLocaleDialect(
                    dialect=None,
                    is_daemon_host=False,
                    inherit_host_env_locale=False,
                    raw_env_locale_override=None,
                )
        except TypeError:
            return None

    @classmethod
    def lookup_cold_root_state(cls, yscb_root: HostPath) -> ColdWorkspaceDialectState:
        rk = yscb_root.comparison_key
        with cls._LOCK:
            stack = cls._COLD_STACK_BY_ROOT.get(rk)
            if not stack:
                return ColdWorkspaceDialectState(has_active_kernel=False, dialect=None)
            live = [item for item in stack if item.getter_ref() is not None]
            if not live:
                cls._COLD_STACK_BY_ROOT.pop(rk, None)
                return ColdWorkspaceDialectState(has_active_kernel=False, dialect=None)
            if len(live) != len(stack):
                cls._COLD_STACK_BY_ROOT[rk] = live
            return ColdWorkspaceDialectState(has_active_kernel=True, dialect=live[-1].dialect)

    @classmethod
    def lookup_cold_root(cls, yscb_root: HostPath) -> Optional[str]:
        return cls.lookup_cold_root_state(yscb_root).dialect


def bind_locale_getter_dialect(
    getter: object,
    yscb_root: HostPath,
    dialect: Optional[str],
    *,
    is_daemon_host: bool = False,
    register_cold_root: bool = True,
    inherit_host_env_locale: bool = True,
    raw_env_locale_override: Optional[str] = None,
) -> None:
    """Associate a WorkspaceKernel locale_getter callback with its cold/daemon dialect policy."""
    _LocaleGetterDialectRegistry.bind(
        getter,
        yscb_root,
        dialect,
        is_daemon_host=is_daemon_host,
        register_cold_root=register_cold_root,
        inherit_host_env_locale=inherit_host_env_locale,
        raw_env_locale_override=raw_env_locale_override,
    )


def unbind_locale_getter_dialect(getter: object) -> None:
    """Clear any dialect association recorded for a WorkspaceKernel locale_getter callback."""
    _LocaleGetterDialectRegistry.unbind(getter)


def lookup_locale_getter_dialect(getter: object) -> Optional[BoundLocaleDialect]:
    """Return BoundLocaleDialect for a registered WorkspaceKernel locale_getter callback, if any."""
    return _LocaleGetterDialectRegistry.lookup(getter)


def bind_locale_getter_owner(owner: object, getter: object) -> None:
    """Weakly associate a RuntimeDispatcher or service factory owner with a locale_getter callback."""
    _LocaleGetterDialectRegistry.bind_owner(owner, getter)


def unbind_locale_getter_owner(owner: object) -> None:
    """Remove any locale_getter association recorded for an owner instance."""
    _LocaleGetterDialectRegistry.unbind_owner(owner)


def lookup_owner_locale_dialect(owner: object) -> Optional[BoundLocaleDialect]:
    """Resolve BoundLocaleDialect for an owner bound via bind_locale_getter_owner, if any."""
    return _LocaleGetterDialectRegistry.lookup_owner(owner)


def lookup_cold_workspace_dialect_state(yscb_root: HostPath) -> ColdWorkspaceDialectState:
    """Return the active cold WorkspaceKernel dialect stack state for yscb_root."""
    return _LocaleGetterDialectRegistry.lookup_cold_root_state(yscb_root)


def lookup_cold_workspace_dialect(yscb_root: HostPath) -> Optional[str]:
    """Return the active cold WorkspaceKernel dialect registered for yscb_root, if any."""
    return _LocaleGetterDialectRegistry.lookup_cold_root(yscb_root)


def probe_workspace_host_dir(target_ws: HostPath) -> Optional[HostPath]:
    """Walk up to 64 symlink-free ancestors of target_ws to locate its owning host_dir."""
    raw_target = str(target_ws)
    if has_symlink_raw_path(raw_target) or is_symlink_or_reparse(raw_target) or not os.path.isdir(raw_target):
        return None
    cur_anc = target_ws.path
    for _depth in range(64):
        raw_anc = str(cur_anc)
        if has_symlink_raw_path(raw_anc) or is_symlink_or_reparse(raw_anc):
            break
        cfg_file = cur_anc / "yscb.config.json"
        if cfg_file.is_file() and not is_symlink_or_reparse(str(cfg_file)):
            try:
                anc_hp = HostPath(cur_anc)
                probe_store = ConfigStore(host_dir=anc_hp, yscb_root=target_ws)
                host_cfg = probe_store.load_host_config()
                root_cand = Path(host_cfg.yscb_root.strip())
                if (root_cand.drive or root_cand.anchor) and not root_cand.is_absolute():
                    raise ValueError("Half-qualified yscb_root")
                raw_root_cand = str(root_cand) if root_cand.is_absolute() else str(cur_anc / root_cand)
                if has_symlink_raw_path(raw_root_cand) or is_symlink_or_reparse(raw_root_cand):
                    raise ValueError("Symlinked yscb_root")
                if HostPath(raw_root_cand) == target_ws:
                    return anc_hp
            except (OSError, ValueError, YscbError):
                pass
        if cur_anc.parent == cur_anc:
            break
        cur_anc = cur_anc.parent
    return None


def hash_json_dir_shallow(update_fn: Callable[[bytes], None], tag: str, dir_path: str) -> None:
    """Feed deterministic (name, mtime_ns, size) lines for regular *.json files in dir_path."""
    try:
        with os.scandir(dir_path) as it_entries:
            entries = sorted(it_entries, key=lambda e: e.name)
        for ent in entries:
            if ent.is_symlink() or is_symlink_or_reparse(ent.path):
                continue
            if ent.is_file(follow_symlinks=False) and ent.name.endswith(".json"):
                st_f = os.stat(ent.path, follow_symlinks=False)
                update_fn(f"{tag}:{ent.name}:{st_f.st_mtime_ns}:{st_f.st_size}\n".encode("utf-8"))
    except OSError:
        pass


def _hash_module_json_tree_bounded(
    update_fn: Callable[[bytes], None],
    mod_name: str,
    mod_dir_path: str,
    *,
    include_tasks_index: bool,
) -> None:
    stack: list[tuple[str, str, int]] = [("", mod_dir_path, 0)]
    while stack:
        rel_pfx, cur_dir, depth = stack.pop()
        try:
            with os.scandir(cur_dir) as it_d:
                entries = sorted(it_d, key=lambda e: e.name, reverse=True)
        except OSError:
            continue
        for ent in entries:
            if ent.name.startswith(".") or ent.name == "__pycache__" or ent.is_symlink() or is_symlink_or_reparse(ent.path):
                continue
            rel_posix = f"{rel_pfx}/{ent.name}" if rel_pfx else ent.name
            try:
                if ent.is_dir(follow_symlinks=False):
                    if depth < 6:
                        stack.append((rel_posix, ent.path, depth + 1))
                elif ent.name.endswith(".json") and ent.is_file(follow_symlinks=False):
                    if not include_tasks_index and rel_posix == "tasks.index.json":
                        continue
                    st_j = os.stat(ent.path, follow_symlinks=False)
                    update_fn(f"mjson:{mod_name}/{rel_posix}:{st_j.st_mtime_ns}:{st_j.st_size}\n".encode("utf-8"))
            except OSError:
                continue


def hash_workspace_surface_trees(
    update_fn: Callable[[bytes], None],
    yscb_root: HostPath,
    *,
    include_space_db: bool = False,
    include_tasks_index: bool = False,
) -> None:
    """Hash config/, .config.local/, optional space state.db, and all module JSON metadata/locales."""
    for cfg_tree_name in ("config", ".config.local"):
        cfg_root = try_resolve_contained_subpath(yscb_root, cfg_tree_name)
        if cfg_root is None or is_symlink_or_reparse(str(cfg_root)) or not os.path.isdir(str(cfg_root)):
            continue
        hash_json_dir_shallow(update_fn, f"{cfg_tree_name}/root", str(cfg_root))
        try:
            with os.scandir(str(cfg_root)) as it_cfg:
                cfg_dirs = sorted(it_cfg, key=lambda e: e.name)
            for mod_ent in cfg_dirs:
                if mod_ent.is_symlink() or is_symlink_or_reparse(mod_ent.path) or not mod_ent.is_dir(follow_symlinks=False):
                    continue
                hash_json_dir_shallow(update_fn, f"{cfg_tree_name}/{mod_ent.name}", mod_ent.path)
        except OSError:
            pass
    if include_space_db:
        sp_db_dir = try_resolve_contained_subpath(yscb_root, ".storage.local", "core", "space")
        if sp_db_dir is not None and not is_symlink_or_reparse(str(sp_db_dir)) and os.path.isdir(str(sp_db_dir)):
            for db_fname in ("state.db", "state.db-wal"):
                db_fp_p = os.path.join(str(sp_db_dir), db_fname)
                try:
                    if not is_symlink_or_reparse(db_fp_p) and os.path.isfile(db_fp_p):
                        st_db = os.stat(db_fp_p, follow_symlinks=False)
                        update_fn(f"spdb:{db_fname}:{st_db.st_mtime_ns}:{st_db.st_size}\n".encode("utf-8"))
                except OSError:
                    pass
    mods_hp = try_resolve_contained_subpath(yscb_root, _MODULES_DIR)
    if mods_hp is not None and not is_symlink_or_reparse(str(mods_hp)) and os.path.isdir(str(mods_hp)):
        try:
            with os.scandir(str(mods_hp)) as it_mods:
                mod_entries = sorted(it_mods, key=lambda e: e.name)
        except OSError:
            mod_entries = []
        for me in mod_entries:
            if me.name.startswith(".") or me.is_symlink() or is_symlink_or_reparse(me.path):
                continue
            try:
                if not me.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            update_fn(f"mod:{me.name}\n".encode("utf-8"))
            _hash_module_json_tree_bounded(
                update_fn,
                me.name,
                me.path,
                include_tasks_index=include_tasks_index,
            )


@dataclass(frozen=True, slots=True)
class ResolvedProjectRoot:
    """Resolved core.project_root physical path and explicit disablement flag."""

    project_root: Optional[HostPath]
    disabled: bool


def resolve_workspace_project_root(host_dir: HostPath, cfg_store: ConfigStore) -> ResolvedProjectRoot:
    """Resolve core.project_root from ConfigStore enforcing symlink and half-qualified path guards."""
    try:
        raw_proj = cfg_store.get_module_value(_CORE_ID, "project_root", default=None)
    except YscbError:
        return ResolvedProjectRoot(None, False)
    if type(raw_proj) is not str:
        return ResolvedProjectRoot(None, False)
    rel_txt = raw_proj.strip()
    if not rel_txt or rel_txt.lower() == "!undefined":
        return ResolvedProjectRoot(None, True)
    cand = Path(rel_txt)
    if (cand.drive or cand.anchor) and not cand.is_absolute():
        return ResolvedProjectRoot(None, False)
    raw_target = cand if cand.is_absolute() else (host_dir.path / cand)
    if has_symlink_raw_path(str(raw_target)) or is_symlink_or_reparse(str(raw_target)):
        return ResolvedProjectRoot(None, False)
    try:
        return ResolvedProjectRoot(HostPath(raw_target), False)
    except ValueError:
        return ResolvedProjectRoot(None, False)


@dataclass(frozen=True, slots=True)
class ValidatedUriSchemeSpec:
    """Validated Contributes 2.0 core.uri_schemes specification prior to MountRule materialization."""

    scheme: str
    owner: str
    target_path: Optional[HostPath]
    target_uri: Optional[SemanticUri]
    provider_module: Optional[ModuleId]
    config_binding: Optional[str]
    description: str


def extract_validated_uri_schemes(
    host_dir: HostPath,
    cfg_store: ConfigStore,
    core_agg: AggregatedContributes,
) -> tuple[ValidatedUriSchemeSpec, ...]:
    """Validate provenance, donor ownership, '@' placeholder binding, and scheme isolation for uri_schemes."""
    raw_schemes = core_agg.raw_merged.get("uri_schemes")
    if not isinstance(raw_schemes, Mapping):
        return ()
    validated: list[ValidatedUriSchemeSpec] = []
    for scheme_name, spec_raw in sorted((k, v) for k, v in raw_schemes.items() if type(k) is str):
        if not isinstance(spec_raw, Mapping):
            continue
        tok_raw = spec_raw.get("token")
        if tok_raw is not None and (type(tok_raw) is not str or tok_raw != scheme_name):
            continue
        escaped_key = scheme_name.replace("~", "~0").replace("/", "~1")
        prov_entry = core_agg.provenance.origin_for(f"/uri_schemes/{escaped_key}")
        if prov_entry is None:
            continue
        owner = prov_entry.final_owner

        desc = spec_raw.get("description") if type(spec_raw.get("description")) is str else ""
        t_uri_s = spec_raw.get("target_uri")
        cfg_bind = spec_raw.get("config_binding")
        if t_uri_s is not None and cfg_bind is not None:
            continue
        prov_s = spec_raw.get("provider_module")
        prov_mod: Optional[ModuleId] = None
        if prov_s is not None:
            if type(prov_s) is not str:
                continue
            try:
                prov_mod = ModuleId(prov_s)
            except ValueError:
                continue

        if owner not in ("core", "project"):
            try:
                donor_mod = ModuleId(owner)
            except ValueError:
                continue
            if prov_mod is not None and prov_mod != donor_mod:
                continue
            prov_mod = donor_mod
            if cfg_bind is not None:
                if type(cfg_bind) is not str or "." not in cfg_bind or cfg_bind.split(".", 1)[0] != owner:
                    continue
        elif owner == "project":
            if prov_mod == _CORE_ID:
                continue
            if cfg_bind is not None:
                if type(cfg_bind) is not str or "." not in cfg_bind or cfg_bind.split(".", 1)[0] == "core":
                    continue

        target_uri: Optional[SemanticUri] = None
        target_path: Optional[HostPath] = None
        if t_uri_s is not None:
            if type(t_uri_s) is not str or not t_uri_s.strip():
                continue
            try:
                target_uri = SemanticUri.parse(t_uri_s.strip())
            except ValueError:
                continue
            if owner != "core":
                if target_uri.scheme in _FORBIDDEN_CONTRIBUTED_TARGET_SCHEMES:
                    continue
                if owner == "project":
                    if target_uri.uses_module_placeholder or target_uri.scheme in _ISOLATED_CONTRIBUTED_TARGET_SCHEMES:
                        continue
                else:
                    if target_uri.uses_module_placeholder:
                        target_uri = target_uri.bind_module(ModuleId(owner))
                    if target_uri.scheme in _ISOLATED_CONTRIBUTED_TARGET_SCHEMES:
                        first_seg = target_uri.rel_path.split("/", 1)[0] if target_uri.rel_path else ""
                        if first_seg != owner:
                            continue
        elif cfg_bind is not None:
            if type(cfg_bind) is not str or "." not in cfg_bind:
                continue
            mod_part, key_part = cfg_bind.split(".", 1)
            try:
                bound_val = cfg_store.get_module_value(ModuleId(mod_part), key_part, default=None)
            except (ValueError, YscbError):
                bound_val = None
            if type(bound_val) is str and bound_val.strip() and bound_val.strip().lower() != "!undefined":
                p_cand = Path(bound_val.strip())
                if (p_cand.drive or p_cand.anchor) and not p_cand.is_absolute():
                    continue
                raw_hp_c = p_cand if p_cand.is_absolute() else (host_dir.path / p_cand)
                if has_symlink_raw_path(str(raw_hp_c)) or is_symlink_or_reparse(str(raw_hp_c)):
                    continue
                try:
                    target_path = HostPath(raw_hp_c)
                except ValueError:
                    continue

        validated.append(
            ValidatedUriSchemeSpec(
                scheme=scheme_name,
                owner=owner,
                target_path=target_path,
                target_uri=target_uri,
                provider_module=prov_mod,
                config_binding=cfg_bind if type(cfg_bind) is str else None,
                description=desc,
            )
        )
    return tuple(validated)


def is_permitted_contributed_mount_root(
    resolved_hp: Optional[HostPath],
    *,
    owner: str,
    host_dir: HostPath,
    yscb_root: HostPath,
    proj_info: ResolvedProjectRoot,
) -> bool:
    """Return True iff a resolved contributed URI physical root obeys workspace sandbox boundaries."""
    if owner == "core" or resolved_hp is None:
        return True
    if (
        resolved_hp == host_dir
        or resolved_hp.path in host_dir.path.parents
        or resolved_hp.path in yscb_root.path.parents
    ):
        return False
    proj_root = proj_info.project_root
    proj_root_disabled = proj_info.disabled
    is_owner_yscb_data = False
    if owner != "project":
        owner_data_roots = tuple(
            dr
            for dr in (
                try_resolve_contained_subpath(yscb_root, "storage", owner),
                try_resolve_contained_subpath(yscb_root, ".storage.local", owner),
                try_resolve_contained_subpath(yscb_root, ".cache", owner),
            )
            if dr is not None
        )
        is_owner_yscb_data = any(
            resolved_hp == dr or dr.path in resolved_hp.path.parents
            for dr in owner_data_roots
        )
    if host_dir.path in resolved_hp.path.parents and not is_owner_yscb_data:
        if proj_root_disabled or (
            proj_root is not None
            and resolved_hp != proj_root
            and proj_root.path not in resolved_hp.path.parents
        ):
            return False
    return not is_control_plane_reserved_path(
        resolved_hp,
        yscb_root=yscb_root,
        host_dir=host_dir,
        project_root=proj_root,
        project_root_disabled=proj_root_disabled,
        owner=owner,
    )


@dataclass(frozen=True, slots=True)
class ParsedSpaceContribution:
    """Validated Contributes 2.0 core.spaces specification prior to SpaceSpec materialization."""

    space_id: SpaceId
    entries: tuple[SemanticUri, ...]
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    presets: tuple[str, ...]
    compose: tuple[str, ...]
    watch: bool
    hash_policy_name: str
    description: str


def _require_str_seq(raw_seq: object) -> Optional[tuple[str, ...]]:
    if not isinstance(raw_seq, (list, tuple)):
        return None
    if not all(type(x) is str for x in raw_seq):
        return None
    return tuple(raw_seq)


def extract_parsed_space_contributions(
    core_agg: AggregatedContributes,
) -> tuple[ParsedSpaceContribution, ...]:
    """Parse and validate donor-bucketed Contributes 2.0 core.spaces entries deterministically."""
    raw_bucket = core_agg.raw_merged.get("spaces")
    if not isinstance(raw_bucket, Mapping):
        return ()
    parsed: list[ParsedSpaceContribution] = []
    sorted_donors = sorted((k, v) for k, v in raw_bucket.items() if type(k) is str)
    for donor_key, donor_spaces in sorted_donors:
        clean_donor = donor_key.strip()
        if not clean_donor or not isinstance(donor_spaces, Mapping):
            continue
        sorted_spaces = sorted((k, v) for k, v in donor_spaces.items() if type(k) is str)
        for sp_name, sp_raw in sorted_spaces:
            if not isinstance(sp_raw, Mapping):
                continue
            try:
                sid = SpaceId.parse(sp_name) if "/" in sp_name else SpaceId(clean_donor, sp_name)
                if sid.owner != clean_donor:
                    continue
                entries_s = _require_str_seq(sp_raw.get("entries", []))
                inc_s = _require_str_seq(sp_raw.get("include", []))
                exc_s = _require_str_seq(sp_raw.get("exclude", []))
                pre_s = _require_str_seq(sp_raw.get("presets", []))
                comp_s = _require_str_seq(sp_raw.get("compose", []))
                if (
                    entries_s is None
                    or inc_s is None
                    or exc_s is None
                    or pre_s is None
                    or comp_s is None
                ):
                    continue
                raw_hp = sp_raw.get("hash_policy", "adaptive")
                if raw_hp is None:
                    eff_hp_name = "adaptive"
                elif type(raw_hp) is str:
                    hp_low = raw_hp.strip().lower()
                    eff_hp_name = hp_low if hp_low in _VALID_SPACE_HASH_POLICIES else "adaptive"
                else:
                    continue
                raw_desc = sp_raw.get("description", "")
                if raw_desc is None:
                    desc_s = ""
                elif type(raw_desc) is str:
                    desc_s = raw_desc
                else:
                    continue
                raw_watch = sp_raw.get("watch")
                if raw_watch is None:
                    eff_watch = False if sid.name in ("gitignore", "readonly") else True
                elif type(raw_watch) is bool:
                    eff_watch = raw_watch
                else:
                    continue
                parsed.append(
                    ParsedSpaceContribution(
                        space_id=sid,
                        entries=tuple(SemanticUri.parse(u) for u in entries_s),
                        include=inc_s,
                        exclude=exc_s,
                        presets=pre_s,
                        compose=comp_s,
                        watch=eff_watch,
                        hash_policy_name=eff_hp_name,
                        description=desc_s,
                    )
                )
            except (ValueError, YscbError):
                continue
    return tuple(parsed)


__all__ = (
    "BoundLocaleDialect",
    "ColdWorkspaceDialectState",
    "ParsedSpaceContribution",
    "ResolvedProjectRoot",
    "ValidatedUriSchemeSpec",
    "bind_locale_getter_dialect",
    "bind_locale_getter_owner",
    "extract_parsed_space_contributions",
    "extract_validated_uri_schemes",
    "hash_json_dir_shallow",
    "hash_workspace_surface_trees",
    "is_permitted_contributed_mount_root",
    "lookup_cold_workspace_dialect",
    "lookup_cold_workspace_dialect_state",
    "lookup_locale_getter_dialect",
    "lookup_owner_locale_dialect",
    "probe_workspace_host_dir",
    "resolve_workspace_project_root",
    "unbind_locale_getter_dialect",
    "unbind_locale_getter_owner",
)
