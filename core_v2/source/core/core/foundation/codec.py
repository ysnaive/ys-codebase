"""Pure-standard-library strict codec and Draft 2020-12 JSON Schema exporter for Core 2.0."""

from __future__ import annotations

import base64
import binascii
import collections.abc as cabc
import dataclasses
from dataclasses import dataclass
from enum import Enum
import functools
import hashlib
import json
import math
import operator
import re
import sys
import threading
import types
import typing
from types import UnionType
from typing import (
    Annotated,
    Callable,
    ClassVar,
    Final,
    ForwardRef,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)
import weakref

from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary
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
    require_pure_str,
)

T = TypeVar("T")
_JSON_SCHEMA_DRAFT_URI: Final[str] = "https://json-schema.org/draft/2020-12/schema"
_CANONICAL_INT_KEY_RE: Final[re.Pattern[str]] = re.compile(r"(?:0|-?[1-9][0-9]*)")
_MAX_CODEC_DEPTH: Final[int] = MAX_USER_JSON_DEPTH
_ENVELOPE_DEPTH_HEADROOM: Final[int] = 8
_STR_PARSE_ONLY_VO_TYPES: Final[frozenset[type[object]]] = frozenset(
    {SemVer4, VersionConstraint, SemanticUri, SpaceId, SpacePath}
)
_STR_INIT_VO_TYPES: Final[frozenset[type[object]]] = frozenset(
    {ModuleId, TaskId, EventId, HostPath, EnvHash}
)
_STR_VO_TYPES: Final[frozenset[type[object]]] = _STR_PARSE_ONLY_VO_TYPES | _STR_INIT_VO_TYPES
_INT_VO_TYPES: Final[frozenset[type[object]]] = frozenset({SnapshotGen})
_SCALAR_VO_TYPES: Final[frozenset[type[object]]] = _STR_VO_TYPES | _INT_VO_TYPES
_SCALAR_MAP_KEY_TYPES: Final[frozenset[type[object]]] = frozenset({bool, int, *_SCALAR_VO_TYPES})
_SUPPORTED_SCALAR_CLASSES: Final[tuple[type[object], ...]] = (
    bool,
    int,
    float,
    str,
    bytes,
    ModuleId,
    TaskId,
    EventId,
    HostPath,
    SemVer4,
    VersionConstraint,
    SemanticUri,
    SpaceId,
    SpacePath,
    SnapshotGen,
    EnvHash,
)
_UNPARAM_SCHEMA_FORMS: Final[tuple[object, ...]] = (
    JsonValue,
    JsonObject,
    MutableJsonObject,
    type(None),
    dict,
    cabc.Mapping,
    Mapping,
    list,
    cabc.Sequence,
    Sequence,
    tuple,
    Tuple,
    frozenset,
)

FieldGetter = tuple[str, Callable[[object], object]]
DcMeta = tuple[tuple[tuple[str, bool], ...], dict[str, object]]


class _UnresolvedLocalHintError(Exception):
    """Raised internally when get_type_hints fails on an unresolved local closure scope."""


class _ActiveCodecMemo(threading.local):
    """Per-thread single-call memo avoiding persistent strong refs on recursive or local types."""

    def __init__(self) -> None:
        self.dc_meta: Optional[dict[type[object], DcMeta]] = None
        self.valid_schemas: Optional[set[object]] = None


class _CodecMetadataCache:
    """Thread-safe weak-key metadata, Enum table, and callable hint cache."""

    _INSTANCE: ClassVar[Optional[_CodecMetadataCache]] = None
    _INIT_LOCK: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def instance(cls) -> _CodecMetadataCache:
        inst = cls._INSTANCE
        if inst is not None:
            return inst
        with cls._INIT_LOCK:
            if cls._INSTANCE is None:
                cls._INSTANCE = cls()
            return cls._INSTANCE

    def __init__(self) -> None:
        self.active = _ActiveCodecMemo()
        self.lock = threading.RLock()
        self.dc_getters: weakref.WeakKeyDictionary[type[object], tuple[FieldGetter, ...]] = weakref.WeakKeyDictionary()
        self.dc_meta: weakref.WeakKeyDictionary[type[object], DcMeta] = weakref.WeakKeyDictionary()
        self.enum_tables: weakref.WeakKeyDictionary[type[Enum], tuple[tuple[JsonValue, str], ...]] = weakref.WeakKeyDictionary()
        self.valid_type_schemas: weakref.WeakSet[type[object]] = weakref.WeakSet()
        self.callable_payloads: weakref.WeakKeyDictionary[object, tuple[bool, Optional[object]]] = weakref.WeakKeyDictionary()


def _is_untyped_wildcard(tp: object) -> bool:
    return tp is object


def _is_forbidden_any_type(tp: object) -> bool:
    return repr(tp) == "typing.Any" or (isinstance(tp, ForwardRef) and tp.__forward_arg__ == "Any")


def _assert_int64_range(val: int, *, path: str) -> int:
    if val < INT64_MIN or val > INT64_MAX:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Integer out of int64 range at {path}")
    return val


def _check_finite_float(val: float, *, path: str) -> float:
    if not math.isfinite(val):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Non-finite float at {path}")
    return val


def _check_str_valid_utf8(s: str, *, path: str) -> str:
    try:
        s.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid UTF-8 surrogate string at {path}: {safe_exception_summary(exc)}") from exc
    return s


def _unwrap_annotated(tp: object) -> object:
    cur = tp
    while get_origin(cur) is Annotated:
        args = get_args(cur)
        if not args:
            break
        cur = args[0]
    return cur


def _is_explicit_empty_tuple_type(tp: object) -> bool:
    unwrapped = _unwrap_annotated(tp)
    if unwrapped is tuple or unwrapped == Tuple:
        return False
    return get_origin(unwrapped) is tuple and get_args(unwrapped) in ((), ((),))


def _first_match(candidates: tuple[object, ...], fn: Callable[[object], T], err_msg: str) -> T:
    for cand in candidates:
        try:
            return fn(cand)
        except YscbError:
            pass
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, err_msg)


def _decode_str_vo_instance(tp: type[object], raw_str: str) -> object:
    if tp is SemVer4:
        return SemVer4.parse(raw_str)
    if tp is VersionConstraint:
        return VersionConstraint.parse(raw_str)
    if tp is SemanticUri:
        return SemanticUri.parse(raw_str)
    if tp is SpaceId:
        return SpaceId.parse(raw_str)
    if tp is SpacePath:
        return SpacePath.parse(raw_str)
    return tp(raw_str)


def _strict_json(
    raw: object, *, as_wire: bool, path: str, depth: int, max_depth: int, active_ids: Optional[set[int]] = None
) -> JsonValue:
    if depth > max_depth:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Maximum nesting depth exceeded at {path}")
    if isinstance(raw, Enum):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unencoded Enum {type(raw).__name__} forbidden at {path}")
    if raw is None or type(raw) is bool:
        return raw
    if type(raw) is str:
        return _check_str_valid_utf8(raw, path=path)
    if type(raw) is int:
        return _assert_int64_range(raw, path=path)
    if type(raw) is float:
        return _check_finite_float(raw, path=path)
    if isinstance(raw, (list, tuple, cabc.Mapping)):
        obj_id = id(raw)
        if active_ids is not None:
            if obj_id in active_ids:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Circular reference detected at {path}")
            active_ids.add(obj_id)
        try:
            if isinstance(raw, (list, tuple)):
                seq = [
                    _strict_json(x, as_wire=as_wire, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth, active_ids=active_ids)
                    for i, x in enumerate(raw)
                ]
                return seq if as_wire else tuple(seq)
            return _strict_json_object(raw, as_wire=as_wire, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids)
        finally:
            if active_ids is not None:
                active_ids.remove(obj_id)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid JSON value of type {type(raw).__name__} at {path}")


def _strict_json_object(
    raw: object, *, as_wire: bool, path: str, depth: int, max_depth: int, active_ids: Optional[set[int]] = None
) -> MutableJsonObject:
    if depth > max_depth:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Maximum nesting depth exceeded at {path}")
    if not isinstance(raw, cabc.Mapping):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected JSON object at {path}")
    out: MutableJsonObject = {}
    for k, v in raw.items():
        if type(k) is not str:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected plain string key at {path}")
        _check_str_valid_utf8(k, path=path)
        out[k] = _strict_json(v, as_wire=as_wire, path=f"{path}.{k}", depth=depth + 1, max_depth=max_depth, active_ids=active_ids)
    return out


def _generic_type_params(cls: type[object]) -> tuple[object, ...]:
    try:
        params = cls.__parameters__
    except AttributeError:
        return ()
    return params if isinstance(params, tuple) else ()


def _rebuild_resolved_generic(orig: object, resolved_args: tuple[object, ...], fallback: object) -> object:
    if orig in (Union, UnionType):
        if len(resolved_args) == 1:
            return resolved_args[0]
        try:
            return functools.reduce(operator.or_, resolved_args)
        except TypeError:
            return Union[resolved_args]
    try:
        return operator.getitem(orig, resolved_args[0] if len(resolved_args) == 1 else resolved_args)
    except TypeError:
        return fallback


def _substitute_typevars(tp: object, tv_map: Mapping[object, object]) -> object:
    tp = _unwrap_annotated(tp)
    if isinstance(tp, TypeVar):
        return tv_map.get(tp, tp)
    if _is_explicit_empty_tuple_type(tp):
        return tuple[()]
    origin, args = get_origin(tp), get_args(tp)
    if origin is None or origin is Literal or not args:
        return tp
    return _rebuild_resolved_generic(origin, tuple(_substitute_typevars(a, tv_map) for a in args), tp)


def _try_mark_seen(seen: set[object], key: object) -> bool:
    try:
        if key in seen:
            return False
        seen.add(key)
        return True
    except TypeError:
        fallback = ("unhashable", id(key))
        if fallback in seen:
            return False
        seen.add(fallback)
        return True


