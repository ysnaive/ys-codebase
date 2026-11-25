"""Dual-mode JSON Schema Draft 2020-12 validator and locale bundle contract verifier."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import difflib
from enum import Enum
import json
import math
import os
import re
from typing import Final, Mapping, Optional, Sequence

from core.filesystem.fs import (
    MAX_JSON_FILE_BYTES,
    has_symlink_raw_path,
    is_symlink_or_reparse,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
)
from core.foundation.errors import YscbError, safe_exception_summary, sanitize_utf8_text
from core.foundation.primitives import (
    INT64_MAX,
    INT64_MIN,
    MAX_USER_JSON_DEPTH,
    EnvHash,
    EventId,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    MutableJsonObject,
    SemVer4,
    SemanticUri,
    SnapshotGen,
    SpaceId,
    SpacePath,
    TaskId,
    VersionConstraint,
    clone_strict_json_object,
    is_valid_relative_segment,
    require_pure_str,
    require_typed_tuple,
    strict_parse_json_object,
)
from core.metadata.contributes.provenance import ctb_join_pointer
from core.metadata.contributes.spec import ContributesSchemaBundle

_CTB_LOCALE_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\{\{|\}\}|\{([a-zA-Z0-9_.:-]+)\}")
_CTB_CANONICAL_INT_STR_RE: Final[re.Pattern[str]] = re.compile(r"^(?:0|-?[1-9][0-9]*)$")
_CTB_UNIQUE_ID_FIELDS: Final[tuple[str, ...]] = ("token", "id", "name", "key")


class ValidationSeverity(Enum):
    """Diagnostic severity level for contributes and locale contract checks."""

    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """Single structured validation diagnostic with RFC 6901 pointer and optional typo hint."""

    severity: ValidationSeverity
    source_label: str
    json_pointer: str
    message: str
    suggestion: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.severity, ValidationSeverity):
            raise ValueError(
                f"ValidationIssue.severity must be ValidationSeverity, got {self.severity!r}"
            )
        clean_src = sanitize_utf8_text(
            require_pure_str(self.source_label, "ValidationIssue.source_label", non_empty=True)
        )
        object.__setattr__(self, "source_label", clean_src)
        require_pure_str(self.json_pointer, "ValidationIssue.json_pointer")
        if self.json_pointer != "" and not self.json_pointer.startswith("/"):
            raise ValueError(
                f"ValidationIssue.json_pointer must be '' or start with '/', got {self.json_pointer!r}"
            )
        clean_msg = sanitize_utf8_text(
            require_pure_str(self.message, "ValidationIssue.message", non_empty=True)
        )
        object.__setattr__(self, "message", clean_msg)
        if self.suggestion is not None:
            clean_sug = sanitize_utf8_text(
                require_pure_str(self.suggestion, "ValidationIssue.suggestion", non_empty=True)
            )
            object.__setattr__(self, "suggestion", clean_sug)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Aggregated validation report for a single target module."""

    target_module: ModuleId
    issues: tuple[ValidationIssue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.target_module, ModuleId):
            raise ValueError(
                f"ValidationReport.target_module must be ModuleId, got {self.target_module!r}"
            )
        object.__setattr__(
            self,
            "issues",
            require_typed_tuple(self.issues, ValidationIssue, "ValidationReport.issues"),
        )

    @property
    def ok(self) -> bool:
        return not any(issue.severity == ValidationSeverity.ERROR for issue in self.issues)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == ValidationSeverity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == ValidationSeverity.WARNING)


@dataclass(frozen=True, slots=True)
class _CtbNodeValidation:
    valid: bool
    sanitized: JsonValue


@dataclass(frozen=True, slots=True)
class _CtbDonorValidation:
    sanitized_points: MutableJsonObject
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True, slots=True)
class _CtbSchemaEvalCtx:
    source_label: str
    defs: JsonObject
    strict: bool
    point_strict_fields: bool
    is_project_override: bool


def ctb_suggest_close_match(word: str, candidates: Sequence[str]) -> Optional[str]:
    """Return a ``Did you mean '<candidate>'?`` hint when a close match exists."""
    if not word or not candidates:
        return None
    matches = difflib.get_close_matches(word, sorted(set(candidates)), n=1, cutoff=0.6)
    return f"Did you mean '{matches[0]}'?" if matches else None


