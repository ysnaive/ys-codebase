"""SpaceRegistry: three-source two-pass space compiler, dynamic spaces, and pruned walker."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import sqlite3
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
import time
from typing import Callable, ClassVar, Final, Iterator, Mapping, Optional, Sequence
from weakref import WeakKeyDictionary

from core.filesystem.fs import IGNORED_FS_PREFIXES, is_atomic_staging_filename, is_symlink_or_reparse
from core.filesystem.space.hasher import SPC_BLAKE2B_DIGEST_SIZE, spc_compute_file_hash
from core.filesystem.space.rules import (
    HashPolicy,
    SpaceFileEntry,
    SpaceMatchExplain,
    SpaceSpec,
    SpcCandidateCoords,
    SpcCompiledRuleSet,
    SpcControlPlaneRoots,
    SpcRuleItem,
    spc_build_candidate_coords,
    spc_check_space_uri_owner_boundary,
    spc_compute_rel_str,
    spc_extract_embedded_rule_uri,
    spc_is_control_plane_reserved_path,
    spc_normalize_space_id,
    spc_sort_owner_keys,
)
from core.filesystem.storage import ModuleDatabase
from core.filesystem.vfs import KernelVfs
from core.foundation.codec import DataclassCodec
from core.foundation.errors import ErrorCode, YscbError
from core.foundation.observability import CancellationToken
from core.foundation.primitives import (
    IS_WINDOWS,
    HostPath,
    ModuleId,
    SemanticUri,
    SpaceId,
    SpacePath,
    is_valid_relative_segment,
    require_pure_str,
    strict_parse_json_object,
)

_SPACE_REQUIRED_TABLES: Final[frozenset[str]] = frozenset(
    {
        "dynamic_spaces",
        "space_snapshots",
        "space_files",
        "space_change_log",
        "consumer_cursors",
    }
)

_SPACE_DDL_STATEMENTS: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS dynamic_spaces (
        owner TEXT NOT NULL,
        name TEXT NOT NULL,
        spec_json TEXT NOT NULL,
        updated_at_ns INTEGER NOT NULL,
        PRIMARY KEY (owner, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS space_snapshots (
        target_key TEXT PRIMARY KEY,
        generation INTEGER NOT NULL,
        config_hash TEXT NOT NULL,
        merkle_root TEXT NOT NULL,
        file_count INTEGER NOT NULL,
        updated_at_ns INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS space_files (
        target_key TEXT NOT NULL,
        rel_path TEXT NOT NULL,
        abs_path TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        updated_gen INTEGER NOT NULL,
        PRIMARY KEY (target_key, rel_path)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_space_files_abs
    ON space_files (target_key, abs_path)
    """,
    """
    CREATE TABLE IF NOT EXISTS space_change_log (
        target_key TEXT NOT NULL,
        gen INTEGER NOT NULL,
        rel_path TEXT NOT NULL,
        op TEXT NOT NULL CHECK (op IN ('A', 'M', 'D')),
        PRIMARY KEY (target_key, gen, rel_path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS consumer_cursors (
        consumer_id TEXT NOT NULL,
        target_key TEXT NOT NULL,
        acked_gen INTEGER NOT NULL,
        config_hash TEXT NOT NULL,
        merkle_root TEXT NOT NULL,
        updated_at_ns INTEGER NOT NULL,
        PRIMARY KEY (consumer_id, target_key)
    )
    """,
)

_BUILTIN_GITIGNORE_INCLUDE: Final[tuple[str, ...]] = (
    "yscb://.modules/",
    "yscb://.build/",
    "yscb://.mirror/",
    "yscb://.snapshots/",
    "yscb://.cache/",
    "yscb://.config.local/",
    "yscb://.storage.local/",
    "yscb://.venv/",
    "*.local.json",
    "__pycache__/",
    "*.pyc",
    "*.bak",
)

_BUILTIN_WORKSPACE_EXCLUDE: Final[tuple[str, ...]] = (
    "yscb://.modules/**",
    "yscb://.build/**",
    "yscb://.mirror/**",
    "yscb://.snapshots/**",
    "yscb://.cache/**",
    "yscb://.config.local/**",
    "yscb://.storage.local/**",
    "yscb://.venv/**",
    ".git",
    ".svn",
    ".hg",
    ".DS_Store",
    "Thumbs.db",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
)

_WILDCARD_INC_TOKENS: Final[frozenset[str]] = frozenset({"*", "**", "**/*"})


@dataclass(frozen=True, slots=True)
class _SpcResolvedEntry:
    uri: SemanticUri
    host_path: Optional[HostPath]


@dataclass(frozen=True, slots=True)
class _SpcCompiledSpace:
    spec: SpaceSpec
    resolved_entries: tuple[_SpcResolvedEntry, ...]
    effective_include: tuple[SpcRuleItem, ...]
    effective_exclude: tuple[SpcRuleItem, ...]
    has_explicit_include: bool
    compiled_include: SpcCompiledRuleSet
    compiled_exclude: SpcCompiledRuleSet
    negated_presets: tuple[_SpcCompiledSpace, ...]
    pos_compose: tuple[SpaceId, ...]
    neg_compose: tuple[SpaceId, ...]


@dataclass(frozen=True, slots=True)
class SpcRawFileRecord:
    """Internal unhashed file discovery record shared with SpaceScanner."""

    rel_path: SpacePath
    abs_path: HostPath
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class _SpcRegistrySnapshot:
    ordered_specs: tuple[SpaceSpec, ...]
    compiled_by_id: Mapping[SpaceId, _SpcCompiledSpace]
    config_hashes: Mapping[SpaceId, str]
    proj_root: Optional[HostPath]
    control_roots: SpcControlPlaneRoots
    dynamic_specs: tuple[SpaceSpec, ...]


def spc_ensure_space_tables(db: ModuleDatabase) -> None:
    """Initialize all five core.filesystem.space SQLite tables idempotently if missing."""
    if not isinstance(db, ModuleDatabase):
        raise ValueError(f"Expected ModuleDatabase, got {db!r}")
    with db.read_snapshot() as snap:
        rows = snap.query_all(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN "
            "('dynamic_spaces', 'space_snapshots', 'space_files', 'space_change_log', 'consumer_cursors')"
        )
        existing = {require_pure_str(r[0], "table_name") for r in rows}
    if _SPACE_REQUIRED_TABLES <= existing:
        return
    with db.write_transaction() as tx:
        for ddl in _SPACE_DDL_STATEMENTS:
            tx.execute(ddl)


def _build_builtin_specs() -> tuple[SpaceSpec, ...]:
    project_root_uri = SemanticUri("project", "")
    return (
        SpaceSpec(
            space_id=SpaceId("core", "gitignore"),
            entries=(project_root_uri,),
            include=_BUILTIN_GITIGNORE_INCLUDE,
            exclude=(),
            watch=False,
            hash_policy=HashPolicy.ADAPTIVE,
            description="Built-in Git ignore space materialized into project://.gitignore.",
        ),
        SpaceSpec(
            space_id=SpaceId("core", "workspace"),
            entries=(project_root_uri,),
            include=("*",),
            exclude=_BUILTIN_WORKSPACE_EXCLUDE,
            watch=True,
            hash_policy=HashPolicy.ADAPTIVE,
            description="Built-in project workspace boundary space.",
        ),
    )


def _merge_two_specs_pass1(base: SpaceSpec, incoming: SpaceSpec) -> SpaceSpec:
    merged_entries: list[SemanticUri] = list(base.entries)
    for ent in incoming.entries:
        if ent not in merged_entries:
            merged_entries.append(ent)

    merged_exclude: list[str] = list(base.exclude)
    for exc in incoming.exclude:
        if exc not in merged_exclude:
            merged_exclude.append(exc)

    merged_presets: list[str] = list(base.presets)
    for pre in incoming.presets:
        if pre not in merged_presets:
            merged_presets.append(pre)

    merged_compose: list[str] = list(base.compose)
    for comp in incoming.compose:
        if comp not in merged_compose:
            merged_compose.append(comp)

    combined_inc: list[str] = []
    for inc in (*base.include, *incoming.include):
        if inc not in combined_inc:
            combined_inc.append(inc)
    if combined_inc and any(tok in _WILDCARD_INC_TOKENS for tok in combined_inc):
        final_include: tuple[str, ...] = ("*",)
    else:
        final_include = tuple(combined_inc)

    eff_desc = incoming.description if incoming.description else base.description
    return SpaceSpec(
        space_id=base.space_id,
        entries=tuple(merged_entries),
        include=final_include,
        exclude=tuple(merged_exclude),
        presets=tuple(merged_presets),
        compose=tuple(merged_compose),
        watch=incoming.watch,
        hash_policy=incoming.hash_policy,
        description=eff_desc,
    )


