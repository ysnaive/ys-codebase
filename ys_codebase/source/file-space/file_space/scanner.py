"""
BinarySnapshotManager (YFP2), CursorStore, and FingerprintScanner.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple, Union

from .exceptions import FingerprintCorruptedError
from .manager import FileSpaceManager
from .schema import (
    FileFingerprint,
    HashPolicy,
    ScanDiffDetail,
    ScanDiffResult,
    FileSpaceConfig,
)

YFP2_MAGIC = b"YFP2"
YFP2_VERSION = 2
RACY_CLEAN_WINDOW_NS = 10_000_000
SPARSE_SAMPLE_CHUNK_BYTES = 64 * 1024
LAZY_STABILIZATION_SECONDS = 2.0

_WATCHER_STATE_LOCK = threading.Lock()
_ACTIVE_WATCHER_COUNT = 0


def _adjust_active_watcher_count(delta: int) -> None:
    """Increment or decrement the active in-process watcher count."""
    global _ACTIVE_WATCHER_COUNT
    with _WATCHER_STATE_LOCK:
        _ACTIVE_WATCHER_COUNT = max(0, _ACTIVE_WATCHER_COUNT + delta)


def _is_daemon_pid_alive(project_root: Optional[Path]) -> bool:
    """Probe whether a background server/file-space daemon process is alive for project_root."""
    if project_root is None:
        return False
    p_root = Path(project_root)
    candidates = [
        p_root / "ys_codebase" / ".cache" / "server" / "daemon.json",
        p_root / ".cache" / "server" / "daemon.json",
        p_root / "ys_codebase" / ".cache" / "file-space" / "daemon.json",
        p_root / ".cache" / "file-space" / "daemon.json",
    ]
    for status_file in candidates:
        if not status_file.is_file():
            continue
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            pid = int(data.get("pid", 0)) if isinstance(data, dict) else 0
            if pid > 0:
                try:
                    from core.platform import is_process_alive
                    if is_process_alive(pid):
                        return True
                except Exception:
                    os.kill(pid, 0)
                    return True
        except Exception:
            continue
    return False


def is_watcher_active(project_root: Optional[Path] = None) -> bool:
    """Return True if a background file-space watcher process or worker is alive."""
    with _WATCHER_STATE_LOCK:
        if _ACTIVE_WATCHER_COUNT > 0:
            return True
    return _is_daemon_pid_alive(project_root)


def _atomic_write_bytes(target_path: Path, payload: bytes) -> None:
    """Write bytes to a temporary sibling file, fsync, and atomically replace target_path."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target_path.parent),
        prefix=f".{target_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, target_path)
    except Exception:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        raise


def compute_merkle_root(entries: Dict[str, FileFingerprint]) -> str:
    """
    Compute a deterministic Blake2b-160 Merkle root over active (non-deleted) file fingerprints.
    """
    hasher = hashlib.blake2b(digest_size=20)
    active_keys = sorted(
        k for k, fp in entries.items() if not fp.is_deleted
    )
    for key in active_keys:
        fp = entries[key]
        record = f"{fp.path}\0{fp.size}\0{fp.content_hash}\n".encode("utf-8")
        hasher.update(record)
    return hasher.hexdigest()


@dataclass
class SnapshotState:
    """
    In-memory representation of a YFP2 binary snapshot file.
    """

    head_generation: int = 0
    merkle_root: str = ""
    config_hash: str = ""
    entries: Dict[str, FileFingerprint] = field(default_factory=dict)

    @property
    def active_entries(self) -> Dict[str, FileFingerprint]:
        """Return only non-deleted file fingerprints."""
        return {
            path: fp
            for path, fp in self.entries.items()
            if not fp.is_deleted
        }


