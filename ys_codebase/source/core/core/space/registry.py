"""
SpaceRegistry: Namespace-isolated `<owner>/<name>` loading, `<name>` short-name union addressing,
single-point `match_path` explainability, and zero-redundancy `os.scandir` pruned `iter_space_files`.
"""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

from .exceptions import SpaceNotFoundError
from .schema import (
    GitignoreEvaluator,
    HashPolicy,
    PresetConfig,
    RuleItem,
    SpaceConfig,
    resolve_semantic_or_rel_path,
)


def _sort_owner_keys(owners: Iterable[str]) -> List[str]:
    """Deterministic ordering: `core` first, alphabetical modules next, `project` last."""
    owner_set = set(owners)
    ordered: List[str] = []
    if "core" in owner_set:
        ordered.append("core")
        owner_set.remove("core")
    has_proj = "project" in owner_set
    if has_proj:
        owner_set.remove("project")
    ordered.extend(sorted(owner_set))
    if has_proj:
        ordered.append("project")
    return ordered


def _parse_qualified_key(key: str, default_owner: str) -> Tuple[str, str, str]:
    clean = str(key or "").strip().strip("/")
    if "/" in clean:
        owner, short = clean.split("/", 1)
        owner = owner.strip() or default_owner
        short = short.strip()
    else:
        owner = default_owner
        short = clean
    return f"{owner}/{short}", owner, short


def _has_intervening_symlink(child: Path, parent: Path) -> bool:
    """Return True if any path segment from child up to parent (inclusive of child) is a symlink."""
    try:
        rel_parts = child.relative_to(parent).parts
    except ValueError:
        return True
    cur = parent
    for part in rel_parts:
        cur = cur / part
        try:
            if cur.is_symlink():
                return True
        except OSError:
            return True
    return False


def compute_canonical_rel_path(
    file_abs: Path,
    entry_abs: Path,
    project_root: Path,
) -> str:
    """
    Compute canonical display relative path (POSIX).
    Tries relative to `project_root` first; if outside `project_root`, falls back
    gracefully to relative to `entry_abs` without raising ValueError.
    """
    try:
        rel_proj = file_abs.relative_to(project_root).as_posix()
        if rel_proj and rel_proj != "." and not rel_proj.startswith(".."):
            return rel_proj
    except ValueError:
        pass

    try:
        rel_entry = file_abs.relative_to(entry_abs).as_posix()
        if rel_entry and rel_entry != "." and not rel_entry.startswith(".."):
            entry_prefix = entry_abs.name
            return f"{entry_prefix}/{rel_entry}" if entry_prefix else rel_entry
    except ValueError:
        pass

    return file_abs.name


@dataclass(frozen=True)
class SpaceFileEntry:
    """Canonical deduplicated file entry yielded by `iter_space_files`."""

    rel_path: str
    abs_path: Path
    entry_path: Path
    matched_spaces: Tuple[str, ...]
    size: int
    mtime_ns: int
    ctime_ns: int

    def to_dict(self) -> Dict[str, Any]:
        """Serialize SpaceFileEntry into a dictionary."""
        return {
            "rel_path": self.rel_path,
            "abs_path": self.abs_path.as_posix(),
            "entry_path": self.entry_path.as_posix(),
            "matched_spaces": list(self.matched_spaces),
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "ctime_ns": self.ctime_ns,
        }


@dataclass(frozen=True)
class SpaceMatchDetail:
    """Per-space diagnostic explanation for `match_path`."""

    qualified_space: str
    matched: bool
    reason: str
    matched_entry: Optional[str] = None
    include_rule: Optional[str] = None
    include_source: Optional[str] = None
    exclude_rule: Optional[str] = None
    exclude_source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize SpaceMatchDetail into a dictionary."""
        return {
            "qualified_space": self.qualified_space,
            "matched": self.matched,
            "reason": self.reason,
            "matched_entry": self.matched_entry,
            "include_rule": self.include_rule,
            "include_source": self.include_source,
            "exclude_rule": self.exclude_rule,
            "exclude_source": self.exclude_source,
        }


@dataclass(frozen=True)
class MatchExplainResult:
    """Aggregated result of `match_path` across one or more spaces."""

    target_path: str
    abs_path: str
    matched: bool
    matched_spaces: Tuple[str, ...]
    details: Tuple[SpaceMatchDetail, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize MatchExplainResult into a dictionary."""
        return {
            "target_path": self.target_path,
            "abs_path": self.abs_path,
            "matched": self.matched,
            "matched_spaces": list(self.matched_spaces),
            "details": [d.to_dict() for d in self.details],
        }


