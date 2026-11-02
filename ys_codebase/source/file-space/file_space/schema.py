"""
Data models and schema contracts for the file-space module.
"""
from dataclasses import dataclass, field
from enum import Enum
import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Set, Union


class FileSpaceOrigin(str, Enum):
    """Origin classification for a registered workspace."""

    MODULE = "module"
    PROJECT = "project"
    MERGED = "merged"
    EPHEMERAL = "ephemeral"


class HashPolicy(str, Enum):
    """Tiered content hashing strategy for Stage 2 fingerprint scanning."""

    ADAPTIVE = "adaptive"
    FULL_HASH = "full_hash"
    STAT_ONLY = "stat_only"
    LAZY_STABILIZED = "lazy_stabilized"


@dataclass
class FileSpaceConfig:
    """
    Configuration and geometry definition of a named workspace.
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
    origin: FileSpaceOrigin = FileSpaceOrigin.PROJECT
    owner_modules: List[str] = field(default_factory=list)
    raw_include_uris: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.hash_policy, str):
            try:
                self.hash_policy = HashPolicy(self.hash_policy)
            except ValueError:
                from .exceptions import InvalidFileSpaceConfigError

                raise InvalidFileSpaceConfigError(
                    f"Invalid hash_policy '{self.hash_policy}' for space '{self.name}'"
                )
        if isinstance(self.origin, str) and not isinstance(self.origin, FileSpaceOrigin):
            try:
                self.origin = FileSpaceOrigin(self.origin)
            except ValueError:
                self.origin = FileSpaceOrigin.PROJECT
        if not self.raw_include_uris and self.include:
            self.raw_include_uris = [str(p) for p in self.include]

    @property
    def origin_display(self) -> str:
        """Return provider origin label: origin(A) for single provider or merged(A, B, ...) for multiple."""
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
        result: List[Path] = []
        for item in self.include:
            if isinstance(item, Path):
                result.append(item)
            else:
                result.append(Path(str(item)))
        return result

    def is_file_included(self, rel_path: Union[str, Path]) -> bool:
        """
        Check whether a relative path passes exclude rules and file_patterns.
        """
        posix_str = (
            rel_path.as_posix()
            if isinstance(rel_path, Path)
            else str(rel_path).replace("\\", "/")
        ).strip("/")
        if not posix_str:
            return False

        parts = PurePosixPath(posix_str).parts
        filename = parts[-1]

        for pattern in self.exclude:
            norm_pat = pattern.replace("\\", "/").strip("/")
            if not norm_pat:
                continue
            if "/" in norm_pat:
                if fnmatch.fnmatch(posix_str, norm_pat) or posix_str.startswith(
                    norm_pat + "/"
                ):
                    return False
            else:
                for part in parts:
                    if part == norm_pat or fnmatch.fnmatch(part, norm_pat):
                        return False

        if not self.file_patterns:
            return True

        for pat in self.file_patterns:
            if fnmatch.fnmatch(filename, pat) or fnmatch.fnmatch(posix_str, pat):
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
        raw_inc = list(data.get("raw_include_uris", data.get("include", [])))
        inc = [Path(p) if isinstance(p, Path) else p for p in data.get("include", [])]
        return cls(
            name=name,
            include=inc,
            exclude=list(data.get("exclude", [])),
            file_patterns=list(data.get("file_patterns", [])),
            description=str(data.get("description", "")),
            hash_policy=data.get("hash_policy", HashPolicy.ADAPTIVE),
            large_file_threshold_mb=int(data.get("large_file_threshold_mb", 10)),
            follow_symlinks=bool(data.get("follow_symlinks", False)),
            watch=bool(data.get("watch", True)),
            weight=float(data.get("weight", 1.0)),
            origin=FileSpaceOrigin(data.get("origin", FileSpaceOrigin.PROJECT.value)),
            owner_modules=list(data.get("owner_modules", [])),
            raw_include_uris=[str(u) for u in raw_inc],
        )


@dataclass
class FileFingerprint:
    """
    Monotonic generation file fingerprint record stored in YFP2 snapshots.
    """

    path: str = ""
    mtime_ns: int = 0
    size: int = 0
    content_hash: str = ""
    source_root: str = ""
    created_gen: int = 1
    updated_gen: int = 1
    is_deleted: bool = False
    pending_stabilization: bool = False

    def __post_init__(self) -> None:
        self.path = str(self.path or "").replace("\\", "/")
        self.mtime_ns = int(self.mtime_ns or 0)
        self.size = int(self.size)
        self.content_hash = str(self.content_hash or "")
        self.source_root = str(self.source_root)
        self.created_gen = int(self.created_gen)
        self.updated_gen = int(self.updated_gen)
        self.is_deleted = bool(self.is_deleted)
        self.pending_stabilization = bool(self.pending_stabilization)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize FileFingerprint into a dictionary."""
        return {
            "path": self.path,
            "mtime_ns": self.mtime_ns,
            "size": self.size,
            "content_hash": self.content_hash,
            "source_root": self.source_root,
            "created_gen": self.created_gen,
            "updated_gen": self.updated_gen,
            "is_deleted": self.is_deleted,
            "pending_stabilization": self.pending_stabilization,
        }


