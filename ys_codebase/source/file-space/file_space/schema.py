"""
Data models and schema contracts for the file-space module.
"""
from dataclasses import dataclass, field
from enum import Enum
import fnmatch
from pathlib import Path
import re
from typing import Any, Dict, FrozenSet, List, Optional, Pattern, Set, Tuple, Union


def _compile_glob_pattern(norm_pat: str, *, allow_dir_prefix: bool = False) -> Pattern[str]:
    """
    Compile a normalized POSIX glob pattern into a regular expression.
    Supports zero-or-more directory segments for `**/` and `/**/`.
    """
    working = norm_pat
    has_leading_ds = False
    has_trailing_ds = False
    if working == "**":
        return re.compile(r"(?s:^.*\Z)")
    if working.startswith("**/"):
        has_leading_ds = True
        working = working[3:]
    if working.endswith("/**"):
        has_trailing_ds = True
        working = working[:-3]

    chunks = working.split("/**/")
    translated_chunks: List[str] = []
    for chunk in chunks:
        if not chunk:
            translated_chunks.append("")
            continue
        raw_regex = fnmatch.translate(chunk)
        # Strip fnmatch's wrapper (?s: ... )\Z or \Z to compose sub-expressions cleanly
        if raw_regex.startswith("(?s:") and raw_regex.endswith(")\\Z"):
            inner = raw_regex[4:-3]
        elif raw_regex.endswith("\\Z"):
            inner = raw_regex[:-2]
        elif raw_regex.endswith("$"):
            inner = raw_regex[:-1]
        else:
            inner = raw_regex
        translated_chunks.append(inner)

    body = r"(?:/|/.+/)".join(translated_chunks)
    prefix = r"(?:.+/)?" if has_leading_ds else ""
    if has_trailing_ds or allow_dir_prefix:
        suffix = r"(?:/.*)?"
    else:
        suffix = ""
    return re.compile(f"(?s:^{prefix}{body}{suffix}\\Z)")


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
    origin: Union[FileSpaceOrigin, str] = FileSpaceOrigin.PROJECT
    owner_modules: List[str] = field(default_factory=list)
    raw_include_uris: List[str] = field(default_factory=list)

    _exclude_exact_segments: FrozenSet[str] = field(default_factory=frozenset, init=False, repr=False, compare=False)
    _exclude_rel_exact: FrozenSet[str] = field(default_factory=frozenset, init=False, repr=False, compare=False)
    _exclude_rel_prefixes: Tuple[str, ...] = field(default_factory=tuple, init=False, repr=False, compare=False)
    _exclude_ext_suffixes: Tuple[str, ...] = field(default_factory=tuple, init=False, repr=False, compare=False)
    _exclude_seg_regexes: Tuple[Pattern[str], ...] = field(default_factory=tuple, init=False, repr=False, compare=False)
    _exclude_rel_regexes: Tuple[Pattern[str], ...] = field(default_factory=tuple, init=False, repr=False, compare=False)
    _include_all: bool = field(default=True, init=False, repr=False, compare=False)
    _include_ext_suffixes: Tuple[str, ...] = field(default_factory=tuple, init=False, repr=False, compare=False)
    _include_exact_names: FrozenSet[str] = field(default_factory=frozenset, init=False, repr=False, compare=False)
    _include_regexes: Tuple[Pattern[str], ...] = field(default_factory=tuple, init=False, repr=False, compare=False)
    _compiled_filter_sig: Optional[Tuple[Tuple[str, ...], Tuple[str, ...]]] = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        from .exceptions import InvalidFileSpaceConfigError

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
        self._compile_filter_rules()

    def _compile_filter_rules(self) -> None:
        sig = (tuple(self.exclude), tuple(self.file_patterns))
        if self._compiled_filter_sig == sig:
            return

        exact_segs: Set[str] = set()
        rel_exact: Set[str] = set()
        rel_prefixes: List[str] = []
        excl_exts: List[str] = []
        seg_regexes: List[Pattern[str]] = []
        rel_regexes: List[Pattern[str]] = []

        for pattern in self.exclude:
            norm_pat = str(pattern).replace("\\", "/").strip("/")
            if not norm_pat:
                continue
            has_wildcard = any(ch in norm_pat for ch in ("*", "?", "["))
            if "/" in norm_pat:
                if not has_wildcard:
                    rel_exact.add(norm_pat)
                    rel_prefixes.append(norm_pat + "/")
                else:
                    rel_regexes.append(
                        _compile_glob_pattern(norm_pat, allow_dir_prefix=True)
                    )
            else:
                if not has_wildcard:
                    exact_segs.add(norm_pat)
                elif norm_pat.startswith("*.") and not any(
                    ch in norm_pat[1:] for ch in ("*", "?", "[")
                ):
                    excl_exts.append(norm_pat[1:])
                else:
                    seg_regexes.append(
                        _compile_glob_pattern(norm_pat, allow_dir_prefix=False)
                    )

        self._exclude_exact_segments = frozenset(exact_segs)
        self._exclude_rel_exact = frozenset(rel_exact)
        self._exclude_rel_prefixes = tuple(rel_prefixes)
        self._exclude_ext_suffixes = tuple(excl_exts)
        self._exclude_seg_regexes = tuple(seg_regexes)
        self._exclude_rel_regexes = tuple(rel_regexes)

        if not self.file_patterns:
            self._include_all = True
            self._include_ext_suffixes = ()
            self._include_exact_names = frozenset()
            self._include_regexes = ()
        else:
            inc_all = False
            inc_exts: List[str] = []
            inc_names: Set[str] = set()
            inc_rxs: List[Pattern[str]] = []
            for raw_pat in self.file_patterns:
                pat = str(raw_pat).replace("\\", "/").strip("/")
                if not pat:
                    continue
                if pat in ("*", "**", "**/*"):
                    inc_all = True
                    break
                has_wildcard = any(ch in pat for ch in ("*", "?", "["))
                if "/" not in pat:
                    if not has_wildcard:
                        inc_names.add(pat)
                    elif pat.startswith("*.") and not any(
                        ch in pat[1:] for ch in ("*", "?", "[")
                    ):
                        inc_exts.append(pat[1:])
                    else:
                        inc_rxs.append(_compile_glob_pattern(pat, allow_dir_prefix=False))
                else:
                    inc_rxs.append(_compile_glob_pattern(pat, allow_dir_prefix=False))

            self._include_all = inc_all
            self._include_ext_suffixes = tuple(inc_exts)
            self._include_exact_names = frozenset(inc_names)
            self._include_regexes = tuple(inc_rxs)

        self._compiled_filter_sig = sig

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
        return [
            item if isinstance(item, Path) else Path(str(item))
            for item in self.include
        ]

    def _matches_exclude(self, norm_rel: str, parts: List[str]) -> bool:
        if self._exclude_exact_segments and any(
            part in self._exclude_exact_segments for part in parts
        ):
            return True
        if self._exclude_rel_exact and norm_rel in self._exclude_rel_exact:
            return True
        if self._exclude_rel_prefixes and norm_rel.startswith(self._exclude_rel_prefixes):
            return True
        if self._exclude_ext_suffixes and any(
            part.endswith(self._exclude_ext_suffixes) for part in parts
        ):
            return True
        if self._exclude_seg_regexes and any(
            rx.match(part) for rx in self._exclude_seg_regexes for part in parts
        ):
            return True
        if self._exclude_rel_regexes and any(
            rx.match(norm_rel) for rx in self._exclude_rel_regexes
        ):
            return True
        return False

    def is_dir_excluded(self, dir_name: str, rel_dir_posix: str) -> bool:
        """
        Check whether a directory segment and its workspace-relative POSIX path match any exclude rule.
        """
        if self._compiled_filter_sig != (tuple(self.exclude), tuple(self.file_patterns)):
            self._compile_filter_rules()

        norm_rel = rel_dir_posix.replace("\\", "/").strip("/")
        if not norm_rel or norm_rel == ".":
            return False

        parts = [p for p in norm_rel.split("/") if p] if norm_rel else [dir_name]
        if dir_name and dir_name not in parts:
            parts.append(dir_name)
        return self._matches_exclude(norm_rel, parts)

    def is_file_included(self, rel_path: Union[str, Path]) -> bool:
        """
        Check whether a relative path passes exclude rules and file_patterns.
        """
        if self._compiled_filter_sig != (tuple(self.exclude), tuple(self.file_patterns)):
            self._compile_filter_rules()

        posix_str = (
            rel_path.as_posix()
            if isinstance(rel_path, Path)
            else str(rel_path).replace("\\", "/")
        ).strip("/")
        if not posix_str or posix_str == ".":
            return False

        if "/" in posix_str:
            parts = [p for p in posix_str.split("/") if p and p != "."]
            if not parts:
                return False
            posix_str = "/".join(parts)
            filename = parts[-1]
        else:
            parts = [posix_str]
            filename = posix_str

        if self._matches_exclude(posix_str, parts):
            return False

        if self._include_all:
            return True
        if self._include_ext_suffixes and filename.endswith(self._include_ext_suffixes):
            return True
        if self._include_exact_names and filename in self._include_exact_names:
            return True
        if self._include_regexes and any(
            rx.match(filename) or rx.match(posix_str) for rx in self._include_regexes
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
        raw_inc = list(data.get("raw_include_uris", data.get("include", [])))
        inc = [Path(p) if isinstance(p, Path) else p for p in data.get("include", [])]
        return cls(
            name=name,
            include=inc,
            exclude=list(data.get("exclude", [])),
            file_patterns=list(data.get("file_patterns", [])),
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
        for count_attr, set_attr in (
            ("added_count", "added"),
            ("modified_count", "modified"),
            ("deleted_count", "deleted"),
            ("unchanged_count", "unchanged"),
        ):
            raw_val = getattr(self, count_attr)
            norm_val = max(0, int(raw_val)) if raw_val else len(getattr(self.detail, set_attr))
            setattr(self, count_attr, norm_val)
        self.from_generation = max(0, int(self.from_generation))
        self.to_generation = max(0, int(self.to_generation))
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
