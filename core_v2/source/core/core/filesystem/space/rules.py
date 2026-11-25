"""Value objects and symmetric three-coordinate rule compilation for core.filesystem.space."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Callable, Final, Mapping, Optional, Pattern, Sequence

from core.foundation.primitives import (
    HostPath,
    ModuleId,
    SemanticUri,
    SnapshotGen,
    SpaceId,
    SpacePath,
    require_non_none,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
)

SpcUriResolver = Callable[[SemanticUri, str], Optional[HostPath]]

_WILDCARD_CHARS: Final[frozenset[str]] = frozenset({"*", "?", "["})
_UNIVERSAL_GLOBS: Final[frozenset[str]] = frozenset({"*", "**", "**/*"})


class HashPolicy(Enum):
    """Content fingerprinting policy for logical file space scanning."""

    STAT_ONLY = "stat_only"
    ADAPTIVE = "adaptive"
    FULL_HASH = "full_hash"


@dataclass(frozen=True, slots=True)
class SpaceSpec:
    """Immutable declaration of a logical file space or pure rule preset."""

    space_id: SpaceId
    entries: tuple[SemanticUri, ...] = ()
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    presets: tuple[str, ...] = ()
    compose: tuple[str, ...] = ()
    watch: bool = True
    hash_policy: HashPolicy = HashPolicy.ADAPTIVE
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.space_id, SpaceId):
            raise ValueError(f"SpaceSpec.space_id must be SpaceId, got {self.space_id!r}")
        if not isinstance(self.hash_policy, HashPolicy):
            raise ValueError(f"SpaceSpec.hash_policy must be HashPolicy, got {self.hash_policy!r}")
        require_pure_bool(self.watch, "SpaceSpec.watch")
        require_pure_str(self.description, "SpaceSpec.description")

        norm_entries: list[SemanticUri] = []
        for item in self.entries:
            if not isinstance(item, SemanticUri):
                raise ValueError(f"SpaceSpec.entries requires SemanticUri items, got {item!r}")
            norm_entries.append(item)
        object.__setattr__(self, "entries", tuple(norm_entries))

        for attr_name, raw_seq in (
            ("include", self.include),
            ("exclude", self.exclude),
            ("presets", self.presets),
            ("compose", self.compose),
        ):
            cleaned_items: list[str] = []
            for raw_item in raw_seq:
                require_pure_str(raw_item, f"SpaceSpec.{attr_name} item")
                stripped = raw_item.strip()
                if stripped:
                    cleaned_items.append(stripped)
            object.__setattr__(self, attr_name, tuple(cleaned_items))


@dataclass(frozen=True, slots=True)
class SpaceFileEntry:
    """Single canonical file entry resolved within a logical file space."""

    rel_path: SpacePath
    abs_path: HostPath
    size_bytes: int
    mtime_ns: int
    content_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.rel_path, SpacePath):
            raise ValueError(f"SpaceFileEntry.rel_path must be SpacePath, got {self.rel_path!r}")
        if not isinstance(self.abs_path, HostPath):
            raise ValueError(f"SpaceFileEntry.abs_path must be HostPath, got {self.abs_path!r}")
        require_pure_int(self.size_bytes, "SpaceFileEntry.size_bytes", min_val=0)
        require_pure_int(self.mtime_ns, "SpaceFileEntry.mtime_ns", min_val=0)
        require_pure_str(self.content_hash, "SpaceFileEntry.content_hash")


@dataclass(frozen=True, slots=True)
class SpaceMatchExplain:
    """Single-point diagnostic explanation for SpaceRegistry.match_path."""

    space_id: SpaceId
    matched: bool
    matched_entry: Optional[SemanticUri] = None
    matched_include: Optional[str] = None
    matched_exclude: Optional[str] = None
    source_space: Optional[SpaceId] = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.space_id, SpaceId):
            raise ValueError(f"SpaceMatchExplain.space_id must be SpaceId, got {self.space_id!r}")
        require_pure_bool(self.matched, "SpaceMatchExplain.matched")
        if self.matched_entry is not None and not isinstance(self.matched_entry, SemanticUri):
            raise ValueError(f"SpaceMatchExplain.matched_entry must be SemanticUri or None, got {self.matched_entry!r}")
        if self.matched_include is not None:
            require_pure_str(self.matched_include, "SpaceMatchExplain.matched_include")
        if self.matched_exclude is not None:
            require_pure_str(self.matched_exclude, "SpaceMatchExplain.matched_exclude")
        if self.source_space is not None and not isinstance(self.source_space, SpaceId):
            raise ValueError(f"SpaceMatchExplain.source_space must be SpaceId or None, got {self.source_space!r}")
        require_pure_str(self.reason, "SpaceMatchExplain.reason")


@dataclass(frozen=True, slots=True)
class SpaceDiffBatch:
    """Orthogonal incremental delta batch between two space generations."""

    space_id: SpaceId
    from_gen: SnapshotGen
    to_gen: SnapshotGen
    config_hash: str
    merkle_root: str
    added: tuple[SpacePath, ...] = ()
    modified: tuple[SpacePath, ...] = ()
    deleted: tuple[SpacePath, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.space_id, SpaceId):
            raise ValueError(f"SpaceDiffBatch.space_id must be SpaceId, got {self.space_id!r}")
        if not isinstance(self.from_gen, SnapshotGen) or not isinstance(self.to_gen, SnapshotGen):
            raise ValueError("SpaceDiffBatch.from_gen and to_gen must be SnapshotGen.")
        require_pure_str(self.config_hash, "SpaceDiffBatch.config_hash")
        require_pure_str(self.merkle_root, "SpaceDiffBatch.merkle_root")

        for field_label, seq_val in (
            ("added", self.added),
            ("modified", self.modified),
            ("deleted", self.deleted),
        ):
            out_paths: list[SpacePath] = []
            for sp in seq_val:
                if not isinstance(sp, SpacePath):
                    raise ValueError(f"SpaceDiffBatch.{field_label} requires SpacePath items, got {sp!r}")
                out_paths.append(sp)
            object.__setattr__(self, field_label, tuple(out_paths))

        add_set = set(self.added)
        mod_set = set(self.modified)
        del_set = set(self.deleted)
        if (add_set & mod_set) or (add_set & del_set) or (mod_set & del_set):
            raise ValueError("SpaceDiffBatch added, modified, and deleted sets must be pairwise disjoint.")

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

    @property
    def dirty_files(self) -> tuple[SpacePath, ...]:
        combined = sorted({*self.added, *self.modified}, key=str)
        return tuple(combined)


@dataclass(frozen=True, slots=True)
class ConsumerCursor:
    """Per-consumer acknowledged snapshot watermark stored in state.db."""

    consumer_id: str
    space_id: SpaceId
    acked_gen: SnapshotGen
    config_hash: str
    merkle_root: str

    def __post_init__(self) -> None:
        require_pure_str(self.consumer_id, "ConsumerCursor.consumer_id")
        if not self.consumer_id.strip():
            raise ValueError("ConsumerCursor.consumer_id must not be empty.")
        if not isinstance(self.space_id, SpaceId):
            raise ValueError(f"ConsumerCursor.space_id must be SpaceId, got {self.space_id!r}")
        if not isinstance(self.acked_gen, SnapshotGen):
            raise ValueError(f"ConsumerCursor.acked_gen must be SnapshotGen, got {self.acked_gen!r}")
        require_pure_str(self.config_hash, "ConsumerCursor.config_hash")
        require_pure_str(self.merkle_root, "ConsumerCursor.merkle_root")


@dataclass(frozen=True, slots=True)
class SpaceStatusSnapshot:
    """Read-only status summary of a logical space snapshot and its consumer cursors."""

    space_id: SpaceId
    generation: SnapshotGen
    config_hash: str
    merkle_root: str
    file_count: int
    cursors: tuple[ConsumerCursor, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.space_id, SpaceId):
            raise ValueError(f"SpaceStatusSnapshot.space_id must be SpaceId, got {self.space_id!r}")
        if not isinstance(self.generation, SnapshotGen):
            raise ValueError(f"SpaceStatusSnapshot.generation must be SnapshotGen, got {self.generation!r}")
        require_pure_str(self.config_hash, "SpaceStatusSnapshot.config_hash")
        require_pure_str(self.merkle_root, "SpaceStatusSnapshot.merkle_root")
        require_pure_int(self.file_count, "SpaceStatusSnapshot.file_count", min_val=0)
        norm_cursors: list[ConsumerCursor] = []
        for cur in self.cursors:
            if not isinstance(cur, ConsumerCursor):
                raise ValueError(f"SpaceStatusSnapshot.cursors requires ConsumerCursor, got {cur!r}")
            norm_cursors.append(cur)
        object.__setattr__(self, "cursors", tuple(norm_cursors))


@dataclass(frozen=True, slots=True)
class GitignoreSyncResult:
    """Outcome of GitignoreMaterializer.sync."""

    changed: bool
    target_uri: SemanticUri
    groups: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        require_pure_bool(self.changed, "GitignoreSyncResult.changed")
        if not isinstance(self.target_uri, SemanticUri):
            raise ValueError(f"GitignoreSyncResult.target_uri must be SemanticUri, got {self.target_uri!r}")
        require_non_none(self.groups, "GitignoreSyncResult.groups")
        frozen_groups: dict[str, tuple[str, ...]] = {}
        for key, vals in self.groups.items():
            require_pure_str(key, "GitignoreSyncResult.groups key")
            clean_vals = tuple(require_pure_str(v, "GitignoreSyncResult.groups pattern") for v in vals)
            frozen_groups[key] = clean_vals
        object.__setattr__(self, "groups", MappingProxyType(frozen_groups))


@dataclass(frozen=True, slots=True)
class SpcRuleItem:
    """Internal rule item tracking pattern text and originating SpaceId."""

    raw_pattern: str
    source_space: SpaceId


@dataclass(frozen=True, slots=True)
class SpcCandidateCoords:
    """Normalized three-coordinate representation of a candidate file or directory."""

    norm_abs: str
    project_rel: Optional[str]
    entry_rel: str
    parts: tuple[str, ...]
    is_dir: bool
    is_project_ancestor: bool = False


@dataclass(frozen=True, slots=True)
class _SpcCompiledRule:
    """Precompiled representation of a single include or exclude rule."""

    item: SpcRuleItem
    coordinate: str
    exact_val: Optional[str] = None
    prefix_val: Optional[str] = None
    ext_suffix: Optional[str] = None
    regex: Optional[Pattern[str]] = None
    dir_only: bool = False
    static_rel_prefix: str = ""


def spc_sort_owner_keys(owners: Sequence[str]) -> tuple[str, ...]:
    """Order module owner identifiers with 'core' first, alphabetical middle, and 'project' last."""
    unique = set(owners)
    unique.discard("")
    ordered: list[str] = []
    if "core" in unique:
        ordered.append("core")
        unique.remove("core")
    has_proj = "project" in unique
    if has_proj:
        unique.remove("project")
    ordered.extend(sorted(unique))
    if has_proj:
        ordered.append("project")
    return tuple(ordered)


def spc_normalize_space_id(raw: SpaceId | str) -> Optional[SpaceId]:
    """Normalize a SpaceId, '/<name>', '<owner>/<name>', or bare '<name>' alias into SpaceId."""
    if isinstance(raw, SpaceId):
        return raw
    if type(raw) is not str:
        raise ValueError(f"space_id must be SpaceId or str, got {raw!r}")
    cleaned = raw.strip()
    if not cleaned:
        return None
    if "/" not in cleaned:
        cleaned = f"/{cleaned}"
    try:
        return SpaceId.parse(cleaned)
    except ValueError:
        return None


def spc_compute_rel_str(target_abs: Path, base_abs: Path) -> Optional[str]:
    """Return POSIX relative path of target_abs inside base_abs, '' if equal, or None if outside."""
    try:
        rel = target_abs.relative_to(base_abs).as_posix()
    except ValueError:
        return None
    if rel == ".":
        return ""
    if rel.startswith(".."):
        return None
    return rel.strip("/")


def spc_build_candidate_coords(
    cand_abs: HostPath,
    entry_abs: HostPath,
    proj_root: Optional[HostPath],
    *,
    is_dir: bool,
) -> SpcCandidateCoords:
    """Construct normalized three-coordinate descriptors for rule evaluation."""
    norm_abs = os.path.normcase(cand_abs.path.as_posix()).replace("\\", "/").rstrip("/")
    proj_rel_raw = spc_compute_rel_str(cand_abs.path, proj_root.path) if proj_root is not None else None
    proj_rel = os.path.normcase(proj_rel_raw).replace("\\", "/") if proj_rel_raw is not None else None

    ent_rel_raw = spc_compute_rel_str(cand_abs.path, entry_abs.path)
    if ent_rel_raw is None:
        ent_rel = ""
    elif ent_rel_raw == "" and not is_dir:
        ent_rel = os.path.normcase(cand_abs.path.name)
    else:
        ent_rel = os.path.normcase(ent_rel_raw).replace("\\", "/")

    norm_fname = os.path.normcase(cand_abs.path.name)
    dir_segs: list[str] = []
    for rel_src in (ent_rel, proj_rel):
        if not rel_src:
            continue
        raw_parts = [s for s in rel_src.split("/") if s]
        anc_parts = raw_parts if is_dir else raw_parts[:-1]
        for seg in anc_parts:
            if seg not in dir_segs:
                dir_segs.append(seg)
    if is_dir:
        seg_list = list(dir_segs)
    else:
        seg_list = [*dir_segs, norm_fname] if norm_fname else list(dir_segs)
    is_proj_anc = bool(
        is_dir
        and proj_root is not None
        and proj_rel_raw is None
        and spc_compute_rel_str(proj_root.path, cand_abs.path)
    )
    return SpcCandidateCoords(
        norm_abs=norm_abs,
        project_rel=proj_rel,
        entry_rel=ent_rel,
        parts=tuple(seg_list),
        is_dir=is_dir,
        is_project_ancestor=is_proj_anc,
    )


def _translate_single_segment_glob(seg_pat: str) -> str:
    """Translate a single path segment glob into a regex fragment that never matches '/'."""
    idx = 0
    length = len(seg_pat)
    parts: list[str] = []
    while idx < length:
        ch = seg_pat[idx]
        idx += 1
        if ch == "*":
            while idx < length and seg_pat[idx] == "*":
                idx += 1
            parts.append(r"[^/]*")
        elif ch == "?":
            parts.append(r"[^/]")
        elif ch == "[":
            cur = idx
            if cur < length and seg_pat[cur] in ("!", "^"):
                cur += 1
            if cur < length and seg_pat[cur] == "]":
                cur += 1
            while cur < length and seg_pat[cur] != "]":
                cur += 1
            if cur >= length:
                parts.append(r"\[")
            else:
                stuff = seg_pat[idx:cur]
                idx = cur + 1
                negated = False
                if stuff and stuff[0] in ("!", "^"):
                    negated = True
                    stuff = stuff[1:]
                escaped = stuff.replace("\\", r"\\")
                escaped = re.sub(r"([&~|])", r"\\\1", escaped)
                escaped = re.sub(r"([^-])-", lambda m: f"{m.group(1)}-", escaped)
                if escaped.startswith("-"):
                    escaped = r"\-" + escaped[1:]
                cls_expr = f"[^{escaped}]" if negated else f"[{escaped}]"
                parts.append(f"(?:(?=[^/]){cls_expr})")
        else:
            parts.append(re.escape(ch))
    return "".join(parts)


def _compile_glob_regex(
    norm_pat: str,
    *,
    allow_dir_prefix: bool,
    preserve_leading_slash: bool = False,
) -> Pattern[str]:
    leading_slashes = ""
    if preserve_leading_slash:
        slash_cnt = len(norm_pat) - len(norm_pat.lstrip("/"))
        leading_slashes = "/" * slash_cnt
    raw_segs = [seg for seg in norm_pat.split("/") if seg]
    collapsed: list[str] = []
    for seg in raw_segs:
        if seg == "**" and collapsed and collapsed[-1] == "**":
            continue
        collapsed.append(seg)
    if not collapsed or collapsed == ["**"]:
        return re.compile(f"(?s:^{leading_slashes}.*\\Z)")

    has_leading_ds = False
    has_trailing_ds = False
    if collapsed[0] == "**":
        has_leading_ds = True
        collapsed = collapsed[1:]
    if collapsed and collapsed[-1] == "**":
        has_trailing_ds = True
        collapsed = collapsed[:-1]
    if not collapsed:
        return re.compile(f"(?s:^{leading_slashes}.*\\Z)")

    runs: list[str] = []
    cur_run: list[str] = []
    for seg in collapsed:
        if seg == "**":
            runs.append("/".join(cur_run))
            cur_run = []
        else:
            cur_run.append(_translate_single_segment_glob(seg))
    runs.append("/".join(cur_run))

    body = r"(?:/|/.+/)".join(runs)
    prefix = r"(?:.+/)?" if has_leading_ds else ""
    suffix = r"(?:/.*)?" if (has_trailing_ds or allow_dir_prefix) else ""
    return re.compile(f"(?s:^{leading_slashes}{prefix}{body}{suffix}\\Z)")


def _extract_static_rel_prefix(norm_pat: str) -> str:
    segs = [s for s in norm_pat.split("/") if s]
    static_segs: list[str] = []
    for seg in segs:
        if any(ch in _WILDCARD_CHARS for ch in seg):
            break
        static_segs.append(seg)
    if not static_segs:
        return ""
    if len(static_segs) == len(segs):
        return "/".join(static_segs[:-1]) + "/" if len(static_segs) > 1 else ""
    return "/".join(static_segs) + "/"


def _compile_uri_coordinate_rule(
    item: SpcRuleItem,
    norm_raw: str,
    dir_only: bool,
    owner: str,
    uri_resolver: SpcUriResolver,
) -> Optional[_SpcCompiledRule]:
    scheme_part, rest_part = norm_raw.split("://", 1)
    scheme_clean = scheme_part.strip()
    rest_stripped = rest_part.strip("/")
    if not scheme_clean:
        return None
    eff_dir_only = dir_only or (rest_stripped == "**") or rest_stripped.endswith("/**")

    wildcard_idx = -1
    for idx, ch in enumerate(rest_stripped):
        if ch in _WILDCARD_CHARS:
            wildcard_idx = idx
            break

    if wildcard_idx == -1:
        raw_uri = f"{scheme_clean}://{rest_stripped}" if rest_stripped else f"{scheme_clean}://"
        try:
            parsed_uri = SemanticUri.parse(raw_uri)
        except ValueError:
            return None
        eff_owner = item.source_space.owner or owner
        resolved_hp = uri_resolver(parsed_uri, eff_owner)
        if resolved_hp is None:
            return None
        norm_base = os.path.normcase(resolved_hp.path.as_posix()).replace("\\", "/").rstrip("/")
        return _SpcCompiledRule(
            item=item,
            coordinate="uri",
            exact_val=norm_base,
            prefix_val=f"{norm_base}/",
            dir_only=eff_dir_only,
        )

    static_prefix = rest_stripped[:wildcard_idx]
    if "/" in static_prefix:
        static_dir, _ = static_prefix.rsplit("/", 1)
        glob_tail = rest_stripped[len(static_dir) + 1 :]
        raw_base = f"{scheme_clean}://{static_dir}"
    else:
        glob_tail = rest_stripped
        raw_base = f"{scheme_clean}://"

    try:
        base_uri = SemanticUri.parse(raw_base)
    except ValueError:
        return None
    eff_owner = item.source_space.owner or owner
    resolved_base = uri_resolver(base_uri, eff_owner)
    if resolved_base is None:
        return None
    base_posix = os.path.normcase(resolved_base.path.as_posix()).replace("\\", "/").rstrip("/")
    if glob_tail == "**":
        return _SpcCompiledRule(
            item=item,
            coordinate="uri",
            exact_val=base_posix,
            prefix_val=f"{base_posix}/",
            dir_only=True,
        )
    full_glob = os.path.normcase(f"{base_posix}/{glob_tail}" if glob_tail else base_posix).replace("\\", "/")
    return _SpcCompiledRule(
        item=item,
        coordinate="uri",
        prefix_val=f"{base_posix}/",
        regex=_compile_glob_regex(full_glob, allow_dir_prefix=True, preserve_leading_slash=True),
        dir_only=eff_dir_only,
    )


def _compile_single_spc_rule(
    item: SpcRuleItem,
    owner: str,
    uri_resolver: SpcUriResolver,
) -> Optional[_SpcCompiledRule]:
    raw = item.raw_pattern.strip()
    if not raw or raw.startswith("#"):
        return None
    norm_raw = raw.replace("\\", "/")
    dir_only = norm_raw.endswith("/") and norm_raw != "/"

    if "://" in norm_raw:
        return _compile_uri_coordinate_rule(item, norm_raw, dir_only, owner, uri_resolver)

    clean_pat = norm_raw.strip("/")
    if not clean_pat:
        return None
    if clean_pat in _UNIVERSAL_GLOBS:
        return _SpcCompiledRule(item=item, coordinate="all", dir_only=dir_only)

    if clean_pat.endswith("/**"):
        dir_only = True

    has_wildcard = any(ch in _WILDCARD_CHARS for ch in clean_pat)
    norm_pat = os.path.normcase(clean_pat).replace("\\", "/")

    if "/" in norm_pat:
        if norm_pat.endswith("/**") and not any(ch in _WILDCARD_CHARS for ch in norm_pat[:-3]):
            base_seg = norm_pat[:-3].strip("/")
            if "/" not in base_seg:
                return _SpcCompiledRule(
                    item=item,
                    coordinate="name",
                    exact_val=base_seg,
                    dir_only=True,
                )
            return _SpcCompiledRule(
                item=item,
                coordinate="rel",
                exact_val=base_seg,
                prefix_val=f"{base_seg}/",
                dir_only=True,
                static_rel_prefix=f"{base_seg}/",
            )
        if not has_wildcard:
            return _SpcCompiledRule(
                item=item,
                coordinate="rel",
                exact_val=norm_pat,
                prefix_val=f"{norm_pat}/",
                dir_only=dir_only,
                static_rel_prefix=_extract_static_rel_prefix(norm_pat),
            )
        return _SpcCompiledRule(
            item=item,
            coordinate="rel",
            regex=_compile_glob_regex(norm_pat, allow_dir_prefix=True),
            dir_only=dir_only,
            static_rel_prefix=_extract_static_rel_prefix(norm_pat),
        )

    if not has_wildcard:
        return _SpcCompiledRule(item=item, coordinate="name", exact_val=norm_pat, dir_only=dir_only)
    if norm_pat.startswith("*.") and not any(ch in _WILDCARD_CHARS for ch in norm_pat[1:]):
        return _SpcCompiledRule(item=item, coordinate="name", ext_suffix=norm_pat[1:], dir_only=dir_only)
    return _SpcCompiledRule(
        item=item,
        coordinate="name",
        regex=_compile_glob_regex(norm_pat, allow_dir_prefix=False),
        dir_only=dir_only,
    )


def _rule_matches_coords(comp: _SpcCompiledRule, coords: SpcCandidateCoords) -> bool:
    """Symmetric rule evaluation: allow_dir_prefix=True and match_any_segment_for_name=True."""
    if comp.dir_only and not coords.is_dir:
        dir_segs = coords.parts[:-1]
        if comp.coordinate == "all":
            return bool(dir_segs)
        if comp.coordinate == "name":
            if comp.exact_val is not None:
                return comp.exact_val in dir_segs
            if comp.ext_suffix is not None:
                return any(seg.endswith(comp.ext_suffix) for seg in dir_segs)
            if comp.regex is not None:
                return any(comp.regex.match(seg) is not None for seg in dir_segs)
            return False
        if comp.coordinate == "rel":
            rels = [r for r in (coords.project_rel, coords.entry_rel) if r]
            for rel_v in rels:
                if comp.prefix_val is not None and rel_v.startswith(comp.prefix_val):
                    return True
                if comp.regex is not None and "/" in rel_v:
                    parent_rel = rel_v.rsplit("/", 1)[0]
                    if comp.regex.match(parent_rel) is not None:
                        return True
            return False
        if comp.coordinate == "uri":
            if comp.prefix_val is not None and coords.norm_abs.startswith(comp.prefix_val):
                if comp.regex is None:
                    return True
                if "/" in coords.norm_abs:
                    parent_abs = coords.norm_abs.rsplit("/", 1)[0]
                    base_dir = comp.prefix_val[:-1]
                    if (parent_abs == base_dir or parent_abs.startswith(comp.prefix_val)) and (
                        comp.regex.match(parent_abs) is not None
                    ):
                        return True
            return False
        return False

    if comp.coordinate == "all":
        return bool(coords.parts) if comp.dir_only else True

    if comp.coordinate == "uri":
        if comp.exact_val is not None:
            if coords.norm_abs == comp.exact_val:
                return True
            return bool(comp.prefix_val is not None and coords.norm_abs.startswith(comp.prefix_val))
        if (
            comp.prefix_val is not None
            and coords.norm_abs != comp.prefix_val[:-1]
            and not coords.norm_abs.startswith(comp.prefix_val)
        ):
            return False
        return bool(comp.regex is not None and comp.regex.match(coords.norm_abs) is not None)

    if comp.coordinate == "rel":
        rels = [r for r in (coords.project_rel, coords.entry_rel) if r]
        for rel_v in rels:
            if comp.exact_val is not None:
                if rel_v == comp.exact_val:
                    return True
                if comp.prefix_val is not None and rel_v.startswith(comp.prefix_val):
                    return True
            elif comp.regex is not None and comp.regex.match(rel_v) is not None:
                return True
        return False

    if comp.coordinate == "name":
        if comp.exact_val is not None:
            return comp.exact_val in coords.parts
        if comp.ext_suffix is not None:
            return any(seg.endswith(comp.ext_suffix) for seg in coords.parts)
        if comp.regex is not None:
            return any(comp.regex.match(seg) is not None for seg in coords.parts)
    return False


class SpcCompiledRuleSet:
    """Symmetric precompiled rule matcher with fast-path lookup and subtree exemption detection."""

    def __init__(
        self,
        rules: Sequence[SpcRuleItem],
        *,
        owner: str,
        uri_resolver: SpcUriResolver,
    ) -> None:
        self._rules: tuple[SpcRuleItem, ...] = tuple(rules)
        compiled_items: list[_SpcCompiledRule] = []
        fallback_items: list[_SpcCompiledRule] = []
        exact_names: set[str] = set()
        ext_suffixes: list[str] = []
        rel_exact: set[str] = set()
        rel_prefixes: list[str] = []
        uri_exact: set[str] = set()
        uri_prefixes: list[str] = []
        has_all = False

        for r_item in self._rules:
            eff_owner = r_item.source_space.owner or owner
            comp = _compile_single_spc_rule(r_item, eff_owner, uri_resolver)
            if comp is None:
                continue
            compiled_items.append(comp)
            covered = False
            if comp.coordinate == "all" and not comp.dir_only:
                has_all = True
                covered = True
            elif comp.coordinate == "name" and not comp.dir_only:
                if comp.exact_val is not None:
                    exact_names.add(comp.exact_val)
                    covered = True
                elif comp.ext_suffix is not None:
                    ext_suffixes.append(comp.ext_suffix)
                    covered = True
            elif comp.coordinate == "rel":
                if comp.exact_val is not None and not comp.dir_only and comp.regex is None:
                    rel_exact.add(comp.exact_val)
                    covered = True
                if comp.prefix_val is not None and comp.regex is None:
                    rel_prefixes.append(comp.prefix_val)
                    if comp.dir_only:
                        covered = False
            elif comp.coordinate == "uri":
                if comp.exact_val is not None and not comp.dir_only and comp.regex is None:
                    uri_exact.add(comp.exact_val)
                    covered = True
                if comp.prefix_val is not None and comp.regex is None:
                    uri_prefixes.append(comp.prefix_val)
                    if comp.dir_only:
                        covered = False
            if not covered:
                fallback_items.append(comp)

        self._compiled: tuple[_SpcCompiledRule, ...] = tuple(compiled_items)
        self._fallback: tuple[_SpcCompiledRule, ...] = tuple(fallback_items)
        self._has_all = has_all
        self._exact_names: frozenset[str] = frozenset(exact_names)
        self._ext_suffixes: tuple[str, ...] = tuple(ext_suffixes)
        self._rel_exact: frozenset[str] = frozenset(rel_exact)
        self._rel_prefixes: tuple[str, ...] = tuple(rel_prefixes)
        self._uri_exact: frozenset[str] = frozenset(uri_exact)
        self._uri_prefixes: tuple[str, ...] = tuple(uri_prefixes)

    @property
    def items(self) -> tuple[SpcRuleItem, ...]:
        return self._rules

    @property
    def is_empty(self) -> bool:
        return len(self._compiled) == 0

    def find_match(self, coords: SpcCandidateCoords) -> Optional[SpcRuleItem]:
        for comp in self._compiled:
            if _rule_matches_coords(comp, coords):
                return comp.item
        return None

    def matches_fast(self, coords: SpcCandidateCoords) -> bool:
        if self._has_all:
            return True
        if self._exact_names and any(seg in self._exact_names for seg in coords.parts):
            return True
        if self._ext_suffixes and any(seg.endswith(self._ext_suffixes) for seg in coords.parts):
            return True
        if self._rel_exact:
            if (coords.project_rel and coords.project_rel in self._rel_exact) or (
                coords.entry_rel and coords.entry_rel in self._rel_exact
            ):
                return True
        if self._rel_prefixes:
            if (coords.project_rel and coords.project_rel.startswith(self._rel_prefixes)) or (
                coords.entry_rel and coords.entry_rel.startswith(self._rel_prefixes)
            ):
                return True
        if self._uri_exact and coords.norm_abs in self._uri_exact:
            return True
        if self._uri_prefixes and coords.norm_abs.startswith(self._uri_prefixes):
            return True
        for comp in self._fallback:
            if _rule_matches_coords(comp, coords):
                return True
        return False

    def has_potential_descendant_match(self, dir_coords: SpcCandidateCoords) -> bool:
        """Return True if any compiled rule could potentially match a descendant inside dir_coords."""
        if not self._compiled:
            return False
        dir_abs_prefix = f"{dir_coords.norm_abs.rstrip('/')}/"
        has_root_rel = (
            (dir_coords.project_rel == "")
            or (dir_coords.entry_rel == "")
            or dir_coords.is_project_ancestor
        )
        rels = [r.strip("/") for r in (dir_coords.project_rel, dir_coords.entry_rel) if r]
        rel_prefixes = [f"{r}/" for r in rels if r]

        for comp in self._compiled:
            if comp.coordinate in ("all", "name"):
                return True
            if comp.coordinate == "uri":
                if comp.exact_val is not None and comp.exact_val.startswith(dir_abs_prefix):
                    return True
                if comp.prefix_val is not None and (
                    comp.prefix_val.startswith(dir_abs_prefix) or dir_abs_prefix.startswith(comp.prefix_val)
                ):
                    return True
                continue
            if comp.coordinate == "rel":
                if has_root_rel or not rel_prefixes:
                    return True
                if comp.regex is not None:
                    if not comp.static_rel_prefix:
                        return True
                    if any(
                        comp.static_rel_prefix.startswith(rp) or rp.startswith(comp.static_rel_prefix)
                        for rp in rel_prefixes
                    ):
                        return True
                    continue
                for rp in rel_prefixes:
                    if comp.exact_val is not None and comp.exact_val.startswith(rp):
                        return True
                    if comp.prefix_val is not None and (
                        comp.prefix_val.startswith(rp) or rp.startswith(comp.prefix_val)
                    ):
                        return True
                for r_val in rels:
                    if comp.exact_val is not None and f"/{r_val}/".endswith(f"/{comp.exact_val.split('/', 1)[0]}/"):
                        return True
                    if comp.prefix_val is not None and f"/{r_val}/".endswith(f"/{comp.prefix_val.split('/', 1)[0]}/"):
                        return True
        return False


_SPC_KERNEL_ONLY_SCHEMES: frozenset[str] = frozenset(
    {"yscb", "module", "module.mirror", "snapshot", "yscb.venv"}
)
_SPC_PRIVATE_MODULE_SCHEMES: frozenset[str] = frozenset(
    {"config.local", "cache", "storage.local"}
)
_SPC_HOST_ROOT_CONTROL_FILENAMES: frozenset[str] = frozenset(
    {"yscb.config.json", "yscb.config.local.json", "yscb.py", ".gitignore"}
)


@dataclass(frozen=True, slots=True)
class SpcControlPlaneRoots:
    """Physical control-plane roots excluded from non-core space enumeration and locking."""

    yscb_root: Optional[HostPath] = None
    host_dir: Optional[HostPath] = None
    proj_root: Optional[HostPath] = None


def spc_check_space_uri_owner_boundary(
    uri: SemanticUri,
    owner: str,
    *,
    is_readonly_space: bool = False,
) -> Optional[str]:
    """Verify that a space owner is permitted to reference a SemanticUri in entries or rules."""
    if owner == "core":
        return None
    scheme = uri.scheme
    if scheme in _SPC_KERNEL_ONLY_SCHEMES:
        return f"Non-core space owner '{owner or 'project'}' cannot reference kernel-reserved scheme '{scheme}://'."
    if is_readonly_space and scheme in ("config", "yscb.host"):
        return f"Non-core readonly space '{owner}/readonly' cannot lock '{scheme}://'."
    bound = uri
    if uri.uses_module_placeholder:
        if not owner or owner == "project":
            return f"Space owner '{owner or 'project'}' cannot use '@/' module placeholder in '{uri}'."
        try:
            bound = uri.bind_module(ModuleId(owner))
        except ValueError as exc:
            return str(exc)
    first_seg = bound.rel_path.split("/", 1)[0] if bound.rel_path else ""
    if is_readonly_space:
        if owner in ("", "project") and scheme in (*_SPC_PRIVATE_MODULE_SCHEMES, "storage"):
            return f"Non-core readonly space '{owner or 'project'}/readonly' cannot lock '{scheme}://'."
        if owner not in ("", "project") and scheme == "storage" and first_seg != owner:
            return f"Module readonly space '{owner}/readonly' cannot lock foreign storage URI '{uri}'."
    if owner and owner != "project":
        if scheme in _SPC_PRIVATE_MODULE_SCHEMES and first_seg != owner:
            return f"Module space owner '{owner}' cannot reference foreign module-isolated URI '{uri}'."
        if scheme == "config" and first_seg != owner:
            return f"Module space owner '{owner}' cannot reference foreign config URI '{uri}'."
    return None


def spc_extract_embedded_rule_uri(raw_pattern: str) -> Optional[SemanticUri]:
    """Extract and parse the base SemanticUri from an include/exclude rule containing '://', if present."""
    cleaned = raw_pattern.strip()
    if not cleaned or cleaned.startswith("#"):
        return None
    if cleaned.startswith("!"):
        cleaned = cleaned[1:].strip()
    if "://" not in cleaned:
        return None
    scheme_part, rest_part = cleaned.split("://", 1)
    scheme_clean = scheme_part.strip()
    rest_clean = rest_part.strip().lstrip("/\\").replace("\\", "/").rstrip("/")
    wildcard_idx = -1
    for idx, ch in enumerate(rest_clean):
        if ch in _WILDCARD_CHARS:
            wildcard_idx = idx
            break
    if wildcard_idx == -1:
        base_rel = rest_clean
    else:
        static_prefix = rest_clean[:wildcard_idx]
        base_rel = static_prefix.rsplit("/", 1)[0] if "/" in static_prefix else ""
    raw_uri_str = f"{scheme_clean}://{base_rel}" if base_rel else f"{scheme_clean}://"
    return SemanticUri.parse(raw_uri_str)


_SPC_YSCB_PROTECTED_SUBTREES: tuple[str, ...] = (
    ".modules",
    ".build",
    ".mirror",
    ".snapshots",
    ".venv",
    "config/core",
    ".config.local/core",
    "storage/core",
    ".storage.local/core",
    ".cache/core",
    ".cache/locks",
    ".cache/daemon",
)


def spc_is_control_plane_reserved_path(
    cand_hp: HostPath,
    roots: SpcControlPlaneRoots,
    *,
    entry_hp: Optional[HostPath] = None,
) -> bool:
    """Return True when cand_hp lies on a reserved workspace control-plane file or directory."""
    cand_p = cand_hp.path
    if roots.yscb_root is not None:
        rel_yscb = spc_compute_rel_str(cand_p, roots.yscb_root.path)
        if rel_yscb is not None:
            if entry_hp is None or spc_compute_rel_str(entry_hp.path, roots.yscb_root.path) is None:
                return True
            norm_rel = rel_yscb.lower()
            if norm_rel == "" or any(
                norm_rel == pfx or norm_rel.startswith(f"{pfx}/") for pfx in _SPC_YSCB_PROTECTED_SUBTREES
            ):
                return True
    if roots.host_dir is not None and cand_p.parent == roots.host_dir.path:
        if os.path.normcase(cand_p.name) in _SPC_HOST_ROOT_CONTROL_FILENAMES:
            return True
    if roots.proj_root is not None and cand_p.parent == roots.proj_root.path:
        if os.path.normcase(cand_p.name) == ".gitignore":
            return True
    for base_hp in (roots.proj_root, roots.host_dir):
        if base_hp is None:
            continue
        rel = spc_compute_rel_str(cand_p, base_hp.path)
        if rel:
            if any(os.path.normcase(seg) == ".git" for seg in rel.split("/") if seg):
                return True
    return False