def ctb_canonical_json_key(val: JsonValue) -> str:
    """Return a deterministic canonical JSON string preserving bool vs int distinction."""
    return json.dumps(val, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def ctb_extract_unique_item_id(item: JsonValue) -> str:
    """Extract a canonical uniqueness key for array elements under MergeStrategy.UNIQUE."""
    if isinstance(item, Mapping):
        for field_key in _CTB_UNIQUE_ID_FIELDS:
            if field_key in item:
                raw_id = item[field_key]
                if type(raw_id) is str and raw_id.strip():
                    return f"{field_key}:{raw_id}"
                if type(raw_id) is int:
                    return f"{field_key}:{raw_id}"
        return f"object:{ctb_canonical_json_key(item)}"
    if item is None or type(item) in (bool, int, float, str):
        return f"scalar:{type(item).__name__}:{item}"
    return f"value:{ctb_canonical_json_key(item)}"


def ctb_deref_schema(schema: JsonObject, defs: JsonObject) -> JsonObject:
    """Resolve ``$ref`` chains against root ``$defs`` while preserving outer annotations."""
    cur: JsonObject = schema
    seen_refs: set[str] = set()
    outer_extras: MutableJsonObject = {}
    for extra_key in (
        "x-yscb-merge",
        "x-yscb-dedupe",
        "x-yscb-strict-fields",
        "x-yscb-bucket-by-donor",
        "description",
    ):
        if extra_key in schema:
            outer_extras[extra_key] = schema[extra_key]
    while True:
        ref_val = cur.get("$ref")
        if type(ref_val) is not str or not ref_val.startswith("#/$defs/"):
            break
        def_name = ref_val[len("#/$defs/") :]
        if def_name in seen_refs:
            break
        seen_refs.add(def_name)
        resolved = defs.get(def_name)
        if not isinstance(resolved, Mapping):
            break
        cur = resolved
    if not outer_extras or cur is schema:
        return cur
    merged: MutableJsonObject = dict(cur)
    merged.update(outer_extras)
    return merged


def _ctb_issue_severity(strict: bool) -> ValidationSeverity:
    return ValidationSeverity.ERROR if strict else ValidationSeverity.WARNING


def _ctb_validate_vo_string(vo_tag: str, raw_str: str) -> Optional[str]:
    try:
        if vo_tag == "ModuleId":
            ModuleId(raw_str)
        elif vo_tag == "TaskId":
            TaskId(raw_str)
        elif vo_tag == "EventId":
            EventId(raw_str)
        elif vo_tag == "HostPath":
            HostPath(raw_str)
        elif vo_tag == "SemVer4":
            SemVer4.parse(raw_str)
        elif vo_tag == "VersionConstraint":
            VersionConstraint.parse(raw_str)
        elif vo_tag == "SemanticUri":
            SemanticUri.parse(raw_str)
        elif vo_tag == "SpaceId":
            SpaceId.parse(raw_str)
        elif vo_tag == "SpacePath":
            SpacePath.parse(raw_str)
        elif vo_tag == "EnvHash":
            EnvHash(raw_str)
        elif vo_tag == "int_key":
            if _CTB_CANONICAL_INT_STR_RE.fullmatch(raw_str) is None:
                return f"Invalid canonical integer key {raw_str!r}."
            parsed_i = int(raw_str)
            if not (INT64_MIN <= parsed_i <= INT64_MAX):
                return f"Integer key {raw_str!r} out of int64 range."
        elif vo_tag == "SnapshotGen_key":
            if _CTB_CANONICAL_INT_STR_RE.fullmatch(raw_str) is None:
                return f"Invalid SnapshotGen key {raw_str!r}."
            SnapshotGen(int(raw_str))
    except (ValueError, TypeError, YscbError) as exc:
        return safe_exception_summary(exc)
    return None


def _ctb_validate_base64_str(raw_str: str) -> Optional[str]:
    try:
        decoded = base64.b64decode(raw_str.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        return f"Invalid base64 string: {safe_exception_summary(exc)}"
    if base64.b64encode(decoded).decode("ascii") != raw_str:
        return "Non-canonical base64 string encoding."
    return None


def _ctb_validate_string_constraints(
    val: str,
    schema: JsonObject,
    ptr: str,
    ctx: _CtbSchemaEvalCtx,
    issues: list[ValidationIssue],
) -> bool:
    min_len = schema.get("minLength")
    if type(min_len) is int and len(val) < min_len:
        issues.append(
            ValidationIssue(
                severity=_ctb_issue_severity(ctx.strict),
                source_label=ctx.source_label,
                json_pointer=ptr,
                message=f"String length {len(val)} is less than minimum {min_len}.",
            )
        )
        return False
    max_len = schema.get("maxLength")
    if type(max_len) is int and len(val) > max_len:
        issues.append(
            ValidationIssue(
                severity=_ctb_issue_severity(ctx.strict),
                source_label=ctx.source_label,
                json_pointer=ptr,
                message=f"String length {len(val)} exceeds maximum {max_len}.",
            )
        )
        return False
    pat = schema.get("pattern")
    if type(pat) is str:
        try:
            matched = re.search(pat, val) is not None
        except re.error:
            matched = True
        if not matched:
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=ptr,
                    message=f"String {val!r} does not match required pattern {pat!r}.",
                )
            )
            return False
    if schema.get("contentEncoding") == "base64":
        b64_err = _ctb_validate_base64_str(val)
        if b64_err is not None:
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=ptr,
                    message=b64_err,
                )
            )
            return False
    vo_tag = schema.get("x-yscb-vo")
    if type(vo_tag) is str:
        vo_err = _ctb_validate_vo_string(vo_tag, val)
        if vo_err is not None:
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=ptr,
                    message=f"Invalid {vo_tag} value {val!r}: {vo_err}",
                )
            )
            return False
    return True


