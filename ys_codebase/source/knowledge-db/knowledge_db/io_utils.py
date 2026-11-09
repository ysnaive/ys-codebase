"""
Atomic Gzip + Pickle Binary Persistence and Dirty File Path Matching Primitives for Knowledge-DB.
"""

import gzip
import os
from pathlib import Path
import pickle
from typing import Any, Set, Union

from ast_engine.io_utils import (
    load_gzip_pickle,
    normalize_dirty_paths,
)
from core.vfs import write_bytes


def _is_abs_norm(path_str: str) -> bool:
    return path_str.startswith("/") or (
        len(path_str) > 2 and path_str[1] == ":" and path_str[2] == "/"
    )


def is_dirty_file_match(doc_file_path: str, dirty_paths_norm: Set[str]) -> bool:
    """
    Check whether doc_file_path matches any normalized path in dirty_paths_norm.
    Prevents cross-module relative path suffix false positives while allowing
    workspace-absolute paths to match project-relative paths.
    """
    if not dirty_paths_norm:
        return False
    sym_raw = str(doc_file_path).replace("\\", "/").lower()
    sym_is_abs = _is_abs_norm(sym_raw)
    sym_path_norm = sym_raw.strip("/")
    if not sym_path_norm:
        return False
    if (
        sym_raw in dirty_paths_norm
        or sym_path_norm in dirty_paths_norm
        or ("/" + sym_path_norm) in dirty_paths_norm
    ):
        return True
    for p in dirty_paths_norm:
        p_is_abs = _is_abs_norm(p)
        if p_is_abs and not sym_is_abs and p.endswith("/" + sym_path_norm):
            return True
        if sym_is_abs and not p_is_abs and sym_raw.endswith("/" + p.strip("/")):
            return True
    return False


def atomic_save_gzip_pickle(
    target_path: Union[str, Path],
    payload: Any,
    compresslevel: int = 1,
) -> Path:
    """
    Serialize payload via pickle + gzip and atomically persist to target_path
    via core.vfs.write_bytes(..., atomic=True) with Windows retry support.
    Cleans up any leftover temporary `.tmp` files on exception.
    """
    p = Path(target_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    raw_pickle = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    compressed = gzip.compress(raw_pickle, compresslevel=compresslevel)
    try:
        write_bytes(str(p), compressed, atomic=True)
        return p
    except BaseException:
        for leftover in p.parent.glob(f"*{p.name}*.tmp*"):
            try:
                leftover.unlink()
            except OSError:
                pass
        raise


__all__ = [
    "atomic_save_gzip_pickle",
    "load_gzip_pickle",
    "normalize_dirty_paths",
    "is_dirty_file_match",
]
