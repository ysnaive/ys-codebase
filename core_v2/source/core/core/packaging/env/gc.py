"""Non-blocking rollback-friendly virtual environment garbage collector with lock-tolerant skipping."""

from __future__ import annotations

from dataclasses import dataclass
import errno
import os
import stat
import threading
import time
from typing import Final, Optional, Sequence

from core.filesystem.fs import (
    is_symlink_or_reparse,
    resolve_contained_subpath,
    try_resolve_contained_subpath,
)
from core.foundation.primitives import (
    IS_WINDOWS,
    HostPath,
    require_pure_bool,
    require_typed_tuple,
)
from core.foundation.proc import is_process_alive
from core.packaging.env.pool import (
    ImmutableVenvPool,
    env_extract_dirname_tail_hash,
    env_resolve_venv_root,
    env_try_acquire_hash_lock_nonblocking,
)
from core.packaging.env.spec import (
    EnvGcPolicy,
    EnvGcResult,
    EnvMetadata,
    EnvSpec,
    env_read_metadata,
    env_robust_rmtree,
)

_STAGING_PREFIX: Final[str] = ".staging_"
_SECONDS_PER_DAY: Final[float] = 86400.0
_LOCKED_ERRNOS: Final[frozenset[int]] = frozenset(
    {
        errno.EACCES,
        errno.EPERM,
        errno.EBUSY,
        errno.ETXTBSY,
        errno.ENOTEMPTY,
        errno.EEXIST,
    }
)


@dataclass(frozen=True, slots=True)
class _EnvInactiveCandidate:
    env_dir: HostPath
    meta: EnvMetadata


def _extract_staging_owner_pid(entry_name: str) -> Optional[int]:
    if not entry_name.startswith(_STAGING_PREFIX):
        return None
    tail = entry_name[len(_STAGING_PREFIX) :]
    if not tail:
        return None
    tokens = tail.split("_")
    if len(tokens) >= 3 and tokens[-2].isdigit() and len(tokens[-2]) <= 10 and tokens[-1].isdigit():
        return int(tokens[-2])
    return None


def _is_locked_os_error(exc: OSError) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if exc.errno in _LOCKED_ERRNOS:
        return True
    if IS_WINDOWS:
        win_err = exc.winerror
        if isinstance(win_err, int) and win_err in (5, 32, 33, 145):
            return True
    return False


def _try_remove_env_tree(target_dir: HostPath) -> bool:
    try:
        env_robust_rmtree(target_dir.path, clear_readonly_files=True)
        return True
    except OSError as exc:
        if _is_locked_os_error(exc):
            return False
        raise


def _sweep_orphan_staging_dirs(
    venv_root: HostPath,
    cleaned_staging: list[HostPath],
    skipped_locked: list[HostPath],
) -> None:
    try:
        with os.scandir(str(venv_root)) as entries_it:
            entries = sorted(entries_it, key=lambda item: item.name)
    except OSError:
        return
    for entry in entries:
        name = entry.name
        if not name.startswith(_STAGING_PREFIX):
            continue
        owner_pid = _extract_staging_owner_pid(name)
        if owner_pid is not None and is_process_alive(owner_pid):
            continue
        if entry.is_symlink() or is_symlink_or_reparse(entry.path):
            try:
                os.unlink(entry.path)
            except OSError:
                try:
                    os.rmdir(entry.path)
                except OSError:
                    pass
            continue
        cand_dir = try_resolve_contained_subpath(venv_root, name)
        if cand_dir is None:
            continue
        if _try_remove_env_tree(cand_dir):
            cleaned_staging.append(cand_dir)
        else:
            skipped_locked.append(cand_dir)


def _stat_env_meta_sig(env_dir: HostPath) -> Optional[tuple[int, int]]:
    meta_raw = os.path.join(str(env_dir), ".yscb_env_meta.json")
    try:
        st = os.lstat(meta_raw)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    return (st.st_mtime_ns, st.st_ino)


