"""
YS-Codebase Core Locale & Host Dialect Resolution Engine.
Supports explicit multi-layer fallback chains, two-stage recursive token interpolation,
and deterministic static contract validation based on 'definition' semantic files.

100% Python Standard Library, Zero Third-Party Dependencies.
"""
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import difflib
import json
import locale as _py_locale
import logging
import os
import re
import sys

from core.validator import ValidationIssue, ValidationResult

logger = logging.getLogger("core.locale")

DEFAULT_LOCALE_CHAIN: List[str] = ["zh"]
MAX_INTERPOLATION_DEPTH: int = 5

# Memory cache: abs_file_path -> (mtime, parsed_dict)
_LOCALE_FILE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}

# Sentinel strings for protecting escaped braces '{{' and '}}'
_ESCAPED_LBRACE = "\x00YSCB_LBRACE\x00"
_ESCAPED_RBRACE = "\x00YSCB_RBRACE\x00"
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_.:-]+)\}")


def clear_cache() -> None:
    """Clear the in-memory locale JSON cache."""
    _LOCALE_FILE_CACHE.clear()


def parse_locale_chain(raw_chain: Optional[Union[str, List[str]]]) -> List[str]:
    """
    Normalize a comma-separated string or list of strings into a deduplicated,
    order-preserving list of explicit lang-ids without implicit '-' splitting ([P01:DR-02]).
    """
    if not raw_chain:
        return []

    items: List[str] = []
    if isinstance(raw_chain, str):
        for part in raw_chain.split(","):
            cleaned = part.strip()
            if cleaned:
                items.append(cleaned)
    elif isinstance(raw_chain, (list, tuple)):
        for item in raw_chain:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    items.append(cleaned)

    seen: Set[str] = set()
    result: List[str] = []
    for lang_id in items:
        if lang_id not in seen:
            seen.add(lang_id)
            result.append(lang_id)
    return result


def detect_system_locale_chain(raw_tag: Optional[str] = None) -> List[str]:
    """
    Detect the user's OS primary language and return an explicit fallback chain.
    Extracts only the primary language code (e.g. 'ja_JP.UTF-8' -> ['ja', 'zh'],
    'zh_TW.UTF-8' -> ['zh']) and falls back to ['zh'] (team native language) on
    C/POSIX/unknown environments.
    """
    candidates: List[str] = []
    if raw_tag is not None:
        candidates.append(raw_tag)
    else:
        for env_key in ("LC_ALL", "LC_MESSAGES", "LANG"):
            val = os.environ.get(env_key, "").strip()
            if val:
                candidates.append(val)
        if not candidates and sys.platform == "win32":
            try:
                import ctypes
                lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
                win_loc = _py_locale.windows_locale.get(lang_id, "")
                if win_loc:
                    candidates.append(win_loc)
            except Exception:
                pass
        if not candidates:
            try:
                loc_tuple = _py_locale.getlocale()
                if loc_tuple and loc_tuple[0]:
                    candidates.append(str(loc_tuple[0]))
            except Exception:
                pass

    for raw in candidates:
        cleaned = raw.strip().split(".")[0].split("@")[0].strip()
        if not cleaned or cleaned.upper() in ("C", "POSIX", "UTF-8"):
            continue
        primary = re.split(r"[-_]", cleaned)[0].lower()
        if primary and primary.isalpha() and len(primary) in (2, 3):
            return ["zh"] if primary == "zh" else [primary, "zh"]

    return ["zh"]


def get_active_chain(explicit_chain: Optional[Union[str, List[str]]] = None) -> List[str]:
    """
    Resolve the active explicit priority fallback chain.
    Priority:
      1. explicit_chain argument
      2. YSCB_LOCALE environment variable (comma-separated)
      3. config://core 'locale' setting (list[str] or comma-separated str)
      4. DEFAULT_LOCALE_CHAIN (['zh'])
    """
    if explicit_chain is not None:
        parsed = parse_locale_chain(explicit_chain)
        if parsed:
            return parsed

    env_val = os.environ.get("YSCB_LOCALE", "").strip()
    if env_val:
        parsed = parse_locale_chain(env_val)
        if parsed:
            return parsed

    try:
        from core import config
        cfg_val = config.get("core", "locale", default=None)
        if cfg_val is not None:
            parsed = parse_locale_chain(cfg_val)
            if parsed:
                return parsed
    except Exception:
        pass

    return list(DEFAULT_LOCALE_CHAIN)


