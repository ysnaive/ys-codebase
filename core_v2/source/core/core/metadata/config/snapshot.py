"""Smart deduplicating and atomic workspace configuration SnapshotVault."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import time
from typing import Final, Mapping, Optional
import uuid

from core.filesystem.fs import (
    IGNORED_FS_PREFIXES,
    FileLock,
    MAX_JSON_FILE_BYTES,
    assert_no_symlink_raw_path,
    atomic_write_bytes,
    atomic_write_json,
    has_symlink_raw_path,
    is_atomic_staging_filename,
    is_symlink_or_reparse,
    read_json_dict,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
    silent_unlink,
    walk_nonsymlink_dir_tree,
)
from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary
from core.foundation.proc import is_process_alive
from core.foundation.primitives import (
    IS_WINDOWS,
    HostPath,
    JsonObject,
    JsonValue,
    MutableJsonObject,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    safe_real_to_float,
    validate_relative_segment,
)

_CFG_SNAPSHOTS_DIRNAME: Final[str] = ".snapshots"
_CFG_SNAP_META_FILENAME: Final[str] = "snapshot.meta.json"
_CFG_HOST_CONFIG_FILENAME: Final[str] = "yscb.config.json"
_CFG_SNAP_ID_RE: Final[re.Pattern[str]] = re.compile(r"^snap_\d{8}T\d{12}Z_(\d+)$")
_CFG_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_CFG_BACKUP_AREAS: Final[tuple[tuple[str, str], ...]] = (
    ("config", "config"),
    ("storage", "storage"),
)


@dataclass(frozen=True, slots=True)
class _CfgAreaCapture:
    exists: bool
    dirs: tuple[str, ...]
    files: tuple[tuple[str, str, bytes], ...]


@dataclass(frozen=True, slots=True)
class _CfgLiveWorkspaceCapture:
    host_config_bytes: Optional[bytes]
    host_config_sha256: Optional[str]
    areas: Mapping[str, _CfgAreaCapture]
    state_fingerprint: str


@dataclass(frozen=True, slots=True)
class _CfgStoredSnapshotRecord:
    meta: SnapshotMeta
    seq_num: int
    snap_dir: HostPath
    host_config_sha256: Optional[str]
    area_dirs: Mapping[str, tuple[str, ...]]
    area_files: Mapping[str, Mapping[str, str]]


@dataclass(frozen=True, slots=True)
class _CfgVerifiedAreaPayload:
    exists: bool
    dirs: tuple[str, ...]
    files: tuple[tuple[str, bytes], ...]


def _cfg_snapshot_sort_key(rec: _CfgStoredSnapshotRecord) -> tuple[float, int, str]:
    return (rec.meta.created_epoch_sec, rec.seq_num, rec.meta.snapshot_id)


def _cfg_require_vault_host_path(val: object, label: str) -> HostPath:
    if not isinstance(val, HostPath):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"{label} must be HostPath, got {val!r}")
    if has_symlink_raw_path(str(val)):
        raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink {label}: {val}")
    return val


def _cfg_replace_dir_with_nt_retry(src_dir: str, dst_dir: str) -> None:
    if not IS_WINDOWS:
        os.replace(src_dir, dst_dir)
        return
    for attempt in range(8):
        try:
            os.replace(src_dir, dst_dir)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.015 * (attempt + 1))


def _cfg_chmod_writable_best_effort(raw_path: str, *, is_dir: bool) -> None:
    if not raw_path or is_symlink_or_reparse(raw_path):
        return
    try:
        st = os.lstat(raw_path)
        if stat.S_ISLNK(st.st_mode):
            return
        os.chmod(raw_path, 0o700 if is_dir else 0o600)
    except OSError:
        return


def _cfg_unlink_link_or_reparse(raw_path: str) -> None:
    try:
        os.unlink(raw_path)
        return
    except FileNotFoundError:
        return
    except OSError:
        try:
            os.rmdir(raw_path)
        except OSError:
            return


def _cfg_unlink_nofollow_retry(raw_path: str) -> None:
    if is_symlink_or_reparse(raw_path):
        _cfg_unlink_link_or_reparse(raw_path)
        return
    for attempt in range(6):
        try:
            os.unlink(raw_path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            _cfg_chmod_writable_best_effort(raw_path, is_dir=False)
            if attempt == 5:
                return
            if IS_WINDOWS:
                time.sleep(0.01 * (attempt + 1))
        except OSError:
            return


def _cfg_rmtree_nofollow_best_effort(root_dir: str) -> None:
    if not os.path.lexists(root_dir):
        return
    if is_symlink_or_reparse(root_dir):
        _cfg_unlink_link_or_reparse(root_dir)
        return
    try:
        st = os.lstat(root_dir)
    except OSError:
        return
    if not stat.S_ISDIR(st.st_mode):
        _cfg_unlink_nofollow_retry(root_dir)
        return

    dirs_postorder: list[str] = []
    stack: list[str] = [root_dir]
    while stack:
        cur = stack.pop()
        dirs_postorder.append(cur)
        _cfg_chmod_writable_best_effort(cur, is_dir=True)
        try:
            with os.scandir(cur) as it:
                entries = list(it)
        except OSError:
            continue
        for ent in entries:
            if ent.is_symlink() or is_symlink_or_reparse(ent.path):
                _cfg_unlink_link_or_reparse(ent.path)
                continue
            try:
                if ent.is_dir(follow_symlinks=False):
                    stack.append(ent.path)
                else:
                    _cfg_unlink_nofollow_retry(ent.path)
            except OSError:
                _cfg_unlink_nofollow_retry(ent.path)

    for dir_path in reversed(dirs_postorder):
        for attempt in range(6):
            try:
                os.rmdir(dir_path)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                _cfg_chmod_writable_best_effort(dir_path, is_dir=True)
                if IS_WINDOWS and attempt < 5:
                    time.sleep(0.01 * (attempt + 1))
                else:
                    break
            except OSError:
                break


def _cfg_capture_single_area(yscb_root: HostPath, subdir_name: str) -> _CfgAreaCapture:
    area_root = resolve_contained_subpath(yscb_root, subdir_name)
    raw_area = str(area_root)
    if not os.path.lexists(raw_area):
        return _CfgAreaCapture(exists=False, dirs=(), files=())
    if is_symlink_or_reparse(raw_area) or has_symlink_raw_path(raw_area):
        raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlinked directory during snapshot: {area_root}")
    if not os.path.isdir(raw_area):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Expected directory at '{area_root}', found non-directory.")

    rel_dirs: list[str] = ["."]
    captured_files: list[tuple[str, str, bytes]] = []
    for cur_dir, entries in walk_nonsymlink_dir_tree(raw_area):
        rel_cur = os.path.relpath(cur_dir, raw_area)
        dir_parts = () if rel_cur in ("", ".") else tuple(Path(rel_cur).parts)
        if dir_parts:
            rel_dirs.append("/".join(dir_parts))
        for ent in entries:
            if ent.name.startswith(IGNORED_FS_PREFIXES) or is_atomic_staging_filename(ent.name):
                continue
            if ent.is_symlink() or is_symlink_or_reparse(ent.path):
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Refusing symlink inside '{area_root}': {ent.path}",
                )
            try:
                is_reg = ent.is_file(follow_symlinks=False)
            except OSError as exc:
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"Failed reading '{ent.path}' during snapshot: {safe_exception_summary(exc)}",
                ) from exc
            if not is_reg:
                continue
            raw_bytes = read_nofollow_regular_bytes(ent.path)
            if raw_bytes is None:
                if has_symlink_raw_path(ent.path):
                    raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlinked file: {ent.path}")
                raise YscbError(ErrorCode.CONFIG_INVALID, f"Failed reading regular file during snapshot: {ent.path}")
            rel_posix = "/".join((*dir_parts, ent.name))
            digest = hashlib.sha256(raw_bytes).hexdigest()
            captured_files.append((rel_posix, digest, raw_bytes))

    rel_dirs.sort()
    captured_files.sort(key=lambda item: item[0])
    return _CfgAreaCapture(
        exists=True,
        dirs=tuple(rel_dirs),
        files=tuple(captured_files),
    )


def _cfg_compute_state_fingerprint(
    host_sha256: Optional[str],
    areas: Mapping[str, _CfgAreaCapture],
) -> str:
    manifest_doc: MutableJsonObject = {
        "host_config": host_sha256,
        "areas": {
            area_key: {
                "exists": area_cap.exists,
                "dirs": list(area_cap.dirs),
                "files": [[rel_p, sha] for rel_p, sha, _data in area_cap.files],
            }
            for area_key, _subdir in _CFG_BACKUP_AREAS
            for area_cap in (areas[area_key],)
        },
    }
    wire = json.dumps(
        manifest_doc,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(wire).hexdigest()


def _cfg_capture_live_workspace(host_dir: HostPath, yscb_root: HostPath) -> _CfgLiveWorkspaceCapture:
    host_cfg_path = resolve_contained_subpath(host_dir, _CFG_HOST_CONFIG_FILENAME)
    raw_host_cfg = str(host_cfg_path)
    host_bytes: Optional[bytes] = None
    host_sha: Optional[str] = None
    if os.path.lexists(raw_host_cfg):
        host_bytes = read_nofollow_regular_bytes(raw_host_cfg, max_bytes=MAX_JSON_FILE_BYTES)
        if host_bytes is None:
            if has_symlink_raw_path(raw_host_cfg):
                raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlinked {_CFG_HOST_CONFIG_FILENAME}")
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Unreadable {_CFG_HOST_CONFIG_FILENAME}: {host_cfg_path}")
        host_sha = hashlib.sha256(host_bytes).hexdigest()

    areas: dict[str, _CfgAreaCapture] = {}
    for area_key, subdir_name in _CFG_BACKUP_AREAS:
        areas[area_key] = _cfg_capture_single_area(yscb_root, subdir_name)

    fp = _cfg_compute_state_fingerprint(host_sha, areas)
    return _CfgLiveWorkspaceCapture(
        host_config_bytes=host_bytes,
        host_config_sha256=host_sha,
        areas=areas,
        state_fingerprint=fp,
    )


def _cfg_validate_rel_posix_path(raw_rel: object, *, allow_dot: bool) -> Optional[str]:
    if type(raw_rel) is not str or not raw_rel:
        return None
    if allow_dot and raw_rel == ".":
        return "."
    if "\\" in raw_rel or raw_rel.startswith("/") or raw_rel.endswith("/"):
        return None
    segs = raw_rel.split("/")
    if not segs or any(not s for s in segs):
        return None
    for seg in segs:
        if not _cfg_is_safe_snap_segment(seg):
            return None
    return "/".join(segs)


def _cfg_is_safe_snap_segment(seg: str) -> bool:
    try:
        validate_relative_segment(seg, label="snapshot entry segment")
        return True
    except ValueError:
        return False


def _cfg_parse_stored_snapshot(snap_dir: HostPath, expected_id: str) -> Optional[_CfgStoredSnapshotRecord]:
    m_id = _CFG_SNAP_ID_RE.fullmatch(expected_id)
    if m_id is None:
        return None
    seq_num = int(m_id.group(1))
    doc = read_json_dict(snap_dir, _CFG_SNAP_META_FILENAME)
    if doc is None or doc.get("schema_version") != 2:
        return None
    snap_id = doc.get("snapshot_id")
    created_utc = doc.get("created_at_utc")
    created_ep = doc.get("created_epoch_sec")
    tag = doc.get("tag")
    state_fp = doc.get("state_fingerprint")
    host_sha = doc.get("host_config_sha256")
    raw_dirs = doc.get("dirs")
    raw_entries = doc.get("entries")
    if (
        snap_id != expected_id
        or type(created_utc) is not str
        or type(tag) is not str
        or type(state_fp) is not str
        or _CFG_SHA256_RE.fullmatch(state_fp) is None
        or type(created_ep) not in (int, float)
        or not isinstance(raw_dirs, Mapping)
        or not isinstance(raw_entries, Mapping)
    ):
        return None
    if host_sha is not None and (type(host_sha) is not str or _CFG_SHA256_RE.fullmatch(host_sha) is None):
        return None

    parsed_dirs: dict[str, tuple[str, ...]] = {}
    parsed_files: dict[str, Mapping[str, str]] = {}
    for area_key, _subdir in _CFG_BACKUP_AREAS:
        d_list = raw_dirs.get(area_key)
        f_map = raw_entries.get(area_key)
        if not isinstance(d_list, list) or not isinstance(f_map, Mapping):
            return None
        clean_d: list[str] = []
        for item in d_list:
            norm_d = _cfg_validate_rel_posix_path(item, allow_dot=True)
            if norm_d is None:
                return None
            clean_d.append(norm_d)
        clean_f: dict[str, str] = {}
        for rk, rv in f_map.items():
            norm_f = _cfg_validate_rel_posix_path(rk, allow_dot=False)
            if norm_f is None or type(rv) is not str or _CFG_SHA256_RE.fullmatch(rv) is None:
                return None
            clean_f[norm_f] = rv
        parsed_dirs[area_key] = tuple(clean_d)
        parsed_files[area_key] = clean_f

    try:
        meta = SnapshotMeta(
            snapshot_id=expected_id,
            created_at_utc=created_utc,
            created_epoch_sec=float(created_ep),
            tag=tag,
            state_fingerprint=state_fp,
            reused=False,
        )
    except YscbError:
        return None

    return _CfgStoredSnapshotRecord(
        meta=meta,
        seq_num=seq_num,
        snap_dir=snap_dir,
        host_config_sha256=host_sha,
        area_dirs=parsed_dirs,
        area_files=parsed_files,
    )


def _cfg_scan_stored_snapshots(yscb_root: HostPath) -> list[_CfgStoredSnapshotRecord]:
    snaps_root = resolve_contained_subpath(yscb_root, _CFG_SNAPSHOTS_DIRNAME)
    raw_root = str(snaps_root)
    if not os.path.lexists(raw_root):
        return []
    if is_symlink_or_reparse(raw_root) or not os.path.isdir(raw_root):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid .snapshots root: {snaps_root}")
    records: list[_CfgStoredSnapshotRecord] = []
    try:
        with os.scandir(raw_root) as it:
            entries = list(it)
    except OSError as exc:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Failed scanning '{snaps_root}': {safe_exception_summary(exc)}",
        ) from exc
    for ent in entries:
        if ent.name.startswith(".") or ent.is_symlink() or is_symlink_or_reparse(ent.path):
            continue
        try:
            if not ent.is_dir(follow_symlinks=False):
                continue
            child_hp = resolve_contained_subpath(snaps_root, ent.name)
        except (OSError, ValueError, YscbError):
            continue
        rec = _cfg_parse_stored_snapshot(child_hp, ent.name)
        if rec is not None:
            records.append(rec)
    records.sort(key=_cfg_snapshot_sort_key)
    return records


def _cfg_write_snapshot_staging(
    staging_dir: HostPath,
    snap_id: str,
    created_utc: str,
    created_epoch: float,
    tag: str,
    capture: _CfgLiveWorkspaceCapture,
) -> None:
    raw_staging = str(staging_dir)
    assert_no_symlink_raw_path(raw_staging)
    os.makedirs(raw_staging, exist_ok=False)

    if capture.host_config_bytes is not None:
        host_dst = resolve_contained_subpath(staging_dir, "payload", "host", _CFG_HOST_CONFIG_FILENAME)
        atomic_write_bytes(host_dst, capture.host_config_bytes)

    dirs_json: MutableJsonObject = {}
    entries_json: MutableJsonObject = {}
    for area_key, _subdir in _CFG_BACKUP_AREAS:
        area_cap = capture.areas[area_key]
        dirs_list: list[JsonValue] = list(area_cap.dirs)
        files_map: MutableJsonObject = {}
        if area_cap.exists:
            area_payload_root = resolve_contained_subpath(staging_dir, "payload", area_key)
            os.makedirs(str(area_payload_root), exist_ok=True)
            for rel_dir in area_cap.dirs:
                if rel_dir != ".":
                    sub_hp = resolve_contained_subpath(area_payload_root, *rel_dir.split("/"))
                    os.makedirs(str(sub_hp), exist_ok=True)
            for rel_posix, sha_hex, file_bytes in area_cap.files:
                file_hp = resolve_contained_subpath(area_payload_root, *rel_posix.split("/"))
                atomic_write_bytes(file_hp, file_bytes)
                files_map[rel_posix] = sha_hex
        dirs_json[area_key] = dirs_list
        entries_json[area_key] = files_map

    meta_doc: JsonObject = {
        "schema_version": 2,
        "snapshot_id": snap_id,
        "created_at_utc": created_utc,
        "created_epoch_sec": created_epoch,
        "tag": tag,
        "state_fingerprint": capture.state_fingerprint,
        "host_config_sha256": capture.host_config_sha256,
        "dirs": dirs_json,
        "entries": entries_json,
    }
    meta_dst = resolve_contained_subpath(staging_dir, _CFG_SNAP_META_FILENAME)
    atomic_write_json(meta_dst, meta_doc)


def _cfg_verify_and_load_snapshot_payload(
    rec: _CfgStoredSnapshotRecord,
) -> tuple[Optional[bytes], Mapping[str, _CfgVerifiedAreaPayload]]:
    host_bytes: Optional[bytes] = None
    if rec.host_config_sha256 is not None:
        host_src = resolve_contained_subpath(rec.snap_dir, "payload", "host", _CFG_HOST_CONFIG_FILENAME)
        try:
            host_bytes = read_nofollow_regular_bytes(str(host_src), max_bytes=MAX_JSON_FILE_BYTES)
        except OSError:
            host_bytes = None
        if host_bytes is None or hashlib.sha256(host_bytes).hexdigest() != rec.host_config_sha256:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Snapshot '{rec.meta.snapshot_id}' failed integrity check for {_CFG_HOST_CONFIG_FILENAME}.",
            )

    verified_areas: dict[str, _CfgVerifiedAreaPayload] = {}
    for area_key, _subdir in _CFG_BACKUP_AREAS:
        d_tup = rec.area_dirs[area_key]
        f_map = rec.area_files[area_key]
        exists_flag = bool(d_tup or f_map)
        loaded_files: list[tuple[str, bytes]] = []
        if exists_flag:
            area_src_root = resolve_contained_subpath(rec.snap_dir, "payload", area_key)
            for rel_posix, exp_sha in sorted(f_map.items()):
                f_src = resolve_contained_subpath(area_src_root, *rel_posix.split("/"))
                try:
                    f_bytes = read_nofollow_regular_bytes(str(f_src))
                except OSError:
                    f_bytes = None
                if f_bytes is None or hashlib.sha256(f_bytes).hexdigest() != exp_sha:
                    raise YscbError(
                        ErrorCode.CONFIG_INVALID,
                        f"Snapshot '{rec.meta.snapshot_id}' failed integrity check for '{area_key}/{rel_posix}'.",
                    )
                loaded_files.append((rel_posix, f_bytes))
        verified_areas[area_key] = _CfgVerifiedAreaPayload(
            exists=exists_flag,
            dirs=d_tup,
            files=tuple(loaded_files),
        )
    return (host_bytes, verified_areas)


def _cfg_materialize_restore_staging_dir(
    staging_dir: HostPath,
    payload: _CfgVerifiedAreaPayload,
) -> None:
    raw_staging = str(staging_dir)
    assert_no_symlink_raw_path(raw_staging)
    os.makedirs(raw_staging, exist_ok=False)
    for rel_dir in payload.dirs:
        if rel_dir != ".":
            sub_hp = resolve_contained_subpath(staging_dir, *rel_dir.split("/"))
            os.makedirs(str(sub_hp), exist_ok=True)
    for rel_posix, f_bytes in payload.files:
        f_hp = resolve_contained_subpath(staging_dir, *rel_posix.split("/"))
        atomic_write_bytes(f_hp, f_bytes)


def _cfg_sync_area_in_place(
    live_hp: HostPath,
    payload: _CfgVerifiedAreaPayload,
) -> None:
    raw_live = str(live_hp)
    assert_no_symlink_raw_path(raw_live)
    target_files: dict[str, bytes] = dict(payload.files)
    target_dirs: set[str] = set()
    for rel_dir in payload.dirs:
        if rel_dir != ".":
            parts = rel_dir.split("/")
            for idx in range(1, len(parts) + 1):
                target_dirs.add("/".join(parts[:idx]))
    for rel_posix in target_files:
        parts = rel_posix.split("/")
        for idx in range(1, len(parts)):
            target_dirs.add("/".join(parts[:idx]))

    if payload.exists:
        os.makedirs(raw_live, exist_ok=True)
        for rel_dir in sorted(target_dirs, key=lambda d: (d.count("/"), d)):
            sub_hp = resolve_contained_subpath(live_hp, *rel_dir.split("/"))
            raw_sub = str(sub_hp)
            if is_symlink_or_reparse(raw_sub):
                raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink inside '{live_hp}': {raw_sub}")
            if os.path.lexists(raw_sub) and not os.path.isdir(raw_sub):
                _cfg_unlink_nofollow_retry(raw_sub)
            os.makedirs(raw_sub, exist_ok=True)
        for rel_posix, f_bytes in payload.files:
            f_hp = resolve_contained_subpath(live_hp, *rel_posix.split("/"))
            raw_f = str(f_hp)
            if is_symlink_or_reparse(raw_f):
                raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink inside '{live_hp}': {raw_f}")
            if os.path.isdir(raw_f):
                _cfg_rmtree_nofollow_best_effort(raw_f)
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
                raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink inside '{live_hp}': {ent.path}")
            if ent.is_file(follow_symlinks=False):
                rel_file = "/".join((*dir_parts, ent.name))
                if not payload.exists or rel_file not in target_files:
                    _cfg_unlink_nofollow_retry(ent.path)
    for rel_dir, raw_dir in sorted(existing_dirs, key=lambda item: item[0].count("/"), reverse=True):
        if not payload.exists or rel_dir not in target_dirs:
            try:
                os.rmdir(raw_dir)
            except OSError:
                pass
    if not payload.exists:
        try:
            os.rmdir(raw_live)
        except OSError:
            pass


def _cfg_extract_temp_owner_pid(entry_name: str) -> Optional[int]:
    tokens = entry_name.split("_")
    if len(tokens) >= 3 and tokens[-2].isdigit() and len(tokens[-2]) <= 10:
        return int(tokens[-2])
    return None


def _cfg_execute_atomic_restore_swap(
    host_dir: HostPath,
    yscb_root: HostPath,
    host_bytes: Optional[bytes],
    areas: Mapping[str, _CfgVerifiedAreaPayload],
) -> None:
    nonce = f"{os.getpid()}_{uuid.uuid4().hex[:10]}"
    os.makedirs(str(yscb_root), exist_ok=True)
    os.makedirs(str(host_dir), exist_ok=True)

    host_cfg_dest = resolve_contained_subpath(host_dir, _CFG_HOST_CONFIG_FILENAME)
    raw_host_dest = str(host_cfg_dest)
    had_prev_host = os.path.lexists(raw_host_dest)
    prev_host_bytes: Optional[bytes] = None
    if had_prev_host:
        try:
            prev_host_bytes = read_nofollow_regular_bytes(raw_host_dest, max_bytes=MAX_JSON_FILE_BYTES)
        except OSError as exc:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Cannot read existing {_CFG_HOST_CONFIG_FILENAME} prior to snapshot restore: {safe_exception_summary(exc)}",
            ) from exc
        if prev_host_bytes is None:
            if has_symlink_raw_path(raw_host_dest) or is_symlink_or_reparse(raw_host_dest):
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Refusing symlinked {_CFG_HOST_CONFIG_FILENAME} during snapshot restore.",
                )
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Existing {_CFG_HOST_CONFIG_FILENAME} is non-regular or exceeds size limit.",
            )

    staged_paths: dict[str, HostPath] = {}
    backup_paths: dict[str, HostPath] = {}
    displaced_live: list[tuple[HostPath, HostPath]] = []
    placed_live: list[HostPath] = []
    inplace_backups: list[tuple[HostPath, _CfgVerifiedAreaPayload]] = []
    host_mutated = False
    commit_ok = False

    try:
        for area_key, _subdir_name in _CFG_BACKUP_AREAS:
            area_payload = areas[area_key]
            if area_payload.exists:
                stg_hp = resolve_contained_subpath(
                    yscb_root,
                    f".staging_restore_{area_key}_{nonce}",
                )
                _cfg_materialize_restore_staging_dir(stg_hp, area_payload)
                staged_paths[area_key] = stg_hp

        for area_key, subdir_name in _CFG_BACKUP_AREAS:
            live_hp = resolve_contained_subpath(yscb_root, subdir_name)
            raw_live = str(live_hp)
            if os.path.lexists(raw_live) and (is_symlink_or_reparse(raw_live) or has_symlink_raw_path(raw_live)):
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Refusing symlinked directory during snapshot restore: {live_hp}",
                )
            if os.path.lexists(raw_live):
                bak_hp = resolve_contained_subpath(
                    yscb_root,
                    f".tmp_prev_{area_key}_{nonce}",
                )
                try:
                    _cfg_replace_dir_with_nt_retry(raw_live, str(bak_hp))
                except OSError:
                    if not os.path.isdir(raw_live) or is_symlink_or_reparse(raw_live):
                        raise
                    prev_cap = _cfg_capture_single_area(yscb_root, subdir_name)
                    inplace_backups.append(
                        (
                            live_hp,
                            _CfgVerifiedAreaPayload(
                                exists=prev_cap.exists,
                                dirs=prev_cap.dirs,
                                files=tuple((rp, fb) for rp, _sh, fb in prev_cap.files),
                            ),
                        )
                    )
                    _cfg_sync_area_in_place(live_hp, areas[area_key])
                    continue
                backup_paths[area_key] = bak_hp
                displaced_live.append((live_hp, bak_hp))
            stg_hp_opt = staged_paths.get(area_key)
            if stg_hp_opt is not None:
                _cfg_replace_dir_with_nt_retry(str(stg_hp_opt), raw_live)
                staged_paths.pop(area_key, None)
                placed_live.append(live_hp)

        host_mutated = True
        if host_bytes is not None:
            atomic_write_bytes(host_cfg_dest, host_bytes)
        else:
            silent_unlink(host_cfg_dest)
        commit_ok = True
    except BaseException as exc:
        if host_mutated:
            if had_prev_host and prev_host_bytes is not None:
                try:
                    atomic_write_bytes(host_cfg_dest, prev_host_bytes)
                except (OSError, ValueError, YscbError):
                    pass
            elif not had_prev_host:
                silent_unlink(host_cfg_dest)
        for live_hp, prev_payload in reversed(inplace_backups):
            try:
                _cfg_sync_area_in_place(live_hp, prev_payload)
            except (OSError, ValueError, YscbError):
                pass
        for placed_hp in reversed(placed_live):
            _cfg_rmtree_nofollow_best_effort(str(placed_hp))
        for live_hp, bak_hp in reversed(displaced_live):
            if os.path.lexists(str(bak_hp)):
                if os.path.lexists(str(live_hp)):
                    _cfg_rmtree_nofollow_best_effort(str(live_hp))
                try:
                    _cfg_replace_dir_with_nt_retry(str(bak_hp), str(live_hp))
                except OSError:
                    pass
        if isinstance(exc, YscbError):
            raise
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Atomic snapshot restore failed and was rolled back: {safe_exception_summary(exc)}",
        ) from exc
    finally:
        for stg_rem in staged_paths.values():
            _cfg_rmtree_nofollow_best_effort(str(stg_rem))
        if commit_ok:
            for bak_rem in backup_paths.values():
                if os.path.lexists(str(bak_rem)):
                    _cfg_rmtree_nofollow_best_effort(str(bak_rem))


@dataclass(frozen=True, slots=True)
class SnapshotRetentionPolicy:
    """Smart snapshot retention and burst-coalescing deduplication policy."""

    max_snapshots: int = 3
    max_age_days: float = 7.0
    coalesce_window_sec: float = 60.0

    def __post_init__(self) -> None:
        try:
            require_pure_int(self.max_snapshots, "SnapshotRetentionPolicy.max_snapshots", min_val=1)
            max_age = safe_real_to_float(self.max_age_days, label="SnapshotRetentionPolicy.max_age_days")
            coalesce = safe_real_to_float(
                self.coalesce_window_sec,
                label="SnapshotRetentionPolicy.coalesce_window_sec",
            )
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
        if not math.isfinite(max_age) or max_age < 0.0:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"SnapshotRetentionPolicy.max_age_days must be finite and >= 0, got {self.max_age_days!r}",
            )
        if not math.isfinite(coalesce) or coalesce < 0.0:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"SnapshotRetentionPolicy.coalesce_window_sec must be finite and >= 0, got {self.coalesce_window_sec!r}",
            )
        object.__setattr__(self, "max_age_days", max_age)
        object.__setattr__(self, "coalesce_window_sec", coalesce)


@dataclass(frozen=True, slots=True)
class SnapshotMeta:
    """Immutable metadata describing a workspace configuration snapshot."""

    snapshot_id: str
    created_at_utc: str
    created_epoch_sec: float
    tag: str
    state_fingerprint: str
    reused: bool = False

    def __post_init__(self) -> None:
        try:
            require_pure_str(self.snapshot_id, "SnapshotMeta.snapshot_id", non_empty=True)
            validate_relative_segment(self.snapshot_id, label="SnapshotMeta.snapshot_id")
            require_pure_str(self.created_at_utc, "SnapshotMeta.created_at_utc", non_empty=True)
            epoch_val = safe_real_to_float(self.created_epoch_sec, label="SnapshotMeta.created_epoch_sec")
            require_pure_str(self.tag, "SnapshotMeta.tag", non_empty=True)
            require_pure_str(self.state_fingerprint, "SnapshotMeta.state_fingerprint", non_empty=True)
            require_pure_bool(self.reused, "SnapshotMeta.reused")
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
        if self.snapshot_id.startswith("."):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"SnapshotMeta.snapshot_id cannot start with '.': {self.snapshot_id!r}",
            )
        if not math.isfinite(epoch_val) or epoch_val < 0.0:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"SnapshotMeta.created_epoch_sec must be finite and >= 0, got {self.created_epoch_sec!r}",
            )
        if _CFG_SHA256_RE.fullmatch(self.state_fingerprint) is None:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"SnapshotMeta.state_fingerprint must be 64-char lowercase hex SHA-256, got {self.state_fingerprint!r}",
            )
        object.__setattr__(self, "created_epoch_sec", epoch_val)


class SnapshotVault:
    """Dual-layer atomic configuration snapshot vault excluding .storage.local/ and .cache/."""

    def __init__(
        self,
        *,
        host_dir: HostPath,
        yscb_root: HostPath,
        policy: SnapshotRetentionPolicy = SnapshotRetentionPolicy(),
    ) -> None:
        self._host_dir = _cfg_require_vault_host_path(host_dir, "SnapshotVault.host_dir")
        self._yscb_root = _cfg_require_vault_host_path(yscb_root, "SnapshotVault.yscb_root")
        if not isinstance(policy, SnapshotRetentionPolicy):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"SnapshotVault.policy must be SnapshotRetentionPolicy, got {policy!r}",
            )
        self._policy = policy
        self._guard = threading.RLock()

    def _acquire_vault_file_lock(self) -> FileLock:
        snaps_root = resolve_contained_subpath(self._yscb_root, _CFG_SNAPSHOTS_DIRNAME)
        assert_no_symlink_raw_path(str(snaps_root))
        os.makedirs(str(snaps_root), exist_ok=True)
        lock_hp = resolve_contained_subpath(snaps_root, ".vault.lock")
        v_lock = FileLock(lock_hp, allow_transitions=False)
        v_lock.acquire(shared=False, blocking=True, timeout_sec=30.0)
        return v_lock

    def _prune_locked(self, now_epoch: float, *, protected_id: Optional[str]) -> tuple[str, ...]:
        snaps_root = resolve_contained_subpath(self._yscb_root, _CFG_SNAPSHOTS_DIRNAME)
        raw_root = str(snaps_root)
        if not os.path.lexists(raw_root):
            return ()
        try:
            with os.scandir(raw_root) as it:
                for ent in it:
                    if ent.name.startswith((".tmp_", ".staging_")):
                        owner_pid = _cfg_extract_temp_owner_pid(ent.name)
                        if owner_pid is not None and is_process_alive(owner_pid):
                            continue
                        _cfg_rmtree_nofollow_best_effort(ent.path)
                    elif (
                        _CFG_SNAP_ID_RE.fullmatch(ent.name) is not None
                        and not ent.is_symlink()
                        and ent.is_dir(follow_symlinks=False)
                        and not os.path.lexists(os.path.join(ent.path, _CFG_SNAP_META_FILENAME))
                    ):
                        _cfg_rmtree_nofollow_best_effort(ent.path)
        except OSError:
            pass

        records = _cfg_scan_stored_snapshots(self._yscb_root)
        if not records:
            return ()

        max_age_sec = self._policy.max_age_days * 86400.0
        newest_first = list(reversed(records))
        retained_count = 0
        removed_ids: list[str] = []

        for rec in newest_first:
            sid = rec.meta.snapshot_id
            if sid == protected_id:
                retained_count += 1
                continue
            age_sec = now_epoch - rec.meta.created_epoch_sec
            age_expired = (
                (age_sec >= 0.0)
                if self._policy.max_age_days == 0.0
                else (age_sec > max_age_sec)
            )
            if age_expired or retained_count >= self._policy.max_snapshots:
                prune_tmp = resolve_contained_subpath(
                    snaps_root,
                    f".tmp_prune_{sid}_{os.getpid()}_{uuid.uuid4().hex[:8]}",
                )
                try:
                    _cfg_replace_dir_with_nt_retry(str(rec.snap_dir), str(prune_tmp))
                except OSError:
                    meta_hp = resolve_contained_subpath(rec.snap_dir, _CFG_SNAP_META_FILENAME)
                    _cfg_unlink_nofollow_retry(str(meta_hp))
                    if os.path.lexists(str(meta_hp)):
                        retained_count += 1
                    else:
                        _cfg_rmtree_nofollow_best_effort(str(rec.snap_dir))
                        removed_ids.append(sid)
                else:
                    _cfg_rmtree_nofollow_best_effort(str(prune_tmp))
                    removed_ids.append(sid)
            else:
                retained_count += 1

        removed_ids.reverse()
        return tuple(removed_ids)

    def create_snapshot(self, tag: str, *, force: bool = False) -> SnapshotMeta:
        try:
            clean_tag = require_pure_str(tag, "SnapshotVault.create_snapshot tag", non_empty=True)
            require_pure_bool(force, "SnapshotVault.create_snapshot force")
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc

        with self._guard:
            v_lock = self._acquire_vault_file_lock()
            try:
                return self._create_snapshot_under_locks(clean_tag, force=force)
            finally:
                v_lock.release()

    def _create_snapshot_under_locks(self, clean_tag: str, *, force: bool) -> SnapshotMeta:
        now_epoch = time.time()
        now_dt = datetime.now(timezone.utc)
        existing = _cfg_scan_stored_snapshots(self._yscb_root)
        capture = _cfg_capture_live_workspace(self._host_dir, self._yscb_root)

        if not force and existing:
            latest = existing[-1]
            latest_age = now_epoch - latest.meta.created_epoch_sec
            latest_expired = (
                (latest_age >= 0.0)
                if self._policy.max_age_days == 0.0
                else (latest_age > self._policy.max_age_days * 86400.0)
            )
            if not latest_expired:
                if latest.meta.state_fingerprint == capture.state_fingerprint:
                    self._prune_locked(now_epoch, protected_id=latest.meta.snapshot_id)
                    return replace(latest.meta, reused=True)
                if latest_age < self._policy.coalesce_window_sec:
                    self._prune_locked(now_epoch, protected_id=latest.meta.snapshot_id)
                    return replace(latest.meta, reused=True)

        next_seq = (existing[-1].seq_num + 1) if existing else 1
        utc_compact = now_dt.strftime("%Y%m%dT%H%M%S%fZ")
        created_utc = now_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        snap_id = f"snap_{utc_compact}_{next_seq:04d}"

        snaps_root = resolve_contained_subpath(self._yscb_root, _CFG_SNAPSHOTS_DIRNAME)
        assert_no_symlink_raw_path(str(snaps_root))
        os.makedirs(str(snaps_root), exist_ok=True)
        staging_dir = resolve_contained_subpath(
            snaps_root,
            f".tmp_{snap_id}_{os.getpid()}_{uuid.uuid4().hex[:8]}",
        )
        final_dir = resolve_contained_subpath(snaps_root, snap_id)
        try:
            _cfg_write_snapshot_staging(
                staging_dir,
                snap_id,
                created_utc,
                now_epoch,
                clean_tag,
                capture,
            )
            assert_no_symlink_raw_path(str(final_dir))
            _cfg_replace_dir_with_nt_retry(str(staging_dir), str(final_dir))
        except YscbError:
            _cfg_rmtree_nofollow_best_effort(str(staging_dir))
            raise
        except (OSError, ValueError) as exc:
            _cfg_rmtree_nofollow_best_effort(str(staging_dir))
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Failed creating workspace snapshot '{snap_id}': {safe_exception_summary(exc)}",
            ) from exc

        self._prune_locked(now_epoch, protected_id=snap_id)
        return SnapshotMeta(
            snapshot_id=snap_id,
            created_at_utc=created_utc,
            created_epoch_sec=now_epoch,
            tag=clean_tag,
            state_fingerprint=capture.state_fingerprint,
            reused=False,
        )

    def list_snapshots(self) -> tuple[SnapshotMeta, ...]:
        with self._guard:
            records = _cfg_scan_stored_snapshots(self._yscb_root)
            return tuple(rec.meta for rec in reversed(records))

    def restore_snapshot(self, snapshot_id: Optional[str] = None) -> SnapshotMeta:
        target_id: Optional[str] = None
        if snapshot_id is not None:
            try:
                target_id = require_pure_str(snapshot_id, "snapshot_id", non_empty=True)
                validate_relative_segment(target_id, label="snapshot_id")
            except ValueError as exc:
                raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
            if target_id.startswith("."):
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"Invalid snapshot_id {target_id!r}",
                )

        with self._guard:
            v_lock = self._acquire_vault_file_lock()
            try:
                return self._restore_snapshot_under_locks(target_id)
            finally:
                v_lock.release()

    def _restore_snapshot_under_locks(self, target_id: Optional[str]) -> SnapshotMeta:
        records = _cfg_scan_stored_snapshots(self._yscb_root)
        if not records:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                "No valid snapshots available in SnapshotVault to restore.",
            )
        if target_id is None:
            chosen = records[-1]
        else:
            matched = next((r for r in records if r.meta.snapshot_id == target_id), None)
            if matched is None:
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"Snapshot '{target_id}' not found in SnapshotVault.",
                )
            chosen = matched

        host_bytes, verified_areas = _cfg_verify_and_load_snapshot_payload(chosen)
        _cfg_execute_atomic_restore_swap(
            self._host_dir,
            self._yscb_root,
            host_bytes,
            verified_areas,
        )
        return chosen.meta

    def prune(self) -> tuple[str, ...]:
        with self._guard:
            snaps_root = resolve_contained_subpath(self._yscb_root, _CFG_SNAPSHOTS_DIRNAME)
            if not os.path.lexists(str(snaps_root)):
                return ()
            v_lock = self._acquire_vault_file_lock()
            try:
                return self._prune_locked(time.time(), protected_id=None)
            finally:
                v_lock.release()
