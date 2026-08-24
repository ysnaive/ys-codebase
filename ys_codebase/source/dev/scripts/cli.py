"""
Dev Module CLI Dispatcher.
"""
import sys
import os

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

from dev.scaffold import Scaffolder
from dev.checker import Checker
from dev.builder import Builder
from core import uri

def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
        
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("YS-Codebase Developer Tools (dev)")
        print("Commands:")
        print("  create <module_name> [--desc=\"<description>\"]")
        print("  check [module_name | --all]")
        print("  build [module_name | --all] [--clean]")
        return 0

    cmd = argv[0]
    args = argv[1:]
    
    desc = ""
    clean = False
    all_flag = False
    clean_args = []
    
    for a in args:
        if a.startswith("--desc="):
            desc = a.split("=", 1)[1].strip("\"'")
        elif a.startswith("--description="):
            desc = a.split("=", 1)[1].strip("\"'")
        elif a == "--clean":
            clean = True
        elif a == "--all":
            all_flag = True
        else:
            clean_args.append(a)

    scaffolder = Scaffolder()
    checker = Checker()
    builder = Builder()

    if cmd == "create":
        if not clean_args:
            print("[dev:create] Error: Module name is required.")
            return 1
        name = clean_args[0]
        ok, msg = scaffolder.create_module(name, description=desc)
        print(f"[dev:create] {msg}")
        return 0 if ok else 1

    elif cmd == "check":
        if all_flag or not clean_args:
            print("[dev:check] Scanning all modules in source/...")
            res_dict = checker.check_all()
            if not res_dict:
                print("  (No modules found in source/)")
                return 0
            all_passed = True
            for mod, (ok, errs) in res_dict.items():
                if ok:
                    print(f"  [*] {mod}: PASSED")
                else:
                    all_passed = False
                    print(f"  [!] {mod}: FAILED")
                    for e in errs:
                        print(f"      - {e}")
            return 0 if all_passed else 1
        else:
            name = clean_args[0]
            ok, errs = checker.check_module(name)
            if ok:
                print(f"[dev:check] Module '{name}' passed all compliance checks.")
                return 0
            else:
                print(f"[dev:check] Module '{name}' failed compliance checks:")
                for e in errs:
                    print(f"  - {e}")
                return 1

    elif cmd == "build":
        if all_flag:
            print("[dev:build] Building all modules in source/...")
            res_dict = builder.build_all(clean=clean)
            if not res_dict:
                print("  (No modules found in source/)")
                return 0
            all_passed = True
            for mod, (ok, msg) in res_dict.items():
                if ok:
                    print(f"  [*] {mod}: {msg}")
                else:
                    all_passed = False
                    print(f"  [!] {mod}: {msg}")
            return 0 if all_passed else 1
        else:
            if not clean_args:
                print("[dev:build] Error: Module name or --all flag is required.")
                return 1
            name = clean_args[0]
            ok, msg = builder.build_module(name, clean=clean)
            print(f"[dev:build] {msg}")
            return 0 if ok else 1

    else:
        print(f"[dev] Unknown command '{cmd}'. Run 'python yscb.py dev --help' for available commands.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
