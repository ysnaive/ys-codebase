"""Static zero-import CLI task index compiler, schema v2 codec, and fingerprint-cached workspace aggregator."""

from __future__ import annotations

import collections.abc as cabc
import dataclasses
from dataclasses import dataclass
from enum import Enum
import math
import os
import stat
import types
from typing import (
    Annotated,
    Final,
    Generic,
    TypeVar,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Union,
    get_args,
    get_origin,
)

from core.execution.event import normalize_payload_filter
from core.execution.runtime import (
    CORE_MODULE_ID,
    BoundTask,
    CliBindingSpec,
    ConcurrencyMode,
    DispatchMode,
    MODULES_DIRNAME,
    PeriodicScheduleSpec,
    SecurityTier,
    SelfMutationScope,
    SubscriptionRouteSpec,
    TaskExposure,
    TaskMetadata,
    TaskRouteSpec,
    YscbModule,
)
from core.metadata.config import (
    lookup_compiled_module_root_default_tasks,
    lookup_compiled_module_surface_meta,
)
from core.filesystem.fs import (
    MAX_JSON_FILE_BYTES,
    atomic_write_json,
    is_symlink_or_reparse,
    read_json_dict,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
    try_resolve_contained_subpath,
)
from core.foundation import (
    DataclassCodec,
    EnvHash,
    ErrorCode,
    EventId,
    HostPath,
    INT64_MAX,
    INT64_MIN,
    JsonObject,
    JsonPrimitive,
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
    YscbError,
    clone_strict_json_object,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    require_typed_tuple,
    resolve_dataclass_init_hints,
    strict_parse_json_object,
)
from core.surface.sdk import Arg, Empty, ExitCodeProvider, HumanRenderable, Module, Option

TASKS_INDEX_SCHEMA_VERSION: Final[int] = 2
_TASKS_INDEX_FILENAME: Final[str] = "tasks.index.json"
_RESERVED_GLOBAL_CLI_FLAGS: Final[frozenset[str]] = frozenset(
    {"-h", "--help", "--json", "--cold", "--approve", "--host-dir", "--profile", "--profile-mem"}
)
_VALID_CLI_SCALAR_TYPE_NAMES: Final[frozenset[str]] = frozenset(
    {"str", "int", "float", "bool", "dict"}
)
_VALID_CLI_TYPE_NAMES: Final[frozenset[str]] = frozenset(
    {*_VALID_CLI_SCALAR_TYPE_NAMES, *(f"list[{t}]" for t in _VALID_CLI_SCALAR_TYPE_NAMES)}
)
_CLI_TRUE_CHOICE_LITERALS: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_CLI_FALSE_CHOICE_LITERALS: Final[frozenset[str]] = frozenset({"0", "false", "no", "off"})
_VALID_CLI_BOOL_CHOICE_LITERALS: Final[frozenset[str]] = (
    _CLI_TRUE_CHOICE_LITERALS | _CLI_FALSE_CHOICE_LITERALS
)


def classify_cli_bool_choices(choices: Optional[Sequence[str]]) -> tuple[bool, bool]:
    if not choices:
        return (True, True)
    low = {c.strip().lower() for c in choices}
    return (bool(low & _CLI_TRUE_CHOICE_LITERALS), bool(low & _CLI_FALSE_CHOICE_LITERALS))


def _validate_cli_type_and_choices(
    type_name: str,
    choices: Optional[Sequence[str]],
    label: str,
) -> Optional[tuple[str, ...]]:
    require_pure_str(type_name, f"{label}.type_name", non_empty=True)
    if type_name not in _VALID_CLI_TYPE_NAMES:
        raise ValueError(f"Unsupported {label}.type_name: {type_name!r}")
    if choices is None:
        return None
    typed_choices = require_typed_tuple(choices, str, f"{label}.choices")
    if not typed_choices:
        raise ValueError(f"{label}.choices must not be empty when specified")
    elem_tp = type_name[5:-1] if type_name.startswith("list[") else type_name
    if elem_tp == "dict":
        raise ValueError(f"{label}.choices cannot be combined with dict type_name")
    if elem_tp == "int":
        for ch_tok in typed_choices:
            iv = int(ch_tok)
            if iv < INT64_MIN or iv > INT64_MAX:
                raise ValueError(f"{label}.choices integer out of 64-bit signed range: {ch_tok!r}")
    elif elem_tp == "float":
        for ch_tok in typed_choices:
            fv = float(ch_tok)
            if not math.isfinite(fv):
                raise ValueError(f"{label}.choices float must be finite: {ch_tok!r}")
    elif elem_tp == "bool":
        for ch_tok in typed_choices:
            if ch_tok.strip().lower() not in _VALID_CLI_BOOL_CHOICE_LITERALS:
                raise ValueError(f"{label}.choices boolean literal invalid: {ch_tok!r}")
    return typed_choices


def _validate_cli_token_seq(seq: Sequence[str], label: str) -> tuple[str, ...]:
    typed = require_typed_tuple(seq, str, label)
    for tok in typed:
        if not tok or tok != tok.strip() or any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in tok):
            raise ValueError(f"{label} contains blank, whitespace, or control-character token: {tok!r}")
    return typed


def _sanitize_json_default(raw_val: object) -> JsonValue:
    if raw_val is None or isinstance(raw_val, (bool, int, float, str)):
        return raw_val
    if isinstance(raw_val, list):
        return [_sanitize_json_default(item) for item in raw_val]
    if isinstance(raw_val, tuple):
        return [_sanitize_json_default(item) for item in raw_val]
    if isinstance(raw_val, Mapping):
        return dict(clone_strict_json_object(raw_val, label="CLI default value"))
    return None


def _iter_concrete_type_branches(tp: object) -> tuple[type[object], ...]:
    origin = get_origin(tp)
    if origin is Annotated:
        return _iter_concrete_type_branches(get_args(tp)[0])
    if origin in (Union, types.UnionType):
        out: list[type[object]] = []
        for branch in get_args(tp):
            out.extend(_iter_concrete_type_branches(branch))
        return tuple(out)
    if isinstance(tp, type):
        return (tp,)
    if isinstance(origin, type):
        return (origin,)
    return ()


