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
from dev.releaser import ReleasePipeline

def main(argv: List[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("[dev] YS-Codebase Developer Tools")
        print("Usage:")
        print("  python yscb.py dev create <name> [--desc=\"...\"]")
        print("  python yscb.py dev check [name | --all]")
        print("  python yscb.py dev build [name | --all] [--clean]")
        print("  python yscb.py dev release <name> [bump_type] [options]")
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
            print("[dev:build] Building all modules in source/ (dev complete package)...")
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

    elif subcmd == "release":
        if not sub_argv:
            print("[dev:release] Usage: python yscb.py dev release <module> [major|minor|patch|revision|ver] [options]")
            return 1
            
        mod_name = sub_argv[0]
        bump_type = None
        explicit_ver = None
        yes = "-y" in sub_argv or "--yes" in sub_argv
        dry_run = "--dry-run" in sub_argv
        tag_flag = True if "--tag" in sub_argv else (False if "--no-tag" in sub_argv else None)
        no_test = "--no-test" in sub_argv
        
        pos_args = [a for a in sub_argv[1:] if not a.startswith("-")]
        if pos_args:
            arg_val = pos_args[0]
            if arg_val.lower() in ("major", "minor", "patch", "revision"):
                bump_type = arg_val.lower()
            else:
                explicit_ver = arg_val
                
        releaser = ReleasePipeline()
        ok, msg = releaser.run_release(
            module_name=mod_name,
            bump_type=bump_type,
            explicit_version=explicit_ver,
            yes=yes,
            dry_run=dry_run,
            tag=tag_flag,
            no_test=no_test
        )
        print(f"[dev:release] {msg}")
        return 0 if ok else 1

    elif subcmd in ("test", "op-mksb", "op-test"):
        tester = Tester()
        return tester.run([subcmd] + sub_argv)

    else:
        print(f"[dev] Unknown subcommand '{subcmd}'. Use --help for available commands.")
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
