"""
Core 1.2.8.x migration hook.
Migrates legacy `<yscb_dir>/config/file-space/contribute.json` spaces into
`<yscb_dir>/config/core/contribute.json` when upgrading `core` from 1.2.7.x to >= 1.2.8.0.
"""
from typing import Any, Dict, Optional
import copy
import json
import os


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


def migrate(context: Dict[str, Any]) -> bool:
    """
    Migrates legacy `<yscb_dir>/config/file-space/contribute.json` into `<yscb_dir>/config/core/contribute.json`.
    """
    yscb_dir = context.get("yscb_dir")
    if not yscb_dir:
        try:
            from core import uri
            yscb_dir = uri.resolve_yscb_root()
        except Exception:
            return True

    legacy_dir = os.path.join(yscb_dir, "config", "file-space")
    legacy_cfg_path = os.path.join(legacy_dir, "contribute.json")
    if not os.path.isfile(legacy_cfg_path):
        return True

    legacy_data = _read_json_dict_or_none(legacy_cfg_path)
    if legacy_data is None:
        return True

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
    return True