def _ctb_validate_any_of(
    val: JsonValue,
    branches: Sequence[JsonValue],
    ptr: str,
    ctx: _CtbSchemaEvalCtx,
    existing_node: JsonValue,
    depth: int,
    issues: list[ValidationIssue],
) -> _CtbNodeValidation:
    dict_branches = [b for b in branches if isinstance(b, Mapping)]
    if not dict_branches:
        return _CtbNodeValidation(valid=True, sanitized=val)

    partial_hit: Optional[tuple[_CtbNodeValidation, list[ValidationIssue]]] = None
    best_fail_issues: list[ValidationIssue] = []
    best_type_match = False

    for branch in dict_branches:
        resolved_b = ctb_deref_schema(branch, ctx.defs)
        branch_issues: list[ValidationIssue] = []
        res = _ctb_validate_schema_value(
            val,
            resolved_b,
            ptr,
            ctx,
            existing_node=existing_node,
            depth=depth + 1,
            issues=branch_issues,
        )
        if res.valid and not branch_issues:
            return res
        if res.valid and partial_hit is None:
            partial_hit = (res, branch_issues)
        b_type = resolved_b.get("type")
        same_container = (isinstance(val, Mapping) and b_type == "object") or (
            isinstance(val, (list, tuple)) and b_type == "array"
        )
        if same_container and not best_type_match:
            best_type_match = True
            best_fail_issues = branch_issues
        elif not best_fail_issues and b_type != "null":
            best_fail_issues = branch_issues

    if partial_hit is not None:
        issues.extend(partial_hit[1])
        return partial_hit[0]
    if best_fail_issues:
        issues.extend(best_fail_issues)
    else:
        issues.append(
            ValidationIssue(
                severity=_ctb_issue_severity(ctx.strict),
                source_label=ctx.source_label,
                json_pointer=ptr,
                message=f"Value of type '{type(val).__name__}' did not match any union schema branch.",
            )
        )
    return _CtbNodeValidation(valid=False, sanitized=None)


def _ctb_validate_array_node(
    val: JsonValue,
    schema: JsonObject,
    ptr: str,
    ctx: _CtbSchemaEvalCtx,
    depth: int,
    issues: list[ValidationIssue],
) -> _CtbNodeValidation:
    if not isinstance(val, (list, tuple)):
        issues.append(
            ValidationIssue(
                severity=_ctb_issue_severity(ctx.strict),
                source_label=ctx.source_label,
                json_pointer=ptr,
                message=f"Expected JSON array, got {type(val).__name__}.",
            )
        )
        return _CtbNodeValidation(valid=False, sanitized=None)

    min_items = schema.get("minItems")
    max_items = schema.get("maxItems")
    if type(min_items) is int and len(val) < min_items:
        issues.append(
            ValidationIssue(
                severity=_ctb_issue_severity(ctx.strict),
                source_label=ctx.source_label,
                json_pointer=ptr,
                message=f"Array length {len(val)} is less than minimum {min_items}.",
            )
        )
        return _CtbNodeValidation(valid=False, sanitized=None)
    if type(max_items) is int and len(val) > max_items:
        issues.append(
            ValidationIssue(
                severity=_ctb_issue_severity(ctx.strict),
                source_label=ctx.source_label,
                json_pointer=ptr,
                message=f"Array length {len(val)} exceeds maximum {max_items}.",
            )
        )
        return _CtbNodeValidation(valid=False, sanitized=None)

    prefix_items = schema.get("prefixItems")
    if isinstance(prefix_items, (list, tuple)):
        if schema.get("items") is False and len(val) > len(prefix_items):
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=ptr,
                    message=f"Expected tuple of length {len(prefix_items)}, got {len(val)}.",
                )
            )
            return _CtbNodeValidation(valid=False, sanitized=None)
        sanitized_tuple: list[JsonValue] = []
        all_ok = True
        for idx, item in enumerate(val):
            item_ptr = f"{ptr}/{idx}"
            item_sc = prefix_items[idx] if idx < len(prefix_items) else schema.get("items")
            if isinstance(item_sc, Mapping):
                res = _ctb_validate_schema_value(
                    item, item_sc, item_ptr, ctx, existing_node=None, depth=depth + 1, issues=issues
                )
                if not res.valid:
                    all_ok = False
                sanitized_tuple.append(res.sanitized)
            else:
                sanitized_tuple.append(item)
        return _CtbNodeValidation(valid=all_ok, sanitized=sanitized_tuple if all_ok else None)

    item_schema = schema.get("items")
    unique_req = schema.get("uniqueItems") is True
    seen_canon: set[str] = set()
    out_items: list[JsonValue] = []
    had_error = False

    for idx, item in enumerate(val):
        item_ptr = f"{ptr}/{idx}"
        san_item: JsonValue = item
        if isinstance(item_schema, Mapping):
            res = _ctb_validate_schema_value(
                item, item_schema, item_ptr, ctx, existing_node=None, depth=depth + 1, issues=issues
            )
            if not res.valid:
                had_error = True
                continue
            san_item = res.sanitized
        if unique_req:
            ck = ctb_canonical_json_key(san_item)
            if ck in seen_canon:
                issues.append(
                    ValidationIssue(
                        severity=_ctb_issue_severity(ctx.strict),
                        source_label=ctx.source_label,
                        json_pointer=item_ptr,
                        message="Duplicate array item violates uniqueItems constraint.",
                    )
                )
                had_error = True
                continue
            seen_canon.add(ck)
        out_items.append(san_item)

    if schema.get("x-yscb-merge") == "unique":
        prev_issue_len = len(issues)
        out_items = _ctb_check_intra_donor_unique_list(
            out_items, ptr, ctx.source_label, ctx.strict, issues
        )
        if len(issues) > prev_issue_len:
            had_error = True
    if ctx.strict and had_error:
        return _CtbNodeValidation(valid=False, sanitized=None)
    return _CtbNodeValidation(valid=True, sanitized=out_items)


