"""
Core Platform - Cross-Platform OS & Process Abstraction SDK.
"""

from core.platform import daemon_probe
from core.platform.lock import InterProcessLock, LockAcquisitionError
from core.platform.process import (
    can_spawn_background_daemon,
    get_host_memory_info,
    get_process_rss_mb,
    is_process_alive,
    kill_process_tree,
    reap_sandbox_processes,
    set_process_title,
    spawn_detached,
    terminate_popen_tree,
    trim_process_memory,
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
    restore_process_env_and_cwd,
    restore_sys_path,
)

__all__ = (
    "daemon_probe",
    "can_spawn_background_daemon",
    "spawn_detached",
    "is_process_alive",
    "kill_process_tree",
    "terminate_popen_tree",
    "set_process_title",
    "get_process_rss_mb",
    "get_host_memory_info",
    "trim_process_memory",
    "reap_sandbox_processes",
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
    "restore_process_env_and_cwd",
    "restore_sys_path",
)
