"""
SyncCoordinator: Inter-process locked orchestration of cloud repository initialization,
Shortcut delta branches, Copy-on-Write (.history/) & unreferenced garbage collection (.trash/),
incremental state ledger persistence, 4-stage bidirectional synchronization under 'repo_sync/',
and local-cache-driven soft-merge / soft-remove of the root README.md.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from dataclasses import asdict, dataclass, field
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
    GDriveTransportError,
    SyncSpaceSpec,
    collect_space_local_files,
    is_sensitive_credential_path,
    normalize_remote_rel_path,
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
    FOLDER_MIME_TYPE,
    AbstractSyncTransport,
    ChangeRecord,
    RemoteEntry,
    compute_local_hashes,
)

DEFAULT_REPO_SYNC_ROOT = "repo"
REPO_SYNC_ROOT_PREFIX = DEFAULT_REPO_SYNC_ROOT
REPO_CONFIG_FILENAME = ".yscb_gdrive.json"
REPO_README_FILENAME = "README.md"
ROOT_README_BEGIN_MARKER = "<!-- === YSCB GDRIVE REPO_SYNC BEGIN === -->"
ROOT_README_END_MARKER = "<!-- === YSCB GDRIVE REPO_SYNC END === -->"

SYSTEM_NAMES = {
    REPO_CONFIG_FILENAME,
    REPO_README_FILENAME,
    ".history",
    ".trash",
}
STABILIZATION_WINDOW_NS = 2_000_000_000  # 2.0 seconds
MAX_LOG_BYTES = 2 * 1024 * 1024  # 2 MB
PARALLEL_TRANSFER_WORKERS = 8


def build_managed_readme_content(repo_sync_root: str = DEFAULT_REPO_SYNC_ROOT) -> str:
    """Generate the standard README.md placed at <root_folder_id>/<repo_sync_root>/README.md."""
    norm_root = normalize_remote_rel_path(repo_sync_root) or DEFAULT_REPO_SYNC_ROOT
    return (
        f"# YS-Codebase Google Drive Managed Sync Repository (`{norm_root}/`)\n\n"
        "> **[!IMPORTANT] 自動化託管聲明**\n"
        f"> 本 `{norm_root}/` 資料夾由 `yscb module:gdrive-support` (`yscb gdrive`) 自動管理。\n\n"
        "## 1. 目錄結構規範\n\n"
        "- `.yscb_gdrive.json`：倉庫身分證、分支註冊表與跨分支引用索引（**請勿手動刪除或修改**）。\n"
        "- `main/`：完整主幹分支（存放 100% 真實資料夾與最新完整實體檔案）。\n"
        "- `<branch>/`（如 `v1.0`, `v1.5`）：差量版本分支（真實資料夾骨架 + 差異實體檔 + 指向未修改檔案之 Google Drive Shortcut）。\n"
        "- `.history/`：存放被更新替換下來、但仍受舊分支 Shortcut 引用之凍結版本實體檔（當無任何分支引用時自動移入 Google Drive 原生 30 天垃圾桶）。\n"
        "- `.trash/`：專供無原生垃圾桶權限之外部/網頁版 AI 搬移待刪除檔案的暫存緩衝區（**注意：本地 `yscb gdrive` 同步或分支操作時會自動清空 `.trash/` 內的所有項目並移入 Google Drive 原生 30 天垃圾桶，切勿將 `.trash/` 當作長期備份資料夾！**）。\n\n"
        "## 2. 人類與外部/網頁版 AI Agent 操作注意事項\n\n"
        f"1. **修改前先確認目標分支（直接改 `main/` vs. 新增雲端分支 `{norm_root}/<new_branch>/`）**：外部 Agent 於寫入前應先向使用者確認要直接更新 `main/` 或是建立新分支 `{norm_root}/<new_branch>/`（本地 `yscb gdrive` 支援自動發現雲端新建之分支資料夾，無須手動修改 `.yscb_gdrive.json`）。\n"
        f"2. **更新既有檔案時**：若無法直接覆寫原檔案版本（例如透過網頁版 Gemini 操作），請**先將原檔案或原 Shortcut 移動至 `{norm_root}/.trash/` 資料夾，再於原路徑建立更新後的檔案**（本地同步時會自動幫你把 `{norm_root}/.trash/` 內的舊檔轉移至 Google Drive 原生 30 天垃圾桶）。\n"
        "3. **保持原檔案類型**：請直接上傳/建立原始檔案格式（如 `.md`, `.json`, `.py`, `.xlsx`, `.pdf`），勿轉換為雲端專屬線上文件格式。\n"
        "4. **切勿直接修改 `.history/` 內之檔案**：`.history/` 專供保護歷史分支版本凍結完整性。\n"
    )


def build_root_readme_managed_block(repo_sync_root: str = DEFAULT_REPO_SYNC_ROOT) -> str:
    """Generate the managed block injected into the top-level <root_folder_id>/README.md when repo_sync.enable is True."""
    norm_root = normalize_remote_rel_path(repo_sync_root) or DEFAULT_REPO_SYNC_ROOT
    return (
        f"{ROOT_README_BEGIN_MARKER}\n"
        f"## YS-Codebase Cloud Root & `{norm_root}/` Managed Notice (`yscb module:gdrive-support`)\n\n"
        f"- **純雲端自由儲存區 (`<root>/*`，不含 `{norm_root}/`)**：\n"
        f"  - 位於本根目錄（`{norm_root}/` 以外）的所有資料夾與檔案屬於**不拉到本地自動同步之純雲端儲存區**，供開發者或 Agent 透過原子指令（`yscb gdrive ls / get / put / mkdir / rm`）按需單點存取。\n"
        f"- **受控分支同步倉 (`<root>/{norm_root}/`)**：\n"
        f"  - `{norm_root}/` 子目錄目前已啟用（`repo_sync.enable: true`），由 `yscb gdrive` 三方狀態機與 Shortcut 分支機制自動納管。詳細操作規範請參閱 `{norm_root}/README.md`。\n"
        f"{ROOT_README_END_MARKER}"
    )


def merge_root_readme_block(
    existing_text: str,
    managed_block: Optional[str] = None,
    *,
    managed_body: str = "",
    repo_sync_root: str = DEFAULT_REPO_SYNC_ROOT,
) -> str:
    """
    Soft-merge the YSCB managed repo_sync block into top-level README.md content.
    Preserves all user-authored text outside the BEGIN/END markers.
    """
    block = (
        managed_block
        or managed_body
        or build_root_readme_managed_block(repo_sync_root=repo_sync_root)
    ).strip()
    if not existing_text or not existing_text.strip():
        return block + "\n"

    begin_idx = existing_text.find(ROOT_README_BEGIN_MARKER)
    end_idx = existing_text.find(ROOT_README_END_MARKER)
    if begin_idx != -1 and end_idx != -1 and end_idx >= begin_idx:
        end_pos = end_idx + len(ROOT_README_END_MARKER)
        before = existing_text[:begin_idx].rstrip()
        after = existing_text[end_pos:].lstrip()
        parts = [p for p in (before, block, after) if p]
        return "\n\n".join(parts) + "\n"

    cleaned = existing_text.rstrip()
    return f"{cleaned}\n\n{block}\n"


def strip_root_readme_block(existing_text: str) -> str:
    """
    Soft-remove the YSCB managed repo_sync block from top-level README.md content.
    Returns the remaining user-authored text (empty string if nothing remains).
    """
    if not existing_text:
        return ""
    begin_idx = existing_text.find(ROOT_README_BEGIN_MARKER)
    end_idx = existing_text.find(ROOT_README_END_MARKER)
    if begin_idx == -1 or end_idx == -1 or end_idx < begin_idx:
        return existing_text

    end_pos = end_idx + len(ROOT_README_END_MARKER)
    before = existing_text[:begin_idx].rstrip()
    after = existing_text[end_pos:].lstrip()
    if before and after:
        return f"{before}\n\n{after}\n"
    if before:
        return f"{before}\n"
    if after:
        return f"{after}\n"
    return ""


def reconcile_root_readme_state(
    config: GDriveConfig,
    transport: AbstractSyncTransport,
    readme_state_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Check local cache for the last known 'repo_sync.enable' state for this target root.
    Only when a state transition is detected (or first initialization with enable=True)
    does it inspect/update the cloud root README.md:
    - enable == True: create root/README.md or soft-merge the managed block into existing root/README.md.
    - enable == False: if root/README.md exists, strip the managed block; if empty after stripping,
      move root/README.md to .trash/, otherwise write back the preserved user content (soft-remove).
    """
    state_file = (
        Path(readme_state_path).resolve()
        if readme_state_path is not None
        else Path(uri.resolve("storage.local://gdrive-support/readme_sync_state.json")).resolve()
    )
    target_key = (config.sandbox_dir or config.root_folder_id or "default").strip()
    if not target_key:
        return {"changed": False, "action": "skipped_unconfigured"}

    cache_data: Dict[str, Any] = {"states": {}}
    if state_file.is_file():
        try:
            loaded = vfs.read_json(state_file)
            if isinstance(loaded, dict) and isinstance(loaded.get("states"), dict):
                cache_data = loaded
        except Exception:
            cache_data = {"states": {}}

    states_map: Dict[str, Any] = cache_data.setdefault("states", {})
    curr_enabled = bool(config.repo_sync_enabled)
    prev_enabled = states_map.get(target_key)

    if prev_enabled is not None and bool(prev_enabled) == curr_enabled:
        return {"changed": False, "action": "noop_cached", "enabled": curr_enabled}

    if prev_enabled is None and not curr_enabled:
        states_map[target_key] = False
        state_file.parent.mkdir(parents=True, exist_ok=True)
        vfs.write_json(state_file, cache_data, indent=2, encoding="utf-8", atomic=True)
        return {"changed": False, "action": "initialized_disabled_cache", "enabled": False}

    action_taken = "none"
    existing_entry = transport.get_entry(REPO_README_FILENAME)

    with tempfile.TemporaryDirectory(prefix="yscb_root_readme_") as tmp_d:
        tmp_path = Path(tmp_d) / REPO_README_FILENAME
        existing_text = ""
        if existing_entry is not None and not existing_entry.is_dir:
            transport.download_file(REPO_README_FILENAME, tmp_path)
            existing_text = tmp_path.read_text(encoding="utf-8")

        if curr_enabled:
            merged_text = merge_root_readme_block(
                existing_text, repo_sync_root=config.repo_sync_root
            )
            tmp_path.write_text(merged_text, encoding="utf-8")
            in_place_id = (
                existing_entry.file_id
                if existing_entry is not None and not existing_entry.is_dir
                else None
            )
            transport.upload_file(
                tmp_path, REPO_README_FILENAME, in_place_file_id=in_place_id
            )
            action_taken = "soft_merged" if existing_text.strip() else "created"
        else:
            if existing_entry is not None and not existing_entry.is_dir:
                stripped = strip_root_readme_block(existing_text)
                if not stripped.strip():
                    transport.trash_file(REPO_README_FILENAME)
                    action_taken = "removed_to_trash"
                elif stripped != existing_text:
                    tmp_path.write_text(stripped, encoding="utf-8")
                    transport.upload_file(
                        tmp_path,
                        REPO_README_FILENAME,
                        in_place_file_id=existing_entry.file_id,
                    )
                    action_taken = "soft_removed"
                else:
                    action_taken = "unmanaged_preserved"
            else:
                action_taken = "absent_noop"

    states_map[target_key] = curr_enabled
    state_file.parent.mkdir(parents=True, exist_ok=True)
    vfs.write_json(state_file, cache_data, indent=2, encoding="utf-8", atomic=True)
    return {"changed": True, "action": action_taken, "enabled": curr_enabled}