def _check_space_uri_owner_boundary(
    uri: SemanticUri,
    owner: str,
    *,
    is_readonly_space: bool,
) -> Optional[str]:
    return spc_check_space_uri_owner_boundary(uri, owner, is_readonly_space=is_readonly_space)


def _resolve_uri_safe(
    vfs: KernelVfs,
    uri: SemanticUri,
    owner: str,
    *,
    is_readonly_space: bool = False,
) -> Optional[HostPath]:
    if _check_space_uri_owner_boundary(uri, owner, is_readonly_space=is_readonly_space) is not None:
        return None
    bound = uri
    if uri.uses_module_placeholder:
        if not owner or owner == "project":
            return None
        try:
            bound = uri.bind_module(ModuleId(owner))
        except ValueError:
            return None
    try:
        return vfs.try_get_physical_path(bound)
    except YscbError:
        return None


def _has_intervening_symlink(cand_path: Path, base_path: Path) -> bool:
    if is_symlink_or_reparse(str(base_path)):
        return True
    if cand_path == base_path:
        return False
    try:
        rel_parts = cand_path.relative_to(base_path).parts
    except ValueError:
        return True
    cur = base_path
    for seg in rel_parts:
        cur = cur / seg
        if is_symlink_or_reparse(str(cur)):
            return True
    return False


def _has_ignored_space_segments(cand_path: Path, base_path: Path, *, is_dir: bool) -> bool:
    try:
        rel_parts = cand_path.relative_to(base_path).parts
    except ValueError:
        return False
    if not rel_parts:
        if not is_dir:
            return cand_path.name.startswith(IGNORED_FS_PREFIXES) or is_atomic_staging_filename(cand_path.name)
        return False
    for seg in rel_parts:
        if seg.startswith(IGNORED_FS_PREFIXES):
            return True
    if not is_dir and is_atomic_staging_filename(rel_parts[-1]):
        return True
    return False


def _compute_space_rel_path(
    file_abs: HostPath,
    entry_abs: HostPath,
    entry_uri: SemanticUri,
    proj_root: Optional[HostPath],
) -> Optional[SpacePath]:
    if proj_root is not None:
        rel_proj = spc_compute_rel_str(file_abs.path, proj_root.path)
        if rel_proj:
            try:
                return SpacePath.parse(rel_proj)
            except ValueError:
                pass
    rel_ent = spc_compute_rel_str(file_abs.path, entry_abs.path)
    if rel_ent == "":
        try:
            return SpacePath.parse(file_abs.path.name)
        except ValueError:
            return None
    if rel_ent:
        prefix = entry_abs.path.name
        if not is_valid_relative_segment(prefix):
            prefix = entry_uri.scheme.replace(".", "_")
        cand_rel = f"{prefix}/{rel_ent}" if is_valid_relative_segment(prefix) else rel_ent
        try:
            return SpacePath.parse(cand_rel)
        except ValueError:
            return None
    return None


def _select_deepest_entry_pair(
    cand_path: Path,
    default_pair: tuple[SemanticUri, HostPath],
    all_pairs: Sequence[tuple[SemanticUri, HostPath]],
) -> tuple[SemanticUri, HostPath]:
    if len(all_pairs) <= 1:
        return default_pair
    best = default_pair
    best_depth = len(default_pair[1].path.parts)
    for cand_uri, cand_hp in all_pairs:
        cand_depth = len(cand_hp.path.parts)
        if cand_depth <= best_depth:
            continue
        if spc_compute_rel_str(cand_path, cand_hp.path) is not None:
            best = (cand_uri, cand_hp)
            best_depth = cand_depth
    return best


def _matches_preset_space_fast(preset_comp: _SpcCompiledSpace, coords: SpcCandidateCoords) -> bool:
    if preset_comp.compiled_exclude.matches_fast(coords):
        return False
    if any(_matches_preset_space_fast(sub_neg, coords) for sub_neg in preset_comp.negated_presets):
        return False
    return preset_comp.compiled_include.matches_fast(coords)


def _find_preset_space_match(preset_comp: _SpcCompiledSpace, coords: SpcCandidateCoords) -> Optional[SpcRuleItem]:
    if preset_comp.compiled_exclude.find_match(coords) is not None:
        return None
    if any(_find_preset_space_match(sub_neg, coords) is not None for sub_neg in preset_comp.negated_presets):
        return None
    return preset_comp.compiled_include.find_match(coords)


def _preset_has_potential_descendant_exemption(
    preset_comp: _SpcCompiledSpace,
    dir_coords: SpcCandidateCoords,
) -> bool:
    if preset_comp.compiled_exclude.has_potential_descendant_match(dir_coords):
        return True
    for sub_neg in preset_comp.negated_presets:
        if (
            sub_neg.compiled_include.matches_fast(dir_coords)
            or sub_neg.compiled_include.has_potential_descendant_match(dir_coords)
        ):
            return True
    return False


def _is_dir_pruned_for_space(
    compiled: _SpcCompiledSpace,
    dir_abs: HostPath,
    entry_abs: HostPath,
    proj_root: Optional[HostPath],
) -> bool:
    coords = spc_build_candidate_coords(dir_abs, entry_abs, proj_root, is_dir=True)
    if compiled.compiled_exclude.matches_fast(coords):
        return True
    for neg_preset in compiled.negated_presets:
        if _matches_preset_space_fast(neg_preset, coords) and not _preset_has_potential_descendant_exemption(
            neg_preset, coords
        ):
            return True
    return False


def _is_file_matched_in_own_space(
    compiled: _SpcCompiledSpace,
    file_abs: HostPath,
    entry_abs: HostPath,
    proj_root: Optional[HostPath],
) -> bool:
    coords = spc_build_candidate_coords(file_abs, entry_abs, proj_root, is_dir=False)
    if compiled.compiled_exclude.matches_fast(coords):
        return False
    for neg_preset in compiled.negated_presets:
        if _matches_preset_space_fast(neg_preset, coords):
            return False
    return compiled.compiled_include.matches_fast(coords)


def _explain_file_in_own_entry(
    compiled: _SpcCompiledSpace,
    target_abs: HostPath,
    entry_uri: SemanticUri,
    entry_abs: HostPath,
    proj_root: Optional[HostPath],
    *,
    is_dir: bool,
) -> SpaceMatchExplain:
    coords = spc_build_candidate_coords(target_abs, entry_abs, proj_root, is_dir=is_dir)
    exc_hit = compiled.compiled_exclude.find_match(coords)
    if exc_hit is not None:
        return SpaceMatchExplain(
            space_id=compiled.spec.space_id,
            matched=False,
            matched_entry=entry_uri,
            matched_exclude=exc_hit.raw_pattern,
            source_space=exc_hit.source_space,
            reason="excluded",
        )
    for neg_preset in compiled.negated_presets:
        neg_inc_hit = _find_preset_space_match(neg_preset, coords)
        if neg_inc_hit is not None:
            return SpaceMatchExplain(
                space_id=compiled.spec.space_id,
                matched=False,
                matched_entry=entry_uri,
                matched_exclude=neg_inc_hit.raw_pattern,
                source_space=neg_preset.spec.space_id,
                reason="excluded_by_preset",
            )
    inc_hit = compiled.compiled_include.find_match(coords)
    if inc_hit is not None:
        return SpaceMatchExplain(
            space_id=compiled.spec.space_id,
            matched=True,
            matched_entry=entry_uri,
            matched_include=inc_hit.raw_pattern,
            source_space=inc_hit.source_space,
            reason="included",
        )
    return SpaceMatchExplain(
        space_id=compiled.spec.space_id,
        matched=False,
        matched_entry=entry_uri,
        reason="not_matching_include",
    )


