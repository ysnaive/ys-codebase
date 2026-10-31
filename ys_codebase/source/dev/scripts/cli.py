"""
CLI router entry point for module:dev.
Migrated to core.commands active execution contract with strong-typed CmdBags.
"""
import sys
import os
import json
from typing import Any, List, Dict

from core.commands import CmdBags, CmdOption
from core.guard import guard_dispatch
from core import uri, vfs, semver

def _normalize_bags(cmd_bags: Any, default_cmd: str = "") -> CmdBags:
    """容錯正規化：若傳入 List[str] 則包裝為 CmdBags，支援內部測試直呼與帶值短/長選項別名解析。"""
    if isinstance(cmd_bags, CmdBags):
        return cmd_bags
    if isinstance(cmd_bags, (list, tuple)):
        value_options = {
            "k", "pattern", "m", "msg", "message", "j", "jobs",
            "dir", "type", "target", "desc", "report-json",
        }
        alias_map = {
            "k": "pattern",
            "pattern": "k",
            "m": "msg",
            "msg": "m",
            "message": "msg",
            "j": "jobs",
            "jobs": "j",
            "a": "all",
            "all": "a",
            "q": "quiet",
            "quiet": "q",
            "v": "verbose",
            "verbose": "v",
            "f": "force",
            "force": "f",
            "no-parallel": "sequential",
            "sequential": "no-parallel",
            "stress": "perf",
            "perf": "stress",
        }
        args = list(cmd_bags)
        raw_cmd = " ".join(args)
        opts: Dict[str, CmdOption] = {}
        pos: List[str] = []
        idx = 0
        while idx < len(args):
            a = args[idx]
            if a.startswith("-") and len(a) > 1:
                k = a[2:] if a.startswith("--") else a[1:]
                v: Any = True
                if "=" in k:
                    k, v = k.split("=", 1)
                elif k in value_options and idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                    v = args[idx + 1]
                    idx += 1
                opts[k] = CmdOption(name=k, params=v)
                alt = alias_map.get(k)
                if alt and alt not in opts:
                    opts[alt] = CmdOption(name=alt, params=v)
            else:
                pos.append(a)
            idx += 1
        return CmdBags(raw_cmd=raw_cmd, command=default_cmd, args=pos, options=opts)
    return CmdBags(raw_cmd="", command=default_cmd, args=[], options={})


def _get_short_to_canonical_pairs() -> Dict[str, str]:
    """回傳短別名與對應長選項映射表。"""
    return {
        "k": "pattern",
        "j": "jobs",
        "a": "all",
        "q": "quiet",
        "v": "verbose",
        "f": "force",
        "no-parallel": "sequential",
        "stress": "perf",
    }


def _should_skip_alias(opt_name: str, options: dict) -> bool:
    """若短別名與對應長選項同時存在於 options，略過短別名以避免重複展開。"""
    canon = _get_short_to_canonical_pairs().get(opt_name)
    return bool(canon and canon in options)


def _build_tester_argv(subcmd: str, bags: CmdBags) -> List[str]:
    raw_args = [subcmd]
    if bags.args:
        sub_args = bags.args[1:] if bags.args[0] == subcmd else bags.args
        raw_args.extend(sub_args)
    seen_opts = set()
    short_pairs = _get_short_to_canonical_pairs()
    for opt_name, opt in bags.options.items():
        if opt_name in short_pairs and _should_skip_alias(opt_name, bags.options):
            continue
        if opt_name in seen_opts:
            continue
        seen_opts.add(opt_name)
        if opt.params is True:
            raw_args.append(f"--{opt_name}")
        elif opt.params is not False and opt.params is not None:
            raw_args.append(f"--{opt_name}={opt.params}")
    return raw_args


def _handle_bump(subcmd: str, cmd_bags: CmdBags) -> int:
    guard_dispatch("dev")
    bump_type = subcmd.split("-", 1)[1].lower() if "-" in subcmd else subcmd.lower()
    targets = cmd_bags.args
    if not targets:
        print(f"[dev:{subcmd}] Usage: python yscb.py dev {subcmd} <module_name>")
        return 1

    mod_name = targets[0]
    src_manifest_uri = f"module.source://{mod_name}/manifest.json"
    if not vfs.exists(src_manifest_uri):
        print(f"[dev:{subcmd}] Error: Source module '{mod_name}' not found at {src_manifest_uri}.", file=sys.stderr)
        return 1

    try:
        manifest_data = vfs.read_json(src_manifest_uri)
        curr_ver = manifest_data.get("version", "1.0.0.0")
        next_ver = semver.bump_version(curr_ver, bump_type)
        manifest_data["version"] = next_ver
        vfs.write_json(src_manifest_uri, manifest_data, indent=2)
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
    desc_val = bags.get_option_value("desc")
    if desc_val:
        desc = str(desc_val).strip('\"')
    from dev.scaffold import Scaffolder
    scaffolder = Scaffolder()
    ok, msg = scaffolder.create_module(name, desc)
    print(f"[dev:create] {msg}")
    return 0 if ok else 1


