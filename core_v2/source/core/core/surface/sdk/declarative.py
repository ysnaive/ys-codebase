"""Declarative Task/Module/TaskGroup DSL, CLI schema annotations, output protocols, and test fixtures."""

from __future__ import annotations

from abc import ABC, ABCMeta
import collections.abc as cabc
import dataclasses
from dataclasses import dataclass
from enum import Enum
import inspect
import threading
import types
from typing import (
    Annotated,
    Callable,
    ClassVar,
    Generic,
    Literal,
    Mapping,
    Optional,
    Sequence,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)
import weakref

from core.execution.event import EventMetadata, EventOrdering, EventSubscriptionSpec, normalize_payload_filter
from core.execution.lifecycle import LifoResourceStack
from core.execution.runtime import (
    CORE_MODULE_ID,
    BoundTask,
    CliBindingSpec,
    ConcurrencyMode,
    DispatchMode,
    Empty,
    ModuleRuntimeServices,
    PeriodicScheduleSpec,
    SecurityTier,
    Task,
    TaskContext,
    TaskExposure,
    TaskMetadata,
    YscbModule,
    build_default_module_services,
    resolve_active_module_services,
)
from core.filesystem.storage import BlobVault, ModuleDatabase, SchemaMigration, StorageOpenOptions
from core.filesystem.vfs import ScopedVfs
from core.foundation import (
    EnvHash,
    ErrorCode,
    EventId,
    HostPath,
    JsonObject,
    JsonPrimitive,
    JsonValue,
    LocaleCatalog,
    ModuleId,
    Profiler,
    SchemaExporter,
    SemVer4,
    SemanticUri,
    SnapshotGen,
    SpaceId,
    SpacePath,
    StructuredLogger,
    TaskId,
    VersionConstraint,
    YscbError,
    is_valid_type_annotation,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    resolve_dataclass_init_hints,
    validate_relative_segment,
)
from core.metadata.config import register_compiled_module_surface_meta
from core.metadata.contributes import AggregatedContributes, ExtensionPointSpec, compile_extension_points

TIn = TypeVar("TIn")
TPayload = TypeVar("TPayload")
TConfig = TypeVar("TConfig")
TModule_co = TypeVar("TModule_co", bound="Module", covariant=True)
_TFn = TypeVar("_TFn", bound=Callable[..., object])

_ON_MIGRATE_TASK_SUFFIX = "yscb_on_migrate"
_RESERVED_GLOBAL_CLI_FLAGS = frozenset(
    {"-h", "--help", "--json", "--cold", "--approve", "--host-dir", "--profile", "--profile-mem"}
)


def _require_token(value: str, label: str) -> str:
    clean = require_pure_str(value, label, non_empty=True)
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in clean):
        raise ValueError(f"{label} cannot contain whitespace or control characters: {clean!r}")
    return clean


def _validate_storage_rel_name(raw_name: str, *, label: str, add_db_ext: bool) -> str:
    clean = require_pure_str(raw_name, label, non_empty=True).strip()
    if not clean or "://" in clean or "\\" in clean or clean.startswith("/") or clean.endswith("/"):
        raise ValueError(f"Invalid {label} {raw_name!r}: must be a clean relative name under storage.local://@/")
    parts = [seg for seg in clean.split("/")]
    if any(not seg or seg == "@" for seg in parts):
        raise ValueError(f"Invalid {label} {raw_name!r}: empty or '@' segments are forbidden")
    for seg in parts:
        validate_relative_segment(seg, label=label)
    rel = "/".join(parts)
    if add_db_ext and not rel.endswith(".db"):
        rel = f"{rel}.db"
    return rel


@dataclass(frozen=True, slots=True)
class Arg:
    """Positional CLI argument metadata attached via typing.Annotated."""

    summary: str = ""
    name: Optional[str] = None

    def __post_init__(self) -> None:
        require_pure_str(self.summary, "Arg.summary")
        if self.name is not None and (_require_token(self.name, "Arg.name").startswith("-")):
            raise ValueError(f"Arg.name cannot start with '-', got {self.name!r}")


@dataclass(frozen=True, slots=True)
class Option:
    """Named CLI option metadata attached via typing.Annotated."""

    short: Optional[str] = None
    summary: str = ""
    long_name: Optional[str] = None
    group: Optional[str] = None

    def __post_init__(self) -> None:
        require_pure_str(self.summary, "Option.summary")
        if self.short is not None:
            require_pure_str(self.short, "Option.short", non_empty=True)
            stripped = self.short[1:] if self.short.startswith("-") else self.short
            if self.short.startswith("--") or len(stripped) != 1 or not stripped.isalnum():
                raise ValueError(f"Option.short must be one alphanumeric char (optionally '-x'), got {self.short!r}")
            if f"-{stripped}" in _RESERVED_GLOBAL_CLI_FLAGS:
                raise ValueError(f"Option.short '-{stripped}' collides with reserved global CLI flag")
        if self.long_name is not None:
            long_clean = _require_token(self.long_name, "Option.long_name").lstrip("-")
            if not long_clean or "=" in long_clean:
                raise ValueError(
                    f"Option.long_name must contain non-dash characters and forbid '=', got {self.long_name!r}"
                )
            if f"--{long_clean}" in _RESERVED_GLOBAL_CLI_FLAGS:
                raise ValueError(f"Option.long_name '--{long_clean}' collides with reserved global CLI flag")
        if self.group is not None:
            grp_clean = require_pure_str(self.group, "Option.group", non_empty=True).strip()
            if not grp_clean:
                raise ValueError("Option.group cannot be blank whitespace")
            object.__setattr__(self, "group", grp_clean)


@dataclass(frozen=True, slots=True)
class MigrationRequest:
    """Input DTO dispatched to a module's @on_migrate handler during version upgrades."""

    old_version: SemVer4
    new_version: SemVer4

    def __post_init__(self) -> None:
        if not isinstance(self.old_version, SemVer4) or not isinstance(self.new_version, SemVer4):
            raise ValueError("MigrationRequest old_version and new_version must be SemVer4 instances")


class _SdkStateRegistry:
    """Thread-safe weak-key registry for ModuleEnv closer stacks, services, and compiled declarative classes."""

    _INSTANCE: ClassVar[Optional[_SdkStateRegistry]] = None
    _INIT_LOCK: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stacks: weakref.WeakKeyDictionary[ModuleEnv, LifoResourceStack] = weakref.WeakKeyDictionary()
        self._services: weakref.WeakKeyDictionary[ModuleEnv, ModuleRuntimeServices] = weakref.WeakKeyDictionary()
        self._classes: weakref.WeakKeyDictionary[type[object], _CompiledClassMeta] = weakref.WeakKeyDictionary()
        self._group_parents: weakref.WeakKeyDictionary[TaskGroup[Module], Module] = weakref.WeakKeyDictionary()

    @classmethod
    def instance(cls) -> _SdkStateRegistry:
        if cls._INSTANCE is None:
            with cls._INIT_LOCK:
                cls._INSTANCE = cls._INSTANCE or cls()
        return cls._INSTANCE

    def env_stack(self, env: ModuleEnv) -> LifoResourceStack:
        with self._lock:
            return self._stacks.setdefault(env, LifoResourceStack())

    def bind_env_services(self, env: ModuleEnv, services: ModuleRuntimeServices) -> None:
        with self._lock:
            self._services[env] = services

    def env_services(self, env: ModuleEnv) -> ModuleRuntimeServices:
        with self._lock:
            existing = self._services.get(env)
        if existing is not None:
            return existing
        fallback = build_default_module_services(env.workspace_root, CORE_MODULE_ID)
        with self._lock:
            return self._services.setdefault(env, fallback)

    def classify_bases(self, bases: tuple[type[object], ...]) -> Optional[str]:
        with self._lock:
            for base in bases:
                for anc in base.__mro__:
                    if (meta := self._classes.get(anc)) is not None and meta.kind.startswith("root_"):
                        return "task_group" if meta.kind == "root_group" else "module"
        return None

    def put_meta(self, cls_obj: type[object], meta: _CompiledClassMeta) -> None:
        with self._lock:
            self._classes[cls_obj] = meta

    def get_meta(self, cls_obj: type[object]) -> Optional[_CompiledClassMeta]:
        with self._lock:
            return self._classes.get(cls_obj)

    def require_entries(self, cls_obj: type[object]) -> tuple[_CompiledMethodEntry, ...]:
        if (meta := self.get_meta(cls_obj)) is None:
            raise ValueError(f"Unregistered TaskGroup {cls_obj.__name__}")
        return meta.entries

    def bind_group_parent(self, group: TaskGroup[Module], module: Module) -> None:
        with self._lock:
            self._group_parents[group] = module

    def get_group_parent(self, group: TaskGroup[Module]) -> Optional[Module]:
        with self._lock:
            return self._group_parents.get(group)


