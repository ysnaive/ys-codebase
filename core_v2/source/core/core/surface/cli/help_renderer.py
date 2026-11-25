"""1.x-faithful HelpRenderer formatting Security/Dispatch badges, Arguments, grouped Options, Pros/Cons, and Subcommands."""

from __future__ import annotations

import json
from typing import Optional, Sequence

from core.execution.runtime import CORE_MODULE_ID
from core.surface.cli.caller_mode import CallerMode
from core.surface.cli.index import CliArgSpec, CliOptionSpec, IndexedTaskEntry, classify_cli_bool_choices
from core.surface.cli.parser import CliCommandNode


def _format_arg_token(arg: CliArgSpec) -> str:
    choice_Part = f"=[{' | '.join(arg.choices)}]" if arg.choices else ""
    ellipsis = "..." if arg.is_variadic else ""
    body = f"{arg.name}{choice_Part}{ellipsis}"
    return f"<{body}>" if arg.required else f"[{body}]"


def _format_option_flag_spec(opt: CliOptionSpec) -> str:
    short_prefix = f"-{opt.short}, " if opt.short is not None else ""
    if opt.type_name == "bool":
        has_true, has_false = classify_cli_bool_choices(opt.choices)
        if has_true and has_false:
            return f"{short_prefix}--{opt.long_name} / --no-{opt.long_name}"
        if has_false and not has_true:
            return f"{short_prefix}--no-{opt.long_name}"
        return f"{short_prefix}--{opt.long_name}"
    val_hint = f"[{' | '.join(opt.choices)}]" if opt.choices else opt.type_name.upper()
    return f"{short_prefix}--{opt.long_name} <{val_hint}>"


def _format_option_meta_suffix(opt: CliOptionSpec) -> str:
    parts: list[str] = []
    if opt.required:
        parts.append("required")
    elif opt.default is not None:
        parts.append(f"default: {json.dumps(opt.default, ensure_ascii=False)}")
    return f" ({', '.join(parts)})" if parts else ""


