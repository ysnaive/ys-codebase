"""
Core Lifecycle Hook for `module:vscode-support` (`scripts/hook.core.py`).
Subscribes to `on_env_synced`, `on_reload`, and `on_remove` emitted by `core`.
"""

import os
import sys
from typing import Any

from core import uri


def _sync_workspace() -> bool:
    try:
        from vscode_support.projector import SettingsProjector

        proj_root = uri.resolve("project://", interactive=False)
        if not proj_root or not os.path.isdir(proj_root):
            return False
        projector = SettingsProjector()
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
    """當移除目標包含 `vscode-support` 時，100% 乾淨還原 `.vscode/settings.json` 並清除 `.vscode/schemas/` 與穩定連結。"""
    try:
        targets = getattr(ctx, "args", None) if ctx is not None else None
        if isinstance(targets, (list, tuple)) and "vscode-support" not in targets:
            return False
        from vscode_support.projector import SettingsProjector

        proj_root = uri.resolve("project://", interactive=False)
        if not proj_root or not os.path.isdir(proj_root):
            return False
        projector = SettingsProjector()
        return projector.revert_vscode_settings(proj_root)
    except Exception as e:
        print(f"[vscode-support:hook] Warning: Failed during on_remove revert: {e}", file=sys.stderr)
        return False

