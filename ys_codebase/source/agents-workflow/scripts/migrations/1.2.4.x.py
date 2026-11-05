"""
agents-workflow 1.2.4.x migration hook.
Migrates legacy release manifests and source SHA-1 cache from `storage://agents-workflow/`
and `cache://agents-workflow/` into `storage.local://agents-workflow/`, keeping runtime
publisher code free of legacy fallback branches.
"""

from typing import Any, Dict
import datetime
import json
import os
import shutil


def _move_or_discard(src_path: str, dst_path: str) -> None:
    """Idempotently moves `src_path` to `dst_path`, or removes `src_path` if `dst_path` already exists."""
    if not os.path.isfile(src_path):
        return
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    if not os.path.exists(dst_path):
        shutil.move(src_path, dst_path)
    else:
        try:
            os.remove(src_path)
        except OSError:
            pass


def migrate(context: Dict[str, Any]) -> bool:
    """
    Idempotently migrates legacy `<storage_dir>/release_manifest.json` and
    `<yscb_dir>/.cache/agents-workflow/{project_release_manifest,release_manifest,source_sha1_cache}.json`
    into `<storage_local_dir>/` and cleans up legacy files and empty `<storage_dir>`.
    """
    yscb_dir = context.get("yscb_dir")
    if not yscb_dir:
        try:
            from core import uri
            yscb_dir = uri.resolve_yscb_root()
        except Exception:
            return True

    storage_dir = context.get("storage_dir") or os.path.join(yscb_dir, "storage", "agents-workflow")
    storage_local_dir = context.get("storage_local_dir") or os.path.join(
        yscb_dir, ".storage.local", "agents-workflow"
    )
    cache_dir = os.path.join(yscb_dir, ".cache", "agents-workflow")

    # 1. Migrate legacy storage://agents-workflow/release_manifest.json -> project_release_manifest.json
    legacy_storage_manifest = os.path.join(storage_dir, "release_manifest.json")
    target_proj_manifest = os.path.join(storage_local_dir, "project_release_manifest.json")
    if os.path.isfile(legacy_storage_manifest):
        os.makedirs(storage_local_dir, exist_ok=True)
        if not os.path.exists(target_proj_manifest):
            converted_payload = None
            try:
                with open(legacy_storage_manifest, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    if "published_files" in raw:
                        converted_payload = raw
                    elif isinstance(raw.get("files"), list):
                        converted_payload = {
                            "fingerprint": raw.get("fingerprint", ""),
                            "active_targets": raw.get("active_targets", ["antigravity"]),
                            "published_files": raw["files"],
                            "combined_fingerprint": raw.get("combined_fingerprint", raw.get("fingerprint", "")),
                            "updated_at": raw.get(
                                "updated_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            ),
                        }
            except Exception:
                converted_payload = None

            if converted_payload is not None:
                tmp_path = f"{target_proj_manifest}.tmp"
                with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(converted_payload, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                os.replace(tmp_path, target_proj_manifest)
                try:
                    os.remove(legacy_storage_manifest)
                except OSError:
                    pass
            else:
                shutil.move(legacy_storage_manifest, target_proj_manifest)
        else:
            try:
                os.remove(legacy_storage_manifest)
            except OSError:
                pass

    if os.path.isdir(storage_dir):
        try:
            if not os.listdir(storage_dir):
                os.rmdir(storage_dir)
        except OSError:
            pass

    # 2. Migrate cache://agents-workflow/{project_release_manifest,release_manifest,source_sha1_cache}.json
    for fname in ("project_release_manifest.json", "release_manifest.json", "source_sha1_cache.json"):
        src_p = os.path.join(cache_dir, fname)
        dst_p = os.path.join(storage_local_dir, fname)
        _move_or_discard(src_p, dst_p)

    return True
