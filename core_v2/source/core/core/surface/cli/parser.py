"""Zero-import static CLI command-tree router, DN-13 group default resolver, and orthogonal Option.group parser."""

from __future__ import annotations

from dataclasses import dataclass, field
import difflib
from enum import Enum
import json
import math
import re
from typing import Final, Mapping, NoReturn, Optional, Sequence

from core.execution.runtime import TaskExposure
from core.foundation import (
    ErrorCode,
    INT64_MAX,
    INT64_MIN,
    JsonObject,
    JsonValue,
    ModuleId,
    MutableJsonObject,
    YscbError,
    clone_strict_json_object,
    require_pure_bool,
    require_pure_str,
    require_typed_tuple,
)
from core.surface.cli.index import (
    CliOptionSpec,
    IndexedTaskEntry,
    ModuleTasksIndex,
    classify_cli_bool_choices,
)

_TRUE_LITERALS: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_FALSE_LITERALS: Final[frozenset[str]] = frozenset({"0", "false", "no", "off"})
_NEG_NUMERIC_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"^-(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)
_NUMERIC_POSITIONAL_TYPES: Final[frozenset[str]] = frozenset(
    {"int", "float", "list[int]", "list[float]"}
)


def _next_positional_accepts_negative_number(task_entry: IndexedTaskEntry, filled_count: int) -> bool:
    if not task_entry.args:
        return False
    if filled_count < len(task_entry.args):
        target_arg = task_entry.args[filled_count]
    elif task_entry.args[-1].is_variadic:
        target_arg = task_entry.args[-1]
    else:
        return False
    return target_arg.type_name in _NUMERIC_POSITIONAL_TYPES


def _clone_default_value(val: JsonValue) -> JsonValue:
    if isinstance(val, list):
        return [_clone_default_value(item) for item in val]
    if isinstance(val, Mapping):
        return dict(clone_strict_json_object(val, label="CLI default"))
    return val


class CliRouteKind(Enum):
    """Static resolution outcome kind for a CLI argv sequence."""

    HELP = "help"
    TASK = "task"


@dataclass(frozen=True, slots=True)
class GlobalCliFlags:
    """Extracted global flags alongside remaining command/task tokens."""

    help_requested: bool = False
    json_output: bool = False
    force_cold: bool = False
    approve_token: Optional[str] = None
    remaining_args: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_pure_bool(self.help_requested, "help_requested")
        require_pure_bool(self.json_output, "json_output")
        require_pure_bool(self.force_cold, "force_cold")
        if self.approve_token is not None:
            require_pure_str(self.approve_token, "approve_token", non_empty=True)
        object.__setattr__(self, "remaining_args", require_typed_tuple(self.remaining_args, str, "remaining_args"))


@dataclass(slots=True)
class CliCommandNode:
    """Node in the static zero-import CLI routing tree."""

    canonical_path: tuple[str, ...]
    summary: str = ""
    aliases: tuple[str, ...] = ()
    owner_module: Optional[ModuleId] = None
    default_task: Optional[IndexedTaskEntry] = None
    children: dict[str, CliCommandNode] = field(default_factory=dict)
    alias_to_child: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CliRouteResolution:
    """Resolved CLI route (either a Help target node or a validated Task + normalized DTO dict)."""

    kind: CliRouteKind
    node: CliCommandNode
    task_entry: Optional[IndexedTaskEntry] = None
    normalized_input: JsonObject = field(default_factory=dict)


