"""
Server Module - Master Supervisor & Localhost HTTP Server.

Coordinates daemon state, dynamic port binding (127.0.0.1:0), security bearer token,
single warm worker subprocess lifecycle, idle TTL auto-shutdown, and serialized dispatch queue.
"""

from dataclasses import asdict, dataclass
import http.server
import json
import os
import platform
import secrets
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse

from core import vfs
from core.platform import (
    InterProcessLock,
    daemon_probe,
    ensure_private_venv,
    is_process_alive,
    set_process_title,
    spawn_detached,
    terminate_popen_tree,
)
from server.logger import ServerLogger
from server.watcher import ModulesWatcher


_PREEMPTED_ERROR = "Worker terminated by restart/stop"


class WorkerSpawnError(RuntimeError):
    """Raised when a warm worker fails the `worker_alive` handshake (crashed or hung at startup)."""


@dataclass
class ServerDaemonState:
    pid: int
    worker_pid: int
    port: int
    token: str
    root: str
    start_time: float
    idle_timeout_sec: float
    tasks_executed: int = 0


def format_uptime(uptime_sec: float) -> str:
    """Formats uptime seconds into human-readable string."""
    uptime_val = float(uptime_sec)
    mins = int(uptime_val // 60)
    secs = uptime_val % 60
    if mins > 0:
        return f"{mins}m {secs:.1f}s ({uptime_val:.1f}s)"
    return f"{uptime_val:.1f}s"


def format_watcher_status(watcher: Optional[Dict[str, Any]], include_slash: bool = True) -> str:
    """Formats ModulesWatcher status dictionary into display label."""
    if not watcher or not watcher.get("enabled"):
        return "DISABLED"
    if watcher.get("active"):
        dir_name = os.path.basename(watcher.get("monitored_dir") or ".modules")
        suffix = "/" if include_slash else ""
        return f"ACTIVE (Monitoring {dir_name}{suffix})"
    return "STOPPED"


def read_daemon_state(yscb_root: str) -> Optional[ServerDaemonState]:
    """Reads and deserializes daemon.json from yscb_root/.cache/server/daemon.json."""
    state_file = os.path.join(yscb_root, ".cache", "server", "daemon.json")
    if not os.path.exists(state_file):
        return None
    try:
        data = vfs.read_json(state_file)
        if isinstance(data, dict):
            return ServerDaemonState(**data)
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None


def build_fallback_status_payload(state: ServerDaemonState) -> Dict[str, Any]:
    """Builds fallback status dictionary from ServerDaemonState when HTTP probe is unavailable."""
    return {
        "pid": state.pid,
        "worker_pid": state.worker_pid,
        "port": state.port,
        "root": state.root,
        "idle_timeout_sec": state.idle_timeout_sec,
        "log_file": os.path.join(state.root, ".cache", "server", "log"),
    }


def spawn_detached_master(
    yscb_root: str,
    idle_timeout_sec: float,
    enable_watcher: bool = True,
) -> int:
    """Assembles cross-platform Python command and spawns a detached MasterSupervisor daemon."""
    core_dir = os.path.abspath(os.path.join(yscb_root, ".modules", "core"))
    server_dir = os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root_abs = os.path.abspath(yscb_root)

    code = (
        "import sys; "
        "sys.path.insert(0, sys.argv[1]); "
        "sys.path.insert(0, sys.argv[2]); "
        "from server.master import MasterSupervisor; "
        "MasterSupervisor(sys.argv[3], idle_timeout_sec=float(sys.argv[4]), enable_watcher=(sys.argv[5] == '1')).start(foreground=True)"
    )
    cmd = [
        sys.executable,
        "-c",
        code,
        core_dir,
        server_dir,
        root_abs,
        str(float(idle_timeout_sec)),
        "1" if enable_watcher else "0",
    ]
    return spawn_detached(cmd, cwd=yscb_root)


def format_startup_banner(info: Dict[str, Any]) -> str:
    """Formats ASCII startup banner with key runtime parameters."""
    lines = [
        "======================================================================",
        "  __   __ ____   ____     ____                               ",
        "  \\ \\ / // ___| / ___|   / ___|  ___ _ ____   _____ _ __     ",
        "   \\ V / \\___ \\| |   ____\\___ \\ / _ \\ '__\\ \\ / / _ \\ '__|    ",
        "    | |   ___) | |__|_____|__) |  __/ |   \\ V /  __/ |       ",
        "    |_|  |____/ \\____|   |____/ \\___|_|    \\_/ \\___|_|       ",
        "======================================================================",
        "[Server] Daemon successfully started!",
        f"  ├── Master PID      : {info.get('pid')}",
        f"  ├── Worker PID      : {info.get('worker_pid')} (State: {str(info.get('state', 'ready')).upper()})",
        f"  ├── Listening Port  : {info.get('port')} (http://127.0.0.1:{info.get('port')})",
        f"  ├── Workspace Root  : {info.get('root')}",
    ]
    idle = info.get("idle_seconds_left")
    ttl_cfg = info.get("idle_timeout_sec")
    if ttl_cfg is not None and float(ttl_cfg) > 0:
        ttl_str = f"{float(ttl_cfg):.1f}s (Auto-shutdown when idle)"
    elif idle is not None and float(idle) > 0:
        ttl_str = f"{float(idle):.1f}s (Auto-shutdown when idle)"
    else:
        ttl_str = "Disabled (Persistent)"
    lines.append(f"  ├── Idle Timeout    : {ttl_str}")

    w_str = format_watcher_status(info.get("watcher", {}))
    lines.append(f"  ├── Modules Watcher : {w_str}")

    services = info.get("services", [])
    if services:
        svc_names = ", ".join(s.get("name", "svc") for s in services)
        lines.append(f"  ├── Background Svcs : {len(services)} registered ({svc_names})")
    else:
        lines.append("  ├── Background Svcs : 0 registered")

    log_path = info.get("log_file") or ""
    lines.append(f"  └── Real-time Log   : {log_path}")
    lines.append("======================================================================")
    return "\n".join(lines)


def format_shutdown_summary(summary: Dict[str, Any]) -> str:
    """Formats structured shutdown summary card."""
    uptime_fmt = format_uptime(float(summary.get("uptime_seconds", 0.0)))
    tasks = summary.get("tasks_executed", 0)
    svcs = summary.get("services_stopped", 0)
    reason = summary.get("reason", "Graceful CLI shutdown request")
    arch = summary.get("archive_log", "")

    lines = [
        "======================================================================",
        "YS-Codebase Server Shutdown Summary",
        "======================================================================",
        "[Server] Daemon stopped gracefully.",
        f"  ├── Total Uptime    : {uptime_fmt}",
        f"  ├── Tasks Handled   : {tasks} tasks executed",
        f"  ├── Services Stopped: {svcs} background services terminated",
        f"  ├── Shutdown Reason : {reason}",
        f"  └── Archived Log    : {arch}",
        "======================================================================",
    ]
    return "\n".join(lines)


class MasterSupervisor:
    """
    Central supervisor process managing the HTTP dispatcher, warm worker child process,
    idle TTL self-destruct, and .modules/ hot reload.
    """

    def __init__(
        self,
        yscb_root: str,
        idle_timeout_sec: float = 1800.0,
        enable_watcher: bool = True,
    ) -> None:
        self.yscb_root = os.path.abspath(yscb_root)
        self.idle_timeout_sec = float(idle_timeout_sec)
        ensure_private_venv(self.yscb_root)
        self.enable_watcher = enable_watcher

        self.token = secrets.token_hex(16)
        self.state_file = os.path.join(self.yscb_root, ".cache", "server", "daemon.json")
        self.lock_file = os.path.join(self.yscb_root, ".cache", "server", "daemon.lock")

        self.logger = ServerLogger(self.yscb_root)
        self.watcher: Optional[ModulesWatcher] = None

        self._worker_proc: Optional[subprocess.Popen] = None
        self._worker_lock = threading.Lock()
        self._dispatch_lock = threading.Lock()
        self._worker_services: List[Dict[str, Any]] = []
        # FR-09: two-stage handshake state (per spawned worker)
        self._worker_ready_event = threading.Event()
        self._warming_since: Optional[float] = None
        self._worker_alive_timeout_sec = self._load_worker_alive_timeout()
        # FR-01: PIDs of workers killed while a dispatch was in flight
        self._preempted_pids: Set[int] = set()
        # FR-02: currently executing dispatch task snapshot
        self._current_task: Optional[Dict[str, Any]] = None

        self._start_time = time.time()
        self._last_active_time = self._start_time
        self._tasks_executed = 0
        self._is_running = False
        self._is_stopped = False
        self._restarting = False
        self._stop_lock = threading.Lock()
        self._httpd: Optional[http.server.HTTPServer] = None
        self._lock: Optional[InterProcessLock] = None
        self.port = 0

    @staticmethod
    def _load_worker_alive_timeout() -> float:
        from server.config import DEFAULT_WORKER_ALIVE_TIMEOUT_SEC, ServerConfig
        try:
            return float(ServerConfig.load().worker_alive_timeout_sec)
        except (TypeError, ValueError):
            return DEFAULT_WORKER_ALIVE_TIMEOUT_SEC

    def _worker_state(self) -> str:
        """Returns worker lifecycle state: 'ready', 'warming' or 'restarting' (no live worker)."""
        proc = self._worker_proc
        if proc is None or proc.poll() is not None:
            return "restarting"
        return "ready" if self._worker_ready_event.is_set() else "warming"

    def get_status_dict(self) -> Dict[str, Any]:
        """
        Returns structured dictionary of server runtime status.

        Never acquires `_dispatch_lock`, so it stays responsive while a task is running.
        Includes `current_task` ({module, args, started_at, elapsed_sec} or None) and,
        while the worker is pre-warming, `warming_elapsed_sec`.
        """
        worker_pid = self._worker_proc.pid if self._worker_proc else 0
        now = time.time()
        uptime = now - self._start_time
        idle_left = max(0.0, self.idle_timeout_sec - (now - self._last_active_time))
        watcher_status = {
            "enabled": self.enable_watcher,
            "active": (self.watcher is not None and self.watcher.is_running),
            "monitored_dir": self.watcher.modules_dir if self.watcher else None,
        }
        task = self._current_task
        current_task: Optional[Dict[str, Any]] = None
        if task is not None:
            current_task = dict(task)
            current_task["elapsed_sec"] = max(0.0, now - float(task["started_at"]))
        state = self._worker_state()
        status = {
            "status": "running",
            "state": state,
            "pid": os.getpid(),
            "worker_pid": worker_pid,
            "port": self.port,
            "root": self.yscb_root,
            "start_time": self._start_time,
            "uptime_seconds": uptime,
            "tasks_executed": self._tasks_executed,
            "idle_seconds_left": idle_left,
            "idle_timeout_sec": self.idle_timeout_sec,
            "log_file": self.logger.log_file,
            "services": self._worker_services or [],
            "watcher": watcher_status,
            "current_task": current_task,
        }
        warming_since = self._warming_since
        if state == "warming" and warming_since is not None:
            status["warming_elapsed_sec"] = max(0.0, now - warming_since)
        return status

    def _initialize_daemon_environment(self) -> None:
        """Sets process title, initializes crash-recovered logger, and resets runtime flags."""
        set_process_title("yscb server")
        start_ts = self.logger.recover_and_open()
        self.logger.info(
            f"Starting MasterSupervisor (PID: {os.getpid()}, Root: {self.yscb_root}, "
            f"Idle TTL: {self.idle_timeout_sec}s, StartTime: {start_ts})"
        )
        self._is_running = True
        self._is_stopped = False
        self._restarting = False
        self._last_active_time = time.time()

    def _start_http_and_watcher_services(self) -> None:
        """Binds localhost HTTP server, spawns warm worker, and activateswatcher & idle TTL threads."""
        self._httpd = _create_http_server(self)
        self.port = self._httpd.server_address[1]
        self.logger.info(f"HTTP Server listening on 127.0.0.1:{self.port}")

        self._write_state()

        with self._worker_lock:
            try:
                self._spawn_worker_locked()
                self.logger.info(f"Initial Warm Worker spawned (PID: {self._worker_proc.pid if self._worker_proc else 0})")
            except WorkerSpawnError as err:
                # EC-08: keep the daemon up; the next dispatch re-attempts spawning
                self.logger.error(f"Initial Warm Worker spawn failed: {err}")
        self._write_state()

        if self.enable_watcher:
            modules_dir = os.path.join(self.yscb_root, ".modules")
            self.watcher = ModulesWatcher(modules_dir, on_change_callback=self.on_modules_changed, debounce_sec=0.5)
            self.watcher.start()
            self.logger.info(f"ModulesWatcher active on {modules_dir}")

        if self.idle_timeout_sec > 0:
            ttl_thread = threading.Thread(target=self._idle_ttl_loop, daemon=True, name="idle-ttl")
            ttl_thread.start()

    def _run_supervisor_main_loop(self, foreground: bool) -> None:
        """Runs HTTP server either in blocking foreground mode or background daemon thread."""
        if foreground:
            self.logger.echo_console = True
            banner = format_startup_banner(self.get_status_dict())
            print(banner, flush=True)
            try:
                if self._httpd:
                    self._httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()
        else:
            self._http_thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="http-server")
            self._http_thread.start()

    def start(self, foreground: bool = False) -> int:
        """Starts the master supervisor with rigid single-instance lock protection."""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

        self._lock = InterProcessLock(self.lock_file)
        if not self._lock.acquire(blocking=False):
            state = read_daemon_state(self.yscb_root)
            if state and is_process_alive(state.pid):
                return state.pid
            # No live daemon: the lock may be briefly held by a CLI liveness probe; retry shortly
            if not self._lock.acquire(blocking=True, timeout_sec=0.5):
                state = read_daemon_state(self.yscb_root)
                return state.pid if state and is_process_alive(state.pid) else 0

        # OBS-01: rebind auto-spawn probe record from the launcher PID to this master PID
        daemon_probe.bind_master_pid(self.yscb_root, os.getpid())
        try:
            self._initialize_daemon_environment()
            self._start_http_and_watcher_services()
            self._run_supervisor_main_loop(foreground)
            return os.getpid()
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        """Stops the master supervisor and all child workers."""
        with self._stop_lock:
            if self._is_stopped:
                return
            self._is_stopped = True
            self.logger.info(f"Stopping MasterSupervisor (PID: {os.getpid()})...")
            self._is_running = False

            if self.watcher:
                self.watcher.stop()
                self.watcher = None

            # FR-01: preempt any in-flight dispatch by killing the worker (no _dispatch_lock)
            with self._worker_lock:
                self._kill_worker_locked(timeout_sec=2.0)

            if self._httpd:
                try:
                    self._httpd.shutdown()
                    self._httpd.server_close()
                except Exception:
                    pass
                self._httpd = None

            if self._lock:
                try:
                    self._lock.release()
                except Exception:
                    pass
                self._lock = None

            self._cleanup_state()
            # FR-03: graceful shutdown marker resets empirical reaping detection
            daemon_probe.mark_clean_exit(self.yscb_root)
            self.logger.archive_and_close()

    def _kill_worker_locked(self, timeout_sec: float = 2.0) -> None:
        """
        Terminates the child worker and closes all pipe handles (caller holds `_worker_lock`).

        Idle worker: two-stage handshake (`{"action": "exit"}` then process-tree termination).
        Busy worker (dispatch in flight): skips the handshake and terminates the process tree
        immediately so the blocked dispatch `readline()` hits EOF and releases `_dispatch_lock`.
        """
        if not self._worker_proc:
            return
        proc = self._worker_proc

        exited_gracefully = False
        if self._current_task is not None:
            self._preempted_pids.add(proc.pid)
        elif proc.poll() is None and proc.stdin:
            try:
                proc.stdin.write(b'{"action": "exit"}\n')
                proc.stdin.flush()
                proc.wait(timeout=min(timeout_sec, 1.5))
                exited_gracefully = True
            except (OSError, ValueError, subprocess.TimeoutExpired) as err:
                self.logger.warning(f"Worker (PID: {proc.pid}) graceful exit handshake failed: {err}")

        if not exited_gracefully and proc.poll() is None:
            if not terminate_popen_tree(proc, timeout_sec=timeout_sec):
                self.logger.error(f"Failed to terminate worker process tree (PID: {proc.pid})")

        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe:
                try:
                    pipe.close()
                except (OSError, ValueError):
                    pass
        self._worker_proc = None
        self._warming_since = None

    def restart_worker(self) -> int:
        """
        Preemptively terminates the current worker and spawns a fresh one while syncing ServerConfig.

        FR-01: the worker is killed under `_worker_lock` only (never waiting on `_dispatch_lock`),
        which unblocks any in-flight dispatch; `_dispatch_lock` is then acquired to spawn.

        Returns:
            int: PID of the fresh worker.

        Raises:
            WorkerSpawnError: if the fresh worker fails the alive handshake.
        """
        # Load config before any destructive action so a config error never leaves the daemon worker-less
        from server.config import ServerConfig
        cfg = ServerConfig.load()

        with self._worker_lock:
            old_pid = self._worker_proc.pid if self._worker_proc else 0
            self.logger.info(f"Restarting Warm Worker (terminating old PID: {old_pid})...")
            self._kill_worker_locked(timeout_sec=1.5)

        self.idle_timeout_sec = float(cfg.idle_timeout_sec)
        self._worker_alive_timeout_sec = float(cfg.worker_alive_timeout_sec)

        with self._dispatch_lock:
            with self._worker_lock:
                if self._worker_proc is not None and self._worker_proc.poll() is None:
                    # A queued dispatch already spawned a fresh worker after the kill
                    new_pid = self._worker_proc.pid
                else:
                    try:
                        new_pid = self._spawn_worker_locked()
                    except WorkerSpawnError as err:
                        self.logger.error(f"Warm Worker restart failed: {err}")
                        raise
                self._last_active_time = time.time()
                self._write_state()
                self.logger.info(f"Fresh Warm Worker spawned (PID: {new_pid})")
                return new_pid

    def on_modules_changed(self, affected_modules: Optional[Set[str]] = None) -> None:
        """
        Dual-channel reload dispatcher:
        - If 'server' or 'core' changed: triggers restart_server()
        - Otherwise: triggers restart_worker()
        """
        self.logger.info(f"ModulesWatcher detected change in modules: {affected_modules}")
        if affected_modules and ("server" in affected_modules or "core" in affected_modules):
            self.logger.info(f"[Server] Detected core/server module update ({affected_modules}). Triggering Master self-restart...")
            self.restart_server()
        else:
            self.logger.info(f"[Server] Detected domain module update ({affected_modules or 'unknown'}). Reloading Warm Worker...")
            try:
                self.restart_worker()
            except WorkerSpawnError as err:
                self.logger.error(f"[Server] Warm Worker reload failed; next dispatch will retry spawning: {err}")

    def _perform_self_restart(self) -> int:
        """
        Executes the ordered self-restart handover sequence:
        stops watcher, terminates and reaps the worker, closes the HTTP server,
        releases the singleton lock, archives and closes the logger, and spawns
        a detached replacement Master daemon.

        Returns:
            int: PID of the newly spawned replacement Master process, or 0 on failure.
        """
        try:
            self.stop()
        except Exception as err:
            try:
                self.logger.warning(f"[Server] Error stopping daemon during restart: {err}")
            except Exception:
                pass

        try:
            return spawn_detached_master(
                yscb_root=self.yscb_root,
                idle_timeout_sec=self.idle_timeout_sec,
                enable_watcher=self.enable_watcher,
            )
        except Exception:
            return 0

    def restart_server(self) -> None:
        """
        Gracefully restarts the entire Server daemon (Master + Worker).
        Guarded by _restarting flag so a single Master instance only ever spawns one replacement.
        """
        with self._stop_lock:
            if self._restarting or self._is_stopped:
                return
            self._restarting = True

        if self.watcher:
            try:
                self.watcher.stop()
            except Exception:
                pass

        self.logger.info("Initiating graceful MasterSupervisor self-restart...")

        def _do_restart() -> None:
            try:
                self._perform_self_restart()
            finally:
                os._exit(0)

        t = threading.Thread(target=_do_restart, daemon=True, name="server-self-restart")
        t.start()

    def _ensure_ready_worker(self) -> subprocess.Popen:
        """
        Ensures a live (alive-handshaked) worker subprocess exists and returns its Popen handle.

        Raises:
            WorkerSpawnError: if a required respawn fails the alive handshake.
        """
        with self._worker_lock:
            if not self._worker_proc or self._worker_proc.poll() is not None:
                self._spawn_worker_locked()
                self._write_state()
            return self._worker_proc  # type: ignore

    def _wait_worker_ready(self, timeout_sec: Optional[float] = None) -> bool:
        """
        Blocks until the current worker reports `worker_ready` (FR-09).

        Args:
            timeout_sec: Optional upper bound; None waits as long as the worker stays alive.

        Returns:
            bool: True once ready; False if the worker died (EC-07) or the timeout elapsed.
        """
        deadline = None if timeout_sec is None else time.time() + timeout_sec
        while True:
            proc = self._worker_proc
            event = self._worker_ready_event
            if proc is None or proc.poll() is not None:
                return False
            if event.is_set():
                return True
            if deadline is not None and time.time() >= deadline:
                return False
            event.wait(0.1)

    def _stream_task_over_worker_pipe(
        self,
        proc: subprocess.Popen,
        target_mod: str,
        req_payload: Dict[str, Any],
        chunk_emitter: Callable[[Dict[str, Any]], None],
    ) -> int:
        """Writes dispatch payload to worker stdin and relays NDJSON stream chunks until task_finish."""
        try:
            req_line = json.dumps(req_payload) + "\n"
            proc.stdin.write(req_line.encode("utf-8"))  # type: ignore
            proc.stdin.flush()  # type: ignore
        except Exception as e:
            self.logger.error(f"Failed to write task payload to worker stdin: {e}", exc_info=e)
            chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": str(e)})
            return 1

        exit_code = 0
        while True:
            try:
                line = proc.stdout.readline()  # type: ignore
                if not line:
                    err_text = self._worker_eof_error(proc)
                    self.logger.error(f"{err_text} during dispatch for module='{target_mod}'")
                    chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": err_text})
                    return 1

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                packet = json.loads(line_str)
                if packet.get("type") == "touch_activity":
                    self.touch_activity(source=str(packet.get("source") or "worker"))
                    continue
                if packet.get("type") == "log":
                    self.logger.log(
                        packet.get("level", "INFO"),
                        packet.get("msg", ""),
                        component=packet.get("component", "worker"),
                    )
                    continue

                chunk_emitter(packet)

                if packet.get("type") == "task_finish":
                    exit_code = packet.get("exit_code", 0)
                    dur_ms = packet.get("duration_ms", 0.0)
                    self.logger.info(f"Task dispatch finished: module='{target_mod}', exit_code={exit_code}, duration={dur_ms:.1f}ms")
                    break
            except Exception as ex:
                if proc.pid in self._preempted_pids:
                    # EC-02: pipe closed by a preempting restart/stop
                    self._preempted_pids.discard(proc.pid)
                    self.logger.warning(f"Dispatch for module='{target_mod}' preempted: {_PREEMPTED_ERROR}")
                    chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": _PREEMPTED_ERROR})
                    return 1
                self.logger.error(f"Exception during worker stream reading: {ex}", exc_info=ex)
                chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": str(ex)})
                return 1

        self._last_active_time = time.time()
        return exit_code

    def _worker_eof_error(self, proc: subprocess.Popen) -> str:
        """Classifies a worker stdout EOF as preemption (EC-02) or unexpected closure."""
        if proc.pid in self._preempted_pids:
            self._preempted_pids.discard(proc.pid)
            return _PREEMPTED_ERROR
        return "Worker stdout closed unexpectedly"

    def dispatch_task(self, req_data: Dict[str, Any], chunk_emitter: Any) -> int:
        """
        Dispatches a CLI task to the warm worker sequentially under `_dispatch_lock`.

        Tracks `current_task` for status reporting, waits for a warming worker to become
        ready (FR-09), and converts `WorkerSpawnError` into a failing `task_finish` (EC-08).
        """
        with self._worker_lock:
            self._last_active_time = time.time()
            self._tasks_executed += 1

        target_mod = req_data.get("module", "unknown")
        cmd_args = req_data.get("args", [])
        self.logger.info(f"Task dispatch requested: module='{target_mod}', args={cmd_args}")

        with self._dispatch_lock:
            self._current_task = {"module": target_mod, "args": list(cmd_args), "started_at": time.time()}
            try:
                try:
                    proc = self._ensure_ready_worker()
                except WorkerSpawnError as err:
                    self.logger.error(f"Task dispatch aborted: {err}")
                    chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": str(err)})
                    return 1
                if not self._wait_worker_ready():
                    err_text = self._worker_eof_error(proc)
                    if err_text != _PREEMPTED_ERROR:
                        err_text = "Worker exited before becoming ready"
                    self.logger.error(f"Task dispatch aborted for module='{target_mod}': {err_text}")
                    chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": err_text})
                    return 1
                req_payload = {
                    "action": "dispatch",
                    "module": req_data["module"],
                    "args": cmd_args,
                    "cwd": req_data.get("cwd", self.yscb_root),
                    "env": req_data.get("env"),
                }
                return self._stream_task_over_worker_pipe(proc, target_mod, req_payload, chunk_emitter)
            finally:
                self._current_task = None
                # Dispatch is serialized; stale preemption markers never outlive their task
                self._preempted_pids.clear()

    def _spawn_worker_locked(self) -> int:
        """
        Spawns a warm worker (caller holds `_worker_lock`) using a two-stage handshake (FR-09).

        Waits up to `worker_alive_timeout_sec` for `worker_alive`; afterwards the worker is in
        state `warming` and a background reader waits (unbounded while alive) for `worker_ready`.
        POSIX workers run in their own session so `terminate_popen_tree` can kill the whole tree.

        Returns:
            int: PID of the alive worker.

        Raises:
            WorkerSpawnError: if the worker exits or stays silent before `worker_alive` (EC-08).
        """
        worker_script = os.path.join(os.path.dirname(__file__), "worker.py")
        cmd = [sys.executable, worker_script, "--yscb-root", self.yscb_root]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        from core.platform.venv import get_venv_site_packages

        site_pkg = get_venv_site_packages(self.yscb_root)

        py_paths = [
            self.yscb_root,
            os.path.join(self.yscb_root, ".modules"),
            os.path.join(self.yscb_root, ".modules", "core"),
            os.path.join(self.yscb_root, ".modules", "server"),
        ]
        host_cand = os.path.dirname(self.yscb_root)
        if os.path.isfile(os.path.join(host_cand, "yscb.config.json")):
            norm_host = host_cand.replace("\\", "/")
            if "/source/" not in norm_host and not norm_host.endswith("/source"):
                py_paths.append(host_cand)
        try:
            from core import uri
            proj_dir = uri.resolve("project://", interactive=False)
            if proj_dir and os.path.isdir(proj_dir):
                norm_proj = os.path.abspath(proj_dir).replace("\\", "/")
                if "/source/" not in norm_proj and not norm_proj.endswith("/source"):
                    if proj_dir not in py_paths:
                        py_paths.append(proj_dir)
        except Exception:
            pass
        if os.path.isdir(site_pkg):
            py_paths.insert(0, site_pkg)
        curr_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join([p for p in py_paths if os.path.isdir(p)] + ([curr_pp] if curr_pp else []))

        popen_kwargs: Dict[str, Any] = {"close_fds": True}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        else:
            popen_kwargs["start_new_session"] = True

        ready_event = threading.Event()
        alive_event = threading.Event()
        self._worker_ready_event = ready_event
        proc = subprocess.Popen(
            cmd,
            cwd=self.yscb_root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            **popen_kwargs,
        )
        self._worker_proc = proc

        def _drain_stderr(pipe: Any, pid: int) -> None:
            try:
                for line in iter(pipe.readline, b""):
                    if not line:
                        break
                    line_str = line.decode("utf-8", errors="replace").rstrip()
                    if line_str:
                        self.logger.error(f"[Worker:{pid}:stderr] {line_str}")
            except Exception:
                pass
            finally:
                try:
                    pipe.close()
                except OSError:
                    pass

        threading.Thread(target=_drain_stderr, args=(proc.stderr, proc.pid), daemon=True, name=f"worker-stderr-{proc.pid}").start()

        def _read_handshake() -> None:
            try:
                while True:
                    line = proc.stdout.readline()  # type: ignore
                    if not line:
                        break
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if not line_str:
                        continue
                    data = json.loads(line_str)
                    pkt_type = data.get("type")
                    if pkt_type == "log":
                        self.logger.log(data.get("level", "INFO"), data.get("msg", ""), component=data.get("component", "worker"))
                        continue
                    if pkt_type == "touch_activity":
                        self.touch_activity(source=str(data.get("source") or "worker"))
                        continue
                    if pkt_type == "worker_alive":
                        alive_event.set()
                        continue
                    if pkt_type == "worker_ready":
                        if "services" in data and isinstance(data["services"], list):
                            self._worker_services = data["services"]
                        alive_event.set()
                        ready_event.set()
                        if self._worker_proc is proc:
                            self._warming_since = None
                        self.logger.info(f"Warm Worker (PID: {proc.pid}) ready")
                        break
            except (OSError, ValueError) as err:
                # Pipe closed by kill or malformed handshake line: the worker is treated as not ready
                self.logger.warning(f"Warm Worker (PID: {proc.pid}) handshake reader stopped: {err}")

        t = threading.Thread(target=_read_handshake, daemon=True, name=f"worker-handshake-{proc.pid}")
        t.start()

        deadline = time.time() + self._worker_alive_timeout_sec
        while not alive_event.is_set() and time.time() < deadline and proc.poll() is None:
            alive_event.wait(0.05)

        if not alive_event.is_set() or proc.poll() is not None:
            reason = "exited prematurely" if proc.poll() is not None else (
                f"sent no worker_alive within {self._worker_alive_timeout_sec:.1f}s"
            )
            self.logger.warning(f"Warm Worker (PID: {proc.pid}) failed alive handshake ({reason}); cleaning up.")
            self._kill_worker_locked(timeout_sec=1.0)
            t.join(timeout=0.5)
            raise WorkerSpawnError(f"Warm Worker (PID: {proc.pid}) failed alive handshake: {reason}")

        if not ready_event.is_set():
            self._warming_since = time.time()
        return proc.pid

    def touch_activity(self, source: str = "probe") -> float:
        """Refreshes `_last_active_time` to prevent idle auto-shutdown while background workers are active."""
        now = time.time()
        self._last_active_time = now
        return max(0.0, self.idle_timeout_sec - (now - self._last_active_time))

    def _idle_ttl_loop(self) -> None:
        while self._is_running:
            time.sleep(2.0)
            if not self._is_running:
                break
            idle_seconds = time.time() - self._last_active_time
            if self.idle_timeout_sec > 0 and idle_seconds >= self.idle_timeout_sec:
                self.logger.info(f"Idle TTL ({self.idle_timeout_sec}s) reached. Initiating automatic shutdown...")
                threading.Thread(target=self.stop, daemon=True).start()
                break

    def _write_state(self) -> None:
        worker_pid = self._worker_proc.pid if self._worker_proc else 0
        state = ServerDaemonState(
            pid=os.getpid(),
            worker_pid=worker_pid,
            port=self.port,
            token=self.token,
            root=self.yscb_root,
            start_time=self._start_time,
            idle_timeout_sec=self.idle_timeout_sec,
            tasks_executed=self._tasks_executed,
        )
        vfs.write_json(self.state_file, asdict(state), indent=2, atomic=True)
        try:
            os.chmod(self.state_file, 0o600)
        except OSError:
            pass

    def _cleanup_state(self) -> None:
        """
        Removes daemon.json only. daemon.lock is intentionally kept (FR-13): deleting it would let
        a concurrent starter lock a fresh inode while another holds the unlinked one; liveness is
        always decided by lock ownership (EC-11).
        """
        try:
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
        except OSError as err:
            self.logger.warning(f"Failed to remove daemon state file {self.state_file}: {err}")


