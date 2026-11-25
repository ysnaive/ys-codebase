"""Recursive default key infiller and JSON object merge helpers for configuration matrices."""

from __future__ import annotations

from typing import Mapping

from core.foundation.errors import ErrorCode, YscbError
from core.foundation.primitives import (
    MAX_USER_JSON_DEPTH,
    JsonObject,
    JsonValue,
    MutableJsonObject,
    clone_strict_json_object,
)


def cfg_clone_json_object(payload: object, *, label: str = "config object") -> MutableJsonObject:
    """Validate and deep-clone a strict JSON object, raising CONFIG_INVALID on violation."""
    try:
        return clone_strict_json_object(payload, max_depth=MAX_USER_JSON_DEPTH, label=label)
    except (TypeError, ValueError) as exc:
        raise YscbError(ErrorCode.CONFIG_INVALID, str(exc)) from exc


def cfg_clone_json_value(value: JsonValue, *, label: str = "config value") -> JsonValue:
    """Validate and deep-clone a single JSON value without container aliasing."""
    wrapped = cfg_clone_json_object({"value": value}, label=label)
    return wrapped["value"]


def _cfg_merge_cloned_dicts(
    base: MutableJsonObject,
    override: Mapping[str, JsonValue],
    depth: int,
) -> MutableJsonObject:
    if depth > MAX_USER_JSON_DEPTH:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Configuration merge exceeded maximum nesting depth ({MAX_USER_JSON_DEPTH}).",
        )
    merged: MutableJsonObject = dict(base)
    for key, over_val in override.items():
        cur_val = merged.get(key)
        if key in merged and isinstance(cur_val, dict) and isinstance(over_val, Mapping):
            merged[key] = _cfg_merge_cloned_dicts(cur_val, over_val, depth + 1)
        else:
            merged[key] = over_val
    return merged


def cfg_deep_merge_json_objects(base: JsonObject, override: JsonObject) -> MutableJsonObject:
    """Recursively merge two JSON objects where scalars and lists in override replace base."""
    clean_base = cfg_clone_json_object(base, label="base config")
    clean_override = cfg_clone_json_object(override, label="override config")
    return _cfg_merge_cloned_dicts(clean_base, clean_override, 0)


def _cfg_infill_missing_into(
    target: MutableJsonObject,
    template: MutableJsonObject,
    prefix: str,
    added_keys: list[str],
    depth: int,
) -> None:
    if depth > MAX_USER_JSON_DEPTH:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"DeepInfiller exceeded maximum JSON nesting depth ({MAX_USER_JSON_DEPTH}).",
        )
    for key, tmpl_val in template.items():
        key_path = f"{prefix}.{key}" if prefix else key
        if key not in target:
            target[key] = tmpl_val
            added_keys.append(key_path)
            continue
        existing_val = target[key]
        if isinstance(existing_val, dict) and isinstance(tmpl_val, dict):
            _cfg_infill_missing_into(existing_val, tmpl_val, key_path, added_keys, depth + 1)


class DeepInfiller:
    """Recursive in-place default key infiller preserving 100% of existing user values."""

    @staticmethod
    def infill(
        existing: JsonObject,
        template: JsonObject,
    ) -> tuple[MutableJsonObject, tuple[str, ...]]:
        out = cfg_clone_json_object(existing, label="DeepInfiller.infill existing")
        clean_tmpl = cfg_clone_json_object(template, label="DeepInfiller.infill template")
        added_keys: list[str] = []
        _cfg_infill_missing_into(out, clean_tmpl, "", added_keys, 0)
        return (out, tuple(added_keys))
