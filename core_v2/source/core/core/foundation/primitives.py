"""Immutable, construction-normalized domain value objects and JSON type aliases for Core 2.0."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
import os
import sys
from pathlib import Path
import re
from typing import (
    Callable,
    Final,
    ForwardRef,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    TypeAlias,
    TypeVar,
    get_args,
    get_origin,
)

JsonPrimitive: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonPrimitive | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
JsonObject: TypeAlias = Mapping[str, JsonValue]
IS_WINDOWS: Final[bool] = sys.platform == "win32"
MutableJsonObject: TypeAlias = dict[str, JsonValue]
MAX_USER_JSON_DEPTH: Final[int] = 128
MAX_ENVELOPE_JSON_DEPTH: Final[int] = MAX_USER_JSON_DEPTH + 6
MAX_PARSE_JSON_DEPTH: Final[int] = MAX_ENVELOPE_JSON_DEPTH + 2
_T = TypeVar("_T")


def _bind_json_alias_forward_module() -> None:
    for branch in get_args(JsonValue):
        for arg in get_args(branch):
            if isinstance(arg, ForwardRef):
                object.__setattr__(arg, "__forward_module__", __name__)


_bind_json_alias_forward_module()

_MODULE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_QUALIFIED_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$")


@dataclass(frozen=True, slots=True)
class ModuleId:
    """Validated module identifier (e.g., 'core', 'knowledge-db')."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise ValueError(f"ModuleId requires a plain str, got {self.value!r}")
        cleaned = self.value.strip()
        if not cleaned or not _MODULE_ID_RE.match(cleaned):
            raise ValueError(f"Invalid ModuleId: {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TaskId:
    """Validated qualified task identifier '<module>.<task_name>'."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise ValueError(f"TaskId requires a plain str, got {self.value!r}")
        cleaned = self.value.strip()
        if not cleaned or not _QUALIFIED_ID_RE.match(cleaned):
            raise ValueError(f"Invalid TaskId (expected '<module>.<name>'): {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    @property
    def module_id(self) -> ModuleId:
        return ModuleId(self.value.split(".", 1)[0])

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class EventId:
    """Validated qualified event identifier '<module>.<event_name>'."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise ValueError(f"EventId requires a plain str, got {self.value!r}")
        cleaned = self.value.strip()
        if not cleaned or not _QUALIFIED_ID_RE.match(cleaned):
            raise ValueError(f"Invalid EventId (expected '<module>.<name>'): {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    @property
    def module_id(self) -> ModuleId:
        return ModuleId(self.value.split(".", 1)[0])

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class HostPath:
    """Canonicalized absolute real host filesystem path free of implicit process cwd coupling."""

    path: Path
    comparison_key: str

    def __init__(self, raw: str | os.PathLike[str] | Path) -> None:
        if isinstance(raw, (bytes, bytearray, Enum)) or (isinstance(raw, str) and type(raw) is not str):
            raise ValueError(f"HostPath requires a plain str or PathLike[str], got {raw!r}")
        try:
            raw_str = os.fspath(raw)
        except TypeError as exc:
            raise ValueError(f"HostPath requires a plain str or PathLike[str], got {raw!r}") from exc
        if type(raw_str) is not str or not raw_str or "\x00" in raw_str or not Path(raw_str).is_absolute():
            raise ValueError(f"HostPath requires a non-empty absolute path: {raw!r}")
        try:
            raw_str.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"HostPath requires valid UTF-8 path without lone surrogates: {raw!r}") from exc
        resolved = _resolve_canonical_host_path(raw_str)
        resolved_str = str(resolved)
        try:
            resolved_str.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"Resolved HostPath contains non-UTF-8 surrogates: {resolved_str!r}") from exc
        norm_key = os.path.normcase(resolved_str)
        object.__setattr__(self, "path", resolved)
        object.__setattr__(self, "comparison_key", norm_key)

    def join(self, *parts: str) -> HostPath:
        if not parts:
            return self
        seps = "/\\" if IS_WINDOWS else "/"
        cleaned: list[str] = []
        for idx, part in enumerate(parts):
            require_pure_str(part, "HostPath.join part")
            cand_p = Path(part)
            if not part or "\x00" in part or cand_p.is_absolute() or bool(cand_p.anchor) or ".." in cand_p.parts:
                raise ValueError(f"HostPath.join requires relative non-traversing segments, got {part!r}")
            cleaned.append(part if idx == len(parts) - 1 else part.rstrip(seps))
        base = str(self.path).rstrip(seps) or str(self.path)
        prefix = base if base.endswith(tuple(seps)) else f"{base}{os.sep}"
        return HostPath(prefix + os.sep.join(cleaned))

    def resolve_caller_relative(self, target: str | os.PathLike[str]) -> HostPath:
        if isinstance(target, (bytes, bytearray, Enum)) or (isinstance(target, str) and type(target) is not str):
            raise ValueError(f"resolve_caller_relative requires plain str or PathLike[str], got {target!r}")
        try:
            raw_t = os.fspath(target)
        except TypeError as exc:
            raise ValueError(f"resolve_caller_relative requires plain str or PathLike[str], got {target!r}") from exc
        require_pure_str(raw_t, "resolve_caller_relative target")
        if not raw_t or "\x00" in raw_t:
            raise ValueError(f"resolve_caller_relative requires non-empty path: {target!r}")
        cand = Path(raw_t)
        if cand.is_absolute():
            return HostPath(raw_t)
        if bool(cand.anchor):
            raise ValueError(f"Anchor-relative path forbidden in resolve_caller_relative: {target!r}")
        seps = "/\\" if IS_WINDOWS else "/"
        base = str(self.path).rstrip(seps) or str(self.path)
        prefix = base if base.endswith(tuple(seps)) else f"{base}{os.sep}"
        return HostPath(f"{prefix}{raw_t}")

    def __str__(self) -> str:
        return str(self.path)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HostPath):
            return NotImplemented
        return self.comparison_key == other.comparison_key

    def __hash__(self) -> int:
        return hash(self.comparison_key)


