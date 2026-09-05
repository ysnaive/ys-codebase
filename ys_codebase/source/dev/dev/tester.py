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
from typing import List, Dict, Any, Optional, Tuple
from dev.testing.runner import TestDiscovery, TestRunner, ASCIIReportFormatter, get_test_category
from dev.testing.sandbox import SandboxProvisioner, SandboxContext

def safe_print(text: Any = "", file=None, end: str = "\n", flush: bool = False) -> None:
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


class Tester:
    def __init__(self):
        pass

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
            # Invoked as Tester.run(["core", ...]) or with arguments directly
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
        # Gate 0: Block direct host execution to prevent sandbox leakage
        is_sandbox_env = (
            os.environ.get("YSCB_TEST_SANDBOX") == "1"
            and (
                os.path.basename(os.getcwd()) == "host_env"
                or os.path.isdir(os.path.join(os.getcwd(), "engine"))
                or (os.environ.get("YSCB_SANDBOX_DIR") and os.path.isdir(os.environ.get("YSCB_SANDBOX_DIR")))
            )
        )
        if not is_sandbox_env:
            print("[dev:test] Security Guard Blocked: 'dev op-test' is an internal in-place runner and cannot be executed directly on the host workspace.", file=sys.stderr)
            print("           Please use 'python yscb.py dev test <module>' to run tests inside an authenticated virtual sandbox.", file=sys.stderr)
            return 1

        report_json_path = None
        quiet_report = False
        quiet_mode = os.environ.get("YSCB_TEST_QUIET") == "1"
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
            elif a in ("-q", "--quiet"):
                quiet_mode = True
            elif a == "--all":
                run_all = True
            elif a == "--contract-only":
                contract_only = True
            elif a in ("-v", "--verbose"):
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
            elif a.startswith("-k="):
                pattern = a.split("=", 1)[1]
            elif not a.startswith("-"):
                target_mod = a
            idx += 1

        VALID_TYPES = {"logic", "logical", "env", "host_cli", "workflow", "perf", "performance", "stress", "all", "all_types", "all-types"}
        if test_type and test_type.lower().replace("-", "_") not in {t.replace("-", "_") for t in VALID_TYPES}:
            print(f"[dev:test] Error: Invalid test type '{test_type}'. Valid types: logic, env, workflow, perf, all")
            return 1

        if target:
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

        # Determine filter mode string for report metadata
        if test_type:
            tt = test_type.lower().replace("-", "_")
            if tt in ("all", "all_types"):
                filter_mode = "ALL Types"
            else:
                filter_mode = f"[{test_type.upper()}]"
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
            "skipped": 0,
            "duration": 0.0,
            "failures_list": []
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
                contract_only=contract_only
            )
            
            result, captured_output = runner.run_suite(suite)
            mod_duration = time.perf_counter() - mod_start
            if not verbose and not quiet_report and not quiet_mode:
                print(f"[dev:test] {mod_name} test finish in ({mod_duration:.2f}s)", flush=True)
            mod_total = result.testsRun
            mod_failed = len(result.failures) + len(result.errors)
            mod_skipped = len(result.skipped)
            mod_passed = mod_total - mod_failed - mod_skipped
            
            if mod_failed > 0:
                all_passed = False

            # Accurate classification based on TestCase class name
            contract_failed = sum(1 for c, _ in result.failures + result.errors if "Contract" in c.__class__.__name__)
            custom_failed = mod_failed - contract_failed

            contract_skipped = sum(1 for c, _ in result.skipped if "Contract" in c.__class__.__name__)
            custom_skipped = mod_skipped - contract_skipped

            contract_passed = max(0, contract_total - contract_failed - contract_skipped)
            custom_passed = max(0, custom_total - custom_failed - custom_skipped)

            # Taxonomy breakdown for custom passed tests
            logic_passed = 0
            env_passed = 0
            workflow_passed = 0
            perf_passed = 0
            
            failed_test_objs = set(c for c, _ in result.failures + result.errors)
            skipped_test_objs = set(c for c, _ in result.skipped)
            
            def _tally_custom(node: Any):
                nonlocal logic_passed, env_passed, workflow_passed, perf_passed
                if isinstance(node, unittest.TestSuite):
                    for sub in node:
                        _tally_custom(sub)
                elif isinstance(node, unittest.TestCase):
                    if "Contract" in node.__class__.__name__:
                        return
                    if node not in failed_test_objs and node not in skipped_test_objs:
                        cat = get_test_category(node)
                        if cat == "logic":
                            logic_passed += 1
                        elif cat == "env":
                            env_passed += 1
                        elif cat == "workflow":
                            workflow_passed += 1
                        elif cat == "perf":
                            perf_passed += 1
            _tally_custom(suite)

            err_msgs = []
            for test_case, tb in result.failures:
                last_line = tb.strip().splitlines()[-1] if tb.strip() else "AssertionError"
                loc = ""
                for l in reversed(tb.strip().splitlines()):
                    if "File " in l and ", line " in l:
                        loc = l.strip()
                        break
                cls_name = test_case.__class__.__name__
                m_name = getattr(test_case, "_testMethodName", "")
                rerun_target = f"python yscb.py dev test --target={mod_name}:{cls_name}.{m_name}" if m_name else f"python yscb.py dev test --target={mod_name}:{cls_name}"
                err_msgs.append(f"{test_case}: {last_line}")
                report_data["failures_list"].append({
                    "module": mod_name,
                    "test": f"{cls_name}.{m_name}" if m_name else str(test_case),
                    "type": "FAIL",
                    "message": last_line,
                    "location": loc,
                    "rerun": rerun_target,
                    "captured_output": captured_output
                })
            for test_case, tb in result.errors:
                last_line = tb.strip().splitlines()[-1] if tb.strip() else "Error"
                loc = ""
                for l in reversed(tb.strip().splitlines()):
                    if "File " in l and ", line " in l:
                        loc = l.strip()
                        break
                cls_name = test_case.__class__.__name__
                m_name = getattr(test_case, "_testMethodName", "")
                rerun_target = f"python yscb.py dev test --target={mod_name}:{cls_name}.{m_name}" if m_name else f"python yscb.py dev test --target={mod_name}:{cls_name}"
                err_msgs.append(f"{test_case}: {last_line}")
                report_data["failures_list"].append({
                    "module": mod_name,
                    "test": f"{cls_name}.{m_name}" if m_name else str(test_case),
                    "type": "ERROR",
                    "message": last_line,
                    "location": loc,
                    "rerun": rerun_target,
                    "captured_output": captured_output
                })

            mod_info = {
                "name": mod_name,
                "passed": mod_failed == 0,
                "duration": mod_duration,
                "contract_total": contract_total,
                "contract_passed": contract_passed,
                "custom_total": custom_total,
                "custom_passed": custom_passed,
                "logic_passed": logic_passed,
                "env_passed": env_passed,
                "workflow_passed": workflow_passed,
                "perf_passed": perf_passed,
                "errors": err_msgs
            }
            report_data["modules"].append(mod_info)
            report_data["total"] += mod_total
            report_data["passed"] += mod_passed
            report_data["failed"] += mod_failed
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

    def _run_test(self, argv: List[str]) -> int:
        """High-level facade: auto dev build -> op-mksb -> run op-test in sandbox -> cleanup"""
        is_nested = os.environ.get("YSCB_NESTED_TEST") == "1"
        keep_sandbox = "--keep-sandbox" in argv
        no_build = "--no-build" in argv
        is_sequential = "--sequential" in argv or "--no-parallel" in argv
        quiet_mode = "-q" in argv or "--quiet" in argv or os.environ.get("YSCB_TEST_QUIET") == "1"
        verbose = "-v" in argv or "--verbose" in argv
        
        # Parse -j / --jobs and --sync
        jobs = None
        sync_requested = "--sync" in argv
        clean_argv = []
        idx = 0
        while idx < len(argv):
            a = argv[idx]
            if a in ("--no-build", "--sequential", "--no-parallel", "--sync"):
                idx += 1
                continue
            if a.startswith("--jobs="):
                try:
                    jobs = int(a.split("=", 1)[1])
                except ValueError:
                    pass
                idx += 1
                continue
            if a == "-j" or a == "--jobs":
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
            clean_argv.append(a)
            idx += 1

        target_mod = next((a for a in clean_argv if not a.startswith("-") and a != "test"), None)
        is_all = "--all" in clean_argv or target_mod == "--all"
        target_param = next((a for a in clean_argv if a.startswith("--target=")), None)

        # Multi-module parallel dispatch if --all (or multiple modules) and not sequential and no single target
        if is_all and not is_sequential and not target_param:
            all_modules = TestDiscovery.discover_modules(None)
            if len(all_modules) > 1:
                return self._run_parallel_test(
                    clean_argv,
                    all_modules,
                    no_build=no_build,
                    keep_sandbox=keep_sandbox,
                    jobs=jobs,
                    is_nested=is_nested,
                    sync_requested=sync_requested,
                    quiet_mode=quiet_mode
                )

        # 1. Automatic pre-test Hermetic Dev Build (unless --no-build)
        if not no_build:
            if not is_nested and not quiet_mode:
                print("[dev:test] Pre-building modules for test execution...", flush=True)
            from dev.builder import Builder
            builder = Builder()
            if target_mod and target_mod != "--all":
                ok, msg = builder.build_module(target_mod)
                if not ok:
                    print(f"[dev:test] Pre-build failed for module '{target_mod}':\n  {msg}", file=sys.stderr)
                    return 1
            else:
                results = builder.build_all()
                for m_name, (ok, msg) in results.items():
                    if not ok:
                        print(f"[dev:test] Pre-build failed for module '{m_name}':\n  {msg}", file=sys.stderr)
                        return 1
        
        # 2. Provision virtual sandbox (resolves from build:// -> mirror:// -> provider)
        cand_targets = ["--all"] if is_all else ([target_mod] if target_mod else None)
        ctx = SandboxProvisioner.create_sandbox(target_modules=cand_targets)
        sandbox_dir = ctx.sandbox_dir
        sandbox_idx = int(os.environ.get("YSCB_SANDBOX_INDEX", "1"))
        sandbox_display_id = f"sandbox {sandbox_idx}"
        host_dir = ctx.host_dir
        if not is_nested and not quiet_mode:
            print(f'[dev:test] Create {sandbox_display_id} at: "{sandbox_dir}"', flush=True)
        
        # 3. Invoke dev op-test inside sandbox via JSON IPC
        sandbox_yscb = os.path.join(host_dir, "yscb.py")
        report_json_path = os.path.join(ctx.engine_dir, "report_single.json")
        op_test_args = [a for a in clean_argv if a != "test"]
        op_test_args.extend([f"--report-json={report_json_path}", "--quiet-report"])
        cmd = [sys.executable, sandbox_yscb, "dev", "op-test"] + op_test_args
        
        p_env = dict(os.environ)
        p_env["YSCB_TEST_SANDBOX"] = "1"
        p_env["YSCB_SANDBOX_DIR"] = sandbox_dir
        p_env["YSCB_SANDBOX_ID"] = sandbox_display_id
        if quiet_mode:
            p_env["YSCB_TEST_QUIET"] = "1"

        report_data = None
        ret_code = 1
        res = None
        try:
            res = subprocess.run(
                cmd,
                cwd=host_dir,
                env=p_env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            ret_code = res.returncode
            if os.path.isfile(report_json_path):
                try:
                    with open(report_json_path, "r", encoding="utf-8") as rf:
                        report_data = json.load(rf)
                except Exception:
                    pass
        except Exception as e:
            if not is_nested:
                safe_print(f"[dev:test] Subprocess execution error: {e}", file=sys.stderr)
            ret_code = 1

        # Output shielding & dual-mode rendering
        if not is_nested:
            if verbose:
                if res and res.stdout:
                    safe_print(res.stdout, end="", flush=True)
                if res and res.stderr:
                    safe_print(res.stderr, end="", file=sys.stderr, flush=True)
                if report_data:
                    safe_print(ASCIIReportFormatter.format_summary(report_data))
            elif quiet_mode:
                if report_data:
                    safe_print(ASCIIReportFormatter.format_throttled(report_data))
                else:
                    safe_print(f"Pass: 0, Fail: 1, Skip: 0")
                    if res and res.stderr:
                        tail = "\n".join(res.stderr.strip().splitlines()[-20:])
                        safe_print(f"\n[dev:test] Subprocess execution failed with code {ret_code}:\n{tail}", file=sys.stderr)
            else:
                if report_data:
                    w_lines = [l for l in ((res.stderr if res else "") or "").splitlines() if l.strip()]
                    safe_print(ASCIIReportFormatter.format_summary(report_data, warnings_count=len(w_lines)))
                else:
                    safe_print(f"[dev:test] Subprocess execution failed with code {ret_code}.", file=sys.stderr)
                    if res and res.stderr:
                        tail = "\n".join(res.stderr.strip().splitlines()[-20:])
                        safe_print(f"[dev:test] Stderr tail:\n{tail}", file=sys.stderr)
            
        # 4. Teardown policy
        if ret_code == 0 and not keep_sandbox:
            if not is_nested and not quiet_mode:
                print(f"[dev:test] Cleaned up {sandbox_display_id}", flush=True)
            if "--all" in clean_argv:
                SandboxProvisioner.cleanup_all_sandboxes()
            else:
                SandboxProvisioner.cleanup_sandbox(sandbox_dir, force=True)
        else:
            SandboxProvisioner.prune_sandboxes(max_keep=3)
            if not is_nested:
                if ret_code != 0:
                    print(f"[dev:test] Test failed. Sandbox preserved at: {sandbox_dir}")
                elif not quiet_mode:
                    print(f"[dev:test] Sandbox preserved at: {sandbox_dir}")

        if ret_code == 0 and not is_nested:
            tested_mods = [target_mod] if (target_mod and target_mod != "--all") else []
            self._handle_post_test_sync(tested_mods, sync_requested, quiet=quiet_mode)

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
        quiet_mode: bool = False
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
                    res_data = future.result()
                    worker_results[mod_name] = res_data
                except Exception as e:
                    if not is_nested:
                        print(f"[dev:test] Worker error for '{mod_name}': {e}", file=sys.stderr)
                    worker_results[mod_name] = {
                        "module": mod_name,
                        "worker_idx": 0,
                        "returncode": 1,
                        "report_data": None,
                        "sandbox_dir": ""
                    }

        # Aggregate report
        all_passed = True
        aggregated_modules = []
        total_tests = 0
        total_passed = 0
        total_failed = 0
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
                m_info = rep["modules"][0]
                aggregated_modules.append(m_info)
                total_tests += rep.get("total", 0)
                total_passed += rep.get("passed", 0)
                total_failed += rep.get("failed", 0)
                total_skipped += rep.get("skipped", 0)
                failures_list.extend(rep.get("failures_list", []))
            else:
                # Fallback if module failed before exporting report
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
                    "errors": [f"Execution failed with code {w_res.get('returncode') if w_res else 1}"]
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
            "skipped": total_skipped,
            "duration": parallel_duration,
            "failures_list": failures_list
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
            SandboxProvisioner.prune_sandboxes(max_keep=3)

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
        quiet_mode: bool = False
    ) -> Dict[str, Any]:
        """Worker executing a single module inside an isolated sandbox."""
        ctx = SandboxProvisioner.create_sandbox()
        sandbox_dir = ctx.sandbox_dir
        sandbox_display_id = f"sandbox {worker_idx}"
        host_dir = ctx.host_dir
        verbose = "-v" in clean_argv or "--verbose" in clean_argv
        if not is_nested and not quiet_mode:
            safe_print(f'[dev:test] Create {sandbox_display_id} at: "{sandbox_dir}"', flush=True)
            safe_print(f"[dev:test] {mod_name} begin test in {sandbox_display_id}", flush=True)

        sandbox_yscb = os.path.join(host_dir, "yscb.py")
        op_test_args = [a for a in clean_argv if a != "test" and a != "--all"] + [mod_name]
        
        report_json_path = os.path.join(ctx.engine_dir, f"report_{mod_name}.json")
        op_test_args.extend([f"--report-json={report_json_path}", "--quiet-report"])

        cmd = [sys.executable, sandbox_yscb, "dev", "op-test"] + op_test_args
        p_env = dict(os.environ)
        p_env["YSCB_TEST_SANDBOX"] = "1"
        p_env["YSCB_SANDBOX_DIR"] = sandbox_dir
        p_env["YSCB_SANDBOX_ID"] = sandbox_display_id
        p_env["YSCB_SANDBOX_INDEX"] = str(worker_idx)
        if quiet_mode:
            p_env["YSCB_TEST_QUIET"] = "1"

        mod_report_data = None
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
                errors="replace"
            )
            ret_code = res.returncode
            mod_duration = time.perf_counter() - mod_start
            if not is_nested and not quiet_mode:
                safe_print(f"[dev:test] {mod_name} test finish in ({mod_duration:.2f}s)", flush=True)
                if verbose:
                    if res.stdout:
                        safe_print(res.stdout, end="", flush=True)
                    if res.stderr:
                        safe_print(res.stderr, end="", file=sys.stderr, flush=True)
            if os.path.isfile(report_json_path):
                with open(report_json_path, "r", encoding="utf-8") as rf:
                    mod_report_data = json.load(rf)
        except Exception as e:
            if not is_nested:
                safe_print(f"[dev:test] Subprocess error for module '{mod_name}': {e}", file=sys.stderr)
            ret_code = 1

        # Granular cleanup policy
        if ret_code == 0 and not keep_sandbox:
            if not is_nested and not quiet_mode:
                print(f"[dev:test] Cleaned up {sandbox_display_id}", flush=True)
            SandboxProvisioner.cleanup_sandbox(sandbox_dir, force=True)
        else:
            SandboxProvisioner.prune_sandboxes(max_keep=3)
            if not is_nested:
                if ret_code != 0:
                    print(f"[dev:test] Test failed. Sandbox preserved at: {sandbox_dir}", flush=True)
                elif not quiet_mode:
                    print(f"[dev:test] Sandbox preserved at: {sandbox_dir}", flush=True)

        w_count = len([l for l in ((res.stderr if res else "") or "").splitlines() if l.strip()])
        return {
            "module": mod_name,
            "worker_idx": worker_idx,
            "returncode": ret_code,
            "report_data": mod_report_data,
            "sandbox_dir": sandbox_dir,
            "warnings_count": w_count
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
            except Exception:
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
        else:
            if not quiet:
                for mod in valid_targets:
                    safe_print(f"\n[*] Hint: Tests passed! Run 'python yscb.py install {mod}@build' to install the built package.")

