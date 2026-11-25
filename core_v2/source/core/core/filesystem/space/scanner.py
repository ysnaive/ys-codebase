"""Two-stage SQLite WAL incremental scanner, surgical dirty-path patcher, and multi-consumer cursors."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
import stat
import threading
import time
from typing import Final, Iterator, Mapping, Optional, Sequence

from core.filesystem.fs import IGNORED_FS_PREFIXES, is_atomic_staging_filename, is_symlink_or_reparse
from core.filesystem.space.hasher import SpcMerkleItem, spc_compute_file_hash, spc_compute_merkle_root
from core.filesystem.space.registry import (
    SpaceRegistry,
    SpcCapturedRegistryView,
    spc_capture_registry_view,
    spc_ensure_space_tables,
)
from core.filesystem.space.rules import (
    ConsumerCursor,
    SpaceDiffBatch,
    SpaceStatusSnapshot,
)
from core.filesystem.storage import ModuleDatabase, SnapshotReader, WriteTransaction
from core.foundation.observability import CancellationToken
from core.foundation.primitives import (
    IS_WINDOWS,
    HostPath,
    SnapshotGen,
    SpaceId,
    SpacePath,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    safe_realpath,
)
from core.foundation.profiler import NullProfiler, Profiler

_RACY_CLEAN_WINDOW_NS: Final[int] = 20_000_000


@dataclass(frozen=True, slots=True)
class _SpcStoredFile:
    rel_path: str
    abs_path: str
    size_bytes: int
    mtime_ns: int
    content_hash: str
    updated_gen: int


@dataclass(frozen=True, slots=True)
class _SpcStoredSnapshot:
    exists: bool
    generation: int
    config_hash: str
    merkle_root: str
    file_count: int
    updated_at_ns: int


def _col_str(row: Sequence[object], idx: int) -> str:
    return require_pure_str(row[idx], f"sql_col[{idx}]")


def _col_int(row: Sequence[object], idx: int) -> int:
    return require_pure_int(row[idx], f"sql_col[{idx}]")


def _read_snapshot_meta(reader: SnapshotReader, target_key: str) -> _SpcStoredSnapshot:
    row = reader.query_one(
        "SELECT generation, config_hash, merkle_root, file_count, updated_at_ns "
        "FROM space_snapshots WHERE target_key = ?",
        (target_key,),
    )
    if row is None:
        return _SpcStoredSnapshot(False, 0, "", "", 0, 0)
    return _SpcStoredSnapshot(
        exists=True,
        generation=_col_int(row, 0),
        config_hash=_col_str(row, 1),
        merkle_root=_col_str(row, 2),
        file_count=_col_int(row, 3),
        updated_at_ns=_col_int(row, 4),
    )


def _read_stored_files(reader: SnapshotReader, target_key: str) -> dict[str, _SpcStoredFile]:
    rows = reader.query_all(
        "SELECT rel_path, abs_path, size_bytes, mtime_ns, content_hash, updated_gen "
        "FROM space_files WHERE target_key = ?",
        (target_key,),
    )
    out: dict[str, _SpcStoredFile] = {}
    for row in rows:
        rel_p = _col_str(row, 0)
        out[rel_p] = _SpcStoredFile(
            rel_path=rel_p,
            abs_path=_col_str(row, 1),
            size_bytes=_col_int(row, 2),
            mtime_ns=_col_int(row, 3),
            content_hash=_col_str(row, 4),
            updated_gen=_col_int(row, 5),
        )
    return out


def _pruned_gen_watermark_key(target_key: str) -> str:
    return f"pruned_gen:{target_key}"


def _gen_floor_watermark_key(target_key: str) -> str:
    return f"gen_floor:{target_key}"


def _read_pruned_gen(reader_or_tx: SnapshotReader | WriteTransaction, target_key: str) -> int:
    raw = reader_or_tx.get_watermark(_pruned_gen_watermark_key(target_key))
    if raw is not None and raw.isdigit():
        return int(raw)
    return 0


def _read_gen_floor(reader_or_tx: SnapshotReader | WriteTransaction, target_key: str) -> int:
    raw = reader_or_tx.get_watermark(_gen_floor_watermark_key(target_key))
    if raw is not None and raw.isdigit():
        return int(raw)
    return 0


def _fold_change_log_ops(
    rows: Sequence[Sequence[object]],
) -> tuple[tuple[SpacePath, ...], tuple[SpacePath, ...], tuple[SpacePath, ...]]:
    states: dict[str, Optional[str]] = {}
    for row in rows:
        rel_p = _col_str(row, 0)
        op = _col_str(row, 1)
        prev_op = states.get(rel_p)
        if prev_op is None:
            states[rel_p] = op
        elif prev_op == "A":
            if op == "D":
                states[rel_p] = None
            else:
                states[rel_p] = "A"
        elif prev_op == "M":
            states[rel_p] = "D" if op == "D" else "M"
        elif prev_op == "D":
            states[rel_p] = "M" if op == "A" else "D"

    added = tuple(SpacePath.parse(k) for k in sorted(k for k, v in states.items() if v == "A"))
    modified = tuple(SpacePath.parse(k) for k in sorted(k for k, v in states.items() if v == "M"))
    deleted = tuple(SpacePath.parse(k) for k in sorted(k for k, v in states.items() if v == "D"))
    return (added, modified, deleted)


def _is_racy_clean_candidate(
    cur_mtime_ns: int,
    scan_start_ns: int,
    prev_snap_updated_ns: int,
) -> bool:
    if (scan_start_ns - cur_mtime_ns) < _RACY_CLEAN_WINDOW_NS:
        return True
    if prev_snap_updated_ns > 0 and cur_mtime_ns >= (prev_snap_updated_ns - _RACY_CLEAN_WINDOW_NS):
        return True
    return False





class SpaceScanner:
    """Two-stage incremental scanner, surgical dirty-path patcher, and multi-consumer cursor engine."""

    def __init__(
        self,
        registry: SpaceRegistry,
        db: ModuleDatabase,
        *,
        profiler: Optional[Profiler] = None,
    ) -> None:
        if not isinstance(registry, SpaceRegistry):
            raise ValueError(f"SpaceScanner requires SpaceRegistry, got {registry!r}")
        spc_ensure_space_tables(db)
        self._registry: SpaceRegistry = registry
        self._db: ModuleDatabase = db
        self._profiler: Profiler = profiler if profiler is not None else NullProfiler()
        self._scan_lock = threading.RLock()
        self._inflight_lock = threading.Lock()
        self._inflight_from_gens: dict[str, list[int]] = {}

    def _prune_consumed_change_logs(self, tx: WriteTransaction, target_key: str) -> None:
        min_row = tx.query_one(
            "SELECT MIN(acked_gen) FROM consumer_cursors WHERE target_key = ?",
            (target_key,),
        )
        if min_row is None or min_row[0] is None:
            return
        cutoff = require_pure_int(min_row[0], "min_acked_gen")
        with self._inflight_lock:
            pinned = self._inflight_from_gens.get(target_key)
            if pinned:
                cutoff = min(cutoff, min(pinned))
        if cutoff <= 0:
            return
        prev_pruned = _read_pruned_gen(tx, target_key)
        tx.execute(
            "DELETE FROM space_change_log WHERE target_key = ? AND gen <= ?",
            (target_key, cutoff),
        )
        if cutoff > prev_pruned:
            tx.set_watermark(_pruned_gen_watermark_key(target_key), str(cutoff))

    def _commit_snapshot_delta(
        self,
        resolved_id: SpaceId,
        target_key: str,
        cur_cfg_hash: str,
        next_files: Mapping[str, _SpcStoredFile],
        prev_snap: _SpcStoredSnapshot,
        prev_files: Mapping[str, _SpcStoredFile],
        stat_refreshed_rels: Sequence[str],
        scan_ts_ns: int,
        advance_snap_ts: bool,
        is_full_scan: bool,
        view: SpcCapturedRegistryView,
        cancel_token: Optional[CancellationToken],
    ) -> SpaceDiffBatch:
        with self._profiler.scope_relative("Commit"):
            batch = self._commit_snapshot_delta_once(
                resolved_id=resolved_id,
                target_key=target_key,
                cur_cfg_hash=cur_cfg_hash,
                next_files=next_files,
                prev_snap=prev_snap,
                prev_files=prev_files,
                stat_refreshed_rels=stat_refreshed_rels,
                scan_ts_ns=scan_ts_ns,
                advance_snap_ts=advance_snap_ts,
                is_full_scan=is_full_scan,
                cancel_token=cancel_token,
            )
        if batch is None:
            return self._scan_locked(resolved_id, force=False, cancel_token=cancel_token, view=view)
        return batch

    def _commit_snapshot_delta_once(
        self,
        resolved_id: SpaceId,
        target_key: str,
        cur_cfg_hash: str,
        next_files: Mapping[str, _SpcStoredFile],
        prev_snap: _SpcStoredSnapshot,
        prev_files: Mapping[str, _SpcStoredFile],
        stat_refreshed_rels: Sequence[str],
        scan_ts_ns: int,
        advance_snap_ts: bool,
        is_full_scan: bool,
        cancel_token: Optional[CancellationToken],
    ) -> Optional[SpaceDiffBatch]:
        added_rels = sorted(rel for rel in next_files if rel not in prev_files)
        deleted_rels = sorted(rel for rel in prev_files if rel not in next_files)
        modified_rels = sorted(
            rel
            for rel, cur_f in next_files.items()
            if rel in prev_files and prev_files[rel].content_hash != cur_f.content_hash
        )

        merkle_items = [
            SpcMerkleItem(rel_path=f.rel_path, size_bytes=f.size_bytes, content_hash=f.content_hash)
            for f in next_files.values()
        ]
        cur_merkle = spc_compute_merkle_root(merkle_items)

        has_delta = bool(added_rels or modified_rels or deleted_rels)
        cfg_changed = prev_snap.exists and prev_snap.config_hash != cur_cfg_hash
        need_new_gen = (not prev_snap.exists) or has_delta or cfg_changed

        if not need_new_gen:
            noop_stale = False
            if stat_refreshed_rels or advance_snap_ts:
                with self._db.write_transaction(cancel_token=cancel_token) as tx:
                    chk_meta = tx.query_one(
                        "SELECT generation, config_hash FROM space_snapshots WHERE target_key = ?",
                        (target_key,),
                    )
                    if (
                        chk_meta is None
                        or _col_int(chk_meta, 0) != prev_snap.generation
                        or _col_str(chk_meta, 1) != prev_snap.config_hash
                    ):
                        noop_stale = True
                    else:
                        for rel_r in stat_refreshed_rels:
                            rf = next_files[rel_r]
                            tx.execute(
                                "UPDATE space_files SET mtime_ns = ?, size_bytes = ? "
                                "WHERE target_key = ? AND rel_path = ?",
                                (rf.mtime_ns, rf.size_bytes, target_key, rel_r),
                            )
                        if advance_snap_ts:
                            tx.execute(
                                "UPDATE space_snapshots SET updated_at_ns = ? WHERE target_key = ?",
                                (scan_ts_ns, target_key),
                            )
            if noop_stale:
                return None
            cur_gen = SnapshotGen(prev_snap.generation)
            return SpaceDiffBatch(
                space_id=resolved_id,
                from_gen=cur_gen,
                to_gen=cur_gen,
                config_hash=cur_cfg_hash,
                merkle_root=cur_merkle,
            )

        stale_base = False
        new_gen_int = 0
        with self._db.write_transaction(cancel_token=cancel_token) as tx:
            tx_meta = tx.query_one(
                "SELECT generation, config_hash FROM space_snapshots WHERE target_key = ?",
                (target_key,),
            )
            base_exists = tx_meta is not None
            base_gen_int = _col_int(tx_meta, 0) if tx_meta is not None else 0
            base_cfg = _col_str(tx_meta, 1) if tx_meta is not None else ""
            if (
                base_exists != prev_snap.exists
                or base_gen_int != prev_snap.generation
                or (prev_snap.exists and base_cfg != prev_snap.config_hash)
            ):
                stale_base = True
            else:
                gen_floor = _read_gen_floor(tx, target_key)
                new_gen_int = max(base_gen_int, gen_floor) + 1

                if deleted_rels:
                    tx.executemany(
                        "DELETE FROM space_files WHERE target_key = ? AND rel_path = ?",
                        [(target_key, rel_d) for rel_d in deleted_rels],
                    )

                upserts_rels = set(added_rels) | set(modified_rels) | set(stat_refreshed_rels)
                if not prev_snap.exists:
                    upserts_rels.update(next_files.keys())

                if upserts_rels:
                    tx.executemany(
                        """
                        INSERT INTO space_files (
                            target_key, rel_path, abs_path, size_bytes, mtime_ns, content_hash, updated_gen
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(target_key, rel_path) DO UPDATE SET
                            abs_path = excluded.abs_path,
                            size_bytes = excluded.size_bytes,
                            mtime_ns = excluded.mtime_ns,
                            content_hash = excluded.content_hash,
                            updated_gen = excluded.updated_gen
                        """,
                        [
                            (
                                target_key,
                                rel_u,
                                next_files[rel_u].abs_path,
                                next_files[rel_u].size_bytes,
                                next_files[rel_u].mtime_ns,
                                next_files[rel_u].content_hash,
                                new_gen_int
                                if (rel_u in added_rels or rel_u in modified_rels or not prev_snap.exists)
                                else next_files[rel_u].updated_gen,
                            )
                            for rel_u in sorted(upserts_rels)
                        ],
                    )

                log_entries: list[tuple[str, int, str, str]] = []
                for rel_a in added_rels:
                    log_entries.append((target_key, new_gen_int, rel_a, "A"))
                for rel_m in modified_rels:
                    log_entries.append((target_key, new_gen_int, rel_m, "M"))
                for rel_d in deleted_rels:
                    log_entries.append((target_key, new_gen_int, rel_d, "D"))
                if log_entries:
                    tx.executemany(
                        "INSERT OR REPLACE INTO space_change_log (target_key, gen, rel_path, op) VALUES (?, ?, ?, ?)",
                        log_entries,
                    )

                eff_updated_ns = (
                    scan_ts_ns
                    if (is_full_scan or advance_snap_ts or not prev_snap.exists)
                    else prev_snap.updated_at_ns
                )
                tx.execute(
                    """
                    INSERT INTO space_snapshots (
                        target_key, generation, config_hash, merkle_root, file_count, updated_at_ns
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(target_key) DO UPDATE SET
                        generation = excluded.generation,
                        config_hash = excluded.config_hash,
                        merkle_root = excluded.merkle_root,
                        file_count = excluded.file_count,
                        updated_at_ns = excluded.updated_at_ns
                    """,
                    (target_key, new_gen_int, cur_cfg_hash, cur_merkle, len(next_files), eff_updated_ns),
                )
                self._prune_consumed_change_logs(tx, target_key)
                tx.mark_generation_bumped()

        if stale_base:
            return None

        return SpaceDiffBatch(
            space_id=resolved_id,
            from_gen=SnapshotGen(base_gen_int),
            to_gen=SnapshotGen(new_gen_int),
            config_hash=cur_cfg_hash,
            merkle_root=cur_merkle,
            added=tuple(SpacePath.parse(r) for r in added_rels),
            modified=tuple(SpacePath.parse(r) for r in modified_rels),
            deleted=tuple(SpacePath.parse(r) for r in deleted_rels),
        )

    def status(self, space_id: SpaceId | str) -> SpaceStatusSnapshot:
        view = spc_capture_registry_view(self._registry)
        spec = view.get_space(space_id)
        resolved_id = spec.space_id
        target_key = str(resolved_id)
        live_cfg_hash = view.config_hash(resolved_id)

        with self._db.read_snapshot() as snap:
            meta = _read_snapshot_meta(snap, target_key)
            cursor_rows = snap.query_all(
                "SELECT consumer_id, acked_gen, config_hash, merkle_root "
                "FROM consumer_cursors WHERE target_key = ? ORDER BY consumer_id ASC",
                (target_key,),
            )

        cursors = tuple(
            ConsumerCursor(
                consumer_id=_col_str(c_row, 0),
                space_id=resolved_id,
                acked_gen=SnapshotGen(_col_int(c_row, 1)),
                config_hash=_col_str(c_row, 2),
                merkle_root=_col_str(c_row, 3),
            )
            for c_row in cursor_rows
        )
        return SpaceStatusSnapshot(
            space_id=resolved_id,
            generation=SnapshotGen(meta.generation),
            config_hash=meta.config_hash if meta.exists else live_cfg_hash,
            merkle_root=meta.merkle_root,
            file_count=meta.file_count,
            cursors=cursors,
        )

    def scan(
        self,
        space_id: SpaceId | str,
        *,
        force: bool = False,
        cancel_token: Optional[CancellationToken] = None,
    ) -> SpaceDiffBatch:
        require_pure_bool(force, "force")
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        with self._profiler.scope_relative("Space/Scan"):
            with self._scan_lock:
                return self._scan_locked(space_id, force=force, cancel_token=cancel_token)

    def _scan_locked(
        self,
        space_id: SpaceId | str,
        *,
        force: bool,
        cancel_token: Optional[CancellationToken],
        view: Optional[SpcCapturedRegistryView] = None,
    ) -> SpaceDiffBatch:
        active_view = view if view is not None else spc_capture_registry_view(self._registry)
        spec = active_view.get_space(space_id)
        resolved_id = spec.space_id
        target_key = str(resolved_id)
        cur_cfg_hash = active_view.config_hash(resolved_id)
        eff_policy = spec.hash_policy
        scan_start_ns = time.time_ns()

        with self._db.read_snapshot() as snap:
            prev_snap = _read_snapshot_meta(snap, target_key)
            prev_files = _read_stored_files(snap, target_key)

        with self._profiler.scope_relative("WalkFiles"):
            stat_entries = active_view.iter_raw_files(resolved_id, cancel_token=cancel_token)
        next_files: dict[str, _SpcStoredFile] = {}
        stat_refreshed: list[str] = []
        rechecked_racy = False

        with self._profiler.scope_relative("HashFiles"):
            for st_ent in stat_entries:
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                rel_s = str(st_ent.rel_path)
                prev_f = prev_files.get(rel_s)
                is_racy = _is_racy_clean_candidate(st_ent.mtime_ns, scan_start_ns, prev_snap.updated_at_ns)
                can_reuse = (
                    (not force)
                    and prev_snap.exists
                    and prev_snap.config_hash == cur_cfg_hash
                    and prev_f is not None
                    and prev_f.size_bytes == st_ent.size_bytes
                    and prev_f.mtime_ns == st_ent.mtime_ns
                    and not is_racy
                )
                if can_reuse and prev_f is not None:
                    next_files[rel_s] = prev_f
                    continue
                if is_racy and prev_f is not None and prev_f.size_bytes == st_ent.size_bytes and prev_f.mtime_ns == st_ent.mtime_ns:
                    rechecked_racy = True

                try:
                    computed_hash = spc_compute_file_hash(
                        st_ent.abs_path,
                        size_bytes=st_ent.size_bytes,
                        mtime_ns=st_ent.mtime_ns,
                        policy=eff_policy,
                    )
                except OSError:
                    continue
                if computed_hash is None:
                    continue

                if (
                    prev_f is not None
                    and prev_f.content_hash == computed_hash
                    and (prev_f.size_bytes != st_ent.size_bytes or prev_f.mtime_ns != st_ent.mtime_ns)
                ):
                    stat_refreshed.append(rel_s)

                next_files[rel_s] = _SpcStoredFile(
                    rel_path=rel_s,
                    abs_path=str(st_ent.abs_path),
                    size_bytes=st_ent.size_bytes,
                    mtime_ns=st_ent.mtime_ns,
                    content_hash=computed_hash,
                    updated_gen=prev_f.updated_gen if prev_f is not None else max(1, prev_snap.generation + 1),
                )

        return self._commit_snapshot_delta(
            resolved_id=resolved_id,
            target_key=target_key,
            cur_cfg_hash=cur_cfg_hash,
            next_files=next_files,
            prev_snap=prev_snap,
            prev_files=prev_files,
            stat_refreshed_rels=stat_refreshed,
            scan_ts_ns=scan_start_ns,
            advance_snap_ts=rechecked_racy and (scan_start_ns - prev_snap.updated_at_ns) >= _RACY_CLEAN_WINDOW_NS,
            is_full_scan=True,
            view=active_view,
            cancel_token=cancel_token,
        )

    def patch_paths(
        self,
        dirty_paths: frozenset[HostPath],
        *,
        cancel_token: Optional[CancellationToken] = None,
    ) -> tuple[SpaceDiffBatch, ...]:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        if not dirty_paths:
            return ()
        for hp in dirty_paths:
            if not isinstance(hp, HostPath):
                raise ValueError(f"dirty_paths requires HostPath elements, got {hp!r}")

        with self._profiler.scope_relative("Space/PatchPaths"):
            with self._scan_lock:
                return self._patch_paths_locked(dirty_paths, cancel_token=cancel_token)

    def _patch_paths_locked(
        self,
        dirty_paths: frozenset[HostPath],
        *,
        cancel_token: Optional[CancellationToken],
    ) -> tuple[SpaceDiffBatch, ...]:
        view = spc_capture_registry_view(self._registry)
        patch_start_ns = time.time_ns()
        with self._db.read_snapshot() as snap:
            snap_rows = snap.query_all("SELECT target_key FROM space_snapshots ORDER BY target_key ASC")
        tracked_set = {_col_str(r, 0) for r in snap_rows}

        candidate_ids: list[SpaceId] = [
            s.space_id
            for s in view.list_spaces()
            if s.watch
            and s.space_id.name not in ("gitignore", "readonly")
            and (s.space_id.owner != "" or str(s.space_id) in tracked_set)
        ]

        batches: list[SpaceDiffBatch] = []
        for sid in candidate_ids:
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            spec = view.get_space(sid)
            target_key = str(sid)
            cur_cfg_hash = view.config_hash(sid)

            with self._db.read_snapshot() as snap:
                prev_snap = _read_snapshot_meta(snap, target_key)
                prev_files = _read_stored_files(snap, target_key)

            if not prev_snap.exists or prev_snap.config_hash != cur_cfg_hash:
                full_batch = self._scan_locked(sid, force=False, cancel_token=cancel_token, view=view)
                if full_batch.has_changes:
                    batches.append(full_batch)
                continue

            prev_by_abs: dict[str, _SpcStoredFile] = {
                os.path.normcase(f.abs_path).rstrip("/\\"): f for f in prev_files.values()
            }
            has_dir_or_prefix_dirty = False
            relevant = False

            for d_hp in dirty_paths:
                raw_d = str(d_hp)
                norm_d = d_hp.comparison_key.rstrip("/\\")
                d_sep = f"{norm_d}{os.sep}"
                if norm_d in prev_by_abs:
                    relevant = True
                elif any(abs_k.startswith(d_sep) for abs_k in prev_by_abs):
                    relevant = True
                    has_dir_or_prefix_dirty = True
                try:
                    if os.path.isdir(raw_d) and not is_symlink_or_reparse(raw_d):
                        has_dir_or_prefix_dirty = True
                        for member_sid in view.collect_positive_closure(sid):
                            dir_exp = view.match_path(member_sid, d_hp)
                            if dir_exp.matched or dir_exp.reason in (
                                "not_matching_include",
                                "excluded_by_preset",
                                "excluded_by_compose",
                                "ancestor_of_entry",
                            ):
                                relevant = True
                                break
                except OSError:
                    pass
                if not relevant and view.match_path(sid, d_hp).matched:
                    relevant = True

            if not relevant:
                continue
            if has_dir_or_prefix_dirty or bool(spec.compose) or len(spec.entries) > 1:
                dir_batch = self._scan_locked(sid, force=False, cancel_token=cancel_token, view=view)
                if dir_batch.has_changes:
                    batches.append(dir_batch)
                continue

            next_files = dict(prev_files)
            stat_refreshed: list[str] = []
            need_fallback_scan = False

            for d_hp in dirty_paths:
                raw_d = str(d_hp)
                norm_d = d_hp.comparison_key.rstrip("/\\")
                old_rec = prev_by_abs.get(norm_d)
                if (
                    d_hp.path.name.startswith(IGNORED_FS_PREFIXES)
                    or is_atomic_staging_filename(d_hp.path.name)
                    or is_symlink_or_reparse(raw_d)
                ):
                    if old_rec is not None:
                        next_files.pop(old_rec.rel_path, None)
                    continue

                try:
                    f_st = os.lstat(raw_d)
                    exists_reg = stat.S_ISREG(f_st.st_mode)
                except OSError:
                    f_st = None
                    exists_reg = False

                if not exists_reg or f_st is None or not view.match_path(sid, d_hp).matched:
                    if old_rec is not None:
                        next_files.pop(old_rec.rel_path, None)
                    continue

                actual_abs = safe_realpath(raw_d) if IS_WINDOWS else raw_d
                if old_rec is None or old_rec.abs_path != actual_abs:
                    need_fallback_scan = True
                    break
                rel_s = old_rec.rel_path
                cur_sz = max(0, int(f_st.st_size))
                cur_mt = max(0, int(f_st.st_mtime_ns))
                try:
                    c_hash = spc_compute_file_hash(
                        d_hp,
                        size_bytes=cur_sz,
                        mtime_ns=cur_mt,
                        policy=spec.hash_policy,
                    )
                except OSError:
                    if old_rec is not None:
                        next_files.pop(old_rec.rel_path, None)
                    continue
                if c_hash is None:
                    if old_rec is not None:
                        next_files.pop(old_rec.rel_path, None)
                    continue

                if old_rec is not None and old_rec.content_hash == c_hash:
                    if old_rec.size_bytes != cur_sz or old_rec.mtime_ns != cur_mt:
                        stat_refreshed.append(rel_s)
                next_files[rel_s] = _SpcStoredFile(
                    rel_path=rel_s,
                    abs_path=raw_d,
                    size_bytes=cur_sz,
                    mtime_ns=cur_mt,
                    content_hash=c_hash,
                    updated_gen=old_rec.updated_gen if old_rec is not None else prev_snap.generation + 1,
                )

            if need_fallback_scan:
                fb_batch = self._scan_locked(sid, force=False, cancel_token=cancel_token, view=view)
                if fb_batch.has_changes:
                    batches.append(fb_batch)
                continue

            patch_batch = self._commit_snapshot_delta(
                resolved_id=sid,
                target_key=target_key,
                cur_cfg_hash=cur_cfg_hash,
                next_files=next_files,
                prev_snap=prev_snap,
                prev_files=prev_files,
                stat_refreshed_rels=stat_refreshed,
                scan_ts_ns=patch_start_ns,
                advance_snap_ts=False,
                is_full_scan=False,
                view=view,
                cancel_token=cancel_token,
            )
            if patch_batch.has_changes:
                batches.append(patch_batch)

        return tuple(batches)

    def diff(self, space_id: SpaceId | str, consumer_id: str) -> SpaceDiffBatch:
        require_pure_str(consumer_id, "consumer_id")
        clean_cid = consumer_id.strip()
        if not clean_cid:
            raise ValueError("consumer_id must be a non-empty string.")
        with self._profiler.scope_relative("Space/Diff"):
            return self._diff_validated(space_id, clean_cid)

    def _diff_validated(self, space_id: SpaceId | str, clean_cid: str) -> SpaceDiffBatch:
        view = spc_capture_registry_view(self._registry)
        spec = view.get_space(space_id)
        resolved_id = spec.space_id
        target_key = str(resolved_id)
        live_cfg_hash = view.config_hash(resolved_id)

        with self._db.read_snapshot() as snap:
            meta = _read_snapshot_meta(snap, target_key)
            gen_floor = _read_gen_floor(snap, target_key)
            cur_row = snap.query_one(
                "SELECT acked_gen, config_hash, merkle_root "
                "FROM consumer_cursors WHERE consumer_id = ? AND target_key = ?",
                (clean_cid, target_key),
            )
            acked_gen = _col_int(cur_row, 0) if cur_row is not None else 0
            cur_cfg = _col_str(cur_row, 1) if cur_row is not None else ""
            cur_merkle = _col_str(cur_row, 2) if cur_row is not None else ""

            if not meta.exists:
                eff_from = acked_gen if acked_gen > gen_floor else 0
                return SpaceDiffBatch(
                    space_id=resolved_id,
                    from_gen=SnapshotGen(eff_from),
                    to_gen=SnapshotGen(0),
                    config_hash=live_cfg_hash,
                    merkle_root="",
                )

            if (
                cur_row is not None
                and acked_gen == meta.generation
                and acked_gen > gen_floor
                and cur_cfg == meta.config_hash
                and cur_merkle == meta.merkle_root
            ):
                return SpaceDiffBatch(
                    space_id=resolved_id,
                    from_gen=SnapshotGen(acked_gen),
                    to_gen=SnapshotGen(meta.generation),
                    config_hash=meta.config_hash,
                    merkle_root=meta.merkle_root,
                )

            pruned_gen = _read_pruned_gen(snap, target_key)
            cursor_desynced = (
                cur_row is None
                or acked_gen == 0
                or acked_gen <= gen_floor
                or acked_gen < pruned_gen
                or acked_gen > meta.generation
                or (
                    acked_gen == meta.generation
                    and (cur_cfg != meta.config_hash or cur_merkle != meta.merkle_root)
                )
            )
            if cursor_desynced:
                file_rows = snap.query_all(
                    "SELECT rel_path FROM space_files WHERE target_key = ? ORDER BY rel_path ASC",
                    (target_key,),
                )
                all_added = tuple(SpacePath.parse(_col_str(r, 0)) for r in file_rows)
                return SpaceDiffBatch(
                    space_id=resolved_id,
                    from_gen=SnapshotGen(0),
                    to_gen=SnapshotGen(meta.generation),
                    config_hash=meta.config_hash,
                    merkle_root=meta.merkle_root,
                    added=all_added,
                )

            log_rows = snap.query_all(
                "SELECT rel_path, op FROM space_change_log "
                "WHERE target_key = ? AND gen > ? AND gen <= ? ORDER BY gen ASC, rel_path ASC",
                (target_key, acked_gen, meta.generation),
            )

        added, modified, deleted = _fold_change_log_ops(log_rows)
        return SpaceDiffBatch(
            space_id=resolved_id,
            from_gen=SnapshotGen(acked_gen),
            to_gen=SnapshotGen(meta.generation),
            config_hash=meta.config_hash,
            merkle_root=meta.merkle_root,
            added=added,
            modified=modified,
            deleted=deleted,
        )

    def ack_cursor(self, space_id: SpaceId | str, consumer_id: str, batch: SpaceDiffBatch) -> bool:
        require_pure_str(consumer_id, "consumer_id")
        clean_cid = consumer_id.strip()
        if not clean_cid:
            raise ValueError("consumer_id must be a non-empty string.")
        if not isinstance(batch, SpaceDiffBatch):
            raise ValueError(f"batch must be SpaceDiffBatch, got {batch!r}")
        with self._profiler.scope_relative("Space/AckCursor"):
            return self._ack_cursor_validated(space_id, clean_cid, batch)

    def _ack_cursor_validated(self, space_id: SpaceId | str, clean_cid: str, batch: SpaceDiffBatch) -> bool:
        spec = self._registry.get_space(space_id)
        resolved_id = spec.space_id
        if batch.space_id != resolved_id:
            raise ValueError(f"SpaceDiffBatch.space_id '{batch.space_id}' does not match '{resolved_id}'.")
        target_key = str(resolved_id)

        target_gen = batch.to_gen.value
        from_gen_val = batch.from_gen.value
        if target_gen <= 0 or from_gen_val > target_gen:
            return False

        with self._db.read_snapshot() as snap:
            snap_meta = _read_snapshot_meta(snap, target_key)
            snap_floor = _read_gen_floor(snap, target_key)
            cur_row = snap.query_one(
                "SELECT acked_gen, config_hash, merkle_root "
                "FROM consumer_cursors WHERE consumer_id = ? AND target_key = ?",
                (clean_cid, target_key),
            )
        if (
            not snap_meta.exists
            or target_gen <= snap_floor
            or target_gen > snap_meta.generation
            or (
                target_gen == snap_meta.generation
                and (batch.config_hash != snap_meta.config_hash or batch.merkle_root != snap_meta.merkle_root)
            )
        ):
            return False
        raw_acked = _col_int(cur_row, 0) if cur_row is not None else 0
        eff_acked = raw_acked if (cur_row is not None and raw_acked > snap_floor) else 0
        if from_gen_val > eff_acked:
            return False
        if cur_row is not None:
            cur_cfg = _col_str(cur_row, 1)
            cur_merkle = _col_str(cur_row, 2)
            if raw_acked == target_gen and cur_cfg == batch.config_hash and cur_merkle == batch.merkle_root:
                return False
            if raw_acked > target_gen:
                return False

        now_ns = time.time_ns()
        with self._db.write_transaction() as tx:
            tx_snap_row = tx.query_one(
                "SELECT generation, config_hash, merkle_root FROM space_snapshots WHERE target_key = ?",
                (target_key,),
            )
            tx_floor = _read_gen_floor(tx, target_key)
            if tx_snap_row is None:
                return False
            tx_gen = _col_int(tx_snap_row, 0)
            tx_cfg = _col_str(tx_snap_row, 1)
            tx_merkle = _col_str(tx_snap_row, 2)
            if (
                target_gen <= tx_floor
                or target_gen > tx_gen
                or (target_gen == tx_gen and (batch.config_hash != tx_cfg or batch.merkle_root != tx_merkle))
            ):
                return False
            recheck = tx.query_one(
                "SELECT acked_gen, config_hash, merkle_root "
                "FROM consumer_cursors WHERE consumer_id = ? AND target_key = ?",
                (clean_cid, target_key),
            )
            tx_raw_acked = _col_int(recheck, 0) if recheck is not None else 0
            tx_eff_acked = tx_raw_acked if (recheck is not None and tx_raw_acked > tx_floor) else 0
            if from_gen_val > tx_eff_acked:
                return False
            if recheck is not None:
                rc_cfg = _col_str(recheck, 1)
                rc_merkle = _col_str(recheck, 2)
                if tx_raw_acked == target_gen and rc_cfg == batch.config_hash and rc_merkle == batch.merkle_root:
                    return False
                if tx_raw_acked > target_gen:
                    return False

            tx.execute(
                """
                INSERT INTO consumer_cursors (
                    consumer_id, target_key, acked_gen, config_hash, merkle_root, updated_at_ns
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(consumer_id, target_key) DO UPDATE SET
                    acked_gen = excluded.acked_gen,
                    config_hash = excluded.config_hash,
                    merkle_root = excluded.merkle_root,
                    updated_at_ns = excluded.updated_at_ns
                """,
                (clean_cid, target_key, batch.to_gen.value, batch.config_hash, batch.merkle_root, now_ns),
            )
            self._prune_consumed_change_logs(tx, target_key)
        return True

    @contextmanager
    def consume_diff(self, space_id: SpaceId | str, consumer_id: str) -> Iterator[SpaceDiffBatch]:
        resolved_key = str(self._registry.get_space(space_id).space_id)
        with self._inflight_lock:
            pre_pin = self._inflight_from_gens.setdefault(resolved_key, [])
            pre_pin.append(0)
        batch: Optional[SpaceDiffBatch] = None
        pinned_val = 0
        try:
            batch = self.diff(space_id, consumer_id)
            pinned_val = batch.from_gen.value
            with self._inflight_lock:
                cur_pin = self._inflight_from_gens.get(resolved_key)
                if cur_pin is not None and 0 in cur_pin:
                    cur_pin.remove(0)
                    cur_pin.append(pinned_val)
            yield batch
            self.ack_cursor(space_id, consumer_id, batch)
        finally:
            with self._inflight_lock:
                fin_pin = self._inflight_from_gens.get(resolved_key)
                if fin_pin is not None:
                    if pinned_val in fin_pin:
                        fin_pin.remove(pinned_val)
                    elif 0 in fin_pin:
                        fin_pin.remove(0)
                    if not fin_pin:
                        self._inflight_from_gens.pop(resolved_key, None)

    def clean(
        self,
        space_id: Optional[SpaceId | str] = None,
        *,
        consumer_id: Optional[str] = None,
    ) -> int:
        target_key: Optional[str] = None
        if space_id is not None:
            resolved_id = self._registry.get_space(space_id).space_id
            target_key = str(resolved_id)

        clean_cid: Optional[str] = None
        if consumer_id is not None:
            require_pure_str(consumer_id, "consumer_id")
            clean_cid = consumer_id.strip()
            if not clean_cid:
                raise ValueError("consumer_id must not be empty when specified.")

        with self._scan_lock:
            with self._db.write_transaction() as tx:
                if clean_cid is not None and target_key is not None:
                    return tx.execute(
                        "DELETE FROM consumer_cursors WHERE consumer_id = ? AND target_key = ?",
                        (clean_cid, target_key),
                    )
                if clean_cid is not None:
                    return tx.execute("DELETE FROM consumer_cursors WHERE consumer_id = ?", (clean_cid,))
                if target_key is not None:
                    snap_row = tx.query_one(
                        "SELECT generation FROM space_snapshots WHERE target_key = ?",
                        (target_key,),
                    )
                    snap_gen = _col_int(snap_row, 0) if snap_row is not None else 0
                    new_floor = max(_read_gen_floor(tx, target_key), _read_pruned_gen(tx, target_key), snap_gen)
                    if new_floor > 0:
                        tx.set_watermark(_gen_floor_watermark_key(target_key), str(new_floor))
                        tx.set_watermark(_pruned_gen_watermark_key(target_key), str(new_floor))
                    removed = tx.execute("DELETE FROM consumer_cursors WHERE target_key = ?", (target_key,))
                    removed += tx.execute("DELETE FROM space_change_log WHERE target_key = ?", (target_key,))
                    removed += tx.execute("DELETE FROM space_files WHERE target_key = ?", (target_key,))
                    removed += tx.execute("DELETE FROM space_snapshots WHERE target_key = ?", (target_key,))
                    if removed > 0:
                        tx.mark_generation_bumped()
                    return removed
                all_snaps = tx.query_all("SELECT target_key, generation FROM space_snapshots")
                for s_row in all_snaps:
                    tk = _col_str(s_row, 0)
                    sg = _col_int(s_row, 1)
                    nf = max(_read_gen_floor(tx, tk), _read_pruned_gen(tx, tk), sg)
                    if nf > 0:
                        tx.set_watermark(_gen_floor_watermark_key(tk), str(nf))
                        tx.set_watermark(_pruned_gen_watermark_key(tk), str(nf))
                removed_all = tx.execute("DELETE FROM consumer_cursors")
                removed_all += tx.execute("DELETE FROM space_change_log")
                removed_all += tx.execute("DELETE FROM space_files")
                removed_all += tx.execute("DELETE FROM space_snapshots")
                if removed_all > 0:
                    tx.mark_generation_bumped()
                return removed_all