def _ctb_validate_object_node(
    val: JsonValue,
    schema: JsonObject,
    ptr: str,
    ctx: _CtbSchemaEvalCtx,
    existing_node: JsonValue,
    depth: int,
    issues: list[ValidationIssue],
) -> _CtbNodeValidation:
    if not isinstance(val, Mapping):
        issues.append(
            ValidationIssue(
                severity=_ctb_issue_severity(ctx.strict),
                source_label=ctx.source_label,
                json_pointer=ptr,
                message=f"Expected JSON object, got {type(val).__name__}.",
            )
        )
        return _CtbNodeValidation(valid=False, sanitized=None)

    existing_map: Optional[Mapping[str, JsonValue]] = existing_node if isinstance(existing_node, Mapping) else None
    props = schema.get("properties")
    if isinstance(props, Mapping):
        req_raw = schema.get("required")
        required_set = (
            {r for r in req_raw if type(r) is str}
            if isinstance(req_raw, (list, tuple))
            else set()
        )
        known_fields = [k for k in props.keys() if type(k) is str]
        add_props = schema.get("additionalProperties", True)
        out_obj: MutableJsonObject = {}
        fatal_obj = False

        for key, raw_v in val.items():
            key_ptr = ctb_join_pointer(ptr, key)
            prop_sc = props.get(key)
            if isinstance(prop_sc, Mapping):
                child_existing = existing_map.get(key) if existing_map is not None else None
                res = _ctb_validate_schema_value(
                    raw_v,
                    prop_sc,
                    key_ptr,
                    ctx,
                    existing_node=child_existing,
                    depth=depth + 1,
                    issues=issues,
                )
                if res.valid:
                    out_obj[key] = res.sanitized
                elif ctx.strict:
                    fatal_obj = True
                elif key in required_set and not (existing_map is not None and key in existing_map):
                    fatal_obj = True
            elif isinstance(add_props, Mapping):
                res = _ctb_validate_schema_value(
                    raw_v, add_props, key_ptr, ctx, existing_node=None, depth=depth + 1, issues=issues
                )
                if res.valid:
                    out_obj[key] = res.sanitized
                elif ctx.strict:
                    fatal_obj = True
            elif not ctx.point_strict_fields:
                continue
            elif add_props is False:
                hint = ctb_suggest_close_match(key, known_fields)
                issues.append(
                    ValidationIssue(
                        severity=_ctb_issue_severity(ctx.strict),
                        source_label=ctx.source_label,
                        json_pointer=key_ptr,
                        message=f"Unknown field '{key}'.",
                        suggestion=hint,
                    )
                )
                if ctx.strict:
                    fatal_obj = True
            else:
                out_obj[key] = raw_v

        eff_merge = schema.get("x-yscb-merge")
        allow_existing_fill = (
            ctx.is_project_override
            and existing_map is not None
            and eff_merge != "replace"
        )
        for req_key in sorted(required_set):
            present_now = req_key in out_obj
            present_before = allow_existing_fill and existing_map is not None and req_key in existing_map
            if not present_now and not present_before:
                req_ptr = ctb_join_pointer(ptr, req_key)
                if req_key not in val:
                    issues.append(
                        ValidationIssue(
                            severity=_ctb_issue_severity(ctx.strict),
                            source_label=ctx.source_label,
                            json_pointer=req_ptr,
                            message=f"Missing required field '{req_key}'.",
                        )
                    )
                fatal_obj = True

        if fatal_obj:
            return _CtbNodeValidation(valid=False, sanitized=None)
        return _CtbNodeValidation(valid=True, sanitized=out_obj)

    prop_names_sc = schema.get("propertyNames")
    add_props_sc = schema.get("additionalProperties", True)
    dyn_out: MutableJsonObject = {}
    had_dyn_err = False

    for key, raw_v in val.items():
        key_ptr = ctb_join_pointer(ptr, key)
        if isinstance(prop_names_sc, Mapping):
            key_res = _ctb_validate_schema_value(
                key, prop_names_sc, key_ptr, ctx, existing_node=None, depth=depth + 1, issues=issues
            )
            if not key_res.valid:
                had_dyn_err = True
                continue
        if isinstance(add_props_sc, Mapping):
            child_existing = existing_map.get(key) if existing_map is not None else None
            val_res = _ctb_validate_schema_value(
                raw_v,
                add_props_sc,
                key_ptr,
                ctx,
                existing_node=child_existing,
                depth=depth + 1,
                issues=issues,
            )
            if not val_res.valid:
                had_dyn_err = True
                continue
            dyn_out[key] = val_res.sanitized
        elif add_props_sc is False:
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=key_ptr,
                    message=f"Unexpected property '{key}' in closed object.",
                )
            )
            had_dyn_err = True
        else:
            dyn_out[key] = raw_v

    if ctx.strict and had_dyn_err:
        return _CtbNodeValidation(valid=False, sanitized=None)
    return _CtbNodeValidation(valid=True, sanitized=dyn_out)


