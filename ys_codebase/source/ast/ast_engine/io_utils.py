"""
Atomic Gzip + Pickle Binary Persistence, Project Root Discovery, and Dirty File Path Matching Primitives for module:ast.
"""

import gzip
import io
import os
from pathlib import Path
import pickle
from typing import Any, Iterable, Optional, Set, Union

from core.context import get_virtual_cwd
from core.vfs import write_bytes


def resolve_project_root(explicit_root: Optional[Union[str, Path]] = None) -> Path:
    """Resolve canonical project root directory from `explicit_root`, `project://`, or `Path.cwd()`."""
    if explicit_root is not None:
        return Path(explicit_root).resolve()
    try:
        from core import uri

        res = uri.resolve("project://", interactive=False)
        if res and not str(res).startswith("!undefined"):
            return Path(str(res)).resolve()
    except Exception:
        pass
    return Path(get_virtual_cwd()).resolve()


def compute_project_relpath(
    file_path: Path,
    fallback_base: Optional[Path] = None,
    project_root: Optional[Union[str, Path]] = None,
) -> str:
    """Compute forward-slash relative path from `project_root` (or `fallback_base`) to `file_path`."""
    try:
        resolved_file = file_path.resolve()
    except OSError:
        resolved_file = file_path

    if project_root is not None:
        try:
            root = Path(project_root).resolve()
            rel = os.path.relpath(str(resolved_file), str(root)).replace("\\", "/")
            if rel != ".." and not rel.startswith("../"):
                return rel
        except Exception:
            pass

    try:
        default_root = resolve_project_root()
        rel = os.path.relpath(str(resolved_file), str(default_root)).replace("\\", "/")
        if rel != ".." and not rel.startswith("../"):
            return rel
    except Exception:
        pass

    if fallback_base is not None:
        try:
            rel = os.path.relpath(str(file_path), str(fallback_base)).replace("\\", "/")
            if rel != ".." and not rel.startswith("../"):
                base_name = Path(fallback_base).name
                return f"{base_name}/{rel}" if base_name else rel
        except Exception:
            pass

    return file_path.name


def atomic_save_gzip_pickle(
    target_path: Union[str, Path],
    payload: Any,
    compresslevel: int = 1,
) -> Path:
    """
    Serialize payload via pickle + gzip context manager and atomically write to target_path via core.vfs.write_bytes.
    Ensures any temporary `.tmp` file in the parent directory is cleaned up in `finally` on write error.
    """
    p = Path(target_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    raw_pickle = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=compresslevel) as gz:
        gz.write(raw_pickle)
    compressed = buf.getvalue()
    tmp_path = p.with_name(f".{p.name}.tmp.{os.getpid()}")
    try:
        write_bytes(str(p), compressed, atomic=True)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        for leftover in p.parent.glob(f"*{p.name}*.tmp*"):
            try:
                leftover.unlink()
            except OSError:
                pass
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
    """Normalize dirty file paths to forward-slash lowercase strings."""
    return {str(p).replace("\\", "/").lower() for p in dirty_file_paths if p}


def is_dirty_file_match(doc_file_path: str, dirty_paths_norm: Set[str]) -> bool:
    """Check whether doc_file_path matches any normalized path in dirty_paths_norm."""
    if not dirty_paths_norm:
        return False
    sym_path_norm = str(doc_file_path).replace("\\", "/").strip("/").lower()
    if not sym_path_norm:
        return False
    if sym_path_norm in dirty_paths_norm or ("/" + sym_path_norm) in dirty_paths_norm:
        return True
    if "/" not in sym_path_norm:
        suffix = "/" + sym_path_norm
        for p in dirty_paths_norm:
            is_abs_p = p.startswith("/") or (len(p) > 2 and p[1] == ":" and p[2] == "/")
            if is_abs_p and p.endswith(suffix):
                return True
        return False
    for p in dirty_paths_norm:
        if "/" in p and (p.endswith("/" + sym_path_norm) or sym_path_norm.endswith("/" + p)):
            return True
    return False
