"""Atomic staging extractor, *.tmpl configuration deployer/stripper, 3-stage handle-lock swapper, and space cleaner."""

from __future__ import annotations

import errno
import os
from pathlib import Path
import shutil
import stat
import threading
from typing import Callable, ClassVar, Final, Mapping, Optional
import weakref
import zipfile
import zlib

from core.filesystem.fs import (
    MAX_JSON_FILE_BYTES,
    assert_no_symlink_raw_path,
    atomic_write_json,
    has_symlink_raw_path,
    is_symlink_or_reparse,
    read_json_dict,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
    try_resolve_contained_subpath,
)
from core.filesystem.vfs import KernelVfs
from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary
from core.foundation.primitives import (
    IS_WINDOWS,
    HostPath,
    JsonObject,
    ModuleId,
    MutableJsonObject,
    SemanticUri,
    strict_parse_json_object,
)
from core.foundation.proc import is_process_alive
from core.metadata.config import ConfigStore, ModuleManifest
from core.packaging.installer.models import (
    INS_MAX_ZIP_ARCHIVE_BYTES,
    INS_MAX_ZIP_COMPRESSION_RATIO,
    INS_MAX_ZIP_MEMBERS,
    INS_MAX_ZIP_SINGLE_BYTES,
    INS_MAX_ZIP_TOTAL_BYTES,
    INS_ZIP_RATIO_CHECK_MIN_BYTES,
    IndexReleaseRecord,
    InsZipPathCollisionTracker,
    PurgeLevel,
    ins_assert_not_reserved_module_id,
    ins_has_dependencies_override,
    ins_open_verified_zip_stream,
    ins_override_manifest_dependencies,
    ins_parse_manifest_dict,
    ins_rewrite_manifest_dependencies_json,
    ins_robust_rmtree,
    ins_validate_zip_member_info,
    ins_verify_zip_archive,
)

_CLEAN_SCHEME_PAIRS: Final[tuple[tuple[str, str], ...]] = (
    ("cache", ".cache"),
    ("storage.local", ".storage.local"),
)
_PURGE_SCHEME_PAIRS: Final[tuple[tuple[str, str], ...]] = (
    ("config", "config"),
    ("config.local", ".config.local"),
    ("storage", "storage"),
    ("storage.local", ".storage.local"),
    ("cache", ".cache"),
)
_NOFOLLOW_EXCL_WRITE_FLAGS: Final[int] = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | (os.O_BINARY if IS_WINDOWS else 0)
    | (0 if IS_WINDOWS else os.O_NOFOLLOW)
)

_MaterializeHook = Callable[
    ["AtomicPackageDeployer", ModuleId, HostPath, Optional[IndexReleaseRecord], bool],
    ModuleManifest,
]


class _InsDeployerRegistry:
    """Weak registry binding AtomicPackageDeployer instances to internal materialization hooks."""

    guard: ClassVar[threading.Lock] = threading.Lock()
    hooks: ClassVar[weakref.WeakKeyDictionary[AtomicPackageDeployer, _MaterializeHook]] = (
        weakref.WeakKeyDictionary()
    )

    @classmethod
    def register(cls, deployer: AtomicPackageDeployer, hook: _MaterializeHook) -> None:
        with cls.guard:
            cls.hooks[deployer] = hook

    @classmethod
    def lookup(cls, deployer: AtomicPackageDeployer) -> _MaterializeHook:
        with cls.guard:
            return cls.hooks[deployer]


def ins_materialize_module(
    deployer: AtomicPackageDeployer,
    module_id: ModuleId,
    zip_path: HostPath,
    *,
    release_override: Optional[IndexReleaseRecord] = None,
    deploy_configurable: bool = True,
) -> ModuleManifest:
    """Internal materializer allowing rollback/reconcile paths to skip deploy_configurable."""
    hook = _InsDeployerRegistry.lookup(deployer)
    return hook(deployer, module_id, zip_path, release_override, deploy_configurable)


def _extract_schema_defaults(
    props: Mapping[str, object],
    defs_map: Mapping[str, object],
    seen_refs: frozenset[str] = frozenset(),
) -> MutableJsonObject:
    out: MutableJsonObject = {}
    for key, raw_spec in props.items():
        if type(key) is not str or not isinstance(raw_spec, Mapping):
            continue
        if "default" in raw_spec:
            val = raw_spec["default"]
            if val is None or isinstance(val, (bool, int, float, str, list, dict)):
                out[key] = val
            continue
        ref_str = raw_spec.get("$ref")
        if type(ref_str) is str and ref_str.startswith("#/$defs/"):
            def_name = ref_str[len("#/$defs/") :]
            if def_name in seen_refs:
                continue
            target_def = defs_map.get(def_name)
            if isinstance(target_def, Mapping) and isinstance(target_def.get("properties"), Mapping):
                nested = _extract_schema_defaults(
                    target_def["properties"],
                    defs_map,
                    seen_refs | {def_name},
                )
                req_list = target_def.get("required", ())
                has_unfilled_req = isinstance(req_list, list) and any(
                    isinstance(r, str) and r not in nested for r in req_list
                )
                if nested and not has_unfilled_req:
                    out[key] = nested
    return out


