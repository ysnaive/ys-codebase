"""
Composite snapshot, two-stage incremental scanner, YFP2 binary persistence,
and multi-consumer transactional watermark cursors for `core.space`.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import struct
import threading
import time
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple, Union

from core import vfs
from core.context import (
    cell_span,
    get_or_compute_cell_state,
    get_runtime_context,
    invalidate_cell_state,
)
from core.platform.lock import InterProcessLock

from .exceptions import SpaceError
from .hasher import (
    BLAKE2B_DIGEST_SIZE,
    FileHashEntry,
    compute_file_hash,
    compute_space_merkle_root,
)
from .registry import (
    SpaceFileEntry,
    SpaceRegistry,
    compute_canonical_rel_path,
    get_default_registry,
    reset_default_registry,
)
from .schema import HashPolicy, resolve_semantic_or_rel_path
from .watcher import (
    get_active_watcher,
    is_watcher_active,
    resolve_watcher_dirty_path,
)

RACY_CLEAN_WINDOW_NS = 10_000_000  # 10 milliseconds


def _sanitize_target_key(key: str) -> str:
    raw = str(key or "").strip()
    if raw.startswith("/"):
        clean_synth = raw.lstrip("/")
        if clean_synth and "/" not in clean_synth:
            return f"synthetic__{clean_synth}"
    clean = raw.strip("/")
    if not clean:
        return "__all__"
    return (
        clean.replace("/", "__")
        .replace("\\", "__")
        .replace(":", "_")
        .replace("*", "_all_")
    )


@dataclass(frozen=True)
class FileFingerprint:
    """Persistent per-file fingerprint record with monotonic generation tracking."""

    rel_path: str
    mtime_ns: int
    ctime_ns: int
    size: int
    content_hash: str
    created_gen: int = 1
    updated_gen: int = 1
    is_deleted: bool = False
    entry_path: str = ""
    _cached_packed_bytes: Optional[bytes] = field(default=None, init=False, repr=False, compare=False)
    _cached_merkle_bytes: Optional[bytes] = field(default=None, init=False, repr=False, compare=False)
    _cached_norm_rel: Optional[str] = field(default=None, init=False, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize FileFingerprint into a dictionary."""
        return {
            "rel_path": self.rel_path,
            "mtime_ns": self.mtime_ns,
            "ctime_ns": self.ctime_ns,
            "size": self.size,
            "content_hash": self.content_hash,
            "created_gen": self.created_gen,
            "updated_gen": self.updated_gen,
            "is_deleted": self.is_deleted,
            "entry_path": self.entry_path,
        }


@dataclass(frozen=True, eq=False)
class ScanDiffDetail:
    """Categorized file relative paths produced by a scan or consumer diff."""

    added: Set[str] = field(default_factory=set, compare=False)
    modified: Set[str] = field(default_factory=set, compare=False)
    deleted: Set[str] = field(default_factory=set, compare=False)
    unchanged: Set[str] = field(default_factory=set, compare=False)

    @property
    def dirty_files(self) -> Set[str]:
        """Return union of added and modified relative paths (excluding deleted)."""
        return self.added | self.modified

    @property
    def has_changes(self) -> bool:
        """Return True if any file was added, modified, or deleted."""
        return bool(self.added or self.modified or self.deleted)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ScanDiffDetail into sorted lists."""
        return {
            "added": sorted(self.added),
            "modified": sorted(self.modified),
            "deleted": sorted(self.deleted),
            "unchanged": sorted(self.unchanged),
        }


@dataclass(frozen=True, eq=False)
class ScanDiffResult:
    """Summary and detailed delta between two generations or a scan pass."""

    added_count: int = 0
    modified_count: int = 0
    deleted_count: int = 0
    unchanged_count: int = 0
    detail: ScanDiffDetail = field(default_factory=ScanDiffDetail, compare=False)
    from_generation: int = 0
    to_generation: int = 0
    merkle_root: str = ""
    space_name: Optional[str] = None
    space_generations: Dict[str, int] = field(default_factory=dict, compare=False)

    @property
    def has_changes(self) -> bool:
        """Return True if any file was added, modified, or deleted."""
        return self.detail.has_changes

    @property
    def added(self) -> List[str]:
        """Return sorted list of added relative paths."""
        return sorted(self.detail.added)

    @property
    def modified(self) -> List[str]:
        """Return sorted list of modified relative paths."""
        return sorted(self.detail.modified)

    @property
    def deleted(self) -> List[str]:
        """Return sorted list of deleted relative paths."""
        return sorted(self.detail.deleted)

    @property
    def unchanged(self) -> List[str]:
        """Return sorted list of unchanged relative paths."""
        return sorted(self.detail.unchanged)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ScanDiffResult into a dictionary."""
        return {
            "space_name": self.space_name or "*",
            "from_generation": self.from_generation,
            "to_generation": self.to_generation,
            "merkle_root": self.merkle_root,
            "added": self.added,
            "modified": self.modified,
            "deleted": self.deleted,
            "added_count": self.added_count,
            "modified_count": self.modified_count,
            "deleted_count": self.deleted_count,
            "unchanged_count": self.unchanged_count,
            "has_changes": self.detail.has_changes,
            "space_generations": dict(self.space_generations),
            "detail": self.detail.to_dict(),
        }


@dataclass(frozen=True, eq=False)
class SnapshotState:
    """Complete snapshot state for a target space query."""

    head_generation: int = 0
    merkle_root: str = ""
    config_hash: str = ""
    entries: Dict[str, FileFingerprint] = field(default_factory=dict, compare=False)

    last_diff: Optional[ScanDiffResult] = field(default=None, compare=False)

    def active_entries(self) -> Dict[str, FileFingerprint]:
        """Return only non-deleted FileFingerprint entries."""
        return {k: v for k, v in self.entries.items() if not v.is_deleted}


def _compute_merkle_from_fingerprints(active_fps: Iterable[FileFingerprint]) -> str:
    hasher = hashlib.blake2b(digest_size=BLAKE2B_DIGEST_SIZE)
    items: List[Tuple[str, bytes]] = []
    for fp in active_fps:
        norm_rel = fp._cached_norm_rel
        if norm_rel is None:
            norm_rel = fp.rel_path.replace("\\", "/")
            object.__setattr__(fp, "_cached_norm_rel", norm_rel)
        m_bytes = fp._cached_merkle_bytes
        if m_bytes is None:
            m_bytes = f"{norm_rel}\0{fp.size}\0{fp.content_hash}\n".encode("utf-8")
            object.__setattr__(fp, "_cached_merkle_bytes", m_bytes)
        items.append((norm_rel, m_bytes))
    items.sort(key=lambda pair: pair[0])
    for _, m_bytes in items:
        hasher.update(m_bytes)
    return hasher.hexdigest()


class BinarySnapshotManager:
    """
    Serializer and loader for the `YFP2` binary snapshot format.
    Uses `core.vfs.write_bytes(..., atomic=True)` and validates a trailing 16-byte Blake2b checksum.
    """

    MAGIC = b"YFP2"
    VERSION = 2
    _HEADER_PREFIX = struct.Struct("<4sIIQHH")
    _ENTRY_PREFIX = struct.Struct("<HHHQQQQQB")

    def save_state(self, state: SnapshotState, path: Union[str, Path]) -> Path:
        """Serialize `state` into `YFP2` binary format and write atomically via `core.vfs`."""
        target_p = Path(str(path))
        target_p.parent.mkdir(parents=True, exist_ok=True)

        merkle_bytes = state.merkle_root.encode("utf-8")
        cfg_bytes = state.config_hash.encode("utf-8")

        sorted_items = sorted(state.entries.values(), key=lambda e: e.rel_path)
        header_buf = self._HEADER_PREFIX.pack(
            self.MAGIC,
            self.VERSION,
            len(sorted_items),
            max(0, int(state.head_generation)),
            len(merkle_bytes),
            len(cfg_bytes),
        )

        chunks: List[bytes] = [header_buf, merkle_bytes, cfg_bytes]
        for fp in sorted_items:
            packed = fp._cached_packed_bytes
            if packed is None:
                rel_b = fp.rel_path.encode("utf-8")
                hash_b = fp.content_hash.encode("utf-8")
                ent_b = fp.entry_path.encode("utf-8")
                rec_head = self._ENTRY_PREFIX.pack(
                    len(rel_b),
                    len(hash_b),
                    len(ent_b),
                    max(0, int(fp.mtime_ns)),
                    max(0, int(fp.ctime_ns)),
                    max(0, int(fp.size)),
                    max(0, int(fp.created_gen)),
                    max(0, int(fp.updated_gen)),
                    1 if fp.is_deleted else 0,
                )
                packed = rec_head + rel_b + hash_b + ent_b
                object.__setattr__(fp, "_cached_packed_bytes", packed)
            chunks.append(packed)

        body = b"".join(chunks)
        checksum = hashlib.blake2b(body, digest_size=BLAKE2B_DIGEST_SIZE).digest()
        vfs.write_bytes(str(target_p), body + checksum, atomic=True)
        return target_p

    def load_summary(self, path: Union[str, Path]) -> Tuple[int, str, str, int]:
        """
        Fast O(N-header-stride) binary summary reader returning
        `(head_generation, merkle_root, config_hash, active_file_count)` without decoding
        per-file strings or allocating `FileFingerprint` objects.
        """
        target_p = Path(str(path))
        if not target_p.is_file():
            return (0, "", "", 0)
        try:
            raw = vfs.read_bytes(str(target_p))
        except Exception:
            return (0, "", "", 0)
        min_len = self._HEADER_PREFIX.size + BLAKE2B_DIGEST_SIZE
        if len(raw) < min_len:
            return (0, "", "", 0)
        body = memoryview(raw)[:-BLAKE2B_DIGEST_SIZE]
        expected_sum = raw[-BLAKE2B_DIGEST_SIZE:]
        if hashlib.blake2b(body, digest_size=BLAKE2B_DIGEST_SIZE).digest() != expected_sum:
            return (0, "", "", 0)
        try:
            magic, ver, count, head_gen, merkle_len, cfg_len = self._HEADER_PREFIX.unpack_from(body, 0)
            if magic != self.MAGIC or ver != self.VERSION:
                return (0, "", "", 0)
            offset = self._HEADER_PREFIX.size
            body_len = len(body)
            if offset + merkle_len + cfg_len > body_len:
                return (0, "", "", 0)
            merkle_root = bytes(body[offset : offset + merkle_len]).decode("utf-8")
            offset += merkle_len
            config_hash = bytes(body[offset : offset + cfg_len]).decode("utf-8")
            offset += cfg_len
            rec_size = self._ENTRY_PREFIX.size
            active_count = 0
            for _ in range(count):
                if offset + rec_size > body_len:
                    return (0, "", "", 0)
                rel_len, hash_len, ent_len = struct.unpack_from("<HHH", body, offset)
                is_del = body[offset + rec_size - 1]
                offset += rec_size + rel_len + hash_len + ent_len
                if offset > body_len:
                    return (0, "", "", 0)
                if not is_del:
                    active_count += 1
            if offset != body_len:
                return (0, "", "", 0)
            return (int(head_gen), merkle_root, config_hash, active_count)
        except Exception:
            return (0, "", "", 0)

    def load_state(self, path: Union[str, Path]) -> SnapshotState:
        """
        Load a `YFP2` binary snapshot from `path`.
        Gracefully falls back to an empty `SnapshotState(head_generation=0)` if missing or corrupted.
        """
        target_p = Path(str(path))
        if not target_p.is_file():
            return SnapshotState()

        try:
            raw = vfs.read_bytes(str(target_p))
        except Exception:
            return SnapshotState()

        min_len = self._HEADER_PREFIX.size + BLAKE2B_DIGEST_SIZE
        if len(raw) < min_len:
            return SnapshotState()

        body = raw[:-BLAKE2B_DIGEST_SIZE]
        expected_sum = raw[-BLAKE2B_DIGEST_SIZE:]
        actual_sum = hashlib.blake2b(body, digest_size=BLAKE2B_DIGEST_SIZE).digest()
        if actual_sum != expected_sum:
            return SnapshotState()

        try:
            magic, ver, count, head_gen, merkle_len, cfg_len = self._HEADER_PREFIX.unpack_from(
                body, 0
            )
            if magic != self.MAGIC or ver != self.VERSION:
                return SnapshotState()

            offset = self._HEADER_PREFIX.size
            if offset + merkle_len + cfg_len > len(body):
                return SnapshotState()
            merkle_root = body[offset : offset + merkle_len].decode("utf-8")
            offset += merkle_len
            config_hash = body[offset : offset + cfg_len].decode("utf-8")
            offset += cfg_len

            entries: Dict[str, FileFingerprint] = {}
            for _ in range(count):
                if offset + self._ENTRY_PREFIX.size > len(body):
                    return SnapshotState()
                (
                    rel_len,
                    hash_len,
                    ent_len,
                    mtime_ns,
                    ctime_ns,
                    size,
                    created_gen,
                    updated_gen,
                    del_flag,
                ) = self._ENTRY_PREFIX.unpack_from(body, offset)
                offset += self._ENTRY_PREFIX.size
                if offset + rel_len + hash_len + ent_len > len(body):
                    return SnapshotState()
                rec_start = offset - self._ENTRY_PREFIX.size
                rel_path = body[offset : offset + rel_len].decode("utf-8")
                offset += rel_len
                content_hash = body[offset : offset + hash_len].decode("utf-8")
                offset += hash_len
                entry_path = body[offset : offset + ent_len].decode("utf-8")
                offset += ent_len

                fp_obj = FileFingerprint(
                    rel_path=rel_path,
                    mtime_ns=int(mtime_ns),
                    ctime_ns=int(ctime_ns),
                    size=int(size),
                    content_hash=content_hash,
                    created_gen=int(created_gen),
                    updated_gen=int(updated_gen),
                    is_deleted=bool(del_flag),
                    entry_path=entry_path,
                )
                object.__setattr__(fp_obj, "_cached_packed_bytes", body[rec_start:offset])
                entries[rel_path] = fp_obj

            if offset != len(body):
                return SnapshotState()

            return SnapshotState(
                head_generation=int(head_gen),
                merkle_root=merkle_root,
                config_hash=config_hash,
                entries=entries,
            )
        except Exception:
            return SnapshotState()