def _unwrap_field_type_and_marker(raw_tp: object) -> tuple[object, Optional[Arg | Option], bool]:
    cur = raw_tp
    marker: Optional[Arg | Option] = None
    is_opt = False
    while True:
        origin = get_origin(cur)
        if origin is Annotated:
            args = get_args(cur)
            for meta_item in args[1:]:
                if isinstance(meta_item, (Arg, Option)):
                    if marker is not None:
                        raise ValueError(f"Field annotation cannot combine multiple Arg/Option markers: {raw_tp!r}")
                    marker = meta_item
            cur = args[0]
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


def _classify_choice_values(raw_vals: Sequence[object]) -> tuple[str, Optional[tuple[str, ...]]]:
    if not raw_vals:
        raise ValueError("CLI Literal or Enum annotation cannot be empty")
    unwrapped = [v.value if isinstance(v, Enum) else v for v in raw_vals]
    choices = tuple(str(v) for v in unwrapped)
    if all(type(v) is bool for v in unwrapped):
        return ("bool", choices)
    if all(type(v) is int for v in unwrapped):
        return ("int", choices)
    if all(type(v) is float for v in unwrapped):
        return ("float", choices)
    if all(type(v) is str for v in unwrapped):
        return ("str", choices)
    raise ValueError(f"Heterogeneous or non-scalar CLI Literal/Enum choices are unsupported: {unwrapped!r}")


def _extract_choices_and_type_name(tp: object) -> tuple[str, Optional[tuple[str, ...]], bool]:
    while get_origin(tp) is Annotated:
        tp = get_args(tp)[0]
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        non_none = [a for a in get_args(tp) if a is not type(None)]
        if len(non_none) == 1:
            return _extract_choices_and_type_name(non_none[0])
        raise ValueError(f"Multi-type Union CLI field annotation is unsupported: {tp!r}")
    if origin is Literal:
        tp_name, choices = _classify_choice_values(get_args(tp))
        return (tp_name, choices, False)
    if isinstance(tp, type) and issubclass(tp, Enum):
        tp_name, choices = _classify_choice_values(tuple(tp))
        return (tp_name, choices, False)
    if origin in (list, tuple, Sequence, cabc.Sequence, frozenset):
        args = get_args(tp)
        if origin is tuple and not (len(args) == 2 and args[1] is Ellipsis):
            raise ValueError(
                f"Fixed-length or heterogeneous tuple CLI annotation is unsupported (use tuple[T, ...]): {tp!r}"
            )
        elem_tp = args[0] if args and args[0] is not Ellipsis else str
        elem_name, elem_choices, elem_is_seq = _extract_choices_and_type_name(elem_tp)
        if elem_is_seq:
            raise ValueError(f"Nested sequence CLI annotation is unsupported: {tp!r}")
        return (f"list[{elem_name}]", elem_choices, True)
    if (isinstance(tp, type) and dataclasses.is_dataclass(tp) and tp not in _CLI_SCALAR_VO_TYPES) or (
        isinstance(origin, type) and dataclasses.is_dataclass(origin) and origin not in _CLI_SCALAR_VO_TYPES
    ):
        return ("dict", None, False)
    if tp in (dict, Mapping, cabc.Mapping) or origin in (dict, Mapping, cabc.Mapping):
        return ("dict", None, False)
    if tp is bool:
        return ("bool", None, False)
    if tp is int or tp is SnapshotGen:
        return ("int", None, False)
    if tp is float:
        return ("float", None, False)
    return ("str", None, False)


def _compute_field_default_json(fld: dataclasses.Field[object]) -> tuple[bool, JsonValue]:
    if fld.default is not dataclasses.MISSING:
        return (True, _sanitize_json_default(DataclassCodec.encode(fld.default)))
    if fld.default_factory is not dataclasses.MISSING:
        sample = fld.default_factory()
        return (True, _sanitize_json_default(DataclassCodec.encode(sample)))
    return (False, None)


@dataclass(frozen=True, slots=True)
class CliArgSpec:
    """Compiled static CLI positional argument contract stored in tasks.index.json."""

    field: str
    name: str
    type_name: str
    required: bool
    summary: str = ""
    choices: Optional[tuple[str, ...]] = None
    default: JsonValue = None

    def __post_init__(self) -> None:
        require_pure_str(self.field, "CliArgSpec.field", non_empty=True)
        _ = _validate_cli_token_seq((self.name,), "CliArgSpec.name")
        require_pure_bool(self.required, "CliArgSpec.required")
        require_pure_str(self.summary, "CliArgSpec.summary")
        validated_choices = _validate_cli_type_and_choices(self.type_name, self.choices, "CliArgSpec")
        if validated_choices is not None:
            object.__setattr__(self, "choices", validated_choices)
        object.__setattr__(self, "default", _sanitize_json_default(self.default))

    @property
    def is_variadic(self) -> bool:
        return self.type_name.startswith("list[")

    def to_json_dict(self) -> JsonObject:
        out: MutableJsonObject = {
            "field": self.field,
            "name": self.name,
            "type": self.type_name,
            "required": self.required,
            "summary": self.summary,
            "default": self.default,
        }
        if self.choices is not None:
            out["choices"] = list(self.choices)
        return out

    @classmethod
    def from_json_dict(cls, doc: Mapping[str, object]) -> CliArgSpec:
        raw_choices = doc.get("choices")
        choices: Optional[tuple[str, ...]] = None
        if raw_choices is not None:
            if not isinstance(raw_choices, list):
                raise ValueError("CliArgSpec.choices must be a JSON array of strings or null")
            choices = require_typed_tuple(raw_choices, str, "CliArgSpec.choices")
        return cls(
            field=require_pure_str(doc.get("field"), "arg.field", non_empty=True),
            name=require_pure_str(doc.get("name"), "arg.name", non_empty=True),
            type_name=require_pure_str(doc.get("type"), "arg.type", non_empty=True),
            required=require_pure_bool(doc.get("required"), "arg.required"),
            summary=require_pure_str(doc.get("summary", ""), "arg.summary"),
            choices=choices,
            default=_sanitize_json_default(doc.get("default")),
        )


