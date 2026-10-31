"""
Contributes Command Handlers for YSCB Core.
Provides 'contributes list' and 'contributes check'.
"""
from typing import Optional, Dict, Any
import os

from core import uri, vfs
from core.validator import ContributesValidator, ValidationResult
from core import contributes
from core import locale as core_locale


def _append_locale_validation_errors(
    res: ValidationResult,
    module_name: str,
    data: Any,
    base_dir: Optional[str],
) -> None:
    """Append locale contract validation issues when target is core and payload declares locales."""
    if isinstance(data, dict) and "locales" in data and isinstance(data["locales"], dict):
        loc_res = core_locale.validate_module_locales(module_name, data["locales"], base_dir=base_dir)
        res.issues.extend(loc_res.issues)
        res.is_valid = len([i for i in res.issues if i.severity == "ERROR"]) == 0


def list_contributes(module_filter: Optional[str] = None) -> int:
    """List all registered contribute points across ecosystem."""
    points = contributes.list_points(module_filter)
    if not points:
        print("[core:contributes] No contribution points found.")
        return 0

    print("\nYS-Codebase Registered Contribution Points:")
    print("=" * 85)
    print(f"{'Target Module':<18} | {'Point Key':<20} | {'Type':<12} | {'Description'}")
    print("-" * 85)
    for p in points:
        mod = p.get("module", "")
        pt = p.get("point", "")
        ft = p.get("format_type", "object")
        desc = p.get("description", "")
        # Shorten description if too long
        if len(desc) > 35:
            desc = desc[:32] + "..."
        print(f"{mod:<18} | {pt:<20} | {ft:<12} | {desc}")
    print("=" * 85)
    print(f"Total points registered: {len(points)}\n")
    return 0


def _check_format_schema_mode(target_or_uri: Optional[str]) -> int:
    """Meta-check on _format.json schema for a given module."""
    mod_name = target_or_uri or "core"
    fmt_uri = f"module.source://{mod_name}/contributes/_format.json"
    if not vfs.exists(fmt_uri):
        fmt_uri = f"module://{mod_name}/contributes/_format.json"
    if not vfs.exists(fmt_uri):
        print(f"[core:contributes] [FAIL] Error: Format schema not found for module '{mod_name}' at '{fmt_uri}'.")
        return 1
    try:
        data = vfs.read_json(fmt_uri)
    except Exception as e:
        print(f"[core:contributes] [FAIL] Error reading '{fmt_uri}': {e}")
        return 1
    res = ContributesValidator.validate_format_schema(data)
    print(res.format_report(file_label=fmt_uri))
    return 0 if res.is_valid else 1


def _check_single_file_mode(file_uri: str) -> int:
    """Validate a single contributes JSON file or _format.json schema."""
    try:
        p = uri.resolve(file_uri, interactive=False) if "://" in file_uri else os.path.abspath(file_uri)
        if not os.path.isfile(p):
            print(f"[core:contributes] [FAIL] File not found: {file_uri}")
            return 1
    except Exception as e:
        print(f"[core:contributes] [FAIL] Invalid path/URI '{file_uri}': {e}")
        return 1

    fname = os.path.basename(p)
    if fname.startswith("_"):
        print(f"[core:contributes] Checking special metadata file '{fname}' as format schema...")
        data = vfs.read_json(p) if "://" not in file_uri else vfs.read_json(file_uri)
        res = ContributesValidator.validate_format_schema(data)
        print(res.format_report(file_label=file_uri))
        return 0 if res.is_valid else 1

    parent_dir = os.path.dirname(p.rstrip("/\\"))
    if fname == "contribute.json":
        target_mod = os.path.basename(parent_dir)
        donor_mod = "project"
    else:
        target_mod = fname[:-5]
        donor_mod = None

    target_format = contributes.get_format(target_mod)
    if target_format is None:
        print(f"[core:contributes] [WARN] Target module '{target_mod}' does not define a _format.json schema. Skipping validation.")
        return 0

    data = vfs.read_json(file_uri) if "://" in file_uri else vfs.read_json(p)
    if isinstance(data, dict) and target_mod in data and isinstance(data[target_mod], dict):
        data = data[target_mod]

    res = ContributesValidator.validate(target_mod, data, donor_mod=donor_mod, format_schema=target_format, strict_points=True)
    if target_mod == "core":
        inferred_base = parent_dir if fname == "contribute.json" else os.path.dirname(os.path.dirname(p))
        _append_locale_validation_errors(res, donor_mod or target_mod, data, inferred_base)
    print(res.format_report(file_label=file_uri))
    return 0 if res.is_valid else 1


