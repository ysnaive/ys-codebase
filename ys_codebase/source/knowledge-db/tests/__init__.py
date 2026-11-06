"""Tests package for knowledge-db module with shared testing utilities."""

import importlib.util
import os
import sys
from pathlib import Path
from typing import Optional, Union

PKG_ROOT = Path(__file__).resolve().parent.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def process(args: list) -> int:
    """Invoke CLI command through core command dispatcher."""
    from core.commands.dispatcher import dispatch

    full_args = ["knowledge-db"] + list(args)
    return dispatch(full_args)


def load_script_module(rel_path: str):
    """Dynamically load a script module under scripts/ (supports dots/subdirectories)."""
    mod_path = PKG_ROOT / "scripts" / rel_path
    mod_name = "kdb_script_" + rel_path.replace("/", "_").replace(".", "_")
    spec = importlib.util.spec_from_file_location(mod_name, str(mod_path))
    mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def advance_mtime(
    path: Union[str, Path],
    old_mtime_ns: Optional[int] = None,
    delta_ns: int = 1_000_000_000,
) -> int:
    """Deterministically advance file mtime_ns via os.utime without time.sleep."""
    p = Path(path)
    st = p.stat()
    base_ns = old_mtime_ns if old_mtime_ns is not None else st.st_mtime_ns
    new_mtime_ns = max(st.st_mtime_ns + delta_ns, base_ns + delta_ns)
    os.utime(p, ns=(st.st_atime_ns, new_mtime_ns))
    return p.stat().st_mtime_ns


def write_text_and_advance_mtime(
    path: Union[str, Path],
    content: str,
    encoding: str = "utf-8",
    delta_ns: int = 1_000_000_000,
) -> int:
    """Write text to path and deterministically advance its mtime_ns beyond previous mtime_ns."""
    p = Path(path)
    old_ns = p.stat().st_mtime_ns if p.exists() else None
    p.write_text(content, encoding=encoding)
    return advance_mtime(p, old_mtime_ns=old_ns, delta_ns=delta_ns)
