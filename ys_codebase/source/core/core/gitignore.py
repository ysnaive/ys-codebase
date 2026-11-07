"""
YS-Codebase Unified Gitignore Engine (`core.gitignore`).
100% Python Standard Library, Zero Third-Party Dependency.
Consolidates static `contributes` (`gitignore`) and dynamic SDK registrations into a single
root `project://.gitignore` managed block grouped by `# [<module>]`, while seamlessly
migrating legacy blocks and cleaning up obsolete nested `.gitignore` files.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from core import events, uri, vfs
from core.context import ExecutionContext

GITIGNORE_BEGIN_MARKER = "# === YSCB MANAGED GITIGNORE BEGIN ==="
GITIGNORE_END_MARKER = "# === YSCB MANAGED GITIGNORE END ==="

LEGACY_INTERNAL_BEGIN = "# === YSCB INTERNAL IGNORE BEGIN ==="
LEGACY_INTERNAL_END = "# === YSCB INTERNAL IGNORE END ==="
LEGACY_AW_BEGIN = "# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ==="
LEGACY_AW_END = "# === YSCB AGENTS_WORKFLOW IGNORE END ==="

DYNAMIC_CACHE_URI = "storage.local://core/gitignore_dynamic.json"

LEGACY_UNANCHORED_LINES: Set[str] = {
    "# YS-Codebase Autonomous Internal Ignore Rules",
    "/.modules/",
    "/.build/",
    "/.mirror/",
    "/.temp/",
    "/.snapshots/",
    "/.cache/",
    "/.config.local/",
    "/.storage.local/",
    "/.venv/",
    "*.local.json",
    "__pycache__/",
    "*.pyc",
    "yscb.py.bak",
    "*.bak",
}

# In-memory overlay for custom/sandboxed proj_root invocations:
# norm_proj_root -> {module_name: [raw_patterns]}
_CUSTOM_ROOT_DYNAMIC_STORE: Dict[str, Dict[str, List[str]]] = {}


def _validate_module_name(module: str) -> str:
    """Validates that the caller provided a non-empty string module identifier."""
    if not isinstance(module, str) or not module.strip():
        raise ValueError("module name must be a non-empty string")
    return module.strip()


def _resolve_roots(
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> Tuple[str, str, bool]:
    """
    Resolves `(proj_root_abs, yscb_root_abs, is_custom_root)`.
    Determines whether `proj_root` is an isolated test/custom directory vs the active workspace.
    """
    default_proj = ""
    default_yscb = ""
    try:
        default_proj = os.path.abspath(uri.resolve("project://", interactive=False))
    except Exception:
        try:
            host_d, _ = uri._get_host_config()
            default_proj = os.path.abspath(host_d)
        except Exception:
            default_proj = os.path.abspath(os.getcwd())

    try:
        default_yscb = os.path.abspath(uri.resolve("yscb://", interactive=False))
    except Exception:
        try:
            default_yscb = os.path.abspath(uri.resolve_yscb_root())
        except Exception:
            default_yscb = default_proj

    eff_proj = os.path.abspath(proj_root) if proj_root else default_proj
    if yscb_root:
        eff_yscb = os.path.abspath(yscb_root)
    elif proj_root and os.path.normcase(os.path.realpath(eff_proj)) != os.path.normcase(os.path.realpath(default_proj)):
        cand_yscb = os.path.join(eff_proj, "ys_codebase")
        cand_dot_yscb = os.path.join(eff_proj, ".yscb")
        if os.path.isdir(cand_yscb):
            eff_yscb = cand_yscb
        elif os.path.isdir(cand_dot_yscb):
            eff_yscb = cand_dot_yscb
        else:
            eff_yscb = eff_proj
    else:
        eff_yscb = default_yscb

    is_custom = bool(
        proj_root and os.path.normcase(os.path.realpath(eff_proj)) != os.path.normcase(os.path.realpath(default_proj))
    )
    return eff_proj, eff_yscb, is_custom


def normalize_pattern(
    raw_pattern: str,
    proj_root: str,
    yscb_root: Optional[str] = None,
) -> Optional[str]:
    """
    Normalizes a raw gitignore rule or semantic URI (e.g. `yscb://.venv/`, `project://.vscode/schemas/`)
    into a standard gitignore pattern anchored relative to `proj_root`.
    """
    if not isinstance(raw_pattern, str):
        return None
    pat = raw_pattern.strip()
    if not pat or pat.startswith("#"):
        return None

    is_negated = pat.startswith("!")
    core_pat = pat[1:].strip() if is_negated else pat
    if not core_pat:
        return None

    trailing_slash = core_pat.endswith("/") or core_pat.endswith("\\")

    if "://" in core_pat:
        scheme, rest = core_pat.split("://", 1)
        scheme_lower = scheme.strip().lower()
        rest_clean = rest.strip().lstrip("/\\").replace("\\", "/")

        eff_proj = os.path.realpath(os.path.abspath(proj_root))
        eff_yscb = os.path.realpath(os.path.abspath(yscb_root)) if yscb_root else eff_proj

        if scheme_lower in ("project", "yscb.host"):
            target_abs = os.path.join(eff_proj, rest_clean) if rest_clean else eff_proj
        elif scheme_lower == "yscb":
            target_abs = os.path.join(eff_yscb, rest_clean) if rest_clean else eff_yscb
        elif scheme_lower in ("config", "config.local", "storage", "storage.local", "cache", "module", "snapshot"):
            sub_map = {
                "config": "config",
                "config.local": ".config.local",
                "storage": "storage",
                "storage.local": ".storage.local",
                "cache": ".cache",
                "module": ".modules",
                "snapshot": ".snapshots",
            }
            base_sub = os.path.join(eff_yscb, sub_map[scheme_lower])
            target_abs = os.path.join(base_sub, rest_clean) if rest_clean else base_sub
        else:
            try:
                target_abs = uri.resolve(core_pat, interactive=False)
            except Exception:
                return None

        try:
            rel = os.path.relpath(os.path.realpath(target_abs), eff_proj).replace("\\", "/")
        except ValueError:
            return None

        if rel.startswith("../") or rel == "..":
            return None

        if rel == ".":
            return None

        normalized = f"/{rel.strip('/')}"
        if trailing_slash and not normalized.endswith("/"):
            normalized += "/"
        return f"!{normalized}" if is_negated else normalized

    clean_glob = core_pat.replace("\\", "/")
    return f"!{clean_glob}" if is_negated else clean_glob


def _migrate_legacy_dynamic_cache_if_needed(is_custom_root: bool) -> Dict[str, List[str]]:
    """
    Reads and removes legacy `storage.local://core/gitignore_dynamic.json` if present,
    migrating its patterns into the in-memory store without creating new cache files.
    """
    if is_custom_root:
        return {}
    migrated: Dict[str, List[str]] = {}
    try:
        if vfs.exists(DYNAMIC_CACHE_URI):
            data = vfs.read_json(DYNAMIC_CACHE_URI)
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(k, str) and k.strip() and isinstance(v, list):
                        migrated[k.strip()] = [str(x) for x in v if isinstance(x, str) and x.strip()]
            vfs.remove(DYNAMIC_CACHE_URI, missing_ok=True)
    except Exception:
        pass
    return migrated


def _load_dynamic_registry(
    proj_root: str,
    is_custom_root: bool,
) -> Dict[str, List[str]]:
    """Loads active runtime-registered patterns per module from memory."""
    norm_key = os.path.normcase(os.path.abspath(proj_root))
    store = _CUSTOM_ROOT_DYNAMIC_STORE.setdefault(norm_key, {})
    if not is_custom_root and not store:
        migrated = _migrate_legacy_dynamic_cache_if_needed(is_custom_root)
        if migrated:
            store.update(migrated)
    return dict(store)


def _save_dynamic_registry(
    registry: Dict[str, List[str]],
    proj_root: str,
    is_custom_root: bool,
) -> None:
    """Stores runtime-registered patterns per module in memory and removes legacy disk cache if present."""
    norm_key = os.path.normcase(os.path.abspath(proj_root))
    _CUSTOM_ROOT_DYNAMIC_STORE[norm_key] = dict(registry)
    if not is_custom_root:
        try:
            if vfs.exists(DYNAMIC_CACHE_URI):
                vfs.remove(DYNAMIC_CACHE_URI, missing_ok=True)
        except Exception:
            pass


def _extract_patterns_from_contrib_payload(payload: Any) -> List[str]:
    """
    Extracts ignore rules from `spaces.gitignore` (`include` -> positive, `exclude` -> `!<pattern>`)
    as well as legacy top-level `"gitignore"` list from a `contributes/core.json` or `contribute.json` payload.
    """
    if not isinstance(payload, dict):
        return []
    body = payload.get("core") if isinstance(payload.get("core"), dict) else payload
    if not isinstance(body, dict):
        return []

    patterns: List[str] = []

    spaces_sec = body.get("spaces")
    if isinstance(spaces_sec, dict):
        gi_space = spaces_sec.get("gitignore")
        if isinstance(gi_space, dict):
            raw_inc = gi_space.get("include")
            if isinstance(raw_inc, list):
                for item in raw_inc:
                    if isinstance(item, str) and item.strip():
                        s = item.strip()
                        if s not in patterns:
                            patterns.append(s)
            raw_exc = gi_space.get("exclude")
            if isinstance(raw_exc, list):
                for item in raw_exc:
                    if isinstance(item, str) and item.strip():
                        s = item.strip()
                        neg_s = s if s.startswith("!") else f"!{s}"
                        if neg_s not in patterns:
                            patterns.append(neg_s)

    raw_legacy = body.get("gitignore")
    if isinstance(raw_legacy, list):
        for item in raw_legacy:
            if isinstance(item, str) and item.strip():
                s = item.strip()
                if s not in patterns:
                    patterns.append(s)

    return patterns


def _collect_static_contributes_by_module(
    proj_root: str,
    yscb_root: str,
    is_custom_root: bool,
) -> Dict[str, List[str]]:
    """
    Collects static `"gitignore"` rules from installed modules in `yscb_root/.modules`
    (including `core` via its own `contributes/core.json`) and project-level
    `yscb_root/config/core/contribute.json`.
    """
    grouped: Dict[str, List[str]] = {}

    modules_dir = os.path.join(yscb_root, ".modules")
    if os.path.isdir(modules_dir):
        try:
            for mod_name in sorted(os.listdir(modules_dir)):
                if mod_name.startswith("."):
                    continue
                cpath = os.path.join(modules_dir, mod_name, "contributes", "core.json")
                if os.path.isfile(cpath):
                    try:
                        data = vfs.read_json(cpath)
                        pats = _extract_patterns_from_contrib_payload(data)
                        if pats:
                            bucket = grouped.setdefault(mod_name, [])
                            for p in pats:
                                if p not in bucket:
                                    bucket.append(p)
                    except Exception:
                        pass
        except OSError:
            pass
    elif not is_custom_root:
        try:
            if vfs.exists("module://") and vfs.is_dir("module://"):
                for mod_name in sorted(vfs.listdir("module://")):
                    if mod_name.startswith("."):
                        continue
                    c_uri = f"module://{mod_name}/contributes/core.json"
                    if vfs.exists(c_uri):
                        try:
                            data = vfs.read_json(c_uri)
                            pats = _extract_patterns_from_contrib_payload(data)
                            if pats:
                                bucket = grouped.setdefault(mod_name, [])
                                for p in pats:
                                    if p not in bucket:
                                        bucket.append(p)
                        except Exception:
                            pass
        except Exception:
            pass

    if "core" not in grouped:
        core_pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self_contrib_path = os.path.join(core_pkg_dir, "contributes", "core.json")
        if os.path.isfile(self_contrib_path):
            try:
                data = vfs.read_json(self_contrib_path)
                pats = _extract_patterns_from_contrib_payload(data)
                if pats:
                    grouped["core"] = pats
            except Exception:
                pass

    proj_contrib_path = os.path.join(yscb_root, "config", "core", "contribute.json")
    if os.path.isfile(proj_contrib_path):
        try:
            data = vfs.read_json(proj_contrib_path)
            pats = _extract_patterns_from_contrib_payload(data)
            if pats:
                bucket = grouped.setdefault("project", [])
                for p in pats:
                    if p not in bucket:
                        bucket.append(p)
        except Exception:
            pass

    return grouped


def _sort_module_keys(keys: Iterable[str]) -> List[str]:
    """Orders module keys with `core` first, `project` last, and other modules alphabetically."""
    key_set = set(keys)
    ordered: List[str] = []
    if "core" in key_set:
        ordered.append("core")
        key_set.remove("core")
    has_project = "project" in key_set
    if has_project:
        key_set.remove("project")
    ordered.extend(sorted(key_set))
    if has_project:
        ordered.append("project")
    return ordered


def _collect_space_registry_gitignore_groups(
    proj_root: str,
    yscb_root: str,
    is_custom_root: bool,
) -> Dict[str, List[str]]:
    """
    Collects `<owner>/gitignore` space definitions from `SpaceRegistry`
    (including `on_register_file_spaces` hooks and runtime registrations).
    """
    grouped: Dict[str, List[str]] = {}
    try:
        from core.space import SpaceRegistry, get_default_registry

        if not is_custom_root:
            reg = get_default_registry(project_root=proj_root, yscb_dir=yscb_root)
        else:
            reg = SpaceRegistry(project_root=proj_root, yscb_dir=yscb_root)

        for s_cfg in reg.list_spaces():
            if s_cfg.short_name != "gitignore" or not s_cfg.owner:
                continue
            bucket = grouped.setdefault(s_cfg.owner, [])
            for pat in s_cfg.include:
                s = str(pat).strip()
                if s and s != "*" and s not in bucket:
                    bucket.append(s)
            for pat in s_cfg.exclude:
                s = str(pat).strip()
                if s:
                    neg_s = s if s.startswith("!") else f"!{s}"
                    if neg_s not in bucket:
                        bucket.append(neg_s)
    except Exception:
        pass
    return grouped


def collect_grouped_patterns(
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> Dict[str, List[str]]:
    """
    Collects, normalizes, deduplicates, and sorts gitignore rules grouped by module name.
    """
    eff_proj, eff_yscb, is_custom = _resolve_roots(proj_root=proj_root, yscb_root=yscb_root)
    static_groups = _collect_static_contributes_by_module(eff_proj, eff_yscb, is_custom)
    space_groups = _collect_space_registry_gitignore_groups(eff_proj, eff_yscb, is_custom)
    dynamic_groups = _load_dynamic_registry(eff_proj, is_custom)

    combined_raw: Dict[str, List[str]] = {}
    for mod, pats in static_groups.items():
        combined_raw.setdefault(mod, []).extend(pats)
    for mod, pats in space_groups.items():
        bucket = combined_raw.setdefault(mod, [])
        for p in pats:
            if p not in bucket:
                bucket.append(p)
    for mod, pats in dynamic_groups.items():
        bucket = combined_raw.setdefault(mod, [])
        for p in pats:
            if p not in bucket:
                bucket.append(p)

    normalized_groups: Dict[str, List[str]] = {}
    for mod in _sort_module_keys(combined_raw.keys()):
        pos_list: List[str] = []
        neg_list: List[str] = []
        seen: Set[str] = set()
        for raw_p in combined_raw[mod]:
            norm_p = normalize_pattern(raw_p, eff_proj, eff_yscb)
            if norm_p and norm_p not in seen:
                seen.add(norm_p)
                if norm_p.startswith("!"):
                    neg_list.append(norm_p)
                else:
                    pos_list.append(norm_p)
        if pos_list or neg_list:
            if mod == "core":
                normalized_groups[mod] = pos_list + neg_list
            else:
                normalized_groups[mod] = sorted(pos_list) + sorted(neg_list)

    return normalized_groups


def render_managed_block(grouped_patterns: Dict[str, List[str]]) -> str:
    """Renders the `# === YSCB MANAGED GITIGNORE BEGIN ===` block with `# [<module>]` sub-headers."""
    lines: List[str] = [
        GITIGNORE_BEGIN_MARKER,
        "# Auto-managed by YSCB core.gitignore. Do not edit this block manually.",
    ]
    for mod in _sort_module_keys(grouped_patterns.keys()):
        pats = grouped_patterns.get(mod, [])
        if not pats:
            continue
        lines.append(f"# [{mod}]")
        lines.extend(pats)
    lines.append(GITIGNORE_END_MARKER)
    return "\n".join(lines)


def _strip_legacy_blocks_and_lines(content: str) -> Tuple[str, bool]:
    """
    Strips legacy `# === YSCB INTERNAL IGNORE BEGIN ===`, `# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===`,
    and legacy `# YS-Codebase Autonomous Internal Ignore Rules` lines while preserving user custom lines.
    Returns `(cleaned_content, had_legacy)`.
    """
    if not content:
        return "", False

    had_legacy = False
    cleaned = content

    for begin_m, end_m in (
        (LEGACY_INTERNAL_BEGIN, LEGACY_INTERNAL_END),
        (LEGACY_AW_BEGIN, LEGACY_AW_END),
    ):
        pat = re.compile(
            rf"\n*{re.escape(begin_m)}[\s\S]*?{re.escape(end_m)}\n*",
            re.MULTILINE,
        )
        if pat.search(cleaned):
            had_legacy = True
            cleaned = pat.sub("\n", cleaned)

    if "# YS-Codebase Autonomous Internal Ignore Rules" in cleaned:
        had_legacy = True
        out_lines: List[str] = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if stripped in LEGACY_UNANCHORED_LINES:
                continue
            out_lines.append(line)
        cleaned = "\n".join(out_lines)

    return cleaned, had_legacy


def _cleanup_obsolete_nested_gitignores(proj_root: str, yscb_root: str) -> List[str]:
    """
    Cleans up obsolete nested `.gitignore` files (`yscb://.gitignore` when `yscb:// != project://`,
    and `project://.vscode/schemas/.gitignore`) while preserving `yscb://.gitignore` if it contains
    user-authored custom rules outside the legacy managed block.
    """
    cleaned_paths: List[str] = []

    if os.path.normcase(os.path.realpath(os.path.abspath(proj_root))) != os.path.normcase(os.path.realpath(os.path.abspath(yscb_root))):
        yscb_gi = os.path.join(yscb_root, ".gitignore")
        if vfs.is_file(yscb_gi):
            try:
                raw = vfs.read_text(yscb_gi)
                rem, _ = _strip_legacy_blocks_and_lines(raw)
                pat_new = re.compile(
                    rf"\n*{re.escape(GITIGNORE_BEGIN_MARKER)}[\s\S]*?{re.escape(GITIGNORE_END_MARKER)}\n*",
                    re.MULTILINE,
                )
                rem = pat_new.sub("\n", rem)
                non_empty_user_lines = [
                    ln for ln in rem.splitlines() if ln.strip() and not ln.strip().startswith("# Auto-managed")
                ]
                if not non_empty_user_lines:
                    vfs.remove(yscb_gi, missing_ok=True)
                    cleaned_paths.append(yscb_gi)
                elif rem.strip() != raw.strip():
                    vfs.write_text(yscb_gi, rem.strip() + "\n", encoding="utf-8", atomic=True)
                    cleaned_paths.append(yscb_gi)
            except Exception:
                pass

    schemas_gi = os.path.join(proj_root, ".vscode", "schemas", ".gitignore")
    if vfs.is_file(schemas_gi):
        try:
            if vfs.read_text(schemas_gi).strip() == "*":
                vfs.remove(schemas_gi, missing_ok=True)
                cleaned_paths.append(schemas_gi)
        except Exception:
            pass

    return cleaned_paths


def _sync_runtime_gitignore_space(
    mod_name: str,
    raw_patterns: List[str],
    eff_proj: str,
    eff_yscb: str,
    is_custom: bool,
) -> None:
    """Bridges runtime gitignore pattern updates into `core.space` for the active workspace."""
    if is_custom:
        return
    try:
        from core.space import get_default_registry

        reg = get_default_registry(project_root=eff_proj, yscb_dir=eff_yscb)
        q_name = f"{mod_name}/gitignore"
        if not raw_patterns:
            unreg_fn = getattr(reg, "unregister_space", None)
            if callable(unreg_fn):
                unreg_fn(q_name)
            return

        inc_list: List[str] = []
        exc_list: List[str] = []
        for pat in raw_patterns:
            if pat.startswith("!"):
                core_p = pat[1:].strip()
                if core_p and core_p not in exc_list:
                    exc_list.append(core_p)
            else:
                if pat not in inc_list:
                    inc_list.append(pat)

        reg_fn = getattr(reg, "register_space", None) or getattr(reg, "define_ephemeral_space", None)
        if callable(reg_fn):
            reg_fn(
                q_name,
                {
                    "entries": ["project://"],
                    "include": inc_list,
                    "exclude": exc_list,
                    "watch": False,
                },
                watch=False,
            )
    except Exception:
        pass


def register_dynamic(
    module: str,
    patterns: Iterable[str],
    *,
    sync_now: bool = True,
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Registers or replaces runtime gitignore patterns for `module` (mandatory non-empty string).
    Bridges to `<module>/gitignore` in `core.space` and optionally triggers `sync()`.
    """
    mod_name = _validate_module_name(module)
    eff_proj, eff_yscb, is_custom = _resolve_roots(proj_root=proj_root, yscb_root=yscb_root)

    clean_list: List[str] = []
    seen: Set[str] = set()
    for p in patterns or []:
        if isinstance(p, str) and p.strip():
            s = p.strip()
            if s not in seen:
                seen.add(s)
                clean_list.append(s)

    reg = _load_dynamic_registry(eff_proj, is_custom)
    if clean_list:
        reg[mod_name] = clean_list
    else:
        reg.pop(mod_name, None)
    _save_dynamic_registry(reg, eff_proj, is_custom)
    _sync_runtime_gitignore_space(mod_name, clean_list, eff_proj, eff_yscb, is_custom)

    if sync_now:
        return sync(proj_root=eff_proj, yscb_root=eff_yscb)

    return {
        "updated": False,
        "created": False,
        "module": mod_name,
        "patterns": clean_list,
    }


