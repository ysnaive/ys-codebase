"""Strongly typed extension point contracts, field merge annotations, and static schema bundle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Generic, Mapping, Optional, TypeVar

from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary, sanitize_utf8_text
from core.foundation.primitives import (
    JsonObject,
    ModuleId,
    MutableJsonObject,
    clone_strict_json_object,
    is_valid_type_annotation,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
)

TPoint = TypeVar("TPoint")


def ctb_deep_freeze_json(val: object) -> object:
    """Recursively convert JSON dicts and lists into immutable MappingProxyType and tuple."""
    if isinstance(val, Mapping):
        return MappingProxyType({k: ctb_deep_freeze_json(v) for k, v in val.items()})
    if isinstance(val, (list, tuple)):
        return tuple(ctb_deep_freeze_json(item) for item in val)
    return val


class MergeStrategy(Enum):
    """Deterministic aggregation strategy for Contributes 2.0 extension points and fields."""

    MERGE = "merge"
    EXTEND = "extend"
    REPLACE = "replace"
    UNIQUE = "unique"
    BUCKET_BY_DONOR = "bucket_by_donor"


@dataclass(frozen=True, slots=True)
class ContribField:
    """Field-level merge strategy, IDE description, and deduplication metadata for Annotated."""

    merge: Optional[MergeStrategy] = None
    description: str = ""
    dedupe: bool = True

    def __post_init__(self) -> None:
        if self.merge is not None and not isinstance(self.merge, MergeStrategy):
            raise ValueError(f"ContribField.merge must be MergeStrategy or None, got {self.merge!r}")
        clean_desc = sanitize_utf8_text(require_pure_str(self.description, "ContribField.description"))
        object.__setattr__(self, "description", clean_desc)
        require_pure_bool(self.dedupe, "ContribField.dedupe")


@dataclass(frozen=True, slots=True)
class ExtensionPointSpec(Generic[TPoint]):
    """Host module strongly typed single source of truth for one extension point."""

    name: str
    payload_type: type[TPoint]
    description: str = ""
    merge_strategy: MergeStrategy = MergeStrategy.MERGE
    strict_fields: bool = True

    def __post_init__(self) -> None:
        raw_name = require_pure_str(self.name, "ExtensionPointSpec.name", non_empty=True)
        clean_name = raw_name.strip()
        if (
            not clean_name
            or clean_name == "$schema"
            or any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in clean_name)
        ):
            raise ValueError(f"Invalid ExtensionPointSpec.name: {self.name!r}")
        object.__setattr__(self, "name", clean_name)
        if not is_valid_type_annotation(self.payload_type):
            raise ValueError(
                f"ExtensionPointSpec.payload_type must be a valid type annotation, got {self.payload_type!r}"
            )
        clean_desc = sanitize_utf8_text(require_pure_str(self.description, "ExtensionPointSpec.description"))
        object.__setattr__(self, "description", clean_desc)
        if not isinstance(self.merge_strategy, MergeStrategy):
            raise ValueError(
                f"ExtensionPointSpec.merge_strategy must be MergeStrategy, got {self.merge_strategy!r}"
            )
        require_pure_bool(self.strict_fields, "ExtensionPointSpec.strict_fields")


def _ctb_validate_points_schema_structure(schema_obj: JsonObject) -> None:
    raw_props = schema_obj.get("properties")
    if raw_props is not None:
        if not isinstance(raw_props, Mapping):
            raise ValueError("points_schema.properties must be a JSON object mapping.")
        for pt_name, pt_schema in raw_props.items():
            if type(pt_name) is not str or not pt_name.strip() or not isinstance(pt_schema, Mapping):
                raise ValueError(f"Invalid extension point schema entry for {pt_name!r}.")
    raw_defs = schema_obj.get("$defs")
    if raw_defs is not None:
        if not isinstance(raw_defs, Mapping):
            raise ValueError("points_schema.$defs must be a JSON object mapping.")
        for def_name, def_schema in raw_defs.items():
            if type(def_name) is not str or not def_name or not isinstance(def_schema, Mapping):
                raise ValueError(f"Invalid $defs schema entry for {def_name!r}.")


@dataclass(frozen=True, slots=True)
class ContributesSchemaBundle:
    """Compiled static extension point contract serializable as contributes/_schema.json."""

    target_module: ModuleId
    schema_version: int
    points_schema: JsonObject

    def __post_init__(self) -> None:
        if not isinstance(self.target_module, ModuleId):
            raise ValueError(
                f"ContributesSchemaBundle.target_module must be ModuleId, got {self.target_module!r}"
            )
        require_pure_int(self.schema_version, "ContributesSchemaBundle.schema_version", min_val=1, max_val=2)
        cloned = clone_strict_json_object(
            self.points_schema,
            label="ContributesSchemaBundle.points_schema",
        )
        _ctb_validate_points_schema_structure(cloned)
        object.__setattr__(self, "points_schema", ctb_deep_freeze_json(cloned))

    def to_json(self) -> MutableJsonObject:
        """Serialize this schema bundle into a fresh JSON-safe dictionary."""
        return {
            "target_module": self.target_module.value,
            "schema_version": self.schema_version,
            "points_schema": clone_strict_json_object(
                self.points_schema,
                label="ContributesSchemaBundle.points_schema",
            ),
        }

    @classmethod
    def from_json(cls, raw: JsonObject) -> ContributesSchemaBundle:
        """Deserialize and validate a static contributes/_schema.json dictionary."""
        try:
            cloned = clone_strict_json_object(raw, label="ContributesSchemaBundle.from_json")
        except (TypeError, ValueError) as exc:
            raise YscbError(
                ErrorCode.CONTRIBUTES_INVALID,
                f"Invalid contributes schema bundle JSON: {safe_exception_summary(exc)}",
            ) from exc
        allowed_keys = frozenset({"$schema", "target_module", "schema_version", "points_schema"})
        extra_keys = sorted(k for k in cloned if k not in allowed_keys)
        if extra_keys:
            raise YscbError(
                ErrorCode.CONTRIBUTES_INVALID,
                f"Unexpected top-level keys in contributes schema bundle: {extra_keys}",
            )
        if "$schema" in cloned and type(cloned["$schema"]) is not str:
            raise YscbError(ErrorCode.CONTRIBUTES_INVALID, "Field '$schema' in schema bundle must be a string.")
        raw_target = cloned.get("target_module")
        raw_ver = cloned.get("schema_version")
        raw_points = cloned.get("points_schema")
        if type(raw_target) is not str:
            raise YscbError(ErrorCode.CONTRIBUTES_INVALID, "Missing or non-string 'target_module' in schema bundle.")
        if type(raw_ver) is not int:
            raise YscbError(ErrorCode.CONTRIBUTES_INVALID, "Missing or non-integer 'schema_version' in schema bundle.")
        if not isinstance(raw_points, Mapping):
            raise YscbError(ErrorCode.CONTRIBUTES_INVALID, "Missing or non-object 'points_schema' in schema bundle.")
        try:
            mod_id = ModuleId(raw_target)
            return cls(
                target_module=mod_id,
                schema_version=raw_ver,
                points_schema=raw_points,
            )
        except ValueError as exc:
            raise YscbError(
                ErrorCode.CONTRIBUTES_INVALID,
                f"Malformed contributes schema bundle for '{raw_target}': {safe_exception_summary(exc)}",
            ) from exc
