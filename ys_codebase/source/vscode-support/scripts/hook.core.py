"""
Core Lifecycle Hook for `module:vscode-support` (`scripts/hook.core.py`).
Subscribes to `on_env_synced`, `on_reload`, and `on_remove` emitted by `core`.
"""

import os
from typing import Any, Optional, Tuple

from core import uri
from core.log import log


def _get_workspace_projector() -> Tuple[Optional[str], Any]:
    from vscode_support.projector import SettingsProjector

    proj_root = uri.resolve("project://", interactive=False)
    if not proj_root or not os.path.isdir(proj_root):
        return None, None
    return proj_root, SettingsProjector()


def _sync_workspace() -> bool:
    try:
        proj_root, projector = _get_workspace_projector()
        if not proj_root or projector is None:
            return False
        return projector.sync_vscode_settings(proj_root)
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
    """當 `SpaceRegistry` 重載時確保 `vscode-support/gitignore` 空間已註冊。"""
    try:
        registry = ctx.get("registry") if isinstance(ctx, dict) else getattr(ctx, "registry", None)
        if registry is None:
            return False
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
        return projector.revert_vscode_settings(proj_root)
    except Exception as e:
        log(f"[vscode-support:hook] Warning: Failed during on_remove revert: {e}", stream="stderr")
        return False
