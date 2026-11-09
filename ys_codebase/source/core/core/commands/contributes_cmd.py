"""
Contributes Command Handlers for YSCB Core.
Provides 'contributes list' and 'contributes check'.
"""
from typing import Optional, Dict, Any, Tuple
import os

from core import uri, vfs
from core.log import log, log_error, log_info, log_warn
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


def _validate_unified_contributes_payload(
    u_data: Dict[str, Any],
    donor_mod: str,
    base_dir: Optional[str],
    file_label: str,
) -> Tuple[bool, int]:
    """Validates a unified `contributes.json` payload against its target format schemas."""
    if "commands" in u_data and isinstance(u_data["commands"], dict) and not any(
        isinstance(v, dict) and "commands" in v for v in u_data.values()
    ):
        target_format = contributes.get_format("core")
        if target_format is None:
            return True, 0
        res = ContributesValidator.validate("core", u_data, donor_mod=donor_mod, format_schema=target_format, strict_points=True)
        _append_locale_validation_errors(res, donor_mod, u_data, base_dir)
        if not res.is_valid:
            log(res.format_report(file_label=file_label))
            return False, 1
        return True, 1

    all_ok = True
    checked_targets = 0
    for raw_target, c_body in u_data.items():
        if not isinstance(c_body, dict):
            continue
        eff_target = "core" if raw_target == "commands" else raw_target
        target_format = contributes.get_format(eff_target)
        if target_format is None:
            continue
        res = ContributesValidator.validate(eff_target, c_body, donor_mod=donor_mod, format_schema=target_format, strict_points=True)
        if eff_target == "core":
            _append_locale_validation_errors(res, donor_mod, c_body, base_dir)
        checked_targets += 1
        if not res.is_valid:
            log(res.format_report(file_label=f"{file_label}#{raw_target}"))
            all_ok = False
    return all_ok, (1 if checked_targets > 0 else 0)


def list_contributes(module_filter: Optional[str] = None) -> int:
    """List all registered contribute points across ecosystem."""
    points = contributes.list_points(module_filter)
    if not points:
        log_info("[core:contributes] No contribution points found.")
        return 0

    log("\nYS-Codebase Registered Contribution Points:")
    log("=" * 85)
    log(f"{'Target Module':<18} | {'Point Key':<20} | {'Type':<12} | {'Description'}")
    log("-" * 85)
    for p in points:
        mod = p.get("module", "")
        pt = p.get("point", "")
        ft = p.get("format_type", "object")
        desc = p.get("description", "")
        if len(desc) > 35:
            desc = desc[:32] + "..."
        log(f"{mod:<18} | {pt:<20} | {ft:<12} | {desc}")
    log("=" * 85)
    log(f"Total points registered: {len(points)}\n")
    return 0


def _check_format_schema_mode(target_or_uri: Optional[str]) -> int:
    """Meta-check on _format.json schema for a given module."""
    mod_name = target_or_uri or "core"
    fmt_uri = f"module.source://{mod_name}/contributes/_format.json"
    if not vfs.exists(fmt_uri):
        fmt_uri = f"module://{mod_name}/contributes/_format.json"
    if not vfs.exists(fmt_uri):
        log_error(f"[core:contributes] [FAIL] Error: Format schema not found for module '{mod_name}' at '{fmt_uri}'.")
        return 1
    try:
        data = vfs.read_json(fmt_uri)
    except Exception as e:
        log_error(f"[core:contributes] [FAIL] Error reading '{fmt_uri}': {e}")
        return 1
    res = ContributesValidator.validate_format_schema(data)
    log(res.format_report(file_label=fmt_uri))
    return 0 if res.is_valid else 1


