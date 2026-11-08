"""
Data models and precompiled symmetric three-coordinate rule matchers for core.space.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import fnmatch
import os
from pathlib import Path
import re
from typing import Any, Dict, FrozenSet, List, Optional, Pattern, Sequence, Set, Tuple, Union

from core.context import get_virtual_cwd
from .exceptions import SpaceError


def _compile_glob_pattern(norm_pat: str, *, allow_dir_prefix: bool = False) -> Pattern[str]:
    """
    Compile a normalized POSIX glob pattern into a regular expression.
    Supports zero-or-more directory segments for `**/` and `/**/`.
    """
    working = norm_pat
    has_leading_ds = False
    has_trailing_ds = False
    if working == "**":
        return re.compile(r"(?s:^.*\Z)")
    if working.startswith("**/"):
        has_leading_ds = True
        working = working[3:]
    if working.endswith("/**"):
        has_trailing_ds = True
        working = working[:-3]

    chunks = working.split("/**/")
    translated_chunks: List[str] = []
    for chunk in chunks:
        if not chunk:
            translated_chunks.append("")
            continue
        raw_regex = fnmatch.translate(chunk)
        if raw_regex.startswith("(?s:") and raw_regex.endswith(")\\Z"):
            inner = raw_regex[4:-3]
        elif raw_regex.endswith("\\Z"):
            inner = raw_regex[:-2]
        elif raw_regex.endswith("$"):
            inner = raw_regex[:-1]
        else:
            inner = raw_regex
        translated_chunks.append(inner)

    body = r"(?:/|/.+/)".join(translated_chunks)
    prefix = r"(?:.+/)?" if has_leading_ds else ""
    if has_trailing_ds or allow_dir_prefix:
        suffix = r"(?:/.*)?"
    else:
        suffix = ""
    return re.compile(f"(?s:^{prefix}{body}{suffix}\\Z)")


def resolve_semantic_or_rel_path(
    raw_uri_or_path: str,
    project_root: Path,
    yscb_dir: Optional[Path] = None,
    *,
    owner_module: Optional[str] = None,
) -> Optional[Path]:
    """
    Resolve a semantic URI or project-relative path into a normalized physical Path.
    Returns None if the URI scheme is unknown or malformed.
    """
    raw = str(raw_uri_or_path or "").strip()
    if not raw:
        return None

    if "://" in raw:
        scheme, rest = raw.split("://", 1)
        scheme_clean = scheme.strip()
        rest_clean = rest.strip().lstrip("/\\").replace("\\", "/")
        if not scheme_clean:
            return None

        if rest_clean.startswith("@/") or rest_clean == "@":
            if owner_module and owner_module != "project":
                rest_clean = owner_module if rest_clean == "@" else f"{owner_module}{rest_clean[1:]}"

        eff_proj = Path(os.path.abspath(str(project_root)))
        if yscb_dir is not None:
            eff_yscb = Path(os.path.abspath(str(yscb_dir)))
        else:
            cand_yscb = eff_proj / "ys_codebase"
            eff_yscb = cand_yscb if cand_yscb.is_dir() else eff_proj

        if scheme_clean in ("project", "yscb.host"):
            base_p = eff_proj
            return Path(os.path.normpath(str(base_p / rest_clean))) if rest_clean else base_p
        if scheme_clean == "yscb":
            base_p = eff_yscb
            return Path(os.path.normpath(str(base_p / rest_clean))) if rest_clean else base_p

        sub_map = {
            "config": "config",
            "config.local": ".config.local",
            "storage": "storage",
            "storage.local": ".storage.local",
            "cache": ".cache",
            "module": ".modules",
            "module.install": ".modules",
            "module.source": "source",
            "module.build": ".build",
            "module.release": "release",
            "module.mirror": ".mirror",
            "snapshot": ".snapshots",
            "yscb.venv": ".venv",
        }
        if scheme_clean in sub_map:
            base_p = eff_yscb / sub_map[scheme_clean]
            return Path(os.path.normpath(str(base_p / rest_clean))) if rest_clean else base_p

        try:
            from core import uri as core_uri

            resolved_str = core_uri.resolve(raw, current_module=owner_module, interactive=False)
            if resolved_str and not str(resolved_str).startswith("!undefined"):
                return Path(os.path.normpath(os.path.abspath(str(resolved_str))))
        except Exception:
            return None
        return None

    p = Path(raw)
    if p.is_absolute():
        return Path(os.path.normpath(str(p)))
    return Path(os.path.normpath(str(Path(os.path.abspath(str(project_root))) / raw)))


class HashPolicy(str, Enum):
    """Content hashing strategy for file and space fingerprint computation."""

    ADAPTIVE = "adaptive"
    FULL_HASH = "full_hash"
    STAT_ONLY = "stat_only"
    LAZY_STABILIZED = "lazy_stabilized"


@dataclass(frozen=True)
class RuleItem:
    """Single include or exclude filter rule with provenance metadata."""

    raw_pattern: str
    source: str
    is_negated: bool = False


@dataclass(frozen=True)
class _CompiledRuleEntry:
    """Internal precompiled representation of a single RuleItem."""

    rule: RuleItem
    coordinate: str  # "uri" | "rel" | "name" | "all"
    exact_val: Optional[str] = None
    prefix_val: Optional[str] = None
    ext_suffix: Optional[str] = None
    regex: Optional[Pattern[str]] = None
    dir_only: bool = False


def _compile_single_rule(
    rule: RuleItem,
    project_root: Path,
    yscb_dir: Optional[Path] = None,
    *,
    owner_module: Optional[str] = None,
    allow_dir_prefix: bool = True,
    pattern_override: Optional[str] = None,
) -> Optional[_CompiledRuleEntry]:
    raw = str(pattern_override if pattern_override is not None else (rule.raw_pattern or "")).strip()
    if not raw or raw.startswith("#"):
        return None

    norm_raw = raw.replace("\\", "/")
    dir_only = norm_raw.endswith("/") and norm_raw != "/"

    # Coordinate 1: Semantic URI prefix (contains "://")
    if "://" in norm_raw:
        scheme_part, rest_part = norm_raw.split("://", 1)
        rest_stripped = rest_part.strip("/")
        wildcard_idx = -1
        for i, ch in enumerate(rest_stripped):
            if ch in ("*", "?", "["):
                wildcard_idx = i
                break

        if wildcard_idx == -1:
            base_uri = f"{scheme_part}://{rest_stripped}" if rest_stripped else f"{scheme_part}://"
            resolved_base = resolve_semantic_or_rel_path(
                base_uri, project_root, yscb_dir, owner_module=owner_module
            )
            if resolved_base is None:
                return None
            norm_abs = os.path.normcase(resolved_base.as_posix()).replace("\\", "/").rstrip("/")
            return _CompiledRuleEntry(
                rule=rule,
                coordinate="uri",
                exact_val=norm_abs,
                prefix_val=f"{norm_abs}/" if allow_dir_prefix else None,
                dir_only=dir_only,
            )

        static_prefix = rest_stripped[:wildcard_idx]
        if "/" in static_prefix:
            static_dir, _ = static_prefix.rsplit("/", 1)
            glob_tail = rest_stripped[len(static_dir) + 1 :]
            base_uri = f"{scheme_part}://{static_dir}"
        else:
            glob_tail = rest_stripped
            base_uri = f"{scheme_part}://"

        resolved_base = resolve_semantic_or_rel_path(
            base_uri, project_root, yscb_dir, owner_module=owner_module
        )
        if resolved_base is None:
            return None
        base_posix = os.path.normcase(resolved_base.as_posix()).replace("\\", "/").rstrip("/")
        full_glob = os.path.normcase(
            f"{base_posix}/{glob_tail}" if glob_tail else base_posix
        ).replace("\\", "/")
        rx = _compile_glob_pattern(full_glob, allow_dir_prefix=allow_dir_prefix)
        return _CompiledRuleEntry(
            rule=rule,
            coordinate="uri",
            prefix_val=f"{base_posix}/",
            regex=rx,
            dir_only=dir_only,
        )

    clean_pat = norm_raw.strip("/")
    if not clean_pat:
        return None

    if clean_pat in ("*", "**", "**/*"):
        return _CompiledRuleEntry(
            rule=rule,
            coordinate="all",
            dir_only=dir_only,
        )

    has_wildcard = any(ch in clean_pat for ch in ("*", "?", "["))

    # Coordinate 2: Relative path containing "/" (matches project_rel or entry_rel)
    if "/" in clean_pat:
        norm_pat = os.path.normcase(clean_pat).replace("\\", "/")
        if norm_pat.endswith("/**") and not any(
            ch in norm_pat[:-3] for ch in ("*", "?", "[")
        ):
            base_seg = norm_pat[:-3].strip("/")
            if "/" not in base_seg:
                return _CompiledRuleEntry(
                    rule=rule,
                    coordinate="name",
                    exact_val=base_seg,
                    dir_only=True,
                )
            return _CompiledRuleEntry(
                rule=rule,
                coordinate="rel",
                exact_val=base_seg,
                prefix_val=f"{base_seg}/" if allow_dir_prefix else None,
                dir_only=True,
            )
        if not has_wildcard:
            return _CompiledRuleEntry(
                rule=rule,
                coordinate="rel",
                exact_val=norm_pat,
                prefix_val=f"{norm_pat}/" if allow_dir_prefix else None,
                dir_only=dir_only,
            )
        return _CompiledRuleEntry(
            rule=rule,
            coordinate="rel",
            regex=_compile_glob_pattern(norm_pat, allow_dir_prefix=allow_dir_prefix),
            dir_only=dir_only,
        )

    # Coordinate 3: Pure filename or directory segment name (no "/")
    norm_pat = os.path.normcase(clean_pat).replace("\\", "/")
    if not has_wildcard:
        return _CompiledRuleEntry(
            rule=rule,
            coordinate="name",
            exact_val=norm_pat,
            dir_only=dir_only,
        )
    if norm_pat.startswith("*.") and not any(ch in norm_pat[1:] for ch in ("*", "?", "[")):
        return _CompiledRuleEntry(
            rule=rule,
            coordinate="name",
            ext_suffix=norm_pat[1:],
            dir_only=dir_only,
        )
    return _CompiledRuleEntry(
        rule=rule,
        coordinate="name",
        regex=_compile_glob_pattern(norm_pat, allow_dir_prefix=False),
        dir_only=dir_only,
    )


def _entry_matches_candidate(
    entry: _CompiledRuleEntry,
    *,
    norm_abs: str,
    project_rel: Optional[str],
    entry_rel: str,
    parts: Sequence[str],
    filename: str,
    is_dir: bool,
    match_any_segment_for_name: bool,
) -> bool:
    if entry.dir_only and not is_dir:
        # A directory-only rule (ending with "/") also matches files inside that directory
        # when allow_dir_prefix is active (e.g. exclude rule "build/").
        if entry.coordinate == "name" and entry.exact_val:
            dir_segments = parts if is_dir else parts[:-1]
            return entry.exact_val in dir_segments
        if entry.coordinate == "name" and entry.regex:
            dir_segments = parts if is_dir else parts[:-1]
            return any(entry.regex.match(seg) for seg in dir_segments)
        if entry.coordinate == "rel":
            rels = [r for r in (project_rel, entry_rel) if r]
            for r in rels:
                if entry.prefix_val and r.startswith(entry.prefix_val):
                    return True
                if entry.regex and entry.regex.match(r):
                    return True
            return False
        if entry.coordinate == "uri":
            if entry.prefix_val and norm_abs.startswith(entry.prefix_val):
                if entry.regex is None:
                    return True
                return bool(entry.regex.match(norm_abs))
            return False
        return False

    if entry.coordinate == "all":
        return True

    if entry.coordinate == "uri":
        if entry.exact_val is not None:
            if norm_abs == entry.exact_val:
                return True
            if entry.prefix_val and norm_abs.startswith(entry.prefix_val):
                return True
            return False
        if entry.prefix_val and not norm_abs.startswith(entry.prefix_val):
            return False
        if entry.regex is not None:
            return bool(entry.regex.match(norm_abs))
        return False

    if entry.coordinate == "rel":
        rels = [r for r in (project_rel, entry_rel) if r]
        for r in rels:
            if entry.exact_val is not None:
                if r == entry.exact_val:
                    return True
                if entry.prefix_val and r.startswith(entry.prefix_val):
                    return True
            elif entry.regex is not None and entry.regex.match(r):
                return True
        return False

    if entry.coordinate == "name":
        target_pool = parts if match_any_segment_for_name else (filename,)
        if entry.exact_val is not None:
            return entry.exact_val in target_pool
        if entry.ext_suffix is not None:
            return any(seg.endswith(entry.ext_suffix) for seg in target_pool)
        if entry.regex is not None:
            return any(entry.regex.match(seg) for seg in target_pool)
    return False


class CompiledRuleSet:
    """
    Precompiled symmetric filter engine combining fast $O(1)$ set/prefix checks with full
    rule provenance lookup for explainability (`match`).
    """

    def __init__(
        self,
        rules: Sequence[RuleItem],
        project_root: Path,
        yscb_dir: Optional[Path] = None,
        *,
        owner_module: Optional[str] = None,
        is_exclude: bool = False,
    ) -> None:
        self.rules: Tuple[RuleItem, ...] = tuple(rules)
        self.is_exclude = is_exclude

        compiled_list: List[_CompiledRuleEntry] = []
        exact_names: Set[str] = set()
        ext_suffixes: List[str] = []
        rel_exact: Set[str] = set()
        rel_prefixes: List[str] = []
        uri_exact: Set[str] = set()
        uri_prefixes: List[str] = []
        has_match_all = False

        for r in self.rules:
            if r.is_negated:
                continue
            comp = _compile_single_rule(
                r,
                project_root,
                yscb_dir,
                owner_module=owner_module,
                allow_dir_prefix=True,
            )
            if comp is None:
                continue
            compiled_list.append(comp)
            if comp.coordinate == "all" and not comp.dir_only:
                has_match_all = True
            elif comp.coordinate == "name" and not comp.dir_only:
                if comp.exact_val is not None:
                    exact_names.add(comp.exact_val)
                elif comp.ext_suffix is not None:
                    ext_suffixes.append(comp.ext_suffix)
            elif comp.coordinate == "rel":
                if comp.exact_val is not None and not comp.dir_only:
                    rel_exact.add(comp.exact_val)
                if comp.prefix_val is not None and comp.regex is None:
                    rel_prefixes.append(comp.prefix_val)
            elif comp.coordinate == "uri":
                if comp.exact_val is not None and not comp.dir_only:
                    uri_exact.add(comp.exact_val)
                if comp.prefix_val is not None and comp.regex is None:
                    uri_prefixes.append(comp.prefix_val)

        self._compiled: Tuple[_CompiledRuleEntry, ...] = tuple(compiled_list)
        self._has_match_all = has_match_all
        self._exact_names: FrozenSet[str] = frozenset(exact_names)
        self._ext_suffixes: Tuple[str, ...] = tuple(ext_suffixes)
        self._rel_exact: FrozenSet[str] = frozenset(rel_exact)
        self._rel_prefixes: Tuple[str, ...] = tuple(rel_prefixes)
        self._uri_exact: FrozenSet[str] = frozenset(uri_exact)
        self._uri_prefixes: Tuple[str, ...] = tuple(uri_prefixes)

    def find_matching_rule(
        self,
        *,
        norm_abs: str,
        project_rel: Optional[str],
        entry_rel: str,
        parts: Sequence[str],
        filename: str,
        is_dir: bool,
    ) -> Optional[RuleItem]:
        """Return the first matching RuleItem, or None."""
        for comp in self._compiled:
            if _entry_matches_candidate(
                comp,
                norm_abs=norm_abs,
                project_rel=project_rel,
                entry_rel=entry_rel,
                parts=parts,
                filename=filename,
                is_dir=is_dir,
                match_any_segment_for_name=True,
            ):
                return comp.rule
        return None

    def matches_fast(
        self,
        *,
        norm_abs: str,
        project_rel: Optional[str],
        entry_rel: str,
        parts: Sequence[str],
        filename: str,
        is_dir: bool,
    ) -> bool:
        """Fast boolean check during directory walk (`ls`)."""
        if self._has_match_all:
            return True
        if self._exact_names and any(p in self._exact_names for p in parts):
            return True
        if self._ext_suffixes and any(p.endswith(self._ext_suffixes) for p in parts):
            return True

        if self._rel_exact:
            if (project_rel and project_rel in self._rel_exact) or (
                entry_rel and entry_rel in self._rel_exact
            ):
                return True
        if self._rel_prefixes:
            if (project_rel and project_rel.startswith(self._rel_prefixes)) or (
                entry_rel and entry_rel.startswith(self._rel_prefixes)
            ):
                return True
        if self._uri_exact and norm_abs in self._uri_exact:
            return True
        if self._uri_prefixes and norm_abs.startswith(self._uri_prefixes):
            return True

        return (
            self.find_matching_rule(
                norm_abs=norm_abs,
                project_rel=project_rel,
                entry_rel=entry_rel,
                parts=parts,
                filename=filename,
                is_dir=is_dir,
            )
            is not None
        )

    def has_potential_descendant_match(
        self, norm_abs: str, project_rel: Optional[str], entry_rel: str
    ) -> bool:
        """
        Return True if any rule in this rule set could potentially match a file or subdirectory
        under the directory represented by `(norm_abs, project_rel, entry_rel)`.
        Used for safe local subtree pruning when evaluating negated presets (`!<space>`).
        """
        if not self._compiled:
            return False
        dir_abs_prefix = f"{norm_abs.rstrip('/')}/"
        rels = [r.strip("/") for r in (project_rel, entry_rel) if r]
        rel_prefixes = [f"{r}/" for r in rels if r]

        for comp in self._compiled:
            if comp.coordinate == "all":
                return True
            if comp.coordinate == "name":
                if comp.ext_suffix is None and comp.exact_val is None:
                    return True
                continue
            if comp.regex is not None:
                return True
            if comp.coordinate == "uri":
                if comp.exact_val and comp.exact_val.startswith(dir_abs_prefix):
                    return True
                if comp.prefix_val and (
                    comp.prefix_val.startswith(dir_abs_prefix)
                    or dir_abs_prefix.startswith(comp.prefix_val)
                ):
                    return True
            elif comp.coordinate == "rel":
                for rp in rel_prefixes:
                    if comp.exact_val and comp.exact_val.startswith(rp):
                        return True
                    if comp.prefix_val and (
                        comp.prefix_val.startswith(rp) or rp.startswith(comp.prefix_val)
                    ):
                        return True
                for r in rels:
                    if comp.exact_val and f"/{r}/".endswith(f"/{comp.exact_val.split('/', 1)[0]}/"):
                        return True
                    if comp.prefix_val and f"/{r}/".endswith(f"/{comp.prefix_val.split('/', 1)[0]}/"):
                        return True
        return False


def _compute_norm_rel(target_abs: Path, base_abs: Path) -> Optional[str]:
    try:
        rel = target_abs.relative_to(base_abs).as_posix()
        if rel == ".":
            return ""
        if rel.startswith(".."):
            return None
        return os.path.normcase(rel.strip("/")).replace("\\", "/")
    except ValueError:
        return None


@dataclass(frozen=True)
class SpaceConfig:
    """
    Configuration, expanded rules, and precompiled three-coordinate matchers for a single space definition.
    """

    qualified_name: str
    owner: str
    short_name: str
    description: str = ""
    entries: Tuple[str, ...] = ()
    compose: Tuple[str, ...] = ()
    presets: Tuple[str, ...] = ()
    include: Tuple[str, ...] = ()
    exclude: Tuple[str, ...] = ()
    hash_policy: HashPolicy = HashPolicy.ADAPTIVE
    large_file_threshold_mb: int = 10
    follow_symlinks: bool = False
    watch: bool = True
    effective_include: Tuple[RuleItem, ...] = ()
    effective_exclude: Tuple[RuleItem, ...] = ()
    negated_presets: Tuple["SpaceConfig", ...] = ()
    unresolved_presets: Tuple[str, ...] = ()
    unresolved_compose: Tuple[str, ...] = ()
    uri_warnings: Tuple[str, ...] = ()

    _project_root: Path = field(default_factory=lambda: Path(get_virtual_cwd()), repr=False, compare=False)
    _yscb_dir: Optional[Path] = field(default=None, repr=False, compare=False)
    _compiled_include: Optional[CompiledRuleSet] = field(default=None, init=False, repr=False, compare=False)
    _compiled_exclude: Optional[CompiledRuleSet] = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if isinstance(self.hash_policy, str):
            try:
                object.__setattr__(self, "hash_policy", HashPolicy(self.hash_policy))
            except ValueError as exc:
                raise SpaceError(
                    f"Invalid hash_policy '{self.hash_policy}' for space '{self.qualified_name}'."
                ) from exc

        try:
            if isinstance(self.large_file_threshold_mb, bool):
                raise TypeError("boolean is not a valid threshold")
            object.__setattr__(self, "large_file_threshold_mb", int(self.large_file_threshold_mb))
        except (TypeError, ValueError) as exc:
            raise SpaceError(
                f"Invalid large_file_threshold_mb '{self.large_file_threshold_mb}' for space '{self.qualified_name}'."
            ) from exc
        if self.large_file_threshold_mb <= 0:
            raise SpaceError(
                f"Space '{self.qualified_name}' large_file_threshold_mb must be positive, got {self.large_file_threshold_mb}."
            )

        object.__setattr__(self, "entries", tuple(str(e) for e in self.entries if str(e).strip()))
        object.__setattr__(self, "compose", tuple(str(c) for c in self.compose if str(c).strip()))
        object.__setattr__(self, "presets", tuple(str(p) for p in self.presets if str(p).strip()))
        object.__setattr__(self, "include", tuple(str(i) for i in self.include if str(i).strip()))
        object.__setattr__(self, "exclude", tuple(str(x) for x in self.exclude if str(x).strip()))

        if not self.effective_include:
            raw_inc = self.include if self.include else ("*",)
            object.__setattr__(
                self,
                "effective_include",
                tuple(
                    RuleItem(raw_pattern=pat, source=f"space:{self.qualified_name}")
                    for pat in raw_inc
                ),
            )
        if not self.effective_exclude and self.exclude:
            object.__setattr__(
                self,
                "effective_exclude",
                tuple(
                    RuleItem(raw_pattern=pat, source=f"space:{self.qualified_name}")
                    for pat in self.exclude
                ),
            )

        self._compile_matchers()

    def _compile_matchers(self) -> None:
        object.__setattr__(
            self,
            "_compiled_include",
            CompiledRuleSet(
                self.effective_include,
                self._project_root,
                self._yscb_dir,
                owner_module=self.owner,
                is_exclude=False,
            ),
        )
        object.__setattr__(
            self,
            "_compiled_exclude",
            CompiledRuleSet(
                self.effective_exclude,
                self._project_root,
                self._yscb_dir,
                owner_module=self.owner,
                is_exclude=True,
            ),
        )

    def resolve_entries(
        self, project_root: Optional[Path] = None
    ) -> List[Tuple[str, Optional[Path], bool]]:
        """
        Resolve each declared entry URI/path into `(raw_entry, resolved_path, exists_on_disk)`.
        Never raises FileNotFoundError for missing physical paths.
        """
        proj = Path(os.path.abspath(str(project_root or self._project_root)))
        results: List[Tuple[str, Optional[Path], bool]] = []
        for raw_entry in self.entries:
            resolved = resolve_semantic_or_rel_path(
                raw_entry, proj, self._yscb_dir, owner_module=self.owner
            )
            if resolved is None:
                results.append((raw_entry, None, False))
                continue
            try:
                exists = resolved.exists()
            except OSError:
                exists = False
            results.append((raw_entry, resolved, exists))
        return results

    def _prepare_candidate_coords(
        self, target_abs: Path, entry_abs: Path, project_root: Path
    ) -> Tuple[str, Optional[str], str, List[str], str]:
        norm_abs = os.path.normcase(target_abs.as_posix()).replace("\\", "/").rstrip("/")
        project_rel = _compute_norm_rel(target_abs, project_root)
        entry_rel_opt = _compute_norm_rel(target_abs, entry_abs)
        if entry_rel_opt is None or entry_rel_opt == "":
            entry_rel = os.path.normcase(target_abs.name).replace("\\", "/")
        else:
            entry_rel = entry_rel_opt

        rel_for_parts = (
            entry_rel if entry_rel else (project_rel or os.path.normcase(target_abs.name).replace("\\", "/"))
        )
        parts: List[str] = []
        if project_rel:
            for p in project_rel.split("/"):
                if p and p != "." and p not in parts:
                    parts.append(p)
        for p in rel_for_parts.split("/"):
            if p and p != "." and p not in parts:
                parts.append(p)
        filename = os.path.normcase(target_abs.name).replace("\\", "/")
        if filename and filename not in parts:
            parts.append(filename)
        return norm_abs, project_rel, entry_rel, parts, filename

    def is_dir_excluded_fast(
        self, dir_abs: Path, entry_abs: Path, project_root: Path
    ) -> bool:
        """Fast boolean directory exclusion check for `os.scandir` pruning."""
        if self._compiled_exclude is None:
            self._compile_matchers()
        assert self._compiled_exclude is not None
        norm_abs, project_rel, entry_rel, parts, filename = self._prepare_candidate_coords(
            dir_abs, entry_abs, project_root
        )
        if self._compiled_exclude.matches_fast(
            norm_abs=norm_abs,
            project_rel=project_rel,
            entry_rel=entry_rel,
            parts=parts,
            filename=filename,
            is_dir=True,
        ):
            return True
        for neg_sp in self.negated_presets:
            if neg_sp._compiled_include is None or neg_sp._compiled_exclude is None:
                neg_sp._compile_matchers()
            assert neg_sp._compiled_include is not None
            assert neg_sp._compiled_exclude is not None
            if neg_sp._compiled_include.matches_fast(
                norm_abs=norm_abs,
                project_rel=project_rel,
                entry_rel=entry_rel,
                parts=parts,
                filename=filename,
                is_dir=True,
            ):
                if not neg_sp._compiled_exclude.matches_fast(
                    norm_abs=norm_abs,
                    project_rel=project_rel,
                    entry_rel=entry_rel,
                    parts=parts,
                    filename=filename,
                    is_dir=True,
                ) and not neg_sp._compiled_exclude.has_potential_descendant_match(
                    norm_abs, project_rel, entry_rel
                ):
                    return True
        return False

    def is_dir_excluded(
        self, dir_abs: Path, entry_abs: Path, project_root: Path
    ) -> bool:
        """Alias for `is_dir_excluded_fast`."""
        return self.is_dir_excluded_fast(dir_abs, entry_abs, project_root)

    def check_dir_excluded(
        self, dir_abs: Path, entry_abs: Path, project_root: Path
    ) -> Optional[RuleItem]:
        """Return the specific exclude RuleItem that prunes `dir_abs`, or None."""
        if self._compiled_exclude is None:
            self._compile_matchers()
        assert self._compiled_exclude is not None
        norm_abs, project_rel, entry_rel, parts, filename = self._prepare_candidate_coords(
            dir_abs, entry_abs, project_root
        )
        own_excl = self._compiled_exclude.find_matching_rule(
            norm_abs=norm_abs,
            project_rel=project_rel,
            entry_rel=entry_rel,
            parts=parts,
            filename=filename,
            is_dir=True,
        )
        if own_excl is not None:
            return own_excl
        for neg_sp in self.negated_presets:
            if neg_sp._compiled_include is None or neg_sp._compiled_exclude is None:
                neg_sp._compile_matchers()
            assert neg_sp._compiled_include is not None
            assert neg_sp._compiled_exclude is not None
            neg_inc_rule = neg_sp._compiled_include.find_matching_rule(
                norm_abs=norm_abs,
                project_rel=project_rel,
                entry_rel=entry_rel,
                parts=parts,
                filename=filename,
                is_dir=True,
            )
            if neg_inc_rule is not None:
                if not neg_sp._compiled_exclude.matches_fast(
                    norm_abs=norm_abs,
                    project_rel=project_rel,
                    entry_rel=entry_rel,
                    parts=parts,
                    filename=filename,
                    is_dir=True,
                ) and not neg_sp._compiled_exclude.has_potential_descendant_match(
                    norm_abs, project_rel, entry_rel
                ):
                    return RuleItem(
                        raw_pattern=neg_inc_rule.raw_pattern,
                        source=f"preset:!{neg_sp.qualified_name}",
                        is_negated=True,
                    )
        return None

    def is_file_matched_fast(
        self, file_abs: Path, entry_abs: Path, project_root: Path
    ) -> bool:
        """Fast boolean file inclusion check (exclude takes priority over include)."""
        if self._compiled_exclude is None or self._compiled_include is None:
            self._compile_matchers()
        assert self._compiled_exclude is not None
        assert self._compiled_include is not None
        norm_abs, project_rel, entry_rel, parts, filename = self._prepare_candidate_coords(
            file_abs, entry_abs, project_root
        )
        if self._compiled_exclude.matches_fast(
            norm_abs=norm_abs,
            project_rel=project_rel,
            entry_rel=entry_rel,
            parts=parts,
            filename=filename,
            is_dir=False,
        ):
            return False
        for neg_sp in self.negated_presets:
            if neg_sp._compiled_include is None or neg_sp._compiled_exclude is None:
                neg_sp._compile_matchers()
            assert neg_sp._compiled_include is not None
            assert neg_sp._compiled_exclude is not None
            if neg_sp._compiled_include.matches_fast(
                norm_abs=norm_abs,
                project_rel=project_rel,
                entry_rel=entry_rel,
                parts=parts,
                filename=filename,
                is_dir=False,
            ) and not neg_sp._compiled_exclude.matches_fast(
                norm_abs=norm_abs,
                project_rel=project_rel,
                entry_rel=entry_rel,
                parts=parts,
                filename=filename,
                is_dir=False,
            ):
                return False
        return self._compiled_include.matches_fast(
            norm_abs=norm_abs,
            project_rel=project_rel,
            entry_rel=entry_rel,
            parts=parts,
            filename=filename,
            is_dir=False,
        )

    def match_file(
        self,
        file_abs: Path,
        entry_abs: Path,
        project_root: Path,
        *,
        is_dir: bool = False,
    ) -> Tuple[bool, Optional[RuleItem], Optional[RuleItem]]:
        """
        Evaluate a target path against this space's exclude and include rules.
        Returns `(is_matched, matched_include_rule, matched_exclude_rule)`.
        """
        if self._compiled_exclude is None or self._compiled_include is None:
            self._compile_matchers()
        assert self._compiled_exclude is not None
        assert self._compiled_include is not None

        norm_abs, project_rel, entry_rel, parts, filename = self._prepare_candidate_coords(
            file_abs, entry_abs, project_root
        )

        # Also check if any ancestor directory under entry_abs is excluded
        cur = file_abs.parent
        ancestors: List[Path] = []
        while True:
            try:
                rel_anc = cur.relative_to(entry_abs)
            except ValueError:
                break
            if str(rel_anc) == ".":
                break
            ancestors.append(cur)
            if cur.parent == cur:
                break
            cur = cur.parent

        for anc in reversed(ancestors):
            anc_excl = self.check_dir_excluded(anc, entry_abs, project_root)
            if anc_excl is not None:
                return False, None, anc_excl

        excl_rule = self._compiled_exclude.find_matching_rule(
            norm_abs=norm_abs,
            project_rel=project_rel,
            entry_rel=entry_rel,
            parts=parts,
            filename=filename,
            is_dir=is_dir,
        )
        if excl_rule is not None:
            return False, None, excl_rule

        for neg_sp in self.negated_presets:
            if neg_sp._compiled_include is None or neg_sp._compiled_exclude is None:
                neg_sp._compile_matchers()
            assert neg_sp._compiled_include is not None
            assert neg_sp._compiled_exclude is not None
            neg_inc_rule = neg_sp._compiled_include.find_matching_rule(
                norm_abs=norm_abs,
                project_rel=project_rel,
                entry_rel=entry_rel,
                parts=parts,
                filename=filename,
                is_dir=is_dir,
            )
            if neg_inc_rule is not None and not neg_sp._compiled_exclude.matches_fast(
                norm_abs=norm_abs,
                project_rel=project_rel,
                entry_rel=entry_rel,
                parts=parts,
                filename=filename,
                is_dir=is_dir,
            ):
                return False, None, neg_inc_rule

        if is_dir:
            return True, RuleItem(raw_pattern="*", source=f"space:{self.qualified_name}"), None

        inc_rule = self._compiled_include.find_matching_rule(
            norm_abs=norm_abs,
            project_rel=project_rel,
            entry_rel=entry_rel,
            parts=parts,
            filename=filename,
            is_dir=False,
        )
        return (inc_rule is not None), inc_rule, None

    def to_dict(self, project_root: Optional[Path] = None) -> Dict[str, Any]:
        """Serialize SpaceConfig and resolved entry diagnostics into a dictionary."""
        resolved_entries_info = []
        for raw_e, res_p, exists in self.resolve_entries(project_root):
            resolved_entries_info.append(
                {
                    "entry": raw_e,
                    "resolved_path": res_p.as_posix() if res_p is not None else None,
                    "exists": exists,
                }
            )
        return {
            "qualified_name": self.qualified_name,
            "owner": self.owner,
            "short_name": self.short_name,
            "description": self.description,
            "entries": list(self.entries),
            "compose": list(self.compose),
            "resolved_entries": resolved_entries_info,
            "presets": list(self.presets),
            "unresolved_presets": list(self.unresolved_presets),
            "unresolved_compose": list(self.unresolved_compose),
            "uri_warnings": list(self.uri_warnings),
            "include": list(self.include) if self.include else ["*"],
            "exclude": list(self.exclude),
            "effective_include": [
                {"pattern": r.raw_pattern, "source": r.source} for r in self.effective_include
            ],
            "effective_exclude": [
                {"pattern": r.raw_pattern, "source": r.source} for r in self.effective_exclude
            ],
            "hash_policy": self.hash_policy.value,
            "large_file_threshold_mb": self.large_file_threshold_mb,
            "follow_symlinks": self.follow_symlinks,
            "watch": self.watch,
        }
