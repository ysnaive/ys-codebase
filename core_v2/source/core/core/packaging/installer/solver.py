"""Backtracking dependency constraint intersection solver and installed-state self-healing engine."""

from __future__ import annotations

from dataclasses import dataclass
import os
import stat
from types import MappingProxyType
from typing import Final, Mapping, Optional, Sequence

from core.filesystem.fs import is_symlink_or_reparse, try_resolve_contained_subpath
from core.foundation.errors import ErrorCode, YscbError
from core.foundation.primitives import (
    HostPath,
    ModuleId,
    SemVer4,
    VersionConstraint,
    require_pure_bool,
    require_typed_tuple,
)
from core.packaging.installer.mirror import MirrorStore
from core.packaging.installer.models import (
    INS_NON_FALLBACK_ERROR_CODES,
    IndexReleaseRecord,
    PackageRequest,
    RemoteModuleIndex,
    ins_assert_not_reserved_module_id,
    ins_has_dependencies_override,
    ins_is_build_request,
    ins_peek_zip_manifest,
    ins_read_manifest_file,
)
from core.packaging.installer.provider import ProviderClient

_CORE_MODULE_ID: Final[ModuleId] = ModuleId("core")
_MAX_SOLVER_STEPS: Final[int] = 4096
_RANGE_OP_PREFIXES: Final[tuple[str, ...]] = (">=", "<=", "!=", "~=", "^=", "^", ">", "<")


@dataclass(frozen=True, slots=True)
class _InsCandidateOption:
    version: SemVer4
    release_record: Optional[IndexReleaseRecord]
    dependencies: Mapping[ModuleId, VersionConstraint]


