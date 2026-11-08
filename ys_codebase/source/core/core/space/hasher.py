"""
Pure standard-library file and space fingerprint computation (`stat_only`, `adaptive`, `full_hash`)
and deterministic Blake2b Merkle Root aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import struct
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from .exceptions import SpaceError, SpaceNotFoundError
from .registry import SpaceRegistry, compute_canonical_rel_path, get_default_registry
from .schema import HashPolicy, resolve_semantic_or_rel_path

SPARSE_SAMPLE_CHUNK_BYTES = 64 * 1024
BLAKE2B_DIGEST_SIZE = 16


@dataclass(frozen=True)
class FileHashEntry:
    """Single file fingerprint record computed by `hash_target`."""

    rel_path: str
    abs_path: str
    size: int
    mtime_ns: int
    content_hash: str
    matched_spaces: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize FileHashEntry into a dictionary."""
        return {
            "rel_path": self.rel_path,
            "abs_path": self.abs_path,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "content_hash": self.content_hash,
            "matched_spaces": list(self.matched_spaces),
        }


@dataclass(frozen=True)
class SpaceHashResult:
    """Aggregated result of single-file or space-level fingerprint computation."""

    target: str
    target_type: str  # "file" | "space"
    policy: str
    file_count: int
    merkle_root: str
    files: Tuple[FileHashEntry, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize SpaceHashResult into a dictionary."""
        return {
            "target": self.target,
            "target_type": self.target_type,
            "policy": self.policy,
            "file_count": self.file_count,
            "merkle_root": self.merkle_root,
            "files": [f.to_dict() for f in self.files],
        }


def _normalize_hash_policy(policy: Union[HashPolicy, str]) -> HashPolicy:
    if isinstance(policy, HashPolicy):
        return policy
    try:
        return HashPolicy(str(policy).strip().lower())
    except ValueError as exc:
        raise SpaceError(
            f"Invalid hash_policy '{policy}'. Expected one of: {[p.value for p in HashPolicy]}."
        ) from exc


def _compute_full_blake2b(file_path: Path) -> str:
    hasher = hashlib.blake2b(digest_size=BLAKE2B_DIGEST_SIZE)
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _compute_sparse_sample_blake2b(file_path: Path, size: int) -> str:
    hasher = hashlib.blake2b(digest_size=BLAKE2B_DIGEST_SIZE)
    hasher.update(struct.pack("<Q", max(0, int(size))))
    chunk_sz = SPARSE_SAMPLE_CHUNK_BYTES

    with open(file_path, "rb") as f:
        if size <= chunk_sz * 3:
            hasher.update(f.read())
        else:
            hasher.update(f.read(chunk_sz))
            mid_offset = max(chunk_sz, (size // 2) - (chunk_sz // 2))
            f.seek(mid_offset, os.SEEK_SET)
            hasher.update(f.read(chunk_sz))
            tail_offset = max(mid_offset + chunk_sz, size - chunk_sz)
            f.seek(tail_offset, os.SEEK_SET)
            hasher.update(f.read(chunk_sz))

    return f"sample2b:{hasher.hexdigest()}"


def compute_file_hash(
    file_path: Union[str, Path],
    size: Optional[int] = None,
    mtime_ns: Optional[int] = None,
    policy: Union[HashPolicy, str] = HashPolicy.ADAPTIVE,
    large_file_threshold_mb: int = 10,
) -> str:
    """
    Compute content fingerprint for a single file according to `policy`:
    - `stat_only`: deterministic `stat:<size>:<mtime_ns>`
    - `full_hash`: full-file Blake2b 16-byte hex digest
    - `adaptive` (and `lazy_stabilized` in atomic synchronous mode): full Blake2b below
      `large_file_threshold_mb`, or head/middle/tail sparse-sample Blake2b for large files.
    """
    hp = _normalize_hash_policy(policy)
    p = Path(file_path)

    if size is None or mtime_ns is None:
        st = p.stat()
        eff_size = int(st.st_size) if size is None else int(size)
        eff_mtime_ns = int(st.st_mtime_ns) if mtime_ns is None else int(mtime_ns)
    else:
        eff_size = int(size)
        eff_mtime_ns = int(mtime_ns)

    if hp == HashPolicy.STAT_ONLY:
        return f"stat:{eff_size}:{eff_mtime_ns}"

    threshold_bytes = max(1, int(large_file_threshold_mb)) * 1024 * 1024
    if hp in (HashPolicy.ADAPTIVE, HashPolicy.LAZY_STABILIZED) and eff_size >= threshold_bytes:
        return _compute_sparse_sample_blake2b(p, eff_size)

    return _compute_full_blake2b(p)


def compute_space_merkle_root(entries: Sequence[FileHashEntry]) -> str:
    """
    Compute a deterministic Blake2b 16-byte hex digest Merkle Root over sorted file entries.
    Uses POSIX normalized `rel_path`, `size`, and `content_hash` so cross-platform results match 100%.
    """
    hasher = hashlib.blake2b(digest_size=BLAKE2B_DIGEST_SIZE)
    sorted_entries = sorted(entries, key=lambda e: e.rel_path.replace("\\", "/"))
    for entry in sorted_entries:
        norm_rel = entry.rel_path.replace("\\", "/")
        record = f"{norm_rel}\0{entry.size}\0{entry.content_hash}\n".encode("utf-8")
        hasher.update(record)
    return hasher.hexdigest()


def hash_target(
    registry: SpaceRegistry,
    target: Optional[str] = None,
    *,
    policy: Optional[Union[HashPolicy, str]] = None,
) -> SpaceHashResult:
    """
    Compute atomic fingerprints and deterministic `merkle_root` for either:
    1. A registered space (`<owner>/<space>`, `<space>`, or `None` for all spaces), or
    2. A single physical file path or semantic URI if `target` resolves to an existing file on disk
       and does not match a registered space name.
    Never writes or mutates any persistent snapshot files on disk.
    """
    explicit_policy = _normalize_hash_policy(policy) if policy is not None else None

    if target is not None and str(target).strip():
        raw_t = str(target).strip()
        # First check if raw_t is a registered space
        try:
            matched_spaces = registry.resolve_spaces(raw_t)
        except SpaceNotFoundError:
            matched_spaces = []

        if not matched_spaces:
            # Check if raw_t is an existing file path or semantic URI
            cand_path = resolve_semantic_or_rel_path(
                raw_t, registry.project_root, registry.yscb_dir
            )
            if cand_path is not None and cand_path.is_file():
                eff_pol = explicit_policy or HashPolicy.ADAPTIVE
                st = cand_path.stat()
                f_size = int(st.st_size)
                f_mtime = int(st.st_mtime_ns)
                c_hash = compute_file_hash(
                    cand_path,
                    size=f_size,
                    mtime_ns=f_mtime,
                    policy=eff_pol,
                )
                rel_p = compute_canonical_rel_path(
                    cand_path, cand_path.parent, registry.project_root
                )
                entry = FileHashEntry(
                    rel_path=rel_p,
                    abs_path=cand_path.as_posix(),
                    size=f_size,
                    mtime_ns=f_mtime,
                    content_hash=c_hash,
                    matched_spaces=(),
                )
                merkle = compute_space_merkle_root((entry,))
                return SpaceHashResult(
                    target=raw_t,
                    target_type="file",
                    policy=eff_pol.value,
                    file_count=1,
                    merkle_root=merkle,
                    files=(entry,),
                )
            # Neither a registered space nor an existing file -> raise SpaceNotFoundError
            registry.resolve_spaces(raw_t)
    else:
        matched_spaces = registry.resolve_spaces(None)

    space_map = {s.qualified_name: s for s in matched_spaces}
    walked_files = registry.iter_space_files(target)

    # Determine effective policy label for report
    if explicit_policy is not None:
        report_policy = explicit_policy.value
    elif len(matched_spaces) == 1:
        report_policy = matched_spaces[0].hash_policy.value
    else:
        policies = {s.hash_policy.value for s in matched_spaces}
        report_policy = policies.pop() if len(policies) == 1 else HashPolicy.ADAPTIVE.value

    hash_entries: list[FileHashEntry] = []
    for wf in walked_files:
        if explicit_policy is not None:
            file_policy = explicit_policy
            threshold_mb = 10
            if wf.matched_spaces and wf.matched_spaces[0] in space_map:
                threshold_mb = space_map[wf.matched_spaces[0]].large_file_threshold_mb
        elif wf.matched_spaces and wf.matched_spaces[0] in space_map:
            primary_space = space_map[wf.matched_spaces[0]]
            file_policy = primary_space.hash_policy
            threshold_mb = primary_space.large_file_threshold_mb
        else:
            file_policy = HashPolicy.ADAPTIVE
            threshold_mb = 10

        try:
            c_hash = compute_file_hash(
                wf.abs_path,
                size=wf.size,
                mtime_ns=wf.mtime_ns,
                policy=file_policy,
                large_file_threshold_mb=threshold_mb,
            )
        except OSError:
            continue

        hash_entries.append(
            FileHashEntry(
                rel_path=wf.rel_path,
                abs_path=wf.abs_path.as_posix(),
                size=wf.size,
                mtime_ns=wf.mtime_ns,
                content_hash=c_hash,
                matched_spaces=wf.matched_spaces,
            )
        )

    merkle = compute_space_merkle_root(hash_entries)
    return SpaceHashResult(
        target=str(target) if target else "*",
        target_type="space",
        policy=report_policy,
        file_count=len(hash_entries),
        merkle_root=merkle,
        files=tuple(hash_entries),
    )


def hash_space_or_path(
    target: Optional[str] = None,
    *,
    policy: Optional[Union[HashPolicy, str]] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
) -> SpaceHashResult:
    """Convenience atomic primitive for hashing a space or single file path."""
    reg = registry or get_default_registry(project_root=project_root, yscb_dir=yscb_dir)
    return hash_target(reg, target=target, policy=policy)
