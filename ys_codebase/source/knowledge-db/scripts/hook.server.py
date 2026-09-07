"""
Server daemon lifecycle hook for module:knowledge-db.
Provides pre-warm hook on server worker warming events.
"""

import logging
import threading
from typing import Any

logger = logging.getLogger("knowledge-db.hook.server")


def on_worker_warming(context: Any) -> str:
    """
    Called when server worker enters warming stage.
    Pre-warms KnowledgeEngine and caches unified index in a background thread.
    """
    def _do_pre_warm():
        try:
            from knowledge_db.engine import KnowledgeEngine
            KnowledgeEngine.pre_warm()
            logger.info("[hook.server] Knowledge-DB pre-warm completed successfully.")
        except Exception as e:
            logger.warning(f"[hook.server] Knowledge-DB pre-warm failed or skipped: {e}")

    threading.Thread(target=_do_pre_warm, daemon=True, name="kdb-prewarm").start()
    return "warming_started"


def on_server_worker_warming(context: Any) -> str:
    """Backward-compatible alias for server_worker_warming."""
    return on_worker_warming(context)