def _check_modules_mode(target_or_uri: Optional[str]) -> int:
    """Validate contributes across one or all installed modules."""
    if target_or_uri:
        mod_uri = f"module://{target_or_uri}"
        cfg_uri = f"config://{target_or_uri}/contribute.json"
        if not vfs.exists(mod_uri) and not vfs.exists(cfg_uri):
            print(f"[core:contributes] [FAIL] Module or target not found: {target_or_uri}")
            return 1
        modules_to_check = [target_or_uri]
    else:
        modules_to_check = vfs.listdir("module://") if vfs.exists("module://") else []
    if not modules_to_check:
        print("[core:contributes] No installed modules found to check.")
        return 0

    all_passed = True
    checked_files_count = 0

    for donor in modules_to_check:
        contrib_dir = f"module://{donor}/contributes"
        if vfs.exists(contrib_dir) and vfs.is_dir(contrib_dir):
            try:
                files = vfs.listdir(contrib_dir)
            except Exception:
                files = []

            for f in files:
                if not f.endswith(".json") or f.startswith("_"):
                    continue
                target_mod = f[:-5]
                target_format = contributes.get_format(target_mod)
                if target_format is None:
                    continue

                f_uri = f"{contrib_dir}/{f}"
                try:
                    data = vfs.read_json(f_uri)
                except Exception as e:
                    print(f"[FAIL] [{f_uri}] JSON syntax error: {e}")
                    all_passed = False
                    continue

                res = ContributesValidator.validate(target_mod, data, donor_mod=donor, format_schema=target_format, strict_points=True)
                if target_mod == "core":
                    try:
                        donor_base = uri.resolve(f"module://{donor}", interactive=False)
                    except Exception:
                        donor_base = None
                    _append_locale_validation_errors(res, donor, data, donor_base)
                checked_files_count += 1
                if not res.is_valid:
                    print(res.format_report(file_label=f_uri))
                    all_passed = False

        # Also check project-level config://<target>/contribute.json
        cfg_uri = f"config://{donor}/contribute.json"
        if vfs.exists(cfg_uri):
            target_format = contributes.get_format(donor)
            if target_format is not None:
                try:
                    cfg_data = vfs.read_json(cfg_uri)
                    if isinstance(cfg_data, dict) and donor in cfg_data and isinstance(cfg_data[donor], dict):
                        cfg_data = cfg_data[donor]
                    res = ContributesValidator.validate(donor, cfg_data, donor_mod="project", format_schema=target_format, strict_points=True)
                    if donor == "core":
                        try:
                            cfg_base = uri.resolve(f"config://{donor}", interactive=False)
                        except Exception:
                            cfg_base = None
                        _append_locale_validation_errors(res, "project", cfg_data, cfg_base)
                    checked_files_count += 1
                    if not res.is_valid:
                        print(res.format_report(file_label=cfg_uri))
                        all_passed = False
                except Exception as e:
                    print(f"[FAIL] [{cfg_uri}] JSON syntax error: {e}")
                    all_passed = False

    if all_passed:
        print(f"\n[PASS] All contributes definitions are valid! (Checked {checked_files_count} file(s))\n")
        return 0
    print("\n[FAIL] Contributes validation failed. Please address the errors above.\n")
    return 1


def check_contributes(target_or_uri: Optional[str] = None, is_format_check: bool = False) -> int:
    """
    Rigidly validate module contributes definitions against format schemas.
    target_or_uri can be:
    - None (validates all installed modules)
    - Module name (e.g. 'core' or 'dev')
    - Semantic URI to file (e.g. 'module.source://dev/contributes/core.json')
    - Physical file path
    """
    if is_format_check:
        return _check_format_schema_mode(target_or_uri)
    if target_or_uri and ("://" in target_or_uri or target_or_uri.endswith(".json")):
        return _check_single_file_mode(target_or_uri)
    return _check_modules_mode(target_or_uri)
