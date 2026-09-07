"""
Knowledge-DB Service Worker - Background Indexing & Watchdog Watcher.

Implements BaseServiceWorker for module:knowledge-db.
Monitors workspace source directories with 500ms debounce, performs incremental
hot patches across AST, BM25, Call Graph, and FastEmbed Vector indices,
and atomically updates binary snapshots on disk via core.vfs and core.platform.
"""

import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Set, Union

try:
    from server.service import BaseServiceWorker
except ImportError:
    # Dev / sandbox fallback: resolve peer source/server directory
    import sys
    from pathlib import Path
    _src_parent = Path(__file__).resolve().parent.parent.parent
    _cand_server = _src_parent / "server"
    if _cand_server.is_dir() and str(_cand_server) not in sys.path:
        sys.path.insert(0, str(_cand_server))
    try:
        from server.service import BaseServiceWorker
    except ImportError:
        from abc import ABC, abstractmethod

        class BaseServiceWorker(ABC):
            """Fallback BaseServiceWorker when server module is not yet installed."""
            @property
            @abstractmethod
            def name(self) -> str:
                pass

            @abstractmethod
            def start(self, context: Dict[str, Any]) -> None:
                pass

            @abstractmethod
            def stop(self) -> None:
                pass

            @abstractmethod
            def health_check(self) -> bool:
                pass


logger = logging.getLogger("knowledge_db.service")

DEFAULT_VCS_IGNORED_DIRS: Set[str] = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".cache",
    ".modules",
}


def resolve_watch_extensions(space_manager: Optional[Any] = None) -> Set[str]:
    """Dynamically collects watchable file extensions from registered languages and spaces."""
    exts: Set[str] = {".json"}
    try:
        from .parsers.registry import ParserRegistry
        reg = ParserRegistry()
        if hasattr(reg, "get_supported_extensions"):
            exts.update(reg.get_supported_extensions())
    except Exception:
        pass

    if space_manager is not None:
        try:
            spaces = space_manager.get_union_spaces()
            for sp in spaces:
                for pat in getattr(sp, "file_patterns", []):
                    if pat.startswith("*."):
                        exts.add(pat[1:].lower())
        except Exception:
            pass

    return exts


