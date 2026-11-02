"""
Development and Sandbox Test Execution Hook for `module:ast` (`scripts/hook.dev.py`).
"""

import logging
from pathlib import Path
from typing import Any


def on_test_setup(context: Any = None, **kwargs: Any) -> None:
    """Prepare `.cache/ast/{indices,bundles}` inside the sandbox before test execution."""
    sb_str = getattr(context, "sandbox_dir", None)
    if not sb_str and isinstance(context, dict):
        sb_str = context.get("sandbox_dir") or context.get("sandbox_root") or context.get("root_dir")
    if not sb_str:
        sb_str = getattr(context, "root_dir", getattr(context, "sandbox_path", str(context) if context else ""))
    if not sb_str:
        return

    sb_path = Path(str(sb_str))
    cache_dir = sb_path / ".cache" / "ast"
    (cache_dir / "indices").mkdir(parents=True, exist_ok=True)
    (cache_dir / "bundles").mkdir(parents=True, exist_ok=True)
    logging.getLogger("ast.hook.dev").debug("[hook.dev] Prepared ast cache storage at: %s", cache_dir)


def on_test_teardown(context: Any = None, **kwargs: Any) -> None:
    """Clean up temporary state after sandbox test execution."""
    logging.getLogger("ast.hook.dev").debug("[hook.dev] Teardown ast sandbox for: %s", context)
