"""
Deprecated data models and schema contracts for the file-space module.
Delegates directly to core.space data structures.
"""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.space import (
    FileFingerprint,
    HashPolicy,
    RuleItem,
    ScanDiffDetail,
    ScanDiffResult,
    SnapshotState,
    SpaceConfig,
    SpaceFileEntry,
)
from .exceptions import InvalidFileSpaceConfigError


class FileSpaceOrigin(str, Enum):
    """Origin classification for a registered workspace."""

    MODULE = "module"
    PROJECT = "project"
    MERGED = "merged"
    EPHEMERAL = "ephemeral"


@dataclass
class FileSpaceConfig:
    """
    Compatibility wrapper representing a workspace configuration backed by core.space.SpaceConfig.
    """

    name: str
    include: List[Any] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    file_patterns: List[str] = field(default_factory=list)
    description: str = ""
    hash_policy: Union[HashPolicy, str] = HashPolicy.ADAPTIVE
    large_file_threshold_mb: int = 10
    follow_symlinks: bool = False
    watch: bool = True
    weight: float = 1.0
    origin: Union[FileSpaceOrigin, str] = FileSpaceOrigin.PROJECT
    owner_modules: List[str] = field(default_factory=list)
    raw_include_uris: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.hash_policy, str):
            try:
                self.hash_policy = HashPolicy(self.hash_policy)
            except ValueError as exc:
                raise InvalidFileSpaceConfigError(
                    f"Invalid hash_policy '{self.hash_policy}' for space '{self.name}'"
                ) from exc
        if isinstance(self.origin, str) and not isinstance(self.origin, FileSpaceOrigin):
            try:
                self.origin = FileSpaceOrigin(self.origin)
            except ValueError:
                self.origin = FileSpaceOrigin.PROJECT

        try:
            if isinstance(self.large_file_threshold_mb, bool):
                raise TypeError("boolean is not a valid threshold")
            self.large_file_threshold_mb = int(self.large_file_threshold_mb)
        except (TypeError, ValueError) as exc:
            raise InvalidFileSpaceConfigError(
                f"Invalid large_file_threshold_mb '{self.large_file_threshold_mb}' for space '{self.name}'"
            ) from exc
        if self.large_file_threshold_mb <= 0:
            raise InvalidFileSpaceConfigError(
                f"Space '{self.name}' large_file_threshold_mb must be positive, got {self.large_file_threshold_mb}."
            )

        try:
            if isinstance(self.weight, bool):
                raise TypeError("boolean is not a valid weight")
            self.weight = float(self.weight)
        except (TypeError, ValueError) as exc:
            raise InvalidFileSpaceConfigError(
                f"Invalid weight '{self.weight}' for space '{self.name}'"
            ) from exc

        if not self.raw_include_uris and self.include:
            self.raw_include_uris = [str(p) for p in self.include]

    @property
    def origin_display(self) -> str:
        """Return provider origin label."""
        owners = [str(o) for o in self.owner_modules if o]
        if self.origin == FileSpaceOrigin.MERGED or len(owners) > 1:
            return f"merged({', '.join(owners)})"
        if len(owners) == 1:
            return f"origin({owners[0]})"
        origin_val = (
            self.origin.value
            if isinstance(self.origin, FileSpaceOrigin)
            else str(self.origin)
        )
        return f"origin({origin_val})"

    @property
    def resolved_include_paths(self) -> List[Path]:
        """Return include entries normalized as Path objects."""
        return [
            item if isinstance(item, Path) else Path(str(item))
            for item in self.include
        ]

    @classmethod
    def from_space_config(
        cls,
        space_cfg: SpaceConfig,
        project_root: Optional[Path] = None,
    ) -> "FileSpaceConfig":
        """Adapt a core.space.SpaceConfig instance into FileSpaceConfig."""
        resolved_entries = space_cfg.resolve_entries(project_root)
        inc_paths = [
            res_p if res_p is not None else Path(raw_e)
            for raw_e, res_p, _exists in resolved_entries
        ]
        if getattr(space_cfg, "is_ephemeral", False) or space_cfg.owner in ("__unknown__", "ephemeral"):
            origin = FileSpaceOrigin.EPHEMERAL
        elif space_cfg.owner == "project":
            origin = FileSpaceOrigin.PROJECT
        else:
            origin = FileSpaceOrigin.MODULE
        return cls(
            name=space_cfg.short_name,
            include=inc_paths,
            raw_include_uris=list(space_cfg.entries),
            exclude=list(space_cfg.exclude),
            file_patterns=list(space_cfg.include),
            description=space_cfg.description,
            hash_policy=space_cfg.hash_policy,
            large_file_threshold_mb=space_cfg.large_file_threshold_mb,
            follow_symlinks=space_cfg.follow_symlinks,
            watch=space_cfg.watch,
            origin=origin,
            owner_modules=[space_cfg.owner],
        )

    def is_file_included(self, rel_path: str) -> bool:
        """Return True if rel_path matches file_patterns and is not excluded."""
        import fnmatch

        norm_p = str(rel_path).replace("\\", "/").strip("/")
        parts = [p for p in norm_p.split("/") if p]
        fname = parts[-1] if parts else norm_p
        for exc in self.exclude:
            clean_exc = str(exc).replace("\\", "/").strip("/")
            if (
                clean_exc in parts
                or fnmatch.fnmatch(norm_p, clean_exc)
                or fnmatch.fnmatch(fname, clean_exc)
            ):
                return False
        if not self.file_patterns:
            return True
        for pat in self.file_patterns:
            clean_pat = str(pat).replace("\\", "/").strip("/")
            if clean_pat in ("*", "**", "**/*") or fnmatch.fnmatch(norm_p, clean_pat) or fnmatch.fnmatch(fname, clean_pat):
                return True
        return False

    def is_dir_excluded(self, dir_name: str, rel_dir: str = "") -> bool:
        """Return True if directory name or relative directory path is excluded."""
        import fnmatch

        norm_name = str(dir_name).replace("\\", "/").strip("/")
        norm_rel = str(rel_dir or dir_name).replace("\\", "/").strip("/")
        for exc in self.exclude:
            clean_exc = str(exc).replace("\\", "/").strip("/")
            if (
                norm_name == clean_exc
                or norm_rel == clean_exc
                or fnmatch.fnmatch(norm_name, clean_exc)
                or fnmatch.fnmatch(norm_rel, clean_exc)
            ):
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize FileSpaceConfig into a plain dictionary."""
        return {
            "name": self.name,
            "include": [
                p.as_posix() if isinstance(p, Path) else str(p) for p in self.include
            ],
            "raw_include_uris": list(self.raw_include_uris),
            "exclude": list(self.exclude),
            "file_patterns": list(self.file_patterns),
            "description": self.description,
            "hash_policy": (
                self.hash_policy.value
                if isinstance(self.hash_policy, HashPolicy)
                else str(self.hash_policy)
            ),
            "large_file_threshold_mb": int(self.large_file_threshold_mb),
            "follow_symlinks": bool(self.follow_symlinks),
            "watch": bool(self.watch),
            "weight": float(self.weight),
            "origin": (
                self.origin.value
                if isinstance(self.origin, FileSpaceOrigin)
                else str(self.origin)
            ),
            "owner_modules": list(self.owner_modules),
        }

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "FileSpaceConfig":
        """Construct FileSpaceConfig from a dictionary definition."""
        raw_inc = list(
            data.get(
                "raw_include_uris",
                data.get("entries", data.get("include", [])),
            )
        )
        inc = [
            Path(p) if isinstance(p, Path) else p
            for p in data.get("entries", data.get("include", []))
        ]
        return cls(
            name=name,
            include=inc,
            exclude=list(data.get("exclude", [])),
            file_patterns=list(data.get("file_patterns", data.get("include_patterns", []))),
            description=str(data.get("description", "")),
            hash_policy=data.get("hash_policy", HashPolicy.ADAPTIVE),
            large_file_threshold_mb=data.get("large_file_threshold_mb", 10),
            follow_symlinks=bool(data.get("follow_symlinks", False)),
            watch=bool(data.get("watch", True)),
            weight=data.get("weight", 1.0),
            origin=data.get("origin", FileSpaceOrigin.PROJECT),
            owner_modules=list(data.get("owner_modules", [])),
            raw_include_uris=[str(u) for u in raw_inc],
        )


__all__ = [
    "FileFingerprint",
    "FileSpaceConfig",
    "FileSpaceOrigin",
    "HashPolicy",
    "RuleItem",
    "ScanDiffDetail",
    "ScanDiffResult",
    "SnapshotState",
    "SpaceConfig",
    "SpaceFileEntry",
]
