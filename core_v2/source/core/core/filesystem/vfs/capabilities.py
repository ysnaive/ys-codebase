"""Capability bitmasks and immutable stat value objects for the semantic virtual filesystem."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Flag, auto

from core.foundation.primitives import require_pure_bool, require_pure_int


class VfsCapabilities(Flag):
    """Bitmask flags describing semantic and physical properties of a VFS mount or path."""

    NONE = 0
    READABLE = auto()
    WRITABLE = auto()
    PERSISTENT = auto()
    GIT_TRACKED = auto()
    ENUMERABLE = auto()
    PHYSICAL_PATH = auto()


@dataclass(frozen=True, slots=True)
class VfsStat:
    """Normalized cross-platform metadata snapshot for a VFS entry."""

    exists: bool
    is_dir: bool
    is_readonly: bool
    size_bytes: int
    mtime_ns: int
    ino: int

    def __post_init__(self) -> None:
        require_pure_bool(self.exists, "VfsStat.exists")
        require_pure_bool(self.is_dir, "VfsStat.is_dir")
        require_pure_bool(self.is_readonly, "VfsStat.is_readonly")
        require_pure_int(self.size_bytes, "VfsStat.size_bytes", min_val=0, max_val=None)
        require_pure_int(self.mtime_ns, "VfsStat.mtime_ns", min_val=0, max_val=None)
        require_pure_int(self.ino, "VfsStat.ino", min_val=0, max_val=None)
