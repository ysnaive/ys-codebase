"""
Core Platform - Cross-Platform OS & Process Abstraction SDK.
"""

from core.platform.lock import InterProcessLock, LockAcquisitionError
from core.platform.process import (
    can_spawn_background_daemon,
    is_process_alive,
    kill_process_tree,
    set_process_title,
    spawn_detached,
)
from core.platform.venv import ensure_private_venv

__all__ = [
    "can_spawn_background_daemon",
    "spawn_detached",
    "is_process_alive",
    "kill_process_tree",
    "set_process_title",
    "InterProcessLock",
    "LockAcquisitionError",
    "ensure_private_venv",
]
