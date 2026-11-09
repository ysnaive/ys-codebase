"""
Core Platform - Cross-Platform Process Primitives.

Provides robust process lifecycle primitives (detached spawning, liveness probe,
and process tree termination) across Linux/POSIX and Windows environments.
"""

import errno
import gc
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from core.context import get_env, get_env_snapshot, get_runtime_context


_TRUTHY_ENV_VALUES = ("1", "true", "True")
_TRIM_STATE_KEY = "core.platform.process.last_trim_ts"


def _close_popen_pipes(proc: Optional[subprocess.Popen]) -> None:
    """Deterministically closes any open stdin/stdout/stderr pipes on a `Popen` instance."""
    if proc is None:
        return
    for stream_name in ("stdin", "stdout", "stderr"):
        stream_obj = getattr(proc, stream_name, None)
        if stream_obj is not None:
            try:
                stream_obj.close()
            except Exception:
                pass


def _get_can_spawn_cache() -> Optional[bool]:
    return get_runtime_context().process_can_spawn_daemon_cache


def _set_can_spawn_cache(val: Optional[bool]) -> None:
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
    if get_env("YSCB_FORCE_DAEMON") in _TRUTHY_ENV_VALUES:
        return True

    if get_env("YSCB_NO_DAEMON") in _TRUTHY_ENV_VALUES:
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

        probe_proc: Optional[subprocess.Popen] = None
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
        finally:
            if probe_proc is not None:
                _close_popen_pipes(probe_proc)
                if probe_proc.poll() is None:
                    try:
                        probe_proc.kill()
                        probe_proc.wait(timeout=0.5)
                    except Exception:
                        pass
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
    current_env = dict(get_env_snapshot())
    if env:
        current_env.update(env)

    proc: Optional[subprocess.Popen] = None
    try:
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
    finally:
        _close_popen_pipes(proc)


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
        if os.path.isdir("/proc"):
            if not os.path.exists(proc_status):
                return False
            try:
                with open(proc_status, "r", encoding="utf-8", errors="replace") as f:
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