def _read_config_schema_defaults(staging_hp: HostPath) -> MutableJsonObject:
    schema_hp = try_resolve_contained_subpath(staging_hp, "config.schema.json")
    if schema_hp is None or not os.path.lexists(str(schema_hp)):
        return {}
    if is_symlink_or_reparse(str(schema_hp)) or has_symlink_raw_path(str(schema_hp)):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Refusing symlink config.schema.json inside staging '{staging_hp}'.",
        )
    doc = read_json_dict(schema_hp)
    if doc is None:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Malformed or oversized config.schema.json inside staging '{staging_hp}'.",
        )
    raw_props = doc.get("properties")
    if not isinstance(raw_props, Mapping):
        return {}
    raw_defs = doc.get("$defs")
    defs_map: Mapping[str, object] = raw_defs if isinstance(raw_defs, Mapping) else {}
    return _extract_schema_defaults(raw_props, defs_map)


def _extract_verified_zip_into_staging(zip_path: HostPath, staging_hp: HostPath) -> None:
    raw_zip = str(zip_path)
    try:
        with ins_open_verified_zip_stream(zip_path) as raw_stream, zipfile.ZipFile(raw_stream, "r") as zf:
            infos = zf.infolist()
            if len(infos) > INS_MAX_ZIP_MEMBERS:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Zip archive '{zip_path}' exceeds {INS_MAX_ZIP_MEMBERS} entries limit.",
                )
            collision_tracker = InsZipPathCollisionTracker()
            total_extracted = 0
            for info in infos:
                parts = ins_validate_zip_member_info(info, archive_label=raw_zip)
                if not parts:
                    continue
                is_dir_entry = info.is_dir() or info.filename.endswith("/")
                collision_tracker.register(
                    parts,
                    is_dir=is_dir_entry,
                    raw_name=info.filename,
                    archive_label=raw_zip,
                )
                dest_member = resolve_contained_subpath(staging_hp, *parts)
                if is_dir_entry:
                    os.makedirs(str(dest_member), exist_ok=True)
                    assert_no_symlink_raw_path(str(dest_member))
                    continue
                if info.file_size > INS_MAX_ZIP_SINGLE_BYTES:
                    raise YscbError(
                        ErrorCode.PACKAGE_INTEGRITY_ERROR,
                        f"Zip entry '{info.filename}' exceeds {INS_MAX_ZIP_SINGLE_BYTES} bytes limit.",
                    )
                os.makedirs(str(dest_member.path.parent), exist_ok=True)
                assert_no_symlink_raw_path(str(dest_member))
                if os.path.lexists(str(dest_member)):
                    raise YscbError(
                        ErrorCode.PACKAGE_INTEGRITY_ERROR,
                        f"Duplicate zip entry '{info.filename}' in '{zip_path}'.",
                    )
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                file_mode = 0o755 if (not IS_WINDOWS and bool(unix_mode & 0o111)) else 0o644
                fd = os.open(str(dest_member), _NOFOLLOW_EXCL_WRITE_FLAGS, file_mode)
                try:
                    if not IS_WINDOWS and file_mode == 0o755:
                        try:
                            os.fchmod(fd, 0o755)
                        except OSError:
                            pass
                    out_f = os.fdopen(fd, "wb")
                except BaseException:
                    os.close(fd)
                    raise
                file_extracted = 0
                with out_f, zf.open(info, "r") as src_f:
                    while True:
                        chunk = src_f.read(65536)
                        if not chunk:
                            break
                        file_extracted += len(chunk)
                        total_extracted += len(chunk)
                        if file_extracted > INS_MAX_ZIP_SINGLE_BYTES or total_extracted > INS_MAX_ZIP_TOTAL_BYTES:
                            raise YscbError(
                                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                                f"Zip extraction exceeded uncompressed size limit in '{zip_path}'.",
                            )
                        if file_extracted >= INS_ZIP_RATIO_CHECK_MIN_BYTES and (
                            info.compress_size <= 0
                            or file_extracted > info.compress_size * INS_MAX_ZIP_COMPRESSION_RATIO
                        ):
                            raise YscbError(
                                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                                f"Zip entry '{info.filename}' in '{zip_path}' exceeded compression ratio limit.",
                            )
                        out_f.write(chunk)
    except YscbError:
        raise
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        zlib.error,
        OSError,
        EOFError,
        ValueError,
        RuntimeError,
        NotImplementedError,
    ) as exc:
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Failed extracting '{zip_path}' into staging: {safe_exception_summary(exc)}",
        ) from exc


