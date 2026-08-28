"""
CLI router entry point for module:dev.
"""
import sys
import os
import json
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

from core import uri
from core import semver
from dev.scaffold import Scaffolder
from dev.checker import Checker, CheckSeverity, CheckIssue, CheckReport
from dev.builder import Builder
from dev.tester import Tester
from dev.releaser import Releaser


def _handle_bump(subcmd: str, sub_argv: List[str]) -> int:
    bump_type = subcmd.split("-", 1)[1].lower()
    targets = [a for a in sub_argv if not a.startswith("-")]
    if not targets:
        print(f"[dev:{subcmd}] Usage: python yscb.py dev {subcmd} <module_name>")
        return 1
    
    mod_name = targets[0]
    src_manifest_uri = f"module.source://{mod_name}/manifest.json"
    if not uri.exists(src_manifest_uri):
        print(f"[dev:{subcmd}] Error: Source module '{mod_name}' not found at {src_manifest_uri}.", file=sys.stderr)
        return 1

    try:
        manifest_data = uri.read_json(src_manifest_uri)
        curr_ver = manifest_data.get("version", "1.0.0.0")
        next_ver = semver.bump_version(curr_ver, bump_type)
        manifest_data["version"] = next_ver
        uri.write_json(src_manifest_uri, manifest_data, indent=2)
        print(f"[dev:{subcmd}] Successfully bumped '{mod_name}': {curr_ver} -> {next_ver} ({bump_type}).")
        return 0
    except Exception as e:
        print(f"[dev:{subcmd}] Error bumping version for '{mod_name}': {e}", file=sys.stderr)
        return 1