@dataclass
class SyncReport:
    """Structured summary of a pull / push / sync execution."""

    branch: str
    mode: str
    pushed: List[str] = field(default_factory=list)
    pulled: List[str] = field(default_factory=list)
    deleted_local: List[str] = field(default_factory=list)
    deleted_remote: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    moved_to_history: List[str] = field(default_factory=list)
    gc_history_to_trash: List[str] = field(default_factory=list)
    skipped_stabilizing: List[str] = field(default_factory=list)
    exit_code: int = 0
    yielded: bool = False
    cache_hit_level: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class _BackgroundYieldRequested(Exception):
    """Internal signal raised when a background worker yields the lock to a foreground CLI."""


class SyncCoordinator:
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

    def _repo_rel(self, sub_path: str = "") -> str:
        """Return a remote path scoped inside '<repo_sync_prefix>/<sub_path>'."""
        norm_sub = normalize_remote_rel_path(sub_path)
        if not norm_sub:
            return self.repo_sync_prefix
        return f"{self.repo_sync_prefix}/{norm_sub}"

    def _precreate_remote_dirs(self, remote_file_paths: List[str]) -> List[RemoteEntry]:
        """
        Pre-create all ancestor parent directories sequentially on the main thread
        sorted by path depth before dispatching concurrent worker threads.
        """
        parents: Set[str] = set()
        for p in remote_file_paths:
            curr = Path(p).parent.as_posix()
            while curr not in ("", "."):
                parents.add(curr)
                curr = Path(curr).parent.as_posix()
        created: List[RemoteEntry] = []
        for parent_rel in sorted(parents, key=lambda x: (x.count("/"), x)):
            created.append(self.transport.mkdir(parent_rel))
        return created

    def reconcile_root_readme(self) -> Dict[str, Any]:
        """Reconcile the top-level root/README.md if repo_sync.enable changed vs local cache."""
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
        except Exception:
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
                except Exception:
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
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Local Ledger (sync_state.json & FingerprintCache)
    # ------------------------------------------------------------------

    def _load_local_state(self) -> Dict[str, Any]:
        if self.state_path.is_file():
            try:
                data = vfs.read_json(self.state_path)
                if isinstance(data, dict):
                    data.setdefault("branches", {})
                    data.setdefault("fingerprint_cache", {})
                    return data
            except Exception:
                pass
        return {"branches": {}, "fingerprint_cache": {}}

    def _save_local_state(self, state: Dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        vfs.write_json(self.state_path, state, indent=2, encoding="utf-8", atomic=True)

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
            if rel.startswith(f"{repo_prefix}/"):
                name = rel[len(repo_prefix) + 1 :]
            else:
                name = Path(rel).name
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
        """List all registered cloud branches under repo_sync/ and active_branch."""
        self.ensure_repo_sync_enabled()
        meta = self._ensure_remote_repo_initialized()
        return {
            "active_branch": self.config.active_branch,
            "default_branch": meta.get("default_branch", "main"),
            "branches": meta.get("branches", {}),
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
            self.transport.mkdir(dst_branch_prefix)
            src_entries = self.transport.list_files(src_branch_prefix, recursive=True)
            branch_files_map = meta.setdefault("branch_files", {})
            new_branch_map: Dict[str, str] = {}

            shortcut_tasks: List[Tuple[str, str, str]] = []
            dir_count = 0
            for entry in src_entries:
                if entry.skipped_reason:
                    continue
                sub_rel = entry.rel_path[len(src_branch_prefix) + 1 :]
                dst_rel = f"{dst_branch_prefix}/{sub_rel}"
                if entry.is_dir:
                    self.transport.mkdir(dst_rel)
                    dir_count += 1
                else:
                    target_fid = (
                        entry.target_file_id if entry.is_shortcut else entry.file_id
                    )
                    shortcut_tasks.append((sub_rel, dst_rel, target_fid))

            self._precreate_remote_dirs([dst_rel for _, dst_rel, _ in shortcut_tasks])

            shortcut_count = 0
            if shortcut_tasks:
                with ThreadPoolExecutor(max_workers=PARALLEL_TRANSFER_WORKERS) as pool:
                    fut_map = {
                        pool.submit(
                            self.transport.create_shortcut, target_fid, dst_rel
                        ): (sub_rel, target_fid)
                        for sub_rel, dst_rel, target_fid in shortcut_tasks
                    }
                    for fut in as_completed(fut_map):
                        fut.result()
                        sub_rel, target_fid = fut_map[fut]
                        new_branch_map[sub_rel] = target_fid
                        shortcut_count += 1
                new_branch_map = dict(sorted(new_branch_map.items()))

            now_iso = datetime.now(timezone.utc).isoformat()
            branches[norm_branch] = {
                "created_at": now_iso,
                "base_branch": source_branch,
            }
            branch_files_map[norm_branch] = new_branch_map
            self._write_remote_repo_meta(meta)
            state = self._load_local_state()
            state.pop("remote_repo_cache", None)
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
        Move repo_sync/<branch_name>/ to repo_sync/.trash/, remove it from .yscb_gdrive.json,
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

            self._trash_repo_item(self._repo_rel(norm_branch))
            branches.pop(norm_branch, None)
            meta.get("branch_files", {}).pop(norm_branch, None)

            gc_trashed = self._gc_unreferenced_history_files(meta)
            flushed_ext_trash = self._flush_external_repo_trash()
            self._write_remote_repo_meta(meta)

            state = self._load_local_state()
            state.get("branches", {}).pop(norm_branch, None)
            state.pop("remote_repo_cache", None)
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
        Atomically switch worktree from current active_branch to target_branch under repo_sync/.
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
            curr_remote_snap, _ = self._collect_remote_branch_snapshot(curr_branch)

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

            target_remote_snap, _ = self._collect_remote_branch_snapshot(norm_target)
            target_branch_state = (
                state.setdefault("branches", {})
                .setdefault(norm_target, {})
                .setdefault("files", {})
            )

            removed_orphans: List[str] = []
            pulled_files: List[str] = []

            try:
                old_tracked_paths = set(curr_base.keys())
                for rel_p in sorted(old_tracked_paths - set(target_remote_snap.keys())):
                    abs_local = local_path_map.get(rel_p) or self._resolve_remote_rel_to_local_abs(rel_p)
                    if abs_local and abs_local.is_file():
                        if backup:
                            self._create_conflict_backup(abs_local)
                        abs_local.unlink()
                        removed_orphans.append(rel_p)
                    target_branch_state.pop(rel_p, None)

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
                            self._create_conflict_backup(abs_local)
                        self.transport.download_file(
                            self._repo_rel(f"{norm_target}/{rel_p}"), abs_local
                        )
                        pulled_files.append(rel_p)

                    md5_hex, sha_hex, sz = compute_local_hashes(abs_local)
                    st = abs_local.stat()
                    new_base = FileEntry(
                        rel_path=rel_p,
                        md5=md5_hex,
                        sha256=sha_hex,
                        size=sz,
                        mtime_ns=int(st.st_mtime_ns),
                        file_id=rem_entry.effective_file_id(),
                        is_shortcut=rem_entry.is_shortcut,
                        target_file_id=rem_entry.target_file_id,
                    )
                    target_branch_state[rel_p] = new_base.to_dict()
            finally:
                state.pop("remote_repo_cache", None)
                self._save_local_state(state)

            self._persist_active_branch_to_config(norm_target)
            object.__setattr__(self.config, "active_branch", norm_target)

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
        Execute the 4-stage synchronization pipeline on repo_sync/<active_branch>/:
        Stage 1: Collect local, remote (via 3-level changes API cache), and baseline snapshots.
        Stage 2: Compute 8-state SyncActions via stateless reconciler.py.
        Stage 3: Execute transfers with single-file atomic Copy-on-Write (repo_sync/.history/),
                 cooperative foreground preemption yielding, incremental per-file state commit,
                 and reference-counted repo_sync/.history/ -> repo_sync/.trash/ garbage collection.
        Stage 4: Write structured sync.log entry and return SyncReport.
        """
        self.ensure_repo_sync_enabled()
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

            state = self._load_local_state()
            branch_state_dict = (
                state.setdefault("branches", {})
                .setdefault(branch, {})
                .setdefault("files", {})
            )
            baseline_snap: Dict[str, FileEntry] = {
                k: FileEntry.from_dict(v) for k, v in branch_state_dict.items()
            }

            # Stage 1: Snapshot collection (Local + 3-Level Incremental Remote Cache)
            local_snap, local_path_map, stabilizing = self._collect_local_snapshot(
                state, now_ns=now_ns
            )
            if background_worker and self.should_yield_background():
                self._save_local_state(state)
                return SyncReport(
                    branch=branch, mode=norm_mode, yielded=True, cache_hit_level=None
                )

            cache_hit_level = 2
            flushed_ext_stage1: List[str] = []
            inc_res = self._try_incremental_remote_cache(state, branch)
            if inc_res is not None:
                cache_hit_level, meta, remote_snap, raw_remote_entries = inc_res
                self.reconcile_root_readme()
            else:
                cache_hit_level = 2
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
                    self._save_local_state(state)
                    return SyncReport(
                        branch=branch,
                        mode=norm_mode,
                        yielded=True,
                        cache_hit_level=cache_hit_level,
                    )

                flushed_ext_stage1 = self._flush_external_repo_trash()
                remote_snap, raw_remote_entries, branch_dir_ids, branch_dir_meta = (
                    self._scan_remote_branch_with_dirs(branch)
                )

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
                    rel_p: r_ent.effective_file_id()
                    for rel_p, r_ent in remote_snap.items()
                }

                for other_b in meta.get("branches", {}).keys():
                    if other_b == branch:
                        continue
                    if background_worker and self.should_yield_background():
                        self._save_local_state(state)
                        return SyncReport(
                            branch=branch,
                            mode=norm_mode,
                            yielded=True,
                            cache_hit_level=cache_hit_level,
                        )
                    o_snap, o_raw, o_dirs, o_dmeta = (
                        self._scan_remote_branch_with_dirs(other_b)
                    )
                    cache_branches[other_b] = {
                        "raw_entries": {k: v.to_dict() for k, v in o_raw.items()},
                        "dir_ids": o_dirs,
                    }
                    all_folder_meta.update(o_dmeta)
                    branch_files_map_init[other_b] = {
                        rel_p: r_ent.effective_file_id()
                        for rel_p, r_ent in o_snap.items()
                    }

                self._populate_remote_repo_cache(
                    state=state,
                    page_token=start_token,
                    meta=meta,
                    cache_branches=cache_branches,
                    folder_meta=all_folder_meta,
                )

            if branch not in meta.get("branches", {}):
                raise GDriveConfigError(
                    f"Active branch '{branch}' is not registered in {self._repo_rel(REPO_CONFIG_FILENAME)}."
                )

            for stab_rel in stabilizing:
                local_snap.pop(stab_rel, None)
                remote_snap.pop(stab_rel, None)
                baseline_snap.pop(stab_rel, None)

            allow_pull_del = bool(effective_delete or self.config.pull_delete_default)
            allow_push_del = bool(effective_delete or self.config.push_delete_default)

            # Stage 2: Stateless three-way reconciliation
            actions = reconcile_three_way(
                local_snap=local_snap,
                remote_snap=remote_snap,
                baseline_snap=baseline_snap,
                mode=norm_mode,
                allow_pull_delete=allow_pull_del,
                allow_push_delete=allow_push_del,
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
                cache_hit_level=cache_hit_level,
            )
            if flushed_ext_stage1:
                report.gc_history_to_trash.extend(flushed_ext_stage1)

            branch_files_map: Dict[str, Dict[str, str]] = meta.setdefault(
                "branch_files", {}
            )
            prev_branch_files = dict(branch_files_map.get(branch) or {})
            curr_branch_files = {
                rel_p: r_ent.effective_file_id()
                for rel_p, r_ent in remote_snap.items()
            }
            branch_files_map[branch] = curr_branch_files
            history_files: Dict[str, str] = meta.setdefault("history_files", {})
            meta_dirty = bool(curr_branch_files != prev_branch_files)
            first_push_err: Optional[BaseException] = None
            first_pull_err: Optional[BaseException] = None

            # Stage 3: Execute actions with atomic per-file CoW + upload and try/finally state persistence
            try:
                push_tasks: List[
                    Tuple[
                        str,
                        Path,
                        str,
                        Optional[RemoteEntry],
                        FileEntry,
                        SyncActionType,
                        Optional[FileEntry],
                        Optional[FileEntry],
                    ]
                ] = []
                pull_tasks: List[Tuple[str, Path, str, FileEntry]] = []

                for act in actions:
                    if background_worker and self.should_yield_background():
                        report.yielded = True
                        break

                    rel_p = act.rel_path
                    remote_branch_rel = self._repo_rel(f"{branch}/{rel_p}")

                    if act.action == SyncActionType.IN_SYNC:
                        if act.local_entry and act.remote_entry:
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
                            branch_state_dict.pop(rel_p, None)
                            if rel_p in curr_branch_files:
                                curr_branch_files.pop(rel_p, None)
                                meta_dirty = True
                            self._update_cache_branch_entry(
                                state, branch, rel_p, None
                            )
                            self._save_local_state(state)
                        continue

                    if act.action == SyncActionType.CONFLICT:
                        continue

                    if act.action in (
                        SyncActionType.PUSH_NEW,
                        SyncActionType.PUSH_UPDATE,
                    ):
                        abs_local = local_path_map.get(
                            rel_p
                        ) or self._resolve_remote_rel_to_local_abs(rel_p)
                        if abs_local is None or not abs_local.is_file():
                            continue
                        existing_rem = raw_remote_entries.get(rel_p)
                        loc_ent = act.local_entry
                        assert loc_ent is not None
                        push_tasks.append(
                            (
                                rel_p,
                                abs_local,
                                remote_branch_rel,
                                existing_rem,
                                loc_ent,
                                act.action,
                                act.remote_entry,
                                act.baseline_entry,
                            )
                        )
                        continue

                    if act.action in (
                        SyncActionType.PULL_NEW,
                        SyncActionType.PULL_UPDATE,
                    ):
                        abs_local = local_path_map.get(
                            rel_p
                        ) or self._resolve_remote_rel_to_local_abs(rel_p)
                        if abs_local is None:
                            continue
                        if (
                            backup
                            and abs_local.is_file()
                            and act.action == SyncActionType.PULL_UPDATE
                        ):
                            if (
                                force
                                and act.local_entry
                                and act.baseline_entry
                                and act.local_entry.md5 != act.baseline_entry.md5
                            ):
                                self._create_conflict_backup(abs_local)

                        rem_ent = act.remote_entry
                        assert rem_ent is not None
                        pull_tasks.append(
                            (rel_p, abs_local, remote_branch_rel, rem_ent)
                        )
                        continue

                    if act.action == SyncActionType.DELETE_LOCAL:
                        abs_local = local_path_map.get(
                            rel_p
                        ) or self._resolve_remote_rel_to_local_abs(rel_p)
                        if abs_local and abs_local.is_file():
                            if backup:
                                self._create_conflict_backup(abs_local)
                            abs_local.unlink()
                        branch_state_dict.pop(rel_p, None)
                        self._save_local_state(state)
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
                                    remote_branch_rel, hist_rel
                                )
                                with self._meta_lock:
                                    history_files[existing_rem.file_id] = hist_rel
                                    report.moved_to_history.append(
                                        existing_rem.file_id
                                    )
                            else:
                                self._trash_repo_item(remote_branch_rel)
                        with self._meta_lock:
                            curr_branch_files.pop(rel_p, None)
                            meta_dirty = True
                        branch_state_dict.pop(rel_p, None)
                        self._update_cache_branch_entry(state, branch, rel_p, None)
                        self._save_local_state(state)
                        report.deleted_remote.append(rel_p)
                        continue

                if push_tasks and not report.yielded:
                    created_dirs = self._precreate_remote_dirs(
                        [
                            remote_branch_rel
                            for _, _, remote_branch_rel, _, _, _, _, _ in push_tasks
                        ]
                    )
                    self._update_cache_dirs(state, branch, created_dirs)
                    any_cow_needed = any(
                        existing_rem is not None
                        and not existing_rem.is_shortcut
                        and is_file_id_referenced_by_other_branches(
                            existing_rem.file_id, branch, branch_files_map
                        )
                        for _, _, _, existing_rem, _, _, _, _ in push_tasks
                    )
                    if any_cow_needed:
                        self.transport.mkdir(self._repo_rel(".history"))

                    def _upload_task(
                        rel_p_item: str,
                        abs_local_item: Path,
                        remote_branch_rel_item: str,
                        existing_rem_item: Optional[RemoteEntry],
                        act_type_item: SyncActionType,
                        rem_ent_item: Optional[FileEntry],
                        base_ent_item: Optional[FileEntry],
                    ) -> RemoteEntry:
                        nonlocal meta_dirty
                        if background_worker and self.should_yield_background():
                            raise _BackgroundYieldRequested()
                        if (
                            backup
                            and force
                            and existing_rem_item is not None
                            and act_type_item == SyncActionType.PUSH_UPDATE
                            and rem_ent_item
                            and base_ent_item
                            and rem_ent_item.md5 != base_ent_item.md5
                        ):
                            rem_bak = abs_local_item.with_name(
                                f"{abs_local_item.name}.remote_conflict.{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.bak"
                            )
                            self.transport.download_file(
                                remote_branch_rel_item, rem_bak
                            )

                        in_place_fid: Optional[str] = None
                        if existing_rem_item is not None:
                            if existing_rem_item.is_shortcut:
                                self._trash_repo_item(remote_branch_rel_item)
                                in_place_fid = None
                            else:
                                old_fid = existing_rem_item.file_id
                                with self._meta_lock:
                                    needs_cow = (
                                        is_file_id_referenced_by_other_branches(
                                            old_fid, branch, branch_files_map
                                        )
                                    )
                                if needs_cow:
                                    hist_dir_rel = self._repo_rel(".history")
                                    hist_rel = f"{hist_dir_rel}/{old_fid}_{Path(rel_p_item).name}"
                                    self.transport.move_file(
                                        remote_branch_rel_item, hist_rel
                                    )
                                    with self._meta_lock:
                                        history_files[old_fid] = hist_rel
                                        report.moved_to_history.append(old_fid)
                                        meta_dirty = True
                                    in_place_fid = None
                                else:
                                    in_place_fid = old_fid

                        return self.transport.upload_file(
                            abs_local_item,
                            remote_branch_rel_item,
                            in_place_file_id=in_place_fid,
                        )

                    with ThreadPoolExecutor(
                        max_workers=PARALLEL_TRANSFER_WORKERS
                    ) as pool:
                        fut_map = {
                            pool.submit(
                                _upload_task,
                                rel_p,
                                abs_local,
                                remote_branch_rel,
                                existing_rem,
                                act_type,
                                rem_ent,
                                base_ent,
                            ): (rel_p, loc_ent)
                            for (
                                rel_p,
                                abs_local,
                                remote_branch_rel,
                                existing_rem,
                                loc_ent,
                                act_type,
                                rem_ent,
                                base_ent,
                            ) in push_tasks
                        }
                        for fut in as_completed(fut_map):
                            rel_p, loc_ent = fut_map[fut]
                            if fut.cancelled():
                                continue
                            try:
                                uploaded = fut.result()
                            except _BackgroundYieldRequested:
                                report.yielded = True
                                continue
                            except BaseException as exc:
                                if first_push_err is None:
                                    first_push_err = exc
                                continue
                            with self._meta_lock:
                                curr_branch_files[rel_p] = uploaded.file_id
                                meta_dirty = True
                            new_base = FileEntry(
                                rel_path=rel_p,
                                md5=loc_ent.md5,
                                sha256=loc_ent.sha256,
                                size=loc_ent.size,
                                mtime_ns=loc_ent.mtime_ns,
                                file_id=uploaded.file_id,
                                is_shortcut=False,
                                target_file_id="",
                            )
                            branch_state_dict[rel_p] = new_base.to_dict()
                            self._update_cache_branch_entry(
                                state, branch, rel_p, uploaded
                            )
                            self._save_local_state(state)
                            report.pushed.append(rel_p)
                            if (
                                background_worker
                                and self.should_yield_background()
                            ):
                                report.yielded = True
                                for pending_fut in fut_map:
                                    if not pending_fut.done():
                                        pending_fut.cancel()
                                break
                    report.pushed.sort()
                    if first_push_err is not None:
                        raise first_push_err

                if pull_tasks and not report.yielded:

                    def _download_and_hash(
                        remote_branch_rel: str, abs_local: Path
                    ) -> Tuple[str, str, int, int]:
                        if background_worker and self.should_yield_background():
                            raise _BackgroundYieldRequested()
                        self.transport.download_file(remote_branch_rel, abs_local)
                        md5_hex, sha_hex, sz = compute_local_hashes(abs_local)
                        st = abs_local.stat()
                        return md5_hex, sha_hex, sz, int(st.st_mtime_ns)

                    with ThreadPoolExecutor(
                        max_workers=PARALLEL_TRANSFER_WORKERS
                    ) as pool:
                        fut_map = {
                            pool.submit(
                                _download_and_hash, remote_branch_rel, abs_local
                            ): (rel_p, rem_ent)
                            for rel_p, abs_local, remote_branch_rel, rem_ent in pull_tasks
                        }
                        for fut in as_completed(fut_map):
                            rel_p, rem_ent = fut_map[fut]
                            if fut.cancelled():
                                continue
                            try:
                                md5_hex, sha_hex, sz, mtime_ns = fut.result()
                            except _BackgroundYieldRequested:
                                report.yielded = True
                                continue
                            except BaseException as exc:
                                if first_pull_err is None:
                                    first_pull_err = exc
                                continue
                            new_base = FileEntry(
                                rel_path=rel_p,
                                md5=md5_hex,
                                sha256=sha_hex,
                                size=sz,
                                mtime_ns=mtime_ns,
                                file_id=rem_ent.effective_file_id(),
                                is_shortcut=rem_ent.is_shortcut,
                                target_file_id=rem_ent.target_file_id,
                            )
                            branch_state_dict[rel_p] = new_base.to_dict()
                            self._save_local_state(state)
                            report.pulled.append(rel_p)
                            if (
                                background_worker
                                and self.should_yield_background()
                            ):
                                report.yielded = True
                                for pending_fut in fut_map:
                                    if not pending_fut.done():
                                        pending_fut.cancel()
                                break
                    report.pulled.sort()
                    if first_pull_err is not None:
                        raise first_pull_err

                if not report.yielded:
                    if not (
                        cache_hit_level == 0
                        and not report.pushed
                        and not report.deleted_remote
                        and not report.moved_to_history
                    ):
                        gc_trashed = self._gc_unreferenced_history_files(
                            meta, scan_physical=(cache_hit_level == 2)
                        )
                        if gc_trashed:
                            report.gc_history_to_trash.extend(gc_trashed)
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
                self._save_local_state(state)

            self._append_log("run_sync", report.to_dict())
            return report
        finally:
            self._background_abort_check = None
            lock.release()

    # ------------------------------------------------------------------
    # Internal Snapshot & GC Helpers
    # ------------------------------------------------------------------

    def _trash_repo_item(self, remote_rel_path: str) -> bool:
        """
        Move an item inside <repo_sync_root>/ directly to Google Drive's native 30-day Trash
        (or sandbox .trash/ in LocalSandboxTransport) via transport.trash_file().
        """
        return self.transport.trash_file(remote_rel_path)

    def _flush_external_repo_trash(self) -> List[str]:
        """
        Auto-clean any items placed inside '<repo_sync_root>/.trash/' by external/web AI agents
        by moving them into Google Drive's native 30-day Trash via transport.trash_file().
        """
        trash_dir_rel = self._repo_rel(".trash")
        flushed_ids: List[str] = []
        for entry in self.transport.list_files(trash_dir_rel, recursive=False):
            if self.transport.trash_file(entry.rel_path):
                flushed_ids.append(entry.file_id)
        return flushed_ids

    def _gc_unreferenced_history_files(
        self, meta: Dict[str, Any], scan_physical: bool = True
    ) -> List[str]:
        """
        Inspect all files tracked in meta['history_files'] (and any physical entries under <repo_sync_root>/.history/
        when scan_physical is True). If a file_id is no longer referenced by any active branch in meta['branch_files'],
        move it from <repo_sync_root>/.history/ to Google Drive's native 30-day Trash.
        """
        history_files: Dict[str, str] = meta.setdefault("history_files", {})
        if scan_physical:
            hist_dir_rel = self._repo_rel(".history")
            for entry in self.transport.list_files(hist_dir_rel, recursive=False):
                if not entry.is_dir and entry.file_id not in history_files:
                    history_files[entry.file_id] = entry.rel_path

        if not history_files:
            return []

        branch_files_map: Dict[str, Dict[str, str]] = meta.get("branch_files", {})
        orphan_ids = compute_orphan_history_file_ids(
            set(history_files.keys()), branch_files_map
        )
        trashed_ids: List[str] = []
        for fid in orphan_ids:
            hist_rel = history_files.get(fid, "")
            if hist_rel and self.transport.get_entry(hist_rel) is not None:
                self._trash_repo_item(hist_rel)
            history_files.pop(fid, None)
            trashed_ids.append(fid)
        return trashed_ids

    def _collect_local_snapshot(
        self,
        state: Dict[str, Any],
        now_ns: Optional[int] = None,
    ) -> Tuple[Dict[str, FileEntry], Dict[str, Path], List[str]]:
        effective_now_ns = now_ns if now_ns is not None else time.time_ns()
        fp_cache: Dict[str, Dict[str, Any]] = state.setdefault(
            "fingerprint_cache", {}
        )
        local_snap: Dict[str, FileEntry] = {}
        local_path_map: Dict[str, Path] = {}
        stabilizing: List[str] = []

        for spec in self.config.sync_spaces:
            threshold_bytes = int(max(1, spec.large_file_threshold_mb)) * 1024 * 1024
            files_map = collect_space_local_files(
                spec,
                project_root=self.project_root,
                file_space_manager=self._file_space_manager,
            )
            for remote_rel, abs_path in files_map.items():
                if not abs_path.is_file():
                    continue
                st = abs_path.stat()
                mtime_ns = int(st.st_mtime_ns)
                sz = int(st.st_size)

                if (
                    sz >= threshold_bytes
                    and (effective_now_ns - mtime_ns) < STABILIZATION_WINDOW_NS
                ):
                    stabilizing.append(remote_rel)
                    continue

                cache_key = abs_path.as_posix()
                cached = fp_cache.get(cache_key)
                if (
                    isinstance(cached, dict)
                    and cached.get("mtime_ns") == mtime_ns
                    and cached.get("size") == sz
                    and cached.get("md5")
                    and cached.get("sha256")
                ):
                    md5_hex = str(cached["md5"])
                    sha_hex = str(cached["sha256"])
                else:
                    md5_hex, sha_hex, sz = compute_local_hashes(abs_path)
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

    def _collect_remote_branch_snapshot(
        self, branch: str
    ) -> Tuple[Dict[str, FileEntry], Dict[str, RemoteEntry]]:
        snap, raw_map, _, _ = self._scan_remote_branch_with_dirs(branch)
        return snap, raw_map

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
            if not rel_p or rel_p in SYSTEM_NAMES:
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

    def _populate_remote_repo_cache(
        self,
        state: Dict[str, Any],
        page_token: str,
        meta: Dict[str, Any],
        cache_branches: Dict[str, Any],
        folder_meta: Dict[str, Dict[str, str]],
    ) -> None:
        if not page_token:
            state.pop("remote_repo_cache", None)
            return

        repo_ent = self.transport.get_entry(self._repo_rel())
        hist_ent = self.transport.get_entry(self._repo_rel(".history"))
        trash_ent = self.transport.get_entry(self._repo_rel(".trash"))
        meta_ent = self.transport.get_entry(self._repo_rel(REPO_CONFIG_FILENAME))

        sys_folders = meta.get("system_folders") or {}
        known_folder_ids: Set[str] = set()
        for f_ent in (repo_ent, hist_ent, trash_ent):
            if f_ent is not None and f_ent.file_id:
                known_folder_ids.add(f_ent.file_id)
                folder_meta[f_ent.file_id] = {
                    "name": f_ent.name,
                    "parent_id": f_ent.parent_id,
                }
        for k in ("history_id", "trash_id", "main_id"):
            val = str(sys_folders.get(k) or "")
            if val:
                known_folder_ids.add(val)
        for b_data in cache_branches.values():
            for d_id in (b_data.get("dir_ids") or {}).keys():
                if d_id:
                    known_folder_ids.add(d_id)

        state["remote_repo_cache"] = {
            "root_folder_id": self.config.root_folder_id,
            "repo_sync_prefix": self.repo_sync_prefix,
            "page_token": page_token,
            "repo_folder_id": repo_ent.file_id if repo_ent else "",
            "history_folder_id": (
                hist_ent.file_id
                if hist_ent
                else str(sys_folders.get("history_id") or "")
            ),
            "trash_folder_id": (
                trash_ent.file_id
                if trash_ent
                else str(sys_folders.get("trash_id") or "")
            ),
            "meta_file_id": meta_ent.file_id if meta_ent else "",
            "meta_md5": meta_ent.md5 if meta_ent else "",
            "repo_meta": copy.deepcopy(meta),
            "branches": cache_branches,
            "known_folder_ids": sorted(known_folder_ids),
            "folder_meta": folder_meta,
        }

    def _update_cache_branch_entry(
        self,
        state: Dict[str, Any],
        branch: str,
        rel_p: str,
        entry: Optional[RemoteEntry],
    ) -> None:
        cache = state.get("remote_repo_cache")
        if not isinstance(cache, dict):
            return
        branches = cache.get("branches")
        if not isinstance(branches, dict) or branch not in branches:
            return
        raw_entries = branches[branch].setdefault("raw_entries", {})
        if entry is None:
            raw_entries.pop(rel_p, None)
        else:
            raw_entries[rel_p] = entry.to_dict()

    def _update_cache_dirs(
        self,
        state: Dict[str, Any],
        branch: str,
        dir_entries: List[RemoteEntry],
    ) -> None:
        cache = state.get("remote_repo_cache")
        if not isinstance(cache, dict):
            return
        branches = cache.get("branches")
        if not isinstance(branches, dict) or branch not in branches:
            return
        dir_ids = branches[branch].setdefault("dir_ids", {})
        folder_meta = cache.setdefault("folder_meta", {})
        known = set(cache.get("known_folder_ids") or [])
        branch_dir = self._repo_rel(branch)
        prefix = f"{branch_dir}/"

        for d_ent in dir_entries:
            if not d_ent.file_id:
                continue
            known.add(d_ent.file_id)
            folder_meta[d_ent.file_id] = {
                "name": d_ent.name,
                "parent_id": d_ent.parent_id,
            }
            if d_ent.rel_path == branch_dir:
                dir_ids[d_ent.file_id] = ""
            elif d_ent.rel_path.startswith(prefix):
                dir_ids[d_ent.file_id] = d_ent.rel_path[len(prefix) :]
        cache["known_folder_ids"] = sorted(known)

    def _update_cache_meta(
        self,
        state: Dict[str, Any],
        meta: Dict[str, Any],
        meta_entry: Optional[RemoteEntry],
    ) -> None:
        cache = state.get("remote_repo_cache")
        if not isinstance(cache, dict):
            return
        cache["repo_meta"] = copy.deepcopy(meta)
        if meta_entry is not None:
            cache["meta_file_id"] = meta_entry.file_id
            cache["meta_md5"] = meta_entry.md5

    def _try_incremental_remote_cache(
        self, state: Dict[str, Any], branch: str
    ) -> Optional[
        Tuple[int, Dict[str, Any], Dict[str, FileEntry], Dict[str, RemoteEntry]]
    ]:
        cache = state.get("remote_repo_cache")
        if not isinstance(cache, dict):
            return None
        if cache.get("root_folder_id") != self.config.root_folder_id:
            return None
        if cache.get("repo_sync_prefix") != self.repo_sync_prefix:
            return None
        page_token = str(cache.get("page_token") or "")
        if not page_token:
            return None
        repo_meta = cache.get("repo_meta")
        cache_branches = cache.get("branches")
        if not isinstance(repo_meta, dict) or not isinstance(cache_branches, dict):
            return None
        if branch not in cache_branches:
            return None
        for reg_b in (repo_meta.get("branches") or {}).keys():
            if reg_b not in cache_branches:
                return None

        try:
            changes, new_token = self.transport.list_changes(page_token)
        except GDriveTransportError:
            return None
        except Exception:
            return None

        if not new_token:
            return None

        meta_file_id = str(cache.get("meta_file_id") or "")
        meta_md5 = str(cache.get("meta_md5") or "")
        repo_folder_id = str(cache.get("repo_folder_id") or "")
        history_folder_id = str(cache.get("history_folder_id") or "")
        trash_folder_id = str(cache.get("trash_folder_id") or "")
        known_folder_ids: Set[str] = set(cache.get("known_folder_ids") or [])
        folder_meta: Dict[str, Dict[str, str]] = dict(
            cache.get("folder_meta") or {}
        )
        history_file_ids: Set[str] = set(
            (repo_meta.get("history_files") or {}).keys()
        )

        all_branch_dir_ids: Set[str] = set()
        file_id_to_branch_paths: Dict[str, List[Tuple[str, str]]] = {}
        target_id_to_shortcuts: Dict[str, List[Tuple[str, str]]] = {}

        for b_name, b_data in cache_branches.items():
            for d_id in (b_data.get("dir_ids") or {}).keys():
                if d_id:
                    all_branch_dir_ids.add(d_id)
            for rel_p, r_dict in (b_data.get("raw_entries") or {}).items():
                fid = str(r_dict.get("file_id") or "")
                if fid:
                    file_id_to_branch_paths.setdefault(fid, []).append(
                        (b_name, rel_p)
                    )
                if r_dict.get("is_shortcut"):
                    tid = str(r_dict.get("target_file_id") or "")
                    if tid:
                        target_id_to_shortcuts.setdefault(tid, []).append(
                            (b_name, rel_p)
                        )

        dedup_changes: Dict[str, ChangeRecord] = {}
        for ch in changes:
            if ch.file_id:
                dedup_changes[ch.file_id] = ch

        level1_ops: List[ChangeRecord] = []
        repo_prefix = self._repo_rel()

        for ch in dedup_changes.values():
            fid = ch.file_id
            ent = ch.entry

            # 1. Ignore system READMEs (root/README.md and <repo>/README.md)
            if not ch.removed and ent is not None:
                if ent.rel_path == self._repo_rel(REPO_README_FILENAME) or (
                    ch.name == REPO_README_FILENAME
                    and ch.parent_id
                    in (repo_folder_id, self.config.root_folder_id, "sandbox_root")
                ):
                    continue

            # 2. Check .yscb_gdrive.json
            if (
                fid == meta_file_id
                or (ch.name == REPO_CONFIG_FILENAME and ch.parent_id == repo_folder_id)
                or (
                    ent is not None
                    and ent.rel_path == self._repo_rel(REPO_CONFIG_FILENAME)
                )
            ):
                if (
                    not ch.removed
                    and ent is not None
                    and fid == meta_file_id
                    and meta_md5
                    and ent.md5 == meta_md5
                ):
                    continue
                return None

            # 3. Check folder items or known folders
            is_folder_change = (
                fid in known_folder_ids
                or fid in all_branch_dir_ids
                or ch.mime_type == FOLDER_MIME_TYPE
                or (ent is not None and ent.is_dir)
            )
            if is_folder_change:
                if ch.removed:
                    if fid in known_folder_ids or fid in all_branch_dir_ids:
                        return None
                    continue
                if fid in known_folder_ids or fid in all_branch_dir_ids:
                    fm = folder_meta.get(fid)
                    if (
                        fm is not None
                        and ch.name == fm.get("name")
                        and ch.parent_id == fm.get("parent_id")
                    ):
                        continue
                    return None
                if (
                    ch.parent_id in known_folder_ids
                    or ch.parent_id in all_branch_dir_ids
                    or (
                        ent is not None
                        and (
                            ent.rel_path == repo_prefix
                            or ent.rel_path.startswith(f"{repo_prefix}/")
                        )
                    )
                ):
                    return None
                continue

            # 4. Check external repo/.trash additions
            if ch.parent_id == trash_folder_id or (
                ent is not None
                and ent.rel_path.startswith(f"{self._repo_rel('.trash')}/")
            ):
                if not ch.removed:
                    return None
                continue

            # 5. Non-folder file/shortcut change
            if ch.removed:
                if fid in file_id_to_branch_paths or fid in target_id_to_shortcuts:
                    level1_ops.append(ch)
                continue

            if ent is None:
                continue

            if fid in file_id_to_branch_paths or fid in target_id_to_shortcuts:
                for b_name, rel_p in file_id_to_branch_paths.get(fid, []):
                    old_d = cache_branches[b_name]["raw_entries"].get(rel_p)
                    if not old_d:
                        return None
                    if ent.name != old_d.get("name") or ent.parent_id != old_d.get(
                        "parent_id"
                    ):
                        return None

                changed_vs_cache = False
                for b_name, rel_p in file_id_to_branch_paths.get(fid, []):
                    old_d = cache_branches[b_name]["raw_entries"][rel_p]
                    if (
                        old_d.get("md5") != ent.md5
                        or old_d.get("size") != ent.size
                        or old_d.get("target_file_id") != ent.target_file_id
                        or old_d.get("dangling_shortcut") != ent.dangling_shortcut
                    ):
                        changed_vs_cache = True
                for b_name, rel_p in target_id_to_shortcuts.get(fid, []):
                    sc_d = cache_branches[b_name]["raw_entries"][rel_p]
                    if (
                        sc_d.get("md5") != ent.md5
                        or sc_d.get("size") != ent.size
                        or sc_d.get("dangling_shortcut")
                    ):
                        changed_vs_cache = True

                if changed_vs_cache:
                    level1_ops.append(ch)
                continue

            if fid in history_file_ids:
                continue
            if ch.parent_id == history_folder_id:
                if not ch.removed:
                    return None
                continue

            if ch.parent_id in all_branch_dir_ids:
                for b_name, b_data in cache_branches.items():
                    b_dirs = b_data.get("dir_ids") or {}
                    if ch.parent_id in b_dirs:
                        sub_dir = b_dirs[ch.parent_id]
                        rel_p = (
                            f"{sub_dir}/{ent.name}".strip("/")
                            if sub_dir
                            else ent.name
                        )
                        if (
                            rel_p in SYSTEM_NAMES
                            or rel_p in (b_data.get("raw_entries") or {})
                        ):
                            return None
                level1_ops.append(ch)
                continue

            if ch.parent_id in known_folder_ids or (
                ent.rel_path == repo_prefix
                or ent.rel_path.startswith(f"{repo_prefix}/")
            ):
                return None

        # Apply Level 1 patches if any
        if level1_ops:
            for ch in level1_ops:
                fid = ch.file_id
                ent = ch.entry
                if ch.removed:
                    for b_name, rel_p in file_id_to_branch_paths.get(fid, []):
                        cache_branches[b_name]["raw_entries"].pop(rel_p, None)
                    for b_name, rel_p in target_id_to_shortcuts.get(fid, []):
                        cache_branches[b_name]["raw_entries"].pop(rel_p, None)
                    continue

                assert ent is not None
                if fid in file_id_to_branch_paths or fid in target_id_to_shortcuts:
                    for b_name, rel_p in file_id_to_branch_paths.get(fid, []):
                        old_d = cache_branches[b_name]["raw_entries"].get(rel_p)
                        if not old_d:
                            continue
                        if ent.skipped_reason:
                            cache_branches[b_name]["raw_entries"].pop(rel_p, None)
                        else:
                            patched = RemoteEntry(
                                rel_path=str(old_d.get("rel_path") or ""),
                                name=ent.name,
                                file_id=ent.file_id,
                                mime_type=ent.mime_type,
                                is_dir=False,
                                size=ent.size,
                                md5=ent.md5,
                                mtime_ns=ent.mtime_ns,
                                parent_id=ent.parent_id,
                                is_shortcut=ent.is_shortcut,
                                target_file_id=ent.target_file_id,
                                target_mime_type=ent.target_mime_type,
                                dangling_shortcut=ent.dangling_shortcut,
                                skipped_reason=ent.skipped_reason,
                            )
                            cache_branches[b_name]["raw_entries"][
                                rel_p
                            ] = patched.to_dict()

                    for b_name, rel_p in target_id_to_shortcuts.get(fid, []):
                        sc_d = cache_branches[b_name]["raw_entries"].get(rel_p)
                        if not sc_d:
                            continue
                        if ent.skipped_reason:
                            cache_branches[b_name]["raw_entries"].pop(rel_p, None)
                        else:
                            sc_d["md5"] = ent.md5
                            sc_d["size"] = ent.size
                            sc_d["mtime_ns"] = ent.mtime_ns
                            sc_d["target_mime_type"] = ent.mime_type
                            sc_d["dangling_shortcut"] = False
                            sc_d["skipped_reason"] = ""
                    continue

                for b_name, b_data in cache_branches.items():
                    b_dirs = b_data.get("dir_ids") or {}
                    if ch.parent_id in b_dirs:
                        sub_dir = b_dirs[ch.parent_id]
                        rel_p = (
                            f"{sub_dir}/{ent.name}".strip("/")
                            if sub_dir
                            else ent.name
                        )
                        if not ent.skipped_reason and rel_p not in SYSTEM_NAMES:
                            full_rel = self._repo_rel(f"{b_name}/{rel_p}")
                            added = RemoteEntry(
                                rel_path=full_rel,
                                name=ent.name,
                                file_id=ent.file_id,
                                mime_type=ent.mime_type,
                                is_dir=False,
                                size=ent.size,
                                md5=ent.md5,
                                mtime_ns=ent.mtime_ns,
                                parent_id=ent.parent_id,
                                is_shortcut=ent.is_shortcut,
                                target_file_id=ent.target_file_id,
                                target_mime_type=ent.target_mime_type,
                                dangling_shortcut=ent.dangling_shortcut,
                                skipped_reason=ent.skipped_reason,
                            )
                            b_data.setdefault("raw_entries", {})[
                                rel_p
                            ] = added.to_dict()

        cache["page_token"] = new_token
        meta_copy = copy.deepcopy(repo_meta)
        branch_files_map = meta_copy.setdefault("branch_files", {})
        for b_name, b_data in cache_branches.items():
            b_files: Dict[str, str] = {}
            for rel_p, r_dict in (b_data.get("raw_entries") or {}).items():
                r_ent = RemoteEntry.from_dict(r_dict)
                b_files[rel_p] = (
                    r_ent.target_file_id if r_ent.is_shortcut else r_ent.file_id
                )
            branch_files_map[b_name] = b_files
        cache["repo_meta"] = copy.deepcopy(meta_copy)

        active_raw_dict = cache_branches[branch].get("raw_entries") or {}
        remote_snap: Dict[str, FileEntry] = {}
        raw_remote_entries: Dict[str, RemoteEntry] = {}
        for rel_p, r_dict in active_raw_dict.items():
            r_ent = RemoteEntry.from_dict(r_dict)
            raw_remote_entries[rel_p] = r_ent
            remote_snap[rel_p] = FileEntry(
                rel_path=rel_p,
                md5=r_ent.md5,
                sha256="",
                size=r_ent.size,
                mtime_ns=r_ent.mtime_ns,
                file_id=r_ent.file_id,
                is_shortcut=r_ent.is_shortcut,
                target_file_id=r_ent.target_file_id,
            )

        hit_level = 1 if level1_ops else 0
        return hit_level, meta_copy, remote_snap, raw_remote_entries

    def _persist_active_branch_to_config(self, target_branch: str) -> None:
        """
        Persist updated active_branch into config://gdrive-support/ while preserving all existing
        repo_sync fields. In isolated test environments where core_config is unavailable, log and continue.
        """
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
        strictly enforcing that the resolved path stays within project_root and the space's include_roots,
        and never targets sensitive credential/token files.
        """
        for spec in self.config.sync_spaces:
            proj_rel = spec.remote_to_local_rel(remote_rel_path)
            if proj_rel is not None and proj_rel:
                candidate = (self.project_root / proj_rel).resolve()
                if spec.is_local_abs_allowed(
                    candidate, self.project_root
                ) and not is_sensitive_credential_path(candidate, self.project_root):
                    return candidate
        return None

    @staticmethod
    def _create_conflict_backup(local_path: Path) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        bak_path = local_path.with_name(f"{local_path.name}.conflict.{ts}.bak")
        shutil.copy2(local_path, bak_path)
        return bak_path
