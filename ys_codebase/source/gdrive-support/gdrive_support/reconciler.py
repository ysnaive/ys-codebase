"""
100% Stateless Three-Way Reconciliation Engine & Reference-Counted History Calculator.

Invariants:
- Zero disk I/O, zero network I/O, zero system clock calls (no time.time_ns()).
- Strictly depends only on Python stdlib and gdrive_support.config (never imports transport.py).
"""
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class SyncActionType(str, Enum):
    """8-state reconciliation action enumeration."""

    IN_SYNC = "IN_SYNC"
    PUSH_NEW = "PUSH_NEW"
    PUSH_UPDATE = "PUSH_UPDATE"
    PULL_NEW = "PULL_NEW"
    PULL_UPDATE = "PULL_UPDATE"
    DELETE_REMOTE = "DELETE_REMOTE"
    DELETE_LOCAL = "DELETE_LOCAL"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class FileEntry:
    """
    Immutable snapshot entry representing a local, remote, or baseline file state.
    For remote shortcuts, md5/size reflect the resolved target file's content digest.
    """

    rel_path: str
    md5: str
    sha256: str = ""
    size: int = 0
    mtime_ns: int = 0
    file_id: str = ""
    is_shortcut: bool = False
    target_file_id: str = ""

    def effective_file_id(self) -> str:
        """Return target_file_id if this entry is a shortcut, otherwise file_id."""
        if self.is_shortcut and self.target_file_id:
            return self.target_file_id
        return self.file_id

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileEntry":
        return cls(
            rel_path=str(data.get("rel_path") or ""),
            md5=str(data.get("md5") or ""),
            sha256=str(data.get("sha256") or ""),
            size=int(data.get("size") or 0),
            mtime_ns=int(data.get("mtime_ns") or 0),
            file_id=str(data.get("file_id") or ""),
            is_shortcut=bool(data.get("is_shortcut", False)),
            target_file_id=str(data.get("target_file_id") or ""),
        )


@dataclass(frozen=True)
class SyncAction:
    """
    Calculated reconciliation decision for a single branch-relative path.
    """

    rel_path: str
    action: SyncActionType
    local_entry: Optional[FileEntry] = None
    remote_entry: Optional[FileEntry] = None
    baseline_entry: Optional[FileEntry] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rel_path": self.rel_path,
            "action": self.action.value,
            "local_entry": self.local_entry.to_dict() if self.local_entry else None,
            "remote_entry": self.remote_entry.to_dict() if self.remote_entry else None,
            "baseline_entry": (
                self.baseline_entry.to_dict() if self.baseline_entry else None
            ),
            "reason": self.reason,
        }


def _same_digest(a: FileEntry, b: FileEntry) -> bool:
    if a.md5 and b.md5:
        return a.md5 == b.md5 and a.size == b.size
    if a.sha256 and b.sha256:
        return a.sha256 == b.sha256 and a.size == b.size
    return a.size == b.size and a.mtime_ns == b.mtime_ns


