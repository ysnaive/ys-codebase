"""
Core Commands - Unified Terminal Help Renderer.
100% Python Standard Library.
"""
from typing import Dict, List, Optional

from core.commands.registry import ArgSpec, CommandSpec, CommandsRegistry, ModuleSpec, OptionSpec


class HelpRenderer:
    """
    生態系統一 Help 格式化終端渲染器。
    提供全域、模組級與指令級結構化說明輸出。
    """

    @staticmethod
    def _tier_badge(tier: str) -> str:
        tier_lower = tier.lower()
        if tier_lower in ("safe", "green"):
            return "🟢 自主安全 (safe)"
        elif tier_lower in ("gated", "danger", "red"):
            return "🔴 授權守門 (gated)"
        elif tier_lower in ("conditional", "warn", "warning", "yellow"):
            return "🟡 階段條件 (conditional)"
        return f"[{tier}]"

    @classmethod
    def format_arg_placeholder(cls, arg_spec: ArgSpec) -> str:
        """依據 required 與 choice 轉譯視覺格式化佔位符。"""
        if arg_spec.choice:
            choice_str = " | ".join(arg_spec.choice)
            return f"<{arg_spec.name}=[{choice_str}]>" if arg_spec.required else f"[{arg_spec.name}=[{choice_str}]]"
        return f"<{arg_spec.name}>" if arg_spec.required else f"[{arg_spec.name}]"

    @classmethod
    def render_global_help(cls, registry: CommandsRegistry) -> str:
        """渲染全域 CLI 幫助訊息。"""
        lines = [
            "=" * 80,
            "YS-Codebase - Ultra-Thin Modular Microkernel CLI",
            "=" * 80,
            "USAGE:",
            "  python yscb.py <command> [options]",
            "  python yscb.py <module> <command> [options]",
            "",
            "CORE COMMANDS:",
            "  init <root>             Initialize workspace and unpack core module",
        ]

        core_mod = registry.get_module("core")
        if core_mod:
            for cmd_name, cmd_spec in sorted(core_mod.commands.items()):
                if cmd_spec.args:
                    args_disp = " ".join([cls.format_arg_placeholder(a) for a in cmd_spec.args.values()])
                    disp_name = f"{cmd_name} {args_disp}"
                else:
                    disp_name = cmd_name
                lines.append(f"  {disp_name:<23} {cmd_spec.description}")
        else:
            lines.extend([
                "  install <module>        Install a module from provider or local package",
                "  update [module]         Update installed module(s) to latest version",
                "  remove <module>         Remove an installed module from environment",
                "  list                    List all installed modules, versions and providers",
                "  status                  Health check and runtime diagnostic report",
                "  reload                  Reconcile and refresh runtime environment",
                "  rollback [snapshot]     Revert environment to the previous snapshot state",
                "  uri <resolve|to-uri>    Resolve canonical semantic URI to physical path",
                "  config <subcmd>         YS-Codebase module configuration manager",
            ])

        lines.append("")
        lines.append("MODULE COMMANDS:")
        other_modules = [m for m in registry.list_modules() if m != "core"]
        if other_modules:
            for m in other_modules:
                mod = registry.get_module(m)
                desc = mod.description if mod and mod.description else f"{m} module tools"
                alias_str = f" (aliases: {', '.join(mod.module_alias)})" if mod and mod.module_alias else ""
                lines.append(f"  {m:<23} {desc}{alias_str}")
        else:
            lines.append("  (No external modules registered)")

        lines.extend([
            "",
            "GLOBAL OPTIONS:",
            "  -h, --help              Show this help message and exit",
            "=" * 80,
        ])
        return "\n".join(lines)

    @classmethod
    def render_module_help(cls, module_name: str, mod_spec: ModuleSpec) -> str:
        """渲染模組級 CLI 幫助訊息。"""
        lines = [
            "=" * 80,
            f"YS-Codebase Module: {module_name}",
            "=" * 80,
        ]
        if mod_spec.description:
            lines.append(f"Description: {mod_spec.description}")
        if mod_spec.module_alias:
            lines.append(f"Aliases    : {', '.join(mod_spec.module_alias)}")

        lines.extend([
            "",
            "USAGE:",
            f"  python yscb.py {module_name} <command> [options]",
            "",
            "AVAILABLE COMMANDS:",
        ])

        if mod_spec.commands:
            for cmd_name, cmd_spec in sorted(mod_spec.commands.items()):
                tier_tag = f"[{cmd_spec.tier}]"
                if cmd_spec.args:
                    args_disp = " ".join([cls.format_arg_placeholder(a) for a in cmd_spec.args.values()])
                    disp_name = f"{cmd_name} {args_disp}"
                else:
                    disp_name = cmd_name
                lines.append(f"  {disp_name:<25} {tier_tag:<10} {cmd_spec.description}")
        else:
            lines.append("  (No commands defined)")

        lines.extend([
            "",
            "Run 'python yscb.py " + module_name + " <command> --help' for command details.",
            "=" * 80,
        ])
        return "\n".join(lines)

    @classmethod
    def render_cmd_help(cls, module_name: str, cmd_name: str, cmd_spec: CommandSpec) -> str:
        """渲染指令級 CLI 幫助訊息。"""
        args_str = " ".join([cls.format_arg_placeholder(a) for a in cmd_spec.args.values()])
        usage_args = f" {args_str}" if args_str else ""
        subcmd_ph = " <subcommand>" if cmd_spec.cmd and not cmd_spec.args else ""
        lines = [
            "=" * 80,
            f"Command: python yscb.py {module_name} {cmd_name}",
            "=" * 80,
            f"Description: {cmd_spec.description}",
            f"Security   : {cls._tier_badge(cmd_spec.tier)}",
            f"Server Mode: {'✅ Hot IPC Compatible' if cmd_spec.server_compatible else 'Local Cold Run Only'}",
            "",
            "USAGE:",
            f"  python yscb.py {module_name} {cmd_name}{subcmd_ph}{usage_args} [options]",
        ]

        # 渲染子指令清單 (SUBCOMMANDS)
        if cmd_spec.cmd:
            lines.append("")
            lines.append("AVAILABLE SUBCOMMANDS:")
            for sub_name, sub_spec in sorted(cmd_spec.cmd.items()):
                tier_tag = f"[{sub_spec.tier}]"
                sub_args_str = " ".join([cls.format_arg_placeholder(a) for a in sub_spec.args.values()])
                disp_name = f"{sub_name} {sub_args_str}" if sub_args_str else sub_name
                lines.append(f"  {disp_name:<25} {tier_tag:<10} {sub_spec.description}")
            lines.append("")
            lines.append(f"Run 'python yscb.py {module_name} {cmd_name} <subcommand> --help' for subcommand details.")

        # 渲染位置參數說明 (ARGUMENTS)
        if cmd_spec.args:
            lines.append("")
            lines.append("ARGUMENTS:")
            for arg_name, arg_spec in cmd_spec.args.items():
                ph = cls.format_arg_placeholder(arg_spec)
                req_tag = "[required]" if arg_spec.required else "[optional]"
                desc_parts = []
                if arg_spec.description:
                    desc_parts.append(arg_spec.description)
                if arg_spec.choice:
                    desc_parts.append(f"(choices: {', '.join(arg_spec.choice)})")
                desc_parts.append(req_tag)
                desc_text = " ".join(desc_parts)
                lines.append(f"  {ph:<30} {desc_text}")

        # 分組渲染正交選項
        if cmd_spec.groups:
            lines.append("")
            lines.append("OPTIONS:")
            for group_name, opt_names in sorted(cmd_spec.groups.items()):
                group_header = f"  -- [Group: {group_name}]" if group_name != "default" else "  -- [Standard Options]"
                lines.append(group_header)
                for opt_name in opt_names:
                    opt_spec = cmd_spec.canonical_options.get(opt_name)
                    if not opt_spec:
                        continue
                    val_suffix = ""
                    if opt_spec.takes_value:
                        first_arg = next(iter(opt_spec.args.values()))
                        val_suffix = f" {cls.format_arg_placeholder(first_arg)}"
                    aliases_part = f" (alias: {', '.join(['-' + a if len(a) == 1 else '--' + a for a in opt_spec.alias])})" if opt_spec.alias else ""
                    opt_flag = f"--{opt_name}{val_suffix}"
                    lines.append(f"    {opt_flag:<30} {opt_spec.description}{aliases_part}")
        elif cmd_spec.canonical_options:
            lines.append("")
            lines.append("OPTIONS:")
            for opt_name, opt_spec in sorted(cmd_spec.canonical_options.items()):
                val_suffix = ""
                if opt_spec.takes_value:
                    first_arg = next(iter(opt_spec.args.values()))
                    val_suffix = f" {cls.format_arg_placeholder(first_arg)}"
                aliases_part = f" (alias: {', '.join(['-' + a if len(a) == 1 else '--' + a for a in opt_spec.alias])})" if opt_spec.alias else ""
                opt_flag = f"--{opt_name}{val_suffix}"
                lines.append(f"    {opt_flag:<30} {opt_spec.description}{aliases_part}")

        # 渲染 Usage Pros & Cons
        if cmd_spec.usage_pros:
            lines.append("")
            lines.append("RECOMMENDED USAGE (Pros):")
            for pro in cmd_spec.usage_pros:
                lines.append(f"  ✅ {pro}")

        if cmd_spec.usage_cons:
            lines.append("")
            lines.append("RESTRICTIONS & GATES (Cons):")
            for con in cmd_spec.usage_cons:
                lines.append(f"  🚨 {con}")

        lines.append("=" * 80)
        return "\n".join(lines)