def _is_dataclass_or_generic_dc(tp: object) -> bool:
    tp = _unwrap_annotated(tp)
    if tp in _SCALAR_VO_TYPES:
        return False
    orig = get_origin(tp)
    return (isinstance(tp, type) and dataclasses.is_dataclass(tp)) or (
        isinstance(orig, type) and orig not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(orig)
    )


def _copy_fn_closure_cells(fn_obj: types.FunctionType, out: dict[str, object]) -> None:
    for var_name, cell in zip(fn_obj.__code__.co_freevars, fn_obj.__closure__ or ()):
        try:
            out[var_name] = cell.cell_contents
        except ValueError:
            continue


def _populate_module_and_outer_classes(mod: types.ModuleType, qualname: str, out: dict[str, object]) -> None:
    for k, v in mod.__dict__.items():
        if not k.startswith("__") and k not in out:
            out[k] = v
    cur_ns: Mapping[str, object] = mod.__dict__
    for part in qualname.split(".")[:-1]:
        if part == "<locals>":
            break
        nxt = cur_ns.get(part)
        if not isinstance(nxt, type):
            break
        out.update({ck: cv for ck, cv in nxt.__dict__.items() if not ck.startswith("__")})
        out[part] = nxt
        cur_ns = nxt.__dict__


def _populate_single_mro_base(base: type[object], out: dict[str, object]) -> None:
    raw_params = base.__dict__.get("__parameters__", ())
    for p_var in (raw_params if isinstance(raw_params, tuple) else ()):
        if isinstance(p_var, TypeVar) and p_var.__name__ not in out:
            out[p_var.__name__] = p_var
    raw_bases = base.__dict__.get("__orig_bases__", ())
    for orig_b in (raw_bases if isinstance(raw_bases, tuple) else ()):
        for b_arg in get_args(orig_b):
            if isinstance(b_arg, type) and b_arg.__name__ not in out:
                out[b_arg.__name__] = b_arg
    for member in base.__dict__.values():
        raw_fn = member.__func__ if isinstance(member, (staticmethod, classmethod)) else member
        if isinstance(raw_fn, types.FunctionType):
            _copy_fn_closure_cells(raw_fn, out)


def _populate_qualname_and_closure_ns(mod_name: str, qualname: str, cls_or_fn: object, out: dict[str, object]) -> None:
    mod = sys.modules.get(mod_name)
    if mod is not None:
        _populate_module_and_outer_classes(mod, qualname, out)
    if isinstance(cls_or_fn, type):
        for base in cls_or_fn.__mro__:
            _populate_single_mro_base(base, out)
        out[cls_or_fn.__name__] = cls_or_fn
    elif isinstance(cls_or_fn, types.FunctionType):
        for k, v in cls_or_fn.__globals__.items():
            if not k.startswith("__") and k not in out:
                out[k] = v
        _copy_fn_closure_cells(cls_or_fn, out)


def infer_sequence_element_dataclass(fn: object, *, strict_unresolved: bool) -> tuple[bool, Optional[object]]:
    """Infer TPayload from a mapper callable's first Sequence[TPayload] parameter inside the codec boundary."""
    if not callable(fn):
        return (True, None)
    cache = _CodecMetadataCache.instance()
    with cache.lock:
        try:
            cached = cache.callable_payloads.get(fn)
        except TypeError:
            cached = None
    if cached is not None and cached[0]:
        return cached
    cur_fn: object = fn
    skip_pos, bound_kw = 0, set()
    while isinstance(cur_fn, functools.partial):
        skip_pos += len(cur_fn.args)
        if cur_fn.keywords:
            bound_kw.update(cur_fn.keywords.keys())
        cur_fn = cur_fn.func
    owner_cls: Optional[type[object]] = None
    if isinstance(cur_fn, types.MethodType):
        owner_cls = cur_fn.__self__ if isinstance(cur_fn.__self__, type) else type(cur_fn.__self__)
        target_fn = cur_fn.__func__ if isinstance(cur_fn.__func__, types.FunctionType) else None
        skip_pos += 1
    elif isinstance(cur_fn, types.FunctionType):
        target_fn = cur_fn
    elif isinstance(cur_fn, type):
        owner_cls = cur_fn
        target_fn = cur_fn.__init__ if isinstance(cur_fn.__init__, types.FunctionType) else None
        skip_pos += 1
    else:
        owner_cls = type(cur_fn)
        call_m = owner_cls.__call__
        target_fn = call_m if isinstance(call_m, types.FunctionType) else None
        skip_pos += 1
    if target_fn is None:
        return (True, None)
    code = target_fn.__code__
    candidates = [
        *code.co_varnames[: code.co_argcount][skip_pos:],
        *code.co_varnames[code.co_argcount : code.co_argcount + code.co_kwonlyargcount],
    ]
    param_name = next((p for p in candidates if p not in bound_kw), None)
    if param_name is None:
        return (True, None)
    localns: dict[str, object] = {}
    if owner_cls is not None:
        _populate_qualname_and_closure_ns(owner_cls.__module__, owner_cls.__qualname__, owner_cls, localns)
    _populate_qualname_and_closure_ns(target_fn.__module__, target_fn.__qualname__, target_fn, localns)
    try:
        hints = get_type_hints(target_fn, localns=localns)
    except (NameError, TypeError, AttributeError) as exc:
        if strict_unresolved and param_name in target_fn.__annotations__:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unresolvable mapper hint: {safe_exception_summary(exc)}") from exc
        return (False, None)
    inferred: Optional[object] = None
    if param_name in hints:
        param_tp = _unwrap_annotated(hints[param_name])
        if get_origin(param_tp) in (list, tuple, Sequence, cabc.Sequence):
            args = get_args(param_tp)
            elem_tp = _unwrap_annotated(args[0]) if args else None
            if elem_tp is not None and _is_dataclass_or_generic_dc(elem_tp):
                inferred = elem_tp
    with cache.lock:
        try:
            cache.callable_payloads[fn] = (True, inferred)
        except TypeError:
            pass
    return (True, inferred)


def _type_tree_any(tp: object, pred: cabc.Callable[[object], bool], seen: Optional[set[int]] = None) -> bool:
    walk_seen = seen if seen is not None else set()
    obj_id = id(tp)
    if obj_id in walk_seen:
        return False
    walk_seen.add(obj_id)
    if get_origin(tp) is Annotated:
        if any(pred(m) or _type_tree_any(m, pred, walk_seen) for m in tp.__metadata__):
            return True
        tp = get_args(tp)[0]
    if pred(tp):
        return True
    if isinstance(tp, TypeVar):
        return (tp.__bound__ is not None and _type_tree_any(tp.__bound__, pred, walk_seen)) or any(
            _type_tree_any(c, pred, walk_seen) for c in tp.__constraints__
        )
    origin = get_origin(tp)
    return (origin is not None and pred(origin)) or any(_type_tree_any(a, pred, walk_seen) for a in get_args(tp))


def _obj_in_module_prefix(obj: object, prefix: str, dot_pkg: str) -> bool:
    mod_nm = obj.__module__ if isinstance(obj, (type, types.FunctionType, TypeVar)) else type(obj).__module__
    return isinstance(mod_nm, str) and (mod_nm == prefix or mod_nm.startswith(dot_pkg))


def _node_mentions_module_prefix(node: object, prefix: str, dot_pkg: str) -> bool:
    if isinstance(node, ForwardRef):
        fmod = node.__forward_module__
        return fmod is None or fmod == prefix or fmod.startswith(dot_pkg)
    if isinstance(node, (type, Enum, TypeVar)):
        return _obj_in_module_prefix(node, prefix, dot_pkg)
    return type(node).__module__ not in ("builtins", "typing", "types") and _obj_in_module_prefix(node, prefix, dot_pkg)


def _type_mentions_module_prefix(tp: object, prefix: str) -> bool:
    clean_p = prefix.strip(".")
    return bool(clean_p) and _type_tree_any(tp, lambda node: _node_mentions_module_prefix(node, clean_p, f"{clean_p}."))


def _needs_localns_for_forward_ref(tp: object) -> bool:
    tp = _unwrap_annotated(tp)
    if isinstance(tp, ForwardRef):
        if tp.__forward_arg__ == "JsonValue":
            return False
        mod_name = tp.__forward_module__
        return not (mod_name and mod_name in sys.modules and tp.__forward_arg__ in sys.modules[mod_name].__dict__)
    return any(_needs_localns_for_forward_ref(a) for a in get_args(tp))


def _resolve_forward_ref(ref: ForwardRef, *, localns: Optional[Mapping[str, object]]) -> object:
    if ref.__forward_arg__ == "JsonValue":
        return JsonValue
    if localns is not None and ref.__forward_arg__ in localns:
        return localns[ref.__forward_arg__]
    mod_name = ref.__forward_module__
    if mod_name and mod_name in sys.modules and ref.__forward_arg__ in sys.modules[mod_name].__dict__:
        return sys.modules[mod_name].__dict__[ref.__forward_arg__]
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unresolved ForwardRef {ref.__forward_arg__!r}")


def _unwrap_ref_leaf(tp: object, *, localns: Optional[Mapping[str, object]]) -> object:
    cur = _unwrap_annotated(tp)
    ref_chain: set[str] = set()
    while isinstance(cur, ForwardRef):
        if cur.__forward_arg__ == "JsonValue":
            return JsonValue
        if cur.__forward_arg__ in ref_chain:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Cyclic ForwardRef {cur.__forward_arg__!r}")
        ref_chain.add(cur.__forward_arg__)
        cur = _unwrap_annotated(_resolve_forward_ref(cur, localns=localns))
    return cur


def _resolve_schema_refs(tp: object, localns: Optional[Mapping[str, object]], ref_stack: frozenset[str] = frozenset()) -> object:
    cur = _unwrap_annotated(tp)
    while isinstance(cur, ForwardRef):
        if cur.__forward_arg__ == "JsonValue":
            return JsonValue
        if cur.__forward_arg__ in ref_stack:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Cyclic ForwardRef {cur.__forward_arg__!r}")
        ref_stack = ref_stack | {cur.__forward_arg__}
        cur = _unwrap_annotated(_resolve_forward_ref(cur, localns=localns))
    if _is_forbidden_any_type(cur):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "typing.Any is forbidden in DataclassCodec schema")
    orig, args = get_origin(cur), get_args(cur)
    if (
        orig is None
        or orig in (Literal, ClassVar)
        or not args
        or not _type_tree_any(cur, lambda n: isinstance(n, ForwardRef) and n.__forward_arg__ != "JsonValue")
    ):
        return cur
    resolved_args = tuple(Ellipsis if a is Ellipsis else _resolve_schema_refs(a, localns, ref_stack) for a in args)
    return _rebuild_resolved_generic(orig, resolved_args, cur)


