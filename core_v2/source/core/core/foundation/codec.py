"""Pure-standard-library strict codec between frozen dataclasses and JSON-safe structures."""

from __future__ import annotations

import base64
import binascii
from collections import OrderedDict
import collections.abc as cabc
import dataclasses
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
    EventId,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    MutableJsonObject,
    TaskId,
    require_non_none,
)

T = TypeVar("T")
_CANONICAL_INT_KEY_RE = re.compile(r"(?:0|-?[1-9][0-9]*)")
_PLAN_LRU_LIMIT = 512
_MAX_CODEC_DEPTH = MAX_USER_JSON_DEPTH
_ENVELOPE_DEPTH_HEADROOM = 8

DecodeFn = Callable[[JsonValue, str, int], object]
LeafDecodeFn = Callable[[JsonValue, str], object]
FieldGetter = tuple[str, Callable[[object], object]]


def _as_leaf_plan(fn: LeafDecodeFn) -> DecodeFn:
    return lambda raw, path, *_rest: fn(raw, path)


class _UnresolvedLocalHintError(Exception):
    """Raised internally when get_type_hints fails on an exited local closure scope."""


def _is_untyped_wildcard(tp: object) -> bool:
    return tp is object


def _is_forbidden_any_type(tp: object) -> bool:
    return repr(tp) == "typing.Any" or (isinstance(tp, ForwardRef) and tp.__forward_arg__ == "Any")


CompiledDcMeta = tuple[tuple[tuple[str, bool], ...], dict[str, tuple[object, dict[str, object]]]]


class _ActiveCodecMemo(threading.local):
    def __init__(self) -> None:
        self.plans: Optional[dict[object, DecodeFn]] = None
        self.hints: Optional[dict[type[object], CompiledDcMeta]] = None


class _WeakTypeToken:
    """Hashable weak-reference wrapper preventing DataclassCodec caches from pinning dynamic user types."""

    __slots__ = ("_ref", "_hash")

    def __init__(
        self,
        cls: type[object],
        on_dead: Optional[cabc.Callable[[weakref.ReferenceType[type[object]]], object]] = None,
    ) -> None:
        self._ref = weakref.ref(cls, on_dead) if on_dead is not None else weakref.ref(cls)
        self._hash = hash(cls)

    def resolve(self) -> Optional[type[object]]:
        return self._ref()

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: object) -> bool:
        if type(other) is not _WeakTypeToken:
            return False
        c1, c2 = self._ref(), other._ref()
        return c1 is not None and c1 is c2


@dataclasses.dataclass(frozen=True, slots=True)
class _DehydratedExpr:
    kind: str
    head: object
    args: tuple[object, ...] = ()


def _dehydrate_type(
    tp: object,
    on_dead: Optional[cabc.Callable[[weakref.ReferenceType[type[object]]], object]] = None,
) -> object:
    if isinstance(tp, Enum):
        return _DehydratedExpr("enum", _WeakTypeToken(type(tp), on_dead), (tp.name,))
    if isinstance(tp, type):
        if tp.__module__ == "builtins" or tp in (ModuleId, TaskId, EventId, HostPath):
            return tp
        try:
            return _WeakTypeToken(tp, on_dead)
        except TypeError:
            return tp
    orig = get_origin(tp)
    if orig is Annotated:
        return _DehydratedExpr(
            "ann",
            _dehydrate_type(get_args(tp)[0], on_dead),
            tuple(
                _dehydrate_type(
                    m if isinstance(m, (type, Enum, TypeVar, ForwardRef)) or get_origin(m) is not None else type(m),
                    on_dead,
                )
                for m in tp.__metadata__
            ),
        )
    if orig is not None:
        norm_o: object = Union if orig in (Union, UnionType) else (cabc.Sequence if orig is Sequence else (cabc.Mapping if orig is Mapping else orig))
        return _DehydratedExpr("gen", _dehydrate_type(norm_o, on_dead), tuple(_dehydrate_type(a, on_dead) for a in get_args(tp)))
    return tp


def _rehydrate_type(tok: object) -> tuple[bool, object]:
    if type(tok) is _WeakTypeToken:
        cls = tok.resolve()
        return (cls is not None, cls)
    if not isinstance(tok, _DehydratedExpr):
        return (True, tok)
    ok_h, head = _rehydrate_type(tok.head)
    if not ok_h:
        return (False, None)
    if tok.kind == "enum":
        if not isinstance(head, type) or not issubclass(head, Enum) or not tok.args or not isinstance(tok.args[0], str):
            return (False, None)
        return (True, head[tok.args[0]])
    a_res = [_rehydrate_type(a) for a in tok.args]
    if not all(ok for ok, _ in a_res):
        return (False, None)
    args = tuple(v for _, v in a_res)
    if tok.kind == "ann":
        return (True, operator.getitem(Annotated, (head, *args)))
    if head is tuple and not args:
        return (True, tuple[()])
    return (True, _rebuild_resolved_generic(head, args, head))


class _CodecMetadataCache:
    """Thread-safe compiled plan, dataclass MRO field metadata, Enum table, and callable hint cache."""

    def __init__(self) -> None:
        self.active = _ActiveCodecMemo()
        self.lock = threading.RLock()
        self.dc_getters: weakref.WeakKeyDictionary[type[object], tuple[FieldGetter, ...]] = weakref.WeakKeyDictionary()
        self.dc_hints: weakref.WeakKeyDictionary[
            type[object],
            tuple[tuple[tuple[str, bool], ...], dict[str, object]],
        ] = weakref.WeakKeyDictionary()
        self.enum_tables: weakref.WeakKeyDictionary[type[Enum], tuple[tuple[JsonValue, str], ...]] = (
            weakref.WeakKeyDictionary()
        )
        self.type_plans: weakref.WeakKeyDictionary[type[object], DecodeFn] = weakref.WeakKeyDictionary()
        self.form_plans: OrderedDict[object, DecodeFn] = OrderedDict()
        self.callable_payloads: weakref.WeakKeyDictionary[object, tuple[bool, object]] = (
            weakref.WeakKeyDictionary()
        )
        self.recursive_dcs: weakref.WeakSet[type[object]] = weakref.WeakSet()
        self.valid_type_schemas: weakref.WeakSet[type[object]] = weakref.WeakSet()
        self.valid_form_schemas: OrderedDict[object, None] = OrderedDict()


def _assert_int64_range(val: int, *, path: str) -> int:
    if val < INT64_MIN or val > INT64_MAX:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Integer out of int64 range at {path}")
    return val


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
    return get_origin(unwrapped) is tuple and get_args(unwrapped) == ()


def _check_str_valid_utf8(s: str, *, path: str) -> str:
    try:
        s.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid UTF-8 surrogate string at {path}: {safe_exception_summary(exc)}") from exc
    return s


def _validate_json_value(raw: object, *, path: str, depth: int) -> JsonValue:
    if depth > _MAX_CODEC_DEPTH:
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
        if not math.isfinite(raw):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Non-finite float at {path}")
        return raw
    if isinstance(raw, (list, tuple)):
        return tuple(_validate_json_value(item, path=f"{path}[{i}]", depth=depth + 1) for i, item in enumerate(raw))
    if isinstance(raw, cabc.Mapping):
        return _validate_json_object(raw, path=path, depth=depth)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid JSON value of type {type(raw).__name__} at {path}")


def _validate_json_object(raw: object, *, path: str, depth: int) -> MutableJsonObject:
    if depth > _MAX_CODEC_DEPTH:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Maximum nesting depth exceeded at {path}")
    if not isinstance(raw, cabc.Mapping):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected JSON object at {path}")
    validated_map: MutableJsonObject = {}
    for k, v in raw.items():
        if type(k) is not str:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected plain string key at {path}")
        _check_str_valid_utf8(k, path=path)
        validated_map[k] = _validate_json_value(v, path=f"{path}.{k}", depth=depth + 1)
    return validated_map


def _substitute_typevars(tp: object, tv_map: Mapping[object, object]) -> object:
    tp = _unwrap_annotated(tp)
    if isinstance(tp, TypeVar):
        return tv_map.get(tp, tp)
    if _is_explicit_empty_tuple_type(tp):
        return tuple[()]
    origin = get_origin(tp)
    if origin is None or origin is Literal:
        return tp
    args = get_args(tp)
    if not args:
        return tp
    replaced = tuple(_substitute_typevars(a, tv_map) for a in args)
    if origin is UnionType or origin is Union:
        return functools.reduce(operator.or_, replaced)
    try:
        return operator.getitem(origin, replaced[0] if len(replaced) == 1 else replaced)
    except TypeError:
        return tp


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
    orig_args = [b_arg for orig_b in (raw_bases if isinstance(raw_bases, tuple) else ()) for b_arg in get_args(orig_b)]
    for b_arg in orig_args:
        if isinstance(b_arg, type) and b_arg.__name__ not in out:
            out[b_arg.__name__] = b_arg
    for member in base.__dict__.values():
        raw_fn = member.__func__ if isinstance(member, (staticmethod, classmethod)) else member
        if isinstance(raw_fn, types.FunctionType):
            _copy_fn_closure_cells(raw_fn, out)


def _populate_qualname_and_closure_ns(
    mod_name: str,
    qualname: str,
    cls_or_fn: object,
    out: dict[str, object],
) -> None:
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


def _populate_active_stack_locals(qualname: str, out: dict[str, object]) -> None:
    if ".<locals>." not in qualname:
        return
    parts = qualname.split(".")
    fn_names = {parts[i] for i in range(len(parts) - 1) if parts[i + 1] == "<locals>"}
    frame: Optional[types.FrameType] = sys._getframe(0)
    while frame is not None:
        if frame.f_code.co_name in fn_names:
            out.update({k: v for k, v in frame.f_locals.items() if isinstance(v, (type, TypeVar)) and k not in out})
        frame = frame.f_back


@dataclasses.dataclass(frozen=True, slots=True)
class _UnwrappedCallable:
    target_fn: Optional[types.FunctionType]
    owner_cls: Optional[type[object]]
    skip_pos: int
    bound_kw: set[str]


def _unwrap_callable_target(fn: object) -> _UnwrappedCallable:
    cur: object = fn
    skip_pos = 0
    bound_kw: set[str] = set()
    while isinstance(cur, functools.partial):
        skip_pos += len(cur.args)
        if cur.keywords:
            bound_kw.update(cur.keywords.keys())
        cur = cur.func
    if isinstance(cur, types.MethodType):
        owner = cur.__self__ if isinstance(cur.__self__, type) else type(cur.__self__)
        fn_obj = cur.__func__ if isinstance(cur.__func__, types.FunctionType) else None
        return _UnwrappedCallable(fn_obj, owner, skip_pos + 1, bound_kw)
    if isinstance(cur, types.FunctionType):
        return _UnwrappedCallable(cur, None, skip_pos, bound_kw)
    if isinstance(cur, type):
        init_fn = cur.__init__ if isinstance(cur.__init__, types.FunctionType) else None
        return _UnwrappedCallable(init_fn, cur, skip_pos + 1, bound_kw)
    call_m = type(cur).__call__
    return _UnwrappedCallable(call_m if isinstance(call_m, types.FunctionType) else None, type(cur), skip_pos + 1, bound_kw)


def infer_sequence_element_dataclass(fn: object, *, strict_unresolved: bool) -> tuple[bool, Optional[object]]:
    """Infer TPayload from a mapper callable's first Sequence[TPayload] parameter inside the codec reflection boundary."""
    if not callable(fn):
        return (True, None)
    with DataclassCodec._CACHE.lock:
        try:
            cached = DataclassCodec._CACHE.callable_payloads.get(fn)
        except TypeError:
            cached = None
    if cached is not None and cached[0]:
        ok_cb, inf_tp = _rehydrate_type(cached[1])
        if ok_cb:
            return (True, inf_tp)

    unwrapped = _unwrap_callable_target(fn)
    target_fn, owner_cls, skip_pos, bound_kw = (
        unwrapped.target_fn,
        unwrapped.owner_cls,
        unwrapped.skip_pos,
        unwrapped.bound_kw,
    )
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
    hints = _try_resolve_callable_hints(target_fn, localns, param_name, strict_unresolved=strict_unresolved)
    if hints is None:
        return (False, None)
    inferred: Optional[object] = None
    if param_name in hints:
        param_tp = _unwrap_annotated(hints[param_name])
        if get_origin(param_tp) in (list, tuple, Sequence, cabc.Sequence):
            args = get_args(param_tp)
            elem_tp = _unwrap_annotated(args[0]) if args else None
            if elem_tp is not None and _is_dataclass_or_generic_dc(elem_tp):
                inferred = elem_tp
    with DataclassCodec._CACHE.lock:
        try:
            DataclassCodec._CACHE.callable_payloads[fn] = (True, _dehydrate_type(inferred))
        except TypeError:
            pass
    return (True, inferred)


def _try_resolve_callable_hints(
    target_fn: types.FunctionType,
    localns: dict[str, object],
    param_name: str,
    *,
    strict_unresolved: bool,
) -> Optional[dict[str, object]]:
    try:
        return get_type_hints(target_fn, localns=localns)
    except NameError:
        _populate_active_stack_locals(target_fn.__qualname__, localns)
    try:
        return get_type_hints(target_fn, localns=localns)
    except (NameError, TypeError, AttributeError) as exc:
        if strict_unresolved and param_name in target_fn.__annotations__:
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"Unresolvable type annotation on event subscription mapper: {safe_exception_summary(exc)}",
            ) from exc
        return None


def _is_wildcard_elem(arg: object) -> bool:
    arg = _unwrap_annotated(arg)
    if _is_wildcard_json_candidate(arg):
        return True
    if isinstance(arg, ForwardRef):
        return arg.__forward_arg__ in ("JsonValue", "object")
    if get_origin(arg) in (Union, UnionType):
        u_args = get_args(arg)
        has_seq = any(
            get_origin(_unwrap_annotated(b)) in (list, cabc.Sequence, Sequence, tuple) and _is_wildcard_json_candidate(b)
            for b in u_args
        )
        has_map = any(
            get_origin(_unwrap_annotated(b)) in (dict, cabc.Mapping, Mapping) and _is_wildcard_json_candidate(b)
            for b in u_args
        )
        has_jref = any(isinstance(b, ForwardRef) and b.__forward_arg__ == "JsonValue" for b in u_args)
        return (
            {type(None), bool, int, float, str}.issubset(u_args)
            and (has_jref or (has_seq and has_map))
            and all(
                b in (type(None), bool, int, float, str)
                or _is_wildcard_json_candidate(b)
                or (isinstance(b, ForwardRef) and b.__forward_arg__ == "JsonValue")
                for b in u_args
            )
        )
    return False


