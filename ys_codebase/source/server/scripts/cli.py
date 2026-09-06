"""
Server Module CLI Entry Point.
Provides management commands: start, stop, status, reload.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from core.guard import guard_dispatch
from core.platform import is_process_alive, kill_process_tree, spawn_detached
from server.master import MasterSupervisor, ServerDaemonState


def _get_yscb_root() -> str:
    # yscb_root is current workspace or parent of .cache
    return os.environ.get("YSCB_HOST_DIR", os.getcwd())


def _read_daemon_state(yscb_root: str) -> Optional[ServerDaemonState]:
    state_file = os.path.join(yscb_root, ".cache", "server", "daemon.json")
    if not os.path.exists(state_file):
        return None
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return ServerDaemonState(**data)
    except Exception:
        return None


def _http_request(state: ServerDaemonState, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    url = f"http://127.0.0.1:{state.port}{path}"
    headers = {
        "Authorization": f"Bearer {state.token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except Exception:
        return None


def _handle_start(args: List[str], yscb_root: str) -> int:
    parser = argparse.ArgumentParser(prog="server start", description="Start persistent server daemon")
    parser.add_argument("--console", action="store_true", help="Run server in foreground console mode")
    parser.add_argument("--daemon", action="store_true", default=True, help="Run server detached in background (default)")
    parser.add_argument("--ttl", type=float, default=900.0, help="Idle timeout in seconds (0 to disable)")
    parsed = parser.parse_args(args)

    state = _read_daemon_state(yscb_root)
    if state and is_process_alive(state.pid):
        print(f"[Server] Daemon is already running (PID: {state.pid}, Port: {state.port}).")
        return 0

    if parsed.console:
        print(f"[*] Starting Server in foreground console mode (Root: {yscb_root})...")
        sup = MasterSupervisor(yscb_root=yscb_root, idle_timeout_sec=parsed.ttl)
        sup.start(foreground=True)
        return 0
    else:
        # Background detached mode
        cmd = [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, r'{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}'); "
            f"from server.master import MasterSupervisor; MasterSupervisor(r'{yscb_root}', idle_timeout_sec={parsed.ttl}).start(foreground=True)",
        ]
        pid = spawn_detached(cmd, cwd=yscb_root)
        print(f"[Server] Starting background daemon (PID: {pid})...")

        # Wait for state file creation
        for _ in range(30):
            time.sleep(0.1)
            state = _read_daemon_state(yscb_root)
            if state and is_process_alive(state.pid):
                print(f"[Server] Daemon successfully started (PID: {state.pid}, Port: {state.port}).")
                return 0

        print("[Server] Daemon started but readiness probe timed out.")
        return 0


def _handle_stop(args: List[str], yscb_root: str) -> int:
    parser = argparse.ArgumentParser(prog="server stop", description="Stop persistent server daemon")
    parser.add_argument("--force", action="store_true", help="Force kill daemon and worker process tree")
    parsed = parser.parse_args(args)

    state = _read_daemon_state(yscb_root)
    if not state or not is_process_alive(state.pid):
        print("[Server] Daemon is not running.")
        # Clean stale file if any
        state_file = os.path.join(yscb_root, ".cache", "server", "daemon.json")
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
            except OSError:
                pass
        return 0

    if not parsed.force:
        print(f"[Server] Sending graceful shutdown request to daemon (PID: {state.pid})...")
        resp = _http_request(state, "/api/shutdown", method="POST", timeout=2.0)
        if resp:
            for _ in range(20):
                time.sleep(0.1)
                if not is_process_alive(state.pid):
                    print("[Server] Daemon stopped gracefully.")
                    return 0

    print(f"[Server] Terminating process tree for PID: {state.pid}...")
    kill_process_tree(state.pid, timeout_sec=2.0)
    print("[Server] Daemon stopped.")
    return 0


def _handle_status(args: List[str], yscb_root: str) -> int:
    state = _read_daemon_state(yscb_root)
    if not state or not is_process_alive(state.pid):
        print("[Server] Status: Stopped (No active daemon found).")
        return 0

    info = _http_request(state, "/api/status", method="GET", timeout=1.5)
    if not info:
        print(f"[Server] Daemon PID {state.pid} alive but HTTP not responding (Port: {state.port}).")
        return 1

    ttl_str = f"{info['idle_seconds_left']:.1f}s" if state.idle_timeout_sec > 0 else "Disabled (Persistent)"
    print("======================================================================")
    print("YS-Codebase Server Daemon Status")
    print("======================================================================")
    print(f"[*] State         : {info.get('state', 'ready').upper()}")
    print(f"[*] Master PID    : {info.get('pid')}")
    print(f"[*] Worker PID    : {info.get('worker_pid')} ({'Alive' if is_process_alive(info.get('worker_pid', 0)) else 'Restarting'})")
    print(f"[*] Port          : {info.get('port')}")
    print(f"[*] Workspace Root: {info.get('root')}")
    print(f"[*] Tasks Handled : {info.get('tasks_executed')}")
    print(f"[*] Idle TTL Left : {ttl_str}")

    services = info.get("services", [])
    if services:
        print("----------------------------------------------------------------------")
        print("[*] Background Services:")
        for svc in services:
            print(f"    • {svc['name']}: {'Running' if svc['alive'] else 'Stopped'}")
    print("======================================================================")
    return 0


def _handle_reload(args: List[str], yscb_root: str) -> int:
    state = _read_daemon_state(yscb_root)
    if not state or not is_process_alive(state.pid):
        print("[Server] Daemon is not running. Nothing to reload.")
        return 1

    print(f"[Server] Requesting warm worker hot reload (PID: {state.pid})...")
    resp = _http_request(state, "/api/reload", method="POST", timeout=3.0)
    if resp and "new_worker_pid" in resp:
        print(f"[Server] Worker reloaded successfully (New Worker PID: {resp['new_worker_pid']}).")
        return 0
    else:
        print("[Server] Worker reload request failed or timed out.")
        return 1


def process(args: List[str]) -> int:
    """
    Entry point for server module.
    """
    guard_dispatch("server")

    if not args or args[0] in ("-h", "--help", "help"):
        print("Usage: python yscb.py server <command> [options]")
        print("Commands:")
        print("  start     Start the persistent server daemon (--daemon, --console, --ttl)")
        print("  stop      Stop the running persistent server daemon (--force)")
        print("  status    Inspect persistent server daemon and worker status")
        print("  reload    Hot reload warm worker subprocess")
        return 0

    subcommand = args[0]
    sub_args = args[1:]
    yscb_root = _get_yscb_root()

    if subcommand == "start":
        return _handle_start(sub_args, yscb_root)
    elif subcommand == "stop":
        return _handle_stop(sub_args, yscb_root)
    elif subcommand == "status":
        return _handle_status(sub_args, yscb_root)
    elif subcommand == "reload":
        return _handle_reload(sub_args, yscb_root)
    else:
        print(f"Error: Unknown server command '{subcommand}'. Run 'server --help' for usage.")
        return 1
