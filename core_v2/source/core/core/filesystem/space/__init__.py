"""Domain 2.4: Unified logical file spaces, dynamic spaces, SQLite WAL incremental scanner, and .gitignore materializer."""

from core.filesystem.space.gitignore import GitignoreMaterializer
from core.filesystem.space.registry import SpaceRegistry
from core.filesystem.space.rules import (
    ConsumerCursor,
    GitignoreSyncResult,
    HashPolicy,
    SpaceDiffBatch,
    SpaceFileEntry,
    SpaceMatchExplain,
    SpaceSpec,
    SpaceStatusSnapshot,
)
from core.filesystem.space.scanner import SpaceScanner

__all__ = (
    "ConsumerCursor",
    "GitignoreMaterializer",
    "GitignoreSyncResult",
    "HashPolicy",
    "SpaceDiffBatch",
    "SpaceFileEntry",
    "SpaceMatchExplain",
    "SpaceRegistry",
    "SpaceScanner",
    "SpaceSpec",
    "SpaceStatusSnapshot",
)
