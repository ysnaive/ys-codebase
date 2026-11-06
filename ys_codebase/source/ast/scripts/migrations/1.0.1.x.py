"""
ast 1.0.1.x migration hook.
Migrates legacy `<yscb_dir>/.cache/ast/{indices,bundles}` non-lock files into
`<storage_local_dir>/{indices,bundles}` when upgrading `ast` to >= 1.0.1.0.
"""
import os
import shutil
from typing import Any, Dict


def _migrate_dir_contents(src_dir: str, dst_dir: str) -> None:
    if not os.path.isdir(src_dir):
        return
    try:
        os.makedirs(dst_dir, exist_ok=True)
        entries = sorted(os.listdir(src_dir))
    except OSError:
        return
    for entry in entries:
        if entry.endswith(".lock"):
            continue
        src_path = os.path.join(src_dir, entry)
        dst_path = os.path.join(dst_dir, entry)
        if os.path.isdir(src_path):
            _migrate_dir_contents(src_path, dst_path)
        elif os.path.isfile(src_path):
            if not os.path.exists(dst_path):
                try:
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    shutil.move(src_path, dst_path)
                except OSError:
                    pass
            else:
                try:
                    os.remove(src_path)
                except OSError:
                    pass
    try:
        if not os.listdir(src_dir):
            os.rmdir(src_dir)
    except OSError:
        pass


def migrate(context: Dict[str, Any]) -> bool:
    """
    Idempotently migrates non-lock files from `<yscb_dir>/.cache/ast/{indices,bundles}`
    into `<storage_local_dir>/{indices,bundles}`.
    """
    ctx = context if isinstance(context, dict) else {}
    yscb_dir = ctx.get("yscb_dir")
    if not yscb_dir:
        try:
            from core import uri

            yscb_dir = uri.resolve_yscb_root()
        except Exception:
            return True

    storage_local_dir = ctx.get("storage_local_dir") or os.path.join(
        str(yscb_dir), ".storage.local", "ast"
    )
    legacy_cache_dir = os.path.join(str(yscb_dir), ".cache", "ast")
    if not os.path.isdir(legacy_cache_dir):
        return True

    for subdir in ("indices", "bundles"):
        src_sub = os.path.join(legacy_cache_dir, subdir)
        dst_sub = os.path.join(str(storage_local_dir), subdir)
        try:
            _migrate_dir_contents(src_sub, dst_sub)
        except OSError:
            pass

    return True
