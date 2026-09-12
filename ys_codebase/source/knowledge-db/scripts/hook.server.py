"""
Server daemon lifecycle hook for module:knowledge-db.
Provides pre-warm hook on server worker warming events and hosts background watcher.
"""

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger("knowledge-db.hook.server")

_watcher_instance: Optional[Any] = None
_watcher_lock = threading.Lock()


def on_worker_warming(context: Any) -> str:
    """
    Called when server worker enters warming stage.
    Pre-warms KnowledgeEngine and launches background watcher in the Worker process.
    """
    def _do_pre_warm():
        global _watcher_instance
        try:
            from knowledge_db.engine import KnowledgeEngine, get_engine
            KnowledgeEngine.pre_warm()
            logger.info("[hook.server] Knowledge-DB pre-warm completed successfully.")
        except Exception as e:
            logger.warning(f"[hook.server] Knowledge-DB pre-warm failed or skipped: {e}")

        try:
            with _watcher_lock:
                if _watcher_instance is None:
                    from knowledge_db.service import KnowledgeDBServiceWorker
                    root = None
                    if isinstance(context, dict):
                        root = context.get("yscb_root") or context.get("workspace_root")
                    _watcher_instance = KnowledgeDBServiceWorker(workspace_root=root)
                    _watcher_instance.start({"yscb_root": str(root) if root else ""})
                    logger.info("[hook.server] KnowledgeDBServiceWorker started in Worker process.")
        except Exception as e:
            logger.warning(f"[hook.server] Failed to start KnowledgeDBServiceWorker: {e}")

    threading.Thread(target=_do_pre_warm, daemon=True, name="kdb-prewarm").start()
    return "warming_started"


def on_server_worker_warming(context: Any) -> str:
    """Backward-compatible alias for server_worker_warming."""
    return on_worker_warming(context)

