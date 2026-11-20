"""Cross-platform OS process-tree supervision, detached daemon spawning, and liveness probes."""

from __future__ import annotations

import atexit
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
import errno
import functools
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Callable, ClassVar, Final, Iterator, Mapping, Optional, Sequence
import uuid

from core.foundation.errors import safe_exception_summary
from core.foundation.primitives import (
    IS_WINDOWS,
    PYTHON_LAUNCHER_HIJACK_ENV_KEYS,
    TREE_ID_ENV_KEY,
    HostPath,
    clamp_wait_sec,
    invoke_observer_safely,
    require_non_none,
    require_pure_bool,
    require_typed_tuple,
)

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

    _WIN_GET_TIMES = _WIN_K32.GetProcessTimes
    _WIN_GET_TIMES.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    _WIN_GET_TIMES.restype = wintypes.BOOL

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
    # Allow explicit CREATE_BREAKAWAY_FROM_JOB (spawn_detached) while killing normal child trees on job close.
    info.BasicLimitInformation.LimitFlags = 0x00002000 | 0x00000800
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
        if int(_WIN_RESUME_PROC(proc_handle)) < 0:
            _WIN_TERM_JOB(job, 1)
            _WIN_CLOSE_HANDLE(job)
            return None
        return int(job)
    finally:
        _WIN_CLOSE_HANDLE(proc_handle)


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


def _darwin_query_bsdinfo(pid: int) -> tuple[Optional[_DarwinBsdStat], int]:
    if sys.platform != "darwin" or pid <= 0:
        return (None, 0)
    info = _DarwinProcBsdInfo()
    sz = ctypes.sizeof(info)
    ctypes.set_errno(0)
    ret = int(_DARWIN_PROC_PIDINFO(pid, 3, 0, ctypes.byref(info), sz))
    if ret != sz:
        return (None, int(ctypes.get_errno()))
    start_us = int(info.pbi_start_tvsec) * 1_000_000 + int(info.pbi_start_tvusec)
    return (_DarwinBsdStat(int(info.pbi_status), int(info.pbi_ppid), int(info.pbi_pgid), start_us), 0)


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
        bsd_st, err_no = _darwin_query_bsdinfo(pid)
        if bsd_st is not None:
            return bsd_st.status == 5
        if err_no == errno.ESRCH:
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


def _read_windows_proc_starttime(pid: int) -> Optional[int]:
    if not IS_WINDOWS or pid <= 0:
        return None
    handle = _WIN_OPEN_PROC(0x1000, False, pid)
    if not handle:
        return None
    try:
        ct = wintypes.FILETIME()
        et = wintypes.FILETIME()
        kt = wintypes.FILETIME()
        ut = wintypes.FILETIME()
        if not _WIN_GET_TIMES(handle, ctypes.byref(ct), ctypes.byref(et), ctypes.byref(kt), ctypes.byref(ut)):
            return None
        return (int(ct.dwHighDateTime) << 32) | int(ct.dwLowDateTime)
    finally:
        _WIN_CLOSE_HANDLE(handle)


def get_process_start_tag(pid: int) -> Optional[str]:
    """Return an OS process creation-time fingerprint string for PID-reuse detection when supported."""
    if not is_process_alive(pid):
        return None
    st = _read_windows_proc_starttime(pid) if IS_WINDOWS else _read_posix_proc_starttime(pid)
    return str(st) if st is not None else None


def _validate_proc_argv_and_cwd(argv: Sequence[str], cwd: HostPath, label: str) -> list[str]:
    if not isinstance(cwd, HostPath):
        raise ValueError(f"{label} cwd must be HostPath, got {cwd!r}")
    tup = require_typed_tuple(argv, str, f"{label} argv")
    if not tup or any("\x00" in seg for seg in tup):
        raise ValueError(f"{label} argv must be a non-empty NUL-free Sequence[str].")
    return list(tup)


_STRIPPED_LAUNCHER_ENV_KEYS: Final[tuple[str, ...]] = (
    TREE_ID_ENV_KEY,
    *PYTHON_LAUNCHER_HIJACK_ENV_KEYS,
)
_STRIPPED_LAUNCHER_ENV_UPPER: Final[frozenset[str]] = frozenset(k.upper() for k in _STRIPPED_LAUNCHER_ENV_KEYS)


def _validate_process_env_map(env: Mapping[str, str], label: str) -> dict[str, str]:
    if not isinstance(env, Mapping):
        raise ValueError(f"{label} must be Mapping[str, str], got {type(env).__name__}")
    cleaned: dict[str, str] = {}
    for k, v in env.items():
        if type(k) is not str or type(v) is not str:
            raise ValueError(f"{label} entries must be plain str->str")
        if not k or "=" in k or "\x00" in k or "\x00" in v:
            raise ValueError(f"{label} contains invalid NUL or '=' in key/value: {k!r}")
        try:
            k.encode("utf-8", errors="strict")
            v.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"{label} contains non-UTF-8 surrogates") from exc
        cleaned[k] = v
    return cleaned


