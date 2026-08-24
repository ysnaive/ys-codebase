"""
CLI router entry point for module:dev.
"""
import sys
import os
from typing import List

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
from dev.tester import Tester

def main(argv: List[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("[dev] YS-Codebase Developer Tools")
        print("Usage:")
        print("  python yscb.py dev create <name> [--desc=\"...\"]")
        print("  python yscb.py dev check [name | --all]")
        print("  python yscb.py dev build [name | --all] [--clean]")
        print("  python yscb.py dev test [name | --all] [options]")
        print("  python yscb.py dev op-mksb [--dir=<path>]")
        print("  python yscb.py dev op-test [name | --all] [options]")
        return 0

    subcmd = argv[0]
    sub_argv = argv[1:]

    if subcmd == "create":
        if not sub_argv:
            print("[dev:create] Usage: python yscb.py dev create <name> [--desc=\"...\"]")
            return 1
        name = sub_argv[0]
        desc = "A YS-Codebase module"
        for arg in sub_argv[1:]:
            if arg.startswith("--desc="):
                desc = arg.split("=", 1)[1].strip('\"')
        scaffolder = Scaffolder()
        ok, msg = scaffolder.create_module(name, desc)
        print(f"[dev:create] {msg}")
        return 0 if ok else 1

    elif subcmd == "check":
        checker = Checker()
        if not sub_argv or "--all" in sub_argv:
            print("[dev:check] Scanning all modules in source/...")
            results = checker.check_all()
            all_ok = True
            for mod, (passed, errors) in results.items():
                if passed:
                    print(f"  [*] {mod}: PASSED")
                else:
                    all_ok = False
                    print(f"  [!] {mod}: FAILED")
                    for err in errors:
                        print(f"      - {err}")
            return 0 if all_ok else 1
        else:
            name = sub_argv[0]
            passed, errors = checker.check_module(name)
            if passed:
                print(f"[dev:check] Module '{name}': PASSED")
                return 0
            else:
                print(f"[dev:check] Module '{name}': FAILED")
                for err in errors:
                    print(f"  - {err}")
                return 1

    elif subcmd == "build":
        builder = Builder()
        clean = "--clean" in sub_argv
        targets = [a for a in sub_argv if not a.startswith("-")]

        if "--all" in sub_argv or not targets:
            print("[dev:build] Building all modules in source/...")
            results = builder.build_all(clean=clean)
            all_ok = True
            for mod, (passed, msg) in results.items():
                if passed:
                    print(f"  [*] {mod}: {msg}")
                else:
                    all_ok = False
                    print(f"  [!] {mod}: {msg}")
            return 0 if all_ok else 1
        else:
            name = targets[0]
            passed, msg = builder.build_module(name, clean=clean)
            print(f"[dev:build] {msg}")
            return 0 if passed else 1

    elif subcmd in ("test", "op-mksb", "op-test"):
        tester = Tester()
        return tester.run([subcmd] + sub_argv)

    else:
        print(f"[dev] Unknown subcommand '{subcmd}'. Use --help for available commands.")
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
