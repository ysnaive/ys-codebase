"""Transactional offline package engine orchestrating SnapshotVault, ProviderClient, MirrorStore, DependencySolver, ImmutableVenvPool, and AtomicPackageDeployer."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Callable, Final, Iterator, Mapping, Optional, Sequence

from core.filesystem.fs import (
    IGNORED_FS_PREFIXES,
    MAX_JSON_FILE_BYTES,
    FileLock,
    assert_no_symlink_raw_path,
    atomic_write_bytes,
    has_symlink_raw_path,
    is_atomic_staging_filename,
    is_symlink_or_reparse,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
    silent_unlink,
    try_resolve_contained_subpath,
    walk_nonsymlink_dir_tree,
)
from core.filesystem.vfs import KernelVfs
from core.foundation.errors import ErrorCode, YscbError
from core.foundation.observability import CancellationToken
from core.foundation.primitives import (
    HostPath,
    ModuleId,
    SemVer4,
    is_valid_relative_segment,
    require_pure_bool,
    require_pure_str,
    require_typed_tuple,
)
from core.foundation.proc import is_public_env_truthy
from core.metadata.config import (
    ConfigStore,
    HostConfig,
    InstalledModuleRecord,
    ModuleManifest,
    SnapshotVault,
)
from core.packaging.env import EnvSpec, ImmutableVenvPool
from core.packaging.installer.deployer import AtomicPackageDeployer, ins_materialize_module
from core.packaging.installer.mirror import MirrorStore
from core.packaging.installer.models import (
    INS_MAX_ZIP_ARCHIVE_BYTES,
    INS_NON_FALLBACK_ERROR_CODES,
    INS_RESERVED_NON_MODULE_IDS,
    DeploymentReport,
    IndexReleaseRecord,
    PackageRequest,
    PurgeLevel,
    UpgradeTransition,
    ins_assert_not_reserved_module_id,
    ins_has_dependencies_override,
    ins_override_manifest_dependencies,
    ins_peek_zip_manifest,
    ins_read_manifest_file,
    ins_robust_rmtree,
    ins_utc_now_iso,
)
from core.packaging.installer.provider import ProviderClient, ins_is_http_provider, ins_is_provider_offline
from core.packaging.installer.solver import DependencySolver, ins_reconcile_installed_with_overrides

_CORE_MODULE_ID: Final[ModuleId] = ModuleId("core")
_MAX_RECONCILE_ROUNDS: Final[int] = 32
_ENGINE_LOCK_TIMEOUT_SEC: Final[float] = 120.0
_TX_GUARD_AREAS: Final[tuple[tuple[str, str], ...]] = (
    ("config", "config"),
    ("config_local", ".config.local"),
    ("storage", "storage"),
)


@dataclass(frozen=True, slots=True)
class _InsPlannedPackage:
    module_id: ModuleId
    version: SemVer4
    release_record: Optional[IndexReleaseRecord]
    provider: str
    zip_path: HostPath
    manifest: ModuleManifest


@dataclass(frozen=True, slots=True)
class _InsTxWorkspaceGuard:
    guard_dir: HostPath
    had_host_cfg: bool
    host_cfg_bytes: Optional[bytes]
    area_present: Mapping[str, bool]


def _snapshot_existing_mirror_indices(yscb_root: HostPath) -> dict[HostPath, bytes]:
    captured: dict[HostPath, bytes] = {}
    mirror_root = try_resolve_contained_subpath(yscb_root, ".mirror")
    if mirror_root is None or not os.path.isdir(str(mirror_root)) or is_symlink_or_reparse(str(mirror_root)):
        return captured
    try:
        with os.scandir(str(mirror_root)) as it:
            entries = list(it)
    except OSError:
        return captured
    for ent in entries:
        if ent.name.startswith(".") or ent.name in INS_RESERVED_NON_MODULE_IDS or ent.is_symlink():
            continue
        if not ent.is_dir(follow_symlinks=False):
            continue
        idx_hp = try_resolve_contained_subpath(mirror_root, ent.name, "index.json")
        if idx_hp is None:
            continue
        try:
            raw_b = read_nofollow_regular_bytes(str(idx_hp), max_bytes=MAX_JSON_FILE_BYTES)
        except OSError:
            raw_b = None
        if raw_b is not None:
            captured[idx_hp] = raw_b
    return captured


class _InsMirrorTxJournal:
    """Transactional backup journal for overwritten or newly staged .mirror/*.zip and index.json files."""

    def __init__(self, yscb_root: HostPath, seq: int) -> None:
        self._yscb_root = yscb_root
        self._seq = seq
        self._backup_dir: Optional[HostPath] = None
        self._overwritten: dict[HostPath, HostPath] = {}
        self._newly_created: set[HostPath] = set()
        self._initial_indices: dict[HostPath, bytes] = _snapshot_existing_mirror_indices(yscb_root)
        self._item_seq = 0

    def record_before_fetch(self, mirror_zip: HostPath) -> None:
        if mirror_zip in self._overwritten or mirror_zip in self._newly_created:
            return
        raw_zip = str(mirror_zip)
        if not os.path.lexists(raw_zip):
            self._newly_created.add(mirror_zip)
            return
        orig_bytes = read_nofollow_regular_bytes(raw_zip, max_bytes=INS_MAX_ZIP_ARCHIVE_BYTES)
        if orig_bytes is None:
            return
        if self._backup_dir is None:
            temp_root = resolve_contained_subpath(self._yscb_root, ".temp")
            os.makedirs(str(temp_root), exist_ok=True)
            bak_dir = resolve_contained_subpath(temp_root, f"mirror_tx_{os.getpid()}_{self._seq}")
            if os.path.lexists(str(bak_dir)):
                ins_robust_rmtree(str(bak_dir))
            os.makedirs(str(bak_dir), exist_ok=False)
            self._backup_dir = bak_dir
        self._item_seq += 1
        bak_file = resolve_contained_subpath(self._backup_dir, f"orig_{self._item_seq}.zip")
        atomic_write_bytes(bak_file, orig_bytes)
        self._overwritten[mirror_zip] = bak_file

    def restore_on_failure(self) -> None:
        for target_zip, bak_file in self._overwritten.items():
            try:
                bak_bytes = read_nofollow_regular_bytes(str(bak_file), max_bytes=INS_MAX_ZIP_ARCHIVE_BYTES)
                if bak_bytes is not None:
                    atomic_write_bytes(target_zip, bak_bytes)
            except (OSError, YscbError):
                pass
        for created_zip in self._newly_created:
            try:
                silent_unlink(created_zip)
                parent_dir = str(created_zip.path.parent)
                if os.path.isdir(parent_dir) and not is_symlink_or_reparse(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
            except OSError:
                pass
        for idx_hp, orig_idx_bytes in self._initial_indices.items():
            try:
                cur_idx_bytes = read_nofollow_regular_bytes(str(idx_hp), max_bytes=MAX_JSON_FILE_BYTES)
            except OSError:
                cur_idx_bytes = None
            if cur_idx_bytes != orig_idx_bytes:
                try:
                    atomic_write_bytes(idx_hp, orig_idx_bytes)
                except (OSError, YscbError):
                    pass
        mirror_root = try_resolve_contained_subpath(self._yscb_root, ".mirror")
        if mirror_root is not None and os.path.isdir(str(mirror_root)) and not is_symlink_or_reparse(str(mirror_root)):
            try:
                with os.scandir(str(mirror_root)) as it:
                    entries = list(it)
            except OSError:
                entries = []
            for ent in entries:
                if ent.name.startswith(".") or ent.name in INS_RESERVED_NON_MODULE_IDS or ent.is_symlink():
                    continue
                if not ent.is_dir(follow_symlinks=False):
                    continue
                cand_idx = try_resolve_contained_subpath(mirror_root, ent.name, "index.json")
                if cand_idx is not None and cand_idx not in self._initial_indices and os.path.lexists(str(cand_idx)):
                    silent_unlink(cand_idx)
                    mod_mirror_raw = str(cand_idx.path.parent)
                    try:
                        if os.path.isdir(mod_mirror_raw) and not is_symlink_or_reparse(mod_mirror_raw) and not os.listdir(mod_mirror_raw):
                            os.rmdir(mod_mirror_raw)
                    except OSError:
                        pass

    def cleanup(self) -> None:
        if self._backup_dir is not None and os.path.lexists(str(self._backup_dir)):
            try:
                ins_robust_rmtree(str(self._backup_dir))
            except OSError:
                pass
        _remove_empty_temp_root(self._yscb_root)


def _remove_empty_temp_root(yscb_root: HostPath) -> None:
    temp_root = try_resolve_contained_subpath(yscb_root, ".temp")
    if temp_root is not None:
        raw_temp = str(temp_root)
        if os.path.isdir(raw_temp) and not is_symlink_or_reparse(raw_temp):
            try:
                os.rmdir(raw_temp)
            except OSError:
                pass


def _core_first_key(mod_id: ModuleId) -> tuple[int, str]:
    return (0 if mod_id == _CORE_MODULE_ID else 1, mod_id.value)


def _check_cancel(cancel_token: Optional[CancellationToken]) -> None:
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()


def _resolve_wheel_cache_dir(yscb_root: HostPath) -> Optional[HostPath]:
    for parts in ((".cache", "wheels"), (".mirror", "wheels")):
        cand = try_resolve_contained_subpath(yscb_root, *parts)
        if cand is not None and os.path.isdir(str(cand)) and not is_symlink_or_reparse(str(cand)):
            return cand
    return None


def _select_same_triplet_active_fallback(
    requested_version: SemVer4,
    provider: ProviderClient,
    mirror: MirrorStore,
    module_id: ModuleId,
    provider_url: str,
) -> Optional[tuple[SemVer4, Optional[IndexReleaseRecord]]]:
    if requested_version.is_build:
        return None
    try:
        idx = provider.fetch_index(module_id, provider=provider_url if provider_url else None)
        mirror.save_index_cache(idx)
    except YscbError as exc:
        if exc.detail.code in INS_NON_FALLBACK_ERROR_CODES:
            raise
        cached = mirror.load_index_cache(module_id)
        if cached is None:
            return None
        idx = cached

    req_triple = requested_version.triple()
    candidates: list[SemVer4] = []
    for cand_v in idx.versions:
        if cand_v.is_build or cand_v.triple() != req_triple:
            continue
        rec = idx.releases.get(str(cand_v))
        if rec is not None and (rec.status != "active" or rec.yanked):
            continue
        if cand_v not in candidates:
            candidates.append(cand_v)
    for rec in idx.releases.values():
        cand_v = rec.version
        if (
            not cand_v.is_build
            and cand_v.triple() == req_triple
            and rec.status == "active"
            and not rec.yanked
            and cand_v not in candidates
        ):
            candidates.append(cand_v)

    if not candidates:
        return None
    best_v = max(candidates)
    return (best_v, idx.releases.get(str(best_v)))


def _replace_dir_with_retry(src_raw: str, dst_raw: str) -> None:
    last_exc: Optional[OSError] = None
    for attempt in range(5):
        try:
            os.replace(src_raw, dst_raw)
            return
        except OSError as exc:
            last_exc = exc
            if attempt < 4:
                time.sleep(0.015 * (attempt + 1))
    if last_exc is not None:
        raise last_exc


def _capture_tx_workspace_guard(host_dir: HostPath, yscb_root: HostPath, seq: int) -> _InsTxWorkspaceGuard:
    temp_root = resolve_contained_subpath(yscb_root, ".temp")
    os.makedirs(str(temp_root), exist_ok=True)
    guard_dir = resolve_contained_subpath(temp_root, f"tx_guard_{os.getpid()}_{seq}")
    if os.path.lexists(str(guard_dir)):
        ins_robust_rmtree(str(guard_dir))
    os.makedirs(str(guard_dir), exist_ok=False)

    try:
        host_cfg_hp = resolve_contained_subpath(host_dir, "yscb.config.json")
        raw_host_cfg = str(host_cfg_hp)
        had_host = os.path.lexists(raw_host_cfg)
        host_bytes: Optional[bytes] = None
        if had_host:
            if is_symlink_or_reparse(raw_host_cfg) or has_symlink_raw_path(raw_host_cfg):
                raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlinked yscb.config.json: '{host_cfg_hp}'")
            host_bytes = read_nofollow_regular_bytes(raw_host_cfg, max_bytes=MAX_JSON_FILE_BYTES)
            if host_bytes is None:
                raise YscbError(ErrorCode.CONFIG_INVALID, f"Unreadable yscb.config.json: '{host_cfg_hp}'")

        area_present: dict[str, bool] = {}
        for area_key, subdir_name in _TX_GUARD_AREAS:
            live_hp = resolve_contained_subpath(yscb_root, subdir_name)
            raw_live = str(live_hp)
            if not os.path.lexists(raw_live):
                area_present[area_key] = False
                continue
            if is_symlink_or_reparse(raw_live) or has_symlink_raw_path(raw_live):
                raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlinked workspace directory: '{live_hp}'")
            area_present[area_key] = True
            bak_area = resolve_contained_subpath(guard_dir, area_key)
            os.makedirs(str(bak_area), exist_ok=True)
            for cur_dir, entries in walk_nonsymlink_dir_tree(raw_live):
                rel_cur = os.path.relpath(cur_dir, raw_live)
                dir_parts = () if rel_cur in ("", ".") else tuple(Path(rel_cur).parts)
                dst_sub = resolve_contained_subpath(bak_area, *dir_parts) if dir_parts else bak_area
                os.makedirs(str(dst_sub), exist_ok=True)
                for ent in entries:
                    if ent.name.startswith(IGNORED_FS_PREFIXES) or is_atomic_staging_filename(ent.name):
                        continue
                    if ent.is_symlink() or is_symlink_or_reparse(ent.path):
                        raise YscbError(
                            ErrorCode.SECURITY_GATED,
                            f"Refusing symlink inside '{live_hp}': '{ent.path}'",
                        )
                    if ent.is_file(follow_symlinks=False):
                        f_bytes = read_nofollow_regular_bytes(ent.path)
                        if f_bytes is None:
                            if has_symlink_raw_path(ent.path):
                                raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlinked file: '{ent.path}'")
                            raise YscbError(ErrorCode.CONFIG_INVALID, f"Unreadable regular file: '{ent.path}'")
                        dst_file_hp = resolve_contained_subpath(dst_sub, ent.name)
                        atomic_write_bytes(dst_file_hp, f_bytes)
        return _InsTxWorkspaceGuard(
            guard_dir=guard_dir,
            had_host_cfg=had_host,
            host_cfg_bytes=host_bytes,
            area_present=area_present,
        )
    except BaseException:
        if os.path.lexists(str(guard_dir)):
            try:
                ins_robust_rmtree(str(guard_dir))
            except OSError:
                pass
        _remove_empty_temp_root(yscb_root)
        raise


def _sync_guard_backup_in_place(
    live_hp: HostPath,
    bak_area: Optional[HostPath],
) -> None:
    raw_live = str(live_hp)
    assert_no_symlink_raw_path(raw_live)
    target_dirs: set[str] = set()
    target_files: dict[str, bytes] = {}
    if bak_area is not None and os.path.isdir(str(bak_area)):
        raw_bak = str(bak_area)
        for cur_dir, entries in walk_nonsymlink_dir_tree(raw_bak):
            rel_cur = os.path.relpath(cur_dir, raw_bak)
            dir_parts = () if rel_cur in ("", ".") else tuple(Path(rel_cur).parts)
            for idx in range(1, len(dir_parts) + 1):
                target_dirs.add("/".join(dir_parts[:idx]))
            for ent in entries:
                if ent.is_file(follow_symlinks=False):
                    f_bytes = read_nofollow_regular_bytes(ent.path)
                    if f_bytes is not None:
                        target_files["/".join((*dir_parts, ent.name))] = f_bytes

    if bak_area is not None:
        os.makedirs(raw_live, exist_ok=True)
        for rel_dir in sorted(target_dirs, key=lambda d: (d.count("/"), d)):
            sub_hp = resolve_contained_subpath(live_hp, *rel_dir.split("/"))
            raw_sub = str(sub_hp)
            if is_symlink_or_reparse(raw_sub):
                raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink inside '{live_hp}': '{raw_sub}'")
            if os.path.lexists(raw_sub) and not os.path.isdir(raw_sub):
                silent_unlink(sub_hp)
            os.makedirs(raw_sub, exist_ok=True)
        for rel_posix, f_bytes in sorted(target_files.items()):
            f_hp = resolve_contained_subpath(live_hp, *rel_posix.split("/"))
            raw_f = str(f_hp)
            if is_symlink_or_reparse(raw_f):
                raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink inside '{live_hp}': '{raw_f}'")
            if os.path.isdir(raw_f):
                ins_robust_rmtree(raw_f)
            atomic_write_bytes(f_hp, f_bytes)

    if not os.path.isdir(raw_live):
        return
    existing_dirs: list[tuple[str, str]] = []
    for cur_dir, entries in walk_nonsymlink_dir_tree(raw_live):
        rel_cur = os.path.relpath(cur_dir, raw_live)
        dir_parts = () if rel_cur in ("", ".") else tuple(Path(rel_cur).parts)
        if dir_parts:
            existing_dirs.append(("/".join(dir_parts), cur_dir))
        for ent in entries:
            if ent.name.startswith(IGNORED_FS_PREFIXES) or is_atomic_staging_filename(ent.name):
                continue
            if ent.is_symlink() or is_symlink_or_reparse(ent.path):
                raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink inside '{live_hp}': '{ent.path}'")
            if ent.is_file(follow_symlinks=False):
                rel_file = "/".join((*dir_parts, ent.name))
                if bak_area is None or rel_file not in target_files:
                    silent_unlink(resolve_contained_subpath(live_hp, *rel_file.split("/")))
    for rel_dir, raw_dir in sorted(existing_dirs, key=lambda item: item[0].count("/"), reverse=True):
        if bak_area is None or rel_dir not in target_dirs:
            try:
                os.rmdir(raw_dir)
            except OSError:
                pass
    if bak_area is None:
        try:
            os.rmdir(raw_live)
        except OSError:
            pass


def _restore_single_tx_guard_area(
    yscb_root: HostPath,
    guard: _InsTxWorkspaceGuard,
    area_key: str,
    subdir_name: str,
    seq: int,
) -> None:
    live_hp = resolve_contained_subpath(yscb_root, subdir_name)
    raw_live = str(live_hp)
    stage_hp = resolve_contained_subpath(yscb_root, f".staging_txguard_{area_key}_{os.getpid()}_{seq}")
    prev_hp = resolve_contained_subpath(yscb_root, f".tmp_txprev_{area_key}_{os.getpid()}_{seq}")
    raw_stage = str(stage_hp)
    raw_prev = str(prev_hp)
    for residual in (raw_stage, raw_prev):
        if os.path.lexists(residual):
            ins_robust_rmtree(residual)
    moved_prev = False
    try:
        if guard.area_present.get(area_key, False):
            bak_area = resolve_contained_subpath(guard.guard_dir, area_key)
            if os.path.isdir(str(bak_area)):
                shutil.copytree(str(bak_area), raw_stage, symlinks=False)
            else:
                os.makedirs(raw_stage, exist_ok=True)
            if os.path.lexists(raw_live):
                if is_symlink_or_reparse(raw_live):
                    ins_robust_rmtree(raw_live)
                else:
                    try:
                        _replace_dir_with_retry(raw_live, raw_prev)
                        moved_prev = True
                    except OSError:
                        if not os.path.isdir(raw_live) or is_symlink_or_reparse(raw_live):
                            raise
                        _sync_guard_backup_in_place(live_hp, bak_area)
                        return
            try:
                _replace_dir_with_retry(raw_stage, raw_live)
            except OSError:
                if moved_prev and os.path.lexists(raw_prev) and not os.path.lexists(raw_live):
                    try:
                        _replace_dir_with_retry(raw_prev, raw_live)
                    except OSError:
                        pass
                raise
        elif os.path.lexists(raw_live):
            if is_symlink_or_reparse(raw_live):
                ins_robust_rmtree(raw_live)
            else:
                try:
                    ins_robust_rmtree(raw_live)
                except OSError:
                    if not os.path.isdir(raw_live) or is_symlink_or_reparse(raw_live):
                        raise
                    _sync_guard_backup_in_place(live_hp, None)
    finally:
        for residual in (raw_stage, raw_prev):
            if os.path.lexists(residual):
                try:
                    ins_robust_rmtree(residual)
                except OSError:
                    pass


def _restore_tx_workspace_guard(
    host_dir: HostPath,
    yscb_root: HostPath,
    guard: _InsTxWorkspaceGuard,
    seq: int,
) -> None:
    first_err: Optional[BaseException] = None
    for area_key, subdir_name in _TX_GUARD_AREAS:
        try:
            _restore_single_tx_guard_area(yscb_root, guard, area_key, subdir_name, seq)
        except BaseException as area_exc:
            if first_err is None:
                first_err = area_exc

    try:
        host_cfg_hp = resolve_contained_subpath(host_dir, "yscb.config.json")
        if guard.had_host_cfg and guard.host_cfg_bytes is not None:
            atomic_write_bytes(host_cfg_hp, guard.host_cfg_bytes)
        elif not guard.had_host_cfg:
            silent_unlink(host_cfg_hp)
    except BaseException as cfg_exc:
        if first_err is None:
            first_err = cfg_exc

    if first_err is not None:
        raise first_err


class OfflinePackageEngine:
    """Pure offline batch transactional package engine."""

    def __init__(
        self,
        *,
        host_dir: HostPath,
        yscb_root: HostPath,
        config_store: ConfigStore,
        snapshot_vault: SnapshotVault,
        env_pool: ImmutableVenvPool,
        vfs: KernelVfs,
    ) -> None:
        if not isinstance(host_dir, HostPath):
            raise ValueError(f"OfflinePackageEngine.host_dir must be HostPath, got {host_dir!r}")
        if not isinstance(yscb_root, HostPath):
            raise ValueError(f"OfflinePackageEngine.yscb_root must be HostPath, got {yscb_root!r}")
        if not isinstance(config_store, ConfigStore):
            raise ValueError(
                f"OfflinePackageEngine.config_store must be ConfigStore, got {config_store!r}"
            )
        if not isinstance(snapshot_vault, SnapshotVault):
            raise ValueError(
                f"OfflinePackageEngine.snapshot_vault must be SnapshotVault, got {snapshot_vault!r}"
            )
        if not isinstance(env_pool, ImmutableVenvPool):
            raise ValueError(
                f"OfflinePackageEngine.env_pool must be ImmutableVenvPool, got {env_pool!r}"
            )
        if not isinstance(vfs, KernelVfs):
            raise ValueError(f"OfflinePackageEngine.vfs must be KernelVfs, got {vfs!r}")
        assert_no_symlink_raw_path(str(host_dir))
        assert_no_symlink_raw_path(str(yscb_root))
        self._host_dir = host_dir
        self._yscb_root = yscb_root
        self._config_store = config_store
        self._snapshot_vault = snapshot_vault
        self._env_pool = env_pool
        self._vfs = vfs
        self._mirror = MirrorStore(yscb_root=yscb_root)
        self._solver = DependencySolver()
        self._deployer = AtomicPackageDeployer(
            yscb_root=yscb_root,
            config_store=config_store,
            vfs=vfs,
        )
        self._tx_lock = threading.Lock()
        self._tx_seq = 0
        self._op_lock = threading.RLock()
        self._op_lock_depth = 0

    def _next_tx_seq(self) -> int:
        with self._tx_lock:
            self._tx_seq += 1
            return self._tx_seq

    @contextlib.contextmanager
    def _engine_tx_lock(self, cancel_token: Optional[CancellationToken] = None) -> Iterator[None]:
        with self._op_lock:
            file_lock: Optional[FileLock] = None
            if self._op_lock_depth == 0:
                locks_dir = resolve_contained_subpath(self._yscb_root, ".cache", "locks")
                os.makedirs(str(locks_dir), exist_ok=True)
                lock_hp = resolve_contained_subpath(locks_dir, "package_engine.lock")
                file_lock = FileLock(lock_hp, allow_transitions=False)
                file_lock.acquire(
                    shared=False,
                    blocking=True,
                    timeout_sec=_ENGINE_LOCK_TIMEOUT_SEC,
                    cancel_token=cancel_token,
                )
            self._op_lock_depth += 1
            try:
                yield
            finally:
                self._op_lock_depth -= 1
                if file_lock is not None:
                    file_lock.release()

    def _begin_workspace_tx_protection(self, tag: str) -> tuple[str, Optional[_InsTxWorkspaceGuard]]:
        snap = self._snapshot_vault.create_snapshot(tag)
        tx_guard: Optional[_InsTxWorkspaceGuard] = (
            _capture_tx_workspace_guard(self._host_dir, self._yscb_root, self._next_tx_seq())
            if snap.reused
            else None
        )
        return (snap.snapshot_id, tx_guard)

    @contextlib.contextmanager
    def migration_rollback_scope(self) -> Iterator[Callable[[], None]]:
        """Capture an exact pre-transaction workspace guard for post-deploy @on_migrate rollback."""
        with self._engine_tx_lock():
            guard = _capture_tx_workspace_guard(self._host_dir, self._yscb_root, self._next_tx_seq())

        def _restore_pre_transaction() -> None:
            with self._engine_tx_lock():
                _restore_tx_workspace_guard(self._host_dir, self._yscb_root, guard, self._next_tx_seq())
                self._config_store.reload()
                self._reconcile_materialized_modules_from_mirror()

        try:
            yield _restore_pre_transaction
        finally:
            with self._engine_tx_lock():
                self._cleanup_tx_guard(guard)

    def _cleanup_tx_guard(
        self,
        tx_guard: Optional[_InsTxWorkspaceGuard],
        mirror_journal: Optional[_InsMirrorTxJournal] = None,
    ) -> None:
        if mirror_journal is not None:
            mirror_journal.cleanup()
        if tx_guard is not None and os.path.lexists(str(tx_guard.guard_dir)):
            try:
                ins_robust_rmtree(str(tx_guard.guard_dir))
            except OSError:
                pass
        _remove_empty_temp_root(self._yscb_root)

    def _is_module_healthy_on_disk(self, module_id: ModuleId, expected_version: SemVer4) -> bool:
        mf_hp = try_resolve_contained_subpath(
            self._yscb_root,
            ".modules",
            module_id.value,
            "manifest.json",
        )
        if mf_hp is None:
            return False
        try:
            mf = ins_read_manifest_file(mf_hp, expected_module_id=module_id)
        except YscbError:
            return False
        if mf is None or mf.version != expected_version:
            return False
        entry_parts = [s for s in mf.entry.replace("\\", "/").split("/") if s]
        if not entry_parts:
            return False
        entry_hp = try_resolve_contained_subpath(
            self._yscb_root,
            ".modules",
            module_id.value,
            *entry_parts,
        )
        return entry_hp is not None and os.path.isfile(str(entry_hp))

    def _list_materialized_module_ids(self) -> tuple[ModuleId, ...]:
        mods_dir = try_resolve_contained_subpath(self._yscb_root, ".modules")
        if mods_dir is None or not os.path.isdir(str(mods_dir)):
            return ()
        found: list[ModuleId] = []
        try:
            with os.scandir(str(mods_dir)) as it:
                for ent in it:
                    if ent.name.startswith(".") or ent.name in INS_RESERVED_NON_MODULE_IDS or ent.is_symlink():
                        continue
                    if ent.is_dir(follow_symlinks=False) and is_valid_relative_segment(ent.name):
                        try:
                            found.append(ModuleId(ent.name))
                        except ValueError:
                            continue
        except OSError:
            return ()
        found.sort(key=_core_first_key)
        return tuple(found)

    def _read_materialized_disk_versions(self) -> dict[ModuleId, SemVer4]:
        versions: dict[ModuleId, SemVer4] = {}
        for mod_id in self._list_materialized_module_ids():
            mf_hp = try_resolve_contained_subpath(
                self._yscb_root,
                ".modules",
                mod_id.value,
                "manifest.json",
            )
            if mf_hp is None:
                continue
            try:
                mf = ins_read_manifest_file(mf_hp, expected_module_id=mod_id)
            except YscbError:
                continue
            if mf is not None and self._is_module_healthy_on_disk(mod_id, mf.version):
                versions[mod_id] = mf.version
        return versions

    def _read_installed_manifest(self, module_id: ModuleId, version: SemVer4) -> Optional[ModuleManifest]:
        mf_hp = try_resolve_contained_subpath(
            self._yscb_root,
            ".modules",
            module_id.value,
            "manifest.json",
        )
        if mf_hp is not None:
            mf = ins_read_manifest_file(mf_hp, expected_module_id=module_id)
            if mf is not None and (mf.version == version or version.is_build):
                return mf
        if self._mirror.has_package(module_id, version):
            zip_hp = self._mirror.get_package_path(module_id, version)
            mf_zip = ins_peek_zip_manifest(
                zip_hp,
                expected_module_id=module_id,
                expected_version=None if version.is_build else version,
            )
            idx = self._mirror.load_index_cache(module_id)
            rel_rec = idx.releases.get(str(version)) if idx is not None else None
            if ins_has_dependencies_override(rel_rec) and rel_rec is not None:
                return ins_override_manifest_dependencies(mf_zip, rel_rec.dependencies)
            return mf_zip
        return None

    def _lookup_release_record(
        self,
        module_id: ModuleId,
        version: SemVer4,
        provider_client: ProviderClient,
        eff_provider: str,
    ) -> Optional[IndexReleaseRecord]:
        if version.is_build:
            return None
        cached_idx = self._mirror.load_index_cache(module_id)
        if ins_is_provider_offline(provider_client):
            if cached_idx is not None and str(version) in cached_idx.releases:
                return cached_idx.releases[str(version)]
            try:
                local_idx = provider_client.fetch_index(
                    module_id,
                    provider=eff_provider if eff_provider else None,
                )
                self._mirror.save_index_cache(local_idx)
                return local_idx.releases.get(str(version))
            except YscbError as exc:
                if exc.detail.code in INS_NON_FALLBACK_ERROR_CODES:
                    raise
                return cached_idx.releases.get(str(version)) if cached_idx is not None else None

        try:
            fetched_idx = provider_client.fetch_index(
                module_id,
                provider=eff_provider if eff_provider else None,
            )
            self._mirror.save_index_cache(fetched_idx)
            return fetched_idx.releases.get(str(version))
        except YscbError as exc:
            if exc.detail.code in INS_NON_FALLBACK_ERROR_CODES:
                raise
            return cached_idx.releases.get(str(version)) if cached_idx is not None else None

    def _stage_to_mirror(
        self,
        module_id: ModuleId,
        version: SemVer4,
        rel_rec: Optional[IndexReleaseRecord],
        provider_client: ProviderClient,
        eff_provider: str,
        *,
        force_fetch: bool,
        ignore_sha256: bool,
        mirror_journal: Optional[_InsMirrorTxJournal] = None,
    ) -> _InsPlannedPackage:
        mirror_zip = self._mirror.get_package_path(module_id, version)
        has_mirror_pkg = self._mirror.has_package(module_id, version)
        need_fetch = force_fetch or version.is_build or not has_mirror_pkg

        expected_sha: Optional[str] = None
        if not version.is_build:
            if rel_rec is not None and rel_rec.sha256:
                expected_sha = rel_rec.sha256
            elif (
                not ignore_sha256
                and ins_is_http_provider(eff_provider)
                and not ins_is_provider_offline(provider_client)
                and (need_fetch or rel_rec is not None)
            ):
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Missing SHA-256 digest in index.json for '{module_id}@{version}'.",
                )

        if need_fetch:
            if mirror_journal is not None:
                mirror_journal.record_before_fetch(mirror_zip)
            provider_client.fetch_package_zip(
                module_id,
                version,
                mirror_zip,
                provider=eff_provider if eff_provider else None,
                expected_sha256=expected_sha,
                ignore_sha256=ignore_sha256 or version.is_build,
            )
        self._mirror.verify_zip_integrity(
            mirror_zip,
            expected_sha256=expected_sha,
            ignore_sha256=ignore_sha256 or version.is_build or expected_sha is None,
        )
        mf = ins_peek_zip_manifest(
            mirror_zip,
            expected_module_id=module_id,
            expected_version=version,
        )
        if ins_has_dependencies_override(rel_rec) and rel_rec is not None:
            mf = ins_override_manifest_dependencies(mf, rel_rec.dependencies)
        return _InsPlannedPackage(
            module_id=module_id,
            version=version,
            release_record=rel_rec,
            provider=eff_provider,
            zip_path=mirror_zip,
            manifest=mf,
        )

    def _has_unsatisfied_effective_deps(
        self,
        merged_versions: Mapping[ModuleId, SemVer4],
        staged_by_id: Mapping[ModuleId, _InsPlannedPackage],
    ) -> bool:
        for mod_id, ver in merged_versions.items():
            staged = staged_by_id.get(mod_id)
            mf = staged.manifest if staged is not None else self._read_installed_manifest(mod_id, ver)
            if mf is None:
                continue
            for dep_id, dep_c in mf.dependencies.items():
                cur_dep_ver = merged_versions.get(dep_id)
                if cur_dep_ver is None or (not cur_dep_ver.is_build and not dep_c.satisfies(cur_dep_ver)):
                    return True
        return False

    def _solve_and_stage_constrained_plan(
        self,
        reqs: Sequence[PackageRequest],
        cur_installed: Mapping[ModuleId, SemVer4],
        provider_client: ProviderClient,
        prov_lookup: Callable[[ModuleId], str],
        *,
        same_major_only: bool,
        only_changed: bool,
        force_fetch: bool,
        ignore_sha256: bool,
        mirror_journal: _InsMirrorTxJournal,
    ) -> list[_InsPlannedPackage]:
        staged_cache: dict[tuple[ModuleId, SemVer4], _InsPlannedPackage] = {}
        for _round in range(_MAX_RECONCILE_ROUNDS):
            plan = self._solver.resolve_install_plan(
                reqs,
                cur_installed,
                provider_client,
                self._mirror,
                same_major_only=same_major_only,
            )
            selected_plan = (
                {
                    m: (v, rec)
                    for m, (v, rec) in plan.items()
                    if cur_installed.get(m) != v or v.is_build
                }
                if only_changed
                else dict(plan)
            )
            round_items: list[_InsPlannedPackage] = []
            merged_versions = dict(cur_installed)
            for mod_id, (ver, rel_rec) in selected_plan.items():
                pair_key = (mod_id, ver)
                cached_pkg = staged_cache.get(pair_key)
                if cached_pkg is None:
                    eff_prov = prov_lookup(mod_id)
                    eff_rel = rel_rec or self._lookup_release_record(
                        mod_id,
                        ver,
                        provider_client,
                        eff_prov,
                    )
                    cached_pkg = self._stage_to_mirror(
                        mod_id,
                        ver,
                        eff_rel,
                        provider_client,
                        eff_prov,
                        force_fetch=force_fetch,
                        ignore_sha256=ignore_sha256,
                        mirror_journal=mirror_journal,
                    )
                    staged_cache[pair_key] = cached_pkg
                round_items.append(cached_pkg)
                merged_versions[mod_id] = ver

            staged_by_id = {it.module_id: it for it in round_items}
            if not self._has_unsatisfied_effective_deps(merged_versions, staged_by_id):
                return round_items

        raise YscbError(
            ErrorCode.DEPENDENCY_CONFLICT,
            "Exceeded maximum transitive dependency resolution rounds.",
        )

    def _reconcile_restore_closure(
        self,
        staged_items: list[_InsPlannedPackage],
        merged_versions: dict[ModuleId, SemVer4],
        provider_client: ProviderClient,
        prov_lookup: Callable[[ModuleId], str],
        *,
        force_fetch: bool,
        ignore_sha256: bool,
        mirror_journal: _InsMirrorTxJournal,
    ) -> list[_InsPlannedPackage]:
        base_versions: dict[ModuleId, SemVer4] = dict(merged_versions)
        base_staged: dict[ModuleId, _InsPlannedPackage] = {
            it.module_id: it for it in staged_items
        }
        staged_cache: dict[tuple[ModuleId, SemVer4], _InsPlannedPackage] = {}
        seen_mods: set[ModuleId] = set(base_versions.keys())
        for _round in range(_MAX_RECONCILE_ROUNDS):
            prov_overrides = {m: prov_lookup(m) for m in seen_mods}
            healed = ins_reconcile_installed_with_overrides(
                base_versions,
                provider_client,
                self._mirror,
                prov_overrides,
                same_major_only=False,
            )
            if not healed:
                return staged_items
            seen_mods.update(healed.keys())
            cand_versions: dict[ModuleId, SemVer4] = dict(base_versions)
            cand_staged: dict[ModuleId, _InsPlannedPackage] = dict(base_staged)
            cand_list: list[_InsPlannedPackage] = [
                it for it in staged_items if it.module_id not in healed
            ]
            for h_mod, h_ver in healed.items():
                pair_key = (h_mod, h_ver)
                h_staged = staged_cache.get(pair_key)
                if h_staged is None:
                    h_prov = prov_lookup(h_mod)
                    h_rel = self._lookup_release_record(h_mod, h_ver, provider_client, h_prov)
                    h_staged = self._stage_to_mirror(
                        h_mod,
                        h_ver,
                        h_rel,
                        provider_client,
                        h_prov,
                        force_fetch=force_fetch,
                        ignore_sha256=ignore_sha256,
                        mirror_journal=mirror_journal,
                    )
                    staged_cache[pair_key] = h_staged
                cand_versions[h_mod] = h_ver
                cand_staged[h_mod] = h_staged
                cand_list.append(h_staged)
            if not self._has_unsatisfied_effective_deps(cand_versions, cand_staged):
                merged_versions.clear()
                merged_versions.update(cand_versions)
                return cand_list
        raise YscbError(
            ErrorCode.DEPENDENCY_CONFLICT,
            "Exceeded maximum transitive dependency reconciliation rounds.",
        )

    def _ensure_tier1_envs(
        self,
        all_manifests: Sequence[ModuleManifest],
        *,
        offline: bool,
        cancel_token: Optional[CancellationToken],
    ) -> Mapping[ModuleId, EnvSpec]:
        env_specs = ImmutableVenvPool.resolve_group_specs(all_manifests)
        wheel_dir = _resolve_wheel_cache_dir(self._yscb_root)
        seen_hashes: set[str] = set()
        for mod_id in sorted(env_specs.keys(), key=_core_first_key):
            spec = env_specs[mod_id]
            h_str = str(spec.env_hash)
            if h_str in seen_hashes:
                continue
            seen_hashes.add(h_str)
            _check_cancel(cancel_token)
            self._env_pool.ensure_env(
                spec,
                offline=offline,
                wheel_cache_dir=wheel_dir,
                cancel_token=cancel_token,
            )
        return env_specs

    def _reconcile_materialized_modules_from_mirror(self) -> None:
        self._config_store.reload()
        restored_cfg = self._config_store.load_host_config()
        desired_ids = set(restored_cfg.installed_modules.keys())
        for disk_mod in self._list_materialized_module_ids():
            if disk_mod not in desired_ids and disk_mod != _CORE_MODULE_ID:
                try:
                    self._deployer.remove_module(disk_mod, purge_level=PurgeLevel.NONE)
                except (OSError, YscbError):
                    pass
        for mod_id in sorted(desired_ids, key=_core_first_key):
            rec = restored_cfg.installed_modules[mod_id]
            if self._mirror.has_package(mod_id, rec.version):
                zip_hp = self._mirror.get_package_path(mod_id, rec.version)
                idx = self._mirror.load_index_cache(mod_id)
                rel_ov = idx.releases.get(str(rec.version)) if idx is not None else None
                try:
                    ins_materialize_module(
                        self._deployer,
                        mod_id,
                        zip_hp,
                        release_override=rel_ov,
                        deploy_configurable=False,
                    )
                except (OSError, YscbError):
                    pass

    def _rollback_write_failure_quietly(
        self,
        snapshot_id: str,
        tx_guard: Optional[_InsTxWorkspaceGuard],
        mirror_journal: Optional[_InsMirrorTxJournal] = None,
    ) -> None:
        if mirror_journal is not None:
            try:
                mirror_journal.restore_on_failure()
            except (OSError, ValueError, YscbError):
                pass
        if tx_guard is None and not snapshot_id:
            return
        try:
            if tx_guard is not None:
                _restore_tx_workspace_guard(
                    self._host_dir,
                    self._yscb_root,
                    tx_guard,
                    self._next_tx_seq(),
                )
            elif snapshot_id:
                self._snapshot_vault.restore_snapshot(snapshot_id)
        except (OSError, ValueError, YscbError):
            pass
        try:
            self._reconcile_materialized_modules_from_mirror()
        except (OSError, ValueError, YscbError):
            pass

    def _execute_planned_deployment(
        self,
        host_cfg: HostConfig,
        planned_items: Sequence[_InsPlannedPackage],
        explicit_requested_ids: frozenset[ModuleId],
        snapshot_id: str,
        *,
        force_materialize: bool,
        eff_offline: bool,
        cancel_token: Optional[CancellationToken],
        baseline_versions: Optional[Mapping[ModuleId, SemVer4]] = None,
        prune_unlisted_modules: bool = False,
    ) -> DeploymentReport:
        cur_versions: dict[ModuleId, SemVer4] = (
            dict(baseline_versions)
            if baseline_versions is not None
            else {m: r.version for m, r in host_cfg.installed_modules.items()}
        )
        planned_by_id: dict[ModuleId, _InsPlannedPackage] = {
            item.module_id: item for item in planned_items
        }
        final_versions: dict[ModuleId, SemVer4] = (
            {m: p.version for m, p in planned_by_id.items()}
            if prune_unlisted_modules
            else {
                **cur_versions,
                **{m: p.version for m, p in planned_by_id.items()},
            }
        )

        all_manifests: list[ModuleManifest] = []
        for mod_id in sorted(final_versions.keys(), key=_core_first_key):
            if mod_id in planned_by_id:
                all_manifests.append(planned_by_id[mod_id].manifest)
            else:
                existing_mf = self._read_installed_manifest(mod_id, final_versions[mod_id])
                if existing_mf is not None:
                    all_manifests.append(existing_mf)

        env_specs = self._ensure_tier1_envs(
            all_manifests,
            offline=eff_offline,
            cancel_token=cancel_token,
        )

        _check_cancel(cancel_token)
        transitions: list[UpgradeTransition] = []
        installed_out: dict[ModuleId, SemVer4] = {}
        onboarding: dict[ModuleId, tuple[str, ...]] = {}
        reconciled_list: list[ModuleId] = []
        updated_records: dict[ModuleId, InstalledModuleRecord] = (
            {} if prune_unlisted_modules else dict(host_cfg.installed_modules)
        )
        now_str = ins_utc_now_iso()

        for item in planned_items:
            _check_cancel(cancel_token)
            mod_id = item.module_id
            old_ver = cur_versions.get(mod_id)
            already_same = (
                old_ver is not None
                and old_ver == item.version
                and not item.version.is_build
                and self._is_module_healthy_on_disk(mod_id, item.version)
            )
            if force_materialize or not already_same:
                mat_mf = self._deployer.materialize_module(
                    mod_id,
                    item.zip_path,
                    release_override=item.release_record,
                )
            else:
                mat_mf = item.manifest

            installed_out[mod_id] = item.version
            if mat_mf.onboarding and (old_ver is None or old_ver != item.version or force_materialize):
                onboarding[mod_id] = mat_mf.onboarding
            if old_ver is None or old_ver != item.version or item.version.is_build:
                is_upg = old_ver is not None and item.version > old_ver
                transitions.append(
                    UpgradeTransition(
                        module_id=mod_id,
                        old_version=old_ver,
                        new_version=item.version,
                        is_upgrade=is_upg,
                    )
                )
            if mod_id not in explicit_requested_ids and (old_ver is None or old_ver != item.version):
                reconciled_list.append(mod_id)
            updated_records[mod_id] = InstalledModuleRecord(
                version=item.version,
                installed_at=now_str,
                provider=item.provider,
            )

        removed_orphans: list[ModuleId] = []
        if prune_unlisted_modules:
            for disk_mod in self._list_materialized_module_ids():
                if disk_mod not in final_versions and disk_mod != _CORE_MODULE_ID:
                    self._deployer.remove_module(disk_mod, purge_level=PurgeLevel.NONE)
                    removed_orphans.append(disk_mod)

        self._config_store.save_host_config(
            HostConfig(
                yscb_root=host_cfg.yscb_root,
                default_provider=host_cfg.default_provider,
                installed_modules=updated_records,
            )
        )
        return DeploymentReport(
            installed=installed_out,
            removed=tuple(removed_orphans),
            transitions=tuple(transitions),
            env_specs=env_specs,
            snapshot_id=snapshot_id,
            reconciled_dependencies=tuple(reconciled_list),
            onboarding_hints=onboarding,
        )

    def install(
        self,
        requests: Sequence[PackageRequest],
        *,
        force: bool = False,
        ignore_sha256: bool = False,
        offline: bool = False,
        cancel_token: Optional[CancellationToken] = None,
    ) -> DeploymentReport:
        req_tuple = require_typed_tuple(requests, PackageRequest, "requests")
        for req_item in req_tuple:
            ins_assert_not_reserved_module_id(req_item.module_id, label="OfflinePackageEngine.install module_id")
        require_pure_bool(force, "force")
        require_pure_bool(ignore_sha256, "ignore_sha256")
        require_pure_bool(offline, "offline")
        eff_offline = offline or is_public_env_truthy("YSCB_OFFLINE")
        _check_cancel(cancel_token)

        with self._engine_tx_lock(cancel_token):
            host_cfg = self._config_store.load_host_config()
            if not req_tuple:
                cur_mfs = [
                    mf
                    for m, r in host_cfg.installed_modules.items()
                    if (mf := self._read_installed_manifest(m, r.version)) is not None
                ]
                return DeploymentReport(
                    installed={},
                    removed=(),
                    transitions=(),
                    env_specs=ImmutableVenvPool.resolve_group_specs(cur_mfs),
                    snapshot_id=None,
                )

            mirror_journal = _InsMirrorTxJournal(self._yscb_root, self._next_tx_seq())
            snap_id = ""
            tx_guard: Optional[_InsTxWorkspaceGuard] = None
            try:
                provider_client = ProviderClient(
                    yscb_root=self._yscb_root,
                    host_dir=self._host_dir,
                    default_provider=host_cfg.default_provider,
                    offline=eff_offline,
                )
                cur_installed = {m: r.version for m, r in host_cfg.installed_modules.items()}
                prov_overrides: dict[ModuleId, str] = {}
                explicit_ids: set[ModuleId] = set()
                for req in req_tuple:
                    explicit_ids.add(req.module_id)
                    if req.provider_override is not None and req.provider_override.strip():
                        prov_overrides[req.module_id] = req.provider_override.strip()

                def _resolve_mod_provider(target_mod: ModuleId) -> str:
                    _check_cancel(cancel_token)
                    return (
                        prov_overrides.get(target_mod)
                        or (
                            host_cfg.installed_modules[target_mod].provider
                            if target_mod in host_cfg.installed_modules
                            else ""
                        )
                        or host_cfg.default_provider
                    )

                staged_items = self._solve_and_stage_constrained_plan(
                    req_tuple,
                    cur_installed,
                    provider_client,
                    _resolve_mod_provider,
                    same_major_only=False,
                    only_changed=False,
                    force_fetch=force,
                    ignore_sha256=ignore_sha256,
                    mirror_journal=mirror_journal,
                )

                ordered_items = sorted(
                    staged_items,
                    key=lambda it: (0 if it.module_id == _CORE_MODULE_ID else 1, staged_items.index(it)),
                )
                snap_id, tx_guard = self._begin_workspace_tx_protection("install")
                return self._execute_planned_deployment(
                    host_cfg,
                    ordered_items,
                    frozenset(explicit_ids),
                    snap_id,
                    force_materialize=force,
                    eff_offline=eff_offline,
                    cancel_token=cancel_token,
                )
            except BaseException:
                self._rollback_write_failure_quietly(snap_id, tx_guard, mirror_journal)
                raise
            finally:
                self._cleanup_tx_guard(tx_guard, mirror_journal)

    def update(
        self,
        modules: Sequence[ModuleId] = (),
        *,
        provider: Optional[str] = None,
        ignore_sha256: bool = False,
        offline: bool = False,
        cancel_token: Optional[CancellationToken] = None,
    ) -> DeploymentReport:
        mod_tuple = require_typed_tuple(modules, ModuleId, "modules")
        for upd_mod in mod_tuple:
            ins_assert_not_reserved_module_id(upd_mod, label="OfflinePackageEngine.update module_id")
        if provider is not None:
            require_pure_str(provider, "provider")
        require_pure_bool(ignore_sha256, "ignore_sha256")
        require_pure_bool(offline, "offline")
        eff_offline = offline or is_public_env_truthy("YSCB_OFFLINE")
        _check_cancel(cancel_token)

        with self._engine_tx_lock(cancel_token):
            host_cfg = self._config_store.load_host_config()
            cur_installed = {m: r.version for m, r in host_cfg.installed_modules.items()}

            if mod_tuple:
                for target_m in mod_tuple:
                    if target_m not in cur_installed:
                        raise YscbError(
                            ErrorCode.DEPENDENCY_CONFLICT,
                            f"Cannot update module '{target_m}': module is not currently installed.",
                        )
                targets = sorted(set(mod_tuple), key=_core_first_key)
            else:
                targets = sorted(
                    (m for m, v in cur_installed.items() if not v.is_build),
                    key=_core_first_key,
                )

            if not targets:
                cur_mfs = [
                    mf
                    for m, v in cur_installed.items()
                    if (mf := self._read_installed_manifest(m, v)) is not None
                ]
                return DeploymentReport(
                    installed={},
                    removed=(),
                    transitions=(),
                    env_specs=ImmutableVenvPool.resolve_group_specs(cur_mfs),
                    snapshot_id=None,
                )

            mirror_journal = _InsMirrorTxJournal(self._yscb_root, self._next_tx_seq())
            snap_id = ""
            tx_guard: Optional[_InsTxWorkspaceGuard] = None
            try:
                prov_override = provider.strip() if (provider is not None and provider.strip()) else None
                provider_client = ProviderClient(
                    yscb_root=self._yscb_root,
                    host_dir=self._host_dir,
                    default_provider=prov_override or host_cfg.default_provider,
                    offline=eff_offline,
                )

                def _resolve_upd_provider(target_mod: ModuleId) -> str:
                    _check_cancel(cancel_token)
                    return (
                        prov_override
                        or (
                            host_cfg.installed_modules[target_mod].provider
                            if target_mod in host_cfg.installed_modules
                            else ""
                        )
                        or host_cfg.default_provider
                    )

                reqs = [
                    PackageRequest(
                        module_id=m,
                        version_spec=None,
                        is_build=cur_installed[m].is_build,
                        provider_override=_resolve_upd_provider(m),
                    )
                    for m in targets
                ]

                staged_items = self._solve_and_stage_constrained_plan(
                    reqs,
                    cur_installed,
                    provider_client,
                    _resolve_upd_provider,
                    same_major_only=True,
                    only_changed=True,
                    force_fetch=False,
                    ignore_sha256=ignore_sha256,
                    mirror_journal=mirror_journal,
                )

                if not staged_items:
                    cur_mfs = [
                        mf
                        for m, v in cur_installed.items()
                        if (mf := self._read_installed_manifest(m, v)) is not None
                    ]
                    return DeploymentReport(
                        installed={},
                        removed=(),
                        transitions=(),
                        env_specs=ImmutableVenvPool.resolve_group_specs(cur_mfs),
                        snapshot_id=None,
                    )

                ordered_items = sorted(
                    staged_items,
                    key=lambda it: (0 if it.module_id == _CORE_MODULE_ID else 1, staged_items.index(it)),
                )
                snap_id, tx_guard = self._begin_workspace_tx_protection("update")
                return self._execute_planned_deployment(
                    host_cfg,
                    ordered_items,
                    frozenset(targets),
                    snap_id,
                    force_materialize=False,
                    eff_offline=eff_offline,
                    cancel_token=cancel_token,
                )
            except BaseException:
                self._rollback_write_failure_quietly(snap_id, tx_guard, mirror_journal)
                raise
            finally:
                self._cleanup_tx_guard(tx_guard, mirror_journal)

    def restore(
        self,
        *,
        provider: Optional[str] = None,
        force: bool = False,
        ignore_sha256: bool = False,
        offline: bool = False,
        cancel_token: Optional[CancellationToken] = None,
    ) -> DeploymentReport:
        if provider is not None:
            require_pure_str(provider, "provider")
        require_pure_bool(force, "force")
        require_pure_bool(ignore_sha256, "ignore_sha256")
        require_pure_bool(offline, "offline")
        eff_offline = offline or is_public_env_truthy("YSCB_OFFLINE")
        _check_cancel(cancel_token)

        with self._engine_tx_lock(cancel_token):
            host_cfg = self._config_store.load_host_config()
            disk_versions = self._read_materialized_disk_versions()
            if not host_cfg.installed_modules:
                orphan_mods = [
                    m for m in self._list_materialized_module_ids() if m != _CORE_MODULE_ID
                ]
                if not orphan_mods:
                    return DeploymentReport(
                        installed={},
                        removed=(),
                        transitions=(),
                        env_specs={},
                        snapshot_id=None,
                    )
                mj_empty = _InsMirrorTxJournal(self._yscb_root, self._next_tx_seq())
                snap_empty, tx_guard_empty = self._begin_workspace_tx_protection("restore")
                try:
                    for orphan_m in orphan_mods:
                        self._deployer.remove_module(orphan_m, purge_level=PurgeLevel.NONE)
                    return DeploymentReport(
                        installed={},
                        removed=tuple(orphan_mods),
                        transitions=(),
                        env_specs={},
                        snapshot_id=snap_empty,
                    )
                except BaseException:
                    self._rollback_write_failure_quietly(snap_empty, tx_guard_empty, mj_empty)
                    raise
                finally:
                    self._cleanup_tx_guard(tx_guard_empty, mj_empty)

            mirror_journal = _InsMirrorTxJournal(self._yscb_root, self._next_tx_seq())
            snap_id = ""
            tx_guard: Optional[_InsTxWorkspaceGuard] = None
            try:
                prov_override = provider.strip() if (provider is not None and provider.strip()) else None
                provider_client = ProviderClient(
                    yscb_root=self._yscb_root,
                    host_dir=self._host_dir,
                    default_provider=prov_override or host_cfg.default_provider,
                    offline=eff_offline,
                )

                def _resolve_res_provider(target_mod: ModuleId) -> str:
                    _check_cancel(cancel_token)
                    return (
                        prov_override
                        or (
                            host_cfg.installed_modules[target_mod].provider
                            if target_mod in host_cfg.installed_modules
                            else ""
                        )
                        or host_cfg.default_provider
                    )

                staged_items: list[_InsPlannedPackage] = []
                restored_versions: dict[ModuleId, SemVer4] = {}
                ordered_ids = sorted(host_cfg.installed_modules.keys(), key=_core_first_key)

                for mod_id in ordered_ids:
                    eff_prov = _resolve_res_provider(mod_id)
                    inst_rec = host_cfg.installed_modules[mod_id]
                    target_ver = inst_rec.version

                    has_local_mirror = self._mirror.has_package(mod_id, target_ver)
                    rel_rec = self._lookup_release_record(mod_id, target_ver, provider_client, eff_prov)

                    is_pruned_missing = (
                        not target_ver.is_build
                        and not has_local_mirror
                        and rel_rec is not None
                        and rel_rec.status == "pruned"
                    )
                    if is_pruned_missing:
                        fb = _select_same_triplet_active_fallback(
                            target_ver,
                            provider_client,
                            self._mirror,
                            mod_id,
                            eff_prov,
                        )
                        if fb is None:
                            raise YscbError(
                                ErrorCode.DEPENDENCY_CONFLICT,
                                f"Version '{mod_id}@{target_ver}' has been pruned upstream and no active same-triplet revision exists.",
                            )
                        target_ver, rel_rec = fb

                    try:
                        staged = self._stage_to_mirror(
                            mod_id,
                            target_ver,
                            rel_rec,
                            provider_client,
                            eff_prov,
                            force_fetch=force,
                            ignore_sha256=ignore_sha256,
                            mirror_journal=mirror_journal,
                        )
                    except YscbError as fetch_err:
                        can_try_pruned_fallback = (
                            not has_local_mirror
                            and not target_ver.is_build
                            and target_ver == inst_rec.version
                            and fetch_err.detail.code not in INS_NON_FALLBACK_ERROR_CODES
                        )
                        if not can_try_pruned_fallback:
                            raise
                        fb_retry = _select_same_triplet_active_fallback(
                            inst_rec.version,
                            provider_client,
                            self._mirror,
                            mod_id,
                            eff_prov,
                        )
                        if fb_retry is None or fb_retry[0] == target_ver:
                            raise
                        target_ver, rel_rec = fb_retry
                        staged = self._stage_to_mirror(
                            mod_id,
                            target_ver,
                            rel_rec,
                            provider_client,
                            eff_prov,
                            force_fetch=force,
                            ignore_sha256=ignore_sha256,
                            mirror_journal=mirror_journal,
                        )

                    staged_items.append(staged)
                    restored_versions[mod_id] = target_ver

                staged_items = self._reconcile_restore_closure(
                    staged_items,
                    restored_versions,
                    provider_client,
                    _resolve_res_provider,
                    force_fetch=force,
                    ignore_sha256=ignore_sha256,
                    mirror_journal=mirror_journal,
                )

                ordered_items = sorted(
                    staged_items,
                    key=lambda it: (0 if it.module_id == _CORE_MODULE_ID else 1, staged_items.index(it)),
                )
                snap_id, tx_guard = self._begin_workspace_tx_protection("restore")
                return self._execute_planned_deployment(
                    host_cfg,
                    ordered_items,
                    frozenset(ordered_ids),
                    snap_id,
                    force_materialize=force,
                    eff_offline=eff_offline,
                    cancel_token=cancel_token,
                    baseline_versions=disk_versions,
                    prune_unlisted_modules=True,
                )
            except BaseException:
                self._rollback_write_failure_quietly(snap_id, tx_guard, mirror_journal)
                raise
            finally:
                self._cleanup_tx_guard(tx_guard, mirror_journal)

    def validate_remove_targets(
        self,
        modules: Sequence[ModuleId],
        *,
        force: bool = False,
    ) -> tuple[ModuleId, ...]:
        mod_tuple = require_typed_tuple(modules, ModuleId, "modules")
        for rm_mod in mod_tuple:
            ins_assert_not_reserved_module_id(rm_mod, label="OfflinePackageEngine.remove module_id")
        require_pure_bool(force, "force")
        if not mod_tuple:
            return ()

        deduped: list[ModuleId] = []
        for mod_id in mod_tuple:
            if mod_id == _CORE_MODULE_ID:
                raise YscbError(
                    ErrorCode.DEPENDENCY_CONFLICT,
                    "Core microkernel module 'core' cannot be removed.",
                )
            if mod_id not in deduped:
                deduped.append(mod_id)

        host_cfg = self._config_store.load_host_config()
        removing_set = set(deduped)
        if not force:
            for mod_id in deduped:
                if mod_id not in host_cfg.installed_modules:
                    raise YscbError(
                        ErrorCode.DEPENDENCY_CONFLICT,
                        f"Cannot remove '{mod_id}': module is not installed.",
                    )
            for rem_id, rem_rec in host_cfg.installed_modules.items():
                if rem_id in removing_set:
                    continue
                rem_mf = self._read_installed_manifest(rem_id, rem_rec.version)
                if rem_mf is None:
                    continue
                for dep_id in rem_mf.dependencies:
                    if dep_id in removing_set:
                        raise YscbError(
                            ErrorCode.DEPENDENCY_CONFLICT,
                            f"Cannot remove '{dep_id}': still required by installed module '{rem_id}@{rem_rec.version}'.",
                        )
        return tuple(deduped)

    def remove(
        self,
        modules: Sequence[ModuleId],
        *,
        purge_level: PurgeLevel = PurgeLevel.NONE,
        force: bool = False,
    ) -> DeploymentReport:
        mod_tuple = require_typed_tuple(modules, ModuleId, "modules")
        for rm_mod in mod_tuple:
            ins_assert_not_reserved_module_id(rm_mod, label="OfflinePackageEngine.remove module_id")
        if not isinstance(purge_level, PurgeLevel):
            raise ValueError(f"purge_level must be PurgeLevel, got {purge_level!r}")
        require_pure_bool(force, "force")

        with self._engine_tx_lock():
            if not mod_tuple:
                host_cfg_empty = self._config_store.load_host_config()
                cur_mfs = [
                    mf
                    for m, r in host_cfg_empty.installed_modules.items()
                    if (mf := self._read_installed_manifest(m, r.version)) is not None
                ]
                return DeploymentReport(
                    installed={},
                    removed=(),
                    transitions=(),
                    env_specs=ImmutableVenvPool.resolve_group_specs(cur_mfs),
                    snapshot_id=None,
                )

            deduped = list(self.validate_remove_targets(mod_tuple, force=force))
            host_cfg = self._config_store.load_host_config()
            removing_set = set(deduped)
            mirror_journal = _InsMirrorTxJournal(self._yscb_root, self._next_tx_seq())
            snap_id, tx_guard = self._begin_workspace_tx_protection("remove")
            try:

                for mod_id in deduped:
                    self._deployer.remove_module(mod_id, purge_level=purge_level)

                remaining_records = {
                    m: rec for m, rec in host_cfg.installed_modules.items() if m not in removing_set
                }
                self._config_store.save_host_config(
                    HostConfig(
                        yscb_root=host_cfg.yscb_root,
                        default_provider=host_cfg.default_provider,
                        installed_modules=remaining_records,
                    )
                )
                rem_manifests = [
                    mf
                    for m, rec in remaining_records.items()
                    if (mf := self._read_installed_manifest(m, rec.version)) is not None
                ]
                env_specs = ImmutableVenvPool.resolve_group_specs(rem_manifests)
                return DeploymentReport(
                    installed={},
                    removed=tuple(deduped),
                    transitions=(),
                    env_specs=env_specs,
                    snapshot_id=snap_id,
                )
            except BaseException:
                self._rollback_write_failure_quietly(snap_id, tx_guard, mirror_journal)
                raise
            finally:
                self._cleanup_tx_guard(tx_guard, mirror_journal)

    def _materialize_desired_from_mirror_impl(
        self,
        *,
        offline: bool,
        deploy_configurable: bool,
        mirror_journal: Optional[_InsMirrorTxJournal] = None,
    ) -> DeploymentReport:
        eff_offline = offline or is_public_env_truthy("YSCB_OFFLINE")
        host_cfg = self._config_store.load_host_config()
        provider_client = ProviderClient(
            yscb_root=self._yscb_root,
            host_dir=self._host_dir,
            default_provider=host_cfg.default_provider,
            offline=eff_offline,
        )

        desired_ids = set(host_cfg.installed_modules.keys())
        ordered_ids = sorted(desired_ids, key=_core_first_key)
        prepared: list[_InsPlannedPackage] = []
        for mod_id in ordered_ids:
            inst_rec = host_cfg.installed_modules[mod_id]
            ver = inst_rec.version
            eff_prov = inst_rec.provider or host_cfg.default_provider
            idx = self._mirror.load_index_cache(mod_id)
            rel_rec = idx.releases.get(str(ver)) if idx is not None else None
            if rel_rec is None and not ver.is_build and not eff_offline:
                rel_rec = self._lookup_release_record(mod_id, ver, provider_client, eff_prov)
            has_local_pkg = self._mirror.has_package(mod_id, ver)
            if not has_local_pkg:
                staged = self._stage_to_mirror(
                    mod_id,
                    ver,
                    rel_rec,
                    provider_client,
                    eff_prov,
                    force_fetch=False,
                    ignore_sha256=False,
                    mirror_journal=mirror_journal,
                )
                prepared.append(staged)
                continue
            mirror_zip = self._mirror.get_package_path(mod_id, ver)
            self._mirror.verify_zip_integrity(
                mirror_zip,
                expected_sha256=(rel_rec.sha256 if (rel_rec is not None and rel_rec.sha256) else None),
                ignore_sha256=(rel_rec is None or not rel_rec.sha256 or ver.is_build),
            )
            mf = ins_peek_zip_manifest(
                mirror_zip,
                expected_module_id=mod_id,
                expected_version=ver,
            )
            if ins_has_dependencies_override(rel_rec) and rel_rec is not None:
                mf = ins_override_manifest_dependencies(mf, rel_rec.dependencies)
            prepared.append(
                _InsPlannedPackage(
                    module_id=mod_id,
                    version=ver,
                    release_record=rel_rec,
                    provider=eff_prov,
                    zip_path=mirror_zip,
                    manifest=mf,
                )
            )

        env_specs = self._ensure_tier1_envs(
            [item.manifest for item in prepared],
            offline=eff_offline,
            cancel_token=None,
        )

        installed_map: dict[ModuleId, SemVer4] = {}
        for item in prepared:
            ins_materialize_module(
                self._deployer,
                item.module_id,
                item.zip_path,
                release_override=item.release_record,
                deploy_configurable=deploy_configurable,
            )
            installed_map[item.module_id] = item.version

        removed_extra: list[ModuleId] = []
        for disk_mod in self._list_materialized_module_ids():
            if disk_mod not in desired_ids and disk_mod != _CORE_MODULE_ID:
                self._deployer.remove_module(disk_mod, purge_level=PurgeLevel.NONE)
                removed_extra.append(disk_mod)

        return DeploymentReport(
            installed=installed_map,
            removed=tuple(removed_extra),
            transitions=(),
            env_specs=env_specs,
            snapshot_id=None,
        )

    def reload_from_mirror(self, *, offline: bool = True) -> DeploymentReport:
        require_pure_bool(offline, "offline")
        with self._engine_tx_lock():
            tx_seq = self._next_tx_seq()
            rl_guard = _capture_tx_workspace_guard(self._host_dir, self._yscb_root, tx_seq)
            mirror_journal = _InsMirrorTxJournal(self._yscb_root, tx_seq)
            try:
                return self._materialize_desired_from_mirror_impl(
                    offline=offline,
                    deploy_configurable=True,
                    mirror_journal=mirror_journal,
                )
            except BaseException:
                self._rollback_write_failure_quietly("", rl_guard, mirror_journal)
                raise
            finally:
                self._cleanup_tx_guard(rl_guard, mirror_journal)

    def rollback(self, snapshot_id: Optional[str] = None) -> DeploymentReport:
        if snapshot_id is not None:
            require_pure_str(snapshot_id, "snapshot_id", non_empty=True)

        with self._engine_tx_lock():
            prev_installed: dict[ModuleId, SemVer4] = {}
            try:
                prev_cfg = self._config_store.load_host_config()
                prev_installed = {m: r.version for m, r in prev_cfg.installed_modules.items()}
            except (OSError, ValueError, YscbError):
                prev_installed = {}

            tx_seq = self._next_tx_seq()
            rb_guard = _capture_tx_workspace_guard(self._host_dir, self._yscb_root, tx_seq)
            rb_mirror_journal = _InsMirrorTxJournal(self._yscb_root, tx_seq)
            try:
                restored_meta = self._snapshot_vault.restore_snapshot(snapshot_id)
                self._config_store.reload()
                restored_cfg = self._config_store.load_host_config()

                desired_ids = set(restored_cfg.installed_modules.keys())
                reload_report = self._materialize_desired_from_mirror_impl(
                    offline=True,
                    deploy_configurable=False,
                    mirror_journal=rb_mirror_journal,
                )
                removed_ids = sorted(
                    (set(prev_installed.keys()) | set(reload_report.removed))
                    - desired_ids
                    - {_CORE_MODULE_ID},
                    key=_core_first_key,
                )
                transitions: list[UpgradeTransition] = []
                for mod_id in sorted(desired_ids, key=_core_first_key):
                    new_ver = restored_cfg.installed_modules[mod_id].version
                    old_ver = prev_installed.get(mod_id)
                    if old_ver != new_ver:
                        transitions.append(
                            UpgradeTransition(
                                module_id=mod_id,
                                old_version=old_ver,
                                new_version=new_ver,
                                is_upgrade=(old_ver is not None and new_ver > old_ver),
                            )
                        )

                return DeploymentReport(
                    installed=reload_report.installed,
                    removed=tuple(removed_ids),
                    transitions=tuple(transitions),
                    env_specs=reload_report.env_specs,
                    snapshot_id=restored_meta.snapshot_id,
                )
            except BaseException:
                self._rollback_write_failure_quietly("", rb_guard, rb_mirror_journal)
                raise
            finally:
                self._cleanup_tx_guard(rb_guard, rb_mirror_journal)