def _resolve_node_dataclass(node: object, localns: Optional[Mapping[str, object]] = None) -> Optional[type[object]]:
    if isinstance(node, ForwardRef):
        if node.__forward_arg__ == "JsonValue":
            return None
        try:
            return _resolve_node_dataclass(_resolve_forward_ref(node, localns=localns), localns)
        except YscbError:
            return None
    node = _unwrap_annotated(node)
    if node in _SCALAR_VO_TYPES:
        return None
    orig = get_origin(node)
    if isinstance(orig, type) and orig not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(orig):
        return orig
    return node if isinstance(node, type) and dataclasses.is_dataclass(node) else None


def _is_uncacheable_local_node(node: object) -> bool:
    if isinstance(node, ForwardRef):
        return node.__forward_arg__ != "JsonValue"
    return ".<locals>." in (node.__qualname__ if isinstance(node, type) else type(node).__qualname__)


def _resolve_single_class_hints(
    dc_cls: type[object], init_names: set[str], parent_localns: Optional[Mapping[str, object]]
) -> dict[str, object]:
    out: dict[str, object] = {}
    for cls in reversed(dc_cls.__mro__):
        own_anns = cls.__dict__.get("__annotations__")
        if cls is object or not isinstance(own_anns, Mapping) or not own_anns:
            continue
        field_anns = {k: v for k, v in own_anns.items() if k in init_names}
        if not field_anns:
            continue
        own_lns: dict[str, object] = dict(parent_localns) if parent_localns is not None else {}
        _populate_qualname_and_closure_ns(cls.__module__, cls.__qualname__, cls, own_lns)
        probe = type(cls.__name__, (), {"__annotations__": field_anns, "__module__": cls.__module__})
        mod = sys.modules.get(cls.__module__)
        globalns = mod.__dict__ if mod is not None else own_lns
        try:
            out.update(get_type_hints(probe, globalns=globalns, localns=own_lns, include_extras=True))
        except (NameError, TypeError, AttributeError) as exc:
            raise _UnresolvedLocalHintError(f"Unresolvable type hint on {cls.__name__}: {safe_exception_summary(exc)}") from exc
    return out


def resolve_dataclass_init_hints(dc_cls: type[object]) -> dict[str, object]:
    """Resolve init-field type annotations (preserving Annotated extras) across MRO, outer classes, and closures."""
    if not isinstance(dc_cls, type) or not dataclasses.is_dataclass(dc_cls):
        raise ValueError(f"Expected @dataclass type, got {dc_cls!r}")
    init_names = {f.name for f in dataclasses.fields(dc_cls) if f.init}
    try:
        return _resolve_single_class_hints(dc_cls, init_names, None)
    except _UnresolvedLocalHintError as exc:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, str(exc)) from exc


def _is_dc_cyclic(dc_cls: type[object], hints: Mapping[str, object], localns: Optional[Mapping[str, object]]) -> bool:
    seen, stack = set(), list(hints.values())
    while stack:
        cur = _unwrap_annotated(stack.pop())
        stack.extend(a for a in get_args(cur) if a not in (Ellipsis, type(None)))
        sub = _resolve_node_dataclass(cur, localns)
        if sub is None:
            continue
        if sub is dc_cls:
            return True
        if sub not in seen:
            seen.add(sub)
            try:
                sub_hints = _resolve_single_class_hints(sub, {f.name for f in dataclasses.fields(sub) if f.init}, localns)
            except _UnresolvedLocalHintError:
                return True
            stack.extend(sub_hints.values())
    return False


def _get_dc_meta(dc_cls: type[object], localns: Optional[Mapping[str, object]]) -> DcMeta:
    cache = _CodecMetadataCache.instance()
    act_meta = cache.active.dc_meta if localns is None else None
    if act_meta is not None and dc_cls in act_meta:
        return act_meta[dc_cls]
    if localns is None and ".<locals>." not in dc_cls.__qualname__:
        with cache.lock:
            cached = cache.dc_meta.get(dc_cls)
            if cached is not None:
                if act_meta is not None:
                    act_meta[dc_cls] = cached
                return cached
    init_specs = tuple((f.name, f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING) for f in dataclasses.fields(dc_cls) if f.init)
    hints = _resolve_single_class_hints(dc_cls, {fn for fn, _req in init_specs}, localns)
    meta: DcMeta = (init_specs, hints)
    if act_meta is not None:
        act_meta[dc_cls] = meta
    cacheable = (
        localns is None
        and ".<locals>." not in dc_cls.__qualname__
        and not any(_needs_localns_for_forward_ref(ft) or _type_tree_any(ft, _is_uncacheable_local_node) for ft in hints.values())
        and not _is_dc_cyclic(dc_cls, hints, None)
    )
    if cacheable:
        with cache.lock:
            cache.dc_meta[dc_cls] = meta
    return meta


def _type_satisfies_bound(arg: object, bound: object) -> bool:
    arg_u, bound_u = _unwrap_annotated(arg), _unwrap_annotated(bound)
    if _is_untyped_wildcard(bound_u):
        return True
    if isinstance(arg_u, TypeVar):
        if arg_u.__bound__ is not None:
            return _type_satisfies_bound(arg_u.__bound__, bound_u)
        return bool(arg_u.__constraints__) and all(_type_satisfies_bound(c, bound_u) for c in arg_u.__constraints__)
    if get_origin(bound_u) in (Union, UnionType):
        return any(_type_satisfies_bound(arg_u, b) for b in get_args(bound_u))
    if get_origin(arg_u) in (Union, UnionType):
        return all(_type_satisfies_bound(a, bound_u) for a in get_args(arg_u))
    if arg_u == bound_u:
        return True
    arg_cls = get_origin(arg_u) if get_origin(arg_u) is not None else arg_u
    return isinstance(arg_cls, type) and isinstance(bound_u, type) and issubclass(arg_cls, bound_u)


def _validate_enum_wire_val(val: object, enum_cls: type[Enum], member_name: str) -> JsonValue:
    path = f"{enum_cls.__name__}.{member_name}"
    if val is None or type(val) is bool:
        return val
    if type(val) is int:
        return _assert_int64_range(val, path=path)
    if type(val) is float:
        return _check_finite_float(val, path=path)
    if type(val) is str:
        return _check_str_valid_utf8(val, path=path)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported Enum value type {type(val).__name__} on {path}")


def _get_enum_table(tp: type[Enum]) -> tuple[tuple[JsonValue, str], ...]:
    cache = _CodecMetadataCache.instance()
    local_enum = ".<locals>." in tp.__qualname__
    if not local_enum:
        with cache.lock:
            cached = cache.enum_tables.get(tp)
            if cached is not None:
                return cached
    table = tuple((_validate_enum_wire_val(m.value, tp, m.name), m.name) for m in tp)
    if not local_enum:
        with cache.lock:
            cache.enum_tables[tp] = table
    return table


def _canonical_map_key_str(val: object, *, path: str) -> str:
    if type(val) is bool:
        return "true" if val else "false"
    if type(val) is int:
        return str(_assert_int64_range(val, path=path))
    if type(val) is SnapshotGen and isinstance(val, SnapshotGen):
        return str(_assert_int64_range(val.value, path=path))
    if type(val) is str or type(val) in _STR_VO_TYPES:
        return _check_str_valid_utf8(str(val), path=path)
    if isinstance(val, Enum):
        _get_enum_table(type(val))
        mv = val.value
        if type(mv) is str:
            return mv
        if type(mv) is int:
            return str(mv)
        if type(mv) is bool:
            return "true" if mv else "false"
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported map key {type(val).__name__} at {path}")


def _validate_literal_schema_args(args: tuple[object, ...]) -> None:
    if not args:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Empty Literal[...] is forbidden")
    for arg in args:
        if isinstance(arg, Enum):
            _get_enum_table(type(arg))
        elif type(arg) is int:
            _assert_int64_range(arg, path="Literal")
        elif type(arg) is str:
            _check_str_valid_utf8(arg, path="Literal")
        elif arg is not None and type(arg) not in (bool, bytes):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported Literal argument {arg!r}")


def _validate_map_key_schema(key_tp: object, *, localns: Optional[Mapping[str, object]]) -> None:
    k = _resolve_schema_refs(key_tp, localns)
    if isinstance(k, TypeVar):
        branches = k.__constraints__ or ((k.__bound__,) if k.__bound__ is not None else ())
        if not branches:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unbounded TypeVar {k.__name__} forbidden as map key")
        for b in branches:
            _validate_map_key_schema(b, localns=localns)
        return
    origin, args = get_origin(k), get_args(k)
    if origin in (Union, UnionType):
        for branch in args:
            _validate_map_key_schema(branch, localns=localns)
        return
    if origin is Literal:
        if not args:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Empty Literal[...] map key is forbidden")
        for arg in args:
            if not (type(arg) in (bool, int, str) or isinstance(arg, Enum)):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported Literal map key {arg!r}")
            _canonical_map_key_str(arg, path="LiteralMapKey")
        return
    if k is str or k in _SCALAR_MAP_KEY_TYPES:
        return
    if isinstance(k, type) and issubclass(k, Enum):
        seen_strs: set[str] = set()
        for wv, m_name in _get_enum_table(k):
            if type(wv) not in (bool, int, str):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Enum {k.__name__}.{m_name} invalid as map key")
            s_key = _canonical_map_key_str(k[m_name], path=f"{k.__name__}.{m_name}")
            if s_key in seen_strs:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Colliding Enum map key string {s_key!r} on {k.__name__}")
            seen_strs.add(s_key)
        return
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported map key type {k!r}")


