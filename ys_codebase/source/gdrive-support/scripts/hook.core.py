"""
Core Lifecycle Hook for `module:gdrive-support` (`scripts/hook.core.py`).
Listens to `on_register_file_spaces` to dynamically register `gdrive-support/cloud`
when `repo_sync.enable` is True without instantiating `SpaceRegistry` recursively.
"""

from __future__ import annotations

from typing import Any, List, Optional

from core.log import log
from gdrive_support.config import load_lightweight_repo_sync_settings


def _load_lightweight_repo_sync_settings(registry: Any = None) -> tuple[bool, bool, List[str]]:
    """Delegate lightweight repo_sync configuration extraction to gdrive_support.config."""
    return load_lightweight_repo_sync_settings(registry)


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
        log(
            f"[gdrive-support:hook] Warning: Failed during on_register_file_spaces: {exc}",
            stream="stderr",
        )
        return False
