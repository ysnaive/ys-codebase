"""Domain 2.2: Capability-masked semantic virtual filesystem, mount routing, and dual-layer readonly guard."""

from core.filesystem.vfs.capabilities import VfsCapabilities, VfsStat
from core.filesystem.vfs.echo import VfsEchoGuard
from core.filesystem.vfs.mount import MountHealthEntry, MountRule, UriMountTable, build_standard_mount_rules
from core.filesystem.vfs.provider import MemoryVfsProvider, PhysicalDirectoryProvider, VfsProvider
from core.filesystem.vfs.readonly import ReadonlyPolicy, ReadonlySyncResult
from core.filesystem.vfs.scoped import AccessPolicy, KernelVfs, ScopedVfs, VfsHub

__all__: tuple[str, ...] = (
    "AccessPolicy",
    "KernelVfs",
    "MemoryVfsProvider",
    "MountHealthEntry",
    "MountRule",
    "PhysicalDirectoryProvider",
    "ReadonlyPolicy",
    "ReadonlySyncResult",
    "ScopedVfs",
    "UriMountTable",
    "VfsCapabilities",
    "VfsEchoGuard",
    "VfsHub",
    "VfsProvider",
    "VfsStat",
    "build_standard_mount_rules",
)
