"""
Deprecated FingerprintScanner, BinarySnapshotManager, and CursorStore forwarding layer.
Delegates all scanning, YFP2 snapshot persistence, and watermark cursors to core.space.
"""
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional, Union

from core.space import (
    BinarySnapshotManager,
    CursorStore,
    FileFingerprint,
    ScanDiffDetail,
    ScanDiffResult,
    SnapshotState,
    SpaceError,
    SpaceNotFoundError,
    SpaceScanner,
    compute_file_hash,
    compute_space_merkle_root,
    is_watcher_active as _core_is_watcher_active,
)
from .exceptions import FileSpaceError, FileSpaceNotFoundError, InvalidFileSpaceConfigError
from .manager import FileSpaceManager


def _atomic_write_bytes(target_path: Path, data: bytes) -> None:
    """Delegate atomic byte write to core.vfs."""
    from core import vfs

    vfs.makedirs(str(target_path.parent), exist_ok=True)
    vfs.write_bytes(str(target_path), data, atomic=True)


def compute_merkle_root(entries: Dict[str, FileFingerprint]) -> str:
    """Delegate Merkle root calculation to core.space."""
    from core.space.scanner import _compute_merkle_from_fingerprints

    active = [fp for fp in entries.values() if not fp.is_deleted]
    return _compute_merkle_from_fingerprints(active)


def is_watcher_active(
    project_root: Optional[Path] = None,
    space_name: Optional[str] = None,
    *,
    space_manager: Optional[FileSpaceManager] = None,
) -> bool:
    """Delegate watcher activity check to core.space.is_watcher_active."""
    reg = space_manager.registry if space_manager is not None else None
    return _core_is_watcher_active(
        space_query=space_name,
        registry=reg,
        project_root=project_root,
    )


