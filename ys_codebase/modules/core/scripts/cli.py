"""
Core Module CLI Dispatcher.
"""
import sys
import os
from typing import List

# Add parent directory to sys.path so 'core' package can be imported directly
current_dir = os.path.dirname(os.path.abspath(__file__))
module_dir = os.path.dirname(current_dir)
modules_root = os.path.dirname(module_dir)

if os.path.isdir(modules_root):
    for m in os.listdir(modules_root):
        m_p = os.path.join(modules_root, m)
        if os.path.isdir(m_p) and m_p not in sys.path:
            sys.path.insert(0, m_p)

if module_dir not in sys.path:
    sys.path.insert(0, module_dir)

from core.installer import Installer
from core import uri


def cmd_uri(args: List[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        print("YS-Codebase Semantic URI VFS CLI")
        print("Usage:")
        print("  uri list / uri --list             List all registered semantic URI schemes")
        print("  uri resolve <path_or_uri>         Resolve semantic URI to absolute path")
        print("  uri to-uri <abs_path>             Convert absolute path to semantic URI")
        print("  uri check                         Health check all registered URI schemes")
        return 0

    sub_cmd = args[0]
    sub_args = args[1:]

    if sub_cmd in ("list", "--list", "-l"):
        schemes = uri.list_registered_schemes_summary()
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
    elif sub_cmd == "resolve":
        if not sub_args:
            print("[core:uri] Error: URI string required.")
            return 1
        try:
            res = uri.resolve(sub_args[0], interactive=True)
            print(res)
            return 0
        except Exception as e:
            print(f"[core:uri] Error: {e}")
            return 1
    elif sub_cmd == "to-uri":
        if not sub_args:
            print("[core:uri] Error: Absolute path required.")
            return 1
        try:
            res = uri.to_uri(sub_args[0])
            print(res)
            return 0
        except Exception as e:
            print(f"[core:uri] Error: {e}")
            return 1
    elif sub_cmd == "check":
        schemes = uri.list_registered_schemes_summary()
        print("\nYS-Codebase URI Health Check:")
        print("-" * 80)
        healthy = True
        for s in schemes:
            status = "OK" if not s['resolved_path'].startswith("!undefined") else "UNDEFINED"
            if status == "UNDEFINED":
                healthy = False
            print(f"[*] {s['token'] + '://':<18} -> {s['resolved_path']} [{status}]")
        print("-" * 80)
        print(f"Overall URI Status: {'HEALTHY' if healthy else 'WARNING (!undefined schemes present)'}")
        return 0
    else:
        print(f"[core:uri] Unknown sub-command '{sub_cmd}'. Run 'python yscb.py uri --help' for help.")
        return 1


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
        
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("YS-Codebase Core Module CLI")
        print("Commands:")
        print("  install <module>[@version] [--provider=<source>]")
        print("  update [module] [--provider=<source>]")
        print("  remove <module> [--clean] [--purge] [--force]")
        print("  list [--remote]")
        print("  status")
        print("  rollback [snapshot_id]")
        print("  reload")
        print("  uri <list|resolve|to-uri|check>")
        return 0

    cmd = argv[0]
    args = argv[1:]
    
    if cmd == "uri":
        return cmd_uri(args)

    # Parse provider flag if present
    provider = None
    clean = False
    purge = False
    remote = False
    clean_args = []
    force_flag = False
    version = None
    
    for a in args:
        if a.startswith("--provider="):
            provider = a.split("=", 1)[1].strip("\"'")
        elif a.startswith("--version="):
            version = a.split("=", 1)[1].strip("\"'")
        elif a == "--force":
            force_flag = True
        elif a == "--clean":
            clean = True
        elif a == "--purge":
            purge = True
        elif a == "--remote":
            remote = True
        else:
            clean_args.append(a)

    installer = Installer()
    
    if cmd == "install":
        if not clean_args:
            print("[core:install] Error: Module name is required.")
            return 1
        module_spec = clean_args[0]
        if "@" in module_spec:
            module_name, version = module_spec.split("@", 1)
        else:
            module_name = module_spec
        return installer.cmd_install(module_name, version=version, provider=provider, force=force_flag)
    elif cmd == "update":
        mod_name = clean_args[0] if clean_args else None
        return installer.cmd_update(mod_name, provider=provider)
    elif cmd == "remove":
        mod_name = clean_args[0] if clean_args else ""
        return installer.cmd_remove(mod_name, clean=clean, purge=purge, force=force_flag)
    elif cmd == "list":
        return installer.cmd_list(remote=remote, provider=provider)
    elif cmd == "status":
        return installer.cmd_status()
    elif cmd == "rollback":
        target = clean_args[0] if clean_args else None
        return installer.cmd_rollback(target)
    elif cmd == "reload":
        return installer.cmd_reload()
    else:
        print(f"[core] Unknown command '{cmd}'. Run 'python yscb.py core --help' for available commands.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