class _InsSolverContext:
    """Per-invocation memoized index, local manifest resolver, and immutable search constraints."""

    def __init__(
        self,
        *,
        yscb_root: HostPath,
        installed: Mapping[ModuleId, SemVer4],
        provider: ProviderClient,
        mirror: MirrorStore,
        provider_overrides: Mapping[ModuleId, str],
        same_major_only: bool,
    ) -> None:
        self.yscb_root = yscb_root
        self.installed = dict(installed)
        self.provider = provider
        self.mirror = mirror
        self.provider_overrides = dict(provider_overrides)
        self.same_major_only = same_major_only
        self.explicit_targets: frozenset[ModuleId] = frozenset()
        self.root_constraints: dict[ModuleId, list[VersionConstraint]] = {}
        self.pinned_modules: frozenset[ModuleId] = frozenset()
        self.baseline_deps: dict[ModuleId, Mapping[ModuleId, VersionConstraint]] = {}
        self.index_cache: dict[ModuleId, RemoteModuleIndex] = {}
        self.local_deps_cache: dict[tuple[ModuleId, SemVer4], Mapping[ModuleId, VersionConstraint]] = {}
        self.steps: int = 0
        self.failure_notes: list[str] = []

    def get_index(self, module_id: ModuleId) -> RemoteModuleIndex:
        cached = self.index_cache.get(module_id)
        if cached is not None:
            return cached
        prov_ov = self.provider_overrides.get(module_id)
        try:
            fetched = self.provider.fetch_index(module_id, provider=prov_ov)
            self.mirror.save_index_cache(fetched)
            self.index_cache[module_id] = fetched
            return fetched
        except YscbError as exc:
            if exc.detail.code in INS_NON_FALLBACK_ERROR_CODES:
                raise
            mirror_idx = self.mirror.load_index_cache(module_id)
            if mirror_idx is not None:
                self.index_cache[module_id] = mirror_idx
                return mirror_idx
            raise YscbError(
                ErrorCode.DEPENDENCY_CONFLICT,
                f"Unable to load release index for '{module_id}': {exc.detail.message}",
            ) from exc

    def read_local_dependencies_fast(
        self,
        module_id: ModuleId,
        version: SemVer4,
    ) -> Optional[Mapping[ModuleId, VersionConstraint]]:
        key = (module_id, version)
        if key in self.local_deps_cache:
            return self.local_deps_cache[key]
        mirror_idx = self.mirror.load_index_cache(module_id)
        if mirror_idx is not None:
            rel_rec = mirror_idx.releases.get(str(version))
            if ins_has_dependencies_override(rel_rec) and rel_rec is not None:
                self.local_deps_cache[key] = rel_rec.dependencies
                return rel_rec.dependencies
        if self.mirror.has_package(module_id, version):
            zip_hp = self.mirror.get_package_path(module_id, version)
            mf_zip = ins_peek_zip_manifest(
                zip_hp,
                expected_module_id=module_id,
                expected_version=None if version.is_build else version,
            )
            self.local_deps_cache[key] = mf_zip.dependencies
            return mf_zip.dependencies
        mod_mf_hp = try_resolve_contained_subpath(
            self.yscb_root,
            ".modules",
            module_id.value,
            "manifest.json",
        )
        if mod_mf_hp is not None:
            mf = ins_read_manifest_file(mod_mf_hp, expected_module_id=module_id)
            if mf is not None and (mf.version == version or version.is_build):
                self.local_deps_cache[key] = mf.dependencies
                return mf.dependencies
        return None

    def read_effective_dependencies(
        self,
        module_id: ModuleId,
        version: SemVer4,
    ) -> Mapping[ModuleId, VersionConstraint]:
        fast = self.read_local_dependencies_fast(module_id, version)
        if fast is not None:
            return fast
        if version.is_build:
            cand = self.resolve_build_option(module_id, None)
            self.local_deps_cache[(module_id, version)] = cand.dependencies
            return cand.dependencies
        idx = self.get_index(module_id)
        rel_rec = idx.releases.get(str(version))
        if ins_has_dependencies_override(rel_rec) and rel_rec is not None:
            self.local_deps_cache[(module_id, version)] = rel_rec.dependencies
            return rel_rec.dependencies
        self.local_deps_cache[(module_id, version)] = MappingProxyType({})
        return self.local_deps_cache[(module_id, version)]

    def resolve_build_option(
        self,
        module_id: ModuleId,
        version_spec: Optional[str],
    ) -> _InsCandidateOption:
        requested_triple: Optional[tuple[int, ...]] = None
        if version_spec is not None:
            cleaned = version_spec.strip().lstrip("=")
            if cleaned and cleaned not in ("build", "@build"):
                try:
                    parsed_req = SemVer4.parse(cleaned)
                    requested_triple = parsed_req.triple()
                except ValueError as exc:
                    raise YscbError(
                        ErrorCode.DEPENDENCY_CONFLICT,
                        f"Invalid @build version specification '{version_spec}' for '{module_id}': {exc}",
                    ) from exc

        build_root = try_resolve_contained_subpath(self.yscb_root, ".build")
        if build_root is not None and os.path.isdir(str(build_root)):
            zip_cands: list[HostPath] = []
            exact_b_name = (
                f"{requested_triple[0]}.{requested_triple[1]}.{requested_triple[2]}.build.zip"
                if requested_triple is not None
                else None
            )
            for direct in (
                try_resolve_contained_subpath(build_root, f"{module_id.value}.zip"),
                try_resolve_contained_subpath(build_root, f"{module_id.value}.build.zip"),
                (
                    try_resolve_contained_subpath(build_root, module_id.value, exact_b_name)
                    if exact_b_name is not None
                    else None
                ),
            ):
                if direct is not None and os.path.isfile(str(direct)) and not is_symlink_or_reparse(str(direct)):
                    zip_cands.append(direct)
            mod_build_dir = try_resolve_contained_subpath(build_root, module_id.value)
            if mod_build_dir is not None and os.path.isdir(str(mod_build_dir)) and not is_symlink_or_reparse(str(mod_build_dir)):
                timed: list[tuple[float, HostPath]] = []
                try:
                    with os.scandir(str(mod_build_dir)) as it:
                        for ent in it:
                            if ent.is_symlink() or not ent.name.endswith(".zip"):
                                continue
                            try:
                                st = ent.stat(follow_symlinks=False)
                            except OSError:
                                continue
                            if stat.S_ISREG(st.st_mode):
                                sub_hp = try_resolve_contained_subpath(mod_build_dir, ent.name)
                                if sub_hp is not None and sub_hp not in zip_cands:
                                    timed.append((st.st_mtime, sub_hp))
                except OSError:
                    timed = []
                timed.sort(key=lambda pair: pair[0], reverse=True)
                zip_cands.extend(hp for _mt, hp in timed)
            for b_zip in zip_cands:
                mf = ins_peek_zip_manifest(b_zip, expected_module_id=module_id)
                b_ver = SemVer4(mf.version.major, mf.version.minor, mf.version.patch, 0, is_build=True)
                if requested_triple is None or b_ver.triple() == requested_triple:
                    return _InsCandidateOption(version=b_ver, release_record=None, dependencies=mf.dependencies)

        src_mf_hp = try_resolve_contained_subpath(self.yscb_root, "source", module_id.value, "manifest.json")
        if src_mf_hp is not None:
            src_mf = ins_read_manifest_file(src_mf_hp, expected_module_id=module_id)
            if src_mf is not None:
                b_ver = SemVer4(src_mf.version.major, src_mf.version.minor, src_mf.version.patch, 0, is_build=True)
                if requested_triple is None or b_ver.triple() == requested_triple:
                    return _InsCandidateOption(
                        version=b_ver,
                        release_record=None,
                        dependencies=src_mf.dependencies,
                    )

        raise YscbError(
            ErrorCode.DEPENDENCY_CONFLICT,
            f"Local @build package or matching source manifest not found for '{module_id}'.",
        )


