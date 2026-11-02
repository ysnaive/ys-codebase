"""
Atomic Gzip + Pickle Binary Persistence and Dirty File Path Matching Primitives for Knowledge-DB.
Delegates to `ast_engine.io_utils` as the Single Source of Truth (SSOT).
"""

from pathlib import Path
import sys


def _ensure_ast_path() -> None:
    try:
        import ast_engine  # noqa: F401

        return
    except ImportError:
        pass
    pkg_dir = Path(__file__).resolve().parent.parent
    source_or_mod_root = pkg_dir.parent
    for cand in (
        source_or_mod_root / "ast",
        source_or_mod_root.parent / ".modules" / "ast",
    ):
        if cand.is_dir():
            cand_str = str(cand)
            if cand_str not in sys.path:
                sys.path.insert(0, cand_str)


_ensure_ast_path()

from ast_engine.io_utils import (  # noqa: E402
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
