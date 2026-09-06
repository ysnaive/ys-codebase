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


def _ensure_venv(yscb_root: str) -> None:
    tag, sys_name = f"py{sys.version_info.major}{sys.version_info.minor}", platform.system()
    sub = os.path.join(".venv", tag, "Lib", "site-packages") if sys_name == "Windows" else os.path.join(".venv", tag, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
    site_pkg = os.path.join(yscb_root, sub)
    if os.path.isdir(site_pkg) and site_pkg not in sys.path:
        sys.path.insert(0, site_pkg)


# Bootstrap python path to include source and core
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_server_dir = os.path.dirname(_cur_dir)
_source_dir = os.path.dirname(_server_dir)
for _p in [_server_dir, _source_dir, os.path.join(_source_dir, "core")]:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from core import events
from core.guard import GUARD_ENV_HOST, GUARD_ENV_TOKEN
from server.streamer import DebouncedIOStreamer



class WarmWorker:
    """
    Persistent warm worker executing inside an isolated subprocess.
    """

    def __init__(self, yscb_root: str, emit_packet_fn: Any) -> None:
        self.yscb_root = os.path.abspath(yscb_root)
        _ensure_venv(self.yscb_root)
        self.emit_packet_fn = emit_packet_fn
        self._is_running = True

    def pre_warm(self) -> None:
        """Emits warming events and pre-warms core runtime."""
        start_t = time.time()
        pid = os.getpid()

        try:
            events.broadcast("server_worker_warming", {"worker_pid": pid, "start_time": start_t}, emit_module="server")
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

            # Lazy load target module entry point via robust spec loader
            target_cli = os.path.join(self.yscb_root, ".modules", module, "scripts", "cli.py")
            if not os.path.isfile(target_cli):
                target_cli = os.path.join(self.yscb_root, "source", module, "scripts", "cli.py")
            if not os.path.isfile(target_cli):
                raise ModuleNotFoundError(f"CLI script not found for module '{module}' at '{target_cli}'")

            mod_root = os.path.dirname(os.path.dirname(os.path.abspath(target_cli)))
            if mod_root not in sys.path:
                sys.path.insert(0, mod_root)
            core_dir = os.path.join(self.yscb_root, ".modules", "core")
            if os.path.isdir(core_dir) and core_dir not in sys.path:
                sys.path.insert(0, core_dir)

            spec = importlib.util.spec_from_file_location(f"yscb_mod_{module.replace('-', '_')}_cli", target_cli)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load spec from {target_cli}")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)

            fn = getattr(mod, "process", getattr(mod, "main", None))
            if not callable(fn):
                streamer.write("stderr", f"Error: Module '{module}' does not export 'process(args)'\n")
                exit_code = 1
            else:
                orig_argv = list(sys.argv)
                sys.argv = [target_cli] + args
                with streamer:
                    try:
                        ret = fn(args)
                        exit_code = int(ret) if ret is not None else 0
                    except SystemExit as se:
                        # Intercept SystemExit to keep worker alive!
                        exit_code = se.code if isinstance(se.code, int) else (1 if se.code else 0)
                    finally:
                        sys.argv = orig_argv

        except Exception as ex:
            streamer.write("stderr", f"[Server Worker Error] {type(ex).__name__}: {str(ex)}\n")
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