@dataclass
class ScanDiffDetail:
    """
    Detailed file path sets for an incremental scan or consumer cursor diff.
    """

    added: Set[str] = field(default_factory=set)
    modified: Set[str] = field(default_factory=set)
    deleted: Set[str] = field(default_factory=set)
    unchanged: Set[str] = field(default_factory=set)

    @property
    def dirty_files(self) -> Set[str]:
        """Set of files that were either added or modified."""
        return self.added | self.modified

    @property
    def has_changes(self) -> bool:
        """True if any file was added, modified, or deleted."""
        return bool(self.added or self.modified or self.deleted)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ScanDiffDetail into sorted lists."""
        return {
            "added": sorted(self.added),
            "modified": sorted(self.modified),
            "deleted": sorted(self.deleted),
            "unchanged": sorted(self.unchanged),
            "has_changes": self.has_changes,
        }


@dataclass
class ScanDiffResult:
    """
    Aggregated result of a workspace fingerprint scan or consumer cursor diff.
    """

    added_count: int = 0
    modified_count: int = 0
    deleted_count: int = 0
    unchanged_count: int = 0
    detail: ScanDiffDetail = field(default_factory=ScanDiffDetail)
    from_generation: int = 0
    to_generation: int = 0
    merkle_root: str = ""
    space_name: Optional[str] = None
    space_generations: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.detail is None:
            self.detail = ScanDiffDetail()
        self.added_count = int(self.added_count) if self.added_count else len(self.detail.added)
        self.modified_count = int(self.modified_count) if self.modified_count else len(self.detail.modified)
        self.deleted_count = int(self.deleted_count) if self.deleted_count else len(self.detail.deleted)
        self.unchanged_count = int(self.unchanged_count) if self.unchanged_count else len(self.detail.unchanged)
        self.from_generation = int(self.from_generation)
        self.to_generation = int(self.to_generation)
        self.merkle_root = str(self.merkle_root)
        self.space_generations = dict(self.space_generations) if self.space_generations else {}

    @property
    def added(self) -> List[str]:
        """Sorted list of added relative file paths."""
        return sorted(self.detail.added)

    @property
    def modified(self) -> List[str]:
        """Sorted list of modified relative file paths."""
        return sorted(self.detail.modified)

    @property
    def deleted(self) -> List[str]:
        """Sorted list of deleted relative file paths."""
        return sorted(self.detail.deleted)

    @property
    def unchanged(self) -> List[str]:
        """Sorted list of unchanged relative file paths."""
        return sorted(self.detail.unchanged)

    @property
    def has_changes(self) -> bool:
        """True if any file was added, modified, or deleted."""
        return (
            self.added_count > 0
            or self.modified_count > 0
            or self.deleted_count > 0
            or self.detail.has_changes
        )

    @property
    def total_changed(self) -> int:
        """Total count of added, modified, and deleted files."""
        return self.added_count + self.modified_count + self.deleted_count

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ScanDiffResult into a dictionary."""
        return {
            "space_name": self.space_name,
            "added_count": self.added_count,
            "modified_count": self.modified_count,
            "deleted_count": self.deleted_count,
            "unchanged_count": self.unchanged_count,
            "from_generation": self.from_generation,
            "to_generation": self.to_generation,
            "space_generations": dict(self.space_generations),
            "merkle_root": self.merkle_root,
            "has_changes": self.has_changes,
            "added": self.added,
            "modified": self.modified,
            "deleted": self.deleted,
            "detail": self.detail.to_dict(),
        }
