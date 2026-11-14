"""
Server Module - Master Supervisor & Localhost HTTP Server.

Coordinates daemon state, dynamic port binding (127.0.0.1:0), security bearer token,
single warm worker subprocess lifecycle, idle TTL auto-shutdown, and serialized dispatch queue.
"""

from dataclasses import asdict, dataclass
import http.server
import json
import errno
import os
import queue
import secrets
import select
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from core import vfs
from core.log import RollingFileLogger, create_managed_thread, log
from core.context import get_env
from core.platform import (
    InterProcessLock,
    build_runtime_pythonpath,
    daemon_probe,
    ensure_private_venv,
    get_host_memory_info,
    get_process_rss_mb,
    is_process_alive,
    set_process_title,
    spawn_detached,
    terminate_popen_tree,
)
from server.config import (
    DEFAULT_IDLE_TIMEOUT_SEC,
    DEFAULT_WORKER_ALIVE_TIMEOUT_SEC,
    ServerConfig,
)
from server.watcher import ModulesWatcher


_PREEMPTED_ERROR = "Worker terminated by restart/stop"
_REJECTED_BEFORE_EXECUTION = -503
_WATCHER_DRAIN_TIMEOUT_SEC = 5.0


class WorkerSpawnError(RuntimeError):
    """Raised when a warm worker fails the `worker_alive` handshake (crashed or hung at startup)."""


