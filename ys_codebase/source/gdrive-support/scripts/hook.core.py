"""
Core Lifecycle Hook for `module:gdrive-support` (`scripts/hook.core.py`).
Listens to `on_register_file_spaces` to dynamically register `gdrive-support/cloud`
when `repo_sync.enable` is True without instantiating `SpaceRegistry` recursively.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional


def _load_lightweight_repo_sync_settings(registry: Any = None) -> tuple[bool, bool, List[str]]:
    """
    Lightweight reader for `gdrive-support` config (`repo_sync` & `sync_spaces`).
    Never calls `load_gdrive_config()` or `SpaceRegistry()` to avoid recursion.
    """
    raw_cfg: Dict[str, Any] = {}
    raw_sync_spaces: List[Any] = []

    proj_root_obj = getattr(registry, "project_root", None)
    yscb_dir_obj = getattr(registry, "yscb_dir", None)
    proj_str = str(proj_root_obj) if proj_root_obj is not None else None
    yscb_str = (
        str(yscb_dir_obj)
        if yscb_dir_obj is not None
        else (proj_str if proj_str else None)
    )

    try:
        from core import config as core_config
        from core import contributes as core_contributes
        from core import uri

        if proj_str and yscb_str:
            with uri.host_scope(proj_str, yscb_str):
                loaded = core_config.get("gdrive-support")
                if isinstance(loaded, dict):
                    raw_cfg.update(loaded)
                contrib = core_contributes.get("gdrive-support")
                if isinstance(contrib, dict) and isinstance(contrib.get("sync_spaces"), list):
                    raw_sync_spaces = list(contrib["sync_spaces"])
        else:
            loaded = core_config.get("gdrive-support")
            if isinstance(loaded, dict):
                raw_cfg.update(loaded)
            contrib = core_contributes.get("gdrive-support")
            if isinstance(contrib, dict) and isinstance(contrib.get("sync_spaces"), list):
                raw_sync_spaces = list(contrib["sync_spaces"])
    except Exception:
        pass

    if isinstance(raw_cfg.get("sync_spaces"), list):
        raw_sync_spaces = list(raw_cfg["sync_spaces"])

    repo_sync_sec = raw_cfg.get("repo_sync")
    repo_sync_dict = dict(repo_sync_sec) if isinstance(repo_sync_sec, dict) else {}

    if "enable" in repo_sync_dict:
        enabled = bool(repo_sync_dict["enable"])
    elif "repo_sync_enabled" in raw_cfg:
        enabled = bool(raw_cfg["repo_sync_enabled"])
    else:
        enabled = False

    auto_sync = bool(
        enabled and repo_sync_dict.get("auto_sync", raw_cfg.get("auto_sync", False))
    )

    compose_spaces: List[str] = []
    for item in raw_sync_spaces:
        sp = ""
        if isinstance(item, dict):
            sp = str(item.get("space") or "").strip()
        elif isinstance(item, str) and item.strip():
            sp = item.strip()
        if sp and sp not in ("cloud", "/cloud", "gdrive-support/cloud") and sp not in compose_spaces:
            compose_spaces.append(sp)

    if not compose_spaces:
        compose_spaces = ["source", "docs", "plans"]

    return enabled, auto_sync, compose_spaces


def on_register_file_spaces(ctx: Optional[Any] = None) -> bool:
    """
    Triggered on `SpaceRegistry.reload()`.
    If `repo_sync.enable` is True, dynamically registers `gdrive-support/cloud`.
    """
    try:
        registry = ctx.get("registry") if isinstance(ctx, dict) else getattr(ctx, "registry", None)
        if registry is None:
            return False

        enabled, auto_sync, compose_spaces = _load_lightweight_repo_sync_settings(registry)
        if not enabled:
            return False

        register_fn = getattr(registry, "register_space", None) or getattr(
            registry, "define_ephemeral_space", None
        )
        if not callable(register_fn):
            return False

        register_fn(
            "gdrive-support/cloud",
            {
                "description": "Google Drive repo_sync 雲端分支同步空間",
                "compose": compose_spaces,
                "watch": bool(auto_sync),
            },
        )
        return True
    except Exception as exc:
        print(
            f"[gdrive-support:hook] Warning: Failed during on_register_file_spaces: {exc}",
            file=sys.stderr,
        )
        return False
