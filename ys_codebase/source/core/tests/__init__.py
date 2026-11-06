"""
Core module unit test package and shared test helpers.
"""
import hashlib
import importlib.util
import json
import os
import types
import zipfile
from typing import Any, Dict, Optional, Union


def _core_source_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_core_cli_module(module_name: str = "_test_core_scripts_cli") -> types.ModuleType:
    """Dynamically load source/core/scripts/cli.py for direct unit testing."""
    cli_path = os.path.join(_core_source_root(), "scripts", "cli.py")
    if not os.path.isfile(cli_path):
        from core import uri
        cli_path = uri.resolve("module://core/scripts/cli.py")
    spec = importlib.util.spec_from_file_location(module_name, cli_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load spec for '{cli_path}'")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_yscb_host_module(module_name: str = "_test_yscb_host") -> types.ModuleType:
    """Dynamically locate and load the thin host script yscb.py."""
    yscb_path: Optional[str] = None
    try:
        from core import uri
        cfg_path, _ = uri._get_host_config()
        cand = os.path.join(os.path.dirname(cfg_path), "yscb.py")
        if os.path.isfile(cand):
            yscb_path = cand
    except Exception:
        pass

    if not yscb_path:
        curr = _core_source_root()
        for _ in range(6):
            cand = os.path.join(curr, "yscb.py")
            if os.path.isfile(cand):
                yscb_path = cand
                break
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            curr = parent

    if not yscb_path or not os.path.isfile(yscb_path):
        raise FileNotFoundError("Could not locate host 'yscb.py' for test loading.")

    spec = importlib.util.spec_from_file_location(module_name, yscb_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load spec for '{yscb_path}'")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_core_migration_module(
    script_name: str = "1.2.7.x.py",
    module_name: str = "_test_core_mig",
) -> types.ModuleType:
    """Dynamically locate and load a migration script under source/core/scripts/migrations/."""
    mig_path = os.path.join(_core_source_root(), "scripts", "migrations", script_name)
    if not os.path.isfile(mig_path):
        from core import uri
        mig_path = uri.resolve(f"module://core/scripts/migrations/{script_name}")
    spec = importlib.util.spec_from_file_location(module_name, mig_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load spec for migration script '{mig_path}'")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def create_provider_release_zip(
    provider_dir: str,
    mod_name: str,
    version: str,
    dependencies: Optional[Dict[str, Any]] = None,
    manifest: Optional[Dict[str, Any]] = None,
    extra_files: Optional[Dict[str, Union[str, bytes]]] = None,
    release_meta: Optional[Dict[str, Any]] = None,
    write_index: bool = True,
    compute_sha256: bool = True,
    status: str = "active",
    entry: str = "scripts/cli.py",
) -> str:
    """Create a module release .zip in provider_dir/<mod_name>/<version>.zip and update index.json."""
    mod_prov_dir = os.path.join(provider_dir, mod_name)
    os.makedirs(mod_prov_dir, exist_ok=True)
    zp = os.path.join(mod_prov_dir, f"{version}.zip")

    if manifest is not None:
        mf_data = dict(manifest)
        if dependencies is not None and "dependencies" not in mf_data:
            mf_data["dependencies"] = dependencies
    else:
        mf_data = {
            "name": mod_name,
            "version": version,
            "description": f"Test module {mod_name}",
            "entry": entry,
            "dependencies": dependencies or {},
        }

    files_map = dict(extra_files or {})
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
        if "manifest.json" not in files_map:
            zf.writestr("manifest.json", json.dumps(mf_data, indent=2))
        if entry and entry not in files_map:
            zf.writestr(entry, f"VER = '{version}'\ndef main():\n    return 0\n")
        for arcname, content in files_map.items():
            zf.writestr(arcname, content)

    if write_index:
        idx_path = os.path.join(mod_prov_dir, "index.json")
        idx_data: Dict[str, Any] = {"name": mod_name, "versions": [], "releases": {}}
        if os.path.isfile(idx_path):
            try:
                with open(idx_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    idx_data.update(loaded)
            except (OSError, json.JSONDecodeError):
                pass

        versions = list(idx_data.get("versions", []))
        if version not in versions:
            versions.append(version)
        idx_data["versions"] = versions

        releases = dict(idx_data.get("releases", {}))
        rel_entry = dict(release_meta) if isinstance(release_meta, dict) else {}
        rel_entry.setdefault("status", status)
        rel_entry.setdefault("dependencies", mf_data.get("dependencies", {}))
        if compute_sha256:
            with open(zp, "rb") as f:
                rel_entry["sha256"] = hashlib.sha256(f.read()).hexdigest()
        releases[version] = rel_entry
        idx_data["releases"] = releases

        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(idx_data, f, indent=2)

    return zp


__all__ = [
    "load_core_cli_module",
    "load_yscb_host_module",
    "load_core_migration_module",
    "create_provider_release_zip",
]