def extract_global_flags(argv: Sequence[str]) -> GlobalCliFlags:
    """Extract global reserved flags (--help/-h, --json, --cold, --approve) before '--'."""
    tokens = require_typed_tuple(argv, str, "argv")
    help_req = False
    json_out = False
    cold = False
    approve_tok: Optional[str] = None
    rem: list[str] = []
    idx = 0
    after_double_dash = False

    while idx < len(tokens):
        tok = tokens[idx]
        if after_double_dash:
            rem.append(tok)
            idx += 1
            continue
        if tok == "--":
            rem.append(tok)
            after_double_dash = True
            idx += 1
            continue
        if tok in ("-h", "--help"):
            help_req = True
            idx += 1
            continue
        if tok == "--json":
            json_out = True
            idx += 1
            continue
        if tok == "--cold":
            cold = True
            idx += 1
            continue
        if tok.startswith("--approve="):
            val = tok[len("--approve=") :].strip()
            if not val:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Flag '--approve=' requires a non-empty token.")
            approve_tok = val
            idx += 1
            continue
        if tok == "--approve":
            if idx + 1 >= len(tokens) or not tokens[idx + 1].strip() or tokens[idx + 1].strip().startswith("-"):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Flag '--approve' requires a non-empty token argument.")
            approve_tok = tokens[idx + 1].strip()
            idx += 2
            continue
        rem.append(tok)
        idx += 1

    return GlobalCliFlags(
        help_requested=help_req,
        json_output=json_out,
        force_cold=cold,
        approve_token=approve_tok,
        remaining_args=tuple(rem),
    )


def _prune_inactive_node_aliases(node: CliCommandNode) -> None:
    for seg_name, child in node.children.items():
        child.aliases = tuple(
            al for al in child.aliases if al not in node.children and node.alias_to_child.get(al) == seg_name
        )
        _prune_inactive_node_aliases(child)


def build_cli_command_tree(indices: Sequence[ModuleTasksIndex]) -> CliCommandNode:
    """Construct the complete root command tree from static ModuleTasksIndex records."""
    root = CliCommandNode(canonical_path=(), summary="YS-Codebase 2.0 Microkernel CLI")
    ordered_indices = sorted(indices, key=lambda idx_item: (0 if idx_item.module_id.value == "core" else 1, idx_item.module_id.value))
    reserved_root_tokens: set[str] = {"init", "self-update"}

    for mod_idx in ordered_indices:
        is_core = mod_idx.module_id.value == "core"
        cli_tasks = [
            t for t in mod_idx.tasks
            if t.exposure == TaskExposure.CLI_AND_SDK and (bool(t.command_path) or not is_core)
        ]
        if not is_core and not cli_tasks:
            continue
        if is_core:
            mount_root = root
        else:
            mod_name = mod_idx.module_id.value
            if mod_name in reserved_root_tokens:
                continue
            mod_node = root.children.get(mod_name)
            if mod_node is not None and mod_node.owner_module != mod_idx.module_id:
                continue
            if mod_node is None:
                mod_node = CliCommandNode(
                    canonical_path=(mod_name,),
                    summary=mod_idx.description or f"Module '{mod_name}' commands",
                    aliases=mod_idx.module_aliases,
                    owner_module=mod_idx.module_id,
                )
                root.children[mod_name] = mod_node
                root.alias_to_child.pop(mod_name, None)
                for mod_alias in mod_idx.module_aliases:
                    if (
                        mod_alias not in reserved_root_tokens
                        and mod_alias not in root.children
                        and mod_alias not in root.alias_to_child
                    ):
                        root.alias_to_child[mod_alias] = mod_name
            mount_root = mod_node

        for task_entry in cli_tasks:
            if not task_entry.command_path:
                if not is_core:
                    mount_root.default_task = task_entry
                    if not mod_idx.description and task_entry.summary:
                        mount_root.summary = task_entry.summary
                continue
            cur = mount_root
            full_prefix = list(cur.canonical_path)
            aborted_path = False
            for seg_idx, seg in enumerate(task_entry.command_path):
                if cur is root and not is_core and seg in reserved_root_tokens:
                    aborted_path = True
                    break
                full_prefix.append(seg)
                is_leaf = seg_idx == len(task_entry.command_path) - 1
                child = cur.children.get(seg)
                if child is None:
                    child = CliCommandNode(
                        canonical_path=tuple(full_prefix),
                        summary=task_entry.summary if is_leaf else f"Command group '{seg}'",
                        aliases=task_entry.aliases if is_leaf else (),
                        owner_module=mod_idx.module_id,
                    )
                    cur.children[seg] = child
                    cur.alias_to_child.pop(seg, None)
                elif child.owner_module is not None and child.owner_module != mod_idx.module_id and not is_core:
                    aborted_path = True
                    break
                elif is_leaf:
                    child.summary = task_entry.summary or child.summary
                    child.aliases = task_entry.aliases
                if is_leaf and not aborted_path:
                    child.default_task = task_entry
                    for al in task_entry.aliases:
                        if cur is root and not is_core and al in reserved_root_tokens:
                            continue
                        if al not in cur.children and al not in cur.alias_to_child:
                            cur.alias_to_child[al] = seg
                cur = child
        if is_core:
            reserved_root_tokens.update(root.children.keys())
            reserved_root_tokens.update(root.alias_to_child.keys())

    _prune_inactive_node_aliases(root)
    return root


