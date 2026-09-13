"""
Server Module - Modules Watcher.

Monitors the .modules/ deployment directory for changes (install/update/rebuild)
and triggers warm worker replacement when changes are detected.
"""

import inspect
import os
import threading
import time
from typing import Any, Callable, Dict, Optional, Set


class ModulesWatcher:
    """
    Watches the project's .modules/ directory for changes using lightweight
    mtime snapshots, notifying the server master to reload worker or restart server.
    """

    def __init__(
        self,
        modules_dir: str,
        on_change_callback: Callable[..., None],
        poll_interval_sec: float = 1.0,
        debounce_sec: float = 0.0,
    ) -> None:
        self.modules_dir = os.path.abspath(modules_dir)
        self.on_change_callback = on_change_callback
        self.poll_interval = poll_interval_sec
        self.debounce_sec = debounce_sec
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._last_snapshot: Dict[str, float] = {}

    @property
    def is_running(self) -> bool:
        """Return whether the watcher thread is currently running."""
        return self._is_running

    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._last_snapshot = self._take_snapshot()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="modules-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _poll_loop(self) -> None:
        while self._is_running:
            time.sleep(self.poll_interval)
            if not self._is_running:
                break

            current_snapshot = self._take_snapshot()
            if self._has_changed(self._last_snapshot, current_snapshot):
                # Debounce stabilization
                if self.debounce_sec > 0:
                    time.sleep(self.debounce_sec)
                    current_snapshot = self._take_snapshot()

                affected_modules = self._extract_affected_modules(self._last_snapshot, current_snapshot)
                self._last_snapshot = current_snapshot
                try:
                    self._notify_change(affected_modules)
                except Exception:
                    pass

    def _extract_affected_modules(self, prev: Dict[str, float], curr: Dict[str, float]) -> Set[str]:
        """
        Extract top-level module directory names under modules_dir for any added,
        modified, or deleted files.
        """
        changed_paths = {p for p, mtime in curr.items() if prev.get(p) != mtime} | (set(prev.keys()) - set(curr.keys()))
        affected: Set[str] = set()
        for p in changed_paths:
            try:
                rel = os.path.relpath(p, self.modules_dir)
                parts = rel.split(os.sep)
                if parts and parts[0] and parts[0] != "." and not parts[0].startswith("."):
                    affected.add(parts[0])
            except (ValueError, OSError):
                pass
        return affected

    def _notify_change(self, affected_modules: Set[str]) -> None:
        """Invokes on_change_callback with affected_modules if supported, else zero-args."""
        try:
            sig = inspect.signature(self.on_change_callback)
            if len(sig.parameters) > 0:
                self.on_change_callback(affected_modules)
                return
        except (TypeError, ValueError):
            pass

        try:
            self.on_change_callback(affected_modules)
        except TypeError:
            self.on_change_callback()

    def _take_snapshot(self) -> Dict[str, float]:
        snapshot: Dict[str, float] = {}
        if not os.path.exists(self.modules_dir):
            return snapshot

        try:
            # Snapshot top-level manifests and zip timestamps under .modules
            for root, dirs, files in os.walk(self.modules_dir):
                for f in files:
                    if f.endswith((".py", ".json", ".zip", ".dist-info")):
                        p = os.path.join(root, f)
                        try:
                            snapshot[p] = os.path.getmtime(p)
                        except OSError:
                            pass
        except Exception:
            pass

        return snapshot

    def _has_changed(self, prev: Dict[str, float], curr: Dict[str, float]) -> bool:
        if set(prev.keys()) != set(curr.keys()):
            return True
        for k, v in curr.items():
            if prev.get(k) != v:
                return True
        return False
