"""
Server Module - Modules Watcher.

Monitors the .modules/ deployment directory for changes (install/update/rebuild)
and triggers warm worker replacement when changes are detected.
"""

import os
import threading
import time
from typing import Callable, Dict, Optional


class ModulesWatcher:
    """
    Watches the project's .modules/ directory for changes using lightweight
    mtime snapshots, notifying the server master to restart the warm worker.
    """

    def __init__(
        self,
        modules_dir: str,
        on_change_callback: Callable[[], None],
        poll_interval_sec: float = 1.0,
    ) -> None:
        self.modules_dir = os.path.abspath(modules_dir)
        self.on_change_callback = on_change_callback
        self.poll_interval = poll_interval_sec
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._last_snapshot: Dict[str, float] = {}

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
                self._last_snapshot = current_snapshot
                try:
                    self.on_change_callback()
                except Exception:
                    pass

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