def _suggest_closest_command(unknown: str, node: CliCommandNode) -> Optional[str]:
    candidates = sorted(set(node.children.keys()) | set(node.alias_to_child.keys()))
    matches = difflib.get_close_matches(unknown, candidates, n=1, cutoff=0.55)
    return matches[0] if matches else None


def _raise_unknown_command_error(unknown: str, node: CliCommandNode) -> NoReturn:
    suggestion = _suggest_closest_command(unknown, node)
    ctx_path = " ".join(("yscb", *node.canonical_path))
    hint = f" Did you mean '{suggestion}'?" if suggestion is not None else ""
    remed = f"Run '{ctx_path} --help' to list available commands."
    if suggestion is not None:
        remed = f"Did you mean '{suggestion}'? {remed}"
    raise YscbError(
        ErrorCode.CODEC_VALIDATION_FAILED,
        f"Unknown command '{unknown}' under '{ctx_path}'.{hint}",
        remediation=remed,
    )


def _validate_bool_choice(val: bool, choices: Optional[tuple[str, ...]], label: str) -> None:
    if choices is None:
        return
    allowed: set[bool] = set()
    for ch in choices:
        c_low = ch.strip().lower()
        if c_low in _TRUE_LITERALS:
            allowed.add(True)
        elif c_low in _FALSE_LITERALS:
            allowed.add(False)
    if val not in allowed:
        joined = " | ".join(choices)
        raise YscbError(
            ErrorCode.CODEC_VALIDATION_FAILED,
            f"InvalidChoice for {label}: got {val!r}, expected one of [{joined}].",
        )


def _coerce_scalar_value(
    raw_val: str,
    type_name: str,
    choices: Optional[tuple[str, ...]],
    label: str,
) -> JsonValue:
    if type_name == "bool":
        low = raw_val.strip().lower()
        if low in _TRUE_LITERALS:
            bool_val = True
        elif low in _FALSE_LITERALS:
            bool_val = False
        else:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid boolean value {raw_val!r} for {label}.")
        _validate_bool_choice(bool_val, choices, label)
        return bool_val
    if type_name == "int":
        try:
            int_val = int(raw_val)
        except ValueError as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid integer value {raw_val!r} for {label}.") from exc
        if int_val < INT64_MIN or int_val > INT64_MAX:
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"Integer value {raw_val!r} out of 64-bit signed range for {label}.",
            )
        if choices is not None:
            try:
                allowed_ints = {int(c) for c in choices}
            except ValueError as exc:
                raise YscbError(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"Malformed integer choice list for {label}: {choices!r}.",
                ) from exc
            if int_val not in allowed_ints:
                joined = " | ".join(choices)
                raise YscbError(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"InvalidChoice for {label}: got {raw_val!r}, expected one of [{joined}].",
                )
        return int_val
    if type_name == "float":
        try:
            flt_val = float(raw_val)
        except ValueError as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid float value {raw_val!r} for {label}.") from exc
        if not math.isfinite(flt_val):
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"Non-finite float value {raw_val!r} forbidden for {label}.",
            )
        if choices is not None:
            try:
                allowed_flts = tuple(float(c) for c in choices)
            except ValueError as exc:
                raise YscbError(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"Malformed float choice list for {label}: {choices!r}.",
                ) from exc
            if not any(flt_val == fv for fv in allowed_flts):
                joined = " | ".join(choices)
                raise YscbError(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"InvalidChoice for {label}: got {raw_val!r}, expected one of [{joined}].",
                )
        return flt_val
    if choices is not None and raw_val not in choices:
        joined = " | ".join(choices)
        raise YscbError(
            ErrorCode.CODEC_VALIDATION_FAILED,
            f"InvalidChoice for {label}: got {raw_val!r}, expected one of [{joined}].",
        )
    if type_name == "dict":
        try:
            parsed = json.loads(raw_val)
        except ValueError as exc:
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"Invalid JSON object for {label}: {raw_val!r}") from exc
        if not isinstance(parsed, dict):
            raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, f"{label} expects a JSON object, got {type(parsed).__name__}")
        return dict(clone_strict_json_object(parsed, label=label))
    return raw_val


