"""
CLI router entry point for module:dev.
Migrated to core.commands active execution contract with strong-typed CmdBags.
"""
import sys
import os
import json
from typing import Any, List, Optional

from core.commands import CmdBags, CmdOption
from core.guard import guard_dispatch
from core import uri
from core import semver
from dev.scaffold import Scaffolder
from dev.checker import Checker, CheckSeverity, CheckIssue, CheckReport
from dev.builder import Builder
from dev.tester import Tester
from dev.releaser import Releaser


def _normalize_bags(cmd_bags: Any, default_cmd: str = "") -> CmdBags:
    """容錯正規化：若傳入 List[str] 則包裝為 CmdBags，支援內部測試直呼。"""
    if isinstance(cmd_bags, CmdBags):
        return cmd_bags
    if isinstance(cmd_bags, (list, tuple)):
        args = list(cmd_bags)
        raw_cmd = " ".join(args)
        opts = {}
        pos = []
        for a in args:
            if a.startswith("--"):
                k = a[2:]
                v = True
                if "=" in k:
                    k, val = k.split("=", 1)
                    v = val
                opts[k] = CmdOption(name=k, params=v)
            elif a.startswith("-") and len(a) > 1:
                k = a[1:]
                opts[k] = CmdOption(name=k, params=True)
            else:
                pos.append(a)
        return CmdBags(raw_cmd=raw_cmd, command=default_cmd, args=pos, options=opts)
    return CmdBags(raw_cmd="", command=default_cmd, args=[], options={})


def _handle_bump(subcmd: str, cmd_bags: CmdBags) -> int:
    guard_dispatch("dev")
    bump_type = subcmd.split("-", 1)[1].lower() if "-" in subcmd else subcmd.lower()
    targets = cmd_bags.args
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


def create(cmd_bags: Any) -> int:
    """Create a new module skeleton (source/<name>)."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "create")
    if not bags.args:
        print("[dev:create] Usage: python yscb.py dev create <name> [--desc=\"...\"]")
        return 1
    name = bags.args[0]
    desc = "A YS-Codebase module"
    desc_opt = bags.get_option("desc")
    if desc_opt:
        desc = str(desc_opt).strip('\"')
    scaffolder = Scaffolder()
    ok, msg = scaffolder.create_module(name, desc)
    print(f"[dev:create] {msg}")
    return 0 if ok else 1


def check(cmd_bags: Any) -> int:
    """Validate module structure and manifest compliance."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "check")
    checker = Checker()
    json_output = bags.has_option("json")
    check_all = bags.has_option("all") or bags.has_option("a") or not bags.args

    if check_all:
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
        name = bags.args[0]
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


def build(cmd_bags: Any) -> int:
    """Build dev package (.build.zip with tests)."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "build")
    builder = Builder()
    build_all = bags.has_option("all") or bags.has_option("a") or not bags.args

    if build_all:
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
        name = bags.args[0]
        passed, msg = builder.build_module(name)
        print(f"[dev:build] {msg}")
        return 0 if passed else 1


def release(cmd_bags: Any) -> int:
    """Package and release pure module (.zip to release/)."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "release")
    releaser = Releaser()
    force = bags.has_option("force") or bags.has_option("f")
    release_all = bags.has_option("all") or bags.has_option("a") or not bags.args

    if release_all:
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
        name = bags.args[0]
        ok, msg = releaser.release_module(name, force=force)
        if ok:
            print(f"[dev:release] {msg}")
            return 0
        else:
            print(f"[dev:release] Error: {msg}", file=sys.stderr)
            return 1


def release_check(cmd_bags: Any) -> int:
    """Run 3-Gate verification on release readiness without packaging."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "release-check")
    if bags.has_option("all") or bags.has_option("a"):
        print("[dev:release-check] Error: 'release-check' only supports checking a single module. '--all' is not supported.", file=sys.stderr)
        return 1
    force = bags.has_option("force") or bags.has_option("f")
    if not bags.args:
        print("[dev:release-check] Usage: python yscb.py dev release-check <module_name> [--force|-f]")
        return 1
    mod_name = bags.args[0]
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


def release_git(cmd_bags: Any) -> int:
    """Integrated pipeline: test -> release-check -> release -> local git commit/tag."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "release-git")
    force = bags.has_option("force") or bags.has_option("f")
    commit_msg = bags.get_option("msg") or bags.get_option("m")
    if len(bags.args) < 1 or (not commit_msg and len(bags.args) < 2):
        print("[dev:release-git] Usage: python yscb.py dev release-git <module_name> \"<commit message>\" [--force|-f]")
        return 1
    mod_name = bags.args[0]
    if not commit_msg:
        commit_msg = bags.args[1]
    releaser = Releaser()
    ok, msg = releaser.release_git(mod_name, str(commit_msg), force=force)
    if ok:
        print(f"[dev:release-git] {msg}")
        return 0
    else:
        print(f"[dev:release-git] Error: {msg}", file=sys.stderr)
        return 1


def bump_major(cmd_bags: Any) -> int:
    bags = _normalize_bags(cmd_bags, "bump-major")
    return _handle_bump("bump-major", bags)


def bump_minor(cmd_bags: Any) -> int:
    bags = _normalize_bags(cmd_bags, "bump-minor")
    return _handle_bump("bump-minor", bags)


def bump_patch(cmd_bags: Any) -> int:
    bags = _normalize_bags(cmd_bags, "bump-patch")
    return _handle_bump("bump-patch", bags)


def bump_revision(cmd_bags: Any) -> int:
    bags = _normalize_bags(cmd_bags, "bump-revision")
    return _handle_bump("bump-revision", bags)


def test(cmd_bags: Any) -> int:
    """Run module tests inside an isolated sandbox."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "test")
    raw_args = ["test"]
    if bags.args:
        raw_args.extend(bags.args)
    for opt_name, opt in bags.options.items():
        if opt.params is True:
            raw_args.append(f"--{opt_name}")
        elif opt.params is not False and opt.params is not None:
            raw_args.append(f"--{opt_name}={opt.params}")
    tester = Tester()
    return tester.run(raw_args)


def op_mksb(cmd_bags: Any) -> int:
    """Internal atomic sandbox creation operation."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "op-mksb")
    raw_args = ["op-mksb"] + bags.args
    for opt_name, opt in bags.options.items():
        if opt.params is True:
            raw_args.append(f"--{opt_name}")
        elif opt.params is not False and opt.params is not None:
            raw_args.append(f"--{opt_name}={opt.params}")
    tester = Tester()
    return tester.run(raw_args)


def op_test(cmd_bags: Any) -> int:
    """Internal atomic test runner operation."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "op-test")
    raw_args = ["op-test"] + bags.args
    for opt_name, opt in bags.options.items():
        if opt.params is True:
            raw_args.append(f"--{opt_name}")
        elif opt.params is not False and opt.params is not None:
            raw_args.append(f"--{opt_name}={opt.params}")
    tester = Tester()
    return tester.run(raw_args)

