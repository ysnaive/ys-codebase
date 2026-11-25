"""2x2 strongly-typed configuration matrix store implementing ConfigViewPort."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
from types import MappingProxyType
from typing import Final, Mapping, Optional, Sequence, TypeVar

from core.filesystem.fs import (
    IGNORED_FS_PREFIXES,
    MAX_JSON_FILE_BYTES,
    atomic_write_bytes,
    atomic_write_json,
    has_symlink_raw_path,
    hash_nofollow_regular_sha256,
    is_atomic_staging_filename,
    is_symlink_or_reparse,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
    walk_nonsymlink_dir_tree,
)
from core.foundation.codec import DataclassCodec, resolve_dataclass_init_hints
from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary
from core.foundation.primitives import (
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    MutableJsonObject,
    SemVer4,
    require_pure_bool,
    require_pure_str,
    strict_parse_json_object,
    validate_relative_segment,
)
from core.metadata.config.manifest import cfg_assert_not_reserved_module_id
from core.metadata.config.infill import (
    DeepInfiller,
    cfg_clone_json_object,
    cfg_clone_json_value,
    cfg_deep_merge_json_objects,
)

TConfig = TypeVar("TConfig")

_CFG_HOST_FILENAME: Final[str] = "yscb.config.json"
_CFG_HOST_LOCAL_FILENAME: Final[str] = "yscb.config.local.json"
_CFG_PROJECT_DIRNAME: Final[str] = "config"
_CFG_LOCAL_DIRNAME: Final[str] = ".config.local"
_CFG_MODULES_DIRNAME: Final[str] = ".modules"
_CFG_MOD_PROJECT_FILENAME: Final[str] = "config.project.json"
_CFG_MOD_LOCAL_FILENAME: Final[str] = "config.local.json"
_CFG_MOD_SCHEMA_FILENAME: Final[str] = "config.schema.json"
_CFG_TMPL_SUFFIX: Final[str] = ".tmpl"
_CFG_HOST_LOCAL_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(
    {"yscb_root", "default_provider"}
)


@dataclass(frozen=True, slots=True)
class _CfgStatSignature:
    exists: bool
    mtime_ns: int = 0
    size: int = 0
    ino: int = 0
    is_symlink: bool = False


@dataclass(frozen=True, slots=True)
class _CfgModuleCacheEntry:
    proj_sig: _CfgStatSignature
    local_sig: _CfgStatSignature
    merged: MutableJsonObject


def _cfg_stat_signature(target: HostPath) -> _CfgStatSignature:
    raw = str(target)
    if has_symlink_raw_path(raw) or is_symlink_or_reparse(raw):
        return _CfgStatSignature(exists=True, mtime_ns=-1, size=-1, ino=-1, is_symlink=True)
    try:
        st = os.stat(raw, follow_symlinks=False)
    except OSError:
        return _CfgStatSignature(exists=False)
    if not stat.S_ISREG(st.st_mode):
        return _CfgStatSignature(exists=True, mtime_ns=-1, size=-1, ino=-1)
    return _CfgStatSignature(
        exists=True,
        mtime_ns=st.st_mtime_ns,
        size=st.st_size,
        ino=st.st_ino,
    )


def _cfg_require_host_path(val: object, label: str) -> HostPath:
    if not isinstance(val, HostPath):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"{label} must be HostPath, got {val!r}")
    if has_symlink_raw_path(str(val)):
        raise YscbError(ErrorCode.SECURITY_GATED, f"Refusing symlink {label}: {val}")
    return val


def _cfg_require_module_id(val: object) -> ModuleId:
    if not isinstance(val, ModuleId):
        raise YscbError(ErrorCode.CONFIG_INVALID, f"module_id must be ModuleId, got {val!r}")
    cfg_assert_not_reserved_module_id(val, "module_id")
    return val


def _cfg_validate_key_segments(key: object) -> tuple[str, ...]:
    try:
        clean_key = require_pure_str(key, "config key", non_empty=True)
    except ValueError as exc:
        raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
    if "." not in clean_key:
        return (clean_key,)
    parts = tuple(clean_key.split("."))
    if any(not p for p in parts):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Invalid dotted configuration key with empty segment: {clean_key!r}",
        )
    return parts


def _cfg_read_strict_json_file(
    root: HostPath,
    *parts: str,
    required: bool,
) -> Optional[MutableJsonObject]:
    target = resolve_contained_subpath(root, *parts)
    raw_target = str(target)
    if not os.path.lexists(raw_target):
        if required:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Missing required configuration file: {target}",
            )
        return None
    try:
        raw_bytes = read_nofollow_regular_bytes(raw_target, max_bytes=MAX_JSON_FILE_BYTES)
    except OSError as exc:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Failed reading configuration file '{target}': {safe_exception_summary(exc)}",
        ) from exc
    if raw_bytes is None:
        if has_symlink_raw_path(raw_target) or is_symlink_or_reparse(raw_target):
            raise YscbError(
                ErrorCode.SECURITY_GATED,
                f"Refusing symlinked configuration file: {target}",
            )
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Configuration path is not a readable bounded regular file: {target}",
        )
    try:
        return strict_parse_json_object(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Malformed JSON object in '{target}': {safe_exception_summary(exc)}",
        ) from exc


def _cfg_deref_json_schema(schema: JsonObject, defs: JsonObject, depth: int = 0) -> JsonObject:
    cur = schema
    hops = depth
    while hops < 24 and type(cur.get("$ref")) is str:
        ref_str = str(cur["$ref"])
        ref_name: Optional[str] = None
        if ref_str.startswith("#/$defs/"):
            ref_name = ref_str[len("#/$defs/") :]
        elif ref_str.startswith("#/definitions/"):
            ref_name = ref_str[len("#/definitions/") :]
        if ref_name is None or not isinstance(defs.get(ref_name), Mapping):
            break
        target = defs[ref_name]
        if not isinstance(target, Mapping):
            break
        cur = target
        hops += 1
    return cur


def _cfg_extract_json_schema_defaults(
    schema: JsonObject,
    defs: JsonObject,
    depth: int = 0,
) -> MutableJsonObject:
    if depth > 16:
        return {}
    resolved = _cfg_deref_json_schema(schema, defs, depth)
    out: MutableJsonObject = {}
    top_def = resolved.get("default")
    if isinstance(top_def, Mapping):
        out = cfg_clone_json_object(top_def, label="config schema default")
    props = resolved.get("properties")
    if isinstance(props, Mapping):
        for prop_key, prop_sc in props.items():
            if type(prop_key) is not str or not isinstance(prop_sc, Mapping):
                continue
            res_prop = _cfg_deref_json_schema(prop_sc, defs, depth + 1)
            if "default" in res_prop:
                out[prop_key] = cfg_clone_json_value(res_prop["default"], label=f"schema default {prop_key}")
            elif res_prop.get("type") == "object" and prop_key not in out:
                sub_defs = _cfg_extract_json_schema_defaults(res_prop, defs, depth + 1)
                if sub_defs:
                    out[prop_key] = sub_defs
    return out


def _cfg_matches_single_json_type(val: JsonValue, expected_type: str) -> bool:
    if expected_type == "null":
        return val is None
    if expected_type == "boolean":
        return type(val) is bool
    if expected_type == "integer":
        return type(val) is int
    if expected_type == "number":
        return type(val) in (int, float)
    if expected_type == "string":
        return type(val) is str
    if expected_type == "array":
        return isinstance(val, list)
    if expected_type == "object":
        return isinstance(val, Mapping)
    return True


def _cfg_validate_json_schema_node(
    val: JsonValue,
    raw_schema: JsonObject,
    defs: JsonObject,
    ptr: str,
    depth: int = 0,
) -> None:
    if depth > 32:
        return
    schema = _cfg_deref_json_schema(raw_schema, defs, depth)
    loc = ptr or "/"

    if "const" in schema:
        expected_c = schema["const"]
        if type(val) is not type(expected_c) or val != expected_c:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': expected const {expected_c!r}.")

    raw_enum = schema.get("enum")
    if isinstance(raw_enum, list):
        if not any(type(val) is type(ev) and val == ev for ev in raw_enum):
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': value {val!r} not in enum {raw_enum!r}.")

    for comb_key in ("allOf",):
        comb_list = schema.get(comb_key)
        if isinstance(comb_list, list):
            for sub_sc in comb_list:
                if isinstance(sub_sc, Mapping):
                    _cfg_validate_json_schema_node(val, sub_sc, defs, ptr, depth + 1)

    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and any_of:
        matched_any = False
        for branch in any_of:
            if not isinstance(branch, Mapping):
                continue
            try:
                _cfg_validate_json_schema_node(val, branch, defs, ptr, depth + 1)
                matched_any = True
                break
            except YscbError:
                continue
        if not matched_any:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': value {val!r} did not match anyOf schema.")

    one_of = schema.get("oneOf")
    if isinstance(one_of, list) and one_of:
        match_cnt = 0
        for branch in one_of:
            if not isinstance(branch, Mapping):
                continue
            try:
                _cfg_validate_json_schema_node(val, branch, defs, ptr, depth + 1)
                match_cnt += 1
            except YscbError:
                continue
        if match_cnt != 1:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': value {val!r} matched {match_cnt} oneOf branches (expected 1).")

    raw_type = schema.get("type")
    if type(raw_type) is str:
        if not _cfg_matches_single_json_type(val, raw_type):
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': expected JSON type '{raw_type}', got {type(val).__name__}.")
    elif isinstance(raw_type, list) and raw_type:
        type_names = [t for t in raw_type if type(t) is str]
        if type_names and not any(_cfg_matches_single_json_type(val, t) for t in type_names):
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': expected JSON type in {type_names!r}, got {type(val).__name__}.")

    if type(val) in (int, float):
        min_v = schema.get("minimum")
        max_v = schema.get("maximum")
        if type(min_v) in (int, float) and val < min_v:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': {val} < minimum {min_v}.")
        if type(max_v) in (int, float) and val > max_v:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': {val} > maximum {max_v}.")

    if type(val) is str:
        min_l = schema.get("minLength")
        max_l = schema.get("maxLength")
        if type(min_l) is int and len(val) < min_l:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': string shorter than minLength {min_l}.")
        if type(max_l) is int and len(val) > max_l:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': string longer than maxLength {max_l}.")

    if isinstance(val, list):
        min_i = schema.get("minItems")
        max_i = schema.get("maxItems")
        if type(min_i) is int and len(val) < min_i:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': array has fewer than {min_i} items.")
        if type(max_i) is int and len(val) > max_i:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': array exceeds {max_i} items.")
        pfx_items = schema.get("prefixItems")
        if isinstance(pfx_items, list):
            if schema.get("items") is False and len(val) > len(pfx_items):
                raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': tuple array exceeds {len(pfx_items)} elements.")
            for idx, (sub_v, sub_s) in enumerate(zip(val, pfx_items)):
                if isinstance(sub_s, Mapping):
                    _cfg_validate_json_schema_node(sub_v, sub_s, defs, f"{ptr}/{idx}", depth + 1)
        items_sc = schema.get("items")
        if isinstance(items_sc, Mapping):
            start_i = len(pfx_items) if isinstance(pfx_items, list) else 0
            for idx in range(start_i, len(val)):
                _cfg_validate_json_schema_node(val[idx], items_sc, defs, f"{ptr}/{idx}", depth + 1)

    if isinstance(val, Mapping):
        req_keys = schema.get("required")
        if isinstance(req_keys, list):
            for rk in req_keys:
                if type(rk) is str and rk not in val:
                    raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': missing required property {rk!r}.")
        props = schema.get("properties")
        props_map = props if isinstance(props, Mapping) else {}
        add_props = schema.get("additionalProperties", True)
        for k, v in val.items():
            child_ptr = f"{ptr}/{k}"
            if k in props_map:
                p_sc = props_map[k]
                if isinstance(p_sc, Mapping):
                    _cfg_validate_json_schema_node(v, p_sc, defs, child_ptr, depth + 1)
            elif add_props is False:
                raise YscbError(ErrorCode.CONFIG_INVALID, f"Config violation at '{loc}': unknown configuration property {k!r}.")
            elif isinstance(add_props, Mapping):
                _cfg_validate_json_schema_node(v, add_props, defs, child_ptr, depth + 1)


def _cfg_validate_against_module_disk_schema(
    yscb_root: HostPath,
    mod_id: ModuleId,
    candidate_doc: JsonObject,
) -> None:
    schema_doc = _cfg_read_strict_json_file(
        yscb_root,
        _CFG_MODULES_DIRNAME,
        mod_id.value,
        _CFG_MOD_SCHEMA_FILENAME,
        required=False,
    )
    if schema_doc is None:
        return
    raw_defs = schema_doc.get("$defs")
    if not isinstance(raw_defs, Mapping):
        raw_defs = schema_doc.get("definitions")
    defs_map: JsonObject = raw_defs if isinstance(raw_defs, Mapping) else {}
    defaults_doc = _cfg_extract_json_schema_defaults(schema_doc, defs_map)
    effective_doc = cfg_deep_merge_json_objects(defaults_doc, candidate_doc)
    _cfg_validate_json_schema_node(effective_doc, schema_doc, defs_map, "")


def _cfg_write_json_checked(dest: HostPath, payload: JsonObject) -> None:
    try:
        atomic_write_json(dest, payload)
    except YscbError:
        raise
    except (OSError, ValueError) as exc:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Failed writing configuration file '{dest}': {safe_exception_summary(exc)}",
        ) from exc


def _cfg_write_bytes_checked(dest: HostPath, data: bytes) -> None:
    try:
        atomic_write_bytes(dest, data)
    except YscbError:
        raise
    except (OSError, ValueError) as exc:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Failed writing configuration file '{dest}': {safe_exception_summary(exc)}",
        ) from exc


def _cfg_extract_dataclass_defaults(schema_cls: type[object]) -> MutableJsonObject:
    if not isinstance(schema_cls, type) or not dataclasses.is_dataclass(schema_cls):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Expected @dataclass configuration type, got {schema_cls!r}",
        )
    try:
        hints = resolve_dataclass_init_hints(schema_cls)
    except YscbError as exc:
        raise YscbError(ErrorCode.CONFIG_INVALID, exc.detail.message) from exc
    except (NameError, TypeError, ValueError) as exc:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Invalid type annotations on {schema_cls.__name__}: {safe_exception_summary(exc)}",
        ) from exc
    defaults_out: MutableJsonObject = {}
    for fld in dataclasses.fields(schema_cls):
        if not fld.init:
            continue
        if fld.default is not dataclasses.MISSING:
            sample = fld.default
        elif fld.default_factory is not dataclasses.MISSING:
            try:
                sample = fld.default_factory()
            except Exception as exc:
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"Default factory failed on {schema_cls.__name__}.{fld.name}: {safe_exception_summary(exc)}",
                ) from exc
        else:
            continue
        try:
            if fld.name in hints:
                defaults_out[fld.name] = DataclassCodec.encode_typed(hints[fld.name], sample)
            else:
                defaults_out[fld.name] = DataclassCodec.encode(sample)
        except YscbError as exc:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Invalid default value on {schema_cls.__name__}.{fld.name}: {exc.detail.message}",
            ) from exc
    return defaults_out


def _cfg_decode_with_schema(schema_cls: type[TConfig], merged_doc: JsonObject) -> TConfig:
    base_defaults = _cfg_extract_dataclass_defaults(schema_cls)
    effective_doc = cfg_deep_merge_json_objects(base_defaults, merged_doc)
    try:
        return DataclassCodec.decode(schema_cls, effective_doc)
    except YscbError as exc:
        if exc.detail.code == ErrorCode.CONFIG_INVALID:
            raise
        raise YscbError(ErrorCode.CONFIG_INVALID, exc.detail.message) from exc
    except (TypeError, ValueError) as exc:
        raise YscbError(ErrorCode.CONFIG_INVALID, safe_exception_summary(exc)) from exc


def _cfg_apply_set_key(
    doc: MutableJsonObject,
    raw_key: str,
    parts: tuple[str, ...],
    cloned_val: JsonValue,
) -> None:
    if len(parts) == 1 or raw_key in doc:
        doc[raw_key] = cloned_val
        return
    cur: MutableJsonObject = doc
    for seg in parts[:-1]:
        if seg not in cur:
            nxt: MutableJsonObject = {}
            cur[seg] = nxt
            cur = nxt
            continue
        existing_sub = cur[seg]
        if not isinstance(existing_sub, dict):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Cannot set nested key {raw_key!r}: segment {seg!r} holds non-object value.",
            )
        cur = existing_sub
    cur[parts[-1]] = cloned_val


def _cfg_apply_unset_key(
    doc: MutableJsonObject,
    raw_key: str,
    parts: tuple[str, ...],
) -> bool:
    if raw_key in doc:
        del doc[raw_key]
        return True
    if len(parts) == 1:
        return False
    trail: list[tuple[MutableJsonObject, str]] = []
    cur: MutableJsonObject = doc
    for seg in parts[:-1]:
        nxt = cur.get(seg)
        if not isinstance(nxt, dict):
            return False
        trail.append((cur, seg))
        cur = nxt
    leaf = parts[-1]
    if leaf not in cur:
        return False
    del cur[leaf]
    for parent_map, child_key in reversed(trail):
        child_obj = parent_map.get(child_key)
        if isinstance(child_obj, dict) and not child_obj:
            del parent_map[child_key]
        else:
            break
    return True


def _cfg_collect_staging_templates(
    staging_dir: HostPath,
) -> tuple[tuple[str, bytes], ...]:
    raw_root = str(staging_dir)
    if has_symlink_raw_path(raw_root):
        raise YscbError(
            ErrorCode.SECURITY_GATED,
            f"Refusing symlinked staging configurable directory: {staging_dir}",
        )
    if not os.path.lexists(raw_root):
        return ()
    if not os.path.isdir(raw_root):
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"staging_configurable_dir must be a directory: {staging_dir}",
        )
    collected: list[tuple[str, bytes]] = []
    stack: list[tuple[str, tuple[str, ...]]] = [(raw_root, ())]
    while stack:
        cur_dir, rel_prefix = stack.pop()
        try:
            with os.scandir(cur_dir) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"Failed scanning '{cur_dir}': {safe_exception_summary(exc)}",
            ) from exc
        sub_dirs: list[tuple[str, tuple[str, ...]]] = []
        for ent in entries:
            if ent.is_symlink() or is_symlink_or_reparse(ent.path):
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Refusing symlink inside configurable staging directory: {ent.path}",
                )
            try:
                validate_relative_segment(ent.name, label="configurable entry")
            except ValueError as exc:
                raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
            try:
                is_dir = ent.is_dir(follow_symlinks=False)
                is_reg = ent.is_file(follow_symlinks=False)
            except OSError as exc:
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"Failed stat on '{ent.path}': {safe_exception_summary(exc)}",
                ) from exc
            if is_dir:
                sub_dirs.append((ent.path, (*rel_prefix, ent.name)))
                continue
            if not is_reg:
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"Unsupported non-regular file in configurable directory: {ent.path}",
                )
            if not ent.name.endswith(_CFG_TMPL_SUFFIX):
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"All files in configurable/ must end with '.tmpl', got {ent.name!r}",
                )
            stripped_name = ent.name[: -len(_CFG_TMPL_SUFFIX)]
            try:
                validate_relative_segment(stripped_name, label="configurable target filename")
            except ValueError as exc:
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"Invalid target filename derived from template {ent.name!r}: {exc}",
                ) from exc
            try:
                file_bytes = read_nofollow_regular_bytes(ent.path, max_bytes=MAX_JSON_FILE_BYTES)
            except OSError as exc:
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"Failed reading configurable template '{ent.path}': {safe_exception_summary(exc)}",
                ) from exc
            if file_bytes is None:
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"Unreadable or oversized configurable template (> 4 MiB): {ent.path}",
                )
            rel_posix = "/".join((*rel_prefix, stripped_name))
            collected.append((rel_posix, file_bytes))
        stack.extend(reversed(sub_dirs))
    collected.sort(key=lambda item: item[0])
    return tuple(collected)


def _cfg_hash_single_config_file(raw_path: str) -> Optional[str]:
    if has_symlink_raw_path(raw_path) or not os.path.lexists(raw_path):
        return None
    try:
        return _cfg_hash_existing_config_file(raw_path)
    except FileNotFoundError:
        return None


def _cfg_hash_existing_config_file(raw_path: str) -> Optional[str]:
    if raw_path.lower().endswith(".json"):
        try:
            raw_bytes = read_nofollow_regular_bytes(raw_path, max_bytes=MAX_JSON_FILE_BYTES)
        except OSError:
            raw_bytes = None
        if raw_bytes is not None:
            try:
                parsed = strict_parse_json_object(raw_bytes.decode("utf-8"))
                canonical = json.dumps(
                    parsed,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    allow_nan=False,
                ).encode("utf-8")
                return "json:" + hashlib.sha256(canonical).hexdigest()
            except (UnicodeDecodeError, ValueError):
                return "raw:" + hashlib.sha256(raw_bytes).hexdigest()
    digest = hash_nofollow_regular_sha256(raw_path)
    return f"raw:{digest}" if digest else None


def _cfg_collect_dir_fingerprints(root_dir: HostPath, area_tag: str) -> list[tuple[str, str]]:
    raw_root = str(root_dir)
    if has_symlink_raw_path(raw_root) or not os.path.isdir(raw_root):
        return []
    records: list[tuple[str, str]] = []
    for cur_dir, entries in walk_nonsymlink_dir_tree(raw_root):
        rel_dir = os.path.relpath(cur_dir, raw_root)
        dir_parts = () if rel_dir in ("", ".") else tuple(Path(rel_dir).parts)
        for ent in entries:
            if (
                ent.name.startswith(IGNORED_FS_PREFIXES)
                or is_atomic_staging_filename(ent.name)
                or ent.is_symlink()
                or is_symlink_or_reparse(ent.path)
            ):
                continue
            try:
                if not ent.is_file(follow_symlinks=False):
                    continue
            except OSError:
                continue
            f_digest = _cfg_hash_single_config_file(ent.path)
            if f_digest is not None:
                rel_posix = "/".join((*dir_parts, ent.name))
                records.append((f"{area_tag}:{rel_posix}", f_digest))
    records.sort(key=lambda item: item[0])
    return records


@dataclass(frozen=True, slots=True)
class InstalledModuleRecord:
    """Installed module version, timestamp, and provenance record in yscb.config.json."""

    version: SemVer4
    installed_at: str
    provider: str

    def __post_init__(self) -> None:
        if not isinstance(self.version, SemVer4):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"InstalledModuleRecord.version must be SemVer4, got {self.version!r}",
            )
        try:
            require_pure_str(self.installed_at, "InstalledModuleRecord.installed_at", non_empty=True)
            require_pure_str(self.provider, "InstalledModuleRecord.provider", non_empty=True)
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc


@dataclass(frozen=True, slots=True)
class HostConfig:
    """Merged host configuration from yscb.config.json and yscb.config.local.json."""

    yscb_root: str
    default_provider: str
    installed_modules: Mapping[ModuleId, InstalledModuleRecord]

    def __post_init__(self) -> None:
        try:
            require_pure_str(self.yscb_root, "HostConfig.yscb_root", non_empty=True)
            require_pure_str(self.default_provider, "HostConfig.default_provider", non_empty=True)
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
        if not isinstance(self.installed_modules, Mapping):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"HostConfig.installed_modules must be Mapping, got {type(self.installed_modules).__name__}",
            )
        frozen_mods: dict[ModuleId, InstalledModuleRecord] = {}
        for mod_id, rec in self.installed_modules.items():
            if not isinstance(mod_id, ModuleId):
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"HostConfig.installed_modules keys must be ModuleId, got {mod_id!r}",
                )
            cfg_assert_not_reserved_module_id(mod_id, "HostConfig.installed_modules key")
            if not isinstance(rec, InstalledModuleRecord):
                raise YscbError(
                    ErrorCode.CONFIG_INVALID,
                    f"HostConfig.installed_modules[{mod_id}] must be InstalledModuleRecord, got {rec!r}",
                )
            frozen_mods[mod_id] = rec
        object.__setattr__(self, "installed_modules", MappingProxyType(frozen_mods))


class ConfigStore:
    """2x2 configuration matrix store and typed reader structurally satisfying ConfigViewPort."""

    def __init__(self, *, host_dir: HostPath, yscb_root: HostPath) -> None:
        self._host_dir = _cfg_require_host_path(host_dir, "ConfigStore.host_dir")
        self._yscb_root = _cfg_require_host_path(yscb_root, "ConfigStore.yscb_root")
        self._guard = threading.RLock()
        self._module_cache: dict[ModuleId, _CfgModuleCacheEntry] = {}

    def load_host_config(self) -> HostConfig:
        with self._guard:
            base_doc = _cfg_read_strict_json_file(
                self._host_dir,
                _CFG_HOST_FILENAME,
                required=True,
            )
            if base_doc is None:
                raise YscbError(ErrorCode.CONFIG_INVALID, "Missing yscb.config.json")
            try:
                DataclassCodec.decode(HostConfig, base_doc)
            except YscbError as exc:
                if exc.detail.code == ErrorCode.CONFIG_INVALID:
                    raise
                raise YscbError(ErrorCode.CONFIG_INVALID, exc.detail.message) from exc
            local_doc = _cfg_read_strict_json_file(
                self._host_dir,
                _CFG_HOST_LOCAL_FILENAME,
                required=False,
            )
            if local_doc is None:
                effective = base_doc
            else:
                unknown_local = sorted(set(local_doc.keys()) - _CFG_HOST_LOCAL_ALLOWED_KEYS)
                if unknown_local:
                    raise YscbError(
                        ErrorCode.CONFIG_INVALID,
                        f"Unknown keys in {_CFG_HOST_LOCAL_FILENAME}: {unknown_local}",
                    )
                effective = cfg_deep_merge_json_objects(base_doc, local_doc)
            try:
                return DataclassCodec.decode(HostConfig, effective)
            except YscbError as exc:
                if exc.detail.code == ErrorCode.CONFIG_INVALID:
                    raise
                raise YscbError(ErrorCode.CONFIG_INVALID, exc.detail.message) from exc

    def save_host_config(self, config: HostConfig) -> None:
        if not isinstance(config, HostConfig):
            raise YscbError(
                ErrorCode.CONFIG_INVALID,
                f"save_host_config requires HostConfig, got {config!r}",
            )
        try:
            encoded = DataclassCodec.encode_object(config, expected_type=HostConfig)
        except YscbError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, exc.detail.message) from exc
        with self._guard:
            base_doc = _cfg_read_strict_json_file(
                self._host_dir,
                _CFG_HOST_FILENAME,
                required=False,
            )
            local_doc = _cfg_read_strict_json_file(
                self._host_dir,
                _CFG_HOST_LOCAL_FILENAME,
                required=False,
            )
            out_doc: MutableJsonObject = dict(base_doc) if base_doc is not None else {}
            out_doc["installed_modules"] = encoded["installed_modules"]
            for scalar_key in ("yscb_root", "default_provider"):
                if (
                    base_doc is not None
                    and local_doc is not None
                    and scalar_key in local_doc
                    and scalar_key in base_doc
                    and encoded.get(scalar_key) == local_doc.get(scalar_key)
                ):
                    out_doc[scalar_key] = base_doc[scalar_key]
                else:
                    out_doc[scalar_key] = encoded[scalar_key]
            dest = resolve_contained_subpath(self._host_dir, _CFG_HOST_FILENAME)
            _cfg_write_json_checked(dest, out_doc)
            self._module_cache.clear()

    def get_module_dict(self, module_id: ModuleId) -> MutableJsonObject:
        mod_id = _cfg_require_module_id(module_id)
        with self._guard:
            proj_path = resolve_contained_subpath(
                self._yscb_root,
                _CFG_PROJECT_DIRNAME,
                mod_id.value,
                _CFG_MOD_PROJECT_FILENAME,
            )
            local_path = resolve_contained_subpath(
                self._yscb_root,
                _CFG_LOCAL_DIRNAME,
                mod_id.value,
                _CFG_MOD_LOCAL_FILENAME,
            )
            proj_sig = _cfg_stat_signature(proj_path)
            local_sig = _cfg_stat_signature(local_path)
            cached = self._module_cache.get(mod_id)
            if (
                cached is not None
                and cached.proj_sig == proj_sig
                and cached.local_sig == local_sig
                and proj_sig.mtime_ns >= 0
                and local_sig.mtime_ns >= 0
            ):
                return cfg_clone_json_object(cached.merged, label="cached module config")
            proj_doc = _cfg_read_strict_json_file(
                self._yscb_root,
                _CFG_PROJECT_DIRNAME,
                mod_id.value,
                _CFG_MOD_PROJECT_FILENAME,
                required=False,
            )
            local_doc = _cfg_read_strict_json_file(
                self._yscb_root,
                _CFG_LOCAL_DIRNAME,
                mod_id.value,
                _CFG_MOD_LOCAL_FILENAME,
                required=False,
            )
            merged = cfg_deep_merge_json_objects(proj_doc or {}, local_doc or {})
            post_proj_sig = _cfg_stat_signature(proj_path)
            post_local_sig = _cfg_stat_signature(local_path)
            if (
                proj_sig == post_proj_sig
                and local_sig == post_local_sig
                and post_proj_sig.mtime_ns >= 0
                and post_local_sig.mtime_ns >= 0
            ):
                self._module_cache[mod_id] = _CfgModuleCacheEntry(
                    proj_sig=post_proj_sig,
                    local_sig=post_local_sig,
                    merged=merged,
                )
            else:
                self._module_cache.pop(mod_id, None)
            return cfg_clone_json_object(merged, label="module config")

    def get_module_value(
        self,
        module_id: ModuleId,
        key: str,
        default: JsonValue = None,
    ) -> JsonValue:
        mod_id = _cfg_require_module_id(module_id)
        parts = _cfg_validate_key_segments(key)
        clean_default = cfg_clone_json_value(default, label="default config value")
        merged = self.get_module_dict(mod_id)
        if key in merged:
            return cfg_clone_json_value(merged[key], label="module config value")
        if len(parts) == 1:
            return clean_default
        cur: JsonValue = merged
        for seg in parts:
            if isinstance(cur, Mapping) and seg in cur:
                cur = cur[seg]
            else:
                return clean_default
        return cfg_clone_json_value(cur, label="module config value")

    def load_typed(self, module_id: ModuleId, config_cls: type[TConfig]) -> TConfig:
        mod_id = _cfg_require_module_id(module_id)
        merged = self.get_module_dict(mod_id)
        return _cfg_decode_with_schema(config_cls, merged)

    def set_value(
        self,
        module_id: ModuleId,
        key: str,
        value: JsonValue,
        *,
        local: bool = False,
        schema_cls: Optional[type[object]] = None,
    ) -> None:
        mod_id = _cfg_require_module_id(module_id)
        parts = _cfg_validate_key_segments(key)
        try:
            require_pure_bool(local, "ConfigStore.set_value local")
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
        cloned_val = cfg_clone_json_value(value, label=f"ConfigStore.set_value[{key!r}]")
        with self._guard:
            proj_doc = (
                _cfg_read_strict_json_file(
                    self._yscb_root,
                    _CFG_PROJECT_DIRNAME,
                    mod_id.value,
                    _CFG_MOD_PROJECT_FILENAME,
                    required=False,
                )
                or {}
            )
            local_doc = (
                _cfg_read_strict_json_file(
                    self._yscb_root,
                    _CFG_LOCAL_DIRNAME,
                    mod_id.value,
                    _CFG_MOD_LOCAL_FILENAME,
                    required=False,
                )
                or {}
            )
            target_doc = cfg_clone_json_object(
                local_doc if local else proj_doc,
                label="target config layer",
            )
            _cfg_apply_set_key(target_doc, key, parts, cloned_val)
            cand_proj = proj_doc if local else target_doc
            cand_local = target_doc if local else local_doc
            cand_merged = cfg_deep_merge_json_objects(cand_proj, cand_local)
            if schema_cls is not None:
                _cfg_decode_with_schema(schema_cls, cand_merged)
                if not local and cand_local:
                    proj_exposed = cfg_deep_merge_json_objects(cand_merged, cand_proj)
                    _cfg_decode_with_schema(schema_cls, proj_exposed)
            _cfg_validate_against_module_disk_schema(self._yscb_root, mod_id, cand_merged)
            if not local and cand_local:
                proj_disk_exposed = cfg_deep_merge_json_objects(cand_merged, cand_proj)
                _cfg_validate_against_module_disk_schema(self._yscb_root, mod_id, proj_disk_exposed)
            dest = resolve_contained_subpath(
                self._yscb_root,
                _CFG_LOCAL_DIRNAME if local else _CFG_PROJECT_DIRNAME,
                mod_id.value,
                _CFG_MOD_LOCAL_FILENAME if local else _CFG_MOD_PROJECT_FILENAME,
            )
            _cfg_write_json_checked(dest, target_doc)
            self._module_cache.pop(mod_id, None)

    def unset_value(
        self,
        module_id: ModuleId,
        key: str,
        *,
        local: bool = False,
    ) -> bool:
        mod_id = _cfg_require_module_id(module_id)
        parts = _cfg_validate_key_segments(key)
        try:
            require_pure_bool(local, "ConfigStore.unset_value local")
        except ValueError as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc
        with self._guard:
            sub_dir = _CFG_LOCAL_DIRNAME if local else _CFG_PROJECT_DIRNAME
            fname = _CFG_MOD_LOCAL_FILENAME if local else _CFG_MOD_PROJECT_FILENAME
            existing_doc = _cfg_read_strict_json_file(
                self._yscb_root,
                sub_dir,
                mod_id.value,
                fname,
                required=False,
            )
            if existing_doc is None:
                return False
            removed = _cfg_apply_unset_key(existing_doc, key, parts)
            if not removed:
                return False
            dest = resolve_contained_subpath(self._yscb_root, sub_dir, mod_id.value, fname)
            _cfg_write_json_checked(dest, existing_doc)
            self._module_cache.pop(mod_id, None)
            return True

    def deploy_configurable(
        self,
        module_id: ModuleId,
        staging_configurable_dir: HostPath,
        *,
        default_config_template: Optional[JsonObject] = None,
    ) -> tuple[str, ...]:
        mod_id = _cfg_require_module_id(module_id)
        staging_dir = _cfg_require_host_path(
            staging_configurable_dir,
            "ConfigStore.deploy_configurable staging_configurable_dir",
        )
        arg_tmpl = (
            cfg_clone_json_object(default_config_template, label="default_config_template")
            if default_config_template is not None
            else None
        )
        staged_items = _cfg_collect_staging_templates(staging_dir)
        file_proj_tmpl: Optional[MutableJsonObject] = None
        other_templates: list[tuple[str, bytes]] = []
        for rel_posix, raw_bytes in staged_items:
            if rel_posix == _CFG_MOD_PROJECT_FILENAME:
                try:
                    file_proj_tmpl = strict_parse_json_object(raw_bytes.decode("utf-8"))
                except (UnicodeDecodeError, ValueError) as exc:
                    raise YscbError(
                        ErrorCode.CONFIG_INVALID,
                        f"Malformed JSON in '{_CFG_MOD_PROJECT_FILENAME}{_CFG_TMPL_SUFFIX}': {safe_exception_summary(exc)}",
                    ) from exc
            else:
                other_templates.append((rel_posix, raw_bytes))

        eff_proj_tmpl: Optional[MutableJsonObject] = None
        if file_proj_tmpl is not None and arg_tmpl is not None:
            eff_proj_tmpl, _ = DeepInfiller.infill(file_proj_tmpl, arg_tmpl)
        elif file_proj_tmpl is not None:
            eff_proj_tmpl = file_proj_tmpl
        elif arg_tmpl is not None:
            eff_proj_tmpl = arg_tmpl

        written: list[str] = []
        with self._guard:
            mod_cfg_dir = resolve_contained_subpath(
                self._yscb_root,
                _CFG_PROJECT_DIRNAME,
                mod_id.value,
            )
            if eff_proj_tmpl is not None:
                proj_dest = resolve_contained_subpath(mod_cfg_dir, _CFG_MOD_PROJECT_FILENAME)
                existing_proj = _cfg_read_strict_json_file(
                    mod_cfg_dir,
                    _CFG_MOD_PROJECT_FILENAME,
                    required=False,
                )
                if existing_proj is None:
                    infilled_doc, _ = DeepInfiller.infill({}, eff_proj_tmpl)
                    _cfg_write_json_checked(proj_dest, infilled_doc)
                    written.append(_CFG_MOD_PROJECT_FILENAME)
                else:
                    infilled_doc, added_keys = DeepInfiller.infill(existing_proj, eff_proj_tmpl)
                    if added_keys:
                        _cfg_write_json_checked(proj_dest, infilled_doc)
                        written.append(_CFG_MOD_PROJECT_FILENAME)

            for rel_posix, raw_bytes in other_templates:
                rel_segs = tuple(rel_posix.split("/"))
                dest_path = resolve_contained_subpath(mod_cfg_dir, *rel_segs)
                if os.path.lexists(str(dest_path)):
                    continue
                _cfg_write_bytes_checked(dest_path, raw_bytes)
                written.append(rel_posix)

            self._module_cache.pop(mod_id, None)
        return tuple(written)

    def fingerprint(self) -> str:
        with self._guard:
            entries: list[tuple[str, str]] = []
            for host_fname in (_CFG_HOST_FILENAME, _CFG_HOST_LOCAL_FILENAME):
                try:
                    host_p = resolve_contained_subpath(self._host_dir, host_fname)
                except YscbError:
                    continue
                h_dig = _cfg_hash_single_config_file(str(host_p))
                if h_dig is not None:
                    entries.append((f"host:{host_fname}", h_dig))

            for area_tag, dir_name in (
                ("config", _CFG_PROJECT_DIRNAME),
                ("config.local", _CFG_LOCAL_DIRNAME),
            ):
                try:
                    area_root = resolve_contained_subpath(self._yscb_root, dir_name)
                except YscbError:
                    continue
                entries.extend(_cfg_collect_dir_fingerprints(area_root, area_tag))

            payload = json.dumps(
                entries,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
            return hashlib.sha256(payload).hexdigest()

    def reload(self) -> None:
        with self._guard:
            self._module_cache.clear()


_CFG_CORE_ID: Final[ModuleId] = ModuleId("core")


def _cfg_dedupe_locale_chain(items: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        clean = item.strip()
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return tuple(out) if out else ("zh", "en")


def parse_locale_chain_tokens(
    raw_env_locale: Optional[str],
    cfg_store: ConfigStore,
    *,
    dialect: Optional[str] = None,
) -> tuple[str, ...]:
    """Build the ordered LocaleCatalog fallback chain from comma-separated YSCB_LOCALE, config, and AI dialect."""
    if isinstance(raw_env_locale, str) and raw_env_locale.strip():
        parts = [seg.strip() for seg in raw_env_locale.split(",") if seg.strip()]
        if "en" not in parts:
            parts.append("en")
        base_chain = _cfg_dedupe_locale_chain(parts)
    else:
        try:
            raw_loc = cfg_store.get_module_value(_CFG_CORE_ID, "locale", default=["zh", "en"])
        except YscbError:
            raw_loc = ["zh", "en"]
        if type(raw_loc) is str and raw_loc.strip():
            segs = [s.strip() for s in raw_loc.split(",") if s.strip()]
            if "en" not in segs:
                segs.append("en")
            base_chain = _cfg_dedupe_locale_chain(segs)
        elif isinstance(raw_loc, list) and raw_loc and all(type(x) is str and bool(x.strip()) for x in raw_loc):
            base_chain = _cfg_dedupe_locale_chain([str(x).strip() for x in raw_loc])
        else:
            base_chain = ("zh", "en")

    if isinstance(dialect, str) and dialect.strip():
        return _cfg_dedupe_locale_chain((dialect.strip(), *base_chain))
    return base_chain
