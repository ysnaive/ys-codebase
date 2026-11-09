"""
Public SDK entry point for module:gdrive-support (lazy attribute exports).
"""
from typing import Any

__version__ = "1.0.1.6"

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
    "ChangeRecord",
    "AbstractSyncTransport",
    "LocalSandboxTransport",
    "GoogleDriveApiTransport",
    "create_transport",
    "load_oauth_client_config",
    "build_oauth_authorize_url",
    "extract_code_from_input",
    "exchange_oauth_code_for_token",
    "run_oauth_loopback_flow",
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
        "ChangeRecord",
        "AbstractSyncTransport",
        "LocalSandboxTransport",
        "GoogleDriveApiTransport",
        "create_transport",
    ):
        from . import transport

        return getattr(transport, name)

    if name in (
        "load_oauth_client_config",
        "build_oauth_authorize_url",
        "extract_code_from_input",
        "exchange_oauth_code_for_token",
        "run_oauth_loopback_flow",
    ):
        from . import auth_flow

        return getattr(auth_flow, name)

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
        "build_managed_readme_content",
        "build_root_readme_managed_block",
        "merge_root_readme_block",
        "strip_root_readme_block",
        "reconcile_root_readme_state",
    ):
        from . import readme_sync

        return getattr(readme_sync, name)

    if name in (
        "SyncReport",
        "SyncCoordinator",
    ):
        from . import coordinator

        return getattr(coordinator, name)

    if name == "GDriveSyncServiceWorker":
        from . import service

        return getattr(service, name)

    raise AttributeError(f"module 'gdrive_support' has no attribute {name!r}")