def _resolve_canonical_host_path(raw_str: str) -> Path:
    seps = ("/", "\\") if IS_WINDOWS else ("/",)
    anchor = Path(raw_str).anchor
    if len(raw_str) > len(anchor) and raw_str.endswith(seps):
        real_dir = Path(os.path.realpath(raw_str))
        stripped = raw_str.rstrip("/\\" if IS_WINDOWS else "/")
        if (os.path.lexists(real_dir) or os.path.islink(stripped)) and not real_dir.is_dir():
            raise ValueError(f"Trailing path separator on non-directory HostPath: {raw_str!r}")
        return real_dir
    parent_str, tail = os.path.split(raw_str)
    if tail in ("", ".", ".."):
        return Path(os.path.realpath(raw_str))
    real_parent = Path(os.path.realpath(parent_str))
    cand = real_parent / tail
    if (
        os.path.islink(cand)
        and os.path.normcase(real_parent.name) in ("bin", "scripts")
        and (real_parent.parent / "pyvenv.cfg").is_file()
    ):
        real_target = os.path.realpath(cand)
        if os.path.isfile(real_target) and not os.path.isdir(real_target):
            return cand
    return Path(os.path.realpath(cand))


def _reject_nonfinite_json_constant(token: str) -> None:
    raise ValueError(f"Non-finite JSON constant rejected: {token}")


def _parse_finite_json_float(token: str) -> float:
    val = float(token)
    if not math.isfinite(val):
        raise ValueError(f"Overflowing non-finite JSON float rejected: {token}")
    return val


INT64_MIN: Final[int] = -(1 << 63)
INT64_MAX: Final[int] = (1 << 63) - 1