class ModuleEnv:
    """Lifecycle environment passed to Module and TaskGroup init and warmup hooks."""

    __slots__ = ("_workspace_root", "__weakref__")

    def __init__(self, workspace_root: HostPath) -> None:
        if not isinstance(workspace_root, HostPath):
            raise TypeError(f"ModuleEnv.workspace_root must be HostPath, got {type(workspace_root).__name__}")
        self._workspace_root = workspace_root

    @property
    def module_id(self) -> ModuleId:
        return _SdkStateRegistry.instance().env_services(self).module_id

    @property
    def workspace_root(self) -> HostPath:
        return self._workspace_root

    @property
    def vfs(self) -> ScopedVfs:
        return _SdkStateRegistry.instance().env_services(self).vfs

    @property
    def logger(self) -> StructuredLogger:
        return _SdkStateRegistry.instance().env_services(self).logger

    @property
    def locale(self) -> LocaleCatalog:
        return _SdkStateRegistry.instance().env_services(self).locale

    @property
    def profiler(self) -> Profiler:
        return _SdkStateRegistry.instance().env_services(self).profiler

    def register_closer(self, fn: Callable[[], None]) -> None:
        """Register a zero-argument teardown callback executed in LIFO order on shutdown."""
        if not callable(fn):
            raise TypeError("ModuleEnv.register_closer requires a zero-arg callable")
        _SdkStateRegistry.instance().env_stack(self).push_closeable("module_env", fn)

    def load_config(self, config_cls: type[TConfig]) -> TConfig:
        """Decode this module's 2x2 configuration matrix into config_cls."""
        svc = _SdkStateRegistry.instance().env_services(self)
        return cast(TConfig, svc.config_loader(config_cls))

    def load_contributes(self) -> AggregatedContributes:
        """Load aggregated Contributes 2.0 extensions targeting this module."""
        return _SdkStateRegistry.instance().env_services(self).contributes_loader()

    def open_database(
        self,
        name: str,
        *,
        migrations: Sequence[SchemaMigration] = (),
        options: StorageOpenOptions = StorageOpenOptions(),
    ) -> ModuleDatabase:
        """Open a SQLite WAL database under storage.local://@/<name>.db and auto-register LIFO close."""
        rel_db = _validate_storage_rel_name(name, label="database name", add_db_ext=True)
        db = ModuleDatabase(
            self.vfs,
            SemanticUri("storage.local", f"@/{rel_db}"),
            migrations=migrations,
            options=options,
            profiler=self.profiler,
        )
        try:
            self.register_closer(db.close)
        except BaseException:
            db.close()
            raise
        return db

    def open_blob_vault(self, name: str) -> BlobVault:
        """Open a content-addressed/keyed BlobVault rooted at storage.local://@/<name>."""
        rel_vault = _validate_storage_rel_name(name, label="blob vault name", add_db_ext=False)
        return BlobVault(self.vfs, SemanticUri("storage.local", f"@/{rel_vault}"))


def define_event(
    event_id: str, payload_type: type[TPayload] = Empty, *, ordered: bool = False, description: str = ""
) -> EventMetadata[TPayload]:
    """Declare a typed event metadata contract for @on_event subscriptions."""
    eid = event_id if isinstance(event_id, EventId) else EventId(require_pure_str(event_id, "event_id", non_empty=True))
    if _contains_any_type(payload_type) or payload_type is type(None) or not is_valid_type_annotation(payload_type):
        raise ValueError(f"define_event payload_type must be a strict non-Any annotation, got {payload_type!r}")
    ordering = EventOrdering.ORDERED if require_pure_bool(ordered, "ordered") else EventOrdering.UNORDERED
    return EventMetadata(event_id=eid, payload_type=payload_type, ordering=ordering, description=require_pure_str(description, "description"))


@dataclass(frozen=True, slots=True)
class _TaskDeclSpec:
    cli: Optional[tuple[str, ...]] = None
    task_name: Optional[str] = None
    summary: str = ""
    aliases: tuple[str, ...] = ()
    usage_pros: tuple[str, ...] = ()
    usage_cons: tuple[str, ...] = ()
    dispatch_mode: DispatchMode = DispatchMode.HYBRID
    interactive_tty: bool = False
    security: SecurityTier = SecurityTier.SAFE
    lock: Optional[str] = None
    concurrency: ConcurrencyMode = ConcurrencyMode.PARALLEL
    equivalence_fn: Optional[Callable[[object], str]] = None
    timeout_ms: Optional[int] = None


@dataclass(frozen=True, slots=True)
class _EventDeclSpec:
    event: EventMetadata[object] | EventId
    payload_filter: Optional[Mapping[str, tuple[JsonPrimitive, ...]]]
    mapper: Optional[Callable[[Sequence[object]], Optional[object]]]
    payload_type: Optional[type[object]]


@dataclass(frozen=True, slots=True)
class _DecoratedMethod:
    """Immutable callable descriptor accumulating @task, @on_event, @periodic, or @on_migrate specs."""

    fn: Callable[..., object]
    task_spec: Optional[_TaskDeclSpec] = None
    events: tuple[_EventDeclSpec, ...] = ()
    periodic_spec: Optional[PeriodicScheduleSpec] = None
    is_migrate: bool = False

    @property
    def __wrapped__(self) -> Callable[..., object]:
        return self.fn

    def __get__(self, instance: object, _owner: Optional[type[object]] = None) -> object:
        return self if instance is None else types.MethodType(self.fn, instance)

    def __call__(self, *args: object, **kwargs: object) -> object:
        return self.fn(*args, **kwargs)


@dataclass(frozen=True, slots=True)
class _ParsedCallableSig:
    has_req: bool
    ctx_first: bool
    input_type: type[object]
    output_type: type[object]
    none_return: bool
    summary_fallback: str


@dataclass(frozen=True, slots=True)
class _CompiledMethodEntry:
    method_name: str
    decorated: _DecoratedMethod
    parsed_sig: _ParsedCallableSig


def _resolve_method_hints(fn: Callable[..., object], fn_label: str) -> dict[str, object]:
    target = fn if isinstance(fn, (types.FunctionType, types.MethodType, types.BuiltinFunctionType)) else type(fn).__call__
    if isinstance(target, types.BuiltinFunctionType):
        return {}
    try:
        try:
            return get_type_hints(target, include_extras=True)
        except NameError:
            scopes: list[dict[str, object]] = []
            frame = inspect.currentframe()
            try:
                while frame is not None:
                    if frame.f_code.co_filename != __file__:
                        scopes.append(dict(frame.f_locals))
                    frame = frame.f_back
            finally:
                del frame
            return get_type_hints(target, localns={k: v for s in reversed(scopes) for k, v in s.items()}, include_extras=True)
    except Exception as exc:
        raise ValueError(f"Invalid type annotation on {fn_label}: {exc}") from exc