def _ctb_validate_schema_value(
    val: JsonValue,
    raw_schema: JsonObject,
    ptr: str,
    ctx: _CtbSchemaEvalCtx,
    *,
    existing_node: JsonValue,
    depth: int,
    issues: list[ValidationIssue],
) -> _CtbNodeValidation:
    if depth > MAX_USER_JSON_DEPTH:
        issues.append(
            ValidationIssue(
                severity=_ctb_issue_severity(ctx.strict),
                source_label=ctx.source_label,
                json_pointer=ptr,
                message=f"Maximum schema validation depth ({MAX_USER_JSON_DEPTH}) exceeded.",
            )
        )
        return _CtbNodeValidation(valid=False, sanitized=None)

    schema = ctb_deref_schema(raw_schema, ctx.defs)
    if schema.get("x-yscb-merge") == "replace":
        existing_node = None
    any_of = schema.get("anyOf")
    if isinstance(any_of, (list, tuple)):
        any_res = _ctb_validate_any_of(val, any_of, ptr, ctx, existing_node, depth, issues)
        if any_res.valid and isinstance(any_res.sanitized, list) and schema.get("x-yscb-merge") == "unique":
            prev_any_len = len(issues)
            deduped_items = _ctb_check_intra_donor_unique_list(
                any_res.sanitized, ptr, ctx.source_label, ctx.strict, issues
            )
            if ctx.strict and len(issues) > prev_any_len:
                return _CtbNodeValidation(valid=False, sanitized=None)
            return _CtbNodeValidation(valid=True, sanitized=deduped_items)
        return any_res

    if "enum" in schema and isinstance(schema["enum"], (list, tuple)):
        enum_vals = schema["enum"]
        matched_enum = any(type(val) is type(ev) and val == ev for ev in enum_vals)
        if not matched_enum:
            str_cands = [ev for ev in enum_vals if type(ev) is str]
            hint = ctb_suggest_close_match(val, str_cands) if type(val) is str else None
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=ptr,
                    message=f"Invalid enum value {val!r}; expected one of {enum_vals!r}.",
                    suggestion=hint,
                )
            )
            return _CtbNodeValidation(valid=False, sanitized=None)
        return _CtbNodeValidation(valid=True, sanitized=val)

    expected_type = schema.get("type")
    if expected_type is None:
        return _CtbNodeValidation(valid=True, sanitized=val)
    if expected_type == "null":
        if val is not None:
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=ptr,
                    message=f"Expected null, got {type(val).__name__}.",
                )
            )
            return _CtbNodeValidation(valid=False, sanitized=None)
        return _CtbNodeValidation(valid=True, sanitized=None)
    if expected_type == "boolean":
        if type(val) is not bool:
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=ptr,
                    message=f"Expected boolean, got {type(val).__name__}.",
                )
            )
            return _CtbNodeValidation(valid=False, sanitized=None)
        return _CtbNodeValidation(valid=True, sanitized=val)
    if expected_type == "integer":
        if type(val) is not int:
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=ptr,
                    message=f"Expected integer, got {type(val).__name__}.",
                )
            )
            return _CtbNodeValidation(valid=False, sanitized=None)
        min_v = schema.get("minimum")
        max_v = schema.get("maximum")
        if (type(min_v) is int and val < min_v) or (type(max_v) is int and val > max_v):
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=ptr,
                    message=f"Integer {val} out of allowed bounds [{min_v}, {max_v}].",
                )
            )
            return _CtbNodeValidation(valid=False, sanitized=None)
        return _CtbNodeValidation(valid=True, sanitized=val)
    if expected_type == "number":
        if type(val) not in (int, float) or not math.isfinite(float(val)):
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=ptr,
                    message=f"Expected finite number, got {type(val).__name__}.",
                )
            )
            return _CtbNodeValidation(valid=False, sanitized=None)
        return _CtbNodeValidation(valid=True, sanitized=val)
    if expected_type == "string":
        if type(val) is not str:
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(ctx.strict),
                    source_label=ctx.source_label,
                    json_pointer=ptr,
                    message=f"Expected string, got {type(val).__name__}.",
                )
            )
            return _CtbNodeValidation(valid=False, sanitized=None)
        ok_str = _ctb_validate_string_constraints(val, schema, ptr, ctx, issues)
        return _CtbNodeValidation(valid=ok_str, sanitized=val if ok_str else None)
    if expected_type == "array":
        return _ctb_validate_array_node(val, schema, ptr, ctx, depth, issues)
    if expected_type == "object":
        return _ctb_validate_object_node(val, schema, ptr, ctx, existing_node, depth, issues)
    return _CtbNodeValidation(valid=True, sanitized=val)


