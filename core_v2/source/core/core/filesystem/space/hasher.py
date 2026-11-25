"""Deterministic Blake2b-128 file fingerprinting and space Merkle root calculation."""

from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import io
import os
import stat
import struct
import time
from typing import Final, Optional, Sequence

from core.filesystem.fs import has_symlink_raw_path
from core.filesystem.space.rules import HashPolicy
from core.foundation.primitives import IS_WINDOWS, HostPath

SPC_BLAKE2B_DIGEST_SIZE: Final[int] = 16
SPC_ADAPTIVE_THRESHOLD_BYTES: Final[int] = 256 * 1024
SPC_SPARSE_CHUNK_BYTES: Final[int] = 64 * 1024

_NOFOLLOW_OPEN_FLAGS: Final[int] = (
    os.O_RDONLY
    | (os.O_BINARY if IS_WINDOWS else 0)
    | (0 if IS_WINDOWS else os.O_NOFOLLOW | os.O_NONBLOCK)
)


@dataclass(frozen=True, slots=True)
class SpcMerkleItem:
    """Single file digest record participating in space Merkle root computation."""

    rel_path: str
    size_bytes: int
    content_hash: str


def _open_nofollow_regular_reader(raw_path: str) -> Optional[io.BufferedReader]:
    for attempt in range(4):
        if has_symlink_raw_path(raw_path):
            return None
        try:
            fd = os.open(raw_path, _NOFOLLOW_OPEN_FLAGS)
        except PermissionError:
            if IS_WINDOWS and attempt < 3 and not has_symlink_raw_path(raw_path):
                time.sleep(0.005 * (attempt + 1))
                continue
            raise
        except OSError as exc:
            if not IS_WINDOWS and exc.errno in (errno.ELOOP, errno.ENXIO, errno.EOPNOTSUPP, errno.EMLINK):
                return None
            raise
        fd_owned = True
        try:
            f_st = os.fstat(fd)
            if not stat.S_ISREG(f_st.st_mode):
                os.close(fd)
                fd_owned = False
                return None
            if not IS_WINDOWS:
                os.set_blocking(fd, True)
            os.set_inheritable(fd, False)
            raw_io = io.FileIO(fd, "rb", closefd=True)
            fd_owned = False
            reader = io.BufferedReader(raw_io)
        except BaseException:
            if fd_owned:
                try:
                    os.close(fd)
                except OSError:
                    pass
            raise
        if has_symlink_raw_path(raw_path):
            reader.close()
            return None
        return reader
    return None


def _hash_full_blake2b128(raw_path: str) -> Optional[str]:
    reader = _open_nofollow_regular_reader(raw_path)
    if reader is None:
        return None
    hasher = hashlib.blake2b(digest_size=SPC_BLAKE2B_DIGEST_SIZE)
    with reader:
        while True:
            chunk = reader.read(SPC_SPARSE_CHUNK_BYTES)
            if not chunk:
                break
            hasher.update(chunk)
    if IS_WINDOWS and has_symlink_raw_path(raw_path):
        return None
    return hasher.hexdigest()


def _hash_sparse_adaptive_blake2b128(raw_path: str, size_bytes: int) -> Optional[str]:
    reader = _open_nofollow_regular_reader(raw_path)
    if reader is None:
        return None
    hasher = hashlib.blake2b(digest_size=SPC_BLAKE2B_DIGEST_SIZE)
    hasher.update(b"adapt\x00")
    hasher.update(struct.pack("<Q", max(0, size_bytes)))
    chunk_sz = SPC_SPARSE_CHUNK_BYTES
    with reader:
        head_bytes = reader.read(chunk_sz)
        hasher.update(head_bytes)
        mid_offset = max(chunk_sz, (size_bytes // 2) - (chunk_sz // 2))
        reader.seek(mid_offset, os.SEEK_SET)
        hasher.update(reader.read(chunk_sz))
        tail_offset = max(mid_offset + chunk_sz, size_bytes - chunk_sz)
        reader.seek(tail_offset, os.SEEK_SET)
        hasher.update(reader.read(chunk_sz))
    if IS_WINDOWS and has_symlink_raw_path(raw_path):
        return None
    return hasher.hexdigest()


def spc_compute_file_hash(
    file_path: HostPath,
    *,
    size_bytes: int,
    mtime_ns: int,
    policy: HashPolicy,
) -> Optional[str]:
    """Compute deterministic 16-byte Blake2b hex digest according to HashPolicy, or None if symlinked."""
    if policy == HashPolicy.STAT_ONLY:
        if has_symlink_raw_path(str(file_path)):
            return None
        hasher = hashlib.blake2b(digest_size=SPC_BLAKE2B_DIGEST_SIZE)
        hasher.update(b"stat\x00")
        hasher.update(struct.pack("<Qq", max(0, size_bytes), mtime_ns))
        return hasher.hexdigest()

    raw_path = str(file_path)
    if policy == HashPolicy.ADAPTIVE and size_bytes > SPC_ADAPTIVE_THRESHOLD_BYTES:
        return _hash_sparse_adaptive_blake2b128(raw_path, size_bytes)
    return _hash_full_blake2b128(raw_path)


def spc_compute_merkle_root(items: Sequence[SpcMerkleItem]) -> str:
    """Compute deterministic 16-byte Blake2b hex Merkle root over sorted space file records."""
    hasher = hashlib.blake2b(digest_size=SPC_BLAKE2B_DIGEST_SIZE)
    ordered = sorted(items, key=lambda rec: rec.rel_path)
    for rec in ordered:
        payload = f"{rec.rel_path}\x00{rec.size_bytes}\x00{rec.content_hash}\n".encode("utf-8")
        hasher.update(payload)
    return hasher.hexdigest()