def _reconcile_both_present(
    rel_p: str,
    loc: FileEntry,
    rem: FileEntry,
    base: Optional[FileEntry],
    norm_mode: str,
    force: bool,
) -> SyncAction:
    """Reconcile a path present on both local and remote snapshots."""
    if _same_digest(loc, rem):
        return SyncAction(
            rel_path=rel_p,
            action=SyncActionType.IN_SYNC,
            local_entry=loc,
            remote_entry=rem,
            baseline_entry=base,
            reason="identical_digest",
        )

    if base is None:
        if force and norm_mode == "push":
            return SyncAction(
                rel_path=rel_p,
                action=SyncActionType.PUSH_UPDATE,
                local_entry=loc,
                remote_entry=rem,
                baseline_entry=None,
                reason="forced_push_on_add_add_conflict",
            )
        if force and norm_mode == "pull":
            return SyncAction(
                rel_path=rel_p,
                action=SyncActionType.PULL_UPDATE,
                local_entry=loc,
                remote_entry=rem,
                baseline_entry=None,
                reason="forced_pull_on_add_add_conflict",
            )
        return SyncAction(
            rel_path=rel_p,
            action=SyncActionType.CONFLICT,
            local_entry=loc,
            remote_entry=rem,
            baseline_entry=None,
            reason="add_add_diverged",
        )

    loc_changed = not _same_digest(loc, base)
    rem_changed = not _same_digest(rem, base)

    if loc_changed and not rem_changed:
        act = (
            (SyncActionType.PULL_UPDATE if force else SyncActionType.IN_SYNC)
            if norm_mode == "pull"
            else SyncActionType.PUSH_UPDATE
        )
        return SyncAction(
            rel_path=rel_p,
            action=act,
            local_entry=loc,
            remote_entry=rem,
            baseline_entry=base,
            reason="modified_local_only",
        )

    if rem_changed and not loc_changed:
        act = (
            (SyncActionType.PUSH_UPDATE if force else SyncActionType.IN_SYNC)
            if norm_mode == "push"
            else SyncActionType.PULL_UPDATE
        )
        return SyncAction(
            rel_path=rel_p,
            action=act,
            local_entry=loc,
            remote_entry=rem,
            baseline_entry=base,
            reason="modified_remote_only",
        )

    if force and norm_mode == "push":
        act = SyncActionType.PUSH_UPDATE
    elif force and norm_mode == "pull":
        act = SyncActionType.PULL_UPDATE
    else:
        act = SyncActionType.CONFLICT
    return SyncAction(
        rel_path=rel_p,
        action=act,
        local_entry=loc,
        remote_entry=rem,
        baseline_entry=base,
        reason="both_modified_diverged",
    )


def _reconcile_local_only(
    rel_p: str,
    loc: FileEntry,
    base: Optional[FileEntry],
    norm_mode: str,
    allow_pull_delete: bool,
    force: bool,
) -> Optional[SyncAction]:
    """Reconcile a path present only on the local snapshot (remote is None)."""
    if base is None:
        if norm_mode in ("sync", "push"):
            return SyncAction(
                rel_path=rel_p,
                action=SyncActionType.PUSH_NEW,
                local_entry=loc,
                baseline_entry=None,
                reason="added_local",
            )
        if norm_mode == "pull" and allow_pull_delete:
            return SyncAction(
                rel_path=rel_p,
                action=SyncActionType.DELETE_LOCAL,
                local_entry=loc,
                baseline_entry=None,
                reason="pull_delete_untracked_local",
            )
        return None

    loc_changed = not _same_digest(loc, base)
    if loc_changed:
        if force and norm_mode == "push":
            act = SyncActionType.PUSH_NEW
        elif force and norm_mode == "pull" and allow_pull_delete:
            act = SyncActionType.DELETE_LOCAL
        else:
            act = SyncActionType.CONFLICT
        return SyncAction(
            rel_path=rel_p,
            action=act,
            local_entry=loc,
            baseline_entry=base,
            reason="modify_local_delete_remote_conflict",
        )

    if norm_mode in ("sync", "pull") and allow_pull_delete:
        return SyncAction(
            rel_path=rel_p,
            action=SyncActionType.DELETE_LOCAL,
            local_entry=loc,
            baseline_entry=base,
            reason="deleted_on_remote",
        )
    if norm_mode == "push":
        return SyncAction(
            rel_path=rel_p,
            action=SyncActionType.PUSH_NEW,
            local_entry=loc,
            baseline_entry=base,
            reason="restore_deleted_remote_on_push",
        )
    return None


def _reconcile_remote_only(
    rel_p: str,
    rem: FileEntry,
    base: Optional[FileEntry],
    norm_mode: str,
    allow_push_delete: bool,
    force: bool,
) -> Optional[SyncAction]:
    """Reconcile a path present only on the remote snapshot (local is None)."""
    if base is None:
        if norm_mode in ("sync", "pull"):
            return SyncAction(
                rel_path=rel_p,
                action=SyncActionType.PULL_NEW,
                remote_entry=rem,
                baseline_entry=None,
                reason="added_remote",
            )
        if norm_mode == "push" and allow_push_delete:
            return SyncAction(
                rel_path=rel_p,
                action=SyncActionType.DELETE_REMOTE,
                remote_entry=rem,
                baseline_entry=None,
                reason="push_delete_untracked_remote",
            )
        return None

    rem_changed = not _same_digest(rem, base)
    if rem_changed:
        if force and norm_mode == "pull":
            act = SyncActionType.PULL_NEW
        elif force and norm_mode == "push" and allow_push_delete:
            act = SyncActionType.DELETE_REMOTE
        else:
            act = SyncActionType.CONFLICT
        return SyncAction(
            rel_path=rel_p,
            action=act,
            remote_entry=rem,
            baseline_entry=base,
            reason="delete_local_modify_remote_conflict",
        )

    if norm_mode in ("sync", "push") and allow_push_delete:
        return SyncAction(
            rel_path=rel_p,
            action=SyncActionType.DELETE_REMOTE,
            remote_entry=rem,
            baseline_entry=base,
            reason="deleted_locally",
        )
    if norm_mode == "pull":
        return SyncAction(
            rel_path=rel_p,
            action=SyncActionType.PULL_NEW,
            remote_entry=rem,
            baseline_entry=base,
            reason="restore_deleted_local_on_pull",
        )
    return None


