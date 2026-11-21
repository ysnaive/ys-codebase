"""Declarative Task/Module/TaskGroup DSL, CLI schema annotations, output protocols, and test fixtures."""

from __future__ import annotations

from abc import ABC, ABCMeta
from dataclasses import dataclass
import dataclasses
import inspect
import json
import threading
import types
from typing import (
    Annotated, Callable, ClassVar, Mapping, Optional, Protocol, Sequence, TypeVar, cast, get_args, get_origin,
    get_type_hints, runtime_checkable,
)
import weakref

from core.execution.event import EventMetadata, EventOrdering, EventSubscriptionSpec, normalize_payload_filter
from core.execution.lifecycle import LifoResourceStack
from core.execution.runtime import (
    BoundTask, CliBindingSpec, ConcurrencyMode, DispatchMode, PeriodicScheduleSpec, SecurityTier, Task, TaskContext,
    TaskExposure, TaskMetadata, YscbModule,
)
from core.foundation import (
    DataclassCodec, ErrorCode, EventId, HostPath, JsonPrimitive, ModuleId, TaskId, YscbError, is_valid_type_annotation,
    require_pure_bool, require_pure_int, require_pure_str,
)

TIn = TypeVar("TIn")
TPayload = TypeVar("TPayload")
_TFn = TypeVar("_TFn", bound=Callable[..., object])


def _require_token(value: str, label: str) -> str:
    clean = require_pure_str(value, label, non_empty=True)
    if any(ch.isspace() for ch in clean):
        raise ValueError(f"{label} cannot contain whitespace: {clean!r}")
    return clean


@dataclass(frozen=True, slots=True)
class Empty:
    """Empty payload or output DTO for parameterless or void tasks and events."""


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

    def __post_init__(self) -> None:
        require_pure_str(self.summary, "Option.summary")
        if self.short is not None:
            require_pure_str(self.short, "Option.short", non_empty=True)
            stripped = self.short[1:] if self.short.startswith("-") else self.short
            if self.short.startswith("--") or len(stripped) != 1 or not stripped.isalnum():
                raise ValueError(f"Option.short must be one alphanumeric char (optionally '-x'), got {self.short!r}")
        if self.long_name is not None and not _require_token(self.long_name, "Option.long_name").lstrip("-"):
            raise ValueError(f"Option.long_name must contain non-dash characters, got {self.long_name!r}")


@runtime_checkable
class HumanRenderable(Protocol):
    """Optional output protocol rendering human-readable CLI output without altering SDK return values."""

    def render_text(self) -> str: ...


@runtime_checkable
class ExitCodeProvider(Protocol):
    """Optional output protocol supplying semantic CLI process exit codes."""

    def exit_code(self) -> int: ...


def format_output(output: object) -> tuple[str, int]:
    """Extract (rendered_text, exit_code) uniformly from any SDK task return object."""
    code = require_pure_int(output.exit_code(), "ExitCodeProvider.exit_code()", min_val=None, max_val=None) if isinstance(output, ExitCodeProvider) else 0
    if isinstance(output, HumanRenderable):
        return (require_pure_str(output.render_text(), "HumanRenderable.render_text()"), code)
    if output is None or isinstance(output, Empty):
        return ("", code)
    if type(output) is str:
        return (output, code)
    if isinstance(output, (bool, int, float, ModuleId, TaskId, EventId, HostPath)):
        return (str(output), code)
    if (dataclasses.is_dataclass(output) and not isinstance(output, type)) or isinstance(output, (Mapping, list, tuple, frozenset)):
        return (json.dumps(DataclassCodec.encode(output), indent=2, ensure_ascii=False), code)
    return (str(output), code)


class _SdkStateRegistry:
    """Thread-safe weak-key registry for ModuleEnv closer stacks and compiled declarative classes."""

    _INSTANCE: ClassVar[Optional[_SdkStateRegistry]] = None
    _INIT_LOCK: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stacks: weakref.WeakKeyDictionary[ModuleEnv, LifoResourceStack] = weakref.WeakKeyDictionary()
        self._classes: weakref.WeakKeyDictionary[type[object], _CompiledClassMeta] = weakref.WeakKeyDictionary()

    @classmethod
    def instance(cls) -> _SdkStateRegistry:
        if cls._INSTANCE is None:
            with cls._INIT_LOCK:
                cls._INSTANCE = cls._INSTANCE or cls()
        return cls._INSTANCE

    def env_stack(self, env: ModuleEnv) -> LifoResourceStack:
        with self._lock:
            return self._stacks.setdefault(env, LifoResourceStack())

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


