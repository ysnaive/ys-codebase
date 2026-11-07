"""
Configuration parsing, core.space integration, and path mapping validation for gdrive-support.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core import config as core_config
from core import contributes as core_contributes
from core import uri


class GDriveError(Exception):
    """Base exception for all gdrive-support operational and configuration errors."""


class GDriveConfigError(GDriveError):
    """Raised when configuration or sync_spaces mapping validation fails."""


class GDrivePathError(GDriveError):
    """Raised when a remote or local relative path is invalid or attempts traversal."""


class GDriveFileNotFoundError(GDriveError):
    """Raised when a requested remote file, folder, or shortcut target does not exist."""


class GDriveUnsupportedMimeError(GDriveError):
    """Raised when attempting binary operations on unsupported Google Workspace native items."""


class GDriveTransportError(GDriveError):
    """Raised when underlying transport (API or sandbox) operations fail."""


class GDriveRepoUninitializedError(GDriveError):
    """Raised when the remote root folder is non-empty and lacks .yscb_gdrive.json."""


class GDriveConflictError(GDriveError):
    """Raised when unidirectional pull/push encounters a modification conflict without --force."""


class GDriveDirtyWorktreeError(GDriveError):
    """Raised when branch checkout is attempted while local tracked files have unsynced changes."""


class GDriveRepoSyncDisabledError(GDriveError):
    """Raised when a repo_sync operation (init/branch/checkout/pull/push/sync) is invoked while repo_sync.enable is False."""


def normalize_remote_rel_path(remote_path: str) -> str:
    """
    Normalize a remote relative path into clean POSIX format without leading/trailing slashes.
    Rejects parent directory traversal ('..').
    """
    raw = (remote_path or "").strip().replace("\\", "/")
    if not raw or raw == ".":
        return ""
    parts: List[str] = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            raise GDrivePathError(
                f"Invalid remote path '{remote_path}': parent traversal ('..') is forbidden."
            )
        parts.append(part)
    return "/".join(parts)


@dataclass(frozen=True)
class PathMappingRule:
    """
    Bidirectional prefix mapping rule between a project-relative local path and a remote path.
    """

    local_uri: str
    local_rel_prefix: str
    remote_rel_prefix: str


@dataclass(frozen=True)
class SyncSpaceSpec:
    """
    Validated synchronization specification binding a registered core.space and optional mappings.
    """

    space: str
    mappings: Tuple[PathMappingRule, ...] = field(default_factory=tuple)
    include_roots: Tuple[Path, ...] = field(default_factory=tuple)
    large_file_threshold_mb: int = 10
    description: str = ""

    def __post_init__(self) -> None:
        sorted_rules = tuple(
            sorted(
                self.mappings,
                key=lambda r: (len(r.local_rel_prefix), len(r.remote_rel_prefix)),
                reverse=True,
            )
        )
        object.__setattr__(self, "mappings", sorted_rules)
        norm_roots = tuple(Path(p).resolve() for p in self.include_roots)
        object.__setattr__(self, "include_roots", norm_roots)

    def is_local_abs_allowed(self, target_abs: Path, proj_root: Path) -> bool:
        """
        Verify target_abs resides inside project_root AND (when include_roots are configured)
        within at least one of this space's registered include_roots.
        """
        resolved_target = target_abs.resolve()
        if not _is_path_within_roots(resolved_target, [proj_root.resolve()]):
            return False
        if not self.include_roots:
            return True
        return _is_path_within_roots(resolved_target, list(self.include_roots))

    def local_to_remote_rel(self, project_rel_path: str) -> Optional[str]:
        """
        Convert a project-relative POSIX path into its mapped remote branch-relative POSIX path.
        Returns None if explicit mappings are defined and the path does not match any mapping rule.
        """
        norm_local = normalize_remote_rel_path(project_rel_path)
        if not self.mappings:
            return norm_local

        for rule in self.mappings:
            loc_prefix = rule.local_rel_prefix
            rem_prefix = rule.remote_rel_prefix
            if not loc_prefix:
                return f"{rem_prefix}/{norm_local}".strip("/") if rem_prefix else norm_local
            if norm_local == loc_prefix:
                return rem_prefix
            if norm_local.startswith(f"{loc_prefix}/"):
                suffix = norm_local[len(loc_prefix) + 1 :]
                return f"{rem_prefix}/{suffix}".strip("/") if rem_prefix else suffix
        return None

    def remote_to_local_rel(self, remote_rel_path: str) -> Optional[str]:
        """
        Convert a remote branch-relative POSIX path back into its project-relative POSIX path.
        Returns None if explicit mappings are defined and the remote path does not match any rule.
        """
        norm_remote = normalize_remote_rel_path(remote_rel_path)
        if not self.mappings:
            return norm_remote

        rules_by_remote = sorted(
            self.mappings,
            key=lambda r: len(r.remote_rel_prefix),
            reverse=True,
        )
        for rule in rules_by_remote:
            loc_prefix = rule.local_rel_prefix
            rem_prefix = rule.remote_rel_prefix
            if not rem_prefix:
                return f"{loc_prefix}/{norm_remote}".strip("/") if loc_prefix else norm_remote
            if norm_remote == rem_prefix:
                return loc_prefix
            if norm_remote.startswith(f"{rem_prefix}/"):
                suffix = norm_remote[len(rem_prefix) + 1 :]
                return f"{loc_prefix}/{suffix}".strip("/") if loc_prefix else suffix
        return None


@dataclass(frozen=True)
class RepoSyncConfig:
    """
    Configuration block for 'repo_sync' (branch management and three-way workspace synchronization).
    When enable is False (default), all repo_sync operations and background auto_sync are disabled.
    """

    enable: bool = False
    repo_sync_root: str = "repo"
    active_branch: str = "main"
    auto_sync: bool = False
    poll_interval_sec: float = 30.0
    pull_delete_default: bool = False
    push_delete_default: bool = False
    sync_spaces: Tuple[SyncSpaceSpec, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GDriveConfig:
    """
    Immutable configuration container for module:gdrive-support.
    """

    root_folder_id: str = ""
    repo_sync_enabled: bool = False
    repo_sync_root: str = "repo"
    active_branch: str = "main"
    auto_sync: bool = False
    poll_interval_sec: float = 30.0
    pull_delete_default: bool = False
    push_delete_default: bool = False
    auth_mode: str = "oauth_user"
    credentials_uri: str = "config.local://gdrive-support/credentials.json"
    token_uri: str = "config.local://gdrive-support/token.json"
    sandbox_dir: str = ""
    sync_spaces: Tuple[SyncSpaceSpec, ...] = field(default_factory=tuple)

    @property
    def repo_sync(self) -> RepoSyncConfig:
        """Return the structured RepoSyncConfig view."""
        return RepoSyncConfig(
            enable=self.repo_sync_enabled,
            repo_sync_root=self.repo_sync_root,
            active_branch=self.active_branch,
            auto_sync=bool(self.repo_sync_enabled and self.auto_sync),
            poll_interval_sec=self.poll_interval_sec,
            pull_delete_default=self.pull_delete_default,
            push_delete_default=self.push_delete_default,
            sync_spaces=self.sync_spaces if self.repo_sync_enabled else (),
        )


def _resolve_project_root(explicit_project_root: Optional[Path] = None) -> Path:
    if explicit_project_root is not None:
        return Path(explicit_project_root).resolve()
    resolved = uri.resolve("project://")
    return Path(resolved).resolve()


def _resolve_local_uri_to_abs(local_uri_str: str, proj_root: Path) -> Path:
    raw = (local_uri_str or "").strip()
    if not raw:
        raise GDriveConfigError("Mapping 'local' URI cannot be empty.")
    if "://" in raw:
        if raw.startswith("project://"):
            rel_part = raw[len("project://") :].lstrip("/")
            return (proj_root / rel_part).resolve()
        try:
            resolved = uri.resolve(raw)
            if resolved:
                return Path(resolved).resolve()
        except Exception as exc:
            raise GDriveConfigError(f"Failed to resolve mapping URI '{raw}': {exc}") from exc
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (proj_root / raw).resolve()


def _is_path_within_roots(target_abs: Path, allowed_roots: List[Path]) -> bool:
    for root in allowed_roots:
        resolved_root = root.resolve()
        if target_abs == resolved_root:
            return True
        try:
            target_abs.relative_to(resolved_root)
            return True
        except ValueError:
            continue
    return False


def _load_space_include_roots(
    proj_root: Path,
    explicit_include_roots: Optional[Dict[str, List[Path]]] = None,
) -> Dict[str, List[Path]]:
    if explicit_include_roots is not None:
        return {
            k: [Path(p).resolve() for p in v]
            for k, v in explicit_include_roots.items()
        }
    try:
        from core.space import SpaceRegistry, resolve_semantic_or_rel_path

        reg = SpaceRegistry(project_root=proj_root)
        result: Dict[str, List[Path]] = {}
        for s_cfg in reg.list_spaces():
            roots: List[Path] = []
            if hasattr(reg, "collect_all_entry_paths") and s_cfg.qualified_name:
                try:
                    roots = [
                        Path(p).resolve()
                        for p in reg.collect_all_entry_paths(s_cfg.qualified_name)
                    ]
                except Exception:
                    roots = []
            if not roots:
                for raw_ent in s_cfg.entries:
                    resolved_p = resolve_semantic_or_rel_path(raw_ent, proj_root)
                    if resolved_p is not None:
                        roots.append(Path(resolved_p).resolve())
            if s_cfg.short_name and (roots or s_cfg.short_name not in result):
                if roots and s_cfg.short_name in result and result[s_cfg.short_name]:
                    merged = list(result[s_cfg.short_name])
                    for r in roots:
                        if r not in merged:
                            merged.append(r)
                    result[s_cfg.short_name] = merged
                else:
                    result[s_cfg.short_name] = roots
            if s_cfg.qualified_name:
                result[s_cfg.qualified_name] = roots
        return result
    except Exception:
        return {}


def _load_space_thresholds_mb(proj_root: Path) -> Dict[str, int]:
    try:
        from core.space import SpaceRegistry

        reg = SpaceRegistry(project_root=proj_root)
        thresholds: Dict[str, int] = {}
        for s_cfg in reg.list_spaces():
            val = getattr(s_cfg, "large_file_threshold_mb", 10)
            thresh = int(val) if isinstance(val, (int, float)) and val > 0 else 10
            if s_cfg.short_name:
                thresholds[s_cfg.short_name] = thresh
            if s_cfg.qualified_name:
                thresholds[s_cfg.qualified_name] = thresh
        return thresholds
    except Exception:
        return {}


_FORBIDDEN_CREDENTIAL_FILENAMES = frozenset(
    {
        "credentials.json",
        "token.json",
        "service_account.json",
        "client_secret.json",
        ".env",
    }
)


def is_sensitive_credential_path(abs_path: Path, proj_root: Path) -> bool:
    """
    Hard security guard: Return True if abs_path points to any credential, token,
    private key, or local/module secret file that must NEVER be uploaded to
    Google Drive or overwritten by repo_sync.
    """
    name_low = abs_path.name.lower()
    if name_low in _FORBIDDEN_CREDENTIAL_FILENAMES:
        return True
    if "secret" in name_low and name_low.endswith(".json"):
        return True
    if name_low.endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    try:
        rel_posix = abs_path.relative_to(proj_root).as_posix()
    except ValueError:
        try:
            rel_posix = abs_path.resolve().relative_to(proj_root.resolve()).as_posix()
        except ValueError:
            rel_posix = ""
    if rel_posix and rel_posix.startswith(
        (
            "ys_codebase/.config.local/",
            "ys_codebase/.storage.local/",
            "ys_codebase/config/gdrive-support/",
            "ys_codebase/.cache/gdrive-support/",
        )
    ) and rel_posix != "ys_codebase/config/gdrive-support/config.project.json":
        return True
    return False


def parse_sync_spaces(
    raw_sync_spaces: List[Dict[str, Any]],
    proj_root: Path,
    space_include_roots: Dict[str, List[Path]],
    space_thresholds_mb: Optional[Dict[str, int]] = None,
) -> Tuple[SyncSpaceSpec, ...]:
    """
    Validate and compile raw sync_spaces declarations against registered core.space include roots.
    """
    thresholds_map = space_thresholds_mb or {}
    specs: List[SyncSpaceSpec] = []
    for item in raw_sync_spaces:
        if not isinstance(item, dict):
            continue
        space_name = str(item.get("space") or "").strip()
        if not space_name:
            raise GDriveConfigError("Each sync_spaces entry must specify a non-empty 'space' name.")
        if space_name not in space_include_roots:
            raise GDriveConfigError(
                f"Sync space '{space_name}' is not registered in core.space. "
                f"Available spaces: {sorted(space_include_roots.keys())}"
            )
        inc_roots = space_include_roots[space_name]
        raw_mappings = item.get("mapping") or []
        if not isinstance(raw_mappings, list):
            raise GDriveConfigError(
                f"Invalid 'mapping' in sync space '{space_name}': expected a list of {local, remote} objects."
            )

        compiled_rules: List[PathMappingRule] = []
        for rule_obj in raw_mappings:
            if not isinstance(rule_obj, dict):
                raise GDriveConfigError(
                    f"Invalid mapping item in sync space '{space_name}': expected dict."
                )
            local_uri_str = str(rule_obj.get("local") or "").strip()
            remote_str = str(rule_obj.get("remote") or "").strip()
            if not local_uri_str:
                raise GDriveConfigError(
                    f"Mapping rule in space '{space_name}' is missing 'local'."
                )
            target_abs = _resolve_local_uri_to_abs(local_uri_str, proj_root)
            if not _is_path_within_roots(target_abs, inc_roots):
                allowed_str = ", ".join(p.as_posix() for p in inc_roots)
                raise GDriveConfigError(
                    f"Mapping local path '{local_uri_str}' (resolved to '{target_abs.as_posix()}') "
                    f"is outside the include roots of space '{space_name}' ([{allowed_str}])."
                )
            try:
                local_rel = target_abs.relative_to(proj_root).as_posix()
                if local_rel == ".":
                    local_rel = ""
            except ValueError as exc:
                raise GDriveConfigError(
                    f"Mapping local path '{target_abs.as_posix()}' must reside inside project_root '{proj_root.as_posix()}'."
                ) from exc

            remote_rel = normalize_remote_rel_path(remote_str)
            compiled_rules.append(
                PathMappingRule(
                    local_uri=local_uri_str,
                    local_rel_prefix=local_rel,
                    remote_rel_prefix=remote_rel,
                )
            )

        specs.append(
            SyncSpaceSpec(
                space=space_name,
                mappings=tuple(compiled_rules),
                include_roots=tuple(inc_roots),
                large_file_threshold_mb=int(thresholds_map.get(space_name, 10)),
                description=str(item.get("description") or ""),
            )
        )
    return tuple(specs)


def load_gdrive_config(
    config_override: Optional[Dict[str, Any]] = None,
    project_root: Optional[Path] = None,
    space_include_roots: Optional[Dict[str, List[Path]]] = None,
) -> GDriveConfig:
    """
    Load GDriveConfig from core.config and core.contributes (or explicit overrides).
    Enforces auto_sync=False by default and validates all sync_spaces mapping boundaries.
    """
    proj_root = _resolve_project_root(project_root)

    raw_cfg: Dict[str, Any] = {}
    try:
        loaded = core_config.get("gdrive-support")
        if isinstance(loaded, dict):
            raw_cfg.update(loaded)
    except Exception:
        pass

    if config_override:
        raw_cfg.update(config_override)

    raw_sync_spaces: Optional[List[Dict[str, Any]]] = None
    if config_override and "sync_spaces" in config_override:
        raw_sync_spaces = config_override["sync_spaces"]
    else:
        try:
            contrib = core_contributes.get("gdrive-support")
            if isinstance(contrib, dict) and isinstance(contrib.get("sync_spaces"), list):
                raw_sync_spaces = contrib["sync_spaces"]
        except Exception:
            raw_sync_spaces = []

    compiled_spaces: Tuple[SyncSpaceSpec, ...] = ()
    if raw_sync_spaces:
        inc_map = _load_space_include_roots(proj_root, space_include_roots)
        thresh_map = _load_space_thresholds_mb(proj_root)
        compiled_spaces = parse_sync_spaces(
            raw_sync_spaces, proj_root, inc_map, thresh_map
        )

    raw_repo_sync = raw_cfg.get("repo_sync")
    repo_sync_dict: Dict[str, Any] = (
        dict(raw_repo_sync) if isinstance(raw_repo_sync, dict) else {}
    )

    if "enable" in repo_sync_dict:
        repo_sync_enabled = bool(repo_sync_dict["enable"])
    elif "repo_sync_enabled" in raw_cfg:
        repo_sync_enabled = bool(raw_cfg["repo_sync_enabled"])
    else:
        repo_sync_enabled = False

    raw_repo_sync_root = repo_sync_dict.get(
        "repo_sync_root", raw_cfg.get("repo_sync_root") or "repo"
    )
    repo_sync_root = (
        normalize_remote_rel_path(str(raw_repo_sync_root or "repo")) or "repo"
    )

    raw_active_branch = repo_sync_dict.get(
        "active_branch", raw_cfg.get("active_branch") or "main"
    )
    active_branch = (
        normalize_remote_rel_path(str(raw_active_branch or "main")) or "main"
    )
    if "/" in active_branch:
        raise GDriveConfigError(
            f"Invalid active_branch '{active_branch}': branch name cannot contain '/'."
        )

    raw_auto_sync = bool(
        repo_sync_dict.get("auto_sync", raw_cfg.get("auto_sync", False))
    )
    effective_auto_sync = bool(repo_sync_enabled and raw_auto_sync)

    poll_interval_sec = float(
        repo_sync_dict.get(
            "poll_interval_sec", raw_cfg.get("poll_interval_sec", 30.0)
        )
    )
    pull_delete_default = bool(
        repo_sync_dict.get(
            "pull_delete_default", raw_cfg.get("pull_delete_default", False)
        )
    )
    push_delete_default = bool(
        repo_sync_dict.get(
            "push_delete_default", raw_cfg.get("push_delete_default", False)
        )
    )

    return GDriveConfig(
        root_folder_id=str(raw_cfg.get("root_folder_id") or "").strip(),
        repo_sync_enabled=repo_sync_enabled,
        repo_sync_root=repo_sync_root,
        active_branch=active_branch,
        auto_sync=effective_auto_sync,
        poll_interval_sec=poll_interval_sec,
        pull_delete_default=pull_delete_default,
        push_delete_default=push_delete_default,
        auth_mode=str(raw_cfg.get("auth_mode") or "oauth_user").strip(),
        credentials_uri=str(
            raw_cfg.get("credentials_uri")
            or "config.local://gdrive-support/credentials.json"
        ).strip(),
        token_uri=str(
            raw_cfg.get("token_uri") or "config.local://gdrive-support/token.json"
        ).strip(),
        sandbox_dir=str(raw_cfg.get("sandbox_dir") or "").strip(),
        sync_spaces=compiled_spaces if repo_sync_enabled else (),
    )


def collect_space_local_files(
    spec: SyncSpaceSpec,
    project_root: Optional[Path] = None,
    file_space_manager: Optional[Any] = None,
) -> Dict[str, Path]:
    """
    Enumerate files in the target file-space, normalize each path via abs_path.relative_to(project_root)
    to eliminate single-root inc_root stripping, and return a dict of {remote_rel_path: abs_local_path}.
    """
    with_stat = collect_space_local_files_with_stat(
        spec,
        project_root=project_root,
        file_space_manager=file_space_manager,
    )
    return {remote_rel: abs_p for remote_rel, (abs_p, _mtime, _sz) in with_stat.items()}


def collect_space_local_files_with_stat(
    spec: SyncSpaceSpec,
    project_root: Optional[Path] = None,
    file_space_manager: Optional[Any] = None,
) -> Dict[str, Tuple[Path, Optional[int], Optional[int]]]:
    """
    Enumerate files in the target space along with pre-collected (mtime_ns, size) metadata
    when supported by SpaceRegistry or the space manager, avoiding per-file Path.resolve() and redundant stat() calls.
    Returns a dict of {remote_rel_path: (abs_local_path, mtime_ns, size)}.
    """
    proj_root = _resolve_project_root(project_root)
    if file_space_manager is None:
        from core.space import SpaceRegistry

        file_space_manager = SpaceRegistry(project_root=proj_root)

    mapped_files: Dict[str, Tuple[Path, Optional[int], Optional[int]]] = {}
    raw_items: List[Tuple[Path, Optional[int], Optional[int]]] = []
    if hasattr(file_space_manager, "iter_space_files_with_stat"):
        for _rel_p, abs_path, _src_root, mtime_ns, _ctime_ns, size in file_space_manager.iter_space_files_with_stat(
            spec.space
        ):
            raw_items.append((Path(abs_path), int(mtime_ns), int(size)))
    else:
        for item in file_space_manager.iter_space_files(spec.space):
            if hasattr(item, "abs_path"):
                m_ns = getattr(item, "mtime_ns", None)
                sz = getattr(item, "size", None)
                raw_items.append(
                    (
                        item.abs_path if isinstance(item.abs_path, Path) else Path(item.abs_path),
                        int(m_ns) if m_ns is not None else None,
                        int(sz) if sz is not None else None,
                    )
                )
            else:
                _rel_p, abs_path, _src_root = item[0], item[1], item[2]
                raw_items.append(
                    (abs_path if isinstance(abs_path, Path) else Path(abs_path), None, None)
                )

    for abs_path, mtime_ns, size in raw_items:
        local_abs = abs_path if isinstance(abs_path, Path) else Path(abs_path)
        if is_sensitive_credential_path(local_abs, proj_root):
            continue
        try:
            proj_rel = local_abs.relative_to(proj_root).as_posix()
        except ValueError:
            try:
                local_abs = local_abs.resolve()
                proj_rel = local_abs.relative_to(proj_root).as_posix()
            except ValueError:
                continue
        remote_rel = spec.local_to_remote_rel(proj_rel)
        if remote_rel is None or not remote_rel:
            continue
        mapped_files[remote_rel] = (local_abs, mtime_ns, size)
    return mapped_files

