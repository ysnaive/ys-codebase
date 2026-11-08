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
from typing import Any, Dict, List, Optional
from core.context import get_runtime_context


_TRUTHY_ENV_VALUES = ("1", "true", "True")


def _get_can_spawn_cache() -> Optional[bool]:
    if "_CAN_SPAWN_DAEMON_CACHE" in globals():
        return globals()["_CAN_SPAWN_DAEMON_CACHE"]
    return get_runtime_context().process_can_spawn_daemon_cache


def _set_can_spawn_cache(val: Optional[bool]) -> None:
    if "_CAN_SPAWN_DAEMON_CACHE" in globals():
        globals()["_CAN_SPAWN_DAEMON_CACHE"] = val
    get_runtime_context().process_can_spawn_daemon_cache = val


def can_spawn_background_daemon(force_reprobe: bool = False, yscb_root: Optional[str] = None) -> bool:
    """
    Probes whether the current execution environment allows spawning a persistent
    background daemon process detached from the parent process group / Job Object.

    Decision order:
        1. ``YSCB_FORCE_DAEMON=1`` -> True (explicit override, bypasses all probes).
        2. ``YSCB_NO_DAEMON=1`` -> False.
        3. Windows: Job Object breakaway probe (cached per process).
        4. POSIX: empirical reaping detection via ``core.platform.daemon_probe``
           when ``yscb_root`` is given (not cached, daemon state changes); True otherwise.

    Args:
        force_reprobe: If True, bypasses the in-memory cache and re-probes the environment.
        yscb_root: Absolute yscb root used to locate the spawn probe record (POSIX only).

    Returns:
        bool: True if background daemon spawning is supported, False otherwise.
    """
    if os.environ.get("YSCB_FORCE_DAEMON") in _TRUTHY_ENV_VALUES:
        return True

    if os.environ.get("YSCB_NO_DAEMON") in _TRUTHY_ENV_VALUES:
        return False

    if sys.platform != "win32":
        if not yscb_root:
            return True
        from core.platform import daemon_probe
        # Daemon liveness (daemon.json / daemon.lock) is probed lazily inside, only when needed
        return not daemon_probe.is_reaping_env(yscb_root)

    cached = _get_can_spawn_cache()
    if cached is not None and not force_reprobe:
        return cached

    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        k32.IsProcessInJob.restype = wintypes.BOOL

        in_job = wintypes.BOOL(0)
        res = k32.IsProcessInJob(k32.GetCurrentProcess(), None, ctypes.byref(in_job))
        if res and not bool(in_job.value):
            _set_can_spawn_cache(True)
            return True

        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        creationflags = 0
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creationflags |= subprocess.DETACHED_PROCESS
        flags_with_breakaway = creationflags | CREATE_BREAKAWAY_FROM_JOB

        try:
            probe_proc = subprocess.Popen(
                [sys.executable, "-c", "pass"],
                creationflags=flags_with_breakaway,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
            probe_proc.wait(timeout=2.0)
            _set_can_spawn_cache(True)
            return True
        except OSError:
            _set_can_spawn_cache(False)
            return False
    except Exception:
        _set_can_spawn_cache(False)
        return False


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
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags |= subprocess.CREATE_NO_WINDOW

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

    proc._child_created = False
    return proc.pid


def set_process_title(title: str) -> bool:
    """
    Sets the human-readable process title/name in a cross-platform manner.

    Supports:
    - setproctitle module (Linux/macOS/Windows, if installed)
    - Linux native prctl(PR_SET_NAME) via ctypes (standard library)
    - macOS / BSD native libc setprogname via ctypes (standard library)
    - Windows SetConsoleTitleW via ctypes (standard library)

    Args:
        title: Target process title (e.g. 'yscb server', 'yscb server: worker').

    Returns:
        bool: True if at least one naming mechanism succeeded, False otherwise.
    """
    success = False

    # 1. Try setproctitle if available
    try:
        import setproctitle
        setproctitle.setproctitle(title)
        success = True
    except Exception:
        pass

    # 2. Linux native prctl(PR_SET_NAME)
    if sys.platform.startswith("linux"):
        try:
            import ctypes
            import ctypes.util
            libc_name = ctypes.util.find_library("c") or "libc.so.6"
            libc = ctypes.CDLL(libc_name)
            PR_SET_NAME = 15
            byte_name = title.encode("utf-8")[:15]
            if libc.prctl(PR_SET_NAME, ctypes.c_char_p(byte_name), 0, 0, 0) == 0:
                success = True
        except Exception:
            pass

    # 3. macOS / BSD native setprogname
    elif sys.platform == "darwin" or "bsd" in sys.platform:
        try:
            import ctypes
            import ctypes.util
            libc_name = ctypes.util.find_library("c")
            if libc_name:
                libc = ctypes.CDLL(libc_name)
                if hasattr(libc, "setprogname"):
                    libc.setprogname(ctypes.c_char_p(title.encode("utf-8")))
                    success = True
        except Exception:
            pass

    # 4. Windows console title
    elif sys.platform == "win32":
        try:
            import ctypes
            if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "kernel32"):
                ctypes.windll.kernel32.SetConsoleTitleW(str(title))
                success = True
        except Exception:
            pass

    return success


