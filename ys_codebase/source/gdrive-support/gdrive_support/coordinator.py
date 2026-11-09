"""
SyncCoordinator: Inter-process locked orchestration of cloud repository initialization,
Shortcut delta branches, Copy-on-Write (.history/) & unreferenced garbage collection (.trash/),
incremental state ledger persistence, 4-stage bidirectional synchronization under 'repo_sync/',
and local-cache-driven soft-merge / soft-remove of the root README.md.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import contextvars
import copy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid

from core import config as core_config
from core import uri
from core import vfs
from core.log import log_file_jsonl
from core.platform.lock import InterProcessLock
from core.platform.process import is_process_alive

from .config import (
    GDriveConfig,
    GDriveConfigError,
    GDriveConflictError,
    GDriveDirtyWorktreeError,
    GDriveError,
    GDriveFileNotFoundError,
    GDrivePathError,
    GDriveRepoSyncDisabledError,
    GDriveRepoUninitializedError,
    collect_space_local_files_with_stat,
    is_sensitive_credential_path,
    normalize_remote_rel_path,
)
from .incremental_cache import (
    BRANCH_INTERNAL_SYSTEM_NAMES,
    IncrementalCacheMixin,
    _IncrementalPatchContext,
)
from .ledger import LocalStateLedgerMixin
from .readme_sync import (
    DEFAULT_REPO_SYNC_ROOT,
    REPO_README_FILENAME,
    ROOT_README_BEGIN_MARKER,
    ROOT_README_END_MARKER,
    _extract_cached_readme_state,
    build_managed_readme_content,
    build_root_readme_managed_block,
    merge_root_readme_block,
    reconcile_root_readme_state,
    strip_root_readme_block,
)
from .reconciler import (
    FileEntry,
    SyncAction,
    SyncActionType,
    compute_orphan_history_file_ids,
    is_file_id_referenced_by_other_branches,
    reconcile_three_way,
)
from .transport import (
    AbstractSyncTransport,
    RemoteEntry,
    compute_local_hashes,
)

REPO_CONFIG_FILENAME = ".yscb_gdrive.json"

SYSTEM_NAMES = frozenset({
    REPO_CONFIG_FILENAME,
    REPO_README_FILENAME,
    ".history",
    ".trash",
})
STABILIZATION_WINDOW_NS = 2_000_000_000  # 2.0 seconds
MAX_LOG_BYTES = 2 * 1024 * 1024  # 2 MB
PARALLEL_TRANSFER_WORKERS = 8


def _create_conflict_backup(local_path: Path) -> Path:
    """Create a timestamped local `.conflict.<UTC>.bak` backup copy before overwriting or deleting."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bak_path = local_path.with_name(f"{local_path.name}.conflict.{ts}.bak")
    shutil.copy2(local_path, bak_path)
    return bak_path


class SyncReport:
    """Structured summary of a pull / push / sync execution."""

    def __init__(
        self,
        branch: str,
        mode: str,
        pushed: Optional[List[str]] = None,
        pulled: Optional[List[str]] = None,
        deleted_local: Optional[List[str]] = None,
        deleted_remote: Optional[List[str]] = None,
        conflicts: Optional[List[str]] = None,
        moved_to_history: Optional[List[str]] = None,
        gc_history_to_trash: Optional[List[str]] = None,
        skipped_stabilizing: Optional[List[str]] = None,
        exit_code: int = 0,
        yielded: bool = False,
        cache_hit_level: Optional[int] = None,
    ) -> None:
        self.branch = branch
        self.mode = mode
        self.pushed: List[str] = list(pushed) if pushed is not None else []
        self.pulled: List[str] = list(pulled) if pulled is not None else []
        self.deleted_local: List[str] = list(deleted_local) if deleted_local is not None else []
        self.deleted_remote: List[str] = list(deleted_remote) if deleted_remote is not None else []
        self.conflicts: List[str] = list(conflicts) if conflicts is not None else []
        self.moved_to_history: List[str] = list(moved_to_history) if moved_to_history is not None else []
        self.gc_history_to_trash: List[str] = list(gc_history_to_trash) if gc_history_to_trash is not None else []
        self.skipped_stabilizing: List[str] = list(skipped_stabilizing) if skipped_stabilizing is not None else []
        self.exit_code = exit_code
        self.yielded = yielded
        self.cache_hit_level = cache_hit_level

    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch": self.branch,
            "mode": self.mode,
            "pushed": self.pushed,
            "pulled": self.pulled,
            "deleted_local": self.deleted_local,
            "deleted_remote": self.deleted_remote,
            "conflicts": self.conflicts,
            "moved_to_history": self.moved_to_history,
            "gc_history_to_trash": self.gc_history_to_trash,
            "skipped_stabilizing": self.skipped_stabilizing,
            "exit_code": self.exit_code,
            "yielded": self.yielded,
            "cache_hit_level": self.cache_hit_level,
        }


@dataclass(frozen=True)
class _PushTask:
    """Encapsulated Stage 3 upload work item."""

    rel_path: str
    abs_local: Path
    remote_branch_rel: str
    existing_remote: Optional[RemoteEntry]
    local_entry: FileEntry
    action_type: SyncActionType
    remote_entry: Optional[FileEntry]
    baseline_entry: Optional[FileEntry]


@dataclass(frozen=True)
class _PullTask:
    """Encapsulated Stage 3 download work item."""

    rel_path: str
    abs_local: Path
    remote_branch_rel: str
    remote_entry: FileEntry


@dataclass(frozen=True)
class _RemoteStageSnapshot:
    """Stage 1 remote snapshot and cache state before Stage 3 reconciliation."""

    cache_hit_level: int
    meta: Dict[str, Any]
    remote_snap: Dict[str, FileEntry]
    raw_remote_entries: Dict[str, RemoteEntry]
    branch_dir_ids_current: Dict[str, str]
    flushed_external_trash: List[str]
    pending_page_token: str
    stage1_meta_dirty: bool = False


class _BackgroundYieldRequested(Exception):
    """Internal signal raised when a background worker yields the lock to a foreground CLI."""


