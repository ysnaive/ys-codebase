"""
Server Module - Service Worker Base & Lifecycle Manager.

Provides abstract interface BaseServiceWorker for domain background tasks
(such as knowledge-db file watcher) and unifies their lifecycle to follow
the server's idle TTL and shutdown policy.
"""

from abc import ABC, abstractmethod
import logging
import threading
import time
from typing import Any, Dict, List, Optional


class BaseServiceWorker(ABC):
    """
    Abstract base class for domain background service workers.

    Lifecycle Iron Rule:
    Service workers MUST strictly follow the server daemon's lifecycle.
    They share the server's idle TTL and are gracefully terminated upon
    server shutdown. They MUST NOT persist independently.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique service worker identifier (e.g. 'knowledge-db-watcher')."""
        pass

    @abstractmethod
    def start(self, context: Dict[str, Any]) -> None:
        """Starts background work in a thread or subprocess."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Gracefully shuts down the service worker and releases resources."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Probes whether the background service is running healthy."""
        pass


class ServiceManager:
    """Manages registered background service workers and synchronizes their lifecycle."""

    def __init__(self) -> None:
        self._services: Dict[str, BaseServiceWorker] = {}
        self._lock = threading.Lock()

    def register(self, worker: BaseServiceWorker) -> None:
        with self._lock:
            self._services[worker.name] = worker

    def start_all(self, context: Dict[str, Any]) -> None:
        with self._lock:
            for name, worker in self._services.items():
                try:
                    worker.start(context)
                except Exception as e:
                    logging.error(f"[Server Service] Failed to start worker '{name}': {e}")

    def stop_all(self, timeout_sec: float = 2.0) -> None:
        with self._lock:
            for name, worker in self._services.items():
                try:
                    worker.stop()
                except Exception as e:
                    logging.error(f"[Server Service] Failed to stop worker '{name}': {e}")

    def get_status(self) -> List[Dict[str, Any]]:
        status_list: List[Dict[str, Any]] = []
        with self._lock:
            for name, worker in self._services.items():
                try:
                    alive = worker.health_check()
                except Exception:
                    alive = False
                status_list.append({"name": name, "alive": alive})
        return status_list
