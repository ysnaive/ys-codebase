"""
Public SDK entry point for module:gdrive-support (lazy attribute exports).
"""
from typing import Any

__version__ = "1.0.1.5"

__all__ = [
    "__version__",
    "GDriveError",
    "GDriveConfigError",
    "GDrivePathError",
    "GDriveFileNotFoundError",
    "GDriveUnsupportedMimeError",
    "GDriveTransportError",
    "GDriveRepoUninitializedError",
    "GDriveRepoSyncDisabledError",
    "GDriveConflictError",
    "GDriveDirtyWorktreeError",
    "PathMappingRule",
    "SyncSpaceSpec",
    "RepoSyncConfig",
    "GDriveConfig",
    "normalize_remote_rel_path",
    "is_sensitive_credential_path",
    "load_gdrive_config",
    "collect_space_local_files",
    "collect_space_local_files_with_stat",
    "RemoteEntry",
    "AbstractSyncTransport",
    "LocalSandboxTransport",
    "GoogleDriveApiTransport",
    "create_transport",
    "SyncActionType",
    "FileEntry",
    "SyncAction",
    "reconcile_three_way",
    "compute_history_ref_counts",
    "compute_orphan_history_file_ids",
    "is_file_id_referenced_by_other_branches",
    "DEFAULT_REPO_SYNC_ROOT",
    "ROOT_README_BEGIN_MARKER",
    "ROOT_README_END_MARKER",
    "SyncReport",
    "SyncCoordinator",
    "build_managed_readme_content",
    "build_root_readme_managed_block",
    "merge_root_readme_block",
    "strip_root_readme_block",
    "reconcile_root_readme_state",
    "GDriveSyncServiceWorker",
]


def __getattr__(name: str) -> Any:
    if name in (
        "GDriveError",
        "GDriveConfigError",
        "GDrivePathError",
        "GDriveFileNotFoundError",
        "GDriveUnsupportedMimeError",
        "GDriveTransportError",
        "GDriveRepoUninitializedError",
        "GDriveRepoSyncDisabledError",
        "GDriveConflictError",
        "GDriveDirtyWorktreeError",
        "PathMappingRule",
        "SyncSpaceSpec",
        "RepoSyncConfig",
        "GDriveConfig",
        "normalize_remote_rel_path",
        "is_sensitive_credential_path",
        "load_gdrive_config",
        "collect_space_local_files",
        "collect_space_local_files_with_stat",
    ):
        from . import config

        return getattr(config, name)

    if name in (
        "RemoteEntry",
        "AbstractSyncTransport",
        "LocalSandboxTransport",
        "GoogleDriveApiTransport",
        "create_transport",
    ):
        from . import transport

        return getattr(transport, name)

    if name in (
        "SyncActionType",
        "FileEntry",
        "SyncAction",
        "reconcile_three_way",
        "compute_history_ref_counts",
        "compute_orphan_history_file_ids",
        "is_file_id_referenced_by_other_branches",
    ):
        from . import reconciler

        return getattr(reconciler, name)

    if name in (
        "DEFAULT_REPO_SYNC_ROOT",
        "ROOT_README_BEGIN_MARKER",
        "ROOT_README_END_MARKER",
        "SyncReport",
        "SyncCoordinator",
        "build_managed_readme_content",
        "build_root_readme_managed_block",
        "merge_root_readme_block",
        "strip_root_readme_block",
        "reconcile_root_readme_state",
    ):
        from . import coordinator

        return getattr(coordinator, name)

    if name == "GDriveSyncServiceWorker":
        from . import service

        return getattr(service, name)

    raise AttributeError(f"module 'gdrive_support' has no attribute {name!r}")