def _compile_all_spaces(
    vfs: KernelVfs,
    static_specs: Sequence[SpaceSpec],
    dynamic_specs: Sequence[SpaceSpec],
    overlay_specs: Sequence[SpaceSpec],
) -> _SpcRegistrySnapshot:
    merged_by_id: dict[SpaceId, SpaceSpec] = {}
    for layer_spec in (*_build_builtin_specs(), *static_specs, *dynamic_specs, *overlay_specs):
        if not isinstance(layer_spec, SpaceSpec):
            raise ValueError(f"Expected SpaceSpec, got {layer_spec!r}")
        existing = merged_by_id.get(layer_spec.space_id)
        if existing is None:
            merged_by_id[layer_spec.space_id] = layer_spec
        else:
            merged_by_id[layer_spec.space_id] = _merge_two_specs_pass1(existing, layer_spec)

    owners_by_name: dict[str, list[str]] = {}
    all_names: set[str] = {"readonly"}
    present_owners = spc_sort_owner_keys([sid.owner for sid in merged_by_id if sid.owner != ""])
    for owner in present_owners:
        owner_names = sorted(sid.name for sid in merged_by_id if sid.owner == owner)
        for name in owner_names:
            all_names.add(name)
            owners_by_name.setdefault(name, []).append(owner)
    for sid in list(merged_by_id.keys()):
        if sid.owner == "":
            all_names.add(sid.name)

    for short_name in sorted(all_names):
        synth_id = SpaceId("", short_name)
        member_owners = owners_by_name.get(short_name, [])
        compose_members = tuple(f"{o}/{short_name}" for o in member_owners)
        default_watch = False if short_name in ("gitignore", "readonly") else True
        any_watch = (
            any(merged_by_id[SpaceId(o, short_name)].watch for o in member_owners)
            if member_owners
            else default_watch
        )
        member_policies = {merged_by_id[SpaceId(o, short_name)].hash_policy for o in member_owners}
        synth_policy = next(iter(member_policies)) if len(member_policies) == 1 else HashPolicy.ADAPTIVE
        synth_base = SpaceSpec(
            space_id=synth_id,
            entries=(),
            include=(),
            exclude=(),
            presets=(),
            compose=compose_members,
            watch=any_watch,
            hash_policy=synth_policy,
            description=f"Synthesized union space for '{short_name}'.",
        )
        explicit_synth = merged_by_id.get(synth_id)
        merged_by_id[synth_id] = (
            _merge_two_specs_pass1(synth_base, explicit_synth) if explicit_synth is not None else synth_base
        )

    proj_root = _resolve_uri_safe(vfs, SemanticUri("project", ""), "")
    control_roots = SpcControlPlaneRoots(
        yscb_root=_resolve_uri_safe(vfs, SemanticUri("yscb", ""), "core"),
        host_dir=_resolve_uri_safe(vfs, SemanticUri("yscb.host", ""), "core"),
        proj_root=proj_root,
    )

    compiled_map: dict[SpaceId, _SpcCompiledSpace] = {}

    def _resolve_preset_targets(ref_body: str) -> tuple[SpaceId, ...]:
        parsed = spc_normalize_space_id(ref_body)
        if parsed is None:
            raise YscbError(ErrorCode.SPACE_NOT_FOUND, f"Invalid or unknown preset reference '{ref_body}'.")
        if parsed.owner == "":
            member_ids = [SpaceId(o, parsed.name) for o in owners_by_name.get(parsed.name, [])]
            explicit_synth_spec = merged_by_id.get(parsed)
            if explicit_synth_spec is not None and (
                explicit_synth_spec.include or explicit_synth_spec.exclude or explicit_synth_spec.presets
            ):
                member_ids.append(parsed)
            if member_ids:
                return tuple(member_ids)
            if parsed in merged_by_id:
                return (parsed,)
            raise YscbError(ErrorCode.SPACE_NOT_FOUND, f"Referenced preset space '{ref_body}' does not exist.")
        if parsed not in merged_by_id:
            raise YscbError(ErrorCode.SPACE_NOT_FOUND, f"Referenced preset space '{ref_body}' does not exist.")
        return (parsed,)

    def _compile_space_dfs(sid: SpaceId, visiting: tuple[SpaceId, ...]) -> _SpcCompiledSpace:
        cached = compiled_map.get(sid)
        if cached is not None:
            return cached
        if sid in visiting:
            chain = " -> ".join(str(x) for x in (*visiting, sid))
            raise YscbError(
                ErrorCode.SPACE_CYCLE,
                f"Circular preset reference detected in logical spaces: {chain}",
                remediation="Break the cyclic 'presets' reference chain across SpaceSpec definitions.",
            )
        next_visiting = (*visiting, sid)
        spec = merged_by_id[sid]

        preset_non_wild_inc: list[SpcRuleItem] = []
        preset_wild_inc: Optional[SpcRuleItem] = None
        eff_exc: list[SpcRuleItem] = []
        neg_presets: list[_SpcCompiledSpace] = []

        for raw_pre in spec.presets:
            is_neg = raw_pre.startswith("!")
            ref_body = raw_pre[1:].strip() if is_neg else raw_pre
            targets = _resolve_preset_targets(ref_body)
            for t_id in targets:
                t_comp = _compile_space_dfs(t_id, next_visiting)
                if is_neg:
                    if all(existing.spec.space_id != t_comp.spec.space_id for existing in neg_presets):
                        neg_presets.append(t_comp)
                else:
                    if t_comp.has_explicit_include:
                        for inc_it in t_comp.effective_include:
                            orig_src = inc_it.source_space
                            if inc_it.raw_pattern in _WILDCARD_INC_TOKENS:
                                if preset_wild_inc is None:
                                    preset_wild_inc = SpcRuleItem("*", orig_src)
                            else:
                                cand_it = SpcRuleItem(inc_it.raw_pattern, orig_src)
                                if cand_it not in preset_non_wild_inc:
                                    preset_non_wild_inc.append(cand_it)
                    for exc_it in t_comp.effective_exclude:
                        cand_ex = SpcRuleItem(exc_it.raw_pattern, exc_it.source_space)
                        if cand_ex not in eff_exc:
                            eff_exc.append(cand_ex)
                    for child_neg in t_comp.negated_presets:
                        if all(existing.spec.space_id != child_neg.spec.space_id for existing in neg_presets):
                            neg_presets.append(child_neg)

        own_has_wild = any(p in _WILDCARD_INC_TOKENS for p in spec.include)
        has_explicit_inc = bool(spec.include) or bool(preset_non_wild_inc) or (preset_wild_inc is not None)
        eff_inc: list[SpcRuleItem] = []

        if own_has_wild:
            eff_inc = [SpcRuleItem("*", sid)]
        else:
            eff_inc.extend(preset_non_wild_inc)
            for own_pat in spec.include:
                cand_own = SpcRuleItem(own_pat, sid)
                if cand_own not in eff_inc:
                    eff_inc.append(cand_own)
            if not eff_inc and preset_wild_inc is not None:
                eff_inc.append(preset_wild_inc)
            if not eff_inc and sid.name != "gitignore":
                eff_inc.append(SpcRuleItem("*", sid))

        for own_exc in spec.exclude:
            cand_exc = SpcRuleItem(own_exc, sid)
            if cand_exc not in eff_exc:
                eff_exc.append(cand_exc)

        pos_comp: list[SpaceId] = []
        neg_comp: list[SpaceId] = []
        for raw_comp in spec.compose:
            is_neg_c = raw_comp.startswith("!")
            comp_body = raw_comp[1:].strip() if is_neg_c else raw_comp
            comp_id = spc_normalize_space_id(comp_body)
            if comp_id is None or comp_id not in merged_by_id:
                raise YscbError(
                    ErrorCode.SPACE_NOT_FOUND,
                    f"Referenced compose space '{comp_body}' in '{sid}' does not exist.",
                )
            bucket = neg_comp if is_neg_c else pos_comp
            if comp_id not in bucket:
                bucket.append(comp_id)

        is_ro_space = sid.name == "readonly"
        resolved_ents = tuple(
            _SpcResolvedEntry(
                uri=ent_u,
                host_path=_resolve_uri_safe(vfs, ent_u, sid.owner, is_readonly_space=is_ro_space),
            )
            for ent_u in spec.entries
        )
        space_uri_resolver: Callable[[SemanticUri, str], Optional[HostPath]] = (
            lambda u, o, _ro=is_ro_space: _resolve_uri_safe(vfs, u, o, is_readonly_space=_ro)
        )
        comp_inc_set = SpcCompiledRuleSet(eff_inc, owner=sid.owner, uri_resolver=space_uri_resolver)
        comp_exc_set = SpcCompiledRuleSet(eff_exc, owner=sid.owner, uri_resolver=space_uri_resolver)
        built = _SpcCompiledSpace(
            spec=spec,
            resolved_entries=resolved_ents,
            effective_include=tuple(eff_inc),
            effective_exclude=tuple(eff_exc),
            has_explicit_include=has_explicit_inc,
            compiled_include=comp_inc_set,
            compiled_exclude=comp_exc_set,
            negated_presets=tuple(neg_presets),
            pos_compose=tuple(pos_comp),
            neg_compose=tuple(neg_comp),
        )
        compiled_map[sid] = built
        return built

    ordered_ids: list[SpaceId] = []
    for owner in present_owners:
        for name in sorted(s.name for s in merged_by_id if s.owner == owner):
            ordered_ids.append(SpaceId(owner, name))
    for synth_name in sorted(s.name for s in merged_by_id if s.owner == ""):
        ordered_ids.append(SpaceId("", synth_name))

    for sid in ordered_ids:
        _compile_space_dfs(sid, ())

    compose_verified: set[SpaceId] = set()

    def _verify_compose_acyclic(sid: SpaceId, stack: tuple[SpaceId, ...]) -> None:
        if sid in stack:
            chain = " -> ".join(str(x) for x in (*stack, sid))
            raise YscbError(
                ErrorCode.SPACE_CYCLE,
                f"Circular compose reference detected in logical spaces: {chain}",
                remediation="Break the cyclic 'compose' reference chain across SpaceSpec definitions.",
            )
        if sid in compose_verified:
            return
        comp_sp = compiled_map[sid]
        next_stack = (*stack, sid)
        for child_id in (*comp_sp.pos_compose, *comp_sp.neg_compose):
            _verify_compose_acyclic(child_id, next_stack)
        compose_verified.add(sid)

    for sid in ordered_ids:
        _verify_compose_acyclic(sid, ())

    cfg_hashes: dict[SpaceId, str] = {}
    for sid in ordered_ids:
        cfg_hashes[sid] = _compute_single_config_hash(sid, compiled_map)

    return _SpcRegistrySnapshot(
        ordered_specs=tuple(compiled_map[sid].spec for sid in ordered_ids),
        compiled_by_id=compiled_map,
        config_hashes=cfg_hashes,
        proj_root=proj_root,
        control_roots=control_roots,
        dynamic_specs=tuple(dynamic_specs),
    )


