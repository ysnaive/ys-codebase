"""
Legacy daemon compatibility and server probe utility for module:knowledge-db.

In sub_04 architecture refactor, the dedicated HotReloadServer is deprecated and replaced
by KnowledgeDBServiceWorker (hosted by module:server).
This file provides compatibility aliases and server probe helpers.
"""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("knowledge_db.daemon")

_SERVER_JIT_NOTIFIED: bool = False

DEFAULT_VCS_IGNORED_DIRS: Set[str] = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".cache",
    ".modules",
}


from dataclasses import asdict, dataclass, field


@dataclass
class DaemonInfo:
    """Compatibility daemon state descriptor."""
    pid: int
    version: str = "1.0.2.6"
    workspace_root: str = ""
    start_time: float = 0.0
    started_at: float = 0.0
    running: bool = True
    spaces: List[str] = field(default_factory=list)
    spaces_signature: str = ""
    current_spaces: List[str] = field(default_factory=list)
    current_spaces_signature: str = ""
    log_file: Optional[str] = None
    status: Optional[str] = None

    def __post_init__(self):
        if not self.started_at and self.start_time:
            self.started_at = self.start_time
        elif not self.start_time and self.started_at:
            self.start_time = self.started_at

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)



def check_and_notify_hot_reload_server(
    workspace_root: Optional[Union[str, Path]] = None,
) -> Tuple[bool, Optional[DaemonInfo]]:
    """
    Probes whether a server daemon is running in the background.
    If running, notifies stderr once to skip slow JIT checks.
    :return: (is_running, DaemonInfo)
    """
    global _SERVER_JIT_NOTIFIED
    try:
        from server.master import MasterSupervisor
        from core.platform.process import is_process_alive

        root_path = str(workspace_root) if workspace_root else None
        state = MasterSupervisor.read_state(yscb_root=root_path)
        if state and state.pid and is_process_alive(state.pid):
            info = DaemonInfo(
                pid=state.pid,
                version=getattr(state, "version", "1.0.0"),
                workspace_root=getattr(state, "yscb_root", str(workspace_root or "")),
                started_at=getattr(state, "started_at", 0.0),
                running=True,
                log_file=getattr(state, "log_file", None),
            )
            if not _SERVER_JIT_NOTIFIED:
                print(f"Server daemon(pid:{state.pid}) exist, skip JIT check.", file=sys.stderr, flush=True)
                _SERVER_JIT_NOTIFIED = True
            return True, info
    except Exception:
        pass
    return False, None