def _ctb_check_intra_donor_unique_list(
    items: list[JsonValue],
    ptr: str,
    source_label: str,
    strict: bool,
    issues: list[ValidationIssue],
) -> list[JsonValue]:
    seen_ids: set[str] = set()
    kept: list[JsonValue] = []
    for idx, item in enumerate(items):
        uid = ctb_extract_unique_item_id(item)
        if uid in seen_ids:
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(strict),
                    source_label=source_label,
                    json_pointer=f"{ptr}/{idx}",
                    message=f"Duplicate unique item ({uid}) within the same donor contribution.",
                )
            )
            continue
        seen_ids.add(uid)
        kept.append(item)
    return kept


def ctb_validate_donor_payload(
    *,
    source_label: str,
    target_module: ModuleId,
    raw_payload: object,
    bundle: Optional[ContributesSchemaBundle],
    strict: bool,
    is_project_override: bool = False,
    existing_merged: Optional[JsonObject] = None,
) -> _CtbDonorValidation:
    """Validate and sanitize a single donor JSON payload against a target schema bundle."""
    if not isinstance(raw_payload, Mapping):
        return _CtbDonorValidation(
            sanitized_points={},
            issues=(
                ValidationIssue(
                    severity=_ctb_issue_severity(strict),
                    source_label=source_label,
                    json_pointer="",
                    message=f"Contributes payload must be a JSON object, got {type(raw_payload).__name__}.",
                ),
            ),
        )
    try:
        cloned_payload = clone_strict_json_object(raw_payload, label=source_label)
    except (TypeError, ValueError) as exc:
        return _CtbDonorValidation(
            sanitized_points={},
            issues=(
                ValidationIssue(
                    severity=_ctb_issue_severity(strict),
                    source_label=source_label,
                    json_pointer="",
                    message=f"Malformed JSON object in '{source_label}': {safe_exception_summary(exc)}",
                ),
            ),
        )

    issues: list[ValidationIssue] = []
    sanitized_points: MutableJsonObject = {}

    if bundle is None:
        for key, val in cloned_payload.items():
            if key == "$schema" and type(val) is str:
                continue
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(strict),
                    source_label=source_label,
                    json_pointer=ctb_join_pointer("", key),
                    message=(
                        f"Unknown extension point '{key}': target module '{target_module.value}' "
                        "declares no extension points."
                    ),
                )
            )
        return _CtbDonorValidation(sanitized_points=sanitized_points, issues=tuple(issues))

    raw_props = bundle.points_schema.get("properties")
    points_props: Mapping[str, JsonValue] = raw_props if isinstance(raw_props, Mapping) else {}
    raw_defs = bundle.points_schema.get("$defs")
    defs_map: JsonObject = raw_defs if isinstance(raw_defs, Mapping) else {}
    known_names = [k for k in points_props.keys() if type(k) is str]

    for point_name, point_val in cloned_payload.items():
        if point_name == "$schema" and type(point_val) is str:
            continue
        point_ptr = ctb_join_pointer("", point_name)
        point_schema = points_props.get(point_name)
        if not isinstance(point_schema, Mapping):
            hint = ctb_suggest_close_match(point_name, known_names)
            issues.append(
                ValidationIssue(
                    severity=_ctb_issue_severity(strict),
                    source_label=source_label,
                    json_pointer=point_ptr,
                    message=f"Unknown extension point '{point_name}' for module '{target_module.value}'.",
                    suggestion=hint,
                )
            )
            continue

        strict_fields = point_schema.get("x-yscb-strict-fields") is not False
        is_bucket = (
            point_schema.get("x-yscb-bucket-by-donor") is True
            or point_schema.get("x-yscb-merge") == "bucket_by_donor"
        )
        existing_point_val: JsonValue = None
        if existing_merged is not None and point_name in existing_merged:
            if is_bucket:
                bucket_obj = existing_merged.get(point_name)
                if is_project_override and isinstance(bucket_obj, Mapping):
                    existing_point_val = bucket_obj.get("project")
            else:
                existing_point_val = existing_merged.get(point_name)

        eval_ctx = _CtbSchemaEvalCtx(
            source_label=source_label,
            defs=defs_map,
            strict=strict,
            point_strict_fields=strict_fields,
            is_project_override=is_project_override,
        )
        pre_err_count = sum(1 for i in issues if i.severity == ValidationSeverity.ERROR)
        res = _ctb_validate_schema_value(
            point_val,
            point_schema,
            point_ptr,
            eval_ctx,
            existing_node=existing_point_val,
            depth=0,
            issues=issues,
        )
        if not res.valid:
            continue
        san_val = res.sanitized
        post_err_count = sum(1 for i in issues if i.severity == ValidationSeverity.ERROR)
        if strict and post_err_count > pre_err_count:
            continue
        sanitized_points[point_name] = san_val

    return _CtbDonorValidation(sanitized_points=sanitized_points, issues=tuple(issues))