def _derive_yscb_root_from_mirror(mirror: MirrorStore) -> HostPath:
    probe_zip = mirror.get_package_path(_CORE_MODULE_ID, SemVer4(0, 0, 0))
    return HostPath(str(probe_zip.path.parent.parent.parent))


def _is_explicit_exact_pin(version_spec: Optional[str]) -> bool:
    if version_spec is None:
        return False
    cleaned = version_spec.strip()
    if not cleaned or "," in cleaned or "*" in cleaned:
        return False
    if cleaned.startswith(_RANGE_OP_PREFIXES):
        return False
    if cleaned.startswith("=="):
        target = cleaned[2:].strip()
    elif cleaned.startswith("="):
        target = cleaned[1:].strip()
    else:
        target = cleaned
    try:
        parsed = SemVer4.parse(target)
    except ValueError:
        return False
    return not parsed.is_build


def _parse_request_constraint(version_spec: Optional[str], *, module_id: ModuleId) -> VersionConstraint:
    if version_spec is None or not version_spec.strip():
        return VersionConstraint.parse("*")
    cleaned = version_spec.strip()
    try:
        return VersionConstraint.parse(cleaned)
    except ValueError as exc:
        raise YscbError(
            ErrorCode.DEPENDENCY_CONFLICT,
            f"Invalid version constraint {version_spec!r} for '{module_id}': {exc}",
        ) from exc


def _satisfies_all(ver: SemVer4, constraints: Sequence[VersionConstraint]) -> bool:
    if ver.is_build:
        return True
    return all(c.satisfies(ver) for c in constraints)


def _module_priority_key(mod_id: ModuleId) -> tuple[int, str]:
    return (0 if mod_id == _CORE_MODULE_ID else 1, mod_id.value)


