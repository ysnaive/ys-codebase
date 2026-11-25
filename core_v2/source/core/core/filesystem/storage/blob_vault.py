"""Sharded content-addressed and keyed binary blob vault restricted to storage.local://."""

from __future__ import annotations

import errno
import hashlib
import io
import os
from pathlib import Path
import re
import stat
import time
from typing import BinaryIO, Final, Optional

from core.filesystem.fs import (
    IGNORED_FS_PREFIXES,
    assert_no_symlink_raw_path,
    atomic_write_bytes,
    has_symlink_raw_path,
    is_atomic_staging_filename,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
    walk_nonsymlink_dir_tree,
)
from core.filesystem.storage.database import stg_verify_local_storage_target
from core.filesystem.vfs import ScopedVfs
from core.foundation.errors import ErrorCode, YscbError
from core.foundation.primitives import (
    IS_WINDOWS,
    HostPath,
    SemanticUri,
    require_pure_str,
    require_typed_frozenset,
    validate_relative_segment,
)

_STG_SHA256_HEX_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_STG_BLOB_OPEN_FLAGS: Final[int] = (
    os.O_RDONLY
    | (os.O_BINARY if IS_WINDOWS else (os.O_NOFOLLOW | os.O_NONBLOCK))
)


def _stg_is_transient_blob_name(name: str) -> bool:
    return (
        name.startswith(IGNORED_FS_PREFIXES)
        or is_atomic_staging_filename(name)
        or ".tmp_" in name
    )


def _stg_parse_ref_segments(raw_ref: str, *, label: str) -> tuple[str, ...]:
    require_pure_str(raw_ref, label)
    if not raw_ref or "\\" in raw_ref or raw_ref.startswith("/") or raw_ref.endswith("/"):
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Invalid {label} {raw_ref!r}: expected normalized POSIX relative blob reference.",
            remediation="Pass a relative blob reference returned by put_content_addressed() or put_keyed().",
        )
    parts = tuple(raw_ref.split("/"))
    if any(not p for p in parts):
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Invalid {label} {raw_ref!r}: empty path segments are forbidden.",
            remediation="Remove consecutive slashes from blob references.",
        )
    for seg in parts:
        if _stg_is_transient_blob_name(seg):
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Invalid {label} {raw_ref!r}: transient staging names are reserved.",
                remediation="Use regular non-staging blob names.",
            )
        try:
            validate_relative_segment(seg, label=label)
        except ValueError as exc:
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Invalid {label} {raw_ref!r}: {exc}",
                remediation="Use safe relative path segments without '..' or reserved characters.",
            ) from exc
    return parts


def _stg_resolve_vault_subpath(root_path: HostPath, parts: tuple[str, ...], raw_ref: str) -> HostPath:
    try:
        return resolve_contained_subpath(root_path, *parts)
    except YscbError as exc:
        if exc.detail.code == ErrorCode.ACCESS_DENIED:
            raise
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Refusing unsafe or symlinked blob path {raw_ref!r}: {exc.detail.message}",
            remediation="Ensure 'storage.local://' contains no symbolic links or reparse points.",
        ) from exc


def _stg_unlink_with_nt_retry(raw_path: str) -> bool:
    for attempt in range(6):
        try:
            os.unlink(raw_path)
            return True
        except FileNotFoundError:
            return False
        except PermissionError:
            if not IS_WINDOWS or attempt == 5:
                raise
            time.sleep(0.01 * (attempt + 1))
    return False


def _stg_prune_empty_parents(leaf_parent: Path, root_dir: Path) -> None:
    norm_root = os.path.normcase(str(root_dir))
    cur = leaf_parent
    while os.path.normcase(str(cur)) != norm_root:
        try:
            if os.path.commonpath([norm_root, os.path.normcase(str(cur))]) != norm_root:
                return
            os.rmdir(cur)
        except (OSError, ValueError):
            return
        cur = cur.parent


