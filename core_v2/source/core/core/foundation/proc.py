"""Cross-platform OS process-tree supervision, detached daemon spawning, and liveness probes."""

from __future__ import annotations

import atexit
from collections import deque
from dataclasses import dataclass, field
import errno
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Callable, ClassVar, Mapping, Optional, Sequence
import uuid

from core.foundation.errors import safe_exception_summary
from core.foundation.observability import clamp_wait_sec
from core.foundation.primitives import invoke_observer_safely, IS_WINDOWS, HostPath, require_non_none, require_pure_bool, require_typed_tuple

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    class _JobObjectBasicLimitInfo(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _JobObjectExtendedLimitInfo(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JobObjectBasicLimitInfo),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _WIN_K32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _WIN_OPEN_PROC = _WIN_K32.OpenProcess
    _WIN_OPEN_PROC.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _WIN_OPEN_PROC.restype = wintypes.HANDLE

    _WIN_CLOSE_HANDLE = _WIN_K32.CloseHandle
    _WIN_CLOSE_HANDLE.argtypes = [wintypes.HANDLE]
    _WIN_CLOSE_HANDLE.restype = wintypes.BOOL

    _WIN_WAIT_SINGLE = _WIN_K32.WaitForSingleObject
    _WIN_WAIT_SINGLE.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _WIN_WAIT_SINGLE.restype = wintypes.DWORD

    _WIN_GET_EXIT = _WIN_K32.GetExitCodeProcess
    _WIN_GET_EXIT.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _WIN_GET_EXIT.restype = wintypes.BOOL

    _WIN_CREATE_JOB = _WIN_K32.CreateJobObjectW
    _WIN_CREATE_JOB.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _WIN_CREATE_JOB.restype = wintypes.HANDLE

    _WIN_SET_JOB_INFO = _WIN_K32.SetInformationJobObject
    _WIN_SET_JOB_INFO.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _WIN_SET_JOB_INFO.restype = wintypes.BOOL

    _WIN_ASSIGN_JOB = _WIN_K32.AssignProcessToJobObject
    _WIN_ASSIGN_JOB.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _WIN_ASSIGN_JOB.restype = wintypes.BOOL

    _WIN_TERM_JOB = _WIN_K32.TerminateJobObject
    _WIN_TERM_JOB.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _WIN_TERM_JOB.restype = wintypes.BOOL

    _WIN_NTDLL = ctypes.WinDLL("ntdll", use_last_error=True)
    _WIN_RESUME_PROC = _WIN_NTDLL.NtResumeProcess
    _WIN_RESUME_PROC.argtypes = [wintypes.HANDLE]
    _WIN_RESUME_PROC.restype = wintypes.LONG
elif sys.platform == "darwin":
    import ctypes

    class _DarwinProcBsdInfo(ctypes.Structure):
        _fields_ = [
            ("pbi_flags", ctypes.c_uint32),
            ("pbi_status", ctypes.c_uint32),
            ("pbi_xstatus", ctypes.c_uint32),
            ("pbi_pid", ctypes.c_uint32),
            ("pbi_ppid", ctypes.c_uint32),
            ("pbi_uid", ctypes.c_uint32),
            ("pbi_gid", ctypes.c_uint32),
            ("pbi_ruid", ctypes.c_uint32),
            ("pbi_rgid", ctypes.c_uint32),
            ("pbi_svuid", ctypes.c_uint32),
            ("pbi_svgid", ctypes.c_uint32),
            ("rfu_1", ctypes.c_uint32),
            ("pbi_comm", ctypes.c_char * 16),
            ("pbi_name", ctypes.c_char * 32),
            ("pbi_nfiles", ctypes.c_uint32),
            ("pbi_pgid", ctypes.c_uint32),
            ("pbi_pjobc", ctypes.c_uint32),
            ("e_tdev", ctypes.c_uint32),
            ("e_tpgid", ctypes.c_uint32),
            ("pbi_nice", ctypes.c_int32),
            ("pbi_start_tvsec", ctypes.c_uint64),
            ("pbi_start_tvusec", ctypes.c_uint64),
        ]

    _DARWIN_LIBSYS = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    _DARWIN_PROC_PIDINFO = _DARWIN_LIBSYS.proc_pidinfo
    _DARWIN_PROC_PIDINFO.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    _DARWIN_PROC_PIDINFO.restype = ctypes.c_int

    _DARWIN_PROC_LISTPIDS = _DARWIN_LIBSYS.proc_listpids
    _DARWIN_PROC_LISTPIDS.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
    _DARWIN_PROC_LISTPIDS.restype = ctypes.c_int


def _create_win32_kill_on_close_job(pid: int) -> Optional[int]:
    if not IS_WINDOWS:
        return None
    job = _WIN_CREATE_JOB(None, None)
    if not job:
        return None
    info = _JobObjectExtendedLimitInfo()
    info.BasicLimitInformation.LimitFlags = 0x00002000
    if not _WIN_SET_JOB_INFO(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        _WIN_CLOSE_HANDLE(job)
        return None
    proc_handle = _WIN_OPEN_PROC(0x0001 | 0x0100 | 0x0800, False, pid)
    if not proc_handle:
        _WIN_CLOSE_HANDLE(job)
        return None
    try:
        if not _WIN_ASSIGN_JOB(job, proc_handle):
            _WIN_CLOSE_HANDLE(job)
            return None
        _WIN_RESUME_PROC(proc_handle)
        return int(job)
    finally:
        _WIN_CLOSE_HANDLE(proc_handle)


def _close_win32_job(job_handle: Optional[int]) -> None:
    if not IS_WINDOWS or job_handle is None:
        return
    _WIN_TERM_JOB(wintypes.HANDLE(job_handle), 1)
    _WIN_CLOSE_HANDLE(wintypes.HANDLE(job_handle))


def _is_process_alive_windows(pid: int) -> bool:
    synchronize = 0x00100000
    process_query_limited = 0x1000
    wait_timeout = 0x00000102
    error_access_denied = 5

    handle = _WIN_OPEN_PROC(synchronize | process_query_limited, False, pid)
    if handle:
        try:
            return int(_WIN_WAIT_SINGLE(handle, 0)) == wait_timeout
        finally:
            _WIN_CLOSE_HANDLE(handle)

    handle = _WIN_OPEN_PROC(process_query_limited, False, pid)
    if not handle:
        return int(ctypes.get_last_error()) == error_access_denied
    try:
        exit_code = wintypes.DWORD(0)
        if _WIN_GET_EXIT(handle, ctypes.byref(exit_code)):
            return int(exit_code.value) == 259
        return True
    finally:
        _WIN_CLOSE_HANDLE(handle)


@dataclass(frozen=True, slots=True)
class _DarwinBsdStat:
    status: int
    ppid: int
    pgid: int
    start_us: int


def _darwin_query_bsdinfo(pid: int) -> Optional[_DarwinBsdStat]:
    if sys.platform != "darwin" or pid <= 0:
        return None
    info = _DarwinProcBsdInfo()
    sz = ctypes.sizeof(info)
    ret = int(_DARWIN_PROC_PIDINFO(pid, 3, 0, ctypes.byref(info), sz))
    if ret != sz:
        return None
    start_us = int(info.pbi_start_tvsec) * 1_000_000 + int(info.pbi_start_tvusec)
    return _DarwinBsdStat(int(info.pbi_status), int(info.pbi_ppid), int(info.pbi_pgid), start_us)


def _check_proc_zombie_stat(pid: int) -> bool:
    stat_file = Path(f"/proc/{pid}/stat")
    if stat_file.is_file():
        try:
            raw = stat_file.read_bytes()
        except OSError:
            return False
        rparen = raw.rfind(b")")
        return rparen != -1 and len(raw) > rparen + 2 and raw[rparen + 2 : rparen + 3] == b"Z"
    if sys.platform == "darwin":
        bsd_st = _darwin_query_bsdinfo(pid)
        if bsd_st is not None:
            return bsd_st.status == 5
        if ctypes.get_errno() == errno.ESRCH:
            return True
    if sys.platform == "darwin" or "bsd" in sys.platform:
        try:
            cp = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(pid)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
            st_str = cp.stdout.strip()
            return not st_str or st_str.startswith("Z")
        except Exception:
            return False
    return False


def _is_process_alive_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OverflowError):
        return False
    except PermissionError:
        return True
    except OSError as exc:
        return exc.errno != errno.ESRCH
    return not _check_proc_zombie_stat(pid)


def is_process_alive(pid: int) -> bool:
    """Return True if an OS process with ``pid`` currently exists and is not a zombie."""
    max_pid = 0xFFFFFFFF if IS_WINDOWS else 0x7FFFFFFF
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 or pid > max_pid:
        return False
    return _is_process_alive_windows(pid) if IS_WINDOWS else _is_process_alive_posix(pid)


def _validate_proc_argv_and_cwd(argv: Sequence[str], cwd: HostPath, label: str) -> list[str]:
    if not isinstance(cwd, HostPath):
        raise ValueError(f"{label} cwd must be HostPath, got {cwd!r}")
    tup = require_typed_tuple(argv, str, f"{label} argv")
    if not tup or any("\x00" in seg for seg in tup):
        raise ValueError(f"{label} argv must be a non-empty NUL-free Sequence[str].")
    return list(tup)


def spawn_detached(
    argv: Sequence[str],
    *,
    cwd: HostPath,
    extra_env: Optional[Mapping[str, str]] = None,
) -> int:
    """Spawn a fully detached background process via an intermediate launcher (0 ResourceWarning)."""
    clean_argv = _validate_proc_argv_and_cwd(argv, cwd, "spawn_detached")
    launcher_code = "\n".join(
        (
            "import json, os, subprocess, sys, warnings",
            "warnings.simplefilter('ignore', ResourceWarning)",
            "cfg = json.loads(sys.argv[1])",
            "env = dict(os.environ)",
            "env.update(cfg.get('extra_env') or {})",
            "kw = {'cwd': cfg['cwd'], 'env': env, 'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL, 'close_fds': True}",
            "if os.name == 'nt':",
            "    try:",
            "        p = subprocess.Popen(cfg['argv'], **{**kw, 'creationflags': 0x00000008 | 0x00000200 | 0x01000000})",
            "    except OSError:",
            "        p = subprocess.Popen(cfg['argv'], **{**kw, 'creationflags': 0x00000008 | 0x00000200})",
            "else:",
            "    p = subprocess.Popen(cfg['argv'], **{**kw, 'start_new_session': True})",
            "sys.stdout.write(str(p.pid))",
            "sys.stdout.flush()",
            "os._exit(0)",
        )
    )
    merged_extra = dict(extra_env) if extra_env else {}
    if sys.dont_write_bytecode:
        merged_extra.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    if sys.flags.optimize > 0:
        merged_extra.setdefault("PYTHONOPTIMIZE", str(sys.flags.optimize))
    opt_flags = [f"-{'O' * min(2, sys.flags.optimize)}"] if sys.flags.optimize > 0 else []
    payload = json.dumps({"argv": clean_argv, "cwd": str(cwd), "extra_env": merged_extra})
    launcher_argv = [sys.executable, *(["-B"] if sys.dont_write_bytecode else []), *opt_flags, "-c", launcher_code, payload]
    try:
        completed = subprocess.run(
            launcher_argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10.0,
            check=True,
        )
        return int(completed.stdout.strip())
    except (subprocess.SubprocessError, ValueError) as exc:
        raise OSError(f"Failed to spawn detached process: {safe_exception_summary(exc)}") from exc


@dataclass(frozen=True, slots=True)
class _PosixPsSnapshot:
    by_ppid: dict[int, list[int]]
    by_pgid: dict[int, list[int]]


def _snapshot_darwin_tree_maps() -> Optional[_PosixPsSnapshot]:
    if sys.platform != "darwin":
        return None
    est_bytes = int(_DARWIN_PROC_LISTPIDS(1, 0, None, 0))
    if est_bytes <= 0:
        return None
    cap_cnt = max(256, (est_bytes // 4) + 128)
    buf = (ctypes.c_int * cap_cnt)()
    used_bytes = int(_DARWIN_PROC_LISTPIDS(1, 0, ctypes.byref(buf), cap_cnt * 4))
    if used_bytes <= 0:
        return None
    by_ppid: dict[int, list[int]] = {}
    by_pgid: dict[int, list[int]] = {}
    for idx in range(min(cap_cnt, used_bytes // 4)):
        pid_v = int(buf[idx])
        bsd_st = _darwin_query_bsdinfo(pid_v) if pid_v > 0 else None
        if bsd_st is not None and bsd_st.status != 5:
            by_ppid.setdefault(bsd_st.ppid, []).append(pid_v)
            by_pgid.setdefault(bsd_st.pgid, []).append(pid_v)
    return _PosixPsSnapshot(by_ppid, by_pgid)


def _snapshot_ps_tree_maps() -> _PosixPsSnapshot:
    darwin_snap = _snapshot_darwin_tree_maps()
    if darwin_snap is not None:
        return darwin_snap
    try:
        cp = subprocess.run(
            ["ps", "-ax", "-o", "pid=,ppid=,pgid="],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except OSError:
        return _PosixPsSnapshot({}, {})
    by_ppid: dict[int, list[int]] = {}
    by_pgid: dict[int, list[int]] = {}
    for line in cp.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit():
            pid_v, ppid_v, pgid_v = int(parts[0]), int(parts[1]), int(parts[2])
            by_ppid.setdefault(ppid_v, []).append(pid_v)
            by_pgid.setdefault(pgid_v, []).append(pid_v)
    return _PosixPsSnapshot(by_ppid, by_pgid)


def _read_direct_proc_children(root_pid: int, ps_map: Optional[dict[int, list[int]]]) -> list[int]:
    if ps_map is not None:
        return ps_map.get(root_pid, [])
    task_dir = Path(f"/proc/{root_pid}/task")
    if not task_dir.is_dir():
        return []
    out: list[int] = []
    try:
        tid_dirs = list(task_dir.iterdir())
    except OSError:
        return out
    for tid_dir in tid_dirs:
        try:
            raw_ch = (tid_dir / "children").read_text(encoding="utf-8")
        except OSError:
            continue
        out.extend(int(tok) for tok in raw_ch.split() if tok.isdigit())
    return out


def _read_posix_proc_starttime(pid: int) -> Optional[int]:
    if IS_WINDOWS or pid <= 0:
        return None
    if sys.platform == "darwin":
        bsd_st = _darwin_query_bsdinfo(pid)
        return bsd_st.start_us if bsd_st is not None else None
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    rparen = raw.rfind(")")
    if rparen < 0:
        return None
    fields = raw[rparen + 2 :].split()
    return int(fields[19]) if len(fields) > 19 and fields[19].isdigit() else None


def _collect_posix_descendants_walk(
    root_pid: int,
    seen: set[int],
    ps_map: Optional[dict[int, list[int]]],
) -> list[int]:
    if root_pid <= 0 or root_pid in seen:
        return []
    seen.add(root_pid)
    ordered: list[int] = []
    for cpid in _read_direct_proc_children(root_pid, ps_map):
        ordered.extend(_collect_posix_descendants_walk(cpid, seen, ps_map))
        ordered.append(cpid)
    return ordered


_HAS_POSIX_PROC_STAT: bool = (not IS_WINDOWS) and Path("/proc/self/stat").is_file()
_HAS_POSIX_PROC_STARTTIME: bool = _HAS_POSIX_PROC_STAT or sys.platform == "darwin"


def _collect_posix_descendants(
    root_pid: int,
    seen: set[int],
    ps_map: Optional[dict[int, list[int]]] = None,
) -> list[int]:
    if IS_WINDOWS or root_pid <= 0:
        return []
    if not _HAS_POSIX_PROC_STAT and ps_map is None:
        ps_map = _snapshot_ps_tree_maps().by_ppid
    return _collect_posix_descendants_walk(root_pid, seen, ps_map)


def _is_targeted_descendant_alive(dpid: int, exp_st: Optional[int]) -> bool:
    if dpid <= 1 or not is_process_alive(dpid):
        return False
    if _HAS_POSIX_PROC_STARTTIME and (exp_st is None or _read_posix_proc_starttime(dpid) != exp_st):
        return False
    return True


def _signal_posix_descendants(targets: dict[int, Optional[int]], sig: int) -> None:
    for dpid, exp_st in targets.items():
        if not _is_targeted_descendant_alive(dpid, exp_st):
            continue
        try:
            os.killpg(dpid, sig)
        except OSError:
            pass
        try:
            os.kill(dpid, sig)
        except OSError:
            pass


def _await_posix_descendants_dead(targets: dict[int, Optional[int]], max_wait_sec: float = 0.5) -> None:
    if not targets:
        return
    deadline = time.monotonic() + max_wait_sec
    while time.monotonic() < deadline:
        if not any(_is_targeted_descendant_alive(dpid, exp_st) for dpid, exp_st in targets.items()):
            return
        time.sleep(0.002)


@dataclass(frozen=True, slots=True)
class _ProcStatRow:
    pid: int
    state: str
    ppid: int
    pgid: int


def _parse_procfs_stat_entry(entry_name: str) -> Optional[_ProcStatRow]:
    if not entry_name.isdigit():
        return None
    pid_v = int(entry_name)
    try:
        raw = Path(f"/proc/{pid_v}/stat").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    rparen = raw.rfind(")")
    if rparen < 0:
        return None
    fields = raw[rparen + 2 :].split()
    if len(fields) < 3 or not fields[1].lstrip("-").isdigit() or not fields[2].lstrip("-").isdigit():
        return None
    return _ProcStatRow(pid_v, fields[0], int(fields[1]), int(fields[2]))


def _snapshot_procfs_tree_maps() -> _PosixPsSnapshot:
    by_ppid: dict[int, list[int]] = {}
    by_pgid: dict[int, list[int]] = {}
    try:
        entries = [e.name for e in Path("/proc").iterdir()]
    except OSError:
        return _PosixPsSnapshot({}, {})
    for name in entries:
        parsed = _parse_procfs_stat_entry(name)
        if parsed is None:
            continue
        by_ppid.setdefault(parsed.ppid, []).append(parsed.pid)
        by_pgid.setdefault(parsed.pgid, []).append(parsed.pid)
    return _PosixPsSnapshot(by_ppid, by_pgid)


def _collect_orphan_pgid_members_posix(
    root_pid: int,
    seen: set[int],
    ps_snap: Optional[_PosixPsSnapshot] = None,
) -> list[int]:
    if IS_WINDOWS or root_pid <= 0 or is_process_alive(root_pid):
        return []
    snap = ps_snap or (_snapshot_procfs_tree_maps() if _HAS_POSIX_PROC_STAT else _snapshot_ps_tree_maps())
    out: list[int] = []
    for p in snap.by_pgid.get(root_pid, ()):
        if p != root_pid and p not in seen:
            seen.add(p)
            out.append(p)
    idx = 0
    while idx < len(out):
        cur = out[idx]
        idx += 1
        for ch in snap.by_ppid.get(cur, ()):
            if ch != root_pid and ch not in seen:
                seen.add(ch)
                out.append(ch)
    return out


def _environ_contains_tree_token(env_raw: bytes, token_bytes: bytes) -> bool:
    for entry in env_raw.split(b"\x00"):
        if entry.startswith(b"_YSCB_TREE_ID="):
            return token_bytes in entry[14:].split(b",")
    return False


def _collect_procfs_env_token_pids(
    token_bytes: bytes,
    root_pid: int,
    seen: set[int],
    ps_map: Optional[dict[int, list[int]]] = None,
) -> list[int]:
    if IS_WINDOWS or not _HAS_POSIX_PROC_STAT or not token_bytes:
        return []
    me = os.getpid()
    roots: list[int] = []
    try:
        entries = [e.name for e in Path("/proc").iterdir() if e.name.isdigit()]
    except OSError:
        return roots
    for name in entries:
        pid_v = int(name)
        if pid_v in (me, root_pid) or pid_v in seen:
            continue
        try:
            env_raw = Path(f"/proc/{pid_v}/environ").read_bytes()
        except OSError:
            continue
        if _environ_contains_tree_token(env_raw, token_bytes):
            roots.append(pid_v)
    return [dpid for tpid in roots for dpid in (*_collect_posix_descendants(tpid, seen, ps_map), tpid)]


def _validate_signal_numbers(sig_nums: Sequence[int]) -> frozenset[int]:
    max_sig = min(256, int(signal.NSIG))
    validated: list[int] = []
    for sig_num in sig_nums:
        if isinstance(sig_num, bool) or not isinstance(sig_num, int) or not (1 <= sig_num < max_sig):
            raise ValueError(f"Invalid signal number in sig_nums: {sig_num!r}")
        validated.append(sig_num)
    return frozenset(validated)


def _close_sock_quietly(s: Optional[socket.socket]) -> None:
    if s is None:
        return
    try:
        s.close()
    except OSError:
        pass


@dataclass(slots=True)
class _SignalMuxState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    active_guards: list[SignalWakeupGuard] = field(default_factory=list)
    retiring_barriers: deque[tuple[SignalWakeupGuard, threading.Event]] = field(default_factory=deque)
    orig_handlers: dict[int, object] = field(default_factory=dict)
    handled_sigs: frozenset[int] = field(default_factory=frozenset)
    orig_handlers_snap: Mapping[int, object] = field(default_factory=dict)
    wsock: Optional[socket.socket] = None
    prev_wakeup_fd: int = -1
    watcher_thread: Optional[threading.Thread] = None


def _refresh_mux_snapshots_locked(mux: _SignalMuxState) -> None:
    mux.handled_sigs = frozenset(s for g in mux.active_guards for s in g._sig_nums)
    mux.orig_handlers_snap = dict(mux.orig_handlers)


@dataclass(frozen=True, slots=True)
class _MainDrainHandles:
    wsock: Optional[socket.socket] = None
    watcher: Optional[threading.Thread] = None


def _forward_wakeup_bytes(prev_fd: int, data: bytes) -> None:
    if prev_fd < 0 or not data:
        return
    if IS_WINDOWS:
        try:
            borrowed = socket.socket(fileno=prev_fd)
        except OSError:
            borrowed = None
        if borrowed is not None:
            try:
                borrowed.send(data)
            except OSError:
                pass
            finally:
                borrowed.detach()
            return
    try:
        os.write(prev_fd, data)
    except OSError:
        pass


def _restore_unused_mux_handlers_locked(mux: _SignalMuxState, needed: set[int]) -> None:
    for sig_num in [s for s in mux.orig_handlers if s not in needed]:
        old_h = mux.orig_handlers.pop(sig_num)
        try:
            if signal.getsignal(sig_num) is _mux_signal_handler:
                signal.signal(sig_num, old_h)
        except (OSError, ValueError):
            continue
    _refresh_mux_snapshots_locked(mux)


def _detach_mux_on_main_locked(mux: _SignalMuxState) -> _MainDrainHandles:
    _restore_unused_mux_handlers_locked(mux, set())
    ws, wt, prev_fd = mux.wsock, mux.watcher_thread, mux.prev_wakeup_fd
    if ws is not None:
        try:
            cur_fd = signal.set_wakeup_fd(-1)
            if cur_fd != ws.fileno() and cur_fd >= 0:
                signal.set_wakeup_fd(cur_fd)
            elif prev_fd >= 0:
                signal.set_wakeup_fd(prev_fd)
        except (OSError, ValueError):
            pass
    mux.prev_wakeup_fd = -1
    mux.wsock = None
    mux.watcher_thread = None
    return _MainDrainHandles(ws, wt)


def _finish_main_drain(handles: _MainDrainHandles, *, join_watcher: bool = True) -> None:
    ws = handles.wsock
    if ws is not None:
        try:
            ws.shutdown(socket.SHUT_WR)
        except OSError:
            pass
    wt = handles.watcher
    if join_watcher and wt is not None and wt is not threading.current_thread() and wt.is_alive():
        wt.join(timeout=1.0)
    if ws is not None:
        _close_sock_quietly(ws)


def _ensure_mux_pipe_locked(mux: _SignalMuxState) -> tuple[bool, _MainDrainHandles]:
    if mux.wsock is not None and mux.watcher_thread is not None and mux.watcher_thread.is_alive():
        return (True, _MainDrainHandles())
    stale = _detach_mux_on_main_locked(mux)
    rsock, wsock = socket.socketpair()
    wsock.setblocking(False)
    try:
        prev_fd = signal.set_wakeup_fd(wsock.fileno(), warn_on_full_buffer=False)
    except (OSError, ValueError):
        _close_sock_quietly(wsock)
        _close_sock_quietly(rsock)
        return (False, stale)
    wt = threading.Thread(target=_mux_watch_loop, args=(mux, rsock, prev_fd), name="yscb-sig-wakeup", daemon=True)
    mux.wsock = wsock
    mux.prev_wakeup_fd = prev_fd
    mux.watcher_thread = wt
    try:
        wt.start()
    except BaseException:
        mux.wsock = None
        mux.prev_wakeup_fd = -1
        mux.watcher_thread = None
        try:
            signal.set_wakeup_fd(prev_fd if prev_fd >= 0 else -1)
        except (OSError, ValueError):
            pass
        _close_sock_quietly(wsock)
        _close_sock_quietly(rsock)
        raise
    return (True, stale)


def _register_mux_signals_locked(mux: _SignalMuxState, sig_nums: frozenset[int]) -> bool:
    any_ok = False
    for sig_num in sig_nums:
        try:
            cur_h = signal.getsignal(sig_num)
            if cur_h is _mux_signal_handler:
                mux.orig_handlers.setdefault(sig_num, signal.SIG_DFL)
                _refresh_mux_snapshots_locked(mux)
                any_ok = True
                continue
            mux.orig_handlers[sig_num] = cur_h
            _refresh_mux_snapshots_locked(mux)
            signal.signal(sig_num, _mux_signal_handler)
            any_ok = True
        except (OSError, ValueError):
            mux.orig_handlers.pop(sig_num, None)
            _refresh_mux_snapshots_locked(mux)
    return any_ok


def _process_single_mux_byte(mux: _SignalMuxState, sig_byte: int, prev_fd: int) -> None:
    if sig_byte == 0:
        popped: Optional[tuple[SignalWakeupGuard, threading.Event]] = None
        with mux.lock:
            if mux.retiring_barriers:
                popped = mux.retiring_barriers.popleft()
        if popped is not None:
            popped[0]._mark_inactive()
            popped[1].set()
        return
    b_seq = bytes((sig_byte,))
    _forward_wakeup_bytes(prev_fd, b_seq)
    with mux.lock:
        targets = (*mux.active_guards, *(rg for rg, _ev in mux.retiring_barriers))
    for guard in targets:
        guard._dispatch_signal(sig_byte)


def _retire_all_pending_barriers(mux: _SignalMuxState) -> None:
    with mux.lock:
        pending = list(mux.retiring_barriers)
        mux.retiring_barriers.clear()
    for guard, ev in pending:
        guard._mark_inactive()
        ev.set()


def _mux_watch_loop(mux: _SignalMuxState, rs: socket.socket, prev_fd: int) -> None:
    try:
        while True:
            try:
                data = rs.recv(64)
            except OSError:
                return
            if not data:
                return
            for b_val in data:
                _process_single_mux_byte(mux, b_val, prev_fd)
    finally:
        _retire_all_pending_barriers(mux)
        _close_sock_quietly(rs)


class SignalWakeupGuard:
    """Routes main-thread OS signals through a single FIFO-barrier C-level set_wakeup_fd coordinator."""

    _MUX: ClassVar[_SignalMuxState] = _SignalMuxState()

    @classmethod
    def drain_retired_on_main(cls) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        handles = _MainDrainHandles()
        with cls._MUX.lock:
            needed = {s for g in cls._MUX.active_guards for s in g._sig_nums}
            if cls._MUX.active_guards:
                _restore_unused_mux_handlers_locked(cls._MUX, needed)
            elif bool(cls._MUX.orig_handlers) or cls._MUX.wsock is not None:
                handles = _detach_mux_on_main_locked(cls._MUX)
        _finish_main_drain(handles)

    @classmethod
    def _try_drain_from_signal_handler(cls) -> bool:
        mux = cls._MUX
        if not mux.lock.acquire(blocking=False):
            return False
        handles = _MainDrainHandles()
        try:
            if mux.active_guards:
                return False
            if bool(mux.orig_handlers) or mux.wsock is not None:
                handles = _detach_mux_on_main_locked(mux)
        finally:
            mux.lock.release()
        _finish_main_drain(handles, join_watcher=False)
        return True

    def __init__(
        self,
        sig_nums: Sequence[int],
        on_signal: Callable[[], None],
        *,
        on_second_signal: Optional[Callable[[], None]] = None,
    ) -> None:
        self._sig_nums = _validate_signal_numbers(sig_nums)
        self._on_signal = on_signal
        self._on_second_signal = on_second_signal
        self._state_lock = threading.Lock()
        self._installed = False
        self._seen_hits = 0

    def __enter__(self) -> SignalWakeupGuard:
        self.install()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def _is_active(self) -> bool:
        with self._state_lock:
            return self._installed

    def _mark_inactive(self) -> None:
        with self._state_lock:
            self._installed = False

    def _dispatch_signal(self, sig_num: int) -> None:
        if sig_num not in self._sig_nums:
            return
        with self._state_lock:
            if not self._installed:
                return
            was_first = self._seen_hits == 0
            self._seen_hits += 1
        if was_first:
            invoke_observer_safely(self._on_signal)
        elif self._on_second_signal is not None and self._is_active():
            invoke_observer_safely(self._on_second_signal)

    def _activate_guard_locked(self, mux: _SignalMuxState) -> _MainDrainHandles:
        with self._state_lock:
            self._seen_hits = 0
            self._installed = True
        mux.active_guards.append(self)
        _refresh_mux_snapshots_locked(mux)
        if _register_mux_signals_locked(mux, self._sig_nums):
            return _MainDrainHandles()
        mux.active_guards.remove(self)
        self._mark_inactive()
        _refresh_mux_snapshots_locked(mux)
        return _detach_mux_on_main_locked(mux) if not mux.active_guards else _MainDrainHandles()

    def install(self) -> None:
        if threading.current_thread() is not threading.main_thread() or not self._sig_nums:
            return
        stale = _MainDrainHandles()
        abort_drain = _MainDrainHandles()
        mux = SignalWakeupGuard._MUX
        with mux.lock:
            if self in mux.active_guards:
                return
            pipe_ok, stale = _ensure_mux_pipe_locked(mux)
            if pipe_ok:
                abort_drain = self._activate_guard_locked(mux)
        _finish_main_drain(stale)
        _finish_main_drain(abort_drain)

    def _enqueue_retire_barrier_locked(self, mux: _SignalMuxState, on_watcher: bool) -> Optional[threading.Event]:
        if on_watcher or mux.wsock is None:
            self._mark_inactive()
            return None
        done_ev = threading.Event()
        mux.retiring_barriers.append((self, done_ev))
        try:
            mux.wsock.send(b"\x00")
            return done_ev
        except OSError:
            mux.retiring_barriers.pop()
            self._mark_inactive()
            return None

    def _close_on_main_locked(self, mux: _SignalMuxState, was_active: bool, on_watcher: bool) -> tuple[_MainDrainHandles, Optional[threading.Event]]:
        needed = {s for g in mux.active_guards for s in g._sig_nums}
        _restore_unused_mux_handlers_locked(mux, needed)
        if not mux.active_guards and (bool(mux.orig_handlers) or mux.wsock is not None):
            if was_active:
                mux.retiring_barriers.append((self, threading.Event()))
            return (_detach_mux_on_main_locked(mux), None)
        return (_MainDrainHandles(), self._enqueue_retire_barrier_locked(mux, on_watcher) if was_active else None)

    def close(self) -> None:
        cur_th = threading.current_thread()
        is_main = cur_th is threading.main_thread()
        handles = _MainDrainHandles()
        barrier_ev: Optional[threading.Event] = None
        mux = SignalWakeupGuard._MUX
        with mux.lock:
            on_watcher = cur_th is mux.watcher_thread
            was_active = self in mux.active_guards
            if was_active:
                mux.active_guards.remove(self)
                _refresh_mux_snapshots_locked(mux)
            else:
                self._mark_inactive()
            if is_main:
                handles, barrier_ev = self._close_on_main_locked(mux, was_active, on_watcher)
            elif was_active:
                barrier_ev = self._enqueue_retire_barrier_locked(mux, on_watcher)
        _finish_main_drain(handles)
        if barrier_ev is not None:
            barrier_ev.wait(timeout=1.0)
            self._mark_inactive()


atexit.register(SignalWakeupGuard.drain_retired_on_main)


def _mux_signal_handler(sig_num: int, frame: object) -> None:
    mux = SignalWakeupGuard._MUX
    if sig_num in mux.handled_sigs:
        return
    orig = mux.orig_handlers_snap.get(sig_num, signal.SIG_DFL)
    SignalWakeupGuard._try_drain_from_signal_handler()
    if callable(orig) and orig is not _mux_signal_handler:
        orig(sig_num, frame)
        return
    if orig == signal.SIG_DFL:
        try:
            if signal.getsignal(sig_num) is _mux_signal_handler:
                signal.signal(sig_num, signal.SIG_DFL)
        except (OSError, ValueError):
            return
        signal.raise_signal(sig_num)


def _build_managed_child_env(
    env: Optional[Mapping[str, str]],
    token_hex: str,
) -> Optional[dict[str, str]]:
    need_flags = sys.dont_write_bytecode or sys.flags.optimize > 0 or bool(token_hex)
    env_map = dict(env) if env is not None else (dict(os.environ) if need_flags else None)
    if env_map is None:
        return None
    if token_hex:
        prev_chain = env_map.get("_YSCB_TREE_ID", "").strip(",")
        env_map["_YSCB_TREE_ID"] = f"{prev_chain},{token_hex}" if prev_chain else token_hex
    if sys.dont_write_bytecode:
        env_map.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    if sys.flags.optimize > 0:
        env_map.setdefault("PYTHONOPTIMIZE", str(sys.flags.optimize))
    return env_map


class ManagedProcessTree:
    """Supervises a child OS process group/Job Object with PID-reuse protection and optional TTY inheritance."""

    def __init__(
        self,
        argv: Sequence[str],
        *,
        cwd: HostPath,
        env: Optional[Mapping[str, str]] = None,
        inherit_tty: bool = False,
    ) -> None:
        require_pure_bool(inherit_tty, "ManagedProcessTree.inherit_tty")
        clean_argv = _validate_proc_argv_and_cwd(argv, cwd, "ManagedProcessTree")
        self._owns_process_group = not inherit_tty
        tok_hex = "" if IS_WINDOWS else uuid.uuid4().hex
        self._tree_token_bytes = tok_hex.encode("ascii")
        stream_target = None if inherit_tty else subprocess.DEVNULL
        env_map = _build_managed_child_env(env, tok_hex)
        if IS_WINDOWS:
            flags = 0x00000004 | (0 if inherit_tty else subprocess.CREATE_NEW_PROCESS_GROUP)
            self._proc = subprocess.Popen(
                clean_argv,
                cwd=str(cwd),
                env=env_map,
                stdin=stream_target,
                stdout=stream_target,
                stderr=stream_target,
                close_fds=True,
                creationflags=flags,
            )
            self._job_handle = _create_win32_kill_on_close_job(self._proc.pid)
            if self._job_handle is None:
                self._proc.kill()
                self._proc.wait()
                raise OSError("Failed to bind child process to Win32 kill-on-close Job Object.")
        else:
            self._proc = subprocess.Popen(
                clean_argv,
                cwd=str(cwd),
                env=env_map,
                stdin=stream_target,
                stdout=stream_target,
                stderr=stream_target,
                close_fds=True,
                start_new_session=(not inherit_tty),
            )
            self._job_handle = None
        self._lock = threading.Lock()
        self._term_lock = threading.Lock()
        self._known_descendants: dict[int, Optional[int]] = {}
        self._tree_cleaned = False

    def __enter__(self) -> ManagedProcessTree:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.terminate_tree()

    @property
    def pid(self) -> int:
        return self._proc.pid

    def snapshot_descendants(self) -> None:
        """Capture live descendant PIDs before closing IPC channels that trigger root exit."""
        with self._lock:
            if not self._tree_cleaned:
                self._refresh_posix_descendants_unlocked()

    def _refresh_posix_descendants_unlocked(self) -> dict[int, Optional[int]]:
        if IS_WINDOWS:
            return {}
        for dpid, exp_st in list(self._known_descendants.items()):
            cur_st = _read_posix_proc_starttime(dpid)
            if not is_process_alive(dpid) or (exp_st is not None and cur_st != exp_st):
                self._known_descendants.pop(dpid, None)
        ps_snap = None if _HAS_POSIX_PROC_STAT else _snapshot_ps_tree_maps()
        ps_map = ps_snap.by_ppid if ps_snap is not None else None
        seeds = [self._proc.pid] if self._proc.returncode is None else []
        seeds.extend(self._known_descendants.keys())
        seen: set[int] = set()
        new_pids = [
            cpid
            for spid in seeds
            for cpid in _collect_posix_descendants(spid, seen, ps_map)
            if cpid not in self._known_descendants
        ]
        if self._owns_process_group:
            for gpid in _collect_orphan_pgid_members_posix(self._proc.pid, seen, ps_snap):
                if gpid not in self._known_descendants:
                    new_pids.append(gpid)
        if self._tree_token_bytes:
            for dpid in _collect_procfs_env_token_pids(self._tree_token_bytes, self._proc.pid, seen, ps_map):
                if dpid not in self._known_descendants:
                    new_pids.append(dpid)
        for cpid in new_pids:
            st = _read_posix_proc_starttime(cpid)
            if st is not None or not _HAS_POSIX_PROC_STARTTIME:
                self._known_descendants[cpid] = st
        return dict(self._known_descendants)

    def _peek_exited_without_reap_posix(self) -> bool:
        if IS_WINDOWS or self._proc.returncode is not None:
            return self._proc.returncode is not None
        try:
            return os.waitid(os.P_PID, self._proc.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG) is not None
        except AttributeError:
            return not _is_process_alive_posix(self._proc.pid)
        except ChildProcessError:
            return True
        except OSError:
            return not _is_process_alive_posix(self._proc.pid)

    def _sweep_residual_descendants_unlocked(self, *, allow_group_kill: bool) -> None:
        if IS_WINDOWS:
            self._kill_residual_group()
            return
        targets = self._refresh_posix_descendants_unlocked()
        if allow_group_kill and self._owns_process_group and self._proc.returncode is None:
            self._kill_residual_group()
        _signal_posix_descendants(targets, int(signal.SIGKILL))
        _await_posix_descendants_dead(targets)

    def _finalize_exited_tree_unlocked(self, *, root_unreaped: bool) -> None:
        if self._tree_cleaned:
            return
        self._sweep_residual_descendants_unlocked(allow_group_kill=root_unreaped)
        self._tree_cleaned = True

    def peek_alive(self) -> bool:
        with self._lock:
            if self._proc.returncode is not None or self._tree_cleaned:
                return False
            if IS_WINDOWS:
                return _is_process_alive_windows(self._proc.pid)
            return not self._peek_exited_without_reap_posix()

    def poll(self) -> Optional[int]:
        with self._lock:
            if not self._tree_cleaned and self._peek_exited_without_reap_posix():
                self._finalize_exited_tree_unlocked(root_unreaped=True)
            rc = self._proc.poll()
            if rc is not None:
                self._finalize_exited_tree_unlocked(root_unreaped=False)
            return rc

    def _reap_if_exited_unlocked(self) -> bool:
        if self._peek_exited_without_reap_posix():
            self._finalize_exited_tree_unlocked(root_unreaped=True)
            _ = self._proc.poll()
            return True
        if self._proc.poll() is not None:
            self._finalize_exited_tree_unlocked(root_unreaped=False)
            return True
        return False

    def _poll_reaped(self) -> bool:
        with self._lock:
            return self._tree_cleaned or self._reap_if_exited_unlocked()

    def _wait_graceful_exit(self, grace_sec: float) -> bool:
        if IS_WINDOWS:
            try:
                self._proc.wait(timeout=grace_sec)
            except subprocess.TimeoutExpired:
                return False
            with self._lock:
                self._finalize_exited_tree_unlocked(root_unreaped=False)
            return True
        deadline = time.monotonic() + grace_sec
        step = 0.002
        while time.monotonic() < deadline:
            if self._poll_reaped():
                return True
            time.sleep(min(step, max(0.001, deadline - time.monotonic())))
            step = min(0.015, step * 2.0)
        return self._poll_reaped()

    def _force_kill_and_reap(self) -> None:
        with self._lock:
            if self._tree_cleaned:
                return
            self._sweep_residual_descendants_unlocked(allow_group_kill=(self._proc.returncode is None))
            if self._proc.returncode is None:
                try:
                    self._proc.kill()
                except OSError:
                    pass
        try:
            self._proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            pass
        with self._lock:
            self._finalize_exited_tree_unlocked(root_unreaped=(self._proc.returncode is None))

    def terminate_tree(self, *, grace_sec: float = 0.5) -> None:
        """Gracefully signal the entire process group once, escalating to hard kill and reaping."""
        safe_grace = require_non_none(clamp_wait_sec(grace_sec, min_sec=0.05))
        with self._term_lock:
            with self._lock:
                if self._tree_cleaned or self._reap_if_exited_unlocked():
                    return
                self._send_graceful_group_signal()
            if self._wait_graceful_exit(safe_grace):
                return
            self._force_kill_and_reap()

    def kill_tree_now(self) -> None:
        """Immediately force-kill the entire process group/tree once and reap the root Popen."""
        with self._term_lock:
            self._force_kill_and_reap()

    def _send_graceful_group_signal(self) -> None:
        if IS_WINDOWS:
            if self._owns_process_group:
                try:
                    self._proc.send_signal(signal.CTRL_BREAK_EVENT)
                except (AttributeError, OSError):
                    pass
            return
        targets = self._refresh_posix_descendants_unlocked()
        if self._owns_process_group:
            try:
                os.killpg(self._proc.pid, signal.SIGTERM)
            except OSError:
                try:
                    self._proc.terminate()
                except OSError:
                    pass
        else:
            try:
                self._proc.terminate()
            except OSError:
                pass
        _signal_posix_descendants(targets, int(signal.SIGTERM))

    def _kill_residual_group(self) -> None:
        if IS_WINDOWS:
            if self._job_handle is not None:
                _close_win32_job(self._job_handle)
                self._job_handle = None
            return
        try:
            os.killpg(self._proc.pid, signal.SIGKILL)
        except OSError:
            pass
