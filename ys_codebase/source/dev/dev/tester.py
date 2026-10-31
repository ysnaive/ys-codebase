"""
CLI Command dispatcher for 'dev test', 'dev op-mksb', and 'dev op-test'.
"""
import os
import sys
import json
import time
import unittest
import subprocess
import concurrent.futures
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from dev.testing.runner import TestDiscovery, TestRunner, ASCIIReportFormatter, get_test_category
from dev.testing.sandbox import SandboxProvisioner


def safe_print(text: Any = "", file: Any = None, end: str = "\n", flush: bool = False) -> None:
    """
    Safely output text to standard streams on Windows systems where encoding
    (e.g., cp950) might throw UnicodeEncodeError on certain special characters.
    """
    target = file or sys.stdout
    content = str(text) + end
    try:
        target.write(content)
        if flush:
            target.flush()
    except UnicodeEncodeError:
        enc = getattr(target, "encoding", None) or "utf-8"
        safe_str = content.encode(enc, errors="replace").decode(enc, errors="replace")
        try:
            target.write(safe_str)
            if flush:
                target.flush()
        except Exception:
            ascii_str = content.encode("ascii", errors="replace").decode("ascii")
            target.write(ascii_str)
            if flush:
                target.flush()
    except Exception:
        pass


@dataclass(frozen=True)
class _TestRunConfig:
    clean_argv: List[str]
    target_mod: Optional[str]
    target_param: Optional[str]
    is_all: bool
    no_build: bool
    keep_sandbox: bool
    is_sequential: bool
    quiet_mode: bool
    verbose: bool
    jobs: Optional[int]
    sync_requested: bool
    is_nested: bool


def _parse_test_run_config(argv: List[str]) -> _TestRunConfig:
    is_nested = os.environ.get("YSCB_NESTED_TEST") == "1"
    keep_sandbox = "--keep-sandbox" in argv
    no_build = "--no-build" in argv
    is_sequential = "--sequential" in argv or "--no-parallel" in argv
    quiet_mode = "-q" in argv or "--q" in argv or "--quiet" in argv or os.environ.get("YSCB_TEST_QUIET") == "1"
    verbose = "-v" in argv or "--v" in argv or "--verbose" in argv

    jobs: Optional[int] = None
    sync_requested = "--sync" in argv
    pattern_val: Optional[str] = None
    clean_argv: List[str] = []
    idx = 0
    while idx < len(argv):
        a = argv[idx]
        if a in ("--no-build", "--sequential", "--no-parallel", "--sync"):
            idx += 1
            continue
        if a.startswith("--jobs=") or a.startswith("--j="):
            try:
                jobs = int(a.split("=", 1)[1])
            except ValueError:
                pass
            idx += 1
            continue
        if a in ("-j", "--j", "--jobs"):
            if idx + 1 < len(argv):
                try:
                    jobs = int(argv[idx + 1])
                    idx += 2
                    continue
                except ValueError:
                    pass
            idx += 1
            continue
        if a.startswith("-j") and len(a) > 2 and a[2:].isdigit():
            jobs = int(a[2:])
            idx += 1
            continue
        if a in ("-k", "--k", "--pattern"):
            if idx + 1 < len(argv):
                pattern_val = argv[idx + 1]
                idx += 2
                continue
            idx += 1
            continue
        if a.startswith(("-k=", "--k=", "--pattern=")):
            pattern_val = a.split("=", 1)[1]
            idx += 1
            continue
        if a in ("-q", "--q", "--quiet", "-v", "--v", "--verbose"):
            idx += 1
            continue
        if a in ("-a", "--a"):
            clean_argv.append("--all")
            idx += 1
            continue
        clean_argv.append(a)
        idx += 1

    if pattern_val is not None:
        clean_argv.append(f"--pattern={pattern_val}")
    if quiet_mode:
        clean_argv.append("--quiet")
    if verbose:
        clean_argv.append("--verbose")

    target_mod = next((a for a in clean_argv if not a.startswith("-") and a != "test"), None)
    target_param = next((a for a in clean_argv if a.startswith("--target=")), None)
    if not target_mod and target_param:
        target_val = target_param.split("=", 1)[1]
        if ":" in target_val:
            target_mod = target_val.split(":", 1)[0]
    is_all = "--all" in clean_argv or target_mod == "--all"

    return _TestRunConfig(
        clean_argv=clean_argv,
        target_mod=target_mod,
        target_param=target_param,
        is_all=is_all,
        no_build=no_build,
        keep_sandbox=keep_sandbox,
        is_sequential=is_sequential,
        quiet_mode=quiet_mode,
        verbose=verbose,
        jobs=jobs,
        sync_requested=sync_requested,
        is_nested=is_nested,
    )


