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
    ensure_private_venv,
    is_process_alive,
    kill_process_tree,
    set_process_title,
    spawn_detached,
)
from server.logger import ServerLogger
from server.watcher import ModulesWatcher


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
        data = vfs.read_json(state_file, default=None)
        if isinstance(data, dict):
            return ServerDaemonState(**data)
    except Exception:
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
    core_dir = os.path.join(yscb_root, ".modules", "core")
    server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    core_p = os.path.abspath(core_dir).replace("\\", "/")
    server_p = os.path.abspath(server_dir).replace("\\", "/")
    root_p = os.path.abspath(yscb_root).replace("\\", "/")

    cmd = [
        sys.executable,
        "-c",
        f"import sys; "
        f"sys.path.insert(0, '{core_p}'); "
        f"sys.path.insert(0, '{server_p}'); "
        f"from server.master import MasterSupervisor; "
        f"MasterSupervisor('{root_p}', idle_timeout_sec={idle_timeout_sec}, enable_watcher={enable_watcher}).start(foreground=True)",
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
        idle_timeout_sec: float = 900.0,
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

    def get_status_dict(self) -> Dict[str, Any]:
        """Returns structured dictionary of server runtime status."""
        worker_pid = self._worker_proc.pid if self._worker_proc else 0
        uptime = time.time() - self._start_time
        idle_left = max(0.0, self.idle_timeout_sec - (time.time() - self._last_active_time))
        watcher_status = {
            "enabled": self.enable_watcher,
            "active": (self.watcher is not None and self.watcher.is_running),
            "monitored_dir": self.watcher.modules_dir if self.watcher else None,
        }
        return {
            "status": "running",
            "state": "ready" if is_process_alive(worker_pid) else "restarting",
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
        }

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
            self._spawn_worker_locked()
        self.logger.info(f"Initial Warm Worker spawned (PID: {self._worker_proc.pid if self._worker_proc else 0})")
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
            return 0

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
            self.logger.archive_and_close()

    def _kill_worker_locked(self, timeout_sec: float = 2.0) -> None:
        """Safely terminates child worker process with two-stage handshake and closes all pipe handles."""
        if not self._worker_proc:
            return
        proc = self._worker_proc

        exited_gracefully = False
        try:
            if proc.poll() is None and proc.stdin:
                proc.stdin.write(b'{"action": "exit"}\n')
                proc.stdin.flush()
                wait_timeout = min(timeout_sec, 1.5)
                proc.wait(timeout=wait_timeout)
                exited_gracefully = True
        except Exception:
            pass

        if not exited_gracefully and proc.poll() is None:
            try:
                kill_process_tree(proc.pid, timeout_sec=timeout_sec)
            except Exception:
                pass

        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe:
                try:
                    pipe.close()
                except OSError:
                    pass
        self._worker_proc = None

    def restart_worker(self) -> int:
        """Terminates existing worker and spawns a fresh worker subprocess while syncing ServerConfig."""
        with self._worker_lock:
            old_pid = self._worker_proc.pid if self._worker_proc else 0
            self.logger.info(f"Restarting Warm Worker (terminating old PID: {old_pid})...")
            self._kill_worker_locked(timeout_sec=1.5)

            try:
                from server.config import ServerConfig
                cfg = ServerConfig.load()
                self.idle_timeout_sec = float(cfg.idle_timeout_sec)
            except Exception:
                pass

            new_pid = self._spawn_worker_locked()
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
            self.restart_worker()

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
                self.stop()
            except Exception as e:
                self.logger.warning(f"[Server] Error stopping daemon during restart: {e}")

            try:
                spawn_detached_master(
                    yscb_root=self.yscb_root,
                    idle_timeout_sec=self.idle_timeout_sec,
                    enable_watcher=self.enable_watcher,
                )
            except Exception as ex:
                self.logger.error(f"[Server] Failed to spawn new Master daemon: {ex}")
            finally:
                os._exit(0)

        t = threading.Thread(target=_do_restart, daemon=True, name="server-self-restart")
        t.start()

    def _ensure_ready_worker(self) -> subprocess.Popen:
        """Ensures a live worker subprocess is running and returns its Popen handle."""
        with self._worker_lock:
            if not self._worker_proc or not is_process_alive(self._worker_proc.pid):
                self._spawn_worker_locked()
                self._write_state()
            return self._worker_proc  # type: ignore

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
                    self.logger.error(f"Worker stdout closed unexpectedly during dispatch for module='{target_mod}'")
                    chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": "Worker stdout closed unexpectedly"})
                    return 1

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                packet = json.loads(line_str)
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
                self.logger.error(f"Exception during worker stream reading: {ex}", exc_info=ex)
                chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": str(ex)})
                return 1

        self._last_active_time = time.time()
        return exit_code

    def dispatch_task(self, req_data: Dict[str, Any], chunk_emitter: Any) -> int:
        """Dispatches a CLI task to the warm worker sequentially under _dispatch_lock."""
        self._last_active_time = time.time()
        self._tasks_executed += 1

        target_mod = req_data.get("module", "unknown")
        cmd_args = req_data.get("args", [])
        self.logger.info(f"Task dispatch requested: module='{target_mod}', args={cmd_args}")

        with self._dispatch_lock:
            proc = self._ensure_ready_worker()
            req_payload = {
                "action": "dispatch",
                "module": req_data["module"],
                "args": cmd_args,
                "cwd": req_data.get("cwd", self.yscb_root),
                "env": req_data.get("env"),
            }
            return self._stream_task_over_worker_pipe(proc, target_mod, req_payload, chunk_emitter)

    def _spawn_worker_locked(self) -> int:
        worker_script = os.path.join(os.path.dirname(__file__), "worker.py")
        cmd = [sys.executable, worker_script, "--yscb-root", self.yscb_root]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        tag, sys_name = f"py{sys.version_info.major}{sys.version_info.minor}", platform.system()
        sub = (
            os.path.join(".venv", tag, "Lib", "site-packages")
            if sys_name == "Windows"
            else os.path.join(".venv", tag, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
        )
        site_pkg = os.path.join(self.yscb_root, sub)

        py_paths = [
            self.yscb_root,
            os.path.join(self.yscb_root, ".modules"),
            os.path.join(self.yscb_root, ".modules", "core"),
            os.path.join(self.yscb_root, ".modules", "server"),
        ]
        if os.path.isdir(site_pkg):
            py_paths.insert(0, site_pkg)
        curr_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join([p for p in py_paths if os.path.isdir(p)] + ([curr_pp] if curr_pp else []))

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        proc = subprocess.Popen(
            cmd,
            cwd=self.yscb_root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            bufsize=0,
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

        ready_event = threading.Event()

        def _read_ready() -> None:
            try:
                while True:
                    line = proc.stdout.readline()  # type: ignore
                    if not line:
                        break
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if not line_str:
                        continue
                    data = json.loads(line_str)
                    if data.get("type") == "log":
                        self.logger.log(data.get("level", "INFO"), data.get("msg", ""), component=data.get("component", "worker"))
                        continue
                    if data.get("type") == "worker_ready":
                        if "services" in data and isinstance(data["services"], list):
                            self._worker_services = data["services"]
                        ready_event.set()
                        break
            except Exception:
                pass

        t = threading.Thread(target=_read_ready, daemon=True, name=f"worker-ready-{proc.pid}")
        t.start()
        t.join(timeout=3.0)

        if not ready_event.is_set() or proc.poll() is not None:
            self.logger.warning(f"Warm Worker (PID: {proc.pid}) failed readiness handshake or exited prematurely; cleaning up.")
            self._kill_worker_locked(timeout_sec=1.0)
            t.join(timeout=0.5)
            return 0

        return proc.pid

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

    def _cleanup_state(self) -> None:
        for fp in (self.state_file, self.lock_file):
            try:
                if os.path.exists(fp):
                    os.remove(fp)
            except OSError:
                pass


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
            if auth_header != expected:
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
            elif parsed.path == "/api/reload":
                new_pid = supervisor.restart_worker()
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
