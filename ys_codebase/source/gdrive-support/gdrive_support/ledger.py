"""
Local synchronization state ledger (sync_state.json + WAL journal) and remote_repo_cache maintenance mixin.
"""
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from core import vfs

from .config import GDriveConfig, normalize_remote_rel_path
from .transport import AbstractSyncTransport, RemoteEntry

REPO_CONFIG_FILENAME = ".yscb_gdrive.json"


class LocalStateLedgerMixin:
    """
    Manages sync_state.json, WAL journal (sync_state.journal.jsonl), FingerprintCache,
    and in-place updates to state['remote_repo_cache'].
    """

    config: GDriveConfig
    transport: AbstractSyncTransport
    repo_sync_prefix: str
    state_path: Path
    state_journal_path: Path

    def _repo_rel(self, sub_path: str = "") -> str:
        norm_sub = normalize_remote_rel_path(sub_path)
        if not norm_sub:
            return self.repo_sync_prefix
        return f"{self.repo_sync_prefix}/{norm_sub}"

    def _peek_persisted_active_branch(self) -> str:
        """
        Pure read-only inspection of active_branch from state_path without replaying or unlinking
        the WAL journal. Safe to call without holding sync.lock.
        """
        if not self.state_path.is_file():
            return ""
        try:
            data = vfs.read_json(self.state_path)
            if isinstance(data, dict):
                branch = normalize_remote_rel_path(str(data.get("active_branch") or ""))
                if branch and "/" not in branch:
                    return branch
        except (OSError, ValueError):
            pass
        return ""

    def _load_local_state(self) -> Dict[str, Any]:
        state: Dict[str, Any] = {"branches": {}, "fingerprint_cache": {}}
        if self.state_path.is_file():
            try:
                data = vfs.read_json(self.state_path)
                if isinstance(data, dict):
                    data.setdefault("branches", {})
                    data.setdefault("fingerprint_cache", {})
                    state = data
            except (OSError, ValueError):
                pass
        if self._replay_state_journal(state):
            self._save_local_state(state)
        return state

    def _save_local_state(self, state: Dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        vfs.write_json(self.state_path, state, indent=2, encoding="utf-8", atomic=True)
        try:
            self.state_journal_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _append_state_journal(self, record: Dict[str, Any]) -> None:
        try:
            self.state_journal_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
        except OSError:
            pass

    def _replay_state_journal(self, state: Dict[str, Any]) -> bool:
        if not self.state_journal_path.is_file():
            return False
        replayed = False
        try:
            raw_text = self.state_journal_path.read_text(encoding="utf-8")
        except OSError:
            return False

        branches_dict = state.setdefault("branches", {})
        fp_cache = state.setdefault("fingerprint_cache", {})
        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            op = rec.get("op")
            branch = str(rec.get("branch") or "")
            rel_path = str(rec.get("rel_path") or "")
            if not branch or not rel_path:
                continue
            b_files = branches_dict.setdefault(branch, {}).setdefault("files", {})
            if op == "upsert_file":
                base_entry = rec.get("base_entry")
                if isinstance(base_entry, dict):
                    b_files[rel_path] = base_entry
                    replayed = True
                cache_entry = rec.get("cache_entry")
                if isinstance(cache_entry, dict):
                    try:
                        self._update_cache_branch_entry(
                            state, branch, rel_path, RemoteEntry.from_dict(cache_entry)
                        )
                    except Exception:
                        pass
                fp_key = str(rec.get("fp_key") or "")
                fp_entry = rec.get("fp_entry")
                if fp_key and isinstance(fp_entry, dict):
                    fp_cache[fp_key] = fp_entry
            elif op == "delete_file":
                b_files.pop(rel_path, None)
                if rec.get("remove_from_cache"):
                    self._update_cache_branch_entry(state, branch, rel_path, None)
                replayed = True
        return replayed

    def _record_branch_file_upsert(
        self,
        state: Dict[str, Any],
        branch: str,
        rel_path: str,
        base_entry_dict: Dict[str, Any],
        cache_entry: Optional[RemoteEntry] = None,
        fp_key: Optional[str] = None,
        fp_entry: Optional[Dict[str, Any]] = None,
    ) -> None:
        state.setdefault("branches", {}).setdefault(branch, {}).setdefault("files", {})[
            rel_path
        ] = base_entry_dict
        if cache_entry is not None:
            self._update_cache_branch_entry(state, branch, rel_path, cache_entry)
        if fp_key and isinstance(fp_entry, dict):
            state.setdefault("fingerprint_cache", {})[fp_key] = fp_entry
        self._append_state_journal(
            {
                "op": "upsert_file",
                "branch": branch,
                "rel_path": rel_path,
                "base_entry": base_entry_dict,
                "cache_entry": cache_entry.to_dict() if cache_entry is not None else None,
                "fp_key": fp_key,
                "fp_entry": fp_entry,
            }
        )

    def _record_branch_file_delete(
        self,
        state: Dict[str, Any],
        branch: str,
        rel_path: str,
        remove_from_cache: bool = False,
    ) -> None:
        state.setdefault("branches", {}).setdefault(branch, {}).setdefault(
            "files", {}
        ).pop(rel_path, None)
        if remove_from_cache:
            self._update_cache_branch_entry(state, branch, rel_path, None)
        self._append_state_journal(
            {
                "op": "delete_file",
                "branch": branch,
                "rel_path": rel_path,
                "remove_from_cache": bool(remove_from_cache),
            }
        )

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

    def _update_cache_branch_snapshot(
        self,
        state: Dict[str, Any],
        branch: str,
        raw_entries: Dict[str, RemoteEntry],
        dir_ids: Dict[str, str],
        dir_meta: Dict[str, Dict[str, str]],
    ) -> None:
        """Incrementally update a single branch's entries and folder metadata in remote_repo_cache."""
        cache = state.get("remote_repo_cache")
        if not isinstance(cache, dict):
            return
        branches = cache.get("branches")
        if not isinstance(branches, dict):
            return
        old_b = branches.get(branch)
        known = set(cache.get("known_folder_ids") or [])
        folder_meta = cache.setdefault("folder_meta", {})
        if isinstance(old_b, dict):
            for old_did in (old_b.get("dir_ids") or {}).keys():
                known.discard(old_did)
                folder_meta.pop(old_did, None)
        branches[branch] = {
            "raw_entries": {k: v.to_dict() for k, v in raw_entries.items()},
            "dir_ids": dict(dir_ids),
        }
        for d_id in dir_ids.keys():
            if d_id:
                known.add(d_id)
        folder_meta.update(dir_meta)
        cache["known_folder_ids"] = sorted(known)

    def _remove_cache_branch(self, state: Dict[str, Any], branch: str) -> None:
        """Incrementally remove a deleted branch and its folder IDs from remote_repo_cache."""
        cache = state.get("remote_repo_cache")
        if not isinstance(cache, dict):
            return
        branches = cache.get("branches")
        if not isinstance(branches, dict):
            return
        removed_b = branches.pop(branch, None)
        if isinstance(removed_b, dict):
            known = set(cache.get("known_folder_ids") or [])
            folder_meta = cache.setdefault("folder_meta", {})
            for d_id in (removed_b.get("dir_ids") or {}).keys():
                known.discard(d_id)
                folder_meta.pop(d_id, None)
            cache["known_folder_ids"] = sorted(known)
