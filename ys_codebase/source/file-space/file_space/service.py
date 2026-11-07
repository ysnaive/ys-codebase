"""
Deprecated watcher service forwarding layer for the file-space module.
Delegates in-process subscriptions and watcher state queries directly to core.space.watcher.
Never starts a duplicate background watchdog observer.
"""
from typing import Any, Callable, Dict, Iterable, Optional

from core.space.watcher import (
    broadcast_file_space_changed,
    clear_subscribers,
    get_active_watcher,
    is_watcher_active,
    notify_subscribers,
    read_watcher_state,
    register_active_watcher,
    remove_watcher_state,
    resolve_watcher_cache_dir,
    resolve_watcher_dirty_path,
    resolve_watcher_state_path,
    subscribe as _core_subscribe,
    write_watcher_state,
)


def subscribe(
    callback: Callable[[str, Any], Any],
    *,
    spaces: Optional[Iterable[str]] = None,
) -> Callable[[], None]:
    """Delegate subscription registration to core.space.subscribe."""
    return _core_subscribe(callback, spaces=spaces)


def _dispatch_to_subscribers(space_name: str, diff_res: Any) -> None:
    """Delegate in-process subscriber notification to core.space.watcher.notify_subscribers."""
    notify_subscribers(space_name, diff_res)


class FileSpaceWatcherServiceWorker:
    """
    No-op deprecated service worker placeholder.
    Background watching is now handled exclusively by server's core-space-watcher (`CoreSpaceWatcherServiceWorker`).
    """

    def __init__(
        self,
        name: str = "file-space-watcher",
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        _ = kwargs
        self._name = name
        self.context = dict(context) if isinstance(context, dict) else {}
        self._running = False

    @property
    def name(self) -> str:
        return self._name

    def start(self, context: Optional[Dict[str, Any]] = None) -> None:
        if context is not None and isinstance(context, dict):
            self.context.update(context)
        self._running = True

    def stop(self, timeout: float = 5.0) -> None:
        _ = timeout
        self._running = False

    def is_alive(self) -> bool:
        return self._running

    def health_check(self) -> bool:
        return True

    def notify_file_event(self, *args: Any, **kwargs: Any) -> list:
        _ = (args, kwargs)
        return []

    def flush_dirty_spaces(self) -> Dict[str, Any]:
        return {}

    def flush_space_now(self, space_name: Optional[str] = None) -> Any:
        _ = space_name
        return None

    def get_custom_metrics(self) -> Dict[str, Any]:
        return {
            "deprecated": True,
            "deprecated_shell": True,
            "delegated_to": "core-space-watcher",
        }


__all__ = [
    "FileSpaceWatcherServiceWorker",
    "_dispatch_to_subscribers",
    "broadcast_file_space_changed",
    "clear_subscribers",
    "get_active_watcher",
    "is_watcher_active",
    "notify_subscribers",
    "read_watcher_state",
    "register_active_watcher",
    "remove_watcher_state",
    "resolve_watcher_cache_dir",
    "resolve_watcher_dirty_path",
    "resolve_watcher_state_path",
    "subscribe",
    "write_watcher_state",
]