def _contains_any_type(tp: object) -> bool:
    if repr(tp) == "typing.Any" or (origin := get_origin(tp)) is None:
        return repr(tp) == "typing.Any"
    args = get_args(tp)
    return repr(origin) == "typing.Any" or (_contains_any_type(args[0]) if (origin is Annotated and args) else any(_contains_any_type(a) for a in args))


_SDK_SCALAR_VO_TYPES: frozenset[type[object]] = frozenset(
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
        SnapshotGen,
        EnvHash,
    }
)


def _is_non_scalar_dataclass_input(tp: object) -> bool:
    cur = tp
    while get_origin(cur) is Annotated:
        cur = get_args(cur)[0]
    if cur is Empty:
        return True
    origin = get_origin(cur)
    if isinstance(cur, type) and dataclasses.is_dataclass(cur) and cur not in _SDK_SCALAR_VO_TYPES:
        if Generic in cur.__mro__ and bool(cur.__parameters__):
            return False
        return True
    if isinstance(origin, type) and dataclasses.is_dataclass(origin) and origin not in _SDK_SCALAR_VO_TYPES:
        return True
    return False


def _unwrap_cli_dto_field(raw_tp: object) -> tuple[object, object, bool]:
    cur = raw_tp
    marker: object = None
    is_opt = False
    while True:
        origin = get_origin(cur)
        if origin is Annotated:
            ann_args = get_args(cur)
            cur = ann_args[0]
            for meta_item in ann_args[1:]:
                if isinstance(meta_item, (Arg, Option)):
                    if marker is not None:
                        raise ValueError(f"Field annotation cannot combine multiple Arg/Option markers: {raw_tp!r}")
                    marker = meta_item
            continue
        if origin in (Union, types.UnionType):
            u_args = get_args(cur)
            non_none = [a for a in u_args if a is not type(None)]
            if len(non_none) == 1 and len(non_none) < len(u_args):
                is_opt = True
                cur = non_none[0]
                continue
        break
    return (cur, marker, is_opt)


def _check_cli_choice_homogeneity_and_is_bool(inner_tp: object) -> tuple[bool, bool]:
    cur = inner_tp
    while get_origin(cur) is Annotated:
        cur = get_args(cur)[0]
    origin = get_origin(cur)
    if origin in (Union, types.UnionType):
        non_none = [a for a in get_args(cur) if a is not type(None)]
        if len(non_none) == 1:
            return _check_cli_choice_homogeneity_and_is_bool(non_none[0])
        raise ValueError(f"Multi-type Union CLI field annotation is unsupported: {cur!r}")
    if origin in (list, tuple, Sequence, cabc.Sequence, frozenset):
        args = get_args(cur)
        if origin is tuple and not (len(args) == 2 and args[1] is Ellipsis):
            raise ValueError(
                f"Fixed-length or heterogeneous tuple CLI annotation is unsupported (use tuple[T, ...]): {cur!r}"
            )
        if args and args[0] is not Ellipsis:
            _elem_bool, elem_is_seq = _check_cli_choice_homogeneity_and_is_bool(args[0])
            if elem_is_seq:
                raise ValueError(f"Nested sequence CLI annotation is unsupported: {cur!r}")
        return (False, True)
    if origin is Literal or (isinstance(cur, type) and issubclass(cur, Enum)):
        raw_vals = get_args(cur) if origin is Literal else tuple(cur)
        if not raw_vals:
            raise ValueError("CLI Literal or Enum annotation cannot be empty")
        unwrapped = [v.value if isinstance(v, Enum) else v for v in raw_vals]
        if all(type(v) is bool for v in unwrapped):
            return (True, False)
        if (
            all(type(v) is int for v in unwrapped)
            or all(type(v) is float for v in unwrapped)
            or all(type(v) is str for v in unwrapped)
        ):
            return (False, False)
        raise ValueError(f"Heterogeneous or non-scalar CLI Literal/Enum choices are unsupported: {unwrapped!r}")
    return (cur is bool, False)


def _validate_cli_dto_option_flags(task_id: TaskId, input_type: object) -> None:
    cur = input_type
    while get_origin(cur) is Annotated:
        cur = get_args(cur)[0]
    if cur is Empty:
        return
    origin_tp = get_origin(cur)
    subst_map: dict[object, object] = {}
    if isinstance(cur, type) and dataclasses.is_dataclass(cur):
        dc_cls = cur
    elif isinstance(origin_tp, type) and dataclasses.is_dataclass(origin_tp):
        dc_cls = origin_tp
        if Generic in dc_cls.__mro__:
            subst_map = dict(zip(dc_cls.__parameters__, get_args(cur)))
    else:
        return
    raw_hints = resolve_dataclass_init_hints(dc_cls)
    seen_variadic_arg = False
    seen_optional_arg = False
    seen_flags: set[str] = set()
    implicit_neg_flags: set[str] = set()
    for fld in dataclasses.fields(dc_cls):
        if not fld.init:
            continue
        eff_tp = _subst_generic_typevars(raw_hints.get(fld.name, fld.type), subst_map) if subst_map else raw_hints.get(fld.name, fld.type)
        inner_tp, marker, is_opt = _unwrap_cli_dto_field(eff_tp)
        is_scalar_bool, is_seq = _check_cli_choice_homogeneity_and_is_bool(inner_tp)
        if isinstance(marker, Arg):
            has_dflt = (fld.default is not dataclasses.MISSING) or (fld.default_factory is not dataclasses.MISSING)
            is_req_arg = (not has_dflt) and (not is_opt)
            if seen_variadic_arg:
                raise ValueError(f"Task '{task_id}': variadic positional Arg must be the final Arg field")
            if is_req_arg and seen_optional_arg:
                raise ValueError(
                    f"Task '{task_id}': required positional Arg '{fld.name}' cannot follow an optional positional Arg"
                )
            if is_seq:
                seen_variadic_arg = True
            if not is_req_arg:
                seen_optional_arg = True
            continue
        opt_meta = marker if isinstance(marker, Option) else Option()
        long_raw = opt_meta.long_name if opt_meta.long_name is not None else fld.name.replace("_", "-")
        long_clean = long_raw.lstrip("-")
        short_clean = opt_meta.short.lstrip("-") if opt_meta.short is not None else None
        for flag_tok in (f"--{long_clean}", f"-{short_clean}" if short_clean else ""):
            if flag_tok:
                if flag_tok in _RESERVED_GLOBAL_CLI_FLAGS:
                    raise ValueError(
                        f"Task '{task_id}': CLI option flag '{flag_tok}' collides with reserved global CLI flag"
                    )
                if flag_tok in seen_flags or flag_tok in implicit_neg_flags:
                    raise ValueError(f"Task '{task_id}': duplicate or colliding CLI option flag '{flag_tok}'")
                seen_flags.add(flag_tok)
        if is_scalar_bool:
            neg_tok = f"--no-{long_clean}"
            if neg_tok in _RESERVED_GLOBAL_CLI_FLAGS or neg_tok in seen_flags or neg_tok in implicit_neg_flags:
                raise ValueError(
                    f"Task '{task_id}': negated boolean CLI flag '{neg_tok}' collides with another option"
                )
            implicit_neg_flags.add(neg_tok)


def _is_valid_sdk_task_input_type(tp: object) -> bool:
    cur = tp
    while get_origin(cur) is Annotated:
        cur = get_args(cur)[0]
    if _is_non_scalar_dataclass_input(cur):
        return True
    if cur in (object, dict, Mapping, cabc.Mapping, JsonObject, JsonValue):
        return True
    origin = get_origin(cur)
    if origin in (dict, Mapping, cabc.Mapping):
        args = get_args(cur)
        return not args or args[0] is str
    if origin in (Union, types.UnionType):
        branches = [b for b in get_args(cur) if b is not type(None)]
        return bool(branches) and all(_is_valid_sdk_task_input_type(b) for b in branches)
    return False