class HotReloadServer:
    """
    Deprecated compatibility facade.
    Directs users to 'python yscb.py server' and delegates background tasks
    to KnowledgeDBServiceWorker.
    """

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        pipeline: Optional[Any] = None,
        space_manager: Optional[Any] = None,
        config: Optional[Any] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        from .service import KnowledgeDBServiceWorker
        self._worker = KnowledgeDBServiceWorker(self.workspace_root)
        if pipeline:
            self._worker._pipeline = pipeline
        if space_manager:
            self._worker._space_manager = space_manager
        self.pipeline = pipeline
        self.space_manager = space_manager
        self.config = config
        self.version = "1.0.2.6"
        self.file_logger = None
        self._debounce_lock = self._worker._debounce_lock

    @property
    def _debounce_timer(self):
        return self._worker._debounce_timer

    @_debounce_timer.setter
    def _debounce_timer(self, val):
        self._worker._debounce_timer = val

    @property
    def _pending_dirty_paths(self):
        return self._worker._pending_dirty_paths

    @classmethod
    def get_cache_dir(cls, workspace_root: Optional[Union[str, Path]] = None) -> Path:
        root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        d = root / ".cache" / "knowledge-db"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @classmethod
    def get_pid_file(cls, workspace_root: Optional[Union[str, Path]] = None) -> Path:
        return cls.get_cache_dir(workspace_root) / "daemon.pid"

    @classmethod
    def get_lock_file(cls, workspace_root: Optional[Union[str, Path]] = None) -> Path:
        return cls.get_cache_dir(workspace_root) / "daemon.lock"

    @classmethod
    def get_logs_dir(cls, workspace_root: Optional[Union[str, Path]] = None) -> Path:
        d = cls.get_cache_dir(workspace_root) / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @classmethod
    def get_module_version(cls) -> str:
        return "1.0.2.6"

    @classmethod
    def rotate_logs(cls, logs_dir: Path, keep: int = 3) -> None:
        pass

    @classmethod
    def write_pid_info(cls, workspace_root: Optional[Union[str, Path]], info: DaemonInfo) -> None:
        pid_file = cls.get_pid_file(workspace_root)
        import json
        pid_file.write_text(json.dumps(info.__dict__))

    @classmethod
    def is_pid_alive(cls, pid: int) -> bool:
        from core.platform.process import is_process_alive
        return is_process_alive(pid)

    @classmethod
    def kill_process_tree(cls, pid: int) -> None:
        from core.platform.process import kill_process_tree
        kill_process_tree(pid)

    @classmethod
    def get_current_spaces_signature(cls, workspace_root: Optional[Union[str, Path]] = None, space_manager: Optional[Any] = None) -> Tuple[List[str], str]:
        if space_manager:
            try:
                spaces = [sp.name for sp in space_manager.get_union_spaces()]
                return spaces, "sig"
            except Exception:
                pass
        return [], "sig"

    def _setup_logger(self, is_foreground: bool = False) -> None:
        pass

    def _write_pid_file(self) -> None:
        pid_file = self.get_pid_file(self.workspace_root)
        pid_file.write_text(str(os.getpid()))

    def is_path_watched(self, path: Union[str, Path]) -> bool:
        return self._worker.is_path_watched(path)

    def on_file_changed(self, file_path: str) -> None:
        self._worker.on_file_changed(file_path)

    def _execute_debounced_patch(self) -> None:
        self._worker._execute_debounced_patch()

    @classmethod
    def is_running(cls, workspace_root: Optional[Union[str, Path]] = None) -> Tuple[bool, Optional[DaemonInfo]]:
        pid_file = cls.get_pid_file(workspace_root)
        if pid_file.is_file():
            try:
                import json
                data = json.loads(pid_file.read_text())
                if isinstance(data, dict) and "pid" in data:
                    from core.platform.process import is_process_alive
                    if is_process_alive(int(data["pid"])):
                        valid_keys = {"pid", "version", "workspace_root", "start_time", "started_at", "running", "spaces", "spaces_signature", "current_spaces", "current_spaces_signature", "log_file", "status"}
                        clean_data = {k: v for k, v in data.items() if k in valid_keys}
                        return True, DaemonInfo(**clean_data)
            except Exception:
                pass
        return check_and_notify_hot_reload_server(workspace_root)

    @classmethod
    def status(cls, workspace_root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        is_run, info = cls.is_running(workspace_root)
        return {
            "running": is_run,
            "pid": info.pid if info else None,
            "version": info.version if info else None,
            "workspace_root": str(workspace_root or Path.cwd()),
            "current_module_version": "1.0.2.6",
        }

    @classmethod
    def get_daemon_executable(cls, workspace_root: Optional[Union[str, Path]] = None) -> str:
        bin_dir = cls.get_cache_dir(workspace_root) / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        exe_name = "yscb-knowledge-db-daemon.exe" if sys.platform == "win32" else "yscb-knowledge-db-daemon"
        target_exe = bin_dir / exe_name
        try:
            if target_exe.is_file():
                if target_exe.stat().st_mtime >= Path(sys.executable).stat().st_mtime:
                    return str(target_exe)
                try:
                    target_exe.unlink(missing_ok=True)
                except OSError:
                    return str(target_exe)
            if sys.platform == "win32":
                try:
                    os.link(sys.executable, target_exe)
                    return str(target_exe)
                except OSError:
                    pass
            else:
                try:
                    os.symlink(sys.executable, target_exe)
                    return str(target_exe)
                except OSError:
                    pass
            import shutil
            shutil.copy2(sys.executable, target_exe)
            return str(target_exe)
        except Exception as e:
            logger.debug(f"Failed creating custom daemon executable: {e}")
            return sys.executable

    @classmethod
    def set_process_title(cls, title: str = "yscb: knowledge-db daemon") -> None:
        try:
            from core.platform.process import set_process_title
            set_process_title(title)
        except Exception:
            try:
                import setproctitle
                setproctitle.setproctitle(title)
            except Exception:
                pass

    @classmethod
    def stop(cls, workspace_root: Optional[Union[str, Path]] = None) -> bool:
        pid_file = cls.get_pid_file(workspace_root)
        running, info = cls.is_running(workspace_root)
        if not running or info is None:
            if pid_file.is_file():
                try:
                    pid_file.unlink()
                except OSError:
                    pass
            try:
                from server.master import MasterSupervisor
                srv = MasterSupervisor(yscb_root=str(workspace_root) if workspace_root else None)
                return srv.stop()
            except Exception:
                pass
            return True

        target_pid = info.pid
        cls.kill_process_tree(target_pid)
        import time
        for _ in range(20):
            time.sleep(0.1)
            if not cls.is_pid_alive(target_pid):
                break
        else:
            cls.kill_process_tree(target_pid)

        if pid_file.is_file():
            try:
                pid_file.unlink()
            except OSError:
                pass
        try:
            from server.master import MasterSupervisor
            srv = MasterSupervisor(yscb_root=str(workspace_root) if workspace_root else None)
            srv.stop()
        except Exception:
            pass
        return True

    @classmethod
    def ensure_running(cls, workspace_root: Optional[Union[str, Path]] = None, **kwargs) -> bool:
        try:
            from server.master import MasterSupervisor
            srv = MasterSupervisor(yscb_root=str(workspace_root) if workspace_root else None)
            pid = srv.start(foreground=False)
            return pid > 0
        except Exception:
            return False