def reconcile_three_way(
    local_snap: Dict[str, FileEntry],
    remote_snap: Dict[str, FileEntry],
    baseline_snap: Dict[str, FileEntry],
    mode: str = "sync",
    allow_pull_delete: bool = False,
    allow_push_delete: bool = False,
    force: bool = False,
) -> List[SyncAction]:
    """
    Pure three-way reconciliation function.
    mode: 'sync' (bidirectional), 'pull' (remote -> local), or 'push' (local -> remote).
    """
    norm_mode = (mode or "sync").strip().lower()
    all_paths = sorted(
        set(local_snap.keys()) | set(remote_snap.keys()) | set(baseline_snap.keys())
    )
    actions: List[SyncAction] = []

    for rel_p in all_paths:
        loc = local_snap.get(rel_p)
        rem = remote_snap.get(rel_p)
        base = baseline_snap.get(rel_p)

        if loc is not None and rem is not None:
            actions.append(
                _reconcile_both_present(rel_p, loc, rem, base, norm_mode, force)
            )
            continue

        if loc is not None and rem is None:
            loc_action = _reconcile_local_only(
                rel_p, loc, base, norm_mode, allow_pull_delete, force
            )
            if loc_action is not None:
                actions.append(loc_action)
            continue

        if rem is not None and loc is None:
            rem_action = _reconcile_remote_only(
                rel_p, rem, base, norm_mode, allow_push_delete, force
            )
            if rem_action is not None:
                actions.append(rem_action)
            continue

        if base is not None:
            actions.append(
                SyncAction(
                    rel_path=rel_p,
                    action=SyncActionType.IN_SYNC,
                    local_entry=None,
                    remote_entry=None,
                    baseline_entry=base,
                    reason="both_deleted_prune_baseline",
                )
            )

    return actions


def compute_history_ref_counts(
    history_file_ids: Set[str],
    branch_files_map: Dict[str, Dict[str, str]],
) -> Dict[str, int]:
    """
    Pure function: compute how many active branch entries reference each file_id in .history/.
    branch_files_map maps {branch_name: {rel_path: effective_target_file_id}}.
    """
    counts: Dict[str, int] = {fid: 0 for fid in history_file_ids}
    for _branch, rel_map in branch_files_map.items():
        for _rel, target_fid in rel_map.items():
            if target_fid in counts:
                counts[target_fid] += 1
    return counts


def compute_orphan_history_file_ids(
    history_file_ids: Set[str],
    branch_files_map: Dict[str, Dict[str, str]],
) -> List[str]:
    """
    Pure function: return sorted list of file_ids in .history/ whose reference count across
    all active branches has dropped to 0 (eligible for automatic move to .trash/).
    """
    counts = compute_history_ref_counts(history_file_ids, branch_files_map)
    return sorted(fid for fid, cnt in counts.items() if cnt == 0)


def is_file_id_referenced_by_other_branches(
    file_id: str,
    active_branch: str,
    branch_files_map: Dict[str, Dict[str, str]],
) -> bool:
    """
    Pure function: return True if file_id is referenced by at least one branch other than active_branch.
    Used to decide between In-Place PATCH (False) vs. Copy-on-Write into .history/ (True).
    """
    if not file_id:
        return False
    for branch, rel_map in branch_files_map.items():
        if branch == active_branch:
            continue
        if file_id in rel_map.values():
            return True
    return False
