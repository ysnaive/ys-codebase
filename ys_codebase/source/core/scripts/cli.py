"""
Core Module CLI Entrypoint - Precise Command Handlers Contract.
No legacy process(args) fallback.
"""
import builtins
import os
import sys
from typing import Any, List, Optional

from core.commands.bags import CmdBags, CmdOption
from core.guard import guard_dispatch
from core.installer import Installer
from core import config as core_config
from core import uri as core_uri


def _normalize_bags(cmd_bags: Any, default_cmd: str = "") -> CmdBags:
    """Normalize input into CmdBags for compatibility with direct list invocations."""
    if isinstance(cmd_bags, CmdBags):
        return cmd_bags
    if isinstance(cmd_bags, (builtins.list, tuple)):
        args = []
        options = {}
        for a in cmd_bags:
            if a.startswith("--"):
                if "=" in a:
                    k, v = a[2:].split("=", 1)
                    options[k] = CmdOption(name=k, params=v)
                else:
                    k = a[2:]
                    options[k] = CmdOption(name=k, params=True)
            elif a.startswith("-") and len(a) > 1:
                k = a[1:]
                options[k] = CmdOption(name=k, params=True)
            else:
                args.append(a)
        raw_cmd_str = " ".join([str(x) for x in cmd_bags])
        return CmdBags(raw_cmd=raw_cmd_str, command=default_cmd, args=args, options=options)
    return CmdBags(raw_cmd="", command=default_cmd)


def config_list(cmd_bags: CmdBags) -> int:
    """List module configurations."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    json_output = cmd_bags.has_option("json")
    mod_filter = cmd_bags.get_option_value("mod")

    mods = [mod_filter] if mod_filter else core_config.list_modules()
    if not mods:
        print("[core:config] No configuration found for any module.")
        return 0

    summary = {}
    for m in mods:
        summary[m] = {
            "config": core_config.get_all(m),
            "has_project_config": os.path.isfile(core_config.get_config_path(m, local=False)),
            "has_local_config": os.path.isfile(core_config.get_config_path(m, local=True)),
        }

    if json_output:
        import json
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    print("\nYS-Codebase Module Configurations:")
    print("=" * 80)
    for m, info in summary.items():
        local_flag_txt = "[LOCAL OVERLAY]" if info["has_local_config"] else "[PROJECT]"
        print(f"[*] Module: {m} {local_flag_txt}")
        print(f"    |-- Project: {core_config.get_config_path(m, local=False)}")
        if info["has_local_config"]:
            print(f"    |-- Local  : {core_config.get_config_path(m, local=True)}")
        cfg_items = info["config"]
        if isinstance(cfg_items, dict) and cfg_items:
            for k, v in cfg_items.items():
                print(f"    • {k}: {v}")
        else:
            print("    • (empty)")
    print("=" * 80)
    return 0


def config_get(cmd_bags: CmdBags) -> int:
    """Get effective configuration value."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if not cmd_bags.args:
        print("[core:config] Error: Module name required. (e.g. 'config get agents-workflow paths.plans')")
        return 1
    mod_name = cmd_bags.args[0]
    key = cmd_bags.args[1] if len(cmd_bags.args) > 1 else None
    json_output = cmd_bags.has_option("json")

    val = core_config.get(mod_name, key)
    if json_output or isinstance(val, (dict, builtins.list)):
        import json
        print(json.dumps(val, indent=2, ensure_ascii=False))
    else:
        print(val)
    return 0


def config_set(cmd_bags: CmdBags) -> int:
    """Set configuration value."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if len(cmd_bags.args) < 3:
        print("[core:config] Error: Module name, key, and value required. (e.g. 'config set core project_root ./ [--local]')")
        return 1

    mod_name, key, raw_val = cmd_bags.args[0], cmd_bags.args[1], cmd_bags.args[2]
    local_flag = cmd_bags.has_option("local")

    val = raw_val
    if raw_val.lower() == "true":
        val = True
    elif raw_val.lower() == "false":
        val = False
    elif raw_val.lower() in ("none", "null"):
        val = None
    elif raw_val.isdigit():
        val = int(raw_val)
    elif raw_val.startswith(("[", "{")) and raw_val.endswith(("]", "}")):
        import json
        try:
            val = json.loads(raw_val)
        except Exception:
            val = raw_val

    try:
        core_config.set(mod_name, key, val, local=local_flag)
        tier_name = "config.local.json" if local_flag else "config.project.json"
        print(f"[core:config] Successfully set '{key}' = {val} in '{tier_name}' for module '{mod_name}'.")
        return 0
    except Exception as e:
        print(f"[core:config] Error setting config: {e}")
        return 1


def config_reload(cmd_bags: CmdBags) -> int:
    """Reload cached configuration."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    mod_name = cmd_bags.args[0] if cmd_bags.args else None
    core_config.reload(mod_name)
    print(f"[core:config] Reloaded configuration cache for {'all modules' if not mod_name else mod_name}.")
    return 0


