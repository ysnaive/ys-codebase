"""
Core Lifecycle Hook for `module:vscode-support` (`scripts/hook.core.py`).
Subscribes to `on_env_synced`, `on_reload`, and `on_remove` emitted by `core`.
"""

import os
import sys
from typing import Any, Optional, Tuple

from core import uri


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
        print(f"[vscode-support:hook] Warning: Failed to sync VS Code workspace: {e}", file=sys.stderr)
        return False


def on_env_synced(ctx: Any = None) -> bool:
    """當 `core` 完成微環境 `pip_dependencies` 同步後自動更新穩定連結、Schema 與 `.vscode/settings.json`。"""
    return _sync_workspace()


def on_reload(ctx: Any = None) -> bool:
    """當 `core` 重載模組與擴充點後自動同步 Schema 與 `.vscode/settings.json`。"""
    return _sync_workspace()


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
        print(f"[vscode-support:hook] Warning: Failed during on_remove revert: {e}", file=sys.stderr)
        return False
