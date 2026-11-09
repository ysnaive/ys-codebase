"""
SpaceRegistry: Namespace-isolated `<owner>/<name>` loading, `<name>` short-name union addressing,
single-point `match_path` explainability, and zero-redundancy `os.scandir` pruned `iter_space_files`.
"""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union

from core.context import get_runtime_context, get_virtual_cwd
from .exceptions import SpaceCycleError, SpaceError, SpaceNotFoundError
from .schema import (
    HashPolicy,
    RuleItem,
    SpaceConfig,
    resolve_semantic_or_rel_path,
)
from .watcher import notify_space_registered


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


def _parse_qualified_key(
    key: str, default_owner: str = "__unknown__"
) -> Tuple[str, str, str]:
    clean = str(key or "").strip()
    if clean.startswith("/"):
        stripped = clean.lstrip("/")
        if "/" not in stripped and stripped:
            return f"/{stripped}", "", stripped
    clean = clean.strip("/")
    if "/" in clean:
        owner, short = clean.split("/", 1)
        owner = owner.strip() or default_owner
        short = short.strip()
    else:
        owner = default_owner
        short = clean
    return f"{owner}/{short}", owner, short


def _merge_raw_space_dict(
    existing: Dict[str, Any], incoming: Mapping[str, Any]
) -> Dict[str, Any]:
    """
    Merge `incoming` raw space definition into `existing` using rule-level absolute union:
    - `entries`, `compose`, `presets`, `exclude`: deduplicated ordered union.
    - `include`: if either `existing` or `incoming` contains `*`, `**`, or `**/*`, result is `["*"]`;
      otherwise deduplicated union (retaining `existing` if `incoming` omits `include`).
    - Scalar fields (`description`, `hash_policy`, `large_file_threshold_mb`, `follow_symlinks`, `watch`):
      updated when explicitly provided in `incoming`.
    """
    merged: Dict[str, Any] = dict(existing)

    # Merge list fields: entries (including legacy include_entries), compose, presets, exclude
    for field_name in ("entries", "compose", "presets", "exclude"):
        cur_raw = merged.get(field_name, [])
        if field_name == "entries" and not cur_raw and "include_entries" in merged:
            cur_raw = merged.get("include_entries", [])
        cur_list: List[str] = [
            str(x).strip()
            for x in (cur_raw if isinstance(cur_raw, (list, tuple)) else [])
            if str(x).strip()
        ]
        inc_raw = incoming.get(field_name)
        if field_name == "entries" and inc_raw is None and "include_entries" in incoming:
            inc_raw = incoming.get("include_entries")
        if isinstance(inc_raw, (list, tuple)):
            for x in inc_raw:
                s = str(x).strip()
                if s and s not in cur_list:
                    cur_list.append(s)
        merged[field_name] = cur_list

    # Merge `include` with wildcard absorption
    has_existing_inc = "include" in merged and isinstance(merged["include"], (list, tuple))
    cur_inc: List[str] = (
        [str(x).strip() for x in merged["include"] if str(x).strip()]
        if has_existing_inc
        else []
    )
    inc_provided = "include" in incoming and isinstance(incoming["include"], (list, tuple))
    new_inc: List[str] = (
        [str(x).strip() for x in incoming["include"] if str(x).strip()]
        if inc_provided
        else []
    )
    if cur_inc or new_inc:
        combined_inc: List[str] = []
        for pat in (*cur_inc, *new_inc):
            if pat not in combined_inc:
                combined_inc.append(pat)
        if any(pat in ("*", "**", "**/*") for pat in combined_inc):
            merged["include"] = ["*"]
        else:
            merged["include"] = combined_inc
    elif inc_provided:
        merged["include"] = []

    # Scalar fields
    if "description" in incoming and incoming["description"] is not None:
        desc_str = str(incoming["description"]).strip()
        if desc_str or "description" not in merged:
            merged["description"] = desc_str
    for scalar_key in (
        "hash_policy",
        "large_file_threshold_mb",
        "follow_symlinks",
        "watch",
    ):
        if scalar_key in incoming and incoming[scalar_key] is not None:
            merged[scalar_key] = incoming[scalar_key]

    return merged


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
    Atomic registry for `<owner>/<name>` spaces and synthesized `/<name>` short-name union spaces.
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

        self._spaces: Dict[str, SpaceConfig] = {}
        self._spaces_by_short: Dict[str, List[SpaceConfig]] = {}
        self._runtime_spaces: Dict[str, Dict[str, Any]] = {}
        self._raw_spaces_by_owner: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._in_reload_broadcast: bool = False
        self._lock = threading.RLock()

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
                default_proj = Path(os.path.normpath(os.path.abspath(get_virtual_cwd())))

        if default_yscb is None:
            cand = default_proj / "ys_codebase"
            default_yscb = cand if cand.is_dir() else default_proj

        if yscb_dir is not None:
            eff_yscb = Path(os.path.normpath(os.path.abspath(str(yscb_dir))))
            if project_root is not None:
                eff_proj = Path(os.path.normpath(os.path.abspath(str(project_root))))
            elif os.path.normcase(str(eff_yscb)) != os.path.normcase(str(default_yscb)):
                if eff_yscb.name in ("ys_codebase", ".yscb") and (
                    (eff_yscb.parent / "yscb.config.json").is_file()
                    or (eff_yscb.parent / "yscb.py").is_file()
                ):
                    eff_proj = eff_yscb.parent
                else:
                    eff_proj = eff_yscb
            else:
                eff_proj = default_proj
        elif project_root is not None:
            eff_proj = Path(os.path.normpath(os.path.abspath(str(project_root))))
            if os.path.normcase(str(eff_proj)) != os.path.normcase(str(default_proj)):
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
        else:
            eff_proj = default_proj
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

    def reload(self) -> None:
        """
        Reload all space definitions using the four-stage, two-pass compilation pipeline:
        Pass 1: Stage 1 (Module Contributes) -> Stage 2 (Project Config) ->
                Stage 3 (`on_register_file_spaces` Event) -> Stage 4 (Runtime Injection).
        Pass 2: Synthesize `/<short-name>` spaces -> DFS expand `presets`/`!presets` -> Compile `SpaceConfig`.
        """
        with self._lock:
            base_spaces_by_owner = self._discover_raw_definitions()
            self._raw_spaces_by_owner = base_spaces_by_owner

            # Stage 3: Broadcast `on_register_file_spaces` unless in sandbox/explicit mode or re-entering
            if (
                self._explicit_spaces is None
                and self._explicit_presets is None
                and not self._in_reload_broadcast
            ):
                self._in_reload_broadcast = True
                try:
                    from core import events as core_events

                    core_events.broadcast(
                        "on_register_file_spaces",
                        {
                            "registry": self,
                            "project_root": str(self._project_root),
                            "yscb_dir": str(self._yscb_dir),
                        },
                        emit_module="core",
                        search_roots=[str(self._yscb_dir / ".modules")],
                    )
                except Exception:
                    pass
                finally:
                    self._in_reload_broadcast = False

            self._compile_pass_two()

    def _compile_pass_two(self) -> None:
        """
        Execute Pass 2 compilation over `self._raw_spaces_by_owner` merged with `self._runtime_spaces`:
        1. Merge Stage 4 `self._runtime_spaces` via `_merge_raw_space_dict`.
        2. Synthesize `/<short-name>` (`owner=""`) for every short name.
        3. Topologically compile each space (DFS expanding `presets` and `!presets` with cycle detection).
        4. Populate `unresolved_compose` and validate `compose` DAG cycles.
        """
        merged_by_owner: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for owner, owner_dict in self._raw_spaces_by_owner.items():
            merged_by_owner[owner] = {
                s_name: dict(s_val) for s_name, s_val in owner_dict.items()
            }

        # Stage 4: Overlay runtime spaces via rule-level union
        for q_name, rt_raw in self._runtime_spaces.items():
            _, owner, short = _parse_qualified_key(q_name, "__unknown__")
            owner_bucket = merged_by_owner.setdefault(owner, {})
            owner_bucket[short] = _merge_raw_space_dict(
                owner_bucket.get(short, {}), rt_raw
            )

        # Group owners by short_name in deterministic order
        owners_by_short: Dict[str, List[str]] = {}
        all_raw_by_qname: Dict[str, Tuple[str, str, Dict[str, Any]]] = {}
        for owner in _sort_owner_keys(merged_by_owner.keys()):
            owner_spaces = merged_by_owner[owner]
            for short_name in sorted(owner_spaces.keys()):
                s_data = owner_spaces[short_name]
                if not isinstance(s_data, dict):
                    continue
                q_name = f"/{short_name}" if owner == "" else f"{owner}/{short_name}"
                all_raw_by_qname[q_name] = (owner, short_name, s_data)
                if owner != "":
                    owners_by_short.setdefault(short_name, []).append(owner)

        # Cross-share workspace ceiling exclude rules across all `<owner>/workspace` definitions
        ws_owners = owners_by_short.get("workspace", [])
        if ws_owners:
            unified_ws_exclude: List[str] = []
            for ws_o in ws_owners:
                ws_raw = merged_by_owner[ws_o].get("workspace", {})
                for pat in ws_raw.get("exclude", []) or []:
                    s_pat = str(pat).strip()
                    if s_pat and s_pat not in unified_ws_exclude:
                        unified_ws_exclude.append(s_pat)
            if unified_ws_exclude:
                for ws_o in ws_owners:
                    ws_qname = f"{ws_o}/workspace"
                    if ws_qname in all_raw_by_qname:
                        o_val, s_val, d_val = all_raw_by_qname[ws_qname]
                        d_copy = dict(d_val)
                        d_copy["exclude"] = list(unified_ws_exclude)
                        all_raw_by_qname[ws_qname] = (o_val, s_val, d_copy)

        # Synthesize `/<short_name>` raw definitions for every short_name
        for short_name in sorted(owners_by_short.keys()):
            synth_qname = f"/{short_name}"
            owner_list = owners_by_short[short_name]
            compose_members = [f"{o}/{short_name}" for o in owner_list]
            any_watch = any(
                bool(merged_by_owner[o][short_name].get("watch", True))
                for o in owner_list
            )
            synth_exclude: List[str] = []
            if short_name == "workspace" and ws_owners:
                synth_exclude = list(unified_ws_exclude)
            synth_base: Dict[str, Any] = {
                "description": f"Synthesized union space for '{short_name}' across {', '.join(owner_list)}",
                "entries": [],
                "compose": compose_members,
                "presets": [],
                "include": ["*"],
                "exclude": synth_exclude,
                "watch": any_watch,
            }
            if synth_qname in all_raw_by_qname:
                existing_synth = all_raw_by_qname[synth_qname][2]
                synth_base = _merge_raw_space_dict(synth_base, existing_synth)
            all_raw_by_qname[synth_qname] = ("", short_name, synth_base)

        compiled_spaces: Dict[str, SpaceConfig] = {}
        spaces_by_short: Dict[str, List[SpaceConfig]] = {}

        def _resolve_preset_target_qnames(ref_clean: str) -> List[str]:
            if ref_clean.startswith("/"):
                short = ref_clean.lstrip("/")
                return [f"{o}/{short}" for o in owners_by_short.get(short, [])]
            if "/" in ref_clean:
                return [ref_clean] if ref_clean in all_raw_by_qname else []
            return [f"{o}/{ref_clean}" for o in owners_by_short.get(ref_clean, [])]

        def _compile_single_space(
            q_name: str, visiting: Tuple[str, ...]
        ) -> SpaceConfig:
            if q_name in compiled_spaces:
                return compiled_spaces[q_name]
            if q_name in visiting:
                cycle_chain = " -> ".join([*visiting, q_name])
                raise SpaceCycleError(
                    f"Circular space preset reference detected: {cycle_chain}"
                )
            next_visiting = (*visiting, q_name)
            owner, short_name, raw_data = all_raw_by_qname[q_name]
            cfg = self._build_space_config_pass2(
                q_name=q_name,
                owner=owner,
                short_name=short_name,
                raw_data=raw_data,
                visiting=next_visiting,
                resolve_preset_targets=_resolve_preset_target_qnames,
                compile_target=_compile_single_space,
            )
            compiled_spaces[q_name] = cfg
            return cfg

        # Compile owner-qualified spaces in deterministic owner order first, then synthesized spaces
        for owner in _sort_owner_keys(merged_by_owner.keys()):
            if owner == "":
                continue
            for short_name in sorted(merged_by_owner[owner].keys()):
                q_name = f"{owner}/{short_name}"
                if q_name in all_raw_by_qname:
                    cfg = _compile_single_space(q_name, ())
                    spaces_by_short.setdefault(short_name, []).append(cfg)

        for short_name in sorted(owners_by_short.keys()):
            synth_qname = f"/{short_name}"
            if synth_qname in all_raw_by_qname:
                _compile_single_space(synth_qname, ())

        # Reorder self._spaces deterministically: owner spaces first, then `/<short>`
        ordered_spaces: Dict[str, SpaceConfig] = {}
        for owner in _sort_owner_keys(merged_by_owner.keys()):
            if owner == "":
                continue
            for short_name in sorted(merged_by_owner[owner].keys()):
                q_name = f"{owner}/{short_name}"
                if q_name in compiled_spaces:
                    ordered_spaces[q_name] = compiled_spaces[q_name]
        for short_name in sorted(owners_by_short.keys()):
            synth_qname = f"/{short_name}"
            if synth_qname in compiled_spaces:
                ordered_spaces[synth_qname] = compiled_spaces[synth_qname]

        self._spaces = ordered_spaces
        self._spaces_by_short = spaces_by_short
        self._refresh_unresolved_compose()

    def _refresh_unresolved_compose(self) -> None:
        for space_cfg in self._spaces.values():
            unresolved_c: List[str] = []
            for comp_ref in space_cfg.compose:
                clean_ref = str(comp_ref or "").strip()
                target_ref = (
                    clean_ref[1:].strip() if clean_ref.startswith("!") else clean_ref
                )
                if not self._lookup_spaces_non_throwing(target_ref):
                    if comp_ref not in unresolved_c:
                        unresolved_c.append(comp_ref)
            object.__setattr__(space_cfg, "unresolved_compose", tuple(unresolved_c))

    def _discover_raw_definitions(
        self,
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        spaces_by_owner: Dict[str, Dict[str, Dict[str, Any]]] = {}

        if self._explicit_presets is not None or self._explicit_spaces is not None:
            for k, v in (self._explicit_presets or {}).items():
                if not isinstance(v, dict):
                    continue
                _, owner, short = _parse_qualified_key(
                    k, str(v.get("owner", "project"))
                )
                p_dict = dict(v)
                p_dict.setdefault("entries", [])
                owner_bucket = spaces_by_owner.setdefault(owner, {})
                owner_bucket[short] = _merge_raw_space_dict(
                    owner_bucket.get(short, {}), p_dict
                )

            for k, v in (self._explicit_spaces or {}).items():
                if not isinstance(v, dict):
                    continue
                _, owner, short = _parse_qualified_key(
                    k, str(v.get("owner", "project"))
                )
                owner_bucket = spaces_by_owner.setdefault(owner, {})
                owner_bucket[short] = _merge_raw_space_dict(
                    owner_bucket.get(short, {}), dict(v)
                )
            return spaces_by_owner

        # Stage 1: Scan installed modules in yscb_dir/.modules/*/contributes/core.json
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
                        core_json, mod_name, spaces_by_owner
                    )

        # Fallback for core's own contributes/core.json if core is not yet materialized in .modules
        if "core" not in spaces_by_owner:
            core_pkg_root = Path(__file__).resolve().parents[2]
            self_core_json = core_pkg_root / "contributes" / "core.json"
            if self_core_json.is_file():
                self._extract_file_definitions(
                    self_core_json, "core", spaces_by_owner
                )

        # Stage 2: Scan project-level config/core/contribute.json
        proj_contrib = self._yscb_dir / "config" / "core" / "contribute.json"
        if proj_contrib.is_file():
            self._extract_file_definitions(
                proj_contrib, "project", spaces_by_owner
            )

        return spaces_by_owner

    @staticmethod
    def _extract_file_definitions(
        json_path: Path,
        default_owner: str,
        spaces_by_owner: Dict[str, Dict[str, Dict[str, Any]]],
    ) -> None:
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        body = (
            payload.get("core", payload)
            if isinstance(payload.get("core"), dict)
            else payload
        )
        if not isinstance(body, dict):
            return

        # Backward compatibility: legacy `presets` converted into rule-only spaces (`entries: []`)
        raw_p = body.get("presets")
        if isinstance(raw_p, dict):
            for p_key, p_val in raw_p.items():
                if str(p_key).startswith("_") or not isinstance(p_val, dict):
                    continue
                _, owner, short = _parse_qualified_key(p_key, default_owner)
                p_dict = dict(p_val)
                p_dict.setdefault("entries", [])
                owner_bucket = spaces_by_owner.setdefault(owner, {})
                owner_bucket[short] = _merge_raw_space_dict(
                    owner_bucket.get(short, {}), p_dict
                )

        # Backward compatibility: legacy top-level `gitignore` list converted into `<owner>/gitignore` space
        raw_gi = body.get("gitignore")
        if isinstance(raw_gi, list):
            gi_inc: List[str] = []
            gi_exc: List[str] = []
            for item in raw_gi:
                s = str(item or "").strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("!"):
                    neg_body = s[1:].strip()
                    if neg_body and neg_body not in gi_exc:
                        gi_exc.append(neg_body)
                else:
                    if s not in gi_inc:
                        gi_inc.append(s)
            if gi_inc or gi_exc:
                gi_space_dict: Dict[str, Any] = {
                    "entries": ["project://"],
                    "include": gi_inc,
                    "exclude": gi_exc,
                    "watch": False,
                }
                owner_bucket = spaces_by_owner.setdefault(default_owner, {})
                owner_bucket["gitignore"] = _merge_raw_space_dict(
                    owner_bucket.get("gitignore", {}), gi_space_dict
                )

        raw_s = body.get("spaces")
        if isinstance(raw_s, dict):
            for s_key, s_val in raw_s.items():
                if str(s_key).startswith("_") or not isinstance(s_val, dict):
                    continue
                _, owner, short = _parse_qualified_key(s_key, default_owner)
                owner_bucket = spaces_by_owner.setdefault(owner, {})
                owner_bucket[short] = _merge_raw_space_dict(
                    owner_bucket.get(short, {}), dict(s_val)
                )

    def _build_space_config_pass2(
        self,
        *,
        q_name: str,
        owner: str,
        short_name: str,
        raw_data: Mapping[str, Any],
        visiting: Tuple[str, ...],
        resolve_preset_targets: Any,
        compile_target: Any,
    ) -> SpaceConfig:
        raw_entries = raw_data.get("entries", raw_data.get("include_entries", []))
        if not isinstance(raw_entries, (list, tuple)):
            raw_entries = []
        entries_tuple = tuple(str(e) for e in raw_entries if str(e).strip())

        raw_compose = raw_data.get("compose", [])
        if not isinstance(raw_compose, (list, tuple)):
            raw_compose = []
        compose_tuple = tuple(str(c) for c in raw_compose if str(c).strip())

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
        negated_presets_list: List[SpaceConfig] = []
        unresolved: List[str] = []

        # Expand explicit presets (positive rule union and `!` negated preset collection)
        for preset_ref in presets_tuple:
            clean_ref = str(preset_ref or "").strip()
            if not clean_ref:
                continue
            is_negated = clean_ref.startswith("!")
            target_ref = clean_ref[1:].strip() if is_negated else clean_ref
            if target_ref == "@gitignore":
                target_ref = "gitignore"
                is_negated = True

            target_qnames: List[str] = resolve_preset_targets(target_ref)
            if not target_qnames:
                if preset_ref not in unresolved:
                    unresolved.append(preset_ref)
                continue

            for t_qname in target_qnames:
                t_cfg: SpaceConfig = compile_target(t_qname, visiting)
                if is_negated:
                    if all(
                        existing.qualified_name != t_cfg.qualified_name
                        for existing in negated_presets_list
                    ):
                        negated_presets_list.append(t_cfg)
                    for neg_child in t_cfg.negated_presets:
                        if all(
                            existing.qualified_name != neg_child.qualified_name
                            for existing in negated_presets_list
                        ):
                            negated_presets_list.append(neg_child)
                else:
                    p_src = f"preset:{t_cfg.qualified_name}"
                    # Only pull target's effective_include if target had explicit include or positive presets
                    has_explicit_target_inc = bool(t_cfg.include) or any(
                        r.source.startswith("preset:")
                        for r in t_cfg.effective_include
                    )
                    if has_explicit_target_inc:
                        for r_item in t_cfg.effective_include:
                            item = RuleItem(
                                raw_pattern=r_item.raw_pattern, source=p_src
                            )
                            if item not in effective_inc:
                                effective_inc.append(item)
                    for r_item in t_cfg.effective_exclude:
                        item = RuleItem(
                            raw_pattern=r_item.raw_pattern, source=p_src
                        )
                        if item not in effective_exc:
                            effective_exc.append(item)
                    for neg_child in t_cfg.negated_presets:
                        if all(
                            existing.qualified_name != neg_child.qualified_name
                            for existing in negated_presets_list
                        ):
                            negated_presets_list.append(neg_child)

        space_src = f"space:{q_name}"
        for pat in inc_tuple:
            item = RuleItem(raw_pattern=pat, source=space_src)
            if item not in effective_inc:
                effective_inc.append(item)

        # Rule-level absolute union for include: if any rule is `*`/`**`/`**/*`, collapse to `*`
        if any(r.raw_pattern in ("*", "**", "**/*") for r in effective_inc):
            first_wildcard_src = next(
                (
                    r.source
                    for r in effective_inc
                    if r.raw_pattern in ("*", "**", "**/*")
                ),
                space_src,
            )
            effective_inc = [RuleItem(raw_pattern="*", source=first_wildcard_src)]
        elif not effective_inc:
            effective_inc.append(RuleItem(raw_pattern="*", source=space_src))

        for pat in exc_tuple:
            item = RuleItem(raw_pattern=pat, source=space_src)
            if item not in effective_exc:
                effective_exc.append(item)

        # Check URI warnings on entries
        uri_warnings: List[str] = []
        for entry_str in entries_tuple:
            if "://" in entry_str:
                res = resolve_semantic_or_rel_path(
                    entry_str,
                    self._project_root,
                    self._yscb_dir,
                    owner_module=owner or None,
                )
                if res is None:
                    uri_warnings.append(f"Unresolvable entry URI: '{entry_str}'")

        default_watch = False if short_name == "gitignore" else True
        eff_watch = bool(raw_data.get("watch", default_watch))

        return SpaceConfig(
            qualified_name=q_name,
            owner=owner,
            short_name=short_name,
            description=str(raw_data.get("description", "") or ""),
            entries=entries_tuple,
            compose=compose_tuple,
            presets=presets_tuple,
            include=inc_tuple,
            exclude=exc_tuple,
            hash_policy=raw_data.get("hash_policy", HashPolicy.ADAPTIVE),
            large_file_threshold_mb=raw_data.get("large_file_threshold_mb", 10),
            follow_symlinks=bool(raw_data.get("follow_symlinks", False)),
            watch=eff_watch,
            effective_include=tuple(effective_inc),
            effective_exclude=tuple(effective_exc),
            negated_presets=tuple(negated_presets_list),
            unresolved_presets=tuple(unresolved),
            uri_warnings=tuple(uri_warnings),
            _project_root=self._project_root,
            _yscb_dir=self._yscb_dir,
        )

    def _lookup_spaces_non_throwing(self, query: str) -> List[SpaceConfig]:
        q = str(query or "").strip()
        if not q:
            return []
        if q.startswith("/"):
            found = self._spaces.get(q)
            return [found] if found is not None else []
        if "/" in q:
            found = self._spaces.get(q)
            return [found] if found is not None else []
        synth = self._spaces.get(f"/{q}")
        if synth is not None:
            return [synth]
        return list(self._spaces_by_short.get(q, []))

    def _split_compose_children(
        self, space_cfg: SpaceConfig, visiting: Tuple[str, ...]
    ) -> Tuple[List[SpaceConfig], List[SpaceConfig]]:
        """
        Resolve `space_cfg.compose` into `(positive_children, negative_children)` while detecting cycles.
        """
        if space_cfg.qualified_name in visiting:
            cycle_chain = " -> ".join([*visiting, space_cfg.qualified_name])
            raise SpaceCycleError(
                f"Circular space compose reference detected: {cycle_chain}"
            )
        next_visiting = (*visiting, space_cfg.qualified_name)
        pos_children: List[SpaceConfig] = []
        neg_children: List[SpaceConfig] = []
        for comp_ref in space_cfg.compose:
            clean_ref = str(comp_ref or "").strip()
            if not clean_ref:
                continue
            is_neg = clean_ref.startswith("!")
            target_ref = clean_ref[1:].strip() if is_neg else clean_ref
            matched_children = self._lookup_spaces_non_throwing(target_ref)
            for child_cfg in matched_children:
                if child_cfg.qualified_name in next_visiting:
                    cycle_chain = " -> ".join(
                        [*next_visiting, child_cfg.qualified_name]
                    )
                    raise SpaceCycleError(
                        f"Circular space compose reference detected: {cycle_chain}"
                    )
                target_bucket = neg_children if is_neg else pos_children
                if child_cfg not in target_bucket:
                    target_bucket.append(child_cfg)
        return pos_children, neg_children

    def list_spaces(
        self,
        owner: Optional[str] = None,
        *,
        include_synthetic: bool = True,
    ) -> List[SpaceConfig]:
        """List all registered SpaceConfig instances in deterministic order."""
        with self._lock:
            spaces = list(self._spaces.values())
            if not include_synthetic:
                spaces = [s for s in spaces if s.owner != ""]
            if owner is not None:
                return [s for s in spaces if s.owner == owner]
            return spaces

    def resolve_spaces(self, query: Optional[str] = None) -> List[SpaceConfig]:
        """
        Resolve space query:
        - `None` or `""` -> `[self._spaces["/workspace"]]` if present, else non-gitignore owner spaces with entries/compose
        - `*` -> all watched owner spaces (excluding `gitignore` and rule-only spaces)
        - `<owner>/<space>` -> `[self._spaces["<owner>/<space>"]]`
        - `<space>` or `/<space>` -> `[self._spaces["/<space>"]]`
        Raises SpaceNotFoundError if no space matches.
        """
        with self._lock:
            q = "" if query is None else str(query).strip()
            if q == "":
                ws_cfg = self._spaces.get("/workspace")
                if ws_cfg is not None:
                    return [ws_cfg]
                return [
                    s
                    for s in self._spaces.values()
                    if s.owner != ""
                    and s.short_name != "gitignore"
                    and (s.entries or s.compose)
                ]

            if q in ("*", "__all__"):
                return [
                    s
                    for s in self._spaces.values()
                    if s.owner != ""
                    and s.watch
                    and s.short_name != "gitignore"
                    and (s.entries or s.compose)
                ]

            if q.startswith("/"):
                found = self._spaces.get(q)
                if found is None:
                    available = sorted(self._spaces.keys())
                    raise SpaceNotFoundError(
                        f"Space '{q}' is not registered. Available spaces: {available}"
                    )
                return [found]

            if "/" in q:
                found = self._spaces.get(q)
                if found is None:
                    available = sorted(self._spaces.keys())
                    raise SpaceNotFoundError(
                        f"Space '{q}' is not registered. Available spaces: {available}"
                    )
                return [found]

            synth = self._spaces.get(f"/{q}")
            if synth is not None:
                return [synth]

            matched = list(self._spaces_by_short.get(q, []))
            if not matched:
                available = sorted(
                    set(self._spaces.keys()) | set(self._spaces_by_short.keys())
                )
                raise SpaceNotFoundError(
                    f"Space '{q}' is not registered. Available spaces: {available}"
                )
            return matched

    def get_spaces(self, query: Optional[str] = None) -> List[SpaceConfig]:
        """Alias for `resolve_spaces(query)`."""
        return self.resolve_spaces(query)

    def register_space(
        self,
        name: str,
        config: Union[SpaceConfig, Mapping[str, Any]],
        *,
        watch: Optional[bool] = None,
    ) -> SpaceConfig:
        """
        Register or merge a runtime space definition (Stage 4 / Stage 3 hook injection).
        Uses `<owner>/<name>` if `name` contains `/`, otherwise defaults to `__unknown__/<name>`.
        """
        with self._lock:
            q_name, owner, short_name = _parse_qualified_key(name, "__unknown__")
            if not short_name:
                raise SpaceError("Space name must not be empty.")
            if isinstance(config, SpaceConfig):
                raw_dict: Dict[str, Any] = {
                    "description": config.description,
                    "entries": list(config.entries),
                    "compose": list(config.compose),
                    "presets": list(config.presets),
                    "include": list(config.include),
                    "exclude": list(config.exclude),
                    "hash_policy": config.hash_policy,
                    "large_file_threshold_mb": config.large_file_threshold_mb,
                    "follow_symlinks": config.follow_symlinks,
                    "watch": bool(watch) if watch is not None else bool(config.watch),
                }
            elif isinstance(config, Mapping):
                raw_dict = dict(config)
                if watch is not None:
                    raw_dict["watch"] = bool(watch)
            else:
                raise SpaceError(
                    f"Invalid space config type '{type(config).__name__}'."
                )

            existing = self._runtime_spaces.get(q_name, {})
            self._runtime_spaces[q_name] = _merge_raw_space_dict(existing, raw_dict)

            if self._in_reload_broadcast:
                default_w = False if short_name == "gitignore" else True
                eff_w = bool(self._runtime_spaces[q_name].get("watch", default_w))
                return SpaceConfig(
                    qualified_name=q_name,
                    owner=owner,
                    short_name=short_name,
                    description=str(self._runtime_spaces[q_name].get("description", "") or ""),
                    entries=tuple(self._runtime_spaces[q_name].get("entries", [])),
                    compose=tuple(self._runtime_spaces[q_name].get("compose", [])),
                    presets=tuple(self._runtime_spaces[q_name].get("presets", [])),
                    include=tuple(self._runtime_spaces[q_name].get("include", [])),
                    exclude=tuple(self._runtime_spaces[q_name].get("exclude", [])),
                    watch=eff_w,
                    _project_root=self._project_root,
                    _yscb_dir=self._yscb_dir,
                )

            self._compile_pass_two()
            space_cfg = self._spaces[q_name]

        if space_cfg.watch:
            notify_space_registered(q_name)
        return space_cfg

    def unregister_space(self, name: str) -> bool:
        """
        Remove a runtime-injected space definition by `<owner>/<name>` or `<name>` and recompile.
        Returns True if a runtime space was removed.
        """
        with self._lock:
            q_name, _owner, _short = _parse_qualified_key(name, "__unknown__")
            removed = False
            if q_name in self._runtime_spaces:
                del self._runtime_spaces[q_name]
                removed = True
            elif name in self._runtime_spaces:
                del self._runtime_spaces[name]
                removed = True
            if removed and not self._in_reload_broadcast:
                self._compile_pass_two()
            return removed

    def define_ephemeral_space(
        self,
        name: str,
        config: Union[SpaceConfig, Mapping[str, Any]],
        *,
        watch: Optional[bool] = None,
    ) -> SpaceConfig:
        """Backward-compatible alias for `register_space`."""
        return self.register_space(name, config, watch=watch)

    def _collect_participating_spaces(
        self,
        space_query: Optional[str] = None,
    ) -> List[SpaceConfig]:
        """Collect all spaces participating positively in `space_query` (own + positive `compose`)."""
        roots = self.resolve_spaces(space_query)
        collected: List[SpaceConfig] = []

        def _visit(cfg: SpaceConfig, visiting: Tuple[str, ...]) -> None:
            pos_children, _neg_children = self._split_compose_children(cfg, visiting)
            if cfg not in collected:
                collected.append(cfg)
            next_visiting = (*visiting, cfg.qualified_name)
            for child in pos_children:
                _visit(child, next_visiting)

        for r in roots:
            _visit(r, ())
        return collected

    def _collect_all_dependency_spaces(
        self,
        space_query: Optional[str] = None,
    ) -> List[SpaceConfig]:
        """
        Collect all spaces affecting `space_query` for `compute_config_hash`:
        positive `compose`, negative `!compose`, positive `presets`, and negative `!presets`.
        """
        roots = self.resolve_spaces(space_query)
        collected: List[SpaceConfig] = []
        visited_qnames: Set[str] = set()

        def _visit(cfg: SpaceConfig, compose_visiting: Tuple[str, ...]) -> None:
            pos_children, neg_children = self._split_compose_children(
                cfg, compose_visiting
            )
            if cfg.qualified_name not in visited_qnames:
                visited_qnames.add(cfg.qualified_name)
                collected.append(cfg)
            next_visiting = (*compose_visiting, cfg.qualified_name)
            for child in (*pos_children, *neg_children):
                _visit(child, next_visiting)
            for neg_p in cfg.negated_presets:
                if neg_p.qualified_name not in visited_qnames:
                    _visit(neg_p, ())
            for p_ref in cfg.presets:
                clean_ref = str(p_ref or "").strip()
                target_ref = (
                    clean_ref[1:].strip() if clean_ref.startswith("!") else clean_ref
                )
                for p_target in self._lookup_spaces_non_throwing(target_ref):
                    if p_target.qualified_name not in visited_qnames:
                        _visit(p_target, ())

        for r in roots:
            _visit(r, ())
        return collected

    def compute_config_hash(self, space_query: Optional[str] = None) -> str:
        """
        Compute a deterministic 16-byte Blake2b hex digest over all participating spaces,
        their positive/negative `compose` children, and positive/negative `presets` dependencies.
        """
        dependencies = self._collect_all_dependency_spaces(space_query)
        hasher = hashlib.blake2b(digest_size=16)
        for s_cfg in sorted(dependencies, key=lambda s: s.qualified_name):
            payload = {
                "qualified_name": s_cfg.qualified_name,
                "entries": list(s_cfg.entries),
                "compose": list(s_cfg.compose),
                "presets": list(s_cfg.presets),
                "effective_include": [
                    (r.raw_pattern, r.source) for r in s_cfg.effective_include
                ],
                "effective_exclude": [
                    (r.raw_pattern, r.source) for r in s_cfg.effective_exclude
                ],
                "negated_presets": [
                    np.qualified_name for np in s_cfg.negated_presets
                ],
                "hash_policy": s_cfg.hash_policy.value,
                "large_file_threshold_mb": s_cfg.large_file_threshold_mb,
                "follow_symlinks": s_cfg.follow_symlinks,
                "watch": s_cfg.watch,
            }
            hasher.update(json.dumps(payload, sort_keys=True).encode("utf-8"))
        return hasher.hexdigest()

    def collect_all_entry_paths(self, space_query: Optional[str] = None) -> List[Path]:
        """Return all existing or declared resolved `entry_path`s across participating and composed spaces."""
        participating = self._collect_participating_spaces(space_query)
        entry_paths: List[Path] = []
        seen: Set[str] = set()
        for s_cfg in participating:
            for _raw_e, res_p, _exists in s_cfg.resolve_entries(self._project_root):
                if res_p is None:
                    continue
                norm_k = os.path.normcase(str(res_p))
                if norm_k not in seen:
                    seen.add(norm_k)
                    entry_paths.append(res_p)
        return entry_paths

    def resolve_file_path(
        self,
        rel_path: str,
        space_query: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Resolve a canonical relative path back to a physical `Path` on disk if it exists,
        respects symlink boundaries, and matches the queried space(s).
        Returns None if not found or excluded.
        """
        clean_rel = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
        if not clean_rel:
            return None

        participating = self._collect_participating_spaces(space_query)
        allow_symlinks = any(s.follow_symlinks for s in participating)

        candidates: List[Tuple[Path, Path]] = []
        proj_cand = Path(os.path.normpath(str(self._project_root / clean_rel)))
        candidates.append((proj_cand, self._project_root))

        for entry_p in self.collect_all_entry_paths(space_query):
            if entry_p.is_file():
                if clean_rel == entry_p.name or clean_rel.endswith(f"/{entry_p.name}"):
                    candidates.append((entry_p, entry_p))
                continue
            cand_direct = Path(os.path.normpath(str(entry_p / clean_rel)))
            candidates.append((cand_direct, entry_p))
            if entry_p.name and clean_rel.startswith(f"{entry_p.name}/"):
                stripped = clean_rel[len(entry_p.name) + 1 :]
                if stripped:
                    cand_stripped = Path(os.path.normpath(str(entry_p / stripped)))
                    candidates.append((cand_stripped, entry_p))

        seen_cands: Set[str] = set()
        for cand_abs, base_dir in candidates:
            norm_k = os.path.normcase(str(cand_abs))
            if norm_k in seen_cands:
                continue
            seen_cands.add(norm_k)
            try:
                if not allow_symlinks:
                    if cand_abs.is_symlink() or _has_intervening_symlink(cand_abs, base_dir):
                        continue
                if not cand_abs.is_file():
                    continue
            except OSError:
                continue

            match_res = self.match_path(cand_abs, space_query=space_query)
            if match_res.matched:
                return cand_abs

        return None

    def match_path(
        self,
        file_path: Union[str, Path],
        space_query: Optional[str] = None,
        *,
        space: Optional[str] = None,
        is_dir: Optional[bool] = None,
    ) -> MatchExplainResult:
        """
        Single-point three-coordinate path judgment and explanation without full disk scanning.
        Evaluates whether `file_path` belongs to the queried space(s) and explains the exact
        entry, include rule, or exclude rule responsible.
        """
        eff_query = space if space is not None else space_query
        target_spaces = self.resolve_spaces(eff_query)
        raw_str = (
            file_path.as_posix()
            if isinstance(file_path, Path)
            else str(file_path).strip()
        )

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
                resolved_target = Path(
                    os.path.normpath(str(self._project_root / p))
                )

        if is_dir is None:
            try:
                eff_is_dir = resolved_target.is_dir()
            except OSError:
                eff_is_dir = raw_str.endswith(("/", "\\"))
        else:
            eff_is_dir = bool(is_dir)

        matched_space_names: List[str] = []
        details: List[SpaceMatchDetail] = []

        for space_cfg in target_spaces:
            if space_cfg.owner == "" and not space_cfg.entries and space_cfg.compose:
                pos_c, neg_c = self._split_compose_children(space_cfg, ())
                if not neg_c:
                    for child_cfg in pos_c:
                        child_detail = self._evaluate_single_space_match(
                            child_cfg, resolved_target, is_dir=eff_is_dir
                        )
                        details.append(child_detail)
                        if (
                            child_detail.matched
                            and child_cfg.qualified_name not in matched_space_names
                        ):
                            matched_space_names.append(child_cfg.qualified_name)
                    continue
            detail = self._evaluate_single_space_match(
                space_cfg, resolved_target, is_dir=eff_is_dir
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
        visiting: Tuple[str, ...] = (),
    ) -> SpaceMatchDetail:
        detail, _entry_p = self._evaluate_single_space_match_with_entry(
            space_cfg, target_abs, is_dir=is_dir, visiting=visiting
        )
        return detail

    def _evaluate_single_space_match_with_entry(
        self,
        space_cfg: SpaceConfig,
        target_abs: Path,
        *,
        is_dir: bool,
        visiting: Tuple[str, ...] = (),
    ) -> Tuple[SpaceMatchDetail, Optional[Path]]:
        # Validate compose DAG cycle upfront and split into positive and negative children
        pos_children, neg_children = self._split_compose_children(
            space_cfg, visiting
        )
        next_visiting = (*visiting, space_cfg.qualified_name)

        # Evaluate negative `!compose` children first: if matched by any negative child, exclude
        for neg_child in neg_children:
            neg_detail, _neg_entry = self._evaluate_single_space_match_with_entry(
                neg_child, target_abs, is_dir=is_dir, visiting=next_visiting
            )
            if neg_detail.matched:
                return (
                    SpaceMatchDetail(
                        qualified_space=space_cfg.qualified_name,
                        matched=False,
                        reason="excluded",
                        matched_entry=neg_detail.matched_entry,
                        exclude_rule=f"!{neg_child.qualified_name}",
                        exclude_source=f"compose:!{neg_child.qualified_name}",
                    ),
                    None,
                )

        try:
            if not space_cfg.follow_symlinks and target_abs.is_symlink():
                return (
                    SpaceMatchDetail(
                        qualified_space=space_cfg.qualified_name,
                        matched=False,
                        reason="symlink_not_followed",
                    ),
                    None,
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
                    if t_real == e_real or not str(
                        t_real.relative_to(e_real)
                    ).startswith(".."):
                        candidate_entries.append((raw_entry, e_real))
                except (OSError, ValueError):
                    pass

        # Sort candidate entries by deepest (most specific) path first
        candidate_entries.sort(key=lambda item: len(item[1].parts), reverse=True)

        last_detail: Optional[SpaceMatchDetail] = None
        for raw_entry, entry_path in candidate_entries:
            matched, inc_rule, exc_rule = space_cfg.match_file(
                target_abs, entry_path, self._project_root, is_dir=is_dir
            )
            if matched:
                return (
                    SpaceMatchDetail(
                        qualified_space=space_cfg.qualified_name,
                        matched=True,
                        reason="included",
                        matched_entry=raw_entry,
                        include_rule=inc_rule.raw_pattern if inc_rule else "*",
                        include_source=(
                            inc_rule.source
                            if inc_rule
                            else f"space:{space_cfg.qualified_name}"
                        ),
                    ),
                    entry_path,
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

        # Evaluate positive composed child spaces (absolute union without parent secondary filter)
        for child_cfg in pos_children:
            child_detail, child_entry_path = (
                self._evaluate_single_space_match_with_entry(
                    child_cfg, target_abs, is_dir=is_dir, visiting=next_visiting
                )
            )
            comp_entry_tag = f"compose:{child_cfg.qualified_name}"
            if child_detail.matched_entry:
                comp_entry_tag = f"{comp_entry_tag} ({child_detail.matched_entry})"

            if child_detail.matched and child_entry_path is not None:
                return (
                    SpaceMatchDetail(
                        qualified_space=space_cfg.qualified_name,
                        matched=True,
                        reason="included",
                        matched_entry=comp_entry_tag,
                        include_rule=child_detail.include_rule or "*",
                        include_source=(
                            child_detail.include_source
                            or f"compose:{child_cfg.qualified_name}"
                        ),
                    ),
                    child_entry_path,
                )
            if last_detail is None and child_detail.reason != "outside_entries":
                last_detail = SpaceMatchDetail(
                    qualified_space=space_cfg.qualified_name,
                    matched=False,
                    reason=child_detail.reason,
                    matched_entry=comp_entry_tag,
                    exclude_rule=child_detail.exclude_rule,
                    exclude_source=child_detail.exclude_source,
                )

        if last_detail is not None:
            return last_detail, None

        return (
            SpaceMatchDetail(
                qualified_space=space_cfg.qualified_name,
                matched=False,
                reason="outside_entries",
            ),
            None,
        )

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
        visiting: Tuple[str, ...] = (),
    ) -> None:
        pos_children, neg_children = self._split_compose_children(
            space_cfg, visiting
        )
        next_visiting = (*visiting, space_cfg.qualified_name)

        own_map: Dict[str, List[Any]] = {}
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
                st = (
                    entry_path.stat()
                    if space_cfg.follow_symlinks
                    else entry_path.lstat()
                )
            except OSError:
                continue

            if entry_path.is_file():
                # Single-file entry
                if space_cfg.is_file_matched_fast(
                    entry_path, entry_path, self._project_root
                ):
                    self._record_matched_file(
                        file_abs=entry_path,
                        entry_abs=entry_path,
                        space_cfg=space_cfg,
                        st=st,
                        dedup_map=own_map,
                    )
            elif entry_path.is_dir():
                if space_cfg.is_dir_excluded_fast(
                    entry_path, entry_path, self._project_root
                ):
                    continue
                self._scandir_walk_recursive(
                    current_dir=entry_path,
                    entry_abs=entry_path,
                    all_space_entries=valid_entries,
                    space_cfg=space_cfg,
                    visited_inodes=visited_inodes,
                    visited_dirs_norm=visited_dirs_norm,
                    dedup_map=own_map,
                )

        # Evaluate positive composed child spaces (absolute union without parent secondary filter)
        if pos_children:
            composed_map: Dict[str, List[Any]] = {}
            for child_cfg in pos_children:
                self._walk_single_space(
                    child_cfg, composed_map, visiting=next_visiting
                )

            own_rel_index: Dict[str, List[Any]] = {
                item[0]: item for item in own_map.values()
            }
            for phys_key, c_item in composed_map.items():
                (
                    c_rel,
                    c_abs,
                    c_entry_abs,
                    c_matched_spaces,
                    c_size,
                    c_mtime,
                    c_ctime,
                ) = c_item
                existing_own = own_map.get(phys_key) or own_rel_index.get(c_rel)
                if existing_own is not None:
                    own_matched: List[str] = existing_own[3]
                    for m_sp in c_matched_spaces:
                        if m_sp not in own_matched:
                            own_matched.append(m_sp)
                else:
                    if space_cfg.owner == "":
                        merged_spaces = list(c_matched_spaces)
                    else:
                        merged_spaces = [space_cfg.qualified_name]
                        for m_sp in c_matched_spaces:
                            if m_sp not in merged_spaces:
                                merged_spaces.append(m_sp)
                    new_item = [
                        c_rel,
                        c_abs,
                        c_entry_abs,
                        merged_spaces,
                        c_size,
                        c_mtime,
                        c_ctime,
                    ]
                    own_map[phys_key] = new_item
                    own_rel_index[c_rel] = new_item

        # Apply negative `!compose` set difference if any negative children are declared
        if neg_children and own_map:
            excluded_phys: List[str] = []
            for phys_key, item in own_map.items():
                cand_abs: Path = item[1]
                if any(
                    self._evaluate_single_space_match_with_entry(
                        neg_child,
                        cand_abs,
                        is_dir=False,
                        visiting=next_visiting,
                    )[0].matched
                    for neg_child in neg_children
                ):
                    excluded_phys.append(phys_key)
            for phys_key in excluded_phys:
                own_map.pop(phys_key, None)

        # Merge own_map into caller's dedup_map (U_own takes priority over U_compose on rel_path collision)
        rel_path_index: Dict[str, List[Any]] = {
            item[0]: item for item in dedup_map.values()
        }
        for phys_key, item in own_map.items():
            existing = dedup_map.get(phys_key)
            if existing is not None:
                matched_list: List[str] = existing[3]
                for m_sp in item[3]:
                    if m_sp not in matched_list:
                        matched_list.append(m_sp)
                continue
            existing_rel = rel_path_index.get(item[0])
            if existing_rel is not None:
                matched_list = existing_rel[3]
                for m_sp in item[3]:
                    if m_sp not in matched_list:
                        matched_list.append(m_sp)
                continue
            dedup_map[phys_key] = item
            rel_path_index[item[0]] = item

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


def get_default_registry(
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> SpaceRegistry:
    """
    Return the process-level shared SpaceRegistry for `(project_root, yscb_dir)`.
    Ensures runtime ephemeral spaces (`define_ephemeral_space`) registered via top-level
    SDK calls are visible to subsequent queries and the in-process Watcher.
    """
    eff_proj, eff_yscb = SpaceRegistry._resolve_roots(project_root, yscb_dir)
    key = (
        os.path.normcase(str(eff_proj)),
        os.path.normcase(str(eff_yscb)),
    )
    ctx = get_runtime_context()
    with ctx.space_registries_lock:
        reg = ctx.space_default_registries.get(key)
        if reg is None:
            reg = SpaceRegistry(project_root=eff_proj, yscb_dir=eff_yscb)
            ctx.space_default_registries[key] = reg
        return reg


def reset_default_registry() -> None:
    """Clear all cached process-level default SpaceRegistry instances."""
    ctx = get_runtime_context()
    with ctx.space_registries_lock:
        ctx.space_default_registries.clear()


def match_path(
    file_path: Union[str, Path],
    space_query: Optional[str] = None,
    *,
    space: Optional[str] = None,
    is_dir: Optional[bool] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> MatchExplainResult:
    """Convenience atomic primitive for single-path matching and rule explanation."""
    reg = registry or get_default_registry(project_root=project_root, yscb_dir=yscb_dir)
    return reg.match_path(
        file_path, space_query=space_query, space=space, is_dir=is_dir
    )


def iter_space_files(
    space_query: Optional[str] = None,
    *,
    pattern: Optional[str] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> List[SpaceFileEntry]:
    """Convenience atomic primitive for zero-redundancy directory-pruned file traversal."""
    reg = registry or get_default_registry(project_root=project_root, yscb_dir=yscb_dir)
    return reg.iter_space_files(space_query=space_query, pattern=pattern)


def resolve_file_path(
    rel_path: str,
    space_query: Optional[str] = None,
    *,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> Optional[Path]:
    """Convenience primitive for resolving a canonical relative path to a physical disk Path."""
    reg = registry or get_default_registry(project_root=project_root, yscb_dir=yscb_dir)
    return reg.resolve_file_path(rel_path, space_query=space_query)


def register_space(
    name: str,
    config: Union[SpaceConfig, Mapping[str, Any]],
    *,
    watch: Optional[bool] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> SpaceConfig:
    """Convenience primitive for registering or merging a runtime space (`watch=True` by default)."""
    reg = registry or get_default_registry(project_root=project_root, yscb_dir=yscb_dir)
    return reg.register_space(name, config, watch=watch)


def unregister_space(
    name: str,
    *,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> bool:
    """Convenience primitive for removing a runtime-registered space."""
    reg = registry or get_default_registry(project_root=project_root, yscb_dir=yscb_dir)
    return reg.unregister_space(name)


def define_ephemeral_space(
    name: str,
    config: Union[SpaceConfig, Mapping[str, Any]],
    *,
    watch: Optional[bool] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> SpaceConfig:
    """Backward-compatible alias for `register_space`."""
    return register_space(
        name,
        config,
        watch=watch,
        registry=registry,
        project_root=project_root,
        yscb_dir=yscb_dir,
    )


def __getattr__(name: str) -> Any:
    """PEP 562 backward-compatible attribute delegation to active `RuntimeContext`."""
    ctx = get_runtime_context()
    if name == "_DEFAULT_REGISTRIES":
        return ctx.space_default_registries
    if name == "_DEFAULT_REGISTRIES_LOCK":
        return ctx.space_registries_lock
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
