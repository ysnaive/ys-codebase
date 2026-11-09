"""
Server Module - Warm Worker Process.

Persistent worker subprocess that pre-warms Python runtime, broadcasts
warm-up events via core.events, executes tasks sequentially with debounced
stream interception and RuntimeScope isolation (`bind_runtime_context`),
intercepts SystemExit, and implements lazy module loading.
"""

import argparse
from dataclasses import dataclass
import json
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from core import events, uri
from core.context import (
    bind_cell_context,
    bind_runtime_context,
    get_env,
    get_runtime_context,
    get_virtual_cwd,
)
from core.guard import GUARD_ENV_HOST, GUARD_ENV_TOKEN
from core.log import (
    DebouncedIOStreamer,
    bind_log_context,
    clear_error_hint,
    get_last_error_hint,
)
from core.platform import (
    ensure_installed_modules_path,
    ensure_private_venv,
    get_process_rss_mb,
    set_process_title,
    trim_process_memory,
)
from server.service import ServiceManager


@dataclass(frozen=True)
class _WorkerIPCLinkSink:
    """
    Lightweight background log sink adapter that forwards background `core.log` lines
    from `ServiceWorker` threads as structured `{"type": "log", ...}` IPC packets to `MasterSupervisor`.
    """

    emit_packet_fn: Callable[[Dict[str, Any]], None]

    def log(self, level: str, msg: Any, component: str = "service") -> None:
        self.emit_packet_fn({
            "type": "log",
            "level": str(level or "INFO").upper(),
            "component": str(component or "service"),
            "msg": str(msg),
        })


def _reconfigure_utf8_stream(stream_obj: Any) -> None:
    """Reconfigures a text stream to UTF-8 with replacement error handling when supported."""
    reconf = getattr(stream_obj, "reconfigure", None)
    if callable(reconf):
        try:
            reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _resolve_host_dir(yscb_root: str) -> str:
    """Resolves the active host workspace root directory without mutating os.environ."""
    host_dir = get_env(GUARD_ENV_HOST)
    if not host_dir or not os.path.isdir(host_dir):
        cand = os.path.dirname(yscb_root)
        host_dir = cand if os.path.isfile(os.path.join(cand, "yscb.config.json")) else yscb_root
    return host_dir


