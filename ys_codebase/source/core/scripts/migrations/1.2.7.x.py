"""
Core 1.2.7.x migration hook.
Migrates legacy `config://<mod>/config*.local.json` files into `config.local://<mod>/config*.local.json`
and migrates `<yscb_dir>/.cache/core/gitignore_dynamic.json` into `<yscb_dir>/.storage.local/core/gitignore_dynamic.json`
when upgrading `core` to >= 1.2.7.0, keeping runtime lookup logic 100% free of legacy fallback branches.
"""
from typing import Any, Dict, Optional
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


def _read_json_dict_or_none(file_path: str) -> Optional[Dict[str, Any]]:
    """Reads a JSON file and returns it if it is a dictionary, otherwise None."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                return loaded
    except Exception:
        pass
    return None


def _atomic_write_json_file(target_path: str, data: Dict[str, Any]) -> None:
    """Atomically writes a dictionary as formatted JSON to `target_path`."""
    tmp_path = f"{target_path}.tmp_{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, target_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


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
                legacy_data = _read_json_dict_or_none(legacy_path)
                target_data = _read_json_dict_or_none(target_path)

                if legacy_data is not None and target_data is not None:
                    merged = _deep_merge_dict(target_data, legacy_data)
                    _atomic_write_json_file(target_path, merged)
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

    legacy_data = _read_json_dict_or_none(legacy_gi_path)
    target_data = _read_json_dict_or_none(target_gi_path)

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
        _atomic_write_json_file(target_gi_path, merged)
    elif legacy_data is not None and target_data is None:
        shutil.copy2(legacy_gi_path, target_gi_path)

    try:
        os.remove(legacy_gi_path)
    except OSError:
        pass


def _convert_legacy_space_entry(raw_space: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a legacy `file-space` definition (`include` roots + `file_patterns` globs)
    into the `core.space` definition format (`entries` roots + `include` globs).
    """
    converted: Dict[str, Any] = {}
    if "description" in raw_space:
        converted["description"] = raw_space["description"]

    if "entries" in raw_space:
        converted["entries"] = copy.deepcopy(raw_space["entries"])
    elif "include" in raw_space and "file_patterns" in raw_space:
        converted["entries"] = copy.deepcopy(raw_space["include"])
        converted["include"] = copy.deepcopy(raw_space["file_patterns"])
    elif "include" in raw_space:
        # Check if `include` looks like URI/path roots rather than globs
        inc_list = raw_space["include"]
        if isinstance(inc_list, list) and all(
            isinstance(x, str) and ("://" in x or not any(ch in x for ch in ("*", "?")))
            for x in inc_list
        ):
            converted["entries"] = copy.deepcopy(inc_list)
        else:
            converted["entries"] = ["project://"]
            converted["include"] = copy.deepcopy(inc_list)

    if "file_patterns" in raw_space and "include" not in converted:
        converted["include"] = copy.deepcopy(raw_space["file_patterns"])
    elif "include" in raw_space and "entries" in raw_space:
        converted["include"] = copy.deepcopy(raw_space["include"])

    for key in (
        "compose",
        "presets",
        "exclude",
        "hash_policy",
        "large_file_threshold_mb",
        "follow_symlinks",
        "watch",
    ):
        if key in raw_space:
            converted[key] = copy.deepcopy(raw_space[key])
    return converted


def _migrate_legacy_file_space_config(yscb_dir: str) -> None:
    """
    Migrates `<yscb_dir>/config/file-space/contribute.json` spaces into
    `<yscb_dir>/config/core/contribute.json`, converting `include` + `file_patterns`
    into `entries` + `include`, and removes the legacy file and empty directory.
    """
    legacy_dir = os.path.join(yscb_dir, "config", "file-space")
    legacy_cfg_path = os.path.join(legacy_dir, "contribute.json")
    if not os.path.isfile(legacy_cfg_path):
        return

    legacy_data = _read_json_dict_or_none(legacy_cfg_path)
    if legacy_data is None:
        return

    raw_spaces = legacy_data.get("spaces")
    if isinstance(raw_spaces, dict) and raw_spaces:
        core_cfg_dir = os.path.join(yscb_dir, "config", "core")
        core_cfg_path = os.path.join(core_cfg_dir, "contribute.json")
        os.makedirs(core_cfg_dir, exist_ok=True)

        target_data = _read_json_dict_or_none(core_cfg_path) or {}
        target_spaces = target_data.get("spaces")
        if not isinstance(target_spaces, dict):
            target_spaces = {}

        for sp_name, sp_def in raw_spaces.items():
            if sp_name not in target_spaces and isinstance(sp_def, dict):
                target_spaces[sp_name] = _convert_legacy_space_entry(sp_def)

        target_data["spaces"] = target_spaces
        _atomic_write_json_file(core_cfg_path, target_data)

    try:
        os.remove(legacy_cfg_path)
    except OSError:
        pass
    try:
        if os.path.isdir(legacy_dir) and not os.listdir(legacy_dir):
            os.rmdir(legacy_dir)
    except OSError:
        pass


def migrate(context: Dict[str, Any]) -> bool:
    """
    Scans `<yscb_dir>/config/<mod>/config*.local.json` across all modules and migrates
    each file to `<yscb_dir>/.config.local/<mod>/config*.local.json`, migrates
    `<yscb_dir>/.cache/core/gitignore_dynamic.json` to `<storage_local_dir>/gitignore_dynamic.json`,
    and migrates legacy `<yscb_dir>/config/file-space/contribute.json` into `<yscb_dir>/config/core/contribute.json`.
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
    _migrate_legacy_file_space_config(yscb_dir)

    try:
        from core import config
        config.reload()
    except Exception:
        pass

    return True