def _ctb_extract_locale_placeholders(template: str) -> frozenset[str]:
    if "{" not in template:
        return frozenset()
    tokens: set[str] = set()
    for match in _CTB_LOCALE_TOKEN_RE.finditer(template):
        whole = match.group(0)
        if whole in ("{{", "}}"):
            continue
        tok = match.group(1)
        if tok:
            tokens.add(tok)
    return frozenset(tokens)


def _ctb_is_cross_module_noun_ref(token: str) -> bool:
    if ":" not in token:
        return False
    mod_part, key_part = token.split(":", 1)
    if not mod_part or not key_part.strip():
        return False
    try:
        ModuleId(mod_part)
        return True
    except ValueError:
        return False


def _ctb_load_contained_locale_json(
    module_root: HostPath,
    rel_raw: object,
    json_pointer: str,
    source_label: str,
    issues: list[ValidationIssue],
) -> Optional[MutableJsonObject]:
    if type(rel_raw) is not str or not rel_raw.strip():
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                source_label=source_label,
                json_pointer=json_pointer,
                message="Locale file pointer must be a non-empty relative path string.",
            )
        )
        return None
    rel_clean = rel_raw.strip()
    if rel_clean.startswith(("/", "\\")) or ":" in rel_clean or "\x00" in rel_clean:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                source_label=source_label,
                json_pointer=json_pointer,
                message=f"Absolute or invalid locale file path rejected: {rel_raw!r}.",
            )
        )
        return None
    raw_segs = [seg for seg in re.split(r"[\\/]+", rel_clean) if seg]
    if not raw_segs or any(seg in (".", "..") or not is_valid_relative_segment(seg) for seg in raw_segs):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                source_label=source_label,
                json_pointer=json_pointer,
                message=f"Path traversal or unsafe segment rejected in locale path: {rel_raw!r}.",
            )
        )
        return None
    try:
        resolved_hp = resolve_contained_subpath(module_root, *raw_segs)
    except (OSError, ValueError, YscbError) as exc:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                source_label=source_label,
                json_pointer=json_pointer,
                message=f"Symlink or path escape rejected for locale file {rel_raw!r}: {safe_exception_summary(exc)}",
            )
        )
        return None

    target_str = str(resolved_hp)
    if is_symlink_or_reparse(target_str):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                source_label=source_label,
                json_pointer=json_pointer,
                message=f"Refusing symlinked locale file: {rel_raw!r}.",
            )
        )
        return None
    if not os.path.lexists(target_str):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                source_label=source_label,
                json_pointer=json_pointer,
                message=f"Locale file not found: {rel_raw!r}.",
            )
        )
        return None

    try:
        raw_bytes = read_nofollow_regular_bytes(target_str, max_bytes=MAX_JSON_FILE_BYTES)
    except OSError:
        raw_bytes = None
    if raw_bytes is None:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                source_label=source_label,
                json_pointer=json_pointer,
                message=f"Refusing non-regular, symlinked, or oversized locale file: {rel_raw!r}.",
            )
        )
        return None
    try:
        return strict_parse_json_object(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                source_label=source_label,
                json_pointer=json_pointer,
                message=f"Invalid JSON object in locale file {rel_raw!r}: {safe_exception_summary(exc)}",
            )
        )
        return None


@dataclass(frozen=True, slots=True)
class _CtbDefKeyContract:
    placeholders: frozenset[str]
    explicit_contract: bool


def _ctb_parse_definition_entries(
    def_obj: JsonObject,
    source_label: str,
    issues: list[ValidationIssue],
) -> dict[str, _CtbDefKeyContract]:
    contracts: dict[str, _CtbDefKeyContract] = {}
    for def_key, def_val in def_obj.items():
        if def_key == "$schema" and type(def_val) is str:
            continue
        key_ptr = ctb_join_pointer("/locales/definition", def_key)
        if type(def_val) is str:
            contracts[def_key] = _CtbDefKeyContract(
                placeholders=_ctb_extract_locale_placeholders(def_val),
                explicit_contract=False,
            )
            continue
        if isinstance(def_val, Mapping):
            has_desc = "description" in def_val
            has_phs = "placeholders" in def_val
            if not has_desc and not has_phs:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        source_label=source_label,
                        json_pointer=key_ptr,
                        message=(
                            f"Definition entry '{def_key}' must declare 'description' or 'placeholders'."
                        ),
                    )
                )
                continue
            if has_desc:
                raw_desc = def_val.get("description")
                if type(raw_desc) is not str or not raw_desc.strip():
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.ERROR,
                            source_label=source_label,
                            json_pointer=ctb_join_pointer(key_ptr, "description"),
                            message=f"Definition entry '{def_key}' requires a non-empty string 'description'.",
                        )
                    )
            raw_phs = def_val.get("placeholders", [])
            if not isinstance(raw_phs, list) or any(type(p) is not str or not p.strip() for p in raw_phs):
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        source_label=source_label,
                        json_pointer=ctb_join_pointer(key_ptr, "placeholders"),
                        message=f"'placeholders' in definition entry '{def_key}' must be a list of non-empty strings.",
                    )
                )
                contracts[def_key] = _CtbDefKeyContract(placeholders=frozenset(), explicit_contract=True)
            else:
                contracts[def_key] = _CtbDefKeyContract(
                    placeholders=frozenset(p.strip() for p in raw_phs if type(p) is str),
                    explicit_contract=True,
                )
            continue
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                source_label=source_label,
                json_pointer=key_ptr,
                message=(
                    f"Definition value for '{def_key}' must be a baseline string or definition object, "
                    f"got {type(def_val).__name__}."
                ),
            )
        )
    return contracts


