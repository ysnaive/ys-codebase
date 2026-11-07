"""
Migration script for module `ast` upgrading to >= 1.0.1.0.
1. Automatically migrates legacy `.cache/ast/{indices,bundles}` to `.storage.local/ast/{indices,bundles}`
   (skipping transient `.lock` files) and cleans up migrated files.
2. Resets the `ast` consumer cursor in `core.space` so upgrading cleanly re-baselines space snapshots.
"""

import shutil
from pathlib import Path
from typing import Any


def migrate(context: Any) -> bool:
    try:
        from core.space import reset_cursor

        reset_cursor(None, consumer_id="ast")
    except Exception:
        pass

    if isinstance(context, dict):
        yscb_dir_raw = context.get("yscb_dir")
        storage_local_raw = context.get("storage_local_dir")
        project_root_raw = context.get("project_root")
    else:
        yscb_dir_raw = getattr(context, "yscb_dir", None)
        storage_local_raw = getattr(context, "storage_local_dir", None)
        project_root_raw = getattr(context, "project_root", None)

    legacy_cache_dir = None
    target_storage_dir = None

    if yscb_dir_raw:
        yscb_path = Path(str(yscb_dir_raw))
        legacy_cache_dir = yscb_path / ".cache" / "ast"
        target_storage_dir = (
            Path(str(storage_local_raw))
            if storage_local_raw
            else (yscb_path / ".storage.local" / "ast")
        )
    elif project_root_raw:
        proj_path = Path(str(project_root_raw))
        legacy_cache_dir = proj_path / "ys_codebase" / ".cache" / "ast"
        if not legacy_cache_dir.exists():
            legacy_cache_dir = proj_path / ".cache" / "ast"
        if storage_local_raw:
            target_storage_dir = Path(str(storage_local_raw))
        elif (proj_path / "ys_codebase").is_dir():
            target_storage_dir = proj_path / "ys_codebase" / ".storage.local" / "ast"
        else:
            target_storage_dir = proj_path / ".storage.local" / "ast"

    if not legacy_cache_dir or not legacy_cache_dir.exists() or not target_storage_dir:
        return True

    target_storage_dir.mkdir(parents=True, exist_ok=True)

    for subdir_name in ("indices", "bundles"):
        src_sub = legacy_cache_dir / subdir_name
        dst_sub = target_storage_dir / subdir_name
        if src_sub.is_dir():
            dst_sub.mkdir(parents=True, exist_ok=True)
            for item in list(src_sub.iterdir()):
                if item.name.endswith(".lock") or item.name.startswith(".ast_index"):
                    continue
                target_item = dst_sub / item.name
                if not target_item.exists():
                    shutil.move(str(item), str(target_item))
                else:
                    if item.is_file():
                        item.unlink(missing_ok=True)
                    elif item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)

    return True