def _is_wildcard_json_candidate(cand: object) -> bool:
    cand = _unwrap_annotated(cand)
    if _is_explicit_empty_tuple_type(cand):
        return False
    if _is_untyped_wildcard(cand) or cand in (
        JsonValue,
        JsonObject,
        MutableJsonObject,
        dict,
        cabc.Mapping,
        Mapping,
        list,
        cabc.Sequence,
        Sequence,
        tuple,
        Tuple,
    ):
        return True
    origin = get_origin(cand)
    if origin in (dict, cabc.Mapping, Mapping):
        args = get_args(cand)
        return not args or (len(args) >= 2 and args[0] is str and _is_wildcard_elem(args[1]))
    if origin in (list, cabc.Sequence, Sequence):
        args = get_args(cand)
        return not args or _is_wildcard_elem(args[0])
    if origin is tuple:
        args = get_args(cand)
        return len(args) == 2 and args[1] is Ellipsis and _is_wildcard_elem(args[0])
    return False


_SCALAR_VO_TYPES: frozenset[type[object]] = frozenset({ModuleId, TaskId, EventId, HostPath})


def _is_dataclass_or_generic_dc(tp: object) -> bool:
    tp = _unwrap_annotated(tp)
    if tp in _SCALAR_VO_TYPES:
        return False
    orig = get_origin(tp)
    return (isinstance(tp, type) and dataclasses.is_dataclass(tp)) or (
        isinstance(orig, type) and orig not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(orig)
    )


def _rank_map_key_candidate(t: object) -> int:
    t = _unwrap_annotated(t)
    if get_origin(t) is Literal or (isinstance(t, type) and issubclass(t, Enum)):
        return 0
    key_ranks: dict[object, int] = {bool: 1, int: 2, TaskId: 3, EventId: 3, ModuleId: 4, HostPath: 5, str: 6}
    return key_ranks.get(t, 7)


def _map_key_specificity_rank(tp: object) -> int:
    tp = _unwrap_annotated(tp)
    if get_origin(tp) in (Union, UnionType):
        return min((_rank_map_key_candidate(a) for a in get_args(tp) if a is not type(None)), default=7)
    return _rank_map_key_candidate(tp)


@dataclasses.dataclass(order=True, frozen=True, slots=True)
class _TypeSpecRank:
    major: int
    minor: int = 0
    sub: int = 0


@dataclasses.dataclass(order=True, frozen=True, slots=True)
class _UnionCandRank:
    r0: int
    r1: int = 0
    r2: int = 0
    r3: int = 0


_WILDCARD_SPEC = _TypeSpecRank(9, 9, 9)
_WILDCARD_UNION = _UnionCandRank(9, 9, 9, 9)


def _type_specificity_tuple(tp: object) -> _TypeSpecRank:
    tp = _unwrap_annotated(tp)
    if _is_explicit_empty_tuple_type(tp):
        return _TypeSpecRank(1, 0, 0)
    if _is_wildcard_elem(tp):
        return _WILDCARD_SPEC
    if _is_dataclass_or_generic_dc(tp) or (isinstance(tp, type) and issubclass(tp, Enum)):
        return _TypeSpecRank(0, 0, 0)
    scalar_ranks: dict[object, _TypeSpecRank] = {
        TaskId: _TypeSpecRank(1, 0, 0),
        EventId: _TypeSpecRank(1, 0, 0),
        ModuleId: _TypeSpecRank(1, 1, 0),
        HostPath: _TypeSpecRank(1, 2, 0),
        bytes: _TypeSpecRank(1, 3, 0),
        bool: _TypeSpecRank(4, 0, 0),
        int: _TypeSpecRank(5, 0, 0),
        str: _TypeSpecRank(5, 0, 0),
        float: _TypeSpecRank(5, 1, 0),
    }
    if tp in scalar_ranks:
        return scalar_ranks[tp]
    orig = get_origin(tp)
    if orig is Literal:
        return _TypeSpecRank(0, 0, 0)
    if orig in (Union, UnionType):
        return min((_type_specificity_tuple(a) for a in get_args(tp) if a is not type(None)), default=_WILDCARD_SPEC)
    if orig is frozenset or tp is frozenset:
        args = get_args(tp)
        sub = _type_specificity_tuple(args[0]) if args else _TypeSpecRank(5, 0, 0)
        return _TypeSpecRank(2, sub.major, sub.minor)
    if orig is tuple:
        args = get_args(tp)
        if not args:
            return _TypeSpecRank(8, 8, 8)
        if len(args) == 2 and args[1] is Ellipsis:
            sub = _type_specificity_tuple(args[0])
            return _WILDCARD_SPEC if sub.major >= 9 else _TypeSpecRank(2, sub.major, sub.minor)
        elem_specs = [_type_specificity_tuple(a) for a in args]
        best = min(elem_specs, default=_WILDCARD_SPEC)
        return _WILDCARD_SPEC if best.major >= 9 else _TypeSpecRank(1, best.major, sum(s.major for s in elem_specs))
    if orig in (list, cabc.Sequence, Sequence):
        args = get_args(tp)
        if not args:
            return _TypeSpecRank(8, 8, 8)
        sub = _type_specificity_tuple(args[0])
        return _WILDCARD_SPEC if sub.major >= 9 else _TypeSpecRank(2, sub.major, sub.minor)
    if orig in (dict, cabc.Mapping, Mapping):
        args = get_args(tp)
        if len(args) < 2:
            return _TypeSpecRank(8, 8, 8)
        v_sub = _type_specificity_tuple(args[1])
        if args[0] is not str:
            return _TypeSpecRank(2, _map_key_specificity_rank(args[0]), v_sub.major)
        return _WILDCARD_SPEC if v_sub.major >= 9 else _TypeSpecRank(3, v_sub.major, v_sub.minor)
    return _TypeSpecRank(6, 0, 0)


def _union_candidate_rank(cand: object, raw: JsonValue) -> _UnionCandRank:
    cand = _unwrap_annotated(cand)
    if _is_wildcard_json_candidate(cand):
        return _WILDCARD_UNION
    orig = get_origin(cand)
    is_enum_or_lit = orig is Literal or (isinstance(cand, type) and issubclass(cand, Enum))
    if isinstance(raw, bool):
        return _UnionCandRank(0) if is_enum_or_lit else (_UnionCandRank(1) if cand is bool else _UnionCandRank(5))
    if isinstance(raw, int):
        return (
            _UnionCandRank(0)
            if is_enum_or_lit
            else (_UnionCandRank(1) if cand is int else (_UnionCandRank(2) if cand is float else _UnionCandRank(5)))
        )
    if isinstance(raw, float):
        return _UnionCandRank(0) if is_enum_or_lit else (_UnionCandRank(1) if cand is float else _UnionCandRank(5))
    if isinstance(raw, str):
        str_ranks: dict[object, int] = {TaskId: 1, EventId: 1, ModuleId: 2, HostPath: 3, str: 4, bytes: 5}
        return _UnionCandRank(0 if is_enum_or_lit else str_ranks.get(cand, 6))
    if isinstance(raw, cabc.Mapping):
        if _is_dataclass_or_generic_dc(cand):
            return _UnionCandRank(0)
        if orig in (dict, cabc.Mapping, Mapping) and len(get_args(cand)) >= 2:
            k_arg, v_arg = get_args(cand)[0], get_args(cand)[1]
            v_spec = _type_specificity_tuple(v_arg)
            if k_arg is not str:
                return _UnionCandRank(1, _map_key_specificity_rank(k_arg), v_spec.major, v_spec.minor)
            return _WILDCARD_UNION if v_spec.major >= 9 else _UnionCandRank(2, v_spec.major, v_spec.minor, v_spec.sub)
        return _UnionCandRank(4)
    if isinstance(raw, (list, tuple, frozenset)):
        if _is_explicit_empty_tuple_type(cand):
            return _UnionCandRank(1)
        if is_enum_or_lit:
            return _UnionCandRank(0)
        if cand is frozenset or orig is frozenset:
            args = get_args(cand)
            es = _type_specificity_tuple(args[0]) if args else _TypeSpecRank(5, 0, 0)
            return _UnionCandRank(2, es.major, es.minor, es.sub)
        args = get_args(cand)
        if orig is tuple and args and (len(args) != 2 or args[1] is not Ellipsis):
            elem_specs = [_type_specificity_tuple(a) for a in args]
            best = min(elem_specs, default=_TypeSpecRank(5, 0, 0))
            return _WILDCARD_UNION if best.major >= 9 else _UnionCandRank(1, best.major, best.minor, sum(s.major for s in elem_specs))
        if orig in (tuple, list, cabc.Sequence, Sequence) and args:
            es = _type_specificity_tuple(args[0])
            return _WILDCARD_UNION if es.major >= 9 else _UnionCandRank(3, es.major, es.minor, es.sub)
        return _UnionCandRank(5, 5)
    return _UnionCandRank(1)