class BinarySnapshotManager:
    """
    Atomic reader and writer for YFP2 monotonic generation binary snapshots.

    Binary format layout (Little-Endian):
    - Header:
      - 4B Magic: b"YFP2"
      - 2B Version: uint16 (2)
      - 8B head_generation: uint64
      - 4B entry_count: uint32
      - 2B merkle_len: uint16 + merkle_root UTF-8 bytes
      - 2B config_len: uint16 + config_hash UTF-8 bytes
    - Per-Entry Record:
      - 2B path_len: uint16 + path UTF-8 bytes
      - 8B mtime_ns: int64
      - 8B size: uint64
      - 2B hash_len: uint16 + content_hash UTF-8 bytes
      - 2B root_len: uint16 + source_root UTF-8 bytes
      - 8B created_gen: uint64
      - 8B updated_gen: uint64
      - 1B flags: uint8 (bit 0 = is_deleted, bit 1 = pending_stabilization)
    - Footer:
      - 20B Blake2b checksum of the entire preceding byte stream.
    """

    HEADER_PREFIX = struct.Struct("<4sHQI")
    SHORT_LEN = struct.Struct("<H")
    ENTRY_FIXED = struct.Struct("<qqQQB")
    CHECKSUM_SIZE = 20

    def __init__(self, snapshot_path: Optional[Union[str, Path]] = None) -> None:
        self.snapshot_path = Path(snapshot_path) if snapshot_path else None

    def _resolve_target_path(
        self, path: Optional[Union[str, Path]] = None
    ) -> Path:
        target = Path(path) if path is not None else self.snapshot_path
        if target is None:
            raise ValueError("Snapshot path must be specified.")
        return target

    def save_state(
        self,
        state: SnapshotState,
        path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """
        Atomically serialize and write SnapshotState to disk in YFP2 binary format.
        """
        target = self._resolve_target_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        merkle_bytes = state.merkle_root.encode("utf-8")
        config_bytes = state.config_hash.encode("utf-8")
        entries_list = [
            state.entries[k] for k in sorted(state.entries.keys())
        ]

        chunks: List[bytes] = [
            self.HEADER_PREFIX.pack(
                YFP2_MAGIC,
                YFP2_VERSION,
                max(0, int(state.head_generation)),
                len(entries_list),
            ),
            self.SHORT_LEN.pack(len(merkle_bytes)),
            merkle_bytes,
            self.SHORT_LEN.pack(len(config_bytes)),
            config_bytes,
        ]

        for fp in entries_list:
            path_b = fp.path.encode("utf-8")
            hash_b = fp.content_hash.encode("utf-8")
            root_b = fp.source_root.encode("utf-8")
            flags = (1 if fp.is_deleted else 0) | (
                2 if fp.pending_stabilization else 0
            )
            chunks.append(self.SHORT_LEN.pack(len(path_b)))
            chunks.append(path_b)
            chunks.append(self.SHORT_LEN.pack(len(hash_b)))
            chunks.append(hash_b)
            chunks.append(self.SHORT_LEN.pack(len(root_b)))
            chunks.append(root_b)
            chunks.append(
                self.ENTRY_FIXED.pack(
                    int(fp.mtime_ns),
                    max(0, int(fp.size)),
                    max(0, int(fp.created_gen)),
                    max(0, int(fp.updated_gen)),
                    flags,
                )
            )

        body = b"".join(chunks)
        digest = hashlib.blake2b(body, digest_size=self.CHECKSUM_SIZE).digest()
        payload = body + digest
        _atomic_write_bytes(target, payload)
        return target

    def load_state(
        self, path: Optional[Union[str, Path]] = None
    ) -> SnapshotState:
        """
        Read and verify a YFP2 binary snapshot file from disk.
        Raises FingerprintCorruptedError if magic, version, structure, or checksum is invalid.
        """
        target = self._resolve_target_path(path)
        if not target.exists():
            return SnapshotState(
                head_generation=0,
                merkle_root=compute_merkle_root({}),
                config_hash="",
                entries={},
            )

        try:
            raw = target.read_bytes()
        except OSError as exc:
            raise FingerprintCorruptedError(
                f"Failed to read snapshot '{target}': {exc}"
            ) from exc

        min_len = self.HEADER_PREFIX.size + 4 + self.CHECKSUM_SIZE
        if len(raw) < min_len:
            raise FingerprintCorruptedError(
                f"Snapshot '{target}' is truncated ({len(raw)} bytes)."
            )

        body = raw[: -self.CHECKSUM_SIZE]
        expected_digest = raw[-self.CHECKSUM_SIZE :]
        actual_digest = hashlib.blake2b(
            body, digest_size=self.CHECKSUM_SIZE
        ).digest()

        offset = 0
        magic, version, head_gen, entry_count = self.HEADER_PREFIX.unpack_from(
            body, offset
        )
        offset += self.HEADER_PREFIX.size

        if magic != YFP2_MAGIC or version != YFP2_VERSION:
            raise FingerprintCorruptedError(
                f"Invalid YFP2 header in '{target}': magic={magic!r}, version={version}"
            )

        if actual_digest != expected_digest:
            raise FingerprintCorruptedError(
                f"Checksum mismatch in YFP2 snapshot '{target}'."
            )

        try:
            (merkle_len,) = self.SHORT_LEN.unpack_from(body, offset)
            offset += self.SHORT_LEN.size
            merkle_root = body[offset : offset + merkle_len].decode("utf-8")
            offset += merkle_len

            (config_len,) = self.SHORT_LEN.unpack_from(body, offset)
            offset += self.SHORT_LEN.size
            config_hash = body[offset : offset + config_len].decode("utf-8")
            offset += config_len

            entries: Dict[str, FileFingerprint] = {}
            for _ in range(entry_count):
                (path_len,) = self.SHORT_LEN.unpack_from(body, offset)
                offset += self.SHORT_LEN.size
                rel_path = body[offset : offset + path_len].decode("utf-8")
                offset += path_len

                (hash_len,) = self.SHORT_LEN.unpack_from(body, offset)
                offset += self.SHORT_LEN.size
                content_hash = body[offset : offset + hash_len].decode("utf-8")
                offset += hash_len

                (root_len,) = self.SHORT_LEN.unpack_from(body, offset)
                offset += self.SHORT_LEN.size
                source_root = body[offset : offset + root_len].decode("utf-8")
                offset += root_len

                (
                    mtime_ns,
                    size,
                    created_gen,
                    updated_gen,
                    flags,
                ) = self.ENTRY_FIXED.unpack_from(body, offset)
                offset += self.ENTRY_FIXED.size

                entries[rel_path] = FileFingerprint(
                    path=rel_path,
                    mtime_ns=mtime_ns,
                    size=size,
                    content_hash=content_hash,
                    source_root=source_root,
                    created_gen=created_gen,
                    updated_gen=updated_gen,
                    is_deleted=bool(flags & 1),
                    pending_stabilization=bool(flags & 2),
                )

            if offset != len(body):
                raise FingerprintCorruptedError(
                    f"Trailing unparsed bytes in snapshot '{target}'."
                )
        except (struct.error, UnicodeDecodeError) as exc:
            raise FingerprintCorruptedError(
                f"Corrupted record structure in snapshot '{target}': {exc}"
            ) from exc

        return SnapshotState(
            head_generation=head_gen,
            merkle_root=merkle_root,
            config_hash=config_hash,
            entries=entries,
        )


class CursorStore:
    """
    Persistent storage for independent multi-consumer watermark cursors.
    Stored at `<storage_root>/cursors/<consumer_id>.json`.
    """

    def __init__(self, storage_root: Path) -> None:
        self.storage_root = Path(storage_root)
        self.cursors_dir = self.storage_root / "cursors"
        self.cursors_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _sanitize_consumer_id(consumer_id: str) -> str:
        cleaned = "".join(
            ch if (ch.isalnum() or ch in ("-", "_", ".")) else "_"
            for ch in (consumer_id or "default")
        ).strip(".")
        return cleaned or "default"

    def _cursor_file(self, consumer_id: str) -> Path:
        safe_id = self._sanitize_consumer_id(consumer_id)
        return self.cursors_dir / f"{safe_id}.json"

    def load_consumer(self, consumer_id: str = "default") -> Dict[str, Dict[str, Any]]:
        """Load all space cursor states for a given consumer_id."""
        with self._lock:
            c_file = self._cursor_file(consumer_id)
            if not c_file.is_file():
                return {}
            try:
                data = json.loads(c_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
            return {}

    def get_cursor(
        self, space_key: str, consumer_id: str = "default"
    ) -> Dict[str, Any]:
        """Get cursor watermark record for a specific space_key and consumer_id."""
        with self._lock:
            all_spaces = self.load_consumer(consumer_id)
            rec = all_spaces.get(space_key)
            if isinstance(rec, dict):
                return {
                    "acked_gen": int(rec.get("acked_gen", 0)),
                    "merkle_root": str(rec.get("merkle_root", "")),
                    "config_hash": str(rec.get("config_hash", "")),
                    "updated_at": float(rec.get("updated_at", 0.0)),
                }
            return {
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
        """Atomically persist updated cursor watermark for a space_key and consumer_id."""
        with self._lock:
            self.cursors_dir.mkdir(parents=True, exist_ok=True)
            c_file = self._cursor_file(consumer_id)
            all_spaces = self.load_consumer(consumer_id)
            all_spaces[space_key] = {
                "acked_gen": int(acked_gen),
                "merkle_root": str(merkle_root),
                "config_hash": str(config_hash),
                "updated_at": time.time(),
            }
            payload = json.dumps(all_spaces, indent=2, sort_keys=True).encode("utf-8")
            _atomic_write_bytes(c_file, payload)

    def reset_cursor(
        self,
        space_key: Optional[str] = None,
        consumer_id: str = "default",
    ) -> None:
        """Reset cursor watermark for a specific space or entire consumer."""
        with self._lock:
            c_file = self._cursor_file(consumer_id)
            if space_key is None:
                if c_file.exists():
                    try:
                        c_file.unlink()
                    except OSError:
                        pass
                return

            all_spaces = self.load_consumer(consumer_id)
            if space_key in all_spaces:
                del all_spaces[space_key]
                if not all_spaces:
                    if c_file.exists():
                        try:
                            c_file.unlink()
                        except OSError:
                            pass
                else:
                    payload = json.dumps(all_spaces, indent=2, sort_keys=True).encode("utf-8")
                    _atomic_write_bytes(c_file, payload)

    def list_consumers(self) -> List[str]:
        """List all consumer IDs that currently have persisted cursor files."""
        if not self.cursors_dir.is_dir():
            return []
        result: List[str] = []
        for p in sorted(self.cursors_dir.glob("*.json")):
            if not p.name.startswith("."):
                result.append(p.stem)
        return result


class FingerprintScanner:
    """
    Two-stage incremental file fingerprint scanner with four hash policies,
    10ms Racy-Clean guard, YFP2 monotonic generation snapshots, and multi-consumer cursors.
    """

    UNIFIED_KEY = "__all__"

    def __init__(
        self,
        space_manager: Optional[FileSpaceManager] = None,
        storage_root: Optional[Path] = None,
    ) -> None:
        self.space_manager = space_manager or FileSpaceManager(
            storage_root=storage_root
        )
        self.storage_root = (
            Path(storage_root).resolve()
            if storage_root is not None
            else self.space_manager.storage_root
        )
        self.snapshots_dir = self.storage_root / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_mgr = BinarySnapshotManager()
        self.cursor_store = CursorStore(self.storage_root)

    def get_snapshot_path(self, space_name: Optional[str] = None) -> Path:
        """Return the YFP2 snapshot file path for a specific space or unified view."""
        key = space_name if space_name is not None else "unified"
        return self.snapshots_dir / f"{key}.yfp2.bin"

    @staticmethod
    def compute_file_hash(
        file_path: Path,
        size: int,
        mtime_ns: int,
        policy: Union[HashPolicy, str] = HashPolicy.ADAPTIVE,
        large_file_threshold_mb: int = 10,
        background: bool = False,
        now_ns: Optional[int] = None,
    ) -> Tuple[str, bool]:
        """
        Compute content fingerprint according to the space's HashPolicy.
        Returns (content_hash, pending_stabilization).
        """
        hp = (
            policy
            if isinstance(policy, HashPolicy)
            else HashPolicy(str(policy))
        )
        threshold_bytes = max(1, int(large_file_threshold_mb)) * 1024 * 1024

        if hp == HashPolicy.STAT_ONLY:
            return f"stat:{size}:{mtime_ns}", False

        if hp == HashPolicy.LAZY_STABILIZED:
            current_ns = now_ns if now_ns is not None else time.time_ns()
            age_seconds = (current_ns - mtime_ns) / 1_000_000_000.0
            if (
                background
                and size >= threshold_bytes
                and age_seconds < LAZY_STABILIZATION_SECONDS
            ):
                return f"pending:{size}:{mtime_ns}", True
            hp = HashPolicy.ADAPTIVE

        if hp == HashPolicy.ADAPTIVE and size >= threshold_bytes:
            return FingerprintScanner._compute_sparse_sample_hash(
                file_path, size
            ), False

        return FingerprintScanner._compute_full_blake2b(file_path), False

    @staticmethod
    def _compute_full_blake2b(file_path: Path) -> str:
        hasher = hashlib.blake2b(digest_size=20)
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _compute_sparse_sample_hash(file_path: Path, size: int) -> str:
        hasher = hashlib.blake2b(digest_size=20)
        hasher.update(struct.pack("<Q", size))
        chunk_sz = SPARSE_SAMPLE_CHUNK_BYTES

        with open(file_path, "rb") as f:
            if size <= chunk_sz * 3:
                hasher.update(f.read())
            else:
                # 1. First 64KB
                hasher.update(f.read(chunk_sz))
                # 2. Middle 64KB
                mid_offset = max(chunk_sz, (size // 2) - (chunk_sz // 2))
                f.seek(mid_offset, os.SEEK_SET)
                hasher.update(f.read(chunk_sz))
                # 3. Last 64KB
                tail_offset = max(mid_offset + chunk_sz, size - chunk_sz)
                f.seek(tail_offset, os.SEEK_SET)
                hasher.update(f.read(chunk_sz))

        return f"sample2b:{hasher.hexdigest()}"

    def _load_or_recover_state(
        self, space_name: Optional[str]
    ) -> Tuple[SnapshotState, bool]:
        """
        Load existing SnapshotState or recover cleanly if corrupted or missing.
        Returns (state, was_corrupted_or_reset).
        """
        snap_path = self.get_snapshot_path(space_name)
        if not snap_path.exists():
            return (
                SnapshotState(
                    head_generation=0,
                    merkle_root=compute_merkle_root({}),
                    config_hash="",
                    entries={},
                ),
                False,
            )
        try:
            state = self.snapshot_mgr.load_state(snap_path)
            return state, False
        except FingerprintCorruptedError:
            try:
                snap_path.unlink()
            except OSError:
                pass
            return (
                SnapshotState(
                    head_generation=0,
                    merkle_root=compute_merkle_root({}),
                    config_hash="",
                    entries={},
                ),
                True,
            )

    def _prepare_previous_state(
        self,
        space_name: str,
        cfg_hash: str,
        previous_state: Optional[SnapshotState],
        force: bool,
    ) -> SnapshotState:
        if previous_state is None and not force:
            prev_state, corrupted = self._load_or_recover_state(space_name)
            if corrupted or (
                prev_state.config_hash and prev_state.config_hash != cfg_hash
            ):
                return SnapshotState(
                    head_generation=prev_state.head_generation,
                    merkle_root="",
                    config_hash=cfg_hash,
                    entries={},
                )
            return prev_state
        if previous_state is not None and not force:
            return previous_state
        existing_state, _ = self._load_or_recover_state(space_name)
        return SnapshotState(
            head_generation=existing_state.head_generation,
            merkle_root="",
            config_hash=cfg_hash,
            entries={},
        )

    def _evaluate_entry_fingerprint(
        self,
        rel_path: str,
        abs_path: Path,
        src_root: Path,
        cfg: FileSpaceConfig,
        prev_fp: Optional[FileFingerprint],
        next_gen_candidate: int,
        scan_start_ns: int,
        background: bool,
        force: bool,
    ) -> Tuple[Optional[str], Optional[FileFingerprint]]:
        try:
            st = abs_path.stat()
        except OSError:
            return None, None

        mtime_ns = int(st.st_mtime_ns)
        ctime_ns = int(getattr(st, "st_ctime_ns", mtime_ns))
        size = int(st.st_size)
        latest_stat_ns = max(mtime_ns, ctime_ns)
        is_racy = (
            abs(scan_start_ns - mtime_ns) < RACY_CLEAN_WINDOW_NS
            or abs(scan_start_ns - latest_stat_ns) < RACY_CLEAN_WINDOW_NS
            or (prev_fp is not None and ctime_ns > prev_fp.mtime_ns)
        )

        if (
            prev_fp is not None
            and not prev_fp.is_deleted
            and not prev_fp.pending_stabilization
            and not is_racy
            and not force
            and prev_fp.mtime_ns == mtime_ns
            and prev_fp.size == size
        ):
            return "unchanged", None

        try:
            content_hash, pending = self.compute_file_hash(
                file_path=abs_path,
                size=size,
                mtime_ns=mtime_ns,
                policy=cfg.hash_policy,
                large_file_threshold_mb=cfg.large_file_threshold_mb,
                background=background,
                now_ns=scan_start_ns,
            )
        except OSError:
            return None, None

        if prev_fp is None or prev_fp.is_deleted:
            return (
                "added",
                FileFingerprint(
                    path=rel_path,
                    mtime_ns=mtime_ns,
                    size=size,
                    content_hash=content_hash,
                    source_root=src_root.as_posix(),
                    created_gen=next_gen_candidate,
                    updated_gen=next_gen_candidate,
                    is_deleted=False,
                    pending_stabilization=pending,
                ),
            )
        if (
            prev_fp.content_hash != content_hash
            or prev_fp.pending_stabilization != pending
        ):
            return (
                "modified",
                FileFingerprint(
                    path=rel_path,
                    mtime_ns=mtime_ns,
                    size=size,
                    content_hash=content_hash,
                    source_root=src_root.as_posix(),
                    created_gen=prev_fp.created_gen,
                    updated_gen=next_gen_candidate,
                    is_deleted=False,
                    pending_stabilization=pending,
                ),
            )
        return (
            "unchanged",
            FileFingerprint(
                path=rel_path,
                mtime_ns=mtime_ns,
                size=size,
                content_hash=content_hash,
                source_root=src_root.as_posix(),
                created_gen=prev_fp.created_gen,
                updated_gen=prev_fp.updated_gen,
                is_deleted=False,
                pending_stabilization=False,
            ),
        )

    @staticmethod
    def _mark_deleted_entries(
        prev_entries: Dict[str, FileFingerprint],
        seen_paths: Set[str],
        next_gen_candidate: int,
        new_entries: Dict[str, FileFingerprint],
    ) -> Set[str]:
        deleted_set: Set[str] = set()
        for rel_path, prev_fp in prev_entries.items():
            if rel_path not in seen_paths and not prev_fp.is_deleted:
                deleted_set.add(rel_path)
                new_entries[rel_path] = FileFingerprint(
                    path=rel_path,
                    mtime_ns=prev_fp.mtime_ns,
                    size=prev_fp.size,
                    content_hash=prev_fp.content_hash,
                    source_root=prev_fp.source_root,
                    created_gen=prev_fp.created_gen,
                    updated_gen=next_gen_candidate,
                    is_deleted=True,
                    pending_stabilization=False,
                )
        return deleted_set

    def scan_space(
        self,
        space_name: str,
        previous_state: Optional[SnapshotState] = None,
        *,
        background: bool = False,
        force: bool = False,
    ) -> Tuple[SnapshotState, ScanDiffResult]:
        """
        Execute two-stage fingerprint scan on a single workspace and return
        the updated SnapshotState and ScanDiffResult relative to previous_state.
        """
        cfg = self.space_manager.get_space(space_name)
        cfg_hash = self.space_manager.compute_config_hash(space_name)
        prev_state = self._prepare_previous_state(
            space_name, cfg_hash, previous_state, force
        )

        scan_start_ns = time.time_ns()
        prev_entries = prev_state.entries
        next_gen_candidate = prev_state.head_generation + 1

        added_set: Set[str] = set()
        modified_set: Set[str] = set()
        unchanged_set: Set[str] = set()
        new_entries: Dict[str, FileFingerprint] = dict(prev_entries)
        seen_paths: Set[str] = set()

        for rel_path, abs_path, src_root in self.space_manager.iter_space_files(
            space_name
        ):
            seen_paths.add(rel_path)
            status, updated_fp = self._evaluate_entry_fingerprint(
                rel_path=rel_path,
                abs_path=abs_path,
                src_root=src_root,
                cfg=cfg,
                prev_fp=prev_entries.get(rel_path),
                next_gen_candidate=next_gen_candidate,
                scan_start_ns=scan_start_ns,
                background=background,
                force=force,
            )
            if status == "added":
                added_set.add(rel_path)
            elif status == "modified":
                modified_set.add(rel_path)
            elif status == "unchanged":
                unchanged_set.add(rel_path)
            if updated_fp is not None:
                new_entries[rel_path] = updated_fp

        deleted_set = self._mark_deleted_entries(
            prev_entries, seen_paths, next_gen_candidate, new_entries
        )
        has_structural_change = bool(added_set or modified_set or deleted_set)
        final_gen = (
            next_gen_candidate
            if (prev_state.head_generation == 0 or has_structural_change)
            else prev_state.head_generation
        )

        m_root = compute_merkle_root(new_entries)
        new_state = SnapshotState(
            head_generation=final_gen,
            merkle_root=m_root,
            config_hash=cfg_hash,
            entries=new_entries,
        )
        detail = ScanDiffDetail(
            added=added_set,
            modified=modified_set,
            deleted=deleted_set,
            unchanged=unchanged_set,
        )
        diff_res = ScanDiffResult(
            added_count=len(added_set),
            modified_count=len(modified_set),
            deleted_count=len(deleted_set),
            unchanged_count=len(unchanged_set),
            detail=detail,
            from_generation=prev_state.head_generation,
            to_generation=final_gen,
            merkle_root=m_root,
            space_name=space_name,
            space_generations={space_name: final_gen},
        )
        return new_state, diff_res

    def refresh(
        self,
        space_name: Optional[str] = None,
        *,
        background: bool = False,
        force: bool = False,
    ) -> ScanDiffResult:
        """
        Perform incremental fingerprint scan for one space or all registered spaces,
        atomically persist updated YFP2 snapshot(s), and return ScanDiffResult.
        """
        if space_name is not None:
            new_state, diff_res = self.scan_space(
                space_name, background=background, force=force
            )
            self.snapshot_mgr.save_state(
                new_state, self.get_snapshot_path(space_name)
            )
            return diff_res

        all_added: Set[str] = set()
        all_modified: Set[str] = set()
        all_deleted: Set[str] = set()
        all_unchanged: Set[str] = set()
        unified_entries: Dict[str, FileFingerprint] = {}
        space_gens: Dict[str, int] = {}

        prev_unified, _ = self._load_or_recover_state(None)
        any_change = False

        for s_name in self.space_manager.list_spaces():
            s_state, s_diff = self.scan_space(
                s_name, background=background, force=force
            )
            self.snapshot_mgr.save_state(
                s_state, self.get_snapshot_path(s_name)
            )
            space_gens[s_name] = s_state.head_generation
            if s_diff.has_changes:
                any_change = True
            all_added |= s_diff.detail.added
            all_modified |= s_diff.detail.modified
            all_deleted |= s_diff.detail.deleted
            all_unchanged |= s_diff.detail.unchanged
            for rel_p, fp in s_state.entries.items():
                if rel_p not in unified_entries or not fp.is_deleted:
                    unified_entries[rel_p] = fp

        all_unchanged -= all_added | all_modified | all_deleted
        if prev_unified.head_generation == 0 or any_change or force:
            next_unified_gen = prev_unified.head_generation + 1
        else:
            next_unified_gen = prev_unified.head_generation

        unified_merkle = compute_merkle_root(unified_entries)
        unified_cfg_hash = self.space_manager.compute_config_hash(None)
        unified_state = SnapshotState(
            head_generation=next_unified_gen,
            merkle_root=unified_merkle,
            config_hash=unified_cfg_hash,
            entries=unified_entries,
        )
        self.snapshot_mgr.save_state(
            unified_state, self.get_snapshot_path(None)
        )

        detail = ScanDiffDetail(
            added=all_added,
            modified=all_modified,
            deleted=all_deleted,
            unchanged=all_unchanged,
        )
        return ScanDiffResult(
            added_count=len(all_added),
            modified_count=len(all_modified),
            deleted_count=len(all_deleted),
            unchanged_count=len(all_unchanged),
            detail=detail,
            from_generation=prev_unified.head_generation,
            to_generation=next_unified_gen,
            merkle_root=unified_merkle,
            space_name=None,
            space_generations=space_gens,
        )

    def snapshot(
        self, space_name: Optional[str] = None, *, refresh_first: bool = False
    ) -> Dict[str, FileFingerprint]:
        """
        Return the current map of active FileFingerprints for a space or all spaces.
        If no snapshot exists on disk yet, triggers an initial refresh().
        """
        snap_path = self.get_snapshot_path(space_name)
        if refresh_first or not snap_path.exists():
            self.refresh(space_name)
        state, corrupted = self._load_or_recover_state(space_name)
        if corrupted:
            self.refresh(space_name, force=True)
            state, _ = self._load_or_recover_state(space_name)
        return state.active_entries

    def merkle_root(
        self, space_name: Optional[str] = None, *, refresh_first: bool = False
    ) -> str:
        """
        Return the Blake2b-160 Merkle root hex digest of the specified space (or all spaces).
        """
        snap_path = self.get_snapshot_path(space_name)
        if refresh_first or not snap_path.exists():
            self.refresh(space_name)
        state, corrupted = self._load_or_recover_state(space_name)
        if corrupted:
            self.refresh(space_name, force=True)
            state, _ = self._load_or_recover_state(space_name)
        return state.merkle_root

    def diff(
        self,
        space_name: Optional[str] = None,
        consumer_id: str = "default",
        *,
        auto_refresh: bool = True,
    ) -> ScanDiffResult:
        """
        Compute the monotonic generation delta between a consumer's acked_gen watermark
        and the current YFP2 snapshot without advancing the consumer's cursor.
        """
        if auto_refresh or not self.get_snapshot_path(space_name).exists():
            self.refresh(space_name)

        if space_name is None:
            return self._diff_all_spaces(consumer_id, auto_refresh=auto_refresh)

        return self._diff_space(space_name, consumer_id)

    def _diff_space(self, space_name: str, consumer_id: str) -> ScanDiffResult:
        state, corrupted = self._load_or_recover_state(space_name)
        if corrupted:
            self.refresh(space_name, force=True)
            state, _ = self._load_or_recover_state(space_name)

        cfg_hash = self.space_manager.compute_config_hash(space_name)
        cursor = self.cursor_store.get_cursor(space_name, consumer_id)
        acked_gen = cursor["acked_gen"]
        cursor_cfg_hash = cursor["config_hash"]

        if (
            acked_gen > state.head_generation
            or (cursor_cfg_hash and cursor_cfg_hash != cfg_hash)
        ):
            acked_gen = 0

        added_set: Set[str] = set()
        modified_set: Set[str] = set()
        deleted_set: Set[str] = set()
        unchanged_set: Set[str] = set()

        for rel_path, fp in state.entries.items():
            if fp.is_deleted:
                if acked_gen > 0 and fp.created_gen <= acked_gen < fp.updated_gen:
                    deleted_set.add(rel_path)
            else:
                if fp.created_gen > acked_gen:
                    added_set.add(rel_path)
                elif fp.updated_gen > acked_gen:
                    modified_set.add(rel_path)
                else:
                    unchanged_set.add(rel_path)

        detail = ScanDiffDetail(
            added=added_set,
            modified=modified_set,
            deleted=deleted_set,
            unchanged=unchanged_set,
        )
        return ScanDiffResult(
            added_count=len(added_set),
            modified_count=len(modified_set),
            deleted_count=len(deleted_set),
            unchanged_count=len(unchanged_set),
            detail=detail,
            from_generation=acked_gen,
            to_generation=state.head_generation,
            merkle_root=state.merkle_root,
            space_name=space_name,
            space_generations={space_name: state.head_generation},
        )

    def _diff_all_spaces(
        self, consumer_id: str, *, auto_refresh: bool = False
    ) -> ScanDiffResult:
        watcher_active = is_watcher_active(self.space_manager.project_root)
        all_added: Set[str] = set()
        all_modified: Set[str] = set()
        all_deleted: Set[str] = set()
        all_unchanged: Set[str] = set()
        space_gens: Dict[str, int] = {}

        for s_name in self.space_manager.list_spaces():
            s_cfg = self.space_manager.get_space(s_name)
            sub_auto_refresh = False
            if not auto_refresh and watcher_active and s_cfg and not s_cfg.watch:
                sub_auto_refresh = True
            s_diff = self.diff(
                s_name, consumer_id=consumer_id, auto_refresh=sub_auto_refresh
            )
            space_gens[s_name] = s_diff.to_generation
            all_added |= s_diff.detail.added
            all_modified |= s_diff.detail.modified
            all_deleted |= s_diff.detail.deleted
            all_unchanged |= s_diff.detail.unchanged

        all_unchanged -= all_added | all_modified | all_deleted
        unified_state, _ = self._load_or_recover_state(None)
        u_cursor = self.cursor_store.get_cursor(self.UNIFIED_KEY, consumer_id)

        detail = ScanDiffDetail(
            added=all_added,
            modified=all_modified,
            deleted=all_deleted,
            unchanged=all_unchanged,
        )
        return ScanDiffResult(
            added_count=len(all_added),
            modified_count=len(all_modified),
            deleted_count=len(all_deleted),
            unchanged_count=len(all_unchanged),
            detail=detail,
            from_generation=u_cursor["acked_gen"],
            to_generation=unified_state.head_generation,
            merkle_root=unified_state.merkle_root,
            space_name=None,
            space_generations=space_gens,
        )

    def ack(
        self,
        space_name: Optional[str] = None,
        consumer_id: str = "default",
        generation: Optional[int] = None,
        space_generations: Optional[Dict[str, int]] = None,
    ) -> int:
        """
        Advance the consumer's cursor watermark to the target generation (or current head_generation).
        """
        if space_name is not None:
            state, _ = self._load_or_recover_state(space_name)
            target_gen = (
                int(generation)
                if generation is not None
                else (
                    int(space_generations[space_name])
                    if space_generations and space_name in space_generations
                    else state.head_generation
                )
            )
            cfg_hash = self.space_manager.compute_config_hash(space_name)
            self.cursor_store.set_cursor(
                space_key=space_name,
                consumer_id=consumer_id,
                acked_gen=target_gen,
                merkle_root=state.merkle_root,
                config_hash=cfg_hash,
            )
            return target_gen

        for s_name in self.space_manager.list_spaces():
            s_state, _ = self._load_or_recover_state(s_name)
            s_cfg_hash = self.space_manager.compute_config_hash(s_name)
            s_target_gen = (
                int(space_generations[s_name])
                if space_generations and s_name in space_generations
                else s_state.head_generation
            )
            self.cursor_store.set_cursor(
                space_key=s_name,
                consumer_id=consumer_id,
                acked_gen=s_target_gen,
                merkle_root=s_state.merkle_root,
                config_hash=s_cfg_hash,
            )

        u_state, _ = self._load_or_recover_state(None)
        target_u_gen = (
            int(generation)
            if generation is not None
            else u_state.head_generation
        )
        u_cfg_hash = self.space_manager.compute_config_hash(None)
        self.cursor_store.set_cursor(
            space_key=self.UNIFIED_KEY,
            consumer_id=consumer_id,
            acked_gen=target_u_gen,
            merkle_root=u_state.merkle_root,
            config_hash=u_cfg_hash,
        )
        return target_u_gen

    def reset_cursor(
        self,
        space_name: Optional[str] = None,
        consumer_id: str = "default",
    ) -> None:
        """Reset a consumer's watermark cursor to generation 0."""
        self.cursor_store.reset_cursor(
            space_key=space_name, consumer_id=consumer_id
        )

    @contextmanager
    def consume_diff(
        self,
        space_name: Optional[str] = None,
        consumer_id: str = "default",
        *,
        auto_refresh: Optional[bool] = None,
    ) -> Iterator[ScanDiffResult]:
        """
        Exception-safe transactional cursor consumption context manager.
        Automatically advances cursor via ack() upon normal exit; preserves previous cursor if an exception occurs.
        """
        if auto_refresh is None:
            if not is_watcher_active(self.space_manager.project_root):
                auto_refresh = True
            elif space_name is not None:
                s_cfg = self.space_manager.get_space(space_name)
                auto_refresh = bool(s_cfg and not s_cfg.watch)
            else:
                auto_refresh = False
        diff_result = self.diff(
            space_name=space_name,
            consumer_id=consumer_id,
            auto_refresh=auto_refresh,
        )
        yield diff_result
        self.ack(
            space_name=space_name,
            consumer_id=consumer_id,
            generation=diff_result.to_generation,
            space_generations=getattr(diff_result, "space_generations", None),
        )