class WorkerMemoryHealthMonitor:
    """
    Algorithmic memory health evaluator for persistent warm workers.

    Instead of enforcing a static MB cap, tracks the worker's post-warm-up working-set
    baseline (`baseline_rss_mb = max(median(initial_idle_samples), 256.0)`) and evaluates
    post-trim idle RSS (`current_rss_mb`) across three relative dimensions:
    1. Severe working-set bloat: expansion >= 3.5x AND delta >= 512 MB.
    2. Host RAM pressure + bloat: MemAvailable/MemTotal < 15% AND expansion >= 2.2x AND delta >= 256 MB.
    3. Sustained monotonic ratcheting: >= 5 consecutive idle windows with >= 64 MB growth each,
       expansion >= 2.5x, AND delta >= 384 MB.
    """

    MIN_BASELINE_FLOOR_MB: float = 256.0
    CALIBRATION_SAMPLES: int = 3
    RATCHET_STEP_MB: float = 64.0
    RATCHET_WINDOWS_REQUIRED: int = 5
    RECYCLE_COOLDOWN_SEC: float = 60.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.baseline_rss_mb: float = 0.0
        self.current_rss_mb: float = 0.0
        self.peak_rss_mb: float = 0.0
        self.consecutive_growth_windows: int = 0
        self.recycle_count: int = 0
        self.last_recycle_reason: Optional[str] = None
        self.last_recycle_time: float = 0.0
        self._calibration_samples: List[float] = []
        self._last_idle_sample_mb: float = 0.0

    def reset_for_new_worker(self, initial_rss_mb: float = 0.0) -> None:
        """Resets per-worker baseline calibration while preserving cumulative recycle telemetry."""
        with self._lock:
            self._calibration_samples.clear()
            self.consecutive_growth_windows = 0
            self._last_idle_sample_mb = 0.0
            self.current_rss_mb = max(0.0, float(initial_rss_mb))
            self.peak_rss_mb = self.current_rss_mb
            if initial_rss_mb > 0.0:
                self._calibration_samples.append(float(initial_rss_mb))
                self.baseline_rss_mb = max(float(initial_rss_mb), self.MIN_BASELINE_FLOOR_MB)
                self._last_idle_sample_mb = float(initial_rss_mb)
            else:
                self.baseline_rss_mb = 0.0

    def record_sample(self, rss_mb: float, is_idle: bool = False) -> None:
        """Updates current/peak RSS and refines initial idle baseline when calibrating."""
        if rss_mb <= 0.0:
            return
        with self._lock:
            val = float(rss_mb)
            self.current_rss_mb = val
            if val > self.peak_rss_mb:
                self.peak_rss_mb = val
            if is_idle and len(self._calibration_samples) < self.CALIBRATION_SAMPLES:
                if not self._calibration_samples or val <= self.baseline_rss_mb:
                    self._calibration_samples.append(val)
                    sorted_s = sorted(self._calibration_samples)
                    med = sorted_s[len(sorted_s) // 2]
                    self.baseline_rss_mb = max(med, self.MIN_BASELINE_FLOOR_MB)
                if self._last_idle_sample_mb <= 0.0:
                    self._last_idle_sample_mb = val

    def evaluate(
        self,
        current_rss_mb: float,
        host_mem: Optional[Dict[str, float]] = None,
        is_idle: bool = True,
    ) -> Tuple[bool, str]:
        """
        Evaluates whether an idle worker exhibits abnormal memory retention requiring auto-recycle.

        Returns `(should_recycle, reason)`. Never triggers when `is_idle` is False.
        """
        if current_rss_mb <= 0.0:
            return False, ""
        self.record_sample(current_rss_mb, is_idle=is_idle)
        if not is_idle:
            return False, ""

        now = time.time()
        with self._lock:
            if self.last_recycle_time > 0.0 and (now - self.last_recycle_time) < self.RECYCLE_COOLDOWN_SEC:
                return False, ""

            base = max(self.baseline_rss_mb, self.MIN_BASELINE_FLOOR_MB)
            if self.baseline_rss_mb <= 0.0:
                self.baseline_rss_mb = max(current_rss_mb, self.MIN_BASELINE_FLOOR_MB)
                base = self.baseline_rss_mb

            if self._last_idle_sample_mb > 0.0:
                if (current_rss_mb - self._last_idle_sample_mb) >= self.RATCHET_STEP_MB:
                    self.consecutive_growth_windows += 1
                    self._last_idle_sample_mb = current_rss_mb
                elif current_rss_mb < self._last_idle_sample_mb:
                    self.consecutive_growth_windows = 0
                    self._last_idle_sample_mb = current_rss_mb
            else:
                self._last_idle_sample_mb = current_rss_mb

            expansion = current_rss_mb / base if base > 0.0 else 1.0
            delta_mb = current_rss_mb - base

            avail_ratio = 1.0
            if isinstance(host_mem, dict):
                raw_ratio = host_mem.get("available_ratio", host_mem.get("avail_ratio", 0.0))
                total_mb = host_mem.get("total_mb", 0.0)
                if total_mb > 0.0 and raw_ratio > 0.0:
                    avail_ratio = float(raw_ratio)

            reason = ""
            if expansion >= 3.5 and delta_mb >= 512.0:
                reason = (
                    f"Severe working-set bloat: RSS={current_rss_mb:.1f}MB "
                    f"(baseline={base:.1f}MB, expansion={expansion:.2f}x, delta=+{delta_mb:.1f}MB)"
                )
            elif avail_ratio < 0.15 and expansion >= 2.2 and delta_mb >= 256.0:
                reason = (
                    f"Host memory pressure ({avail_ratio * 100.0:.1f}% free) with worker bloat: "
                    f"RSS={current_rss_mb:.1f}MB (baseline={base:.1f}MB, expansion={expansion:.2f}x)"
                )
            elif (
                self.consecutive_growth_windows >= self.RATCHET_WINDOWS_REQUIRED
                and expansion >= 2.5
                and delta_mb >= 384.0
            ):
                reason = (
                    f"Sustained monotonic RSS ratcheting ({self.consecutive_growth_windows} windows): "
                    f"RSS={current_rss_mb:.1f}MB (baseline={base:.1f}MB, expansion={expansion:.2f}x)"
                )

            if reason:
                self.recycle_count += 1
                self.last_recycle_reason = reason
                self.last_recycle_time = now
                self.consecutive_growth_windows = 0
                return True, reason

            return False, ""

    def to_status_dict(self, live_rss_mb: float = 0.0) -> Dict[str, Any]:
        """Returns a status snapshot dictionary for `/api/status` and `server status`."""
        if live_rss_mb > 0.0:
            self.record_sample(live_rss_mb, is_idle=False)
        with self._lock:
            eff_base = max(self.baseline_rss_mb, self.MIN_BASELINE_FLOOR_MB) if self.baseline_rss_mb > 0.0 else 0.0
            expansion = (self.current_rss_mb / eff_base) if eff_base > 0.0 else 1.0
            return {
                "current_rss_mb": round(self.current_rss_mb, 1),
                "baseline_rss_mb": round(eff_base, 1),
                "peak_rss_mb": round(self.peak_rss_mb, 1),
                "expansion_ratio": round(expansion, 2),
                "consecutive_growth_windows": self.consecutive_growth_windows,
                "recycle_count": self.recycle_count,
                "last_recycle_reason": self.last_recycle_reason,
            }


@dataclass(frozen=True)
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
        idle_timeout_sec: Optional[float] = None,
        enable_watcher: bool = True,
    ) -> None:
        self.yscb_root = os.path.abspath(yscb_root)
        self._explicit_idle_timeout: Optional[float] = (
            float(idle_timeout_sec) if idle_timeout_sec is not None else None
        )
        self.idle_timeout_sec = (
            self._explicit_idle_timeout
            if self._explicit_idle_timeout is not None
            else DEFAULT_IDLE_TIMEOUT_SEC
        )
        ensure_private_venv(self.yscb_root)
        self.enable_watcher = enable_watcher

        self.token = secrets.token_hex(16)
        self.state_file = os.path.join(self.yscb_root, ".cache", "server", "daemon.json")
        self.lock_file = os.path.join(self.yscb_root, ".cache", "server", "daemon.lock")

        self.logger = RollingFileLogger(self.yscb_root)
        self.watcher: Optional[ModulesWatcher] = None

        self._worker_proc: Optional[subprocess.Popen] = None
        self._worker_lock = threading.Lock()
        self._dispatch_lock = threading.Lock()
        self._services_lock = threading.Lock()
        self._worker_services: List[Dict[str, Any]] = []
        self._active_task_queue: Optional[queue.Queue] = None
        # Two-stage handshake state (per spawned worker)
        self._worker_ready_event = threading.Event()
        self._warming_since: Optional[float] = None
        self._worker_alive_timeout_sec = self._load_worker_alive_timeout()
        # PIDs of workers killed while a dispatch was in flight
        self._preempted_pids: Set[int] = set()
        # Currently executing dispatch task snapshot
        self._current_task: Optional[Dict[str, Any]] = None
        self.memory_monitor = WorkerMemoryHealthMonitor()

        self._start_time = time.time()
        self._last_active_time = self._start_time
        self._activity_lock = threading.Lock()
        self._tasks_executed = 0
        self._is_running = False
        self._is_stopped = False
        self._stop_event = threading.Event()
        self._ttl_thread: Optional[threading.Thread] = None
        self._http_thread: Optional[threading.Thread] = None
        self._restarting = False
        self._pending_worker_reload = False
        self._restart_thread: Optional[threading.Thread] = None
        self._stop_lock = threading.Lock()
        self._httpd: Optional[http.server.HTTPServer] = None
        self._lock: Optional[InterProcessLock] = None
        self.port = 0

    @staticmethod
    def _load_worker_alive_timeout() -> float:
        try:
            return float(ServerConfig.load().worker_alive_timeout_sec)
        except (TypeError, ValueError):
            return DEFAULT_WORKER_ALIVE_TIMEOUT_SEC

    @staticmethod
    def _emit_task_failure(chunk_emitter: Callable[[Dict[str, Any]], None], error_msg: str) -> int:
        """Emits a failing task_finish packet and returns exit code 1."""
        chunk_emitter({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": error_msg})
        return 1

    def is_any_worker_service_busy(self) -> bool:
        """Returns True if any registered background service in `_worker_services` is actively busy."""
        with self._services_lock:
            services_snapshot = list(self._worker_services or [])
        for svc in services_snapshot:
            if not isinstance(svc, dict):
                continue
            if bool(svc.get("busy")):
                return True
            st = str(svc.get("state") or "").strip().upper()
            if st in ("STARTING", "UPDATING"):
                return True
            metrics = svc.get("metrics")
            if isinstance(metrics, dict) and bool(metrics.get("busy")):
                return True
        return False

    def _is_worker_completely_idle(self) -> bool:
        """Returns True iff no foreground dispatch task is running AND no background service is busy."""
        if self._current_task is not None:
            return False
        if self._worker_state() != "ready":
            return False
        if self.is_any_worker_service_busy():
            return False
        return True

    def _update_worker_service_status(self, packet: Dict[str, Any]) -> None:
        """Synchronizes `_worker_services` and optional `worker_rss_mb` from a `service_status` IPC packet."""
        rss_val = packet.get("worker_rss_mb")
        if isinstance(rss_val, (int, float)) and float(rss_val) > 0.0:
            self.memory_monitor.record_sample(float(rss_val), is_idle=False)
        services_list = packet.get("services")
        if isinstance(services_list, list):
            with self._services_lock:
                self._worker_services = list(services_list)
            if any(
                isinstance(s, dict)
                and (
                    bool(s.get("busy"))
                    or str(s.get("state") or "").strip().upper() in ("STARTING", "UPDATING")
                )
                for s in services_list
            ):
                self.touch_activity(source="service_status")
            return
        svc_name = packet.get("name")
        if not isinstance(svc_name, str) or not svc_name:
            return
        svc_state = str(packet.get("state") or "READY")
        svc_alive = bool(packet.get("alive", svc_state != "STOPPED"))
        svc_busy = bool(packet.get("busy", svc_state in ("STARTING", "UPDATING")))
        svc_metrics = packet.get("metrics")
        with self._services_lock:
            updated: List[Dict[str, Any]] = []
            found = False
            for item in self._worker_services or []:
                entry = dict(item)
                if entry.get("name") == svc_name:
                    entry["state"] = svc_state
                    entry["alive"] = svc_alive
                    entry["busy"] = svc_busy
                    if "provider" in packet and packet["provider"]:
                        entry["provider"] = packet["provider"]
                    if "description" in packet and packet["description"] is not None:
                        entry["description"] = packet["description"]
                    if isinstance(svc_metrics, dict):
                        entry["metrics"] = dict(svc_metrics)
                    found = True
                updated.append(entry)
            if not found:
                new_entry: Dict[str, Any] = {
                    "name": svc_name,
                    "provider": str(packet.get("provider") or "unknown"),
                    "description": str(packet.get("description") or ""),
                    "alive": svc_alive,
                    "state": svc_state,
                    "busy": svc_busy,
                }
                if isinstance(svc_metrics, dict):
                    new_entry["metrics"] = dict(svc_metrics)
                updated.append(new_entry)
            self._worker_services = updated
        if svc_busy:
            self.touch_activity(source=svc_name)

    def _handle_worker_control_packet(self, packet: Dict[str, Any]) -> bool:
        """Handles control IPC packets ('touch_activity', 'log', and 'service_status') from the warm worker."""
        pkt_type = packet.get("type")
        if pkt_type == "touch_activity":
            self.touch_activity(source=str(packet.get("source") or "worker"))
            return True
        if pkt_type == "log":
            self.logger.log(
                packet.get("level", "INFO"),
                packet.get("msg", ""),
                component=packet.get("component", "worker"),
            )
            return True
        if pkt_type == "service_status":
            self._update_worker_service_status(packet)
            return True
        return False

    def _handle_worker_packet(self, packet: Dict[str, Any]) -> bool:
        """Alias for `_handle_worker_control_packet` handling background status and activity packets."""
        return self._handle_worker_control_packet(packet)

    def _build_shutdown_summary(self) -> Dict[str, Any]:
        """Builds the graceful shutdown summary dictionary."""
        proc = self._worker_proc
        worker_pid = proc.pid if proc is not None else 0
        uptime = time.time() - self._start_time
        return {
            "pid": os.getpid(),
            "worker_pid": worker_pid,
            "uptime_seconds": uptime,
            "tasks_executed": self._tasks_executed,
            "services_stopped": len(self._worker_services),
            "reason": "Graceful CLI shutdown request",
            "archive_log": self.logger.get_expected_archive_path(),
        }

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
        proc = self._worker_proc
        worker_pid = proc.pid if proc is not None else 0
        now = time.time()
        uptime = now - self._start_time
        with self._activity_lock:
            last_active = self._last_active_time
        idle_left = max(0.0, self.idle_timeout_sec - (now - last_active))
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
        live_worker_rss = get_process_rss_mb(worker_pid) if worker_pid > 0 else 0.0
        with self._services_lock:
            services_snap = list(self._worker_services or [])
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
            "services": services_snap,
            "watcher": watcher_status,
            "current_task": current_task,
            "worker_memory": self.memory_monitor.to_status_dict(live_rss_mb=live_worker_rss),
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
        with self._activity_lock:
            self._last_active_time = time.time()

    def _start_http_and_watcher_services(self) -> None:
        """Binds localhost HTTP server, spawns warm worker, and activates watcher & idle TTL threads."""
        self._httpd = _create_http_server(self)
        self.port = self._httpd.server_address[1]
        self.logger.info(f"HTTP Server listening on 127.0.0.1:{self.port}")

        self._write_state()

        with self._worker_lock:
            try:
                self._spawn_worker_locked()
                self.logger.info(f"Initial Warm Worker spawned (PID: {self._worker_proc.pid if self._worker_proc else 0})")
            except WorkerSpawnError as err:
                # Keep the daemon up; the next dispatch re-attempts spawning
                self.logger.error(f"Initial Warm Worker spawn failed: {err}")
        self._write_state()

        if self.enable_watcher:
            modules_dir = os.path.join(self.yscb_root, ".modules")
            self.watcher = ModulesWatcher(modules_dir, on_change_callback=self.on_modules_changed, debounce_sec=0.5)
            self.watcher.start()
            self.logger.info(f"ModulesWatcher active on {modules_dir}")

        self._stop_event.clear()
        ttl_thread = create_managed_thread(self._idle_ttl_loop, daemon=True, name="idle-ttl")
        self._ttl_thread = ttl_thread
        ttl_thread.start()

    def _run_supervisor_main_loop(self, foreground: bool) -> None:
        """Runs HTTP server either in blocking foreground mode or background daemon thread."""
        if foreground:
            self.logger.echo_console = True
            banner = format_startup_banner(self.get_status_dict())
            log(banner, flush=True)
            try:
                if self._httpd:
                    self._httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                if self._restarting:
                    if self._restart_thread is not None:
                        self._restart_thread.join(timeout=5.0)
                else:
                    self.stop()
        else:
            http_thread = create_managed_thread(self._httpd.serve_forever, daemon=True, name="http-server")
            self._http_thread = http_thread
            http_thread.start()

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

        # Rebind auto-spawn probe record from the launcher PID to this master PID
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
            self._stop_event.set()

            if self.watcher:
                self.watcher.stop()
                self.watcher = None

            # Preempt any in-flight dispatch by killing the worker (no _dispatch_lock)
            with self._worker_lock:
                self._kill_worker_locked(timeout_sec=2.0)

            if self._httpd:
                try:
                    self._httpd.shutdown()
                    self._httpd.server_close()
                except Exception:
                    pass
                self._httpd = None

            curr_th = threading.current_thread()
            for managed_th in (self._ttl_thread, self._http_thread):
                if managed_th is not None and managed_th is not curr_th and managed_th.is_alive():
                    try:
                        managed_th.join(timeout=1.0)
                    except Exception:
                        pass
            self._ttl_thread = None
            self._http_thread = None

            if self._lock:
                try:
                    self._lock.release()
                except Exception:
                    pass
                self._lock = None

            self._cleanup_state()
            # Graceful shutdown marker resets empirical reaping detection
            daemon_probe.mark_clean_exit(self.yscb_root)
            self.logger.archive_and_close()

    def _kill_worker_locked(self, timeout_sec: float = 2.0) -> None:
        """
        Terminates the child worker and closes all pipe handles (caller holds `_worker_lock`).

        Idle worker: two-stage handshake (`{"action": "exit"}` then process-tree termination).
        Busy worker (dispatch in flight): skips the handshake and terminates the process tree
        immediately so the blocked dispatch hits EOF and releases `_dispatch_lock`.
        """
        if not self._worker_proc:
            with self._services_lock:
                self._worker_services = []
            return
        proc = self._worker_proc
        task_q = getattr(proc, "_yscb_task_queue", None)

        has_active_services = self.is_any_worker_service_busy() or bool(self._worker_services)
        handshake_timeout = max(float(timeout_sec), 5.0) if has_active_services else float(timeout_sec)

        exited_gracefully = False
        if self._current_task is not None:
            self._preempted_pids.add(proc.pid)
        elif proc.poll() is None and proc.stdin:
            try:
                proc.stdin.write(b'{"action": "exit"}\n')
                proc.stdin.flush()
                proc.wait(timeout=handshake_timeout)
                exited_gracefully = True
            except (OSError, ValueError, subprocess.TimeoutExpired) as err:
                self.logger.warning(f"Worker (PID: {proc.pid}) graceful exit handshake failed: {err}")

        if not exited_gracefully and proc.poll() is None:
            if not terminate_popen_tree(proc, timeout_sec=timeout_sec):
                self.logger.error(f"Failed to terminate worker process tree (PID: {proc.pid})")

        if proc.stdin:
            try:
                proc.stdin.close()
            except (OSError, ValueError):
                pass
        try:
            setattr(proc, "_yscb_demux_active", False)
        except Exception:
            pass
        if isinstance(task_q, queue.Queue):
            try:
                task_q.put_nowait(None)
            except queue.Full:
                try:
                    task_q.get_nowait()
                except Exception:
                    pass
                try:
                    task_q.put_nowait(None)
                except Exception:
                    pass
            except Exception:
                pass
        curr_th = threading.current_thread()
        io_threads = [
            io_th
            for io_th in (getattr(proc, "_yscb_io_threads", ()) or ())
            if io_th is not None and io_th is not curr_th
        ]
        for io_th in io_threads:
            if io_th.is_alive():
                try:
                    io_th.join(timeout=0.5)
                except Exception:
                    pass
        any_reader_alive = any(io_th.is_alive() for io_th in io_threads)
        # Skip closing read pipes on Windows if a reader thread is still blocked in ReadFile on an inherited grandchild handle.
        if not (sys.platform == "win32" and any_reader_alive):
            for pipe in (proc.stdout, proc.stderr):
                if pipe:
                    try:
                        pipe.close()
                    except (OSError, ValueError):
                        pass
        self._worker_proc = None
        self._active_task_queue = None
        self._warming_since = None
        with self._services_lock:
            self._worker_services = []

    def _sync_config_on_restart(self, cfg: ServerConfig) -> None:
        """Synchronizes worker alive timeout and (unless explicitly overridden via CLI) idle timeout."""
        if self._explicit_idle_timeout is None:
            self.idle_timeout_sec = float(cfg.idle_timeout_sec)
        self._worker_alive_timeout_sec = float(cfg.worker_alive_timeout_sec)

    def restart_worker(
        self,
        *,
        if_idle_only: bool = False,
        touch_activity: bool = True,
    ) -> int:
        """
        Terminates the current worker and spawns a fresh one while syncing ServerConfig.

        When `if_idle_only=True` (used by background RSS auto-recycling), acquires `_dispatch_lock`
        non-blockingly first and aborts if a foreground task or background service is busy.
        When `if_idle_only=False` (explicit reload), kills under `_worker_lock` first to unblock
        any stuck dispatch, then acquires `_dispatch_lock` to spawn.

        Returns:
            int: PID of the fresh worker (or 0 if skipped due to `if_idle_only=True`).

        Raises:
            WorkerSpawnError: if the fresh worker fails the alive handshake.
        """
        if self._is_stopped or self._restarting:
            return 0
        # Load config before any destructive action so a config error never leaves the daemon worker-less
        cfg = ServerConfig.load()

        if if_idle_only:
            if not self._dispatch_lock.acquire(blocking=False):
                return 0
            try:
                if not self._is_worker_completely_idle():
                    return 0
                self._sync_config_on_restart(cfg)
                with self._worker_lock:
                    old_pid = self._worker_proc.pid if self._worker_proc else 0
                    self.logger.info(f"Restarting idle Warm Worker (terminating old PID: {old_pid})...")
                    self._kill_worker_locked(timeout_sec=1.5)
                    try:
                        new_pid = self._spawn_worker_locked()
                    except WorkerSpawnError as err:
                        self.logger.error(f"Warm Worker restart failed: {err}")
                        raise
                    if touch_activity:
                        with self._activity_lock:
                            self._last_active_time = time.time()
                    self._write_state()
                    self.logger.info(f"Fresh Warm Worker spawned (PID: {new_pid})")
                    return new_pid
            finally:
                self._dispatch_lock.release()

        if self._is_stopped or self._restarting:
            return 0
        with self._worker_lock:
            if self._is_stopped or self._restarting:
                return 0
            self._pending_worker_reload = False
            old_pid = self._worker_proc.pid if self._worker_proc else 0
            self.logger.info(f"Restarting Warm Worker (terminating old PID: {old_pid})...")
            self._kill_worker_locked(timeout_sec=1.5)

        self._sync_config_on_restart(cfg)

        with self._dispatch_lock:
            with self._worker_lock:
                if self._is_stopped or self._restarting:
                    return 0
                if self._worker_proc is not None and self._worker_proc.poll() is None:
                    # A queued dispatch already spawned a fresh worker after the kill
                    new_pid = self._worker_proc.pid
                else:
                    try:
                        new_pid = self._spawn_worker_locked()
                    except WorkerSpawnError as err:
                        self.logger.error(f"Warm Worker restart failed: {err}")
                        raise
                if touch_activity:
                    with self._activity_lock:
                        self._last_active_time = time.time()
                if self.watcher is not None and hasattr(self.watcher, "refresh_snapshot"):
                    try:
                        self.watcher.refresh_snapshot()
                    except Exception:
                        pass
                self._write_state()
                self.logger.info(f"Fresh Warm Worker spawned (PID: {new_pid})")
                return new_pid

    def _wait_active_dispatch_drain(self, timeout_sec: float = _WATCHER_DRAIN_TIMEOUT_SEC) -> None:
        """Waits up to `timeout_sec` for an in-flight foreground dispatch to complete before background reload."""
        if self._dispatch_lock.acquire(blocking=True, timeout=max(0.0, float(timeout_sec))):
            self._dispatch_lock.release()

    def on_modules_changed(self, affected_modules: Optional[Set[str]] = None) -> None:
        """
        Dual-channel reload dispatcher:
        - If 'server' or 'core' changed: triggers restart_server()
        - Otherwise: drains any short in-flight foreground dispatch, then triggers restart_worker()
        """
        self.logger.info(f"ModulesWatcher detected change in modules: {affected_modules}")
        if affected_modules and ("server" in affected_modules or "core" in affected_modules):
            self.logger.info(f"[Server] Detected core/server module update ({affected_modules}). Triggering Master self-restart...")
            self.restart_server()
        else:
            if self._is_stopped or self._restarting:
                return
            self.logger.info(f"[Server] Detected domain module update ({affected_modules or 'unknown'}). Reloading Warm Worker...")
            drained = self._dispatch_lock.acquire(blocking=True, timeout=max(0.0, float(_WATCHER_DRAIN_TIMEOUT_SEC)))
            if drained:
                self._dispatch_lock.release()
                if self._is_stopped or self._restarting:
                    return
                try:
                    self.restart_worker()
                except WorkerSpawnError as err:
                    self.logger.error(f"[Server] Warm Worker reload failed; next dispatch will retry spawning: {err}")
            else:
                with self._worker_lock:
                    self._pending_worker_reload = True
                self.logger.info(
                    f"[Server] Foreground dispatch still active after {_WATCHER_DRAIN_TIMEOUT_SEC:.1f}s; deferring Warm Worker reload until task completes."
                )

    def _perform_self_restart(self) -> int:
        """
        Executes the ordered self-restart handover sequence:
        retains `daemon.lock` while stopping watcher, worker, HTTP server, and logger,
        then releases `daemon.lock` immediately prior to spawning the replacement Master.

        Returns:
            int: PID of the newly spawned replacement Master process, or 0 on failure.
        """
        held_lock = self._lock
        self._lock = None
        try:
            self.stop()
        except Exception as err:
            try:
                self.logger.warning(f"[Server] Error stopping daemon during restart: {err}")
            except Exception:
                pass
        finally:
            if held_lock is not None:
                try:
                    held_lock.release()
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

        # Unpublish daemon.json immediately so new CLI callers fall back cleanly while draining in-flight work
        self._cleanup_state()
        self.logger.info("Initiating graceful MasterSupervisor self-restart...")

        def _do_restart() -> None:
            try:
                self._wait_active_dispatch_drain()
                self._perform_self_restart()
            finally:
                os._exit(0)

        t = threading.Thread(target=_do_restart, daemon=True, name="server-self-restart")
        self._restart_thread = t
        t.start()

    def _ensure_ready_worker(self) -> subprocess.Popen:
        """
        Ensures a live (alive-handshaked) worker subprocess exists and returns its Popen handle.

        Raises:
            WorkerSpawnError: if a required respawn fails the alive handshake.
        """
        with self._worker_lock:
            if self._worker_proc is not None and self._worker_proc.poll() is not None:
                self._kill_worker_locked(timeout_sec=0.5)
            if not self._worker_proc:
                self._spawn_worker_locked()
                self._write_state()
            return self._worker_proc  # type: ignore

    def _wait_worker_ready(self, timeout_sec: Optional[float] = None) -> bool:
        """
        Blocks until the current worker reports `worker_ready`.

        Args:
            timeout_sec: Optional upper bound; defaults to `max(30.0, self._worker_alive_timeout_sec * 6.0)`
                so a hung pre-warm hook never permanently deadlocks `_dispatch_lock`.

        Returns:
            bool: True once ready; False if the worker died or the timeout elapsed.
        """
        eff_timeout = (
            float(timeout_sec)
            if timeout_sec is not None
            else max(30.0, float(self._worker_alive_timeout_sec) * 6.0)
        )
        deadline = time.time() + eff_timeout
        while True:
            proc = self._worker_proc
            event = self._worker_ready_event
            if proc is None or proc.poll() is not None:
                return False
            if event.is_set():
                return True
            if time.time() >= deadline:
                return False
            event.wait(0.05)

    def _ensure_worker_demux_queue(self, proc: subprocess.Popen) -> queue.Queue:
        """Ensures `proc` has an active single-owner stdout demuxer queue attached."""
        task_q = getattr(proc, "_yscb_task_queue", None)
        if isinstance(task_q, queue.Queue):
            return task_q
        task_q = queue.Queue(maxsize=512)
        try:
            setattr(proc, "_yscb_task_queue", task_q)
            setattr(proc, "_yscb_demux_active", True)
        except Exception:
            pass
        self._active_task_queue = task_q
        alive_evt = threading.Event()
        alive_evt.set()
        demux_t = create_managed_thread(
            self._read_worker_handshake,
            args=(proc, alive_evt, self._worker_ready_event),
            daemon=True,
            name=f"worker-stdout-demux-{getattr(proc, 'pid', 0)}",
        )
        try:
            existing_io = list(getattr(proc, "_yscb_io_threads", ()) or ())
            existing_io.append(demux_t)
            setattr(proc, "_yscb_io_threads", existing_io)
        except Exception:
            pass
        demux_t.start()
        return task_q

    def _send_worker_cancel(
        self,
        proc: subprocess.Popen,
        target_mod: str,
        task_id: Optional[str] = None,
    ) -> None:
        """Sends a non-destructive cooperative cancel signal over `proc.stdin` when client disconnects."""
        try:
            if proc.poll() is None and proc.stdin is not None:
                cancel_pkt: Dict[str, Any] = {"action": "cancel"}
                if task_id is not None:
                    cancel_pkt["task_id"] = task_id
                proc.stdin.write((json.dumps(cancel_pkt) + "\n").encode("utf-8"))
                proc.stdin.flush()
                self.logger.info(
                    f"Client disconnected during dispatch for module='{target_mod}' (task_id={task_id}); sent cooperative cancel to worker."
                )
        except OSError:
            pass

    def _stream_task_over_worker_pipe(
        self,
        proc: subprocess.Popen,
        target_mod: str,
        req_payload: Dict[str, Any],
        chunk_emitter: Callable[[Dict[str, Any]], None],
        is_client_disconnected: Optional[Callable[[], bool]] = None,
    ) -> int:
        """Writes dispatch payload to worker stdin and relays NDJSON stream chunks via single-owner demux queue."""
        task_q = self._ensure_worker_demux_queue(proc)
        raw_tid = req_payload.get("task_id")
        task_id: Optional[str] = str(raw_tid) if isinstance(raw_tid, str) and raw_tid else None

        try:
            req_line = json.dumps(req_payload) + "\n"
            proc.stdin.write(req_line.encode("utf-8"))  # type: ignore
            proc.stdin.flush()  # type: ignore
        except Exception as e:
            self.logger.error(f"Failed to write task payload to worker stdin: {e}", exc_info=e)
            with self._worker_lock:
                if self._worker_proc is proc:
                    self._kill_worker_locked(timeout_sec=1.0)
            return self._emit_task_failure(chunk_emitter, str(e))

        exit_code = 0
        cancel_sent = False
        cancel_sent_mono: Optional[float] = None
        last_emit_mono = time.monotonic()
        last_worker_packet_mono = last_emit_mono
        import math as _math
        try:
            raw_cg = float(get_env("YSCB_CANCEL_GRACE_SEC", "5.0") or "5.0")
            cancel_grace_sec = max(0.1, raw_cg) if _math.isfinite(raw_cg) else 5.0
        except (TypeError, ValueError):
            cancel_grace_sec = 5.0
        req_env = req_payload.get("env") if isinstance(req_payload, dict) else None
        raw_stall = (
            req_env.get("YSCB_WORKER_STALL_TIMEOUT_SEC")
            if isinstance(req_env, dict) and req_env.get("YSCB_WORKER_STALL_TIMEOUT_SEC") is not None
            else get_env("YSCB_WORKER_STALL_TIMEOUT_SEC", "120.0")
        )
        try:
            parsed_stall = float(raw_stall if raw_stall is not None else "120.0")
            worker_stall_timeout_sec = (
                max(0.2, parsed_stall)
                if _math.isfinite(parsed_stall) and parsed_stall > 0
                else 0.0
            )
        except (TypeError, ValueError):
            worker_stall_timeout_sec = 120.0
        heartbeat_interval_sec = 15.0

        while True:
            try:
                now_top = time.monotonic()
                if (
                    not cancel_sent
                    and is_client_disconnected is not None
                    and is_client_disconnected()
                ):
                    cancel_sent = True
                    cancel_sent_mono = now_top
                    self._send_worker_cancel(proc, target_mod, task_id=task_id)
                if (
                    cancel_sent
                    and cancel_sent_mono is not None
                    and (now_top - cancel_sent_mono) >= cancel_grace_sec
                ):
                    self.logger.warning(
                        f"Task for module='{target_mod}' (task_id={task_id}) did not exit within {cancel_grace_sec:.1f}s after client disconnect; force-recycling worker."
                    )
                    try:
                        setattr(proc, "_yscb_demux_active", False)
                    except Exception:
                        pass
                    with self._worker_lock:
                        if self._worker_proc is proc:
                            self._kill_worker_locked(timeout_sec=1.0)
                            self._pending_worker_reload = True
                    return 130

                try:
                    packet = task_q.get(timeout=0.15)
                except queue.Empty:
                    now_m = time.monotonic()
                    if proc.poll() is not None and task_q.empty():
                        err_text = self._worker_eof_error(proc)
                        with self._worker_lock:
                            if self._worker_proc is proc:
                                self._kill_worker_locked(timeout_sec=0.5)
                        self.logger.error(f"{err_text} during dispatch for module='{target_mod}'")
                        return self._emit_task_failure(chunk_emitter, err_text)
                    # Only real packets from the worker advance last_worker_packet_mono; synthetic heartbeats
                    # do not suppress stall detection when a worker deadlocks silently.
                    if (
                        worker_stall_timeout_sec > 0
                        and not cancel_sent
                        and (now_m - last_worker_packet_mono) >= worker_stall_timeout_sec
                    ):
                        stall_msg = (
                            f"Worker task for module='{target_mod}' (task_id={task_id}) stalled without worker output "
                            f"for {worker_stall_timeout_sec:.1f}s; force-recycling worker."
                        )
                        self.logger.warning(stall_msg)
                        try:
                            setattr(proc, "_yscb_demux_active", False)
                        except Exception:
                            pass
                        with self._worker_lock:
                            if self._worker_proc is proc:
                                self._kill_worker_locked(timeout_sec=1.0)
                                self._pending_worker_reload = True
                        return self._emit_task_failure(chunk_emitter, stall_msg)
                    if not cancel_sent and (now_m - last_emit_mono) >= heartbeat_interval_sec:
                        chunk_emitter({"type": "heartbeat", "ts": time.time()})
                        last_emit_mono = now_m
                    continue

                if packet is None:
                    err_text = self._worker_eof_error(proc)
                    with self._worker_lock:
                        if self._worker_proc is proc:
                            self._kill_worker_locked(timeout_sec=0.5)
                    self.logger.error(f"{err_text} during dispatch for module='{target_mod}'")
                    return self._emit_task_failure(chunk_emitter, err_text)

                last_worker_packet_mono = time.monotonic()
                if not cancel_sent:
                    chunk_emitter(packet)
                    last_emit_mono = last_worker_packet_mono

                if packet.get("type") == "task_finish":
                    if "services" in packet and isinstance(packet["services"], list):
                        with self._services_lock:
                            self._worker_services = list(packet["services"])
                    exit_code = packet.get("exit_code", 0)
                    dur_ms = packet.get("duration_ms", 0.0)
                    stages_str = packet.get("stages")
                    stages_suffix = f" [{stages_str}]" if isinstance(stages_str, str) and stages_str else ""
                    self.logger.info(
                        f"Task dispatch finished: module='{target_mod}', exit_code={exit_code}, duration={dur_ms:.1f}ms{stages_suffix}"
                    )
                    break
                if (
                    not cancel_sent
                    and is_client_disconnected is not None
                    and is_client_disconnected()
                ):
                    cancel_sent = True
                    cancel_sent_mono = time.monotonic()
                    self._send_worker_cancel(proc, target_mod, task_id=task_id)
            except Exception as ex:
                try:
                    setattr(proc, "_yscb_demux_active", False)
                except Exception:
                    pass
                with self._worker_lock:
                    was_preempted = proc.pid in self._preempted_pids
                    if was_preempted:
                        self._preempted_pids.discard(proc.pid)
                    elif self._worker_proc is proc:
                        self._kill_worker_locked(timeout_sec=1.0)
                if was_preempted:
                    # Pipe closed by a preempting restart/stop
                    self.logger.warning(f"Dispatch for module='{target_mod}' preempted: {_PREEMPTED_ERROR}")
                    return self._emit_task_failure(chunk_emitter, _PREEMPTED_ERROR)
                self.logger.error(f"Exception during worker stream reading: {ex}", exc_info=ex)
                return self._emit_task_failure(chunk_emitter, str(ex))

        with self._activity_lock:
            self._last_active_time = time.time()
        return exit_code

    def _worker_eof_error(self, proc: subprocess.Popen) -> str:
        """Classifies a worker stdout EOF as preemption or unexpected closure."""
        with self._worker_lock:
            if proc.pid in self._preempted_pids:
                self._preempted_pids.discard(proc.pid)
                return _PREEMPTED_ERROR
        return "Worker stdout closed unexpectedly"

    def dispatch_task(
        self,
        req_data: Dict[str, Any],
        chunk_emitter: Any,
        *,
        is_client_disconnected: Optional[Callable[[], bool]] = None,
        _reject_if_stopping: bool = False,
    ) -> int:
        """
        Dispatches a CLI task to the warm worker sequentially under `_dispatch_lock`.

        Tracks `current_task` for status reporting, waits for a warming worker to become
        ready, and converts `WorkerSpawnError` into a failing `task_finish`.
        """
        if _reject_if_stopping and (self._restarting or self._is_stopped):
            return _REJECTED_BEFORE_EXECUTION

        with self._activity_lock:
            self._last_active_time = time.time()

        target_mod = req_data.get("module", "unknown")
        cmd_args = req_data.get("args", [])
        self.logger.info(f"Task dispatch requested: module='{target_mod}', args={cmd_args}")

        with self._dispatch_lock:
            if _reject_if_stopping and (self._restarting or self._is_stopped):
                return _REJECTED_BEFORE_EXECUTION
            with self._worker_lock:
                self._tasks_executed += 1
            if is_client_disconnected is not None and is_client_disconnected():
                self.logger.info(
                    f"Skipping queued dispatch for module='{target_mod}' because client already disconnected."
                )
                return 130
            with self._worker_lock:
                self._current_task = {"module": target_mod, "args": list(cmd_args), "started_at": time.time()}
            try:
                try:
                    proc = self._ensure_ready_worker()
                except WorkerSpawnError as err:
                    self.logger.error(f"Task dispatch aborted: {err}")
                    return self._emit_task_failure(chunk_emitter, str(err))
                if not self._wait_worker_ready():
                    err_text = self._worker_eof_error(proc)
                    if err_text != _PREEMPTED_ERROR:
                        if proc.poll() is None:
                            err_text = "Worker pre-warm timed out before becoming ready"
                            with self._worker_lock:
                                if self._worker_proc is proc:
                                    self._kill_worker_locked(timeout_sec=1.0)
                        else:
                            err_text = "Worker exited before becoming ready"
                    self.logger.error(f"Task dispatch aborted for module='{target_mod}': {err_text}")
                    return self._emit_task_failure(chunk_emitter, err_text)
                task_id = str(req_data.get("task_id") or secrets.token_hex(8))
                req_payload = {
                    "action": "dispatch",
                    "task_id": task_id,
                    "module": req_data["module"],
                    "args": cmd_args,
                    "cwd": req_data.get("cwd", self.yscb_root),
                    "env": req_data.get("env"),
                }
                return self._stream_task_over_worker_pipe(
                    proc,
                    target_mod,
                    req_payload,
                    chunk_emitter,
                    is_client_disconnected=is_client_disconnected,
                )
            finally:
                with self._worker_lock:
                    self._current_task = None
                    # Dispatch is serialized; stale preemption markers never outlive their task
                    self._preempted_pids.clear()
                    should_reload_after = bool(
                        self._pending_worker_reload and not self._is_stopped and not self._restarting
                    )
                    if should_reload_after:
                        self._pending_worker_reload = False
                        try:
                            self._kill_worker_locked(timeout_sec=1.5)
                        except Exception:
                            pass
                        can_respawn = (
                            self._is_running or os.path.isdir(os.path.join(self.yscb_root, ".modules", "core"))
                        ) and not self._is_stopped and not self._restarting
                        if can_respawn:
                            try:
                                new_pid = self._spawn_worker_locked()
                                if self.watcher is not None and hasattr(self.watcher, "refresh_snapshot"):
                                    try:
                                        self.watcher.refresh_snapshot()
                                    except Exception:
                                        pass
                                if self._is_running or os.path.exists(self.state_file):
                                    self._write_state()
                                self.logger.info(f"Fresh Warm Worker respawned after recycle/reload (PID: {new_pid})")
                            except Exception as respawn_err:
                                if self._is_running or os.path.exists(self.state_file):
                                    try:
                                        self._write_state()
                                    except Exception:
                                        pass
                                self.logger.warning(f"Deferred Warm Worker respawn skipped/failed: {respawn_err}")
                        elif self._is_running or os.path.exists(self.state_file):
                            try:
                                self._write_state()
                            except Exception:
                                pass

    def _drain_worker_stderr(self, pipe: Any, pid: int) -> None:
        """Drains worker stderr stream in a background thread and logs non-empty lines."""
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

    def _read_worker_handshake(
        self,
        proc: subprocess.Popen,
        alive_event: threading.Event,
        ready_event: threading.Event,
    ) -> None:
        """
        Single-owner stdout reader loop for the warm worker subprocess.

        Processes two-stage handshake packets ('worker_alive' -> 'worker_ready'),
        continuously drains background control packets ('log', 'service_status', 'touch_activity')
        even while the worker is idle, and routes foreground task packets to `proc._yscb_task_queue`.
        """
        task_q: Optional[queue.Queue] = getattr(proc, "_yscb_task_queue", None)
        dup_ready_count = 0
        try:
            while True:
                line = proc.stdout.readline()  # type: ignore
                if not line:
                    break
                if isinstance(line, bytes):
                    line_str = line.decode("utf-8", errors="replace").strip()
                else:
                    line_str = str(line).strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                except ValueError:
                    continue
                if not isinstance(data, dict):
                    continue
                if self._handle_worker_control_packet(data):
                    continue
                pkt_type = data.get("type")
                if pkt_type == "worker_alive":
                    alive_event.set()
                    continue
                if pkt_type == "worker_ready":
                    if ready_event.is_set():
                        dup_ready_count += 1
                        if dup_ready_count >= 3:
                            break
                        continue
                    if "services" in data and isinstance(data["services"], list):
                        with self._services_lock:
                            self._worker_services = list(data["services"])
                    ready_rss = float(data.get("worker_rss_mb") or 0.0)
                    if ready_rss <= 0.0 and proc.pid > 0:
                        ready_rss = get_process_rss_mb(proc.pid)
                    self.memory_monitor.reset_for_new_worker(initial_rss_mb=ready_rss)
                    alive_event.set()
                    ready_event.set()
                    if self._worker_proc is proc:
                        self._warming_since = None
                    self.logger.info(f"Warm Worker (PID: {proc.pid}) ready (RSS: {ready_rss:.1f} MB)")
                    continue
                if isinstance(task_q, queue.Queue):
                    while getattr(proc, "_yscb_demux_active", True) and not self._is_stopped:
                        try:
                            task_q.put(data, timeout=0.2)
                            break
                        except queue.Full:
                            if proc.poll() is not None and self._current_task is None:
                                break
                            continue
        except (OSError, ValueError) as err:
            if not ready_event.is_set():
                self.logger.warning(f"Warm Worker (PID: {proc.pid}) handshake reader stopped: {err}")
        finally:
            try:
                setattr(proc, "_yscb_demux_active", False)
            except Exception:
                pass
            if getattr(proc, "stdout", None) is not None:
                try:
                    proc.stdout.close()  # type: ignore[union-attr]
                except Exception:
                    pass
            if isinstance(task_q, queue.Queue):
                try:
                    task_q.put_nowait(None)
                except queue.Full:
                    try:
                        task_q.get_nowait()
                    except Exception:
                        pass
                    try:
                        task_q.put_nowait(None)
                    except Exception:
                        pass
                except Exception:
                    pass

    def _spawn_worker_locked(self) -> int:
        """
        Spawns a warm worker (caller holds `_worker_lock`) using a two-stage handshake.

        Waits up to `worker_alive_timeout_sec` for `worker_alive`; afterwards the worker is in
        state `warming` and the single-owner stdout demuxer thread waits for `worker_ready`
        and continues draining background/foreground packets for the lifetime of the worker.

        Returns:
            int: PID of the alive worker.

        Raises:
            WorkerSpawnError: if the worker exits or stays silent before `worker_alive`.
        """
        worker_script = os.path.join(os.path.dirname(__file__), "worker.py")
        cmd = [sys.executable, worker_script, "--yscb-root", self.yscb_root]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["YSCB_IN_SERVER_WORKER"] = "1"

        env["PYTHONPATH"] = build_runtime_pythonpath(
            yscb_root=self.yscb_root,
            priority_module="server",
            include_host_roots=True,
            existing_pythonpath=env.get("PYTHONPATH", ""),
        )

        popen_kwargs: Dict[str, Any] = {"close_fds": True}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        else:
            popen_kwargs["start_new_session"] = True

        ready_event = threading.Event()
        alive_event = threading.Event()
        if self._is_stopped:
            raise WorkerSpawnError("MasterSupervisor is stopped; refusing to spawn worker")
        task_q: queue.Queue = queue.Queue(maxsize=512)
        self._worker_ready_event = ready_event
        self._active_task_queue = task_q
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
        try:
            setattr(proc, "_yscb_task_queue", task_q)
            setattr(proc, "_yscb_demux_active", True)
        except Exception:
            pass
        self._worker_proc = proc

        stderr_t = create_managed_thread(
            self._drain_worker_stderr,
            args=(proc.stderr, proc.pid),
            daemon=True,
            name=f"worker-stderr-{proc.pid}",
        )
        t = create_managed_thread(
            self._read_worker_handshake,
            args=(proc, alive_event, ready_event),
            daemon=True,
            name=f"worker-stdout-demux-{proc.pid}",
        )
        try:
            setattr(proc, "_yscb_io_threads", [stderr_t, t])
        except Exception:
            pass
        stderr_t.start()
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
        with self._activity_lock:
            self._last_active_time = time.time()
            return max(0.0, self.idle_timeout_sec)

    def touch(self, source: str = "probe") -> float:
        """Alias for `touch_activity` refreshing supervisor activity timestamp."""
        return self.touch_activity(source=source)

    def _evaluate_worker_memory_health(self) -> None:
        """Evaluates worker memory health during idle windows and triggers seamless auto-recycle if needed."""
        proc = self._worker_proc
        if proc is None or proc.poll() is not None:
            return
        if self.is_any_worker_service_busy():
            return
        is_idle = self._is_worker_completely_idle()
        rss_mb = get_process_rss_mb(proc.pid)
        if rss_mb <= 0.0:
            return
        host_mem = get_host_memory_info() if is_idle else None
        should_recycle, reason = self.memory_monitor.evaluate(
            current_rss_mb=rss_mb,
            host_mem=host_mem,
            is_idle=is_idle,
        )
        if should_recycle:
            self.logger.warning(
                f"[MemoryHealthMonitor] Auto-recycling idle Warm Worker (PID: {proc.pid}): {reason}"
            )
            try:
                self.restart_worker(if_idle_only=True, touch_activity=False)
            except Exception as err:
                self.logger.error(f"[MemoryHealthMonitor] Failed to auto-recycle worker: {err}")

    def _idle_ttl_loop(self) -> None:
        while self._is_running:
            if self._stop_event.wait(2.0) or not self._is_running:
                break
            proc = self._worker_proc
            if proc is not None and proc.poll() is not None:
                with self._worker_lock:
                    if self._worker_proc is proc:
                        self._kill_worker_locked(timeout_sec=0.5)
                        try:
                            self._write_state()
                        except Exception:
                            pass
            worker_actively_busy = (
                self._current_task is not None
                or (
                    self._worker_proc is not None
                    and self._worker_proc.poll() is None
                    and (not self._worker_ready_event.is_set() or self.is_any_worker_service_busy())
                )
            )
            if worker_actively_busy:
                self.touch_activity(source="busy_guard")
                continue
            with self._activity_lock:
                last_active = self._last_active_time
            idle_seconds = time.time() - last_active
            if self.idle_timeout_sec > 0 and idle_seconds >= self.idle_timeout_sec:
                self.logger.info(f"Idle TTL ({self.idle_timeout_sec}s) reached. Initiating automatic shutdown...")
                create_managed_thread(self.stop, daemon=True, name='idle-ttl-stop').start()
                break
            if idle_seconds >= 2.0:
                self._evaluate_worker_memory_health()

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
        Removes daemon.json only. daemon.lock is intentionally kept: deleting it would let
        a concurrent starter lock a fresh inode while another holds the unlinked one; liveness is
        always decided by lock ownership.
        """
        try:
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
        except OSError as err:
            self.logger.warning(f"Failed to remove daemon state file {self.state_file}: {err}")


def _normalize_root_path(path_str: str) -> str:
    """Normalizes a workspace or engine root path across symlinks, junctions, and case-insensitive filesystems."""
    return os.path.normcase(os.path.realpath(os.path.abspath(path_str)))


def _is_client_socket_closed(sock: Any) -> bool:
    """Non-blockingly probes whether the HTTP client socket has sent TCP FIN or RST across Linux/macOS/Windows."""
    if sock is None:
        return False
    try:
        fileno_fn = getattr(sock, "fileno", None)
        if not callable(fileno_fn):
            return False
        fd = fileno_fn()
        if not isinstance(fd, int) or fd < 0:
            return True

        if hasattr(select, "poll"):
            poller = select.poll()
            poll_mask = (
                getattr(select, "POLLIN", 1)
                | getattr(select, "POLLHUP", 16)
                | getattr(select, "POLLERR", 8)
                | getattr(select, "POLLNVAL", 32)
            )
            poller.register(fd, poll_mask)
            events = poller.poll(0)
            if not events:
                return False
            _, revents = events[0]
            if revents & getattr(select, "POLLNVAL", 32):
                return True
            if (revents & (getattr(select, "POLLHUP", 16) | getattr(select, "POLLERR", 8))) and not (
                revents & getattr(select, "POLLIN", 1)
            ):
                return True
        else:
            readable, _, _ = select.select([sock], [], [], 0.0)
            if not readable:
                return False

        dontwait = getattr(socket, "MSG_DONTWAIT", 0)
        if dontwait:
            peeked = sock.recv(1, socket.MSG_PEEK | dontwait)
            return peeked == b""

        gettimeout_fn = getattr(sock, "gettimeout", None)
        settimeout_fn = getattr(sock, "settimeout", None)
        prev_timeout = gettimeout_fn() if callable(gettimeout_fn) else None
        if callable(settimeout_fn):
            settimeout_fn(0.0)
        try:
            peeked = sock.recv(1, socket.MSG_PEEK)
            return peeked == b""
        finally:
            if callable(settimeout_fn):
                try:
                    settimeout_fn(prev_timeout)
                except OSError:
                    pass
    except BlockingIOError:
        return False
    except OSError as err:
        if getattr(err, "errno", None) in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR) or getattr(
            err, "winerror", None
        ) == 10035:
            return False
        return True
    except Exception:
        return False


class _NonBlockingThreadingHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


def _create_http_server(supervisor: MasterSupervisor) -> http.server.HTTPServer:
    class DispatcherHTTPHandler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        timeout = 10.0

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send_json_response(self, status_code: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

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
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                supervisor.logger.warning(f"HTTP GET {parsed.path} -> 404 Not Found")

        def _reject_bad_dispatch(self, error_msg: str, log_msg: Optional[str] = None) -> None:
            self._send_json_response(400, {"error": error_msg})
            if log_msg:
                supervisor.logger.warning(log_msg)

        def _parse_dispatch_request(self) -> Optional[Dict[str, Any]]:
            try:
                content_len = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                self._reject_bad_dispatch("Invalid Content-Length", "HTTP POST /api/dispatch -> 400 Invalid Content-Length")
                return None
            if content_len < 0:
                self._reject_bad_dispatch("Invalid Content-Length", "HTTP POST /api/dispatch -> 400 Negative Content-Length")
                return None

            raw_body = self.rfile.read(content_len).decode("utf-8", errors="replace") if content_len > 0 else ""
            try:
                req_data = json.loads(raw_body)
            except ValueError:
                self._reject_bad_dispatch("Invalid JSON", "HTTP POST /api/dispatch -> 400 Invalid JSON")
                return None

            if not isinstance(req_data, dict):
                self._reject_bad_dispatch(
                    "Invalid dispatch payload: expected JSON object",
                    "HTTP POST /api/dispatch -> 400 Payload Not Object",
                )
                return None

            mod_val = req_data.get("module")
            if not isinstance(mod_val, str) or not mod_val.strip():
                self._reject_bad_dispatch(
                    "Missing or invalid 'module' field",
                    "HTTP POST /api/dispatch -> 400 Invalid Module Field",
                )
                return None

            args_val = req_data.get("args", [])
            if not isinstance(args_val, list):
                self._reject_bad_dispatch(
                    "Invalid 'args' field: expected list",
                    "HTTP POST /api/dispatch -> 400 Invalid Args Field",
                )
                return None

            req_root = req_data.get("yscb_root")
            if req_root:
                if not isinstance(req_root, str):
                    self._reject_bad_dispatch("Invalid 'yscb_root' field")
                    return None
                req_norm = _normalize_root_path(req_root)
                sup_norm = _normalize_root_path(supervisor.yscb_root)
                parent_norm = _normalize_root_path(os.path.dirname(supervisor.yscb_root))
                if req_norm != sup_norm and req_norm != parent_norm:
                    self._reject_bad_dispatch(
                        "Workspace Root Mismatch",
                        f"HTTP POST /api/dispatch -> 400 Workspace Root Mismatch ({req_root})",
                    )
                    return None

            return req_data

        def _handle_post_dispatch(self, t0: float) -> None:
            req_data = self._parse_dispatch_request()
            if req_data is None:
                return

            if supervisor._restarting or supervisor._is_stopped:
                self._send_json_response(503, {"error": "Server restarting or stopping"})
                supervisor.logger.info("HTTP POST /api/dispatch -> 503 (Server restarting or stopping)")
                return

            disconnect_event = threading.Event()
            headers_sent = False

            def _ensure_stream_headers() -> bool:
                nonlocal headers_sent
                if headers_sent:
                    return True
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    headers_sent = True
                    return True
                except OSError:
                    disconnect_event.set()
                    return False

            def chunk_emitter(packet: Dict[str, Any]) -> None:
                if disconnect_event.is_set():
                    return
                if not _ensure_stream_headers():
                    return
                chunk_bytes = (json.dumps(packet) + "\n").encode("utf-8")
                chunk_header = f"{len(chunk_bytes):X}\r\n".encode("utf-8")
                try:
                    self.wfile.write(chunk_header + chunk_bytes + b"\r\n")
                    self.wfile.flush()
                except OSError:
                    disconnect_event.set()

            def _check_disconnected() -> bool:
                if disconnect_event.is_set():
                    return True
                if _is_client_socket_closed(getattr(self, "connection", None)):
                    disconnect_event.set()
                    return True
                return False

            rc = supervisor.dispatch_task(
                req_data,
                chunk_emitter,
                is_client_disconnected=_check_disconnected,
                _reject_if_stopping=True,
            )
            if rc == _REJECTED_BEFORE_EXECUTION and not headers_sent:
                self._send_json_response(503, {"error": "Server restarting or stopping"})
                supervisor.logger.info("HTTP POST /api/dispatch -> 503 (Rejected before execution during restart)")
                return

            self.close_connection = True
            if not disconnect_event.is_set() and _ensure_stream_headers():
                try:
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except OSError:
                    disconnect_event.set()
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
                summary = supervisor._build_shutdown_summary()
                self._send_json_response(200, {"status": "shutting_down", "summary": summary})
                dur_ms = (time.time() - t0) * 1000.0
                supervisor.logger.info(
                    f"HTTP POST /api/shutdown -> 200 ({dur_ms:.1f}ms, Uptime: {summary['uptime_seconds']:.1f}s)"
                )
                create_managed_thread(supervisor.stop, daemon=True, name="http-shutdown").start()
            else:
                self.send_response(404)
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                supervisor.logger.warning(f"HTTP POST {parsed.path} -> 404 Not Found")

    return _NonBlockingThreadingHTTPServer(("127.0.0.1", 0), DispatcherHTTPHandler)
