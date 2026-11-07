"""
Deprecated FileSpaceManager forwarding adapter.
Delegates workspace registration, path resolution, and file iteration to core.space.SpaceRegistry.
"""
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from core.space import (
    SpaceConfig,
    SpaceError,
    SpaceNotFoundError,
    SpaceRegistry,
    get_default_registry,
)
from .exceptions import FileSpaceNotFoundError, InvalidFileSpaceConfigError
from .schema import FileSpaceConfig, FileSpaceOrigin

DEFAULT_EXCLUDES: List[str] = [
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "target",
    ".idea",
    ".vscode",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dll",
    "*.dylib",
    "*.class",
    ".DS_Store",
]

DEFAULT_FILE_PATTERNS: List[str] = [
    "*.py",
    "*.md",
    "*.js",
    "*.ts",
    "*.jsx",
    "*.tsx",
    "*.json",
    "*.yaml",
    "*.yml",
    "*.toml",
    "*.rs",
    "*.go",
    "*.java",
    "*.c",
    "*.cpp",
    "*.h",
    "*.hpp",
    "*.cs",
    "*.rb",
    "*.php",
    "*.html",
    "*.css",
    "*.scss",
    "*.sql",
    "*.sh",
    "*.bat",
    "*.ps1",
]


def _convert_legacy_space_dict(raw_cfg: Dict[str, Any], default_owner: str = "project") -> Dict[str, Any]:
    """Convert legacy file-space dict (`include` + `file_patterns`) to core.space dict (`entries` + `include`)."""
    converted = dict(raw_cfg)
    if "entries" not in converted and "include" in converted:
        converted["entries"] = [
            p.as_posix() if isinstance(p, Path) else str(p)
            for p in converted.get("include", [])
        ]
        if "file_patterns" in converted:
            converted["include"] = [str(p) for p in converted.get("file_patterns", [])]
        else:
            converted["include"] = ["*"]
    elif "file_patterns" in converted and "include" not in converted:
        converted["include"] = [str(p) for p in converted.get("file_patterns", [])]
    if "owner" not in converted:
        owners = converted.get("owner_modules") or converted.get("__providers__")
        if isinstance(owners, list) and owners:
            converted["owner"] = str(owners[0])
        else:
            converted["owner"] = default_owner
    return converted


