"""
Server Module - Debounced IO Streamer.

Compatibility facade re-exporting `DebouncedIOStreamer` and `_StreamProxy` from `core.log`.
"""

from core.log import DebouncedIOStreamer, _StreamProxy

__all__ = [
    "DebouncedIOStreamer",
    "_StreamProxy",
]