def _parse_bounded_json_int(token: str) -> int:
    digits = token[1:] if token[:1] in ("+", "-") else token
    if len(digits) > 20:
        raise ValueError("JSON integer out of int64 range.")
    val = int(token)
    if not (INT64_MIN <= val <= INT64_MAX):
        raise ValueError("JSON integer out of int64 range.")
    return val


def require_pure_str(val: object, label: str = "value", *, non_empty: bool = False) -> str:
    if type(val) is not str:
        raise ValueError(f"{label} must be an exact str, got {val!r}")
    val.encode("utf-8")
    if non_empty and not val.strip():
        raise ValueError(f"{label} must be a non-empty plain str.")
    return val


def require_pure_int(
    val: object,
    label: str = "value",
    *,
    min_val: Optional[int] = INT64_MIN,
    max_val: Optional[int] = INT64_MAX,
) -> int:
    if type(val) is not int:
        raise ValueError(f"{label} must be an exact int, got {val!r}")
    if (min_val is not None and val < min_val) or (max_val is not None and val > max_val):
        raise ValueError(f"{label} must be in [{min_val}, {max_val}], got {val!r}")
    return val


def invoke_observer_safely(fn: Callable[[], object]) -> None:
    """Execute an observer or progress callback isolating Exception, SystemExit, and GeneratorExit."""
    try:
        fn()
    except (Exception, SystemExit, GeneratorExit):
        return


def decrement_ref_count(table: dict[_T, int], key: _T) -> int:
    """Decrement positive integer ref-count for truthy key, popping entry when <= 0."""
    if not key:
        return 0
    rem = table.get(key, 0) - 1
    if rem <= 0:
        table.pop(key, None)
        return 0
    table[key] = rem
    return rem


def require_pure_bool(val: object, label: str = "value") -> bool:
    if type(val) is not bool:
        raise ValueError(f"{label} must be a bool, got {val!r}")
    return val


def require_typed_tuple(items: object, elem_type: type[_T], label: str = "items") -> tuple[_T, ...]:
    if isinstance(items, (str, bytes, bytearray, memoryview)) or not isinstance(items, Sequence):
        raise ValueError(f"{label} must be a non-string Sequence of {elem_type.__name__}.")
    tup = tuple(items)
    exact_scalars = (str, int, float, bool)
    for item in tup:
        if elem_type in exact_scalars:
            if type(item) is not elem_type:
                raise ValueError(f"{label} elements must be exact {elem_type.__name__}, got {item!r}")
        elif not isinstance(item, elem_type):
            raise ValueError(f"{label} elements must be {elem_type.__name__}, got {item!r}")
        if elem_type is str and type(item) is str:
            item.encode("utf-8")
    return tup


def require_typed_frozenset(items: object, elem_type: type[_T], label: str = "items") -> frozenset[_T]:
    """Validate an arbitrary non-string/bytes Iterable into a strongly typed frozenset."""
    if isinstance(items, (str, bytes, bytearray, memoryview)) or not isinstance(items, Iterable):
        raise ValueError(f"{label} must be an Iterable of {elem_type.__name__} (not str/bytes), got {items!r}")
    return frozenset(require_typed_tuple(tuple(items), elem_type, label))


def is_valid_type_annotation(tp_val: object) -> bool:
    return not isinstance(tp_val, bool) and (isinstance(tp_val, type) or get_origin(tp_val) is not None)


def _check_strict_json_scalar(val: object, *, label: str) -> JsonPrimitive:
    if isinstance(val, Enum):
        raise ValueError(f"{label} forbids unencoded Enum {type(val).__name__}")
    if val is None or type(val) is bool:
        return val
    if type(val) is int:
        if not (INT64_MIN <= val <= INT64_MAX):
            raise ValueError(f"{label} integer out of int64 range: {val!r}")
        return val
    if type(val) is float:
        if not math.isfinite(val):
            raise ValueError(f"{label} float must be finite: {val!r}")
        return val
    if type(val) is str:
        val.encode("utf-8")
        return val
    if isinstance(val, (int, float, str)):
        raise ValueError(f"{label} forbids custom scalar subclass {type(val).__name__}")
    raise TypeError(f"{label} contains unsupported JSON type {type(val).__name__}")