def _compute_single_config_hash(
    root_id: SpaceId,
    compiled_by_id: Mapping[SpaceId, _SpcCompiledSpace],
) -> str:
    visited: set[SpaceId] = set()
    stack: list[SpaceId] = [root_id]
    while stack:
        cur_id = stack.pop()
        if cur_id in visited:
            continue
        visited.add(cur_id)
        comp = compiled_by_id[cur_id]
        stack.extend(comp.pos_compose)
        stack.extend(comp.neg_compose)
        for neg_p in comp.negated_presets:
            stack.append(neg_p.spec.space_id)

    hasher = hashlib.blake2b(digest_size=SPC_BLAKE2B_DIGEST_SIZE)
    for dep_id in sorted(visited, key=str):
        comp = compiled_by_id[dep_id]
        payload = {
            "space_id": str(dep_id),
            "entries": [
                [str(re_item.uri), re_item.host_path.comparison_key if re_item.host_path is not None else None]
                for re_item in comp.resolved_entries
            ],
            "effective_include": [[r.raw_pattern, str(r.source_space)] for r in comp.effective_include],
            "effective_exclude": [[r.raw_pattern, str(r.source_space)] for r in comp.effective_exclude],
            "negated_presets": [str(np.spec.space_id) for np in comp.negated_presets],
            "pos_compose": [str(cid) for cid in comp.pos_compose],
            "neg_compose": [str(cid) for cid in comp.neg_compose],
            "hash_policy": comp.spec.hash_policy.value,
            "watch": comp.spec.watch,
        }
        hasher.update(json.dumps(payload, sort_keys=True).encode("utf-8"))
    return hasher.hexdigest()


def _load_dynamic_specs_from_db(db: ModuleDatabase) -> tuple[SpaceSpec, ...]:
    with db.read_snapshot() as snap:
        rows = snap.query_all("SELECT owner, name, spec_json FROM dynamic_spaces")
    by_owner_name: dict[tuple[str, str], SpaceSpec] = {}
    owners: set[str] = set()
    for row in rows:
        owner_str = require_pure_str(row[0], "dynamic_spaces.owner")
        name_str = require_pure_str(row[1], "dynamic_spaces.name")
        raw_json = require_pure_str(row[2], "dynamic_spaces.spec_json")
        parsed_obj = strict_parse_json_object(raw_json)
        spec_obj = DataclassCodec.decode(SpaceSpec, parsed_obj)
        owners.add(owner_str)
        by_owner_name[(owner_str, name_str)] = spec_obj
    ordered_specs: list[SpaceSpec] = []
    for owner_k in spc_sort_owner_keys(tuple(owners)):
        names_for_owner = sorted(nm for ow, nm in by_owner_name if ow == owner_k)
        for nm in names_for_owner:
            ordered_specs.append(by_owner_name[(owner_k, nm)])
    return tuple(ordered_specs)


def _walk_own_entries(
    compiled: _SpcCompiledSpace,
    proj_root: Optional[HostPath],
    control_roots: SpcControlPlaneRoots,
    cancel_token: Optional[CancellationToken] = None,
) -> list[SpcRawFileRecord]:
    enforce_cp_carveout = compiled.spec.space_id.owner != "core"
    valid_pairs: list[tuple[SemanticUri, HostPath]] = []
    for res_ent in compiled.resolved_entries:
        if res_ent.host_path is not None:
            valid_pairs.append((res_ent.uri, res_ent.host_path))

    own_records: list[SpcRawFileRecord] = []
    seen_hps: set[HostPath] = set()
    visited_dirs: set[HostPath] = set()

    for ent_uri, ent_hp in valid_pairs:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        raw_ent = str(ent_hp)
        if is_symlink_or_reparse(raw_ent):
            continue
        try:
            ent_st = os.lstat(raw_ent)
        except OSError:
            continue

        if stat.S_ISREG(ent_st.st_mode):
            if is_atomic_staging_filename(ent_hp.path.name):
                continue
            if enforce_cp_carveout and spc_is_control_plane_reserved_path(ent_hp, control_roots, entry_hp=ent_hp):
                continue
            best_u, best_h = _select_deepest_entry_pair(ent_hp.path, (ent_uri, ent_hp), valid_pairs)
            if _is_file_matched_in_own_space(compiled, ent_hp, best_h, proj_root):
                rel_sp = _compute_space_rel_path(ent_hp, best_h, best_u, proj_root)
                if rel_sp is not None and ent_hp not in seen_hps:
                    seen_hps.add(ent_hp)
                    own_records.append(
                        SpcRawFileRecord(
                            rel_path=rel_sp,
                            abs_path=ent_hp,
                            size_bytes=max(0, int(ent_st.st_size)),
                            mtime_ns=max(0, int(ent_st.st_mtime_ns)),
                        )
                    )
            continue

        if not stat.S_ISDIR(ent_st.st_mode):
            continue
        if enforce_cp_carveout and spc_is_control_plane_reserved_path(ent_hp, control_roots, entry_hp=ent_hp):
            continue
        if _is_dir_pruned_for_space(compiled, ent_hp, ent_hp, proj_root):
            continue

        dir_stack: list[tuple[HostPath, SemanticUri, HostPath]] = [(ent_hp, ent_uri, ent_hp)]
        while dir_stack:
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            cur_dir, cur_ent_uri, cur_ent_hp = dir_stack.pop()
            if cur_dir in visited_dirs:
                continue
            visited_dirs.add(cur_dir)
            try:
                with os.scandir(str(cur_dir)) as scan_it:
                    dir_entries = sorted(scan_it, key=lambda d: d.name)
            except OSError:
                continue

            next_dirs: list[tuple[HostPath, SemanticUri, HostPath]] = []
            for d_ent in dir_entries:
                if (
                    d_ent.name.startswith(IGNORED_FS_PREFIXES)
                    or is_atomic_staging_filename(d_ent.name)
                    or d_ent.is_symlink()
                    or is_symlink_or_reparse(d_ent.path)
                ):
                    continue
                try:
                    child_hp = HostPath(d_ent.path)
                    is_sub_dir = d_ent.is_dir(follow_symlinks=False)
                except (OSError, ValueError):
                    continue

                best_uri, best_hp = _select_deepest_entry_pair(
                    child_hp.path,
                    (cur_ent_uri, cur_ent_hp),
                    valid_pairs,
                )
                if enforce_cp_carveout and spc_is_control_plane_reserved_path(child_hp, control_roots, entry_hp=best_hp):
                    continue
                if is_sub_dir:
                    if _is_dir_pruned_for_space(compiled, child_hp, best_hp, proj_root):
                        continue
                    next_dirs.append((child_hp, best_uri, best_hp))
                else:
                    try:
                        f_st = d_ent.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if not stat.S_ISREG(f_st.st_mode):
                        continue
                    if not _is_file_matched_in_own_space(compiled, child_hp, best_hp, proj_root):
                        continue
                    rel_sp = _compute_space_rel_path(child_hp, best_hp, best_uri, proj_root)
                    if rel_sp is not None and child_hp not in seen_hps:
                        seen_hps.add(child_hp)
                        own_records.append(
                            SpcRawFileRecord(
                                rel_path=rel_sp,
                                abs_path=child_hp,
                                size_bytes=max(0, int(f_st.st_size)),
                                mtime_ns=max(0, int(f_st.st_mtime_ns)),
                            )
                        )
            dir_stack.extend(reversed(next_dirs))
    return own_records