def _extract_test_cases_from_suite(node: Any) -> List[unittest.TestCase]:
    collected: List[unittest.TestCase] = []
    if isinstance(node, unittest.TestSuite):
        for sub in node:
            collected.extend(_extract_test_cases_from_suite(sub))
    elif isinstance(node, unittest.TestCase):
        collected.append(node)
    return collected


def _record_test_failure_entry(
    mod_name: str,
    test_case: unittest.TestCase,
    tb: str,
    fail_type: str,
    default_msg: str,
    captured_output: str,
) -> Tuple[str, Dict[str, Any]]:
    last_line = tb.strip().splitlines()[-1] if tb.strip() else default_msg
    loc = ""
    for line in reversed(tb.strip().splitlines()):
        if "File " in line and ", line " in line:
            loc = line.strip()
            break
    cls_name = test_case.__class__.__name__
    m_name = getattr(test_case, "_testMethodName", "")
    rerun_target = (
        f"python yscb.py dev test --target={mod_name}:{cls_name}.{m_name}"
        if m_name
        else f"python yscb.py dev test --target={mod_name}:{cls_name}"
    )
    entry = {
        "module": mod_name,
        "test": f"{cls_name}.{m_name}" if m_name else str(test_case),
        "type": fail_type,
        "message": last_line,
        "location": loc,
        "rerun": rerun_target,
        "captured_output": captured_output,
    }
    return f"{test_case}: {last_line}", entry