def _create_http_server(supervisor: MasterSupervisor) -> http.server.HTTPServer:
    class DispatcherHTTPHandler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send_json_response(self, status_code: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authenticate(self) -> bool:
            auth_header = self.headers.get("Authorization", "")
            expected = f"Bearer {supervisor.token}"
            if not secrets.compare_digest(auth_header, expected):
                supervisor.logger.warning(f"HTTP Unauthorized access attempt to {self.path}")
                self._send_json_response(403, {"error": "Unauthorized"})
                return False
            return True

        def do_GET(self) -> None:
            t0 = time.time()
            parsed = urlparse(self.path)
            if parsed.path == "/api/status":
                if not self._authenticate():
                    return
                self._send_json_response(200, supervisor.get_status_dict())
                dur_ms = (time.time() - t0) * 1000.0
                supervisor.logger.info(f"HTTP GET /api/status -> 200 ({dur_ms:.1f}ms)")
            else:
                self.send_response(404)
                self.end_headers()
                supervisor.logger.warning(f"HTTP GET {parsed.path} -> 404 Not Found")

        def _handle_post_dispatch(self, t0: float) -> None:
            content_len = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_len).decode("utf-8")
            try:
                req_data = json.loads(raw_body)
            except ValueError:
                self._send_json_response(400, {"error": "Invalid JSON"})
                supervisor.logger.warning("HTTP POST /api/dispatch -> 400 Invalid JSON")
                return

            req_root = req_data.get("yscb_root")
            if req_root:
                req_abs = os.path.abspath(req_root)
                if req_abs != supervisor.yscb_root and req_abs != os.path.dirname(supervisor.yscb_root):
                    self._send_json_response(400, {"error": "Workspace Root Mismatch"})
                    supervisor.logger.warning(f"HTTP POST /api/dispatch -> 400 Workspace Root Mismatch ({req_abs})")
                    return

            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def chunk_emitter(packet: Dict[str, Any]) -> None:
                chunk_bytes = (json.dumps(packet) + "\n").encode("utf-8")
                chunk_header = f"{len(chunk_bytes):X}\r\n".encode("utf-8")
                try:
                    self.wfile.write(chunk_header + chunk_bytes + b"\r\n")
                    self.wfile.flush()
                except OSError:
                    pass

            supervisor.dispatch_task(req_data, chunk_emitter)
            self.close_connection = True
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except OSError:
                pass
            dur_ms = (time.time() - t0) * 1000.0
            supervisor.logger.info(f"HTTP POST /api/dispatch -> 200 ({dur_ms:.1f}ms)")

        def do_POST(self) -> None:
            t0 = time.time()
            parsed = urlparse(self.path)
            if not self._authenticate():
                return

            if parsed.path == "/api/dispatch":
                self._handle_post_dispatch(t0)
            elif parsed.path == "/api/touch":
                idle_left = supervisor.touch_activity(source="http")
                self._send_json_response(
                    200,
                    {
                        "status": "ok",
                        "idle_seconds_left": idle_left,
                        "idle_timeout_sec": supervisor.idle_timeout_sec,
                    },
                )
            elif parsed.path == "/api/reload":
                try:
                    new_pid = supervisor.restart_worker()
                except WorkerSpawnError as err:
                    self._send_json_response(500, {"error": str(err)})
                    supervisor.logger.error(f"HTTP POST /api/reload -> 500 ({err})")
                    return
                self._send_json_response(200, {"status": "worker_restarted", "new_worker_pid": new_pid})
                dur_ms = (time.time() - t0) * 1000.0
                supervisor.logger.info(f"HTTP POST /api/reload -> 200 ({dur_ms:.1f}ms, New PID: {new_pid})")
            elif parsed.path == "/api/shutdown":
                worker_pid = supervisor._worker_proc.pid if supervisor._worker_proc else 0
                uptime = time.time() - supervisor._start_time
                summary = {
                    "pid": os.getpid(),
                    "worker_pid": worker_pid,
                    "uptime_seconds": uptime,
                    "tasks_executed": supervisor._tasks_executed,
                    "services_stopped": len(supervisor._worker_services),
                    "reason": "Graceful CLI shutdown request",
                    "archive_log": supervisor.logger.get_expected_archive_path(),
                }
                self._send_json_response(200, {"status": "shutting_down", "summary": summary})
                dur_ms = (time.time() - t0) * 1000.0
                supervisor.logger.info(f"HTTP POST /api/shutdown -> 200 ({dur_ms:.1f}ms, Uptime: {uptime:.1f}s)")
                threading.Thread(target=supervisor.stop, daemon=True).start()
            else:
                self.send_response(404)
                self.end_headers()
                supervisor.logger.warning(f"HTTP POST {parsed.path} -> 404 Not Found")

    return http.server.ThreadingHTTPServer(("127.0.0.1", 0), DispatcherHTTPHandler)
