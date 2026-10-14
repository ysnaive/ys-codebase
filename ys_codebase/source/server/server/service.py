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
        """
        Starts background work in a thread or subprocess.

        Args:
            context: Server daemon execution context dictionary containing:
                - "yscb_root" (str): Absolute path to the YSCB project root directory.
                - "workspace_root" (str, optional): Host workspace root directory.
                - "config" (dict, optional): Server and module configuration dict.
        """
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
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register(
        self,
        worker: BaseServiceWorker,
        provider: str = "core",
        description: str = "",
    ) -> None:
        with self._lock:
            self._services[worker.name] = worker
            self._metadata[worker.name] = {
                "provider": provider,
                "description": description,
            }

    def load_from_contributes(self, yscb_root: str) -> None:
        """
        Dynamically loads and registers services declared in contributes/server.json across modules.
        """
        try:
            import json
            modules_dir = os.path.join(yscb_root, ".modules")
            if os.path.isdir(modules_dir):
                for mod_name in sorted(os.listdir(modules_dir)):
                    srv_json = os.path.join(modules_dir, mod_name, "contributes", "server.json")
                    if os.path.isfile(srv_json):
                        try:
                            with open(srv_json, "r", encoding="utf-8") as f:
                                sdata = json.load(f)
                                for item in sdata.get("services", []):
                                    self._load_service_item(item, provider=mod_name)
                        except Exception as ex:
                            logging.warning(f"[Server Service] Error reading {srv_json}: {ex}")
        except Exception as e:
            logging.warning(f"[Server Service] Failed to load contributes services: {e}")

    def _load_service_item(self, item: Dict[str, Any], provider: str = "unknown") -> None:
        worker_cls_str = item.get("worker_class")
        if not worker_cls_str or not isinstance(worker_cls_str, str):
            return
        try:
            import importlib
            if ":" in worker_cls_str:
                mod_path, cls_name = worker_cls_str.split(":", 1)
            elif "." in worker_cls_str:
                mod_path, cls_name = worker_cls_str.rsplit(".", 1)
            else:
                return
            mod = importlib.import_module(mod_path)
            cls_obj = getattr(mod, cls_name)
            instance = cls_obj()
            self.register(instance, provider=provider, description=item.get("description", ""))
        except Exception as e:
            logging.error(f"[Server Service] Failed to instantiate service '{item.get('name')}': {e}")

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
                meta = self._metadata.get(name, {})
                try:
                    alive = worker.health_check()
                except Exception:
                    alive = False
                status_list.append({
                    "name": name,
                    "provider": meta.get("provider", "unknown"),
                    "description": meta.get("description", ""),
                    "alive": alive,
                })
        return status_list
