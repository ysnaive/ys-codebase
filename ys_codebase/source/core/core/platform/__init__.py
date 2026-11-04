"""
Core Platform - Cross-Platform OS & Process Abstraction SDK.
"""

from core.platform import daemon_probe
from core.platform.lock import InterProcessLock, LockAcquisitionError
from core.platform.process import (
    can_spawn_background_daemon,
    is_process_alive,
    kill_process_tree,
    set_process_title,
    spawn_detached,
    terminate_popen_tree,
)
from core.platform.venv import (
    activate_test_module_source_path,
    build_runtime_pythonpath,
    ensure_installed_modules_path,
    ensure_private_venv,
    get_venv_site_packages,
    init_subprocess_sys_path,
    list_installed_module_roots,
    list_module_search_roots,
    restore_sys_path,
)

__all__ = [
    "daemon_probe",
    "can_spawn_background_daemon",
    "spawn_detached",
    "is_process_alive",
    "kill_process_tree",
    "terminate_popen_tree",
    "set_process_title",
    "InterProcessLock",
    "LockAcquisitionError",
    "ensure_private_venv",
    "get_venv_site_packages",
    "list_installed_module_roots",
    "list_module_search_roots",
    "ensure_installed_modules_path",
    "build_runtime_pythonpath",
    "init_subprocess_sys_path",
    "activate_test_module_source_path",
    "restore_sys_path",
]