class KnowledgeDBServiceWorker(BaseServiceWorker):
    """
    Background file watcher and incremental index hot-patcher for knowledge-db.
    Managed by server MasterSupervisor, strictly following server idle TTL and shutdown.
    """

    def __init__(self, workspace_root: Optional[Union[str, Path]] = None) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self._observer = None
        self._is_running = False
        self._debounce_timer: Optional[threading.Timer] = None
        self._debounce_lock = threading.Lock()
        self._pending_dirty_paths: Set[str] = set()
        self._pipeline = None
        self._space_manager = None
        self._supported_extensions: Optional[Set[str]] = None

    @property
    def name(self) -> str:
        return "knowledge-db-watcher"

    def _get_space_manager(self) -> Any:
        if self._space_manager is None:
            from .space import SpaceManager
            self._space_manager = SpaceManager()
        return self._space_manager

    def _get_pipeline(self) -> Any:
        if self._pipeline is None:
            from .engine import KnowledgeEngine
            engine = KnowledgeEngine()
            self._pipeline = engine.pipeline
        return self._pipeline

    def _get_supported_extensions(self) -> Set[str]:
        if self._supported_extensions is None:
            self._supported_extensions = resolve_watch_extensions(self._get_space_manager())
        return self._supported_extensions

    def is_path_watched(self, file_path: Union[str, Path]) -> bool:
        """Determines if a given path is an eligible file for incremental indexing."""
        p = Path(file_path)
        for part in p.parts:
            if part in DEFAULT_VCS_IGNORED_DIRS:
                return False

        if p.suffix.lower() not in self._get_supported_extensions():
            return False

        sm = self._get_space_manager()
        if sm is None:
            return True

        try:
            spaces = sm.get_union_spaces()
            if not spaces:
                return True

            abs_p = p.resolve()
            abs_p_str = str(abs_p).replace("\\", "/")

            for sp in spaces:
                roots = sm.resolve_space_include(sp.name)
                for root in roots:
                    root_res = Path(root).resolve()
                    root_str = str(root_res).replace("\\", "/")
                    if abs_p_str == root_str or abs_p_str.startswith(root_str + "/"):
                        return True
        except Exception:
            return True

        if self.workspace_root:
            ws_root_str = str(self.workspace_root.resolve()).replace("\\", "/")
            if abs_p_str == ws_root_str or abs_p_str.startswith(ws_root_str + "/"):
                return True

        return False

    def on_file_changed(self, file_path: str) -> None:
        """Handles incoming file events, filters irrelevant paths, debounces with 500ms timer."""
        if not self._is_running:
            return

        p = Path(file_path)
        if not self.is_path_watched(p):
            return

        with self._debounce_lock:
            self._pending_dirty_paths.add(str(p.resolve()))
            try:
                indices_dir = self._get_pipeline().get_indices_dir()
                (indices_dir / ".watcher_dirty").touch(exist_ok=True)
            except Exception:
                pass
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()

            self._debounce_timer = threading.Timer(0.5, self._execute_debounced_patch)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _execute_debounced_patch(self) -> None:
        """Executes debounced incremental indexing hot-patch on the pipeline."""
        with self._debounce_lock:
            dirty = list(self._pending_dirty_paths)
            self._pending_dirty_paths.clear()
            self._debounce_timer = None

        try:
            indices_dir = self._get_pipeline().get_indices_dir()
            dirty_flag = indices_dir / ".watcher_dirty"
            if dirty_flag.exists():
                try:
                    dirty_flag.unlink()
                except OSError:
                    pass
        except Exception:
            pass

        if not dirty or not self._is_running:
            return

        try:
            pipeline = self._get_pipeline()
            indices_dir = pipeline.get_indices_dir()
            meta_file = indices_dir / "unified.meta.bin"

            _, scanned_count, reason, full_files_map, diff_detail = pipeline.scanner.check_invalidation(
                snapshot_path=meta_file
            )

            if diff_detail.has_changes:
                res = None
                try:
                    res = pipeline.hot_patch_unified_index(diff_detail, full_files_map, timeout_seconds=float("inf"))
                except Exception as pe:
                    logger.warning(f"Hot patch exception: {pe}, fallback to full rebuild.")

                patched = bool(res[0]) if isinstance(res, (tuple, list)) and len(res) > 0 else bool(res)
                if not patched:
                    try:
                        pipeline.build_unified_index(force=True, current_files=full_files_map)
                    except Exception as fe:
                        logger.error(f"Fallback full rebuild failed: {fe}", exc_info=True)
        except Exception as e:
            logger.error(f"Error during debounced hot patch: {e}", exc_info=True)

    def start(self, context: Dict[str, Any]) -> None:
        """Starts background file watcher using watchdog Observer."""
        if self._is_running:
            return

        root = context.get("yscb_root") or context.get("workspace_root")
        if root:
            self.workspace_root = Path(root).resolve()
        elif not self.workspace_root:
            self.workspace_root = Path.cwd().resolve()

        self._is_running = True
        try:
            indices_dir = self._get_pipeline().get_indices_dir()
            active_file = indices_dir / ".watcher_active"
            import json
            with open(active_file, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "time": time.time()}, f)
        except Exception:
            pass

        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
            from watchdog.observers.polling import PollingObserver

            service_ref = self

            class Handler(FileSystemEventHandler):
                def on_any_event(self, event):
                    if getattr(event, "is_directory", False):
                        return
                    src = getattr(event, "src_path", None)
                    if src:
                        service_ref.on_file_changed(src)
                    dst = getattr(event, "dest_path", None)
                    if dst:
                        service_ref.on_file_changed(dst)

            use_polling = os.getenv("KNOWLEDGE_DB_FORCE_POLLING", "0").lower() in ("1", "true", "yes")
            self._observer = PollingObserver() if use_polling else Observer()
            handler = Handler()

            sm = self._get_space_manager()
            watch_dirs = set()
            try:
                for sp in sm.get_union_spaces():
                    for inc in sm.resolve_space_include(sp.name):
                        p = Path(inc).resolve()
                        if p.is_dir():
                            watch_dirs.add(p)
            except Exception:
                pass

            if not watch_dirs:
                watch_dirs.add(self.workspace_root)

            for d in watch_dirs:
                if d.is_dir():
                    self._observer.schedule(handler, str(d), recursive=True)

            self._observer.start()
            logger.info(f"[{self.name}] Watchdog observer started for {len(watch_dirs)} directories.")
        except Exception as e:
            logger.warning(f"[{self.name}] Watchdog failed to start: {e}. Running in passive mode.")

    def stop(self) -> None:
        """Stops the file observer and releases background resources."""
        self._is_running = False

        try:
            indices_dir = self._get_pipeline().get_indices_dir()
            active_file = indices_dir / ".watcher_active"
            if active_file.exists():
                active_file.unlink()
        except Exception:
            pass

        with self._debounce_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            self._pending_dirty_paths.clear()

        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:
                pass
            self._observer = None

    def health_check(self) -> bool:
        """Returns True if the worker is actively running and observer thread is healthy."""
        if not self._is_running:
            return False
        if self._observer is not None:
            return self._observer.is_alive()
        return True