class ModuleEnv:
    """Lifecycle environment passed to Module and TaskGroup init and warmup hooks."""

    __slots__ = ("workspace_root", "__weakref__")
    workspace_root: HostPath

    def __init__(self, workspace_root: HostPath) -> None:
        if not isinstance(workspace_root, HostPath):
            raise TypeError(f"ModuleEnv.workspace_root must be HostPath, got {type(workspace_root).__name__}")
        self.workspace_root = workspace_root

    def register_closer(self, fn: Callable[[], None]) -> None:
        """Register a zero-argument teardown callback executed in LIFO order on shutdown."""
        if not callable(fn):
            raise TypeError("ModuleEnv.register_closer requires a zero-arg callable")
        _SdkStateRegistry.instance().env_stack(self).push_closeable("module_env", fn)


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
    dispatch_mode: DispatchMode = DispatchMode.HYBRID
    interactive_tty: bool = False
    security: SecurityTier = SecurityTier.SAFE
    lock: Optional[str] = None
    concurrency: ConcurrencyMode = ConcurrencyMode.PARALLEL
    timeout_ms: Optional[int] = None


@dataclass(frozen=True, slots=True)
class _EventDeclSpec:
    event: EventMetadata[object] | EventId
    payload_filter: Optional[Mapping[str, tuple[JsonPrimitive, ...]]]
    mapper: Optional[Callable[[Sequence[object]], Optional[object]]]
    payload_type: Optional[type[object]]


