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

        # Case 1: Present on both local and remote
        if loc is not None and rem is not None:
            if _same_digest(loc, rem):
                actions.append(
                    SyncAction(
                        rel_path=rel_p,
                        action=SyncActionType.IN_SYNC,
                        local_entry=loc,
                        remote_entry=rem,
                        baseline_entry=base,
                        reason="identical_digest",
                    )
                )
                continue

            if base is None:
                # Both sides added different content without prior baseline
                if force and norm_mode == "push":
                    actions.append(
                        SyncAction(
                            rel_path=rel_p,
                            action=SyncActionType.PUSH_UPDATE,
                            local_entry=loc,
                            remote_entry=rem,
                            baseline_entry=base,
                            reason="forced_push_on_add_add_conflict",
                        )
                    )
                elif force and norm_mode == "pull":
                    actions.append(
                        SyncAction(
                            rel_path=rel_p,
                            action=SyncActionType.PULL_UPDATE,
                            local_entry=loc,
                            remote_entry=rem,
                            baseline_entry=base,
                            reason="forced_pull_on_add_add_conflict",
                        )
                    )
                else:
                    actions.append(
                        SyncAction(
                            rel_path=rel_p,
                            action=SyncActionType.CONFLICT,
                            local_entry=loc,
                            remote_entry=rem,
                            baseline_entry=None,
                            reason="add_add_diverged",
                        )
                    )
                continue

            loc_changed = not _same_digest(loc, base)
            rem_changed = not _same_digest(rem, base)

            if loc_changed and not rem_changed:
                if norm_mode == "pull":
                    act = SyncActionType.PULL_UPDATE if force else SyncActionType.IN_SYNC
                else:
                    act = SyncActionType.PUSH_UPDATE
                actions.append(
                    SyncAction(
                        rel_path=rel_p,
                        action=act,
                        local_entry=loc,
                        remote_entry=rem,
                        baseline_entry=base,
                        reason="modified_local_only",
                    )
                )
            elif rem_changed and not loc_changed:
                if norm_mode == "push":
                    act = SyncActionType.PUSH_UPDATE if force else SyncActionType.IN_SYNC
                else:
                    act = SyncActionType.PULL_UPDATE
                actions.append(
                    SyncAction(
                        rel_path=rel_p,
                        action=act,
                        local_entry=loc,
                        remote_entry=rem,
                        baseline_entry=base,
                        reason="modified_remote_only",
                    )
                )
            else:
                # Both modified differently relative to baseline
                if force and norm_mode == "push":
                    act = SyncActionType.PUSH_UPDATE
                elif force and norm_mode == "pull":
                    act = SyncActionType.PULL_UPDATE
                else:
                    act = SyncActionType.CONFLICT
                actions.append(
                    SyncAction(
                        rel_path=rel_p,
                        action=act,
                        local_entry=loc,
                        remote_entry=rem,
                        baseline_entry=base,
                        reason="both_modified_diverged",
                    )
                )
            continue

        # Case 2: Present only on local (rem is None)
        if loc is not None and rem is None:
            if base is None:
                # Brand new local file
                if norm_mode in ("sync", "push"):
                    actions.append(
                        SyncAction(
                            rel_path=rel_p,
                            action=SyncActionType.PUSH_NEW,
                            local_entry=loc,
                            baseline_entry=None,
                            reason="added_local",
                        )
                    )
                elif norm_mode == "pull" and allow_pull_delete:
                    actions.append(
                        SyncAction(
                            rel_path=rel_p,
                            action=SyncActionType.DELETE_LOCAL,
                            local_entry=loc,
                            baseline_entry=None,
                            reason="pull_delete_untracked_local",
                        )
                    )
            else:
                # File existed in baseline, deleted on remote
                loc_changed = not _same_digest(loc, base)
                if loc_changed:
                    if force and norm_mode == "push":
                        act = SyncActionType.PUSH_NEW
                    elif force and norm_mode == "pull" and allow_pull_delete:
                        act = SyncActionType.DELETE_LOCAL
                    else:
                        act = SyncActionType.CONFLICT
                    actions.append(
                        SyncAction(
                            rel_path=rel_p,
                            action=act,
                            local_entry=loc,
                            baseline_entry=base,
                            reason="modify_local_delete_remote_conflict",
                        )
                    )
                else:
                    if norm_mode in ("sync", "pull") and allow_pull_delete:
                        actions.append(
                            SyncAction(
                                rel_path=rel_p,
                                action=SyncActionType.DELETE_LOCAL,
                                local_entry=loc,
                                baseline_entry=base,
                                reason="deleted_on_remote",
                            )
                        )
                    elif norm_mode == "push":
                        actions.append(
                            SyncAction(
                                rel_path=rel_p,
                                action=SyncActionType.PUSH_NEW,
                                local_entry=loc,
                                baseline_entry=base,
                                reason="restore_deleted_remote_on_push",
                            )
                        )
            continue

        # Case 3: Present only on remote (loc is None)
        if rem is not None and loc is None:
            if base is None:
                # Brand new remote file
                if norm_mode in ("sync", "pull"):
                    actions.append(
                        SyncAction(
                            rel_path=rel_p,
                            action=SyncActionType.PULL_NEW,
                            remote_entry=rem,
                            baseline_entry=None,
                            reason="added_remote",
                        )
                    )
                elif norm_mode == "push" and allow_push_delete:
                    actions.append(
                        SyncAction(
                            rel_path=rel_p,
                            action=SyncActionType.DELETE_REMOTE,
                            remote_entry=rem,
                            baseline_entry=None,
                            reason="push_delete_untracked_remote",
                        )
                    )
            else:
                # File existed in baseline, deleted locally
                rem_changed = not _same_digest(rem, base)
                if rem_changed:
                    if force and norm_mode == "pull":
                        act = SyncActionType.PULL_NEW
                    elif force and norm_mode == "push" and allow_push_delete:
                        act = SyncActionType.DELETE_REMOTE
                    else:
                        act = SyncActionType.CONFLICT
                    actions.append(
                        SyncAction(
                            rel_path=rel_p,
                            action=act,
                            remote_entry=rem,
                            baseline_entry=base,
                            reason="delete_local_modify_remote_conflict",
                        )
                    )
                else:
                    if norm_mode in ("sync", "push") and allow_push_delete:
                        actions.append(
                            SyncAction(
                                rel_path=rel_p,
                                action=SyncActionType.DELETE_REMOTE,
                                remote_entry=rem,
                                baseline_entry=base,
                                reason="deleted_locally",
                            )
                        )
                    elif norm_mode == "pull":
                        actions.append(
                            SyncAction(
                                rel_path=rel_p,
                                action=SyncActionType.PULL_NEW,
                                remote_entry=rem,
                                baseline_entry=base,
                                reason="restore_deleted_local_on_pull",
                            )
                        )
            continue

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

