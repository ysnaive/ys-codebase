"""
Core Platform - Cross-Platform Python Environment & Runtime sys.path Authority.
"""

import os
import platform
import sys
from typing import List, Optional, Sequence, Set, Tuple


_ACTIVE_TEST_SOURCE_PATHS: List[Tuple[str, str]] = []


def _norm_abs(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def _norm_key(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def _is_source_tree_path(path: str, yscb_root: Optional[str] = None) -> bool:
    if not path:
        return False
    eff_root = yscb_root or _resolve_yscb_root(None)
    root_real = os.path.normpath(os.path.realpath(eff_root)) if eff_root and os.path.exists(eff_root) else None
    host_real = os.path.dirname(root_real) if root_real else None
    for cand in (_norm_abs(path), os.path.normpath(os.path.realpath(path))):
        slash_p = cand.replace("\\", "/")
        if yscb_root:
            src_dir = _norm_abs(os.path.join(yscb_root, "source")).replace("\\", "/")
            if slash_p == src_dir or slash_p.startswith(src_dir + "/"):
                return True
        matched_workspace = False
        if root_real:
            for base in (root_real, host_real):
                if base and (cand == base or cand.startswith(base + os.sep)):
                    matched_workspace = True
                    rel_slash = os.path.relpath(cand, base).replace("\\", "/")
                    if rel_slash == "source" or rel_slash.startswith("source/") or "/source/" in f"/{rel_slash}/":
                        return True
        if not matched_workspace:
            if "/source/" in slash_p or slash_p.endswith("/source"):
                return True
    return False


def _resolve_yscb_root(yscb_root: Optional[str] = None) -> Optional[str]:
    if yscb_root and str(yscb_root).strip():
        return _norm_abs(str(yscb_root))
    try:
        from core import uri
        resolved = uri.resolve("yscb://")
        if resolved:
            return _norm_abs(resolved)
    except Exception:
        pass
    return None


def _collect_host_roots(yscb_root: Optional[str]) -> List[str]:
    root = _resolve_yscb_root(yscb_root)
    candidates: List[str] = []
    if root and os.path.isdir(root):
        candidates.append(root)
        host_cand = os.path.dirname(root)
        if os.path.isfile(os.path.join(host_cand, "yscb.config.json")):
            candidates.append(_norm_abs(host_cand))

    try:
        from core import uri
        for scheme in ("project://", "yscb.host://"):
            try:
                resolved = uri.resolve(scheme)
                if resolved and os.path.isdir(resolved):
                    candidates.append(_norm_abs(resolved))
            except Exception:
                continue
    except Exception:
        pass

    result: List[str] = []
    seen: Set[str] = set()
    for cand in candidates:
        if _is_source_tree_path(cand, root):
            continue
        key = _norm_key(cand)
        if key not in seen:
            seen.add(key)
            result.append(cand)
    return result


def get_venv_site_packages(yscb_root: str) -> str:
    """
    Returns the platform-specific private virtualenv site-packages path under yscb_root.
    """
    tag = f"py{sys.version_info.major}{sys.version_info.minor}"
    sys_name = platform.system()
    sub = (
        os.path.join(".venv", tag, "Lib", "site-packages")
        if sys_name == "Windows"
        else os.path.join(".venv", tag, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
    )
    return os.path.join(yscb_root, sub)


def _read_host_venv_pth(site_pkg: str) -> List[str]:
    """Reads valid directory entries from ``<site_pkg>/host_venv.pth``, ignoring comments and import statements."""
    pth = os.path.join(site_pkg, "host_venv.pth")
    if not os.path.isfile(pth):
        return []
    entries: List[str] = []
    try:
        with open(pth, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                t = line.strip()
                if not t or t.startswith("#") or t.startswith(("import ", "import\t")):
                    continue
                if os.path.isdir(t) and t not in entries:
                    entries.append(t)
    except Exception:
        pass
    return entries


def ensure_private_venv(yscb_root: str) -> None:
    """
    Ensures that the private virtual environment for the current Python interpreter
    version is added to sys.path, recursively parsing any host_venv.pth files.

    Args:
        yscb_root: Absolute or relative path to the YSCB project root directory.
    """
    site_pkg = get_venv_site_packages(yscb_root)
    if os.path.isdir(site_pkg) and site_pkg not in sys.path:
        for t in reversed(_read_host_venv_pth(site_pkg)):
            if t not in sys.path:
                sys.path.insert(0, t)
        sys.path.insert(0, site_pkg)


def list_installed_module_roots(
    yscb_root: Optional[str] = None,
    priority_module: Optional[str] = None,
) -> List[str]:
    """
    Scan `<yscb_root>/.modules/` and return normalized absolute paths of all
    installed module directories.

    Hidden entries (starting with `.`, such as `.staging_*` or `.old_*`), non-directory
    entries, and any path pointing into `/source` are excluded.
    Ordering places `.modules/<priority_module>` first (if specified and present),
    followed by `.modules/core` (if present), followed by all remaining installed
    modules sorted alphabetically by directory name.
    """
    root = _resolve_yscb_root(yscb_root)
    if not root:
        return []
    modules_dir = os.path.join(root, ".modules")
    if not os.path.isdir(modules_dir):
        return []

    try:
        entries = sorted(os.listdir(modules_dir))
    except OSError:
        return []

    valid_map = {}
    for entry in entries:
        if not entry or entry.startswith("."):
            continue
        mod_path = _norm_abs(os.path.join(modules_dir, entry))
        if not os.path.isdir(mod_path):
            continue
        if _is_source_tree_path(mod_path, root):
            continue
        valid_map[entry] = mod_path

    ordered_names: List[str] = []
    if priority_module and priority_module in valid_map:
        ordered_names.append(priority_module)
    if "core" in valid_map and "core" not in ordered_names:
        ordered_names.append("core")
    for name in sorted(valid_map.keys()):
        if name not in ordered_names:
            ordered_names.append(name)

    result: List[str] = []
    seen_keys: Set[str] = set()
    for name in ordered_names:
        p = valid_map[name]
        key = _norm_key(p)
        if key not in seen_keys:
            seen_keys.add(key)
            result.append(p)
    return result


def list_module_search_roots(
    yscb_root: Optional[str] = None,
    prefer_source: bool = True,
) -> List[str]:
    """
    Return normalized absolute paths of all YSCB module search roots under `yscb_root`.

    When `prefer_source=True` (used for static IDE analysis projection such as
    VS Code `python.analysis.extraPaths`), `<yscb_root>/source/<mod>` is preferred
    whenever a valid non-hidden module directory exists under `source/`, falling back to
    `<yscb_root>/.modules/<mod>` for installed-only modules. When `prefer_source=False`,
    delegates to `list_installed_module_roots(yscb_root)`.
    Ordering places `core` first (if present), followed by all remaining modules
    sorted alphabetically by module directory name.
    """
    root = _resolve_yscb_root(yscb_root)
    if not root:
        return []
    if not prefer_source:
        return list_installed_module_roots(root)

    valid_map = {}
    modules_dir = os.path.join(root, ".modules")
    if os.path.isdir(modules_dir):
        try:
            for entry in sorted(os.listdir(modules_dir)):
                if not entry or entry.startswith("."):
                    continue
                mod_path = _norm_abs(os.path.join(modules_dir, entry))
                if os.path.isdir(mod_path) and not _is_source_tree_path(mod_path, root):
                    valid_map[entry] = mod_path
        except OSError:
            pass

    source_dir = os.path.join(root, "source")
    if os.path.isdir(source_dir):
        try:
            for entry in sorted(os.listdir(source_dir)):
                if not entry or entry.startswith("."):
                    continue
                src_mod_path = _norm_abs(os.path.join(source_dir, entry))
                if os.path.isdir(src_mod_path):
                    valid_map[entry] = src_mod_path
        except OSError:
            pass

    ordered_names: List[str] = []
    if "core" in valid_map:
        ordered_names.append("core")
    for name in sorted(valid_map.keys()):
        if name not in ordered_names:
            ordered_names.append(name)

    result: List[str] = []
    seen_keys: Set[str] = set()
    for name in ordered_names:
        p = valid_map[name]
        key = _norm_key(p)
        if key not in seen_keys:
            seen_keys.add(key)
            result.append(p)
    return result


def ensure_installed_modules_path(
    yscb_root: Optional[str] = None,
    priority_module: Optional[str] = None,
    include_host_roots: bool = False,
    extra_paths: Optional[Sequence[str]] = None,
) -> List[str]:
    """
    Ensure all installed `.modules/<mod>` roots (plus optional `extra_paths` and
    host roots) are mounted in `sys.path` with deterministic front priority.
    """
    root = _resolve_yscb_root(yscb_root)
    installed_roots = list_installed_module_roots(root, priority_module=priority_module)

    front_paths: List[str] = []
    front_keys: Set[str] = set()

    def _add_front(cand: str, allow_source: bool = False) -> None:
        if not cand or not os.path.isdir(cand):
            return
        norm_p = _norm_abs(cand)
        if not allow_source and _is_source_tree_path(norm_p, root):
            return
        key = _norm_key(norm_p)
        if key not in front_keys:
            front_keys.add(key)
            front_paths.append(norm_p)

    if extra_paths:
        for ep in extra_paths:
            _add_front(ep, allow_source=True)

    current_root_key = _norm_key(root) if root and os.path.isdir(root) else ""
    for active_src, active_root_key in list(_ACTIVE_TEST_SOURCE_PATHS):
        if not active_root_key or active_root_key == current_root_key:
            _add_front(active_src, allow_source=True)

    if root:
        modules_dir = os.path.join(root, ".modules")
        if priority_module:
            _add_front(os.path.join(modules_dir, priority_module))
        _add_front(os.path.join(modules_dir, "core"))

    promoted: List[str] = []
    if front_paths:
        sys.path[:] = [
            existing for existing in sys.path
            if not (existing and _norm_key(existing) in front_keys)
        ]
        for idx, fp in enumerate(front_paths):
            sys.path.insert(idx, fp)
            promoted.append(fp)

    existing_keys: Set[str] = {_norm_key(p) for p in sys.path if p}
    insert_pos = len(front_paths)
    for mod_root in installed_roots:
        key = _norm_key(mod_root)
        if key not in existing_keys:
            sys.path.insert(insert_pos, mod_root)
            insert_pos += 1
            existing_keys.add(key)
            promoted.append(mod_root)

    if include_host_roots:
        for host_root in _collect_host_roots(root):
            key = _norm_key(host_root)
            if key not in existing_keys:
                sys.path.append(host_root)
                existing_keys.add(key)
                promoted.append(host_root)

    return promoted


def build_runtime_pythonpath(
    yscb_root: Optional[str] = None,
    priority_module: Optional[str] = None,
    include_host_roots: bool = True,
    existing_pythonpath: Optional[str] = None,
) -> str:
    """
    Build an `os.pathsep`-joined `PYTHONPATH` string for child processes,
    including `.venv` site-packages, all installed `.modules/<mod>`, host roots,
    and existing `PYTHONPATH` entries while strictly excluding `/source` paths.
    """
    root = _resolve_yscb_root(yscb_root)
    candidates: List[str] = []

    if root:
        site_pkg = get_venv_site_packages(root)
        if os.path.isdir(site_pkg):
            candidates.append(_norm_abs(site_pkg))
            for t in _read_host_venv_pth(site_pkg):
                candidates.append(_norm_abs(t))

    candidates.extend(list_installed_module_roots(root, priority_module=priority_module))

    if include_host_roots:
        candidates.extend(_collect_host_roots(root))

    raw_existing = os.environ.get("PYTHONPATH", "") if existing_pythonpath is None else existing_pythonpath
    if raw_existing:
        for item in raw_existing.split(os.pathsep):
            cleaned = item.strip()
            if cleaned:
                candidates.append(_norm_abs(cleaned))

    final_entries: List[str] = []
    seen_keys: Set[str] = set()
    for cand in candidates:
        if not cand or _is_source_tree_path(cand, root):
            continue
        key = _norm_key(cand)
        if key not in seen_keys:
            seen_keys.add(key)
            final_entries.append(cand)

    return os.pathsep.join(final_entries)


def init_subprocess_sys_path(parent_sys_path: Sequence[str]) -> None:
    """
    Synchronize a child worker process's `sys.path` with `parent_sys_path`
    by inserting missing entries at the front while preserving order.
    """
    if not parent_sys_path:
        return
    for entry in reversed(list(parent_sys_path)):
        if entry and entry not in sys.path:
            sys.path.insert(0, entry)


def activate_test_module_source_path(
    src_real: str,
    src_root: Optional[str] = None,
    yscb_root: Optional[str] = None,
) -> List[str]:
    """
    Prepare `sys.path` for `dev test` suite discovery of a single target module:
    mounts all installed `.modules/*` dependency roots, strips other modules'
    `source/*` paths under `src_root`, pins `src_real` at `sys.path[0]`, and
    returns the original `sys.path` snapshot.
    """
    orig_sys_path = list(sys.path)
    norm_src_real = _norm_abs(src_real)
    real_src_key = _norm_key(norm_src_real)
    resolved_root = _resolve_yscb_root(yscb_root)
    target_root_key = _norm_key(resolved_root) if resolved_root and os.path.isdir(resolved_root) else ""

    if src_root:
        real_root_key = _norm_key(src_root)
        root_prefix = real_root_key + os.sep
        _ACTIVE_TEST_SOURCE_PATHS[:] = [
            (p, rk) for p, rk in _ACTIVE_TEST_SOURCE_PATHS
            if not (
                (_norm_key(p) == real_root_key or _norm_key(p).startswith(root_prefix))
                and _norm_key(p) != real_src_key
            )
        ]

    _ACTIVE_TEST_SOURCE_PATHS[:] = [
        (p, rk) for p, rk in _ACTIVE_TEST_SOURCE_PATHS if _norm_key(p) != real_src_key
    ]
    _ACTIVE_TEST_SOURCE_PATHS.insert(0, (norm_src_real, target_root_key))

    ensure_installed_modules_path(yscb_root=yscb_root)

    if src_root:
        real_root_key = _norm_key(src_root)
        root_prefix = real_root_key + os.sep
        sys.path[:] = [
            p for p in sys.path
            if not (
                p
                and (_norm_key(p) == real_root_key or _norm_key(p).startswith(root_prefix))
                and _norm_key(p) != real_src_key
            )
        ]

    sys.path[:] = [
        p for p in sys.path
        if not (p and (_norm_key(p) == real_src_key or _norm_abs(p) == norm_src_real))
    ]
    sys.path.insert(0, norm_src_real)
    return orig_sys_path


def restore_sys_path(snapshot: Sequence[str]) -> None:
    """
    Restore `sys.path` in-place from a previously captured snapshot and prune
    any active test source paths no longer present in `sys.path`.
    """
    sys.path[:] = list(snapshot)
    snapshot_keys = {_norm_key(p) for p in snapshot if p}
    _ACTIVE_TEST_SOURCE_PATHS[:] = [
        (p, rk) for p, rk in _ACTIVE_TEST_SOURCE_PATHS if _norm_key(p) in snapshot_keys
    ]