class CursorStore:
    """
    Persistent multi-consumer watermark cursor store at `<storage_root>/cursors/<consumer_id>.json`.
    Protected by `threading.RLock` and `InterProcessLock`.
    """

    def __init__(self, storage_root: Path, lock_dir: Optional[Path] = None) -> None:
        self._storage_root = Path(os.path.abspath(str(storage_root)))
        self._cursors_dir = self._storage_root / "cursors"
        self._lock_dir = (
            Path(os.path.abspath(str(lock_dir)))
            if lock_dir is not None
            else (self._storage_root / "locks")
        )
        self._rlock = threading.RLock()
        self._consumer_locks: Dict[str, threading.RLock] = {}
        self._mem_cache: Dict[str, Tuple[int, int, Dict[str, Dict[str, Any]]]] = {}
        self._batch_depth: Dict[str, int] = {}
        self._batch_dirty: Dict[str, Dict[str, Dict[str, Any]]] = {}

    @property
    def cursors_dir(self) -> Path:
        return self._cursors_dir

    @staticmethod
    def _norm_cid(consumer_id: Any) -> str:
        if isinstance(consumer_id, dict):
            return str(consumer_id.get("id") or next(iter(consumer_id.values()), "default") or "default")
        return str(consumer_id or "default")

    def _get_consumer_lock(self, norm_cid: str) -> threading.RLock:
        # _rlock stays a strict leaf lock for metadata dicts so distinct consumers never block each other.
        with self._rlock:
            lock = self._consumer_locks.get(norm_cid)
            if lock is None:
                lock = threading.RLock()
                self._consumer_locks[norm_cid] = lock
            return lock

    def _consumer_path(self, consumer_id: str) -> Path:
        safe_id = _sanitize_target_key(self._norm_cid(consumer_id))
        return self._cursors_dir / f"{safe_id}.json"

    @contextmanager
    def _locked(self, consumer_id: str) -> Iterator[None]:
        norm_cid = self._norm_cid(consumer_id)
        safe_id = _sanitize_target_key(norm_cid)
        lock_file = self._lock_dir / f"cursor_{safe_id}.lock"
        with self._get_consumer_lock(norm_cid):
            with InterProcessLock(str(lock_file), timeout=5.0, reentrant=True):
                yield

    @contextmanager
    def batch_cursor_updates(self, consumer_id: str = "default") -> Iterator[None]:
        """Coalesce multiple `set_cursor` updates for `consumer_id` into a single atomic JSON write on exit."""
        norm_cid = self._norm_cid(consumer_id)
        with self._locked(norm_cid):
            with self._rlock:
                depth = self._batch_depth.get(norm_cid, 0)
                self._batch_depth[norm_cid] = depth + 1
            try:
                yield
            finally:
                with self._rlock:
                    rem = max(0, self._batch_depth.get(norm_cid, 1) - 1)
                    if rem > 0:
                        self._batch_depth[norm_cid] = rem
                        pending = None
                    else:
                        self._batch_depth.pop(norm_cid, None)
                        pending = self._batch_dirty.pop(norm_cid, None)
                if pending is not None:
                    c_path = self._consumer_path(norm_cid)
                    c_path.parent.mkdir(parents=True, exist_ok=True)
                    payload = {
                        "consumer_id": norm_cid,
                        "spaces": pending,
                    }
                    vfs.write_json(str(c_path), payload, atomic=True)
                    try:
                        st = c_path.stat()
                        snap_cache = (
                            int(st.st_mtime_ns),
                            int(st.st_size),
                            {k: dict(v) for k, v in pending.items() if isinstance(v, dict)},
                        )
                        with self._rlock:
                            self._mem_cache[c_path.as_posix()] = snap_cache
                    except OSError:
                        with self._rlock:
                            self._mem_cache.pop(c_path.as_posix(), None)

    def load_consumer(self, consumer_id: str = "default") -> Dict[str, Dict[str, Any]]:
        """Load all space cursor records for `consumer_id`."""
        norm_cid = self._norm_cid(consumer_id)
        with self._rlock:
            if norm_cid in self._batch_dirty:
                return {
                    k: dict(v)
                    for k, v in self._batch_dirty[norm_cid].items()
                    if isinstance(v, dict)
                }
        c_path = self._consumer_path(norm_cid)
        cache_key = c_path.as_posix()
        try:
            st = c_path.stat()
            mtime_ns = int(st.st_mtime_ns)
            size = int(st.st_size)
        except OSError:
            with self._rlock:
                self._mem_cache.pop(cache_key, None)
            return {}

        with self._rlock:
            cached = self._mem_cache.get(cache_key)
            if cached is not None and cached[0] == mtime_ns and cached[1] == size:
                return {k: dict(v) for k, v in cached[2].items() if isinstance(v, dict)}

        try:
            data = vfs.read_json(str(c_path))
            if isinstance(data, dict) and isinstance(data.get("spaces"), dict):
                spaces = {
                    k: dict(v)
                    for k, v in data["spaces"].items()
                    if isinstance(v, dict)
                }
                with self._rlock:
                    self._mem_cache[cache_key] = (
                        mtime_ns,
                        size,
                        {k: dict(v) for k, v in spaces.items()},
                    )
                return spaces
        except Exception:
            pass
        return {}

    def get_cursor(self, space_key: str, consumer_id: str = "default") -> Dict[str, Any]:
        """Return the cursor record for `(space_key, consumer_id)`, defaulting to generation 0."""
        spaces = self.load_consumer(consumer_id)
        rec = spaces.get(space_key)
        if isinstance(rec, dict):
            acked_val = int(rec.get("acked_generation", rec.get("acked_gen", 0)))
            return {
                "acked_generation": acked_val,
                "acked_gen": acked_val,
                "merkle_root": str(rec.get("merkle_root", "")),
                "config_hash": str(rec.get("config_hash", "")),
                "updated_at": float(rec.get("updated_at", 0.0)),
            }
        return {
            "acked_generation": 0,
            "acked_gen": 0,
            "merkle_root": "",
            "config_hash": "",
            "updated_at": 0.0,
        }

    def set_cursor(
        self,
        space_key: str,
        consumer_id: str,
        acked_gen: int,
        merkle_root: str = "",
        config_hash: str = "",
    ) -> None:
        """Atomically persist the watermark cursor for `(space_key, consumer_id)`."""
        norm_gen = max(0, int(acked_gen))
        norm_merkle = str(merkle_root or "")
        norm_cfg = str(config_hash or "")
        existing = self.load_consumer(consumer_id).get(space_key)
        if (
            isinstance(existing, dict)
            and int(existing.get("acked_generation", existing.get("acked_gen", -1))) == norm_gen
            and str(existing.get("merkle_root", "")) == norm_merkle
            and str(existing.get("config_hash", "")) == norm_cfg
        ):
            return

        with self._locked(consumer_id):
            c_path = self._consumer_path(consumer_id)
            c_path.parent.mkdir(parents=True, exist_ok=True)
            spaces = self.load_consumer(consumer_id)
            rec = spaces.get(space_key)
            if (
                isinstance(rec, dict)
                and int(rec.get("acked_generation", rec.get("acked_gen", -1))) == norm_gen
                and str(rec.get("merkle_root", "")) == norm_merkle
                and str(rec.get("config_hash", "")) == norm_cfg
            ):
                return
            spaces[space_key] = {
                "acked_generation": norm_gen,
                "merkle_root": norm_merkle,
                "config_hash": norm_cfg,
                "updated_at": time.time(),
            }
            norm_cid = self._norm_cid(consumer_id)
            with self._rlock:
                if self._batch_depth.get(norm_cid, 0) > 0:
                    self._batch_dirty[norm_cid] = spaces
                    return
            payload = {
                "consumer_id": norm_cid,
                "spaces": spaces,
            }
            vfs.write_json(str(c_path), payload, atomic=True)
            try:
                st = c_path.stat()
                snap_cache = (
                    int(st.st_mtime_ns),
                    int(st.st_size),
                    {k: dict(v) for k, v in spaces.items() if isinstance(v, dict)},
                )
                with self._rlock:
                    self._mem_cache[c_path.as_posix()] = snap_cache
            except OSError:
                with self._rlock:
                    self._mem_cache.pop(c_path.as_posix(), None)

    def reset_cursor(
        self,
        space_key: Optional[str] = None,
        consumer_id: str = "default",
    ) -> None:
        """Reset cursor for a specific `space_key` or remove the entire consumer cursor file when `space_key` is None."""
        norm_cid = self._norm_cid(consumer_id)
        with self._locked(consumer_id):
            c_path = self._consumer_path(consumer_id)
            cache_key = c_path.as_posix()
            if not c_path.is_file():
                with self._rlock:
                    self._mem_cache.pop(cache_key, None)
                    if space_key is None:
                        self._batch_dirty.pop(norm_cid, None)
                return
            if space_key is None:
                try:
                    vfs.remove(str(c_path))
                except Exception:
                    pass
                with self._rlock:
                    self._mem_cache.pop(cache_key, None)
                    self._batch_dirty.pop(norm_cid, None)
                return
            spaces = self.load_consumer(consumer_id)
            if space_key in spaces:
                del spaces[space_key]
                if spaces:
                    vfs.write_json(
                        str(c_path),
                        {"consumer_id": consumer_id or "default", "spaces": spaces},
                        atomic=True,
                    )
                    try:
                        st = c_path.stat()
                        snap_cache = (
                            int(st.st_mtime_ns),
                            int(st.st_size),
                            {k: dict(v) for k, v in spaces.items() if isinstance(v, dict)},
                        )
                        with self._rlock:
                            self._mem_cache[cache_key] = snap_cache
                    except OSError:
                        with self._rlock:
                            self._mem_cache.pop(cache_key, None)
                else:
                    try:
                        vfs.remove(str(c_path))
                    except Exception:
                        pass
                    with self._rlock:
                        self._mem_cache.pop(cache_key, None)

    def list_consumers(self) -> List[str]:
        """List all persisted consumer IDs on disk."""
        if not self._cursors_dir.is_dir():
            return []
        result: List[str] = []
        try:
            for name in sorted(os.listdir(self._cursors_dir)):
                if name.endswith(".json"):
                    c_path = self._cursors_dir / name
                    try:
                        data = vfs.read_json(str(c_path))
                        cid = str(data.get("consumer_id") or name[:-5])
                    except Exception:
                        cid = name[:-5]
                    if cid not in result:
                        result.append(cid)
        except OSError:
            pass
        return result