def extract_placeholders(template_text: str) -> Set[str]:
    """
    Extract all '{placeholder}' variable names from template_text after stripping
    escaped double-braces '{{' and '}}' (EC-03, [P02:DR-02]).
    """
    if not isinstance(template_text, str) or "{" not in template_text:
        return set()
    sanitized = template_text.replace("{{", _ESCAPED_LBRACE).replace("}}", _ESCAPED_RBRACE)
    return set(_PLACEHOLDER_RE.findall(sanitized))


def _resolve_module_base_dir(module: str, base_dir: Optional[str] = None) -> Optional[str]:
    """Resolve the physical root directory of a module."""
    if base_dir:
        return os.path.abspath(base_dir)
    try:
        from core import uri
        if module == "project":
            return uri.resolve("config://core", interactive=False)
        mod_uri = f"module://{module}"
        if uri.exists(mod_uri):
            return uri.resolve(mod_uri, interactive=False)
        src_uri = f"module.source://{module}"
        if uri.exists(src_uri):
            return uri.resolve(src_uri, interactive=False)
    except Exception:
        pass
    return None


def _is_safe_subpath(base_dir: str, rel_path: str) -> Tuple[bool, str]:
    """
    Verify that rel_path resolves strictly inside base_dir without '..' traversal (EC-05).
    Returns (is_safe, resolved_abs_path).
    """
    if not isinstance(rel_path, str) or not rel_path.strip():
        return False, ""
    norm_base = os.path.realpath(os.path.abspath(base_dir))
    # Reject explicit parent traversal segments or absolute paths
    if os.path.isabs(rel_path):
        return False, os.path.abspath(rel_path)
    candidate = os.path.realpath(os.path.abspath(os.path.join(norm_base, rel_path)))
    is_inside = candidate == norm_base or candidate.startswith(norm_base + os.sep)
    return is_inside, candidate


