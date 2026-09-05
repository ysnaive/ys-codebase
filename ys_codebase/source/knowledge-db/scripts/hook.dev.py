"""
Development and test execution hook for module:knowledge-db.
Provides setup and teardown lifecycle integration for YSCB sandbox testing.
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("knowledge-db.hook.dev")


def on_test_setup(context: Any) -> None:
    """
    Called before module test suite execution in the virtual sandbox.
    """
    os.environ["KNOWLEDGE_DB_MOCK_EMBEDDING"] = "1"
    sb_str = getattr(context, "sandbox_dir", None)
    if not sb_str:
        sb_str = getattr(context, "root_dir", getattr(context, "sandbox_path", str(context)))

    sb_path = Path(str(sb_str))
    # Ensure cache and indices scratch directories exist
    cache_dir = sb_path / ".cache" / "knowledge-db"
    (cache_dir / "indices").mkdir(parents=True, exist_ok=True)
    (cache_dir / "bundles").mkdir(parents=True, exist_ok=True)
    (cache_dir / "spaces").mkdir(parents=True, exist_ok=True)
    logger.debug(f"[hook.dev] Prepared knowledge-db cache storage at: {cache_dir}")


def on_test_teardown(context: Any) -> None:
    """
    Called after module test suite execution finishes in the virtual sandbox.
    """
    os.environ.pop("KNOWLEDGE_DB_MOCK_EMBEDDING", None)
    logger.debug(f"[hook.dev] Teardown knowledge-db sandbox for: {context}")

