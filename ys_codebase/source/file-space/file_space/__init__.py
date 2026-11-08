"""
Deprecated facade entry point for the file-space module.
All operations delegate 100% to `core.space`.
Please update `core` to `>=1.2.7.5` and run `python yscb.py remove file-space`.
"""
from contextlib import contextmanager
from pathlib import Path
import threading
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from core.space import (
    BinarySnapshotManager,
    CompiledRuleSet,
    CursorStore,
    FileFingerprint,
    FileHashEntry,
    HashPolicy,
    MatchExplainResult,
    RuleItem,
    ScanDiffDetail,
    ScanDiffResult,
    SnapshotState,
    SpaceConfig,
    SpaceCycleError,
    SpaceError,
    SpaceFileEntry,
    SpaceHashResult,
    SpaceMatchDetail,
    SpaceNotFoundError,
    SpaceRegistry,
    SpaceScanner,
    get_default_registry,
    get_knowledge_db_spaces,
    get_registered_file_spaces_table,
    is_watcher_active,
    register_space,
    reset_default_instances,
    unregister_space,
)
from core.context import get_runtime_context
from .exceptions import (
    FileSpaceError,
    FileSpaceNotFoundError,
    FingerprintCorruptedError,
    InvalidFileSpaceConfigError,
)
from .manager import DEFAULT_EXCLUDES, DEFAULT_FILE_PATTERNS, FileSpaceManager
from .scanner import FingerprintScanner, compute_merkle_root
from .schema import FileSpaceConfig, FileSpaceOrigin
from .service import FileSpaceWatcherServiceWorker, clear_subscribers, subscribe

__version__ = "1.0.1.5"

_SINGLETON_LOCK = threading.RLock()


def _get_default_state() -> Dict[str, Any]:
    ctx = get_runtime_context()
    state = getattr(ctx, "module_states", None)
    if state is None:
        state = {}
        setattr(ctx, "module_states", state)
    st = state.setdefault(
        "file_space.defaults",
        {"manager": None, "scanner": None, "custom_configured": False},
    )
    if "_DEFAULT_MANAGER" in globals():
        mgr_override = globals().pop("_DEFAULT_MANAGER")
        st["manager"] = mgr_override
        if mgr_override is None:
            st["custom_configured"] = False
            if "_DEFAULT_SCANNER" not in globals():
                st["scanner"] = None
    if "_DEFAULT_SCANNER" in globals():
        scn_override = globals().pop("_DEFAULT_SCANNER")
        st["scanner"] = scn_override
        if scn_override is None:
            st["custom_configured"] = False
    return st


def _get_default_scanner() -> FingerprintScanner:
    with _SINGLETON_LOCK:
        st = _get_default_state()
        scn = st.get("scanner")
        mgr = st.get("manager")
        expected_root = get_default_registry().project_root
        root_mismatch = not st.get("custom_configured", False) and (
            getattr(mgr, "project_root", None) != expected_root
            or getattr(getattr(scn, "space_manager", None), "project_root", None) != expected_root
        )
        if scn is None or mgr is None or root_mismatch:
            mgr = FileSpaceManager()
            scn = FingerprintScanner(space_manager=mgr)
            st["manager"] = mgr
            st["scanner"] = scn
            st["custom_configured"] = False
        return scn