def _validate_generic_dc_type_args(
    orig: type[object], args: tuple[object, ...], *, localns: Optional[Mapping[str, object]], seen: set[object]
) -> None:
    params = _generic_type_params(orig)
    if not params or len(args) != len(params):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Generic dataclass {orig.__name__} arity mismatch")
    for param, arg in zip(params, args):
        _validate_schema(arg, localns=localns, seen=seen)
        if isinstance(param, TypeVar):
            if param.__constraints__ and not any(_type_satisfies_bound(arg, c) for c in param.__constraints__):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"TypeVar {param.__name__} constraint violation")
            if param.__bound__ is not None and not _type_satisfies_bound(arg, param.__bound__):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"TypeVar {param.__name__} bound violation")


def _validate_dc_fields_schema(
    dc_cls: type[object], tv_map: Mapping[object, object], *, localns: Optional[Mapping[str, object]], seen: set[object]
) -> None:
    init_specs, hints = _get_dc_meta(dc_cls, localns)
    for field_name, _req in init_specs:
        if field_name not in hints:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Missing type hint for {dc_cls.__name__}.{field_name}")
        _validate_schema(_substitute_typevars(hints[field_name], tv_map) if tv_map else hints[field_name], localns=localns, seen=seen)


def _validate_schema(tp: object, *, localns: Optional[Mapping[str, object]], seen: set[object]) -> None:
    if _is_forbidden_any_type(tp) or get_origin(tp) is ClassVar:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Forbidden Any or ClassVar in DataclassCodec schema")
    cur = _unwrap_ref_leaf(tp, localns=localns)
    if _is_forbidden_any_type(cur) or get_origin(cur) is ClassVar:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Forbidden Any or ClassVar in DataclassCodec schema")
    if cur in _UNPARAM_SCHEMA_FORMS or _is_untyped_wildcard(cur) or _is_explicit_empty_tuple_type(cur):
        return
    if isinstance(cur, TypeVar):
        if not _try_mark_seen(seen, cur):
            return
        if cur.__bound__ is not None:
            _validate_schema(cur.__bound__, localns=localns, seen=seen)
        for constraint in cur.__constraints__:
            _validate_schema(constraint, localns=localns, seen=seen)
        return
    cache = _CodecMetadataCache.instance()
    if localns is None and isinstance(cur, type) and cur in cache.valid_type_schemas:
        return
    if not _try_mark_seen(seen, cur):
        return
    origin, args = get_origin(cur), get_args(cur)
    if origin is Literal:
        _validate_literal_schema_args(args)
    elif origin in (Union, UnionType):
        for branch in args:
            _validate_schema(branch, localns=localns, seen=seen)
    elif origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            if args[0] is Ellipsis:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Invalid tuple[..., ...] schema")
            _validate_schema(args[0], localns=localns, seen=seen)
        else:
            if Ellipsis in args:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Misplaced Ellipsis in tuple schema {cur!r}")
            for item_tp in args:
                _validate_schema(item_tp, localns=localns, seen=seen)
    elif origin in (list, Sequence, cabc.Sequence, frozenset):
        if len(args) != 1:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected 1 type arg for {cur!r}")
        _validate_schema(args[0], localns=localns, seen=seen)
    elif origin in (dict, Mapping, cabc.Mapping):
        if len(args) != 2:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected 2 type args for {cur!r}")
        _validate_map_key_schema(args[0], localns=localns)
        _validate_schema(args[1], localns=localns, seen=seen)
    elif isinstance(origin, type) and origin not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(origin):
        _validate_generic_dc_type_args(origin, args, localns=localns, seen=seen)
        _validate_dc_fields_schema(origin, dict(zip(_generic_type_params(origin), args)), localns=localns, seen=seen)
    elif origin is not None:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported generic schema type {cur!r}")
    elif cur in _SUPPORTED_SCALAR_CLASSES:
        return
    elif isinstance(cur, type) and issubclass(cur, Enum):
        _get_enum_table(cur)
    elif isinstance(cur, type) and dataclasses.is_dataclass(cur):
        _validate_dc_fields_schema(cur, {}, localns=localns, seen=seen)
    else:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported schema type {cur!r}")


def _ensure_schema_valid_once(tp: object, *, localns: Optional[Mapping[str, object]]) -> None:
    cache = _CodecMetadataCache.instance()
    act_valid = cache.active.valid_schemas if localns is None else None
    if act_valid is not None:
        try:
            if tp in act_valid:
                return
        except TypeError:
            pass
    cacheable = localns is None and isinstance(tp, type) and ".<locals>." not in tp.__qualname__
    if cacheable:
        with cache.lock:
            if tp in cache.valid_type_schemas:
                if act_valid is not None:
                    act_valid.add(tp)
                return
    try:
        _validate_schema(tp, localns=localns, seen=set())
    except _UnresolvedLocalHintError as exc:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, str(exc)) from exc
    if act_valid is not None:
        try:
            act_valid.add(tp)
        except TypeError:
            pass
    if cacheable and not _type_tree_any(tp, _is_uncacheable_local_node):
        with cache.lock:
            cache.valid_type_schemas.add(tp)


def _decode_enum(tp: type[Enum], raw: object, *, path: str) -> Enum:
    table = _get_enum_table(tp)
    if raw is None or type(raw) in (bool, int, float, str):
        for wire_val, member_name in table:
            if type(raw) is type(wire_val) and raw == wire_val:
                return tp[member_name]
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid {tp.__name__} value {raw!r} at {path}")


def _decode_bytes(raw: object, *, path: str) -> bytes:
    if type(raw) is not str:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected base64 str for bytes at {path}")
    try:
        decoded = base64.b64decode(raw.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid base64 bytes at {path}: {safe_exception_summary(exc)}") from exc
    if base64.b64encode(decoded).decode("ascii") != raw:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Non-canonical base64 bytes at {path}")
    return decoded


def _decode_literal(tp: object, raw: object, *, path: str) -> object:
    for arg in get_args(tp):
        if isinstance(arg, Enum):
            if type(raw) is type(arg.value) and raw == arg.value:
                return arg
        elif type(arg) is bytes:
            if type(raw) is str:
                try:
                    if _decode_bytes(raw, path=path) == arg:
                        return arg
                except YscbError:
                    pass
        elif type(raw) is type(arg) and raw == arg:
            if type(arg) is int:
                _assert_int64_range(raw, path=path)
            elif type(arg) is str:
                _check_str_valid_utf8(raw, path=path)
            return arg
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Value {raw!r} does not match {tp!r} at {path}")


def _decode_map_key(key_tp: object, raw_key: object, *, path: str, localns: Optional[Mapping[str, object]]) -> object:
    if type(raw_key) is not str:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected string JSON map key at {path}")
    _check_str_valid_utf8(raw_key, path=path)
    k = _resolve_schema_refs(key_tp, localns)
    if isinstance(k, TypeVar):
        branches = k.__constraints__ or ((k.__bound__,) if k.__bound__ is not None else ())
        if not branches:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unresolved TypeVar map key {k.__name__} at {path}")
        return _first_match(branches, lambda b: _decode_map_key(b, raw_key, path=path, localns=localns), f"Map key failed TypeVar {k.__name__} at {path}")
    origin, args = get_origin(k), get_args(k)
    if origin in (Union, UnionType):
        return _first_match(args, lambda b: _decode_map_key(b, raw_key, path=path, localns=localns), f"Map key {raw_key!r} failed union {k!r} at {path}")
    if origin is Literal:
        for arg in args:
            if _canonical_map_key_str(arg, path=path) == raw_key:
                return arg
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Map key {raw_key!r} does not match {k!r} at {path}")
    if k is str:
        return raw_key
    if k is bool:
        if raw_key in ("true", "false"):
            return raw_key == "true"
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid bool map key {raw_key!r} at {path}")
    if k is int:
        if _CANONICAL_INT_KEY_RE.fullmatch(raw_key) is None:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Non-canonical int map key {raw_key!r} at {path}")
        return _assert_int64_range(int(raw_key), path=path)
    if k is SnapshotGen:
        if _CANONICAL_INT_KEY_RE.fullmatch(raw_key) is None:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Non-canonical SnapshotGen map key {raw_key!r} at {path}")
        try:
            return SnapshotGen(_assert_int64_range(int(raw_key), path=path))
        except ValueError as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid SnapshotGen map key at {path}: {safe_exception_summary(exc)}") from exc
    if isinstance(k, type) and k in _STR_VO_TYPES:
        try:
            return _decode_str_vo_instance(k, raw_key)
        except (YscbError, ValueError, TypeError) as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid {k.__name__} map key at {path}: {safe_exception_summary(exc)}") from exc
    if isinstance(k, type) and issubclass(k, Enum):
        for _wv, m_name in _get_enum_table(k):
            member = k[m_name]
            if _canonical_map_key_str(member, path=path) == raw_key:
                return member
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid {k.__name__} map key {raw_key!r} at {path}")
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported map key schema {k!r} at {path}")


def _decode_scalar(tp: type[object], raw: object, *, path: str) -> object:
    if issubclass(tp, Enum):
        return _decode_enum(tp, raw, path=path)
    if tp is bool:
        if type(raw) is not bool:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected bool at {path}, got {type(raw).__name__}")
        return raw
    if tp is int:
        if type(raw) is not int:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected int at {path}, got {type(raw).__name__}")
        return _assert_int64_range(raw, path=path)
    if tp is SnapshotGen:
        if type(raw) is not int:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected int for SnapshotGen at {path}, got {type(raw).__name__}")
        try:
            return SnapshotGen(_assert_int64_range(raw, path=path))
        except ValueError as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid SnapshotGen at {path}: {safe_exception_summary(exc)}") from exc
    if tp is float:
        if type(raw) is float:
            return _check_finite_float(raw, path=path)
        if type(raw) is int:
            _assert_int64_range(raw, path=path)
            return _check_finite_float(float(raw), path=path)
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected float at {path}, got {type(raw).__name__}")
    if tp is str:
        if type(raw) is not str:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected str at {path}, got {type(raw).__name__}")
        return _check_str_valid_utf8(raw, path=path)
    if tp is bytes:
        return _decode_bytes(raw, path=path)
    if type(raw) is not str:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected str for {tp.__name__} at {path}")
    _check_str_valid_utf8(raw, path=path)
    try:
        return _decode_str_vo_instance(tp, raw)
    except (YscbError, ValueError, TypeError) as exc:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid {tp.__name__} at {path}: {safe_exception_summary(exc)}") from exc


def _ensure_json_seq(raw: object, *, path: str) -> cabc.Sequence[object]:
    if not isinstance(raw, (list, tuple)):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected sequence at {path}, got {type(raw).__name__}")
    return raw


def _decode_container(
    origin: object, args: tuple[object, ...], raw: object, *, path: str, depth: int, max_depth: int, localns: Optional[Mapping[str, object]]
) -> object:
    if origin is tuple:
        seq = _ensure_json_seq(raw, path=path)
        if not args or args == ((),):
            if seq:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected empty tuple at {path}")
            return ()
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode_value(args[0], item, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth, localns=localns) for i, item in enumerate(seq))
        if len(seq) != len(args):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected tuple length {len(args)} at {path}, got {len(seq)}")
        return tuple(_decode_value(t_i, v_i, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth, localns=localns) for i, (t_i, v_i) in enumerate(zip(args, seq)))
    if origin in (list, Sequence, cabc.Sequence):
        seq = _ensure_json_seq(raw, path=path)
        decoded = [_decode_value(args[0], item, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth, localns=localns) for i, item in enumerate(seq)]
        return decoded if origin is list else tuple(decoded)
    if origin is frozenset:
        seq = _ensure_json_seq(raw, path=path)
        try:
            return frozenset(_decode_value(args[0], item, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth, localns=localns) for i, item in enumerate(seq))
        except TypeError as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unhashable frozenset element at {path}: {safe_exception_summary(exc)}") from exc
    if not isinstance(raw, cabc.Mapping):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected mapping at {path}, got {type(raw).__name__}")
    out: dict[object, object] = {}
    for rk, rv in raw.items():
        dk = _decode_map_key(args[0], rk, path=f"{path}[{rk!r}]", localns=localns)
        if dk in out:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Duplicate decoded map key at {path}")
        out[dk] = _decode_value(args[1], rv, path=f"{path}.{rk}", depth=depth + 1, max_depth=max_depth, localns=localns)
    return out if origin is dict else types.MappingProxyType(out)