_GLOBAL_RESERVED_FLAGS: Final[frozenset[str]] = frozenset(
    {"-h", "--help", "--json", "--cold", "--approve", "--host-dir"}
)


def _is_non_value_flag_token(
    next_tok: str,
    task_entry: Optional[IndexedTaskEntry],
    opt_spec: Optional[CliOptionSpec] = None,
) -> bool:
    if next_tok == "--":
        return True
    allows_arbitrary_str = (
        opt_spec is not None
        and opt_spec.type_name in ("str", "list[str]")
        and (opt_spec.choices is None or next_tok in opt_spec.choices)
    )
    if allows_arbitrary_str:
        return False
    if next_tok in _GLOBAL_RESERVED_FLAGS or next_tok.startswith(("--approve=", "--host-dir=")):
        return True
    if _NEG_NUMERIC_TOKEN_RE.fullmatch(next_tok) is not None:
        if opt_spec is not None and opt_spec.type_name in _NUMERIC_POSITIONAL_TYPES:
            return False
        if task_entry is None or all(o.short != next_tok[1:] for o in task_entry.options if o.short is not None):
            return False
        return True
    if task_entry is not None:
        if next_tok in ("-y", "--yes"):
            return True
        if next_tok.startswith("--") and len(next_tok) > 2:
            body_l = next_tok[2:]
            cand_l = body_l.split("=", 1)[0]
            has_eq = "=" in body_l
            for decl_opt in task_entry.options:
                if decl_opt.long_name == cand_l:
                    return True
                if not has_eq and decl_opt.type_name == "bool" and cand_l == f"no-{decl_opt.long_name}":
                    return True
        elif next_tok.startswith("-") and not next_tok.startswith("--") and len(next_tok) > 1:
            cand_s = next_tok[1:].split("=", 1)[0]
            if any(decl_opt.short == cand_s for decl_opt in task_entry.options if decl_opt.short is not None):
                return True
    return False


def _bind_parsed_option(
    opt_spec: CliOptionSpec,
    *,
    task_entry: IndexedTaskEntry,
    tokens: Sequence[str],
    idx: int,
    has_inline: bool,
    inline_val: str,
    negated_bool: bool,
    group_label: str,
    error_label: str,
    parsed_fields: MutableJsonObject,
    multi_accum: dict[str, list[JsonValue]],
    group_hits: dict[str, dict[str, str]],
) -> int:
    if opt_spec.group is not None:
        hits = group_hits.setdefault(opt_spec.group, {})
        hits.setdefault(opt_spec.field, group_label)

    if opt_spec.type_name == "bool":
        if negated_bool:
            bool_v = False
        elif has_inline:
            bool_v = bool(_coerce_scalar_value(inline_val, "bool", None, error_label))
        else:
            bool_v = True
        _validate_bool_choice(bool_v, opt_spec.choices, error_label)
        parsed_fields[opt_spec.field] = bool_v
        return idx + 1

    if has_inline:
        raw_v = inline_val
        next_idx = idx + 1
    else:
        if idx + 1 >= len(tokens) or _is_non_value_flag_token(tokens[idx + 1], task_entry, opt_spec):
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"Option '{error_label}' requires a value.",
            )
        raw_v = tokens[idx + 1]
        next_idx = idx + 2

    if opt_spec.is_multi:
        elem_tp = opt_spec.type_name[5:-1]
        coerced = _coerce_scalar_value(raw_v, elem_tp, opt_spec.choices, error_label)
        multi_accum.setdefault(opt_spec.field, []).append(coerced)
    else:
        parsed_fields[opt_spec.field] = _coerce_scalar_value(
            raw_v, opt_spec.type_name, opt_spec.choices, error_label
        )
    return next_idx


