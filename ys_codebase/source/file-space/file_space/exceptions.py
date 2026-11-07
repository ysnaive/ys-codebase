"""
Deprecated exception hierarchy for the file-space module.
Delegates directly to core.space.exceptions.
"""
from core.space.exceptions import (
    SpaceCycleError,
    SpaceError,
    SpaceNotFoundError,
)


class FileSpaceError(SpaceError):
    """Base exception for all file-space errors (subclasses core.space.SpaceError)."""


class FileSpaceNotFoundError(SpaceNotFoundError, FileSpaceError):
    """Raised when a requested workspace is not registered."""


class InvalidFileSpaceConfigError(FileSpaceError):
    """Raised when a workspace definition violates schema constraints."""


class FingerprintCorruptedError(FileSpaceError):
    """Raised when a YFP2 binary snapshot file has an invalid header or corrupted payload."""


__all__ = [
    "FileSpaceError",
    "FileSpaceNotFoundError",
    "FingerprintCorruptedError",
    "InvalidFileSpaceConfigError",
    "SpaceCycleError",
    "SpaceError",
    "SpaceNotFoundError",
]