def _canonical_map_key_str(encoded_val: JsonValue) -> str:
    if isinstance(encoded_val, str):
        return encoded_val
    return json.dumps(encoded_val, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _decode_map_key(
    key_tp: object,
    raw_key: object,
    *,
    path: str,
    depth: int,
    localns: Optional[Mapping[str, object]],
) -> object:
    key_tp = _resolve_schema_refs(key_tp, localns)
    if type(raw_key) is not str:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected plain string map key at {path}")
    _check_str_valid_utf8(raw_key, path=path)
    if _is_untyped_wildcard(key_tp) or key_tp is str:
        return raw_key
    origin = get_origin(key_tp)
    if origin in (Union, UnionType):
        _validate_map_key_schema(key_tp, set(), localns)
        ordered = sorted(
            (a for a in get_args(key_tp) if a is not type(None)),
            key=lambda a: _rank_map_key_candidate(_resolve_schema_refs(a, localns)),
        )
        for branch in ordered:
            try:
                return _decode_map_key(branch, raw_key, path=path, depth=depth, localns=localns)
            except (YscbError, ValueError, TypeError, OverflowError):
                continue
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Map key {raw_key!r} at {path} did not match union {key_tp}")
    if origin is Literal:
        matched_lits = [lit for lit in get_args(key_tp) if _canonical_map_key_str(DataclassCodec.encode(lit)) == raw_key]
        if len(matched_lits) == 1:
            return matched_lits[0]
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid literal map key {raw_key!r} at {path}")
    if isinstance(key_tp, type) and issubclass(key_tp, Enum):
        matched = [m for enc_v, m in _get_enum_table(key_tp) if _canonical_map_key_str(enc_v) == raw_key]
        if len(matched) > 1:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Ambiguous enum map key {raw_key!r} for {key_tp.__name__} at {path}")
        if len(matched) == 1:
            return matched[0]
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid enum key {raw_key!r} at {path}")
    if key_tp is bool:
        if raw_key in ("true", "false"):
            return raw_key == "true"
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid canonical bool key {raw_key!r} at {path}")
    if key_tp is int:
        if len(raw_key) > 20 or _CANONICAL_INT_KEY_RE.fullmatch(raw_key) is None:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid canonical int key {raw_key!r} at {path}")
        return _assert_int64_range(int(raw_key), path=path)
    if key_tp in (ModuleId, TaskId, EventId, HostPath):
        return _decode_by_type(key_tp, raw_key, path=path, depth=depth, localns=localns)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported mapping key type {key_tp} at {path}")


def _strict_json_equals(expected: JsonValue, actual: JsonValue) -> bool:
    if expected is None or actual is None:
        return expected is actual
    if isinstance(expected, bool) or isinstance(actual, bool):
        return isinstance(expected, bool) and isinstance(actual, bool) and expected is actual
    if isinstance(expected, float) or isinstance(actual, float):
        return isinstance(expected, float) and isinstance(actual, float) and expected == actual
    if isinstance(expected, int) or isinstance(actual, int):
        return isinstance(expected, int) and isinstance(actual, int) and expected == actual
    if isinstance(expected, str) or isinstance(actual, str):
        return isinstance(expected, str) and isinstance(actual, str) and expected == actual
    if isinstance(expected, cabc.Mapping) and isinstance(actual, cabc.Mapping):
        return set(expected.keys()) == set(actual.keys()) and all(
            _strict_json_equals(expected[k], actual[k]) for k in expected
        )
    if isinstance(expected, cabc.Sequence) and isinstance(actual, cabc.Sequence):
        return len(expected) == len(actual) and all(_strict_json_equals(a, b) for a, b in zip(expected, actual))
    return False


def _get_enum_table(tp: type[Enum]) -> tuple[tuple[JsonValue, Enum], ...]:
    with DataclassCodec._CACHE.lock:
        cached = DataclassCodec._CACHE.enum_tables.get(tp)
    if cached is None:
        cached = tuple((DataclassCodec.encode(m.value), m.name) for m in tp)
        with DataclassCodec._CACHE.lock:
            DataclassCodec._CACHE.enum_tables[tp] = cached
    return tuple((enc_v, tp[m_name]) for enc_v, m_name in cached)


def _decode_enum(tp: type[Enum], raw: JsonValue, *, path: str, depth: int) -> Enum:
    if isinstance(raw, Enum):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unencoded Enum forbidden at {path}")
    validated_raw = _validate_json_value(raw, path=path, depth=depth)
    for enc_val, member in _get_enum_table(tp):
        if _strict_json_equals(enc_val, validated_raw):
            return member
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid enum value {raw!r} for {tp.__name__} at {path}")


def _compile_scalar_plan(tp: type[object]) -> Optional[DecodeFn]:
    if issubclass(tp, Enum):
        enum_ref = weakref.ref(tp)

        def _dec_enum(raw: JsonValue, path: str, depth: int) -> object:
            cls_obj = enum_ref()
            if cls_obj is None:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unloaded Enum type at {path}")
            return _decode_enum(cls_obj, raw, path=path, depth=depth)

        return _dec_enum
    if tp in (ModuleId, TaskId, EventId, HostPath):
        def _dec_vo(raw: JsonValue, path: str) -> object:
            if type(raw) is not str:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected string at {path} for {tp.__name__}")
            checked_raw = _check_str_valid_utf8(raw, path=path)
            try:
                return tp(checked_raw)
            except (ValueError, TypeError, OSError) as exc:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid {tp.__name__} at {path}: {safe_exception_summary(exc)}") from exc
        return _as_leaf_plan(_dec_vo)
    if tp is bytes:
        def _dec_bytes(raw: JsonValue, path: str) -> bytes:
            if type(raw) is not str:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected base64 string for bytes at {path}")
            try:
                decoded = base64.b64decode(raw.encode("ascii"), validate=True)
            except (ValueError, binascii.Error) as exc:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid base64 bytes at {path}: {safe_exception_summary(exc)}") from exc
            if base64.b64encode(decoded).decode("ascii") != raw:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Non-canonical base64 padding at {path}")
            return decoded
        return _as_leaf_plan(_dec_bytes)
    if tp is bool:
        def _dec_bool(raw: JsonValue, path: str) -> bool:
            if type(raw) is not bool:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected bool at {path}")
            return raw
        return _as_leaf_plan(_dec_bool)
    if tp is int:
        def _dec_int(raw: JsonValue, path: str) -> int:
            if type(raw) is not int:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected int at {path}")
            return _assert_int64_range(raw, path=path)
        return _as_leaf_plan(_dec_int)
    if tp is float:
        def _dec_float(raw: JsonValue, path: str) -> float:
            if type(raw) not in (int, float):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected float at {path}")
            if type(raw) is int:
                _assert_int64_range(raw, path=path)
            val_f = float(raw)
            if not math.isfinite(val_f):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Non-finite float at {path}")
            return 0.0 if val_f == 0.0 else val_f
        return _as_leaf_plan(_dec_float)
    if tp is str:
        def _dec_str(raw: JsonValue, path: str) -> str:
            if type(raw) is not str:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected str at {path}")
            return _check_str_valid_utf8(raw, path=path)
        return _as_leaf_plan(_dec_str)
    return None


def _build_mro_tv_maps(dc_cls: type[object], initial_tv_map: Mapping[object, object]) -> dict[type[object], dict[object, object]]:
    per_cls: dict[type[object], dict[object, object]] = {dc_cls: dict(initial_tv_map)}
    for cls in dc_cls.__mro__:
        own_map = per_cls.get(cls, {})
        raw_bases = cls.__dict__.get("__orig_bases__", ())
        if not isinstance(raw_bases, tuple):
            continue
        for orig_base in raw_bases:
            b_orig = get_origin(orig_base)
            if not isinstance(b_orig, type):
                continue
            b_params = b_orig.__dict__.get("__parameters__", ())
            if not isinstance(b_params, tuple):
                continue
            b_args = tuple(_substitute_typevars(a, own_map) for a in get_args(orig_base))
            target_map = per_cls.setdefault(b_orig, {})
            for p_var, arg_tp in zip(b_params, b_args):
                target_map.setdefault(p_var, arg_tp)
    return per_cls


def _resolve_single_class_hints(
    cls: type[object],
    own_anns: Mapping[str, object],
    own_lns: dict[str, object],
) -> dict[str, object]:
    probe = type(cls.__name__, (), {"__annotations__": dict(own_anns), "__module__": cls.__module__})
    mod = sys.modules.get(cls.__module__)
    globalns = mod.__dict__ if mod is not None else own_lns
    try:
        return get_type_hints(probe, globalns=globalns, localns=own_lns, include_extras=True)
    except NameError:
        _populate_active_stack_locals(cls.__qualname__, own_lns)
    try:
        return get_type_hints(probe, globalns=globalns, localns=own_lns, include_extras=True)
    except NameError as exc:
        raise _UnresolvedLocalHintError(f"Unresolvable type hint on {cls.__name__}: {safe_exception_summary(exc)}") from exc


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
        if tp.__bound__ is not None and _type_tree_any(tp.__bound__, pred, walk_seen):
            return True
        return any(_type_tree_any(c, pred, walk_seen) for c in tp.__constraints__)
    origin = get_origin(tp)
    if origin is not None and pred(origin):
        return True
    return any(_type_tree_any(a, pred, walk_seen) for a in get_args(tp))


def _obj_in_module_prefix(obj: object, prefix: str, dot_pkg: str) -> bool:
    if isinstance(obj, (type, types.FunctionType, TypeVar)):
        mod_nm = obj.__module__
        return isinstance(mod_nm, str) and (mod_nm == prefix or mod_nm.startswith(dot_pkg))
    cls_mod = type(obj).__module__
    return cls_mod == prefix or cls_mod.startswith(dot_pkg)


def _node_mentions_module_prefix(node: object, prefix: str, dot_pkg: str) -> bool:
    if isinstance(node, ForwardRef):
        fmod = node.__forward_module__
        return fmod is None or fmod == prefix or fmod.startswith(dot_pkg)
    if isinstance(node, (type, Enum, TypeVar)):
        return _obj_in_module_prefix(node, prefix, dot_pkg)
    return type(node).__module__ not in ("builtins", "typing", "types") and _obj_in_module_prefix(node, prefix, dot_pkg)


def _type_mentions_module_prefix(tp: object, prefix: str) -> bool:
    clean_p = prefix.strip(".")
    if not clean_p:
        return False
    dot_pkg = f"{clean_p}."
    return _type_tree_any(tp, lambda node: _node_mentions_module_prefix(node, clean_p, dot_pkg))


def _resolve_node_dataclass(node: object) -> Optional[type[object]]:
    if isinstance(node, ForwardRef):
        try:
            resolved = _resolve_forward_ref(node, localns=None)
        except YscbError:
            return None
        return _resolve_node_dataclass(resolved)
    if node in _SCALAR_VO_TYPES:
        return None
    orig = get_origin(node)
    if isinstance(orig, type) and orig not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(orig):
        return orig
    return node if isinstance(node, type) and dataclasses.is_dataclass(node) else None


def _dataclass_reaches_target(cur_dc: type[object], target_dc: type[object], seen: set[type[object]]) -> bool:
    if cur_dc is target_dc:
        return True
    if cur_dc in seen:
        return False
    seen.add(cur_dc)
    init_names = {f.name for f in dataclasses.fields(cur_dc) if f.init}
    try:
        hints = get_type_hints(cur_dc)
    except Exception:
        return True
    return any(
        fname in init_names
        and _type_tree_any(
            tp,
            lambda node: (dc := _resolve_node_dataclass(node)) is not None
            and _dataclass_reaches_target(dc, target_dc, seen),
        )
        for fname, tp in hints.items()
    )


def _is_recursive_dataclass_node(node: object) -> bool:
    dc_cls = _resolve_node_dataclass(node)
    if dc_cls is None:
        return False
    _compile_mro_base_metadata(dc_cls, None)
    return _is_self_referential_dataclass(dc_cls)


def _is_uncacheable_local_or_unbound_node(node: object) -> bool:
    if isinstance(node, ForwardRef):
        return node.__forward_arg__ != "JsonValue"
    if isinstance(node, type):
        return ".<locals>." in node.__qualname__
    return ".<locals>." in type(node).__qualname__


def _lookup_cached_dc_hints(
    dc_cls: type[object],
) -> Optional[tuple[tuple[tuple[str, bool], ...], dict[str, tuple[object, dict[str, object]]]]]:
    with DataclassCodec._CACHE.lock:
        cached_w = DataclassCodec._CACHE.dc_hints.get(dc_cls)
    if cached_w is None:
        return None
    rehyd_pairs = {k: _rehydrate_type(wt) for k, wt in cached_w[1].items()}
    if not all(ok for ok, _ in rehyd_pairs.values()):
        return None
    return (cached_w[0], {k: (vt, {}) for k, (_, vt) in rehyd_pairs.items()})


def _compile_mro_base_metadata(
    dc_cls: type[object],
    parent_localns: Optional[Mapping[str, object]],
) -> tuple[tuple[tuple[str, bool], ...], dict[str, tuple[object, dict[str, object]]]]:
    is_local_cls = ".<locals>." in dc_cls.__qualname__
    act_hints = DataclassCodec._CACHE.active.hints if parent_localns is None else None
    if act_hints is not None and dc_cls in act_hints:
        return act_hints[dc_cls]
    if parent_localns is None and not is_local_cls:
        rehyd = _lookup_cached_dc_hints(dc_cls)
        if rehyd is not None:
            if act_hints is not None:
                act_hints[dc_cls] = rehyd
            return rehyd
    init_specs = tuple(
        (f.name, f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING)
        for f in dataclasses.fields(dc_cls)
        if f.init
    )
    init_names = {fname for fname, _req in init_specs}
    per_cls_tv = _build_mro_tv_maps(dc_cls, {})
    raw_fields: dict[str, tuple[object, dict[str, object]]] = {}
    for cls in reversed(dc_cls.__mro__):
        own_anns = cls.__dict__.get("__annotations__")
        if cls is object or not isinstance(own_anns, Mapping) or not own_anns:
            continue
        field_anns = {k: v for k, v in own_anns.items() if k in init_names}
        if not field_anns:
            continue
        own_lns: dict[str, object] = dict(parent_localns) if (cls is dc_cls and parent_localns is not None) else {}
        _populate_qualname_and_closure_ns(cls.__module__, cls.__qualname__, cls, own_lns)
        cls_hints = _resolve_single_class_hints(cls, field_anns, own_lns)
        own_tv = per_cls_tv.get(cls, {})
        for fname in (fn for fn in field_anns.keys() if fn in cls_hints):
            sub_tp = _substitute_typevars(cls_hints[fname], own_tv)
            kept_lns = (
                {k: v for k, v in own_lns.items() if v is not dc_cls}
                if (is_local_cls or _needs_localns_for_forward_ref(sub_tp))
                else {}
            )
            raw_fields[fname] = (sub_tp, kept_lns)
    has_cycle = any(
        _type_tree_any(
            sub_tp,
            lambda node: (dc := _resolve_node_dataclass(node)) is not None
            and _dataclass_reaches_target(dc, dc_cls, set()),
        )
        for sub_tp, _lns in raw_fields.values()
    )
    compiled = (init_specs, raw_fields)
    if act_hints is not None:
        act_hints[dc_cls] = compiled
    if parent_localns is None and not is_local_cls:
        with DataclassCodec._CACHE.lock:
            if has_cycle:
                DataclassCodec._CACHE.recursive_dcs.add(dc_cls)
            elif not any(lns for _st, lns in raw_fields.values()):
                DataclassCodec._CACHE.dc_hints[dc_cls] = (
                    init_specs,
                    {k: _dehydrate_type(st) for k, (st, _lns) in raw_fields.items()},
                )
    return compiled


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


def _type_satisfies_bound(arg_tp: object, bound: object) -> bool:
    arg_u = _unwrap_annotated(arg_tp)
    bnd_u = _unwrap_annotated(bound)
    if bnd_u is object:
        return True
    if arg_u is object:
        return False
    if isinstance(arg_u, TypeVar):
        if arg_u is bnd_u:
            return True
        if arg_u.__constraints__:
            return all(_type_satisfies_bound(c, bnd_u) for c in arg_u.__constraints__)
        return arg_u.__bound__ is not None and _type_satisfies_bound(arg_u.__bound__, bnd_u)
    if get_origin(arg_u) in (Union, UnionType):
        return all(_type_satisfies_bound(b, bnd_u) for b in get_args(arg_u))
    if get_origin(bnd_u) in (Union, UnionType):
        return any(_type_satisfies_bound(arg_u, b) for b in get_args(bnd_u))
    a_cls = get_origin(arg_u) or arg_u
    b_cls = get_origin(bnd_u) or bnd_u
    if b_cls is int and a_cls is bool:
        return False
    if b_cls is float and a_cls in (int, float):
        return True
    return isinstance(a_cls, type) and isinstance(b_cls, type) and issubclass(a_cls, b_cls)


def _validate_generic_dc_type_args(origin: type[object], args: tuple[object, ...]) -> None:
    params = _generic_type_params(origin)
    if params and len(args) != len(params):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Generic arity mismatch for {origin.__name__}: {args}")
    for p_var, arg_tp in zip(params, args):
        if not isinstance(p_var, TypeVar):
            continue
        if p_var.__constraints__ and not any(
            _unwrap_annotated(arg_tp) == _unwrap_annotated(c)
            or (isinstance(arg_tp, TypeVar) and _type_satisfies_bound(arg_tp, c))
            for c in p_var.__constraints__
        ):
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"Type argument {arg_tp} violates TypeVar constraints on {origin.__name__}",
            )
        if p_var.__bound__ is not None and not _type_satisfies_bound(arg_tp, p_var.__bound__):
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"Type argument {arg_tp} violates TypeVar bound {p_var.__bound__} on {origin.__name__}",
            )