def _parse_task_tokens(task_entry: IndexedTaskEntry, tokens: Sequence[str]) -> JsonObject:
    by_long: dict[str, CliOptionSpec] = {opt.long_name: opt for opt in task_entry.options}
    by_short: dict[str, CliOptionSpec] = {
        opt.short: opt for opt in task_entry.options if opt.short is not None
    }
    parsed_fields: MutableJsonObject = {}
    multi_accum: dict[str, list[JsonValue]] = {}
    group_hits: dict[str, dict[str, str]] = {}
    positionals: list[str] = []

    idx = 0
    after_dd = False
    while idx < len(tokens):
        tok = tokens[idx]
        if after_dd:
            positionals.append(tok)
            idx += 1
            continue
        if tok == "--":
            after_dd = True
            idx += 1
            continue
        if tok in ("-y", "--yes") and "yes" not in by_long and "y" not in by_short:
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"Static '{tok}' bypass flag is forbidden on '{task_entry.task_id}'; use --approve=<token> when gated.",
            )
        if tok.startswith("--") and len(tok) > 2:
            body = tok[2:]
            if "=" in body:
                opt_name, inline_val = body.split("=", 1)
                has_inline = True
            else:
                opt_name, inline_val = body, ""
                has_inline = False

            negated_bool = False
            opt_spec = by_long.get(opt_name)
            if opt_spec is None and opt_name.startswith("no-") and not has_inline:
                cand_spec = by_long.get(opt_name[3:])
                if cand_spec is not None and cand_spec.type_name == "bool":
                    opt_spec = cand_spec
                    negated_bool = True

            if opt_spec is None:
                raise YscbError(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"Unknown option '--{opt_name}' for task '{task_entry.task_id}'.",
                )
            display_flag = f"--{opt_name}"
            idx = _bind_parsed_option(
                opt_spec,
                task_entry=task_entry,
                tokens=tokens,
                idx=idx,
                has_inline=has_inline,
                inline_val=inline_val,
                negated_bool=negated_bool,
                group_label=display_flag,
                error_label=display_flag,
                parsed_fields=parsed_fields,
                multi_accum=multi_accum,
                group_hits=group_hits,
            )
            continue

        if tok.startswith("-") and len(tok) > 1:
            body = tok[1:]
            if "=" in body:
                s_key, s_val = body.split("=", 1)
                has_s_val = True
            else:
                s_key, s_val = body, ""
                has_s_val = False
            opt_spec = by_short.get(s_key)
            if opt_spec is None:
                if (
                    not has_s_val
                    and _NEG_NUMERIC_TOKEN_RE.fullmatch(tok) is not None
                    and _next_positional_accepts_negative_number(task_entry, len(positionals))
                ):
                    positionals.append(tok)
                    idx += 1
                    continue
                raise YscbError(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"Unknown short option '-{s_key}' for task '{task_entry.task_id}'.",
                )
            s_has_t, s_has_f = classify_cli_bool_choices(opt_spec.choices)
            false_only_short = bool(
                not has_s_val
                and opt_spec.type_name == "bool"
                and s_has_f
                and not s_has_t
            )
            idx = _bind_parsed_option(
                opt_spec,
                task_entry=task_entry,
                tokens=tokens,
                idx=idx,
                has_inline=has_s_val,
                inline_val=s_val,
                negated_bool=false_only_short,
                group_label=(f"--no-{opt_spec.long_name}" if false_only_short else f"--{opt_spec.long_name}"),
                error_label=f"-{s_key}",
                parsed_fields=parsed_fields,
                multi_accum=multi_accum,
                group_hits=group_hits,
            )
            continue

        positionals.append(tok)
        idx += 1

    for grp_name, used_field_map in group_hits.items():
        if len(used_field_map) >= 2:
            joined_flags = ", ".join(used_field_map.values())
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"Mutually exclusive options in group '{grp_name}' cannot be combined: {joined_flags}.",
            )

    for opt_spec in task_entry.options:
        if opt_spec.field in multi_accum:
            parsed_fields[opt_spec.field] = list(multi_accum[opt_spec.field])
        elif opt_spec.field not in parsed_fields:
            if opt_spec.required:
                m_has_t, m_has_f = classify_cli_bool_choices(opt_spec.choices)
                false_only = opt_spec.type_name == "bool" and m_has_f and not m_has_t
                req_flag = f"--no-{opt_spec.long_name}" if false_only else f"--{opt_spec.long_name}"
                raise YscbError(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"Missing required option '{req_flag}' for task '{task_entry.task_id}'.",
                )
            parsed_fields[opt_spec.field] = _clone_default_value(opt_spec.default)

    pos_idx = 0
    for arg_spec in task_entry.args:
        if arg_spec.is_variadic:
            rem_pos = positionals[pos_idx:]
            pos_idx = len(positionals)
            if arg_spec.required and not rem_pos:
                raise YscbError(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"Missing required positional argument '<{arg_spec.name}...>' for task '{task_entry.task_id}'.",
                )
            if rem_pos:
                elem_tp = arg_spec.type_name[5:-1]
                parsed_fields[arg_spec.field] = [
                    _coerce_scalar_value(item, elem_tp, arg_spec.choices, f"<{arg_spec.name}>")
                    for item in rem_pos
                ]
            else:
                parsed_fields[arg_spec.field] = _clone_default_value(arg_spec.default)
        else:
            if pos_idx < len(positionals):
                parsed_fields[arg_spec.field] = _coerce_scalar_value(
                    positionals[pos_idx], arg_spec.type_name, arg_spec.choices, f"<{arg_spec.name}>"
                )
                pos_idx += 1
            elif arg_spec.required:
                raise YscbError(
                    ErrorCode.CODEC_VALIDATION_FAILED,
                    f"Missing required positional argument '<{arg_spec.name}>' for task '{task_entry.task_id}'.",
                )
            else:
                parsed_fields[arg_spec.field] = _clone_default_value(arg_spec.default)

    if pos_idx < len(positionals):
        extra = positionals[pos_idx]
        raise YscbError(
            ErrorCode.CODEC_VALIDATION_FAILED,
            f"Unexpected positional argument '{extra}' for task '{task_entry.task_id}'.",
        )

    return parsed_fields