def _decode_dataclass(
    dc_cls: type[object],
    tv_map: Mapping[object, object],
    raw: object,
    *,
    path: str,
    depth: int,
    max_depth: int,
    localns: Optional[Mapping[str, object]],
) -> object:
    if not isinstance(raw, cabc.Mapping):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected mapping for {dc_cls.__name__} at {path}")
    init_specs, hints = _get_dc_meta(dc_cls, localns)
    known = {fn for fn, _req in init_specs}
    for raw_k in raw:
        if type(raw_k) is not str:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected string field key on {dc_cls.__name__} at {path}")
        _check_str_valid_utf8(raw_k, path=path)
        if raw_k not in known:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unexpected field {raw_k!r} for {dc_cls.__name__} at {path}")
    init_kwargs: dict[str, object] = {}
    for field_name, is_required in init_specs:
        if field_name in raw:
            ft = _substitute_typevars(hints[field_name], tv_map) if tv_map else hints[field_name]
            init_kwargs[field_name] = _decode_value(ft, raw[field_name], path=f"{path}.{field_name}", depth=depth + 1, max_depth=max_depth, localns=localns)
        elif is_required:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Missing required field {dc_cls.__name__}.{field_name} at {path}")
    try:
        return dc_cls(**init_kwargs)
    except YscbError:
        raise
    except (TypeError, ValueError) as exc:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Dataclass init failed for {dc_cls.__name__}: {safe_exception_summary(exc)}") from exc


def _decode_value(
    tp: object, raw: object, *, path: str, depth: int, max_depth: int, localns: Optional[Mapping[str, object]]
) -> object:
    if depth > max_depth:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Maximum nesting depth exceeded at {path}")
    cur = _unwrap_ref_leaf(tp, localns=localns)
    if cur == JsonValue or _is_untyped_wildcard(cur):
        return _strict_json(raw, as_wire=False, path=path, depth=depth, max_depth=max_depth)
    if cur is type(None):
        if raw is not None:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected None at {path}")
        return None
    if cur == JsonObject or cur in (cabc.Mapping, Mapping):
        return types.MappingProxyType(_strict_json_object(raw, as_wire=False, path=path, depth=depth, max_depth=max_depth))
    if cur == MutableJsonObject or cur is dict:
        return _strict_json_object(raw, as_wire=False, path=path, depth=depth, max_depth=max_depth)
    if cur is list:
        return [_strict_json(x, as_wire=False, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth) for i, x in enumerate(_ensure_json_seq(raw, path=path))]
    if cur in (cabc.Sequence, Sequence, tuple, Tuple):
        return tuple(_strict_json(x, as_wire=False, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth) for i, x in enumerate(_ensure_json_seq(raw, path=path)))
    if cur is frozenset:
        try:
            return frozenset(_strict_json(x, as_wire=False, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth) for i, x in enumerate(_ensure_json_seq(raw, path=path)))
        except TypeError as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unhashable frozenset element at {path}: {safe_exception_summary(exc)}") from exc
    if isinstance(cur, TypeVar):
        if cur.__constraints__:
            return _first_match(cur.__constraints__, lambda b: _decode_value(b, raw, path=path, depth=depth, max_depth=max_depth, localns=localns), f"Value failed TypeVar {cur.__name__} at {path}")
        if cur.__bound__ is not None:
            return _decode_value(cur.__bound__, raw, path=path, depth=depth, max_depth=max_depth, localns=localns)
        return _strict_json(raw, as_wire=False, path=path, depth=depth, max_depth=max_depth)
    origin, args = get_origin(cur), get_args(cur)
    if origin is Literal:
        return _decode_literal(cur, raw, path=path)
    if origin in (Union, UnionType):
        return _first_match(args, lambda b: _decode_value(b, raw, path=path, depth=depth, max_depth=max_depth, localns=localns), f"Value failed union {cur!r} at {path}")
    if origin in (tuple, list, Sequence, cabc.Sequence, frozenset, dict, Mapping, cabc.Mapping):
        return _decode_container(origin, args, raw, path=path, depth=depth, max_depth=max_depth, localns=localns)
    if isinstance(origin, type) and origin not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(origin):
        return _decode_dataclass(origin, dict(zip(_generic_type_params(origin), args)), raw, path=path, depth=depth, max_depth=max_depth, localns=localns)
    if isinstance(cur, type) and (cur in _SUPPORTED_SCALAR_CLASSES or issubclass(cur, Enum)):
        return _decode_scalar(cur, raw, path=path)
    if isinstance(cur, type) and dataclasses.is_dataclass(cur):
        return _decode_dataclass(cur, {}, raw, path=path, depth=depth, max_depth=max_depth, localns=localns)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported target type {cur!r} at {path}")


def _decode_by_type(tp: object, raw: object, *, max_depth: int, localns: Optional[Mapping[str, object]]) -> object:
    cache = _CodecMetadataCache.instance()
    act = cache.active
    owns_act = act.dc_meta is None
    if owns_act:
        act.dc_meta, act.valid_schemas = {}, set()
    try:
        _ensure_schema_valid_once(tp, localns=localns)
        return _decode_value(tp, raw, path="$", depth=0, max_depth=max_depth, localns=localns)
    except _UnresolvedLocalHintError as exc:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, str(exc)) from exc
    finally:
        if owns_act:
            act.dc_meta, act.valid_schemas = None, None


def _get_dataclass_field_getters(dc_cls: type[object]) -> tuple[FieldGetter, ...]:
    cache = _CodecMetadataCache.instance()
    local_dc = ".<locals>." in dc_cls.__qualname__
    if not local_dc:
        with cache.lock:
            cached = cache.dc_getters.get(dc_cls)
            if cached is not None:
                return cached
    getters = tuple((f.name, operator.attrgetter(f.name)) for f in dataclasses.fields(dc_cls) if f.init)
    if not local_dc:
        with cache.lock:
            cache.dc_getters[dc_cls] = getters
    return getters


def _sort_encoded_frozenset(items: list[JsonValue]) -> list[JsonValue]:
    if len(items) <= 1:
        return items
    return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))


def _encode_untyped_value(val: object, *, path: str, depth: int, max_depth: int, active_ids: set[int]) -> JsonValue:
    if depth > max_depth:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Maximum nesting depth exceeded at {path}")
    if val is None or type(val) is bool:
        return val
    if type(val) is int:
        return _assert_int64_range(val, path=path)
    if type(val) is float:
        return _check_finite_float(val, path=path)
    if type(val) is str:
        return _check_str_valid_utf8(val, path=path)
    if type(val) is bytes:
        return base64.b64encode(val).decode("ascii")
    if isinstance(val, Enum):
        _get_enum_table(type(val))
        return val.value
    if type(val) is SnapshotGen and isinstance(val, SnapshotGen):
        return _assert_int64_range(val.value, path=path)
    if type(val) in _STR_VO_TYPES:
        return _check_str_valid_utf8(str(val), path=path)
    if isinstance(val, (type, set)):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported value type {type(val).__name__} at {path}")
    if dataclasses.is_dataclass(val):
        return _encode_dataclass_checked(type(val), {}, val, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids)
    obj_id = id(val)
    if obj_id in active_ids:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Circular reference detected at {path}")
    if isinstance(val, (list, tuple, frozenset, cabc.Mapping)):
        active_ids.add(obj_id)
        try:
            if isinstance(val, (list, tuple)):
                return [_encode_untyped_value(x, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth, active_ids=active_ids) for i, x in enumerate(val)]
            if isinstance(val, frozenset):
                return _sort_encoded_frozenset([_encode_untyped_value(x, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth, active_ids=active_ids) for i, x in enumerate(val)])
            out: MutableJsonObject = {}
            for k, v in val.items():
                if type(k) is not str:
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected str map key at {path}")
                _check_str_valid_utf8(k, path=path)
                out[k] = _encode_untyped_value(v, path=f"{path}.{k}", depth=depth + 1, max_depth=max_depth, active_ids=active_ids)
            return out
        finally:
            active_ids.remove(obj_id)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported value type {type(val).__name__} at {path}")