def _build_candidate_options(
    ctx: _InsSolverContext,
    mod_id: ModuleId,
    constraints: Sequence[VersionConstraint],
    *,
    allow_yanked: bool,
    prefer_same_major_as: Optional[SemVer4],
    min_version: Optional[SemVer4] = None,
) -> list[_InsCandidateOption]:
    idx = ctx.get_index(mod_id)
    seen_vers: set[SemVer4] = set()
    raw_pool: list[SemVer4] = []
    for v in idx.versions:
        if not v.is_build and v not in seen_vers:
            seen_vers.add(v)
            raw_pool.append(v)
    if allow_yanked:
        for rec in idx.releases.values():
            if not rec.version.is_build and rec.version not in seen_vers:
                seen_vers.add(rec.version)
                raw_pool.append(rec.version)

    enforce_min = min_version if (min_version is not None and not min_version.is_build) else None
    valid_options: list[_InsCandidateOption] = []
    for cand_v in sorted(raw_pool, reverse=True):
        if enforce_min is not None and cand_v < enforce_min:
            continue
        rel_rec = idx.releases.get(str(cand_v))
        if rel_rec is not None:
            if rel_rec.status == "pruned" and not ctx.mirror.has_package(mod_id, cand_v):
                continue
            if rel_rec.yanked and not allow_yanked:
                continue
        if not _satisfies_all(cand_v, constraints):
            continue
        deps: Mapping[ModuleId, VersionConstraint]
        if ins_has_dependencies_override(rel_rec) and rel_rec is not None:
            deps = rel_rec.dependencies
        elif ctx.mirror.has_package(mod_id, cand_v):
            deps = ins_peek_zip_manifest(
                ctx.mirror.get_package_path(mod_id, cand_v),
                expected_module_id=mod_id,
                expected_version=cand_v,
            ).dependencies
        else:
            local_fast = (
                ctx.read_local_dependencies_fast(mod_id, cand_v)
                if ctx.installed.get(mod_id) == cand_v
                else None
            )
            deps = local_fast if local_fast is not None else MappingProxyType({})
        valid_options.append(
            _InsCandidateOption(
                version=cand_v,
                release_record=rel_rec,
                dependencies=deps,
            )
        )

    if prefer_same_major_as is not None and not prefer_same_major_as.is_build:
        same_maj = [opt for opt in valid_options if opt.version.major == prefer_same_major_as.major]
        cross_maj = [opt for opt in valid_options if opt.version.major != prefer_same_major_as.major]
        ordered_options = [*same_maj, *cross_maj]
    else:
        ordered_options = valid_options

    if ctx.same_major_only:
        cur_inst = ctx.installed.get(mod_id)
        if (
            cur_inst is not None
            and not cur_inst.is_build
            and all(opt.version != cur_inst for opt in ordered_options)
            and (enforce_min is None or cur_inst >= enforce_min)
            and _satisfies_all(cur_inst, constraints)
        ):
            local_deps = ctx.read_local_dependencies_fast(mod_id, cur_inst)
            if local_deps is not None:
                ordered_options.append(
                    _InsCandidateOption(
                        version=cur_inst,
                        release_record=idx.releases.get(str(cur_inst)),
                        dependencies=local_deps,
                    )
                )
    return ordered_options


def _collect_active_constraints(
    ctx: _InsSolverContext,
    chosen: Mapping[ModuleId, _InsCandidateOption],
) -> dict[ModuleId, list[VersionConstraint]]:
    merged: dict[ModuleId, list[VersionConstraint]] = {
        m: list(cs) for m, cs in ctx.root_constraints.items()
    }
    for _mod_id, opt in chosen.items():
        for dep_id, dep_c in opt.dependencies.items():
            merged.setdefault(dep_id, []).append(dep_c)
    for mod_id, deps in ctx.baseline_deps.items():
        if mod_id in chosen:
            continue
        for dep_id, dep_c in deps.items():
            merged.setdefault(dep_id, []).append(dep_c)
    return merged


def _try_promote_blocking_holders(
    ctx: _InsSolverContext,
    target_mod: ModuleId,
    active_constraints: Mapping[ModuleId, list[VersionConstraint]],
    chosen: dict[ModuleId, _InsCandidateOption],
    blocked_holders: frozenset[ModuleId],
) -> Optional[dict[ModuleId, _InsCandidateOption]]:
    holder_candidates: list[ModuleId] = []
    for holder_mod, holder_deps in ctx.baseline_deps.items():
        if (
            holder_mod in chosen
            or holder_mod in ctx.explicit_targets
            or holder_mod in blocked_holders
            or target_mod not in holder_deps
        ):
            continue
        holder_cur = ctx.installed.get(holder_mod)
        if holder_cur is None or holder_cur.is_build:
            continue
        holder_candidates.append(holder_mod)

    holder_candidates.sort(key=_module_priority_key)
    exhausted_local: set[ModuleId] = set(blocked_holders)
    for holder_mod in holder_candidates:
        holder_cur = ctx.installed[holder_mod]
        holder_reqs = list(active_constraints.get(holder_mod, ()))
        if ctx.same_major_only:
            holder_reqs.append(VersionConstraint.compatible_same_major(holder_cur))
        try:
            raw_opts = _build_candidate_options(
                ctx,
                holder_mod,
                holder_reqs,
                allow_yanked=False,
                prefer_same_major_as=(holder_cur if not ctx.same_major_only else None),
                min_version=holder_cur,
            )
        except YscbError as exc:
            if exc.detail.code in INS_NON_FALLBACK_ERROR_CODES:
                raise
            exhausted_local.add(holder_mod)
            continue
        upgrade_opts = [opt for opt in raw_opts if opt.version > holder_cur]
        for h_opt in upgrade_opts:
            chosen[holder_mod] = h_opt
            solved = _search_satisfying_plan(ctx, chosen, frozenset(exhausted_local))
            if solved is not None:
                return solved
            del chosen[holder_mod]
        exhausted_local.add(holder_mod)
    return None