def clear_dynamic(
    module: str,
    *,
    sync_now: bool = True,
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Removes all runtime gitignore patterns registered by `module` and optionally triggers `sync()`.
    """
    mod_name = _validate_module_name(module)
    eff_proj, eff_yscb, is_custom = _resolve_roots(proj_root=proj_root, yscb_root=yscb_root)

    reg = _load_dynamic_registry(eff_proj, is_custom)
    removed = mod_name in reg
    reg.pop(mod_name, None)
    _save_dynamic_registry(reg, eff_proj, is_custom)
    _sync_runtime_gitignore_space(mod_name, [], eff_proj, eff_yscb, is_custom)

    if sync_now:
        res = sync(proj_root=eff_proj, yscb_root=eff_yscb)
        res["cleared_module"] = mod_name
        res["had_dynamic_entries"] = removed
        return res

    return {
        "updated": False,
        "created": False,
        "cleared_module": mod_name,
        "had_dynamic_entries": removed,
    }


def register(
    module: str,
    patterns: Iterable[str],
    *,
    sync_now: bool = True,
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Alias for `register_dynamic` supporting positive rules and `!<pattern>` exemptions."""
    return register_dynamic(
        module,
        patterns,
        sync_now=sync_now,
        proj_root=proj_root,
        yscb_root=yscb_root,
    )


def unregister(
    module: str,
    patterns: Optional[Iterable[str]] = None,
    *,
    sync_now: bool = True,
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unregisters specific runtime gitignore patterns (or all patterns when `patterns` is None)
    for `module` and optionally triggers `sync()`.
    """
    if patterns is None:
        return clear_dynamic(
            module,
            sync_now=sync_now,
            proj_root=proj_root,
            yscb_root=yscb_root,
        )
    mod_name = _validate_module_name(module)
    eff_proj, eff_yscb, is_custom = _resolve_roots(proj_root=proj_root, yscb_root=yscb_root)
    remove_set = {str(p).strip() for p in patterns if isinstance(p, str) and str(p).strip()}
    reg = _load_dynamic_registry(eff_proj, is_custom)
    existing = list(reg.get(mod_name, []))
    remaining = [p for p in existing if p not in remove_set]
    return register_dynamic(
        mod_name,
        remaining,
        sync_now=sync_now,
        proj_root=eff_proj,
        yscb_root=eff_yscb,
    )


def sync(
    *,
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
    emit_event: bool = True,
) -> Dict[str, Any]:
    """
    Synthesizes static `contributes` and dynamic SDK rules into `project://.gitignore`
    with Zero-Touch idempotency and atomic file replacement.
    """
    eff_proj, eff_yscb, is_custom = _resolve_roots(proj_root=proj_root, yscb_root=yscb_root)
    grouped = collect_grouped_patterns(proj_root=eff_proj, yscb_root=eff_yscb)
    block_text = render_managed_block(grouped)

    flat_patterns: List[str] = []
    for mod in _sort_module_keys(grouped.keys()):
        for p in grouped[mod]:
            if p not in flat_patterns:
                flat_patterns.append(p)

    gi_path = os.path.join(eff_proj, ".gitignore")
    has_existing = vfs.is_file(gi_path)
    existing_content = ""
    if has_existing:
        try:
            existing_content = vfs.read_text(gi_path)
        except Exception:
            existing_content = ""

    base_content, _ = _strip_legacy_blocks_and_lines(existing_content)

    managed_re = re.compile(
        rf"{re.escape(GITIGNORE_BEGIN_MARKER)}[\s\S]*?{re.escape(GITIGNORE_END_MARKER)}",
        re.MULTILINE,
    )

    if managed_re.search(base_content):
        merged_content = managed_re.sub(block_text, base_content)
        if not merged_content.endswith("\n"):
            merged_content += "\n"
    else:
        trimmed = base_content.strip()
        if trimmed:
            merged_content = trimmed + "\n\n" + block_text + "\n"
        else:
            merged_content = block_text + "\n"

    cleaned_nested = _cleanup_obsolete_nested_gitignores(eff_proj, eff_yscb)

    if has_existing and existing_content == merged_content:
        return {
            "updated": False,
            "created": False,
            "target_path": gi_path,
            "groups": grouped,
            "patterns": flat_patterns,
            "cleaned_nested": cleaned_nested,
        }

    try:
        os.makedirs(eff_proj, exist_ok=True)
        vfs.write_text(gi_path, merged_content, encoding="utf-8", atomic=True)
        result = {
            "updated": True,
            "created": not has_existing,
            "target_path": gi_path,
            "groups": grouped,
            "patterns": flat_patterns,
            "cleaned_nested": cleaned_nested,
        }
        if emit_event and not is_custom:
            try:
                events.broadcast(
                    "on_gitignore_synced",
                    ExecutionContext("core", "gitignore", ["sync"]),
                    emit_module="core",
                )
            except Exception:
                pass
        return result
    except Exception as exc:
        return {
            "updated": False,
            "created": False,
            "target_path": gi_path,
            "groups": grouped,
            "patterns": flat_patterns,
            "cleaned_nested": cleaned_nested,
            "error": str(exc),
        }


def status(
    *,
    proj_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Inspects the current state of `project://.gitignore` and reports whether the managed block
    is present and up-to-date with all registered static and dynamic module rules.
    """
    eff_proj, eff_yscb, is_custom = _resolve_roots(proj_root=proj_root, yscb_root=yscb_root)
    grouped = collect_grouped_patterns(proj_root=eff_proj, yscb_root=eff_yscb)
    expected_block = render_managed_block(grouped)

    flat_patterns: List[str] = []
    for mod in _sort_module_keys(grouped.keys()):
        for p in grouped[mod]:
            if p not in flat_patterns:
                flat_patterns.append(p)

    gi_path = os.path.join(eff_proj, ".gitignore")
    exists = vfs.is_file(gi_path)
    is_synced = False
    has_managed_block = False

    if exists:
        try:
            raw = vfs.read_text(gi_path)
            has_managed_block = GITIGNORE_BEGIN_MARKER in raw and GITIGNORE_END_MARKER in raw
            is_synced = expected_block in raw
        except Exception:
            pass

    dynamic_reg = _load_dynamic_registry(eff_proj, is_custom)
    return {
        "target_path": gi_path,
        "exists": exists,
        "has_managed_block": has_managed_block,
        "in_sync": is_synced,
        "groups": grouped,
        "dynamic_modules": sorted(dynamic_reg.keys()),
        "total_patterns": len(flat_patterns),
        "patterns": flat_patterns,
    }