def _collect_posix_descendants(root_pid: int) -> Tuple[Set[int], Set[int]]:
    """
    Recursively collect all descendant PIDs and their PGIDs starting from ``root_pid``
    on Linux/POSIX by scanning ``/proc/<pid>/task/*/children`` and ``/proc/*/stat`` (PPID).
    Penetrates ``setsid()`` (``start_new_session=True``) boundaries so detached grandchild
    processes are never orphaned.
    """
    if root_pid <= 0 or sys.platform == "win32":
        return set(), set()

    children_map: Dict[int, Set[int]] = {}
    if os.path.isdir("/proc"):
        try:
            with os.scandir("/proc") as proc_it:
                for entry in proc_it:
                    if not entry.name.isdigit():
                        continue
                    cpid = int(entry.name)
                    # Fast path 1: /proc/<cpid>/stat PPID
                    stat_file = os.path.join(entry.path, "stat")
                    try:
                        with open(stat_file, "r", encoding="utf-8", errors="replace") as f:
                            raw = f.read()
                        rparen = raw.rfind(")")
                        if rparen != -1:
                            fields = raw[rparen + 2 :].split()
                            if len(fields) >= 2:
                                ppid = int(fields[1])
                                children_map.setdefault(ppid, set()).add(cpid)
                    except OSError:
                        pass
        except OSError:
            pass

    def _read_task_children(p: int) -> Set[int]:
        found: Set[int] = set()
        task_dir = f"/proc/{p}/task"
        if not os.path.isdir(task_dir):
            return found
        try:
            with os.scandir(task_dir) as task_it:
                for t_entry in task_it:
                    ch_path = os.path.join(t_entry.path, "children")
                    try:
                        with open(ch_path, "r", encoding="utf-8", errors="replace") as cf:
                            for tok in cf.read().split():
                                if tok.isdigit():
                                    found.add(int(tok))
                    except OSError:
                        pass
        except OSError:
            pass
        return found

    descendants: Set[int] = set()
    pgids: Set[int] = set()
    queue: List[int] = [root_pid]
    visited: Set[int] = {root_pid}

    while queue:
        curr = queue.pop(0)
        direct = set(children_map.get(curr, set())) | _read_task_children(curr)
        for ch in direct:
            if ch <= 1 or ch == os.getpid():
                continue
            descendants.add(ch)
            try:
                ch_pgid = os.getpgid(ch)
                if ch_pgid > 1 and ch_pgid != os.getpgid(0):
                    pgids.add(ch_pgid)
            except OSError:
                pass
            if ch not in visited:
                visited.add(ch)
                queue.append(ch)

    if not os.path.isdir("/proc") and shutil.which("pgrep"):
        try:
            res = subprocess.run(
                ["pgrep", "-P", str(root_pid)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1.0,
                check=False,
            )
            for line in (res.stdout or "").splitlines():
                line = line.strip()
                if line.isdigit():
                    ch = int(line)
                    if ch > 1 and ch != os.getpid():
                        descendants.add(ch)
        except Exception:
            pass

    return descendants, pgids


def _signal_posix_tree(
    root_pid: int,
    sig: int,
    descendants: Optional[Set[int]] = None,
    pgids: Optional[Set[int]] = None,
) -> None:
    """Send ``sig`` to ``root_pid``, its process group (if leader), and all discovered descendants/PGIDs."""
    if descendants is None or pgids is None:
        curr_desc, curr_pgids = _collect_posix_descendants(root_pid)
        all_desc = (descendants or set()) | curr_desc
        all_pgids = (pgids or set()) | curr_pgids
    else:
        all_desc = set(descendants)
        all_pgids = set(pgids)

    try:
        pgid = os.getpgid(root_pid)
        if pgid == root_pid and pgid > 1:
            all_pgids.add(pgid)
    except OSError:
        pass

    my_pgid = -1
    try:
        my_pgid = os.getpgid(0)
    except OSError:
        pass

    for target_pgid in all_pgids:
        if target_pgid > 1 and target_pgid != my_pgid:
            try:
                os.killpg(target_pgid, sig)
            except OSError:
                pass

    for target_pid in (*all_desc, root_pid):
        if target_pid > 1 and target_pid != os.getpid():
            try:
                os.kill(target_pid, sig)
            except OSError:
                pass


def kill_process_tree(pid: int, timeout_sec: float = 3.0) -> bool:
    """
    Gracefully and forcefully terminates the specified process and all its child/descendant
    processes (penetrating ``setsid()`` / ``start_new_session=True`` boundaries).

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
        descendants, pgids = _collect_posix_descendants(pid)
        _signal_posix_tree(pid, signal.SIGTERM, descendants=descendants, pgids=pgids)

        start_wait = time.time()
        while time.time() - start_wait < timeout_sec:
            try:
                os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pass
            if not is_process_alive(pid) and not any(is_process_alive(d) for d in descendants):
                return True
            time.sleep(0.05)

        _signal_posix_tree(pid, signal.SIGKILL, descendants=descendants, pgids=pgids)
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass
        time.sleep(0.05)

        return not is_process_alive(pid)


def terminate_popen_tree(proc: subprocess.Popen, timeout_sec: float = 2.0) -> bool:
    """
    Terminates a child ``Popen`` process (and all its descendants/process groups on POSIX)
    while letting ``Popen`` itself reap the exit status (avoids ``waitpid`` races with
    ``is_process_alive``) and deterministically closing any open pipes in `finally`.

    Args:
        proc: Child process handle.
        timeout_sec: Grace period before escalating to a forced kill.

    Returns:
        bool: True if the process is confirmed terminated, False otherwise.
    """
    try:
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

        descendants, pgids = _collect_posix_descendants(proc.pid)
        _signal_posix_tree(proc.pid, signal.SIGTERM, descendants=descendants, pgids=pgids)
        try:
            proc.wait(timeout=timeout_sec)
            # Ensure any detached grandchildren that called setsid() are also reaped
            if any(is_process_alive(d) for d in descendants):
                _signal_posix_tree(proc.pid, signal.SIGKILL, descendants=descendants, pgids=pgids)
            return True
        except subprocess.TimeoutExpired:
            pass

        _signal_posix_tree(proc.pid, signal.SIGKILL, descendants=descendants, pgids=pgids)
        try:
            proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            return False
        return True
    finally:
        _close_popen_pipes(proc)


def get_process_rss_mb(pid: Optional[int] = None) -> float:
    """
    Return the current Resident Set Size (RSS) in megabytes (MB) for ``pid``
    (defaults to ``os.getpid()``). Returns ``0.0`` if unavailable or terminated.
    """
    target_pid = os.getpid() if pid is None else int(pid)
    if target_pid <= 0:
        return 0.0

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = (
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                )

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            PROCESS_VM_READ = 0x0010
            k32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            handle = k32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, target_pid
            )
            if not handle:
                return 0.0
            try:
                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                if psapi.GetProcessMemoryInfo(
                    handle, ctypes.byref(counters), counters.cb
                ):
                    return round(float(counters.WorkingSetSize) / (1024.0 * 1024.0), 2)
            finally:
                k32.CloseHandle(handle)
        except Exception:
            return 0.0
        return 0.0

    # Linux /proc/<pid>/status VmRSS
    if os.path.isdir("/proc"):
        status_path = f"/proc/{target_pid}/status"
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            parts = line.split()
                            if len(parts) >= 2 and parts[1].isdigit():
                                return round(float(parts[1]) / 1024.0, 2)
            except OSError:
                return 0.0
        return 0.0

    # Fallback: macOS / BSD `ps -o rss= -p <pid>`
    try:
        res = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(target_pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
            check=False,
        )
        if res.returncode == 0:
            raw_kb = (res.stdout or "").strip()
            if raw_kb.isdigit():
                return round(float(raw_kb) / 1024.0, 2)
    except Exception:
        pass
    return 0.0


def get_host_memory_info() -> Dict[str, float]:
    """
    Return host physical memory metrics in MB:
    ``{"total_mb": ..., "available_mb": ..., "available_ratio": ...}``.
    Returns empty dict if unavailable.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = (
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                )

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_mb = float(stat.ullTotalPhys) / (1024.0 * 1024.0)
                avail_mb = float(stat.ullAvailPhys) / (1024.0 * 1024.0)
                ratio = (avail_mb / total_mb) if total_mb > 0 else 1.0
                return {
                    "total_mb": round(total_mb, 2),
                    "available_mb": round(avail_mb, 2),
                    "available_ratio": round(ratio, 4),
                }
        except Exception:
            return {}
        return {}

    meminfo_path = "/proc/meminfo"
    if os.path.exists(meminfo_path):
        try:
            total_kb = 0.0
            avail_kb = 0.0
            free_kb = 0.0
            cached_kb = 0.0
            buffers_kb = 0.0
            with open(meminfo_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total_kb = float(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        avail_kb = float(line.split()[1])
                    elif line.startswith("MemFree:"):
                        free_kb = float(line.split()[1])
                    elif line.startswith("Buffers:"):
                        buffers_kb = float(line.split()[1])
                    elif line.startswith("Cached:"):
                        cached_kb = float(line.split()[1])
            if total_kb > 0:
                if avail_kb <= 0:
                    avail_kb = free_kb + buffers_kb + cached_kb
                total_mb = total_kb / 1024.0
                avail_mb = avail_kb / 1024.0
                return {
                    "total_mb": round(total_mb, 2),
                    "available_mb": round(avail_mb, 2),
                    "available_ratio": round(avail_mb / total_mb, 4),
                }
        except Exception:
            pass
    return {}


def trim_process_memory(min_interval_sec: float = 5.0) -> bool:
    """
    Run ``gc.collect()`` and release free heap arenas back to the OS kernel
    (via ``libc.malloc_trim(0)`` on Linux or ``SetProcessWorkingSetSize`` on Windows).
    Throttled by ``min_interval_sec`` so frequent calls do not incur excessive GC overhead.
    """
    now = time.monotonic()
    ctx = get_runtime_context()
    last_ts = float(ctx.get_module_state(_TRIM_STATE_KEY, lambda: 0.0) or 0.0)
    if min_interval_sec > 0 and (now - last_ts) < min_interval_sec:
        return False
    ctx.set_module_state(_TRIM_STATE_KEY, now)

    try:
        gc.collect()
    except Exception:
        pass

    if sys.platform.startswith("linux"):
        try:
            import ctypes
            import ctypes.util

            libc_name = ctypes.util.find_library("c") or "libc.so.6"
            libc = ctypes.CDLL(libc_name)
            if hasattr(libc, "malloc_trim"):
                libc.malloc_trim(0)
                return True
        except Exception:
            pass
    return True


def reap_sandbox_processes(sandbox_dir: Union[str, Path], timeout_sec: float = 2.0) -> int:
    """
    Scan and terminate any residual processes whose ``cwd``, ``cmdline``, or
    ``YSCB_SANDBOX_DIR`` environment variable resides inside ``sandbox_dir``.
    Returns the number of root processes terminated.
    """
    if not sandbox_dir or sys.platform == "win32" or not os.path.isdir("/proc"):
        return 0

    try:
        norm_sb = os.path.normcase(os.path.normpath(os.path.realpath(str(sandbox_dir))))
        norm_sb_abs = os.path.normcase(os.path.normpath(os.path.abspath(str(sandbox_dir))))
    except OSError:
        return 0

    my_pid = os.getpid()
    matched_pids: Set[int] = set()

    def _matches_sb(p_str: str) -> bool:
        if not p_str:
            return False
        norm_p = os.path.normcase(os.path.normpath(p_str))
        return (
            norm_p == norm_sb
            or norm_p.startswith(norm_sb + os.sep)
            or norm_p == norm_sb_abs
            or norm_p.startswith(norm_sb_abs + os.sep)
        )

    try:
        with os.scandir("/proc") as proc_it:
            for entry in proc_it:
                if not entry.name.isdigit():
                    continue
                pid = int(entry.name)
                if pid <= 1 or pid == my_pid:
                    continue

                # 1. Check /proc/<pid>/cwd symlink
                try:
                    cwd_target = os.readlink(os.path.join(entry.path, "cwd"))
                    if _matches_sb(cwd_target):
                        matched_pids.add(pid)
                        continue
                except OSError:
                    pass

                # 2. Check /proc/<pid>/cmdline
                try:
                    with open(os.path.join(entry.path, "cmdline"), "rb") as f:
                        raw_cmd = f.read().decode("utf-8", errors="ignore")
                    if norm_sb in raw_cmd or norm_sb_abs in raw_cmd:
                        matched_pids.add(pid)
                        continue
                except OSError:
                    pass

                # 3. Check /proc/<pid>/environ for YSCB_SANDBOX_DIR
                try:
                    with open(os.path.join(entry.path, "environ"), "rb") as f:
                        raw_env = f.read().decode("utf-8", errors="ignore")
                    if f"YSCB_SANDBOX_DIR={norm_sb}" in raw_env or f"YSCB_SANDBOX_DIR={norm_sb_abs}" in raw_env:
                        matched_pids.add(pid)
                        continue
                except OSError:
                    pass
    except OSError:
        pass

    reaped = 0
    for pid in sorted(matched_pids):
        if is_process_alive(pid):
            kill_process_tree(pid, timeout_sec=timeout_sec)
            reaped += 1
    return reaped


def __getattr__(name: str) -> Any:
    """PEP 562 backward-compatible attribute delegation to active `RuntimeContext`."""
    if name == "_CAN_SPAWN_DAEMON_CACHE":
        return _get_can_spawn_cache()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
