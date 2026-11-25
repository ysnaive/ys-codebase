"""Compiler translating Python ExtensionPointSpec definitions into Draft 2020-12 JSON Schema bundles."""

from __future__ import annotations

import collections.abc as cabc
import dataclasses
from dataclasses import dataclass
from enum import Enum
import functools
import operator
from types import UnionType
from typing import (
    Annotated,
    Final,
    Literal,
    Mapping,
    Optional,
    Sequence,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from core.foundation.codec import SchemaExporter, resolve_dataclass_init_hints
from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary
from core.foundation.primitives import (
    EnvHash,
    EventId,
    HostPath,
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
    require_typed_tuple,
)
from core.metadata.contributes.spec import (
    ContribField,
    ContributesSchemaBundle,
    ExtensionPointSpec,
    MergeStrategy,
)

_CTB_DRAFT_2020_12_URI: Final[str] = "https://json-schema.org/draft/2020-12/schema"
_CTB_SCHEMA_BUNDLE_VERSION: Final[int] = 2
_CTB_VO_TYPE_NAMES: Final[frozenset[type[object]]] = frozenset(
    {
        ModuleId,
        TaskId,
        EventId,
        HostPath,
        SemVer4,
        VersionConstraint,
        SemanticUri,
        SpaceId,
        SpacePath,
        EnvHash,
    }
)


@dataclass(frozen=True, slots=True)
class _CtbExtractedFieldMeta:
    base_type: object
    merge: Optional[MergeStrategy] = None
    description: Optional[str] = None
    dedupe: Optional[bool] = None


def _ctb_extract_contrib_field(tp: object) -> _CtbExtractedFieldMeta:
    cur = tp
    merge_val: Optional[MergeStrategy] = None
    desc_val: Optional[str] = None
    dedupe_val: Optional[bool] = None
    while True:
        orig = get_origin(cur)
        if orig is Annotated:
            ann_args = get_args(cur)
            if not ann_args:
                break
            for meta in ann_args[1:]:
                if isinstance(meta, ContribField):
                    if meta.merge is not None and merge_val is None:
                        merge_val = meta.merge
                    if meta.description.strip() and desc_val is None:
                        desc_val = meta.description.strip()
                    if dedupe_val is None:
                        dedupe_val = meta.dedupe
            cur = ann_args[0]
            continue
        if orig in (Union, UnionType):
            u_args = get_args(cur)
            non_none = [a for a in u_args if a is not type(None)]
            if len(non_none) == 1 and len(u_args) == 2 and get_origin(non_none[0]) is Annotated:
                inner_meta = _ctb_extract_contrib_field(non_none[0])
                if inner_meta.merge is not None and merge_val is None:
                    merge_val = inner_meta.merge
                if inner_meta.description is not None and desc_val is None:
                    desc_val = inner_meta.description
                if inner_meta.dedupe is not None and dedupe_val is None:
                    dedupe_val = inner_meta.dedupe
            break
        break
    return _CtbExtractedFieldMeta(
        base_type=cur,
        merge=merge_val,
        description=desc_val,
        dedupe=dedupe_val,
    )


def _ctb_strip_all_annotated(tp: object) -> object:
    while get_origin(tp) is Annotated:
        ann_args = get_args(tp)
        if not ann_args:
            return tp
        tp = ann_args[0]
    origin = get_origin(tp)
    args = get_args(tp)
    if origin is None or origin is Literal or not args:
        return tp
    stripped_args = tuple(Ellipsis if a is Ellipsis else _ctb_strip_all_annotated(a) for a in args)
    if origin in (Union, UnionType):
        if len(stripped_args) == 1:
            return stripped_args[0]
        try:
            return functools.reduce(operator.or_, stripped_args)
        except TypeError:
            return Union[stripped_args]
    try:
        return operator.getitem(origin, stripped_args[0] if len(stripped_args) == 1 else stripped_args)
    except TypeError:
        return tp


def _ctb_substitute_tv(tp: object, tv_map: Mapping[object, object]) -> object:
    if not tv_map:
        return tp
    if get_origin(tp) is Annotated:
        ann_args = get_args(tp)
        if not ann_args:
            return tp
        inner_sub = _ctb_substitute_tv(ann_args[0], tv_map)
        return Annotated[(inner_sub, *ann_args[1:])]
    if isinstance(tp, TypeVar):
        return tv_map.get(tp, tp)
    origin = get_origin(tp)
    args = get_args(tp)
    if origin is None or origin is Literal or not args:
        return tp
    sub_args = tuple(Ellipsis if a is Ellipsis else _ctb_substitute_tv(a, tv_map) for a in args)
    if origin in (Union, UnionType):
        if len(sub_args) == 1:
            return sub_args[0]
        try:
            return functools.reduce(operator.or_, sub_args)
        except TypeError:
            return Union[sub_args]
    try:
        return operator.getitem(origin, sub_args[0] if len(sub_args) == 1 else sub_args)
    except TypeError:
        return tp


def _ctb_canonical_enum_or_lit_key(val: object) -> Optional[str]:
    raw = val.value if isinstance(val, Enum) else val
    if type(raw) is bool:
        return "true" if raw else "false"
    if type(raw) is int:
        return str(raw)
    if type(raw) is str:
        return raw
    return None


def _ctb_export_map_key_schema(key_tp: object) -> MutableJsonObject:
    unwrapped = _ctb_extract_contrib_field(key_tp).base_type
    if isinstance(unwrapped, TypeVar):
        branches = unwrapped.__constraints__ or ((unwrapped.__bound__,) if unwrapped.__bound__ is not None else ())
        if not branches:
            return {"type": "string"}
        if len(branches) == 1:
            return _ctb_export_map_key_schema(branches[0])
        return {"anyOf": [_ctb_export_map_key_schema(b) for b in branches]}
    origin = get_origin(unwrapped)
    args = get_args(unwrapped)
    if origin in (Union, UnionType):
        return {"anyOf": [_ctb_export_map_key_schema(b) for b in args]}
    if origin is Literal:
        lit_keys: list[JsonValue] = []
        for arg in args:
            mapped = _ctb_canonical_enum_or_lit_key(arg)
            if mapped is not None:
                lit_keys.append(mapped)
        return {"type": "string", "enum": lit_keys}
    if unwrapped is str:
        return {"type": "string"}
    if unwrapped is bool:
        return {"type": "string", "enum": ["true", "false"]}
    if unwrapped is int:
        return {"type": "string", "pattern": "^(?:0|-?[1-9][0-9]*)$", "x-yscb-vo": "int_key"}
    if unwrapped is SnapshotGen:
        return {"type": "string", "pattern": "^(?:0|[1-9][0-9]*)$", "x-yscb-vo": "SnapshotGen_key"}
    if isinstance(unwrapped, type) and unwrapped in _CTB_VO_TYPE_NAMES:
        return {"type": "string", "x-yscb-vo": unwrapped.__name__}
    if isinstance(unwrapped, type) and issubclass(unwrapped, Enum):
        enum_keys: list[JsonValue] = []
        for member in unwrapped:
            mapped = _ctb_canonical_enum_or_lit_key(member)
            if mapped is not None:
                enum_keys.append(mapped)
        return {"type": "string", "enum": enum_keys}
    return {"type": "string"}


def _ctb_generic_params(dc_cls: type[object]) -> tuple[object, ...]:
    try:
        params = dc_cls.__parameters__
    except AttributeError:
        return ()
    return params if isinstance(params, tuple) else ()


def _ctb_resolve_dc_hints(dc_cls: type[object]) -> dict[str, object]:
    try:
        return resolve_dataclass_init_hints(dc_cls)
    except (YscbError, NameError, TypeError, AttributeError, ValueError):
        try:
            return dict(get_type_hints(dc_cls, include_extras=True))
        except (NameError, TypeError, AttributeError):
            return {fld.name: fld.type for fld in dataclasses.fields(dc_cls) if fld.init}


def _ctb_enrich_dc_fields(
    dc_cls: type[object],
    type_args: tuple[object, ...],
    dc_schema: MutableJsonObject,
    defs: dict[str, MutableJsonObject],
    visited_defs: set[str],
) -> None:
    raw_props = dc_schema.get("properties")
    if not isinstance(raw_props, dict):
        return
    tv_map = dict(zip(_ctb_generic_params(dc_cls), type_args)) if type_args else {}
    hints = _ctb_resolve_dc_hints(dc_cls)
    for fld in dataclasses.fields(dc_cls):
        if not fld.init or fld.name not in raw_props or fld.name not in hints:
            continue
        prop_node = raw_props[fld.name]
        if not isinstance(prop_node, dict):
            continue
        field_tp = _ctb_substitute_tv(hints[fld.name], tv_map) if tv_map else hints[fld.name]
        _ctb_enrich_schema_node(field_tp, prop_node, defs, visited_defs)


def _ctb_enrich_schema_node(
    tp: object,
    schema_node: MutableJsonObject,
    defs: dict[str, MutableJsonObject],
    visited_defs: set[str],
) -> None:
    meta = _ctb_extract_contrib_field(tp)
    if meta.merge is not None:
        schema_node["x-yscb-merge"] = meta.merge.value
    if meta.description is not None:
        schema_node["description"] = meta.description
    if meta.dedupe is not None:
        schema_node["x-yscb-dedupe"] = meta.dedupe

    base = meta.base_type
    if isinstance(base, type) and base in _CTB_VO_TYPE_NAMES:
        schema_node["x-yscb-vo"] = base.__name__
        return

    ref_str = schema_node.get("$ref")
    if type(ref_str) is str and ref_str.startswith("#/$defs/"):
        def_name = ref_str[len("#/$defs/") :]
        if def_name in visited_defs:
            return
        target_def = defs.get(def_name)
        if isinstance(target_def, dict):
            visited_defs.add(def_name)
            orig_dc = get_origin(base)
            if isinstance(orig_dc, type) and orig_dc not in _CTB_VO_TYPE_NAMES and dataclasses.is_dataclass(orig_dc):
                _ctb_enrich_dc_fields(orig_dc, get_args(base), target_def, defs, visited_defs)
            elif isinstance(base, type) and base not in _CTB_VO_TYPE_NAMES and dataclasses.is_dataclass(base):
                _ctb_enrich_dc_fields(base, (), target_def, defs, visited_defs)
        return

    origin = get_origin(base)
    args = get_args(base)
    if isinstance(origin, type) and origin not in _CTB_VO_TYPE_NAMES and dataclasses.is_dataclass(origin):
        _ctb_enrich_dc_fields(origin, args, schema_node, defs, visited_defs)
        return
    if isinstance(base, type) and base not in _CTB_VO_TYPE_NAMES and dataclasses.is_dataclass(base):
        _ctb_enrich_dc_fields(base, (), schema_node, defs, visited_defs)
        return

    if origin in (Union, UnionType):
        any_of = schema_node.get("anyOf")
        if isinstance(any_of, list) and len(any_of) == len(args):
            for branch_tp, branch_sc in zip(args, any_of):
                if isinstance(branch_sc, dict):
                    _ctb_enrich_schema_node(branch_tp, branch_sc, defs, visited_defs)
        else:
            collapsed = _ctb_strip_all_annotated(base)
            col_origin = get_origin(collapsed)
            col_args = get_args(collapsed)
            if col_origin in (Union, UnionType) and isinstance(any_of, list) and len(any_of) == len(col_args):
                for branch_tp, branch_sc in zip(col_args, any_of):
                    if isinstance(branch_sc, dict):
                        _ctb_enrich_schema_node(branch_tp, branch_sc, defs, visited_defs)
            elif col_origin not in (Union, UnionType) and "anyOf" not in schema_node:
                _ctb_enrich_schema_node(collapsed, schema_node, defs, visited_defs)
    elif origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            items_sc = schema_node.get("items")
            if isinstance(items_sc, dict):
                _ctb_enrich_schema_node(args[0], items_sc, defs, visited_defs)
        else:
            pfx = schema_node.get("prefixItems")
            if isinstance(pfx, list) and len(pfx) == len(args):
                for elem_tp, elem_sc in zip(args, pfx):
                    if isinstance(elem_sc, dict):
                        _ctb_enrich_schema_node(elem_tp, elem_sc, defs, visited_defs)
    elif origin in (list, Sequence, cabc.Sequence, frozenset) and args:
        items_sc = schema_node.get("items")
        if isinstance(items_sc, dict):
            _ctb_enrich_schema_node(args[0], items_sc, defs, visited_defs)
    elif origin in (dict, Mapping, cabc.Mapping) and len(args) == 2:
        if args[0] is not str:
            schema_node["propertyNames"] = _ctb_export_map_key_schema(args[0])
        add_props = schema_node.get("additionalProperties")
        if isinstance(add_props, dict):
            _ctb_enrich_schema_node(args[1], add_props, defs, visited_defs)


def _ctb_rewrite_def_refs(node: JsonValue, rename_map: Mapping[str, str]) -> JsonValue:
    if not rename_map:
        return node
    if isinstance(node, dict):
        rewritten: MutableJsonObject = {}
        for k, v in node.items():
            if k == "$ref" and type(v) is str and v.startswith("#/$defs/"):
                old_def = v[len("#/$defs/") :]
                new_def = rename_map.get(old_def, old_def)
                rewritten[k] = f"#/$defs/{new_def}"
            else:
                rewritten[k] = _ctb_rewrite_def_refs(v, rename_map)
        return rewritten
    if isinstance(node, list):
        return [_ctb_rewrite_def_refs(item, rename_map) for item in node]
    return node


def _ctb_hoist_point_defs(
    point_name: str,
    point_schema: MutableJsonObject,
    local_defs: dict[str, MutableJsonObject],
    merged_defs: dict[str, MutableJsonObject],
) -> MutableJsonObject:
    if not local_defs:
        return point_schema
    rename_map: dict[str, str] = {}
    used_targets: set[str] = set()
    changed = True
    while changed:
        changed = False
        for def_key, def_val in local_defs.items():
            if def_key in rename_map:
                continue
            rewritten_cand = _ctb_rewrite_def_refs(def_val, rename_map)
            if def_key in merged_defs and merged_defs[def_key] != rewritten_cand:
                cand = f"{point_name}_{def_key}"
                seq = 2
                while cand in merged_defs or cand in local_defs or cand in used_targets:
                    cand = f"{point_name}_{def_key}_{seq}"
                    seq += 1
                rename_map[def_key] = cand
                used_targets.add(cand)
                changed = True

    for def_key, def_val in local_defs.items():
        target_key = rename_map.get(def_key, def_key)
        rewritten_def = _ctb_rewrite_def_refs(def_val, rename_map)
        if isinstance(rewritten_def, dict):
            merged_defs[target_key] = rewritten_def

    rewritten_point = _ctb_rewrite_def_refs(point_schema, rename_map)
    return rewritten_point if isinstance(rewritten_point, dict) else point_schema


def compile_extension_points(
    target_module: ModuleId,
    specs: Sequence[ExtensionPointSpec[object]],
) -> ContributesSchemaBundle:
    """Compile host Python ExtensionPointSpec declarations into a Draft 2020-12 ContributesSchemaBundle."""
    if not isinstance(target_module, ModuleId):
        raise ValueError(f"compile_extension_points target_module must be ModuleId, got {target_module!r}")
    spec_tuple = require_typed_tuple(specs, ExtensionPointSpec, "compile_extension_points.specs")

    seen_names: set[str] = set()
    points_props: MutableJsonObject = {}
    merged_defs: dict[str, MutableJsonObject] = {}

    for spec in spec_tuple:
        if spec.name in seen_names:
            raise YscbError(
                ErrorCode.CONTRIBUTES_INVALID,
                f"Duplicate extension point '{spec.name}' declared on module '{target_module.value}'.",
            )
        seen_names.add(spec.name)
        try:
            exported = SchemaExporter.export(spec.payload_type, title=spec.name)
        except YscbError as exc:
            raise YscbError(
                ErrorCode.CONTRIBUTES_INVALID,
                f"Failed to compile extension point '{spec.name}' on '{target_module.value}': {safe_exception_summary(exc)}",
            ) from exc

        exported.pop("$schema", None)
        raw_local_defs = exported.pop("$defs", {})
        local_defs: dict[str, MutableJsonObject] = {}
        if isinstance(raw_local_defs, dict):
            for dk, dv in raw_local_defs.items():
                if type(dk) is str and isinstance(dv, dict):
                    local_defs[dk] = dv

        visited_defs: set[str] = set()
        _ctb_enrich_schema_node(spec.payload_type, exported, local_defs, visited_defs)

        hoisted_point = _ctb_hoist_point_defs(spec.name, exported, local_defs, merged_defs)
        hoisted_point["x-yscb-merge"] = spec.merge_strategy.value
        hoisted_point["x-yscb-strict-fields"] = spec.strict_fields
        if spec.merge_strategy == MergeStrategy.BUCKET_BY_DONOR:
            hoisted_point["x-yscb-bucket-by-donor"] = True
        if spec.description:
            hoisted_point["description"] = spec.description
        if not spec.strict_fields and hoisted_point.get("type") == "object" and "properties" in hoisted_point:
            hoisted_point["additionalProperties"] = True

        points_props[spec.name] = hoisted_point

    points_schema: MutableJsonObject = {
        "$schema": _CTB_DRAFT_2020_12_URI,
        "title": f"{target_module.value}.contributes",
        "type": "object",
        "properties": points_props,
        "additionalProperties": False,
        "$defs": merged_defs,
    }
    return ContributesSchemaBundle(
        target_module=target_module,
        schema_version=_CTB_SCHEMA_BUNDLE_VERSION,
        points_schema=points_schema,
    )
