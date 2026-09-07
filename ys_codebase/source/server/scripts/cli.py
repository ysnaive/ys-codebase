"""
Server Module CLI Entry Point - Precise Command Handlers Contract.
Provides management commands: start, stop, status, reload.
No legacy process(args) fallback.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from core.commands.bags import CmdBags, CmdOption
from core.guard import guard_dispatch
from core.platform import is_process_alive, kill_process_tree, spawn_detached
from server.config import ServerConfig
from server.master import MasterSupervisor, ServerDaemonState


def _resolve_enable_console(
    console_arg: Optional[bool],
    daemon_arg: Optional[bool],
    config_val: bool = False,
) -> bool:
    """
    啟動模式優先級決策：
    1. console_arg 為 True -> True (CLI --console 強制覆蓋除錯)
    2. daemon_arg 為 True -> False (CLI --daemon 強制覆蓋背景)
    3. 皆未指定 (None) -> config_val
    """
    if console_arg is True:
        return True
    if daemon_arg is True:
        return False
    return bool(config_val)


def _get_yscb_root() -> str:
    try:
        from core import uri
        return uri.resolve("yscb://")
    except Exception:
        cand = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if os.path.isdir(os.path.join(cand, ".modules")) or os.path.isdir(os.path.join(cand, "source")):
            return cand
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


def _http_request(
    state: ServerDaemonState,
    path: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 2.0,
) -> Optional[Dict[str, Any]]:
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


def start(cmd_bags: CmdBags) -> int:
    """Start persistent server daemon."""
    guard_dispatch("server")
    yscb_root = _get_yscb_root()

    console_arg = True if cmd_bags.has_option("console") else None
    daemon_arg = True if cmd_bags.has_option("daemon") else None
    raw_ttl = cmd_bags.get_option_value("ttl")
    ttl = float(raw_ttl) if raw_ttl is not None else None

    state = _read_daemon_state(yscb_root)
    if state and is_process_alive(state.pid):
        print(f"[Server] Daemon is already running (PID: {state.pid}, Port: {state.port}).")
        return 0

    cfg = ServerConfig.load(workspace_root=yscb_root)
    if not cfg.enable:
        print("[Server] Server is disabled in configuration ('enable': false). Aborting start.")
        return 1

    enable_console = _resolve_enable_console(console_arg, daemon_arg, cfg.enable_console)
    effective_ttl = ttl if ttl is not None else cfg.idle_timeout_sec

    if enable_console:
        print(f"[*] Starting Server in foreground console mode (Root: {yscb_root}, TTL: {effective_ttl}s)...")
        sup = MasterSupervisor(yscb_root=yscb_root, idle_timeout_sec=effective_ttl)
        sup.start(foreground=True)
        return 0
    else:
        # Background detached mode
        core_dir = os.path.join(yscb_root, ".modules", "core")
        if not os.path.isdir(core_dir):
            core_dir = os.path.join(yscb_root, "source", "core")
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [
            sys.executable,
            "-c",
            f"import sys; "
            f"sys.path.insert(0, r'{core_dir}'); "
            f"sys.path.insert(0, r'{server_dir}'); "
            f"from server.master import MasterSupervisor; MasterSupervisor(r'{yscb_root}', idle_timeout_sec={effective_ttl}).start(foreground=True)",
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


def stop(cmd_bags: CmdBags) -> int:
    """Stop persistent server daemon."""
    guard_dispatch("server")
    yscb_root = _get_yscb_root()
    force_flag = cmd_bags.has_option("force")

    state = _read_daemon_state(yscb_root)
    if not state or not is_process_alive(state.pid):
        print("[Server] Daemon is not running.")
        state_file = os.path.join(yscb_root, ".cache", "server", "daemon.json")
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
            except OSError:
                pass
        return 0

    if not force_flag:
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


def status(cmd_bags: CmdBags) -> int:
    """Inspect persistent server daemon and worker status."""
    guard_dispatch("server")
    yscb_root = _get_yscb_root()
    state = _read_daemon_state(yscb_root)
    if not state or not is_process_alive(state.pid):
        cfg = ServerConfig.load(workspace_root=yscb_root)
        if not cfg.enable:
            print("[Server] Status: Disabled ('enable': false in config).")
        else:
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
        print(f"[*] Background Services ({len(services)} registered):")
        for svc in services:
            prov = f" (module: {svc.get('provider')})" if svc.get("provider") else ""
            status_txt = "RUNNING" if svc.get("alive") else "STOPPED"
            print(f"    ├── [{svc['name']}]{prov} : {status_txt}")
    print("======================================================================")
    return 0


def reload(cmd_bags: CmdBags) -> int:
    """Hot reload warm worker subprocess."""
    guard_dispatch("server")
    yscb_root = _get_yscb_root()
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


def _handle_start(args: Any, yscb_abs: Optional[str] = None, server_cfg: Optional[ServerConfig] = None) -> int:
    """Helper for starting server, supporting both raw args list and CmdBags."""
    if isinstance(args, (list, tuple)):
        if "--console" in args and "--daemon" in args:
            raise SystemExit(2)
        root = yscb_abs or _get_yscb_root()
        cfg = server_cfg or ServerConfig.load(workspace_root=root)
        if not cfg.enable:
            print("[Server] Server is disabled in configuration ('enable': false). Aborting start.")
            return 1
        options = {}
        if "--console" in args:
            options["console"] = CmdOption(name="console", params=True)
        if "--daemon" in args:
            options["daemon"] = CmdOption(name="daemon", params=True)
        for a in args:
            if a.startswith("--ttl="):
                val = a.split("=", 1)[1]
                options["ttl"] = CmdOption(name="ttl", params=val)
        bags = CmdBags(raw_cmd="start " + " ".join(args), command="start", args=[], options=options)
        return start(bags)
    elif isinstance(args, CmdBags):
        return start(args)
    return 1
