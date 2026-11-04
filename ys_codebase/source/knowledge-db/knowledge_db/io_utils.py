"""
Atomic Gzip + Pickle Binary Persistence and Dirty File Path Matching Primitives for Knowledge-DB.
Delegates to `ast_engine.io_utils` as the Single Source of Truth (SSOT).
"""

from ast_engine.io_utils import (
    atomic_save_gzip_pickle,
    is_dirty_file_match,
    load_gzip_pickle,
    normalize_dirty_paths,
)

__all__ = [
    "atomic_save_gzip_pickle",
    "load_gzip_pickle",
    "normalize_dirty_paths",
    "is_dirty_file_match",
]