def _check_single_file_mode(file_uri: str) -> int:
    """Validate a single contributes JSON file or _format.json schema."""
    try:
        p = uri.resolve(file_uri, interactive=False) if "://" in file_uri else os.path.abspath(file_uri)
        if not os.path.isfile(p):
            log_error(f"[core:contributes] [FAIL] File not found: {file_uri}")
            return 1
    except Exception as e:
        log_error(f"[core:contributes] [FAIL] Invalid path/URI '{file_uri}': {e}")
        return 1

    fname = os.path.basename(p)
    if fname.startswith("_"):
        log_info(f"[core:contributes] Checking special metadata file '{fname}' as format schema...")
        try:
            data = vfs.read_json(p) if "://" not in file_uri else vfs.read_json(file_uri)
        except Exception as e:
            log_error(f"[core:contributes] [FAIL] Error reading '{file_uri}': {e}")
            return 1
        res = ContributesValidator.validate_format_schema(data)
        log(res.format_report(file_label=file_uri))
        return 0 if res.is_valid else 1

    parent_dir = os.path.dirname(p.rstrip("/\\"))
    if fname == "contributes.json":
        donor_name = os.path.basename(parent_dir) or "unknown"
        try:
            u_data = vfs.read_json(file_uri) if "://" in file_uri else vfs.read_json(p)
        except Exception as e:
            log_error(f"[core:contributes] [FAIL] Error reading '{file_uri}': {e}")
            return 1
        if not isinstance(u_data, dict):
            log_error(f"[core:contributes] [FAIL] Root of '{file_uri}' must be a JSON object.")
            return 1
        ok, _ = _validate_unified_contributes_payload(u_data, donor_name, parent_dir, file_uri)
        if ok:
            log(f"[PASS] {file_uri}: All contributes declarations are valid.")
            return 0
        return 1

    if fname == "contribute.json":
        raw_target = os.path.basename(parent_dir)
        target_mod = "core" if raw_target == "commands" else raw_target
        donor_mod: Optional[str] = "project"
    else:
        raw_target = fname[:-5]
        target_mod = "core" if raw_target == "commands" else raw_target
        if os.path.basename(parent_dir) == "contributes":
            donor_mod = os.path.basename(os.path.dirname(parent_dir)) or None
        else:
            donor_mod = None

    target_format = contributes.get_format(target_mod)
    if target_format is None:
        log_warn(f"[core:contributes] [WARN] Target module '{target_mod}' does not define a _format.json schema. Skipping validation.")
        return 0

    try:
        data = vfs.read_json(file_uri) if "://" in file_uri else vfs.read_json(p)
    except Exception as e:
        log_error(f"[core:contributes] [FAIL] Error reading '{file_uri}': {e}")
        return 1
    if isinstance(data, dict) and target_mod in data and isinstance(data[target_mod], dict):
        data = data[target_mod]

    res = ContributesValidator.validate(target_mod, data, donor_mod=donor_mod or "", format_schema=target_format, strict_points=True)
    if target_mod == "core":
        inferred_base = parent_dir if fname == "contribute.json" else os.path.dirname(os.path.dirname(p))
        _append_locale_validation_errors(res, donor_mod or target_mod, data, inferred_base)
    log(res.format_report(file_label=file_uri))
    return 0 if res.is_valid else 1


def _check_modules_mode(target_or_uri: Optional[str]) -> int:
    """Validate contributes across one or all installed modules."""
    if target_or_uri:
        mod_uri = f"module://{target_or_uri}"
        cfg_uri = f"config://{target_or_uri}/contribute.json"
        if not vfs.exists(mod_uri) and not vfs.exists(cfg_uri):
            log_error(f"[core:contributes] [FAIL] Module or target not found: {target_or_uri}")
            return 1
        modules_to_check = [target_or_uri]
    else:
        modules_to_check = [d for d in vfs.listdir("module://") if not d.startswith(".")] if vfs.exists("module://") else []
    if not modules_to_check:
        log_info("[core:contributes] No installed modules found to check.")
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
                raw_target = f[:-5]
                target_mod = "core" if raw_target == "commands" else raw_target
                target_format = contributes.get_format(target_mod)
                if target_format is None:
                    continue

                f_uri = f"{contrib_dir}/{f}"
                try:
                    data = vfs.read_json(f_uri)
                except Exception as e:
                    log_error(f"[FAIL] [{f_uri}] JSON syntax error: {e}")
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
                    log(res.format_report(file_label=f_uri))
                    all_passed = False

        # Also check unified module://<donor>/contributes.json if present
        unified_uri = f"module://{donor}/contributes.json"
        if vfs.exists(unified_uri):
            try:
                u_data = vfs.read_json(unified_uri)
                if isinstance(u_data, dict):
                    try:
                        donor_base = uri.resolve(f"module://{donor}", interactive=False)
                    except Exception:
                        donor_base = None
                    u_ok, u_count = _validate_unified_contributes_payload(u_data, donor, donor_base, unified_uri)
                    checked_files_count += u_count
                    if not u_ok:
                        all_passed = False
                else:
                    log_error(f"[FAIL] [{unified_uri}] Root must be a JSON object.")
                    all_passed = False
            except Exception as e:
                log_error(f"[FAIL] [{unified_uri}] JSON syntax error: {e}")
                all_passed = False

        # Also check project-level config://<target>/contribute.json
        cfg_uri = f"config://{donor}/contribute.json"
        if vfs.exists(cfg_uri):
            eff_donor = "core" if donor == "commands" else donor
            target_format = contributes.get_format(eff_donor)
            if target_format is not None:
                try:
                    cfg_data = vfs.read_json(cfg_uri)
                    if isinstance(cfg_data, dict) and eff_donor in cfg_data and isinstance(cfg_data[eff_donor], dict):
                        cfg_data = cfg_data[eff_donor]
                    res = ContributesValidator.validate(eff_donor, cfg_data, donor_mod="project", format_schema=target_format, strict_points=True)
                    if eff_donor == "core":
                        try:
                            cfg_base = uri.resolve(f"config://{donor}", interactive=False)
                        except Exception:
                            cfg_base = None
                        _append_locale_validation_errors(res, "project", cfg_data, cfg_base)
                    checked_files_count += 1
                    if not res.is_valid:
                        log(res.format_report(file_label=cfg_uri))
                        all_passed = False
                except Exception as e:
                    log_error(f"[FAIL] [{cfg_uri}] JSON syntax error: {e}")
                    all_passed = False

    if all_passed:
        log(f"\n[PASS] All contributes definitions are valid! (Checked {checked_files_count} file(s))\n")
        return 0
    log_error("\n[FAIL] Contributes validation failed. Please address the errors above.\n")
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