def check(cmd_bags: Any) -> int:
    """Validate module structure and manifest compliance."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "check")
    from dev.checker import Checker, CheckSeverity
    checker = Checker()
    json_output = bags.has_option("json")
    check_all = bags.has_option("all") or bags.has_option("a") or not bags.args

    if check_all:
        reports = checker.check_all()
        if json_output:
            print(json.dumps({mod: rep.to_dict() for mod, rep in reports.items()}, indent=2))
            return 0 if all(rep.passed for rep in reports.values()) else 1
        title = "YS-Codebase Module Compliance Diagnostic Report"
    else:
        name = bags.args[0]
        rep = checker.check_module(name)
        if json_output:
            print(json.dumps(rep.to_dict(), indent=2))
            return 0 if rep.passed else 1
        reports = {name: rep}
        title = f"YS-Codebase Module Compliance Report: {name}"

    print("=" * 70)
    print(title)
    print("=" * 70)
    all_passed = True
    pass_cnt, warn_cnt, fail_cnt = 0, 0, 0

    for mod, rep in reports.items():
        print(f"[*] Module: {mod:<50} [{rep.status.value}]")
        if rep.status == CheckSeverity.PASS:
            pass_cnt += 1
        elif rep.status == CheckSeverity.WARN:
            warn_cnt += 1
        else:
            fail_cnt += 1
            all_passed = False

        for issue in rep.issues:
            if check_all and rep.status == CheckSeverity.WARN and issue.severity != CheckSeverity.WARN:
                continue
            loc = f" ({issue.file_path})" if issue.file_path else ""
            print(f"    |-- [{issue.severity.value}] [{issue.category}]{loc} {issue.message}")

    print("-" * 70)
    status_text = "PASSED" if all_passed and warn_cnt == 0 else ("WARNINGS FOUND" if all_passed else "FAILED (Release Blocked)")
    if check_all:
        print(f"Summary : {len(reports)} Total, {pass_cnt} Passed, {warn_cnt} Warnings, {fail_cnt} Failed")
    print(f"Status  : {status_text}")
    print("=" * 70)
    return 0 if all_passed else 1


def build(cmd_bags: Any) -> int:
    """Build dev package (.build.zip with tests)."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "build")
    from dev.builder import Builder
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
    from dev.releaser import Releaser
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
    force = bags.has_option("force") or bags.has_option("f")
    from dev.releaser import Releaser
    releaser = Releaser()

    if bags.has_option("all") or bags.has_option("a") or not bags.args:
        from dev.checker import discover_source_modules
        modules = discover_source_modules()
        all_passed = True
        print(f"[dev:release-check] Checking release readiness for all {len(modules)} modules...")
        for mod_name in modules:
            passed, errors = releaser.release_check(mod_name, force=force)
            if passed:
                print(f"  [*] Module '{mod_name}': READY (All 3 Gates Passed)")
            else:
                all_passed = False
                print(f"  [!] Module '{mod_name}': FAILED")
                for err in errors:
                    print(f"      - {err}")
        if all_passed:
            print("[dev:release-check] All modules are READY for release.")
            return 0
        else:
            print("[dev:release-check] One or more modules FAILED release check.", file=sys.stderr)
            return 1

    mod_name = bags.args[0]
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
    commit_msg = bags.get_option_value("msg") or bags.get_option_value("m")
    if len(bags.args) < 1 or (not commit_msg and len(bags.args) < 2):
        print("[dev:release-git] Usage: python yscb.py dev release-git <module_name> \"<commit message>\" [--force|-f]")
        return 1
    mod_name = bags.args[0]
    if not commit_msg:
        commit_msg = bags.args[1]
    from dev.releaser import Releaser
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
    from dev.tester import Tester
    return Tester().run(_build_tester_argv("test", bags))


def op_mksb(cmd_bags: Any) -> int:
    """Internal atomic sandbox creation operation."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "op-mksb")
    from dev.tester import Tester
    return Tester().run(_build_tester_argv("op-mksb", bags))


def op_test(cmd_bags: Any) -> int:
    """Internal atomic test runner operation."""
    guard_dispatch("dev")
    bags = _normalize_bags(cmd_bags, "op-test")
    from dev.tester import Tester
    return Tester().run(_build_tester_argv("op-test", bags))