def configure_default_file_space(
    project_root: Optional[Path] = None,
    storage_root: Optional[Path] = None,
    spaces_config: Optional[Dict[str, Dict[str, Any]]] = None,
    contributed_spaces: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[FileSpaceManager, FingerprintScanner]:
    """Configure or reset the default FileSpaceManager and FingerprintScanner forwarding instances."""
    with _SINGLETON_LOCK:
        st = _get_default_state()
        mgr = FileSpaceManager(
            project_root=project_root,
            storage_root=storage_root,
            spaces_config=spaces_config,
            contributed_spaces=contributed_spaces,
        )
        scn = FingerprintScanner(
            space_manager=mgr,
            storage_root=mgr.storage_root,
        )
        st["manager"] = mgr
        st["scanner"] = scn
        st["custom_configured"] = any(
            x is not None
            for x in (project_root, storage_root, spaces_config, contributed_spaces)
        )
        return mgr, scn


def __getattr__(name: str) -> Any:
    if name == "_DEFAULT_MANAGER":
        return _get_default_state().get("manager")
    if name == "_DEFAULT_SCANNER":
        return _get_default_state().get("scanner")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def list_spaces() -> List[str]:
    """Return registered workspace short names."""
    return _get_default_scanner().space_manager.list_spaces()


def get_space(name: str) -> FileSpaceConfig:
    """Return the FileSpaceConfig for a named workspace."""
    return _get_default_scanner().space_manager.get_space(name)


def define_ephemeral_space(
    name: str, config: Union[FileSpaceConfig, SpaceConfig, Dict[str, Any]]
) -> FileSpaceConfig:
    """Register an ephemeral in-memory workspace."""
    return _get_default_scanner().space_manager.define_ephemeral_space(name, config)


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
    """Iterate over (rel_path, abs_path, entry_path) across one or all workspaces."""
    return _get_default_scanner().space_manager.iter_space_files(
        space_name=space_name
    )


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


def scan(
    space_name: Optional[str] = None,
    *,
    force: bool = False,
) -> ScanDiffResult:
    """Alias for refresh(space_name, force=force)."""
    return _get_default_scanner().scan(space_name=space_name, force=force)


def snapshot(
    space_name: Optional[str] = None, *, refresh_first: bool = False
) -> Dict[str, FileFingerprint]:
    """Return active FileFingerprint map for the specified workspace."""
    return _get_default_scanner().snapshot(
        space_name=space_name, refresh_first=refresh_first
    )


def merkle_root(
    space_name: Optional[str] = None, *, refresh_first: bool = False
) -> str:
    """Return the Merkle root hex digest for the specified workspace."""
    return _get_default_scanner().merkle_root(
        space_name=space_name, refresh_first=refresh_first
    )


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
    """Advance a consumer's watermark cursor."""
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
    """Transactional context manager that yields ScanDiffResult and acknowledges on normal exit."""
    with _get_default_scanner().consume_diff(
        space_name=space_name,
        consumer_id=consumer_id,
        auto_refresh=auto_refresh,
    ) as diff_res:
        yield diff_res


__all__ = [
    "BinarySnapshotManager",
    "CompiledRuleSet",
    "CursorStore",
    "DEFAULT_EXCLUDES",
    "DEFAULT_FILE_PATTERNS",
    "FileFingerprint",
    "FileHashEntry",
    "FileSpaceConfig",
    "FileSpaceError",
    "FileSpaceManager",
    "FileSpaceNotFoundError",
    "FileSpaceOrigin",
    "FileSpaceWatcherServiceWorker",
    "FingerprintCorruptedError",
    "FingerprintScanner",
    "HashPolicy",
    "InvalidFileSpaceConfigError",
    "MatchExplainResult",
    "RuleItem",
    "ScanDiffDetail",
    "ScanDiffResult",
    "SnapshotState",
    "SpaceConfig",
    "SpaceCycleError",
    "SpaceError",
    "SpaceFileEntry",
    "SpaceHashResult",
    "SpaceMatchDetail",
    "SpaceNotFoundError",
    "SpaceRegistry",
    "SpaceScanner",
    "ack",
    "clear_subscribers",
    "compute_merkle_root",
    "configure_default_file_space",
    "consume_diff",
    "define_ephemeral_space",
    "diff",
    "get_knowledge_db_spaces",
    "get_registered_file_spaces_table",
    "get_space",
    "is_watcher_active",
    "iter_space_files",
    "list_spaces",
    "merkle_root",
    "refresh",
    "register_space",
    "reset_cursor",
    "reset_default_instances",
    "resolve_file_path",
    "scan",
    "snapshot",
    "subscribe",
    "unregister_space",
]
