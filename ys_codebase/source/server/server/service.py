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
import threading
import time
import urllib.request
from typing import Any, Dict, List, Optional

from core.platform import ensure_installed_modules_path

_LAST_TOUCH_TS: float = 0.0
_LAST_TOUCH_BY_ROOT: Dict[str, float] = {}
_TOUCH_MIN_INTERVAL_SEC: float = 1.0
_TOUCH_LOCK = threading.Lock()


def _resolve_service_root(yscb_root: Optional[str]) -> str:
    """Resolves the active YSCB root directory for daemon state lookup."""
    if yscb_root:
        return yscb_root
    try:
        from core import uri

        resolved_root = uri.resolve("yscb://", interactive=False)
        if resolved_root:
            return resolved_root
    except Exception:
        pass
    cand = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.isdir(os.path.join(cand, ".cache")):
        return cand
    return os.environ.get("YSCB_HOST_DIR", os.getcwd())


def touch_activity(
    yscb_root: Optional[str] = None,
    *,
    source: str = "sdk",
    force: bool = False,
) -> bool:
    """
    Refresh the running Server daemon's idle timeout timer (non-CLI keepalive probe SDK).

    Reads `.cache/server/daemon.json` and sends an authenticated `POST /api/touch`
    (debounced to at most once per 1.0s unless `force=True`) to the MasterSupervisor so
    background workers (`file-space-watcher`, `knowledge-db-worker`, `gdrive-sync`) and
    external SDK callers keep the server alive without corrupting the worker stdout pipe.

    Returns True if the activity timestamp was refreshed (or throttled within 1s), False if no
    active daemon was reachable.
    """
    global _LAST_TOUCH_TS
    now = time.monotonic()
    resolved_root = _resolve_service_root(yscb_root)
    root_key = os.path.normcase(os.path.abspath(resolved_root))
    if not force:
        with _TOUCH_LOCK:
            last_ts = (
                0.0
                if (_LAST_TOUCH_TS == 0.0 and not _LAST_TOUCH_BY_ROOT)
                else _LAST_TOUCH_BY_ROOT.get(root_key, 0.0)
            )
            if last_ts > 0.0 and (now - last_ts) < _TOUCH_MIN_INTERVAL_SEC:
                return True

    state_file = os.path.join(resolved_root, ".cache", "server", "daemon.json")
    if not os.path.isfile(state_file):
        return False
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        port = int(state.get("port", 0) or 0)
        token = str(state.get("token", "") or "")
        if port <= 0 or not token:
            return False
        url = f"http://127.0.0.1:{port}/api/touch"
        body = json.dumps({"source": source}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status != 200:
                return False
        with _TOUCH_LOCK:
            _LAST_TOUCH_TS = now
            _LAST_TOUCH_BY_ROOT[root_key] = now
        return True
    except Exception:
        return False


def _load_service_class_from_uri(uri_str: str, provider: str = "unknown") -> Optional[type]:
    """Resolves and imports a service worker class from a 'code.class://' or dotted URI string."""
    raw_str = uri_str
    if raw_str.startswith("code.class://"):
        raw_str = raw_str[len("code.class://"):]

    if ":" in raw_str:
        mod_path, cls_name = raw_str.split(":", 1)
    elif "." in raw_str:
        mod_path, cls_name = raw_str.rsplit(".", 1)
    else:
        return None

    mod_path = mod_path.replace("/", ".")
    if "." in mod_path:
        first_seg, rest = mod_path.split(".", 1)
        mod_path = f"{first_seg.replace('-', '_')}.{rest}"
    else:
        mod_path = mod_path.replace("-", "_")

    try:
        mod = importlib.import_module(mod_path)
    except ModuleNotFoundError:
        if provider and provider != "unknown":
            prov_norm = f"{provider.replace('-', '_')}."
            if mod_path.startswith(prov_norm):
                candidate_path = mod_path[len(prov_norm):]
                mod = importlib.import_module(candidate_path)
                return getattr(mod, cls_name)
        raise
    return getattr(mod, cls_name)


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

    def touch_activity(self) -> bool:
        """Notify the server supervisor that this background worker is actively processing work."""
        return touch_activity(source=self.name)


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
                    provider = item.get("__provider__") or item.get("_provider") or "unknown"
                    self._load_service_item(item, provider=provider, yscb_root=yscb_root)
                return

            modules_dir = os.path.join(yscb_root, ".modules")
            if not os.path.isdir(modules_dir):
                return
            for mod_name in sorted(os.listdir(modules_dir)):
                srv_json = os.path.join(modules_dir, mod_name, "contributes", "server.json")
                if not os.path.isfile(srv_json):
                    continue
                try:
                    with open(srv_json, "r", encoding="utf-8") as f:
                        sdata = json.load(f)
                    for item in sdata.get("services", []):
                        self._load_service_item(item, provider=mod_name, yscb_root=yscb_root)
                except (OSError, ValueError) as ex:
                    logging.warning(f"[Server Service] Error reading {srv_json}: {ex}")
        except Exception as e:
            logging.warning(f"[Server Service] Failed to load contributes services: {e}")

    def _load_service_item(self, item: Dict[str, Any], provider: str = "unknown", yscb_root: Optional[str] = None) -> None:
        worker_cls_str = item.get("worker_class")
        if not worker_cls_str or not isinstance(worker_cls_str, str):
            return

        service_name = item.get("name") or "unnamed_service"
        auto_start = item.get("auto_start", True)

        if yscb_root and provider and provider != "unknown":
            ensure_installed_modules_path(yscb_root=yscb_root, priority_module=provider)

        try:
            cls_obj = _load_service_class_from_uri(worker_cls_str, provider=provider)
            if cls_obj is None:
                return
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

    def stop_all(self) -> None:
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