def config(cmd_bags: CmdBags) -> int:
    """YS-Codebase Module Configuration Manager (Group Dispatcher)."""
    cmd_bags = _normalize_bags(cmd_bags)
    args = cmd_bags.args

    if not args:
        print("YS-Codebase Module Configuration Manager")
        print("Usage:")
        print("  config list [--mod=<module>] [--json]        List module configurations")
        print("  config get <module> [key] [--json]           Get effective configuration value")
        print("  config set <module> <key> <val> [--local]    Set configuration value")
        print("  config reload [module]                       Reload cached configuration")
        return 0

    sub_cmd = args[0]
    sub_bags = CmdBags(raw_cmd=cmd_bags.raw_cmd, command=sub_cmd, args=args[1:], options=cmd_bags.options)
    if sub_cmd == "list":
        return config_list(sub_bags)
    elif sub_cmd == "get":
        return config_get(sub_bags)
    elif sub_cmd == "set":
        return config_set(sub_bags)
    elif sub_cmd == "reload":
        return config_reload(sub_bags)
    else:
        print(f"[core:config] Unknown sub-command '{sub_cmd}'. Run 'python yscb.py config --help' for help.")
        return 1


def uri_list(cmd_bags: CmdBags) -> int:
    """List all registered semantic URI schemes."""
    guard_dispatch("core")
    schemes = core_uri.list_registered_schemes_summary()
    print("\nYS-Codebase Registered URI Schemes Catalog:")
    print("=" * 110)
    print(f"{'SCHEME':<23} {'TYPE':<8} {'PROVIDER':<12} {'RAW TARGET / VALUE':<28} {'RESOLVED PATH'}")
    print("-" * 110)
    for s in schemes:
        token_str = f"{s['token']}://"
        stype = s.get("type", "const")
        provider = s.get("provider", "core")
        raw_val = s.get("value", "")
        res_path = s.get("resolved_path", "")
        print(f"{token_str:<23} {stype:<8} {provider:<12} {raw_val:<28} {res_path}")
    print("=" * 110)
    return 0


def uri_resolve(cmd_bags: CmdBags) -> int:
    """Resolve semantic URI to absolute physical path."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if not cmd_bags.args:
        print("[core:uri] Error: URI string required.")
        return 1
    try:
        res = core_uri.resolve(cmd_bags.args[0], interactive=True)
        print(res)
        return 0
    except Exception as e:
        print(f"[core:uri] Error: {e}")
        return 1


def uri_to_uri(cmd_bags: CmdBags) -> int:
    """Convert absolute path to semantic URI."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if not cmd_bags.args:
        print("[core:uri] Error: Absolute path required.")
        return 1
    try:
        res = core_uri.to_uri(cmd_bags.args[0])
        print(res)
        return 0
    except Exception as e:
        print(f"[core:uri] Error: {e}")
        return 1


def uri_check(cmd_bags: CmdBags) -> int:
    """Health check all registered URI schemes."""
    guard_dispatch("core")
    schemes = core_uri.list_registered_schemes_summary()
    print("\nYS-Codebase URI Health Check:")
    print("-" * 80)
    healthy = True
    for s in schemes:
        status = "OK" if not s["resolved_path"].startswith("!undefined") else "UNDEFINED"
        if status == "UNDEFINED":
            healthy = False
        print(f"[*] {s['token'] + '://':<18} -> {s['resolved_path']} [{status}]")
    print("-" * 80)
    print(f"Overall URI Status: {'HEALTHY' if healthy else 'WARNING (!undefined schemes present)'}")
    return 0


def uri(cmd_bags: CmdBags) -> int:
    """YS-Codebase Semantic URI VFS CLI (Group Dispatcher)."""
    cmd_bags = _normalize_bags(cmd_bags)
    args = cmd_bags.args

    if not args:
        print("YS-Codebase Semantic URI VFS CLI")
        print("Usage:")
        print("  uri list / uri --list             List all registered semantic URI schemes")
        print("  uri resolve <path_or_uri>         Resolve semantic URI to absolute path")
        print("  uri to-uri <abs_path>             Convert absolute path to semantic URI")
        print("  uri check                         Health check all registered URI schemes")
        return 0

    sub_cmd = args[0]
    sub_bags = CmdBags(raw_cmd=cmd_bags.raw_cmd, command=sub_cmd, args=args[1:], options=cmd_bags.options)
    if sub_cmd in ("list", "--list", "-l"):
        return uri_list(sub_bags)
    elif sub_cmd == "resolve":
        return uri_resolve(sub_bags)
    elif sub_cmd == "to-uri":
        return uri_to_uri(sub_bags)
    elif sub_cmd == "check":
        return uri_check(sub_bags)
    else:
        print(f"[core:uri] Unknown sub-command '{sub_cmd}'. Run 'python yscb.py uri --help' for help.")
        return 1