def validate_locale_bundle(
    donor_module: ModuleId,
    module_root: HostPath,
    locale_pointers: Mapping[str, str],
) -> tuple[ValidationIssue, ...]:
    """Validate a donor module's locale bundle pointers, containment, keys, and placeholders."""
    if not isinstance(donor_module, ModuleId):
        raise ValueError(f"validate_locale_bundle donor_module must be ModuleId, got {donor_module!r}")
    if not isinstance(module_root, HostPath):
        raise ValueError(f"validate_locale_bundle module_root must be HostPath, got {module_root!r}")
    if not isinstance(locale_pointers, Mapping):
        raise ValueError("validate_locale_bundle locale_pointers must be a Mapping.")

    source_label = f"module:{donor_module.value}/locales"
    issues: list[ValidationIssue] = []

    root_str = str(module_root)
    if has_symlink_raw_path(root_str) or not os.path.isdir(root_str):
        return (
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                source_label=source_label,
                json_pointer="/locales",
                message=f"Module root directory is missing or traverses a symlink: '{module_root}'.",
            ),
        )

    if "definition" not in locale_pointers:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                source_label=source_label,
                json_pointer="/locales/definition",
                message="Missing required 'definition' baseline locale file pointer.",
            )
        )
        for lang_key, lang_rel in locale_pointers.items():
            if type(lang_key) is str:
                _ctb_load_contained_locale_json(
                    module_root,
                    lang_rel,
                    ctb_join_pointer("/locales", lang_key),
                    source_label,
                    issues,
                )
        return tuple(issues)

    def_obj = _ctb_load_contained_locale_json(
        module_root,
        locale_pointers["definition"],
        "/locales/definition",
        source_label,
        issues,
    )
    if def_obj is None:
        for lang_key, lang_rel in locale_pointers.items():
            if lang_key != "definition" and type(lang_key) is str:
                _ctb_load_contained_locale_json(
                    module_root,
                    lang_rel,
                    ctb_join_pointer("/locales", lang_key),
                    source_label,
                    issues,
                )
        return tuple(issues)

    contracts = _ctb_parse_definition_entries(def_obj, source_label, issues)
    defined_keys = sorted(contracts.keys())
    zero_arg_nouns = frozenset(k for k, spec in contracts.items() if not spec.placeholders)

    for raw_lang_id, raw_lang_rel in locale_pointers.items():
        if type(raw_lang_id) is not str or not raw_lang_id.strip():
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    source_label=source_label,
                    json_pointer="/locales",
                    message=f"Locale language identifier must be a non-empty string, got {raw_lang_id!r}.",
                )
            )
            continue
        if raw_lang_id == "definition":
            continue
        lang_ptr = ctb_join_pointer("/locales", raw_lang_id)
        lang_obj = _ctb_load_contained_locale_json(
            module_root, raw_lang_rel, lang_ptr, source_label, issues
        )
        if lang_obj is None:
            continue

        for t_key, t_val in lang_obj.items():
            if t_key == "$schema" and type(t_val) is str:
                continue
            entry_ptr = ctb_join_pointer(lang_ptr, t_key)
            if t_key not in contracts:
                hint = ctb_suggest_close_match(t_key, defined_keys)
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        source_label=source_label,
                        json_pointer=entry_ptr,
                        message=f"Orphan locale key '{t_key}' in '{raw_lang_id}' is not defined in 'definition'.",
                        suggestion=hint,
                    )
                )
                continue
            if type(t_val) is not str:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        source_label=source_label,
                        json_pointer=entry_ptr,
                        message=f"Locale entry '{t_key}' in '{raw_lang_id}' must be a string, got {type(t_val).__name__}.",
                    )
                )
                continue

            contract = contracts[t_key]
            actual_raw = _ctb_extract_locale_placeholders(t_val)
            expected_eff = (
                contract.placeholders
                if contract.explicit_contract
                else frozenset(
                    p
                    for p in contract.placeholders
                    if p not in zero_arg_nouns and not _ctb_is_cross_module_noun_ref(p)
                )
            )
            actual_eff = frozenset(
                p
                for p in actual_raw
                if p in expected_eff or (p not in zero_arg_nouns and not _ctb_is_cross_module_noun_ref(p))
            )
            missing = sorted(expected_eff - actual_eff)
            extra = sorted(actual_eff - expected_eff)
            if missing or extra:
                details: list[str] = []
                if missing:
                    details.append(f"missing {missing}")
                if extra:
                    details.append(f"undeclared {extra}")
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        source_label=source_label,
                        json_pointer=entry_ptr,
                        message=(
                            f"Placeholder mismatch for '{t_key}' in '{raw_lang_id}': {'; '.join(details)}."
                        ),
                    )
                )

    return tuple(issues)