def _search_satisfying_plan(
    ctx: _InsSolverContext,
    chosen: dict[ModuleId, _InsCandidateOption],
    blocked_holders: frozenset[ModuleId],
) -> Optional[dict[ModuleId, _InsCandidateOption]]:
    ctx.steps += 1
    if ctx.steps > _MAX_SOLVER_STEPS:
        raise YscbError(
            ErrorCode.DEPENDENCY_CONFLICT,
            "Dependency solver exceeded maximum backtracking search budget.",
        )

    active_constraints = _collect_active_constraints(ctx, chosen)

    for assigned_mod, assigned_opt in list(chosen.items()):
        reqs = active_constraints.get(assigned_mod, ())
        if not _satisfies_all(assigned_opt.version, reqs):
            promoted = _try_promote_blocking_holders(
                ctx,
                assigned_mod,
                active_constraints,
                chosen,
                blocked_holders,
            )
            if promoted is not None:
                return promoted
            ctx.failure_notes.append(
                f"{assigned_mod}@{assigned_opt.version} violates [{', '.join(str(c) for c in reqs)}]"
            )
            return None

    next_mod: Optional[ModuleId] = None
    candidate_mods = sorted(
        set(ctx.explicit_targets) | set(active_constraints.keys()),
        key=_module_priority_key,
    )
    for cand_mod in candidate_mods:
        if cand_mod in chosen:
            continue
        if cand_mod in ctx.explicit_targets:
            next_mod = cand_mod
            break
        cur_inst_v = ctx.installed.get(cand_mod)
        reqs = active_constraints.get(cand_mod, ())
        if cur_inst_v is None or not _satisfies_all(cur_inst_v, reqs):
            next_mod = cand_mod
            break

    if next_mod is None:
        return dict(chosen)

    mod_constraints = list(active_constraints.get(next_mod, ()))
    cur_ver = ctx.installed.get(next_mod)
    if ctx.same_major_only and cur_ver is not None and not cur_ver.is_build:
        mod_constraints.append(VersionConstraint.compatible_same_major(cur_ver))

    min_floor = cur_ver if next_mod not in ctx.explicit_targets else None
    options = _build_candidate_options(
        ctx,
        next_mod,
        mod_constraints,
        allow_yanked=(next_mod in ctx.pinned_modules),
        prefer_same_major_as=(cur_ver if not ctx.same_major_only else None),
        min_version=min_floor,
    )

    for opt in options:
        chosen[next_mod] = opt
        solved = _search_satisfying_plan(ctx, chosen, blocked_holders)
        if solved is not None:
            return solved
        del chosen[next_mod]

    promoted_plan = _try_promote_blocking_holders(
        ctx,
        next_mod,
        active_constraints,
        chosen,
        blocked_holders,
    )
    if promoted_plan is not None:
        return promoted_plan

    if not options:
        req_desc = ", ".join(str(c) for c in mod_constraints) or "*"
        ctx.failure_notes.append(f"no candidate for '{next_mod}' satisfies [{req_desc}]")
    return None


def _topological_order_plan(
    solved: Mapping[ModuleId, _InsCandidateOption],
) -> Mapping[ModuleId, tuple[SemVer4, Optional[IndexReleaseRecord]]]:
    ordered: list[ModuleId] = []
    visited: set[ModuleId] = set()
    temp_mark: set[ModuleId] = set()

    def _visit(mod_id: ModuleId) -> None:
        if mod_id in visited or mod_id not in solved:
            return
        if mod_id in temp_mark:
            return
        temp_mark.add(mod_id)
        deps = solved[mod_id].dependencies
        for dep_id in sorted(deps.keys(), key=_module_priority_key):
            if dep_id in solved and dep_id != mod_id:
                _visit(dep_id)
        temp_mark.remove(mod_id)
        visited.add(mod_id)
        ordered.append(mod_id)

    for root_id in sorted(solved.keys(), key=_module_priority_key):
        _visit(root_id)

    core_first = sorted(
        ordered,
        key=lambda m: (0 if m == _CORE_MODULE_ID else 1, ordered.index(m)),
    )
    out: dict[ModuleId, tuple[SemVer4, Optional[IndexReleaseRecord]]] = {
        m: (solved[m].version, solved[m].release_record) for m in core_first
    }
    return MappingProxyType(out)


