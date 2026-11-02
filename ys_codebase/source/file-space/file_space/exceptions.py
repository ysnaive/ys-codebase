"""
Exception hierarchy for the file-space module.
"""


class FileSpaceError(Exception):
    """Base exception for all file-space module errors."""


class FileSpaceNotFoundError(FileSpaceError):
    """Raised when a requested workspace is not registered."""


class InvalidFileSpaceConfigError(FileSpaceError):
    """Raised when a workspace definition violates schema or directory constraints."""


class FingerprintCorruptedError(FileSpaceError):
    """Raised when a YFP2 binary snapshot file has an invalid header or corrupted payload."""