def is_process_alive(pid: int) -> bool:
    """
    Probes whether a process with the given PID is currently active and alive.
    Accurately detects terminated/zombie processes.

    Args:
        pid: Process identifier to inspect.

    Returns:
        bool: True if process is active and running, False if terminated or zombie.
    """
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL

            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            try:
                exit_code = wintypes.DWORD()
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
            if not os.path.exists(proc_status):
                try:
                    res = subprocess.run(
                        ["ps", "-o", "stat=", "-p", str(pid)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        timeout=1.0,
                        check=False,
                    )
                    if res.returncode == 0:
                        stat_str = (res.stdout or "").strip().upper()
                        if stat_str.startswith(("Z", "X")):
                            return False
                except Exception:
                    pass
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
                timeout=max(1.0, float(timeout_sec)),
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


def terminate_popen_tree(proc: subprocess.Popen, timeout_sec: float = 2.0) -> bool:
    """
    Terminates a child ``Popen`` process (and its process group on POSIX) while
    letting ``Popen`` itself reap the exit status (avoids ``waitpid`` races with
    ``is_process_alive``).

    POSIX: SIGTERM to the process group (the child must be started with
    ``start_new_session=True``) -> ``proc.wait(timeout)`` -> SIGKILL -> ``proc.wait``.
    Windows: ``taskkill /T /F`` -> ``proc.wait``.

    Args:
        proc: Child process handle.
        timeout_sec: Grace period before escalating to a forced kill.

    Returns:
        bool: True if the process is confirmed terminated, False otherwise.
    """
    if proc.poll() is not None:
        return True

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(1.0, float(timeout_sec)),
                check=False,
            )
        except Exception:
            pass
        try:
            proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                return False
        return True

    def _signal_group(sig: int) -> None:
        try:
            pgid = os.getpgid(proc.pid)
        except OSError:
            return
        try:
            if pgid == proc.pid:
                os.killpg(pgid, sig)
            else:
                os.kill(proc.pid, sig)
        except OSError as err:
            if err.errno != errno.ESRCH:
                raise

    _signal_group(signal.SIGTERM)
    try:
        proc.wait(timeout=timeout_sec)
        return True
    except subprocess.TimeoutExpired:
        pass

    _signal_group(signal.SIGKILL)
    try:
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return False
    return True


def __getattr__(name: str) -> Any:
    """PEP 562 backward-compatible attribute delegation to active `RuntimeContext`."""
    if name == "_CAN_SPAWN_DAEMON_CACHE":
        return _get_can_spawn_cache()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
