"""
Core 1.2.8.x migration hook.
Migrates legacy `<yscb_dir>/config/file-space/contribute.json` spaces into
`<yscb_dir>/config/core/contribute.json` when upgrading `core` from 1.2.7.x to >= 1.2.8.0,
and cleans up obsolete `file-space` directories and `yscb.config.json` entries.
"""
from typing import Any, Dict, Optional
import copy
import json
import os
import shutil


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


def _cleanup_legacy_file_space_residuals(yscb_dir: str, host_dir: Optional[str]) -> None:
    """Removes obsolete `file-space` entries in `yscb.config.json` and residual storage/cache directories."""
    eff_host = host_dir
    if not eff_host and os.path.isfile(os.path.join(os.path.dirname(yscb_dir), "yscb.config.json")):
        eff_host = os.path.dirname(yscb_dir)
    if eff_host:
        host_cfg_path = os.path.join(eff_host, "yscb.config.json")
        host_cfg = _read_json_dict_or_none(host_cfg_path)
        if isinstance(host_cfg, dict) and isinstance(host_cfg.get("installed_modules"), dict):
            if "file-space" in host_cfg["installed_modules"]:
                del host_cfg["installed_modules"]["file-space"]
                _atomic_write_json_file(host_cfg_path, host_cfg)

    for obsolete_sub in (
        os.path.join(".modules", "file-space"),
        os.path.join(".mirror", "file-space"),
        os.path.join(".cache", "file-space"),
        os.path.join(".storage.local", "file-space"),
        os.path.join(".config.local", "file-space"),
    ):
        obs_path = os.path.join(yscb_dir, obsolete_sub)
        if os.path.isdir(obs_path):
            shutil.rmtree(obs_path, ignore_errors=True)


def migrate(context: Dict[str, Any]) -> bool:
    """
    Migrates legacy `<yscb_dir>/config/file-space/contribute.json` into `<yscb_dir>/config/core/contribute.json`
    and purges obsolete `file-space` runtime/cache/storage directories.
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
    if os.path.isfile(legacy_cfg_path):
        legacy_data = _read_json_dict_or_none(legacy_cfg_path)
        if legacy_data is not None:
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

    _cleanup_legacy_file_space_residuals(yscb_dir, context.get("host_dir"))
    return True