class SpaceRegistry:
    """
    Atomic registry for `<owner>/<name>` presets and spaces with short-name `<name>` union addressing.
    """

    def __init__(
        self,
        project_root: Optional[Union[str, Path]] = None,
        yscb_dir: Optional[Union[str, Path]] = None,
        *,
        raw_presets: Optional[Dict[str, Dict[str, Any]]] = None,
        raw_spaces: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self._project_root, self._yscb_dir = self._resolve_roots(
            project_root, yscb_dir
        )
        self._explicit_presets = raw_presets
        self._explicit_spaces = raw_spaces

        self._presets: Dict[str, PresetConfig] = {}
        self._presets_by_short: Dict[str, List[PresetConfig]] = {}
        self._spaces: Dict[str, SpaceConfig] = {}
        self._spaces_by_short: Dict[str, List[SpaceConfig]] = {}
        self._gitignore_eval: Optional[GitignoreEvaluator] = None

        self.reload()

    @staticmethod
    def _resolve_roots(
        project_root: Optional[Union[str, Path]],
        yscb_dir: Optional[Union[str, Path]],
    ) -> Tuple[Path, Path]:
        default_proj: Optional[Path] = None
        default_yscb: Optional[Path] = None
        try:
            from core import uri as core_uri

            p_str = core_uri.resolve("project://", interactive=False)
            if p_str and not str(p_str).startswith("!undefined"):
                default_proj = Path(os.path.normpath(os.path.abspath(str(p_str))))
        except Exception:
            default_proj = None

        try:
            from core import uri as core_uri

            y_str = core_uri.resolve_yscb_root()
            if y_str:
                default_yscb = Path(os.path.normpath(os.path.abspath(str(y_str))))
        except Exception:
            default_yscb = None

        if default_proj is None:
            if default_yscb is not None and default_yscb.name == "ys_codebase":
                default_proj = default_yscb.parent
            else:
                default_proj = Path(os.path.normpath(os.path.abspath(os.getcwd())))

        if default_yscb is None:
            cand = default_proj / "ys_codebase"
            default_yscb = cand if cand.is_dir() else default_proj

        eff_proj = (
            Path(os.path.normpath(os.path.abspath(str(project_root))))
            if project_root is not None
            else default_proj
        )
        if yscb_dir is not None:
            eff_yscb = Path(os.path.normpath(os.path.abspath(str(yscb_dir))))
        elif project_root is not None and os.path.normcase(str(eff_proj)) != os.path.normcase(
            str(default_proj)
        ):
            cand_yscb = eff_proj / "ys_codebase"
            cand_dot = eff_proj / ".yscb"
            if cand_yscb.is_dir():
                eff_yscb = cand_yscb
            elif cand_dot.is_dir():
                eff_yscb = cand_dot
            else:
                eff_yscb = eff_proj
        else:
            eff_yscb = default_yscb

        return eff_proj, eff_yscb

    @property
    def project_root(self) -> Path:
        """Return normalized project root Path."""
        return self._project_root

    @property
    def yscb_dir(self) -> Path:
        """Return normalized YSCB root directory Path."""
        return self._yscb_dir

    def _get_gitignore_evaluator(self) -> GitignoreEvaluator:
        if self._gitignore_eval is None:
            self._gitignore_eval = GitignoreEvaluator.from_gitignore_file(
                self._project_root, self._yscb_dir
            )
        return self._gitignore_eval

    def reload(self) -> None:
        """Reload all preset and space definitions from modules and project configuration."""
        self._presets.clear()
        self._presets_by_short.clear()
        self._spaces.clear()
        self._spaces_by_short.clear()
        self._gitignore_eval = None

        raw_presets_by_owner, raw_spaces_by_owner = self._discover_raw_definitions()

        # 1. Register presets in deterministic owner order
        for owner in _sort_owner_keys(raw_presets_by_owner.keys()):
            owner_presets = raw_presets_by_owner[owner]
            for short_name in sorted(owner_presets.keys()):
                p_data = owner_presets[short_name]
                if not isinstance(p_data, dict):
                    continue
                q_name = f"{owner}/{short_name}"
                inc_list = [str(x) for x in p_data.get("include", []) if str(x).strip()]
                exc_list = [str(x) for x in p_data.get("exclude", []) if str(x).strip()]
                preset_cfg = PresetConfig(
                    qualified_name=q_name,
                    owner=owner,
                    short_name=short_name,
                    description=str(p_data.get("description", "") or ""),
                    include=tuple(inc_list),
                    exclude=tuple(exc_list),
                )
                self._presets[q_name] = preset_cfg
                self._presets_by_short.setdefault(short_name, []).append(preset_cfg)

        # 2. Build and register spaces in deterministic owner order
        for owner in _sort_owner_keys(raw_spaces_by_owner.keys()):
            owner_spaces = raw_spaces_by_owner[owner]
            for short_name in sorted(owner_spaces.keys()):
                s_data = owner_spaces[short_name]
                if not isinstance(s_data, dict):
                    continue
                space_cfg = self._build_space_config(owner, short_name, s_data)
                self._spaces[space_cfg.qualified_name] = space_cfg
                self._spaces_by_short.setdefault(short_name, []).append(space_cfg)

    def _discover_raw_definitions(
        self,
    ) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], Dict[str, Dict[str, Dict[str, Any]]]]:
        presets_by_owner: Dict[str, Dict[str, Dict[str, Any]]] = {}
        spaces_by_owner: Dict[str, Dict[str, Dict[str, Any]]] = {}

        if self._explicit_presets is not None or self._explicit_spaces is not None:
            for k, v in (self._explicit_presets or {}).items():
                if not isinstance(v, dict):
                    continue
                _, owner, short = _parse_qualified_key(k, str(v.get("owner", "project")))
                presets_by_owner.setdefault(owner, {})[short] = dict(v)

            for k, v in (self._explicit_spaces or {}).items():
                if not isinstance(v, dict):
                    continue
                _, owner, short = _parse_qualified_key(k, str(v.get("owner", "project")))
                spaces_by_owner.setdefault(owner, {})[short] = dict(v)
            return presets_by_owner, spaces_by_owner

        # Scan installed modules in yscb_dir/.modules/*/contributes/core.json
        modules_dir = self._yscb_dir / ".modules"
        if modules_dir.is_dir():
            try:
                mod_names = sorted(os.listdir(modules_dir))
            except OSError:
                mod_names = []
            for mod_name in mod_names:
                if mod_name.startswith("."):
                    continue
                core_json = modules_dir / mod_name / "contributes" / "core.json"
                if core_json.is_file():
                    self._extract_file_definitions(
                        core_json, mod_name, presets_by_owner, spaces_by_owner
                    )

        # Fallback for core's own contributes/core.json if core is not yet materialized in .modules
        if "core" not in presets_by_owner and "core" not in spaces_by_owner:
            core_pkg_root = Path(__file__).resolve().parents[2]
            self_core_json = core_pkg_root / "contributes" / "core.json"
            if self_core_json.is_file():
                self._extract_file_definitions(
                    self_core_json, "core", presets_by_owner, spaces_by_owner
                )

        # Scan project-level config/core/contribute.json
        proj_contrib = self._yscb_dir / "config" / "core" / "contribute.json"
        if proj_contrib.is_file():
            self._extract_file_definitions(
                proj_contrib, "project", presets_by_owner, spaces_by_owner
            )

        return presets_by_owner, spaces_by_owner

    @staticmethod
    def _extract_file_definitions(
        json_path: Path,
        default_owner: str,
        presets_by_owner: Dict[str, Dict[str, Dict[str, Any]]],
        spaces_by_owner: Dict[str, Dict[str, Dict[str, Any]]],
    ) -> None:
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        body = payload.get("core", payload) if isinstance(payload.get("core"), dict) else payload
        if not isinstance(body, dict):
            return

        raw_p = body.get("presets")
        if isinstance(raw_p, dict):
            for p_key, p_val in raw_p.items():
                if str(p_key).startswith("_") or not isinstance(p_val, dict):
                    continue
                _, owner, short = _parse_qualified_key(p_key, default_owner)
                presets_by_owner.setdefault(owner, {})[short] = dict(p_val)

        raw_s = body.get("spaces")
        if isinstance(raw_s, dict):
            for s_key, s_val in raw_s.items():
                if str(s_key).startswith("_") or not isinstance(s_val, dict):
                    continue
                _, owner, short = _parse_qualified_key(s_key, default_owner)
                spaces_by_owner.setdefault(owner, {})[short] = dict(s_val)

    def _build_space_config(
        self, owner: str, short_name: str, raw_data: Dict[str, Any]
    ) -> SpaceConfig:
        q_name = f"{owner}/{short_name}"
        raw_entries = raw_data.get("entries", raw_data.get("include_entries", []))
        if not isinstance(raw_entries, (list, tuple)):
            raw_entries = []
        entries_tuple = tuple(str(e) for e in raw_entries if str(e).strip())

        raw_presets = raw_data.get("presets", [])
        if not isinstance(raw_presets, (list, tuple)):
            raw_presets = []
        presets_tuple = tuple(str(p) for p in raw_presets if str(p).strip())

        raw_inc = raw_data.get("include", [])
        if not isinstance(raw_inc, (list, tuple)):
            raw_inc = []
        inc_tuple = tuple(str(i) for i in raw_inc if str(i).strip())

        raw_exc = raw_data.get("exclude", [])
        if not isinstance(raw_exc, (list, tuple)):
            raw_exc = []
        exc_tuple = tuple(str(x) for x in raw_exc if str(x).strip())

        effective_inc: List[RuleItem] = []
        effective_exc: List[RuleItem] = []
        unresolved: List[str] = []
        uses_gitignore = False

        # Expand explicit presets only (no implicit global default_presets)
        for preset_ref in presets_tuple:
            if preset_ref == "@gitignore":
                uses_gitignore = True
                continue
            matched_presets = self._lookup_presets_non_throwing(preset_ref)
            if not matched_presets:
                if preset_ref not in unresolved:
                    unresolved.append(preset_ref)
                continue
            for p_cfg in matched_presets:
                p_src = f"preset:{p_cfg.qualified_name}"
                for pat in p_cfg.include:
                    item = RuleItem(raw_pattern=pat, source=p_src)
                    if item not in effective_inc:
                        effective_inc.append(item)
                for pat in p_cfg.exclude:
                    item = RuleItem(raw_pattern=pat, source=p_src)
                    if item not in effective_exc:
                        effective_exc.append(item)

        space_src = f"space:{q_name}"
        for pat in inc_tuple:
            item = RuleItem(raw_pattern=pat, source=space_src)
            if item not in effective_inc:
                effective_inc.append(item)

        for pat in exc_tuple:
            item = RuleItem(raw_pattern=pat, source=space_src)
            if item not in effective_exc:
                effective_exc.append(item)

        if not effective_inc:
            effective_inc.append(RuleItem(raw_pattern="*", source=space_src))

        # Check URI warnings on entries and URI rules
        uri_warnings: List[str] = []
        for entry_str in entries_tuple:
            if "://" in entry_str:
                res = resolve_semantic_or_rel_path(
                    entry_str, self._project_root, self._yscb_dir, owner_module=owner
                )
                if res is None:
                    uri_warnings.append(f"Unresolvable entry URI: '{entry_str}'")

        gi_eval = self._get_gitignore_evaluator() if uses_gitignore else None

        return SpaceConfig(
            qualified_name=q_name,
            owner=owner,
            short_name=short_name,
            description=str(raw_data.get("description", "") or ""),
            entries=entries_tuple,
            presets=presets_tuple,
            include=inc_tuple,
            exclude=exc_tuple,
            hash_policy=raw_data.get("hash_policy", HashPolicy.ADAPTIVE),
            large_file_threshold_mb=raw_data.get("large_file_threshold_mb", 10),
            follow_symlinks=bool(raw_data.get("follow_symlinks", False)),
            effective_include=tuple(effective_inc),
            effective_exclude=tuple(effective_exc),
            unresolved_presets=tuple(unresolved),
            uri_warnings=tuple(uri_warnings),
            _project_root=self._project_root,
            _yscb_dir=self._yscb_dir,
            _gitignore_eval=gi_eval,
        )

    def _lookup_presets_non_throwing(self, query: str) -> List[PresetConfig]:
        q = str(query or "").strip()
        if not q:
            return []
        if "/" in q:
            found = self._presets.get(q)
            return [found] if found is not None else []
        return list(self._presets_by_short.get(q, []))

    def list_presets(self, owner: Optional[str] = None) -> List[PresetConfig]:
        """List all registered PresetConfig instances in deterministic order."""
        if owner:
            return [p for p in self._presets.values() if p.owner == owner]
        return list(self._presets.values())

    def resolve_presets(self, query: str) -> List[PresetConfig]:
        """
        Resolve `<owner>/<preset>` (single definition) or `<preset>` short name (union of definitions).
        Raises SpaceNotFoundError if not found.
        """
        q = str(query or "").strip()
        if q == "@gitignore":
            gi_eval = self._get_gitignore_evaluator()
            raw_pats = [comp.rule.raw_pattern for comp, _ in gi_eval._rules]
            return [
                PresetConfig(
                    qualified_name="@gitignore",
                    owner="builtin",
                    short_name="@gitignore",
                    description="Built-in dynamic preset from project://.gitignore",
                    include=(),
                    exclude=tuple(raw_pats),
                )
            ]
        matched = self._lookup_presets_non_throwing(q)
        if not matched:
            available = sorted(self._presets.keys())
            raise SpaceNotFoundError(
                f"Preset '{query}' is not registered. Available presets: {available}"
            )
        return matched

    def list_spaces(self, owner: Optional[str] = None) -> List[SpaceConfig]:
        """List all registered SpaceConfig instances in deterministic order."""
        if owner:
            return [s for s in self._spaces.values() if s.owner == owner]
        return list(self._spaces.values())

    def resolve_spaces(self, query: Optional[str] = None) -> List[SpaceConfig]:
        """
        Resolve space query:
        - `None` -> all registered spaces
        - `<owner>/<space>` (contains `/`) -> exact single SpaceConfig
        - `<space>` (no `/`) -> union of all SpaceConfig definitions with `short_name == <space>`
        Raises SpaceNotFoundError if no space matches.
        """
        if query is None or str(query).strip() == "":
            return list(self._spaces.values())

        q = str(query).strip()
        if "/" in q:
            found = self._spaces.get(q)
            if found is None:
                available = sorted(self._spaces.keys())
                raise SpaceNotFoundError(
                    f"Space '{q}' is not registered. Available spaces: {available}"
                )
            return [found]

        matched = list(self._spaces_by_short.get(q, []))
        if not matched:
            available = sorted(set(self._spaces.keys()) | set(self._spaces_by_short.keys()))
            raise SpaceNotFoundError(
                f"Space '{q}' is not registered. Available spaces: {available}"
            )
        return matched

    def get_spaces(self, query: Optional[str] = None) -> List[SpaceConfig]:
        """Alias for `resolve_spaces(query)`."""
        return self.resolve_spaces(query)

    def match_path(
        self,
        file_path: Union[str, Path],
        space_query: Optional[str] = None,
    ) -> MatchExplainResult:
        """
        Single-point three-coordinate path judgment and explanation without full disk scanning.
        Evaluates whether `file_path` belongs to the queried space(s) and explains the exact
        entry, include rule, or exclude rule responsible.
        """
        target_spaces = self.resolve_spaces(space_query)
        raw_str = file_path.as_posix() if isinstance(file_path, Path) else str(file_path).strip()

        if "://" in raw_str:
            resolved_target = resolve_semantic_or_rel_path(
                raw_str, self._project_root, self._yscb_dir
            )
            if resolved_target is None:
                resolved_target = Path(os.path.normpath(os.path.abspath(raw_str)))
        else:
            p = Path(raw_str)
            if p.is_absolute():
                resolved_target = Path(os.path.normpath(str(p)))
            else:
                resolved_target = Path(os.path.normpath(str(self._project_root / p)))

        try:
            is_dir = resolved_target.is_dir()
        except OSError:
            is_dir = raw_str.endswith(("/", "\\"))

        matched_space_names: List[str] = []
        details: List[SpaceMatchDetail] = []

        for space_cfg in target_spaces:
            detail = self._evaluate_single_space_match(
                space_cfg, resolved_target, is_dir=is_dir
            )
            details.append(detail)
            if detail.matched:
                matched_space_names.append(space_cfg.qualified_name)

        return MatchExplainResult(
            target_path=raw_str,
            abs_path=resolved_target.as_posix(),
            matched=bool(matched_space_names),
            matched_spaces=tuple(matched_space_names),
            details=tuple(details),
        )

    def _evaluate_single_space_match(
        self,
        space_cfg: SpaceConfig,
        target_abs: Path,
        *,
        is_dir: bool,
    ) -> SpaceMatchDetail:
        try:
            if not space_cfg.follow_symlinks and target_abs.is_symlink():
                return SpaceMatchDetail(
                    qualified_space=space_cfg.qualified_name,
                    matched=False,
                    reason="symlink_not_followed",
                )
        except OSError:
            pass

        resolved_entries = space_cfg.resolve_entries(self._project_root)
        candidate_entries: List[Tuple[str, Path]] = []

        for raw_entry, entry_path, _exists in resolved_entries:
            if entry_path is None:
                continue
            if os.path.normcase(str(target_abs)) == os.path.normcase(str(entry_path)):
                candidate_entries.append((raw_entry, entry_path))
                continue
            try:
                rel = target_abs.relative_to(entry_path)
                if str(rel) != "." and not str(rel).startswith(".."):
                    if not space_cfg.follow_symlinks and _has_intervening_symlink(
                        target_abs, entry_path
                    ):
                        continue
                    candidate_entries.append((raw_entry, entry_path))
                    continue
            except ValueError:
                pass

            if space_cfg.follow_symlinks:
                try:
                    t_real = target_abs.resolve()
                    e_real = entry_path.resolve()
                    if t_real == e_real or not str(t_real.relative_to(e_real)).startswith(".."):
                        candidate_entries.append((raw_entry, e_real))
                except (OSError, ValueError):
                    pass

        if not candidate_entries:
            return SpaceMatchDetail(
                qualified_space=space_cfg.qualified_name,
                matched=False,
                reason="outside_entries",
            )

        # Sort candidate entries by deepest (most specific) path first
        candidate_entries.sort(key=lambda item: len(item[1].parts), reverse=True)

        last_detail: Optional[SpaceMatchDetail] = None
        for raw_entry, entry_path in candidate_entries:
            matched, inc_rule, exc_rule = space_cfg.match_file(
                target_abs, entry_path, self._project_root, is_dir=is_dir
            )
            if matched:
                return SpaceMatchDetail(
                    qualified_space=space_cfg.qualified_name,
                    matched=True,
                    reason="included",
                    matched_entry=raw_entry,
                    include_rule=inc_rule.raw_pattern if inc_rule else "*",
                    include_source=inc_rule.source if inc_rule else f"space:{space_cfg.qualified_name}",
                )
            if exc_rule is not None:
                last_detail = SpaceMatchDetail(
                    qualified_space=space_cfg.qualified_name,
                    matched=False,
                    reason="excluded",
                    matched_entry=raw_entry,
                    exclude_rule=exc_rule.raw_pattern,
                    exclude_source=exc_rule.source,
                )
            elif last_detail is None:
                last_detail = SpaceMatchDetail(
                    qualified_space=space_cfg.qualified_name,
                    matched=False,
                    reason="not_matching_include",
                    matched_entry=raw_entry,
                )

        assert last_detail is not None
        return last_detail

    def iter_space_files(
        self,
        space_query: Optional[str] = None,
        *,
        pattern: Optional[str] = None,
    ) -> List[SpaceFileEntry]:
        """
        Zero-redundancy directory-pruned file walker using `os.scandir` and `DirEntry.stat()`.
        Deduplicates physical files across multiple entries and unioned spaces, returning
        deterministically sorted `SpaceFileEntry` items.
        """
        target_spaces = self.resolve_spaces(space_query)

        # Dedup map: norm_physical_key -> (rel_path, abs_path, entry_path, [qualified_spaces], size, mtime_ns, ctime_ns)
        dedup_map: Dict[str, List[Any]] = {}

        for space_cfg in target_spaces:
            self._walk_single_space(space_cfg, dedup_map)

        results: List[SpaceFileEntry] = []
        norm_pattern = pattern.replace("\\", "/").strip("/") if pattern else None

        for item in dedup_map.values():
            rel_path, abs_path, entry_path, matched_spaces, size, mtime_ns, ctime_ns = item
            if norm_pattern:
                if not (
                    fnmatch.fnmatch(rel_path, norm_pattern)
                    or fnmatch.fnmatch(abs_path.name, norm_pattern)
                ):
                    continue
            results.append(
                SpaceFileEntry(
                    rel_path=rel_path,
                    abs_path=abs_path,
                    entry_path=entry_path,
                    matched_spaces=tuple(matched_spaces),
                    size=size,
                    mtime_ns=mtime_ns,
                    ctime_ns=ctime_ns,
                )
            )

        results.sort(key=lambda e: (e.rel_path, e.abs_path.as_posix()))
        return results

    def _walk_single_space(
        self,
        space_cfg: SpaceConfig,
        dedup_map: Dict[str, List[Any]],
    ) -> None:
        resolved_entries = space_cfg.resolve_entries(self._project_root)

        # Prepare valid existing entries, sorted so more specific entries are known
        valid_entries: List[Path] = []
        for _raw_e, entry_path, exists in resolved_entries:
            if entry_path is None or not exists:
                continue
            valid_entries.append(entry_path)

        visited_inodes: Set[Tuple[int, int]] = set()
        visited_dirs_norm: Set[str] = set()

        for entry_path in valid_entries:
            try:
                is_sym = entry_path.is_symlink()
                if is_sym and not space_cfg.follow_symlinks:
                    continue
                st = entry_path.stat() if space_cfg.follow_symlinks else entry_path.lstat()
            except OSError:
                continue

            if entry_path.is_file():
                # Single-file entry
                if space_cfg.is_file_matched_fast(entry_path, entry_path, self._project_root):
                    self._record_matched_file(
                        file_abs=entry_path,
                        entry_abs=entry_path,
                        space_cfg=space_cfg,
                        st=st,
                        dedup_map=dedup_map,
                    )
            elif entry_path.is_dir():
                self._scandir_walk_recursive(
                    current_dir=entry_path,
                    entry_abs=entry_path,
                    all_space_entries=valid_entries,
                    space_cfg=space_cfg,
                    visited_inodes=visited_inodes,
                    visited_dirs_norm=visited_dirs_norm,
                    dedup_map=dedup_map,
                )

    def _scandir_walk_recursive(
        self,
        current_dir: Path,
        entry_abs: Path,
        all_space_entries: Sequence[Path],
        space_cfg: SpaceConfig,
        visited_inodes: Set[Tuple[int, int]],
        visited_dirs_norm: Set[str],
        dedup_map: Dict[str, List[Any]],
    ) -> None:
        if space_cfg.follow_symlinks:
            try:
                dir_st = current_dir.stat()
                if dir_st.st_ino != 0:
                    inode_key = (dir_st.st_dev, dir_st.st_ino)
                    if inode_key in visited_inodes:
                        return
                    visited_inodes.add(inode_key)
                else:
                    real_key = os.path.normcase(str(current_dir.resolve()))
                    if real_key in visited_dirs_norm:
                        return
                    visited_dirs_norm.add(real_key)
            except OSError:
                return

        try:
            with os.scandir(current_dir) as it:
                dir_entries = list(it)
        except OSError:
            return

        # Sort dir_entries by name for deterministic walk order
        dir_entries.sort(key=lambda d: d.name)

        for d_entry in dir_entries:
            try:
                is_sym = d_entry.is_symlink()
                if is_sym and not space_cfg.follow_symlinks:
                    continue

                child_path = Path(d_entry.path)
                # Use deepest enclosing entry in this space for entry_rel calculation
                effective_entry = self._select_deepest_entry(
                    child_path, entry_abs, all_space_entries
                )

                if d_entry.is_dir(follow_symlinks=space_cfg.follow_symlinks):
                    # Prune excluded directory subtree BEFORE descending
                    if space_cfg.is_dir_excluded_fast(
                        child_path, effective_entry, self._project_root
                    ):
                        continue
                    self._scandir_walk_recursive(
                        current_dir=child_path,
                        entry_abs=effective_entry,
                        all_space_entries=all_space_entries,
                        space_cfg=space_cfg,
                        visited_inodes=visited_inodes,
                        visited_dirs_norm=visited_dirs_norm,
                        dedup_map=dedup_map,
                    )
                elif d_entry.is_file(follow_symlinks=space_cfg.follow_symlinks):
                    if not space_cfg.is_file_matched_fast(
                        child_path, effective_entry, self._project_root
                    ):
                        continue
                    st = d_entry.stat(follow_symlinks=space_cfg.follow_symlinks)
                    self._record_matched_file(
                        file_abs=child_path,
                        entry_abs=effective_entry,
                        space_cfg=space_cfg,
                        st=st,
                        dedup_map=dedup_map,
                    )
            except OSError:
                continue

    @staticmethod
    def _select_deepest_entry(
        target_path: Path, default_entry: Path, all_entries: Sequence[Path]
    ) -> Path:
        if len(all_entries) <= 1:
            return default_entry
        best = default_entry
        best_depth = len(default_entry.parts)
        for cand in all_entries:
            if len(cand.parts) <= best_depth:
                continue
            try:
                rel = target_path.relative_to(cand)
                if not str(rel).startswith(".."):
                    best = cand
                    best_depth = len(cand.parts)
            except ValueError:
                continue
        return best

    def _record_matched_file(
        self,
        *,
        file_abs: Path,
        entry_abs: Path,
        space_cfg: SpaceConfig,
        st: os.stat_result,
        dedup_map: Dict[str, List[Any]],
    ) -> None:
        if space_cfg.follow_symlinks:
            try:
                phys_key = os.path.normcase(os.path.realpath(str(file_abs)))
            except OSError:
                phys_key = os.path.normcase(os.path.abspath(str(file_abs)))
        else:
            phys_key = os.path.normcase(os.path.abspath(str(file_abs)))

        mtime_ns = int(st.st_mtime_ns)
        ctime_ns = int(getattr(st, "st_ctime_ns", mtime_ns))
        size = int(st.st_size)

        existing = dedup_map.get(phys_key)
        if existing is not None:
            matched_list: List[str] = existing[3]
            if space_cfg.qualified_name not in matched_list:
                matched_list.append(space_cfg.qualified_name)
            return

        rel_path = compute_canonical_rel_path(file_abs, entry_abs, self._project_root)
        dedup_map[phys_key] = [
            rel_path,
            file_abs,
            entry_abs,
            [space_cfg.qualified_name],
            size,
            mtime_ns,
            ctime_ns,
        ]


def match_path(
    file_path: Union[str, Path],
    space_query: Optional[str] = None,
    *,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> MatchExplainResult:
    """Convenience atomic primitive for single-path matching and rule explanation."""
    reg = registry or SpaceRegistry(project_root=project_root, yscb_dir=yscb_dir)
    return reg.match_path(file_path, space_query=space_query)


def iter_space_files(
    space_query: Optional[str] = None,
    *,
    pattern: Optional[str] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> List[SpaceFileEntry]:
    """Convenience atomic primitive for zero-redundancy directory-pruned file traversal."""
    reg = registry or SpaceRegistry(project_root=project_root, yscb_dir=yscb_dir)
    return reg.iter_space_files(space_query=space_query, pattern=pattern)