def _strip_staging_templates_and_verify(staging_hp: HostPath) -> None:
    cfg_dir_raw = os.path.join(str(staging_hp), "configurable")
    if os.path.lexists(cfg_dir_raw):
        ins_robust_rmtree(cfg_dir_raw)

    yscbignore_raw = os.path.join(str(staging_hp), ".yscbignore")
    if os.path.lexists(yscbignore_raw):
        ins_robust_rmtree(yscbignore_raw)

    stack: list[str] = [str(staging_hp)]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                entries = list(it)
        except OSError as exc:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Failed verifying stripped staging tree '{cur}': {safe_exception_summary(exc)}",
            ) from exc
        for ent in entries:
            if ent.is_symlink() or is_symlink_or_reparse(ent.path):
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Symbolic link '{ent.path}' forbidden in staged module directory.",
                )
            if ent.name == ".yscbignore" or ent.name.endswith(".tmpl"):
                ins_robust_rmtree(ent.path)
                continue
            if ent.is_dir(follow_symlinks=False):
                stack.append(ent.path)

    if os.path.lexists(cfg_dir_raw) or os.path.lexists(yscbignore_raw):
        raise YscbError(
            ErrorCode.PACKAGE_INTEGRITY_ERROR,
            f"Staging strip verification failed: residual configurable/ or .yscbignore in '{staging_hp}'.",
        )