def ins_reconcile_installed_with_overrides(
    installed: Mapping[ModuleId, SemVer4],
    provider: ProviderClient,
    mirror: MirrorStore,
    provider_overrides: Mapping[ModuleId, str],
    *,
    same_major_only: bool = False,
) -> Mapping[ModuleId, SemVer4]:
    """Internal reconciliation helper preserving per-module provider_overrides and major lock."""
    if not isinstance(installed, Mapping):
        raise ValueError(f"installed must be Mapping[ModuleId, SemVer4], got {installed!r}")
    clean_installed: dict[ModuleId, SemVer4] = {}
    for m_id, ver in installed.items():
        if not isinstance(m_id, ModuleId) or not isinstance(ver, SemVer4):
            raise ValueError("installed must map ModuleId to SemVer4.")
        clean_installed[m_id] = ver
    if not isinstance(provider, ProviderClient):
        raise ValueError(f"provider must be ProviderClient, got {provider!r}")
    if not isinstance(mirror, MirrorStore):
        raise ValueError(f"mirror must be MirrorStore, got {mirror!r}")
    require_pure_bool(same_major_only, "same_major_only")

    if not clean_installed:
        return MappingProxyType({})

    yscb_root = _derive_yscb_root_from_mirror(mirror)
    ctx = _InsSolverContext(
        yscb_root=yscb_root,
        installed=clean_installed,
        provider=provider,
        mirror=mirror,
        provider_overrides=provider_overrides,
        same_major_only=same_major_only,
    )

    baseline_deps: dict[ModuleId, Mapping[ModuleId, VersionConstraint]] = {}
    needs_healing = False
    for mod_id, ver in clean_installed.items():
        deps = ctx.read_effective_dependencies(mod_id, ver)
        baseline_deps[mod_id] = deps
        for dep_id, dep_c in deps.items():
            cur_dep_ver = clean_installed.get(dep_id)
            if cur_dep_ver is None or (not cur_dep_ver.is_build and not dep_c.satisfies(cur_dep_ver)):
                needs_healing = True

    if not needs_healing:
        return MappingProxyType({})

    ctx.baseline_deps = baseline_deps
    solved = _search_satisfying_plan(ctx, {}, frozenset())
    if solved is None:
        detail = "; ".join(ctx.failure_notes[-3:]) if ctx.failure_notes else "no compatible version intersection"
        raise YscbError(
            ErrorCode.DEPENDENCY_CONFLICT,
            f"Cannot reconcile installed module dependencies: {detail}.",
        )

    ordered = _topological_order_plan(solved)
    healed: dict[ModuleId, SemVer4] = {}
    for mod_id, (new_ver, _rec) in ordered.items():
        if clean_installed.get(mod_id) != new_ver:
            healed[mod_id] = new_ver
    return MappingProxyType(healed)


