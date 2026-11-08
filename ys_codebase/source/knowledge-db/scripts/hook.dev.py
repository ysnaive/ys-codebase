"""
Development and test execution hook for module:knowledge-db.
Provides setup and teardown lifecycle integration for YSCB sandbox testing.
"""

from pathlib import Path
from typing import Any

from core.context import get_runtime_context
from core.log import log_debug


def on_test_setup(context: Any) -> None:
    """
    Called before module test suite execution in the virtual sandbox.
    """
    get_runtime_context().set_module_state("knowledge_db.mock_embedding", True)
    sb_str = getattr(context, "sandbox_dir", None)
    if not sb_str:
        sb_str = getattr(context, "root_dir", getattr(context, "sandbox_path", str(context)))

    sb_path = Path(str(sb_str))
    storage_dir = sb_path / ".storage.local" / "knowledge-db"
    (storage_dir / "indices").mkdir(parents=True, exist_ok=True)
    (storage_dir / "bundles").mkdir(parents=True, exist_ok=True)
    (storage_dir / "models").mkdir(parents=True, exist_ok=True)
    cache_dir = sb_path / ".cache" / "knowledge-db"
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_debug(f"[hook.dev] Prepared knowledge-db storage at: {storage_dir}")


def on_test_teardown(context: Any) -> None:
    """
    Called after module test suite execution finishes in the virtual sandbox.
    """
    get_runtime_context().set_module_state("knowledge_db.mock_embedding", False)
    log_debug(f"[hook.dev] Teardown knowledge-db sandbox for: {context}")