def _finite_wire_tokens(branch: object) -> Optional[frozenset[str]]:
    if get_origin(branch) is Literal:
        raw_vals = tuple(v.value if isinstance(v, Enum) else v for v in get_args(branch))
    elif isinstance(branch, type) and issubclass(branch, Enum):
        raw_vals = tuple(m.value for m in branch)
    else:
        return None
    tokens: list[str] = []
    for rv in raw_vals:
        enc = DataclassCodec.encode(rv)
        tokens.append(json.dumps(enc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
    return frozenset(tokens)


def _wire_json_kind_of_encoded(enc: JsonValue) -> str:
    if enc is None:
        return "null"
    if type(enc) is bool:
        return "bool"
    if type(enc) is int:
        return "int"
    if type(enc) is float:
        return "float"
    if type(enc) is str:
        return "str"
    return "object" if isinstance(enc, cabc.Mapping) else "array"


def _wire_json_kinds(tp: object) -> set[str]:
    all_kinds = {"null", "bool", "int", "float", "str", "array", "object"}
    cur = _unwrap_annotated(tp)
    if _is_wildcard_elem(cur) or isinstance(cur, TypeVar):
        return all_kinds
    if cur is type(None):
        return {"null"}
    if cur is bool:
        return {"bool"}
    if cur is int:
        return {"int"}
    if cur is float:
        return {"int", "float"}
    if cur in {str, bytes, ModuleId, TaskId, EventId, HostPath}:
        return {"str"}
    orig = get_origin(cur)
    if orig in (Union, UnionType):
        return {k for a in get_args(cur) for k in _wire_json_kinds(a)}
    if orig is Literal:
        return {_wire_json_kind_of_encoded(DataclassCodec.encode(v.value if isinstance(v, Enum) else v)) for v in get_args(cur)}
    if isinstance(cur, type) and issubclass(cur, Enum):
        return {_wire_json_kind_of_encoded(DataclassCodec.encode(m.value)) for m in cur}
    if _is_dataclass_or_generic_dc(cur) or orig in (dict, Mapping, cabc.Mapping) or cur in (dict, Mapping, cabc.Mapping, JsonObject, MutableJsonObject):
        return {"object"}
    if orig in (list, Sequence, cabc.Sequence, tuple, frozenset) or cur in (list, Sequence, cabc.Sequence, tuple, Tuple, frozenset):
        return {"array"}
    return all_kinds


def _extract_dc_and_args(tp: object) -> tuple[type[object], tuple[object, ...]]:
    cur = _unwrap_annotated(tp)
    orig = get_origin(cur)
    if isinstance(orig, type) and orig not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(orig):
        return (orig, get_args(cur))
    if isinstance(cur, type) and cur not in _SCALAR_VO_TYPES and dataclasses.is_dataclass(cur):
        return (cur, ())
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected dataclass type, got {tp}")


@dataclasses.dataclass(frozen=True, slots=True)
class _DcEnvelopeSchema:
    required: set[str]
    known: set[str]
    field_types: dict[str, object]


def _dataclass_envelope_fields(
    dc_cls: type[object],
    args: tuple[object, ...],
) -> _DcEnvelopeSchema:
    tv_map = dict(zip(_generic_type_params(dc_cls), args)) if args else {}
    try:
        specs, base_fields = _compile_mro_base_metadata(dc_cls, None)
        ftypes = {
            fn: _resolve_schema_refs(_substitute_typevars(ft, tv_map) if tv_map else ft, f_lns)
            for fn, (ft, f_lns) in base_fields.items()
        }
        req = {fn for fn, is_req in specs if is_req}
        known = {fn for fn, _is_req in specs}
        return _DcEnvelopeSchema(req, known, ftypes)
    except _UnresolvedLocalHintError:
        init_f = [f for f in dataclasses.fields(dc_cls) if f.init]
        req = {f.name for f in init_f if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING}
        known = {f.name for f in init_f}
        ftypes = {
            f.name: (
                _substitute_typevars(f.type, tv_map)
                if (tv_map and not isinstance(f.type, str))
                else (object if isinstance(f.type, str) else f.type)
            )
            for f in init_f
        }
        return _DcEnvelopeSchema(req, known, ftypes)


def _dataclasses_overlap_on_wire(b1: object, b2: object, pair_seen: set[object]) -> bool:
    dc1, args1 = _extract_dc_and_args(b1)
    dc2, args2 = _extract_dc_and_args(b2)
    if not _try_mark_seen(pair_seen, ((dc1, args1), (dc2, args2))):
        return True
    env1 = _dataclass_envelope_fields(dc1, args1)
    env2 = _dataclass_envelope_fields(dc2, args2)
    common_req = env1.required | env2.required
    if not (common_req <= (env1.known & env2.known)):
        return False
    return all(
        _wire_domains_overlap(env1.field_types.get(k, object), env2.field_types.get(k, object), pair_seen)
        for k in common_req
    )


def _wire_domains_overlap(t1: object, t2: object, pair_seen: set[object]) -> bool:
    u1, u2 = _unwrap_annotated(t1), _unwrap_annotated(t2)
    for idx_tv, cand_tv in ((1, u1), (2, u2)):
        if isinstance(cand_tv, TypeVar):
            other = u2 if idx_tv == 1 else u1
            if cand_tv.__constraints__:
                return any(_wire_domains_overlap(c, other, pair_seen) for c in cand_tv.__constraints__)
            if cand_tv.__bound__ is not None:
                return _wire_domains_overlap(cand_tv.__bound__, other, pair_seen)
            return True
    if _is_wildcard_elem(u1) or _is_wildcard_elem(u2):
        return True
    if get_origin(u1) in (Union, UnionType):
        return any(_wire_domains_overlap(a, u2, pair_seen) for a in get_args(u1))
    if get_origin(u2) in (Union, UnionType):
        return any(_wire_domains_overlap(u1, a, pair_seen) for a in get_args(u2))
    tok1, tok2 = _finite_wire_tokens(u1), _finite_wire_tokens(u2)
    if tok1 is not None and tok2 is not None:
        return bool(tok1 & tok2)
    str_vos = {ModuleId, HostPath, TaskId, EventId}
    if u1 in str_vos and u2 in str_vos:
        return u1 is u2 or {u1, u2} == {TaskId, EventId}
    if _is_dataclass_or_generic_dc(u1) and _is_dataclass_or_generic_dc(u2):
        return _dataclasses_overlap_on_wire(u1, u2, pair_seen)
    return bool(_wire_json_kinds(u1) & _wire_json_kinds(u2))


def _var_seq_elem_type(tp: object) -> Optional[object]:
    orig = get_origin(tp)
    args = get_args(tp)
    if orig in (list, Sequence, cabc.Sequence, frozenset) and len(args) == 1:
        return _unwrap_annotated(args[0])
    if orig is tuple and len(args) == 2 and args[1] is Ellipsis:
        return _unwrap_annotated(args[0])
    return None


def _fixed_tuple_elem_types(tp: object) -> Optional[tuple[object, ...]]:
    if get_origin(tp) is not tuple or _is_explicit_empty_tuple_type(tp):
        return None
    args = get_args(tp)
    if not args or (len(args) == 2 and args[1] is Ellipsis):
        return None
    return tuple(_unwrap_annotated(a) for a in args)


def _finite_str_collides_with_vo(fin_tp: object, vo_tp: object) -> bool:
    if vo_tp not in {ModuleId, TaskId, EventId, HostPath}:
        return False
    if get_origin(fin_tp) is Literal:
        raw_vals = tuple(v.value if isinstance(v, Enum) else v for v in get_args(fin_tp))
    elif isinstance(fin_tp, type) and issubclass(fin_tp, Enum):
        raw_vals = tuple(m.value for m in fin_tp)
    else:
        return False
    for raw_item in raw_vals:
        enc = DataclassCodec.encode(raw_item)
        if type(enc) is str and _try_parse_vo_str(vo_tp, enc):
            return True
    return False


def _try_parse_vo_str(vo_tp: object, raw_str: str) -> bool:
    if not callable(vo_tp):
        return False
    try:
        vo_tp(raw_str)
        return True
    except (ValueError, TypeError, OSError):
        return False


_SCALAR_MAP_KEY_TYPES: frozenset[type[object]] = frozenset({bool, int, ModuleId, TaskId, EventId, HostPath})
_OVERLAPPING_SCALAR_KEY_PAIRS: frozenset[frozenset[type[object]]] = frozenset(
    {
        frozenset({bool, ModuleId}),
        frozenset({int, ModuleId}),
        frozenset({TaskId, EventId}),
    }
)


def _unwrap_enum_leaf(val: object) -> object:
    depth = 0
    while isinstance(val, Enum):
        depth += 1
        if depth > _MAX_CODEC_DEPTH:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Maximum Enum nesting depth exceeded.")
        val = val.value
    return val


def _encode_finite_map_key_item(item: object, tp: object, *, is_enum_member: bool) -> tuple[str, object]:
    leaf = _unwrap_enum_leaf(item)
    if is_enum_member or isinstance(item, Enum):
        tok = _canonical_map_key_str(DataclassCodec.encode(leaf))
        return (_check_str_valid_utf8(tok, path="$map_key_schema"), leaf)
    if type(item) is bool:
        return ("true" if item else "false", item)
    if type(item) is int:
        return (str(_assert_int64_range(item, path="$map_key_schema")), item)
    if type(item) is str:
        return (_check_str_valid_utf8(item, path="$map_key_schema"), item)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported map key member {item!r} in {tp!r}")


def _finite_map_key_entries(tp: object) -> Optional[tuple[tuple[str, object], ...]]:
    cur = _unwrap_annotated(tp)
    if get_origin(cur) is Literal:
        _validate_literal_schema_args(cur, get_args(cur))
        raw_args = get_args(cur)
        is_enum = False
    elif isinstance(cur, type) and issubclass(cur, Enum):
        raw_args = tuple(cur)
        is_enum = True
    else:
        return None
    if not raw_args:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Empty finite map key schema {tp!r}")
    entries: list[tuple[str, object]] = []
    seen_tokens: set[str] = set()
    for item in raw_args:
        tok, leaf = _encode_finite_map_key_item(item, tp, is_enum_member=is_enum)
        if tok in seen_tokens:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Duplicate canonical map key {tok!r} in {tp!r}")
        seen_tokens.add(tok)
        entries.append((tok, leaf))
    return tuple(entries)


def _finite_key_collides_with_scalar(
    entries: tuple[tuple[str, object], ...],
    scalar_tp: object,
    *,
    allow_refinement: bool,
) -> bool:
    for ks, leaf in entries:
        if scalar_tp is bool and ks in ("true", "false") and not (allow_refinement and type(leaf) is bool):
            return True
        is_c_int = len(ks) <= 20 and _CANONICAL_INT_KEY_RE.fullmatch(ks) is not None and (INT64_MIN <= int(ks) <= INT64_MAX)
        if scalar_tp is int and is_c_int and not (allow_refinement and type(leaf) is int):
            return True
        if scalar_tp in {ModuleId, TaskId, EventId, HostPath} and _try_parse_vo_str(scalar_tp, ks):
            return True
    return False


def _map_key_pair_conflicts(raw_k1: object, raw_k2: object, *, allow_refinement: bool) -> bool:
    u1, u2 = _unwrap_annotated(raw_k1), _unwrap_annotated(raw_k2)
    for idx_u, cand_u in ((1, u1), (2, u2)):
        other = u2 if idx_u == 1 else u1
        if isinstance(cand_u, TypeVar):
            if cand_u.__constraints__:
                return any(_map_key_pair_conflicts(c, other, allow_refinement=allow_refinement) for c in cand_u.__constraints__)
            if cand_u.__bound__ is not None:
                return _map_key_pair_conflicts(cand_u.__bound__, other, allow_refinement=allow_refinement)
            return True
        if get_origin(cand_u) in (Union, UnionType):
            return any(_map_key_pair_conflicts(a, other, allow_refinement=allow_refinement) for a in get_args(cand_u))
    if u1 == u2:
        return not allow_refinement
    if u1 is str or u2 is str or _is_untyped_wildcard(u1) or _is_untyped_wildcard(u2):
        return not allow_refinement
    e1, e2 = _finite_map_key_entries(u1), _finite_map_key_entries(u2)
    if e1 is not None and e2 is not None:
        return bool({k for k, _ in e1} & {k for k, _ in e2})
    if e1 is not None and u2 in _SCALAR_MAP_KEY_TYPES:
        return _finite_key_collides_with_scalar(e1, u2, allow_refinement=allow_refinement)
    if e2 is not None and u1 in _SCALAR_MAP_KEY_TYPES:
        return _finite_key_collides_with_scalar(e2, u1, allow_refinement=allow_refinement)
    if u1 in _SCALAR_MAP_KEY_TYPES and u2 in _SCALAR_MAP_KEY_TYPES:
        return frozenset({u1, u2}) in _OVERLAPPING_SCALAR_KEY_PAIRS
    return True


def _is_typed_mapping_branch(tp: object) -> bool:
    return get_origin(tp) in (dict, Mapping, cabc.Mapping) and not _is_wildcard_json_candidate(tp)


def _containers_conflict_in_lattice(b1: object, b2: object, pair_seen: set[object]) -> bool:
    e1, e2 = _var_seq_elem_type(b1), _var_seq_elem_type(b2)
    ft1, ft2 = _fixed_tuple_elem_types(b1), _fixed_tuple_elem_types(b2)
    if e1 is not None and e2 is not None:
        return (
            e1 == e2
            or _type_specificity_tuple(e1) == _type_specificity_tuple(e2)
            or _union_branches_conflict(e1, e2, pair_seen)
        )
    if (e1 is not None and ft2 is not None and any(_wire_domains_overlap(e1, x, pair_seen) for x in ft2)) or (
        e2 is not None and ft1 is not None and any(_wire_domains_overlap(e2, x, pair_seen) for x in ft1)
    ):
        return True
    if ft1 is not None and ft2 is not None and len(ft1) == len(ft2):
        return ft1 == ft2 or any(_union_branches_conflict(x, y, pair_seen) for x, y in zip(ft1, ft2) if x != y)
    if (_is_dataclass_or_generic_dc(b1) and _is_typed_mapping_branch(b2)) or (
        _is_dataclass_or_generic_dc(b2) and _is_typed_mapping_branch(b1)
    ):
        return True
    a1, a2 = get_args(b1), get_args(b2)
    if _is_typed_mapping_branch(b1) and _is_typed_mapping_branch(b2) and len(a1) == 2 and len(a2) == 2:
        k1, v1 = _unwrap_annotated(a1[0]), _unwrap_annotated(a1[1])
        k2, v2 = _unwrap_annotated(a2[0]), _unwrap_annotated(a2[1])
        if k1 != k2:
            return _map_key_pair_conflicts(k1, k2, allow_refinement=False)
        return v1 == v2 or _union_branches_conflict(v1, v2, pair_seen)
    return False


def _seq_or_wildcard_elem(tp: object) -> Optional[object]:
    elem = _var_seq_elem_type(tp)
    if elem is not None:
        return elem
    if tp in (list, Sequence, cabc.Sequence, tuple, Tuple, frozenset):
        return object
    if get_origin(tp) in (list, Sequence, cabc.Sequence, frozenset) and not get_args(tp):
        return object
    return None


def _map_or_wildcard_val(tp: object) -> Optional[object]:
    orig = get_origin(tp)
    args = get_args(tp)
    if orig in (dict, Mapping, cabc.Mapping):
        return _unwrap_annotated(args[1]) if len(args) == 2 else object
    if tp in (dict, Mapping, cabc.Mapping, JsonObject, MutableJsonObject):
        return object
    return None


def _is_universal_json_wildcard(tp: object) -> bool:
    if _is_untyped_wildcard(tp):
        return True
    if isinstance(tp, ForwardRef) and tp.__forward_arg__ in ("JsonValue", "object"):
        return True
    return isinstance(tp, TypeVar) and not tp.__constraints__ and tp.__bound__ is None


def _type_reaches_bytes(raw_tp: object, seen: set[object]) -> bool:
    tp = _unwrap_annotated(raw_tp)
    if tp is bytes:
        return True
    if isinstance(tp, TypeVar):
        if tp.__constraints__:
            return any(_type_reaches_bytes(c, seen) for c in tp.__constraints__)
        return tp.__bound__ is not None and _type_reaches_bytes(tp.__bound__, seen)
    if isinstance(tp, ForwardRef):
        if tp.__forward_arg__ in ("JsonValue", "object") or not _try_mark_seen(seen, ("fref", tp)):
            return False
        try:
            return _type_reaches_bytes(_resolve_forward_ref(tp, localns=None), seen)
        except YscbError:
            return False
    if _is_dataclass_or_generic_dc(tp):
        dc_cls, dc_args = _extract_dc_and_args(tp)
        if not _try_mark_seen(seen, ("dc_b", dc_cls, dc_args)):
            return False
        env = _dataclass_envelope_fields(dc_cls, dc_args)
        return any(_type_reaches_bytes(ft, seen) for ft in env.field_types.values())
    return any(_type_reaches_bytes(a, seen) for a in get_args(tp) if a not in (Ellipsis, type(None)))


def _dc_vs_map_bytes_conflict(b1: object, b2: object, pair_seen: set[object]) -> bool:
    for dc_cand, map_cand in ((b1, b2), (b2, b1)):
        mv = _map_or_wildcard_val(map_cand)
        if _is_dataclass_or_generic_dc(dc_cand) and mv is not None:
            env = _dataclass_envelope_fields(*_extract_dc_and_args(dc_cand))
            return any(_branches_have_bytes_text_conflict(ft, mv, pair_seen) for ft in env.field_types.values())
    return False


def _tuple_or_seq_bytes_conflict(b1: object, b2: object, pair_seen: set[object]) -> bool:
    se1, se2 = _seq_or_wildcard_elem(b1), _seq_or_wildcard_elem(b2)
    if se1 is not None and se2 is not None:
        return _branches_have_bytes_text_conflict(se1, se2, pair_seen)
    ft1, ft2 = _fixed_tuple_elem_types(b1), _fixed_tuple_elem_types(b2)
    if se1 is not None and ft2 is not None:
        return any(_branches_have_bytes_text_conflict(se1, x, pair_seen) for x in ft2)
    if se2 is not None and ft1 is not None:
        return any(_branches_have_bytes_text_conflict(x, se2, pair_seen) for x in ft1)
    if ft1 is not None and ft2 is not None and len(ft1) == len(ft2):
        return any(_branches_have_bytes_text_conflict(x, y, pair_seen) for x, y in zip(ft1, ft2))
    return False


def _expand_bound_typevar_bytes_conflict(tv: TypeVar, other: object, pair_seen: set[object]) -> bool:
    if tv.__constraints__:
        return any(_branches_have_bytes_text_conflict(c, other, pair_seen) for c in tv.__constraints__)
    return tv.__bound__ is not None and _branches_have_bytes_text_conflict(tv.__bound__, other, pair_seen)


def _branches_have_bytes_text_conflict(raw_b1: object, raw_b2: object, pair_seen: set[object]) -> bool:
    b1, b2 = _unwrap_annotated(raw_b1), _unwrap_annotated(raw_b2)
    if not _try_mark_seen(pair_seen, ("bytes_txt", b1, b2)):
        return False
    if isinstance(b1, TypeVar) and (b1.__constraints__ or b1.__bound__ is not None):
        return _expand_bound_typevar_bytes_conflict(b1, b2, pair_seen)
    if isinstance(b2, TypeVar) and (b2.__constraints__ or b2.__bound__ is not None):
        return _expand_bound_typevar_bytes_conflict(b2, b1, pair_seen)
    if get_origin(b1) in (Union, UnionType):
        return any(_branches_have_bytes_text_conflict(a, b2, pair_seen) for a in get_args(b1) if a is not type(None))
    if get_origin(b2) in (Union, UnionType):
        return any(_branches_have_bytes_text_conflict(b1, a, pair_seen) for a in get_args(b2) if a is not type(None))
    if (b1 is bytes and "str" in _wire_json_kinds(b2)) or (b2 is bytes and "str" in _wire_json_kinds(b1)):
        return True
    if _is_universal_json_wildcard(b1):
        return _type_reaches_bytes(b2, set())
    if _is_universal_json_wildcard(b2):
        return _type_reaches_bytes(b1, set())
    if _tuple_or_seq_bytes_conflict(b1, b2, pair_seen) or _dc_vs_map_bytes_conflict(b1, b2, pair_seen):
        return True
    mv1, mv2 = _map_or_wildcard_val(b1), _map_or_wildcard_val(b2)
    return mv1 is not None and mv2 is not None and _branches_have_bytes_text_conflict(mv1, mv2, pair_seen)


def _union_branches_conflict(raw_b1: object, raw_b2: object, pair_seen: set[object]) -> bool:
    """Return True when two union branches violate deterministic specificity-lattice resolution."""
    b1, b2 = _unwrap_annotated(raw_b1), _unwrap_annotated(raw_b2)
    if _branches_have_bytes_text_conflict(b1, b2, pair_seen):
        return True
    if _is_wildcard_json_candidate(b1) or _is_wildcard_json_candidate(b2):
        return False
    for idx_tv, cand_tv in ((1, b1), (2, b2)):
        if isinstance(cand_tv, TypeVar):
            other = b2 if idx_tv == 1 else b1
            if cand_tv.__constraints__:
                return any(_union_branches_conflict(c, other, pair_seen) for c in cand_tv.__constraints__)
            if cand_tv.__bound__ is not None:
                return _union_branches_conflict(cand_tv.__bound__, other, pair_seen)
            return True
    tok1, tok2 = _finite_wire_tokens(b1), _finite_wire_tokens(b2)
    if tok1 is not None and tok2 is not None:
        return bool(tok1 & tok2)
    if _finite_str_collides_with_vo(b1, b2) or _finite_str_collides_with_vo(b2, b1):
        return True
    if {b1, b2} == {TaskId, EventId}:
        return True
    if _is_dataclass_or_generic_dc(b1) and _is_dataclass_or_generic_dc(b2):
        return _dataclasses_overlap_on_wire(b1, b2, pair_seen)
    return _containers_conflict_in_lattice(b1, b2, pair_seen)


def _dedup_union_branches(branches: Sequence[object]) -> list[object]:
    uniq: list[object] = []
    for br in branches:
        if not any(br == prev for prev in uniq):
            uniq.append(br)
    return uniq


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


def _resolve_schema_refs(
    tp: object,
    localns: Optional[Mapping[str, object]],
    ref_stack: frozenset[str] = frozenset(),
) -> object:
    cur = _unwrap_annotated(tp)
    while isinstance(cur, ForwardRef):
        if cur.__forward_arg__ == "JsonValue":
            return JsonValue
        if cur.__forward_arg__ in ref_stack:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Cyclic ForwardRef {cur.__forward_arg__!r}")
        ref_stack = ref_stack | {cur.__forward_arg__}
        cur = _unwrap_annotated(_resolve_forward_ref(cur, localns=localns))
    if _is_forbidden_any_type(cur):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "typing.Any is forbidden in DataclassCodec schema.")
    orig = get_origin(cur)
    args = get_args(cur)
    if (
        orig is None
        or orig in (Literal, ClassVar)
        or not args
        or not _type_tree_any(cur, lambda n: isinstance(n, ForwardRef) and n.__forward_arg__ != "JsonValue")
    ):
        return cur
    resolved_args = tuple(
        Ellipsis if a is Ellipsis else _resolve_schema_refs(a, localns, ref_stack) for a in args
    )
    return _rebuild_resolved_generic(orig, resolved_args, cur)


def _assert_unambiguous_union_branches(
    tp: object,
    localns: Optional[Mapping[str, object]] = None,
) -> None:
    resolved_tp = _resolve_schema_refs(tp, localns)
    if _is_wildcard_elem(resolved_tp):
        return
    if get_origin(resolved_tp) not in (Union, UnionType):
        return
    uniq = _dedup_union_branches([_unwrap_annotated(c) for c in get_args(resolved_tp) if c is not type(None)])
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            if _union_branches_conflict(uniq[i], uniq[j], set()):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Ambiguous untagged union branches in {tp}")


def _validate_dc_fields_schema(
    dc_cls: type[object],
    args: tuple[object, ...],
    seen: set[object],
) -> None:
    try:
        _, base_fields = _compile_mro_base_metadata(dc_cls, None)
    except _UnresolvedLocalHintError:
        for f in dataclasses.fields(dc_cls):
            if f.init and not isinstance(f.type, str):
                _validate_declared_type_schema(f.type, seen)
        return
    tv_map = dict(zip(_generic_type_params(dc_cls), args)) if args else {}
    for raw_f_tp, f_lns in base_fields.values():
        f_tp = _substitute_typevars(raw_f_tp, tv_map) if tv_map else raw_f_tp
        _validate_declared_type_schema(f_tp, seen, localns=f_lns or None)


def _is_schema_cached(tp: object) -> bool:
    cache = DataclassCodec._CACHE
    with cache.lock:
        if isinstance(tp, type):
            try:
                return tp in cache.valid_type_schemas
            except TypeError:
                return False
        try:
            wkey = _dehydrate_type(tp)
            if wkey in cache.valid_form_schemas:
                cache.valid_form_schemas.move_to_end(wkey)
                return True
        except TypeError:
            return False
    return False


def _record_schema_cached(tp: object) -> None:
    if (
        _needs_localns_for_forward_ref(tp)
        or _type_tree_any(tp, _is_uncacheable_local_or_unbound_node)
        or _type_tree_any(tp, _is_recursive_dataclass_node)
    ):
        return
    cache = DataclassCodec._CACHE
    with cache.lock:
        if isinstance(tp, type):
            try:
                cache.valid_type_schemas.add(tp)
            except TypeError:
                return
            return
        key_box: list[object] = []

        def _evict_dead_schema(_r: object) -> None:
            if key_box:
                with cache.lock:
                    cache.valid_form_schemas.pop(key_box[0], None)

        try:
            wkey = _dehydrate_type(tp, _evict_dead_schema)
            key_box.append(wkey)
            cache.valid_form_schemas[wkey] = None
            cache.valid_form_schemas.move_to_end(wkey)
            while len(cache.valid_form_schemas) > _PLAN_LRU_LIMIT:
                cache.valid_form_schemas.popitem(last=False)
        except TypeError:
            return


_UNPARAM_SCHEMA_FORMS: tuple[object, ...] = (
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
_SUPPORTED_SCALAR_CLASSES: tuple[type[object], ...] = (
    bool,
    int,
    float,
    str,
    bytes,
    ModuleId,
    TaskId,
    EventId,
    HostPath,
)


def _validate_map_key_union_schema(
    resolved_k: object,
    walk_seen: set[object],
    localns: Optional[Mapping[str, object]],
) -> None:
    branches = get_args(resolved_k)
    if not branches or any(b is type(None) for b in branches):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid nullable or empty map key union {resolved_k!r}")
    for br in branches:
        _validate_map_key_schema(br, walk_seen, localns)
    uniq = _dedup_union_branches([_unwrap_annotated(b) for b in branches])
    for idx_i in range(len(uniq)):
        for idx_j in range(idx_i + 1, len(uniq)):
            if _map_key_pair_conflicts(uniq[idx_i], uniq[idx_j], allow_refinement=True):
                raise YscbError(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"Ambiguous colliding map key union {resolved_k!r}",
                )


def _validate_map_key_schema(
    key_tp: object,
    walk_seen: set[object],
    localns: Optional[Mapping[str, object]],
) -> None:
    resolved_k = _resolve_schema_refs(key_tp, localns)
    if _is_forbidden_any_type(resolved_k):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "typing.Any is forbidden in map key schema.")
    if _is_untyped_wildcard(resolved_k) or resolved_k is str or resolved_k in _SCALAR_MAP_KEY_TYPES:
        return
    if isinstance(resolved_k, TypeVar):
        for c in resolved_k.__constraints__:
            _validate_map_key_schema(c, walk_seen, localns)
        if resolved_k.__bound__ is not None:
            _validate_map_key_schema(resolved_k.__bound__, walk_seen, localns)
        return
    if get_origin(resolved_k) in (Union, UnionType):
        _validate_map_key_union_schema(resolved_k, walk_seen, localns)
        return
    if _finite_map_key_entries(resolved_k) is not None:
        return
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported mapping key schema {key_tp!r}")


def _validate_literal_schema_args(tp: object, args: tuple[object, ...]) -> None:
    if not args:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Empty Literal schema {tp!r}")
    for lit in args:
        if lit is None or isinstance(lit, (bool, Enum)):
            continue
        if type(lit) is int:
            _assert_int64_range(lit, path="$schema")
        elif type(lit) is float and math.isfinite(lit):
            continue
        elif type(lit) is str:
            _check_str_valid_utf8(lit, path="$schema")
        else:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported Literal member {lit!r} in {tp!r}")


def _validate_origin_type_schema(
    tp: object,
    origin: object,
    args: tuple[object, ...],
    walk_seen: set[object],
    localns: Optional[Mapping[str, object]],
) -> None:
    if origin is Literal:
        _validate_literal_schema_args(tp, args)
        return
    if origin in (Union, UnionType):
        _assert_unambiguous_union_branches(tp, localns=localns)
        for arg in args:
            _validate_declared_type_schema(arg, walk_seen, localns=localns)
        return
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            _validate_declared_type_schema(args[0], walk_seen, localns=localns)
            return
        if any(a is Ellipsis for a in args):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid tuple Ellipsis schema {tp!r}")
        for arg in args:
            _validate_declared_type_schema(arg, walk_seen, localns=localns)
        return
    if origin in (list, cabc.Sequence, Sequence, frozenset):
        if len(args) > 1:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid sequence arity in schema {tp!r}")
        for arg in args:
            _validate_declared_type_schema(arg, walk_seen, localns=localns)
        return
    if origin in (dict, cabc.Mapping, Mapping):
        if len(args) not in (0, 2):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid mapping arity in schema {tp!r}")
        if len(args) == 2:
            _validate_map_key_schema(args[0], walk_seen, localns)
            _validate_declared_type_schema(args[1], walk_seen, localns=localns)
        return
    if isinstance(origin, type) and dataclasses.is_dataclass(origin):
        _validate_generic_dc_type_args(origin, args)
        if _try_mark_seen(walk_seen, (origin, args)):
            _validate_dc_fields_schema(origin, args, walk_seen)
        for arg in args:
            _validate_declared_type_schema(arg, walk_seen, localns=localns)
        return
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported generic schema type {tp!r}")


def _validate_declared_type_schema(
    tp: object,
    seen: Optional[set[object]] = None,
    *,
    localns: Optional[Mapping[str, object]] = None,
) -> None:
    tp = _unwrap_annotated(tp)
    if get_origin(tp) is ClassVar:
        return
    if _is_forbidden_any_type(tp):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "typing.Any is forbidden in DataclassCodec schema.")
    is_root = seen is None and localns is None
    if is_root and _is_schema_cached(tp):
        return
    walk_seen = seen if seen is not None else set()
    if isinstance(tp, ForwardRef):
        if tp.__forward_arg__ == "JsonValue":
            return
        resolved = _resolve_forward_ref(tp, localns=localns)
        if _try_mark_seen(walk_seen, ("fwd", tp.__forward_arg__, id(resolved))):
            _validate_declared_type_schema(resolved, walk_seen, localns=localns)
        return
    if isinstance(tp, TypeVar):
        for c in tp.__constraints__:
            _validate_declared_type_schema(c, walk_seen, localns=localns)
        if tp.__bound__ is not None:
            _validate_declared_type_schema(tp.__bound__, walk_seen, localns=localns)
        return
    if _is_untyped_wildcard(tp) or tp in _UNPARAM_SCHEMA_FORMS:
        if is_root:
            _record_schema_cached(tp)
        return
    origin = get_origin(tp)
    if origin is not None:
        _validate_origin_type_schema(tp, origin, get_args(tp), walk_seen, localns)
    elif isinstance(tp, type):
        if tp in _SUPPORTED_SCALAR_CLASSES or issubclass(tp, Enum):
            pass
        elif dataclasses.is_dataclass(tp):
            if _try_mark_seen(walk_seen, tp):
                _validate_dc_fields_schema(tp, (), walk_seen)
        else:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported target class {tp!r}")
    else:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported non-type schema {tp!r}")
    if is_root:
        _record_schema_cached(tp)


