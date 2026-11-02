"""
Server daemon lifecycle hooks for the file-space module.
"""
import logging
import threading
from typing import Any

logger = logging.getLogger("file_space.hook.server")


def on_worker_warming(context: Any) -> str:
    """
    Pre-warm initial file-space snapshots in a background thread when server worker starts warming.
    """

    def _do_pre_warm() -> None:
        try:
            import file_space

            file_space.refresh(background=True)
            logger.info("[hook.server] File-Space snapshot pre-warm completed.")
        except Exception as exc:
            logger.warning(
                "[hook.server] File-Space snapshot pre-warm skipped: %s", exc
            )

    threading.Thread(
        target=_do_pre_warm, daemon=True, name="file-space-prewarm"
    ).start()
    return "warming_started"


def on_server_worker_warming(context: Any) -> str:
    """Standard event entry point matching events.broadcast('server_worker_warming')."""
    return on_worker_warming(context)