@dataclass(frozen=True, slots=True)
class CliOptionSpec:
    """Compiled static CLI named option contract stored in tasks.index.json."""

    field: str
    long_name: str
    short: Optional[str]
    type_name: str
    required: bool
    default: JsonValue = None
    group: Optional[str] = None
    choices: Optional[tuple[str, ...]] = None
    summary: str = ""

    def __post_init__(self) -> None:
        require_pure_str(self.field, "CliOptionSpec.field", non_empty=True)
        clean_long = _validate_cli_token_seq((self.long_name,), "CliOptionSpec.long_name")[0].lstrip("-")
        if not clean_long or "=" in clean_long:
            raise ValueError(f"Invalid CliOptionSpec.long_name: {self.long_name!r}")
        if f"--{clean_long}" in _RESERVED_GLOBAL_CLI_FLAGS:
            raise ValueError(f"CliOptionSpec.long_name '--{clean_long}' collides with reserved global CLI flag")
        object.__setattr__(self, "long_name", clean_long)
        if self.short is not None:
            s_clean = require_pure_str(self.short, "CliOptionSpec.short", non_empty=True).lstrip("-")
            if len(s_clean) != 1 or not s_clean.isalnum():
                raise ValueError(f"Invalid CliOptionSpec.short: {self.short!r}")
            if f"-{s_clean}" in _RESERVED_GLOBAL_CLI_FLAGS:
                raise ValueError(f"CliOptionSpec.short '-{s_clean}' collides with reserved global CLI flag")
            object.__setattr__(self, "short", s_clean)
        require_pure_bool(self.required, "CliOptionSpec.required")
        object.__setattr__(self, "default", _sanitize_json_default(self.default))
        if self.group is not None:
            object.__setattr__(self, "group", require_pure_str(self.group, "CliOptionSpec.group", non_empty=True))
        validated_choices = _validate_cli_type_and_choices(self.type_name, self.choices, "CliOptionSpec")
        if validated_choices is not None:
            object.__setattr__(self, "choices", validated_choices)
        if self.type_name == "bool" and f"--no-{clean_long}" in _RESERVED_GLOBAL_CLI_FLAGS:
            raise ValueError(f"CliOptionSpec negated flag '--no-{clean_long}' collides with reserved global CLI flag")
        require_pure_str(self.summary, "CliOptionSpec.summary")

    @property
    def is_multi(self) -> bool:
        return self.type_name.startswith("list[")

    def to_json_dict(self) -> JsonObject:
        return {
            "field": self.field,
            "long_name": self.long_name,
            "short": self.short,
            "type": self.type_name,
            "required": self.required,
            "default": self.default,
            "group": self.group,
            "choices": list(self.choices) if self.choices is not None else None,
            "summary": self.summary,
        }

    @classmethod
    def from_json_dict(cls, doc: Mapping[str, object]) -> CliOptionSpec:
        raw_short = doc.get("short")
        raw_grp = doc.get("group")
        raw_choices = doc.get("choices")
        if raw_choices is not None and not isinstance(raw_choices, list):
            raise ValueError("CliOptionSpec.choices must be a JSON array of strings or null")
        safe_default = _sanitize_json_default(doc.get("default"))
        return cls(
            field=require_pure_str(doc.get("field"), "option.field", non_empty=True),
            long_name=require_pure_str(doc.get("long_name"), "option.long_name", non_empty=True),
            short=require_pure_str(raw_short, "option.short", non_empty=True) if raw_short is not None else None,
            type_name=require_pure_str(doc.get("type"), "option.type", non_empty=True),
            required=require_pure_bool(doc.get("required"), "option.required"),
            default=safe_default,
            group=require_pure_str(raw_grp, "option.group", non_empty=True) if raw_grp is not None else None,
            choices=require_typed_tuple(raw_choices, str, "option.choices") if raw_choices is not None else None,
            summary=require_pure_str(doc.get("summary", ""), "option.summary"),
        )


@dataclass(frozen=True, slots=True)
class CliSubscriptionSpec:
    """Static event subscription entry serialized in tasks.index.json."""

    event_id: EventId
    payload_filter: Optional[Mapping[str, tuple[JsonPrimitive, ...]]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, EventId):
            raise ValueError(f"CliSubscriptionSpec.event_id must be EventId, got {self.event_id!r}")
        if self.payload_filter is not None:
            object.__setattr__(self, "payload_filter", normalize_payload_filter(self.payload_filter))

    def to_json_dict(self) -> JsonObject:
        filt_json: Optional[MutableJsonObject] = None
        if self.payload_filter is not None:
            filt_json = {k: list(vals) for k, vals in self.payload_filter.items()}
        return {
            "event_id": self.event_id.value,
            "payload_filter": filt_json,
        }

    @classmethod
    def from_json_dict(cls, doc: Mapping[str, object]) -> CliSubscriptionSpec:
        eid = EventId(require_pure_str(doc.get("event_id"), "subscription.event_id", non_empty=True))
        raw_f = doc.get("payload_filter")
        if raw_f is not None and not isinstance(raw_f, Mapping):
            raise ValueError("CliSubscriptionSpec.payload_filter must be a JSON object or null")
        parsed_f: Optional[dict[str, tuple[JsonPrimitive, ...]]] = None
        if isinstance(raw_f, Mapping):
            parsed_f = {}
            for k, v in raw_f.items():
                key_s = require_pure_str(k, "payload_filter key", non_empty=True)
                if not isinstance(v, list):
                    raise ValueError("payload_filter entry must be a list of JSON primitives")
                prim_list: list[JsonPrimitive] = []
                for item in v:
                    if item is None or isinstance(item, (bool, int, float, str)):
                        prim_list.append(item)
                    else:
                        raise ValueError(f"Invalid non-primitive in payload_filter: {item!r}")
                parsed_f[key_s] = tuple(prim_list)
        return cls(event_id=eid, payload_filter=parsed_f)


