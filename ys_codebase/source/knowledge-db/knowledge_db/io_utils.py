"""
Atomic Gzip + Pickle Binary Persistence and Dirty File Path Matching Primitives for Knowledge-DB.
"""

import gzip
import os
from pathlib import Path
import pickle
import threading
from typing import Any, Union

from ast_engine.io_utils import (
    is_dirty_file_match,
    load_gzip_pickle,
    normalize_dirty_paths,
)


def atomic_save_gzip_pickle(
    target_path: Union[str, Path],
    payload: Any,
    compresslevel: int = 1,
) -> Path:
    """
    Serialize payload via pickle + gzip and atomically replace target_path,
    cleaning up any temporary `.tmp` file in the finally block if saving fails.
    """
    p = Path(target_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = p.parent / f".{p.name}.tmp.{os.getpid()}.{threading.get_ident()}"
    try:
        raw_pickle = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
        compressed = gzip.compress(raw_pickle, compresslevel=compresslevel)
        with open(tmp_path, "wb") as f:
            f.write(compressed)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(str(tmp_path), str(p))
        return p
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


__all__ = [
    "atomic_save_gzip_pickle",
    "load_gzip_pickle",
    "normalize_dirty_paths",
    "is_dirty_file_match",
]
