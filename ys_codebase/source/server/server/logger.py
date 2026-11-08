"""
Server Module - Real-time Immediate Flush Logger & Crash Recovery System.

Delegates underlying rolling log management, crash recovery, and atomic replacement
to `core.log.RollingFileLogger`.
"""

from core.log import (
    RollingFileLogger,
    _extract_log_file_timestamp,
    _safe_replace_file,
)


class ServerLogger(RollingFileLogger):
    """
    Central real-time immediate flush logger for Server daemon.
    Inherits full rolling history retention, crash recovery, and immediate flush
    guarantees from `core.log.RollingFileLogger`.
    """

    pass


__all__ = [
    "ServerLogger",
    "RollingFileLogger",
    "_extract_log_file_timestamp",
    "_safe_replace_file",
]