def _encode_map_key(key_tp: object, val: object, *, path: str) -> str:
    k = _resolve_schema_refs(key_tp, None)
    if isinstance(k, TypeVar):
        branches = k.__constraints__ or ((k.__bound__,) if k.__bound__ is not None else ())
        if not branches:
            return _canonical_map_key_str(val, path=path)
        return _first_match(branches, lambda b: _encode_map_key(b, val, path=path), f"Map key {val!r} failed TypeVar {k.__name__} at {path}")
    origin, args = get_origin(k), get_args(k)
    if origin in (Union, UnionType):
        return _first_match(args, lambda b: _encode_map_key(b, val, path=path), f"Map key {val!r} failed union {k!r} at {path}")
    if origin is Literal:
        for arg in args:
            if type(val) is type(arg) and val == arg:
                return _canonical_map_key_str(arg, path=path)
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Map key {val!r} does not match {k!r} at {path}")
    if k is str:
        if type(val) is not str:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected str map key at {path}")
        return _check_str_valid_utf8(val, path=path)
    if k is bool:
        if type(val) is not bool:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected bool map key at {path}")
        return "true" if val else "false"
    if k is int:
        if type(val) is not int:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected int map key at {path}")
        return str(_assert_int64_range(val, path=path))
    if isinstance(k, type) and (k in _SCALAR_VO_TYPES or issubclass(k, Enum)):
        if type(val) is not k:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected {k.__name__} map key at {path}")
        return _canonical_map_key_str(val, path=path)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported map key schema {k!r} at {path}")


def _encode_scalar_typed(tp: type[object], val: object, *, path: str) -> JsonValue:
    if issubclass(tp, Enum):
        if type(val) is not tp:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected {tp.__name__} at {path}")
        _get_enum_table(tp)
        return val.value
    if type(val) is not tp:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected {tp.__name__} at {path}")
    if tp is int:
        return _assert_int64_range(val, path=path)
    if tp is SnapshotGen and isinstance(val, SnapshotGen):
        return _assert_int64_range(val.value, path=path)
    if tp is float:
        return _check_finite_float(val, path=path)
    if tp is bytes:
        return base64.b64encode(val).decode("ascii")
    if tp is str:
        return _check_str_valid_utf8(val, path=path)
    if tp is bool:
        return val
    return _check_str_valid_utf8(str(val), path=path)


def _encode_literal_typed(tp: object, val: object, *, path: str) -> JsonValue:
    for arg in get_args(tp):
        if type(val) is type(arg) and val == arg:
            if isinstance(val, Enum):
                _get_enum_table(type(val))
                return val.value
            if type(val) is bytes:
                return base64.b64encode(val).decode("ascii")
            if type(val) is int:
                return _assert_int64_range(val, path=path)
            if type(val) is str:
                return _check_str_valid_utf8(val, path=path)
            return val
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Value {val!r} does not match {tp!r} at {path}")


def _encode_container_typed(
    origin: object, args: tuple[object, ...], val: object, *, path: str, depth: int, max_depth: int, active_ids: set[int]
) -> JsonValue:
    obj_id = id(val)
    if obj_id in active_ids:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Circular reference detected at {path}")
    active_ids.add(obj_id)
    try:
        if origin is tuple:
            if not isinstance(val, tuple):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected tuple at {path}, got {type(val).__name__}")
            if not args or args == ((),):
                if val:
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected empty tuple at {path}")
                return []
            if len(args) == 2 and args[1] is Ellipsis:
                return [_encode_declared_value(args[0], item, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth, active_ids=active_ids) for i, item in enumerate(val)]
            if len(val) != len(args):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected tuple length {len(args)} at {path}, got {len(val)}")
            return [_encode_declared_value(t_i, v_i, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth, active_ids=active_ids) for i, (t_i, v_i) in enumerate(zip(args, val))]
        if origin in (list, Sequence, cabc.Sequence):
            if (origin is list and type(val) is not list) or (origin is not list and not isinstance(val, (list, tuple))):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected sequence at {path}, got {type(val).__name__}")
            return [_encode_declared_value(args[0], item, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth, active_ids=active_ids) for i, item in enumerate(val)]
        if origin is frozenset:
            if not isinstance(val, frozenset):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected frozenset at {path}, got {type(val).__name__}")
            return _sort_encoded_frozenset([_encode_declared_value(args[0], item, path=f"{path}[{i}]", depth=depth + 1, max_depth=max_depth, active_ids=active_ids) for i, item in enumerate(val)])
        if (origin is dict and not isinstance(val, dict)) or (origin is not dict and not isinstance(val, cabc.Mapping)):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected mapping at {path}, got {type(val).__name__}")
        out: MutableJsonObject = {}
        for k, v in val.items():
            k_str = _encode_map_key(args[0], k, path=f"{path}[{k!r}]")
            if k_str in out:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Duplicate serialized map key {k_str!r} at {path}")
            out[k_str] = _encode_declared_value(args[1], v, path=f"{path}.{k_str}", depth=depth + 1, max_depth=max_depth, active_ids=active_ids)
        return out
    finally:
        active_ids.remove(obj_id)


def _encode_dataclass_checked(
    dc_cls: type[object], tv_map: Mapping[object, object], obj: object, *, path: str, depth: int, max_depth: int, active_ids: set[int]
) -> MutableJsonObject:
    if depth > max_depth:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Maximum nesting depth exceeded at {path}")
    if type(obj) is not dc_cls:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected {dc_cls.__name__} at {path}, got {type(obj).__name__}")
    obj_id = id(obj)
    if obj_id in active_ids:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Circular reference detected at {path}")
    active_ids.add(obj_id)
    try:
        try:
            _, hints = _get_dc_meta(dc_cls, None)
        except _UnresolvedLocalHintError:
            hints = None
        if hints is not None:
            _ensure_schema_valid_once(dc_cls, localns=None)
        out: MutableJsonObject = {}
        for field_name, getter in _get_dataclass_field_getters(dc_cls):
            val = getter(obj)
            if hints is None:
                out[field_name] = _encode_untyped_value(val, path=f"{path}.{field_name}", depth=depth + 1, max_depth=max_depth, active_ids=active_ids)
            else:
                ft = _substitute_typevars(hints[field_name], tv_map) if tv_map else hints[field_name]
                out[field_name] = _encode_declared_value(ft, val, path=f"{path}.{field_name}", depth=depth + 1, max_depth=max_depth, active_ids=active_ids)
        return out
    finally:
        active_ids.remove(obj_id)


def _encode_declared_value(
    tp: object, val: object, *, path: str, depth: int, max_depth: int, active_ids: set[int]
) -> JsonValue:
    if depth > max_depth:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Maximum nesting depth exceeded at {path}")
    cur = _unwrap_ref_leaf(tp, localns=None)
    if cur == JsonValue:
        return _strict_json(val, as_wire=True, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids)
    if _is_untyped_wildcard(cur):
        return _encode_untyped_value(val, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids)
    if cur is type(None):
        if val is not None:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected None at {path}")
        return None
    bare_checks: tuple[tuple[tuple[object, ...], type[object] | tuple[type[object], ...]], ...] = (
        ((dict,), dict), ((cabc.Mapping, Mapping), cabc.Mapping), ((list,), list),
        ((tuple, Tuple), tuple), ((cabc.Sequence, Sequence), (list, tuple)), ((frozenset,), frozenset),
    )
    for forms, expected_inst in bare_checks:
        if cur in forms:
            if not isinstance(val, expected_inst) or (cur is list and type(val) is not list):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected {cur!r} at {path}")
            return _encode_untyped_value(val, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids)
    if isinstance(cur, TypeVar):
        if cur.__constraints__:
            return _first_match(cur.__constraints__, lambda b: _encode_declared_value(b, val, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids), f"Value failed TypeVar {cur.__name__} at {path}")
        if cur.__bound__ is not None:
            return _encode_declared_value(cur.__bound__, val, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids)
        return _encode_untyped_value(val, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids)
    origin, args = get_origin(cur), get_args(cur)
    if origin is Literal:
        return _encode_literal_typed(cur, val, path=path)
    if origin in (Union, UnionType):
        return _first_match(args, lambda b: _encode_declared_value(b, val, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids), f"Value failed union {cur!r} at {path}")
    if origin in (tuple, list, Sequence, cabc.Sequence, frozenset, dict, Mapping, cabc.Mapping):
        return _encode_container_typed(origin, args, val, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids)
    if isinstance(origin, type) and origin not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(origin):
        return _encode_dataclass_checked(origin, dict(zip(_generic_type_params(origin), args)), val, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids)
    if isinstance(cur, type) and (cur in _SUPPORTED_SCALAR_CLASSES or issubclass(cur, Enum)):
        return _encode_scalar_typed(cur, val, path=path)
    if isinstance(cur, type) and dataclasses.is_dataclass(cur):
        return _encode_dataclass_checked(cur, {}, val, path=path, depth=depth, max_depth=max_depth, active_ids=active_ids)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported declared type {cur!r} at {path}")


def _encode_by_type(expected_type: Optional[object], obj: object, *, max_depth: int) -> JsonValue:
    cache = _CodecMetadataCache.instance()
    act = cache.active
    owns_act = act.dc_meta is None
    if owns_act:
        act.dc_meta, act.valid_schemas = {}, set()
    try:
        active_ids: set[int] = set()
        if expected_type is None:
            return _encode_untyped_value(obj, path="$", depth=0, max_depth=max_depth, active_ids=active_ids)
        _ensure_schema_valid_once(expected_type, localns=None)
        return _encode_declared_value(expected_type, obj, path="$", depth=0, max_depth=max_depth, active_ids=active_ids)
    except _UnresolvedLocalHintError as exc:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, str(exc)) from exc
    finally:
        if owns_act:
            act.dc_meta, act.valid_schemas = None, None