@dataclass(frozen=True, slots=True)
class IndexedTaskEntry:
    """Complete static task entry inside tasks.index.json."""

    task_id: TaskId
    command_path: tuple[str, ...]
    aliases: tuple[str, ...]
    summary: str
    usage_pros: tuple[str, ...]
    usage_cons: tuple[str, ...]
    exposure: TaskExposure
    security_tier: SecurityTier
    dispatch_mode: DispatchMode
    interactive_tty: bool
    args: tuple[CliArgSpec, ...] = ()
    options: tuple[CliOptionSpec, ...] = ()
    subscriptions: tuple[CliSubscriptionSpec, ...] = ()
    periodic: Optional[PeriodicScheduleSpec] = None
    mutation_scope: SelfMutationScope = SelfMutationScope.NONE
    resource_key: Optional[str] = None
    concurrency_mode: ConcurrencyMode = ConcurrencyMode.PARALLEL
    timeout_ms: Optional[int] = None
    void_output: bool = False
    custom_render: bool = False
    custom_exit_code: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, TaskId):
            raise ValueError(f"IndexedTaskEntry.task_id must be TaskId, got {self.task_id!r}")
        object.__setattr__(self, "command_path", _validate_cli_token_seq(self.command_path, "command_path"))
        object.__setattr__(self, "aliases", _validate_cli_token_seq(self.aliases, "aliases"))
        require_pure_str(self.summary, "IndexedTaskEntry.summary")
        object.__setattr__(self, "usage_pros", require_typed_tuple(self.usage_pros, str, "usage_pros"))
        object.__setattr__(self, "usage_cons", require_typed_tuple(self.usage_cons, str, "usage_cons"))
        if not isinstance(self.exposure, TaskExposure):
            raise ValueError(f"Invalid TaskExposure: {self.exposure!r}")
        if self.exposure == TaskExposure.CLI_AND_SDK and not self.command_path:
            if self.task_id.module_id == CORE_MODULE_ID:
                raise ValueError("Built-in 'core' CLI task must declare a non-empty command_path")
            if self.aliases:
                raise ValueError(f"Module-root default CLI task '{self.task_id}' cannot declare task-level aliases")
        if not isinstance(self.security_tier, SecurityTier):
            raise ValueError(f"Invalid SecurityTier: {self.security_tier!r}")
        if not isinstance(self.dispatch_mode, DispatchMode):
            raise ValueError(f"Invalid DispatchMode: {self.dispatch_mode!r}")
        require_pure_bool(self.interactive_tty, "IndexedTaskEntry.interactive_tty")
        checked_args = require_typed_tuple(self.args, CliArgSpec, "args")
        seen_fields: set[str] = set()
        seen_var_arg = False
        seen_opt_arg = False
        for a_spec in checked_args:
            if a_spec.field in seen_fields:
                raise ValueError(f"Task '{self.task_id}': duplicate parameter field '{a_spec.field}'")
            seen_fields.add(a_spec.field)
            if seen_var_arg:
                raise ValueError(f"Task '{self.task_id}': variadic positional Arg must be the final Arg field")
            if a_spec.required and seen_opt_arg:
                raise ValueError(
                    f"Task '{self.task_id}': required positional Arg '{a_spec.field}' cannot follow an optional Arg"
                )
            if a_spec.is_variadic:
                seen_var_arg = True
            if not a_spec.required:
                seen_opt_arg = True
        object.__setattr__(self, "args", checked_args)
        checked_opts = require_typed_tuple(self.options, CliOptionSpec, "options")
        seen_flags: set[str] = set()
        for o_spec in checked_opts:
            if o_spec.field in seen_fields:
                raise ValueError(f"Task '{self.task_id}': duplicate parameter field '{o_spec.field}'")
            seen_fields.add(o_spec.field)
            long_tok = f"--{o_spec.long_name}"
            if long_tok in seen_flags:
                raise ValueError(f"Task '{self.task_id}': duplicate or colliding CLI option flag '{long_tok}'")
            seen_flags.add(long_tok)
            if o_spec.short is not None:
                short_tok = f"-{o_spec.short}"
                if short_tok in seen_flags:
                    raise ValueError(f"Task '{self.task_id}': duplicate or colliding CLI option flag '{short_tok}'")
                seen_flags.add(short_tok)
            if o_spec.type_name == "bool":
                neg_tok = f"--no-{o_spec.long_name}"
                if neg_tok in seen_flags:
                    raise ValueError(
                        f"Task '{self.task_id}': negated boolean CLI flag '{neg_tok}' collides with another option"
                    )
                seen_flags.add(neg_tok)
        object.__setattr__(self, "options", checked_opts)
        object.__setattr__(
            self,
            "subscriptions",
            require_typed_tuple(self.subscriptions, CliSubscriptionSpec, "subscriptions"),
        )
        if self.periodic is not None and not isinstance(self.periodic, PeriodicScheduleSpec):
            raise ValueError(f"Invalid PeriodicScheduleSpec: {self.periodic!r}")
        if not isinstance(self.mutation_scope, SelfMutationScope):
            raise ValueError(f"Invalid SelfMutationScope: {self.mutation_scope!r}")
        if self.resource_key is not None:
            require_pure_str(self.resource_key, "resource_key", non_empty=True)
        if not isinstance(self.concurrency_mode, ConcurrencyMode):
            raise ValueError(f"Invalid ConcurrencyMode: {self.concurrency_mode!r}")
        if self.timeout_ms is not None:
            require_pure_int(self.timeout_ms, "timeout_ms", min_val=1)
        require_pure_bool(self.void_output, "void_output")
        require_pure_bool(self.custom_render, "custom_render")
        require_pure_bool(self.custom_exit_code, "custom_exit_code")

    def to_route_spec(self) -> TaskRouteSpec:
        cli_spec: Optional[CliBindingSpec] = None
        if self.exposure == TaskExposure.CLI_AND_SDK:
            eff_cp = self.command_path if self.command_path else (self.task_id.module_id.value,)
            cli_spec = CliBindingSpec(
                command_path=eff_cp,
                summary=self.summary or f"Execute {self.task_id}",
                aliases=self.aliases,
                usage_pros=self.usage_pros,
                usage_cons=self.usage_cons,
            )
        return TaskRouteSpec(
            task_id=self.task_id,
            exposure=self.exposure,
            cli=cli_spec,
            dispatch_mode=self.dispatch_mode,
            mutation_scope=self.mutation_scope,
            interactive_tty=self.interactive_tty,
            security_tier=self.security_tier,
            resource_key=self.resource_key,
            concurrency_mode=self.concurrency_mode,
            timeout_ms=self.timeout_ms,
            subscriptions=tuple(
                SubscriptionRouteSpec(event_id=s.event_id, payload_filter=s.payload_filter)
                for s in self.subscriptions
            ),
            periodic=self.periodic,
        )

    def to_json_dict(self) -> JsonObject:
        periodic_json: JsonValue = None
        if self.periodic is not None:
            periodic_json = {
                "default_interval_sec": self.periodic.default_interval_sec,
                "interval_config_key": self.periodic.interval_config_key,
                "enabled_config_key": self.periodic.enabled_config_key,
            }
        out: MutableJsonObject = {
            "task_id": self.task_id.value,
            "command_path": list(self.command_path),
            "aliases": list(self.aliases),
            "summary": self.summary,
            "usage_pros": list(self.usage_pros),
            "usage_cons": list(self.usage_cons),
            "exposure": self.exposure.value,
            "security_tier": self.security_tier.value,
            "dispatch_mode": self.dispatch_mode.value,
            "interactive_tty": self.interactive_tty,
            "args": [a.to_json_dict() for a in self.args],
            "options": [o.to_json_dict() for o in self.options],
            "subscriptions": [s.to_json_dict() for s in self.subscriptions],
            "periodic": periodic_json,
            "mutation_scope": self.mutation_scope.value,
            "resource_key": self.resource_key,
            "concurrency_mode": self.concurrency_mode.value,
            "timeout_ms": self.timeout_ms,
            "void_output": self.void_output,
            "custom_render": self.custom_render,
            "custom_exit_code": self.custom_exit_code,
        }
        return out

    @classmethod
    def from_json_dict(cls, doc: Mapping[str, object]) -> IndexedTaskEntry:
        raw_cmd = doc.get("command_path", [])
        raw_al = doc.get("aliases", [])
        raw_pros = doc.get("usage_pros", [])
        raw_cons = doc.get("usage_cons", [])
        raw_args = doc.get("args", [])
        raw_opts = doc.get("options", [])
        raw_subs = doc.get("subscriptions", [])
        if not (
            isinstance(raw_cmd, list)
            and isinstance(raw_al, list)
            and isinstance(raw_pros, list)
            and isinstance(raw_cons, list)
            and isinstance(raw_args, list)
            and isinstance(raw_opts, list)
            and isinstance(raw_subs, list)
        ):
            raise ValueError("IndexedTaskEntry list fields must be JSON arrays")
        if not (
            all(isinstance(a, Mapping) for a in raw_args)
            and all(isinstance(o, Mapping) for o in raw_opts)
            and all(isinstance(s, Mapping) for s in raw_subs)
        ):
            raise ValueError("IndexedTaskEntry args, options, and subscriptions items must be JSON objects")
        raw_per = doc.get("periodic")
        if raw_per is not None and not isinstance(raw_per, Mapping):
            raise ValueError("IndexedTaskEntry periodic field must be a JSON object or null")
        periodic: Optional[PeriodicScheduleSpec] = None
        if isinstance(raw_per, Mapping):
            if "default_interval_sec" not in raw_per:
                raise ValueError("periodic.default_interval_sec is required")
            iv_raw = raw_per.get("default_interval_sec")
            if isinstance(iv_raw, bool) or not isinstance(iv_raw, (int, float)):
                raise ValueError("periodic.default_interval_sec must be numeric")
            ic_raw = raw_per.get("interval_config_key")
            ec_raw = raw_per.get("enabled_config_key")
            periodic = PeriodicScheduleSpec(
                default_interval_sec=float(iv_raw),
                interval_config_key=(
                    require_pure_str(ic_raw, "interval_config_key", non_empty=True) if ic_raw is not None else None
                ),
                enabled_config_key=(
                    require_pure_str(ec_raw, "enabled_config_key", non_empty=True) if ec_raw is not None else None
                ),
            )
        raw_mut = doc.get("mutation_scope", SelfMutationScope.NONE.value)
        raw_conc = doc.get("concurrency_mode", ConcurrencyMode.PARALLEL.value)
        raw_rk = doc.get("resource_key")
        raw_tmo = doc.get("timeout_ms")
        raw_void = doc.get("void_output", False)
        raw_crender = doc.get("custom_render", False)
        raw_cexit = doc.get("custom_exit_code", False)
        return cls(
            task_id=TaskId(require_pure_str(doc.get("task_id"), "task_id", non_empty=True)),
            command_path=require_typed_tuple(raw_cmd, str, "command_path"),
            aliases=require_typed_tuple(raw_al, str, "aliases"),
            summary=require_pure_str(doc.get("summary", ""), "summary"),
            usage_pros=require_typed_tuple(raw_pros, str, "usage_pros"),
            usage_cons=require_typed_tuple(raw_cons, str, "usage_cons"),
            exposure=TaskExposure(require_pure_str(doc.get("exposure"), "exposure", non_empty=True)),
            security_tier=SecurityTier(require_pure_str(doc.get("security_tier"), "security_tier", non_empty=True)),
            dispatch_mode=DispatchMode(require_pure_str(doc.get("dispatch_mode"), "dispatch_mode", non_empty=True)),
            interactive_tty=require_pure_bool(doc.get("interactive_tty", False), "interactive_tty"),
            args=tuple(CliArgSpec.from_json_dict(a) for a in raw_args),
            options=tuple(CliOptionSpec.from_json_dict(o) for o in raw_opts),
            subscriptions=tuple(CliSubscriptionSpec.from_json_dict(s) for s in raw_subs),
            periodic=periodic,
            mutation_scope=SelfMutationScope(require_pure_str(raw_mut, "mutation_scope", non_empty=True)),
            resource_key=require_pure_str(raw_rk, "resource_key", non_empty=True) if raw_rk is not None else None,
            concurrency_mode=ConcurrencyMode(require_pure_str(raw_conc, "concurrency_mode", non_empty=True)),
            timeout_ms=require_pure_int(raw_tmo, "timeout_ms", min_val=1) if raw_tmo is not None else None,
            void_output=require_pure_bool(raw_void, "void_output"),
            custom_render=require_pure_bool(raw_crender, "custom_render"),
            custom_exit_code=require_pure_bool(raw_cexit, "custom_exit_code"),
        )


