"""
Server Module - Modules Watcher.

Monitors the .modules/ deployment directory for changes (install/update/rebuild)
and triggers warm worker replacement when changes are detected.
"""

import os
import threading
import time
from typing import Callable, Dict, Optional, Set

from core.platform import InterProcessLock


def _scan_modules_dir(modules_dir: str) -> Dict[str, float]:
    """Scans .modules directory and returns a mapping of watched file paths to their modification timestamps."""
    snapshot: Dict[str, float] = {}
    if not os.path.exists(modules_dir):
        return snapshot

    try:
        for root, _, files in os.walk(modules_dir):
            for f in files:
                if f.endswith((".py", ".json", ".zip", ".dist-info")):
                    p = os.path.join(root, f)
                    try:
                        snapshot[p] = os.path.getmtime(p)
                    except OSError:
                        pass
    except OSError:
        pass

    return snapshot


class ModulesWatcher:
    """
    Watches the project's .modules/ directory for changes using lightweight
    mtime snapshots, notifying the server master to reload worker or restart server.
    """

    def __init__(
        self,
        modules_dir: str,
        on_change_callback: Callable[[Set[str]], None],
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
        self._last_snapshot = _scan_modules_dir(self.modules_dir)
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="modules-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _is_core_transaction_locked(self) -> bool:
        """
        Checks whether core is currently executing an install/update/reload transaction
        by probing <yscb_root>/.cache/.yscb.lock non-blockingly, or if .modules/core
        is mid-transition without manifest.json.
        """
        yscb_root = os.path.dirname(self.modules_dir)
        lock_file = os.path.join(yscb_root, ".cache", ".yscb.lock")
        if os.path.isfile(lock_file):
            probe = InterProcessLock(lock_file)
            if not probe.acquire(blocking=False):
                return True
            probe.release()

        core_mod_dir = os.path.join(self.modules_dir, "core")
        if os.path.isdir(core_mod_dir) and not os.path.isfile(os.path.join(core_mod_dir, "manifest.json")):
            return True

        return False

    def _poll_loop(self) -> None:
        while self._is_running:
            time.sleep(self.poll_interval)
            if not self._is_running:
                break

            if self._is_core_transaction_locked():
                continue

            current_snapshot = _scan_modules_dir(self.modules_dir)
            if self._last_snapshot != current_snapshot:
                if self.debounce_sec > 0:
                    time.sleep(self.debounce_sec)
                    if not self._is_running or self._is_core_transaction_locked():
                        continue
                    current_snapshot = _scan_modules_dir(self.modules_dir)

                affected_modules = self._extract_affected_modules(self._last_snapshot, current_snapshot)
                self._last_snapshot = current_snapshot
                if not affected_modules:
                    continue
                try:
                    self.on_change_callback(affected_modules)
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
