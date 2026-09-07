"""
Server Module - Master Supervisor & Localhost HTTP Server.

Coordinates daemon state, dynamic port binding (127.0.0.1:0), security bearer token,
single warm worker subprocess lifecycle, idle TTL auto-shutdown, and serialized dispatch queue.
"""

from dataclasses import asdict, dataclass
import http.server
import json
import importlib
import logging
import os
import platform
import queue
import secrets
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

from core import vfs
from core.platform import is_process_alive, kill_process_tree, InterProcessLock, ensure_private_venv, spawn_detached
from server.service import ServiceManager
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

        self.service_manager = ServiceManager()
        self.watcher: Optional[ModulesWatcher] = None

        self._worker_proc: Optional[subprocess.Popen] = None
        self._worker_lock = threading.Lock()
        self._task_queue = queue.Queue()

        self._last_active_time = time.time()
        self._tasks_executed = 0
        self._is_running = False
        self._httpd: Optional[http.server.HTTPServer] = None
        self.port = 0

    def start(self, foreground: bool = False) -> int:
        """Starts the master supervisor."""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

        lock = InterProcessLock(self.lock_file)
        if not lock.acquire(blocking=False):
            state = self.read_state()
            if state and is_process_alive(state.pid):
                return state.pid
            # If lock held by dead process, cleanup and proceed

        self._is_running = True
        self._last_active_time = time.time()

        # 1. Start HTTP Server on dynamic port 127.0.0.1:0
        self._httpd = _create_http_server(self)
        self.port = self._httpd.server_address[1]

        # 2. Spawn initial Warm Worker
        self._spawn_worker()

        # 3. Write daemon.json state file
        self._write_state()

        # 4. Start ModulesWatcher
        if self.enable_watcher:
            modules_dir = os.path.join(self.yscb_root, ".modules")
            self.watcher = ModulesWatcher(modules_dir, on_change_callback=self.on_modules_changed, debounce_sec=0.5)
            self.watcher.start()

        # 5. Discover and Start Service Workers
        self._discover_service_workers()
        self.service_manager.start_all({"yscb_root": self.yscb_root})

        # 6. Start Idle TTL checker thread
        if self.idle_timeout_sec > 0:
            ttl_thread = threading.Thread(target=self._idle_ttl_loop, daemon=True, name="idle-ttl")
            ttl_thread.start()

        if foreground:
            try:
                self._httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()
        else:
            self._http_thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="http-server")
            self._http_thread.start()

        return os.getpid()

    def _discover_service_workers(self) -> None:
        """Dynamically discovers and registers pluggable service workers from domain modules via core SDK."""
        try:
            from core import contributes
            server_contrib = contributes.get("server", default={})
        except Exception as e:
            logger.warning(f"[Server] Failed loading server contributes via core SDK: {e}")
            return

        services_config = server_contrib.get("services", [])
        if isinstance(services_config, dict):
            services_config = [services_config]

        for item in services_config:
            if not isinstance(item, dict):
                continue
            worker_cls_path = item.get("worker_class")
            donor_mod = item.get("__provider__", "unknown")
            name = item.get("name", f"{donor_mod}-worker")
            desc = item.get("description", "")
            if not worker_cls_path:
                continue

            for mod_cand in [
                os.path.join(self.yscb_root, ".modules", donor_mod),
                os.path.join(self.yscb_root, "source", donor_mod),
            ]:
                if os.path.isdir(mod_cand) and mod_cand not in sys.path:
                    sys.path.insert(0, mod_cand)

            try:
                if ":" in worker_cls_path:
                    mod_path, cls_name = worker_cls_path.split(":", 1)
                else:
                    mod_path, cls_name = worker_cls_path.rsplit(".", 1)
                mod = importlib.import_module(mod_path)
                cls = getattr(mod, cls_name)
                worker_instance = cls(self.yscb_root)
                self.service_manager.register(worker_instance, provider=donor_mod, description=desc)
                logger.info(f"[Server Service] Registered worker '{name}' from module '{donor_mod}'")
            except Exception as ex:
                logger.warning(f"[Server Service] Failed to instantiate worker '{name}' from module '{donor_mod}': {ex}")

    def stop(self, force: bool = False) -> None:
        """Stops the master supervisor and all child workers."""
        self._is_running = False

        if self.watcher:
            self.watcher.stop()
            self.watcher = None

        self.service_manager.stop_all(timeout_sec=2.0)

        with self._worker_lock:
            if self._worker_proc:
                try:
                    kill_process_tree(self._worker_proc.pid, timeout_sec=2.0)
                except Exception:
                    pass
                self._worker_proc = None

        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None

        self._cleanup_state()

    def restart_worker(self) -> int:
        """Terminates existing worker and spawns a fresh worker subprocess."""
        with self._worker_lock:
            if self._worker_proc:
                try:
                    kill_process_tree(self._worker_proc.pid, timeout_sec=1.5)
                except Exception:
                    pass
                self._worker_proc = None

            new_pid = self._spawn_worker_locked()
            self._write_state()
            return new_pid

    def on_modules_changed(self, affected_modules: Optional[Set[str]] = None) -> None:
        """
        Dual-channel reload dispatcher:
        - If 'server' or 'core' changed: triggers restart_server()
        - Otherwise: triggers restart_worker()
        """
        if affected_modules and ("server" in affected_modules or "core" in affected_modules):
            logger.info(f"[Server] Detected core/server module update ({affected_modules}). Triggering Master self-restart...")
            self.restart_server()
        else:
            logger.info(f"[Server] Detected domain module update ({affected_modules or 'unknown'}). Reloading Warm Worker...")
            self.restart_worker()

    def restart_server(self) -> None:
        """
        Gracefully restarts the entire Server daemon (Master + Worker).
        Cleans up current Master instance and spawns a fresh detached Master daemon.
        """
        def _do_restart():
            try:
                # 1. Stop current Master resources
                self.stop()
            except Exception as e:
                logger.warning(f"[Server] Error stopping daemon during restart: {e}")

            # 2. Spawn detached new Master daemon
            try:
                core_dir = os.path.join(self.yscb_root, ".modules", "core")
                if not os.path.isdir(core_dir):
                    core_dir = os.path.join(self.yscb_root, "source", "core")
                server_dir = os.path.join(self.yscb_root, ".modules", "server")
                if not os.path.isdir(server_dir):
                    server_dir = os.path.join(self.yscb_root, "source", "server")

                cmd = [
                    sys.executable,
                    "-c",
                    f"import sys; "
                    f"sys.path.insert(0, r'{core_dir}'); "
                    f"sys.path.insert(0, r'{server_dir}'); "
                    f"from server.master import MasterSupervisor; MasterSupervisor(r'{self.yscb_root}', idle_timeout_sec={self.idle_timeout_sec}, enable_watcher={self.enable_watcher}).start(foreground=True)",
                ]
                spawn_detached(cmd, cwd=self.yscb_root)
            except Exception as ex:
                logger.error(f"[Server] Failed to spawn new Master daemon: {ex}")
            finally:
                # 3. Exit current process
                os._exit(0)

        t = threading.Thread(target=_do_restart, daemon=True, name="server-self-restart")
        t.start()

    def dispatch_task(self, req_data: Dict[str, Any], chunk_emitter: Any) -> int:
        """Dispatches a CLI task to the warm worker sequentially."""
        self._last_active_time = time.time()
        self._tasks_executed += 1

        with self._worker_lock:
            if not self._worker_proc or not is_process_alive(self._worker_proc.pid):
                self._spawn_worker_locked()
                self._write_state()

            proc = self._worker_proc

        req_payload = {
            "action": "dispatch",
            "module": req_data["module"],
            "args": req_data.get("args", []),
            "cwd": req_data.get("cwd", self.yscb_root),
            "env": req_data.get("env"),
        }

        # Send request line to worker
        try:
            req_line = json.dumps(req_payload) + "\n"
            proc.stdin.write(req_line.encode("utf-8"))
            proc.stdin.flush()
        except Exception as e:
            chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": str(e)})
            return 1

        exit_code = 0
        # Read stream chunks from worker until task_finish
        while True:
            try:
                line = proc.stdout.readline()
                if not line:
                    chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": "Worker stdout closed unexpectedly"})
                    return 1

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                packet = json.loads(line_str)
                chunk_emitter(packet)

                if packet.get("type") == "task_finish":
                    exit_code = packet.get("exit_code", 0)
                    break
            except Exception as ex:
                chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": str(ex)})
                return 1

        self._last_active_time = time.time()
        return exit_code

    def _spawn_worker(self) -> int:
        with self._worker_lock:
            return self._spawn_worker_locked()

    def _spawn_worker_locked(self) -> int:
        worker_script = os.path.join(os.path.dirname(__file__), "worker.py")
        cmd = [sys.executable, worker_script, "--yscb-root", self.yscb_root]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # Ensure child worker has access to source, modules, and private .venv
        tag, sys_name = f"py{sys.version_info.major}{sys.version_info.minor}", platform.system()
        sub = os.path.join(".venv", tag, "Lib", "site-packages") if sys_name == "Windows" else os.path.join(".venv", tag, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
        site_pkg = os.path.join(self.yscb_root, sub)

        py_paths = [
            self.yscb_root,
            os.path.join(self.yscb_root, ".modules"),
            os.path.join(self.yscb_root, ".modules", "core"),
            os.path.join(self.yscb_root, "source"),
            os.path.join(self.yscb_root, "source", "core"),
            os.path.join(self.yscb_root, "source", "server"),
        ]
        if os.path.isdir(site_pkg):
            py_paths.insert(0, site_pkg)
        curr_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join([p for p in py_paths if os.path.isdir(p)] + ([curr_pp] if curr_pp else []))

        proc = subprocess.Popen(
            cmd,
            cwd=self.yscb_root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self._worker_proc = proc

        # Non-blocking wait for worker_ready packet with 3.0s timeout
        ready_received = False
        def _read_ready():
            nonlocal ready_received
            try:
                line = proc.stdout.readline()
                if line:
                    data = json.loads(line.decode("utf-8", errors="replace").strip())
                    if data.get("type") == "worker_ready":
                        ready_received = True
            except Exception:
                pass

        t = threading.Thread(target=_read_ready, daemon=True)
        t.start()
        t.join(timeout=3.0)

        return proc.pid


    def _idle_ttl_loop(self) -> None:
        while self._is_running:
            time.sleep(2.0)
            if not self._is_running:
                break
            idle_seconds = time.time() - self._last_active_time
            if self.idle_timeout_sec > 0 and idle_seconds >= self.idle_timeout_sec:
                logging.info(f"[Server Master] Idle TTL ({self.idle_timeout_sec}s) reached. Shutting down...")
                # Run shutdown in a separate thread so it doesn't block the loop
                threading.Thread(target=self.stop, daemon=True).start()
                break

    def read_state(self) -> Optional[ServerDaemonState]:
        if not os.path.exists(self.state_file):
            return None
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                d = json.load(f)
                return ServerDaemonState(**d)
        except Exception:
            return None

    def _write_state(self) -> None:
        worker_pid = self._worker_proc.pid if self._worker_proc else 0
        state = ServerDaemonState(
            pid=os.getpid(),
            worker_pid=worker_pid,
            port=self.port,
            token=self.token,
            root=self.yscb_root,
            start_time=time.time(),
            idle_timeout_sec=self.idle_timeout_sec,
            tasks_executed=self._tasks_executed,
        )
        vfs.write_json(self.state_file, asdict(state), indent=2, atomic=True)

    def _cleanup_state(self) -> None:
        try:
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
        except OSError:
            pass
        try:
            if os.path.exists(self.lock_file):
                os.remove(self.lock_file)
        except OSError:
            pass


def _create_http_server(supervisor: MasterSupervisor) -> http.server.HTTPServer:
    class DispatcherHTTPHandler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):
            # Suppress default stdout request logging
            pass

        def _authenticate(self) -> bool:
            auth_header = self.headers.get("Authorization", "")
            expected = f"Bearer {supervisor.token}"
            if auth_header != expected:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized"}\n')
                return False
            return True

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/status":
                if not self._authenticate():
                    return
                worker_pid = supervisor._worker_proc.pid if supervisor._worker_proc else 0
                idle_left = max(0.0, supervisor.idle_timeout_sec - (time.time() - supervisor._last_active_time))
                status_payload = {
                    "status": "running",
                    "state": "ready" if is_process_alive(worker_pid) else "restarting",
                    "pid": os.getpid(),
                    "worker_pid": worker_pid,
                    "port": supervisor.port,
                    "root": supervisor.yscb_root,
                    "tasks_executed": supervisor._tasks_executed,
                    "idle_seconds_left": idle_left,
                    "services": supervisor.service_manager.get_status(),
                }
                body = json.dumps(status_payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            parsed = urlparse(self.path)
            if not self._authenticate():
                return

            if parsed.path == "/api/dispatch":
                content_len = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_len).decode("utf-8")
                try:
                    req_data = json.loads(raw_body)
                except Exception:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Invalid JSON"}\n')
                    return

                # Check workspace root isolation (matches either yscb_root or parent host dir)
                req_root = req_data.get("yscb_root")
                if req_root:
                    req_abs = os.path.abspath(req_root)
                    if req_abs != supervisor.yscb_root and req_abs != os.path.dirname(supervisor.yscb_root):
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b'{"error": "Workspace Root Mismatch"}\n')
                        return

                # Send 200 chunked response
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()

                def chunk_emitter(packet: Dict[str, Any]):
                    chunk_bytes = (json.dumps(packet) + "\n").encode("utf-8")
                    chunk_header = f"{len(chunk_bytes):X}\r\n".encode("utf-8")
                    try:
                        self.wfile.write(chunk_header + chunk_bytes + b"\r\n")
                        self.wfile.flush()
                    except Exception:
                        pass

                supervisor.dispatch_task(req_data, chunk_emitter)
                self.close_connection = True
                # Send terminal 0 chunk
                try:
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except Exception:
                    pass

            elif parsed.path == "/api/reload":
                new_pid = supervisor.restart_worker()
                resp = json.dumps({"status": "worker_restarted", "new_worker_pid": new_pid}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

            elif parsed.path == "/api/shutdown":
                resp = json.dumps({"status": "shutting_down"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
                threading.Thread(target=supervisor.stop, daemon=True).start()

            else:
                self.send_response(404)
                self.end_headers()

    return http.server.ThreadingHTTPServer(("127.0.0.1", 0), DispatcherHTTPHandler)