@dataclass(frozen=True, slots=True)
class _DecoratedMethod:
    """Immutable callable descriptor accumulating @task, @on_event, and @periodic specs."""

    fn: Callable[..., object]
    task_spec: Optional[_TaskDeclSpec] = None
    events: tuple[_EventDeclSpec, ...] = ()
    periodic_spec: Optional[PeriodicScheduleSpec] = None

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
    dec, parsed, decl = entry.decorated, entry.parsed_sig, entry.decorated.task_spec or _TaskDeclSpec()
    tid = _qualify_task_id(module_id, decl.task_name, label="@task name", allow_foreign=allow_foreign_module) if decl.task_name is not None else TaskId(f"{module_id.value}.{entry.method_name}")
    if dec.events or dec.periodic_spec is not None:
        if decl.security == SecurityTier.GATED:
            raise ValueError(f"Task {tid.value!r} with SecurityTier.GATED cannot bind @on_event or @periodic")
        if decl.dispatch_mode == DispatchMode.COLD_ONLY:
            raise ValueError(f"Task {tid.value!r} with DispatchMode.COLD_ONLY cannot bind @on_event or @periodic")
    cli_spec = CliBindingSpec(decl.cli, decl.summary or parsed.summary_fallback or f"Execute {tid.value}", decl.aliases) if decl.cli is not None else None
    exposure = TaskExposure.CLI_AND_SDK if cli_spec is not None else (TaskExposure.SDK_ONLY if dec.task_spec is not None else TaskExposure.INTERNAL_TRIGGER)
    for ev in dec.events:
        if ev.mapper is None and parsed.input_type is not Empty:
            raise ValueError(f"@on_event without mapper on {entry.method_name!r} requires a parameterless (self, ctx) task method")
    subs = tuple(EventSubscriptionSpec(
        event=ev.event, payload_filter=ev.payload_filter, payload_type=ev.payload_type,
        batch_mapper=ev.mapper if ev.mapper is not None else (lambda batch: Empty() if batch else None),
    ) for ev in dec.events)
    return TaskMetadata(
        task_id=tid, input_type=parsed.input_type, output_type=parsed.output_type, exposure=exposure, cli=cli_spec,
        dispatch_mode=decl.dispatch_mode, interactive_tty=decl.interactive_tty, security_tier=decl.security,
        resource_key=decl.lock, concurrency_mode=decl.concurrency, timeout_ms=decl.timeout_ms,
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

    def __init__(self, module_id: ModuleId, bound_tasks: tuple[BoundTask, ...], module_obj: Optional[Module] = None, group_objs: tuple[TaskGroup, ...] = ()) -> None:
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
        stack = _SdkStateRegistry.instance().env_stack(env := ModuleEnv(workspace_root))
        try:
            for target in (self._module_obj, *self._group_objs):
                if is_init:
                    stack.push_closeable(self._module_id.value if target is self._module_obj else type(target).__name__, target.on_close)
                    target.on_init(env)
                else:
                    target.on_warmup(env)
        except (Exception, SystemExit, GeneratorExit):
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
    groups: tuple[type[TaskGroup], ...]
    entries: tuple[_CompiledMethodEntry, ...]


def _validate_task_and_cli_uniqueness(metadatas: Sequence[TaskMetadata[object, object]]) -> None:
    seen_ids, seen_cli, seen_tokens = set(), set(), set()
    for meta in metadatas:
        if meta.task_id in seen_ids:
            raise ValueError(f"Duplicate task_id {meta.task_id.value!r}")
        seen_ids.add(meta.task_id)
        if (cli := meta.cli) is not None:
            if cli.command_path in seen_cli:
                raise ValueError(f"Duplicate CLI command path {cli.command_path!r}")
            seen_cli.add(cli.command_path)
            for token in (cli.command_path[-1],) + cli.aliases:
                if (key := (cli.command_path[:-1], token)) in seen_tokens:
                    raise ValueError(f"CLI command/alias collision under parent {cli.command_path[:-1]!r}: {token!r}")
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


def _read_module_groups(cls_obj: type[Module], registry: _SdkStateRegistry) -> tuple[type[TaskGroup], ...]:
    if not isinstance(raw_groups := cls_obj.groups, (tuple, list)):
        raise ValueError(f"{cls_obj.__name__}.groups must be a tuple of TaskGroup subclasses")
    normalized: list[type[TaskGroup]] = []
    for grp in raw_groups:
        if not isinstance(grp, type) or not issubclass(grp, TaskGroup) or grp is TaskGroup or inspect.isabstract(grp) or registry.get_meta(grp) is None:
            raise ValueError(f"{cls_obj.__name__}.groups entries must be concrete TaskGroup subclasses, got {grp!r}")
        if grp in normalized:
            raise ValueError(f"Duplicate TaskGroup {grp.__name__} in {cls_obj.__name__}.groups")
        normalized.append(grp)
    return tuple(normalized)


def _compile_declarative_class(
    cls_obj: type[object], kind: str, entries: tuple[_CompiledMethodEntry, ...], registry: _SdkStateRegistry, *, is_abstract: bool
) -> None:
    if kind == "task_group":
        if not is_abstract:
            _validate_task_and_cli_uniqueness([_resolve_task_metadata(ModuleId("group"), e, allow_foreign_module=True) for e in entries])
        registry.put_meta(cls_obj, _CompiledClassMeta(kind=kind, module_id=None, groups=(), entries=entries))
        return
    mod_cls = cast(type[Module], cls_obj)
    groups, mod_id = _read_module_groups(mod_cls, registry), None
    if not is_abstract:
        if type(mod_cls.id) is not str or not mod_cls.id.strip():
            raise ValueError(f"Concrete Module subclass {mod_cls.__name__} must declare a non-empty string id")
        mod_id = ModuleId(require_pure_str(mod_cls.id, f"{mod_cls.__name__}.id", non_empty=True))
        all_entries = [*entries, *(e for grp in groups for e in registry.require_entries(grp))]
        _validate_task_and_cli_uniqueness([_resolve_task_metadata(mod_id, e) for e in all_entries])
    registry.put_meta(cls_obj, _CompiledClassMeta(kind=kind, module_id=mod_id, groups=groups, entries=entries))


class _DeclarativeMeta(ABCMeta):
    """Metaclass collecting and validating @task, @on_event, and @periodic schemas on class definition."""

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


class TaskGroup(metaclass=_DeclarativeMeta):
    """Base class for modular groups of @task, @on_event, and @periodic methods."""

    def on_init(self, env: ModuleEnv) -> None:
        """Initialize group-owned resources during module startup."""
        _ = env

    def on_warmup(self, env: ModuleEnv) -> None:
        """Run non-blocking daemon warmup work after init completes."""
        _ = env

    def on_close(self) -> None:
        """Release group-owned resources on teardown."""


class Module(metaclass=_DeclarativeMeta):
    """Declarative base class compiling @task/@on_event/@periodic methods into a YscbModule."""

    id: ClassVar[str] = ""
    groups: ClassVar[tuple[type[TaskGroup], ...]] = ()

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
        registry = _SdkStateRegistry.instance()
        meta = registry.get_meta(type(self))
        if meta is None or meta.module_id is None:
            raise ValueError(f"Cannot convert abstract or unregistered Module {type(self).__name__} without a valid id")
        group_objs = tuple(grp_cls() for grp_cls in meta.groups)
        sources = ((self, meta.entries), *((grp, registry.require_entries(type(grp))) for grp in group_objs))
        bound = tuple(_SdkBoundTask(_resolve_task_metadata(meta.module_id, e), types.MethodType(e.decorated.fn, owner), e.parsed_sig) for owner, es in sources for e in es)
        return _SdkYscbModule(meta.module_id, bound, module_obj=self, group_objs=group_objs)


def _attach_decl(
    target: _TFn, *, task_spec: Optional[_TaskDeclSpec] = None, event_spec: Optional[_EventDeclSpec] = None,
    periodic_spec: Optional[PeriodicScheduleSpec] = None,
) -> _TFn:
    if isinstance(target, (classmethod, staticmethod, property)) or not callable(target):
        raise ValueError("@task, @on_event, and @periodic can only decorate instance methods")
    base = target if isinstance(target, _DecoratedMethod) else _DecoratedMethod(fn=target)
    if task_spec is not None and base.task_spec is not None:
        raise ValueError("Duplicate @task decorator on the same method")
    if periodic_spec is not None and base.periodic_spec is not None:
        raise ValueError("Duplicate @periodic decorator on the same method")
    return cast(_TFn, _DecoratedMethod(
        fn=base.fn, task_spec=task_spec or base.task_spec,
        events=((event_spec,) + base.events) if event_spec is not None else base.events,
        periodic_spec=periodic_spec or base.periodic_spec,
    ))


def _normalize_cli_tokens(cli: Optional[str | tuple[str, ...]]) -> Optional[tuple[str, ...]]:
    if cli is None:
        return None
    if type(cli) is str:
        tokens = tuple(part for part in cli.split() if part)
        if not tokens:
            raise ValueError("@task cli string cannot be empty or whitespace")
        return tokens
    if isinstance(cli, tuple) and cli:
        return tuple(_require_token(item, "cli segment") for item in cli)
    raise ValueError(f"@task cli must be str, non-empty tuple[str, ...], or None, got {cli!r}")


def task(
    cli: Optional[str | tuple[str, ...]] = None, *, name: Optional[str] = None, summary: str = "",
    aliases: tuple[str, ...] = (), dispatch_mode: DispatchMode = DispatchMode.HYBRID, interactive_tty: bool = False,
    security: SecurityTier = SecurityTier.SAFE, lock: Optional[str] = None,
    concurrency: Optional[ConcurrencyMode] = None, timeout_ms: Optional[int] = None,
) -> Callable[[_TFn], _TFn]:
    """Declare an SDK and optional CLI task on a Module or TaskGroup method."""
    if callable(cli) and name is None and not summary and not aliases and dispatch_mode == DispatchMode.HYBRID and not interactive_tty and security == SecurityTier.SAFE and lock is None and concurrency is None and timeout_ms is None:
        return cast(Callable[[_TFn], _TFn], _attach_decl(cast(_TFn, cli), task_spec=_TaskDeclSpec()))
    cli_tokens = _normalize_cli_tokens(cli)
    if not isinstance(aliases, tuple):
        raise ValueError(f"@task aliases must be tuple[str, ...], got {type(aliases).__name__}")
    if aliases and cli_tokens is None:
        raise ValueError("@task aliases require a non-empty cli command path")
    if (norm_name := _require_token(name, "name") if name is not None else None) is not None:
        _ = TaskId(norm_name if "." in norm_name else f"probe.{norm_name}")
    if not isinstance(dispatch_mode, DispatchMode):
        raise ValueError(f"@task dispatch_mode must be DispatchMode, got {dispatch_mode!r}")
    eff_sec, norm_lock, eff_conc = _normalize_exec_policy(security, lock, concurrency, owner="@task")
    spec = _TaskDeclSpec(
        cli=cli_tokens, task_name=norm_name, summary=require_pure_str(summary, "summary"),
        aliases=tuple(_require_token(a, "alias") for a in aliases), dispatch_mode=dispatch_mode,
        interactive_tty=require_pure_bool(interactive_tty, "interactive_tty"), security=eff_sec, lock=norm_lock, concurrency=eff_conc,
        timeout_ms=require_pure_int(timeout_ms, "timeout_ms", min_val=1, max_val=None) if timeout_ms is not None else None,
    )
    return lambda target: _attach_decl(target, task_spec=spec)


def on_event(
    event: EventMetadata[TPayload] | EventId | str, *,
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
        self, name: str, handler: Callable[..., object], *, summary: str = "",
        security: SecurityTier = SecurityTier.SAFE, lock: Optional[str] = None, concurrency: Optional[ConcurrencyMode] = None,
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
        return _SdkYscbModule(self._module_id, tuple(self._tasks))