def _force_file_writable(raw_path: str) -> None:
    if is_symlink_or_reparse(raw_path):
        return
    try:
        st = os.lstat(raw_path)
        if stat.S_ISDIR(st.st_mode):
            extra = (stat.S_IWRITE | stat.S_IREAD) if IS_WINDOWS else (stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
            os.chmod(raw_path, stat.S_IMODE(st.st_mode) | extra)
        elif not stat.S_ISLNK(st.st_mode):
            os.chmod(raw_path, stat.S_IMODE(st.st_mode) | stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _shares_physical_file_with_any(cand_path: str, peer_paths: tuple[str, ...]) -> bool:
    if is_symlink_or_reparse(cand_path):
        return False
    for peer in peer_paths:
        if not os.path.lexists(peer) or is_symlink_or_reparse(peer):
            continue
        try:
            if os.path.samefile(cand_path, peer):
                return True
        except OSError:
            continue
    return False


def _prepare_inplace_file_destination(dst_f: str) -> None:
    parent_dir = os.path.dirname(dst_f)
    target_name = os.path.basename(dst_f)
    target_fold = target_name.casefold()
    _force_file_writable(parent_dir)
    try:
        with os.scandir(parent_dir) as it:
            for ent in it:
                if ent.name != target_name and ent.name.casefold() == target_fold:
                    if os.path.lexists(dst_f) and _shares_physical_file_with_any(ent.path, (dst_f,)):
                        _force_file_writable(ent.path)
                        try:
                            os.unlink(ent.path)
                        except OSError:
                            pass
    except OSError:
        pass
    if os.path.lexists(dst_f):
        if is_symlink_or_reparse(dst_f) or os.path.isdir(dst_f):
            ins_robust_rmtree(dst_f)
        else:
            _force_file_writable(dst_f)


def _write_nofollow_file_bytes(dst_raw: str, payload: bytes) -> None:
    fd = os.open(dst_raw, _NOFOLLOW_EXCL_WRITE_FLAGS, 0o644)
    try:
        out_f = os.fdopen(fd, "wb")
    except BaseException:
        os.close(fd)
        raise
    with out_f:
        out_f.write(payload)
        out_f.flush()


def _ensure_subdir_clearing_blocking_files(base_raw: str, rel_dir: str) -> str:
    if not rel_dir or rel_dir == ".":
        return base_raw
    cur = base_raw
    for part in Path(rel_dir).parts:
        parent_dir = cur
        next_cur = os.path.join(parent_dir, part)
        if os.path.lexists(next_cur) and (is_symlink_or_reparse(next_cur) or not os.path.isdir(next_cur)):
            _force_file_writable(next_cur)
            ins_robust_rmtree(next_cur)
        elif os.path.isdir(parent_dir) and os.path.isdir(next_cur) and not is_symlink_or_reparse(next_cur):
            part_fold = part.casefold()
            matched_actual: Optional[str] = None
            try:
                with os.scandir(parent_dir) as it:
                    for ent in it:
                        if ent.name != part and ent.name.casefold() == part_fold:
                            if _shares_physical_file_with_any(ent.path, (next_cur,)):
                                matched_actual = ent.path
                                break
            except OSError:
                matched_actual = None
            if matched_actual is not None and not is_symlink_or_reparse(matched_actual):
                _force_file_writable(parent_dir)
                _force_file_writable(matched_actual)
                case_tmp = os.path.join(
                    parent_dir,
                    f".yscb_case_{os.getpid()}_{os.path.basename(matched_actual)}",
                )
                if os.path.lexists(case_tmp):
                    ins_robust_rmtree(case_tmp)
                os.replace(matched_actual, case_tmp)
                try:
                    os.replace(case_tmp, next_cur)
                except BaseException:
                    if os.path.lexists(case_tmp) and not os.path.lexists(matched_actual):
                        try:
                            os.replace(case_tmp, matched_actual)
                        except OSError:
                            pass
                    raise
        os.makedirs(next_cur, exist_ok=True)
        cur = next_cur
    return cur


def _is_handle_locked_directory_rename(
    err: OSError,
    parent_raw: str,
    target_raw: str,
    seq: int,
) -> bool:
    if not isinstance(err, PermissionError) and err.errno not in (
        errno.EACCES,
        errno.EBUSY,
        errno.EPERM,
    ):
        return False
    if not os.path.isdir(parent_raw) or not os.path.isdir(target_raw):
        return False
    req_mode = os.W_OK if IS_WINDOWS else (os.W_OK | os.X_OK)
    if not os.access(parent_raw, req_mode) or not os.access(target_raw, req_mode):
        return False

    probe_src = os.path.join(target_raw, f".yscb_probe_src_{os.getpid()}_{seq}")
    probe_dst = os.path.join(target_raw, f".yscb_probe_dst_{os.getpid()}_{seq}")
    try:
        with open(probe_src, "wb") as f:
            f.write(b"1")
            f.flush()
        os.replace(probe_src, probe_dst)
        os.unlink(probe_dst)
        return True
    except OSError:
        return False
    finally:
        for cand in (probe_src, probe_dst):
            if os.path.lexists(cand):
                try:
                    os.unlink(cand)
                except OSError:
                    pass


def _backup_existing_files(target_raw: str, backup_raw: str) -> tuple[set[str], set[str]]:
    existing_rels: set[str] = set()
    existing_dirs: set[str] = set()
    os.makedirs(backup_raw, exist_ok=True)
    for cur_root, dirs, files in os.walk(target_raw):
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith((".old_", ".staging_", ".yscb_probe_"))
            and not is_symlink_or_reparse(os.path.join(cur_root, d))
        ]
        rel_dir = "" if cur_root == target_raw else os.path.relpath(cur_root, target_raw)
        if rel_dir:
            existing_dirs.add(rel_dir.replace("\\", "/"))
        for fname in files:
            if fname.startswith((".yscb_probe_", ".yscb_tmp_", ".yscb_restore_")):
                continue
            src_file = os.path.join(cur_root, fname)
            if is_symlink_or_reparse(src_file):
                continue
            raw_bytes = read_nofollow_regular_bytes(src_file, max_bytes=INS_MAX_ZIP_ARCHIVE_BYTES)
            if raw_bytes is None:
                continue
            rel_item = os.path.join(rel_dir, fname) if rel_dir else fname
            existing_rels.add(rel_item.replace("\\", "/"))
            dst_bak = os.path.join(backup_raw, rel_item)
            os.makedirs(os.path.dirname(dst_bak), exist_ok=True)
            _write_nofollow_file_bytes(dst_bak, raw_bytes)
    return (existing_rels, existing_dirs)


def _restore_files_from_backup(
    target_raw: str,
    backup_raw: str,
    existing_rels: set[str],
    existing_dirs: set[str],
    seq: int,
) -> None:
    for saved_dir in sorted(existing_dirs):
        try:
            _ensure_subdir_clearing_blocking_files(target_raw, saved_dir.replace("/", os.sep))
        except OSError:
            pass
    existing_by_fold: dict[str, list[str]] = {}
    for rel_key in existing_rels:
        existing_by_fold.setdefault(rel_key.casefold(), []).append(
            os.path.join(target_raw, rel_key.replace("/", os.sep))
        )
    for norm_rel in existing_rels:
        os_rel = norm_rel.replace("/", os.sep)
        bak_f = os.path.join(backup_raw, os_rel)
        dst_f = os.path.join(target_raw, os_rel)
        bak_bytes = read_nofollow_regular_bytes(bak_f, max_bytes=INS_MAX_ZIP_ARCHIVE_BYTES)
        if bak_bytes is not None:
            rel_parent = os.path.dirname(os_rel)
            _ensure_subdir_clearing_blocking_files(target_raw, rel_parent)
            tmp_f = os.path.join(
                os.path.dirname(dst_f),
                f".yscb_restore_{os.getpid()}_{seq}_{os.path.basename(dst_f)}",
            )
            try:
                _prepare_inplace_file_destination(dst_f)
                _write_nofollow_file_bytes(tmp_f, bak_bytes)
                os.replace(tmp_f, dst_f)
            except OSError:
                if os.path.lexists(tmp_f):
                    try:
                        os.unlink(tmp_f)
                    except OSError:
                        pass
    for cur_root, _dirs, files in os.walk(target_raw):
        rel_dir = "" if cur_root == target_raw else os.path.relpath(cur_root, target_raw)
        for fname in files:
            rel_item = (os.path.join(rel_dir, fname) if rel_dir else fname).replace("\\", "/")
            if rel_item not in existing_rels:
                extra_f = os.path.join(cur_root, fname)
                if is_symlink_or_reparse(extra_f):
                    try:
                        ins_robust_rmtree(extra_f)
                    except OSError:
                        pass
                    continue
                peers = tuple(existing_by_fold.get(rel_item.casefold(), ()))
                if _shares_physical_file_with_any(extra_f, peers):
                    continue
                _force_file_writable(extra_f)
                try:
                    os.unlink(extra_f)
                except OSError:
                    pass
    existing_dir_paths = tuple(os.path.join(target_raw, d.replace("/", os.sep)) for d in existing_dirs)
    for cur_root, dirs, _files in os.walk(target_raw, topdown=False):
        for d_name in dirs:
            d_full = os.path.join(cur_root, d_name)
            rel_d = os.path.relpath(d_full, target_raw).replace("\\", "/")
            if rel_d not in existing_dirs:
                if is_symlink_or_reparse(d_full):
                    try:
                        ins_robust_rmtree(d_full)
                    except OSError:
                        pass
                    continue
                if _shares_physical_file_with_any(d_full, existing_dir_paths):
                    continue
                try:
                    if not os.listdir(d_full):
                        _force_file_writable(os.path.dirname(d_full))
                        _force_file_writable(d_full)
                        os.rmdir(d_full)
                except OSError:
                    pass


def _inplace_atomic_sync_directory(
    staging_raw: str,
    target_raw: str,
    parent_raw: str,
    mod_name: str,
    seq: int,
) -> None:
    backup_raw = os.path.join(parent_raw, f".old_backup_{mod_name}_{os.getpid()}_{seq}")
    existing_rels: set[str] = set()
    existing_dirs: set[str] = set()
    try:
        existing_rels, existing_dirs = _backup_existing_files(target_raw, backup_raw)
        staged_rels: set[str] = set()
        for cur_root, _dirs, files in os.walk(staging_raw):
            rel_dir = "" if cur_root == staging_raw else os.path.relpath(cur_root, staging_raw)
            _ensure_subdir_clearing_blocking_files(target_raw, rel_dir)
            for fname in files:
                rel_item = os.path.join(rel_dir, fname) if rel_dir else fname
                staged_rels.add(rel_item.replace("\\", "/"))
                src_f = os.path.join(cur_root, fname)
                src_bytes = read_nofollow_regular_bytes(src_f, max_bytes=INS_MAX_ZIP_ARCHIVE_BYTES)
                if src_bytes is None:
                    raise YscbError(
                        ErrorCode.PACKAGE_INTEGRITY_ERROR,
                        f"Unreadable staged module file '{src_f}'.",
                    )
                dst_f = os.path.join(target_raw, rel_item)
                tmp_dst = os.path.join(os.path.dirname(dst_f), f".yscb_tmp_{os.getpid()}_{seq}_{fname}")
                try:
                    _prepare_inplace_file_destination(dst_f)
                    _write_nofollow_file_bytes(tmp_dst, src_bytes)
                    os.replace(tmp_dst, dst_f)
                finally:
                    if os.path.lexists(tmp_dst):
                        try:
                            os.unlink(tmp_dst)
                        except OSError:
                            pass

        staged_by_fold: dict[str, list[str]] = {}
        for s_rel in staged_rels:
            staged_by_fold.setdefault(s_rel.casefold(), []).append(
                os.path.join(target_raw, s_rel.replace("/", os.sep))
            )
        for cur_root, dirs, files in os.walk(target_raw):
            kept_dirs: list[str] = []
            for d_name in dirs:
                d_path = os.path.join(cur_root, d_name)
                if is_symlink_or_reparse(d_path):
                    ins_robust_rmtree(d_path)
                else:
                    kept_dirs.append(d_name)
            dirs[:] = kept_dirs
            rel_dir = "" if cur_root == target_raw else os.path.relpath(cur_root, target_raw)
            for fname in files:
                obs_f = os.path.join(cur_root, fname)
                if is_symlink_or_reparse(obs_f):
                    ins_robust_rmtree(obs_f)
                    continue
                norm_rel = (os.path.join(rel_dir, fname) if rel_dir else fname).replace("\\", "/")
                if norm_rel in staged_rels:
                    continue
                peers = tuple(staged_by_fold.get(norm_rel.casefold(), ()))
                if _shares_physical_file_with_any(obs_f, peers):
                    continue
                _force_file_writable(obs_f)
                os.unlink(obs_f)

        staged_dir_paths: list[str] = []
        for s_root, s_dirs, _s_files in os.walk(staging_raw):
            for sd in s_dirs:
                s_rel_d = os.path.relpath(os.path.join(s_root, sd), staging_raw)
                staged_dir_paths.append(os.path.join(target_raw, s_rel_d))
        staged_dir_tuple = tuple(staged_dir_paths)
        for cur_root, dirs, _files in os.walk(target_raw, topdown=False):
            for d_name in dirs:
                d_full = os.path.join(cur_root, d_name)
                rel_d = os.path.relpath(d_full, target_raw)
                if is_symlink_or_reparse(d_full):
                    ins_robust_rmtree(d_full)
                    continue
                if not os.path.exists(os.path.join(staging_raw, rel_d)):
                    if _shares_physical_file_with_any(d_full, staged_dir_tuple):
                        continue
                    try:
                        if not os.listdir(d_full):
                            _force_file_writable(os.path.dirname(d_full))
                            _force_file_writable(d_full)
                            os.rmdir(d_full)
                    except OSError:
                        pass
    except BaseException:
        _restore_files_from_backup(target_raw, backup_raw, existing_rels, existing_dirs, seq)
        raise
    finally:
        if os.path.lexists(backup_raw):
            ins_robust_rmtree(backup_raw)


def _replace_directory_with_exdev_fallback(
    src_raw: str,
    dst_raw: str,
    parent_raw: str,
    mod_name: str,
    seq: int,
) -> None:
    try:
        os.replace(src_raw, dst_raw)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        exdev_stage = os.path.join(parent_raw, f".staging_exdev_{mod_name}_{os.getpid()}_{seq}")
        if os.path.lexists(exdev_stage):
            ins_robust_rmtree(exdev_stage)
        try:
            shutil.copytree(src_raw, exdev_stage, symlinks=False)
            os.replace(exdev_stage, dst_raw)
            ins_robust_rmtree(src_raw)
        finally:
            if os.path.lexists(exdev_stage):
                ins_robust_rmtree(exdev_stage)


def _atomic_swap_staged_module_dir(
    staging_hp: HostPath,
    target_hp: HostPath,
    modules_root: HostPath,
    mod_name: str,
    seq: int,
) -> None:
    staging_raw = str(staging_hp)
    target_raw = str(target_hp)
    parent_raw = str(modules_root)
    old_hp = resolve_contained_subpath(modules_root, f".old_{mod_name}_{os.getpid()}_{seq}")
    old_raw = str(old_hp)

    moved_old = False
    swap_ok = False
    try:
        if os.path.lexists(old_raw):
            ins_robust_rmtree(old_raw)
        if os.path.lexists(target_raw):
            if is_symlink_or_reparse(target_raw):
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Refusing symlink target module directory: '{target_hp}'.",
                )
            try:
                _replace_directory_with_exdev_fallback(target_raw, old_raw, parent_raw, mod_name, seq)
                moved_old = True
            except OSError as rename_err:
                if _is_handle_locked_directory_rename(rename_err, parent_raw, target_raw, seq):
                    _inplace_atomic_sync_directory(staging_raw, target_raw, parent_raw, mod_name, seq)
                    swap_ok = True
                    return
                raise
        _replace_directory_with_exdev_fallback(staging_raw, target_raw, parent_raw, mod_name, seq)
        swap_ok = True
    except BaseException as exc:
        if moved_old and os.path.lexists(old_raw):
            try:
                if os.path.lexists(target_raw):
                    ins_robust_rmtree(target_raw)
                _replace_directory_with_exdev_fallback(old_raw, target_raw, parent_raw, mod_name, seq)
            except OSError:
                pass
        if isinstance(exc, OSError) and not isinstance(exc, YscbError):
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Failed swapping staged module '{mod_name}' into '{target_hp}': {safe_exception_summary(exc)}",
            ) from exc
        raise
    finally:
        if swap_ok and os.path.lexists(old_raw):
            try:
                ins_robust_rmtree(old_raw)
            except OSError:
                pass
        if swap_ok:
            try:
                with os.scandir(parent_raw) as it:
                    for ent in it:
                        if ent.name.startswith(f".old_{mod_name}_") and ent.name != os.path.basename(old_raw):
                            toks = ent.name.split("_")
                            if len(toks) >= 4 and toks[-2].isdigit() and not is_process_alive(int(toks[-2])):
                                try:
                                    ins_robust_rmtree(ent.path)
                                except OSError:
                                    pass
            except OSError:
                pass