class FingerprintScanner:
    """
    Lightweight compatibility wrapper delegating all operations to core.space.SpaceScanner.
    """

    UNIFIED_KEY = SpaceScanner.UNIFIED_KEY

    def __init__(
        self,
        space_manager: Optional[FileSpaceManager] = None,
        storage_root: Optional[Path] = None,
        *,
        scanner: Optional[SpaceScanner] = None,
    ) -> None:
        self.space_manager = space_manager or FileSpaceManager(
            storage_root=storage_root
        )
        eff_storage = (
            Path(storage_root).resolve()
            if storage_root is not None
            else self.space_manager.storage_root
        )
        self._scanner = scanner or SpaceScanner(
            registry=self.space_manager.registry,
            storage_root=eff_storage,
        )

    @property
    def storage_root(self) -> Path:
        return self._scanner.storage_root

    @property
    def snapshots_dir(self) -> Path:
        return self._scanner.snapshots_dir

    @property
    def cursor_store(self) -> CursorStore:
        return self._scanner.cursor_store

    def get_snapshot_path(self, space_name: Optional[str] = None) -> Path:
        key = self._scanner._canonical_space_key(space_name)
        return self._scanner._snapshot_path(key)

    def _load_or_recover_state(
        self, space_name: Optional[str] = None
    ) -> tuple:
        key = self._scanner._canonical_space_key(space_name)
        is_ephem = self.space_manager.registry.is_ephemeral_query(space_name)
        state = self._scanner._load_snapshot_state(key, is_ephemeral=is_ephem)
        return state, False

    def is_watcher_dirty(self, space_name: Optional[str] = None) -> bool:
        _ = space_name
        return self._scanner.has_watcher_dirty_marker()

    @staticmethod
    def compute_file_hash(
        file_path: Path,
        size: int,
        mtime_ns: int,
        policy: Any = "adaptive",
        large_file_threshold_mb: int = 10,
    ) -> str:
        try:
            return compute_file_hash(
                file_path,
                size=size,
                mtime_ns=mtime_ns,
                policy=policy,
                large_file_threshold_mb=large_file_threshold_mb,
            )
        except SpaceError as exc:
            raise InvalidFileSpaceConfigError(str(exc)) from exc

    def refresh(
        self,
        space_name: Optional[str] = None,
        *,
        background: bool = False,
        force: bool = False,
    ) -> ScanDiffResult:
        try:
            return self._scanner.refresh(
                space_query=space_name, background=background, force=force
            )
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        except SpaceError as exc:
            raise FileSpaceError(str(exc)) from exc

    def scan(
        self,
        space_name: Optional[str] = None,
        *,
        force: bool = False,
    ) -> ScanDiffResult:
        return self.refresh(space_name=space_name, force=force)

    def patch_space_files(
        self,
        space_name: Optional[str],
        dirty_paths: Iterable[Union[str, Path]],
        *,
        background: bool = False,
    ) -> SnapshotState:
        _ = background
        try:
            return self._scanner.patch_files(space_name, dirty_paths)
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        except SpaceError as exc:
            raise FileSpaceError(str(exc)) from exc

    def snapshot(
        self,
        space_name: Optional[str] = None,
        *,
        refresh_first: bool = False,
    ) -> Dict[str, FileFingerprint]:
        try:
            return self._scanner.snapshot(
                space_query=space_name, refresh_first=refresh_first
            )
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        except SpaceError as exc:
            raise FileSpaceError(str(exc)) from exc

    def merkle_root(
        self,
        space_name: Optional[str] = None,
        *,
        refresh_first: bool = False,
    ) -> str:
        try:
            return self._scanner.merkle_root(
                space_query=space_name, refresh_first=refresh_first
            )
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        except SpaceError as exc:
            raise FileSpaceError(str(exc)) from exc

    def diff(
        self,
        space_name: Optional[str] = None,
        consumer_id: str = "default",
        *,
        auto_refresh: bool = True,
    ) -> ScanDiffResult:
        try:
            return self._scanner.diff(
                space_query=space_name,
                consumer_id=consumer_id,
                auto_refresh=auto_refresh,
            )
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        except SpaceError as exc:
            raise FileSpaceError(str(exc)) from exc

    def ack(
        self,
        space_name: Optional[str] = None,
        consumer_id: str = "default",
        generation: Optional[int] = None,
        space_generations: Optional[Dict[str, int]] = None,
    ) -> int:
        try:
            return self._scanner.ack(
                space_query=space_name,
                consumer_id=consumer_id,
                generation=generation,
                space_generations=space_generations,
            )
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        except SpaceError as exc:
            raise FileSpaceError(str(exc)) from exc

    def reset_cursor(
        self,
        space_name: Optional[str] = None,
        consumer_id: str = "default",
    ) -> None:
        try:
            self._scanner.reset_cursor(
                space_query=space_name, consumer_id=consumer_id
            )
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        except SpaceError as exc:
            raise FileSpaceError(str(exc)) from exc

    @contextmanager
    def consume_diff(
        self,
        space_name: Optional[str] = None,
        consumer_id: str = "default",
        *,
        auto_refresh: Optional[bool] = None,
    ) -> Iterator[ScanDiffResult]:
        eff_refresh = True if auto_refresh is None else bool(auto_refresh)
        try:
            with self._scanner.consume_diff(
                space_query=space_name,
                consumer_id=consumer_id,
                auto_refresh=eff_refresh,
            ) as res:
                yield res
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        except SpaceError as exc:
            raise FileSpaceError(str(exc)) from exc

    def status(self, space_name: Optional[str] = None) -> Dict[str, Any]:
        try:
            return self._scanner.status(space_query=space_name)
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        except SpaceError as exc:
            raise FileSpaceError(str(exc)) from exc

    def clean(
        self,
        space_name: Optional[str] = None,
        *,
        consumer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            return self._scanner.clean(
                space_query=space_name, consumer_id=consumer_id
            )
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        except SpaceError as exc:
            raise FileSpaceError(str(exc)) from exc


__all__ = [
    "BinarySnapshotManager",
    "CursorStore",
    "FileFingerprint",
    "FingerprintScanner",
    "ScanDiffDetail",
    "ScanDiffResult",
    "SnapshotState",
    "SpaceScanner",
    "_atomic_write_bytes",
    "compute_merkle_root",
    "compute_space_merkle_root",
    "is_watcher_active",
]
