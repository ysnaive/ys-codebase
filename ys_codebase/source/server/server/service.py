"""
Server Module - Service Worker Base & Lifecycle Manager.

Provides abstract interface BaseServiceWorker for domain background tasks
(such as knowledge-db file watcher) and unifies their lifecycle to follow
the server's idle TTL and shutdown policy.
"""

from abc import ABC, abstractmethod
import importlib
import json
import logging
import os
import sys
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
        name: Optional[str] = None,
        provider: str = "core",
        description: str = "",
        auto_start: bool = True,
    ) -> None:
        with self._lock:
            key = name or worker.name
            self._services[key] = worker
            self._metadata[key] = {
                "provider": provider,
                "description": description,
                "auto_start": bool(auto_start),
            }

    def load_from_contributes(self, yscb_root: str) -> None:
        """
        Dynamically loads and registers services declared in contributes/server.json across modules.
        Prioritizes aggregated registry from core.contributes.get('server', 'services').
        """
        try:
            services_data = None
            try:
                from core import contributes
                services_data = contributes.get("server", "services", default=None)
            except Exception:
                services_data = None

            if isinstance(services_data, list) and services_data:
                for item in services_data:
                    provider = item.get("__provider__") or item.get("_provider") or item.get("provider") or "unknown"
                    self._load_service_item(item, provider=provider, yscb_root=yscb_root)
                return

            # Fallback to scanning .modules/*/contributes/server.json if contributes cache unavailable
            modules_dir = os.path.join(yscb_root, ".modules")
            if os.path.isdir(modules_dir):
                for mod_name in sorted(os.listdir(modules_dir)):
                    srv_json = os.path.join(modules_dir, mod_name, "contributes", "server.json")
                    if os.path.isfile(srv_json):
                        try:
                            with open(srv_json, "r", encoding="utf-8") as f:
                                sdata = json.load(f)
                                for item in sdata.get("services", []):
                                    self._load_service_item(item, provider=mod_name, yscb_root=yscb_root)
                        except Exception as ex:
                            logging.warning(f"[Server Service] Error reading {srv_json}: {ex}")
        except Exception as e:
            logging.warning(f"[Server Service] Failed to load contributes services: {e}")

    def _load_service_item(self, item: Dict[str, Any], provider: str = "unknown", yscb_root: Optional[str] = None) -> None:
        worker_cls_str = item.get("worker_class") or item.get("entry")
        if not worker_cls_str or not isinstance(worker_cls_str, str):
            return

        service_name = item.get("name") or item.get("id") or "unnamed_service"
        auto_start = item.get("auto_start", True)

        # Dynamic path injection for provider module under .modules/<provider>
        if yscb_root and provider and provider != "unknown":
            prov_dir = os.path.join(yscb_root, ".modules", provider)
            if prov_dir not in sys.path:
                sys.path.insert(0, prov_dir)

        try:
            raw_str = worker_cls_str
            for prefix in ("code.class://", "code.func://"):
                if raw_str.startswith(prefix):
                    raw_str = raw_str[len(prefix):]
                    break

            if ":" in raw_str:
                mod_path, cls_name = raw_str.split(":", 1)
            elif "." in raw_str:
                mod_path, cls_name = raw_str.rsplit(".", 1)
            else:
                return

            # Normalize hyphenated module prefix in path (e.g. knowledge-db/service -> knowledge_db.service)
            mod_path = mod_path.replace("/", ".")
            if "." in mod_path:
                first_seg, rest = mod_path.split(".", 1)
                mod_path = f"{first_seg.replace('-', '_')}.{rest}"
            else:
                mod_path = mod_path.replace("-", "_")

            # Try to import directly first; if not found and prefixed by provider, attempt stripping provider prefix
            try:
                mod = importlib.import_module(mod_path)
            except ModuleNotFoundError:
                stripped = False
                if provider and provider != "unknown":
                    prov_norm = f"{provider.replace('-', '_')}."
                    if mod_path.startswith(prov_norm):
                        candidate_path = mod_path[len(prov_norm):]
                        try:
                            mod = importlib.import_module(candidate_path)
                            mod_path = candidate_path
                            stripped = True
                        except ModuleNotFoundError:
                            pass
                if not stripped:
                    raise
            cls_obj = getattr(mod, cls_name)
            instance = cls_obj()
            self.register(
                instance,
                name=service_name,
                provider=provider,
                description=item.get("description", ""),
                auto_start=bool(auto_start),
            )
        except Exception as e:
            logging.error(f"[Server Service] Failed to instantiate service '{service_name}': {e}")

    def start_all(self, context: Dict[str, Any]) -> None:
        with self._lock:
            for name, worker in self._services.items():
                meta = self._metadata.get(name, {})
                if not meta.get("auto_start", True):
                    continue
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