class DependencySolver:
    """Dependency constraint intersection solver and three-state self-healing engine."""

    def resolve_install_plan(
        self,
        requests: Sequence[PackageRequest],
        installed: Mapping[ModuleId, SemVer4],
        provider: ProviderClient,
        mirror: MirrorStore,
        *,
        same_major_only: bool = False,
    ) -> Mapping[ModuleId, tuple[SemVer4, Optional[IndexReleaseRecord]]]:
        req_tuple = require_typed_tuple(requests, PackageRequest, "requests")
        if not isinstance(installed, Mapping):
            raise ValueError(f"installed must be Mapping[ModuleId, SemVer4], got {installed!r}")
        clean_installed: dict[ModuleId, SemVer4] = {}
        for m_id, ver in installed.items():
            if not isinstance(m_id, ModuleId) or not isinstance(ver, SemVer4):
                raise ValueError("installed must map ModuleId to SemVer4.")
            ins_assert_not_reserved_module_id(m_id, label="installed module_id")
            clean_installed[m_id] = ver
        if not isinstance(provider, ProviderClient):
            raise ValueError(f"provider must be ProviderClient, got {provider!r}")
        if not isinstance(mirror, MirrorStore):
            raise ValueError(f"mirror must be MirrorStore, got {mirror!r}")
        require_pure_bool(same_major_only, "same_major_only")

        if not req_tuple:
            return MappingProxyType({})

        prov_overrides: dict[ModuleId, str] = {}
        for req in req_tuple:
            ins_assert_not_reserved_module_id(req.module_id, label="PackageRequest.module_id")
            if req.provider_override is not None and req.provider_override.strip():
                ov = req.provider_override.strip()
                prev_ov = prov_overrides.get(req.module_id)
                if prev_ov is not None and prev_ov != ov:
                    raise YscbError(
                        ErrorCode.DEPENDENCY_CONFLICT,
                        f"Conflicting provider_override values for '{req.module_id}': '{prev_ov}' vs '{ov}'.",
                    )
                prov_overrides[req.module_id] = ov

        yscb_root = _derive_yscb_root_from_mirror(mirror)
        ctx = _InsSolverContext(
            yscb_root=yscb_root,
            installed=clean_installed,
            provider=provider,
            mirror=mirror,
            provider_overrides=prov_overrides,
            same_major_only=same_major_only,
        )

        initial_chosen: dict[ModuleId, _InsCandidateOption] = {}
        root_constraints: dict[ModuleId, list[VersionConstraint]] = {}
        pinned: set[ModuleId] = set()
        explicit_targets: set[ModuleId] = set()

        for req in req_tuple:
            explicit_targets.add(req.module_id)
            if ins_is_build_request(req):
                build_opt = ctx.resolve_build_option(req.module_id, req.version_spec)
                prev_build = initial_chosen.get(req.module_id)
                if prev_build is not None and prev_build.version != build_opt.version:
                    raise YscbError(
                        ErrorCode.DEPENDENCY_CONFLICT,
                        f"Conflicting @build versions for '{req.module_id}'.",
                    )
                initial_chosen[req.module_id] = build_opt
            else:
                parsed_c = _parse_request_constraint(req.version_spec, module_id=req.module_id)
                root_constraints.setdefault(req.module_id, []).append(parsed_c)
                if _is_explicit_exact_pin(req.version_spec):
                    pinned.add(req.module_id)

        baseline_deps: dict[ModuleId, Mapping[ModuleId, VersionConstraint]] = {}
        for inst_mod, inst_ver in clean_installed.items():
            if inst_mod in explicit_targets:
                continue
            eff_deps = ctx.read_local_dependencies_fast(inst_mod, inst_ver)
            if eff_deps is None and not inst_ver.is_build:
                try:
                    eff_deps = ctx.read_effective_dependencies(inst_mod, inst_ver)
                except YscbError as exc:
                    if exc.detail.code in INS_NON_FALLBACK_ERROR_CODES:
                        raise
                    eff_deps = None
            if eff_deps is not None:
                baseline_deps[inst_mod] = eff_deps

        ctx.explicit_targets = frozenset(explicit_targets)
        ctx.root_constraints = root_constraints
        ctx.pinned_modules = frozenset(pinned)
        ctx.baseline_deps = baseline_deps

        solved = _search_satisfying_plan(ctx, initial_chosen, frozenset())
        if solved is None:
            detail = "; ".join(ctx.failure_notes[-3:]) if ctx.failure_notes else "disjoint version constraints"
            raise YscbError(
                ErrorCode.DEPENDENCY_CONFLICT,
                f"Failed to resolve compatible dependency intersection: {detail}.",
            )
        return _topological_order_plan(solved)

    def reconcile_installed_dependencies(
        self,
        installed: Mapping[ModuleId, SemVer4],
        provider: ProviderClient,
        mirror: MirrorStore,
    ) -> Mapping[ModuleId, SemVer4]:
        return ins_reconcile_installed_with_overrides(
            installed,
            provider,
            mirror,
            {},
            same_major_only=False,
        )