def _prune_contained_symlinks(root_hp: HostPath) -> int:
    raw_root = str(root_hp)
    if not os.path.isdir(raw_root) or is_symlink_or_reparse(raw_root):
        return 0
    removed_count = 0
    visited_dirs: set[tuple[int, int]] = set()
    try:
        st_root = os.lstat(raw_root)
        visited_dirs.add((st_root.st_dev, st_root.st_ino))
    except OSError:
        return 0
    stack: list[str] = [raw_root]
    while stack:
        cur_dir = stack.pop()
        try:
            with os.scandir(cur_dir) as it:
                entries = list(it)
        except OSError:
            continue
        for ent in entries:
            ent_path = ent.path
            if ent.is_symlink() or is_symlink_or_reparse(ent_path):
                _force_file_writable(cur_dir)
                try:
                    os.unlink(ent_path)
                    removed_count += 1
                except OSError:
                    try:
                        os.rmdir(ent_path)
                        removed_count += 1
                    except OSError:
                        pass
                continue
            try:
                if ent.is_dir(follow_symlinks=False):
                    st_sub = ent.stat(follow_symlinks=False)
                    sig = (st_sub.st_dev, st_sub.st_ino)
                    if sig not in visited_dirs:
                        visited_dirs.add(sig)
                        stack.append(ent_path)
            except OSError:
                continue
    return removed_count