def _evaluate_space_file_set(
    sid: SpaceId,
    compiled_by_id: Mapping[SpaceId, _SpcCompiledSpace],
    proj_root: Optional[HostPath],
    control_roots: SpcControlPlaneRoots,
    memo: dict[SpaceId, tuple[SpcRawFileRecord, ...]],
    cancel_token: Optional[CancellationToken] = None,
) -> tuple[SpcRawFileRecord, ...]:
    cached = memo.get(sid)
    if cached is not None:
        return cached
    comp = compiled_by_id[sid]
    raw_candidates: list[SpcRawFileRecord] = _walk_own_entries(
        comp,
        proj_root,
        control_roots,
        cancel_token=cancel_token,
    )
    for pos_id in comp.pos_compose:
        raw_candidates.extend(
            _evaluate_space_file_set(pos_id, compiled_by_id, proj_root, control_roots, memo, cancel_token=cancel_token)
        )

    if comp.neg_compose and raw_candidates:
        filtered: list[SpcRawFileRecord] = []
        for rec in raw_candidates:
            excluded = False
            for neg_id in comp.neg_compose:
                if _explain_space_match_recursive(
                    compiled_by_id[neg_id],
                    compiled_by_id,
                    rec.abs_path,
                    proj_root,
                    control_roots,
                    is_dir=False,
                ).matched:
                    excluded = True
                    break
            if not excluded:
                filtered.append(rec)
        raw_candidates = filtered

    deduped: list[SpcRawFileRecord] = []
    used_rels: set[str] = set()
    for rec in raw_candidates:
        rel_key = os.path.normcase(str(rec.rel_path)) if IS_WINDOWS else str(rec.rel_path)
        if rel_key in used_rels:
            continue
        used_rels.add(rel_key)
        deduped.append(rec)

    result = tuple(deduped)
    memo[sid] = result
    return result


def _explain_space_match_recursive(
    comp: _SpcCompiledSpace,
    compiled_by_id: Mapping[SpaceId, _SpcCompiledSpace],
    target_abs: HostPath,
    proj_root: Optional[HostPath],
    control_roots: SpcControlPlaneRoots,
    *,
    is_dir: bool,
) -> SpaceMatchExplain:
    sid = comp.spec.space_id
    if is_symlink_or_reparse(str(target_abs)):
        return SpaceMatchExplain(space_id=sid, matched=False, reason="symlink_rejected")
    if not is_dir:
        try:
            t_st = os.lstat(str(target_abs))
        except OSError:
            t_st = None
        if t_st is not None and not stat.S_ISREG(t_st.st_mode) and not stat.S_ISDIR(t_st.st_mode):
            return SpaceMatchExplain(space_id=sid, matched=False, reason="non_regular_file")

    cand_entries: list[tuple[SemanticUri, HostPath]] = []
    saw_ignored_segment = False
    saw_entry_descendant = False
    for res_ent in comp.resolved_entries:
        ent_hp = res_ent.host_path
        if ent_hp is None:
            continue
        if spc_compute_rel_str(target_abs.path, ent_hp.path) is not None:
            if _has_intervening_symlink(target_abs.path, ent_hp.path):
                return SpaceMatchExplain(space_id=sid, matched=False, reason="symlink_rejected")
            if _has_ignored_space_segments(target_abs.path, ent_hp.path, is_dir=is_dir):
                saw_ignored_segment = True
                continue
            cand_entries.append((res_ent.uri, ent_hp))
        elif is_dir and bool(spc_compute_rel_str(ent_hp.path, target_abs.path)):
            saw_entry_descendant = True

    cand_entries.sort(key=lambda pair: len(pair[1].path.parts), reverse=True)
    best_failure: Optional[SpaceMatchExplain] = None
    pos_hit: Optional[SpaceMatchExplain] = None

    if cand_entries and sid.owner != "core":
        filtered_cands = [
            (u, h)
            for (u, h) in cand_entries
            if not spc_is_control_plane_reserved_path(target_abs, control_roots, entry_hp=h)
        ]
        if len(filtered_cands) != len(cand_entries):
            saw_ignored_segment = True
        cand_entries = filtered_cands

    for ent_uri, ent_hp in cand_entries:
        own_exp = _explain_file_in_own_entry(comp, target_abs, ent_uri, ent_hp, proj_root, is_dir=is_dir)
        if own_exp.matched:
            pos_hit = own_exp
            break
        if own_exp.matched_exclude is not None or best_failure is None:
            best_failure = own_exp

    if pos_hit is None:
        for pos_id in comp.pos_compose:
            pos_exp = _explain_space_match_recursive(
                compiled_by_id[pos_id],
                compiled_by_id,
                target_abs,
                proj_root,
                control_roots,
                is_dir=is_dir,
            )
            if pos_exp.matched:
                pos_hit = SpaceMatchExplain(
                    space_id=sid,
                    matched=True,
                    matched_entry=pos_exp.matched_entry,
                    matched_include=pos_exp.matched_include,
                    source_space=pos_exp.source_space if pos_exp.source_space is not None else pos_id,
                    reason="included",
                )
                break
            if best_failure is None and pos_exp.reason != "outside_entries":
                best_failure = SpaceMatchExplain(
                    space_id=sid,
                    matched=False,
                    matched_entry=pos_exp.matched_entry,
                    matched_exclude=pos_exp.matched_exclude,
                    source_space=pos_exp.source_space if pos_exp.source_space is not None else pos_id,
                    reason=pos_exp.reason,
                )

    if pos_hit is not None:
        for neg_id in comp.neg_compose:
            neg_exp = _explain_space_match_recursive(
                compiled_by_id[neg_id],
                compiled_by_id,
                target_abs,
                proj_root,
                control_roots,
                is_dir=is_dir,
            )
            if neg_exp.matched:
                return SpaceMatchExplain(
                    space_id=sid,
                    matched=False,
                    matched_entry=pos_hit.matched_entry,
                    matched_exclude=f"!{neg_id}",
                    source_space=neg_id,
                    reason="excluded_by_compose",
                )
        return pos_hit

    if best_failure is not None:
        return best_failure
    if saw_ignored_segment:
        return SpaceMatchExplain(space_id=sid, matched=False, reason="excluded")
    if saw_entry_descendant:
        return SpaceMatchExplain(space_id=sid, matched=False, reason="ancestor_of_entry")
    return SpaceMatchExplain(space_id=sid, matched=False, reason="outside_entries")


