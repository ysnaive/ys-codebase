"""
Atomic Gzip + Pickle Binary Persistence Primitives for Knowledge-DB.
"""

import gzip
from pathlib import Path
import pickle
from typing import Any, Union

from core.vfs import write_bytes


def atomic_save_gzip_pickle(
    target_path: Union[str, Path],
    payload: Any,
    compresslevel: int = 1,
) -> Path:
    """
    Serialize payload via pickle + gzip and atomically write to target_path via core.vfs.write_bytes.
    """
    p = Path(target_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    raw_pickle = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    compressed = gzip.compress(raw_pickle, compresslevel=compresslevel)
    write_bytes(str(p), compressed)
    return p


def load_gzip_pickle(target_path: Union[str, Path], raise_on_missing: bool = False) -> Any:
    """
    Read and deserialize a gzip-compressed pickle file from target_path.
    If raise_on_missing is False and the file is missing or corrupted, returns None.
    """
    p = Path(target_path)
    if not p.exists():
        if raise_on_missing:
            raise FileNotFoundError(f"Gzip pickle file not found: {p}")
        return None
    try:
        with gzip.open(p, "rb") as f:
            return pickle.loads(f.read())
    except Exception:
        if raise_on_missing:
            raise
        return None
