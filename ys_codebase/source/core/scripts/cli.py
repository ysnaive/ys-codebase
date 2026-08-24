"""
Core Module CLI Dispatcher.
"""
import sys
import os

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

def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
        
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("YS-Codebase Core Module CLI")
        print("Commands:")
        print("  install <module>[@version] [--provider=<source>]")
        print("  update [module] [--provider=<source>]")
        print("  remove <module> [--clean]")
        print("  list [--remote]")
        print("  status")
        print("  rollback [snapshot_id]")
        print("  reload")
        return 0

    cmd = argv[0]
    args = argv[1:]
    
    # Parse provider flag if present
    provider = None
    clean = False
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
        return installer.cmd_remove(mod_name, clean=clean)
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
