"""
Server Module - Warm Worker Process.

Persistent worker subprocess that pre-warms Python runtime, broadcasts
warm-up events via core.events, executes tasks sequentially with debounced
stream interception, intercepts SystemExit, and implements lazy module loading.
"""

import argparse
import importlib
import importlib.util
import json
import os
import platform
import sys
import time
from typing import Any, Dict, List, Optional


# Bootstrap python path to include source and core
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_server_dir = os.path.dirname(_cur_dir)
_source_dir = os.path.dirname(_server_dir)
for _p in [_server_dir, _source_dir, os.path.join(_source_dir, "core")]:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from core import events
from core.guard import GUARD_ENV_HOST, GUARD_ENV_TOKEN
from core.platform import ensure_private_venv
from server.streamer import DebouncedIOStreamer



class WarmWorker:
    """
    Persistent warm worker executing inside an isolated subprocess.
    """

    def __init__(self, yscb_root: str, emit_packet_fn: Any) -> None:
        self.yscb_root = os.path.abspath(yscb_root)
        ensure_private_venv(self.yscb_root)
        self.emit_packet_fn = emit_packet_fn
        self._is_running = True
        self._module_cache: Dict[str, Any] = {}

    def pre_warm(self) -> None:
        """Emits warming events and pre-warms core runtime."""
        start_t = time.time()
        pid = os.getpid()

        try:
            events.broadcast("server_worker_warming", {"worker_pid": pid, "start_time": start_t}, emit_module="server")
            events.broadcast("worker_warming", {"worker_pid": pid, "start_time": start_t}, emit_module="server")
        except Exception:
            pass

        # Pre-warm Python environment paths
        modules_dir = os.path.join(self.yscb_root, ".modules")
        if modules_dir not in sys.path:
            sys.path.insert(0, modules_dir)

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


    def execute_task(
        self,
        module: str,
        args: List[str],
        cwd: str,
        env: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Executes target module process(args) with lazy loading and SystemExit containment.
        """
        start_time = time.time()
        orig_cwd = os.getcwd()
        orig_env = dict(os.environ)

        streamer = DebouncedIOStreamer(emit_chunk=self.emit_packet_fn, debounce_ms=500)

        try:
            if cwd and os.path.isdir(cwd):
                os.chdir(cwd)

            if env:
                os.environ.update(env)

            # Security guard injection
            host_dir = os.environ.get(GUARD_ENV_HOST)
            if not host_dir or not os.path.isdir(host_dir):
                cand = os.path.dirname(self.yscb_root)
                host_dir = cand if os.path.isfile(os.path.join(cand, "yscb.config.json")) else self.yscb_root
            os.environ[GUARD_ENV_HOST] = host_dir
            os.environ[GUARD_ENV_TOKEN] = os.environ.get(GUARD_ENV_TOKEN, "yscb_auth_dispatch")

            cmd_name = args[0] if args else "help"
            sub_args = args[1:] if len(args) > 1 else []

            with streamer:
                try:
                    from core.commands.dispatcher import _load_registry, dispatch_local, _find_module_cli, _MODULE_CACHE
                    registry = _load_registry(self.yscb_root)
                    cmd_spec = registry.get_command(module, cmd_name)
                    target_cli = _find_module_cli(module, self.yscb_root)
                    exit_code = dispatch_local(
                        module_name=module,
                        cmd_name=cmd_name,
                        raw_args=sub_args,
                        cmd_spec=cmd_spec,
                        yscb_abs=self.yscb_root,
                    )
                    if target_cli and target_cli in _MODULE_CACHE:
                        self._module_cache[module] = _MODULE_CACHE[target_cli]
                except SystemExit as se:
                    exit_code = se.code if isinstance(se.code, int) else (1 if se.code else 0)

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
            except Exception:
                pass
            os.environ.clear()
            os.environ.update(orig_env)

            duration_ms = (time.time() - start_time) * 1000.0
            streamer.send_task_finish(exit_code=exit_code, duration_ms=duration_ms)

        return exit_code


def worker_main(yscb_root: str, in_stream=None, out_stream=None) -> None:
    """Entry point for warm worker subprocess loop reading from stdin and writing to stdout."""
    in_io = in_stream or sys.stdin
    out_io = out_stream or sys.stdout

    def emit_fn(packet: Dict[str, Any]) -> None:
        try:
            line = json.dumps(packet) + "\n"
            out_io.write(line)
            out_io.flush()
        except Exception:
            pass

    worker = WarmWorker(yscb_root=yscb_root, emit_packet_fn=emit_fn)
    worker.pre_warm()

    # Notify master that worker is ready
    emit_fn({"type": "worker_ready", "worker_pid": os.getpid()})

    while True:
        try:
            line = in_io.readline()
            if not line:
                break

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YS-Codebase Server Warm Worker")
    parser.add_argument("--yscb-root", default=".", help="YS-Codebase root path")
    parsed_args = parser.parse_args()

    worker_main(yscb_root=parsed_args.yscb_root)