def _needs_localns_for_forward_ref(tp: object) -> bool:
    tp = _unwrap_annotated(tp)
    if isinstance(tp, ForwardRef):
        if tp.__forward_arg__ == "JsonValue":
            return False
        mod_name = tp.__forward_module__
        if mod_name and mod_name in sys.modules and tp.__forward_arg__ in sys.modules[mod_name].__dict__:
            return False
        return True
    return any(_needs_localns_for_forward_ref(a) for a in get_args(tp))


def _make_bound_field_decoder(field_tp: object, eff_lns: Optional[Mapping[str, object]]) -> DecodeFn:
    cell: list[Optional[DecodeFn]] = [None]
    stored_tp = _dehydrate_type(field_tp) if eff_lns is None else field_tp

    def _run_field(val: JsonValue, path: str, depth: int) -> object:
        if depth > _MAX_CODEC_DEPTH:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Maximum nesting depth exceeded at {path}")
        fn = cell[0]
        if fn is None:
            if eff_lns is None:
                ok_f, live_tp = _rehydrate_type(stored_tp)
                if not ok_f:
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unloaded field type at {path}")
            else:
                live_tp = stored_tp
            fn = _get_or_compile_plan(live_tp, eff_lns)
            cell[0] = fn
        return fn(val, path, depth)

    return _run_field