def _lookup_value_taking_option(tok: str, task_entry: Optional[IndexedTaskEntry]) -> Optional[CliOptionSpec]:
    if (
        task_entry is None
        or not tok.startswith("-")
        or tok == "--"
        or "=" in tok
        or tok in _GLOBAL_RESERVED_FLAGS
        or tok == "--host-dir"
    ):
        return None
    if tok.startswith("--") and len(tok) > 2:
        opt_name = tok[2:]
        for opt in task_entry.options:
            if opt.long_name == opt_name:
                return opt if opt.type_name != "bool" else None
        return None
    if len(tok) > 1:
        s_key = tok[1:]
        for opt in task_entry.options:
            if opt.short == s_key:
                return opt if opt.type_name != "bool" else None
    return None


def extract_contextual_global_flags(
    argv: Sequence[str],
    indices: Sequence[ModuleTasksIndex],
) -> GlobalCliFlags:
    """Extract global flags while preserving option values of matched task options."""
    tokens = require_typed_tuple(argv, str, "argv")
    root = build_cli_command_tree(indices)
    cur = root
    in_cmd_prefix = True
    after_double_dash = False
    help_req = False
    json_out = False
    cold = False
    approve_tok: Optional[str] = None
    rem: list[str] = []
    idx = 0

    while idx < len(tokens):
        tok = tokens[idx]
        if after_double_dash:
            rem.append(tok)
            idx += 1
            continue
        if tok == "--":
            rem.append(tok)
            after_double_dash = True
            in_cmd_prefix = False
            idx += 1
            continue
        matched_val_opt = _lookup_value_taking_option(tok, cur.default_task) if not in_cmd_prefix else None
        if matched_val_opt is not None:
            rem.append(tok)
            if idx + 1 < len(tokens) and not _is_non_value_flag_token(
                tokens[idx + 1], cur.default_task, matched_val_opt
            ):
                rem.append(tokens[idx + 1])
                idx += 2
            else:
                idx += 1
            continue
        if tok in ("-h", "--help"):
            help_req = True
            idx += 1
            continue
        if tok == "--json":
            json_out = True
            idx += 1
            continue
        if tok == "--cold":
            cold = True
            idx += 1
            continue
        if tok.startswith("--approve="):
            val = tok[len("--approve=") :].strip()
            if not val:
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Flag '--approve=' requires a non-empty token.")
            approve_tok = val
            idx += 1
            continue
        if tok == "--approve":
            if idx + 1 >= len(tokens) or not tokens[idx + 1].strip() or tokens[idx + 1].strip().startswith("-"):
                raise YscbError(ErrorCode.CODEC_VALIDATION_FAILED, "Flag '--approve' requires a non-empty token argument.")
            approve_tok = tokens[idx + 1].strip()
            idx += 2
            continue
        if in_cmd_prefix:
            if tok.startswith("-"):
                in_cmd_prefix = False
                continue
            canon_child = tok if tok in cur.children else cur.alias_to_child.get(tok, tok)
            if canon_child in cur.children:
                cur = cur.children[canon_child]
                rem.append(tok)
                idx += 1
                continue
            in_cmd_prefix = False
            continue
        rem.append(tok)
        idx += 1

    return GlobalCliFlags(
        help_requested=help_req,
        json_output=json_out,
        force_cold=cold,
        approve_token=approve_tok,
        remaining_args=tuple(rem),
    )