def _load_json_cached(abs_path: str) -> Optional[Dict[str, Any]]:
    """Load a JSON object with (abs_path, mtime) caching."""
    try:
        if not os.path.isfile(abs_path):
            return None
        mtime = os.path.getmtime(abs_path)
        cached = _LOCALE_FILE_CACHE.get(abs_path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        with open(abs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _LOCALE_FILE_CACHE[abs_path] = (mtime, data)
            return data
    except Exception as e:
        logger.warning(f"Failed to load locale JSON '{abs_path}': {e}")
    return None


def _get_module_locales_decl(module: str, base_dir: Optional[str] = None) -> Dict[str, str]:
    """
    Retrieve the 'locales' file mapping for the specified module.
    1. If base_dir is explicitly provided, read <base_dir>/contributes/core.json directly.
    2. Otherwise query core.contributes.get('core', 'locales') (__modules__[module]),
       or fallback to reading module://<module>/contributes/core.json.
    """
    if base_dir:
        contrib_core_p = os.path.join(base_dir, "contributes", "core.json")
        if os.path.isfile(contrib_core_p):
            data = _load_json_cached(contrib_core_p)
            if isinstance(data, dict) and isinstance(data.get("locales"), dict):
                return {
                    k: v for k, v in data["locales"].items()
                    if not k.startswith("_") and isinstance(v, str)
                }

    try:
        from core import contributes
        merged_locales = contributes.get("core", "locales", default={})
        if isinstance(merged_locales, dict):
            modules_bucket = merged_locales.get("__modules__", {})
            if isinstance(modules_bucket, dict) and isinstance(modules_bucket.get(module), dict):
                return {
                    k: v for k, v in modules_bucket[module].items()
                    if not k.startswith("_") and isinstance(v, str)
                }
            # Fallback if flat dictionary matches the module provider
            if merged_locales.get("__provider__") == module:
                return {
                    k: v for k, v in merged_locales.items()
                    if not k.startswith("_") and isinstance(v, str)
                }
    except Exception:
        pass

    resolved_base = _resolve_module_base_dir(module, base_dir)
    if resolved_base:
        contrib_core_p = os.path.join(resolved_base, "contributes", "core.json")
        if os.path.isfile(contrib_core_p):
            data = _load_json_cached(contrib_core_p)
            if isinstance(data, dict) and isinstance(data.get("locales"), dict):
                return {
                    k: v for k, v in data["locales"].items()
                    if not k.startswith("_") and isinstance(v, str)
                }

    return {}


def get_definition(module: str, base_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Read and return the semantic definition dictionary ('definition') for a module."""
    decl = _get_module_locales_decl(module, base_dir=base_dir)
    def_rel = decl.get("definition")
    if not def_rel:
        return {}
    resolved_base = _resolve_module_base_dir(module, base_dir)
    if not resolved_base:
        return {}
    is_safe, abs_p = _is_safe_subpath(resolved_base, def_rel)
    if not is_safe:
        logger.warning(f"Unsafe locale definition path '{def_rel}' in module '{module}'.")
        return {}
    data = _load_json_cached(abs_p)
    return data if isinstance(data, dict) else {}


def _split_module_key(raw_key: str, explicit_module: Optional[str] = None) -> Tuple[str, str]:
    """Parse '<module>:<key>' or infer module from explicit_module / active context."""
    if ":" in raw_key:
        mod_part, key_part = raw_key.split(":", 1)
        if mod_part.strip() and key_part.strip():
            return mod_part.strip(), key_part.strip()
    if explicit_module and explicit_module.strip():
        return explicit_module.strip(), raw_key
    try:
        from core import uri
        ctx_mod = uri.get_module_context()
        if ctx_mod:
            return ctx_mod, raw_key
    except Exception:
        pass
    return "core", raw_key


def resolve_raw(
    key: str,
    *,
    module: Optional[str] = None,
    chain: Optional[Union[str, List[str]]] = None,
    base_dir: Optional[str] = None,
) -> Optional[Tuple[str, str, str]]:
    """
    Search for `key` strictly along the active explicit fallback chain.
    Returns `(resolved_module, matched_lang_id, raw_template)` or `None` if not found.
    """
    if not isinstance(key, str) or not key.strip():
        return None

    target_mod, clean_key = _split_module_key(key.strip(), explicit_module=module)
    active_chain = get_active_chain(chain)

    # Check project override bucket first if available and no explicit base_dir
    candidate_modules = [target_mod]
    for mod_name in candidate_modules:
        decl = _get_module_locales_decl(mod_name, base_dir=base_dir)
        if not decl:
            continue
        mod_base = _resolve_module_base_dir(mod_name, base_dir=base_dir)
        if not mod_base:
            continue

        for lang_id in active_chain:
            rel_path = decl.get(lang_id)
            if not rel_path:
                continue
            is_safe, abs_path = _is_safe_subpath(mod_base, rel_path)
            if not is_safe:
                continue
            lang_dict = _load_json_cached(abs_path)
            if isinstance(lang_dict, dict) and clean_key in lang_dict:
                val = lang_dict[clean_key]
                if isinstance(val, str):
                    return (mod_name, lang_id, val)

    return None


def _interpolate_template(
    template_str: str,
    current_mod: str,
    active_chain: List[str],
    kwargs: Dict[str, Any],
    base_dir: Optional[str],
    visited: Set[str],
    depth: int,
) -> str:
    """
    Perform two-stage recursive interpolation on `template_str`:
      1. Protect escaped '{{' and '}}'.
      2. Replace '{var}' from `kwargs` if present.
      3. Otherwise recursively resolve '{var}' as a locale/noun token along `active_chain`
         (checking `current_mod` first, then falling back to `'core'` if unprefixed).
      4. Restore escaped '{{' -> '{' and '}}' -> '}'.
    """
    if not isinstance(template_str, str) or "{" not in template_str:
        return template_str

    protected = template_str.replace("{{", _ESCAPED_LBRACE).replace("}}", _ESCAPED_RBRACE)

    def _replace_match(match: re.Match) -> str:
        token = match.group(1)
        if token in kwargs and kwargs[token] is not None:
            return str(kwargs[token])

        if depth >= MAX_INTERPOLATION_DEPTH:
            return match.group(0)

        # Resolve token as a locale / dialect noun reference
        if ":" in token:
            cand_specs = [token]
        else:
            cand_specs = [f"{current_mod}:{token}"]
            if current_mod != "core":
                cand_specs.append(f"core:{token}")

        for spec in cand_specs:
            if spec in visited:
                continue
            spec_mod, spec_key = _split_module_key(spec)
            spec_base = base_dir if spec_mod == current_mod else None
            hit = resolve_raw(spec_key, module=spec_mod, chain=active_chain, base_dir=spec_base)
            if hit is not None:
                resolved_mod, _, raw_sub = hit
                next_visited = set(visited)
                next_visited.add(f"{resolved_mod}:{spec_key}")
                return _interpolate_template(
                    raw_sub,
                    current_mod=resolved_mod,
                    active_chain=active_chain,
                    kwargs=kwargs,
                    base_dir=spec_base,
                    visited=next_visited,
                    depth=depth + 1,
                )

        # Unknown placeholder: preserve literal '{token}' without raising KeyError (EC-03)
        return match.group(0)

    interpolated = _PLACEHOLDER_RE.sub(_replace_match, protected)
    return interpolated.replace(_ESCAPED_LBRACE, "{").replace(_ESCAPED_RBRACE, "}")


def t(
    key: str,
    *,
    module: Optional[str] = None,
    chain: Optional[Union[str, List[str]]] = None,
    default: Optional[str] = None,
    base_dir: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """
    Retrieve localized message for `key` along the explicit fallback chain and perform
    parameter formatting + recursive proper-noun interpolation (FR-03, FR-04).
    """
    active_chain = get_active_chain(chain)
    hit = resolve_raw(key, module=module, chain=active_chain, base_dir=base_dir)
    if hit is None:
        fallback_text = default if default is not None else key
        target_mod, clean_key = _split_module_key(key, explicit_module=module)
        return _interpolate_template(
            fallback_text,
            current_mod=target_mod,
            active_chain=active_chain,
            kwargs=kwargs,
            base_dir=base_dir,
            visited={f"{target_mod}:{clean_key}"},
            depth=0,
        )

    resolved_mod, _, raw_template = hit
    _, clean_key = _split_module_key(key, explicit_module=resolved_mod)
    return _interpolate_template(
        raw_template,
        current_mod=resolved_mod,
        active_chain=active_chain,
        kwargs=kwargs,
        base_dir=base_dir,
        visited={f"{resolved_mod}:{clean_key}"},
        depth=0,
    )


translate = t


def validate_module_locales(
    module_name: str,
    locales_decl: Dict[str, Any],
    base_dir: Optional[str] = None,
) -> ValidationResult:
    """
    Rigidly validate a module's 'locales' declaration against its 'definition' contract:
      1. Verify 'definition' key exists and points to a valid JSON object inside module root.
      2. Verify every key in 'definition' is an object with a non-empty string 'description'
         and optional 'placeholders' (list of strings).
      3. Verify every '<lang-id>' file exists inside module root, is a valid JSON object,
         contains no orphan keys (keys absent from 'definition'), and its '{placeholder}'
         set matches 'definition[key].placeholders' ([P04:DR-01]).
    """
    issues: List[ValidationIssue] = []

    if not isinstance(locales_decl, dict):
        issues.append(ValidationIssue(
            path="locales",
            message=f"Expected object/dict for 'locales', got {type(locales_decl).__name__}.",
            severity="ERROR",
        ))
        return ValidationResult(is_valid=False, issues=issues)

    clean_decl = {k: v for k, v in locales_decl.items() if not str(k).startswith("_")}
    if "definition" not in clean_decl or not isinstance(clean_decl.get("definition"), str) or not clean_decl["definition"].strip():
        issues.append(ValidationIssue(
            path="locales.definition",
            message="Missing required non-empty string field 'definition' (semantic contract file path).",
            severity="ERROR",
        ))
        return ValidationResult(is_valid=False, issues=issues)

    resolved_base = _resolve_module_base_dir(module_name, base_dir=base_dir)
    if not resolved_base or not os.path.isdir(resolved_base):
        issues.append(ValidationIssue(
            path="locales",
            message=f"Cannot resolve base directory for module '{module_name}'.",
            severity="ERROR",
        ))
        return ValidationResult(is_valid=False, issues=issues)

    # 1. Validate 'definition' file
    def_rel = clean_decl["definition"].strip()
    is_safe, def_abs = _is_safe_subpath(resolved_base, def_rel)
    if not is_safe:
        issues.append(ValidationIssue(
            path="locales.definition",
            message=f"Path traversal or outside-module path rejected: '{def_rel}'.",
            severity="ERROR",
        ))
        return ValidationResult(is_valid=False, issues=issues)

    if not os.path.isfile(def_abs):
        issues.append(ValidationIssue(
            path="locales.definition",
            message=f"Locale definition file not found: '{def_rel}'.",
            severity="ERROR",
        ))
        return ValidationResult(is_valid=False, issues=issues)

    try:
        with open(def_abs, "r", encoding="utf-8") as f:
            def_data = json.load(f)
    except Exception as e:
        issues.append(ValidationIssue(
            path="locales.definition",
            message=f"Invalid JSON syntax in '{def_rel}': {e}",
            severity="ERROR",
        ))
        return ValidationResult(is_valid=False, issues=issues)

    if not isinstance(def_data, dict):
        issues.append(ValidationIssue(
            path="locales.definition",
            message=f"Locale definition file '{def_rel}' must contain a top-level JSON object.",
            severity="ERROR",
        ))
        return ValidationResult(is_valid=False, issues=issues)

    expected_placeholders_map: Dict[str, Set[str]] = {}
    for def_key, def_spec in def_data.items():
        if str(def_key).startswith("_"):
            continue
        k_path = f"locales.definition.{def_key}"
        if not isinstance(def_spec, dict):
            issues.append(ValidationIssue(
                path=k_path,
                message=f"Definition entry '{def_key}' must be an object with 'description' and optional 'placeholders'.",
                severity="ERROR",
            ))
            continue

        desc = def_spec.get("description")
        if not isinstance(desc, str) or not desc.strip():
            issues.append(ValidationIssue(
                path=f"{k_path}.description",
                message=f"Definition entry '{def_key}' is missing a non-empty string 'description'.",
                severity="ERROR",
            ))

        ph_list = def_spec.get("placeholders", [])
        if not isinstance(ph_list, list) or any(not isinstance(p, str) or not p.strip() for p in ph_list):
            issues.append(ValidationIssue(
                path=f"{k_path}.placeholders",
                message=f"'placeholders' in definition entry '{def_key}' must be a list of non-empty strings.",
                severity="ERROR",
            ))
            expected_placeholders_map[def_key] = set()
        else:
            expected_placeholders_map[def_key] = {p.strip() for p in ph_list}

    defined_keys = sorted(list(expected_placeholders_map.keys()))

    # 2. Validate each '<lang-id>' file against 'definition'
    for lang_id, lang_rel in clean_decl.items():
        if lang_id == "definition":
            continue
        l_path = f"locales.{lang_id}"
        if not isinstance(lang_rel, str) or not lang_rel.strip():
            issues.append(ValidationIssue(
                path=l_path,
                message=f"Locale file path for '{lang_id}' must be a non-empty string.",
                severity="ERROR",
            ))
            continue

        l_safe, l_abs = _is_safe_subpath(resolved_base, lang_rel.strip())
        if not l_safe:
            issues.append(ValidationIssue(
                path=l_path,
                message=f"Path traversal or outside-module path rejected for '{lang_id}': '{lang_rel}'.",
                severity="ERROR",
            ))
            continue

        if not os.path.isfile(l_abs):
            issues.append(ValidationIssue(
                path=l_path,
                message=f"Locale file for '{lang_id}' not found: '{lang_rel}'.",
                severity="ERROR",
            ))
            continue

        try:
            with open(l_abs, "r", encoding="utf-8") as f:
                lang_data = json.load(f)
        except Exception as e:
            issues.append(ValidationIssue(
                path=l_path,
                message=f"Invalid JSON syntax in locale file '{lang_rel}': {e}",
                severity="ERROR",
            ))
            continue

        if not isinstance(lang_data, dict):
            issues.append(ValidationIssue(
                path=l_path,
                message=f"Locale file '{lang_rel}' must contain a top-level JSON object.",
                severity="ERROR",
            ))
            continue

        for t_key, t_val in lang_data.items():
            if str(t_key).startswith("_"):
                continue
            tk_path = f"locales.{lang_id}.{t_key}"
            if t_key not in expected_placeholders_map:
                matches = difflib.get_close_matches(str(t_key), defined_keys, n=1)
                hint = f"Did you mean '{matches[0]}'?" if matches else f"Key must be declared in '{def_rel}' first."
                issues.append(ValidationIssue(
                    path=tk_path,
                    message=f"Orphan locale key '{t_key}' in '{lang_id}' is not defined in '{def_rel}'.",
                    severity="ERROR",
                    suggestion=hint,
                ))
                continue

            if not isinstance(t_val, str):
                issues.append(ValidationIssue(
                    path=tk_path,
                    message=f"Localized value for '{t_key}' in '{lang_id}' must be a string, got {type(t_val).__name__}.",
                    severity="ERROR",
                ))
                continue

            actual_phs = extract_placeholders(t_val)
            expected_phs = expected_placeholders_map[t_key]
            missing_phs = sorted(list(expected_phs - actual_phs))
            unknown_phs = sorted(list(actual_phs - expected_phs))
            if missing_phs or unknown_phs:
                parts = []
                if missing_phs:
                    parts.append(f"missing required placeholder(s): {missing_phs}")
                if unknown_phs:
                    parts.append(f"undeclared placeholder(s): {unknown_phs}")
                issues.append(ValidationIssue(
                    path=tk_path,
                    message=f"Placeholder contract mismatch for '{t_key}' in '{lang_id}': {'; '.join(parts)}.",
                    severity="ERROR",
                    suggestion=f"Expected placeholders from '{def_rel}': {sorted(list(expected_phs))}",
                ))

    is_valid = len([i for i in issues if i.severity == "ERROR"]) == 0
    return ValidationResult(is_valid=is_valid, issues=issues, payload=locales_decl)