class AtomicPackageDeployer:
    """Staging assembler, *.tmpl configuration deployer/stripper, atomic directory swapper, and 5-space cleaner."""

    def __init__(self, *, yscb_root: HostPath, config_store: ConfigStore, vfs: KernelVfs) -> None:
        if not isinstance(yscb_root, HostPath):
            raise ValueError(f"AtomicPackageDeployer.yscb_root must be HostPath, got {yscb_root!r}")
        if not isinstance(config_store, ConfigStore):
            raise ValueError(f"AtomicPackageDeployer.config_store must be ConfigStore, got {config_store!r}")
        if not isinstance(vfs, KernelVfs):
            raise ValueError(f"AtomicPackageDeployer.vfs must be KernelVfs, got {vfs!r}")
        assert_no_symlink_raw_path(str(yscb_root))
        self._yscb_root = yscb_root
        self._modules_root = resolve_contained_subpath(yscb_root, ".modules")
        self._config_store = config_store
        self._vfs = vfs
        self._seq_lock = threading.Lock()
        self._seq = 0
        _InsDeployerRegistry.register(self, AtomicPackageDeployer._materialize_internal)

    def _next_seq(self) -> int:
        with self._seq_lock:
            self._seq += 1
            return self._seq

    def _delete_space_entry(self, scheme: str, subdir: str, module_id: ModuleId) -> None:
        ins_assert_not_reserved_module_id(module_id, label="AtomicPackageDeployer space cleanup")
        if module_id.value == "core":
            raise YscbError(
                ErrorCode.DEPENDENCY_CONFLICT,
                "Core microkernel module 'core' cannot be removed.",
            )
        phys_hp = resolve_contained_subpath(self._yscb_root, subdir, module_id.value)
        uri = SemanticUri(scheme, module_id.value)
        try:
            if self._vfs.exists(uri):
                self._vfs.delete(uri, recursive=True)
        except YscbError as exc:
            if exc.detail.code == ErrorCode.URI_UNDEFINED:
                pass
            elif (
                exc.detail.code == ErrorCode.ACCESS_DENIED
                and "submount" not in exc.detail.message.lower()
                and os.path.isdir(str(phys_hp))
                and not is_symlink_or_reparse(str(phys_hp))
                and _prune_contained_symlinks(phys_hp) > 0
            ):
                try:
                    if self._vfs.exists(uri):
                        self._vfs.delete(uri, recursive=True)
                except YscbError as retry_exc:
                    if retry_exc.detail.code != ErrorCode.URI_UNDEFINED:
                        raise
            else:
                raise
        if os.path.lexists(str(phys_hp)):
            ins_robust_rmtree(str(phys_hp))

    def _materialize_internal(
        self,
        module_id: ModuleId,
        zip_path: HostPath,
        release_override: Optional[IndexReleaseRecord],
        deploy_configurable: bool,
    ) -> ModuleManifest:
        if not isinstance(module_id, ModuleId):
            raise ValueError(f"AtomicPackageDeployer.materialize_module requires ModuleId, got {module_id!r}")
        ins_assert_not_reserved_module_id(module_id, label="AtomicPackageDeployer.materialize_module")
        if not isinstance(zip_path, HostPath):
            raise ValueError(f"AtomicPackageDeployer.materialize_module requires HostPath, got {zip_path!r}")
        if release_override is not None and not isinstance(release_override, IndexReleaseRecord):
            raise ValueError(
                f"release_override must be IndexReleaseRecord or None, got {release_override!r}"
            )

        ins_verify_zip_archive(zip_path, expected_sha256=None, ignore_sha256=True)

        seq = self._next_seq()
        try:
            assert_no_symlink_raw_path(str(self._modules_root))
            os.makedirs(str(self._modules_root), exist_ok=True)
            assert_no_symlink_raw_path(str(self._modules_root))
            staging_hp = resolve_contained_subpath(
                self._modules_root,
                f".staging_{module_id.value}_{os.getpid()}_{seq}",
            )
            if os.path.lexists(str(staging_hp)):
                ins_robust_rmtree(str(staging_hp))
            os.makedirs(str(staging_hp), exist_ok=False)
        except OSError as exc:
            raise YscbError(
                ErrorCode.PACKAGE_INTEGRITY_ERROR,
                f"Failed preparing module staging directory under '{self._modules_root}': {safe_exception_summary(exc)}",
            ) from exc

        try:
            _extract_verified_zip_into_staging(zip_path, staging_hp)

            mf_hp = resolve_contained_subpath(staging_hp, "manifest.json")
            try:
                mf_bytes = read_nofollow_regular_bytes(str(mf_hp), max_bytes=MAX_JSON_FILE_BYTES)
            except OSError:
                mf_bytes = None
            if mf_bytes is None:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Extracted package for '{module_id}' is missing regular manifest.json.",
                )
            try:
                raw_mf: JsonObject = strict_parse_json_object(mf_bytes.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Malformed manifest.json in package for '{module_id}': {safe_exception_summary(exc)}",
                ) from exc

            manifest = ins_parse_manifest_dict(raw_mf, expected_module_id=module_id)
            if release_override is not None and manifest.version != release_override.version:
                raise YscbError(
                    ErrorCode.PACKAGE_INTEGRITY_ERROR,
                    f"Extracted manifest version '{manifest.version}' for '{module_id}' mismatches release version '{release_override.version}'.",
                )
            if ins_has_dependencies_override(release_override) and release_override is not None:
                manifest = ins_override_manifest_dependencies(manifest, release_override.dependencies)
                patched_mf = ins_rewrite_manifest_dependencies_json(raw_mf, release_override.dependencies)
                atomic_write_json(mf_hp, patched_mf)
            elif "schema_version" not in raw_mf or "description" not in raw_mf:
                atomic_write_json(
                    mf_hp,
                    ins_rewrite_manifest_dependencies_json(raw_mf, manifest.dependencies),
                )

            if deploy_configurable:
                schema_defaults = _read_config_schema_defaults(staging_hp)
                staging_cfg_dir = resolve_contained_subpath(staging_hp, "configurable")
                if os.path.isdir(str(staging_cfg_dir)) or bool(schema_defaults):
                    self._config_store.deploy_configurable(
                        module_id,
                        staging_cfg_dir,
                        default_config_template=schema_defaults if schema_defaults else None,
                    )

            _strip_staging_templates_and_verify(staging_hp)

            target_hp = resolve_contained_subpath(self._modules_root, module_id.value)
            _atomic_swap_staged_module_dir(
                staging_hp,
                target_hp,
                self._modules_root,
                module_id.value,
                seq,
            )
            return manifest
        finally:
            if os.path.lexists(str(staging_hp)):
                ins_robust_rmtree(str(staging_hp))

    def materialize_module(
        self,
        module_id: ModuleId,
        zip_path: HostPath,
        *,
        release_override: Optional[IndexReleaseRecord] = None,
    ) -> ModuleManifest:
        return self._materialize_internal(module_id, zip_path, release_override, True)

    def remove_module(self, module_id: ModuleId, *, purge_level: PurgeLevel = PurgeLevel.NONE) -> None:
        if not isinstance(module_id, ModuleId):
            raise ValueError(f"AtomicPackageDeployer.remove_module requires ModuleId, got {module_id!r}")
        if not isinstance(purge_level, PurgeLevel):
            raise ValueError(f"AtomicPackageDeployer.remove_module requires PurgeLevel, got {purge_level!r}")
        ins_assert_not_reserved_module_id(module_id, label="AtomicPackageDeployer.remove_module")
        if module_id.value == "core":
            raise YscbError(
                ErrorCode.DEPENDENCY_CONFLICT,
                "Core microkernel module 'core' cannot be removed.",
            )

        self._delete_space_entry("module", ".modules", module_id)

        if purge_level == PurgeLevel.CLEAN:
            for scheme, subdir in _CLEAN_SCHEME_PAIRS:
                self._delete_space_entry(scheme, subdir, module_id)
        elif purge_level == PurgeLevel.PURGE:
            for scheme, subdir in _PURGE_SCHEME_PAIRS:
                self._delete_space_entry(scheme, subdir, module_id)