class SpaceRegistry:
    """Logical file space compiler and query registry merging static, dynamic, and overlay specs."""

    def __init__(
        self,
        vfs: KernelVfs,
        db: ModuleDatabase,
        *,
        static_specs: Sequence[SpaceSpec] = (),
    ) -> None:
        if not isinstance(vfs, KernelVfs):
            raise ValueError(f"SpaceRegistry requires KernelVfs, got {vfs!r}")
        spc_ensure_space_tables(db)
        self._vfs: KernelVfs = vfs
        self._db: ModuleDatabase = db
        self._static_specs: tuple[SpaceSpec, ...] = tuple(static_specs)
        self._overlay_specs: tuple[SpaceSpec, ...] = ()
        self._lock = threading.RLock()
        self._snap: _SpcRegistrySnapshot = _compile_all_spaces(
            self._vfs,
            self._static_specs,
            _load_dynamic_specs_from_db(self._db),
            self._overlay_specs,
        )
        _SpcRegistryInternals.update(self, self._lock, self._snap)

    def _init_overlay_instance(
        self,
        vfs: KernelVfs,
        db: ModuleDatabase,
        static_specs: tuple[SpaceSpec, ...],
        dynamic_specs: tuple[SpaceSpec, ...],
        overlay_specs: tuple[SpaceSpec, ...],
    ) -> None:
        self._vfs = vfs
        self._db = db
        self._static_specs = static_specs
        self._overlay_specs = overlay_specs
        self._lock = threading.RLock()
        self._snap = _compile_all_spaces(vfs, static_specs, dynamic_specs, overlay_specs)
        _SpcRegistryInternals.update(self, self._lock, self._snap)

    def _lookup_compiled(self, space_id: SpaceId | str) -> tuple[_SpcRegistrySnapshot, _SpcCompiledSpace]:
        norm_id = spc_normalize_space_id(space_id)
        with self._lock:
            snap = self._snap
        if norm_id is None or norm_id not in snap.compiled_by_id:
            raise YscbError(
                ErrorCode.SPACE_NOT_FOUND,
                f"Logical file space '{space_id}' is not registered.",
                remediation="Inspect registered spaces via SpaceRegistry.list_spaces().",
            )
        return (snap, snap.compiled_by_id[norm_id])

    def reload(self, static_specs: Optional[Sequence[SpaceSpec]] = None) -> None:
        with self._lock:
            eff_static = tuple(static_specs) if static_specs is not None else self._static_specs
            dyn_specs = _load_dynamic_specs_from_db(self._db)
            compiled_snap = _compile_all_spaces(self._vfs, eff_static, dyn_specs, self._overlay_specs)
            self._static_specs = eff_static
            self._snap = compiled_snap
            _SpcRegistryInternals.update(self, self._lock, compiled_snap)

    def with_overlay(self, extra_specs: Sequence[SpaceSpec]) -> SpaceRegistry:
        extra_tuple = tuple(extra_specs)
        with self._lock:
            base_static = self._static_specs
            base_dyn = self._snap.dynamic_specs
            combined_overlay = (*self._overlay_specs, *extra_tuple)
        clone = SpaceRegistry.__new__(SpaceRegistry)
        clone._init_overlay_instance(self._vfs, self._db, base_static, base_dyn, combined_overlay)
        return clone

    def set_dynamic_space(self, owner: ModuleId, name: str, spec: SpaceSpec) -> bool:
        if not isinstance(owner, ModuleId):
            raise ValueError(f"owner must be ModuleId, got {owner!r}")
        require_pure_str(name, "name")
        clean_name = name.strip()
        try:
            expected_id = SpaceId(owner.value, clean_name)
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
        if not isinstance(spec, SpaceSpec) or spec.space_id != expected_id:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"spec.space_id must match '{expected_id}', got {spec!r}",
            )
        is_ro = clean_name == "readonly"
        for entry_uri in spec.entries:
            violation = _check_space_uri_owner_boundary(entry_uri, owner.value, is_readonly_space=is_ro)
            if violation is not None:
                raise YscbError(ErrorCode.ACCESS_DENIED, violation)
        for raw_rule in (*spec.include, *spec.exclude):
            try:
                rule_uri = spc_extract_embedded_rule_uri(raw_rule)
            except ValueError as exc:
                raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid embedded URI in space rule {raw_rule!r}: {exc}") from exc
            if rule_uri is not None:
                rule_violation = _check_space_uri_owner_boundary(rule_uri, owner.value, is_readonly_space=is_ro)
                if rule_violation is not None:
                    raise YscbError(ErrorCode.ACCESS_DENIED, rule_violation)

        encoded_dict = DataclassCodec.encode(spec)
        spec_json = json.dumps(encoded_dict, sort_keys=True, ensure_ascii=False)

        with self._lock:
            with self._db.read_snapshot() as r_snap:
                existing_row = r_snap.query_one(
                    "SELECT spec_json FROM dynamic_spaces WHERE owner = ? AND name = ?",
                    (owner.value, clean_name),
                )
            if existing_row is not None and require_pure_str(existing_row[0], "spec_json") == spec_json:
                return False

            cur_dyn = [s for s in _load_dynamic_specs_from_db(self._db) if s.space_id != expected_id]
            cur_dyn.append(spec)
            cur_dyn_sorted = sorted(cur_dyn, key=lambda s: (spc_sort_owner_keys((s.space_id.owner,)), s.space_id.name))
            preview_snap = _compile_all_spaces(
                self._vfs,
                self._static_specs,
                tuple(cur_dyn_sorted),
                self._overlay_specs,
            )

            now_ns = time.time_ns()
            with self._db.write_transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO dynamic_spaces (owner, name, spec_json, updated_at_ns)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(owner, name) DO UPDATE SET
                        spec_json = excluded.spec_json,
                        updated_at_ns = excluded.updated_at_ns
                    """,
                    (owner.value, clean_name, spec_json, now_ns),
                )
            self._snap = preview_snap
            _SpcRegistryInternals.update(self, self._lock, preview_snap)
            return True

    def remove_dynamic_space(self, owner: ModuleId, name: str) -> bool:
        if not isinstance(owner, ModuleId):
            raise ValueError(f"owner must be ModuleId, got {owner!r}")
        require_pure_str(name, "name")
        clean_name = name.strip()
        if not clean_name:
            return False
        target_id = SpaceId(owner.value, clean_name)
        with self._lock:
            with self._db.read_snapshot() as r_snap:
                row = r_snap.query_one(
                    "SELECT 1 FROM dynamic_spaces WHERE owner = ? AND name = ?",
                    (owner.value, clean_name),
                )
            if row is None:
                return False
            remaining_dyn = [s for s in _load_dynamic_specs_from_db(self._db) if s.space_id != target_id]
            preview_snap = _compile_all_spaces(
                self._vfs,
                self._static_specs,
                tuple(remaining_dyn),
                self._overlay_specs,
            )
            with self._db.write_transaction() as tx:
                removed = tx.execute(
                    "DELETE FROM dynamic_spaces WHERE owner = ? AND name = ?",
                    (owner.value, clean_name),
                )
            if removed > 0:
                self._snap = preview_snap
                _SpcRegistryInternals.update(self, self._lock, preview_snap)
                return True
            return False

    def clear_dynamic_spaces(self, owner: ModuleId) -> int:
        if not isinstance(owner, ModuleId):
            raise ValueError(f"owner must be ModuleId, got {owner!r}")
        with self._lock:
            with self._db.read_snapshot() as r_snap:
                cnt_row = r_snap.query_one(
                    "SELECT COUNT(*) FROM dynamic_spaces WHERE owner = ?",
                    (owner.value,),
                )
            if cnt_row is None or int(cnt_row[0] or 0) == 0:
                return 0
            remaining_dyn = [s for s in _load_dynamic_specs_from_db(self._db) if s.space_id.owner != owner.value]
            preview_snap = _compile_all_spaces(
                self._vfs,
                self._static_specs,
                tuple(remaining_dyn),
                self._overlay_specs,
            )
            with self._db.write_transaction() as tx:
                deleted = tx.execute("DELETE FROM dynamic_spaces WHERE owner = ?", (owner.value,))
            if deleted > 0:
                self._snap = preview_snap
                _SpcRegistryInternals.update(self, self._lock, preview_snap)
            return deleted

    def list_spaces(self, *, owner: Optional[str] = None) -> tuple[SpaceSpec, ...]:
        with self._lock:
            specs = self._snap.ordered_specs
        if owner is None:
            return specs
        require_pure_str(owner, "owner")
        return tuple(s for s in specs if s.space_id.owner == owner)

    def get_space(self, space_id: SpaceId | str) -> SpaceSpec:
        _snap, comp = self._lookup_compiled(space_id)
        return comp.spec

    def config_hash(self, space_id: SpaceId | str) -> str:
        snap, comp = self._lookup_compiled(space_id)
        return snap.config_hashes[comp.spec.space_id]

    def match_path(self, space_id: SpaceId | str, target: HostPath | SemanticUri) -> SpaceMatchExplain:
        snap, comp = self._lookup_compiled(space_id)
        sid = comp.spec.space_id
        if isinstance(target, SemanticUri):
            bound = self._vfs.bind_uri(target) if target.uses_module_placeholder else target
            try:
                resolved_hp = self._vfs.try_get_physical_path(bound)
            except YscbError as exc:
                if exc.detail.code in (ErrorCode.ACCESS_DENIED, ErrorCode.SECURITY_GATED):
                    return SpaceMatchExplain(space_id=sid, matched=False, reason="symlink_rejected")
                raise
            if resolved_hp is None:
                return SpaceMatchExplain(space_id=sid, matched=False, reason="unphysical_uri")
            target_hp = resolved_hp
        elif isinstance(target, HostPath):
            target_hp = target
        else:
            raise ValueError(f"target must be HostPath or SemanticUri, got {target!r}")

        try:
            is_d = target_hp.path.is_dir()
        except OSError:
            is_d = False
        return _explain_space_match_recursive(comp, snap.compiled_by_id, target_hp, snap.proj_root, snap.control_roots, is_dir=is_d)

    def iter_files(self, space_id: SpaceId | str, *, pattern: Optional[str] = None) -> Iterator[SpaceFileEntry]:
        snap, comp = self._lookup_compiled(space_id)
        norm_pat: Optional[str] = None
        if pattern is not None:
            require_pure_str(pattern, "pattern")
            stripped_p = pattern.replace("\\", "/").strip("/")
            norm_pat = stripped_p if stripped_p else None

        file_recs = _evaluate_space_file_set(comp.spec.space_id, snap.compiled_by_id, snap.proj_root, snap.control_roots, {})
        ordered_recs = sorted(file_recs, key=lambda rec: str(rec.rel_path))

        def _gen() -> Iterator[SpaceFileEntry]:
            for rec in ordered_recs:
                rel_s = str(rec.rel_path)
                if norm_pat is not None:
                    if not (fnmatch.fnmatch(rel_s, norm_pat) or fnmatch.fnmatch(rec.abs_path.path.name, norm_pat)):
                        continue
                try:
                    c_hash = spc_compute_file_hash(
                        rec.abs_path,
                        size_bytes=rec.size_bytes,
                        mtime_ns=rec.mtime_ns,
                        policy=comp.spec.hash_policy,
                    )
                except OSError:
                    continue
                if c_hash is None:
                    continue
                yield SpaceFileEntry(
                    rel_path=rec.rel_path,
                    abs_path=rec.abs_path,
                    size_bytes=rec.size_bytes,
                    mtime_ns=rec.mtime_ns,
                    content_hash=c_hash,
                )

        return _gen()

    def resolve_file_path(self, space_id: SpaceId | str, rel_path: SpacePath | str) -> HostPath:
        snap, comp = self._lookup_compiled(space_id)
        sp = rel_path if isinstance(rel_path, SpacePath) else SpacePath.parse(rel_path)
        for resolved_hp in _resolve_candidates_in_space(comp.spec.space_id, sp, snap):
            return resolved_hp
        raise YscbError(
            ErrorCode.SPACE_NOT_FOUND,
            f"Relative path '{sp}' does not resolve to an active file in space '{comp.spec.space_id}'.",
        )

    def collect_watch_roots(self) -> tuple[HostPath, ...]:
        with self._lock:
            snap = self._snap
        seed_stack: list[SpaceId] = [
            sid
            for sid, comp in snap.compiled_by_id.items()
            if sid.owner != "" and comp.spec.watch and sid.name not in ("gitignore", "readonly")
        ]
        watched_closure: set[SpaceId] = set()
        while seed_stack:
            cur_sid = seed_stack.pop()
            if cur_sid in watched_closure:
                continue
            watched_closure.add(cur_sid)
            cur_comp = snap.compiled_by_id.get(cur_sid)
            if cur_comp is not None:
                seed_stack.extend(cur_comp.pos_compose)

        raw_roots: list[HostPath] = []
        for sid in watched_closure:
            comp = snap.compiled_by_id[sid]
            for res_ent in comp.resolved_entries:
                hp = res_ent.host_path
                if hp is not None and hp not in raw_roots:
                    raw_roots.append(hp)

        ordered = sorted(raw_roots, key=lambda p: (len(p.path.parts), p.comparison_key))
        minimal: list[HostPath] = []
        dir_prefixes: list[str] = []
        for cand in ordered:
            norm_key = cand.comparison_key.rstrip("/\\")
            if any(norm_key == pfx or norm_key.startswith(f"{pfx}{os.sep}") for pfx in dir_prefixes):
                continue
            minimal.append(cand)
            try:
                is_reg_file = cand.path.is_file()
            except OSError:
                is_reg_file = False
            if not is_reg_file:
                dir_prefixes.append(norm_key)
        return tuple(sorted(minimal, key=lambda p: p.comparison_key))

    @staticmethod
    def build_stateless_readonly_matcher(
        vfs: KernelVfs,
        *,
        static_specs: Sequence[SpaceSpec] = (),
        dynamic_db_path: Optional[HostPath] = None,
        reserved_filter: Optional[Callable[[HostPath, str], bool]] = None,
    ) -> Callable[[HostPath], bool]:
        """Build a connection-free ReadonlyPolicy matcher over static and persisted dynamic spaces."""
        if not isinstance(vfs, KernelVfs):
            raise ValueError(f"Expected KernelVfs, got {vfs!r}")
        dyn_specs: tuple[SpaceSpec, ...] = ()
        if dynamic_db_path is not None:
            raw_db = str(dynamic_db_path)
            if os.path.isfile(raw_db) and not is_symlink_or_reparse(raw_db):
                rows: list[tuple[object, object, object]] = []
                try:
                    with closing(sqlite3.connect(raw_db, timeout=5.0)) as conn:
                        cur = conn.execute("SELECT owner, name, spec_json FROM dynamic_spaces")
                        rows = [(r[0], r[1], r[2]) for r in cur.fetchall()]
                except (OSError, sqlite3.Error):
                    rows = []
                by_owner_name: dict[tuple[str, str], SpaceSpec] = {}
                owners: set[str] = set()
                for row in rows:
                    try:
                        owner_s = require_pure_str(row[0], "dynamic_spaces.owner")
                        name_s = require_pure_str(row[1], "dynamic_spaces.name")
                        spec_s = require_pure_str(row[2], "dynamic_spaces.spec_json")
                        spec_obj = DataclassCodec.decode(SpaceSpec, strict_parse_json_object(spec_s))
                    except (ValueError, YscbError):
                        continue
                    owners.add(owner_s)
                    by_owner_name[(owner_s, name_s)] = spec_obj
                ordered_dyn: list[SpaceSpec] = []
                for ow_k in spc_sort_owner_keys(tuple(owners)):
                    for nm_k in sorted(nm for ow, nm in by_owner_name if ow == ow_k):
                        ordered_dyn.append(by_owner_name[(ow_k, nm_k)])
                dyn_specs = tuple(ordered_dyn)
        try:
            snap = _compile_all_spaces(vfs, static_specs, dyn_specs, ())
        except YscbError:
            ro_only_static = tuple(
                replace_sp
                for replace_sp in (
                    SpaceSpec(
                        space_id=sp.space_id,
                        entries=sp.entries,
                        include=sp.include,
                        exclude=sp.exclude,
                        watch=sp.watch,
                        hash_policy=sp.hash_policy,
                        description=sp.description,
                    )
                    for sp in static_specs
                    if sp.space_id.name == "readonly"
                )
            )
            ro_only_dyn = tuple(
                SpaceSpec(
                    space_id=sp.space_id,
                    entries=sp.entries,
                    include=sp.include,
                    exclude=sp.exclude,
                    watch=sp.watch,
                    hash_policy=sp.hash_policy,
                    description=sp.description,
                )
                for sp in dyn_specs
                if sp.space_id.name == "readonly"
            )
            try:
                snap = _compile_all_spaces(vfs, ro_only_static, ro_only_dyn, ())
            except YscbError:
                return lambda _hp: False

        ro_compiled = tuple(
            snap.compiled_by_id[sp.space_id]
            for sp in snap.ordered_specs
            if sp.space_id.owner != "" and sp.space_id.name == "readonly"
        )
        if not ro_compiled:
            return lambda _hp: False

        def _matches_ro(hp: HostPath) -> bool:
            for comp in ro_compiled:
                owner = comp.spec.space_id.owner
                if owner != "core" and reserved_filter is not None and reserved_filter(hp, owner):
                    continue
                try:
                    if _explain_space_match_recursive(
                        comp,
                        snap.compiled_by_id,
                        hp,
                        snap.proj_root,
                        snap.control_roots,
                        is_dir=False,
                    ).matched:
                        return True
                except YscbError:
                    continue
            return False

        return _matches_ro


def _space_path_matches_query(computed: Optional[SpacePath], query: SpacePath) -> bool:
    if computed is None:
        return False
    if IS_WINDOWS:
        return os.path.normcase(str(computed)) == os.path.normcase(str(query))
    return computed == query


def _resolve_candidates_in_space(
    sid: SpaceId,
    sp: SpacePath,
    snap: _SpcRegistrySnapshot,
) -> list[HostPath]:
    comp = snap.compiled_by_id[sid]
    rel_str = str(sp)
    own_pairs = [(re_ent.uri, re_ent.host_path) for re_ent in comp.resolved_entries if re_ent.host_path is not None]

    own_cands: list[tuple[HostPath, SemanticUri, HostPath]] = []
    for ent_uri, base_hp in own_pairs:
        raw_b = str(base_hp)
        if is_symlink_or_reparse(raw_b):
            continue
        if base_hp.path.is_file():
            best_u, best_h = _select_deepest_entry_pair(base_hp.path, (ent_uri, base_hp), own_pairs)
            if _space_path_matches_query(_compute_space_rel_path(base_hp, best_h, best_u, snap.proj_root), sp):
                own_cands.append((base_hp, ent_uri, base_hp))
            continue
        if snap.proj_root is not None:
            if spc_compute_rel_str(base_hp.path, snap.proj_root.path) is not None:
                try:
                    proj_cand = snap.proj_root.join(rel_str)
                    if spc_compute_rel_str(proj_cand.path, base_hp.path) is not None:
                        own_cands.append((proj_cand, ent_uri, base_hp))
                except ValueError:
                    pass
                continue
            if bool(spc_compute_rel_str(snap.proj_root.path, base_hp.path)):
                try:
                    proj_cand = snap.proj_root.join(rel_str)
                    if spc_compute_rel_str(proj_cand.path, base_hp.path) is not None:
                        own_cands.append((proj_cand, ent_uri, base_hp))
                except ValueError:
                    pass
        ext_pfx = base_hp.path.name
        if not is_valid_relative_segment(ext_pfx):
            ext_pfx = ent_uri.scheme.replace(".", "_")
        if is_valid_relative_segment(ext_pfx):
            pfx_slash = f"{ext_pfx}/"
            matches_pfx = (
                os.path.normcase(rel_str).startswith(os.path.normcase(pfx_slash))
                if IS_WINDOWS
                else rel_str.startswith(pfx_slash)
            )
            if matches_pfx:
                tail = rel_str[len(pfx_slash) :]
                if tail:
                    try:
                        own_cands.append((base_hp.join(tail), ent_uri, base_hp))
                    except ValueError:
                        pass
        else:
            try:
                own_cands.append((base_hp.join(rel_str), ent_uri, base_hp))
            except ValueError:
                pass

    matched_hps: list[HostPath] = []
    seen_hps: set[HostPath] = set()
    for cand_hp, ent_uri, ent_hp in own_cands:
        if cand_hp in seen_hps or is_atomic_staging_filename(cand_hp.path.name):
            continue
        if sid.owner != "core" and spc_is_control_plane_reserved_path(cand_hp, snap.control_roots, entry_hp=ent_hp):
            continue
        raw_c = str(cand_hp)
        if is_symlink_or_reparse(raw_c):
            continue
        try:
            st = os.lstat(raw_c)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode):
            continue
        if _has_intervening_symlink(cand_hp.path, ent_hp.path) or _has_ignored_space_segments(
            cand_hp.path, ent_hp.path, is_dir=False
        ):
            continue
        best_uri, best_hp = _select_deepest_entry_pair(cand_hp.path, (ent_uri, ent_hp), own_pairs)
        if not _space_path_matches_query(_compute_space_rel_path(cand_hp, best_hp, best_uri, snap.proj_root), sp):
            continue
        if _is_file_matched_in_own_space(comp, cand_hp, best_hp, snap.proj_root):
            seen_hps.add(cand_hp)
            matched_hps.append(cand_hp)

    for pos_id in comp.pos_compose:
        for child_hp in _resolve_candidates_in_space(pos_id, sp, snap):
            if child_hp not in seen_hps:
                seen_hps.add(child_hp)
                matched_hps.append(child_hp)

    if comp.neg_compose and matched_hps:
        survived: list[HostPath] = []
        for cand_hp in matched_hps:
            if any(
                _explain_space_match_recursive(
                    snap.compiled_by_id[neg_id],
                    snap.compiled_by_id,
                    cand_hp,
                    snap.proj_root,
                    snap.control_roots,
                    is_dir=False,
                ).matched
                for neg_id in comp.neg_compose
            ):
                continue
            survived.append(cand_hp)
        return survived[:1]
    return matched_hps[:1]


class SpcCapturedRegistryView:
    """Immutable atomic snapshot view of SpaceRegistry for tear-free SpaceScanner execution."""

    def __init__(self, snap: _SpcRegistrySnapshot) -> None:
        self._snap = snap

    def list_spaces(self) -> tuple[SpaceSpec, ...]:
        return self._snap.ordered_specs

    def get_space(self, space_id: SpaceId | str) -> SpaceSpec:
        norm_id = spc_normalize_space_id(space_id)
        if norm_id is None or norm_id not in self._snap.compiled_by_id:
            raise YscbError(
                ErrorCode.SPACE_NOT_FOUND,
                f"Logical file space '{space_id}' is not registered.",
                remediation="Inspect registered spaces via SpaceRegistry.list_spaces().",
            )
        return self._snap.compiled_by_id[norm_id].spec

    def config_hash(self, space_id: SpaceId | str) -> str:
        spec = self.get_space(space_id)
        return self._snap.config_hashes[spec.space_id]

    def match_path(self, space_id: SpaceId | str, target_hp: HostPath) -> SpaceMatchExplain:
        spec = self.get_space(space_id)
        comp = self._snap.compiled_by_id[spec.space_id]
        try:
            is_d = target_hp.path.is_dir()
        except OSError:
            is_d = False
        return _explain_space_match_recursive(
            comp,
            self._snap.compiled_by_id,
            target_hp,
            self._snap.proj_root,
            self._snap.control_roots,
            is_dir=is_d,
        )

    def collect_positive_closure(self, root_sid: SpaceId) -> tuple[SpaceId, ...]:
        visited: list[SpaceId] = []
        stack: list[SpaceId] = [root_sid]
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.append(cur)
            cur_comp = self._snap.compiled_by_id[cur]
            stack.extend(reversed(cur_comp.pos_compose))
        return tuple(visited)

    def iter_raw_files(
        self,
        space_id: SpaceId,
        *,
        cancel_token: Optional[CancellationToken] = None,
    ) -> tuple[SpcRawFileRecord, ...]:
        _ = self.get_space(space_id)
        recs = _evaluate_space_file_set(
            space_id,
            self._snap.compiled_by_id,
            self._snap.proj_root,
            self._snap.control_roots,
            {},
            cancel_token=cancel_token,
        )
        return tuple(sorted(recs, key=lambda r: str(r.rel_path)))

    def extract_gitignore_rules(self) -> dict[str, tuple[tuple[SpcRuleItem, ...], tuple[SpcRuleItem, ...]]]:
        out: dict[str, tuple[tuple[SpcRuleItem, ...], tuple[SpcRuleItem, ...]]] = {}
        for sid, comp in self._snap.compiled_by_id.items():
            if sid.owner != "" and sid.name == "gitignore":
                out[sid.owner] = (comp.effective_include, comp.effective_exclude)
        return out


class _SpcRegistryInternals:
    entries: ClassVar[WeakKeyDictionary[SpaceRegistry, tuple[threading.RLock, _SpcRegistrySnapshot]]] = (
        WeakKeyDictionary()
    )

    @classmethod
    def update(cls, reg: SpaceRegistry, lock: threading.RLock, snap: _SpcRegistrySnapshot) -> None:
        cls.entries[reg] = (lock, snap)

    @classmethod
    def capture(cls, reg: SpaceRegistry) -> SpcCapturedRegistryView:
        pair = cls.entries.get(reg)
        if pair is None:
            raise RuntimeError("SpaceRegistry internal snapshot is not initialized.")
        lock, _ = pair
        with lock:
            _, latest = cls.entries[reg]
        return SpcCapturedRegistryView(latest)


def spc_capture_registry_view(registry: SpaceRegistry) -> SpcCapturedRegistryView:
    """Capture an atomic lock-consistent snapshot view of SpaceRegistry."""
    return _SpcRegistryInternals.capture(registry)


def spc_compile_gitignore_rules(
    registry: SpaceRegistry,
) -> dict[str, tuple[tuple[SpcRuleItem, ...], tuple[SpcRuleItem, ...]]]:
    """Extract precompiled effective include/exclude rules per <owner>/gitignore space."""
    return spc_capture_registry_view(registry).extract_gitignore_rules()
