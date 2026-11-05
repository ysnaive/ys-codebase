"""
FileSpaceManager: Dual-track workspace aggregation, path resolution, and file iteration.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple, Union

from .exceptions import InvalidFileSpaceConfigError, FileSpaceNotFoundError
from .schema import HashPolicy, FileSpaceConfig, FileSpaceOrigin

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


def _dedup_preserve_order(items: List[Any]) -> List[Any]:
    seen: Set[str] = set()
    result: List[Any] = []
    for item in items:
        key = item.as_posix() if isinstance(item, Path) else str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


class FileSpaceManager:
    """
    Central workspace registry and path resolution engine.

    Supports dual-track space discovery:
    1. Module Contributed: loaded from installed modules' contributes/file-space.json.
    2. Project Override: loaded from host config://file-space/contribute.json.
    3. Ephemeral Spaces: registered at runtime in memory for sandbox testing.
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
    ) -> None:
        self.core_context = core_context
        self._explicit_project_root = (
            Path(project_root).resolve() if project_root else None
        )
        effective_storage = storage_root if storage_root is not None else storage_dir
        self._explicit_storage_root = (
            Path(effective_storage).resolve() if effective_storage else None
        )
        self._custom_config_dir = (
            Path(config_dir).resolve() if config_dir else None
        )
        self._explicit_spaces_config = spaces_config
        if contributed_spaces is not None:
            self._explicit_contributed_spaces = contributed_spaces
        elif isinstance(contributes_data, dict):
            self._explicit_contributed_spaces = contributes_data.get(
                "spaces", contributes_data
            )
        else:
            self._explicit_contributed_spaces = None
        self._uri_resolver = uri_resolver
        self._cached_project_root: Optional[Path] = (
            self._explicit_project_root
        )
        self._spaces: Dict[str, FileSpaceConfig] = {}
        self._ephemeral_spaces: Dict[str, FileSpaceConfig] = {}
        self._loaded = False
        self.load_spaces()

    @property
    def project_root(self) -> Path:
        """Resolve and return the host workspace root directory."""
        if self._cached_project_root is not None:
            return self._cached_project_root
        if self._explicit_project_root is not None:
            self._cached_project_root = self._explicit_project_root
            return self._cached_project_root
        resolved = self._resolve_uri("project://")
        if resolved is not None:
            if resolved.name == "ys_codebase" and (resolved.parent / "ys_codebase").is_dir():
                self._cached_project_root = resolved.parent.resolve()
            else:
                self._cached_project_root = resolved.resolve()
            return self._cached_project_root
        cwd = Path.cwd().resolve()
        if cwd.name == "ys_codebase":
            self._cached_project_root = cwd.parent
        else:
            self._cached_project_root = cwd
        return self._cached_project_root

    @property
    def storage_root(self) -> Path:
        """Resolve and return the storage directory for snapshots and cursors."""
        if self._explicit_storage_root is not None:
            self._explicit_storage_root.mkdir(parents=True, exist_ok=True)
            return self._explicit_storage_root
        resolved = self._resolve_uri("file-space.storage://") or self._resolve_uri(
            "storage.local://file-space/"
        )
        if resolved is not None:
            resolved.mkdir(parents=True, exist_ok=True)
            return resolved.resolve()
        fallback = self.project_root / "ys_codebase" / ".storage.local" / "file-space"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    def _resolve_uri(self, uri_or_path: Union[str, Path]) -> Optional[Path]:
        if isinstance(uri_or_path, Path):
            if uri_or_path.is_absolute():
                return uri_or_path.resolve()
            return (self.project_root / uri_or_path).resolve()

        raw = str(uri_or_path).strip()
        if not raw:
            return None

        if self._uri_resolver is not None:
            try:
                res = self._uri_resolver(raw)
                if res:
                    return Path(res).resolve()
            except Exception:
                pass

        if "://" in raw:
            try:
                from core import uri as core_uri

                res = core_uri.resolve(raw)
                if res:
                    return Path(res).resolve()
            except Exception:
                return None

        p = Path(raw)
        if p.is_absolute():
            return p.resolve()
        base = (
            self._explicit_project_root
            if self._explicit_project_root is not None
            else Path.cwd().resolve()
        )
        return (base / p).resolve()

    def _normalize_include_entries(
        self, raw_includes: List[Any]
    ) -> Tuple[List[Path], List[str]]:
        resolved_paths: List[Path] = []
        raw_uris: List[str] = []
        seen_paths: Set[str] = set()

        for entry in raw_includes:
            raw_str = entry.as_posix() if isinstance(entry, Path) else str(entry).strip()
            if not raw_str:
                continue
            raw_uris.append(raw_str)
            resolved = self._resolve_uri(entry)
            if resolved is not None:
                key = resolved.as_posix()
                if key not in seen_paths:
                    seen_paths.add(key)
                    resolved_paths.append(resolved)
        return resolved_paths, _dedup_preserve_order(raw_uris)

    @property
    def storage_dir(self) -> Path:
        """Backward-compatible alias for storage_root."""
        return self.storage_root

    def _discover_module_contributed_spaces(self) -> Dict[str, Dict[str, Any]]:
        if self._explicit_contributed_spaces is not None:
            return self._explicit_contributed_spaces

        aggregated: Dict[str, Dict[str, Any]] = {}
        try:
            from core import contributes as core_contributes

            data = core_contributes.get("file-space")
            spaces_map = data.get("spaces", {}) if isinstance(data, dict) else {}
            if isinstance(spaces_map, dict):
                for s_name, s_cfg in spaces_map.items():
                    if not isinstance(s_cfg, dict):
                        continue
                    providers_raw = s_cfg.get("__providers__")
                    if isinstance(providers_raw, list) and providers_raw:
                        donors = [str(p) for p in providers_raw]
                    elif "__provider__" in s_cfg:
                        donors = [str(s_cfg["__provider__"])]
                    elif isinstance(s_cfg.get("owner_modules"), list) and s_cfg["owner_modules"]:
                        donors = [str(p) for p in s_cfg["owner_modules"]]
                    else:
                        donors = ["module"]

                    if s_name not in aggregated:
                        copied = dict(s_cfg)
                        copied["include"] = list(s_cfg.get("include", []))
                        copied["exclude"] = list(
                            s_cfg.get("exclude", DEFAULT_EXCLUDES)
                        )
                        copied["file_patterns"] = list(
                            s_cfg.get("file_patterns", DEFAULT_FILE_PATTERNS)
                        )
                        copied["owner_modules"] = _dedup_preserve_order(donors)
                        aggregated[s_name] = copied
                    else:
                        existing = aggregated[s_name]
                        existing["include"] = _dedup_preserve_order(
                            existing.get("include", [])
                            + list(s_cfg.get("include", []))
                        )
                        if "exclude" in s_cfg:
                            existing["exclude"] = _dedup_preserve_order(
                                existing.get("exclude", [])
                                + list(s_cfg.get("exclude", []))
                            )
                        if "file_patterns" in s_cfg:
                            existing["file_patterns"] = _dedup_preserve_order(
                                existing.get("file_patterns", [])
                                + list(s_cfg.get("file_patterns", []))
                            )
                        owners = existing.setdefault("owner_modules", [])
                        for d in donors:
                            if d not in owners:
                                owners.append(d)
                        for scalar_key in (
                            "description",
                            "hash_policy",
                            "large_file_threshold_mb",
                            "follow_symlinks",
                            "watch",
                            "weight",
                        ):
                            if scalar_key in s_cfg and not existing.get(scalar_key):
                                existing[scalar_key] = s_cfg[scalar_key]
        except Exception:
            pass

        return aggregated

    def _discover_project_spaces(self) -> Dict[str, Dict[str, Any]]:
        if self._explicit_spaces_config is not None:
            return self._explicit_spaces_config

        if self._custom_config_dir is not None:
            cfg_path = self._custom_config_dir / "contribute.json"
        else:
            cfg_path = self._resolve_uri("config://file-space/contribute.json")

        project_spaces: Dict[str, Dict[str, Any]] = {}
        if cfg_path is not None and cfg_path.is_file():
            try:
                payload = json.loads(cfg_path.read_text(encoding="utf-8"))
                spaces_dict = payload.get("spaces", {})
                if isinstance(spaces_dict, dict):
                    for s_name, s_cfg in spaces_dict.items():
                        if isinstance(s_cfg, dict) and s_name not in project_spaces:
                            project_spaces[s_name] = dict(s_cfg)
            except Exception:
                pass
        return project_spaces

    def _build_space_config(
        self,
        name: str,
        raw_cfg: Dict[str, Any],
        origin: FileSpaceOrigin,
        owner_modules: Optional[List[str]] = None,
    ) -> FileSpaceConfig:
        raw_includes = list(raw_cfg.get("include", []))
        if not raw_includes:
            raise InvalidFileSpaceConfigError(
                f"Space '{name}' must define a non-empty 'include' list."
            )
        resolved_paths, raw_uris = self._normalize_include_entries(raw_includes)
        excludes = _dedup_preserve_order(
            list(raw_cfg.get("exclude", DEFAULT_EXCLUDES))
        )
        file_patterns = _dedup_preserve_order(
            list(raw_cfg.get("file_patterns", DEFAULT_FILE_PATTERNS))
        )
        hash_policy_val = raw_cfg.get("hash_policy", HashPolicy.ADAPTIVE)
        threshold_mb = int(raw_cfg.get("large_file_threshold_mb", 10))
        if threshold_mb <= 0:
            raise InvalidFileSpaceConfigError(
                f"Space '{name}' large_file_threshold_mb must be positive, got {threshold_mb}."
            )

        return FileSpaceConfig(
            name=name,
            include=resolved_paths,
            raw_include_uris=raw_uris,
            exclude=excludes,
            file_patterns=file_patterns,
            description=str(raw_cfg.get("description", "")),
            hash_policy=hash_policy_val,
            large_file_threshold_mb=threshold_mb,
            follow_symlinks=bool(raw_cfg.get("follow_symlinks", False)),
            watch=bool(raw_cfg.get("watch", True)),
            weight=float(raw_cfg.get("weight", 1.0)),
            origin=origin,
            owner_modules=list(
                owner_modules
                if owner_modules is not None
                else raw_cfg.get("owner_modules", [])
            ),
        )

    def _load_contributed_space_configs(
        self, merged_spaces: Dict[str, FileSpaceConfig]
    ) -> None:
        contributed = self._discover_module_contributed_spaces()
        for name, cfg in contributed.items():
            raw_owners = cfg.get("owner_modules")
            if isinstance(raw_owners, list) and raw_owners:
                owners = _dedup_preserve_order([str(o) for o in raw_owners])
            elif isinstance(cfg.get("__providers__"), list) and cfg["__providers__"]:
                owners = _dedup_preserve_order([str(o) for o in cfg["__providers__"]])
            elif "__provider__" in cfg:
                owners = [str(cfg["__provider__"])]
            else:
                owners = ["module"]

            if owners == ["project"]:
                origin = FileSpaceOrigin.PROJECT
            elif "project" in owners:
                origin = FileSpaceOrigin.MERGED
            else:
                origin = FileSpaceOrigin.MODULE

            merged_spaces[name] = self._build_space_config(
                name=name,
                raw_cfg=cfg,
                origin=origin,
                owner_modules=owners,
            )

    def _merge_project_space_override(
        self, name: str, base: FileSpaceConfig, p_cfg: Dict[str, Any]
    ) -> FileSpaceConfig:
        override_mode = str(p_cfg.get("override_mode", "merge")).strip().lower()
        is_replace = override_mode == "replace"

        if is_replace and "include" in p_cfg:
            combined_raw_includes = _dedup_preserve_order(
                list(p_cfg.get("include", []))
            )
        else:
            combined_raw_includes = _dedup_preserve_order(
                list(base.raw_include_uris) + list(p_cfg.get("include", []))
            )
        resolved_paths, raw_uris = self._normalize_include_entries(
            combined_raw_includes
        )
        if "exclude" in p_cfg:
            combined_excludes = (
                _dedup_preserve_order(list(p_cfg["exclude"]))
                if is_replace
                else _dedup_preserve_order(
                    list(base.exclude) + list(p_cfg["exclude"])
                )
            )
        else:
            combined_excludes = list(base.exclude)

        if "file_patterns" in p_cfg:
            combined_patterns = (
                _dedup_preserve_order(list(p_cfg["file_patterns"]))
                if is_replace
                else _dedup_preserve_order(
                    list(base.file_patterns) + list(p_cfg["file_patterns"])
                )
            )
        else:
            combined_patterns = list(base.file_patterns)

        owners = _dedup_preserve_order(list(base.owner_modules) + ["project"])
        return FileSpaceConfig(
            name=name,
            include=resolved_paths,
            raw_include_uris=raw_uris,
            exclude=combined_excludes,
            file_patterns=combined_patterns,
            description=str(p_cfg.get("description", base.description)),
            hash_policy=p_cfg.get("hash_policy", base.hash_policy),
            large_file_threshold_mb=int(
                p_cfg.get(
                    "large_file_threshold_mb", base.large_file_threshold_mb
                )
            ),
            follow_symlinks=bool(
                p_cfg.get("follow_symlinks", base.follow_symlinks)
            ),
            watch=bool(p_cfg.get("watch", base.watch)),
            weight=float(p_cfg.get("weight", base.weight)),
            origin=FileSpaceOrigin.MERGED,
            owner_modules=owners,
        )

    def _apply_project_space_overrides(
        self, merged_spaces: Dict[str, FileSpaceConfig]
    ) -> None:
        has_explicit_project_override = (
            self._explicit_spaces_config is not None
            or self._custom_config_dir is not None
            or self._explicit_contributed_spaces is not None
        )
        project_cfgs = self._discover_project_spaces()
        for name, p_cfg in project_cfgs.items():
            if name not in merged_spaces:
                merged_spaces[name] = self._build_space_config(
                    name=name,
                    raw_cfg=p_cfg,
                    origin=FileSpaceOrigin.PROJECT,
                    owner_modules=["project"],
                )
            elif (
                has_explicit_project_override
                or str(p_cfg.get("override_mode", "")).strip().lower() == "replace"
            ):
                merged_spaces[name] = self._merge_project_space_override(
                    name, merged_spaces[name], p_cfg
                )

    def _synthesize_default_source_space(self) -> FileSpaceConfig:
        p_root = self.project_root
        return FileSpaceConfig(
            name="source",
            include=[p_root],
            raw_include_uris=[p_root.as_posix()],
            exclude=list(DEFAULT_EXCLUDES),
            file_patterns=list(DEFAULT_FILE_PATTERNS),
            description="Default project workspace",
            hash_policy=HashPolicy.ADAPTIVE,
            large_file_threshold_mb=10,
            follow_symlinks=False,
            watch=True,
            weight=1.0,
            origin=FileSpaceOrigin.PROJECT,
            owner_modules=["project"],
        )

    def load_spaces(self, force: bool = False) -> Dict[str, FileSpaceConfig]:
        """
        Load and merge all module-contributed, project-configured, and ephemeral spaces.
        When already loaded and `force=False`, returns a shallow copy of the cached map.
        """
        if self._loaded and not force:
            return dict(self._spaces)

        merged_spaces: Dict[str, FileSpaceConfig] = {}
        self._load_contributed_space_configs(merged_spaces)
        self._apply_project_space_overrides(merged_spaces)

        if (
            not merged_spaces
            and self._explicit_spaces_config is None
            and self._explicit_contributed_spaces is None
        ):
            merged_spaces["source"] = self._synthesize_default_source_space()

        for e_name, e_cfg in self._ephemeral_spaces.items():
            merged_spaces[e_name] = e_cfg

        self._spaces = merged_spaces
        self._loaded = True
        return dict(self._spaces)

    def define_ephemeral_space(
        self, name: str, config: Union[FileSpaceConfig, Dict[str, Any]]
    ) -> FileSpaceConfig:
        """
        Register an in-memory ephemeral workspace for runtime or sandbox isolation.
        """
        if isinstance(config, FileSpaceConfig):
            resolved_paths, raw_uris = self._normalize_include_entries(
                list(config.include)
            )
            space_cfg = FileSpaceConfig(
                name=name,
                include=resolved_paths,
                raw_include_uris=raw_uris,
                exclude=list(config.exclude or DEFAULT_EXCLUDES),
                file_patterns=list(config.file_patterns or DEFAULT_FILE_PATTERNS),
                description=config.description,
                hash_policy=config.hash_policy,
                large_file_threshold_mb=config.large_file_threshold_mb,
                follow_symlinks=config.follow_symlinks,
                watch=config.watch,
                weight=config.weight,
                origin=FileSpaceOrigin.EPHEMERAL,
                owner_modules=["ephemeral"],
            )
        elif isinstance(config, dict):
            space_cfg = self._build_space_config(
                name=name,
                raw_cfg=config,
                origin=FileSpaceOrigin.EPHEMERAL,
                owner_modules=["ephemeral"],
            )
        else:
            raise InvalidFileSpaceConfigError(
                f"Expected FileSpaceConfig or dict for ephemeral space '{name}'."
            )

        self._ephemeral_spaces[name] = space_cfg
        self._spaces[name] = space_cfg
        return space_cfg

    def list_spaces(self) -> List[str]:
        """Return all registered workspace names in deterministic order."""
        if not self._loaded:
            self.load_spaces()
        return list(self._spaces.keys())

    def get_all_spaces(self) -> Dict[str, FileSpaceConfig]:
        """Return a mapping of all registered workspace names to FileSpaceConfig."""
        if not self._loaded:
            self.load_spaces()
        return dict(self._spaces)

    def get_space(self, name: str) -> FileSpaceConfig:
        """Return the FileSpaceConfig for the specified workspace or raise FileSpaceNotFoundError."""
        if not self._loaded:
            self.load_spaces()
        if name not in self._spaces:
            raise FileSpaceNotFoundError(
                f"Workspace '{name}' is not registered. Available spaces: {list(self._spaces.keys())}"
            )
        return self._spaces[name]

    def resolve_space_include(self, name: str) -> List[Path]:
        """Return existing directory paths for a workspace's include roots."""
        cfg = self.get_space(name)
        valid_dirs: List[Path] = []
        for inc_path in cfg.resolved_include_paths:
            if inc_path.exists() and inc_path.is_dir():
                valid_dirs.append(inc_path.resolve())
        return valid_dirs

    def compute_config_hash(self, space_name: Optional[str] = None) -> str:
        """Compute a deterministic digest of workspace geometry and filter rules."""
        if space_name is not None:
            cfg = self.get_space(space_name)
            payload = {
                "name": cfg.name,
                "include": sorted(p.as_posix() for p in cfg.resolved_include_paths),
                "exclude": sorted(cfg.exclude),
                "file_patterns": sorted(cfg.file_patterns),
                "hash_policy": (
                    cfg.hash_policy.value
                    if isinstance(cfg.hash_policy, HashPolicy)
                    else str(cfg.hash_policy)
                ),
                "large_file_threshold_mb": cfg.large_file_threshold_mb,
                "follow_symlinks": cfg.follow_symlinks,
            }
        else:
            payload = {
                name: {
                    "include": sorted(
                        p.as_posix() for p in cfg.resolved_include_paths
                    ),
                    "exclude": sorted(cfg.exclude),
                    "file_patterns": sorted(cfg.file_patterns),
                    "hash_policy": (
                        cfg.hash_policy.value
                        if isinstance(cfg.hash_policy, HashPolicy)
                        else str(cfg.hash_policy)
                    ),
                    "large_file_threshold_mb": cfg.large_file_threshold_mb,
                    "follow_symlinks": cfg.follow_symlinks,
                }
                for name, cfg in sorted(self.get_all_spaces().items())
            }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.blake2b(
            serialized.encode("utf-8"), digest_size=16
        ).hexdigest()

    def file_belongs_to_space(
        self, file_path: Union[str, Path], space_cfg: Union[str, FileSpaceConfig]
    ) -> bool:
        """
        Determine whether an absolute or relative file path falls within a workspace
        and satisfies its exclude and file_patterns filters.
        """
        cfg = (
            self.get_space(space_cfg)
            if isinstance(space_cfg, str)
            else space_cfg
        )
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = (self.project_root / candidate).resolve()
        elif cfg.follow_symlinks:
            candidate = candidate.resolve()

        matched_rel: Optional[str] = None
        for inc_root in cfg.resolved_include_paths:
            if inc_root.is_file():
                if candidate == inc_root or candidate.resolve() == inc_root.resolve():
                    return True
                continue
            try:
                rel = candidate.relative_to(inc_root).as_posix()
                if rel == ".":
                    return False
                matched_rel = rel
                break
            except ValueError:
                try:
                    rel = candidate.resolve().relative_to(inc_root.resolve()).as_posix()
                    if rel == ".":
                        return False
                    matched_rel = rel
                    break
                except ValueError:
                    continue

        if matched_rel is None:
            return False

        return cfg.is_file_included(matched_rel)

    def resolve_file_path(
        self, rel_path: str, space_name: Optional[str] = None
    ) -> Optional[Path]:
        """
        Safely resolve a workspace-relative path to an existing absolute file Path.
        Rejects path traversal ('..') outside workspace include roots.
        """
        norm_rel = str(rel_path).replace("\\", "/").strip("/")
        if not norm_rel:
            return None
        posix_parts = PurePosixPath(norm_rel).parts
        if ".." in posix_parts:
            return None

        target_spaces = (
            [self.get_space(space_name)]
            if space_name is not None
            else list(self.get_all_spaces().values())
        )

        for cfg in target_spaces:
            for inc_root in cfg.resolved_include_paths:
                root_resolved = inc_root.resolve()
                candidate = (root_resolved / norm_rel).resolve()
                try:
                    candidate.relative_to(root_resolved)
                except ValueError:
                    continue
                if candidate.is_file():
                    return candidate

            proj_root = self.project_root.resolve()
            fallback_candidate = (proj_root / norm_rel).resolve()
            try:
                fallback_candidate.relative_to(proj_root)
            except ValueError:
                continue
            if fallback_candidate.is_file() and self.file_belongs_to_space(
                fallback_candidate, cfg
            ):
                return fallback_candidate

        return None

    def _compute_rel_path(
        self,
        abs_file: Path,
        inc_root: Path,
        multi_root: bool,
        proj_root: Optional[Path] = None,
    ) -> str:
        effective_proj_root = (
            proj_root if proj_root is not None else self.project_root
        )
        if not multi_root:
            try:
                return abs_file.relative_to(inc_root).as_posix()
            except ValueError:
                pass
        try:
            return abs_file.relative_to(effective_proj_root).as_posix()
        except ValueError:
            try:
                return abs_file.relative_to(inc_root).as_posix()
            except ValueError:
                return abs_file.name

    def iter_space_files(
        self, space_name: Optional[str] = None
    ) -> Iterator[Tuple[str, Path, Path]]:
        """
        Iterate over all active files in one or all workspaces.
        Yields (rel_path, abs_path, source_root) tuples in deterministic order.
        """
        for rel_p, abs_p, src_root, _mtime_ns, _ctime_ns, _size in self.iter_space_files_with_stat(
            space_name
        ):
            yield (rel_p, abs_p, src_root)

    def iter_space_files_with_stat(
        self, space_name: Optional[str] = None
    ) -> Iterator[Tuple[str, Path, Path, int, int, int]]:
        """
        Iterate over all active files in one or all workspaces, reusing DirEntry.stat() results.
        Yields (rel_path, abs_path, source_root, mtime_ns, ctime_ns, size) in deterministic order.
        """
        target_names = (
            [space_name] if space_name is not None else self.list_spaces()
        )
        seen_rel_paths: Set[str] = set()
        proj_root = self.project_root

        for s_name in target_names:
            cfg = self.get_space(s_name)
            inc_roots = self.resolve_space_include(s_name)
            multi_root = len(inc_roots) > 1
            visited_dirs: Set[Tuple[int, int]] = set()
            visited_dir_paths: Set[str] = set()
            collected: List[Tuple[str, Path, Path, int, int, int]] = []

            for inc_root in inc_roots:
                self._walk_root(
                    current_dir=inc_root,
                    inc_root=inc_root,
                    cfg=cfg,
                    multi_root=multi_root,
                    visited_dirs=visited_dirs,
                    collected=collected,
                    proj_root=proj_root,
                    visited_dir_paths=visited_dir_paths,
                    rel_dir_prefix="",
                )

            collected.sort(key=lambda item: item[0])
            for rel_p, abs_p, src_root, mtime_ns, ctime_ns, size in collected:
                dedup_key = f"{s_name}:{rel_p}" if space_name is None else rel_p
                if dedup_key not in seen_rel_paths:
                    seen_rel_paths.add(dedup_key)
                    yield (rel_p, abs_p, src_root, mtime_ns, ctime_ns, size)

    def _walk_root(
        self,
        current_dir: Path,
        inc_root: Path,
        cfg: FileSpaceConfig,
        multi_root: bool,
        visited_dirs: Set[Tuple[int, int]],
        collected: List[Any],
        proj_root: Optional[Path] = None,
        visited_dir_paths: Optional[Set[str]] = None,
        rel_dir_prefix: str = "",
    ) -> None:
        if cfg.follow_symlinks:
            try:
                dir_stat = current_dir.stat()
                dir_key = (dir_stat.st_dev, dir_stat.st_ino)
                if dir_key in visited_dirs:
                    return
                visited_dirs.add(dir_key)
            except OSError:
                return
        elif multi_root and visited_dir_paths is not None:
            norm_dir_key = current_dir.as_posix()
            if norm_dir_key in visited_dir_paths:
                return
            visited_dir_paths.add(norm_dir_key)

        try:
            with os.scandir(current_dir) as it:
                entries = list(it)
        except OSError:
            return

        for entry in entries:
            try:
                is_symlink = entry.is_symlink()
                if is_symlink and not cfg.follow_symlinks:
                    continue
                entry_name = entry.name
                rel_to_root = (
                    f"{rel_dir_prefix}/{entry_name}"
                    if rel_dir_prefix
                    else entry_name
                )

                if entry.is_dir(follow_symlinks=cfg.follow_symlinks):
                    if self._is_dir_excluded(entry_name, rel_to_root, cfg):
                        continue
                    self._walk_root(
                        current_dir=Path(entry.path),
                        inc_root=inc_root,
                        cfg=cfg,
                        multi_root=multi_root,
                        visited_dirs=visited_dirs,
                        collected=collected,
                        proj_root=proj_root,
                        visited_dir_paths=visited_dir_paths,
                        rel_dir_prefix=rel_to_root,
                    )
                elif entry.is_file(follow_symlinks=cfg.follow_symlinks):
                    if not cfg.is_file_included(rel_to_root):
                        continue
                    st = entry.stat(follow_symlinks=cfg.follow_symlinks)
                    mtime_ns = int(st.st_mtime_ns)
                    ctime_ns = int(getattr(st, "st_ctime_ns", mtime_ns))
                    size = int(st.st_size)
                    entry_path = Path(entry.path)
                    if not cfg.follow_symlinks and not multi_root:
                        rel_path = rel_to_root
                    else:
                        target_file_path = (
                            entry_path
                            if (not is_symlink and not cfg.follow_symlinks)
                            else (entry_path.resolve() if not is_symlink else entry_path)
                        )
                        rel_path = self._compute_rel_path(
                            target_file_path,
                            inc_root,
                            multi_root,
                            proj_root=proj_root,
                        )
                    collected.append(
                        (rel_path, entry_path, inc_root, mtime_ns, ctime_ns, size)
                    )
            except OSError:
                continue

    @staticmethod
    def _is_dir_excluded(
        dir_name: str,
        rel_dir_posix: str,
        exclude_patterns: Union[List[str], FileSpaceConfig],
    ) -> bool:
        if isinstance(exclude_patterns, FileSpaceConfig):
            return exclude_patterns.is_dir_excluded(dir_name, rel_dir_posix)

        import fnmatch

        for pattern in exclude_patterns:
            norm = pattern.replace("\\", "/").strip("/")
            if not norm:
                continue
            if "/" in norm:
                if fnmatch.fnmatch(rel_dir_posix, norm) or rel_dir_posix.startswith(
                    norm + "/"
                ):
                    return True
            else:
                if dir_name == norm or fnmatch.fnmatch(dir_name, norm):
                    return True
        return False
