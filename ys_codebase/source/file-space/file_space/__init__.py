"""
Public SDK entry point for the file-space module.
"""
from contextlib import contextmanager
from pathlib import Path
import threading
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from .exceptions import (
    FingerprintCorruptedError,
    InvalidFileSpaceConfigError,
    FileSpaceError,
    FileSpaceNotFoundError,
)
from .manager import DEFAULT_EXCLUDES, DEFAULT_FILE_PATTERNS, FileSpaceManager
from .scanner import (
    BinarySnapshotManager,
    CursorStore,
    FingerprintScanner,
    SnapshotState,
    compute_merkle_root,
)
from .schema import (
    FileFingerprint,
    HashPolicy,
    ScanDiffDetail,
    ScanDiffResult,
    FileSpaceConfig,
    FileSpaceOrigin,
)
from .service import FileSpaceWatcherServiceWorker, clear_subscribers, subscribe

_SINGLETON_LOCK = threading.RLock()
_DEFAULT_MANAGER: Optional[FileSpaceManager] = None
_DEFAULT_SCANNER: Optional[FingerprintScanner] = None


def _get_default_scanner() -> FingerprintScanner:
    global _DEFAULT_MANAGER, _DEFAULT_SCANNER
    with _SINGLETON_LOCK:
        if _DEFAULT_SCANNER is None:
            _DEFAULT_MANAGER = FileSpaceManager()
            _DEFAULT_SCANNER = FingerprintScanner(space_manager=_DEFAULT_MANAGER)
        return _DEFAULT_SCANNER


def configure_default_file_space(
    project_root: Optional[Path] = None,
    storage_root: Optional[Path] = None,
    spaces_config: Optional[Dict[str, Dict[str, Any]]] = None,
    contributed_spaces: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[FileSpaceManager, FingerprintScanner]:
    """
    Configure or reset the default module-level FileSpaceManager and FingerprintScanner singletons.
    """
    global _DEFAULT_MANAGER, _DEFAULT_SCANNER
    with _SINGLETON_LOCK:
        _DEFAULT_MANAGER = FileSpaceManager(
            project_root=project_root,
            storage_root=storage_root,
            spaces_config=spaces_config,
            contributed_spaces=contributed_spaces,
        )
        _DEFAULT_SCANNER = FingerprintScanner(
            space_manager=_DEFAULT_MANAGER,
            storage_root=_DEFAULT_MANAGER.storage_root,
        )
        return _DEFAULT_MANAGER, _DEFAULT_SCANNER


# ----------------------------------------------------------------------
# ISpaceRegistry Top-Level Facade
# ----------------------------------------------------------------------
def list_spaces() -> List[str]:
    """Return all registered workspace names."""
    return _get_default_scanner().space_manager.list_spaces()


def get_space(name: str) -> FileSpaceConfig:
    """Return the FileSpaceConfig for a named workspace."""
    return _get_default_scanner().space_manager.get_space(name)


def define_ephemeral_space(
    name: str, config: Union[FileSpaceConfig, Dict[str, Any]]
) -> FileSpaceConfig:
    """Register an ephemeral in-memory workspace on the default FileSpaceManager."""
    return _get_default_scanner().space_manager.define_ephemeral_space(
        name, config
    )


def resolve_file_path(
    rel_path: str, space_name: Optional[str] = None
) -> Optional[Path]:
    """Resolve a workspace-relative path to an absolute Path."""
    return _get_default_scanner().space_manager.resolve_file_path(
        rel_path, space_name=space_name
    )


def iter_space_files(
    space_name: Optional[str] = None,
) -> Iterator[Tuple[str, Path, Path]]:
    """Iterate over (rel_path, abs_path, source_root) across one or all workspaces."""
    return _get_default_scanner().space_manager.iter_space_files(
        space_name=space_name
    )


# ----------------------------------------------------------------------
# ISnapshotProvider Top-Level Facade
# ----------------------------------------------------------------------
def refresh(
    space_name: Optional[str] = None,
    *,
    background: bool = False,
    force: bool = False,
) -> ScanDiffResult:
    """Perform two-stage incremental fingerprint scan and update YFP2 snapshot(s)."""
    return _get_default_scanner().refresh(
        space_name=space_name, background=background, force=force
    )


def snapshot(
    space_name: Optional[str] = None, *, refresh_first: bool = False
) -> Dict[str, FileFingerprint]:
    """Return active FileFingerprint map for the specified workspace (or all workspaces)."""
    return _get_default_scanner().snapshot(
        space_name=space_name, refresh_first=refresh_first
    )


def merkle_root(
    space_name: Optional[str] = None, *, refresh_first: bool = False
) -> str:
    """Return the Merkle root hex digest for the specified workspace (or all workspaces)."""
    return _get_default_scanner().merkle_root(
        space_name=space_name, refresh_first=refresh_first
    )


# ----------------------------------------------------------------------
# IChangeCursor Top-Level Facade
# ----------------------------------------------------------------------
def diff(
    space_name: Optional[str] = None,
    consumer_id: str = "default",
    *,
    auto_refresh: bool = True,
) -> ScanDiffResult:
    """Compute pending incremental changes for a consumer cursor without advancing it."""
    return _get_default_scanner().diff(
        space_name=space_name,
        consumer_id=consumer_id,
        auto_refresh=auto_refresh,
    )


def ack(
    space_name: Optional[str] = None,
    consumer_id: str = "default",
    generation: Optional[int] = None,
    space_generations: Optional[Dict[str, int]] = None,
) -> int:
    """確認消費者已處理完畢，推進游標世代號。"""
    return _get_default_scanner().ack(
        space_name=space_name,
        consumer_id=consumer_id,
        generation=generation,
        space_generations=space_generations,
    )


def reset_cursor(
    space_name: Optional[str] = None,
    consumer_id: str = "default",
) -> None:
    """Reset a consumer's watermark cursor to generation 0."""
    _get_default_scanner().reset_cursor(
        space_name=space_name, consumer_id=consumer_id
    )


@contextmanager
def consume_diff(
    space_name: Optional[str] = None,
    consumer_id: str = "default",
    *,
    auto_refresh: Optional[bool] = None,
) -> Iterator[ScanDiffResult]:
    """
    Transactional context manager that yields ScanDiffResult for a consumer
    and automatically calls ack() on normal exit, or preserves the cursor on exception.
    """
    with _get_default_scanner().consume_diff(
        space_name=space_name,
        consumer_id=consumer_id,
        auto_refresh=auto_refresh,
    ) as diff_res:
        yield diff_res


__all__ = [
    "BinarySnapshotManager",
    "CursorStore",
    "DEFAULT_EXCLUDES",
    "DEFAULT_FILE_PATTERNS",
    "FileFingerprint",
    "FingerprintCorruptedError",
    "FingerprintScanner",
    "HashPolicy",
    "InvalidFileSpaceConfigError",
    "ScanDiffDetail",
    "ScanDiffResult",
    "SnapshotState",
    "FileSpaceConfig",
    "FileSpaceError",
    "FileSpaceManager",
    "FileSpaceNotFoundError",
    "FileSpaceOrigin",
    "FileSpaceWatcherServiceWorker",
    "ack",
    "clear_subscribers",
    "compute_merkle_root",
    "configure_default_file_space",
    "consume_diff",
    "define_ephemeral_space",
    "diff",
    "get_space",
    "iter_space_files",
    "list_spaces",
    "merkle_root",
    "refresh",
    "reset_cursor",
    "resolve_file_path",
    "snapshot",
    "subscribe",
]
