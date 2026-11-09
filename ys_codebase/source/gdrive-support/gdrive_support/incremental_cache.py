"""
Level 0 / Level 1 Incremental Remote Cache Pipeline via Google Drive changes.list API.
"""
import copy
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import GDriveConfig, GDriveTransportError, normalize_remote_rel_path
from .reconciler import FileEntry
from .transport import (
    FOLDER_MIME_TYPE,
    AbstractSyncTransport,
    ChangeRecord,
    RemoteEntry,
)

REPO_CONFIG_FILENAME = ".yscb_gdrive.json"
REPO_README_FILENAME = "README.md"
BRANCH_INTERNAL_SYSTEM_NAMES = frozenset({
    REPO_CONFIG_FILENAME,
    ".history",
    ".trash",
})


class _IncrementalPatchContext:
    """Working state for isolated Level 1 incremental change patching."""

    def __init__(
        self,
        repo_meta: Dict[str, Any],
        cache_branches: Dict[str, Any],
        known_folder_ids: Set[str],
        folder_meta: Dict[str, Dict[str, str]],
        all_branch_dir_ids: Set[str],
        file_id_to_branch_paths: Dict[str, List[Tuple[str, str]]],
        target_id_to_shortcuts: Dict[str, List[Tuple[str, str]]],
        history_file_ids: Set[str],
        meta_file_id: str,
        meta_md5: str,
        repo_folder_id: str,
        history_folder_id: str,
        trash_folder_id: str,
        folder_patched: bool = False,
        new_folder_registered: bool = False,
    ) -> None:
        self.repo_meta = repo_meta
        self.cache_branches = cache_branches
        self.known_folder_ids = known_folder_ids
        self.folder_meta = folder_meta
        self.all_branch_dir_ids = all_branch_dir_ids
        self.file_id_to_branch_paths = file_id_to_branch_paths
        self.target_id_to_shortcuts = target_id_to_shortcuts
        self.history_file_ids = history_file_ids
        self.meta_file_id = meta_file_id
        self.meta_md5 = meta_md5
        self.repo_folder_id = repo_folder_id
        self.history_folder_id = history_folder_id
        self.trash_folder_id = trash_folder_id
        self.folder_patched = folder_patched
        self.new_folder_registered = new_folder_registered


