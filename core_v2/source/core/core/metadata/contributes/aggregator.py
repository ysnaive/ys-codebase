"""Pure-in-memory two-tier topological contributes aggregator and typed decoder."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import os
import threading
from types import MappingProxyType
from typing import Final, Mapping, Optional, Sequence

from core.filesystem.fs import (
    MAX_JSON_FILE_BYTES,
    has_symlink_raw_path,
    is_symlink_or_reparse,
    read_nofollow_regular_bytes,
    try_resolve_contained_subpath,
)
from core.foundation.codec import DataclassCodec
from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary
from core.foundation.primitives import (
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    MutableJsonObject,
    clone_strict_json_object,
    is_valid_type_annotation,
    require_pure_bool,
    require_pure_str,
    require_typed_tuple,
    strict_parse_json_object,
)
from core.metadata.config import ModuleManifest
from core.metadata.contributes.compiler import compile_extension_points
from core.metadata.contributes.provenance import (
    CtbProvenanceTracker,
    ProvenanceGraph,
    ctb_join_pointer,
)
from core.metadata.contributes.spec import (
    ContributesSchemaBundle,
    ExtensionPointSpec,
    MergeStrategy,
    TPoint,
    ctb_deep_freeze_json,
)
from core.metadata.contributes.validator import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    ctb_canonical_json_key,
    ctb_deref_schema,
    ctb_extract_unique_item_id,
    ctb_validate_donor_payload,
    validate_locale_bundle,
)

_EMPTY_LIVE_SPECS: Final[Mapping[ModuleId, Sequence[ExtensionPointSpec[object]]]] = MappingProxyType({})
_PROJECT_DONOR_LABEL: Final[str] = "project"
_CORE_TARGET_ID: Final[ModuleId] = ModuleId("core")


@dataclass(frozen=True, slots=True)
class AggregatedContributes:
    """Single-target aggregation result pairing pure business JSON with ProvenanceGraph."""

    target_module: ModuleId
    raw_merged: JsonObject
    provenance: ProvenanceGraph
    warnings: tuple[ValidationIssue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.target_module, ModuleId):
            raise ValueError(
                f"AggregatedContributes.target_module must be ModuleId, got {self.target_module!r}"
            )
        cloned = clone_strict_json_object(
            self.raw_merged,
            label="AggregatedContributes.raw_merged",
        )
        object.__setattr__(self, "raw_merged", ctb_deep_freeze_json(cloned))
        if not isinstance(self.provenance, ProvenanceGraph):
            raise ValueError(
                f"AggregatedContributes.provenance must be ProvenanceGraph, got {self.provenance!r}"
            )
        object.__setattr__(
            self,
            "warnings",
            require_typed_tuple(self.warnings, ValidationIssue, "AggregatedContributes.warnings"),
        )

    def has_point(self, point_name: str) -> bool:
        """Return True iff at least one donor contributed ``point_name``."""
        require_pure_str(point_name, "point_name", non_empty=True)
        return point_name in self.raw_merged

    def decode_point(self, point_name: str, target_cls: type[TPoint]) -> TPoint:
        """Decode ``point_name`` into ``target_cls`` via DataclassCodec."""
        require_pure_str(point_name, "point_name", non_empty=True)
        if not is_valid_type_annotation(target_cls):
            raise YscbError(
                ErrorCode.CONTRIBUTES_INVALID,
                f"Invalid target_cls annotation {target_cls!r} when decoding '{point_name}'.",
            )
        if point_name not in self.raw_merged:
            raise YscbError(
                ErrorCode.CONTRIBUTES_INVALID,
                f"Extension point '{point_name}' is not present in aggregated contributes for '{self.target_module.value}'.",
            )
        try:
            decoded: TPoint = DataclassCodec.decode(target_cls, self.raw_merged[point_name])
            return decoded
        except (YscbError, TypeError, ValueError) as exc:
            raise YscbError(
                ErrorCode.CONTRIBUTES_INVALID,
                f"Failed to decode extension point '{point_name}' on '{self.target_module.value}': {safe_exception_summary(exc)}",
            ) from exc

    def decode_donor_bucket(self, point_name: str, item_cls: type[TPoint]) -> Mapping[str, TPoint]:
        """Decode a BUCKET_BY_DONOR extension point into an immutable ``Mapping[str, TPoint]``."""
        require_pure_str(point_name, "point_name", non_empty=True)
        if not is_valid_type_annotation(item_cls):
            raise YscbError(
                ErrorCode.CONTRIBUTES_INVALID,
                f"Invalid item_cls annotation {item_cls!r} when decoding donor bucket '{point_name}'.",
            )
        if point_name not in self.raw_merged:
            return MappingProxyType({})
        raw_bucket = self.raw_merged[point_name]
        if not isinstance(raw_bucket, Mapping):
            raise YscbError(
                ErrorCode.CONTRIBUTES_INVALID,
                f"Extension point '{point_name}' on '{self.target_module.value}' is not a donor bucket mapping.",
            )
        decoded_bucket: dict[str, TPoint] = {}
        for donor_key, donor_payload in raw_bucket.items():
            try:
                decoded_item: TPoint = DataclassCodec.decode(item_cls, donor_payload)
            except (YscbError, TypeError, ValueError) as exc:
                raise YscbError(
                    ErrorCode.CONTRIBUTES_INVALID,
                    f"Failed to decode donor '{donor_key}' in extension point '{point_name}': {safe_exception_summary(exc)}",
                ) from exc
            decoded_bucket[donor_key] = decoded_item
        return MappingProxyType(decoded_bucket)


@dataclass(slots=True)
class _CtbMergeCtx:
    source_label: str
    strict: bool
    is_project_override: bool
    unique_owners: dict[str, dict[str, str]]
    issues: list[ValidationIssue]


@dataclass(frozen=True, slots=True)
class _CtbLoadedJsonResult:
    present: bool
    payload: Optional[MutableJsonObject]
    error_message: Optional[str]


def _ctb_clone_json_value(val: JsonValue) -> JsonValue:
    if isinstance(val, Mapping):
        return {k: _ctb_clone_json_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_ctb_clone_json_value(item) for item in val]
    return val


def _ctb_topo_rank_key(mod_id: ModuleId) -> tuple[int, str]:
    return (0 if mod_id.value == "core" else 1, mod_id.value)


def _ctb_sort_manifests_topologically(manifests: Sequence[ModuleManifest]) -> tuple[ModuleManifest, ...]:
    manifest_tuple = require_typed_tuple(manifests, ModuleManifest, "manifests")
    by_id: dict[ModuleId, ModuleManifest] = {}
    by_val: dict[str, ModuleManifest] = {}
    for manifest in manifest_tuple:
        if manifest.id in by_id:
            raise ValueError(f"Duplicate ModuleManifest id in ContributesAggregator: {manifest.id.value!r}")
        by_id[manifest.id] = manifest
        by_val[manifest.id.value] = manifest

    in_degree: dict[ModuleId, int] = {}
    dependents: dict[ModuleId, list[ModuleId]] = {mid: [] for mid in by_id}
    for mid, manifest in by_id.items():
        active_deps = {
            dep_id
            for dep_id in manifest.dependencies.keys()
            if dep_id in by_id and dep_id != mid
        }
        in_degree[mid] = len(active_deps)
        for dep_id in active_deps:
            dependents[dep_id].append(mid)

    ready_heap: list[tuple[int, str]] = [
        _ctb_topo_rank_key(mid) for mid, deg in in_degree.items() if deg == 0
    ]
    heapq.heapify(ready_heap)

    ordered: list[ModuleManifest] = []
    visited: set[ModuleId] = set()
    while ready_heap:
        _, cur_val = heapq.heappop(ready_heap)
        cur_manifest = by_val[cur_val]
        cur_id = cur_manifest.id
        visited.add(cur_id)
        ordered.append(cur_manifest)
        for nxt_id in dependents[cur_id]:
            in_degree[nxt_id] -= 1
            if in_degree[nxt_id] == 0:
                heapq.heappush(ready_heap, _ctb_topo_rank_key(nxt_id))

    if len(ordered) < len(by_id):
        remaining = sorted(
            (mid for mid in by_id if mid not in visited),
            key=_ctb_topo_rank_key,
        )
        for rem_id in remaining:
            ordered.append(by_id[rem_id])

    return tuple(ordered)


def _ctb_compile_live_specs_map(
    live_specs: Mapping[ModuleId, Sequence[ExtensionPointSpec[object]]],
) -> dict[ModuleId, ContributesSchemaBundle]:
    if not isinstance(live_specs, Mapping):
        raise ValueError(f"ContributesAggregator.live_specs must be a Mapping, got {live_specs!r}")
    compiled: dict[ModuleId, ContributesSchemaBundle] = {}
    for mod_id, specs in live_specs.items():
        if not isinstance(mod_id, ModuleId):
            raise ValueError(f"live_specs key must be ModuleId, got {mod_id!r}")
        compiled[mod_id] = compile_extension_points(mod_id, specs)
    return compiled


def _ctb_parse_strategy_tag(raw_tag: object, *, default: MergeStrategy) -> MergeStrategy:
    if type(raw_tag) is str:
        for member in MergeStrategy:
            if member.value == raw_tag:
                return member
    return default


def _ctb_deref_preserving_meta(branch: JsonObject, defs: JsonObject) -> JsonObject:
    deref = ctb_deref_schema(branch, defs)
    extra_merge = branch.get("x-yscb-merge")
    extra_dedupe = branch.get("x-yscb-dedupe")
    need_merge = extra_merge is not None and "x-yscb-merge" not in deref
    need_dedupe = extra_dedupe is not None and "x-yscb-dedupe" not in deref
    if not need_merge and not need_dedupe:
        return deref
    copied = dict(deref)
    if need_merge:
        copied["x-yscb-merge"] = extra_merge
    if need_dedupe:
        copied["x-yscb-dedupe"] = extra_dedupe
    return copied


def _ctb_iter_candidate_branches(schema: JsonObject, defs: JsonObject) -> tuple[JsonObject, ...]:
    resolved = _ctb_deref_preserving_meta(schema, defs)
    any_of = resolved.get("anyOf")
    if not isinstance(any_of, (list, tuple)):
        return () if resolved.get("type") == "null" else (resolved,)
    out: list[JsonObject] = []
    for branch in any_of:
        if isinstance(branch, Mapping):
            for sub_b in _ctb_iter_candidate_branches(branch, defs):
                patched = dict(sub_b)
                changed = False
                if "x-yscb-merge" not in patched and "x-yscb-merge" in resolved:
                    patched["x-yscb-merge"] = resolved["x-yscb-merge"]
                    changed = True
                if "x-yscb-dedupe" not in patched and "x-yscb-dedupe" in resolved:
                    patched["x-yscb-dedupe"] = resolved["x-yscb-dedupe"]
                    changed = True
                out.append(patched if changed else sub_b)
    return tuple(out)


def _ctb_unwrap_non_null_branch(schema: JsonObject, defs: JsonObject) -> JsonObject:
    cands = _ctb_iter_candidate_branches(schema, defs)
    if cands:
        return cands[0]
    return ctb_deref_schema(schema, defs)


def _ctb_branch_matches_value(
    branch: JsonObject,
    val: JsonValue,
    defs: JsonObject,
    _depth: int = 0,
) -> bool:
    if _depth > 32:
        return True
    resolved = _ctb_deref_preserving_meta(branch, defs)
    any_of = resolved.get("anyOf")
    if isinstance(any_of, (list, tuple)):
        return any(
            isinstance(b, Mapping) and _ctb_branch_matches_value(b, val, defs, _depth + 1)
            for b in any_of
        )
    if "enum" in resolved and isinstance(resolved["enum"], (list, tuple)):
        return any(type(val) is type(ev) and val == ev for ev in resolved["enum"])
    b_type = resolved.get("type")
    if b_type is None:
        return True
    if b_type == "null":
        return val is None
    if b_type == "boolean":
        return type(val) is bool
    if b_type == "integer":
        return type(val) is int
    if b_type == "number":
        return type(val) in (int, float)
    if b_type == "string":
        return type(val) is str
    if b_type == "array":
        if not isinstance(val, list):
            return False
        min_items = resolved.get("minItems")
        max_items = resolved.get("maxItems")
        if type(min_items) is int and len(val) < min_items:
            return False
        if type(max_items) is int and len(val) > max_items:
            return False
        pfx = resolved.get("prefixItems")
        if isinstance(pfx, (list, tuple)):
            if len(val) != len(pfx):
                return False
            return all(
                isinstance(ps, Mapping) and _ctb_branch_matches_value(ps, pv, defs, _depth + 1)
                for ps, pv in zip(pfx, val)
            )
        items_sc = resolved.get("items")
        if isinstance(items_sc, Mapping):
            return all(_ctb_branch_matches_value(items_sc, elem, defs, _depth + 1) for elem in val)
        return True
    if b_type == "object":
        if not isinstance(val, Mapping):
            return False
        props = resolved.get("properties")
        add_props = resolved.get("additionalProperties", True)
        if isinstance(props, Mapping):
            for k, v in val.items():
                if k in props:
                    p_sc = props[k]
                    if isinstance(p_sc, Mapping) and not _ctb_branch_matches_value(p_sc, v, defs, _depth + 1):
                        return False
                elif add_props is False:
                    return False
                elif isinstance(add_props, Mapping):
                    if not _ctb_branch_matches_value(add_props, v, defs, _depth + 1):
                        return False
            return True
        if add_props is False and bool(val):
            return False
        if isinstance(add_props, Mapping):
            return all(_ctb_branch_matches_value(add_props, v, defs, _depth + 1) for v in val.values())
        return True
    return False


def _ctb_select_branch_for_value(schema: JsonObject, val: JsonValue, defs: JsonObject) -> JsonObject:
    cands = _ctb_iter_candidate_branches(schema, defs)
    for cand in cands:
        if _ctb_branch_matches_value(cand, val, defs):
            return cand
    return cands[0] if cands else ctb_deref_schema(schema, defs)


def _ctb_resolve_compatible_branch(
    schema: JsonObject,
    existing: JsonValue,
    incoming: JsonValue,
    defs: JsonObject,
) -> Optional[JsonObject]:
    cands = _ctb_iter_candidate_branches(schema, defs)
    if len(cands) <= 1:
        return cands[0] if cands else ctb_deref_schema(schema, defs)
    exist_matches = [idx for idx, c in enumerate(cands) if _ctb_branch_matches_value(c, existing, defs)]
    inc_matches = [idx for idx, c in enumerate(cands) if _ctb_branch_matches_value(c, incoming, defs)]
    if exist_matches and inc_matches:
        inc_set = set(inc_matches)
        for idx in exist_matches:
            if idx in inc_set:
                cand = cands[idx]
                if isinstance(existing, Mapping) and isinstance(incoming, Mapping):
                    preview: dict[str, JsonValue] = {**existing, **incoming}
                    if not _ctb_branch_matches_value(cand, preview, defs):
                        continue
                return cand
        return None
    if inc_matches:
        return cands[inc_matches[0]]
    return cands[0]


def _ctb_resolve_child_schema(
    parent_schema: JsonObject,
    key: str,
    defs: JsonObject,
    child_val: JsonValue = None,
) -> tuple[JsonObject, Optional[MergeStrategy]]:
    resolved_parent = _ctb_unwrap_non_null_branch(parent_schema, defs)
    props = resolved_parent.get("properties")
    if isinstance(props, Mapping) and isinstance(props.get(key), Mapping):
        prop_sc = _ctb_deref_preserving_meta(props[key], defs)
        raw_m = prop_sc.get("x-yscb-merge")
        if raw_m is None:
            branch_sc = (
                _ctb_select_branch_for_value(prop_sc, child_val, defs)
                if child_val is not None
                else _ctb_unwrap_non_null_branch(prop_sc, defs)
            )
            raw_m = branch_sc.get("x-yscb-merge")
        explicit = _ctb_parse_strategy_tag(raw_m, default=MergeStrategy.MERGE) if type(raw_m) is str else None
        return (prop_sc, explicit)
    add_props = resolved_parent.get("additionalProperties")
    if isinstance(add_props, Mapping):
        val_sc = _ctb_deref_preserving_meta(add_props, defs)
        raw_m = val_sc.get("x-yscb-merge")
        if raw_m is None:
            branch_sc = (
                _ctb_select_branch_for_value(val_sc, child_val, defs)
                if child_val is not None
                else _ctb_unwrap_non_null_branch(val_sc, defs)
            )
            raw_m = branch_sc.get("x-yscb-merge")
        explicit = _ctb_parse_strategy_tag(raw_m, default=MergeStrategy.MERGE) if type(raw_m) is str else None
        return (val_sc, explicit)
    return ({}, None)


def _ctb_resolve_array_item_schema(parent_schema: JsonObject, defs: JsonObject) -> JsonObject:
    resolved_parent = _ctb_unwrap_non_null_branch(parent_schema, defs)
    items_sc = resolved_parent.get("items")
    return _ctb_deref_preserving_meta(items_sc, defs) if isinstance(items_sc, Mapping) else {}


_UNKNOWN_UNIQUE_OWNER: Final[str] = "<unknown>"


def _ctb_prune_unique_owners(ptr: str, ctx: _CtbMergeCtx) -> None:
    if ptr == "":
        ctx.unique_owners.clear()
        return
    prefix = f"{ptr}/"
    stale_keys = [k for k in ctx.unique_owners if k == ptr or k.startswith(prefix)]
    for k in stale_keys:
        del ctx.unique_owners[k]


def _ctb_seed_unique_owners_recursive(
    ptr: str,
    val: JsonValue,
    schema: JsonObject,
    defs: JsonObject,
    donor: str,
    ctx: _CtbMergeCtx,
) -> None:
    resolved = _ctb_deref_preserving_meta(schema, defs)
    active_sc = _ctb_select_branch_for_value(resolved, val, defs)
    raw_m = resolved.get("x-yscb-merge")
    if raw_m is None:
        raw_m = active_sc.get("x-yscb-merge")
    strat = _ctb_parse_strategy_tag(raw_m, default=MergeStrategy.MERGE)
    if strat == MergeStrategy.UNIQUE:
        owners = ctx.unique_owners.setdefault(ptr, {})
        if isinstance(val, Mapping):
            for k in val:
                owners[k] = donor
        elif isinstance(val, list):
            for item in val:
                owners[ctb_extract_unique_item_id(item)] = donor
        else:
            owners["__self__"] = donor
    if isinstance(val, Mapping):
        for k, v in val.items():
            child_sc, _ = _ctb_resolve_child_schema(active_sc, k, defs, v)
            _ctb_seed_unique_owners_recursive(ctb_join_pointer(ptr, k), v, child_sc, defs, donor, ctx)
    elif isinstance(val, list):
        pfx = active_sc.get("prefixItems")
        if isinstance(pfx, (list, tuple)):
            for idx, item in enumerate(val):
                elem_sc = pfx[idx] if idx < len(pfx) and isinstance(pfx[idx], Mapping) else {}
                _ctb_seed_unique_owners_recursive(f"{ptr}/{idx}", item, elem_sc, defs, donor, ctx)
        else:
            item_sc = _ctb_resolve_array_item_schema(active_sc, defs)
            for idx, item in enumerate(val):
                _ctb_seed_unique_owners_recursive(f"{ptr}/{idx}", item, item_sc, defs, donor, ctx)


def _ctb_extend_list(
    existing: list[JsonValue],
    incoming: list[JsonValue],
    ptr: str,
    dedupe: bool,
    donor: str,
    prov: CtbProvenanceTracker,
) -> list[JsonValue]:
    prov.touch(ptr, donor)
    if dedupe:
        seen_canon: dict[str, int] = {
            ctb_canonical_json_key(item): idx for idx, item in enumerate(existing)
        }
        for item in incoming:
            ck = ctb_canonical_json_key(item)
            if ck in seen_canon:
                dup_idx = seen_canon[ck]
                prov.touch(f"{ptr}/{dup_idx}", donor, update_owner=False)
            else:
                new_idx = len(existing)
                cloned_item = _ctb_clone_json_value(item)
                existing.append(cloned_item)
                seen_canon[ck] = new_idx
                prov.record_subtree(f"{ptr}/{new_idx}", cloned_item, donor)
    else:
        for item in incoming:
            new_idx = len(existing)
            cloned_item = _ctb_clone_json_value(item)
            existing.append(cloned_item)
            prov.record_subtree(f"{ptr}/{new_idx}", cloned_item, donor)
    return existing


def _ctb_merge_unique_container(
    existing: JsonValue,
    incoming: JsonValue,
    ptr: str,
    schema: JsonObject,
    defs: JsonObject,
    donor: str,
    prov: CtbProvenanceTracker,
    ctx: _CtbMergeCtx,
) -> JsonValue:
    owners = ctx.unique_owners.setdefault(ptr, {})
    severity = ValidationSeverity.ERROR if ctx.strict else ValidationSeverity.WARNING

    if isinstance(existing, dict) and isinstance(incoming, Mapping):
        active_map_sc = _ctb_resolve_compatible_branch(schema, existing, incoming, defs)
        if active_map_sc is None:
            active_map_sc = _ctb_select_branch_for_value(schema, incoming, defs)
        touched_any = False
        for key, raw_inc in incoming.items():
            child_ptr = ctb_join_pointer(ptr, key)
            child_sc, _ = _ctb_resolve_child_schema(active_map_sc, key, defs, raw_inc)
            if key in existing:
                prev_owner = owners.get(key, _UNKNOWN_UNIQUE_OWNER)
                if not ctx.is_project_override and prev_owner != donor:
                    ctx.issues.append(
                        ValidationIssue(
                            severity=severity,
                            source_label=ctx.source_label,
                            json_pointer=child_ptr,
                            message=(
                                f"Unique key collision on {key!r}: already declared by '{prev_owner}', "
                                f"cannot be redeclared by '{donor}'."
                            ),
                        )
                    )
                    continue
                touched_any = True
                existing[key] = _ctb_merge_node(
                    existing[key],
                    raw_inc,
                    child_ptr,
                    child_sc,
                    defs,
                    MergeStrategy.MERGE,
                    donor,
                    prov,
                    ctx,
                )
            else:
                touched_any = True
                cloned_v = _ctb_clone_json_value(raw_inc)
                existing[key] = cloned_v
                owners[key] = donor
                _ctb_seed_unique_owners_recursive(child_ptr, cloned_v, child_sc, defs, donor, ctx)
                prov.record_subtree(child_ptr, cloned_v, donor)
        if touched_any:
            prov.touch(ptr, donor)
        return existing

    if isinstance(existing, list) and isinstance(incoming, list):
        active_list_sc = _ctb_select_branch_for_value(schema, incoming, defs)
        item_sc = _ctb_resolve_array_item_schema(active_list_sc, defs)
        id_to_idx: dict[str, int] = {
            ctb_extract_unique_item_id(elem): idx for idx, elem in enumerate(existing)
        }
        touched_any = False
        for raw_inc in incoming:
            uid = ctb_extract_unique_item_id(raw_inc)
            if uid in id_to_idx:
                exist_idx = id_to_idx[uid]
                elem_ptr = f"{ptr}/{exist_idx}"
                prev_owner = owners.get(uid, _UNKNOWN_UNIQUE_OWNER)
                if not ctx.is_project_override and prev_owner != donor:
                    ctx.issues.append(
                        ValidationIssue(
                            severity=severity,
                            source_label=ctx.source_label,
                            json_pointer=elem_ptr,
                            message=(
                                f"Unique item collision ({uid}) at '{ptr}': already declared by '{prev_owner}', "
                                f"cannot be redeclared by '{donor}'."
                            ),
                        )
                    )
                    continue
                touched_any = True
                existing[exist_idx] = _ctb_merge_node(
                    existing[exist_idx],
                    raw_inc,
                    elem_ptr,
                    item_sc,
                    defs,
                    MergeStrategy.MERGE,
                    donor,
                    prov,
                    ctx,
                )
            else:
                touched_any = True
                new_idx = len(existing)
                cloned_item = _ctb_clone_json_value(raw_inc)
                existing.append(cloned_item)
                id_to_idx[uid] = new_idx
                owners[uid] = donor
                _ctb_seed_unique_owners_recursive(f"{ptr}/{new_idx}", cloned_item, item_sc, defs, donor, ctx)
                prov.record_subtree(f"{ptr}/{new_idx}", cloned_item, donor)
        if touched_any:
            prov.touch(ptr, donor)
        return existing

    prev_scalar_owner = owners.get("__self__", _UNKNOWN_UNIQUE_OWNER)
    if not ctx.is_project_override and prev_scalar_owner != donor:
        ctx.issues.append(
            ValidationIssue(
                severity=severity,
                source_label=ctx.source_label,
                json_pointer=ptr,
                message=(
                    f"Unique value collision at '{ptr}': already declared by '{prev_scalar_owner}', "
                    f"cannot be redeclared by '{donor}'."
                ),
            )
        )
        return existing
    cloned_val = _ctb_clone_json_value(incoming)
    prov.prune_descendants(ptr)
    _ctb_prune_unique_owners(ptr, ctx)
    _ctb_seed_unique_owners_recursive(ptr, cloned_val, schema, defs, donor, ctx)
    prov.record_subtree(ptr, cloned_val, donor)
    return cloned_val


def _ctb_merge_node(
    existing: JsonValue,
    incoming: JsonValue,
    ptr: str,
    raw_schema: JsonObject,
    defs: JsonObject,
    strategy: MergeStrategy,
    donor: str,
    prov: CtbProvenanceTracker,
    ctx: _CtbMergeCtx,
) -> JsonValue:
    schema = _ctb_deref_preserving_meta(raw_schema, defs)
    if strategy == MergeStrategy.REPLACE:
        cloned = _ctb_clone_json_value(incoming)
        prov.prune_descendants(ptr)
        _ctb_prune_unique_owners(ptr, ctx)
        _ctb_seed_unique_owners_recursive(ptr, cloned, schema, defs, donor, ctx)
        prov.record_subtree(ptr, cloned, donor)
        return cloned

    if strategy == MergeStrategy.UNIQUE:
        return _ctb_merge_unique_container(existing, incoming, ptr, schema, defs, donor, prov, ctx)

    if strategy == MergeStrategy.EXTEND:
        if isinstance(existing, list) and isinstance(incoming, list):
            compat_list_sc = _ctb_resolve_compatible_branch(schema, existing, incoming, defs)
            if compat_list_sc is not None and "prefixItems" not in compat_list_sc:
                dedupe = (schema.get("x-yscb-dedupe") is not False) and (
                    compat_list_sc.get("x-yscb-dedupe") is not False
                )
                return _ctb_extend_list(existing, incoming, ptr, dedupe, donor, prov)
        cloned = _ctb_clone_json_value(incoming)
        prov.prune_descendants(ptr)
        _ctb_prune_unique_owners(ptr, ctx)
        _ctb_seed_unique_owners_recursive(ptr, cloned, schema, defs, donor, ctx)
        prov.record_subtree(ptr, cloned, donor)
        return cloned

    if isinstance(existing, dict) and isinstance(incoming, Mapping):
        compat_obj_sc = _ctb_resolve_compatible_branch(schema, existing, incoming, defs)
        if compat_obj_sc is None:
            cloned_switch = _ctb_clone_json_value(incoming)
            prov.prune_descendants(ptr)
            _ctb_prune_unique_owners(ptr, ctx)
            _ctb_seed_unique_owners_recursive(ptr, cloned_switch, schema, defs, donor, ctx)
            prov.record_subtree(ptr, cloned_switch, donor)
            return cloned_switch
        prov.touch(ptr, donor)
        for key, raw_inc in incoming.items():
            child_ptr = ctb_join_pointer(ptr, key)
            child_sc, explicit_strat = _ctb_resolve_child_schema(compat_obj_sc, key, defs, raw_inc)
            if key in existing:
                eff_strat = explicit_strat if explicit_strat is not None else MergeStrategy.MERGE
                existing[key] = _ctb_merge_node(
                    existing[key], raw_inc, child_ptr, child_sc, defs, eff_strat, donor, prov, ctx
                )
            else:
                cloned_v = _ctb_clone_json_value(raw_inc)
                existing[key] = cloned_v
                _ctb_seed_unique_owners_recursive(child_ptr, cloned_v, child_sc, defs, donor, ctx)
                prov.record_subtree(child_ptr, cloned_v, donor)
        return existing

    if isinstance(existing, list) and isinstance(incoming, list):
        compat_arr_sc = _ctb_resolve_compatible_branch(schema, existing, incoming, defs)
        if compat_arr_sc is None or "prefixItems" in schema or "prefixItems" in compat_arr_sc:
            cloned_tuple = _ctb_clone_json_value(incoming)
            prov.prune_descendants(ptr)
            _ctb_prune_unique_owners(ptr, ctx)
            _ctb_seed_unique_owners_recursive(ptr, cloned_tuple, schema, defs, donor, ctx)
            prov.record_subtree(ptr, cloned_tuple, donor)
            return cloned_tuple
        dedupe = (schema.get("x-yscb-dedupe") is not False) and (compat_arr_sc.get("x-yscb-dedupe") is not False)
        return _ctb_extend_list(existing, incoming, ptr, dedupe, donor, prov)

    cloned_scalar = _ctb_clone_json_value(incoming)
    prov.prune_descendants(ptr)
    _ctb_prune_unique_owners(ptr, ctx)
    _ctb_seed_unique_owners_recursive(ptr, cloned_scalar, schema, defs, donor, ctx)
    prov.record_subtree(ptr, cloned_scalar, donor)
    return cloned_scalar


def _ctb_validate_core_builtin_extras(
    *,
    yscb_root: HostPath,
    target_module: ModuleId,
    donor_module: Optional[ModuleId],
    source_label: str,
    sanitized_points: Mapping[str, JsonValue],
    strict: bool,
    issues: list[ValidationIssue],
) -> Mapping[str, JsonValue]:
    if target_module != _CORE_TARGET_ID or not sanitized_points:
        return sanitized_points

    severity = ValidationSeverity.ERROR if strict else ValidationSeverity.WARNING
    out_points: dict[str, JsonValue] = dict(sanitized_points)

    raw_schemes = out_points.get("uri_schemes")
    if isinstance(raw_schemes, Mapping):
        filtered_schemes: dict[str, JsonValue] = {}
        changed_schemes = False
        for scheme_key, spec_val in raw_schemes.items():
            if isinstance(spec_val, Mapping):
                tok_val = spec_val.get("token")
                if tok_val is not None and tok_val != scheme_key:
                    changed_schemes = True
                    tok_ptr = ctb_join_pointer(ctb_join_pointer("/uri_schemes", scheme_key), "token")
                    issues.append(
                        ValidationIssue(
                            severity=severity,
                            source_label=source_label,
                            json_pointer=tok_ptr,
                            message=(
                                f"URI scheme token {tok_val!r} must match outer mapping key {scheme_key!r}."
                            ),
                        )
                    )
                    continue
            filtered_schemes[scheme_key] = spec_val
        if changed_schemes:
            out_points["uri_schemes"] = filtered_schemes

    if donor_module is not None and "locales" in out_points:
        raw_loc_ptrs = out_points["locales"]
        if isinstance(raw_loc_ptrs, Mapping):
            str_ptrs = {k: v for k, v in raw_loc_ptrs.items() if type(k) is str and type(v) is str}
            donor_root = try_resolve_contained_subpath(yscb_root, ".modules", donor_module.value)
            if donor_root is None:
                issues.append(
                    ValidationIssue(
                        severity=severity,
                        source_label=source_label,
                        json_pointer="/locales",
                        message=f"Donor module directory missing or unsafe for '{donor_module.value}'.",
                    )
                )
            else:
                loc_issues = validate_locale_bundle(donor_module, donor_root, str_ptrs)
                if strict:
                    issues.extend(loc_issues)
                else:
                    for li in loc_issues:
                        issues.append(
                            ValidationIssue(
                                severity=ValidationSeverity.WARNING,
                                source_label=li.source_label,
                                json_pointer=li.json_pointer,
                                message=li.message,
                                suggestion=li.suggestion,
                            )
                        )

    return out_points


def _ctb_apply_validated_donor_points(
    *,
    raw_merged: MutableJsonObject,
    sanitized_points: Mapping[str, JsonValue],
    bundle: Optional[ContributesSchemaBundle],
    donor: str,
    source_label: str,
    strict: bool,
    is_project_override: bool,
    prov: CtbProvenanceTracker,
    unique_owners: dict[str, dict[str, str]],
    issues: list[ValidationIssue],
) -> None:
    if not sanitized_points or bundle is None:
        return
    raw_props = bundle.points_schema.get("properties")
    points_props: Mapping[str, JsonValue] = raw_props if isinstance(raw_props, Mapping) else {}
    raw_defs = bundle.points_schema.get("$defs")
    defs_map: JsonObject = raw_defs if isinstance(raw_defs, Mapping) else {}

    merge_ctx = _CtbMergeCtx(
        source_label=source_label,
        strict=strict,
        is_project_override=is_project_override,
        unique_owners=unique_owners,
        issues=issues,
    )

    for point_name, point_val in sanitized_points.items():
        raw_pt_sc = points_props.get(point_name)
        pt_schema: JsonObject = raw_pt_sc if isinstance(raw_pt_sc, Mapping) else {}
        point_ptr = ctb_join_pointer("", point_name)
        is_bucket = (
            pt_schema.get("x-yscb-bucket-by-donor") is True
            or pt_schema.get("x-yscb-merge") == MergeStrategy.BUCKET_BY_DONOR.value
        )
        if is_bucket:
            prov.touch("", donor)
            prov.touch(point_ptr, donor)
            existing_bucket = raw_merged.get(point_name)
            if not isinstance(existing_bucket, dict):
                existing_bucket = {}
                raw_merged[point_name] = existing_bucket
            donor_ptr = ctb_join_pointer(point_ptr, donor)
            if donor in existing_bucket:
                existing_bucket[donor] = _ctb_merge_node(
                    existing_bucket[donor],
                    point_val,
                    donor_ptr,
                    pt_schema,
                    defs_map,
                    MergeStrategy.MERGE,
                    donor,
                    prov,
                    merge_ctx,
                )
            else:
                cloned_bucket_val = _ctb_clone_json_value(point_val)
                existing_bucket[donor] = cloned_bucket_val
                _ctb_seed_unique_owners_recursive(
                    donor_ptr,
                    cloned_bucket_val,
                    pt_schema,
                    defs_map,
                    donor,
                    merge_ctx,
                )
                prov.record_subtree(donor_ptr, cloned_bucket_val, donor)
            continue

        pt_strategy = _ctb_parse_strategy_tag(
            pt_schema.get("x-yscb-merge"),
            default=MergeStrategy.MERGE,
        )
        if point_name in raw_merged:
            raw_merged[point_name] = _ctb_merge_node(
                raw_merged[point_name],
                point_val,
                point_ptr,
                pt_schema,
                defs_map,
                pt_strategy,
                donor,
                prov,
                merge_ctx,
            )
            if prov.has_donor(point_ptr, donor):
                prov.touch("", donor)
        else:
            cloned_pt = _ctb_clone_json_value(point_val)
            raw_merged[point_name] = cloned_pt
            _ctb_seed_unique_owners_recursive(point_ptr, cloned_pt, pt_schema, defs_map, donor, merge_ctx)
            prov.touch("", donor)
            prov.record_subtree(point_ptr, cloned_pt, donor)


def _ctb_read_optional_contained_json(root: HostPath, *subparts: str) -> _CtbLoadedJsonResult:
    cur_raw = str(root)
    if is_symlink_or_reparse(cur_raw):
        return _CtbLoadedJsonResult(
            present=True,
            payload=None,
            error_message=f"Refusing symlinked workspace root: '{root}'.",
        )
    for seg in subparts[:-1]:
        cur_raw = os.path.join(cur_raw, seg)
        if is_symlink_or_reparse(cur_raw):
            return _CtbLoadedJsonResult(
                present=True,
                payload=None,
                error_message=f"Refusing symlinked intermediate directory along '{'/'.join(subparts)}'.",
            )
        if not os.path.lexists(cur_raw):
            return _CtbLoadedJsonResult(present=False, payload=None, error_message=None)

    leaf_raw = os.path.join(cur_raw, subparts[-1])
    if is_symlink_or_reparse(leaf_raw):
        return _CtbLoadedJsonResult(
            present=True,
            payload=None,
            error_message=f"Refusing symlinked JSON file '{'/'.join(subparts)}'.",
        )
    if not os.path.lexists(leaf_raw):
        return _CtbLoadedJsonResult(present=False, payload=None, error_message=None)

    resolved = try_resolve_contained_subpath(root, *subparts)
    if resolved is None:
        return _CtbLoadedJsonResult(
            present=True,
            payload=None,
            error_message=f"Path containment check failed for '{'/'.join(subparts)}'.",
        )
    try:
        raw_bytes = read_nofollow_regular_bytes(str(resolved), max_bytes=MAX_JSON_FILE_BYTES)
    except OSError as exc:
        return _CtbLoadedJsonResult(
            present=True,
            payload=None,
            error_message=f"Failed reading JSON file '{'/'.join(subparts)}': {exc}",
        )
    if raw_bytes is None:
        return _CtbLoadedJsonResult(
            present=True,
            payload=None,
            error_message=f"Refusing non-regular, symlinked, or oversized JSON file '{'/'.join(subparts)}'.",
        )
    try:
        parsed = strict_parse_json_object(raw_bytes.decode("utf-8"))
        return _CtbLoadedJsonResult(present=True, payload=parsed, error_message=None)
    except (UnicodeDecodeError, ValueError) as exc:
        return _CtbLoadedJsonResult(
            present=True,
            payload=None,
            error_message=f"Malformed JSON object in '{'/'.join(subparts)}': {safe_exception_summary(exc)}",
        )


def _ctb_load_disk_schema_bundle(yscb_root: HostPath, target_module: ModuleId) -> Optional[ContributesSchemaBundle]:
    loaded = _ctb_read_optional_contained_json(
        yscb_root, ".modules", target_module.value, "contributes", "_schema.json"
    )
    if not loaded.present:
        return None
    if loaded.error_message is not None or loaded.payload is None:
        raise YscbError(
            ErrorCode.CONTRIBUTES_INVALID,
            f"Corrupt schema bundle for '{target_module.value}': {loaded.error_message}",
        )
    bundle = ContributesSchemaBundle.from_json(loaded.payload)
    if bundle.target_module != target_module:
        raise YscbError(
            ErrorCode.CONTRIBUTES_INVALID,
            f"Schema bundle target_module '{bundle.target_module.value}' mismatches directory '{target_module.value}'.",
        )
    return bundle


def _ctb_collect_forbidden_local_override_issues(
    yscb_root: HostPath,
    target_module: ModuleId,
    *,
    strict: bool,
    issues: list[ValidationIssue],
) -> None:
    if has_symlink_raw_path(str(yscb_root)) or is_symlink_or_reparse(str(yscb_root)):
        return
    for local_dir in ("config", ".config.local"):
        dir_l1 = os.path.join(str(yscb_root), local_dir)
        if is_symlink_or_reparse(dir_l1):
            if local_dir == ".config.local":
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR if strict else ValidationSeverity.WARNING,
                        source_label=f"project:{local_dir}",
                        json_pointer="",
                        message=f"Refusing symlink directory '{local_dir}' during contributes aggregation.",
                    )
                )
            continue
        dir_l2 = os.path.join(dir_l1, target_module.value)
        if os.path.lexists(dir_l1) and is_symlink_or_reparse(dir_l2):
            if local_dir == ".config.local":
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR if strict else ValidationSeverity.WARNING,
                        source_label=f"project:{local_dir}/{target_module.value}",
                        json_pointer="",
                        message=(
                            f"Refusing symlink directory '{local_dir}/{target_module.value}' "
                            "during contributes aggregation."
                        ),
                    )
                )
            continue
        mod_cfg_dir = try_resolve_contained_subpath(yscb_root, local_dir, target_module.value)
        if mod_cfg_dir is not None and os.path.lexists(os.path.join(str(mod_cfg_dir), "contribute.local.json")):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    source_label=f"project:{local_dir}/{target_module.value}/contribute.local.json",
                    json_pointer="",
                    message=(
                        f"Local contributes override '{local_dir}/{target_module.value}/contribute.local.json' "
                        "is forbidden and has been ignored."
                    ),
                    suggestion=f"Move team-shared overrides into 'config/{target_module.value}/contribute.json'.",
                )
            )


class ContributesAggregator:
    """Pure-in-memory two-tier topological contributes aggregator with zero disk cache writes."""

    def __init__(
        self,
        *,
        yscb_root: HostPath,
        manifests: Sequence[ModuleManifest],
        live_specs: Mapping[ModuleId, Sequence[ExtensionPointSpec[object]]] = _EMPTY_LIVE_SPECS,
    ) -> None:
        if not isinstance(yscb_root, HostPath):
            raise ValueError(f"ContributesAggregator.yscb_root must be HostPath, got {yscb_root!r}")
        self._lock = threading.RLock()
        self._yscb_root: HostPath = yscb_root
        self._topo_manifests: tuple[ModuleManifest, ...] = _ctb_sort_manifests_topologically(manifests)
        self._live_bundles: dict[ModuleId, ContributesSchemaBundle] = _ctb_compile_live_specs_map(live_specs)
        self._disk_bundles: dict[ModuleId, Optional[ContributesSchemaBundle]] = {}
        self._reload_gen: int = 0

    def reload(
        self,
        manifests: Optional[Sequence[ModuleManifest]] = None,
        live_specs: Optional[Mapping[ModuleId, Sequence[ExtensionPointSpec[object]]]] = None,
    ) -> None:
        """Reload installed module manifests and/or live ExtensionPointSpec definitions."""
        new_topo = _ctb_sort_manifests_topologically(manifests) if manifests is not None else None
        new_live = _ctb_compile_live_specs_map(live_specs) if live_specs is not None else None
        with self._lock:
            self._reload_gen += 1
            if new_topo is not None:
                self._topo_manifests = new_topo
            if new_live is not None:
                self._live_bundles = new_live
            self._disk_bundles.clear()

    def _resolve_bundle_for_gen(
        self,
        target_module: ModuleId,
        observed_gen: int,
        yscb_root: HostPath,
    ) -> Optional[ContributesSchemaBundle]:
        bundle = _ctb_load_disk_schema_bundle(yscb_root, target_module)
        with self._lock:
            if self._reload_gen == observed_gen:
                self._disk_bundles[target_module] = bundle
        return bundle

    def get_schema_bundle(self, target_module: ModuleId) -> Optional[ContributesSchemaBundle]:
        """Return the ContributesSchemaBundle for ``target_module`` from live_specs or disk _schema.json."""
        if not isinstance(target_module, ModuleId):
            raise ValueError(f"get_schema_bundle target_module must be ModuleId, got {target_module!r}")
        with self._lock:
            if target_module in self._live_bundles:
                return self._live_bundles[target_module]
            if target_module in self._disk_bundles:
                return self._disk_bundles[target_module]
            observed_gen = self._reload_gen
            yscb_root = self._yscb_root
        return self._resolve_bundle_for_gen(target_module, observed_gen, yscb_root)

    def list_extension_points(
        self,
        target_module: Optional[ModuleId] = None,
    ) -> Mapping[ModuleId, ContributesSchemaBundle]:
        """Return available ContributesSchemaBundles for ``target_module`` or all registered modules."""
        if target_module is not None:
            if not isinstance(target_module, ModuleId):
                raise ValueError(
                    f"list_extension_points target_module must be ModuleId or None, got {target_module!r}"
                )
            single = self.get_schema_bundle(target_module)
            return MappingProxyType({target_module: single}) if single is not None else MappingProxyType({})

        with self._lock:
            candidates = self._ordered_target_ids_locked()
        result: dict[ModuleId, ContributesSchemaBundle] = {}
        for mod_id in candidates:
            bundle = self.get_schema_bundle(mod_id)
            if bundle is not None:
                result[mod_id] = bundle
        return MappingProxyType(result)

    def _ordered_target_ids_locked(self) -> tuple[ModuleId, ...]:
        seen: set[ModuleId] = set()
        ordered: list[ModuleId] = []
        for manifest in self._topo_manifests:
            if manifest.id not in seen:
                seen.add(manifest.id)
                ordered.append(manifest.id)
        extra_live = sorted(
            (mid for mid in self._live_bundles if mid not in seen),
            key=_ctb_topo_rank_key,
        )
        ordered.extend(extra_live)
        return tuple(ordered)

    def _run_target_pipeline(
        self,
        target_module: ModuleId,
        *,
        strict: bool,
    ) -> tuple[AggregatedContributes, tuple[ValidationIssue, ...]]:
        with self._lock:
            topo_donors = self._topo_manifests
            yscb_root = self._yscb_root
            observed_gen = self._reload_gen
            has_cached_bundle = target_module in self._live_bundles or target_module in self._disk_bundles
            cached_bundle = (
                self._live_bundles[target_module]
                if target_module in self._live_bundles
                else self._disk_bundles.get(target_module)
            )

        issues: list[ValidationIssue] = []
        raw_merged: MutableJsonObject = {}
        prov = CtbProvenanceTracker()
        unique_owners: dict[str, dict[str, str]] = {}

        bundle: Optional[ContributesSchemaBundle] = cached_bundle
        if not has_cached_bundle:
            try:
                bundle = self._resolve_bundle_for_gen(target_module, observed_gen, yscb_root)
            except YscbError as exc:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR if strict else ValidationSeverity.WARNING,
                        source_label=f"module:{target_module.value}/contributes/_schema.json",
                        json_pointer="",
                        message=exc.detail.message,
                    )
                )
                agg_empty = AggregatedContributes(
                    target_module=target_module,
                    raw_merged={},
                    provenance=prov.build(),
                    warnings=tuple(i for i in issues if i.severity == ValidationSeverity.WARNING),
                )
                return (agg_empty, tuple(issues))

        _ctb_collect_forbidden_local_override_issues(
            yscb_root,
            target_module,
            strict=strict,
            issues=issues,
        )

        for donor_manifest in topo_donors:
            donor_id = donor_manifest.id
            donor_label = f"module:{donor_id.value}/contributes/{target_module.value}.json"
            loaded = _ctb_read_optional_contained_json(
                yscb_root, ".modules", donor_id.value, "contributes", f"{target_module.value}.json"
            )
            if not loaded.present:
                continue
            if loaded.error_message is not None or loaded.payload is None:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR if strict else ValidationSeverity.WARNING,
                        source_label=donor_label,
                        json_pointer="",
                        message=loaded.error_message or f"Failed to read '{donor_label}'.",
                    )
                )
                continue
            val_res = ctb_validate_donor_payload(
                source_label=donor_label,
                target_module=target_module,
                raw_payload=loaded.payload,
                bundle=bundle,
                strict=strict,
                is_project_override=False,
                existing_merged=raw_merged,
            )
            issues.extend(val_res.issues)
            eff_donor_points = _ctb_validate_core_builtin_extras(
                yscb_root=yscb_root,
                target_module=target_module,
                donor_module=donor_id,
                source_label=donor_label,
                sanitized_points=val_res.sanitized_points,
                strict=strict,
                issues=issues,
            )
            _ctb_apply_validated_donor_points(
                raw_merged=raw_merged,
                sanitized_points=eff_donor_points,
                bundle=bundle,
                donor=donor_id.value,
                source_label=donor_label,
                strict=strict,
                is_project_override=False,
                prov=prov,
                unique_owners=unique_owners,
                issues=issues,
            )

        proj_label = f"project:config/{target_module.value}/contribute.json"
        proj_loaded = _ctb_read_optional_contained_json(
            yscb_root, "config", target_module.value, "contribute.json"
        )
        if proj_loaded.present:
            if proj_loaded.error_message is not None or proj_loaded.payload is None:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR if strict else ValidationSeverity.WARNING,
                        source_label=proj_label,
                        json_pointer="",
                        message=proj_loaded.error_message or f"Failed to read '{proj_label}'.",
                    )
                )
            else:
                proj_val = ctb_validate_donor_payload(
                    source_label=proj_label,
                    target_module=target_module,
                    raw_payload=proj_loaded.payload,
                    bundle=bundle,
                    strict=strict,
                    is_project_override=True,
                    existing_merged=raw_merged,
                )
                issues.extend(proj_val.issues)
                eff_proj_points = _ctb_validate_core_builtin_extras(
                    yscb_root=yscb_root,
                    target_module=target_module,
                    donor_module=None,
                    source_label=proj_label,
                    sanitized_points=proj_val.sanitized_points,
                    strict=strict,
                    issues=issues,
                )
                _ctb_apply_validated_donor_points(
                    raw_merged=raw_merged,
                    sanitized_points=eff_proj_points,
                    bundle=bundle,
                    donor=_PROJECT_DONOR_LABEL,
                    source_label=proj_label,
                    strict=strict,
                    is_project_override=True,
                    prov=prov,
                    unique_owners=unique_owners,
                    issues=issues,
                )

        warnings_tuple = tuple(i for i in issues if i.severity == ValidationSeverity.WARNING)
        aggregated = AggregatedContributes(
            target_module=target_module,
            raw_merged=raw_merged,
            provenance=prov.build(),
            warnings=warnings_tuple,
        )
        return (aggregated, tuple(issues))

    def aggregate(self, target_module: ModuleId, *, strict: bool = False) -> AggregatedContributes:
        """Aggregate topological module contributions and project override for ``target_module``."""
        if not isinstance(target_module, ModuleId):
            raise ValueError(f"aggregate target_module must be ModuleId, got {target_module!r}")
        require_pure_bool(strict, "strict")
        aggregated, all_issues = self._run_target_pipeline(target_module, strict=strict)
        errors = [i for i in all_issues if i.severity == ValidationSeverity.ERROR]
        if strict and errors:
            first = errors[0]
            loc = f"{first.source_label} ({first.json_pointer or '/'})"
            suffix = f" (+{len(errors) - 1} more error(s))" if len(errors) > 1 else ""
            raise YscbError(
                ErrorCode.CONTRIBUTES_INVALID,
                f"Contributes validation failed for '{target_module.value}' at {loc}: {first.message}{suffix}",
                remediation=first.suggestion,
            )
        return aggregated

    def validate_all(self, *, strict: bool = True) -> tuple[ValidationReport, ...]:
        """Validate all installed/registered target modules and return their ValidationReports."""
        require_pure_bool(strict, "strict")
        with self._lock:
            targets = self._ordered_target_ids_locked()
        reports: list[ValidationReport] = []
        for target_id in targets:
            _, issues = self._run_target_pipeline(target_id, strict=strict)
            reports.append(ValidationReport(target_module=target_id, issues=issues))
        return tuple(reports)

    def validate_donor_file(
        self,
        donor_label: str,
        target_module: ModuleId,
        raw_payload: JsonObject,
        *,
        strict: bool = True,
    ) -> ValidationReport:
        """Validate a standalone donor payload against ``target_module``'s schema bundle."""
        clean_label = require_pure_str(donor_label, "donor_label", non_empty=True)
        if not isinstance(target_module, ModuleId):
            raise ValueError(f"validate_donor_file target_module must be ModuleId, got {target_module!r}")
        require_pure_bool(strict, "strict")
        try:
            bundle = self.get_schema_bundle(target_module)
        except YscbError as exc:
            return ValidationReport(
                target_module=target_module,
                issues=(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR if strict else ValidationSeverity.WARNING,
                        source_label=clean_label,
                        json_pointer="",
                        message=exc.detail.message,
                    ),
                ),
            )
        is_proj = clean_label == _PROJECT_DONOR_LABEL or clean_label.startswith("project:")
        res = ctb_validate_donor_payload(
            source_label=clean_label,
            target_module=target_module,
            raw_payload=raw_payload,
            bundle=bundle,
            strict=strict,
            is_project_override=is_proj,
            existing_merged=None,
        )
        return ValidationReport(target_module=target_module, issues=res.issues)
