"""Immutable, construction-normalized domain value objects and JSON type aliases for Core 2.0."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
import os
import sys
import threading
from pathlib import Path, PureWindowsPath
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
TREE_ID_ENV_KEY: Final[str] = "_YSCB_TREE_ID"
PYTHON_LAUNCHER_HIJACK_ENV_KEYS: Final[tuple[str, ...]] = (
    "__PYVENV_LAUNCHER__",
    "PYTHONSTARTUP",
    "PYTHONINSPECT",
)
MutableJsonObject: TypeAlias = dict[str, JsonValue]
MAX_USER_JSON_DEPTH: Final[int] = 128
MAX_ENVELOPE_JSON_DEPTH: Final[int] = MAX_USER_JSON_DEPTH + 6
MAX_PARSE_JSON_DEPTH: Final[int] = MAX_ENVELOPE_JSON_DEPTH + 2
_T = TypeVar("_T")


for _json_branch in get_args(JsonValue):
    for _json_arg in get_args(_json_branch):
        if isinstance(_json_arg, ForwardRef):
            object.__setattr__(_json_arg, "__forward_module__", __name__)

_WIN_RESERVED_DEVICE_STEMS: Final[frozenset[str]] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        "clock$",
        "conin$",
        "conout$",
        *(f"com{s}" for s in (*range(1, 10), "\u00b9", "\u00b2", "\u00b3")),
        *(f"lpt{s}" for s in (*range(1, 10), "\u00b9", "\u00b2", "\u00b3")),
    }
)


_WIN_ILLEGAL_SEGMENT_CHARS: Final[frozenset[str]] = frozenset("<>:\"/\\|?*")
_WIN_DEVICE_NS_RE: Final[re.Pattern[str]] = re.compile(r"^[\\/]{2,}[.?](?:[\\/]|$)")


def is_valid_relative_segment(segment: str) -> bool:
    """Return True iff segment is a single non-traversing cross-platform safe path component."""
    if type(segment) is not str or not segment or segment in (".", ".."):
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F or ch in _WIN_ILLEGAL_SEGMENT_CHARS for ch in segment):
        return False
    if segment.endswith((".", " ")):
        return False
    try:
        segment.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    stem = segment.split(".", 1)[0].rstrip(". ").lower()
    return stem not in _WIN_RESERVED_DEVICE_STEMS


def validate_relative_segment(segment: str, *, label: str = "path segment") -> str:
    """Validate and return a single non-traversing cross-platform safe path segment."""
    require_pure_str(segment, label)
    if not is_valid_relative_segment(segment):
        raise ValueError(f"Invalid {label}: {segment!r}")
    return segment

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
        _validate_host_path_segments(raw_str)
        resolved = _resolve_canonical_host_path(raw_str)
        resolved_str = str(resolved)
        _validate_host_path_segments(resolved_str)
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
            if not part or "\x00" in part or ":" in part or cand_p.is_absolute() or bool(cand_p.anchor):
                raise ValueError(f"HostPath.join requires relative non-traversing segments, got {part!r}")
            sub_segs = [s for s in re.split(r"[\\/]+", part) if s]
            if not sub_segs or any(not is_valid_relative_segment(s) for s in sub_segs):
                raise ValueError(f"HostPath.join requires relative non-traversing segments, got {part!r}")
            trailing = os.sep if (idx == len(parts) - 1 and part.endswith(tuple(seps))) else ""
            cleaned.append(os.sep.join(sub_segs) + trailing)
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
        if bool(cand.anchor) or raw_t.startswith(("/", "\\")) or ":" in raw_t:
            raise ValueError(f"Anchor-relative or stream path forbidden in resolve_caller_relative: {target!r}")
        raw_segs = [s for s in re.split(r"[\\/]+", raw_t) if s]
        if not raw_segs:
            raise ValueError(f"resolve_caller_relative requires non-empty relative segments: {target!r}")
        for seg in raw_segs:
            if seg not in (".", ".."):
                validate_relative_segment(seg, label="resolve_caller_relative segment")
        trailing = os.sep if raw_t.endswith(("/", "\\")) else ""
        norm_rel = os.sep.join(raw_segs) + trailing
        seps = "/\\" if IS_WINDOWS else "/"
        base = str(self.path).rstrip(seps) or str(self.path)
        prefix = base if base.endswith(tuple(seps)) else f"{base}{os.sep}"
        return HostPath(f"{prefix}{norm_rel}")

    def __str__(self) -> str:
        return str(self.path)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HostPath):
            return NotImplemented
        return self.comparison_key == other.comparison_key

    def __hash__(self) -> int:
        return hash(self.comparison_key)


def _validate_windows_path_str(path_str: str) -> None:
    if _WIN_DEVICE_NS_RE.match(path_str) is not None:
        raise ValueError(f"Win32 device or verbatim namespace forbidden in HostPath: {path_str!r}")
    if path_str.startswith(("\\\\", "//")):
        unc_parts = [p for p in re.split(r"[\\/]+", path_str.lstrip("\\/")) if p]
        if len(unc_parts) < 2:
            raise ValueError(f"Incomplete Windows UNC path in HostPath: {path_str!r}")
        server, share = unc_parts[0], unc_parts[1]
        if ":" in server or ":" in share or not is_valid_relative_segment(server) or not is_valid_relative_segment(share):
            raise ValueError(f"Invalid UNC server/share component in HostPath: {path_str!r}")
        for seg in unc_parts[2:]:
            if ":" in seg or (seg not in (".", "..") and not is_valid_relative_segment(seg)):
                raise ValueError(f"Invalid cross-platform path segment {seg!r} in HostPath: {path_str!r}")
        return
    pw = PureWindowsPath(path_str)
    drv = pw.drive
    if len(drv) != 2 or not drv[0].isascii() or not drv[0].isalpha() or drv[1] != ":" or not pw.root:
        raise ValueError(f"Invalid Windows drive anchor in HostPath: {path_str!r}")
    tail = path_str[len(pw.anchor) :]
    if ":" in tail:
        raise ValueError(f"Colon / NTFS stream syntax forbidden in HostPath: {path_str!r}")
    for seg in re.split(r"[\\/]+", tail):
        if seg and seg not in (".", "..") and not is_valid_relative_segment(seg):
            raise ValueError(f"Invalid cross-platform path segment {seg!r} in HostPath: {path_str!r}")


def _validate_host_path_segments(path_str: str) -> None:
    if IS_WINDOWS:
        _validate_windows_path_str(path_str)
        return
    p_obj = Path(path_str)
    tail = path_str[len(p_obj.anchor) :] if p_obj.anchor else path_str
    if ":" in tail:
        raise ValueError(f"Colon / NTFS stream syntax forbidden in HostPath: {path_str!r}")
    for seg in re.split(r"/+", tail):
        if seg and seg not in (".", "..") and not is_valid_relative_segment(seg):
            raise ValueError(f"Invalid cross-platform path segment {seg!r} in HostPath: {path_str!r}")


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

    def _parse_float(token: str) -> float:
        val = float(token)
        if not math.isfinite(val):
            raise ValueError(f"Overflowing non-finite JSON float rejected: {token}")
        return val

    def _reject_const(token: str) -> None:
        raise ValueError(f"Non-finite JSON constant rejected: {token}")

    try:
        decoded = json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_const,
            parse_float=_parse_float,
            parse_int=_parse_bounded_json_int,
        )
    except RecursionError as exc:
        raise ValueError("JSON nesting depth limit exceeded.") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Expected top-level JSON object.")
    validate_wire_json_object(decoded, max_depth=MAX_PARSE_JSON_DEPTH, label="JSON")
    return decoded


MAX_SAFE_WAIT_SEC: Final[float] = min(86400.0 * 7.0, float(threading.TIMEOUT_MAX) * 0.5)


def safe_real_to_float(val: object, *, label: str = "value") -> float:
    """Convert exact int/float (excluding bool/Enum/subclasses) to pure float, clamping huge ints within [-1e18, 1e18]."""
    if type(val) not in (int, float):
        raise ValueError(f"{label} must be an exact int or float, got {val!r}")
    if type(val) is int:
        return float(min(10**18, max(-(10**18), val)))
    return val


def validate_min_sec(min_sec: float) -> float:
    """Validate non-negative finite minimum wait bound clamped to MAX_SAFE_WAIT_SEC."""
    f_min = safe_real_to_float(min_sec, label="min_sec")
    if not math.isfinite(f_min) or f_min < 0.0:
        raise ValueError(f"min_sec must be finite and >= 0, got {min_sec!r}")
    return min(MAX_SAFE_WAIT_SEC, f_min)


def clamp_wait_sec(timeout_sec: Optional[float], *, min_sec: float = 0.0) -> Optional[float]:
    """Validate optional wait seconds (rejecting bool and NaN) and clamp within [min_sec, MAX_SAFE_WAIT_SEC]."""
    safe_min = validate_min_sec(min_sec)
    if timeout_sec is None:
        return None
    f_val = safe_real_to_float(timeout_sec, label="timeout_sec")
    if math.isnan(f_val):
        raise ValueError(f"timeout_sec must not be bool or NaN, got {timeout_sec!r}")
    return min(MAX_SAFE_WAIT_SEC, max(safe_min, f_val))
