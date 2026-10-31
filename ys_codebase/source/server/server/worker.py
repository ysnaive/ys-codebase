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
from typing import Any, Dict, List, Optional

from core import events
from core.guard import GUARD_ENV_HOST, GUARD_ENV_TOKEN
from core.platform import ensure_private_venv
from server.service import ServiceManager
from server.streamer import DebouncedIOStreamer


class WarmWorker:
    """
    Persistent warm worker executing inside an isolated subprocess.
    """

    def __init__(self, yscb_root: str, emit_packet_fn: Any) -> None:
        self.yscb_root = os.path.abspath(yscb_root)
        ensure_private_venv(self.yscb_root)
        self.emit_packet_fn = emit_packet_fn
        self.service_manager = ServiceManager()

    def pre_warm(self) -> None:
        """Emits warming events and pre-warms core runtime."""
        start_t = time.time()
        pid = os.getpid()

        modules_dir = os.path.join(self.yscb_root, ".modules")
        if modules_dir not in sys.path:
            sys.path.insert(0, modules_dir)

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
    ) -> int:
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

                return dispatch_local(
                    module_name=module,
                    cmd_name=cmd_name,
                    raw_args=sub_args,
                    cmd_spec=cmd_spec,
                    yscb_abs=self.yscb_root,
                )
            except SystemExit as se:
                return se.code if isinstance(se.code, int) else (1 if se.code else 0)

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
        start_time = time.time()
        orig_cwd = os.getcwd()
        orig_env = dict(os.environ)

        streamer = DebouncedIOStreamer(emit_chunk=self.emit_packet_fn, debounce_ms=500)
        exit_code = 1

        try:
            self._prepare_execution_env(cwd, env)
            exit_code = self._dispatch_command_with_captured_streams(module, args, streamer)
        except Exception as ex:
            streamer.write("stderr", f"[Server Worker Error] {type(ex).__name__}: {str(ex)}\n")
            self.emit_packet_fn({
                "type": "log",
                "level": "ERROR",
                "component": "worker",
                "msg": f"Task execution failed for module='{module}', args={args}: {type(ex).__name__}: {str(ex)}",
            })
            exit_code = 1
        finally:
            try:
                os.chdir(orig_cwd)
            except OSError:
                pass
            os.environ.clear()
            os.environ.update(orig_env)

            duration_ms = (time.time() - start_time) * 1000.0
            streamer.send_task_finish(exit_code=exit_code, duration_ms=duration_ms)

        return exit_code


def worker_main(yscb_root: str, in_stream: Any = None, out_stream: Any = None) -> None:
    """Entry point for warm worker subprocess loop reading from stdin and writing to stdout."""
    try:
        from core.platform import set_process_title
        set_process_title("yscb server: worker")
    except Exception:
        pass

    orig_stdout = sys.stdout
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