def _class_or_fields_mention_prefix(dc_cls: type[object], hints: Mapping[str, object], prefix: str) -> bool:
    return _type_mentions_module_prefix(dc_cls, prefix) or any(_type_mentions_module_prefix(ft, prefix) for ft in hints.values())


class DataclassCodec:
    """Strict pure-stdlib codec between immutable dataclasses/value objects and JSON-safe values."""

    @staticmethod
    def encode(obj: object) -> JsonValue:
        return _encode_by_type(None, obj, max_depth=_MAX_CODEC_DEPTH)

    @staticmethod
    def encode_typed(expected_type: object, obj: object) -> JsonValue:
        return _encode_by_type(expected_type, obj, max_depth=_MAX_CODEC_DEPTH)

    @staticmethod
    def encode_object(obj: object, *, expected_type: Optional[object] = None) -> MutableJsonObject:
        encoded = _encode_by_type(expected_type, obj, max_depth=_MAX_CODEC_DEPTH)
        if type(encoded) is not dict:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"encode_object expected JSON object, got {type(encoded).__name__}")
        return encoded

    @staticmethod
    def encode_envelope(obj: object) -> MutableJsonObject:
        encoded = _encode_by_type(None, obj, max_depth=_MAX_CODEC_DEPTH + _ENVELOPE_DEPTH_HEADROOM)
        if type(encoded) is not dict:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"encode_envelope expected JSON object, got {type(encoded).__name__}")
        return encoded

    @staticmethod
    def decode_envelope(target_cls: type[T], raw: JsonValue) -> T:
        return _decode_by_type(target_cls, raw, max_depth=_MAX_CODEC_DEPTH + _ENVELOPE_DEPTH_HEADROOM, localns=None)

    @overload
    @staticmethod
    def decode(target_cls: type[T], raw: JsonValue, *, localns: Optional[Mapping[str, object]] = None) -> T:
        ...

    @overload
    @staticmethod
    def decode(target_cls: object, raw: JsonValue, *, localns: Optional[Mapping[str, object]] = None) -> object:
        ...

    @staticmethod
    def decode(target_cls: object, raw: JsonValue, *, localns: Optional[Mapping[str, object]] = None) -> object:
        return _decode_by_type(target_cls, raw, max_depth=_MAX_CODEC_DEPTH, localns=localns)

    @staticmethod
    def canonical_hash(raw: object) -> str:
        encoded = DataclassCodec.encode(raw)
        wire_bytes = json.dumps(encoded, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
        return hashlib.sha256(wire_bytes).hexdigest()

    @staticmethod
    def evict_module_prefix(module_prefix: str) -> None:
        if type(module_prefix) is not str:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "module_prefix must be str")
        clean = module_prefix.strip(".")
        if not clean:
            return
        dot_pkg = f"{clean}."
        cache = _CodecMetadataCache.instance()
        with cache.lock:
            evicted_cls: set[type[object]] = set()
            for cls_k, meta in list(cache.dc_meta.items()):
                if _class_or_fields_mention_prefix(cls_k, meta[1], clean):
                    evicted_cls.add(cls_k)
                    cache.dc_meta.pop(cls_k, None)
            for cls_k in list(cache.dc_getters):
                if cls_k in evicted_cls or _type_mentions_module_prefix(cls_k, clean):
                    cache.dc_getters.pop(cls_k, None)
            for enum_k in list(cache.enum_tables):
                if _obj_in_module_prefix(enum_k, clean, dot_pkg):
                    cache.enum_tables.pop(enum_k, None)
            for valid_k in list(cache.valid_type_schemas):
                if valid_k in evicted_cls or _type_mentions_module_prefix(valid_k, clean):
                    cache.valid_type_schemas.discard(valid_k)
            for fn_k, cached_v in list(cache.callable_payloads.items()):
                if _obj_in_module_prefix(fn_k, clean, dot_pkg) or (cached_v[1] is not None and _type_mentions_module_prefix(cached_v[1], clean)):
                    cache.callable_payloads.pop(fn_k, None)
            try:
                cleanups = typing._cleanups
            except AttributeError:
                cleanups = ()
            for cleanup in cleanups:
                if callable(cleanup):
                    cleanup()


@dataclass(slots=True)
class _FndAnnotatedMetaInfo:
    base_type: object
    description: Optional[str] = None
    merge_strategy: Optional[str] = None


@dataclass(slots=True)
class _FndSchemaExportCtx:
    defs: dict[str, MutableJsonObject]
    in_progress: set[str]
    key_to_def: dict[object, str]
    root_key: Optional[object] = None
    root_referenced: bool = False


def _extract_annotated_meta(tp: object) -> _FndAnnotatedMetaInfo:
    cur = tp
    desc: Optional[str] = None
    merge_tag: Optional[str] = None
    while get_origin(cur) is Annotated:
        for meta in cur.__metadata__:
            if type(meta) is str and meta.strip():
                desc = meta.strip()
            elif isinstance(meta, cabc.Mapping):
                raw_d = meta.get("description")
                if type(raw_d) is str and raw_d.strip():
                    desc = raw_d.strip()
            elif dataclasses.is_dataclass(meta) and not isinstance(meta, type):
                for fld in dataclasses.fields(meta):
                    f_val = operator.attrgetter(fld.name)(meta)
                    if fld.name in ("description", "summary") and type(f_val) is str and f_val.strip():
                        desc = f_val.strip()
                    elif fld.name == "merge" and isinstance(f_val, Enum) and type(f_val.value) is str:
                        merge_tag = f_val.value
        args = get_args(cur)
        if not args:
            break
        cur = args[0]
    return _FndAnnotatedMetaInfo(base_type=cur, description=desc, merge_strategy=merge_tag)


def _json_type_tag_for_wire_values(values: Sequence[JsonValue]) -> Optional[str]:
    if not values:
        return None
    tags: set[str] = set()
    for val in values:
        if val is None:
            tags.add("null")
        elif type(val) is bool:
            tags.add("boolean")
        elif type(val) is int:
            tags.add("integer")
        elif type(val) is float:
            tags.add("number")
        elif type(val) is str:
            tags.add("string")
        else:
            return None
    return next(iter(tags)) if len(tags) == 1 else None


def _short_schema_type_slug(tp: object) -> str:
    unwrapped = _unwrap_annotated(tp)
    if isinstance(unwrapped, type):
        return unwrapped.__name__
    orig = get_origin(unwrapped)
    args = get_args(unwrapped)
    if isinstance(orig, type) and args:
        arg_slug = "_".join(_short_schema_type_slug(a) for a in args if a is not Ellipsis)
        return f"{orig.__name__}_{arg_slug}" if arg_slug else orig.__name__
    return re.sub(r"[^0-9A-Za-z_]+", "_", str(unwrapped)).strip("_") or "Type"


def _allocate_def_name(dc_cls: type[object], type_args: tuple[object, ...], ctx: _FndSchemaExportCtx) -> str:
    base_name = (
        f"{dc_cls.__name__}_{'_'.join(_short_schema_type_slug(a) for a in type_args)}"
        if type_args
        else dc_cls.__name__
    )
    if base_name not in ctx.defs and base_name not in ctx.in_progress:
        return base_name
    qual_prefix = re.sub(r"[^0-9A-Za-z_]+", "_", f"{dc_cls.__module__}_{dc_cls.__qualname__}").strip("_")
    cand = f"{qual_prefix}_{base_name}" if type_args else qual_prefix
    seq_idx = 2
    unique = cand
    while unique in ctx.defs or unique in ctx.in_progress:
        unique = f"{cand}_{seq_idx}"
        seq_idx += 1
    return unique


def _export_scalar_schema(tp: type[object]) -> MutableJsonObject:
    if issubclass(tp, Enum):
        wire_vals: list[JsonValue] = [wv for wv, _ in _get_enum_table(tp)]
        tp_tag = _json_type_tag_for_wire_values(wire_vals)
        out: MutableJsonObject = {"enum": wire_vals}
        if tp_tag is not None:
            out["type"] = tp_tag
        return out
    if tp is bool:
        return {"type": "boolean"}
    if tp is int:
        return {"type": "integer", "minimum": INT64_MIN, "maximum": INT64_MAX}
    if tp is SnapshotGen:
        return {"type": "integer", "minimum": 0, "maximum": INT64_MAX}
    if tp is float:
        return {"type": "number"}
    if tp is str:
        return {"type": "string"}
    if tp is bytes:
        return {"type": "string", "contentEncoding": "base64"}
    if tp is ModuleId:
        return {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]*$"}
    if tp in (TaskId, EventId):
        return {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]*(\\.[a-z0-9][a-z0-9_-]*)+$"}
    if tp is SemanticUri:
        return {"type": "string", "pattern": "^[a-z][a-z0-9_-]*(\\.[a-z0-9_-]+)*://.*$"}
    if tp is SpaceId:
        return {"type": "string", "pattern": "^([a-z0-9][a-z0-9_-]*)?/[a-z0-9][a-z0-9_-]*$"}
    if tp is EnvHash:
        return {"type": "string", "pattern": "^[0-9a-f]{16,64}$"}
    if tp is SemVer4:
        return {"type": "string", "minLength": 5}
    return {"type": "string", "minLength": 1}


def _export_literal_schema(tp: object) -> MutableJsonObject:
    vals: list[JsonValue] = []
    for arg in get_args(tp):
        if isinstance(arg, Enum):
            vals.append(_validate_enum_wire_val(arg.value, type(arg), arg.name))
        elif type(arg) is bytes:
            vals.append(base64.b64encode(arg).decode("ascii"))
        elif arg is None or type(arg) in (bool, int, str):
            vals.append(arg)
    out: MutableJsonObject = {"enum": vals}
    tp_tag = _json_type_tag_for_wire_values(vals)
    if tp_tag is not None:
        out["type"] = tp_tag
    return out


