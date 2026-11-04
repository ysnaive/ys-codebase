"""
SyncCoordinator: Inter-process locked orchestration of cloud repository initialization,
Shortcut delta branches, Copy-on-Write (.history/) & unreferenced garbage collection (.trash/),
incremental state ledger persistence, 4-stage bidirectional synchronization under 'repo_sync/',
and local-cache-driven soft-merge / soft-remove of the root README.md.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from core import config as core_config
from core import uri
from core import vfs
from core.platform.lock import InterProcessLock

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
from .transport import AbstractSyncTransport, RemoteEntry, compute_local_hashes

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
        else Path(uri.resolve("cache://gdrive-support/readme_sync_state.json")).resolve()
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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
            else Path(uri.resolve("cache://gdrive-support/sync_state.json")).resolve()
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
            else Path(uri.resolve("cache://gdrive-support/readme_sync_state.json")).resolve()
        )
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

    def _precreate_remote_dirs(self, remote_file_paths: List[str]) -> None:
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
        for parent_rel in sorted(parents, key=lambda x: (x.count("/"), x)):
            self.transport.mkdir(parent_rel)

    def reconcile_root_readme(self) -> Dict[str, Any]:
        """Reconcile the top-level root/README.md if repo_sync.enable changed vs local cache."""
        return reconcile_root_readme_state(
            config=self.config,
            transport=self.transport,
            readme_state_path=self.readme_state_path,
        )

    # ------------------------------------------------------------------
    # Lock & Logging Helpers
    # ------------------------------------------------------------------

    def _acquire_lock(self, non_blocking: bool = False, timeout_sec: float = 30.0) -> InterProcessLock:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = InterProcessLock(str(self.lock_path))
        acquired = (
            lock.acquire(blocking=False)
            if non_blocking
            else lock.acquire(blocking=True, timeout_sec=timeout_sec)
        )
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

    def _write_remote_repo_meta(self, meta: Dict[str, Any]) -> None:
        cfg_rel = self._repo_rel(REPO_CONFIG_FILENAME)
        with tempfile.TemporaryDirectory(prefix="yscb_gdrive_meta_") as tmp_d:
            local_tmp = Path(tmp_d) / REPO_CONFIG_FILENAME
            local_tmp.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.transport.upload_file(local_tmp, cfg_rel)

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
    ) -> SyncReport:
        """
        Execute the 4-stage synchronization pipeline on repo_sync/<active_branch>/:
        Stage 1: Collect local, remote, and baseline snapshots (with <2.0s stabilization filter).
        Stage 2: Compute 8-state SyncActions via stateless reconciler.py.
        Stage 3: Execute transfers with Copy-on-Write (repo_sync/.history/), incremental per-file state commit,
                 and reference-counted repo_sync/.history/ -> repo_sync/.trash/ garbage collection.
        Stage 4: Write structured sync.log entry and return SyncReport.
        """
        self.ensure_repo_sync_enabled()
        norm_mode = (mode or "sync").strip().lower()
        if norm_mode not in ("sync", "pull", "push"):
            raise GDriveConfigError(f"Unsupported sync mode: '{mode}'")

        lock = self._acquire_lock(non_blocking=non_blocking_lock)
        try:
            meta = self._ensure_remote_repo_initialized()
            branch = self.config.active_branch
            if branch not in meta.get("branches", {}):
                raise GDriveConfigError(
                    f"Active branch '{branch}' is not registered in {self._repo_rel(REPO_CONFIG_FILENAME)}."
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

            # Stage 1: Snapshot collection
            local_snap, local_path_map, stabilizing = self._collect_local_snapshot(
                state, now_ns=now_ns
            )
            remote_snap, raw_remote_entries = self._collect_remote_branch_snapshot(branch)

            for stab_rel in stabilizing:
                local_snap.pop(stab_rel, None)
                remote_snap.pop(stab_rel, None)
                baseline_snap.pop(stab_rel, None)

            allow_pull_del = bool(delete or self.config.pull_delete_default)
            allow_push_del = bool(delete or self.config.push_delete_default)

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
            )

            branch_files_map: Dict[str, Dict[str, str]] = meta.setdefault(
                "branch_files", {}
            )
            prev_branch_files = dict(branch_files_map.get(branch) or {})
            curr_branch_files = {
                rel_p: r_ent.effective_file_id()
                for rel_p, r_ent in remote_snap.items()
            }
            branch_files_map[branch] = curr_branch_files
            for other_b in meta.get("branches", {}).keys():
                if other_b != branch:
                    other_snap, _ = self._collect_remote_branch_snapshot(other_b)
                    branch_files_map[other_b] = {
                        rel_p: r_ent.effective_file_id()
                        for rel_p, r_ent in other_snap.items()
                    }

            history_files: Dict[str, str] = meta.setdefault("history_files", {})
            meta_dirty = bool(curr_branch_files != prev_branch_files)

            # Stage 3: Execute actions with try/finally incremental state persistence
            try:
                push_tasks: List[Tuple[str, Path, str, Optional[str], FileEntry]] = []
                pull_tasks: List[Tuple[str, Path, str, FileEntry]] = []

                for act in actions:
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
                            self._save_local_state(state)
                        continue

                    if act.action == SyncActionType.CONFLICT:
                        continue

                    if act.action in (SyncActionType.PUSH_NEW, SyncActionType.PUSH_UPDATE):
                        abs_local = local_path_map.get(rel_p) or self._resolve_remote_rel_to_local_abs(rel_p)
                        if abs_local is None or not abs_local.is_file():
                            continue

                        existing_rem = raw_remote_entries.get(rel_p)
                        if (
                            backup
                            and force
                            and existing_rem is not None
                            and act.action == SyncActionType.PUSH_UPDATE
                            and act.remote_entry
                            and act.baseline_entry
                            and act.remote_entry.md5 != act.baseline_entry.md5
                        ):
                            rem_bak = abs_local.with_name(
                                f"{abs_local.name}.remote_conflict.{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.bak"
                            )
                            self.transport.download_file(remote_branch_rel, rem_bak)

                        in_place_fid: Optional[str] = None

                        if existing_rem is not None:
                            if existing_rem.is_shortcut:
                                self._trash_repo_item(remote_branch_rel)
                                in_place_fid = None
                            else:
                                old_fid = existing_rem.file_id
                                if is_file_id_referenced_by_other_branches(
                                    old_fid, branch, branch_files_map
                                ):
                                    hist_dir_rel = self._repo_rel(".history")
                                    self.transport.mkdir(hist_dir_rel)
                                    hist_rel = f"{hist_dir_rel}/{old_fid}_{Path(rel_p).name}"
                                    self.transport.move_file(remote_branch_rel, hist_rel)
                                    history_files[old_fid] = hist_rel
                                    report.moved_to_history.append(old_fid)
                                    meta_dirty = True
                                    in_place_fid = None
                                else:
                                    in_place_fid = old_fid

                        loc_ent = act.local_entry
                        assert loc_ent is not None
                        push_tasks.append(
                            (rel_p, abs_local, remote_branch_rel, in_place_fid, loc_ent)
                        )
                        continue

                    if act.action in (SyncActionType.PULL_NEW, SyncActionType.PULL_UPDATE):
                        abs_local = local_path_map.get(rel_p) or self._resolve_remote_rel_to_local_abs(rel_p)
                        if abs_local is None:
                            continue
                        if backup and abs_local.is_file() and act.action == SyncActionType.PULL_UPDATE:
                            if force and act.local_entry and act.baseline_entry and act.local_entry.md5 != act.baseline_entry.md5:
                                self._create_conflict_backup(abs_local)

                        rem_ent = act.remote_entry
                        assert rem_ent is not None
                        pull_tasks.append((rel_p, abs_local, remote_branch_rel, rem_ent))
                        continue

                    if act.action == SyncActionType.DELETE_LOCAL:
                        abs_local = local_path_map.get(rel_p) or self._resolve_remote_rel_to_local_abs(rel_p)
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
                            if not existing_rem.is_shortcut and is_file_id_referenced_by_other_branches(
                                existing_rem.file_id, branch, branch_files_map
                            ):
                                hist_dir_rel = self._repo_rel(".history")
                                self.transport.mkdir(hist_dir_rel)
                                hist_rel = f"{hist_dir_rel}/{existing_rem.file_id}_{Path(rel_p).name}"
                                self.transport.move_file(remote_branch_rel, hist_rel)
                                history_files[existing_rem.file_id] = hist_rel
                                report.moved_to_history.append(existing_rem.file_id)
                            else:
                                self._trash_repo_item(remote_branch_rel)
                        curr_branch_files.pop(rel_p, None)
                        meta_dirty = True
                        branch_state_dict.pop(rel_p, None)
                        self._save_local_state(state)
                        report.deleted_remote.append(rel_p)
                        continue

                if push_tasks:
                    self._precreate_remote_dirs(
                        [remote_branch_rel for _, _, remote_branch_rel, _, _ in push_tasks]
                    )
                    first_push_err: Optional[BaseException] = None
                    with ThreadPoolExecutor(max_workers=PARALLEL_TRANSFER_WORKERS) as pool:
                        fut_map = {
                            pool.submit(
                                self.transport.upload_file,
                                abs_local,
                                remote_branch_rel,
                                in_place_file_id=in_place_fid,
                            ): (rel_p, loc_ent)
                            for rel_p, abs_local, remote_branch_rel, in_place_fid, loc_ent in push_tasks
                        }
                        for fut in as_completed(fut_map):
                            rel_p, loc_ent = fut_map[fut]
                            try:
                                uploaded = fut.result()
                            except BaseException as exc:
                                if first_push_err is None:
                                    first_push_err = exc
                                continue
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
                            self._save_local_state(state)
                            report.pushed.append(rel_p)
                    report.pushed.sort()
                    if first_push_err is not None:
                        raise first_push_err

                if pull_tasks:
                    def _download_and_hash(
                        remote_branch_rel: str, abs_local: Path
                    ) -> Tuple[str, str, int, int]:
                        self.transport.download_file(remote_branch_rel, abs_local)
                        md5_hex, sha_hex, sz = compute_local_hashes(abs_local)
                        st = abs_local.stat()
                        return md5_hex, sha_hex, sz, int(st.st_mtime_ns)

                    first_pull_err: Optional[BaseException] = None
                    with ThreadPoolExecutor(max_workers=PARALLEL_TRANSFER_WORKERS) as pool:
                        fut_map = {
                            pool.submit(
                                _download_and_hash, remote_branch_rel, abs_local
                            ): (rel_p, rem_ent)
                            for rel_p, abs_local, remote_branch_rel, rem_ent in pull_tasks
                        }
                        for fut in as_completed(fut_map):
                            rel_p, rem_ent = fut_map[fut]
                            try:
                                md5_hex, sha_hex, sz, mtime_ns = fut.result()
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
                    report.pulled.sort()
                    if first_pull_err is not None:
                        raise first_pull_err

                gc_trashed = self._gc_unreferenced_history_files(meta)
                if gc_trashed:
                    report.gc_history_to_trash.extend(gc_trashed)
                    meta_dirty = True

                flushed_ext = self._flush_external_repo_trash()
                if flushed_ext:
                    report.gc_history_to_trash.extend(flushed_ext)

                if meta_dirty:
                    self._write_remote_repo_meta(meta)
            finally:
                self._save_local_state(state)

            self._append_log("run_sync", report.to_dict())
            return report
        finally:
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

    def _gc_unreferenced_history_files(self, meta: Dict[str, Any]) -> List[str]:
        """
        Inspect all files tracked in meta['history_files'] (and any physical entries under <repo_sync_root>/.history/).
        If a file_id is no longer referenced by any active branch in meta['branch_files'],
        move it from <repo_sync_root>/.history/ to Google Drive's native 30-day Trash.
        """
        history_files: Dict[str, str] = meta.setdefault("history_files", {})
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
        branch_dir = self._repo_rel(branch)
        prefix = f"{branch_dir}/"
        entries = self.transport.list_files(branch_dir, recursive=True)
        snap: Dict[str, FileEntry] = {}
        raw_map: Dict[str, RemoteEntry] = {}

        for ent in entries:
            if ent.is_dir or ent.skipped_reason:
                continue
            if not ent.rel_path.startswith(prefix):
                continue
            rel_p = ent.rel_path[len(prefix) :]
            if not rel_p or rel_p in SYSTEM_NAMES:
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
        return snap, raw_map

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
