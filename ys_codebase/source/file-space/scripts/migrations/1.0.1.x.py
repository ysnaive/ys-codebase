"""
file-space 1.0.1.x migration hook.
Migrates legacy `<yscb_dir>/.cache/file-space/{snapshots,cursors}` files into
`<storage_local_dir>/{snapshots,cursors}` when upgrading `file-space` to >= 1.0.1.0.
"""
import os
import shutil
from typing import Any, Dict


def _migrate_dir_contents(src_dir: str, dst_dir: str) -> None:
    if not os.path.isdir(src_dir):
        return
    os.makedirs(dst_dir, exist_ok=True)
    for entry in sorted(os.listdir(src_dir)):
        src_path = os.path.join(src_dir, entry)
        dst_path = os.path.join(dst_dir, entry)
        if os.path.isdir(src_path):
            _migrate_dir_contents(src_path, dst_path)
        elif os.path.isfile(src_path):
            if not os.path.exists(dst_path):
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.move(src_path, dst_path)
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
    Idempotently migrates `<yscb_dir>/.cache/file-space/{snapshots,cursors}`
    into `<storage_local_dir>/{snapshots,cursors}`.
    """
    yscb_dir = context.get("yscb_dir")
    if not yscb_dir:
        try:
            from core import uri

            yscb_dir = uri.resolve_yscb_root()
        except Exception:
            return True

    storage_local_dir = context.get("storage_local_dir") or os.path.join(
        str(yscb_dir), ".storage.local", "file-space"
    )
    legacy_cache_dir = os.path.join(str(yscb_dir), ".cache", "file-space")
    if not os.path.isdir(legacy_cache_dir):
        return True

    for subdir in ("snapshots", "cursors"):
        src_sub = os.path.join(legacy_cache_dir, subdir)
        dst_sub = os.path.join(str(storage_local_dir), subdir)
        _migrate_dir_contents(src_sub, dst_sub)

    return True
