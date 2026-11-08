"""
Protected Module Namespace Loader for YS-Codebase (`core.loader`).
100% Python Standard Library.

Provides a single sanctioned authority for dynamically loading Python module files
(CLI scripts, lifecycle hooks, migrations, and `code.func://` symbols) with:
1. `(st_mtime_ns, st_size)` generation fingerprint caching & automatic hot-reload.
2. Atomic `sys.modules` snapshot & rollback on `exec_module` failure (preventing half-initialized zombie modules).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import types
from typing import Dict, Optional, Sequence, Tuple, Union

from core.context import get_runtime_context


def _file_generation(file_path: str) -> Tuple[int, int]:
    """Returns `(st_mtime_ns, st_size)` for a file path, or `(-1, -1)` if stat fails."""
    try:
        st = os.stat(file_path)
        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
        return (mtime_ns, st.st_size)
    except OSError:
        return (-1, -1)


def load_module_from_path(
    module_key: str,
    file_path: Union[str, Path],
    *,
    alias_keys: Sequence[str] = (),
    reload_if_changed: bool = True,
    priority_module: Optional[str] = None,
    extra_sys_paths: Optional[Sequence[str]] = None,
    yscb_root: Optional[str] = None,
) -> types.ModuleType:
    """
    Loads a Python module from `file_path` into a protected namespace key (`module_key`),
    caching by `(norm_file_path, st_mtime_ns, st_size)` and rolling back `sys.modules`
    atomically if `exec_module` raises an exception.

    Args:
        module_key: Unique module namespace identifier in `sys.modules` (e.g. `_yscb_mod_core_cli`).
        file_path: Physical path to the `.py` file.
        alias_keys: Optional additional keys in `sys.modules` to bind to the loaded module.
        reload_if_changed: When True, reloads the module if file `(mtime_ns, size)` changed.
        priority_module: Optional module name passed to `ensure_installed_modules_path`.
        extra_sys_paths: Optional extra directories passed to `ensure_installed_modules_path`.
        yscb_root: Optional explicit `yscb_root` passed to `ensure_installed_modules_path`.

    Returns:
        Loaded `types.ModuleType` instance.
    """
    if not isinstance(module_key, str) or not module_key.startswith("_yscb_mod_"):
        raise ValueError(
            f"Protected namespace violation: module_key '{module_key}' must start with '_yscb_mod_'."
        )
    real_path = os.path.normpath(os.path.abspath(str(file_path)))
    if not os.path.isfile(real_path):
        raise FileNotFoundError(f"Module file not found: '{real_path}'")

    if priority_module is not None or extra_sys_paths is not None or yscb_root is not None:
        from core.platform import ensure_installed_modules_path

        ensure_installed_modules_path(
            yscb_root=yscb_root,
            priority_module=priority_module,
            extra_paths=list(extra_sys_paths) if extra_sys_paths else None,
        )

    ctx = get_runtime_context()
    mtime_ns, size = _file_generation(real_path)

    with ctx.loader_lock:
        cached = ctx.loaded_modules_cache.get(module_key)
        if cached is not None:
            c_path, c_mtime, c_size, c_mod = cached
            if c_path == real_path and (
                not reload_if_changed or (c_mtime == mtime_ns and c_size == size and mtime_ns != -1)
            ):
                sys.modules[module_key] = c_mod
                for ak in alias_keys:
                    if ak:
                        sys.modules[ak] = c_mod
                return c_mod

        spec = importlib.util.spec_from_file_location(module_key, real_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for '{real_path}' (key='{module_key}')")

        mod_obj = importlib.util.module_from_spec(spec)
        all_keys = (module_key, *(ak for ak in alias_keys if ak))
        prev_entries: Dict[str, Optional[types.ModuleType]] = {
            k: sys.modules.get(k) for k in all_keys
        }

        for k in all_keys:
            sys.modules[k] = mod_obj

        try:
            spec.loader.exec_module(mod_obj)
        except Exception:
            for k, prev_mod in prev_entries.items():
                if prev_mod is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = prev_mod
            ctx.loaded_modules_cache.pop(module_key, None)
            raise

        ctx.loaded_modules_cache[module_key] = (real_path, mtime_ns, size, mod_obj)
        return mod_obj


def get_cached_module(module_key: str) -> Optional[types.ModuleType]:
    """Returns a previously loaded module from the runtime loader cache if present."""
    ctx = get_runtime_context()
    with ctx.loader_lock:
        entry = ctx.loaded_modules_cache.get(module_key)
        return entry[3] if entry is not None else None


def clear_loaded_modules(prefix: Optional[str] = None) -> None:
    """Clears cached module entries (and removes matching `_yscb_` keys from `sys.modules`)."""
    ctx = get_runtime_context()
    with ctx.loader_lock:
        if prefix is None:
            keys = list(ctx.loaded_modules_cache.keys())
            ctx.loaded_modules_cache.clear()
        else:
            keys = [k for k in ctx.loaded_modules_cache if k.startswith(prefix)]
            for k in keys:
                ctx.loaded_modules_cache.pop(k, None)
        for k in keys:
            if k.startswith("_yscb_"):
                sys.modules.pop(k, None)


__all__ = (
    "load_module_from_path",
    "get_cached_module",
    "clear_loaded_modules",
)