def validate_json_primitive(val: object, label: str = "payload") -> JsonPrimitive:
    try:
        return _check_strict_json_scalar(val, label=label)
    except TypeError as exc:
        raise ValueError(f"{label} contains unsupported JSON type {type(val).__name__}") from exc


def _walk_strict_json(
    cur: object,
    depth: int,
    max_depth: int,
    label: str,
    *,
    clone: bool,
) -> JsonValue:
    if depth > max_depth:
        raise ValueError(f"{label} exceeded maximum JSON nesting depth ({max_depth}).")
    if isinstance(cur, Mapping):
        out_map: MutableJsonObject = {}
        for k, v in cur.items():
            if type(k) is not str:
                raise TypeError(f"{label} mapping key must be exact str, got {type(k).__name__}")
            k.encode("utf-8")
            val = _walk_strict_json(v, depth + 1, max_depth, label, clone=clone)
            if clone:
                out_map[k] = val
        return out_map
    if isinstance(cur, (list, tuple)):
        if clone:
            return [_walk_strict_json(item, depth + 1, max_depth, label, clone=True) for item in cur]
        for item in cur:
            _walk_strict_json(item, depth + 1, max_depth, label, clone=False)
        return None
    return _check_strict_json_scalar(cur, label=label)


def validate_wire_json_object(
    payload: object,
    *,
    max_depth: int = MAX_ENVELOPE_JSON_DEPTH,
    label: str = "payload",
) -> None:
    """Validate an outbound JSON object symmetrically with strict_parse_json_object."""
    if not isinstance(payload, Mapping):
        raise TypeError(f"{label} must be a JSON object Mapping, got {type(payload).__name__}")
    try:
        _walk_strict_json(payload, 0, max_depth, label, clone=False)
    except RecursionError as exc:
        raise ValueError(f"{label} exceeded maximum JSON recursion depth.") from exc


def clone_strict_json_object(
    payload: object,
    *,
    max_depth: int = MAX_USER_JSON_DEPTH,
    label: str = "payload",
) -> MutableJsonObject:
    """Deep-validate and deep-copy a JSON object (int64, UTF-8, finite float, no Enum, no container aliasing)."""
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be a JSON object Mapping, got {payload!r}")
    try:
        cloned = _walk_strict_json(payload, 0, max_depth, label, clone=True)
    except (TypeError, RecursionError) as exc:
        raise ValueError(f"{label} validation failed: {exc}") from exc
    if not isinstance(cloned, dict):
        raise ValueError(f"{label} must clone to dict.")
    return cloned


def require_non_none(val: Optional[_T], message: str = "Expected non-None invariant") -> _T:
    """Narrow an Optional value at runtime under both standard and -O optimized execution."""
    if val is None:
        raise RuntimeError(message)
    return val


def _reject_duplicate_json_keys(pairs: list[tuple[str, JsonValue]]) -> MutableJsonObject:
    out: MutableJsonObject = {}
    for key, val in pairs:
        if key in out:
            raise ValueError(f"Duplicate JSON object key rejected: {key!r}")
        out[key] = val
    return out


def strict_parse_json_object(raw_text: str) -> MutableJsonObject:
    """Parse a JSON object rejecting non-str input, deep recursion, duplicate keys, NaN/Inf, and surrogates."""
    require_pure_str(raw_text, "raw_text")
    try:
        decoded = json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json_constant,
            parse_float=_parse_finite_json_float,
            parse_int=_parse_bounded_json_int,
        )
    except RecursionError as exc:
        raise ValueError("JSON nesting depth limit exceeded.") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Expected top-level JSON object.")
    validate_wire_json_object(decoded, max_depth=MAX_PARSE_JSON_DEPTH, label="JSON")
    return decoded
