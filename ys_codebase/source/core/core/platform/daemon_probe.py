"""
Core Platform - Empirical Background Daemon Reaping Probe.

Detects execution environments (e.g. sandboxed agent terminals) that silently
reap detached background daemons. Instead of guessing from static environment
traits, every auto-spawn is recorded; if a recorded daemon later disappears
without having written a clean-exit marker, the environment accumulates a
``reaped_count``. Reaching ``REAP_THRESHOLD`` marks the environment as unable to
host a persistent daemon. Any clean exit resets the counter.

Records are keyed by ``env_fingerprint()`` so that hosts sharing the same
``.cache`` directory (e.g. Windows host + Linux guest) never pollute each other.

All I/O failures are deliberately degraded to "no record" (EC-03): the probe
file is observational data, never a business-critical artifact.

Standard library only; must not import ``server`` (NFR-01).
"""

import json
import os
import socket
import sys
import time
from typing import Any, Dict, Optional

from core.platform.lock import InterProcessLock

PROBE_REL_PATH: str = os.path.join(".cache", "server", "spawn_probe.json")
DAEMON_LOCK_REL_PATH: str = os.path.join(".cache", "server", "daemon.lock")
DAEMON_STATE_REL_PATH: str = os.path.join(".cache", "server", "daemon.json")
REAP_THRESHOLD: int = 2


def env_fingerprint() -> str:
    """Returns a stable identifier of the current host environment (hostname + platform)."""
    return f"{socket.gethostname()}|{sys.platform}"


def _probe_path(yscb_root: str) -> str:
    return os.path.join(yscb_root, PROBE_REL_PATH)


def _load_all(yscb_root: str) -> Dict[str, Any]:
    """Loads all fingerprint records; unreadable or malformed files degrade to empty (EC-03)."""
    path = _probe_path(yscb_root)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_all(yscb_root: str, data: Dict[str, Any]) -> None:
    """Atomically persists all records; write failures are degraded silently (observability only)."""
    path = _probe_path(yscb_root)
    tmp_path = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _get_entry(data: Dict[str, Any]) -> Dict[str, Any]:
    entry = data.get(env_fingerprint())
    if not isinstance(entry, dict):
        entry = {}
    try:
        reaped = int(entry.get("reaped_count", 0))
    except (TypeError, ValueError):
        reaped = 0
    try:
        pid = int(entry.get("pid", 0) or 0)
    except (TypeError, ValueError):
        pid = 0
    return {
        "pid": pid,
        "spawned_at": entry.get("spawned_at", 0.0),
        "clean_exit": bool(entry.get("clean_exit", False)),
        "reaped_count": max(reaped, 0),
    }


def record_spawn(yscb_root: str, pid: int) -> None:
    """
    Records an auto-spawned daemon PID for the current environment fingerprint.

    Args:
        yscb_root: Absolute yscb root directory.
        pid: PID of the freshly spawned detached daemon process.
    """
    data = _load_all(yscb_root)
    entry = _get_entry(data)
    entry.update({"pid": int(pid), "spawned_at": time.time(), "clean_exit": False})
    data[env_fingerprint()] = entry
    _save_all(yscb_root, data)


def bind_master_pid(yscb_root: str, pid: int) -> None:
    """
    Rebinds the pending spawn record to the actual master PID.

    ``record_spawn`` stores the PID of the short-lived ``server start --daemon`` launcher; the master
    calls this right after acquiring the single-instance lock. No-op when the current fingerprint has
    no record or its record is already marked clean_exit (i.e. the master was not auto-spawned).

    Args:
        yscb_root: Absolute yscb root directory.
        pid: PID of the running master supervisor.
    """
    data = _load_all(yscb_root)
    if env_fingerprint() not in data:
        return
    entry = _get_entry(data)
    if entry["clean_exit"]:
        return
    entry["pid"] = int(pid)
    data[env_fingerprint()] = entry
    _save_all(yscb_root, data)


def mark_clean_exit(yscb_root: str) -> None:
    """
    Marks that the daemon of the current environment exited gracefully and resets
    the reaping counter to zero.

    Args:
        yscb_root: Absolute yscb root directory.
    """
    data = _load_all(yscb_root)
    entry = _get_entry(data)
    entry.update({"pid": 0, "clean_exit": True, "reaped_count": 0})
    data[env_fingerprint()] = entry
    _save_all(yscb_root, data)


def is_daemon_lock_held(yscb_root: str) -> bool:
    """Returns True when ``daemon.lock`` is held by a live daemon (EC-11: lock ownership is the truth)."""
    lock_file = os.path.join(yscb_root, DAEMON_LOCK_REL_PATH)
    if not os.path.isfile(lock_file):
        return False
    probe_lock = InterProcessLock(lock_file)
    try:
        if not probe_lock.acquire(blocking=False):
            return True
    except OSError:
        return False
    probe_lock.release()
    return False


def _is_daemon_active(yscb_root: str) -> bool:
    """
    Cheapest-first daemon liveness: daemon.json pid liveness, then (only if inconclusive)
    a non-blocking daemon.lock probe, minimizing contention with a concurrently starting master.
    """
    from core.platform.process import is_process_alive

    state_file = os.path.join(yscb_root, DAEMON_STATE_REL_PATH)
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        pid = int(state.get("pid", 0) or 0) if isinstance(state, dict) else 0
    except (OSError, ValueError, TypeError):
        pid = 0
    if pid > 0 and is_process_alive(pid):
        return True
    return is_daemon_lock_held(yscb_root)


def is_reaping_env(yscb_root: str, daemon_active: Optional[bool] = None) -> bool:
    """
    Evaluates whether the current environment empirically reaps background daemons.

    If the last recorded spawn PID is dead, never wrote a clean exit, and no daemon
    is currently active, the record is consumed and ``reaped_count`` incremented.

    Args:
        yscb_root: Absolute yscb root directory.
        daemon_active: Whether a daemon is currently alive. When None, liveness is probed lazily
            (daemon.json pid first, then daemon.lock) only if the record otherwise qualifies.

    Returns:
        bool: True if ``reaped_count >= REAP_THRESHOLD`` for this fingerprint.
    """
    from core.platform.process import is_process_alive

    data = _load_all(yscb_root)
    if env_fingerprint() not in data:
        return False
    entry = _get_entry(data)
    pid = entry["pid"]
    if pid > 0 and not entry["clean_exit"] and not is_process_alive(pid):
        active = daemon_active if daemon_active is not None else _is_daemon_active(yscb_root)
        if not active:
            entry["reaped_count"] += 1
            entry["pid"] = 0
            data[env_fingerprint()] = entry
            _save_all(yscb_root, data)
    return entry["reaped_count"] >= REAP_THRESHOLD