class IncrementalCacheMixin:
    """
    Implements Level 0 and Level 1 incremental remote snapshot patching with atomic
    page_token synchronization and reverse-index maintenance.
    """

    config: GDriveConfig
    transport: AbstractSyncTransport
    repo_sync_prefix: str

    def _repo_rel(self, sub_path: str = "") -> str:
        norm_sub = normalize_remote_rel_path(sub_path)
        if not norm_sub:
            return self.repo_sync_prefix
        return f"{self.repo_sync_prefix}/{norm_sub}"

    def _try_incremental_remote_cache(
        self, state: Dict[str, Any], branch: str
    ) -> Optional[
        Tuple[int, Dict[str, Any], Dict[str, FileEntry], Dict[str, RemoteEntry], str]
    ]:
        """
        Attempt Level 0 / Level 1 incremental remote cache patching via changes.list.
        Operates strictly on deep-copied working structures so any fallback (return None)
        leaves state['remote_repo_cache'] completely untouched.
        When validated, atomically updates cache['branches'] and cache['page_token'] together.
        """
        cache = state.get("remote_repo_cache")
        ctx_and_token = self._build_incremental_patch_context(cache, branch)
        if ctx_and_token is None:
            return None
        ctx, page_token = ctx_and_token

        try:
            changes, new_token = self.transport.list_changes(page_token)
        except GDriveTransportError:
            return None
        except Exception:
            return None

        if not new_token:
            return None

        classified = self._classify_incremental_changes(ctx, changes)
        if classified is None:
            return None
        folder_changes, non_folder_changes = classified

        unresolved_folder_ids = self._apply_incremental_folder_changes(
            ctx, folder_changes
        )
        if unresolved_folder_ids is None:
            return None

        if ctx.new_folder_registered and not non_folder_changes:
            return None

        level1_ops = self._validate_incremental_file_changes(
            ctx, non_folder_changes, unresolved_folder_ids
        )
        if level1_ops is None:
            return None

        if level1_ops:
            self._apply_incremental_file_ops(ctx, level1_ops)

        assert isinstance(cache, dict)
        cache["branches"] = ctx.cache_branches
        cache["page_token"] = new_token
        if ctx.folder_patched:
            cache["known_folder_ids"] = sorted(ctx.known_folder_ids)
            cache["folder_meta"] = ctx.folder_meta

        branch_files_map = ctx.repo_meta.setdefault("branch_files", {})
        for b_name, b_data in ctx.cache_branches.items():
            b_files: Dict[str, str] = {}
            for rel_p, r_dict in (b_data.get("raw_entries") or {}).items():
                r_ent = RemoteEntry.from_dict(r_dict)
                b_files[rel_p] = (
                    r_ent.target_file_id if r_ent.is_shortcut else r_ent.file_id
                )
            branch_files_map[b_name] = b_files
        cache["repo_meta"] = copy.deepcopy(ctx.repo_meta)

        active_raw_dict = ctx.cache_branches[branch].get("raw_entries") or {}
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

        hit_level = 1 if (level1_ops or ctx.folder_patched) else 0
        return hit_level, ctx.repo_meta, remote_snap, raw_remote_entries, new_token

    def _build_incremental_patch_context(
        self, cache: Any, branch: str
    ) -> Optional[Tuple[_IncrementalPatchContext, str]]:
        """Validate remote_repo_cache preconditions and construct an isolated working copy."""
        if not isinstance(cache, dict):
            return None
        if cache.get("root_folder_id") != self.config.root_folder_id:
            return None
        if cache.get("repo_sync_prefix") != self.repo_sync_prefix:
            return None
        page_token = str(cache.get("page_token") or "")
        if not page_token:
            return None
        raw_repo_meta = cache.get("repo_meta")
        raw_cache_branches = cache.get("branches")
        if not isinstance(raw_repo_meta, dict) or not isinstance(
            raw_cache_branches, dict
        ):
            return None
        if branch not in raw_cache_branches:
            return None
        for reg_b, reg_b_info in (raw_repo_meta.get("branches") or {}).items():
            if reg_b not in raw_cache_branches:
                return None
            if (
                isinstance(reg_b_info, dict)
                and reg_b_info.get("auto_discovered")
                and not (raw_repo_meta.get("branch_files") or {}).get(reg_b)
            ):
                return None

        repo_meta = copy.deepcopy(raw_repo_meta)
        cache_branches = copy.deepcopy(raw_cache_branches)
        known_folder_ids: Set[str] = set(cache.get("known_folder_ids") or [])
        folder_meta: Dict[str, Dict[str, str]] = copy.deepcopy(
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

        ctx = _IncrementalPatchContext(
            repo_meta=repo_meta,
            cache_branches=cache_branches,
            known_folder_ids=known_folder_ids,
            folder_meta=folder_meta,
            all_branch_dir_ids=all_branch_dir_ids,
            file_id_to_branch_paths=file_id_to_branch_paths,
            target_id_to_shortcuts=target_id_to_shortcuts,
            history_file_ids=history_file_ids,
            meta_file_id=str(cache.get("meta_file_id") or ""),
            meta_md5=str(cache.get("meta_md5") or ""),
            repo_folder_id=str(cache.get("repo_folder_id") or ""),
            history_folder_id=str(cache.get("history_folder_id") or ""),
            trash_folder_id=str(cache.get("trash_folder_id") or ""),
        )
        return ctx, page_token

    def _classify_incremental_changes(
        self, ctx: _IncrementalPatchContext, changes: List[ChangeRecord]
    ) -> Optional[Tuple[List[ChangeRecord], List[ChangeRecord]]]:
        """Deduplicate change records, filter managed READMEs, check .yscb_gdrive.json, and split folder vs file changes."""
        dedup_changes: Dict[str, ChangeRecord] = {}
        for ch in changes:
            if ch.file_id:
                dedup_changes[ch.file_id] = ch

        folder_changes: List[ChangeRecord] = []
        non_folder_changes: List[ChangeRecord] = []

        for ch in dedup_changes.values():
            fid = ch.file_id
            ent = ch.entry

            if not ch.removed and ent is not None:
                if ent.rel_path == self._repo_rel(REPO_README_FILENAME) or (
                    ch.name == REPO_README_FILENAME
                    and ch.parent_id
                    in (ctx.repo_folder_id, self.config.root_folder_id, "sandbox_root")
                ):
                    continue

            if (
                fid == ctx.meta_file_id
                or (
                    ch.name == REPO_CONFIG_FILENAME
                    and ch.parent_id == ctx.repo_folder_id
                )
                or (
                    ent is not None
                    and ent.rel_path == self._repo_rel(REPO_CONFIG_FILENAME)
                )
            ):
                if (
                    not ch.removed
                    and ent is not None
                    and fid == ctx.meta_file_id
                    and ctx.meta_md5
                    and ent.md5 == ctx.meta_md5
                ):
                    continue
                return None

            is_folder_change = (
                fid in ctx.known_folder_ids
                or fid in ctx.all_branch_dir_ids
                or ch.mime_type == FOLDER_MIME_TYPE
                or (ent is not None and ent.is_dir)
            )
            if is_folder_change:
                folder_changes.append(ch)
            else:
                non_folder_changes.append(ch)

        return folder_changes, non_folder_changes

    def _apply_incremental_folder_changes(
        self, ctx: _IncrementalPatchContext, folder_changes: List[ChangeRecord]
    ) -> Optional[Set[str]]:
        """Process folder removals, renames, and topological new subdirectories in Level 1."""
        pending_new_folders: List[ChangeRecord] = []
        for ch in folder_changes:
            fid = ch.file_id
            if ch.removed:
                if fid in ctx.known_folder_ids or fid in ctx.all_branch_dir_ids:
                    if not self._remove_incremental_folder_subtree(ctx, fid):
                        return None
                continue

            if fid in ctx.known_folder_ids or fid in ctx.all_branch_dir_ids:
                fm = ctx.folder_meta.get(fid)
                if (
                    fm is not None
                    and ch.name == fm.get("name")
                    and ch.parent_id == fm.get("parent_id")
                ):
                    continue
                return None

            if ch.parent_id == ctx.repo_folder_id:
                return None

            pending_new_folders.append(ch)

        while pending_new_folders:
            progress = False
            remaining_folders: List[ChangeRecord] = []
            for ch in pending_new_folders:
                if ch.parent_id in ctx.all_branch_dir_ids:
                    progress = True
                    if not self._register_incremental_new_subfolder(ctx, ch):
                        return None
                elif ch.parent_id in ctx.known_folder_ids:
                    return None
                else:
                    remaining_folders.append(ch)
            pending_new_folders = remaining_folders
            if not progress:
                break

        repo_prefix = self._repo_rel()
        unresolved_folder_ids: Set[str] = set()
        for ch in pending_new_folders:
            ent = ch.entry
            if ent is not None and (
                ent.rel_path == repo_prefix
                or ent.rel_path.startswith(f"{repo_prefix}/")
            ):
                return None
            unresolved_folder_ids.add(ch.file_id)
        return unresolved_folder_ids

    def _remove_incremental_folder_subtree(
        self, ctx: _IncrementalPatchContext, fid: str
    ) -> bool:
        """Purge a removed branch subdirectory and any cross-branch shortcuts targeting its files."""
        if fid in (ctx.repo_folder_id, ctx.history_folder_id, ctx.trash_folder_id):
            return False
        matched_branch = False
        for b_data in ctx.cache_branches.values():
            b_dirs: Dict[str, str] = b_data.setdefault("dir_ids", {})
            if fid not in b_dirs:
                continue
            matched_branch = True
            rel_dir = b_dirs[fid]
            if not rel_dir:
                return False
            dir_prefix = f"{rel_dir}/"
            sub_dir_ids = [
                d_id
                for d_id, d_rel in list(b_dirs.items())
                if d_rel == rel_dir or d_rel.startswith(dir_prefix)
            ]
            for d_id in sub_dir_ids:
                b_dirs.pop(d_id, None)
                ctx.all_branch_dir_ids.discard(d_id)
                ctx.known_folder_ids.discard(d_id)
                ctx.folder_meta.pop(d_id, None)

            raw_entries: Dict[str, Dict[str, Any]] = b_data.setdefault(
                "raw_entries", {}
            )
            removed_rel_paths = [
                r_path
                for r_path in list(raw_entries.keys())
                if r_path == rel_dir or r_path.startswith(dir_prefix)
            ]
            for r_path in removed_rel_paths:
                r_dict = raw_entries.pop(r_path, None) or {}
                entry_fid = str(r_dict.get("file_id") or "")
                if not entry_fid:
                    continue
                ctx.file_id_to_branch_paths.pop(entry_fid, None)
                for sc_b, sc_rel in ctx.target_id_to_shortcuts.pop(entry_fid, []):
                    if sc_b in ctx.cache_branches:
                        sc_dict = (
                            ctx.cache_branches[sc_b].get("raw_entries") or {}
                        ).pop(sc_rel, None) or {}
                        sc_fid = str(sc_dict.get("file_id") or "")
                        if sc_fid:
                            ctx.file_id_to_branch_paths.pop(sc_fid, None)
            ctx.folder_patched = True
        return matched_branch

    def _register_incremental_new_subfolder(
        self, ctx: _IncrementalPatchContext, ch: ChangeRecord
    ) -> bool:
        """Register a newly created branch subdirectory into the working cache."""
        fid = ch.file_id
        ent = ch.entry
        dir_name = (ch.name or (ent.name if ent is not None else "")).strip()
        if not dir_name or dir_name in BRANCH_INTERNAL_SYSTEM_NAMES:
            return False
        for b_data in ctx.cache_branches.values():
            b_dirs = b_data.setdefault("dir_ids", {})
            if ch.parent_id not in b_dirs:
                continue
            parent_rel = b_dirs[ch.parent_id]
            rel_dir = f"{parent_rel}/{dir_name}".strip("/") if parent_rel else dir_name
            if (
                rel_dir in BRANCH_INTERNAL_SYSTEM_NAMES
                or rel_dir in b_dirs.values()
                or rel_dir in (b_data.get("raw_entries") or {})
            ):
                return False
            b_dirs[fid] = rel_dir
            ctx.all_branch_dir_ids.add(fid)
            ctx.known_folder_ids.add(fid)
            ctx.folder_meta[fid] = {
                "name": dir_name,
                "parent_id": ch.parent_id,
            }
            ctx.folder_patched = True
            ctx.new_folder_registered = True
        return True

    def _validate_incremental_file_changes(
        self,
        ctx: _IncrementalPatchContext,
        non_folder_changes: List[ChangeRecord],
        unresolved_folder_ids: Set[str],
    ) -> Optional[List[ChangeRecord]]:
        """Validate non-folder change records and collect eligible Level 1 file patch operations."""
        level1_ops: List[ChangeRecord] = []
        repo_prefix = self._repo_rel()

        for ch in non_folder_changes:
            fid = ch.file_id
            ent = ch.entry

            if ch.parent_id == ctx.trash_folder_id or (
                ent is not None
                and ent.rel_path.startswith(f"{self._repo_rel('.trash')}/")
            ):
                if not ch.removed:
                    return None
                continue

            if ch.removed:
                if (
                    fid in ctx.file_id_to_branch_paths
                    or fid in ctx.target_id_to_shortcuts
                ):
                    level1_ops.append(ch)
                continue

            if ent is None:
                continue

            if ch.parent_id in unresolved_folder_ids:
                return None

            if (
                fid in ctx.file_id_to_branch_paths
                or fid in ctx.target_id_to_shortcuts
            ):
                if not self._is_known_file_change_valid(ctx, fid, ent):
                    return None
                if self._has_known_file_changed_vs_cache(ctx, fid, ent):
                    level1_ops.append(ch)
                continue

            if fid in ctx.history_file_ids:
                continue
            if ch.parent_id == ctx.history_folder_id:
                if not ch.removed:
                    return None
                continue

            if ch.parent_id in ctx.all_branch_dir_ids:
                if not self._is_new_branch_file_valid(ctx, ch.parent_id, ent.name):
                    return None
                level1_ops.append(ch)
                continue

            if ch.parent_id in ctx.known_folder_ids or (
                ent.rel_path == repo_prefix
                or ent.rel_path.startswith(f"{repo_prefix}/")
            ):
                return None

        return level1_ops

    def _is_known_file_change_valid(
        self, ctx: _IncrementalPatchContext, fid: str, ent: RemoteEntry
    ) -> bool:
        for b_name, rel_p in ctx.file_id_to_branch_paths.get(fid, []):
            old_d = ctx.cache_branches[b_name]["raw_entries"].get(rel_p)
            if not old_d:
                return False
            if ent.name != old_d.get("name") or ent.parent_id != old_d.get("parent_id"):
                return False
        return True

    def _has_known_file_changed_vs_cache(
        self, ctx: _IncrementalPatchContext, fid: str, ent: RemoteEntry
    ) -> bool:
        for b_name, rel_p in ctx.file_id_to_branch_paths.get(fid, []):
            old_d = ctx.cache_branches[b_name]["raw_entries"][rel_p]
            if (
                old_d.get("md5") != ent.md5
                or old_d.get("size") != ent.size
                or old_d.get("target_file_id") != ent.target_file_id
                or old_d.get("dangling_shortcut") != ent.dangling_shortcut
            ):
                return True
        for b_name, rel_p in ctx.target_id_to_shortcuts.get(fid, []):
            sc_d = ctx.cache_branches[b_name]["raw_entries"][rel_p]
            if (
                sc_d.get("md5") != ent.md5
                or sc_d.get("size") != ent.size
                or sc_d.get("dangling_shortcut")
            ):
                return True
        return False

    def _is_new_branch_file_valid(
        self, ctx: _IncrementalPatchContext, parent_id: str, file_name: str
    ) -> bool:
        for b_data in ctx.cache_branches.values():
            b_dirs = b_data.get("dir_ids") or {}
            if parent_id in b_dirs:
                sub_dir = b_dirs[parent_id]
                rel_p = f"{sub_dir}/{file_name}".strip("/") if sub_dir else file_name
                if (
                    rel_p in BRANCH_INTERNAL_SYSTEM_NAMES
                    or rel_p in (b_data.get("raw_entries") or {})
                ):
                    return False
        return True

    def _apply_incremental_file_ops(
        self, ctx: _IncrementalPatchContext, level1_ops: List[ChangeRecord]
    ) -> None:
        """Apply validated Level 1 file/shortcut additions, updates, and removals to the working cache."""
        for ch in level1_ops:
            fid = ch.file_id
            ent = ch.entry
            if ch.removed:
                for b_name, rel_p in ctx.file_id_to_branch_paths.pop(fid, []):
                    ctx.cache_branches[b_name]["raw_entries"].pop(rel_p, None)
                for b_name, rel_p in ctx.target_id_to_shortcuts.pop(fid, []):
                    sc_d = ctx.cache_branches[b_name]["raw_entries"].pop(rel_p, None)
                    if isinstance(sc_d, dict):
                        sc_fid = str(sc_d.get("file_id") or "")
                        if sc_fid:
                            ctx.file_id_to_branch_paths.pop(sc_fid, None)
                continue

            assert ent is not None
            if (
                fid in ctx.file_id_to_branch_paths
                or fid in ctx.target_id_to_shortcuts
            ):
                self._patch_existing_cached_file_or_shortcut(ctx, fid, ent)
                continue

            for b_name, b_data in ctx.cache_branches.items():
                b_dirs = b_data.get("dir_ids") or {}
                if ch.parent_id not in b_dirs:
                    continue
                sub_dir = b_dirs[ch.parent_id]
                rel_p = f"{sub_dir}/{ent.name}".strip("/") if sub_dir else ent.name
                if (
                    not ent.skipped_reason
                    and rel_p not in BRANCH_INTERNAL_SYSTEM_NAMES
                ):
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
                    b_data.setdefault("raw_entries", {})[rel_p] = added.to_dict()
                    if added.file_id:
                        ctx.file_id_to_branch_paths.setdefault(added.file_id, []).append(
                            (b_name, rel_p)
                        )
                    if added.is_shortcut and added.target_file_id:
                        ctx.target_id_to_shortcuts.setdefault(
                            added.target_file_id, []
                        ).append((b_name, rel_p))
                break

    def _patch_existing_cached_file_or_shortcut(
        self, ctx: _IncrementalPatchContext, fid: str, ent: RemoteEntry
    ) -> None:
        for b_name, rel_p in ctx.file_id_to_branch_paths.get(fid, []):
            old_d = ctx.cache_branches[b_name]["raw_entries"].get(rel_p)
            if not old_d:
                continue
            if ent.skipped_reason:
                ctx.cache_branches[b_name]["raw_entries"].pop(rel_p, None)
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
                ctx.cache_branches[b_name]["raw_entries"][rel_p] = patched.to_dict()

        for b_name, rel_p in ctx.target_id_to_shortcuts.get(fid, []):
            sc_d = ctx.cache_branches[b_name]["raw_entries"].get(rel_p)
            if not sc_d:
                continue
            if ent.skipped_reason:
                ctx.cache_branches[b_name]["raw_entries"].pop(rel_p, None)
            else:
                sc_d["md5"] = ent.md5
                sc_d["size"] = ent.size
                sc_d["mtime_ns"] = ent.mtime_ns
                sc_d["target_mime_type"] = ent.mime_type
                sc_d["dangling_shortcut"] = False
                sc_d["skipped_reason"] = ""