def _compile_literal_plan(tp: object) -> DecodeFn:
    _validate_literal_schema_args(tp, get_args(tp))
    table = tuple(
        (DataclassCodec.encode(lit.value if isinstance(lit, Enum) else lit), _dehydrate_type(lit))
        for lit in get_args(tp)
    )

    def _dec_lit(raw: JsonValue, path: str, depth: int) -> object:
        if isinstance(raw, Enum):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unencoded Enum forbidden at {path}")
        validated_raw = _validate_json_value(raw, path=path, depth=depth)
        for enc_val, w_lit in table:
            if _strict_json_equals(enc_val, validated_raw):
                ok_l, lit_val = _rehydrate_type(w_lit)
                if not ok_l:
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unloaded Literal member at {path}")
                return lit_val
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid Literal value {raw!r} at {path}")

    return _dec_lit


@dataclasses.dataclass(frozen=True, slots=True)
class _DcFieldSpec:
    name: str
    required: bool
    decode_fn: DecodeFn


def _build_dc_field_specs(
    dc_cls: type[object],
    init_specs: Sequence[tuple[str, bool]],
    base_fields: Mapping[str, tuple[object, dict[str, object]]],
    tv_map: Mapping[object, object],
    fallback_lns: Mapping[str, object],
) -> tuple[_DcFieldSpec, ...]:
    raw_types = {f.name: f.type for f in dataclasses.fields(dc_cls) if f.init}
    is_local_cls = ".<locals>." in dc_cls.__qualname__
    specs: list[_DcFieldSpec] = []
    for fname, required in init_specs:
        entry = base_fields.get(fname)
        base_tp = entry[0] if entry is not None else raw_types.get(fname, object)
        field_tp = _substitute_typevars(base_tp, tv_map) if tv_map else base_tp
        field_lns = entry[1] if entry is not None else fallback_lns
        _validate_declared_type_schema(field_tp, localns=field_lns or None)
        eff_lns = field_lns if (field_lns and (is_local_cls or _needs_localns_for_forward_ref(field_tp))) else None
        specs.append(_DcFieldSpec(fname, required, _make_bound_field_decoder(field_tp, eff_lns)))
    return tuple(specs)


def _compile_dataclass_plan(
    dc_cls: type[object],
    tv_map: Mapping[object, object],
    parent_localns: Optional[Mapping[str, object]],
) -> DecodeFn:
    try:
        init_specs, base_fields = _compile_mro_base_metadata(dc_cls, parent_localns)
    except _UnresolvedLocalHintError as exc:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, safe_exception_summary(exc)) from exc
    known_names = frozenset(fname for fname, _req in init_specs)
    fallback_lns: dict[str, object] = dict(parent_localns) if parent_localns is not None else {}
    _populate_qualname_and_closure_ns(dc_cls.__module__, dc_cls.__qualname__, dc_cls, fallback_lns)
    fallback_lns.pop(dc_cls.__name__, None)
    field_specs = _build_dc_field_specs(dc_cls, init_specs, base_fields, tv_map, fallback_lns)
    dc_ref = weakref.ref(dc_cls)
    cls_name = dc_cls.__name__

    def _dec_dc(raw: JsonValue, path: str, depth: int) -> object:
        cls_obj = dc_ref()
        if cls_obj is None:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unloaded dataclass {cls_name} at {path}")
        if not isinstance(raw, cabc.Mapping):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected object mapping at {path} for {cls_name}")
        for k in raw.keys():
            if type(k) is not str:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected plain str field key at {path} for {cls_name}")
        if any(k not in known_names for k in raw.keys()):
            unknown = sorted(str(k) for k in raw.keys() if k not in known_names)
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unexpected fields {unknown} at {path} for {cls_name}")
        kwargs: dict[str, object] = {}
        for fs in field_specs:
            if fs.name in raw:
                kwargs[fs.name] = fs.decode_fn(raw[fs.name], f"{path}.{fs.name}", depth + 1)
            elif fs.required:
                raise YscbError(
                    ErrorCode.CODEC_VALIDATION_FAILED, f"Missing required field '{fs.name}' at {path} for {cls_name}"
                )
        try:
            return cls_obj(**kwargs)
        except (ValueError, TypeError) as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Validation failed at {path}: {safe_exception_summary(exc)}") from exc

    return _dec_dc


def _compile_tuple_plan(tp: object, localns: Optional[Mapping[str, object]]) -> DecodeFn:
    if tp is tuple or tp == Tuple:
        return lambda raw, path, depth: tuple(
            _validate_json_value(item, path=f"{path}[{i}]", depth=depth + 1)
            for i, item in enumerate(_ensure_json_seq(raw, path))
        )
    args = get_args(tp)
    if not args:
        def _dec_empty_tuple(raw: JsonValue, path: str) -> tuple[()]:
            seq = _ensure_json_seq(raw, path)
            if len(seq) != 0:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected empty tuple at {path}, got length {len(seq)}")
            return ()
        return _as_leaf_plan(_dec_empty_tuple)
    if len(args) == 2 and args[1] is Ellipsis:
        elem_plan = _get_or_compile_plan(args[0], localns)
        def _dec_var_tuple(raw: JsonValue, path: str, depth: int) -> tuple[object, ...]:
            seq = _ensure_json_seq(raw, path)
            return tuple(elem_plan(item, f"{path}[{i}]", depth + 1) for i, item in enumerate(seq))
        return _dec_var_tuple
    elem_plans = tuple(_get_or_compile_plan(a, localns) for a in args)

    def _dec_fixed_tuple(raw: JsonValue, path: str, depth: int) -> tuple[object, ...]:
        seq = _ensure_json_seq(raw, path)
        if len(seq) != len(elem_plans):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Tuple length mismatch at {path}")
        return tuple(elem_plans[i](seq[i], f"{path}[{i}]", depth + 1) for i in range(len(elem_plans)))

    return _dec_fixed_tuple


def _ensure_json_seq(raw: JsonValue, path: str) -> cabc.Sequence[JsonValue]:
    if not isinstance(raw, (list, tuple)):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected sequence at {path}")
    return raw


def _compile_collection_plan(origin: object, tp: object, localns: Optional[Mapping[str, object]]) -> Optional[DecodeFn]:
    if origin is tuple:
        return _compile_tuple_plan(tp, localns)
    if origin in (list, cabc.Sequence, Sequence):
        args = get_args(tp)
        elem_plan = _get_or_compile_plan(args[0] if args else object, localns)
        as_list = origin is list
        def _dec_seq(raw: JsonValue, path: str, depth: int) -> object:
            seq = _ensure_json_seq(raw, path)
            items = [elem_plan(item, f"{path}[{i}]", depth + 1) for i, item in enumerate(seq)]
            return items if as_list else tuple(items)
        return _dec_seq
    if origin is frozenset:
        args = get_args(tp)
        elem_plan = _get_or_compile_plan(args[0] if args else object, localns)
        def _dec_fset(raw: JsonValue, path: str, depth: int) -> frozenset[object]:
            if not isinstance(raw, (list, tuple, frozenset)):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected array/frozenset at {path}")
            decoded_items = [elem_plan(item, f"{path}[{i}]", depth + 1) for i, item in enumerate(raw)]
            try:
                return frozenset(decoded_items)
            except TypeError as exc:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unhashable frozenset element at {path}: {safe_exception_summary(exc)}") from exc
        return _dec_fset
    if origin in (dict, cabc.Mapping, Mapping):
        args = get_args(tp)
        if len(args) not in (0, 2):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid mapping arity in {tp!r}")
        key_tp = args[0] if len(args) == 2 else str
        val_tp = args[1] if len(args) == 2 else object
        _validate_map_key_schema(key_tp, set(), localns)
        if key_tp is str and (
            _is_untyped_wildcard(val_tp)
            or val_tp is JsonValue
            or (isinstance(val_tp, ForwardRef) and val_tp.__forward_arg__ == "JsonValue")
        ):
            return lambda raw, path, depth: _validate_json_object(raw, path=path, depth=depth)
        val_plan = _get_or_compile_plan(val_tp, localns)
        stored_kt = _dehydrate_type(key_tp) if localns is None else key_tp
        def _dec_map(raw: JsonValue, path: str, depth: int) -> dict[object, object]:
            if not isinstance(raw, cabc.Mapping):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected mapping at {path}")
            if localns is None:
                ok_k, live_kt = _rehydrate_type(stored_kt)
                if not ok_k:
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unloaded mapping key type at {path}")
            else:
                live_kt = stored_kt
            decoded_map: dict[object, object] = {}
            for k, v in raw.items():
                dec_k = _decode_map_key(live_kt, k, path=f"{path}.key", depth=depth + 1, localns=localns)
                if dec_k in decoded_map:
                    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Duplicate decoded mapping key {dec_k!r} at {path}")
                decoded_map[dec_k] = val_plan(v, f"{path}.{k}", depth + 1)
            return decoded_map
        return _dec_map
    return None


def _compile_union_plan(tp: object, localns: Optional[Mapping[str, object]]) -> DecodeFn:
    resolved_tp = _resolve_schema_refs(tp, localns)
    if _is_wildcard_elem(resolved_tp):
        return lambda raw, path, depth: _validate_json_value(raw, path=path, depth=depth)
    args = get_args(tp)
    allows_none = type(None) in args
    non_none = tuple(c for c in args if c is not type(None))
    resolved_map = {c: _resolve_schema_refs(c, localns) for c in non_none}
    _assert_unambiguous_union_branches(tp, localns=localns)
    tp_label = repr(tp)
    branch_entries = tuple(
        (_dehydrate_type(resolved_map[c]) if localns is None else resolved_map[c], _get_or_compile_plan(resolved_map[c], localns))
        for c in non_none
    )

    def _dec_union(raw: JsonValue, path: str, depth: int) -> object:
        if isinstance(raw, int) and not isinstance(raw, bool):
            _assert_int64_range(raw, path=path)
        if raw is None and allows_none:
            return None
        ranked_branches: list[tuple[_UnionCandRank, DecodeFn]] = []
        for stored_br, b_plan in branch_entries:
            if localns is None:
                ok_b, live_br = _rehydrate_type(stored_br)
                if not ok_b:
                    continue
            else:
                live_br = stored_br
            ranked_branches.append((_union_candidate_rank(live_br, raw), b_plan))
        ranked_branches.sort(key=lambda pair: pair[0])
        for _rk, b_plan in ranked_branches:
            try:
                return b_plan(raw, path, depth)
            except (YscbError, ValueError, TypeError, OverflowError):
                continue
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Value at {path} did not match union {tp_label}")

    return _dec_union


def _resolve_forward_ref(ref: ForwardRef, *, localns: Optional[Mapping[str, object]]) -> object:
    if ref.__forward_arg__ == "JsonValue":
        return JsonValue
    if localns is not None and ref.__forward_arg__ in localns:
        return localns[ref.__forward_arg__]
    mod_name = ref.__forward_module__
    if mod_name and mod_name in sys.modules:
        mod_ns = sys.modules[mod_name].__dict__
        if ref.__forward_arg__ in mod_ns:
            return mod_ns[ref.__forward_arg__]
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unresolved ForwardRef {ref.__forward_arg__!r}")


def _compile_plan_uncached(tp: object, localns: Optional[Mapping[str, object]]) -> DecodeFn:
    tp = _unwrap_annotated(tp)
    if _is_forbidden_any_type(tp):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "typing.Any is forbidden in DataclassCodec.")
    if isinstance(tp, ForwardRef):
        tp = _unwrap_annotated(_resolve_forward_ref(tp, localns=localns))
        if _is_forbidden_any_type(tp):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "typing.Any is forbidden in DataclassCodec.")
    if isinstance(tp, TypeVar):
        if tp.__constraints__:
            return _compile_union_plan(functools.reduce(operator.or_, tp.__constraints__), localns)
        if tp.__bound__ is not None:
            return _compile_plan_uncached(tp.__bound__, localns)
        return lambda raw, path, depth: _validate_json_value(raw, path=path, depth=depth)
    if _is_untyped_wildcard(tp) or tp is JsonValue:
        return lambda raw, path, depth: _validate_json_value(raw, path=path, depth=depth)
    if tp in (JsonObject, MutableJsonObject, dict, cabc.Mapping, Mapping):
        return lambda raw, path, depth: _validate_json_object(raw, path=path, depth=depth)
    if tp is type(None):
        def _dec_none(raw: JsonValue, path: str) -> None:
            if raw is not None:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected None at {path}, got {type(raw).__name__}")
            return None
        return _as_leaf_plan(_dec_none)
    if tp is tuple or tp == Tuple:
        return _compile_tuple_plan(tuple, localns)
    if tp is frozenset:
        return require_non_none(_compile_collection_plan(frozenset, tp, localns))
    if tp in (list, cabc.Sequence, Sequence):
        return require_non_none(_compile_collection_plan(list if tp is list else Sequence, tp, localns))

    origin = get_origin(tp)
    if origin is Literal:
        return _compile_literal_plan(tp)
    if origin is Union or origin is UnionType:
        return _compile_union_plan(tp, localns)
    col_plan = _compile_collection_plan(origin, tp, localns)
    if col_plan is not None:
        return col_plan
    if isinstance(origin, type) and dataclasses.is_dataclass(origin):
        g_args = get_args(tp)
        _validate_generic_dc_type_args(origin, g_args)
        tv_map = dict(zip(_generic_type_params(origin), g_args))
        return _compile_dataclass_plan(origin, tv_map, localns)
    if isinstance(tp, type):
        scalar_plan = _compile_scalar_plan(tp)
        if scalar_plan is not None:
            return scalar_plan
        if dataclasses.is_dataclass(tp):
            return _compile_dataclass_plan(tp, {}, localns)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported target type {tp}")