def _validate_sig_type(tp: object, fn_label: str, *, role: str, allow_none: bool) -> type[object]:
    if tp is type(None) and allow_none:
        return Empty
    if tp is type(None) or (not allow_none and tp is TaskContext) or _contains_any_type(tp) or not is_valid_type_annotation(tp):
        raise ValueError(f"Invalid task {role} annotation {tp!r} on {fn_label}")
    return cast(type[object], tp)


def _parse_callable_signature(fn: Callable[..., object], *, expect_self: bool, require_return_ann: bool) -> _ParsedCallableSig:
    fn_label = fn.__qualname__ if isinstance(fn, (types.FunctionType, types.MethodType, type)) else type(fn).__qualname__
    params = list(inspect.signature(fn).parameters.values())
    if any(p.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY) or p.default is not inspect.Parameter.empty for p in params):
        raise ValueError(f"Task handler {fn_label} only supports positional parameters without defaults")
    if len(params) not in ((2, 3) if expect_self else (1, 2)):
        raise ValueError(f"Task handler {fn_label} must accept {'(self, ctx) or (self, req, ctx)' if expect_self else '(ctx) or (req, ctx)'}")
    hints, eff = _resolve_method_hints(fn, fn_label), (params[1:] if expect_self else params)
    has_req, ctx_first, input_type, ctx_p = len(eff) == 2, False, cast(type[object], Empty), eff[0]
    if has_req:
        p0, p1 = eff
        ctx_first = hints.get(p0.name) is TaskContext or (p0.name == "ctx" and p0.name not in hints and p1.name in hints)
        ctx_p, req_p = (p0, p1) if ctx_first else (p1, p0)
        if req_p.name not in hints:
            raise ValueError(f"Task parameter {req_p.name!r} on {fn_label} requires a type annotation")
        input_type = _validate_sig_type(hints[req_p.name], fn_label, role="input", allow_none=False)
    if ctx_p.name in hints and hints[ctx_p.name] is not TaskContext:
        raise ValueError(f"Task context parameter {ctx_p.name!r} on {fn_label} must be TaskContext")
    if "return" not in hints and require_return_ann:
        raise ValueError(f"Task method {fn_label} must declare a return annotation (use -> None for Empty)")
    output_type, none_return = (
        (cast(type[object], object), False)
        if "return" not in hints
        else (_validate_sig_type(hints["return"], fn_label, role="return", allow_none=True), hints["return"] is type(None))
    )
    doc_first = next((s for line in (inspect.getdoc(fn) or "").splitlines() if (s := line.strip())), "")
    return _ParsedCallableSig(has_req, ctx_first, input_type, output_type, none_return, doc_first)


def _qualify_task_id(module_id: ModuleId, raw_name: str, *, label: str = "task name", allow_foreign: bool = False) -> TaskId:
    clean = _require_token(raw_name, label)
    if "." not in clean:
        return TaskId(f"{module_id.value}.{clean}")
    tid = TaskId(clean)
    if not allow_foreign and tid.module_id != module_id:
        raise ValueError(f"Task {clean!r} must belong to module {module_id.value!r}")
    return tid


def _normalize_exec_policy(
    security: SecurityTier, lock: Optional[str], concurrency: Optional[ConcurrencyMode], *, owner: str
) -> tuple[SecurityTier, Optional[str], ConcurrencyMode]:
    if not isinstance(security, SecurityTier):
        raise ValueError(f"{owner} security must be SecurityTier, got {security!r}")
    if concurrency is not None and not isinstance(concurrency, ConcurrencyMode):
        raise ValueError(f"{owner} concurrency must be ConcurrencyMode or None, got {concurrency!r}")
    norm_lock = require_pure_str(lock, "lock", non_empty=True) if lock is not None else None
    eff_conc = concurrency if concurrency is not None else (ConcurrencyMode.SERIALIZE if norm_lock is not None else ConcurrencyMode.PARALLEL)
    return (security, norm_lock, eff_conc)


def _resolve_task_metadata(module_id: ModuleId, entry: _CompiledMethodEntry, *, allow_foreign_module: bool = False) -> TaskMetadata[object, object]:
    dec, parsed = entry.decorated, entry.parsed_sig
    if dec.is_migrate:
        if not parsed.has_req or parsed.input_type is not MigrationRequest or not parsed.none_return:
            raise ValueError(
                f"@on_migrate method {entry.method_name!r} must declare (self, req: MigrationRequest, ctx: TaskContext) -> None"
            )
        return TaskMetadata(
            task_id=TaskId(f"{module_id.value}.{_ON_MIGRATE_TASK_SUFFIX}"),
            input_type=MigrationRequest,
            output_type=Empty,
            exposure=TaskExposure.INTERNAL_TRIGGER,
        )
    decl = dec.task_spec or _TaskDeclSpec()
    tid = _qualify_task_id(module_id, decl.task_name, label="@task name", allow_foreign=allow_foreign_module) if decl.task_name is not None else TaskId(f"{module_id.value}.{entry.method_name}")
    if dec.events or dec.periodic_spec is not None:
        if decl.security in (SecurityTier.GATED, SecurityTier.CRITICAL):
            raise ValueError(f"Task {tid.value!r} with {decl.security.name} cannot bind @on_event or @periodic")
        if decl.dispatch_mode == DispatchMode.COLD_ONLY:
            raise ValueError(f"Task {tid.value!r} with DispatchMode.COLD_ONLY cannot bind @on_event or @periodic")
    cli_spec: Optional[CliBindingSpec] = None
    if decl.cli is not None:
        if len(decl.cli) == 0:
            if module_id == CORE_MODULE_ID:
                raise ValueError("Built-in 'core' module cannot declare a module-root cli=() default task")
            if decl.aliases:
                raise ValueError(
                    f"Module-root default task {tid.value!r} with cli=() cannot declare task-level aliases; use Module.aliases"
                )
            eff_cmd_path = (module_id.value,)
        else:
            eff_cmd_path = decl.cli
        cli_spec = CliBindingSpec(
            eff_cmd_path,
            decl.summary or parsed.summary_fallback or f"Execute {tid.value}",
            decl.aliases,
            decl.usage_pros,
            decl.usage_cons,
        )
    exposure = TaskExposure.CLI_AND_SDK if cli_spec is not None else (TaskExposure.SDK_ONLY if dec.task_spec is not None else TaskExposure.INTERNAL_TRIGGER)
    if cli_spec is not None:
        if not _is_non_scalar_dataclass_input(parsed.input_type):
            raise ValueError(
                f"CLI task {tid.value!r} input_type must be Empty or a non-scalar request @dataclass DTO, got {parsed.input_type!r}"
            )
        _validate_cli_dto_option_flags(tid, parsed.input_type)
    elif not _is_valid_sdk_task_input_type(parsed.input_type):
        raise ValueError(
            f"Task {tid.value!r} input_type must encode as a JSON object (Empty, request @dataclass, or Mapping[str, ...]), got {parsed.input_type!r}"
        )
    for ev in dec.events:
        if ev.mapper is None and parsed.input_type is not Empty:
            raise ValueError(
                f"@on_event without mapper on {entry.method_name!r} requires a parameterless (self, ctx) task method; "
                "pass mapper=lambda batch: MyReq(...) to inspect payloads or declare (self, ctx: TaskContext)."
            )
    subs = tuple(EventSubscriptionSpec(
        event=ev.event, payload_filter=ev.payload_filter, payload_type=ev.payload_type,
        batch_mapper=ev.mapper if ev.mapper is not None else (lambda batch: Empty() if batch else None),
    ) for ev in dec.events)
    return TaskMetadata(
        task_id=tid, input_type=parsed.input_type, output_type=parsed.output_type, exposure=exposure, cli=cli_spec,
        dispatch_mode=decl.dispatch_mode, interactive_tty=decl.interactive_tty, security_tier=decl.security,
        resource_key=decl.lock, concurrency_mode=decl.concurrency, equivalence_fn=decl.equivalence_fn, timeout_ms=decl.timeout_ms,
        subscriptions=subs, periodic=dec.periodic_spec,
    )