class EnvGarbageCollector:
    """非阻塞孤兒環境回收器（保留近期離線回滾環境；Windows 鎖檔跳過不阻斷升級）。"""

    def __init__(
        self,
        pool: ImmutableVenvPool,
        *,
        policy: EnvGcPolicy = EnvGcPolicy(),
    ) -> None:
        if not isinstance(pool, ImmutableVenvPool):
            raise ValueError(f"pool must be ImmutableVenvPool, got {pool!r}")
        if not isinstance(policy, EnvGcPolicy):
            raise ValueError(f"policy must be EnvGcPolicy, got {policy!r}")
        self._pool = pool
        self._policy = policy
        self._seq_lock = threading.Lock()
        self._gc_seq = 0

    def _next_gc_seq(self) -> int:
        with self._seq_lock:
            self._gc_seq += 1
            return self._gc_seq

    def collect(
        self,
        active_specs: Sequence[EnvSpec],
        *,
        force_all: bool = False,
    ) -> EnvGcResult:
        active_tup = require_typed_tuple(active_specs, EnvSpec, "active_specs")
        require_pure_bool(force_all, "force_all")
        try:
            venv_root = env_resolve_venv_root(self._pool)
        except Exception:
            return EnvGcResult()
        if not os.path.isdir(str(venv_root)) or is_symlink_or_reparse(str(venv_root)):
            return EnvGcResult()

        cleaned_staging: list[HostPath] = []
        skipped_locked: list[HostPath] = []
        removed: list[HostPath] = []
        retained_rollback: list[HostPath] = []

        _sweep_orphan_staging_dirs(venv_root, cleaned_staging, skipped_locked)

        active_keys = {self._pool.get_env_dir(spec).comparison_key for spec in active_tup}
        scan_started_epoch = time.time()
        grace_sec = self._policy.grace_days * _SECONDS_PER_DAY
        keep_count = self._policy.keep_inactive_per_group

        eligible_by_group: dict[str, list[_EnvInactiveCandidate]] = {}
        slated_for_removal: list[tuple[HostPath, Optional[EnvMetadata], Optional[tuple[int, int]]]] = []

        for env_dir, meta in self._pool.list_envs():
            if env_dir.comparison_key in active_keys:
                continue
            if (
                not force_all
                and keep_count > 0
                and grace_sec > 0.0
                and meta is not None
                and meta.complete
                and (scan_started_epoch - meta.last_used_epoch_sec) < grace_sec
            ):
                eligible_by_group.setdefault(meta.group, []).append(
                    _EnvInactiveCandidate(env_dir=env_dir, meta=meta)
                )
            else:
                slated_for_removal.append((env_dir, meta, _stat_env_meta_sig(env_dir)))

        retained_per_group: dict[str, int] = {}
        for group_name in sorted(eligible_by_group):
            ranked = sorted(
                eligible_by_group[group_name],
                key=lambda item: (-item.meta.last_used_epoch_sec, str(item.env_dir)),
            )
            kept_slice = ranked[:keep_count]
            retained_per_group[group_name] = len(kept_slice)
            for kept_item in kept_slice:
                retained_rollback.append(kept_item.env_dir)
            for excess_item in ranked[keep_count:]:
                slated_for_removal.append((excess_item.env_dir, excess_item.meta, _stat_env_meta_sig(excess_item.env_dir)))

        for target_dir, target_meta, init_sig in slated_for_removal:
            cand_hash = (
                target_meta.env_hash
                if target_meta is not None
                else env_extract_dirname_tail_hash(target_dir.path.name)
            )
            held_lock = (
                env_try_acquire_hash_lock_nonblocking(self._pool, cand_hash)
                if cand_hash is not None
                else None
            )
            if cand_hash is not None and held_lock is None:
                skipped_locked.append(target_dir)
                continue
            try:
                if not os.path.lexists(str(target_dir)):
                    continue
                fresh_meta = env_read_metadata(target_dir)
                if fresh_meta is not None and fresh_meta.complete:
                    prev_used = (
                        target_meta.last_used_epoch_sec
                        if (target_meta is not None and target_meta.complete)
                        else -1.0
                    )
                    fresh_sig = _stat_env_meta_sig(target_dir)
                    if (
                        fresh_meta.last_used_epoch_sec > scan_started_epoch
                        or fresh_meta.last_used_epoch_sec > prev_used
                        or (init_sig is not None and fresh_sig is not None and fresh_sig != init_sig)
                    ):
                        continue
                if (
                    not force_all
                    and keep_count > 0
                    and grace_sec > 0.0
                    and fresh_meta is not None
                    and fresh_meta.complete
                    and (time.time() - fresh_meta.last_used_epoch_sec) < grace_sec
                    and retained_per_group.get(fresh_meta.group, 0) < keep_count
                ):
                    retained_per_group[fresh_meta.group] = retained_per_group.get(fresh_meta.group, 0) + 1
                    retained_rollback.append(target_dir)
                    continue
                evict_name = f".staging_gc_{target_dir.path.name}_{os.getpid()}_{self._next_gc_seq()}"
                evict_dir = resolve_contained_subpath(venv_root, evict_name)
                try:
                    os.replace(str(target_dir), str(evict_dir))
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    if _is_locked_os_error(exc):
                        skipped_locked.append(target_dir)
                        continue
                    raise
                if _try_remove_env_tree(evict_dir):
                    removed.append(target_dir)
                else:
                    orphan_evict = resolve_contained_subpath(
                        venv_root,
                        f".staging_gc_orphan_{self._next_gc_seq()}_{target_dir.path.name}",
                    )
                    try:
                        os.replace(str(evict_dir), str(orphan_evict))
                    except OSError:
                        pass
                    skipped_locked.append(target_dir)
            finally:
                if held_lock is not None:
                    held_lock.release()

        return EnvGcResult(
            removed_dirs=tuple(removed),
            skipped_locked_dirs=tuple(skipped_locked),
            retained_rollback_dirs=tuple(retained_rollback),
            cleaned_staging_dirs=tuple(cleaned_staging),
        )
