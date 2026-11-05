"""
BinarySnapshotManager (YFP2), CursorStore, and FingerprintScanner.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import stat as stat_mod
import struct
import sys
import tempfile
import threading
import time
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple, Union
import weakref

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
_ACTIVE_WATCHER_WORKERS: List[Any] = []


def _adjust_active_watcher_count(delta: int, worker: Optional[Any] = None) -> None:
    """Increment or decrement the active in-process watcher count and track active workers."""
    global _ACTIVE_WATCHER_COUNT
    with _WATCHER_STATE_LOCK:
        _ACTIVE_WATCHER_COUNT = max(0, _ACTIVE_WATCHER_COUNT + delta)
        if worker is not None:
            if delta > 0:
                _ACTIVE_WATCHER_WORKERS.append(weakref.ref(worker))
            elif delta < 0:
                _ACTIVE_WATCHER_WORKERS[:] = [
                    ref for ref in _ACTIVE_WATCHER_WORKERS
                    if ref() is not None and ref() is not worker
                ]


def _flush_in_process_watcher(
    project_root: Optional[Path], space_name: Optional[str] = None
) -> None:
    """If an in-process watcher worker has pending dirty paths for space_name, flush it synchronously."""
    with _WATCHER_STATE_LOCK:
        refs = list(_ACTIVE_WATCHER_WORKERS)
    for ref in refs:
        worker = ref()
        if worker is None:
            continue
        try:
            if project_root is not None:
                w_root = getattr(getattr(worker, "space_manager", None), "project_root", None)
                if w_root is not None and Path(w_root).resolve() != Path(project_root).resolve():
                    continue
            if space_name is not None and hasattr(worker, "flush_space_now"):
                worker.flush_space_now(space_name)
            elif space_name is None and hasattr(worker, "flush_dirty_spaces"):
                worker.flush_dirty_spaces(force=True)
        except Exception:
            continue


def _check_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        from core.platform import is_process_alive

        return bool(is_process_alive(pid))
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


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
            if _check_pid_alive(pid):
                return True
        except Exception:
            continue
    return False


def _read_watcher_state_file(project_root: Optional[Path]) -> Optional[Dict[str, Any]]:
    if project_root is None:
        return None
    p_root = Path(project_root)
    candidates = [
        p_root / "ys_codebase" / ".cache" / "file-space" / "watcher_state.json",
        p_root / ".cache" / "file-space" / "watcher_state.json",
    ]
    for cand in candidates:
        if cand.is_file():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
    return None


def is_watcher_active(
    project_root: Optional[Path] = None,
    space_name: Optional[str] = None,
    *,
    space_manager: Optional[FileSpaceManager] = None,
) -> bool:
    """
    Return True if a background file-space watcher process or worker is actively watching
    the workspace (and the specified space_name has watch=True).
    """
    svc_mod = sys.modules.get("file_space.service")
    if svc_mod is not None:
        svc_fn = getattr(svc_mod, "is_watcher_active", None)
        if svc_fn is not None and svc_fn is not is_watcher_active:
            try:
                base_active = bool(svc_fn(project_root))
            except TypeError:
                base_active = bool(svc_fn())
            if not base_active:
                return False
            if space_name is not None and space_manager is not None:
                try:
                    return bool(space_manager.get_space(space_name).watch)
                except Exception:
                    return True
            return True

    state_data = _read_watcher_state_file(project_root)
    if state_data is not None:
        if not bool(state_data.get("watchdog_running", False)):
            return False
        pid = int(state_data.get("pid", 0))
        if pid > 0 and not _check_pid_alive(pid):
            return False
        watched_list = state_data.get("watched_spaces")
        if space_name is not None and isinstance(watched_list, list):
            if space_name not in watched_list:
                return False

    with _WATCHER_STATE_LOCK:
        in_proc_active = _ACTIVE_WATCHER_COUNT > 0
        active_refs = list(_ACTIVE_WATCHER_WORKERS)

    daemon_alive = in_proc_active or _is_daemon_pid_alive(project_root) or (
        state_data is not None and bool(state_data.get("watchdog_running", False))
    )
    if not daemon_alive:
        return False

    if space_name is not None:
        if space_manager is not None:
            try:
                return bool(space_manager.get_space(space_name).watch)
            except Exception:
                pass
        for ref in active_refs:
            w = ref()
            w_mgr = getattr(w, "space_manager", None) if w is not None else None
            if w_mgr is not None:
                try:
                    return bool(w_mgr.get_space(space_name).watch)
                except Exception:
                    continue
        if project_root is not None:
            try:
                mgr = FileSpaceManager(project_root=Path(project_root))
                return bool(mgr.get_space(space_name).watch)
            except Exception:
                pass

    return True


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
        max_retries = 5
        for attempt in range(max_retries):
            try:
                os.replace(tmp_name, target_path)
                break
            except PermissionError:
                if attempt >= max_retries - 1:
                    raise
                time.sleep(0.01 * (2**attempt))
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
    last_diff: Optional[ScanDiffResult] = field(
        default=None, repr=False, compare=False
    )

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

    @contextmanager
    def _cursor_lock(self, consumer_id: str) -> Iterator[None]:
        """Acquire both thread-level RLock and cross-process InterProcessLock for a consumer cursor."""
        with self._lock:
            self.cursors_dir.mkdir(parents=True, exist_ok=True)
            safe_id = self._sanitize_consumer_id(consumer_id)
            lock_path = self.cursors_dir / f".{safe_id}.lock"
            ip_lock = None
            try:
                from core.platform.lock import InterProcessLock

                ip_lock = InterProcessLock(str(lock_path), timeout=5.0)
                ip_lock.acquire(blocking=True, timeout_sec=5.0)
            except Exception:
                ip_lock = None
            try:
                yield
            finally:
                if ip_lock is not None:
                    try:
                        ip_lock.release()
                    except Exception:
                        pass

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
        with self._cursor_lock(consumer_id):
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
        with self._cursor_lock(consumer_id):
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

    def get_watcher_dirty_beacon_path(self) -> Path:
        """Return the cross-process dirty beacon file path in the snapshots directory."""
        return self.snapshots_dir / ".watcher_dirty"

    def mark_watcher_dirty(self, dirty: bool = True) -> None:
        """Create or remove the cross-process `.watcher_dirty` beacon file."""
        beacon = self.get_watcher_dirty_beacon_path()
        try:
            if dirty:
                beacon.parent.mkdir(parents=True, exist_ok=True)
                beacon.write_bytes(b"1")
            elif beacon.exists():
                beacon.unlink()
        except OSError:
            pass

    def is_watcher_dirty(self, space_name: Optional[str] = None) -> bool:
        """Return True if an active watcher has pending un-flushed changes on disk or in-process."""
        beacon = self.get_watcher_dirty_beacon_path()
        if beacon.exists():
            return True
        with _WATCHER_STATE_LOCK:
            refs = list(_ACTIVE_WATCHER_WORKERS)
        for ref in refs:
            worker = ref()
            if worker is None:
                continue
            try:
                w_root = getattr(getattr(worker, "space_manager", None), "project_root", None)
                if w_root is not None and Path(w_root).resolve() != self.space_manager.project_root.resolve():
                    continue
                dirty_spaces = getattr(worker, "_dirty_spaces", None)
                if dirty_spaces:
                    if space_name is None or space_name in dirty_spaces:
                        return True
            except Exception:
                continue
        return False

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
        stat_tuple: Optional[Tuple[int, int, int]] = None,
    ) -> Tuple[Optional[str], Optional[FileFingerprint]]:
        if stat_tuple is not None:
            mtime_ns, ctime_ns, size = stat_tuple
        else:
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
            effective_created_gen = (
                prev_fp.created_gen
                if (prev_fp is not None and prev_fp.created_gen > 0)
                else next_gen_candidate
            )
            return (
                "added",
                FileFingerprint(
                    path=rel_path,
                    mtime_ns=mtime_ns,
                    size=size,
                    content_hash=content_hash,
                    source_root=src_root.as_posix(),
                    created_gen=effective_created_gen,
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

    def _iter_space_entries_with_stat(
        self, space_name: str
    ) -> Iterator[Tuple[str, Path, Path, Optional[Tuple[int, int, int]]]]:
        if hasattr(self.space_manager, "iter_space_files_with_stat"):
            for (
                rel_p,
                abs_p,
                src_root,
                mtime_ns,
                ctime_ns,
                size,
            ) in self.space_manager.iter_space_files_with_stat(space_name):
                yield (rel_p, abs_p, src_root, (mtime_ns, ctime_ns, size))
        else:
            for rel_p, abs_p, src_root in self.space_manager.iter_space_files(
                space_name
            ):
                yield (rel_p, abs_p, src_root, None)

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

        for (
            rel_path,
            abs_path,
            src_root,
            stat_tuple,
        ) in self._iter_space_entries_with_stat(space_name):
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
                stat_tuple=stat_tuple,
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
        new_state = SnapshotState(
            head_generation=final_gen,
            merkle_root=m_root,
            config_hash=cfg_hash,
            entries=new_entries,
            last_diff=diff_res,
        )
        return new_state, diff_res

    def patch_space_files(
        self,
        space_name: str,
        dirty_paths: Iterable[Union[str, Path]],
        background: bool = False,
    ) -> SnapshotState:
        """
        Incrementally update a workspace's YFP2 snapshot for a targeted subset of dirty file paths
        in O(|dirty|) stat/hash operations without walking the entire directory tree.
        Falls back to scan_space() if no baseline snapshot exists or config_hash has changed.
        """
        cfg = self.space_manager.get_space(space_name)
        cfg_hash = self.space_manager.compute_config_hash(space_name)
        snap_path = self.get_snapshot_path(space_name)

        if not snap_path.exists():
            new_state, _ = self.scan_space(space_name, background=background)
            self.snapshot_mgr.save_state(new_state, snap_path)
            return new_state

        prev_state, corrupted = self._load_or_recover_state(space_name)
        if (
            corrupted
            or prev_state.head_generation == 0
            or (prev_state.config_hash and prev_state.config_hash != cfg_hash)
        ):
            new_state, _ = self.scan_space(
                space_name, background=background, force=corrupted
            )
            self.snapshot_mgr.save_state(new_state, snap_path)
            return new_state

        inc_roots = self.space_manager.resolve_space_include(space_name)
        multi_root = len(inc_roots) > 1
        proj_root = self.space_manager.project_root
        scan_start_ns = time.time_ns()
        prev_entries = prev_state.entries
        next_gen_candidate = prev_state.head_generation + 1

        added_set: Set[str] = set()
        modified_set: Set[str] = set()
        deleted_set: Set[str] = set()
        new_entries: Dict[str, FileFingerprint] = dict(prev_entries)
        any_entry_mutated = False

        for raw_item in dirty_paths:
            if not raw_item:
                continue
            cand_path = Path(raw_item)
            matched_root: Optional[Path] = None
            rel_to_root: Optional[str] = None
            abs_file: Optional[Path] = None

            if not cand_path.is_absolute():
                norm_rel = str(raw_item).replace("\\", "/").strip("/")
                if norm_rel in prev_entries and prev_entries[norm_rel].source_root:
                    matched_root = Path(prev_entries[norm_rel].source_root)
                    abs_file = matched_root / norm_rel
                    try:
                        rel_to_root = abs_file.relative_to(matched_root).as_posix()
                    except ValueError:
                        rel_to_root = norm_rel
                else:
                    for inc_root in inc_roots:
                        if inc_root.is_file():
                            if inc_root.name == norm_rel or self.space_manager._compute_rel_path(
                                inc_root, inc_root, multi_root, proj_root=proj_root
                            ) == norm_rel:
                                matched_root = inc_root
                                abs_file = inc_root
                                rel_to_root = inc_root.name
                                break
                            continue
                        cand_abs = inc_root / norm_rel
                        if cand_abs.exists() or len(inc_roots) == 1:
                            matched_root = inc_root
                            abs_file = cand_abs
                            rel_to_root = norm_rel
                            break
            else:
                abs_file = (
                    cand_path.resolve() if cfg.follow_symlinks else cand_path
                )
                for inc_root in inc_roots:
                    if inc_root.is_file():
                        if abs_file == inc_root or abs_file.resolve() == inc_root.resolve():
                            matched_root = inc_root
                            rel_to_root = inc_root.name
                            break
                        continue
                    try:
                        rel_to_root = abs_file.relative_to(inc_root).as_posix()
                        matched_root = inc_root
                        break
                    except ValueError:
                        try:
                            res_p = abs_file.resolve()
                            rel_to_root = res_p.relative_to(inc_root).as_posix()
                            abs_file = res_p
                            matched_root = inc_root
                            break
                        except ValueError:
                            continue

            if (
                matched_root is None
                or abs_file is None
                or not rel_to_root
                or rel_to_root == "."
            ):
                continue

            if not cfg.follow_symlinks and not multi_root:
                rel_path = rel_to_root
            else:
                rel_path = self.space_manager._compute_rel_path(
                    abs_file, matched_root, multi_root, proj_root=proj_root
                )

            prev_fp = prev_entries.get(rel_path)
            is_included = cfg.is_file_included(rel_to_root)
            stat_tuple: Optional[Tuple[int, int, int]] = None

            if is_included:
                try:
                    if not cfg.follow_symlinks and abs_file.is_symlink():
                        stat_tuple = None
                    else:
                        st = abs_file.stat()
                        if stat_mod.S_ISREG(st.st_mode):
                            mtime_ns = int(st.st_mtime_ns)
                            ctime_ns = int(getattr(st, "st_ctime_ns", mtime_ns))
                            size = int(st.st_size)
                            stat_tuple = (mtime_ns, ctime_ns, size)
                except OSError:
                    stat_tuple = None

            if stat_tuple is None:
                if prev_fp is not None and not prev_fp.is_deleted:
                    deleted_set.add(rel_path)
                    any_entry_mutated = True
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
                continue

            status, updated_fp = self._evaluate_entry_fingerprint(
                rel_path=rel_path,
                abs_path=abs_file,
                src_root=matched_root,
                cfg=cfg,
                prev_fp=prev_fp,
                next_gen_candidate=next_gen_candidate,
                scan_start_ns=scan_start_ns,
                background=background,
                force=False,
                stat_tuple=stat_tuple,
            )
            if status == "added":
                added_set.add(rel_path)
            elif status == "modified":
                modified_set.add(rel_path)
            if updated_fp is not None:
                new_entries[rel_path] = updated_fp
                any_entry_mutated = True

        changed_paths = added_set | modified_set | deleted_set
        unchanged_set = {
            k
            for k, fp in new_entries.items()
            if not fp.is_deleted and k not in changed_paths
        }
        has_structural_change = bool(changed_paths)
        final_gen = (
            next_gen_candidate
            if has_structural_change
            else prev_state.head_generation
        )
        m_root = (
            compute_merkle_root(new_entries)
            if has_structural_change
            else prev_state.merkle_root
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
        new_state = SnapshotState(
            head_generation=final_gen,
            merkle_root=m_root,
            config_hash=cfg_hash,
            entries=new_entries,
            last_diff=diff_res,
        )
        if has_structural_change or any_entry_mutated:
            self.snapshot_mgr.save_state(new_state, snap_path)
        return new_state

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
        if not refresh_first:
            _flush_in_process_watcher(self.space_manager.project_root, space_name)
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
        if not refresh_first:
            _flush_in_process_watcher(self.space_manager.project_root, space_name)
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
        if not auto_refresh:
            _flush_in_process_watcher(self.space_manager.project_root, space_name)
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
        watcher_active = is_watcher_active(
            self.space_manager.project_root, space_manager=self.space_manager
        )
        all_added: Set[str] = set()
        all_modified: Set[str] = set()
        all_deleted: Set[str] = set()
        all_unchanged: Set[str] = set()
        space_gens: Dict[str, int] = {}
        space_merkle_parts: List[str] = []

        for s_name in self.space_manager.list_spaces():
            s_cfg = self.space_manager.get_space(s_name)
            sub_auto_refresh = False
            if not auto_refresh and watcher_active and s_cfg and not s_cfg.watch:
                sub_auto_refresh = True
            s_diff = self.diff(
                s_name, consumer_id=consumer_id, auto_refresh=sub_auto_refresh
            )
            space_gens[s_name] = s_diff.to_generation
            space_merkle_parts.append(f"{s_name}:{s_diff.merkle_root}")
            all_added |= s_diff.detail.added
            all_modified |= s_diff.detail.modified
            all_deleted |= s_diff.detail.deleted
            all_unchanged |= s_diff.detail.unchanged

        all_unchanged -= all_added | all_modified | all_deleted
        unified_state, _ = self._load_or_recover_state(None)
        u_cursor = self.cursor_store.get_cursor(self.UNIFIED_KEY, consumer_id)

        dynamic_gen = sum(space_gens.values())
        effective_to_gen = max(unified_state.head_generation, dynamic_gen)
        if space_merkle_parts:
            hasher = hashlib.blake2b(digest_size=20)
            for part in sorted(space_merkle_parts):
                hasher.update(f"{part}\n".encode("utf-8"))
            effective_merkle = hasher.hexdigest()
        else:
            effective_merkle = unified_state.merkle_root

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
            to_generation=effective_to_gen,
            merkle_root=effective_merkle,
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

        resolved_space_gens: Dict[str, int] = {}
        for s_name in self.space_manager.list_spaces():
            s_state, _ = self._load_or_recover_state(s_name)
            s_cfg_hash = self.space_manager.compute_config_hash(s_name)
            s_target_gen = (
                int(space_generations[s_name])
                if space_generations and s_name in space_generations
                else s_state.head_generation
            )
            resolved_space_gens[s_name] = s_target_gen
            self.cursor_store.set_cursor(
                space_key=s_name,
                consumer_id=consumer_id,
                acked_gen=s_target_gen,
                merkle_root=s_state.merkle_root,
                config_hash=s_cfg_hash,
            )

        u_state, _ = self._load_or_recover_state(None)
        dynamic_u_gen = sum(resolved_space_gens.values())
        target_u_gen = (
            int(generation)
            if generation is not None
            else max(u_state.head_generation, dynamic_u_gen)
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
            if not is_watcher_active(
                self.space_manager.project_root,
                space_name=space_name,
                space_manager=self.space_manager,
            ):
                auto_refresh = True
            elif self.is_watcher_dirty(space_name=space_name):
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