def _lookup_cached_plan(tp: object, is_plain_type: bool) -> Optional[DecodeFn]:
    with DataclassCodec._CACHE.lock:
        if is_plain_type and isinstance(tp, type):
            return DataclassCodec._CACHE.type_plans.get(tp)
        try:
            wkey = _dehydrate_type(tp)
            cached_f = DataclassCodec._CACHE.form_plans.get(wkey)
        except TypeError:
            return None
        if cached_f is not None:
            DataclassCodec._CACHE.form_plans.move_to_end(wkey)
        return cached_f


def _is_self_referential_dataclass(tp: type[object]) -> bool:
    if tp in _SCALAR_VO_TYPES or not dataclasses.is_dataclass(tp):
        return False
    with DataclassCodec._CACHE.lock:
        if tp in DataclassCodec._CACHE.recursive_dcs:
            return True
        if tp in DataclassCodec._CACHE.dc_hints:
            return False
    return True


def _store_cached_plan(tp: object, is_plain_type: bool, compiled: DecodeFn) -> None:
    if _type_tree_any(tp, _is_uncacheable_local_or_unbound_node) or _type_tree_any(tp, _is_recursive_dataclass_node):
        return
    cache = DataclassCodec._CACHE
    with cache.lock:
        if is_plain_type and isinstance(tp, type):
            cache.type_plans[tp] = compiled
            return
        key_box: list[object] = []

        def _evict_dead_plan(_r: object) -> None:
            if key_box:
                with cache.lock:
                    cache.form_plans.pop(key_box[0], None)

        try:
            wkey = _dehydrate_type(tp, _evict_dead_plan)
            key_box.append(wkey)
            cache.form_plans[wkey] = compiled
            if len(cache.form_plans) > _PLAN_LRU_LIMIT:
                cache.form_plans.popitem(last=False)
        except TypeError:
            return


def _get_or_compile_plan(tp: object, localns: Optional[Mapping[str, object]]) -> DecodeFn:
    if localns:
        return _compile_plan_uncached(tp, localns)
    act_plans = DataclassCodec._CACHE.active.plans
    if act_plans is not None:
        try:
            in_act = act_plans.get(tp)
        except TypeError:
            in_act = None
        if in_act is not None:
            return in_act
    is_plain_type = isinstance(tp, type)
    cached = _lookup_cached_plan(tp, is_plain_type)
    if cached is not None:
        return cached
    compiled = _compile_plan_uncached(tp, None)
    if act_plans is not None:
        try:
            act_plans[tp] = compiled
        except TypeError:
            pass
    _store_cached_plan(tp, is_plain_type, compiled)
    return compiled


def _decode_by_type(
    tp: object,
    raw: JsonValue,
    *,
    path: str,
    depth: int,
    localns: Optional[Mapping[str, object]],
) -> object:
    if depth > _MAX_CODEC_DEPTH:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Maximum nesting depth exceeded at {path}")
    act = DataclassCodec._CACHE.active
    owns_memo = localns is None and act.plans is None
    if owns_memo:
        act.plans = {}
        act.hints = {}
    try:
        plan = _get_or_compile_plan(tp, localns)
        return plan(raw, path, depth)
    finally:
        if owns_memo:
            act.plans = None
            act.hints = None


def _get_dataclass_field_getters(dc_cls: type[object]) -> tuple[FieldGetter, ...]:
    with DataclassCodec._CACHE.lock:
        cached = DataclassCodec._CACHE.dc_getters.get(dc_cls)
        if cached is not None:
            return cached
    try:
        _compile_mro_base_metadata(dc_cls, None)
    except _UnresolvedLocalHintError as exc:
        if ".<locals>." not in dc_cls.__qualname__:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, safe_exception_summary(exc)) from exc
    getters: tuple[FieldGetter, ...] = tuple(
        (f.name, operator.attrgetter(f.name)) for f in dataclasses.fields(dc_cls) if f.init
    )
    with DataclassCodec._CACHE.lock:
        DataclassCodec._CACHE.dc_getters[dc_cls] = getters
    return getters


@dataclasses.dataclass(slots=True)
class _EncodeCtx:
    valid_schemas: set[object] = dataclasses.field(default_factory=set)


def _ensure_schema_valid_once(
    tp: object,
    ctx: _EncodeCtx,
    *,
    self_key: Optional[object] = None,
    localns: Optional[Mapping[str, object]] = None,
) -> None:
    unwrapped = _unwrap_annotated(tp)
    try:
        in_memo = unwrapped in ctx.valid_schemas
    except TypeError:
        in_memo = False
    if in_memo:
        return
    if localns is None and _is_schema_cached(unwrapped):
        try:
            ctx.valid_schemas.add(unwrapped)
        except TypeError:
            pass
        return
    seed = {self_key} if self_key is not None else None
    _validate_declared_type_schema(tp, seed, localns=localns)
    try:
        ctx.valid_schemas.add(unwrapped)
    except TypeError:
        pass
    if localns is None:
        _record_schema_cached(unwrapped)


def _encode_mapping_strict(
    obj: cabc.Mapping[object, object],
    *,
    depth: int,
    ctx: _EncodeCtx,
    key_tp: Optional[object] = None,
    val_tp: Optional[object] = None,
    localns: Optional[Mapping[str, object]] = None,
) -> MutableJsonObject:
    if depth > _MAX_CODEC_DEPTH:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Maximum nesting depth exceeded during mapping encode.")
    encoded_map: MutableJsonObject = {}
    for k, v in obj.items():
        if key_tp is not None:
            _ = _encode_value_checked(k, depth=depth + 1, ctx=ctx, declared_tp=key_tp, localns=localns)
        if isinstance(k, Enum):
            enc_k = _canonical_map_key_str(_encode_value_checked(k.value, depth=depth + 1, ctx=ctx))
        elif isinstance(k, bool):
            enc_k = "true" if k else "false"
        elif type(k) is int:
            enc_k = str(_assert_int64_range(k, path="$map_key"))
        elif type(k) is str or isinstance(k, (ModuleId, TaskId, EventId, HostPath)):
            enc_k = str(k)
        else:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported mapping key type: {type(k).__name__}")
        if enc_k in encoded_map:
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"Duplicate serialized mapping key {enc_k!r} in DataclassCodec.encode.",
            )
        _check_str_valid_utf8(enc_k, path="$map_key")
        encoded_map[enc_k] = _encode_value_checked(
            v, depth=depth + 1, ctx=ctx, declared_tp=val_tp, localns=localns
        )
    return encoded_map


class DataclassCodec:
    """Single reflection boundary converting strongly typed dataclasses to/from JsonValue.

    Untagged unions resolve deterministically along a strict specificity lattice
    (Enum/Literal > TaskId/EventId > ModuleId > HostPath > bool > int/str > float > JsonValue,
    and tuple[()] > variable-length sequences), while rejecting equal-rank, binary-vs-text,
    overlapping-dataclass, or overlapping-key-domain ambiguities at schema validation time.
    """

    _CACHE: ClassVar[_CodecMetadataCache] = _CodecMetadataCache()

    @staticmethod
    def encode(obj: object) -> JsonValue:
        act = DataclassCodec._CACHE.active
        owns_h = act.hints is None
        if owns_h:
            act.hints = {}
        try:
            return _encode_value_checked(obj, depth=0, ctx=_EncodeCtx())
        except (RecursionError, UnicodeError) as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Codec encode failed: {safe_exception_summary(exc)}") from exc
        finally:
            if owns_h:
                act.hints = None

    @staticmethod
    def encode_typed(expected_type: object, obj: object) -> JsonValue:
        act = DataclassCodec._CACHE.active
        owns_h = act.hints is None
        if owns_h:
            act.hints = {}
        try:
            ctx = _EncodeCtx()
            _ensure_schema_valid_once(expected_type, ctx)
            return _encode_value_checked(obj, depth=0, ctx=ctx, declared_tp=expected_type)
        except (RecursionError, UnicodeError) as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Codec encode_typed failed: {safe_exception_summary(exc)}") from exc
        finally:
            if owns_h:
                act.hints = None

    @staticmethod
    def encode_object(obj: object, *, expected_type: Optional[object] = None) -> MutableJsonObject:
        encoded = (
            DataclassCodec.encode_typed(expected_type, obj)
            if expected_type is not None
            else DataclassCodec.encode(obj)
        )
        if not isinstance(encoded, cabc.Mapping):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Expected dataclass/mapping to encode into JsonObject.")
        return dict(encoded)

    @staticmethod
    def encode_envelope(obj: object) -> MutableJsonObject:
        act = DataclassCodec._CACHE.active
        owns_h = act.hints is None
        if owns_h:
            act.hints = {}
        try:
            encoded = _encode_value_checked(obj, depth=-_ENVELOPE_DEPTH_HEADROOM, ctx=_EncodeCtx())
        except (RecursionError, UnicodeError) as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Envelope encode failed: {safe_exception_summary(exc)}") from exc
        finally:
            if owns_h:
                act.hints = None
        if not isinstance(encoded, cabc.Mapping):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Expected envelope dataclass to encode into JsonObject.")
        return dict(encoded)

    @staticmethod
    def decode_envelope(target_cls: type[T], raw: JsonValue) -> T:
        try:
            return _decode_by_type(
                target_cls,
                raw,
                path="$",
                depth=-_ENVELOPE_DEPTH_HEADROOM,
                localns=None,
            )
        except (RecursionError, UnicodeError) as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Envelope decode failed: {safe_exception_summary(exc)}") from exc

    @overload
    @staticmethod
    def decode(
        target_cls: type[T],
        raw: JsonValue,
        *,
        localns: Optional[Mapping[str, object]] = None,
    ) -> T: ...

    @overload
    @staticmethod
    def decode(
        target_cls: object,
        raw: JsonValue,
        *,
        localns: Optional[Mapping[str, object]] = None,
    ) -> object: ...

    @staticmethod
    def decode(
        target_cls: object,
        raw: JsonValue,
        *,
        localns: Optional[Mapping[str, object]] = None,
    ) -> object:
        try:
            return _decode_by_type(target_cls, raw, path="$", depth=0, localns=localns)
        except (RecursionError, UnicodeError) as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Codec decode failed: {safe_exception_summary(exc)}") from exc

    @staticmethod
    def canonical_hash(raw: object) -> str:
        try:
            encoded = DataclassCodec.encode(raw)
            canonical = json.dumps(
                encoded,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        except (RecursionError, UnicodeError) as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Codec canonical_hash failed: {safe_exception_summary(exc)}") from exc

    @staticmethod
    def evict_module_prefix(module_prefix: str) -> None:
        root_pkg = module_prefix.strip(".")
        if not root_pkg:
            return
        dot_pkg = f"{root_pkg}."
        cache = DataclassCodec._CACHE
        with cache.lock:
            hints_snap = dict(cache.dc_hints.items())
            for wk_map in (cache.dc_getters, cache.dc_hints, cache.enum_tables, cache.type_plans):
                stale_keys = [
                    k for k in list(wk_map.keys()) if _class_or_fields_mention_prefix(k, root_pkg, dot_pkg, hints_snap, set())
                ]
                for k in stale_keys:
                    wk_map.pop(k, None)
            stale_cb = [
                k
                for k, v in list(cache.callable_payloads.items())
                if _obj_in_module_prefix(k, root_pkg, dot_pkg)
                or (v[1] is not None and _class_or_fields_mention_prefix(v[1], root_pkg, dot_pkg, hints_snap, set()))
            ]
            for k in stale_cb:
                cache.callable_payloads.pop(k, None)
            for wk_set in (cache.valid_type_schemas, cache.recursive_dcs):
                for k in [k for k in list(wk_set) if _class_or_fields_mention_prefix(k, root_pkg, dot_pkg, hints_snap, set())]:
                    wk_set.discard(k)
            for form_map in (cache.form_plans, cache.valid_form_schemas):
                stale_forms = [
                    fk for fk in list(form_map.keys()) if _class_or_fields_mention_prefix(fk, root_pkg, dot_pkg, hints_snap, set())
                ]
                for fk in stale_forms:
                    form_map.pop(fk, None)
        try:
            tp_cleanups = tuple(typing._cleanups)
        except AttributeError:
            tp_cleanups = ()
        for cleanup_fn in tp_cleanups:
            cleanup_fn()


def _class_or_fields_mention_prefix(
    obj: object,
    root_pkg: str,
    dot_pkg: str,
    hints_snap: Mapping[type[object], tuple[tuple[tuple[str, bool], ...], dict[str, object]]],
    seen: set[int],
) -> bool:
    ok_obj, live_obj = _rehydrate_type(obj)
    if not ok_obj:
        return True
    obj = live_obj
    if id(obj) in seen:
        return False
    seen.add(id(obj))
    if _type_mentions_module_prefix(obj, root_pkg):
        return True
    dc_cls = _resolve_node_dataclass(obj)
    if dc_cls is None:
        return _obj_in_module_prefix(obj, root_pkg, dot_pkg) if isinstance(obj, type) else False
    hint_entry = hints_snap.get(dc_cls)
    if hint_entry is not None:
        rehyd = [_rehydrate_type(wt) for wt in hint_entry[1].values()]
        if not all(ok for ok, _ in rehyd):
            return True
        field_types: list[object] = [vt for _, vt in rehyd]
    else:
        field_types = [f.type for f in dataclasses.fields(dc_cls) if f.init and not isinstance(f.type, str)]
    return any(
        _type_mentions_module_prefix(ft, root_pkg)
        or _type_tree_any(
            ft,
            lambda n: (sub := _resolve_node_dataclass(n)) is not None
            and _class_or_fields_mention_prefix(sub, root_pkg, dot_pkg, hints_snap, seen),
        )
        for ft in field_types
    )


def _generic_type_params(cls: type[object]) -> tuple[object, ...]:
    try:
        params = cls.__parameters__
    except AttributeError:
        return ()
    return params if isinstance(params, tuple) else ()


def _literal_member_matches(val: object, lit: object, *, path: str) -> bool:
    if isinstance(lit, Enum):
        return type(val) is type(lit) and val == lit
    if isinstance(val, Enum):
        return False
    if isinstance(lit, str) and isinstance(val, str):
        _check_str_valid_utf8(val, path=path)
    return type(val) is type(lit) and val == lit


def _resolve_annotated_or_ref(tp: object, localns: Optional[Mapping[str, object]]) -> object:
    cur = _unwrap_annotated(tp)
    steps = 0
    while isinstance(cur, ForwardRef):
        if cur.__forward_arg__ == "JsonValue":
            return JsonValue
        steps += 1
        if steps > _MAX_CODEC_DEPTH:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Cyclic ForwardRef during encode.")
        cur = _unwrap_annotated(_resolve_forward_ref(cur, localns=localns))
    return cur


def _branch_can_match_outer(obj: object, raw_br: object, localns: Optional[Mapping[str, object]]) -> bool:
    br = _resolve_annotated_or_ref(raw_br, localns)
    if isinstance(br, TypeVar):
        if br.__constraints__:
            return any(_branch_can_match_outer(obj, c, localns) for c in br.__constraints__)
        return _branch_can_match_outer(obj, br.__bound__ if br.__bound__ is not None else JsonValue, localns)
    if br is JsonValue or _is_untyped_wildcard(br):
        return obj is None or type(obj) in (bool, int, float, str) or isinstance(obj, (list, tuple, cabc.Mapping))
    if br in (JsonObject, MutableJsonObject, dict, cabc.Mapping, Mapping):
        return isinstance(obj, cabc.Mapping)
    if br in (list, cabc.Sequence, Sequence, tuple, Tuple):
        return isinstance(obj, (list, tuple))
    if br is frozenset:
        return isinstance(obj, frozenset)
    if br is type(None):
        return obj is None
    if _is_explicit_empty_tuple_type(br):
        return isinstance(obj, (tuple, list)) and len(obj) == 0
    orig = get_origin(br)
    if orig in (Union, UnionType):
        return any(_branch_can_match_outer(obj, sub, localns) for sub in get_args(br))
    if orig is Literal:
        return any(_literal_member_matches(obj, lit, path="$union") for lit in get_args(br))
    if orig in (list, cabc.Sequence, Sequence, tuple):
        return isinstance(obj, (list, tuple))
    if orig is frozenset:
        return isinstance(obj, frozenset)
    if orig in (dict, cabc.Mapping, Mapping):
        return isinstance(obj, cabc.Mapping)
    if isinstance(orig, type) and dataclasses.is_dataclass(orig):
        return type(obj) is orig
    if isinstance(br, type):
        if br in (bool, int, str, bytes):
            return type(obj) is br
        if br is float:
            return type(obj) in (int, float)
        if br in _SCALAR_VO_TYPES or issubclass(br, Enum):
            return not isinstance(obj, type) and isinstance(obj, br)
        if dataclasses.is_dataclass(br):
            return type(obj) is br
    return True


def _encode_union_value(
    obj: object,
    tp: object,
    args: tuple[object, ...],
    *,
    depth: int,
    ctx: _EncodeCtx,
    localns: Optional[Mapping[str, object]],
) -> JsonValue:
    if obj is None:
        if type(None) in args:
            return None
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"None not allowed for {tp}")
    non_none = [b for b in args if b is not type(None)]
    if len(non_none) == 1:
        return _encode_value_checked(obj, depth=depth, ctx=ctx, declared_tp=non_none[0], localns=localns)
    compat = [b for b in non_none if _branch_can_match_outer(obj, b, localns)]
    if not compat:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Value {obj!r} did not match {tp}")
    if len(compat) == 1:
        return _encode_value_checked(obj, depth=depth, ctx=ctx, declared_tp=compat[0], localns=localns)
    if type(obj) is int:
        compat.sort(key=lambda b: 1 if _resolve_annotated_or_ref(b, localns) is float else 0)
    for br in compat:
        try:
            return _encode_value_checked(obj, depth=depth, ctx=ctx, declared_tp=br, localns=localns)
        except YscbError:
            continue
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Value {obj!r} did not match {tp}")


