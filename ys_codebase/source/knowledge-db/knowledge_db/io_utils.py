"""
Atomic Gzip + Pickle Binary Persistence and Dirty File Path Matching Primitives for Knowledge-DB.
"""

import gzip
from pathlib import Path
import pickle
from typing import Any, Iterable, Set, Union

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


def normalize_dirty_paths(dirty_file_paths: Iterable[str]) -> Set[str]:
    """正規化待修補或淘汰之髒檔案路徑集合（統一正斜線與小寫）"""
    return {str(p).replace("\\", "/").lower() for p in dirty_file_paths if p}


def is_dirty_file_match(doc_file_path: str, dirty_paths_norm: Set[str]) -> bool:
    """判斷符號或索引紀錄之檔案路徑是否命中正規化後的髒檔案路徑集合"""
    if not dirty_paths_norm:
        return False
    sym_path_norm = str(doc_file_path).replace("\\", "/").lower()
    for p in dirty_paths_norm:
        if sym_path_norm == p:
            return True
        if "/" in p and (p.endswith("/" + sym_path_norm) or sym_path_norm.endswith("/" + p)):
            return True
    return False