class Tester:
    def run(self, argv: List[str]) -> int:
        if not argv:
            self._print_usage()
            return 1

        subcmd = argv[0]
        sub_argv = argv[1:]

        if subcmd == "op-mksb":
            return self._run_op_mksb(sub_argv)
        elif subcmd == "op-test":
            return self._run_op_test(sub_argv)
        elif subcmd == "test":
            return self._run_test(sub_argv)
        else:
            return self._run_test(argv)

    def _print_usage(self) -> None:
        print("[dev:test] Usage: python yscb.py dev test [module_name | --all] [options]")
        print("Subcommands / Modes:")
        print("  dev test [mod | --all]     High-level E2E: Auto build -> Provision sandbox -> Run tests -> Teardown")
        print("  dev op-mksb [--dir=<path>] Atomic primitive: Provision isolated virtual sandbox")
        print("  dev op-test [mod | --all]  Atomic primitive: Run in-place test execution without sandboxing")
        print("Parallel & Concurrency Options:")
        print("  -j <N>, --jobs=<N>         Set max parallel worker processes (default: min(cpu_count, num_modules))")
        print("  --sequential, --no-parallel Disable parallel execution and run sequentially")
        print("Classification & Targeting Options:")
        print("  --logical        Run only unit / pure logical tests")
        print("  --env            Run environment / inter-module / DI tests")
        print("  --workflow       Run multi-step composite workflow / E2E tests (default excluded)")
        print("  --perf, --stress Run performance / stress benchmark tests (default excluded)")
        print("  --all-types      Run tests across all categories (logic + env + workflow + perf)")
        print("  --type=<type>    Filter test type (logic | env | workflow | perf | all)")
        print("  --target=<mod:[case][.method]>  Pinpoint specific module, test case or method")
        print("General Options:")
        print("  --all            Run tests across all modules in source/")
        print("  --no-build       Skip automatic pre-test hermetic build")
        print("  --keep-sandbox   Retain virtual sandbox directory upon test completion")
        print("  --sync           After 100% test pass, auto-install local @build package to environment")
        print("  -q, --quiet      Throttle output mode: compact Pass/Fail/Skip and failures only")
        print("  -v, --verbose    Expand verbose test method execution details")

    def _run_op_mksb(self, argv: List[str]) -> int:
        target_dir = None
        for a in argv:
            if a.startswith("--dir="):
                target_dir = a.split("=", 1)[1]
        try:
            ctx = SandboxProvisioner.create_sandbox(target_dir)
            print(f"[dev:op-mksb] Provisioned virtual sandbox at: {ctx.sandbox_dir}")
            return 0
        except Exception as e:
            print(f"[dev:op-mksb] Error provisioning sandbox: {e}")
            return 1

    def _run_op_test(self, argv: List[str]) -> int:
        """In-place atomic test execution engine."""
        is_sandbox_env = (
            os.environ.get("YSCB_TEST_SANDBOX") == "1"
            and (
                os.path.basename(os.getcwd()) == "host_env"
                or os.path.isdir(os.path.join(os.getcwd(), "engine"))
                or bool(os.environ.get("YSCB_SANDBOX_DIR") and os.path.isdir(os.environ.get("YSCB_SANDBOX_DIR", "")))
            )
        )
        if not is_sandbox_env:
            print("[dev:test] Security Guard Blocked: 'dev op-test' is an internal in-place runner and cannot be executed directly on the host workspace.", file=sys.stderr)
            print("           Please use 'python yscb.py dev test <module>' to run tests inside an authenticated virtual sandbox.", file=sys.stderr)
            return 1

        report_json_path = None
        quiet_report = False
        quiet_mode = False
        target_mod = None
        test_type = None
        pattern = None
        target = None
        contract_only = False
        verbose = False
        keep_sandbox = False
        run_all = False

        idx = 0
        while idx < len(argv):
            a = argv[idx]
            if a.startswith("--report-json="):
                report_json_path = a.split("=", 1)[1]
            elif a == "--quiet-report":
                quiet_report = True
            elif a in ("-q", "--q", "--quiet"):
                quiet_mode = True
            elif a in ("-a", "--a", "--all"):
                run_all = True
            elif a == "--contract-only":
                contract_only = True
            elif a in ("-v", "--v", "--verbose"):
                verbose = True
            elif a == "--keep-sandbox":
                keep_sandbox = True
            elif a == "--logical":
                test_type = "logic"
            elif a == "--env":
                test_type = "env"
            elif a == "--workflow":
                test_type = "workflow"
            elif a in ("--perf", "--stress"):
                test_type = "perf"
            elif a == "--all-types":
                test_type = "all"
            elif a.startswith("--type="):
                test_type = a.split("=", 1)[1]
            elif a.startswith("--target="):
                target = a.split("=", 1)[1]
            elif a in ("-k", "--pattern"):
                if idx + 1 < len(argv):
                    pattern = argv[idx + 1]
                    idx += 1
            elif a.startswith(("-k=", "--k=", "--pattern=")):
                pattern = a.split("=", 1)[1]
            elif not a.startswith("-"):
                target_mod = a
            idx += 1

        valid_types = {"logic", "logical", "env", "network", "workflow", "perf", "all", "all_types"}
        if test_type and test_type.lower().replace("-", "_") not in valid_types:
            print(f"[dev:test] Error: Invalid test type '{test_type}'. Valid types: logic, env, network, workflow, perf, all")
            return 1

        if target and ":" in target:
            target_mod_match = target.split(":", 1)[0]
            if target_mod_match:
                target_mod = target_mod_match

        if not target_mod and not run_all:
            target_mod = "core"

        modules = TestDiscovery.discover_modules(target_mod)
        if not modules:
            if target_mod:
                print(f"[dev:test] Error: Module '{target_mod}' not found in source/.")
            else:
                print("[dev:test] No modules found in source/.")
            return 1

        if test_type:
            tt = test_type.lower().replace("-", "_")
            filter_mode = "ALL Types" if tt in ("all", "all_types") else f"[{test_type.upper()}]"
        else:
            filter_mode = "Default (LOGIC + ENV)"

        target_scope = target if target else (target_mod if target_mod and not run_all else "All")

        runner = TestRunner(verbose=verbose, keep_sandbox=keep_sandbox)
        report_data: Dict[str, Any] = {
            "filter_mode": filter_mode,
            "target_scope": target_scope,
            "no_build": "--no-build" in argv,
            "modules": [],
            "total": 0,
            "passed": 0,
            "failed": 0,
            "unknown": 0,
            "skipped": 0,
            "duration": 0.0,
            "failures_list": [],
        }

        sandbox_id = os.environ.get("YSCB_SANDBOX_ID", "sandbox 1")
        start_time = time.perf_counter()
        all_passed = True

        for mod_name in modules:
            if not verbose and not quiet_report and not quiet_mode:
                print(f"[dev:test] {mod_name} begin test in {sandbox_id}", flush=True)
            mod_start = time.perf_counter()
            suite, contract_total, custom_total = TestDiscovery.build_suite_for_module(
                mod_name,
                test_type=test_type,
                pattern=pattern,
                target=target,
                contract_only=contract_only,
            )

            all_test_instances = _extract_test_cases_from_suite(suite)
            result, captured_output = runner.run_suite(suite)
            mod_duration = time.perf_counter() - mod_start
            if not verbose and not quiet_report and not quiet_mode:
                print(f"[dev:test] {mod_name} test finish in ({mod_duration:.2f}s)", flush=True)
            mod_total = result.testsRun
            mod_failed = len(result.failures) + len(result.errors)
            mod_skipped = len(result.skipped)
            mod_passed = mod_total - mod_failed - mod_skipped

            contract_failed = sum(1 for c, _ in result.failures + result.errors if "Contract" in c.__class__.__name__)
            custom_failed = mod_failed - contract_failed

            contract_skipped = sum(1 for c, _ in result.skipped if "Contract" in c.__class__.__name__)
            custom_skipped = mod_skipped - contract_skipped

            contract_passed = max(0, contract_total - contract_failed - contract_skipped)

            logic_passed = 0
            env_passed = 0
            workflow_passed = 0
            perf_passed = 0
            mod_unknown = 0
            unknown_methods = []

            failed_test_objs = {c for c, _ in result.failures + result.errors}
            skipped_test_objs = {c for c, _ in result.skipped}

            for test_case in all_test_instances:
                if test_case in failed_test_objs or test_case in skipped_test_objs:
                    continue
                st = getattr(test_case, "execution_status", None) or getattr(test_case, "_execution_status", None)
                if st == "UNKNOWN":
                    mod_unknown += 1
                    cls_name = test_case.__class__.__name__
                    m_name = getattr(test_case, "_testMethodName", "")
                    unknown_methods.append(f"{cls_name}.{m_name}" if m_name else str(test_case))
                    continue
                if "Contract" in test_case.__class__.__name__:
                    continue
                cat = get_test_category(test_case)
                if cat == "logic":
                    logic_passed += 1
                elif cat == "env":
                    env_passed += 1
                elif cat == "workflow":
                    workflow_passed += 1
                elif cat == "perf":
                    perf_passed += 1

            custom_passed = max(0, custom_total - custom_failed - custom_skipped - mod_unknown)
            mod_explicit_passed = max(0, mod_passed - mod_unknown)

            if mod_failed > 0 or mod_unknown > 0:
                all_passed = False

            err_msgs = []
            for test_case, tb in result.failures:
                err_str, entry = _record_test_failure_entry(mod_name, test_case, tb, "FAIL", "AssertionError", captured_output)
                err_msgs.append(err_str)
                report_data["failures_list"].append(entry)

            for test_case, tb in result.errors:
                err_str, entry = _record_test_failure_entry(mod_name, test_case, tb, "ERROR", "Error", captured_output)
                err_msgs.append(err_str)
                report_data["failures_list"].append(entry)

            for um in unknown_methods:
                err_msgs.append(f"{um}: execution status UNKNOWN (missing self.mark_passed())")
                report_data["failures_list"].append({
                    "module": mod_name,
                    "test": um,
                    "type": "UNKNOWN",
                    "message": "Missing self.mark_passed()",
                    "location": "",
                    "rerun": f"python yscb.py dev test --target={mod_name}:{um}",
                    "captured_output": captured_output,
                })

            report_data["modules"].append({
                "name": mod_name,
                "passed": (mod_failed == 0 and mod_unknown == 0),
                "duration": mod_duration,
                "contract_total": contract_total,
                "contract_passed": contract_passed,
                "custom_total": custom_total,
                "custom_passed": custom_passed,
                "logic_passed": logic_passed,
                "env_passed": env_passed,
                "workflow_passed": workflow_passed,
                "perf_passed": perf_passed,
                "unknown": mod_unknown,
                "errors": err_msgs,
            })
            report_data["total"] += mod_total
            report_data["passed"] += mod_explicit_passed
            report_data["failed"] += mod_failed
            report_data["unknown"] += mod_unknown
            report_data["skipped"] += mod_skipped

        report_data["duration"] = time.perf_counter() - start_time

        if report_json_path:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(report_json_path)), exist_ok=True)
                with open(report_json_path, "w", encoding="utf-8") as rf:
                    json.dump(report_data, rf, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[dev:test] Warning: Failed to export report JSON: {e}", file=sys.stderr)

        if not quiet_report:
            if quiet_mode:
                safe_print(ASCIIReportFormatter.format_throttled(report_data))
            else:
                safe_print(ASCIIReportFormatter.format_summary(report_data))
        return 0 if all_passed else 1

    def _execute_single_module_in_sandbox(
        self,
        op_test_args: List[str],
        report_filename: str,
        sandbox_idx: int,
        target_modules: Optional[List[str]] = None,
        quiet_mode: bool = False,
        is_nested: bool = False,
        mod_label: Optional[str] = None,
    ) -> Tuple[int, Optional[Dict[str, Any]], str, Optional[subprocess.CompletedProcess]]:
        """Unified helper to create sandbox, invoke dev op-test subprocess, and parse report JSON."""
        ctx = SandboxProvisioner.create_sandbox(target_modules=target_modules)
        sandbox_dir = ctx.sandbox_dir
        sandbox_display_id = f"sandbox {sandbox_idx}"
        host_dir = ctx.host_dir

        if not is_nested and not quiet_mode:
            safe_print(f'[dev:test] Create {sandbox_display_id} at: "{sandbox_dir}"', flush=True)
            if mod_label:
                safe_print(f"[dev:test] {mod_label} begin test in {sandbox_display_id}", flush=True)

        sandbox_yscb = os.path.join(host_dir, "yscb.py")
        report_json_path = os.path.join(ctx.engine_dir, report_filename)
        cmd = [sys.executable, sandbox_yscb, "dev", "op-test"] + op_test_args + [
            f"--report-json={report_json_path}",
            "--quiet-report",
        ]

        p_env = dict(os.environ)
        p_env["YSCB_TEST_SANDBOX"] = "1"
        p_env["YSCB_SANDBOX_DIR"] = sandbox_dir
        p_env["YSCB_SANDBOX_ID"] = sandbox_display_id
        p_env["YSCB_SANDBOX_INDEX"] = str(sandbox_idx)
        if quiet_mode:
            p_env["YSCB_TEST_QUIET"] = "1"

        report_data = None
        ret_code = 1
        res = None
        mod_start = time.perf_counter()
        try:
            res = subprocess.run(
                cmd,
                cwd=host_dir,
                env=p_env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            ret_code = res.returncode
            mod_duration = time.perf_counter() - mod_start
            if mod_label and not is_nested and not quiet_mode:
                safe_print(f"[dev:test] {mod_label} test finish in ({mod_duration:.2f}s)", flush=True)
            if os.path.isfile(report_json_path):
                try:
                    with open(report_json_path, "r", encoding="utf-8") as rf:
                        report_data = json.load(rf)
                except (OSError, json.JSONDecodeError):
                    pass
        except Exception as e:
            if not is_nested:
                err_prefix = f"Subprocess error for module '{mod_label}'" if mod_label else "Subprocess execution error"
                safe_print(f"[dev:test] {err_prefix}: {e}", file=sys.stderr)
            ret_code = 1

        return ret_code, report_data, sandbox_dir, res

    def _run_test(self, argv: List[str]) -> int:
        """High-level facade: auto dev build -> op-mksb -> run op-test in sandbox -> cleanup"""
        cfg = _parse_test_run_config(argv)

        if cfg.is_all and not cfg.is_sequential and not cfg.target_param:
            all_modules = TestDiscovery.discover_modules(None)
            if len(all_modules) > 1:
                return self._run_parallel_test(
                    cfg.clean_argv,
                    all_modules,
                    no_build=cfg.no_build,
                    keep_sandbox=cfg.keep_sandbox,
                    jobs=cfg.jobs,
                    is_nested=cfg.is_nested,
                    sync_requested=cfg.sync_requested,
                    quiet_mode=cfg.quiet_mode,
                )

        if not cfg.no_build:
            if not cfg.is_nested and not cfg.quiet_mode:
                print("[dev:test] Pre-building modules for test execution...", flush=True)
            from dev.builder import Builder
            builder = Builder()
            if cfg.target_mod and cfg.target_mod != "--all":
                ok, msg = builder.build_module(cfg.target_mod)
                if not ok:
                    print(f"[dev:test] Pre-build failed for module '{cfg.target_mod}':\n  {msg}", file=sys.stderr)
                    return 1
            else:
                results = builder.build_all()
                for m_name, (ok, msg) in results.items():
                    if not ok:
                        print(f"[dev:test] Pre-build failed for module '{m_name}':\n  {msg}", file=sys.stderr)
                        return 1

        cand_targets = ["--all"] if cfg.is_all else ([cfg.target_mod] if cfg.target_mod else None)
        sandbox_idx = int(os.environ.get("YSCB_SANDBOX_INDEX", "1"))
        sandbox_display_id = f"sandbox {sandbox_idx}"
        op_test_args = [a for a in cfg.clean_argv if a != "test"]

        ret_code, report_data, sandbox_dir, res = self._execute_single_module_in_sandbox(
            op_test_args=op_test_args,
            report_filename="report_single.json",
            sandbox_idx=sandbox_idx,
            target_modules=cand_targets,
            quiet_mode=cfg.quiet_mode,
            is_nested=cfg.is_nested,
        )

        if not cfg.is_nested:
            if cfg.verbose:
                if res and res.stdout:
                    safe_print(res.stdout, end="", flush=True)
                if res and res.stderr:
                    safe_print(res.stderr, end="", file=sys.stderr, flush=True)
                if report_data:
                    safe_print(ASCIIReportFormatter.format_summary(report_data))
            elif cfg.quiet_mode:
                if report_data:
                    safe_print(ASCIIReportFormatter.format_throttled(report_data))
                else:
                    safe_print("Pass: 0, Fail: 1, Skip: 0")
                    if res and res.stderr:
                        tail = "\n".join(res.stderr.strip().splitlines()[-20:])
                        safe_print(f"\n[dev:test] Subprocess execution failed with code {ret_code}:\n{tail}", file=sys.stderr)
            else:
                if report_data:
                    w_lines = [line for line in ((res.stderr if res else "") or "").splitlines() if line.strip()]
                    safe_print(ASCIIReportFormatter.format_summary(report_data, warnings_count=len(w_lines)))
                else:
                    safe_print(f"[dev:test] Subprocess execution failed with code {ret_code}.", file=sys.stderr)
                    if res and res.stderr:
                        tail = "\n".join(res.stderr.strip().splitlines()[-20:])
                        safe_print(f"[dev:test] Stderr tail:\n{tail}", file=sys.stderr)

        if ret_code == 0 and not cfg.keep_sandbox:
            if not cfg.is_nested and not cfg.quiet_mode:
                print(f"[dev:test] Cleaned up {sandbox_display_id}", flush=True)
            if "--all" in cfg.clean_argv:
                SandboxProvisioner.cleanup_all_sandboxes()
            else:
                SandboxProvisioner.cleanup_sandbox(sandbox_dir, force=True)
        else:
            SandboxProvisioner.prune_sandboxes(max_keep=3)
            if not cfg.is_nested:
                if ret_code != 0:
                    print(f"[dev:test] Test failed. Sandbox preserved at: {sandbox_dir}")
                elif not cfg.quiet_mode:
                    print(f"[dev:test] Sandbox preserved at: {sandbox_dir}")

        if ret_code == 0 and not cfg.is_nested:
            tested_mods = [cfg.target_mod] if (cfg.target_mod and cfg.target_mod != "--all") else []
            self._handle_post_test_sync(tested_mods, cfg.sync_requested, quiet=cfg.quiet_mode)

        return ret_code

    def _run_parallel_test(
        self,
        clean_argv: List[str],
        modules: List[str],
        no_build: bool = False,
        keep_sandbox: bool = False,
        jobs: Optional[int] = None,
        is_nested: bool = False,
        sync_requested: bool = False,
        quiet_mode: bool = False,
    ) -> int:
        """Runs multiple modules concurrently across independent virtual sandboxes."""
        if not no_build:
            if not is_nested and not quiet_mode:
                print("[dev:test] Pre-building modules for test execution...", flush=True)
            from dev.builder import Builder
            builder = Builder()
            results = builder.build_all()
            for m_name, (ok, msg) in results.items():
                if not ok:
                    print(f"[dev:test] Pre-build failed for module '{m_name}':\n  {msg}", file=sys.stderr)
                    return 1

        SandboxProvisioner.adapt_build_pip_dependencies(target_modules=modules)

        cpu_limit = os.cpu_count() or 4
        max_workers = jobs if (jobs and jobs > 0) else min(cpu_limit, len(modules))

        start_time = time.perf_counter()
        worker_results: Dict[str, Dict[str, Any]] = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for idx, mod_name in enumerate(modules):
                kw = {
                    "worker_idx": idx + 1,
                    "clean_argv": clean_argv,
                    "keep_sandbox": keep_sandbox,
                    "is_nested": is_nested,
                }
                if quiet_mode:
                    kw["quiet_mode"] = True
                f = executor.submit(self._run_single_module_worker, mod_name, **kw)
                futures[f] = mod_name
            for future in concurrent.futures.as_completed(futures):
                mod_name = futures[future]
                try:
                    worker_results[mod_name] = future.result()
                except Exception as e:
                    if not is_nested:
                        print(f"[dev:test] Worker error for '{mod_name}': {e}", file=sys.stderr)
                    worker_results[mod_name] = {
                        "module": mod_name,
                        "worker_idx": 0,
                        "returncode": 1,
                        "report_data": None,
                        "sandbox_dir": "",
                    }

        all_passed = True
        aggregated_modules = []
        total_tests = 0
        total_passed = 0
        total_failed = 0
        total_unknown = 0
        total_skipped = 0
        failures_list = []
        filter_mode = "Default (LOGIC + ENV)"

        for mod_name in modules:
            w_res = worker_results.get(mod_name)
            if not w_res or w_res["returncode"] != 0:
                all_passed = False

            rep = w_res.get("report_data") if w_res else None
            if rep and rep.get("modules"):
                filter_mode = rep.get("filter_mode", filter_mode)
                aggregated_modules.append(rep["modules"][0])
                total_tests += rep.get("total", 0)
                total_passed += rep.get("passed", 0)
                total_failed += rep.get("failed", 0)
                total_unknown += rep.get("unknown", 0)
                total_skipped += rep.get("skipped", 0)
                failures_list.extend(rep.get("failures_list", []))
            else:
                all_passed = False
                aggregated_modules.append({
                    "name": mod_name,
                    "passed": False,
                    "duration": 0.0,
                    "contract_total": 0,
                    "contract_passed": 0,
                    "custom_total": 0,
                    "custom_passed": 0,
                    "logic_passed": 0,
                    "env_passed": 0,
                    "workflow_passed": 0,
                    "perf_passed": 0,
                    "unknown": 0,
                    "errors": [f"Execution failed with code {w_res.get('returncode') if w_res else 1}"],
                })
                total_failed += 1

        parallel_duration = time.perf_counter() - start_time
        final_report: Dict[str, Any] = {
            "filter_mode": filter_mode,
            "target_scope": "All",
            "no_build": no_build,
            "modules": aggregated_modules,
            "total": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "unknown": total_unknown,
            "skipped": total_skipped,
            "duration": parallel_duration,
            "failures_list": failures_list,
        }

        total_warnings = sum(w.get("warnings_count", 0) for w in worker_results.values() if w)
        if not is_nested:
            if quiet_mode:
                safe_print(ASCIIReportFormatter.format_throttled(final_report))
            else:
                safe_print(ASCIIReportFormatter.format_summary(final_report, warnings_count=total_warnings))

        if all_passed and not keep_sandbox:
            if "--all" in clean_argv:
                SandboxProvisioner.cleanup_all_sandboxes()
        else:
            SandboxProvisioner.prune_sandboxes(max_keep=8)

        ret_code = 0 if all_passed else 1
        if ret_code == 0 and not is_nested:
            self._handle_post_test_sync(modules, sync_requested, quiet=quiet_mode)

        return ret_code

    def _run_single_module_worker(
        self,
        mod_name: str,
        worker_idx: int,
        clean_argv: List[str],
        keep_sandbox: bool = False,
        is_nested: bool = False,
        quiet_mode: bool = False,
    ) -> Dict[str, Any]:
        """Worker executing a single module inside an isolated sandbox."""
        verbose = "-v" in clean_argv or "--verbose" in clean_argv
        opts_only = [a for a in clean_argv if a.startswith("-") and a != "--all"]
        op_test_args = opts_only + [mod_name]

        ret_code, mod_report_data, sandbox_dir, res = self._execute_single_module_in_sandbox(
            op_test_args=op_test_args,
            report_filename=f"report_{mod_name}.json",
            sandbox_idx=worker_idx,
            quiet_mode=quiet_mode,
            is_nested=is_nested,
            mod_label=mod_name,
        )

        if not is_nested and not quiet_mode and verbose and res:
            if res.stdout:
                safe_print(res.stdout, end="", flush=True)
            if res.stderr:
                safe_print(res.stderr, end="", file=sys.stderr, flush=True)

        sandbox_display_id = f"sandbox {worker_idx}"
        if ret_code == 0 and not keep_sandbox:
            if not is_nested and not quiet_mode:
                print(f"[dev:test] Cleaned up {sandbox_display_id}", flush=True)
            SandboxProvisioner.cleanup_sandbox(sandbox_dir, force=True)
        else:
            if not is_nested:
                if ret_code != 0:
                    print(f"[dev:test] Test failed. Sandbox preserved at: {sandbox_dir}", flush=True)
                elif not quiet_mode:
                    print(f"[dev:test] Sandbox preserved at: {sandbox_dir}", flush=True)

        w_count = len([line for line in ((res.stderr if res else "") or "").splitlines() if line.strip()])
        return {
            "module": mod_name,
            "worker_idx": worker_idx,
            "returncode": ret_code,
            "report_data": mod_report_data,
            "sandbox_dir": sandbox_dir,
            "warnings_count": w_count,
        }

    def _handle_post_test_sync(self, modules: List[str], sync_requested: bool, quiet: bool = False) -> None:
        """處理測試成功後的 --sync 本地直裝或友善引導提示。"""
        if not modules:
            return

        host_dir = os.environ.get("YSCB_HOST_DIR") or os.getcwd()
        cfg_path = os.path.join(host_dir, "yscb.config.json")
        installed_mods = {}
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as rf:
                    cfg_data = json.load(rf)
                    installed_mods = cfg_data.get("installed_modules", {})
            except (OSError, json.JSONDecodeError):
                pass

        valid_targets = [m for m in modules if m in installed_mods]
        if not valid_targets:
            return

        yscb_py = os.path.join(host_dir, "yscb.py")
        if sync_requested:
            for mod in valid_targets:
                safe_print(f"\n[dev:test:sync] Auto-installing '{mod}@build' into local environment...")
                cmd = [sys.executable, yscb_py, "install", f"{mod}@build", "--force"]
                res = subprocess.run(cmd, cwd=host_dir)
                if res.returncode == 0:
                    safe_print(f"[dev:test:sync] Successfully synced '{mod}@build'.")
                else:
                    safe_print(f"[dev:test:sync] Failed to sync '{mod}@build'.", file=sys.stderr)
        elif not quiet:
            for mod in valid_targets:
                safe_print(f"\n[*] Hint: Tests passed! Run 'python yscb.py install {mod}@build' to install the built package.")