class WarmWorker:
    """
    Persistent warm worker executing inside an isolated subprocess.
    Enforces Three-Plane Separation (`MasterSupervisor` / `WarmWorker` / `ServiceWorker`)
    and routes task `virtual_cwd` and `env` overrides through `core.context.bind_runtime_context`
    with zero `os.chdir()` or `os.environ` global mutations.
    """

    def __init__(self, yscb_root: str, emit_packet_fn: Any) -> None:
        self.yscb_root = os.path.abspath(yscb_root)
        self.host_dir = _resolve_host_dir(self.yscb_root)
        uri.set_yscb_root(self.yscb_root)
        uri.set_host_dir(self.host_dir)
        ensure_private_venv(self.yscb_root)
        self.emit_packet_fn = emit_packet_fn
        self._ipc_log_sink = _WorkerIPCLinkSink(emit_packet_fn=emit_packet_fn)
        self.service_manager = ServiceManager()
        self._task_lock = threading.RLock()

    def _emit_log(self, level: str, msg: str) -> None:
        """Emits a structured worker log packet to the master supervisor."""
        self.emit_packet_fn({
            "type": "log",
            "level": level,
            "component": "worker",
            "msg": msg,
        })

    def _record_task_exception(
        self,
        ex: Exception,
        module: str,
        args: List[str],
        streamer: DebouncedIOStreamer,
        stop_capture: bool = False,
    ) -> Tuple[int, str]:
        """Formats an unhandled task exception, writes to captured stderr, optionally stops capture, and logs error."""
        err_text = f"{type(ex).__name__}: {str(ex)}"
        streamer.write("stderr", f"[Server Worker Error] {err_text}\n")
        if stop_capture:
            streamer.stop_capture()
        self._emit_log("ERROR", f"Task execution failed for module='{module}', args={args}: {err_text}")
        return 1, err_text

    def pre_warm(self) -> None:
        """Emits warming events and pre-warms core runtime under isolated background log context."""
        start_t = time.time()
        pid = os.getpid()

        ensure_installed_modules_path(
            yscb_root=self.yscb_root,
            priority_module="server",
            include_host_roots=True,
        )

        with bind_runtime_context(
            virtual_cwd=self.yscb_root,
            env={
                "YSCB_ROOT_DIR": self.yscb_root,
                GUARD_ENV_HOST: self.host_dir,
                "YSCB_IN_SERVER_WORKER": "1",
            },
            host_dir=self.host_dir,
            yscb_dir=self.yscb_root,
            module_name="server",
        ), bind_log_context(
            background_sink=self._ipc_log_sink,  # type: ignore[arg-type]
            component="worker",
            isolated_error_scope=True,
        ):
            try:
                self.service_manager.load_from_contributes(self.yscb_root)
            except Exception as e:
                self._emit_log("WARNING", f"Failed to load background services contributes: {e}")

            try:
                events.broadcast(
                    "server_worker_warming",
                    {"worker_pid": pid, "start_time": start_t},
                    emit_module="server",
                )
            except Exception:
                pass

            try:
                self.service_manager.start_all({
                    "yscb_root": self.yscb_root,
                    "workspace_root": self.host_dir,
                    "log_sink": self._ipc_log_sink,
                })
            except Exception as e:
                self._emit_log("WARNING", f"Failed to initialize background services: {e}")

            duration_ms = (time.time() - start_t) * 1000.0
            try:
                events.broadcast(
                    "server_worker_ready",
                    {"worker_pid": pid, "duration_ms": duration_ms},
                    emit_module="server",
                )
            except Exception:
                pass
            if not self.service_manager.is_any_busy():
                try:
                    trim_process_memory()
                except Exception:
                    pass

        self._emit_log("INFO", f"Warm worker pre_warm completed in {duration_ms:.1f}ms (PID: {pid})")

    def _build_task_env_overrides(self, env: Optional[Dict[str, str]]) -> Tuple[str, Dict[str, Optional[str]]]:
        """Builds request-scoped environment overrides for `bind_runtime_context` without mutating `os.environ`."""
        merged_env: Dict[str, Optional[str]] = {}
        if env:
            for k, v in env.items():
                merged_env[str(k)] = str(v) if v is not None else None

        host_dir = merged_env.get(GUARD_ENV_HOST) or get_env(GUARD_ENV_HOST) or self.host_dir
        if not host_dir or not os.path.isdir(host_dir):
            host_dir = self.host_dir
        merged_env["YSCB_ROOT_DIR"] = self.yscb_root
        merged_env[GUARD_ENV_HOST] = host_dir
        merged_env["YSCB_IN_SERVER_WORKER"] = "1"
        merged_env[GUARD_ENV_TOKEN] = (
            merged_env.get(GUARD_ENV_TOKEN)
            or get_env(GUARD_ENV_TOKEN)
            or "yscb_auth_dispatch"
        )
        return host_dir, merged_env

    def _dispatch_command_with_captured_streams(
        self,
        module: str,
        args: List[str],
        streamer: DebouncedIOStreamer,
    ) -> Tuple[int, Optional[str]]:
        """Resolves command path, dispatches local CLI under captured IO streams, and contains SystemExit."""
        clear_error_hint()
        with streamer:
            try:
                from core.commands.dispatcher import (
                    _load_registry,
                    dispatch_local,
                )
                registry = _load_registry(self.yscb_root)
                cmd_path, cmd_spec, sub_args = registry.resolve_command_path(module, args)
                if not cmd_path:
                    cmd_name = args[0] if args else "help"
                    sub_args = args[1:] if len(args) > 1 else []
                    cmd_spec = registry.get_command(module, cmd_name)
                else:
                    cmd_name = cmd_path

                rc = dispatch_local(
                    module_name=module,
                    cmd_name=cmd_name,
                    raw_args=sub_args,
                    cmd_spec=cmd_spec,
                    yscb_abs=self.yscb_root,
                )
                err_hint = (get_last_error_hint() or f"Command exited with code {rc}") if rc != 0 else None
                return rc, err_hint
            except SystemExit as se:
                code = se.code if isinstance(se.code, int) else (1 if se.code else 0)
                err_hint = (get_last_error_hint() or f"Command exited with code {code}") if code != 0 else None
                return code, err_hint
            except Exception as ex:
                return self._record_task_exception(ex, module, args, streamer, stop_capture=False)

    def execute_task(
        self,
        module: str,
        args: List[str],
        cwd: str,
        env: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Executes target module command with lazy loading, `bind_runtime_context` isolation,
        `DebouncedIOStreamer` capture, and `SystemExit` containment.
        """
        with self._task_lock:
            start_time = time.time()
            eff_cwd = cwd if (cwd and os.path.isdir(cwd)) else get_virtual_cwd(fallback=self.yscb_root)
            if not eff_cwd:
                eff_cwd = self.yscb_root
            host_dir, task_env = self._build_task_env_overrides(env)

            streamer = DebouncedIOStreamer(emit_chunk=self.emit_packet_fn, debounce_ms=500)
            exit_code = 1
            err_text: Optional[str] = None
            stages_summary: Optional[str] = None

            try:
                get_runtime_context().set_module_state("server.worker.foreground_active", True)
                with bind_runtime_context(
                    virtual_cwd=eff_cwd,
                    env=task_env,
                    host_dir=host_dir,
                    yscb_dir=self.yscb_root,
                    module_name=module,
                ), bind_cell_context(
                    module_name=module,
                    command=str(args[0]) if args else "default",
                    reuse_existing=False,
                ) as cell:
                    try:
                        exit_code, err_text = self._dispatch_command_with_captured_streams(module, args, streamer)
                    finally:
                        stages_summary = cell.format_stages_summary() or None
            except Exception as ex:
                exit_code, err_text = self._record_task_exception(ex, module, args, streamer, stop_capture=True)
            finally:
                try:
                    get_runtime_context().set_module_state("server.worker.foreground_active", False)
                except Exception:
                    pass
                duration_ms = (time.time() - start_time) * 1000.0
                if not self.service_manager.is_any_busy():
                    try:
                        trim_process_memory()
                    except Exception:
                        pass
                try:
                    self.emit_packet_fn({
                        "type": "service_status",
                        "services": self.service_manager.get_status(),
                        "worker_rss_mb": get_process_rss_mb(),
                    })
                except Exception:
                    pass
                streamer.send_task_finish(
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    error=err_text,
                    stages=stages_summary,
                )

            return exit_code


def worker_main(yscb_root: str, in_stream: Any = None, out_stream: Any = None) -> None:
    """Entry point for warm worker subprocess loop reading from stdin and writing to stdout."""
    try:
        set_process_title("yscb server: worker")
    except Exception:
        pass

    orig_stdout = sys.stdout
    if out_stream is None:
        for stream_obj in (orig_stdout, sys.stderr):
            _reconfigure_utf8_stream(stream_obj)
    if in_stream is None:
        _reconfigure_utf8_stream(sys.stdin)

    ipc_out = out_stream or orig_stdout
    in_io = in_stream or sys.stdin

    ipc_lock = threading.Lock()

    def emit_fn(packet: Dict[str, Any]) -> None:
        with ipc_lock:
            try:
                line = json.dumps(packet) + "\n"
                ipc_out.write(line)
                ipc_out.flush()
            except OSError:
                pass

    worker: Optional[WarmWorker] = None
    try:
        # 兩段式握手第一段，啟動即宣告存活（pre_warm 可能耗時，由 worker_ready 宣告就緒）
        emit_fn({"type": "worker_alive", "worker_pid": os.getpid()})
        worker = WarmWorker(yscb_root=yscb_root, emit_packet_fn=emit_fn)

        with bind_runtime_context(
            virtual_cwd=worker.yscb_root,
            env={
                "YSCB_ROOT_DIR": worker.yscb_root,
                GUARD_ENV_HOST: worker.host_dir,
                "YSCB_IN_SERVER_WORKER": "1",
            },
            host_dir=worker.host_dir,
            yscb_dir=worker.yscb_root,
            module_name="server",
        ), bind_log_context(
            background_sink=worker._ipc_log_sink,  # type: ignore[arg-type]
            component="worker",
            isolated_error_scope=True,
        ):
            worker.pre_warm()

            emit_fn({
                "type": "worker_ready",
                "worker_pid": os.getpid(),
                "services": worker.service_manager.get_status(),
                "worker_rss_mb": get_process_rss_mb(),
            })

            while True:
                try:
                    line = in_io.readline()
                    if not line:
                        break

                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="replace")
                    line = line.strip()
                    if not line:
                        continue

                    req = json.loads(line)
                    cmd = req.get("action")
                    if cmd == "exit":
                        break

                    if cmd == "dispatch":
                        worker.execute_task(
                            module=req["module"],
                            args=req.get("args", []),
                            cwd=req.get("cwd", yscb_root),
                            env=req.get("env"),
                        )

                except (KeyboardInterrupt, BrokenPipeError):
                    break
                except Exception as err:
                    emit_fn({"type": "task_finish", "exit_code": 1, "duration_ms": 0.0, "error": str(err)})
    finally:
        if worker is not None:
            try:
                with bind_runtime_context(
                    virtual_cwd=worker.yscb_root,
                    env={
                        "YSCB_ROOT_DIR": worker.yscb_root,
                        GUARD_ENV_HOST: worker.host_dir,
                    },
                    host_dir=worker.host_dir,
                    yscb_dir=worker.yscb_root,
                    module_name="server",
                ), bind_log_context(
                    background_sink=worker._ipc_log_sink,  # type: ignore[arg-type]
                    component="worker",
                    isolated_error_scope=True,
                ):
                    worker.service_manager.stop_all()
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YS-Codebase Server Warm Worker")
    parser.add_argument("--yscb-root", default=".", help="YS-Codebase root path")
    parsed_args = parser.parse_args()

    worker_main(yscb_root=parsed_args.yscb_root)