@dataclass(frozen=True, slots=True)
class ModuleTasksIndex:
    """Module-level tasks.index.json schema v2 container."""

    module_id: ModuleId
    module_aliases: tuple[str, ...] = ()
    description: str = ""
    tasks: tuple[IndexedTaskEntry, ...] = ()
    schema_version: int = TASKS_INDEX_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, ModuleId):
            raise ValueError(f"ModuleTasksIndex.module_id must be ModuleId, got {self.module_id!r}")
        object.__setattr__(self, "module_aliases", _validate_cli_token_seq(self.module_aliases, "module_aliases"))
        require_pure_str(self.description, "ModuleTasksIndex.description")
        object.__setattr__(self, "tasks", require_typed_tuple(self.tasks, IndexedTaskEntry, "tasks"))
        ver = require_pure_int(self.schema_version, "schema_version", min_val=1)
        if ver != TASKS_INDEX_SCHEMA_VERSION:
            raise ValueError(f"Unsupported tasks.index.json schema_version {ver}; expected {TASKS_INDEX_SCHEMA_VERSION}")
        seen_tids: set[TaskId] = set()
        seen_cmd_paths: set[tuple[str, ...]] = set()
        root_default_count = 0
        for entry in self.tasks:
            if entry.task_id.module_id != self.module_id:
                raise ValueError(
                    f"ModuleTasksIndex '{self.module_id}' cannot contain foreign task '{entry.task_id}'"
                )
            if entry.task_id in seen_tids:
                raise ValueError(
                    f"ModuleTasksIndex '{self.module_id}' contains duplicate task_id '{entry.task_id}'"
                )
            seen_tids.add(entry.task_id)
            if entry.exposure == TaskExposure.CLI_AND_SDK:
                if not entry.command_path:
                    root_default_count += 1
                    if root_default_count > 1:
                        raise ValueError(
                            f"ModuleTasksIndex '{self.module_id}' can declare at most one root default CLI task"
                        )
                else:
                    if entry.command_path in seen_cmd_paths:
                        raise ValueError(
                            f"ModuleTasksIndex '{self.module_id}' contains duplicate CLI command_path {entry.command_path!r}"
                        )
                    seen_cmd_paths.add(entry.command_path)
        if root_default_count > 0 and (self.module_id.value,) in seen_cmd_paths:
            raise ValueError(
                f"ModuleTasksIndex '{self.module_id}' cannot combine root default cli=() with subcommand {(self.module_id.value,)!r}"
            )

    def to_route_specs(self) -> tuple[TaskRouteSpec, ...]:
        return tuple(entry.to_route_spec() for entry in self.tasks)

    def to_json_dict(self) -> JsonObject:
        return {
            "schema_version": self.schema_version,
            "module_id": self.module_id.value,
            "module_aliases": list(self.module_aliases),
            "description": self.description,
            "tasks": [t.to_json_dict() for t in self.tasks],
        }

    @classmethod
    def from_json_dict(cls, doc: Mapping[str, object]) -> ModuleTasksIndex:
        try:
            ver = require_pure_int(doc.get("schema_version"), "schema_version", min_val=1)
            mid = ModuleId(require_pure_str(doc.get("module_id"), "module_id", non_empty=True))
            raw_aliases = doc.get("module_aliases", [])
            raw_tasks = doc.get("tasks", [])
            if not isinstance(raw_aliases, list) or not isinstance(raw_tasks, list):
                raise ValueError("module_aliases and tasks must be JSON arrays")
            tasks: list[IndexedTaskEntry] = []
            for item in raw_tasks:
                if not isinstance(item, Mapping):
                    raise ValueError("Each task in tasks.index.json must be an object")
                tasks.append(IndexedTaskEntry.from_json_dict(item))
            return cls(
                module_id=mid,
                module_aliases=require_typed_tuple(raw_aliases, str, "module_aliases"),
                description=require_pure_str(doc.get("description", ""), "description"),
                tasks=tuple(tasks),
                schema_version=ver,
            )
        except (TypeError, ValueError) as exc:
            raise YscbError(ErrorCode.CONFIG_INVALID, f"Invalid tasks.index.json: {exc}") from exc