def install(cmd_bags: CmdBags) -> int:
    """Install a module from provider or local build package (@build)."""
    guard_dispatch("core")
    if not cmd_bags.args:
        print("[core:install] Error: Module name is required.")
        return 1

    module_spec = cmd_bags.args[0]
    version = cmd_bags.get_option_value("version")
    if "@" in module_spec:
        module_name, version = module_spec.split("@", 1)
    else:
        module_name = module_spec

    provider = cmd_bags.get_option_value("provider")
    force_flag = cmd_bags.has_option("force")

    installer = Installer()
    return installer.cmd_install(module_name, version=version, provider=provider, force=force_flag)


def update(cmd_bags: CmdBags) -> int:
    """Update installed module(s) to latest version."""
    guard_dispatch("core")
    mod_name = cmd_bags.args[0] if cmd_bags.args else None
    provider = cmd_bags.get_option_value("provider")
    installer = Installer()
    return installer.cmd_update(mod_name, provider=provider)


def remove(cmd_bags: CmdBags) -> int:
    """Remove an installed module from environment."""
    guard_dispatch("core")
    mod_name = cmd_bags.args[0] if cmd_bags.args else ""
    clean = cmd_bags.has_option("clean")
    purge = cmd_bags.has_option("purge")
    force_flag = cmd_bags.has_option("force")
    installer = Installer()
    return installer.cmd_remove(mod_name, clean=clean, purge=purge, force=force_flag)


def list(cmd_bags: CmdBags) -> int:
    """List all installed modules, versions and providers."""
    guard_dispatch("core")
    remote = cmd_bags.has_option("remote")
    provider = cmd_bags.get_option_value("provider")
    installer = Installer()
    ret = installer.cmd_list(remote=remote, provider=provider)
    try:
        from core.update_checker import UpdateChecker
        checker = UpdateChecker()
        checker.check_updates(force=False)
        checker.print_tips_if_available()
    except Exception:
        pass
    return ret


def status(cmd_bags: CmdBags) -> int:
    """Health check and runtime diagnostic report."""
    guard_dispatch("core")
    installer = Installer()
    ret = installer.cmd_status()
    try:
        from core.update_checker import UpdateChecker
        checker = UpdateChecker()
        checker.check_updates(force=False)
        checker.print_tips_if_available()
    except Exception:
        pass
    return ret


def reload(cmd_bags: CmdBags) -> int:
    """Reconcile and refresh runtime environment."""
    guard_dispatch("core")
    installer = Installer()
    return installer.cmd_reload()


def rollback(cmd_bags: CmdBags) -> int:
    """Revert environment to the previous snapshot state."""
    guard_dispatch("core")
    target = cmd_bags.args[0] if cmd_bags.args else None
    installer = Installer()
    return installer.cmd_rollback(target)


def restore(cmd_bags: CmdBags) -> int:
    """Restore missing installed modules from mirror or provider."""
    guard_dispatch("core")
    force_flag = cmd_bags.has_option("force")
    provider = cmd_bags.get_option_value("provider")
    installer = Installer()
    return installer.cmd_restore(force=force_flag, provider=provider)


def bootstrap(cmd_bags: CmdBags) -> int:
    """Bootstrap alias for restore."""
    return restore(cmd_bags)


def event_list(cmd_bags: CmdBags) -> int:
    """List all registered ecosystem events."""
    guard_dispatch("core")
    from core import events
    contributed = events.get_contributed_events()
    print("=" * 70)
    print("  YS-Codebase - Ecosystem Event Registry")
    print("=" * 70)
    if not contributed:
        print("  (No contributed events found)")
    else:
        for mod_name, ev_list in sorted(contributed.items()):
            print(f"\n[{mod_name}]")
            for ev in ev_list:
                ename = ev.get("name", "")
                edesc = ev.get("description", "")
                print(f"  {ename:<25} {edesc}")
    print("\n" + "=" * 70)
    return 0


def event(cmd_bags: CmdBags) -> int:
    """Ecosystem Event Registry and Inspector (Group Dispatcher)."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    sub_cmd = cmd_bags.args[0] if cmd_bags.args else "list"
    if sub_cmd == "list":
        return event_list(cmd_bags)
    else:
        print(f"[core:event] Unknown subcommand '{sub_cmd}'. Available: list")
        return 1


# Legacy test compatibility aliases
def cmd_config(cmd_bags: Any) -> int:
    return config(cmd_bags)


def cmd_uri(cmd_bags: Any) -> int:
    return uri(cmd_bags)


def cmd_install(cmd_bags: Any) -> int:
    return install(cmd_bags)


def cmd_update(cmd_bags: Any) -> int:
    return update(cmd_bags)


def cmd_remove(cmd_bags: Any) -> int:
    return remove(cmd_bags)


def cmd_list(cmd_bags: Any) -> int:
    return list(cmd_bags)


def cmd_status(cmd_bags: Any) -> int:
    return status(cmd_bags)


def cmd_reload(cmd_bags: Any) -> int:
    return reload(cmd_bags)


def cmd_rollback(cmd_bags: Any) -> int:
    return rollback(cmd_bags)


def cmd_restore(cmd_bags: Any) -> int:
    return restore(cmd_bags)


def cmd_event(cmd_bags: Any) -> int:
    return event(cmd_bags)
