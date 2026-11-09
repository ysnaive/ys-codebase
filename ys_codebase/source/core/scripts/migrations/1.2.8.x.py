"""
Core 1.2.8.x migration hook.
Migrates legacy `<yscb_dir>/config/file-space/contribute.json` spaces into
`<yscb_dir>/config/core/contribute.json` when upgrading `core` from 1.2.7.x to >= 1.2.8.0,
and cleans up obsolete `file-space` directories and `yscb.config.json` entries.
"""
from typing import Any, Dict, Optional
import os
import shutil

from core.loader import load_module_from_path


def _load_mig_127_module() -> Any:
    mig_127_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "1.2.7.x.py")
    if not os.path.isfile(mig_127_path):
        return None
    try:
        return load_module_from_path("_yscb_mod_core_mig_127_shared", mig_127_path)
    except Exception:
        return None


def _cleanup_legacy_file_space_residuals(yscb_dir: str, host_dir: Optional[str], mig_127: Any) -> None:
    """Removes obsolete `file-space` entries in `yscb.config.json` and residual storage/cache directories."""
    eff_host = host_dir
    if not eff_host and os.path.isfile(os.path.join(os.path.dirname(yscb_dir), "yscb.config.json")):
        eff_host = os.path.dirname(yscb_dir)
    if eff_host and mig_127 is not None:
        host_cfg_path = os.path.join(eff_host, "yscb.config.json")
        host_cfg = mig_127._read_json_dict_or_none(host_cfg_path)
        if isinstance(host_cfg, dict) and isinstance(host_cfg.get("installed_modules"), dict):
            if "file-space" in host_cfg["installed_modules"]:
                del host_cfg["installed_modules"]["file-space"]
                mig_127._atomic_write_json_file(host_cfg_path, host_cfg)

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

    mig_127 = _load_mig_127_module()
    if mig_127 is not None and hasattr(mig_127, "_migrate_legacy_file_space_config"):
        mig_127._migrate_legacy_file_space_config(yscb_dir)

    _cleanup_legacy_file_space_residuals(yscb_dir, context.get("host_dir"), mig_127)

    try:
        from core import config, contributes
        config.reload()
        contributes.invalidate_cache()
    except Exception:
        pass

    return True