class FileSpaceManager:
    """
    Lightweight compatibility adapter delegating all operations to core.space.SpaceRegistry.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        storage_root: Optional[Path] = None,
        spaces_config: Optional[Dict[str, Dict[str, Any]]] = None,
        contributed_spaces: Optional[Dict[str, Dict[str, Any]]] = None,
        uri_resolver: Optional[Any] = None,
        *,
        core_context: Optional[Any] = None,
        config_dir: Optional[Path] = None,
        storage_dir: Optional[Path] = None,
        contributes_data: Optional[Dict[str, Any]] = None,
        registry: Optional[SpaceRegistry] = None,
    ) -> None:
        _ = (uri_resolver, config_dir)
        self.core_context = core_context
        effective_storage = storage_root if storage_root is not None else storage_dir
        self._explicit_storage_root = (
            Path(effective_storage).resolve() if effective_storage else None
        )

        raw_spaces: Optional[Dict[str, Dict[str, Any]]] = None
        self._space_weights: Dict[str, float] = {}
        if spaces_config is not None or contributed_spaces is not None or contributes_data is not None:
            raw_spaces = {}
            contrib_src = contributed_spaces
            if contrib_src is None and isinstance(contributes_data, dict):
                contrib_src = contributes_data.get("spaces", contributes_data)
            for k, v in (contrib_src or {}).items():
                if isinstance(v, dict):
                    conv = _convert_legacy_space_dict(v, default_owner="module")
                    owner_name = str(conv.get("owner") or "module")
                    q_key = k if "/" in str(k) else f"{owner_name}/{k}"
                    raw_spaces[q_key] = conv
                    short_k = str(k).split("/", 1)[-1]
                    if "weight" in v:
                        self._space_weights[q_key] = float(v["weight"])
                        self._space_weights.setdefault(short_k, float(v["weight"]))
            for k, v in (spaces_config or {}).items():
                if isinstance(v, dict):
                    conv = _convert_legacy_space_dict(v, default_owner="project")
                    owner_name = str(conv.get("owner") or "project")
                    q_key = k if "/" in str(k) else f"{owner_name}/{k}"
                    raw_spaces[q_key] = conv
                    short_k = str(k).split("/", 1)[-1]
                    if "weight" in v:
                        self._space_weights[q_key] = float(v["weight"])
                        self._space_weights[short_k] = float(v["weight"])

        try:
            if registry is not None:
                self._registry = registry
            elif raw_spaces is not None:
                self._registry = SpaceRegistry(
                    project_root=project_root,
                    raw_spaces=raw_spaces,
                )
            elif project_root is not None:
                self._registry = SpaceRegistry(project_root=project_root)
            else:
                self._registry = get_default_registry()
        except SpaceError as exc:
            raise InvalidFileSpaceConfigError(str(exc)) from exc

    @property
    def registry(self) -> SpaceRegistry:
        """Return underlying core.space.SpaceRegistry instance."""
        return self._registry

    @property
    def project_root(self) -> Path:
        """Return normalized project root Path from SpaceRegistry."""
        return self._registry.project_root

    @property
    def storage_root(self) -> Path:
        """Return storage directory for snapshots and cursors."""
        if self._explicit_storage_root is not None:
            self._explicit_storage_root.mkdir(parents=True, exist_ok=True)
            return self._explicit_storage_root
        default_dir = self._registry.yscb_dir / ".storage.local" / "core" / "space"
        default_dir.mkdir(parents=True, exist_ok=True)
        return default_dir

    @property
    def storage_dir(self) -> Path:
        """Alias for storage_root."""
        return self.storage_root

    def load_spaces(self, force: bool = False) -> Dict[str, FileSpaceConfig]:
        """Return mapping of registered workspace names to adapted FileSpaceConfig."""
        if force:
            self._registry.reload()
        result: Dict[str, FileSpaceConfig] = {}
        for s_cfg in self._registry.list_spaces():
            adapted = FileSpaceConfig.from_space_config(s_cfg, self.project_root)
            result[s_cfg.short_name] = adapted
            result[s_cfg.qualified_name] = adapted
        return result

    def list_spaces(self) -> List[str]:
        """Return registered workspace short names in deterministic order."""
        seen: List[str] = []
        for s_cfg in self._registry.list_spaces():
            if s_cfg.short_name not in seen:
                seen.append(s_cfg.short_name)
        return seen

    def get_all_spaces(self) -> Dict[str, FileSpaceConfig]:
        """Return mapping of short workspace names to FileSpaceConfig."""
        result: Dict[str, FileSpaceConfig] = {}
        for s_cfg in self._registry.list_spaces():
            result[s_cfg.short_name] = FileSpaceConfig.from_space_config(
                s_cfg, self.project_root
            )
        return result

    def _adapt_matched_spaces(self, matched: List[SpaceConfig]) -> FileSpaceConfig:
        primary = matched[-1]
        if len(matched) == 1:
            cfg = FileSpaceConfig.from_space_config(primary, self.project_root)
            w = self._space_weights.get(primary.qualified_name, self._space_weights.get(primary.short_name))
            if w is not None:
                cfg.weight = float(w)
            return cfg

        merged_inc: List[Path] = []
        merged_raw_uris: List[str] = []
        merged_exc: List[str] = []
        merged_pats: List[str] = []
        owners: List[str] = []
        for s_cfg in matched:
            if s_cfg.owner and s_cfg.owner not in owners:
                owners.append(s_cfg.owner)
            for raw_e, res_p, _exists in s_cfg.resolve_entries(self.project_root):
                p_obj = res_p if res_p is not None else Path(raw_e)
                if p_obj not in merged_inc:
                    merged_inc.append(p_obj)
                if raw_e not in merged_raw_uris:
                    merged_raw_uris.append(raw_e)
            for exc in s_cfg.exclude:
                if exc not in merged_exc:
                    merged_exc.append(exc)
            for pat in s_cfg.include:
                if pat not in merged_pats:
                    merged_pats.append(pat)

        w = self._space_weights.get(primary.qualified_name, self._space_weights.get(primary.short_name, 1.0))
        return FileSpaceConfig(
            name=primary.short_name,
            include=merged_inc,
            raw_include_uris=merged_raw_uris,
            exclude=merged_exc,
            file_patterns=merged_pats,
            description=primary.description,
            hash_policy=primary.hash_policy,
            large_file_threshold_mb=primary.large_file_threshold_mb,
            follow_symlinks=primary.follow_symlinks,
            watch=primary.watch,
            weight=float(w),
            origin=FileSpaceOrigin.MERGED if len(owners) > 1 else FileSpaceOrigin.PROJECT,
            owner_modules=owners,
        )

    def get_space(self, name: str) -> FileSpaceConfig:
        """Resolve a workspace by name and return an adapted FileSpaceConfig."""
        try:
            matched = self._registry.resolve_spaces(name)
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        if not matched:
            raise FileSpaceNotFoundError(f"Workspace '{name}' is not registered.")
        return self._adapt_matched_spaces(matched)

    def define_ephemeral_space(
        self, name: str, config: Union[FileSpaceConfig, SpaceConfig, Dict[str, Any]]
    ) -> FileSpaceConfig:
        """Register an in-memory ephemeral space via core.space.SpaceRegistry."""
        try:
            if isinstance(config, SpaceConfig):
                s_cfg = self._registry.define_ephemeral_space(name, config)
            elif isinstance(config, FileSpaceConfig):
                raw_dict = {
                    "entries": [
                        p.as_posix() if isinstance(p, Path) else str(p)
                        for p in (config.raw_include_uris or config.include)
                    ],
                    "include": list(config.file_patterns) if config.file_patterns else ["*"],
                    "exclude": list(config.exclude),
                    "description": config.description,
                    "hash_policy": config.hash_policy,
                    "large_file_threshold_mb": config.large_file_threshold_mb,
                    "follow_symlinks": config.follow_symlinks,
                    "watch": config.watch,
                }
                s_cfg = self._registry.define_ephemeral_space(name, raw_dict)
            elif isinstance(config, dict):
                s_cfg = self._registry.define_ephemeral_space(
                    name, _convert_legacy_space_dict(config, default_owner="ephemeral")
                )
            else:
                raise InvalidFileSpaceConfigError(
                    f"Expected FileSpaceConfig or dict for ephemeral space '{name}'."
                )
        except SpaceError as exc:
            raise InvalidFileSpaceConfigError(str(exc)) from exc
        return FileSpaceConfig.from_space_config(s_cfg, self.project_root)

    def resolve_space_include(self, name: str) -> List[Path]:
        """Return resolved entry paths for the specified workspace."""
        try:
            return self._registry.collect_all_entry_paths(name)
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc

    def compute_config_hash(self, space_name: Optional[str] = None) -> str:
        """Delegate config hash calculation to SpaceRegistry."""
        try:
            return self._registry.compute_config_hash(space_name)
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc

    def file_belongs_to_space(
        self, file_path: Union[str, Path], space_cfg: Union[str, FileSpaceConfig]
    ) -> bool:
        """Delegate single-path membership check to SpaceRegistry.match_path."""
        space_query = space_cfg if isinstance(space_cfg, str) else space_cfg.name
        try:
            return self._registry.match_path(file_path, space_query=space_query).matched
        except SpaceError:
            return False

    def resolve_file_path(
        self, rel_path: str, space_name: Optional[str] = None
    ) -> Optional[Path]:
        """Delegate relative path resolution to SpaceRegistry.resolve_file_path."""
        try:
            return self._registry.resolve_file_path(rel_path, space_query=space_name)
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc

    def iter_space_files(
        self, space_name: Optional[str] = None
    ) -> Iterator[Tuple[str, Path, Path]]:
        """Yield `(rel_path, abs_path, entry_path)` tuples from SpaceRegistry.iter_space_files."""
        try:
            entries = self._registry.iter_space_files(space_query=space_name)
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        for e in entries:
            rel_p = e.rel_path
            try:
                sub = e.abs_path.relative_to(e.entry_path).as_posix()
                if sub and sub != "." and not sub.startswith(".."):
                    rel_p = sub
            except ValueError:
                pass
            yield (rel_p, e.abs_path, e.entry_path)

    def iter_space_files_with_stat(
        self, space_name: Optional[str] = None
    ) -> Iterator[Tuple[str, Path, Path, int, int, int]]:
        """Yield `(rel_path, abs_path, entry_path, mtime_ns, ctime_ns, size)` tuples."""
        try:
            entries = self._registry.iter_space_files(space_query=space_name)
        except SpaceNotFoundError as exc:
            raise FileSpaceNotFoundError(str(exc)) from exc
        for e in entries:
            rel_p = e.rel_path
            try:
                sub = e.abs_path.relative_to(e.entry_path).as_posix()
                if sub and sub != "." and not sub.startswith(".."):
                    rel_p = sub
            except ValueError:
                pass
            yield (
                rel_p,
                e.abs_path,
                e.entry_path,
                e.mtime_ns,
                e.ctime_ns,
                e.size,
            )


__all__ = [
    "DEFAULT_EXCLUDES",
    "DEFAULT_FILE_PATTERNS",
    "FileSpaceManager",
]