class HelpRenderer:
    """Zero-import 1.x-compatible CLI help card renderer with compact ASCII mode for AI/non-TTY callers."""

    def __init__(self, caller_mode: CallerMode = CallerMode.HUMAN_TTY) -> None:
        if not isinstance(caller_mode, CallerMode):
            raise TypeError(f"caller_mode must be CallerMode, got {type(caller_mode).__name__}")
        self._caller_mode = caller_mode

    @property
    def compact_mode(self) -> bool:
        return self._caller_mode in (CallerMode.AGENT, CallerMode.NON_TTY)

    def render_node(self, node: CliCommandNode) -> str:
        """Render complete help text for root, module/group, or leaf task nodes."""
        cmd_prefix = " ".join(("yscb", *node.canonical_path))
        task_entry = node.default_task
        lines: list[str] = []

        usage_tail: list[str] = []
        if node.children:
            usage_tail.append("<command>" if task_entry is None else "[command]")
        if task_entry is not None:
            usage_tail.extend(_format_arg_token(a) for a in task_entry.args)
        usage_tail.append("[options]")
        lines.append(f"Usage: {cmd_prefix} {' '.join(usage_tail)}")

        summary_txt = task_entry.summary if (task_entry is not None and task_entry.summary) else node.summary
        if summary_txt:
            lines.append("")
            lines.append(summary_txt)

        if node.aliases:
            lines.append(f"Aliases  : {', '.join(node.aliases)}")

        if task_entry is not None:
            sec_badge = task_entry.security_tier.value.upper()
            disp_badge = task_entry.dispatch_mode.value.upper()
            lines.append("")
            lines.append(f"Security : [{sec_badge}]")
            lines.append(f"Dispatch : [{disp_badge}]")
            if node.children:
                lines.append(f"Default  : Runs '{task_entry.task_id}' when invoked without a subcommand")

        if node.children:
            lines.append("")
            lines.append("SUBCOMMANDS:")
            lines.extend(self._render_subcommands(node))

        if task_entry is not None:
            if task_entry.args:
                lines.append("")
                lines.append("ARGUMENTS:")
                lines.extend(self._render_arguments(task_entry.args))

            if task_entry.options:
                lines.append("")
                lines.append("OPTIONS:")
                lines.extend(self._render_options(task_entry.options))

            if task_entry.usage_pros:
                lines.append("")
                lines.append("RECOMMENDED USAGE (Pros):")
                for item in task_entry.usage_pros:
                    lines.append(f"  + {item}")

            if task_entry.usage_cons:
                lines.append("")
                lines.append("RESTRICTIONS & GATES (Cons):")
                for item in task_entry.usage_cons:
                    lines.append(f"  - {item}")

        lines.append("")
        lines.append("GLOBAL OPTIONS:")
        lines.extend(self._render_global_options())
        return "\n".join(lines) + "\n"

    def _render_subcommands(self, node: CliCommandNode) -> list[str]:
        rows: list[tuple[str, str]] = []
        for child_name in sorted(node.children):
            child = node.children[child_name]
            alias_part = f" ({', '.join(child.aliases)})" if child.aliases else ""
            badge = f"[{child.default_task.security_tier.value.upper()}] " if child.default_task is not None else ""
            rows.append((f"{child_name}{alias_part}", f"{badge}{child.summary}".strip()))
        return self._format_two_col(rows)

    def _render_arguments(self, args: Sequence[CliArgSpec]) -> list[str]:
        rows: list[tuple[str, str]] = []
        for arg in args:
            req_tag = "required" if arg.required else "optional"
            desc = f"{arg.summary} ({req_tag})".strip() if arg.summary else f"({req_tag})"
            rows.append((_format_arg_token(arg), desc))
        return self._format_two_col(rows)

    def _render_options(self, options: Sequence[CliOptionSpec]) -> list[str]:
        ungrouped: list[CliOptionSpec] = []
        grouped: dict[str, list[CliOptionSpec]] = {}
        for opt in options:
            if opt.group is None:
                ungrouped.append(opt)
            else:
                grouped.setdefault(opt.group, []).append(opt)

        out: list[str] = []
        if ungrouped:
            rows = [
                (_format_option_flag_spec(o), f"{o.summary}{_format_option_meta_suffix(o)}".strip())
                for o in ungrouped
            ]
            out.extend(self._format_two_col(rows))

        for grp_name, grp_opts in grouped.items():
            if out:
                out.append("")
            out.append(f"  [Group: {grp_name} (Mutually Exclusive)]")
            rows = [
                (_format_option_flag_spec(o), f"{o.summary}{_format_option_meta_suffix(o)}".strip())
                for o in grp_opts
            ]
            out.extend(self._format_two_col(rows, indent="    "))
        return out

    def _render_global_options(self) -> list[str]:
        rows: list[tuple[str, str]] = [
            ("-h, --help", "Show zero-import command help and exit"),
            ("--json", "Emit strict single-object TaskOutcome JSON to stdout"),
            ("--cold", "Force local cold execution bypassing warm daemon"),
            ("--approve=<token>", "Consume single-use approval token for GATED tasks"),
            ("--host-dir=<path>", "Explicit workspace host directory override"),
            ("--profile", "Print hierarchical execution timing tree to stderr"),
            ("--profile-mem", "Track tracemalloc memory allocations and print profile tree to stderr"),
        ]
        return self._format_two_col(rows)

    def _format_two_col(
        self,
        rows: Sequence[tuple[str, str]],
        *,
        indent: str = "  ",
    ) -> list[str]:
        if not rows:
            return []
        if self.compact_mode:
            return [
                f"{indent}{left} : {right}" if right else f"{indent}{left}"
                for left, right in rows
            ]
        width = min(36, max(len(left) for left, _ in rows))
        rendered: list[str] = []
        for left, right in rows:
            if not right:
                rendered.append(f"{indent}{left}")
            elif len(left) <= width:
                rendered.append(f"{indent}{left.ljust(width)}  {right}")
            else:
                rendered.append(f"{indent}{left}\n{indent}{' ' * width}  {right}")
        return rendered


def render_task_help(
    task_entry: IndexedTaskEntry,
    *,
    caller_mode: CallerMode = CallerMode.HUMAN_TTY,
    module_prefix: Optional[str] = None,
) -> str:
    """Convenience helper rendering standalone leaf task help."""
    eff_prefix = (
        (None if task_entry.task_id.module_id == CORE_MODULE_ID else task_entry.task_id.module_id.value)
        if module_prefix is None
        else module_prefix
    )
    canon = (eff_prefix, *task_entry.command_path) if eff_prefix else task_entry.command_path
    node = CliCommandNode(
        canonical_path=canon,
        summary=task_entry.summary,
        aliases=task_entry.aliases,
        owner_module=task_entry.task_id.module_id,
        default_task=task_entry,
    )
    return HelpRenderer(caller_mode).render_node(node)
