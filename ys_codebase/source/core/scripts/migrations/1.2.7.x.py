"""
Core 1.2.7.x migration hook.
Migrates legacy `config://<mod>/config*.local.json` files into `config.local://<mod>/config*.local.json`
and migrates `<yscb_dir>/.cache/core/gitignore_dynamic.json` into `<yscb_dir>/.storage.local/core/gitignore_dynamic.json`
when upgrading `core` to >= 1.2.7.0, keeping runtime lookup logic 100% free of legacy fallback branches.
"""
from typing import Any, Dict
import copy
import json
import os
import shutil


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merges `override` onto a copy of `base`."""
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge_dict(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def _migrate_local_configs(yscb_dir: str) -> None:
    """Migrates `<yscb_dir>/config/<mod>/config*.local.json` to `<yscb_dir>/.config.local/<mod>/`."""
    cfg_root = os.path.join(yscb_dir, "config")
    local_root = os.path.join(yscb_dir, ".config.local")
    if not os.path.isdir(cfg_root):
        return

    for mod_name in sorted(os.listdir(cfg_root)):
        if mod_name.startswith("."):
            continue
        mod_cfg_dir = os.path.join(cfg_root, mod_name)
        if not os.path.isdir(mod_cfg_dir):
            continue

        for fname in sorted(os.listdir(mod_cfg_dir)):
            is_local_cfg = fname == "config.local.json" or (
                fname.startswith("config.") and fname.endswith(".local.json")
            )
            if not is_local_cfg:
                continue

            legacy_path = os.path.join(mod_cfg_dir, fname)
            if not os.path.isfile(legacy_path):
                continue

            target_mod_dir = os.path.join(local_root, mod_name)
            target_path = os.path.join(target_mod_dir, fname)
            os.makedirs(target_mod_dir, exist_ok=True)

            if not os.path.exists(target_path):
                shutil.move(legacy_path, target_path)
            else:
                legacy_data = None
                target_data = None
                try:
                    with open(legacy_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            legacy_data = loaded
                except Exception:
                    legacy_data = None

                try:
                    with open(target_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            target_data = loaded
                except Exception:
                    target_data = None

                if legacy_data is not None and target_data is not None:
                    merged = _deep_merge_dict(target_data, legacy_data)
                    tmp_path = f"{target_path}.tmp"
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        json.dump(merged, f, indent=2, ensure_ascii=False)
                        f.write("\n")
                    os.replace(tmp_path, target_path)
                elif legacy_data is not None and target_data is None:
                    shutil.copy2(legacy_path, target_path)

                try:
                    os.remove(legacy_path)
                except OSError:
                    pass

        try:
            if not os.listdir(mod_cfg_dir):
                os.rmdir(mod_cfg_dir)
        except OSError:
            pass


def _migrate_gitignore_dynamic(yscb_dir: str, storage_local_dir: str) -> None:
    """Migrates `<yscb_dir>/.cache/core/gitignore_dynamic.json` to `<storage_local_dir>/gitignore_dynamic.json`."""
    legacy_gi_path = os.path.join(yscb_dir, ".cache", "core", "gitignore_dynamic.json")
    if not os.path.isfile(legacy_gi_path):
        return

    os.makedirs(storage_local_dir, exist_ok=True)
    target_gi_path = os.path.join(storage_local_dir, "gitignore_dynamic.json")

    if not os.path.exists(target_gi_path):
        shutil.move(legacy_gi_path, target_gi_path)
        return

    legacy_data = None
    target_data = None
    try:
        with open(legacy_gi_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                legacy_data = loaded
    except Exception:
        legacy_data = None

    try:
        with open(target_gi_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                target_data = loaded
    except Exception:
        target_data = None

    if legacy_data is not None and target_data is not None:
        merged = copy.deepcopy(target_data)
        for k, v in legacy_data.items():
            if k not in merged:
                merged[k] = copy.deepcopy(v)
            elif isinstance(merged[k], list) and isinstance(v, list):
                for item in v:
                    if item not in merged[k]:
                        merged[k].append(item)
            elif isinstance(merged[k], dict) and isinstance(v, dict):
                merged[k] = _deep_merge_dict(v, merged[k])
        tmp_path = f"{target_gi_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, target_gi_path)
    elif legacy_data is not None and target_data is None:
        shutil.copy2(legacy_gi_path, target_gi_path)

    try:
        os.remove(legacy_gi_path)
    except OSError:
        pass


def migrate(context: Dict[str, Any]) -> bool:
    """
    Scans `<yscb_dir>/config/<mod>/config*.local.json` across all modules and migrates
    each file to `<yscb_dir>/.config.local/<mod>/config*.local.json`, and migrates
    `<yscb_dir>/.cache/core/gitignore_dynamic.json` to `<storage_local_dir>/gitignore_dynamic.json`.
    """
    yscb_dir = context.get("yscb_dir")
    if not yscb_dir:
        try:
            from core import uri
            yscb_dir = uri.resolve_yscb_root()
        except Exception:
            return True

    storage_local_dir = context.get("storage_local_dir") or os.path.join(
        yscb_dir, ".storage.local", "core"
    )

    _migrate_local_configs(yscb_dir)
    _migrate_gitignore_dynamic(yscb_dir, storage_local_dir)

    try:
        from core import config
        config.reload()
    except Exception:
        pass

    return True