_CLI_SCALAR_VO_TYPES: frozenset[type[object]] = frozenset(
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


def _substitute_typevars(tp: object, subst: Mapping[object, object]) -> object:
    if not subst:
        return tp
    if isinstance(tp, TypeVar):
        return subst.get(tp, tp)
    origin = get_origin(tp)
    args = get_args(tp)
    if origin is None or not args:
        return tp
    if origin is Annotated:
        return Annotated[(_substitute_typevars(args[0], subst), *args[1:])]
    if origin in (Union, types.UnionType):
        resolved_u = tuple(_substitute_typevars(a, subst) for a in args)
        acc = resolved_u[0]
        for nxt in resolved_u[1:]:
            acc = Union[acc, nxt]
        return acc
    if origin is Literal:
        return tp
    if isinstance(origin, type):
        return origin[tuple(_substitute_typevars(a, subst) for a in args)]
    return tp


def _compile_input_dto_fields(input_type: object, task_id: TaskId) -> tuple[tuple[CliArgSpec, ...], tuple[CliOptionSpec, ...]]:
    cur_tp = input_type
    while get_origin(cur_tp) is Annotated:
        cur_tp = get_args(cur_tp)[0]
    if cur_tp is Empty:
        return ((), ())
    origin_tp = get_origin(cur_tp)
    subst_map: dict[object, object] = {}
    if isinstance(cur_tp, type) and dataclasses.is_dataclass(cur_tp) and cur_tp not in _CLI_SCALAR_VO_TYPES:
        if Generic in cur_tp.__mro__ and bool(cur_tp.__parameters__):
            raise ValueError(f"Task '{task_id}': generic request DTO {cur_tp!r} must specify concrete type arguments")
        dc_cls = cur_tp
    elif isinstance(origin_tp, type) and dataclasses.is_dataclass(origin_tp) and origin_tp not in _CLI_SCALAR_VO_TYPES:
        dc_cls = origin_tp
        subst_map = dict(zip(dc_cls.__parameters__, get_args(cur_tp)))
    else:
        raise ValueError(
            f"Task '{task_id}': CLI input_type must be Empty or a non-scalar request @dataclass DTO, got {input_type!r}"
        )
    raw_hints = resolve_dataclass_init_hints(dc_cls)
    hints = {k: _substitute_typevars(v, subst_map) for k, v in raw_hints.items()} if subst_map else raw_hints
    args_out: list[CliArgSpec] = []
    opts_out: list[CliOptionSpec] = []
    seen_variadic = False
    seen_optional_arg = False
    seen_opt_flags: set[str] = set()
    implicit_neg_flags: set[str] = set()

    for fld in dataclasses.fields(dc_cls):
        if not fld.init:
            continue
        raw_tp = hints.get(fld.name, fld.type)
        inner_tp, marker, is_opt = _unwrap_field_type_and_marker(raw_tp)
        tp_name, choices, is_seq = _extract_choices_and_type_name(inner_tp)
        has_dflt, dflt_json = _compute_field_default_json(fld)
        is_required = (not has_dflt) and (not is_opt)

        if isinstance(marker, Arg):
            if seen_variadic:
                raise ValueError(f"Task '{task_id}': variadic positional Arg must be the final Arg field")
            if is_required and seen_optional_arg:
                raise ValueError(
                    f"Task '{task_id}': required positional Arg '{fld.name}' cannot follow an optional positional Arg"
                )
            if is_seq:
                seen_variadic = True
            if not is_required:
                seen_optional_arg = True
            arg_name = marker.name if marker.name is not None else fld.name.replace("_", "-")
            eff_arg_dflt: JsonValue = dflt_json if has_dflt else (None if is_opt else ([] if is_seq else None))
            args_out.append(
                CliArgSpec(
                    field=fld.name,
                    name=arg_name,
                    type_name=tp_name,
                    required=is_required,
                    summary=marker.summary,
                    choices=choices,
                    default=eff_arg_dflt,
                )
            )
        else:
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
                    if flag_tok in seen_opt_flags or flag_tok in implicit_neg_flags:
                        raise ValueError(f"Task '{task_id}': duplicate or colliding CLI option flag '{flag_tok}'")
                    seen_opt_flags.add(flag_tok)
            has_bool_true, has_bool_false = (
                classify_cli_bool_choices(choices) if tp_name == "bool" else (False, False)
            )
            is_bivalent_bool = tp_name == "bool" and has_bool_true and has_bool_false
            allows_neg = tp_name == "bool"
            if allows_neg:
                neg_tok = f"--no-{long_clean}"
                if neg_tok in _RESERVED_GLOBAL_CLI_FLAGS or neg_tok in seen_opt_flags or neg_tok in implicit_neg_flags:
                    raise ValueError(
                        f"Task '{task_id}': negated boolean CLI flag '{neg_tok}' collides with another option"
                    )
                implicit_neg_flags.add(neg_tok)
            eff_default: JsonValue = (
                dflt_json if has_dflt else (False if is_bivalent_bool and not is_opt else None)
            )
            opts_out.append(
                CliOptionSpec(
                    field=fld.name,
                    long_name=long_clean,
                    short=short_clean,
                    type_name=tp_name,
                    required=is_required and not is_bivalent_bool,
                    default=eff_default,
                    group=opt_meta.group,
                    choices=choices,
                    summary=opt_meta.summary,
                )
            )
    return (tuple(args_out), tuple(opts_out))


def _compile_bound_task_entry(bound_task: BoundTask, *, is_root_default: bool = False) -> IndexedTaskEntry:
    meta: TaskMetadata[object, object] = bound_task.metadata
    cli_spec = meta.cli
    args, opts = _compile_input_dto_fields(meta.input_type, meta.task_id) if cli_spec is not None else ((), ())
    subs = tuple(
        CliSubscriptionSpec(event_id=s.event_id, payload_filter=s.payload_filter)
        for s in meta.subscriptions
    )
    concrete_out_branches = _iter_concrete_type_branches(meta.output_type)
    has_custom_render = any(issubclass(b, HumanRenderable) for b in concrete_out_branches)
    has_custom_exit = any(issubclass(b, ExitCodeProvider) for b in concrete_out_branches)
    eff_cmd_path = () if is_root_default else (cli_spec.command_path if cli_spec is not None else ())
    return IndexedTaskEntry(
        task_id=meta.task_id,
        command_path=eff_cmd_path,
        aliases=cli_spec.aliases if cli_spec is not None else (),
        summary=cli_spec.summary if cli_spec is not None else "",
        usage_pros=cli_spec.usage_pros if cli_spec is not None else (),
        usage_cons=cli_spec.usage_cons if cli_spec is not None else (),
        exposure=meta.exposure,
        security_tier=meta.security_tier,
        dispatch_mode=meta.dispatch_mode,
        interactive_tty=meta.interactive_tty,
        args=args,
        options=opts,
        subscriptions=subs,
        periodic=meta.periodic,
        mutation_scope=meta.mutation_scope,
        resource_key=meta.resource_key,
        concurrency_mode=meta.concurrency_mode,
        timeout_ms=meta.timeout_ms,
        void_output=(concrete_out_branches == (Empty,)),
        custom_render=has_custom_render,
        custom_exit_code=has_custom_exit,
    )


def compile_tasks_index(module_source: type[Module] | Module | YscbModule) -> ModuleTasksIndex:
    """Compile a declarative Module class/instance or YscbModule into a static ModuleTasksIndex."""
    if isinstance(module_source, type) and issubclass(module_source, Module):
        mod_inst = module_source()
        ymod = mod_inst.to_yscb_module()
        aliases = module_source.aliases
        desc = module_source.description
    elif isinstance(module_source, Module):
        cls_obj = type(module_source)
        ymod = module_source.to_yscb_module()
        aliases = cls_obj.aliases
        desc = cls_obj.description
    elif isinstance(module_source, YscbModule):
        ymod = module_source
        aliases, desc = lookup_compiled_module_surface_meta(module_source)
    else:
        raise TypeError(f"compile_tasks_index expects Module class/instance or YscbModule, got {module_source!r}")

    root_defaults = lookup_compiled_module_root_default_tasks(ymod)
    try:
        entries = tuple(
            _compile_bound_task_entry(bt, is_root_default=(bt.task_id in root_defaults))
            for bt in ymod.tasks()
        )
        return ModuleTasksIndex(
            module_id=ymod.module_id,
            module_aliases=aliases,
            description=desc,
            tasks=entries,
        )
    except ValueError as exc:
        raise YscbError(
            ErrorCode.CONFIG_INVALID,
            f"Invalid CLI task schema on '{ymod.module_id}': {exc}",
        ) from exc


class WorkspaceTasksIndexCache:
    """Zero-import loader and (.cache/tasks.index.json) fingerprint aggregator for installed module indices."""

    def __init__(
        self,
        yscb_root: HostPath,
        *,
        builtin_indices: Sequence[ModuleTasksIndex] = (),
    ) -> None:
        if not isinstance(yscb_root, HostPath):
            raise TypeError(f"yscb_root must be HostPath, got {type(yscb_root).__name__}")
        self._yscb_root = yscb_root
        self._builtins = require_typed_tuple(builtin_indices, ModuleTasksIndex, "builtin_indices")

    def _scan_disk_fingerprints(self) -> dict[str, tuple[HostPath, int, int]]:
        mods_hp = try_resolve_contained_subpath(self._yscb_root, MODULES_DIRNAME)
        if mods_hp is None or not os.path.isdir(str(mods_hp)) or is_symlink_or_reparse(str(mods_hp)):
            return {}
        found: dict[str, tuple[HostPath, int, int]] = {}
        try:
            with os.scandir(str(mods_hp)) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            return {}
        for ent in entries:
            if ent.name.startswith(".") or ent.is_symlink() or is_symlink_or_reparse(ent.path):
                continue
            try:
                if not ent.is_dir(follow_symlinks=False):
                    continue
                _ = ModuleId(ent.name)
            except (OSError, ValueError):
                continue
            idx_hp = try_resolve_contained_subpath(mods_hp, ent.name, _TASKS_INDEX_FILENAME)
            if idx_hp is None or is_symlink_or_reparse(str(idx_hp)):
                continue
            try:
                st = os.lstat(str(idx_hp))
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                found[ent.name] = (idx_hp, int(st.st_mtime_ns), int(st.st_size))
        return found

    def load_all(self, *, force_rebuild: bool = False) -> tuple[ModuleTasksIndex, ...]:
        """Load aggregated ModuleTasksIndex entries using (mtime_ns, size) fingerprint caching."""
        require_pure_bool(force_rebuild, "force_rebuild")
        disk_fps = self._scan_disk_fingerprints()
        expected_fp_doc: MutableJsonObject = {
            mod_name: [mtime_ns, size]
            for mod_name, (_hp, mtime_ns, size) in sorted(disk_fps.items())
        }
        cache_hp = try_resolve_contained_subpath(self._yscb_root, ".cache", _TASKS_INDEX_FILENAME)

        if not force_rebuild and cache_hp is not None:
            cached = read_json_dict(cache_hp)
            if (
                cached is not None
                and cached.get("schema_version") == TASKS_INDEX_SCHEMA_VERSION
                and cached.get("fingerprints") == expected_fp_doc
                and isinstance(cached.get("modules"), list)
            ):
                try:
                    raw_mods = cached["modules"]
                    raw_skipped = cached.get("skipped_modules", [])
                    if (
                        isinstance(raw_mods, list)
                        and all(isinstance(m, Mapping) for m in raw_mods)
                        and isinstance(raw_skipped, list)
                        and all(type(s) is str for s in raw_skipped)
                    ):
                        disk_indices = [ModuleTasksIndex.from_json_dict(m) for m in raw_mods]
                        loaded_ids = [m.module_id.value for m in disk_indices]
                        skipped_set = set(raw_skipped)
                        loaded_set = set(loaded_ids)
                        if (
                            len(loaded_ids) == len(loaded_set)
                            and len(raw_skipped) == len(skipped_set)
                            and loaded_set.isdisjoint(skipped_set)
                            and (loaded_set | skipped_set) == set(expected_fp_doc.keys())
                        ):
                            return self._merge_with_builtins(disk_indices)
                except YscbError:
                    pass

        rebuilt_disk: list[ModuleTasksIndex] = []
        skipped_disk: list[str] = []
        for mod_name in sorted(disk_fps):
            idx_hp, _mt, _sz = disk_fps[mod_name]
            try:
                raw_bytes = read_nofollow_regular_bytes(str(idx_hp), max_bytes=MAX_JSON_FILE_BYTES)
            except OSError:
                raw_bytes = None
            if raw_bytes is None:
                skipped_disk.append(mod_name)
                continue
            try:
                doc = strict_parse_json_object(raw_bytes.decode("utf-8"))
                parsed_idx = ModuleTasksIndex.from_json_dict(doc)
            except (UnicodeDecodeError, ValueError, YscbError):
                skipped_disk.append(mod_name)
                continue
            if parsed_idx.module_id.value == mod_name:
                rebuilt_disk.append(parsed_idx)
            else:
                skipped_disk.append(mod_name)

        if os.path.isdir(str(self._yscb_root)) and not is_symlink_or_reparse(str(self._yscb_root)):
            try:
                out_cache = resolve_contained_subpath(self._yscb_root, ".cache", _TASKS_INDEX_FILENAME)
                atomic_write_json(
                    out_cache,
                    {
                        "schema_version": TASKS_INDEX_SCHEMA_VERSION,
                        "fingerprints": expected_fp_doc,
                        "skipped_modules": skipped_disk,
                        "modules": [m.to_json_dict() for m in rebuilt_disk],
                    },
                )
            except (OSError, ValueError, YscbError):
                pass

        return self._merge_with_builtins(rebuilt_disk)

    def _merge_with_builtins(self, disk_indices: Sequence[ModuleTasksIndex]) -> tuple[ModuleTasksIndex, ...]:
        by_id: dict[ModuleId, ModuleTasksIndex] = {b.module_id: b for b in self._builtins}
        for d_idx in disk_indices:
            if d_idx.module_id not in by_id:
                by_id[d_idx.module_id] = d_idx
        ordered_keys = sorted(by_id.keys(), key=lambda m: (0 if m.value == "core" else 1, m.value))
        return tuple(by_id[k] for k in ordered_keys)
