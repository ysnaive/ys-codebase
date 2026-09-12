"""
Core Platform - Cross-Platform OS & Process Abstraction SDK.
"""

from core.platform.lock import InterProcessLock, LockAcquisitionError
from core.platform.process import is_process_alive, kill_process_tree, set_process_title, spawn_detached
from core.platform.venv import ensure_private_venv

__all__ = [
    "spawn_detached",
    "is_process_alive",
    "kill_process_tree",
    "set_process_title",
    "InterProcessLock",
    "LockAcquisitionError",
    "ensure_private_venv",
]