class SpaceScanner:
    """
    Composite file-space scanner managing `YFP2` monotonic generation snapshots,
    two-stage incremental hashing, `patch_files`, and multi-consumer watermark cursors.
    """

    UNIFIED_KEY = "__all__"
    MAX_TOMBSTONE_GEN_WINDOW = 64

    def __init__(
        self,
        registry: Optional[SpaceRegistry] = None,
        storage_root: Optional[Union[str, Path]] = None,
        lock_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self._registry = registry or get_default_registry()
        self._explicit_storage_root = storage_root
        self._storage_root = self._resolve_default_storage_root(storage_root)
        self._lock_dir = self._resolve_default_lock_dir(lock_dir)
        self._snapshots_dir = self._storage_root / "snapshots"
        self._snapshot_mgr = BinarySnapshotManager()
        self._cursor_store = CursorStore(self._storage_root, self._lock_dir)
        self._rlock = threading.RLock()
        self._snapshot_mem_cache: Dict[str, Tuple[int, int, bytes, SnapshotState]] = {}
        self._summary_mem_cache: Dict[str, Tuple[int, int, bytes, Tuple[int, str, str, int]]] = {}
        self._hash_memo: Optional[Dict[Tuple[str, int, int, str, int], str]] = None

    @property
    def registry(self) -> SpaceRegistry:
        return self._registry

    @property
    def storage_root(self) -> Path:
        return self._storage_root

    @property
    def snapshots_dir(self) -> Path:
        return self._snapshots_dir

    @property
    def cursor_store(self) -> CursorStore:
        return self._cursor_store

    def _resolve_default_storage_root(
        self, explicit_root: Optional[Union[str, Path]]
    ) -> Path:
        if explicit_root is not None:
            return Path(os.path.normpath(os.path.abspath(str(explicit_root))))
        res = resolve_semantic_or_rel_path(
            "storage.local://core/space",
            self._registry.project_root,
            self._registry.yscb_dir,
        )
        if res is not None:
            return res
        return self._registry.yscb_dir / ".storage.local" / "core" / "space"

    def _resolve_default_lock_dir(
        self, explicit_lock_dir: Optional[Union[str, Path]]
    ) -> Path:
        if explicit_lock_dir is not None:
            return Path(os.path.normpath(os.path.abspath(str(explicit_lock_dir))))
        if self._explicit_storage_root is not None:
            return self._storage_root / "locks"
        res = resolve_semantic_or_rel_path(
            "cache://core/space/locks",
            self._registry.project_root,
            self._registry.yscb_dir,
        )
        if res is not None:
            return res
        return self._registry.yscb_dir / ".cache" / "core" / "space" / "locks"

    def _canonical_space_key(self, space_query: Optional[str]) -> str:
        if space_query is None or str(space_query).strip() in ("", "*", "__all__"):
            return self.UNIFIED_KEY
        q = str(space_query).strip()
        resolved = self._registry.resolve_spaces(q)
        if len(resolved) == 1:
            return resolved[0].qualified_name
        return q

    def _snapshot_path(self, space_key: str) -> Path:
        if space_key == self.UNIFIED_KEY:
            canon_key = self.UNIFIED_KEY
        else:
            canon_key = self._canonical_space_key(space_key)
        safe_name = _sanitize_target_key(canon_key)
        return self._snapshots_dir / f"{safe_name}.yfp2.bin"

    @contextmanager
    def _locked_space(self, space_key: str) -> Iterator[None]:
        safe_name = _sanitize_target_key(space_key)
        lock_file = self._lock_dir / f"snap_{safe_name}.lock"
        with self._rlock:
            with InterProcessLock(str(lock_file), timeout=10.0, reentrant=True):
                yield

    @staticmethod
    def _read_tail_checksum(snap_p: Path, size: int) -> bytes:
        if size < BLAKE2B_DIGEST_SIZE:
            return b""
        with open(snap_p, "rb") as f:
            f.seek(size - BLAKE2B_DIGEST_SIZE)
            return f.read(BLAKE2B_DIGEST_SIZE)

    def _load_snapshot_state(self, space_key: str) -> SnapshotState:
        snap_p = self._snapshot_path(space_key)
        cache_key = snap_p.as_posix()
        try:
            st = snap_p.stat()
            mtime_ns = int(st.st_mtime_ns)
            size = int(st.st_size)
            tail_sig = self._read_tail_checksum(snap_p, size)
        except OSError:
            with self._rlock:
                self._snapshot_mem_cache.pop(cache_key, None)
                self._summary_mem_cache.pop(cache_key, None)
            return SnapshotState()

        with self._rlock:
            cached = self._snapshot_mem_cache.get(cache_key)
            if (
                cached is not None
                and cached[0] == mtime_ns
                and cached[1] == size
                and cached[2] == tail_sig
            ):
                c_state = cached[3]
                return SnapshotState(
                    head_generation=c_state.head_generation,
                    merkle_root=c_state.merkle_root,
                    config_hash=c_state.config_hash,
                    entries=dict(c_state.entries),
                )

        loaded = self._snapshot_mgr.load_state(snap_p)
        if loaded.head_generation > 0 or loaded.entries:
            with self._rlock:
                self._summary_mem_cache[cache_key] = (
                    mtime_ns,
                    size,
                    tail_sig,
                    (
                        int(loaded.head_generation),
                        loaded.merkle_root,
                        loaded.config_hash,
                        sum(1 for e in loaded.entries.values() if not e.is_deleted),
                    ),
                )
                self._snapshot_mem_cache[cache_key] = (
                    mtime_ns,
                    size,
                    tail_sig,
                    SnapshotState(
                        head_generation=loaded.head_generation,
                        merkle_root=loaded.merkle_root,
                        config_hash=loaded.config_hash,
                        entries=dict(loaded.entries),
                    ),
                )
        else:
            with self._rlock:
                self._snapshot_mem_cache.pop(cache_key, None)
                self._summary_mem_cache.pop(cache_key, None)
        return loaded

    def _save_snapshot_state(
        self, space_key: str, state: SnapshotState
    ) -> None:
        snap_p = self._snapshot_mgr.save_state(state, self._snapshot_path(space_key))
        cache_key = snap_p.as_posix()
        try:
            st = snap_p.stat()
            size = int(st.st_size)
            tail_sig = self._read_tail_checksum(snap_p, size)
            with self._rlock:
                self._summary_mem_cache[cache_key] = (
                    int(st.st_mtime_ns),
                    size,
                    tail_sig,
                    (
                        int(state.head_generation),
                        state.merkle_root,
                        state.config_hash,
                        sum(1 for e in state.entries.values() if not e.is_deleted),
                    ),
                )
                self._snapshot_mem_cache[cache_key] = (
                    int(st.st_mtime_ns),
                    size,
                    tail_sig,
                    SnapshotState(
                        head_generation=state.head_generation,
                        merkle_root=state.merkle_root,
                        config_hash=state.config_hash,
                        entries=dict(state.entries),
                    ),
                )
        except OSError:
            with self._rlock:
                self._snapshot_mem_cache.pop(cache_key, None)
                self._summary_mem_cache.pop(cache_key, None)

    def _prune_expired_tombstones(
        self,
        space_key: str,
        entries: Dict[str, FileFingerprint],
        head_gen: int,
    ) -> Dict[str, FileFingerprint]:
        """Evicts historical `is_deleted=True` tombstones that have exceeded the retention window and consumer watermarks."""
        window = max(1, int(self.MAX_TOMBSTONE_GEN_WINDOW))
        if head_gen <= window:
            return entries

        active_watermarks: List[int] = []
        try:
            for cid in self._cursor_store.list_consumers():
                rec = self._cursor_store.get_cursor(space_key, cid)
                acked = int(rec.get("acked_generation", 0))
                if acked > 0:
                    active_watermarks.append(acked)
        except Exception:
            pass

        min_watermark = min(active_watermarks) if active_watermarks else head_gen
        pruned: Dict[str, FileFingerprint] = {}
        for rel_k, fp in entries.items():
            if not fp.is_deleted:
                pruned[rel_k] = fp
                continue
            age = head_gen - fp.updated_gen
            if age > window and (fp.updated_gen <= min_watermark or age > window * 4):
                continue
            pruned[rel_k] = fp
        return pruned

    def _get_cursor_record(
        self, space_key: str, consumer_id: str
    ) -> Dict[str, Any]:
        return self._cursor_store.get_cursor(space_key, consumer_id)

    def _set_cursor_record(
        self,
        space_key: str,
        consumer_id: str,
        acked_gen: int,
        merkle_root: str,
        config_hash: str,
    ) -> None:
        self._cursor_store.set_cursor(
            space_key,
            consumer_id,
            acked_gen=acked_gen,
            merkle_root=merkle_root,
            config_hash=config_hash,
        )

    def _resolve_file_policy(
        self, matched_spaces: Sequence[str], space_map: Dict[str, Any]
    ) -> Tuple[HashPolicy, int]:
        for q_name in matched_spaces:
            s_cfg = space_map.get(q_name)
            if s_cfg is not None:
                return s_cfg.hash_policy, s_cfg.large_file_threshold_mb
        return HashPolicy.ADAPTIVE, 10

    def scan(
        self,
        space_query: Optional[str] = None,
        *,
        force: bool = False,
    ) -> ScanDiffResult:
        """
        Execute a two-stage incremental scan for `space_query` (or all watched spaces if `None`/`*`),
        updating the `YFP2` snapshot only when changes occur or on initial generation 0.
        """
        with cell_span("space.scan"):
            if space_query is None or str(space_query).strip() in ("", "*"):
                space_gens: Dict[str, int] = {}
                batch_memo: Dict[Tuple[str, int, int, str, int], str] = {}
                with self._registry.batch_walk_session():
                    for s_cfg in self._registry.list_spaces(include_synthetic=True):
                        if (
                            not s_cfg.watch
                            or s_cfg.short_name == "gitignore"
                            or (not s_cfg.entries and not s_cfg.compose)
                        ):
                            continue
                        sub_res = self._scan_single_query(s_cfg.qualified_name, force=force, hash_memo=batch_memo)
                        space_gens[s_cfg.qualified_name] = sub_res.to_generation
                    unified_res = self._scan_single_query(None, force=force, hash_memo=batch_memo)
                object.__setattr__(unified_res, "space_generations", space_gens)
                if self.has_watcher_dirty_marker():
                    self.mark_watcher_dirty(False)
                return unified_res

            res = self._scan_single_query(space_query, force=force)
            single_gens: Dict[str, int] = {res.space_name or str(space_query): res.to_generation}
            if res.from_generation != res.to_generation or res.has_changes:
                try:
                    synced_deps = self.sync_dependent_snapshots(res.space_name or str(space_query))
                    for dep_k, dep_res in synced_deps.items():
                        single_gens[dep_k] = dep_res.to_generation
                except Exception:
                    pass
            object.__setattr__(res, "space_generations", single_gens)
            return res

    def refresh(
        self,
        space_query: Optional[str] = None,
        *,
        background: bool = False,
        force: bool = False,
    ) -> ScanDiffResult:
        """Alias for `scan(space_query, force=force)` (retains `background` parameter for compatibility)."""
        _ = background
        return self.scan(space_query, force=force)

    def _scan_single_query(
        self,
        space_query: Optional[str],
        *,
        force: bool = False,
        hash_memo: Optional[Dict[Tuple[str, int, int, str, int], str]] = None,
    ) -> ScanDiffResult:
        space_key = self._canonical_space_key(space_query)
        eff_query = "*" if space_key == self.UNIFIED_KEY else space_query

        with self._locked_space(space_key):
            prev_state = self._load_snapshot_state(space_key)
            curr_cfg_hash = self._registry.compute_config_hash(eff_query)
            config_changed = bool(
                prev_state.head_generation == 0
                or prev_state.config_hash != curr_cfg_hash
                or force
            )

            participating_spaces = self._registry._collect_participating_spaces(eff_query)
            space_map = {s.qualified_name: s for s in participating_spaces}
            walked_files: List[SpaceFileEntry] = self._registry.iter_space_files(eff_query)

            now_ns = time.time_ns()
            next_gen = prev_state.head_generation + 1
            new_entries: Dict[str, FileFingerprint] = {}
            detail = ScanDiffDetail()
            seen_rels: Set[str] = set()

            for wf in walked_files:
                rel_p = wf.rel_path
                seen_rels.add(rel_p)
                prev_fp = prev_state.entries.get(rel_p)
                policy, threshold_mb = self._resolve_file_policy(wf.matched_spaces, space_map)

                # Stage 1: Fast (mtime_ns, size) + Racy-Clean check
                is_racy = (now_ns - wf.mtime_ns) < RACY_CLEAN_WINDOW_NS
                if (
                    not config_changed
                    and prev_fp is not None
                    and not prev_fp.is_deleted
                    and prev_fp.size == wf.size
                    and prev_fp.mtime_ns == wf.mtime_ns
                    and not is_racy
                ):
                    new_entries[rel_p] = FileFingerprint(
                        rel_path=rel_p,
                        mtime_ns=wf.mtime_ns,
                        ctime_ns=wf.ctime_ns,
                        size=wf.size,
                        content_hash=prev_fp.content_hash,
                        created_gen=prev_fp.created_gen,
                        updated_gen=prev_fp.updated_gen,
                        is_deleted=False,
                        entry_path=wf.entry_path.as_posix(),
                    )
                    detail.unchanged.add(rel_p)
                    continue

                # Stage 2: Compute content hash via core.space.hasher (with batch memoization when active)
                memo_key: Optional[Tuple[str, int, int, str, int]] = None
                c_hash: Optional[str] = None
                eff_memo = hash_memo if hash_memo is not None else self._hash_memo
                if eff_memo is not None:
                    memo_key = (
                        wf.abs_path.as_posix(),
                        wf.size,
                        wf.mtime_ns,
                        str(policy.value if hasattr(policy, "value") else policy),
                        int(threshold_mb),
                    )
                    c_hash = eff_memo.get(memo_key)
                if c_hash is None:
                    try:
                        c_hash = compute_file_hash(
                            wf.abs_path,
                            size=wf.size,
                            mtime_ns=wf.mtime_ns,
                            policy=policy,
                            large_file_threshold_mb=threshold_mb,
                        )
                    except OSError:
                        continue
                    if eff_memo is not None and memo_key is not None:
                        eff_memo[memo_key] = c_hash

                if prev_fp is None or prev_fp.is_deleted:
                    detail.added.add(rel_p)
                    new_entries[rel_p] = FileFingerprint(
                        rel_path=rel_p,
                        mtime_ns=wf.mtime_ns,
                        ctime_ns=wf.ctime_ns,
                        size=wf.size,
                        content_hash=c_hash,
                        created_gen=next_gen,
                        updated_gen=next_gen,
                        is_deleted=False,
                        entry_path=wf.entry_path.as_posix(),
                    )
                elif prev_fp.content_hash != c_hash:
                    detail.modified.add(rel_p)
                    new_entries[rel_p] = FileFingerprint(
                        rel_path=rel_p,
                        mtime_ns=wf.mtime_ns,
                        ctime_ns=wf.ctime_ns,
                        size=wf.size,
                        content_hash=c_hash,
                        created_gen=prev_fp.created_gen,
                        updated_gen=next_gen,
                        is_deleted=False,
                        entry_path=wf.entry_path.as_posix(),
                    )
                else:
                    # Touch-only (mtime changed or racy window, but content_hash identical)
                    detail.unchanged.add(rel_p)
                    new_entries[rel_p] = FileFingerprint(
                        rel_path=rel_p,
                        mtime_ns=wf.mtime_ns,
                        ctime_ns=wf.ctime_ns,
                        size=wf.size,
                        content_hash=c_hash,
                        created_gen=prev_fp.created_gen,
                        updated_gen=prev_fp.updated_gen,
                        is_deleted=False,
                        entry_path=wf.entry_path.as_posix(),
                    )

            # Check deleted entries compared to previous snapshot
            for old_rel, old_fp in prev_state.entries.items():
                if old_rel in seen_rels:
                    continue
                if not old_fp.is_deleted:
                    detail.deleted.add(old_rel)
                    new_entries[old_rel] = FileFingerprint(
                        rel_path=old_rel,
                        mtime_ns=old_fp.mtime_ns,
                        ctime_ns=old_fp.ctime_ns,
                        size=old_fp.size,
                        content_hash=old_fp.content_hash,
                        created_gen=old_fp.created_gen,
                        updated_gen=next_gen,
                        is_deleted=True,
                        entry_path=old_fp.entry_path,
                    )
                else:
                    new_entries[old_rel] = old_fp

            active_fps = [fp for fp in new_entries.values() if not fp.is_deleted]
            merkle = _compute_merkle_from_fingerprints(active_fps)

            if prev_state.head_generation == 0 or detail.has_changes or config_changed:
                final_gen = next_gen if (detail.has_changes or prev_state.head_generation == 0 or config_changed) else prev_state.head_generation
                new_entries = self._prune_expired_tombstones(space_key, new_entries, final_gen)
                new_state = SnapshotState(
                    head_generation=final_gen,
                    merkle_root=merkle,
                    config_hash=curr_cfg_hash,
                    entries=new_entries,
                )
                self._save_snapshot_state(space_key, new_state)
            else:
                final_gen = prev_state.head_generation
                if any(
                    new_entries[r].mtime_ns != prev_state.entries[r].mtime_ns
                    for r in detail.unchanged
                    if r in prev_state.entries
                ):
                    new_entries = self._prune_expired_tombstones(space_key, new_entries, final_gen)
                    new_state = SnapshotState(
                        head_generation=final_gen,
                        merkle_root=merkle,
                        config_hash=curr_cfg_hash,
                        entries=new_entries,
                    )
                    self._save_snapshot_state(space_key, new_state)

            return ScanDiffResult(
                added_count=len(detail.added),
                modified_count=len(detail.modified),
                deleted_count=len(detail.deleted),
                unchanged_count=len(detail.unchanged),
                detail=detail,
                from_generation=prev_state.head_generation,
                to_generation=final_gen,
                merkle_root=merkle,
                space_name=space_key,
            )

    def patch_files(
        self,
        space_query: Optional[str],
        dirty_paths: Iterable[Union[str, Path]],
    ) -> SnapshotState:
        """
        Incrementally patch specific dirty file paths into the snapshot for `space_query`
        without a full directory tree walk.
        Handles multi-space unions, composed spaces, and deleted external entry files.
        """
        space_key = self._canonical_space_key(space_query)
        eff_query = "*" if space_key == self.UNIFIED_KEY else space_query

        with self._locked_space(space_key):
            prev_state = self._load_snapshot_state(space_key)
            if prev_state.head_generation == 0:
                scan_res = self._scan_single_query(eff_query)
                st = self._load_snapshot_state(space_key)
                object.__setattr__(st, "last_diff", scan_res)
                return st

            curr_cfg_hash = self._registry.compute_config_hash(eff_query)
            if prev_state.config_hash != curr_cfg_hash:
                scan_res = self._scan_single_query(eff_query, force=True)
                st = self._load_snapshot_state(space_key)
                object.__setattr__(st, "last_diff", scan_res)
                return st

            participating_spaces = self._registry._collect_participating_spaces(eff_query)
            space_map = {s.qualified_name: s for s in participating_spaces}
            all_entry_paths = self._registry.collect_all_entry_paths(eff_query)

            entries = dict(prev_state.entries)
            next_gen = prev_state.head_generation + 1
            any_mutated = False
            detail = ScanDiffDetail()

            for raw_p in dirty_paths:
                raw_str = raw_p.as_posix() if isinstance(raw_p, Path) else str(raw_p).strip()
                if not raw_str:
                    continue
                if "://" in raw_str:
                    cand_abs = resolve_semantic_or_rel_path(
                        raw_str, self._registry.project_root, self._registry.yscb_dir
                    )
                    if cand_abs is None:
                        cand_abs = Path(os.path.normpath(os.path.abspath(raw_str)))
                else:
                    p_obj = Path(raw_str)
                    cand_abs = (
                        Path(os.path.normpath(str(p_obj)))
                        if p_obj.is_absolute()
                        else Path(os.path.normpath(str(self._registry.project_root / p_obj)))
                    )

                try:
                    is_existing_file = cand_abs.is_file()
                except OSError:
                    is_existing_file = False

                if is_existing_file:
                    target_key = "*" if space_key == self.UNIFIED_KEY else space_key
                    if self._registry.is_path_matched_fast(cand_abs, target_key, is_dir=False):
                        matched_entry_abs = self._find_best_entry_for_file(
                            cand_abs, all_entry_paths
                        )
                        rel_p = compute_canonical_rel_path(
                            cand_abs, matched_entry_abs, self._registry.project_root
                        )
                        has_non_default_policy = any(
                            sp_c.hash_policy != HashPolicy.ADAPTIVE
                            or sp_c.large_file_threshold_mb != 10
                            for sp_c in participating_spaces
                        )
                        if has_non_default_policy:
                            matched_sp_names = [
                                sp_c.qualified_name
                                for sp_c in participating_spaces
                                if self._registry.is_path_matched_fast(
                                    cand_abs, sp_c.qualified_name, is_dir=False
                                )
                            ]
                            policy, threshold_mb = self._resolve_file_policy(
                                matched_sp_names, space_map
                            )
                        else:
                            policy, threshold_mb = HashPolicy.ADAPTIVE, 10
                        try:
                            st = cand_abs.stat()
                            f_size = int(st.st_size)
                            f_mtime = max(0, int(st.st_mtime_ns))
                            f_ctime = max(0, int(getattr(st, "st_ctime_ns", f_mtime)))
                            c_hash = compute_file_hash(
                                cand_abs,
                                size=f_size,
                                mtime_ns=f_mtime,
                                policy=policy,
                                large_file_threshold_mb=threshold_mb,
                            )
                        except OSError:
                            continue

                        old_fp = entries.get(rel_p)
                        if old_fp is None or old_fp.is_deleted:
                            entries[rel_p] = FileFingerprint(
                                rel_path=rel_p,
                                mtime_ns=f_mtime,
                                ctime_ns=f_ctime,
                                size=f_size,
                                content_hash=c_hash,
                                created_gen=next_gen,
                                updated_gen=next_gen,
                                is_deleted=False,
                                entry_path=matched_entry_abs.as_posix(),
                            )
                            detail.added.add(rel_p)
                            detail.deleted.discard(rel_p)
                            any_mutated = True
                        elif old_fp.content_hash != c_hash:
                            entries[rel_p] = FileFingerprint(
                                rel_path=rel_p,
                                mtime_ns=f_mtime,
                                ctime_ns=f_ctime,
                                size=f_size,
                                content_hash=c_hash,
                                created_gen=old_fp.created_gen,
                                updated_gen=next_gen,
                                is_deleted=False,
                                entry_path=matched_entry_abs.as_posix(),
                            )
                            if rel_p not in detail.added:
                                detail.modified.add(rel_p)
                            any_mutated = True
                        else:
                            entries[rel_p] = FileFingerprint(
                                rel_path=rel_p,
                                mtime_ns=f_mtime,
                                ctime_ns=f_ctime,
                                size=f_size,
                                content_hash=c_hash,
                                created_gen=old_fp.created_gen,
                                updated_gen=old_fp.updated_gen,
                                is_deleted=False,
                                entry_path=matched_entry_abs.as_posix(),
                            )
                        continue

                # File does not exist or no longer matches space rules -> locate candidate rel_paths to mark deleted
                candidate_rels = self._infer_candidate_rel_paths_for_deletion(
                    cand_abs, raw_str, all_entry_paths, entries
                )
                for c_rel in candidate_rels:
                    old_fp = entries.get(c_rel)
                    if old_fp is not None and not old_fp.is_deleted:
                        entries[c_rel] = FileFingerprint(
                            rel_path=c_rel,
                            mtime_ns=old_fp.mtime_ns,
                            ctime_ns=old_fp.ctime_ns,
                            size=old_fp.size,
                            content_hash=old_fp.content_hash,
                            created_gen=old_fp.created_gen,
                            updated_gen=next_gen,
                            is_deleted=True,
                            entry_path=old_fp.entry_path,
                        )
                        detail.added.discard(c_rel)
                        detail.modified.discard(c_rel)
                        detail.deleted.add(c_rel)
                        any_mutated = True

            if not any_mutated:
                active_count = sum(1 for fp in prev_state.entries.values() if not fp.is_deleted)
                object.__setattr__(
                    prev_state,
                    "last_diff",
                    ScanDiffResult(
                        added_count=0,
                        modified_count=0,
                        deleted_count=0,
                        unchanged_count=active_count,
                        detail=detail,
                        from_generation=prev_state.head_generation,
                        to_generation=prev_state.head_generation,
                        merkle_root=prev_state.merkle_root,
                        space_name=space_key,
                        space_generations={space_key: prev_state.head_generation},
                    ),
                )
                return prev_state

            entries = self._prune_expired_tombstones(space_key, entries, next_gen)
            active_fps = [fp for fp in entries.values() if not fp.is_deleted]
            for fp in active_fps:
                if fp.rel_path not in detail.added and fp.rel_path not in detail.modified:
                    detail.unchanged.add(fp.rel_path)

            merkle = _compute_merkle_from_fingerprints(active_fps)
            diff_res = ScanDiffResult(
                added_count=len(detail.added),
                modified_count=len(detail.modified),
                deleted_count=len(detail.deleted),
                unchanged_count=len(detail.unchanged),
                detail=detail,
                from_generation=prev_state.head_generation,
                to_generation=next_gen,
                merkle_root=merkle,
                space_name=space_key,
                space_generations={space_key: next_gen},
            )
            new_state = SnapshotState(
                head_generation=next_gen,
                merkle_root=merkle,
                config_hash=curr_cfg_hash,
                entries=entries,
                last_diff=diff_res,
            )
            self._save_snapshot_state(space_key, new_state)
            return new_state

    def _find_best_entry_for_file(
        self, file_abs: Path, all_entry_paths: Sequence[Path]
    ) -> Path:
        best: Optional[Path] = None
        best_depth = -1
        for entry_p in all_entry_paths:
            if os.path.normcase(str(file_abs)) == os.path.normcase(str(entry_p)):
                return entry_p
            try:
                rel = file_abs.relative_to(entry_p)
                if not str(rel).startswith("..") and len(entry_p.parts) > best_depth:
                    best = entry_p
                    best_depth = len(entry_p.parts)
            except ValueError:
                continue
        return best if best is not None else self._registry.project_root

    def _infer_candidate_rel_paths_for_deletion(
        self,
        cand_abs: Path,
        raw_str: str,
        all_entry_paths: Sequence[Path],
        existing_entries: Dict[str, FileFingerprint],
    ) -> List[str]:
        candidates: List[str] = []
        norm_raw = raw_str.replace("\\", "/").strip("/")
        if norm_raw in existing_entries:
            candidates.append(norm_raw)

        for entry_p in [self._registry.project_root, *all_entry_paths]:
            rel_c = compute_canonical_rel_path(cand_abs, entry_p, self._registry.project_root)
            if rel_c in existing_entries and rel_c not in candidates:
                candidates.append(rel_c)

        for rel_k, fp in existing_entries.items():
            if fp.is_deleted or not fp.entry_path:
                continue
            ent_p = Path(fp.entry_path)
            rel_c = compute_canonical_rel_path(cand_abs, ent_p, self._registry.project_root)
            if rel_c == rel_k and rel_k not in candidates:
                candidates.append(rel_k)

        return candidates

    def _dirty_marker_path(self) -> Path:
        if self._explicit_storage_root is not None:
            return self._storage_root / ".watcher_dirty"
        return resolve_watcher_dirty_path(
            self._registry.project_root, self._registry.yscb_dir
        )

    def mark_watcher_dirty(self, is_dirty: bool) -> None:
        """Create or remove the `.watcher_dirty` marker file."""
        marker = self._dirty_marker_path()
        try:
            if is_dirty:
                vfs.makedirs(str(marker.parent), exist_ok=True)
                vfs.write_bytes(str(marker), b"1", atomic=True)
            else:
                if marker.exists():
                    vfs.remove(str(marker), missing_ok=True)
        except Exception:
            if not is_dirty and marker.exists():
                try:
                    marker.unlink()
                except OSError:
                    pass
        invalidate_cell_state("core.space.watcher_dirty")

    def has_watcher_dirty_marker(self) -> bool:
        """Return True if `.watcher_dirty` exists on disk."""
        marker = self._dirty_marker_path()
        return bool(
            get_or_compute_cell_state(
                ("core.space.watcher_dirty", os.path.normcase(str(marker))),
                marker.is_file,
            )
        )

    def _flush_in_process_watcher(
        self, space_query: Optional[Union[str, Iterable[str]]] = None
    ) -> bool:
        """
        If an active in-process watcher is running, synchronously flush any pending debounce events.
        Returns True if an active in-process watcher handled the flush without a transaction lock block.
        """
        worker = get_active_watcher()
        if worker is not None:
            is_alive_fn = getattr(worker, "is_alive", None)
            if callable(is_alive_fn) and is_alive_fn():
                is_locked_fn = getattr(worker, "is_transaction_locked", None)
                if callable(is_locked_fn) and is_locked_fn():
                    return False
                flush_fn = getattr(worker, "flush_space_now", None)
                if callable(flush_fn):
                    try:
                        flush_fn(space_query)
                        return True
                    except Exception:
                        pass
        return False

    def _has_existing_snapshot(self, space_key: str) -> bool:
        canon_key = self._canonical_space_key(space_key)
        return self._snapshot_path(canon_key).is_file()

    def sync_dependent_snapshots(
        self,
        changed_qname: str,
        dirty_paths: Optional[Iterable[Union[str, Path]]] = None,
        *,
        exclude_keys: Optional[Iterable[str]] = None,
    ) -> Dict[str, ScanDiffResult]:
        """
        Synchronize existing dependent snapshots when a space `changed_qname` updates:
        - Synthesized short-name union snapshot `/<short_name>` (if distinct from `changed_qname` and already initialized)
        - Any composite parent space that transitively depends on `changed_qname` via `compose` (if already initialized
          and not already scheduled in `exclude_keys`)
        - Unified snapshot `__all__` (if already initialized)
        """
        synced: Dict[str, ScanDiffResult] = {}
        excluded: Set[str] = {str(k).strip() for k in (exclude_keys or ())}
        dirty_list = list(dirty_paths) if dirty_paths is not None else []
        use_patch = 0 < len(dirty_list) <= 200

        candidate_keys: List[str] = []
        if "/" in changed_qname:
            short_name = changed_qname.split("/", 1)[-1]
            synth_key = f"/{short_name}" if short_name else ""
            if (
                synth_key
                and synth_key != changed_qname
                and synth_key not in excluded
            ):
                candidate_keys.append(synth_key)
            if (
                short_name
                and short_name != changed_qname
                and short_name not in excluded
                and short_name not in candidate_keys
            ):
                candidate_keys.append(short_name)

        # Check registered composite spaces that transitively depend on changed_qname
        for s_cfg in self._registry.list_spaces():
            if s_cfg.qualified_name == changed_qname or not s_cfg.compose:
                continue
            try:
                deps = self._registry._collect_all_dependency_spaces(
                    s_cfg.qualified_name
                )
            except Exception:
                continue
            if any(p.qualified_name == changed_qname for p in deps):
                if (
                    s_cfg.qualified_name not in candidate_keys
                    and s_cfg.qualified_name not in excluded
                ):
                    candidate_keys.append(s_cfg.qualified_name)
                if (
                    s_cfg.short_name
                    and s_cfg.short_name != s_cfg.qualified_name
                    and s_cfg.short_name not in candidate_keys
                    and s_cfg.short_name not in excluded
                ):
                    candidate_keys.append(s_cfg.short_name)

        seen_canon: Set[str] = set()
        for dep_key in candidate_keys:
            try:
                canon_dep = self._canonical_space_key(dep_key)
            except Exception:
                continue
            if canon_dep in excluded:
                continue
            if canon_dep in seen_canon:
                if canon_dep in synced:
                    synced[dep_key] = synced[canon_dep]
                continue
            seen_canon.add(canon_dep)
            if not self._has_existing_snapshot(canon_dep):
                continue
            try:
                if use_patch:
                    st = self.patch_files(canon_dep, dirty_list)
                    if st.last_diff is not None:
                        synced[dep_key] = st.last_diff
                        synced[canon_dep] = st.last_diff
                else:
                    res_dep = self._scan_single_query(canon_dep)
                    synced[dep_key] = res_dep
                    synced[canon_dep] = res_dep
            except Exception:
                continue

        # Sync unified "__all__" snapshot if it exists
        if self._has_existing_snapshot(self.UNIFIED_KEY) and self.UNIFIED_KEY not in excluded:
            try:
                if use_patch:
                    st_all = self.patch_files(self.UNIFIED_KEY, dirty_list)
                    if st_all.last_diff is not None:
                        synced[self.UNIFIED_KEY] = st_all.last_diff
                else:
                    synced[self.UNIFIED_KEY] = self._scan_single_query(self.UNIFIED_KEY)
            except Exception:
                pass

        return synced

    def sync_dependent_snapshots_batch(
        self,
        changed_qnames: Iterable[str],
        dirty_paths: Optional[Iterable[Union[str, Path]]] = None,
        *,
        exclude_keys: Optional[Iterable[str]] = None,
    ) -> Dict[str, ScanDiffResult]:
        """
        Batch-synchronize existing dependent snapshots for multiple `changed_qnames`
        in a single pass, ensuring each synthetic short-name space, composite space,
        and `__all__` is patched/scanned at most once per batch.
        """
        qname_list = [str(q).strip() for q in changed_qnames if str(q).strip()]
        if not qname_list:
            return {}
        synced: Dict[str, ScanDiffResult] = {}
        excluded: Set[str] = {str(k).strip() for k in (exclude_keys or ())}
        excluded.update(qname_list)
        dirty_list = list(dirty_paths) if dirty_paths is not None else []
        use_patch = 0 < len(dirty_list) <= 200

        candidate_keys: List[str] = []
        for changed_qname in qname_list:
            if "/" in changed_qname:
                short_name = changed_qname.split("/", 1)[-1]
                synth_key = f"/{short_name}" if short_name else ""
                if (
                    synth_key
                    and synth_key != changed_qname
                    and synth_key not in excluded
                    and synth_key not in candidate_keys
                ):
                    candidate_keys.append(synth_key)
                if (
                    short_name
                    and short_name != changed_qname
                    and short_name not in excluded
                    and short_name not in candidate_keys
                ):
                    candidate_keys.append(short_name)

        qname_set = set(qname_list)
        for s_cfg in self._registry.list_spaces():
            if s_cfg.qualified_name in qname_set or not s_cfg.compose:
                continue
            try:
                deps = self._registry._collect_all_dependency_spaces(
                    s_cfg.qualified_name
                )
            except Exception:
                continue
            if any(p.qualified_name in qname_set for p in deps):
                if (
                    s_cfg.qualified_name not in candidate_keys
                    and s_cfg.qualified_name not in excluded
                ):
                    candidate_keys.append(s_cfg.qualified_name)
                if (
                    s_cfg.short_name
                    and s_cfg.short_name != s_cfg.qualified_name
                    and s_cfg.short_name not in candidate_keys
                    and s_cfg.short_name not in excluded
                ):
                    candidate_keys.append(s_cfg.short_name)

        seen_canon: Set[str] = set()
        for dep_key in candidate_keys:
            try:
                canon_dep = self._canonical_space_key(dep_key)
            except Exception:
                continue
            if canon_dep in excluded:
                continue
            if canon_dep in seen_canon:
                if canon_dep in synced:
                    synced[dep_key] = synced[canon_dep]
                continue
            seen_canon.add(canon_dep)
            if not self._has_existing_snapshot(canon_dep):
                continue
            try:
                if use_patch:
                    st = self.patch_files(canon_dep, dirty_list)
                    if st.last_diff is not None:
                        synced[dep_key] = st.last_diff
                        synced[canon_dep] = st.last_diff
                else:
                    res_dep = self._scan_single_query(canon_dep)
                    synced[dep_key] = res_dep
                    synced[canon_dep] = res_dep
            except Exception:
                continue

        if self._has_existing_snapshot(self.UNIFIED_KEY) and self.UNIFIED_KEY not in excluded:
            try:
                if use_patch:
                    st_all = self.patch_files(self.UNIFIED_KEY, dirty_list)
                    if st_all.last_diff is not None:
                        synced[self.UNIFIED_KEY] = st_all.last_diff
                else:
                    synced[self.UNIFIED_KEY] = self._scan_single_query(self.UNIFIED_KEY)
            except Exception:
                pass

        return synced

    def _resolve_effective_auto_refresh(
        self,
        space_query: Optional[str],
        space_key: str,
        auto_refresh: Optional[bool],
    ) -> bool:
        """
        Resolve effective `auto_refresh` policy for `diff` and `consume_diff`:
        When `auto_refresh` is `None` (default), if using default storage root,
        `.watcher_dirty` is not set, an initialized snapshot exists for `space_key`,
        and the file-space watcher is live, skip redundant directory tree walks (`False`).
        """
        if auto_refresh is not None:
            return bool(auto_refresh)
        if (
            self._explicit_storage_root is None
            and not self.has_watcher_dirty_marker()
            and self._has_existing_snapshot(space_key)
            and is_watcher_active(space_query, registry=self._registry)
        ):
            return False
        return True

    def snapshot(
        self,
        space_query: Optional[str] = None,
        *,
        refresh_first: bool = False,
    ) -> Dict[str, FileFingerprint]:
        """
        Return a dictionary of active `rel_path -> FileFingerprint` for `space_query`.
        Automatically runs an initial scan if no snapshot exists yet or if `refresh_first=True`.
        """
        flushed_in_proc = self._flush_in_process_watcher(space_query)
        space_key = self._canonical_space_key(space_query)
        if refresh_first or (not flushed_in_proc and self.has_watcher_dirty_marker()):
            self.scan(space_query)
        state = self._load_snapshot_state(space_key)
        if state.head_generation == 0 and not refresh_first:
            self.scan(space_query)
            state = self._load_snapshot_state(space_key)
        return state.active_entries()

    def merkle_root(
        self,
        space_query: Optional[str] = None,
        *,
        refresh_first: bool = False,
    ) -> str:
        """Return the 16-byte Blake2b hex `merkle_root` of `space_query` from its snapshot."""
        flushed_in_proc = self._flush_in_process_watcher(space_query)
        space_key = self._canonical_space_key(space_query)
        if refresh_first or (not flushed_in_proc and self.has_watcher_dirty_marker()):
            self.scan(space_query)
        state = self._load_snapshot_state(space_key)
        if state.head_generation == 0 and not refresh_first:
            self.scan(space_query)
            state = self._load_snapshot_state(space_key)
        return state.merkle_root

    def diff(
        self,
        space_query: Optional[str] = None,
        consumer_id: str = "default",
        *,
        auto_refresh: Optional[bool] = None,
    ) -> ScanDiffResult:
        """
        Compute the delta between `consumer_id`'s acknowledged watermark generation
        and the current head generation of `space_query`.
        """
        flushed_in_proc = self._flush_in_process_watcher(space_query)
        space_key = self._canonical_space_key(space_query)
        eff_auto_refresh = self._resolve_effective_auto_refresh(
            space_query, space_key, auto_refresh
        )
        if eff_auto_refresh or (not flushed_in_proc and self.has_watcher_dirty_marker()):
            scan_res = self.scan(space_query)
            space_gens = scan_res.space_generations
        else:
            space_gens = {}

        state = self._load_snapshot_state(space_key)
        if state.head_generation == 0 and not eff_auto_refresh:
            scan_res = self.scan(space_query)
            space_gens = scan_res.space_generations
            state = self._load_snapshot_state(space_key)

        cursor = self._get_cursor_record(space_key, consumer_id)
        orig_from_gen = int(cursor.get("acked_generation", 0))
        cursor_cfg_hash = str(cursor.get("config_hash", ""))
        cfg_changed = bool(cursor_cfg_hash and cursor_cfg_hash != state.config_hash)

        from_gen = orig_from_gen
        if cfg_changed or (from_gen > state.head_generation):
            from_gen = 0

        detail = ScanDiffDetail()
        for rel_p, fp in state.entries.items():
            if fp.is_deleted:
                if (from_gen > 0 and fp.created_gen <= from_gen < fp.updated_gen) or (
                    cfg_changed
                    and orig_from_gen > 0
                    and fp.created_gen <= orig_from_gen < fp.updated_gen
                ):
                    detail.deleted.add(rel_p)
            else:
                if fp.created_gen > from_gen:
                    detail.added.add(rel_p)
                elif fp.updated_gen > from_gen:
                    detail.modified.add(rel_p)
                else:
                    detail.unchanged.add(rel_p)

        if not space_gens:
            space_gens = {space_key: state.head_generation}

        return ScanDiffResult(
            added_count=len(detail.added),
            modified_count=len(detail.modified),
            deleted_count=len(detail.deleted),
            unchanged_count=len(detail.unchanged),
            detail=detail,
            from_generation=from_gen,
            to_generation=state.head_generation,
            merkle_root=state.merkle_root,
            space_name=space_key,
            space_generations=space_gens,
        )

    def ack(
        self,
        space_query: Optional[str] = None,
        consumer_id: str = "default",
        generation: Optional[int] = None,
        space_generations: Optional[Dict[str, int]] = None,
    ) -> int:
        """Advance `consumer_id`'s watermark cursor to `generation` (or current `head_generation`)."""
        space_key = self._canonical_space_key(space_query)
        head_gen, merkle_root, cfg_hash, _active_cnt = self.get_snapshot_summary(space_key)
        target_gen = int(generation) if generation is not None else head_gen

        self._set_cursor_record(
            space_key,
            consumer_id,
            acked_gen=target_gen,
            merkle_root=merkle_root,
            config_hash=cfg_hash,
        )
        if space_generations:
            for sub_key, sub_gen in space_generations.items():
                if sub_key == space_key:
                    continue
                _sub_h, sub_merkle, sub_cfg, _sub_c = self.get_snapshot_summary(sub_key)
                self._set_cursor_record(
                    sub_key,
                    consumer_id,
                    acked_gen=int(sub_gen),
                    merkle_root=sub_merkle,
                    config_hash=sub_cfg,
                )
            if target_gen == 0:
                target_gen = max((int(g) for g in space_generations.values()), default=0)
        return target_gen

    def reset_cursor(
        self,
        space_query: Optional[str] = None,
        consumer_id: str = "default",
    ) -> None:
        """Reset watermark cursor for `(space_query, consumer_id)`."""
        if space_query is None:
            self._cursor_store.reset_cursor(None, consumer_id=consumer_id)
            return
        space_key = self._canonical_space_key(space_query)
        self._cursor_store.reset_cursor(space_key, consumer_id=consumer_id)

    @contextmanager
    def consume_diff(
        self,
        space_query: Optional[str] = None,
        consumer_id: str = "default",
        *,
        auto_refresh: Optional[bool] = None,
    ) -> Iterator[ScanDiffResult]:
        """
        At-Least-Once transactional diff consumption context manager:
        - Yields `ScanDiffResult` on entry.
        - Automatically acknowledges (`ack`) the target generation on normal exit.
        - Preserves the existing watermark cursor if an exception is raised inside the `with` block.
        """
        diff_res = self.diff(
            space_query=space_query,
            consumer_id=consumer_id,
            auto_refresh=auto_refresh,
        )
        yield diff_res
        self.ack(
            space_query=space_query,
            consumer_id=consumer_id,
            generation=diff_res.to_generation,
            space_generations=diff_res.space_generations,
        )

    def get_snapshot_summary(self, target_key: Optional[str] = None) -> Tuple[int, str, str, int]:
        """Return `(head_generation, merkle_root, config_hash, active_file_count)` using memory cache or `load_summary`."""
        snap_file = self._snapshot_path(target_key)
        cache_key = snap_file.as_posix()
        try:
            st = snap_file.stat()
            mtime_ns = int(st.st_mtime_ns)
            size = int(st.st_size)
            tail_sig = self._read_tail_checksum(snap_file, size)
        except OSError:
            with self._rlock:
                self._snapshot_mem_cache.pop(cache_key, None)
                self._summary_mem_cache.pop(cache_key, None)
            return (0, "", "", 0)

        with self._rlock:
            sum_cached = self._summary_mem_cache.get(cache_key)
            if (
                sum_cached is not None
                and sum_cached[0] == mtime_ns
                and sum_cached[1] == size
                and sum_cached[2] == tail_sig
            ):
                return sum_cached[3]
            if sum_cached is not None:
                self._summary_mem_cache.pop(cache_key, None)

        with self._rlock:
            cached = self._snapshot_mem_cache.get(cache_key)
            if (
                cached is not None
                and cached[0] == mtime_ns
                and cached[1] == size
                and cached[2] == tail_sig
            ):
                mem_st = cached[3]
                res_tuple = (
                    int(mem_st.head_generation),
                    mem_st.merkle_root,
                    mem_st.config_hash,
                    sum(1 for e in mem_st.entries.values() if not e.is_deleted),
                )
                self._summary_mem_cache[cache_key] = (mtime_ns, size, tail_sig, res_tuple)
                return res_tuple
            if cached is not None:
                self._snapshot_mem_cache.pop(cache_key, None)

        res_tuple = self._snapshot_mgr.load_summary(snap_file)
        if res_tuple[0] > 0:
            with self._rlock:
                self._summary_mem_cache[cache_key] = (mtime_ns, size, tail_sig, res_tuple)
        return res_tuple

    def status(self, space_query: Optional[str] = None) -> Dict[str, Any]:
        """Return comprehensive health, snapshot generation, Merkle root, and consumer cursor status."""
        target_spaces = self._registry.resolve_spaces(space_query)
        consumers = self._cursor_store.list_consumers()

        spaces_report: List[Dict[str, Any]] = []
        for s_cfg in target_spaces:
            q_name = s_cfg.qualified_name
            is_synth = s_cfg.owner == ""
            head_gen, merkle_root, cfg_hash, active_count = self.get_snapshot_summary(q_name)
            if is_synth and head_gen == 0 and s_cfg.short_name != q_name:
                sh_gen, sh_merkle, sh_cfg, sh_cnt = self.get_snapshot_summary(s_cfg.short_name)
                if sh_gen > 0:
                    head_gen, merkle_root, cfg_hash, active_count = sh_gen, sh_merkle, sh_cfg, sh_cnt
            snap_file = self._snapshot_path(q_name)
            short_snap_file = self._snapshot_path(s_cfg.short_name) if is_synth else None
            cursors_info: Dict[str, Any] = {}
            for cid in consumers:
                c_rec = self._get_cursor_record(q_name, cid)
                if is_synth and c_rec.get("acked_generation", 0) == 0 and s_cfg.short_name != q_name:
                    c_rec = self._get_cursor_record(s_cfg.short_name, cid)
                if c_rec.get("acked_generation", 0) > 0:
                    cursors_info[cid] = c_rec

            s_dict = s_cfg.to_dict(self._registry.project_root)
            s_dict.update(
                {
                    "head_generation": head_gen,
                    "merkle_root": merkle_root,
                    "config_hash": cfg_hash,
                    "active_file_count": active_count,
                    "snapshot_exists": (
                        snap_file.is_file()
                        or (short_snap_file is not None and short_snap_file.is_file())
                    ),
                    "cursors": cursors_info,
                }
            )
            spaces_report.append(s_dict)

        u_gen, u_merkle, _, _ = self.get_snapshot_summary(self.UNIFIED_KEY)
        watcher_active = is_watcher_active(space_query, registry=self._registry)
        return {
            "status": "ok",
            "query": space_query or "*",
            "project_root": self._registry.project_root.as_posix(),
            "storage_root": self._storage_root.as_posix(),
            "watcher_active": watcher_active,
            "watcher_dirty": self.has_watcher_dirty_marker(),
            "unified_generation": u_gen,
            "unified_merkle_root": u_merkle,
            "consumers": consumers,
            "space_count": len(spaces_report),
            "spaces": spaces_report,
        }

    def clean(
        self,
        space_query: Optional[str] = None,
        *,
        consumer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Clean persisted snapshot files and/or consumer watermark cursors:
        - If `consumer_id` is specified, resets that consumer's cursor (for `space_query` or all spaces).
        - If `space_query` is specified (without `consumer_id`), removes that space's snapshot and cursors.
        - If both are `None`, removes all snapshots and cursors under `storage.local://core/space/`.
        """
        removed_snapshots: List[str] = []
        reset_consumers: List[str] = []

        if consumer_id is not None:
            self.reset_cursor(space_query=space_query, consumer_id=consumer_id)
            reset_consumers.append(consumer_id)
            return {
                "status": "ok",
                "space": space_query or "*",
                "consumer": consumer_id,
                "removed_snapshots": removed_snapshots,
                "reset_consumers": reset_consumers,
            }

        if space_query is not None and str(space_query).strip() not in ("", "*"):
            resolved_spaces = self._registry.resolve_spaces(space_query)
            space_key = self._canonical_space_key(space_query)
            with self._locked_space(space_key):
                snap_p = self._snapshot_path(space_key)
                with self._rlock:
                    self._snapshot_mem_cache.pop(snap_p.as_posix(), None)
                    self._summary_mem_cache.pop(snap_p.as_posix(), None)
                if snap_p.is_file():
                    try:
                        vfs.remove(str(snap_p))
                        removed_snapshots.append(snap_p.name)
                    except Exception:
                        pass
            for s_cfg in resolved_spaces:
                for cand_k in (
                    s_cfg.qualified_name,
                    f"/{s_cfg.short_name}",
                    s_cfg.short_name,
                ):
                    with self._locked_space(self._canonical_space_key(cand_k)):
                        sp = self._snapshot_path(cand_k)
                        with self._rlock:
                            self._snapshot_mem_cache.pop(sp.as_posix(), None)
                            self._summary_mem_cache.pop(sp.as_posix(), None)
                        if sp.is_file():
                            try:
                                vfs.remove(str(sp))
                                if sp.name not in removed_snapshots:
                                    removed_snapshots.append(sp.name)
                            except Exception:
                                pass
            # Also invalidate composite parent spaces and unified snapshot that aggregate resolved_spaces
            resolved_qset = {s.qualified_name for s in resolved_spaces}
            dep_keys: List[str] = [self.UNIFIED_KEY]
            for all_cfg in self._registry.list_spaces():
                if all_cfg.qualified_name in resolved_qset or not all_cfg.compose:
                    continue
                try:
                    deps = self._registry._collect_all_dependency_spaces(all_cfg.qualified_name)
                except Exception:
                    continue
                if any(d.qualified_name in resolved_qset for d in deps):
                    dep_keys.append(all_cfg.qualified_name)
                    if all_cfg.short_name and all_cfg.short_name != all_cfg.qualified_name:
                        dep_keys.append(all_cfg.short_name)
            for dep_k in dep_keys:
                canon_dep = self.UNIFIED_KEY if dep_k == self.UNIFIED_KEY else self._canonical_space_key(dep_k)
                with self._locked_space(canon_dep):
                    dep_sp = self._snapshot_path(dep_k)
                    with self._rlock:
                        self._snapshot_mem_cache.pop(dep_sp.as_posix(), None)
                        self._summary_mem_cache.pop(dep_sp.as_posix(), None)
                    if dep_sp.is_file():
                        try:
                            vfs.remove(str(dep_sp))
                            if dep_sp.name not in removed_snapshots:
                                removed_snapshots.append(dep_sp.name)
                        except Exception:
                            pass
            for cid in self._cursor_store.list_consumers():
                self._cursor_store.reset_cursor(space_key, consumer_id=cid)
                self._cursor_store.reset_cursor(self.UNIFIED_KEY, consumer_id=cid)
                for s_cfg in resolved_spaces:
                    self._cursor_store.reset_cursor(s_cfg.qualified_name, consumer_id=cid)
                    self._cursor_store.reset_cursor(f"/{s_cfg.short_name}", consumer_id=cid)
                    self._cursor_store.reset_cursor(s_cfg.short_name, consumer_id=cid)
                reset_consumers.append(cid)
            return {
                "status": "ok",
                "space": space_key,
                "consumer": None,
                "removed_snapshots": removed_snapshots,
                "reset_consumers": reset_consumers,
            }

        # Clean all snapshots and cursors under per-space InterProcessLock protection
        if self._snapshots_dir.is_dir():
            for name in sorted(os.listdir(self._snapshots_dir)):
                p = self._snapshots_dir / name
                if p.is_file():
                    lock_key = name[:-len(".yfp2.bin")] if name.endswith(".yfp2.bin") else name
                    with self._locked_space(lock_key):
                        with self._rlock:
                            self._snapshot_mem_cache.pop(p.as_posix(), None)
                            self._summary_mem_cache.pop(p.as_posix(), None)
                        if p.is_file():
                            try:
                                vfs.remove(str(p))
                                removed_snapshots.append(name)
                            except Exception:
                                pass
        with self._rlock:
            self._snapshot_mem_cache.clear()
            self._summary_mem_cache.clear()
        for cid in self._cursor_store.list_consumers():
            self._cursor_store.reset_cursor(None, consumer_id=cid)
            reset_consumers.append(cid)

        return {
            "status": "ok",
            "space": "*",
            "consumer": None,
            "removed_snapshots": removed_snapshots,
            "reset_consumers": reset_consumers,
        }


# =========================================================================
# Module-level Convenience Facade Functions & Default Shared Instances
# =========================================================================


def get_default_scanner(
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> SpaceScanner:
    """
    Return the process-level shared SpaceScanner instance for `(project_root, yscb_dir, storage_root)`.
    Ensures in-memory ephemeral snapshots and cursors are shared across top-level SDK calls
    and the active in-process Watcher.
    """
    if registry is not None:
        return SpaceScanner(registry=registry, storage_root=storage_root)

    reg = get_default_registry(project_root=project_root, yscb_dir=yscb_dir)
    storage_key = (
        os.path.normcase(os.path.abspath(str(storage_root)))
        if storage_root is not None
        else "__default__"
    )
    key = (
        os.path.normcase(str(reg.project_root)),
        os.path.normcase(str(reg.yscb_dir)),
        storage_key,
    )
    ctx = get_runtime_context()
    with ctx.space_scanners_lock:
        sc = ctx.space_default_scanners.get(key)
        if sc is None:
            sc = SpaceScanner(registry=reg, storage_root=storage_root)
            ctx.space_default_scanners[key] = sc
        return sc


def reset_default_instances() -> None:
    """Clear all cached process-level default SpaceScanner and SpaceRegistry instances."""
    ctx = get_runtime_context()
    with ctx.space_scanners_lock:
        ctx.space_default_scanners.clear()
    reset_default_registry()


def _default_scanner(
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> SpaceScanner:
    if scanner is not None:
        return scanner
    return get_default_scanner(
        registry=registry,
        project_root=project_root,
        yscb_dir=yscb_dir,
        storage_root=storage_root,
    )


def scan(
    space_query: Optional[str] = None,
    *,
    force: bool = False,
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> ScanDiffResult:
    """Convenience primitive to run a two-stage incremental scan."""
    sc = _default_scanner(scanner, registry, project_root, yscb_dir, storage_root)
    return sc.scan(space_query=space_query, force=force)


def refresh(
    space_query: Optional[str] = None,
    *,
    background: bool = False,
    force: bool = False,
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> ScanDiffResult:
    """Convenience alias for `scan`."""
    sc = _default_scanner(scanner, registry, project_root, yscb_dir, storage_root)
    return sc.refresh(space_query=space_query, background=background, force=force)


def patch_files(
    space_query: str,
    dirty_paths: Iterable[Union[str, Path]],
    *,
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> SnapshotState:
    """Convenience primitive to incrementally patch dirty files into a space snapshot."""
    sc = _default_scanner(scanner, registry, project_root, yscb_dir, storage_root)
    return sc.patch_files(space_query, dirty_paths)


def snapshot(
    space_query: Optional[str] = None,
    *,
    refresh_first: bool = False,
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> Dict[str, FileFingerprint]:
    """Convenience primitive to retrieve active `rel_path -> FileFingerprint` snapshot entries."""
    sc = _default_scanner(scanner, registry, project_root, yscb_dir, storage_root)
    return sc.snapshot(space_query=space_query, refresh_first=refresh_first)


def merkle_root(
    space_query: Optional[str] = None,
    *,
    refresh_first: bool = False,
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> str:
    """Convenience primitive to retrieve the 16-byte Blake2b hex Merkle root for a space."""
    sc = _default_scanner(scanner, registry, project_root, yscb_dir, storage_root)
    return sc.merkle_root(space_query=space_query, refresh_first=refresh_first)


def diff(
    space_query: Optional[str] = None,
    consumer_id: str = "default",
    *,
    auto_refresh: Optional[bool] = None,
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> ScanDiffResult:
    """Convenience primitive to compute consumer delta against current snapshot generation."""
    sc = _default_scanner(scanner, registry, project_root, yscb_dir, storage_root)
    return sc.diff(space_query=space_query, consumer_id=consumer_id, auto_refresh=auto_refresh)


def ack(
    space_query: Optional[str] = None,
    consumer_id: str = "default",
    generation: Optional[int] = None,
    space_generations: Optional[Dict[str, int]] = None,
    *,
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> int:
    """Convenience primitive to advance a consumer's watermark cursor."""
    sc = _default_scanner(scanner, registry, project_root, yscb_dir, storage_root)
    return sc.ack(
        space_query=space_query,
        consumer_id=consumer_id,
        generation=generation,
        space_generations=space_generations,
    )


def reset_cursor(
    space_query: Optional[str] = None,
    consumer_id: str = "default",
    *,
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> None:
    """Convenience primitive to reset a consumer's watermark cursor."""
    sc = _default_scanner(scanner, registry, project_root, yscb_dir, storage_root)
    sc.reset_cursor(space_query=space_query, consumer_id=consumer_id)


@contextmanager
def consume_diff(
    space_query: Optional[str] = None,
    consumer_id: str = "default",
    *,
    auto_refresh: Optional[bool] = None,
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> Iterator[ScanDiffResult]:
    """Convenience transactional context manager for At-Least-Once diff consumption."""
    sc = _default_scanner(scanner, registry, project_root, yscb_dir, storage_root)
    with sc.consume_diff(
        space_query=space_query, consumer_id=consumer_id, auto_refresh=auto_refresh
    ) as res:
        yield res


def status(
    space_query: Optional[str] = None,
    *,
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Convenience primitive to inspect space snapshot and cursor status."""
    sc = _default_scanner(scanner, registry, project_root, yscb_dir, storage_root)
    return sc.status(space_query=space_query)


def clean(
    space_query: Optional[str] = None,
    *,
    consumer_id: Optional[str] = None,
    scanner: Optional[SpaceScanner] = None,
    registry: Optional[SpaceRegistry] = None,
    project_root: Optional[Union[str, Path]] = None,
    yscb_dir: Optional[Union[str, Path]] = None,
    storage_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Convenience primitive to clean persisted snapshots and/or consumer cursors."""
    sc = _default_scanner(scanner, registry, project_root, yscb_dir, storage_root)
    return sc.clean(space_query=space_query, consumer_id=consumer_id)


def __getattr__(name: str) -> Any:
    """PEP 562 backward-compatible attribute delegation to active `RuntimeContext`."""
    ctx = get_runtime_context()
    if name == "_DEFAULT_SCANNERS":
        return ctx.space_default_scanners
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
