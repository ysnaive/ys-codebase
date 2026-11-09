"""
Core Module CLI Entrypoint - Precise Command Handlers Contract.
No legacy process(args) fallback.
"""
import builtins
import json
import os
import re
from typing import Any, List

from core.commands.bags import CmdBags, CmdOption
from core.guard import guard_dispatch
from core.installer import Installer
from core.log import log, log_error, log_info
from core import config as core_config
from core import uri as core_uri


def _render_subcommand_group_help(cmd_name: str) -> int:
    """Render help message for a core subcommand group (config, uri, event, contributes, gitignore, file-space)."""
    from core.commands.help import HelpRenderer
    from core.commands.dispatcher import _load_registry, _get_yscb_root
    _, yscb_abs = _get_yscb_root()
    reg = _load_registry(yscb_abs)
    spec = reg.get_command("core", cmd_name)
    if spec is None:
        log(f"YS-Codebase Core Command Group: {cmd_name}\n(Run 'python yscb.py {cmd_name} --help' for details)")
        return 0
    log(HelpRenderer.render_cmd_help("core", cmd_name, spec))
    return 0


def _parse_cli_scalar_or_json(raw_val: str) -> Any:
    """Parse CLI raw string value into boolean, null, integer, float, JSON container, or plain string."""
    low = raw_val.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("none", "null"):
        return None
    if re.match(r"^[+-]?\d+$", raw_val):
        return int(raw_val)
    if re.match(r"^[+-]?\d+\.\d+$", raw_val):
        return float(raw_val)
    if raw_val.startswith(("[", "{")) and raw_val.endswith(("]", "}")):
        try:
            return json.loads(raw_val)
        except Exception:
            return raw_val
    return raw_val


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
    local_only = cmd_bags.has_option("local")
    mod_filter = cmd_bags.get_option_value("mod")

    mods = [mod_filter] if mod_filter else core_config.list_modules()
    if not mods:
        if json_output:
            log(json.dumps({}, indent=2, ensure_ascii=False))
            return 0
        log_info("[core:config] No configuration found for any module.")
        return 0

    summary = {}
    for m in mods:
        has_local = os.path.isfile(core_config.get_config_path(m, local=True))
        if local_only and not has_local:
            continue
        cfg_data = core_config.get_raw(m, local=True) if local_only else core_config.get_all(m)
        summary[m] = {
            "config": cfg_data,
            "has_project_config": os.path.isfile(core_config.get_config_path(m, local=False)),
            "has_local_config": has_local,
        }

    if json_output:
        log(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    log("\nYS-Codebase Module Configurations:")
    log("=" * 80)
    for m, info in summary.items():
        local_flag_txt = "[LOCAL OVERLAY]" if info["has_local_config"] else "[PROJECT]"
        log(f"[*] Module: {m} {local_flag_txt}")
        log(f"    |-- Project: {core_config.get_config_path(m, local=False)}")
        if info["has_local_config"]:
            log(f"    |-- Local  : {core_config.get_config_path(m, local=True)}")
        cfg_items = info["config"]
        if isinstance(cfg_items, dict) and cfg_items:
            for k, v in cfg_items.items():
                log(f"    • {k}: {v}")
        else:
            log("    • (empty)")
    log("=" * 80)
    return 0


def config_inspect(cmd_bags: CmdBags) -> int:
    """Inspect effective value, source hierarchy and override status of a key."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if len(cmd_bags.args) < 2:
        log_error("[core:config] Error: Module name and key required. (e.g. 'config inspect core project_root [--json]')")
        return 1

    mod_name, key = cmd_bags.args[0], cmd_bags.args[1]
    json_output = cmd_bags.has_option("json")

    res = core_config.inspect(mod_name, key)
    if json_output:
        log(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    log(f"\nConfiguration Inspection: '{mod_name}' -> '{key}'")
    log("-" * 60)
    log(f"  Effective Value : {res.get('effective')}")
    log(f"  Source Hierarchy: {res.get('source')}")
    log(f"  Project Value   : {res.get('project_value')}")
    log(f"  Local Value     : {res.get('local_value')}")
    log(f"  Is Overridden   : {res.get('is_overridden')}")
    log("-" * 60)
    return 0


def config_unset(cmd_bags: CmdBags) -> int:
    """Delete a configuration key from project or local overlay."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if len(cmd_bags.args) < 2:
        log_error("[core:config] Error: Module name and key required. (e.g. 'config unset core project_root [--local]')")
        return 1

    mod_name, key = cmd_bags.args[0], cmd_bags.args[1]
    local_flag = cmd_bags.has_option("local")

    try:
        deleted = core_config.delete(mod_name, key, local=local_flag)
        tier_name = "config.local.json" if local_flag else "config.project.json"
        if deleted:
            log_info(f"[core:config] Successfully unset '{key}' from '{tier_name}' for module '{mod_name}'.")
            return 0
        else:
            log_error(f"[core:config] Key '{key}' not found in '{tier_name}' for module '{mod_name}'.")
            return 1
    except Exception as e:
        log_error(f"[core:config] Error unsetting config: {e}")
        return 1


def config_get(cmd_bags: CmdBags) -> int:
    """Get effective configuration value."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if not cmd_bags.args:
        log_error("[core:config] Error: Module name required. (e.g. 'config get agents-workflow paths.plans')")
        return 1
    mod_name = cmd_bags.args[0]
    key = cmd_bags.args[1] if len(cmd_bags.args) > 1 else None
    json_output = cmd_bags.has_option("json")

    val = core_config.get(mod_name, key)
    if json_output or isinstance(val, (dict, builtins.list)):
        log(json.dumps(val, indent=2, ensure_ascii=False))
    else:
        log(val)
    return 0


def config_set(cmd_bags: CmdBags) -> int:
    """Set configuration value."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if len(cmd_bags.args) < 3:
        log_error("[core:config] Error: Module name, key, and value required. (e.g. 'config set core project_root ./ [--local]')")
        return 1

    mod_name, key, raw_val = cmd_bags.args[0], cmd_bags.args[1], cmd_bags.args[2]
    local_flag = cmd_bags.has_option("local")
    val = _parse_cli_scalar_or_json(raw_val)

    try:
        core_config.set(mod_name, key, val, local=local_flag)
        tier_name = "config.local.json" if local_flag else "config.project.json"
        log_info(f"[core:config] Successfully set '{key}' = {val} in '{tier_name}' for module '{mod_name}'.")
        return 0
    except Exception as e:
        log_error(f"[core:config] Error setting config: {e}")
        return 1


def config_reload(cmd_bags: CmdBags) -> int:
    """Reload cached configuration."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    mod_name = cmd_bags.args[0] if cmd_bags.args else None
    core_config.reload(mod_name)
    log_info(f"[core:config] Reloaded configuration cache for {'all modules' if not mod_name else mod_name}.")
    return 0


def config(cmd_bags: CmdBags) -> int:
    """YS-Codebase Module Configuration Manager (Group Dispatcher)."""
    cmd_bags = _normalize_bags(cmd_bags)
    args = cmd_bags.args

    if not args:
        return _render_subcommand_group_help("config")

    sub_cmd = args[0]
    sub_bags = CmdBags(raw_cmd=cmd_bags.raw_cmd, command=sub_cmd, args=args[1:], options=cmd_bags.options)
    if sub_cmd == "list":
        return config_list(sub_bags)
    elif sub_cmd == "get":
        return config_get(sub_bags)
    elif sub_cmd == "set":
        return config_set(sub_bags)
    elif sub_cmd == "inspect":
        return config_inspect(sub_bags)
    elif sub_cmd == "unset":
        return config_unset(sub_bags)
    elif sub_cmd == "reload":
        return config_reload(sub_bags)
    else:
        log_error(f"[core:config] Unknown sub-command '{sub_cmd}'. Run 'python yscb.py config --help' for help.")
        return 1


def uri_list(cmd_bags: CmdBags) -> int:
    """List all registered semantic URI schemes."""
    guard_dispatch("core")
    schemes = core_uri.list_registered_schemes_summary()
    log("\nYS-Codebase Registered URI Schemes Catalog:")
    log("=" * 110)
    log(f"{'SCHEME':<23} {'TYPE':<8} {'PROVIDER':<12} {'RAW TARGET / VALUE':<28} {'RESOLVED PATH'}")
    log("-" * 110)
    for s in schemes:
        token_str = f"{s['token']}://"
        stype = s.get("type", "const")
        provider = s.get("provider", "core")
        raw_val = s.get("value", "")
        res_path = s.get("resolved_path", "")
        log(f"{token_str:<23} {stype:<8} {provider:<12} {raw_val:<28} {res_path}")
    log("=" * 110)
    return 0


def uri_resolve(cmd_bags: CmdBags) -> int:
    """Resolve semantic URI to absolute physical path."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if not cmd_bags.args:
        log_error("[core:uri] Error: URI string required.")
        return 1
    try:
        res = core_uri.resolve(cmd_bags.args[0], interactive=True)
        log(res)
        return 0
    except Exception as e:
        log_error(f"[core:uri] Error: {e}")
        return 1


def uri_to_uri(cmd_bags: CmdBags) -> int:
    """Convert absolute path to semantic URI."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if not cmd_bags.args:
        log_error("[core:uri] Error: Absolute path required.")
        return 1
    try:
        res = core_uri.to_uri(cmd_bags.args[0])
        log(res)
        return 0
    except Exception as e:
        log_error(f"[core:uri] Error: {e}")
        return 1


def uri_check(cmd_bags: CmdBags) -> int:
    """Health check all registered URI schemes."""
    guard_dispatch("core")
    schemes = core_uri.list_registered_schemes_summary()
    log("\nYS-Codebase URI Health Check:")
    log("-" * 80)
    healthy = True
    quick_fixes: List[str] = []
    for s in schemes:
        status = "OK" if not s["resolved_path"].startswith("!undefined") else "UNDEFINED"
        if status == "UNDEFINED":
            healthy = False
            hint_fn = getattr(core_uri, "format_undefined_uri_hint", None)
            if callable(hint_fn):
                hint_cmd = hint_fn(
                    s.get("token", ""),
                    s.get("provider", "core"),
                    s.get("value", "unknown"),
                )
                if hint_cmd not in quick_fixes:
                    quick_fixes.append(hint_cmd)
        log(f"[*] {s['token'] + '://':<18} -> {s['resolved_path']} [{status}]")
    log("-" * 80)
    log(f"Overall URI Status: {'HEALTHY' if healthy else 'WARNING (!undefined schemes present)'}")
    if quick_fixes:
        log("\n[Quick Fix] Run the following command(s) to initialize undefined schemes:")
        for qf in quick_fixes:
            log(f"  + {qf}")
    return 0


def uri(cmd_bags: CmdBags) -> int:
    """YS-Codebase Semantic URI VFS CLI (Group Dispatcher)."""
    cmd_bags = _normalize_bags(cmd_bags)
    args = cmd_bags.args

    if not args:
        return _render_subcommand_group_help("uri")

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
        log_error(f"[core:uri] Unknown sub-command '{sub_cmd}'. Run 'python yscb.py uri --help' for help.")
        return 1


def install(cmd_bags: CmdBags) -> int:
    """Install one or more modules from provider or local build package (@build)."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags, "install")
    if not cmd_bags.args:
        log_error("[core:install] Error: Module name is required.")
        return 1

    version = cmd_bags.get_option_value("version")
    provider = cmd_bags.get_option_value("provider")
    force_flag = cmd_bags.has_option("force")
    ignore_sha256 = cmd_bags.has_option("ignore-sha256")

    specs = cmd_bags.args
    if len(specs) == 1:
        module_spec = specs[0]
        if "@" in module_spec:
            module_target, version = module_spec.split("@", 1)
        else:
            module_target = module_spec
    else:
        module_target = [s for s in specs]

    installer = Installer()
    return installer.cmd_install(
        module_target,
        version=version,
        provider=provider,
        force=force_flag,
        ignore_sha256=ignore_sha256,
    )


def update(cmd_bags: CmdBags) -> int:
    """Update installed module(s) to latest version."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags, "update")
    if not cmd_bags.args:
        mod_target = None
    elif len(cmd_bags.args) == 1:
        mod_target = cmd_bags.args[0]
    else:
        mod_target = [s for s in cmd_bags.args]
    provider = cmd_bags.get_option_value("provider")
    ignore_sha256 = cmd_bags.has_option("ignore-sha256")
    installer = Installer()
    return installer.cmd_update(mod_target, provider=provider, ignore_sha256=ignore_sha256)


def remove(cmd_bags: CmdBags) -> int:
    """Remove one or more installed modules from environment."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags, "remove")
    if not cmd_bags.args:
        mod_target = ""
    elif len(cmd_bags.args) == 1:
        mod_target = cmd_bags.args[0]
    else:
        mod_target = [s for s in cmd_bags.args]
    clean = cmd_bags.has_option("clean")
    purge = cmd_bags.has_option("purge")
    force_flag = cmd_bags.has_option("force")
    installer = Installer()
    return installer.cmd_remove(mod_target, clean=clean, purge=purge, force=force_flag)


def list(cmd_bags: CmdBags) -> int:
    """List all installed modules, versions and providers."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags, "list")
    remote = cmd_bags.has_option("remote")
    provider = cmd_bags.get_option_value("provider")
    installer = Installer()
    return installer.cmd_list(remote=remote, provider=provider)


def status(cmd_bags: CmdBags) -> int:
    """Health check and runtime diagnostic report."""
    guard_dispatch("core")
    installer = Installer()
    return installer.cmd_status()


def reload(cmd_bags: CmdBags) -> int:
    """Reconcile and refresh runtime environment."""
    guard_dispatch("core")
    installer = Installer()
    return installer.cmd_reload()


def rollback(cmd_bags: CmdBags) -> int:
    """Revert environment to the previous snapshot state."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags, "rollback")
    target = cmd_bags.args[0] if cmd_bags.args else None
    installer = Installer()
    return installer.cmd_rollback(target)


def restore(cmd_bags: CmdBags) -> int:
    """Restore missing installed modules from mirror or provider."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags, "restore")
    force_flag = cmd_bags.has_option("force")
    provider = cmd_bags.get_option_value("provider")
    ignore_sha256 = cmd_bags.has_option("ignore-sha256")
    installer = Installer()
    return installer.cmd_restore(force=force_flag, provider=provider, ignore_sha256=ignore_sha256)


def event_list(cmd_bags: CmdBags) -> int:
    """List all registered ecosystem events."""
    guard_dispatch("core")
    from core import events
    contributed = events.get_contributed_events()
    log("=" * 70)
    log("  YS-Codebase - Ecosystem Event Registry")
    log("=" * 70)
    if not contributed:
        log("  (No contributed events found)")
    else:
        for mod_name, ev_list in sorted(contributed.items()):
            log(f"\n[{mod_name}]")
            for ev in ev_list:
                ename = ev.get("name", "")
                edesc = ev.get("description", "")
                log(f"  {ename:<25} {edesc}")
    log("\n" + "=" * 70)
    return 0


def event(cmd_bags: CmdBags) -> int:
    """Ecosystem Event Registry and Inspector (Group Dispatcher)."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if not cmd_bags.args:
        return _render_subcommand_group_help("event")
    sub_cmd = cmd_bags.args[0]
    sub_bags = CmdBags(
        raw_cmd=cmd_bags.raw_cmd,
        command=sub_cmd,
        args=cmd_bags.args[1:],
        options=cmd_bags.options,
    )
    if sub_cmd == "list":
        return event_list(sub_bags)
    else:
        log_error(f"[core:event] Unknown subcommand '{sub_cmd}'. Available: list")
        return 1


def contributes_list(cmd_bags: CmdBags) -> int:
    """List registered contribute points."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    from core.commands import contributes_cmd
    mod_filter = cmd_bags.get_option_value("module") or cmd_bags.get_option_value("m")
    if not mod_filter and cmd_bags.args:
        mod_filter = cmd_bags.args[0]
    return contributes_cmd.list_contributes(mod_filter)


def contributes_check(cmd_bags: CmdBags) -> int:
    """Check contributes against schema."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    from core.commands import contributes_cmd
    target = cmd_bags.args[0] if cmd_bags.args else None
    is_format = cmd_bags.has_option("format")
    return contributes_cmd.check_contributes(target, is_format_check=is_format)


def contributes(cmd_bags: CmdBags) -> int:
    """Contributes Schema Validation and Inspection Manager (Group Dispatcher)."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    args = cmd_bags.args
    if not args:
        return _render_subcommand_group_help("contributes")
    sub_cmd = args[0]
    sub_args = args[1:]
    sub_bags = CmdBags(
        raw_cmd=cmd_bags.raw_cmd,
        command=sub_cmd,
        args=sub_args,
        options=cmd_bags.options,
    )
    if sub_cmd == "list":
        return contributes_list(sub_bags)
    elif sub_cmd == "check":
        return contributes_check(sub_bags)
    else:
        log_error(f"[core:contributes] Unknown subcommand '{sub_cmd}'. Available: list, check", stream="stderr")
        return 1


def gitignore_status(cmd_bags: CmdBags) -> int:
    """Inspect project://.gitignore managed block status and grouped module rules."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    from core import gitignore as gi_mod
    info = gi_mod.status()
    if cmd_bags.has_option("json"):
        log(json.dumps(info, indent=2, ensure_ascii=False))
        return 0
    log("=" * 70)
    log("  YS-Codebase - Unified Gitignore Status")
    log("=" * 70)
    log(f"  Target File    : {info.get('target_path')}")
    log(f"  Exists         : {info.get('exists')}")
    log(f"  Managed Block  : {info.get('has_managed_block')}")
    log(f"  In Sync        : {info.get('in_sync')}")
    log(f"  Total Rules    : {info.get('total_patterns')}")
    groups = info.get("groups", {})
    if groups:
        log("\n  Module Groups:")
        for mod, pats in groups.items():
            log(f"    # [{mod}] ({len(pats)} rule(s))")
    log("=" * 70)
    return 0


def gitignore_sync(cmd_bags: CmdBags) -> int:
    """Synthesize and synchronize all module ignore rules into project://.gitignore."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    from core import gitignore as gi_mod
    res = gi_mod.sync()
    if cmd_bags.has_option("json"):
        log(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if not res.get("error") else 1
    if res.get("error"):
        log_error(f"[core:gitignore] Error: {res['error']}", stream="stderr")
        return 1
    state_label = "created" if res.get("created") else ("updated" if res.get("updated") else "already up-to-date")
    log_info(
        f"[core:gitignore] '{res.get('target_path')}' is {state_label} "
        f"({len(res.get('patterns', []))} rule(s) across {len(res.get('groups', {}))} module group(s))."
    )
    return 0


def gitignore(cmd_bags: CmdBags) -> int:
    """Unified project://.gitignore managed block inspector and synchronizer (Group Dispatcher)."""
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    args = cmd_bags.args
    if not args:
        return _render_subcommand_group_help("gitignore")
    sub_cmd = args[0]
    sub_args = args[1:]
    sub_bags = CmdBags(
        raw_cmd=cmd_bags.raw_cmd,
        command=sub_cmd,
        args=sub_args,
        options=cmd_bags.options,
    )
    if sub_cmd == "status":
        return gitignore_status(sub_bags)
    elif sub_cmd == "sync":
        return gitignore_sync(sub_bags)
    else:
        log_error(f"[core:gitignore] Unknown subcommand '{sub_cmd}'. Available: status, sync", stream="stderr")
        return 1


def _emit_space_error(exc: Exception, json_output: bool) -> int:
    """Emit structured or human-readable error message for core.space CLI commands and return exit code 1."""
    if json_output:
        log(
            json.dumps(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        log_error(f"[core:file-space] Error: {exc}", stream="stderr")
    return 1


def _handle_space_spaces(cmd_bags: CmdBags) -> int:
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    json_output = cmd_bags.has_option("json")
    owner_filter = cmd_bags.get_option_value("owner") or cmd_bags.get_option_value("o")
    query = cmd_bags.args[0] if cmd_bags.args else None

    from core.space import SpaceError, get_default_registry

    try:
        reg = get_default_registry()
        if query:
            spaces = reg.resolve_spaces(query)
        else:
            spaces = reg.list_spaces(owner=owner_filter)
        if owner_filter and query:
            spaces = [s for s in spaces if s.owner == owner_filter]
    except SpaceError as exc:
        return _emit_space_error(exc, json_output)

    payload = {
        "status": "ok",
        "query": query,
        "count": len(spaces),
        "spaces": [s.to_dict(reg.project_root) for s in spaces],
    }
    if json_output:
        log(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    log("=" * 80)
    log(f"  YS-Codebase Core File-Space Registry ({len(spaces)} space(s))")
    log("=" * 80)
    if not spaces:
        log("  (No spaces registered)")
    for s_dict in payload["spaces"]:
        log(f"\n[*] {s_dict['qualified_name']} (short: {s_dict['short_name']}, owner: {s_dict['owner']})")
        if s_dict["description"]:
            log(f"    Description : {s_dict['description']}")
        log(f"    Hash Policy : {s_dict['hash_policy']} (threshold: {s_dict['large_file_threshold_mb']} MB)")
        for ent in s_dict["resolved_entries"]:
            state_lbl = "OK" if ent["exists"] else "MISSING (exists: false)"
            log(f"    Entry       : {ent['entry']} -> {ent['resolved_path']} [{state_lbl}]")
        if s_dict.get("compose"):
            log(f"    Compose     : {', '.join(s_dict['compose'])}")
        if s_dict.get("unresolved_compose"):
            log(f"    UnresolvedC : {', '.join(s_dict['unresolved_compose'])}")
        if s_dict["presets"]:
            log(f"    Presets     : {', '.join(s_dict['presets'])}")
        if s_dict["unresolved_presets"]:
            log(f"    Unresolved  : {', '.join(s_dict['unresolved_presets'])}")
        log(f"    Include     : {', '.join(s_dict['include'])}")
        if s_dict["exclude"]:
            log(f"    Exclude     : {', '.join(s_dict['exclude'])}")
    log("\n" + "=" * 80)
    return 0


def _handle_space_match(cmd_bags: CmdBags) -> int:
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    json_output = cmd_bags.has_option("json")
    space_opt = cmd_bags.get_option_value("space") or cmd_bags.get_option_value("s")

    if not cmd_bags.args:
        from core.space import SpaceError

        return _emit_space_error(SpaceError("Target path argument is required for 'match'."), json_output)

    target_path = cmd_bags.args[0]
    space_query = space_opt or (cmd_bags.args[1] if len(cmd_bags.args) > 1 else None)

    from core.space import SpaceError, get_default_registry

    try:
        reg = get_default_registry()
        res = reg.match_path(target_path, space_query=space_query)
    except SpaceError as exc:
        return _emit_space_error(exc, json_output)

    payload = {"status": "ok", **res.to_dict()}
    if json_output:
        log(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    state_str = "MATCHED" if res.matched else "NOT MATCHED"
    log(f"[core:file-space] Match Path: {res.target_path} -> [{state_str}]")
    log(f"  Absolute Path  : {res.abs_path}")
    log(f"  Matched Spaces : {', '.join(res.matched_spaces) if res.matched_spaces else '(none)'}")
    for d in res.details:
        log(f"  - [{d.qualified_space}] matched={d.matched} reason={d.reason}")
        if d.matched_entry:
            log(f"      entry   : {d.matched_entry}")
        if d.include_rule:
            log(f"      include : {d.include_rule} ({d.include_source})")
        if d.exclude_rule:
            log(f"      exclude : {d.exclude_rule} ({d.exclude_source})")
    return 0


def _handle_space_ls(cmd_bags: CmdBags) -> int:
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    json_output = cmd_bags.has_option("json")
    space_opt = cmd_bags.get_option_value("space") or cmd_bags.get_option_value("s")
    pattern = cmd_bags.get_option_value("pattern") or cmd_bags.get_option_value("p")
    space_query = space_opt or (cmd_bags.args[0] if cmd_bags.args else None)

    from core.space import SpaceError, get_default_registry

    try:
        reg = get_default_registry()
        files = reg.iter_space_files(space_query=space_query, pattern=pattern)
    except SpaceError as exc:
        return _emit_space_error(exc, json_output)

    payload = {
        "status": "ok",
        "space": space_query or "*",
        "pattern": pattern,
        "count": len(files),
        "files": [f.to_dict() for f in files],
    }
    if json_output:
        log(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    for f in files:
        spaces_tag = ",".join(f.matched_spaces)
        log(f"{f.rel_path}\t({f.size} B)\t[{spaces_tag}]")
    log(f"Total files: {len(files)}")
    return 0


def _handle_space_hash(cmd_bags: CmdBags) -> int:
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    json_output = cmd_bags.has_option("json")
    policy_opt = cmd_bags.get_option_value("policy") or cmd_bags.get_option_value("p")
    target = cmd_bags.args[0] if cmd_bags.args else None

    from core.space import SpaceError, get_default_registry, hash_target

    try:
        reg = get_default_registry()
        res = hash_target(reg, target=target, policy=policy_opt)
    except SpaceError as exc:
        return _emit_space_error(exc, json_output)

    payload = {"status": "ok", **res.to_dict()}
    if json_output:
        log(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    log(f"[core:file-space] Hash Target: {res.target} ({res.target_type})")
    log(f"  Policy      : {res.policy}")
    log(f"  File Count  : {res.file_count}")
    log(f"  Merkle Root : {res.merkle_root}")
    return 0


def _handle_space_status(cmd_bags: CmdBags) -> int:
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    json_output = cmd_bags.has_option("json")
    space_opt = cmd_bags.get_option_value("space") or cmd_bags.get_option_value("s")
    space_query = space_opt or (cmd_bags.args[0] if cmd_bags.args else None)

    from core.space import SpaceError, get_default_scanner

    try:
        scanner = get_default_scanner()
        payload = scanner.status(space_query=space_query)
    except SpaceError as exc:
        return _emit_space_error(exc, json_output)

    if json_output:
        log(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    log("=" * 80)
    log(f"  YS-Codebase Core File-Space Status ({payload['space_count']} space(s))")
    log("=" * 80)
    log(f"  Project Root       : {payload['project_root']}")
    log(f"  Storage Root       : {payload['storage_root']}")
    log(f"  Unified Generation : {payload['unified_generation']}")
    if payload["unified_merkle_root"]:
        log(f"  Unified MerkleRoot : {payload['unified_merkle_root']}")
    for s_info in payload["spaces"]:
        log(f"\n[*] {s_info['qualified_name']} (gen={s_info['head_generation']}, files={s_info['active_file_count']})")
        if s_info["merkle_root"]:
            log(f"    Merkle Root : {s_info['merkle_root']}")
        if s_info.get("compose"):
            log(f"    Compose     : {', '.join(s_info['compose'])}")
        if s_info.get("cursors"):
            for cid, c_rec in s_info["cursors"].items():
                log(f"    Cursor[{cid}] : acked_gen={c_rec['acked_generation']}")
    log("\n" + "=" * 80)
    return 0


def _handle_space_scan(cmd_bags: CmdBags) -> int:
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    json_output = cmd_bags.has_option("json")
    force = cmd_bags.has_option("force") or cmd_bags.has_option("f")
    space_opt = cmd_bags.get_option_value("space") or cmd_bags.get_option_value("s")
    space_query = space_opt or (cmd_bags.args[0] if cmd_bags.args else None)

    from core.space import SpaceError, get_default_scanner

    try:
        scanner = get_default_scanner()
        res = scanner.scan(space_query=space_query, force=force)
    except SpaceError as exc:
        return _emit_space_error(exc, json_output)

    payload = {"status": "ok", **res.to_dict()}
    if json_output:
        log(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    log(f"[core:file-space] Scan Target: {res.space_name} (gen {res.from_generation} -> {res.to_generation})")
    log(
        f"  Added: {res.added_count}, Modified: {res.modified_count}, "
        f"Deleted: {res.deleted_count}, Unchanged: {res.unchanged_count}"
    )
    log(f"  Merkle Root : {res.merkle_root}")
    return 0


def _handle_space_diff(cmd_bags: CmdBags) -> int:
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    json_output = cmd_bags.has_option("json")
    do_ack = cmd_bags.has_option("ack") or cmd_bags.has_option("a")
    consumer_id = (
        cmd_bags.get_option_value("consumer")
        or cmd_bags.get_option_value("c")
        or "default"
    )
    space_opt = cmd_bags.get_option_value("space") or cmd_bags.get_option_value("s")
    space_query = space_opt or (cmd_bags.args[0] if cmd_bags.args else None)

    from core.space import SpaceError, get_default_scanner

    try:
        scanner = get_default_scanner()
        res = scanner.diff(space_query=space_query, consumer_id=consumer_id)
        acked_gen: Optional[int] = None
        if do_ack:
            acked_gen = scanner.ack(
                space_query=space_query,
                consumer_id=consumer_id,
                generation=res.to_generation,
                space_generations=res.space_generations,
            )
    except SpaceError as exc:
        return _emit_space_error(exc, json_output)

    payload = {
        "status": "ok",
        "consumer": consumer_id,
        "acked": do_ack,
        "acked_generation": acked_gen,
        **res.to_dict(),
    }
    if json_output:
        log(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    log(
        f"[core:file-space] Diff Target: {res.space_name} [consumer={consumer_id}] "
        f"(gen {res.from_generation} -> {res.to_generation})"
    )
    log(
        f"  Added: {res.added_count}, Modified: {res.modified_count}, "
        f"Deleted: {res.deleted_count}, Unchanged: {res.unchanged_count}"
    )
    for rel_p in sorted(res.detail.added):
        log(f"  + {rel_p}")
    for rel_p in sorted(res.detail.modified):
        log(f"  M {rel_p}")
    for rel_p in sorted(res.detail.deleted):
        log(f"  - {rel_p}")
    if do_ack:
        log(f"  [ACK] Consumer '{consumer_id}' advanced to generation {acked_gen}")
    return 0


def _handle_space_clean(cmd_bags: CmdBags) -> int:
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    json_output = cmd_bags.has_option("json")
    consumer_id = cmd_bags.get_option_value("consumer") or cmd_bags.get_option_value("c")
    space_opt = cmd_bags.get_option_value("space") or cmd_bags.get_option_value("s")
    space_query = space_opt or (cmd_bags.args[0] if cmd_bags.args else None)

    from core.space import SpaceError, get_default_scanner

    try:
        scanner = get_default_scanner()
        payload = scanner.clean(space_query=space_query, consumer_id=consumer_id)
    except SpaceError as exc:
        return _emit_space_error(exc, json_output)

    if json_output:
        log(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    log_info(
        f"[core:file-space] Clean Target: {payload['space']} "
        f"(removed_snapshots={len(payload['removed_snapshots'])}, "
        f"reset_consumers={len(payload['reset_consumers'])})"
    )
    return 0


def _dispatch_space_group(cmd_bags: CmdBags, group_cmd_name: str) -> int:
    guard_dispatch("core")
    cmd_bags = _normalize_bags(cmd_bags)
    if not cmd_bags.args:
        return _render_subcommand_group_help(group_cmd_name)
    sub_cmd = cmd_bags.args[0]
    sub_bags = CmdBags(
        raw_cmd=cmd_bags.raw_cmd,
        command=sub_cmd,
        args=cmd_bags.args[1:],
        options=cmd_bags.options,
    )
    handlers = {
        "spaces": _handle_space_spaces,
        "match": _handle_space_match,
        "ls": _handle_space_ls,
        "hash": _handle_space_hash,
        "status": _handle_space_status,
        "scan": _handle_space_scan,
        "diff": _handle_space_diff,
        "clean": _handle_space_clean,
    }
    handler = handlers.get(sub_cmd)
    if handler is not None:
        return handler(sub_bags)
    log_error(
        f"[core:{group_cmd_name}] Unknown subcommand '{sub_cmd}'. "
        "Available: spaces, match, ls, hash, status, scan, diff, clean",
        stream="stderr",
    )
    return 1


def file_space_spaces(cmd_bags: CmdBags) -> int:
    return _handle_space_spaces(cmd_bags)


def file_space_match(cmd_bags: CmdBags) -> int:
    return _handle_space_match(cmd_bags)


def file_space_ls(cmd_bags: CmdBags) -> int:
    return _handle_space_ls(cmd_bags)


def file_space_hash(cmd_bags: CmdBags) -> int:
    return _handle_space_hash(cmd_bags)


def file_space_status(cmd_bags: CmdBags) -> int:
    return _handle_space_status(cmd_bags)


def file_space_scan(cmd_bags: CmdBags) -> int:
    return _handle_space_scan(cmd_bags)


def file_space_diff(cmd_bags: CmdBags) -> int:
    return _handle_space_diff(cmd_bags)


def file_space_clean(cmd_bags: CmdBags) -> int:
    return _handle_space_clean(cmd_bags)


def fs_spaces(cmd_bags: CmdBags) -> int:
    return _handle_space_spaces(cmd_bags)


def fs_match(cmd_bags: CmdBags) -> int:
    return _handle_space_match(cmd_bags)


def fs_ls(cmd_bags: CmdBags) -> int:
    return _handle_space_ls(cmd_bags)


def fs_hash(cmd_bags: CmdBags) -> int:
    return _handle_space_hash(cmd_bags)


def fs_status(cmd_bags: CmdBags) -> int:
    return _handle_space_status(cmd_bags)


def fs_scan(cmd_bags: CmdBags) -> int:
    return _handle_space_scan(cmd_bags)


def fs_diff(cmd_bags: CmdBags) -> int:
    return _handle_space_diff(cmd_bags)


def fs_clean(cmd_bags: CmdBags) -> int:
    return _handle_space_clean(cmd_bags)


def file_space(cmd_bags: CmdBags) -> int:
    """Core L0 Atomic & Composite File-Space Engine (Group Dispatcher)."""
    return _dispatch_space_group(cmd_bags, "file-space")


def fs(cmd_bags: CmdBags) -> int:
    """Shorthand alias for Core L0 Atomic & Composite File-Space Engine (Group Dispatcher)."""
    return _dispatch_space_group(cmd_bags, "fs")