class SyncCoordinator(LocalStateLedgerMixin, IncrementalCacheMixin):
    """
    Coordinates branch lifecycle, three-way reconciliation, Copy-on-Write (.history/),
    reference-counted garbage collection (.trash/), and incremental state ledger updates
    under the isolated '<root_folder_id>/repo_sync/' directory.
    """

    def __init__(
        self,
        config: GDriveConfig,
        transport: AbstractSyncTransport,
        project_root: Optional[Path] = None,
        state_path: Optional[Path] = None,
        lock_path: Optional[Path] = None,
        log_path: Optional[Path] = None,
        readme_state_path: Optional[Path] = None,
        file_space_manager: Optional[Any] = None,
        repo_sync_prefix: Optional[str] = None,
    ) -> None:
        self.config = config
        self.transport = transport
        effective_prefix = (
            repo_sync_prefix
            if repo_sync_prefix is not None
            else (config.repo_sync_root or DEFAULT_REPO_SYNC_ROOT)
        )
        self.repo_sync_prefix = (
            normalize_remote_rel_path(effective_prefix) or DEFAULT_REPO_SYNC_ROOT
        )
        self.project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(uri.resolve("project://")).resolve()
        )
        self.state_path = (
            Path(state_path).resolve()
            if state_path is not None
            else Path(uri.resolve("storage.local://gdrive-support/sync_state.json")).resolve()
        )
        self.state_journal_path = self.state_path.with_name(
            f"{self.state_path.stem}.journal.jsonl"
        )
        self.lock_path = (
            Path(lock_path).resolve()
            if lock_path is not None
            else Path(uri.resolve("cache://gdrive-support/sync.lock")).resolve()
        )
        self.log_path = (
            Path(log_path).resolve()
            if log_path is not None
            else Path(uri.resolve("cache://gdrive-support/sync.log")).resolve()
        )
        self.readme_state_path = (
            Path(readme_state_path).resolve()
            if readme_state_path is not None
            else Path(uri.resolve("storage.local://gdrive-support/readme_sync_state.json")).resolve()
        )
        self.yield_signal_path = self.lock_path.parent / "cli_yield.signal"
        self._meta_lock = threading.Lock()
        self._background_abort_check: Optional[Callable[[], bool]] = None
        self._file_space_manager = file_space_manager

    # ------------------------------------------------------------------
    # Gate & Path Prefix Helpers
    # ------------------------------------------------------------------

    def ensure_repo_sync_enabled(self) -> None:
        """Raise GDriveRepoSyncDisabledError if repo_sync.enable is False."""
        if not self.config.repo_sync_enabled:
            raise GDriveRepoSyncDisabledError(
                "repo_sync is disabled ('repo_sync.enable' is false in config://gdrive-support/). "
                "Branch and sync operations (init, branch, checkout, pull, push, sync) are blocked; "
                "only atomic operations (ls, get, put, rm, mkdir, shortcut) are permitted."
            )

    def _precreate_remote_dirs(self, remote_file_paths: List[str]) -> List[RemoteEntry]:
        """
        Pre-create all ancestor parent directories grouped by depth level (BFS)
        before dispatching concurrent file transfer threads.
        """
        parents: Set[str] = set()
        for p in remote_file_paths:
            curr = Path(p).parent.as_posix()
            while curr not in ("", "."):
                parents.add(curr)
                curr = Path(curr).parent.as_posix()
        if not parents:
            return []

        by_depth: Dict[int, List[str]] = {}
        for parent_rel in sorted(parents):
            by_depth.setdefault(parent_rel.count("/"), []).append(parent_rel)

        def _mkdir_worker(d_rel: str) -> RemoteEntry:
            try:
                return self.transport.mkdir(d_rel)
            finally:
                self.transport.release_thread_resources()

        created: List[RemoteEntry] = []
        for depth in sorted(by_depth.keys()):
            level_dirs = by_depth[depth]
            if len(level_dirs) == 1:
                created.append(self.transport.mkdir(level_dirs[0]))
                continue
            with ThreadPoolExecutor(
                max_workers=min(PARALLEL_TRANSFER_WORKERS, len(level_dirs))
            ) as pool:
                fut_map = {
                    pool.submit(
                        contextvars.copy_context().run,
                        _mkdir_worker,
                        d_rel,
                    ): d_rel
                    for d_rel in level_dirs
                }
                level_results: Dict[str, RemoteEntry] = {}
                for fut in as_completed(fut_map):
                    d_rel = fut_map[fut]
                    level_results[d_rel] = fut.result()
                for d_rel in level_dirs:
                    created.append(level_results[d_rel])
        return created

    def reconcile_root_readme(self) -> Dict[str, Any]:
        """Reconcile the top-level root/README.md if repo_sync.enable or repo_sync_root changed vs local cache."""
        return reconcile_root_readme_state(
            config=self.config,
            transport=self.transport,
            readme_state_path=self.readme_state_path,
        )

    # ------------------------------------------------------------------
    # Lock, Cooperative Preemption & Logging Helpers
    # ------------------------------------------------------------------

    def should_yield_background(self) -> bool:
        """
        Return True if a background sync worker should yield the lock immediately:
        - Either _background_abort_check() returned True, or
        - A valid foreground cli_yield.signal file exists (age <= 120s and live PID).
          Orphan signal files (>120s old or dead PID) are automatically unlinked and ignored.
        """
        if self._background_abort_check is not None:
            try:
                if self._background_abort_check():
                    return True
            except Exception:
                pass

        if not self.yield_signal_path.exists():
            return False

        try:
            raw = json.loads(self.yield_signal_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                self.yield_signal_path.unlink(missing_ok=True)
                return False
            pid = int(raw.get("pid") or 0)
            ts = float(raw.get("ts") or 0.0)
        except (OSError, ValueError, TypeError):
            self.yield_signal_path.unlink(missing_ok=True)
            return False

        if pid <= 0 or ts <= 0.0:
            self.yield_signal_path.unlink(missing_ok=True)
            return False

        if (time.time() - ts) > 120.0 or (
            pid != os.getpid() and not is_process_alive(pid)
        ):
            self.yield_signal_path.unlink(missing_ok=True)
            return False

        return True

    def _acquire_lock(
        self, non_blocking: bool = False, timeout_sec: float = 60.0
    ) -> InterProcessLock:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = InterProcessLock(str(self.lock_path))
        if non_blocking:
            acquired = lock.acquire(blocking=False)
        else:
            acquired = lock.acquire(blocking=False)
            if not acquired:
                try:
                    vfs.write_json(
                        self.yield_signal_path,
                        {"pid": os.getpid(), "ts": time.time()},
                        indent=2,
                        encoding="utf-8",
                        atomic=True,
                    )
                except OSError:
                    pass
                try:
                    acquired = lock.acquire(blocking=True, timeout_sec=timeout_sec)
                finally:
                    self.yield_signal_path.unlink(missing_ok=True)
        if not acquired:
            raise GDriveError(
                f"Could not acquire sync lock at '{self.lock_path.as_posix()}'."
            )
        return lock

    def _append_log(self, event: str, details: Dict[str, Any]) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            if self.log_path.is_file() and self.log_path.stat().st_size >= MAX_LOG_BYTES:
                rotated = self.log_path.with_suffix(".log.1")
                os.replace(self.log_path, rotated)
            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event,
                **details,
            }
            log_file_jsonl(self.log_path, record)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Cloud repo_sync/.yscb_gdrive.json Metadata Management
    # ------------------------------------------------------------------

    def _read_remote_repo_meta(self) -> Optional[Dict[str, Any]]:
        cfg_rel = self._repo_rel(REPO_CONFIG_FILENAME)
        entry = self.transport.get_entry(cfg_rel)
        if entry is None:
            return None
        with tempfile.TemporaryDirectory(prefix="yscb_gdrive_meta_") as tmp_d:
            local_tmp = Path(tmp_d) / REPO_CONFIG_FILENAME
            self.transport.download_file(cfg_rel, local_tmp)
            data = json.loads(local_tmp.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("branches", {"main": {"created_at": ""}})
                data.setdefault("branch_files", {})
                data.setdefault("history_files", {})
                return data
        return None

    def _write_remote_repo_meta(self, meta: Dict[str, Any]) -> RemoteEntry:
        cfg_rel = self._repo_rel(REPO_CONFIG_FILENAME)
        with tempfile.TemporaryDirectory(prefix="yscb_gdrive_meta_") as tmp_d:
            local_tmp = Path(tmp_d) / REPO_CONFIG_FILENAME
            local_tmp.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return self.transport.upload_file(local_tmp, cfg_rel)

    def _reconcile_unregistered_cloud_branches(
        self, meta: Dict[str, Any]
    ) -> List[str]:
        """
        Scan top-level directories under <repo_sync_root>/ and automatically register any
        non-system directory (not in SYSTEM_NAMES and not starting with '.' or '_') that
        was created directly on Google Drive without updating .yscb_gdrive.json.
        """
        branches = meta.setdefault("branches", {})
        branch_files = meta.setdefault("branch_files", {})
        repo_prefix = self._repo_rel()
        discovered: List[str] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for entry in self.transport.list_files(repo_prefix, recursive=False):
            if not entry.is_dir or entry.skipped_reason:
                continue
            rel = entry.rel_path
            name = (
                rel[len(repo_prefix) + 1 :]
                if rel.startswith(f"{repo_prefix}/")
                else Path(rel).name
            )
            if (
                not name
                or "/" in name
                or name in SYSTEM_NAMES
                or name.startswith(".")
                or name.startswith("_")
            ):
                continue
            if name not in branches:
                branches[name] = {
                    "created_at": now_iso,
                    "base_branch": meta.get("default_branch", "main"),
                    "auto_discovered": True,
                }
                branch_files.setdefault(name, {})
                discovered.append(name)

        if discovered:
            self._write_remote_repo_meta(meta)
        return discovered

    def _ensure_remote_repo_initialized(self) -> Dict[str, Any]:
        """
        Verify repo_sync/.yscb_gdrive.json exists on remote.
        - If repo_sync/ is completely empty (or does not exist yet), auto-initialize it.
        - If repo_sync/ is non-empty and lacks .yscb_gdrive.json, abort with GDriveRepoUninitializedError.
        - When initialized, auto-discover any cloud-created branch directories under repo_sync/.
        """
        self.reconcile_root_readme()
        meta = self._read_remote_repo_meta()
        if meta is not None:
            self._reconcile_unregistered_cloud_branches(meta)
            return meta

        top_entries = self.transport.list_files(self._repo_rel(), recursive=False)
        if top_entries:
            raise GDriveRepoUninitializedError(
                f"Remote '{self._repo_rel()}' folder is non-empty but lacks '{REPO_CONFIG_FILENAME}'. "
                "Refusing to sync to prevent overwriting an unmanaged folder. "
                "Run 'python yscb.py gdrive init' explicitly to initialize."
            )
        return self._bootstrap_remote_repo()

    def _bootstrap_remote_repo(self) -> Dict[str, Any]:
        self.transport.mkdir(self._repo_rel())
        hist_dir = self.transport.mkdir(self._repo_rel(".history"))
        trash_dir = self.transport.mkdir(self._repo_rel(".trash"))
        main_dir = self.transport.mkdir(self._repo_rel("main"))

        with tempfile.TemporaryDirectory(prefix="yscb_gdrive_readme_") as tmp_d:
            readme_tmp = Path(tmp_d) / REPO_README_FILENAME
            readme_tmp.write_text(
                build_managed_readme_content(repo_sync_root=self.repo_sync_prefix),
                encoding="utf-8",
            )
            self.transport.upload_file(readme_tmp, self._repo_rel(REPO_README_FILENAME))

        self.reconcile_root_readme()

        now_iso = datetime.now(timezone.utc).isoformat()
        meta: Dict[str, Any] = {
            "schema_version": "1.0",
            "managed_by": "yscb module:gdrive-support",
            "repo_id": f"gdrive_repo_{uuid.uuid4().hex[:12]}",
            "repo_sync_prefix": self.repo_sync_prefix,
            "created_at": now_iso,
            "default_branch": "main",
            "system_folders": {
                "history_id": hist_dir.file_id,
                "trash_id": trash_dir.file_id,
                "main_id": main_dir.file_id,
            },
            "branches": {
                "main": {
                    "created_at": now_iso,
                    "base_branch": None,
                }
            },
            "branch_files": {
                "main": {},
            },
            "history_files": {},
        }
        self._write_remote_repo_meta(meta)
        return meta

    # ------------------------------------------------------------------
    # Public Branch & Repo Lifecycle Operations
    # ------------------------------------------------------------------

    def init_repo(self, force: bool = False) -> Dict[str, Any]:
        """Explicitly initialize <root_folder_id>/repo_sync/ and soft-merge root/README.md."""
        self.ensure_repo_sync_enabled()
        lock = self._acquire_lock()
        try:
            existing = self._read_remote_repo_meta()
            if existing is not None and not force:
                self.reconcile_root_readme()
                return {"status": "already_initialized", "meta": existing}
            meta = self._bootstrap_remote_repo()
            state = self._load_local_state()
            state.pop("remote_repo_cache", None)
            self._save_local_state(state)
            self._append_log("init_repo", {"repo_id": meta.get("repo_id")})
            return {"status": "initialized", "meta": meta}
        finally:
            lock.release()

    def list_branches(self) -> Dict[str, Any]:
        """List all registered cloud branches under repo_sync/ and active_branch without write side effects."""
        self.ensure_repo_sync_enabled()
        meta = self._read_remote_repo_meta()
        repo_prefix = self._repo_rel()
        now_iso = datetime.now(timezone.utc).isoformat()
        if meta is None:
            top_entries = self.transport.list_files(
                repo_prefix, recursive=False, deduplicate=False
            )
            if top_entries:
                raise GDriveRepoUninitializedError(
                    f"Remote '{repo_prefix}' folder is non-empty but lacks '{REPO_CONFIG_FILENAME}'. "
                    "Refusing to list branches on an unmanaged folder. "
                    "Run 'python yscb.py gdrive init' explicitly to initialize."
                )
            return {
                "active_branch": self.config.active_branch,
                "default_branch": "main",
                "branches": {"main": {"created_at": now_iso, "base_branch": None}},
            }

        branches = copy.deepcopy(meta.get("branches", {}))
        for entry in self.transport.list_files(
            repo_prefix, recursive=False, deduplicate=False
        ):
            if not entry.is_dir or entry.skipped_reason:
                continue
            rel = entry.rel_path
            name = (
                rel[len(repo_prefix) + 1 :]
                if rel.startswith(f"{repo_prefix}/")
                else Path(rel).name
            )
            if (
                not name
                or "/" in name
                or name in SYSTEM_NAMES
                or name.startswith(".")
                or name.startswith("_")
            ):
                continue
            if name not in branches:
                branches[name] = {
                    "created_at": now_iso,
                    "base_branch": meta.get("default_branch", "main"),
                    "auto_discovered": True,
                }
        return {
            "active_branch": self.config.active_branch,
            "default_branch": meta.get("default_branch", "main"),
            "branches": branches,
        }

    def create_branch(
        self, branch_name: str, from_branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new delta branch repo_sync/<branch_name>/ with real directory skeleton and
        Google Drive Shortcuts pointing to all files in repo_sync/<from_branch> (default 'main').
        """
        self.ensure_repo_sync_enabled()
        norm_branch = normalize_remote_rel_path(branch_name)
        if not norm_branch or "/" in norm_branch or norm_branch in SYSTEM_NAMES:
            raise GDrivePathError(f"Invalid branch name: '{branch_name}'")

        source_branch = normalize_remote_rel_path(from_branch or "main") or "main"
        lock = self._acquire_lock()
        try:
            meta = self._ensure_remote_repo_initialized()
            branches = meta.setdefault("branches", {})
            if norm_branch in branches:
                raise GDriveConfigError(f"Branch '{norm_branch}' already exists.")
            if source_branch not in branches:
                raise GDriveConfigError(f"Source branch '{source_branch}' does not exist.")

            dst_branch_prefix = self._repo_rel(norm_branch)
            src_branch_prefix = self._repo_rel(source_branch)
            branch_root_ent = self.transport.mkdir(dst_branch_prefix)
            src_entries = self.transport.list_files(src_branch_prefix, recursive=True)
            branch_files_map = meta.setdefault("branch_files", {})
            new_branch_map: Dict[str, str] = {}
            created_dir_entries: List[RemoteEntry] = [branch_root_ent]

            shortcut_tasks: List[Tuple[str, str, str]] = []
            dir_count = 0
            for entry in src_entries:
                if entry.skipped_reason:
                    continue
                sub_rel = entry.rel_path[len(src_branch_prefix) + 1 :]
                dst_rel = f"{dst_branch_prefix}/{sub_rel}"
                if entry.is_dir:
                    d_ent = self.transport.mkdir(dst_rel)
                    created_dir_entries.append(d_ent)
                    dir_count += 1
                else:
                    target_fid = (
                        entry.target_file_id if entry.is_shortcut else entry.file_id
                    )
                    shortcut_tasks.append((sub_rel, dst_rel, target_fid))

            precreated = self._precreate_remote_dirs(
                [dst_rel for _, dst_rel, _ in shortcut_tasks]
            )
            created_dir_entries.extend(precreated)

            def _shortcut_worker(t_fid: str, d_rel: str) -> RemoteEntry:
                try:
                    return self.transport.create_shortcut(t_fid, d_rel)
                finally:
                    self.transport.release_thread_resources()

            shortcut_count = 0
            created_shortcut_entries: Dict[str, RemoteEntry] = {}
            if shortcut_tasks:
                with ThreadPoolExecutor(max_workers=PARALLEL_TRANSFER_WORKERS) as pool:
                    fut_map = {
                        pool.submit(
                            contextvars.copy_context().run,
                            _shortcut_worker,
                            target_fid,
                            dst_rel,
                        ): (sub_rel, target_fid)
                        for sub_rel, dst_rel, target_fid in shortcut_tasks
                    }
                    for fut in as_completed(fut_map):
                        sc_ent = fut.result()
                        sub_rel, target_fid = fut_map[fut]
                        new_branch_map[sub_rel] = target_fid
                        created_shortcut_entries[sub_rel] = sc_ent
                        shortcut_count += 1
                new_branch_map = dict(sorted(new_branch_map.items()))

            now_iso = datetime.now(timezone.utc).isoformat()
            branches[norm_branch] = {
                "created_at": now_iso,
                "base_branch": source_branch,
            }
            branch_files_map[norm_branch] = new_branch_map
            meta_ent = self._write_remote_repo_meta(meta)

            state = self._load_local_state()
            cache = state.get("remote_repo_cache")
            if isinstance(cache, dict) and isinstance(cache.get("branches"), dict):
                cache["branches"][norm_branch] = {
                    "raw_entries": {
                        k: v.to_dict() for k, v in sorted(created_shortcut_entries.items())
                    },
                    "dir_ids": {},
                }
                self._update_cache_dirs(state, norm_branch, created_dir_entries)
                self._update_cache_meta(state, meta, meta_ent)
            self._save_local_state(state)
            self._append_log(
                "create_branch",
                {
                    "branch": norm_branch,
                    "from": source_branch,
                    "shortcuts": shortcut_count,
                },
            )
            return {
                "status": "ok",
                "branch": norm_branch,
                "from_branch": source_branch,
                "directories_created": dir_count,
                "shortcuts_created": shortcut_count,
            }
        finally:
            lock.release()

    def delete_branch(self, branch_name: str) -> Dict[str, Any]:
        """
        Move repo_sync/<branch_name>/ to Google Drive Trash (or sandbox .trash/), remove it from .yscb_gdrive.json,
        and immediately garbage-collect any repo_sync/.history/ files whose reference count drops to 0.
        """
        self.ensure_repo_sync_enabled()
        norm_branch = normalize_remote_rel_path(branch_name)
        if norm_branch == "main":
            raise GDriveConfigError("Deleting the 'main' trunk branch is forbidden.")
        if norm_branch == self.config.active_branch:
            raise GDriveConfigError(
                f"Cannot delete the currently active branch '{norm_branch}'."
            )

        lock = self._acquire_lock()
        try:
            meta = self._ensure_remote_repo_initialized()
            branches = meta.get("branches", {})
            if norm_branch not in branches:
                raise GDriveFileNotFoundError(f"Branch '{norm_branch}' not found.")

            self.transport.trash_file(self._repo_rel(norm_branch))
            branches.pop(norm_branch, None)
            meta.get("branch_files", {}).pop(norm_branch, None)

            gc_trashed = self._gc_unreferenced_history_files(meta)
            flushed_ext_trash = self._flush_external_repo_trash()
            meta_ent = self._write_remote_repo_meta(meta)

            state = self._load_local_state()
            state.get("branches", {}).pop(norm_branch, None)
            self._remove_cache_branch(state, norm_branch)
            self._update_cache_meta(state, meta, meta_ent)
            self._save_local_state(state)

            self._append_log(
                "delete_branch",
                {
                    "branch": norm_branch,
                    "gc_history_to_trash": gc_trashed,
                    "flushed_external_trash": flushed_ext_trash,
                },
            )
            return {
                "status": "ok",
                "deleted_branch": norm_branch,
                "gc_history_to_trash": gc_trashed,
                "flushed_external_trash": flushed_ext_trash,
            }
        finally:
            lock.release()

    def checkout_branch(
        self, target_branch: str, force: bool = False, backup: bool = False
    ) -> Dict[str, Any]:
        """
        Atomically switch worktree from current active_branch to target_branch under repo_sync/
        using a two-phase download-before-delete commit sequence.
        """
        self.ensure_repo_sync_enabled()
        norm_target = normalize_remote_rel_path(target_branch)
        if not norm_target or "/" in norm_target:
            raise GDrivePathError(f"Invalid target branch: '{target_branch}'")

        lock = self._acquire_lock()
        try:
            meta = self._ensure_remote_repo_initialized()
            branches = meta.get("branches", {})
            if norm_target not in branches:
                raise GDriveFileNotFoundError(
                    f"Target branch '{norm_target}' does not exist in remote repository."
                )

            curr_branch = self.config.active_branch
            state = self._load_local_state()
            curr_base_raw = state.get("branches", {}).get(curr_branch, {}).get("files", {})
            curr_base = {
                k: FileEntry.from_dict(v) for k, v in curr_base_raw.items()
            }
            local_snap, local_path_map, _ = self._collect_local_snapshot(state)
            curr_remote_snap, curr_raw_entries, curr_dir_ids, curr_dir_meta = (
                self._scan_remote_branch_with_dirs(curr_branch)
            )

            if not force:
                pre_actions = reconcile_three_way(
                    local_snap,
                    curr_remote_snap,
                    curr_base,
                    mode="sync",
                    allow_push_delete=True,
                )
                dirty = [
                    a.rel_path
                    for a in pre_actions
                    if a.action
                    in (
                        SyncActionType.PUSH_NEW,
                        SyncActionType.PUSH_UPDATE,
                        SyncActionType.DELETE_REMOTE,
                        SyncActionType.CONFLICT,
                    )
                ]
                if dirty:
                    raise GDriveDirtyWorktreeError(
                        f"Local worktree has unsynced changes on branch '{curr_branch}': {dirty}. "
                        "Sync or commit changes first, or pass --force."
                    )

            target_remote_snap, target_raw_entries, target_dir_ids, target_dir_meta = (
                self._scan_remote_branch_with_dirs(norm_target)
            )
            new_target_branch_state: Dict[str, Any] = {}
            fp_cache = state.setdefault("fingerprint_cache", {})

            removed_orphans: List[str] = []
            pulled_files: List[str] = []

            # Phase 1: Download and verify all target branch files first
            for rel_p, rem_entry in sorted(target_remote_snap.items()):
                abs_local = local_path_map.get(rel_p) or self._resolve_remote_rel_to_local_abs(rel_p)
                if abs_local is None:
                    continue
                loc_existing = local_snap.get(rel_p)
                if loc_existing is None or loc_existing.md5 != rem_entry.md5:
                    should_backup = bool(
                        abs_local.is_file()
                        and loc_existing is not None
                        and loc_existing.md5 != rem_entry.md5
                        and (backup or rel_p not in curr_base)
                    )
                    if should_backup:
                        _create_conflict_backup(abs_local)
                    self.transport.download_file(
                        self._repo_rel(f"{norm_target}/{rel_p}"),
                        abs_local,
                        entry_hint=target_raw_entries.get(rel_p),
                    )
                    pulled_files.append(rel_p)

                md5_hex, sha_hex, sz = compute_local_hashes(abs_local)
                st = abs_local.stat()
                mtime_ns = int(st.st_mtime_ns)
                fp_cache[abs_local.as_posix()] = {
                    "mtime_ns": mtime_ns,
                    "size": sz,
                    "md5": md5_hex,
                    "sha256": sha_hex,
                }
                new_base = FileEntry(
                    rel_path=rel_p,
                    md5=md5_hex,
                    sha256=sha_hex,
                    size=sz,
                    mtime_ns=mtime_ns,
                    file_id=rem_entry.effective_file_id(),
                    is_shortcut=rem_entry.is_shortcut,
                    target_file_id=rem_entry.target_file_id,
                )
                new_target_branch_state[rel_p] = new_base.to_dict()

            # Phase 2: Only after all downloads succeed, remove local orphans exclusive to curr_branch
            old_tracked_paths = set(curr_base.keys())
            for rel_p in sorted(old_tracked_paths - set(target_remote_snap.keys())):
                abs_local = local_path_map.get(rel_p) or self._resolve_remote_rel_to_local_abs(rel_p)
                if abs_local and abs_local.is_file():
                    if backup:
                        _create_conflict_backup(abs_local)
                    abs_local.unlink()
                    removed_orphans.append(rel_p)

            # Phase 3: Atomically commit clean target baseline, active_branch, and incremental cache
            branch_files_map = meta.setdefault("branch_files", {})
            branch_files_map[curr_branch] = {
                rel_p: r_ent.effective_file_id()
                for rel_p, r_ent in curr_remote_snap.items()
            }
            branch_files_map[norm_target] = {
                rel_p: r_ent.effective_file_id()
                for rel_p, r_ent in target_remote_snap.items()
            }
            meta_ent: Optional[RemoteEntry] = None
            target_b_info = branches.get(norm_target)
            if isinstance(target_b_info, dict) and target_b_info.pop("auto_discovered", None):
                meta_ent = self._write_remote_repo_meta(meta)

            state.setdefault("branches", {})[norm_target] = {
                "files": new_target_branch_state
            }
            state["active_branch"] = norm_target
            self._update_cache_branch_snapshot(
                state, curr_branch, curr_raw_entries, curr_dir_ids, curr_dir_meta
            )
            self._update_cache_branch_snapshot(
                state, norm_target, target_raw_entries, target_dir_ids, target_dir_meta
            )
            self._update_cache_meta(state, meta, meta_ent)
            self._save_local_state(state)

            self._persist_active_branch_to_config(norm_target)
            self.config = replace(self.config, active_branch=norm_target)

            self._append_log(
                "checkout_branch",
                {
                    "from": curr_branch,
                    "to": norm_target,
                    "pulled": pulled_files,
                    "removed_orphans": removed_orphans,
                },
            )
            return {
                "status": "ok",
                "previous_branch": curr_branch,
                "active_branch": norm_target,
                "pulled_files": pulled_files,
                "removed_orphans": removed_orphans,
            }
        finally:
            lock.release()

    # ------------------------------------------------------------------
    # Four-Stage Synchronization Pipeline (pull / push / sync)
    # ------------------------------------------------------------------

    def run_sync(
        self,
        mode: str = "sync",
        delete: bool = False,
        force: bool = False,
        backup: bool = False,
        now_ns: Optional[int] = None,
        non_blocking_lock: bool = False,
        background_worker: bool = False,
        abort_check: Optional[Callable[[], bool]] = None,
        allow_delete: Optional[bool] = None,
    ) -> SyncReport:
        """
        Execute the 4-stage reconciliation pipeline:
        Stage 1: Collect local snapshot (with 2s stabilization guard + FingerprintCache) and remote snapshot (3-level cache).
        Stage 2: Compute 3-way reconciliation actions against per-branch baseline.
        Stage 3: Execute transfers with Copy-on-Write to .history/, empty-dir pruning, and unreferenced GC to .trash/.
        Stage 4: Persist updated per-file state ledger and return SyncReport.
        """
        from core.context import cell_span

        with cell_span(f"gdrive.sync.{mode}"):
            return self._run_sync_impl(
                mode=mode,
                delete=delete,
                force=force,
                backup=backup,
                now_ns=now_ns,
                non_blocking_lock=non_blocking_lock,
                background_worker=background_worker,
                abort_check=abort_check,
                allow_delete=allow_delete,
            )

    def _run_sync_impl(
        self,
        mode: str = "sync",
        delete: bool = False,
        force: bool = False,
        backup: bool = False,
        now_ns: Optional[int] = None,
        non_blocking_lock: bool = False,
        background_worker: bool = False,
        abort_check: Optional[Callable[[], bool]] = None,
        allow_delete: Optional[bool] = None,
    ) -> SyncReport:
        self.ensure_repo_sync_enabled()
        if not self.config.sync_spaces:
            raise GDriveConfigError(
                "No sync_spaces configured for gdrive-support; refusing to run sync."
            )
        norm_mode = (mode or "sync").strip().lower()
        if norm_mode not in ("sync", "pull", "push"):
            raise GDriveConfigError(f"Unsupported sync mode: '{mode}'")

        effective_delete = bool(delete or allow_delete)
        lock = self._acquire_lock(non_blocking=non_blocking_lock)
        self._background_abort_check = abort_check
        try:
            branch = self.config.active_branch
            if background_worker and self.should_yield_background():
                return SyncReport(
                    branch=branch, mode=norm_mode, yielded=True, cache_hit_level=None
                )

            self.transport.reset_scan_state()
            state = self._load_local_state()
            state["active_branch"] = branch
            branch_state_dict = (
                state.setdefault("branches", {})
                .setdefault(branch, {})
                .setdefault("files", {})
            )
            baseline_snap: Dict[str, FileEntry] = {
                k: FileEntry.from_dict(v) for k, v in branch_state_dict.items()
            }

            local_snap, local_path_map, stabilizing = self._collect_local_snapshot(
                state, now_ns=now_ns
            )
            if background_worker and self.should_yield_background():
                self._save_local_state(state)
                return SyncReport(
                    branch=branch, mode=norm_mode, yielded=True, cache_hit_level=None
                )

            rem_stage = self._collect_remote_stage_snapshot(
                state, branch, background_worker
            )
            if rem_stage is None:
                self._save_local_state(state)
                return SyncReport(
                    branch=branch, mode=norm_mode, yielded=True, cache_hit_level=2
                )

            meta = rem_stage.meta
            remote_snap = rem_stage.remote_snap
            if branch not in meta.get("branches", {}):
                raise GDriveConfigError(
                    f"Active branch '{branch}' is not registered in {self._repo_rel(REPO_CONFIG_FILENAME)}."
                )

            for stab_rel in stabilizing:
                local_snap.pop(stab_rel, None)
                remote_snap.pop(stab_rel, None)
                baseline_snap.pop(stab_rel, None)

            actions = reconcile_three_way(
                local_snap=local_snap,
                remote_snap=remote_snap,
                baseline_snap=baseline_snap,
                mode=norm_mode,
                allow_pull_delete=bool(
                    effective_delete or self.config.pull_delete_default
                ),
                allow_push_delete=bool(
                    effective_delete or self.config.push_delete_default
                ),
                force=force,
            )

            conflicts = [
                a.rel_path for a in actions if a.action == SyncActionType.CONFLICT
            ]
            if conflicts and norm_mode in ("pull", "push") and not force:
                raise GDriveConflictError(
                    f"Unresolved conflicts detected during '{norm_mode}' on branch '{branch}': {conflicts}. "
                    "Use --force (optionally with --backup) or resolve manually."
                )

            report = SyncReport(
                branch=branch,
                mode=norm_mode,
                conflicts=list(conflicts),
                skipped_stabilizing=list(stabilizing),
                exit_code=2 if conflicts else 0,
                cache_hit_level=rem_stage.cache_hit_level,
            )
            if rem_stage.flushed_external_trash:
                report.gc_history_to_trash.extend(rem_stage.flushed_external_trash)

            self._execute_stage3_reconciliation(
                state=state,
                branch=branch,
                branch_state_dict=branch_state_dict,
                rem_stage=rem_stage,
                actions=actions,
                local_path_map=local_path_map,
                report=report,
                force=force,
                backup=backup,
                background_worker=background_worker,
            )

            self._append_log("run_sync", report.to_dict())
            return report
        finally:
            self._background_abort_check = None
            lock.release()

    def _collect_remote_stage_snapshot(
        self,
        state: Dict[str, Any],
        branch: str,
        background_worker: bool,
    ) -> Optional[_RemoteStageSnapshot]:
        """Stage 1 remote snapshot resolution via Level 0/1 incremental cache or Level 2 full scan."""
        prev_cached_bf = copy.deepcopy(
            ((state.get("remote_repo_cache") or {}).get("repo_meta") or {}).get("branch_files") or {}
        )
        inc_res = self._try_incremental_remote_cache(state, branch)
        if inc_res is not None:
            cache_hit_level, meta, remote_snap, raw_remote_entries, pending_token = (
                inc_res
            )
            inc_meta_dirty = bool((meta.get("branch_files") or {}) != prev_cached_bf)
            self._warm_transport_folder_cache(state, branch)
            branch_dir_ids_current = dict(
                (
                    state.get("remote_repo_cache", {})
                    .get("branches", {})
                    .get(branch, {})
                    .get("dir_ids")
                    or {}
                )
            )
            self.reconcile_root_readme()
            return _RemoteStageSnapshot(
                cache_hit_level=cache_hit_level,
                meta=meta,
                remote_snap=remote_snap,
                raw_remote_entries=raw_remote_entries,
                branch_dir_ids_current=branch_dir_ids_current,
                flushed_external_trash=[],
                pending_page_token=pending_token,
                stage1_meta_dirty=inc_meta_dirty,
            )

        start_token = ""
        try:
            start_token = self.transport.get_start_page_token()
        except Exception:
            start_token = ""

        meta = self._ensure_remote_repo_initialized()
        if branch not in meta.get("branches", {}):
            raise GDriveConfigError(
                f"Active branch '{branch}' is not registered in {self._repo_rel(REPO_CONFIG_FILENAME)}."
            )
        if background_worker and self.should_yield_background():
            return None

        prev_meta_bf = copy.deepcopy(meta.get("branch_files") or {})
        flushed_ext_stage1 = self._flush_external_repo_trash()
        remote_snap, raw_remote_entries, branch_dir_ids, branch_dir_meta = (
            self._scan_remote_branch_with_dirs(branch)
        )
        branch_dir_ids_current = dict(branch_dir_ids)

        cache_branches: Dict[str, Any] = {
            branch: {
                "raw_entries": {
                    k: v.to_dict() for k, v in raw_remote_entries.items()
                },
                "dir_ids": branch_dir_ids,
            }
        }
        all_folder_meta: Dict[str, Dict[str, str]] = dict(branch_dir_meta)
        branch_files_map_init: Dict[str, Dict[str, str]] = meta.setdefault(
            "branch_files", {}
        )
        branch_files_map_init[branch] = {
            rel_p: r_ent.effective_file_id() for rel_p, r_ent in remote_snap.items()
        }
        branches_meta = meta.get("branches", {})
        auto_cleared = False
        if isinstance(branches_meta.get(branch), dict) and branches_meta[branch].pop(
            "auto_discovered", None
        ):
            auto_cleared = True

        for other_b, other_info in list(branches_meta.items()):
            if other_b == branch:
                continue
            if background_worker and self.should_yield_background():
                return None
            o_snap, o_raw, o_dirs, o_dmeta = self._scan_remote_branch_with_dirs(
                other_b
            )
            cache_branches[other_b] = {
                "raw_entries": {k: v.to_dict() for k, v in o_raw.items()},
                "dir_ids": o_dirs,
            }
            all_folder_meta.update(o_dmeta)
            branch_files_map_init[other_b] = {
                rel_p: r_ent.effective_file_id() for rel_p, r_ent in o_snap.items()
            }
            if isinstance(other_info, dict) and other_info.pop("auto_discovered", None):
                auto_cleared = True

        stage1_meta_dirty = bool(branch_files_map_init != prev_meta_bf or auto_cleared)
        self._populate_remote_repo_cache(
            state=state,
            page_token=start_token,
            meta=meta,
            cache_branches=cache_branches,
            folder_meta=all_folder_meta,
        )
        return _RemoteStageSnapshot(
            cache_hit_level=2,
            meta=meta,
            remote_snap=remote_snap,
            raw_remote_entries=raw_remote_entries,
            branch_dir_ids_current=branch_dir_ids_current,
            flushed_external_trash=flushed_ext_stage1,
            pending_page_token=start_token,
            stage1_meta_dirty=stage1_meta_dirty,
        )

    def _execute_stage3_reconciliation(
        self,
        state: Dict[str, Any],
        branch: str,
        branch_state_dict: Dict[str, Any],
        rem_stage: _RemoteStageSnapshot,
        actions: List[SyncAction],
        local_path_map: Dict[str, Path],
        report: SyncReport,
        force: bool,
        backup: bool,
        background_worker: bool,
    ) -> None:
        """Stage 3: Execute immediate actions, parallel push/pull pools, empty-dir pruning, and history GC."""
        meta = rem_stage.meta
        branch_files_map: Dict[str, Dict[str, str]] = meta.setdefault(
            "branch_files", {}
        )
        prev_branch_files = dict(branch_files_map.get(branch) or {})
        curr_branch_files = {
            rel_p: r_ent.effective_file_id()
            for rel_p, r_ent in rem_stage.remote_snap.items()
        }
        branch_files_map[branch] = curr_branch_files
        history_files: Dict[str, str] = meta.setdefault("history_files", {})
        meta_dirty = bool(
            rem_stage.stage1_meta_dirty or (curr_branch_files != prev_branch_files)
        )
        first_push_err: Optional[BaseException] = None
        first_pull_err: Optional[BaseException] = None

        try:
            push_tasks, pull_tasks, imm_dirty = self._partition_and_run_immediate_actions(
                state=state,
                branch=branch,
                branch_state_dict=branch_state_dict,
                curr_branch_files=curr_branch_files,
                branch_files_map=branch_files_map,
                history_files=history_files,
                raw_remote_entries=rem_stage.raw_remote_entries,
                local_path_map=local_path_map,
                actions=actions,
                report=report,
                force=force,
                backup=backup,
                background_worker=background_worker,
            )
            if imm_dirty:
                meta_dirty = True

            if push_tasks and not report.yielded:
                push_dirty, first_push_err = self._execute_push_batch(
                    state=state,
                    branch=branch,
                    branch_state_dict=branch_state_dict,
                    curr_branch_files=curr_branch_files,
                    branch_files_map=branch_files_map,
                    history_files=history_files,
                    push_tasks=push_tasks,
                    report=report,
                    force=force,
                    backup=backup,
                    background_worker=background_worker,
                )
                if push_dirty:
                    meta_dirty = True
                if first_push_err is not None:
                    raise first_push_err

            if pull_tasks and not report.yielded:
                first_pull_err = self._execute_pull_batch(
                    state=state,
                    branch=branch,
                    branch_state_dict=branch_state_dict,
                    raw_remote_entries=rem_stage.raw_remote_entries,
                    pull_tasks=pull_tasks,
                    report=report,
                    background_worker=background_worker,
                )
                if first_pull_err is not None:
                    raise first_pull_err

            if not report.yielded:
                if report.deleted_remote:
                    self._prune_empty_remote_branch_dirs(
                        state=state,
                        branch=branch,
                        curr_branch_files=curr_branch_files,
                        deleted_remote=report.deleted_remote,
                        fallback_dir_ids=rem_stage.branch_dir_ids_current,
                    )
                if not (
                    rem_stage.cache_hit_level == 0
                    and not report.pushed
                    and not report.deleted_remote
                    and not report.moved_to_history
                ):
                    had_auto = any(
                        isinstance(b_inf, dict) and bool(b_inf.get("auto_discovered"))
                        for b_inf in (meta.get("branches") or {}).values()
                    )
                    gc_trashed = self._gc_unreferenced_history_files(
                        meta, scan_physical=(rem_stage.cache_hit_level == 2)
                    )
                    if gc_trashed:
                        report.gc_history_to_trash.extend(gc_trashed)
                        meta_dirty = True
                    elif had_auto:
                        meta_dirty = True

            if meta_dirty:
                meta_ent = self._write_remote_repo_meta(meta)
                self._update_cache_meta(state, meta, meta_ent)
                meta_dirty = False
        finally:
            if meta_dirty:
                try:
                    meta_ent = self._write_remote_repo_meta(meta)
                    self._update_cache_meta(state, meta, meta_ent)
                    meta_dirty = False
                except Exception:
                    if first_push_err is None and first_pull_err is None:
                        raise
            else:
                self._update_cache_meta(state, meta, None)

            if first_push_err is not None:
                state.pop("remote_repo_cache", None)
            else:
                cache_obj = state.get("remote_repo_cache")
                if (
                    isinstance(cache_obj, dict)
                    and rem_stage.pending_page_token
                    and not report.yielded
                    and first_pull_err is None
                ):
                    cache_obj["page_token"] = rem_stage.pending_page_token

            self._save_local_state(state)

    def _partition_and_run_immediate_actions(
        self,
        state: Dict[str, Any],
        branch: str,
        branch_state_dict: Dict[str, Any],
        curr_branch_files: Dict[str, str],
        branch_files_map: Dict[str, Dict[str, str]],
        history_files: Dict[str, str],
        raw_remote_entries: Dict[str, RemoteEntry],
        local_path_map: Dict[str, Path],
        actions: List[SyncAction],
        report: SyncReport,
        force: bool,
        backup: bool,
        background_worker: bool,
    ) -> Tuple[List[_PushTask], List[_PullTask], bool]:
        """Partition PUSH/PULL tasks and execute IN_SYNC, DELETE_LOCAL, and DELETE_REMOTE actions."""
        push_tasks: List[_PushTask] = []
        pull_tasks: List[_PullTask] = []
        meta_dirty = False

        for act in actions:
            if background_worker and self.should_yield_background():
                report.yielded = True
                break

            rel_p = act.rel_path
            remote_branch_rel = self._repo_rel(f"{branch}/{rel_p}")

            if act.action == SyncActionType.IN_SYNC:
                if (
                    act.local_entry
                    and act.remote_entry
                    and act.reason == "identical_digest"
                ):
                    merged_entry = FileEntry(
                        rel_path=rel_p,
                        md5=act.local_entry.md5,
                        sha256=act.local_entry.sha256,
                        size=act.local_entry.size,
                        mtime_ns=act.local_entry.mtime_ns,
                        file_id=act.remote_entry.effective_file_id(),
                        is_shortcut=act.remote_entry.is_shortcut,
                        target_file_id=act.remote_entry.target_file_id,
                    )
                    branch_state_dict[rel_p] = merged_entry.to_dict()
                elif (
                    act.local_entry is None
                    and act.remote_entry is None
                    and act.baseline_entry is not None
                ):
                    if rel_p in curr_branch_files:
                        curr_branch_files.pop(rel_p, None)
                        meta_dirty = True
                    self._record_branch_file_delete(
                        state, branch, rel_p, remove_from_cache=True
                    )
                continue

            if act.action == SyncActionType.CONFLICT:
                continue

            if act.action in (SyncActionType.PUSH_NEW, SyncActionType.PUSH_UPDATE):
                abs_local = local_path_map.get(
                    rel_p
                ) or self._resolve_remote_rel_to_local_abs(rel_p)
                if abs_local is None or not abs_local.is_file():
                    continue
                assert act.local_entry is not None
                push_tasks.append(
                    _PushTask(
                        rel_path=rel_p,
                        abs_local=abs_local,
                        remote_branch_rel=remote_branch_rel,
                        existing_remote=raw_remote_entries.get(rel_p),
                        local_entry=act.local_entry,
                        action_type=act.action,
                        remote_entry=act.remote_entry,
                        baseline_entry=act.baseline_entry,
                    )
                )
                continue

            if act.action in (SyncActionType.PULL_NEW, SyncActionType.PULL_UPDATE):
                abs_local = local_path_map.get(
                    rel_p
                ) or self._resolve_remote_rel_to_local_abs(rel_p)
                if abs_local is None:
                    continue
                if (
                    backup
                    and abs_local.is_file()
                    and act.action == SyncActionType.PULL_UPDATE
                    and force
                    and act.local_entry
                    and act.baseline_entry
                    and act.local_entry.md5 != act.baseline_entry.md5
                ):
                    _create_conflict_backup(abs_local)

                assert act.remote_entry is not None
                pull_tasks.append(
                    _PullTask(
                        rel_path=rel_p,
                        abs_local=abs_local,
                        remote_branch_rel=remote_branch_rel,
                        remote_entry=act.remote_entry,
                    )
                )
                continue

            if act.action == SyncActionType.DELETE_LOCAL:
                abs_local = local_path_map.get(
                    rel_p
                ) or self._resolve_remote_rel_to_local_abs(rel_p)
                if abs_local and abs_local.is_file():
                    if backup:
                        _create_conflict_backup(abs_local)
                    abs_local.unlink()
                self._record_branch_file_delete(
                    state, branch, rel_p, remove_from_cache=False
                )
                report.deleted_local.append(rel_p)
                continue

            if act.action == SyncActionType.DELETE_REMOTE:
                existing_rem = raw_remote_entries.get(rel_p)
                if existing_rem is not None:
                    if (
                        not existing_rem.is_shortcut
                        and is_file_id_referenced_by_other_branches(
                            existing_rem.file_id, branch, branch_files_map
                        )
                    ):
                        hist_dir_rel = self._repo_rel(".history")
                        self.transport.mkdir(hist_dir_rel)
                        hist_rel = f"{hist_dir_rel}/{existing_rem.file_id}_{Path(rel_p).name}"
                        self.transport.move_file(
                            remote_branch_rel, hist_rel, entry_hint=existing_rem
                        )
                        with self._meta_lock:
                            history_files[existing_rem.file_id] = hist_rel
                            report.moved_to_history.append(existing_rem.file_id)
                    else:
                        self.transport.trash_file(
                            remote_branch_rel, file_id=existing_rem.file_id
                        )
                with self._meta_lock:
                    curr_branch_files.pop(rel_p, None)
                    meta_dirty = True
                self._record_branch_file_delete(
                    state, branch, rel_p, remove_from_cache=True
                )
                report.deleted_remote.append(rel_p)

        return push_tasks, pull_tasks, meta_dirty

    def _upload_single_push_task(
        self,
        task: _PushTask,
        branch: str,
        branch_files_map: Dict[str, Dict[str, str]],
        history_files: Dict[str, str],
        report: SyncReport,
        force: bool,
        backup: bool,
        background_worker: bool,
    ) -> Tuple[RemoteEntry, bool]:
        """Execute a single push upload task with atomic Copy-on-Write into .history/ when needed."""
        try:
            if background_worker and self.should_yield_background():
                raise _BackgroundYieldRequested()

            existing_rem = task.existing_remote
            if (
                backup
                and force
                and existing_rem is not None
                and task.action_type == SyncActionType.PUSH_UPDATE
                and task.remote_entry
                and task.baseline_entry
                and task.remote_entry.md5 != task.baseline_entry.md5
            ):
                rem_bak = task.abs_local.with_name(
                    f"{task.abs_local.name}.remote_conflict.{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.bak"
                )
                self.transport.download_file(
                    task.remote_branch_rel, rem_bak, entry_hint=existing_rem
                )

            in_place_fid: Optional[str] = None
            cow_moved = False
            if existing_rem is not None:
                if existing_rem.is_shortcut:
                    self.transport.trash_file(
                        task.remote_branch_rel, file_id=existing_rem.file_id
                    )
                else:
                    old_fid = existing_rem.file_id
                    with self._meta_lock:
                        needs_cow = is_file_id_referenced_by_other_branches(
                            old_fid, branch, branch_files_map
                        )
                    if needs_cow:
                        hist_dir_rel = self._repo_rel(".history")
                        hist_rel = f"{hist_dir_rel}/{old_fid}_{Path(task.rel_path).name}"
                        self.transport.move_file(
                            task.remote_branch_rel, hist_rel, entry_hint=existing_rem
                        )
                        with self._meta_lock:
                            history_files[old_fid] = hist_rel
                            report.moved_to_history.append(old_fid)
                        cow_moved = True
                    else:
                        in_place_fid = old_fid

            uploaded = self.transport.upload_file(
                task.abs_local,
                task.remote_branch_rel,
                in_place_file_id=in_place_fid,
            )
            return uploaded, cow_moved
        finally:
            self.transport.release_thread_resources()

    def _execute_push_batch(
        self,
        state: Dict[str, Any],
        branch: str,
        branch_state_dict: Dict[str, Any],
        curr_branch_files: Dict[str, str],
        branch_files_map: Dict[str, Dict[str, str]],
        history_files: Dict[str, str],
        push_tasks: List[_PushTask],
        report: SyncReport,
        force: bool,
        backup: bool,
        background_worker: bool,
    ) -> Tuple[bool, Optional[BaseException]]:
        """Execute all push tasks concurrently and commit per-file state updates."""
        created_dirs = self._precreate_remote_dirs(
            [t.remote_branch_rel for t in push_tasks]
        )
        self._update_cache_dirs(state, branch, created_dirs)
        any_cow_needed = any(
            t.existing_remote is not None
            and not t.existing_remote.is_shortcut
            and is_file_id_referenced_by_other_branches(
                t.existing_remote.file_id, branch, branch_files_map
            )
            for t in push_tasks
        )
        if any_cow_needed:
            self.transport.mkdir(self._repo_rel(".history"))

        meta_dirty = False
        first_push_err: Optional[BaseException] = None

        with ThreadPoolExecutor(max_workers=PARALLEL_TRANSFER_WORKERS) as pool:
            fut_map = {
                pool.submit(
                    contextvars.copy_context().run,
                    self._upload_single_push_task,
                    task,
                    branch,
                    branch_files_map,
                    history_files,
                    report,
                    force,
                    backup,
                    background_worker,
                ): task
                for task in push_tasks
            }
            for fut in as_completed(fut_map):
                task = fut_map[fut]
                if fut.cancelled():
                    continue
                try:
                    uploaded, cow_moved = fut.result()
                except _BackgroundYieldRequested:
                    report.yielded = True
                    continue
                except Exception as exc:
                    if first_push_err is None:
                        first_push_err = exc
                        for pending_fut in fut_map:
                            if not pending_fut.done():
                                pending_fut.cancel()
                    continue

                if cow_moved:
                    meta_dirty = True
                with self._meta_lock:
                    curr_branch_files[task.rel_path] = uploaded.file_id
                    meta_dirty = True
                new_base = FileEntry(
                    rel_path=task.rel_path,
                    md5=task.local_entry.md5,
                    sha256=task.local_entry.sha256,
                    size=task.local_entry.size,
                    mtime_ns=task.local_entry.mtime_ns,
                    file_id=uploaded.file_id,
                    is_shortcut=False,
                    target_file_id="",
                )
                fp_entry = {
                    "mtime_ns": task.local_entry.mtime_ns,
                    "size": task.local_entry.size,
                    "md5": task.local_entry.md5,
                    "sha256": task.local_entry.sha256,
                }
                self._record_branch_file_upsert(
                    state,
                    branch,
                    task.rel_path,
                    new_base.to_dict(),
                    cache_entry=uploaded,
                    fp_key=task.abs_local.as_posix(),
                    fp_entry=fp_entry,
                )
                report.pushed.append(task.rel_path)
                if background_worker and self.should_yield_background():
                    report.yielded = True
                    for pending_fut in fut_map:
                        if not pending_fut.done():
                            pending_fut.cancel()
                    break

        report.pushed.sort()
        return meta_dirty, first_push_err

    def _download_single_pull_task(
        self,
        task: _PullTask,
        raw_remote_entries: Dict[str, RemoteEntry],
        background_worker: bool,
    ) -> Tuple[str, str, int, int, RemoteEntry]:
        """Download a single remote file and compute its local hashes, mtime_ns, and RemoteEntry."""
        try:
            if background_worker and self.should_yield_background():
                raise _BackgroundYieldRequested()
            dl_entry = self.transport.download_file(
                task.remote_branch_rel,
                task.abs_local,
                entry_hint=raw_remote_entries.get(task.rel_path),
            )
            md5_hex, sha_hex, sz = compute_local_hashes(task.abs_local)
            st = task.abs_local.stat()
            return md5_hex, sha_hex, sz, int(st.st_mtime_ns), dl_entry
        finally:
            self.transport.release_thread_resources()

    def _execute_pull_batch(
        self,
        state: Dict[str, Any],
        branch: str,
        branch_state_dict: Dict[str, Any],
        raw_remote_entries: Dict[str, RemoteEntry],
        pull_tasks: List[_PullTask],
        report: SyncReport,
        background_worker: bool,
    ) -> Optional[BaseException]:
        """Execute all pull tasks concurrently and commit per-file state updates."""
        first_pull_err: Optional[BaseException] = None

        with ThreadPoolExecutor(max_workers=PARALLEL_TRANSFER_WORKERS) as pool:
            fut_map = {
                pool.submit(
                    contextvars.copy_context().run,
                    self._download_single_pull_task,
                    task,
                    raw_remote_entries,
                    background_worker,
                ): task
                for task in pull_tasks
            }
            for fut in as_completed(fut_map):
                task = fut_map[fut]
                if fut.cancelled():
                    continue
                try:
                    md5_hex, sha_hex, sz, mtime_ns, dl_entry = fut.result()
                except _BackgroundYieldRequested:
                    report.yielded = True
                    continue
                except Exception as exc:
                    if first_pull_err is None:
                        first_pull_err = exc
                        for pending_fut in fut_map:
                            if not pending_fut.done():
                                pending_fut.cancel()
                    continue

                new_base = FileEntry(
                    rel_path=task.rel_path,
                    md5=md5_hex,
                    sha256=sha_hex,
                    size=sz,
                    mtime_ns=mtime_ns,
                    file_id=task.remote_entry.effective_file_id(),
                    is_shortcut=task.remote_entry.is_shortcut,
                    target_file_id=task.remote_entry.target_file_id,
                )
                cached_rem = raw_remote_entries.get(task.rel_path) or dl_entry
                pulled_raw_entry = replace(
                    cached_rem,
                    rel_path=task.remote_branch_rel,
                    md5=md5_hex,
                    size=sz,
                )
                fp_entry = {
                    "mtime_ns": mtime_ns,
                    "size": sz,
                    "md5": md5_hex,
                    "sha256": sha_hex,
                }
                self._record_branch_file_upsert(
                    state,
                    branch,
                    task.rel_path,
                    new_base.to_dict(),
                    cache_entry=pulled_raw_entry,
                    fp_key=task.abs_local.as_posix(),
                    fp_entry=fp_entry,
                )
                report.pulled.append(task.rel_path)
                if background_worker and self.should_yield_background():
                    report.yielded = True
                    for pending_fut in fut_map:
                        if not pending_fut.done():
                            pending_fut.cancel()
                    break

        report.pulled.sort()
        return first_pull_err

    # ------------------------------------------------------------------
    # Internal Snapshot & GC Helpers
    # ------------------------------------------------------------------

    def _prune_empty_remote_branch_dirs(
        self,
        state: Dict[str, Any],
        branch: str,
        curr_branch_files: Dict[str, str],
        deleted_remote: List[str],
        fallback_dir_ids: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """
        Bottom-up prune empty remote directories inside `<repo_sync_root>/<branch>/`
        left behind after DELETE_REMOTE operations. Never deletes the branch root directory itself.
        """
        if not deleted_remote:
            return []

        candidate_dirs: Set[str] = set()
        for rel_p in deleted_remote:
            curr = Path(rel_p).parent.as_posix()
            while curr not in ("", "."):
                candidate_dirs.add(curr)
                curr = Path(curr).parent.as_posix()
        if not candidate_dirs:
            return []

        non_empty_dirs: Set[str] = set()
        for active_rel in curr_branch_files.keys():
            curr = Path(active_rel).parent.as_posix()
            while curr not in ("", "."):
                if curr in non_empty_dirs:
                    break
                non_empty_dirs.add(curr)
                curr = Path(curr).parent.as_posix()

        cache = state.get("remote_repo_cache")
        dir_ids_map: Dict[str, str] = {}
        if isinstance(cache, dict):
            b_cache = (cache.get("branches") or {}).get(branch)
            if isinstance(b_cache, dict) and isinstance(b_cache.get("dir_ids"), dict):
                dir_ids_map = b_cache["dir_ids"]

        rel_to_fid: Dict[str, str] = {}
        if fallback_dir_ids:
            for fid, d_rel in fallback_dir_ids.items():
                if d_rel:
                    rel_to_fid[d_rel] = fid
        for fid, d_rel in dir_ids_map.items():
            if d_rel:
                rel_to_fid[d_rel] = fid

        for d_rel, d_fid in list(rel_to_fid.items()):
            if not d_rel or d_rel in candidate_dirs or d_rel in non_empty_dirs:
                continue
            curr = d_rel
            while curr not in ("", "."):
                if curr in non_empty_dirs:
                    break
                non_empty_dirs.add(curr)
                curr = Path(curr).parent.as_posix()

        pruned_dirs: List[str] = []
        for d_rel in sorted(
            candidate_dirs, key=lambda p: (p.count("/"), len(p)), reverse=True
        ):
            if d_rel in non_empty_dirs:
                continue
            remote_dir_path = self._repo_rel(f"{branch}/{d_rel}")
            fid = rel_to_fid.get(d_rel)
            if self.transport.trash_file(remote_dir_path, file_id=fid):
                pruned_dirs.append(d_rel)
                if fid:
                    dir_ids_map.pop(fid, None)
                    if isinstance(cache, dict):
                        known = set(cache.get("known_folder_ids") or [])
                        known.discard(fid)
                        cache["known_folder_ids"] = sorted(known)
                        f_meta = cache.get("folder_meta")
                        if isinstance(f_meta, dict):
                            f_meta.pop(fid, None)

        return pruned_dirs

    def _warm_transport_folder_cache(
        self, state: Dict[str, Any], branch: str
    ) -> None:
        """
        Pre-warm transport._folder_cache from state['remote_repo_cache'] when Level 0 or Level 1 hits,
        eliminating redundant _list_children_raw calls during Stage 3 mkdir/upload/move.
        """
        cache = state.get("remote_repo_cache")
        if not isinstance(cache, dict):
            return
        folder_meta = cache.get("folder_meta")
        if not isinstance(folder_meta, dict):
            return

        warm_map: Dict[str, RemoteEntry] = {}
        repo_fid = str(cache.get("repo_folder_id") or "")
        hist_fid = str(cache.get("history_folder_id") or "")
        trash_fid = str(cache.get("trash_folder_id") or "")

        for fid, rel_p in (
            (repo_fid, self._repo_rel()),
            (hist_fid, self._repo_rel(".history")),
            (trash_fid, self._repo_rel(".trash")),
        ):
            if fid:
                fm = folder_meta.get(fid) or {}
                warm_map[rel_p] = RemoteEntry(
                    rel_path=rel_p,
                    name=str(fm.get("name") or Path(rel_p).name),
                    file_id=fid,
                    mime_type="application/vnd.google-apps.folder",
                    is_dir=True,
                    parent_id=str(fm.get("parent_id") or ""),
                )

        b_cache = (cache.get("branches") or {}).get(branch)
        if isinstance(b_cache, dict):
            dir_ids = b_cache.get("dir_ids") or {}
            for d_fid, sub_rel in dir_ids.items():
                if not d_fid:
                    continue
                full_rel = (
                    self._repo_rel(f"{branch}/{sub_rel}")
                    if sub_rel
                    else self._repo_rel(branch)
                )
                fm = folder_meta.get(d_fid) or {}
                warm_map[full_rel] = RemoteEntry(
                    rel_path=full_rel,
                    name=str(fm.get("name") or Path(full_rel).name),
                    file_id=d_fid,
                    mime_type="application/vnd.google-apps.folder",
                    is_dir=True,
                    parent_id=str(fm.get("parent_id") or ""),
                )

        if warm_map:
            self.transport.warm_folder_cache(warm_map)

    def _flush_external_repo_trash(self) -> List[str]:
        """
        Auto-clean any items placed inside '<repo_sync_root>/.trash/' by external/web AI agents
        by moving them into Google Drive's native 30-day Trash via transport.trash_file().
        """
        trash_dir_rel = self._repo_rel(".trash")
        flushed_ids: List[str] = []
        for entry in self.transport.list_files(trash_dir_rel, recursive=False):
            if self.transport.trash_file(entry.rel_path, file_id=entry.file_id):
                flushed_ids.append(entry.file_id)
        return flushed_ids

    def _gc_unreferenced_history_files(
        self, meta: Dict[str, Any], scan_physical: bool = True
    ) -> List[str]:
        """
        Garbage-collect any file in repo_sync/.history/ that is no longer referenced by any branch
        in meta['branch_files'], moving it to Google Drive's native 30-day Trash (or sandbox .trash/).
        Also reconciles any physical files found inside repo_sync/.history/ that are unreferenced.
        """
        branch_files_map: Dict[str, Dict[str, str]] = meta.setdefault("branch_files", {})
        branches_meta: Dict[str, Any] = meta.get("branches", {})
        if isinstance(branches_meta, dict):
            for b_name, b_info in branches_meta.items():
                is_auto = isinstance(b_info, dict) and bool(b_info.get("auto_discovered"))
                if is_auto or b_name not in branch_files_map:
                    b_snap, _, _, _ = self._scan_remote_branch_with_dirs(b_name)
                    branch_files_map[b_name] = {
                        rel_p: r_ent.effective_file_id() for rel_p, r_ent in b_snap.items()
                    }
                    if isinstance(b_info, dict):
                        b_info.pop("auto_discovered", None)
        history_files: Dict[str, str] = meta.setdefault("history_files", {})
        hist_dir_rel = self._repo_rel(".history")

        if scan_physical:
            for entry in self.transport.list_files(hist_dir_rel, recursive=False):
                if entry.is_dir or entry.skipped_reason:
                    continue
                if entry.file_id not in history_files:
                    history_files[entry.file_id] = entry.rel_path

        orphan_ids = compute_orphan_history_file_ids(history_files, branch_files_map)
        trashed_ids: List[str] = []
        for fid in orphan_ids:
            rel_p = history_files.get(fid)
            if rel_p and self.transport.trash_file(rel_p, file_id=fid):
                trashed_ids.append(fid)
            history_files.pop(fid, None)
        return trashed_ids

    def _collect_local_snapshot(
        self, state: Dict[str, Any], now_ns: Optional[int] = None
    ) -> Tuple[Dict[str, FileEntry], Dict[str, Path], List[str]]:
        """
        Collect local file snapshot across all configured sync_spaces.
        Applies the 2-second write-stabilization guard and mtime+size FingerprintCache.
        """
        current_ns = now_ns if now_ns is not None else time.time_ns()
        fp_cache: Dict[str, Dict[str, Any]] = state.setdefault("fingerprint_cache", {})
        local_snap: Dict[str, FileEntry] = {}
        local_path_map: Dict[str, Path] = {}
        stabilizing: List[str] = []

        for spec in self.config.sync_spaces:
            files_map = collect_space_local_files_with_stat(
                spec,
                project_root=self.project_root,
                file_space_manager=self._file_space_manager,
            )
            threshold_bytes = spec.large_file_threshold_mb * 1024 * 1024

            sandbox_root_real = (
                Path(os.path.realpath(str(self.config.sandbox_dir)))
                if self.config.sandbox_dir
                else None
            )
            for remote_rel, (abs_path, pre_mtime_ns, pre_size) in files_map.items():
                if is_sensitive_credential_path(
                    abs_path, self.project_root, config=self.config
                ):
                    continue
                if sandbox_root_real is not None:
                    try:
                        Path(os.path.realpath(str(abs_path))).relative_to(sandbox_root_real)
                        continue
                    except ValueError:
                        pass
                if pre_mtime_ns is not None and pre_size is not None:
                    mtime_ns = pre_mtime_ns
                    sz = pre_size
                else:
                    try:
                        st = abs_path.stat()
                    except OSError:
                        continue
                    mtime_ns = int(st.st_mtime_ns)
                    sz = int(st.st_size)

                if threshold_bytes > 0 and sz >= threshold_bytes:
                    if (current_ns - mtime_ns) < STABILIZATION_WINDOW_NS:
                        stabilizing.append(remote_rel)
                        continue
                    self._append_log(
                        "large_file_warning",
                        {
                            "space": spec.space,
                            "rel_path": remote_rel,
                            "size_bytes": sz,
                            "threshold_bytes": threshold_bytes,
                        },
                    )

                cache_key = abs_path.as_posix()
                cached_fp = fp_cache.get(cache_key)
                if (
                    cached_fp
                    and cached_fp.get("mtime_ns") == mtime_ns
                    and cached_fp.get("size") == sz
                    and cached_fp.get("md5")
                ):
                    md5_hex = str(cached_fp["md5"])
                    sha_hex = str(cached_fp.get("sha256") or "")
                else:
                    try:
                        md5_hex, sha_hex, sz = compute_local_hashes(abs_path)
                    except OSError:
                        continue
                    fp_cache[cache_key] = {
                        "mtime_ns": mtime_ns,
                        "size": sz,
                        "md5": md5_hex,
                        "sha256": sha_hex,
                    }

                local_snap[remote_rel] = FileEntry(
                    rel_path=remote_rel,
                    md5=md5_hex,
                    sha256=sha_hex,
                    size=sz,
                    mtime_ns=mtime_ns,
                )
                local_path_map[remote_rel] = abs_path

        return local_snap, local_path_map, sorted(set(stabilizing))

    def _scan_remote_branch_with_dirs(
        self, branch: str
    ) -> Tuple[
        Dict[str, FileEntry],
        Dict[str, RemoteEntry],
        Dict[str, str],
        Dict[str, Dict[str, str]],
    ]:
        branch_dir = self._repo_rel(branch)
        prefix = f"{branch_dir}/"
        entries = self.transport.list_files(branch_dir, recursive=True)
        branch_dir_ent = self.transport.get_entry(branch_dir)
        dir_ids: Dict[str, str] = {}
        dir_meta: Dict[str, Dict[str, str]] = {}
        if branch_dir_ent is not None and branch_dir_ent.file_id:
            dir_ids[branch_dir_ent.file_id] = ""
            dir_meta[branch_dir_ent.file_id] = {
                "name": branch_dir_ent.name,
                "parent_id": branch_dir_ent.parent_id,
            }

        snap: Dict[str, FileEntry] = {}
        raw_map: Dict[str, RemoteEntry] = {}

        for ent in entries:
            if ent.skipped_reason:
                continue
            if not ent.rel_path.startswith(prefix):
                continue
            rel_p = ent.rel_path[len(prefix) :]
            if not rel_p or rel_p in BRANCH_INTERNAL_SYSTEM_NAMES:
                continue
            if ent.is_dir:
                dir_ids[ent.file_id] = rel_p
                dir_meta[ent.file_id] = {
                    "name": ent.name,
                    "parent_id": ent.parent_id,
                }
                continue
            raw_map[rel_p] = ent
            snap[rel_p] = FileEntry(
                rel_path=rel_p,
                md5=ent.md5,
                sha256="",
                size=ent.size,
                mtime_ns=ent.mtime_ns,
                file_id=ent.file_id,
                is_shortcut=ent.is_shortcut,
                target_file_id=ent.target_file_id,
            )
        return snap, raw_map, dir_ids, dir_meta

    def _persist_active_branch_to_config(self, target_branch: str) -> None:
        """
        Persist updated active_branch into config://gdrive-support/ while preserving all existing
        repo_sync fields. In isolated test environments or when sandbox_dir is active, skip global write.
        """
        if bool(self.config.sandbox_dir):
            return
        repo_sync_block: Dict[str, Any] = {
            "enable": bool(self.config.repo_sync_enabled),
            "repo_sync_root": str(self.config.repo_sync_root or DEFAULT_REPO_SYNC_ROOT),
            "active_branch": target_branch,
            "auto_sync": bool(self.config.auto_sync),
            "poll_interval_sec": float(self.config.poll_interval_sec),
            "pull_delete_default": bool(self.config.pull_delete_default),
            "push_delete_default": bool(self.config.push_delete_default),
        }
        try:
            loaded_cfg = core_config.get("gdrive-support")
            if isinstance(loaded_cfg, dict) and isinstance(
                loaded_cfg.get("repo_sync"), dict
            ):
                merged = dict(loaded_cfg["repo_sync"])
                merged["active_branch"] = target_branch
                repo_sync_block = merged
            core_config.set("gdrive-support", "repo_sync", repo_sync_block)
        except Exception as exc:
            self._append_log(
                "persist_active_branch_skipped",
                {"branch": target_branch, "reason": str(exc)},
            )

    def _resolve_remote_rel_to_local_abs(self, remote_rel_path: str) -> Optional[Path]:
        """
        Resolve a branch-relative remote path to an absolute local path inside a registered sync_space,
        verifying that the resolved target resides within project_root AND the space's include_roots.
        """
        for spec in self.config.sync_spaces:
            local_rel = spec.remote_to_local_rel(remote_rel_path)
            if local_rel is not None:
                cand = (self.project_root / local_rel).resolve()
                if not spec.is_local_abs_allowed(cand, self.project_root):
                    continue
                if is_sensitive_credential_path(
                    cand, self.project_root, config=self.config
                ):
                    continue
                return cand
        return None
