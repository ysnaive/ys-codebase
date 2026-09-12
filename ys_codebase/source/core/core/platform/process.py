"""
Core Platform - Cross-Platform Process Primitives.

Provides robust process lifecycle primitives (detached spawning, liveness probe,
and process tree termination) across Linux/POSIX and Windows environments.
"""

import errno
import os
import signal
import subprocess
import sys
import time
from typing import Dict, List, Optional


def spawn_detached(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> int:
    """
    Spawns a detached process in background independent of the current terminal/parent process.

    Args:
        cmd: Command arguments list.
        cwd: Optional working directory.
        env: Optional environment variables dictionary.

    Returns:
        int: Process ID (PID) of the spawned detached process.
    """
    current_env = os.environ.copy()
    if env:
        current_env.update(env)

    if sys.platform == "win32":
        creationflags = 0
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creationflags |= subprocess.DETACHED_PROCESS

        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        flags_with_breakaway = creationflags | CREATE_BREAKAWAY_FROM_JOB
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=current_env,
                creationflags=flags_with_breakaway,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=current_env,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
    else:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=current_env,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )

    return proc.pid


def is_process_alive(pid: int) -> bool:
    """
    Probes whether a process with the given PID is currently active and alive.
    Accurately detects terminated/zombie processes.

    Args:
        pid: Process identifier to inspect.

    Returns:
        bool: True if process is active and running, False if terminated or zombie.
    """
    if pid <= 0:
        return False

    if sys.platform == "win32":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return False
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    else:
        # Check /proc/<pid>/status on Linux for Zombie state
        proc_status = f"/proc/{pid}/status"
        if os.path.exists(proc_status):
            try:
                with open(proc_status, "r") as f:
                    for line in f:
                        if line.startswith("State:"):
                            # If state contains 'Z' (zombie) or 'X' (dead), it is not alive
                            parts = line.split()
                            if len(parts) >= 2 and parts[1] in ("Z", "X"):
                                return False
                            break
            except (OSError, IOError):
                return False

        # Try non-blocking waitpid in case it is our direct child
        try:
            wpid, _ = os.waitpid(pid, os.WNOHANG)
            if wpid == pid:
                return False
        except (ChildProcessError, OSError):
            pass

        try:
            os.kill(pid, 0)
            return True
        except OSError as err:
            if err.errno == errno.ESRCH:
                return False
            elif err.errno == errno.EPERM:
                return True
            return False


def kill_process_tree(pid: int, timeout_sec: float = 3.0) -> bool:
    """
    Gracefully and forcefully terminates the specified process and all its child processes.

    Args:
        pid: Root process ID of the tree to kill.
        timeout_sec: Grace period before escalating to SIGKILL (POSIX only).

    Returns:
        bool: True if the process is confirmed terminated, False otherwise.
    """
    if not is_process_alive(pid):
        return True

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            time.sleep(0.1)
            return not is_process_alive(pid)
        except Exception:
            return not is_process_alive(pid)
    else:
        try:
            pgid = os.getpgid(pid)
        except OSError:
            pgid = pid

        try:
            if pgid == pid:
                os.killpg(pgid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

        start_wait = time.time()
        while time.time() - start_wait < timeout_sec:
            # Try reaping if direct child
            try:
                os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pass
            if not is_process_alive(pid):
                return True
            time.sleep(0.05)

        if is_process_alive(pid):
            try:
                if pgid == pid:
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pass
            time.sleep(0.05)

        return not is_process_alive(pid)

