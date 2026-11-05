"""
Server Module - Warm Worker Process.

Persistent worker subprocess that pre-warms Python runtime, broadcasts
warm-up events via core.events, executes tasks sequentially with debounced
stream interception, intercepts SystemExit, and implements lazy module loading.
"""

import argparse
import json
import os
import sys
import threading
import time
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Tuple

from core import events, uri
from core.guard import GUARD_ENV_HOST, GUARD_ENV_TOKEN
from core.platform import ensure_private_venv
from server.service import ServiceManager
from server.streamer import DebouncedIOStreamer


def _restore_env_diff(orig_env: Dict[str, str]) -> None:
    """
    Restores os.environ to match orig_env via incremental key diff without calling os.environ.clear(),
    ensuring concurrent daemon threads never observe an empty environment.
    """
    for k in list(os.environ.keys()):
        if k not in orig_env:
            os.environ.pop(k, None)
    for k, v in orig_env.items():
        if os.environ.get(k) != v:
            os.environ[k] = v


class WarmWorker:
    """
    Persistent warm worker executing inside an isolated subprocess.
    """

    def __init__(self, yscb_root: str, emit_packet_fn: Any) -> None:
        self.yscb_root = os.path.abspath(yscb_root)
        ensure_private_venv(self.yscb_root)
        self.emit_packet_fn = emit_packet_fn
        self.service_manager = ServiceManager()
        self._task_lock = threading.RLock()

    def pre_warm(self) -> None:
        """Emits warming events and pre-warms core runtime."""
        start_t = time.time()
        pid = os.getpid()

        from core.platform import ensure_installed_modules_path

        ensure_installed_modules_path(
            yscb_root=self.yscb_root,
            priority_module="server",
            include_host_roots=True,
        )

        try:
            self.service_manager.load_from_contributes(self.yscb_root)
        except Exception as e:
            self.emit_packet_fn({
                "type": "log",
                "level": "WARNING",
                "component": "worker",
                "msg": f"Failed to load background services contributes: {e}",
            })

        try:
            events.broadcast("server_worker_warming", {"worker_pid": pid, "start_time": start_t}, emit_module="server")
        except Exception:
            pass

        try:
            self.service_manager.start_all({"yscb_root": self.yscb_root})
        except Exception as e:
            self.emit_packet_fn({
                "type": "log",
                "level": "WARNING",
                "component": "worker",
                "msg": f"Failed to initialize background services: {e}",
            })

        duration_ms = (time.time() - start_t) * 1000.0
        try:
            events.broadcast("server_worker_ready", {"worker_pid": pid, "duration_ms": duration_ms}, emit_module="server")
        except Exception:
            pass

        self.emit_packet_fn({
            "type": "log",
            "level": "INFO",
            "component": "worker",
            "msg": f"Warm worker pre_warm completed in {duration_ms:.1f}ms (PID: {pid})",
        })

    def _prepare_execution_env(self, cwd: str, env: Optional[Dict[str, str]]) -> None:
        """Applies working directory, environment overrides, and security guard tokens."""
        if cwd and os.path.isdir(cwd):
            os.chdir(cwd)

        if env:
            os.environ.update(env)

        host_dir = os.environ.get(GUARD_ENV_HOST)
        if not host_dir or not os.path.isdir(host_dir):
            cand = os.path.dirname(self.yscb_root)
            host_dir = cand if os.path.isfile(os.path.join(cand, "yscb.config.json")) else self.yscb_root
        os.environ[GUARD_ENV_HOST] = host_dir
        os.environ[GUARD_ENV_TOKEN] = os.environ.get(GUARD_ENV_TOKEN, "yscb_auth_dispatch")

    def _dispatch_command_with_captured_streams(
        self,
        module: str,
        args: List[str],
        streamer: DebouncedIOStreamer,
    ) -> Tuple[int, Optional[str]]:
        """Resolves command path, dispatches local CLI under captured IO streams, and contains SystemExit."""
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
                return rc, None
            except SystemExit as se:
                code = se.code if isinstance(se.code, int) else (1 if se.code else 0)
                return code, None
            except Exception as ex:
                err_text = f"{type(ex).__name__}: {str(ex)}"
                streamer.write("stderr", f"[Server Worker Error] {err_text}\n")
                self.emit_packet_fn({
                    "type": "log",
                    "level": "ERROR",
                    "component": "worker",
                    "msg": f"Task execution failed for module='{module}', args={args}: {err_text}",
                })
                return 1, err_text

    def execute_task(
        self,
        module: str,
        args: List[str],
        cwd: str,
        env: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Executes target module command with lazy loading, stream capture, and SystemExit containment.
        """
        with self._task_lock:
            start_time = time.time()
            orig_cwd = os.getcwd()
            orig_env = dict(os.environ)

            streamer = DebouncedIOStreamer(emit_chunk=self.emit_packet_fn, debounce_ms=500)
            exit_code = 1
            err_text: Optional[str] = None

            try:
                self._prepare_execution_env(cwd, env)
                host_env = os.environ.get(GUARD_ENV_HOST)
                host_ctx = uri.host_scope(host_env) if (host_env and os.path.isdir(host_env)) else nullcontext()
                with host_ctx:
                    exit_code, err_text = self._dispatch_command_with_captured_streams(module, args, streamer)
            except Exception as ex:
                err_text = f"{type(ex).__name__}: {str(ex)}"
                streamer.write("stderr", f"[Server Worker Error] {err_text}\n")
                streamer.stop_capture()
                self.emit_packet_fn({
                    "type": "log",
                    "level": "ERROR",
                    "component": "worker",
                    "msg": f"Task execution failed for module='{module}', args={args}: {err_text}",
                })
                exit_code = 1
            finally:
                try:
                    os.chdir(orig_cwd)
                except OSError:
                    pass
                _restore_env_diff(orig_env)

                duration_ms = (time.time() - start_time) * 1000.0
                streamer.send_task_finish(exit_code=exit_code, duration_ms=duration_ms, error=err_text)

            return exit_code


def worker_main(yscb_root: str, in_stream: Any = None, out_stream: Any = None) -> None:
    """Entry point for warm worker subprocess loop reading from stdin and writing to stdout."""
    try:
        from core.platform import set_process_title
        set_process_title("yscb server: worker")
    except Exception:
        pass

    orig_stdout = sys.stdout
    if out_stream is None:
        for stream_obj in (orig_stdout, sys.stderr):
            reconf = getattr(stream_obj, "reconfigure", None)
            if callable(reconf):
                try:
                    reconf(encoding="utf-8", errors="replace")
                except Exception:
                    pass
    if in_stream is None:
        reconf_in = getattr(sys.stdin, "reconfigure", None)
        if callable(reconf_in):
            try:
                reconf_in(encoding="utf-8", errors="replace")
            except Exception:
                pass

    ipc_out = out_stream or orig_stdout
    in_io = in_stream or sys.stdin

    sys.stdout = sys.stderr

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
        # FR-09: 兩段式握手第一段，啟動即宣告存活（pre_warm 可能耗時，由 worker_ready 宣告就緒）
        emit_fn({"type": "worker_alive", "worker_pid": os.getpid()})
        worker = WarmWorker(yscb_root=yscb_root, emit_packet_fn=emit_fn)
        worker.pre_warm()

        emit_fn({
            "type": "worker_ready",
            "worker_pid": os.getpid(),
            "services": worker.service_manager.get_status(),
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
                worker.service_manager.stop_all()
            except Exception:
                pass
        sys.stdout = orig_stdout


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YS-Codebase Server Warm Worker")
    parser.add_argument("--yscb-root", default=".", help="YS-Codebase root path")
    parsed_args = parser.parse_args()

    worker_main(yscb_root=parsed_args.yscb_root)