def _apply_annotated_extras(schema: MutableJsonObject, info: _FndAnnotatedMetaInfo) -> MutableJsonObject:
    if info.description is None and info.merge_strategy is None:
        return schema
    enriched = dict(schema)
    if info.description is not None:
        enriched["description"] = info.description
    if info.merge_strategy is not None:
        enriched["x-yscb-merge"] = info.merge_strategy
    return enriched


def _try_encode_field_default(fld: dataclasses.Field[object], resolved_tp: object) -> tuple[bool, JsonValue]:
    if fld.default is not dataclasses.MISSING:
        try:
            return (True, DataclassCodec.encode_typed(resolved_tp, fld.default))
        except YscbError:
            try:
                return (True, DataclassCodec.encode(fld.default))
            except YscbError:
                return (False, None)
    if fld.default_factory is not dataclasses.MISSING:
        try:
            sample = fld.default_factory()
            return (True, DataclassCodec.encode_typed(resolved_tp, sample))
        except (YscbError, Exception):
            return (False, None)
    return (False, None)


def _export_dc_object_schema(
    dc_cls: type[object],
    tv_map: Mapping[object, object],
    schema_title: str,
    ctx: _FndSchemaExportCtx,
) -> MutableJsonObject:
    _, hints = _get_dc_meta(dc_cls, None)
    props: MutableJsonObject = {}
    required: list[JsonValue] = []
    for fld in dataclasses.fields(dc_cls):
        if not fld.init:
            continue
        raw_hint = hints[fld.name]
        outer_meta = _extract_annotated_meta(raw_hint)
        resolved_tp = _substitute_typevars(outer_meta.base_type, tv_map) if tv_map else outer_meta.base_type
        field_schema = _apply_annotated_extras(_export_schema_node(resolved_tp, ctx), outer_meta)
        is_req = fld.default is dataclasses.MISSING and fld.default_factory is dataclasses.MISSING
        if is_req:
            required.append(fld.name)
        else:
            has_dflt, enc_dflt = _try_encode_field_default(fld, resolved_tp)
            if has_dflt:
                field_schema = dict(field_schema)
                field_schema["default"] = enc_dflt
        props[fld.name] = field_schema
    return {
        "title": schema_title,
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def _freeze_schema_type_key(tp: object) -> object:
    meta = _extract_annotated_meta(tp)
    orig = get_origin(meta.base_type)
    args = get_args(meta.base_type)
    frozen_base: object
    if orig is not None and args:
        frozen_base = (orig, tuple(_freeze_schema_type_key(a) for a in args))
    else:
        try:
            hash(meta.base_type)
            frozen_base = meta.base_type
        except TypeError:
            frozen_base = repr(meta.base_type)
    if meta.description is None and meta.merge_strategy is None:
        return frozen_base
    return (frozen_base, meta.description, meta.merge_strategy)


def _export_dc_ref_schema(
    dc_cls: type[object],
    type_args: tuple[object, ...],
    ctx: _FndSchemaExportCtx,
) -> MutableJsonObject:
    frozen_args = tuple(_freeze_schema_type_key(a) for a in type_args)
    dc_key: object = (dc_cls, frozen_args) if frozen_args else dc_cls
    if dc_key in ctx.key_to_def:
        def_name = ctx.key_to_def[dc_key]
        if dc_key == ctx.root_key:
            ctx.root_referenced = True
        return {"$ref": f"#/$defs/{def_name}"}
    def_name = _allocate_def_name(dc_cls, type_args, ctx)
    ctx.key_to_def[dc_key] = def_name
    ctx.in_progress.add(def_name)
    try:
        tv_map = dict(zip(_generic_type_params(dc_cls), type_args)) if type_args else {}
        ctx.defs[def_name] = _export_dc_object_schema(dc_cls, tv_map, def_name, ctx)
    finally:
        ctx.in_progress.discard(def_name)
    return {"$ref": f"#/$defs/{def_name}"}


def _export_schema_node(tp: object, ctx: _FndSchemaExportCtx) -> MutableJsonObject:
    meta_info = _extract_annotated_meta(tp)
    cur = _unwrap_ref_leaf(meta_info.base_type, localns=None)
    inner_meta = _extract_annotated_meta(cur)
    if inner_meta.description is not None and meta_info.description is None:
        meta_info.description = inner_meta.description
    if inner_meta.merge_strategy is not None and meta_info.merge_strategy is None:
        meta_info.merge_strategy = inner_meta.merge_strategy
    cur = inner_meta.base_type
    schema: MutableJsonObject
    if cur == JsonValue or _is_untyped_wildcard(cur):
        schema = {}
    elif cur is type(None):
        schema = {"type": "null"}
    elif cur in (JsonObject, MutableJsonObject, dict, cabc.Mapping, Mapping):
        schema = {"type": "object", "additionalProperties": True}
    elif cur in (list, cabc.Sequence, Sequence, tuple, Tuple):
        schema = {"type": "array"}
    elif cur is frozenset:
        schema = {"type": "array", "uniqueItems": True}
    elif _is_explicit_empty_tuple_type(cur):
        schema = {"type": "array", "maxItems": 0}
    elif isinstance(cur, TypeVar):
        if cur.__constraints__:
            schema = {"anyOf": [_export_schema_node(c, ctx) for c in cur.__constraints__]}
        elif cur.__bound__ is not None:
            schema = _export_schema_node(cur.__bound__, ctx)
        else:
            schema = {}
    else:
        origin, args = get_origin(cur), get_args(cur)
        if origin is Literal:
            schema = _export_literal_schema(cur)
        elif origin in (Union, UnionType):
            schema = {"anyOf": [_export_schema_node(b, ctx) for b in args]}
        elif origin is tuple:
            if len(args) == 2 and args[1] is Ellipsis:
                schema = {"type": "array", "items": _export_schema_node(args[0], ctx)}
            else:
                prefix_items: list[JsonValue] = [_export_schema_node(item_tp, ctx) for item_tp in args]
                schema = {
                    "type": "array",
                    "prefixItems": prefix_items,
                    "minItems": len(prefix_items),
                    "maxItems": len(prefix_items),
                    "items": False,
                }
        elif origin in (list, Sequence, cabc.Sequence):
            schema = {"type": "array", "items": _export_schema_node(args[0], ctx)}
        elif origin is frozenset:
            schema = {"type": "array", "items": _export_schema_node(args[0], ctx), "uniqueItems": True}
        elif origin in (dict, Mapping, cabc.Mapping):
            schema = {"type": "object", "additionalProperties": _export_schema_node(args[1], ctx)}
        elif isinstance(origin, type) and origin not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(origin):
            schema = _export_dc_ref_schema(origin, args, ctx)
        elif isinstance(cur, type) and (cur in _SUPPORTED_SCALAR_CLASSES or issubclass(cur, Enum)):
            schema = _export_scalar_schema(cur)
        elif isinstance(cur, type) and dataclasses.is_dataclass(cur):
            schema = _export_dc_ref_schema(cur, (), ctx)
        else:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported SchemaExporter type {cur!r}")
    return _apply_annotated_extras(schema, meta_info)


class SchemaExporter:
    """Pure-standard-library JSON Schema (Draft 2020-12) exporter for Contributes 2.0 and IDE completion."""

    @staticmethod
    def export(target_cls: type[object], *, title: Optional[str] = None) -> MutableJsonObject:
        if title is not None:
            try:
                require_pure_str(title, "SchemaExporter.export title", non_empty=True)
            except ValueError as exc:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, str(exc)) from exc
        cache = _CodecMetadataCache.instance()
        act = cache.active
        owns_act = act.dc_meta is None
        if owns_act:
            act.dc_meta, act.valid_schemas = {}, set()
        try:
            _ensure_schema_valid_once(target_cls, localns=None)
            ctx = _FndSchemaExportCtx(defs={}, in_progress=set(), key_to_def={})
            meta_info = _extract_annotated_meta(target_cls)
            resolved_root = _unwrap_ref_leaf(meta_info.base_type, localns=None)
            orig = get_origin(resolved_root)
            args = get_args(resolved_root)
            if isinstance(orig, type) and orig not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(orig):
                root_dc, root_args = orig, args
            elif isinstance(resolved_root, type) and resolved_root not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(resolved_root):
                root_dc, root_args = resolved_root, ()
            else:
                eff_non_dc_title = title if title is not None else _short_schema_type_slug(resolved_root)
                body = _apply_annotated_extras(_export_schema_node(target_cls, ctx), meta_info)
                raw_non_dc: MutableJsonObject = {
                    "$schema": _JSON_SCHEMA_DRAFT_URI,
                    "title": eff_non_dc_title,
                    **body,
                    "$defs": ctx.defs,
                }
                return clone_strict_json_object(raw_non_dc, label="SchemaExporter output")

            def_name = _allocate_def_name(root_dc, root_args, ctx)
            eff_title = title if title is not None else def_name
            frozen_root_args = tuple(_freeze_schema_type_key(a) for a in root_args)
            root_key: object = (root_dc, frozen_root_args) if frozen_root_args else root_dc
            ctx.root_key = root_key
            ctx.key_to_def[root_key] = def_name
            ctx.in_progress.add(def_name)
            try:
                tv_map = dict(zip(_generic_type_params(root_dc), root_args)) if root_args else {}
                root_obj = _apply_annotated_extras(_export_dc_object_schema(root_dc, tv_map, eff_title, ctx), meta_info)
            finally:
                ctx.in_progress.discard(def_name)
            if ctx.root_referenced:
                def_copy = clone_strict_json_object(root_obj, label="SchemaExporter root def")
                def_copy["title"] = def_name
                ctx.defs[def_name] = def_copy
            raw_root: MutableJsonObject = {
                "$schema": _JSON_SCHEMA_DRAFT_URI,
                **root_obj,
                "$defs": ctx.defs,
            }
            return clone_strict_json_object(raw_root, label="SchemaExporter output")
        except _UnresolvedLocalHintError as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, str(exc)) from exc
        finally:
            if owns_act:
                act.dc_meta, act.valid_schemas = None, None