class BlobVault:
    """External binary blob vault restricted to storage.local:// to keep large payloads out of SQLite WAL."""

    def __init__(self, vfs: ScopedVfs, root_uri: SemanticUri | str) -> None:
        bound_uri, phys = stg_verify_local_storage_target(
            vfs,
            root_uri,
            label="BlobVault",
            require_non_root=False,
        )
        if phys.path.exists() and not phys.path.is_dir():
            raise YscbError(
                ErrorCode.STORAGE_CORRUPT,
                f"BlobVault target '{bound_uri}' points to a regular file instead of a directory.",
                remediation="Specify a dedicated directory URI such as 'storage.local://@/blobs'.",
            )
        vfs.mkdir(bound_uri, parents=True)
        assert_no_symlink_raw_path(str(phys))
        self._root_uri: SemanticUri = bound_uri
        self._root_path: HostPath = phys

    @property
    def root_uri(self) -> SemanticUri:
        return self._root_uri

    def _resolve_existing_or_target(self, ref: str) -> HostPath:
        parts = _stg_parse_ref_segments(ref, label="blob ref")
        primary = _stg_resolve_vault_subpath(self._root_path, parts, ref)
        if len(parts) == 1 and _STG_SHA256_HEX_RE.fullmatch(parts[0]) is not None and not os.path.lexists(str(primary)):
            digest = parts[0]
            return _stg_resolve_vault_subpath(self._root_path, (digest[:2], f"{digest}.blob"), ref)
        return primary

    def put_content_addressed(self, data: bytes) -> str:
        if type(data) is not bytes:
            raise TypeError(f"BlobVault.put_content_addressed requires exact bytes, got {type(data).__name__}")
        digest = hashlib.sha256(data).hexdigest()
        shard = digest[:2]
        blob_name = f"{digest}.blob"
        ref = f"{shard}/{blob_name}"
        target = _stg_resolve_vault_subpath(self._root_path, (shard, blob_name), ref)
        raw_target = str(target)
        if not has_symlink_raw_path(raw_target):
            try:
                st = os.stat(raw_target, follow_symlinks=False)
            except OSError:
                st = None
            if st is not None and stat.S_ISREG(st.st_mode) and st.st_size == len(data):
                return ref
        atomic_write_bytes(target, data)
        return ref

    def put_keyed(self, key: str, data: bytes) -> str:
        if type(data) is not bytes:
            raise TypeError(f"BlobVault.put_keyed requires exact bytes, got {type(data).__name__}")
        parts = _stg_parse_ref_segments(key, label="blob key")
        ref = "/".join(parts)
        target = _stg_resolve_vault_subpath(self._root_path, parts, ref)
        if os.path.isdir(str(target)):
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"BlobVault key {ref!r} collides with an existing directory inside '{self._root_uri}'.",
                remediation="Choose a file key that does not overlap a directory prefix.",
            )
        atomic_write_bytes(target, data)
        return ref

    def exists(self, ref: str) -> bool:
        target = self._resolve_existing_or_target(ref)
        raw_target = str(target)
        if has_symlink_raw_path(raw_target):
            return False
        try:
            st = os.stat(raw_target, follow_symlinks=False)
        except OSError:
            return False
        return stat.S_ISREG(st.st_mode)

    def get_bytes(self, ref: str) -> Optional[bytes]:
        target = self._resolve_existing_or_target(ref)
        raw_target = str(target)
        if not os.path.lexists(raw_target):
            return None
        try:
            return read_nofollow_regular_bytes(raw_target)
        except FileNotFoundError:
            return None

    def open_read(self, ref: str) -> Optional[BinaryIO]:
        target = self._resolve_existing_or_target(ref)
        raw_target = str(target)
        if not os.path.lexists(raw_target) or has_symlink_raw_path(raw_target):
            return None
        for attempt in range(6):
            try:
                fd = os.open(raw_target, _STG_BLOB_OPEN_FLAGS)
                break
            except FileNotFoundError:
                return None
            except PermissionError:
                if not IS_WINDOWS or attempt == 5 or has_symlink_raw_path(raw_target):
                    raise
                time.sleep(0.005 * (attempt + 1))
            except OSError as exc:
                if not IS_WINDOWS and exc.errno in (errno.ELOOP, errno.ENXIO, errno.EOPNOTSUPP, errno.EMLINK):
                    return None
                raise
        else:
            return None
        fd_owned = True
        try:
            f_st = os.fstat(fd)
            if not stat.S_ISREG(f_st.st_mode) or has_symlink_raw_path(raw_target):
                os.close(fd)
                fd_owned = False
                return None
            if not IS_WINDOWS:
                os.set_blocking(fd, True)
            os.set_inheritable(fd, False)
            raw_io = io.FileIO(fd, "rb", closefd=True)
            fd_owned = False
            return io.BufferedReader(raw_io)
        except BaseException:
            if fd_owned:
                try:
                    os.close(fd)
                except OSError:
                    pass
            raise

    def delete(self, ref: str) -> bool:
        target = self._resolve_existing_or_target(ref)
        raw_target = str(target)
        if not os.path.lexists(raw_target) or has_symlink_raw_path(raw_target):
            return False
        try:
            st = os.lstat(raw_target)
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(st.st_mode):
            return False
        removed = _stg_unlink_with_nt_retry(raw_target)
        if removed:
            _stg_prune_empty_parents(target.path.parent, self._root_path.path)
        return removed

    def gc_unreferenced(self, live_refs: frozenset[str]) -> int:
        validated_live = require_typed_frozenset(live_refs, str, "live_refs")
        keep_rel_paths: set[str] = set()
        for raw_ref in validated_live:
            parts = _stg_parse_ref_segments(raw_ref, label="live_refs entry")
            norm_ref = "/".join(parts)
            keep_rel_paths.add(os.path.normcase(norm_ref).replace("\\", "/") if IS_WINDOWS else norm_ref)
            if len(parts) == 1 and _STG_SHA256_HEX_RE.fullmatch(parts[0]) is not None:
                sharded_ref = f"{parts[0][:2]}/{parts[0]}.blob"
                keep_rel_paths.add(os.path.normcase(sharded_ref).replace("\\", "/") if IS_WINDOWS else sharded_ref)

        root_str = str(self._root_path)
        assert_no_symlink_raw_path(root_str)
        removed_count = 0
        candidate_dirs: list[Path] = []
        for cur_dir, entries in walk_nonsymlink_dir_tree(root_str, ignored_dir_prefixes=IGNORED_FS_PREFIXES):
            cur_dir_path = Path(cur_dir)
            if os.path.normcase(cur_dir) != os.path.normcase(root_str):
                candidate_dirs.append(cur_dir_path)
            for ent in entries:
                if _stg_is_transient_blob_name(ent.name) or ent.is_symlink():
                    continue
                try:
                    is_reg = ent.is_file(follow_symlinks=False)
                except OSError:
                    continue
                if not is_reg or has_symlink_raw_path(ent.path):
                    continue
                rel_posix = Path(os.path.relpath(ent.path, root_str)).as_posix()
                cmp_rel = os.path.normcase(rel_posix).replace("\\", "/") if IS_WINDOWS else rel_posix
                if cmp_rel in keep_rel_paths:
                    continue
                if _stg_unlink_with_nt_retry(ent.path):
                    removed_count += 1

        for sub_dir in sorted(candidate_dirs, key=lambda p: len(p.parts), reverse=True):
            _stg_prune_empty_parents(sub_dir, self._root_path.path)
        return removed_count
