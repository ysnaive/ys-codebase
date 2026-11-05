"""
Dev sandbox lifecycle hooks for the file-space module.
"""
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("file_space.hook.dev")


def on_test_setup(context: Any) -> None:
    """
    Prepare isolated storage and cache directories in the sandbox before running tests.
    """
    sb_str = getattr(context, "sandbox_dir", None)
    if not sb_str:
        sb_str = getattr(
            context, "root_dir", getattr(context, "sandbox_path", str(context))
        )
    sb_path = Path(str(sb_str))
    storage_dir = sb_path / ".storage.local" / "file-space"
    (storage_dir / "snapshots").mkdir(parents=True, exist_ok=True)
    (storage_dir / "cursors").mkdir(parents=True, exist_ok=True)
    (storage_dir / "spaces").mkdir(parents=True, exist_ok=True)
    cache_dir = sb_path / ".cache" / "file-space"
    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("[hook.dev] Prepared file-space storage at: %s", storage_dir)


def on_test_teardown(context: Any) -> None:
    """
    Clean up resources after sandbox test suite finishes.
    """
    logger.debug("[hook.dev] Teardown file-space sandbox for: %s", context)