def resolve_cli_invocation(
    flags: GlobalCliFlags,
    indices: Sequence[ModuleTasksIndex],
) -> CliRouteResolution:
    """Resolve CLI tokens against the static command tree with DN-13 group default & fuzzy suggestions."""
    root = build_cli_command_tree(indices)
    tokens = flags.remaining_args
    cur = root
    idx = 0

    while idx < len(tokens):
        tok = tokens[idx]
        if tok == "--" or tok.startswith("-"):
            break
        canon_child = tok if tok in cur.children else cur.alias_to_child.get(tok, tok)
        if canon_child in cur.children:
            cur = cur.children[canon_child]
            idx += 1
            continue
        break

    tail_tokens = tokens[idx:]
    if flags.help_requested:
        if (
            tail_tokens
            and not tail_tokens[0].startswith("-")
            and tail_tokens[0] != "--"
            and cur.children
            and (cur.default_task is None or not cur.default_task.args)
        ):
            _raise_unknown_command_error(tail_tokens[0], cur)
        return CliRouteResolution(kind=CliRouteKind.HELP, node=cur, task_entry=cur.default_task)

    if not tokens:
        return CliRouteResolution(kind=CliRouteKind.HELP, node=root)

    if cur.children:
        if cur.default_task is None:
            if not tail_tokens:
                return CliRouteResolution(kind=CliRouteKind.HELP, node=cur)
            first_tail = tail_tokens[0]
            if not first_tail.startswith("-"):
                _raise_unknown_command_error(first_tail, cur)
            raise YscbError(
                ErrorCode.CODEC_VALIDATION_FAILED,
                f"Command group '{' '.join(('yscb', *cur.canonical_path))}' requires a subcommand.",
                remediation=f"Run 'yscb {' '.join(cur.canonical_path)} --help' to inspect subcommands.",
            )
        if tail_tokens and not tail_tokens[0].startswith("-") and tail_tokens[0] != "--":
            if not cur.default_task.args:
                _raise_unknown_command_error(tail_tokens[0], cur)

    if cur.default_task is None:
        _raise_unknown_command_error(tokens[0], root)

    normalized_dto = _parse_task_tokens(cur.default_task, tail_tokens)
    return CliRouteResolution(
        kind=CliRouteKind.TASK,
        node=cur,
        task_entry=cur.default_task,
        normalized_input=normalized_dto,
    )