def _resolve_dc_field_encode_spec(
    dc_cls: type[object],
    fname: str,
    field_types: Optional[Mapping[str, tuple[object, dict[str, object]]]],
    tv_map: Mapping[object, object],
    localns: Optional[Mapping[str, object]],
) -> tuple[Optional[object], Optional[Mapping[str, object]]]:
    if field_types is not None and fname in field_types:
        raw_tp, raw_lns = field_types[fname]
        f_tp = _substitute_typevars(raw_tp, tv_map) if tv_map else raw_tp
        return (f_tp, raw_lns or localns)
    for f in dataclasses.fields(dc_cls):
        if f.init and f.name == fname and not isinstance(f.type, str):
            f_tp = _substitute_typevars(f.type, tv_map) if tv_map else f.type
            return (f_tp, localns)
    return (None, localns)


def _encode_dataclass_checked(
    obj: object,
    *,
    depth: int,
    ctx: _EncodeCtx,
    tv_map: Mapping[object, object] = {},
    localns: Optional[Mapping[str, object]] = None,
) -> MutableJsonObject:
    dc_cls = type(obj)
    getters = _get_dataclass_field_getters(dc_cls)
    try:
        _, field_types = _compile_mro_base_metadata(dc_cls, None)
    except _UnresolvedLocalHintError:
        field_types = None
    out: MutableJsonObject = {}
    self_key: object = (dc_cls, tuple(tv_map.values())) if tv_map else dc_cls
    for fname, getter in getters:
        fval = getter(obj)
        f_tp, f_lns = _resolve_dc_field_encode_spec(dc_cls, fname, field_types, tv_map, localns)
        if f_tp is not None:
            _ensure_schema_valid_once(f_tp, ctx, self_key=self_key, localns=f_lns)
        out[fname] = _encode_value_checked(fval, depth=depth + 1, ctx=ctx, declared_tp=f_tp, localns=f_lns)
    return out


def _encode_declared_container(
    obj: object,
    origin: object,
    args: tuple[object, ...],
    *,
    depth: int,
    ctx: _EncodeCtx,
    localns: Optional[Mapping[str, object]],
) -> Optional[JsonValue]:
    if origin is tuple:
        if not isinstance(obj, (tuple, list)):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected tuple, got {type(obj).__name__}")
        if not args or (len(args) == 2 and args[1] is Ellipsis):
            el_tp = args[0] if args else JsonValue
            return [_encode_value_checked(it, depth=depth + 1, ctx=ctx, declared_tp=el_tp, localns=localns) for it in obj]
        if len(obj) != len(args):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Tuple length mismatch during encode.")
        return [
            _encode_value_checked(it, depth=depth + 1, ctx=ctx, declared_tp=etp, localns=localns)
            for it, etp in zip(obj, args)
        ]
    if origin in (list, cabc.Sequence, Sequence):
        if not isinstance(obj, (list, tuple)):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected sequence, got {type(obj).__name__}")
        el_tp = args[0] if args else JsonValue
        return [_encode_value_checked(it, depth=depth + 1, ctx=ctx, declared_tp=el_tp, localns=localns) for it in obj]
    if origin is frozenset:
        if not isinstance(obj, frozenset):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected frozenset, got {type(obj).__name__}")
        el_tp = args[0] if args else JsonValue
        items = [_encode_value_checked(it, depth=depth + 1, ctx=ctx, declared_tp=el_tp, localns=localns) for it in obj]
        return _sort_encoded_frozenset_items(items)
    if origin in (dict, cabc.Mapping, Mapping):
        if not isinstance(obj, cabc.Mapping) or len(args) not in (0, 2):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected mapping, got {type(obj).__name__}")
        if not args:
            return _encode_mapping_strict(obj, depth=depth, ctx=ctx, key_tp=str, val_tp=JsonValue, localns=localns)
        _validate_map_key_schema(args[0], set(), localns)
        k_tp = str if _is_universal_json_wildcard(_resolve_annotated_or_ref(args[0], localns)) else args[0]
        return _encode_mapping_strict(obj, depth=depth, ctx=ctx, key_tp=k_tp, val_tp=args[1], localns=localns)
    return None


def _encode_declared_value(
    obj: object,
    declared_tp: object,
    *,
    depth: int,
    ctx: _EncodeCtx,
    localns: Optional[Mapping[str, object]],
) -> JsonValue:
    tp = _resolve_annotated_or_ref(declared_tp, localns)
    if _is_forbidden_any_type(tp):
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "typing.Any is forbidden in DataclassCodec.")
    if isinstance(tp, TypeVar):
        if tp.__constraints__:
            return _encode_union_value(obj, tp, tp.__constraints__, depth=depth, ctx=ctx, localns=localns)
        return _encode_value_checked(obj, depth=depth, ctx=ctx, declared_tp=tp.__bound__, localns=localns)
    if tp is JsonValue or _is_untyped_wildcard(tp):
        if obj is None or type(obj) in (bool, int, float, str):
            return _encode_untyped_value(obj, depth=depth, ctx=ctx)
        if isinstance(obj, (list, tuple)):
            return _encode_declared_container(obj, Sequence, (JsonValue,), depth=depth, ctx=ctx, localns=localns)
        if isinstance(obj, cabc.Mapping):
            return _encode_mapping_strict(obj, depth=depth, ctx=ctx, key_tp=str, val_tp=JsonValue, localns=localns)
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid JSON value of type {type(obj).__name__}")
    if tp in (JsonObject, MutableJsonObject, dict, cabc.Mapping, Mapping):
        return _encode_declared_container(obj, dict, (), depth=depth, ctx=ctx, localns=localns)
    if tp in (list, cabc.Sequence, Sequence, tuple, Tuple, frozenset):
        col_o = frozenset if tp is frozenset else Sequence
        return _encode_declared_container(obj, col_o, (JsonValue,), depth=depth, ctx=ctx, localns=localns)
    if tp is type(None):
        if obj is not None:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected None, got {type(obj).__name__}")
        return None
    if _is_explicit_empty_tuple_type(tp):
        if not isinstance(obj, (tuple, list)) or len(obj) != 0:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Expected empty tuple.")
        return []
    origin = get_origin(tp)
    args = get_args(tp)
    if origin is Literal:
        if not any(_literal_member_matches(obj, lit, path="$") for lit in args):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Literal mismatch: {obj!r}")
        return _encode_untyped_value(obj, depth=depth, ctx=ctx)
    if origin in (Union, UnionType):
        return _encode_union_value(obj, tp, args, depth=depth, ctx=ctx, localns=localns)
    if origin is not None:
        col_res = _encode_declared_container(obj, origin, args, depth=depth, ctx=ctx, localns=localns)
        if col_res is not None:
            return col_res
    if isinstance(origin, type) and dataclasses.is_dataclass(origin):
        if type(obj) is not origin:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected exact {origin.__name__}, got {type(obj).__name__}")
        _validate_generic_dc_type_args(origin, args)
        return _encode_dataclass_checked(
            obj, depth=depth, ctx=ctx, tv_map=dict(zip(_generic_type_params(origin), args)), localns=localns
        )
    if isinstance(tp, type):
        return _encode_declared_leaf_type(obj, tp, depth=depth, ctx=ctx, localns=localns)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported declared type {tp!r}")


def _encode_declared_leaf_type(
    obj: object,
    tp: type[object],
    *,
    depth: int,
    ctx: _EncodeCtx,
    localns: Optional[Mapping[str, object]],
) -> JsonValue:
    if tp is bool:
        if type(obj) is not bool:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected bool, got {type(obj).__name__}")
        return obj
    if tp is int:
        if type(obj) is not int:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected plain int, got {obj!r}")
        return _assert_int64_range(obj, path="$")
    if tp is float:
        if type(obj) not in (int, float):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected finite plain float, got {obj!r}")
        if type(obj) is int:
            _assert_int64_range(obj, path="$")
        f_val = float(obj)
        if not math.isfinite(f_val):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Non-finite float is forbidden: {obj!r}")
        return 0.0 if f_val == 0.0 else f_val
    if tp is str:
        if type(obj) is not str:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected str, got {type(obj).__name__}")
        return _check_str_valid_utf8(obj, path="$")
    if tp is bytes:
        if type(obj) is not bytes:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected bytes, got {type(obj).__name__}")
        return base64.b64encode(obj).decode("ascii")
    if tp in (ModuleId, TaskId, EventId, HostPath) or issubclass(tp, Enum):
        if isinstance(obj, type) or not isinstance(obj, tp):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected {tp.__name__}, got {type(obj).__name__}")
        return _encode_untyped_value(obj, depth=depth, ctx=ctx)
    if dataclasses.is_dataclass(tp):
        if type(obj) is not tp:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Expected exact {tp.__name__}, got {type(obj).__name__}")
        return _encode_dataclass_checked(obj, depth=depth, ctx=ctx, localns=localns)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported declared type {tp!r}")


def _encode_untyped_value(obj: object, *, depth: int, ctx: _EncodeCtx) -> JsonValue:
    if isinstance(obj, Enum):
        return _encode_value_checked(obj.value, depth=depth + 1, ctx=ctx)
    if obj is None or isinstance(obj, bool):
        return obj
    if type(obj) is str:
        return _check_str_valid_utf8(obj, path="$")
    if type(obj) is bytes:
        return base64.b64encode(obj).decode("ascii")
    if type(obj) is int:
        return _assert_int64_range(obj, path="$")
    if type(obj) is float:
        if not math.isfinite(obj):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Non-finite float is forbidden: {obj!r}")
        return 0.0 if obj == 0.0 else obj
    if isinstance(obj, (ModuleId, TaskId, EventId, HostPath)):
        return _check_str_valid_utf8(str(obj), path="$")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _encode_dataclass_checked(obj, depth=depth, ctx=ctx)
    if isinstance(obj, (tuple, list)):
        return [_encode_value_checked(item, depth=depth + 1, ctx=ctx) for item in obj]
    if isinstance(obj, frozenset):
        encoded_items = [_encode_value_checked(item, depth=depth + 1, ctx=ctx) for item in obj]
        return _sort_encoded_frozenset_items(encoded_items)
    if isinstance(obj, cabc.Mapping):
        return _encode_mapping_strict(obj, depth=depth, ctx=ctx)
    raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Unsupported type for DataclassCodec.encode: {type(obj).__name__}")


def _sort_encoded_frozenset_items(items: list[JsonValue]) -> list[JsonValue]:
    if len(items) <= 1:
        return items
    if all(type(x) is str for x in items):
        return sorted(items, key=str)
    return sorted(
        items,
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False),
    )


def _encode_value_checked(
    obj: object,
    *,
    depth: int,
    ctx: _EncodeCtx,
    declared_tp: Optional[object] = None,
    localns: Optional[Mapping[str, object]] = None,
) -> JsonValue:
    if depth > _MAX_CODEC_DEPTH:
        raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Maximum nesting depth exceeded during encode.")
    if declared_tp is not None:
        return _encode_declared_value(obj, declared_tp, depth=depth, ctx=ctx, localns=localns)
    return _encode_untyped_value(obj, depth=depth, ctx=ctx)
