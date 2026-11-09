"""
Core Lifecycle Hook for `module:vscode-support` (`scripts/hook.core.py`).
Subscribes to `on_env_synced`, `on_reload`, and `on_remove` emitted by `core`.
"""

import os
import time
from typing import Any, Dict, Optional, Tuple

from core import uri
from core.context import get_runtime_context
from core.log import log


def _get_workspace_projector() -> Tuple[Optional[str], Any]:
    from vscode_support.projector import SettingsProjector

    proj_root = uri.resolve("project://", interactive=False)
    if not proj_root or not os.path.isdir(proj_root):
        return None, None
    return proj_root, SettingsProjector()


def _dir_shallow_fingerprint(dir_path: str) -> Tuple[Any, ...]:
    if not os.path.isdir(dir_path):
        return ()
    try:
        st = os.stat(dir_path)
        entries = tuple(sorted(os.listdir(dir_path)))
        return (int(getattr(st, "st_mtime_ns", 0)), entries)
    except OSError:
        return ()


def _compute_workspace_sync_fingerprint(proj_root: str, yscb_dir: str) -> Optional[Tuple[Any, ...]]:
    settings_path = os.path.join(proj_root, ".vscode", "settings.json")
    schemas_dir = os.path.join(proj_root, ".vscode", "schemas")
    if not os.path.isfile(settings_path) or not os.path.isdir(schemas_dir):
        return None
    try:
        settings_mtime = int(getattr(os.stat(settings_path), "st_mtime_ns", 0))
    except OSError:
        return None
    return (
        os.path.normcase(os.path.abspath(proj_root)),
        os.path.normcase(os.path.abspath(yscb_dir)),
        settings_mtime,
        _dir_shallow_fingerprint(os.path.join(yscb_dir, ".modules")),
        _dir_shallow_fingerprint(os.path.join(yscb_dir, ".mirror")),
        _dir_shallow_fingerprint(os.path.join(yscb_dir, "source")),
        _dir_shallow_fingerprint(os.path.join(yscb_dir, ".venv")),
    )


def _get_hook_sync_cache() -> Dict[str, Tuple[Tuple[Any, ...], float]]:
    return get_runtime_context().get_module_state("vscode_support.hook_sync_cache", dict)


def _sync_workspace() -> bool:
    try:
        proj_root, projector = _get_workspace_projector()
        if not proj_root or projector is None:
            return False
        proj_key = os.path.normcase(os.path.abspath(proj_root))
        yscb_dir = getattr(projector, "yscb_dir", "") or ""
        sync_cache = _get_hook_sync_cache()
        now = time.monotonic()
        pre_fp = _compute_workspace_sync_fingerprint(proj_root, yscb_dir) if yscb_dir else None
        if pre_fp is not None and proj_key in sync_cache:
            cached_fp, cached_ts = sync_cache[proj_key]
            if cached_fp == pre_fp and (now - cached_ts) < 2.0:
                return True
        ok = bool(projector.sync_vscode_settings(proj_root))
        if ok and yscb_dir:
            post_fp = _compute_workspace_sync_fingerprint(proj_root, yscb_dir)
            if post_fp is not None:
                sync_cache[proj_key] = (post_fp, time.monotonic())
        return ok
    except Exception as e:
        log(f"[vscode-support:hook] Warning: Failed to sync VS Code workspace: {e}", stream="stderr")
        return False


def on_env_synced(ctx: Any = None) -> bool:
    """當 `core` 完成微環境 `pip_dependencies` 同步後自動更新穩定連結、Schema 與 `.vscode/settings.json`。"""
    return _sync_workspace()


def on_reload(ctx: Any = None) -> bool:
    """當 `core` 重載模組與擴充點後自動同步 Schema 與 `.vscode/settings.json`。"""
    return _sync_workspace()


def on_register_file_spaces(ctx: Any = None) -> bool:
    """當 `SpaceRegistry` 重載時確保 `vscode-support/gitignore` 空間已註冊（若已由靜態 `core.json` 載入則跳過重複註冊）。"""
    try:
        registry = ctx.get("registry") if isinstance(ctx, dict) else getattr(ctx, "registry", None)
        if registry is None:
            return False
        spaces_map = getattr(registry, "_spaces", None)
        if isinstance(spaces_map, dict) and "vscode-support/gitignore" in spaces_map:
            return True
        has_space_fn = getattr(registry, "has_space", None)
        if callable(has_space_fn):
            try:
                if bool(has_space_fn("vscode-support/gitignore")):
                    return True
            except Exception:
                pass
        register_fn = getattr(registry, "register_space", None) or getattr(
            registry, "define_ephemeral_space", None
        )
        if not callable(register_fn):
            return False
        register_fn(
            "vscode-support/gitignore",
            {
                "description": "VS Code 動態生成之 JSON Schema 目錄",
                "entries": ["project://"],
                "include": ["project://.vscode/schemas/"],
                "watch": False,
            },
        )
        return True
    except Exception as e:
        log(f"[vscode-support:hook] Warning: Failed during on_register_file_spaces: {e}", stream="stderr")
        return False


def on_remove(ctx: Any = None) -> bool:
    """當移除目標包含 `vscode-support`（或其別名 `vsc`）時，100% 乾淨還原 `.vscode/settings.json` 並清除 `.vscode/schemas/` 與穩定連結。"""
    try:
        targets = getattr(ctx, "args", None) if ctx is not None else None
        if not isinstance(targets, (list, tuple)) or not ({"vscode-support", "vsc"} & set(targets)):
            return False
        proj_root, projector = _get_workspace_projector()
        if not proj_root or projector is None:
            return False
        proj_key = os.path.normcase(os.path.abspath(proj_root))
        _get_hook_sync_cache().pop(proj_key, None)
        return projector.revert_vscode_settings(proj_root)
    except Exception as e:
        log(f"[vscode-support:hook] Warning: Failed during on_remove revert: {e}", stream="stderr")
        return False