class _SdkBoundTask(Task[object, object]):
    """Concrete Task adapter dispatching calls to a declarative method or InMemoryModule handler."""

    def __init__(self, metadata: TaskMetadata[object, object], fn: Callable[..., object], parsed: _ParsedCallableSig) -> None:
        self._metadata, self._fn, self._parsed = metadata, fn, parsed

    @property
    def metadata(self) -> TaskMetadata[object, object]:
        return self._metadata

    def run(self, req: object, ctx: TaskContext) -> object:
        p = self._parsed
        result = self._fn(ctx) if not p.has_req else (self._fn(ctx, req) if p.ctx_first else self._fn(req, ctx))
        if p.none_return and result is not None:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Task {self._metadata.task_id.value!r} declared -> None but returned {type(result).__name__}")
        return Empty() if p.none_return else result


class _SdkYscbModule(YscbModule):
    """Runtime YscbModule adapter bridging declarative Module/TaskGroup or InMemoryModule tasks."""

    def __init__(self, module_id: ModuleId, bound_tasks: tuple[BoundTask, ...], module_obj: Optional[Module] = None, group_objs: tuple[TaskGroup[Module], ...] = ()) -> None:
        self._module_id, self._bound_tasks, self._module_obj, self._group_objs = module_id, bound_tasks, module_obj, group_objs

    @property
    def module_id(self) -> ModuleId:
        return self._module_id

    def tasks(self) -> Sequence[BoundTask]:
        return self._bound_tasks

    def _finish_teardown(self, stack: LifoResourceStack, phase: str) -> None:
        if errs := stack.close_all_lifo():
            raise YscbError(ErrorCode.TEARDOWN_ERROR, f"Module {self._module_id.value!r} {phase} failed: {'; '.join(e.message for e in errs)}")

    def _run_hook_phase(self, workspace_root: HostPath, *, is_init: bool) -> Optional[Callable[[], None]]:
        if self._module_obj is None:
            return None
        registry = _SdkStateRegistry.instance()
        env = ModuleEnv(workspace_root)
        registry.bind_env_services(env, resolve_active_module_services(workspace_root, self._module_id))
        stack = registry.env_stack(env)
        try:
            for target in (self._module_obj, *self._group_objs):
                if is_init:
                    stack.push_closeable(self._module_id.value if target is self._module_obj else type(target).__name__, target.on_close)
                    target.on_init(env)
                else:
                    target.on_warmup(env)
        except BaseException:
            stack.close_all_lifo()
            raise
        return lambda: self._finish_teardown(stack, "teardown" if is_init else "warmup teardown")

    def on_init(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        return self._run_hook_phase(workspace_root, is_init=True)

    def on_start(self, workspace_root: HostPath) -> Optional[Callable[[], None]]:
        return self._run_hook_phase(workspace_root, is_init=False)


@dataclass(frozen=True, slots=True)
class _CompiledClassMeta:
    kind: str
    module_id: Optional[ModuleId]
    groups: tuple[type[TaskGroup[Module]], ...]
    entries: tuple[_CompiledMethodEntry, ...]
    is_abstract: bool = False


def _validate_task_and_cli_uniqueness(
    metadatas: Sequence[TaskMetadata[object, object]],
    *,
    root_default_ids: frozenset[TaskId] = frozenset(),
    owner_module_id: Optional[ModuleId] = None,
) -> None:
    if len(root_default_ids) > 1:
        raise ValueError("At most one cli=() root default task is allowed per Module/TaskGroup")
    group_segments = {
        (cli.command_path[:i], cli.command_path[i])
        for meta in metadatas
        if meta.task_id not in root_default_ids and (cli := meta.cli) is not None
        for i in range(len(cli.command_path) - 1)
    }
    seen_ids, seen_cli, seen_tokens = set(), set(), set()
    for meta in metadatas:
        if meta.task_id in seen_ids:
            raise ValueError(f"Duplicate task_id {meta.task_id.value!r}")
        seen_ids.add(meta.task_id)
        if meta.task_id in root_default_ids:
            continue
        if (cli := meta.cli) is not None:
            if root_default_ids and owner_module_id is not None and cli.command_path == (owner_module_id.value,):
                raise ValueError(
                    f"CLI subcommand {cli.command_path!r} collides with module-root cli=() default task on module {owner_module_id.value!r}"
                )
            if cli.command_path in seen_cli:
                raise ValueError(f"Duplicate CLI command path {cli.command_path!r}")
            seen_cli.add(cli.command_path)
            parent_path = cli.command_path[:-1]
            for al in cli.aliases:
                if (parent_path, al) in group_segments:
                    raise ValueError(
                        f"CLI alias {al!r} on {cli.command_path!r} collides with subcommand group under {parent_path!r}"
                    )
            for token in (cli.command_path[-1],) + cli.aliases:
                if (key := (parent_path, token)) in seen_tokens:
                    raise ValueError(f"CLI command/alias collision under parent {parent_path!r}: {token!r}")
                seen_tokens.add(key)


def _collect_entries_from_class(cls_obj: type[object], namespace: Mapping[str, object], registry: _SdkStateRegistry) -> tuple[_CompiledMethodEntry, ...]:
    merged: dict[str, _CompiledMethodEntry] = {}
    for base in reversed(cls_obj.__mro__):
        if base not in (cls_obj, object) and (base_meta := registry.get_meta(base)) is not None and not base_meta.kind.startswith("root_"):
            merged.update({entry.method_name: entry for entry in base_meta.entries})
    for attr_name, raw_val in namespace.items():
        if isinstance(raw_val, _DecoratedMethod):
            merged[attr_name] = _CompiledMethodEntry(attr_name, raw_val, _parse_callable_signature(raw_val.fn, expect_self=True, require_return_ann=True))
        else:
            merged.pop(attr_name, None)
    return tuple(merged.values())


def _read_module_groups(cls_obj: type[Module], registry: _SdkStateRegistry) -> tuple[type[TaskGroup[Module]], ...]:
    if not isinstance(raw_groups := cls_obj.groups, (tuple, list)):
        raise ValueError(f"{cls_obj.__name__}.groups must be a tuple of TaskGroup subclasses")
    normalized: list[type[TaskGroup[Module]]] = []
    for grp in raw_groups:
        grp_meta = registry.get_meta(grp) if isinstance(grp, type) else None
        if (
            not isinstance(grp, type)
            or not issubclass(grp, TaskGroup)
            or grp is TaskGroup
            or inspect.isabstract(grp)
            or grp_meta is None
            or grp_meta.is_abstract
        ):
            raise ValueError(f"{cls_obj.__name__}.groups entries must be concrete TaskGroup subclasses, got {grp!r}")
        if grp in normalized:
            raise ValueError(f"Duplicate TaskGroup {grp.__name__} in {cls_obj.__name__}.groups")
        normalized.append(grp)
    return tuple(normalized)


def _subst_generic_typevars(tp: object, subst_map: Mapping[object, object]) -> object:
    if tp in subst_map:
        return subst_map[tp]
    origin = get_origin(tp)
    if origin is None:
        return tp
    args = get_args(tp)
    if not args:
        return tp
    if origin is Annotated:
        return Annotated[(_subst_generic_typevars(args[0], subst_map), *args[1:])]
    new_args = tuple(_subst_generic_typevars(a, subst_map) for a in args)
    if new_args == args:
        return tp
    if origin is types.UnionType:
        acc = new_args[0]
        for nxt in new_args[1:]:
            acc = Union[acc, nxt]
        return acc
    return origin[new_args]


def _assert_frozen_slots_dataclass_tree(tp: object, label: str, visited: set[object]) -> None:
    if _contains_any_type(tp):
        raise ValueError(f"{label} forbids typing.Any: {tp!r}")
    if isinstance(tp, TypeVar):
        return
    origin = get_origin(tp)
    if origin is Annotated:
        args = get_args(tp)
        if args:
            _assert_frozen_slots_dataclass_tree(args[0], label, visited)
        return
    if origin in (Union, types.UnionType, tuple, list, Sequence, cabc.Sequence, frozenset, Mapping, cabc.Mapping, dict):
        for arg in get_args(tp):
            if arg is not Ellipsis and arg is not type(None):
                _assert_frozen_slots_dataclass_tree(arg, label, visited)
        return
    if isinstance(origin, type) and dataclasses.is_dataclass(origin):
        t_args = get_args(tp)
        visit_key = (origin, t_args)
        if visit_key in visited:
            return
        visited.add(visit_key)
        for arg in t_args:
            if arg is not Ellipsis and arg is not type(None) and not isinstance(arg, TypeVar):
                if not is_valid_type_annotation(arg):
                    raise ValueError(f"Invalid generic type argument on {label}: {arg!r}")
                _assert_frozen_slots_dataclass_tree(arg, label, visited)
        members_g = dict(inspect.getmembers_static(origin))
        dc_params_g = members_g.get("__dataclass_params__")
        has_slots_g = ("__slots__" in members_g) and ("__dict__" not in members_g) and (origin.__dictoffset__ == 0)
        if not bool(dc_params_g is not None and dc_params_g.frozen is True) or not has_slots_g:
            raise ValueError(f"{label} dataclass {origin.__name__} must declare @dataclass(frozen=True, slots=True)")
        try:
            raw_hints_g = resolve_dataclass_init_hints(origin)
        except YscbError as exc:
            raise ValueError(f"Invalid annotations on {label} dataclass {origin.__name__}: {exc.detail.message}") from exc
        subst_map = dict(zip(origin.__parameters__, t_args)) if Generic in origin.__mro__ else {}
        for fld in dataclasses.fields(origin):
            fld_tp = _subst_generic_typevars(raw_hints_g.get(fld.name, fld.type), subst_map)
            if not is_valid_type_annotation(fld_tp):
                raise ValueError(f"Invalid field annotation {fld.name!r} on {origin.__name__}: {fld_tp!r}")
            _assert_frozen_slots_dataclass_tree(fld_tp, f"{label}.{fld.name}", visited)
        return
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        if tp in visited:
            return
        visited.add(tp)
        members = dict(inspect.getmembers_static(tp))
        dc_params = members.get("__dataclass_params__")
        is_frozen = bool(dc_params is not None and dc_params.frozen is True)
        has_slots = ("__slots__" in members) and ("__dict__" not in members) and (tp.__dictoffset__ == 0)
        if not is_frozen or not has_slots:
            raise ValueError(f"{label} dataclass {tp.__name__} must declare @dataclass(frozen=True, slots=True)")
        try:
            field_hints = resolve_dataclass_init_hints(tp)
        except YscbError as exc:
            raise ValueError(f"Invalid annotations on {label} dataclass {tp.__name__}: {exc.detail.message}") from exc
        for fld in dataclasses.fields(tp):
            fld_tp = field_hints.get(fld.name, fld.type)
            if not is_valid_type_annotation(fld_tp):
                raise ValueError(f"Invalid field annotation {fld.name!r} on {tp.__name__}: {fld_tp!r}")
            _assert_frozen_slots_dataclass_tree(fld_tp, f"{label}.{fld.name}", visited)


def _validate_module_config_and_ext_points(mod_cls: type[Module], mod_id: Optional[ModuleId]) -> None:
    require_pure_str(mod_cls.description, f"{mod_cls.__name__}.description")
    if not isinstance(raw_aliases := mod_cls.aliases, tuple):
        raise ValueError(f"{mod_cls.__name__}.aliases must be tuple[str, ...]")
    seen_al: set[str] = set()
    for al in raw_aliases:
        clean_al = _require_token(al, f"{mod_cls.__name__}.aliases entry")
        if clean_al.startswith("-"):
            raise ValueError(f"{mod_cls.__name__}.aliases entry cannot start with '-': {clean_al!r}")
        if clean_al in seen_al or (mod_id is not None and clean_al == mod_id.value):
            raise ValueError(f"Duplicate or self-colliding alias {clean_al!r} on {mod_cls.__name__}")
        seen_al.add(clean_al)
    cfg_tp = mod_cls.config_type
    if cfg_tp is not None:
        if not isinstance(cfg_tp, type) or not dataclasses.is_dataclass(cfg_tp):
            raise ValueError(f"{mod_cls.__name__}.config_type must be a @dataclass(frozen=True, slots=True) class or None")
        _assert_frozen_slots_dataclass_tree(cfg_tp, f"{mod_cls.__name__}.config_type", set())
        try:
            _ = SchemaExporter.export(cfg_tp, title=f"{mod_cls.__name__}Config")
        except YscbError as exc:
            raise ValueError(f"Invalid {mod_cls.__name__}.config_type schema: {exc.detail.message}") from exc
    if not isinstance(raw_eps := mod_cls.extension_points, tuple):
        raise ValueError(f"{mod_cls.__name__}.extension_points must be tuple[ExtensionPointSpec, ...]")
    for ep in raw_eps:
        if not isinstance(ep, ExtensionPointSpec):
            raise ValueError(f"{mod_cls.__name__}.extension_points entries must be ExtensionPointSpec, got {ep!r}")
    if raw_eps:
        target_mid = mod_id if mod_id is not None else ModuleId("probe")
        try:
            _ = compile_extension_points(target_mid, raw_eps)
        except YscbError as exc:
            raise ValueError(f"Invalid {mod_cls.__name__}.extension_points: {exc.detail.message}") from exc


def _compile_declarative_class(
    cls_obj: type[object], kind: str, entries: tuple[_CompiledMethodEntry, ...], registry: _SdkStateRegistry, *, is_abstract: bool
) -> None:
    if kind == "task_group":
        if any(e.decorated.is_migrate for e in entries):
            raise ValueError(f"@on_migrate must be declared directly on Module, not TaskGroup {cls_obj.__name__}")
        if not is_abstract:
            grp_root_entries = [
                e for e in entries if e.decorated.task_spec is not None and e.decorated.task_spec.cli == ()
            ]
            if len(grp_root_entries) > 1:
                raise ValueError(f"TaskGroup {cls_obj.__name__} can declare at most one cli=() default task")
            grp_metas = [_resolve_task_metadata(ModuleId("group"), e, allow_foreign_module=True) for e in entries]
            grp_root_ids = frozenset(
                m.task_id
                for m, e in zip(grp_metas, entries)
                if e.decorated.task_spec is not None and e.decorated.task_spec.cli == ()
            )
            _validate_task_and_cli_uniqueness(grp_metas, root_default_ids=grp_root_ids)
        registry.put_meta(
            cls_obj,
            _CompiledClassMeta(kind=kind, module_id=None, groups=(), entries=entries, is_abstract=is_abstract),
        )
        return
    mod_cls = cast(type[Module], cls_obj)
    groups, mod_id = _read_module_groups(mod_cls, registry), None
    if not is_abstract:
        if type(mod_cls.id) is not str or not mod_cls.id.strip():
            raise ValueError(f"Concrete Module subclass {mod_cls.__name__} must declare a non-empty string id")
        mod_id = ModuleId(require_pure_str(mod_cls.id, f"{mod_cls.__name__}.id", non_empty=True))
    _validate_module_config_and_ext_points(mod_cls, mod_id)
    if sum(1 for e in entries if e.decorated.is_migrate) > 1:
        raise ValueError(f"Module {mod_cls.__name__} can declare at most one @on_migrate method")
    if not is_abstract and mod_id is not None:
        all_entries = [*entries, *(e for grp in groups for e in registry.require_entries(grp))]
        mod_root_entries = [
            e for e in all_entries if e.decorated.task_spec is not None and e.decorated.task_spec.cli == ()
        ]
        if len(mod_root_entries) > 1:
            raise ValueError(f"Module {mod_cls.__name__} can declare at most one cli=() default task")
        mod_metas = [_resolve_task_metadata(mod_id, e) for e in all_entries]
        mod_root_ids = frozenset(
            m.task_id
            for m, e in zip(mod_metas, all_entries)
            if e.decorated.task_spec is not None and e.decorated.task_spec.cli == ()
        )
        _validate_task_and_cli_uniqueness(mod_metas, root_default_ids=mod_root_ids, owner_module_id=mod_id)
    registry.put_meta(
        cls_obj,
        _CompiledClassMeta(kind=kind, module_id=mod_id, groups=groups, entries=entries, is_abstract=is_abstract),
    )


class _DeclarativeMeta(ABCMeta):
    """Metaclass collecting and validating @task, @on_event, @periodic, and @on_migrate schemas on class definition."""

    def __new__(mcls, name: str, bases: tuple[type[object], ...], namespace: dict[str, object]) -> _DeclarativeMeta:
        cls_obj = super().__new__(mcls, name, bases, namespace)
        registry = _SdkStateRegistry.instance()
        if (kind := registry.classify_bases(bases)) is None:
            if name in ("TaskGroup", "Module"):
                registry.put_meta(cls_obj, _CompiledClassMeta("root_group" if name == "TaskGroup" else "root_module", None, (), ()))
            return cls_obj
        entries = _collect_entries_from_class(cls_obj, namespace, registry)
        _compile_declarative_class(cls_obj, kind, entries, registry, is_abstract=(ABC in bases) or inspect.isabstract(cls_obj))
        return cls_obj


class TaskGroup(Generic[TModule_co], metaclass=_DeclarativeMeta):
    """Base class for modular groups of @task, @on_event, and @periodic methods."""

    @property
    def parent_module(self) -> Optional[TModule_co]:
        """Return the owning Module instance bound during to_yscb_module(), if any."""
        return cast(Optional[TModule_co], _SdkStateRegistry.instance().get_group_parent(self))

    @property
    def module(self) -> TModule_co:
        """Return the owning Module instance bound during to_yscb_module(), raising RuntimeError if unbound."""
        parent = _SdkStateRegistry.instance().get_group_parent(self)
        if parent is None:
            raise RuntimeError(
                f"TaskGroup {type(self).__name__!r} is not bound to a Module; attach it via Module.groups and call to_yscb_module()."
            )
        return cast(TModule_co, parent)

    def on_init(self, env: ModuleEnv) -> None:
        """Initialize group-owned resources during module startup."""
        _ = env

    def on_warmup(self, env: ModuleEnv) -> None:
        """Run non-blocking daemon warmup work after init completes."""
        _ = env

    def on_close(self) -> None:
        """Release group-owned resources on teardown."""


class Module(metaclass=_DeclarativeMeta):
    """Declarative base class compiling @task/@on_event/@periodic/@on_migrate methods into a YscbModule."""

    id: ClassVar[str] = ""
    aliases: ClassVar[tuple[str, ...]] = ()
    description: ClassVar[str] = ""
    groups: ClassVar[tuple[type[TaskGroup[Module]], ...]] = ()
    config_type: ClassVar[Optional[type[object]]] = None
    extension_points: ClassVar[tuple[ExtensionPointSpec[object], ...]] = ()

    def on_init(self, env: ModuleEnv) -> None:
        """Initialize module-owned resources during startup."""
        _ = env

    def on_warmup(self, env: ModuleEnv) -> None:
        """Run non-blocking daemon warmup work after init completes."""
        _ = env

    def on_close(self) -> None:
        """Release module-owned resources on teardown."""

    def to_yscb_module(self) -> YscbModule:
        """Instantiate declared TaskGroups and adapt this module into a runtime YscbModule."""
        cls_obj = type(self)
        registry = _SdkStateRegistry.instance()
        meta = registry.get_meta(cls_obj)
        if meta is None or meta.module_id is None:
            raise ValueError(f"Cannot convert abstract or unregistered Module {cls_obj.__name__} without a valid id")
        group_objs = tuple(grp_cls() for grp_cls in meta.groups)
        for grp in group_objs:
            registry.bind_group_parent(grp, self)
        sources = ((self, meta.entries), *((grp, registry.require_entries(type(grp))) for grp in group_objs))
        bound_list: list[BoundTask] = []
        root_default_ids: set[TaskId] = set()
        for owner, es in sources:
            for e in es:
                t_meta = _resolve_task_metadata(meta.module_id, e)
                if e.decorated.task_spec is not None and e.decorated.task_spec.cli == ():
                    root_default_ids.add(t_meta.task_id)
                bound_list.append(_SdkBoundTask(t_meta, types.MethodType(e.decorated.fn, owner), e.parsed_sig))
        bound = tuple(bound_list)
        ymod = _SdkYscbModule(meta.module_id, bound, module_obj=self, group_objs=group_objs)
        register_compiled_module_surface_meta(
            ymod,
            aliases=tuple(cls_obj.aliases),
            description=require_pure_str(cls_obj.description, f"{cls_obj.__name__}.description"),
            root_default_tasks=frozenset(root_default_ids),
        )
        return ymod


def _attach_decl(
    target: _TFn,
    *,
    task_spec: Optional[_TaskDeclSpec] = None,
    event_spec: Optional[_EventDeclSpec] = None,
    periodic_spec: Optional[PeriodicScheduleSpec] = None,
    is_migrate: bool = False,
) -> _TFn:
    if isinstance(target, (classmethod, staticmethod, property)) or not callable(target):
        raise ValueError("@task, @on_event, @periodic, and @on_migrate can only decorate instance methods")
    base = target if isinstance(target, _DecoratedMethod) else _DecoratedMethod(fn=target)
    if is_migrate or base.is_migrate:
        if base.is_migrate and is_migrate:
            raise ValueError("Duplicate @on_migrate decorator on the same method")
        if (
            task_spec is not None
            or event_spec is not None
            or periodic_spec is not None
            or base.task_spec is not None
            or base.events
            or base.periodic_spec is not None
        ):
            raise ValueError("@on_migrate cannot be stacked with @task, @on_event, or @periodic")
    if task_spec is not None and base.task_spec is not None:
        raise ValueError("Duplicate @task decorator on the same method")
    if periodic_spec is not None and base.periodic_spec is not None:
        raise ValueError("Duplicate @periodic decorator on the same method")
    return cast(
        _TFn,
        _DecoratedMethod(
            fn=base.fn,
            task_spec=task_spec or base.task_spec,
            events=((event_spec,) + base.events) if event_spec is not None else base.events,
            periodic_spec=periodic_spec or base.periodic_spec,
            is_migrate=is_migrate or base.is_migrate,
        ),
    )


def _normalize_cli_tokens(cli: Optional[str | tuple[str, ...]]) -> Optional[tuple[str, ...]]:
    if cli is None:
        return None
    if type(cli) is str:
        tokens = tuple(part for part in cli.split() if part)
        if not tokens:
            raise ValueError("@task cli string cannot be empty or whitespace")
        return tokens
    if isinstance(cli, tuple):
        if len(cli) == 0:
            return ()
        return tuple(_require_token(item, "cli segment") for item in cli)
    raise ValueError(f"@task cli must be str, tuple[str, ...], or None, got {cli!r}")


def _validate_note_lines(lines: object, label: str) -> tuple[str, ...]:
    if not isinstance(lines, tuple):
        raise ValueError(f"@task {label} must be tuple[str, ...], got {type(lines).__name__}")
    out: list[str] = []
    for item in lines:
        clean = require_pure_str(item, f"@task {label} entry", non_empty=True).strip()
        if not clean:
            raise ValueError(f"@task {label} entries cannot be blank whitespace")
        out.append(clean)
    return tuple(out)


def task(
    cli: Optional[str | tuple[str, ...]] = None,
    *,
    name: Optional[str] = None,
    summary: str = "",
    aliases: tuple[str, ...] = (),
    usage_pros: tuple[str, ...] = (),
    usage_cons: tuple[str, ...] = (),
    dispatch_mode: DispatchMode = DispatchMode.HYBRID,
    interactive_tty: bool = False,
    security: SecurityTier = SecurityTier.SAFE,
    lock: Optional[str] = None,
    concurrency: Optional[ConcurrencyMode] = None,
    equivalence_fn: Optional[Callable[[TIn], str]] = None,
    timeout_ms: Optional[int] = None,
) -> Callable[[_TFn], _TFn]:
    """Declare an SDK and optional CLI task on a Module or TaskGroup method."""
    if (
        callable(cli)
        and name is None
        and not summary
        and not aliases
        and not usage_pros
        and not usage_cons
        and dispatch_mode == DispatchMode.HYBRID
        and not interactive_tty
        and security == SecurityTier.SAFE
        and lock is None
        and concurrency is None
        and equivalence_fn is None
        and timeout_ms is None
    ):
        return cast(Callable[[_TFn], _TFn], _attach_decl(cast(_TFn, cli), task_spec=_TaskDeclSpec()))
    cli_tokens = _normalize_cli_tokens(cli)
    if not isinstance(aliases, tuple):
        raise ValueError(f"@task aliases must be tuple[str, ...], got {type(aliases).__name__}")
    pros_tup = _validate_note_lines(usage_pros, "usage_pros")
    cons_tup = _validate_note_lines(usage_cons, "usage_cons")
    if (aliases or pros_tup or cons_tup) and cli_tokens is None:
        raise ValueError("@task aliases, usage_pros, and usage_cons require a non-empty cli command path")
    if (norm_name := _require_token(name, "name") if name is not None else None) is not None:
        _ = TaskId(norm_name if "." in norm_name else f"probe.{norm_name}")
    if not isinstance(dispatch_mode, DispatchMode):
        raise ValueError(f"@task dispatch_mode must be DispatchMode, got {dispatch_mode!r}")
    if equivalence_fn is not None and not callable(equivalence_fn):
        raise ValueError("@task equivalence_fn must be callable or None")
    eff_sec, norm_lock, eff_conc = _normalize_exec_policy(security, lock, concurrency, owner="@task")
    spec = _TaskDeclSpec(
        cli=cli_tokens,
        task_name=norm_name,
        summary=require_pure_str(summary, "summary"),
        aliases=tuple(_require_token(a, "alias") for a in aliases),
        usage_pros=pros_tup,
        usage_cons=cons_tup,
        dispatch_mode=dispatch_mode,
        interactive_tty=require_pure_bool(interactive_tty, "interactive_tty"),
        security=eff_sec,
        lock=norm_lock,
        concurrency=eff_conc,
        equivalence_fn=cast(Optional[Callable[[object], str]], equivalence_fn),
        timeout_ms=require_pure_int(timeout_ms, "timeout_ms", min_val=1, max_val=None) if timeout_ms is not None else None,
    )
    return lambda target: _attach_decl(target, task_spec=spec)


def on_migrate() -> Callable[[_TFn], _TFn]:
    """Mark a Module method (self, req: MigrationRequest, ctx: TaskContext) -> None as its upgrade migration handler."""
    return lambda target: _attach_decl(target, is_migrate=True)


def on_event(
    event: EventMetadata[TPayload] | EventId | str,
    *,
    payload_filter: Optional[Mapping[str, Sequence[JsonPrimitive]]] = None,
    mapper: Optional[Callable[[Sequence[TPayload]], Optional[TIn]]] = None,
) -> Callable[[_TFn], _TFn]:
    """Bind a Module or TaskGroup method to an event stream with optional filter and batch mapper."""
    if isinstance(event, EventMetadata):
        evt_ref, payload_type = cast(EventMetadata[object], event), event.payload_type
    elif isinstance(event, EventId) or type(event) is str:
        evt_ref, payload_type = (event if isinstance(event, EventId) else EventId(require_pure_str(event, "event", non_empty=True))), None
    else:
        raise ValueError(f"@on_event requires EventMetadata, EventId, or non-empty str, got {event!r}")
    if mapper is not None and not callable(mapper):
        raise ValueError("@on_event mapper must be callable or None")
    decl = _EventDeclSpec(evt_ref, normalize_payload_filter(payload_filter), cast(Optional[Callable[[Sequence[object]], Optional[object]]], mapper), payload_type)
    return lambda target: _attach_decl(target, event_spec=decl)


def periodic(interval_sec: float, *, enabled_config_key: Optional[str] = None, interval_config_key: Optional[str] = None) -> Callable[[_TFn], _TFn]:
    """Schedule a Module or TaskGroup method periodically inside the daemon host."""
    spec = PeriodicScheduleSpec(default_interval_sec=interval_sec, enabled_config_key=enabled_config_key, interval_config_key=interval_config_key)
    return lambda target: _attach_decl(target, periodic_spec=spec)


class InMemoryModule:
    """Mutable test fixture registering callable tasks without .modules/ disk artifacts."""

    def __init__(self, module_id: str) -> None:
        self._module_id = module_id if isinstance(module_id, ModuleId) else ModuleId(require_pure_str(module_id, "module_id", non_empty=True))
        self._tasks: list[BoundTask] = []
        self._seen_ids: set[TaskId] = set()

    def add_task(
        self,
        name: str,
        handler: Callable[..., object],
        *,
        summary: str = "",
        security: SecurityTier = SecurityTier.SAFE,
        lock: Optional[str] = None,
        concurrency: Optional[ConcurrencyMode] = None,
    ) -> InMemoryModule:
        """Register a callable task handler and return self for fluent chaining."""
        raw_fn = handler.fn if isinstance(handler, _DecoratedMethod) else handler
        if isinstance(raw_fn, (classmethod, staticmethod, property)) or not callable(raw_fn):
            raise ValueError("InMemoryModule.add_task handler must be callable")
        eff_sec, norm_lock, eff_conc = _normalize_exec_policy(security, lock, concurrency, owner="InMemoryModule")
        decl = _TaskDeclSpec(task_name=_require_token(name, "InMemoryModule task name"), summary=require_pure_str(summary, "summary"), security=eff_sec, lock=norm_lock, concurrency=eff_conc)
        parsed = _parse_callable_signature(raw_fn, expect_self=False, require_return_ann=False)
        meta = _resolve_task_metadata(self._module_id, _CompiledMethodEntry(decl.task_name or name, _DecoratedMethod(raw_fn, decl), parsed))
        if meta.task_id in self._seen_ids:
            raise ValueError(f"Duplicate task_id {meta.task_id.value!r} in InMemoryModule {self._module_id.value!r}")
        self._tasks.append(_SdkBoundTask(meta, raw_fn, parsed))
        self._seen_ids.add(meta.task_id)
        return self

    def to_yscb_module(self) -> YscbModule:
        """Build an immutable YscbModule adapter from all registered tasks."""
        ymod = _SdkYscbModule(self._module_id, tuple(self._tasks))
        register_compiled_module_surface_meta(ymod, aliases=(), description="")
        return ymod