def main(argv: List[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("[dev] YS-Codebase Developer Tools")
        print("Usage:")
        print("  python yscb.py dev create <name> [--desc=\"...\"]")
        print("  python yscb.py dev check [name | --all]")
        print("  python yscb.py dev build [name | --all]")
        print("  python yscb.py dev release [name | --all] [--force|-f]")
        print("  python yscb.py dev release-check <name> [--force|-f]")
        print("  python yscb.py dev release-git <name> \"<commit message>\" [--force|-f]")
        print("  python yscb.py dev bump-[major|minor|patch|revision] <name>")
        print("  python yscb.py dev test [name | --all] [--no-build] [-j <N>] [--sequential] [options]")
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
        json_output = "--json" in sub_argv
        filtered_argv = [a for a in sub_argv if a != "--json"]

        if not filtered_argv or "--all" in filtered_argv or "-a" in filtered_argv:
            reports = checker.check_all()
            if json_output:
                print(json.dumps({mod: rep.to_dict() for mod, rep in reports.items()}, indent=2))
                return 0 if all(rep.passed for rep in reports.values()) else 1

            print("=" * 70)
            print("YS-Codebase Module Compliance Diagnostic Report")
            print("=" * 70)
            all_passed = True
            pass_cnt, warn_cnt, fail_cnt = 0, 0, 0

            for mod, rep in reports.items():
                if rep.status == CheckSeverity.PASS:
                    pass_cnt += 1
                    print(f"[*] Module: {mod:<50} [PASS]")
                elif rep.status == CheckSeverity.WARN:
                    warn_cnt += 1
                    print(f"[*] Module: {mod:<50} [WARN]")
                    for issue in rep.issues:
                        if issue.severity == CheckSeverity.WARN:
                            loc = f" ({issue.file_path})" if issue.file_path else ""
                            print(f"    |-- [WARN] [{issue.category}]{loc} {issue.message}")
                else:
                    fail_cnt += 1
                    all_passed = False
                    print(f"[*] Module: {mod:<50} [FAIL]")
                    for issue in rep.issues:
                        loc = f" ({issue.file_path})" if issue.file_path else ""
                        tag = issue.severity.value
                        print(f"    |-- [{tag}] [{issue.category}]{loc} {issue.message}")

            print("-" * 70)
            status_text = "PASSED" if all_passed and warn_cnt == 0 else ("WARNINGS FOUND" if all_passed else "FAILED (Release Blocked)")
            print(f"Summary : {len(reports)} Total, {pass_cnt} Passed, {warn_cnt} Warnings, {fail_cnt} Failed")
            print(f"Status  : {status_text}")
            print("=" * 70)
            return 0 if all_passed else 1
        else:
            name = filtered_argv[0]
            rep = checker.check_module(name)
            if json_output:
                print(json.dumps(rep.to_dict(), indent=2))
                return 0 if rep.passed else 1

            print("=" * 70)
            print(f"YS-Codebase Module Compliance Report: {name}")
            print("=" * 70)
            print(f"[*] Module: {name:<50} [{rep.status.value}]")
            for issue in rep.issues:
                loc = f" ({issue.file_path})" if issue.file_path else ""
                tag = issue.severity.value
                print(f"    |-- [{tag}] [{issue.category}]{loc} {issue.message}")
            print("-" * 70)
            status_text = "PASSED" if rep.passed and not rep.has_warns else ("WARNINGS FOUND" if rep.passed else "FAILED (Release Blocked)")
            print(f"Status  : {status_text}")
            print("=" * 70)
            return 0 if rep.passed else 1


    elif subcmd == "build":
        builder = Builder()
        targets = [a for a in sub_argv if not a.startswith("-")]

        if "--all" in sub_argv or not targets:
            print("[dev:build] Building all modules in source/ (dev complete package)...")
            results = builder.build_all()
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
            passed, msg = builder.build_module(name)
            print(f"[dev:build] {msg}")
            return 0 if passed else 1

    elif subcmd == "release":
        releaser = Releaser()
        force = "--force" in sub_argv or "-f" in sub_argv
        targets = [a for a in sub_argv if not a.startswith("-")]

        if "--all" in sub_argv or not targets:
            print("[dev:release] Releasing all modules in source/ (topological pure release)...")
            try:
                results = releaser.release_all(force=force)
                all_ok = True
                for mod, (passed, msg) in results.items():
                    if passed:
                        print(f"  [*] {mod}: {msg}")
                    else:
                        all_ok = False
                        print(f"  [!] {mod}: {msg}")
                return 0 if all_ok else 1
            except Exception as e:
                print(f"[dev:release] Batch release error: {e}", file=sys.stderr)
                return 1
        else:
            name = targets[0]
            ok, msg = releaser.release_module(name, force=force)
            if ok:
                print(f"[dev:release] {msg}")
                return 0
            else:
                print(f"[dev:release] Error: {msg}", file=sys.stderr)
                return 1

    elif subcmd.startswith("bump-") and subcmd in ("bump-major", "bump-minor", "bump-patch", "bump-revision"):
        return _handle_bump(subcmd, sub_argv)

    elif subcmd == "release-check":
        if "--all" in sub_argv:
            print("[dev:release-check] Error: 'release-check' only supports checking a single module. '--all' is not supported.", file=sys.stderr)
            return 1
        force = "--force" in sub_argv or "-f" in sub_argv
        targets = [a for a in sub_argv if not a.startswith("-")]
        if not targets:
            print("[dev:release-check] Usage: python yscb.py dev release-check <module_name> [--force|-f]")
            return 1
        mod_name = targets[0]
        releaser = Releaser()
        passed, errors = releaser.release_check(mod_name, force=force)
        if passed:
            msg_suffix = " (Force Override mode)" if force else ""
            print(f"[dev:release-check] Module '{mod_name}' is READY for release (All 3 Gates Passed){msg_suffix}.")
            return 0
        else:
            print(f"[dev:release-check] Module '{mod_name}' FAILED release check:")
            for err in errors:
                print(f"  - {err}")
            return 1

    elif subcmd == "release-git":
        force = "--force" in sub_argv or "-f" in sub_argv
        targets = [a for a in sub_argv if not a.startswith("-")]
        if len(targets) < 2:
            print("[dev:release-git] Usage: python yscb.py dev release-git <module_name> \"<commit message>\" [--force|-f]")
            return 1
        mod_name = targets[0]
        commit_msg = targets[1]
        releaser = Releaser()
        ok, msg = releaser.release_git(mod_name, commit_msg, force=force)
        if ok:
            print(f"[dev:release-git] {msg}")
            return 0
        else:
            print(f"[dev:release-git] Error: {msg}", file=sys.stderr)
            return 1

    elif subcmd in ("test", "op-mksb", "op-test"):
        tester = Tester()
        return tester.run([subcmd] + sub_argv)

    else:
        print(f"[dev] Unknown subcommand '{subcmd}'. Use --help for available commands.")
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