def _strip_launcher_env_keys(env_map: dict[str, str]) -> None:
    for k in [key for key in env_map if key.upper() in _STRIPPED_LAUNCHER_ENV_UPPER]:
        env_map.pop(k, None)


_DETACHED_LAUNCHER_TAG: Final[str] = "_yscb_detached_launcher_v2"


def spawn_detached(
    argv: Sequence[str],
    *,
    cwd: HostPath,
    extra_env: Optional[Mapping[str, str]] = None,
) -> int:
    """Spawn a fully detached background process surviving parent ManagedProcessTree teardown (0 ResourceWarning)."""
    clean_argv = _validate_proc_argv_and_cwd(argv, cwd, "spawn_detached")
    merged_extra = _validate_process_env_map(extra_env, "spawn_detached extra_env") if extra_env is not None else {}
    _strip_launcher_env_keys(merged_extra)
    launcher_code = "\n".join(
        (
            f"# {_DETACHED_LAUNCHER_TAG}",
            "import json, os, subprocess, sys, warnings",
            "warnings.simplefilter('ignore', ResourceWarning)",
            "cfg = json.loads(sys.stdin.read())",
            "env = dict(os.environ)",
            "env.update(cfg.get('extra_env') or {})",
            f"stripped = {sorted(_STRIPPED_LAUNCHER_ENV_UPPER)!r}",
            "for k in [x for x in env if x.upper() in stripped]: env.pop(k, None)",
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
    outer_env = dict(os.environ)
    _strip_launcher_env_keys(outer_env)
    if sys.dont_write_bytecode:
        outer_env["PYTHONDONTWRITEBYTECODE"] = "1"
        merged_extra.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    if sys.flags.optimize > 0:
        outer_env["PYTHONOPTIMIZE"] = str(sys.flags.optimize)
        merged_extra.setdefault("PYTHONOPTIMIZE", str(sys.flags.optimize))
    opt_flags = [f"-{'O' * min(2, sys.flags.optimize)}"] if sys.flags.optimize > 0 else []
    payload = json.dumps({"argv": clean_argv, "cwd": str(cwd), "extra_env": merged_extra})
    launcher_argv = [sys.executable, *(["-B"] if sys.dont_write_bytecode else []), *opt_flags, "-c", launcher_code]
    try:
        if IS_WINDOWS:
            try:
                completed = subprocess.run(
                    launcher_argv,
                    input=payload,
                    cwd=str(cwd),
                    env=outer_env,
                    creationflags=0x00000200 | 0x01000000,
                    capture_output=True,
                    text=True,
                    timeout=10.0,
                    check=True,
                )
            except OSError:
                completed = subprocess.run(
                    launcher_argv,
                    input=payload,
                    cwd=str(cwd),
                    env=outer_env,
                    creationflags=0x00000200,
                    capture_output=True,
                    text=True,
                    timeout=10.0,
                    check=True,
                )
        else:
            completed = subprocess.run(
                launcher_argv,
                input=payload,
                cwd=str(cwd),
                env=outer_env,
                start_new_session=True,
                capture_output=True,
                text=True,
                timeout=10.0,
                check=True,
            )
        return int(completed.stdout.strip())
    except subprocess.CalledProcessError as exc:
        err_tail = (exc.stderr or "").strip()[:200]
        raise OSError(f"Failed to spawn detached process (rc={exc.returncode}): {err_tail}") from None
    except subprocess.TimeoutExpired as exc:
        raise OSError(f"Timed out spawning detached process after {exc.timeout}s") from None
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
    used_bytes = 0
    for _ in range(4):
        buf = (ctypes.c_int * cap_cnt)()
        used_bytes = int(_DARWIN_PROC_LISTPIDS(1, 0, ctypes.byref(buf), cap_cnt * 4))
        if used_bytes <= 0:
            return None
        if used_bytes < cap_cnt * 4:
            break
        cap_cnt *= 2
    by_ppid: dict[int, list[int]] = {}
    by_pgid: dict[int, list[int]] = {}
    for idx in range(min(cap_cnt, used_bytes // 4)):
        pid_v = int(buf[idx])
        bsd_st = _darwin_query_bsdinfo(pid_v)[0] if pid_v > 0 else None
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
        bsd_st, _err = _darwin_query_bsdinfo(pid)
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


def _ps_command_contains_tree_token(cmd_text: str, token_str: str) -> bool:
    marker = f"{TREE_ID_ENV_KEY}="
    if marker not in cmd_text or not token_str:
        return False
    for tok in cmd_text.split():
        if tok.startswith(marker) and token_str in tok[len(marker) :].split(","):
            return True
    return False


def _is_detached_untagged_session_child(
    cpid: int,
    root_sid: Optional[int],
    tree_token_bytes: bytes,
) -> bool:
    if IS_WINDOWS or root_sid is None or not tree_token_bytes:
        return False
    try:
        child_sid = os.getsid(cpid)
    except OSError:
        return False
    if child_sid == root_sid:
        return False
    if _has_posix_proc_stat():
        try:
            env_raw = Path(f"/proc/{cpid}/environ").read_bytes()
        except OSError:
            return False
        return not _environ_contains_tree_token(env_raw, tree_token_bytes)
    token_str = tree_token_bytes.decode("ascii", errors="ignore")
    if not token_str:
        return False
    try:
        cp = subprocess.run(
            ["ps", "eww", "-p", str(cpid), "-o", "command="],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if cp.returncode != 0 or not cp.stdout.strip():
        return False
    if _ps_command_contains_tree_token(cp.stdout, token_str):
        return False
    if _DETACHED_LAUNCHER_TAG in cp.stdout:
        return True
    return sys.platform != "darwin"


def _collect_posix_descendants_walk(
    root_pid: int,
    seen: set[int],
    ps_map: Optional[dict[int, list[int]]],
    *,
    root_sid: Optional[int] = None,
    tree_token_bytes: bytes = b"",
) -> list[int]:
    if root_pid <= 0 or root_pid in seen:
        return []
    seen.add(root_pid)
    ordered: list[int] = []
    for cpid in _read_direct_proc_children(root_pid, ps_map):
        if _is_detached_untagged_session_child(cpid, root_sid, tree_token_bytes):
            continue
        ordered.extend(
            _collect_posix_descendants_walk(
                cpid,
                seen,
                ps_map,
                root_sid=root_sid,
                tree_token_bytes=tree_token_bytes,
            )
        )
        ordered.append(cpid)
    return ordered


@functools.lru_cache(maxsize=1)
def _has_posix_proc_stat() -> bool:
    return (not IS_WINDOWS) and Path("/proc/self/stat").is_file()


def _has_posix_proc_starttime() -> bool:
    return _has_posix_proc_stat() or sys.platform == "darwin"


def _collect_posix_descendants(
    root_pid: int,
    seen: set[int],
    ps_map: Optional[dict[int, list[int]]] = None,
    *,
    tree_token_bytes: bytes = b"",
) -> list[int]:
    if IS_WINDOWS or root_pid <= 0:
        return []
    if not _has_posix_proc_stat() and ps_map is None:
        ps_map = _snapshot_ps_tree_maps().by_ppid
    root_sid: Optional[int] = None
    if tree_token_bytes:
        try:
            root_sid = os.getsid(root_pid)
        except OSError:
            root_sid = None
    return _collect_posix_descendants_walk(
        root_pid,
        seen,
        ps_map,
        root_sid=root_sid,
        tree_token_bytes=tree_token_bytes,
    )


def _is_targeted_descendant_alive(dpid: int, exp_st: Optional[int]) -> bool:
    if dpid <= 1 or not is_process_alive(dpid):
        return False
    if _has_posix_proc_starttime() and (exp_st is None or _read_posix_proc_starttime(dpid) != exp_st):
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


def _parse_procfs_live_stat_entry(entry_name: str) -> Optional[tuple[int, int, int]]:
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
    if len(fields) < 3 or fields[0] == "Z" or not fields[1].lstrip("-").isdigit() or not fields[2].lstrip("-").isdigit():
        return None
    return (pid_v, int(fields[1]), int(fields[2]))


def _snapshot_procfs_tree_maps() -> _PosixPsSnapshot:
    by_ppid: dict[int, list[int]] = {}
    by_pgid: dict[int, list[int]] = {}
    try:
        entries = [e.name for e in Path("/proc").iterdir()]
    except OSError:
        return _PosixPsSnapshot({}, {})
    for name in entries:
        parsed = _parse_procfs_live_stat_entry(name)
        if parsed is None:
            continue
        pid_v, ppid_v, pgid_v = parsed
        by_ppid.setdefault(ppid_v, []).append(pid_v)
        by_pgid.setdefault(pgid_v, []).append(pid_v)
    return _PosixPsSnapshot(by_ppid, by_pgid)


def _collect_orphan_pgid_members_posix(
    root_pid: int,
    seen: set[int],
    ps_snap: Optional[_PosixPsSnapshot] = None,
    *,
    tree_token_bytes: bytes = b"",
) -> list[int]:
    if IS_WINDOWS or root_pid <= 0 or is_process_alive(root_pid):
        return []
    snap = ps_snap or (_snapshot_procfs_tree_maps() if _has_posix_proc_stat() else _snapshot_ps_tree_maps())
    out: list[int] = []
    for p in snap.by_pgid.get(root_pid, ()):
        if p != root_pid and p not in seen:
            seen.add(p)
            out.append(p)
    idx = 0
    while idx < len(out):
        cur = out[idx]
        idx += 1
        cur_sid: Optional[int] = None
        if tree_token_bytes:
            try:
                cur_sid = os.getsid(cur)
            except OSError:
                cur_sid = root_pid
        for ch in snap.by_ppid.get(cur, ()):
            if ch != root_pid and ch not in seen:
                if _is_detached_untagged_session_child(ch, cur_sid, tree_token_bytes):
                    continue
                seen.add(ch)
                out.append(ch)
    return out


def _environ_contains_tree_token(env_raw: bytes, token_bytes: bytes) -> bool:
    prefix_b = f"{TREE_ID_ENV_KEY}=".encode("ascii")
    for entry in env_raw.split(b"\x00"):
        if entry.startswith(prefix_b):
            return token_bytes in entry[len(prefix_b) :].split(b",")
    return False


def _collect_ps_env_token_roots_fallback(
    token_bytes: bytes,
    root_pid: int,
    seen: set[int],
) -> list[int]:
    token_str = token_bytes.decode("ascii", errors="ignore")
    if not token_str:
        return []
    me = os.getpid()
    try:
        cp = subprocess.run(
            ["ps", "eww", "-ax", "-o", "pid=,command="],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
    except OSError:
        return []
    roots: list[int] = []
    for line in cp.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        pid_v = int(parts[0])
        if pid_v in (me, root_pid) or pid_v in seen:
            continue
        if _ps_command_contains_tree_token(parts[1], token_str):
            roots.append(pid_v)
    return roots


def _collect_posix_env_token_pids(
    token_bytes: bytes,
    root_pid: int,
    seen: set[int],
    ps_map: Optional[dict[int, list[int]]] = None,
) -> list[int]:
    if IS_WINDOWS or not token_bytes:
        return []
    if not _has_posix_proc_stat():
        fb_roots = _collect_ps_env_token_roots_fallback(token_bytes, root_pid, seen)
        return [dpid for tpid in fb_roots for dpid in (*_collect_posix_descendants(tpid, seen, ps_map, tree_token_bytes=token_bytes), tpid)]
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
    return [dpid for tpid in roots for dpid in (*_collect_posix_descendants(tpid, seen, ps_map, tree_token_bytes=token_bytes), tpid)]


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


@dataclass(frozen=True, slots=True)
class _MuxWorkItem:
    targets: tuple[SignalWakeupGuard, ...]
    sig_byte: int
    barrier: Optional[tuple[SignalWakeupGuard, threading.Event]] = None


@dataclass(slots=True)
class _SignalMuxState:
    _INSTANCE: ClassVar[Optional[_SignalMuxState]] = None
    _INIT_LOCK: ClassVar[threading.Lock] = threading.Lock()

    lock: threading.Lock = field(default_factory=threading.Lock)
    active_guards: list[SignalWakeupGuard] = field(default_factory=list)
    retiring_barriers: deque[tuple[SignalWakeupGuard, threading.Event]] = field(default_factory=deque)
    dispatch_queue: deque[_MuxWorkItem] = field(default_factory=deque)
    in_flight_guards: tuple[SignalWakeupGuard, ...] = ()
    dispatch_wake: threading.Event = field(default_factory=threading.Event)
    absorbed_credits: dict[int, int] = field(default_factory=dict)
    orig_handlers: dict[int, object] = field(default_factory=dict)
    deferred_main_signals: deque[tuple[int, object]] = field(default_factory=deque)
    main_active_tokens: list[int] = field(default_factory=list)
    rsock: Optional[socket.socket] = None
    wsock: Optional[socket.socket] = None
    prev_wakeup_fd: int = -1
    watcher_thread: Optional[threading.Thread] = None
    pipe_eof: bool = False

    @classmethod
    def instance(cls) -> _SignalMuxState:
        inst = cls._INSTANCE
        if inst is not None:
            return inst
        with cls._INIT_LOCK:
            if cls._INSTANCE is None:
                cls._INSTANCE = cls()
                atexit.register(SignalWakeupGuard.drain_retired_on_main)
            return cls._INSTANCE


def _guarded_mux_sigs_locked(mux: _SignalMuxState) -> set[int]:
    sigs = {s for g in mux.active_guards for s in g.sig_nums}
    for rg, _ev in mux.retiring_barriers:
        sigs.update(rg.sig_nums)
    for ig in mux.in_flight_guards:
        if ig.is_installed:
            sigs.update(ig.sig_nums)
    for item in mux.dispatch_queue:
        for tg in item.targets:
            if tg.is_installed:
                sigs.update(tg.sig_nums)
        if item.barrier is not None:
            sigs.update(item.barrier[0].sig_nums)
    return sigs


def _needed_mux_sigs_locked(mux: _SignalMuxState) -> set[int]:
    sigs = _guarded_mux_sigs_locked(mux)
    for sig_num, cnt in mux.absorbed_credits.items():
        if cnt > 0:
            sigs.add(sig_num)
    return sigs


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


def _pump_pipe_bytes_into_queue_locked(mux: _SignalMuxState) -> None:
    rs = mux.rsock
    if rs is None:
        return
    while True:
        try:
            data = rs.recv(128)
        except BlockingIOError:
            break
        except OSError:
            mux.pipe_eof = True
            break
        if not data:
            mux.pipe_eof = True
            break
        for b_val in data:
            if b_val == 0:
                if mux.retiring_barriers:
                    bar = mux.retiring_barriers.popleft()
                    mux.dispatch_queue.append(_MuxWorkItem((), 0, bar))
                    mux.dispatch_wake.set()
            else:
                _forward_wakeup_bytes(mux.prev_wakeup_fd, bytes((b_val,)))
                candidates: list[SignalWakeupGuard] = []
                for g in (*mux.active_guards, *(rg for rg, _ev in mux.retiring_barriers), *mux.in_flight_guards):
                    if g not in candidates and g.is_installed and b_val in g.sig_nums:
                        candidates.append(g)
                targets = tuple(candidates)
                if targets:
                    mux.absorbed_credits[b_val] = mux.absorbed_credits.get(b_val, 0) + 1
                    mux.dispatch_queue.append(_MuxWorkItem(targets, b_val, None))
                    mux.dispatch_wake.set()


def _restore_unused_mux_handlers_locked(mux: _SignalMuxState, needed: set[int]) -> None:
    for sig_num in [s for s in mux.orig_handlers if s not in needed]:
        old_h = mux.orig_handlers.pop(sig_num)
        try:
            if signal.getsignal(sig_num) is _handle_signal_on_main:
                signal.signal(sig_num, old_h)
        except (OSError, ValueError):
            continue


def _detach_mux_on_main_locked(mux: _SignalMuxState) -> _MainDrainHandles:
    _pump_pipe_bytes_into_queue_locked(mux)
    while mux.retiring_barriers:
        mux.dispatch_queue.append(_MuxWorkItem((), 0, mux.retiring_barriers.popleft()))
    mux.dispatch_wake.set()
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
    mux.rsock = None
    mux.wsock = None
    mux.watcher_thread = None
    mux.pipe_eof = True
    return _MainDrainHandles(ws, wt)


def _finish_main_drain(handles: _MainDrainHandles, *, join_watcher: bool = True) -> None:
    ws = handles.wsock
    try:
        if ws is not None:
            try:
                ws.shutdown(socket.SHUT_WR)
            except OSError:
                pass
        wt = handles.watcher
        if join_watcher and wt is not None and wt is not threading.current_thread() and wt.is_alive():
            wt.join(timeout=1.0)
    finally:
        if ws is not None:
            _close_sock_quietly(ws)


def _ensure_mux_pipe_locked(mux: _SignalMuxState) -> tuple[bool, _MainDrainHandles]:
    if mux.wsock is not None and mux.rsock is not None and mux.watcher_thread is not None and mux.watcher_thread.is_alive():
        return (True, _MainDrainHandles())
    stale = _detach_mux_on_main_locked(mux)
    rsock, wsock = socket.socketpair()
    rsock.setblocking(False)
    wsock.setblocking(False)
    try:
        prev_fd = signal.set_wakeup_fd(wsock.fileno(), warn_on_full_buffer=False)
    except (OSError, ValueError):
        _close_sock_quietly(wsock)
        _close_sock_quietly(rsock)
        return (False, stale)
    mux.pipe_eof = False
    mux.rsock = rsock
    mux.wsock = wsock
    mux.prev_wakeup_fd = prev_fd
    wt = threading.Thread(target=_mux_watch_loop, args=(mux, rsock), name="yscb-sig-wakeup", daemon=True)
    mux.watcher_thread = wt
    try:
        wt.start()
    except BaseException:
        mux.rsock = None
        mux.wsock = None
        mux.prev_wakeup_fd = -1
        mux.watcher_thread = None
        mux.pipe_eof = True
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
            if cur_h is _handle_signal_on_main:
                mux.orig_handlers.setdefault(sig_num, signal.SIG_DFL)
                any_ok = True
                continue
            mux.orig_handlers[sig_num] = cur_h
            signal.signal(sig_num, _handle_signal_on_main)
            any_ok = True
        except (OSError, ValueError):
            mux.orig_handlers.pop(sig_num, None)
    return any_ok


def _mux_watch_loop(mux: _SignalMuxState, my_rsock: socket.socket) -> None:
    try:
        with selectors.DefaultSelector() as sel:
            try:
                sel.register(my_rsock, selectors.EVENT_READ)
            except (OSError, ValueError):
                return
            try:
                while True:
                    item: Optional[_MuxWorkItem] = None
                    exit_loop = False
                    with _locked_mux(mux):
                        if mux.rsock is my_rsock:
                            _pump_pipe_bytes_into_queue_locked(mux)
                        if mux.dispatch_queue:
                            item = mux.dispatch_queue.popleft()
                            if item.barrier is None:
                                mux.in_flight_guards = item.targets
                        else:
                            mux.dispatch_wake.clear()
                            exit_loop = (mux.rsock is not my_rsock) or mux.pipe_eof
                    if item is not None:
                        if item.barrier is not None:
                            item.barrier[0].mark_inactive()
                            item.barrier[1].set()
                        else:
                            try:
                                for guard in item.targets:
                                    guard.dispatch_signal(item.sig_byte)
                            finally:
                                with _locked_mux(mux):
                                    if mux.rsock is my_rsock:
                                        _pump_pipe_bytes_into_queue_locked(mux)
                                    mux.in_flight_guards = ()
                        continue
                    if exit_loop:
                        return
                    try:
                        sel.select(timeout=0.04)
                    except (OSError, ValueError):
                        return
            finally:
                try:
                    sel.unregister(my_rsock)
                except (KeyError, OSError, ValueError):
                    pass
    finally:
        leftover: list[_MuxWorkItem] = []
        with _locked_mux(mux):
            if mux.rsock is my_rsock or mux.rsock is None:
                while mux.retiring_barriers:
                    leftover.append(_MuxWorkItem((), 0, mux.retiring_barriers.popleft()))
                while mux.dispatch_queue:
                    leftover.append(mux.dispatch_queue.popleft())
        for rem in leftover:
            if rem.barrier is not None:
                rem.barrier[0].mark_inactive()
                rem.barrier[1].set()
            else:
                for guard in rem.targets:
                    guard.dispatch_signal(rem.sig_byte)
        _close_sock_quietly(my_rsock)


@contextmanager
def _locked_mux(mux: _SignalMuxState) -> Iterator[_SignalMuxState]:
    is_main = threading.current_thread() is threading.main_thread()
    if is_main:
        mux.main_active_tokens.append(1)
    try:
        mux.lock.acquire()
        try:
            yield mux
        finally:
            mux.lock.release()
    finally:
        if is_main:
            mux.main_active_tokens.pop()
    if is_main and not mux.main_active_tokens and mux.deferred_main_signals:
        _drain_deferred_main_signals(mux)


def _process_main_signal_once(mux: _SignalMuxState, sig_num: int, frame: object) -> None:
    absorbed = False
    orig: object = signal.SIG_DFL
    handles = _MainDrainHandles()
    mux.lock.acquire()
    try:
        _pump_pipe_bytes_into_queue_locked(mux)
        orig = mux.orig_handlers.get(sig_num, signal.SIG_DFL)
        cur_cred = mux.absorbed_credits.get(sig_num, 0)
        guarded_sigs = _guarded_mux_sigs_locked(mux)
        has_more_def = any(s_n == sig_num for s_n, _f in mux.deferred_main_signals)
        if cur_cred > 0:
            absorbed = True
            new_cred = (cur_cred - 1) if (sig_num in guarded_sigs or has_more_def) else 0
            if new_cred > 0:
                mux.absorbed_credits[sig_num] = new_cred
            else:
                mux.absorbed_credits.pop(sig_num, None)
        needed = _needed_mux_sigs_locked(mux)
        if needed:
            _restore_unused_mux_handlers_locked(mux, needed)
        elif not mux.dispatch_queue and (bool(mux.orig_handlers) or mux.wsock is not None):
            handles = _detach_mux_on_main_locked(mux)
    finally:
        mux.lock.release()
    _finish_main_drain(handles, join_watcher=False)
    if absorbed:
        return
    if callable(orig) and orig is not _handle_signal_on_main:
        orig(sig_num, frame)
        return
    if orig == signal.SIG_DFL:
        try:
            if signal.getsignal(sig_num) is _handle_signal_on_main:
                signal.signal(sig_num, signal.SIG_DFL)
        except (OSError, ValueError):
            return
        signal.raise_signal(sig_num)


def _drain_deferred_main_signals(mux: _SignalMuxState) -> None:
    while mux.deferred_main_signals:
        mux.main_active_tokens.append(1)
        try:
            while mux.deferred_main_signals:
                try:
                    s_num, s_frame = mux.deferred_main_signals.popleft()
                except IndexError:
                    break
                _process_main_signal_once(mux, s_num, s_frame)
        finally:
            mux.main_active_tokens.pop()


def _handle_signal_on_main(sig_num: int, frame: object) -> None:
    mux = _SignalMuxState.instance()
    mux.deferred_main_signals.append((sig_num, frame))
    if mux.main_active_tokens:
        return
    _drain_deferred_main_signals(mux)


class SignalWakeupGuard:
    """Routes main-thread OS signals through a single FIFO-barrier C-level set_wakeup_fd coordinator."""

    @classmethod
    def drain_retired_on_main(cls) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        handles = _MainDrainHandles()
        try:
            with _locked_mux(_SignalMuxState.instance()) as mux:
                _pump_pipe_bytes_into_queue_locked(mux)
                needed = _needed_mux_sigs_locked(mux)
                if needed:
                    _restore_unused_mux_handlers_locked(mux, needed)
                elif bool(mux.orig_handlers) or mux.wsock is not None:
                    handles = _detach_mux_on_main_locked(mux)
        finally:
            _finish_main_drain(handles)

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

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _ = (exc_type, exc, tb)
        self.close()

    @contextmanager
    def _locked_guard_state(self) -> Iterator[None]:
        is_main = threading.current_thread() is threading.main_thread()
        mux = _SignalMuxState.instance() if is_main else None
        if mux is not None:
            mux.main_active_tokens.append(1)
        try:
            self._state_lock.acquire()
            try:
                yield
            finally:
                self._state_lock.release()
        finally:
            if mux is not None:
                mux.main_active_tokens.pop()
        if mux is not None and not mux.main_active_tokens and mux.deferred_main_signals:
            _drain_deferred_main_signals(mux)

    @property
    def is_installed(self) -> bool:
        return self._installed

    def mark_inactive(self) -> None:
        self._installed = False

    def dispatch_signal(self, sig_num: int) -> None:
        if sig_num not in self._sig_nums or not self._installed:
            return
        with self._locked_guard_state():
            if not self._installed:
                return
            was_first = self._seen_hits == 0
            self._seen_hits += 1
        if was_first:
            invoke_observer_safely(self._on_signal)
            return
        if self._on_second_signal is not None and self._installed:
            invoke_observer_safely(self._on_second_signal)

    def _activate_guard_locked(self, mux: _SignalMuxState) -> _MainDrainHandles:
        with self._state_lock:
            self._seen_hits = 0
            self._installed = True
        mux.active_guards.append(self)
        if _register_mux_signals_locked(mux, self._sig_nums):
            return _MainDrainHandles()
        mux.active_guards.remove(self)
        self.mark_inactive()
        return _detach_mux_on_main_locked(mux) if not _needed_mux_sigs_locked(mux) else _MainDrainHandles()

    def install(self) -> None:
        if threading.current_thread() is not threading.main_thread() or not self._sig_nums:
            return
        stale = _MainDrainHandles()
        abort_drain = _MainDrainHandles()
        try:
            with _locked_mux(_SignalMuxState.instance()) as mux:
                _pump_pipe_bytes_into_queue_locked(mux)
                if self in mux.active_guards:
                    return
                pipe_ok, stale = _ensure_mux_pipe_locked(mux)
                if pipe_ok:
                    abort_drain = self._activate_guard_locked(mux)
        finally:
            try:
                _finish_main_drain(stale)
            finally:
                _finish_main_drain(abort_drain)

    def _enqueue_retire_barrier_locked(self, mux: _SignalMuxState, on_watcher: bool) -> Optional[threading.Event]:
        if on_watcher or mux.wsock is None or mux.watcher_thread is None or not mux.watcher_thread.is_alive():
            self.mark_inactive()
            return None
        done_ev = threading.Event()
        mux.retiring_barriers.append((self, done_ev))
        try:
            mux.wsock.send(b"\x00")
            _pump_pipe_bytes_into_queue_locked(mux)
            return done_ev
        except OSError:
            if (self, done_ev) in mux.retiring_barriers:
                mux.retiring_barriers.remove((self, done_ev))
            self.mark_inactive()
            return None

    @property
    def sig_nums(self) -> frozenset[int]:
        return self._sig_nums

    def close(self) -> None:
        cur_th = threading.current_thread()
        is_main = cur_th is threading.main_thread()
        barrier_ev: Optional[threading.Event] = None
        with _locked_mux(_SignalMuxState.instance()) as mux:
            _pump_pipe_bytes_into_queue_locked(mux)
            on_watcher = cur_th is mux.watcher_thread
            if self in mux.active_guards:
                mux.active_guards.remove(self)
                barrier_ev = self._enqueue_retire_barrier_locked(mux, on_watcher)
            else:
                self.mark_inactive()
        try:
            if barrier_ev is not None:
                barrier_ev.wait(timeout=1.0)
                if is_main:
                    time.sleep(0.0)
        finally:
            self.mark_inactive()
            handles = _MainDrainHandles()
            try:
                with _locked_mux(_SignalMuxState.instance()) as mux:
                    _pump_pipe_bytes_into_queue_locked(mux)
                    if barrier_ev is not None and (self, barrier_ev) in mux.retiring_barriers:
                        mux.retiring_barriers.remove((self, barrier_ev))
                    if is_main:
                        still_guarded = _guarded_mux_sigs_locked(mux)
                        def_sigs = {sn for sn, _f in mux.deferred_main_signals}
                        for s_k in [k for k in mux.absorbed_credits if k not in still_guarded and k not in def_sigs]:
                            mux.absorbed_credits.pop(s_k, None)
                        needed = _needed_mux_sigs_locked(mux)
                        if needed:
                            _restore_unused_mux_handlers_locked(mux, needed)
                        elif bool(mux.orig_handlers) or mux.wsock is not None:
                            handles = _detach_mux_on_main_locked(mux)
            finally:
                _finish_main_drain(handles)




_MANAGED_HIJACK_ENV_UPPER: Final[frozenset[str]] = frozenset(k.upper() for k in PYTHON_LAUNCHER_HIJACK_ENV_KEYS)


def _build_managed_child_env(
    env: Optional[Mapping[str, str]],
    token_hex: str,
) -> Optional[dict[str, str]]:
    validated = _validate_process_env_map(env, "ManagedProcessTree env") if env is not None else None
    has_hijack = validated is None and any(k.upper() in _MANAGED_HIJACK_ENV_UPPER for k in os.environ)
    need_flags = sys.dont_write_bytecode or sys.flags.optimize > 0 or bool(token_hex) or has_hijack
    if validated is not None:
        env_map: Optional[dict[str, str]] = {
            k: v for k, v in validated.items() if k.upper() not in _MANAGED_HIJACK_ENV_UPPER
        }
    elif need_flags:
        env_map = {k: v for k, v in os.environ.items() if k.upper() not in _MANAGED_HIJACK_ENV_UPPER}
    else:
        env_map = None
    if env_map is None:
        return None
    if token_hex:
        prev_chain = env_map.get(TREE_ID_ENV_KEY, "").strip(",")
        env_map[TREE_ID_ENV_KEY] = f"{prev_chain},{token_hex}" if prev_chain else token_hex
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

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _ = (exc_type, exc, tb)
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
        ps_snap = None if _has_posix_proc_stat() else _snapshot_ps_tree_maps()
        ps_map = ps_snap.by_ppid if ps_snap is not None else None
        seeds = [self._proc.pid] if self._proc.returncode is None else []
        seeds.extend(self._known_descendants.keys())
        seen: set[int] = set()
        new_pids = [
            cpid
            for spid in seeds
            for cpid in _collect_posix_descendants(
                spid, seen, ps_map, tree_token_bytes=self._tree_token_bytes
            )
            if cpid not in self._known_descendants
        ]
        if self._owns_process_group:
            for gpid in _collect_orphan_pgid_members_posix(self._proc.pid, seen, ps_snap, tree_token_bytes=self._tree_token_bytes):
                if gpid not in self._known_descendants:
                    new_pids.append(gpid)
        if self._tree_token_bytes:
            for dpid in _collect_posix_env_token_pids(self._tree_token_bytes, self._proc.pid, seen, ps_map):
                if dpid not in self._known_descendants:
                    new_pids.append(dpid)
        for cpid in new_pids:
            st = _read_posix_proc_starttime(cpid)
            if st is not None or not _has_posix_proc_starttime():
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
                _WIN_TERM_JOB(wintypes.HANDLE(self._job_handle), 1)
                _WIN_CLOSE_HANDLE(wintypes.HANDLE(self._job_handle))
                self._job_handle = None
            return
        try:
            os.killpg(self._proc.pid, signal.SIGKILL)
        except OSError:
            pass
